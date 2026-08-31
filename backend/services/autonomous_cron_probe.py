"""Deterministic CRON health findings for autonomous operations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from backend.services.cron_registry import CronJobDefinition, list_cron_jobs

Plane = Literal["scheduler", "process_logs", "durable_data", "semantic_outcome"]


class FindingState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HealthFinding:
    job_name: str
    plane: Plane
    contract: str
    state: FindingState
    summary: str
    evidence: dict[str, Any]
    observed_at: str
    operator_url: str
    run_url: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_name": self.job_name,
            "plane": self.plane,
            "contract": self.contract,
            "state": self.state.value,
            "summary": self.summary,
            "evidence": self.evidence,
            "observed_at": self.observed_at,
            "operator_url": self.operator_url,
            "run_url": self.run_url,
        }


@dataclass(frozen=True, slots=True)
class CronAudit:
    mode: Literal["daily"]
    generated_at: str
    total_jobs: int
    healthy: int
    degraded: int
    unknown: int
    plane_counts: dict[str, dict[str, int]]
    findings: tuple[HealthFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "total_jobs": self.total_jobs,
            "healthy": self.healthy,
            "degraded": self.degraded,
            "unknown": self.unknown,
            "plane_counts": self.plane_counts,
            "findings": [finding.as_dict() for finding in self.findings],
        }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _state(value: Any) -> FindingState:
    if value in {"healthy", "running"}:
        return FindingState.HEALTHY
    if value == "unknown" or value is None:
        return FindingState.UNKNOWN
    return FindingState.DEGRADED


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _schedule_boundary(
    definition: CronJobDefinition, now: datetime
) -> tuple[datetime, datetime] | None:
    if not definition.evidence_contract.schedule_policies:
        return None
    slots = [
        policy.slots(now) for policy in definition.evidence_contract.schedule_policies
    ]
    return max(previous for previous, _upcoming in slots), min(
        upcoming for _previous, upcoming in slots
    )


def _scheduler_finding_state(
    definition: CronJobDefinition,
    job: Mapping[str, Any],
    now: datetime,
) -> tuple[FindingState, str, dict[str, Any]]:
    execution = job.get("execution_health") or {}
    systemd = job.get("systemd_status") or {}
    workflow = job.get("workflow_status") or {}
    boundary = _schedule_boundary(definition, now)
    if definition.scheduler == "manual":
        return FindingState.HEALTHY, "manual job has no scheduler contract", {}
    if execution.get("applicable") is False and execution.get("status") == "healthy":
        return (
            FindingState.HEALTHY,
            "scheduler is intentionally disabled by configuration",
            {"scheduler": definition.scheduler},
        )
    if systemd.get("available") and (
        systemd.get("enabled") is False or systemd.get("timer_active") is False
    ):
        return (
            FindingState.DEGRADED,
            "declared systemd timer is disabled or inactive",
            {
                "enabled": systemd.get("enabled"),
                "timer_active": systemd.get("timer_active"),
            },
        )
    activity = max(
        (
            candidate
            for candidate in (
                _timestamp(execution.get("last_started_at")),
                _timestamp(execution.get("last_completed_at")),
                _timestamp(job.get("last_run")),
            )
            if candidate is not None
        ),
        default=None,
    )
    if activity is not None and activity > now + timedelta(minutes=5):
        return (
            FindingState.UNKNOWN,
            "latest scheduler activity is ahead of the probe clock",
            {"last_activity_at": _iso(activity)},
        )
    if boundary is None:
        return FindingState.UNKNOWN, "declared schedule has no deterministic slot", {}
    previous, upcoming = boundary
    grace = timedelta(minutes=definition.schedule_grace_minutes)
    required = previous
    if now <= previous + grace:
        prior_slots = [
            policy.slots(previous - timedelta(microseconds=1))[0]
            for policy in definition.evidence_contract.schedule_policies
        ]
        required = max(prior_slots)
    evidence = {
        "last_activity_at": _iso(activity) if activity else None,
        "required_activity_at": _iso(required),
        "next_expected_at": _iso(upcoming),
        "grace_minutes": definition.schedule_grace_minutes,
    }
    if activity is not None and activity >= required:
        return (
            FindingState.HEALTHY,
            "scheduler activity satisfies the as-of slot",
            evidence,
        )
    telemetry_unavailable = (
        workflow.get("available") is False
        or systemd.get("available") is False
        or execution.get("status") == "unknown"
    )
    if activity is None and telemetry_unavailable:
        return FindingState.UNKNOWN, "scheduler telemetry is unavailable", evidence
    return FindingState.DEGRADED, "expected scheduler activity is missing", evidence


def _output_reason(job: Mapping[str, Any]) -> str:
    return str((job.get("output_health") or {}).get("reason") or "")[:256]


def _telemetry_failed(job: Mapping[str, Any]) -> bool:
    return bool((job.get("db_metrics") or {}).get("freshness_error"))


def _durable_state(
    definition: CronJobDefinition, job: Mapping[str, Any], now: datetime
) -> tuple[FindingState, str]:
    if not definition.evidence_contract.durable_data_required:
        return FindingState.HEALTHY, "durable data freshness is not applicable"
    if _telemetry_failed(job):
        return FindingState.UNKNOWN, "durable data telemetry is unavailable"
    last_write = _timestamp(job.get("last_db_write"))
    recent_writes = job.get("recent_write_count")
    if last_write is None:
        if (
            job.get("log_status") == "success_no_work"
            and definition.healthy_no_work_allowed
        ):
            return FindingState.HEALTHY, "no durable write was required for this run"
        return FindingState.UNKNOWN, "no durable write timestamp is available"
    age_minutes = max(0.0, (now - last_write).total_seconds() / 60)
    if age_minutes > definition.stale_after_minutes:
        return (
            FindingState.DEGRADED,
            f"durable data is {age_minutes:.0f}m old",
        )
    if recent_writes == 0 and not definition.healthy_no_work_allowed:
        return FindingState.DEGRADED, "required durable throughput is zero"
    return FindingState.HEALTHY, f"durable data is {age_minutes:.0f}m old"


THROUGHPUT_TERMS = (
    "backlog",
    "queue",
    "no work",
    "zero work",
    "partial",
    "processed",
    "rate-limit",
    "stuck processing",
    "waited",
)


def _throughput_state(
    definition: CronJobDefinition, job: Mapping[str, Any]
) -> tuple[FindingState, str]:
    reason = _output_reason(job)
    lowered = reason.lower()
    work = job.get("work_metrics") or {}
    data = job.get("db_metrics") or {}
    if definition.evidence_contract.throughput_source == "health_record":
        record_available = bool(
            work.get("review_record_available")
            or work.get("monitor_record_available")
            or work.get("operator_record_available")
        )
        record_status = (
            work.get("review_status")
            or work.get("monitor_status")
            or work.get("operator_status")
        )
        if not record_available:
            return FindingState.UNKNOWN, "throughput health record is unavailable"
        if record_status in {"failed", "degraded"}:
            return FindingState.DEGRADED, "throughput health record reports failure"
        if record_status in {"healthy", "dormant"}:
            return FindingState.HEALTHY, "throughput health record passed"
        return FindingState.UNKNOWN, "throughput health record state is unknown"
    if _telemetry_failed(job):
        return FindingState.UNKNOWN, "throughput and backlog telemetry is unavailable"
    output_degraded = (
        _state((job.get("output_health") or {}).get("status")) is FindingState.DEGRADED
    )
    backlog_keys = (
        "backlog",
        "queued",
        "pending",
        "stale",
        "failed",
        "blocking",
        "oldest_wait",
    )
    bad_backlog = any(
        any(term in str(key).lower() for term in backlog_keys)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        for key, value in {**work, **data}.items()
    )
    if output_degraded and (
        bad_backlog or any(term in lowered for term in THROUGHPUT_TERMS)
    ):
        return FindingState.DEGRADED, reason
    if work or any(key != "freshness_error" for key in data):
        return (
            FindingState.HEALTHY,
            "bounded throughput and backlog evidence is available",
        )
    if (
        job.get("log_status") == "success_no_work"
        and definition.healthy_no_work_allowed
    ):
        return FindingState.HEALTHY, "zero work is allowed by the declared contract"
    return FindingState.UNKNOWN, "throughput and backlog evidence is unavailable"


def _semantic_state(
    definition: CronJobDefinition, job: Mapping[str, Any]
) -> tuple[FindingState, str]:
    if definition.evidence_contract.semantic_source == "health_record":
        work = job.get("work_metrics") or {}
        record_available = bool(
            work.get("review_record_available")
            or work.get("monitor_record_available")
            or work.get("operator_record_available")
        )
        record_status = (
            work.get("review_status")
            or work.get("monitor_status")
            or work.get("operator_status")
        )
        if not record_available:
            return FindingState.UNKNOWN, "semantic health record is unavailable"
        if record_status in {"failed", "degraded"}:
            return FindingState.DEGRADED, "semantic health record reports failure"
        if record_status in {"healthy", "dormant"}:
            return FindingState.HEALTHY, "semantic health record passed"
        return FindingState.UNKNOWN, "semantic health record state is unknown"
    if definition.evidence_contract.semantic_source == "unavailable":
        return FindingState.UNKNOWN, "no semantic evaluator is declared"
    if _telemetry_failed(job):
        return FindingState.UNKNOWN, "semantic telemetry is unavailable"
    evidence = (job.get("output_contract_evidence") or {}).get("semantic") or {}
    typed_state = _state(evidence.get("status"))
    typed_reason = str(evidence.get("reason") or "")[:256]
    if typed_state is FindingState.HEALTHY:
        return FindingState.HEALTHY, typed_reason or "semantic evaluator passed"
    if typed_state is FindingState.DEGRADED:
        return FindingState.DEGRADED, typed_reason or "semantic evaluator failed"
    return FindingState.UNKNOWN, "semantic evaluator evidence is unavailable"


def _bounded(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, Mapping):
        return {
            str(key)[:64]: _bounded(item)
            for key, item in list(sorted(value.items(), key=lambda pair: str(pair[0])))[
                :20
            ]
            if isinstance(item, (str, int, float, bool, type(None)))
        }
    return str(type(value).__name__)


def _run_url(job: Mapping[str, Any]) -> str | None:
    workflow = job.get("workflow_status")
    if not isinstance(workflow, Mapping):
        return None
    run_id = workflow.get("run_id")
    if not isinstance(run_id, int) or run_id <= 0:
        return None
    return f"https://github.com/huggingface/paperswithcode/actions/runs/{run_id}"


def build_job_findings(
    definition: CronJobDefinition,
    job: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[HealthFinding, ...]:
    """Evaluate every declared evidence contract without model judgment."""

    observed_at = _iso(now)
    operator_url = "/autonomous-operations?operator=cron"
    if job is None:
        return tuple(
            HealthFinding(
                job_name=definition.id,
                plane=plane,
                contract=contract,
                state=FindingState.UNKNOWN,
                summary="declared job is absent from the collected dashboard",
                evidence={"telemetry": "missing"},
                observed_at=observed_at,
                operator_url=operator_url,
                run_url=None,
            )
            for plane, contract in (
                ("scheduler", "scheduler_execution"),
                ("process_logs", "exit_state"),
                ("process_logs", "log_signature"),
                ("process_logs", "lock_ownership_age"),
                ("durable_data", "durable_data_freshness"),
                ("durable_data", "throughput_backlog"),
                ("semantic_outcome", "semantic_correctness"),
            )
        )

    output = job.get("output_health") or {}
    lock = job.get("lock_state") or {}
    workflow = job.get("workflow_status") or {}
    systemd = job.get("systemd_status") or {}
    log_status = job.get("log_status") or "unknown"
    run_url = _run_url(job)

    scheduler_state, scheduler_summary, scheduler_evidence = _scheduler_finding_state(
        definition, job, now
    )
    scheduler = HealthFinding(
        definition.id,
        "scheduler",
        "scheduler_execution",
        scheduler_state,
        scheduler_summary,
        _bounded(
            {"scheduler": definition.evidence_contract.scheduler, **scheduler_evidence}
        ),
        observed_at,
        operator_url,
        run_url,
    )

    if job.get("is_running"):
        started_at = _timestamp(
            (job.get("execution_health") or {}).get("last_started_at")
        )
        runtime_minutes = (
            max(0.0, (now - started_at).total_seconds() / 60) if started_at else None
        )
        if started_at is None:
            exit_state = FindingState.UNKNOWN
            exit_summary = "current run start time is unavailable"
        elif (
            runtime_minutes is not None
            and runtime_minutes > definition.expected_runtime_minutes
        ):
            exit_state = FindingState.DEGRADED
            exit_summary = "running job exceeded its declared runtime"
        else:
            exit_state = FindingState.HEALTHY
            exit_summary = "job is running within the declared runtime"
    elif log_status in definition.evidence_contract.accepted_exit_states:
        exit_state = FindingState.HEALTHY
        exit_summary = f"latest exit state is {log_status}"
    elif systemd.get("available") and systemd.get("service_result") == "success":
        exit_state = FindingState.HEALTHY
        exit_summary = "latest systemd service exit state is success"
    elif (
        log_status == "failed"
        or workflow.get("conclusion")
        in {
            "failure",
            "cancelled",
            "timed_out",
        }
        or (
            systemd.get("available")
            and systemd.get("service_result") not in {None, "success"}
        )
    ):
        exit_state = FindingState.DEGRADED
        exit_summary = "latest declared execution did not exit successfully"
    else:
        exit_state = FindingState.UNKNOWN
        exit_summary = "latest exit state is unavailable"
    exit_finding = HealthFinding(
        definition.id,
        "process_logs",
        "exit_state",
        exit_state,
        exit_summary,
        _bounded(
            {
                "log_status": log_status,
                "workflow_conclusion": workflow.get("conclusion"),
                "systemd_result": systemd.get("service_result"),
            }
        ),
        observed_at,
        operator_url,
        run_url,
    )

    log_source = definition.evidence_contract.log_source
    work_metrics = job.get("work_metrics") or {}
    if log_source == "health_record":
        record_available = bool(
            work_metrics.get("review_record_available")
            or work_metrics.get("monitor_record_available")
        )
        record_status = work_metrics.get("review_status") or work_metrics.get(
            "monitor_status"
        )
        if not record_available:
            log_state = FindingState.UNKNOWN
        elif record_status in {"healthy", "dormant"}:
            log_state = FindingState.HEALTHY
        elif record_status in {"failed", "degraded"}:
            log_state = FindingState.DEGRADED
        else:
            log_state = FindingState.UNKNOWN
        log_summary = (
            f"latest bounded health-record state is {record_status or 'unknown'}"
        )
    elif log_source == "journal":
        service_result = systemd.get("service_result")
        if not systemd.get("available"):
            log_state = FindingState.UNKNOWN
        elif service_result == "success":
            log_state = FindingState.HEALTHY
        elif service_result:
            log_state = FindingState.DEGRADED
        else:
            log_state = FindingState.UNKNOWN
        log_summary = (
            f"latest bounded journal exit state is {service_result or 'unknown'}"
        )
    elif log_status in definition.evidence_contract.accepted_log_states:
        log_state = FindingState.HEALTHY
        log_summary = f"latest bounded file-log state is {log_status}"
    elif log_status == "failed":
        log_state = FindingState.DEGRADED
        log_summary = "latest bounded file-log state is failed"
    else:
        log_state = FindingState.UNKNOWN
        log_summary = "latest bounded file-log state is unknown"
    log_finding = HealthFinding(
        definition.id,
        "process_logs",
        "log_signature",
        log_state,
        log_summary,
        _bounded(
            {
                "last_run": job.get("last_run"),
                "log_status": log_status,
                "log_source": log_source,
                "health_record_status": record_status
                if log_source == "health_record"
                else None,
                "systemd_result": systemd.get("service_result")
                if log_source == "journal"
                else None,
                "work_summary": job.get("work_summary"),
            }
        ),
        observed_at,
        operator_url,
        run_url,
    )

    if lock.get("stale") is True:
        lock_state = FindingState.DEGRADED
        lock_summary = "held lock exceeded its declared runtime contract"
    elif lock.get("held") is None or lock.get("probe_status") == "unknown":
        lock_state = FindingState.UNKNOWN
        lock_summary = "lock ownership could not be verified"
    else:
        lock_state = FindingState.HEALTHY
        lock_summary = (
            "active lock belongs to a running job"
            if lock.get("held") and job.get("is_running")
            else "no stale held lock"
        )
    lock_finding = HealthFinding(
        definition.id,
        "process_logs",
        "lock_ownership_age",
        lock_state,
        lock_summary,
        _bounded(lock),
        observed_at,
        operator_url,
        run_url,
    )

    freshness_state, freshness_summary = _durable_state(definition, job, now)
    freshness_finding = HealthFinding(
        definition.id,
        "durable_data",
        "durable_data_freshness",
        freshness_state,
        freshness_summary,
        _bounded(job.get("db_metrics") or {}),
        observed_at,
        operator_url,
        run_url,
    )
    throughput_state, throughput_summary = _throughput_state(definition, job)
    throughput_finding = HealthFinding(
        definition.id,
        "durable_data",
        "throughput_backlog",
        throughput_state,
        throughput_summary,
        _bounded(
            {
                "policy": definition.evidence_contract.throughput_policy,
                **{
                    f"work_{key}": value
                    for key, value in (job.get("work_metrics") or {}).items()
                },
                **{
                    f"data_{key}": value
                    for key, value in (job.get("db_metrics") or {}).items()
                },
            }
        ),
        observed_at,
        operator_url,
        run_url,
    )
    semantic_state, semantic_summary = _semantic_state(definition, job)
    semantic_finding = HealthFinding(
        definition.id,
        "semantic_outcome",
        "semantic_correctness",
        semantic_state,
        semantic_summary,
        _bounded(
            {
                "evaluator": definition.evidence_contract.semantic_evaluator,
                "output_reason": output.get("reason"),
                "diagnostic": job.get("diagnostics"),
            }
        ),
        observed_at,
        operator_url,
        run_url,
    )
    return (
        scheduler,
        exit_finding,
        log_finding,
        lock_finding,
        freshness_finding,
        throughput_finding,
        semantic_finding,
    )


class AutonomousCronProbe:
    def __init__(
        self,
        *,
        dashboard_provider: Callable[[], dict[str, Any]] | None = None,
        definitions: Sequence[CronJobDefinition] | None = None,
    ) -> None:
        self.dashboard_provider = dashboard_provider or self._build_dashboard
        self.definitions = tuple(
            definitions if definitions is not None else list_cron_jobs()
        )
        self.by_id = {job.id: job for job in self.definitions}

    @staticmethod
    def _build_dashboard() -> dict[str, Any]:
        from backend.services.cron_health import build_cron_dashboard

        return build_cron_dashboard()

    def probe_job(self, job_name: str, now: datetime) -> tuple[HealthFinding, ...]:
        definition = self.by_id.get(job_name)
        if definition is None:
            raise KeyError(f"CRON job is not declared: {job_name}")
        dashboard = self.dashboard_provider()
        job = next(
            (
                item
                for item in dashboard.get("jobs", ())
                if item.get("job_name") == job_name
            ),
            None,
        )
        return build_job_findings(definition, job, now)

    def audit_all_jobs(self, now: datetime) -> CronAudit:
        dashboard = self.dashboard_provider()
        dashboard_by_id = {
            item.get("job_name"): item for item in dashboard.get("jobs", ())
        }
        findings = tuple(
            finding
            for definition in self.definitions
            for finding in build_job_findings(
                definition, dashboard_by_id.get(definition.id), now
            )
        )
        states = Counter(finding.state.value for finding in findings)
        plane_counts = {
            plane: dict(
                Counter(
                    finding.state.value
                    for finding in findings
                    if finding.plane == plane
                )
            )
            for plane in (
                "scheduler",
                "process_logs",
                "durable_data",
                "semantic_outcome",
            )
        }
        return CronAudit(
            mode="daily",
            generated_at=_iso(now),
            total_jobs=len(self.definitions),
            healthy=states[FindingState.HEALTHY.value],
            degraded=states[FindingState.DEGRADED.value],
            unknown=states[FindingState.UNKNOWN.value],
            plane_counts=plane_counts,
            findings=findings,
        )


def probe_job(job_name: str, now: datetime) -> tuple[HealthFinding, ...]:
    return AutonomousCronProbe().probe_job(job_name, now)


def audit_all_jobs(now: datetime) -> CronAudit:
    return AutonomousCronProbe().audit_all_jobs(now)
