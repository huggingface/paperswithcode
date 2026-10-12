"""Authenticated stream endpoint contract, interruption, and tracing."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import create_app
from backend.routers import chat as chat_router
from backend.services import chat_application_service as chat_application
from backend.services import chat_admission_service as chat_admission
from backend.services import chat_admission_billing as chat_billing
from backend.services import chat_stream_service
from backend.services.chat_session_service import (
    ChatOwner,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    ChatStreamOrchestrator,
)


from backend.utils.auth import require_user


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
        return chat_billing.OpenRouterAdmission(
            "openrouter_funded", "title-test-token", None
        )

    monkeypatch.setattr(chat_application, "authorize_openrouter", authorize_openrouter)

    class FakeLatencyService:
        def __init__(self, *_args):
            pass

        def admit(self, **_kwargs):
            return None

    monkeypatch.setattr(chat_admission, "ChatLatencyService", FakeLatencyService)

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
    monkeypatch.setattr(chat_admission, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_application, "ChatSessionService", FakeService)
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
