"""Durable chat-turn orchestration and projection.

The HTTP router admits a turn and serializes frames. This module owns the
provider/title task lifecycle, durable state transitions, and projection of
provider events into persisted display blocks.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import posixpath
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import fork_session_via_store
from claude_agent_sdk._internal.session_store import project_key_for_directory
from sqlalchemy import select

from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import ChatArtifact, ChatArtifactVersion, ChatSession
from backend.services.latex_paper_service import LatexPaperService
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_citation_service import (
    PaperCitationCandidate,
    candidates_from_citation_history,
    citation_format_counts,
    cited_route_ids,
    extract_s2_candidates,
    normalize_paper_links,
    normalize_s2_catalog_links,
    repair_exact_paper_titles,
    resolve_citation_targets,
)
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_pi_transcript_service import ChatPiTranscriptService
from backend.services.chat_sandbox_service import SandboxError
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_title_budget_service import (
    ChatTitleBudgetService,
    ChatTitleBudgetUnavailable,
)
from backend.services.chat_title_service import (
    TitleProviderUsage,
    fallback_title,
    normalize_title,
    stream_title,
)
from backend.services.chat_tracing_service import (
    ChatTurnTrace,
    NullChatTurnTrace,
    trace_chat_turn,
)
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.services.chat_turn_runner import ChatTurnRunner, create_chat_turn_runner
from backend.services.openrouter_user_budget_service import OpenRouterUserBudgetService
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore
from backend.utils.urls import parse_arxiv_url

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15.0


def _external_paper_candidate(
    url: str, candidates: list[PaperCitationCandidate]
) -> PaperCitationCandidate | None:
    for candidate in candidates:
        if candidate.semantic_scholar_url == url:
            return candidate
    parsed = parse_arxiv_url(url)
    if parsed is None:
        return None
    arxiv_id, _version = parsed
    return next(
        (candidate for candidate in candidates if candidate.arxiv_id == arxiv_id),
        None,
    )


def _external_paper_snapshot(
    candidate: PaperCitationCandidate, url: str, position: int
) -> dict[str, Any]:
    return {
        "kind": "external_source",
        "position": position,
        "route_id": None,
        "url": url,
        "source_type": "paper",
        "provider": "semantic_scholar",
        "title": candidate.title,
        "excerpt": candidate.excerpt,
        "source_url": candidate.semantic_scholar_url,
        "thumbnail_url": None,
        "favicon_url": None,
        "arxiv_id": candidate.arxiv_id,
        "semantic_scholar_id": candidate.semantic_scholar_id,
        "authors": list(candidate.authors),
        "published": candidate.published,
        "conference": None,
        "citation_count": candidate.citation_count,
    }


def _catalog_paper_snapshot(
    item: dict[str, Any], candidate: PaperCitationCandidate | None
) -> dict[str, Any]:
    return {
        "kind": "catalog_paper",
        "position": item["position"],
        "route_id": item["route_id"],
        "url": None,
        "source_type": None,
        "provider": "paperswithcode",
        "title": item["title"],
        "excerpt": None,
        "source_url": item.get("source_url"),
        "thumbnail_url": item.get("thumbnail_url"),
        "favicon_url": None,
        "arxiv_id": item.get("arxiv_id"),
        "semantic_scholar_id": candidate.semantic_scholar_id if candidate else None,
        "authors": item.get("authors") or [],
        "published": item.get("published"),
        "conference": item.get("conference"),
        "citation_count": item.get("citation_count"),
    }


def _attach_block_citations(
    blocks: list[dict[str, Any]], citations: list[dict[str, Any]]
) -> None:
    citations_by_id = {
        item["route_id"]: item
        for item in citations
        if item.get("kind") == "catalog_paper" and item.get("route_id")
    }
    citations_by_url = {
        item["url"]: item
        for item in citations
        if item.get("kind") == "external_source" and item.get("url")
    }
    for block in blocks:
        if block.get("kind") not in {"reasoning", "answer"}:
            continue
        block_citations = [
            citations_by_id[route_id]
            for route_id in cited_route_ids(block.get("text", ""))
            if route_id in citations_by_id
        ]
        for url in dict.fromkeys(
            re.findall(r"\]\((https://[^) \t\n]{1,2000})\)", block.get("text", ""))
        ):
            if url in citations_by_url:
                block_citations.append(citations_by_url[url])
        block["citations"] = block_citations


@dataclass(frozen=True)
class ChatStreamFrame:
    """One transport-neutral frame for the router to serialize."""

    event: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def heartbeat(cls) -> ChatStreamFrame:
        return cls(event=None)


class _ToolTimingFallback:
    """Measure Pi tool lifecycles until the active worker image reports them."""

    def __init__(self, *, enabled: bool, now: Callable[[], float] = time.perf_counter):
        self.enabled = enabled
        self.now = now
        self.started: dict[str, float] = {}

    def apply(self, kind: str, event: dict) -> None:
        if not self.enabled:
            return
        tool_id = str(event.get("id") or "")
        if kind == "tool_call" and tool_id:
            self.started[tool_id] = self.now()
        elif kind == "tool_result" and tool_id:
            started = self.started.pop(tool_id, None)
            if started is not None and int(event.get("took_ms") or 0) == 0:
                event["took_ms"] = max(0, round((self.now() - started) * 1000))


async def sequential_reasoning_events(events: AsyncIterator[dict[str, Any]]):
    """Repair delayed Luna reasoning boundaries before projection and SSE."""
    reasoning_open = False
    async for event in events:
        kind = event.get("type")
        if kind == "reasoning_start":
            if reasoning_open:
                yield {"type": "reasoning_end"}
            reasoning_open = True
        elif kind == "reasoning_end":
            if not reasoning_open:
                continue
            reasoning_open = False
        elif kind in {"done", "error"} and reasoning_open:
            yield {"type": "reasoning_end"}
            reasoning_open = False
        yield event
    if reasoning_open:
        yield {"type": "reasoning_end"}


@dataclass
class ChatTurnProjection:
    """Typed mutable projection of provider events into display state."""

    answer_parts: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    reasoning: dict[str, Any] | None = None
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    apps: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)
    web_sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    paper_candidates: list[PaperCitationCandidate] = field(default_factory=list)
    citation_metrics: dict[str, int | float] = field(default_factory=dict)

    def completed_blocks(self) -> list[dict[str, Any]]:
        completed: list[dict[str, Any]] = []
        for block in self.blocks:
            if block is self.reasoning:
                continue
            if block.get("kind") == "artifact" and block.get("status") not in {
                "ready",
                "error",
            }:
                continue
            item = dict(block)
            if item.get("kind") == "answer":
                item["done"] = True
            elif item.get("kind") == "tool":
                # Persist one bounded authoritative/sanitized snapshot, never
                # the transient raw JSON fragments used for live rendering.
                item.pop("argument_text", None)
                item.pop("argument_state", None)
                if item.get("status") == "running":
                    item["status"] = "error"
            completed.append(item)
        return completed

    def apply(self, kind: str, event: dict[str, Any]) -> None:
        if kind == "reasoning_start":
            self.reasoning = {"kind": "reasoning", "text": ""}
            self.blocks.append(self.reasoning)
        elif kind == "reasoning_delta" and self.reasoning is not None:
            self.reasoning["text"] += event["text"]
        elif kind == "reasoning_end" and self.reasoning is not None:
            current = self.reasoning
            self.reasoning = None
            if (
                len(self.blocks) >= 2
                and self.blocks[-1] is current
                and self.blocks[-2].get("kind") == "reasoning"
                and self.blocks[-2].get("text") == current.get("text")
            ):
                self.blocks.pop()
        elif kind == "tool_call":
            self._start_tool(event)
        elif kind == "tool_call_start":
            self._start_streamed_tool(event)
        elif kind == "tool_call_arguments_delta":
            self._stream_tool_arguments(event)
        elif kind == "tool_call_arguments_done":
            self._finish_tool_arguments(event)
        elif kind == "tool_result":
            self._finish_tool(event)
        elif kind == "app_start":
            self._start_app(event)
        elif kind == "app_result":
            self._finish_app(event)
        elif kind == "artifact_start":
            block = {
                "kind": "artifact",
                "schema_version": 1,
                "scope": "owner",
                "publication_id": event["publication_id"],
                "identifier": event["identifier"],
                "artifact_kind": "posterly",
                "title": event["title"],
                "status": "generating",
                "phase": "publishing_poster",
            }
            self.blocks.append(block)
            self.artifacts[event["publication_id"]] = block
        elif kind == "artifact_ready":
            block = self.artifacts.get(event["publication_id"])
            if block is not None:
                block.update(
                    {
                        "artifact_id": event["artifact_id"],
                        "version_id": event["version_id"],
                        "version": event["version"],
                        "status": "ready",
                        "preview_mime": "image/png",
                        "source_language": "html",
                        "gate_status": event["gate_status"],
                        "total_bytes": event["total_bytes"],
                    }
                )
                block.pop("phase", None)
        elif kind == "artifact_error":
            block = self.artifacts.get(event["publication_id"])
            if block is not None:
                block.update(
                    {
                        "status": "error",
                        "error_code": str(event.get("code") or "artifact_failed")[:64],
                        "error_message": str(
                            event.get("message") or "Poster publication failed"
                        )[:500],
                    }
                )
                block.pop("phase", None)
        elif kind == "answer_delta":
            self._append_answer(event["text"])

    def _append_answer(self, text: str) -> None:
        self.answer_parts.append(text)
        if self.blocks and self.blocks[-1].get("kind") == "answer":
            self.blocks[-1]["text"] += text
            return
        self.blocks.append({"kind": "answer", "text": text, "done": False})

    def _start_tool(self, event: dict[str, Any]) -> None:
        legacy_tool = event["name"] == "search_papers"
        tool: dict[str, Any] = {
            "kind": "tool",
            "schema_version": 1 if legacy_tool else 2,
            "id": event["id"],
            "name": event["name"],
            "args": event["args"],
            "arguments_redacted": bool(event.get("redacted")),
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

    def _start_streamed_tool(self, event: dict[str, Any]) -> None:
        tool = {
            "kind": "tool",
            "schema_version": 2,
            "id": event["id"],
            "name": event["name"],
            "args": {},
            "status": "running",
            "argument_state": "streaming",
            "argument_text": "",
            "arguments_redacted": bool(event.get("redacted")),
            "took_ms": 0,
            "content": [],
            "metadata": {"exit_code": None, "output_truncated": False},
        }
        self.blocks.append(tool)
        self.tools[event["id"]] = tool

    def _stream_tool_arguments(self, event: dict[str, Any]) -> None:
        tool = self.tools.get(event["id"])
        if tool is None:
            return
        if event.get("snapshot"):
            tool["argument_text"] = event["delta"]
        else:
            tool["argument_text"] = (tool.get("argument_text") or "") + event["delta"]
        tool["args"] = event.get("partial_args") or tool.get("args") or {}
        tool["arguments_redacted"] = bool(
            tool.get("arguments_redacted") or event.get("redacted")
        )

    def _finish_tool_arguments(self, event: dict[str, Any]) -> None:
        tool = self.tools.get(event["id"])
        if tool is None:
            return
        tool["args"] = event["args"]
        tool["argument_state"] = "done"
        tool["argument_text"] = json.dumps(
            event["args"], ensure_ascii=False, separators=(",", ":")
        )
        tool["arguments_redacted"] = bool(
            tool.get("arguments_redacted") or event.get("redacted")
        )

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
            if tool.get("name") == "search_web" and event["status"] == "success":
                self._remember_web_sources(event.get("content") or [])
            elif tool.get("name") == "Bash" and event["status"] == "success":
                command = str((tool.get("args") or {}).get("command") or "")
                self.paper_candidates.extend(
                    extract_s2_candidates(command, event.get("content") or [])
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
            self.paper_candidates.append(
                PaperCitationCandidate(
                    title=result["title"],
                    route_id=result["route_id"],
                    arxiv_id=metadata.get("arxiv_id"),
                    semantic_scholar_id=None,
                    semantic_scholar_url=None,
                    authors=tuple(
                        author.get("name", "")
                        for author in metadata.get("authors", [])
                        if author.get("name")
                    ),
                    published=metadata.get("published"),
                    citation_count=metadata.get("citation_count"),
                    excerpt=result.get("content"),
                )
            )
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

    def _start_app(self, event: dict[str, Any]) -> None:
        # App blocks own diagram input; the generic tool block is intentionally
        # omitted so a create_view call never produces a duplicate accordion.
        app = {
            "kind": "app",
            "schema_version": 1,
            "instance_id": event["instance_id"],
            "provider": event["provider"],
            "server": event["server"],
            "tool": event["tool"],
            "resource_uri": event["resource_uri"],
            "status": "loading",
            "input": event["input"],
            "result": {"content": [], "structuredContent": {}, "isError": False},
            "csp": {},
            "permissions": {"clipboardWrite": True},
            "height": 525,
        }
        self.blocks.append(app)
        self.apps[event["id"]] = app

    def _finish_app(self, event: dict[str, Any]) -> None:
        app = self.apps.get(event["id"])
        if app is not None:
            app["status"] = event["status"]
            app["result"] = event["result"]

    def _remember_web_sources(self, content: list[dict[str, Any]]) -> None:
        text = "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return
        for result in results[:5]:
            if not isinstance(result, dict):
                continue
            url = result.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            self.web_sources[url] = {
                "kind": "external_source",
                "position": 0,
                "route_id": None,
                "url": url,
                "source_type": "article",
                "provider": "web",
                "title": str(result.get("title") or "Web source")[:500],
                "excerpt": str(result.get("excerpt") or "")[:4_000],
                "source_url": None,
                "thumbnail_url": result.get("image_url"),
                "favicon_url": result.get("favicon_url"),
                "arxiv_id": None,
                "semantic_scholar_id": None,
                "authors": [],
                "published": result.get("published_date"),
                "conference": None,
                "citation_count": None,
            }

    def finalize(
        self, db, *, prior_citations: list[dict[str, Any]] | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        if not any(block.get("kind") == "answer" for block in self.blocks):
            self.blocks.append({"kind": "answer", "text": "", "done": True})
        else:
            for block in self.blocks:
                if block.get("kind") == "answer":
                    block["done"] = True
        all_candidates = [
            *self.paper_candidates,
            *candidates_from_citation_history(prior_citations or []),
        ]
        original_answer = "".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") == "answer"
        )
        used_candidates: dict[str, PaperCitationCandidate] = {}
        remaining_candidates = all_candidates
        for block in self.blocks:
            if block.get("kind") != "answer":
                continue
            block["text"] = normalize_s2_catalog_links(
                block.get("text", ""), remaining_candidates, db
            )
            block["text"], used = repair_exact_paper_titles(
                block.get("text", ""), remaining_candidates, db
            )
            used_candidates.update(used)
            remaining_candidates = [
                candidate
                for candidate in remaining_candidates
                if candidate.title.casefold() not in used_candidates
            ]
        text = "\n".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") in {"reasoning", "answer"}
        )
        resolved, resolved_targets = resolve_citation_targets(db, text)
        for block in self.blocks:
            if block.get("kind") in {"reasoning", "answer"}:
                block["text"] = normalize_paper_links(
                    block.get("text", ""), resolved_targets
                )
        self.answer_parts = [
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") == "answer"
        ]
        answer = "".join(self.answer_parts)
        text = "\n".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("kind") in {"reasoning", "answer"}
        )
        if resolved:
            candidate_by_arxiv = {
                candidate.arxiv_id: candidate
                for candidate in all_candidates
                if candidate.arxiv_id
            }
            self.citations = []
            for item in resolved:
                candidate = candidate_by_arxiv.get(item.get("arxiv_id"))
                self.citations.append(_catalog_paper_snapshot(item, candidate))
        else:
            cited = set(re.findall(r"\]\(paper:([^) \t\n]{1,200})\)", text))
            self.citations = [
                {
                    "kind": "catalog_paper",
                    "url": None,
                    "source_type": None,
                    "provider": "paperswithcode",
                    "excerpt": None,
                    "favicon_url": None,
                    "semantic_scholar_id": None,
                    **item,
                }
                for item in self.citations
                if item["route_id"] in cited
            ]
        web_urls = list(
            dict.fromkeys(re.findall(r"\]\((https://[^) \t\n]{1,2000})\)", text))
        )
        for url in web_urls:
            candidate = _external_paper_candidate(url, all_candidates)
            if candidate is not None and len(self.citations) < 20:
                self.citations.append(
                    _external_paper_snapshot(candidate, url, len(self.citations))
                )
                continue
            source = self.web_sources.get(url)
            if source is not None and len(self.citations) < 20:
                self.citations.append({**source, "position": len(self.citations)})
        _attach_block_citations(self.blocks, self.citations)
        self.citation_metrics = {
            **citation_format_counts(
                original_answer, all_candidates, set(used_candidates)
            ),
            "catalog_papers": sum(
                citation.get("kind") == "catalog_paper" for citation in self.citations
            ),
            "external_papers": sum(
                citation.get("kind") == "external_source"
                and citation.get("source_type") == "paper"
                for citation in self.citations
            ),
        }
        return answer, self.citations


def _trusted_artifact_ready(
    event: dict[str, Any], admission: TurnAdmission
) -> dict[str, Any] | None:
    try:
        artifact_id = uuid.UUID(str(event["artifact_id"]))
        version_id = uuid.UUID(str(event["version_id"]))
    except (KeyError, TypeError, ValueError):
        return None
    with db_manager.session_local() as db:
        row = db.scalar(
            select(ChatArtifactVersion)
            .join(ChatArtifact)
            .where(
                ChatArtifactVersion.id == version_id,
                ChatArtifactVersion.artifact_id == artifact_id,
                ChatArtifactVersion.turn_id == admission.turn_id,
                ChatArtifactVersion.state == "ready",
                ChatArtifact.session_id == admission.session_id,
            )
        )
        if row is None:
            return None
        artifact = row.artifact
        expected = {
            "identifier": artifact.identifier,
            "version": row.version,
            "kind": "posterly",
            "title": artifact.title,
            "preview_mime": "image/png",
            "source_language": "html",
            "gate_status": row.gate_status,
            "total_bytes": row.byte_count,
        }
        if any(event.get(key) != value for key, value in expected.items()):
            return None
        return {
            "type": "artifact_ready",
            "publication_id": str(event["publication_id"]),
            "artifact_id": str(artifact.id),
            "version_id": str(row.id),
            **expected,
        }


def _trusted_paper_artifact(
    event: dict[str, Any],
    owner: ChatOwner,
    admission: TurnAdmission,
    settings: Settings,
) -> dict[str, Any] | None:
    if event.get("operation") not in {
        "create",
        "begin-edit",
        "draft",
        "repair",
    } or not isinstance(event.get("activated"), bool):
        return None
    try:
        artifact_id = uuid.UUID(str((event.get("descriptor") or {})["artifact_id"]))
    except (KeyError, TypeError, ValueError):
        return None
    with db_manager.session_local() as db:
        artifact = db.scalar(
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifact.session_id == admission.session_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner.hf_user_id,
            )
        )
        if artifact is None:
            return None
        descriptor = LatexPaperService(db, settings).get_descriptor(
            owner.hf_user_id, admission.session_id
        )
        if descriptor is None or descriptor.artifact_id != artifact.id:
            return None
        expected = descriptor.model_dump(mode="json")
        if event.get("descriptor") != expected:
            return None
        return {
            "type": "paper_artifact",
            "operation": event["operation"],
            "activated": event["activated"],
            "descriptor": expected,
        }


def _public_poster_tool_event(kind: str, event: dict[str, Any]) -> dict[str, Any]:
    if kind == "tool_call":
        args, redacted = _safe_poster_tool_args(
            str(event.get("name") or ""), event.get("args")
        )
        return {**event, "args": args, "redacted": redacted}
    if kind == "tool_call_start":
        return {**event, "redacted": False}
    if kind == "tool_call_arguments_delta":
        args, redacted = _safe_poster_tool_args(
            str(event.get("name") or ""), event.get("partial_args")
        )
        # Raw JSON fragments can contain a secret before they become parseable.
        # Poster streams therefore publish a replaceable sanitized snapshot.
        return {
            **event,
            "delta": json.dumps(args, ensure_ascii=False, separators=(",", ":")),
            "partial_args": args,
            "snapshot": True,
            "redacted": redacted,
        }
    if kind == "tool_call_arguments_done":
        args, redacted = _safe_poster_tool_args(
            str(event.get("name") or ""), event.get("args")
        )
        return {**event, "args": args, "redacted": redacted}
    if kind == "tool_result":
        return {
            **event,
            "content": [
                {
                    "type": "text",
                    "text": "Poster workflow step completed.",
                    "truncated": bool(
                        (event.get("metadata") or {}).get("output_truncated")
                    ),
                }
            ],
        }
    return event


_PRIVATE_PAPER_TOOL_NAMES = frozenset(
    {
        "Bash",
        "Read",
        "Grep",
        "Glob",
        "Ls",
        "Write",
        "Edit",
        "WebFetch",
        "search_web",
    }
)


def _private_paper_tool_event(kind: str, event: dict[str, Any]) -> dict[str, Any]:
    """Project paper-authoring tool activity without retaining source text.

    Paper source belongs only in the owner-scoped artifact store.  Tool events are
    copied into chat display blocks and tracing, so they must not retain command
    arguments, streamed fragments, or compiler/editor output.
    """

    tool_id = str(event.get("id") or "")
    tool_name = str(event.get("name") or "private-paper-tool")
    if tool_name not in _PRIVATE_PAPER_TOOL_NAMES:
        tool_name = "private-paper-tool"
    base = {
        "type": kind,
        "id": tool_id,
        "name": tool_name,
        "redacted": True,
    }
    if kind == "tool_call":
        return {**base, "args": {}}
    if kind == "tool_call_start":
        raw_content_index = event.get("content_index")
        content_index = raw_content_index if isinstance(raw_content_index, int) else 0
        return {**base, "content_index": max(0, content_index)}
    if kind == "tool_call_arguments_delta":
        return {
            **base,
            "delta": "{}",
            "partial_args": {},
            "snapshot": True,
        }
    if kind == "tool_call_arguments_done":
        return {**base, "args": {}}
    if kind == "tool_result":
        status = str(event.get("status") or "success")
        if status not in {"success", "error"}:
            status = "error"
        raw_took_ms = event.get("took_ms")
        took_ms = raw_took_ms if isinstance(raw_took_ms, int) else 0
        return {
            **base,
            "status": status,
            "took_ms": max(0, took_ms),
            "content": [
                {
                    "type": "text",
                    "text": "Private paper tool output omitted.",
                    "truncated": True,
                }
            ],
            "metadata": {"exit_code": None, "output_truncated": True},
            "results": [],
        }
    return base


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|secret|password|authorization)\b"
    r"|\b[A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD))(\s*[:=]\s*)([^\s;&|]+)"
)
_SECRET_FLAG = re.compile(
    r"(?i)(--?(?:api[-_]?key|token|secret|password|authorization)(?:=|\s+))"
    r"([^\s;&|]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_DATA_URL = re.compile(r"(?is)data:[^,\s]+,[^\s'\"]+")
_HEREDOC = re.compile(
    r"(?ms)(<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\n).*?^\2\s*$"
)
_LONG_QUOTED = re.compile(r"(['\"])(?:(?!\1).){160,}\1", re.DOTALL)
_INLINE_BODY_FLAG = re.compile(
    r"(?is)(\s(?:-c|--eval|-e|-d|--data|--data-raw)\s+)(['\"]).*?\2"
)


def _bounded_poster_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value, False
    if not isinstance(value, str):
        return "<value redacted>", True
    bounded = value[:500]
    return bounded, len(bounded) != len(value)


def _safe_poster_command(command: str) -> tuple[str, bool]:
    value = command[:4_000]
    redacted = len(value) != len(command)
    executable = value.lstrip().split(maxsplit=1)[0] if value.strip() else ""
    if executable in {"echo", "printf"}:
        destination = re.search(
            r"(?s)(?P<redirect>\s(?:>>?|\|\s*tee(?:\s+-a)?)\s+)"
            r"(?P<path>(?:/workspace/|\./)?[A-Za-z0-9_./-]+)\s*$",
            value,
        )
        suffix = (
            f"{destination.group('redirect')}{destination.group('path')}"
            if destination
            else ""
        )
        return f"{executable} <inline content redacted>{suffix}", True
    allowed_executables = {
        "awk",
        "bash",
        "cd",
        "cat",
        "chromium",
        "cp",
        "curl",
        "find",
        "git",
        "grep",
        "ls",
        "mkdir",
        "mv",
        "node",
        "npm",
        "npx",
        "playwright",
        "posterly",
        "pwc",
        "python",
        "python3",
        "sed",
        "sh",
        "test",
        "tee",
        "uv",
    }
    if (
        executable
        and executable not in allowed_executables
        and not executable.startswith(("./", "/workspace/"))
    ):
        return "<inline content redacted>", True
    value, count = _HEREDOC.subn(r"\1<heredoc body redacted>\n\2", value)
    redacted |= count > 0
    value, count = _SECRET_ASSIGNMENT.subn(r"\1\2<credential redacted>", value)
    redacted |= count > 0
    value, count = _SECRET_FLAG.subn(r"\1<credential redacted>", value)
    redacted |= count > 0
    value, count = _BEARER.subn("Bearer <credential redacted>", value)
    redacted |= count > 0
    value, count = _DATA_URL.subn("<data URL redacted>", value)
    redacted |= count > 0
    value, count = _LONG_QUOTED.subn('"<inline content redacted>"', value)
    redacted |= count > 0
    value, count = _INLINE_BODY_FLAG.subn(r"\1\2<inline content redacted>\2", value)
    redacted |= count > 0
    if re.search(r"(?is)<!doctype\s+html|<html\b", value):
        value = re.sub(
            r"(?is)(<!doctype\s+html|<html\b).*",
            "<inline HTML redacted>",
            value,
        )
        redacted = True
    return value, redacted


def _safe_workspace_path(value: Any) -> tuple[str, bool]:
    raw = str(value or "")[:1_000].replace("\\", "/")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("/workspace/"):
        return normalized.removeprefix("/workspace/"), False
    if normalized == "/workspace":
        return ".", False
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        return "<path redacted>", True
    return normalized, normalized != raw


def _safe_poster_tool_args(name: str, raw_args: Any) -> tuple[dict[str, Any], bool]:
    args = raw_args if isinstance(raw_args, dict) else {}
    if name == "Bash":
        command, redacted = _safe_poster_command(str(args.get("command") or ""))
        safe: dict[str, Any] = {"command": command or "<command pending>"}
        for key in ("timeout", "description"):
            if key in args:
                safe[key], changed = _bounded_poster_value(args[key])
                redacted |= changed
        return safe, redacted or bool(set(args) - {"command", "timeout", "description"})
    if name == "Read":
        path, redacted = _safe_workspace_path(args.get("file_path") or args.get("path"))
        safe = {"file_path": path or "<path pending>"}
        for key in ("offset", "limit"):
            if key in args:
                safe[key], changed = _bounded_poster_value(args[key])
                redacted |= changed
        return safe, redacted or bool(
            set(args) - {"file_path", "path", "offset", "limit"}
        )
    allowed = {
        "Grep": {"pattern", "path", "glob", "limit"},
        "Glob": {"pattern", "path"},
        "Ls": {"path", "limit"},
        "pwc": {"query", "paper", "task", "limit"},
    }.get(name, set())
    safe = {}
    redacted = bool(set(args) - allowed)
    for key in allowed & set(args):
        if key in {"path", "file_path"}:
            safe[key], changed = _safe_workspace_path(args[key])
        else:
            safe[key], changed = _bounded_poster_value(args[key])
        redacted |= changed
    if not safe and args:
        safe = {"details": "<arguments redacted>"}
        redacted = True
    return safe, redacted


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


def _persist_preparation_failure(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    code: str,
) -> None:
    with db_manager.session_local() as db:
        try:
            ChatSessionService(db, settings).abort_prepared_edit(owner, admission, code)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "chat edit preparation cleanup failed session_id=%s",
                admission.session_id,
            )


def _persist_trace_id(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    trace_id: str,
) -> None:
    if not trace_id:
        return
    try:
        with db_manager.session_local() as db:
            ChatSessionService(db, settings).record_langfuse_trace_id(
                owner, admission, trace_id
            )
            db.commit()
    except Exception:
        logger.warning(
            "chat Langfuse trace correlation persistence failed session_id=%s",
            admission.session_id,
            exc_info=True,
        )


async def _prepare_replacement(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    store: PostgresSDKSessionStore,
    on_activated: Callable[[], None] | None = None,
) -> uuid.UUID | None:
    old_id = admission.sdk_session_id
    if not admission.is_replacement:
        return old_id
    session_directory = (
        "/workspace"
        if getattr(admission, "execution_backend", "local_mcp") == "modal_cli"
        else settings.chat_agent_cwd
    )
    project_key = project_key_for_directory(session_directory)
    replacement_id: uuid.UUID | None = None
    is_pi = getattr(admission, "agent_harness", "claude") == "pi"
    logger.info(
        "chat edit preparing session_id=%s target_id=%s source_sdk_id=%s cutoff_id=%s",
        admission.session_id,
        admission.replacement_target_id,
        old_id,
        admission.resume_boundary_id,
    )
    try:
        if old_id is not None and (
            admission.agent_resume_boundary_id
            if is_pi
            else admission.resume_boundary_id
        ):
            if is_pi:
                replacement_id = uuid.uuid4()
                with db_manager.session_local() as db:
                    ChatPiTranscriptService(db, settings).prepare_fork(
                        admission.session_id,
                        old_id,
                        str(admission.agent_resume_boundary_id),
                        replacement_id,
                    )
                    recorded = ChatSessionService(db, settings).record_prepared_fork(
                        owner, admission, replacement_id, "pi"
                    )
                    if not recorded:
                        db.rollback()
                        raise ChatServiceError(
                            "stale_turn", 409, "The edit turn changed"
                        )
                    db.commit()
            else:
                result = await fork_session_via_store(
                    store,
                    str(old_id),
                    directory=session_directory,
                    up_to_message_id=str(admission.resume_boundary_id),
                )
                replacement_id = uuid.UUID(result.session_id)
                with db_manager.session_local() as db:
                    recorded = ChatSessionService(db, settings).record_prepared_fork(
                        owner, admission, replacement_id, project_key
                    )
                    if not recorded:
                        db.rollback()
                        raise ChatServiceError(
                            "stale_turn", 409, "The edit turn changed"
                        )
                    db.commit()
        with db_manager.session_local() as db:
            activated = ChatSessionService(db, settings).activate_edit(
                owner,
                admission,
                replacement_id,
                "pi" if is_pi and replacement_id else project_key,
            )
            if not activated:
                db.rollback()
                raise ChatServiceError("stale_turn", 409, "The edit turn changed")
            db.commit()
    except BaseException:
        if replacement_id:
            if is_pi:
                with contextlib.suppress(Exception):
                    with db_manager.session_local() as db:
                        ChatPiTranscriptService(db, settings).delete_prepared_fork(
                            admission.session_id, replacement_id
                        )
                        db.commit()
            else:
                with contextlib.suppress(Exception):
                    await store.delete(
                        {"project_key": project_key, "session_id": str(replacement_id)}
                    )
        logger.info(
            "chat edit activation outcome session_id=%s target_id=%s outcome=failed",
            admission.session_id,
            admission.replacement_target_id,
        )
        raise
    logger.info(
        "chat edit activation outcome session_id=%s target_id=%s fork_sdk_id=%s outcome=activated",
        admission.session_id,
        admission.replacement_target_id,
        replacement_id,
    )
    if on_activated:
        on_activated()
    if old_id is not None and not is_pi:
        try:
            await store.delete(
                {
                    "project_key": admission.sdk_project_key or project_key,
                    "session_id": str(old_id),
                }
            )
            logger.info(
                "chat edit transcript cleanup session_id=%s source_sdk_id=%s outcome=deleted",
                admission.session_id,
                old_id,
            )
        # Cleanup leaks must be recorded without undoing an activated edit.
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chat edit transcript cleanup session_id=%s source_sdk_id=%s outcome=leaked error=%s",
                admission.session_id,
                old_id,
                type(exc).__name__,
            )
    return replacement_id


async def _title_events(
    owner: ChatOwner,
    settings: Settings,
    admission: TurnAdmission,
    token: uuid.UUID,
    prompt: str,
    queue: asyncio.Queue,
    trace: ChatTurnTrace | NullChatTurnTrace,
) -> None:
    started = time.perf_counter()
    await queue.put({"type": "session_title_start"})
    pieces: list[str] = []
    fallback = False
    reserved = False
    dispatched = False
    usage = TitleProviderUsage()
    try:
        if not settings.chat_title_generation_enabled:
            raise ChatTitleBudgetUnavailable(
                "Server-funded title generation is disabled"
            )
        provider_token = {
            "openrouter": settings.chat_openrouter_api_key,
            "huggingface": settings.chat_title_hf_token,
        }.get(settings.chat_title_provider, "")
        if not provider_token:
            raise ChatTitleBudgetUnavailable("The title credential is unavailable")
        with db_manager.session_local() as db:
            try:
                ChatTitleBudgetService(db, settings).reserve_call(token)
            except ChatTitleBudgetUnavailable:
                db.commit()
                raise
            db.commit()
        reserved = True
        with db_manager.session_local() as db:
            ChatTitleBudgetService(db, settings).mark_dispatched(token)
            db.commit()
        dispatched = True
        async for delta in stream_title(
            prompt,
            settings,
            provider_token=provider_token,
            usage=usage,
        ):
            pieces.append(delta)
        title = normalize_title("".join(pieces))
        if not title:
            raise ValueError("empty title")
        with db_manager.session_local() as db:
            ChatTitleBudgetService(db, settings).settle_call(
                token,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                provider_generation_id=usage.generation_id,
            )
            db.commit()
        await queue.put({"type": "session_title_delta", "text": title})
    except Exception:
        if dispatched:
            try:
                with db_manager.session_local() as db:
                    ChatTitleBudgetService(db, settings).settle_call(
                        token,
                        input_tokens=None,
                        output_tokens=None,
                        provider_generation_id=usage.generation_id,
                    )
                    db.commit()
            except Exception as accounting_error:
                logger.error(
                    "chat title settlement failed session_id=%s error=%s",
                    admission.session_id,
                    type(accounting_error).__name__,
                )
        elif reserved:
            try:
                with db_manager.session_local() as db:
                    ChatTitleBudgetService(db, settings).release_call(token)
                    db.commit()
            except Exception as accounting_error:
                logger.error(
                    "chat title reservation release failed session_id=%s error=%s",
                    admission.session_id,
                    type(accounting_error).__name__,
                )
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
    trace.finish_title(final or title, fallback=fallback)
    logger.info(
        "chat provider call complete call_class=title_generation session=%s "
        "duration_ms=%.1f outcome=%s",
        hashlib.sha256(str(admission.session_id).encode()).hexdigest()[:12],
        (time.perf_counter() - started) * 1000,
        "fallback" if fallback else "success",
    )
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
        display_message: str | None = None,
    ) -> None:
        self.settings = settings
        self.owner = owner
        self.admission = admission
        self.prompt = prompt
        self.display_message = display_message or prompt
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
        self.edit_activated = False
        self.first_application_delta_recorded = False
        self.interruption_reason: str | None = None
        self.trace: ChatTurnTrace | NullChatTurnTrace = NullChatTurnTrace()
        self.private_paper_tool_ids: set[str] = set()
        self.tool_timing = _ToolTimingFallback(
            enabled=getattr(admission, "agent_harness", "claude") == "pi"
        )

    async def events(self) -> AsyncIterator[ChatStreamFrame]:
        if self.admission.replay_assistant:
            async for frame in self._events():
                yield frame
            return
        with trace_chat_turn(
            settings=self.settings,
            request_id=self.request_id,
            session_id=str(self.admission.session_id),
            user_id=self.owner.hf_user_id,
            prompt=self.prompt,
            display_prompt=self.display_message,
            model=self.admission.model_route,
            execution_backend=self.admission.execution_backend,
            is_replacement=self.admission.is_replacement,
            reasoning_effort=getattr(self.admission, "reasoning_effort", "high"),
            content_free=getattr(self.admission, "paper_artifacts_enabled", False),
        ) as trace:
            self.trace = trace
            _persist_trace_id(
                self.owner, self.settings, self.admission, self.trace.trace_id
            )
            try:
                async for frame in self._events():
                    yield frame
            except GeneratorExit:
                self.interruption_reason = self.interruption_reason or "stream_closed"
                self.trace.finish(
                    "".join(self.projection.answer_parts),
                    "interrupted",
                    interruption_reason=self.interruption_reason,
                )
                raise
            except asyncio.CancelledError:
                self.interruption_reason = (
                    self.interruption_reason or "stream_cancelled"
                )
                self.trace.finish(
                    "".join(self.projection.answer_parts),
                    "interrupted",
                    interruption_reason=self.interruption_reason,
                )
                raise

    async def _events(self) -> AsyncIterator[ChatStreamFrame]:
        try:
            yield ChatStreamFrame(
                "stream_start",
                {
                    "request_id": self.request_id,
                    "session_id": self.admission.session_id,
                    "provider_execution": self.admission.replay_assistant is None,
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
                self.trace.finish(
                    "", "error", terminal_code="replacement_prepare_failed"
                )
                yield ChatStreamFrame(
                    "error",
                    {
                        "message": "Couldn’t resend this message. Your original conversation was restored.",
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
            if self.title_token:
                self.trace.start_title(self.settings.chat_title_model)
                self.title_task = asyncio.create_task(
                    _title_events(
                        self.owner,
                        self.settings,
                        self.admission,
                        self.title_token,
                        self.display_message,
                        queue,
                        self.trace,
                    )
                )
            async for frame in self._consume(queue):
                yield frame
            await self._reconcile_mirror()
            if self.title_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await self.title_task
        except asyncio.CancelledError:
            interruption_reason = self.interruption_reason or "stream_cancelled"
            await self._cancel_runner()
            if self.admission.is_replacement and not self.edit_activated:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_preparation_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                    )
                )
            else:
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
            self.terminal = "interrupted"
            self.trace.finish(
                "".join(self.projection.answer_parts),
                "interrupted",
                interruption_reason=interruption_reason,
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
            self.trace.finish(
                "".join(self.projection.answer_parts),
                "error",
                terminal_code="persistence_error",
            )
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
            resume_id = await _prepare_replacement(
                self.owner,
                self.settings,
                self.admission,
                self.store,
                lambda: setattr(self, "edit_activated", True),
            )
            return True, resume_id
        except Exception as exc:
            logger.warning(
                "chat replacement preparation failed session_id=%s error=%s",
                self.admission.session_id,
                type(exc).__name__,
            )
            _persist_preparation_failure(
                self.owner, self.settings, self.admission, "replacement_prepare_failed"
            )
            self.terminal = "error"
            return False, None

    async def _produce_research(self, queue: asyncio.Queue) -> None:
        try:
            assert self.runner is not None
            async for event in sequential_reasoning_events(self.runner.events()):
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
                    self.interruption_reason = "client_disconnect"
                    raise asyncio.CancelledError
                if time.monotonic() - last_write >= HEARTBEAT_SECONDS:
                    yield ChatStreamFrame.heartbeat()
                    last_write = time.monotonic()
                continue
            if await self.is_disconnected():
                self.interruption_reason = "client_disconnect"
                raise asyncio.CancelledError
            event = dict(event)
            kind = event.pop("type")
            self.tool_timing.apply(kind, event)
            self.trace.record_event(kind, event)
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
                frame = self._fail_mirror(event)
                self.trace.finish(
                    "".join(self.projection.answer_parts),
                    self.terminal,
                    terminal_code="transcript_mirror_error",
                )
                yield frame
                if self.research_task:
                    self.research_task.cancel()
                continue
            if kind == "_cancelled":
                _persist_failure(
                    self.owner,
                    self.settings,
                    self.admission,
                    "interrupted",
                    True,
                    self.projection.completed_blocks(),
                )
                self.terminal = "stopped"
                self.trace.finish("".join(self.projection.answer_parts), "stopped")
                yield ChatStreamFrame(
                    "done", {"followups": [], "finish_reason": "stopped"}
                )
                continue
            if kind == "_latency":
                self._record_latency_phase(
                    str(event["phase"]),
                    int(event["elapsed_ms"]),
                    acquisition_outcome=event.get("acquisition_outcome"),
                    first_semantic_event_class=event.get("first_semantic_event_class"),
                    pool_miss_reason=event.get("pool_miss_reason"),
                    session_reuse_cohort=event.get("session_reuse_cohort"),
                    failure_stage=event.get("failure_stage"),
                    failure_class=event.get("failure_class"),
                    attempt_kind=event.get("attempt_kind"),
                )
                continue
            if kind == "_execution_telemetry":
                logger.info(
                    "chat execution recovery request_id=%s turn_id=%s "
                    "rounds=%s/%s denied_rounds=%s calls=%s/%s denied_calls=%s "
                    "tooling_closed=%s limit_reached=%s finalizer_attempted=%s "
                    "finalizer_outcome=%s finalization_latency_ms=%s "
                    "recovery_reason=%s recovery_attempts=%s recovery_outcome=%s",
                    self.request_id,
                    self.admission.turn_id,
                    event.get("tool_rounds_executed"),
                    event.get("maximum_tool_rounds"),
                    event.get("tool_rounds_denied"),
                    event.get("tool_calls_allowed"),
                    event.get("maximum_tool_calls"),
                    event.get("tool_calls_denied"),
                    event.get("tooling_close_reason"),
                    event.get("execution_limit_reached"),
                    event.get("finalizer_attempted"),
                    event.get("finalizer_outcome"),
                    event.get("finalization_latency_ms"),
                    event.get("recovery_reason"),
                    event.get("recovery_attempts"),
                    event.get("recovery_outcome"),
                )
                continue
            if kind == "_mcp_readiness":
                ready = event.get("ready") is True
                failure_class = event.get("failure_class")
                logger.info(
                    "chat MCP readiness request_id=%s enabled=%s ready=%s "
                    "failure_class=%s latency_ms=%s tool_count=%s "
                    "egress_digest=%s",
                    self.request_id,
                    ",".join(event.get("enabled_provider_ids") or []),
                    ready,
                    failure_class or "none",
                    event.get("registration_latency_ms"),
                    len(event.get("registered_tool_names") or []),
                    event.get("egress_policy_digest"),
                )
                if self.settings.chat_excalidraw_enabled and not ready:
                    logger.warning(
                        "chat Excalidraw MCP registration failed "
                        "request_id=%s failure_class=%s",
                        self.request_id,
                        failure_class or "configured_not_connected",
                    )
                continue
            if kind == "usage":
                usage = event.get("usage") or {}
                token_count = (
                    sum(
                        int(value)
                        for key, value in usage.items()
                        if isinstance(value, (int, float)) and "token" in str(key)
                    )
                    if isinstance(usage, dict)
                    else 0
                )
                logger.info(
                    "chat provider usage request_id=%s turn_id=%s phase=%s "
                    "provider_requests=%s tokens=%s",
                    self.request_id,
                    self.admission.turn_id,
                    event.get("phase") or "research",
                    event.get("provider_requests") or 0,
                    token_count,
                )
                self.trace.record_usage(event)
                continue

            if kind == "artifact_ready":
                trusted = _trusted_artifact_ready(event, self.admission)
                if trusted is None:
                    logger.warning(
                        "chat artifact receipt rejected request_id=%s turn_id=%s",
                        self.request_id,
                        self.admission.turn_id,
                    )
                    kind = "artifact_error"
                    event = {
                        "type": kind,
                        "publication_id": str(event.get("publication_id") or ""),
                        "code": "artifact_receipt_invalid",
                        "message": "Poster publication could not be verified.",
                    }
                else:
                    event = trusted
            if kind == "paper_artifact":
                trusted_paper = _trusted_paper_artifact(
                    event, self.owner, self.admission, self.settings
                )
                if trusted_paper is None:
                    logger.warning(
                        "chat paper receipt rejected request_id=%s turn_id=%s",
                        self.request_id,
                        self.admission.turn_id,
                    )
                    continue
                event = trusted_paper
            paper_tool_event = kind in {
                "tool_call",
                "tool_call_start",
                "tool_call_arguments_delta",
                "tool_call_arguments_done",
                "tool_result",
            }
            tool_id = str(event.get("id") or "")
            if (
                getattr(self.admission, "paper_artifacts_enabled", False)
                and paper_tool_event
                and (
                    str(event.get("name") or "") in _PRIVATE_PAPER_TOOL_NAMES
                    or tool_id in self.private_paper_tool_ids
                )
            ):
                if kind != "tool_result":
                    self.private_paper_tool_ids.add(tool_id)
                event = _private_paper_tool_event(kind, event)
            if getattr(self.admission, "poster_mode", False) and kind in {
                "tool_call",
                "tool_call_start",
                "tool_call_arguments_delta",
                "tool_call_arguments_done",
                "tool_result",
            }:
                event = _public_poster_tool_event(kind, event)

            elapsed_ms = round((time.perf_counter() - self.started) * 1000)
            if kind == "workspace_ready":
                self._record_latency_phase("sdk_query_dispatched", elapsed_ms)
            if not self.first_application_delta_recorded and kind in {
                "reasoning_delta",
                "tool_call",
                "tool_call_start",
                "answer_delta",
            }:
                self.first_application_delta_recorded = True
                self._record_latency_phase(
                    "first_semantic_event",
                    elapsed_ms,
                    first_semantic_event_class={
                        "reasoning_delta": "reasoning",
                        "tool_call": "tool",
                        "tool_call_start": "tool",
                        "answer_delta": "answer",
                    }[kind],
                )
                self._record_latency_phase("first_application_sse_delta", elapsed_ms)

            self.projection.apply(kind, event)
            if kind == "tool_call":
                self.trace.start_tool(event)
            elif kind == "tool_call_arguments_done":
                self.trace.start_tool(event)
            elif kind == "tool_result":
                self.trace.finish_tool(event)
                self.private_paper_tool_ids.discard(tool_id)
            if kind == "error":
                budget_interrupted = event.get("code") in {
                    "chat_temporarily_disabled",
                    "chat_disabled_interrupted",
                }
                if budget_interrupted:
                    event["code"] = "chat_disabled_interrupted"
                    event["message"] = (
                        "Chat was disabled while this response was running. "
                        "The partial response is saved. Please try again later."
                    )
                with db_manager.session_local() as error_db:
                    provider_code = ChatCapabilityService(
                        error_db
                    ).provider_error_for_turn(
                        self.admission.session_id, self.admission.turn_id
                    )
                    if provider_code:
                        event["code"] = provider_code
                        if provider_code == "hf_inference_billing_exhausted":
                            event["message"] = (
                                "Hugging Face could not bill this request. Your included "
                                "credits may be exhausted; enable or review pay-as-you-go "
                                "billing in Settings."
                            )
                        elif provider_code == "openrouter_monthly_budget_exhausted":
                            usage = OpenRouterUserBudgetService(
                                error_db, self.settings
                            ).status_percentage(self.owner.hf_user_id)
                            reset = usage.resets_at.isoformat().replace("+00:00", "Z")
                            event["message"] = (
                                f"{usage.remaining_percent}% of your monthly shared "
                                "OpenRouter allowance remains, but that is not enough "
                                "to reserve another model call for this response. "
                                f"It resets at {reset}."
                            )
                        elif provider_code == "openrouter_unavailable":
                            event["message"] = (
                                "OpenRouter is currently unavailable. However, "
                                "you can still bring your own key in Settings."
                            )
                        elif provider_code == "openrouter_byok_credential_invalid":
                            event["message"] = (
                                "Your OpenRouter API key is no longer valid. "
                                "Reconnect it in Settings, then try again."
                            )
                        elif provider_code == "openrouter_byok_billing_error":
                            event["message"] = (
                                "Your OpenRouter key is connected, but OpenRouter "
                                "rejected billing for the account behind it. A key "
                                "spending limit is not an account credit balance. "
                                "Add credits or enable pay-as-you-go in OpenRouter, "
                                "then try again."
                            )
                        elif provider_code == "openrouter_byok_rate_limit":
                            event["message"] = (
                                "Your OpenRouter API key is temporarily rate-limited."
                            )
                _persist_failure(
                    self.owner,
                    self.settings,
                    self.admission,
                    event.get("code") or "provider_error",
                    budget_interrupted,
                    self.projection.completed_blocks(),
                )
                self.terminal = "error"
                self.trace.finish(
                    "".join(self.projection.answer_parts),
                    "error",
                    terminal_code=event.get("code") or "provider_error",
                )
            elif kind == "done":
                self._complete_turn(event)
                event["citations"] = self.projection.citations
                self.terminal = event.get("finish_reason", "success")
                self.trace.finish("".join(self.projection.answer_parts), self.terminal)
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
        logger.warning(
            "chat transcript mirror failed session_id=%s sdk_session_id=%s error=%s",
            self.admission.session_id,
            mirror_session_id,
            str(event.get("error") or "unknown")[:500],
        )
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
        terminal = event.get("terminal")
        completed_result = (
            event.get("result_available") is True
            and isinstance(terminal, dict)
            and terminal.get("type") == "done"
        )
        with db_manager.session_local() as db:
            service = ChatSessionService(db, self.settings)
            service.mark_transcript_degraded(
                self.owner, self.admission.session_id, self.admission.turn_id
            )
            if completed_result:
                terminal_payload = {
                    key: value
                    for key, value in terminal.items()
                    if key not in {"v", "type", "request_id"}
                }
                answer, citations = self._finalize_projection(db, service)
                service.complete_turn(
                    self.owner,
                    self.admission,
                    answer,
                    citations,
                    terminal_payload.get("followups", []),
                    self.projection.completed_blocks(),
                    terminal_payload.get("finish_reason", "success"),
                )
            else:
                service.fail_turn(
                    self.owner,
                    self.admission,
                    "transcript_mirror_error",
                    False,
                    self.projection.completed_blocks(),
                )
            db.commit()
        if completed_result:
            self.terminal = terminal_payload.get("finish_reason", "success")
            logger.warning(
                "chat transcript mirror failed after model result session_id=%s",
                self.admission.session_id,
            )
            return ChatStreamFrame(
                "done",
                {
                    **terminal_payload,
                    "citations": self.projection.citations,
                    "transcript_status": "degraded",
                    "warning": (
                        "The answer was saved, but its research transcript is "
                        "temporarily unavailable. Follow-up actions are disabled."
                    ),
                },
            )
        self.terminal = "error"
        logger.warning(
            "chat transcript mirror failed before model result session_id=%s",
            self.admission.session_id,
        )
        return ChatStreamFrame(
            "error",
            {
                "message": "The conversation could not be saved.",
                "code": "transcript_mirror_error",
            },
        )

    def _complete_turn(self, event: dict[str, Any]) -> None:
        with db_manager.session_local() as db:
            service = ChatSessionService(db, self.settings)
            answer, citations = self._finalize_projection(db, service)
            service.complete_turn(
                self.owner,
                self.admission,
                answer,
                citations,
                event.get("followups", []),
                self.projection.completed_blocks(),
                event.get("finish_reason", "success"),
            )
            db.commit()

    def _finalize_projection(
        self, db, service: ChatSessionService
    ) -> tuple[str, list[dict[str, Any]]]:
        history = service.citation_history(
            self.admission.session_id,
            before_sequence=getattr(
                self.admission, "replacement_target_sequence", None
            ),
        )
        finalized = self.projection.finalize(db, prior_citations=history)
        metrics = self.projection.citation_metrics
        self.trace.record_citation_metrics(metrics)
        logger.info(
            "chat citation format model=%s prompt_hash=%s references=%s "
            "authored=%s repaired=%s unresolved=%s catalog=%s external=%s "
            "compliance_rate=%s",
            self.admission.selected_model,
            getattr(self.admission, "system_prompt_sha256", "") or "unknown",
            metrics.get("paper_references", 0),
            metrics.get("authored_correctly", 0),
            metrics.get("repaired", 0),
            metrics.get("unresolved", 0),
            metrics.get("catalog_papers", 0),
            metrics.get("external_papers", 0),
            metrics.get("compliance_rate", 1.0),
        )
        return finalized

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
        # Starlette may close an async response generator with GeneratorExit
        # instead of delivering CancelledError. Persist the interruption here
        # as a last resort so a disconnected browser cannot leave the turn
        # generating until its lease expires.
        if self.terminal == "disconnect":
            self.interruption_reason = self.interruption_reason or "stream_closed"
            if self.admission.is_replacement and not self.edit_activated:
                await asyncio.shield(
                    asyncio.to_thread(
                        _persist_preparation_failure,
                        self.owner,
                        self.settings,
                        self.admission,
                        "interrupted",
                    )
                )
            else:
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
            self.terminal = "interrupted"
            self.trace.finish(
                "".join(self.projection.answer_parts),
                "interrupted",
                interruption_reason=self.interruption_reason,
            )
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
        status = {
            "success": "complete",
            "max_turns": "complete",
            "tool_limit": "complete",
            "stopped": "stopped",
            "error": "error",
        }.get(self.terminal, "interrupted")
        try:
            with db_manager.session_local() as db:
                ChatLatencyService(db).finalize(
                    self.request_id,
                    status,
                    round((time.perf_counter() - self.started) * 1000),
                )
                db.commit()
        except Exception as exc:
            logger.warning(
                "chat latency finalize failed request_id=%s error=%s",
                self.request_id,
                type(exc).__name__,
            )
        await self.release_admission()

    def _record_latency_phase(
        self,
        phase: str,
        elapsed_ms: int,
        *,
        acquisition_outcome: str | None = None,
        first_semantic_event_class: str | None = None,
        pool_miss_reason: str | None = None,
        session_reuse_cohort: str | None = None,
        failure_stage: str | None = None,
        failure_class: str | None = None,
        attempt_kind: str | None = None,
    ) -> None:
        try:
            with db_manager.session_local() as db:
                latency = ChatLatencyService(db)
                latency.record_phase(
                    self.request_id,
                    phase,
                    elapsed_ms,
                    acquisition_outcome=acquisition_outcome,
                    first_semantic_event_class=first_semantic_event_class,
                    pool_miss_reason=pool_miss_reason,
                    session_reuse_cohort=session_reuse_cohort,
                    failure_stage=failure_stage,
                    failure_class=failure_class,
                    attempt_kind=attempt_kind,
                )
                if (
                    acquisition_outcome == "pool_miss"
                    and pool_miss_reason == "unhealthy_blank"
                ):
                    latency.record_pool_assignment_fallback(self.request_id)
                db.commit()
        except Exception as exc:
            logger.warning(
                "chat latency phase failed request_id=%s phase=%s error=%s",
                self.request_id,
                phase,
                type(exc).__name__,
            )
