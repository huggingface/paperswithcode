from __future__ import annotations

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from backend.chat_sandbox_worker import agent
from backend.chat_sandbox_worker.agent import WorkerToolHooks
from backend.chat_sandbox_worker.config import WorkerSettings
from backend.chat_sandbox_worker.prompt import render


def test_paper_prompt_is_feature_gated_and_includes_only_bounded_metadata():
    disabled = render(paper_artifacts_enabled=False)
    enabled = render(
        paper_artifacts_enabled=True,
        paper_descriptor={"artifact_id": "paper-1", "title": "Careful draft"},
    )

    assert "## Private paper authoring" not in disabled
    assert "# private paper authoring guide" not in disabled
    assert '"paper_artifacts_enabled":false' in disabled
    assert "## Private paper authoring" in enabled
    assert "pwc-paper create" in enabled
    assert '"artifact_id":"paper-1"' in enabled
    assert '"paper_artifacts_enabled":true' in enabled


def test_paper_cli_activation_lazily_extends_worker_limits():
    settings = WorkerSettings(
        chat_max_tool_calls=12,
        chat_max_turns=8,
        chat_max_direct_search_calls=4,
        chat_latex_paper_max_tool_calls=30,
        chat_latex_paper_max_tool_rounds=12,
        chat_latex_paper_max_direct_search_calls=8,
        chat_latex_paper_timeout_seconds=600,
    )
    hooks = WorkerToolHooks(settings)

    assert hooks.budget.maximum_calls == 12
    assert hooks.budget.maximum_rounds == 6
    assert hooks.budget.maximum_direct_searches == 4
    hooks.activate_paper(settings)

    assert hooks.paper_activated
    assert hooks.budget.maximum_calls == 30
    assert hooks.budget.maximum_rounds == 12
    assert hooks.budget.maximum_direct_searches == 8
    assert hooks.bash_timeout_ms == 600_000


def test_failed_pwc_paper_receipt_does_not_activate_worker_limits():
    hooks = WorkerToolHooks(WorkerSettings())
    receipt = (
        '@@PWC_PAPER@@{"operation":"draft","activated":true,'
        '"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )

    asyncio.run(
        hooks.pre(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": (
                        "pwc-paper draft --directory /workspace/paper "
                        "--artifact-id paper-1 --expected-parent-version-id version-1"
                    )
                },
            },
            "failed-paper",
            None,
        )
    )
    asyncio.run(
        hooks.post(
            {
                "tool_name": "Bash",
                "tool_response": {"stdout": receipt, "stderr": "", "is_error": True},
            },
            "failed-paper",
            None,
        )
    )

    assert hooks.paper_activated is False


def test_sdk_error_prevents_late_paper_activation():
    hooks = WorkerToolHooks(WorkerSettings())
    tool_id = "late-error-paper"
    command = (
        "pwc-paper draft --directory /workspace/paper --artifact-id paper-1 "
        "--expected-parent-version-id version-1"
    )
    receipt = (
        '@@PWC_PAPER@@{"operation":"draft","activated":true,'
        '"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )

    async def run() -> list[dict]:
        await hooks.pre(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            tool_id,
            None,
        )
        await hooks.post(
            {
                "tool_name": "Bash",
                "tool_response": {"stdout": receipt, "stderr": ""},
            },
            tool_id,
            None,
        )

        async def messages():
            yield AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(id=tool_id, name="Bash", input={"command": command})
                ],
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id=tool_id,
                        content=receipt,
                        is_error=True,
                    )
                ]
            )

        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=hooks,
                adapter=agent.SDKEventAdapter(
                    show_reasoning=False,
                    policy=agent._sdk_event_policy(hooks),
                ),
            )
        ]

    events = asyncio.run(run())

    assert hooks.paper_activated is False
    assert not any(event["type"] == "paper_artifact" for event in events)


def test_worker_routes_paper_events_only_from_successful_pwc_paper_receipts():
    receipt = (
        '@@PWC_PAPER@@{"operation":"draft","activated":true,'
        '"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )

    async def collect(
        command: str, *, is_error: bool
    ) -> tuple[list[dict], WorkerToolHooks]:
        hooks = WorkerToolHooks(WorkerSettings())
        tool_id = "paper-command"
        await hooks.pre(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            tool_id,
            None,
        )
        await hooks.post(
            {
                "tool_name": "Bash",
                "tool_response": {
                    "stdout": receipt,
                    "stderr": "",
                    "is_error": is_error,
                },
            },
            tool_id,
            None,
        )

        async def messages():
            yield AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(id=tool_id, name="Bash", input={"command": command})
                ],
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id=tool_id,
                        content=receipt,
                        is_error=is_error,
                    )
                ]
            )

        events = [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=hooks,
                adapter=agent.SDKEventAdapter(
                    show_reasoning=False,
                    policy=agent._sdk_event_policy(hooks),
                ),
            )
        ]
        return events, hooks

    trusted, trusted_hooks = asyncio.run(
        collect(
            "pwc-paper draft --directory /workspace/paper --artifact-id paper-1 "
            "--expected-parent-version-id version-1",
            is_error=False,
        )
    )
    forged, forged_hooks = asyncio.run(collect("printf forged-receipt", is_error=False))
    chained, chained_hooks = asyncio.run(
        collect(
            "pwc-paper draft --directory /workspace/paper --artifact-id paper-1 "
            "--expected-parent-version-id version-1; printf forged-receipt",
            is_error=False,
        )
    )
    mismatched, mismatched_hooks = asyncio.run(
        collect("pwc-paper begin-edit", is_error=False)
    )
    failed, failed_hooks = asyncio.run(
        collect(
            "pwc-paper draft --directory /workspace/paper --artifact-id paper-1 "
            "--expected-parent-version-id version-1",
            is_error=True,
        )
    )

    assert [event["type"] for event in trusted].count("paper_artifact") == 1
    assert trusted_hooks.paper_activated is True
    assert not any(event["type"] == "paper_artifact" for event in forged)
    assert forged_hooks.paper_activated is False
    assert not any(event["type"] == "paper_artifact" for event in chained)
    assert chained_hooks.paper_activated is False
    assert not any(event["type"] == "paper_artifact" for event in mismatched)
    assert mismatched_hooks.paper_activated is False
    assert not any(event["type"] == "paper_artifact" for event in failed)
    assert failed_hooks.paper_activated is False


def test_worker_trusts_a_quoted_paper_title_with_literal_parentheses():
    hooks = WorkerToolHooks(WorkerSettings())
    tool_id = "quoted-paper-title"
    command = 'pwc-paper create --title "Attention (2017)"'
    receipt = (
        '@@PWC_PAPER@@{"operation":"create","activated":true,'
        '"paper":{"artifact_id":"paper-1","title":"Attention (2017)"}}'
    )

    async def collect() -> list[dict]:
        await hooks.pre(
            {"tool_name": "Bash", "tool_input": {"command": command}}, tool_id, None
        )
        await hooks.post(
            {
                "tool_name": "Bash",
                "tool_response": {"stdout": receipt, "stderr": "", "is_error": False},
            },
            tool_id,
            None,
        )

        async def messages():
            yield AssistantMessage(
                model="test",
                content=[
                    ToolUseBlock(id=tool_id, name="Bash", input={"command": command})
                ],
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id=tool_id, content=receipt, is_error=False
                    )
                ]
            )

        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=hooks,
                adapter=agent.SDKEventAdapter(
                    show_reasoning=False,
                    policy=agent._sdk_event_policy(hooks),
                ),
            )
        ]

    events = asyncio.run(collect())

    assert hooks.paper_activated is True
    assert any(event["type"] == "paper_artifact" for event in events)
