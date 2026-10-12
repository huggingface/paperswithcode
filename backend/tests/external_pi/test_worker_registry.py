import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.models.database import ChatExternalWorker
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRegistry,
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)


def test_worker_restart_can_replace_only_an_expired_instance_lease():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, first = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.register(
            row,
            worker_id="worker-1",
            instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
            release_id="release-a",
            contract_version="external-pi-v1",
            maximum_sessions=8,
            now=now + timedelta(seconds=14),
            lease_seconds=15,
        )

    row, replacement = registry.register(
        row,
        worker_id="worker-1",
        instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        release_id="release-b",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    assert first.generation == 1
    assert replacement.generation == 2
    assert row.instance_id == replacement.instance_id
    assert row.release_id == "release-b"
    assert row.state == "ready"
    assert row.lease_expires_at == now + timedelta(seconds=30)


def test_heartbeat_and_drain_require_the_current_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, stale = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    row, current = registry.register(
        row,
        worker_id="worker-1",
        instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        release_id="release-b",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    with pytest.raises(StaleWorkerClaim):
        registry.heartbeat(
            row,
            claim=stale,
            active_sessions=1,
            now=now + timedelta(seconds=16),
            lease_seconds=15,
        )

    registry.heartbeat(
        row,
        claim=current,
        active_sessions=3,
        now=now + timedelta(seconds=16),
        lease_seconds=15,
    )
    registry.begin_drain(
        row,
        claim=current,
        now=now + timedelta(seconds=17),
        drain_seconds=20,
    )

    assert row.active_sessions == 3
    assert row.state == "draining"
    assert row.lease_expires_at == now + timedelta(seconds=37)
    registry.heartbeat(
        row,
        claim=current,
        active_sessions=2,
        now=now + timedelta(seconds=18),
        lease_seconds=15,
    )
    assert row.active_sessions == 2
    assert row.lease_expires_at == now + timedelta(seconds=37)

    with pytest.raises(WorkerLeaseUnavailable):
        registry.heartbeat(
            row,
            claim=current,
            active_sessions=3,
            now=now + timedelta(seconds=19),
            lease_seconds=15,
        )


def test_live_registration_retry_preserves_capacity_and_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row, first = registry.register(
        None,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    registry.heartbeat(
        row,
        claim=first,
        active_sessions=3,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )

    row, retried = registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=2),
        lease_seconds=15,
    )

    assert retried == first
    assert row.active_sessions == 3
    assert row.lease_expires_at == now + timedelta(seconds=17)


def test_expired_same_instance_id_is_fenced_with_a_new_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row, stale = registry.register(
        None,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    row, current = registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    assert current.generation == stale.generation + 1
    with pytest.raises(StaleWorkerClaim):
        registry.begin_drain(
            row,
            claim=stale,
            now=now + timedelta(seconds=16),
            drain_seconds=20,
        )


def test_expired_claim_cannot_start_or_finish_a_drain():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, claim = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.begin_drain(
            row,
            claim=claim,
            now=now + timedelta(seconds=15),
            drain_seconds=20,
        )

    row.state = "draining"
    with pytest.raises(WorkerLeaseUnavailable):
        registry.mark_offline(
            row,
            claim=claim,
            now=now + timedelta(seconds=15),
        )


def test_drained_worker_can_go_offline_only_after_sessions_finish():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, claim = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    registry.heartbeat(
        row,
        claim=claim,
        active_sessions=1,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )
    registry.begin_drain(
        row,
        claim=claim,
        now=now + timedelta(seconds=2),
        drain_seconds=20,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.mark_offline(row, claim=claim, now=now + timedelta(seconds=3))

    registry.heartbeat(
        row,
        claim=claim,
        active_sessions=0,
        now=now + timedelta(seconds=4),
        lease_seconds=15,
    )
    registry.mark_offline(row, claim=claim, now=now + timedelta(seconds=5))

    assert row.state == "offline"
    assert row.lease_expires_at == now + timedelta(seconds=5)


def test_repository_serializes_and_persists_registration(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    db = Mock()
    monkeypatch.setattr(repository, "load", Mock(return_value=None))
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)

    claim = repository.register(
        db,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    added = db.add.call_args.args[0]
    assert isinstance(added, ChatExternalWorker)
    assert added.worker_id == claim.worker_id
    assert added.instance_id == claim.instance_id
    assert added.generation == claim.generation == 1
    assert added.active_sessions == 0
    assert db.execute.call_count == 1
    db.flush.assert_called_once_with()


def test_repository_persists_heartbeat_and_graceful_drain(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=instance_id,
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=4,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    claim = repository.registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )[1]
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    db = Mock()

    repository.heartbeat(
        db,
        claim=claim,
        active_sessions=1,
        now=now + timedelta(seconds=2),
        lease_seconds=15,
    )
    repository.begin_drain(
        db,
        claim=claim,
        now=now + timedelta(seconds=3),
        drain_seconds=20,
    )
    repository.heartbeat(
        db,
        claim=claim,
        active_sessions=0,
        now=now + timedelta(seconds=4),
        lease_seconds=15,
    )
    repository.mark_offline(
        db,
        claim=claim,
        now=now + timedelta(seconds=5),
    )

    assert row.state == "offline"
    assert row.active_sessions == 0
    assert row.lease_expires_at == now + timedelta(seconds=5)
    assert db.flush.call_count == 4


def test_repository_selects_an_exact_online_ready_claim(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=4,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))

    claim = repository.select_ready_claim(
        Mock(),
        claim=ExternalWorkerClaim(
            "worker-1", row.instance_id, 4, "release-a", "external-pi-v1"
        ),
        now=now,
    )

    assert claim == ExternalWorkerClaim(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        generation=4,
        release_id="release-a",
        contract_version="external-pi-v1",
    )


@pytest.mark.parametrize("state,expires_delta", [("draining", 15), ("ready", 0)])
def test_repository_selector_rejects_non_ready_or_expired_rows(
    monkeypatch, state, expires_delta
):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=4,
        state=state,
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=expires_delta),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))

    with pytest.raises(WorkerLeaseUnavailable):
        repository.select_ready_claim(
            Mock(),
            claim=ExternalWorkerClaim(
                "worker-1",
                row.instance_id,
                4,
                "release-a",
                "external-pi-v1",
            ),
            now=now,
        )


def test_selector_cannot_cross_bind_workers_at_the_same_generation(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    endpoint_claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        1,
        "release-a",
        "external-pi-v1",
    )
    wrong_row = ChatExternalWorker(
        worker_id="worker-2",
        instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state="ready",
        maximum_sessions=8,
        active_sessions=0,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=wrong_row))

    with pytest.raises(StaleWorkerClaim):
        repository.select_ready_claim(Mock(), claim=endpoint_claim, now=now)


@pytest.mark.parametrize(
    "release_id,contract_version",
    [("release-b", "external-pi-v1"), ("release-a", "external-pi-v2")],
)
def test_ready_claim_rejects_stale_release_or_contract(
    monkeypatch, release_id, contract_version
):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id=release_id,
        contract_version=contract_version,
        generation=1,
        state="ready",
        maximum_sessions=8,
        active_sessions=0,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    claim = ExternalWorkerClaim(
        "worker-1", row.instance_id, 1, "release-a", "external-pi-v1"
    )

    with pytest.raises(StaleWorkerClaim):
        repository.require_ready_claim(Mock(), claim=claim, now=now)


def test_ready_claim_rejects_worker_that_became_full(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state="ready",
        maximum_sessions=8,
        active_sessions=8,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    claim = ExternalWorkerClaim(
        "worker-1", row.instance_id, 1, "release-a", "external-pi-v1"
    )

    with pytest.raises(WorkerLeaseUnavailable):
        repository.require_ready_claim(Mock(), claim=claim, now=now)


@pytest.mark.parametrize(
    "change",
    ["missing", "stale", "draining", "full", "generation", "capacity", "active"],
)
def test_readiness_requires_exact_endpoint_and_registry_identity(monkeypatch, change):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=instance_id,
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    claim = ExternalWorkerClaim(
        "worker-1", instance_id, 1, "release-a", "external-pi-v1"
    )
    endpoint_active = 1
    endpoint_maximum = 8
    if change == "missing":
        row = None
    elif change == "stale":
        row.lease_expires_at = now
    elif change == "draining":
        row.state = "draining"
    elif change == "full":
        row.active_sessions = row.maximum_sessions
        endpoint_active = row.maximum_sessions
    elif change == "generation":
        claim = ExternalWorkerClaim(
            "worker-1", instance_id, 2, "release-a", "external-pi-v1"
        )
    elif change == "capacity":
        endpoint_maximum = 7
    elif change == "active":
        endpoint_active = 2
    monkeypatch.setattr(repository, "load", Mock(return_value=row))

    with pytest.raises((WorkerLeaseUnavailable, StaleWorkerClaim)):
        repository.require_endpoint_ready(
            Mock(),
            claim=claim,
            active_sessions=endpoint_active,
            maximum_sessions=endpoint_maximum,
            configured_maximum_sessions=8,
            now=now,
        )


def test_readiness_accepts_exact_unexpired_worker_with_capacity(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=instance_id,
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))

    repository.require_endpoint_ready(
        Mock(),
        claim=ExternalWorkerClaim(
            "worker-1", instance_id, 1, "release-a", "external-pi-v1"
        ),
        active_sessions=1,
        maximum_sessions=8,
        configured_maximum_sessions=8,
        now=now,
    )


@pytest.mark.parametrize("state", ["ready", "draining"])
def test_live_claim_allows_reattach_when_worker_is_full(monkeypatch, state):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state=state,
        maximum_sessions=8,
        active_sessions=8,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    claim = ExternalWorkerClaim(
        "worker-1", row.instance_id, 1, "release-a", "external-pi-v1"
    )

    repository.require_live_claim(Mock(), claim=claim, now=now)


@pytest.mark.parametrize("state", ["offline", "ready"])
def test_live_claim_rejects_unavailable_or_expired_worker(monkeypatch, state):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=1,
        state=state,
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=(now + timedelta(seconds=15) if state == "offline" else now),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    claim = ExternalWorkerClaim(
        "worker-1", row.instance_id, 1, "release-a", "external-pi-v1"
    )

    with pytest.raises(WorkerLeaseUnavailable):
        repository.require_live_claim(Mock(), claim=claim, now=now)


def test_live_claim_rejects_missing_or_stale_full_identity(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        1,
        "release-a",
        "external-pi-v1",
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=None))
    with pytest.raises(StaleWorkerClaim):
        repository.require_live_claim(Mock(), claim=claim, now=now)

    stale = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=claim.instance_id,
        environment="staging",
        release_id="release-b",
        contract_version=claim.contract_version,
        generation=claim.generation,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "load", Mock(return_value=stale))
    with pytest.raises(StaleWorkerClaim):
        repository.require_live_claim(Mock(), claim=claim, now=now)


def test_final_claim_revalidation_refreshes_the_locked_registry_row():
    repository = ChatExternalWorkerRepository(environment="staging")
    db = Mock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    repository.load(db, "worker-1")

    query = db.execute.call_args.args[0]
    assert query.get_execution_options()["populate_existing"] is True


def test_worker_registry_migration_is_additive_and_environment_scoped():
    migration = (
        Path(__file__).parents[2]
        / "database/migrations/add_chat_external_worker_registry.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS chat_external_workers" in migration
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "PRIMARY KEY" in migration
    assert "instance_id UUID NOT NULL UNIQUE" in migration
    assert "generation BIGINT NOT NULL" in migration
    assert "state IN ('ready', 'draining', 'offline')" in migration
    assert "REVOKE ALL ON chat_external_workers FROM paperswithcode_user" in migration
