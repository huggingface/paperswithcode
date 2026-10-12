from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.loadtests.durable_bridge_probe import run_durable_bridge_probe
from backend.models.database import ChatMessageRecord, ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import SchemaAudit


@pytest.fixture
def disposable_postgresql_factory():
    raw_url = os.environ.get("PWC_DISPOSABLE_POSTGRES_URL")
    if raw_url is None:
        pytest.skip("explicit disposable PostgreSQL URL is required")
    url = make_url(raw_url)
    if not url.database or not url.database.startswith("pwc_bridge_disposable_"):
        pytest.fail("PostgreSQL proof requires an explicitly disposable database")
    if url.database in {"paperswithcode_hf", "pwc_staging"}:
        pytest.fail("application databases are forbidden for this proof")

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE papers (id BIGINT PRIMARY KEY)"))
    ChatSession.__table__.create(engine)
    ChatMessageRecord.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        ChatTurnJob.__table__.drop(engine)
        ChatMessageRecord.__table__.drop(engine)
        ChatSession.__table__.drop(engine)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE papers"))
        engine.dispose()


def _settings() -> Settings:
    return Settings(
        environment="staging",
        release_id="release-staging",
        db_search_path="staging,public",
        chat_durable_turn_dispatch_enabled=True,
        chat_worker_contract_version="worker-v1",
        chat_max_concurrency=2,
    )


def _audit() -> SchemaAudit:
    return SchemaAudit(True, True, True, True, True, True)


def _run(factory, identity: str, gate):
    return run_durable_bridge_probe(
        session_factory=factory,
        settings=_settings(),
        release_id="release-staging",
        worker_contract_version="worker-v1",
        schema_audit=_audit(),
        opaque_identity=identity,
        overlap_gate=gate,
    )


def test_postgresql_probes_overlap_with_two_committed_running_claims(
    disposable_postgresql_factory,
) -> None:
    factory = disposable_postgresql_factory

    class InspectingGate:
        def __init__(self) -> None:
            self.arrived = threading.Barrier(2)
            self.inspected = threading.Barrier(2)
            self.snapshots: list[tuple[int, int]] = []
            self.lock = threading.Lock()

        def wait(self, _participant: str) -> bool:
            self.arrived.wait(timeout=5)
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
            self.inspected.wait(timeout=5)
            return True

    gate = InspectingGate()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda identity: _run(factory, identity, gate),
                ("loadtest-postgresql-a", "loadtest-postgresql-b"),
            )
        )

    assert gate.snapshots == [(2, 0), (2, 0)]
    assert all(result.success for result in results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 0
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 0


def test_postgresql_probe_refuses_unrelated_expired_projection_without_changes(
    disposable_postgresql_factory,
) -> None:
    factory = disposable_postgresql_factory
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
        before = (
            tuple(
                db.execute(
                    select(ChatSession.__table__).where(ChatSession.id == session_id)
                ).one()
            ),
            tuple(
                db.execute(
                    select(ChatMessageRecord.__table__).where(
                        ChatMessageRecord.id == message_id
                    )
                ).one()
            ),
            tuple(
                db.execute(
                    select(ChatTurnJob.__table__).where(ChatTurnJob.turn_id == turn_id)
                ).one()
            ),
        )

    result = _run(factory, "loadtest-postgresql-probe", None)

    assert result.failure_code == "bridge_refused"
    with factory() as db:
        after = (
            tuple(
                db.execute(
                    select(ChatSession.__table__).where(ChatSession.id == session_id)
                ).one()
            ),
            tuple(
                db.execute(
                    select(ChatMessageRecord.__table__).where(
                        ChatMessageRecord.id == message_id
                    )
                ).one()
            ),
            tuple(
                db.execute(
                    select(ChatTurnJob.__table__).where(ChatTurnJob.turn_id == turn_id)
                ).one()
            ),
        )
        assert after == before
        assert db.scalar(select(func.count()).select_from(ChatTurnJob)) == 1
        assert db.scalar(select(func.count()).select_from(ChatSession)) == 1
        assert db.scalar(select(func.count()).select_from(ChatMessageRecord)) == 1
