"""Pure immutable-runtime and dedicated-gateway contract checks."""

from __future__ import annotations

from urllib.parse import urlsplit

GATEWAY_PATH = "/api/internal/chat-gateway"
PUBLIC_STAGING_HOST = "staging.paperswithcode.co"


def require_immutable_image_id(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("im-"):
        raise ValueError("chat runtime requires an immutable Modal image ID")
    return value


def dedicated_gateway_hostname(value: str) -> str:
    gateway = urlsplit(value)
    if (
        gateway.scheme != "https"
        or not gateway.hostname
        or gateway.hostname == PUBLIC_STAGING_HOST
        or gateway.path.rstrip("/") != GATEWAY_PATH
        or gateway.query
        or gateway.fragment
    ):
        raise ValueError("chat gateway must use its dedicated HTTPS origin and path")
    return gateway.hostname
