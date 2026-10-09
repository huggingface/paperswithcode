"""Exercise queue admission against real SQL queries in an isolated SQLite DB."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperCurationJob, PaperCurationWorkflow
from backend.services.hf_daily_curation_service import HFDailyCurationService


@pytest.fixture
def queue_db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only storage is simplified; service queries and ORM mappings are real.
    for model in (Paper, PaperCurationJob, PaperCurationWorkflow):
        columns = []
        for column in model.__table__.columns:
            kind = column.type
            if kind.__class__.__name__ in {"JSONB", "ARRAY", "TSVECTOR", "Vector"}:
                kind = String()
            columns.append(Column(column.name, kind, primary_key=column.primary_key))
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def paper(db, number):
    row = Paper(
        id=number,
        arxiv_id=f"2610.{number:05}",
        title=f"Paper {number}",
        source="arxiv",
        is_latest_version=True,
    )
    db.add(row)
    db.flush()
    return row


def workflow(db, paper_id, *, status="deferred", cohort=date(2026, 9, 15)):
    row = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper_id,
        cohort_date=cohort,
        cohort_order=0,
        policy_version="hf-daily-v1",
        status=status,
        deferred_reason="queue_cap" if status == "deferred" else None,
        created_at=datetime.now(UTC) - timedelta(days=5),
    )
    db.add(row)
    db.flush()
    return row


def service(db, daily, capacity):
    settings = SimpleNamespace(
        codex_curation_policy_version="hf-daily-v1",
        codex_curation_queue_depth=capacity,
        codex_curation_reconcile_limit=200,
        codex_curation_scheduler_enabled=False,
    )
    jobs = Mock()
    svc = HFDailyCurationService(
        db, settings, fetch_cohort=lambda _: daily, job_service=jobs
    )
    svc._state = lambda: SimpleNamespace(canary_released=True)
    svc.release_awaiting_markdown = lambda _: 0
    return svc, jobs


@pytest.mark.parametrize("already_deferred", [False, True])
def test_daily_admitted_before_conference_overflow(queue_db, already_deferred):
    db = queue_db
    old = workflow(db, paper(db, 1).id)
    fresh = paper(db, 2)
    if already_deferred:
        workflow(db, fresh.id)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 1)

    result = svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert jobs.enqueue.call_count == 1
    assert jobs.enqueue.call_args.kwargs["paper_id"] == fresh.id
    assert jobs.enqueue.call_args.kwargs["priority"] == 10
    assert result["released_deferred" if already_deferred else "created"] == 1
    assert db.get(PaperCurationWorkflow, old.id).status == "deferred"


@pytest.mark.parametrize("job_status", ["queued", "dispatching", "running"])
def test_existing_conference_job_promoted_when_featured_on_hf(queue_db, job_status):
    db = queue_db
    fresh = paper(db, 1)
    current = workflow(db, fresh.id, status="queued")
    job = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=fresh.id,
        parent_workflow_id=current.id,
        kind="enrich-paper",
        status=job_status,
        priority=100,
        cohort_date=current.cohort_date,
        trigger="hf-daily-cron",
    )
    db.add(job)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 1)
    # Observe values before the intentional dry-run rollback.
    observed = []
    original_flush = db.flush

    def flush(*args, **kwargs):
        observed.append((job.priority, current.cohort_date))
        return original_flush(*args, **kwargs)

    db.flush = flush

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert (10, date(2026, 10, 9)) in observed
    jobs.enqueue.assert_not_called()


def test_spare_capacity_still_admits_backfill(queue_db):
    db = queue_db
    old = workflow(db, paper(db, 1).id)
    fresh = paper(db, 2)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 2)

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert [
        (c.kwargs["paper_id"], c.kwargs["priority"])
        for c in jobs.enqueue.call_args_list
    ] == [(fresh.id, 10), (old.paper_id, 100)]


def test_full_queue_defers_daily_without_exceeding_capacity(queue_db):
    db = queue_db
    workflow(db, paper(db, 1).id, status="running")
    fresh = paper(db, 2)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 1)

    result = svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert result["deferred"] == 1
    jobs.enqueue.assert_not_called()
