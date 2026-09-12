from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from backend.models.database import (
    ChatExecutorCell,
    ChatExecutorClaim,
    ChatExecutorKeyRevocation,
    ChatExecutorManifest,
    ChatExecutorNonce,
    ChatExecutorRegistration,
    ChatExecutorRollbackAudit,
    ChatExecutorShard,
)
from backend.services.chat_executor_registry import (
    ChatExecutorRegistry,
    ExecutorAuthorizationRejected,
    ExecutorCircuitConflict,
    ExecutorClaimUnavailable,
    ExecutorRollbackRejected,
    ExecutorStorageUnavailable,
)


MIGRATION = (
    Path(__file__).parents[1]
    / "database/migrations/add_chat_executor_registrations.sql"
)
TABLES = (
    ChatExecutorManifest,
    ChatExecutorCell,
    ChatExecutorShard,
    ChatExecutorRegistration,
    ChatExecutorNonce,
    ChatExecutorClaim,
    ChatExecutorKeyRevocation,
    ChatExecutorRollbackAudit,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in TABLES:
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def file_sessions(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'executor-registry.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    for model in TABLES:
        model.__table__.create(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _digest(byte: str) -> str:
    return byte * 64


def _database_now(db: Session) -> datetime:
    value = db.scalar(select(func.current_timestamp()))
    assert value is not None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _seed(
    db: Session,
    *,
    registration_state: str = "ready",
    environment_generation: int = 3,
    shard_generation: int = 7,
) -> tuple[ChatExecutorRegistry, ChatExecutorRegistration]:
    repository = ChatExecutorRegistry()
    now = _database_now(db)
    previous = ChatExecutorManifest(
        digest=_digest("a"),
        parent_digest=None,
        image_digest=_digest("1"),
        environment_binary_digest=_digest("2"),
        daemon_digest=_digest("3"),
        source_commit=_digest("4"),
        protocol_version=6,
        schema_digest=_digest("5"),
        qualification_status="qualified",
        compatibility_state="compatible",
        qualification_evidence_ref="qualification/previous.json",
        ready_capacity=0,
        compatibility_expires_at=now + timedelta(hours=24),
        created_at=now - timedelta(hours=1),
    )
    current = ChatExecutorManifest(
        digest=_digest("b"),
        parent_digest=previous.digest,
        image_digest=_digest("6"),
        environment_binary_digest=_digest("7"),
        daemon_digest=_digest("8"),
        source_commit=_digest("9"),
        protocol_version=7,
        schema_digest=_digest("c"),
        qualification_status="qualified",
        compatibility_state="current",
        qualification_evidence_ref="qualification/current.json",
        ready_capacity=1,
        compatibility_expires_at=None,
        created_at=now,
    )
    cell = ChatExecutorCell(
        cell_id="cell-v1",
        selected_manifest_digest=current.digest,
        circuit_state="closed",
        circuit_revision=1,
        key_epoch=11,
        rollback_epoch=0,
        created_at=now,
        updated_at=now,
    )
    shard = ChatExecutorShard(
        id=uuid.uuid4(),
        cell_id=cell.cell_id,
        shard_id="shard-v1",
        generation=shard_generation,
        state="ready",
        ready_capacity=1,
        created_at=now,
        updated_at=now,
    )
    cell.active_shard_id = shard.id
    registration = ChatExecutorRegistration(
        id=uuid.uuid4(),
        environment_id="environment-v1",
        environment_generation=environment_generation,
        cell_id=cell.cell_id,
        shard_id=shard.id,
        shard_generation=shard_generation,
        public_key_id=_digest("d"),
        public_noise_key={"suite": "noise_hybrid_ik_v1", "public": "only"},
        authorization_key_id="issuer-current",
        key_epoch=cell.key_epoch,
        manifest_digest=current.digest,
        state=registration_state,
        assigned_session_id=None,
        last_seen_at=now,
        expires_at=now + timedelta(hours=23),
        created_at=now,
        updated_at=now,
    )
    db.add_all([previous, current, cell, shard, registration])
    db.flush()
    return repository, registration


def _liveness_nonce(
    db: Session,
    repository: ChatExecutorRegistry,
    registration: ChatExecutorRegistration,
    *,
    digest: str | None = None,
) -> str:
    value = digest or _digest("e")
    repository.issue_nonce(
        db,
        nonce_digest=value,
        purpose="liveness",
        environment_id=registration.environment_id,
        environment_generation=registration.environment_generation,
        shard_id=registration.shard_id,
        shard_generation=registration.shard_generation,
        key_epoch=registration.key_epoch,
        ttl_seconds=2,
        retention_seconds=3600,
    )
    return value


def test_migration_is_metadata_only_and_audit_is_append_only():
    sql = MIGRATION.read_text()
    for table in (
        "chat_executor_cells",
        "chat_executor_shards",
        "chat_executor_registrations",
        "chat_executor_claims",
        "chat_executor_nonces",
        "chat_executor_manifests",
        "chat_executor_key_revocations",
        "chat_executor_rollback_audits",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    lowered = sql.lower()
    assert "plaintext" not in lowered
    assert "command_text" not in lowered
    assert "tool_payload" not in lowered
    assert "grant select, insert on chat_executor_rollback_audits" in lowered
    assert "revoke update, delete on chat_executor_rollback_audits" in lowered
    assert "reject_chat_executor_rollback_audit_mutation" in lowered
    assert "pg_column_size(public_noise_key) <= 4096" in lowered
    assert "normal postgresql backup" in lowered
    assert "privileged database administration" in lowered


def test_atomic_claim_rejects_second_turn_and_stale_generation(db):
    repository, registration = _seed(db)
    nonce = _liveness_nonce(db, repository, registration)
    first = repository.claim_workspace(
        db,
        turn_id=uuid.uuid4(),
        registration_id=registration.id,
        environment_generation=registration.environment_generation,
        shard_generation=registration.shard_generation,
        liveness_nonce_digest=nonce,
        claim_generation=1,
        ttl_seconds=240,
    )
    assert first.registration_id == registration.id
    assert registration.state == "claimed"

    with pytest.raises(ExecutorClaimUnavailable):
        repository.claim_workspace(
            db,
            turn_id=uuid.uuid4(),
            registration_id=registration.id,
            environment_generation=registration.environment_generation - 1,
            shard_generation=registration.shard_generation,
            liveness_nonce_digest=_digest("f"),
            claim_generation=1,
            ttl_seconds=240,
        )


def test_liveness_nonce_is_generation_bound_single_use_and_exactly_two_seconds(db):
    repository, registration = _seed(db)
    nonce = _liveness_nonce(db, repository, registration)
    row = db.get(ChatExecutorNonce, nonce)
    assert row is not None
    row.expires_at = _database_now(db)
    db.flush()
    repository.consume_nonce(
        db,
        nonce_digest=nonce,
        purpose="liveness",
        environment_id=registration.environment_id,
        environment_generation=registration.environment_generation,
        shard_id=registration.shard_id,
        shard_generation=registration.shard_generation,
        key_epoch=registration.key_epoch,
    )
    with pytest.raises(ExecutorAuthorizationRejected):
        repository.consume_nonce(
            db,
            nonce_digest=nonce,
            purpose="liveness",
            environment_id=registration.environment_id,
            environment_generation=registration.environment_generation,
            shard_id=registration.shard_id,
            shard_generation=registration.shard_generation,
            key_epoch=registration.key_epoch,
        )

    wrong = _liveness_nonce(db, repository, registration, digest=_digest("0"))
    with pytest.raises(ExecutorAuthorizationRejected):
        repository.consume_nonce(
            db,
            nonce_digest=wrong,
            purpose="liveness",
            environment_id=registration.environment_id,
            environment_generation=registration.environment_generation,
            shard_id=registration.shard_id,
            shard_generation=registration.shard_generation + 1,
            key_epoch=registration.key_epoch,
        )


def test_checkpoint_uses_database_time_and_writes_no_more_than_every_thirty_seconds(db):
    repository, registration = _seed(db)
    original = registration.last_seen_at
    assert not repository.checkpoint_seen(db, registration_id=registration.id)
    assert registration.last_seen_at == original
    registration.last_seen_at = _database_now(db) - timedelta(seconds=31)
    db.flush()
    assert repository.checkpoint_seen(db, registration_id=registration.id)
    assert registration.last_seen_at > original - timedelta(seconds=1)


def test_shard_replacement_requires_ready_capacity_and_drains_old_generation(db):
    repository, registration = _seed(db)
    old_shard = db.get(ChatExecutorShard, registration.shard_id)
    assert old_shard is not None
    replacement = ChatExecutorShard(
        id=uuid.uuid4(),
        cell_id=old_shard.cell_id,
        shard_id=old_shard.shard_id,
        generation=old_shard.generation + 1,
        state="preparing",
        ready_capacity=0,
    )
    db.add(replacement)
    db.flush()
    with pytest.raises(ExecutorClaimUnavailable):
        repository.activate_shard(db, replacement_id=replacement.id)
    replacement.state = "ready"
    replacement.ready_capacity = 1
    db.flush()

    repository.activate_shard(db, replacement_id=replacement.id)

    cell = db.get(ChatExecutorCell, old_shard.cell_id)
    assert cell.active_shard_id == replacement.id
    assert old_shard.state == "draining"
    assert old_shard.drain_deadline_at is not None

    stale = ChatExecutorShard(
        id=uuid.uuid4(),
        cell_id=old_shard.cell_id,
        shard_id=old_shard.shard_id,
        generation=replacement.generation - 2,
        state="ready",
        ready_capacity=1,
    )
    db.add(stale)
    db.flush()
    with pytest.raises(ExecutorClaimUnavailable):
        repository.activate_shard(db, replacement_id=stale.id)


def test_expiry_and_settlement_are_fenced_and_idempotent(db):
    repository, registration = _seed(db)
    claim = repository.claim_workspace(
        db,
        turn_id=uuid.uuid4(),
        registration_id=registration.id,
        environment_generation=registration.environment_generation,
        shard_generation=registration.shard_generation,
        liveness_nonce_digest=_liveness_nonce(db, repository, registration),
        claim_generation=1,
        ttl_seconds=240,
    )
    settlement_id = uuid.uuid4()
    repository.settle_claim(
        db,
        turn_id=claim.turn_id,
        claim_generation=claim.claim_generation,
        settlement_request_id=settlement_id,
        terminal_code="completed",
    )
    repository.settle_claim(
        db,
        turn_id=claim.turn_id,
        claim_generation=claim.claim_generation,
        settlement_request_id=settlement_id,
        terminal_code="completed",
    )
    assert db.get(ChatExecutorClaim, claim.turn_id).state == "settled"
    with pytest.raises(ExecutorClaimUnavailable):
        repository.settle_claim(
            db,
            turn_id=claim.turn_id,
            claim_generation=claim.claim_generation,
            settlement_request_id=uuid.uuid4(),
            terminal_code="completed",
        )


def test_expired_claim_fences_registration(db):
    repository, registration = _seed(db)
    claim = repository.claim_workspace(
        db,
        turn_id=uuid.uuid4(),
        registration_id=registration.id,
        environment_generation=registration.environment_generation,
        shard_generation=registration.shard_generation,
        liveness_nonce_digest=_liveness_nonce(db, repository, registration),
        claim_generation=1,
        ttl_seconds=240,
    )
    row = db.get(ChatExecutorClaim, claim.turn_id)
    row.expires_at = _database_now(db) - timedelta(seconds=1)
    db.flush()

    assert repository.expire_claims(db) == 1
    assert row.state == "invalidated"
    assert row.terminal_code == "claim_expired"
    assert registration.state == "suspect"


def test_disconnect_after_assertion_invalidates_claim_before_attachment(db):
    repository, registration = _seed(db)
    claim = repository.claim_workspace(
        db,
        turn_id=uuid.uuid4(),
        registration_id=registration.id,
        environment_generation=registration.environment_generation,
        shard_generation=registration.shard_generation,
        liveness_nonce_digest=_liveness_nonce(db, repository, registration),
        claim_generation=1,
        ttl_seconds=240,
    )
    repository.mark_suspect(db, registration_id=registration.id)
    with pytest.raises(ExecutorClaimUnavailable):
        repository.validate_attachment(db, claim=claim)
    assert db.get(ChatExecutorClaim, claim.turn_id).state == "invalidated"


def test_concurrent_nonce_redemption_has_exactly_one_winner(file_sessions):
    with file_sessions() as db:
        repository, registration = _seed(db)
        nonce = _liveness_nonce(db, repository, registration)
        expected = (
            registration.environment_id,
            registration.environment_generation,
            registration.shard_id,
            registration.shard_generation,
            registration.key_epoch,
        )
        db.commit()
    barrier = Barrier(2)

    def redeem() -> bool:
        with file_sessions() as db:
            barrier.wait()
            try:
                ChatExecutorRegistry().consume_nonce(
                    db,
                    nonce_digest=nonce,
                    purpose="liveness",
                    environment_id=expected[0],
                    environment_generation=expected[1],
                    shard_id=expected[2],
                    shard_generation=expected[3],
                    key_epoch=expected[4],
                )
                db.commit()
                return True
            except ExecutorAuthorizationRejected:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: redeem(), range(2)))
    assert sorted(outcomes) == [False, True]


def test_nonce_cleanup_keeps_unexpired_rows_and_cannot_revive_consumed_nonce(db):
    repository, registration = _seed(db)
    active = _liveness_nonce(db, repository, registration)
    consumed = _liveness_nonce(db, repository, registration, digest=_digest("f"))
    repository.consume_nonce(
        db,
        nonce_digest=consumed,
        purpose="liveness",
        environment_id=registration.environment_id,
        environment_generation=registration.environment_generation,
        shard_id=registration.shard_id,
        shard_generation=registration.shard_generation,
        key_epoch=registration.key_epoch,
    )
    consumed_row = db.get(ChatExecutorNonce, consumed)
    consumed_row.expires_at = _database_now(db) - timedelta(seconds=2)
    consumed_row.retention_expires_at = _database_now(db) - timedelta(seconds=1)
    db.flush()

    assert repository.cleanup_nonces(db, batch_size=100) == 1
    assert db.get(ChatExecutorNonce, active) is not None
    with pytest.raises(ExecutorAuthorizationRejected):
        repository.consume_nonce(
            db,
            nonce_digest=consumed,
            purpose="liveness",
            environment_id=registration.environment_id,
            environment_generation=registration.environment_generation,
            shard_id=registration.shard_id,
            shard_generation=registration.shard_generation,
            key_epoch=registration.key_epoch,
        )


def test_key_revocation_is_one_transaction_and_idempotent(db):
    repository, registration = _seed(db)
    now = _database_now(db)
    other_cell = ChatExecutorCell(
        cell_id="cell-v1-other",
        selected_manifest_digest=_digest("b"),
        circuit_state="closed",
        circuit_revision=1,
        key_epoch=11,
        rollback_epoch=0,
        created_at=now,
        updated_at=now,
    )
    other_shard = ChatExecutorShard(
        id=uuid.uuid4(),
        cell_id=other_cell.cell_id,
        shard_id="shard-v1-other",
        generation=7,
        state="ready",
        ready_capacity=1,
        created_at=now,
        updated_at=now,
    )
    other_cell.active_shard_id = other_shard.id
    db.add_all([other_cell, other_shard])
    db.flush()
    other_nonce = repository.issue_nonce(
        db,
        nonce_digest=_digest("0"),
        purpose="reconnect",
        environment_id="environment-v1-other",
        environment_generation=3,
        shard_id=other_shard.id,
        shard_generation=other_shard.generation,
        key_epoch=other_cell.key_epoch,
        ttl_seconds=45,
        retention_seconds=3600,
    )
    claim = repository.claim_workspace(
        db,
        turn_id=uuid.uuid4(),
        registration_id=registration.id,
        environment_generation=registration.environment_generation,
        shard_generation=registration.shard_generation,
        liveness_nonce_digest=_liveness_nonce(db, repository, registration),
        claim_generation=1,
        ttl_seconds=240,
    )
    request_id = uuid.uuid4()
    first = repository.revoke_key(
        db,
        request_id=request_id,
        cell_id="cell-v1",
        key_id="issuer-current",
        actor="oncall@example.org",
        reason_class="suspected_compromise",
    )
    repeated = repository.revoke_key(
        db,
        request_id=request_id,
        cell_id="cell-v1",
        key_id="issuer-current",
        actor="oncall@example.org",
        reason_class="suspected_compromise",
    )
    cell = db.get(ChatExecutorCell, "cell-v1")
    assert first.id == repeated.id
    assert cell.key_epoch == 12
    assert cell.circuit_state == "security_hold"
    assert registration.state == "fenced"
    assert db.get(ChatExecutorClaim, claim.turn_id).state == "invalidated"
    assert other_nonce.invalidated_at is None
    assert db.query(ChatExecutorKeyRevocation).count() == 1


def test_circuit_compare_and_set_and_global_canary_lease(db):
    repository, _registration = _seed(db)
    opened = repository.compare_and_set_circuit(
        db,
        cell_id="cell-v1",
        expected_revision=1,
        new_state="open",
    )
    with pytest.raises(ExecutorCircuitConflict):
        repository.compare_and_set_circuit(
            db,
            cell_id="cell-v1",
            expected_revision=1,
            new_state="closed",
        )
    opened.opened_at = _database_now(db) - timedelta(seconds=31)
    db.flush()
    lease = repository.acquire_canary(db, cell_id="cell-v1", ttl_seconds=30)
    with pytest.raises(ExecutorCircuitConflict):
        repository.acquire_canary(db, cell_id="cell-v1", ttl_seconds=30)
    for ordinal in range(3):
        repository.record_canary(
            db,
            cell_id="cell-v1",
            lease_id=lease.lease_id,
            success=True,
            final=ordinal == 2,
        )
    assert db.get(ChatExecutorCell, "cell-v1").circuit_state == "closed"


def test_manifest_rollback_is_lineage_checked_atomic_and_reconciled_by_request(db):
    repository, _registration = _seed(db)
    request_id = uuid.uuid4()
    audit = repository.rollback_manifest(
        db,
        request_id=request_id,
        cell_id="cell-v1",
        target_digest=_digest("a"),
        actor="oncall@example.org",
        reason_class="image_regression",
        qualification_evidence_ref="qualification/previous.json",
    )
    repeated = repository.rollback_manifest(
        db,
        request_id=request_id,
        cell_id="cell-v1",
        target_digest=_digest("a"),
        actor="oncall@example.org",
        reason_class="image_regression",
        qualification_evidence_ref="qualification/previous.json",
    )
    cell = db.get(ChatExecutorCell, "cell-v1")
    assert audit.request_id == repeated.request_id
    assert audit.outcome == "applied"
    assert cell.selected_manifest_digest == _digest("a")
    assert cell.rollback_epoch == 1
    assert repository.reconcile_rollback(db, request_id=request_id).epoch == 1
    assert db.query(ChatExecutorRollbackAudit).count() == 1

    unrelated = ChatExecutorManifest(
        digest=_digest("f"),
        parent_digest=None,
        image_digest=_digest("1"),
        environment_binary_digest=_digest("2"),
        daemon_digest=_digest("3"),
        source_commit=_digest("4"),
        protocol_version=7,
        schema_digest=_digest("5"),
        qualification_status="qualified",
        compatibility_state="compatible",
        qualification_evidence_ref="qualification/unrelated.json",
        ready_capacity=0,
    )
    db.add(unrelated)
    db.flush()
    with pytest.raises(ExecutorRollbackRejected):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=unrelated.digest,
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/unrelated.json",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("qualification_status", "pending"),
        ("compatibility_state", "incompatible"),
        ("revoked_at", datetime.now(UTC)),
        ("compatibility_expires_at", datetime.now(UTC) - timedelta(seconds=1)),
    ),
)
def test_manifest_rollback_rejects_ineligible_lineage_target(db, field, value):
    repository, _registration = _seed(db)
    target = db.get(ChatExecutorManifest, _digest("a"))
    setattr(target, field, value)
    db.flush()

    with pytest.raises(ExecutorRollbackRejected):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=target.digest,
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/previous.json",
        )


def test_manifest_rollback_rejects_security_hold_and_wrong_evidence(db):
    repository, _registration = _seed(db)
    with pytest.raises(ExecutorRollbackRejected):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=_digest("a"),
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/wrong.json",
        )

    cell = db.get(ChatExecutorCell, "cell-v1")
    cell.circuit_state = "security_hold"
    db.flush()
    with pytest.raises(ExecutorRollbackRejected):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=_digest("a"),
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/previous.json",
        )


def test_audit_insert_failure_precedes_pointer_mutation(db, monkeypatch):
    repository, _registration = _seed(db)
    db.commit()
    original_flush = db.flush
    calls = 0

    def fail_audit_flush(*args, **kwargs):
        nonlocal calls
        inserting_audit = any(
            isinstance(row, ChatExecutorRollbackAudit) for row in db.new
        )
        if inserting_audit:
            calls += 1
        if inserting_audit and calls == 1:
            raise DBAPIError.instance(
                "insert", {}, RuntimeError("storage unavailable"), Exception
            )
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_audit_flush)
    with pytest.raises(ExecutorStorageUnavailable):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=_digest("a"),
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/previous.json",
        )
    db.rollback()
    assert db.get(ChatExecutorCell, "cell-v1").selected_manifest_digest == _digest("b")
    assert db.query(ChatExecutorRollbackAudit).count() == 0


def test_pointer_failure_rolls_back_audit_and_pointer_together(db, monkeypatch):
    repository, _registration = _seed(db)
    db.commit()
    original_flush = db.flush
    audit_flushes = 0

    def fail_pointer_flush(*args, **kwargs):
        nonlocal audit_flushes
        if any(isinstance(row, ChatExecutorRollbackAudit) for row in db.new):
            audit_flushes += 1
        elif audit_flushes == 1 and db.dirty:
            raise DBAPIError.instance(
                "update", {}, RuntimeError("storage unavailable"), Exception
            )
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_pointer_flush)
    with pytest.raises(ExecutorStorageUnavailable):
        repository.rollback_manifest(
            db,
            request_id=uuid.uuid4(),
            cell_id="cell-v1",
            target_digest=_digest("a"),
            actor="oncall@example.org",
            reason_class="image_regression",
            qualification_evidence_ref="qualification/previous.json",
        )
    db.rollback()
    assert db.get(ChatExecutorCell, "cell-v1").selected_manifest_digest == _digest("b")
    assert db.query(ChatExecutorRollbackAudit).count() == 0


def test_registry_models_persist_no_private_or_payload_fields():
    columns = {column.name for model in TABLES for column in model.__table__.columns}
    forbidden = {"private_key", "credential", "token", "command", "path", "payload"}
    assert columns.isdisjoint(forbidden)
    assert "public_noise_key" in columns
    assert "nonce_digest" in columns
    assert "outcome" in columns


@pytest.mark.skipif(
    not os.getenv("PWC_EXECUTOR_REGISTRY_TEST_DATABASE_URL"),
    reason="explicit disposable executor registry PostgreSQL URL is required",
)
def test_postgres_migration_enforces_append_only_audit_and_atomic_nonce():
    url = make_url(os.environ["PWC_EXECUTOR_REGISTRY_TEST_DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith(
        "pwc_executor_registry_test_"
    ):
        pytest.fail("executor registry proof requires a disposable PostgreSQL database")
    engine = create_engine(url)
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(MIGRATION.read_text())
            cursor.execute(MIGRATION.read_text())
        connection.commit()
        with engine.begin() as db:
            permissions = db.exec_driver_sql(
                """
                SELECT
                    has_table_privilege(
                        'paperswithcode_user',
                        'chat_executor_rollback_audits',
                        'SELECT'
                    ),
                    has_table_privilege(
                        'paperswithcode_user',
                        'chat_executor_rollback_audits',
                        'INSERT'
                    ),
                    has_table_privilege(
                        'paperswithcode_user',
                        'chat_executor_rollback_audits',
                        'UPDATE'
                    ),
                    has_table_privilege(
                        'paperswithcode_user',
                        'chat_executor_rollback_audits',
                        'DELETE'
                    )
                """
            ).one()
            assert permissions == (True, True, False, False)

            db.exec_driver_sql(
                """
                INSERT INTO chat_executor_manifests (
                    digest, parent_digest, image_digest,
                    environment_binary_digest, daemon_digest, source_commit,
                    protocol_version, schema_digest, qualification_status,
                    compatibility_state, qualification_evidence_ref,
                    ready_capacity
                ) VALUES
                    (%s, NULL, %s, %s, %s, %s, 6, %s, 'qualified',
                     'compatible', 'qualification/previous.json', 0),
                    (%s, %s, %s, %s, %s, %s, 7, %s, 'qualified',
                     'current', 'qualification/current.json', 1)
                """,
                (
                    _digest("a"),
                    _digest("1"),
                    _digest("2"),
                    _digest("3"),
                    _digest("4"),
                    _digest("5"),
                    _digest("b"),
                    _digest("a"),
                    _digest("6"),
                    _digest("7"),
                    _digest("8"),
                    _digest("9"),
                    _digest("c"),
                ),
            )
            db.exec_driver_sql(
                """
                INSERT INTO chat_executor_cells (
                    cell_id, selected_manifest_digest, key_epoch
                ) VALUES ('cell-v1', %s, 11)
                """,
                (_digest("b"),),
            )

            db.exec_driver_sql(
                """
                INSERT INTO chat_executor_rollback_audits (
                    request_id, cell_id, actor, reason_class, source_digest,
                    target_digest, qualification_evidence_ref, outcome, epoch
                ) VALUES (
                    '00000000-0000-0000-0000-000000000001', 'audit-cell',
                    'operator@example.org', 'image_regression', %s, %s,
                    'qualification/previous.json', 'applied', 1
                )
                """,
                (_digest("b"), _digest("a")),
            )
            db.exec_driver_sql(
                """
                INSERT INTO chat_executor_nonces (
                    nonce_digest, purpose, environment_id, environment_generation,
                    shard_id, shard_generation, key_epoch, expires_at,
                    retention_expires_at
                ) VALUES (
                    %s, 'reconnect', 'environment-v1', 3,
                    '00000000-0000-0000-0000-000000000010', 7, 11,
                    current_timestamp + interval '45 seconds',
                    current_timestamp + interval '1 hour'
                )
                """,
                (_digest("e"),),
            )

        raw = engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                for statement in (
                    "UPDATE chat_executor_rollback_audits SET actor='other'",
                    "DELETE FROM chat_executor_rollback_audits",
                    "UPDATE chat_executor_manifests SET image_digest='"
                    + _digest("f")
                    + "'",
                ):
                    cursor.execute("SAVEPOINT append_only_proof")
                    with pytest.raises(
                        Exception, match="append-only|lineage is immutable"
                    ):
                        cursor.execute(statement)
                    cursor.execute("ROLLBACK TO SAVEPOINT append_only_proof")

                cursor.execute("SET ROLE paperswithcode_user")
                cursor.execute(
                    """
                    INSERT INTO chat_executor_rollback_audits (
                        request_id, cell_id, actor, reason_class, source_digest,
                        target_digest, qualification_evidence_ref, outcome, epoch
                    ) VALUES (
                        '00000000-0000-0000-0000-000000000002', 'audit-cell',
                        'operator@example.org', 'image_regression', %s, %s,
                        'qualification/previous.json', 'applied', 2
                    )
                    """,
                    (_digest("b"), _digest("a")),
                )
                cursor.execute("SELECT count(*) FROM chat_executor_rollback_audits")
                assert cursor.fetchone() == (2,)
                cursor.execute("SAVEPOINT role_permission_proof")
                with pytest.raises(Exception, match="permission denied"):
                    cursor.execute(
                        "UPDATE chat_executor_rollback_audits SET actor='other'"
                    )
                cursor.execute("ROLLBACK TO SAVEPOINT role_permission_proof")
                cursor.execute("RESET ROLE")
            raw.commit()
        finally:
            raw.rollback()
            raw.close()

        barrier = Barrier(2)

        def redeem_reconnect_nonce() -> bool:
            with Session(engine) as db:
                barrier.wait()
                try:
                    ChatExecutorRegistry.consume_nonce(
                        db,
                        nonce_digest=_digest("e"),
                        purpose="reconnect",
                        environment_id="environment-v1",
                        environment_generation=3,
                        shard_id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
                        shard_generation=7,
                        key_epoch=11,
                    )
                    db.commit()
                    return True
                except ExecutorAuthorizationRejected:
                    db.rollback()
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: redeem_reconnect_nonce(), range(2)))
        assert sorted(outcomes) == [False, True]

        rollback_request_id = uuid.uuid4()
        barrier = Barrier(2)

        def rollback_manifest() -> uuid.UUID:
            with Session(engine) as db:
                barrier.wait()
                row = ChatExecutorRegistry().rollback_manifest(
                    db,
                    request_id=rollback_request_id,
                    cell_id="cell-v1",
                    target_digest=_digest("a"),
                    actor="oncall@example.org",
                    reason_class="image_regression",
                    qualification_evidence_ref="qualification/previous.json",
                )
                db.commit()
                return row.request_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            rollback_ids = list(pool.map(lambda _index: rollback_manifest(), range(2)))
        assert rollback_ids == [rollback_request_id, rollback_request_id]
        with Session(engine) as db:
            cell = db.get(ChatExecutorCell, "cell-v1")
            assert cell.selected_manifest_digest == _digest("a")
            assert cell.rollback_epoch == 1

        revocation_request_id = uuid.uuid4()
        barrier = Barrier(2)

        def revoke_key() -> uuid.UUID:
            with Session(engine) as db:
                barrier.wait()
                row = ChatExecutorRegistry().revoke_key(
                    db,
                    request_id=revocation_request_id,
                    cell_id="cell-v1",
                    key_id="issuer-current",
                    actor="oncall@example.org",
                    reason_class="suspected_compromise",
                )
                db.commit()
                return row.id

        with ThreadPoolExecutor(max_workers=2) as pool:
            revocation_ids = list(pool.map(lambda _index: revoke_key(), range(2)))
        assert revocation_ids[0] == revocation_ids[1]
        with Session(engine) as db:
            cell = db.get(ChatExecutorCell, "cell-v1")
            assert cell.key_epoch == 12
            assert cell.circuit_state == "security_hold"
            assert db.query(ChatExecutorKeyRevocation).count() == 1
    finally:
        connection.rollback()
        connection.close()
        engine.dispose()
