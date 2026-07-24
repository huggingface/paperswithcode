"""Credential-ready anonymous HTTP transport for the public catalog API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from pwc_cli import __version__

DEFAULT_API_URL = "https://paperswithcode.co/api/v1"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class TransportError(RuntimeError):
    pass


class ResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResponseError("API returned invalid JSON") from error


class Client:
    def __init__(self, base_url: str | None = None, credential: str | None = None):
        configured = base_url or os.environ.get("PWC_API_URL") or DEFAULT_API_URL
        self.base_url = configured.rstrip("/")
        self.credential = credential

    def get(
        self, path: str, params: dict[str, object | None] | None = None
    ) -> Response:
        query = urllib.parse.urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in (params or {}).items()
                if value is not None
            }
        )
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url += f"?{query}"
        headers = {
            "Accept": "application/json, text/plain;q=0.9",
            "User-Agent": f"pwc-cli/{__version__}",
        }
        if self.credential:
            headers["Authorization"] = f"Bearer {self.credential}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_RESPONSE_BYTES:
                    raise ResponseError("API response exceeded the client byte limit")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ResponseError("API response exceeded the client byte limit")
                return Response(
                    body,
                    {key.lower(): value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as error:
            detail = error.read(4096).decode("utf-8", errors="replace")
            raise TransportError(
                f"API request failed ({error.code}): {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise TransportError(f"API request failed: {error.reason}") from error
