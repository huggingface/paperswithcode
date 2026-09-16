"""Private, separately started gateway for sandbox model/catalog/store traffic."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from huggingface_hub.errors import HfHubHTTPError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.chat_execution_policy import (
    MAX_POSTER_PROVIDER_REQUESTS,
    MAX_PROVIDER_REQUESTS,
    MAX_PROVIDER_TURN_TOKENS,
    MAX_PROVIDER_REQUEST_BYTES,
)
from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
from backend.config import Settings, get_settings
from backend.database.connection import db_manager, get_database_session
from backend.models.chat import LatexPaperSourceEdit
from backend.models.database import (
    ChatMessageRecord,
    ChatOpenRouterProviderCall,
    ChatQualificationScope,
    ChatSession,
    ChatTurnCapability,
    ChatTurnLatency,
)
from backend.services.chat_artifact_service import (
    ArtifactError,
    ChatArtifactService,
    PosterPaperProvenance,
)
from backend.services.latex_paper_service import LatexPaperService
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
)
from backend.services.catalog_errors import CatalogNotFoundError
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.chat_pwc_mcp import (
    ENDPOINT,
    TOOL_NAMES,
    PwcMcpError,
    endpoint_for,
    request_mcp,
)
from backend.services.chat_hf_hub_service import (
    ChatHfHubError,
    ChatHfHubService,
    validate_hf_request,
)
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.durable_external_qualification_contract import (
    DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN,
)
from backend.services.chat_openai_budget_service import (
    MAX_REQUEST_BYTES as MAX_OPENAI_REQUEST_BYTES,
)
from backend.services.chat_openai_budget_service import (
    ChatOpenAIBudgetService,
    OpenAIBudgetError,
    OpenAIBudgetExhausted,
    OpenAILimitExceeded,
    OpenAIRequestBounds,
    actual_usage_microusd,
)
from backend.services.chat_openai_usage_extractor import (
    ExtractedOpenAIUsage,
    OpenAIResponsesUsageExtractor,
    classify_openai_error,
)
from backend.services.chat_paper_context_service import ChatPaperContextService
from backend.services.chat_pi_transcript_service import (
    ChatPiTranscriptService,
    PiTranscriptError,
)
from backend.services.chat_semantic_scholar_service import (
    SemanticScholarGatewayError,
    fetch_semantic_scholar,
)
from backend.services.chat_session_service import ChatServiceError
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.services.chat_tracing_service import start_provider_request_trace
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)
from backend.services.chat_durable_lifecycle_observer import (
    durable_lifecycle_observer,
)
from backend.services.chat_web_fetch_service import (
    ChatWebFetchError,
    fetch_catalog_url,
)
from backend.services.chat_web_search_service import WebSearchError, search_web
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
from backend.services.openrouter_usage_extractor import OpenRouterUsageExtractor
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterAbuseLimitExceeded,
    OpenRouterMonthlyBudgetExhausted,
    OpenRouterPricingUnavailable,
    OpenRouterUserBudgetService,
    RequestBounds,
    opaque_owner,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
    ) as client:
        app.state.pwc_mcp_client = client
        app.state.pwc_mcp_endpoint = endpoint_for(get_settings().environment)
        yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
logger = logging.getLogger(__name__)
hf_telemetry_logger = logging.getLogger("uvicorn.error")
MAX_PROVIDER_OUTPUT_TOKENS = PROVIDER_OUTPUT_TOKEN_LIMIT
MAX_POSTER_PROVIDER_TURN_TOKENS = 8_000_000
QUALIFICATION_PROVIDER_REQUESTS = DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN
QUALIFICATION_PROVIDER_TURN_TOKENS = QUALIFICATION_PROVIDER_REQUESTS * (
    MAX_OPENAI_REQUEST_BYTES // 4 + MAX_PROVIDER_OUTPUT_TOKENS
)


def _hf_latency_bucket(elapsed_seconds: float) -> str:
    elapsed_ms = elapsed_seconds * 1000
    for ceiling in (100, 250, 500, 1000, 3000, 10_000):
        if elapsed_ms < ceiling:
            return f"lt_{ceiling}ms"
    return "gte_10000ms"


def _opaque_turn(turn_id: uuid.UUID) -> str:
    return hashlib.sha256(str(turn_id).encode()).hexdigest()[:12]


def _record_gateway_timing(
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
            _opaque_turn(turn_id),
            phase or "received",
            type(error).__name__,
        )


class CatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class McpCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str | None = Field(default=None, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class HfCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class StoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    key: dict[str, Any] | None = None
    entries: list[dict[str, Any]] | None = None
    project_key: str | None = None
    format: Literal["claude", "pi"] = "claude"
    agent_session_id: uuid.UUID | None = None
    current_leaf_id: str | None = Field(default=None, max_length=255)


class WebFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)


class ArtifactPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_route_id: str = Field(min_length=1, max_length=200)


class PaperCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create", "begin-edit", "repair-context", "draft", "repair"]
    title: str | None = Field(default=None, max_length=300)
    artifact_id: uuid.UUID | None = None
    expected_parent_version_id: uuid.UUID | None = None
    files: list[LatexPaperSourceEdit] = Field(default_factory=list, max_length=100)


def _bearer(authorization: Annotated[str, Header()]) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid capability")
    return token


def _output_tokens_allowed(value: int) -> bool:
    return 1 <= value <= MAX_PROVIDER_OUTPUT_TOKENS


def _provider_turn_limits(
    row: ChatTurnCapability,
    db: Session | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    qualification_scope_id = (
        _qualification_scope_claim(row, db, settings)
        if db is not None and settings is not None
        else None
    )
    if qualification_scope_id is not None:
        return QUALIFICATION_PROVIDER_REQUESTS, QUALIFICATION_PROVIDER_TURN_TOKENS
    if {"artifact", "paper_grant"} & set(getattr(row, "scopes", ())):
        return MAX_POSTER_PROVIDER_REQUESTS, MAX_POSTER_PROVIDER_TURN_TOKENS
    return MAX_PROVIDER_REQUESTS, MAX_PROVIDER_TURN_TOKENS


def _qualification_scope_claim(
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


def _user_provider_credential(row, settings: Settings) -> HfInferenceCredential:
    credential = ChatCapabilityService.provider_credential(
        row, row.owner_hash, settings
    )
    if not credential:
        raise HTTPException(status_code=402, detail="Authorize Hugging Face inference")
    return credential


def _user_provider_token(row, settings: Settings) -> str:
    return _user_provider_credential(row, settings).token


def _provider_headers(
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


def _provider_target(
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
                copied = _user_provider_token(row, settings)
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
        credential = _user_provider_credential(row, settings)
        return (
            "https://router.huggingface.co/v1/messages",
            credential.token,
            credential.bill_to,
        )
    raise HTTPException(status_code=422, detail="Unsupported model provider")


def _prefer_fastest_openrouter_provider(
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


def _optimize_initial_deepseek_payload(
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


def _offered_tool_inventory(payload: dict[str, Any]) -> dict[str, Any]:
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


def _payload_contains_tool_use(payload: bytes) -> bool:
    return b'"type":"tool_use"' in payload or b'"type": "tool_use"' in payload


def _apply_openrouter_reasoning_policy(
    payload: dict[str, Any], effort: str, *, show_reasoning: bool
) -> None:
    if effort not in {"low", "high", "max"}:
        raise ValueError("Unsupported reasoning effort")
    payload["reasoning"] = {
        "effort": effort,
        "exclude": not show_reasoning,
    }


def _capability_owner(row: ChatTurnCapability, db: Session) -> str:
    session = db.get(ChatSession, row.chat_session_id)
    if session is None:
        logger.critical("openrouter funded dispatch missing owner session")
        raise HTTPException(status_code=403, detail="Capability rejected")
    if row.owner_hash != hashlib.sha256(session.hf_user_id.encode()).hexdigest():
        logger.critical("openrouter funded dispatch owner binding mismatch")
        raise HTTPException(status_code=403, detail="Capability rejected")
    return session.hf_user_id


def _record_provider_error(capability_id: uuid.UUID, code: str) -> None:
    with db_manager.session_local() as error_db:
        row = error_db.get(ChatTurnCapability, capability_id)
        if row is not None:
            ChatCapabilityService(error_db).record_provider_error(row, code)
            error_db.commit()


def _byok_provider_error_code(status_code: int) -> str | None:
    return {
        402: "openrouter_byok_billing_error",
        429: "openrouter_byok_rate_limit",
    }.get(status_code)


def _huggingface_provider_error_code(status_code: int) -> str | None:
    if status_code == 402:
        return "hf_inference_billing_exhausted"
    return None


def _settle_openrouter_call(
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


def _record_provider_ttft(call_id: uuid.UUID | None, elapsed_ms: int) -> None:
    if call_id is None:
        return
    with db_manager.session_local() as timing_db:
        call = timing_db.get(ChatOpenRouterProviderCall, call_id)
        if call is not None and call.provider_ttft_ms is None:
            call.provider_ttft_ms = elapsed_ms
        timing_db.commit()


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


def _opaque_openai_identifier(kind: str, value: str, settings: Settings) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode(),
        f"openai:{kind}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"pwc_{digest[:48]}"


def _trusted_openai_payload(
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
        or not _output_tokens_allowed(maximum_tokens)
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
    trusted["reasoning"] = {"effort": row.reasoning_effort}
    if summary is not None:
        trusted["reasoning"]["summary"] = summary
    trusted["safety_identifier"] = _opaque_openai_identifier(
        "owner", row.owner_hash, settings
    )
    trusted["prompt_cache_key"] = _opaque_openai_identifier(
        "session", str(row.chat_session_id), settings
    )
    return trusted, maximum_tokens


def _safe_openai_request_id(value: str | None) -> str | None:
    if not value or not re.fullmatch(r"[A-Za-z0-9._:-]{1,255}", value):
        return None
    return value


def _openai_stream_error_code(outcome: str | None, *, cancelled: bool) -> str | None:
    if outcome == "completed":
        return None
    if cancelled:
        return "openai_stream_cancelled"
    if outcome == "incomplete":
        return "openai_incomplete"
    return "openai_unavailable"


async def _close_openai_stream(upstream: Any, client: Any) -> None:
    with anyio.CancelScope(shield=True):
        await upstream.aclose()
        await client.aclose()


def _settle_openai_call(
    settings: Settings,
    call_id: uuid.UUID,
    extractor: OpenAIResponsesUsageExtractor,
    *,
    provider_request_id: str | None,
    latency_ms: int,
    ttft_ms: int | None,
    error_code: str | None,
):
    result = extractor.result()
    with db_manager.session_local() as accounting_db:
        ChatOpenAIBudgetService(accounting_db, settings).settle_call(
            call_id,
            result,
            provider_request_id=provider_request_id,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            error_code=error_code,
        )
        accounting_db.commit()
    return replace(result, cost_microusd=actual_usage_microusd(settings, result))


@dataclass(frozen=True, slots=True)
class ExternalTurnFenceHeaders:
    worker_id: str | None
    worker_generation: str | None
    lease_generation: str | None

    def claim(self, *, turn_id: str) -> TurnLeaseClaim:
        if (
            self.worker_id is None
            or self.worker_generation is None
            or self.lease_generation is None
        ):
            raise LookupError("External turn fence is missing")
        worker_generation = int(self.worker_generation)
        lease_generation = int(self.lease_generation)
        if worker_generation < 1 or lease_generation < 1:
            raise ValueError("External turn fence generation is invalid")
        return TurnLeaseClaim(
            turn_id=uuid.UUID(turn_id),
            worker_id=self.worker_id,
            worker_generation=worker_generation,
            lease_generation=lease_generation,
        )


def _external_turn_fence_headers(
    x_pwc_turn_worker_id: Annotated[str | None, Header()] = None,
    x_pwc_turn_worker_generation: Annotated[str | None, Header()] = None,
    x_pwc_turn_lease_generation: Annotated[str | None, Header()] = None,
) -> ExternalTurnFenceHeaders:
    return ExternalTurnFenceHeaders(
        worker_id=x_pwc_turn_worker_id,
        worker_generation=x_pwc_turn_worker_generation,
        lease_generation=x_pwc_turn_lease_generation,
    )


TurnFenceDependency = Annotated[
    ExternalTurnFenceHeaders, Depends(_external_turn_fence_headers)
]


def _scope(
    token: str,
    scope: str,
    session_id: str,
    turn_id: str,
    db: Session,
    *,
    model: str | None = None,
    turn_fence: ExternalTurnFenceHeaders | None = None,
):
    try:
        row = ChatCapabilityService(db).validate(
            token,
            scope=scope,
            chat_session_id=uuid.UUID(session_id),
            turn_id=uuid.UUID(turn_id),
            model=model,
        )
    except (CapabilityError, ValueError):
        db.rollback()
        raise HTTPException(status_code=403, detail="Capability rejected") from None
    if "external_turn" not in row.scopes:
        return row
    fence = turn_fence or ExternalTurnFenceHeaders(None, None, None)
    try:
        claim = fence.claim(turn_id=turn_id)
    except LookupError:
        db.rollback()
        raise HTTPException(
            status_code=403,
            detail={
                "code": "chat_turn_fence_missing",
                "message": "External turn fence is required",
            },
        )
    try:
        ChatTurnJobRepository().require_live_claim(
            db,
            claim=claim,
            now=datetime.now(UTC),
        )
    except (StaleTurnClaim, ValueError):
        db.rollback()
        from backend.services.chat_durable_qualification_evidence import (
            record_qualification_event_safely,
        )

        record_qualification_event_safely(
            turn_id=uuid.UUID(turn_id),
            chat_session_id=uuid.UUID(session_id),
            event_type="stale_fence",
        )
        durable_lifecycle_observer(get_settings())("stale_fence_rejection", "stale", 1)
        raise HTTPException(
            status_code=403,
            detail={
                "code": "chat_turn_fence_stale",
                "message": "External turn fence is stale",
            },
        ) from None
    return row


def _authorize_pwc_mcp(
    body: McpCatalogRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.chat_pwc_mcp_enabled:
        raise HTTPException(status_code=503, detail="PwC MCP tools are not enabled")
    if (
        (body.tool is not None and body.tool not in TOOL_NAMES)
        or (body.tool is None and body.arguments)
        or len(json.dumps(body.arguments).encode()) > 16_384
    ):
        raise HTTPException(status_code=422, detail="Invalid MCP tool request")
    capability = _scope(
        _bearer(authorization),
        "catalog",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    try:
        # Filtered searches share the CLI/direct search allowance as well.
        operation = (
            "search"
            if body.tool == "search_papers"
            or (body.tool == "list_papers" and body.arguments.get("search"))
            else "mcp_catalog"
        )
        ChatCapabilityService(db).meter_catalog(
            capability,
            operation,
            maximum_searches=settings.chat_max_direct_search_calls,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Tool execution limit reached"
        ) from None


@app.post("/catalog-mcp", dependencies=[Depends(_authorize_pwc_mcp)])
async def catalog_mcp(body: McpCatalogRequest, request: Request):
    finished = asyncio.Event()

    async def disconnected():
        while not finished.is_set() and not await request.is_disconnected():
            await asyncio.sleep(0.1)

    method = "tools/list" if body.tool is None else "tools/call"
    params = (
        {} if body.tool is None else {"name": body.tool, "arguments": body.arguments}
    )
    call = asyncio.create_task(
        request_mcp(
            request.app.state.pwc_mcp_client,
            method,
            params,
            getattr(request.app.state, "pwc_mcp_endpoint", ENDPOINT),
        )
    )
    disconnect = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait(
            {call, disconnect}, return_when=asyncio.FIRST_COMPLETED
        )
        if disconnect in done:
            raise HTTPException(status_code=499, detail="MCP request cancelled")
        return {"result": await call}
    except PwcMcpError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    finally:
        # A disconnect probe may consume cancellation in its local cancel scope.
        # Give the polling loop an independent exit condition before joining it.
        finished.set()
        call.cancel()
        disconnect.cancel()
        await asyncio.gather(call, disconnect, return_exceptions=True)


@app.post("/catalog")
def catalog(
    body: CatalogRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    scope = "web_search" if body.operation == "web_search" else "catalog"
    capability = _scope(
        token,
        scope,
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    try:
        if body.operation == "web_search":
            ChatCapabilityService(db).meter_web_search(
                capability, maximum_searches=settings.chat_web_search_max_calls
            )
        elif body.operation == "semantic_scholar":
            operation = (
                "search"
                if body.arguments.get("path", "").strip("/") == "paper/search"
                else body.operation
            )
            ChatCapabilityService(db).meter_catalog(
                capability,
                operation,
                maximum_searches=settings.chat_max_direct_search_calls,
            )
        else:
            ChatCapabilityService(db).meter_catalog(
                capability,
                body.operation,
                maximum_searches=settings.chat_max_direct_search_calls,
            )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Tool execution limit reached"
        ) from None
    if body.operation == "web_search":
        try:
            query = body.arguments["query"]
            if set(body.arguments) != {"query"} or not isinstance(query, str):
                raise ValueError
            result = asyncio.run(
                search_web(query, settings, owner_hash=capability.owner_hash)
            )
            return {"result": result}
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="Invalid web search request"
            ) from None
        except WebSearchError as error:
            capability = db.get(ChatTurnCapability, capability.id)
            if capability is not None:
                ChatCapabilityService(db).fail_web_search(capability)
                db.commit()
            raise HTTPException(
                status_code=503,
                detail={"code": error.code, "message": str(error)},
            ) from None
    if body.operation == "semantic_scholar":
        try:
            return {
                "result": fetch_semantic_scholar(
                    settings,
                    str(body.arguments["path"]),
                    dict(body.arguments.get("query") or {}),
                )
            }
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except SemanticScholarGatewayError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail="Semantic Scholar request failed",
            ) from error
        except (httpx.HTTPError, RuntimeError) as error:
            raise HTTPException(
                status_code=503,
                detail="Semantic Scholar is temporarily unavailable",
            ) from error
    try:
        result = ChatGatewayService(db, settings).catalog(
            body.operation, body.arguments
        )
    except CatalogNotFoundError as error:
        raise HTTPException(status_code=404, detail=error.detail) from None
    except (HfHubHTTPError, OSError):
        raise HTTPException(
            status_code=502, detail="Paper Markdown could not be read"
        ) from None
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"result": result}


@app.post("/hf-catalog")
def hf_catalog(
    body: HfCatalogRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.chat_hf_catalog_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hf_unavailable",
                "message": "Hugging Face catalog is unavailable",
            },
        )
    try:
        arguments = validate_hf_request(body.operation, body.arguments)
    except ChatHfHubError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from None
    token = _bearer(authorization)
    capability = _scope(
        token,
        "hf_catalog",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    recursive = body.operation.endswith("_list") and bool(
        arguments.get("repo_id") and arguments.get("recursive")
    )
    try:
        ChatCapabilityService(db).meter_hf_catalog(
            capability,
            recursive=recursive,
            maximum_calls=settings.chat_hf_catalog_max_calls,
            maximum_recursive_calls=settings.chat_hf_recursive_list_max_calls,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail={
                "code": "hf_limit_reached",
                "message": "HF operation limit reached",
            },
        ) from None
    started = time.perf_counter()
    try:
        result = ChatHfHubService(settings).execute(body.operation, arguments)
        hf_telemetry_logger.info(
            "chat hf catalog operation=%s repo_type=%s cache=%s status_class=2xx "
            "latency_bucket=%s result_count=%d response_bytes=%d truncated=%s",
            body.operation,
            body.operation.partition("_")[0],
            result.get("cache", "miss"),
            _hf_latency_bucket(time.perf_counter() - started),
            (result.get("result_set") or {}).get("returned", 1),
            len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()),
            bool((result.get("truncation") or {}).get("truncated")),
        )
        return result
    except ChatHfHubError as error:
        hf_telemetry_logger.info(
            "chat hf catalog operation=%s repo_type=%s cache=miss status_class=%s "
            "latency_bucket=%s result_count=0 response_bytes=0 truncated=false",
            body.operation,
            body.operation.partition("_")[0],
            f"{error.status_code // 100}xx",
            _hf_latency_bucket(time.perf_counter() - started),
        )
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from None


@app.post("/session-store")
def session_store(
    body: StoreRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(
        token,
        "session_store",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    if body.format == "pi":
        if (
            getattr(capability, "agent_harness", "claude") != "pi"
            or body.agent_session_id is None
        ):
            raise HTTPException(status_code=403, detail="Session store scope rejected")
        service = ChatPiTranscriptService(db, settings)
        try:
            if body.action == "create_or_bind_session":
                row = service.create_or_bind_session(
                    capability.chat_session_id, body.agent_session_id
                )
                result: object = {
                    "agent_session_id": str(row.agent_session_id),
                    "current_leaf_id": row.current_leaf_id,
                    "entry_count": row.entry_count,
                    "byte_size": row.byte_size,
                    "format_version": row.format_version,
                }
            elif body.action == "append_entries":
                row = service.append_entries(
                    capability.chat_session_id,
                    body.agent_session_id,
                    body.entries or [],
                    current_leaf_id=body.current_leaf_id,
                )
                result = {
                    "agent_session_id": str(row.agent_session_id),
                    "current_leaf_id": row.current_leaf_id,
                    "entry_count": row.entry_count,
                    "byte_size": row.byte_size,
                    "format_version": row.format_version,
                }
            elif body.action == "load_session":
                snapshot = service.load_session(
                    capability.chat_session_id, body.agent_session_id
                )
                result = {
                    "agent_session_id": str(snapshot.agent_session_id),
                    "current_leaf_id": snapshot.current_leaf_id,
                    "entry_count": snapshot.entry_count,
                    "byte_size": snapshot.byte_size,
                    "format_version": snapshot.format_version,
                    "entries": list(snapshot.entries),
                }
            elif body.action == "delete_session":
                result = service.delete_session(
                    capability.chat_session_id, body.agent_session_id
                )
            else:
                raise PiTranscriptError("Unsupported Pi session store action")
            db.commit()
            return {"result": result}
        except PiTranscriptError as error:
            db.rollback()
            logger.warning(
                "Pi transcript store rejected action=%s reason=%s",
                body.action,
                error,
            )
            raise HTTPException(status_code=409, detail=str(error)) from None
    if body.agent_session_id is not None or body.current_leaf_id is not None:
        raise HTTPException(
            status_code=422, detail="Invalid Claude session store request"
        )
    if getattr(capability, "agent_harness", "claude") != "claude":
        raise HTTPException(status_code=403, detail="Session store scope rejected")
    try:
        result = ChatSessionStoreGateway(db, settings).execute(
            capability,
            SessionStoreCommand(
                action=body.action,
                key=body.key,
                entries=body.entries,
                project_key=body.project_key,
            ),
        )
        db.commit()
        return {"result": result}
    except SessionStoreGatewayError as error:
        db.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None


@app.post("/artifact-prepare")
def artifact_prepare(
    body: ArtifactPrepareRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(
        token,
        "artifact",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    if not settings.chat_artifacts_enabled or not settings.chat_posterly_enabled:
        raise HTTPException(status_code=404, detail="Poster generation is disabled")
    try:
        paper = ChatPaperContextService(db, settings).prepare_one(body.paper_route_id)
    except ChatServiceError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from None
    if (
        paper.source != "arxiv"
        or not paper.arxiv_id
        or not paper.paper_version
        or re.fullmatch(r"v\d+", paper.paper_version) is None
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "poster_paper_unsupported",
                "message": "Poster generation currently supports cataloged arXiv papers only.",
            },
        )
    if not paper.content_available:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "poster_paper_unavailable",
                "message": "Stored paper Markdown is not available yet.",
            },
        )
    if capability.artifact_paper_id not in {None, paper.paper_id}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "poster_paper_conflict",
                "message": "This poster turn is already bound to a different paper.",
            },
        )
    capability.artifact_paper_id = paper.paper_id
    db.commit()
    return {
        "route_id": paper.route_id,
        "paper_id": paper.paper_id,
        "title": paper.title,
        "arxiv_id": f"{paper.arxiv_id}{paper.paper_version}",
        "paper_version": paper.paper_version,
        "content_sha256": paper.content_sha256,
        "source_available": False,
        "paper_markdown": paper.markdown,
        "content_truncated": paper.content_truncated,
        "notice": (
            "Only bounded stored Markdown was available; source fidelity and "
            "real-figure extraction may be limited."
        ),
    }


@app.post("/paper")
def paper_command(
    body: PaperCommandRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Create or inspect the paper bound to this authenticated live turn."""
    capability = _scope(
        _bearer(authorization),
        "paper",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    if not (
        settings.chat_artifacts_enabled
        and settings.chat_latex_paper_enabled
        and settings.chat_latex_compiler_jobs_enabled
    ):
        raise HTTPException(status_code=404, detail="Paper authoring is disabled")
    session = db.get(ChatSession, capability.chat_session_id)
    if session is None or session.active_turn_id != capability.turn_id:
        raise HTTPException(status_code=409, detail="Paper turn is no longer active")
    if session.primary_paper_id is not None:
        raise HTTPException(
            status_code=409, detail="Papers are available only in general chat"
        )
    owner_id = _capability_owner(capability, db)
    service = LatexPaperService(db, settings)
    try:
        if body.operation == "create":
            descriptor = service.create_neutral_scaffold(
                owner_id=owner_id,
                session_id=capability.chat_session_id,
                title=body.title or "Untitled Research Draft",
                actor_type="ai",
                model_identity=session.selected_model,
            )
            result = {"paper": descriptor.model_dump(mode="json")}
        elif body.operation == "begin-edit":
            descriptor = service.get_descriptor(owner_id, capability.chat_session_id)
            if descriptor is None:
                raise ArtifactError("paper_missing", "This chat has no paper yet")
            result = {"paper": descriptor.model_dump(mode="json")}
        elif body.operation == "repair-context":
            descriptor = service.get_descriptor(owner_id, capability.chat_session_id)
            if descriptor is None:
                raise ArtifactError("paper_missing", "This chat has no paper yet")
            context_descriptor, files = service.repair_context(
                owner_id=owner_id, artifact_id=descriptor.artifact_id
            )
            result = {
                "paper": context_descriptor.model_dump(mode="json"),
                "files": [
                    {"path": path, "content": data.decode("utf-8")}
                    for path, data in files.items()
                ],
            }
        elif body.operation == "draft":
            if body.artifact_id is None or body.expected_parent_version_id is None:
                raise ArtifactError(
                    "artifact_invalid", "Draft needs the current paper version"
                )
            current = service.get_descriptor(owner_id, capability.chat_session_id)
            if current is None or current.artifact_id != body.artifact_id:
                raise ArtifactError("paper_missing", "This chat has no paper yet")
            descriptor = service.save_ai_version(
                owner_id=owner_id,
                artifact_id=body.artifact_id,
                expected_parent_version_id=body.expected_parent_version_id,
                files={file.path: file.content.encode("utf-8") for file in body.files},
                model_identity=session.selected_model,
            )
            result = {"paper": descriptor.model_dump(mode="json")}
        elif body.operation == "repair":
            if body.artifact_id is None or body.expected_parent_version_id is None:
                raise ArtifactError(
                    "artifact_invalid", "Repair needs the failed paper version"
                )
            current = service.get_descriptor(owner_id, capability.chat_session_id)
            if current is None or current.artifact_id != body.artifact_id:
                raise ArtifactError("paper_missing", "This chat has no paper yet")
            outcome = service.repair_failed_version(
                owner_id=owner_id,
                artifact_id=body.artifact_id,
                expected_parent_version_id=body.expected_parent_version_id,
                files={file.path: file.content.encode("utf-8") for file in body.files},
                provenance={"selected_model": session.selected_model, "repair": True},
            )
            result = {
                "paper": outcome.descriptor.model_dump(mode="json"),
                "repaired": outcome.repaired,
                "exhausted": outcome.exhausted,
            }
        else:  # Pydantic limits the operation, but keep this boundary explicit.
            raise ArtifactError("artifact_invalid", "Unknown paper operation")
    except ArtifactError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": str(error)},
        ) from None

    activated = "paper_grant" not in capability.scopes
    if activated:
        capability.scopes = sorted({*capability.scopes, "paper_grant"})
        capability.expires_at = max(
            capability.expires_at,
            datetime.now(UTC)
            + timedelta(seconds=settings.chat_latex_paper_timeout_seconds + 60),
        )
        session.active_turn_expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.chat_latex_paper_timeout_seconds + 30
        )
    db.commit()
    return {
        "operation": body.operation,
        "activated": activated,
        **result,
    }


@app.post("/artifact-publish")
async def artifact_publish(
    request: Request,
    publication_id: str,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(
        token,
        "artifact",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    if capability.artifact_paper_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "poster_paper_required",
                "message": "Prepare one cataloged arXiv paper before publishing.",
            },
        )
    if request.headers.get("content-type", "").partition(";")[0] != "application/zip":
        raise HTTPException(status_code=415, detail="Expected a ZIP publication")
    maximum = settings.chat_artifact_max_version_bytes
    declared = request.headers.get("content-length")
    if declared is None or not declared.isdigit() or not 0 < int(declared) <= maximum:
        raise HTTPException(status_code=413, detail="Poster publication is too large")
    descriptor, temporary_name = tempfile.mkstemp(prefix="pwc-artifact-", suffix=".zip")
    total = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            async for chunk in request.stream():
                total += len(chunk)
                if total > maximum:
                    raise HTTPException(
                        status_code=413, detail="Poster publication is too large"
                    )
                output.write(chunk)
        if total != int(declared):
            raise HTTPException(status_code=400, detail="Incomplete poster publication")
        try:
            prepared = ChatPaperContextService(db, settings).prepare_one(
                capability.artifact_paper_id
            )
            if (
                prepared.source != "arxiv"
                or not prepared.arxiv_id
                or not prepared.paper_version
            ):
                raise ArtifactError(
                    "poster_paper_unsupported",
                    "Prepared paper is no longer a supported arXiv paper",
                )
            version = ChatArtifactService(db, settings).publish_zip(
                owner_id=_capability_owner(capability, db),
                session_id=capability.chat_session_id,
                turn_id=capability.turn_id,
                publication_id=publication_id,
                archive=Path(temporary_name),
                expected_paper=PosterPaperProvenance(
                    route_id=prepared.route_id,
                    paper_id=prepared.paper_id,
                    arxiv_id=f"{prepared.arxiv_id}{prepared.paper_version}",
                    paper_version=prepared.paper_version,
                    content_sha256=prepared.content_sha256,
                    source_available=False,
                ),
            )
            db.commit()
        except ArtifactError as error:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error)},
            ) from None
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    artifact = version.artifact
    return {
        "publication_id": publication_id,
        "artifact_id": str(artifact.id),
        "version_id": str(version.id),
        "identifier": artifact.identifier,
        "version": version.version,
        "kind": "posterly",
        "title": artifact.title,
        "preview_mime": version.preview_mime,
        "source_language": "html",
        "gate_status": version.gate_status,
        "total_bytes": version.byte_count,
    }


@app.post("/web-fetch")
async def web_fetch(
    body: WebFetchRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
):
    token = _bearer(authorization)
    _scope(
        token,
        "web_fetch",
        x_pwc_session,
        x_pwc_turn,
        db,
        turn_fence=turn_fence,
    )
    db.commit()
    try:
        result = await fetch_catalog_url(db, body.url)
    except ChatWebFetchError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None
    return Response(
        content=result.body,
        status_code=result.status_code,
        headers={
            "Content-Type": result.content_type,
            "Content-Length": str(len(result.body)),
            "Cache-Control": "no-store",
        },
    )


@app.post("/v1/responses")
async def responses(
    request: Request,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Capability-bound, stateless native OpenAI Responses streaming proxy."""

    started = time.perf_counter()
    if not settings.chat_openai_direct_enabled or not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Direct OpenAI is unavailable")
    try:
        turn_id = uuid.UUID(x_pwc_turn)
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability rejected") from None
    received_at = datetime.now(UTC)
    _record_gateway_timing(settings, turn_id, received_at=received_at)
    raw = await request.body()
    if not raw or len(raw) > MAX_OPENAI_REQUEST_BYTES:
        logger.warning("chat OpenAI gateway rejected phase=request_size")
        raise HTTPException(
            status_code=413,
            detail="request_too_large: Model request is too large",
        )
    try:
        untrusted_payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422, detail="Invalid Responses request"
        ) from None
    try:
        row = _scope(
            _bearer(authorization),
            "model",
            x_pwc_session,
            x_pwc_turn,
            db,
            turn_fence=turn_fence,
        )
    except HTTPException:
        logger.warning("chat OpenAI gateway rejected phase=capability_scope")
        raise
    if (
        row.agent_harness != "pi"
        or row.provider_mode != "openai_funded"
        or row.model != settings.chat_openai_luna_route
    ):
        logger.warning("chat OpenAI gateway rejected phase=capability_profile")
        raise HTTPException(status_code=403, detail="Capability rejected")
    try:
        payload, maximum_tokens = _trusted_openai_payload(
            untrusted_payload, row, settings
        )
    except HTTPException:
        logger.warning("chat OpenAI gateway rejected phase=request_contract")
        raise
    trusted_raw = json.dumps(payload, separators=(",", ":")).encode()
    if len(trusted_raw) > MAX_OPENAI_REQUEST_BYTES:
        logger.warning("chat OpenAI gateway rejected phase=trusted_request_size")
        raise HTTPException(
            status_code=413,
            detail="request_too_large: Model request is too large",
        )
    owner_id = _capability_owner(row, db)
    capability_id = row.id
    qualification_scope_id = _qualification_scope_claim(row, db, settings)
    try:
        maximum_requests, maximum_turn_tokens = _provider_turn_limits(row, db, settings)
        ChatCapabilityService(db).meter_provider(
            row,
            request_tokens=max(1, len(trusted_raw) // 4) + maximum_tokens,
            maximum_requests=maximum_requests,
            maximum_tokens=maximum_turn_tokens,
        )
        call_sequence = row.provider_requests
        trace_id = db.scalar(
            select(ChatMessageRecord.langfuse_trace_id)
            .where(
                ChatMessageRecord.turn_id == turn_id,
                ChatMessageRecord.role == "user",
            )
            .order_by(ChatMessageRecord.sequence.desc())
            .limit(1)
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Model execution limit reached"
        ) from None

    call_id = uuid.uuid5(capability_id, f"openai-provider-call:{call_sequence}")
    try:
        reservation = ChatOpenAIBudgetService(db, settings).reserve_call(
            owner_id=owner_id,
            turn_id=turn_id,
            call_id=call_id,
            call_sequence=call_sequence,
            public_model_id=row.model,
            provider_model=settings.chat_openai_model,
            reasoning_effort=row.reasoning_effort,
            bounds=OpenAIRequestBounds(
                request_bytes=len(trusted_raw),
                maximum_output_tokens=maximum_tokens,
            ),
            qualification_scope_id=qualification_scope_id,
        )
        db.commit()
    except OpenAIBudgetExhausted:
        db.rollback()
        _record_provider_error(capability_id, "openai_budget_exhausted")
        raise HTTPException(
            status_code=429,
            detail={
                "code": "openai_budget_exhausted",
                "message": "The Papers With Code direct OpenAI allowance is exhausted.",
            },
        ) from None
    except OpenAILimitExceeded as error:
        db.rollback()
        code = f"openai_{error.scope}_limited"
        _record_provider_error(capability_id, code)
        headers = None
        if error.retry_at is not None:
            headers = {
                "Retry-After": str(
                    max(
                        1,
                        math.ceil((error.retry_at - datetime.now(UTC)).total_seconds()),
                    )
                )
            }
        raise HTTPException(
            status_code=429,
            detail={
                "code": code,
                "message": "Direct OpenAI usage is temporarily limited.",
            },
            headers=headers,
        ) from None
    except OpenAIBudgetError:
        db.rollback()
        _record_provider_error(capability_id, "openai_unavailable")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openai_unavailable",
                "message": "Direct OpenAI is unavailable.",
            },
        ) from None

    ChatOpenAIBudgetService(db, settings).mark_dispatched(call_id)
    db.commit()
    inventory = _offered_tool_inventory(payload)
    provider_trace = start_provider_request_trace(
        settings=settings,
        trace_id=trace_id,
        turn_id=str(turn_id),
        call_sequence=call_sequence,
        model=settings.chat_openai_model,
        public_model_id=row.model,
        provider_mode="openai_funded",
        reasoning_effort=row.reasoning_effort,
        routing_policy="direct",
        service_tier="default",
        accounting_call_id=str(call_id),
        reserved_microusd=reservation.reserved_microusd,
        offered_tool_count=inventory["offered_tool_count"],
        offered_tool_names=inventory["offered_tool_names"],
        offered_tool_digest=inventory["offered_tool_digest"],
    )
    # A FastAPI yield dependency otherwise retains this connection until the
    # StreamingResponse finishes. At fleet concurrency that exhausts the pool
    # while the gateway is merely waiting on OpenAI, blocking sibling calls.
    # All subsequent accounting uses its own short-lived session.
    db.close()
    client = httpx.AsyncClient(timeout=180, follow_redirects=False)
    try:
        upstream = await client.send(
            client.build_request(
                "POST",
                "https://api.openai.com/v1/responses",
                content=trusted_raw,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        with db_manager.session_local() as accounting_db:
            ChatOpenAIBudgetService(accounting_db, settings).mark_cost_unknown(
                call_id, error_code="openai_unavailable"
            )
            accounting_db.commit()
        _record_provider_error(capability_id, "openai_unavailable")
        provider_trace.finish(
            usage=OpenAIResponsesUsageExtractor().result(),
            status_code=None,
            error_code="openai_unavailable",
            tool_call_returned=False,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "openai_unavailable",
                "message": "Direct OpenAI is unavailable.",
            },
        ) from None
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_response_headers",
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )

    request_id = _safe_openai_request_id(
        upstream.headers.get("x-request-id") or upstream.headers.get("request-id")
    )
    if upstream.status_code >= 400:
        error_body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        error_code = classify_openai_error(upstream.status_code, error_body)
        failed_usage = ExtractedOpenAIUsage(
            service_tier="default",
            input_tokens=0,
            cached_input_tokens=0,
            cache_write_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            outcome="failed",
            cost_microusd=0,
        )
        _record_provider_error(capability_id, error_code)
        with db_manager.session_local() as accounting_db:
            ChatOpenAIBudgetService(accounting_db, settings).settle_call(
                call_id,
                failed_usage,
                provider_request_id=request_id,
                error_code=error_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
            accounting_db.commit()
        provider_trace.finish(
            usage=failed_usage,
            status_code=upstream.status_code,
            error_code=error_code,
            tool_call_returned=False,
        )
        status_code = 429 if error_code == "openai_rate_limited" else 503
        raise HTTPException(
            status_code=status_code,
            detail={"code": error_code, "message": "Direct OpenAI request failed."},
        )

    extractor = OpenAIResponsesUsageExtractor()

    async def chunks():
        first_body_byte_ms: int | None = None
        ttft_ms: int | None = None
        cancelled = False
        try:
            async for chunk in upstream.aiter_bytes():
                extractor.feed(chunk)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                if first_body_byte_ms is None:
                    first_body_byte_ms = elapsed_ms
                    _record_gateway_timing(
                        settings,
                        turn_id,
                        phase="upstream_first_body_byte",
                        elapsed_ms=first_body_byte_ms,
                    )
                if ttft_ms is None and extractor.saw_token_delta:
                    ttft_ms = elapsed_ms
                    provider_trace.first_byte(ttft_ms)
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            cancelled = True
            raise
        finally:
            await _close_openai_stream(upstream, client)
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            error_code = _openai_stream_error_code(
                extractor.result().outcome,
                cancelled=cancelled,
            )
            try:
                trace_usage = _settle_openai_call(
                    settings,
                    call_id,
                    extractor,
                    provider_request_id=request_id,
                    latency_ms=elapsed_ms,
                    ttft_ms=ttft_ms,
                    error_code=error_code,
                )
            except Exception as error:
                logger.error(
                    "openai stream settlement failed call=%s error=%s",
                    call_id,
                    type(error).__name__,
                )
                trace_usage = extractor.result()
            provider_trace.finish(
                usage=trace_usage,
                status_code=upstream.status_code,
                error_code=error_code,
                tool_call_returned=extractor.saw_tool_call,
            )

    return StreamingResponse(
        chunks(),
        status_code=upstream.status_code,
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store"},
    )


@app.post("/v1/messages")
async def messages(
    request: Request,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    turn_fence: TurnFenceDependency,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    if request.headers.get("x-pwc-provider-protocol") == "openai-responses":
        return await responses(
            request,
            authorization,
            x_pwc_session,
            x_pwc_turn,
            turn_fence,
            db,
            settings,
        )
    gateway_started = time.perf_counter()
    received_at = datetime.now(UTC)
    try:
        turn_id = uuid.UUID(x_pwc_turn)
    except ValueError:
        raise HTTPException(status_code=403, detail="Capability rejected") from None
    token = _bearer(authorization)
    raw = await request.body()
    if len(raw) > MAX_PROVIDER_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Model request is too large")
    try:
        payload = json.loads(raw)
        model = str(payload["model"])
        maximum_tokens = int(payload.get("max_tokens", 0))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid model request") from None
    if not _output_tokens_allowed(maximum_tokens):
        raise HTTPException(status_code=422, detail="max_tokens is out of range")
    row = _scope(
        token,
        "model",
        x_pwc_session,
        x_pwc_turn,
        db,
        model=model,
        turn_fence=turn_fence,
    )
    provider = settings.chat_route_providers.get(row.model)
    provider_mode = row.provider_mode or (
        "openrouter_funded" if provider == "openrouter" else "huggingface"
    )
    owner_id = _capability_owner(row, db)
    if provider == "openrouter":
        # Supplemental reconciliation metadata is opaque and cannot identify
        # the HF subject at OpenRouter.
        payload["user"] = opaque_owner(owner_id, settings)
        _prefer_fastest_openrouter_provider(payload, settings)
        if (
            settings.chat_initial_payload_optimization_enabled
            and model == settings.chat_effective_pi_prewarm_model
            and row.provider_requests == 0
        ):
            removed = _optimize_initial_deepseek_payload(
                payload,
                settings.chat_initial_payload_optimization_candidate,
            )
            logger.info(
                "chat initial payload optimization turn=%s removed_system=%s "
                "removed_tools=%s",
                _opaque_turn(turn_id),
                removed["system_blocks"],
                removed["tools"],
            )
        effort = getattr(row, "reasoning_effort", None) or "high"
        try:
            _apply_openrouter_reasoning_policy(
                payload, effort, show_reasoning=settings.chat_show_reasoning
            )
        except ValueError:
            raise HTTPException(status_code=403, detail="Capability rejected")
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > MAX_PROVIDER_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Model request is too large")
    provider_url, provider_token, provider_bill_to = _provider_target(row, settings, db)
    capability_id = row.id
    funded_call_id: uuid.UUID | None = None
    try:
        maximum_requests, maximum_turn_tokens = _provider_turn_limits(row, db, settings)
        ChatCapabilityService(db).meter_provider(
            row,
            request_tokens=max(1, len(raw) // 4) + maximum_tokens,
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
        # Capability validation takes a row lock so concurrent SDK model calls
        # receive distinct request counters. Land that bounded mutation before
        # any provider network check; otherwise a slow OpenRouter budget lookup
        # holds the lock for its full timeout and blocks the other model call.
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Model execution limit reached"
        ) from None

    if provider_mode == "openrouter_funded":
        try:
            await require_openrouter_budget(settings)
        except (OpenRouterBudgetExceeded, OpenRouterBudgetUnavailable):
            _record_provider_error(capability_id, "openrouter_unavailable")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "openrouter_unavailable",
                    "message": (
                        "OpenRouter is currently unavailable. However, you can "
                        "still bring your own key in Settings."
                    ),
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
        try:
            funded_call_id = uuid.uuid5(capability_id, f"provider-call:{call_sequence}")
            OpenRouterUserBudgetService(db, settings).reserve_call(
                owner_id,
                turn_id,
                funded_call_id,
                call_sequence,
                model,
                RequestBounds(
                    request_bytes=len(raw),
                    maximum_output_tokens=maximum_tokens,
                    payload=payload,
                ),
                reasoning_effort=effort,
            )
            db.commit()
        except OpenRouterMonthlyBudgetExhausted as error:
            db.rollback()
            _record_provider_error(capability_id, "openrouter_monthly_budget_exhausted")
            usage = OpenRouterUserBudgetService(db, settings).status_percentage(
                owner_id
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "openrouter_monthly_budget_exhausted",
                    "message": (
                        "The remaining shared Papers With Code OpenRouter allowance "
                        "is not enough for another model call."
                    ),
                    "used_percent": usage.used_percent,
                    "remaining_percent": usage.remaining_percent,
                    "resets_at": error.resets_at.isoformat().replace("+00:00", "Z"),
                },
            ) from None
        except OpenRouterAbuseLimitExceeded as error:
            db.rollback()
            code = f"openrouter_{error.scope}_limited"
            _record_provider_error(capability_id, code)
            retry_seconds = max(
                1,
                math.ceil((error.retry_at - datetime.now(UTC)).total_seconds()),
            )
            raise HTTPException(
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
            db.rollback()
            _record_provider_error(capability_id, "openrouter_unavailable")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "openrouter_unavailable",
                    "message": (
                        "OpenRouter is currently unavailable. However, you can "
                        "still bring your own key in Settings."
                    ),
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
    _record_gateway_timing(settings, turn_id, received_at=received_at)

    if funded_call_id is not None:
        # Persist the ambiguous-dispatch boundary before any network bytes can
        # reach OpenRouter. A crash after this point retains the full bound.
        OpenRouterUserBudgetService(db, settings).mark_dispatched(funded_call_id)
        db.commit()

    client = httpx.AsyncClient(timeout=180, follow_redirects=False)
    inventory = _offered_tool_inventory(payload)
    provider_trace = start_provider_request_trace(
        settings=settings,
        trace_id=trace_id,
        turn_id=str(turn_id),
        call_sequence=call_sequence,
        model=model,
        provider_mode=provider_mode,
        reasoning_effort=getattr(row, "reasoning_effort", None) or "high",
        routing_policy=(
            settings.chat_openrouter_routing_policy
            if settings.chat_openrouter_routing_enabled
            else "throughput"
        ),
        offered_tool_count=inventory["offered_tool_count"],
        offered_tool_names=inventory["offered_tool_names"],
        offered_tool_digest=inventory["offered_tool_digest"],
    )
    upstream_headers = _provider_headers(
        provider_token,
        request,
        bill_to=provider_bill_to,
    )
    try:
        upstream = await client.send(
            client.build_request(
                "POST",
                provider_url,
                content=raw,
                headers=upstream_headers,
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        if funded_call_id is not None:
            with db_manager.session_local() as accounting_db:
                OpenRouterUserBudgetService(accounting_db, settings).mark_cost_unknown(
                    funded_call_id
                )
                accounting_db.commit()
        provider_trace.finish(
            usage=OpenRouterUsageExtractor().result(),
            status_code=None,
            error_code="provider_transport_error",
            tool_call_returned=False,
        )
        raise HTTPException(status_code=502, detail="Model provider failed") from None
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_response_headers",
        elapsed_ms=round((time.perf_counter() - gateway_started) * 1000),
    )

    extractor = OpenRouterUsageExtractor()

    if provider_mode == "openrouter_byok" and upstream.status_code == 401:
        with db_manager.session_local() as credential_db:
            OpenRouterBYOKService(credential_db, settings).invalidate_auth_failure(
                owner_id
            )
            capability = credential_db.get(ChatTurnCapability, capability_id)
            if capability is not None:
                ChatCapabilityService(credential_db).record_provider_error(
                    capability, "openrouter_byok_credential_invalid"
                )
            credential_db.commit()
    elif provider_mode == "openrouter_byok":
        provider_error = _byok_provider_error_code(upstream.status_code)
        if provider_error is not None:
            _record_provider_error(capability_id, provider_error)
    elif provider_mode == "openrouter_funded" and upstream.status_code in {402, 403}:
        _record_provider_error(capability_id, "openrouter_unavailable")
    elif provider_mode == "huggingface":
        provider_error = _huggingface_provider_error_code(upstream.status_code)
        if provider_error is not None:
            _record_provider_error(capability_id, provider_error)

    async def chunks():
        first_byte = True
        saw_tool_use = False
        try:
            async for chunk in upstream.aiter_bytes():
                extractor.feed(chunk)
                if not saw_tool_use and _payload_contains_tool_use(chunk):
                    saw_tool_use = True
                if first_byte:
                    first_byte = False
                    elapsed_ms = round((time.perf_counter() - gateway_started) * 1000)
                    provider_trace.first_byte(elapsed_ms)
                    _record_provider_ttft(funded_call_id, elapsed_ms)
                    _record_gateway_timing(
                        settings,
                        turn_id,
                        phase="upstream_first_body_byte",
                        elapsed_ms=elapsed_ms,
                    )
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            if funded_call_id is not None:
                try:
                    _settle_openrouter_call(settings, funded_call_id, extractor)
                except Exception as error:
                    logger.error(
                        "openrouter stream settlement failed call=%s error=%s",
                        funded_call_id,
                        type(error).__name__,
                    )
            provider_trace.finish(
                usage=extractor.result(),
                status_code=upstream.status_code,
                error_code=(
                    None
                    if upstream.status_code < 400
                    else f"provider_http_{upstream.status_code}"
                ),
                tool_call_returned=saw_tool_use,
            )
            logger.info(
                "chat provider stream complete call_class=research turn=%s "
                "duration_ms=%.1f",
                _opaque_turn(turn_id),
                (time.perf_counter() - gateway_started) * 1000,
            )

    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"content-type", "request-id"}
    }
    if payload.get("stream"):
        return StreamingResponse(
            chunks(), status_code=upstream.status_code, headers=headers
        )
    body = await upstream.aread()
    extractor.inspect_complete_response(body)
    elapsed_ms = round((time.perf_counter() - gateway_started) * 1000)
    provider_trace.first_byte(elapsed_ms)
    _record_provider_ttft(funded_call_id, elapsed_ms)
    _record_gateway_timing(
        settings,
        turn_id,
        phase="upstream_first_body_byte",
        elapsed_ms=elapsed_ms,
    )
    await upstream.aclose()
    await client.aclose()
    if funded_call_id is not None:
        try:
            _settle_openrouter_call(settings, funded_call_id, extractor)
        except Exception as error:
            logger.error(
                "openrouter response settlement failed call=%s error=%s",
                funded_call_id,
                type(error).__name__,
            )
    provider_trace.finish(
        usage=extractor.result(),
        status_code=upstream.status_code,
        error_code=(
            None
            if upstream.status_code < 400
            else f"provider_http_{upstream.status_code}"
        ),
        tool_call_returned=_payload_contains_tool_use(body),
    )
    return Response(body, status_code=upstream.status_code, headers=headers)
