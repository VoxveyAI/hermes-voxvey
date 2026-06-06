from __future__ import annotations

import argparse

from conftest import install_credential_pool_stub
from voxvey.auth_cli import register_cli, voxvey_command
from voxvey.auth_plugin import register
from voxvey.client import get_voxvey_token
from voxvey.oauth import VoxveyOAuthTokens, save_to_hermes_pool
from voxvey.realtime import create_client_secret, websocket_url


def test_get_token_falls_back_to_credential_pool(monkeypatch):
    monkeypatch.delenv("VOXVEY_TOKEN", raising=False)
    monkeypatch.delenv("VOXVEY_API_KEY", raising=False)
    pools = install_credential_pool_stub()
    save_to_hermes_pool(VoxveyOAuthTokens(access_token="oauth-token"), label="oauth")

    assert get_voxvey_token() == "oauth-token"
    assert pools["voxvey"].peek().auth_type == "oauth"


def test_voxvey_auth_plugin_registers_cli_command():
    calls = []

    class Ctx:
        def register_cli_command(self, **kwargs):
            calls.append(kwargs)

    register(Ctx())
    assert calls[0]["name"] == "voxvey"
    assert calls[0]["handler_fn"] is voxvey_command


def test_cli_api_key_stores_pool_entry():
    pools = install_credential_pool_stub()
    parser = argparse.ArgumentParser()
    register_cli(parser)
    args = parser.parse_args(["api-key", "--api-key", "key-123", "--label", "manual"])

    assert voxvey_command(args) == 0
    entry = pools["voxvey"].peek()
    assert entry.access_token == "key-123"
    assert entry.auth_type == "api_key"
    assert entry.label == "manual"


def test_realtime_client_secret_helper(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def request(self, method, path, json_body=None, timeout=None):
            seen.update(method=method, path=path, json_body=json_body, timeout=timeout)
            return 200, {"value": "vxy-realtime-client-secret-test", "expires_at": 123, "model": "xai/grok-voice-latest"}

    monkeypatch.setattr("voxvey.realtime.VoxveyClient", FakeClient)
    secret = create_client_secret(session={"model": "xai/grok-voice-latest", "voice": "eve"}, expires_seconds=300)
    assert secret["value"] == "vxy-realtime-client-secret-test"
    assert seen["path"] == "/v1/realtime/client_secrets"
    assert seen["json_body"]["expires_after"] == {"seconds": 300}
    assert seen["json_body"]["session"]["voice"] == "eve"


def test_realtime_websocket_url(monkeypatch):
    monkeypatch.setenv("VOXVEY_BASE_URL", "https://api.voxvey.com")
    assert websocket_url() == "wss://api.voxvey.com/v1/realtime"
