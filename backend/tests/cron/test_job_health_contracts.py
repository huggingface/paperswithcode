"""Job-specific CRON output health contracts: writers, no-work rules, backfills, and curation queues."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.services import cron_health
from backend.services.cron_health import (
    _paper_markdown_monitor_snapshot,
    evaluate_job_health,
)
from backend.services.cron_registry import get_cron_job


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return job


def test_chat_monitor_surfaces_dormant_and_undelivered_states():
    job = _job("monitor_chat_operational_alerts")
    now = datetime(2026, 8, 14, 12, 20, tzinfo=timezone.utc)
    systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "exec_main_status": 0,
        "last_started_at": "2026-08-14T12:19:00Z",
        "last_completed_at": "2026-08-14T12:19:05Z",
        "service_active": False,
    }
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        dormant = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "dormant",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 0,
                },
            },
            systemd_status=systemd,
            now=now,
        )
        pending = evaluate_job_health(
            job,
            {
                "status": "unknown",
                "is_running": False,
                "work_metrics": {
                    "monitor_record_available": True,
                    "monitor_status": "degraded",
                    "monitor_completed_at": "2026-08-14T12:19:05Z",
                    "undelivered_alert_events": 2,
                },
            },
            systemd_status=systemd,
            now=now,
        )
    assert dormant["output_health"]["status"] == "healthy"
    assert "dormant" in dormant["output_health"]["reason"]
    assert pending["output_health"]["status"] == "broken"
    assert "2 operational alert" in pending["output_health"]["reason"]


def test_github_stars_health_identifies_failed_fresh_credential():
    job = _job("update_github_stars")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "failed",
                "is_running": False,
                "work_metrics": {
                    "fresh_credential": "PWC_GITHUB_TOKEN",
                    "fresh_selected_groups": 2,
                    "fresh_successes": 0,
                    "fresh_failures": 2,
                    "fresh_credential_failures": 2,
                    "weekly_credential": (
                        "GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE"
                    ),
                    "weekly_selected_groups": 2,
                    "weekly_successes": 2,
                    "weekly_failures": 0,
                    "weekly_credential_failures": 0,
                },
            },
            db_metrics={"last_write": recent, "recent_writes": 2},
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["status"] == "broken"
    assert "PWC_GITHUB_TOKEN was rejected" in evaluated["status_reason"]
    assert "weekly" not in evaluated["status_reason"]


def test_hot_health_allows_recent_no_work_when_population_is_empty():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {"repositories_processed": 0},
            },
            db_metrics={
                "last_write": None,
                "recent_writes": 0,
                "hot_repository_count": 0,
                "one_snapshot_over_30m": 0,
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


def test_hot_zero_seed_does_not_mark_paper_propagation_stale():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {},
            },
            db_metrics={
                "last_write": recent,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "one_snapshot_over_30m": 0,
                # The SQL excludes the repository's one-snapshot 0.0 seed.
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


def test_hot_health_alerts_on_rate_reserve_violation():
    job = _job("update_hot_github_trending")
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent,
                "is_running": False,
                "work_metrics": {
                    "rate_limit_remaining": 499,
                    "rate_limit_reserve": 500,
                },
            },
            db_metrics={
                "last_write": recent,
                "recent_writes": 1,
                "hot_repository_count": 1,
                "one_snapshot_over_30m": 0,
                "stale_paper_scores": 0,
                "oldest_eligible_wait_minutes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert evaluated["status"] == "broken"
    assert "reserve violated" in evaluated["status_reason"]


def test_log_success_with_stale_db_is_broken_for_critical_writer():
    job = _job("calculate_trending_scores")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": "2026-06-25 10:00:00",
                "is_running": False,
                "work_metrics": {"repos_updated": 0, "eligible_population": 45299},
            },
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
                "eligible_population": 45299,
                "fresh_positive_scores": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
        assert evaluated["status"] in {"broken", "degraded"}
        assert evaluated["status"] == "broken"
        assert "eligible population" in evaluated["status_reason"].lower()


def test_success_no_work_allowed_for_fresh_incremental_jobs():
    citations_job = _job("update_citations")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        allowed = evaluate_job_health(
            citations_job,
            {"status": "success_no_work", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=5),
                "recent_writes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert allowed["output_health"]["status"] == "unknown"
    assert allowed["status"] == "unknown"

    trending_job = _job("calculate_trending_scores")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        allowed_trending = evaluate_job_health(
            trending_job,
            {
                "status": "success_no_work",
                "is_running": False,
                "work_metrics": {"eligible_population": 45299},
            },
            db_metrics={
                "last_write": datetime.now(timezone.utc) - timedelta(minutes=30),
                "recent_writes": 100,
                "eligible_population": 45299,
                "fresh_positive_scores": 25,
            },
            lock_state={"exists": False, "stale": False},
        )
    assert allowed_trending["output_health"]["status"] == "healthy"


def test_trending_database_output_is_healthy_without_log_counters():
    job = _job("calculate_paper_trending_scores")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "unknown", "is_running": False, "work_metrics": {}},
            db_metrics={
                "last_write": fresh_time,
                "recent_writes": 2135,
                "eligible_population": 31572,
                "fresh_github_component_scores": 1550,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert "database confirms" in evaluated["output_health"]["reason"]


def test_extract_urls_actions_failure_degrades_fresh_writer():
    job = _job("extract_urls")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 53},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 1200,
            },
            lock_state={"exists": False, "stale": False},
            workflow_status={
                "available": True,
                "workflow_file": "cron-extract-urls.yml",
                "run_id": 123,
                "status": "completed",
                "conclusion": "failure",
                "failed_jobs": ["persist"],
            },
        )
    assert evaluated["status"] == "healthy"
    assert evaluated["execution_health"]["scheduler"] == "manual"


def test_extract_urls_actions_unavailable_degrades_fresh_db():
    job = _job("extract_urls")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 53},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 1200,
            },
            lock_state={"exists": False, "stale": False},
            workflow_status={
                "available": False,
                "workflow_file": "cron-extract-urls.yml",
                "error": "gh is not authenticated",
            },
        )
    assert evaluated["status"] == "healthy"
    assert evaluated["workflow_status"]["available"] is False


def test_import_hf_daily_papers_recent_log_is_healthy_without_false_db_provenance():
    job = _job("import_hf_daily_papers")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=9)
    recent_log_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent_log_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 0},
            },
            db_metrics={
                "last_write": stale_time,
                "last_write_iso": stale_time.isoformat(),
                "recent_writes": 0,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"
    assert job.db_freshness_query is None


def test_import_hf_daily_papers_failed_counter_is_broken_even_after_success():
    job = _job("import_hf_daily_papers")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {
                    "upstream_fetch_succeeded": True,
                    "fetched": 12,
                    "inserted": 4,
                    "updated": 7,
                    "failed": 1,
                },
            },
        )

    assert evaluated["output_health"]["status"] == "broken"

    assert "1 imported paper" in evaluated["output_health"]["reason"]


def test_recent_weekly_task_keyword_log_is_healthy_without_db_timestamp():
    job = _job("link_papers_by_task_keywords")
    recent_log_time = datetime.now(timezone.utc) - timedelta(days=6)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": recent_log_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 100},
            },
            db_metrics={},
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


def test_hf_artifacts_fresh_db_metrics_are_healthy():
    job = _job("update_hf_artifacts")
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": fresh_time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_running": False,
                "work_metrics": {"papers_processed": 50},
            },
            db_metrics={
                "last_write": fresh_time,
                "last_write_iso": fresh_time.isoformat(),
                "recent_writes": 30,
                "papers_scanned": 50,
                "links_created": 2,
            },
            lock_state={"exists": False, "stale": False},
        )

    assert evaluated["output_health"]["status"] == "healthy"
    assert evaluated["status"] == "unknown"


@pytest.mark.parametrize(
    ("metrics", "expected", "reason"),
    [
        (
            {"budget_exhausted": True, "missing_after_upstream": 25},
            "degraded",
            "budget is exhausted",
        ),
        (
            {"terminal_shard_failures": 2},
            "broken",
            "remote OCR shard",
        ),
        (
            {"oldest_active_checkpoint_age_minutes": 45},
            "broken",
            "checkpoint is stale",
        ),
        (
            {"interrupted_shards": 1},
            "degraded",
            "partial progress",
        ),
        (
            {
                "unresolved_mount_failures": 1,
                "blocker_classification": "reliability",
            },
            "broken",
            "unresolved volume mount failure",
        ),
        (
            {
                "paid_authorization_required": True,
                "missing_after_upstream": 15,
            },
            "degraded",
            "awaits explicit paid execution authorization",
        ),
        (
            {"semantic_invalid_existing": 3},
            "broken",
            "semantic-invalid existing",
        ),
        (
            {"semantic_validation_failures": 2},
            "broken",
            "semantic validation",
        ),
        (
            {"semantic_evidence_unavailable": 4},
            "unknown",
            "semantic evidence is unavailable",
        ),
    ],
)
def test_paper_markdown_semantic_contract(metrics, expected, reason):
    job = _job("paper_markdown_backfill")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": datetime.now(timezone.utc),
                "is_running": False,
                "work_metrics": metrics,
            },
        )
    assert evaluated["output_health"]["status"] == expected
    assert reason in evaluated["output_health"]["reason"]


def test_paper_markdown_monitor_snapshot_refreshes_only_a_cold_cache():
    fresh = {
        "available": True,
        "updated_at": "2026-08-18T23:00:00Z",
        "summary": {"active_jobs": 1},
    }
    with (
        patch(
            "backend.services.paper_markdown_job_monitor.get_cached_paper_markdown_job_monitor",
            return_value={"available": False, "jobs": [], "summary": {}, "error": None},
        ),
        patch(
            "backend.services.paper_markdown_job_monitor.get_paper_markdown_job_monitor",
            return_value=fresh,
        ) as refresh,
    ):
        assert _paper_markdown_monitor_snapshot() == fresh
        refresh.assert_called_once_with()

    cached = {**fresh, "summary": {"active_jobs": 2}}
    with (
        patch(
            "backend.services.paper_markdown_job_monitor.get_cached_paper_markdown_job_monitor",
            return_value=cached,
        ),
        patch(
            "backend.services.paper_markdown_job_monitor.get_paper_markdown_job_monitor"
        ) as refresh,
    ):
        assert _paper_markdown_monitor_snapshot() == cached
        refresh.assert_not_called()


def test_partial_remote_monitor_evidence_preserves_confirmed_shard_failures():
    merge_remote_metrics = getattr(
        cron_health,
        "_merge_paper_markdown_monitor_metrics",
        None,
    )
    assert merge_remote_metrics is not None

    metrics = merge_remote_metrics(
        {"mode": "live"},
        {
            "available": False,
            "summary": {
                "progress_evidence_timeouts": 1,
                "latest_run_failed_jobs": 1,
                "latest_run_interrupted_jobs": 0,
                "oldest_active_checkpoint_age_minutes": 0,
                "unresolved_mount_failures": 1,
                "recovered_mount_failures": 0,
            },
            "budgets": {},
            "blockers": {},
        },
    )

    assert metrics["remote_monitor_available"] is False
    assert metrics["remote_progress_evidence_timeouts"] == 1
    assert metrics["terminal_shard_failures"] == 1
    assert metrics["unresolved_mount_failures"] == 1
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            _job("paper_markdown_backfill"),
            {
                "status": "success",
                "last_run": datetime.now(timezone.utc),
                "is_running": False,
                "work_metrics": metrics,
            },
        )
    assert evaluated["output_health"]["status"] == "broken"

    preserved = merge_remote_metrics(
        {
            "terminal_shard_failures": 2,
            "unresolved_mount_failures": 1,
        },
        {"available": False, "summary": {}, "budgets": {}, "blockers": {}},
    )
    assert preserved["terminal_shard_failures"] == 2
    assert preserved["unresolved_mount_failures"] == 1


def test_embedding_no_work_is_broken_when_eligible_rows_are_missing():
    job = _job("refresh_paper_embeddings")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"candidates": 0, "embeddings_updated": 0},
            },
            db_metrics={"last_write": now, "recent_writes": 0, "missing_embeddings": 8},
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "8 eligible embeddings" in evaluated["output_health"]["reason"]


def test_embedding_no_work_is_broken_when_content_hashes_are_stale():
    job = _job("refresh_paper_embeddings")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success_no_work",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"candidates": 0, "embeddings_updated": 0},
            },
            db_metrics={
                "last_write": now,
                "recent_writes": 0,
                "missing_embeddings": 0,
                "content_hash_mismatches": 3,
            },
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "3 active-generation content hashes" in evaluated["output_health"]["reason"]


def test_backfill_contract_separates_stale_run_and_provider_throttling():
    job = _job("backfill_method_references")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"provider_rate_limit_hits": 3},
            },
            db_metrics={"last_write": now, "recent_writes": 1, "stale_running": 1},
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "stale database run" in evaluated["output_health"]["reason"]
    assert "provider throttled" in evaluated["output_health"]["reason"]


def test_method_keyword_backfill_fresh_checkpoint_is_resumable_not_stale():
    job = _job("backfill_method_keywords")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={
                "last_write": now,
                "recent_writes": 1,
                "running_runs": 1,
                "stale_running": 0,
                "checkpoint_age_minutes": 90,
                "resume_cursor": 1234,
            },
        )
    assert evaluated["output_health"]["status"] == "healthy"
    assert "resumable checkpoint" in evaluated["output_health"]["reason"]


def test_daily_curation_pause_condition_is_broken():
    job = _job("enqueue_hf_daily_paper_curation")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={
                "last_write": now,
                "dispatch_enabled": False,
                "pause_condition": "daily_token_guardrail",
            },
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "daily_token_guardrail" in evaluated["output_health"]["reason"]


def test_daily_curation_old_queue_age_is_unhealthy():
    job = _job("enqueue_hf_daily_paper_curation")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={
                "last_write": now,
                "queued_jobs": 2,
                "oldest_queued_age_minutes": 360,
            },
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "queued curation job" in evaluated["output_health"]["reason"]


@pytest.mark.parametrize(
    "job_id", ["enqueue_hf_daily_paper_curation", "enqueue_hf_trending_model_curation"]
)
def test_daily_curation_partial_workflow_is_broken(job_id):
    job = _job(job_id)
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {"status": "success", "last_run": now, "is_running": False},
            db_metrics={"last_write": now, "partial_workflows": 1},
        )
    assert evaluated["output_health"]["status"] == "broken"
    assert "partial workflow" in evaluated["output_health"]["reason"]


def test_trending_curation_failed_resolution_overrides_fresh_discovery():
    now = datetime.now(timezone.utc)
    evaluated = evaluate_job_health(
        _job("enqueue_hf_trending_model_curation"),
        {"status": "success_no_work", "last_run": now, "is_running": False},
        db_metrics={"last_write": now, "failed": 2},
        process_running=False,
        lock_state={},
    )
    assert evaluated["output_health"]["status"] == "broken"
    assert (
        "2 model resolution candidate(s) failed" in evaluated["output_health"]["reason"]
    )


def test_managed_organization_snapshot_gap_degrades_output():
    job = _job("calculate_organization_trending_scores")
    now = datetime.now(timezone.utc)
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "last_run": now,
                "is_running": False,
                "work_metrics": {"papers_processed": 23},
            },
            db_metrics={
                "last_write": now,
                "recent_writes": 23,
                "featured_organizations": 24,
                "missing_today_snapshots": 1,
            },
        )
    assert evaluated["output_health"]["status"] == "degraded"
    assert "managed organization" in evaluated["output_health"]["reason"]


def test_thumbnail_preload_bounded_failures_degrade_output():
    job = _job("preload_thumbnails")
    with patch("backend.services.cron_health.is_process_running", return_value=False):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "success",
                "is_running": False,
                "work_metrics": {"failed_downloads": 2},
            },
            workflow_status={
                "available": True,
                "status": "completed",
                "conclusion": "success",
            },
        )
    assert evaluated["output_health"]["status"] == "degraded"
    assert "thumbnail download" in evaluated["output_health"]["reason"]
