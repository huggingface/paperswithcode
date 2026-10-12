from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.chat import ChatFeedbackRequest
from backend.models.database import (
    Base,
    ChatFeedback,
    ChatMessageRecord,
    ChatSession,
)
from backend.services import chat_trackio_service as trackio
from backend.services import chat_feedback_service as feedback


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
            ChatFeedback.__table__,
        ],
    )
    # SQLite ignores the PostgreSQL-only partial-index predicate and would
    # otherwise apply the user-revision uniqueness rule to assistant rows too.
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX idx_chat_messages_current_revision")
    with Session(engine) as session:
        yield session


def _conversation(db: Session, owner_id: str = "owner-1") -> ChatMessageRecord:
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner_id,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
        )
    )
    db.add(
        ChatMessageRecord(
            id=uuid.uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            sequence=1,
            role="user",
            content="Question",
            status="complete",
            langfuse_trace_id="a" * 32,
        )
    )
    assistant = ChatMessageRecord(
        id=uuid.uuid4(),
        session_id=session_id,
        turn_id=turn_id,
        sequence=2,
        role="assistant",
        content="Answer",
        status="complete",
    )
    db.add(assistant)
    db.flush()
    return assistant


class _Client:
    def __init__(self) -> None:
        self.scores: list[dict] = []

    def create_score(self, **score) -> None:
        self.scores.append(score)


def test_feedback_scores_owned_completed_assistant_trace(monkeypatch, db):
    assistant = _conversation(db)
    client = _Client()
    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: client
    )

    found = feedback.ChatFeedbackService(
        db, SimpleNamespace(environment="staging")
    ).submit(
        owner_id="owner-1",
        assistant_message_id=assistant.id,
        value=False,
        comment="  The answer is too long.  ",
    )

    assert found is True
    assert client.scores == [
        {
            "trace_id": "a" * 32,
            "score_id": client.scores[0]["score_id"],
            "name": "user-thumbs",
            "value": 0.0,
            "data_type": "BOOLEAN",
            "comment": "The answer is too long.",
            "metadata": {"assistant_message_id": str(assistant.id)},
        }
    ]
    assert len(client.scores[0]["score_id"]) == 32


def test_feedback_request_limits_optional_comment():
    assert ChatFeedbackRequest(value=False, comment="x" * 500).comment == "x" * 500
    with pytest.raises(ValidationError):
        ChatFeedbackRequest(value=False, comment="x" * 501)
    with pytest.raises(ValidationError):
        ChatFeedbackRequest(value=0)


def test_feedback_does_not_expose_another_users_message(monkeypatch, db):
    assistant = _conversation(db, owner_id="owner-2")
    client = _Client()
    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: client
    )

    found = feedback.ChatFeedbackService(
        db, SimpleNamespace(environment="staging")
    ).submit(
        owner_id="owner-1",
        assistant_message_id=assistant.id,
        value=True,
    )

    assert found is False
    assert client.scores == []


def test_feedback_is_stored_even_without_trace_correlation(monkeypatch, db):
    assistant = _conversation(db)
    user = next(
        row
        for row in db.query(ChatMessageRecord).all()
        if row.role == "user" and row.turn_id == assistant.turn_id
    )
    user.langfuse_trace_id = None
    db.flush()
    client = _Client()
    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: client
    )

    found = feedback.ChatFeedbackService(
        db, SimpleNamespace(environment="staging")
    ).submit(owner_id="owner-1", assistant_message_id=assistant.id, value=True)

    row = db.get(ChatFeedback, assistant.id)
    assert found is True
    assert row.value is True and row.trace_id is None
    # Langfuse scores need a trace; without one the rating is only stored.
    assert row.exported_to is None and client.scores == []


def test_feedback_upserts_the_latest_rating_and_survives_export_failure(
    monkeypatch, db
):
    assistant = _conversation(db)

    class FailingClient:
        def create_score(self, **_score):
            raise RuntimeError("trace store down")

    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: FailingClient()
    )
    service = feedback.ChatFeedbackService(db, SimpleNamespace(environment="staging"))

    assert service.submit(
        owner_id="owner-1", assistant_message_id=assistant.id, value=True
    )
    assert service.submit(
        owner_id="owner-1",
        assistant_message_id=assistant.id,
        value=False,
        comment="Changed my mind",
    )

    rows = db.query(ChatFeedback).all()
    assert len(rows) == 1
    assert (rows[0].value, rows[0].comment, rows[0].exported_to) == (
        False,
        "Changed my mind",
        None,
    )
    assert rows[0].trace_id == "a" * 32


def test_feedback_mirrors_to_trackio_as_a_metric(monkeypatch, db):
    assistant = _conversation(db)
    with monkeypatch.context() as setup:
        setup.setattr(trackio.threading.Thread, "start", lambda self: None)
        setup.setattr(trackio.atexit, "register", lambda *args: None)
        client = trackio.TrackioClient(
            "https://test.hf.space", "secret-token", "pwc-chat", "staging", "rel"
        )
    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: client
    )

    found = feedback.ChatFeedbackService(
        db, SimpleNamespace(environment="staging")
    ).submit(owner_id="owner-1", assistant_message_id=assistant.id, value=True)

    assert found is True
    entry = json.loads(client.pending.get_nowait())
    assert entry["run"].startswith("staging-feedback-")
    assert entry["metrics"] == {"feedback/thumbs_up": 1.0}
    assert len(entry["log_id"]) == 32
    assert db.get(ChatFeedback, assistant.id).exported_to == "trackio"


def test_feedback_listing_counts_and_filters_ratings(monkeypatch, db):
    monkeypatch.setattr(
        feedback, "configured_trace_export_client", lambda _settings: None
    )
    service = feedback.ChatFeedbackService(db, SimpleNamespace(environment="staging"))
    liked = _conversation(db)
    disliked = _conversation(db)
    service.submit(owner_id="owner-1", assistant_message_id=liked.id, value=True)
    service.submit(
        owner_id="owner-1",
        assistant_message_id=disliked.id,
        value=False,
        comment="Wrong benchmark",
    )

    listing = service.list_recent(limit=10)
    negatives = service.list_recent(limit=10, value=False)

    assert (listing.total, listing.positive, listing.negative) == (2, 1, 1)
    assert listing.environment == "staging"
    assert {item.assistant_message_id for item in listing.items} == {
        liked.id,
        disliked.id,
    }
    assert [item.comment for item in negatives.items] == ["Wrong benchmark"]
    with pytest.raises(ValueError):
        service.list_recent(limit=0)
