"""Completion must leave either the whole durable transition or none of it."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Base,
    ModelRelease,
    Paper,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
    TrendingModelCandidate,
)
from backend.services.codex_add_evals_service import CodexPaperJobService


@compiles(BigInteger, "sqlite")
def _bigint(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _postgres_types(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def completion(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'completion.db'}")
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                Paper,
                ModelRelease,
                TrendingModelCandidate,
                PaperCurationJob,
                PaperCurationWorkflow,
                PaperCurationSchedulerState,
            )
        ],
    )
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )
    settings = get_settings().model_copy(update={"codex_jobs_enabled": False})
    service = CodexPaperJobService()
    with Session(engine, autoflush=False) as db:
        paper = Paper(
            title="Report",
            source="external",
            version="v1",
            source_url="https://example.com/report",
        )
        db.add(paper)
        db.flush()
        state = PaperCurationSchedulerState(id=1, consecutive_apply_failures=2)
        workflow = PaperCurationWorkflow(
            id=uuid.uuid4(),
            paper_id=paper.id,
            cohort_date=datetime.now(UTC).date(),
            policy_version="test-v1",
            status="running",
        )
        job = PaperCurationJob(
            id=uuid.uuid4(),
            kind="enrich-paper",
            paper_id=paper.id,
            paper_route=str(paper.id),
            paper_title=paper.title,
            requested_by="test",
            trigger="hf-daily-cron",
            status="running",
            parent_workflow_id=workflow.id,
            policy_version="test-v1",
            submitted_at=datetime.now(UTC),
            mutation_result={"status": "no_changes"},
            validation_summary={"post_write_verification": "passed"},
        )
        db.add_all([state, workflow, job])
        db.commit()
        yield db, service, settings, job
    engine.dispose()


def _resolve_candidate(db, job):
    release = ModelRelease(paper_id=job.paper_id, canonical_name="Model", aliases=[])
    db.add(release)
    db.flush()
    candidate = TrendingModelCandidate(
        id=uuid.uuid4(),
        repo_id="org/model",
        author="org",
        status="resolved",
        readme_sha="a" * 64,
        model_release_id=release.id,
    )
    db.add(candidate)
    workflow = db.get(PaperCurationWorkflow, job.parent_workflow_id)
    job.parent_workflow_id = None
    db.delete(workflow)
    job.kind = "resolve-model-paper"
    job.paper_id = None
    job.paper_route = None
    job.paper_title = None
    job.trigger = "hf-trending-cron"
    job.candidate_id = candidate.id
    db.commit()
    return candidate


@pytest.mark.parametrize("resolution", [False, True], ids=["enrichment", "candidate"])
@pytest.mark.parametrize("boundary", ["workflow", "health", "commit"])
def test_failure_rolls_back_entire_transition(
    completion, monkeypatch, resolution, boundary
):
    db, service, settings, job = completion
    if resolution:
        _resolve_candidate(db, job)
    workflow_count = db.query(PaperCurationWorkflow).count()
    job_id = job.id
    methods = {"workflow": "_advance_workflow", "health": "_evaluate_scheduled_health"}
    original = getattr(service, methods[boundary]) if boundary != "commit" else None

    def interrupt(*args):
        if original is not None:
            original(*args)
        raise RuntimeError("interrupted completion")

    with monkeypatch.context() as patch:
        if boundary == "commit":
            event.listen(db, "before_commit", interrupt)
        else:
            patch.setattr(service, methods[boundary], interrupt)
        with pytest.raises(RuntimeError, match="interrupted completion"):
            service.complete(db, job, report="done", error=None, settings=settings)
        if boundary == "commit":
            event.remove(db, "before_commit", interrupt)
    db.rollback()
    with Session(db.get_bind()) as observer:
        assert observer.get(PaperCurationJob, job_id).status == "running"
        assert observer.query(PaperCurationJob).count() == 1
        assert observer.query(PaperCurationWorkflow).count() == workflow_count
        assert (
            observer.get(PaperCurationSchedulerState, 1).consecutive_apply_failures == 2
        )

    service.complete(db, job, report="done", error=None, settings=settings)
    assert db.query(PaperCurationJob).count() == 2
    assert job.status == "completed"
    assert db.get(PaperCurationSchedulerState, 1).consecutive_apply_failures == 0


@pytest.mark.parametrize("resolution", [False, True], ids=["enrichment", "candidate"])
def test_dispatch_failure_leaves_recoverable_successor(
    completion, monkeypatch, resolution
):
    db, service, settings, job = completion
    if resolution:
        _resolve_candidate(db, job)
    job_id = job.id

    def dispatch_failure(*_args):
        with Session(db.get_bind()) as observer:
            assert observer.get(PaperCurationJob, job_id).status == "completed"
            assert (
                observer.query(PaperCurationJob).filter_by(status="queued").count() == 1
            )
        raise RuntimeError("dispatch unavailable")

    monkeypatch.setattr(service, "dispatch_next", dispatch_failure)
    with pytest.raises(RuntimeError, match="dispatch unavailable"):
        service.complete(db, job, report="done", error=None, settings=settings)
    db.rollback()
    # Replaying completion does not rerun health accounting or create successors.
    service.complete(db, job, report="duplicate", error="late error", settings=settings)
    assert job.report == "done"
    assert db.query(PaperCurationJob).count() == 2
    assert db.get(PaperCurationSchedulerState, 1).consecutive_apply_failures == 0

    launched = []

    def dispatch_row(db, _settings, row):
        launched.append(row.id)
        row.status = "running"
        db.commit()

    monkeypatch.setattr(service, "_dispatch_row", dispatch_row)
    # The ordinary scheduler, in a later session/process, finds the durable queue.
    monkeypatch.setattr(service, "_scheduled_usage_allowed", lambda *_args: True)
    state = db.get(PaperCurationSchedulerState, 1)
    state.dispatch_enabled = True
    state.paused_at = None
    db.commit()
    enabled = settings.model_copy(
        update={
            "codex_curation_scheduler_enabled": True,
            "codex_jobs_max_active": 2,
            "codex_jobs_max_scheduled_active": 1,
        }
    )
    with Session(db.get_bind()) as recovered:
        service._dispatch_next_locked(recovered, enabled)
    assert len(launched) == 1


def test_stale_callback_reloads_terminal_state(completion):
    db, service, settings, job = completion
    with Session(db.get_bind(), expire_on_commit=False) as stale:
        stale_job = stale.get(PaperCurationJob, job.id)
        stale.commit()
        service.complete(db, job, report="first", error=None, settings=settings)
        assert stale_job.status == "running"
        service.complete(
            stale, stale_job, report="second", error=None, settings=settings
        )
        assert stale_job.status == "completed"
        assert stale_job.report == "first"
        assert stale.query(PaperCurationJob).count() == 2


def test_health_window_includes_current_terminal_job_without_autoflush(completion):
    db, service, settings, job = completion
    job.parent_workflow_id = None
    state = db.get(PaperCurationSchedulerState, 1)
    state.consecutive_apply_failures = 0
    for index in range(24):
        db.add(
            PaperCurationJob(
                id=uuid.uuid4(),
                kind="enrich-paper",
                paper_id=job.paper_id,
                paper_route=job.paper_route,
                paper_title=job.paper_title,
                policy_version=f"history-{index}",
                requested_by="test",
                trigger="hf-daily-cron",
                status="failed" if index < 5 else "completed",
                error="apply failure" if index < 5 else None,
                finished_at=datetime.now(UTC) - timedelta(minutes=index + 1),
            )
        )
    db.commit()
    service.complete(db, job, report="failed", error="apply failure", settings=settings)
    assert state.consecutive_apply_failures == 1
    assert state.pause_condition == "terminal_failure_rate"
    assert state.paused_at is not None


def _add_history(db, job, errors):
    for index, error in enumerate(errors):
        db.add(
            PaperCurationJob(
                id=uuid.uuid4(),
                kind="enrich-paper",
                paper_id=job.paper_id,
                paper_route=job.paper_route,
                paper_title=job.paper_title,
                policy_version=f"history-{index}",
                requested_by="test",
                trigger="hf-daily-cron",
                status="failed" if error else "completed",
                error=error,
                finished_at=datetime.now(UTC) - timedelta(minutes=index + 1),
            )
        )
    db.commit()


def test_health_window_ignores_runner_transport_failures(completion):
    db, service, settings, job = completion
    job.parent_workflow_id = None
    state = db.get(PaperCurationSchedulerState, 1)
    state.consecutive_apply_failures = 2
    transport = [
        "Remote runner failed (URLError).",
        "Remote runner failed (RemoteDisconnected).",
        "Remote runner failed (TimeoutError).",
    ]
    _add_history(db, job, transport * 3 + ["apply failure"] * 3 + [None] * 18)

    service.complete(
        db,
        job,
        report="",
        error="Remote runner failed (TimeoutError).",
        settings=settings,
    )

    assert state.consecutive_apply_failures == 2
    assert state.paused_at is None


def test_health_window_pauses_when_most_runners_lose_their_callbacks(completion):
    db, service, settings, job = completion
    job.parent_workflow_id = None
    state = db.get(PaperCurationSchedulerState, 1)
    state.consecutive_apply_failures = 0
    _add_history(db, job, ["Remote runner failed (URLError)."] * 12 + [None] * 12)

    service.complete(
        db, job, report="", error="Remote runner failed (URLError).", settings=settings
    )

    assert state.consecutive_apply_failures == 0
    assert state.pause_condition == "runner_transport_failures"
    assert state.paused_at is not None


def test_transport_outage_pause_outranks_the_daily_breaker(completion):
    db, service, settings, job = completion
    job.parent_workflow_id = None
    state = db.get(PaperCurationSchedulerState, 1)
    state.consecutive_apply_failures = 0
    _add_history(
        db,
        job,
        ["Remote runner failed (URLError)."] * 13 + ["apply failure"] * 6 + [None] * 5,
    )

    service.complete(db, job, report="done", error=None, settings=settings)

    assert state.pause_condition == "runner_transport_failures"


def test_runner_exception_names_outside_transport_still_count(completion):
    db, service, settings, job = completion
    job.parent_workflow_id = None
    state = db.get(PaperCurationSchedulerState, 1)
    state.consecutive_apply_failures = 0
    db.commit()

    service.complete(
        db,
        job,
        report="",
        error="Remote runner failed (JSONDecodeError).",
        settings=settings,
    )

    assert state.consecutive_apply_failures == 1


def test_last_canary_completion_releases_backlog_without_autoflush(completion):
    db, service, settings, job = completion
    job.kind = "add-evals"
    state = db.get(PaperCurationSchedulerState, 1)
    state.canary_released = False
    paper = Paper(
        title="Deferred report",
        source="external",
        version="v1",
        source_url="https://example.com/deferred",
    )
    db.add(paper)
    db.flush()
    deferred = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        cohort_date=datetime.now(UTC).date(),
        policy_version="test-v1",
        status="deferred",
        deferred_reason="canary_cap",
    )
    db.add(deferred)
    db.commit()
    settings = settings.model_copy(update={"codex_curation_queue_depth": 1})
    service.complete(db, job, report="done", error=None, settings=settings)
    assert state.canary_released is True
    assert db.get(PaperCurationWorkflow, job.parent_workflow_id).status == "completed"
    assert deferred.status == "queued"
    assert (
        db.query(PaperCurationJob).filter_by(parent_workflow_id=deferred.id).count()
        == 1
    )


def test_resolved_workflow_cannot_dispatch_uncommitted_work(completion):
    db, service, settings, job = completion
    candidate = _resolve_candidate(db, job)
    with pytest.raises(ValueError, match="committed workflow"):
        service.enqueue_resolved_candidate_workflow(
            db, candidate, settings, commit=False
        )
    assert db.query(PaperCurationWorkflow).count() == 0


def test_candidate_failure_and_scheduler_pause_commit_together(completion, monkeypatch):
    db, service, settings, job = completion
    candidate = _resolve_candidate(db, job)
    candidate.status = "resolving"
    db.commit()
    original = service._evaluate_scheduled_health

    def interrupted_health(*args):
        original(*args)
        raise RuntimeError("interrupted health decision")

    with monkeypatch.context() as patch:
        patch.setattr(service, "_evaluate_scheduled_health", interrupted_health)
        with pytest.raises(RuntimeError, match="interrupted health"):
            service.complete(
                db, job, report="failed", error="apply failure", settings=settings
            )
    db.rollback()
    assert job.status == "running"
    assert candidate.status == "resolving"
    state = db.get(PaperCurationSchedulerState, 1)
    assert state.consecutive_apply_failures == 2
    assert state.paused_at is None

    service.complete(db, job, report="failed", error="apply failure", settings=settings)
    assert job.status == "failed"
    assert candidate.status == "failed"
    assert candidate.rejection_reason == "apply failure"
    assert state.consecutive_apply_failures == 3
    assert state.pause_condition == "apply_or_verification_failures"
    service.complete(
        db, job, report="duplicate", error="apply failure", settings=settings
    )
    assert state.consecutive_apply_failures == 3
