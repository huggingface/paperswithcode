"""Anthropic Messages protocol adapter for the shared provider-call lifecycle.

One adapter serves the Hugging Face router, server-funded OpenRouter, and
OpenRouter bring-your-own-key modes; only funded OpenRouter is metered against
the shared Papers With Code allowance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from backend.chat_execution_policy import MAX_PROVIDER_REQUEST_BYTES
from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatOpenRouterProviderCall,
    ChatSession,
    ChatTurnCapability,
)
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_provider_gateway.lifecycle import (
    ParsedProviderRequest,
    PreparedProviderCall,
    ProviderError,
    ProviderReservationRejected,
    opaque_turn,
    output_tokens_allowed,
)
from backend.services.hf_inference_billing_service import HfInferenceCredential
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    require_openrouter_budget,
)
from backend.services.openrouter_byok_service import (
    OpenRouterBYOKService,
    OpenRouterCredentialUnavailable,
)
from backend.services.openrouter_usage_extractor import (
    ExtractedOpenRouterUsage,
    OpenRouterUsageExtractor,
)
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterAbuseLimitExceeded,
    OpenRouterMonthlyBudgetExhausted,
    OpenRouterPricingUnavailable,
    OpenRouterUserBudgetService,
    RequestBounds,
    opaque_owner,
)

logger = logging.getLogger("backend.chat_gateway_app")

MODEL_REQUEST_TOO_LARGE = "Model request is too large"


def _openrouter_unavailable() -> dict[str, Any]:
    return {
        "code": "openrouter_unavailable",
        "message": (
            "OpenRouter is currently unavailable. However, you can "
            "still bring your own key in Settings."
        ),
        "byok_settings_available": True,
        "support_url": PUBLIC_SUPPORT_URL,
    }


def user_provider_credential(row, settings: Settings) -> HfInferenceCredential:
    credential = ChatCapabilityService.provider_credential(
        row, row.owner_hash, settings
    )
    if not credential:
        raise HTTPException(status_code=402, detail="Authorize Hugging Face inference")
    return credential


def user_provider_token(row, settings: Settings) -> str:
    return user_provider_credential(row, settings).token


def provider_headers(
    provider_token: str,
    request: Request,
    *,
    bill_to: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider_token}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("accept", "application/json"),
        "Anthropic-Version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    if request.headers.get("anthropic-beta"):
        headers["Anthropic-Beta"] = request.headers["anthropic-beta"]
    if bill_to:
        headers["X-HF-Bill-To"] = bill_to
    return headers


def provider_target(
    row, settings: Settings, db: Session | None = None
) -> tuple[str, str, str | None]:
    provider = settings.chat_route_providers.get(row.model)
    if provider == "openrouter":
        mode = getattr(row, "provider_mode", None) or "openrouter_funded"
        if mode == "openrouter_byok":
            if db is None or not row.provider_credential_revision:
                raise HTTPException(status_code=403, detail="Capability rejected")
            session = db.get(ChatSession, row.chat_session_id)
            if (
                session is None
                or row.owner_hash
                != hashlib.sha256(session.hf_user_id.encode()).hexdigest()
            ):
                raise HTTPException(status_code=403, detail="Capability rejected")
            try:
                selected = OpenRouterBYOKService(db, settings).validate_dispatch(
                    session.hf_user_id, row.provider_credential_revision
                )
                copied = user_provider_token(row, settings)
            except OpenRouterCredentialUnavailable:
                raise HTTPException(
                    status_code=401, detail="OpenRouter credential was revoked"
                ) from None
            if not hmac.compare_digest(selected.token, copied):
                raise HTTPException(status_code=403, detail="Capability rejected")
            return (
                "https://openrouter.ai/api/v1/messages",
                copied,
                None,
            )
        if mode != "openrouter_funded":
            raise HTTPException(status_code=403, detail="Capability rejected")
        if (
            not settings.chat_openrouter_server_funded_enabled
            or not settings.chat_openrouter_api_key
        ):
            raise HTTPException(status_code=503, detail="OpenRouter is not configured")
        return (
            "https://openrouter.ai/api/v1/messages",
            settings.chat_openrouter_api_key,
            None,
        )
    if provider == "huggingface":
        credential = user_provider_credential(row, settings)
        return (
            "https://router.huggingface.co/v1/messages",
            credential.token,
            credential.bill_to,
        )
    raise HTTPException(status_code=422, detail="Unsupported model provider")


def prefer_fastest_openrouter_provider(
    payload: dict[str, Any], configured: Settings | None = None
) -> None:
    configured = configured or get_settings()
    policy = (
        configured.chat_openrouter_routing_policy
        if configured.chat_openrouter_routing_enabled
        else "throughput"
    )
    if policy in {"throughput", "latency"}:
        payload["provider"] = {"sort": policy}
        return

    provider: dict[str, Any] = {
        "allow_fallbacks": True,
        "require_parameters": True,
        "max_price": {
            "prompt": configured.chat_openrouter_max_prompt_price_per_million_usd,
            "completion": (
                configured.chat_openrouter_max_completion_price_per_million_usd
            ),
        },
    }
    if policy == "preferred_provider":
        order = [
            slug.strip()
            for slug in configured.chat_openrouter_preferred_providers.split(",")
            if slug.strip()
        ]
        if not order:
            raise RuntimeError("preferred-provider routing requires provider slugs")
        provider["order"] = order
        provider["only"] = order
    else:
        provider.update(
            {
                "sort": "price",
                "preferred_max_latency": {
                    "p90": configured.chat_openrouter_preferred_max_latency_p90_seconds
                },
                "preferred_min_throughput": {
                    "p90": configured.chat_openrouter_preferred_min_throughput_p90
                },
            }
        )
    payload["provider"] = provider


def optimize_initial_deepseek_payload(
    payload: dict[str, Any], candidate: str
) -> dict[str, int]:
    """Remove only byte-identical duplicate immutable payload entries."""

    removed_system = 0
    system = payload.get("system")
    if candidate == "system_duplicates" and isinstance(system, list):
        seen: set[str] = set()
        unique = []
        for block in system:
            identity = json.dumps(block, sort_keys=True, separators=(",", ":"))
            if identity in seen:
                removed_system += 1
                continue
            seen.add(identity)
            unique.append(block)
        payload["system"] = unique
    removed_tools = 0
    tools = payload.get("tools")
    if candidate == "tool_duplicates" and isinstance(tools, list):
        seen_tools: set[str] = set()
        unique_tools = []
        for tool in tools:
            identity = json.dumps(tool, sort_keys=True, separators=(",", ":"))
            if identity in seen_tools:
                removed_tools += 1
                continue
            seen_tools.add(identity)
            unique_tools.append(tool)
        payload["tools"] = unique_tools
    if candidate not in {"system_duplicates", "tool_duplicates"}:
        raise ValueError("Unsupported initial payload optimization candidate")
    return {"system_blocks": removed_system, "tools": removed_tools}


def payload_contains_tool_use(payload: bytes) -> bool:
    return b'"type":"tool_use"' in payload or b'"type": "tool_use"' in payload


def apply_openrouter_reasoning_policy(
    payload: dict[str, Any], effort: str, *, show_reasoning: bool
) -> None:
    if effort not in {"low", "high", "max"}:
        raise ValueError("Unsupported reasoning effort")
    payload["reasoning"] = {
        "effort": effort,
        "exclude": not show_reasoning,
    }


def byok_provider_error_code(status_code: int) -> str | None:
    return {
        402: "openrouter_byok_billing_error",
        429: "openrouter_byok_rate_limit",
    }.get(status_code)


def huggingface_provider_error_code(status_code: int) -> str | None:
    if status_code == 402:
        return "hf_inference_billing_exhausted"
    return None


def settle_openrouter_call(
    settings: Settings,
    call_id: uuid.UUID,
    extractor: OpenRouterUsageExtractor,
) -> None:
    result = extractor.result()
    with db_manager.session_local() as accounting_db:
        service = OpenRouterUserBudgetService(accounting_db, settings)
        if result.cost_microusd is None:
            service.mark_cost_unknown(call_id, result.generation_id)
        else:
            service.settle_call(call_id, result.cost_microusd, result.generation_id)
        call = accounting_db.get(ChatOpenRouterProviderCall, call_id)
        if call is not None:
            call.upstream_provider = result.provider
            call.prompt_tokens = result.prompt_tokens
            call.completion_tokens = result.completion_tokens
            call.cache_read_tokens = result.cache_read_tokens
            call.cache_creation_tokens = result.cache_creation_tokens
        accounting_db.commit()


def record_provider_ttft(call_id: uuid.UUID | None, elapsed_ms: int) -> None:
    if call_id is None:
        return
    with db_manager.session_local() as timing_db:
        call = timing_db.get(ChatOpenRouterProviderCall, call_id)
        if call is not None and call.provider_ttft_ms is None:
            call.provider_ttft_ms = elapsed_ms
        timing_db.commit()


class MessagesUsageStream:
    """OpenRouter usage plus the tool-use and first-byte signals of Messages."""

    def __init__(self) -> None:
        self.extractor = OpenRouterUsageExtractor()
        self.saw_token_delta = False
        self.saw_tool_call = False

    def feed(self, chunk: bytes) -> None:
        self.extractor.feed(chunk)
        # Messages measures time to first body byte, not first token.
        self.saw_token_delta = True
        if not self.saw_tool_call and payload_contains_tool_use(chunk):
            self.saw_tool_call = True

    def inspect_complete_response(self, body: bytes) -> None:
        self.extractor.inspect_complete_response(body)
        self.saw_tool_call = payload_contains_tool_use(body)

    def result(self) -> ExtractedOpenRouterUsage:
        return self.extractor.result()


@dataclass(slots=True)
class UnmeteredProviderLedger:
    """Hugging Face and BYOK calls bill the user's own provider account."""

    name: str = "provider"
    call_id: uuid.UUID | None = None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        del db, turn_id, call_sequence

    def mark_dispatched(self, db: Session) -> None:
        del db

    def trace_accounting(self) -> dict[str, Any]:
        return {}

    def mark_unknown(self, error_code: str) -> None:
        del error_code

    def settle_rejected(
        self,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None:
        del failure, provider_request_id, latency_ms

    def record_ttft(self, elapsed_ms: int) -> None:
        del elapsed_ms

    def settle(
        self,
        usage: MessagesUsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> ExtractedOpenRouterUsage:
        del provider_request_id, latency_ms, ttft_ms, error_code
        return usage.result()


@dataclass(slots=True)
class OpenRouterFundedLedger:
    """Shared Papers With Code OpenRouter allowance for one funded call."""

    settings: Settings
    capability_id: uuid.UUID
    owner_id: str
    model: str
    reasoning_effort: str
    request_bytes: int
    maximum_output_tokens: int
    payload: dict[str, Any]
    name: str = "openrouter"
    call_id: uuid.UUID | None = None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        try:
            await require_openrouter_budget(self.settings)
        except (OpenRouterBudgetExceeded, OpenRouterBudgetUnavailable):
            raise ProviderReservationRejected(
                "openrouter_unavailable",
                status_code=503,
                detail=_openrouter_unavailable(),
            ) from None
        self.call_id = uuid.uuid5(self.capability_id, f"provider-call:{call_sequence}")
        try:
            OpenRouterUserBudgetService(db, self.settings).reserve_call(
                self.owner_id,
                turn_id,
                self.call_id,
                call_sequence,
                self.model,
                RequestBounds(
                    request_bytes=self.request_bytes,
                    maximum_output_tokens=self.maximum_output_tokens,
                    payload=self.payload,
                ),
                reasoning_effort=self.reasoning_effort,
            )
        except OpenRouterMonthlyBudgetExhausted as error:
            resets_at = error.resets_at.isoformat().replace("+00:00", "Z")

            def exhausted() -> dict[str, Any]:
                usage = OpenRouterUserBudgetService(
                    db, self.settings
                ).status_percentage(self.owner_id)
                return {
                    "code": "openrouter_monthly_budget_exhausted",
                    "message": (
                        "The remaining shared Papers With Code OpenRouter allowance "
                        "is not enough for another model call."
                    ),
                    "used_percent": usage.used_percent,
                    "remaining_percent": usage.remaining_percent,
                    "resets_at": resets_at,
                }

            raise ProviderReservationRejected(
                "openrouter_monthly_budget_exhausted",
                status_code=429,
                detail=exhausted,
            ) from None
        except OpenRouterAbuseLimitExceeded as error:
            code = f"openrouter_{error.scope}_limited"
            retry_seconds = max(
                1,
                math.ceil((error.retry_at - datetime.now(UTC)).total_seconds()),
            )
            raise ProviderReservationRejected(
                code,
                status_code=429,
                detail={
                    "code": code,
                    "message": (
                        "Shared OpenRouter usage is temporarily limited. "
                        "You can retry later or use your own key in Settings."
                    ),
                    "byok_settings_available": True,
                },
                headers={"Retry-After": str(retry_seconds)},
            ) from None
        except OpenRouterPricingUnavailable:
            raise ProviderReservationRejected(
                "openrouter_unavailable",
                status_code=503,
                detail=_openrouter_unavailable(),
            ) from None

    def mark_dispatched(self, db: Session) -> None:
        OpenRouterUserBudgetService(db, self.settings).mark_dispatched(self.call_id)

    def trace_accounting(self) -> dict[str, Any]:
        return {}

    def mark_unknown(self, error_code: str) -> None:
        del error_code
        with db_manager.session_local() as accounting_db:
            OpenRouterUserBudgetService(accounting_db, self.settings).mark_cost_unknown(
                self.call_id
            )
            accounting_db.commit()

    def settle_rejected(
        self,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None:
        # Messages relays provider failures; settlement reads their usage.
        del failure, provider_request_id, latency_ms

    def record_ttft(self, elapsed_ms: int) -> None:
        record_provider_ttft(self.call_id, elapsed_ms)

    def settle(
        self,
        usage: MessagesUsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> ExtractedOpenRouterUsage:
        del provider_request_id, latency_ms, ttft_ms, error_code
        settle_openrouter_call(self.settings, self.call_id, usage.extractor)
        return usage.result()


@dataclass(frozen=True, slots=True)
class AnthropicMessagesProtocol:
    """Anthropic Messages relayed to the capability's routed provider."""

    settings: Settings
    receipt_phase: Literal["entry", "dispatch"] = "dispatch"
    transport_error_code: str = "provider_transport_error"
    releases_request_session: bool = False
    shields_upstream_close: bool = False
    logs_stream_completion: bool = True

    def check_available(self) -> None:
        return None

    def parse(self, raw: bytes) -> ParsedProviderRequest:
        if len(raw) > MAX_PROVIDER_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail=MODEL_REQUEST_TOO_LARGE)
        try:
            payload = json.loads(raw)
            model = str(payload["model"])
            maximum_tokens = int(payload.get("max_tokens", 0))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(
                status_code=422, detail="Invalid model request"
            ) from None
        if not output_tokens_allowed(maximum_tokens):
            raise HTTPException(status_code=422, detail="max_tokens is out of range")
        return ParsedProviderRequest(
            payload=payload,
            raw=raw,
            capability_model=model,
            maximum_tokens=maximum_tokens,
        )

    def observe_rejection(self, phase: str) -> None:
        del phase

    def prepare(
        self,
        parsed: ParsedProviderRequest,
        row: ChatTurnCapability,
        db: Session,
        owner: Callable[[], str],
        *,
        turn_id: uuid.UUID,
    ) -> PreparedProviderCall:
        settings = self.settings
        payload = parsed.payload
        model = parsed.capability_model
        raw = parsed.raw
        provider = settings.chat_route_providers.get(row.model)
        provider_mode = row.provider_mode or (
            "openrouter_funded" if provider == "openrouter" else "huggingface"
        )
        owner_id = owner()
        effort = getattr(row, "reasoning_effort", None) or "high"
        if provider == "openrouter":
            # Supplemental reconciliation metadata is opaque and cannot identify
            # the HF subject at OpenRouter.
            payload["user"] = opaque_owner(owner_id, settings)
            prefer_fastest_openrouter_provider(payload, settings)
            if (
                settings.chat_initial_payload_optimization_enabled
                and model == settings.chat_effective_pi_prewarm_model
                and row.provider_requests == 0
            ):
                removed = optimize_initial_deepseek_payload(
                    payload,
                    settings.chat_initial_payload_optimization_candidate,
                )
                logger.info(
                    "chat initial payload optimization turn=%s removed_system=%s "
                    "removed_tools=%s",
                    opaque_turn(turn_id),
                    removed["system_blocks"],
                    removed["tools"],
                )
            try:
                apply_openrouter_reasoning_policy(
                    payload, effort, show_reasoning=settings.chat_show_reasoning
                )
            except ValueError:
                raise HTTPException(status_code=403, detail="Capability rejected")
            raw = json.dumps(payload, separators=(",", ":")).encode()
            if len(raw) > MAX_PROVIDER_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail=MODEL_REQUEST_TOO_LARGE)
        url, credential, bill_to = provider_target(row, settings, db)
        if provider_mode == "openrouter_funded":
            ledger = OpenRouterFundedLedger(
                settings=settings,
                capability_id=row.id,
                owner_id=owner_id,
                model=model,
                reasoning_effort=effort,
                request_bytes=len(raw),
                maximum_output_tokens=parsed.maximum_tokens,
                payload=payload,
            )
        else:
            ledger = UnmeteredProviderLedger()
        return PreparedProviderCall(
            payload=payload,
            raw=raw,
            maximum_tokens=parsed.maximum_tokens,
            capability_id=row.id,
            owner_id=owner_id,
            provider_mode=provider_mode,
            url=url,
            credential=credential,
            bill_to=bill_to,
            ledger=ledger,
            trace_fields={
                "model": model,
                "provider_mode": provider_mode,
                "reasoning_effort": effort,
                "routing_policy": (
                    settings.chat_openrouter_routing_policy
                    if settings.chat_openrouter_routing_enabled
                    else "throughput"
                ),
            },
            stream=bool(payload.get("stream")),
        )

    def upstream_headers(
        self, request: Request, call: PreparedProviderCall
    ) -> dict[str, str]:
        return provider_headers(call.credential, request, bill_to=call.bill_to)

    def usage_extractor(self) -> MessagesUsageStream:
        return MessagesUsageStream()

    def provider_request_id(self, upstream: httpx.Response) -> str | None:
        del upstream
        return None

    def transport_failure(self) -> ProviderError:
        return ProviderError(
            code="provider_transport_error",
            error=HTTPException(status_code=502, detail="Model provider failed"),
            record=False,
        )

    async def map_provider_status(
        self, upstream: httpx.Response, call: PreparedProviderCall
    ) -> ProviderError | None:
        mode = call.provider_mode
        status = upstream.status_code
        if mode == "openrouter_byok" and status == 401:
            with db_manager.session_local() as credential_db:
                OpenRouterBYOKService(
                    credential_db, self.settings
                ).invalidate_auth_failure(call.owner_id)
                capability = credential_db.get(ChatTurnCapability, call.capability_id)
                if capability is not None:
                    ChatCapabilityService(credential_db).record_provider_error(
                        capability, "openrouter_byok_credential_invalid"
                    )
                credential_db.commit()
            return None
        if mode == "openrouter_byok":
            code = byok_provider_error_code(status)
        elif mode == "openrouter_funded" and status in {402, 403}:
            code = "openrouter_unavailable"
        elif mode == "huggingface":
            code = huggingface_provider_error_code(status)
        else:
            code = None
        return None if code is None else ProviderError(code=code, error=None)

    def stream_error_code(
        self, usage: MessagesUsageStream, status_code: int, *, cancelled: bool
    ) -> str | None:
        del usage, cancelled
        return None if status_code < 400 else f"provider_http_{status_code}"

    def response_headers(self, upstream: httpx.Response) -> dict[str, str]:
        return {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() in {"content-type", "request-id"}
        }
