from __future__ import annotations

import io
import json
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services import paper_markdown_job_monitor as monitor
from backend.services.cron_registry import SchedulePolicy, _SCHEDULE_CONTRACTS


def test_markdown_scheduler_contract_has_only_the_hourly_reconciliation():
    policies, grace = _SCHEDULE_CONTRACTS["paper_markdown_backfill"]

    assert policies == (SchedulePolicy.fixed(60, offset_minutes=17),)
    assert grace == 20


def test_cached_monitor_does_not_trigger_remote_collection(monkeypatch):
    monitor.clear_paper_markdown_job_monitor_cache()
    monkeypatch.setattr(
        monitor,
        "_fetch",
        lambda _settings: (_ for _ in ()).throw(AssertionError("remote fetch")),
    )

    result = monitor.get_cached_paper_markdown_job_monitor()

    assert result == {
        "available": False,
        "jobs": [],
        "summary": {},
        "error": None,
    }


def test_monitor_combines_hf_stage_with_compact_shard_progress(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        paper_markdown_incremental_monthly_budget_usd=100.0,
        paper_markdown_backfill_budget_usd=750.0,
        paper_markdown_cost_policy="unmetered_hf",
    )
    progress = {
        "status": "running",
        "total_papers": 500,
        "processed_papers": 123,
        "succeeded_papers": 120,
        "failed_papers": 3,
        "already_existed_papers": 0,
        "extracted_images": 87,
        "omitted_images": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error_samples": [{"arxiv_id": "2607.00001", "error": "invalid_pdf"}],
    }
    job = SimpleNamespace(
        id="job-123",
        url="https://huggingface.co/jobs/huggingface/job-123",
        status=SimpleNamespace(stage="RUNNING", message=None),
        labels={
            "app": "pwc-paper-markdown",
            "mode": "backfill",
            "run_id": "backfill-20260728T151500-a1b2c3d4",
            "shard_id": "00000",
        },
        flavor=SimpleNamespace(name="l40sx1"),
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        durations=SimpleNamespace(total_secs=240),
    )

    class FakeApi:
        def __init__(self, *, token):
            assert token == "private-token"

        def list_jobs(self, **kwargs):
            assert kwargs["namespace"] == "huggingface"
            assert kwargs["labels"] == {"app": "pwc-paper-markdown"}
            return iter([job])

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert path.endswith(
                "_jobs/progress/backfill-20260728T151500-a1b2c3d4/00000.json"
            )
            assert mode == "rb"
            assert block_size == 0
            return io.BytesIO(json.dumps(progress).encode())

    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monkeypatch.setattr(monitor, "HfApi", FakeApi)
    monkeypatch.setattr(monitor, "HfFileSystem", FakeFileSystem)
    monitor.clear_paper_markdown_job_monitor_cache()

    result = monitor.get_paper_markdown_job_monitor()

    assert result["available"] is True
    assert result["summary"]["active_jobs"] == 1
    assert result["summary"]["processed_papers"] == 123
    assert result["summary"]["extracted_images"] == 87
    assert result["summary"]["omitted_images"] == 2
    assert result["budgets"]["live"]["ceiling_usd"] == 100.0
    assert result["budgets"]["live"]["cost_policy"] == "unmetered_hf"
    assert result["budgets"]["live"]["budget_enforced"] is False
    assert result["budgets"]["backfill"]["ceiling_usd"] == 750.0
    assert result["budgets"]["backfill"]["active_reserved_usd"] == 21.6
    assert result["budgets"]["backfill"]["desired_jobs"] == 3
    assert result["budgets"]["backfill"]["affordable_jobs"] == 3
    assert result["summary"]["paid_execution_authorization_required"] == 0
    assert result["jobs"][0]["stage"] == "RUNNING"
    assert result["jobs"][0]["effective_outcome"] == "active"
    assert result["jobs"][0]["progress"]["failed_papers"] == 3
    assert result["jobs"][0]["progress"]["omitted_images"] == 2
    monitor.clear_paper_markdown_job_monitor_cache()


def test_monitor_reads_remote_progress_with_bounded_concurrency(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        paper_markdown_incremental_monthly_budget_usd=100.0,
        paper_markdown_backfill_budget_usd=750.0,
        paper_markdown_cost_policy="unmetered_hf",
    )
    jobs = [
        SimpleNamespace(
            id=f"job-{shard_id}",
            url=f"https://huggingface.co/jobs/huggingface/job-{shard_id}",
            status=SimpleNamespace(stage="COMPLETED", message=None),
            labels={
                "app": "pwc-paper-markdown",
                "mode": "backfill",
                "run_id": "backfill-20260728T151500-a1b2c3d4",
                "shard_id": f"{shard_id:05d}",
            },
            flavor=SimpleNamespace(name="l40sx1"),
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            durations=SimpleNamespace(total_secs=240),
        )
        for shard_id in range(16)
    ]

    class FakeApi:
        def __init__(self, *, token):
            assert token == "private-token"

        def list_jobs(self, **_kwargs):
            return iter(jobs)

    class FakeFileSystem:
        active = 0
        max_active = 0
        lock = threading.Lock()

        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert mode == "rb"
            assert block_size == 0
            cls = type(self)
            with cls.lock:
                cls.active += 1
                cls.max_active = max(cls.max_active, cls.active)
            time.sleep(0.02)
            with cls.lock:
                cls.active -= 1
            shard_id = path.removesuffix(".json").rsplit("/", 1)[-1]
            progress = {
                "status": "completed",
                "total_papers": 1,
                "processed_papers": 1,
                "succeeded_papers": 1,
                "failed_papers": 0,
                "already_existed_papers": 0,
                "extracted_images": 0,
                "omitted_images": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "shard_id": shard_id,
            }
            return io.BytesIO(json.dumps(progress).encode())

    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monkeypatch.setattr(monitor, "HfApi", FakeApi)
    monkeypatch.setattr(monitor, "HfFileSystem", FakeFileSystem)
    monitor.clear_paper_markdown_job_monitor_cache()

    result = monitor.get_paper_markdown_job_monitor()

    assert result["available"] is True
    assert result["summary"]["processed_papers"] == 16
    assert FakeFileSystem.max_active > 1
    assert FakeFileSystem.max_active <= 8
    monitor.clear_paper_markdown_job_monitor_cache()


def test_monitor_returns_unavailable_when_progress_reads_exceed_deadline(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        paper_markdown_incremental_monthly_budget_usd=100.0,
        paper_markdown_backfill_budget_usd=750.0,
        paper_markdown_cost_policy="unmetered_hf",
    )
    jobs = [
        SimpleNamespace(
            id=f"job-{shard_id}",
            url=f"https://huggingface.co/jobs/huggingface/job-{shard_id}",
            status=SimpleNamespace(stage="RUNNING", message=None),
            labels={
                "app": "pwc-paper-markdown",
                "mode": "backfill",
                "run_id": "backfill-20260728T151500-a1b2c3d4",
                "shard_id": f"{shard_id:05d}",
            },
            flavor=SimpleNamespace(name="l40sx1"),
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            durations=SimpleNamespace(total_secs=240),
        )
        for shard_id in range(2)
    ]

    class FakeApi:
        def __init__(self, *, token):
            assert token == "private-token"

        def list_jobs(self, **_kwargs):
            return iter(jobs)

    class SlowFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, _path, _mode, *, block_size):
            assert block_size == 0
            time.sleep(0.2)
            return io.BytesIO(b"{}")

    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monkeypatch.setattr(monitor, "HfApi", FakeApi)
    monkeypatch.setattr(monitor, "HfFileSystem", SlowFileSystem)
    monkeypatch.setattr(monitor, "_PROGRESS_READ_DEADLINE_SECONDS", 0.02, raising=False)
    monitor.clear_paper_markdown_job_monitor_cache()

    started = time.monotonic()
    result = monitor.get_paper_markdown_job_monitor()
    elapsed = time.monotonic() - started

    assert elapsed < 0.15
    assert result["available"] is False
    assert result["summary"]["progress_evidence_timeouts"] == 2
    assert result["error"] == "progress evidence timed out for 2 recent job(s)"
    monitor.clear_paper_markdown_job_monitor_cache()


def test_complete_checkpoint_is_effective_success_despite_hf_error():
    progress = {
        "status": "completed",
        "total_papers": 100,
        "processed_papers": 100,
    }
    assert monitor._effective_outcome("ERROR", progress) == "success"
    assert (
        monitor._effective_outcome(
            "ERROR", {**progress, "status": "partial", "processed_papers": 80}
        )
        == "interrupted"
    )
    assert monitor._effective_outcome("ERROR", None) == "infrastructure_failure"
    assert (
        monitor._effective_outcome(
            "COMPLETED", {**progress, "status": "failed", "fatal_error": "boom"}
        )
        == "worker_failure"
    )
    assert monitor._failure_cause("interrupted", "Process exited 143", {}) == "exit_143"
    assert (
        monitor._failure_cause("infrastructure_failure", "Volume mount failed", None)
        == "volume_mount"
    )


def test_logical_shard_recovers_mount_failure_without_erasing_provider_attempt():
    attempts = [
        {
            "id": "replacement",
            "run_id": "backfill-20260821T100000-11111111",
            "shard_id": "00000",
            "mode": "backfill",
            "profile_id": "backfill-v1",
            "effective_outcome": "success",
            "failure_cause": None,
            "created_at": "2026-08-21T10:05:00Z",
        },
        {
            "id": "original",
            "run_id": "backfill-20260821T100000-11111111",
            "shard_id": "00000",
            "mode": "backfill",
            "profile_id": "backfill-v1",
            "effective_outcome": "infrastructure_failure",
            "failure_cause": "volume_mount",
            "created_at": "2026-08-21T10:00:00Z",
        },
    ]

    logical = monitor._logical_shards(attempts)

    assert len(logical) == 1
    assert logical[0]["provider_attempts"] == 2
    assert logical[0]["provider_job_ids"] == ["replacement", "original"]
    assert logical[0]["effective_outcome"] == "success"
    assert logical[0]["recovered_mount_failure"] is True
    assert logical[0]["unresolved_mount_failure"] is False


def test_latest_logical_mount_failure_remains_unresolved():
    logical = monitor._logical_shards(
        [
            {
                "id": "failed-replacement",
                "run_id": "backfill-20260821T100000-11111111",
                "shard_id": "00000",
                "mode": "backfill",
                "profile_id": "backfill-v1",
                "effective_outcome": "infrastructure_failure",
                "failure_cause": "volume_mount",
                "created_at": "2026-08-21T10:05:00Z",
            },
            {
                "id": "failed-original",
                "run_id": "backfill-20260821T100000-11111111",
                "shard_id": "00000",
                "mode": "backfill",
                "profile_id": "backfill-v1",
                "effective_outcome": "infrastructure_failure",
                "failure_cause": "volume_mount",
                "created_at": "2026-08-21T10:00:00Z",
            },
        ]
    )

    assert logical[0]["provider_attempts"] == 2
    assert logical[0]["recovered_mount_failure"] is False
    assert logical[0]["unresolved_mount_failure"] is True


def test_efficiency_metrics_exclude_active_shard_progress(monkeypatch):
    settings = SimpleNamespace(
        hf_token="private-token",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        paper_markdown_incremental_monthly_budget_usd=100.0,
        paper_markdown_backfill_budget_usd=750.0,
    )
    now = datetime.now(timezone.utc)

    def job(job_id, stage, duration, run_id):
        return SimpleNamespace(
            id=job_id,
            url=f"https://huggingface.co/jobs/huggingface/{job_id}",
            status=SimpleNamespace(stage=stage, message=None),
            labels={
                "app": "pwc-paper-markdown",
                "mode": "backfill",
                "run_id": run_id,
                "shard_id": "00000",
            },
            flavor=SimpleNamespace(name="l40sx1"),
            created_at=now,
            started_at=now,
            finished_at=now if stage == "COMPLETED" else None,
            durations=SimpleNamespace(total_secs=duration),
        )

    jobs = [
        job("complete", "COMPLETED", 3600, "backfill-20260818T120000-11111111"),
        job("active", "RUNNING", 1800, "backfill-20260818T130000-22222222"),
    ]
    progress = {
        "backfill-20260818T120000-11111111": {
            "status": "completed",
            "total_papers": 10,
            "processed_papers": 10,
            "succeeded_papers": 10,
            "paper_duration_p50_seconds": 100,
            "paper_duration_p95_seconds": 200,
            "updated_at": now.isoformat(),
        },
        "backfill-20260818T130000-22222222": {
            "status": "running",
            "total_papers": 100,
            "processed_papers": 50,
            "succeeded_papers": 50,
            "paper_duration_p50_seconds": 1,
            "paper_duration_p95_seconds": 2,
            "updated_at": now.isoformat(),
        },
    }

    class FakeApi:
        def __init__(self, *, token):
            assert token == "private-token"

        def list_jobs(self, **_kwargs):
            return iter(jobs)

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, _mode, *, block_size):
            assert block_size == 0
            run_id = path.split("/_jobs/progress/", 1)[1].split("/", 1)[0]
            return io.BytesIO(json.dumps(progress[run_id]).encode())

    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monkeypatch.setattr(monitor, "HfApi", FakeApi)
    monkeypatch.setattr(monitor, "HfFileSystem", FakeFileSystem)
    monkeypatch.setattr(monitor, "_coverage_history", lambda _now: {})
    monitor.clear_paper_markdown_job_monitor_cache()

    summary = monitor.get_paper_markdown_job_monitor()["summary"]

    assert summary["succeeded_papers"] == 60
    assert summary["estimated_dollars_per_successful_paper"] == 0.18
    assert summary["papers_per_gpu_hour"] == 10
    assert summary["paper_duration_p50_seconds"] == 100
    assert summary["paper_duration_p95_seconds"] == 200
    monitor.clear_paper_markdown_job_monitor_cache()


def test_coverage_history_reports_seven_day_deltas(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    history = tmp_path / "paper_markdown_coverage.jsonl"
    history.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "observed_at": "2026-08-10T00:00:00+00:00",
                    "scope": "full",
                    "eligible_papers": 100,
                    "canonical_markdown_count": 80,
                    "missing_count": 20,
                    "copied_from_upstream_count": 2,
                    "coverage_percentage": 80,
                },
                {
                    "observed_at": "2026-08-18T00:00:00+00:00",
                    "scope": "full",
                    "eligible_papers": 105,
                    "canonical_markdown_count": 90,
                    "missing_count": 15,
                    "copied_from_upstream_count": 1,
                    "coverage_percentage": 85.71,
                    "retryable_due": 7,
                    "retryable_deferred": 3,
                    "permanent_failures": 2,
                    "attempts_exhausted": 1,
                },
            ]
        )
        + "\n"
    )
    coverage = monitor._coverage_history(datetime(2026, 8, 18, tzinfo=timezone.utc))[
        "full"
    ]
    assert coverage["eligible_delta_7d"] == 5
    assert coverage["canonical_delta_7d"] == 10
    assert coverage["missing_delta_7d"] == -5
    assert monitor._retry_dispositions({"full": coverage}) == {
        "retryable_due": 7,
        "retryable_deferred": 3,
        "permanent_failures": 2,
        "attempts_exhausted": 1,
    }


def test_coverage_history_uses_the_configured_production_log_directory(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PWC_CRON_LOG_DIR", raising=False)
    (tmp_path / "paper_markdown_coverage.jsonl").write_text(
        json.dumps(
            {
                "observed_at": "2026-08-24T10:00:00Z",
                "scope": "recent_14_days",
                "eligible_papers": 507,
                "canonical_markdown_count": 507,
                "missing_count": 0,
                "copied_from_upstream_count": 0,
                "coverage_percentage": 100,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        monitor,
        "get_settings",
        lambda: SimpleNamespace(cron_log_dir=str(tmp_path)),
    )

    coverage = monitor._coverage_history(datetime(2026, 8, 24, 10, tzinfo=timezone.utc))

    assert coverage["recent_14_days"]["canonical_markdown_count"] == 507


def test_monitor_is_unavailable_without_a_token(monkeypatch):
    settings = SimpleNamespace(
        hf_token="",
        paper_markdown_hf_namespace="huggingface",
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
    )
    monkeypatch.setattr(monitor, "get_settings", lambda: settings)
    monitor.clear_paper_markdown_job_monitor_cache()

    result = monitor.get_paper_markdown_job_monitor()

    assert result["available"] is False
    assert result["jobs"] == []
    assert "not configured" in result["error"]
    monitor.clear_paper_markdown_job_monitor_cache()
