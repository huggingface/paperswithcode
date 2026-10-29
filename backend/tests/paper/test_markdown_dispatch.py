"""Paper-Markdown scheduler dispatch: budget gates, launch requests, external PDF archival, and retries."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, call

import httpx
import pytest

from backend.tests.paper.markdown_harness import (
    MODULE,
    WORKFLOWS,
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


def _external_candidate():
    return {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "External report",
        "source_url": "https://huggingface.co/acme/report/resolve/main/report.pdf",
        "pdf_url": "https://huggingface.co/acme/report/resolve/main/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }


def test_paid_dispatch_requires_confirmation(monkeypatch):
    job = _scheduler(execute=True, confirm=False, full=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    with pytest.raises(ValueError, match="requires --confirm"):
        job._launch(_candidates(1))


def test_budget_exhaustion_is_a_successful_noop(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    monkeypatch.setattr(
        job, "_budget_decision", lambda _desired, _jobs: {"affordable_jobs": 0}
    )
    assert job._launch(_candidates(1)) == []


def test_measured_profile_paid_dispatch_requires_explicit_gate(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)

    def budget_decision(desired, _jobs):
        job.budget_desired_jobs = desired
        job.budget_affordable_jobs = desired
        return {"affordable_jobs": desired}

    monkeypatch.setattr(
        job,
        "_budget_decision",
        budget_decision,
    )

    assert job._launch(_candidates(1)) == []
    assert job.paid_authorization_required is True
    job.logger.info.assert_called_with(
        "paper Markdown admission: desired=%s affordable=%s planned_or_launched=0",
        1,
        1,
    )


def test_launch_request_uses_the_shared_profile_and_bucket_api_contract():
    job = _scheduler(execute=True, confirm=True, full=False)
    job.api = Mock()
    job.api.run_uv_job.return_value = SimpleNamespace(id="job-1")

    job._run_ocr_job(
        run_id="live-20260821T120000-12345678",
        shard_id="00000",
        manifest_key="_jobs/manifests/live/00000.jsonl",
        provider_attempt=1,
    )

    kwargs = job.api.run_uv_job.call_args.kwargs
    assert kwargs["timeout"] == job.profile.hard_timeout == "7h"
    assert kwargs["script_args"][-1] == str(job.profile.soft_deadline_seconds)
    assert kwargs["labels"]["profile_id"] == job.profile.profile_id
    assert kwargs["labels"]["hard_timeout_seconds"] == str(
        job.profile.hard_timeout_seconds
    )
    assert kwargs["volumes"] == []
    assert kwargs["script_args"][:4] == [
        "--bucket-id",
        "test/paper-markdown",
        "--manifest-key",
        "_jobs/manifests/live/00000.jsonl",
    ]


def test_external_pdf_is_validated_and_archived_before_remote_launch(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(return_value={})
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    download = Mock(return_value=b"%PDF-valid")
    monkeypatch.setattr(MODULE, "download_external_pdf", download, raising=False)
    document = Mock()
    document.__enter__ = Mock(return_value=SimpleNamespace(page_count=2))
    document.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(MODULE.pymupdf, "open", Mock(return_value=document))

    job._launch([_external_candidate()])

    assert job.api.batch_bucket_files.call_args_list[0] == call(
        "test/paper-markdown",
        add=[(b"%PDF-valid", "external/109743/paper.pdf")],
        token="test-token",
    )
    MODULE.pymupdf.open.assert_called_once_with(stream=b"%PDF-valid", filetype="pdf")
    download.assert_called_once_with(
        "https://huggingface.co/acme/report/resolve/main/report.pdf",
        timeout_seconds=30,
        max_elapsed_seconds=30,
    )
    assert (
        job.api.batch_bucket_files.call_args_list[1]
        .kwargs["add"][0][1]
        .endswith("/00000.jsonl")
    )
    job._run_ocr_job.assert_called_once()


def test_external_pdf_archive_is_reused_without_downloading(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(
        return_value={"external/109743/paper.pdf": SimpleNamespace(size=123)}
    )
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    download = Mock(side_effect=AssertionError("archived PDF must be reused"))
    monkeypatch.setattr(MODULE, "download_external_pdf", download)

    job._launch([_external_candidate()])

    download.assert_not_called()
    assert job.api.batch_bucket_files.call_count == 1
    job._run_ocr_job.assert_called_once()


def test_external_pdf_archival_is_bounded_per_scheduler_run(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(return_value={})
    monkeypatch.setattr(MODULE, "EXTERNAL_PDF_ARCHIVE_LIMIT", 1)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    download = Mock(return_value=b"%PDF-valid")
    monkeypatch.setattr(MODULE, "download_external_pdf", download)
    document = Mock()
    document.__enter__ = Mock(return_value=SimpleNamespace(page_count=1))
    document.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(MODULE.pymupdf, "open", Mock(return_value=document))
    second = {
        **_external_candidate(),
        "paper_key": "external/109744",
        "paper_id": "109744",
        "pdf_key": "external/109744/paper.pdf",
        "output_key": "external/109744.md",
    }

    launched = job._launch([_external_candidate(), second])

    assert len(launched) == 1
    assert download.call_count == 1
    manifest = job.api.batch_bucket_files.call_args_list[-1].kwargs["add"][0][0]
    assert b"external/109743" in manifest
    assert b"external/109744" not in manifest


def test_external_pdf_is_not_archived_during_dry_run(monkeypatch):
    job = _scheduler(execute=False, confirm=False, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._existing_paths = Mock()
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    download = Mock(side_effect=AssertionError("dry run must not download PDFs"))
    monkeypatch.setattr(MODULE, "download_external_pdf", download)

    launched = job._launch([_external_candidate()])

    assert launched[0]["mode"] == "dry_run"
    download.assert_not_called()
    job._existing_paths.assert_not_called()
    job.api.batch_bucket_files.assert_not_called()


@pytest.mark.parametrize("http_status", [None, 404])
def test_invalid_external_pdf_is_not_archived_or_dispatched(monkeypatch, http_status):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(return_value={})
    job._bucket_json = Mock(return_value={})
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    monkeypatch.setattr(
        MODULE,
        "download_external_pdf",
        lambda _url, **_kwargs: b"%PDF-broken",
        raising=False,
    )
    monkeypatch.setattr(
        MODULE.pymupdf,
        "open",
        Mock(side_effect=ValueError("broken PDF structure")),
    )

    if http_status is not None:
        response = httpx.Response(
            http_status, request=httpx.Request("GET", "https://example.com/paper.pdf")
        )
        monkeypatch.setattr(
            MODULE,
            "download_external_pdf",
            Mock(
                side_effect=httpx.HTTPStatusError(
                    "missing PDF", request=response.request, response=response
                )
            ),
        )

    launched = job._launch([_external_candidate()])

    assert launched == []
    status_upload = job.api.batch_bucket_files.call_args.kwargs["add"][0]
    assert status_upload[1] == "_jobs/status/external/109743.json"
    status = json.loads(status_upload[0])
    assert status["status"] == "failed"
    assert status["error"] == (
        "broken PDF structure" if http_status is None else "missing PDF"
    )
    assert status["retryable"] is False
    assert MODULE.status_disposition(status) == "permanent_failure"
    job._run_ocr_job.assert_not_called()


def test_invalid_external_pdf_does_not_block_other_papers(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.batch_size = 1
    job.max_jobs = 1
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(return_value={})
    job._bucket_json = Mock(return_value={})
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    monkeypatch.setattr(
        MODULE, "download_external_pdf", Mock(side_effect=ValueError("invalid_pdf"))
    )

    launched = job._launch([_external_candidate(), _candidates(1)[0]])

    assert len(launched) == 1
    manifest = job.api.batch_bucket_files.call_args_list[-1].kwargs["add"][0][0]
    assert b"external/109743" not in manifest
    assert b"2607.00000" in manifest
    job._run_ocr_job.assert_called_once()


def test_external_pdf_upload_failure_does_not_block_other_papers(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.batch_size = 1
    job.max_jobs = 1
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))
    job._existing_paths = Mock(return_value={})
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    monkeypatch.setattr(MODULE, "download_external_pdf", Mock(return_value=b"%PDF"))
    document = Mock()
    document.__enter__ = Mock(return_value=SimpleNamespace(page_count=1))
    document.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(MODULE.pymupdf, "open", Mock(return_value=document))

    def upload(_bucket, *, add, **_kwargs):
        if add[0][1].endswith("/paper.pdf"):
            raise OSError("bucket unavailable")

    job.api.batch_bucket_files.side_effect = upload

    launched = job._launch([_external_candidate(), _candidates(1)[0]])

    assert len(launched) == 1
    manifest = job.api.batch_bucket_files.call_args_list[-1].kwargs["add"][0][0]
    assert b"external/109743" not in manifest
    assert b"2607.00000" in manifest
    job._run_ocr_job.assert_called_once()


def test_unmetered_hf_dispatch_does_not_require_paid_gate(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))

    def budget_decision(desired, _jobs):
        job.budget_desired_jobs = desired
        job.budget_affordable_jobs = desired
        return {"affordable_jobs": desired}

    monkeypatch.setattr(job, "_budget_decision", budget_decision)

    launched = job._launch(_candidates(1))

    assert len(launched) == 1
    assert job.paid_authorization_required is False


def test_dry_reconciliation_appends_coverage_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([papers[1]], 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "valid"})
    job._launch = Mock(return_value=[])

    job.run()
    job.run()

    history = tmp_path / MODULE.COVERAGE_HISTORY_NAME
    rows = [json.loads(line) for line in history.read_text().splitlines()]
    assert len(rows) == 2
    assert all(
        row
        | {
            "observed_at": None,
            "selected_profile": None,
        }
        == {
            "observed_at": None,
            "scope": "full",
            "eligible_papers": 2,
            "canonical_markdown_count": 1,
            "usable_markdown_count": 1,
            "repair_candidates": 0,
            "semantic_invalid_existing": 0,
            "semantic_evidence_unavailable": 0,
            "copied_from_upstream_count": 0,
            "planned_upstream_copy_count": 0,
            "missing_count": 1,
            "layout_missing_count": 0,
            "coverage_percentage": 50.0,
            "retryable_due": 0,
            "retryable_deferred": 0,
            "permanent_failures": 0,
            "attempts_exhausted": 0,
            "semantic_validation_failures": 0,
            "retryable_papers_blocked_by_budget": 0,
            "paid_authorization_required": False,
            "selected_profile": None,
        }
        for row in rows
    )
    # The full lane leaves the recent window's missing layout to the live lane.
    job._launch.assert_called_with([{**papers[1], "retry": False}])


def test_dry_run_does_not_count_unvalidated_upstream_as_usable(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False, full=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([], 1))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "valid"})
    job._launch = Mock(return_value=[])

    job.run()

    coverage = json.loads(
        (tmp_path / MODULE.COVERAGE_HISTORY_NAME).read_text().splitlines()[-1]
    )
    assert coverage["canonical_markdown_count"] == 1
    assert coverage["usable_markdown_count"] == 1
    assert coverage["copied_from_upstream_count"] == 0
    assert coverage["planned_upstream_copy_count"] == 1


def test_recent_semantic_invalid_object_is_not_usable_or_dispatched(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False, full=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([papers[1]], 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "invalid"})
    job._launch = Mock(return_value=[])

    job.run()

    summary_call = next(
        call
        for call in job.logger.info.call_args_list
        if call.args and call.args[0] == "PAPER_MARKDOWN_SUMMARY %s"
    )
    summary = json.loads(summary_call.args[1])
    assert summary["semantic_invalid_existing"] == 1
    assert summary["semantic_evidence_unavailable"] == 0
    assert summary["usable_markdown"] == 0
    assert summary["coverage_percentage"] == 0.0
    job._launch.assert_called_once_with([{**papers[1], "retry": False}])


def test_retry_only_canary_selects_only_persisted_retryable_due(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False)
    job.retry_only = True
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={})
    job._copy_upstream = Mock(return_value=(papers, 0))
    job._status_records = Mock(
        return_value={
            f"_jobs/status/{papers[1]['arxiv_id']}.json": {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
            }
        }
    )
    job._launch = Mock(return_value=[])

    job.run()

    job._launch.assert_called_once_with([{**papers[1], "retry": True}])


@pytest.mark.parametrize("affordable", [0, 1, 3, 4])
def test_scheduler_launches_exact_affordable_prefix(monkeypatch, affordable):
    job = _scheduler(execute=False, confirm=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda _desired, _jobs: {"affordable_jobs": affordable},
    )
    launched = job._launch(_candidates(400))
    assert len(launched) == affordable
    assert sum(int(item["papers"]) for item in launched) == affordable * 100


def test_hourly_workflow_refills_recent_and_full_markdown_lanes():
    workflow = (WORKFLOWS / "cron-paper-markdown.yml").read_text()

    assert (
        'REMOTE_COMMAND="sudo /usr/local/sbin/pwc-cron paper_markdown_backfill"'
        in workflow
    )
    assert 'BACKFILL_COMMAND="$REMOTE_COMMAND --full"' in workflow
    assert (
        'ssh -o StrictHostKeyChecking=yes "${VPS_USER}@${VPS_HOST}" "$REMOTE_COMMAND"'
        in workflow
    )
    assert (
        'ssh -o StrictHostKeyChecking=yes "${VPS_USER}@${VPS_HOST}" "$BACKFILL_COMMAND"'
        in workflow
    )


def test_retry_disposition_uses_persisted_fields():
    now = MODULE.datetime(2026, 8, 18, tzinfo=MODULE.UTC)
    assert (
        MODULE.status_disposition({"status": "failed", "error": "legacy"}, now=now)
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": True}, now=now
        )
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "next_retry_at": "2026-08-19T00:00:00Z",
            },
            now=now,
        )
        == "retryable_deferred"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "attempt_count": 3,
            },
            now=now,
        )
        == "attempts_exhausted"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": False},
            now=now,
        )
        == "permanent_failure"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "attempt_count": 1,
                "error_class": "arxiv_http_404",
                "retryable": False,
            },
            now=now,
        )
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "attempt_count": 2,
                "error_class": "arxiv_http_404",
                "retryable": False,
                "version_fallback_attempted": True,
            },
            now=now,
        )
        == "permanent_failure"
    )


def test_pre_lfs_fix_external_invalid_pdf_is_readmitted_once():
    record = {
        "schema_version": 2,
        "status": "failed",
        "source": "external",
        "attempt_count": 1,
        "error_class": "invalid_pdf",
        "retryable": False,
    }
    assert MODULE.status_disposition(record) == "retryable_due"
    assert (
        MODULE.status_disposition({**record, "lfs_pdf_url_attempted": True})
        == "permanent_failure"
    )
    assert (
        MODULE.status_disposition({**record, "source": "arxiv"}) == "permanent_failure"
    )


def test_missing_canonical_object_overrides_old_success():
    record = {"status": "succeeded", "attempt_count": 1}
    assert MODULE.status_disposition(record) == "completed"
    assert MODULE.status_disposition(record, canonical_missing=True) == "retryable_due"
    record["attempt_count"] = 3
    assert (
        MODULE.status_disposition(record, canonical_missing=True)
        == "attempts_exhausted"
    )


def test_refreshed_version_retries_old_missing_pdf():
    record = {
        "status": "failed",
        "schema_version": 2,
        "error_class": "arxiv_http_404",
        "requested_version": "v1",
        "version_fallback_attempted": True,
        "retryable": False,
        "attempt_count": 2,
    }
    assert (
        MODULE.status_disposition(record, requested_version="v1") == "permanent_failure"
    )
    assert MODULE.status_disposition(record, requested_version="v3") == "retryable_due"
    record["attempt_count"] = 3
    assert (
        MODULE.status_disposition(record, requested_version="v3")
        == "attempts_exhausted"
    )
