from __future__ import annotations

import json

import pytest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from backend.config import get_settings
from backend.services.autonomous_cron_probe import (
    FindingState,
    build_job_findings,
)
from backend.services.cron_health import (
    _persistent_execution_paths,
    evaluate_job_health,
    fetch_persistent_execution,
    fetch_submission_review_output,
    schedule_enabled,
)
from backend.services.cron_registry import get_cron_job


NOW = datetime(2026, 8, 28, 12, 15, tzinfo=UTC)


def test_submission_review_uses_content_free_health_record(monkeypatch, tmp_path):
    record = tmp_path / "autonomous-submission-review-health.json"
    record.write_text(
        json.dumps(
            {
                "status": "healthy",
                "completed_at": "2026-08-28T12:10:00Z",
                "claimed": 3,
                "dry_run": False,
                "remote_launch": True,
            }
        )
    )
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        metrics = fetch_submission_review_output()
    finally:
        get_settings.cache_clear()

    assert metrics == {
        "review_record_available": True,
        "review_status": "healthy",
        "review_completed_at": "2026-08-28T12:10:00Z",
        "submissions_claimed": 3,
        "review_dry_run": False,
        "review_remote_launch": True,
        "review_error_class": None,
    }


def test_systemd_health_record_satisfies_independent_probe_contracts():
    job = get_cron_job("review_submissions")
    assert job is not None
    systemd = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_result": "success",
        "last_started_at": "2026-08-28T12:05:00Z",
        "last_completed_at": "2026-08-28T12:05:10Z",
    }
    evaluated = evaluate_job_health(
        job,
        {
            "status": "unknown",
            "last_run": "2026-08-28T12:05:00Z",
            "is_running": False,
            "work_metrics": {
                "review_record_available": True,
                "review_status": "healthy",
                "review_completed_at": "2026-08-28T12:05:10Z",
                "submissions_claimed": 0,
            },
        },
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status=systemd,
        process_running=False,
        now=NOW,
    )
    findings = build_job_findings(job, evaluated, NOW)

    assert {finding.state for finding in findings} == {FindingState.HEALTHY}
    assert job.evidence_contract.log_source == "health_record"
    assert job.evidence_contract.throughput_source == "health_record"
    assert job.evidence_contract.semantic_source == "health_record"


def test_disabled_submission_review_accepts_an_inactive_timer():
    job = get_cron_job("review_submissions")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {
            "status": "unknown",
            "last_run": None,
            "is_running": False,
            "work_metrics": {"review_record_available": False},
        },
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": False,
            "timer_active": False,
            "service_result": "success",
            "exec_main_status": 0,
        },
        process_running=False,
        schedule_enabled=False,
        now=NOW,
    )

    assert evaluated["execution_health"] == {
        "scheduler": "systemd",
        "last_expected_at": "2026-08-28T12:00:00Z",
        "next_expected_at": "2026-08-28T13:00:00Z",
        "last_started_at": None,
        "last_completed_at": None,
        "status": "healthy",
        "applicable": False,
        "reason": "autonomous submission review is disabled by configuration",
    }
    assert evaluated["output_health"] == {
        "status": "healthy",
        "reason": "output is not applicable while the schedule is disabled",
        "last_verified_at": None,
    }
    assert evaluated["status"] == "healthy"
    findings = build_job_findings(job, evaluated, NOW)
    scheduler = next(
        finding for finding in findings if finding.contract == "scheduler_execution"
    )
    assert scheduler.state is FindingState.HEALTHY
    assert scheduler.summary == "scheduler is intentionally disabled by configuration"


def test_disabled_submission_review_rejects_an_active_timer():
    job = get_cron_job("review_submissions")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_started_at": "2026-08-28T12:05:00Z",
            "last_completed_at": "2026-08-28T12:05:10Z",
        },
        process_running=False,
        schedule_enabled=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "broken"
    assert evaluated["execution_health"]["reason"] == (
        "autonomous submission review timer is active while disabled by configuration"
    )


def test_disabled_submission_review_requires_available_systemd_evidence():
    job = get_cron_job("review_submissions")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={"available": False},
        process_running=False,
        schedule_enabled=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "unknown"
    assert evaluated["execution_health"]["applicable"] is False
    assert evaluated["execution_health"]["reason"] == (
        "cannot verify disabled scheduler state because systemd evidence is unavailable"
    )


def test_submission_schedule_requires_both_feature_flags():
    job = get_cron_job("review_submissions")
    assert job is not None

    assert (
        schedule_enabled(
            job,
            SimpleNamespace(
                autonomous_submission_enabled=True,
                autonomous_submission_jobs_enabled=False,
            ),
        )
        is False
    )
    assert (
        schedule_enabled(
            job,
            SimpleNamespace(
                autonomous_submission_enabled=True,
                autonomous_submission_jobs_enabled=True,
            ),
        )
        is True
    )


def test_pre_reboot_systemd_success_uses_persistent_terminal_evidence():
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_trigger_at": "2026-08-28T05:00:00Z",
            "last_started_at": None,
            "last_completed_at": None,
            "boot_started_at": "2026-08-28T08:00:00Z",
            "persistent_execution": {
                "status": "success",
                "started_at": "2026-08-28T05:00:01Z",
                "completed_at": "2026-08-28T05:04:00Z",
                "release_sha": "a" * 40,
                "source": "launcher_and_file_log",
            },
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "healthy"
    assert evaluated["execution_health"]["last_started_at"] == ("2026-08-28T05:00:01Z")
    assert evaluated["execution_health"]["last_completed_at"] == (
        "2026-08-28T05:04:00Z"
    )
    assert evaluated["execution_health"]["evidence_source"] == ("launcher_and_file_log")


def test_pre_reboot_systemd_slot_without_persistent_evidence_is_unknown():
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_trigger_at": "2026-08-28T05:00:00Z",
            "last_started_at": None,
            "last_completed_at": None,
            "boot_started_at": "2026-08-28T08:00:00Z",
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "unknown"
    assert evaluated["execution_health"]["reason"] == (
        "pre-reboot systemd slot lacks persistent terminal evidence"
    )


def test_pre_reboot_persistent_failure_is_broken():
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "failed", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_trigger_at": "2026-08-28T05:00:00Z",
            "last_started_at": None,
            "last_completed_at": None,
            "boot_started_at": "2026-08-28T08:00:00Z",
            "persistent_execution": {
                "status": "failed",
                "started_at": "2026-08-28T05:00:01Z",
                "completed_at": "2026-08-28T05:04:00Z",
                "release_sha": "a" * 40,
                "source": "launcher_and_file_log",
            },
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "broken"
    assert evaluated["execution_health"]["reason"] == (
        "persistent execution evidence reports failure"
    )


def test_post_reboot_overdue_systemd_slot_is_broken():
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_result": "success",
            "exec_main_status": 0,
            "last_trigger_at": None,
            "last_started_at": None,
            "last_completed_at": None,
            "boot_started_at": "2026-08-28T04:00:00Z",
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "broken"
    assert evaluated["execution_health"]["reason"] == (
        "expected systemd invocation is overdue"
    )


def test_systemd_invocation_queued_behind_a_dependency_is_running():
    job = get_cron_job("calculate_trending_scores")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_active": False,
            "service_start_queued": True,
            "service_result": "success",
            "exec_main_status": 0,
            "queued_since_at": "2026-08-28T11:15:00Z",
            "last_started_at": "2026-08-28T10:15:00Z",
            "last_completed_at": "2026-08-28T10:16:00Z",
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "running"
    assert evaluated["execution_health"]["reason"] == ("systemd start is queued")


def test_systemd_start_cannot_remain_queued_past_its_budget():
    job = get_cron_job("calculate_trending_scores")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_active": False,
            "service_start_queued": True,
            "service_result": "success",
            "exec_main_status": 0,
            "queued_since_at": "2026-08-28T10:00:00Z",
            "last_started_at": "2026-08-28T09:15:00Z",
            "last_completed_at": "2026-08-28T09:16:00Z",
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "stuck"
    assert evaluated["execution_health"]["reason"] == (
        "systemd start remained queued beyond its 70m budget"
    )


def test_systemd_queued_start_without_age_evidence_is_unknown():
    job = get_cron_job("calculate_trending_scores")
    assert job is not None

    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "is_running": False, "work_metrics": {}},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={
            "available": True,
            "enabled": True,
            "timer_active": True,
            "service_active": False,
            "service_start_queued": True,
            "service_result": "success",
            "exec_main_status": 0,
        },
        process_running=False,
        now=NOW,
    )

    assert evaluated["execution_health"]["status"] == "unknown"
    assert evaluated["execution_health"]["reason"] == (
        "systemd start is queued but its queue age is unavailable"
    )


def test_persistent_execution_pairs_exact_release_launch_with_terminal_log(tmp_path):
    launcher = tmp_path / "launcher.jsonl"
    launcher.write_text(
        json.dumps(
            {
                "at": "2026-08-28T05:00:01Z",
                "job": "mirror_thumbnails_to_disk",
                "health_job": "mirror_thumbnails_to_disk",
                "git_sha": "a" * 40,
            }
        )
        + "\n"
    )
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"git_sha": "a" * 40}))
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    evidence = fetch_persistent_execution(
        job,
        {"status": "success", "last_run": "2026-08-28T05:04:00Z"},
        launcher_path=launcher,
        manifest_path=manifest,
    )

    assert evidence == {
        "status": "success",
        "started_at": "2026-08-28T05:00:01Z",
        "completed_at": "2026-08-28T05:04:00Z",
        "release_sha": "a" * 40,
        "source": "launcher_and_file_log",
    }


def test_persistent_execution_rejects_a_launch_from_another_release(tmp_path):
    launcher = tmp_path / "launcher.jsonl"
    launcher.write_text(
        json.dumps(
            {
                "at": "2026-08-28T05:00:01Z",
                "job": "mirror_thumbnails_to_disk",
                "git_sha": "b" * 40,
            }
        )
        + "\n"
    )
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"git_sha": "a" * 40}))
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    assert (
        fetch_persistent_execution(
            job,
            {"status": "success", "last_run": "2026-08-28T05:04:00Z"},
            launcher_path=launcher,
            manifest_path=manifest,
        )
        is None
    )


def test_persistent_execution_does_not_pair_an_old_success_with_a_newer_launch(
    tmp_path,
):
    launcher = tmp_path / "launcher.jsonl"
    launcher.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "at": "2026-08-28T05:00:01Z",
                    "job": "mirror_thumbnails_to_disk",
                    "git_sha": "a" * 40,
                },
                {
                    "at": "2026-08-28T06:00:01Z",
                    "job": "mirror_thumbnails_to_disk",
                    "git_sha": "a" * 40,
                },
            )
        )
        + "\n"
    )
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"git_sha": "a" * 40}))
    job = get_cron_job("mirror_thumbnails_to_disk")
    assert job is not None

    assert (
        fetch_persistent_execution(
            job,
            {"status": "success", "last_run": "2026-08-28T05:04:00Z"},
            launcher_path=launcher,
            manifest_path=manifest,
        )
        is None
    )


def test_submission_schedule_reads_installer_reconciled_state(tmp_path):
    job = get_cron_job("review_submissions")
    assert job is not None
    (tmp_path / "submission-review-schedule.json").write_text(
        json.dumps({"enabled": True})
    )
    assert schedule_enabled(
        job,
        SimpleNamespace(
            cron_log_dir=str(tmp_path),
            autonomous_submission_enabled=False,
            autonomous_submission_jobs_enabled=False,
        ),
    )


def test_persistent_execution_paths_follow_the_active_staging_environment():
    assert _persistent_execution_paths(
        SimpleNamespace(environment="staging", cron_log_dir="/tmp/staging-cron")
    ) == (
        Path("/tmp/staging-cron/launcher.jsonl"),
        Path("/srv/paperswithcode/environments/staging/current/release.json"),
    )


def test_database_telemetry_loss_never_asserts_cross_plane_failures():
    job = get_cron_job("update_citations")
    assert job is not None
    payload = {
        "job_name": job.id,
        "status": "broken",
        "log_status": "success",
        "last_run": "2026-08-28T12:05:00Z",
        "is_running": False,
        "execution_health": {"status": "healthy", "reason": "ran"},
        "output_health": {
            "status": "broken",
            "reason": "database freshness query failed",
        },
        "lock_state": {"exists": False, "held": False, "stale": False},
        "workflow_status": {"available": True, "run_id": 1},
        "db_metrics": {"freshness_error": "database freshness unavailable"},
        "work_metrics": {"papers_processed": 10},
    }

    findings = build_job_findings(job, payload, NOW)
    by_contract = {finding.contract: finding.state for finding in findings}

    assert by_contract["durable_data_freshness"] is FindingState.UNKNOWN
    assert by_contract["throughput_backlog"] is FindingState.UNKNOWN
    assert by_contract["semantic_correctness"] is FindingState.UNKNOWN


def test_trending_semantic_failure_uses_typed_evaluator_outcome():
    job = get_cron_job("calculate_trending_scores")
    assert job is not None
    evaluated = evaluate_job_health(
        job,
        {
            "status": "success",
            "last_run": "2026-08-28T12:16:00Z",
            "is_running": False,
            "work_metrics": {"repositories_processed": 20},
        },
        db_metrics={
            "last_write": NOW,
            "last_write_iso": "2026-08-28T12:15:00Z",
            "recent_writes": 20,
            "eligible_population": 20,
            "fresh_positive_scores": 0,
        },
        lock_state={"exists": False, "held": False, "stale": False},
        workflow_status={
            "available": True,
            "run_id": 4,
            "status": "completed",
            "conclusion": "success",
        },
        process_running=False,
        now=NOW,
    )
    findings = build_job_findings(job, evaluated, NOW)
    by_contract = {finding.contract: finding.state for finding in findings}

    assert by_contract["durable_data_freshness"] is FindingState.HEALTHY
    assert by_contract["throughput_backlog"] is FindingState.HEALTHY
    assert by_contract["semantic_correctness"] is FindingState.DEGRADED


def test_repairable_trending_jobs_use_isolated_runtime_evidence_paths():
    for job_name in ("calculate_trending_scores", "calculate_paper_trending_scores"):
        job = get_cron_job(job_name)
        assert job is not None
        assert job.log_directory == (
            "/var/lib/paperswithcode/production/trending-cron-logs"
        )
        assert job.lock_file == (
            f"/var/lib/paperswithcode/production/trending-cron-locks/{job_name}.lock"
        )


@pytest.mark.parametrize("job_id", ["autonomous_cron_health", "autonomous_cron_audit"])
def test_disabled_cron_operator_has_no_missing_output_findings(job_id):
    job = get_cron_job(job_id)
    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "work_metrics": {}},
        db_metrics={"operator_enabled": False},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={"available": True, "enabled": False, "timer_active": False},
        process_running=False,
        now=NOW,
    )
    assert evaluated["status"] == "healthy"
    assert evaluated["execution_health"]["applicable"] is False
    assert "submission" not in evaluated["execution_health"]["reason"]
    assert all(
        f.state is FindingState.HEALTHY for f in build_job_findings(job, evaluated, NOW)
    )


@pytest.mark.parametrize("operator_enabled", [True, None])
def test_inactive_cron_timer_is_not_implicitly_disabled(operator_enabled):
    job = get_cron_job("autonomous_cron_health")
    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "work_metrics": {}},
        db_metrics={"operator_enabled": operator_enabled},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={"available": True, "enabled": False, "timer_active": False},
        process_running=False,
        now=NOW,
    )
    assert evaluated["execution_health"]["status"] == "broken"


def test_autonomous_cron_units_install_under_registered_names():
    from deploy.install_host_layout import SYSTEMD_UNITS

    root = Path(__file__).resolve().parents[3]
    installer = (root / "deploy/install_deploy_tools.py").read_text()
    for job_id in ("autonomous_cron_health", "autonomous_cron_audit"):
        job = get_cron_job(job_id)
        for unit in (job.systemd_timer, job.systemd_service):
            source = f"autonomous/{unit}"
            assert source in SYSTEMD_UNITS
            assert source in installer
            assert (root / "deploy" / source).is_file()
        assert (
            f"Unit={job.systemd_service}"
            in (root / "deploy/autonomous" / job.systemd_timer).read_text()
        )


@pytest.mark.parametrize("active", ["enabled", "timer_active", "service_active"])
def test_disabled_cron_operator_rejects_active_runtime(active):
    job = get_cron_job("autonomous_cron_health")
    evaluated = evaluate_job_health(
        job,
        {"status": "unknown", "work_metrics": {}},
        db_metrics={"operator_enabled": False},
        lock_state={"exists": False, "held": False, "stale": False},
        systemd_status={"available": True, active: True},
        process_running=False,
        now=NOW,
    )
    assert evaluated["execution_health"]["status"] == "broken"
