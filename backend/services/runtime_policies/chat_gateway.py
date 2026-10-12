"""Private chat gateway validation."""

from __future__ import annotations

from backend.config import Settings
from backend.services.chat_runtime_contract import (
    dedicated_gateway_hostname,
)


def _validate_chat_gateway_policy(settings: Settings) -> None:
    expected_gateway = {
        "staging": "chat-gateway-staging.paperswithcode.co",
        "production": "chat-gateway.paperswithcode.co",
    }[settings.environment]
    try:
        gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    except ValueError as error:
        raise RuntimeError(f"chat runtime is invalid: {error}") from error
    if gateway_host != expected_gateway:
        raise RuntimeError(f"chat gateway must use {expected_gateway}")
