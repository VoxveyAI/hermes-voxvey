"""Voxvey OAuth helpers for Hermes credential pools.

The upstream Hermes runtime can already consume a plugin provider's credential
pool entry as a bearer token through the API-key provider path. These helpers
perform OAuth and save the resulting access token into the `voxvey` pool so
Hermes can use it exactly like an API key at request time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from .client import DEFAULT_BASE_URL


VOXVEY_PROVIDER_ID = "voxvey"
VOXVEY_DISPLAY_NAME = "Voxvey"
VOXVEY_CLIENT_ID = "7KQEibIeoh7N6vZLbUbbUtbQTlVDuRJv"
VOXVEY_ISSUER = "https://login.onehelio.com/"
VOXVEY_AUTHORIZATION_ENDPOINT = "https://login.onehelio.com/authorize"
VOXVEY_TOKEN_ENDPOINT = "https://login.onehelio.com/oauth/token"
VOXVEY_DEVICE_AUTHORIZATION_ENDPOINT = "https://login.onehelio.com/oauth/device/code"
VOXVEY_USERINFO_ENDPOINT = "https://login.onehelio.com/userinfo"
VOXVEY_SCOPE = "openid profile email offline_access"
VOXVEY_REDIRECT_HOST = "127.0.0.1"
VOXVEY_REDIRECT_PORT = 56128
VOXVEY_REDIRECT_PATH = "/voxvey/callback"
VOXVEY_BASE_URL_ENV = "VOXVEY_BASE_URL"


class VoxveyOAuthError(RuntimeError):
    pass


@dataclass
class VoxveyOAuthTokens:
    access_token: str
    refresh_token: str = ""
    id_token: str = ""
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str = ""

    @property
    def expires_at_ms(self) -> int | None:
        if not self.expires_in:
            return None
        return int((time.time() + int(self.expires_in)) * 1000)


def _post_form(url: str, data: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw or exc.reason}
        error = payload.get("error") if isinstance(payload, dict) else str(payload)
        description = payload.get("error_description") if isinstance(payload, dict) else ""
        raise VoxveyOAuthError(str(description or error or exc.reason)) from exc


def _pkce_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _build_authorize_url(*, redirect_uri: str, code_challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": VOXVEY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": VOXVEY_SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{VOXVEY_AUTHORIZATION_ENDPOINT}?{query}"


def _parse_callback_url(callback_url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(callback_url.strip())
    values = urllib.parse.parse_qs(parsed.query or parsed.fragment)
    return {key: value[-1] for key, value in values.items() if value}


def _prompt_for_callback_url(redirect_uri: str) -> dict[str, str]:
    print()
    print("After login, paste the full redirected URL here.")
    print(f"Expected redirect starts with: {redirect_uri}")
    pasted = input("Redirect URL: ").strip()
    if not pasted:
        raise VoxveyOAuthError("No redirect URL pasted.")
    return _parse_callback_url(pasted)


def _start_callback_server() -> tuple[ThreadingHTTPServer, Thread, dict[str, str], str]:
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_GET(self) -> None:
            result.update(_parse_callback_url(f"http://{self.headers.get('Host')}{self.path}"))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Voxvey login complete. You can return to Hermes.")

    server = ThreadingHTTPServer((VOXVEY_REDIRECT_HOST, VOXVEY_REDIRECT_PORT), Handler)
    redirect_uri = f"http://{VOXVEY_REDIRECT_HOST}:{server.server_port}{VOXVEY_REDIRECT_PATH}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, result, redirect_uri


def _wait_for_callback(server: ThreadingHTTPServer, thread: Thread, result: dict[str, str], timeout: float) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if result:
                return dict(result)
            time.sleep(0.1)
        raise VoxveyOAuthError("Timed out waiting for Voxvey redirect callback.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _exchange_code(code: str, *, redirect_uri: str, code_verifier: str, timeout: float) -> VoxveyOAuthTokens:
    payload = _post_form(
        VOXVEY_TOKEN_ENDPOINT,
        {
            "grant_type": "authorization_code",
            "client_id": VOXVEY_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=timeout,
    )
    return _tokens_from_payload(payload)


def _tokens_from_payload(payload: dict[str, Any]) -> VoxveyOAuthTokens:
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise VoxveyOAuthError("Voxvey token response did not include access_token.")
    expires_in = payload.get("expires_in")
    try:
        expires_in = int(expires_in) if expires_in is not None else None
    except Exception:
        expires_in = None
    return VoxveyOAuthTokens(
        access_token=access_token,
        refresh_token=str(payload.get("refresh_token") or "").strip(),
        id_token=str(payload.get("id_token") or "").strip(),
        token_type=str(payload.get("token_type") or "Bearer").strip() or "Bearer",
        expires_in=expires_in,
        scope=str(payload.get("scope") or VOXVEY_SCOPE).strip(),
    )


def login_with_pkce(
    *,
    open_browser: bool = True,
    manual_paste: bool = False,
    timeout: float = 180.0,
) -> VoxveyOAuthTokens:
    """Run browser PKCE login, optionally using manual redirect URL paste."""

    if manual_paste:
        redirect_uri = f"http://{VOXVEY_REDIRECT_HOST}:{VOXVEY_REDIRECT_PORT}{VOXVEY_REDIRECT_PATH}"
        server = thread = None
        callback_result: dict[str, str] = {}
    else:
        server, thread, callback_result, redirect_uri = _start_callback_server()

    verifier = _pkce_verifier()
    state = uuid.uuid4().hex
    authorize_url = _build_authorize_url(
        redirect_uri=redirect_uri,
        code_challenge=_pkce_challenge(verifier),
        state=state,
    )

    print("Open this URL to authorize Hermes with Voxvey:")
    print(authorize_url)
    if open_browser:
        try:
            if webbrowser.open(authorize_url):
                print("Browser opened for Voxvey authorization.")
        except Exception:
            pass

    if manual_paste:
        callback = _prompt_for_callback_url(redirect_uri)
    else:
        try:
            callback = _wait_for_callback(server, thread, callback_result, timeout)  # type: ignore[arg-type]
        except VoxveyOAuthError:
            print()
            print("Loopback callback timed out.")
            callback = _prompt_for_callback_url(redirect_uri)

    if callback.get("error"):
        raise VoxveyOAuthError(callback.get("error_description") or callback["error"])
    if callback.get("state") != state:
        raise VoxveyOAuthError("Voxvey OAuth state mismatch.")
    code = str(callback.get("code") or "").strip()
    if not code:
        raise VoxveyOAuthError("Voxvey redirect did not include an authorization code.")
    return _exchange_code(code, redirect_uri=redirect_uri, code_verifier=verifier, timeout=timeout)


def login_with_device_code(*, open_browser: bool = True, timeout: float = 600.0) -> VoxveyOAuthTokens:
    """Run Voxvey OAuth device-code login."""

    device = _post_form(
        VOXVEY_DEVICE_AUTHORIZATION_ENDPOINT,
        {"client_id": VOXVEY_CLIENT_ID, "scope": VOXVEY_SCOPE},
        timeout=30.0,
    )
    device_code = str(device.get("device_code") or "")
    user_code = str(device.get("user_code") or "")
    verification_uri = str(device.get("verification_uri_complete") or device.get("verification_uri") or "")
    expires_in = int(device.get("expires_in") or timeout)
    interval = max(1, int(device.get("interval") or 5))
    if not device_code or not verification_uri:
        raise VoxveyOAuthError("Voxvey device authorization response was missing required fields.")

    print("To continue Voxvey login:")
    print(f"  1. Open: {verification_uri}")
    if user_code:
        print(f"  2. Enter code: {user_code}")
    if open_browser:
        try:
            webbrowser.open(verification_uri)
        except Exception:
            pass

    deadline = time.monotonic() + min(timeout, expires_in)
    while time.monotonic() < deadline:
        try:
            payload = _post_form(
                VOXVEY_TOKEN_ENDPOINT,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": VOXVEY_CLIENT_ID,
                    "device_code": device_code,
                },
                timeout=30.0,
            )
            return _tokens_from_payload(payload)
        except Exception as exc:
            message = str(exc)
            if "authorization_pending" in message or "slow_down" in message:
                time.sleep(interval)
                continue
            raise
    raise VoxveyOAuthError("Timed out waiting for Voxvey device authorization.")


def refresh_tokens(refresh_token: str, *, timeout: float = 30.0) -> VoxveyOAuthTokens:
    payload = _post_form(
        VOXVEY_TOKEN_ENDPOINT,
        {
            "grant_type": "refresh_token",
            "client_id": VOXVEY_CLIENT_ID,
            "refresh_token": refresh_token,
        },
        timeout=timeout,
    )
    return _tokens_from_payload(payload)


def save_to_hermes_pool(tokens: VoxveyOAuthTokens, *, label: str | None = None, source: str = "manual:voxvey_oauth") -> Any:
    """Persist OAuth tokens in Hermes' credential pool, if Hermes is installed."""

    try:
        from agent.credential_pool import AUTH_TYPE_OAUTH, PooledCredential, load_pool
    except Exception as exc:
        raise VoxveyOAuthError(
            "Hermes credential pool is not importable. Run this inside Hermes Agent's Python environment."
        ) from exc

    pool = load_pool(VOXVEY_PROVIDER_ID)
    entry = PooledCredential(
        provider=VOXVEY_PROVIDER_ID,
        id=uuid.uuid4().hex[:6],
        label=label or "voxvey-oauth",
        auth_type=AUTH_TYPE_OAUTH,
        priority=0,
        source=source,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token or None,
        expires_at_ms=tokens.expires_at_ms,
        base_url=(os.getenv(VOXVEY_BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/") + "/v1",
        last_refresh=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        extra={
            "token_type": tokens.token_type,
            "scope": tokens.scope or VOXVEY_SCOPE,
            "client_id": VOXVEY_CLIENT_ID,
            "issuer": VOXVEY_ISSUER,
        },
    )
    pool.add_entry(entry)
    return entry


def run_login_cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Login to Voxvey for Hermes Agent.")
    parser.add_argument("--device", action="store_true", help="Use OAuth device-code login.")
    parser.add_argument("--manual-paste", action="store_true", help="Use browser PKCE and paste the redirect URL.")
    parser.add_argument("--no-browser", action="store_true", help="Print URLs without opening a browser.")
    parser.add_argument("--label", default="", help="Credential label to store in Hermes.")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    if args.device:
        tokens = login_with_device_code(open_browser=not args.no_browser, timeout=args.timeout)
        source = "manual:voxvey_device_code"
    else:
        tokens = login_with_pkce(
            open_browser=not args.no_browser,
            manual_paste=args.manual_paste,
            timeout=args.timeout,
        )
        source = "manual:voxvey_pkce"
    entry = save_to_hermes_pool(tokens, label=args.label or None, source=source)
    print(f'Saved Voxvey OAuth credentials: "{entry.label}"')
    return 0
