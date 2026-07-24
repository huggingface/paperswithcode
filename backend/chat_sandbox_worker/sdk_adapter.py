"""Generic SDK message-to-event adapter with no server dependencies."""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)


class SDKEventAdapter:
    def __init__(self, *, show_reasoning: bool):
        self.show_reasoning = show_reasoning
        self.reasoning_open = False
        self.answer_started = False
        self.saw_text_delta = False
        self.saw_thinking_delta = False
        self.terminal = False
        self.block_kinds: dict[int, str] = {}
        self.tool_blocks: dict[int, dict[str, Any]] = {}
        self.emitted_tool_ids: set[str] = set()

    def _close_reasoning(self) -> list[dict[str, Any]]:
        if not self.reasoning_open:
            return []
        self.reasoning_open = False
        return [{"type": "reasoning_end"}]

    def _tool_call(self, block: dict[str, Any]) -> list[dict[str, Any]]:
        tool_id = str(block.get("id") or "")
        if not tool_id or tool_id in self.emitted_tool_ids:
            return []
        value = block.get("input")
        if not isinstance(value, dict):
            try:
                value = json.loads("".join(block.get("fragments", [])) or "{}")
            except json.JSONDecodeError:
                return []
        self.emitted_tool_ids.add(tool_id)
        return [
            {
                "type": "tool_call",
                "id": tool_id,
                "name": str(block.get("name") or ""),
                "args": value,
            }
        ]

    def _stream(self, message: StreamEvent) -> list[dict[str, Any]]:
        raw = message.event
        kind = raw.get("type")
        events: list[dict[str, Any]] = []
        index = int(raw.get("index", 0))
        if kind == "content_block_start":
            block = raw.get("content_block") or {}
            block_kind = block.get("type", "")
            self.block_kinds[index] = block_kind
            if block_kind == "thinking" and self.show_reasoning:
                self.reasoning_open = True
                events.append({"type": "reasoning_start"})
            elif block_kind == "tool_use":
                events.extend(self._close_reasoning())
                self.tool_blocks[index] = {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input"),
                    "fragments": [],
                }
            elif block_kind == "text":
                events.extend(self._close_reasoning())
        elif kind == "content_block_delta":
            delta = raw.get("delta") or {}
            if delta.get("type") == "thinking_delta" and self.show_reasoning:
                self.saw_thinking_delta = True
                if not self.reasoning_open:
                    self.reasoning_open = True
                    events.append({"type": "reasoning_start"})
                if delta.get("thinking"):
                    events.append(
                        {"type": "reasoning_delta", "text": delta["thinking"]}
                    )
            elif delta.get("type") == "text_delta":
                events.extend(self._close_reasoning())
                text = delta.get("text", "")
                if text and (self.answer_started or text.strip()):
                    self.answer_started = True
                    self.saw_text_delta = True
                    events.append({"type": "answer_delta", "text": text})
            elif delta.get("type") == "input_json_delta":
                self.tool_blocks.setdefault(
                    index, {"id": "", "name": "", "input": None, "fragments": []}
                )["fragments"].append(delta.get("partial_json", ""))
        elif kind == "content_block_stop":
            if self.block_kinds.get(index) == "thinking":
                events.extend(self._close_reasoning())
            elif self.block_kinds.get(index) == "tool_use":
                events.extend(self._tool_call(self.tool_blocks.get(index, {})))
        elif kind == "message_stop":
            events.extend(self._close_reasoning())
        return events

    def feed(self, message: Any) -> list[dict[str, Any]]:
        if isinstance(message, StreamEvent):
            return self._stream(message)
        events: list[dict[str, Any]] = []
        if isinstance(message, AssistantMessage):
            if message.error:
                self.terminal = True
                return [
                    {
                        "type": "error",
                        "code": "gateway_unavailable",
                        "message": "The model provider failed.",
                    }
                ]
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    events.extend(
                        self._tool_call(
                            {"id": block.id, "name": block.name, "input": block.input}
                        )
                    )
                elif isinstance(block, ThinkingBlock) and not self.saw_thinking_delta:
                    if self.show_reasoning and block.thinking:
                        events.extend(
                            [
                                {"type": "reasoning_start"},
                                {"type": "reasoning_delta", "text": block.thinking},
                                {"type": "reasoning_end"},
                            ]
                        )
                elif isinstance(block, TextBlock) and not self.saw_text_delta:
                    if block.text and (self.answer_started or block.text.strip()):
                        self.answer_started = True
                        events.append({"type": "answer_delta", "text": block.text})
            self.saw_text_delta = False
            self.saw_thinking_delta = False
        elif isinstance(message, ResultMessage):
            events.extend(self._close_reasoning())
            self.terminal = True
            limited = "max_turn" in message.subtype
            if message.is_error and not limited:
                events.append(
                    {
                        "type": "error",
                        "code": "gateway_unavailable",
                        "message": "The research run failed.",
                    }
                )
            else:
                events.append(
                    {
                        "type": "done",
                        "followups": [],
                        "finish_reason": "tool_limit" if limited else "success",
                    }
                )
        return events
