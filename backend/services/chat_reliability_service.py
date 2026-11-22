"""Deterministic, content-free aggregate health probes for production chat."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, Mapping

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from backend.config import Settings
from backend.models.database import ChatMessageRecord, ChatTurnLatency
from backend.services.autonomous_cron_probe import FindingState, HealthFinding
from backend.services.chat_tracing_service import SafeChatTurnObservation

CONTRACTS = (
    "success_rate",
    "provider_errors",
    "auth_errors",
    "billing_errors",
    "time_to_first_token",
    "completion_latency",
    "stream_integrity",
    "persistence",
    "capacity",
    "provider_failover",
)
USER_SIDE_ERROR_CODES = frozenset(
    {
        "cancelled",
        "cancel_control_missing",
        "context_too_large",
        "openai_budget_exhausted",
        "openai_user_concurrency_limited",
        "openai_user_rate_limited",
    }
)
PROVIDER_ERROR_CODES = frozenset({"provider_error", "openai_unavailable"})
BILLING_ERROR_CODES = frozenset({"hf_inference_billing_exhausted"})
INTERRUPTION_ERROR_CODES = frozenset({"external_worker_lost", "lease_expired"})
PERSISTENCE_ERROR_CODES = frozenset({"persistence_error", "transcript_mirror_error"})
MIN_FAILED_TURNS = 3
MIN_PROVIDER_ERRORS = 2
MIN_LATENCY_SAMPLES = 5
TTFT_MEDIAN_LIMIT_MS = 15_000
COMPLETION_P95_LIMIT_MS = 180_000
MAX_TURN_DURATION = timedelta(hours=1)


def release_probe_triggers(
    state: dict[str, Any],
    settings: Settings,
    *,
    provider_runtime_revision: str | None = None,
) -> tuple[bool, bool]:
    """Record release/provider identity and report whether checks must run now."""

    provider_manifest = [
        {
            "id": choice["id"],
            "provider": choice["provider"],
            "route": choice["route"],
        }
        for choice in settings.chat_model_choices
    ]
    provider_digest = hashlib.sha256(
        json.dumps(provider_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    changed = (
        state.get("observed_release_id") != settings.release_id
        or state.get("observed_provider_digest") != provider_digest
        or (
            provider_runtime_revision is not None
            and state.get("observed_provider_runtime_revision")
            != provider_runtime_revision
        )
    )
    state["observed_release_id"] = settings.release_id
    state["observed_provider_digest"] = provider_digest
    if provider_runtime_revision is not None:
        state["observed_provider_runtime_revision"] = provider_runtime_revision
    return changed, changed


@dataclass(frozen=True, slots=True)
class ChatAggregateSnapshot:
    total_requests: int
    successful_requests: int
    provider_errors: int
    auth_errors: int
    billing_errors: int
    ttft_ms: tuple[int, ...]
    completion_ms: tuple[int, ...]
    stream_interruptions: int
    persistence_failures: int
    capacity_failures: int
    collection_complete: bool
    window_start: datetime
    window_end: datetime
    provider_failovers: int = 0


def _percentile(values: tuple[int, ...], percentile: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * percentile / 100) - 1)]


def _finding(
    snapshot: ChatAggregateSnapshot,
    contract: str,
    state: FindingState,
    evidence: dict[str, int | str | None],
    *,
    component: str,
    error_class: str,
) -> HealthFinding:
    return HealthFinding(
        job_name="chat_reliability",
        plane="durable_data" if contract == "persistence" else "process_logs",
        contract=contract,
        state=state,
        summary=f"Chat {contract.replace('_', ' ')} is {state.value}.",
        evidence={
            **evidence,
            "incident_signature": f"chat:{component}:{error_class}",
            "window_start": snapshot.window_start.isoformat(),
            "window_end": snapshot.window_end.isoformat(),
        },
        observed_at=snapshot.window_end.isoformat(),
        operator_url="/admin/autonomous-operations",
        run_url=None,
    )


def classify_chat_aggregates(
    snapshot: ChatAggregateSnapshot,
) -> tuple[HealthFinding, ...]:
    """Classify sanitized counts and timings without inspecting chat content."""

    if not snapshot.collection_complete:
        return tuple(
            _finding(
                snapshot,
                contract,
                FindingState.UNKNOWN,
                {},
                component="aggregate_source",
                error_class="incomplete",
            )
            for contract in CONTRACTS
        )

    total = snapshot.total_requests
    failed = total - snapshot.successful_requests
    success_percent = (
        round(snapshot.successful_requests * 100 / total) if total else None
    )
    p50_ttft = _percentile(snapshot.ttft_ms, 50)
    p95_completion = _percentile(snapshot.completion_ms, 95)
    specs = (
        (
            "success_rate",
            failed >= MIN_FAILED_TURNS
            and success_percent is not None
            and success_percent < 95,
            "request_path",
            "success_rate_low" if total else "no_samples",
            {
                "total_requests": total,
                "failed_requests": failed,
                "success_percent": success_percent,
            },
        ),
        (
            "provider_errors",
            snapshot.provider_errors >= MIN_PROVIDER_ERRORS,
            "provider",
            "provider_error",
            {"failure_count": snapshot.provider_errors},
        ),
        (
            "auth_errors",
            snapshot.auth_errors > 0,
            "authentication",
            "auth_error",
            {"failure_count": snapshot.auth_errors},
        ),
        (
            "billing_errors",
            snapshot.billing_errors > 0,
            "billing",
            "billing_error",
            {"failure_count": snapshot.billing_errors},
        ),
        (
            "time_to_first_token",
            p50_ttft is not None and p50_ttft > TTFT_MEDIAN_LIMIT_MS,
            "stream",
            "ttft_regression",
            {"p50_ms": p50_ttft, "sample_count": len(snapshot.ttft_ms)},
        ),
        (
            "completion_latency",
            p95_completion is not None and p95_completion > COMPLETION_P95_LIMIT_MS,
            "stream",
            "completion_latency",
            {"p95_ms": p95_completion, "sample_count": len(snapshot.completion_ms)},
        ),
        (
            "stream_integrity",
            snapshot.stream_interruptions > 0,
            "stream",
            "interrupted",
            {"failure_count": snapshot.stream_interruptions},
        ),
        (
            "persistence",
            snapshot.persistence_failures > 0,
            "persistence",
            "write_or_reopen_failed",
            {"failure_count": snapshot.persistence_failures},
        ),
        (
            "capacity",
            snapshot.capacity_failures > 0,
            "capacity",
            "saturated",
            {"failure_count": snapshot.capacity_failures},
        ),
        (
            "provider_failover",
            snapshot.provider_failovers > 0,
            "provider",
            "failover",
            {"failover_count": snapshot.provider_failovers},
        ),
    )
    findings = []
    for contract, degraded, component, error_class, evidence in specs:
        state = FindingState.DEGRADED if degraded else FindingState.HEALTHY
        if contract == "success_rate" and total == 0:
            state = FindingState.UNKNOWN
        if (
            contract in {"time_to_first_token", "completion_latency"}
            and evidence["sample_count"] < MIN_LATENCY_SAMPLES
        ):
            state = FindingState.UNKNOWN
            error_class = "no_samples"
        findings.append(
            _finding(
                snapshot,
                contract,
                state,
                evidence,
                component=component,
                error_class=error_class,
            )
        )
    return tuple(findings)


def turn_outcome(terminal_status: str | None, error_code: str | None) -> str | None:
    if terminal_status == "complete":
        return "success"
    if terminal_status not in {"error", "interrupted"}:
        return None
    if error_code is None or error_code in USER_SIDE_ERROR_CODES:
        return None
    if error_code in PROVIDER_ERROR_CODES:
        return "provider_error"
    if error_code in BILLING_ERROR_CODES:
        return "billing_error"
    if "auth" in error_code:
        return "auth_error"
    if error_code in INTERRUPTION_ERROR_CODES:
        return "interrupted"
    if error_code in PERSISTENCE_ERROR_CODES:
        return "persistence_error"
    return "error"


def database_turn_observations(
    db: Session, start: datetime, end: datetime
) -> tuple[SafeChatTurnObservation, ...]:
    rows = db.execute(
        select(
            ChatTurnLatency.terminal_status,
            ChatMessageRecord.error_code,
            ChatTurnLatency.first_semantic_event_ms,
            ChatTurnLatency.total_ms,
        )
        .join(
            ChatMessageRecord,
            and_(
                ChatMessageRecord.turn_id == ChatTurnLatency.turn_id,
                ChatMessageRecord.role == "user",
            ),
        )
        .where(
            ChatTurnLatency.admitted_at >= start - MAX_TURN_DURATION,
            ChatTurnLatency.completed_at >= start,
            ChatTurnLatency.completed_at < end,
            ChatTurnLatency.qualification_run_id.is_(None),
        )
    ).all()
    observations = []
    for terminal_status, error_code, ttft_ms, total_ms in rows:
        outcome = turn_outcome(terminal_status, error_code)
        if outcome is None:
            continue
        succeeded = outcome == "success"
        observations.append(
            SafeChatTurnObservation(
                outcome=outcome,
                ttft_ms=ttft_ms if succeeded else None,
                duration_ms=total_ms if succeeded else None,
            )
        )
    return tuple(observations)


def database_provider_failovers(
    db: Session, settings: Settings, start: datetime, end: datetime
) -> int:
    if not settings.chat_sponsored_deepseek_route:
        return 0
    user = aliased(ChatMessageRecord)
    assistant = aliased(ChatMessageRecord)
    return db.scalar(
        select(func.count())
        .select_from(ChatTurnLatency)
        .join(
            user,
            and_(user.turn_id == ChatTurnLatency.turn_id, user.role == "user"),
        )
        .join(
            assistant,
            and_(
                assistant.turn_id == ChatTurnLatency.turn_id,
                assistant.role == "assistant",
            ),
        )
        .where(
            ChatTurnLatency.admitted_at >= start - MAX_TURN_DURATION,
            ChatTurnLatency.completed_at >= start,
            ChatTurnLatency.completed_at < end,
            ChatTurnLatency.qualification_run_id.is_(None),
            user.model_route == settings.chat_openai_luna_route,
            assistant.model_route == settings.chat_sponsored_deepseek_route,
        )
    )


def _snapshot(
    turns: tuple[SafeChatTurnObservation, ...],
    *,
    complete: bool,
    provider_failovers: int,
    operational_counts: Mapping[str, int],
    start: datetime,
    end: datetime,
) -> ChatAggregateSnapshot:
    outcomes = [item.outcome for item in turns]
    return ChatAggregateSnapshot(
        total_requests=len(turns),
        successful_requests=outcomes.count("success"),
        provider_errors=outcomes.count("provider_error"),
        auth_errors=outcomes.count("auth_error"),
        billing_errors=outcomes.count("billing_error"),
        ttft_ms=tuple(item.ttft_ms for item in turns if item.ttft_ms is not None),
        completion_ms=tuple(
            item.duration_ms for item in turns if item.duration_ms is not None
        ),
        stream_interruptions=sum(
            operational_counts.get(name, 0)
            for name in (
                "stale_turn_reconciliation",
                "worker_reattach_failure_rate",
                "executor_lost_rate",
            )
        )
        + outcomes.count("interrupted"),
        persistence_failures=sum(
            operational_counts.get(name, 0)
            for name in (
                "stream_persistence_failure",
                "transcript_mirror_failure",
                "transcript_reconciliation_failure",
            )
        )
        + outcomes.count("persistence_error"),
        capacity_failures=sum(
            operational_counts.get(name, 0)
            for name in (
                "capacity_saturation",
                "pool_budget_block",
                "pool_replenishment_failure",
            )
        ),
        collection_complete=complete,
        window_start=start,
        window_end=end,
        provider_failovers=provider_failovers,
    )


def probe_chat_aggregates(
    window: timedelta,
    *,
    settings: Settings,
    db: Session,
    now: datetime | None = None,
    operational_counts: Mapping[str, int] | None = None,
) -> tuple[HealthFinding, ...]:
    """Probe one aggregate window from terminal chat turns in the database."""

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    start = observed_at - window
    try:
        turns = database_turn_observations(db, start, observed_at)
        failovers = database_provider_failovers(db, settings, start, observed_at)
        complete = True
    except SQLAlchemyError:
        db.rollback()
        turns, failovers, complete = (), 0, False
    return classify_chat_aggregates(
        _snapshot(
            turns,
            complete=complete,
            provider_failovers=failovers,
            operational_counts=operational_counts or {},
            start=start,
            end=observed_at,
        )
    )
