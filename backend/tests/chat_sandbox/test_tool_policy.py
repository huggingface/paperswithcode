"""Tool round budgets, shell handling, and tool output policy."""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from backend.chat_execution_policy import (
    effective_tool_rounds,
)
from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, sse_event


@pytest.mark.parametrize("name", ["Bash", "Read", "Grep", "WebFetch", "pwc"])
def test_generic_tool_projection_and_event_are_v2_raw_text(name):
    block = DISPLAY_BLOCKS_ADAPTER.validate_python(
        [
            {
                "kind": "tool",
                "schema_version": 2,
                "id": "tool-1",
                "name": name,
                "args": {"command": "pwc search vision"},
                "status": "success",
                "took_ms": 25,
                "content": [
                    {"type": "text", "text": "id\ttitle\n1\tPaper", "truncated": False}
                ],
                "metadata": {"exit_code": 0, "output_truncated": False},
            }
        ]
    )[0]
    assert block.name == name
    assert b'"status":"success"' in sse_event(
        "tool_result",
        id="tool-1",
        status="success",
        took_ms=25,
        content=[{"type": "text", "text": "ok", "truncated": False}],
        metadata={"exit_code": 0, "output_truncated": False},
    )


def test_tool_budget_counts_parallel_calls_and_fifth_search_is_denied():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    for index in range(4):
        assert budget.authorize(
            f"tool-{index}", "Bash", {"command": f"pwc search query-{index}"}
        ).allowed
    denied = budget.authorize("tool-5", "Bash", {"command": "pwc search fifth"})
    assert not denied.allowed
    assert budget.calls == 4


def test_tool_budget_counts_s2_search_against_catalog_search_limit():
    budget = ToolBudget(
        maximum_calls=2,
        maximum_direct_searches=1,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize(
        "tool-1", "Bash", {"command": "s2 search transformers"}
    ).allowed
    assert not budget.authorize(
        "tool-2", "Bash", {"command": "pwc search transformers"}
    ).allowed


def test_worker_bash_hook_enables_fail_fast_pipeline_handling():
    hooks = agent.WorkerToolHooks(agent.WorkerSettings.from_environment())

    result = asyncio.run(
        hooks.pre(
            {"tool_name": "Bash", "tool_input": {"command": "pwc search test"}},
            "tool-1",
            None,
        )
    )

    updated = result["hookSpecificOutput"]["updatedInput"]
    assert updated["command"] == "set -eo pipefail\npwc search test"


def test_successful_shell_result_with_execution_limit_is_reclassified():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize("tool-1", "Bash", {"command": "pwc search test"}).allowed

    result = budget.result(
        "tool-1",
        'pwc: API request failed (429): {"detail":"Tool execution limit reached"}',
        status="success",
        exit_code=0,
    )

    assert result["status"] == "error"
    assert result["metadata"]["exit_code"] == 1
    assert budget.tooling_closed


def test_tool_budget_counts_parallel_batches_and_denies_seventh_round_in_full():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=12,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
        maximum_rounds=effective_tool_rounds(8),
    )
    call_count = 0
    for round_index, batch_size in enumerate((2, 2, 2, 2, 1, 1), start=1):
        ids = [f"r{round_index}-{item}" for item in range(batch_size)]
        budget.register_round(ids)
        for tool_id in ids:
            assert budget.authorize(
                tool_id, "Bash", {"command": "pwc tasks list"}
            ).allowed
            call_count += 1
    assert call_count == 10
    assert budget.tool_rounds_started == 6
    assert budget.tool_rounds_executed == 6

    denied_ids = ["r7-a", "r7-b"]
    budget.register_round(denied_ids)
    assert all(
        not budget.authorize(tool_id, "Bash", {"command": "pwc tasks list"}).allowed
        for tool_id in denied_ids
    )
    assert budget.calls == 10
    assert budget.tool_rounds_denied == 1
    assert budget.tooling_closed


def test_worker_tool_budget_counts_parallel_calls_as_one_round_then_sequential():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=12,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
        maximum_rounds=1,
    )

    for tool_id in ("parallel-a", "parallel-b"):
        budget.register_call(tool_id)
        assert budget.authorize(tool_id, "Bash", {"command": "pwc tasks list"}).allowed

    assert budget.tool_rounds_started == 1
    assert budget.tool_rounds_executed == 1
    for tool_id in ("parallel-a", "parallel-b"):
        budget.result(tool_id, "ok", status="success")

    budget.register_call("parallel-a")
    assert not budget.authorize(
        "parallel-a", "Bash", {"command": "pwc tasks list"}
    ).allowed
    assert budget.tool_rounds_started == 2
    assert budget.tool_rounds_executed == 1
    assert budget.tool_rounds_denied == 1


def test_tool_output_is_utf8_bounded_and_terminal_controls_are_inert():
    text, truncated = bound_tool_output(b"\x1b[31m" + "é".encode() * 100, 64)
    assert truncated
    assert "\x1b" not in text
    assert len(text.encode()) <= 64


def test_tool_policy_rejects_traversal_and_enforces_aggregate_bytes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guide = tmp_path / "PWC_CLI_SKILL.md"
    guide.write_text("guide")
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    denied = budget.authorize(
        "outside",
        "Read",
        {"file_path": str(tmp_path / "secret")},
        workspace=workspace,
        guide=guide,
    )
    assert not denied.allowed
    assert denied.reason == (
        "Read and Grep may only access /workspace or the approved CLI guides. "
        "Rerun the source command with output redirected to /workspace, then try again."
    )
    inlined_skill = budget.authorize(
        "inlined-skill",
        "Read",
        {"file_path": str(guide)},
        workspace=workspace,
        guide=guide,
    )
    assert not inlined_skill.allowed
    assert inlined_skill.reason == (
        "The pwc, s2, and restricted hf CLI skills are already included verbatim in "
        "your system prompt. Read that text instead and run the CLI directly."
    )
    assert not budget.tooling_closed
    assert budget.authorize(
        "recovery",
        "Bash",
        {"command": "printf data > /workspace/result.txt"},
        workspace=workspace,
        guide=guide,
    ).allowed
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    for index in range(3):
        tool_id = f"tool-{index}"
        assert budget.authorize(
            tool_id,
            "Bash",
            {"command": "printf data"},
            workspace=workspace,
            guide=guide,
        ).allowed
        result = budget.result(tool_id, "x" * 100, status="success")
        assert len(result["content"][0]["text"].encode()) <= 24
    assert budget.output_bytes == 48


@pytest.mark.parametrize(
    ("command", "returncode"),
    [
        ("printf 'unmatched\\n' | { rg -- 'match' || test $? -eq 1; }", 0),
        ("false | { rg -- 'match' || test $? -eq 1; }", 1),
    ],
)
def test_rg_no_match_guard_preserves_upstream_pipefail_errors(command, returncode):
    result = subprocess.run(["bash", "-o", "pipefail", "-c", command], check=False)

    assert result.returncode == returncode
