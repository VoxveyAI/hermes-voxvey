"""Argparse wiring for `hermes voxvey ...`."""

from __future__ import annotations

import argparse
import uuid

from voxvey.oauth import (
    VOXVEY_PROVIDER_ID,
    login_with_device_code,
    login_with_pkce,
    save_to_hermes_pool,
)
from voxvey.realtime import DEFAULT_REALTIME_MODEL, create_client_secret, websocket_url


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="voxvey_command")

    login = subs.add_parser("login", help="Login to Voxvey with OAuth")
    login.add_argument("--device", action="store_true", help="Use OAuth device-code login.")
    login.add_argument("--manual-paste", action="store_true", help="Paste the redirected callback URL in the terminal.")
    login.add_argument("--no-browser", action="store_true", help="Print login URLs without opening a browser.")
    login.add_argument("--label", default="", help="Credential label to store in Hermes.")
    login.add_argument("--timeout", type=float, default=180.0)

    key = subs.add_parser("api-key", help="Store a Voxvey API key in the Hermes credential pool")
    key.add_argument("--api-key", default="", help="API key/token. If omitted, prompts securely when possible.")
    key.add_argument("--label", default="", help="Credential label to store in Hermes.")

    subs.add_parser("status", help="Show whether Voxvey credentials are available")

    realtime = subs.add_parser("realtime-secret", help="Create a Voxvey realtime client secret")
    realtime.add_argument("--model", default=DEFAULT_REALTIME_MODEL)
    realtime.add_argument("--voice", default="")
    realtime.add_argument("--instructions", default="")
    realtime.add_argument("--expires-seconds", type=int, default=600)
    subparser.set_defaults(func=voxvey_command)


def _store_api_key(args: argparse.Namespace) -> int:
    token = (getattr(args, "api_key", "") or "").strip()
    if not token:
        try:
            import getpass

            token = getpass.getpass("Paste your Voxvey API key/token: ").strip()
        except Exception:
            token = input("Paste your Voxvey API key/token: ").strip()
    if not token:
        raise SystemExit("No Voxvey API key/token provided.")

    try:
        from agent.credential_pool import AUTH_TYPE_API_KEY, PooledCredential, load_pool
    except Exception as exc:
        raise SystemExit("Hermes credential pool is not importable. Run inside Hermes Agent.") from exc

    pool = load_pool(VOXVEY_PROVIDER_ID)
    entry = PooledCredential(
        provider=VOXVEY_PROVIDER_ID,
        id=uuid.uuid4().hex[:6],
        label=(getattr(args, "label", "") or "").strip() or "voxvey-api-key",
        auth_type=AUTH_TYPE_API_KEY,
        priority=0,
        source="manual",
        access_token=token,
    )
    pool.add_entry(entry)
    print(f'Saved Voxvey API key credential: "{entry.label}"')
    return 0


def _status() -> int:
    from voxvey.client import get_voxvey_token

    token = get_voxvey_token()
    print("Voxvey credentials: " + ("available" if token else "not configured"))
    return 0 if token else 1


def voxvey_command(args: argparse.Namespace) -> int:
    command = getattr(args, "voxvey_command", None)
    if not command:
        print("usage: hermes voxvey {login,api-key,status}")
        return 2
    if command == "status":
        return _status()
    if command == "api-key":
        return _store_api_key(args)
    if command == "realtime-secret":
        session = {"model": args.model}
        if getattr(args, "voice", ""):
            session["voice"] = args.voice
        if getattr(args, "instructions", ""):
            session["instructions"] = args.instructions
        secret = create_client_secret(
            model=args.model,
            session=session,
            expires_seconds=getattr(args, "expires_seconds", 600),
        )
        print(f"Realtime WebSocket URL: {websocket_url()}")
        print(f"Client secret: {secret.get('value', '')}")
        print(f"Expires at: {secret.get('expires_at', '')}")
        return 0
    if command == "login":
        if getattr(args, "device", False):
            tokens = login_with_device_code(
                open_browser=not getattr(args, "no_browser", False),
                timeout=float(getattr(args, "timeout", 180.0) or 180.0),
            )
            source = "manual:voxvey_device_code"
        else:
            tokens = login_with_pkce(
                open_browser=not getattr(args, "no_browser", False),
                manual_paste=bool(getattr(args, "manual_paste", False)),
                timeout=float(getattr(args, "timeout", 180.0) or 180.0),
            )
            source = "manual:voxvey_pkce"
        entry = save_to_hermes_pool(tokens, label=(getattr(args, "label", "") or "").strip() or None, source=source)
        print(f'Saved Voxvey OAuth credentials: "{entry.label}"')
        return 0
    print(f"unknown voxvey command: {command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxvey")
    register_cli(parser)
    args = parser.parse_args(argv)
    return voxvey_command(args)
