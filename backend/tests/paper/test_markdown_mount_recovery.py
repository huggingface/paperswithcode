"""Paper-Markdown mount-failure handling and recovery in the scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call


from backend.tests.paper.markdown_harness import (
    MODULE,
)


def _scheduler(*, execute: bool, confirm: bool, full: bool = True):
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job._prepare_external_pages = lambda: {}
    job.settings = type(
        "Settings",
        (),
        {
            "paper_markdown_backfill_concurrency": 4,
            "paper_markdown_incremental_batch_size": 100,
            "paper_markdown_backfill_batch_size": 100,
            "paper_markdown_hf_bucket_id": "test/paper-markdown",
            "paper_layout_hf_bucket_id": "test/paper-pages",
            "paper_markdown_hf_namespace": "test-owner",
            "paper_markdown_runtime_image": "test-image",
            "paper_markdown_hardware": "l40sx1",
            "paper_markdown_model_id": "test-model",
            "paper_markdown_model_revision": "test-revision",
            "paper_markdown_max_pages": 30,
            "paper_markdown_paid_dispatch_enabled": False,
            "paper_markdown_cost_policy": "metered",
            "hf_token": "test-token",
        },
    )()
    job.full = full
    job.should_execute = execute
    job.confirm = confirm
    job.max_jobs = None
    job.batch_size = None
    job.logger = Mock()
    job.budget_desired_jobs = 0
    job.budget_affordable_jobs = 0
    job.retryable_papers_blocked_by_budget = 0
    job.paid_authorization_required = False
    job.stalled_scheduling_jobs = 0
    job.paid_canary = False
    job.probe_volume = False
    job.recover_mount_failures = False
    job.retry_only = False
    job.budget_projected_usd = None
    job.budget_ceiling_usd = None
    job._remote_jobs = list
    return job


def _remote_job(
    job_id: str,
    *,
    stage: str,
    message: str | None,
    provider_attempt: int = 0,
    run_id: str = "backfill-20260820T030610-65423592",
):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=job_id,
        status=SimpleNamespace(stage=stage, message=message),
        labels={
            "app": "pwc-paper-markdown",
            "mode": "backfill",
            "run_id": run_id,
            "shard_id": "00000",
            "job_type": "ocr",
            "provider_attempt": str(provider_attempt),
        },
        created_at=now - timedelta(hours=1),
        started_at=None,
        finished_at=now - timedelta(minutes=30),
    )


def test_prestart_mount_failure_is_retryable_without_paper_attempt(monkeypatch):
    job = _scheduler(execute=False, confirm=False)
    failure = _remote_job("failed-0", stage="ERROR", message="Volume mount failed")
    job.filesystem = SimpleNamespace(exists=lambda _path: True)
    monkeypatch.setattr(job, "_bucket_json", lambda _key: {})

    candidates, acknowledgement = job._mount_recovery_candidates(
        [failure], now=datetime.now(UTC)
    )

    assert acknowledgement == 0
    assert candidates == [
        {
            "run_id": "backfill-20260820T030610-65423592",
            "shard_id": "00000",
            "manifest_key": (
                "_jobs/manifests/backfill-20260820T030610-65423592/00000.jsonl"
            ),
            "failed_provider_job_id": "failed-0",
            "failed_at": failure.finished_at.isoformat(),
        }
    ]


def test_successful_probe_allows_exactly_one_replacement(monkeypatch):
    job = _scheduler(execute=True, confirm=True)
    candidate = {
        "run_id": "backfill-20260820T030610-65423592",
        "shard_id": "00000",
        "manifest_key": (
            "_jobs/manifests/backfill-20260820T030610-65423592/00000.jsonl"
        ),
        "failed_provider_job_id": "failed-0",
        "failed_at": datetime.now(UTC).isoformat(),
    }
    job._remote_jobs = Mock(return_value=[])
    job._mount_recovery_candidates = Mock(return_value=([candidate], 0))
    job._latest_successful_mount_probe = Mock(
        return_value={"probe_id": "probe-ok", "provider_job_id": "probe-job"}
    )
    job._budget_decision = Mock(return_value={"affordable_jobs": 1})
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="replacement-1"))
    job._persist_dispatch = Mock()

    result = job._recover_mount_failures()

    assert result["launched_replacements"] == 1
    job._run_ocr_job.assert_called_once_with(
        run_id=candidate["run_id"],
        shard_id="00000",
        manifest_key=candidate["manifest_key"],
        provider_attempt=2,
        replacement_for="failed-0",
    )
    assert (
        job._persist_dispatch.call_args.kwargs["provider_attempts"][1][
            "capability_probe_id"
        ]
        == "probe-ok"
    )


def test_two_mount_failures_require_operator_ack_and_late_success_recovers(
    monkeypatch,
):
    job = _scheduler(execute=False, confirm=False)
    first = _remote_job("failed-0", stage="ERROR", message="Volume mount failed")
    second = _remote_job(
        "failed-1",
        stage="ERROR",
        message="Volume mount failed",
        provider_attempt=1,
    )
    candidates, acknowledgement = job._mount_recovery_candidates(
        [first, second], now=datetime.now(UTC)
    )
    assert candidates == []
    assert acknowledgement == 1

    late_success = _remote_job(
        "late-success",
        stage="COMPLETED",
        message=None,
        provider_attempt=1,
    )
    candidates, acknowledgement = job._mount_recovery_candidates(
        [first, late_success], now=datetime.now(UTC)
    )
    assert candidates == []
    assert acknowledgement == 0


def test_mountless_recovery_does_not_require_a_volume_probe():
    job = _scheduler(execute=True, confirm=True)
    job._remote_jobs = Mock(return_value=[])
    job._mount_recovery_candidates = Mock(
        return_value=(
            [
                {
                    "run_id": "backfill-20260820T030610-65423592",
                    "shard_id": "00000",
                    "manifest_key": "manifest.jsonl",
                    "failed_provider_job_id": "failed-0",
                    "failed_at": datetime.now(UTC).isoformat(),
                }
            ],
            0,
        )
    )
    job._budget_decision = Mock(return_value={"affordable_jobs": 1})
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="replacement-1"))
    job._persist_dispatch = Mock()

    result = job._recover_mount_failures()

    assert result["launched_replacements"] == 1
    assert result["storage_transport"] == "bucket_api"


def test_full_reconciliation_recovers_mount_failure_and_fills_remaining_slots():
    job = _scheduler(execute=True, confirm=True)
    job._recover_mount_failures = Mock(
        return_value={
            "operation": "mount_recovery",
            "storage_transport": "bucket_api",
            "launched_replacements": 1,
            "replacement_attempts": [{"provider_job_id": "replacement-1"}],
        }
    )
    job._papers = Mock(return_value=[])
    job._existing_paths = Mock(return_value={})
    job._copy_upstream = Mock(return_value=([], 0))
    job._status_records = Mock(return_value={})
    job._launch = Mock(return_value=[])

    job.run()

    job._recover_mount_failures.assert_called_once_with()
    assert job._papers.call_args_list == [call(), call(recent_only=True)]
    job._launch.assert_called_once_with([], additional_active_job_ids={"replacement-1"})
