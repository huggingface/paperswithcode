from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import Base, ChatMessageRecord, ChatSession, ChatTurnJob
from backend.services import chat_session_service as chat_session_module
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
)
from backend.services.chat_turn_job_repository import ChatTurnJobRepository


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatMessageRecord.__table__,
            ChatTurnJob.__table__,
        ],
    )
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _settings():
    return get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )


def _install_sqlite_coordinator(monkeypatch):
    class _SQLiteCoordinator(ChatTurnAdmissionCoordinator):
        def __init__(self, db, settings):
            super().__init__(
                db,
                settings,
                repository=ChatTurnJobRepository(advisory_locker=lambda *_args: None),
            )

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _SQLiteCoordinator
    )


def _seed_expired_turn(db: Session, *, request_id: str):
    settings = _settings()
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    model = settings.chat_model_choices[0]["id"]
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id="owner-1",
            hf_username="owner",
            selected_model=model,
            reasoning_effort="low",
            active_turn_id=turn_id,
            active_turn_expires_at=now + timedelta(minutes=2),
        )
    )
    db.add(
        ChatMessageRecord(
            id=uuid.uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            sequence=1,
            role="user",
            content="expired prompt",
            client_message_id=request_id,
            web_search_enabled=False,
            reasoning_effort="low",
            revision=1,
            agent_harness="claude",
            status="generating",
            model=model,
            model_route=settings.chat_model_routes[model],
            app_release_id=settings.release_id,
        )
    )
    db.add(
        ChatTurnJob(
            turn_id=turn_id,
            chat_session_id=session_id,
            hf_user_id="owner-1",
            request_id=request_id,
            revision=1,
            dispatch_class="interactive",
            dispatch_route="legacy-claude",
            state="running",
            worker_id="worker-a",
            worker_generation=1,
            lease_generation=1,
            app_release_id=settings.release_id,
            worker_contract_version="legacy-local-v1",
            admitted_at=now - timedelta(minutes=2),
            dispatched_at=now - timedelta(minutes=2),
            started_at=now - timedelta(minutes=2),
            heartbeat_at=now - timedelta(minutes=1),
            lease_expires_at=now - timedelta(seconds=1),
        )
    )
    db.commit()
    return session_id, turn_id


def _router_transaction(db: Session, action):
    try:
        action()
    except ChatServiceError as error:
        if error.commit_changes:
            db.commit()
        else:
            db.rollback()
        return error
    raise AssertionError("Expected retry-required admission failure")


def test_expired_request_replay_commits_reconciliation(monkeypatch, db):
    _install_sqlite_coordinator(monkeypatch)
    session_id, turn_id = _seed_expired_turn(db, request_id="expired-request")
    service = ChatSessionService(db, _settings())

    error = _router_transaction(
        db,
        lambda: service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session_id,
            client_message_id="expired-request",
            text="repeat",
            reasoning_effort="low",
        ),
    )

    db.expire_all()
    session = db.get(ChatSession, session_id)
    message = db.query(ChatMessageRecord).filter_by(turn_id=turn_id).one()
    job = db.get(ChatTurnJob, turn_id)
    assert error.code == "turn_requires_retry"
    assert error.commit_changes is True
    assert job.state == "interrupted"
    assert job.failure_code == "lease_expired"
    assert message.status == "interrupted"
    assert message.error_code == "lease_expired"
    assert session.active_turn_id is None


def test_same_session_new_request_commits_repair_without_new_work(monkeypatch, db):
    _install_sqlite_coordinator(monkeypatch)
    session_id, turn_id = _seed_expired_turn(db, request_id="original-request")
    service = ChatSessionService(db, _settings())

    error = _router_transaction(
        db,
        lambda: service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session_id,
            client_message_id="new-request",
            text="must explicitly retry",
            reasoning_effort="low",
        ),
    )

    db.expire_all()
    assert error.code == "turn_requires_retry"
    assert error.commit_changes is True
    assert db.query(ChatMessageRecord).count() == 1
    assert db.query(ChatTurnJob).count() == 1
    assert db.get(ChatTurnJob, turn_id).state == "interrupted"
    assert db.get(ChatSession, session_id).active_turn_id is None


def test_identity_mismatch_rolls_back_expiry_reconciliation(monkeypatch, db):
    _install_sqlite_coordinator(monkeypatch)
    session_id, turn_id = _seed_expired_turn(db, request_id="stable-request")
    service = ChatSessionService(db, _settings())

    error = _router_transaction(
        db,
        lambda: service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=uuid.uuid4(),
            client_message_id="stable-request",
            text="mismatched session",
            reasoning_effort="low",
        ),
    )

    db.expire_all()
    session = db.get(ChatSession, session_id)
    message = db.query(ChatMessageRecord).filter_by(turn_id=turn_id).one()
    job = db.get(ChatTurnJob, turn_id)
    assert error.code == "idempotency_conflict"
    assert error.commit_changes is False
    assert job.state == "running"
    assert job.failure_code is None
    assert message.status == "generating"
    assert message.error_code is None
    assert session.active_turn_id == turn_id


def test_projection_mismatch_keeps_expired_projection_unmodified(monkeypatch, db):
    _install_sqlite_coordinator(monkeypatch)
    session_id, turn_id = _seed_expired_turn(db, request_id="corrupt-request")
    message = db.query(ChatMessageRecord).filter_by(turn_id=turn_id).one()
    message.status = "complete"
    db.commit()
    service = ChatSessionService(db, _settings())

    error = _router_transaction(
        db,
        lambda: service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session_id,
            client_message_id="new-request",
            text="must fail closed",
            reasoning_effort="low",
        ),
    )

    db.expire_all()
    assert error.code == "durable_admission_failed"
    assert error.commit_changes is False
    assert db.get(ChatTurnJob, turn_id).state == "running"
    assert (
        db.query(ChatMessageRecord).filter_by(turn_id=turn_id).one().status
        == "complete"
    )
    assert db.get(ChatSession, session_id).active_turn_id == turn_id


def test_repeated_expired_replay_never_creates_or_redispatches(monkeypatch, db):
    _install_sqlite_coordinator(monkeypatch)
    session_id, turn_id = _seed_expired_turn(db, request_id="repeat-request")
    settings = _settings()

    errors = []
    for _ in range(2):
        service = ChatSessionService(db, settings)
        errors.append(
            _router_transaction(
                db,
                lambda service=service: service.begin_turn(
                    ChatOwner("owner-1", "owner"),
                    session_id=session_id,
                    client_message_id="repeat-request",
                    text="repeat",
                    reasoning_effort="low",
                ),
            )
        )

    db.expire_all()
    assert [error.code for error in errors] == [
        "turn_requires_retry",
        "turn_requires_retry",
    ]
    assert errors[0].commit_changes is True
    assert errors[1].commit_changes is False
    assert db.query(ChatMessageRecord).count() == 1
    assert db.query(ChatTurnJob).count() == 1
    assert db.get(ChatTurnJob, turn_id).state == "interrupted"
