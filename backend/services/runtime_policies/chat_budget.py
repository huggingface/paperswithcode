"""Chat sandbox spend and provider-reserve validation."""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.services.runtime_policies.chat_capacity import (
    _validate_chat_capacity_policy,
    _validate_chat_resource_policy,
)
from backend.services.runtime_policies.chat_runtime_profile import (
    ChatRuntimeProfile,
)
from backend.services.runtime_policies.chat_title import (
    _validate_chat_title_policy,
)


@dataclass(frozen=True, slots=True)
class SandboxSpendPolicy:
    """Reviewed spend thresholds pinned for deployed chat sandboxes."""

    warning_microusd: int
    application_cap_microusd: int
    environment_cap_microusd: int
    workspace_cap_microusd: int


_STARTER_SANDBOX_SPEND_POLICY = SandboxSpendPolicy(
    warning_microusd=75_000_000,
    application_cap_microusd=100_000_000,
    environment_cap_microusd=0,
    workspace_cap_microusd=250_000_000,
)


_STAGING_STARTER_SPEND_POLICIES = {
    "starter-app105-v2": SandboxSpendPolicy(
        warning_microusd=75_000_000,
        application_cap_microusd=105_000_000,
        environment_cap_microusd=0,
        workspace_cap_microusd=250_000_000,
    ),
    "starter-app150-v3": SandboxSpendPolicy(
        warning_microusd=120_000_000,
        application_cap_microusd=150_000_000,
        environment_cap_microusd=0,
        workspace_cap_microusd=250_000_000,
    ),
}


_TEAM_SANDBOX_SPEND_POLICIES = {
    "v1": SandboxSpendPolicy(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=125_000_000,
        workspace_cap_microusd=250_000_000,
    ),
    "v2": SandboxSpendPolicy(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=250_000_000,
        workspace_cap_microusd=250_000_000,
    ),
    "v3": SandboxSpendPolicy(
        warning_microusd=200_000_000,
        application_cap_microusd=225_000_000,
        environment_cap_microusd=250_000_000,
        workspace_cap_microusd=250_000_000,
    ),
}


def _validate_chat_capacity_and_spend_policy(
    settings: Settings, profile: ChatRuntimeProfile
) -> None:
    """Validate sandbox spend, capacity, alerting, and provider reserve."""

    if not settings.chat_sandbox_spend_enforcement_enabled:
        raise RuntimeError("PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED is required")
    configured_spend = SandboxSpendPolicy(
        warning_microusd=settings.chat_sandbox_warning_microusd,
        application_cap_microusd=settings.chat_sandbox_application_cap_microusd,
        environment_cap_microusd=settings.chat_sandbox_environment_cap_microusd,
        workspace_cap_microusd=settings.chat_sandbox_workspace_cap_microusd,
    )
    if settings.chat_sandbox_provider_mode == "team_environments":
        team_policy_version = next(
            (
                version
                for version, policy in _TEAM_SANDBOX_SPEND_POLICIES.items()
                if configured_spend == policy
            ),
            None,
        )
        expected_spend = _TEAM_SANDBOX_SPEND_POLICIES.get(team_policy_version)
    else:
        team_policy_version = None
        expected_spend = _STARTER_SANDBOX_SPEND_POLICY
        starter_suffix = "starter-v1"
        if settings.environment == "staging":
            for suffix, policy in _STAGING_STARTER_SPEND_POLICIES.items():
                if configured_spend == policy:
                    expected_spend = policy
                    starter_suffix = suffix
    if configured_spend != expected_spend:
        if settings.chat_sandbox_provider_mode == "starter_workspace":
            raise RuntimeError(
                "sandbox spend policy must be $75/$100/$250 with no environment cap"
            )
        raise RuntimeError("team sandbox spend policy is not reviewed")
    _validate_chat_capacity_policy(settings, profile)
    expected_modal_environment = f"pwc-chat-{settings.environment}"
    if settings.chat_sandbox_modal_environment != expected_modal_environment:
        raise RuntimeError(
            f"PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT must be {expected_modal_environment}"
        )
    if not settings.chat_sandbox_modal_workspace:
        raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_WORKSPACE is required")
    if not settings.chat_sandbox_modal_owner_username:
        raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME is required")
    if settings.chat_sandbox_provider_mode == "team_environments":
        policy_suffix = {
            "v1": "125-v1",
            "v2": "250-v2",
            "v3": "250-warn200-app225-v3",
        }[team_policy_version]
        expected_attestation = (
            f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-"
            f"{settings.environment}-{policy_suffix}"
        )
    else:
        expected_attestation = (
            f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-"
            f"{settings.environment}-{starter_suffix}"
        )
    if settings.chat_sandbox_budget_attestation != expected_attestation:
        raise RuntimeError(
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION does not match configured policy"
        )
    primary_alert = settings.chat_sandbox_slack_webhook_url
    fallback_alert = settings.chat_sandbox_alert_fallback_webhook_url
    if not primary_alert or not fallback_alert:
        raise RuntimeError("primary and fallback chat alert destinations are required")
    if fallback_alert == primary_alert:
        raise RuntimeError("primary and fallback chat alert destinations must differ")
    if not settings.chat_sandbox_runbook_url:
        raise RuntimeError("PWC_CHAT_SANDBOX_RUNBOOK_URL is required")
    if not settings.chat_sandbox_operator_username_set:
        raise RuntimeError("PWC_CHAT_SANDBOX_OPERATOR_USERNAMES is required")
    if settings.environment == "production" and (
        not settings.chat_operational_alerts_enabled
        or settings.chat_provider_alert_window_seconds != 300
        or settings.chat_provider_alert_min_failures != 5
        or settings.chat_provider_alert_failure_percent != 50
    ):
        raise RuntimeError(
            "production operational alerts require the reviewed 5-minute, "
            "5-failure, 50-percent provider policy"
        )
    rate = (settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu) * 40 + (
        settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
    ) / 1024 * 7
    burst = int(
        rate
        * settings.chat_sandbox_total_live_cap
        * (
            settings.chat_sandbox_watchdog_seconds
            + settings.chat_sandbox_drain_grace_seconds
            + settings.chat_sandbox_termination_grace_seconds
        )
    ) + (
        settings.chat_sandbox_reconciliation_allowance_microusd
        * settings.chat_sandbox_total_live_cap
    )
    if (
        settings.chat_sandbox_workspace_cap_microusd
        - settings.chat_sandbox_application_cap_microusd
        < burst
    ):
        raise RuntimeError(
            "sandbox provider reserve is smaller than the worst-case aggregate burst"
        )
    _validate_chat_title_policy(settings)
    _validate_chat_resource_policy(settings, profile)
