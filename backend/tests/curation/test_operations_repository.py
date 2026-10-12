import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event

import pytest
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousAction,
    AutonomousControlEvent,
    AutonomousIncidentAttempt,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
    ChatProviderRuntimeState,
    ChatReliabilityBaseline,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    AutonomousStateConflict,
    DryRunMutation,
    IncidentAttemptLimit,
    ManualModeEnabled,
    Operator,
    OperatorDisabled,
    RepairLeaseUnavailable,
    RunContext,
    StaleRepairLease,
)


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
MIGRATION = (
    Path(__file__).parents[2] / "database/migrations/add_autonomous_operations.sql"
)
CURATION_MIGRATION = (
    Path(__file__).parents[2]
    / "database/migrations/add_curation_autonomous_operator.sql"
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        AutonomousOperatorState,
        AutonomousRun,
        AutonomousAction,
        AutonomousControlEvent,
        AutonomousRepairLease,
        AutonomousIncidentAttempt,
        ChatReliabilityBaseline,
        ChatProviderRuntimeState,
    ):
        table.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def postgres_engine():
    database_url = os.getenv("PWC_AUTONOMOUS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PWC_AUTONOMOUS_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    if not (parsed.database or "").startswith("autonomous_ops_test_"):
        pytest.fail("PostgreSQL autonomy tests require a disposable test database")
    engine = create_engine(database_url, pool_size=8)
    cleanup_sql = """
        DROP SCHEMA IF EXISTS staging CASCADE;
        DROP TABLE IF EXISTS autonomous_alert_delivery CASCADE;
        DROP TABLE IF EXISTS chat_provider_runtime_state CASCADE;
        DROP TABLE IF EXISTS chat_reliability_baseline CASCADE;
        DROP TABLE IF EXISTS autonomous_incident_attempt CASCADE;
        DROP TABLE IF EXISTS autonomous_repair_lease CASCADE;
        DROP TABLE IF EXISTS autonomous_control_event CASCADE;
        DROP TABLE IF EXISTS autonomous_action CASCADE;
        DROP TABLE IF EXISTS autonomous_budget_reservation CASCADE;
        DROP TABLE IF EXISTS autonomous_run CASCADE;
        DROP TABLE IF EXISTS autonomous_execution_intent CASCADE;
        DROP TABLE IF EXISTS autonomous_operator_state CASCADE;
        DROP FUNCTION IF EXISTS reject_autonomous_append_only_mutation() CASCADE;
    """
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(cleanup_sql)
            cursor.execute(MIGRATION.read_text())
            cursor.execute(MIGRATION.read_text())
        connection.commit()
    finally:
        connection.close()
    try:
        yield engine
    finally:
        connection = engine.raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(cleanup_sql)
            connection.commit()
        finally:
            connection.close()
            engine.dispose()


def _context(operator: Operator = Operator.CRON_HEALTH) -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        operator=operator,
        dry_run=False,
        manifest_revision="manifest-v1",
    )


def test_operator_switches_are_independent_and_default_disabled(db):
    repository = AutonomousOperationsRepository()

    initial = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=initial.revision,
        actor="admin:owner",
        now=NOW,
    )

    state = repository.get_control_state(db)
    assert state.manual_mode is True
    assert state.enabled == {
        Operator.SUBMISSIONS: True,
        Operator.CURATION: False,
        Operator.CRON_HEALTH: False,
        Operator.CHAT_RELIABILITY: False,
    }
    assert db.query(AutonomousControlEvent).count() == 1


def test_manual_mode_blocks_direct_repository_mutation(db):
    repository = AutonomousOperationsRepository()
    context = _context()
    repository.append_run(db, context=context, status="completed", now=NOW)

    with pytest.raises(ManualModeEnabled):
        repository.append_action(
            db,
            context=context,
            capability="retry_declared_cron",
            reason_code="stale_data",
            resource_kind="declared_cron",
            resource_identifier="refresh-trending",
            before_digest="a" * 64,
            after_digest="b" * 64,
            now=NOW,
        )

    assert db.query(AutonomousAction).count() == 0


def test_runs_and_actions_are_append_only(db):
    repository = AutonomousOperationsRepository()
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    context = _context(Operator.SUBMISSIONS)
    repository.append_run(db, context=context, status="completed", now=NOW)
    action_id = repository.append_action(
        db,
        context=context,
        capability="review_submission",
        reason_code="primary_evidence",
        resource_kind="pending_edit",
        resource_identifier="42",
        before_digest="a" * 64,
        after_digest="b" * 64,
        now=NOW,
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            update(AutonomousRun)
            .where(AutonomousRun.id == context.run_id)
            .values(status="failed")
        )
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(delete(AutonomousAction).where(AutonomousAction.id == action_id))
        db.commit()


def test_release_sha_must_match_runs_durable_published_action(db):
    repository = AutonomousOperationsRepository()
    state = repository.get_control_state(db)
    state = repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    repository.set_operator_enabled(
        db,
        operator=Operator.CRON_HEALTH,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    context = _context()
    repository.append_run(db, context=context, status="completed", now=NOW)
    sha = "a" * 40
    repository.append_action(
        db,
        context=context,
        capability="repair_declared_cron_source",
        reason_code="published",
        resource_kind="source_repair",
        resource_identifier="example_job",
        before_digest="b" * 64,
        after_digest=sha256(sha.encode()).hexdigest(),
        now=NOW,
    )

    assert repository.has_published_repair(
        db, context=context, sha_digest=sha256(sha.encode()).hexdigest()
    )
    assert not repository.has_published_repair(db, context=context, sha_digest="c" * 64)


def test_control_events_and_incident_attempts_are_append_only(db):
    repository = AutonomousOperationsRepository(clock=lambda _db: NOW)
    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CHAT_RELIABILITY,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    attempt_id = repository.reserve_chat_repair_attempt(
        db, context=context, signature="a" * 64
    )
    event_id = db.query(AutonomousControlEvent.id).first()[0]
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(
            update(AutonomousIncidentAttempt)
            .where(AutonomousIncidentAttempt.id == attempt_id)
            .values(signature="b" * 64)
        )
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(
            delete(AutonomousControlEvent).where(AutonomousControlEvent.id == event_id)
        )
        db.commit()


def test_global_repair_lease_expires_and_release_is_compare_and_swap(db):
    clock = [NOW]
    repository = AutonomousOperationsRepository(clock=lambda _db: clock[0])
    first = _context(Operator.CRON_HEALTH)
    second = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=first, status="completed", now=NOW)
    repository.append_run(db, context=second, status="completed", now=NOW)

    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    for operator in (Operator.CRON_HEALTH, Operator.CHAT_RELIABILITY):
        state = repository.get_control_state(db)
        repository.set_operator_enabled(
            db,
            operator=operator,
            enabled=True,
            expected_revision=state.revision,
            actor="admin:owner",
            now=NOW,
        )

    first_lease = repository.acquire_repair_lease(
        db, context=first, ttl=timedelta(minutes=10)
    )
    with pytest.raises(RepairLeaseUnavailable):
        repository.acquire_repair_lease(db, context=second, ttl=timedelta(minutes=10))

    clock[0] = NOW + timedelta(minutes=11)
    replacement = repository.acquire_repair_lease(
        db,
        context=second,
        ttl=timedelta(minutes=10),
    )
    assert replacement.lease_id != first_lease.lease_id
    with pytest.raises(StaleRepairLease):
        repository.release_repair_lease(
            db, lease_id=first_lease.lease_id, owner_run_id=first.run_id
        )
    assert repository.release_repair_lease(
        db, lease_id=replacement.lease_id, owner_run_id=second.run_id
    )


def test_repair_lease_rejects_ineligible_and_mismatched_run_contexts(db):
    repository = AutonomousOperationsRepository(clock=lambda _db: NOW)
    submissions = _context(Operator.SUBMISSIONS)
    repository.append_run(db, context=submissions, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    with pytest.raises(ValueError, match="not eligible"):
        repository.acquire_repair_lease(
            db, context=submissions, ttl=timedelta(minutes=10)
        )

    cron = _context(Operator.CRON_HEALTH)
    repository.append_run(db, context=cron, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CRON_HEALTH,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    with pytest.raises(ValueError, match="context mismatches"):
        repository.acquire_repair_lease(
            db,
            context=replace(cron, manifest_revision="forged-revision"),
            ttl=timedelta(minutes=10),
        )


def test_incident_attempts_use_a_six_hour_window(db):
    clock = [NOW]
    repository = AutonomousOperationsRepository(clock=lambda _db: clock[0])
    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CHAT_RELIABILITY,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    signature = "a" * 64

    attempt_id = repository.reserve_chat_repair_attempt(
        db, context=context, signature=signature
    )
    assert repository.owns_chat_repair_attempt(
        db,
        context=context,
        signature=signature,
        attempt_id=attempt_id,
    )
    clock[0] = NOW + timedelta(hours=5, minutes=59)
    repository.reserve_chat_repair_attempt(db, context=context, signature=signature)

    with pytest.raises(IncidentAttemptLimit):
        repository.reserve_chat_repair_attempt(db, context=context, signature=signature)

    clock[0] = NOW + timedelta(hours=6)
    repository.reserve_chat_repair_attempt(db, context=context, signature=signature)
    assert repository.count_chat_repair_attempts(db, signature=signature) == 2


def test_chat_attempt_reservation_rejects_manual_disabled_and_wrong_context(db):
    repository = AutonomousOperationsRepository(clock=lambda _db: NOW)
    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)

    with pytest.raises(ManualModeEnabled):
        repository.reserve_chat_repair_attempt(db, context=context, signature="a" * 64)

    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    with pytest.raises(OperatorDisabled):
        repository.reserve_chat_repair_attempt(db, context=context, signature="a" * 64)

    cron_context = _context(Operator.CRON_HEALTH)
    repository.append_run(db, context=cron_context, status="completed", now=NOW)
    with pytest.raises(ValueError, match="chat-reliability"):
        repository.reserve_chat_repair_attempt(
            db, context=cron_context, signature="a" * 64
        )


def test_baseline_and_provider_state_store_only_content_free_fields(db):
    repository = AutonomousOperationsRepository()

    baseline = repository.qualify_chat_baseline(
        db,
        sha="1" * 40,
        actor="admin:owner",
        expected_revision=0,
        now=NOW,
    )
    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CHAT_RELIABILITY,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    provider = repository.set_chat_provider_state(
        db,
        context=context,
        environment="staging",
        manifest_revision="provider-v1",
        expected_state_revision=0,
        active_provider="huggingface",
        reason_code="qualified_fallback",
        now=NOW,
    )
    observed = repository.get_chat_provider_state(db, environment="staging")

    assert baseline.sha == "1" * 40
    assert provider.active_provider == "huggingface"
    assert observed is provider
    assert not hasattr(baseline, "content")
    assert set(provider.__table__.columns.keys()) == {
        "environment",
        "manifest_revision",
        "state_revision",
        "active_provider",
        "reason_code",
        "updated_at",
    }
    assert db.query(AutonomousAction).count() == 1
    assert db.query(AutonomousControlEvent).count() == 3


def test_provider_state_cannot_bypass_manual_mode_or_context_binding(db):
    repository = AutonomousOperationsRepository()
    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)
    kwargs = {
        "context": context,
        "environment": "staging",
        "manifest_revision": "provider-v1",
        "expected_state_revision": 0,
        "active_provider": "huggingface",
        "reason_code": "qualified_fallback",
        "now": NOW,
    }

    with pytest.raises(ManualModeEnabled):
        repository.set_chat_provider_state(db, **kwargs)

    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CHAT_RELIABILITY,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    with pytest.raises(DryRunMutation):
        repository.set_chat_provider_state(
            db, **{**kwargs, "context": replace(context, dry_run=True)}
        )
    wrong = _context(Operator.CRON_HEALTH)
    repository.append_run(db, context=wrong, status="completed", now=NOW)
    with pytest.raises(ValueError, match="chat-reliability"):
        repository.set_chat_provider_state(db, **{**kwargs, "context": wrong})


def test_baseline_and_provider_updates_require_compare_and_swap(db):
    repository = AutonomousOperationsRepository()
    repository.qualify_chat_baseline(
        db,
        sha="1" * 40,
        actor="admin:owner",
        expected_revision=0,
        now=NOW,
    )
    with pytest.raises(AutonomousStateConflict):
        repository.qualify_chat_baseline(
            db,
            sha="2" * 40,
            actor="admin:owner",
            expected_revision=0,
            now=NOW,
        )

    context = _context(Operator.CHAT_RELIABILITY)
    repository.append_run(db, context=context, status="completed", now=NOW)
    state = repository.get_control_state(db)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.CHAT_RELIABILITY,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    provider_args = {
        "context": context,
        "environment": "staging",
        "manifest_revision": "provider-v1",
        "expected_state_revision": 0,
        "active_provider": "huggingface",
        "reason_code": "qualified_fallback",
        "now": NOW,
    }
    repository.set_chat_provider_state(db, **provider_args)
    with pytest.raises(AutonomousStateConflict):
        repository.set_chat_provider_state(db, **provider_args)


def test_content_free_boundaries_reject_free_text_and_secret_shaped_values(db):
    repository = AutonomousOperationsRepository()
    state = repository.get_control_state(db)
    with pytest.raises(ValueError, match="actor"):
        repository.set_manual_mode(
            db,
            enabled=False,
            expected_revision=state.revision,
            actor="the user said hello",
            now=NOW,
        )

    with pytest.raises(ValueError, match="run is invalid"):
        repository.append_run(
            db,
            context=replace(
                _context(Operator.SUBMISSIONS), manifest_revision="hf_secret"
            ),
            status="completed",
            now=NOW,
        )

    context = _context(Operator.SUBMISSIONS)
    repository.append_run(db, context=context, status="completed", now=NOW)
    repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    state = repository.get_control_state(db)
    repository.set_operator_enabled(
        db,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    invalid_actions = (
        ("user said hello", "42"),
        ("primary_evidence", "hf_supersecret"),
        ("sk-secretvalue", "42"),
        ("a" * 65, "42"),
    )
    for reason_code, resource_identifier in invalid_actions:
        with pytest.raises(ValueError, match="invalid"):
            repository.append_action(
                db,
                context=context,
                capability="review_submission",
                reason_code=reason_code,
                resource_kind="pending_edit",
                resource_identifier=resource_identifier,
                before_digest="a" * 64,
                after_digest="b" * 64,
                now=NOW,
            )


def test_postgres_migration_is_rerunnable_and_ledgers_reject_truncate(
    postgres_engine,
):
    repository = AutonomousOperationsRepository()
    context = _context(Operator.CRON_HEALTH)
    with Session(postgres_engine) as db:
        repository.append_run(db, context=context, status="completed", now=NOW)
        db.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("TRUNCATE autonomous_run CASCADE"))
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(AutonomousRun)) == 1


def test_curation_migration_cannot_fall_through_to_public_schema(postgres_engine):
    migration_sql = (
        CURATION_MIGRATION.read_text(encoding="utf-8")
        .strip()
        .removeprefix("BEGIN;")
        .removesuffix("COMMIT;")
        .strip()
    )
    connection = postgres_engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.autonomous_operator_state "
                "WHERE operator = 'curation'"
            )
            cursor.execute(
                "ALTER TABLE public.autonomous_operator_state "
                "DROP CONSTRAINT autonomous_operator_state_operator_check; "
                "ALTER TABLE public.autonomous_operator_state "
                "ADD CONSTRAINT autonomous_operator_state_operator_check CHECK ("
                "operator IN ("
                "'global','submissions','cron_health','chat_reliability'"
                "))"
            )
            cursor.execute(
                "CREATE TABLE public.autonomous_alert_delivery ("
                "operator VARCHAR(32), "
                "CONSTRAINT autonomous_alert_delivery_operator_check CHECK ("
                "operator IS NULL OR operator IN ("
                "'submissions','cron_health','chat_reliability'"
                ")))"
            )
            cursor.execute("CREATE SCHEMA staging")
            for relation in (
                "autonomous_operator_state",
                "autonomous_execution_intent",
                "autonomous_run",
                "autonomous_budget_reservation",
                "autonomous_action",
            ):
                cursor.execute(
                    f"CREATE TABLE staging.{relation} "
                    f"(LIKE public.{relation} INCLUDING ALL)"
                )
            cursor.execute("SET LOCAL search_path = staging,public")
            cursor.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.autonomous_operator_state'::regclass "
                "AND conname = 'autonomous_operator_state_operator_check'"
            )
            before = cursor.fetchone()[0]
            cursor.execute("SAVEPOINT curation_migration")
            with pytest.raises(
                postgres_engine.dialect.dbapi.Error,
                match="missing staging.autonomous_alert_delivery prerequisite",
            ):
                cursor.execute(migration_sql)
            cursor.execute("ROLLBACK TO SAVEPOINT curation_migration")
            cursor.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'public.autonomous_operator_state'::regclass "
                "AND conname = 'autonomous_operator_state_operator_check'"
            )
            after = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM public.autonomous_operator_state "
                "WHERE operator = 'curation'"
            )
            assert cursor.fetchone()[0] == 0
            assert after == before
    finally:
        connection.rollback()
        connection.close()


def test_postgres_serializes_baseline_attempts_leases_and_manual_mode(
    postgres_engine,
):
    baseline_barrier = Barrier(2)

    def qualify(sha: str, actor: str) -> str:
        with Session(postgres_engine) as db:
            baseline_barrier.wait()
            try:
                AutonomousOperationsRepository().qualify_chat_baseline(
                    db,
                    sha=sha,
                    actor=actor,
                    expected_revision=0,
                    now=NOW,
                )
                db.commit()
                return "qualified"
            except AutonomousStateConflict:
                db.rollback()
                return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        baseline_outcomes = sorted(
            pool.map(
                lambda args: qualify(*args),
                (("1" * 40, "admin:one"), ("2" * 40, "admin:two")),
            )
        )
    assert baseline_outcomes == ["qualified", "stale"]

    repository = AutonomousOperationsRepository()
    chat_contexts = [_context(Operator.CHAT_RELIABILITY) for _ in range(3)]
    cron_context = _context(Operator.CRON_HEALTH)
    with Session(postgres_engine) as db:
        for context in (*chat_contexts, cron_context):
            repository.append_run(db, context=context, status="completed", now=NOW)
        state = repository.get_control_state(db)
        state = repository.set_manual_mode(
            db,
            enabled=False,
            expected_revision=state.revision,
            actor="admin:integration",
            now=NOW,
        )
        state = repository.set_operator_enabled(
            db,
            operator=Operator.CHAT_RELIABILITY,
            enabled=True,
            expected_revision=state.revision,
            actor="admin:integration",
            now=NOW,
        )
        state = repository.set_operator_enabled(
            db,
            operator=Operator.CRON_HEALTH,
            enabled=True,
            expected_revision=state.revision,
            actor="admin:integration",
            now=NOW,
        )
        control_revision = state.revision
        db.commit()

    attempt_barrier = Barrier(3)

    def reserve_attempt(context: RunContext) -> str:
        with Session(postgres_engine) as db:
            attempt_barrier.wait()
            try:
                repository.reserve_chat_repair_attempt(
                    db, context=context, signature="a" * 64
                )
                db.commit()
                return "reserved"
            except IncidentAttemptLimit:
                db.rollback()
                return "limited"

    with ThreadPoolExecutor(max_workers=3) as pool:
        attempt_outcomes = sorted(pool.map(reserve_attempt, chat_contexts))
    assert attempt_outcomes == ["limited", "reserved", "reserved"]

    lease_barrier = Barrier(2)

    def acquire_lease(context: RunContext) -> str:
        with Session(postgres_engine) as db:
            lease_barrier.wait()
            try:
                repository.acquire_repair_lease(
                    db, context=context, ttl=timedelta(minutes=10)
                )
                db.commit()
                return "acquired"
            except RepairLeaseUnavailable:
                db.rollback()
                return "unavailable"

    with ThreadPoolExecutor(max_workers=2) as pool:
        lease_outcomes = sorted(
            pool.map(acquire_lease, (chat_contexts[0], cron_context))
        )
    assert lease_outcomes == ["acquired", "unavailable"]

    disable_locked = Event()
    provider_started = Event()
    allow_disable_commit = Event()

    def disable_manual_mode() -> None:
        with Session(postgres_engine) as db:
            repository.set_manual_mode(
                db,
                enabled=True,
                expected_revision=control_revision,
                actor="admin:integration",
                now=NOW,
            )
            disable_locked.set()
            assert allow_disable_commit.wait(timeout=5)
            db.commit()

    def switch_provider() -> str:
        assert disable_locked.wait(timeout=5)
        with Session(postgres_engine) as db:
            provider_started.set()
            try:
                repository.set_chat_provider_state(
                    db,
                    context=chat_contexts[0],
                    environment="staging",
                    manifest_revision="provider-v1",
                    expected_state_revision=0,
                    active_provider="huggingface",
                    reason_code="qualified_fallback",
                    now=NOW,
                )
                db.commit()
                return "switched"
            except ManualModeEnabled:
                db.rollback()
                return "manual"

    with ThreadPoolExecutor(max_workers=2) as pool:
        disable_future = pool.submit(disable_manual_mode)
        provider_future = pool.submit(switch_provider)
        assert provider_started.wait(timeout=5)
        allow_disable_commit.set()
        disable_future.result(timeout=5)
        assert provider_future.result(timeout=5) == "manual"
