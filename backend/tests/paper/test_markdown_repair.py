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
    job._prepare_external_pages = lambda: {}
    job._fresh_paper_keys = set
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
        + "Paper zero explains the proposed method. " * 60
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
    monkeypatch.setattr(
        WORKER, "run_chandra", lambda *a: ("irrelevant caption", {}, [])
    )
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


def _planned_candidates(monkeypatch, job, candidates):
    planned = []
    chunks = MODULE.chunks

    def record(items, size):
        planned.extend(items)
        return chunks(items, size)

    monkeypatch.setattr(MODULE, "chunks", record)
    job._budget_decision = Mock(return_value={"affordable_jobs": 0})
    job._launch(candidates)
    return [item["arxiv_id"] for item in planned]


def test_repair_dispatches_beside_workers_with_readable_manifests(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job._remote_jobs = Mock(
        return_value=[SimpleNamespace(id="existing", stage="RUNNING")]
    )
    job._active_jobs = Mock(side_effect=lambda jobs: jobs)
    busy, repair = _candidates(2)
    repair["replace_invalid_sha256"] = "original-hash"
    job._busy_paper_keys = Mock(return_value=({MODULE.entry_paper_key(busy)}, True))

    assert _planned_candidates(monkeypatch, job, [busy, repair]) == [repair["arxiv_id"]]


def test_unreadable_active_manifest_defers_only_repairs(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job._remote_jobs = Mock(
        return_value=[SimpleNamespace(id="existing", stage="RUNNING")]
    )
    job._active_jobs = Mock(side_effect=lambda jobs: jobs)
    missing, repair = _candidates(2)
    repair["replace_invalid_sha256"] = "original-hash"
    job._busy_paper_keys = Mock(return_value=(set(), False))

    assert _planned_candidates(monkeypatch, job, [missing, repair]) == [
        missing["arxiv_id"]
    ]


def test_busy_keys_report_unreadable_active_manifests():
    job = _scheduler(execute=False, confirm=False)
    job.filesystem = Mock()
    job.filesystem.open.side_effect = OSError("unavailable")
    running = SimpleNamespace(
        id="ocr",
        stage="RUNNING",
        labels={"job_type": "ocr", "run_id": "live-1", "shard_id": "00000"},
    )

    assert job._busy_paper_keys([running]) == (set(), False)
    assert job._busy_paper_keys([]) == (set(), True)


def test_full_lane_repairs_small_invalid_objects_outside_the_live_window(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(26)
    fresh, recent, large, small = papers[:1], papers[1:2], papers[2:3], papers[3:]
    job = _scheduler(execute=False, confirm=False, full=True)
    job._papers = Mock(
        side_effect=lambda *, recent_only=False: (
            fresh + recent if recent_only else papers
        )
    )
    sizes = {item["output_key"]: 300 for item in recent + small}
    sizes[large[0]["output_key"]] = MODULE.STUB_SCAN_BYTES
    job._existing_paths = Mock(
        return_value={key: SimpleNamespace(size=size) for key, size in sizes.items()}
    )
    # A paper still missing inside the live window belongs to the live lane and
    # must not hold back full-lane repairs.
    job._copy_upstream = Mock(return_value=(fresh, 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(
        side_effect=lambda inspected, _canonical: {
            item["output_key"]: "invalid" for item in inspected
        }
    )
    job.filesystem = Mock()
    job.filesystem.open.side_effect = lambda *a, **k: BytesIO(b"Title: f7.svg")
    job._launch = Mock(return_value=[])
    job.run()

    inspected = job._semantic_records.call_args.args[0]
    assert [item["arxiv_id"] for item in inspected] == [
        item["arxiv_id"] for item in fresh + recent + small
    ]
    candidates = [
        item for item in job._launch.call_args.args[0] if not item.get("layout_only")
    ]
    # Bounded, and the live lane alone repairs the recent window.
    assert len(candidates) == MODULE.LIVE_REPAIR_LIMIT
    assert {item["arxiv_id"] for item in candidates} <= {
        item["arxiv_id"] for item in small
    }
    assert all(item["replace_invalid_sha256"] for item in candidates)
