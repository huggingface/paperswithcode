"""Executor channel frames and operation builders shared by stream tests."""

from __future__ import annotations

import asyncio
import json


from backend.chat_sandbox_worker.executor_protocol import (
    PROTOCOL,
    encode_response,
)
from backend.services.chat_sandbox_executor import ExecutorContext


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, object]:
    size = int.from_bytes(await reader.readexactly(4), "big")
    assert 0 < size <= 2 * 1024 * 1024
    value = json.loads(await reader.readexactly(size))
    assert isinstance(value, dict)
    return value


async def _write_frame(writer: asyncio.StreamWriter, value: dict[str, object]) -> None:
    encoded = json.dumps(value, separators=(",", ":")).encode()
    writer.write(len(encoded).to_bytes(4, "big") + encoded)
    await writer.drain()


def _context(execution_id: str, tool_call_id: str) -> ExecutorContext:
    return ExecutorContext(
        sandbox=object(),
        workspace_id="workspace-v1",
        workspace_generation=7,
        session_id="session-v1",
        turn_id="turn-v1",
        execution_id=execution_id,
        tool_call_id=tool_call_id,
        worker_generation="worker-v1",
        capability="capability-secret",
        turn_worker_id="turn-worker-v1",
        turn_worker_generation="turn-worker-generation-v1",
        turn_lease_generation="turn-lease-v1",
        turn_deadline_unix_ms=4_000_000_000_000,
    )


def _operation_response(
    request: dict[str, object], response_type: str, **fields: object
) -> bytes:
    return encode_response(
        {
            "protocol": PROTOCOL,
            "type": response_type,
            "request_id": request["request_id"],
            "workspace_id": request["workspace_id"],
            "workspace_generation": request["workspace_generation"],
            "session_id": request["session_id"],
            "turn_id": request["turn_id"],
            "execution_id": request["execution_id"],
            "tool_call_id": request["tool_call_id"],
            **fields,
        }
    )
