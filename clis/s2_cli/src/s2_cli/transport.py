"""Authenticated HTTP transport for the Semantic Scholar Graph API."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from s2_cli import __version__

DEFAULT_API_URL = "https://api.semanticscholar.org/graph/v1"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_REQUEST_DELAY = 1.5
DEFAULT_MAX_RETRIES = 5
TIMEOUT_SECONDS = 30


class MissingKeyError(RuntimeError):
    pass


class TransportError(RuntimeError):
    pass


class ResponseError(RuntimeError):
    pass


class NotFoundError(ResponseError):
    pass


def read_api_key() -> str:
    key = os.environ.get("PWC_SEMANTIC_SCHOLAR_API_KEY") or os.environ.get("S2_API_KEY")
    if not key or not key.strip():
        raise MissingKeyError(
            "missing API key; set PWC_SEMANTIC_SCHOLAR_API_KEY or S2_API_KEY"
        )
    return key.strip()


@dataclass(frozen=True)
class Response:
    body: bytes
    headers: dict[str, str]
    status: int = 200

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResponseError("API returned invalid JSON") from error


@dataclass
class Client:
    api_key: str | None = None
    base_url: str | None = None
    delay: float | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    _last_request_at: float | None = field(default=None, init=False, repr=False)
    _sleep: Any = field(default=time.sleep, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = read_api_key()
        if self.delay is None:
            configured = os.environ.get("S2_REQUEST_DELAY")
            self.delay = (
                float(configured) if configured is not None else DEFAULT_REQUEST_DELAY
            )
        self.base_url = (
            self.base_url or os.environ.get("S2_API_URL") or DEFAULT_API_URL
        ).rstrip("/")

    def get(
        self, path: str, params: dict[str, object | None] | None = None
    ) -> Response:
        query = urllib.parse.urlencode(
            {
                key: value
                for key, value in (params or {}).items()
                if value is not None and value != ""
            }
        )
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url += f"?{query}"
        headers = {
            "Accept": "application/json",
            "User-Agent": f"s2-cli/{__version__}",
            "x-api-key": self.api_key or "",
        }
        request = urllib.request.Request(url, headers=headers)
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS
                ) as response:
                    body = _read_bounded(response)
                    self._last_request_at = time.monotonic()
                    return Response(
                        body,
                        {key.lower(): value for key, value in response.headers.items()},
                        getattr(response, "status", 200),
                    )
            except urllib.error.HTTPError as error:
                self._last_request_at = time.monotonic()
                detail = error.read(4096).decode("utf-8", errors="replace")
                if error.code == 404:
                    raise NotFoundError(_http_message(error.code, detail)) from error
                if error.code == 429:
                    last_error = TransportError(_http_message(error.code, detail))
                    if attempt + 1 >= self.max_retries:
                        break
                    wait = _retry_after_seconds(error, self.delay or 0)
                    self._sleep(wait)
                    continue
                if 500 <= error.code < 600:
                    last_error = TransportError(_http_message(error.code, detail))
                    if attempt + 1 >= self.max_retries:
                        break
                    self._sleep(self.delay or 0)
                    continue
                raise ResponseError(_http_message(error.code, detail)) from error
            except urllib.error.URLError as error:
                self._last_request_at = time.monotonic()
                raise TransportError(f"API request failed: {error.reason}") from error
        raise last_error or TransportError("API request failed")

    def _throttle(self) -> None:
        delay = self.delay or 0
        if delay <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = delay - elapsed
        if remaining > 0:
            self._sleep(remaining)


def _read_bounded(response: Any) -> bytes:
    length = response.headers.get("Content-Length")
    if length and int(length) > MAX_RESPONSE_BYTES:
        raise ResponseError("API response exceeded the client byte limit")
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ResponseError("API response exceeded the client byte limit")
    return body


def _http_message(status: int, detail: str) -> str:
    text = " ".join(detail.split())
    if text:
        return f"API request failed ({status}): {text}"
    return f"API request failed ({status})"


def _retry_after_seconds(error: urllib.error.HTTPError, fallback: float) -> float:
    raw = error.headers.get("Retry-After") if error.headers else None
    if raw is None:
        return max(fallback, 0)
    try:
        return max(float(raw), 0)
    except ValueError:
        return max(fallback, 0)
