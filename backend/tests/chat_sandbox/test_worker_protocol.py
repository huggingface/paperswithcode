"""Worker protocol framing, terminals, poster publication, and stdin contracts."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.protocol import (
    MAX_RUN_PROMPT_BYTES,
    ProtocolError,
    WorkerEventValidator,
    artifact_events_from_output,
    decode_frame,
    encode_frame,
)
from backend.models.chat import sse_event
from backend.services.chat_sandbox_worker_transport import WorkerTurnExecution
from backend.services.chat_session_service import detect_poster_intent


def test_worker_protocol_accepts_complete_turn_after_one_terminal():
    frame = {"v": 1, "type": "run_turn", "request_id": "r"}
    assert decode_frame(encode_frame(frame)) == frame
    validator = WorkerEventValidator()
    validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_correlates_parallel_argument_streams_and_final_args():
    validator = WorkerEventValidator()
    validator.accept(
        {"type": "tool_call_start", "id": "a", "name": "Bash", "content_index": 0}
    )
    validator.accept(
        {"type": "tool_call_start", "id": "b", "name": "Read", "content_index": 1}
    )
    validator.accept(
        {
            "type": "tool_call_arguments_delta",
            "id": "b",
            "name": "Read",
            "delta": '{"file_path":"src',
            "partial_args": {"file_path": "src"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_delta",
            "id": "a",
            "name": "Bash",
            "delta": '{"command":"pwc',
            "partial_args": {"command": "pwc"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_done",
            "id": "a",
            "name": "Bash",
            "args": {"command": "pwc version"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_done",
            "id": "b",
            "name": "Read",
            "args": {"file_path": "src/file.py"},
        }
    )
    validator.accept({"type": "tool_result", "id": "b"})
    validator.accept({"type": "tool_result", "id": "a"})

    with pytest.raises(ProtocolError, match="post-terminal"):
        validator.accept(
            {
                "type": "tool_call_arguments_delta",
                "id": "a",
                "name": "Bash",
                "delta": "duplicate",
                "partial_args": {},
            }
        )


def test_worker_transport_replaces_provider_tool_ids_before_public_projection():
    execution = object.__new__(WorkerTurnExecution)
    execution._public_tool_ids = {}
    execution._next_public_tool_id = 1
    provider_id = "call_" + ("provider-metadata" * 8)

    start = execution._public_event(
        {
            "v": 1,
            "request_id": "request-1",
            "type": "app_start",
            "id": provider_id,
            "instance_id": provider_id,
            "provider": "excalidraw",
            "server": "excalidraw",
            "tool": "create_view",
            "resource_uri": "ui://excalidraw/mcp-app.html",
            "input": {"elements": "[]"},
        }
    )
    result = execution._public_event(
        {"type": "app_result", "id": provider_id, "status": "ready"}
    )

    assert start["id"] == "tool-1"
    assert start["instance_id"] == "tool-1"
    assert result["id"] == "tool-1"
    assert provider_id not in json.dumps(start)
    assert provider_id not in json.dumps(result)
    assert b'"instance_id":"tool-1"' in sse_event(
        start["type"], **{key: value for key, value in start.items() if key != "type"}
    )

    first_provider_id = "call_first-provider-id"
    second_provider_id = "call_second-provider-id"
    streamed = [
        execution._public_event(
            {
                "type": "tool_call_start",
                "id": first_provider_id,
                "name": "Bash",
                "content_index": 0,
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_start",
                "id": second_provider_id,
                "name": "Read",
                "content_index": 1,
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_arguments_delta",
                "id": second_provider_id,
                "name": "Read",
                "delta": '{"file_path":"/work',
                "partial_args": {"file_path": "/work"},
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_arguments_done",
                "id": first_provider_id,
                "name": "Bash",
                "args": {"command": "pwc version"},
            }
        ),
        execution._public_event(
            {"type": "tool_result", "id": second_provider_id, "status": "success"}
        ),
    ]
    assert [event["id"] for event in streamed] == [
        "tool-2",
        "tool-3",
        "tool-3",
        "tool-2",
        "tool-3",
    ]
    assert first_provider_id not in json.dumps(streamed)
    assert second_provider_id not in json.dumps(streamed)


def test_worker_accepts_bounded_inline_paper_prompt_by_utf8_bytes():
    prompt = "é" * (MAX_RUN_PROMPT_BYTES // 2)
    frame = {
        "v": 1,
        "type": "run_turn",
        "request_id": "request-1",
        "prompt": prompt,
        "model": "model-a",
    }

    assert agent._validate_run_frame(frame) == (
        prompt,
        "request-1",
        "model-a",
        False,
        False,
        False,
        "high",
        [],
        "unknown",
    )
    assert decode_frame(encode_frame(frame))["prompt"] == prompt

    frame["prompt"] += "é"
    with pytest.raises(ValueError, match="Invalid prompt"):
        agent._validate_run_frame(frame)


def test_persistent_worker_stdin_accepts_inline_paper_frame():
    frame = encode_frame(
        {
            "v": 1,
            "type": "run_turn",
            "request_id": "request-1",
            "prompt": "x" * (80 * 1024),
            "model": "model-a",
        }
    )

    async def read_frame():
        reader = agent._persistent_stdin_reader()
        reader.feed_data(frame)
        reader.feed_eof()
        return await reader.readline()

    assert asyncio.run(read_frame()) == frame


def test_worker_protocol_rejects_invalid_result_and_terminal_sequences():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="Uncorrelated"):
        validator.accept({"type": "tool_result", "id": "missing"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "answer_delta", "text": "late"})
    with pytest.raises(ProtocolError, match="Duplicate terminal"):
        validator.accept({"type": "error"})


def test_worker_protocol_correlates_one_poster_publication():
    ready = {
        "publication_id": "poster-1",
        "artifact_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
        "identifier": "attention-poster",
        "version": 1,
        "kind": "posterly",
        "title": "Attention Is All You Need",
        "preview_mime": "image/png",
        "source_language": "html",
        "gate_status": "warnings",
        "total_bytes": 1024,
    }
    events = artifact_events_from_output(
        "diagnostic\n@@PWC_ARTIFACT@@" + json.dumps(ready)
    )
    assert [event["type"] for event in events] == [
        "artifact_start",
        "artifact_ready",
    ]

    validator = WorkerEventValidator()
    for event in events:
        validator.accept(event)
    with pytest.raises(ProtocolError, match="duplicate artifact terminal"):
        validator.accept(events[-1])
    validator.accept({"type": "done"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_rejects_unfinished_or_inconsistent_poster():
    validator = WorkerEventValidator()
    validator.accept(
        {
            "type": "artifact_start",
            "publication_id": "poster-1",
            "identifier": "paper-poster",
            "kind": "posterly",
            "title": "Paper poster",
        }
    )
    with pytest.raises(ProtocolError, match="unfinished artifact"):
        validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="Inconsistent artifact terminal"):
        validator.accept(
            {
                "type": "artifact_ready",
                "publication_id": "poster-1",
                "artifact_id": str(uuid.uuid4()),
                "version_id": str(uuid.uuid4()),
                "identifier": "different-poster",
                "version": 1,
                "kind": "posterly",
                "title": "Paper poster",
                "preview_mime": "image/png",
                "source_language": "html",
                "gate_status": "passed",
                "total_bytes": 1024,
            }
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Make a poster for this paper", True),
        ("Use Posterly for @Attention Is All You Need", True),
        ("Summarize the poster section", True),
        ("Summarize this paper", False),
        ("What are the posterior probabilities?", False),
    ],
)
def test_poster_intent_is_explicit_and_word_bounded(text: str, expected: bool):
    assert detect_poster_intent(text) is expected


def test_worker_protocol_requires_terminal_before_successful_completion():
    validator = WorkerEventValidator()

    with pytest.raises(ProtocolError, match="without a semantic terminal"):
        validator.accept({"type": "worker_done", "status": "complete"})
    with pytest.raises(ProtocolError, match="Invalid worker completion status"):
        validator.accept({"type": "worker_done", "status": "unknown"})


def test_worker_protocol_treats_transcript_mirror_failure_as_terminal():
    validator = WorkerEventValidator()
    validator.accept({"type": "_mirror_error"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_accepts_content_free_mcp_readiness():
    validator = WorkerEventValidator()
    validator.accept(
        {
            "type": "_mcp_readiness",
            "ready": False,
            "failure_class": "configured_not_connected",
            "enabled_provider_ids": ["excalidraw"],
            "registered_tool_names": ["bash", "read", "search_web"],
            "registration_latency_ms": 12,
            "egress_policy_digest": "a" * 64,
        }
    )
    validator.accept({"type": "done"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_allows_terminal_less_correlated_cancellation():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="without a correlated cancellation"):
        validator.accept({"type": "worker_done", "status": "stopped"})

    validator.accept(
        {"type": "worker_done", "status": "stopped"},
        allow_terminal_less_stop=True,
    )

    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "worker_done", "status": "stopped"})
    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "done"})
