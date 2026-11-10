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
import socket
import threading
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

import httpx
from huggingface_hub import HfApi
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

from backend.scripts.generate_missing_paper_markdown import (
    MARKDOWN_MIGRATION_LOCK_KEY,
    TITLE_STOP_WORDS,
    validate_canonical_markdown,
)
from backend.services.hf_bucket_filesystem import BucketFileSystem
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

# Whether the reader can show a page itself in a frame is checked from its
# response headers. Framing rarely changes; an unreachable page is checked
# again sooner.
FRAME_CHECK_TIMEOUT_SECONDS = 10
FRAME_CHECK_MAX_REDIRECTS = 5
FRAME_CHECK_MAX_AGE = timedelta(days=7)
FRAME_CHECK_RETRY_AGE = timedelta(days=1)
FRAME_CHECK_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
# frame-ancestors sources that admit the reader at https://paperswithcode.co.
FRAMING_SOURCES = frozenset(
    {"*", "https:", "paperswithcode.co", "https://paperswithcode.co"}
)

_page_locks: dict[str, threading.Lock] = {}
_page_locks_guard = threading.Lock()


def _page_lock(paper_id: str) -> threading.Lock:
    with _page_locks_guard:
        return _page_locks.setdefault(paper_id, threading.Lock())


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
    return content_sha256


def status_key(paper_id: str) -> str:
    return f"_jobs/web-status/external/{paper_id}.json"


def read_status(paper_id: str, *, bucket_id: str, token: str | None) -> dict:
    path = f"hf://buckets/{bucket_id}/{status_key(paper_id)}"
    try:
        with BucketFileSystem(token=token).open(path, "rb", block_size=0) as handle:
            payload = json.loads(handle.read(64 * 1024))
    except (EntryNotFoundError, FileNotFoundError):
        return {}
    return payload if isinstance(payload, dict) else {}


def web_markdown_ready(paper, *, bucket_id: str, token: str | None) -> bool:
    """Whether the page's Markdown exists for curation to read."""
    path = f"hf://buckets/{bucket_id}/{paper_markdown_bucket_key(str(paper.id), source='external')}"
    try:
        return BucketFileSystem(token=token).exists(path)
    except (HfHubHTTPError, OSError):
        return False


def web_markdown_pending(paper, *, bucket_id: str, token: str | None) -> bool:
    """Whether a readable page still awaits its Markdown.

    Pages that are ineligible, already published, or permanently unreadable
    are not pending, so curation never waits on them.
    """
    page_url = external_page_url(
        source=paper.source,
        source_url=paper.source_url,
        conference_url_pdf=paper.conference_url_pdf,
    )
    if page_url is None or web_markdown_ready(paper, bucket_id=bucket_id, token=token):
        return False
    try:
        status = read_status(str(paper.id), bucket_id=bucket_id, token=token)
    except (HfHubHTTPError, OSError, ValueError):
        # A storage outage says nothing about the page; keep waiting.
        return True
    return status.get("status") != "failed" or bool(status.get("retryable"))


def retry_due(status: dict, *, now: datetime | None = None) -> bool:
    """Whether a page with this status record may be scraped again."""
    # A record holding only a framing check has no scrape attempt yet.
    if status.get("status") in {None, "succeeded"}:
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
        **({"framing": prior["framing"]} if "framing" in prior else {}),
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
    with _page_lock(paper_id):
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
    if prior.get("status") == "succeeded" and BucketFileSystem(token=token).exists(
        f"hf://buckets/{bucket_id}/{alias}"
    ):
        return str(prior["markdown_sha256"])
    # Check before the paid scrape; a held lock costs no credit.
    if BucketFileSystem(token=token).exists(
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


def _public_host(hostname: str) -> bool | None:
    """Whether every address the host resolves to is publicly routable.

    ``None`` means the name did not resolve, which may be transient.
    """
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return None
    return bool(infos) and all(
        ipaddress.ip_address(str(info[4][0]).split("%", 1)[0]).is_global
        for info in infos
    )


def _frame_blocker(headers: httpx.Headers) -> str | None:
    """Name the response header that forbids framing, if any.

    Browsers ignore X-Frame-Options when a CSP frame-ancestors directive is
    present, so that directive decides first.
    """
    ancestors = [
        sources.lower().split()
        for policy in headers.get_list("content-security-policy", split_commas=True)
        for directive in policy.split(";")
        for name, _, sources in [directive.strip().partition(" ")]
        if name.lower() == "frame-ancestors"
    ]
    if ancestors:
        allowed = all(
            {source.rstrip("/") for source in sources} & FRAMING_SOURCES
            for sources in ancestors
        )
        return None if allowed else "frame_ancestors"
    return "x_frame_options" if headers.get_list("x-frame-options") else None


def check_page_framing(
    url: str, *, timeout_seconds: float = FRAME_CHECK_TIMEOUT_SECONDS
) -> tuple[bool, str]:
    """Whether the reader can show ``url`` in a frame, and the reason.

    Redirects are followed by hand so every hop must be HTTPS (the reader's
    frame cannot load mixed content) on a publicly routable address. Only
    response headers are read, and only the verdict is kept.
    """
    with httpx.Client(
        timeout=timeout_seconds, headers={"User-Agent": FRAME_CHECK_USER_AGENT}
    ) as client:
        for _ in range(FRAME_CHECK_MAX_REDIRECTS + 1):
            try:
                parsed = urlsplit(url)
                hostname = parsed.hostname
            except ValueError:
                return False, "invalid_url"
            if parsed.scheme != "https" or not hostname:
                return False, "insecure"
            public = _public_host(hostname)
            if public is None:
                return False, "unreachable"
            if not public:
                return False, "private_address"
            try:
                with client.stream("GET", url) as response:
                    if response.has_redirect_location:
                        url = urljoin(url, response.headers["location"])
                        continue
                    if not response.is_success:
                        return False, "http_status"
                    content_type = response.headers.get("content-type", "")
                    if not content_type.lower().startswith("text/html"):
                        return False, "not_html"
                    blocker = _frame_blocker(response.headers)
                    return blocker is None, blocker or "allowed"
            except httpx.InvalidURL:
                return False, "invalid_url"
            except httpx.HTTPError:
                return False, "unreachable"
    return False, "too_many_redirects"


def framing_due(status: dict, page_url: str, *, now: datetime | None = None) -> bool:
    """Whether a page's framing check is missing, for another URL, or stale."""
    framing = status.get("framing")
    if not isinstance(framing, dict) or framing.get("page_url") != page_url:
        return True
    max_age = (
        FRAME_CHECK_RETRY_AGE
        if framing.get("reason") == "unreachable"
        else FRAME_CHECK_MAX_AGE
    )
    checked_at = framing.get("checked_at")
    if not isinstance(checked_at, str):
        return True
    return datetime.fromisoformat(checked_at) + max_age <= (now or datetime.now(UTC))


def page_frameable(status: dict, page_url: str) -> bool:
    """Whether the last framing check let the reader frame this exact URL."""
    framing = status.get("framing")
    return (
        isinstance(framing, dict)
        and framing.get("page_url") == page_url
        and framing.get("frameable") is True
    )


def record_page_framing(
    paper_id: str, page_url: str, *, bucket_id: str, token: str | None
) -> bool:
    """Check a page's framing and store the verdict in its status record."""
    frameable, reason = check_page_framing(page_url)
    with _page_lock(paper_id):
        status = read_status(paper_id, bucket_id=bucket_id, token=token)
        status["framing"] = {
            "page_url": page_url,
            "frameable": frameable,
            "reason": reason,
            "checked_at": datetime.now(UTC).isoformat(),
        }
        HfApi(token=token).batch_bucket_files(
            bucket_id,
            add=[
                (
                    json.dumps(status, sort_keys=True, indent=2).encode(),
                    status_key(paper_id),
                )
            ],
            token=token,
        )
    return frameable
