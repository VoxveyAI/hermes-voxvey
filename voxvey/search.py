"""Voxvey Search provider for Hermes web tools."""

from __future__ import annotations

from typing import Any

from agent.web_search_provider import WebSearchProvider

from voxvey.client import VoxveyClient, VoxveyHTTPError, get_voxvey_token


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
        except Exception:
            pass
    return value


def _result_list(value: Any) -> list[dict[str, Any]]:
    value = _plain(value)
    if not isinstance(value, list):
        return []
    return [item for item in (_plain(item) for item in value) if isinstance(item, dict)]


def _search_results(data: Any) -> list[dict[str, Any]]:
    data = _plain(data)
    if not isinstance(data, dict):
        return []
    nested = data.get("data")
    if isinstance(nested, list):
        return _result_list(nested)
    if isinstance(nested, dict):
        for key in ("web", "results", "organic"):
            values = _result_list(nested.get(key))
            if values:
                return values
    for key in ("web", "results", "organic"):
        values = _result_list(data.get(key))
        if values:
            return values
    return []


def _normalize_web_item(item: dict[str, Any], position: int) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or item.get("name") or item.get("url") or ""),
        "url": str(item.get("url") or item.get("link") or ""),
        "description": str(item.get("description") or item.get("snippet") or item.get("content") or ""),
        "position": int(item.get("position") or position),
    }


def _scrape_payload(data: Any) -> dict[str, Any]:
    data = _plain(data)
    if not isinstance(data, dict):
        return {}
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


class VoxveySearchProvider(WebSearchProvider):
    @property
    def name(self) -> str:
        return "voxvey"

    @property
    def display_name(self) -> str:
        return "Voxvey Search"

    def is_available(self) -> bool:
        return bool(get_voxvey_token())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        try:
            _status, data = VoxveyClient().request(
                "POST",
                "/v2/search",
                json_body={"query": query, "limit": max(1, min(int(limit), 20))},
            )
            web = [_normalize_web_item(item, idx + 1) for idx, item in enumerate(_search_results(data))]
            return {"success": True, "data": {"web": web}}
        except VoxveyHTTPError as exc:
            return {"success": False, "error": str(exc.data or exc)}
        except Exception as exc:
            return {"success": False, "error": f"Voxvey search failed: {exc}"}

    def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        formats = kwargs.get("formats")
        if formats is None:
            requested_format = kwargs.get("format")
            formats = [requested_format] if requested_format in {"markdown", "html"} else ["markdown", "html"]

        for url in urls:
            try:
                _status, data = VoxveyClient(timeout=60).request(
                    "POST",
                    "/v2/scrape",
                    json_body={"url": url, "formats": formats},
                    timeout=60,
                )
                payload = _scrape_payload(data)
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                content = payload.get("markdown") or payload.get("html") or payload.get("content") or ""
                results.append(
                    {
                        "url": str(metadata.get("sourceURL") or payload.get("url") or url),
                        "title": str(metadata.get("title") or payload.get("title") or ""),
                        "content": str(content),
                        "raw_content": str(content),
                        "metadata": metadata,
                    }
                )
            except Exception as exc:
                results.append({"url": url, "title": "", "content": "", "raw_content": "", "error": str(exc)})
        return results

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Voxvey Search",
            "badge": "gateway",
            "tag": "Firecrawl-compatible search and extraction through Voxvey.",
            "env_vars": [
                {
                    "key": "VOXVEY_TOKEN",
                    "prompt": "Voxvey bearer token",
                    "url": "https://developers.voxvey.com/",
                }
            ],
        }


def register(ctx) -> None:
    ctx.register_web_search_provider(VoxveySearchProvider())

