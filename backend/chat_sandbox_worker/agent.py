"""Stock Claude Agent SDK harness for one sandboxed chat turn."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    MirrorErrorMessage,
    ToolResultBlock,
    UserMessage,
    query as sdk_query,
)

from backend.chat_sandbox_worker.protocol import decode_frame, encode_frame
from backend.chat_sandbox_worker.prompt import render as render_system_prompt
from backend.chat_sandbox_worker.remote_store import RemoteSessionStore
from backend.chat_sandbox_worker.config import WorkerSettings
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output

GUIDE = Path("/opt/pwc/CLI_GUIDE.md")
WORKSPACE = Path("/workspace")


def _response_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and item.get("type") == "text"
        )
    if isinstance(value, dict):
        stdout = value.get("stdout")
        stderr = value.get("stderr")
        if isinstance(stdout, str) or isinstance(stderr, str):
            return f"{stdout or ''}{stderr or ''}"
        for key in ("content", "output", "result"):
            if isinstance(value.get(key), str):
                return value[key]
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class WorkerToolHooks:
    def __init__(self, settings: WorkerSettings):
        self.budget = ToolBudget(
            maximum_calls=settings.chat_max_tool_calls,
            maximum_direct_searches=settings.chat_max_direct_search_calls,
            maximum_result_bytes=settings.chat_tool_result_max_bytes,
            maximum_turn_output_bytes=settings.chat_turn_tool_output_max_bytes,
        )
        self.bash_timeout_ms = round(settings.chat_bash_timeout_seconds * 1000)
        self.results: dict[str, dict[str, Any]] = {}

    async def pre(self, hook_input: dict, tool_use_id: str | None, _context: Any):
        tool_id = tool_use_id or str(hook_input.get("tool_use_id") or "")
        name = str(hook_input.get("tool_name") or "")
        arguments = hook_input.get("tool_input") or {}
        decision = self.budget.authorize(tool_id, name, arguments)
        if not decision.allowed:
            self.results[tool_id] = self.budget.result(
                tool_id, decision.reason or "Tool denied.", status="denied"
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": decision.reason,
                }
            }
        updated = dict(arguments)
        if name == "Bash":
            requested = updated.get("timeout")
            updated["timeout"] = min(
                int(requested)
                if isinstance(requested, (int, float))
                else self.bash_timeout_ms,
                self.bash_timeout_ms,
            )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": updated,
            }
        }

    async def post(self, hook_input: dict, tool_use_id: str | None, _context: Any):
        tool_id = tool_use_id or str(hook_input.get("tool_use_id") or "")
        name = str(hook_input.get("tool_name") or "")
        original = hook_input.get("tool_response")
        text = _response_text(original)
        event = self.budget.result(tool_id, text, status="success", exit_code=0)
        self.results[tool_id] = event
        bounded = event["content"][0]["text"]
        if name == "Bash" and isinstance(original, dict):
            updated: Any = dict(original)
            updated["stdout"] = bounded
            updated["stderr"] = ""
        elif isinstance(original, dict):
            updated = dict(original)
            key = next(
                (
                    candidate
                    for candidate in ("content", "output", "result")
                    if candidate in updated
                ),
                None,
            )
            if key is not None:
                updated[key] = bounded
            else:
                updated = bounded
        else:
            updated = bounded
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": updated,
            }
        }

    async def failure(self, hook_input: dict, tool_use_id: str | None, _context: Any):
        tool_id = tool_use_id or str(hook_input.get("tool_use_id") or "")
        error = str(hook_input.get("error") or "Tool failed")
        self.results[tool_id] = self.budget.result(
            tool_id, error, status="error", exit_code=1
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": self.results[tool_id]["content"][0]["text"],
            }
        }


async def stream_turn(frame: dict[str, Any], settings: WorkerSettings):
    if frame.get("type") != "run_turn":
        raise ValueError("Expected run_turn")
    prompt = frame.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8_000:
        raise ValueError("Invalid prompt")
    request_id = str(frame.get("request_id") or "")
    hooks = WorkerToolHooks(settings)
    adapter = SDKEventAdapter(show_reasoning=settings.chat_show_reasoning)
    prompt_text = render_system_prompt(
        max_turns=settings.chat_max_turns,
        max_calls=settings.chat_max_tool_calls,
        max_searches=settings.chat_max_direct_search_calls,
        guide_path=GUIDE,
    )
    model = str(frame["model"])
    options = ClaudeAgentOptions(
        tools=["Bash", "Read", "Grep"],
        allowed_tools=["Bash", "Read", "Grep"],
        disallowed_tools=[
            "Glob",
            "Write",
            "Edit",
            "WebFetch",
            "WebSearch",
            "Task",
            "AskUserQuestion",
        ],
        system_prompt=prompt_text,
        mcp_servers={},
        strict_mcp_config=True,
        permission_mode="dontAsk",
        max_turns=settings.chat_max_turns,
        model=model,
        fallback_model=None,
        env={
            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8765",
            "ANTHROPIC_API_KEY": "sandbox-placeholder-not-a-credential",
            "ANTHROPIC_AUTH_TOKEN": "sandbox-placeholder-not-a-credential",
            "PWC_API_URL": "http://127.0.0.1:8765/api/v1",
            "CLAUDE_CONFIG_DIR": "/home/pwc-chat/.claude",
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        },
        cwd=WORKSPACE,
        setting_sources=[],
        skills=[],
        plugins=[],
        include_partial_messages=True,
        stderr=lambda _line: None,
        hooks={
            "PreToolUse": [
                HookMatcher(matcher="Bash|Read|Grep", hooks=[hooks.pre], timeout=5)
            ],
            "PostToolUse": [
                HookMatcher(matcher="Bash|Read|Grep", hooks=[hooks.post], timeout=5)
            ],
            "PostToolUseFailure": [
                HookMatcher(matcher="Bash|Read|Grep", hooks=[hooks.failure], timeout=5)
            ],
        },
        session_store=RemoteSessionStore(),
        session_store_flush="eager",
        resume=frame.get("resume"),
    )
    stream = sdk_query(prompt=prompt, options=options)
    try:
        async with asyncio.timeout(settings.chat_agent_timeout_seconds):
            async for message in stream:
                if isinstance(message, MirrorErrorMessage):
                    yield {
                        "v": 1,
                        "type": "_mirror_error",
                        "request_id": request_id,
                    }
                    continue
                session_id = getattr(message, "session_id", None)
                if session_id:
                    yield {
                        "v": 1,
                        "type": "_sdk_session",
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                if isinstance(message, UserMessage):
                    for block in (
                        message.content if isinstance(message.content, list) else []
                    ):
                        if not isinstance(block, ToolResultBlock):
                            continue
                        event = hooks.results.pop(block.tool_use_id, None)
                        if event is None:
                            text, truncated = bound_tool_output(
                                _response_text(block.content),
                                settings.chat_tool_result_max_bytes,
                            )
                            event = {
                                "type": "tool_result",
                                "id": block.tool_use_id,
                                "status": "error" if block.is_error else "success",
                                "took_ms": 0,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": text,
                                        "truncated": truncated,
                                    }
                                ],
                                "metadata": {
                                    "exit_code": 1 if block.is_error else 0,
                                    "output_truncated": truncated,
                                },
                            }
                        yield {"v": 1, "request_id": request_id, **event}
                    continue
                for event in adapter.feed(message):
                    yield {"v": 1, "request_id": request_id, **event}
                if adapter.terminal:
                    return
    except TimeoutError:
        yield {
            "v": 1,
            "type": "error",
            "request_id": request_id,
            "code": "sandbox_timeout",
            "message": "The research run timed out.",
        }
    finally:
        await stream.aclose()


async def main_async() -> int:
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: protocol, sys.stdin.buffer
    )
    line = await reader.readline()
    frame = decode_frame(line)
    settings = WorkerSettings.from_environment()
    stopped = False

    async def emit() -> None:
        async for event in stream_turn(frame, settings):
            sys.stdout.buffer.write(encode_frame(event))
            sys.stdout.buffer.flush()

    run_task = asyncio.create_task(emit())

    async def watch_cancel() -> None:
        nonlocal stopped
        while line := await reader.readline():
            candidate = decode_frame(line)
            if candidate.get("type") == "cancel" and candidate.get(
                "request_id"
            ) == frame.get("request_id"):
                stopped = True
                run_task.cancel()
                return

    cancel_task = asyncio.create_task(watch_cancel())
    try:
        await run_task
    except asyncio.CancelledError:
        if not stopped:
            raise
    finally:
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass
    sys.stdout.buffer.write(
        encode_frame(
            {
                "v": 1,
                "type": "worker_done",
                "request_id": str(frame.get("request_id") or ""),
                "status": "stopped" if stopped else "complete",
            }
        )
    )
    sys.stdout.buffer.flush()
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
