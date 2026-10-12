"""Typed chat model and provider registry.

Discovery exposes ``ChatModelRecord`` choices. Routes that are hidden from
discovery but still carried by persisted sessions or already-issued
capabilities remain resolvable through explicit compatibility tables, so a
rolling release never changes the provider behind an immutable route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from backend.config import Settings

ChatProvider = Literal["huggingface", "openrouter", "openai"]
ChatProtocol = Literal["anthropic-messages", "openai-responses"]
ChatFundingMode = Literal["hf_user_billed", "openrouter_funded", "openai_funded"]

DEEPSEEK_V4_FLASH_ID = "deepseek-ai/DeepSeek-V4-Flash-0731"

# Selected-model IDs persisted by sessions created before the DeepSeek-only
# registry. They resolve to the canonical route but never appear in discovery.
LEGACY_SELECTED_MODEL_IDS = (
    "google/gemma-4-31B-it",
    "zai-org/GLM-5.2",
    "moonshotai/Kimi-K3",
    "openai/gpt-oss-120b",
    "deepseek-ai/DeepSeek-V4-Flash",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-terra",
)

ALTERNATIVE_MODEL_LABELS = {
    "openai/gpt-5.6-luna": "GPT-5.6 Luna",
    "google/gemini-3.7-flash": "Gemini 3.7 Flash",
}


@dataclass(frozen=True, slots=True)
class ChatModelRecord:
    """One discoverable model choice and the provider route that serves it."""

    id: str
    label: str
    route: str
    provider: ChatProvider
    provider_model: str
    protocol: ChatProtocol
    funding_mode: ChatFundingMode

    def as_choice(self) -> dict[str, str]:
        """The public discovery shape consumed by the API and the worker."""

        return {
            "id": self.id,
            "label": self.label,
            "route": self.route,
            "provider": self.provider,
            "provider_model": self.provider_model,
            "protocol": self.protocol,
            "funding_mode": self.funding_mode,
        }


def _anthropic_route(
    model_id: str,
    label: str,
    route: str,
    provider: ChatProvider,
    funding_mode: ChatFundingMode,
) -> ChatModelRecord:
    return ChatModelRecord(
        id=model_id,
        label=label,
        route=route,
        provider=provider,
        provider_model=route,
        protocol="anthropic-messages",
        funding_mode=funding_mode,
    )


def _direct_luna(settings: Settings, label: str) -> ChatModelRecord:
    return ChatModelRecord(
        id="gpt-5.6-luna@openai",
        label=label,
        route=settings.chat_openai_luna_route,
        provider="openai",
        provider_model=settings.chat_openai_model,
        protocol="openai-responses",
        funding_mode="openai_funded",
    )


def deepseek_route(settings: Settings) -> str:
    if settings.chat_deepseek_v4_flash_provider == "huggingface":
        return settings.chat_deepseek_v4_flash_route
    return settings.chat_deepseek_v4_flash_openrouter_route


def chat_model_records(settings: Settings) -> tuple[ChatModelRecord, ...]:
    """Return the environment's discoverable models in default-first order."""

    environment = settings.environment
    deepseek_huggingface = settings.chat_deepseek_v4_flash_provider == "huggingface"
    deepseek = _anthropic_route(
        DEEPSEEK_V4_FLASH_ID,
        "DeepSeek V4 Flash",
        deepseek_route(settings),
        settings.chat_deepseek_v4_flash_provider,
        "hf_user_billed" if deepseek_huggingface else "openrouter_funded",
    )
    glm = _anthropic_route(
        "zai-org/GLM-5.3-Flash",
        "GLM-5.3-Flash",
        settings.chat_glm_5_3_flash_route,
        "huggingface",
        "hf_user_billed",
    )
    records: tuple[ChatModelRecord, ...] = (
        (glm,) if environment == "production" else (deepseek,)
    )
    if environment == "production" and settings.chat_openai_direct_enabled:
        records = (_direct_luna(settings, "GPT-5.6 Luna"), glm)
    if environment == "staging":
        staging_records = (
            _anthropic_route(
                "moonshotai/Kimi-K3",
                "Kimi K3",
                settings.chat_kimi_route,
                "huggingface",
                "hf_user_billed",
            ),
            _anthropic_route(
                "gpt-5.6-luna@openrouter",
                "GPT-5.6 Luna",
                settings.chat_luna_route,
                "openrouter",
                "openrouter_funded",
            ),
        )
        if settings.chat_openai_direct_enabled:
            # Staging paper qualification deliberately uses the direct Luna
            # route as the default.  The remaining choices stay available
            # for comparative ordinary-chat testing and existing sessions.
            records = (
                _direct_luna(settings, "GPT-5.6 Luna (Direct)"),
                *records,
                *staging_records,
            )
        else:
            records = records + staging_records
    if environment != "staging" or not settings.chat_alternative_model_enabled:
        return records
    alternative = settings.chat_alternative_model
    # The old comparison flag used the misleading historical Luna ID. Luna
    # now has an explicit OpenRouter choice, while the old ID remains hidden.
    if alternative == "openai/gpt-5.6-luna":
        return records
    if any(record.id == alternative for record in records):
        return records
    return records + (
        _anthropic_route(
            alternative,
            ALTERNATIVE_MODEL_LABELS[alternative],
            alternative,
            "openrouter",
            "openrouter_funded",
        ),
    )


def openrouter_routes(settings: Settings) -> tuple[str, ...]:
    routes = [
        record.route
        for record in chat_model_records(settings)
        if record.provider == "openrouter"
    ]
    if settings.chat_deepseek_v4_flash_openrouter_route not in routes:
        routes.append(settings.chat_deepseek_v4_flash_openrouter_route)
    return tuple(routes)


def discoverable_records(settings: Settings) -> tuple[ChatModelRecord, ...]:
    records = chat_model_records(settings)
    if not settings.is_deployed or settings.environment in {"production", "staging"}:
        return records
    return tuple(record for record in records if record.provider != "openrouter")


def model_routes(settings: Settings) -> dict[str, str]:
    routes = {record.id: record.route for record in discoverable_records(settings)}
    routes.setdefault(DEEPSEEK_V4_FLASH_ID, deepseek_route(settings))
    canonical_route = routes[DEEPSEEK_V4_FLASH_ID]
    # Existing sessions keep their persisted selected-model IDs but move to
    # the sole qualified route. These aliases are intentionally absent from
    # discovery and frontend defaults.
    for legacy_model in LEGACY_SELECTED_MODEL_IDS:
        routes.setdefault(legacy_model, canonical_route)
    if settings.environment == "staging":
        routes["openai/gpt-5.6-luna"] = settings.chat_luna_route
    return routes


def model_providers(settings: Settings) -> dict[str, str]:
    providers = {record.id: record.provider for record in chat_model_records(settings)}
    providers.setdefault(DEEPSEEK_V4_FLASH_ID, settings.chat_deepseek_v4_flash_provider)
    canonical_provider = providers[DEEPSEEK_V4_FLASH_ID]
    for legacy_model in LEGACY_SELECTED_MODEL_IDS:
        providers.setdefault(legacy_model, canonical_provider)
    if settings.environment == "staging":
        providers["openai/gpt-5.6-luna"] = "openrouter"
    return providers


def model_labels(settings: Settings) -> dict[str, str]:
    labels = {record.id: record.label for record in chat_model_records(settings)}
    labels.setdefault(DEEPSEEK_V4_FLASH_ID, "DeepSeek V4 Flash")
    if settings.environment == "staging":
        labels["openai/gpt-5.6-luna"] = "GPT-5.6 Luna (Legacy OpenRouter)"
    return labels


def _retired_routes(settings: Settings) -> tuple[str, ...]:
    """Routes from retired registries that persisted capabilities may carry."""

    return (
        settings.chat_glm_route,
        settings.chat_gemma_route,
        settings.chat_deepseek_v4_flash_route,
        settings.chat_deepseek_v4_flash_openrouter_route,
    )


def route_protocols(settings: Settings) -> dict[str, str]:
    protocols = {
        record.route: record.protocol for record in chat_model_records(settings)
    }
    for route in _retired_routes(settings):
        protocols.setdefault(route, "anthropic-messages")
    return protocols


def route_provider_models(settings: Settings) -> dict[str, str]:
    models = {
        record.route: record.provider_model for record in chat_model_records(settings)
    }
    for route in _retired_routes(settings):
        models.setdefault(route, route)
    return models


def route_funding_modes(settings: Settings) -> dict[str, str]:
    modes = {
        record.route: record.funding_mode for record in chat_model_records(settings)
    }
    modes.setdefault(settings.chat_glm_route, "openrouter_funded")
    modes.setdefault(settings.chat_gemma_route, "openrouter_funded")
    modes.setdefault(settings.chat_deepseek_v4_flash_route, "hf_user_billed")
    modes.setdefault(
        settings.chat_deepseek_v4_flash_openrouter_route, "openrouter_funded"
    )
    return modes


def route_providers(settings: Settings) -> dict[str, str]:
    providers = {
        record.route: record.provider for record in chat_model_records(settings)
    }
    # Both routes remain valid across a rolling provider switch. New turns use
    # chat_deepseek_v4_flash_provider while already-issued capabilities keep
    # their immutable route.
    providers.setdefault(settings.chat_deepseek_v4_flash_route, "huggingface")
    providers.setdefault(settings.chat_deepseek_v4_flash_openrouter_route, "openrouter")
    # Persisted capabilities from the retired comparison registry may still
    # carry these immutable routes even though they are hidden from discovery.
    providers.setdefault(settings.chat_glm_route, "openrouter")
    providers.setdefault(settings.chat_gemma_route, "openrouter")
    providers.setdefault(settings.chat_kimi_route, "huggingface")
    providers.setdefault(settings.chat_luna_route, "openrouter")
    return providers


def effective_pi_prewarm_model(settings: Settings) -> str:
    if settings.chat_pi_prewarm_model:
        return settings.chat_pi_prewarm_model
    if (
        settings.environment in {"production", "staging"}
        and settings.chat_openai_direct_enabled
    ):
        return settings.chat_openai_luna_route
    if settings.chat_alternative_model_enabled:
        return settings.chat_alternative_model
    return discoverable_records(settings)[0].route
