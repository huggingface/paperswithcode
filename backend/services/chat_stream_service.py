"""Durable chat-turn orchestration and projection.

The HTTP router admits a turn and serializes frames. This module owns the
provider/title task lifecycle, durable state transitions, and projection of
provider events into persisted display blocks.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import fork_session_via_store
from claude_agent_sdk._internal.session_store import project_key_for_directory

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_citation_service import cited_route_ids, resolve_citations
from backend.services.chat_sandbox_service import SandboxError
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_title_service import (
    fallback_title,
    normalize_title,
    stream_title,
)
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.services.chat_turn_runner import ChatTurnRunner, create_chat_turn_runner
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class ChatStreamFrame:
    """One transport-neutral frame for the router to serialize."""

    event: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def heartbeat(cls) -> ChatStreamFrame:
        return cls(event=None)


@dataclass
class ChatTurnProjection:
    """Typed mutable projection of provider events into display state."""

    answer_parts: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    reasoning: dict[str, Any] | None = None
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)

    def completed_blocks(self) -> list[dict[str, Any]]:
        completed = [
            block
            for block in self.blocks
            if block.get("kind") != "tool" or block.get("status") != "running"
        ]
        answer = "".join(self.answer_parts)
        if answer.strip():
            completed.append({"kind": "answer", "text": answer, "done": True})
        return completed

    def apply(self, kind: str, event: dict[str, Any]) -> None:
        if kind == "reasoning_start":
            self.reasoning = {"kind": "reasoning", "text": ""}
        elif kind == "reasoning_delta" and self.reasoning is not None:
            self.reasoning["text"] += event["text"]
        elif kind == "reasoning_end" and self.reasoning is not None:
            self.blocks.append(self.reasoning)
            self.reasoning = None
        elif kind == "tool_call":
            self._start_tool(event)
        elif kind == "tool_result":
            self._finish_tool(event)
        elif kind == "answer_delta":
            self.answer_parts.append(event["text"])

    def _start_tool(self, event: dict[str, Any]) -> None:
        legacy_tool = event["name"] == "search_papers"
        tool: dict[str, Any] = {
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
                    "metadata": {"exit_code": None, "output_truncated": False},
                }
            )
        self.blocks.append(tool)
        self.tools[event["id"]] = tool

    def _finish_tool(self, event: dict[str, Any]) -> None:
        tool = self.tools.get(event["id"])
        if tool and event.get("status") is not None:
            tool.update(
                {
                    "status": event["status"],
                    "took_ms": event["took_ms"],
                    "content": event["content"],
                    "metadata": event.get("metadata")
                    or {"exit_code": None, "output_truncated": False},
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
            self.citations.append(
                {
                    "position": len(self.citations),
                    "route_id": result["route_id"],
                    "title": result["title"],
                    "source_url": metadata.get("source_url")
                    or (
                        f"https://arxiv.org/abs/{metadata['arxiv_id']}"
                        if metadata.get("arxiv_id")
                        else None
                    ),
                    "authors": [
                        author.get("name", "") for author in metadata.get("authors", [])
                    ],
                    "published": metadata.get("published"),
                    "conference": metadata.get("conference"),
                }
            )

    def finalize(self, db) -> tuple[str, list[dict[str, Any]]]:
        answer = "".join(self.answer_parts)
        self.blocks.append({"kind": "answer", "text": answer, "done": True})
        text = "\n".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") in {"reasoning", "answer"}
        )
        resolved = resolve_citations(db, text)
        if resolved:
            self.citations = resolved
        else:
            cited = set(re.findall(r"\]\(paper:([^) \t\n]{1,200})\)", text))
            self.citations = [
                item for item in self.citations if item["route_id"] in cited
            ]
        citations_by_id = {item["route_id"]: item for item in self.citations}
        for block in self.blocks:
            if block.get("kind") not in {"reasoning", "answer"}:
                continue
            block["citations"] = [
                citations_by_id[route_id]
                for route_id in cited_route_ids(block.get("text", ""))
                if route_id in citations_by_id
            ]
        return answer, self.citations


def _persist_failure(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    code: str,
    interrupted: bool,
    display_blocks: list[dict[str, Any]] | None = None,
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


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("chat background task failed error=%s", type(exc).__name__)


class ChatStreamOrchestrator:
    """Run one admitted turn and yield transport-neutral stream frames."""

    def __init__(
        self,
        *,
        settings: Settings,
        owner: ChatOwner,
        admission: TurnAdmission,
        prompt: str,
        request_id: str,
        title_token: uuid.UUID | None,
        is_disconnected: Callable[[], Awaitable[bool]],
        release_admission: Callable[[], Awaitable[None]],
    ) -> None:
        self.settings = settings
        self.owner = owner
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.title_token = title_token
        self.is_disconnected = is_disconnected
        self.release_admission = release_admission
        self.principal_hash = hashlib.sha256(owner.hf_user_id.encode()).hexdigest()[:12]
        self.started = time.perf_counter()
        self.terminal = "disconnect"
        self.projection = ChatTurnProjection()
        self.store = PostgresSDKSessionStore()
        self.research_task: asyncio.Task | None = None
        self.title_task: asyncio.Task | None = None
        self.runner: ChatTurnRunner | None = None
        self.mirror_recovery: tuple[str, uuid.UUID] | None = None

    async def events(self) -> AsyncIterator[ChatStreamFrame]:
        try:
            yield ChatStreamFrame(
                "stream_start",
                {
                    "request_id": self.request_id,
                    "session_id": self.admission.session_id,
                },
            )
            if self.admission.replay_assistant:
                yield ChatStreamFrame(
                    "answer_delta", {"text": self.admission.replay_assistant.content}
                )
                yield ChatStreamFrame(
                    "done",
                    {
                        "followups": self.admission.replay_assistant.followups or [],
                        "finish_reason": "success",
                    },
                )
                self.terminal = "success"
                return

            replacement_ready, resume_id = await self._replacement_or_error()
            if not replacement_ready:
                yield ChatStreamFrame(
                    "error",
                    {
                        "message": (
                            "The interrupted prompt could not be prepared for retry."
                        ),
                        "code": "replacement_prepare_failed",
                    },
                )
                return

            queue: asyncio.Queue = asyncio.Queue()
            self.runner = create_chat_turn_runner(
                settings=self.settings,
                owner=self.owner,
                admission=self.admission,
                prompt=self.prompt,
                request_id=self.request_id,
                resume_id=resume_id,
                store=self.store,
            )
            self.research_task = asyncio.create_task(self._produce_research(queue))
            self.title_task = (
                asyncio.create_task(
                    _title_events(
                        self.owner,
                        self.settings,
                        self.admission,
                        self.title_token,
                        self.prompt,
                        queue,
                    )
                )
                if self.title_token
                else None
            )
            async for frame in self._consume(queue):
                yield frame
            await self._reconcile_mirror()
            if self.title_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await self.title_task
        except asyncio.CancelledError:
            await self._cancel_runner()
            await asyncio.shield(
                asyncio.to_thread(
                    _persist_failure,
                    self.owner,
                    self.settings,
                    self.admission,
                    "interrupted",
                    True,
                    self.projection.completed_blocks(),
                )
            )
            raise
        except Exception as exc:
            logger.warning(
                "chat stream persistence failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            _persist_failure(
                self.owner,
                self.settings,
                self.admission,
                "persistence_error",
                False,
            )
            self.terminal = "error"
            yield ChatStreamFrame(
                "error",
                {
                    "message": (
                        "The response could not be saved. You can retry this prompt."
                    ),
                    "code": "persistence_error",
                },
            )
        finally:
            await self._close()

    async def _replacement_or_error(self) -> tuple[bool, uuid.UUID | None]:
        try:
            return (
                True,
                await _prepare_replacement(
                    self.owner, self.settings, self.admission, self.store
                ),
            )
        except Exception as exc:
            logger.warning(
                "chat replacement preparation failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            _persist_failure(
                self.owner,
                self.settings,
                self.admission,
                "replacement_prepare_failed",
                False,
            )
            self.terminal = "error"
            return False, None

    async def _produce_research(self, queue: asyncio.Queue) -> None:
        try:
            assert self.runner is not None
            async for event in self.runner.events():
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except SandboxError as exc:
            await queue.put({"type": "error", "message": str(exc), "code": exc.code})
        except Exception as exc:
            logger.warning(
                "chat research producer failed session_id=%s error=%s",
                self.admission.session_id,
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

    async def _consume(self, queue: asyncio.Queue) -> AsyncIterator[ChatStreamFrame]:
        research_finished = False
        title_finished = self.title_task is None
        last_write = time.monotonic()
        while not (research_finished and title_finished):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
            except TimeoutError:
                if await self.is_disconnected():
                    raise asyncio.CancelledError
                if time.monotonic() - last_write >= HEARTBEAT_SECONDS:
                    yield ChatStreamFrame.heartbeat()
                    last_write = time.monotonic()
                continue
            if await self.is_disconnected():
                raise asyncio.CancelledError
            event = dict(event)
            kind = event.pop("type")
            if kind == "_research_finished":
                research_finished = True
                continue
            if kind == "_title_finished":
                title_finished = True
                continue
            if kind == "_sdk_session":
                self._bind_sdk_session(event)
                continue
            if kind == "_mirror_error":
                yield self._fail_mirror(event)
                if self.research_task:
                    self.research_task.cancel()
                continue

            self.projection.apply(kind, event)
            if kind == "error":
                _persist_failure(
                    self.owner,
                    self.settings,
                    self.admission,
                    event.get("code") or "provider_error",
                    False,
                    self.projection.completed_blocks(),
                )
                self.terminal = "error"
            elif kind == "done":
                self._complete_turn(event)
                event["citations"] = self.projection.citations
                self.terminal = event.get("finish_reason", "success")
            yield ChatStreamFrame(kind, event)
            last_write = time.monotonic()
        if self.research_task:
            with contextlib.suppress(asyncio.CancelledError):
                await self.research_task

    def _bind_sdk_session(self, event: dict[str, Any]) -> None:
        assert self.runner is not None
        sdk_id = uuid.UUID(event["session_id"])
        with db_manager.session_local() as db:
            ChatSessionService(db, self.settings).bind_sdk_session(
                self.owner,
                self.admission.session_id,
                self.admission.turn_id,
                sdk_id,
                project_key_for_directory(self.runner.sdk_directory),
            )
            db.commit()

    def _fail_mirror(self, event: dict[str, Any]) -> ChatStreamFrame:
        mirror_key = event.get("key") or {}
        mirror_session_id = mirror_key.get("session_id")
        mirror_project_key = mirror_key.get("project_key")
        if mirror_session_id and mirror_project_key:
            sdk_id = uuid.UUID(mirror_session_id)
            with db_manager.session_local() as db:
                ChatSessionService(db, self.settings).bind_sdk_session(
                    self.owner,
                    self.admission.session_id,
                    self.admission.turn_id,
                    sdk_id,
                    mirror_project_key,
                )
                db.commit()
            self.mirror_recovery = (mirror_project_key, sdk_id)
        with db_manager.session_local() as db:
            service = ChatSessionService(db, self.settings)
            service.mark_transcript_degraded(
                self.owner, self.admission.session_id, self.admission.turn_id
            )
            service.fail_turn(
                self.owner, self.admission, "transcript_mirror_error", False
            )
            db.commit()
        self.terminal = "error"
        return ChatStreamFrame(
            "error",
            {
                "message": "The conversation could not be saved.",
                "code": "transcript_mirror_error",
            },
        )

    def _complete_turn(self, event: dict[str, Any]) -> None:
        with db_manager.session_local() as db:
            answer, citations = self.projection.finalize(db)
            ChatSessionService(db, self.settings).complete_turn(
                self.owner,
                self.admission,
                answer,
                citations,
                event.get("followups", []),
                self.projection.blocks,
                event.get("finish_reason", "success"),
            )
            db.commit()

    async def _reconcile_mirror(self) -> None:
        if not self.mirror_recovery:
            return
        project_key, sdk_id = self.mirror_recovery
        try:
            recovered = await reconcile_spooled_session(
                self.settings,
                self.store,
                project_key=project_key,
                sdk_session_id=sdk_id,
            )
        except Exception as exc:
            recovered = False
            logger.warning(
                "chat transcript reconciliation failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
        if recovered:
            with db_manager.session_local() as db:
                ChatSessionService(db, self.settings).mark_transcript_ready(
                    self.owner, self.admission.session_id, sdk_id
                )
                db.commit()

    async def _cancel_runner(self) -> None:
        if self.runner and self.research_task and not self.research_task.done():
            with contextlib.suppress(Exception):
                await asyncio.shield(self.runner.cancel())

    async def _close(self) -> None:
        await self._cancel_runner()
        if self.runner:
            with contextlib.suppress(Exception):
                await asyncio.shield(self.runner.close())
        if self.research_task and not self.research_task.done():
            self.research_task.cancel()
        if self.research_task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.research_task
        if self.title_task and not self.title_task.done():
            self.title_task.add_done_callback(_log_background_task_result)
        logger.info(
            "chat request complete request_id=%s principal=%s duration_ms=%.1f finish=%s",
            self.request_id,
            self.principal_hash,
            (time.perf_counter() - self.started) * 1000,
            self.terminal,
        )
        await self.release_admission()
