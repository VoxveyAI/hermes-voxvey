"""Voxvey model provider profile for Hermes."""

from __future__ import annotations

from typing import Any

from plugins.voxvey_common.client import DEFAULT_BASE_URL, VoxveyClient, get_base_url, get_voxvey_token
from providers import register_provider
from providers.base import ProviderProfile


FALLBACK_MODELS = (
    "deepseek/deepseek-v4-flash",
    "openai/gpt-4o-mini",
    "byte/seed-2-0-lite-260428",
)


class VoxveyProviderProfile(ProviderProfile):
    def fetch_models(self, *, api_key: str | None = None, timeout: float = 8.0) -> list[str] | None:
        token = api_key or get_voxvey_token()
        if not token:
            return list(FALLBACK_MODELS)
        client = VoxveyClient(base_url=get_base_url(), token=token, timeout=timeout)
        _status, data = client.request("GET", "/v1/models", timeout=timeout)
        if isinstance(data, dict):
            models = data.get("data", data.get("models", []))
            parsed = []
            for item in models:
                if isinstance(item, str):
                    parsed.append(item)
                elif isinstance(item, dict) and item.get("id"):
                    parsed.append(str(item["id"]))
            return parsed or list(FALLBACK_MODELS)
        return list(FALLBACK_MODELS)


register_provider(
    VoxveyProviderProfile(
        name="voxvey",
        aliases=("vox", "voxvey-api"),
        display_name="Voxvey",
        description="Voxvey sovereign OpenAI-compatible provider gateway.",
        signup_url="https://developers.voxvey.com/",
        env_vars=("VOXVEY_TOKEN", "VOXVEY_API_KEY", "VOXVEY_BASE_URL"),
        base_url=f"{DEFAULT_BASE_URL}/v1",
        models_url=f"{DEFAULT_BASE_URL}/v1/models",
        auth_type="api_key",
        api_mode="chat_completions",
        default_aux_model="deepseek/deepseek-v4-flash",
        fallback_models=FALLBACK_MODELS,
    )
)

