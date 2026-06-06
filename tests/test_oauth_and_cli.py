from __future__ import annotations

import argparse

from conftest import install_credential_pool_stub
from plugins.voxvey_auth import register
from plugins.voxvey_auth.cli import register_cli, voxvey_command
from plugins.voxvey_common.client import get_voxvey_token
from plugins.voxvey_common.oauth import VoxveyOAuthTokens, save_to_hermes_pool


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

