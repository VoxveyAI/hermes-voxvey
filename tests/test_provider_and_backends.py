from __future__ import annotations

import importlib
import sys
from pathlib import Path

from conftest import install_image_stubs, install_provider_stubs, install_video_stubs, install_web_search_stubs


def fresh_import(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_model_provider_registers_profile_and_fetches_models(monkeypatch):
    registered = install_provider_stubs()
    module = fresh_import("voxvey.model_provider")

    assert registered
    profile = registered[0]
    assert profile.name == "voxvey"
    assert profile.aliases == ("vox", "voxvey-api")
    assert profile.base_url == "https://api.voxvey.com/v1"
    assert profile.api_mode == "codex_responses"

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def request(self, method, path, timeout=None):
            assert method == "GET"
            assert path == "/v1/models"
            assert self.kwargs["token"] == "secret"
            return 200, {"data": [{"id": "openai/gpt-4o-mini"}, {"id": "byte/seed"}]}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    assert profile.fetch_models(api_key="secret") == ["openai/gpt-4o-mini", "byte/seed"]


def test_image_backend_registers_and_handles_url(monkeypatch, tmp_path):
    install_image_stubs(tmp_path)
    module = fresh_import("voxvey.image_gen")

    providers = []
    module.register(type("Ctx", (), {"register_image_gen_provider": providers.append})())
    provider = providers[0]

    class FakeClient:
        def request(self, method, path, json_body):
            assert method == "POST"
            assert path == "/v1/images/generations"
            assert json_body["model"] == module.DEFAULT_IMAGE_MODEL
            assert json_body["prompt"] == "draw"
            return 200, {"data": [{"url": "https://cdn.example/image.png"}]}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    result = provider.generate("draw")
    assert result["ok"] is True
    assert result["image"] == "https://cdn.example/image.png"


def test_image_backend_handles_base64(monkeypatch, tmp_path):
    install_image_stubs(tmp_path)
    module = fresh_import("voxvey.image_gen")
    provider = module.VoxveyImageGenProvider()

    class FakeClient:
        def request(self, method, path, json_body):
            return 200, {"data": [{"b64_json": "abc123"}]}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    result = provider.generate("draw")
    assert result["ok"] is True
    assert Path(result["image"]).read_text() == "abc123"


def test_video_backend_creates_and_polls(monkeypatch):
    install_video_stubs()
    module = fresh_import("voxvey.video_gen")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    calls = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def request(self, method, path, json_body=None):
            calls.append((method, path, json_body))
            if method == "POST":
                return 200, {"id": "task-1"}
            return 200, {"status": "succeeded", "video_url": "https://cdn.example/video.mp4"}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    result = module.VoxveyVideoGenProvider().generate("animate", max_poll_attempts=1, poll_interval=0)
    assert result["ok"] is True
    assert result["video"] == "https://cdn.example/video.mp4"
    assert calls[0][1] == module.VIDEO_GENERATIONS_PATH
    assert calls[1][1] == f"{module.VIDEOS_PATH}/task-1"


def test_search_backend_registers_and_normalizes(monkeypatch):
    install_web_search_stubs()
    module = fresh_import("voxvey.search")
    providers = []
    module.register(type("Ctx", (), {"register_web_search_provider": providers.append})())
    provider = providers[0]

    class FakeClient:
        def request(self, method, path, json_body=None, timeout=None):
            assert method == "POST"
            assert path == "/v2/search"
            assert json_body == {"query": "voxvey", "limit": 2}
            return 200, {"success": True, "data": [{"title": "A", "url": "https://a.test", "description": "Snippet"}]}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    result = provider.search("voxvey", limit=2)
    assert result == {
        "success": True,
        "data": {"web": [{"title": "A", "url": "https://a.test", "description": "Snippet", "position": 1}]},
    }


def test_search_extract_calls_scrape(monkeypatch):
    install_web_search_stubs()
    module = fresh_import("voxvey.search")
    provider = module.VoxveySearchProvider()

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def request(self, method, path, json_body=None, timeout=None):
            assert path == "/v2/scrape"
            assert json_body["url"] == "https://example.com"
            return 200, {"data": {"markdown": "Body", "metadata": {"title": "Title", "sourceURL": "https://example.com"}}}

    monkeypatch.setattr(module, "VoxveyClient", FakeClient)
    assert provider.extract(["https://example.com"])[0]["content"] == "Body"
