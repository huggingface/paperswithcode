"""Compatibility tests for typed chat-turn events and lifecycle states."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from backend.services.chat_turn_event_service import (
    CancellationEvent,
    ChatTurnLifecycle,
    CompletionEvent,
    InterruptionReason,
    MirrorFailureEvent,
    PersistedTurnStatus,
    ResearchFinishedEvent,
    TerminalOutcome,
    TitleFinishedEvent,
    TurnFinalizationState,
    TurnTerminalState,
    from_legacy_event,
)


@pytest.mark.parametrize(
    "legacy",
    [
        {"type": "_research_finished"},
        {"type": "session_title_done", "title": "A title"},
        {"type": "_title_finished"},
        {"type": "_sdk_session", "session_id": "sdk-session"},
        {"type": "_mirror_error", "key": {"session_id": "sdk-session"}},
        {"type": "_execution_telemetry", "execution_limit_reached": False},
        {"type": "_latency", "phase": "runner_acquired", "elapsed_ms": 12},
        {"type": "_mcp_readiness", "ready": True, "registered_tool_names": []},
        {"type": "usage", "usage": {"input_tokens": 2}, "model_usage": {}},
        {"type": "usage", "usage": None, "extra": {"values": []}},
        {
            "type": "artifact_start",
            "publication_id": "poster-1",
            "identifier": "poster",
            "title": "Poster",
        },
        {
            "type": "artifact_error",
            "publication_id": "poster-1",
            "code": "failed",
            "message": "Nope",
        },
        {"type": "done"},
        {"type": "done", "finish_reason": "future_outcome"},
        {"type": "done", "followups": [], "finish_reason": "success"},
        {"type": "error", "code": "provider_error", "message": "Unavailable"},
    ],
)
def test_legacy_conversion_is_lossless_for_optional_fields(legacy):
    converted = from_legacy_event(legacy).to_legacy()
    assert converted == legacy
    assert json.dumps(converted, separators=(",", ":")) == json.dumps(
        legacy, separators=(",", ":")
    )


def test_typed_events_are_frozen_and_extras_cannot_replace_type():
    event = from_legacy_event({"type": "usage", "usage": {"input_tokens": 2}})
    with pytest.raises(FrozenInstanceError):
        event.usage = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.usage["input_tokens"] = 3  # type: ignore[index]
    assert event.to_legacy()["type"] == "usage"


def test_completion_freezes_input_collections_and_thaws_fresh_output():
    followups = ["Next"]
    citations = [{"title": "Original", "authors": ["Ada"]}]
    event = CompletionEvent(
        TerminalOutcome.SUCCESS, followups=followups, citations=citations
    )

    followups.append("Changed")
    citations[0]["authors"].append("Grace")
    with pytest.raises(TypeError):
        event.followups[0] = "Changed"  # type: ignore[index]

    first = event.to_legacy()
    first["citations"][0]["authors"].append("Mutated output")
    second = event.to_legacy()

    assert second["followups"] == ["Next"]
    assert second["citations"] == [{"title": "Original", "authors": ["Ada"]}]


def test_legacy_conversion_preserves_serialized_key_order():
    legacy = {
        "extra_before": {"safe": True},
        "followups": ["Next"],
        "type": "done",
        "extra_after": [1, 2],
        "finish_reason": "success",
        "citations": [{"title": "Paper"}],
    }

    expected = json.dumps(legacy, ensure_ascii=False, separators=(",", ":"))
    actual = json.dumps(
        from_legacy_event(legacy).to_legacy(), ensure_ascii=False, separators=(",", ":")
    )

    assert actual == expected


def test_real_stream_order_allows_done_before_research_producer_finishes():
    lifecycle = ChatTurnLifecycle().transition(CompletionEvent(TerminalOutcome.SUCCESS))
    assert lifecycle.finalization is TurnFinalizationState.AWAITING_PRODUCERS

    lifecycle = lifecycle.transition(ResearchFinishedEvent())
    assert lifecycle.terminal is TurnTerminalState.COMPLETED
    assert lifecycle.finalization is TurnFinalizationState.FINALIZED


def test_lifecycle_allows_title_and_research_to_finish_in_either_order():
    lifecycle = ChatTurnLifecycle(title_requested=True)
    lifecycle = lifecycle.transition(TitleFinishedEvent())
    lifecycle = lifecycle.transition(ResearchFinishedEvent())
    lifecycle = lifecycle.transition(CompletionEvent(TerminalOutcome.TOOL_LIMIT))
    assert lifecycle.finalization is TurnFinalizationState.FINALIZED
    assert lifecycle.persistence_outcome().finish_reason is TerminalOutcome.TOOL_LIMIT


def test_mirror_failure_after_a_result_is_completed_with_degraded_transcript():
    lifecycle = ChatTurnLifecycle().transition(
        MirrorFailureEvent(
            result_available=True,
            terminal={"type": "done", "finish_reason": "success"},
        )
    )

    persisted = lifecycle.persistence_outcome()
    assert lifecycle.terminal is TurnTerminalState.COMPLETED_DEGRADED
    assert persisted.status is PersistedTurnStatus.COMPLETE
    assert persisted.transcript_degraded is True


def test_mirror_failure_without_a_result_is_an_error():
    persisted = (
        ChatTurnLifecycle().transition(MirrorFailureEvent()).persistence_outcome()
    )
    assert persisted.status is PersistedTurnStatus.ERROR
    assert persisted.error_code == "transcript_mirror_error"


def test_cancellation_event_is_reserved_for_worker_cancellation():
    with pytest.raises(ValueError, match="worker cancellation"):
        CancellationEvent(InterruptionReason.CLIENT_DISCONNECT)
