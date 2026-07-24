"""Authenticated durable chat sessions and SSE research turns."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict, deque

from claude_agent_sdk import fork_session_via_store
from claude_agent_sdk._internal.session_store import project_key_for_directory
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
from backend.services.chat_citation_service import cited_route_ids, resolve_citations
from backend.services.chat_sandbox_service import SandboxError, SandboxSessionManager
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
    owner_from_user,
)
from backend.services.chat_title_service import (
    fallback_title,
    normalize_title,
    stream_title,
)
from backend.services.chat_turn_runner import (
    ChatTurnRunner,
    create_chat_turn_runner,
)
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore
from backend.utils.auth import require_user

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15.0


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("chat background task failed error=%s", type(exc).__name__)


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


def _persist_failure(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    code: str,
    interrupted: bool,
    display_blocks: list[dict] | None = None,
) -> None:
    with db_manager.session_local() as db:
        try:
            ChatSessionService(db, settings).fail_turn(
                owner, admission, code, interrupted, display_blocks
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("chat cleanup failed session_id=%s", admission.session_id)


async def _prepare_replacement(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    store: PostgresSDKSessionStore,
) -> uuid.UUID | None:
    old_id = admission.sdk_session_id
    if not admission.is_replacement or old_id is None:
        return old_id
    session_directory = (
        "/workspace"
        if getattr(admission, "execution_backend", "local_mcp") == "modal_cli"
        else settings.chat_agent_cwd
    )
    project_key = project_key_for_directory(session_directory)
    replacement_id: uuid.UUID | None = None
    if admission.resume_boundary_id:
        result = await fork_session_via_store(
            store,
            str(old_id),
            directory=session_directory,
            up_to_message_id=str(admission.resume_boundary_id),
        )
        replacement_id = uuid.UUID(result.session_id)
    with db_manager.session_local() as db:
        rebound = ChatSessionService(db, settings).rebind_sdk_session(
            owner,
            admission.session_id,
            admission.turn_id,
            old_id,
            replacement_id,
            project_key,
        )
        if not rebound:
            db.rollback()
            if replacement_id:
                await store.delete(
                    {"project_key": project_key, "session_id": str(replacement_id)}
                )
            raise ChatServiceError("stale_turn", 409, "The replacement turn changed")
        db.commit()
    await store.delete({"project_key": project_key, "session_id": str(old_id)})
    return replacement_id


async def _title_events(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    token: uuid.UUID,
    prompt: str,
    queue: asyncio.Queue,
) -> None:
    await queue.put({"type": "session_title_start"})
    pieces: list[str] = []
    fallback = False
    try:
        async for delta in stream_title(prompt, settings):
            pieces.append(delta)
            await queue.put({"type": "session_title_delta", "text": delta})
        title = normalize_title("".join(pieces))
        if not title:
            raise ValueError("empty title")
    except Exception:
        fallback = True
        title = fallback_title(prompt)
    final = None
    try:
        with db_manager.session_local() as db:
            final = ChatSessionService(db, settings).complete_title(
                owner, admission.session_id, token, title, fallback=fallback
            )
            db.commit()
    except Exception as exc:
        logger.warning(
            "chat title persistence failed session_id=%s error=%s",
            admission.session_id,
            type(exc).__name__,
        )
    if final:
        await queue.put({"type": "session_title_done", "title": final})
    await queue.put({"type": "_title_finished"})


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

    request_id = str(uuid.uuid4())
    principal_hash = hashlib.sha256(owner.hf_user_id.encode()).hexdigest()[:12]
    started = time.perf_counter()

    async def event_stream():
        terminal = "disconnect"
        answer_parts: list[str] = []
        blocks: list[dict] = []
        reasoning: dict | None = None
        tools: dict[str, dict] = {}
        citations: list[dict] = []
        store = PostgresSDKSessionStore()
        research_task: asyncio.Task | None = None
        title_task: asyncio.Task | None = None
        runner: ChatTurnRunner | None = None
        mirror_recovery: tuple[str, uuid.UUID] | None = None

        def completed_projection() -> list[dict]:
            partial = [
                block
                for block in blocks
                if block.get("kind") != "tool" or block.get("status") not in {"running"}
            ]
            partial_answer = "".join(answer_parts)
            if partial_answer.strip():
                partial.append({"kind": "answer", "text": partial_answer, "done": True})
            return partial

        try:
            yield sse_event(
                "stream_start", request_id=request_id, session_id=admission.session_id
            )
            if admission.replay_assistant:
                yield sse_event("answer_delta", text=admission.replay_assistant.content)
                yield sse_event(
                    "done",
                    followups=admission.replay_assistant.followups or [],
                    finish_reason="success",
                )
                terminal = "success"
                return

            try:
                resume_id = await _prepare_replacement(
                    owner, settings, admission, store
                )
            except Exception as exc:
                logger.warning(
                    "chat replacement preparation failed session_id=%s error=%s",
                    admission.session_id,
                    type(exc).__name__,
                )
                _persist_failure(
                    owner, settings, admission, "replacement_prepare_failed", False
                )
                terminal = "error"
                yield sse_event(
                    "error",
                    message="The interrupted prompt could not be prepared for retry.",
                    code="replacement_prepare_failed",
                )
                return

            queue: asyncio.Queue = asyncio.Queue()
            runner = create_chat_turn_runner(
                settings=settings,
                owner=owner,
                admission=admission,
                prompt=body.message,
                request_id=request_id,
                resume_id=resume_id,
                store=store,
            )

            async def produce_research() -> None:
                try:
                    assert runner is not None
                    async for event in runner.events():
                        await queue.put(event)
                except asyncio.CancelledError:
                    raise
                except SandboxError as exc:
                    await queue.put(
                        {
                            "type": "error",
                            "message": str(exc),
                            "code": exc.code,
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "chat research producer failed session_id=%s error=%s",
                        admission.session_id,
                        type(exc).__name__,
                    )
                    await queue.put(
                        {
                            "type": "error",
                            "message": "The model provider is unavailable.",
                            "code": "provider_error",
                        }
                    )
                finally:
                    await queue.put({"type": "_research_finished"})

            research_task = asyncio.create_task(produce_research())
            title_task = (
                asyncio.create_task(
                    _title_events(
                        owner, settings, admission, title_token, body.message, queue
                    )
                )
                if title_token
                else None
            )
            research_finished = False
            title_finished = title_task is None
            last_write = time.monotonic()
            while not (research_finished and title_finished):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                except TimeoutError:
                    if await request.is_disconnected():
                        raise asyncio.CancelledError
                    if time.monotonic() - last_write >= HEARTBEAT_SECONDS:
                        yield b": ping\n\n"
                        last_write = time.monotonic()
                    continue
                if await request.is_disconnected():
                    raise asyncio.CancelledError
                kind = event.pop("type")
                if kind == "_research_finished":
                    research_finished = True
                    continue
                if kind == "_title_finished":
                    title_finished = True
                    continue
                if kind == "_sdk_session":
                    sdk_id = uuid.UUID(event["session_id"])
                    with db_manager.session_local() as db:
                        ChatSessionService(db, settings).bind_sdk_session(
                            owner,
                            admission.session_id,
                            admission.turn_id,
                            sdk_id,
                            project_key_for_directory(runner.sdk_directory),
                        )
                        db.commit()
                    continue
                if kind == "_mirror_error":
                    mirror_key = event.get("key") or {}
                    mirror_session_id = mirror_key.get("session_id")
                    mirror_project_key = mirror_key.get("project_key")
                    if mirror_session_id and mirror_project_key:
                        sdk_id = uuid.UUID(mirror_session_id)
                        with db_manager.session_local() as db:
                            ChatSessionService(db, settings).bind_sdk_session(
                                owner,
                                admission.session_id,
                                admission.turn_id,
                                sdk_id,
                                mirror_project_key,
                            )
                            db.commit()
                        mirror_recovery = (mirror_project_key, sdk_id)
                    with db_manager.session_local() as db:
                        service = ChatSessionService(db, settings)
                        service.mark_transcript_degraded(
                            owner, admission.session_id, admission.turn_id
                        )
                        service.fail_turn(
                            owner, admission, "transcript_mirror_error", False
                        )
                        db.commit()
                    terminal = "error"
                    yield sse_event(
                        "error",
                        message="The conversation could not be saved.",
                        code="transcript_mirror_error",
                    )
                    research_task.cancel()
                    continue
                if kind == "reasoning_start":
                    reasoning = {"kind": "reasoning", "text": ""}
                elif kind == "reasoning_delta" and reasoning is not None:
                    reasoning["text"] += event["text"]
                elif kind == "reasoning_end" and reasoning is not None:
                    blocks.append(reasoning)
                    reasoning = None
                elif kind == "tool_call":
                    legacy_tool = event["name"] == "search_papers"
                    tool = {
                        "kind": "tool",
                        "schema_version": 1 if legacy_tool else 2,
                        "id": event["id"],
                        "name": event["name"],
                        "args": event["args"],
                        "status": "done" if legacy_tool else "running",
                        "took_ms": 0,
                    }
                    if legacy_tool:
                        tool.update({"hits": 0, "results": []})
                    else:
                        tool.update(
                            {
                                "content": [],
                                "metadata": {
                                    "exit_code": None,
                                    "output_truncated": False,
                                },
                            }
                        )
                    blocks.append(tool)
                    tools[event["id"]] = tool
                elif kind == "tool_result":
                    tool = tools.get(event["id"])
                    if tool and event.get("status") is not None:
                        tool.update(
                            {
                                "status": event["status"],
                                "took_ms": event["took_ms"],
                                "content": event["content"],
                                "metadata": event.get("metadata")
                                or {
                                    "exit_code": None,
                                    "output_truncated": False,
                                },
                            }
                        )
                    elif tool:
                        tool.update(
                            {
                                "hits": event["hits"],
                                "took_ms": event["took_ms"],
                                "results": event["results"],
                            }
                        )
                    for result in event.get("results") or []:
                        metadata = result.get("metadata", {})
                        citations.append(
                            {
                                "position": len(citations),
                                "route_id": result["route_id"],
                                "title": result["title"],
                                "source_url": metadata.get("source_url")
                                or (
                                    f"https://arxiv.org/abs/{metadata['arxiv_id']}"
                                    if metadata.get("arxiv_id")
                                    else None
                                ),
                                "authors": [
                                    author.get("name", "")
                                    for author in metadata.get("authors", [])
                                ],
                                "published": metadata.get("published"),
                                "conference": metadata.get("conference"),
                            }
                        )
                elif kind == "answer_delta":
                    answer_parts.append(event["text"])
                elif kind == "error":
                    _persist_failure(
                        owner,
                        settings,
                        admission,
                        event.get("code") or "provider_error",
                        False,
                        completed_projection(),
                    )
                    terminal = "error"
                elif kind == "done":
                    answer = "".join(answer_parts)
                    blocks.append({"kind": "answer", "text": answer, "done": True})
                    with db_manager.session_local() as db:
                        resolved_citations = resolve_citations(
                            db,
                            "\n".join(
                                block.get("text", "")
                                for block in blocks
                                if block.get("kind") in {"reasoning", "answer"}
                            ),
                        )
                        if resolved_citations:
                            citations = resolved_citations
                        else:
                            cited = {
                                match
                                for match in re.findall(
                                    r"\]\(paper:([^) \t\n]{1,200})\)",
                                    "\n".join(
                                        block.get("text", "")
                                        for block in blocks
                                        if block.get("kind") in {"reasoning", "answer"}
                                    ),
                                )
                            }
                            citations = [
                                item for item in citations if item["route_id"] in cited
                            ]
                        citations_by_id = {item["route_id"]: item for item in citations}
                        for block in blocks:
                            if block.get("kind") not in {"reasoning", "answer"}:
                                continue
                            block["citations"] = [
                                citations_by_id[route_id]
                                for route_id in cited_route_ids(block.get("text", ""))
                                if route_id in citations_by_id
                            ]
                        ChatSessionService(db, settings).complete_turn(
                            owner,
                            admission,
                            answer,
                            citations,
                            event.get("followups", []),
                            blocks,
                            event.get("finish_reason", "success"),
                        )
                        db.commit()
                    event["citations"] = citations
                    terminal = event.get("finish_reason", "success")
                yield sse_event(kind, **event)
                last_write = time.monotonic()
                if kind in ("done", "error"):
                    continue
            with contextlib.suppress(asyncio.CancelledError):
                await research_task
            if mirror_recovery:
                project_key, sdk_id = mirror_recovery
                try:
                    recovered = await reconcile_spooled_session(
                        settings,
                        store,
                        project_key=project_key,
                        sdk_session_id=sdk_id,
                    )
                except Exception as exc:
                    recovered = False
                    logger.warning(
                        "chat transcript reconciliation failed session_id=%s error=%s",
                        admission.session_id,
                        type(exc).__name__,
                    )
                if recovered:
                    with db_manager.session_local() as db:
                        ChatSessionService(db, settings).mark_transcript_ready(
                            owner, admission.session_id, sdk_id
                        )
                        db.commit()
            if title_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await title_task
        except asyncio.CancelledError:
            if runner and research_task and not research_task.done():
                with contextlib.suppress(Exception):
                    await asyncio.shield(runner.cancel())
            await asyncio.shield(
                asyncio.to_thread(
                    _persist_failure,
                    owner,
                    settings,
                    admission,
                    "interrupted",
                    True,
                    completed_projection(),
                )
            )
            raise
        except Exception as exc:
            logger.warning(
                "chat stream persistence failed session_id=%s error=%s",
                admission.session_id,
                type(exc).__name__,
            )
            _persist_failure(owner, settings, admission, "persistence_error", False)
            terminal = "error"
            yield sse_event(
                "error",
                message="The response could not be saved. You can retry this prompt.",
                code="persistence_error",
            )
        finally:
            if runner and research_task and not research_task.done():
                with contextlib.suppress(Exception):
                    await asyncio.shield(runner.cancel())
            if runner:
                with contextlib.suppress(Exception):
                    await asyncio.shield(runner.close())
            if research_task and not research_task.done():
                research_task.cancel()
            if research_task:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await research_task
            if title_task and not title_task.done():
                # Title persistence is independent of the client connection and
                # research result. Its own short timeout bounds this detached task.
                title_task.add_done_callback(_log_background_task_result)
            logger.info(
                "chat request complete request_id=%s principal=%s duration_ms=%.1f finish=%s",
                request_id,
                principal_hash,
                (time.perf_counter() - started) * 1000,
                terminal,
            )
            await _admission.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
