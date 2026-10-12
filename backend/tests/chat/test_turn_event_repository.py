import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import BigInteger, Column, MetaData, Table, create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateSchema, CreateTable, DropSchema

from backend.models.database import ChatSession, ChatTurnEventChunk, ChatTurnJob
from backend.services.chat_turn_event_repository import (
    JournalLimitExceeded,
    TurnEventJournal,
    UnsequencedJournalEvent,
)
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    ChatTurnEventChunk.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def disposable_postgresql_engine():
    raw_url = os.environ.get("PWC_DISPOSABLE_POSTGRES_URL")
    if raw_url is None:
        pytest.skip("explicit disposable PostgreSQL URL is required")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("PostgreSQL journal proof requires a PostgreSQL URL")
    database = url.database or ""
    if not (
        database.startswith("pwc_disposable_")
        or database.startswith("pwc_bridge_disposable_")
    ):
        pytest.fail("PostgreSQL journal proof requires a disposable pwc database")
    if database in {"paperswithcode_hf", "pwc_staging"}:
        pytest.fail("application databases are forbidden for this proof")

    schema = f"journal_test_{uuid.uuid4().hex}"
    base_engine = create_engine(url, pool_size=4)
    try:
        with base_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = base_engine.execution_options(schema_translate_map={None: schema})
        Table(
            "papers",
            MetaData(),
            Column("id", BigInteger, primary_key=True),
            schema=schema,
        ).create(base_engine)
        ChatSession.__table__.create(engine)
        ChatTurnJob.__table__.create(engine)
        ChatTurnEventChunk.__table__.create(engine)
        yield engine
    finally:
        with base_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        base_engine.dispose()


def _claimed_turn(db: Session) -> tuple[ChatTurnJob, TurnLeaseClaim]:
    session = ChatSession(
        id=uuid.uuid4(),
        hf_user_id="journal-owner",
        hf_username="journal-owner",
        selected_model="model",
    )
    db.add(session)
    job = ChatTurnJob(
        turn_id=uuid.uuid4(),
        chat_session_id=session.id,
        hf_user_id=session.hf_user_id,
        request_id=f"request-{uuid.uuid4()}",
        revision=1,
        dispatch_class="interactive",
        dispatch_route="external-pi",
        state="running",
        worker_id="worker-a",
        worker_generation=7,
        lease_generation=3,
        app_release_id="release-a",
        worker_contract_version="external-pi-v1",
        admitted_at=NOW - timedelta(seconds=2),
        dispatched_at=NOW - timedelta(seconds=2),
        started_at=NOW - timedelta(seconds=1),
        heartbeat_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    db.add(job)
    db.flush()
    return job, TurnLeaseClaim(job.turn_id, "worker-a", 7, 3)


def event(name: str, payload: dict[str, object]) -> UnsequencedJournalEvent:
    return UnsequencedJournalEvent(event=name, payload=payload)


def test_appends_receive_contiguous_sequences_and_reads_start_after_cursor(db):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()

    first = repository.append(
        db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW
    )
    second = repository.append(
        db, claim=claim, events=[event("delta", {"text": "b"})], now=NOW
    )

    assert [frame.sequence for frame in (*first, *second)] == [1, 2]
    assert (
        repository.read_after(db, turn_id=claim.turn_id, after_sequence=1, limit=10)
        == second
    )
    assert job.event_sequence == 2
    assert job.event_bytes == 106


def test_append_rejects_a_stale_lease_generation_without_mutation(db):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()
    stale = TurnLeaseClaim(
        claim.turn_id,
        claim.worker_id,
        claim.worker_generation,
        claim.lease_generation - 1,
    )

    with pytest.raises(StaleTurnClaim):
        repository.append(
            db, claim=stale, events=[event("delta", {"text": "a"})], now=NOW
        )

    assert job.event_sequence == 0
    assert job.event_bytes == 0
    assert db.query(ChatTurnEventChunk).count() == 0


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "events"),
    [
        ("MAX_FRAME_BYTES", 52, [event("delta", {"text": "a"})]),
        (
            "MAX_TURN_BYTES",
            105,
            [
                event("delta", {"text": "a"}),
                event("delta", {"text": "b"}),
            ],
        ),
        (
            "MAX_TURN_EVENTS",
            1,
            [
                event("delta", {"text": "a"}),
                event("delta", {"text": "b"}),
            ],
        ),
    ],
)
def test_limits_are_enforced_before_mutation(
    db, monkeypatch, limit_name, limit_value, events
):
    job, claim = _claimed_turn(db)
    repository = TurnEventJournal()
    monkeypatch.setattr(repository, limit_name, limit_value)

    with pytest.raises(JournalLimitExceeded) as raised:
        repository.append(db, claim=claim, events=events, now=NOW)

    assert raised.value.code == "event_journal_exhausted"
    assert job.event_sequence == 0
    assert job.event_bytes == 0
    assert db.query(ChatTurnEventChunk).count() == 0


def test_terminal_cleanup_has_no_immediate_deletion_bypass(db):
    job, claim = _claimed_turn(db)
    journal = TurnEventJournal()
    journal.append(db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW)
    ChatTurnJobRepository().write_terminal(
        db, claim=claim, state="completed", now=NOW + timedelta(seconds=1)
    )

    assert not hasattr(journal, "delete_terminal")
    assert db.get(ChatTurnJob, claim.turn_id) is job
    assert db.query(ChatTurnEventChunk).count() == 1


def test_durable_terminal_cleanup_waits_for_grace_and_survives_restart(db):
    job, claim = _claimed_turn(db)
    journal = TurnEventJournal()
    journal.append(db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW)
    ChatTurnJobRepository().write_terminal(
        db, claim=claim, state="completed", now=NOW + timedelta(seconds=1)
    )
    db.commit()

    restarted = TurnEventJournal()
    assert (
        restarted.cleanup_due_terminal(
            db,
            now=NOW + timedelta(seconds=300),
            replay_grace_seconds=300,
            limit=100,
        )
        == 0
    )
    assert db.query(ChatTurnEventChunk).count() == 1

    assert (
        restarted.cleanup_due_terminal(
            db,
            now=NOW + timedelta(seconds=301),
            replay_grace_seconds=300,
            limit=100,
        )
        == 1
    )
    assert db.get(ChatTurnJob, claim.turn_id) is not None
    assert db.query(ChatTurnEventChunk).count() == 0


def test_durable_cleanup_never_deletes_nonterminal_journal(db):
    _job, claim = _claimed_turn(db)
    journal = TurnEventJournal()
    journal.append(db, claim=claim, events=[event("delta", {"text": "a"})], now=NOW)

    assert (
        journal.cleanup_due_terminal(
            db,
            now=NOW + timedelta(hours=1),
            replay_grace_seconds=300,
            limit=100,
        )
        == 0
    )
    assert db.query(ChatTurnEventChunk).count() == 1


def test_model_and_migration_define_the_bounded_event_journal():
    table = ChatTurnEventChunk.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    indexes = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in table.indexes
    )
    migration = (
        Path(__file__).parents[2] / "database/migrations/add_chat_turn_event_chunks.sql"
    ).read_text()

    assert str(ChatTurnJob.__table__.c.event_sequence.server_default.arg) == "0"
    assert str(ChatTurnJob.__table__.c.event_bytes.server_default.arg) == "0"
    assert "uq_chat_turn_event_chunk_start" in ddl
    assert "ck_chat_turn_event_chunk_range" in ddl
    assert "idx_chat_turn_event_chunks_after" in indexes
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert (
        "ADD COLUMN IF NOT EXISTS event_sequence INTEGER NOT NULL DEFAULT 0"
        in migration
    )
    assert (
        "ADD COLUMN IF NOT EXISTS event_bytes INTEGER NOT NULL DEFAULT 0" in migration
    )
    assert "CREATE TABLE IF NOT EXISTS chat_turn_event_chunks" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "OWNER TO paperswithcode_user" in migration


def test_terminal_cleanup_index_is_partial_and_migrated():
    indexes = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in ChatTurnJob.__table__.indexes
    )
    migration = (
        Path(__file__).parents[2]
        / "database/migrations/add_chat_turn_terminal_cleanup_index.sql"
    ).read_text()

    assert "idx_chat_turn_jobs_terminal_cleanup" in indexes
    assert "WHERE state IN ('completed','failed','interrupted')" in indexes
    assert "idx_chat_turn_jobs_terminal_cleanup" in migration
    assert "WHERE state IN ('completed','failed','interrupted')" in migration


def test_postgresql_concurrent_appends_lock_one_turn_and_persist_jsonb(
    disposable_postgresql_engine,
):
    engine = disposable_postgresql_engine
    with Session(engine, expire_on_commit=False) as setup:
        _, claim = _claimed_turn(setup)
        setup.commit()

    ready = Barrier(2)

    def append(text: str) -> int:
        with Session(engine) as db:
            ready.wait(timeout=5)
            frame = TurnEventJournal().append(
                db,
                claim=claim,
                events=[event("delta", {"text": text})],
                now=NOW,
            )[0]
            db.commit()
            return frame.sequence

    with ThreadPoolExecutor(max_workers=2) as executor:
        sequences = tuple(executor.map(append, ("a", "b")))

    with Session(engine) as verify:
        frames = TurnEventJournal().read_after(
            verify, turn_id=claim.turn_id, after_sequence=0, limit=10
        )
        after_first = TurnEventJournal().read_after(
            verify, turn_id=claim.turn_id, after_sequence=1, limit=10
        )
        job = verify.get(ChatTurnJob, claim.turn_id)
        chunks = tuple(
            verify.scalars(
                select(ChatTurnEventChunk).order_by(ChatTurnEventChunk.first_sequence)
            )
        )

        assert sorted(sequences) == [1, 2]
        assert [frame.sequence for frame in frames] == [1, 2]
        assert [frame.sequence for frame in after_first] == [2]
        assert {frame.payload["text"] for frame in frames} == {"a", "b"}
        assert job.event_sequence == 2
        assert job.event_bytes == sum(chunk.payload_bytes for chunk in chunks)
        assert verify.scalar(select(func.count()).select_from(ChatTurnEventChunk)) == 2
        assert all(isinstance(chunk.events, list) for chunk in chunks)


def test_postgresql_rejects_stale_and_limits_before_terminal_cleanup(
    disposable_postgresql_engine,
):
    engine = disposable_postgresql_engine
    with Session(engine, expire_on_commit=False) as setup:
        _, claim = _claimed_turn(setup)
        setup.commit()

    stale = TurnLeaseClaim(
        claim.turn_id,
        claim.worker_id,
        claim.worker_generation,
        claim.lease_generation - 1,
    )
    with Session(engine) as db:
        with pytest.raises(StaleTurnClaim):
            TurnEventJournal().append(
                db,
                claim=stale,
                events=[event("delta", {"text": "stale"})],
                now=NOW,
            )
        job = db.get(ChatTurnJob, claim.turn_id)
        assert (job.event_sequence, job.event_bytes) == (0, 0)
        assert db.scalar(select(func.count()).select_from(ChatTurnEventChunk)) == 0

    limit_cases = (
        ("MAX_FRAME_BYTES", 52, [event("delta", {"text": "a"})]),
        (
            "MAX_TURN_BYTES",
            105,
            [event("delta", {"text": "a"}), event("delta", {"text": "b"})],
        ),
        (
            "MAX_TURN_EVENTS",
            1,
            [event("delta", {"text": "a"}), event("delta", {"text": "b"})],
        ),
    )
    for limit_name, limit_value, events in limit_cases:
        journal = TurnEventJournal()
        setattr(journal, limit_name, limit_value)
        with Session(engine) as db:
            with pytest.raises(JournalLimitExceeded) as raised:
                journal.append(db, claim=claim, events=events, now=NOW)
            job = db.get(ChatTurnJob, claim.turn_id)
            assert raised.value.code == "event_journal_exhausted"
            assert (job.event_sequence, job.event_bytes) == (0, 0)
            assert db.scalar(select(func.count()).select_from(ChatTurnEventChunk)) == 0

    with Session(engine) as db:
        journal = TurnEventJournal()
        journal.append(
            db, claim=claim, events=[event("delta", {"text": "kept"})], now=NOW
        )
        ChatTurnJobRepository().write_terminal(
            db, claim=claim, state="completed", now=NOW + timedelta(seconds=1)
        )
        assert (
            journal.cleanup_due_terminal(
                db,
                now=NOW + timedelta(seconds=301),
                replay_grace_seconds=300,
                limit=100,
            )
            == 1
        )
        db.commit()

    with Session(engine) as verify:
        job = verify.get(ChatTurnJob, claim.turn_id)
        assert job.state == "completed"
        assert job.event_sequence == 1
        assert verify.scalar(select(func.count()).select_from(ChatTurnEventChunk)) == 0
