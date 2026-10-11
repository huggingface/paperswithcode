"""Shared provider-call lifecycle, exercised through the gateway endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

import backend.chat_gateway_app as gateway
from backend.config import Settings
from backend.services.chat_capability_service import CapabilityError
from backend.services.chat_openai_budget_service import (
    OpenAIBudgetExhausted,
    OpenAILimitExceeded,
)
from backend.services.chat_provider_gateway import lifecycle, openai_responses

REAL_ASYNC_CLIENT = httpx.AsyncClient

COMPLETED_STREAM = (
    b"event: response.created\n"
    b'data: {"type":"response.created","response":{"id":"resp_1"}}\n\n'
    b"event: response.output_text.delta\n"
    b'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n'
    b"event: response.completed\n"
    b'data: {"type":"response.completed","response":{"id":"resp_1",'
    b'"service_tier":"default","usage":{"input_tokens":10,'
    b'"input_tokens_details":{"cached_tokens":0},'
    b'"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0}}}}\n\n'
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "jwt_secret": "test-secret-not-for-production",
        "chat_openai_pricing_verified_at": "2026-09-20",
        "chat_openai_direct_enabled": True,
        "openai_api_key": "test-openai-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class Events(list):
    def names(self) -> list[str]:
        return [event[0] for event in self]


class FakeDB:
    def __init__(self, events: Events) -> None:
        self.events = events

    def commit(self) -> None:
        self.events.append(("commit",))

    def rollback(self) -> None:
        self.events.append(("rollback",))

    def close(self) -> None:
        self.events.append(("close",))

    def scalar(self, _query) -> None:
        return None


class FakeRequest:
    def __init__(self, events: Events, payload: bytes) -> None:
        self.events = events
        self.payload = payload
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        self.events.append(("request_body",))
        return self.payload


class FakeTrace:
    def __init__(self, events: Events) -> None:
        self.events = events

    def first_byte(self, elapsed_ms: int) -> None:
        self.events.append(("trace_first_byte",))

    def finish(self, **fields) -> None:
        self.events.append(("trace_finish", fields))


@pytest.fixture
def harness(monkeypatch):
    events = Events()
    settings = _settings()
    row = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        chat_session_id=uuid.uuid4(),
        owner_hash="owner-hash",
        agent_harness="pi",
        provider_mode="openai_funded",
        model=settings.chat_openai_luna_route,
        reasoning_effort="low",
        provider_requests=0,
        scopes=["model"],
    )
    state = SimpleNamespace(
        events=events,
        settings=settings,
        row=row,
        handler=lambda _request: httpx.Response(
            200, content=COMPLETED_STREAM, headers={"x-request-id": "req_1"}
        ),
        reserve_error=None,
        meter_error=None,
        settle_error=None,
    )

    class FakeCapabilityService:
        def __init__(self, _db) -> None:
            pass

        def meter_provider(self, capability, **_bounds) -> None:
            if state.meter_error is not None:
                raise state.meter_error
            capability.provider_requests += 1
            events.append(("meter",))

    class FakeBudgetService:
        def __init__(self, _db, _settings) -> None:
            pass

        def reserve_call(self, **fields):
            events.append(("reserve", fields))
            if state.reserve_error is not None:
                raise state.reserve_error
            return SimpleNamespace(reserved_microusd=1234)

        def mark_dispatched(self, call_id) -> None:
            events.append(("mark_dispatched", call_id))

        def mark_cost_unknown(self, call_id, **fields) -> None:
            events.append(("mark_cost_unknown", call_id, fields))

        def settle_call(self, call_id, usage, **fields) -> None:
            if state.settle_error is not None:
                raise state.settle_error
            events.append(("settle", call_id, usage, fields))

    @contextlib.contextmanager
    def session_local():
        yield FakeDB(Events())

    def client_factory(**kwargs):
        events.append(("client",))

        def handle(request: httpx.Request) -> httpx.Response:
            events.append(("send", request))
            return state.handler(request)

        return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handle), **kwargs)

    def start_trace(**fields):
        events.append(("trace_start", fields))
        return FakeTrace(events)

    def record_timing(_settings, _turn_id, *, phase=None, elapsed_ms=None, **kw):
        events.append(("timing", phase or "received"))

    monkeypatch.setattr(gateway, "_scope", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(gateway, "_capability_owner", lambda *_args: "owner-1")
    monkeypatch.setattr(lifecycle, "ChatCapabilityService", FakeCapabilityService)
    monkeypatch.setattr(openai_responses, "ChatOpenAIBudgetService", FakeBudgetService)
    monkeypatch.setattr(openai_responses, "actual_usage_microusd", lambda *_a: 42)
    monkeypatch.setattr(
        openai_responses, "db_manager", SimpleNamespace(session_local=session_local)
    )
    monkeypatch.setattr(lifecycle.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(lifecycle, "start_provider_request_trace", start_trace)
    monkeypatch.setattr(lifecycle, "record_gateway_timing", record_timing)
    monkeypatch.setattr(
        lifecycle,
        "record_provider_error",
        lambda capability_id, code: events.append(("provider_error", code)),
    )
    return state


def _responses_body(**overrides) -> bytes:
    payload = {
        "model": "gpt-5.6-luna",
        "input": [{"role": "user", "content": "hello"}],
        "max_output_tokens": 100,
        "tools": [{"type": "function", "name": "search"}],
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def _call_responses(state, payload: bytes | None = None):
    async def call():
        return await gateway.responses(
            FakeRequest(state.events, payload or _responses_body()),
            "Bearer capability",
            str(state.row.chat_session_id),
            str(state.row.turn_id),
            None,
            FakeDB(state.events),
            state.settings,
        )

    return call


def _drain(state, payload: bytes | None = None) -> tuple[int, bytes]:
    async def run():
        response = await _call_responses(state, payload)()
        body = b"".join([chunk async for chunk in response.body_iterator])
        return response, body

    response, body = asyncio.run(run())
    return response.status_code, body


def _first(events: Events, name: str):
    return next(event for event in events if event[0] == name)


def test_responses_success_meters_reserves_streams_settles_and_traces(harness):
    status, body = _drain(harness)

    assert status == 200
    assert body == COMPLETED_STREAM
    names = harness.events.names()
    # The ambiguous-dispatch boundary is durable before any provider bytes,
    # and the request session is released before the upstream connection.
    assert names.index("meter") < names.index("reserve")
    assert names.index("reserve") < names.index("mark_dispatched")
    assert names.index("mark_dispatched") < names.index("close")
    assert names.index("close") < names.index("client") < names.index("send")
    assert names[names.index("mark_dispatched") + 1] == "commit"
    reserve = _first(harness.events, "reserve")[1]
    assert reserve["call_sequence"] == 1
    assert reserve["owner_id"] == "owner-1"
    assert reserve["turn_id"] == harness.row.turn_id
    assert reserve["call_id"] == uuid.uuid5(harness.row.id, "openai-provider-call:1")
    send = _first(harness.events, "send")[1]
    assert str(send.url) == "https://api.openai.com/v1/responses"
    assert send.headers["authorization"] == "Bearer test-openai-key"
    assert send.headers["accept"] == "text/event-stream"
    trace = _first(harness.events, "trace_start")[1]
    assert trace["accounting_call_id"] == str(reserve["call_id"])
    assert trace["reserved_microusd"] == 1234
    assert trace["routing_policy"] == "direct"
    assert trace["offered_tool_names"] == ["search"]
    _, call_id, usage, fields = _first(harness.events, "settle")
    assert call_id == reserve["call_id"]
    assert usage.outcome == "completed"
    assert fields["provider_request_id"] == "req_1"
    assert fields["error_code"] is None
    assert fields["ttft_ms"] is not None
    finish = _first(harness.events, "trace_finish")[1]
    assert finish["error_code"] is None
    assert finish["status_code"] == 200
    assert finish["usage"].cost_microusd == 42
    assert "provider_error" not in names


def test_responses_records_gateway_entry_before_body_and_headers_after_send(harness):
    _drain(harness)

    timings = [event for event in harness.events if event[0] in {"timing", "send"}]
    names = harness.events.names()
    assert names.index("timing") < names.index("request_body")
    assert [event[1] if event[0] == "timing" else "send" for event in timings] == [
        "received",
        "send",
        "upstream_response_headers",
        "upstream_first_body_byte",
    ]


def test_responses_provider_rejection_settles_failed_usage_without_streaming(harness):
    harness.handler = lambda _request: httpx.Response(
        429,
        content=b'{"error":{"type":"rate_limit_error"}}',
        headers={"x-request-id": "req_rejected"},
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 429
    assert error.value.detail == {
        "code": "openai_rate_limited",
        "message": "Direct OpenAI request failed.",
    }
    assert ("provider_error", "openai_rate_limited") in harness.events
    _, _, usage, fields = _first(harness.events, "settle")
    assert usage.outcome == "failed"
    assert usage.cost_microusd == 0
    assert fields["provider_request_id"] == "req_rejected"
    assert fields["error_code"] == "openai_rate_limited"
    finish = _first(harness.events, "trace_finish")[1]
    assert finish["status_code"] == 429
    assert finish["tool_call_returned"] is False


def test_responses_transport_failure_marks_cost_unknown_not_settled(harness):
    def fail(_request):
        raise httpx.ConnectError("unreachable")

    harness.handler = fail

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 502
    assert error.value.detail == {
        "code": "openai_unavailable",
        "message": "Direct OpenAI is unavailable.",
    }
    names = harness.events.names()
    assert "settle" not in names
    _, call_id, fields = _first(harness.events, "mark_cost_unknown")
    assert call_id == _first(harness.events, "reserve")[1]["call_id"]
    assert fields == {"error_code": "openai_unavailable"}
    assert names.index("mark_dispatched") < names.index("mark_cost_unknown")
    assert ("provider_error", "openai_unavailable") in harness.events
    finish = _first(harness.events, "trace_finish")[1]
    assert finish["status_code"] is None
    assert finish["error_code"] == "openai_unavailable"


def test_responses_cancellation_settles_the_partial_stream_as_cancelled(harness):
    async def cancel_after_first_chunk():
        response = await _call_responses(harness)()
        iterator = response.body_iterator
        await iterator.__anext__()
        await iterator.aclose()

    harness.handler = lambda _request: httpx.Response(
        200,
        stream=httpx.ByteStream(
            COMPLETED_STREAM.split(b"event: response.completed")[0]
        ),
    )

    asyncio.run(cancel_after_first_chunk())

    _, _, usage, fields = _first(harness.events, "settle")
    assert usage.outcome is None
    assert fields["error_code"] == "openai_stream_cancelled"
    finish = _first(harness.events, "trace_finish")[1]
    assert finish["error_code"] == "openai_stream_cancelled"


def test_responses_settlement_failure_still_finishes_the_trace(harness, caplog):
    harness.settle_error = RuntimeError("database unavailable")

    status, _ = _drain(harness)

    assert status == 200
    finish = _first(harness.events, "trace_finish")[1]
    assert finish["usage"].outcome == "completed"
    assert "openai stream settlement failed" in caplog.text


def test_responses_budget_rejection_rolls_back_without_dispatch(harness):
    harness.reserve_error = OpenAIBudgetExhausted("exhausted")

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 429
    assert error.value.detail["code"] == "openai_budget_exhausted"
    names = harness.events.names()
    assert names[names.index("reserve") + 1] == "rollback"
    assert ("provider_error", "openai_budget_exhausted") in harness.events
    assert "mark_dispatched" not in names
    assert "client" not in names


def test_responses_rate_limit_reservation_sets_retry_after(harness):
    harness.reserve_error = OpenAILimitExceeded(
        "user_rate", datetime.now(UTC) + timedelta(seconds=30)
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 429
    assert error.value.detail["code"] == "openai_user_rate_limited"
    assert 1 <= int(error.value.headers["Retry-After"]) <= 30


def test_responses_turn_limit_rolls_back_before_reservation(harness):
    harness.meter_error = CapabilityError("limit")

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 429
    assert error.value.detail == "Model execution limit reached"
    assert "reserve" not in harness.events.names()


def test_responses_capability_profile_mismatch_is_rejected_before_metering(harness):
    harness.row.provider_mode = "openrouter_funded"

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 403
    assert "meter" not in harness.events.names()


def test_responses_unavailable_gateway_rejects_before_reading_the_body(harness):
    harness.settings = _settings(chat_openai_direct_enabled=False)

    with pytest.raises(HTTPException) as error:
        asyncio.run(_call_responses(harness)())

    assert error.value.status_code == 503
    assert harness.events == []
