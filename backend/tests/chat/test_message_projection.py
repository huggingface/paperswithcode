"""Persisted chat message projection and display bounds."""

from __future__ import annotations

import asyncio
import logging
import uuid

import pytest

from backend.config import get_settings
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
)
from backend.services import chat_stream_service
from backend.services.chat_session_service import (
    ChatOwner,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    ChatStreamOrchestrator,
    ChatTurnProjection,
    sequential_reasoning_events,
)


from backend.services.chat_title_service import fallback_title, normalize_title


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

    from backend.services.chat_turn_event_service import ToolEvent

    now = 10.0
    timing = _ToolTimingFallback(enabled=True, now=lambda: now)
    timing.apply(ToolEvent("tool_call", id="slow"))
    from backend.services.chat_turn_event_service import ToolEvent

    now = 10.025
    timing.apply(ToolEvent("tool_call", id="fast"))
    from backend.services.chat_turn_event_service import ToolEvent

    now = 10.04
    fast = timing.apply(ToolEvent("tool_result", id="fast", took_ms=0))
    assert fast.took_ms == 15

    from backend.services.chat_turn_event_service import ToolEvent

    now = 10.08
    slow = timing.apply(ToolEvent("tool_result", id="slow", took_ms=73))
    assert slow.took_ms == 73


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
