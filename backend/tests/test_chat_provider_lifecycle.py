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
from backend.services.openrouter_user_budget_service import opaque_owner

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


# Anthropic Messages parity across provider modes.

MESSAGES_STREAM = (
    b"event: message_start\n"
    b'data: {"type":"message_start","message":{"id":"msg_1"}}\n\n'
    b"event: content_block_start\n"
    b'data: {"type":"content_block_start","content_block":{"type":"tool_use",'
    b'"name":"search"}}\n\n'
    b"event: message_delta\n"
    b'data: {"type":"message_delta","usage":{"output_tokens":3,"cost":0.0001}}\n\n'
)
MESSAGES_BODY = (
    b'{"id":"gen-1","type":"message","content":[{"type":"text","text":"hi"}],'
    b'"usage":{"input_tokens":5,"output_tokens":2,"cost":0.0002}}'
)


def _route_for(settings: Settings, provider: str) -> str:
    return next(
        route
        for route, routed in settings.chat_route_providers.items()
        if routed == provider
    )


@pytest.fixture
def messages_harness(monkeypatch):
    events = Events()
    settings = _settings(
        chat_openrouter_server_funded_enabled=True,
        chat_openrouter_api_key="test-openrouter-key",
        chat_initial_payload_optimization_enabled=False,
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        chat_session_id=uuid.uuid4(),
        owner_hash="owner-hash",
        agent_harness="pi",
        provider_mode="openrouter_funded",
        model=_route_for(settings, "openrouter"),
        reasoning_effort="high",
        provider_requests=0,
        scopes=["model"],
        provider_credential_revision=None,
    )
    state = SimpleNamespace(
        events=events,
        settings=settings,
        row=row,
        status=200,
        content=MESSAGES_STREAM,
        headers={"content-type": "text/event-stream", "request-id": "req_m"},
        transport_error=False,
    )

    class FakeCapabilityService:
        def __init__(self, _db) -> None:
            pass

        def meter_provider(self, capability, **_bounds) -> None:
            capability.provider_requests += 1
            events.append(("meter",))

        def record_provider_error(self, _capability, code) -> None:
            events.append(("provider_error", code))

    class FakeOpenRouterBudget:
        def __init__(self, _db, _settings) -> None:
            pass

        def reserve_call(self, owner_id, turn_id, call_id, sequence, model, *a, **k):
            events.append(("reserve", call_id))

        def mark_dispatched(self, call_id) -> None:
            events.append(("mark_dispatched", call_id))

        def mark_cost_unknown(self, call_id, *_args) -> None:
            events.append(("mark_cost_unknown", call_id))

        def settle_call(self, call_id, cost, generation_id) -> None:
            events.append(("settle", call_id, cost))

    class FakeBYOK:
        def __init__(self, _db, _settings) -> None:
            pass

        def invalidate_auth_failure(self, owner_id) -> None:
            events.append(("byok_invalidated", owner_id))

    class AccountingDB(FakeDB):
        def get(self, _model, _id):
            return SimpleNamespace(provider_ttft_ms=None)

    @contextlib.contextmanager
    def session_local():
        yield AccountingDB(Events())

    def client_factory(**kwargs):
        events.append(("client",))

        def handle(request: httpx.Request) -> httpx.Response:
            events.append(("send", request))
            if state.transport_error:
                raise httpx.ConnectError("unreachable")
            return httpx.Response(
                state.status, content=state.content, headers=state.headers
            )

        return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handle), **kwargs)

    async def allow_budget(_settings) -> None:
        events.append(("budget_check",))

    def start_trace(**fields):
        events.append(("trace_start", fields))
        return FakeTrace(events)

    def record_ttft(call_id, elapsed_ms) -> None:
        events.append(("ttft", call_id))

    from backend.services.chat_provider_gateway import anthropic_messages

    monkeypatch.setattr(gateway, "_scope", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(gateway, "_capability_owner", lambda *_args: "owner-1")
    monkeypatch.setattr(lifecycle, "ChatCapabilityService", FakeCapabilityService)
    monkeypatch.setattr(
        anthropic_messages, "ChatCapabilityService", FakeCapabilityService
    )
    monkeypatch.setattr(
        anthropic_messages, "OpenRouterUserBudgetService", FakeOpenRouterBudget
    )
    monkeypatch.setattr(anthropic_messages, "OpenRouterBYOKService", FakeBYOK)
    monkeypatch.setattr(anthropic_messages, "require_openrouter_budget", allow_budget)
    monkeypatch.setattr(anthropic_messages, "record_provider_ttft", record_ttft)
    monkeypatch.setattr(
        anthropic_messages,
        "db_manager",
        SimpleNamespace(session_local=session_local),
    )
    monkeypatch.setattr(
        anthropic_messages,
        "user_provider_credential",
        lambda *_args: SimpleNamespace(token="hf-user-token", bill_to="acme"),
    )
    monkeypatch.setattr(lifecycle.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(lifecycle, "start_provider_request_trace", start_trace)
    monkeypatch.setattr(
        lifecycle, "record_gateway_timing", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        lifecycle,
        "record_provider_error",
        lambda capability_id, code: events.append(("provider_error", code)),
    )
    return state


def _call_messages(state, *, stream: bool):
    payload = json.dumps(
        {
            "model": state.row.model,
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": stream,
        }
    ).encode()

    async def call():
        response = await gateway.messages(
            FakeRequest(state.events, payload),
            "Bearer capability",
            str(state.row.chat_session_id),
            str(state.row.turn_id),
            None,
            FakeDB(state.events),
            state.settings,
        )
        if hasattr(response, "body_iterator"):
            body = b"".join([chunk async for chunk in response.body_iterator])
        else:
            body = response.body
        return response, body

    return asyncio.run(call())


PROVIDER_MODES = {
    "huggingface": (
        "https://router.huggingface.co/v1/messages",
        "Bearer hf-user-token",
    ),
    "openrouter_funded": (
        "https://openrouter.ai/api/v1/messages",
        "Bearer test-openrouter-key",
    ),
    "openrouter_byok": (
        "https://openrouter.ai/api/v1/messages",
        "Bearer byok-user-token",
    ),
}


@pytest.fixture
def provider_mode(request, messages_harness, monkeypatch):
    mode = request.param
    state = messages_harness
    if mode == "huggingface":
        state.row.model = _route_for(state.settings, "huggingface")
        state.row.provider_mode = "huggingface"
    elif mode == "openrouter_byok":
        from backend.services.chat_provider_gateway import anthropic_messages

        state.row.provider_mode = "openrouter_byok"
        original = anthropic_messages.provider_target
        monkeypatch.setattr(
            anthropic_messages,
            "provider_target",
            lambda row, settings, db=None: (
                ("https://openrouter.ai/api/v1/messages", "byok-user-token", None)
                if row.provider_mode == "openrouter_byok"
                else original(row, settings, db)
            ),
        )
    return mode


@pytest.mark.parametrize("provider_mode", list(PROVIDER_MODES), indirect=True)
@pytest.mark.parametrize("stream", [True, False])
def test_messages_relays_every_provider_mode_through_the_lifecycle(
    messages_harness, provider_mode, stream
):
    state = messages_harness
    if not stream:
        state.content = MESSAGES_BODY
        state.headers = {"content-type": "application/json", "request-id": "req_m"}

    response, body = _call_messages(state, stream=stream)

    assert response.status_code == 200
    assert body == state.content
    assert response.headers["request-id"] == "req_m"
    url, authorization = PROVIDER_MODES[provider_mode]
    send = _first(state.events, "send")[1]
    assert str(send.url) == url
    assert send.headers["authorization"] == authorization
    assert send.headers["anthropic-version"] == "2023-06-01"
    sent = json.loads(send.content)
    names = state.events.names()
    funded = provider_mode == "openrouter_funded"
    assert ("reserve" in names) is funded
    assert ("settle" in names) is funded
    assert ("ttft" in names) is funded
    if provider_mode == "huggingface":
        assert send.headers["x-hf-bill-to"] == "acme"
        assert "reasoning" not in sent
    else:
        assert sent["reasoning"] == {
            "effort": "high",
            "exclude": not state.settings.chat_show_reasoning,
        }
        assert sent["user"] == opaque_owner("owner-1", state.settings)
        assert sent["provider"] == {"sort": "throughput"}
    if funded:
        call_id = uuid.uuid5(state.row.id, "provider-call:1")
        assert _first(state.events, "reserve")[1] == call_id
        assert names.index("budget_check") < names.index("reserve")
        assert names.index("mark_dispatched") < names.index("send")
    trace = _first(state.events, "trace_start")[1]
    assert trace["provider_mode"] == provider_mode
    assert "accounting_call_id" not in trace
    finish = _first(state.events, "trace_finish")[1]
    assert finish["error_code"] is None
    assert finish["tool_call_returned"] is stream
    # The Messages path keeps the request session for its whole lifetime.
    assert "close" not in names


def test_messages_byok_auth_failure_invalidates_the_credential_and_relays(
    messages_harness,
):
    state = messages_harness
    state.row.provider_mode = "openrouter_byok"
    from backend.services.chat_provider_gateway import anthropic_messages

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            anthropic_messages,
            "provider_target",
            lambda *_args: ("https://openrouter.ai/api/v1/messages", "byok", None),
        )
        state.status = 401
        state.content = b'{"error":{"message":"bad key"}}'
        state.headers = {"content-type": "application/json"}
        response, body = _call_messages(state, stream=False)

    assert response.status_code == 401
    assert body == state.content
    assert ("byok_invalidated", "owner-1") in state.events
    assert ("provider_error", "openrouter_byok_credential_invalid") in state.events
    finish = _first(state.events, "trace_finish")[1]
    assert finish["error_code"] == "provider_http_401"


@pytest.mark.parametrize(
    ("mode", "status", "code"),
    [
        ("openrouter_funded", 402, "openrouter_unavailable"),
        ("huggingface", 402, "hf_inference_billing_exhausted"),
    ],
)
def test_messages_records_provider_billing_errors_and_relays_them(
    messages_harness, mode, status, code
):
    state = messages_harness
    if mode == "huggingface":
        state.row.model = _route_for(state.settings, "huggingface")
        state.row.provider_mode = "huggingface"
    state.status = status
    state.content = b'{"error":{}}'

    response, body = _call_messages(state, stream=True)

    assert response.status_code == status
    assert body == state.content
    assert ("provider_error", code) in state.events


def test_messages_funded_transport_failure_marks_cost_unknown(messages_harness):
    state = messages_harness
    state.transport_error = True

    with pytest.raises(HTTPException) as error:
        _call_messages(state, stream=True)

    assert error.value.status_code == 502
    assert error.value.detail == "Model provider failed"
    names = state.events.names()
    assert names.index("mark_dispatched") < names.index("mark_cost_unknown")
    assert "settle" not in names
    assert "provider_error" not in names
    finish = _first(state.events, "trace_finish")[1]
    assert finish["error_code"] == "provider_transport_error"


def test_messages_funded_budget_outage_rejects_before_reservation(
    messages_harness, monkeypatch
):
    from backend.services.chat_provider_gateway import anthropic_messages
    from backend.services.openrouter_budget_service import (
        OpenRouterBudgetUnavailable,
    )

    async def unavailable(_settings):
        raise OpenRouterBudgetUnavailable("timeout")

    monkeypatch.setattr(anthropic_messages, "require_openrouter_budget", unavailable)

    with pytest.raises(HTTPException) as error:
        _call_messages(messages_harness, stream=True)

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "openrouter_unavailable"
    assert error.value.detail["byok_settings_available"] is True
    names = messages_harness.events.names()
    assert ("provider_error", "openrouter_unavailable") in messages_harness.events
    assert "reserve" not in names
    assert "client" not in names
