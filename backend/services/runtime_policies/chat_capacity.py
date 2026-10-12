"""Chat sandbox capacity and resource validation."""

from __future__ import annotations

from dataclasses import replace

from backend.config import Settings
from backend.services.runtime_policies.chat_runtime_profile import (
    ChatRuntimeKind,
    ChatRuntimeProfile,
    SandboxCapacityPolicy,
    _EXTERNAL_PI_CAPACITY_POLICIES,
    _resolve_chat_runtime_profile,
)


_SANDBOX_CAPACITY_POLICY = SandboxCapacityPolicy(
    max_concurrency=2,
    user_max_concurrency=2,
    total_live_cap=3,
    blank_pool_min=1,
    blank_pool_max=1,
)


def _validate_chat_capacity_policy(
    settings: Settings, profile: ChatRuntimeProfile | None = None
) -> None:
    profile = profile or _resolve_chat_runtime_profile(settings)
    configured = SandboxCapacityPolicy(
        max_concurrency=settings.chat_max_concurrency,
        user_max_concurrency=settings.chat_user_max_concurrency,
        total_live_cap=settings.chat_sandbox_total_live_cap,
        blank_pool_min=settings.chat_blank_pool_min,
        blank_pool_max=settings.chat_blank_pool_max,
    )
    candidates = (
        tuple(_EXTERNAL_PI_CAPACITY_POLICIES.values())
        if profile.kind is ChatRuntimeKind.EXTERNAL_ADMISSION
        else (_SANDBOX_CAPACITY_POLICY,)
    )
    if configured in candidates:
        return
    if (
        settings.environment == "staging"
        and profile.kind is ChatRuntimeKind.EXTERNAL_ADMISSION
        and settings.chat_executor_remote_transport_enabled
        and any(
            configured == replace(expected, blank_pool_min=4, blank_pool_max=4)
            for expected in candidates
        )
    ):
        return
    raise RuntimeError("chat capacity must be the reviewed runtime profile")


def _validate_chat_resource_policy(
    settings: Settings, profile: ChatRuntimeProfile | None = None
) -> None:
    """Validate sandbox resources and warm-pool lifetime."""

    if settings.chat_excalidraw_enabled != settings.chat_mcp_apps_host_enabled:
        raise RuntimeError("Excalidraw worker and MCP App host switches must match")
    if (
        settings.chat_sandbox_cpu_limit is not None
        and settings.chat_sandbox_cpu_limit < settings.chat_sandbox_cpu
    ):
        raise RuntimeError("chat CPU limit is below its request")
    if (
        settings.chat_sandbox_memory_limit_mib is not None
        and settings.chat_sandbox_memory_limit_mib < settings.chat_sandbox_memory_mib
    ):
        raise RuntimeError("chat memory limit is below its request")
    if settings.chat_blank_pool_enabled:
        if not settings.chat_persistent_worker_enabled:
            raise RuntimeError("blank pool requires persistent workers")
        if (
            settings.chat_blank_pool_min_remaining_seconds
            >= settings.chat_persistent_sandbox_lifetime_seconds
        ):
            raise RuntimeError("blank pool minimum remaining lifetime is invalid")
        if (
            settings.chat_blank_pool_rotate_before_seconds
            >= settings.chat_persistent_sandbox_lifetime_seconds
        ):
            raise RuntimeError("blank pool rotation window is invalid")
    if settings.chat_openai_direct_enabled:
        profile = profile or _resolve_chat_runtime_profile(settings)
        if not profile.pool_free and (
            not settings.chat_pi_prewarm_enabled
            or not settings.chat_blank_pool_enabled
            or settings.chat_effective_pi_prewarm_model
            != settings.chat_openai_luna_route
            or settings.chat_pi_prewarm_reasoning_effort != "low"
        ):
            raise RuntimeError(
                "direct OpenAI chat requires the direct-Luna low-reasoning prewarm profile"
            )
    if settings.chat_pi_prewarm_enabled:
        if not settings.chat_blank_pool_enabled:
            raise RuntimeError("Pi prewarm requires the blank pool")
        if not settings.chat_persistent_worker_enabled:
            raise RuntimeError("Pi prewarm requires persistent workers")
        if settings.chat_default_agent_harness != "pi":
            raise RuntimeError("Pi prewarm requires Pi as the default harness")
        prewarm_model = settings.chat_effective_pi_prewarm_model
        if prewarm_model not in settings.chat_route_providers:
            raise RuntimeError("Pi prewarm model is not in the route registry")
        expected_prewarm_model = (
            settings.chat_openai_luna_route
            if settings.chat_openai_direct_enabled
            else (
                settings.chat_alternative_model
                if settings.chat_alternative_model_enabled
                else settings.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
            )
        )
        if prewarm_model != expected_prewarm_model:
            raise RuntimeError("Pi prewarm model does not match the qualified model")
        if not settings.chat_system_prompt_sha256:
            raise RuntimeError("Pi prewarm requires an immutable prompt digest")
