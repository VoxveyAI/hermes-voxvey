"""Voxvey image generation backend for Hermes."""

from __future__ import annotations

from typing import Any

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)
from voxvey.client import VoxveyClient, VoxveyHTTPError, get_voxvey_token


DEFAULT_IMAGE_MODEL = "byte/seedream-5-0-260128"


def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    return {
        "1:1": "1024x1024",
        "16:9": "1792x1024",
        "9:16": "1024x1792",
        "4:3": "1536x1152",
        "3:4": "1152x1536",
    }.get(aspect_ratio, "1024x1024")


def _first_image(data: Any) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, None
    images = data.get("data")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("url"), first.get("b64_json") or first.get("image_b64")
    return data.get("url") or data.get("image_url"), data.get("b64_json") or data.get("image_b64")


class VoxveyImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "voxvey"

    @property
    def display_name(self) -> str:
        return "Voxvey"

    def is_available(self) -> bool:
        return bool(get_voxvey_token())

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "openai/gpt-image-1",
                "display": "OpenAI GPT Image via Voxvey",
                "speed": "provider-dependent",
                "strengths": "OpenAI native image generation through Voxvey",
                "price": "See Voxvey console",
            },
            {
                "id": "xai/grok-imagine-image",
                "display": "xAI Grok Imagine via Voxvey",
                "speed": "provider-dependent",
                "strengths": "xAI native image generation through Voxvey",
                "price": "See Voxvey console",
            },
            {
                "id": DEFAULT_IMAGE_MODEL,
                "display": "BytePlus Seedream via Voxvey",
                "speed": "provider-dependent",
                "strengths": "OpenAI-compatible image generation through Voxvey",
                "price": "See Voxvey console",
            },
            {
                "id": "gemini/gemini-2.5-flash-image",
                "display": "Gemini Flash Image via Voxvey",
                "speed": "provider-dependent",
                "strengths": "Gemini native image generation through Voxvey",
                "price": "See Voxvey console",
            }
        ]

    def default_model(self) -> str:
        return DEFAULT_IMAGE_MODEL

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Voxvey",
            "badge": "gateway",
            "tag": "Image generation through Voxvey's authenticated gateway",
            "env_vars": [
                {
                    "key": "VOXVEY_TOKEN",
                    "prompt": "Voxvey bearer token",
                    "url": "https://developers.voxvey.com/",
                }
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect_ratio = resolve_aspect_ratio(aspect_ratio)
        model = kwargs.get("model") or self.default_model()
        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_input",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )

        payload = {
            "model": model,
            "prompt": prompt,
            "size": kwargs.get("size") or ("2K" if str(model).startswith("byte/") else _size_for_aspect_ratio(aspect_ratio)),
            "response_format": kwargs.get("response_format", "url"),
        }
        if "watermark" in kwargs:
            payload["watermark"] = kwargs["watermark"]
        for key, value in kwargs.items():
            if key not in {"model", "size", "response_format", "watermark"} and value is not None:
                payload[key] = value

        try:
            _status, data = VoxveyClient().request("POST", "/v1/images/generations", json_body=payload)
            image_url, image_b64 = _first_image(data)
            image = image_url
            if image_b64:
                image = str(save_b64_image(image_b64, prefix=self.name, extension="png"))
            if not image:
                return error_response(
                    error="Voxvey image response did not include an image URL or base64 payload",
                    error_type="upstream_response",
                    provider=self.name,
                    model=model,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )
            return success_response(
                image=image,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                provider=self.name,
            )
        except VoxveyHTTPError as exc:
            return error_response(
                error=str(exc),
                error_type="voxvey_http_error",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                status=exc.status,
            )
        except Exception as exc:
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )


def register(ctx) -> None:
    ctx.register_image_gen_provider(VoxveyImageGenProvider())
