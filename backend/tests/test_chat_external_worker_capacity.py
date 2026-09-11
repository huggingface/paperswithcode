import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatExternalWorker,
    ChatExternalWorkerReservation,
)
from backend.services.chat_external_worker_capacity import (
    ChatExternalWorkerCapacityRepository,
    ExternalWorkerCapacityUnavailable,
    ExternalWorkerEndpoint,
    external_worker_endpoints,
)
from backend.config import get_settings


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatExternalWorker.__table__.create(engine)
    ChatExternalWorkerReservation.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _worker(db: Session, ordinal: int) -> ExternalWorkerEndpoint:
    worker_id = f"worker-{ordinal}"
    instance_id = uuid.UUID(f"aaaaaaaa-0000-4000-8000-{ordinal:012x}")
    db.add(
        ChatExternalWorker(
            worker_id=worker_id,
            instance_id=instance_id,
            environment="staging",
            release_id="release-a",
            contract_version="external-pi-v1",
            generation=ordinal,
            state="ready",
            maximum_sessions=32,
            active_sessions=0,
            heartbeat_at=NOW,
            lease_expires_at=NOW + timedelta(seconds=30),
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return ExternalWorkerEndpoint(
        endpoint_id=f"endpoint-{ordinal}",
        worker_id=worker_id,
        base_url=f"http://127.0.0.1:{8780 + ordinal}",
        token=str(ordinal) * 32,
    )


def test_fleet_reservations_admit_one_hundred_across_bounded_workers(db):
    endpoints = tuple(_worker(db, ordinal) for ordinal in range(1, 5))
    db.flush()
    repository = ChatExternalWorkerCapacityRepository(environment="staging")

    reservations = [
        repository.reserve(
            db,
            request_id=f"request-{ordinal}",
            endpoints=endpoints,
            contract_version="external-pi-v1",
            now=NOW,
        )
        for ordinal in range(100)
    ]

    assert len({item.endpoint_id for item in reservations}) == 4
    assert all(
        item.worker_claim.worker_id == item.endpoint.worker_id for item in reservations
    )
    assert (
        max(
            sum(item.endpoint_id == endpoint.endpoint_id for item in reservations)
            for endpoint in endpoints
        )
        <= 32
    )


def test_capacity_candidate_locks_only_one_available_worker_without_waiting(db):
    endpoints = tuple(_worker(db, ordinal) for ordinal in range(1, 9))
    db.flush()
    repository = ChatExternalWorkerCapacityRepository(environment="staging")
    statements = []
    scalars = db.scalars

    def capture(statement, *args, **kwargs):
        statements.append(statement)
        return scalars(statement, *args, **kwargs)

    db.scalars = capture  # type: ignore[method-assign]

    repository.reserve(
        db,
        request_id="parallel-admission",
        endpoints=endpoints,
        contract_version="external-pi-v1",
        now=NOW,
    )

    candidate = next(
        statement
        for statement in statements
        if "chat_external_workers" in str(statement)
    )
    sql = str(candidate.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "LIMIT" in sql


def test_capacity_candidate_retries_a_transient_row_lock(db, monkeypatch):
    endpoint = _worker(db, 1)
    db.flush()
    repository = ChatExternalWorkerCapacityRepository(environment="staging")
    scalars = db.scalars
    attempts = 0
    sleeps = []

    def transient_lock(statement, *args, **kwargs):
        nonlocal attempts
        if "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect())):
            attempts += 1
            if attempts == 1:
                return SimpleNamespace(first=lambda: None)
        return scalars(statement, *args, **kwargs)

    db.scalars = transient_lock  # type: ignore[method-assign]
    monkeypatch.setattr(
        "backend.services.chat_external_worker_capacity.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    reserved = repository.reserve(
        db,
        request_id="transient-lock",
        endpoints=(endpoint,),
        contract_version="external-pi-v1",
        now=NOW,
    )

    assert reserved.endpoint == endpoint
    assert attempts == 2
    assert sleeps == [0.01]


def test_capacity_refusal_and_idempotent_reattach_do_not_consume_extra_slots(db):
    endpoint = _worker(db, 1)
    db.flush()
    repository = ChatExternalWorkerCapacityRepository(environment="staging")
    first = repository.reserve(
        db,
        request_id="stable-request",
        endpoints=(endpoint,),
        contract_version="external-pi-v1",
        now=NOW,
    )
    repeated = repository.reserve(
        db,
        request_id="stable-request",
        endpoints=(endpoint,),
        contract_version="external-pi-v1",
        now=NOW,
    )
    for ordinal in range(31):
        repository.reserve(
            db,
            request_id=f"other-{ordinal}",
            endpoints=(endpoint,),
            contract_version="external-pi-v1",
            now=NOW,
        )

    with pytest.raises(ExternalWorkerCapacityUnavailable):
        repository.reserve(
            db,
            request_id="overload",
            endpoints=(endpoint,),
            contract_version="external-pi-v1",
            now=NOW,
        )

    assert repeated == first
    assert db.query(ChatExternalWorkerReservation).count() == 32


def test_bound_reservation_reattaches_to_exact_original_endpoint(db):
    endpoint = _worker(db, 1)
    db.flush()
    repository = ChatExternalWorkerCapacityRepository(environment="staging")
    reserved = repository.reserve(
        db,
        request_id="stable-request",
        endpoints=(endpoint,),
        contract_version="external-pi-v1",
        now=NOW,
    )
    turn_id = uuid.uuid4()
    repository.bind_turn(db, reservation=reserved, turn_id=turn_id, now=NOW)

    attached = repository.require_turn(
        db, turn_id=turn_id, endpoints=(endpoint,), now=NOW
    )

    assert attached.endpoint == endpoint
    assert attached.worker_claim == reserved.worker_claim


def test_topology_is_bounded_typed_and_keeps_tokens_out_of_repr():
    settings = get_settings().model_copy(
        update={
            "chat_external_pi_worker_id": "",
            "chat_external_pi_worker_url": "",
            "chat_external_pi_worker_token": "",
            "chat_external_pi_worker_endpoints": [
                {
                    "endpoint_id": "blue",
                    "worker_id": "worker-blue",
                    "base_url": "http://127.0.0.1:8780",
                    "token": "b" * 32,
                },
                {
                    "endpoint_id": "green",
                    "worker_id": "worker-green",
                    "base_url": "http://127.0.0.1:8781",
                    "token": "g" * 32,
                },
            ],
        }
    )

    endpoints = external_worker_endpoints(settings)

    assert [item.worker_id for item in endpoints] == ["worker-blue", "worker-green"]
    assert "secret-blue" not in repr(endpoints)


def test_legacy_single_endpoint_requires_explicit_worker_identity():
    settings = get_settings().model_copy(
        update={
            "chat_external_pi_worker_endpoints": [],
            "chat_external_pi_worker_id": "worker-legacy",
            "chat_external_pi_worker_url": "http://127.0.0.1:8766",
            "chat_external_pi_worker_token": "l" * 32,
        }
    )

    assert external_worker_endpoints(settings) == (
        ExternalWorkerEndpoint(
            endpoint_id="legacy",
            worker_id="worker-legacy",
            base_url="http://127.0.0.1:8766",
            token="l" * 32,
        ),
    )


def test_capacity_reservation_migration_is_additive_and_environment_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_external_worker_reservations.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS chat_external_worker_reservations" in migration
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "turn_id UUID UNIQUE" in migration
    assert "worker_generation BIGINT NOT NULL" in migration
    assert "chat_external_worker_reservations_worker_generation_check" in migration
    assert "chat_external_worker_reservations_maximum_sessions_check" in migration
    assert (
        "ADD CONSTRAINT chat_external_worker_reservations_worker_generation_check"
        in migration
    )
    assert "VALIDATE CONSTRAINT" in migration
    assert (
        "REVOKE ALL ON chat_external_worker_reservations FROM paperswithcode_user"
        in migration
    )
    assert "idx_chat_external_worker_reservations_unbound_expiry" in migration
    assert "WHERE turn_id IS NULL" in migration

    from backend.models.database import ChatExternalWorkerReservation

    table = ChatExternalWorkerReservation.__table__
    assert {column.name for column in table.columns} == {
        "request_id",
        "turn_id",
        "endpoint_id",
        "worker_id",
        "instance_id",
        "worker_generation",
        "release_id",
        "contract_version",
        "maximum_sessions",
        "reserved_at",
        "expires_at",
    }
    assert {index.name for index in table.indexes} == {
        "idx_chat_external_worker_reservations_capacity",
        "idx_chat_external_worker_reservations_unbound_expiry",
    }
