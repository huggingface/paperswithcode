"""Paper-Markdown repair of existing canonical objects and its dispatch."""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.tests.paper.markdown_harness import (
    MODULE,
    WORKER,
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


def _candidates(count: int):
    return [
        {
            "arxiv_id": f"2607.{index:05d}",
            "version": "v1",
            "title": f"Paper {index}",
            "output_key": f"2607/2607.{index:05d}.md",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize(
    "failure", [None, "changed", "valid_original", "invalid_replacement"]
)
def test_repair_upload_backs_up_original_before_validated_replacement(
    tmp_path, monkeypatch, failure
):
    key = "2607/2607.00000.md"
    original = b"figure caption only"
    replacement = (
        "Title: Paper zero\n\nMarkdown Content:\n\n"
        + "Paper zero explains the proposed method. " * 5
    ).encode()
    if failure == "valid_original":
        original = replacement
    entry = {
        "output_key": key,
        "title": "Paper zero",
        "replace_invalid_sha256": hashlib.sha256(original).hexdigest(),
    }
    remote = {key: original if failure != "changed" else b"concurrently changed"}
    events = []
    store = WORKER.BucketContentStore("test/bucket", "secret", tmp_path)
    store.repairs = {key: entry}
    WORKER.atomic_write(
        tmp_path / key,
        b"bad replacement" if failure == "invalid_replacement" else replacement + b"\n",
    )
    monkeypatch.setattr(store, "existing", lambda keys: set(keys) & remote.keys())
    monkeypatch.setattr(store, "read", lambda path: remote[path])

    def bridge(_token, request):
        for source, destination in request["files"]:
            events.append(destination)
            remote[destination] = Path(source).read_bytes()
        return {}

    monkeypatch.setattr(WORKER, "run_bucket_bridge", bridge)
    if failure:
        with pytest.raises(ValueError):
            store.upload([key])
        assert events == []
    else:
        store.upload([key])
        backup = f"_jobs/repair-originals/{entry['replace_invalid_sha256']}/{key}"
        assert events == [backup, key]
        assert remote[backup] == original
        assert remote[key] == replacement + b"\n"


def test_failed_repair_keeps_existing_canonical_object(tmp_path, monkeypatch):
    entry = _candidates(1)[0]
    original = b"only a figure caption"
    entry["replace_invalid_sha256"] = hashlib.sha256(original).hexdigest()
    output = tmp_path / entry["output_key"]
    WORKER.atomic_write(output, original)
    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfReader=lambda *a, **k: SimpleNamespace(pages=[1])),
    )
    monkeypatch.setattr(WORKER, "download_pdf_for_entry", lambda entry: (b"pdf", "v1"))
    monkeypatch.setattr(WORKER, "run_chandra", lambda *a: ("irrelevant caption", {}))
    with pytest.raises(ValueError, match="semantic_markdown_mismatch"):
        WORKER.process(entry, tmp_path, tmp_path / "run")
    assert output.read_bytes() == original


def test_repair_selection_is_bounded_and_pins_original(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(3)
    job = _scheduler(execute=False, confirm=False, full=False)
    job.repair_invalid_limit = 1
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(
        return_value={item["output_key"]: object() for item in papers}
    )
    job._copy_upstream = Mock()
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(
        return_value={item["output_key"]: "invalid" for item in papers}
    )
    job.filesystem = Mock()
    original = b"figure caption only"
    job.filesystem.open.side_effect = lambda *a, **k: BytesIO(original)
    job._launch = Mock(return_value=[])
    job.run()
    job._copy_upstream.assert_not_called()
    candidates = job._launch.call_args.args[0]
    assert len(candidates) == 1
    assert (
        candidates[0]["replace_invalid_sha256"] == hashlib.sha256(original).hexdigest()
    )


@pytest.mark.parametrize(
    ("full", "retry_only", "missing_status", "expected_repairs", "expected_missing"),
    [
        (False, False, None, 0, 1),
        (False, False, "permanent", 20, 0),
        (False, False, "deferred", 20, 0),
        (True, False, "permanent", 0, 0),
        (False, True, "permanent", 0, 0),
    ],
)
def test_live_repair_fallback_prioritizes_missing_work_and_respects_mode(
    tmp_path,
    monkeypatch,
    full,
    retry_only,
    missing_status,
    expected_repairs,
    expected_missing,
):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(24)
    job = _scheduler(execute=False, confirm=False, full=full)
    job.retry_only = retry_only
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(
        return_value={item["output_key"]: object() for item in papers[1:]}
    )
    job._copy_upstream = Mock(return_value=([papers[0]], 0))
    statuses = {}
    if missing_status:
        statuses[f"_jobs/status/{papers[0]['arxiv_id']}.json"] = {
            "status": "failed",
            "schema_version": 2,
            "retryable": missing_status == "deferred",
            "next_retry_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
    # Exhausted repairs must not be silently resubmitted by the fallback.
    statuses[f"_jobs/status/{papers[1]['arxiv_id']}.json"] = {
        "status": "failed",
        "schema_version": 2,
        "attempt_count": 3,
    }
    job._status_records = Mock(return_value=statuses)
    job._semantic_records = Mock(
        return_value={item["output_key"]: "invalid" for item in papers[1:]}
    )
    job.filesystem = Mock()
    job.filesystem.open.side_effect = lambda *a, **k: BytesIO(b"caption only")
    job._launch = Mock(return_value=[])
    job.run()
    candidates = job._launch.call_args.args[0]
    assert (
        sum(bool(item.get("replace_invalid_sha256")) for item in candidates)
        == expected_repairs
    )
    assert (
        sum(not item.get("replace_invalid_sha256") for item in candidates)
        == expected_missing
    )
    assert papers[1]["arxiv_id"] not in [item["arxiv_id"] for item in candidates]


def test_repair_dispatch_waits_for_existing_remote_worker():
    job = _scheduler(execute=True, confirm=True, full=False)
    job._remote_jobs = Mock(
        return_value=[SimpleNamespace(id="existing", stage="RUNNING")]
    )
    job._active_jobs = Mock(side_effect=lambda jobs: jobs)
    entry = {**_candidates(1)[0], "replace_invalid_sha256": "original-hash"}
    job._budget_decision = Mock()
    assert job._launch([entry]) == []
    job._budget_decision.assert_not_called()
