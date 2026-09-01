"""Deterministic, content-free aggregate health probes for production chat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Mapping

from backend.config import Settings
from backend.services.autonomous_cron_probe import FindingState, HealthFinding
from backend.services.chat_tracing_service import (
    SafeChatTurnObservation,
    SafeProviderObservation,
    fetch_chat_turn_observations,
    fetch_provider_request_observations,
)

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
)


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
    success_percent = (
        round(snapshot.successful_requests * 100 / total) if total else None
    )
    p95_ttft = _percentile(snapshot.ttft_ms, 95)
    p95_completion = _percentile(snapshot.completion_ms, 95)
    specs = (
        (
            "success_rate",
            total == 0 or (success_percent is not None and success_percent < 95),
            "request_path",
            "success_rate_low" if total else "no_samples",
            {"total_requests": total, "success_percent": success_percent},
        ),
        (
            "provider_errors",
            snapshot.provider_errors > 0,
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
            p95_ttft is not None and p95_ttft > 10_000,
            "stream",
            "ttft_regression",
            {"p95_ms": p95_ttft, "sample_count": len(snapshot.ttft_ms)},
        ),
        (
            "completion_latency",
            p95_completion is not None and p95_completion > 180_000,
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
    )
    findings = []
    for contract, degraded, component, error_class, evidence in specs:
        state = FindingState.DEGRADED if degraded else FindingState.HEALTHY
        if contract == "success_rate" and total == 0:
            state = FindingState.UNKNOWN
        if (
            contract in {"time_to_first_token", "completion_latency"}
            and evidence["sample_count"] == 0
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


def _snapshot(
    observations: tuple[SafeProviderObservation, ...],
    turns: tuple[SafeChatTurnObservation, ...],
    *,
    complete: bool,
    operational_counts: Mapping[str, int],
    start: datetime,
    end: datetime,
) -> ChatAggregateSnapshot:
    outcomes = [item.outcome for item in observations]
    turn_outcomes = [item.outcome for item in turns]
    return ChatAggregateSnapshot(
        total_requests=len(turns),
        successful_requests=turn_outcomes.count("success"),
        provider_errors=max(
            outcomes.count("provider_error"), turn_outcomes.count("provider_error")
        ),
        auth_errors=max(
            outcomes.count("auth_error"), turn_outcomes.count("auth_error")
        ),
        billing_errors=max(
            outcomes.count("billing_error"), turn_outcomes.count("billing_error")
        ),
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
        + turn_outcomes.count("interrupted"),
        persistence_failures=sum(
            operational_counts.get(name, 0)
            for name in (
                "stream_persistence_failure",
                "transcript_mirror_failure",
                "transcript_reconciliation_failure",
            )
        ),
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
    )


def probe_chat_aggregates(
    window: timedelta,
    *,
    settings: Settings,
    now: datetime | None = None,
    operational_counts: Mapping[str, int] | None = None,
) -> tuple[HealthFinding, ...]:
    """Probe one aggregate window using sanitized Langfuse and alert evidence."""

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    start = observed_at - window
    page = fetch_provider_request_observations(settings, start, observed_at)
    turns = fetch_chat_turn_observations(settings, start, observed_at)
    return classify_chat_aggregates(
        _snapshot(
            page.observations if page is not None else (),
            turns.observations if turns is not None else (),
            complete=(
                page is not None
                and page.complete
                and turns is not None
                and turns.complete
            ),
            operational_counts=operational_counts or {},
            start=start,
            end=observed_at,
        )
    )
