from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.loadtests import durable_bridge_probe as bridge_probe
from backend.loadtests.durable_bridge_probe import run_durable_bridge_probe
from backend.models.database import ChatMessageRecord, ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import SchemaAudit
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _settings(**updates) -> Settings:
    return Settings(
        environment="staging",
        release_id="release-staging",
        db_search_path="staging,public",
        chat_durable_turn_dispatch_enabled=True,
        chat_worker_contract_version="worker-v1",
        chat_max_concurrency=2,
    ).model_copy(update=updates)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatMessageRecord.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _audit(**updates) -> SchemaAudit:
    values = {
        "schema": True,
        "role": True,
        "owner": True,
        "privileges": True,
        "indexes": True,
        "constraints": True,
    }
    values.update(updates)
    return SchemaAudit(**values)


def test_probe_exercises_admission_ownership_terminal_and_exact_cleanup() -> None:
    factory = _factory()
    with factory() as db:
        unrelated = ChatSession(
            id=uuid.uuid4(),
            hf_user_id="unrelated",
            hf_username="unrelated",
            selected_model="qualification",
        )
        db.add(unrelated)
        db.commit()
        unrelated_id = unrelated.id

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
        overlap_gate=SimpleNamespace(wait=lambda _participant: True),
    )

    assert result.success is True
    assert [(metric.name, metric.success) for metric in result.metrics] == [
        ("bridge.admission", True),
        ("bridge.ownership", True),
        ("bridge.overlap", True),
        ("bridge.terminal", True),
        ("bridge.cleanup", True),
    ]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
        assert db.get(ChatSession, unrelated_id) is not None


def test_probe_without_peer_times_out_and_cleans_up() -> None:
    factory = _factory()
    gate = bridge_probe.TwoPartyOverlapGate()
    started = time.monotonic()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
        overlap_gate=gate,
    )

    assert time.monotonic() - started < 6
    assert result.failure_code == "bridge_overlap_failed"
    assert [(metric.name, metric.success) for metric in result.metrics] == [
        ("bridge.admission", True),
        ("bridge.ownership", True),
        ("bridge.overlap", False),
        ("bridge.terminal", False),
        ("bridge.cleanup", True),
    ]


def test_two_party_overlap_gate_releases_only_two_distinct_participants() -> None:
    gate = bridge_probe.TwoPartyOverlapGate()

    with ThreadPoolExecutor(max_workers=2) as executor:
        released = tuple(executor.map(gate.wait, ("participant-a", "participant-b")))

    assert released == (True, True)
    assert gate.wait("participant-c") is False


def test_two_probes_overlap_only_after_both_running_claims_are_committed(
    tmp_path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'bridge-overlap.db'}",
        connect_args={"check_same_thread": False},
    )
    ChatSession.__table__.create(engine)
    ChatMessageRecord.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    class InspectingTwoPartyGate:
        def __init__(self):
            self.arrived = threading.Barrier(2)
            self.inspected = threading.Barrier(2)
            self.participants: set[str] = set()
            self.snapshots: list[tuple[int, int]] = []
            self.lock = threading.Lock()

        def wait(self, participant: str) -> bool:
            with self.lock:
                assert participant not in self.participants
                self.participants.add(participant)
            self.arrived.wait(timeout=2)
            with factory() as db:
                running = db.scalar(
                    select(func.count())
                    .select_from(ChatTurnJob)
                    .where(ChatTurnJob.state == "running")
                )
                terminal = db.scalar(
                    select(func.count())
                    .select_from(ChatTurnJob)
                    .where(ChatTurnJob.state == "completed")
                )
            with self.lock:
                self.snapshots.append((running or 0, terminal or 0))
            self.inspected.wait(timeout=2)
            return True

    gate = InspectingTwoPartyGate()

    def run(identity: str):
        return run_durable_bridge_probe(
            session_factory=factory,
            settings=_settings(),
            release_id="release-staging",
            worker_contract_version="worker-v1",
            schema_audit=_audit(),
            opaque_identity=identity,
            overlap_gate=gate,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(run, ("loadtest-opaque-a", "loadtest-opaque-b")))

    assert gate.snapshots == [(2, 0), (2, 0)]
    assert all(result.success for result in results)
    assert all(
        [(metric.name, metric.success) for metric in result.metrics]
        == [
            ("bridge.admission", True),
            ("bridge.ownership", True),
            ("bridge.overlap", True),
            ("bridge.terminal", True),
            ("bridge.cleanup", True),
        ]
        for result in results
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 0


def test_probe_refuses_disabled_bridge_before_writing_rows() -> None:
    factory = _factory()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(chat_durable_turn_dispatch_enabled=False),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert result.metrics[-1].name == "bridge.cleanup"
    assert result.metrics[-1].success is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 0


@pytest.mark.parametrize("capacity", [1, 3])
def test_probe_refuses_non_exact_capacity_before_writing_rows(capacity: int) -> None:
    factory = _factory()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(chat_max_concurrency=capacity),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.failure_code == "bridge_refused"
    assert result.metrics[-1].success is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 0


def test_coordinator_preflight_uses_one_supplied_aware_timestamp() -> None:
    decision_now = datetime(2026, 8, 27, 12, 34, tzinfo=UTC)
    observed: list[datetime] = []

    class Repository:
        def lock_admission_authority(self, _db, *, hf_user_id):
            assert hf_user_id == "loadtest-owner"

        def load_expired_claims(self, _db, *, now, hf_user_id, limit):
            assert hf_user_id == "loadtest-owner"
            assert limit == 2
            observed.append(now)
            return ()

        def preflight_admission(self, _db, **kwargs):
            observed.append(kwargs["now"])
            return SimpleNamespace(existing_job=None)

    coordinator = ChatTurnAdmissionCoordinator(
        object(), _settings(), repository=Repository()
    )

    coordinator.preflight(
        hf_user_id="loadtest-owner",
        request_id="loadtest-request",
        requested_session_id=None,
        now=decision_now,
    )

    assert observed == [decision_now, decision_now]


def test_probe_passes_its_locked_expiry_decision_timestamp_to_preflight(
    monkeypatch,
) -> None:
    decision_now = datetime(2026, 8, 27, 12, 34, tzinfo=UTC)
    later = decision_now + timedelta(seconds=1)
    timestamps = iter((decision_now, later, later))
    observed: list[datetime] = []
    coordinator_type = ChatTurnAdmissionCoordinator

    class Clock:
        @classmethod
        def now(cls, _timezone):
            return next(timestamps)

    class RecordingCoordinator(coordinator_type):
        def preflight(self, **kwargs):
            observed.append(kwargs["now"])
            return super().preflight(**kwargs)

    monkeypatch.setattr(bridge_probe, "datetime", Clock)
    monkeypatch.setattr(
        bridge_probe, "ChatTurnAdmissionCoordinator", RecordingCoordinator
    )

    result = run_durable_bridge_probe(
        session_factory=_factory(),
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
        overlap_gate=SimpleNamespace(wait=lambda _participant: True),
    )

    assert result.success is True
    assert observed == [decision_now]


def test_coordinator_preflight_rejects_naive_supplied_timestamp_before_locking() -> (
    None
):
    class Repository:
        def lock_admission_authority(self, *_args, **_kwargs):
            pytest.fail("naive timestamp reached durable admission authority")

    coordinator = ChatTurnAdmissionCoordinator(
        object(), _settings(), repository=Repository()
    )

    with pytest.raises(ValueError, match="timestamp"):
        coordinator.preflight(
            hf_user_id="loadtest-owner",
            request_id="loadtest-request",
            requested_session_id=None,
            now=datetime(2026, 8, 27, 12, 34, tzinfo=UTC).replace(tzinfo=None),
        )


def test_probe_refuses_unrelated_expired_claim_without_changing_its_projection() -> (
    None
):
    factory = _factory()
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    message_id = uuid.uuid4()
    with factory() as db:
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id="unrelated-owner",
                hf_username="unrelated-owner",
                selected_model="qualification",
                active_turn_id=turn_id,
                active_turn_expires_at=now - timedelta(seconds=1),
            )
        )
        db.add(
            ChatMessageRecord(
                id=message_id,
                session_id=session_id,
                turn_id=turn_id,
                sequence=1,
                role="user",
                content="unrelated-content",
                status="generating",
            )
        )
        db.add(
            ChatTurnJob(
                turn_id=turn_id,
                chat_session_id=session_id,
                hf_user_id="unrelated-owner",
                request_id="unrelated-expired-request",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="unrelated-route",
                state="running",
                worker_id="unrelated-worker",
                worker_generation=1,
                lease_generation=1,
                app_release_id="release-staging",
                worker_contract_version="worker-v1",
                admitted_at=now - timedelta(minutes=2),
                started_at=now - timedelta(minutes=1),
                heartbeat_at=now - timedelta(minutes=1),
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        db.commit()
        before = tuple(
            tuple(row)
            for row in (
                db.execute(
                    select(ChatSession.__table__).where(ChatSession.id == session_id)
                ).one(),
                db.execute(
                    select(ChatMessageRecord.__table__).where(
                        ChatMessageRecord.id == message_id
                    )
                ).one(),
                db.execute(
                    select(ChatTurnJob.__table__).where(ChatTurnJob.turn_id == turn_id)
                ).one(),
            )
        )

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.failure_code == "bridge_refused"
    assert result.metrics[-1].success is True
    with factory() as db:
        after = tuple(
            tuple(row)
            for row in (
                db.execute(
                    select(ChatSession.__table__).where(ChatSession.id == session_id)
                ).one(),
                db.execute(
                    select(ChatMessageRecord.__table__).where(
                        ChatMessageRecord.id == message_id
                    )
                ).one(),
                db.execute(
                    select(ChatTurnJob.__table__).where(ChatTurnJob.turn_id == turn_id)
                ).one(),
            )
        )
        assert after == before
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 1
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
        assert db.scalar(select(func.count()).select_from(ChatMessageRecord)) == 1


def test_probe_refuses_schema_mismatch_before_writing_rows() -> None:
    factory = _factory()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(indexes=False),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert all(not metric.success for metric in result.metrics[:3])


def test_rejected_admission_cleans_only_the_probe_session() -> None:
    factory = _factory()
    unrelated_session_id = uuid.uuid4()
    unrelated_turn_id = uuid.uuid4()
    with factory() as db:
        db.add(
            ChatSession(
                id=unrelated_session_id,
                hf_user_id="unrelated",
                hf_username="unrelated",
                selected_model="qualification",
            )
        )
        db.add(
            ChatTurnJob(
                turn_id=unrelated_turn_id,
                chat_session_id=unrelated_session_id,
                hf_user_id="unrelated",
                request_id=f"unrelated-{uuid.uuid4().hex}",
                revision=1,
                dispatch_class="interactive",
                dispatch_route="test",
                state="admitted",
                app_release_id="release-staging",
                worker_contract_version="worker-v1",
                admitted_at=datetime.now(UTC),
            )
        )
        db.commit()

    result = run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(chat_max_concurrency=1),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity="loadtest-opaque-a",
    )

    assert result.success is False
    assert result.metrics[0].success is False
    assert result.metrics[-1].success is True
    with factory() as db:
        assert db.get(ChatTurnJob, unrelated_turn_id) is not None
        assert db.get(ChatSession, unrelated_session_id) is not None
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 1
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
