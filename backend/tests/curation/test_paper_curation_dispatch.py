"""Scheduled and one-shot dispatch, image verification, and dispatch locking."""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    AutonomousOperatorState,
    AutonomousRun,
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationSchedulerState,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    curation_dispatch_lock,
)


class _DispatchQuery:
    def __init__(self, database):
        self.database = database

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *args):
        self.database.orderings.append([str(value) for value in args])
        return self

    def first(self):
        return self.database.first_results.pop(0)


class _DispatchDatabase:
    def __init__(self, *first_results):
        self.first_results = list(first_results)
        self.orderings = []

    def query(self, *_args):
        return _DispatchQuery(self)


def test_overdue_dispatch_reserves_only_one_slot_before_newest_first():
    oldest_overdue = object()
    newest = object()
    first_slot = _DispatchDatabase(None, None, oldest_overdue)
    remaining_slot = _DispatchDatabase(None, object(), None, newest)

    assert CodexPaperJobService._next_scheduled_row(first_slot) is oldest_overdue
    assert CodexPaperJobService._next_scheduled_row(remaining_slot) is newest
    assert any(
        "cohort_order" in value
        for ordering in remaining_slot.orderings
        for value in ordering
    )


def test_trending_resolution_precedes_non_overdue_backfill():
    trending = object()
    database = _DispatchDatabase(None, object(), trending)

    assert CodexPaperJobService._next_scheduled_row(database) is trending


def test_newest_first_fallback_when_no_overdue_workflow_exists():
    newest = object()
    database = _DispatchDatabase(None, None, None, None, newest)

    assert CodexPaperJobService._next_scheduled_row(database) is newest


def test_hf_dispatch_retries_with_bounded_exponential_backoff(monkeypatch):
    calls = []
    sleeps = []

    class Hub:
        def run_job(self, **values):
            calls.append(values)
            if len(calls) < 3:
                raise OSError("transient dispatch failure")
            return SimpleNamespace(id="hf-job")

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_api", lambda _settings: Hub())
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service.time.sleep", sleeps.append
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        retry_of_id=None,
        repository_sha="a" * 40,
        trigger="hf-daily-cron",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_openai_api_key": "test-openai",
            "github_token": "test-github",
            "hf_token": "test-hf",
        }
    )

    remote = service._run_job_with_retry(
        settings=settings,
        row=row,
        callback_token="callback",
        image="example/image:sha",
    )

    assert remote.id == "hf-job"
    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert all("GITHUB_TOKEN" not in call["secrets"] for call in calls)
    assert all(
        call["secrets"]["PWC_PAPER_MARKDOWN_HF_TOKEN"] == "test-hf" for call in calls
    )
    assert all(call["image"] == "example/image:sha" for call in calls)


def test_space_image_revision_is_verified_and_mismatch_pauses_daily_dispatch(
    monkeypatch,
):
    expected = "a" * 40
    state = SimpleNamespace(
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )

    class Hub:
        observed = expected

        def space_info(self, *, repo_id):
            assert repo_id == "example/curator-0123456789ab"
            return SimpleNamespace(sha=self.observed)

    class Database:
        commits = 0

        def get(self, *_args):
            return state

        def commit(self):
            self.commits += 1

    service = CodexPaperJobService()
    hub = Hub()
    monkeypatch.setattr(service, "_api", lambda _settings: hub)
    settings = get_settings().model_copy(
        update={
            "codex_jobs_image": "hf.co/spaces/example/curator-0123456789ab",
            "codex_jobs_image_revision": expected,
        }
    )
    row = SimpleNamespace(trigger="hf-daily-cron", repository_sha="b" * 40)
    database = Database()

    assert service._verified_job_image(database, settings, row) == (
        "hf.co/spaces/example/curator-0123456789ab"
    )

    hub.observed = "c" * 40
    with pytest.raises(RuntimeError, match="Curator Space revision mismatch"):
        service._verified_job_image(database, settings, row)
    assert state.pause_condition == "curator_image_revision_mismatch"
    assert state.paused_at is not None


def test_dispatch_does_not_append_registry_tag_to_verified_space(monkeypatch):
    from backend.services import codex_add_evals_service as service_module

    launched = {}

    class Database:
        def commit(self):
            pass

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service_module, "_store_bootstrap_bundle", lambda _db, _revision: "b" * 64
    )
    monkeypatch.setattr(
        service,
        "_verified_job_image",
        lambda _db, _settings, _row: "hf.co/spaces/example/curator-0123456789ab",
    )
    monkeypatch.setattr(
        service,
        "_run_job_with_retry",
        lambda **values: launched.update(values) or SimpleNamespace(id="hf-job"),
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        trigger="admin",
        retry_of_id=None,
        repository_sha="b" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        status="queued",
        callback_token_hash=None,
        attempt_count=0,
        hf_job_id=None,
        started_at=None,
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_token": "hf-token",
            "codex_jobs_openai_api_key": "openai-token",
        }
    )

    service._dispatch_row(Database(), settings, row)

    assert launched["image"] == "hf.co/spaces/example/curator-0123456789ab"
    assert row.status == "running"
    assert row.hf_job_id == "hf-job"


@pytest.mark.parametrize("trigger", ["hf-daily-cron", "benchmark-gap-cron"])
def test_one_shot_dispatch_calls_only_the_selected_scheduled_row(monkeypatch, trigger):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger=trigger,
        kind="add-evals",
        status="queued",
    )
    other = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-trending-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return []

    class Database:
        def query(self, model):
            assert model is PaperCurationJob
            return Query()

        def get(self, model, key):
            assert (model, key) == (PaperCurationSchedulerState, 1)
            return scheduler

    launched = []
    service = CodexPaperJobService()

    def launch(_db, _settings, row):
        launched.append(row)
        row.status = "running"
        row.hf_job_id = "hf-canary-job"

    monkeypatch.setattr(
        service,
        "_dispatch_row",
        launch,
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    service.dispatch_canary(Database(), settings, selected)

    assert launched == [selected]
    assert other.status == "queued"
    assert scheduler.dispatch_enabled is False
    assert scheduler.paused_at is not None


@pytest.mark.parametrize(
    ("trigger", "active_triggers"),
    [
        ("hf-daily-cron", ["hf-trending-cron"]),
        # The benchmark-gap lane has its own cap, separate from daily work.
        ("benchmark-gap-cron", ["benchmark-gap-cron", "benchmark-gap-cron"]),
    ],
)
def test_one_shot_dispatch_refuses_to_exceed_scheduled_capacity(
    monkeypatch, trigger, active_triggers
):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger=trigger,
        kind="add-evals",
        status="queued",
    )
    active = [
        SimpleNamespace(trigger=item, status="running") for item in active_triggers
    ]
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return active

    class Database:
        def query(self, _model):
            return Query()

        def get(self, _model, _key):
            return scheduler

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_dispatch_row",
        lambda *_args: pytest.fail("capacity denial must not launch a job"),
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=1,
    )

    with pytest.raises(RuntimeError, match="scheduled curation capacity"):
        service.dispatch_canary(Database(), settings, selected)


def test_one_shot_dispatch_reports_a_non_launched_row_as_failure(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
        hf_job_id=None,
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return []

    class Database:
        def query(self, _model):
            return Query()

        def get(self, model, _key):
            return scheduler if model is PaperCurationSchedulerState else selected

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_dispatch_row", lambda *_args: None)
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    with pytest.raises(RuntimeError, match="did not launch"):
        service.dispatch_canary(Database(), settings, selected)


def test_one_shot_dispatch_cannot_bypass_an_automatic_safety_pause(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="daily_token_guardrail",
        first_enabled_at=datetime.now(UTC),
    )

    class Database:
        def get(self, _model, _key):
            return scheduler

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_dispatch_row",
        lambda *_args: pytest.fail("automatic safety pauses must not be bypassed"),
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    with pytest.raises(RuntimeError, match="operator pause"):
        service.dispatch_canary(Database(), settings, selected)


def test_postgres_curation_dispatch_lock_serializes_concurrent_sessions():
    database_url = os.getenv("PWC_AUTONOMOUS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PWC_AUTONOMOUS_TEST_DATABASE_URL is not configured")
    if not (make_url(database_url).database or "").startswith("autonomous_ops_test_"):
        pytest.fail("Curation concurrency test requires a disposable database")
    engine = create_engine(database_url, pool_size=2)
    first_acquired = Event()
    release_first = Event()
    second_acquired = Event()

    def hold_first_lock():
        with Session(engine) as db:
            with curation_dispatch_lock(db):
                first_acquired.set()
                assert release_first.wait(timeout=5)

    def acquire_second_lock():
        assert first_acquired.wait(timeout=5)
        with Session(engine) as db:
            with curation_dispatch_lock(db):
                second_acquired.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(hold_first_lock)
            second = pool.submit(acquire_second_lock)
            assert first_acquired.wait(timeout=5)
            assert second_acquired.wait(timeout=0.2) is False
            release_first.set()
            first.result(timeout=5)
            second.result(timeout=5)
        assert second_acquired.is_set()
    finally:
        engine.dispose()


def test_scheduled_dispatch_fails_closed_before_remote_launch_when_curation_is_disabled(
    monkeypatch,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AutonomousOperatorState,
        AutonomousRun,
        PaperCurationSchedulerState,
    ):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:

        class Database:
            def get(self, model, key):
                if model is Paper:
                    return SimpleNamespace(id=key)
                return session.get(model, key)

            def __getattr__(self, name):
                return getattr(session, name)

        db = Database()
        operations = AutonomousOperationsRepository()
        control = operations.get_control_state(db)
        assert control.manual_mode is True
        session.get(AutonomousOperatorState, "global").manual_mode = False
        state = PaperCurationSchedulerState(
            id=1,
            dispatch_enabled=True,
            first_enabled_at=datetime.now(UTC),
        )
        db.add(state)
        db.commit()
        row = SimpleNamespace(
            id=uuid.uuid4(),
            kind="enrich-paper",
            paper_id=42,
            candidate_id=None,
            trigger="hf-daily-cron",
            policy_version="scheduled-v1",
            status="queued",
        )
        service = CodexPaperJobService()
        launched = False

        def launch(**_values):
            nonlocal launched
            launched = True
            return SimpleNamespace(id="hf-job")

        monkeypatch.setattr(service, "_run_job_with_retry", launch)
        settings = get_settings().model_copy(
            update={
                "codex_jobs_namespace": "example",
                "codex_jobs_token": "hf-token",
                "codex_jobs_openai_api_key": "openai-token",
            }
        )

        service._dispatch_row(db, settings, row)

        assert launched is False
        assert row.status == "queued"
        assert state.pause_condition == "autonomous_policy_denied"
        assert "curation operator is disabled" in state.pause_reason
        control = operations.get_control_state(db)
        assert control.enabled[Operator.CURATION] is False
    engine.dispose()


def test_bootstrap_bundle_is_allowlisted_hashed_and_release_bound(monkeypatch):
    from backend.services import codex_add_evals_service as service_module

    revision = "d" * 40
    monkeypatch.setattr(service_module, "_git_revision", lambda: revision)
    service = CodexPaperJobService()

    bundle = service.bootstrap_bundle(
        SimpleNamespace(repository_sha=revision, bootstrap_bundle_sha256=None)
    )

    assert bundle["revision"] == revision
    assert {item["path"] for item in bundle["files"]} == set(
        service_module.CURATOR_BOOTSTRAP_PATHS
    )
    for item in bundle["files"]:
        content = base64.b64decode(item["content_b64"], validate=True)
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
    with pytest.raises(ValueError, match="active immutable release"):
        service.bootstrap_bundle(
            SimpleNamespace(repository_sha="e" * 40, bootstrap_bundle_sha256=None)
        )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    PaperCurationBootstrapBundle.__table__.create(engine)
    with Session(engine) as db:
        key = service_module._store_bootstrap_bundle(db, revision)
        assert service_module._store_bootstrap_bundle(db, revision) == key
        assert db.query(PaperCurationBootstrapBundle).count() == 1
        stored = db.get(PaperCurationBootstrapBundle, key)
        assert key == service_module._bootstrap_bundle_key(stored.bundle)
        assert service_module._store_bootstrap_bundle(db, "HEAD") is None

        monkeypatch.setattr(service_module, "_git_revision", lambda: "f" * 40)
        bound = SimpleNamespace(
            repository_sha=revision,
            bootstrap_bundle_sha256=key,
            stored_bootstrap_bundle=stored,
        )
        assert service.bootstrap_bundle(bound) == stored.bundle

        stored.bundle = {**stored.bundle, "files": stored.bundle["files"][1:]}
        with pytest.raises(ValueError, match="does not match its key"):
            service.bootstrap_bundle(bound)
    engine.dispose()

    persisted = service_module._curator_bootstrap_bundle(revision)
    persisted["files"][0]["content_b64"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(ValueError, match="hash mismatch"):
        service_module._validated_bootstrap_bundle(
            SimpleNamespace(repository_sha=revision), persisted
        )
