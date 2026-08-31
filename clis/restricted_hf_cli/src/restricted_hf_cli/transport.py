"""Fixed loopback transport for the restricted worker CLI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 300 * 1024
DEFAULT_URL = "http://127.0.0.1:8765/hf/v1/query"


class TransportError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _endpoint() -> str:
    value = os.environ.get("PWC_HF_API_URL", DEFAULT_URL)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise TransportError("hf_unavailable: restricted gateway is invalid")
    return value


def query(operation: str, arguments: dict) -> dict:
    body = json.dumps(
        {"operation": operation, "arguments": arguments},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    request = urllib.request.Request(
        _endpoint(),
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise TransportError("hf_unavailable: gateway response is too large")
            if content_type != "application/json":
                raise TransportError("hf_unavailable: gateway returned invalid content")
    except urllib.error.HTTPError as error:
        raw = error.read(4096)
        try:
            detail = json.loads(raw).get("detail")
            if isinstance(detail, dict):
                code = str(detail.get("code", "hf_unavailable"))
                message = str(detail.get("message", "request failed"))
            else:
                code = {
                    403: "hf_access_denied",
                    404: "hf_not_found",
                    422: "hf_invalid_request",
                    429: "hf_limit_reached",
                }.get(error.code, "hf_unavailable")
                message = str(detail or "request failed")
        except (ValueError, AttributeError):
            code, message = "hf_unavailable", "request failed"
        raise TransportError(f"{code}: {message}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TransportError(
            "hf_unavailable: restricted gateway is unavailable"
        ) from None
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TransportError(
            "hf_unavailable: gateway returned malformed JSON"
        ) from None
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise TransportError("hf_unavailable: gateway contract mismatch")
    return payload
