"""Worker adapter stream, telemetry, tool-call, and finalizer contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    MirrorErrorMessage,
    ResultMessage,
    StreamEvent,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from backend.chat_execution_policy import (
    FINALIZER_MAX_TURNS,
)
from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.protocol import (
    WorkerEventValidator,
)
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter as WorkerSDKAdapter


def test_adapter_waits_for_late_mirror_before_terminal():
    async def messages():
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sdk-session",
            total_cost_usd=0,
            usage=None,
            result="done",
            structured_output=None,
        )
        yield MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            error="late mirror failure",
            key={"session_id": "sdk-session", "project_key": "workspace"},
        )

    async def run():
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=agent.WorkerToolHooks(agent.WorkerSettings.from_environment()),
                adapter=agent.SDKEventAdapter(show_reasoning=False),
            )
        ]

    events = asyncio.run(run())
    assert [event["type"] for event in events] == [
        "_sdk_session",
        "_mirror_error",
    ]
    assert events[-1]["error"] == "late mirror failure"


def test_worker_adapter_surfaces_hugging_face_billing_errors():
    adapter = WorkerSDKAdapter(show_reasoning=False)

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
        ("unknown", "provider_error"),
    ],
)
def test_worker_adapter_keeps_provider_failures_distinct(provider_error, code):
    events = WorkerSDKAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error=provider_error)
    )

    assert events[0]["type"] == "error"
    assert events[0]["code"] == code


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [("error", "provider_error"), ("_mirror_error", "mirror_error")],
)
def test_worker_telemetry_classifies_terminal_failure(event_type, outcome):
    assert agent._failure_outcome({"type": event_type}) == outcome


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [("error", "provider_error"), ("_mirror_error", "mirror_error")],
)
def test_worker_stream_reports_terminal_failure_outcome(
    monkeypatch, event_type, outcome
):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    async def messages():
        if False:
            yield None

    async def adapted(_messages, *, request_id, **_kwargs):
        yield {"v": 1, "type": event_type, "request_id": request_id}

    monkeypatch.setattr(agent, "sdk_query", lambda **_kwargs: messages())
    monkeypatch.setattr(agent, "_adapt_messages", adapted)

    async def collect():
        return [
            event
            async for event in agent.stream_turn(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "Research this",
                    "model": "model-a",
                    "fetchable_urls": [],
                },
                agent.WorkerSettings.from_environment(),
            )
        ]

    events = asyncio.run(collect())
    assert events[-2]["type"] == "_execution_telemetry"
    assert events[-2]["finalizer_outcome"] == outcome
    assert events[-1]["type"] == event_type


def test_worker_adapter_deduplicates_late_completed_thinking_snapshot():
    adapter = WorkerSDKAdapter(show_reasoning=True)
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


def test_worker_adapter_closes_reasoning_before_luna_starts_next_message():
    adapter = WorkerSDKAdapter(show_reasoning=True)
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
        StreamEvent(
            uuid="6",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Second"},
            },
        ),
        StreamEvent(
            uuid="7",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
    ]


def test_worker_adapter_assembles_streamed_tool_arguments():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Bash",
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"command":"pwc search on-device"}',
                },
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {
            "type": "tool_call",
            "id": "tool-1",
            "name": "Bash",
            "args": {"command": "pwc search on-device"},
        }
    ]


def test_worker_adapter_namespaces_reused_provider_tool_ids():
    hooks = agent.WorkerToolHooks(agent.WorkerSettings.from_environment())

    def tool_result(tool_id, text):
        return {
            "type": "tool_result",
            "id": tool_id,
            "status": "success",
            "took_ms": 1,
            "content": [{"type": "text", "text": text, "truncated": False}],
            "metadata": {"exit_code": 0, "output_truncated": False},
        }

    async def messages():
        yield AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="Bash:0", name="Bash", input={})],
        )
        hooks.results["Bash:0"] = tool_result("Bash:0", "first")
        yield UserMessage(
            content=[ToolResultBlock(tool_use_id="Bash:0", content="first")]
        )
        yield AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="Bash:0", name="Bash", input={}),
                ToolUseBlock(id="Bash:1", name="Bash", input={}),
            ],
        )
        hooks.results["Bash:0"] = tool_result("Bash:0", "second")
        hooks.results["Bash:1"] = tool_result("Bash:1", "third")
        yield UserMessage(
            content=[
                ToolResultBlock(tool_use_id="Bash:0", content="second"),
                ToolResultBlock(tool_use_id="Bash:1", content="third"),
            ]
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="sdk-session",
            total_cost_usd=0,
            usage=None,
            result="done",
            structured_output=None,
        )

    async def run():
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=hooks,
                adapter=agent.SDKEventAdapter(
                    show_reasoning=False, policy=agent._sdk_event_policy(hooks)
                ),
            )
        ]

    events = asyncio.run(run())
    tool_events = [
        event for event in events if event["type"] in {"tool_call", "tool_result"}
    ]
    assert [(event["type"], event["id"]) for event in tool_events] == [
        ("tool_call", "Bash:0"),
        ("tool_result", "Bash:0"),
        ("tool_call", "Bash:0#2"),
        ("tool_call", "Bash:1"),
        ("tool_result", "Bash:0#2"),
        ("tool_result", "Bash:1"),
    ]
    validator = WorkerEventValidator()
    for event in events:
        if event["type"] != "_sdk_session":
            validator.accept(event)
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_adapter_surfaces_recoverable_execution_limit_internally():
    events = WorkerSDKAdapter(show_reasoning=False).feed(
        ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=9,
            session_id="session-a",
        )
    )
    assert [event["type"] for event in events] == ["usage", "_execution_limit"]


def test_worker_adapter_registers_complete_parallel_batch_before_returning_calls():
    batches = []
    adapter = WorkerSDKAdapter(show_reasoning=False, on_tool_batch=batches.append)
    events = adapter.feed(
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="a", name="Bash", input={"command": "one"}),
                ToolUseBlock(id="b", name="Read", input={"file_path": "/workspace/x"}),
            ],
        )
    )
    assert batches == [["a", "b"]]
    assert [event["id"] for event in events] == ["a", "b"]


def test_worker_finalizer_options_are_tool_free_and_single_turn(monkeypatch):
    monkeypatch.setattr(
        agent, "GUIDE", Path(agent.__file__).with_name("PWC_CLI_SKILL.md")
    )
    settings = agent.WorkerSettings.from_environment()
    hooks = agent.WorkerToolHooks(settings)
    options = agent._options(
        settings,
        hooks,
        model="model-a",
        resume="session-a",
        finalizing=True,
    )
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.mcp_servers == {}
    assert options.max_turns == FINALIZER_MAX_TURNS
    assert {"Bash", "Read", "Grep", "WebFetch", "mcp__web__search_web"} <= set(
        options.disallowed_tools
    )
