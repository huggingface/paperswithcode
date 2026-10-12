"""
HTTP utilities for fetching arbitrary external pages (blog posts, technical
reports, vendor announcements) used by the external-resource ingestion path.

Kept deliberately small: we only need plain HTML text and best-effort link
extraction. Heavy parsing (LLM page understanding) lives in genai_steps.
"""

import asyncio
import json
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.safe_outbound_http_service import (
    SafeOutboundHttpError,
    fetch_public_resource,
)


logger = logging.getLogger(__name__)


_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_JSON_CONTENT_TYPES = frozenset({"application/json", "text/json", "text/plain"})


async def fetch_html(
    url: str, timeout_seconds: float = 15.0, max_bytes: int = 2_000_000
) -> Optional[str]:
    """
    Fetch an HTML page. Returns the raw HTML text or ``None`` on failure.

    `max_bytes` caps how much body we read so a runaway server cannot fill
    memory; 2 MB is more than enough for any technical report or blog post.
    """
    if not url:
        return None

    try:

        async def _do_fetch() -> Optional[str]:
            result = await fetch_public_resource(
                url,
                allowed_content_types=_HTML_CONTENT_TYPES,
                max_bytes=max_bytes,
                timeout_seconds=timeout_seconds,
            )
            return result.body.decode("utf-8", errors="replace")

        return await asyncio.shield(_do_fetch())
    except SafeOutboundHttpError as exc:
        logger.warning("fetch_html failed for %s: %s", url, exc)
        return None
    except asyncio.CancelledError:
        logger.warning("fetch_html cancelled for %s", url)
        return None


def html_to_text(html: str, max_chars: int = 100_000) -> str:
    """
    Best-effort extraction of readable page text. Falls back to raw text on
    parse errors. The output is truncated to `max_chars` to keep prompts small.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        logger.warning("html_to_text parse failure: %s", exc)
        text = html

    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


_GITHUB_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.IGNORECASE
)
# Up to three path segments so `datasets/<owner>/<name>` and
# `spaces/<owner>/<name>` are not cut down to a bare owner.
_HF_REPO_RE = re.compile(
    r"https?://huggingface\.co/(?!papers/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)?",
    re.IGNORECASE,
)
# First path segments that are GitHub site pages rather than repository owners.
_GITHUB_NON_OWNER_PATHS = frozenset(
    {
        "about",
        "apps",
        "collections",
        "features",
        "login",
        "marketplace",
        "orgs",
        "settings",
        "sponsors",
        "topics",
        "user-attachments",
    }
)
# First path segments on huggingface.co that are not `<owner>/<model>` repos.
_HF_NON_REPO_PATHS = frozenset(
    {
        "api",
        "blog",
        "chat",
        "collections",
        "docs",
        "join",
        "learn",
        "login",
        "models",
        "organizations",
        "papers",
        "posts",
        "pricing",
        "settings",
        "tasks",
    }
)


def _absolute_links_from_html(html: str, base_url: str) -> List[str]:
    """All absolute href links from anchors plus raw URLs found in text."""
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        soup = None

    urls: List[str] = []
    if soup is not None:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href:
                continue
            if href.startswith(("http://", "https://")):
                urls.append(href)
            elif href.startswith("/"):
                urls.append(urljoin(base_url, href))
    # Raw URLs in the visible text catch the case where the link is not
    # wrapped in an anchor tag (common in plain-text reports).
    urls.extend(_GITHUB_RE.findall(html))
    urls.extend(_HF_REPO_RE.findall(html))
    return urls


def _url_path_parts(url: str, host: str) -> List[str]:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    if netloc != host:
        return []
    return [part for part in parsed.path.split("/") if part]


def canonical_github_repo_url(url: str) -> Optional[str]:
    """``https://github.com/<owner>/<name>`` for a GitHub repository link."""
    # Drop trailing path segments (e.g. /tree/main/...).
    parts = _url_path_parts(url, "github.com")[:2]
    if len(parts) < 2 or parts[0].lower() in _GITHUB_NON_OWNER_PATHS:
        return None
    name = parts[1].removesuffix(".git")
    if not name:
        return None
    return f"https://github.com/{parts[0]}/{name}"


def canonical_hf_repo_url(url: str) -> Optional[str]:
    """Canonical model, dataset, or space URL for a Hugging Face repo link.

    Bare owner pages (``/LiquidAI``, ``/datasets/allenai``,
    ``/spaces/multimodalart``) are not artifacts and return None.
    """
    parts = _url_path_parts(url, "huggingface.co")
    if not parts:
        return None
    first = parts[0].lower()
    if first in {"datasets", "spaces"}:
        if len(parts) < 3:
            return None
        return f"https://huggingface.co/{first}/{parts[1]}/{parts[2]}"
    if len(parts) < 2 or first in _HF_NON_REPO_PATHS:
        return None
    return f"https://huggingface.co/{parts[0]}/{parts[1]}"


def _unique_page_urls(html: str, base_url: str, canonicalize) -> List[str]:
    # GitHub and Hub repo ids are case-insensitive, so case variants keep the
    # first spelling seen on the page.
    seen: set = set()
    out: List[str] = []
    for url in _absolute_links_from_html(html, base_url):
        canonical = canonicalize(url)
        if canonical is None or canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        out.append(canonical)
    return out


def extract_github_urls(html: str, base_url: str = "") -> List[str]:
    """Unique-by-(owner, name) GitHub repository URLs found on a page."""
    return _unique_page_urls(html, base_url, canonical_github_repo_url)


def extract_hf_repo_urls(html: str, base_url: str = "") -> List[str]:
    """Unique HF model/dataset/space URLs (owner/name shape) found on a page."""
    return _unique_page_urls(html, base_url, canonical_hf_repo_url)


_FRAMER_SEARCH_INDEX_RE = re.compile(
    r'name="framer-search-index"\s+content="([^"]+)"', re.IGNORECASE
)


async def _framer_search_index_text(html: str, page_url: str) -> Optional[str]:
    """
    Extract content from a Framer-hosted page via its search index JSON.

    Framer (the SPA builder used by some vendor sites such as zyphra.com)
    renders the body client-side, so the raw HTML returned by `fetch_html`
    is essentially empty. The page advertises a `framer-search-index`
    metadata URL whose JSON contains the prerendered text for every page on
    the site keyed by path. This function pulls the entry for the requested
    URL and concatenates its visible text.

    Returns ``None`` when the page is not a Framer SPA or when the index
    cannot be fetched/parsed.
    """
    match = _FRAMER_SEARCH_INDEX_RE.search(html)
    if not match:
        return None

    index_url = match.group(1)
    try:
        result = await fetch_public_resource(
            index_url,
            allowed_content_types=_JSON_CONTENT_TYPES,
            max_bytes=2_000_000,
            timeout_seconds=15.0,
        )
        payload = json.loads(result.body)
    except (SafeOutboundHttpError, ValueError) as exc:
        logger.warning("framer index fetch failed for %s: %s", index_url, exc)
        return None
    except asyncio.CancelledError:
        return None

    if not isinstance(payload, dict):
        return None

    def _entry_text(entry: dict) -> str:
        chunks: List[str] = []
        title = entry.get("title")
        if title:
            chunks.append(str(title))
        for key in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "codeblock"):
            values = entry.get(key) or []
            if isinstance(values, list):
                for v in values:
                    if v:
                        chunks.append(str(v))
        return "\n".join(chunks).strip()

    def _entry_has_body(entry: dict) -> bool:
        """True iff the entry has at least one heading or paragraph."""
        for key in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "codeblock"):
            values = entry.get(key) or []
            if isinstance(values, list) and any(v for v in values):
                return True
        return False

    path = urlparse(page_url).path or "/"
    entry = payload.get(path) or payload.get(path.rstrip("/"))

    # Some pages (e.g. PDF-hosting "technical report" pages) exist in the
    # index with only a site-level title and no body. Fall back to a related
    # companion post whose slug shares a stem with this URL after stripping
    # common suffixes.
    if not isinstance(entry, dict) or not _entry_has_body(entry):
        slug = path.strip("/").split("/")[-1].lower()
        suffix_words = ("-technical-report", "-paper", "-report", "-blog")
        stem = slug
        for suffix in suffix_words:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        candidates = []
        for cand_path, cand in payload.items():
            if not isinstance(cand, dict):
                continue
            cand_slug = cand_path.strip("/").split("/")[-1].lower()
            if not cand_slug:
                continue
            score = 0
            if cand_slug == stem:
                score = 100
            elif stem and cand_slug.startswith(stem + "-"):
                score = 80
            elif stem and stem.startswith(cand_slug + "-"):
                score = 70
            elif stem and stem in cand_slug:
                score = 50
            if score and _entry_has_body(cand):
                candidates.append((score, cand_path, cand))

        if candidates:
            # Prefer /post/... entries (announcement bodies) over /models/...
            candidates.sort(
                key=lambda item: (
                    item[0],
                    1 if item[1].startswith("/post/") else 0,
                ),
                reverse=True,
            )
            entry = candidates[0][2]

    if not isinstance(entry, dict):
        return None

    text = _entry_text(entry)
    return text or None


async def fetch_html_and_text(
    url: str, max_text_chars: int = 60_000
) -> Tuple[Optional[str], Optional[str]]:
    """
    Convenience: fetch a URL and return (raw_html, plain_text). Either tuple
    element may be None if fetching fails.

    Falls back to the Framer search index when the rendered body is empty so
    that JS-only pages (e.g. zyphra.com) still yield usable text for the LLM.
    """
    html = await fetch_html(url)
    if html is None:
        return None, None

    text = html_to_text(html, max_chars=max_text_chars)
    if len(text) < 200:
        framer_text = await _framer_search_index_text(html, url)
        if framer_text:
            text = framer_text[:max_text_chars]

    return html, text
