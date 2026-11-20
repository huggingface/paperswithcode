#!/usr/bin/env python3
"""Tag local papers with a method when they cite that method's source paper.

For every method that has ``methods.source_paper_id`` set, this script asks
Semantic Scholar for the list of citing papers (``GET /paper/{id}/citations``)
and inserts a ``paper_methods`` row for any citing paper that we already have in
our database.

Dry run (default):
    uv run --env-file backend/keys.env python \
        backend/database/methods_setup/link_papers_by_source_citations.py

Write:
    uv run --env-file backend/keys.env python \
        backend/database/methods_setup/link_papers_by_source_citations.py --write

Single method:
    uv run --env-file backend/keys.env python \
        backend/database/methods_setup/link_papers_by_source_citations.py \
        --method-slug transformer
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Method, Paper

SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"
CITATIONS_FIELDS = "citingPaper.paperId,citingPaper.externalIds,citingPaper.title"
REFERENCES_FIELDS = "citedPaper.paperId,citedPaper.externalIds,citedPaper.title"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_REQUEST_DELAY = 1.5
DEFAULT_BATCH_SIZE = 500
DEFAULT_SAMPLE_UNMATCHED = 5
DEFAULT_MAX_RETRIES = 5
SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP = 9999

ARXIV_VERSION_RE = re.compile(r"v\d+$")


@dataclass
class CitingPaper:
    """A citing paper as returned by Semantic Scholar."""

    semantic_scholar_id: Optional[str]
    arxiv_id: Optional[str]
    title: Optional[str]


@dataclass
class CitedPaper:
    """A reference (paper cited by another) as returned by Semantic Scholar."""

    semantic_scholar_id: Optional[str]
    arxiv_id: Optional[str]
    title: Optional[str]


@dataclass
class MethodResult:
    method_id: int
    method_name: str
    method_slug: Optional[str]
    source_paper_id: int
    semantic_scholar_id: Optional[str] = None
    citations_fetched: int = 0
    matched_papers: int = 0
    new_links: int = 0
    skipped_reason: Optional[str] = None
    sample_unmatched: list[CitingPaper] = field(default_factory=list)


@dataclass
class JobStats:
    methods_processed: int = 0
    methods_skipped: int = 0
    api_calls: int = 0
    rate_limit_hits: int = 0
    api_errors: int = 0
    total_citations_fetched: int = 0
    total_matched_papers: int = 0
    total_new_links: int = 0
    method_results: list[MethodResult] = field(default_factory=list)


def normalize_arxiv_id(arxiv_id: Optional[str]) -> Optional[str]:
    """Strip whitespace and any ``vN`` suffix from an arXiv identifier."""
    if not arxiv_id:
        return None
    cleaned = arxiv_id.strip()
    if not cleaned:
        return None
    return ARXIV_VERSION_RE.sub("", cleaned)


class SemanticScholarClient:
    """Tiny synchronous Semantic Scholar wrapper with throttling and retries."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        request_timeout: float = 30.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        exponential_backoff: bool = False,
        client: Optional[httpx.Client] = None,
        sleep=time.sleep,
    ):
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.exponential_backoff = exponential_backoff
        self._sleep = sleep
        self._owns_client = client is None
        if client is None:
            headers = {"x-api-key": api_key} if api_key else {}
            client = httpx.Client(timeout=request_timeout, headers=headers)
        self._client = client

        self.api_calls = 0
        self.rate_limit_hits = 0
        self.api_errors = 0
        self.retry_attempts = 0
        self.failed_requests = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        for attempt in range(self.max_retries):
            self.api_calls += 1
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                self.api_errors += 1
                print(f"  ! HTTP error: {exc}", file=sys.stderr)
                if attempt + 1 < self.max_retries:
                    self.retry_attempts += 1
                    multiplier = 2**attempt if self.exponential_backoff else attempt + 1
                    self._sleep(self.request_delay * multiplier)
                continue

            status = resp.status_code
            if status == 200:
                self._sleep(self.request_delay)
                return resp.json()
            if status == 404:
                self._sleep(self.request_delay)
                return None
            if status == 429:
                self.rate_limit_hits += 1
                if attempt + 1 < self.max_retries:
                    self.retry_attempts += 1
                    wait = self.request_delay * (
                        2 ** (attempt + 1) if self.exponential_backoff else attempt + 2
                    )
                    print(
                        f"  ! 429 rate limited; sleeping {wait:.1f}s before retry",
                        file=sys.stderr,
                    )
                    self._sleep(wait)
                continue
            if 500 <= status < 600:
                self.api_errors += 1
                if attempt + 1 < self.max_retries:
                    self.retry_attempts += 1
                    wait = self.request_delay * (
                        2**attempt if self.exponential_backoff else attempt + 1
                    )
                    print(
                        f"  ! {status} server error; sleeping {wait:.1f}s before retry",
                        file=sys.stderr,
                    )
                    self._sleep(wait)
                continue

            self.api_errors += 1
            self.failed_requests += 1
            print(
                f"  ! Unexpected status {status} for {url}: {resp.text[:200]}",
                file=sys.stderr,
            )
            return None

        print(f"  ! Giving up after {self.max_retries} retries: {url}", file=sys.stderr)
        self.failed_requests += 1
        return None

    def lookup_paper_by_arxiv(self, arxiv_id: str) -> Optional[dict]:
        return self._request(
            f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/arXiv:{arxiv_id}",
            params={"fields": "paperId,title"},
        )

    def iter_citations(
        self,
        paper_id: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_citations: Optional[int] = None,
    ) -> Iterator[CitingPaper]:
        offset = 0
        fetched = 0
        while True:
            if offset >= SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP:
                return
            limit = page_size
            if max_citations is not None:
                remaining = max_citations - fetched
                if remaining <= 0:
                    return
                limit = min(page_size, remaining)
            limit = min(limit, SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP - offset)
            if limit <= 0:
                return

            data = self._request(
                f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/{paper_id}/citations",
                params={"fields": CITATIONS_FIELDS, "offset": offset, "limit": limit},
            )
            if data is None:
                return

            entries = data.get("data") or []
            for entry in entries:
                citing = entry.get("citingPaper") or {}
                external_ids = citing.get("externalIds") or {}
                yield CitingPaper(
                    semantic_scholar_id=citing.get("paperId"),
                    arxiv_id=normalize_arxiv_id(external_ids.get("ArXiv")),
                    title=citing.get("title"),
                )
                fetched += 1
                if max_citations is not None and fetched >= max_citations:
                    return

            next_offset = data.get("next")
            if not entries or next_offset is None:
                return
            offset = next_offset

    def iter_references(
        self,
        paper_id: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_references: Optional[int] = None,
    ) -> Iterator[CitedPaper]:
        """Yield papers cited by ``paper_id`` (i.e. its bibliography)."""

        offset = 0
        fetched = 0
        while True:
            if offset >= SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP:
                return
            limit = page_size
            if max_references is not None:
                remaining = max_references - fetched
                if remaining <= 0:
                    return
                limit = min(page_size, remaining)
            limit = min(limit, SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP - offset)
            if limit <= 0:
                return

            data = self._request(
                f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/{paper_id}/references",
                params={"fields": REFERENCES_FIELDS, "offset": offset, "limit": limit},
            )
            if data is None:
                return

            entries = data.get("data") or []
            for entry in entries:
                cited = entry.get("citedPaper") or {}
                external_ids = cited.get("externalIds") or {}
                yield CitedPaper(
                    semantic_scholar_id=cited.get("paperId"),
                    arxiv_id=normalize_arxiv_id(external_ids.get("ArXiv")),
                    title=cited.get("title"),
                )
                fetched += 1
                if max_references is not None and fetched >= max_references:
                    return

            next_offset = data.get("next")
            if not entries or next_offset is None:
                return
            offset = next_offset


def select_methods(
    db: Session,
    *,
    method_id: Optional[int] = None,
    method_slug: Optional[str] = None,
    method_name: Optional[str] = None,
    limit_methods: Optional[int] = None,
) -> list[Method]:
    query = db.query(Method).filter(Method.source_paper_id.isnot(None))
    if method_id is not None:
        query = query.filter(Method.id == method_id)
    if method_slug:
        query = query.filter(Method.slug == method_slug.lower())
    if method_name:
        query = query.filter(Method.name == method_name)
    query = query.order_by(Method.id)
    if limit_methods is not None:
        query = query.limit(limit_methods)
    return query.all()


def build_local_paper_index(
    db: Session,
) -> tuple[dict[str, int], dict[str, int]]:
    """Map ``semantic_scholar_id`` and ``arxiv_id`` to local ``paper.id`` for latest versions."""
    rows = db.execute(
        text("""
            SELECT id, arxiv_id, semantic_scholar_id
            FROM papers
            WHERE is_latest_version
            """)
    ).all()
    by_ss: dict[str, int] = {}
    by_arxiv: dict[str, int] = {}
    for row in rows:
        if row.semantic_scholar_id:
            by_ss[row.semantic_scholar_id] = row.id
        if row.arxiv_id:
            by_arxiv[row.arxiv_id] = row.id
    return by_ss, by_arxiv


def existing_paper_ids_for_method(db: Session, method_id: int) -> set[int]:
    rows = db.execute(
        text("SELECT paper_id FROM paper_methods WHERE method_id = :method_id"),
        {"method_id": method_id},
    ).all()
    return {row[0] for row in rows}


def _flush_batch(db: Session, batch: Iterable[dict]) -> None:
    from backend.services.paper_method_link_service import upsert_evidence_links

    upsert_evidence_links(db, list(batch), evidence_type="reference")
    db.commit()


def ensure_source_paper_ss_id(
    db: Session,
    paper: Paper,
    client: SemanticScholarClient,
    write: bool,
) -> Optional[str]:
    if paper.semantic_scholar_id:
        return paper.semantic_scholar_id
    if not paper.arxiv_id:
        return None
    data = client.lookup_paper_by_arxiv(paper.arxiv_id)
    if not data:
        return None
    ss_id = data.get("paperId")
    if not ss_id:
        return None
    if write:
        paper.semantic_scholar_id = ss_id
        db.commit()
    return ss_id


def link_papers_by_source_citations(
    db: Session,
    client: SemanticScholarClient,
    *,
    write: bool,
    method_id: Optional[int] = None,
    method_slug: Optional[str] = None,
    method_name: Optional[str] = None,
    limit_methods: Optional[int] = None,
    max_citations_per_method: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    page_size: int = DEFAULT_PAGE_SIZE,
    sample_unmatched_size: int = DEFAULT_SAMPLE_UNMATCHED,
    log=print,
) -> JobStats:
    """Tag local papers that cite each method's canonical source paper."""

    stats = JobStats()
    methods = select_methods(
        db,
        method_id=method_id,
        method_slug=method_slug,
        method_name=method_name,
        limit_methods=limit_methods,
    )
    log(f"Eligible methods (with source_paper_id): {len(methods)}")
    if not methods:
        return stats

    log("Building local paper index...")
    by_ss, by_arxiv = build_local_paper_index(db)
    log(f"  papers indexed by semantic_scholar_id: {len(by_ss):,}")
    log(f"  papers indexed by arxiv_id:            {len(by_arxiv):,}")

    for idx, method in enumerate(methods, start=1):
        log(
            f"\n[{idx}/{len(methods)}] {method.name} (id={method.id}, slug={method.slug})"
        )
        result = MethodResult(
            method_id=method.id,
            method_name=method.name,
            method_slug=method.slug,
            source_paper_id=method.source_paper_id,
        )

        source_paper = db.get(Paper, method.source_paper_id)
        if source_paper is None:
            result.skipped_reason = "source paper missing from DB"
            log(f"  ! {result.skipped_reason}; skipping")
            stats.methods_skipped += 1
            stats.method_results.append(result)
            continue

        ss_id = ensure_source_paper_ss_id(db, source_paper, client, write)
        if not ss_id:
            result.skipped_reason = "no semantic_scholar_id"
            log(
                f"  ! could not resolve Semantic Scholar ID for source paper "
                f"arxiv_id={source_paper.arxiv_id}; skipping"
            )
            stats.methods_skipped += 1
            stats.method_results.append(result)
            continue
        result.semantic_scholar_id = ss_id

        log(
            f"  source paper id={source_paper.id}, arxiv={source_paper.arxiv_id}, "
            f"ss_id={ss_id}"
        )

        existing_paper_ids = existing_paper_ids_for_method(db, method.id)
        log(
            f"  existing paper_methods rows for this method: "
            f"{len(existing_paper_ids):,}"
        )

        pending_batch: list[dict] = []
        seen_local_paper_ids: set[int] = set()

        for citing in client.iter_citations(
            ss_id,
            page_size=page_size,
            max_citations=max_citations_per_method,
        ):
            result.citations_fetched += 1
            local_paper_id: Optional[int] = None
            if citing.semantic_scholar_id and citing.semantic_scholar_id in by_ss:
                local_paper_id = by_ss[citing.semantic_scholar_id]
            elif citing.arxiv_id and citing.arxiv_id in by_arxiv:
                local_paper_id = by_arxiv[citing.arxiv_id]

            if local_paper_id is None:
                if len(result.sample_unmatched) < sample_unmatched_size:
                    result.sample_unmatched.append(citing)
                continue

            if local_paper_id in seen_local_paper_ids:
                continue
            seen_local_paper_ids.add(local_paper_id)
            result.matched_papers += 1

            if local_paper_id in existing_paper_ids:
                continue
            result.new_links += 1
            pending_batch.append({"paper_id": local_paper_id, "method_id": method.id})

            if write and len(pending_batch) >= batch_size:
                _flush_batch(db, pending_batch)
                existing_paper_ids.update(item["paper_id"] for item in pending_batch)
                pending_batch.clear()

        if write and pending_batch:
            _flush_batch(db, pending_batch)
            existing_paper_ids.update(item["paper_id"] for item in pending_batch)
            pending_batch.clear()

        stats.methods_processed += 1
        stats.total_citations_fetched += result.citations_fetched
        stats.total_matched_papers += result.matched_papers
        stats.total_new_links += result.new_links
        stats.method_results.append(result)

        log(
            f"  citations fetched: {result.citations_fetched:,}, "
            f"matched local papers: {result.matched_papers:,}, "
            f"new links {'inserted' if write else 'pending'}: {result.new_links:,}"
        )
        if result.sample_unmatched and result.matched_papers < result.citations_fetched:
            log("  sample unmatched citations:")
            for sample in result.sample_unmatched:
                log(
                    f"    - ss_id={sample.semantic_scholar_id} "
                    f"arxiv={sample.arxiv_id} title={sample.title!r}"
                )

    stats.api_calls = client.api_calls
    stats.rate_limit_hits = client.rate_limit_hits
    stats.api_errors = client.api_errors
    return stats


def _print_summary(stats: JobStats, write: bool, log=print) -> None:
    log("\n" + "=" * 80)
    log("Summary")
    log("=" * 80)
    log(f"Mode:                            {'write' if write else 'dry-run'}")
    log(f"Methods processed:               {stats.methods_processed:,}")
    log(f"Methods skipped:                 {stats.methods_skipped:,}")
    log(f"Total citations fetched:         {stats.total_citations_fetched:,}")
    log(f"Total matched local papers:      {stats.total_matched_papers:,}")
    log(f"Total new paper_methods links:   {stats.total_new_links:,}")
    log(f"Semantic Scholar API calls:      {stats.api_calls:,}")
    log(f"Rate-limit responses (429):      {stats.rate_limit_hits:,}")
    log(f"API errors:                      {stats.api_errors:,}")
    if not write:
        log("\nDry run complete. Re-run with --write to apply inserts.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply paper_methods inserts (default is dry-run).",
    )
    parser.add_argument("--method-id", type=int, help="Process a single method by ID.")
    parser.add_argument(
        "--method-slug", type=str, help="Process a single method by slug."
    )
    parser.add_argument(
        "--method-name", type=str, help="Process a single method by exact name."
    )
    parser.add_argument(
        "--limit-methods",
        type=int,
        help="Process at most N methods (after filters).",
    )
    parser.add_argument(
        "--max-citations-per-method",
        type=int,
        help="Cap total citations fetched per method (default: no cap).",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help="Seconds between Semantic Scholar requests (default: 1.5).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="paper_methods rows per insert batch (default: 500).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Citations fetched per Semantic Scholar request (max 1000).",
    )
    parser.add_argument(
        "--sample-unmatched-size",
        type=int,
        default=DEFAULT_SAMPLE_UNMATCHED,
        help="Number of unmatched citing papers to print per method.",
    )
    args = parser.parse_args()

    settings = get_settings()
    api_key = settings.semantic_scholar_api_key or None

    print("=" * 80)
    print(f"Method citation tagging ({'write' if args.write else 'dry-run'})")
    print("=" * 80)
    if not api_key:
        print(
            "WARNING: PWC_SEMANTIC_SCHOLAR_API_KEY is not set; "
            "running with anonymous Semantic Scholar access (lower rate limit)"
        )

    client = SemanticScholarClient(
        api_key=api_key,
        request_delay=args.request_delay,
    )
    try:
        with db_manager.session_local() as db:
            stats = link_papers_by_source_citations(
                db,
                client,
                write=args.write,
                method_id=args.method_id,
                method_slug=args.method_slug,
                method_name=args.method_name,
                limit_methods=args.limit_methods,
                max_citations_per_method=args.max_citations_per_method,
                batch_size=args.batch_size,
                page_size=args.page_size,
                sample_unmatched_size=args.sample_unmatched_size,
            )
    finally:
        client.close()

    _print_summary(stats, args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
