"""Admin paper jobs wait for Markdown instead of failing, then resume hourly."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
)
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.hf_daily_curation_service import HFDailyCurationService

AWAITING_ERROR = "[awaiting_markdown] Awaiting paper Markdown extraction: 2610.00001"
TOKEN = "callback-token"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only storage is simplified; service queries and ORM mappings are real.
    for model in (
        Paper,
        PaperCurationJob,
        PaperCurationWorkflow,
        PaperCurationSchedulerState,
    ):
        columns = []
        for column in model.__table__.columns:
            kind = column.type
            if kind.__class__.__name__ in {"JSONB", "ARRAY", "TSVECTOR", "Vector"}:
                kind = String()
            columns.append(Column(column.name, kind, primary_key=column.primary_key))
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def _settings():
    return SimpleNamespace(
        codex_jobs_enabled=False,
        codex_jobs_token="hf-token",
        codex_jobs_namespace="nielsr",
    )


def _running_job(db, *, number=1, trigger="admin", attempt_count=1, kind="add-evals"):
    paper = Paper(
        id=number,
        arxiv_id=f"2610.{number:05}",
        title=f"Paper {number}",
        source="arxiv",
        is_latest_version=True,
    )
    row = PaperCurationJob(
        id=uuid.uuid4(),
        kind=kind,
        paper_id=paper.id,
        requested_by="nielsr",
        status="running",
        trigger=trigger,
        hf_job_id=f"hf-job-{number}",
        callback_token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
        attempt_count=attempt_count,
        trace_status="pending",
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add_all([paper, row])
    db.commit()
    return row


def _complete(db, row, error=AWAITING_ERROR):
    CodexPaperJobService().complete(
        db, row, report="", error=error, settings=_settings()
    )


@pytest.mark.parametrize("kind", ["add-evals", "enrich-paper"])
def test_first_admin_attempt_without_paper_text_waits(db, kind):
    row = _running_job(db, kind=kind)

    _complete(db, row)

    assert row.status == "awaiting_markdown"
    assert row.error == AWAITING_ERROR
    assert row.hf_job_id == "hf-job-1"
    # The finished attempt can no longer call back or apply mutations.
    assert CodexPaperJobService().authenticate(db, row.id, TOKEN) is None


@pytest.mark.parametrize(
    ("trigger", "attempt_count", "error"),
    [
        # A released attempt that still finds no text must not loop.
        ("admin", 2, AWAITING_ERROR),
        # Scheduled jobs defer their workflow instead.
        ("hf-daily-cron", 1, AWAITING_ERROR),
        ("admin", 1, "Remote job failed for another reason."),
    ],
)
def test_other_failures_stay_failed(db, trigger, attempt_count, error):
    row = _running_job(db, trigger=trigger, attempt_count=attempt_count)

    _complete(db, row, error)

    assert row.status == "failed"


def test_hourly_reconcile_requeues_only_jobs_whose_markdown_exists(db):
    ready = _running_job(db, number=1)
    pending = _running_job(db, number=2)
    _complete(db, ready)
    _complete(db, pending)

    service = HFDailyCurationService(
        db,
        _settings(),
        job_service=CodexPaperJobService(),
        markdown_available=lambda paper, _settings: paper.id == 1,
    )

    assert service.release_admin_awaiting_markdown() == 1
    assert ready.status == "queued"
    assert ready.hf_job_id is None
    assert ready.error is None
    assert ready.finished_at is None
    assert pending.status == "awaiting_markdown"


def test_canceling_a_waiting_job_skips_the_finished_remote_job(db):
    row = _running_job(db)
    _complete(db, row)
    api = Mock()

    CodexPaperJobService(hf_api=api).cancel(db, row, _settings())

    assert row.status == "canceled"
    api.cancel_job.assert_not_called()


def test_newer_admin_job_supersedes_a_waiting_one(db):
    older = _running_job(db, number=1)
    _complete(db, older)
    newer = PaperCurationJob(
        id=uuid.uuid4(),
        kind=older.kind,
        paper_id=older.paper_id,
        requested_by="nielsr",
        status="queued",
        trigger="admin",
        attempt_count=0,
        created_at=datetime.now(UTC),
    )
    db.add(newer)
    db.commit()

    service = HFDailyCurationService(
        db,
        _settings(),
        job_service=CodexPaperJobService(),
        markdown_available=lambda _paper, _settings: True,
    )

    assert service.release_admin_awaiting_markdown() == 0
    assert older.status == "canceled"
    assert newer.status == "queued"


def test_release_never_overwrites_a_concurrent_cancel(db):
    row = _running_job(db)
    _complete(db, row)

    def cancel_while_checking(_paper, _settings):
        # An admin cancel commits between the release scan and its update.
        db.query(PaperCurationJob).filter(PaperCurationJob.id == row.id).update(
            {"status": "canceled"}
        )
        return True

    service = HFDailyCurationService(
        db,
        _settings(),
        job_service=CodexPaperJobService(),
        markdown_available=cancel_while_checking,
    )

    assert service.release_admin_awaiting_markdown() == 0
    db.refresh(row)
    assert row.status == "canceled"


@pytest.mark.parametrize("newer_status", ["failed", "canceled"])
def test_stopped_newer_job_does_not_supersede_a_waiting_one(db, newer_status):
    older = _running_job(db, number=1)
    _complete(db, older)
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            kind=older.kind,
            paper_id=older.paper_id,
            requested_by="nielsr",
            status=newer_status,
            trigger="admin",
            attempt_count=1,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()

    service = HFDailyCurationService(
        db,
        _settings(),
        job_service=CodexPaperJobService(),
        markdown_available=lambda _paper, _settings: True,
    )

    assert service.release_admin_awaiting_markdown() == 1
    assert older.status == "queued"
