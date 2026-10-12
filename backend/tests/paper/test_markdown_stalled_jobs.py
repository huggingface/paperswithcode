"""Paper-Markdown handling of remote jobs stalled in scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock


from backend.tests.paper.markdown_harness import (
    MODULE,
)


def _scheduler(*, execute: bool, confirm: bool, full: bool = True):
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job.settings = type(
        "Settings",
        (),
        {
            "paper_markdown_backfill_concurrency": 4,
            "paper_markdown_incremental_batch_size": 100,
            "paper_markdown_backfill_batch_size": 100,
            "paper_markdown_hf_bucket_id": "test/paper-markdown",
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


def _scheduling_job(job_id: str, *, age: timedelta, mode: str = "backfill"):
    return SimpleNamespace(
        id=job_id,
        status=SimpleNamespace(
            stage="SCHEDULING", message="Waiting for requested hardware"
        ),
        labels={"app": "pwc-paper-markdown", "mode": mode},
        created_at=datetime.now(UTC) - age,
    )


def test_stalled_scheduling_jobs_are_cancelled_and_freed_from_slot_accounting():
    job = _scheduler(execute=True, confirm=True, full=True)
    job.api = Mock()
    stalled = _scheduling_job("stalled", age=timedelta(hours=9))
    stalled_live = _scheduling_job("stalled-live", age=timedelta(hours=9), mode="live")
    fresh = _scheduling_job("fresh", age=timedelta(minutes=5))
    running = _remote_job("running", stage="RUNNING", message=None)
    foreign = SimpleNamespace(
        id="foreign",
        status=SimpleNamespace(stage="SCHEDULING", message=None),
        labels={"app": "other"},
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    kept = job._reap_stalled_scheduling(
        [stalled, stalled_live, fresh, running, foreign]
    )
    assert [item.id for item in kept] == ["fresh", "running", "foreign"]
    assert job.stalled_scheduling_jobs == 2
    assert sorted(
        call.kwargs["job_id"] for call in job.api.cancel_job.call_args_list
    ) == ["stalled", "stalled-live"]
    assert all(
        call.kwargs["namespace"] == "test-owner"
        for call in job.api.cancel_job.call_args_list
    )


def test_dry_run_reports_stalled_scheduling_jobs_without_cancelling():
    job = _scheduler(execute=False, confirm=False, full=True)
    job.api = Mock()
    stalled = _scheduling_job("stalled", age=timedelta(hours=2))
    # The dry run previews the execute plan (slot freed) but never cancels.
    assert job._reap_stalled_scheduling([stalled]) == []
    assert job.stalled_scheduling_jobs == 1
    job.api.cancel_job.assert_not_called()


def test_launch_reaps_stalled_scheduling_before_counting_active_slots():
    job = _scheduler(execute=True, confirm=True, full=True)
    job.api = Mock()
    job._remote_jobs = Mock(
        return_value=[_scheduling_job("stalled", age=timedelta(hours=9))]
    )
    seen = {}

    def budget(desired, jobs):
        seen["desired"], seen["jobs"] = desired, jobs
        return {"affordable_jobs": 0}

    job._budget_decision = budget
    assert job._launch([]) == []
    job.api.cancel_job.assert_called_once()
    assert seen["desired"] == 0
    assert seen["jobs"] == []
