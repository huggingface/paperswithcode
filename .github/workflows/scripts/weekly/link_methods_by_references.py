"""
Weekly references-based method tagging cron.

For each paper that has not yet been processed (``papers.methods_scanned_at IS
NULL``), fetch its bibliography from Semantic Scholar
(``GET /paper/{id}/references``) and intersect the references with our set of
canonical method source papers (``methods.source_paper_id``). Insert the
matching ``(paper_id, method_id)`` rows into ``paper_methods`` with
``ON CONFLICT DO NOTHING`` and stamp ``methods_scanned_at`` so the paper is
skipped on subsequent runs.

This is the inverse view of the one-off
``backend/database/methods_setup/link_papers_by_source_citations.py`` script:
that one walks each method's citation list (good for discovering historic
overlap), this one walks each paper's reference list (good for keeping new
papers tagged as they land).

Schedule: weekly (see ``cron-link-methods-by-references.yml``).
Rate limit: ``PWC_SEMANTIC_SCHOLAR_API_KEY`` shared budget, 1 req/s.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import bindparam, text

from scripts.utils.cron_helpers import DatabaseCronJob

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.paper_method_link_service import upsert_evidence_links
from backend.database.methods_setup.link_papers_by_source_citations import (
    SemanticScholarClient,
)


DEFAULT_PAPERS_PER_RUN = 5_000
DEFAULT_REQUEST_DELAY = 1.0
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_RUNTIME_SECONDS = 4 * 60 * 60  # 4h cap; weekly cron is generous.


@dataclass
class JobStats:
    papers_eligible: int = 0
    papers_processed: int = 0
    papers_skipped_no_ss_id: int = 0
    papers_lookup_failed: int = 0
    references_fetched: int = 0
    method_matches_found: int = 0
    links_inserted: int = 0
    api_calls: int = 0
    rate_limit_hits: int = 0
    api_errors: int = 0
    method_link_counts: Dict[int, int] = field(default_factory=lambda: defaultdict(int))


def build_method_source_index(
    db,
) -> Tuple[Dict[str, List[int]], Dict[str, List[int]], Dict[int, str]]:
    """Return ``(by_ss_id, by_arxiv_id, method_id_to_name)`` for current methods."""

    rows = db.execute(
        text(
            """
            SELECT m.id AS method_id,
                   m.name AS method_name,
                   p.semantic_scholar_id AS ss_id,
                   p.arxiv_id AS arxiv_id
            FROM methods m
            JOIN papers p ON p.id = m.source_paper_id
            WHERE m.source_paper_id IS NOT NULL
            """
        )
    ).all()

    by_ss: Dict[str, List[int]] = defaultdict(list)
    by_arxiv: Dict[str, List[int]] = defaultdict(list)
    name_by_id: Dict[int, str] = {}
    for row in rows:
        name_by_id[row.method_id] = row.method_name
        if row.ss_id:
            by_ss[row.ss_id].append(row.method_id)
        if row.arxiv_id:
            by_arxiv[row.arxiv_id].append(row.method_id)

    return by_ss, by_arxiv, name_by_id


def select_unscanned_papers(
    db,
    *,
    limit: int,
    paper_id: Optional[int] = None,
    paper_arxiv_id: Optional[str] = None,
    rescan: bool = False,
) -> List[Dict[str, Any]]:
    """Return papers eligible for the references-based scan, newest first."""

    where_clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}
    # Targeted modes (paper_id / paper_arxiv_id) bypass the "unscanned" filter so
    # operators can re-process a specific paper without flipping --rescan globally.
    if paper_id is not None:
        where_clauses.append("id = :paper_id")
        params["paper_id"] = paper_id
    elif paper_arxiv_id:
        where_clauses.append("arxiv_id = :paper_arxiv_id AND is_latest_version")
        params["paper_arxiv_id"] = paper_arxiv_id
    elif not rescan:
        where_clauses.append("methods_scanned_at IS NULL AND is_latest_version")
    else:
        where_clauses.append("is_latest_version")

    sql = text(
        f"""
        SELECT id, arxiv_id, semantic_scholar_id, title, date_published
        FROM papers
        WHERE {" AND ".join(where_clauses)}
        ORDER BY date_published DESC NULLS LAST, id DESC
        LIMIT :limit
        """
    )

    return [dict(row._mapping) for row in db.execute(sql, params).all()]


def count_unscanned_papers(db) -> int:
    return (
        db.execute(
            text(
                "SELECT COUNT(*) FROM papers "
                "WHERE methods_scanned_at IS NULL AND is_latest_version"
            )
        ).scalar()
    ) or 0


def _resolve_paper_ss_id(paper: Dict[str, Any]) -> Optional[str]:
    """Get an identifier we can use against the Semantic Scholar paper API.

    Prefers the cached ``semantic_scholar_id``; falls back to the ``arXiv:<id>``
    form which Semantic Scholar resolves server-side. Returns ``None`` for
    external papers that have neither identifier.
    """

    if paper.get("semantic_scholar_id"):
        return paper["semantic_scholar_id"]
    arxiv_id = paper.get("arxiv_id")
    if not arxiv_id:
        return None
    return f"arXiv:{arxiv_id}"


def _flush_paper_methods(db, batch: List[dict]) -> int:
    if not batch:
        return 0
    return upsert_evidence_links(db, batch, evidence_type="reference")


def _mark_paper_scanned(db, paper_ids: List[int]) -> None:
    if not paper_ids:
        return
    stmt = text(
        """
        UPDATE papers
        SET methods_scanned_at = :now
        WHERE id IN :paper_ids
        """
    ).bindparams(bindparam("paper_ids", expanding=True))
    db.execute(
        stmt,
        {"now": datetime.now(timezone.utc), "paper_ids": paper_ids},
    )


def link_methods_by_references(
    db,
    client: SemanticScholarClient,
    *,
    limit: int,
    paper_id: Optional[int] = None,
    paper_arxiv_id: Optional[str] = None,
    rescan: bool = False,
    write: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_runtime_seconds: Optional[int] = None,
    log=print,
) -> JobStats:
    """Scan papers' references and tag them with matching methods."""

    stats = JobStats()
    by_ss, by_arxiv, method_name_by_id = build_method_source_index(db)
    log(f"Indexed method source papers: ss_ids={len(by_ss)}, arxiv_ids={len(by_arxiv)}")
    if not by_ss and not by_arxiv:
        log("No methods have a source_paper_id; nothing to do.")
        return stats

    papers = select_unscanned_papers(
        db,
        limit=limit,
        paper_id=paper_id,
        paper_arxiv_id=paper_arxiv_id,
        rescan=rescan,
    )
    stats.papers_eligible = len(papers)
    # End the read transaction before the slow Semantic Scholar lookups:
    # Postgres drops sessions idle in a transaction for 10 minutes, which killed
    # the 2026-10-25 and 2026-10-28 runs at their first flush.
    db.commit()
    log(f"Selected {len(papers):,} eligible papers (newest first).")
    if not papers:
        return stats

    pending_paper_methods: List[dict] = []
    pending_scanned_paper_ids: List[int] = []
    started_at = time.monotonic()

    for idx, paper in enumerate(papers, start=1):
        if (
            max_runtime_seconds is not None
            and time.monotonic() - started_at > max_runtime_seconds
        ):
            log(
                f"Reached runtime cap of {max_runtime_seconds}s; "
                f"stopping after {idx - 1} papers."
            )
            break

        ss_id = _resolve_paper_ss_id(paper)
        if not ss_id:
            stats.papers_skipped_no_ss_id += 1
            log(
                f"  ! [{idx}/{len(papers)}] paper id={paper['id']} "
                f"arxiv={paper.get('arxiv_id')!r} has no SS id and no arxiv id; skipping"
            )
            if write:
                pending_scanned_paper_ids.append(paper["id"])
            continue

        matched_method_ids: set[int] = set()
        references_fetched = 0
        failures_before = getattr(
            client,
            "failed_requests",
            client.api_errors + client.rate_limit_hits,
        )
        for cited in client.iter_references(ss_id):
            references_fetched += 1
            if cited.semantic_scholar_id and cited.semantic_scholar_id in by_ss:
                for method_id in by_ss[cited.semantic_scholar_id]:
                    matched_method_ids.add(method_id)
            elif cited.arxiv_id and cited.arxiv_id in by_arxiv:
                for method_id in by_arxiv[cited.arxiv_id]:
                    matched_method_ids.add(method_id)
        failures_after = getattr(
            client,
            "failed_requests",
            client.api_errors + client.rate_limit_hits,
        )
        if failures_after > failures_before:
            stats.papers_lookup_failed += 1
            log(
                f"  ! [{idx}/{len(papers)}] bibliography lookup failed for "
                f"paper id={paper['id']}; leaving it unscanned for retry"
            )
            continue

        stats.papers_processed += 1
        stats.references_fetched += references_fetched
        stats.method_matches_found += len(matched_method_ids)

        for method_id in matched_method_ids:
            stats.method_link_counts[method_id] += 1
            if write:
                pending_paper_methods.append(
                    {"paper_id": paper["id"], "method_id": method_id}
                )

        if write:
            pending_scanned_paper_ids.append(paper["id"])

        if write and len(pending_paper_methods) >= batch_size:
            stats.links_inserted += _flush_paper_methods(db, pending_paper_methods)
            pending_paper_methods.clear()
            _mark_paper_scanned(db, pending_scanned_paper_ids)
            pending_scanned_paper_ids.clear()
            db.commit()

        if idx % 50 == 0 or idx == len(papers):
            log(
                f"  [{idx}/{len(papers)}] processed; "
                f"references={stats.references_fetched:,}, "
                f"matches={stats.method_matches_found:,}, "
                f"inserted={stats.links_inserted:,}, "
                f"queued={len(pending_paper_methods):,}"
            )

    if write:
        stats.links_inserted += _flush_paper_methods(db, pending_paper_methods)
        pending_paper_methods.clear()
        _mark_paper_scanned(db, pending_scanned_paper_ids)
        pending_scanned_paper_ids.clear()
        db.commit()

    stats.api_calls = client.api_calls
    stats.rate_limit_hits = client.rate_limit_hits
    stats.api_errors = client.api_errors

    if stats.method_link_counts:
        top = sorted(
            stats.method_link_counts.items(), key=lambda item: item[1], reverse=True
        )[:10]
        log("Top methods touched this run:")
        for method_id, count in top:
            name = method_name_by_id.get(method_id, f"<id {method_id}>")
            log(f"  - {name:32} {count:>5,} papers")

    return stats


class MethodReferencesWeeklyJob(DatabaseCronJob):
    """Weekly job that tags papers with methods based on their bibliography."""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_PAPERS_PER_RUN,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS,
        dry_run: bool = False,
        rescan: bool = False,
        paper_id: Optional[int] = None,
        paper_arxiv_id: Optional[str] = None,
    ):
        super().__init__(job_name="link_methods_by_references_weekly", log_level="INFO")
        self.settings = get_settings()
        self.limit = limit
        self.request_delay = request_delay
        self.batch_size = batch_size
        self.max_runtime_seconds = max_runtime_seconds
        self.dry_run = dry_run
        self.rescan = rescan
        self.paper_id = paper_id
        self.paper_arxiv_id = paper_arxiv_id

    def run(self):
        api_key = self.settings.semantic_scholar_api_key or None
        if not api_key:
            self.logger.warning(
                "PWC_SEMANTIC_SCHOLAR_API_KEY is not set; using anonymous access"
            )

        client = SemanticScholarClient(
            api_key=api_key,
            request_delay=self.request_delay,
        )
        try:
            with db_manager.session_local() as db:
                eligible = count_unscanned_papers(db)
                self.logger.info(
                    f"Total papers awaiting references-based scan: {eligible:,}"
                )
                stats = link_methods_by_references(
                    db,
                    client,
                    limit=self.limit,
                    paper_id=self.paper_id,
                    paper_arxiv_id=self.paper_arxiv_id,
                    rescan=self.rescan,
                    write=not self.dry_run,
                    batch_size=self.batch_size,
                    max_runtime_seconds=self.max_runtime_seconds,
                    log=self.logger.info,
                )
        finally:
            client.close()

        self.logger.info("=" * 80)
        self.logger.info("Method references scan summary")
        self.logger.info("=" * 80)
        self.logger.info(
            f"  Mode:                       {'dry-run' if self.dry_run else 'write'}"
        )
        self.logger.info(f"  Papers eligible (selected): {stats.papers_eligible:,}")
        self.logger.info(f"  Papers processed:           {stats.papers_processed:,}")
        self.logger.info(
            f"  Papers skipped (no SS id):  {stats.papers_skipped_no_ss_id:,}"
        )
        self.logger.info(
            f"  Papers with empty refs:     {stats.papers_lookup_failed:,}"
        )
        self.logger.info(f"  References fetched:         {stats.references_fetched:,}")
        self.logger.info(
            f"  Method matches found:       {stats.method_matches_found:,}"
        )
        self.logger.info(f"  paper_methods links written:{stats.links_inserted:,}")
        self.logger.info(f"  Semantic Scholar API calls: {stats.api_calls:,}")
        self.logger.info(f"  Rate-limit responses (429): {stats.rate_limit_hits:,}")
        self.logger.info(f"  API errors:                 {stats.api_errors:,}")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_PAPERS_PER_RUN,
        help=f"Max papers to process this run (default: {DEFAULT_PAPERS_PER_RUN}).",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help="Seconds between Semantic Scholar requests (default: 1.0).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of paper_methods rows per insert batch (default: 500).",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=DEFAULT_MAX_RUNTIME_SECONDS,
        help="Hard cap on total runtime (default: 4h).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write paper_methods or methods_scanned_at; just report counts.",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Include papers that already have methods_scanned_at set.",
    )
    parser.add_argument(
        "--paper-id", type=int, help="Process only this paper id (for debugging)."
    )
    parser.add_argument(
        "--paper-arxiv-id",
        type=str,
        help="Process only the latest version of this arXiv id (for debugging).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    job = MethodReferencesWeeklyJob(
        limit=args.limit,
        request_delay=args.request_delay,
        batch_size=args.batch_size,
        max_runtime_seconds=args.max_runtime_seconds,
        dry_run=args.dry_run,
        rescan=args.rescan,
        paper_id=args.paper_id,
        paper_arxiv_id=args.paper_arxiv_id,
    )
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
