"""One capability-bound provider model call, independent of its wire protocol.

The lifecycle owns every step whose correctness does not depend on the
protocol: capability authorization, turn metering, budget reservation and the
ambiguous-dispatch boundary, upstream transport, streaming, tracing, and
settlement. A protocol adapter supplies the narrow pieces that do differ:
request normalization, upstream headers, usage extraction, provider error
mapping, and response framing.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import anyio
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.chat_execution_policy import (
    MAX_POSTER_PROVIDER_REQUESTS,
    MAX_PROVIDER_REQUESTS,
    MAX_PROVIDER_TURN_TOKENS,
)
from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatMessageRecord,
    ChatQualificationScope,
    ChatTurnCapability,
    ChatTurnLatency,
)
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
)
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_openai_budget_service import (
    MAX_REQUEST_BYTES as MAX_OPENAI_REQUEST_BYTES,
)
from backend.services.chat_tracing_service import start_provider_request_trace
from backend.services.durable_external_qualification_contract import (
    DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN,
)

# Operational log lines keep the gateway's logger name.
logger = logging.getLogger("backend.chat_gateway_app")

MAX_PROVIDER_OUTPUT_TOKENS = PROVIDER_OUTPUT_TOKEN_LIMIT
MAX_POSTER_PROVIDER_TURN_TOKENS = 8_000_000
QUALIFICATION_PROVIDER_REQUESTS = DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN
QUALIFICATION_PROVIDER_TURN_TOKENS = QUALIFICATION_PROVIDER_REQUESTS * (
    MAX_OPENAI_REQUEST_BYTES // 4 + MAX_PROVIDER_OUTPUT_TOKENS
)


def opaque_turn(turn_id: uuid.UUID) -> str:
    return hashlib.sha256(str(turn_id).encode()).hexdigest()[:12]


def output_tokens_allowed(value: int) -> bool:
    return 1 <= value <= MAX_PROVIDER_OUTPUT_TOKENS


def record_gateway_timing(
    settings: Settings,
    turn_id: uuid.UUID,
    *,
    phase: str | None = None,
    elapsed_ms: int | None = None,
    received_at: datetime | None = None,
) -> None:
    if settings.environment != "staging":
        return
    try:
        with db_manager.session_local() as timing_db:
            service = ChatLatencyService(timing_db)
            if received_at is not None:
                service.record_gateway_received(turn_id, received_at)
            elif phase is not None and elapsed_ms is not None:
                service.record_phase_for_turn(turn_id, phase, elapsed_ms)
            timing_db.commit()
    except Exception as error:
        logger.warning(
            "chat gateway latency persistence failed turn=%s phase=%s error=%s",
            opaque_turn(turn_id),
            phase or "received",
            type(error).__name__,
        )


def record_provider_error(capability_id: uuid.UUID, code: str) -> None:
    with db_manager.session_local() as error_db:
        row = error_db.get(ChatTurnCapability, capability_id)
        if row is not None:
            ChatCapabilityService(error_db).record_provider_error(row, code)
            error_db.commit()


def qualification_scope_claim(
    row: ChatTurnCapability, db: Session, settings: Settings
) -> uuid.UUID | None:
    if settings.environment != "staging":
        return None
    return db.scalar(
        select(ChatQualificationScope.id)
        .join(
            ChatTurnLatency,
            ChatTurnLatency.qualification_scope_id == ChatQualificationScope.id,
        )
        .where(
            ChatTurnLatency.turn_id == row.turn_id,
            ChatTurnLatency.qualification_profile == "32-functional-turns",
            ChatQualificationScope.profile == "32-functional-turns",
            ChatQualificationScope.window_ended_at.is_(None),
            ChatQualificationScope.expires_at > datetime.now(UTC),
        )
    )


def provider_turn_limits(
    row: ChatTurnCapability,
    db: Session | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    qualification_scope_id = (
        qualification_scope_claim(row, db, settings)
        if db is not None and settings is not None
        else None
    )
    if qualification_scope_id is not None:
        return QUALIFICATION_PROVIDER_REQUESTS, QUALIFICATION_PROVIDER_TURN_TOKENS
    if {"artifact", "paper_grant"} & set(getattr(row, "scopes", ())):
        return MAX_POSTER_PROVIDER_REQUESTS, MAX_POSTER_PROVIDER_TURN_TOKENS
    return MAX_PROVIDER_REQUESTS, MAX_PROVIDER_TURN_TOKENS


def offered_tool_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        names: list[str] = []
    else:
        names = sorted(
            str(tool["name"])
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        )
    return {
        "offered_tool_count": len(names),
        "offered_tool_names": names,
        "offered_tool_digest": hashlib.sha256(",".join(names).encode()).hexdigest(),
    }


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def close_upstream(upstream: Any, client: Any) -> None:
    """Close the upstream stream even inside an already-cancelled scope."""

    with anyio.CancelScope(shield=True):
        await upstream.aclose()
        await client.aclose()


class ProviderReservationRejected(Exception):
    """A ledger refused to reserve budget; nothing was dispatched."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        detail: Any | Callable[[], Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

    def http_error(self) -> HTTPException:
        # Some details read accounting state, which is only valid after the
        # failed reservation has been rolled back.
        detail = self.detail() if callable(self.detail) else self.detail
        return HTTPException(
            status_code=self.status_code, detail=detail, headers=self.headers
        )


@dataclass(frozen=True, slots=True)
class ProviderError:
    """A provider failure mapped onto the gateway's public error contract."""

    code: str
    error: HTTPException
    usage: Any = None
    record: bool = True


class UsageStream(Protocol):
    saw_token_delta: bool
    saw_tool_call: bool

    def feed(self, chunk: bytes) -> None: ...

    def result(self) -> Any: ...


class ProviderLedger(Protocol):
    """Accounting for one provider call across its dispatch boundaries."""

    name: str
    call_id: uuid.UUID | None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        """Reserve the bounded maximum in ``db``; the lifecycle commits."""

    def mark_dispatched(self, db: Session) -> None:
        """Mark the ambiguous-dispatch boundary in ``db``; the lifecycle commits."""

    def trace_accounting(self) -> dict[str, Any]: ...

    def mark_unknown(self, error_code: str) -> None:
        """Bytes may have reached the provider, but no response arrived."""

    def settle_rejected(
        self,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None: ...

    def record_ttft(self, elapsed_ms: int) -> None: ...

    def settle(
        self,
        usage: UsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> Any:
        """Settle the call and return the usage to record on its trace."""


@dataclass(frozen=True, slots=True)
class ParsedProviderRequest:
    payload: Any
    capability_model: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedProviderCall:
    """A normalized request that is ready for metering and dispatch."""

    payload: dict[str, Any]
    raw: bytes
    maximum_tokens: int
    owner_id: str
    url: str
    credential: str
    ledger: ProviderLedger
    trace_fields: dict[str, Any]
    bill_to: str | None = None
    stream: bool = True


class ProviderProtocol(Protocol):
    """The protocol-specific hooks of one provider endpoint."""

    receipt_phase: Literal["entry", "dispatch"]
    transport_error_code: str

    def check_available(self) -> None: ...

    def parse(self, raw: bytes) -> ParsedProviderRequest:
        """Bound and decode the untrusted request before authorization."""

    def observe_rejection(self, phase: str) -> None: ...

    def prepare(
        self,
        parsed: ParsedProviderRequest,
        row: ChatTurnCapability,
        db: Session,
        owner: Callable[[], str],
    ) -> PreparedProviderCall:
        """Normalize the request against the validated capability."""

    def upstream_headers(
        self, request: Request, call: PreparedProviderCall
    ) -> dict[str, str]: ...

    def usage_extractor(self) -> UsageStream: ...

    def provider_request_id(self, upstream: httpx.Response) -> str | None: ...

    def transport_failure(self) -> ProviderError: ...

    async def map_provider_status(
        self, upstream: httpx.Response
    ) -> ProviderError | None:
        """Return a rejection for upstream failures that are not relayed."""

    def stream_error_code(
        self, usage: UsageStream, status_code: int, *, cancelled: bool
    ) -> str | None: ...

    def response_headers(self, upstream: httpx.Response) -> dict[str, str]: ...


@dataclass(slots=True)
class ProviderCallLifecycle:
    """Run one provider call through authorization, accounting, and transport."""

    db: Session
    settings: Settings
    authenticate: Callable[[], str]
    authorize: Callable[[str, str | None], ChatTurnCapability]
    owner: Callable[[ChatTurnCapability], str]
    started: float = field(default_factory=time.perf_counter)

    async def run(
        self,
        protocol: ProviderProtocol,
        request: Request,
        turn: str,
    ) -> StreamingResponse:
        settings = self.settings
        protocol.check_available()
        try:
            turn_id = uuid.UUID(turn)
        except ValueError:
            raise HTTPException(status_code=403, detail="Capability rejected") from None
        received_at = datetime.now(UTC)
        if protocol.receipt_phase == "entry":
            record_gateway_timing(settings, turn_id, received_at=received_at)
        token = self.authenticate()
        parsed = protocol.parse(await request.body())
        try:
            row = self.authorize(token, parsed.capability_model)
        except HTTPException:
            protocol.observe_rejection("capability_scope")
            raise
        call = protocol.prepare(parsed, row, self.db, lambda: self.owner(row))
        capability_id = row.id
        call_sequence, trace_id = self._meter(row, turn_id, call)
        ledger = call.ledger
        await self._reserve(ledger, capability_id, turn_id, call_sequence)
        if protocol.receipt_phase == "dispatch":
            record_gateway_timing(settings, turn_id, received_at=received_at)
        # Persist the ambiguous-dispatch boundary before any network bytes can
        # reach the provider. A crash after this point retains the full bound.
        ledger.mark_dispatched(self.db)
        self.db.commit()
        inventory = offered_tool_inventory(call.payload)
        provider_trace = start_provider_request_trace(
            settings=settings,
            trace_id=trace_id,
            turn_id=str(turn_id),
            call_sequence=call_sequence,
            **call.trace_fields,
            **ledger.trace_accounting(),
            offered_tool_count=inventory["offered_tool_count"],
            offered_tool_names=inventory["offered_tool_names"],
            offered_tool_digest=inventory["offered_tool_digest"],
        )
        # A FastAPI yield dependency otherwise retains this connection until the
        # StreamingResponse finishes. At fleet concurrency that exhausts the pool
        # while the gateway is merely waiting on the provider, blocking sibling
        # calls. All subsequent accounting uses its own short-lived session.
        self.db.close()
        client = httpx.AsyncClient(timeout=180, follow_redirects=False)
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    call.url,
                    content=call.raw,
                    headers=protocol.upstream_headers(request, call),
                ),
                stream=True,
            )
        except httpx.HTTPError:
            await client.aclose()
            ledger.mark_unknown(protocol.transport_error_code)
            failure = protocol.transport_failure()
            if failure.record:
                record_provider_error(capability_id, failure.code)
            provider_trace.finish(
                usage=protocol.usage_extractor().result(),
                status_code=None,
                error_code=failure.code,
                tool_call_returned=False,
            )
            raise failure.error from None
        record_gateway_timing(
            settings,
            turn_id,
            phase="upstream_response_headers",
            elapsed_ms=_elapsed_ms(self.started),
        )

        request_id = protocol.provider_request_id(upstream)
        rejection = await protocol.map_provider_status(upstream)
        if rejection is not None:
            await upstream.aclose()
            await client.aclose()
            record_provider_error(capability_id, rejection.code)
            ledger.settle_rejected(
                rejection,
                provider_request_id=request_id,
                latency_ms=_elapsed_ms(self.started),
            )
            provider_trace.finish(
                usage=rejection.usage,
                status_code=upstream.status_code,
                error_code=rejection.code,
                tool_call_returned=False,
            )
            raise rejection.error

        usage = protocol.usage_extractor()

        async def chunks():
            first_body_byte_ms: int | None = None
            ttft_ms: int | None = None
            cancelled = False
            try:
                async for chunk in upstream.aiter_bytes():
                    usage.feed(chunk)
                    elapsed_ms = _elapsed_ms(self.started)
                    if first_body_byte_ms is None:
                        first_body_byte_ms = elapsed_ms
                        record_gateway_timing(
                            settings,
                            turn_id,
                            phase="upstream_first_body_byte",
                            elapsed_ms=first_body_byte_ms,
                        )
                    if ttft_ms is None and usage.saw_token_delta:
                        ttft_ms = elapsed_ms
                        provider_trace.first_byte(ttft_ms)
                        ledger.record_ttft(ttft_ms)
                    yield chunk
            except (asyncio.CancelledError, GeneratorExit):
                cancelled = True
                raise
            finally:
                await close_upstream(upstream, client)
                error_code = protocol.stream_error_code(
                    usage, upstream.status_code, cancelled=cancelled
                )
                trace_usage = self._settle(
                    ledger,
                    usage,
                    phase="stream",
                    provider_request_id=request_id,
                    ttft_ms=ttft_ms,
                    error_code=error_code,
                )
                provider_trace.finish(
                    usage=trace_usage,
                    status_code=upstream.status_code,
                    error_code=error_code,
                    tool_call_returned=usage.saw_tool_call,
                )

        return StreamingResponse(
            chunks(),
            status_code=upstream.status_code,
            headers=protocol.response_headers(upstream),
        )

    def _meter(
        self,
        row: ChatTurnCapability,
        turn_id: uuid.UUID,
        call: PreparedProviderCall,
    ) -> tuple[int, str | None]:
        db = self.db
        try:
            maximum_requests, maximum_turn_tokens = provider_turn_limits(
                row, db, self.settings
            )
            ChatCapabilityService(db).meter_provider(
                row,
                request_tokens=max(1, len(call.raw) // 4) + call.maximum_tokens,
                maximum_requests=maximum_requests,
                maximum_tokens=maximum_turn_tokens,
            )
            call_sequence = row.provider_requests
            trace_id = (
                db.scalar(
                    select(ChatMessageRecord.langfuse_trace_id)
                    .where(
                        ChatMessageRecord.turn_id == turn_id,
                        ChatMessageRecord.role == "user",
                    )
                    .order_by(ChatMessageRecord.sequence.desc())
                    .limit(1)
                )
                if hasattr(db, "scalar")
                else None
            )
            # Capability validation takes a row lock so concurrent SDK model
            # calls receive distinct request counters. Land that bounded
            # mutation before any provider network check; otherwise a slow
            # budget lookup holds the lock and blocks the other model call.
            db.commit()
        except CapabilityError:
            db.rollback()
            raise HTTPException(
                status_code=429, detail="Model execution limit reached"
            ) from None
        return call_sequence, trace_id

    async def _reserve(
        self,
        ledger: ProviderLedger,
        capability_id: uuid.UUID,
        turn_id: uuid.UUID,
        call_sequence: int,
    ) -> None:
        try:
            await ledger.reserve(self.db, turn_id=turn_id, call_sequence=call_sequence)
            self.db.commit()
        except ProviderReservationRejected as rejected:
            self.db.rollback()
            record_provider_error(capability_id, rejected.code)
            raise rejected.http_error() from None

    def _settle(
        self,
        ledger: ProviderLedger,
        usage: UsageStream,
        *,
        phase: str,
        provider_request_id: str | None,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> Any:
        try:
            return ledger.settle(
                usage,
                provider_request_id=provider_request_id,
                latency_ms=_elapsed_ms(self.started),
                ttft_ms=ttft_ms,
                error_code=error_code,
            )
        except Exception as error:
            logger.error(
                "%s %s settlement failed call=%s error=%s",
                ledger.name,
                phase,
                ledger.call_id,
                type(error).__name__,
            )
            return usage.result()
