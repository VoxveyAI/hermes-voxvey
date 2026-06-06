"""Helpers for Voxvey realtime sessions."""

from __future__ import annotations

from typing import Any

from voxvey.client import VoxveyClient, get_base_url


DEFAULT_REALTIME_MODEL = "xai/grok-voice-latest"


def create_client_secret(
    *,
    model: str = DEFAULT_REALTIME_MODEL,
    session: dict[str, Any] | None = None,
    expires_seconds: int = 600,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "expires_after": {"seconds": max(1, min(int(expires_seconds), 3600))},
    }
    if session:
        payload["session"] = {**session, "model": session.get("model") or model}
    else:
        payload["model"] = model
    _status, data = VoxveyClient(timeout=timeout).request(
        "POST",
        "/v1/realtime/client_secrets",
        json_body=payload,
        timeout=timeout,
    )
    return data if isinstance(data, dict) else {"data": data}


def websocket_url() -> str:
    base = get_base_url()
    if base.startswith("https://"):
        return "wss://" + base.removeprefix("https://").rstrip("/") + "/v1/realtime"
    if base.startswith("http://"):
        return "ws://" + base.removeprefix("http://").rstrip("/") + "/v1/realtime"
    return base.rstrip("/") + "/v1/realtime"

