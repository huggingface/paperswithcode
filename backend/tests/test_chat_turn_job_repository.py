import inspect
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.models.database import ChatSession, ChatTurnJob
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    ChatTurnJobRepository,
    IdempotencyMismatch,
    InvalidTurnTransition,
    StaleTurnClaim,
    TurnNotClaimable,
    classify_expired_turn,
)

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("state", "failure_code", "expected"),
    [
        ("leased", None, "dispatch_failed"),
        ("running", None, "external_worker_lost"),
        ("waiting_model", None, "external_worker_lost"),
        ("waiting_tool", None, "execution_lost"),
        ("cancelling", None, "cancel_control_missing"),
        ("running", "event_journal_exhausted", "event_journal_exhausted"),
        ("waiting_tool", "execution_lost", "execution_lost"),
    ],
)
def test_expired_turn_failure_classification_is_typed_and_content_free(
    state, failure_code, expected
):
    job = SimpleNamespace(state=state, failure_code=failure_code)

    assert classify_expired_turn(job) == expected


def test_expired_reconciliation_candidate_scan_is_bounded_and_nonlocking():
    seen = []

    class Rows:
        def tuples(self):
            return ()

    class DB:
        def execute(self, query):
            seen.append(query)
            return Rows()

    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    assert repository.load_expired_candidates(DB(), now=NOW, limit=17) == ()

    sql = str(seen[0].compile(dialect=postgresql.dialect()))
    assert "LIMIT" in sql
    assert "chat_session_id" in sql
    assert "turn_id" in sql
    assert "FOR UPDATE" not in sql


def test_expired_reconciliation_does_not_mutate_a_newer_worker_generation(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    old_claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="external-worker",
        worker_generation=7,
        now=NOW,
        lease_seconds=1,
    )
    job.worker_generation = 8
    job.lease_generation += 1
    job.lease_expires_at = NOW + timedelta(seconds=60)
    db.flush()

    with pytest.raises(StaleTurnClaim, match="fenced"):
        repository.interrupt_expired_claim(
            db,
            claim=old_claim,
            failure_code="external_worker_lost",
            now=NOW + timedelta(seconds=2),
        )

    assert (job.state, job.worker_generation, job.lease_generation) == (
        "leased",
        8,
        old_claim.lease_generation + 1,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _session(db: Session, *, owner: str = "owner-1") -> ChatSession:
    row = ChatSession(
        id=uuid.uuid4(),
        hf_user_id=owner,
        hf_username=owner,
        selected_model="model",
    )
    db.add(row)
    db.flush()
    return row


def _admit(
    repository: ChatTurnJobRepository,
    db: Session,
    session: ChatSession,
    *,
    turn_id: uuid.UUID | None = None,
    request_id: str | None = None,
    capacity: int = 8,
):
    return repository.admit(
        db,
        turn_id=turn_id or uuid.uuid4(),
        chat_session_id=session.id,
        hf_user_id=session.hf_user_id,
        request_id=request_id or f"request-{uuid.uuid4()}",
        revision=1,
        dispatch_class="interactive",
        dispatch_route="external-pi",
        app_release_id="release-a",
        worker_contract_version="external-pi-v1",
        now=NOW,
        emergency_capacity=capacity,
    )


def test_turn_job_model_has_durable_state_and_owner_guards():
    table = ChatTurnJob.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    indexes = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in table.indexes
    )

    assert table.primary_key.columns.keys() == ["turn_id"]
    assert table.c.request_id.unique
    assert "revision > 0" in ddl
    assert "lease_generation > 0" in ddl
    assert "chat_turn_jobs_failure_code_check" in ddl
    assert "failure_code ~ '^[a-z0-9][a-z0-9_]{0,63}$'" in ddl
    assert (
        "admitted', 'leased', 'running', 'waiting_model', 'waiting_tool', "
        "'cancelling', 'completed', 'failed', 'interrupted"
    ) in ddl
    assert "uq_chat_turn_jobs_nonterminal_owner" in indexes
    assert (
        "state IN "
        "('admitted','leased','running','waiting_model','waiting_tool','cancelling')"
    ) in indexes


def test_model_created_schema_rejects_unsafe_failure_codes(db):
    session = _session(db)
    db.add(
        ChatTurnJob(
            turn_id=uuid.uuid4(),
            chat_session_id=session.id,
            hf_user_id=session.hf_user_id,
            request_id="unsafe-failure-code",
            revision=1,
            dispatch_class="interactive",
            dispatch_route="external-pi",
            state="admitted",
            app_release_id="release-a",
            worker_contract_version="external-pi-v1",
            admitted_at=NOW,
            failure_code="Unsafe Code!",
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_matching_admission_is_idempotent_and_mismatch_fails_closed(db):
    lock_order = []
    repository = ChatTurnJobRepository(
        advisory_locker=lambda _db, key: lock_order.append(key)
    )
    session = _session(db)
    turn_id = uuid.uuid4()

    first = _admit(repository, db, session, turn_id=turn_id, request_id="request-1")
    replay = _admit(repository, db, session, turn_id=turn_id, request_id="request-1")

    assert first.created is True
    assert replay.created is False
    assert replay.job.turn_id == turn_id
    assert lock_order == ["chat-user:owner-1", "chat-global-active-turns"] * 2
    with pytest.raises(IdempotencyMismatch):
        _admit(repository, db, session, request_id="request-1")
    with pytest.raises(IdempotencyMismatch):
        _admit(repository, db, session, turn_id=turn_id, request_id="request-2")
    assert db.query(ChatTurnJob).count() == 1


def test_preflight_locks_in_order_and_returns_exact_request_replay(db):
    lock_order = []
    repository = ChatTurnJobRepository(
        advisory_locker=lambda _db, key: lock_order.append(key)
    )
    session = _session(db)
    admitted = _admit(repository, db, session, request_id="stable-request").job
    lock_order.clear()

    replay = repository.preflight_admission(
        db,
        hf_user_id=session.hf_user_id,
        request_id="stable-request",
        chat_session_id=session.id,
        emergency_capacity=1,
    )

    assert replay.existing_job is admitted
    assert lock_order == ["chat-user:owner-1", "chat-global-active-turns"]


def test_preflight_rejects_identity_contention_and_exact_capacity_without_writes(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    owner = _session(db)
    other = _session(db, owner="owner-2")
    third = _session(db, owner="owner-3")
    admitted = _admit(repository, db, owner, request_id="owner-request").job

    with pytest.raises(IdempotencyMismatch):
        repository.preflight_admission(
            db,
            hf_user_id=other.hf_user_id,
            request_id=admitted.request_id,
            chat_session_id=None,
            emergency_capacity=3,
        )
    with pytest.raises(IdempotencyMismatch):
        repository.preflight_admission(
            db,
            hf_user_id=owner.hf_user_id,
            request_id=admitted.request_id,
            chat_session_id=other.id,
            emergency_capacity=3,
        )
    with pytest.raises(AccountBusy):
        repository.preflight_admission(
            db,
            hf_user_id=owner.hf_user_id,
            request_id="new-owner-request",
            chat_session_id=owner.id,
            emergency_capacity=3,
        )

    _admit(repository, db, other, request_id="other-request", capacity=3)
    before = db.query(ChatTurnJob).count()
    with pytest.raises(ChatOverload):
        repository.preflight_admission(
            db,
            hf_user_id=third.hf_user_id,
            request_id="third-request",
            chat_session_id=None,
            emergency_capacity=2,
        )
    assert db.query(ChatTurnJob).count() == before


def test_external_capacity_preflight_defers_only_the_global_capacity_lock(db):
    lock_order = []
    repository = ChatTurnJobRepository(
        advisory_locker=lambda _db, key: lock_order.append(key)
    )
    occupied = _session(db, owner="occupied-owner")
    candidate = _session(db, owner="candidate-owner")
    _admit(repository, db, occupied, request_id="occupied-request", capacity=1)
    lock_order.clear()

    preflight = repository.preflight_admission(
        db,
        hf_user_id=candidate.hf_user_id,
        request_id="candidate-request",
        chat_session_id=candidate.id,
        emergency_capacity=1,
        defer_global_capacity=True,
    )

    assert preflight.global_capacity_authorized is False
    assert lock_order == ["chat-user:candidate-owner"]
    with pytest.raises(ChatOverload):
        repository.authorize_global_capacity(db, preflight)
    assert lock_order == [
        "chat-user:candidate-owner",
        "chat-global-active-turns",
    ]


@pytest.mark.parametrize(
    ("field", "different"),
    [
        ("revision", 2),
        ("dispatch_route", "different-route"),
        ("app_release_id", "release-b"),
        ("worker_contract_version", "external-pi-v2"),
    ],
)
def test_preflighted_replay_validates_full_dispatch_identity(db, field, different):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    admitted = _admit(repository, db, session, request_id="exact-replay").job
    preflight = repository.preflight_admission(
        db,
        hf_user_id=session.hf_user_id,
        request_id=admitted.request_id,
        chat_session_id=session.id,
        emergency_capacity=1,
    )
    identity = {
        "turn_id": admitted.turn_id,
        "chat_session_id": session.id,
        "hf_user_id": session.hf_user_id,
        "request_id": admitted.request_id,
        "revision": admitted.revision,
        "dispatch_class": admitted.dispatch_class,
        "dispatch_route": admitted.dispatch_route,
        "app_release_id": admitted.app_release_id,
        "worker_contract_version": admitted.worker_contract_version,
        "now": NOW,
    }
    identity[field] = different

    with pytest.raises(IdempotencyMismatch):
        repository.admit_preflighted(db, preflight=preflight, **identity)

    assert db.query(ChatTurnJob).count() == 1


def test_preflighted_new_admission_does_not_relock_or_recount(db):
    lock_order = []
    repository = ChatTurnJobRepository(
        advisory_locker=lambda _db, key: lock_order.append(key)
    )
    session = _session(db)
    preflight = repository.preflight_admission(
        db,
        hf_user_id=session.hf_user_id,
        request_id="preflighted-new",
        chat_session_id=session.id,
        emergency_capacity=1,
    )

    admission = repository.admit_preflighted(
        db,
        preflight=preflight,
        turn_id=uuid.uuid4(),
        chat_session_id=session.id,
        hf_user_id=session.hf_user_id,
        request_id="preflighted-new",
        revision=1,
        dispatch_class="interactive",
        dispatch_route="external-pi",
        app_release_id="release-a",
        worker_contract_version="external-pi-v1",
        now=NOW,
    )

    assert admission.created is True
    assert preflight.emergency_capacity == 1
    assert (
        "emergency_capacity"
        not in inspect.signature(repository.admit_preflighted).parameters
    )
    assert lock_order == ["chat-user:owner-1", "chat-global-active-turns"]


def test_preflighted_admission_rejects_a_different_session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'preflight-session.db'}")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    with Session(engine, expire_on_commit=False) as seed:
        session = _session(seed)
        seed.commit()
        session_id = session.id
        owner = session.hf_user_id

    with (
        Session(engine, expire_on_commit=False) as first,
        Session(engine, expire_on_commit=False) as second,
    ):
        preflight = repository.preflight_admission(
            first,
            hf_user_id=owner,
            request_id="cross-session",
            chat_session_id=session_id,
            emergency_capacity=1,
        )

        with pytest.raises(ValueError, match="transaction"):
            repository.admit_preflighted(
                second,
                preflight=preflight,
                turn_id=uuid.uuid4(),
                chat_session_id=session_id,
                hf_user_id=owner,
                request_id="cross-session",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="external-pi",
                app_release_id="release-a",
                worker_contract_version="external-pi-v1",
                now=NOW,
            )

        assert second.query(ChatTurnJob).count() == 0


@pytest.mark.parametrize("finish_transaction", ["commit", "rollback"])
def test_preflighted_admission_rejects_a_finished_transaction(db, finish_transaction):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    db.commit()
    preflight = repository.preflight_admission(
        db,
        hf_user_id=session.hf_user_id,
        request_id=f"after-{finish_transaction}",
        chat_session_id=session.id,
        emergency_capacity=1,
    )
    getattr(db, finish_transaction)()

    with pytest.raises(ValueError, match="transaction"):
        repository.admit_preflighted(
            db,
            preflight=preflight,
            turn_id=uuid.uuid4(),
            chat_session_id=session.id,
            hf_user_id=session.hf_user_id,
            request_id=f"after-{finish_transaction}",
            revision=1,
            dispatch_class="interactive",
            dispatch_route="external-pi",
            app_release_id="release-a",
            worker_contract_version="external-pi-v1",
            now=NOW,
        )

    assert db.query(ChatTurnJob).count() == 0


def test_admission_rejects_busy_owner_and_capacity_edge_without_insert(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    owner_session = _session(db)
    other_session = _session(db, owner="owner-2")
    third_session = _session(db, owner="owner-3")
    _admit(repository, db, owner_session, capacity=2)

    with pytest.raises(AccountBusy) as busy:
        _admit(repository, db, owner_session, capacity=2)
    _admit(repository, db, other_session, capacity=2)
    with pytest.raises(ChatOverload) as overload:
        _admit(repository, db, third_session, capacity=2)

    assert busy.value.code == "account_busy"
    assert overload.value.code == "chat_overload"
    assert db.query(ChatTurnJob).count() == 2


def test_concurrent_same_owner_admission_has_one_typed_winner(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'turn-jobs.db'}",
        connect_args={"check_same_thread": False},
    )
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    session_ids = [uuid.uuid4(), uuid.uuid4()]
    with Session(engine) as setup:
        setup.add_all(
            [
                ChatSession(
                    id=session_id,
                    hf_user_id="shared-owner",
                    hf_username="shared-owner",
                    selected_model="model",
                )
                for session_id in session_ids
            ]
        )
        setup.commit()

    ready = Barrier(2)
    transaction_lock = Lock()  # boundary double for PG transaction advisory locks

    def attempt(index: int) -> str:
        repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
        with Session(engine, expire_on_commit=False) as transaction:
            session = transaction.get(ChatSession, session_ids[index])
            ready.wait()
            with transaction_lock:
                try:
                    _admit(repository, transaction, session)
                    transaction.commit()
                    return "admitted"
                except AccountBusy as error:
                    transaction.rollback()
                    return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    assert sorted(outcomes) == ["account_busy", "admitted"]
    with Session(engine) as verify:
        assert verify.query(ChatTurnJob).count() == 1


def test_claim_mutations_are_fenced_and_terminal_is_idempotent(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    admitted = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=admitted.turn_id,
        worker_id="worker-1",
        worker_generation=7,
        now=NOW + timedelta(seconds=1),
        lease_seconds=15,
    )

    assert claim.lease_generation == 1
    assert repository.load_by_request(db, admitted.request_id).state == "leased"
    repository.transition(
        db, claim=claim, state="running", now=NOW + timedelta(seconds=2)
    )
    repository.heartbeat(
        db, claim=claim, now=NOW + timedelta(seconds=3), lease_seconds=15
    )
    repository.transition(
        db,
        claim=claim,
        state="waiting_model",
        now=NOW + timedelta(seconds=4),
        last_agent_session_id=uuid.uuid4(),
        last_resume_boundary_id="entry-42",
    )
    stale_claims = (
        claim.__class__(
            turn_id=claim.turn_id,
            worker_id="worker-2",
            worker_generation=claim.worker_generation,
            lease_generation=claim.lease_generation,
        ),
        claim.__class__(
            turn_id=claim.turn_id,
            worker_id=claim.worker_id,
            worker_generation=claim.worker_generation + 1,
            lease_generation=claim.lease_generation,
        ),
        claim.__class__(
            turn_id=claim.turn_id,
            worker_id=claim.worker_id,
            worker_generation=claim.worker_generation,
            lease_generation=claim.lease_generation + 1,
        ),
    )
    for stale in stale_claims:
        with pytest.raises(StaleTurnClaim):
            repository.heartbeat(
                db, claim=stale, now=NOW + timedelta(seconds=5), lease_seconds=15
            )
        with pytest.raises(StaleTurnClaim):
            repository.transition(
                db,
                claim=stale,
                state="running",
                now=NOW + timedelta(seconds=5),
            )
        with pytest.raises(StaleTurnClaim):
            repository.write_terminal(
                db,
                claim=stale,
                state="failed",
                now=NOW + timedelta(seconds=5),
                failure_code="worker_failed",
            )

    terminal = repository.write_terminal(
        db,
        claim=claim,
        state="completed",
        now=NOW + timedelta(seconds=6),
    )
    replay = repository.write_terminal(
        db,
        claim=claim,
        state="completed",
        now=NOW + timedelta(seconds=7),
    )
    assert terminal is replay
    assert terminal.terminal_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=6)
    assert terminal.lease_expires_at is None
    with pytest.raises(TurnNotClaimable):
        repository.claim(
            db,
            turn_id=admitted.turn_id,
            worker_id="worker-1",
            worker_generation=7,
            now=NOW + timedelta(seconds=8),
            lease_seconds=15,
        )


def test_stop_before_claim_claims_once_and_blocks_later_dispatch(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job

    claim = repository.request_cancelling(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:control",
        worker_generation=17,
        now=NOW,
        lease_seconds=30,
    )
    repeated = repository.request_cancelling(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:replacement",
        worker_generation=18,
        now=NOW + timedelta(seconds=1),
        lease_seconds=30,
    )

    assert claim is not None
    assert repeated == claim
    assert repository.load_by_turn(db, job.turn_id).state == "cancelling"
    with pytest.raises(TurnNotClaimable):
        repository.claim(
            db,
            turn_id=job.turn_id,
            worker_id="orchestrator",
            worker_generation=1,
            now=NOW + timedelta(seconds=2),
            lease_seconds=30,
        )


def test_dispatch_failure_claims_and_interrupts_expired_admission_atomically(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    admitted = _admit(repository, db, session).job

    terminal = repository.interrupt_dispatch_failed(
        db,
        turn_id=admitted.turn_id,
        worker_id="dispatch-coordinator",
        worker_generation=4,
        lease_seconds=30,
        admitted_before=NOW + timedelta(seconds=5),
        now=NOW + timedelta(seconds=10),
    )
    replay = repository.interrupt_dispatch_failed(
        db,
        turn_id=admitted.turn_id,
        worker_id="dispatch-coordinator",
        worker_generation=4,
        lease_seconds=30,
        admitted_before=NOW + timedelta(seconds=5),
        now=NOW + timedelta(seconds=11),
    )

    assert terminal is replay
    assert terminal is not None
    assert terminal.state == "interrupted"
    assert terminal.failure_code == "dispatch_failed"
    assert terminal.worker_id == "dispatch-coordinator"
    assert terminal.worker_generation == 4
    assert terminal.lease_generation == 1
    assert terminal.lease_expires_at is None


@pytest.mark.parametrize(
    "admitted_before",
    [NOW - timedelta(microseconds=1), NOW],
    ids=["fresh", "exact_boundary"],
)
def test_dispatch_failure_preserves_still_dispatchable_admission(db, admitted_before):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    admitted = _admit(repository, db, session).job

    result = repository.interrupt_dispatch_failed(
        db,
        turn_id=admitted.turn_id,
        worker_id="dispatch-coordinator",
        worker_generation=4,
        lease_seconds=30,
        admitted_before=admitted_before,
        now=NOW + timedelta(seconds=10),
    )

    assert result is None
    assert admitted.state == "admitted"
    assert admitted.worker_id is None
    assert admitted.worker_generation is None
    assert admitted.lease_generation is None
    assert admitted.terminal_at is None
    assert admitted.failure_code is None


def test_stop_after_claim_preserves_other_process_fence(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:other-process",
        worker_generation=23,
        now=NOW,
        lease_seconds=30,
    )
    repository.transition(db, claim=claim, state="running", now=NOW)

    cancelled_claim = repository.request_cancelling(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:this-process",
        worker_generation=24,
        now=NOW + timedelta(seconds=1),
        lease_seconds=30,
    )

    assert cancelled_claim == claim
    assert repository.claim_for(repository.load_by_turn(db, job.turn_id)) == claim


def test_missing_cancel_control_terminalizes_exact_claim_once(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.request_cancelling(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:control",
        worker_generation=29,
        now=NOW,
        lease_seconds=1,
    )
    assert claim is not None

    interrupted = repository.interrupt_control_missing(
        db, claim=claim, now=NOW + timedelta(seconds=2)
    )
    repeated = repository.interrupt_control_missing(
        db, claim=claim, now=NOW + timedelta(seconds=3)
    )

    assert interrupted is repeated
    assert interrupted.state == "interrupted"
    assert interrupted.failure_code == "cancel_control_missing"
    assert repository.claim_for(interrupted) == claim


def test_stop_expired_or_terminal_turn_is_not_reclaimed(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:old-process",
        worker_generation=31,
        now=NOW,
        lease_seconds=1,
    )
    with pytest.raises(StaleTurnClaim):
        repository.request_cancelling(
            db,
            turn_id=job.turn_id,
            worker_id="local-runner:new-process",
            worker_generation=32,
            now=NOW + timedelta(seconds=1),
            lease_seconds=30,
        )
    assert repository.claim_for(repository.load_by_turn(db, job.turn_id)) == claim

    repository.interrupt_exact_expired(
        db, turn_id=job.turn_id, now=NOW + timedelta(seconds=1)
    )
    assert (
        repository.request_cancelling(
            db,
            turn_id=job.turn_id,
            worker_id="local-runner:new-process",
            worker_generation=32,
            now=NOW + timedelta(seconds=2),
            lease_seconds=30,
        )
        is None
    )


def test_expired_lease_is_interrupted_and_never_claimable(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="worker-1",
        worker_generation=1,
        now=NOW,
        lease_seconds=5,
    )

    with pytest.raises(StaleTurnClaim):
        repository.write_terminal(
            db,
            claim=claim,
            state="completed",
            now=NOW + timedelta(seconds=5),
        )

    interrupted = repository.interrupt_expired(
        db, now=NOW + timedelta(seconds=5), limit=10
    )

    assert interrupted == 1
    loaded = repository.load_by_turn(db, job.turn_id)
    assert loaded.state == "interrupted"
    assert loaded.failure_code == "lease_expired"
    assert loaded.lease_expires_at is None
    assert (
        repository.interrupt_expired(db, now=NOW + timedelta(seconds=6), limit=10) == 0
    )
    with pytest.raises(TurnNotClaimable):
        repository.claim(
            db,
            turn_id=job.turn_id,
            worker_id="worker-2",
            worker_generation=1,
            now=NOW + timedelta(seconds=6),
            lease_seconds=5,
        )


def test_exact_expiry_preserves_claim_and_is_idempotent(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="worker-1",
        worker_generation=11,
        now=NOW,
        lease_seconds=5,
    )

    interrupted = repository.interrupt_exact_expired(
        db, turn_id=job.turn_id, now=NOW + timedelta(seconds=5)
    )
    repeated = repository.interrupt_exact_expired(
        db, turn_id=job.turn_id, now=NOW + timedelta(seconds=6)
    )

    assert interrupted is repeated
    assert repository.claim_for(interrupted) == claim
    assert interrupted.state == "interrupted"
    assert interrupted.failure_code == "lease_expired"
    assert interrupted.lease_expires_at is None


def test_exact_expiry_refuses_live_or_incompatible_terminal_job(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="worker-1",
        worker_generation=12,
        now=NOW,
        lease_seconds=10,
    )

    with pytest.raises(StaleTurnClaim):
        repository.interrupt_exact_expired(
            db, turn_id=job.turn_id, now=NOW + timedelta(seconds=9)
        )

    repository.write_terminal(
        db,
        claim=claim,
        state="failed",
        now=NOW + timedelta(seconds=2),
        failure_code="provider_failed",
    )
    with pytest.raises(InvalidTurnTransition):
        repository.interrupt_exact_expired(
            db, turn_id=job.turn_id, now=NOW + timedelta(seconds=11)
        )


def test_crashed_worker_lease_is_visible_before_legacy_projection_expires(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:crashed",
        worker_generation=41,
        now=NOW,
        lease_seconds=30,
    )
    session.active_turn_id = job.turn_id
    session.active_turn_expires_at = NOW + timedelta(seconds=210)
    db.flush()

    expired = repository.load_expired_claims(
        db,
        now=NOW + timedelta(seconds=30),
        hf_user_id="new-owner",
        limit=100,
    )

    assert expired == (job,)
    assert session.active_turn_expires_at > NOW + timedelta(seconds=30)


def test_expired_claim_does_not_consume_live_capacity_at_lease_boundary(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    crashed_session = _session(db, owner="crashed-owner")
    job = _admit(repository, db, crashed_session, capacity=1).job
    repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="local-runner:crashed",
        worker_generation=42,
        now=NOW,
        lease_seconds=30,
    )
    new_session = _session(db, owner="new-owner")

    preflight = repository.preflight_admission(
        db,
        hf_user_id=new_session.hf_user_id,
        request_id="new-request",
        chat_session_id=new_session.id,
        emergency_capacity=1,
        now=NOW + timedelta(seconds=30),
    )

    assert preflight.existing_job is None


def test_expired_claim_batch_prioritizes_request_owner(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    other_session = _session(db, owner="other-owner")
    owner_session = _session(db, owner="request-owner")
    other = _admit(repository, db, other_session, capacity=2).job
    owner = _admit(repository, db, owner_session, capacity=2).job
    repository.claim(
        db,
        turn_id=other.turn_id,
        worker_id="local-runner:other",
        worker_generation=1,
        now=NOW,
        lease_seconds=10,
    )
    repository.claim(
        db,
        turn_id=owner.turn_id,
        worker_id="local-runner:owner",
        worker_generation=1,
        now=NOW,
        lease_seconds=20,
    )

    expired = repository.load_expired_claims(
        db,
        now=NOW + timedelta(seconds=30),
        hf_user_id="request-owner",
        limit=1,
    )

    assert expired == (owner,)


def test_stale_session_cannot_replace_a_newer_committed_claim(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stale-claim.db'}")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    with Session(engine, expire_on_commit=False) as setup:
        session = _session(setup)
        turn_id = _admit(repository, setup, session).job.turn_id
        setup.commit()

    with (
        Session(engine, expire_on_commit=False) as stale,
        Session(engine, expire_on_commit=False) as current,
    ):
        stale_job = repository.load_by_turn(stale, turn_id)
        assert stale_job.state == "admitted"
        stale.commit()
        authoritative = repository.claim(
            current,
            turn_id=turn_id,
            worker_id="worker-current",
            worker_generation=9,
            now=NOW + timedelta(seconds=1),
            lease_seconds=15,
        )
        current.commit()

        with pytest.raises(TurnNotClaimable):
            repository.claim(
                stale,
                turn_id=turn_id,
                worker_id="worker-stale",
                worker_generation=3,
                now=NOW + timedelta(seconds=2),
                lease_seconds=15,
            )
        stale.rollback()

    with Session(engine) as verify:
        row = repository.load_by_turn(verify, turn_id)
        assert row.worker_id == authoritative.worker_id
        assert row.worker_generation == authoritative.worker_generation
        assert row.lease_generation == authoritative.lease_generation


def test_require_live_claim_returns_exact_fence_and_rejects_expiry(db):
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    session = _session(db)
    job = _admit(repository, db, session).job
    claim = repository.claim(
        db,
        turn_id=job.turn_id,
        worker_id="worker-live",
        worker_generation=4,
        now=NOW,
        lease_seconds=15,
    )

    assert repository.require_live_claim(db, claim=claim, now=NOW) is job
    with pytest.raises(ValueError):
        repository.require_live_claim(db, claim=claim, now=NOW.replace(tzinfo=None))
    with pytest.raises(StaleTurnClaim):
        repository.require_live_claim(db, claim=claim, now=NOW + timedelta(seconds=15))


def test_stale_session_cannot_overwrite_a_newer_committed_terminal(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'stale-terminal.db'}")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
    with Session(engine, expire_on_commit=False) as setup:
        session = _session(setup)
        job = _admit(repository, setup, session).job
        claim = repository.claim(
            setup,
            turn_id=job.turn_id,
            worker_id="worker-current",
            worker_generation=9,
            now=NOW,
            lease_seconds=15,
        )
        setup.commit()

    with (
        Session(engine, expire_on_commit=False) as stale,
        Session(engine, expire_on_commit=False) as current,
    ):
        stale_job = repository.load_by_turn(stale, job.turn_id)
        assert stale_job.state == "leased"
        stale.commit()
        # SQLite drops timezone information; restore the PostgreSQL-equivalent
        # loaded value without marking the stale object dirty.
        set_committed_value(stale_job, "lease_expires_at", NOW + timedelta(seconds=15))
        current.execute(
            update(ChatTurnJob)
            .where(ChatTurnJob.turn_id == job.turn_id)
            .values(
                state="completed",
                failure_code=None,
                terminal_at=NOW + timedelta(seconds=1),
                heartbeat_at=NOW + timedelta(seconds=1),
                lease_expires_at=None,
            )
        )
        current.commit()

        with pytest.raises(InvalidTurnTransition):
            repository.write_terminal(
                stale,
                claim=claim,
                state="failed",
                failure_code="stale_worker",
                now=NOW + timedelta(seconds=2),
            )
        stale.rollback()

    with Session(engine) as verify:
        row = repository.load_by_turn(verify, job.turn_id)
        assert row.state == "completed"
        assert row.failure_code is None
        assert row.terminal_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=1)


def test_turn_job_migration_is_guarded_and_preserves_schema_ownership():
    migration = (
        Path(__file__).parents[1] / "database/migrations/add_chat_turn_jobs.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_turn_jobs" in migration
    assert "uq_chat_turn_jobs_nonterminal_owner" in migration
    assert "chat_turn_jobs_failure_code_check" in migration
    assert "failure_code ~ '^[a-z0-9][a-z0-9_]{0,63}$'" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "FROM pwc_staging;" in migration

    migration_readme = (
        Path(__file__).parents[1] / "database/migrations/README.md"
    ).read_text()
    deployment = (Path(__file__).parents[2] / "docs/deployment.md").read_text()
    assert "`add_chat_turn_jobs.sql`" in migration_readme
    assert "`add_chat_turn_jobs.sql`" in deployment
