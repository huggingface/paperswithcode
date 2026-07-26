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
    sys.path.insert(0, str(WORKFLOW_SCRIPTS))
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
