from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.responses import Response

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.chat import ChatShareDetail, PublicChatMessage
from backend.models.database import ChatShare
from backend.routers.chat import get_shared_chat
from backend.services.chat_session_service import ChatOwner, ChatServiceError
from backend.services.chat_share_service import ChatShareService


class _Result:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.values)


class _ShareDB:
    def __init__(self, session, messages, *, private_paper_artifact=None):
        self.session = session
        self.source_messages = messages
        self.private_paper_artifact = private_paper_artifact
        self.share = None
        self.queries: list[str] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.queries.append(sql)
        if "pg_advisory_xact_lock" in sql:
            return _Result()
        if "FROM chat_sessions" in sql:
            parameters = set(statement.compile().params.values())
            if self.session.id in parameters and self.session.hf_user_id in parameters:
                return _Result(self.session)
            return _Result(None)
        if "FROM chat_messages" in sql:
            return _Result(values=self.source_messages)
        if "FROM chat_artifacts" in sql:
            return _Result(self.private_paper_artifact)
        if "FROM chat_shares" in sql:
            return _Result(self.share)
        raise AssertionError(sql)

    def add(self, value):
        if isinstance(value, ChatShare):
            self.share = value

    def scalar(self, statement):
        return self.execute(statement).scalar_one_or_none()

    def flush(self):
        if self.share and self.share.created_at is None:
            self.share.created_at = datetime.now(UTC)


def _session(*, busy=False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        hf_user_id="hf-owner",
        selected_model="deepseek-ai/DeepSeek-V4-Flash-0731",
        active_turn_id=uuid.uuid4() if busy else None,
        active_turn_expires_at=datetime.now(UTC) + timedelta(minutes=1)
        if busy
        else None,
    )


def _row(
    sequence: int,
    *,
    role: str = "user",
    content: str = "Question",
    status: str = "complete",
    display_blocks=None,
    citations=None,
    finish_reason=None,
    error_code=None,
    model=None,
    paper_mentions=None,
    paper_selection=None,
    effective_prompt=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        sequence=sequence,
        role=role,
        content=content,
        status=status,
        display_blocks=display_blocks or [],
        citations=citations or [],
        finish_reason=finish_reason,
        error_code=error_code,
        model=model,
        paper_mentions=paper_mentions or [],
        paper_selection=paper_selection,
        effective_prompt=effective_prompt,
    )


def test_create_or_refresh_retains_capability_and_replaces_owned_snapshot():
    session = _session()
    first = _row(1)
    second = _row(2)
    db = _ShareDB(session, [first, second])
    service = ChatShareService(db, get_settings())
    owner = ChatOwner(hf_user_id="hf-owner", hf_username="owner")

    created = service.create_or_refresh(owner, session.id)
    first_share_id = created.id
    assert [message["content"] for message in created.messages] == [
        "Question",
        "Question",
    ]
    assert {uuid.UUID(message["id"]) for message in created.messages}.isdisjoint(
        {first.id, second.id}
    )
    first_snapshot = created.messages

    third = _row(3, content="Replacement")
    db.source_messages = [first, third]
    refreshed = service.create_or_refresh(owner, session.id)
    assert refreshed.id == first_share_id
    assert [message["content"] for message in refreshed.messages] == [
        "Question",
        "Replacement",
    ]
    assert refreshed.messages != first_snapshot
    assert refreshed.snapshot_version == 1
    assert refreshed.updated_at >= created.created_at


def test_share_serializes_with_private_paper_creation_before_querying_artifacts():
    session = _session()
    db = _ShareDB(session, [_row(1)])
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    ChatShareService(db, get_settings()).create_or_refresh(
        ChatOwner(hf_user_id="hf-owner", hf_username="owner"), session.id
    )

    lock_index = next(
        index
        for index, query in enumerate(db.queries)
        if "pg_advisory_xact_lock" in query
    )
    artifact_index = next(
        index
        for index, query in enumerate(db.queries)
        if "FROM chat_artifacts" in query
    )
    assert lock_index < artifact_index


def test_only_immutable_subject_owner_can_create_share():
    session = _session()
    service = ChatShareService(_ShareDB(session, [_row(1)]), get_settings())

    with pytest.raises(ChatServiceError) as exc_info:
        service.create_or_refresh(
            ChatOwner(hf_user_id="different-subject", hf_username="owner"),
            session.id,
        )

    assert exc_info.value.code == "session_not_found"
    assert exc_info.value.status_code == 404


def test_private_message_purge_cannot_change_stored_public_snapshot():
    session = _session()
    source = _row(1, content="Published")
    db = _ShareDB(session, [source])
    service = ChatShareService(db, get_settings())
    share = service.create_or_refresh(
        ChatOwner(hf_user_id="hf-owner", hf_username="owner"), session.id
    )
    stored_messages = list(share.messages)

    db.source_messages = []
    detail = ChatShareService(_PublicDB(share), get_settings()).get_public(
        str(share.id)
    )

    assert detail.messages[0].content == "Published"
    assert share.messages == stored_messages


def test_private_paper_chats_fail_closed_before_a_share_can_capture_turn_text():
    """Paper-turn output can quote manuscript context, so it is never shareable."""
    paper_id = uuid.uuid4()
    version_id = uuid.uuid4()
    row = _row(
        1,
        role="assistant",
        content="I prepared a draft with PRIVATE-PAPER-CANARY.",
        display_blocks=[
            {"kind": "reasoning", "text": "PRIVATE-PAPER-CANARY"},
            {
                "kind": "artifact",
                "schema_version": 1,
                "scope": "owner",
                "artifact_id": str(paper_id),
                "version_id": str(version_id),
                "identifier": "latex-paper",
                "version": 2,
                "artifact_kind": "latex_paper",
                "title": "Private manuscript",
                "status": "ready",
                "preview_mime": "application/pdf",
                "source_language": "latex",
                "total_bytes": 2048,
            },
        ],
    )
    db = _ShareDB(_session(), [row], private_paper_artifact=paper_id)

    with pytest.raises(ChatServiceError) as exc_info:
        ChatShareService(db, get_settings()).create_or_refresh(
            ChatOwner(hf_user_id="hf-owner", hf_username="owner"), db.session.id
        )

    assert exc_info.value.code == "paper_share_disabled"
    assert db.share is None
    assert "PRIVATE-PAPER-CANARY" not in str(getattr(db.share, "messages", []))
    assert str(version_id) not in str(getattr(db.share, "messages", []))


@pytest.mark.parametrize(
    ("session", "messages", "code"),
    [(_session(busy=True), [_row(1)], "session_busy"), (_session(), [], "empty_chat")],
)
def test_create_share_rejects_busy_and_empty_chats(session, messages, code):
    service = ChatShareService(_ShareDB(session, messages), get_settings())
    with pytest.raises(ChatServiceError) as exc_info:
        service.create_or_refresh(
            ChatOwner(hf_user_id="hf-owner", hf_username="owner"), session.id
        )
    assert exc_info.value.code == code


class _PublicDB:
    def __init__(self, share):
        self.share = share

    def execute(self, statement):
        assert "FROM chat_shares" in str(statement)
        params = statement.compile().params
        requested = next(iter(params.values()), None)
        if self.share is not None and requested != self.share.id:
            return _Result(None)
        return _Result(self.share)

    def scalar(self, statement):
        assert "chat_sessions.selected_model" in str(statement)
        return "deepseek-ai/DeepSeek-V4-Flash-0731"


def test_public_projection_preserves_bounded_blocks_and_omits_private_fields():
    user_id = uuid.uuid4()
    assistant_id = uuid.uuid4()
    tool = {
        "kind": "tool",
        "schema_version": 2,
        "id": "tool-1",
        "name": "Bash",
        "args": {"command": "pwc task list"},
        "status": "running",
        "content": [{"type": "text", "text": "bounded output", "truncated": False}],
        "metadata": {"exit_code": None, "output_truncated": False},
    }
    citation = {
        "position": 0,
        "route_id": "2501.00001",
        "title": "A paper",
        "source_url": "https://arxiv.org/abs/2501.00001",
    }
    user = _row(
        1,
        content="Read @A paper",
        paper_selection={
            "route_id": "2501.00001",
            "paper_version": "v2",
            "page": 4,
            "text": "quoted evidence",
            "text_sha256": "a" * 64,
            "included_bytes": 16,
            "page_verified": False,
        },
        paper_mentions=[
            {
                "occurrence_id": "mention-1",
                "route_id": "2501.00001",
                "paper_id": "42",
                "arxiv_id": "2501.00001",
                "title": "A paper",
                "source": "arxiv",
                "source_url": "https://arxiv.org/abs/2501.00001",
                "start": 5,
                "end": 13,
                "content_sha256": "a" * 64,
                "content_truncated": False,
                "content_available": True,
                "included_bytes": 100,
            }
        ],
        effective_prompt="private exact model input",
    )
    user.id = user_id
    assistant = _row(
        2,
        role="assistant",
        content="Answer",
        display_blocks=[
            {"kind": "reasoning", "text": "bounded reasoning"},
            tool,
            {
                "kind": "answer",
                "text": "Answer",
                "done": True,
                "citations": [citation],
            },
        ],
        citations=[citation],
        model="deepseek-ai/DeepSeek-V4-Flash-0731",
        finish_reason="tool_limit",
    )
    assistant.id = assistant_id
    assistant.model_route = "secret-provider-route"
    assistant.followups = ["private followup"]
    db = _ShareDB(_session(), [user, assistant])
    service = ChatShareService(db, get_settings())
    share = service.create_or_refresh(
        ChatOwner(hf_user_id="hf-owner", hf_username="owner"), db.session.id
    )

    detail = ChatShareService(_PublicDB(share), get_settings()).get_public(
        str(share.id)
    )
    payload = detail.model_dump(mode="json")

    assert payload["model"] == "deepseek-ai/DeepSeek-V4-Flash-0731"
    assert payload["model_label"] == "DeepSeek V4 Flash"
    assert payload["model_provider"] == "huggingface"
    assert payload["messages"][1]["model"] == payload["model"]
    assert payload["messages"][1]["finish_reason"] == "tool_limit"
    assert payload["messages"][1]["display_blocks"][1]["status"] == "error"
    assert payload["messages"][0]["paper_mentions"][0]["route_id"] == "2501.00001"
    assert payload["messages"][0]["paper_selection"] == {
        "route_id": "2501.00001",
        "paper_version": "v2",
        "page": 4,
        "text": "quoted evidence",
        "text_sha256": "a" * 64,
        "included_bytes": 16,
        "page_verified": False,
    }
    serialized = str(payload)
    assert "private exact model input" not in serialized
    assert "secret-provider-route" not in serialized
    assert "private followup" not in serialized
    assert set(payload) == {
        "share_id",
        "created_at",
        "updated_at",
        "model",
        "model_label",
        "model_provider",
        "messages",
    }
    assert "title" not in payload
    assert str(user_id) not in serialized
    assert str(assistant_id) not in serialized


@pytest.mark.parametrize("status", ["error", "interrupted"])
def test_failed_and_interrupted_rows_expand_to_stable_public_assistant(status):
    row = _row(
        1,
        content="Question",
        status=status,
        display_blocks=[{"kind": "reasoning", "text": "Partial"}],
        error_code="provider_error",
    )
    db = _ShareDB(_session(), [row])
    share = ChatShareService(db, get_settings()).create_or_refresh(
        ChatOwner(hf_user_id="hf-owner", hf_username="owner"), db.session.id
    )
    messages = (
        ChatShareService(_PublicDB(share), get_settings())
        .get_public(str(share.id))
        .messages
    )

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].display_state == (
        "interrupted" if status == "interrupted" else "failed"
    )
    assert messages[1].display_blocks[0].kind == "reasoning"
    assert (messages[1].finish_reason == "stopped") == (status == "interrupted")
    assert (messages[1].error is not None) == (status == "error")


def test_missing_and_malformed_share_ids_have_same_generic_error():
    service = ChatShareService(_PublicDB(None), get_settings())
    errors = []
    for share_id in ("not-a-uuid", str(uuid.uuid4())):
        with pytest.raises(ChatServiceError) as exc_info:
            service.get_public(share_id)
        errors.append((exc_info.value.status_code, str(exc_info.value)))
    assert errors == [(404, "Shared conversation not found")] * 2


def test_public_route_sets_no_store_without_an_authentication_dependency():
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        snapshot_version=1,
        created_at=now,
        updated_at=now,
        messages=[],
    )
    response = Response()
    detail = get_shared_chat(str(share.id), response, _PublicDB(share), get_settings())

    assert detail.share_id == share.id
    assert response.headers["Cache-Control"] == "no-store"


def test_public_http_get_is_anonymous_and_no_store(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        snapshot_version=1,
        created_at=now,
        updated_at=now,
        messages=[],
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: _PublicDB(share)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/chat/shares/{share.id}")
        missing = client.get(f"/api/v1/chat/shares/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert missing.status_code == 404
    assert missing.headers["Cache-Control"] == "no-store"
    assert missing.json()["detail"]["message"] == "Shared conversation not found"


class _SessionShareDB:
    def __init__(self, share):
        self.share = share

    def execute(self, statement):
        assert "chat_shares.chat_session_id" in str(statement)
        requested = next(iter(statement.compile().params.values()))
        if self.share is None or requested != self.share.chat_session_id:
            return _Result(None)
        return _Result(self.share)


def test_session_public_share_lookup_is_anonymous_and_no_store(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    now = datetime.now(UTC)
    share = SimpleNamespace(
        id=uuid.uuid4(),
        chat_session_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: _SessionShareDB(share)

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/chat/sessions/{share.chat_session_id}/public-share"
        )
        unshared = client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}/public-share")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["public_path"] == f"/share/{share.id}"
    assert unshared.status_code == 404
    assert unshared.headers["Cache-Control"] == "no-store"
    assert unshared.json()["detail"]["message"] == "Shared conversation not found"


def test_public_models_forbid_unexpected_private_fields():
    with pytest.raises(ValidationError):
        PublicChatMessage(
            id=uuid.uuid4(),
            role="user",
            content="Question",
            model_route="private",
        )
    with pytest.raises(ValidationError):
        ChatShareDetail(
            share_id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            messages=[],
            title="Private title",
        )
