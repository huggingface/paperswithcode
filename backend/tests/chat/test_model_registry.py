"""Chat model registry exposes stable ids, not provider routes."""

from __future__ import annotations

from backend.chat_configuration import registry
from backend.config import Settings


def test_model_registry_exposes_stable_ids_not_provider_routes():
    production = Settings(environment="production")
    assert [choice["id"] for choice in production.chat_model_choices] == [
        "zai-org/GLM-5.3-Flash",
    ]
    staging = Settings(
        environment="staging", chat_openrouter_server_funded_enabled=True
    )
    assert [choice["id"] for choice in staging.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
    ]
    assert production.chat_model_routes["zai-org/GLM-5.3-Flash"] == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    for legacy_id in (
        "google/gemma-4-31B-it",
        "zai-org/GLM-5.2",
        "moonshotai/Kimi-K3",
        "openai/gpt-oss-120b",
        "deepseek-ai/DeepSeek-V4-Flash",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-terra",
    ):
        assert (
            production.chat_model_routes[legacy_id]
            == production.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
        )
    assert production.chat_model_providers["zai-org/GLM-5.3-Flash"] == "huggingface"
    assert production.chat_effective_pi_prewarm_model == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    production_direct = Settings(
        environment="production", chat_openai_direct_enabled=True
    )
    assert [choice["id"] for choice in production_direct.chat_model_choices] == [
        "gpt-5.6-luna@openai",
    ]
    # Hidden GLM sessions continue on Luna; issued GLM capabilities resolve.
    assert (
        registry.canonical_model_id(production_direct, "zai-org/GLM-5.3-Flash")
        == "gpt-5.6-luna@openai"
    )
    assert (
        registry.canonical_model_id(production, "zai-org/GLM-5.3-Flash")
        == "zai-org/GLM-5.3-Flash"
    )
    glm_route = production_direct.chat_glm_5_3_flash_route
    assert production_direct.chat_route_providers[glm_route] == "huggingface"
    assert production_direct.chat_route_protocols[glm_route] == "anthropic-messages"
    assert production_direct.chat_route_funding_modes[glm_route] == "hf_user_billed"
    assert production_direct.chat_model_choices[0]["label"] == "GPT-6 Luna"
    assert production_direct.chat_model_providers["gpt-5.6-luna@openai"] == "openai"
    assert production_direct.chat_route_protocols["gpt-5.6-luna@openai"] == (
        "openai-responses"
    )
    assert production_direct.chat_effective_pi_prewarm_model == ("gpt-5.6-luna@openai")
    assert staging.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    )
    assert staging.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "huggingface"
    )
    assert staging.chat_model_routes["moonshotai/Kimi-K3"] == (
        "moonshotai/Kimi-K3:baseten"
    )
    assert staging.chat_model_providers["moonshotai/Kimi-K3"] == "huggingface"
    assert staging.chat_model_routes["gpt-5.6-luna@openrouter"] == "openai/gpt-5.6-luna"
    assert staging.chat_model_providers["gpt-5.6-luna@openrouter"] == "openrouter"
    assert staging.chat_model_routes["openai/gpt-5.6-luna"] == "openai/gpt-5.6-luna"
    assert staging.chat_model_providers["openai/gpt-5.6-luna"] == "openrouter"
    assert staging.chat_model_labels["openai/gpt-5.6-luna"] == (
        "GPT-5.6 Luna (Legacy OpenRouter)"
    )
    assert staging.chat_route_providers["openai/gpt-5.6-luna"] == "openrouter"
    assert "openai/gpt-5.6-luna" in staging.chat_openrouter_routes
    assert staging.chat_model_routes["openai/gpt-5.6-terra"] == (
        "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    )

    direct = Settings(environment="staging", chat_openai_direct_enabled=True)
    assert [choice["id"] for choice in direct.chat_model_choices] == [
        "gpt-5.6-luna@openai",
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
    ]
    assert direct.chat_model_choices[0]["label"] == "GPT-6 Luna (Direct)"
    assert direct.chat_model_routes["gpt-5.6-luna@openai"] == ("gpt-5.6-luna@openai")
    assert direct.chat_model_providers["gpt-5.6-luna@openai"] == "openai"
    assert direct.chat_route_providers["gpt-5.6-luna@openai"] == "openai"
    assert direct.chat_route_protocols["gpt-5.6-luna@openai"] == "openai-responses"
    assert direct.chat_route_provider_models["gpt-5.6-luna@openai"] == ("gpt-6-luna")
    assert direct.chat_route_funding_modes["gpt-5.6-luna@openai"] == "openai_funded"
    assert direct.chat_effective_pi_prewarm_model == "gpt-5.6-luna@openai"

    openrouter = Settings(
        environment="production",
        chat_deepseek_v4_flash_provider="openrouter",
    )
    assert openrouter.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "deepseek/deepseek-v4-flash-0731"
    )
    assert (
        openrouter.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"]
        == "openrouter"
    )
    assert openrouter.chat_effective_pi_prewarm_model == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    assert "deepseek/deepseek-v4-flash-0731" in openrouter.chat_openrouter_routes
    assert openrouter.chat_route_providers[production.chat_deepseek_v4_flash_route] == (
        "huggingface"
    )

    comparison = Settings(
        environment="staging",
        chat_openrouter_server_funded_enabled=True,
        chat_alternative_model_enabled=True,
        chat_alternative_model="google/gemini-3.7-flash",
    )
    assert [choice["id"] for choice in comparison.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
        "google/gemini-3.7-flash",
    ]
    assert comparison.chat_model_routes["google/gemini-3.7-flash"] == (
        "google/gemini-3.7-flash"
    )
    assert comparison.chat_model_providers["google/gemini-3.7-flash"] == "openrouter"


def test_hidden_glm_sessions_report_luna_to_the_frontend(monkeypatch):
    import uuid
    from datetime import UTC, datetime

    from backend.models.database import ChatSession
    from backend.routers import chat

    production_direct = Settings(
        environment="production", chat_openai_direct_enabled=True
    )
    monkeypatch.setattr(chat, "get_settings", lambda: production_direct)
    now = datetime.now(UTC)
    session = ChatSession(
        id=uuid.uuid4(),
        title="GLM chat",
        selected_model="zai-org/GLM-5.3-Flash",
        created_at=now,
        updated_at=now,
        message_count=2,
        web_search_enabled=True,
    )

    assert chat._summary(session).selected_model == "gpt-5.6-luna@openai"


def test_sponsored_deepseek_is_offered_next_to_luna_in_production_only():
    sponsored = Settings(
        environment="production",
        chat_openai_direct_enabled=True,
        chat_sponsored_deepseek_enabled=True,
    )
    assert sponsored.chat_model_choices == (
        {
            "id": "gpt-5.6-luna@openai",
            "label": "GPT-6 Luna",
            "route": "gpt-5.6-luna@openai",
            "provider": "openai",
            "provider_model": "gpt-6-luna",
            "protocol": "openai-responses",
            "funding_mode": "openai_funded",
        },
        {
            "id": "deepseek-ai/DeepSeek-V4.1-Flash-1017",
            "label": "DeepSeek V4.1 Flash (Free)",
            "route": "deepseek-ai/DeepSeek-V4.1-Flash-1017:novita",
            "provider": "huggingface",
            "provider_model": "deepseek-ai/DeepSeek-V4.1-Flash-1017:novita",
            "protocol": "anthropic-messages",
            "funding_mode": "hf_org_funded",
        },
    )
    # Luna stays the default and the prewarmed model.
    assert sponsored.chat_effective_pi_prewarm_model == "gpt-5.6-luna@openai"
    assert (
        registry.canonical_model_id(sponsored, registry.SPONSORED_DEEPSEEK_ID)
        == registry.SPONSORED_DEEPSEEK_ID
    )

    staging = Settings(
        environment="staging",
        chat_openai_direct_enabled=True,
        chat_sponsored_deepseek_enabled=True,
    )
    assert registry.SPONSORED_DEEPSEEK_ID not in {
        choice["id"] for choice in staging.chat_model_choices
    }


def test_switched_off_sponsored_sessions_continue_on_luna():
    switched_off = Settings(environment="production", chat_openai_direct_enabled=True)
    assert (
        registry.canonical_model_id(switched_off, registry.SPONSORED_DEEPSEEK_ID)
        == "gpt-5.6-luna@openai"
    )
    # Already-issued capabilities still bill the organization, never the user.
    route = switched_off.chat_sponsored_deepseek_route
    assert switched_off.chat_route_providers[route] == "huggingface"
    assert switched_off.chat_route_protocols[route] == "anthropic-messages"
    assert switched_off.chat_route_funding_modes[route] == "hf_org_funded"
