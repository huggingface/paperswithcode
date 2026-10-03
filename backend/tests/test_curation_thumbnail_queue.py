from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from backend.config import get_settings
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.curation_thumbnail_queue_service import (
    CurationThumbnailQueueService,
    ThumbnailClaim,
)

os.environ.setdefault("PWC_CURATION_API_URL", "https://example.test/api/v1")
os.environ.setdefault("PWC_CURATION_JOB_ID", str(uuid.uuid4()))
os.environ.setdefault("PWC_CURATION_JOB_TOKEN", "test-token")
os.environ.setdefault("PWC_CURATION_KIND", "enrich-paper")
os.environ.setdefault("PWC_GIT_SHA", "a" * 40)

from jobs import curation_api, run_paper_curation


def test_scheduled_enrichment_proposals_preserve_existing_relations(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_TRIGGER", "hf-daily-cron")
    proposal = {
        "enrich": {
            "task_ids": [2],
            "method_ids": [4],
            "repositories": [
                {"url": "https://github.com/existing/project", "is_official": True},
                {"url": "https://github.com/new/project"},
            ],
            "project_pages": [{"url": "https://new.example"}],
            "task_removal_reasons": {1: "incorrect"},
        }
    }
    context = {
        "paper": {
            "tasks": [{"id": 1}],
            "methods": [{"id": 3}],
            "repositories": [
                {"url": "https://github.com/existing/project", "is_official": False}
            ],
            "project_pages": [{"url": "https://existing.example", "is_official": True}],
        }
    }

    result = curation_api.make_scheduled_enrichment_additive(proposal, context)

    assert result["enrich"]["task_ids"] == [1, 2]
    assert result["enrich"]["method_ids"] == [3, 4]
    assert result["enrich"]["repositories"] == [
        {"url": "https://github.com/existing/project", "is_official": False},
        {"url": "https://github.com/new/project"},
    ]
    assert result["enrich"]["project_pages"] == [
        {"url": "https://existing.example", "is_official": True},
        {"url": "https://new.example"},
    ]
    assert "task_removal_reasons" not in result["enrich"]
    assert proposal["enrich"]["task_ids"] == [2]


def test_resolution_proposal_discards_schema_generated_empty_enrichment(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_TRIGGER", "hf-trending-cron")
    proposal = {
        "resolve_model_paper": {"decision": "reject"},
        "evaluations": [],
        "evaluation_removals": [],
        "benchmark_gaps": [],
        "validation_evidence": [],
        "enrich": {
            "task_ids": None,
            "method_ids": None,
            "repositories": None,
            "project_pages": None,
            "urls_extracted": None,
            "regenerate_thumbnail": False,
            "task_removal_reasons": {},
            "method_removal_reasons": {},
            "project_page_removal_reasons": {},
        },
    }

    result = curation_api.make_scheduled_enrichment_additive(proposal, {})

    assert result["enrich"] is None


def _queue_row(**overrides):
    values = {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000042"),
        "kind": "enrich-paper",
        "paper_id": 42,
        "paper_route": "2601.00001",
        "paper_title": "A useful model",
        "requested_by": "niels",
        "status": "running",
        "hf_job_id": "hf-job",
        "created_at": datetime.now(UTC),
        "started_at": datetime.now(UTC),
        "finished_at": None,
        "submitted_at": datetime.now(UTC),
        "applied_at": datetime.now(UTC),
        "validation_summary": {"post_write_verification": "passed"},
        "mutation_result": {"status": "applied"},
        "report": None,
        "error": None,
        "attempt_count": 1,
        "thumbnail_status": "queued",
        "thumbnail_requested_at": datetime.now(UTC),
        "thumbnail_claimed_at": None,
        "thumbnail_finished_at": None,
        "thumbnail_attempt_count": 0,
        "thumbnail_url": None,
        "thumbnail_previous_width": None,
        "thumbnail_previous_height": None,
        "thumbnail_generated_width": None,
        "thumbnail_generated_height": None,
        "thumbnail_warnings": None,
        "thumbnail_error": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_remote_runner_bootstraps_only_hash_verified_files(tmp_path, monkeypatch):
    contents = {
        path: f"content for {path}".encode()
        for path in run_paper_curation.BOOTSTRAP_PATHS
    }
    monkeypatch.setattr(run_paper_curation, "WORKTREE", tmp_path / "worktree")
    monkeypatch.setattr(
        run_paper_curation,
        "api_request",
        lambda path: {
            "revision": run_paper_curation.REVISION,
            "files": [
                {
                    "path": relative,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "content_b64": base64.b64encode(content).decode(),
                }
                for relative, content in contents.items()
            ],
        },
    )

    run_paper_curation.bootstrap_worktree()

    for relative, content in contents.items():
        assert (run_paper_curation.WORKTREE / relative).read_bytes() == content


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def with_for_update(self, **_kwargs):
        return self

    def first(self):
        return self.rows.pop(0) if self.rows else None


class _Database:
    def __init__(self, row=None, query_rows=None):
        self.row = row
        self.query_rows = list(query_rows or [])
        self.commits = 0
        self.rollbacks = 0

    def query(self, _model):
        return _Query(self.query_rows)

    def get(self, _model, _identity):
        return self.row

    def commit(self):
        self.commits += 1

    def refresh(self, _row, *, with_for_update):
        assert with_for_update is True

    def flush(self):
        pass

    def rollback(self):
        self.rollbacks += 1


def test_claim_is_durable_and_a_claimed_row_is_not_claimed_twice():
    row = _queue_row()
    db = _Database(row=row, query_rows=[row, None])
    service = CurationThumbnailQueueService()

    first = service.claim_next(db)
    second = service.claim_next(db)

    assert first == ThumbnailClaim(job_id=row.id, paper_id=42)
    assert second is None
    assert row.thumbnail_status == "processing"
    assert row.thumbnail_attempt_count == 1
    assert row.thumbnail_claimed_at is not None
    assert db.commits == 1


def test_resolution_thumbnail_claim_uses_applied_paper_id():
    row = _queue_row(
        kind="resolve-model-paper",
        paper_id=None,
        mutation_result={"status": "resolved", "paper_id": 109743},
    )
    db = _Database(row=row, query_rows=[row])

    claim = CurationThumbnailQueueService().claim_next(db)

    assert claim == ThumbnailClaim(job_id=row.id, paper_id=109743)


def test_stale_processing_claim_can_be_recovered():
    row = _queue_row(
        thumbnail_status="processing",
        thumbnail_claimed_at=datetime.now(UTC) - timedelta(hours=1),
        thumbnail_attempt_count=1,
    )
    db = _Database(row=row, query_rows=[row])

    claim = CurationThumbnailQueueService().claim_next(db)

    assert claim is not None
    assert row.thumbnail_attempt_count == 2
    assert row.thumbnail_claimed_at > datetime.now(UTC) - timedelta(minutes=1)


def test_worker_records_success(monkeypatch):
    from backend.services import curation_thumbnail_queue_service as queue_module

    row = _queue_row(thumbnail_status="processing", thumbnail_attempt_count=1)
    db = _Database(row=row)
    result = SimpleNamespace(
        success=True,
        thumbnail_url="/api/thumbnails/example.jpg?v=1",
        previous=SimpleNamespace(width=400, height=280),
        generated=SimpleNamespace(width=400, height=560),
        warnings=(),
    )

    async def regenerate(_db, paper_reference, *, force):
        assert paper_reference == "42"
        assert force is True
        return result

    monkeypatch.setattr(queue_module, "regenerate_paper_thumbnail", regenerate)
    asyncio.run(
        CurationThumbnailQueueService().process_claim(
            db, ThumbnailClaim(job_id=row.id, paper_id=42)
        )
    )

    assert row.thumbnail_status == "succeeded"
    assert row.thumbnail_url == result.thumbnail_url
    assert (row.thumbnail_previous_width, row.thumbnail_previous_height) == (400, 280)
    assert (row.thumbnail_generated_width, row.thumbnail_generated_height) == (
        400,
        560,
    )
    assert row.thumbnail_error is None


def test_worker_records_bounded_failure(monkeypatch):
    from backend.services import curation_thumbnail_queue_service as queue_module

    row = _queue_row(thumbnail_status="processing", thumbnail_attempt_count=1)
    db = _Database(row=row)

    async def regenerate(*_args, **_kwargs):
        raise OSError("x" * 10_000)

    monkeypatch.setattr(queue_module, "regenerate_paper_thumbnail", regenerate)
    asyncio.run(
        CurationThumbnailQueueService().process_claim(
            db, ThumbnailClaim(job_id=row.id, paper_id=42)
        )
    )

    assert db.rollbacks == 1
    assert row.thumbnail_status == "failed"
    assert row.thumbnail_finished_at is not None
    assert len(row.thumbnail_error) == 4_000


def test_completion_requires_accepted_apply_and_successful_thumbnail(monkeypatch):
    service = CodexPaperJobService()
    monkeypatch.setattr(service, "dispatch_next", lambda *_args: None)
    settings = get_settings()

    missing_apply = _queue_row(
        submitted_at=None,
        applied_at=None,
        thumbnail_status=None,
        thumbnail_requested_at=None,
    )
    result = service.complete(
        _Database(row=missing_apply),
        missing_apply,
        report="done",
        error=None,
        settings=settings,
    )
    assert result.status == "failed"
    assert "accepted apply" in result.error

    failed_thumbnail = _queue_row(
        thumbnail_status="failed",
        thumbnail_error="read failed",
    )
    result = service.complete(
        _Database(row=failed_thumbnail),
        failed_thumbnail,
        report="done",
        error=None,
        settings=settings,
    )
    assert result.status == "failed"
    assert result.error == "read failed"

    succeeded_thumbnail = _queue_row(
        thumbnail_status="succeeded",
        thumbnail_finished_at=datetime.now(UTC),
    )
    result = service.complete(
        _Database(row=succeeded_thumbnail),
        succeeded_thumbnail,
        report="done",
        error=None,
        settings=settings,
    )
    assert result.status == "completed"


def test_resolution_completion_does_not_wait_for_thumbnail_worker(monkeypatch):
    service = CodexPaperJobService()
    monkeypatch.setattr(service, "dispatch_next", lambda *_args: None)
    row = _queue_row(
        kind="resolve-model-paper",
        paper_id=None,
        thumbnail_status="queued",
    )

    result = service.complete(
        _Database(row=row),
        row,
        report="resolved",
        error=None,
        settings=get_settings(),
    )

    assert result.status == "completed"
    assert row.thumbnail_status == "queued"


def test_legitimate_no_changes_submission_can_complete(monkeypatch):
    service = CodexPaperJobService()
    monkeypatch.setattr(service, "dispatch_next", lambda *_args: None)
    row = _queue_row(
        kind="add-evals",
        applied_at=None,
        mutation_result={"status": "no_changes"},
        thumbnail_status=None,
        thumbnail_requested_at=None,
    )

    result = service.complete(
        _Database(row=row),
        row,
        report="No configured results matched.",
        error=None,
        settings=get_settings(),
    )

    assert result.status == "completed"
    assert result.submitted_at is not None
    assert result.applied_at is None


def test_runner_propagates_pending_and_failed_thumbnail_status():
    assert "Timed out" in run_paper_curation.thumbnail_completion_error(
        {"status": "processing"}
    )
    assert (
        run_paper_curation.thumbnail_completion_error(
            {"status": "failed", "error": "generation failed"}
        )
        == "generation failed"
    )
    assert (
        run_paper_curation.thumbnail_completion_error({"status": "succeeded"}) is None
    )


def test_scoped_helper_waits_for_terminal_thumbnail_status(monkeypatch, capsys):
    responses = iter(
        [
            {"thumbnail": {"status": "queued"}},
            {"thumbnail": {"status": "succeeded", "success": True}},
        ]
    )
    monkeypatch.setattr(curation_api, "request_json", lambda _path: next(responses))
    monkeypatch.setattr(curation_api.time, "sleep", lambda _seconds: None)

    result = curation_api.wait_for_thumbnail(30, poll_seconds=1)

    assert result["thumbnail"]["status"] == "succeeded"
    assert '"status": "succeeded"' in capsys.readouterr().out


def test_deployment_keeps_thumbnail_mutation_out_of_web_service():
    root = Path(__file__).resolve().parents[2]
    backend_unit = (root / "deploy/systemd/paperswithcode-backend@.service").read_text()
    cron_launcher = (root / "deploy/cron_launcher.py").read_text()
    timer_service = (
        root / "deploy/systemd/pwc-curation-thumbnails.service"
    ).read_text()
    installer = (root / "deploy/install_deploy_tools.py").read_text()

    assert "ProtectSystem=strict" in backend_unit
    assert "/var/lib/paperswithcode/shared" not in backend_unit
    assert '"process_curation_thumbnails"' in cron_launcher
    assert '"PWC_THUMBNAIL_MUTATIONS_ENABLED"] = "true"' in cron_launcher
    assert "pwc-cron process_curation_thumbnails" in timer_service
    assert "--uid=pwc-cron --gid=pwc-cron" in installer
    assert "pwc-curation-thumbnails.timer" in installer
    assert '"enable", "--now"' not in installer
