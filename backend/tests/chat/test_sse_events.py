"""SSE event shapes, app frames, and public tool-event projection."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.config import Settings, get_settings
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
    sse_event,
)
from backend.services import chat_stream_service
from backend.services.chat_session_service import (
    ChatOwner,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    ChatStreamOrchestrator,
    ChatTurnProjection,
    _private_paper_tool_event,
    _public_poster_tool_event,
)


from backend.services.chat_tracing_service import ChatTurnTrace


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


REALISTIC_APP_INSTANCE_ID = (
    "call_jmDrQQmYrX7oYoXE7Z4FP0a9"
    "|fc_06f68c86132359c9016aaa4b63625c87d1b92a328f8e54ae09"
)


def test_sse_event_accepts_openai_call_ids_as_app_instance_ids():
    # The Pi worker reuses the provider tool call ID as the App instance ID.
    # OpenAI Responses IDs are ``call_<id>|fc_<id>`` and exceed 64 characters.
    assert len(REALISTIC_APP_INSTANCE_ID) > 64
    frame = sse_event(
        "app_start",
        id=REALISTIC_APP_INSTANCE_ID,
        instance_id=REALISTIC_APP_INSTANCE_ID,
        provider="excalidraw",
        server="excalidraw",
        tool="create_view",
        resource_uri="ui://excalidraw/mcp-app.html",
        input={"elements": "[]"},
    )
    assert json.loads(frame[6:-2])["instance_id"] == REALISTIC_APP_INSTANCE_ID


def test_app_blocks_with_openai_call_ids_persist():
    projection = ChatTurnProjection()
    projection.apply(
        "app_start",
        {
            "id": REALISTIC_APP_INSTANCE_ID,
            "instance_id": REALISTIC_APP_INSTANCE_ID,
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
            "id": REALISTIC_APP_INSTANCE_ID,
            "status": "ready",
            "took_ms": 12,
            "result": {"content": [], "structuredContent": {}, "isError": False},
        },
    )

    blocks = DISPLAY_BLOCKS_ADAPTER.validate_python(projection.completed_blocks())

    assert [block.kind for block in blocks] == ["app"]
    assert blocks[0].instance_id == REALISTIC_APP_INSTANCE_ID


def test_app_instance_id_stays_bounded():
    with pytest.raises(ValidationError):
        DISPLAY_BLOCKS_ADAPTER.validate_python(
            [
                {
                    "kind": "app",
                    "instance_id": "x" * 201,
                    "provider": "excalidraw",
                    "server": "excalidraw",
                    "tool": "create_view",
                    "resource_uri": "ui://excalidraw/mcp-app.html",
                    "status": "ready",
                    "input": {"elements": "[]"},
                }
            ]
        )


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

    from backend.services.chat_turn_event_service import (
        CompletionEvent,
        TerminalOutcome,
    )

    orchestrator._complete_turn(CompletionEvent(TerminalOutcome.SUCCESS, followups=[]))

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
