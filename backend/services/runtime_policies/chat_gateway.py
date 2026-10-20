"""Private chat gateway validation."""

from __future__ import annotations

from urllib.parse import urlsplit

from backend.config import Settings
from backend.services.chat_runtime_contract import (
    dedicated_gateway_hostname,
)


def _validate_chat_gateway_policy(settings: Settings) -> None:
    try:
        gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    except ValueError as error:
        raise RuntimeError(f"chat runtime is invalid: {error}") from error
    if gateway_host == urlsplit(settings.auth_authority_origin).hostname:
        raise RuntimeError("chat gateway must not share the public site origin")
