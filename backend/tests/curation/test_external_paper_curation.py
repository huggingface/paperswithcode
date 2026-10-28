"""New external papers get one queued enrich-paper -> add-evals workflow."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
)
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.external_paper_curation_service import (
    EXTERNAL_PAPER_POLICY_VERSION,
    enqueue_external_paper_curation,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

SETTINGS = SimpleNamespace(
    codex_jobs_enabled=False,
    codex_jobs_model="gpt-test",
    codex_jobs_reasoning_effort="high",
    codex_jobs_cli_version="0.0.0",
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only storage is simplified; service queries and ORM mappings are real.
    for model in (
        Paper,
        PaperCurationBootstrapBundle,
        PaperCurationJob,
        PaperCurationWorkflow,
        PaperCurationSchedulerState,
    ):
        columns = []
        for column in model.__table__.columns:
            kind = column.type
            if kind.__class__.__name__ == "JSONB":
                kind = JSON()
            elif kind.__class__.__name__ in {"ARRAY", "TSVECTOR", "Vector"}:
                kind = String()
            elif column.primary_key and kind.__class__.__name__ == "BigInteger":
                kind = Integer()  # SQLite autoincrements only INTEGER keys
            # Keep created_at/updated_at defaults; job serialization reads them.
            default = column.server_default if column.name.endswith("_at") else None
            columns.append(
                Column(
                    column.name,
                    kind,
                    primary_key=column.primary_key,
                    server_default=default,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def _paper(db, *, number=1, source="external"):
    paper = Paper(
        id=number,
        arxiv_id=None if source == "external" else f"2610.{number:05}",
        title=f"Release {number}",
        source=source,
        source_url=f"https://huggingface.co/org/model-{number}",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    return paper


def _enqueue(db, paper):
    return enqueue_external_paper_curation(
        db, paper, settings=SETTINGS, jobs=CodexPaperJobService()
    )


def test_new_external_paper_queues_one_admin_lane_workflow(db):
    paper = _paper(db)

    assert _enqueue(db, paper) is True
    db.commit()

    workflow = db.query(PaperCurationWorkflow).one()
    job = db.query(PaperCurationJob).one()
    assert workflow.paper_id == paper.id
    assert workflow.policy_version == EXTERNAL_PAPER_POLICY_VERSION
    assert workflow.status == "queued"
    assert job.kind == "enrich-paper"
    assert job.status == "queued"
    assert job.trigger == "admin"
    assert job.policy_version == EXTERNAL_PAPER_POLICY_VERSION
    assert job.parent_workflow_id == workflow.id
    assert job.requested_by == "external-paper-created"
    assert job.paper_route == str(paper.id)
    # Interactive admin jobs keep priority 0 and dispatch first.
    assert job.priority == 50


def test_external_paper_is_queued_once(db):
    paper = _paper(db)
    assert _enqueue(db, paper) is True
    db.commit()
    db.query(PaperCurationWorkflow).update({"status": "completed"})
    db.query(PaperCurationJob).update({"status": "completed"})
    db.commit()

    assert _enqueue(db, paper) is False
    assert db.query(PaperCurationWorkflow).count() == 1


def test_arxiv_papers_are_not_queued(db):
    assert _enqueue(db, _paper(db, source="arxiv")) is False
    assert db.query(PaperCurationJob).count() == 0


@pytest.mark.parametrize(
    ("workflow_status", "job_status"),
    [("running", None), ("deferred", None), (None, "queued"), (None, "running")],
)
def test_live_curation_work_is_not_duplicated(db, workflow_status, job_status):
    paper = _paper(db)
    if workflow_status:
        db.add(
            PaperCurationWorkflow(
                id=uuid.uuid4(),
                paper_id=paper.id,
                cohort_date=date(2026, 10, 18),
                cohort_order=0,
                policy_version="hf-trending-v1",
                status=workflow_status,
            )
        )
    if job_status:
        db.add(
            PaperCurationJob(
                id=uuid.uuid4(),
                kind="add-evals",
                paper_id=paper.id,
                requested_by="example-admin",
                status=job_status,
                trigger="admin",
                attempt_count=0,
                created_at=datetime.now(UTC),
            )
        )
    db.flush()

    assert _enqueue(db, paper) is False
    assert (
        db.query(PaperCurationWorkflow)
        .filter(PaperCurationWorkflow.policy_version == EXTERNAL_PAPER_POLICY_VERSION)
        .count()
        == 0
    )


def test_completed_enrich_stage_queues_add_evals_in_same_lane(db):
    paper = _paper(db)
    service = CodexPaperJobService()
    enqueue_external_paper_curation(db, paper, settings=SETTINGS, jobs=service)
    db.commit()
    enrich = db.query(PaperCurationJob).one()
    enrich.status = "completed"

    service._advance_workflow(db, enrich, SETTINGS)
    db.commit()

    add_evals = (
        db.query(PaperCurationJob).filter(PaperCurationJob.kind == "add-evals").one()
    )
    assert add_evals.status == "queued"
    assert add_evals.trigger == "admin"
    assert add_evals.policy_version == EXTERNAL_PAPER_POLICY_VERSION
    assert add_evals.priority == 50
    assert add_evals.parent_workflow_id == enrich.parent_workflow_id


def test_late_enrich_completion_closes_workflow_with_finished_evals(db):
    paper = _paper(db)
    service = CodexPaperJobService()
    enqueue_external_paper_curation(db, paper, settings=SETTINGS, jobs=service)
    db.commit()
    enrich = db.query(PaperCurationJob).one()
    workflow = db.get(PaperCurationWorkflow, enrich.parent_workflow_id)
    workflow.status = "running"  # as set by an admin retry
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            kind="add-evals",
            paper_id=paper.id,
            requested_by="example-admin",
            status="completed",
            trigger="admin",
            attempt_count=1,
            created_at=datetime.now(UTC),
            parent_workflow_id=workflow.id,
        )
    )
    enrich.status = "completed"
    db.flush()

    service._advance_workflow(db, enrich, SETTINGS)

    assert workflow.status == "completed"


def _ingest(db, monkeypatch, enqueue, *, queue_curation=True):
    monkeypatch.setattr(
        "backend.services.external_resource_service.find_arxiv_paper_for_title",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "backend.services.external_resource_service.enqueue_external_paper_curation",
        enqueue,
    )
    monkeypatch.setattr(
        "backend.services.external_resource_service.PaperService",
        lambda _db: SimpleNamespace(get_paper_by_id=lambda *_a, **_k: Mock(id=1)),
    )
    service = ExternalResourceService(db)
    monkeypatch.setattr(service, "_link_authors", lambda *_args: (0, 0))
    monkeypatch.setattr(service, "_link_github_repositories", lambda *_args: (0, 0))
    monkeypatch.setattr(
        service,
        "_set_hf_artifacts",
        lambda *_args: {
            "models_added": 0,
            "datasets_added": 0,
            "spaces_added": 0,
            "existing": 0,
        },
    )
    service.add_external_resource(
        ExternalResourceInput(
            source_url="https://huggingface.co/org/new-model",
            title="New Model",
            date_published=date(2026, 10, 16),
        ),
        queue_curation=queue_curation,
    )


def test_ingestion_queues_curation_only_for_newly_created_rows(db, monkeypatch):
    enqueue = Mock(return_value=True)

    _ingest(db, monkeypatch, enqueue)
    _ingest(db, monkeypatch, enqueue)

    enqueue.assert_called_once()
    created = enqueue.call_args.args[1]
    assert created.source == "external"
    assert created.source_url == "https://huggingface.co/org/new-model"


def test_ingestion_can_opt_out_for_callers_with_their_own_workflow(db, monkeypatch):
    enqueue = Mock(return_value=True)

    _ingest(db, monkeypatch, enqueue, queue_curation=False)

    enqueue.assert_not_called()
    assert db.query(Paper).count() == 1


def test_ingestion_archives_the_pdf_only_for_newly_created_rows(db, monkeypatch):
    archive = Mock()
    monkeypatch.setattr(
        "backend.services.external_resource_service.archive_new_external_paper_pdf",
        archive,
    )

    _ingest(db, monkeypatch, Mock(return_value=True))
    _ingest(db, monkeypatch, Mock(return_value=True))

    archive.assert_called_once()
    assert archive.call_args.args == (1, "https://huggingface.co/org/new-model")


def test_backfill_queues_recent_uncurated_papers_hf_models_first(db):
    from datetime import timedelta

    from backend.services.external_paper_curation_service import (
        backfill_external_paper_curation,
    )

    now = datetime.now(UTC)
    rows = {
        1: (now - timedelta(days=2), None),
        2: (now - timedelta(days=5), ["https://huggingface.co/org/model-2"]),
        3: (now - timedelta(days=1), None),
        4: (now - timedelta(days=45), ["https://huggingface.co/org/model-4"]),
    }
    for number, (created_at, hf_models) in rows.items():
        paper = _paper(db, number=number)
        paper.created_at = created_at
        paper.hf_models = hf_models
    curated = _paper(db, number=5)
    curated.created_at = now
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            kind="enrich-paper",
            paper_id=curated.id,
            requested_by="example-admin",
            status="completed",
            trigger="admin",
            attempt_count=1,
        )
    )
    _paper(db, number=6, source="arxiv").created_at = now
    db.commit()

    preview = backfill_external_paper_curation(
        db, days=30, limit=2, dry_run=True, settings=SETTINGS
    )
    assert preview["eligible"] == 3
    assert preview["eligible_with_hf_models"] == 1
    assert preview["queued_paper_ids"] == [2, 3]
    assert db.query(PaperCurationJob).count() == 1

    result = backfill_external_paper_curation(
        db, days=30, limit=2, settings=SETTINGS, jobs=CodexPaperJobService()
    )
    assert result["queued_paper_ids"] == [2, 3]
    jobs = db.query(PaperCurationJob).filter(PaperCurationJob.paper_id.in_([2, 3]))
    assert {job.requested_by for job in jobs} == {"external-paper-backfill"}
    assert backfill_external_paper_curation(db, days=30, limit=10, settings=SETTINGS)[
        "queued_paper_ids"
    ] == [1]


def test_external_paper_jobs_hold_at_most_two_workers(db, monkeypatch):
    service = CodexPaperJobService()
    for number in range(1, 5):
        enqueue_external_paper_curation(
            db, _paper(db, number=number), settings=SETTINGS, jobs=service
        )
    _paper(db, number=9)
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            kind="add-evals",
            paper_id=9,
            requested_by="example-admin",
            status="queued",
            trigger="admin",
            policy_version="admin-v1",
            priority=0,
            attempt_count=0,
        )
    )
    db.commit()

    def launch(_db, _settings, row):
        row.status = "running"
        _db.commit()

    monkeypatch.setattr(service, "_dispatch_row", launch)
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
        codex_curation_scheduler_enabled=False,
    )

    service.dispatch_next(db, settings)

    running = db.query(PaperCurationJob).filter(PaperCurationJob.status == "running")
    assert sorted(job.policy_version for job in running) == [
        "admin-v1",
        EXTERNAL_PAPER_POLICY_VERSION,
        EXTERNAL_PAPER_POLICY_VERSION,
    ]


def test_completed_external_workflow_never_releases_the_daily_canary(db):
    paper = _paper(db)
    service = CodexPaperJobService()
    enqueue_external_paper_curation(db, paper, settings=SETTINGS, jobs=service)
    db.add(PaperCurationSchedulerState(id=1, canary_released=False))
    db.commit()
    job = db.query(PaperCurationJob).one()
    job.kind = "add-evals"
    job.status = "completed"

    service._advance_workflow(db, job, SETTINGS)
    db.commit()

    assert db.query(PaperCurationWorkflow).one().status == "completed"
    assert not db.get(PaperCurationSchedulerState, 1).canary_released
