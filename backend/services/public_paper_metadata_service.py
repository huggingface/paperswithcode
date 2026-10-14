"""Public metadata for papers that are not in the Papers With Code catalog.

Readers and agents ask about arXiv IDs and DOIs the catalog never imported.
This service answers from the catalog when it can and otherwise from Hugging
Face Papers, arXiv, or Crossref, marking the result ``in_catalog=false`` and
listing where the paper can be read. The lookup logic mirrors
``pwc_mcp.external`` in pwc-cli so the MCP can switch to this endpoint with
the same field shape.

Outbound calls are opt-in (only this endpoint makes them), short, size-capped,
cached per worker for an hour (hits and misses alike), and rate-limited so
crawler traffic cannot fan out to the upstream sources.
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
import urllib.parse
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.models.public_paper_metadata import PublicPaperLink, PublicPaperMetadata
from backend.services.paper_service import PaperService
from backend.utils.exceptions import PaperNotFoundError
from backend.utils.urls import (
    get_paper_route_identifier,
    normalize_paper_route_identifier,
    validate_arxiv_id,
)

logger = logging.getLogger(__name__)

PRODUCTION_ORIGIN = "https://paperswithcode.co"
ARXIV_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})", re.IGNORECASE)
ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)
ARXIV_DOI = re.compile(r"10\.48550/arxiv\.(.+)", re.IGNORECASE)
DOI = re.compile(r"10\.\d{4,9}/\S+")
GITHUB_REPO = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+", re.IGNORECASE)
ATOM = "{http://www.w3.org/2005/Atom}"

MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 3600
FAILURE_CACHE_TTL_SECONDS = 60
CACHE_MAX_ENTRIES = 4096
RATE_WINDOW_SECONDS = 60
CLIENT_LOOKUPS_PER_WINDOW = 20
WORKER_LOOKUPS_PER_WINDOW = 120
MAX_CLIENT_BUCKETS = 4096
USER_AGENT = "paperswithcode-public-metadata/1.0 (+https://paperswithcode.co)"


class PublicMetadataError(Exception):
    status_code = 500
    code = "public_metadata_error"

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class InvalidPaperIdentifierError(PublicMetadataError):
    status_code = 400
    code = "invalid_paper_identifier"


class PublicPaperNotFoundError(PublicMetadataError):
    status_code = 404
    code = "paper_not_found"


class PublicMetadataRateLimitedError(PublicMetadataError):
    status_code = 429
    code = "public_metadata_rate_limited"


class PublicMetadataUnavailableError(PublicMetadataError):
    status_code = 503
    code = "public_metadata_unavailable"


@dataclass(frozen=True)
class PaperReference:
    kind: str  # "arxiv", "doi", or "catalog_id"
    value: str


def parse_reference(identifier: str) -> PaperReference | None:
    """Classify an arXiv ID/URL/DOI, a DOI, or a numeric catalog ID."""
    candidate = identifier.strip()
    # Proxies merge the double slash of a URL embedded in a path segment.
    candidate = re.sub(r"^(https?):/+", r"\1://", candidate, flags=re.IGNORECASE)
    arxiv_id = arxiv_reference(candidate)
    if arxiv_id:
        return PaperReference("arxiv", arxiv_id)
    doi = doi_reference(candidate)
    if doi:
        return PaperReference("doi", doi)
    if candidate.isdigit():
        return PaperReference("catalog_id", candidate)
    return None


def arxiv_reference(reference: str) -> str | None:
    """Return the arXiv ID named by an ID, arXiv/HF URL, or arXiv DOI."""
    candidate = reference.strip()
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.casefold().removeprefix("www.")
        parts = [part for part in parsed.path.split("/") if part]
        if host in {"arxiv.org", "export.arxiv.org"} and len(parts) >= 2:
            if parts[0] not in {"abs", "pdf", "html"}:
                return None
            candidate = "/".join(parts[1:]).removesuffix(".pdf")
        elif host == "huggingface.co" and len(parts) >= 2 and parts[0] == "papers":
            candidate = parts[1]
        elif host in {"doi.org", "dx.doi.org"}:
            candidate = urllib.parse.unquote(parsed.path.lstrip("/"))
        else:
            return None
    match = ARXIV_DOI.fullmatch(candidate)
    if match:
        candidate = match.group(1)
    candidate = normalize_paper_route_identifier(candidate.removeprefix("arXiv:"))
    candidate = ARXIV_VERSION.sub("", candidate)
    return candidate if ARXIV_ID.fullmatch(candidate) else None


def doi_reference(reference: str) -> str | None:
    candidate = reference.strip()
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme in {"http", "https"}:
        if parsed.netloc.casefold().removeprefix("www.") not in {
            "doi.org",
            "dx.doi.org",
        }:
            return None
        candidate = urllib.parse.unquote(parsed.path.lstrip("/"))
    candidate = candidate.removeprefix("doi:").strip()
    return candidate if DOI.fullmatch(candidate) else None


class _SlidingWindowLimiter:
    """Per-client and per-worker budgets for uncached upstream lookups."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: OrderedDict[str, deque[float]] = OrderedDict()
        self._worker: deque[float] = deque()

    def acquire(self, client: str) -> int | None:
        """Record a lookup, or return seconds to wait when over budget."""
        now = time.monotonic()
        cutoff = now - RATE_WINDOW_SECONDS
        with self._lock:
            recent = self._clients.pop(client, None) or deque()
            self._clients[client] = recent
            if len(self._clients) > MAX_CLIENT_BUCKETS:
                self._clients.popitem(last=False)
            for window in (recent, self._worker):
                while window and window[0] <= cutoff:
                    window.popleft()
            for window, limit in (
                (recent, CLIENT_LOOKUPS_PER_WINDOW),
                (self._worker, WORKER_LOOKUPS_PER_WINDOW),
            ):
                if len(window) >= limit:
                    return max(1, int(window[0] - cutoff) + 1)
            recent.append(now)
            self._worker.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._clients.clear()
            self._worker.clear()


_UNAVAILABLE = object()


class _LookupCache:
    """Bounded per-worker TTL cache of upstream results, misses included."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            if entry[0] <= time.monotonic():
                del self._entries[key]
                return False, None
            return True, entry[1]

    def put(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = (time.monotonic() + ttl, value)
            while len(self._entries) > CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_cache = _LookupCache()
_limiter = _SlidingWindowLimiter()


def _new_client() -> httpx.Client:
    return httpx.Client()


def reset_public_metadata_state() -> None:
    """Clear the per-worker cache and rate limits (tests)."""
    _cache.clear()
    _limiter.reset()


class PublicPaperSources:
    """Fetch metadata from Hugging Face Papers, arXiv, and Crossref.

    A source answering 404/410 is a definitive miss; any other failure marks
    the lookup ``failed`` so the caller can report unavailability instead of
    claiming the paper does not exist.
    """

    def __init__(self, client: httpx.Client):
        self._client = client
        self.failed = False

    def _get(self, url: str) -> bytes | None:
        try:
            with self._client.stream(
                "GET",
                url,
                headers={
                    "Accept": "application/json, application/atom+xml, text/html;q=0.9",
                    "User-Agent": USER_AGENT,
                },
                timeout=TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as response:
                if response.status_code in {404, 410}:
                    return None
                if response.status_code != 200:
                    self.failed = True
                    logger.info(
                        "Public paper metadata source returned status=%s",
                        response.status_code,
                    )
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_RESPONSE_BYTES:
                        break
                return bytes(body[:MAX_RESPONSE_BYTES])
        except httpx.HTTPError as error:
            self.failed = True
            logger.info(
                "Public paper metadata lookup failed type=%s", type(error).__name__
            )
            return None

    def _json(self, url: str) -> Any:
        body = self._get(url)
        if body is None:
            return None
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.failed = True
            return None

    def by_arxiv_id(self, arxiv_id: str) -> dict[str, Any] | None:
        quoted = urllib.parse.quote(arxiv_id, safe="./")
        paper = self._json(f"https://huggingface.co/api/papers/{quoted}")
        if isinstance(paper, dict) and paper.get("title"):
            return _from_hf(paper)
        # arXiv is authoritative for arXiv IDs, so a Hugging Face failure
        # alone does not make the lookup unavailable.
        self.failed = False
        body = self._get(f"https://arxiv.org/abs/{quoted}")
        if body is not None:
            record = _from_arxiv_abs(arxiv_id, body)
            self.failed = record is None
            if record is not None:
                return record
        elif not self.failed:
            return None
        # The abstract page failed transiently; the export API may still answer.
        query = urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
        body = self._get(f"https://export.arxiv.org/api/query?{query}")
        entries = [
            entry
            for entry in (_arxiv_entries(body) if body else [])
            if entry["arxiv_id"] == arxiv_id
        ]
        if entries:
            return entries[0]
        self.failed = True
        return None

    def by_doi(self, doi: str) -> dict[str, Any] | None:
        payload = self._json(
            f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}"
        )
        work = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(work, dict) or not work.get("title"):
            return None
        titles = work.get("title")
        title = titles[0] if isinstance(titles, list) and titles else str(titles)
        parts = (work.get("issued") or {}).get("date-parts") or [[]]
        published = "-".join(f"{int(value):02d}" for value in parts[0] or []) or None
        abstract = re.sub(r"<[^>]+>", " ", str(work.get("abstract") or ""))
        abstract = " ".join(abstract.split()).removeprefix("Abstract ").strip()
        return {
            "id": doi,
            "arxiv_id": None,
            "doi": doi,
            "title": " ".join(str(title).split()),
            "authors": [
                " ".join(filter(None, (author.get("given"), author.get("family"))))
                for author in work.get("author") or []
                if isinstance(author, dict)
            ],
            "abstract": abstract or None,
            "published": published,
            "url": str(work.get("URL") or f"https://doi.org/{doi}"),
            "pdf_url": None,
            "hf_url": None,
            "repositories": [],
            "project_pages": [],
            "metadata_source": "crossref",
        }


def _from_hf(paper: dict[str, Any]) -> dict[str, Any]:
    arxiv_id = str(paper.get("id") or "")
    repositories = [
        str(url)
        for url in (paper.get("githubRepo"),)
        if isinstance(url, str) and GITHUB_REPO.match(url)
    ]
    project_page = paper.get("projectPage")
    return {
        "id": arxiv_id,
        "arxiv_id": arxiv_id,
        "doi": None,
        "title": " ".join(str(paper.get("title") or "").split()),
        "authors": [
            str(author.get("name"))
            for author in paper.get("authors") or []
            if isinstance(author, dict) and author.get("name")
        ],
        "abstract": " ".join(str(paper.get("summary") or "").split()) or None,
        "published": str(paper.get("publishedAt") or "")[:10] or None,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "hf_url": f"https://huggingface.co/papers/{arxiv_id}",
        "repositories": repositories,
        "project_pages": [project_page] if isinstance(project_page, str) else [],
        "metadata_source": "huggingface",
    }


def _from_arxiv_abs(arxiv_id: str, body: bytes) -> dict[str, Any] | None:
    text = body.decode("utf-8", errors="replace")
    meta: dict[str, list[str]] = {}
    for name, value in re.findall(
        r'<meta\s+name="citation_([a-z_]+)"\s+content="([^"]*)"', text
    ):
        meta.setdefault(name, []).append(html.unescape(value).strip())
    title = (meta.get("title") or [""])[0]
    if not title:
        return None
    published = (meta.get("date") or [""])[0].replace("/", "-") or None
    abstract = " ".join((meta.get("abstract") or [""])[0].split()) or None
    return {
        "id": arxiv_id,
        "arxiv_id": arxiv_id,
        "doi": (meta.get("doi") or [None])[0],
        "title": " ".join(title.split()),
        "authors": [_author_name(value) for value in meta.get("author", [])],
        "abstract": abstract,
        "published": published,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "hf_url": None,
        "repositories": _github_repos(abstract or ""),
        "project_pages": [],
        "metadata_source": "arxiv",
    }


def _arxiv_entries(body: bytes) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    entries = []
    for entry in root.iter(f"{ATOM}entry"):
        identifier = (entry.findtext(f"{ATOM}id") or "").rsplit("/abs/", 1)[-1]
        arxiv_id = ARXIV_VERSION.sub("", identifier.strip())
        if not ARXIV_ID.fullmatch(arxiv_id):
            continue
        abstract = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
        entries.append(
            {
                "id": arxiv_id,
                "arxiv_id": arxiv_id,
                "doi": entry.findtext("{http://arxiv.org/schemas/atom}doi"),
                "title": " ".join((entry.findtext(f"{ATOM}title") or "").split()),
                "authors": [
                    " ".join((author.findtext(f"{ATOM}name") or "").split())
                    for author in entry.iter(f"{ATOM}author")
                ],
                "abstract": abstract or None,
                "published": (entry.findtext(f"{ATOM}published") or "")[:10] or None,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "hf_url": None,
                "repositories": _github_repos(abstract),
                "project_pages": [],
                "metadata_source": "arxiv",
            }
        )
    return entries


def _github_repos(text: str) -> list[str]:
    """GitHub repository URLs in prose, without sentence punctuation or .git."""
    return sorted(
        {url.rstrip(".").removesuffix(".git") for url in GITHUB_REPO.findall(text)}
    )


def _author_name(value: str) -> str:
    """arXiv citation meta lists "Family, Given"; show "Given Family"."""
    family, _, given = value.partition(",")
    return f"{given.strip()} {family.strip()}".strip() if given else value.strip()


def available_at(record: dict[str, Any]) -> list[PublicPaperLink]:
    """Labelled links where the paper can be read, most direct first."""
    links: list[PublicPaperLink] = []
    seen: set[str] = set()

    def add(label: str, url: str | None, kind: str) -> None:
        if url and url not in seen:
            seen.add(url)
            links.append(PublicPaperLink(label=label, url=url, kind=kind))

    add("Papers With Code", record.get("catalog_url"), "catalog")
    if record.get("arxiv_id"):
        add("arXiv abstract", record.get("url"), "abstract")
        add("arXiv PDF", record.get("pdf_url"), "pdf")
    else:
        add("Publisher page", record.get("url"), "abstract")
        add("PDF", record.get("pdf_url"), "pdf")
    add("Hugging Face Papers", record.get("hf_url"), "huggingface")
    doi = record.get("doi")
    if doi:
        add("DOI", f"https://doi.org/{doi}", "doi")
    for repository in record.get("repositories") or []:
        add("Code", repository, "code")
    for page in record.get("project_pages") or []:
        add("Project page", page, "project_page")
    return links


SOURCE_LABELS = {
    "huggingface": "Hugging Face Papers",
    "arxiv": "arXiv",
    "crossref": "Crossref",
}


class PublicPaperMetadataService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, identifier: str, client_ip: str | None) -> PublicPaperMetadata:
        reference = parse_reference(identifier)
        if reference is None:
            raise InvalidPaperIdentifierError(
                "Use an arXiv ID (optionally versioned), an arXiv or Hugging Face "
                "paper URL, a DOI, or a Papers With Code paper ID."
            )
        catalog_paper = self._catalog_paper(reference)
        if catalog_paper is not None:
            return _catalog_metadata(catalog_paper)
        if reference.kind == "catalog_id":
            raise PublicPaperNotFoundError(
                f"No Papers With Code paper has ID {reference.value}."
            )
        return self._public_metadata(reference, client_ip or "unknown")

    def _catalog_paper(self, reference: PaperReference) -> Paper | None:
        if reference.kind == "doi" or (
            reference.kind == "arxiv" and not validate_arxiv_id(reference.value)
        ):
            return None
        try:
            return PaperService(self.db).get_paper_by_id_or_arxiv(reference.value)
        except PaperNotFoundError:
            return None

    def _public_metadata(
        self, reference: PaperReference, client_ip: str
    ) -> PublicPaperMetadata:
        key = f"{reference.kind}:{reference.value.casefold()}"
        hit, record = _cache.get(key)
        if not hit:
            retry_after = _limiter.acquire(client_ip)
            if retry_after is not None:
                raise PublicMetadataRateLimitedError(
                    "Too many uncached public metadata lookups. Try again shortly.",
                    retry_after=retry_after,
                )
            record = self._fetch(reference)
            ttl = (
                FAILURE_CACHE_TTL_SECONDS
                if record is _UNAVAILABLE
                else CACHE_TTL_SECONDS
            )
            _cache.put(key, record, ttl)
        if record is _UNAVAILABLE:
            raise PublicMetadataUnavailableError(
                "Public paper metadata sources are unavailable right now. "
                "Try again in a minute.",
                retry_after=FAILURE_CACHE_TTL_SECONDS,
            )
        if record is None:
            raise PublicPaperNotFoundError(
                f"{reference.value} is not in the Papers With Code catalog, and "
                "Hugging Face Papers, arXiv, and Crossref do not know it either."
            )
        source = SOURCE_LABELS[record["metadata_source"]]
        return PublicPaperMetadata(
            in_catalog=False,
            note=(
                "Not indexed by Papers With Code; metadata comes from "
                f"{source}. Read it at the links in available_at."
            ),
            available_at=available_at(record),
            **record,
        )

    @staticmethod
    def _fetch(reference: PaperReference) -> Any:
        with _new_client() as client:
            return PublicPaperMetadataService._fetch_with(client, reference)

    @staticmethod
    def _fetch_with(client: httpx.Client, reference: PaperReference) -> Any:
        sources = PublicPaperSources(client)
        if reference.kind == "arxiv":
            record = sources.by_arxiv_id(reference.value)
        else:
            record = sources.by_doi(reference.value)
        if record is None and sources.failed:
            return _UNAVAILABLE
        return record


def _catalog_metadata(paper: Paper) -> PublicPaperMetadata:
    route = get_paper_route_identifier(paper.source, paper.arxiv_id, int(paper.id))
    record = {
        "id": str(paper.id),
        "arxiv_id": paper.arxiv_id,
        "doi": None,
        "title": paper.title,
        "authors": list(paper.authors or []),
        "abstract": paper.abstract,
        "published": paper.published.isoformat() if paper.published else None,
        "url": paper.url_abs,
        "pdf_url": paper.url_pdf,
        "hf_url": (
            f"https://huggingface.co/papers/{paper.arxiv_id}"
            if paper.arxiv_id
            else None
        ),
        "repositories": [],
        "project_pages": [],
        "metadata_source": "paperswithcode",
        "catalog_url": f"{PRODUCTION_ORIGIN}/paper/{route}",
    }
    return PublicPaperMetadata(
        in_catalog=True,
        catalog_id=str(paper.id),
        note=(
            "Indexed by Papers With Code; GET /api/v1/papers/"
            f"{route} returns the full catalog record."
        ),
        available_at=available_at(record),
        **record,
    )
