"""Private, separately started gateway for sandbox model/catalog/store traffic."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from huggingface_hub.errors import HfHubHTTPError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.chat import LatexPaperSourceEdit
from backend.models.database import (
    ChatSession,
    ChatTurnCapability,
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
    client_identity,
    endpoint_for,
    request_mcp,
)
from backend.services.chat_hf_hub_service import (
    ChatHfHubError,
    ChatHfHubService,
    validate_hf_request,
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
from backend.services.chat_provider_gateway.lifecycle import (
    ProviderCallLifecycle,
)
from backend.services.chat_provider_gateway.anthropic_messages import (
    AnthropicMessagesProtocol,
)
from backend.services.chat_provider_gateway.openai_responses import (
    OpenAIResponsesProtocol,
)
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


def _hf_latency_bucket(elapsed_seconds: float) -> str:
    elapsed_ms = elapsed_seconds * 1000
    for ceiling in (100, 250, 500, 1000, 3000, 10_000):
        if elapsed_ms < ceiling:
            return f"lt_{ceiling}ms"
    return "gte_10000ms"


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


def _capability_owner(row: ChatTurnCapability, db: Session) -> str:
    session = db.get(ChatSession, row.chat_session_id)
    if session is None:
        logger.critical("openrouter funded dispatch missing owner session")
        raise HTTPException(status_code=403, detail="Capability rejected")
    if row.owner_hash != hashlib.sha256(session.hf_user_id.encode()).hexdigest():
        logger.critical("openrouter funded dispatch owner binding mismatch")
        raise HTTPException(status_code=403, detail="Capability rejected")
    return session.hf_user_id


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


def _session_header(request: Request) -> str:
    headers = getattr(request, "headers", None)
    return headers.get("x-pwc-session", "") if headers is not None else ""


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
            client_identity(_session_header(request)),
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


def _provider_call_lifecycle(
    authorization: str,
    x_pwc_session: str,
    x_pwc_turn: str,
    turn_fence: ExternalTurnFenceHeaders | None,
    db: Session,
    settings: Settings,
) -> ProviderCallLifecycle:
    return ProviderCallLifecycle(
        db=db,
        settings=settings,
        authenticate=lambda: _bearer(authorization),
        authorize=lambda token, model: _scope(
            token,
            "model",
            x_pwc_session,
            x_pwc_turn,
            db,
            model=model,
            turn_fence=turn_fence,
        ),
        owner=lambda row: _capability_owner(row, db),
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

    lifecycle = _provider_call_lifecycle(
        authorization, x_pwc_session, x_pwc_turn, turn_fence, db, settings
    )
    return await lifecycle.run(OpenAIResponsesProtocol(settings), request, x_pwc_turn)


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
    """Anthropic Messages relayed to the capability's routed provider."""

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
    lifecycle = _provider_call_lifecycle(
        authorization, x_pwc_session, x_pwc_turn, turn_fence, db, settings
    )
    return await lifecycle.run(AnthropicMessagesProtocol(settings), request, x_pwc_turn)
