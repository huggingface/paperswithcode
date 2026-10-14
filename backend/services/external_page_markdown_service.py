"""Turn an external paper's web page into its canonical paper Markdown.

External papers whose source is an HTML page (a lab blog post, a model card,
a repository README) have no PDF for the OCR pipeline. Firecrawl renders the
page and returns its main content as Markdown, which is published to the same
bucket keys the OCR worker writes, so the reader, chat, MCP, and CLI read it
like any other paper.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from huggingface_hub import HfApi, HfFileSystem
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

from backend.scripts.generate_missing_paper_markdown import (
    MARKDOWN_MIGRATION_LOCK_KEY,
    TITLE_STOP_WORDS,
    validate_canonical_markdown,
)
from backend.services.paper_markdown_service import (
    paper_markdown_bucket_key,
    paper_markdown_content_key,
    paper_markdown_manifest_key,
)

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
PAGE_MARKDOWN_MAX_BYTES = 2 * 1024 * 1024
# Shorter pages are abstract stubs or conference listings, not readable papers.
PAGE_MARKDOWN_MIN_CHARS = 2000
# The paper title must appear near the top of the page; a program listing that
# mentions the paper somewhere among hundreds of others is not the paper.
TITLE_WINDOW_CHARS = 4000
TITLE_MATCH_RATIO = 0.6
MAX_ATTEMPTS = 3
# Venue and publisher landing pages show an abstract and link the PDF (often
# behind a paywall); scraping them yields metadata, not a paper. Mirrored in
# frontend/src/lib/paperReader.ts.
LANDING_PAGE_HOSTS = frozenset(
    {
        "aclanthology.org",
        "dl.acm.org",
        "doi.org",
        "dx.doi.org",
        "eccv.ecva.net",
        "ieeexplore.ieee.org",
        "link.springer.com",
        "openaccess.thecvf.com",
        "openreview.net",
        "sciencedirect.com",
        "zenodo.org",
    }
)

_page_locks: dict[str, threading.Lock] = {}
_page_locks_guard = threading.Lock()


class ExternalPageMarkdownError(ValueError):
    """A page could not become paper Markdown; ``code`` names the reason."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class ScrapedPage:
    title: str
    markdown: str


def _is_pdf_url(parsed) -> bool:
    marker = f"{parsed.path}?{parsed.query}".lower()
    return ".pdf" in marker or "/pdf" in parsed.path.lower()


def external_page_url(
    *, source: str | None, source_url: str | None, conference_url_pdf: str | None
) -> str | None:
    """Return the web page to read for an HTML-only external paper."""
    if source != "external" or (conference_url_pdf or "").strip():
        return None
    url = (source_url or "").strip()
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        # A fragment points into a page that lists many papers.
        or parsed.fragment
        or _is_pdf_url(parsed)
        or hostname.removeprefix("www.") in LANDING_PAGE_HOSTS
        or hostname == "localhost"
        or hostname.endswith(".localhost")
    ):
        return None
    try:
        if not ipaddress.ip_address(hostname).is_global:
            return None
    except ValueError:
        pass
    return url


def scrape_page(url: str, *, api_key: str, timeout_seconds: float) -> ScrapedPage:
    """Fetch one page's main content as Markdown through Firecrawl."""
    if not api_key:
        raise ExternalPageMarkdownError("firecrawl_not_configured")
    try:
        response = httpx.post(
            FIRECRAWL_SCRAPE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "blockAds": True,
                "removeBase64Images": True,
                "timeout": int(timeout_seconds * 1000),
            },
            timeout=timeout_seconds + 10,
        )
    except httpx.HTTPError as error:
        raise ExternalPageMarkdownError(
            "firecrawl_unavailable", retryable=True
        ) from error
    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalPageMarkdownError("firecrawl_unavailable", retryable=True)
    if response.status_code in {401, 402, 403}:
        raise ExternalPageMarkdownError("firecrawl_rejected", retryable=True)
    payload = response.json() if response.content else {}
    data = payload.get("data") if isinstance(payload, dict) else None
    if response.status_code >= 400 or not payload.get("success") or not data:
        raise ExternalPageMarkdownError("page_unavailable", retryable=True)
    metadata = data.get("metadata") or {}
    status = metadata.get("statusCode")
    if isinstance(status, int) and status >= 400:
        raise ExternalPageMarkdownError("page_unavailable", retryable=status >= 500)
    title = metadata.get("title") or metadata.get("ogTitle") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    return ScrapedPage(title=str(title), markdown=str(data.get("markdown") or ""))


def _title_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)) - TITLE_STOP_WORDS


def page_paper_markdown(title: str, source_url: str, page: ScrapedPage) -> str:
    """Build canonical paper Markdown, rejecting pages that are not the paper."""
    body = page.markdown.replace("\x00", " ").strip()
    if len(body) < PAGE_MARKDOWN_MIN_CHARS:
        raise ExternalPageMarkdownError("page_too_short")
    expected = _title_tokens(title)
    found = _title_tokens(f"{page.title}\n{body[:TITLE_WINDOW_CHARS]}")
    if expected and len(expected & found) < TITLE_MATCH_RATIO * len(expected):
        raise ExternalPageMarkdownError("page_title_mismatch")
    markdown = (
        f"Title: {title.strip()}\n\n"
        f"URL Source: {source_url}\n\n"
        f"Markdown Content:\n\n{body}\n"
    )
    if len(markdown.encode()) > PAGE_MARKDOWN_MAX_BYTES:
        raise ExternalPageMarkdownError("page_too_large")
    try:
        validate_canonical_markdown(title, markdown)
    except ValueError as error:
        raise ExternalPageMarkdownError(str(error)) from error
    return markdown


def publish_paper_markdown(
    paper_id: str, markdown: str, *, bucket_id: str, token: str | None
) -> str:
    """Write the immutable revision, its alias, and the manifest in one batch."""
    raw = markdown.encode()
    content_sha256 = hashlib.sha256(raw).hexdigest()
    content_key = paper_markdown_content_key(content_sha256)
    manifest = {
        "schema_version": 1,
        "paper_key": f"external/{paper_id}",
        "source": "external",
        "content_sha256": content_sha256,
        "content_key": content_key,
        "size_bytes": len(raw),
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    alias_key = paper_markdown_bucket_key(paper_id, source="external")
    HfApi(token=token).batch_bucket_files(
        bucket_id,
        add=[
            (raw, content_key),
            (raw, alias_key),
            (manifest_bytes, paper_markdown_manifest_key(paper_id, source="external")),
        ],
        token=token,
    )
    HfFileSystem(token=token).invalidate_cache(f"hf://buckets/{bucket_id}/external")
    return content_sha256


def status_key(paper_id: str) -> str:
    return f"_jobs/web-status/external/{paper_id}.json"


def read_status(paper_id: str, *, bucket_id: str, token: str | None) -> dict:
    path = f"hf://buckets/{bucket_id}/{status_key(paper_id)}"
    try:
        with HfFileSystem(token=token).open(path, "rb", block_size=0) as handle:
            payload = json.loads(handle.read(64 * 1024))
    except (EntryNotFoundError, FileNotFoundError):
        return {}
    return payload if isinstance(payload, dict) else {}


def retry_due(status: dict, *, now: datetime | None = None) -> bool:
    """Whether a page with this status record may be scraped again."""
    if not status or status.get("status") == "succeeded":
        return True
    if not status.get("retryable"):
        return False
    retry_at = status.get("next_retry_at")
    return not retry_at or datetime.fromisoformat(retry_at) <= (
        now or datetime.now(UTC)
    )


def _write_status(
    paper_id: str,
    payload: dict,
    *,
    prior: dict,
    error: ExternalPageMarkdownError | None,
    bucket_id: str,
    token: str | None,
) -> None:
    now = datetime.now(UTC)
    prior_attempts = int(prior.get("attempt_count") or 0)
    # Our own storage outage says nothing about the page, so it never uses up
    # the page's attempts.
    counted = error is not None and error.code != "storage_unavailable"
    attempts = prior_attempts + 1 if counted else (prior_attempts if error else 0)
    retryable = bool(
        error and error.retryable and (not counted or attempts < MAX_ATTEMPTS)
    )
    record = {
        **payload,
        "paper_key": f"external/{paper_id}",
        "source": "external_page",
        "status": "failed" if error else "succeeded",
        "error_class": error.code if error else None,
        "attempt_count": attempts,
        "retryable": retryable,
        "attempted_at": now.isoformat(),
        "next_retry_at": (
            (now + timedelta(minutes=30 * 4 ** max(0, attempts - 1))).isoformat()
            if retryable
            else None
        ),
    }
    HfApi(token=token).batch_bucket_files(
        bucket_id,
        add=[
            (
                json.dumps(record, sort_keys=True, indent=2).encode(),
                status_key(paper_id),
            )
        ],
        token=token,
    )


def prepare_external_page_markdown(
    *,
    paper_id: str,
    title: str,
    page_url: str,
    api_key: str,
    bucket_id: str,
    token: str | None,
    timeout_seconds: float,
) -> str:
    """Scrape and publish one paper's page; return its content version.

    A failure is recorded with backoff so neither readers nor the hourly job
    pay for the same unreadable page again before it is due. Bucket errors
    surface as a retryable ``storage_unavailable``.
    """
    with _page_locks_guard:
        lock = _page_locks.setdefault(paper_id, threading.Lock())
    with lock:
        try:
            return _prepare(
                paper_id=paper_id,
                title=title,
                page_url=page_url,
                api_key=api_key,
                bucket_id=bucket_id,
                token=token,
                timeout_seconds=timeout_seconds,
            )
        except (HfHubHTTPError, OSError) as error:
            raise ExternalPageMarkdownError(
                "storage_unavailable", retryable=True
            ) from error


def _prepare(
    *,
    paper_id: str,
    title: str,
    page_url: str,
    api_key: str,
    bucket_id: str,
    token: str | None,
    timeout_seconds: float,
) -> str:
    prior = read_status(paper_id, bucket_id=bucket_id, token=token)
    if not retry_due(prior):
        # A page in backoff is not yet known to be unreadable.
        raise ExternalPageMarkdownError(
            str(prior.get("error_class") or "page_unreadable"),
            retryable=bool(prior.get("retryable")),
        )
    # A concurrent request may have published while this one waited.
    alias = paper_markdown_bucket_key(paper_id, source="external")
    if prior.get("status") == "succeeded" and HfFileSystem(token=token).exists(
        f"hf://buckets/{bucket_id}/{alias}"
    ):
        return str(prior["markdown_sha256"])
    # Check before the paid scrape; a held lock costs no credit.
    if HfFileSystem(token=token).exists(
        f"hf://buckets/{bucket_id}/{MARKDOWN_MIGRATION_LOCK_KEY}"
    ):
        raise ExternalPageMarkdownError("markdown_migration_locked", retryable=True)
    try:
        page = scrape_page(page_url, api_key=api_key, timeout_seconds=timeout_seconds)
        markdown = page_paper_markdown(title, page_url, page)
    except ExternalPageMarkdownError as error:
        if error.code != "firecrawl_not_configured":
            _write_status(
                paper_id,
                {"page_url": page_url},
                prior=prior,
                error=error,
                bucket_id=bucket_id,
                token=token,
            )
        raise
    try:
        content_sha256 = publish_paper_markdown(
            paper_id, markdown, bucket_id=bucket_id, token=token
        )
    except HfHubHTTPError as error:
        failure = ExternalPageMarkdownError("storage_unavailable", retryable=True)
        # Back off so a storage outage does not re-scrape on every read.
        _write_status(
            paper_id,
            {"page_url": page_url},
            prior=prior,
            error=failure,
            bucket_id=bucket_id,
            token=token,
        )
        raise failure from error
    _write_status(
        paper_id,
        {"page_url": page_url, "markdown_sha256": content_sha256},
        prior=prior,
        error=None,
        bucket_id=bucket_id,
        token=token,
    )
    return content_sha256
