import asyncio
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
import threading
import time
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_event_service import (
    CompletionEvent,
    LatencyEvent,
    PersistenceEvent,
    from_legacy_event,
)


def _orchestrator() -> ChatStreamOrchestrator:
    return ChatStreamOrchestrator(
        settings=get_settings(),
        owner=ChatOwner("owner", "owner"),
        admission=TurnAdmission(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            selected_model="model",
            model_route="route",
            sdk_session_id=None,
            sdk_project_key=None,
        ),
        prompt="Explain transformers",
        request_id=str(uuid.uuid4()),
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )


def test_latency_telemetry_does_not_block_the_stream_on_database_latency(
    monkeypatch,
) -> None:
    from backend.services import chat_stream_service

    class Session:
        def commit(self) -> None:
            return None

    @contextmanager
    def session_local():
        yield Session()

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )

    def slow_record(*_args, **_kwargs) -> bool:
        time.sleep(0.2)
        return True

    monkeypatch.setattr(
        chat_stream_service.ChatLatencyService, "record_phase", slow_record
    )
    event = from_legacy_event(
        {"type": "_latency", "phase": "agent_session_ready", "elapsed_ms": 125}
    )
    assert isinstance(event, LatencyEvent)
    orchestrator = _orchestrator()

    started = time.perf_counter()
    asyncio.run(orchestrator._handle_latency_event(event))

    assert time.perf_counter() - started < 0.05


def test_sdk_session_persistence_does_not_block_first_token_path(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    orchestrator = _orchestrator()

    def slow_bind(_payload) -> None:
        entered.set()
        release.wait(timeout=0.5)

    monkeypatch.setattr(orchestrator, "_bind_sdk_session", slow_bind)

    async def exercise() -> None:
        await orchestrator._handle_persistence_event(
            PersistenceEvent(session_id=str(uuid.uuid4()))
        )
        while not entered.is_set():
            await asyncio.sleep(0)
        assert orchestrator.sdk_session_persistence_task is not None
        assert not orchestrator.sdk_session_persistence_task.done()
        release.set()
        await orchestrator._await_sdk_session_persistence()

    started = time.perf_counter()
    asyncio.run(exercise())

    assert time.perf_counter() - started < 0.1


def test_sdk_session_persistence_finishes_before_cancellation_is_delivered(
    monkeypatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    orchestrator = _orchestrator()

    def slow_bind(_payload) -> None:
        entered.set()
        release.wait(timeout=0.5)
        completed.set()

    monkeypatch.setattr(orchestrator, "_bind_sdk_session", slow_bind)

    async def exercise() -> None:
        await orchestrator._handle_persistence_event(
            PersistenceEvent(session_id=str(uuid.uuid4()))
        )
        while not entered.is_set():
            await asyncio.sleep(0)
        persistence = asyncio.create_task(orchestrator._await_sdk_session_persistence())
        await asyncio.sleep(0)
        persistence.cancel()
        await asyncio.sleep(0)
        assert not persistence.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await persistence
        assert completed.is_set()

    asyncio.run(exercise())


def test_terminal_persistence_waits_for_sdk_session_binding(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    bound = threading.Event()
    terminal = threading.Event()
    orchestrator = _orchestrator()

    def slow_bind(_payload) -> None:
        entered.set()
        release.wait(timeout=0.5)
        bound.set()

    def persist_terminal() -> None:
        assert bound.is_set()
        terminal.set()

    monkeypatch.setattr(orchestrator, "_bind_sdk_session", slow_bind)

    async def exercise() -> None:
        await orchestrator._handle_persistence_event(
            PersistenceEvent(session_id=str(uuid.uuid4()))
        )
        while not entered.is_set():
            await asyncio.sleep(0)
        persistence = asyncio.create_task(
            orchestrator._persist_terminal_with_lease(persist_terminal)
        )
        await asyncio.sleep(0)
        assert not terminal.is_set()
        release.set()
        await persistence
        assert terminal.is_set()

    asyncio.run(exercise())


def test_sdk_session_bind_failure_prevents_durable_terminal_frame() -> None:
    orchestrator = _orchestrator()
    orchestrator.settings = orchestrator.settings.model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    completion = from_legacy_event(
        {"type": "done", "followups": [], "finish_reason": "success"}
    )
    assert isinstance(completion, CompletionEvent)

    async def fail_bind() -> None:
        raise RuntimeError("sdk bind failed")

    async def exercise() -> None:
        orchestrator.sdk_session_persistence_task = asyncio.create_task(fail_bind())
        with pytest.raises(RuntimeError, match="sdk bind failed"):
            await orchestrator._handle_completion_event(completion)
        assert orchestrator.terminal_persistence.completion is None

    asyncio.run(exercise())


def test_terminal_latency_flushes_buffered_phases_in_one_transaction(
    monkeypatch,
) -> None:
    from backend.services import chat_stream_service

    calls: list[tuple] = []

    class Session:
        def commit(self) -> None:
            calls.append(("commit",))

    @contextmanager
    def session_local():
        yield Session()

    class LatencyService:
        def __init__(self, _db) -> None:
            pass

        def record_phase(self, request_id, phase, elapsed_ms, **kwargs) -> bool:
            calls.append(("phase", request_id, phase, elapsed_ms, kwargs))
            return True

        def record_pool_assignment_fallback(self, request_id) -> bool:
            calls.append(("fallback", request_id))
            return True

        def finalize(self, request_id, status, total_ms) -> bool:
            calls.append(("finalize", request_id, status, total_ms))
            return True

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(chat_stream_service, "ChatLatencyService", LatencyService)
    orchestrator = _orchestrator()
    orchestrator._buffer_latency_phase("agent_session_ready", 125)
    orchestrator._buffer_latency_phase(
        "sandbox_acquisition_started",
        250,
        acquisition_outcome="pool_miss",
        pool_miss_reason="unhealthy_blank",
    )

    orchestrator._persist_latency("complete", 500)

    assert [call[0] for call in calls] == [
        "phase",
        "phase",
        "fallback",
        "finalize",
        "commit",
    ]


def test_invalid_latency_phase_does_not_drop_other_phases_or_finalize(
    monkeypatch,
) -> None:
    from backend.services import chat_stream_service

    calls: list[tuple] = []

    class Session:
        def commit(self) -> None:
            calls.append(("commit",))

    @contextmanager
    def session_local():
        yield Session()

    class LatencyService:
        def __init__(self, _db) -> None:
            pass

        def record_phase(self, _request_id, phase, _elapsed_ms, **_kwargs) -> bool:
            calls.append(("phase", phase))
            if phase == "unsupported":
                raise ValueError("unsupported phase")
            return True

        def record_pool_assignment_fallback(self, _request_id) -> bool:
            return True

        def finalize(self, _request_id, status, total_ms) -> bool:
            calls.append(("finalize", status, total_ms))
            return True

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(chat_stream_service, "ChatLatencyService", LatencyService)
    orchestrator = _orchestrator()
    orchestrator._buffer_latency_phase("unsupported", 10)
    orchestrator._buffer_latency_phase("agent_session_ready", 125)

    orchestrator._persist_latency("complete", 500)

    assert calls == [
        ("phase", "unsupported"),
        ("phase", "agent_session_ready"),
        ("finalize", "complete", 500),
        ("commit",),
    ]


def test_latency_database_failure_retries_terminal_finalize_in_a_fresh_session(
    monkeypatch,
) -> None:
    from backend.services import chat_stream_service

    calls: list[tuple] = []
    session_count = 0

    class Session:
        def __init__(self, number: int) -> None:
            self.number = number

        def commit(self) -> None:
            calls.append(("commit", self.number))

    @contextmanager
    def session_local():
        nonlocal session_count
        session_count += 1
        yield Session(session_count)

    class LatencyService:
        def __init__(self, db) -> None:
            self.session_number = db.number

        def record_phase(self, *_args, **_kwargs) -> bool:
            calls.append(("phase", self.session_number))
            raise RuntimeError("database write failed")

        def record_pool_assignment_fallback(self, _request_id) -> bool:
            return True

        def finalize(self, _request_id, status, total_ms) -> bool:
            calls.append(("finalize", self.session_number, status, total_ms))
            return True

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(chat_stream_service, "ChatLatencyService", LatencyService)
    orchestrator = _orchestrator()
    orchestrator._buffer_latency_phase("agent_session_ready", 125)

    orchestrator._persist_latency("complete", 500)

    assert calls == [
        ("phase", 1),
        ("finalize", 2, "complete", 500),
        ("commit", 2),
    ]


def test_session_acquisition_outcome_names_created_or_resumed_agent_sessions():
    orchestrator = _orchestrator()
    assert orchestrator._session_acquisition_outcome() == "reused_session"

    orchestrator.admission = replace(orchestrator.admission, is_first_turn=True)
    assert orchestrator._session_acquisition_outcome() == "created"

    # Sandbox-backed turns already report their pool outcome; never override it.
    orchestrator._buffer_latency_phase(
        "pool_lookup_completed", 20, acquisition_outcome="pool_hit"
    )
    assert orchestrator._session_acquisition_outcome() is None


def test_failure_attribution_follows_turn_progress_and_lifecycle_code():
    orchestrator = _orchestrator()
    assert orchestrator._failure_attribution("complete") == (None, None)
    assert orchestrator._failure_attribution("error") == ("before_dispatch", "unknown")

    orchestrator._buffer_latency_phase("sdk_query_dispatched", 900)
    orchestrator._transition_failure("external_worker_lost")
    assert orchestrator._failure_attribution("error") == (
        "awaiting_first_event",
        "external_worker_lost",
    )

    orchestrator._buffer_latency_phase("first_semantic_event", 1500)
    assert orchestrator._failure_attribution("error") == (
        "streaming",
        "external_worker_lost",
    )


def test_error_finalize_carries_failure_attribution(monkeypatch) -> None:
    from backend.services import chat_stream_service

    calls: list[tuple] = []

    class Session:
        def commit(self) -> None:
            calls.append(("commit",))

    @contextmanager
    def session_local():
        yield Session()

    class LatencyService:
        def __init__(self, _db) -> None:
            pass

        def record_phase(self, request_id, phase, elapsed_ms, **kwargs) -> bool:
            calls.append(("phase", phase, kwargs.get("acquisition_outcome")))
            return True

        def finalize(self, request_id, status, total_ms, **kwargs) -> bool:
            calls.append(("finalize", status, kwargs))
            return True

    monkeypatch.setattr(
        chat_stream_service,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(chat_stream_service, "ChatLatencyService", LatencyService)
    orchestrator = _orchestrator()
    orchestrator._buffer_latency_phase(
        "sdk_query_dispatched",
        300,
        acquisition_outcome=orchestrator._session_acquisition_outcome(),
    )
    orchestrator._transition_failure("provider_error")

    orchestrator._persist_latency("error", 4000)

    assert calls == [
        ("phase", "sdk_query_dispatched", "reused_session"),
        (
            "finalize",
            "error",
            {
                "failure_stage": "awaiting_first_event",
                "failure_class": "provider_error",
            },
        ),
        ("commit",),
    ]
