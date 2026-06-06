from __future__ import annotations

import json
import urllib.error

import pytest

from plugins.voxvey_common.client import VoxveyClient, VoxveyHTTPError, get_voxvey_token


def test_token_prefers_voxvey_token(monkeypatch):
    monkeypatch.setenv("VOXVEY_TOKEN", "tok")
    monkeypatch.setenv("VOXVEY_API_KEY", "key")
    assert get_voxvey_token() == "tok"


def test_request_sends_bearer_and_parses_json(monkeypatch):
    seen = {}

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":[{"id":"openai/gpt-4o-mini"}]}'

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = req.data
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    status, data = VoxveyClient(base_url="https://api.voxvey.com", token="secret").request(
        "POST",
        "/v1/test",
        json_body={"hello": "world"},
    )

    assert status == 200
    assert data["data"][0]["id"] == "openai/gpt-4o-mini"
    assert seen["auth"] == "Bearer secret"
    assert json.loads(seen["body"]) == {"hello": "world"}


def test_request_raises_structured_http_error(monkeypatch):
    err = urllib.error.HTTPError(
        "https://api.voxvey.com/v1/models",
        402,
        "Payment Required",
        {"Content-Type": "application/json"},
        None,
    )
    err.read = lambda: b'{"error":"insufficient credits"}'
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(err))

    with pytest.raises(VoxveyHTTPError) as caught:
        VoxveyClient(token="secret").request("GET", "/v1/models")
    assert caught.value.status == 402
    assert caught.value.data == {"error": "insufficient credits"}
