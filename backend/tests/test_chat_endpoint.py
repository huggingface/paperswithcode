from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.responses import Response
from starlette.requests import Request

from backend.config import Settings, get_settings
from backend.main import create_app
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
    ChatBrowserLatencyRequest,
    ChatRequest,
    sse_event,
)
from backend.routers import chat as chat_router
from backend.routers.inference_billing import _status as inference_billing_status
from backend.services import chat_mcp, chat_stream_service
from backend.services.chat_agent_service import (
    SEARCH_TOOL_NAME,
    SDKEventAdapter,
    SearchCallLimiter,
    _local_tool_event_policy,
    build_agent_options,
    stream_agent_events,
)
from backend.services.chat_sandbox_service import SandboxCleanupUnverified
from backend.services.chat_sandbox_spend_service import ChatComputeDisabled
from backend.services.chat_session_service import (
    ChatDeletionReceipt,
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    ReplayAssistant,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    ChatStreamOrchestrator,
    ChatTurnProjection,
    _private_paper_tool_event,
    _public_poster_tool_event,
    encode_journal_frame,
    sequential_reasoning_events,
    sanitized_exception_origin,
)


from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_title_service import fallback_title, normalize_title
from backend.services.chat_tracing_service import ChatTurnTrace
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.utils.auth import require_user


def test_sanitized_exception_origin_reports_only_source_location():
    try:
        int(None)
    except TypeError as error:
        origin = sanitized_exception_origin(error)

    assert origin.startswith(
        "test_chat_endpoint.py:test_sanitized_exception_origin_reports_only_source_location:"
    )
    assert origin.rsplit(":", 1)[1].isdigit()
    assert "None" not in origin


def _cookie_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", b"pwc_session=test")],
        }
    )


def test_admin_qualification_evidence_is_content_free_and_bounded(monkeypatch):
    from backend.models.chat import ChatQualificationEvidenceRequest

    scope_id = uuid.uuid4()

    class EvidenceService:
        def __init__(self, db):
            assert db is not None

        def collect(self, **scope):
            assert scope["scope_id"] == scope_id
            return {
                "expected_users": 32,
                "admitted_turns": 32,
                "admission_denominator_events": 32,
                "terminal_turns": 32,
                "queued_states": 0,
                "stale_fences": 0,
                "executor_starts": 16,
                "duplicate_executor_starts": 0,
                "workspace_creates": 1,
                "workspace_reuses": 15,
                "workspace_evictions": 16,
                "billed_duration_ms": 4,
                "window_started_at_ms": 1,
                "window_ended_at_ms": 2,
                "source": "durable_qualification_records",
            }

    monkeypatch.setattr(
        chat_router, "ChatDurableQualificationEvidenceService", EvidenceService
    )

    class DB:
        def commit(self):
            pass

        def rollback(self):
            pass

    db = DB()
    response = chat_router.chat_qualification_evidence(
        ChatQualificationEvidenceRequest(scope_id=scope_id),
        db,
        Settings(environment="staging"),
    )

    assert response["executor_starts"] == 16
    assert "turn_id" not in response and "chat_session_id" not in response


def test_chat_qualification_evidence_request_accepts_json_uuid():
    from backend.models.chat import ChatQualificationEvidenceRequest

    scope_id = uuid.uuid4()

    request = ChatQualificationEvidenceRequest.model_validate(
        {"scope_id": str(scope_id)}
    )

    assert request.scope_id == scope_id


def test_chat_quota_configuration_and_billing_api_fields_are_removed():
    settings = get_settings()

    fields = type(settings).model_fields
    assert "chat_requests_per_minute" not in fields
    assert "chat_requests_per_day" not in fields
    assert "chat_openrouter_requests_per_minute" not in fields
    assert "chat_openrouter_requests_per_day" not in fields
    payload = inference_billing_status(
        settings, connected=True, is_pro=True
    ).model_dump()
    assert "requests_per_minute" not in payload
    assert "requests_per_day" not in payload


def test_reasoning_effort_request_contract_accepts_native_values_only():
    assert (
        ChatRequest(message="hello", client_message_id="request-1").reasoning_effort
        is None
    )
    assert (
        ChatRequest(
            message="hello",
            client_message_id="request-2",
            reasoning_effort="max",
        ).reasoning_effort
        == "max"
    )
    with pytest.raises(ValueError):
        ChatRequest(
            message="hello",
            client_message_id="request-3",
            reasoning_effort="medium",
        )


def test_require_user_returns_immutable_oauth_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth,
        "decode_session_cookie",
        lambda _token: {"sub": "hf-immutable-123", "username": "Alice"},
    )
    user = require_user(_cookie_request())
    assert user["source"] == "cookie"
    assert user["username"] == "alice"
    assert user["hf_user_id"] == "hf-immutable-123"
    assert user["hf_subject"] == "hf-immutable-123"


def test_require_user_rejects_legacy_cookie_without_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth, "decode_session_cookie", lambda _token: {"username": "alice"}
    )
    with pytest.raises(Exception) as exc_info:
        require_user(_cookie_request())
    assert exc_info.value.status_code == 401


def test_chat_request_is_strict_and_requires_message_and_client_id():
    with pytest.raises(ValueError):
        ChatRequest(message="hello")
    with pytest.raises(ValueError):
        ChatRequest(message=" ", client_message_id="id")
    with pytest.raises(ValueError):
        ChatRequest(message="hello", client_message_id="id", unknown=True)
    request = ChatRequest(message="hello", client_message_id="id")
    assert request.session_id is None


def test_journal_sse_serializer_adds_sequence_without_changing_event_payload():
    encoded = encode_journal_frame(JournalFrame(8, "answer_delta", {"text": "héllo"}))

    assert encoded == (
        'id: 8\nevent: answer_delta\ndata: {"type":"answer_delta","text":"héllo"}\n\n'.encode()
    )


def test_journal_sse_serializer_preserves_browser_data_type_contract():
    encoded = encode_journal_frame(
        JournalFrame(4, "done", {"followups": [], "finish_reason": "success"})
    ).decode()
    data = next(
        json.loads(line.removeprefix("data: "))
        for line in encoded.splitlines()
        if line.startswith("data: ")
    )

    assert data == {
        "type": "done",
        "followups": [],
        "finish_reason": "success",
    }


def _completed_durable_admission(*, event_sequence: int = 8) -> TurnAdmission:
    return TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="model",
        model_route="route",
        sdk_session_id=None,
        sdk_project_key=None,
        replay_assistant=ReplayAssistant("canonical answer", ["next"]),
        attach_only=True,
        durable_event_sequence=event_sequence,
    )


def test_completed_durable_replay_uses_full_terminal_journal(monkeypatch):
    admission = _completed_durable_admission()

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert (turn_id, after_sequence) == (admission.turn_id, 4)
            yield JournalFrame(5, "stream_start", {"request_id": "original"})
            yield JournalFrame(6, "answer_delta", {"text": "stored"})
            yield JournalFrame(8, "done", {"finish_reason": "success"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=4
            )
        ]

    assert [(frame.sequence, frame.event) for frame in asyncio.run(collect())] == [
        (5, "stream_start"),
        (6, "answer_delta"),
        (8, "done"),
    ]


def test_completed_durable_replay_suppresses_fallback_at_acknowledged_cursor(
    monkeypatch,
):
    admission = _completed_durable_admission()

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert turn_id == admission.turn_id
            if False:
                yield

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect(cursor):
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    assert [frame.sequence for frame in asyncio.run(collect(7))] == [9, 10, 11]
    assert asyncio.run(collect(8)) == []
    assert asyncio.run(collect(9)) == []
    assert asyncio.run(collect(11)) == []


def test_completed_durable_replay_falls_back_after_job_sequence(monkeypatch):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            if False:
                yield

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect(cursor):
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    all_frames = asyncio.run(collect(7))
    acknowledged = asyncio.run(collect(8))
    assert [(frame.sequence, frame.event) for frame in all_frames] == [
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]
    assert acknowledged == []


def test_completed_durable_replay_preserves_nonterminal_journal_before_fallback(
    monkeypatch,
):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            yield JournalFrame(8, "answer_delta", {"text": "partial"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=0
            )
        ]

    frames = asyncio.run(collect())
    assert [(frame.sequence, frame.event) for frame in frames] == [
        (8, "answer_delta"),
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]
    assert frames[0].payload == {"text": "partial"}
    assert frames[2].payload == {"text": "canonical answer"}


@pytest.mark.parametrize("cursor", [8, 9])
def test_completed_durable_replay_partial_journal_at_acknowledged_cursor_emits_nothing(
    monkeypatch, cursor
):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            if 8 > cursor:
                yield JournalFrame(8, "answer_delta", {"text": "partial"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    assert asyncio.run(collect()) == []


def test_completed_durable_replay_falls_back_if_chunks_disappear_mid_replay(
    monkeypatch,
):
    admission = _completed_durable_admission(event_sequence=8)
    replay_steps = []

    class Coordinator:
        async def subscribe(self, **_kwargs):
            yield JournalFrame(7, "answer_delta", {"text": "partial"})
            replay_steps.append("terminal chunk deleted")

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=0
            )
        ]

    frames = asyncio.run(collect())
    assert replay_steps == ["terminal chunk deleted"]
    assert [(frame.sequence, frame.event) for frame in frames] == [
        (7, "answer_delta"),
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]


def test_reconnect_stream_resumes_after_last_event_id(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    cursors = []

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            return SimpleNamespace(active_turn_id=turn_id), []

    class Coordinator:
        async def subscribe(self, *, turn_id: uuid.UUID, after_sequence: int):
            cursors.append(after_sequence)
            for sequence in (7, 8):
                if sequence > after_sequence:
                    yield JournalFrame(
                        sequence, "answer_delta", {"text": str(sequence)}
                    )

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", b"7")],
        }
    )
    response = chat_router.reconnect_active_stream(
        session_id,
        request,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    async def collect_body():
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    body = asyncio.run(collect_body())
    assert "id: 7\n" not in body
    assert "id: 8\n" in body
    assert cursors == [7]


def test_legacy_reconnect_ignores_malformed_last_event_id(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(active_turn_id=turn_id), []

    class Stream:
        async def subscribe(self):
            yield SimpleNamespace(
                event="done",
                payload={"followups": [], "finish_reason": "success"},
            )

    class Registry:
        def get(self, *_args):
            return Stream()

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "live_chat_stream_registry", lambda: Registry())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", b"not-a-cursor")],
        }
    )

    response = chat_router.reconnect_active_stream(
        session_id,
        request,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    async def collect_body():
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    assert 'data: {"type":"done"' in asyncio.run(collect_body())


@pytest.mark.parametrize("cursor", ["-1", "nope", "1.5"])
def test_reconnect_stream_rejects_invalid_last_event_id(monkeypatch, cursor):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(active_turn_id=turn_id), []

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", cursor.encode())],
        }
    )
    with pytest.raises(Exception) as exc_info:
        chat_router.reconnect_active_stream(
            session_id,
            request,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=object(),
            settings=settings,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "chat_stream_cursor_invalid"


def test_browser_latency_request_is_strict_bounded_and_nonempty():
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest()
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=-1)
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=1, unexpected="content")
    payload = ChatBrowserLatencyRequest(
        submission_to_stream_start_ms=12.5,
        terminal_classification="complete",
    )
    assert payload.submission_to_stream_start_ms == 12.5


def test_cancel_endpoint_uses_owner_checked_active_turn(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, _db, _settings):
            pass

        def request_legacy_cancel(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            calls.append("fence")
            return turn_id

    class Manager:
        async def cancel(self, requested_session_id, requested_turn_id):
            calls.append((requested_session_id, requested_turn_id))
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(
        chat_router, "shared_sandbox_manager", lambda _settings: Manager()
    )
    response = asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=object(),
        )
    )

    assert response.status_code == 204
    assert calls == ["fence", "commit", (session_id, turn_id)]


def test_session_detail_never_caches_private_paper_metadata(monkeypatch):
    session_id = uuid.uuid4()

    class SessionService:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(id=session_id, transcript_status="complete"), []

    class PaperService:
        def __init__(self, *_args):
            pass

        def get_descriptor(self, *_args):
            return {"artifact_id": str(uuid.uuid4())}

    class Summary:
        def model_dump(self):
            return {}

    class Detail:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(chat_router, "ChatSessionService", SessionService)
    monkeypatch.setattr(chat_router, "LatexPaperService", PaperService)
    monkeypatch.setattr(chat_router, "_summary", lambda _session: Summary())
    monkeypatch.setattr(chat_router, "ChatSessionDetail", Detail)
    response = Response()

    chat_router.get_session(
        session_id,
        response,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=object(),
    )

    assert response.headers["Cache-Control"] == "private, no-store"


def test_create_session_fails_closed_when_public_admission_is_disabled():
    settings = Settings(chat_public_admission_enabled=False)

    with pytest.raises(Exception) as exc_info:
        chat_router.create_session(
            SimpleNamespace(selected_model=None),
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=SimpleNamespace(),
            settings=settings,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_temporarily_disabled"


def test_admin_harness_session_is_staging_only_and_returns_neutral_summary(
    monkeypatch,
):
    captured = {}
    session = SimpleNamespace(
        id=uuid.uuid4(),
        title="New chat",
        title_status="pending",
        selected_model="model",
        reasoning_effort="low",
        execution_backend="modal_cli",
        agent_harness="pi",
        web_search_enabled=False,
        message_count=0,
        active_turn_id=None,
        active_turn_expires_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        archived_at=None,
    )

    class Service:
        def __init__(self, _db, _settings):
            pass

        def create_session(self, owner, model, effort, **options):
            captured.update(owner=owner, model=model, effort=effort, **options)
            return session

    db = SimpleNamespace(
        commit=lambda: None, refresh=lambda _row: None, rollback=lambda: None
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "require_pi_release_window", lambda: None)
    response = chat_router.create_admin_harness_session(
        chat_router.AdminCreateHarnessSession(
            agent_harness="pi", selected_model="model", reasoning_effort="low"
        ),
        admin={"source": "cookie", "hf_subject": "admin-subject", "username": "admin"},
        db=db,
        settings=Settings(environment="staging"),
    )

    assert captured["owner"].hf_user_id == "admin-subject"
    assert captured["agent_harness_override"] == "pi"
    assert "agent_harness" not in response.model_dump()

    with pytest.raises(Exception) as exc_info:
        chat_router.create_admin_harness_session(
            chat_router.AdminCreateHarnessSession(agent_harness="pi"),
            admin={"source": "cookie", "hf_subject": "admin-subject"},
            db=db,
            settings=Settings(environment="production"),
        )
    assert exc_info.value.status_code == 404


def test_chat_availability_is_public(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="local_mcp",
        chat_paper_mentions_enabled=True,
        native_pdf_reader_enabled=True,
        paper_reader_chat_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "web_search_available", lambda _settings: True)
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/v1")

    with TestClient(app) as client:
        response = client.get("/api/v1/chat/availability")

    assert response.status_code == 200
    assert response.json()["web_search_available"] is True
    assert response.json()["native_pdf_reader_enabled"] is True
    assert response.json()["paper_reader_chat_enabled"] is True
    assert response.json()["paper_reader_selection_enabled"] is False


def test_chat_availability_maps_spend_rejection_to_content_free_paused_state(
    monkeypatch,
):
    settings = Settings(
        _env_file=None,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="modal_cli",
        chat_sandbox_spend_enforcement_enabled=True,
        chat_paper_mentions_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "web_search_available", lambda _settings: True)

    def reject(*_args, **_kwargs):
        raise ChatComputeDisabled("private circuit detail")

    monkeypatch.setattr(chat_router, "assert_chat_sandbox_spend_available", reject)

    assert chat_router.chat_availability() == {
        "status": "paused",
        "reason": "chat_temporarily_disabled",
        "expected_recovery_at": None,
        "paper_mentions_enabled": True,
        "web_search_available": False,
        "native_pdf_reader_enabled": False,
        "paper_reader_chat_enabled": False,
        "paper_reader_selection_enabled": False,
        "paper_artifacts_enabled": False,
    }


def test_stream_spend_rejection_preserves_exact_503_before_admission(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="modal_cli",
        chat_sandbox_spend_enforcement_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)

    def reject(*_args, **_kwargs):
        raise ChatComputeDisabled("Chat is temporarily disabled")

    monkeypatch.setattr(chat_router, "assert_chat_sandbox_spend_available", reject)
    body = ChatRequest(message="hello", client_message_id="message-a")

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner"},
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "chat_temporarily_disabled",
        "message": "Chat is temporarily disabled",
    }


def test_duplicate_durable_post_attaches_without_preparation_or_source(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=None,
        sdk_project_key=None,
        attach_only=True,
    )
    settings = get_settings().model_copy(
        update={
            "chat_enabled": True,
            "chat_public_admission_enabled": True,
            "chat_sandbox_admission_enabled": True,
            "chat_durable_turn_dispatch_enabled": True,
        }
    )
    calls = {"begin": 0}

    class DB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class Service:
        def __init__(self, *_args):
            pass

        def existing_effective_prompt(self, owner, requested_session, request_id):
            assert (owner.hf_user_id, requested_session, request_id) == (
                "owner-1",
                session_id,
                "stable-request",
            )
            return "persisted prompt"

        def begin_turn(self, *_args, **_kwargs):
            calls["begin"] += 1
            return admission

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert (turn_id, after_sequence) == (admission.turn_id, 3)
            yield JournalFrame(4, "answer_delta", {"text": "attached"})

    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "web_search_available", lambda *_args: True)
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="token", bill_to=None),
    )
    monkeypatch.setattr(
        chat_router.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", DB)
    monkeypatch.setattr(
        chat_router,
        "_prepare_paper_turn",
        lambda *_args: pytest.fail("duplicate prompt was prepared"),
    )
    monkeypatch.setattr(
        chat_router,
        "ChatStreamOrchestrator",
        lambda **_kwargs: pytest.fail("duplicate model source was created"),
    )
    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [(b"last-event-id", b"3")],
        }
    )

    async def exercise():
        response = await chat_router.stream_chat(
            ChatRequest(
                message="retry",
                session_id=session_id,
                client_message_id="stable-request",
            ),
            request,
            {"hf_user_id": "owner-1", "username": "owner"},
        )
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    body = asyncio.run(exercise())

    assert "id: 4\n" in body
    assert calls == {"begin": 1}


def test_failed_detached_terminal_callback_keeps_orchestrator_and_releases_reservation():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    claim = SimpleNamespace(turn_id=turn_id)

    class Orchestrator:
        async def persist_detached_terminal(self, *_args):
            raise RuntimeError("ambiguous terminal")

    orchestrator = Orchestrator()
    released = []
    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime._orchestrators[turn_id] = orchestrator

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    original_release = runtime_module.ChatExternalWorkerCapacityRepository.release_turn
    runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
        lambda _db, *, turn_id: released.append(turn_id)
    )
    try:
        with pytest.raises(RuntimeError, match="ambiguous terminal"):
            asyncio.run(runtime._persist_terminal(claim, "failed", "turn_failed"))
        assert runtime._orchestrators[turn_id] is orchestrator
        assert released == [turn_id]
    finally:
        runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
            original_release
        )
        runtime._orchestrators.pop(turn_id, None)


def test_process_loss_terminal_cleanup_releases_persisted_reservation():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    released = []
    runtime = runtime_module.ChatDetachedRuntime(get_settings())

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    original_release = runtime_module.ChatExternalWorkerCapacityRepository.release_turn
    runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
        lambda _db, *, turn_id: released.append(turn_id)
    )
    try:
        with pytest.raises(RuntimeError, match="owner is unavailable"):
            asyncio.run(
                runtime._persist_terminal(
                    SimpleNamespace(turn_id=turn_id), "failed", "process_lost"
                )
            )
    finally:
        runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
            original_release
        )

    assert released == [turn_id]


def test_terminal_release_failure_does_not_mask_persistence_failure(
    monkeypatch,
):
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    claim = SimpleNamespace(turn_id=turn_id)

    class Orchestrator:
        async def persist_detached_terminal(self, *_args):
            raise RuntimeError("primary persistence failure")

    orchestrator = Orchestrator()
    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime._orchestrators[turn_id] = orchestrator
    cleanup_attempted = []

    async def transaction(operation):
        cleanup_attempted.append(True)
        raise OSError("cleanup database unavailable")

    runtime._transaction = transaction
    monkeypatch.setattr(
        runtime_module.ChatExternalWorkerCapacityRepository,
        "release_turn",
        lambda _db, *, turn_id: None,
    )

    with pytest.raises(RuntimeError, match="primary persistence failure"):
        asyncio.run(runtime._persist_terminal(claim, "failed", "turn_failed"))
    assert cleanup_attempted == [True]
    assert runtime._orchestrators[turn_id] is orchestrator


def test_detached_start_failure_releases_reservation_without_masking_primary_error(
    monkeypatch,
):
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    admission = SimpleNamespace(turn_id=turn_id, session_id=uuid.uuid4())
    released = []
    abandoned = []

    class Registry:
        async def start_detached(self, **_kwargs):
            raise RuntimeError("primary detached start failure")

    class Orchestrator:
        def events(self):
            return None

        async def abandon_detached_start(self):
            abandoned.append(True)

    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime.registry = Registry()

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    monkeypatch.setattr(
        runtime_module.ChatExternalWorkerCapacityRepository,
        "release_turn",
        lambda _db, *, turn_id: released.append(turn_id),
    )

    with pytest.raises(RuntimeError, match="primary detached start failure"):
        asyncio.run(
            runtime.start(
                admission=admission,
                owner_id="owner",
                claim=SimpleNamespace(turn_id=turn_id),
                orchestrator=Orchestrator(),
            )
        )

    assert abandoned == [True]
    assert released == [turn_id]
    assert turn_id not in runtime._orchestrators


def test_detached_start_cleanup_failures_preserve_original_start_error():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    admission = SimpleNamespace(turn_id=turn_id, session_id=uuid.uuid4())
    cleanup_attempted = []

    class Registry:
        async def start_detached(self, **_kwargs):
            raise RuntimeError("original start error")

    class Orchestrator:
        def events(self):
            return None

        async def abandon_detached_start(self):
            raise OSError("abandonment unavailable")

    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime.registry = Registry()

    async def transaction(_operation):
        cleanup_attempted.append(True)
        raise OSError("reservation cleanup unavailable")

    runtime._transaction = transaction

    with pytest.raises(RuntimeError, match="original start error"):
        asyncio.run(
            runtime.start(
                admission=admission,
                owner_id="owner",
                claim=SimpleNamespace(turn_id=turn_id),
                orchestrator=Orchestrator(),
            )
        )

    assert cleanup_attempted == [True]


def test_stream_rejects_paper_selection_when_flag_is_off(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        paper_reader_chat_enabled=True,
        paper_reader_selection_enabled=False,
        environment="staging",
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    body = ChatRequest(
        message="Explain this",
        client_message_id="selection-disabled",
        primary_paper_route_id="2501.00001",
        paper_selection={
            "route_id": "2501.00001",
            "paper_version": "v1",
            "page": 4,
            "text": "quoted evidence",
        },
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner", "role": "admin"},
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "paper_selection_disabled"


def test_stream_gates_selection_follow_ups_to_staging_reviewers(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        paper_reader_chat_enabled=True,
        paper_reader_selection_enabled=True,
        environment="staging",
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    body = ChatRequest(
        message="Explain this",
        client_message_id="selection-follow-up",
        session_id=uuid.uuid4(),
        paper_selection={
            "route_id": "2501.00001",
            "paper_version": "v1",
            "page": 4,
            "text": "quoted evidence",
        },
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner"},
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "staging_access_required"


def test_sandbox_spend_admin_status_preserves_qualification_scope(monkeypatch):
    settings = Settings(_env_file=None, environment="staging")
    seen: list[str] = []
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        chat_router,
        "chat_sandbox_spend_status",
        lambda scoped, **_kwargs: seen.append(scoped.environment) or {"ok": True},
    )

    assert chat_router.chat_sandbox_spend("staging-q-pool") == {"ok": True}
    assert seen == ["staging-q-pool"]

    with pytest.raises(Exception) as exc_info:
        chat_router.chat_sandbox_spend("production-q-pool")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Unknown qualification"


def test_openrouter_key_api_is_absent_when_chat_is_disabled():
    with pytest.raises(Exception) as exc_info:
        chat_router.get_openrouter_key_status(
            user={"hf_user_id": "owner-1"},
            db=SimpleNamespace(),
            settings=Settings(environment="production", chat_enabled=False),
        )

    assert exc_info.value.status_code == 404


def test_production_openrouter_key_api_is_available_when_chat_is_enabled(monkeypatch):
    class FakeService:
        def __init__(self, *_args):
            pass

        def status(self, owner_id):
            assert owner_id == "owner-1"
            return SimpleNamespace(
                public_dict=lambda: {
                    "connected": False,
                    "verified_at": None,
                    "fallback_enabled": False,
                }
            )

    monkeypatch.setattr(chat_router, "OpenRouterBYOKService", FakeService)
    assert chat_router.get_openrouter_key_status(
        user={"hf_user_id": "owner-1"},
        db=SimpleNamespace(),
        settings=Settings(environment="production", chat_enabled=True),
    ) == {
        "connected": False,
        "verified_at": None,
        "fallback_enabled": False,
    }


def test_delete_session_reports_success_only_after_durable_and_workspace_verification(
    monkeypatch,
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            events.append("delete")
            return receipt

        def deletion_complete(self, requested):
            assert requested == receipt
            events.append("verify-db")
            return True

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, sandbox_id, snapshot_id):
            assert (sandbox_id, snapshot_id) == ("sb-1", None)
            events.append("verify-workspace")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    response = asyncio.run(
        chat_router.delete_session(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=Settings(),
        )
    )

    assert response.status_code == 204
    assert events == ["delete", "verify-workspace", "commit", "verify-db"]


def test_deletion_verifier_uses_the_persisted_share_foreign_key():
    class EmptyResult:
        @staticmethod
        def first():
            return None

    class EmptyDB:
        @staticmethod
        def execute(_query):
            return EmptyResult()

    service = ChatSessionService(EmptyDB(), Settings())
    receipt = ChatDeletionReceipt(uuid.uuid4(), None, None, None, None)

    assert service.deletion_complete(receipt) is True


@pytest.mark.parametrize("failure", ["database", "workspace"])
def test_delete_session_never_reports_success_when_removal_is_unverified(
    monkeypatch, failure: str
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)

    class DB:
        def commit(self):
            pass

        def rollback(self):
            pass

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            return receipt

        def deletion_complete(self, _receipt):
            return failure != "database"

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            if failure == "workspace":
                raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_deletion_unverified"


def test_delete_session_workspace_failure_rolls_back_before_commit(monkeypatch):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            events.append("delete")
            return receipt

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            events.append("verify-workspace")
            raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception):
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert events == ["delete", "verify-workspace", "rollback"]


def test_archive_old_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_old_sessions(self, owner, *, days):
            calls.append((owner.hf_user_id, days))
            return 7

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_old_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 7
    assert calls == [("owner-1", 30), "commit"]


def test_archive_old_sessions_marks_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None), SimpleNamespace(archived_at=None)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_old_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner")
    )

    assert archived == 2
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_archive_oldest_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_oldest_sessions(self, owner, *, limit):
            calls.append((owner.hf_user_id, limit))
            return 50

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_oldest_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 50
    assert calls == [("owner-1", 50), "commit"]


def test_archive_oldest_sessions_marks_at_most_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None) for _ in range(50)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_oldest_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner"), limit=50
    )

    assert archived == 50
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_chat_session_quota_error_states_the_exact_limit():
    class FakeDB:
        scalar_query = ""

        def execute(self, _query):
            return None

        def scalar(self, query):
            self.scalar_query = str(query)
            return 100

    db = FakeDB()
    settings = SimpleNamespace(
        chat_model_choices=[{"id": "model"}],
        chat_model_routes={"model": "route"},
        chat_session_limit=100,
    )

    with pytest.raises(ChatServiceError) as exc_info:
        ChatSessionService(db, settings).create_session(
            ChatOwner(hf_user_id="owner-1", hf_username="owner")
        )

    assert exc_info.value.code == "chat_session_quota_exceeded"
    assert "chat_sessions.archived_at IS NULL" in db.scalar_query
    assert str(exc_info.value) == (
        "You can have at most 100 chats. Archive old chats or delete a chat to "
        "create another."
    )


def test_sse_serialization_preserves_unicode_and_newlines():
    frame = sse_event("answer_delta", text="héllo\nworld")
    assert frame.startswith(b"data: ")
    assert frame.endswith(b"\n\n")
    assert json.loads(frame[6:-2])["text"] == "héllo\nworld"


def test_sse_event_accepts_truthful_lifecycle_phase():
    frame = sse_event("lifecycle", phase="preparing_workspace")

    assert json.loads(frame[6:-2]) == {
        "type": "lifecycle",
        "phase": "preparing_workspace",
    }


def test_sse_event_allows_stopped_done_terminal():
    frame = sse_event("done", followups=[], finish_reason="stopped")
    assert json.loads(frame[6:-2])["finish_reason"] == "stopped"


def test_sse_event_accepts_excalidraw_app_frames():
    start = sse_event(
        "app_start",
        id="tool-app-1",
        instance_id="tool-app-1",
        provider="excalidraw",
        server="excalidraw",
        tool="create_view",
        resource_uri="ui://excalidraw/mcp-app.html",
        input={"elements": "[]"},
    )
    result = sse_event(
        "app_result",
        id="tool-app-1",
        status="ready",
        took_ms=42,
        result={
            "content": [{"type": "text", "text": "ok", "truncated": False}],
            "structuredContent": {"checkpointId": "cp-1"},
            "isError": False,
        },
    )

    assert json.loads(start[6:-2]) == {
        "type": "app_start",
        "id": "tool-app-1",
        "instance_id": "tool-app-1",
        "provider": "excalidraw",
        "server": "excalidraw",
        "tool": "create_view",
        "resource_uri": "ui://excalidraw/mcp-app.html",
        "input": {"elements": "[]"},
    }
    assert json.loads(result[6:-2])["status"] == "ready"
    assert json.loads(result[6:-2])["result"]["structuredContent"] == {
        "checkpointId": "cp-1"
    }


def test_sse_event_accepts_posterly_artifact_frames():
    publication_id = "poster-1"
    start = sse_event(
        "artifact_start",
        publication_id=publication_id,
        identifier="attention-is-all-you-need",
        kind="posterly",
        title="Attention Is All You Need — Research Poster",
    )
    ready = sse_event(
        "artifact_ready",
        publication_id=publication_id,
        artifact_id="a9129b6f-b758-4ee7-b8df-6a202404d6c2",
        version_id="d45670d4-fdf6-415b-92c9-34f8a17f7722",
        identifier="attention-is-all-you-need",
        version=1,
        kind="posterly",
        title="Attention Is All You Need — Research Poster",
        preview_mime="image/png",
        source_language="html",
        gate_status="failed",
        total_bytes=22_204,
    )
    error = sse_event(
        "artifact_error",
        publication_id=publication_id,
        code="poster_validation_failed",
        message="Poster validation failed.",
    )

    assert json.loads(start[6:-2])["type"] == "artifact_start"
    assert (
        json.loads(ready[6:-2])["artifact_id"] == "a9129b6f-b758-4ee7-b8df-6a202404d6c2"
    )
    assert json.loads(error[6:-2])["code"] == "poster_validation_failed"


def test_sse_event_accepts_private_paper_artifact_draft_frame():
    artifact_id = "a9129b6f-b758-4ee7-b8df-6a202404d6c2"

    frame = sse_event(
        "paper_artifact",
        operation="draft",
        activated=True,
        descriptor={
            "artifact_id": artifact_id,
            "title": "Private draft",
            "source_head": None,
            "preview_head": None,
            "editing_enabled": False,
        },
    )

    assert json.loads(frame[6:-2]) == {
        "type": "paper_artifact",
        "operation": "draft",
        "activated": True,
        "descriptor": {
            "artifact_id": artifact_id,
            "title": "Private draft",
            "source_head": None,
            "preview_head": None,
            "editing_enabled": False,
        },
    }


def test_poster_tool_events_show_safe_arguments_and_hide_private_evidence():
    call = _public_poster_tool_event(
        "tool_call",
        {
            "type": "tool_call",
            "id": "poster-step",
            "name": "Bash",
            "args": {"command": "private paper text and generated HTML"},
        },
    )
    result = _public_poster_tool_event(
        "tool_result",
        {
            "type": "tool_result",
            "id": "poster-step",
            "status": "success",
            "took_ms": 1,
            "content": [{"type": "text", "text": "private paper text"}],
            "metadata": {"exit_code": 0, "output_truncated": True},
        },
    )

    assert call["args"] == {"command": "<inline content redacted>"}
    assert call["redacted"] is True
    assert result["content"] == [
        {
            "type": "text",
            "text": "Poster workflow step completed.",
            "truncated": True,
        }
    ]


def test_private_paper_tool_events_never_persist_manuscript_content():
    manuscript = "MANUSCRIPT-CANARY: unpublished theorem proof"
    events = [
        _private_paper_tool_event(
            "tool_call",
            {
                "type": "tool_call",
                "id": "paper-1",
                "name": "Bash",
                "args": {"command": f"printf '%s' '{manuscript}' > main.tex"},
            },
        ),
        _private_paper_tool_event(
            "tool_call_arguments_delta",
            {
                "type": "tool_call_arguments_delta",
                "id": "paper-1",
                "name": "Bash",
                "delta": manuscript,
                "partial_args": {"command": manuscript},
            },
        ),
        _private_paper_tool_event(
            "tool_result",
            {
                "type": "tool_result",
                "id": "paper-1",
                "status": "success",
                "content": [{"type": "text", "text": manuscript}],
                "results": [{"text": manuscript}],
            },
        ),
    ]

    serialized = json.dumps(events)
    assert manuscript not in serialized
    assert all(event["redacted"] is True for event in events)


@pytest.mark.parametrize("operation", ["draft", "repair"])
def test_private_paper_trust_gate_accepts_published_draft_operations(
    monkeypatch, operation
):
    artifact_id = uuid.uuid4()
    descriptor = {
        "artifact_id": str(artifact_id),
        "title": "Private paper",
        "source_head": None,
        "preview_head": None,
        "editing_enabled": True,
        "repair_attempts_remaining": 3,
        "repair_exhausted": False,
        "generation_provenance": None,
        "display_metadata": {"title": "Private paper"},
    }

    class DB:
        def scalar(self, _statement):
            return SimpleNamespace(id=artifact_id)

    @contextmanager
    def session_local():
        yield DB()

    class PaperService:
        def __init__(self, _db, _settings):
            pass

        def get_descriptor(self, _owner_id, _session_id):
            return SimpleNamespace(
                artifact_id=artifact_id,
                model_dump=lambda **_kwargs: descriptor,
            )

    monkeypatch.setattr(
        chat_stream_service, "db_manager", SimpleNamespace(session_local=session_local)
    )
    monkeypatch.setattr(chat_stream_service, "LatexPaperService", PaperService)
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test-model",
        model_route="test-route",
        sdk_session_id=None,
        sdk_project_key=None,
    )

    assert chat_stream_service._trusted_paper_artifact(
        {"operation": operation, "activated": True, "descriptor": descriptor},
        ChatOwner(hf_user_id="test-user", hf_username="tester"),
        admission,
        Settings(environment="staging"),
    ) == {
        "type": "paper_artifact",
        "operation": operation,
        "activated": True,
        "descriptor": descriptor,
    }


def test_poster_tool_argument_stream_sanitizes_before_public_projection():
    bash = _public_poster_tool_event(
        "tool_call_arguments_delta",
        {
            "type": "tool_call_arguments_delta",
            "id": "bash-1",
            "name": "Bash",
            "delta": "raw secret must not survive",
            "partial_args": {
                "command": (
                    "pwc poster render --token=secret <<'HTML'\n"
                    "<html>private paper</html>\nHTML"
                )
            },
        },
    )
    read = _public_poster_tool_event(
        "tool_call_arguments_done",
        {
            "type": "tool_call_arguments_done",
            "id": "read-1",
            "name": "Read",
            "args": {"file_path": "/workspace/output/poster.png", "limit": 10},
        },
    )

    encoded = json.dumps(bash)
    assert bash["snapshot"] is True
    assert bash["redacted"] is True
    assert "secret" not in encoded
    assert "private paper" not in encoded
    assert "<heredoc body redacted>" in encoded
    assert read["args"] == {"file_path": "output/poster.png", "limit": 10}

    for command, safe_fragment in (
        (
            "echo 'short private paper text' > /workspace/input/paper.txt",
            "/workspace/input/paper.txt",
        ),
        (
            "printf '%s' 'short private text' > ./output/poster.html",
            "./output/poster.html",
        ),
        ("python -c \"print('<html>generated</html>')\"", "python -c"),
    ):
        projected = _public_poster_tool_event(
            "tool_call_arguments_done",
            {
                "type": "tool_call_arguments_done",
                "id": "write-1",
                "name": "Bash",
                "args": {"command": command},
            },
        )
        encoded = json.dumps(projected)
        assert projected["redacted"] is True
        assert safe_fragment in encoded
        assert "short private" not in encoded
        assert "<html>generated</html>" not in encoded


def test_poster_sanitized_arguments_are_the_only_persisted_tool_projection():
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call_start",
        {"id": "tool-1", "name": "Bash", "content_index": 0},
    )
    final = _public_poster_tool_event(
        "tool_call_arguments_done",
        {
            "id": "tool-1",
            "name": "Bash",
            "args": {
                "command": "printf '%s' 'private paper text' > /workspace/output/poster.html"
            },
        },
    )
    projection.apply("tool_call_arguments_done", final)
    persisted = json.dumps(projection.completed_blocks())
    DISPLAY_BLOCKS_ADAPTER.validate_python(projection.completed_blocks())

    assert "private paper text" not in persisted
    assert "<inline content redacted>" in persisted
    assert "/workspace/output/poster.html" in persisted

    captured: dict = {}

    class Root:
        def start_observation(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace()

    trace = object.__new__(ChatTurnTrace)
    trace.tools = {}
    trace.root = Root()
    trace.start_tool(final)
    traced = json.dumps(captured)
    assert "private paper text" not in traced
    assert "<inline content redacted>" in traced


def test_complete_turn_persists_authoritative_streamed_tool_snapshot(monkeypatch):
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="gpt-5.6-luna@openai",
        model_route="gpt-5.6-luna@openai",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
        agent_harness="pi",
    )
    orchestrator = ChatStreamOrchestrator(
        settings=get_settings().model_copy(update={"environment": "development"}),
        owner=ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission=admission,
        prompt="hello",
        request_id="request-id",
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )
    orchestrator.projection.apply(
        "tool_call_start",
        {"id": "tool-1", "name": "Bash", "content_index": 0},
    )
    orchestrator.projection.apply(
        "tool_call_arguments_delta",
        {
            "id": "tool-1",
            "name": "Bash",
            "delta": '{"command":"pwc',
            "partial_args": {"command": "pwc"},
        },
    )
    orchestrator.projection.apply(
        "tool_call_arguments_done",
        {"id": "tool-1", "name": "Bash", "args": {"command": "pwc version"}},
    )
    orchestrator.projection.apply(
        "tool_result",
        {
            "id": "tool-1",
            "status": "success",
            "took_ms": 12,
            "content": [{"type": "text", "text": "ok", "truncated": False}],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    orchestrator.projection.apply("answer_delta", {"text": "Done."})

    captured: dict = {}
    database = SimpleNamespace(commit=lambda: captured.setdefault("committed", True))

    @contextmanager
    def session_local():
        yield database

    class SessionService:
        def __init__(self, db, settings):
            assert db is database

        def complete_turn(self, *args):
            captured["blocks"] = args[5]

        def citation_history(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", SessionService)
    monkeypatch.setattr(
        chat_stream_service,
        "resolve_citation_targets",
        lambda _db, _text: ([], {}),
    )

    orchestrator._complete_turn({"followups": [], "finish_reason": "success"})

    DISPLAY_BLOCKS_ADAPTER.validate_python(captured["blocks"])
    tool = next(block for block in captured["blocks"] if block["kind"] == "tool")
    assert tool["args"] == {"command": "pwc version"}
    assert "argument_text" not in tool
    assert "argument_state" not in tool
    assert captured["committed"] is True


def test_streamed_tool_argument_events_have_strict_public_sse_shapes():
    start = json.loads(
        sse_event("tool_call_start", id="tool-1", name="Bash", content_index=0)[6:-2]
    )
    delta = json.loads(
        sse_event(
            "tool_call_arguments_delta",
            id="tool-1",
            name="Bash",
            delta='{"command":"pwc',
            partial_args={"command": "pwc"},
        )[6:-2]
    )
    done = json.loads(
        sse_event(
            "tool_call_arguments_done",
            id="tool-1",
            name="Bash",
            args={"command": "pwc version"},
        )[6:-2]
    )

    assert start["content_index"] == 0
    assert delta["partial_args"] == {"command": "pwc"}
    assert done["args"] == {"command": "pwc version"}


def test_chat_projection_keeps_app_blocks_out_of_tool_accordions():
    projection = ChatTurnProjection()
    projection.apply(
        "app_start",
        {
            "id": "tool-app-1",
            "instance_id": "tool-app-1",
            "provider": "excalidraw",
            "server": "excalidraw",
            "tool": "create_view",
            "resource_uri": "ui://excalidraw/mcp-app.html",
            "input": {"elements": "[]"},
        },
    )
    projection.apply(
        "app_result",
        {
            "id": "tool-app-1",
            "status": "ready",
            "took_ms": 12,
            "result": {
                "content": [{"type": "text", "text": "ok", "truncated": False}],
                "structuredContent": {},
                "isError": False,
            },
        },
    )
    projection.apply("answer_delta", {"text": "Here is the schematic."})

    blocks = projection.completed_blocks()
    DISPLAY_BLOCKS_ADAPTER.validate_python(blocks)

    assert [block["kind"] for block in blocks] == ["app", "answer"]
    assert blocks[0]["status"] == "ready"
    assert blocks[0]["tool"] == "create_view"


def test_chat_projection_preserves_sse_block_order():
    # Keep an explicit persisted-shape check in releases following Pi image
    # changes so the rollback window contains two qualified readers.
    projection = ChatTurnProjection()
    projection.apply("answer_delta", {"text": "Before tool."})
    projection.apply(
        "tool_call",
        {"id": "tool-1", "name": "Bash", "args": {"command": "pwc task list"}},
    )
    projection.apply(
        "tool_result",
        {
            "id": "tool-1",
            "status": "success",
            "took_ms": 12,
            "content": [{"type": "text", "text": "done", "truncated": False}],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply("reasoning_start", {})
    projection.apply("reasoning_delta", {"text": "Check another benchmark."})
    projection.apply("reasoning_end", {})
    projection.apply("answer_delta", {"text": "After tool."})

    blocks = projection.completed_blocks()
    DISPLAY_BLOCKS_ADAPTER.validate_python(blocks)

    assert [block["kind"] for block in blocks] == [
        "answer",
        "tool",
        "reasoning",
        "answer",
    ]
    assert [block["text"] for block in blocks if block["kind"] == "answer"] == [
        "Before tool.",
        "After tool.",
    ]


def test_pi_tool_timing_fallback_measures_parallel_calls_and_preserves_worker_timing():
    from backend.services.chat_stream_service import _ToolTimingFallback

    now = 10.0
    timing = _ToolTimingFallback(enabled=True, now=lambda: now)
    timing.apply("tool_call", {"id": "slow"})
    now = 10.025
    timing.apply("tool_call", {"id": "fast"})
    now = 10.04
    fast = {"id": "fast", "took_ms": 0}
    timing.apply("tool_result", fast)
    assert fast["took_ms"] == 15

    now = 10.08
    slow = {"id": "slow", "took_ms": 73}
    timing.apply("tool_result", slow)
    assert slow["took_ms"] == 73


def test_pi_recovery_telemetry_is_logged_without_becoming_a_public_frame(
    caplog, monkeypatch
):
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
        agent_harness="pi",
    )
    orchestrator = ChatStreamOrchestrator(
        settings=get_settings().model_copy(update={"environment": "development"}),
        owner=ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission=admission,
        prompt="hello",
        request_id="request-id",
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )
    monkeypatch.setattr(chat_stream_service, "_legacy_turn_is_active", lambda *_: True)

    async def consume():
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(
            {
                "type": "_execution_telemetry",
                "tool_calls": 2,
                "tool_rounds_executed": 2,
                "execution_limit_reached": False,
                "recovery_reason": "incomplete_response",
                "recovery_attempts": 1,
                "recovery_outcome": "recovered_after_retry",
            }
        )
        await queue.put({"type": "_research_finished"})
        return [frame async for frame in orchestrator._consume(queue)]

    caplog.set_level(logging.INFO, logger="backend.services.chat_stream_service")
    assert asyncio.run(consume()) == []
    assert "recovery_reason=incomplete_response" in caplog.text
    assert "recovery_attempts=1" in caplog.text
    assert "recovery_outcome=recovered_after_retry" in caplog.text


def test_chat_projection_collapses_consecutive_duplicate_reasoning():
    projection = ChatTurnProjection()
    for _ in range(2):
        projection.apply("reasoning_start", {})
        projection.apply("reasoning_delta", {"text": "**Same plan**"})
        projection.apply("reasoning_end", {})

    assert projection.completed_blocks() == [
        {"kind": "reasoning", "text": "**Same plan**"}
    ]


def test_chat_projection_drops_unresolved_paper_placeholders_before_persistence(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.services.chat_stream_service.resolve_citation_targets",
        lambda _db, _text: ([], {}),
    )
    projection = ChatTurnProjection()
    projection.apply(
        "answer_delta",
        {"text": "Use [DINO](paper:<cfg>) for this workload."},
    )

    answer, citations = projection.finalize(object())

    assert answer == "Use DINO for this workload."
    assert projection.answer_parts == [answer]
    assert projection.blocks[-1]["text"] == answer
    assert citations == []


def test_chat_projection_canonicalizes_resolved_paper_aliases(monkeypatch):
    citation = {
        "position": 0,
        "route_id": "2501.00001",
        "title": "Paper",
        "source_url": "https://arxiv.org/abs/2501.00001",
    }
    monkeypatch.setattr(
        "backend.services.chat_stream_service.resolve_citation_targets",
        lambda _db, _text: ([citation], {"9": "2501.00001"}),
    )
    projection = ChatTurnProjection()
    projection.apply("answer_delta", {"text": "Read [Paper](paper:9)."})

    answer, citations = projection.finalize(object())

    assert answer == "Read [Paper](paper:2501.00001)."
    assert citations[0]["kind"] == "catalog_paper"
    assert citations[0]["route_id"] == "2501.00001"
    assert citations[0]["title"] == "Paper"
    assert projection.blocks[-1]["citations"] == citations


def test_chat_projection_canonicalizes_arxiv_urls(monkeypatch):
    citation = {
        "position": 0,
        "route_id": "2501.00001",
        "title": "Paper",
        "source_url": "https://arxiv.org/abs/2501.00001",
    }
    monkeypatch.setattr(
        "backend.services.chat_stream_service.resolve_citation_targets",
        lambda _db, _text: ([citation], {"2501.00001": "2501.00001"}),
    )
    projection = ChatTurnProjection()
    projection.apply(
        "answer_delta",
        {
            "text": "Read [https://arxiv.org/abs/2501.00001]"
            "(https://arxiv.org/abs/2501.00001)."
        },
    )

    answer, citations = projection.finalize(object())

    assert answer == ("Read [https://arxiv.org/abs/2501.00001](paper:2501.00001).")
    assert citations[0]["kind"] == "catalog_paper"
    assert citations[0]["route_id"] == "2501.00001"
    assert citations[0]["title"] == "Paper"
    assert projection.blocks[-1]["citations"] == citations


def test_stream_boundary_normalizer_repairs_nested_and_extra_reasoning_events():
    async def source():
        for event in [
            {"type": "reasoning_start"},
            {"type": "reasoning_delta", "text": "First"},
            {"type": "reasoning_start"},
            {"type": "reasoning_delta", "text": "Second"},
            {"type": "reasoning_end"},
            {"type": "reasoning_end"},
            {"type": "done"},
        ]:
            yield event

    async def collect():
        return [event async for event in sequential_reasoning_events(source())]

    assert [event["type"] for event in asyncio.run(collect())] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "done",
    ]


def test_model_registry_exposes_stable_ids_not_provider_routes():
    production = Settings(environment="production")
    assert [choice["id"] for choice in production.chat_model_choices] == [
        "zai-org/GLM-5.3-Flash",
    ]
    staging = Settings(
        environment="staging", chat_openrouter_server_funded_enabled=True
    )
    assert [choice["id"] for choice in staging.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
    ]
    assert production.chat_model_routes["zai-org/GLM-5.3-Flash"] == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    for legacy_id in (
        "google/gemma-4-31B-it",
        "zai-org/GLM-5.2",
        "moonshotai/Kimi-K3",
        "openai/gpt-oss-120b",
        "deepseek-ai/DeepSeek-V4-Flash",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-terra",
    ):
        assert (
            production.chat_model_routes[legacy_id]
            == production.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
        )
    assert production.chat_model_providers["zai-org/GLM-5.3-Flash"] == "huggingface"
    assert production.chat_effective_pi_prewarm_model == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    production_direct = Settings(
        environment="production", chat_openai_direct_enabled=True
    )
    assert [choice["id"] for choice in production_direct.chat_model_choices] == [
        "gpt-5.6-luna@openai",
        "zai-org/GLM-5.3-Flash",
    ]
    assert production_direct.chat_model_choices[0]["label"] == "GPT-5.6 Luna"
    assert production_direct.chat_model_providers["gpt-5.6-luna@openai"] == "openai"
    assert production_direct.chat_route_protocols["gpt-5.6-luna@openai"] == (
        "openai-responses"
    )
    assert production_direct.chat_effective_pi_prewarm_model == ("gpt-5.6-luna@openai")
    assert staging.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    )
    assert staging.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "huggingface"
    )
    assert staging.chat_model_routes["moonshotai/Kimi-K3"] == (
        "moonshotai/Kimi-K3:baseten"
    )
    assert staging.chat_model_providers["moonshotai/Kimi-K3"] == "huggingface"
    assert staging.chat_model_routes["gpt-5.6-luna@openrouter"] == "openai/gpt-5.6-luna"
    assert staging.chat_model_providers["gpt-5.6-luna@openrouter"] == "openrouter"
    assert staging.chat_model_routes["openai/gpt-5.6-luna"] == "openai/gpt-5.6-luna"
    assert staging.chat_model_providers["openai/gpt-5.6-luna"] == "openrouter"
    assert staging.chat_model_labels["openai/gpt-5.6-luna"] == (
        "GPT-5.6 Luna (Legacy OpenRouter)"
    )
    assert staging.chat_route_providers["openai/gpt-5.6-luna"] == "openrouter"
    assert "openai/gpt-5.6-luna" in staging.chat_openrouter_routes
    assert staging.chat_model_routes["openai/gpt-5.6-terra"] == (
        "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    )

    direct = Settings(environment="staging", chat_openai_direct_enabled=True)
    assert [choice["id"] for choice in direct.chat_model_choices] == [
        "gpt-5.6-luna@openai",
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
    ]
    assert direct.chat_model_choices[0]["label"] == "GPT-5.6 Luna (Direct)"
    assert direct.chat_model_routes["gpt-5.6-luna@openai"] == ("gpt-5.6-luna@openai")
    assert direct.chat_model_providers["gpt-5.6-luna@openai"] == "openai"
    assert direct.chat_route_providers["gpt-5.6-luna@openai"] == "openai"
    assert direct.chat_route_protocols["gpt-5.6-luna@openai"] == "openai-responses"
    assert direct.chat_route_provider_models["gpt-5.6-luna@openai"] == ("gpt-5.6-luna")
    assert direct.chat_route_funding_modes["gpt-5.6-luna@openai"] == "openai_funded"
    assert direct.chat_effective_pi_prewarm_model == "gpt-5.6-luna@openai"

    openrouter = Settings(
        environment="production",
        chat_deepseek_v4_flash_provider="openrouter",
    )
    assert openrouter.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"] == (
        "deepseek/deepseek-v4-flash-0731"
    )
    assert (
        openrouter.chat_model_providers["deepseek-ai/DeepSeek-V4-Flash-0731"]
        == "openrouter"
    )
    assert openrouter.chat_effective_pi_prewarm_model == (
        "zai-org/GLM-5.3-Flash:fastest"
    )
    assert "deepseek/deepseek-v4-flash-0731" in openrouter.chat_openrouter_routes
    assert openrouter.chat_route_providers[production.chat_deepseek_v4_flash_route] == (
        "huggingface"
    )

    comparison = Settings(
        environment="staging",
        chat_openrouter_server_funded_enabled=True,
        chat_alternative_model_enabled=True,
        chat_alternative_model="google/gemini-3.7-flash",
    )
    assert [choice["id"] for choice in comparison.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/Kimi-K3",
        "gpt-5.6-luna@openrouter",
        "google/gemini-3.7-flash",
    ]
    assert comparison.chat_model_routes["google/gemini-3.7-flash"] == (
        "google/gemini-3.7-flash"
    )
    assert comparison.chat_model_providers["google/gemini-3.7-flash"] == "openrouter"


def test_title_and_display_projection_bounds():
    assert (
        normalize_title('  "Vision   Transformer Trends."  ')
        == "Vision Transformer Trends"
    )
    assert len(fallback_title("word " * 100)) <= 80
    reader_title = fallback_title(
        "<primary_paper_title>Attention Is All You Need</primary_paper_title>\n"
        "<user_message>What is the key contribution?</user_message>"
    )
    assert reader_title == ("Attention Is All You Need — What is the key contribution")
    assert "<" not in reader_title
    with pytest.raises(ValueError):
        DISPLAY_BLOCKS_ADAPTER.validate_python(
            [
                {
                    "kind": "tool",
                    "id": "t",
                    "name": "search_papers",
                    "args": {"secret": "not allowed"},
                    "status": "done",
                    "hits": 0,
                    "took_ms": 1,
                    "results": [],
                }
            ]
        )


def test_spooled_transcript_recovery_replays_main_and_subpaths(tmp_path):
    session_id = "00000000-0000-0000-0000-000000000123"
    recovery = tmp_path / "pwc-chat-recovery"
    project = recovery / "attempt" / "projects" / "project-key"
    project.mkdir(parents=True)
    main_entries = [{"type": "user", "uuid": "u1"}]
    (project / f"{session_id}.jsonl").write_text(
        json.dumps(main_entries[0]) + "\n", encoding="utf-8"
    )
    subpath = project / session_id / "subagents"
    subpath.mkdir(parents=True)
    (subpath / "agent-one.jsonl").write_text(
        json.dumps({"type": "assistant", "uuid": "u2"}) + "\n",
        encoding="utf-8",
    )

    class FakeStore:
        def __init__(self):
            self.rows = {}

        async def append(self, key, entries):
            self.rows[(key["session_id"], key.get("subpath"))] = entries

        async def load(self, key):
            return self.rows.get((key["session_id"], key.get("subpath")))

    store = FakeStore()
    settings = get_settings().model_copy(
        update={"chat_recovery_spool_dir": str(recovery)}
    )
    recovered = asyncio.run(
        reconcile_spooled_session(
            settings,
            store,
            project_key="project-key",
            sdk_session_id=uuid.UUID(session_id),
        )
    )
    assert recovered is True
    assert store.rows[(session_id, None)] == main_entries
    assert store.rows[(session_id, "subagents/agent-one")][0]["uuid"] == "u2"
    assert not (recovery / "attempt").exists()


def test_search_limiter_denies_third_call():
    limiter = SearchCallLimiter(2)
    request = {"tool_name": SEARCH_TOOL_NAME}
    first = asyncio.run(limiter(request, None, None))
    second = asyncio.run(limiter(request, None, None))
    third = asyncio.run(limiter(request, None, None))
    assert first["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert second["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert third["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_search_limiter_latches_failed_web_search():
    limiter = SearchCallLimiter(4, maximum_web=3, maximum_total=12)
    request = {"tool_name": "mcp__web__search_web"}

    assert (
        asyncio.run(limiter(request, None, None))["hookSpecificOutput"][
            "permissionDecision"
        ]
        == "allow"
    )
    asyncio.run(
        limiter.post({**request, "tool_response": {"is_error": True}}, None, None)
    )
    assert (
        asyncio.run(limiter(request, None, None))["hookSpecificOutput"][
            "permissionDecision"
        ]
        == "deny"
    )


def test_sdk_adapter_streams_reasoning_tool_result_and_answer():
    adapter = SDKEventAdapter(
        show_reasoning=True, policy=_local_tool_event_policy(None)
    )
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Search first"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": SEARCH_TOOL_NAME,
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 1,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"query":"VLMs","top_k":3}',
                },
            },
        ),
        StreamEvent(
            uuid="6",
            session_id="s",
            event={"type": "content_block_stop", "index": 1},
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tool-1",
                    content=json.dumps(
                        {"hits": 1, "took_ms": 9, "results": [{"route_id": "1"}]}
                    ),
                )
            ]
        ),
        StreamEvent(
            uuid="7",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "text_delta", "text": "Answer"},
            },
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="s",
        ),
    ]
    events = [event for message in messages for event in adapter.feed(message)]
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "answer_delta",
        "usage",
        "done",
    ]
    assert events[3]["args"] == {"query": "VLMs", "top_k": 3}
    assert events[4]["results"] == [{"route_id": "1"}]


def test_local_tool_limiter_denies_seventh_parallel_batch_without_call_slots():
    limiter = SearchCallLimiter(
        maximum=12, maximum_web=12, maximum_total=12, maximum_rounds=6
    )
    for round_number in range(1, 7):
        tool_id = f"round-{round_number}"
        limiter.register_round([tool_id])
        decision = asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"
    denied_ids = ["round-7-a", "round-7-b"]
    limiter.register_round(denied_ids)
    decisions = [
        asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        for tool_id in denied_ids
    ]
    assert all(
        item["hookSpecificOutput"]["permissionDecision"] == "deny" for item in decisions
    )
    assert limiter.total_calls == 6
    assert limiter.rounds_denied == 1
    assert limiter.tooling_closed


def test_local_tool_limiter_counts_parallel_calls_as_one_round_then_sequential():
    limiter = SearchCallLimiter(
        maximum=12, maximum_web=12, maximum_total=12, maximum_rounds=1
    )

    for tool_id in ("parallel-a", "parallel-b"):
        decision = asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"

    assert limiter.rounds_started == 1
    assert limiter.rounds_executed == 1
    for tool_id in ("parallel-a", "parallel-b"):
        asyncio.run(
            limiter.post(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )

    decision = asyncio.run(
        limiter(
            {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": "parallel-a"},
            "parallel-a",
            None,
        )
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert limiter.rounds_started == 2
    assert limiter.rounds_executed == 1
    assert limiter.rounds_denied == 1


def test_sdk_adapter_complete_messages_do_not_need_partial_events():
    adapter = SDKEventAdapter(show_reasoning=True)
    events = adapter.feed(
        AssistantMessage(
            model="test",
            content=[
                ThinkingBlock(thinking="plan", signature="sig"),
                ToolUseBlock(id="t", name=SEARCH_TOOL_NAME, input={"query": "x"}),
                TextBlock(text="answer"),
            ],
        )
    )
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "answer_delta",
    ]


def test_sdk_adapter_does_not_reset_partial_flags_on_intermediate_snapshots():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={"type": "message_start", "message": {}},
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Same plan"},
            },
        ),
        AssistantMessage(model="test", content=[]),
        AssistantMessage(
            model="test",
            content=[ThinkingBlock(thinking="Same plan", signature="sig")],
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {"type": "reasoning_start"},
        {"type": "reasoning_delta", "text": "Same plan"},
        {"type": "reasoning_end"},
    ]


def test_sdk_adapter_closes_reasoning_before_next_message_start():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "First"},
            },
        ),
        StreamEvent(
            uuid="4", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
    ]


def test_sdk_adapter_surfaces_hugging_face_billing_errors():
    adapter = SDKEventAdapter(show_reasoning=False)

    events = adapter.feed(
        AssistantMessage(model="test", content=[], error="billing_error")
    )

    assert events == [
        {
            "type": "error",
            "code": "hf_inference_billing_exhausted",
            "message": (
                "Hugging Face could not bill this request. Your included credits "
                "may be exhausted; enable or review pay-as-you-go billing in Settings."
            ),
        }
    ]


@pytest.mark.parametrize(
    ("provider_error", "code"),
    [
        ("authentication_failed", "hf_inference_credential_expired"),
        ("rate_limit", "provider_rate_limit"),
        ("server_error", "provider_unavailable"),
        ("invalid_request", "provider_invalid_request"),
        ("unknown", "provider_error"),
    ],
)
def test_sdk_adapter_keeps_provider_failures_distinct(provider_error, code):
    events = SDKEventAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error=provider_error)
    )

    assert events[0]["type"] == "error"
    assert events[0]["code"] == code


def test_sdk_adapter_hides_leading_whitespace_and_over_budget_searches():
    adapter = SDKEventAdapter(show_reasoning=True, policy=_local_tool_event_policy(2))
    events = []
    for message in [
        AssistantMessage(model="test", content=[TextBlock(text="\n\n")]),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t1", name=SEARCH_TOOL_NAME, input={"query": "one"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t2", name=SEARCH_TOOL_NAME, input={"query": "two"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t3", name=SEARCH_TOOL_NAME, input={"query": "three"})
            ],
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="t3", content="The search limit was reached"
                )
            ]
        ),
        AssistantMessage(model="test", content=[TextBlock(text="Final answer")]),
    ]:
        events.extend(adapter.feed(message))

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_call",
        "answer_delta",
    ]
    assert [event.get("id") for event in events[:2]] == ["t1", "t2"]


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, _condition):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, papers, conference_rows=None):
        self.papers = papers
        self.conference_rows = conference_rows or []
        self.closed = False

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is chat_mcp.DBPaper:
            return _FakeQuery(self.papers)
        if len(entities) == 2 and entities[1] is chat_mcp.DBConference:
            return _FakeQuery(self.conference_rows)
        return _FakeQuery([])

    def close(self):
        self.closed = True


def test_search_payload_supports_external_rows_and_bounds_content(monkeypatch):
    paper = SimpleNamespace(
        id=9,
        arxiv_id=None,
        source="external",
        source_url="https://example.com/release",
        thumbnail_url="/api/thumbnails/custom/9.webp",
        title="Release",
        abstract="x" * 5_000,
        date_published=date(2026, 7, 1),
        conference="Legacy Conference",
        citation_count=4,
    )
    session = _FakeSession(
        [paper], [(9, SimpleNamespace(name="Linked Conference", year=2026))]
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def search_papers(self, query, limit, mode):
            assert query == "model"
            assert limit == 3
            assert mode == "keyword"
            return [SimpleNamespace(id="9")]

        def hydrate_cards(self, papers, include_resources):
            assert papers == [paper]
            assert include_resources
            return [
                SimpleNamespace(
                    id="9",
                    arxiv_id=None,
                    source="external",
                    source_url="https://example.com/release",
                    thumbnail_url="/api/thumbnails/custom/9.webp",
                    title="Release",
                    abstract="x" * 5_000,
                    authors=["Lab"],
                    published=date(2026, 7, 1),
                    conference="Legacy Conference",
                    citation_count=4,
                    tasks=[SimpleNamespace(name="Language Modeling", slug="lm")],
                    methods=[SimpleNamespace(name="Transformer", slug="transformer")],
                    repositories=[
                        SimpleNamespace(
                            url="https://github.com/acme/model", num_stars=10
                        )
                    ],
                    project_pages=[SimpleNamespace(url="https://acme.example/model")],
                )
            ]

    monkeypatch.setattr(chat_mcp, "PaperService", FakePaperService)
    payload = chat_mcp.search_papers_payload(
        "model", 3, session_factory=lambda: session
    )
    hit = payload["results"][0]
    assert session.closed
    assert hit["route_id"] == "9"
    assert hit["metadata"]["source"] == "external"
    assert hit["metadata"]["thumbnail_url"] == "/api/thumbnails/custom/9.webp"
    assert hit["metadata"]["conference"] == "Linked Conference"
    assert len(hit["content"]) == 4_000
    assert hit["content_truncated"] is True
    assert chat_mcp._serialized_size(payload) <= 40_000


def test_result_byte_cap_handles_multibyte_content():
    metadata = {
        "arxiv_id": None,
        "source": "external",
        "source_url": "https://example.com",
        "authors": [],
        "published": None,
        "conference": None,
        "citation_count": None,
        "tasks": [],
        "methods": [],
        "repositories": [],
        "project_pages": [],
    }
    payload = {
        "hits": 10,
        "took_ms": 1,
        "results": [
            {
                "route_id": str(index),
                "title": "paper",
                "content": "界" * 4_000,
                "content_truncated": False,
                "metadata": dict(metadata),
            }
            for index in range(10)
        ],
    }
    chat_mcp._enforce_result_bytes(payload)
    assert chat_mcp._serialized_size(payload) <= chat_mcp.MAX_RESULT_BYTES
    assert payload["results"][-1]["content_truncated"] is True


def test_agent_options_expose_only_search(tmp_path):
    settings = get_settings().model_copy(
        update={
            "hf_token": "shared-nielsr-token",
            "chat_max_search_calls": 2,
        }
    )
    options, _ = build_agent_options(
        settings, tmp_path, provider_token="connected-user-token"
    )
    assert options.tools == []
    assert options.allowed_tools == [SEARCH_TOOL_NAME]
    assert options.setting_sources == []
    assert options.skills == []
    assert options.plugins == []
    assert options.fallback_model is None
    assert options.env["ANTHROPIC_API_KEY"] == "connected-user-token"
    assert options.env["ANTHROPIC_AUTH_TOKEN"] == "connected-user-token"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://router.huggingface.co"
    assert "shared-nielsr-token" not in options.env.values()
    assert "HF_BILL_TO" not in options.env
    assert "ANTHROPIC_CUSTOM_HEADERS" not in options.env
    assert "at most 2 times" in options.system_prompt
    assert "mcp__web__search_web" not in options.allowed_tools
    assert "mcp__web__search_web" in options.disallowed_tools
    assert "web" not in options.mcp_servers
    assert "search_web" not in options.system_prompt
    assert (
        "[repo_id](https://huggingface.co/datasets/<repo_id>)" in options.system_prompt
    )
    assert "[owner/repo](https://github.com/owner/repo)" in options.system_prompt
    assert "Never output a bare repository" in options.system_prompt
    assert (
        "Always favor native paper hyperlinks instead of arXiv links, unless the user "
        "explicitly asks for an arXiv link." in options.system_prompt
    )
    assert "When comparing papers, prefer a Markdown table." in options.system_prompt

    openrouter, _ = build_agent_options(
        settings,
        tmp_path,
        provider_token="openrouter-token",
        provider_base_url="https://openrouter.ai/api",
        model_route=settings.chat_deepseek_v4_flash_openrouter_route,
    )
    assert openrouter.model == "deepseek/deepseek-v4-flash-0731"
    assert openrouter.env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
    assert openrouter.env["ANTHROPIC_AUTH_TOKEN"] == "openrouter-token"

    web, _ = build_agent_options(
        settings,
        tmp_path,
        provider_token="connected-user-token",
        web_search_enabled=True,
        owner_hash="a" * 64,
    )
    assert "mcp__web__search_web" in web.allowed_tools
    assert "mcp__web__search_web" not in web.disallowed_tools
    assert "web" in web.mcp_servers
    assert "search_web" in web.system_prompt


def test_failed_turn_keeps_partial_tool_projection():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        active_turn_expires_at=None,
        projection_bytes=0,
        updated_at=None,
    )
    message = SimpleNamespace(status="generating", error_code=None, display_blocks=[])

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return message if key == message_id else None

    admission = SimpleNamespace(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=message_id,
    )
    blocks = [
        {
            "kind": "tool",
            "id": "t1",
            "name": "search_papers",
            "args": {"query": "object detection"},
            "status": "done",
            "hits": 0,
            "took_ms": 10,
            "results": [],
        }
    ]

    ChatSessionService(FakeDB(), get_settings()).fail_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        "provider_error",
        display_blocks=blocks,
    )

    assert message.status == "error"
    assert message.error_code == "provider_error"
    assert message.display_blocks == blocks
    assert session.active_turn_id is None
    assert session.projection_bytes > 0


def test_completed_turn_persists_finish_reason_in_authenticated_history():
    from backend.routers.chat import _message

    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        last_sequence=1,
        message_count=1,
        projection_bytes=0,
        updated_at=None,
    )
    user_message = SimpleNamespace(status="generating")

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def __init__(self):
            self.added = []

        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return user_message if key == user_message_id else None

        def add(self, value):
            self.added.append(value)

        def flush(self):
            for value in self.added:
                value.revision = 1
                value.created_at = datetime.now(UTC)

    db = FakeDB()
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
    )

    assistant = ChatSessionService(db, get_settings()).complete_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        answer="Bounded answer",
        citations=[],
        followups=[],
        display_blocks=[],
        finish_reason="scope_blocked",
    )

    assert assistant.finish_reason == "scope_blocked"
    assert _message(assistant).finish_reason == "scope_blocked"


def test_agent_timeout_emits_typed_error_and_closes_sdk_stream(monkeypatch):
    from backend.services import chat_agent_service

    state = {"closed": False}

    async def fake_query(**_kwargs):
        try:
            await asyncio.sleep(1)
            yield None
        finally:
            state["closed"] = True

    async def collect():
        settings = get_settings().model_copy(
            update={"hf_token": "test", "chat_timeout_seconds": 0.01}
        )
        return [
            event
            async for event in stream_agent_events(
                "hello",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=None,
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert events == [
        {
            "type": "error",
            "code": "provider_timeout",
            "message": "The model provider timed out. Try again shortly.",
        }
    ]
    assert state["closed"] is True


def test_local_agent_max_turns_runs_one_same_session_tool_free_finalizer(monkeypatch):
    from backend.chat_execution_policy import FINALIZER_PROMPT
    from backend.services import chat_agent_service

    calls = []

    def fake_query(*, prompt, options):
        calls.append((prompt, options))

        async def messages():
            if len(calls) == 1:
                yield ResultMessage(
                    subtype="error_max_turns",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=True,
                    num_turns=9,
                    session_id="session-a",
                    usage={"input_tokens": 10},
                )
            else:
                yield AssistantMessage(
                    model="test", content=[TextBlock(text="Recovered answer")]
                )
                yield ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id="session-a",
                    usage={"output_tokens": 4},
                )

        return messages()

    async def collect():
        settings = get_settings().model_copy(update={"chat_timeout_seconds": 30})
        return [
            event
            async for event in stream_agent_events(
                "Research this",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=object(),
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert len(calls) == 2
    assert calls[1][0] == FINALIZER_PROMPT
    assert calls[1][1].resume == "session-a"
    assert calls[1][1].max_turns == 1
    assert calls[1][1].tools == []
    assert calls[1][1].allowed_tools == []
    assert [event["type"] for event in events] == [
        "_sdk_session",
        "usage",
        "answer_delta",
        "usage",
        "_execution_telemetry",
        "done",
    ]
    assert events[-1]["finish_reason"] == "success"
    assert FINALIZER_PROMPT not in json.dumps(events)


def test_local_agent_skips_finalizer_without_minimum_deadline_window(monkeypatch):
    from backend.services import chat_agent_service

    calls = 0

    def fake_query(*, prompt, options):
        nonlocal calls
        calls += 1

        async def messages():
            yield ResultMessage(
                subtype="error_max_turns",
                duration_ms=1,
                duration_api_ms=1,
                is_error=True,
                num_turns=9,
                session_id="session-a",
            )

        return messages()

    async def collect():
        settings = get_settings().model_copy(update={"chat_timeout_seconds": 5})
        return [
            event
            async for event in stream_agent_events(
                "Research this",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=object(),
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert calls == 1
    assert events[-2]["type"] == "_execution_telemetry"
    assert events[-2]["finalizer_attempted"] is False
    assert events[-2]["finalizer_outcome"] == "insufficient_time"
    assert events[-1] == {
        "type": "done",
        "followups": [],
        "finish_reason": "tool_limit",
    }


def test_chat_endpoint_requires_authentication(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 401


def test_chat_endpoint_stream_contract(monkeypatch):
    from backend.routers import chat as chat_router
    from backend.services import chat_stream_service

    async def fake_stream(_prompt, _settings, **_kwargs):
        yield {"type": "answer_delta", "text": "hello"}
        yield {"type": "done", "followups": [], "finish_reason": "success"}

    async def fake_title(_prompt, _settings, **_kwargs):
        # Let research finish first: title events must still reach the client.
        assert _kwargs["provider_token"] == "title-test-token"
        assert "bill_to" not in _kwargs
        await asyncio.sleep(0.01)
        yield "Research chat"

    admission = SimpleNamespace(
        session_id="00000000-0000-0000-0000-000000000001",
        turn_id="00000000-0000-0000-0000-000000000002",
        user_message_id="00000000-0000-0000-0000-000000000003",
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
        replay_assistant=None,
        is_replacement=False,
        prompt_revision=1,
        title_should_generate=True,
        execution_backend="local_mcp",
        agent_harness="pi",
    )

    commits = []

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            commits.append(True)

    class FakeService:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            return admission

        def begin_title(self, *_args, **_kwargs):
            return uuid.UUID("00000000-0000-0000-0000-000000000004")

        def complete_title(self, *_args, **_kwargs):
            return "Research chat"

        def complete_turn(self, *_args, **_kwargs):
            pass

        def citation_history(self, *_args, **_kwargs):
            return []

        def turn_is_active(self, *_args, **_kwargs):
            return True

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(settings, "chat_title_generation_enabled", True)
    monkeypatch.setattr(settings, "chat_openrouter_api_key", "title-test-token")
    monkeypatch.setattr(settings, "chat_openrouter_server_funded_enabled", True)
    monkeypatch.setattr(settings, "chat_title_hf_token", "title-test-token")
    monkeypatch.setattr(settings, "chat_title_bill_to", "huggingface")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )

    async def authorize_openrouter(*_args, **_kwargs):
        assert commits, "durable admission must release its locks before provider I/O"
        return chat_router.OpenRouterAdmission(
            "openrouter_funded", "title-test-token", None
        )

    monkeypatch.setattr(chat_router, "_authorize_openrouter", authorize_openrouter)

    class FakeLatencyService:
        def __init__(self, *_args):
            pass

        def admit(self, **_kwargs):
            return None

    monkeypatch.setattr(chat_router, "ChatLatencyService", FakeLatencyService)

    class FakeRunner:
        sdk_directory = settings.chat_agent_cwd

        def events(self):
            return fake_stream("", settings)

        async def cancel(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(
        chat_stream_service,
        "create_chat_turn_runner",
        lambda **_kwargs: FakeRunner(),
    )
    monkeypatch.setattr(chat_stream_service, "stream_title", fake_title)

    class FakeTitleBudget:
        def __init__(self, *_args):
            pass

        def reserve_call(self, *_args):
            return None

        def mark_dispatched(self, *_args):
            return None

        def settle_call(self, *_args, **_kwargs):
            return 1

    monkeypatch.setattr(chat_stream_service, "ChatTitleBudgetService", FakeTitleBudget)
    monkeypatch.setattr(chat_router, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            headers={"Last-Event-ID": "not-a-cursor"},
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-store, no-transform"
    assert response.content.startswith(
        b": " + (b" " * chat_router.SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
    )
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["type"] for event in events] == [
        "stream_start",
        "answer_delta",
        "done",
        "session_title_start",
        "session_title_delta",
        "session_title_done",
    ]


def test_closing_stream_persists_interrupted_turn(monkeypatch):
    from backend.services import chat_stream_service

    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
    )
    persisted = []
    released = []
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_failure",
        lambda *args: persisted.append(args),
    )

    class Trace(chat_stream_service.NullChatTurnTrace):
        def __init__(self):
            self.finishes = []

        def finish(self, answer, status, **details):
            self.finishes.append((answer, status, details))

    trace = Trace()

    @contextmanager
    def trace_turn(**_kwargs):
        yield trace

    monkeypatch.setattr(chat_stream_service, "trace_chat_turn", trace_turn)

    async def scenario():
        orchestrator = ChatStreamOrchestrator(
            settings=get_settings().model_copy(update={"environment": "development"}),
            owner=ChatOwner(hf_user_id="hf-user", hf_username="tester"),
            admission=admission,
            prompt="hello",
            request_id=str(uuid.uuid4()),
            title_token=None,
            is_disconnected=lambda: asyncio.sleep(0, result=False),
            release_admission=lambda: asyncio.sleep(0, result=released.append(True)),
        )
        stream = orchestrator.events()
        first = await anext(stream)
        await stream.aclose()
        return first, orchestrator

    first, orchestrator = asyncio.run(scenario())

    assert first.event == "stream_start"
    assert persisted[0][2] == admission
    assert persisted[0][3:] == ("interrupted", True, [])
    assert orchestrator.terminal_label == "interrupted"
    assert trace.finishes[-1] == (
        "",
        "interrupted",
        {"interruption_reason": "stream_closed"},
    )
    assert released == [True]


def test_closing_completed_stream_preserves_successful_trace(monkeypatch):
    from backend.services import chat_stream_service

    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
    )

    class Trace(chat_stream_service.NullChatTurnTrace):
        def __init__(self):
            self.finishes = []

        def finish(self, answer, status, **details):
            self.finishes.append((answer, status, details))

    trace = Trace()

    @contextmanager
    def trace_turn(**_kwargs):
        yield trace

    monkeypatch.setattr(chat_stream_service, "trace_chat_turn", trace_turn)

    async def scenario():
        orchestrator = ChatStreamOrchestrator(
            settings=get_settings().model_copy(update={"environment": "development"}),
            owner=ChatOwner(hf_user_id="hf-user", hf_username="tester"),
            admission=admission,
            prompt="hello",
            request_id=str(uuid.uuid4()),
            title_token=None,
            is_disconnected=lambda: asyncio.sleep(0, result=False),
            release_admission=lambda: asyncio.sleep(0),
        )

        async def completed_events():
            orchestrator._transition_completion_reason("success")
            yield chat_stream_service.ChatStreamFrame(
                "done", {"followups": [], "finish_reason": "success"}
            )

        monkeypatch.setattr(orchestrator, "_events", completed_events)
        stream = orchestrator.events()
        frame = await anext(stream)
        await stream.aclose()
        return frame, orchestrator

    frame, orchestrator = asyncio.run(scenario())

    assert frame.event == "done"
    assert orchestrator.terminal_label == "success"
    assert trace.finishes[-1] == ("", "success", {})


def test_paper_turn_enables_content_free_tracing(monkeypatch):
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test-model",
        model_route="test-route",
        sdk_session_id=None,
        sdk_project_key=None,
        paper_artifacts_enabled=True,
    )
    trace_arguments = {}

    @contextmanager
    def trace_turn(**kwargs):
        trace_arguments.update(kwargs)
        yield chat_stream_service.NullChatTurnTrace()

    monkeypatch.setattr(chat_stream_service, "trace_chat_turn", trace_turn)
    monkeypatch.setattr(chat_stream_service, "_persist_trace_id", lambda *_args: None)
    orchestrator = ChatStreamOrchestrator(
        settings=get_settings().model_copy(update={"environment": "development"}),
        owner=ChatOwner(hf_user_id="test-user", hf_username="tester"),
        admission=admission,
        prompt="MANUSCRIPT-CANARY",
        request_id=str(uuid.uuid4()),
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )

    async def no_events():
        if False:
            yield None

    monkeypatch.setattr(orchestrator, "_events", no_events)

    async def consume():
        async for _frame in orchestrator.events():
            pass

    asyncio.run(consume())

    assert trace_arguments["content_free"] is True


def test_trace_id_persistence_does_not_block_event_loop(monkeypatch):
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test-model",
        model_route="test-route",
        sdk_session_id=None,
        sdk_project_key=None,
    )
    persistence_threads = []

    class Trace(chat_stream_service.NullChatTurnTrace):
        trace_id = "a" * 32

    @contextmanager
    def trace_turn(**_kwargs):
        yield Trace()

    monkeypatch.setattr(chat_stream_service, "trace_chat_turn", trace_turn)
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_trace_id",
        lambda *_args: persistence_threads.append(threading.get_ident()),
    )
    orchestrator = ChatStreamOrchestrator(
        settings=get_settings().model_copy(update={"environment": "development"}),
        owner=ChatOwner(hf_user_id="test-user", hf_username="tester"),
        admission=admission,
        prompt="hello",
        request_id=str(uuid.uuid4()),
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )

    async def dispatched_events():
        yield chat_stream_service.ChatStreamFrame("stream_start")
        assert persistence_threads == []
        yield chat_stream_service.ChatStreamFrame("workspace_ready")

    monkeypatch.setattr(orchestrator, "_events", dispatched_events)

    async def consume():
        event_loop_thread = threading.get_ident()
        async for _frame in orchestrator.events():
            pass
        await orchestrator.trace_id_persistence_task
        return event_loop_thread

    event_loop_thread = asyncio.run(consume())

    assert len(persistence_threads) == 1
    assert persistence_threads[0] != event_loop_thread


def test_chat_endpoint_rejects_when_capacity_is_occupied(monkeypatch, caplog):
    from backend.routers import chat as chat_router

    calls = {"begin_turn": 0, "runner": 0}

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def rollback(self):
            return None

    class NoCapacity:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            calls["begin_turn"] += 1
            raise ChatServiceError(
                "chat_capacity",
                429,
                "Research capacity is currently occupied",
                active_count=2,
            )

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", NoCapacity)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(
        chat_router,
        "ChatStreamOrchestrator",
        lambda **_kwargs: calls.__setitem__("runner", calls["runner"] + 1),
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "chat_capacity"
    assert response.headers["retry-after"] == "5"
    assert calls == {"begin_turn": 1, "runner": 0}
    assert "chat capacity denied environment=" in caplog.text
    assert "ceiling=" in caplog.text
    assert "denial_count=" in caplog.text
    assert "hello" not in caplog.text


def test_stream_endpoint_rejects_forged_qualification_scope_header(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="staging",
        release_id="0123456789ab-staging",
        chat_durable_turn_dispatch_enabled=True,
    )
    monkeypatch.setattr(
        chat_router, "has_valid_non_cookie_admin_credential", lambda *_args: True
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-pwc-qualification-scope-id", b"forged-not-a-uuid"),
                (b"x-pwc-qualification-workload", b"no_tool"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        chat_router._durable_qualification_scope(request, settings)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "qualification_scope_rejected"}


def test_stream_endpoint_rejects_nonexistent_active_qualification_scope(
    monkeypatch,
):
    from backend.services.chat_durable_qualification_evidence import (
        QualificationEvidenceUnavailable,
    )

    scope_id = uuid.uuid4()
    settings = Settings(
        _env_file=None,
        environment="staging",
        release_id="0123456789ab-staging",
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_durable_turn_dispatch_enabled=True,
        hf_token="test-token",
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def rollback(self):
            return None

    class MissingScope:
        def __init__(self, _db):
            pass

        def require_active_context(self, *_args, **_kwargs):
            raise QualificationEvidenceUnavailable("scope does not exist")

    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        chat_router, "has_valid_non_cookie_admin_credential", lambda *_args: True
    )
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-token", bill_to=None),
    )
    monkeypatch.setattr(
        chat_router.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    monkeypatch.setattr(
        chat_router,
        "_prepare_paper_turn",
        lambda *_args: chat_router.PreparedPaperTurn("hello", "hello", [], 0, 0, 0),
    )
    monkeypatch.setattr(
        chat_router, "ChatDurableQualificationEvidenceService", MissingScope
    )
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-pwc-qualification-scope-id", str(scope_id).encode()),
                (b"x-pwc-qualification-workload", b"no_tool"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                ChatRequest(message="hello", client_message_id="qualified-request"),
                request,
                {"hf_user_id": "operator", "username": "operator"},
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "qualification_scope_unavailable"}


def test_paper_hydration_failure_precedes_turn_admission_and_runner(monkeypatch):
    from backend.routers import chat as chat_router

    calls = {"begin_turn": 0, "runner": 0}

    class NoAdmission:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            calls["begin_turn"] += 1
            raise AssertionError("turn admission must not run")

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_default_backend", "local_mcp")
    monkeypatch.setattr(settings, "chat_paper_mentions_enabled", True)
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )

    def fail_preparation(*_args):
        raise ChatServiceError(
            "paper_context_unavailable",
            503,
            "Attached paper context could not be prepared.",
        )

    monkeypatch.setattr(
        chat_router,
        "_prepare_paper_turn",
        fail_preparation,
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", NoAdmission)
    monkeypatch.setattr(
        chat_router,
        "ChatStreamOrchestrator",
        lambda **_kwargs: calls.__setitem__("runner", calls["runner"] + 1),
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "message": "Read Paper",
                "client_message_id": "paper-client-id",
                "paper_mentions": [
                    {
                        "route_id": "2501.00001",
                        "title": "Paper",
                        "start": 5,
                        "end": 10,
                    }
                ],
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "paper_context_unavailable"
    assert calls == {"begin_turn": 0, "runner": 0}


def test_new_chat_capacity_rejection_precedes_session_creation(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((0, 2))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    settings = get_settings().model_copy(update={"chat_max_concurrency": 2})
    service = ChatSessionService(FakeDB(), settings)
    created = []
    monkeypatch.setattr(
        service,
        "create_session",
        lambda *_args, **_kwargs: created.append(True),
    )

    with pytest.raises(ChatServiceError) as error:
        service.begin_turn(
            ChatOwner(hf_user_id="third-user", hf_username="third"),
            session_id=None,
            client_message_id="third-request",
            text="This content must not be stored",
        )

    assert error.value.code == "chat_capacity"
    assert error.value.active_count == 2
    assert created == []


def test_one_user_can_admit_two_concurrent_active_turns(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((1, 1))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    class ReachedSessionCreation(Exception):
        pass

    def reached_creation(*_args, **_kwargs):
        raise ReachedSessionCreation

    settings = get_settings().model_copy(
        update={"chat_max_concurrency": 2, "chat_user_max_concurrency": 2}
    )
    service = ChatSessionService(FakeDB(), settings)
    monkeypatch.setattr(
        service,
        "create_session",
        reached_creation,
    )

    with pytest.raises(ReachedSessionCreation):
        service.begin_turn(
            ChatOwner(hf_user_id="same-user", hf_username="same"),
            session_id=None,
            client_message_id="second-request",
            text="A second concurrent turn is allowed",
        )
