"""Bounded, credential-free requests to the first-party stateless MCP server."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx

ENDPOINT = "https://paperswithcode.co/mcp"
MAX_RESPONSE_BYTES = 1024 * 1024
TOOL_NAMES = frozenset(
    {
        "search_papers",
        "get_paper_info",
        "list_papers",
        "read_paper",
        "get_related_papers",
        "get_paper_lineage",
        "get_task",
        "get_method",
        "list_benchmarks",
        "get_benchmark",
    }
)
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


class PwcMcpError(Exception):
    """Sanitized upstream failure; never includes request or response contents."""


async def request_mcp(
    client: httpx.AsyncClient, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {**params, "_meta": META},
    }
    try:
        async with asyncio.timeout(30):
            async with client.stream(
                "POST",
                ENDPOINT,
                json=payload,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code != 200:
                    raise PwcMcpError("Papers With Code MCP is unavailable")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise PwcMcpError(
                            "MCP response is too large; narrow the request"
                        )
                value = json.loads(chunks)
    except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError) as error:
        raise PwcMcpError("Papers With Code MCP request failed") from error
    if (
        not isinstance(value, dict)
        or value.get("jsonrpc") != "2.0"
        or value.get("id") != request_id
        or "error" in value
        or not isinstance(value.get("result"), dict)
    ):
        raise PwcMcpError("Papers With Code MCP returned an invalid response")
    result = value["result"]
    if method == "tools/list":
        tools = result.get("tools")
        if not isinstance(tools, list) or any(not isinstance(t, dict) for t in tools):
            raise PwcMcpError("Papers With Code MCP returned invalid tools")
        selected = [t for t in tools if t.get("name") in TOOL_NAMES]
        if (
            len(selected) != len(TOOL_NAMES)
            or {t["name"] for t in selected} != TOOL_NAMES
        ):
            raise PwcMcpError("Papers With Code MCP tool contract is incomplete")
        return {"tools": selected}
    return result
