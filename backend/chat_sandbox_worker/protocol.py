"""Versioned, bounded stdout protocol for one sandbox worker."""

from __future__ import annotations

import json
from typing import Any

FRAME_PREFIX = "@@PWC_CHAT_V1@@"
MAX_FRAME_BYTES = 512 * 1024


class ProtocolError(RuntimeError):
    pass


class WorkerEventValidator:
    """Reject duplicate terminals and uncorrelated tool results."""

    allowed = {
        "worker_ready",
        "_sdk_session",
        "_mirror_error",
        "usage",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "answer_delta",
        "done",
        "error",
        "worker_done",
    }

    def __init__(self):
        self.tools: set[str] = set()
        self.results: set[str] = set()
        self.terminal = False

    def accept(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind not in self.allowed:
            raise ProtocolError("Unknown worker event type")
        if self.terminal and kind != "worker_done":
            raise ProtocolError("Worker event followed a terminal event")
        if kind == "tool_call":
            tool_id = str(event.get("id") or "")
            if not tool_id or tool_id in self.tools:
                raise ProtocolError("Duplicate or invalid tool call")
            self.tools.add(tool_id)
        elif kind == "tool_result":
            tool_id = str(event.get("id") or "")
            if tool_id not in self.tools or tool_id in self.results:
                raise ProtocolError("Uncorrelated or duplicate tool result")
            self.results.add(tool_id)
        elif kind in {"done", "error"}:
            if self.terminal:
                raise ProtocolError("Duplicate terminal worker event")
            self.terminal = True


def encode_frame(payload: dict[str, Any]) -> bytes:
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(value) > MAX_FRAME_BYTES:
        raise ProtocolError("Worker frame is too large")
    return FRAME_PREFIX.encode() + value + b"\n"


def decode_frame(line: bytes) -> dict[str, Any]:
    if not line.startswith(FRAME_PREFIX.encode()):
        raise ProtocolError("Invalid worker frame prefix")
    payload = line[len(FRAME_PREFIX) :]
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("Worker frame is too large")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ProtocolError("Invalid worker frame JSON") from error
    if not isinstance(value, dict) or value.get("v") != 1:
        raise ProtocolError("Unsupported worker protocol version")
    return value
