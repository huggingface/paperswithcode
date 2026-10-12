"""Contract coverage shared by local and sandbox SDK event projections."""

from __future__ import annotations

import json

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter, SDKEventPolicy
from backend.services.chat_agent_service import _local_tool_event_policy


def _messages():
    return [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Plan"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
        AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="call", name="mcp__web__search_web", input={})],
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="call", content="first")]),
        AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="call", name="Bash", input={"command": "pwd"})],
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="call", content="second")]),
        AssistantMessage(
            model="test",
            content=[
                ThinkingBlock(thinking="late", signature="sig"),
                TextBlock(text="Answer"),
            ],
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="session",
        ),
    ]


@pytest.mark.parametrize(
    "policy",
    [
        SDKEventPolicy(tool_name=lambda name: name.removeprefix("mcp__web__")),
        _local_tool_event_policy(None),
    ],
    ids=["sandbox", "local"],
)
def test_sdk_event_adapter_contract_covers_both_execution_paths(policy):
    batches: list[list[str]] = []
    adapter = SDKEventAdapter(
        show_reasoning=True,
        policy=SDKEventPolicy(
            tool_name=policy.tool_name,
            allow_tool_call=policy.allow_tool_call,
            format_tool_result=policy.format_tool_result,
            format_terminal_result=policy.format_terminal_result,
            on_tool_batch=batches.append,
        ),
    )

    events = [event for message in _messages() for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "answer_delta",
        "usage",
        "done",
    ]
    assert [event["id"] for event in events if event["type"] == "tool_call"] == [
        "call",
        "call#2",
    ]
    assert [event["id"] for event in events if event["type"] == "tool_result"] == [
        "call",
        "call#2",
    ]
    assert events[3]["name"] == "search_web"
    assert batches == [["call"], ["call"]]


def test_sdk_event_adapter_policy_can_suppress_a_tool_and_its_result():
    adapter = SDKEventAdapter(
        show_reasoning=False,
        policy=SDKEventPolicy(allow_tool_call=lambda _id, name, _args: name != "Read"),
    )

    events = [
        event
        for message in [
            AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(id="keep", name="Bash", input={}),
                    ToolUseBlock(id="hide", name="Read", input={}),
                ],
            ),
            UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="keep", content=json.dumps({})),
                    ToolResultBlock(tool_use_id="hide", content=json.dumps({})),
                ]
            ),
        ]
        for event in adapter.feed(message)
    ]

    assert [(event["type"], event["id"]) for event in events] == [
        ("tool_call", "keep"),
        ("tool_result", "keep"),
    ]


def test_suppressed_occurrence_does_not_orphan_a_reused_tool_id():
    calls = 0

    def allow_once(_tool_id, _name, _args):
        nonlocal calls
        calls += 1
        return calls > 1

    adapter = SDKEventAdapter(
        show_reasoning=False,
        policy=SDKEventPolicy(allow_tool_call=allow_once),
    )
    events = [
        event
        for message in [
            AssistantMessage(
                model="test", content=[ToolUseBlock(id="same", name="Read", input={})]
            ),
            AssistantMessage(
                model="test", content=[ToolUseBlock(id="same", name="Read", input={})]
            ),
            UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="same", content="suppressed"),
                    ToolResultBlock(tool_use_id="same", content="allowed"),
                ]
            ),
        ]
        for event in adapter.feed(message)
    ]

    assert [(event["type"], event["id"]) for event in events] == [
        ("tool_call", "same"),
        ("tool_result", "same"),
    ]
    assert events[-1]["content"] == "allowed"


def test_terminal_result_policy_preserves_local_error_and_execution_limit():
    adapter = SDKEventAdapter(
        show_reasoning=False, policy=_local_tool_event_policy(None)
    )
    failed = adapter.feed(
        ResultMessage(
            subtype="error",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=1,
            session_id="session",
        )
    )

    assert failed[-1] == {"type": "error", "message": "The chat request failed."}

    limited = SDKEventAdapter(
        show_reasoning=False, policy=_local_tool_event_policy(None)
    ).feed(
        ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=1,
            session_id="session",
        )
    )
    assert limited[-1] == {"type": "_execution_limit", "reason": "max_turns"}


def test_default_terminal_policy_projects_provider_and_billing_errors():
    adapter = SDKEventAdapter(show_reasoning=False)
    provider = adapter.feed(
        AssistantMessage(model="test", content=[], error="rate_limit")
    )
    assert provider == [
        {
            "type": "error",
            "code": "provider_rate_limit",
            "message": "The selected model is temporarily rate-limited. Try again shortly.",
        }
    ]

    terminal = SDKEventAdapter(show_reasoning=False).feed(
        ResultMessage(
            subtype="error",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=1,
            session_id="session",
        )
    )
    assert terminal[-1]["code"] == "gateway_unavailable"


def test_complete_only_reasoning_and_billing_error_are_projected():
    adapter = SDKEventAdapter(show_reasoning=True)
    reasoning = adapter.feed(
        AssistantMessage(
            model="test", content=[ThinkingBlock(thinking="Plan", signature="sig")]
        )
    )
    assert [event["type"] for event in reasoning] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
    ]

    billing = SDKEventAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error="billing_error")
    )
    assert billing[0]["code"] == "hf_inference_billing_exhausted"
