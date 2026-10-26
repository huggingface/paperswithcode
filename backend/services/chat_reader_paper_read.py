"""Serve the reader's page-tagged paper text to ``pwc_read_paper``.

A reader turn cites ``{p5b3}`` block tags from the primary paper's layout
Markdown. The hosted MCP ``read_paper`` returns canonical Markdown without those
tags, so a model that continued or re-read the primary paper through the tool
answered from text it could not cite. The chat gateway answers those reads from
the same tagged text instead; offsets count its UTF-8 bytes exactly as the
context's ``included_bytes`` does, so a continuation starts where it ended.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatMessageRecord
from backend.services.paper_layout_service import (
    citable_markdown,
    read_paged_markdown_bounded,
    read_paper_layout,
)

logger = logging.getLogger(__name__)

CURSOR_PREFIX = "layout:"
# The cursor after the last tagged chunk of a page-capped layout; following it
# reads the untagged stored Markdown through the hosted MCP from the start.
UNTAGGED_CURSOR_PREFIX = "layout-untagged:"
CHUNK_BYTES = 64 * 1024
LAYOUT_MAX_BYTES = 2 * 1024 * 1024


class ReaderPaperCursorError(Exception):
    """A layout cursor no longer matches the paper's tagged text."""


def _primary_layout_context(db: Session, turn_id: str) -> dict[str, Any] | None:
    context = db.scalar(
        select(ChatMessageRecord.primary_paper_context)
        .where(
            ChatMessageRecord.turn_id == turn_id,
            ChatMessageRecord.role == "user",
        )
        .order_by(ChatMessageRecord.revision.desc())
        .limit(1)
    )
    if not context or context.get("content_origin") != "layout_markdown":
        return None
    return context


def _result(paper: str, markdown: str, next_cursor: str | None) -> dict[str, Any]:
    page = {
        "schema_version": "v1",
        "paper": paper,
        "markdown": markdown,
        "truncated": next_cursor is not None,
        "next_cursor": next_cursor,
        "in_catalog": True,
        "available_at": None,
    }
    return {
        "content": [{"type": "text", "text": json.dumps(page)}],
        "structuredContent": page,
    }


def read_reader_paper(
    db: Session, settings: Settings, turn_id: str, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    """Return a ``read_paper`` result from the tagged text, or ``None`` to use MCP.

    Only the turn's primary reader paper with layout Markdown is served here,
    addressed by its route, PwC or arXiv ID. Raises ``ReaderPaperCursorError``
    when a layout cursor is stale.
    """
    cursor = arguments.get("cursor")
    offset = arguments.get("offset")
    if cursor is not None and not str(cursor).startswith(CURSOR_PREFIX):
        return None
    if cursor is not None and offset is not None:
        return None
    context = _primary_layout_context(db, turn_id)
    paper = str(arguments.get("paper") or "").strip()
    if context is None or paper not in {
        value
        for value in (
            context.get("route_id"),
            context.get("paper_id"),
            context.get("arxiv_id"),
        )
        if value
    }:
        return None
    source = context["source"]
    markdown_id = context["arxiv_id"] if source == "arxiv" else context["paper_id"]
    try:
        markdown, _ = read_paged_markdown_bounded(
            markdown_id,
            source=source,
            bucket_id=settings.paper_layout_hf_bucket_id,
            token=settings.hf_token or None,
            max_bytes=LAYOUT_MAX_BYTES,
        )
    except ValueError as error:
        # Without the tagged text the canonical Markdown is still worth reading.
        logger.warning(
            "chat reader paper read outcome=layout_unavailable paper_id=%s error=%s",
            context["paper_id"],
            type(error).__name__,
        )
        return None
    data = citable_markdown(markdown.replace("\x00", " ")).encode()
    version = hashlib.sha256(data).hexdigest()[:16]

    start = int(offset or 0)
    if cursor is not None:
        cursor_version, _, cursor_offset = str(cursor)[len(CURSOR_PREFIX) :].partition(
            ":"
        )
        if cursor_version != version or not cursor_offset.isdigit():
            raise ReaderPaperCursorError(
                "Paper text changed; read it again from the beginning"
            )
        start = int(cursor_offset)
    start = min(start, len(data))
    while start < len(data) and data[start] & 0xC0 == 0x80:
        start += 1
    end = min(start + CHUNK_BYTES, len(data))
    while end < len(data) and data[end] & 0xC0 == 0x80:
        end -= 1
    text = data[start:end].decode()
    if end < len(data):
        return _result(paper, text, f"{CURSOR_PREFIX}{version}:{end}")

    try:
        layout = read_paper_layout(
            markdown_id,
            source=source,
            bucket_id=settings.paper_layout_hf_bucket_id,
            token=settings.hf_token or None,
        )
    except (ValueError, KeyError, OSError) as error:
        # The sidecar only says whether pages are missing; keep the tagged text.
        logger.warning(
            "chat reader paper read outcome=sidecar_unavailable paper_id=%s error=%s",
            context["paper_id"],
            type(error).__name__,
        )
        return _result(paper, text, None)
    if layout["processed_pages"] >= layout["page_count"]:
        return _result(paper, text, None)
    text += (
        f"\n\n[The page-tagged text ends after page {layout['processed_pages']} of "
        f'{layout["page_count"]}. Continuing with cursor "next" reads the untagged '
        "stored Markdown from the beginning; only the tags above can be cited.]"
    )
    return _result(paper, text, f"{UNTAGGED_CURSOR_PREFIX}{version}")
