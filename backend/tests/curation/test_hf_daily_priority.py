"""Exercise queue admission against real SQL queries in an isolated SQLite DB."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperXTrending,
)
from backend.services.hf_daily_curation_service import HFDailyCurationService


@pytest.fixture
def queue_db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only storage is simplified; service queries and ORM mappings are real.
    for model in (Paper, PaperCurationJob, PaperCurationWorkflow, PaperXTrending):
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
    svc.release_awaiting_markdown = lambda _, **kwargs: 0
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


def test_spare_capacity_admits_backfill_while_daily_pending(queue_db):
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


@pytest.mark.parametrize(
    "status", [None, "deferred", "failed", "partial", "queued", "running", "canceled"]
)
def test_daily_without_ready_job_allows_conference_dispatch(queue_db, status):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 9, 1)
    if status:
        workflow(db, fresh.id, status=status)
    old = workflow(db, paper(db, 2).id, status="queued")
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            paper_id=old.paper_id,
            parent_workflow_id=old.id,
            kind="enrich-paper",
            status="queued",
            priority=100,
            trigger="hf-daily-cron",
        )
    )
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db).paper_id == old.paper_id


def test_completed_daily_allows_conference_dispatch(queue_db):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 9, 1)
    workflow(db, fresh.id, status="completed")
    old = workflow(db, paper(db, 2).id, status="queued")
    job = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=old.paper_id,
        parent_workflow_id=old.id,
        kind="enrich-paper",
        status="queued",
        priority=100,
        trigger="hf-daily-cron",
    )
    db.add(job)
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db) is job


def test_daily_outside_live_window_is_still_admitted(queue_db):
    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 9, 1)
    db.commit()
    svc, jobs = service(db, [], 1)
    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)
    assert jobs.enqueue.call_args.kwargs["paper_id"] == fresh.id


def test_daily_frees_full_backfill_queue_without_canceling_jobs(queue_db):
    db = queue_db
    old = workflow(db, paper(db, 1).id, status="queued")
    old_job = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=old.paper_id,
        parent_workflow_id=old.id,
        kind="enrich-paper",
        status="queued",
        priority=100,
        trigger="hf-daily-cron",
    )
    db.add(old_job)
    fresh = paper(db, 2)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 1)
    result = svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)
    assert result["created"] == 1
    assert jobs.enqueue.call_args.kwargs["paper_id"] == fresh.id
    assert old_job.status == "queued"


def test_released_backfill_reuses_parked_job(queue_db):
    db = queue_db
    old_paper = paper(db, 1)
    old = workflow(db, old_paper.id)
    job = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=old.paper_id,
        parent_workflow_id=old.id,
        kind="enrich-paper",
        status="queued",
        priority=100,
        trigger="hf-daily-cron",
    )
    db.add(job)
    db.flush()
    svc, jobs = service(db, [], 1)
    svc._enqueue_workflow(old, old_paper, priority=100)
    assert old.status == "queued"
    jobs.enqueue.assert_not_called()


@pytest.mark.parametrize("daily_trigger", ["hf-daily-cron", "hf-trending-cron"])
def test_daily_dispatch_precedes_overdue_conference_job(queue_db, daily_trigger):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    old = workflow(db, paper(db, 1).id, status="queued")
    fresh = paper(db, 2)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    daily = workflow(db, fresh.id, status="queued", cohort=date(2026, 10, 9))
    daily.created_at = datetime.now(UTC)
    for parent in (old, daily):
        job = PaperCurationJob(
            id=uuid.uuid4(),
            paper_id=parent.paper_id,
            parent_workflow_id=parent.id,
            kind="enrich-paper",
            status="queued",
            priority=100,
            trigger=daily_trigger if parent is daily else "hf-daily-cron",
        )
        db.add(job)
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db).paper_id == fresh.id


def test_trending_resolution_can_run_while_daily_waits_for_markdown(queue_db):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    workflow(db, fresh.id)
    job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        status="queued",
        priority=25,
        trigger="hf-trending-cron",
    )
    db.add(job)
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db) is job


def test_daily_retry_reclaims_next_available_worker(queue_db):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    daily = workflow(db, fresh.id, status="failed")
    old = workflow(db, paper(db, 2).id, status="queued")
    background = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=old.paper_id,
        parent_workflow_id=old.id,
        kind="enrich-paper",
        status="queued",
        priority=100,
        trigger="hf-daily-cron",
    )
    db.add(background)
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db) is background

    daily.status = "running"
    retry = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=fresh.id,
        parent_workflow_id=daily.id,
        kind="enrich-paper",
        status="queued",
        priority=50,
        trigger="hf-daily-cron",
    )
    db.add(retry)
    db.flush()
    assert CodexPaperJobService._next_scheduled_row(db) is retry


def test_blocked_daily_does_not_prevent_backfill_admission(queue_db):
    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    workflow(db, fresh.id, status="failed")
    old = workflow(db, paper(db, 2).id)
    db.commit()
    svc, jobs = service(db, [], 1)

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert jobs.enqueue.call_count == 1
    assert jobs.enqueue.call_args.kwargs["paper_id"] == old.paper_id


def test_running_daily_does_not_reserve_idle_workers(queue_db):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    daily = workflow(db, fresh.id, status="running")
    active = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=fresh.id,
        parent_workflow_id=daily.id,
        kind="enrich-paper",
        status="running",
        priority=10,
        trigger="hf-daily-cron",
    )
    old = workflow(db, paper(db, 2).id, status="queued")
    background = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=old.paper_id,
        parent_workflow_id=old.id,
        kind="enrich-paper",
        status="queued",
        priority=100,
        trigger="hf-daily-cron",
    )
    db.add_all([active, background])
    db.flush()

    assert CodexPaperJobService._next_scheduled_row(db) is background
    assert active.status == "running"


def test_source_ready_backfill_resumes_despite_failed_daily(queue_db):
    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 9)
    workflow(db, fresh.id, status="failed")
    old = workflow(db, paper(db, 2).id)
    old.deferred_reason = "awaiting_markdown"
    db.commit()
    svc, jobs = service(db, [], 1)
    svc.markdown_available = lambda paper, settings: True
    svc.release_awaiting_markdown = (
        HFDailyCurationService.release_awaiting_markdown.__get__(svc)
    )

    result = svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert result["released_markdown_ready"] == 1
    assert jobs.enqueue.call_count == 1
    assert jobs.enqueue.call_args.kwargs["paper_id"] == old.paper_id


@pytest.mark.parametrize("backfill_reason", ["queue_cap", "awaiting_markdown"])
@pytest.mark.parametrize("capacity", [0, 1, 2])
def test_daily_retry_consumes_admission_capacity(queue_db, backfill_reason, capacity):
    db = queue_db
    fresh = paper(db, 1)
    current = workflow(db, fresh.id, status="failed")
    old = workflow(db, paper(db, 2).id)
    old.deferred_reason = backfill_reason
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], capacity)
    svc.markdown_available = lambda paper, settings: True
    svc.release_awaiting_markdown = (
        HFDailyCurationService.release_awaiting_markdown.__get__(svc)
    )

    def retry(row):
        assert row is current
        row.status = "running"
        return True

    svc.retry_terminal_workflow = Mock(side_effect=retry)
    result = svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert result["retried"] == min(capacity, 1)
    assert jobs.enqueue.call_count == max(0, capacity - 1)
    if capacity == 2:
        assert jobs.enqueue.call_args.kwargs["paper_id"] == old.paper_id


def x_trending(db, paper_id, shared_on=date(2026, 10, 9), rank=1):
    db.add(PaperXTrending(shared_on=shared_on, paper_id=paper_id, rank=rank))
    db.flush()


def test_x_trending_admitted_before_hf_daily_cohort(queue_db):
    db = queue_db
    daily = paper(db, 1)
    older = paper(db, 2)
    newer = paper(db, 3)
    x_trending(db, older.id, shared_on=date(2026, 9, 1))
    x_trending(db, newer.id, rank=4)
    db.commit()
    svc, jobs = service(db, [daily.arxiv_id], 2)

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    # The most recently shared X papers take the capacity, at X priority, even
    # though they are not HF daily papers.
    calls = [call.kwargs for call in jobs.enqueue.call_args_list]
    assert [(call["paper_id"], call["priority"]) for call in calls] == [
        (newer.id, 5),
        (older.id, 5),
    ]


def test_queued_job_promoted_when_trending_on_x(queue_db):
    db = queue_db
    fresh = paper(db, 1)
    fresh.hf_daily_featured_on = date(2026, 10, 8)
    current = workflow(db, fresh.id, status="queued")
    job = PaperCurationJob(
        id=uuid.uuid4(),
        paper_id=fresh.id,
        parent_workflow_id=current.id,
        kind="add-evals",
        status="queued",
        priority=10,
        cohort_date=current.cohort_date,
        trigger="hf-daily-cron",
    )
    db.add(job)
    x_trending(db, fresh.id)
    db.commit()
    svc, jobs = service(db, [fresh.arxiv_id], 1)
    observed = []
    original_flush = db.flush

    def flush(*args, **kwargs):
        observed.append(job.priority)
        return original_flush(*args, **kwargs)

    db.flush = flush

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    assert 5 in observed
    jobs.enqueue.assert_not_called()


def test_x_trending_job_dispatches_before_daily_and_backlog(queue_db):
    from backend.services.codex_add_evals_service import CodexPaperJobService

    db = queue_db
    rows = {}
    for number, priority, featured in [
        (1, 100, None),
        (2, 10, date(2026, 10, 9)),
        (3, 5, None),
    ]:
        item = paper(db, number)
        item.hf_daily_featured_on = featured
        current = workflow(db, item.id, status="queued")
        rows[number] = PaperCurationJob(
            id=uuid.uuid4(),
            paper_id=item.id,
            parent_workflow_id=current.id,
            kind="enrich-paper",
            status="queued",
            priority=priority,
            cohort_date=current.cohort_date,
            trigger="hf-daily-cron",
        )
        db.add(rows[number])
    x_trending(db, 3)
    db.flush()

    assert CodexPaperJobService._next_scheduled_row(db) is rows[3]


def test_x_trending_priority_survives_versions_and_skips_external(queue_db):
    db = queue_db
    old = paper(db, 1)
    x_trending(db, old.id)
    old.is_latest_version = False
    newer = Paper(
        id=2,
        arxiv_id=old.arxiv_id,
        title="Paper 1 v2",
        source="arxiv",
        is_latest_version=True,
    )
    external = Paper(id=3, title="Blog", source="external", is_latest_version=True)
    db.add_all([newer, external])
    db.flush()
    x_trending(db, external.id, rank=2)
    db.commit()
    svc, jobs = service(db, [], 2)

    svc.reconcile(today=date(2026, 10, 9), lookback_days=1, dry_run=True)

    calls = [call.kwargs for call in jobs.enqueue.call_args_list]
    assert [(call["paper_id"], call["priority"]) for call in calls] == [(2, 5)]
