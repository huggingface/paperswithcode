"""
Per-paper social preview (Open Graph / Twitter) meta tag injection.

Paper pages are normally rendered by the React SPA from `frontend/dist/
index.html`, which carries only generic site-wide social tags. Crawlers like
Twitterbot, Slackbot and Discord don't execute JavaScript, so they always see
the same generic preview for every paper URL.

This module returns a per-paper variant of the SPA HTML with paper-specific
`<title>`, `description`, `og:*` and `twitter:*` tags injected, including
an absolute image URL pointing at the paper's existing thumbnail when the
image is already on disk. Newly imported arXiv papers use Hugging Face's
first-page social preview until the local thumbnail is ready; other missing
images use a shared static fallback that always exists.

Nothing here touches the React bundle or runtime behaviour. The injected
HTML still references the same Vite-built `index.html`, and React takes over
once it boots.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

from PIL import Image as PILImage

from backend.models.papers import Paper
from backend.services.paper_seo_service import (
    PaperSeoDocument,
    render_bibliographic_meta,
)
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.latex_text import latex_to_plain_text

logger = logging.getLogger(__name__)


PRODUCTION_ORIGIN = "https://paperswithcode.co"
FALLBACK_IMAGE_PATH = "/api/og/default.png"
MAX_DESCRIPTION_CHARS = 280
HF_PAPER_SOCIAL_THUMBNAIL_TEMPLATE = (
    "https://cdn-thumbnails.huggingface.co/social-thumbnails/"
    "papers/{arxiv_id}/gradient.png"
)

# The default OG image (backend/services/default_og_image.py) is a 1200x630 PNG,
# the standard summary_large_image size.
FALLBACK_IMAGE_MIME = "image/png"
FALLBACK_IMAGE_WIDTH = 1200
FALLBACK_IMAGE_HEIGHT = 630
HF_PAPER_SOCIAL_THUMBNAIL_MIME = "image/png"
HF_PAPER_SOCIAL_THUMBNAIL_WIDTH = 1200
HF_PAPER_SOCIAL_THUMBNAIL_HEIGHT = 630


@dataclass(frozen=True)
class _ResolvedImage:
    """Outcome of resolving the social image URL for a paper."""

    absolute_url: str
    is_fallback: bool
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


def build_request_origin(
    scheme: Optional[str],
    host: Optional[str],
) -> str:
    """
    Build the public origin (``scheme://host``) for absolute URLs in meta tags.

    Falls back to the production origin when the request did not carry
    trustworthy forwarded headers (the typical case when curling the
    backend directly without a host header).
    """
    safe_scheme = (scheme or "https").lower()
    if safe_scheme not in {"http", "https"}:
        safe_scheme = "https"
    safe_host = (host or "").strip()
    if not safe_host:
        return PRODUCTION_ORIGIN
    return f"{safe_scheme}://{safe_host}"


def _truncate_description(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[: limit - 1].rstrip()
    return truncated + "\u2026"


def _absolutize(url: str, origin: str) -> str:
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return url
    return origin.rstrip("/") + "/" + url.lstrip("/")


def _is_arxiv_thumbnail_url(path: str) -> bool:
    return path.startswith("/api/thumbnails/") and not path.startswith(
        "/api/thumbnails/custom/"
    )


def _is_custom_thumbnail_url(path: str) -> bool:
    return path.startswith("/api/thumbnails/custom/")


def _extract_thumbnail_filename(thumbnail_path: str) -> Optional[str]:
    """Pull the JPEG filename out of an internal /api/thumbnails/... URL."""
    parts = urlsplit(thumbnail_path)
    leaf = parts.path.rsplit("/", 1)[-1]
    if not leaf or "." not in leaf:
        return None
    return leaf


def _strip_thumbnail_query_for_external_check(url: str) -> str:
    """Return ``url`` with query/fragment removed for filesystem lookups."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _guess_image_mime(url: str) -> Optional[str]:
    """Best-effort MIME type from a thumbnail URL's file extension."""
    leaf = urlsplit(url).path.rsplit("/", 1)[-1].lower()
    if leaf.endswith(".png"):
        return "image/png"
    if leaf.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if leaf.endswith(".webp"):
        return "image/webp"
    if leaf.endswith(".gif"):
        return "image/gif"
    return None


def _read_image_dimensions(path: Path) -> tuple[Optional[int], Optional[int]]:
    """Return ``(width, height)`` from an on-disk image, or ``(None, None)``."""
    try:
        with PILImage.open(path) as img:
            return img.width, img.height
    except Exception as exc:
        logger.debug("Could not read image dimensions for %s: %s", path, exc)
        return None, None


def _fallback_image(origin: str) -> _ResolvedImage:
    return _ResolvedImage(
        _absolutize(FALLBACK_IMAGE_PATH, origin),
        is_fallback=True,
        mime_type=FALLBACK_IMAGE_MIME,
        width=FALLBACK_IMAGE_WIDTH,
        height=FALLBACK_IMAGE_HEIGHT,
    )


def _hugging_face_paper_image(arxiv_id: str) -> _ResolvedImage:
    """Return Hugging Face's landscape first-page preview for an arXiv paper."""
    return _ResolvedImage(
        HF_PAPER_SOCIAL_THUMBNAIL_TEMPLATE.format(
            arxiv_id=quote(arxiv_id.strip(), safe="")
        ),
        is_fallback=False,
        mime_type=HF_PAPER_SOCIAL_THUMBNAIL_MIME,
        width=HF_PAPER_SOCIAL_THUMBNAIL_WIDTH,
        height=HF_PAPER_SOCIAL_THUMBNAIL_HEIGHT,
    )


def _missing_paper_image(paper: Paper, origin: str) -> _ResolvedImage:
    """Choose the best social image when the local paper thumbnail is absent."""
    arxiv_id = (paper.arxiv_id or "").strip()
    if paper.source == "arxiv" and arxiv_id:
        return _hugging_face_paper_image(arxiv_id)
    return _fallback_image(origin)


def resolve_social_image_url(
    paper: Paper,
    origin: str,
    thumbnail_service: Optional[ThumbnailService] = None,
) -> _ResolvedImage:
    """
    Pick an absolute image URL for ``og:image`` / ``twitter:image``.

    Prefers the paper's existing thumbnail (the same JPEG the site already
    displays in feed cards). If a newly imported arXiv paper is not on disk
    yet, use Hugging Face's already-generated first-page social image. This
    closes the race between the hourly paper import, social posts, and our
    thumbnail preload. Other papers use the shared default image.
    """
    raw_thumb = (paper.thumbnail_url or "").strip()
    if not raw_thumb:
        return _missing_paper_image(paper, origin)

    if raw_thumb.startswith(("http://", "https://")):
        return _ResolvedImage(
            raw_thumb, is_fallback=False, mime_type=_guess_image_mime(raw_thumb)
        )

    if not raw_thumb.startswith("/"):
        return _fallback_image(origin)

    if _is_arxiv_thumbnail_url(raw_thumb) or _is_custom_thumbnail_url(raw_thumb):
        path_only = _strip_thumbnail_query_for_external_check(raw_thumb)
        filename = _extract_thumbnail_filename(path_only)
        if filename:
            service = thumbnail_service or ThumbnailService()
            on_disk = _check_thumbnail_on_disk(
                service, filename, _is_custom_thumbnail_url(raw_thumb)
            )
            if on_disk is not None:
                width, height = _read_image_dimensions(on_disk)
                return _ResolvedImage(
                    _absolutize(raw_thumb, origin),
                    is_fallback=False,
                    mime_type=_guess_image_mime(path_only) or "image/jpeg",
                    width=width,
                    height=height,
                )

    return _missing_paper_image(paper, origin)


def _check_thumbnail_on_disk(
    service: ThumbnailService, filename: str, is_custom: bool
) -> Optional[Path]:
    """
    Return the local path to the thumbnail JPEG if it is materialised.

    ``get_local_thumbnail_path`` already filters out missing files, so a
    non-``None`` return means the file is on the local mirror. Custom
    thumbnails go through the same disk-only path to avoid per-request HF
    bucket round-trips on the public preview hot path.
    """
    try:
        if is_custom:
            path: Optional[Path] = service.get_local_custom_thumbnail_path(filename)
        else:
            path = service.get_local_thumbnail_path(filename)
    except Exception as exc:
        logger.debug("Thumbnail existence check failed for %s: %s", filename, exc)
        return None
    return path


def _authors_line(authors: list[str], max_authors: int = 5) -> str:
    cleaned = [a for a in (authors or []) if a]
    if not cleaned:
        return ""
    if len(cleaned) <= max_authors:
        return ", ".join(cleaned)
    head = ", ".join(cleaned[:max_authors])
    return f"{head} et al."


def _build_description(paper: Paper) -> str:
    """Pick a sensible description string from abstract + author line."""
    abstract = (paper.abstract or "").strip()
    if abstract:
        return _truncate_description(abstract)

    authors = _authors_line(paper.authors or [])
    if authors:
        return _truncate_description(f"By {authors}.")

    return "Trending AI research papers with code, datasets, methods, and evaluation leaderboards."


def _build_title(paper: Paper) -> str:
    paper_title = latex_to_plain_text((paper.title or "").strip()) or "Paper"
    return f"{paper_title} | Papers with Code"


def _build_image_alt(paper: Paper, is_fallback: bool) -> str:
    if is_fallback:
        return "Papers with Code"
    paper_title = latex_to_plain_text((paper.title or "").strip())
    if paper_title:
        return f"First page preview of {paper_title}"
    return "Paper preview"


def _build_canonical_url(origin: str, route_identifier: str) -> str:
    return f"{origin.rstrip('/')}/paper/{route_identifier}"


@dataclass(frozen=True)
class PaperMetaTags:
    """The set of meta tag values rendered into a paper-page HTML response."""

    title: str
    description: str
    canonical_url: str
    image_url: str
    is_fallback_image: bool
    image_alt: str
    image_mime_type: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None


def build_paper_meta(
    paper: Paper,
    *,
    route_identifier: str,
    origin: str,
    thumbnail_service: Optional[ThumbnailService] = None,
) -> PaperMetaTags:
    image = resolve_social_image_url(paper, origin, thumbnail_service=thumbnail_service)
    return PaperMetaTags(
        title=_build_title(paper),
        description=_build_description(paper),
        canonical_url=_build_canonical_url(origin, route_identifier),
        image_url=image.absolute_url,
        is_fallback_image=image.is_fallback,
        image_alt=_build_image_alt(paper, image.is_fallback),
        image_mime_type=image.mime_type,
        image_width=image.width,
        image_height=image.height,
    )


# --- HTML injection ----------------------------------------------------------


_HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)
_TITLE_TAG_RE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
_META_NAME_RE_TEMPLATE = r'<meta\s+name=["\']{name}["\'][^>]*/?>'
_META_PROPERTY_RE_TEMPLATE = r'<meta\s+property=["\']{prop}["\'][^>]*/?>'
_CANONICAL_LINK_RE = re.compile(
    r'<link\s+rel=["\']canonical["\'][^>]*/?>', re.IGNORECASE
)

# Static social tags shipped in frontend/index.html that we replace with
# paper-specific values. Listed exhaustively so crawlers never see a generic
# site-wide tag ahead of (or alongside) the per-paper one.
_STATIC_META_NAMES = (
    "description",
    "twitter:card",
    "twitter:title",
    "twitter:description",
    "twitter:image",
    "twitter:image:alt",
)
_STATIC_META_PROPERTIES = (
    "og:title",
    "og:description",
    "og:type",
    "og:url",
    "og:image",
    "og:image:secure_url",
    "og:image:type",
    "og:image:width",
    "og:image:height",
    "og:image:alt",
    "og:site_name",
)


def _escape(value: str) -> str:
    return html_lib.escape(value, quote=True)


def _replace_or_remove(html: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub("", html, count=1)


def inject_paper_meta(
    html: str,
    meta: PaperMetaTags,
    document: Optional[PaperSeoDocument] = None,
) -> str:
    """
    Return ``html`` with paper-specific meta tags replacing the static ones.

    The strategy is:
      1. Strip the static meta tags that the production ``index.html`` ships
         with so crawlers don't see conflicting values.
      2. Insert a paper-specific block right before ``</head>`` containing
         the canonical title, description, and Open Graph / Twitter tags.

    String-based rewriting is intentional: the SPA's ``index.html`` is a tiny
    static template, and we want to avoid pulling in an HTML parser dependency
    just for this hot, per-request path.
    """
    rewritten = _TITLE_TAG_RE.sub("", html, count=1)
    rewritten = _CANONICAL_LINK_RE.sub("", rewritten, count=1)
    for name in _STATIC_META_NAMES:
        pattern = re.compile(
            _META_NAME_RE_TEMPLATE.format(name=re.escape(name)), re.IGNORECASE
        )
        rewritten = _replace_or_remove(rewritten, pattern)
    for prop in _STATIC_META_PROPERTIES:
        pattern = re.compile(
            _META_PROPERTY_RE_TEMPLATE.format(prop=re.escape(prop)), re.IGNORECASE
        )
        rewritten = _replace_or_remove(rewritten, pattern)

    block = _render_meta_block(meta, document)

    match = _HEAD_CLOSE_RE.search(rewritten)
    if match:
        insert_at = match.start()
        return rewritten[:insert_at] + block + rewritten[insert_at:]

    return rewritten + block


def _render_meta_block(
    meta: PaperMetaTags, document: Optional[PaperSeoDocument] = None
) -> str:
    title = _escape(meta.title)
    description = _escape(meta.description)
    canonical = _escape(meta.canonical_url)
    image = _escape(meta.image_url)
    image_alt = _escape(meta.image_alt)

    page_title = _escape(document.search_title) if document else title
    page_description = _escape(document.description) if document else description
    social_description = (
        _escape(document.social_description) if document else description
    )
    lines = [
        f"    <title>{page_title}</title>",
        f'    <meta name="description" content="{page_description}" />',
        f'    <link rel="canonical" href="{canonical}" />',
        f'    <meta property="og:title" content="{title}" />',
        f'    <meta property="og:description" content="{social_description}" />',
        '    <meta property="og:type" content="article" />',
        f'    <meta property="og:url" content="{canonical}" />',
        f'    <meta property="og:image" content="{image}" />',
    ]
    if meta.image_url.startswith("https://"):
        lines.append(f'    <meta property="og:image:secure_url" content="{image}" />')
    if meta.image_mime_type:
        lines.append(
            f'    <meta property="og:image:type" content="{_escape(meta.image_mime_type)}" />'
        )
    if meta.image_width:
        lines.append(
            f'    <meta property="og:image:width" content="{meta.image_width}" />'
        )
    if meta.image_height:
        lines.append(
            f'    <meta property="og:image:height" content="{meta.image_height}" />'
        )
    lines.extend(
        [
            f'    <meta property="og:image:alt" content="{image_alt}" />',
            '    <meta property="og:site_name" content="Papers with Code" />',
            '    <meta name="twitter:card" content="summary_large_image" />',
            f'    <meta name="twitter:title" content="{title}" />',
            f'    <meta name="twitter:description" content="{social_description}" />',
            f'    <meta name="twitter:image" content="{image}" />',
            f'    <meta name="twitter:image:alt" content="{image_alt}" />',
        ]
    )

    if document:
        lines.append(
            "    " + render_bibliographic_meta(document).replace("\n", "\n    ")
        )

    return "\n" + "\n".join(lines) + "\n  "
