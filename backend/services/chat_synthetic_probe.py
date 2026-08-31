"""Four-hourly dedicated-account synthetic chat lifecycle probe."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from backend.config import get_settings
from backend.services.autonomous_cron_probe import FindingState

SYNTHETIC_PROMPT = "Reply with the single word healthy."


class SyntheticChatTransport(Protocol):
    async def verify_login(self) -> bool: ...
    async def create_session(self) -> str: ...
    def stream_turn(self, session_id: str) -> AsyncIterator[dict[str, object]]: ...
    async def session_is_reopenable(self, session_id: str) -> bool: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def session_is_absent(self, session_id: str) -> bool: ...
    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SyntheticChatResult:
    environment: str
    state: FindingState
    incident_signature: str
    steps: dict[str, str]
    observed_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "state": self.state.value,
            "incident_signature": self.incident_signature,
            "steps": self.steps,
            "observed_at": self.observed_at,
        }


class HttpSyntheticChatTransport:
    """Production-only HTTP adapter; credentials never enter probe results."""

    def __init__(self, *, cookie: str, expected_username: str):
        settings = get_settings()
        cookie_name = (
            settings.shared_session_cookie_name or settings.session_cookie_name
        )
        self.expected_username = expected_username
        self.client = httpx.AsyncClient(
            base_url="https://paperswithcode.co",
            timeout=httpx.Timeout(240, connect=15),
            cookies={cookie_name: cookie},
            headers={"User-Agent": "pwc-synthetic-chat-reliability/1"},
        )

    async def verify_login(self) -> bool:
        response = await self.client.get("/api/v1/auth/me")
        if response.status_code != 200:
            return False
        return response.json().get("username") == self.expected_username

    async def create_session(self) -> str:
        response = await self.client.post(
            "/api/v1/chat/sessions", json={"reasoning_effort": "low"}
        )
        response.raise_for_status()
        return str(response.json()["id"])

    async def stream_turn(self, session_id: str) -> AsyncIterator[dict[str, object]]:
        payload = {
            "message": SYNTHETIC_PROMPT,
            "client_message_id": f"synthetic-{uuid.uuid4()}",
            "session_id": session_id,
            "reasoning_effort": "low",
        }
        async with self.client.stream(
            "POST", "/api/v1/chat/stream", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    yield {"type": event.get("type")}

    async def session_is_reopenable(self, session_id: str) -> bool:
        response = await self.client.get(f"/api/v1/chat/sessions/{session_id}")
        if response.status_code != 200:
            return False
        messages = response.json().get("messages", [])
        return any(
            row.get("role") == "assistant" and row.get("status") == "complete"
            for row in messages
        )

    async def delete_session(self, session_id: str) -> None:
        response = await self.client.delete(f"/api/v1/chat/sessions/{session_id}")
        response.raise_for_status()

    async def session_is_absent(self, session_id: str) -> bool:
        response = await self.client.get(f"/api/v1/chat/sessions/{session_id}")
        return response.status_code == 404

    async def close(self) -> None:
        await self.client.aclose()


def _result(
    environment: str,
    state: FindingState,
    signature: str,
    steps: dict[str, str],
    now: datetime,
) -> SyntheticChatResult:
    return SyntheticChatResult(environment, state, signature, steps, now.isoformat())


async def run_synthetic_chat(
    environment: str,
    *,
    transport: SyntheticChatTransport | None = None,
    now: datetime | None = None,
) -> SyntheticChatResult:
    """Verify login through deletion without retaining prompt or response content."""

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    if environment != "production":
        return _result(
            environment,
            FindingState.UNKNOWN,
            "chat:synthetic:environment_refused",
            {},
            observed_at,
        )
    if transport is None:
        cookie = os.environ.get("PWC_CHAT_SYNTHETIC_SESSION_COOKIE", "")
        username = os.environ.get("PWC_CHAT_SYNTHETIC_EXPECTED_USERNAME", "")
        if not cookie or not username:
            return _result(
                environment,
                FindingState.UNKNOWN,
                "chat:synthetic:credential_unavailable",
                {},
                observed_at,
            )
        transport = HttpSyntheticChatTransport(
            cookie=cookie, expected_username=username
        )

    steps: dict[str, str] = {}
    session_id: str | None = None
    signature = "chat:synthetic:healthy"
    try:
        if not await transport.verify_login():
            steps["login"] = "degraded"
            return _result(
                environment,
                FindingState.DEGRADED,
                "chat:authentication:login_failed",
                steps,
                observed_at,
            )
        steps["login"] = "healthy"
        session_id = await transport.create_session()
        steps["admission"] = "healthy"
        first_token = False
        terminal = None
        async for event in transport.stream_turn(session_id):
            event_type = event.get("type")
            if event_type in {"answer_delta", "reasoning_delta"}:
                first_token = True
            if event_type in {"done", "error"}:
                terminal = str(event_type)
        steps["first_token"] = "healthy" if first_token else "degraded"
        steps["complete_stream"] = "healthy" if terminal == "done" else "degraded"
        if not first_token:
            signature = "chat:stream:first_token_missing"
        elif terminal != "done":
            signature = "chat:stream:terminal_error"
        reopenable = await transport.session_is_reopenable(session_id)
        steps["persistence_reopen"] = "healthy" if reopenable else "degraded"
        if signature == "chat:synthetic:healthy" and not reopenable:
            signature = "chat:persistence:reopen_failed"
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        signature = "chat:synthetic:transport_error"
        steps.setdefault("admission", "degraded")
    finally:
        if session_id is not None:
            try:
                await transport.delete_session(session_id)
                absent = await transport.session_is_absent(session_id)
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                absent = False
            steps["cleanup"] = "healthy" if absent else "degraded"
            if not absent and signature == "chat:synthetic:healthy":
                signature = "chat:cleanup:deletion_failed"
        try:
            await transport.close()
        except httpx.HTTPError:
            steps["cleanup"] = "degraded"
            if signature == "chat:synthetic:healthy":
                signature = "chat:cleanup:transport_close_failed"

    expected = {
        "login",
        "admission",
        "first_token",
        "complete_stream",
        "persistence_reopen",
        "cleanup",
    }
    state = (
        FindingState.HEALTHY
        if set(steps) == expected
        and all(value == "healthy" for value in steps.values())
        else FindingState.DEGRADED
    )
    return _result(environment, state, signature, steps, observed_at)
