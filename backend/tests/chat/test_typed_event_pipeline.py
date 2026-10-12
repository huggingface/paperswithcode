"""Typed ingress, enrichment, and terminal parity without legacy reparsing."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest

from backend.config import get_settings
from backend.services import chat_stream_service as streams
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_turn_event_service import (
    UNSET,
    ChatTurnLifecycle,
    CompletionEvent,
    LatencyEvent,
    LegacyPassthroughEvent,
    McpReadinessEvent,
    PersistenceEvent,
    ResearchFinishedEvent,
    TerminalOutcome,
    ToolEvent,
    from_legacy_event,
    update_event,
)
from backend.services.chat_turn_job_repository import TurnLeaseClaim


def orchestrator():
    claim = TurnLeaseClaim(uuid.uuid4(), "worker", 1, 1)
    return streams.ChatStreamOrchestrator(
        settings=get_settings().model_copy(
            update={"chat_durable_turn_dispatch_enabled": True}
        ),
        owner=ChatOwner("owner", "owner"),
        admission=TurnAdmission(
            session_id=uuid.uuid4(),
            turn_id=claim.turn_id,
            user_message_id=uuid.uuid4(),
            selected_model="model",
            model_route="route",
            sdk_session_id=None,
            sdk_project_key=None,
            agent_harness="pi",
            durable_claim=claim,
        ),
        prompt="hello",
        request_id="request",
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )


@pytest.mark.parametrize("typed", [False, True])
def test_ingress_normalizes_raw_once_and_never_reparses_typed_events(
    monkeypatch, typed
):
    raw = [
        {"type": "_sdk_session", "session_id": str(uuid.uuid4()), "extension": None},
        {"type": "_latency", "phase": "agent_session_ready", "elapsed_ms": 7},
        {"type": "_mcp_readiness", "ready": True, "enabled_provider_ids": []},
        {"type": "tool_call", "id": "tool", "name": "Read", "args": {}, "future": None},
        {
            "type": "tool_result",
            "id": "tool",
            "status": "success",
            "content": [],
            "took_ms": None,
        },
        {"type": "usage", "usage": {"input_tokens": 2}, "extension": [None]},
        {"first": None, "type": "future_event", "last": {"empty": []}},
        {"type": "answer_delta", "text": "hello"},
        {
            "extension": None,
            "type": "done",
            "followups": [],
            "finish_reason": "success",
        },
        {"type": "_research_finished"},
    ]
    events = [from_legacy_event(item) for item in raw] if typed else raw
    normalize = Mock(wraps=from_legacy_event)
    monkeypatch.setattr(streams, "from_legacy_event", normalize)
    stream = orchestrator()
    clock = iter([10.0, 10.025])
    stream.tool_timing = streams._ToolTimingFallback(
        enabled=True, now=lambda: next(clock)
    )
    bound = []
    monkeypatch.setattr(stream, "_bind_sdk_session", bound.append)
    saved = []
    monkeypatch.setattr(stream, "_complete_turn", saved.append)
    trace = []
    monkeypatch.setattr(
        stream.trace,
        "record_event",
        lambda kind, payload: trace.append((kind, payload)),
    )

    async def run():
        queue = asyncio.Queue()
        for event in events:
            await queue.put(event)
        frames = [frame async for frame in stream._consume(queue)]
        assert saved == [], "projection must wait for the detached journal callback"
        await stream.persist_detached_terminal(
            stream.admission.durable_claim, "completed", None
        )
        return frames

    frames = asyncio.run(run())
    assert normalize.call_count == (0 if typed else len(raw))
    assert isinstance(bound[0], PersistenceEvent)
    assert isinstance(saved[0], CompletionEvent)
    assert saved[0].to_legacy() == {
        "type": "done",
        "extension": None,
        "followups": [],
        "finish_reason": "success",
        "citations": [],
    }
    assert [frame.event for frame in frames] == [
        "tool_call",
        "tool_result",
        "future_event",
        "answer_delta",
        "done",
    ]
    assert frames[1].payload["took_ms"] == 25
    assert json.dumps(frames[2].payload) == '{"first": null, "last": {"empty": []}}'
    assert frames[0].payload["future"] is None
    assert trace[4][1]["took_ms"] == 25
    assert "citations" not in trace[-2][1], (
        "raw trace precedes public completion enrichment"
    )


@pytest.mark.parametrize(
    "event",
    [
        CompletionEvent(raw_finish_reason="stopped"),
        CompletionEvent(TerminalOutcome.STOPPED, finish_reason_present=False),
        CompletionEvent(TerminalOutcome.STOPPED, raw_finish_reason=None),
        CompletionEvent(TerminalOutcome.SUCCESS, raw_finish_reason="future"),
        CompletionEvent(TerminalOutcome.SUCCESS, raw_finish_reason="tool_limit"),
    ],
)
def test_typed_completion_effective_outcome_matches_raw_wire(event):
    assert ChatTurnLifecycle().transition(event) == ChatTurnLifecycle().transition(
        from_legacy_event(event.to_legacy())
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"extra": None, "type": "tool_result", "id": "x"},
        {"extra": [None], "took_ms": None, "type": "tool_result", "id": "x"},
        {"type": "tool_result", "id": "x", "took_ms": 0, "last": {}},
        {"type": "tool_result", "id": "x", "took_ms": 5, "last": {}},
    ],
)
def test_timing_enrichment_preserves_wire_order_and_unknown_extras(raw):
    now = iter([1.0, 1.01])
    timing = streams._ToolTimingFallback(enabled=True, now=lambda: next(now))
    timing.apply(ToolEvent("tool_call", id="x"))
    event = from_legacy_event(raw)
    result = timing.apply(event)
    expected = dict(raw)
    if not raw.get("took_ms"):
        expected["took_ms"] = 10
    assert json.dumps(result.to_legacy()) == json.dumps(expected)
    assert event.to_legacy() == raw


def test_explicit_legacy_tool_passthrough_retains_timing_without_serializing(
    monkeypatch,
):
    monkeypatch.setattr(
        LegacyPassthroughEvent,
        "to_legacy",
        lambda _: pytest.fail("serialized passthrough"),
    )
    now = iter([1.0, 1.012])
    timing = streams._ToolTimingFallback(enabled=True, now=lambda: next(now))
    timing.apply(LegacyPassthroughEvent("tool_call", extras=(("id", "x"),)))
    result = timing.apply(
        LegacyPassthroughEvent(
            "tool_result",
            extras=(("extra", None), ("id", "x")),
            field_order=("type", "extra", "id"),
        )
    )
    assert result.to_legacy() == {
        "type": "tool_result",
        "extra": None,
        "id": "x",
        "took_ms": 12,
    }


def test_enrichment_appends_wire_keys_not_completion_control_fields():
    event = from_legacy_event({"before": None, "type": "done"})
    result = update_event(
        event, outcome=TerminalOutcome.STOPPED, finish_reason_present=True
    )
    assert list(result.to_legacy()) == ["before", "type", "finish_reason"]
    assert result.to_legacy()["finish_reason"] == "stopped"
    failure = update_event(
        from_legacy_event({"message": None, "type": "error", "extra": []}),
        code="failed",
    )
    assert list(failure.to_legacy()) == ["message", "type", "extra", "code"]
    assert failure.message is None
    assert from_legacy_event({"type": "error"}).message is UNSET


@pytest.mark.parametrize(
    "event",
    [
        LatencyEvent(phase="agent_session_ready", elapsed_ms=3),
        McpReadinessEvent(
            ready=True, enabled_provider_ids=["read"], registered_tool_names=[]
        ),
        PersistenceEvent(session_id=str(uuid.uuid4())),
    ],
)
def test_internal_handlers_read_typed_fields_without_legacy_serialization(
    monkeypatch, event
):
    monkeypatch.setattr(
        type(event), "to_legacy", lambda _: pytest.fail("serialized internal event")
    )
    stream = orchestrator()
    monkeypatch.setattr(stream, "_bind_sdk_session", lambda value: None)

    async def run():
        handled = await stream._dispatch_event(event)
        await stream._await_sdk_session_persistence()
        return handled

    assert asyncio.run(run()).frame is None


@pytest.mark.parametrize("internal", [False, True])
def test_typed_checkpoint_callback_is_carried_until_frame_persistence(
    monkeypatch, internal
):
    @dataclass(frozen=True)
    class CheckpointedLatency(LatencyEvent):
        after_persist: object = None

    @dataclass(frozen=True)
    class CheckpointedTool(ToolEvent):
        after_persist: object = None

    receipt = AsyncMock()
    event = (
        CheckpointedLatency(
            phase="agent_session_ready", elapsed_ms=3, after_persist=receipt
        )
        if internal
        else CheckpointedTool(
            "tool_call",
            id="x",
            extras=(("name", "Read"), ("args", ("dict", ()))),
            after_persist=receipt,
        )
    )
    stream = orchestrator()

    async def run():
        queue = asyncio.Queue()
        await queue.put(event)
        iterator = stream._consume(queue)
        frame = await anext(iterator)
        receipt.assert_not_awaited()
        assert frame.after_persist is receipt
        assert "after_persist" not in frame.payload
        await iterator.aclose()
        await frame.after_persist()
        receipt.assert_awaited_once()
        return frame

    frame = asyncio.run(run())
    assert frame.event == (None if internal else "tool_call")


@pytest.mark.parametrize("typed", [False, True])
def test_failure_enrichment_keeps_typed_terminal_without_reparsing(monkeypatch, typed):
    from contextlib import contextmanager
    from backend.services.chat_turn_event_service import TurnTerminalState

    stream = orchestrator()
    raw = {
        "extension": None,
        "message": None,
        "type": "error",
        "code": "provider_error",
    }
    event = from_legacy_event(raw) if typed else raw
    normalize = Mock(wraps=from_legacy_event)
    monkeypatch.setattr(streams, "from_legacy_event", normalize)

    @contextmanager
    def session():
        yield object()

    monkeypatch.setattr(streams.db_manager, "_session_local", session)
    monkeypatch.setattr(
        streams.ChatCapabilityService,
        "provider_error_for_turn",
        lambda *_: "openrouter_unavailable",
    )

    async def run():
        queue = asyncio.Queue()
        await queue.put(event)
        await queue.put(ResearchFinishedEvent())
        return [frame async for frame in stream._consume(queue)]

    frames = asyncio.run(run())
    assert normalize.call_count == (0 if typed else 1)
    assert stream.lifecycle.terminal is TurnTerminalState.FAILED
    assert stream.lifecycle.failure_code == "openrouter_unavailable"
    assert list(frames[0].payload) == ["extension", "message", "code"]
    assert frames[0].payload["extension"] is None
    assert "bring your own key" in frames[0].payload["message"]


@pytest.mark.parametrize("typed", [False, True])
def test_cancellation_dispatch_does_not_require_legacy_reparse(monkeypatch, typed):
    from backend.services.chat_turn_event_service import CancellationEvent

    stream = orchestrator()
    event = CancellationEvent() if typed else {"type": "_cancelled"}
    normalize = Mock(wraps=from_legacy_event)
    monkeypatch.setattr(streams, "from_legacy_event", normalize)
    finalize = AsyncMock(
        return_value=streams.ChatStreamFrame("done", {"finish_reason": "stopped"})
    )
    monkeypatch.setattr(stream, "_finalize_cancellation", finalize)

    async def run():
        queue = asyncio.Queue()
        await queue.put(event)
        await queue.put(ResearchFinishedEvent())
        return [frame async for frame in stream._consume(queue)]

    frames = asyncio.run(run())
    assert normalize.call_count == (0 if typed else 1)
    finalize.assert_awaited_once_with(cancel_runner=False)
    assert frames[0].payload == {"finish_reason": "stopped"}
