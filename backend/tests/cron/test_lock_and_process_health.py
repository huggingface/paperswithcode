"""Lock and running-process evidence in CRON health."""

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


def test_stale_lock_with_fresh_db_is_healthy():
    job = _job("update_github_stars")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(hours=1),
                "last_write_iso": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat(),
                "recent_writes": 10,
            },
            lock_state={
                "exists": True,
                "stale": True,
                "age_minutes": 120,
                "path": "/tmp/github_stars.lock",
            },
        )
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"
    assert evaluated["lock_stale"] is True


def test_stale_lock_with_stale_db_is_broken():
    job = _job("update_github_stars")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
            },
            lock_state={
                "exists": True,
                "stale": True,
                "age_minutes": 120,
                "path": "/tmp/github_stars.lock",
            },
        )
    assert evaluated["status"] == "broken"
    assert evaluated["lock_stale"] is True


def test_running_process_within_expected_runtime():
    job = _job("calculate_trending_scores")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "running",
                "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": True,
                "work_metrics": {},
            },
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=20),
                "recent_writes": 100,
            },
            lock_state={"exists": True, "stale": False},
        )
    assert evaluated["output_health"]["status"] == "running"
    assert evaluated["status"] == "unknown"
