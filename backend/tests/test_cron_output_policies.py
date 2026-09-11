"""Behavior tests for registry-selected CRON output policies."""

from dataclasses import replace
from datetime import datetime, timezone

from backend.services.cron_health import WORK_METRICS_PROVIDERS, evaluate_job_health
from backend.services.cron_registry import get_cron_job, list_cron_jobs


def _job_with_alias(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return replace(job, id=f"aliased_{job_id}")


def test_registry_owns_specialized_dashboard_evidence_sources():
    jobs = {job.id: job for job in list_cron_jobs()}

    assert jobs["paper_markdown_backfill"].work_metrics_provider == (
        "paper_markdown_monitor"
    )
    assert jobs["monitor_chat_operational_alerts"].work_metrics_provider == (
        "chat_monitor"
    )
    assert jobs["run_chat_synthetic_probe"].work_metrics_provider == ("chat_synthetic")
    assert jobs["review_submissions"].work_metrics_provider == "submission_review"
    assert jobs["mirror_thumbnails_to_disk"].db_metrics_provider == ("thumbnail_cache")
    assert jobs["calculate_paper_trending_scores"].dependency_job_id == (
        "calculate_trending_scores"
    )
    assert {
        job.work_metrics_provider for job in jobs.values() if job.work_metrics_provider
    } <= WORK_METRICS_PROVIDERS.keys()


def test_hot_github_policy_owns_rate_limit_reserve_rule():
    job = _job_with_alias("update_hot_github_trending")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": now,
            "is_running": False,
            "work_metrics": {
                "rate_limit_remaining": 499,
                "rate_limit_reserve": 500,
            },
        },
        db_metrics={
            "last_write": now,
            "recent_writes": 1,
            "hot_repository_count": 1,
            "oldest_eligible_wait_minutes": 0,
            "stale_paper_scores": 0,
            "one_snapshot_over_30m": 0,
        },
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={"available": False},
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "broken"
    assert "reserve violated" in result["output_health"]["reason"]


def test_github_stars_policy_owns_failed_queue_rule():
    job = _job_with_alias("update_github_stars")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": now,
            "is_running": False,
            "work_metrics": {
                "fresh_credential": "PWC_GITHUB_TOKEN",
                "fresh_selected_groups": 2,
                "fresh_successes": 0,
                "fresh_failures": 2,
                "fresh_credential_failures": 2,
            },
        },
        db_metrics={"last_write": now, "recent_writes": 1},
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={"available": False},
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "broken"
    assert "PWC_GITHUB_TOKEN was rejected" in result["output_health"]["reason"]


def test_hot_github_policy_accepts_empty_population_without_fresh_writes():
    job = _job_with_alias("update_hot_github_trending")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": now,
            "is_running": False,
            "work_metrics": {"repositories_processed": 0},
        },
        db_metrics={
            "last_write": None,
            "recent_writes": 0,
            "hot_repository_count": 0,
            "oldest_eligible_wait_minutes": 0,
            "stale_paper_scores": 0,
            "one_snapshot_over_30m": 0,
        },
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={"available": False},
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "healthy"
    assert "no database writes" not in result["output_health"]["reason"]


def test_curation_thumbnail_policy_accepts_successful_empty_queue_poll():
    job = _job_with_alias("process_curation_thumbnails")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False},
        db_metrics={
            "last_write": None,
            "recent_writes": 0,
            "queued": 0,
            "processing": 0,
            "stale_processing": 0,
            "failed": 0,
        },
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_started_at": "2026-08-31T11:59:00Z",
            "last_completed_at": "2026-08-31T11:59:05Z",
            "service_active": False,
        },
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "healthy"
    assert "no thumbnail work is pending" in result["output_health"]["reason"]


def test_paper_trending_policy_owns_dependency_health_rule():
    job = _job_with_alias("calculate_paper_trending_scores")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": now,
            "is_running": False,
            "work_metrics": {"papers_scanned": 10},
        },
        db_metrics={
            "last_write": now,
            "recent_writes": 10,
            "eligible_population": 10,
            "fresh_positive_scores": 10,
        },
        dependency_status="broken",
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={"available": False},
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "degraded"
    assert (
        "dependency calculate_trending_scores is broken"
        in (result["output_health"]["reason"])
    )


def test_generic_policy_does_not_apply_paper_trending_dependency_rule():
    source = _job_with_alias("calculate_paper_trending_scores")
    job = replace(source, output_evaluator="generic")
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    result = evaluate_job_health(
        job,
        {"status": "success", "last_run": now, "is_running": False},
        db_metrics={"last_write": now, "recent_writes": 10},
        dependency_status="broken",
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={"available": False},
        process_running=False,
        now=now,
    )

    assert result["output_health"]["status"] == "healthy"
    assert "calculate_trending_scores" not in result["output_health"]["reason"]
