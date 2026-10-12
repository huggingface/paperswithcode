from __future__ import annotations

from datetime import UTC, datetime

from backend.services.autonomous_cron_probe import (
    AutonomousCronProbe,
    FindingState,
)
from backend.services.cron_registry import get_cron_job
from backend.services.cron_dashboard_snapshot_service import (
    CronDashboardSnapshotService,
)


NOW = datetime(2026, 8, 28, 12, 15, tzinfo=UTC)


def dashboard_job(**updates):
    value = {
        "job_name": "update_citations",
        "status": "healthy",
        "log_status": "success",
        "status_reason": "all contracts passed",
        "is_running": False,
        "last_run": "2026-08-28T12:05:00Z",
        "last_db_write": "2026-08-28T12:04:00Z",
        "recent_write_count": 10,
        "execution_health": {
            "status": "healthy",
            "reason": "systemd timer and latest service exit are healthy",
            "scheduler": "systemd",
        },
        "systemd_status": {
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_started_at": "2026-08-28T12:00:10Z",
            "last_completed_at": "2026-08-28T12:05:00Z",
            "service_active": False,
        },
        "output_health": {
            "status": "healthy",
            "reason": "durable output is fresh",
        },
        "output_contract_evidence": {
            "semantic": {
                "status": "healthy",
                "reason": "typed evaluator passed",
                "evaluator": "citations",
            }
        },
        "lock_state": {
            "exists": False,
            "held": False,
            "stale": False,
            "probe_status": "unlocked",
        },
        "workflow_status": {
            "available": True,
            "run_id": 123,
            "conclusion": "success",
        },
        "db_metrics": {"recent_writes": 10, "backlog": 0},
        "work_metrics": {"papers_processed": 10},
        "diagnostic_groups": {
            "scheduler_orchestration": [],
            "output_freshness_completeness": [],
        },
    }
    value.update(updates)
    return value


def probe_for(job_payload):
    definition = get_cron_job(job_payload["job_name"])
    assert definition is not None
    return AutonomousCronProbe(
        dashboard_provider=lambda: {"jobs": [job_payload]},
        definitions=(definition,),
    )


def test_probe_returns_typed_contracts_and_operator_run_links():
    findings = probe_for(dashboard_job()).probe_job("update_citations", NOW)

    assert {finding.contract for finding in findings} == {
        "scheduler_execution",
        "exit_state",
        "log_signature",
        "lock_ownership_age",
        "durable_data_freshness",
        "throughput_backlog",
        "semantic_correctness",
    }
    assert {finding.state for finding in findings} == {FindingState.HEALTHY}
    assert all(
        finding.operator_url == "/autonomous-operations?operator=cron"
        for finding in findings
    )
    assert all(finding.run_url.endswith("/actions/runs/123") for finding in findings)
    definition = get_cron_job("update_citations")
    assert definition is not None
    assert definition.evidence_contract.durable_data_required is True
    assert definition.evidence_contract.throughput_policy == "no_work_allowed"


def test_declared_schedule_contract_stays_utc_across_dst_boundary():
    definition = get_cron_job("update_citations")
    assert definition is not None
    policy = definition.evidence_contract.schedule_policies[0]

    previous, upcoming = policy.slots(datetime(2026, 3, 8, 2, 0, tzinfo=UTC))

    assert previous.tzinfo is UTC
    assert upcoming.tzinfo is UTC
    assert upcoming > previous


def test_probe_degrades_stale_lock_but_accepts_long_valid_running_job():
    stale = dashboard_job(
        status="stuck",
        is_running=False,
        lock_state={
            "exists": True,
            "held": True,
            "stale": True,
            "age_minutes": 61,
            "probe_status": "held",
        },
    )
    stale_findings = probe_for(stale).probe_job("update_citations", NOW)
    lock = next(
        item for item in stale_findings if item.contract == "lock_ownership_age"
    )
    assert lock.state is FindingState.DEGRADED
    assert lock.evidence["age_minutes"] == 61

    running = dashboard_job(
        status="running",
        is_running=True,
        log_status="running",
        execution_health={
            "status": "running",
            "reason": "within its runtime budget",
            "scheduler": "github_actions",
        },
        lock_state={
            "exists": True,
            "held": True,
            "stale": False,
            "age_minutes": 40,
            "probe_status": "held",
        },
    )
    running_findings = probe_for(running).probe_job("update_citations", NOW)
    assert (
        next(
            item for item in running_findings if item.contract == "lock_ownership_age"
        ).state
        is FindingState.HEALTHY
    )


def test_probe_distinguishes_silent_success_from_unavailable_telemetry():
    silent = dashboard_job(
        status="broken",
        last_db_write="2026-08-28T09:00:00Z",
        output_health={
            "status": "broken",
            "reason": "log succeeded but durable writes and semantic output are stale",
        },
        output_contract_evidence={
            "semantic": {
                "status": "broken",
                "reason": "semantic output is stale",
                "evaluator": "citations",
            }
        },
        db_metrics={"recent_writes": 0, "backlog": 19},
    )
    silent_findings = probe_for(silent).probe_job("update_citations", NOW)
    assert (
        next(
            item
            for item in silent_findings
            if item.contract == "durable_data_freshness"
        ).state
        is FindingState.DEGRADED
    )
    assert (
        next(
            item for item in silent_findings if item.contract == "semantic_correctness"
        ).state
        is FindingState.DEGRADED
    )
    throughput = next(
        item for item in silent_findings if item.contract == "throughput_backlog"
    )
    assert throughput.evidence["data_backlog"] == 19

    unavailable = dashboard_job(
        status="unknown",
        log_status="unknown",
        execution_health={
            "status": "unknown",
            "reason": "scheduler telemetry unavailable",
            "scheduler": "github_actions",
        },
        output_health={"status": "unknown", "reason": "database unavailable"},
        workflow_status={"available": False, "error": "permission denied"},
        db_metrics={"freshness_error": "database freshness unavailable"},
    )
    unavailable_findings = probe_for(unavailable).probe_job("update_citations", NOW)
    assert FindingState.UNKNOWN in {item.state for item in unavailable_findings}
    assert FindingState.DEGRADED not in {item.state for item in unavailable_findings}


def test_probe_recomputes_scheduler_boundary_from_requested_as_of_time():
    probe = probe_for(dashboard_job())

    current = probe.probe_job("update_citations", NOW)
    stale = probe.probe_job(
        "update_citations", datetime(2026, 8, 28, 14, 30, tzinfo=UTC)
    )

    assert (
        next(
            finding for finding in current if finding.contract == "scheduler_execution"
        ).state
        is FindingState.HEALTHY
    )
    assert (
        next(
            finding for finding in stale if finding.contract == "scheduler_execution"
        ).state
        is FindingState.DEGRADED
    )


def test_systemd_exit_state_uses_unit_result_when_file_log_is_unavailable():
    definition = get_cron_job("monitor_chat_operational_alerts")
    assert definition is not None
    payload = dashboard_job(
        job_name=definition.id,
        log_status="unknown",
        systemd_status={"available": True, "service_result": "success"},
    )
    findings = AutonomousCronProbe(
        dashboard_provider=lambda: {"jobs": [payload]},
        definitions=(definition,),
    ).probe_job(definition.id, NOW)

    assert (
        next(finding for finding in findings if finding.contract == "exit_state").state
        is FindingState.HEALTHY
    )


def test_running_runtime_uses_current_scheduler_start_not_prior_log():
    payload = dashboard_job(
        status="running",
        is_running=True,
        log_status="running",
        last_run="2026-08-27T12:00:00Z",
        execution_health={
            "status": "running",
            "reason": "current run is active",
            "scheduler": "github_actions",
            "last_started_at": "2026-08-28T12:05:00Z",
        },
        lock_state={
            "exists": True,
            "held": True,
            "stale": False,
            "age_minutes": 10,
            "probe_status": "held",
        },
    )

    findings = probe_for(payload).probe_job("update_citations", NOW)

    assert (
        next(finding for finding in findings if finding.contract == "exit_state").state
        is FindingState.HEALTHY
    )


def test_daily_audit_covers_four_planes_and_is_reproducible():
    probe = probe_for(dashboard_job())

    first = probe.audit_all_jobs(NOW)
    second = probe.audit_all_jobs(NOW)

    assert first == second
    assert first.mode == "daily"
    assert set(first.plane_counts) == {
        "scheduler",
        "process_logs",
        "durable_data",
        "semantic_outcome",
    }
    assert first.total_jobs == 1
    assert first.degraded == 0
    assert first.unknown == 0


def test_probe_rejects_unknown_job_without_collecting_again():
    calls = 0

    def provider():
        nonlocal calls
        calls += 1
        return {"jobs": []}

    probe = AutonomousCronProbe(dashboard_provider=provider, definitions=())

    try:
        probe.probe_job("not-declared", NOW)
    except KeyError as exc:
        assert "not-declared" in str(exc)
    else:
        raise AssertionError("unknown jobs must fail closed")
    assert calls == 0


def test_strict_snapshot_is_persisted_without_invoking_a_model(tmp_path):
    definition = get_cron_job("update_citations")
    assert definition is not None
    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=lambda _previous: {
            "timestamp": "2026-08-28T12:15:00Z",
            "jobs": [dashboard_job()],
            "manual_operations": [],
            "summary": {},
        },
        now=lambda: NOW,
    )

    snapshot = service.build_autonomous_snapshot(daily=False, definitions=(definition,))

    assert snapshot["mode"] == "strict_15m"
    assert snapshot["total_jobs"] == 1
    assert service.autonomous_snapshot_path.is_file()
    assert "codex" not in service.autonomous_snapshot_path.read_text().lower()
