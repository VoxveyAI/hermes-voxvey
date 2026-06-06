from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def import_from_path(name: str, path: str | Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def install_provider_stubs():
    providers = types.ModuleType("providers")
    providers_base = types.ModuleType("providers.base")
    registered = []

    class ProviderProfile:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def register_provider(profile):
        registered.append(profile)

    providers.register_provider = register_provider
    providers_base.ProviderProfile = ProviderProfile
    sys.modules["providers"] = providers
    sys.modules["providers.base"] = providers_base
    return registered


def install_image_stubs(tmp_path):
    agent = types.ModuleType("agent")
    image_mod = types.ModuleType("agent.image_gen_provider")

    class ImageGenProvider:
        pass

    def error_response(**kwargs):
        return {"ok": False, **kwargs}

    def success_response(**kwargs):
        return {"ok": True, **kwargs}

    def save_b64_image(image_b64, prefix, extension):
        path = tmp_path / f"{prefix}.{extension}"
        path.write_text(image_b64)
        return path

    image_mod.DEFAULT_ASPECT_RATIO = "1:1"
    image_mod.ImageGenProvider = ImageGenProvider
    image_mod.error_response = error_response
    image_mod.success_response = success_response
    image_mod.resolve_aspect_ratio = lambda value: value or "1:1"
    image_mod.save_b64_image = save_b64_image
    sys.modules["agent"] = agent
    sys.modules["agent.image_gen_provider"] = image_mod


def install_video_stubs():
    agent = types.ModuleType("agent")
    video_mod = types.ModuleType("agent.video_gen_provider")

    class VideoGenProvider:
        pass

    def error_response(**kwargs):
        return {"ok": False, **kwargs}

    def success_response(**kwargs):
        return {"ok": True, **kwargs}

    video_mod.VideoGenProvider = VideoGenProvider
    video_mod.error_response = error_response
    video_mod.success_response = success_response
    sys.modules["agent"] = agent
    sys.modules["agent.video_gen_provider"] = video_mod


def install_web_search_stubs():
    agent = sys.modules.get("agent") or types.ModuleType("agent")
    web_mod = types.ModuleType("agent.web_search_provider")

    class WebSearchProvider:
        pass

    web_mod.WebSearchProvider = WebSearchProvider
    sys.modules["agent"] = agent
    sys.modules["agent.web_search_provider"] = web_mod


def install_credential_pool_stub():
    agent = sys.modules.get("agent") or types.ModuleType("agent")
    pool_mod = types.ModuleType("agent.credential_pool")
    pools = {}

    @dataclass
    class PooledCredential:
        provider: str
        id: str
        label: str
        auth_type: str
        priority: int
        source: str
        access_token: str
        refresh_token: str | None = None
        base_url: str | None = None
        expires_at_ms: int | None = None
        last_refresh: str | None = None
        extra: dict | None = None

    class Pool:
        def __init__(self, provider):
            self.provider = provider
            self.items = []

        def add_entry(self, entry):
            self.items.append(entry)

        def has_credentials(self):
            return bool(self.items)

        def peek(self):
            return self.items[0] if self.items else None

    def load_pool(provider):
        return pools.setdefault(provider, Pool(provider))

    pool_mod.AUTH_TYPE_API_KEY = "api_key"
    pool_mod.AUTH_TYPE_OAUTH = "oauth"
    pool_mod.PooledCredential = PooledCredential
    pool_mod.load_pool = load_pool
    sys.modules["agent"] = agent
    sys.modules["agent.credential_pool"] = pool_mod
    return pools
