"""OpenAI Responses protocol adapter for the shared provider-call lifecycle."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatTurnCapability
from backend.services.chat_openai_budget_service import (
    MAX_REQUEST_BYTES as MAX_OPENAI_REQUEST_BYTES,
)
from backend.services.chat_openai_usage_extractor import (
    ExtractedOpenAIUsage,
    OpenAIResponsesUsageExtractor,
    classify_openai_error,
)
from backend.services.chat_provider_gateway.ledgers import (
    OpenAIResponsesLedger,
    openai_unavailable,
)
from backend.services.chat_provider_gateway.lifecycle import (
    ParsedProviderRequest,
    PreparedProviderCall,
    ProviderError,
    output_tokens_allowed,
    qualification_scope_claim,
)

logger = logging.getLogger("backend.chat_gateway_app")

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_RESPONSES_FIELDS = {
    "include",
    "input",
    "instructions",
    "max_output_tokens",
    "model",
    "parallel_tool_calls",
    "prompt_cache_key",
    "prompt_cache_options",
    "prompt_cache_retention",
    "reasoning",
    "service_tier",
    "store",
    "stream",
    "text",
    "tool_choice",
    "tools",
}
REQUEST_TOO_LARGE = "request_too_large: Model request is too large"
REASONING_EFFORT_ORDER = ("low", "medium", "high", "max")


def opaque_openai_identifier(kind: str, value: str, settings: Settings) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode(),
        f"openai:{kind}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"pwc_{digest[:48]}"


def granted_reasoning_effort(requested: object, granted: str) -> str:
    """Honor a worker's lower effort (recovery downgrade), never a higher one."""
    if (
        requested in REASONING_EFFORT_ORDER
        and granted in REASONING_EFFORT_ORDER
        and REASONING_EFFORT_ORDER.index(requested)
        < REASONING_EFFORT_ORDER.index(granted)
    ):
        return requested
    return granted


def trusted_openai_payload(
    payload: object,
    row: ChatTurnCapability,
    settings: Settings,
) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict) or not set(payload) <= OPENAI_RESPONSES_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid Responses request")
    provider_model = settings.chat_openai_model
    if payload.get("model") != provider_model:
        raise HTTPException(status_code=403, detail="Capability rejected")
    maximum_tokens = payload.get("max_output_tokens")
    if (
        not isinstance(maximum_tokens, int)
        or isinstance(maximum_tokens, bool)
        or not output_tokens_allowed(maximum_tokens)
    ):
        raise HTTPException(status_code=422, detail="max_output_tokens is out of range")
    include = payload.get("include")
    if include is not None and (
        not isinstance(include, list)
        or any(item != "reasoning.encrypted_content" for item in include)
    ):
        raise HTTPException(status_code=422, detail="Unsupported Responses include")
    reasoning = payload.get("reasoning")
    if reasoning is not None and not isinstance(reasoning, dict):
        raise HTTPException(status_code=422, detail="Invalid Responses reasoning")
    summary = reasoning.get("summary") if isinstance(reasoning, dict) else None
    if summary not in {None, "auto", "concise", "detailed"}:
        raise HTTPException(
            status_code=422, detail="Invalid Responses reasoning summary"
        )
    tools = payload.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict)
        or tool.get("type") != "function"
        or not isinstance(tool.get("name"), str)
        or not 1 <= len(tool["name"]) <= 64
        or not set(tool) <= {"type", "name", "description", "parameters", "strict"}
        for tool in tools
    ):
        raise HTTPException(status_code=422, detail="Unsupported Responses tool")
    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, str):
        if tool_choice not in {"auto", "none", "required"}:
            raise HTTPException(
                status_code=422, detail="Unsupported Responses tool choice"
            )
    elif tool_choice is not None and (
        not isinstance(tool_choice, dict)
        or tool_choice.get("type") != "function"
        or not isinstance(tool_choice.get("name"), str)
        or set(tool_choice) != {"type", "name"}
    ):
        raise HTTPException(status_code=422, detail="Unsupported Responses tool choice")
    trusted = dict(payload)
    trusted.pop("prompt_cache_options", None)
    trusted.pop("prompt_cache_retention", None)
    trusted["model"] = provider_model
    trusted["stream"] = True
    trusted["store"] = False
    trusted["service_tier"] = "default"
    trusted["include"] = ["reasoning.encrypted_content"]
    requested_effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    trusted["reasoning"] = {
        "effort": granted_reasoning_effort(requested_effort, row.reasoning_effort)
    }
    if summary is not None:
        trusted["reasoning"]["summary"] = summary
    trusted["safety_identifier"] = opaque_openai_identifier(
        "owner", row.owner_hash, settings
    )
    trusted["prompt_cache_key"] = opaque_openai_identifier(
        "session", str(row.chat_session_id), settings
    )
    return trusted, maximum_tokens


def safe_openai_request_id(value: str | None) -> str | None:
    if not value or not re.fullmatch(r"[A-Za-z0-9._:-]{1,255}", value):
        return None
    return value


def openai_stream_error_code(outcome: str | None, *, cancelled: bool) -> str | None:
    if outcome == "completed":
        return None
    if cancelled:
        return "openai_stream_cancelled"
    if outcome == "incomplete":
        return "openai_incomplete"
    return "openai_unavailable"


@dataclass(frozen=True, slots=True)
class OpenAIResponsesProtocol:
    """Capability-bound, stateless native OpenAI Responses streaming."""

    settings: Settings
    transport_error: ProviderError = field(
        default_factory=lambda: ProviderError(
            code="openai_unavailable",
            error=HTTPException(status_code=502, detail=openai_unavailable()),
        )
    )

    def check_available(self) -> None:
        if not self.settings.chat_openai_direct_enabled or not (
            self.settings.openai_api_key
        ):
            raise HTTPException(status_code=503, detail="Direct OpenAI is unavailable")

    def parse(self, raw: bytes) -> ParsedProviderRequest:
        if not raw or len(raw) > MAX_OPENAI_REQUEST_BYTES:
            self.observe_rejection("request_size")
            raise HTTPException(status_code=413, detail=REQUEST_TOO_LARGE)
        try:
            return ParsedProviderRequest(payload=json.loads(raw), raw=raw)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=422, detail="Invalid Responses request"
            ) from None

    def observe_rejection(self, phase: str) -> None:
        logger.warning("chat OpenAI gateway rejected phase=%s", phase)

    def prepare(
        self,
        parsed: ParsedProviderRequest,
        row: ChatTurnCapability,
        db: Session,
        owner: Callable[[], str],
        *,
        turn_id: uuid.UUID,
    ) -> PreparedProviderCall:
        del turn_id
        settings = self.settings
        if (
            row.agent_harness != "pi"
            or row.provider_mode != "openai_funded"
            or row.model != settings.chat_openai_luna_route
        ):
            self.observe_rejection("capability_profile")
            raise HTTPException(status_code=403, detail="Capability rejected")
        try:
            payload, maximum_tokens = trusted_openai_payload(
                parsed.payload, row, settings
            )
        except HTTPException:
            self.observe_rejection("request_contract")
            raise
        reasoning_effort = payload["reasoning"]["effort"]
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > MAX_OPENAI_REQUEST_BYTES:
            self.observe_rejection("trusted_request_size")
            raise HTTPException(status_code=413, detail=REQUEST_TOO_LARGE)
        owner_id = owner()
        return PreparedProviderCall(
            payload=payload,
            raw=raw,
            maximum_tokens=maximum_tokens,
            capability_id=row.id,
            owner_id=owner_id,
            provider_mode="openai_funded",
            url=OPENAI_RESPONSES_URL,
            credential=settings.openai_api_key,
            ledger=OpenAIResponsesLedger(
                settings=settings,
                capability_id=row.id,
                owner_id=owner_id,
                public_model_id=row.model,
                reasoning_effort=reasoning_effort,
                request_bytes=len(raw),
                maximum_output_tokens=maximum_tokens,
                qualification_scope_id=qualification_scope_claim(row, db, settings),
            ),
            trace_fields={
                "model": settings.chat_openai_model,
                "public_model_id": row.model,
                "provider_mode": "openai_funded",
                "reasoning_effort": reasoning_effort,
                "routing_policy": "direct",
                "service_tier": "default",
            },
        )

    def upstream_headers(
        self, request: Request, call: PreparedProviderCall
    ) -> dict[str, str]:
        del request
        return {
            "Authorization": f"Bearer {call.credential}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def usage_extractor(self) -> OpenAIResponsesUsageExtractor:
        return OpenAIResponsesUsageExtractor()

    def provider_request_id(self, upstream: httpx.Response) -> str | None:
        return safe_openai_request_id(
            upstream.headers.get("x-request-id") or upstream.headers.get("request-id")
        )

    async def map_provider_status(
        self, upstream: httpx.Response, call: PreparedProviderCall
    ) -> ProviderError | None:
        del call
        if upstream.status_code < 400:
            return None
        error_code = classify_openai_error(upstream.status_code, await upstream.aread())
        return ProviderError(
            code=error_code,
            error=HTTPException(
                status_code=429 if error_code == "openai_rate_limited" else 503,
                detail={"code": error_code, "message": "Direct OpenAI request failed."},
            ),
            usage=ExtractedOpenAIUsage(
                service_tier="default",
                input_tokens=0,
                cached_input_tokens=0,
                cache_write_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                outcome="failed",
                cost_microusd=0,
            ),
        )

    def stream_error_code(
        self,
        usage: OpenAIResponsesUsageExtractor,
        status_code: int,
        *,
        cancelled: bool,
    ) -> str | None:
        del status_code
        return openai_stream_error_code(usage.result().outcome, cancelled=cancelled)

    def response_headers(self, upstream: httpx.Response) -> dict[str, str]:
        del upstream
        return {"Content-Type": "text/event-stream", "Cache-Control": "no-store"}
