"""Tests for cron log parsing used by the admin dashboard."""

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.services.cron_health import evaluate_job_health
from backend.services.cron_registry import get_cron_job


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_SCRIPTS = REPO_ROOT / ".github" / "workflows"


def _load_cron_helpers():
    if str(WORKFLOW_SCRIPTS) not in sys.path:
        sys.path.append(str(WORKFLOW_SCRIPTS))
    module_path = WORKFLOW_SCRIPTS / "scripts" / "utils" / "cron_helpers.py"
    spec = importlib.util.spec_from_file_location("cron_helpers_for_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_get_cron_job_status_uses_current_run_start_not_earlier_completion(
    monkeypatch,
):
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990101"
    log_file = logs_dir / f"extract_urls_hourly_{test_date}.log"

    morning = datetime(2099, 1, 1, 8, 8, 0)
    afternoon = datetime(2099, 1, 1, 17, 26, 13)

    log_body = (
        f"{morning.strftime('%Y-%m-%d %H:%M:%S')} - cron.extract_urls_hourly - INFO - "
        "Starting cron job: extract_urls_hourly\n"
        f"{morning.strftime('%Y-%m-%d %H:%M:%S')} - cron.extract_urls_hourly - INFO - "
        "URL Extraction completed successfully\n"
        f"{morning.strftime('%Y-%m-%d %H:%M:%S')} - cron.extract_urls_hourly - INFO - "
        "Cron job completed successfully: extract_urls_hourly\n"
        f"{afternoon.strftime('%Y-%m-%d %H:%M:%S')} - cron.extract_urls_hourly - INFO - "
        "Starting cron job: extract_urls_hourly\n"
    )

    log_file.write_text(log_body, encoding="utf-8")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="root 12345 python -m scripts.hourly.extract_urls_hourly\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        status = cron_helpers.get_cron_job_status("extract_urls_hourly", test_date)
    finally:
        log_file.unlink(missing_ok=True)

    assert status["is_running"] is True
    assert status["status"] == "running"
    assert status["last_run"] == afternoon.strftime("%Y-%m-%d %H:%M:%S")


def test_get_cron_job_status_ignores_untimestamped_failure_before_current_run():
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990102"
    log_file = logs_dir / f"extract_urls_hourly_{test_date}.log"
    morning = "2099-01-02 08:00:00"
    afternoon = "2099-01-02 17:00:00"
    log_file.write_text(
        f"{morning} - Starting cron job: extract_urls_hourly\n"
        "cron job failed: old wrapped failure\n"
        f"{afternoon} - Starting cron job: extract_urls_hourly\n",
        encoding="utf-8",
    )

    running = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="python extract_urls_hourly", stderr=""
    )
    try:
        with patch("subprocess.run", return_value=running):
            status = cron_helpers.get_cron_job_status("extract_urls_hourly", test_date)
    finally:
        log_file.unlink(missing_ok=True)

    assert status["status"] == "running"
    assert status["last_run"] == afternoon


def test_get_cron_job_status_reads_only_a_bounded_log_tail(monkeypatch, tmp_path):
    cron_helpers = _load_cron_helpers()
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    test_date = "20990103"
    log_file = tmp_path / f"bounded_{test_date}.log"
    log_file.write_bytes(
        b"x" * (cron_helpers.MAX_CRON_LOG_READ_BYTES + 128)
        + b"\n2099-01-03 17:00:00 - Starting cron job: bounded\n"
        + b"2099-01-03 17:00:01 - Cron job completed successfully: bounded\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        ),
    )

    status = cron_helpers.get_cron_job_status("bounded", test_date)

    assert status["status"] == "success_no_work"
    assert status["last_run"] == "2099-01-03 17:00:01"


def test_evaluate_job_health_does_not_mark_recent_run_as_stuck():
    job = get_cron_job("extract_urls")
    assert job is not None
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with patch("backend.services.cron_health.is_process_running", return_value=True):
        evaluated = evaluate_job_health(
            job,
            {
                "status": "running",
                "last_run": recent,
                "is_running": True,
                "work_metrics": {},
            },
            db_metrics={
                "last_write": datetime.now(timezone.utc),
                "recent_writes": 10,
            },
            lock_state={"exists": True, "stale": False},
        )
    assert evaluated["status"] == "running"
    assert evaluated["status"] != "stuck"


def test_get_cron_job_status_parses_queue_specific_github_metrics():
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990103"
    log_file = logs_dir / f"github_stars_cron_{test_date}.log"
    log_file.write_text(
        "2099-01-03 08:00:00 - Starting GitHub Stars Update\n"
        '2099-01-03 08:00:01 - GITHUB_STARS_SUMMARY {"fresh_credential": '
        '"PWC_GITHUB_TOKEN", "fresh_selected_groups": 2, '
        '"fresh_successes": 0, "fresh_failures": 2, '
        '"fresh_credential_failures": 2}\n'
        "2099-01-03 08:00:02 - GitHub Stars Update job failed: credential rejected\n",
        encoding="utf-8",
    )

    try:
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        ):
            status = cron_helpers.get_cron_job_status("github_stars_cron", test_date)
    finally:
        log_file.unlink(missing_ok=True)

    assert status["status"] == "failed"
    assert status["work_metrics"]["fresh_credential"] == "PWC_GITHUB_TOKEN"
    assert status["work_metrics"]["fresh_credential_failures"] == 2


def test_get_cron_job_status_parses_daily_curation_summary():
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990105"
    log_file = logs_dir / f"enqueue_hf_daily_paper_curation_{test_date}.log"
    log_file.write_text(
        "2099-01-05 08:00:00 - Starting cron job: enqueue_hf_daily_paper_curation\n"
        '2099-01-05 08:00:01 - HF_DAILY_CURATION_SUMMARY {"created": 2, '
        '"dispatch_enabled": true, "queued": 4}\n'
        "2099-01-05 08:00:02 - Cron job completed successfully: "
        "enqueue_hf_daily_paper_curation\n",
        encoding="utf-8",
    )
    try:
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        ):
            status = cron_helpers.get_cron_job_status(
                "enqueue_hf_daily_paper_curation", test_date
            )
    finally:
        log_file.unlink(missing_ok=True)

    assert status["work_metrics"] == {
        "created": 2,
        "dispatch_enabled": True,
        "queued": 4,
    }


def test_get_cron_job_status_counts_named_paper_groups_as_work():
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990106"
    log_file = logs_dir / f"sync_artificial_analysis_{test_date}.log"
    log_file.write_text(
        "2099-01-06 08:00:00 - Starting cron job: sync_artificial_analysis\n"
        "2099-01-06 08:00:01 - Papers processed: language=60 tts=14\n"
        "2099-01-06 08:00:02 - Cron job completed successfully: "
        "sync_artificial_analysis\n",
        encoding="utf-8",
    )

    try:
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        ):
            status = cron_helpers.get_cron_job_status(
                "sync_artificial_analysis", test_date
            )
    finally:
        log_file.unlink(missing_ok=True)

    assert status["status"] == "success"
    assert status["work_summary"] == "Processed 74 items"
    assert status["work_metrics"] == {
        "papers_processed": 74,
        "language_processed": 60,
        "tts_processed": 14,
    }


def test_timeout_log_is_a_failure_not_a_success():
    cron_helpers = _load_cron_helpers()
    logs_dir = WORKFLOW_SCRIPTS / "scripts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    test_date = "20990104"
    log_file = logs_dir / f"update_citations_hourly_{test_date}.log"
    log_file.write_text(
        "2099-01-04 08:00:00 - Starting cron job: update_citations_hourly\n"
        "2099-01-04 08:45:00 - Job timed out after 2700s\n",
        encoding="utf-8",
    )
    try:
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
        ):
            status = cron_helpers.get_cron_job_status(
                "update_citations_hourly", test_date
            )
    finally:
        log_file.unlink(missing_ok=True)

    assert status["status"] == "failed"
    assert "Job timed out" in status["error"]
