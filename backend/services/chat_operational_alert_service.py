"""Content-free operational alerts for production chat health."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatExecutorTransportAlert, ChatMessageRecord
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
)
from backend.services.autonomous_cron_probe import FindingState, HealthFinding

PROVIDER_ERROR_CODES = frozenset(
    {
        "provider_error",
        "provider_invalid_request",
        "provider_rate_limit",
        "provider_timeout",
        "provider_unavailable",
    }
)

# These strings are emitted without prompts, answers, capabilities, or credentials.
# Provider failures are excluded because they use the sustained database signal below.
RUNTIME_FAILURE_PATTERNS = {
    "pool_replenishment_failure": "chat blank pool replenishment failed",
    "pool_budget_block": "chat blank pool budget blocked",
    "turn_cleanup_failure": "chat cleanup failed",
    "edit_cleanup_failure": "chat edit preparation cleanup failed",
    "background_task_failure": "chat background task failed",
    "stream_persistence_failure": "chat stream persistence failed",
    "transcript_mirror_failure": "chat transcript mirror failed",
    "transcript_reconciliation_failure": "chat transcript reconciliation failed",
    "latency_finalize_failure": "chat latency finalize failed",
    "latency_phase_failure": "chat latency phase failed",
    "stale_turn_reconciliation": "chat stale turns reconciled",
    "langfuse_initialization_failure": "chat Langfuse trace initialization failed",
    "langfuse_finalization_failure": "chat Langfuse trace finalization failed",
    "langfuse_client_failure": "chat Langfuse client initialization failed",
    "excalidraw_mcp_unready": "chat Excalidraw MCP registration failed",
    "durable_lifecycle_telemetry_failure": (
        "chat durable lifecycle Langfuse emission failed"
    ),
    "event_journal_bound": (
        "chat durable lifecycle event=typed_failure code=event_journal_exhausted"
    ),
    "projection_mismatch": (
        "chat durable lifecycle event=typed_failure code=projection_mismatch"
    ),
    "cancel_control_missing": (
        "chat durable lifecycle event=typed_failure code=cancel_control_missing"
    ),
    "dispatch_failed": (
        "chat durable lifecycle event=typed_failure code=dispatch_failed"
    ),
    "stale_fence_rejection": (
        "chat durable lifecycle event=stale_fence_rejection code=stale"
    ),
    "expired_turn_lease": (
        "chat durable lifecycle event=expired_turn_lease code=expired"
    ),
    "paper_curation_dispatch_pause": "paper curation dispatch paused",
    "paper_curation_dispatch_recovery": "paper curation dispatch resumed",
}
LIFECYCLE_PATTERN = re.compile(
    r"chat durable lifecycle event=(?P<event>[a-z_]+) "
    r"code=(?P<code>[a-z_]+|none) value=(?P<value>\d+)(?:\s|$)"
)
LIFECYCLE_ALERT_NAMES = frozenset(
    {
        "worker_reattach_failure_rate",
        "executor_lost_rate",
        "capacity_saturation",
        "workspace_create_ratio",
        "ttft_regression_rate",
        "stale_fence_rejection",
        "expired_turn_lease",
    }
)
MAX_LIFECYCLE_VALUE = 16 * 1024 * 1024
EXECUTOR_ALERT_CLAIM_SECONDS = 60
EXECUTOR_ALERT_RETRY_SECONDS = 60


def _alert_now(db: Session, test_now: datetime | None) -> datetime:
    if test_now is not None and db.get_bind().dialect.name == "sqlite":
        return test_now
    value = db.scalar(select(func.current_timestamp()))
    if value is None:
        raise RuntimeError("executor transport alert clock is unavailable")
    return value


def claim_executor_transport_alert(
    db: Session, *, owner: str, now: datetime | None = None
) -> ChatExecutorTransportAlert | None:
    """Fence one pending/expired outbox row for immediate or minute retry delivery."""

    if not owner or len(owner) > 128:
        raise ValueError("executor transport alert owner is invalid")
    observed = _alert_now(db, now)
    row = db.scalar(
        select(ChatExecutorTransportAlert)
        .where(
            ChatExecutorTransportAlert.delivery_state != "acknowledged",
            ChatExecutorTransportAlert.next_attempt_at <= observed,
            (
                (ChatExecutorTransportAlert.delivery_state == "pending")
                | (ChatExecutorTransportAlert.claim_expires_at <= observed)
            ),
        )
        .order_by(
            ChatExecutorTransportAlert.created_at, ChatExecutorTransportAlert.event_id
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    row.delivery_state = "claimed"
    row.claim_owner = owner
    row.claim_expires_at = observed + timedelta(seconds=EXECUTOR_ALERT_CLAIM_SECONDS)
    row.attempts += 1
    db.flush()
    return row


def settle_executor_transport_alert(
    db: Session,
    *,
    event_id: str,
    owner: str,
    acknowledged: bool,
    now: datetime | None = None,
) -> bool:
    """Acknowledge exactly once or return a failed delivery to minute retry."""

    observed = _alert_now(db, now)
    row = db.scalar(
        select(ChatExecutorTransportAlert)
        .where(ChatExecutorTransportAlert.event_id == event_id)
        .with_for_update()
    )
    if row is None or row.delivery_state == "acknowledged":
        return False
    if row.delivery_state != "claimed" or row.claim_owner != owner:
        raise RuntimeError("executor transport alert claim is stale")
    row.claim_owner = None
    row.claim_expires_at = None
    if acknowledged:
        row.delivery_state = "acknowledged"
        row.acknowledged_at = observed
    else:
        row.delivery_state = "pending"
        row.next_attempt_at = observed + timedelta(seconds=EXECUTOR_ALERT_RETRY_SECONDS)
    db.flush()
    return True


def executor_transport_alert_event(
    *, environment: str, epoch: int, transition: str, now: datetime
) -> dict[str, Any]:
    """Build the bounded, content-free event for a durably claimed epoch."""

    if environment not in {"staging", "production"} or epoch < 1:
        raise ValueError("executor transport alert scope is invalid")
    if transition not in {"open", "security_hold", "recovered"}:
        raise ValueError("executor transport alert transition is invalid")
    recovered = transition == "recovered"
    return {
        "id": f"executor-circuit:{environment}:{epoch}:{transition}",
        "signal": (
            "chat_executor_transport_recovered"
            if recovered
            else "chat_executor_transport_circuit_open"
        ),
        "severity": "recovery" if recovered else "critical",
        "count": 1,
        "classifications": {f"executor_transport_{transition}": 1},
        "window_start": now.isoformat(),
        "window_end": now.isoformat(),
        "primary_delivery_state": "pending",
        "fallback_delivery_state": "pending",
        "primary_attempts": 0,
        "fallback_attempts": 0,
        "created_at": now.isoformat(),
    }


def reliability_alert_classifications(
    findings: tuple[HealthFinding, ...] | list[HealthFinding],
) -> dict[str, int]:
    """Project degraded findings to bounded, content-free alert keys."""

    classifications: dict[str, int] = {}
    for finding in findings:
        if finding.state != FindingState.DEGRADED:
            continue
        signature = finding.evidence.get("incident_signature")
        if not isinstance(signature, str) or not signature.startswith("chat:"):
            continue
        classifications[f"{finding.contract}|{signature}"] = 1
    return classifications


@dataclass(frozen=True)
class ProviderHealth:
    total_turns: int
    failed_turns: int
    window_start: datetime
    window_end: datetime

    @property
    def failure_percent(self) -> int:
        if not self.total_turns:
            return 0
        return round(self.failed_turns * 100 / self.total_turns)


def provider_health(db: Session, settings: Settings, now: datetime) -> ProviderHealth:
    """Count terminal Hugging Face turns without reading transcript content."""

    start = now - timedelta(seconds=settings.chat_provider_alert_window_seconds)
    provider_route = next(
        choice["route"]
        for choice in settings.chat_model_choices
        if choice["provider"] == "huggingface"
    )
    terminal = ChatMessageRecord.status.in_(("complete", "error", "interrupted"))
    scope = (
        ChatMessageRecord.role == "user",
        ChatMessageRecord.model_route == provider_route,
        ChatMessageRecord.created_at >= start,
        ChatMessageRecord.created_at <= now,
        terminal,
    )
    total = int(
        db.scalar(select(func.count()).select_from(ChatMessageRecord).where(*scope))
        or 0
    )
    failed = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessageRecord)
            .where(*scope, ChatMessageRecord.error_code.in_(PROVIDER_ERROR_CODES))
        )
        or 0
    )
    return ProviderHealth(total, failed, start, now)


def provider_transition(
    *, active: bool, health: ProviderHealth, settings: Settings
) -> str | None:
    """Return only incident-entry or full-window-recovery transitions."""

    sustained = (
        health.failed_turns >= settings.chat_provider_alert_min_failures
        and health.failure_percent >= settings.chat_provider_alert_failure_percent
    )
    if not active and sustained:
        return "hf_provider_sustained_failure"
    if active and health.failed_turns == 0:
        return "hf_provider_recovered"
    return None


def runtime_failure_counts(messages: list[str]) -> dict[str, int]:
    """Classify raw journal lines, returning only content-free aggregate counts."""

    counts = {
        name: sum(pattern in message for message in messages)
        for name, pattern in RUNTIME_FAILURE_PATTERNS.items()
    }
    counts["session_store_forbidden"] = sum(
        "POST /api/internal/chat-gateway/session-store" in message
        and "403 Forbidden" in message
        for message in messages
    )
    return {name: count for name, count in counts.items() if count}


def lifecycle_window_alerts(messages: list[str], settings: Settings) -> dict[str, int]:
    """Return only configured lifecycle threshold breaches for one log window."""

    observations: list[tuple[str, str, int]] = []
    for message in messages:
        match = LIFECYCLE_PATTERN.search(message)
        if match is None:
            continue
        value = int(match.group("value"))
        if value <= MAX_LIFECYCLE_VALUE:
            observations.append((match.group("event"), match.group("code"), value))

    def count(event: str, code: str) -> int:
        return sum(
            value
            for observed_event, observed_code, value in observations
            if observed_event == event and observed_code == code
        )

    def rate_breached(numerator: int, denominator: int, percent: int) -> bool:
        return (
            denominator >= settings.chat_lifecycle_alert_min_samples
            and numerator * 100 >= denominator * percent
        )

    alerts: dict[str, int] = {}
    stale_fences = count("stale_fence_rejection", "stale")
    if stale_fences:
        alerts["stale_fence_rejection"] = stale_fences
    expired_leases = count("expired_turn_lease", "expired")
    if expired_leases:
        alerts["expired_turn_lease"] = expired_leases
    worker_failures = count("typed_failure", "external_worker_lost")
    worker_successes = count("worker_reconnect", "none")
    if rate_breached(
        worker_failures,
        worker_failures + worker_successes,
        settings.chat_lifecycle_alert_failure_percent,
    ):
        alerts["worker_reattach_failure_rate"] = worker_failures

    executor_failures = count("typed_failure", "execution_lost")
    executor_attempts = count("turn_state", "waiting_tool")
    if rate_breached(
        executor_failures,
        executor_attempts,
        settings.chat_lifecycle_alert_failure_percent,
    ):
        alerts["executor_lost_rate"] = executor_failures

    saturations = count("capacity_saturation", "none")
    if saturations >= settings.chat_lifecycle_capacity_saturation_count:
        alerts["capacity_saturation"] = saturations

    workspace_creates = count("workspace_state", "created")
    workspace_reuses = count("workspace_state", "reused")
    if rate_breached(
        workspace_creates,
        workspace_creates + workspace_reuses,
        settings.chat_lifecycle_workspace_create_percent,
    ):
        alerts["workspace_create_ratio"] = workspace_creates

    ttft_values = [
        value
        for event, code, value in observations
        if event == "ttft_ms" and code == "none"
    ]
    slow_ttft = sum(
        value >= settings.chat_lifecycle_ttft_threshold_ms for value in ttft_values
    )
    if rate_breached(
        slow_ttft,
        len(ttft_values),
        settings.chat_lifecycle_ttft_regression_percent,
    ):
        alerts["ttft_regression_rate"] = slow_ttft
    return alerts


def operational_alert_payload(
    event: dict[str, Any], settings: Settings
) -> dict[str, str]:
    """Render a content-free payload shared by primary and fallback delivery."""

    classifications = ",".join(sorted(event.get("classifications", {}))) or "none"
    return {
        "text": (
            f"PwC chat operational alert; signal={event['signal']}; "
            f"severity={event['severity']}; environment={settings.environment}; "
            f"release={settings.release_id}; count={event['count']}; "
            f"classifications={classifications}; window_start={event['window_start']}; "
            f"window_end={event['window_end']}; event_id={event['id']}; "
            f"runbook={settings.chat_sandbox_runbook_url}"
        )
    }


async def post_operational_alert(
    url: str,
    event: dict[str, Any],
    settings: Settings,
) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            url, json=operational_alert_payload(event, settings)
        )
        response.raise_for_status()


def provider_runtime_revision(db: Session, environment: str) -> str | None:
    """Return a content-free revision token for the active durable provider route."""

    row = AutonomousOperationsRepository().get_chat_provider_state(
        db,
        environment=environment,
    )
    if row is None:
        return None
    return ":".join(
        (
            row.environment,
            str(row.state_revision),
            row.manifest_revision,
            row.active_provider,
        )
    )
