"""Chat inference provider, discovery, scope-guardrail, and OpenRouter validation."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from backend.chat_sandbox_worker.contract import (
    PROVIDER_OUTPUT_TOKEN_LIMIT,
)
from backend.config import Settings
from backend.services.runtime_policies.chat_gateway import (
    _validate_chat_gateway_policy,
)


def validate_chat_scope_guardrail_configuration(settings: Settings) -> None:
    if not settings.chat_scope_guardrail_enabled:
        return
    if settings.chat_scope_guardrail_glm_model != "zai-org/GLM-5.3-Flash:baseten":
        raise RuntimeError("scope guardrail GLM must pin the Baseten provider")
    if settings.chat_scope_guardrail_openai_model != "gpt-6-luna":
        raise RuntimeError("scope guardrail fallback must use direct Luna")
    if settings.chat_scope_guardrail_max_context_chars != 8_000:
        raise RuntimeError("scope guardrail context must preserve a full API message")
    if not all(
        (
            settings.chat_scope_guardrail_hf_token,
            settings.chat_scope_guardrail_hf_bill_to,
            settings.chat_scope_guardrail_openai_api_key,
        )
    ):
        raise RuntimeError("scope guardrail requires dedicated server credentials")
    if settings.chat_scope_guardrail_hf_token == settings.hf_token:
        raise RuntimeError("scope guardrail must not reuse the main HF credential")
    private_paper_mode = (
        settings.chat_latex_paper_enabled
        or settings.chat_latex_compiler_jobs_enabled
        or settings.chat_latex_compiler_qualification_mode
    )
    if settings.environment == "staging" and (
        not settings.chat_artifacts_enabled
        or (
            not private_paper_mode and not settings.chat_artifact_shared_preview_enabled
        )
        or settings.chat_artifact_storage_backend != "hf_bucket"
        or not settings.chat_artifact_hf_bucket_id
    ):
        raise RuntimeError("scope guardrail must preserve staging research artifacts")
    if settings.chat_posterly_enabled:
        raise RuntimeError("Posterly must remain disabled with scope enforcement")


def validate_chat_provider_policy(
    settings: Settings,
    *,
    include_openrouter: bool = True,
) -> None:
    """Validate inference credentials, discovery, gateway, search, and OpenRouter."""

    validate_chat_scope_guardrail_configuration(settings)

    if not all(
        (
            settings.hf_oauth_client_id,
            settings.hf_oauth_client_secret,
            settings.hf_oauth_credential_secret,
        )
    ):
        raise RuntimeError(
            "enabled chat requires the Hugging Face OAuth authentication path"
        )
    discovered = settings.chat_model_choices
    expected_huggingface_route = "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    expected_openrouter_route = "deepseek/deepseek-v4-flash-0731"
    if settings.chat_deepseek_v4_flash_route != expected_huggingface_route:
        raise RuntimeError("DeepSeek V4 Flash must use the reviewed Hugging Face route")
    if settings.chat_deepseek_v4_flash_openrouter_route != expected_openrouter_route:
        raise RuntimeError("DeepSeek V4 Flash must use the reviewed OpenRouter route")
    expected_provider = settings.chat_deepseek_v4_flash_provider
    if settings.environment == "production":
        expected_glm_route = "zai-org/GLM-5.3-Flash:fastest"
        if settings.chat_glm_5_3_flash_route != expected_glm_route:
            raise RuntimeError("GLM-5.3-Flash must use Hugging Face fastest routing")
        expected_discovery = (
            {
                "id": "zai-org/GLM-5.3-Flash",
                "label": "GLM-5.3-Flash",
                "route": expected_glm_route,
                "provider": "huggingface",
            },
        )
    else:
        expected_discovery = (
            {
                "id": "deepseek-ai/DeepSeek-V4-Flash-0731",
                "label": "DeepSeek V4 Flash",
                "route": (
                    expected_huggingface_route
                    if expected_provider == "huggingface"
                    else expected_openrouter_route
                ),
                "provider": expected_provider,
            },
        )
    if settings.chat_openai_direct_enabled:
        if not settings.openai_api_key:
            raise RuntimeError("direct OpenAI chat requires an OpenAI API key")
        if (
            settings.chat_openai_luna_route != "gpt-5.6-luna@openai"
            or settings.chat_openai_model != "gpt-6-luna"
        ):
            raise RuntimeError("direct OpenAI chat must use the reviewed Luna route")
        direct_choice = {
            "id": "gpt-5.6-luna@openai",
            "label": (
                "GPT-6 Luna"
                if settings.environment == "production"
                else "GPT-6 Luna (Direct)"
            ),
            "route": settings.chat_openai_luna_route,
            "provider": "openai",
        }
        if settings.environment == "production":
            # GLM-5.3-Flash is hidden while direct Luna serves production.
            expected_discovery = (direct_choice,)
    if settings.chat_sponsored_deepseek_enabled:
        if settings.environment != "production":
            raise RuntimeError("the sponsored DeepSeek model is production-only")
        expected_sponsored_route = "deepseek-ai/DeepSeek-V4.1-Flash-1017:novita"
        if settings.chat_sponsored_deepseek_route != expected_sponsored_route:
            raise RuntimeError(
                "sponsored DeepSeek V4.1 Flash must use the reviewed Novita route"
            )
        # The organization pays through the dedicated title credential.
        if (
            not settings.chat_title_hf_token
            or settings.chat_title_bill_to != "huggingface"
        ):
            raise RuntimeError(
                "sponsored DeepSeek requires the huggingface-billed title credential"
            )
        expected_discovery += (
            {
                "id": "deepseek-ai/DeepSeek-V4.1-Flash-1017",
                "label": "DeepSeek V4.1 Flash",
                "route": expected_sponsored_route,
                "provider": "huggingface",
            },
        )
    if settings.environment == "staging":
        expected_kimi_route = "moonshotai/Kimi-K3:baseten"
        if settings.chat_kimi_route != expected_kimi_route:
            raise RuntimeError("Kimi K3 must use the reviewed Hugging Face route")
        if settings.chat_luna_route != "openai/gpt-5.6-luna":
            raise RuntimeError("GPT-5.6 Luna must use the reviewed OpenAI route")
        expected_discovery += (
            {
                "id": "moonshotai/Kimi-K3",
                "label": "Kimi K3",
                "route": expected_kimi_route,
                "provider": "huggingface",
            },
            {
                "id": "gpt-5.6-luna@openrouter",
                "label": "GPT-5.6 Luna",
                "route": settings.chat_luna_route,
                "provider": "openrouter",
            },
        )
        if settings.chat_openai_direct_enabled:
            expected_discovery = (direct_choice,) + expected_discovery
    if settings.chat_alternative_model_enabled:
        if settings.environment != "staging":
            raise RuntimeError("alternative chat models are staging-only")
        if (
            settings.chat_alternative_model != "openai/gpt-5.6-luna"
            and settings.chat_alternative_model
            not in {choice["id"] for choice in expected_discovery}
        ):
            candidate_labels = {
                "openai/gpt-5.6-luna": "GPT-5.6 Luna",
                "google/gemini-3.7-flash": "Gemini 3.7 Flash",
            }
            expected_discovery += (
                {
                    "id": settings.chat_alternative_model,
                    "label": candidate_labels[settings.chat_alternative_model],
                    "route": settings.chat_alternative_model,
                    "provider": "openrouter",
                },
            )
    discovery_projection = tuple(
        {
            "id": choice["id"],
            "label": choice["label"],
            "route": choice["route"],
            "provider": choice["provider"],
        }
        for choice in discovered
    )
    if discovery_projection != expected_discovery:
        raise RuntimeError("chat discovery contains an unreviewed model configuration")
    if settings.chat_default_backend != "modal_cli":
        raise RuntimeError("deployed chat must use the isolated Modal backend")
    expected_modal_percentage = 100 if settings.chat_enabled else 0
    if settings.chat_new_chat_modal_percentage != expected_modal_percentage:
        raise RuntimeError("chat must not spill new sessions to local execution")
    if settings.chat_web_search_enabled:
        web_search_url = urlsplit(settings.chat_web_search_exa_url)
        if (
            settings.chat_web_search_provider != "exa"
            or not settings.chat_web_search_exa_api_key
            or web_search_url.scheme != "https"
            or web_search_url.hostname != "api.exa.ai"
            or web_search_url.path.rstrip("/") != "/search"
            or settings.chat_web_search_max_calls != 3
            or settings.chat_web_search_timeout_seconds != 3
            or settings.chat_web_search_result_count != 5
            or settings.chat_web_search_max_result_bytes != 16 * 1024
            or settings.chat_web_search_query_max_chars != 500
            or not (
                1
                <= settings.chat_web_search_monthly_warning_calls
                <= settings.chat_web_search_monthly_hard_calls
                <= 6_000
            )
        ):
            raise RuntimeError("web-search runtime descriptor is invalid")
    if settings.chat_hf_catalog_enabled:
        if (
            settings.chat_hf_catalog_timeout_seconds != 10
            or settings.chat_hf_catalog_max_calls != 6
            or settings.chat_hf_recursive_list_max_calls != 2
            or settings.chat_hf_discovery_max_limit != 50
            or settings.chat_hf_max_files != 200
            or settings.chat_hf_max_depth != 10
            or settings.chat_hf_card_metadata_max_bytes != 32 * 1024
            or settings.chat_hf_card_text_max_bytes != 192 * 1024
            or settings.chat_hf_card_total_max_bytes != 224 * 1024
            or settings.chat_hf_cache_max_entries != 512
            or settings.chat_hf_cache_max_bytes != 64 * 1024 * 1024
            or settings.chat_hf_response_max_bytes != 256 * 1024
        ):
            raise RuntimeError("HF catalog runtime descriptor is invalid")
    _validate_chat_gateway_policy(settings)
    if include_openrouter:
        _validate_chat_openrouter_policy(settings)


def _validate_chat_openrouter_policy(settings: Settings) -> None:
    """Validate deployed OpenRouter credentials and durable accounting."""

    if (
        settings.chat_openrouter_routing_enabled
        and settings.chat_openrouter_routing_policy == "preferred_provider"
    ):
        providers = [
            value.strip()
            for value in settings.chat_openrouter_preferred_providers.split(",")
            if value.strip()
        ]
        if not providers or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9._/-]{0,127}", value)
            for value in providers
        ):
            raise RuntimeError(
                "preferred-provider routing requires valid provider slugs"
            )

    if (
        settings.environment == "staging"
        and not settings.chat_openrouter_server_funded_enabled
    ):
        raise RuntimeError("staging OpenRouter funded/BYOK paths must remain enabled")
    # Production's OpenAI and HF routes do not use the shared OpenRouter key.
    # Keep durable accounting validation for existing sessions and BYOK below.
    if (
        settings.chat_openrouter_server_funded_enabled
        and not settings.chat_openrouter_api_key
    ):
        raise RuntimeError("server-funded OpenRouter chat requires an OpenRouter key")
    if settings.chat_openrouter_workspace_monthly_budget_usd != 200:
        raise RuntimeError("OpenRouter workspace budget must equal $200")
    expected_user_budget = 1 if settings.environment == "staging" else 5
    if settings.chat_openrouter_monthly_user_budget_usd != expected_user_budget:
        raise RuntimeError(
            f"OpenRouter per-user budget must equal ${expected_user_budget}"
        )
    if (
        settings.chat_openrouter_daily_budget_usd != 10
        or settings.chat_openrouter_rate_limit_window_seconds != 600
        or settings.chat_openrouter_user_rate_limit_calls != 30
        or settings.chat_openrouter_global_rate_limit_calls != 80
    ):
        raise RuntimeError("OpenRouter abuse circuit policy is invalid")
    if not settings.chat_openrouter_user_tracking_secret:
        raise RuntimeError("OpenRouter user tracking HMAC is required")
    from backend.services.openrouter_byok_service import credential_keyring
    from backend.services.openrouter_user_budget_service import (
        RequestBounds,
        safe_maximum_microusd,
    )

    try:
        credential_keyring(settings)
        maximum = max(
            safe_maximum_microusd(
                settings,
                route,
                RequestBounds(
                    request_bytes=1,
                    maximum_output_tokens=PROVIDER_OUTPUT_TOKEN_LIMIT,
                    payload={"messages": [{"role": "user", "content": "x"}]},
                ),
            )
            for route in settings.chat_openrouter_routes
        )
    except (ValueError, RuntimeError) as error:
        raise RuntimeError(
            "OpenRouter durable accounting configuration is invalid"
        ) from error
    if maximum > 1_000_000:
        raise RuntimeError(
            "OpenRouter minimum request bound exceeds the per-user hard budget"
        )
    from backend.services.openrouter_budget_service import (
        OpenRouterBudgetUnavailable,
        validate_openrouter_guardrail,
    )

    try:
        validate_openrouter_guardrail(settings)
    except OpenRouterBudgetUnavailable as error:
        raise RuntimeError(
            "OpenRouter provider-enforced guardrail is invalid"
        ) from error
