import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import threading
import time
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_event_service import (
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


def test_sdk_session_persistence_does_not_block_other_streams(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    orchestrator = _orchestrator()

    def slow_bind(_payload) -> None:
        entered.set()
        release.wait(timeout=0.5)

    monkeypatch.setattr(orchestrator, "_bind_sdk_session", slow_bind)

    async def exercise() -> None:
        persistence = asyncio.create_task(
            orchestrator._handle_persistence_event(
                PersistenceEvent(session_id=str(uuid.uuid4()))
            )
        )
        while not entered.is_set():
            await asyncio.sleep(0)
        release.set()
        await persistence

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
        persistence = asyncio.create_task(
            orchestrator._handle_persistence_event(
                PersistenceEvent(session_id=str(uuid.uuid4()))
            )
        )
        while not entered.is_set():
            await asyncio.sleep(0)
        persistence.cancel()
        await asyncio.sleep(0)
        assert not persistence.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await persistence
        assert completed.is_set()

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
