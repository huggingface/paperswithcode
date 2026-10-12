"""Schedule health: grace windows, scheduled-run precedence, and fail-closed scheduler evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch


from backend.services.cron_health import (
    evaluate_job_health,
)
from backend.services.cron_registry import get_cron_job


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return job


def test_schedule_grace_transitions_are_deterministic():
    job = _job("update_hot_github_trending")
    log = {"status": "success_no_work", "is_running": False, "work_metrics": {}}
    db = {
        "hot_repository_count": 0,
        "recent_writes": 0,
        "oldest_eligible_wait_minutes": 0,
        "stale_paper_scores": 0,
        "one_snapshot_over_30m": 0,
    }
    stale_systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "exec_main_status": 0,
        "last_started_at": "2026-08-14T11:59:50Z",
        "last_completed_at": "2026-08-14T12:00:00Z",
        "next_trigger_at": "2026-08-14T12:30:00Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        during_grace = evaluate_job_health(
            job,
            log,
            db_metrics=db,
            lock_state={"exists": False, "held": False, "stale": False},
            systemd_status=stale_systemd,
            now=datetime(2026, 8, 14, 12, 24, tzinfo=timezone.utc),
        )
        after_grace = evaluate_job_health(
            job,
            log,
            db_metrics=db,
            lock_state={"exists": False, "held": False, "stale": False},
            systemd_status=stale_systemd,
            now=datetime(2026, 8, 14, 12, 26, tzinfo=timezone.utc),
        )
    assert during_grace["execution_health"]["status"] == "degraded"
    assert after_grace["execution_health"]["status"] == "broken"


def test_failed_scheduled_run_wins_over_fresh_manual_recovery_output():
    job = _job("update_hot_github_trending")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    failed_systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "exit-code",
        "exec_main_status": 1,
        "last_started_at": "2026-08-14T12:15:10Z",
        "last_completed_at": "2026-08-14T12:17:00Z",
        "next_trigger_at": "2026-08-14T12:30:00Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={
                "last_write": now,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "oldest_eligible_wait_minutes": 0,
                "stale_paper_scores": 0,
                "one_snapshot_over_30m": 0,
            },
            lock_state={"exists": False, "held": False, "stale": False},
            systemd_status=failed_systemd,
            now=now,
        )
    assert evaluated["execution_health"]["status"] == "broken"
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "broken"


def test_unavailable_scheduler_evidence_fails_closed_to_unknown():
    job = _job("update_citations")
    now = datetime(2026, 8, 14, 12, 40, tzinfo=timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"papers_processed": 10},
            },
            db_metrics={"last_write": now, "recent_writes": 10},
            lock_state={"exists": False, "held": False, "stale": False},
            workflow_status={"available": False, "error": "permission denied"},
            now=now,
        )
    assert evaluated["execution_health"]["status"] == "unknown"
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


def test_systemd_timer_failure_and_success_are_independent_of_output():
    job = _job("monitor_chat_operational_alerts")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    common = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "exec_main_status": 0,
        "last_started_at": "2026-08-14T12:19:00Z",
        "last_completed_at": "2026-08-14T12:19:05Z",
        "next_trigger_at": "2026-08-14T12:20:05Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        healthy = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "healthy",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status=common,
            now=now,
        )
        disabled = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "healthy",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status={**common, "enabled": False},
            now=now,
        )
    assert healthy["status"] == "healthy"
    assert disabled["execution_health"]["status"] == "broken"
    assert disabled["output_health"]["status"] == "healthy"
    assert disabled["status"] == "broken"


def test_successful_workflow_is_health_evidence_without_logs_or_database():
    job = _job("preload_thumbnails")
    now = datetime(2026, 8, 14, 13, 1, tzinfo=timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False},
            db_metrics={},
            workflow_status={
                "available": True,
                "status": "completed",
                "conclusion": "success",
            },
            systemd_status={
                "available": True,
                "enabled": True,
                "timer_active": True,
                "service_result": "success",
                "exec_main_status": 0,
                "last_started_at": "2026-08-14T09:59:50Z",
                "last_completed_at": "2026-08-14T10:00:00Z",
                "next_trigger_at": "2026-08-14T15:00:00Z",
                "service_active": False,
            },
            lock_state={"exists": False, "stale": False},
            now=now,
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["execution_health"]["status"] == "broken"


def test_stale_successful_workflow_cannot_mask_fresh_database_writes():
    job = _job("update_citations")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    stale_completion = datetime.now(timezone.utc) - timedelta(hours=3)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": fresh_time, "is_running": False},
            db_metrics={"last_write": fresh_time, "recent_writes": 10},
            lock_state={"exists": False, "stale": False},
            systemd_status={
                "available": True,
                "enabled": True,
                "timer_active": True,
                "service_result": "success",
                "exec_main_status": 0,
                "last_started_at": stale_completion.isoformat(),
                "last_completed_at": stale_completion.isoformat(),
                "next_trigger_at": None,
                "service_active": False,
            },
        )

    assert evaluated["status"] in {"degraded", "broken"}
    assert evaluated["execution_health"]["status"] in {"degraded", "broken"}
