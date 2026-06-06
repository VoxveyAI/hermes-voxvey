"""Small dependency-free Voxvey API client used by the plugin bundle."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.voxvey.com"


class VoxveyHTTPError(RuntimeError):
    """HTTP error with status and parsed response body."""

    def __init__(self, status: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.data = data


def get_voxvey_token() -> str | None:
    """Return the preferred Voxvey bearer token.

    Order:
      1. `VOXVEY_TOKEN`
      2. `VOXVEY_API_KEY`
      3. Hermes credential pool entry for provider `voxvey`
    """

    token = os.environ.get("VOXVEY_TOKEN") or os.environ.get("VOXVEY_API_KEY")
    if token:
        return token
    try:
        from agent.credential_pool import load_pool

        pool = load_pool("voxvey")
        entry = pool.peek() if pool and pool.has_credentials() else None
        if entry:
            pooled = getattr(entry, "access_token", "") or getattr(entry, "runtime_api_key", "")
            pooled = str(pooled).strip()
            if pooled:
                return pooled
    except Exception:
        pass
    return None


def get_base_url() -> str:
    return (os.environ.get("VOXVEY_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class VoxveyClient:
    """HTTP client for Voxvey's authenticated gateway."""

    def __init__(self, *, base_url: str | None = None, token: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.token = token if token is not None else get_voxvey_token()
        self.timeout = timeout

    def url(self, path: str, query: dict[str, Any] | None = None) -> str:
        normalized = "/" + path.lstrip("/")
        url = f"{self.base_url}{normalized}"
        if query:
            clean_query = {k: v for k, v in query.items() if v is not None}
            if clean_query:
                url = f"{url}?{urllib.parse.urlencode(clean_query, doseq=True)}"
        return url

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        text_body: str | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, Any]:
        body: bytes | None = None
        request_headers = dict(headers or {})
        if self.token:
            request_headers.setdefault("Authorization", f"Bearer {self.token}")
        if json_body is not None:
            body = json_dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif text_body is not None:
            body = text_body.encode("utf-8")
            request_headers.setdefault("Content-Type", "text/plain")

        req = urllib.request.Request(
            self.url(path, query),
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        return self._open(req, timeout=timeout)

    def multipart_request(
        self,
        method: str,
        path: str,
        *,
        fields: dict[str, Any] | None = None,
        files: dict[str, str | Path] | None = None,
        query: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, Any]:
        boundary = "voxvey-hermes-boundary"
        chunks: list[bytes] = []
        for key, value in (fields or {}).items():
            if value is None:
                continue
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for key, raw_path in (files or {}).items():
            file_path = Path(raw_path)
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    (
                        f'Content-Disposition: form-data; name="{key}"; '
                        f'filename="{file_path.name}"\r\n'
                    ).encode(),
                    f"Content-Type: {content_type}\r\n\r\n".encode(),
                    file_path.read_bytes(),
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode())

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            self.url(path, query),
            data=b"".join(chunks),
            headers=headers,
            method=method.upper(),
        )
        return self._open(req, timeout=timeout)

    def _open(self, req: urllib.request.Request, *, timeout: float | None = None) -> tuple[int, Any]:
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as response:
                raw = response.read()
                return response.status, self._decode(raw, response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            data = self._decode(raw, exc.headers.get("Content-Type", ""))
            message = data.get("error") if isinstance(data, dict) else str(data)
            raise VoxveyHTTPError(exc.code, str(message), data) from exc
        except urllib.error.URLError as exc:
            raise VoxveyHTTPError(0, str(exc.reason), None) from exc

    @staticmethod
    def _decode(raw: bytes, content_type: str) -> Any:
        if not raw:
            return None
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {
                "content_type": content_type or "application/octet-stream",
                "base64": base64.b64encode(raw).decode("ascii"),
            }
