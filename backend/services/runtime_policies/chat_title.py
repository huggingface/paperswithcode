"""Chat title-generation validation."""

from __future__ import annotations

from backend.config import Settings


def _validate_chat_title_policy(settings: Settings) -> None:
    """Validate the environment-specific title provider and spend circuit."""

    if not settings.chat_scope_guardrail_enabled:
        raise RuntimeError("enabled chat requires the research-scope guardrail")
    if (
        not settings.chat_title_generation_enabled
        or not settings.chat_title_credential_owner.strip()
        or settings.chat_title_credential_environment != settings.environment
    ):
        raise RuntimeError(
            "an environment-scoped title credential with a named owner is required"
        )
    hf_glm = (
        settings.chat_title_provider == "huggingface"
        and settings.chat_title_model == "zai-org/GLM-5.3-Flash:baseten"
        and settings.chat_title_hf_token
        and settings.chat_title_bill_to
    )
    if not hf_glm:
        raise RuntimeError("an HF GLM title credential is required")
    if (
        settings.chat_title_max_tokens != 64
        or settings.chat_title_monthly_cap_microusd <= 0
        or not 0
        < settings.chat_title_warning_microusd
        < settings.chat_title_monthly_cap_microusd
        or settings.chat_title_max_call_microusd
        > settings.chat_title_monthly_cap_microusd
        or settings.chat_title_max_call_microusd
        < (
            8_000 * settings.chat_title_input_microusd_per_token
            + settings.chat_title_max_tokens
            * settings.chat_title_output_microusd_per_token
        )
    ):
        raise RuntimeError("the title model and monthly circuit are invalid")
