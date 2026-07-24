"""Agent SDK SessionStore adapter scoped through the localhost broker."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any


class RemoteSessionStore:
    def __init__(self, origin: str = "http://127.0.0.1:8765"):
        self.origin = origin.rstrip("/")

    def _request(self, payload: dict[str, Any]) -> Any:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"{self.origin}/session-store",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2 * 1024 * 1024)
        return json.loads(body).get("result")

    async def append(self, key: dict, entries: list[dict]) -> None:
        await asyncio.to_thread(
            self._request, {"action": "append", "key": key, "entries": entries}
        )

    async def load(self, key: dict) -> list[dict] | None:
        return await asyncio.to_thread(self._request, {"action": "load", "key": key})

    async def list_sessions(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(
            self._request, {"action": "list_sessions", "project_key": project_key}
        )

    async def list_session_summaries(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(
            self._request,
            {"action": "list_session_summaries", "project_key": project_key},
        )

    async def list_subkeys(self, key: dict) -> list[str]:
        return await asyncio.to_thread(
            self._request, {"action": "list_subkeys", "key": key}
        )

    async def delete(self, key: dict) -> None:
        await asyncio.to_thread(self._request, {"action": "delete", "key": key})
