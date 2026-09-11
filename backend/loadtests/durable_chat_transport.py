"""Concrete bounded HTTP/SSE transport for durable staging qualification."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from backend.loadtests.external_pi_fleet_core import (
    FleetRunRefused,
    DurableQualificationEvidence,
)
from backend.services.durable_external_qualification_contract import (
    DURABLE_QUALIFICATION_TEARDOWN_TIMEOUT_SECONDS,
)

_STAGING_ORIGIN = "https://staging.paperswithcode.co"
_CHAT_STREAM_PATH = "/api/v1/chat/stream"
_QUALIFICATION_SCOPE_PATH = "/api/v1/chat/admin/qualification-scopes"
_QUALIFICATION_EVIDENCE_PATH = "/api/v1/chat/admin/qualification-evidence"
_MAX_EVENT_BYTES = 128 * 1024
_MAX_STREAM_BYTES = 2 * 1024 * 1024
_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_EVENTS = {
    "stream_start",
    "reasoning_start",
    "answer_delta",
    "reasoning_delta",
    "reasoning_end",
    "tool_call",
    "tool_call_start",
    "tool_call_arguments_delta",
    "tool_call_arguments_done",
    "tool_result",
    "sandbox_start",
    "sandbox_ready",
    "workspace_ready",
    "lifecycle",
    "done",
    "error",
    "session_title_start",
    "session_title_delta",
    "session_title_done",
    "app_start",
    "app_result",
    "artifact_start",
    "artifact_ready",
    "artifact_error",
}
_PROMPTS = {
    "no_tool": "Reply with READY only. Do not call tools.",
    "admission_stream": "Reply with READY only. Do not call tools.",
    "read": (
        "Use the Read tool exactly once to read durable-ready.txt. "
        "Do not use Bash or any other tool."
    ),
    "bash": (
        "Use the Bash tool exactly once to run `printf durable-ready`, "
        "then report only the exit code."
    ),
}


def _profile_run_id(base: str, profile_name: str) -> str:
    suffix = "f32" if profile_name == "32-functional-turns" else "a100"
    return f"{base}-{suffix}"


class DurableUser(Protocol):
    ordinal: int
    workload: str


class _HttpSession(Protocol):
    cookies: object
    trust_env: bool
    proxies: dict

    def post(self, url: str, **kwargs): ...

    def delete(self, url: str, **kwargs): ...

    def close(self) -> None: ...


def _requests_session() -> _HttpSession:
    # Locust must get the first opportunity to patch networking in live runs.
    import requests

    return requests.Session()


@dataclass(frozen=True, slots=True)
class DurableChatTransportConfig:
    base_url: str
    synthetic_cookies: tuple[str, ...] = field(repr=False)
    initial_model: str
    qualification_run_id: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    max_spend_microusd: int = field(default=10_000_000)
    provider_spend_ceiling_microusd: int = field(default=0)
    timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != _STAGING_ORIGIN:
            raise FleetRunRefused("durable transport requires the exact staging origin")
        if (
            not 1 <= len(self.synthetic_cookies) <= 100
            or any(
                not cookie or len(cookie) > 8_192 for cookie in self.synthetic_cookies
            )
            or len(set(self.synthetic_cookies)) != len(self.synthetic_cookies)
        ):
            raise FleetRunRefused("durable transport synthetic credentials are invalid")
        if not self.initial_model or len(self.initial_model) > 128:
            raise FleetRunRefused("durable transport model is invalid")
        if self.qualification_run_id and not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{0,31}", self.qualification_run_id
        ):
            raise FleetRunRefused("durable qualification scope is invalid")
        if self.admin_token and not 32 <= len(self.admin_token) <= 8192:
            raise FleetRunRefused("durable qualification admin credential is invalid")
        if bool(self.qualification_run_id) != bool(self.admin_token):
            raise FleetRunRefused("durable qualification credentials are incomplete")
        if self.qualification_run_id and not 1 <= self.max_spend_microusd <= 10_000_000:
            raise FleetRunRefused("durable qualification spend envelope is invalid")
        if not 0 <= self.provider_spend_ceiling_microusd <= self.max_spend_microusd:
            raise FleetRunRefused("durable qualification provider budget is invalid")
        if not 1 <= self.timeout_seconds <= 120:
            raise FleetRunRefused("durable transport timeout is invalid")


@dataclass(frozen=True, slots=True)
class _SSEEvent:
    sequence: int
    event: str
    data: Mapping[str, object] = field(repr=False)


class _SSEParser:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._total = 0

    def feed(self, chunk: bytes) -> tuple[_SSEEvent, ...]:
        if not isinstance(chunk, bytes):
            raise FleetRunRefused("durable SSE chunk is invalid")
        self._total += len(chunk)
        if self._total > _MAX_STREAM_BYTES:
            raise FleetRunRefused("durable SSE stream exceeds its bound")
        self._buffer.extend(chunk)
        events: list[_SSEEvent] = []
        while True:
            normalized = bytes(self._buffer).replace(b"\r\n", b"\n")
            boundary = normalized.find(b"\n\n")
            if boundary < 0:
                if len(self._buffer) > _MAX_EVENT_BYTES:
                    raise FleetRunRefused("durable SSE event exceeds its bound")
                break
            block = normalized[:boundary]
            self._buffer = bytearray(normalized[boundary + 2 :])
            if not block or block.startswith(b":"):
                continue
            events.append(self._parse(block))
        return tuple(events)

    def close(self) -> None:
        if self._buffer.strip():
            raise FleetRunRefused("durable SSE stream ended mid-event")

    @staticmethod
    def _parse(block: bytes) -> _SSEEvent:
        fields: dict[str, bytes] = {}
        for line in block.splitlines():
            name, separator, value = line.partition(b":")
            if (
                not separator
                or name not in {b"id", b"event", b"data"}
                or name.decode() in fields
            ):
                raise FleetRunRefused("durable SSE fields are invalid")
            fields[name.decode()] = value.lstrip(b" ")
        if set(fields) != {"id", "event", "data"}:
            raise FleetRunRefused("durable SSE fields are incomplete")
        try:
            sequence = int(fields["id"])
            event = fields["event"].decode("ascii")
            data = json.loads(fields["data"])
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise FleetRunRefused("durable SSE event is malformed") from None
        if sequence < 1 or not isinstance(data, dict):
            raise FleetRunRefused("durable SSE event contract is invalid")
        if event not in _EVENTS:
            raise FleetRunRefused(f"durable SSE event is not allowed: {event}")
        if data.get("type") != event:
            raise FleetRunRefused("durable SSE event type is inconsistent")
        return _SSEEvent(sequence, event, data)


class HttpSSEDurableChatTransport:
    """Drive one real chat turn, detach after admission, and resume by cursor."""

    def __init__(
        self,
        config: DurableChatTransportConfig,
        *,
        scope_id: uuid.UUID | None = None,
        session_factory: Callable[[], _HttpSession] = _requests_session,
    ) -> None:
        self._config = config
        self._scope_id = scope_id
        self._session_factory = session_factory

    def open_durable_stream(self, spec: DurableUser) -> Mapping[str, object]:
        session = self._session_factory()
        try:
            return self._open_durable_stream_with_session(spec, session)
        finally:
            session.close()

    def _open_durable_stream_with_session(
        self, spec: DurableUser, session: _HttpSession
    ) -> Mapping[str, object]:
        if (
            type(spec.ordinal) is not int
            or not 0 <= spec.ordinal < len(self._config.synthetic_cookies)
            or spec.workload not in _PROMPTS
        ):
            raise FleetRunRefused("durable user assignment is invalid")
        session.trust_env = False
        session.proxies.clear()
        hostname = urlsplit(self._config.base_url).hostname
        session.cookies.set(
            "pwc_staging_session",
            self._config.synthetic_cookies[spec.ordinal],
            domain=hostname,
            secure=True,
        )
        client_message_id = str(uuid.uuid4())
        body: dict[str, object] = {
            "message": _PROMPTS[spec.workload],
            "session_id": None,
            "client_message_id": client_message_id,
            "web_search_enabled": False,
            "reasoning_effort": "low",
            "initial_model": self._config.initial_model,
        }
        started = time.perf_counter()
        first = self._open(session, body, after_sequence=None, workload=spec.workload)
        if first.status_code != 200:
            return self._refusal(first, started, workload=spec.workload)

        session_id: str | None = None
        request_id: str | None = None
        cursor = 0
        model_starts = 0
        admission_ms: int | None = None
        with first:
            parser = _SSEParser()
            detached = False
            for event in self._events(first, parser):
                cursor = self._advance(cursor, event)
                if event.event != "stream_start":
                    raise FleetRunRefused("durable stream did not begin with admission")
                session_id, request_id, starts = self._stream_identity(event)
                model_starts += starts
                admission_ms = self._elapsed_ms(started)
                detached = True
                break
            if not detached or admission_ms is None:
                raise FleetRunRefused("durable stream admission evidence is missing")

        body["session_id"] = session_id
        second = self._open(
            session, body, after_sequence=cursor, workload=spec.workload
        )
        if second.status_code != 200:
            raise FleetRunRefused("durable reconnect was refused")
        reconnect_ready_ms = self._elapsed_ms(started)
        ttft_ms: int | None = None
        terminal_cause: str | None = None
        failure_code: str | None = None
        duplicate_turns = 0
        with second:
            parser = _SSEParser()
            saw_resumed_event = False
            for event in self._events(second, parser):
                cursor = self._advance(cursor, event)
                saw_resumed_event = True
                if (
                    event.event
                    in {
                        "answer_delta",
                        "reasoning_delta",
                        "tool_call",
                        "tool_call_start",
                    }
                    and ttft_ms is None
                ):
                    ttft_ms = self._elapsed_ms(started)
                if event.event == "stream_start":
                    replay_session, replay_request, starts = self._stream_identity(
                        event
                    )
                    duplicate_turns += int(
                        replay_session != session_id or replay_request != request_id
                    )
                    model_starts += starts
                elif event.event == "error":
                    code = event.data.get("code")
                    if not isinstance(code, str) or not _CODE.fullmatch(code):
                        raise FleetRunRefused("durable stream failure is untyped")
                    failure_code = code
                    terminal_cause = "failed"
                    break
                elif event.event == "done":
                    terminal_cause = "completed"
                    break
            if not saw_resumed_event:
                raise FleetRunRefused("durable reconnect replay is empty")
        if terminal_cause is None:
            raise FleetRunRefused("durable stream terminal is missing")
        completion_ms = self._elapsed_ms(started)
        return {
            "workload": spec.workload,
            "outcome": terminal_cause,
            "admission_ms": admission_ms,
            "reconnect_ready_ms": reconnect_ready_ms,
            "ttft_ms": ttft_ms,
            "completion_ms": completion_ms,
            "reconnects": 1,
            "reconnect_successes": 1,
            "model_starts": model_starts,
            "duplicate_turns": duplicate_turns,
            "terminal_cause": terminal_cause,
            "failure_code": failure_code,
        }

    def _open(
        self,
        session,
        body: Mapping[str, object],
        *,
        after_sequence: int | None,
        workload: str,
    ):
        headers = {
            "Accept": "text/event-stream",
            "Origin": _STAGING_ORIGIN,
        }
        if self._scope_id is not None:
            headers.update(
                {
                    "X-Admin-Token": self._config.admin_token,
                    "X-PWC-Qualification-Scope-ID": str(self._scope_id),
                    "X-PWC-Qualification-Workload": {
                        "no_tool": "no_tool",
                        "admission_stream": "no_tool",
                        "read": "read",
                        "bash": "bash",
                    }[workload],
                }
            )
        if after_sequence is not None:
            headers["Last-Event-ID"] = str(after_sequence)
        return session.post(
            urljoin(self._config.base_url, _CHAT_STREAM_PATH),
            json=dict(body),
            headers=headers,
            stream=True,
            timeout=self._config.timeout_seconds,
            allow_redirects=False,
        )

    @staticmethod
    def _events(response, parser: _SSEParser) -> Iterator[_SSEEvent]:
        # Qualification measures the first semantic SSE event, so it must not
        # wait for a later event merely to fill urllib3's requested read size.
        # This path carries only the bounded synthetic staging workload.
        for chunk in response.iter_content(chunk_size=1):
            for event in parser.feed(chunk):
                yield event
        parser.close()

    @staticmethod
    def _advance(cursor: int, event: _SSEEvent) -> int:
        if event.sequence <= cursor:
            raise FleetRunRefused("durable SSE cursor is duplicate or stale")
        return event.sequence

    @staticmethod
    def _stream_identity(event: _SSEEvent) -> tuple[str, str, int]:
        session_id = event.data.get("session_id")
        request_id = event.data.get("request_id")
        provider_execution = event.data.get("provider_execution")
        try:
            uuid.UUID(str(session_id))
            uuid.UUID(str(request_id))
        except ValueError:
            raise FleetRunRefused("durable stream identity is invalid") from None
        if type(provider_execution) is not bool:
            raise FleetRunRefused("durable model-start evidence is invalid")
        return str(session_id), str(request_id), int(provider_execution)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1_000))

    @classmethod
    def _refusal(
        cls, response, started: float, *, workload: str
    ) -> Mapping[str, object]:
        with response:
            try:
                payload = response.json()
            except ValueError:
                payload = None
        if response.status_code != 429 or payload != {
            "detail": {"code": "chat_overload"}
        }:
            raise FleetRunRefused("durable chat refusal is untyped")
        elapsed = cls._elapsed_ms(started)
        return {
            "workload": workload,
            "outcome": "refused",
            "ttft_ms": elapsed,
            "completion_ms": elapsed,
            "reconnects": 0,
            "reconnect_successes": 0,
            "model_starts": 0,
            "duplicate_turns": 0,
            "terminal_cause": "refused",
            "failure_code": "chat_overload",
        }


class HttpDurableQualificationEvidenceSource:
    """Read one exact durable run cohort from the protected staging API."""

    def __init__(
        self,
        config: DurableChatTransportConfig,
        *,
        session_factory: Callable[[], _HttpSession] = _requests_session,
    ) -> None:
        self._config = config
        self._session_factory = session_factory

    def _session(self) -> _HttpSession:
        session = self._session_factory()
        session.trust_env = False
        session.proxies.clear()
        session.cookies.set(
            "pwc_staging_session",
            self._config.synthetic_cookies[0],
            domain=urlsplit(self._config.base_url).hostname,
            secure=True,
        )
        return session

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Accept": "application/json", "Origin": _STAGING_ORIGIN}

    def begin_scope(self, profile_name: str) -> Mapping[str, object]:
        if profile_name not in {"32-functional-turns", "100-immediate-admission"}:
            raise FleetRunRefused("durable qualification profile is invalid")
        if not self._config.admin_token or not self._config.qualification_run_id:
            raise FleetRunRefused("durable qualification credentials are incomplete")
        session = self._session()
        try:
            headers = self._headers() | {"X-Admin-Token": self._config.admin_token}
            response = session.post(
                urljoin(self._config.base_url, _QUALIFICATION_SCOPE_PATH),
                json={
                    "run_id": _profile_run_id(
                        self._config.qualification_run_id, profile_name
                    ),
                    "profile": profile_name,
                },
                headers=headers,
                timeout=10.0,
                allow_redirects=False,
            )
            with response:
                payload = response.json() if response.status_code == 201 else None
            if not isinstance(payload, dict):
                raise FleetRunRefused("durable qualification scope is unavailable")
            scope_id = uuid.UUID(str(payload.get("scope_id")))
            if (
                payload.get("profile") != profile_name
                or payload.get("run_id")
                != _profile_run_id(self._config.qualification_run_id, profile_name)
                or not re.fullmatch(
                    r"[0-9a-f]{12}-staging",
                    str(payload.get("app_release_id", "")),
                )
                or not payload.get("window_started_at")
                or not payload.get("expires_at")
            ):
                raise ValueError
            return payload | {"scope_id": scope_id}
        except (TypeError, ValueError, KeyError):
            raise FleetRunRefused("durable qualification scope is invalid") from None
        finally:
            session.close()

    def collect(self, scope_id: uuid.UUID) -> DurableQualificationEvidence:
        session = self._session()
        try:
            response = session.post(
                urljoin(self._config.base_url, _QUALIFICATION_EVIDENCE_PATH),
                json={"scope_id": str(scope_id)},
                headers=self._headers() | {"X-Admin-Token": self._config.admin_token},
                timeout=10.0,
                allow_redirects=False,
            )
            with response:
                if response.status_code != 200:
                    raise FleetRunRefused(
                        "durable qualification evidence is unavailable"
                    )
                try:
                    return DurableQualificationEvidence.model_validate(response.json())
                except (ValueError, TypeError):
                    raise FleetRunRefused(
                        "durable qualification evidence is invalid"
                    ) from None
        finally:
            session.close()

    def teardown(self, scope_id: uuid.UUID) -> Mapping[str, object]:
        """Evict and close only the exact server-issued qualification cohort."""
        session = self._session()
        try:
            response = session.post(
                urljoin(
                    self._config.base_url,
                    f"{_QUALIFICATION_SCOPE_PATH}/{scope_id}/teardown",
                ),
                headers=self._headers() | {"X-Admin-Token": self._config.admin_token},
                timeout=DURABLE_QUALIFICATION_TEARDOWN_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            with response:
                payload = response.json() if response.status_code == 200 else None
            if not isinstance(payload, dict):
                raise FleetRunRefused("qualification scope teardown failed")
            expected = payload.get("expected_tool_turns")
            if (
                expected not in {0, 16}
                or payload.get("targeted_sessions") != expected
                or payload.get("closed_intervals") != expected
                or payload.get("eviction_events") != expected
                or payload.get("source") != "exact_scope_canonical_eviction"
            ):
                raise FleetRunRefused("qualification scope teardown is incomplete")
            return payload
        finally:
            session.close()

    def cleanup(self, scope_id: uuid.UUID) -> None:
        session = self._session()
        try:
            response = session.delete(
                urljoin(
                    self._config.base_url,
                    f"{_QUALIFICATION_SCOPE_PATH}/{scope_id}",
                ),
                headers=self._headers() | {"X-Admin-Token": self._config.admin_token},
                timeout=10.0,
                allow_redirects=False,
            )
            with response:
                if response.status_code != 204:
                    raise FleetRunRefused("qualification scope cleanup failed")
        finally:
            session.close()


def create_live_durable_transport(
    config: DurableChatTransportConfig,
    scope_id: uuid.UUID,
) -> HttpSSEDurableChatTransport:
    """Construct the only transport accepted by guarded live qualification."""
    if not config.admin_token or not config.qualification_run_id:
        raise FleetRunRefused("live qualification credentials are incomplete")
    return HttpSSEDurableChatTransport(config, scope_id=scope_id)


__all__ = (
    "DurableChatTransportConfig",
    "HttpSSEDurableChatTransport",
    "HttpDurableQualificationEvidenceSource",
    "create_live_durable_transport",
)
