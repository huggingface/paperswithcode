"""The reviewed chat runtime profile and external Pi capacity tiers."""

from __future__ import annotations

from collections.abc import Callable

from dataclasses import dataclass
from enum import Enum

from backend.config import Settings
from backend.chat_sandbox_worker.executor_protocol import PROTOCOL as EXECUTOR_CONTRACT
from backend.services.chat_runtime_contract import (
    ExternalAdmissionContract,
    require_external_admission_contract,
)


@dataclass(frozen=True, slots=True)
class SandboxCapacityPolicy:
    """Reviewed active-turn and warm-pool capacity."""

    max_concurrency: int
    user_max_concurrency: int
    total_live_cap: int
    blank_pool_min: int
    blank_pool_max: int


# Reviewed external Pi capacity tiers, keyed by admitted concurrent turns. The
# deploy tooling sizes the eight-replica fleet from the same tier value, and
# the OpenAI circuits below must match the tier (see docs/deployment.md).
_EXTERNAL_PI_CAPACITY_POLICIES = {
    tier: SandboxCapacityPolicy(
        max_concurrency=tier,
        user_max_concurrency=1,
        total_live_cap=16,
        blank_pool_min=1,
        blank_pool_max=1,
    )
    for tier in (32, 64)
}


_EXTERNAL_PI_CAPACITY_POLICY = _EXTERNAL_PI_CAPACITY_POLICIES[32]


# OpenAI concurrency equals the tier; the ten-minute call allowance grows faster
# because an MCP research turn spends 10-13 model calls and a full tier of turns
# cycles several times per window. The 32-turn allowance keeps each
# environment's established value; deploy/configure_host_env.py writes the same
# table and a test pins the two together.
_EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS = {
    "production": {32: 512, 64: 4096},
    "staging": {32: 300, 64: 4096},
}


def _external_pi_capacity_tier(settings: Settings) -> int | None:
    """Return the reviewed tier whose turn and OpenAI budgets the settings match."""

    tier = settings.chat_max_concurrency
    allowances = _EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS.get(settings.environment, {})
    if (
        tier in _EXTERNAL_PI_CAPACITY_POLICIES
        and settings.chat_openai_global_max_concurrency == tier
        and settings.chat_openai_global_rate_limit_calls == allowances.get(tier)
    ):
        return tier
    return None


class ChatRuntimeKind(Enum):
    LOCAL = "local"
    STAGING_QUALIFICATION = "staging_qualification"
    EXTERNAL_ADMISSION = "external_admission"


@dataclass(frozen=True, slots=True)
class ChatRuntimeProfile:
    kind: ChatRuntimeKind
    pool_free: bool = False


def _resolve_chat_runtime_profile(
    settings: Settings,
    require_contract: Callable[
        [ExternalAdmissionContract], object
    ] = require_external_admission_contract,
) -> ChatRuntimeProfile:
    """Resolve approved resource exceptions from the canonical runtime contract.

    Incomplete reversible bridges remain local and gain no resource exemption.
    Admission, unlike a disabled bridge, must always have a complete contract.
    """
    contract = ExternalAdmissionContract(
        durable_dispatch=settings.chat_durable_turn_dispatch_enabled,
        event_journal_schema=settings.chat_turn_event_journal_schema_enabled,
        external_supervisor=settings.chat_external_pi_supervisor_enabled,
        ready_worker_registry=settings.chat_external_pi_ready_registry_enabled,
        remote_workspace_tools=settings.chat_remote_workspace_tools_enabled,
        lazy_workspace=settings.chat_lazy_workspace_enabled,
        sandbox_executor=settings.chat_sandbox_executor_enabled,
        remote_bash=settings.chat_remote_bash_enabled,
        remote_read=settings.chat_remote_read_enabled,
        worker_contract_version=settings.chat_external_pi_worker_contract_version,
        runtime_contract_version=settings.chat_external_pi_runtime_contract_version,
    )
    try:
        require_contract(contract)
    except ValueError as error:
        if settings.chat_external_pi_admission_enabled:
            raise RuntimeError(
                "external Pi admission requires the complete durable runtime contract"
            ) from error
        return ChatRuntimeProfile(ChatRuntimeKind.LOCAL)

    pool_free = (
        settings.chat_sandbox_executor_contract_version == EXECUTOR_CONTRACT
        and not settings.chat_blank_pool_enabled
        and not settings.chat_pi_prewarm_enabled
    )
    if settings.chat_external_pi_admission_enabled:
        return ChatRuntimeProfile(
            ChatRuntimeKind.EXTERNAL_ADMISSION,
            pool_free=pool_free
            and settings.environment in {"staging", "production"}
            and _external_pi_capacity_tier(settings) is not None
            and settings.chat_user_max_concurrency == 1
            and settings.chat_openai_user_max_concurrency == 1
            and settings.chat_sandbox_total_live_cap == 16,
        )
    if (
        pool_free
        and settings.environment == "staging"
        and settings.chat_openai_direct_enabled
        and settings.chat_max_concurrency == 2
        and settings.chat_sandbox_total_live_cap == 3
    ):
        return ChatRuntimeProfile(ChatRuntimeKind.STAGING_QUALIFICATION, pool_free=True)
    return ChatRuntimeProfile(ChatRuntimeKind.LOCAL)
