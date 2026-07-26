"""Authenticated durable chat sessions and SSE research turns."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import db_manager, get_database_session
from backend.models.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionSummary,
    CreateSessionRequest,
    UpdateSessionRequest,
    sse_event,
)
from backend.models.database import ChatMessageRecord, ChatSession
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_session_service import (
    ChatServiceError,
    ChatSessionService,
    owner_from_user,
)
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.utils.auth import require_user

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _prewarm_sandbox(settings: Settings, session_id: uuid.UUID) -> None:
    try:
        asyncio.run(SandboxSessionManager(settings).ensure_ready(session_id))
    except Exception as exc:
        # First-turn ensure_ready remains authoritative and retryable. Prewarm
        # failure is an optimization miss, never a session-creation failure.
        logger.warning(
            "chat sandbox prewarm failed session_id=%s error=%s",
            session_id,
            type(exc).__name__,
        )


class _AdmissionControl:
    """Compatibility seam; durable admission is enforced transactionally."""

    async def try_acquire(self, _maximum: int) -> bool:
        return True

    async def release(self) -> None:
        return


class _PrincipalRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, principal: str, per_minute: int, per_day: int) -> int | None:
        now = time.monotonic()
        async with self._lock:
            events = self._events[principal]
            while events and events[0] <= now - 86_400:
                events.popleft()
            recent = [event for event in events if event > now - 60]
            if len(events) >= per_day:
                return max(1, round(86_400 - (now - events[0])))
            if len(recent) >= per_minute:
                return max(1, round(60 - (now - recent[0])))
            events.append(now)
            return None


_admission = _AdmissionControl()
_rate_limiter = _PrincipalRateLimiter()


def _raise(exc: ChatServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
        headers={"Retry-After": "5"} if exc.status_code == 429 else None,
    )


def _busy(session: ChatSession) -> bool:
    from datetime import UTC, datetime

    return bool(
        session.active_turn_id
        and session.active_turn_expires_at
        and session.active_turn_expires_at > datetime.now(UTC)
    )


def _summary(session: ChatSession) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=session.id,
        title=session.title,
        selected_model=session.selected_model,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        is_busy=_busy(session),
    )


def _message(row: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=row.id,
        turn_id=row.turn_id,
        sequence=row.sequence,
        role=row.role,
        content=row.content,
        revision=row.revision,
        status=row.status,
        citations=row.citations or [],
        followups=row.followups or [],
        display_blocks=row.display_blocks or [],
        model=row.model,
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
            {"id": choice["id"], "label": choice["label"]}
            for choice in settings.chat_model_choices
        ],
        "default_model": settings.chat_model_choices[0]["id"],
    }


@router.post("/sessions", response_model=ChatSessionSummary, status_code=201)
def create_session(
    body: CreateSessionRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        session = ChatSessionService(db, settings).create_session(
            owner_from_user(user), body.selected_model
        )
        db.commit()
        db.refresh(session)
        if session.execution_backend == "modal_cli":
            background_tasks.add_task(_prewarm_sandbox, settings, session.id)
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


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        session, messages = ChatSessionService(db, settings).get_session(
            owner_from_user(user), session_id
        )
        return ChatSessionDetail(
            **_summary(session).model_dump(),
            messages=[_message(row) for row in messages],
            transcript_status=session.transcript_status,
        )
    except ChatServiceError as exc:
        _raise(exc)


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
        assert session is not None
        db.commit()
        db.refresh(session)
        return _summary(session)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    try:
        sandbox_id, snapshot_id = ChatSessionService(db, settings).delete_session(
            owner_from_user(user), session_id
        )
        db.commit()
        if sandbox_id or snapshot_id:
            await SandboxSessionManager(settings).cleanup_deleted(
                sandbox_id, snapshot_id
            )
        return Response(status_code=204)
    except ChatServiceError as exc:
        db.rollback()
        _raise(exc)


@router.post("/stream", summary="Stream a durable research-assistant response")
async def stream_chat(
    body: ChatRequest, request: Request, user: dict = Depends(require_user)
):
    settings = get_settings()
    if not settings.chat_enabled or not settings.hf_token:
        raise HTTPException(status_code=503, detail="Chat is not configured")
    if not await _admission.try_acquire(settings.chat_max_concurrency):
        raise HTTPException(
            status_code=429,
            detail="Chat capacity is currently occupied",
            headers={"Retry-After": "5"},
        )
    owner = owner_from_user(user)
    retry_after = await _rate_limiter.check(
        owner.hf_user_id,
        settings.chat_requests_per_minute,
        settings.chat_requests_per_day,
    )
    if retry_after is not None:
        await _admission.release()
        raise HTTPException(
            status_code=429,
            detail="Chat rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        with db_manager.session_local() as db:
            try:
                service = ChatSessionService(db, settings)
                admission = service.begin_turn(
                    owner,
                    session_id=body.session_id,
                    client_message_id=body.client_message_id,
                    text=body.message,
                    initial_model=body.initial_model,
                    replace_message_id=body.replace_message_id,
                    prior_revision=body.prior_revision,
                )
                title_token = (
                    service.begin_title(
                        owner,
                        admission.session_id,
                        revision=admission.prompt_revision,
                    )
                    if admission.title_should_generate
                    and not admission.replay_assistant
                    else None
                )
                db.commit()
            except ChatServiceError as exc:
                if exc.commit_changes:
                    db.commit()
                else:
                    db.rollback()
                raise
    except ChatServiceError as exc:
        await _admission.release()
        _raise(exc)

    orchestrator = ChatStreamOrchestrator(
        settings=settings,
        owner=owner,
        admission=admission,
        prompt=body.message,
        request_id=str(uuid.uuid4()),
        title_token=title_token,
        is_disconnected=request.is_disconnected,
        release_admission=_admission.release,
    )

    async def event_stream():
        async for frame in orchestrator.events():
            if frame.event is None:
                yield b": ping\n\n"
            else:
                yield sse_event(frame.event, **frame.payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
