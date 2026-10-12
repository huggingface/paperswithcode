"""Admin CRON dashboard API: summary, freshness, status refresh, and remote job snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app
from backend.services.cron_health import (
    _dashboard_job_summary,
    _normalize_db_metric,
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PWC_ADMIN_API_TOKEN", "test-admin-token")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_dashboard_summary_reports_all_records_and_scheduled_denominator():
    jobs = [
        {"category": "daily", "status": "healthy"},
        {"category": "hourly", "status": "broken"},
        {"category": "manual", "status": "healthy"},
    ]

    summary = _dashboard_job_summary(jobs)

    assert summary["total_jobs"] == 3
    assert summary["scheduled_jobs"] == 2
    assert summary["manual_jobs"] == 1
    assert summary["healthy"] == 1
    assert summary["broken"] == 1
    assert summary["health_score"] == 50


def test_database_freshness_metrics_preserve_bounded_scheduler_state():
    paused_at = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    assert _normalize_db_metric("pause_condition", "daily_token_guardrail") == (
        "daily_token_guardrail"
    )
    assert _normalize_db_metric("paused_at", paused_at) == "2026-08-28T10:00:00Z"
    assert _normalize_db_metric("queued_jobs", 4) == 4


def test_cron_status_requires_admin(client):
    response = client.get("/api/v1/cron/status")
    assert response.status_code == 401


def test_cron_status_accepts_admin_token(client):
    with patch("backend.routers.cron.CronDashboardSnapshotService") as service:
        service.return_value.get_status.return_value = (
            {
                "timestamp": "2026-06-25T12:00:00Z",
                "jobs": [],
                "summary": {
                    "total_jobs": 0,
                    "healthy": 0,
                    "degraded": 0,
                    "broken": 0,
                    "running": 0,
                    "stuck": 0,
                    "unknown": 0,
                    "health_score": 0,
                    "critical_issues": [],
                    "what_to_check_next": "All monitored jobs look healthy",
                },
                "snapshot_generated_at": "2026-06-25T12:00:00Z",
                "snapshot_age_seconds": 0.0,
                "snapshot_stale": False,
                "refreshing": False,
            },
            False,
        )
        response = client.get(
            "/api/v1/cron/status",
            headers={"X-Admin-Token": "test-admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["summary"]["total_jobs"] == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["snapshot_stale"] is False


def test_cron_status_schedules_stale_refresh_and_supports_force(client):
    payload = {
        "timestamp": "2026-06-25T12:00:00Z",
        "jobs": [],
        "summary": {
            "total_jobs": 0,
            "healthy": 0,
            "degraded": 0,
            "broken": 0,
            "running": 0,
            "stuck": 0,
            "unknown": 0,
            "health_score": 0,
            "critical_issues": [],
            "what_to_check_next": "All monitored jobs look healthy",
        },
        "snapshot_generated_at": "2026-06-25T12:00:00Z",
        "snapshot_age_seconds": 61.0,
        "snapshot_stale": True,
        "refreshing": True,
    }
    with patch("backend.routers.cron.CronDashboardSnapshotService") as service:
        service.return_value.get_status.return_value = (payload, True)
        response = client.get(
            "/api/v1/cron/status?force_refresh=true",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert response.status_code == 200
    service.return_value.get_status.assert_called_once_with(force_refresh=True)
    service.return_value.refresh_in_background.assert_called_once()


def test_paper_markdown_jobs_requires_admin(client):
    response = client.get("/api/v1/cron/paper-markdown-jobs")
    assert response.status_code == 401


def test_paper_markdown_jobs_returns_remote_snapshot(client):
    payload = {
        "available": True,
        "namespace": "huggingface",
        "updated_at": "2026-07-28T15:20:00Z",
        "jobs": [{"id": "job-123", "stage": "RUNNING"}],
        "logical_shards": [{"run_id": "run-1", "shard_id": "00000"}],
        "summary": {"active_jobs": 1},
        "selected_profiles": {"live": {"profile_id": "live-v1"}},
        "blockers": {"live": "none"},
        "retry_dispositions": {"retryable_due": 15},
        "error": None,
    }
    with patch(
        "backend.routers.cron.get_paper_markdown_job_monitor",
        return_value=payload,
    ):
        response = client.get(
            "/api/v1/cron/paper-markdown-jobs",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert response.status_code == 200
    assert response.json()["jobs"][0]["id"] == "job-123"
    assert response.json()["summary"]["active_jobs"] == 1
    assert response.json()["logical_shards"][0]["run_id"] == "run-1"
    assert response.json()["selected_profiles"]["live"]["profile_id"] == "live-v1"
    assert response.json()["retry_dispositions"]["retryable_due"] == 15
