"""Bounded, credential-free requests to the first-party stateless MCP server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

import httpx

ENDPOINT = "https://paperswithcode.co/mcp"
# Each environment talks to its own MCP component (deploy/mcp_release.py ports);
# staging must exercise the staging release rather than production's.
# The gateway connects to the loopback listener directly (no nginx hop) so the
# server accepts X-PwC-MCP-Client and rate-limits each chat session on its own.
ENDPOINTS = {
    "production": "http://127.0.0.1:8002/mcp",
    "staging": "http://127.0.0.1:8003/mcp",
}
CLIENT_IDENTITY_HEADER = "X-PwC-MCP-Client"
MAX_RESPONSE_BYTES = 1024 * 1024
# One tool per read-only pwc CLI research command (huggingface/pwc-cli PR #13).
TOOL_NAMES = frozenset(
    {
        "search_papers",
        "get_paper_info",
        "list_papers",
        "read_paper",
        "list_recent_papers",
        "list_trending_papers",
        "get_related_papers",
        "get_paper_lineage",
        "get_task",
        "list_tasks",
        "get_method",
        "list_methods",
        "get_conference",
        "list_conferences",
        "get_organization",
        "list_organizations",
        "get_framework",
        "list_frameworks",
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


def endpoint_for(environment: str) -> str:
    """Return the MCP endpoint of one environment; unknown names use the public URL."""
    return ENDPOINTS.get(environment, ENDPOINT)


def client_identity(session_id: str) -> str:
    """Opaque per-chat-session rate-limit identity; never the raw session ID."""
    digest = hashlib.sha256(f"chat-session:{session_id}".encode()).hexdigest()
    return f"chat-{digest[:32]}"


async def request_mcp(
    client: httpx.AsyncClient,
    method: str,
    params: dict[str, Any],
    endpoint: str = ENDPOINT,
    identity: str | None = None,
) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if identity:
        headers[CLIENT_IDENTITY_HEADER] = identity
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
                endpoint,
                json=payload,
                headers=headers,
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
