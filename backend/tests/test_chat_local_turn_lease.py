from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.config import get_settings
from backend.services import chat_session_service as chat_session_module
from backend.services import chat_stream_service
from backend.services.chat_local_turn_lease import (
    LOCAL_TURN_LEASE_OWNER,
    ChatLocalTurnLeaseService,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_event_service import (
    CompletionEvent,
    ResearchFinishedEvent,
    TerminalOutcome,
    TurnTerminalState,
)
from backend.services.chat_turn_job_repository import TurnLeaseClaim

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def _admission(*, claim: TurnLeaseClaim | None = None) -> TurnAdmission:
    return TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=claim.turn_id if claim else uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="gpt-5.6-luna@openai",
        model_route="gpt-5.6-luna@openai",
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        durable_claim=claim,
    )


def _orchestrator(settings, admission):
    return ChatStreamOrchestrator(
        settings=settings,
        owner=ChatOwner("owner-1", "owner"),
        admission=admission,
        prompt="research",
        request_id="request-1",
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )


def test_local_owner_identity_is_opaque_and_positive():
    assert re.fullmatch(r"local-runner:[0-9a-f]{32}", LOCAL_TURN_LEASE_OWNER.worker_id)
    assert LOCAL_TURN_LEASE_OWNER.worker_generation > 0
    assert not any(
        value in LOCAL_TURN_LEASE_OWNER.worker_id.lower()
        for value in ("root", "localhost", "/root", "prompt", "transcript")
    )
    assert LOCAL_TURN_LEASE_OWNER.create() != LOCAL_TURN_LEASE_OWNER


def test_claim_uses_exact_process_boot_fence_and_protected_lease():
    repository = Mock()
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 3)
    repository.claim.return_value = claim
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_lease_seconds": 30,
        }
    )
    service = ChatLocalTurnLeaseService(
        Mock(),
        settings,
        repository=repository,
        owner=type(
            "Owner", (), {"worker_id": "local-runner:abc", "worker_generation": 7}
        )(),
    )

    assert service.claim(claim.turn_id, now=NOW) == claim
    repository.claim.assert_called_once_with(
        service.db,
        turn_id=claim.turn_id,
        worker_id="local-runner:abc",
        worker_generation=7,
        now=NOW,
        lease_seconds=30,
    )


def test_local_lease_service_cannot_be_used_when_bridge_is_disabled():
    service = ChatLocalTurnLeaseService(Mock(), get_settings(), repository=Mock())

    with pytest.raises(RuntimeError, match="disabled"):
        service.claim(uuid.uuid4(), now=NOW)


def test_orchestrator_claims_and_starts_before_runner_dispatch(monkeypatch):
    order: list[str] = []
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, claim.worker_id, 7, 1)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )

    def claim_turn(_settings, current):
        order.append("claim")
        return current.__class__(
            **{
                name: getattr(current, name)
                for name in current.__dataclass_fields__
                if name != "durable_claim"
            },
            durable_claim=claim,
        )

    async def prepare(*_args, **_kwargs):
        order.append("prepare")

    monkeypatch.setattr(chat_stream_service, "_claim_local_turn", claim_turn)
    monkeypatch.setattr(chat_stream_service, "_prepare_replacement", prepare)
    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda *_args: order.append("heartbeat"),
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_start_local_turn",
        lambda *_args: order.append("running"),
    )

    def create_runner(**_kwargs):
        order.append("dispatch")
        raise RuntimeError("runner construction failed")

    monkeypatch.setattr(chat_stream_service, "create_chat_turn_runner", create_runner)
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_failure",
        lambda *_args: order.append("failed"),
    )
    orchestrator = _orchestrator(settings, admission)
    orchestrator._close = AsyncMock()

    async def collect():
        return [frame async for frame in orchestrator._events()]

    frames = asyncio.run(collect())

    assert [frame.event for frame in frames] == ["stream_start", "error"]
    assert order == ["claim", "prepare", "heartbeat", "running", "dispatch"]
    assert orchestrator.admission.durable_claim == claim


def test_durable_done_waits_for_detached_terminal_callback(monkeypatch):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    admission = _admission(claim=claim)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    orchestrator = _orchestrator(settings, admission)
    persisted = []
    monkeypatch.setattr(
        orchestrator, "_complete_turn", lambda event: persisted.append(dict(event))
    )

    async def exercise():
        queue = asyncio.Queue()
        await queue.put({"type": "done", "followups": [], "finish_reason": "success"})
        await queue.put({"type": "_research_finished"})
        stream = orchestrator._consume(queue)
        terminal = await anext(stream)
        assert persisted == []
        await orchestrator.persist_detached_terminal(claim, "completed", None)
        await stream.aclose()
        return terminal

    terminal = asyncio.run(exercise())

    assert terminal.event == "done"
    assert persisted == [{"followups": [], "finish_reason": "success", "citations": []}]
    assert orchestrator.lifecycle.terminal is TurnTerminalState.COMPLETED
    assert isinstance(orchestrator.terminal_persistence.completion, CompletionEvent)


def test_durable_consumer_accepts_typed_events_without_changing_stream_contract(
    monkeypatch,
):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    orchestrator = _orchestrator(settings, _admission(claim=claim))
    persisted = []
    monkeypatch.setattr(
        orchestrator, "_complete_turn", lambda event: persisted.append(dict(event))
    )

    async def exercise():
        queue = asyncio.Queue()
        await queue.put(
            CompletionEvent(
                TerminalOutcome.SUCCESS,
                followups=[],
            )
        )
        await queue.put(ResearchFinishedEvent())
        frames = [frame async for frame in orchestrator._consume(queue)]
        await orchestrator.persist_detached_terminal(claim, "completed", None)
        return frames

    frames = asyncio.run(exercise())

    assert [(frame.event, frame.payload) for frame in frames] == [
        (
            "done",
            {"followups": [], "finish_reason": "success", "citations": []},
        )
    ]
    assert persisted == [{"followups": [], "finish_reason": "success", "citations": []}]
    assert orchestrator.lifecycle.terminal is TurnTerminalState.COMPLETED
    assert isinstance(orchestrator.terminal_persistence.completion, CompletionEvent)


def test_detached_terminal_callback_transitions_lifecycle_without_source_terminal(
    monkeypatch,
):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    orchestrator = _orchestrator(settings, _admission(claim=claim))
    persisted = []
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_failure",
        lambda _owner, _settings, _admission, code, *_args: persisted.append(code),
    )

    asyncio.run(
        orchestrator.persist_detached_terminal(
            claim,
            "failed",
            "event_journal_exhausted",
        )
    )

    assert persisted == ["event_journal_exhausted"]
    assert orchestrator.lifecycle.terminal is TurnTerminalState.FAILED
    assert orchestrator.terminal_label == "error"


def test_execution_lost_event_persists_canonical_terminal_code(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    orchestrator = _orchestrator(settings, _admission())
    persisted = []
    monkeypatch.setattr(
        chat_stream_service.ChatCapabilityService,
        "provider_error_for_turn",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_failure",
        lambda _owner, _settings, _admission, code, *_args: persisted.append(code),
    )
    monkeypatch.setattr(chat_stream_service, "_legacy_turn_is_active", lambda *_: True)

    async def consume():
        queue = asyncio.Queue()
        await queue.put(
            {
                "type": "error",
                "message": "The sandbox execution could not be recovered.",
                "code": "execution_lost",
            }
        )
        await queue.put({"type": "_research_finished"})
        return [frame async for frame in orchestrator._consume(queue)]

    frames = asyncio.run(consume())

    assert [(frame.event, frame.payload["code"]) for frame in frames] == [
        ("error", "execution_lost")
    ]
    assert persisted == ["execution_lost"]


def test_durable_stream_start_payload_is_journal_serializable():
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    orchestrator = _orchestrator(settings, _admission())

    async def exercise():
        stream = orchestrator._events()
        frame = await anext(stream)
        assert orchestrator.terminal_persistence.begin()
        orchestrator.terminal_persistence.finish()
        await stream.aclose()
        return frame

    frame = asyncio.run(exercise())

    assert frame.event == "stream_start"
    assert json.loads(json.dumps(frame.payload))["session_id"] == str(
        orchestrator.admission.session_id
    )


def test_periodic_heartbeat_runs_during_continuous_work(monkeypatch):
    calls: list[TurnLeaseClaim] = []
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_heartbeat_seconds": 0.01,
        }
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_claim_local_turn",
        lambda _settings, current: current.__class__(
            **{
                name: getattr(current, name)
                for name in current.__dataclass_fields__
                if name != "durable_claim"
            },
            durable_claim=claim,
        ),
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda _settings, current: calls.append(current.durable_claim),
    )
    orchestrator = _orchestrator(settings, admission)

    async def exercise():
        await orchestrator._claim_durable_turn()
        await asyncio.sleep(0.035)
        await orchestrator._stop_lease_heartbeat()

    asyncio.run(exercise())

    assert len(calls) >= 2
    assert set(calls) == {claim}


def test_failed_detached_start_stops_claim_heartbeat():
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    orchestrator = _orchestrator(settings, _admission(claim=claim))

    async def exercise():
        orchestrator.lease_heartbeat_task = asyncio.create_task(asyncio.Event().wait())
        await orchestrator.abandon_detached_start()

    asyncio.run(exercise())

    assert orchestrator.lease_heartbeat_task is None


def test_blocked_replacement_is_cancelled_and_awaited_when_heartbeat_fails(
    monkeypatch,
):
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_heartbeat_seconds": 0.01,
        }
    )
    cleanup_finished = asyncio.Event()
    order: list[str] = []

    async def blocked_preparation(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            order.append("preparation_cleanup")
            cleanup_finished.set()

    monkeypatch.setattr(
        chat_stream_service, "_prepare_replacement", blocked_preparation
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda *_args: (_ for _ in ()).throw(ValueError("lease lost")),
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_persist_preparation_failure",
        lambda *_args: order.append("terminal_persisted"),
    )
    orchestrator = _orchestrator(
        settings, replace(_admission(claim=claim), is_replacement=True)
    )

    async def exercise():
        orchestrator.lease_heartbeat_task = asyncio.create_task(
            orchestrator._heartbeat_durable_turn()
        )
        result = await asyncio.wait_for(orchestrator._replacement_or_error(), 0.2)
        assert cleanup_finished.is_set()
        await orchestrator.persist_detached_terminal(
            claim, "failed", "replacement_prepare_failed"
        )
        return result

    assert asyncio.run(exercise()) == (False, None)
    assert order == ["preparation_cleanup", "terminal_persisted"]
    assert orchestrator.lease_heartbeat_task is None


@pytest.mark.parametrize("terminal_path", ["cancellation", "preparation", "close"])
def test_slow_terminal_keeps_heartbeat_live_until_transaction_returns(
    monkeypatch, terminal_path
):
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_heartbeat_seconds": 0.01,
        }
    )
    started = threading.Event()
    release = threading.Event()
    calls: list[TurnLeaseClaim] = []

    def slow_terminal(path):
        assert path == terminal_path
        started.set()
        assert release.wait(timeout=1)

    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda _settings, current: calls.append(current.durable_claim),
    )
    orchestrator = _orchestrator(settings, _admission(claim=claim))

    async def exercise():
        orchestrator.lease_heartbeat_task = asyncio.create_task(
            orchestrator._heartbeat_durable_turn()
        )
        terminal = asyncio.create_task(
            orchestrator._persist_terminal_with_lease(slow_terminal, terminal_path)
        )
        while not started.is_set():
            await asyncio.sleep(0)
        await asyncio.sleep(0.035)
        assert len(calls) >= 2
        release.set()
        await terminal
        stopped_at = len(calls)
        await asyncio.sleep(0.025)
        assert len(calls) == stopped_at

    asyncio.run(exercise())

    assert orchestrator.lease_heartbeat_task is None


@pytest.mark.parametrize("terminal_path", ["preparation_failure", "generic_failure"])
def test_cancelled_terminal_waits_for_transaction_without_orphan_or_duplicate(
    monkeypatch, terminal_path
):
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_heartbeat_seconds": 0.01,
        }
    )
    started = threading.Event()
    release = threading.Event()
    terminal_calls: list[str] = []
    heartbeats: list[TurnLeaseClaim] = []

    def blocked_terminal(path):
        terminal_calls.append(path)
        started.set()
        assert release.wait(timeout=1)

    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda _settings, current: heartbeats.append(current.durable_claim),
    )
    orchestrator = _orchestrator(settings, _admission(claim=claim))

    async def exercise():
        orchestrator.lease_heartbeat_task = asyncio.create_task(
            orchestrator._heartbeat_durable_turn()
        )
        terminal = asyncio.create_task(
            orchestrator._persist_terminal_with_lease(blocked_terminal, terminal_path)
        )
        while not started.is_set():
            await asyncio.sleep(0)
        terminal.cancel()
        await asyncio.sleep(0.025)
        first_count = len(heartbeats)
        assert first_count >= 1
        assert not terminal.done()
        terminal.cancel()
        await asyncio.sleep(0.025)
        assert len(heartbeats) > first_count
        assert not terminal.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await terminal
        stopped_at = len(heartbeats)
        await asyncio.sleep(0.025)
        assert len(heartbeats) == stopped_at

    asyncio.run(exercise())

    assert terminal_calls == [terminal_path]
    assert orchestrator.lease_heartbeat_task is None


@pytest.mark.parametrize("terminal_path", ["outer", "preparation", "generic"])
def test_orchestrator_cancellation_during_terminal_cleanup_is_exactly_once(
    monkeypatch, terminal_path
):
    admission = _admission()
    claim = TurnLeaseClaim(admission.turn_id, "local-runner:abc", 7, 1)
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_heartbeat_seconds": 0.01,
        }
    )
    started = threading.Event()
    release = threading.Event()
    terminal_calls: list[str] = []
    heartbeats: list[TurnLeaseClaim] = []

    def claim_turn(_settings, current):
        return current.__class__(
            **{
                name: getattr(current, name)
                for name in current.__dataclass_fields__
                if name != "durable_claim"
            },
            durable_claim=claim,
        )

    async def preparation(*_args, **_kwargs):
        if terminal_path == "preparation":
            raise RuntimeError("preparation failed")

    def create_runner(**_kwargs):
        if terminal_path == "outer":
            raise asyncio.CancelledError
        raise RuntimeError("generic failure")

    def blocked_terminal(*_args):
        terminal_calls.append(terminal_path)
        started.set()
        assert release.wait(timeout=1)

    class Latency:
        def __init__(self, _db):
            pass

        def finalize(self, *_args):
            pass

    @contextmanager
    def session_local():
        yield SimpleNamespace(commit=lambda: None)

    monkeypatch.setattr(chat_stream_service, "_claim_local_turn", claim_turn)
    monkeypatch.setattr(
        chat_stream_service,
        "_heartbeat_local_turn",
        lambda _settings, current: heartbeats.append(current.durable_claim),
    )
    monkeypatch.setattr(chat_stream_service, "_start_local_turn", lambda *_args: None)
    monkeypatch.setattr(chat_stream_service, "_prepare_replacement", preparation)
    monkeypatch.setattr(chat_stream_service, "create_chat_turn_runner", create_runner)
    monkeypatch.setattr(chat_stream_service, "_persist_failure", blocked_terminal)
    monkeypatch.setattr(
        chat_stream_service, "_persist_preparation_failure", blocked_terminal
    )
    monkeypatch.setattr(
        chat_stream_service, "db_manager", SimpleNamespace(session_local=session_local)
    )
    monkeypatch.setattr(chat_stream_service, "ChatLatencyService", Latency)
    orchestrator = _orchestrator(settings, admission)

    async def exercise():
        stream = asyncio.create_task(_collect_stream_events(orchestrator))
        for _attempt in range(2_000):
            if started.is_set():
                break
            await asyncio.sleep(0.001)
        else:
            pending = []
            for task in asyncio.all_tasks():
                if task.done():
                    continue
                stack = "\n".join(
                    f"{frame.f_code.co_filename}:{frame.f_lineno} "
                    f"in {frame.f_code.co_name}"
                    for frame in task.get_stack()
                )
                pending.append(f"{task.get_name()}:\n{stack}")
            pytest.fail(
                "terminal persistence never started; pending tasks:\n"
                + "\n".join(pending)
            )
        stream.cancel()
        await asyncio.sleep(0.025)
        first_count = len(heartbeats)
        assert first_count >= 1
        stream.cancel()
        await asyncio.sleep(0.025)
        assert len(heartbeats) > first_count
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await stream
        stopped_at = len(heartbeats)
        await asyncio.sleep(0.025)
        assert len(heartbeats) == stopped_at

    asyncio.run(exercise())

    assert terminal_calls == [terminal_path]
    assert orchestrator.lease_heartbeat_task is None
    assert orchestrator.terminal_persistence.completed is True
    assert orchestrator.lifecycle.terminal is not TurnTerminalState.ACTIVE
    assert orchestrator.terminal_label == (
        "interrupted" if terminal_path == "outer" else "error"
    )


async def _collect_stream_events(orchestrator):
    frames = []
    async for frame in orchestrator._events():
        frames.append(frame)
        claim = orchestrator.admission.durable_claim
        if claim is None:
            continue
        if frame.event == "done":
            state = (
                "interrupted"
                if frame.payload.get("finish_reason") == "stopped"
                else "completed"
            )
            await orchestrator.persist_detached_terminal(
                claim,
                state,
                "cancelled" if state == "interrupted" else None,
            )
        elif frame.event == "error":
            await orchestrator.persist_detached_terminal(
                claim, "failed", frame.payload.get("code") or "turn_failed"
            )
    return frames


def test_stale_claim_never_prepares_or_dispatches(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    admission = _admission()
    monkeypatch.setattr(
        chat_stream_service,
        "_claim_local_turn",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("already claimed")),
    )
    monkeypatch.setattr(
        chat_stream_service,
        "_prepare_replacement",
        lambda *_args, **_kwargs: pytest.fail("stale turn was prepared"),
    )
    monkeypatch.setattr(
        chat_stream_service,
        "create_chat_turn_runner",
        lambda **_kwargs: pytest.fail("stale turn was dispatched"),
    )
    orchestrator = _orchestrator(settings, admission)
    orchestrator._close = AsyncMock()

    async def collect():
        return [frame async for frame in orchestrator._events()]

    frames = asyncio.run(collect())

    assert [frame.event for frame in frames] == ["stream_start", "error"]
    assert orchestrator.admission.durable_claim is None


def test_terminal_fence_failure_leaves_legacy_projection_unchanged(monkeypatch):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    admission = _admission(claim=claim)
    session = SimpleNamespace(
        active_turn_id=admission.turn_id,
        active_turn_expires_at=NOW,
        updated_at=NOW,
        projection_bytes=0,
    )
    message = SimpleNamespace(status="generating", error_code=None)

    class DB:
        def get(self, _model, key):
            return message if key == admission.user_message_id else None

    class FailingLease:
        def __init__(self, *_args, **_kwargs):
            pass

        def write_terminal(self, *_args, **_kwargs):
            raise RuntimeError("stale fence")

    monkeypatch.setattr(chat_session_module, "ChatLocalTurnLeaseService", FailingLease)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    service = ChatSessionService(DB(), settings)
    service._owned = lambda *_args, **_kwargs: session

    with pytest.raises(RuntimeError, match="stale fence"):
        service.fail_turn(ChatOwner("owner-1", "owner"), admission, "provider_error")

    assert session.active_turn_id == admission.turn_id
    assert message.status == "generating"
    assert message.error_code is None


def test_disabled_terminal_projection_never_constructs_lease_service(monkeypatch):
    admission = _admission()
    session = SimpleNamespace(
        active_turn_id=admission.turn_id,
        active_turn_expires_at=NOW,
        updated_at=NOW,
        projection_bytes=0,
    )
    message = SimpleNamespace(status="generating", error_code=None)

    class DB:
        def get(self, _model, key):
            return message if key == admission.user_message_id else None

    monkeypatch.setattr(
        chat_session_module,
        "ChatLocalTurnLeaseService",
        lambda *_args, **_kwargs: pytest.fail("durable table queried"),
    )
    service = ChatSessionService(DB(), get_settings())
    service._owned = lambda *_args, **_kwargs: session

    service.fail_turn(ChatOwner("owner-1", "owner"), admission, "provider_error")

    assert session.active_turn_id is None
    assert message.status == "error"


def test_legacy_cancel_fences_projection_before_cross_process_control():
    turn_id = uuid.uuid4()
    session = SimpleNamespace(
        id=uuid.uuid4(),
        active_turn_id=turn_id,
        active_turn_expires_at=NOW,
        updated_at=NOW,
    )
    message = SimpleNamespace(status="generating", error_code=None)

    class DB:
        def scalar(self, _query):
            return message

    service = ChatSessionService(DB(), get_settings())
    service._owned = lambda *_args, **_kwargs: session

    assert (
        service.request_legacy_cancel(ChatOwner("owner-1", "owner"), session.id)
        == turn_id
    )
    assert message.status == "interrupted"
    assert message.error_code == "cancelled"
    assert session.active_turn_id == turn_id
    assert session.active_turn_expires_at == NOW


def test_legacy_stream_observes_cross_process_cancel_fence(monkeypatch):
    admission = _admission()
    orchestrator = _orchestrator(get_settings(), admission)
    cancel_calls = []

    class Runner:
        async def cancel(self):
            cancel_calls.append("cancel")

    orchestrator.runner = Runner()
    monkeypatch.setattr(chat_stream_service, "_legacy_turn_is_active", lambda *_: False)
    monkeypatch.setattr(chat_stream_service, "_persist_failure", lambda *_: None)

    async def exercise():
        orchestrator.research_task = asyncio.create_task(asyncio.sleep(60))
        queue = asyncio.Queue()
        frames = [frame async for frame in orchestrator._consume(queue)]
        orchestrator.research_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await orchestrator.research_task
        return frames

    frames = asyncio.run(exercise())

    assert [frame.event for frame in frames] == ["done"]
    assert frames[0].payload["finish_reason"] == "stopped"
    assert cancel_calls == ["cancel"]
    assert orchestrator.terminal_label == "stopped"


def test_legacy_cancel_poll_outage_does_not_fail_an_active_turn(monkeypatch):
    orchestrator = _orchestrator(get_settings(), _admission())

    def unavailable(*_args):
        raise OSError("database unavailable")

    monkeypatch.setattr(chat_stream_service, "_legacy_turn_is_active", unavailable)

    assert asyncio.run(orchestrator._legacy_cancel_requested(force=True)) is False
    assert orchestrator.legacy_cancel_seen is False


def test_completion_writes_durable_terminal_before_legacy_projection(monkeypatch):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    admission = _admission(claim=claim)
    session = SimpleNamespace(
        id=admission.session_id,
        active_turn_id=admission.turn_id,
        active_turn_expires_at=NOW,
        updated_at=NOW,
        projection_bytes=0,
        last_sequence=1,
        message_count=1,
    )
    message = SimpleNamespace(status="generating")
    terminal_calls = []

    class DB:
        def __init__(self):
            self.added = []

        def get(self, _model, key):
            return message if key == admission.user_message_id else None

        def add(self, value):
            self.added.append(value)

        def flush(self):
            pass

    database = DB()

    class Lease:
        def __init__(self, db, _settings):
            assert db is database

        def write_terminal(self, exact_claim, **terminal):
            assert session.active_turn_id == admission.turn_id
            terminal_calls.append((exact_claim, terminal))

    monkeypatch.setattr(chat_session_module, "ChatLocalTurnLeaseService", Lease)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    service = ChatSessionService(database, settings)
    service._owned = lambda *_args, **_kwargs: session

    service.complete_turn(
        ChatOwner("owner-1", "owner"),
        admission,
        "answer",
        [],
        [],
        [],
        "success",
    )

    assert terminal_calls[0][0] == claim
    assert terminal_calls[0][1]["state"] == "completed"
    assert terminal_calls[0][1]["failure_code"] is None
    assert session.active_turn_id is None
    assert message.status == "complete"


def test_preparation_failure_pairs_sanitized_terminal_on_same_database(monkeypatch):
    claim = TurnLeaseClaim(uuid.uuid4(), "local-runner:abc", 7, 1)
    admission = _admission(claim=claim)
    session = SimpleNamespace(active_turn_id=admission.turn_id)
    database = Mock()
    terminal_calls = []

    class Lease:
        def __init__(self, db, _settings):
            assert db is database

        def write_terminal(self, exact_claim, **terminal):
            terminal_calls.append((exact_claim, terminal))

    monkeypatch.setattr(chat_session_module, "ChatLocalTurnLeaseService", Lease)
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    service = ChatSessionService(database, settings)
    service._owned = lambda *_args, **_kwargs: session
    service.edits = Mock()

    service.abort_prepared_edit(
        ChatOwner("owner-1", "owner"),
        admission,
        "Provider Error! includes unsafe detail",
    )

    assert terminal_calls[0][0] == claim
    assert terminal_calls[0][1]["state"] == "failed"
    assert terminal_calls[0][1]["failure_code"] == "turn_failed"
    service.edits.abort.assert_called_once_with(
        session, admission, "Provider Error! includes unsafe detail"
    )
