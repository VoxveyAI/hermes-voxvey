"""Voxvey video generation backend for Hermes."""

from __future__ import annotations

import time
from typing import Any

from agent.video_gen_provider import VideoGenProvider, error_response, success_response
from plugins.voxvey_common.client import VoxveyClient, VoxveyHTTPError, get_voxvey_token


DEFAULT_VIDEO_MODEL = "byte/dreamina-seedance-2-0-260128"
TASKS_PATH = "/v1/byte/contents/generations/tasks"


def _task_id(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("id", "task_id"):
            if data.get(key):
                return str(data[key])
        nested = data.get("data")
        if isinstance(nested, dict):
            return _task_id(nested)
    return None


def _task_video(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("video", "video_url", "url", "output_url"):
            if data.get(key):
                return str(data[key])
        nested = data.get("data") or data.get("result") or data.get("output")
        if isinstance(nested, dict):
            return _task_video(nested)
        if isinstance(nested, list) and nested:
            return _task_video(nested[0])
    return None


def _task_status(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("status", "state"):
            if data.get(key):
                return str(data[key]).lower()
        nested = data.get("data")
        if isinstance(nested, dict):
            return _task_status(nested)
    return "unknown"


class VoxveyVideoGenProvider(VideoGenProvider):
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
                "id": DEFAULT_VIDEO_MODEL,
                "display": "BytePlus Seedance via Voxvey",
                "speed": "provider-dependent",
                "strengths": "Text-to-video and image-to-video task routing",
                "price": "See Voxvey console",
                "modalities": ["text", "image"],
            }
        ]

    def default_model(self) -> str:
        return DEFAULT_VIDEO_MODEL

    def capabilities(self) -> dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
            "resolutions": ["480p", "720p", "1080p"],
            "min_duration": 1,
            "max_duration": 30,
            "supports_audio": False,
            "supports_negative_prompt": True,
            "max_reference_images": 4,
        }

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Voxvey",
            "badge": "gateway",
            "tag": "Video generation through Voxvey BytePlus task routes",
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
        *,
        model: str | None = None,
        image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        duration: int | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        negative_prompt: str | None = None,
        audio: bool | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        model_id = model or self.default_model()
        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_input",
                provider=self.name,
                model=model_id,
                prompt=prompt,
            )

        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        optional = {
            "image_url": image_url,
            "reference_image_urls": reference_image_urls,
            "duration": duration,
            "negative_prompt": negative_prompt,
            "audio": audio,
            "seed": seed,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        for key, value in kwargs.items():
            if key not in {"wait", "max_poll_attempts", "poll_interval"} and value is not None:
                payload[key] = value

        try:
            client = VoxveyClient(timeout=float(kwargs.get("timeout", 120)))
            _status, created = client.request("POST", TASKS_PATH, json_body=payload)
            task_id = _task_id(created)
            if not task_id:
                return error_response(
                    error="Voxvey video response did not include a task id",
                    error_type="upstream_response",
                    provider=self.name,
                    model=model_id,
                    prompt=prompt,
                )

            if not kwargs.get("wait", True):
                return success_response(
                    video=None,
                    model=model_id,
                    prompt=prompt,
                    modality="image" if image_url else "text",
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                    provider=self.name,
                    task_id=task_id,
                    status="created",
                )

            attempts = int(kwargs.get("max_poll_attempts", 60))
            interval = float(kwargs.get("poll_interval", 2.0))
            last_data = created
            for _ in range(attempts):
                _poll_status, last_data = client.request("GET", f"{TASKS_PATH}/{task_id}")
                video = _task_video(last_data)
                status = _task_status(last_data)
                if video:
                    return success_response(
                        video=video,
                        model=model_id,
                        prompt=prompt,
                        modality="image" if image_url else "text",
                        aspect_ratio=aspect_ratio,
                        duration=duration,
                        provider=self.name,
                        task_id=task_id,
                        status=status,
                    )
                if status in {"failed", "failure", "cancelled", "canceled", "error"}:
                    return error_response(
                        error=last_data,
                        error_type="video_task_failed",
                        provider=self.name,
                        model=model_id,
                        prompt=prompt,
                        task_id=task_id,
                        status=status,
                    )
                time.sleep(interval)

            return success_response(
                video=None,
                model=model_id,
                prompt=prompt,
                modality="image" if image_url else "text",
                aspect_ratio=aspect_ratio,
                duration=duration,
                provider=self.name,
                task_id=task_id,
                status=_task_status(last_data),
            )
        except VoxveyHTTPError as exc:
            return error_response(
                error=str(exc),
                error_type="voxvey_http_error",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                status=exc.status,
            )
        except Exception as exc:
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=self.name,
                model=model_id,
                prompt=prompt,
            )


def register(ctx) -> None:
    ctx.register_video_gen_provider(VoxveyVideoGenProvider())
