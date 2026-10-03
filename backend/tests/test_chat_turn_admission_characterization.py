from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    ReplayAssistant,
)


class _Result:
    def __init__(self, *, one=None, rows=()):
        self._one = one
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _ScriptedDB:
    def __init__(self, *, execute_results=(), scalar_results=()):
        self._execute_results = iter(execute_results)
        self._scalar_results = iter(scalar_results)
        self.events: list[tuple[str, object]] = []
        self.added: list[object] = []
        self.flush_calls = 0

    def execute(self, query):
        self.events.append(("execute", query))
        return next(self._execute_results)

    def scalar(self, query):
        self.events.append(("scalar", query))
        return next(self._scalar_results)

    def add(self, value):
        self.events.append(("add", value))
        self.added.append(value)

    def flush(self):
        self.events.append(("flush", None))
        self.flush_calls += 1


def _session(settings, **overrides):
    values = {
        "id": uuid.uuid4(),
        "hf_user_id": "owner-1",
        "hf_username": "owner",
        "selected_model": settings.chat_model_choices[0]["id"],
        "execution_backend": "local_mcp",
        "transcript_status": "pending",
        "sdk_session_id": None,
        "sdk_project_key": None,
        "active_turn_id": None,
        "active_turn_expires_at": None,
        "transcript_bytes": 0,
        "projection_bytes": 0,
        "message_count": 0,
        "last_sequence": 0,
        "title_source": None,
        "web_search_enabled": False,
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _owned_service(db, settings, session):
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session
    return service


def _compiled_values(query) -> set[object]:
    return set(query.compile().params.values())


def test_completed_assistant_replay_returns_visible_result_without_writes():
    settings = get_settings()
    session = _session(settings)
    turn_id = uuid.uuid4()
    user_message = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        status="complete",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=3,
        web_search_enabled=False,
    )
    assistant_message = SimpleNamespace(
        content="The persisted answer",
        followups=["What changed?"],
        finish_reason="scope_blocked",
    )
    db = _ScriptedDB(
        execute_results=(
            _Result(one=user_message),
            _Result(one=assistant_message),
        )
    )
    admission = _owned_service(db, settings, session).begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=session.id,
        client_message_id="stable-request-id",
        text="This retry body is not admitted again",
    )

    assert admission.session_id == session.id
    assert admission.turn_id == turn_id
    assert admission.user_message_id == user_message.id
    assert admission.is_first_turn is True
    assert admission.replay_assistant == ReplayAssistant(
        content="The persisted answer",
        followups=["What changed?"],
        finish_reason="scope_blocked",
    )
    assert db.added == []
    assert db.flush_calls == 0


def test_reused_request_id_with_different_search_permission_conflicts_before_writes():
    settings = get_settings()
    session = _session(settings)
    existing = SimpleNamespace(web_search_enabled=True)
    db = _ScriptedDB(execute_results=(_Result(one=existing),))
    service = _owned_service(db, settings, session)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="reused-request-id",
            text="same client request",
            web_search_enabled=False,
        )

    assert exc_info.value.code == "idempotency_conflict"
    assert exc_info.value.status_code == 409
    assert db.added == []
    assert db.flush_calls == 0


def test_primary_paper_binding_is_immutable_before_capacity_or_writes():
    settings = get_settings()
    session = _session(settings, primary_paper_id=42)
    db = _ScriptedDB(execute_results=(_Result(one=None),))
    service = _owned_service(db, settings, session)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="paper-mismatch",
            text="Explain this paper",
            primary_paper_id=43,
        )

    assert exc_info.value.code == "primary_paper_mismatch"
    assert db.added == []
    assert db.flush_calls == 0


def test_expired_ordinary_generating_replay_is_interrupted_and_requires_new_id():
    settings = get_settings()
    turn_id = uuid.uuid4()
    session = _session(
        settings,
        active_turn_id=turn_id,
        active_turn_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        status="generating",
        error_code=None,
        web_search_enabled=False,
    )
    db = _ScriptedDB(execute_results=(_Result(one=existing), _Result(one=None)))
    service = _owned_service(db, settings, session)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="expired-request-id",
            text="retry",
        )

    assert exc_info.value.code == "turn_requires_retry"
    assert exc_info.value.status_code == 409
    assert exc_info.value.commit_changes is True
    assert existing.status == "interrupted"
    assert existing.error_code == "lease_expired"
    assert session.active_turn_id is None
    assert session.active_turn_expires_at is None
    assert db.added == []
    assert db.flush_calls == 0


@pytest.mark.parametrize(
    ("quota", "settings_update", "session_update", "text", "expected_code"),
    [
        (
            "storage",
            {"chat_session_byte_limit": 1024, "chat_user_byte_limit": 1024},
            {},
            "x" * 600,
            "chat_storage_quota_exceeded",
        ),
        (
            "message",
            {"chat_session_message_limit": 2},
            {"message_count": 1},
            "one more turn",
            "chat_message_quota_exceeded",
        ),
    ],
)
def test_quota_rejection_precedes_session_mutation_and_message_add(
    quota, settings_update, session_update, text, expected_code
):
    settings = get_settings().model_copy(update=settings_update)
    session = _session(settings, **session_update)
    before = {
        name: getattr(session, name)
        for name in (
            "last_sequence",
            "message_count",
            "active_turn_id",
            "active_turn_expires_at",
            "projection_bytes",
            "web_search_enabled",
            "updated_at",
        )
    }
    db = _ScriptedDB(
        execute_results=(
            _Result(one=None),
            _Result(),
            _Result(),
            _Result(),
        ),
        scalar_results=(0, 0, 0),
    )
    service = _owned_service(db, settings, session)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id=f"{quota}-quota-request",
            text=text,
        )

    assert exc_info.value.code == expected_code
    assert {name: getattr(session, name) for name in before} == before
    assert db.added == []
    assert db.flush_calls == 0


def test_first_message_admission_sets_title_flag_and_locks_user_before_global(
    monkeypatch,
):
    settings = get_settings()
    session = _session(settings)
    db = _ScriptedDB(
        execute_results=(_Result(), _Result(), _Result()),
        scalar_results=(0, 0, 0),
    )
    service = ChatSessionService(db, settings)

    def create_session(
        owner, selected_model, reasoning_effort, *, agent_harness_override
    ):
        assert agent_harness_override is None
        db.events.append(("create_session", (owner, selected_model, reasoning_effort)))
        return session

    monkeypatch.setattr(service, "create_session", create_session)
    monkeypatch.setattr(service, "fetchable_url_seed", lambda *_args, **_kwargs: [])
    owner = ChatOwner("owner-1", "owner")
    admission = service.begin_turn(
        owner,
        session_id=None,
        client_message_id="first-request",
        text="What is new?",
        initial_model=session.selected_model,
    )

    first_lock, second_lock = [
        payload for event, payload in db.events if event == "execute"
    ][:2]
    assert f"chat-user:{owner.hf_user_id}" in _compiled_values(first_lock)
    assert "chat-global-active-turns" in _compiled_values(second_lock)
    assert [event for event, _payload in db.events[:4]] == [
        "execute",
        "execute",
        "scalar",
        "scalar",
    ]

    assert admission.session_id == session.id
    assert admission.is_first_turn is True
    assert admission.title_should_generate is True
    assert admission.replay_assistant is None
    assert admission.prompt_revision == 1
    assert session.last_sequence == 1
    assert session.message_count == 1
    assert session.active_turn_id == admission.turn_id
    assert session.active_turn_expires_at is not None
    assert session.projection_bytes == 2 * len("What is new?".encode()) + len(b"[]")
    assert len(db.added) == 1
    assert db.added[0].id == admission.user_message_id
    assert db.added[0].role == "user"
    assert db.added[0].status == "generating"
    assert db.flush_calls == 1
