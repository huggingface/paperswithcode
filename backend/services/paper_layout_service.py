"""Page-aware paper layout for reader citations into the PDF.

The layout bucket holds, per paper, Chandra OCR Markdown with a
``<!-- pwc:p{page}b{block} -->`` anchor before every layout block, plus a
``.blocks.json`` sidecar mapping each anchor to its page, label, bounding box
(on a 0-1000 grid of the page) and enclosing section header. Reader chat cites
anchors; the reader highlights their boxes in the PDF.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from huggingface_hub import HfFileSystem
from huggingface_hub.errors import EntryNotFoundError

from backend.services.paper_markdown_service import (
    normalize_markdown_paper_id,
    paper_markdown_bucket_key,
    read_paper_markdown_bounded,
)

BLOCKS_MAX_BYTES = 8 * 1024 * 1024
PREVIEW_CHARS = 280
CACHE_MAX_ENTRIES = 64
CACHE_TTL_SECONDS = 10 * 60
_PAGE_MARKER = re.compile(r"<!-- pwc:page (\d+) -->")
_BLOCK_MARKER = re.compile(r"<!-- pwc:(p\d+b\d+) -->\n?")


class PaperLayoutNotFoundError(ValueError):
    """The paper has no page-aware layout yet."""


_cache: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_cache_lock = threading.Lock()


def _blocks_key(paper_id: str, source: str) -> str:
    return paper_markdown_bucket_key(paper_id, source=source).removesuffix(".md") + (
        ".blocks.json"
    )


def read_paper_layout(
    paper_id: str, *, source: str, bucket_id: str, token: str | None
) -> dict[str, Any]:
    """Return ``{"page_count", "processed_pages", "blocks"}`` for one paper.

    Each block keeps its page, label, bbox, section anchor and a short text
    preview for hover cards.
    """
    source, normalized = normalize_markdown_paper_id(paper_id, source)
    cache_key = (bucket_id, f"{source}:{normalized}")
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(cache_key)
            return cached[1]

    path = f"hf://buckets/{bucket_id}/{_blocks_key(normalized, source)}"
    try:
        with HfFileSystem(token=token).open(path, "rb", block_size=0) as handle:
            raw = handle.read(BLOCKS_MAX_BYTES + 1)
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise PaperLayoutNotFoundError(f"No layout for paper {normalized}") from error
    if len(raw) > BLOCKS_MAX_BYTES:
        raise PaperLayoutNotFoundError(f"Layout for paper {normalized} is too large")
    sidecar = json.loads(raw)
    layout = {
        "page_count": sidecar["page_count"],
        "processed_pages": sidecar["processed_pages"],
        "blocks": {
            anchor: {
                "page": block["page"],
                "label": block["label"],
                "bbox": block["bbox"],
                "section": block.get("section"),
                "text": block.get("text", "")[:PREVIEW_CHARS],
            }
            for anchor, block in sidecar["blocks"].items()
        },
    }
    with _cache_lock:
        _cache[cache_key] = (now, layout)
        _cache.move_to_end(cache_key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return layout


def read_paged_markdown_bounded(
    paper_id: str, *, source: str, bucket_id: str, token: str | None, max_bytes: int
) -> tuple[str, bool]:
    """Read the anchored Markdown prefix, or raise ``PaperLayoutNotFoundError``."""
    try:
        return read_paper_markdown_bounded(
            paper_id,
            source=source,
            bucket_id=bucket_id,
            token=token,
            max_bytes=max_bytes,
        )
    except ValueError as error:
        if "was not found" in str(error):
            raise PaperLayoutNotFoundError(str(error)) from error
        raise


def citable_markdown(markdown: str) -> str:
    """Rewrite layout comments into compact plain-text tags the model can cite.

    ``<!-- pwc:page 5 -->`` becomes ``[page 5]`` and each block comment becomes
    a ``{p5b3}`` prefix on the block it introduces.
    """
    markdown = _PAGE_MARKER.sub(r"[page \1]", markdown)
    return _BLOCK_MARKER.sub(r"{\1} ", markdown)
