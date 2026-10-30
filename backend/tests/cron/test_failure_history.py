"""Recent launcher failure history and false alarms from quiet or settled work."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.services import cron_health
from backend.services.cron_health import evaluate_job_health, fetch_launcher_history
from backend.services.cron_registry import get_cron_job

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
SYSTEMD_OK = {
    "available": True,
    "enabled": True,
    "timer_active": True,
    "service_result": "success",
    "exec_main_status": 0,
    "last_started_at": "2026-10-17T11:59:00Z",
    "last_completed_at": "2026-10-17T11:59:05Z",
    "service_active": False,
}


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return replace(job, schedule_policies=())


def _record(minutes_ago: int, event: str, job: str, returncode: int = 0) -> str:
    at = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return json.dumps(
        {
            "at": at,
            "event": event,
            "job": job,
            "health_job": job,
            "git_sha": "a" * 40,
            "started_at": at,
            "returncode": returncode,
        }
    )


def _evaluate(job, **kwargs):
    kwargs.setdefault("lock_state", {"exists": False, "held": False})
    kwargs.setdefault("process_running", False)
    kwargs.setdefault("systemd_status", SYSTEMD_OK)
    return evaluate_job_health(
        job, kwargs.pop("log", {"status": "unknown"}), now=NOW, **kwargs
    )


def test_launcher_history_counts_window_streak_and_lock_skips(tmp_path):
    launcher = tmp_path / "launcher.jsonl"
    launcher.write_text(
        "\n".join(
            [
                _record(60 * 30, "exit", "update_github_stars", 1),
                json.dumps({"at": NOW.isoformat(), "job": "update_github_stars"}),
                _record(200, "exit", "update_github_stars", 0),
                _record(120, "exit", "update_github_stars", 1),
                _record(60, "exit", "update_github_stars", 1),
                _record(30, "lock_skipped", "preload_thumbnails"),
                "not json",
            ]
        )
    )

    history = fetch_launcher_history(launcher_path=launcher, now=NOW)

    assert history["update_github_stars"]["runs"] == 3
    assert history["update_github_stars"]["failures"] == 2
    assert history["update_github_stars"]["consecutive_failures"] == 2
    assert history["preload_thumbnails"]["lock_skips"] == 1
    assert history["preload_thumbnails"]["runs"] == 0


def test_launcher_history_keys_lane_jobs_by_dashboard_id(tmp_path):
    launcher = tmp_path / "launcher.jsonl"
    record = json.loads(_record(10, "exit", "sync_mmeb_v2"))
    record["health_job"] = "v2"
    launcher.write_text(json.dumps(record))

    history = fetch_launcher_history(launcher_path=launcher, now=NOW)

    assert history["sync_mmeb_v2"]["runs"] == 1
    assert "v2" not in history


def test_failure_streak_breaks_a_job_that_is_running_now():
    history = {"runs": 11, "failures": 11, "consecutive_failures": 11, "lock_skips": 0}
    result = _evaluate(
        _job("update_github_stars"),
        systemd_status={**SYSTEMD_OK, "service_active": True},
        launcher_history=history,
    )

    assert result["execution_health"]["status"] == "broken"
    assert "last 11 launcher exits failed" in result["execution_health"]["reason"]
    assert result["status"] == "broken"


def test_failures_before_a_latest_success_still_show():
    job = _job("monitor_chat_operational_alerts")
    history = {"runs": 1440, "failures": 557, "consecutive_failures": 0}

    result = _evaluate(job, launcher_history=history)

    assert result["execution_health"]["status"] == "degraded"
    assert "557 of 1440 runs failed" in result["execution_health"]["reason"]
    rare = _evaluate(
        job, launcher_history={"runs": 1440, "failures": 3, "consecutive_failures": 0}
    )
    assert rare["execution_health"]["status"] == "healthy"


def test_lock_skips_degrade_only_jobs_whose_runs_differ():
    history = {"runs": 4, "failures": 0, "consecutive_failures": 0, "lock_skips": 2}

    lanes = _evaluate(_job("preload_thumbnails"), launcher_history=history)
    overlap = _evaluate(_job("process_curation_thumbnails"), launcher_history=history)

    assert lanes["execution_health"]["status"] == "degraded"
    assert "shared lock" in lanes["execution_health"]["reason"]
    assert overlap["execution_health"]["status"] == "healthy"


def test_persistent_execution_ignores_terminal_records(tmp_path):
    launcher = tmp_path / "launcher.jsonl"
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"git_sha": "a" * 40}))
    start = {
        "at": "2026-10-17T11:00:00+00:00",
        "job": "sync_tabarena",
        "health_job": "sync_tabarena",
        "git_sha": "a" * 40,
    }
    launcher.write_text(
        json.dumps(start) + "\n" + _record(30, "exit", "sync_tabarena") + "\n"
    )

    evidence = cron_health.fetch_persistent_execution(
        get_cron_job("sync_tabarena"),
        {"status": "success", "last_run": "2026-10-17T11:10:00Z"},
        launcher_path=launcher,
        manifest_path=manifest,
    )

    assert evidence is not None
    assert evidence["started_at"] == "2026-10-17T11:00:00Z"


def test_idle_curation_thumbnail_queue_ignores_old_failures_and_staleness():
    result = _evaluate(
        _job("process_curation_thumbnails"),
        db_metrics={
            "last_write": NOW - timedelta(hours=5),
            "recent_writes": 0,
            "queued": 0,
            "processing": 0,
            "stale_processing": 0,
            "failed": 0,
        },
    )

    assert result["output_health"]["status"] == "healthy"


def test_citation_rate_limits_need_a_material_share_of_calls():
    job = _job("update_citations")
    log = {
        "status": "success",
        "last_run": NOW - timedelta(minutes=5),
        "work_metrics": {"papers_processed": 1000, "api_calls": 1240},
    }
    db = {"last_write": NOW - timedelta(minutes=5), "recent_writes": 900}

    rare = _evaluate(
        job,
        log={**log, "work_metrics": {**log["work_metrics"], "rate_limit_hits": 5}},
        db_metrics=db,
    )
    heavy = _evaluate(
        job,
        log={**log, "work_metrics": {**log["work_metrics"], "rate_limit_hits": 200}},
        db_metrics=db,
    )

    assert rare["output_health"]["status"] == "healthy"
    assert heavy["output_health"]["status"] == "degraded"


def test_covered_home_feed_makes_quiet_question_warming_healthy():
    job = _job("warm_paper_suggested_questions")
    covered = {
        "last_write": NOW - timedelta(hours=8),
        "recent_writes": 0,
        "visible_papers": 90,
        "visible_missing": 0,
    }

    healthy = _evaluate(job, db_metrics=covered)
    missing = _evaluate(job, db_metrics={**covered, "visible_missing": 12})

    assert healthy["output_health"]["status"] == "healthy"
    assert "every home-feed paper" in healthy["output_health"]["reason"]
    assert missing["output_health"]["status"] == "degraded"
    assert "12 of 90 home-feed papers" in missing["output_health"]["reason"]


def test_x_posts_and_radar_are_judged_on_durable_or_exit_evidence():
    posted = {"last_write": NOW - timedelta(hours=2), "recent_writes": 3}

    paper_posts = _evaluate(_job("post_trending_paper_to_x"), db_metrics=posted)
    insights = _evaluate(_job("post_x_insight"), db_metrics=posted)
    radar = _evaluate(_job("scan_model_releases"))

    assert paper_posts["output_health"]["status"] == "healthy"
    assert insights["output_health"]["status"] == "healthy"
    assert radar["output_health"]["status"] == "healthy"
