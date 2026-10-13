"""Scheduler evidence adapters for GitHub Actions workflows and systemd units."""

from __future__ import annotations

from unittest.mock import patch


from backend.config import get_settings
from backend.services.cron_health import (
    _gh_json,
    fetch_systemd_status,
    fetch_workflow_status,
)
from backend.services.cron_registry import get_cron_job


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return job


def test_gh_json_uses_configured_token_and_explicit_repository(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_TOKEN", "test-github-token")
    get_settings.cache_clear()
    completed = type(
        "CompletedProcess",
        (),
        {"returncode": 0, "stdout": "[]", "stderr": ""},
    )()

    with patch(
        "backend.services.cron_health.subprocess.run", return_value=completed
    ) as run:
        payload, error = _gh_json(["run", "list"])

    assert payload == []
    assert error is None
    command = run.call_args.args[0]
    environment = run.call_args.kwargs["env"]
    assert command == ["gh", "run", "list"]
    assert run.call_args.kwargs["check"] is False
    assert "test-github-token" not in command
    assert environment["GH_TOKEN"] == "test-github-token"
    assert environment["GH_REPO"] == "huggingface/paperswithcode"
    get_settings.cache_clear()


def test_single_job_workflow_does_not_fetch_job_details():
    list_payload = [
        {
            "databaseId": 123,
            "status": "completed",
            "conclusion": "success",
            "updatedAt": "2026-07-28T15:00:00Z",
        }
    ]

    with patch(
        "backend.services.cron_health._gh_json",
        return_value=(list_payload, None),
    ) as gh_json:
        status = fetch_workflow_status(
            "test-single-job.yml",
            expected_jobs=("run",),
        )

    assert status["available"] is True
    assert status["conclusion"] == "success"
    assert status["updated_at"] == "2026-07-28T15:00:00Z"
    assert gh_json.call_count == 2


def test_multi_job_workflow_fetches_job_details():
    list_payload = [
        {
            "databaseId": 456,
            "status": "completed",
            "conclusion": "failure",
        }
    ]
    view_payload = {
        "jobs": [
            {"name": "select", "status": "completed", "conclusion": "success"},
            {"name": "persist", "status": "completed", "conclusion": "failure"},
        ]
    }

    with patch(
        "backend.services.cron_health._gh_json",
        side_effect=[
            (list_payload, None),
            ([], None),
            (view_payload, None),
        ],
    ) as gh_json:
        status = fetch_workflow_status(
            "test-multi-job.yml",
            expected_jobs=("select", "discover", "persist"),
        )

    assert status["failed_jobs"] == ["persist"]
    assert gh_json.call_count == 3


def test_workflow_adapter_errors_are_sanitized():
    with patch(
        "backend.services.cron_health._gh_json",
        return_value=(None, "HTTP 401 token ghp_do_not_serialize"),
    ):
        status = fetch_workflow_status("test-sanitized-error.yml")
    assert status["available"] is False
    assert status["error"] == "GitHub Actions authentication was rejected"
    assert "ghp_do_not_serialize" not in str(status)


def test_systemd_adapter_reads_only_registry_units():
    responses = [
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "UnitFileState=enabled\nActiveState=active\nSubState=waiting\nLastTriggerUSec=Fri 2026-08-14 12:19:00 UTC\nNextElapseUSecRealtime=\nActiveEnterTimestamp=Fri 2026-08-14 08:00:10 UTC\n",
            },
        )(),
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "Result=success\nExecMainStatus=0\nActiveState=inactive\nJob=101665\nExecMainStartTimestamp=Fri 2026-08-14 12:19:00 UTC\nExecMainExitTimestamp=Fri 2026-08-14 12:19:05 UTC\n",
            },
        )(),
        type(
            "Result",
            (),
            {"returncode": 0, "stdout": "JobType=start\nState=waiting\n"},
        )(),
    ]
    job = _job("monitor_chat_operational_alerts")
    with (
        patch(
            "backend.services.cron_health.subprocess.run", side_effect=responses
        ) as run,
        patch(
            "backend.services.cron_health._system_boot_started_at",
            return_value="2026-08-14T08:00:00Z",
        ),
    ):
        status = fetch_systemd_status(job)
    assert status["available"] is True
    assert status["enabled"] is True
    assert status["service_result"] == "success"
    assert status["service_start_queued"] is True
    assert status["boot_started_at"] == "2026-08-14T08:00:00Z"
    assert status["timer_activated_at"] == "Fri 2026-08-14 08:00:10 UTC"
    assert [call.args[0][2] for call in run.call_args_list] == [
        job.systemd_timer,
        job.systemd_service,
        "101665",
    ]


def test_systemd_adapter_does_not_treat_a_stop_job_as_a_queued_start():
    responses = [
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "UnitFileState=enabled\nActiveState=active\nSubState=waiting\n",
            },
        )(),
        type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "Result=success\nExecMainStatus=0\nActiveState=inactive\nJob=42\n",
            },
        )(),
        type(
            "Result",
            (),
            {"returncode": 0, "stdout": "JobType=stop\nState=waiting\n"},
        )(),
    ]
    job = _job("monitor_chat_operational_alerts")
    with (
        patch("backend.services.cron_health.subprocess.run", side_effect=responses),
        patch(
            "backend.services.cron_health._system_boot_started_at",
            return_value="2026-08-14T08:00:00Z",
        ),
    ):
        status = fetch_systemd_status(job)

    assert status["service_start_queued"] is False


def test_multi_unit_adapter_preserves_the_oldest_queued_lane_trigger():
    job = _job("preload_thumbnails")
    common = {
        "available": True,
        "enabled": True,
        "timer_active": True,
        "service_active": False,
        "service_result": "success",
        "exec_main_status": 0,
        "next_trigger_at": None,
        "boot_started_at": "2026-08-14T08:00:00Z",
    }
    statuses = [
        {
            **common,
            "timer": job.systemd_unit_pairs[0][0],
            "service": job.systemd_unit_pairs[0][1],
            "service_start_queued": True,
            "last_trigger_at": "2026-08-14T08:30:00Z",
            "last_started_at": "2026-08-14T07:30:00Z",
            "last_completed_at": "2026-08-14T07:31:00Z",
        },
        *[
            {
                **common,
                "timer": timer,
                "service": service,
                "service_start_queued": False,
                "last_trigger_at": "2026-08-14T12:00:00Z",
                "last_started_at": "2026-08-14T12:00:00Z",
                "last_completed_at": "2026-08-14T12:01:00Z",
            }
            for timer, service in job.systemd_unit_pairs[1:]
        ],
    ]

    with patch("backend.services.cron_health._read_systemd_pair", side_effect=statuses):
        status = fetch_systemd_status(job)

    assert status["service_start_queued"] is True
    assert status["queued_since_at"] == "2026-08-14T08:30:00Z"


def test_systemd_adapter_attaches_persistent_execution_when_boot_lost_timestamps():
    job = _job("mirror_thumbnails_to_disk")
    pair = {
        "available": True,
        "timer": job.systemd_timer,
        "service": job.systemd_service,
        "enabled": True,
        "timer_active": True,
        "service_active": False,
        "last_started_at": None,
        "last_completed_at": None,
        "next_trigger_at": None,
    }
    persistent = {
        "status": "success",
        "started_at": "2026-08-14T05:00:00Z",
        "completed_at": "2026-08-14T05:04:00Z",
        "release_sha": "a" * 40,
        "source": "launcher_and_file_log",
    }
    with (
        patch("backend.services.cron_health._read_systemd_pair", return_value=pair),
        patch(
            "backend.services.cron_health.fetch_persistent_execution",
            return_value=persistent,
        ) as fetch_persistent,
    ):
        status = fetch_systemd_status(job, {"status": "success"})

    assert status["persistent_execution"] == persistent
    fetch_persistent.assert_called_once_with(job, {"status": "success"})
