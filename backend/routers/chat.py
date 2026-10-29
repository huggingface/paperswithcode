"""Authenticated durable chat sessions and SSE research turns."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from itertools import count
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.mcp_app_registry import WORKER_MCP_PROVIDERS
from backend.chat_configuration import registry
from backend.config import Settings, get_settings
from backend.database.connection import db_manager, get_database_session
from backend.models.chat import (
    ArchiveOldChatsResponse,
    ChatAutocompleteVocabularyResponse,
    ChatAvailabilityResponse,
    ChatBrowserLatencyRequest,
    ChatFeedbackListResponse,
    ChatFeedbackRequest,
    ChatMessageResponse,
    ChatRequest,
    LatexPaperHistoryPage,
    LatexPaperRestoreRequest,
    LatexPaperSaveCompileRequest,
    ChatSandboxSpendResponse,
    ChatQualificationEvidenceRequest,
    ChatQualificationEvidenceResponse,
    ChatQualificationScopeRequest,
    ChatQualificationScopeResponse,
    ChatQualificationTeardownResponse,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionSummary,
    ChatShareDetail,
    ChatShareSummary,
    ChatWebSearchBudgetResponse,
    CreateSessionRequest,
    UpdateSessionRequest,
    sse_event,
)
from backend.models.database import (
    ChatArtifactVersion,
    ChatMessageRecord,
    ChatSession,
)
from backend.routers.inference_billing import inference_credential_for_request
from backend.services.chat_artifact_service import ArtifactError, ChatArtifactService
from backend.services.chat_autocomplete_service import get_autocomplete_vocabulary
from backend.services.chat_feedback_service import (
    ChatFeedbackService,
    ChatFeedbackUnavailable,
)
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.latex_paper_service import LatexPaperService
from backend.services.chat_detached_runtime import (
    detached_chat_runtime,
    replay_detached_frames,
)
from backend.services.chat_live_stream_service import (
    live_chat_stream_registry,
)
from backend.services.chat_mcp_app_proxy import (
    APP_HTML_MIME,
    fetch_excalidraw_app_html,
    forward_excalidraw_mcp,
)
from backend.services.chat_paper_context_service import (
    ChatPaperContextService,
)
from backend.services.chat_pi_release_window import (
    PiReleaseWindowUnavailable,
    require_pi_release_window,
)
from backend.services.chat_sandbox_service import (
    SandboxCleanupUnverified,
    SandboxSessionManager,
)
from backend.services.chat_sandbox_spend_access import (
    chat_sandbox_spend_available,
    chat_sandbox_spend_status,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    owner_from_user,
)
from backend.services.chat_share_service import ChatShareService
from backend.services.chat_stream_service import (
    encode_journal_frame,
)
from backend.services.chat_turn_runner import shared_sandbox_manager
from backend.services.chat_turn_cancellation_coordinator import (
    ChatTurnCancellationCoordinator,
)
from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_durable_lifecycle_observer import durable_lifecycle_observer
from backend.services.chat_durable_qualification_evidence import (
    ChatDurableQualificationEvidenceService,
    QualificationEvidenceUnavailable,
)
from backend.services.chat_web_search_service import (
    ChatWebSearchBudgetService,
    web_search_available,
)
from backend.services.chat_openai_budget_service import ChatOpenAIBudgetService
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetUnavailable,
    openrouter_budget_status,
)
from backend.services.openrouter_byok_service import (
    OpenRouterBYOKService,
    OpenRouterCredentialError,
    OpenRouterCredentialUnavailable,
)
from backend.utils.csrf import has_valid_non_cookie_admin_credential
from backend.services.openrouter_user_budget_service import (
    OpenRouterUserBudgetService,
)
from backend.utils.auth import require_admin, require_user
from backend.utils.client_ip import get_proxied_client_ip

from backend.services.chat_application_service import (
    ChatApplicationService,
    ChatApplicationError,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def detached_turn_coordinator():
    return detached_chat_runtime().coordinator


async def _durable_replay_frames(admission, *, request_id: str, after_sequence: int):
    async for frame in replay_detached_frames(
        detached_turn_coordinator(),
        admission,
        request_id=request_id,
        after_sequence=after_sequence,
    ):
        yield frame


def _last_event_sequence(request: Request) -> int:
    raw = request.headers.get("last-event-id", "0")
    try:
        sequence = int(raw)
    except ValueError:
        sequence = -1
    if sequence < 0 or str(sequence) != raw:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "chat_stream_cursor_invalid",
                "message": "Last-Event-ID must be a non-negative integer.",
            },
        )
    return sequence


CHAT_CAPACITY_RETRY_SECONDS = 5
PRODUCTION_CHAT_URL = "https://paperswithcode.co/chat"
SSE_PROXY_FLUSH_PADDING_BYTES = 2048
_capacity_denials = count(1)
_prewarm_requests: dict[str, deque[float]] = {}
_PREWARM_CLIENT_BUCKETS = 4096
_prewarm_lock = asyncio.Lock()
_prewarm_tasks: dict[str, asyncio.Task[None]] = {}


class PaperContextPrewarmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: str = Field(min_length=1, max_length=200)


def _prewarm_paper(settings: Settings, route_id: str) -> None:
    with db_manager.session_local() as db:
        ChatPaperContextService(db, settings).prewarm(route_id)


async def _run_prewarm(settings: Settings, route_id: str) -> None:
    try:
        await asyncio.to_thread(_prewarm_paper, settings, route_id)
    finally:
        async with _prewarm_lock:
            _prewarm_tasks.pop(route_id, None)


def _raise(exc: ChatServiceError, headers: dict[str, str] | None = None) -> None:
    response_headers = dict(headers or {})
    if exc.code == "chat_capacity":
        response_headers["Retry-After"] = str(CHAT_CAPACITY_RETRY_SECONDS)
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), **exc.details},
        headers=response_headers or None,
    )


def _raise_artifact(error: ArtifactError) -> None:
    status = {
        "artifact_not_found": 404,
        "artifact_unauthorized": 403,
        "artifact_too_large": 413,
        "poster_storage_quota_exceeded": 429,
        "artifact_quota_exceeded": 429,
        "compile_capacity_exceeded": 429,
        "artifact_storage_failed": 503,
        "artifact_deletion_failed": 503,
        "artifact_corrupt": 503,
        "paper_conflict": 409,
    }.get(error.code, 422)
    raise HTTPException(
        status_code=status,
        detail={"code": error.code, "message": str(error)},
    ) from error


class ConnectOpenRouterKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=1, max_length=512)


class SetOpenRouterFallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class AdminCreateHarnessSession(BaseModel):
    """Protected qualification-only session creation contract."""

    model_config = ConfigDict(extra="forbid")
    agent_harness: Literal["claude", "pi"]
    selected_model: str | None = None
    reasoning_effort: Literal["low", "medium", "high", "max"] = "medium"


def _durable_qualification_scope(
    request: Request, settings: Settings
) -> tuple[uuid.UUID, Literal["no_tool", "read", "bash"]] | None:
    raw_scope_id = request.headers.get("X-PWC-Qualification-Scope-ID")
    if raw_scope_id is None:
        return None
    try:
        scope_id = uuid.UUID(raw_scope_id)
    except ValueError:
        scope_id = None
    workload = request.headers.get("X-PWC-Qualification-Workload")
    if (
        settings.environment != "staging"
        or scope_id is None
        or workload not in {"no_tool", "read", "bash"}
        or not (has_valid_non_cookie_admin_credential(request, settings))
    ):
        raise HTTPException(
            status_code=403,
            detail={"code": "qualification_scope_rejected"},
        )
    return scope_id, workload


def _require_openrouter_settings(settings: Settings) -> None:
    if not settings.chat_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _require_same_origin_csrf(request: Request, settings: Settings) -> None:
    if settings.is_deployed:
        origin = request.headers.get("origin")
        expected = f"https://{request.headers.get('host', '').split(':', 1)[0]}"
        site = request.headers.get("sec-fetch-site")
        if site not in {None, "same-origin", "same-site"}:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "csrf_rejected",
                    "message": "Request origin was rejected.",
                },
            )
        if origin == expected:
            return
        referer = request.headers.get("referer", "")
        if (
            request.method == "GET"
            and origin is None
            and site in {"same-origin", "same-site"}
            and (referer == expected or referer.startswith(f"{expected}/"))
        ):
            return
        raise HTTPException(
            status_code=403,
            detail={
                "code": "csrf_rejected",
                "message": "Request origin was rejected.",
            },
        )


def _require_recent_auth(request: Request, user: dict, settings: Settings) -> None:
    from backend.routers.auth import decode_request_session

    issued_at = (decode_request_session(request) or {}).get("iat")
    now = datetime.now(UTC).timestamp()
    if (
        not isinstance(issued_at, (int, float))
        or now - issued_at > settings.chat_openrouter_recent_auth_seconds
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "fresh_auth_required",
                "message": (
                    "For security, refresh your Hugging Face sign-in before "
                    "changing your OpenRouter key."
                ),
            },
        )
    _require_same_origin_csrf(request, settings)


def _busy(session: ChatSession) -> bool:
    from datetime import UTC, datetime

    return bool(
        session.active_turn_id
        and session.active_turn_expires_at
        and session.active_turn_expires_at > datetime.now(UTC)
    )


def _summary(session: ChatSession) -> ChatSessionSummary:
    primary = getattr(session, "primary_paper", None)
    primary_projection = None
    if primary is not None:
        # External papers have no arXiv id; their reader route is the paper id.
        primary_projection = {
            "id": str(primary.id),
            "route_id": primary.arxiv_id or str(primary.id),
            "title": primary.title,
            "arxiv_id": primary.arxiv_id,
        }
    return ChatSessionSummary(
        id=session.id,
        title=session.title,
        # Hidden models report the model their next turn will actually use.
        selected_model=registry.canonical_model_id(
            get_settings(), session.selected_model
        ),
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        is_busy=_busy(session),
        web_search_enabled=session.web_search_enabled,
        reasoning_effort=getattr(session, "reasoning_effort", None) or "high",
        primary_paper=primary_projection,
    )


def _message(row: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        turn_id=row.turn_id,
        sequence=row.sequence,
        role=row.role,
        content=row.content,
        paper_mentions=row.paper_mentions or [],
        paper_selection=getattr(row, "paper_selection", None),
        viewer_context=getattr(row, "viewer_context", None),
        revision=row.revision,
        status=row.status,
        citations=row.citations or [],
        followups=row.followups or [],
        display_blocks=row.display_blocks or [],
        model=row.model,
        reasoning_effort=getattr(row, "reasoning_effort", None) or "high",
        finish_reason=row.finish_reason,
        error_code=row.error_code,
        created_at=row.created_at,
    )


@router.get("/models")
def list_models(
    user: dict = Depends(require_user), settings: Settings = Depends(get_settings)
):
    del user
    return {
        "items": [
            {
                "id": choice["id"],
                "label": choice["label"],
                "provider": choice["provider"],
                "sponsored": choice["funding_mode"] == "hf_org_funded",
                "reasoning_efforts": ["low", "medium", "high", "max"],
            }
            for choice in settings.chat_model_choices
        ],
        "default_model": settings.chat_model_choices[0]["id"],
    }


def _require_mcp_apps_host(settings: Settings) -> None:
    if (
        not settings.chat_enabled
        or not settings.chat_mcp_apps_host_enabled
        or settings.environment not in {"staging", "production"}
    ):
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/mcp-apps/excalidraw/html")
async def excalidraw_app_html(
    request: Request,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Cached Excalidraw App shell for historical and live diagram frames."""
    del user
    _require_mcp_apps_host(settings)
    _require_same_origin_csrf(request, settings)
    # The App runs in an iframe beside private diagram content, so every
    # environment serves only the reviewed HTML digest, never upstream changes.
    expected_sha256 = next(
        provider.app_html_sha256
        for provider in WORKER_MCP_PROVIDERS
        if provider.id == "excalidraw"
    )
    html = await fetch_excalidraw_app_html(expected_sha256=expected_sha256)
    return Response(content=html, media_type=APP_HTML_MIME)


@router.api_route("/mcp-apps/excalidraw", methods=["GET", "POST", "DELETE"])
async def proxy_excalidraw_mcp_app(
    request: Request,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Same-origin App-host proxy; never forwards PwC cookies."""
    del user
    _require_mcp_apps_host(settings)
    _require_same_origin_csrf(request, settings)
    return await forward_excalidraw_mcp(request)


@router.get(
    "/autocomplete-vocabulary", response_model=ChatAutocompleteVocabularyResponse
)
def chat_autocomplete_vocabulary(
    response: Response, db: Session = Depends(get_database_session)
):
    """Public catalog names that chat composers complete with Tab."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"names": get_autocomplete_vocabulary(db)}


@router.get("/availability", response_model=ChatAvailabilityResponse)
def chat_availability():
    """Content-free public state; internal warning and accounting stay private."""
    settings = get_settings()
    search_available = web_search_available(settings)
    if (
        not settings.chat_public_admission_enabled
        or not settings.chat_sandbox_admission_enabled
    ):
        return {
            "status": "paused",
            "reason": "chat_temporarily_disabled",
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": False,
            "native_pdf_reader_enabled": settings.native_pdf_reader_enabled,
            "paper_reader_chat_enabled": settings.paper_reader_chat_enabled,
            "paper_reader_selection_enabled": settings.paper_reader_selection_enabled,
            "paper_reader_citations_enabled": settings.paper_reader_citations_enabled,
            "paper_artifacts_enabled": (
                settings.chat_artifacts_enabled
                and settings.chat_latex_paper_enabled
                and settings.chat_latex_compiler_jobs_enabled
            ),
        }
    if (
        settings.chat_default_backend != "modal_cli"
        or not settings.chat_sandbox_spend_enforcement_enabled
    ):
        return {
            "status": "available",
            "reason": None,
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": search_available,
            "native_pdf_reader_enabled": settings.native_pdf_reader_enabled,
            "paper_reader_chat_enabled": settings.paper_reader_chat_enabled,
            "paper_reader_selection_enabled": settings.paper_reader_selection_enabled,
            "paper_reader_citations_enabled": settings.paper_reader_citations_enabled,
            "paper_artifacts_enabled": (
                settings.chat_artifacts_enabled
                and settings.chat_latex_paper_enabled
                and settings.chat_latex_compiler_jobs_enabled
            ),
        }
    if chat_sandbox_spend_available(
        settings,
        session_factory=db_manager.session_local,
    ):
        return {
            "status": "available",
            "reason": None,
            "expected_recovery_at": None,
            "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
            "web_search_available": search_available,
            "native_pdf_reader_enabled": settings.native_pdf_reader_enabled,
            "paper_reader_chat_enabled": settings.paper_reader_chat_enabled,
            "paper_reader_selection_enabled": settings.paper_reader_selection_enabled,
            "paper_reader_citations_enabled": settings.paper_reader_citations_enabled,
            "paper_artifacts_enabled": (
                settings.chat_artifacts_enabled
                and settings.chat_latex_paper_enabled
                and settings.chat_latex_compiler_jobs_enabled
            ),
        }
    return {
        "status": "paused",
        "reason": "chat_temporarily_disabled",
        "expected_recovery_at": None,
        "paper_mentions_enabled": settings.chat_paper_mentions_enabled,
        "web_search_available": False,
        "native_pdf_reader_enabled": settings.native_pdf_reader_enabled,
        "paper_reader_chat_enabled": settings.paper_reader_chat_enabled,
        "paper_reader_selection_enabled": settings.paper_reader_selection_enabled,
        "paper_reader_citations_enabled": settings.paper_reader_citations_enabled,
        "paper_artifacts_enabled": (
            settings.chat_artifacts_enabled
            and settings.chat_latex_paper_enabled
            and settings.chat_latex_compiler_jobs_enabled
        ),
    }


@router.get(
    "/admin/web-search-budget",
    dependencies=[Depends(require_admin)],
    response_model=ChatWebSearchBudgetResponse,
)
def chat_web_search_budget():
    settings = get_settings()
    if not settings.chat_web_search_enabled:
        raise HTTPException(status_code=404, detail="Web search is not enabled")
    with db_manager.session_local() as db, db.begin():
        return ChatWebSearchBudgetService(db, settings).status()


@router.get(
    "/admin/sandbox-spend",
    dependencies=[Depends(require_admin)],
    response_model=ChatSandboxSpendResponse,
)
def chat_sandbox_spend(environment: str | None = None):
    settings = get_settings()
    if environment is not None:
        if not environment.startswith(f"{settings.environment}-q-"):
            raise HTTPException(status_code=404, detail="Unknown qualification")
        settings = settings.model_copy(update={"environment": environment})
    return chat_sandbox_spend_status(
        settings,
        session_factory=db_manager.session_local,
    )


@router.post(
    "/admin/qualification-scopes",
    dependencies=[Depends(require_admin)],
    response_model=ChatQualificationScopeResponse,
    status_code=201,
)
def create_chat_qualification_scope(
    body: ChatQualificationScopeRequest,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Issue one release-bound, server-timed protected staging cohort."""
    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        scope = ChatDurableQualificationEvidenceService(db).create_scope(
            run_id=body.run_id,
            profile=body.profile,
            settings=settings,
        )
        db.commit()
        return scope
    except QualificationEvidenceUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "qualification_scope_unavailable"},
        ) from None


@router.post(
    "/admin/qualification-evidence",
    dependencies=[Depends(require_admin)],
    response_model=ChatQualificationEvidenceResponse,
)
def chat_qualification_evidence(
    body: ChatQualificationEvidenceRequest,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Return the exact protected run cohort without identities or content."""
    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        evidence = ChatDurableQualificationEvidenceService(db).collect(
            scope_id=body.scope_id, settings=settings
        )
        db.commit()
        return evidence
    except QualificationEvidenceUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "qualification_evidence_unavailable"},
        ) from None


@router.post(
    "/admin/qualification-scopes/{scope_id}/teardown",
    dependencies=[Depends(require_admin)],
    response_model=ChatQualificationTeardownResponse,
)
async def teardown_chat_qualification_scope(
    scope_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Evict only the exact server-scoped qualification cohort."""
    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        proof = await ChatDurableQualificationEvidenceService(db).teardown_scope(
            scope_id=scope_id,
            settings=settings,
            sandbox_manager=shared_sandbox_manager(settings),
        )
        db.commit()
        return proof
    except QualificationEvidenceUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "qualification_teardown_incomplete"},
        ) from None


@router.delete(
    "/admin/qualification-scopes/{scope_id}",
    dependencies=[Depends(require_admin)],
    status_code=204,
)
def delete_chat_qualification_scope(
    scope_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    ChatDurableQualificationEvidenceService(db).cleanup_scope(scope_id)
    db.commit()
    return Response(status_code=204)


@router.get("/usage")
async def get_openrouter_usage(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_openrouter_settings(settings)
    try:
        user_status = OpenRouterUserBudgetService(db, settings).status_percentage(
            user["hf_user_id"]
        )
    except Exception as error:
        logger.error("openrouter usage status failed error=%s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openrouter_usage_unavailable",
                "message": "OpenRouter usage is temporarily unavailable.",
            },
        ) from None
    result = user_status.public_dict()
    try:
        shared_status = await openrouter_budget_status(settings)
    except OpenRouterBudgetUnavailable:
        result.update(
            available=False,
            unavailable_reason="provider_status_unavailable",
        )
        return result
    if not user_status.available:
        unavailable_reason = "personal_allowance_exhausted"
    else:
        unavailable_reason = shared_status.unavailable_reason
    result.update(
        available=user_status.available and shared_status.within_budget,
        unavailable_reason=unavailable_reason,
    )
    return result


@router.get("/openai-usage")
def get_openai_usage(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.chat_enabled or not settings.chat_openai_direct_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    status = ChatOpenAIBudgetService(db, settings).status_percentage(user["hf_user_id"])
    return status.public_dict()


@router.get("/openrouter-key")
def get_openrouter_key_status(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_openrouter_settings(settings)
    try:
        return (
            OpenRouterBYOKService(db, settings).status(user["hf_user_id"]).public_dict()
        )
    except Exception as error:
        logger.error(
            "openrouter credential status failed error=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "openrouter_credential_unavailable",
                "message": "Your OpenRouter key status is temporarily unavailable.",
            },
        ) from None


@router.put("/openrouter-key")
async def connect_openrouter_key(
    body: ConnectOpenRouterKey,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_openrouter_settings(settings)
    _require_recent_auth(request, user, settings)
    try:
        status = await OpenRouterBYOKService(db, settings).connect(
            user["hf_user_id"], body.api_key
        )
        db.commit()
        return status.public_dict()
    except OpenRouterCredentialError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from None
    except OpenRouterCredentialUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="OpenRouter key verification is temporarily unavailable.",
        ) from None


@router.patch("/openrouter-key")
def set_openrouter_fallback(
    body: SetOpenRouterFallback,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_openrouter_settings(settings)
    if body.enabled:
        _require_recent_auth(request, user, settings)
    else:
        _require_same_origin_csrf(request, settings)
    try:
        status = OpenRouterBYOKService(db, settings).set_fallback_enabled(
            user["hf_user_id"], body.enabled
        )
        db.commit()
        return status.public_dict()
    except OpenRouterCredentialError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.delete("/openrouter-key", status_code=204)
def disconnect_openrouter_key(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_openrouter_settings(settings)
    _require_recent_auth(request, user, settings)
    OpenRouterBYOKService(db, settings).disconnect(user["hf_user_id"])
    db.commit()
    return Response(status_code=204)


@router.post("/sessions", response_model=ChatSessionSummary, status_code=201)
def create_session(
    body: CreateSessionRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.chat_public_admission_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "chat_temporarily_disabled",
                "message": "Chat is temporarily disabled. No chat was created.",
            },
        )
    try:
        session = ChatSessionService(db, settings).create_session(
            owner_from_user(user), body.selected_model, body.reasoning_effort
        )
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post(
    "/admin/sessions",
    response_model=ChatSessionSummary,
    status_code=201,
    dependencies=[],
)
def create_admin_harness_session(
    body: AdminCreateHarnessSession,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Create a fresh pinned qualification chat without exposing a public picker."""

    if settings.environment != "staging":
        raise HTTPException(status_code=404, detail="Not found")
    if body.agent_harness == "pi":
        try:
            require_pi_release_window()
        except PiReleaseWindowUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "pi_qualification_unavailable",
                    "message": str(exc),
                },
            ) from exc
    subject = str(admin.get("hf_subject") or "admin-api-token")
    owner_id = (
        str(admin.get("chat_qualification_owner") or subject)
        if admin.get("source") == "cookie"
        else f"operator:{subject}"
    )
    owner = ChatOwner(
        hf_user_id=owner_id,
        hf_username=str(admin.get("username") or "operator"),
    )
    try:
        session = ChatSessionService(db, settings).create_session(
            owner,
            body.selected_model,
            body.reasoning_effort,
            agent_harness_override=body.agent_harness,
            operator_subject=subject,
        )
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/sessions", response_model=ChatSessionList)
def list_sessions(
    limit: int = Query(50, ge=1, le=50),
    cursor: str | None = None,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        rows, next_cursor = ChatSessionService(db, settings).list_sessions(
            owner_from_user(user), cursor, limit
        )
        return ChatSessionList(
            items=[_summary(row) for row in rows], next_cursor=next_cursor
        )
    except ChatServiceError as exc:
        _raise(exc)


@router.post("/sessions/archive-old", response_model=ArchiveOldChatsResponse)
def archive_old_sessions(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        archived_count = ChatSessionService(db, settings).archive_old_sessions(
            owner_from_user(user), days=30
        )
        db.commit()
        return ArchiveOldChatsResponse(archived_count=archived_count)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/sessions/archive-oldest", response_model=ArchiveOldChatsResponse)
def archive_oldest_sessions(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        archived_count = ChatSessionService(db, settings).archive_oldest_sessions(
            owner_from_user(user), limit=50
        )
        db.commit()
        return ArchiveOldChatsResponse(archived_count=archived_count)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: uuid.UUID,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        session, messages = ChatSessionService(db, settings).get_session(
            owner_from_user(user), session_id
        )
        return ChatSessionDetail(
            **_summary(session).model_dump(),
            messages=[_message(row) for row in messages],
            transcript_status=session.transcript_status,
            latex_paper=LatexPaperService(db, settings).get_descriptor(
                owner_from_user(user).hf_user_id, session.id
            ),
        )
    except ChatServiceError as exc:
        _raise(exc)


@router.get(
    "/sessions/{session_id}/stream",
    summary="Reconnect to an active research-assistant response",
)
def reconnect_active_stream(
    session_id: uuid.UUID,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    after_sequence = (
        _last_event_sequence(request)
        if settings.chat_durable_turn_dispatch_enabled
        else 0
    )
    owner = owner_from_user(user)
    try:
        session, _messages = ChatSessionService(db, settings).get_session(
            owner, session_id
        )
    except ChatServiceError as exc:
        _raise(exc)
    if session.active_turn_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "chat_not_busy",
                "message": "This chat is not generating.",
            },
        )
    stream = None
    if not settings.chat_durable_turn_dispatch_enabled:
        stream = live_chat_stream_registry().get(
            session_id, session.active_turn_id, owner.hf_user_id
        )
        if stream is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_stream_unavailable",
                    "message": "The active response cannot be reconnected.",
                },
            )

    async def event_stream():
        yield b": " + (b" " * SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
        if settings.chat_durable_turn_dispatch_enabled:
            async for frame in detached_turn_coordinator().subscribe(
                turn_id=session.active_turn_id, after_sequence=after_sequence
            ):
                yield encode_journal_frame(frame)
        else:
            assert stream is not None
            async for frame in stream.subscribe():
                if frame.event is None:
                    yield b": ping\n\n"
                else:
                    yield sse_event(frame.event, **frame.payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/sessions/{session_id}/share",
    response_model=ChatShareSummary,
)
def create_or_refresh_share(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        service = ChatShareService(db, settings)
        share = service.create_or_refresh(owner_from_user(user), session_id)
        storage = ChatArtifactService(db, settings).storage
        try:
            db.commit()
        except Exception:
            db.rollback()
            for prefix in service.new_storage_prefixes:
                try:
                    storage.delete_prefix(prefix)
                except Exception:
                    logger.error(
                        "failed public poster rollback cleanup prefix=%s", prefix
                    )
            raise
        for prefix in service.stale_storage_prefixes:
            try:
                storage.delete_prefix(prefix)
            except Exception:
                logger.warning("stale public poster cleanup failed share=%s", share.id)
        db.refresh(share)
        return ChatShareSummary(
            share_id=share.id,
            public_path=f"/share/{share.id}",
            created_at=share.created_at,
            updated_at=share.updated_at,
        )
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.get("/artifacts/storage")
def get_artifact_storage_status(
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "private, no-store"
    return ChatArtifactService(db, settings).storage_status(
        owner_from_user(user).hf_user_id
    )


@router.get("/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: uuid.UUID,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        service = ChatArtifactService(db, settings)
        artifact = service.get_artifact(owner_from_user(user).hf_user_id, artifact_id)
        if artifact.kind == "latex_paper":
            return LatexPaperService(db, settings).get_artifact_descriptor(
                owner_from_user(user).hf_user_id, artifact_id
            )
        versions = list(
            db.scalars(
                select(ChatArtifactVersion)
                .where(
                    ChatArtifactVersion.artifact_id == artifact.id,
                    ChatArtifactVersion.state == "ready",
                )
                .order_by(ChatArtifactVersion.version)
            )
        )
        return {
            "artifact_id": artifact.id,
            "identifier": artifact.identifier,
            "artifact_kind": artifact.kind,
            "title": artifact.title,
            "latest_version": artifact.latest_version,
            "versions": [
                {
                    "version_id": item.id,
                    "version": item.version,
                    "gate_status": item.gate_status,
                    "preview_mime": item.preview_mime,
                    "total_bytes": item.byte_count,
                    "created_at": item.created_at,
                }
                for item in versions
            ],
        }
    except ArtifactError as error:
        _raise_artifact(error)


@router.post("/artifacts/{artifact_id}/save-compile")
def save_compile_latex_paper(
    artifact_id: uuid.UUID,
    request: LatexPaperSaveCompileRequest,
    http_request: Request,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Publish a complete human source snapshot; drafts never reach this route."""
    response.headers["Cache-Control"] = "private, no-store"
    _require_same_origin_csrf(http_request, settings)
    try:
        descriptor = LatexPaperService(db, settings).save_human_version(
            owner_id=owner_from_user(user).hf_user_id,
            artifact_id=artifact_id,
            expected_parent_version_id=request.expected_parent_version_id,
            files={file.path: file.content.encode("utf-8") for file in request.files},
        )
        db.commit()
        return descriptor
    except ArtifactError as error:
        db.rollback()
        _raise_artifact(error)


@router.post("/artifacts/{artifact_id}/figures")
def upload_latex_paper_figure(
    artifact_id: uuid.UUID,
    http_request: Request,
    response: Response,
    expected_parent_version_id: uuid.UUID = Form(),
    path: str = Form(),
    figure: UploadFile = File(),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Publish a vetted PNG/JPEG/PDF figure as an immutable owner-only version."""
    response.headers["Cache-Control"] = "private, no-store"
    _require_same_origin_csrf(http_request, settings)
    try:
        data = figure.file.read(settings.chat_artifact_max_image_bytes + 1)
        descriptor = LatexPaperService(db, settings).upload_figure(
            owner_id=owner_from_user(user).hf_user_id,
            artifact_id=artifact_id,
            expected_parent_version_id=expected_parent_version_id,
            path=path,
            data=data,
            declared_media_type=figure.content_type or "",
        )
        db.commit()
        return descriptor
    except ArtifactError as error:
        db.rollback()
        _raise_artifact(error)


@router.post("/artifacts/{artifact_id}/refresh-compile")
def refresh_latex_paper_compile(
    artifact_id: uuid.UUID,
    http_request: Request,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Owner-driven, idempotent polling keeps a queued canvas up to date."""
    response.headers["Cache-Control"] = "private, no-store"
    _require_same_origin_csrf(http_request, settings)
    try:
        descriptor = LatexPaperService(db, settings).refresh_compile(
            owner_id=owner_from_user(user).hf_user_id,
            artifact_id=artifact_id,
        )
        db.commit()
        return descriptor
    except ArtifactError as error:
        db.rollback()
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions", response_model=LatexPaperHistoryPage)
def get_latex_paper_history(
    artifact_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=16),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Return one bounded page of private immutable-version audit metadata."""
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return LatexPaperService(db, settings).list_history(
            owner_id=owner_from_user(user).hf_user_id,
            artifact_id=artifact_id,
            limit=limit,
            cursor=cursor,
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.post("/artifacts/{artifact_id}/versions/restore")
def restore_latex_paper_version(
    artifact_id: uuid.UUID,
    request: LatexPaperRestoreRequest,
    http_request: Request,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Restore a snapshot by publishing a newly compiled immutable child."""
    response.headers["Cache-Control"] = "private, no-store"
    _require_same_origin_csrf(http_request, settings)
    try:
        descriptor = LatexPaperService(db, settings).restore_version(
            owner_id=owner_from_user(user).hf_user_id,
            artifact_id=artifact_id,
            source_version_id=request.source_version_id,
            expected_parent_version_id=request.expected_parent_version_id,
        )
        db.commit()
        return descriptor
    except ArtifactError as error:
        db.rollback()
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/manifest")
def get_artifact_manifest(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    response: Response,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    try:
        owner = owner_from_user(user).hf_user_id
        artifact = ChatArtifactService(db, settings).get_artifact(owner, artifact_id)
        if artifact.kind == "latex_paper":
            return LatexPaperService(db, settings).get_manifest(
                owner, artifact_id, version_id
            )
        return (
            ChatArtifactService(db, settings)
            .get_version(owner, artifact_id, version_id)
            .manifest
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.delete("/artifacts/{artifact_id}/versions/{version_id}", status_code=204)
def delete_artifact_version(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    http_request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_same_origin_csrf(http_request, settings)
    try:
        owner = owner_from_user(user).hf_user_id
        artifact = ChatArtifactService(db, settings).get_artifact(owner, artifact_id)
        if artifact.kind == "latex_paper":
            LatexPaperService(db, settings).delete_version(
                owner, artifact_id, version_id
            )
        else:
            ChatArtifactService(db, settings).delete_version(
                owner, artifact_id, version_id
            )
        db.commit()
        return Response(status_code=204)
    except ArtifactError as error:
        db.rollback()
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/preview")
def get_artifact_preview(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        service = ChatArtifactService(db, settings)
        owner = owner_from_user(user).hf_user_id
        artifact = service.get_artifact(owner, artifact_id)
        if artifact.kind == "latex_paper":
            item = LatexPaperService(db, settings).read_preview_pdf(
                owner, artifact_id, version_id
            )
        else:
            version = service.get_version(owner, artifact_id, version_id)
            item = service.read_version_file(
                owner, artifact_id, version_id, version.preview_path, role="preview"
            )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Disposition": f'inline; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/source/{path:path}")
def get_artifact_source(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    path: str,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        owner = owner_from_user(user).hf_user_id
        artifact = ChatArtifactService(db, settings).get_artifact(owner, artifact_id)
        if artifact.kind == "latex_paper":
            item = LatexPaperService(db, settings).read_source_file(
                owner, artifact_id, version_id, path
            )
        else:
            item = ChatArtifactService(db, settings).read_version_file(
                owner, artifact_id, version_id, path, role="source"
            )
        return Response(
            content=item.data,
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Disposition": f'attachment; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/figures/{path:path}")
def get_latex_paper_figure(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    path: str,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Serve a private figure as a download, never executable active content."""
    try:
        item = LatexPaperService(db, settings).read_figure(
            owner_from_user(user).hf_user_id, artifact_id, version_id, path
        )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Security-Policy": "sandbox; default-src 'none'",
                "Content-Disposition": f'attachment; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/export/pdf")
def download_latex_paper_pdf(
    artifact_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Download the owner's last successfully compiled paper PDF."""
    try:
        item = LatexPaperService(db, settings).export_last_successful_pdf(
            owner_from_user(user).hf_user_id, artifact_id
        )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Disposition": f'attachment; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/export/source.zip")
def download_latex_paper_source_zip(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Download one owner-selected immutable paper source bundle."""
    try:
        item = LatexPaperService(db, settings).export_source_zip(
            owner_from_user(user).hf_user_id, artifact_id, version_id
        )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Disposition": f'attachment; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get("/artifacts/{artifact_id}/versions/{version_id}/download/{path:path}")
def download_artifact_file(
    artifact_id: uuid.UUID,
    version_id: uuid.UUID,
    path: str,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        item = ChatArtifactService(db, settings).read_version_file(
            owner_from_user(user).hf_user_id,
            artifact_id,
            version_id,
            path,
            role="download",
        )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "private, immutable, max-age=31536000",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{item.filename}"',
            },
        )
    except ArtifactError as error:
        _raise_artifact(error)


@router.get(
    "/sessions/{session_id}/public-share",
    response_model=ChatShareSummary,
)
def get_session_public_share(
    session_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Let visitors who open a private chat URL land on its public share."""
    response.headers["Cache-Control"] = "no-store"
    try:
        share = ChatShareService(db, settings).get_for_session(session_id)
    except ChatServiceError as exc:
        _raise(exc, {"Cache-Control": "no-store"})
    return ChatShareSummary(
        share_id=share.id,
        public_path=f"/share/{share.id}",
        created_at=share.created_at,
        updated_at=share.updated_at,
    )


@router.get("/shares/{share_id}", response_model=ChatShareDetail)
def get_shared_chat(
    share_id: str,
    response: Response,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return ChatShareService(db, settings).get_public(share_id)
    except ChatServiceError as exc:
        _raise(exc, {"Cache-Control": "no-store"})


def _public_artifact_response(
    share_id: str,
    capability_id: str,
    *,
    role: Literal["preview", "pdf"],
    disposition: Literal["inline", "attachment"],
    db: Session,
    settings: Settings,
) -> Response:
    try:
        item = ChatShareService(db, settings).read_public_artifact(
            share_id, capability_id, role=role
        )
        return Response(
            content=item.data,
            media_type=item.media_type,
            headers={
                "Cache-Control": "public, immutable, max-age=31536000",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'{disposition}; filename="{item.filename}"',
            },
        )
    except ChatServiceError as exc:
        _raise(exc, {"Cache-Control": "no-store"})


@router.get("/shares/{share_id}/artifacts/{capability_id}/preview")
def get_shared_artifact_preview(
    share_id: str,
    capability_id: str,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    return _public_artifact_response(
        share_id,
        capability_id,
        role="preview",
        disposition="inline",
        db=db,
        settings=settings,
    )


@router.get("/shares/{share_id}/artifacts/{capability_id}/download/png")
def download_shared_artifact_png(
    share_id: str,
    capability_id: str,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    return _public_artifact_response(
        share_id,
        capability_id,
        role="preview",
        disposition="attachment",
        db=db,
        settings=settings,
    )


@router.get("/shares/{share_id}/artifacts/{capability_id}/download/pdf")
def download_shared_artifact_pdf(
    share_id: str,
    capability_id: str,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    return _public_artifact_response(
        share_id,
        capability_id,
        role="pdf",
        disposition="attachment",
        db=db,
        settings=settings,
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionSummary)
def update_session(
    session_id: uuid.UUID,
    body: UpdateSessionRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    service = ChatSessionService(db, settings)
    owner = owner_from_user(user)
    try:
        session = None
        if body.title is not None:
            session = service.rename_session(owner, session_id, body.title)
        if body.selected_model is not None:
            session = service.select_model(owner, session_id, body.selected_model)
        if body.reasoning_effort is not None:
            session = service.select_reasoning_effort(
                owner, session_id, body.reasoning_effort
            )
        assert session is not None
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/sessions/{session_id}/cancel", status_code=204)
async def cancel_active_turn(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    owner = owner_from_user(user)
    if getattr(settings, "chat_durable_turn_dispatch_enabled", False):
        try:
            coordinator_kwargs = (
                {"external_cancel": detached_chat_runtime(settings).cancel}
                if settings.chat_external_pi_admission_enabled
                else {}
            )
            await ChatTurnCancellationCoordinator(
                db,
                settings,
                shared_sandbox_manager(settings),
                observe=durable_lifecycle_observer(settings),
                **coordinator_kwargs,
            ).cancel(owner, session_id)
        except ChatServiceError as exc:
            db.rollback()
            _raise(exc)
        return Response(status_code=204)
    try:
        turn_id = ChatSessionService(db, settings).request_legacy_cancel(
            owner, session_id
        )
        db.commit()
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)
    if turn_id is None:
        return Response(status_code=204)
    manager = shared_sandbox_manager(settings)
    cancelled = await manager.cancel(session_id, turn_id)
    if not cancelled:
        await manager.terminate(session_id, failure_code="cancel_control_missing")
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        service = ChatSessionService(db, settings)
        receipt = service.delete_session(owner_from_user(user), session_id)
        if receipt.sandbox_id or receipt.snapshot_id:
            try:
                await SandboxSessionManager(settings).cleanup_deleted(
                    receipt.sandbox_id, receipt.snapshot_id
                )
            except SandboxCleanupUnverified as exc:
                raise ChatServiceError(
                    "chat_deletion_unverified",
                    503,
                    "Chat workspace deletion could not be verified. Retry before relying on removal.",
                ) from exc
        artifact_storage = ChatArtifactService(db, settings).storage
        try:
            for prefix in receipt.artifact_prefixes:
                artifact_storage.delete_prefix(prefix)
        except ArtifactError as exc:
            raise ChatServiceError(
                "chat_deletion_unverified",
                503,
                "Poster storage deletion could not be verified. Retry before relying on removal.",
            ) from exc
        db.commit()
        if not service.deletion_complete(receipt):
            raise ChatServiceError(
                "chat_deletion_unverified",
                503,
                "Chat deletion could not be verified. Retry before relying on removal.",
            )
        return Response(status_code=204)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/paper-context/prewarm")
async def prewarm_paper_context(body: PaperContextPrewarmRequest, request: Request):
    """Best-effort public warming; paper content never leaves the server."""
    settings = get_settings()
    if not settings.chat_paper_mentions_enabled:
        return {"status": "disabled"}
    started = time.perf_counter()
    client_ip = get_proxied_client_ip(request) or "unknown"
    now = time.monotonic()
    async with _prewarm_lock:
        if (
            client_ip not in _prewarm_requests
            and len(_prewarm_requests) >= _PREWARM_CLIENT_BUCKETS
        ):
            _prewarm_requests.pop(next(iter(_prewarm_requests)))
        recent = _prewarm_requests.setdefault(client_ip, deque())
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 30:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "paper_context_rate_limited",
                    "message": "Try again shortly.",
                },
                headers={"Retry-After": "5"},
            )
        recent.append(now)
        existing = _prewarm_tasks.get(body.route_id)
        coalesced = existing is not None
        if existing is None:
            if len(_prewarm_tasks) >= 4:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "paper_context_busy",
                        "message": "Try again shortly.",
                    },
                    headers={"Retry-After": "2"},
                )
            existing = asyncio.create_task(_run_prewarm(settings, body.route_id))
            _prewarm_tasks[body.route_id] = existing
    try:
        await asyncio.wait_for(
            asyncio.shield(existing),
            timeout=settings.chat_paper_context_timeout_seconds,
        )
    except TimeoutError as exc:
        logger.info(
            "chat paper prewarm outcome=timeout coalesced=%s elapsed_ms=%s",
            coalesced,
            round((time.perf_counter() - started) * 1000),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "paper_context_unavailable",
                "message": "Paper context preparation timed out.",
            },
            headers={"Retry-After": "2"},
        ) from exc
    except ChatServiceError as exc:
        logger.info(
            "chat paper prewarm outcome=%s coalesced=%s elapsed_ms=%s",
            exc.code,
            coalesced,
            round((time.perf_counter() - started) * 1000),
        )
        _raise(exc)
    logger.info(
        "chat paper prewarm outcome=ready coalesced=%s elapsed_ms=%s",
        coalesced,
        round((time.perf_counter() - started) * 1000),
    )
    return {"status": "ready"}


@router.post("/stream", summary="Stream a durable research-assistant response")
async def stream_chat(
    body: ChatRequest, request: Request, user: dict = Depends(require_user)
):
    settings = get_settings()
    qualification_scope = _durable_qualification_scope(request, settings)
    after_sequence = (
        _last_event_sequence(request)
        if settings.chat_durable_turn_dispatch_enabled
        else 0
    )
    credential = inference_credential_for_request(request, user, settings)
    owner = owner_from_user(
        user,
        inference_token=credential.token if credential else None,
        inference_bill_to=credential.bill_to if credential else None,
    )
    try:
        outcome = await ChatApplicationService(settings).start_turn(
            body=body,
            owner=owner,
            user_role=user.get("role"),
            inference_credential_present=credential is not None,
            qualification_scope=qualification_scope,
            after_sequence=after_sequence,
        )
    except ChatApplicationError as exc:
        raise HTTPException(exc.status_code, exc.detail, headers=exc.headers) from exc
    except ChatServiceError as exc:
        if exc.code == "chat_capacity":
            logger.warning(
                "chat capacity denied environment=%s release=%s active=%s ceiling=%s denial_count=%s retry_seconds=%s",
                settings.environment,
                settings.release_id,
                exc.active_count,
                settings.chat_max_concurrency,
                next(_capacity_denials),
                CHAT_CAPACITY_RETRY_SECONDS,
            )
        _raise(exc)

    async def event_stream():
        # Some edge POPs buffer small initial HTTP/2 DATA frames even when the
        # origin and nginx both disable response buffering. An ignored SSE
        # comment above the common 2 KiB threshold forces those intermediaries
        # to flush the response before the first model delta arrives.
        yield b": " + (b" " * SSE_PROXY_FLUSH_PADDING_BYTES) + b"\n\n"
        sequence = 0
        async for frame in outcome.frames:
            if isinstance(frame, JournalFrame):
                yield encode_journal_frame(frame)
            elif frame.event is None:
                yield b": ping\n\n"
            elif settings.chat_durable_turn_dispatch_enabled:
                sequence += 1
                yield encode_journal_frame(
                    JournalFrame(sequence, frame.event, frame.payload)
                )
            else:
                yield sse_event(frame.event, **frame.payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/latency/{request_id}", status_code=204)
def report_browser_latency(
    request_id: uuid.UUID,
    body: ChatBrowserLatencyRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    owner = owner_from_user(user)
    try:
        found = ChatLatencyService(db).update_browser(
            owner.hf_user_id, str(request_id), body
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not found:
        db.rollback()
        raise HTTPException(status_code=404, detail="Chat request not found")
    db.commit()
    return Response(status_code=204)


@router.get(
    "/admin/feedback",
    dependencies=[Depends(require_admin)],
    response_model=ChatFeedbackListResponse,
)
def list_chat_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    value: bool | None = Query(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    return ChatFeedbackService(db, settings).list_recent(limit=limit, value=value)


@router.post("/messages/{message_id}/feedback", status_code=204)
def submit_chat_feedback(
    message_id: uuid.UUID,
    body: ChatFeedbackRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    owner = owner_from_user(user)
    try:
        found = ChatFeedbackService(db, settings).submit(
            owner_id=owner.hf_user_id,
            assistant_message_id=message_id,
            value=body.value,
            comment=body.comment,
        )
    except ChatFeedbackUnavailable:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Chat feedback is temporarily unavailable",
        ) from None
    if not found:
        db.rollback()
        raise HTTPException(status_code=404, detail="Assistant response not found")
    # The request session only closes on exit; the stored rating must commit.
    db.commit()
    return Response(status_code=204)
