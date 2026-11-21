"""Bounded, resumable historical method-link backfills."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Callable, Iterable

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from backend.models.database import (
    Method,
    MethodKeywordBackfillRun,
    MethodReferenceBackfillMonth,
    Paper,
    PaperMethodExclusion,
)
from backend.services.paper_method_link_service import (
    method_history_start,
    month_start,
    shift_month,
    upsert_evidence_links,
)
from backend.utils.keyword_matching import (
    create_keyword_patterns_with_metadata,
    find_matching_items_longest_match,
)

KEYWORD_MATCHER_VERSION = "longest-match-v1"
REFERENCE_LOCK_NAMESPACE = 0x4D524246
KEYWORD_LOCK_ID = 0x4D4B4246


@dataclass
class BackfillStats:
    papers_processed: int = 0
    papers_unresolvable: int = 0
    papers_failed: int = 0
    api_calls: int = 0
    matches: int = 0
    links_written: int = 0
    months_completed: int = 0


def _request_failure_count(client) -> int:
    """Return terminal request failures, with compatibility for test clients."""
    if hasattr(client, "failed_requests"):
        return client.failed_requests
    return client.api_errors + client.rate_limit_hits


def audit_undated_method_links(db: Session, *, sample_size: int = 20) -> dict:
    """Summarize latest-version method links omitted from monthly charts."""
    total = (
        db.execute(
            text("""
            SELECT count(DISTINCT p.id)
            FROM papers p JOIN paper_methods pm ON pm.paper_id = p.id
            WHERE p.is_latest_version AND p.date_published IS NULL
            """)
        ).scalar()
        or 0
    )
    grouped = [
        dict(row._mapping)
        for row in db.execute(
            text("""
                SELECT p.source,
                       (p.arxiv_id IS NOT NULL) AS has_arxiv_id,
                       count(DISTINCT p.id) AS paper_count
                FROM papers p
                JOIN paper_methods pm ON pm.paper_id = p.id
                WHERE p.is_latest_version AND p.date_published IS NULL
                GROUP BY 1, 2 ORDER BY 1, 2
                """)
        ).all()
    ]
    sample = [
        dict(row._mapping)
        for row in db.execute(
            text("""
                SELECT DISTINCT p.id, p.arxiv_id, p.source, p.title
                FROM papers p
                JOIN paper_methods pm ON pm.paper_id = p.id
                WHERE p.is_latest_version AND p.date_published IS NULL
                ORDER BY p.id LIMIT :sample_size
                """),
            {"sample_size": sample_size},
        ).all()
    ]
    return {"total": total, "grouped": grouped, "sample": sample}


def keyword_catalog_rows(db: Session) -> tuple[str, list[dict]]:
    methods = [
        {"id": row.id, "name": row.name, "keywords": row.keywords}
        for row in db.query(Method)
        .filter(Method.keywords.isnot(None), Method.keywords != "")
        .order_by(Method.id)
        .all()
    ]
    payload = json.dumps(
        {
            "matcher": KEYWORD_MATCHER_VERSION,
            "methods": [
                {"id": method["id"], "keywords": method["keywords"]}
                for method in methods
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return digest, methods


def keyword_catalog(
    db: Session,
) -> tuple[str, list[dict], dict, dict]:
    digest, methods = keyword_catalog_rows(db)
    sensitive, insensitive = create_keyword_patterns_with_metadata(methods)
    return digest, methods, sensitive, insensitive


def run_keyword_backfill(
    db: Session,
    *,
    after_paper_id: int | None = None,
    limit: int = 5_000,
    max_runtime_seconds: int = 3_600,
    dry_run: bool = True,
    resume: bool = False,
    batch_size: int = 250,
    log: Callable[[str], None] = print,
) -> BackfillStats:
    """Stream the latest-version catalog and apply the importer matcher."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if max_runtime_seconds < 1:
        raise ValueError("max_runtime_seconds must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    digest, methods, sensitive, insensitive = keyword_catalog(db)
    stats = BackfillStats()
    if not methods:
        return stats
    if (
        db.bind.dialect.name == "postgresql"
        and not db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": KEYWORD_LOCK_ID}
        ).scalar()
    ):
        raise RuntimeError("another method keyword backfill is running")
    run = None
    try:
        run = None if dry_run else db.get(MethodKeywordBackfillRun, digest)
        if run is None and not dry_run:
            superseded = (
                db.query(MethodKeywordBackfillRun)
                .filter(
                    MethodKeywordBackfillRun.status == "running",
                    MethodKeywordBackfillRun.keyword_catalog_sha256 != digest,
                )
                .all()
            )
            for previous in superseded:
                previous.status = "failed"
                previous.completed_at = datetime.now(UTC)
                previous.updated_at = datetime.now(UTC)
                previous.last_error = "superseded by a changed method keyword catalog"
            if superseded:
                db.commit()
            run = MethodKeywordBackfillRun(
                keyword_catalog_sha256=digest,
                status="running",
                eligible_papers=db.query(func.count(Paper.id))
                .filter(Paper.is_latest_version)
                .scalar(),
                started_at=datetime.now(UTC),
            )
            db.add(run)
            db.commit()
        elif run is not None and not resume and after_paper_id is None:
            raise ValueError(
                "progress already exists for this keyword catalog; pass --resume"
            )
        if run is not None and not dry_run:
            run.status = "running"
            run.completed_at = None
            run.last_error = None
            run.updated_at = datetime.now(UTC)
            db.commit()
        cursor = after_paper_id or (run.cursor_paper_id if resume and run else 0) or 0
        started = time.monotonic()
        while stats.papers_processed < limit:
            papers = (
                db.query(Paper.id, Paper.title, Paper.abstract)
                .filter(Paper.is_latest_version, Paper.id > cursor)
                .order_by(Paper.id)
                .limit(min(batch_size, limit - stats.papers_processed))
                .all()
            )
            if not papers or time.monotonic() - started >= max_runtime_seconds:
                break
            links: list[dict] = []
            for paper_id, title, abstract in papers:
                matches = find_matching_items_longest_match(
                    " ".join(filter(None, (title, abstract))), sensitive, insensitive
                )
                links.extend(
                    {"paper_id": paper_id, "method_id": method_id}
                    for method_id in matches
                )
                stats.matches += len(matches)
                cursor = paper_id
            if not dry_run:
                stats.links_written += upsert_evidence_links(
                    db, links, evidence_type="keyword"
                )
                run.processed_papers += len(papers)
                run.cursor_paper_id = cursor
                run.updated_at = datetime.now(UTC)
                db.commit()
            stats.papers_processed += len(papers)
            log(
                f"keyword backfill cursor={cursor} processed={stats.papers_processed} "
                f"matches={stats.matches}"
            )
        if not dry_run and not (
            db.query(Paper.id)
            .filter(Paper.is_latest_version, Paper.id > cursor)
            .first()
        ):
            run.eligible_papers = (
                db.query(func.count(Paper.id)).filter(Paper.is_latest_version).scalar()
            )
            run.status = "complete"
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            db.commit()
        return stats
    except Exception as exc:
        db.rollback()
        if run is not None and not dry_run:
            run = db.get(MethodKeywordBackfillRun, digest)
            if run is not None:
                run.status = "failed"
                run.completed_at = datetime.now(UTC)
                run.updated_at = datetime.now(UTC)
                run.last_error = str(exc)
                db.commit()
        raise
    finally:
        if db.bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": KEYWORD_LOCK_ID},
            )


def select_sourced_methods(
    db: Session, *, method_ids: Iterable[int] = (), method_slugs: Iterable[str] = ()
) -> list[Method]:
    query = db.query(Method).filter(Method.source_paper_id.isnot(None))
    ids, slugs = list(method_ids), list(method_slugs)
    if ids or slugs:
        query = query.filter(or_(Method.id.in_(ids), Method.slug.in_(slugs)))
    return (
        query.outerjoin(Paper, Paper.id == Method.source_paper_id)
        .order_by(Paper.citation_count.desc().nullslast(), Method.id)
        .all()
    )


def seed_reference_months(
    db: Session,
    methods: Iterable[Method],
    *,
    month_from: date | None = None,
    month_to: date | None = None,
    write: bool,
) -> list[date]:
    current = month_start(datetime.now(UTC).date())
    months: set[date] = set()
    for method in methods:
        start = max(method_history_start(db, method) or current, month_from or date.min)
        end = min(month_to or current, current)
        cursor = start
        while cursor <= end:
            months.add(cursor)
            if (
                write
                and db.get(MethodReferenceBackfillMonth, (method.id, cursor)) is None
            ):
                db.add(
                    MethodReferenceBackfillMonth(
                        method_id=method.id, month_start=cursor, status="pending"
                    )
                )
            cursor = shift_month(cursor, 1)
    if write:
        db.commit()
    return sorted(months)


def run_reference_backfill(
    db: Session,
    client,
    *,
    method_ids: Iterable[int] = (),
    method_slugs: Iterable[str] = (),
    month_from: date | None = None,
    month_to: date | None = None,
    limit: int = 1_000,
    max_runtime_seconds: int = 3_600,
    dry_run: bool = True,
    resume: bool = False,
    retry_failures: bool = False,
    batch_size: int = 250,
    log: Callable[[str], None] = print,
) -> BackfillStats:
    """Scan local papers oldest-first and match selected method sources locally."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if max_runtime_seconds < 1:
        raise ValueError("max_runtime_seconds must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    methods = select_sourced_methods(
        db, method_ids=method_ids, method_slugs=method_slugs
    )
    if not methods:
        raise ValueError("no sourced methods matched the selection")
    months = seed_reference_months(
        db, methods, month_from=month_from, month_to=month_to, write=not dry_run
    )
    source_rows = {
        method.id: db.get(Paper, method.source_paper_id) for method in methods
    }
    by_ss: dict[str, set[int]] = {}
    by_arxiv: dict[str, set[int]] = {}
    for method_id, paper in source_rows.items():
        if paper and paper.semantic_scholar_id:
            by_ss.setdefault(paper.semantic_scholar_id, set()).add(method_id)
        if paper and paper.arxiv_id:
            by_arxiv.setdefault(paper.arxiv_id, set()).add(method_id)
    provider_name = getattr(client, "provider_name", "semantic_scholar")
    by_openalex: dict[str, set[int]] = {}
    if provider_name == "openalex":
        source_batch = client.fetch_works(by_arxiv)
        if source_batch is None:
            raise RuntimeError("OpenAlex source-paper lookup failed")
        for arxiv_id, method_ids_for_source in by_arxiv.items():
            work_ids = source_batch.work_ids_by_arxiv.get(arxiv_id, set())
            if not work_ids:
                log(f"OpenAlex could not resolve method source arXiv:{arxiv_id}")
                continue
            for work_id in work_ids:
                by_openalex.setdefault(work_id, set()).update(method_ids_for_source)
        if not by_openalex:
            raise ValueError("OpenAlex could not resolve any selected method source")
    stats = BackfillStats()
    started = time.monotonic()
    for month in months:
        if stats.papers_processed + stats.papers_unresolvable >= limit:
            break
        next_month = shift_month(month, 1)
        eligible = (
            db.query(func.count(Paper.id))
            .filter(
                Paper.is_latest_version,
                Paper.date_published >= month,
                Paper.date_published < next_month,
            )
            .scalar()
            or 0
        )
        active = [
            method
            for method in methods
            if (method_history_start(db, method) or month) <= month
        ]
        rows = (
            {method.id: None for method in active}
            if dry_run
            else {
                method.id: db.get(MethodReferenceBackfillMonth, (method.id, month))
                for method in active
            }
        )
        if not dry_run:
            stale_complete_method_ids = {
                method_id
                for method_id, row in rows.items()
                if row and row.status == "complete" and row.eligible_papers != eligible
            }
            rows = {
                method_id: row
                for method_id, row in rows.items()
                if row
                and (row.status != "complete" or method_id in stale_complete_method_ids)
            }
            active = [method for method in active if method.id in rows]
            if not resume and any(
                row.cursor_published_at is not None for row in rows.values()
            ):
                raise ValueError(
                    "progress already exists for this selection; pass --resume"
                )
        if not active:
            continue
        lock_key = REFERENCE_LOCK_NAMESPACE ^ month.toordinal()
        if (
            db.bind.dialect.name == "postgresql"
            and not db.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": lock_key}
            ).scalar()
        ):
            log(f"reference backfill month={month} skipped: lock held")
            continue
        if not dry_run:
            for method_id in stale_complete_method_ids:
                row = rows[method_id]
                row.status = "pending"
                row.processed_papers = 0
                row.matched_papers = 0
                row.unresolvable_papers = 0
                row.retryable_failures = 0
                row.cursor_published_at = None
                row.cursor_paper_id = None
                row.completed_at = None
                row.last_error = None
        row_cursors = {
            method_id: (
                row.cursor_published_at if row else None,
                (row.cursor_paper_id or 0) if row else 0,
            )
            for method_id, row in rows.items()
        }
        cursor_date, cursor_id = min(
            (
                (published or date.min, paper_id)
                for published, paper_id in row_cursors.values()
            ),
            default=(date.min, 0),
        )
        if cursor_date == date.min:
            cursor_date = None
        query = db.query(
            Paper.id, Paper.date_published, Paper.semantic_scholar_id, Paper.arxiv_id
        ).filter(
            Paper.is_latest_version,
            Paper.date_published >= month,
            Paper.date_published < next_month,
        )
        if cursor_date:
            query = query.filter(
                or_(
                    Paper.date_published > cursor_date,
                    and_(Paper.date_published == cursor_date, Paper.id > cursor_id),
                )
            )
        papers = (
            query.order_by(Paper.date_published, Paper.id)
            .limit(limit - stats.papers_processed - stats.papers_unresolvable)
            .all()
        )
        excluded_pairs = (
            {
                (paper_id, method_id)
                for paper_id, method_id in db.query(
                    PaperMethodExclusion.paper_id, PaperMethodExclusion.method_id
                )
                .filter(
                    PaperMethodExclusion.paper_id.in_([paper.id for paper in papers]),
                    PaperMethodExclusion.method_id.in_(rows),
                )
                .all()
            }
            if papers
            else set()
        )
        openalex_batch = (
            client.fetch_works(paper.arxiv_id for paper in papers if paper.arxiv_id)
            if provider_name == "openalex"
            else None
        )
        openalex_lookup_failed = provider_name == "openalex" and openalex_batch is None
        if not dry_run:
            for row in rows.values():
                row.status = "running"
                row.eligible_papers = eligible
                row.attempt_count += 1
                if retry_failures:
                    row.retryable_failures = 0
                    row.last_error = None
                row.started_at = row.started_at or datetime.now(UTC)
                row.updated_at = datetime.now(UTC)
            db.commit()
        pending_checkpoint = 0
        runtime_reached = False
        lookup_failed = False
        for paper in papers:
            if time.monotonic() - started >= max_runtime_seconds:
                runtime_reached = True
                break
            eligible_method_ids = {
                method_id
                for method_id, (published, paper_id) in row_cursors.items()
                if published is None
                or (paper.date_published, paper.id) > (published, paper_id)
            }
            if provider_name == "openalex":
                identifier = f"arXiv:{paper.arxiv_id}" if paper.arxiv_id else None
                failed = openalex_lookup_failed
                if failed:
                    resolved = False
                    matched = set()
                elif not identifier:
                    resolved = False
                    stats.papers_unresolvable += 1
                    matched = set()
                elif not openalex_batch.work_ids_by_arxiv.get(paper.arxiv_id):
                    resolved = False
                    stats.papers_unresolvable += 1
                    matched = set()
                else:
                    resolved = True
                    matched = {
                        method_id
                        for reference_id in openalex_batch.references_by_arxiv.get(
                            paper.arxiv_id, set()
                        )
                        for method_id in by_openalex.get(reference_id, set())
                        if method_id in eligible_method_ids
                        and (paper.id, method_id) not in excluded_pairs
                    }
            else:
                identifier = paper.semantic_scholar_id or (
                    f"arXiv:{paper.arxiv_id}" if paper.arxiv_id else None
                )
                resolved = bool(identifier)
                if not identifier:
                    stats.papers_unresolvable += 1
                    matched = set()
                    failed = False
                else:
                    failures_before = _request_failure_count(client)
                    cited = list(client.iter_references(identifier))
                    failed = _request_failure_count(client) > failures_before
                    matched = {
                        method_id
                        for reference in cited
                        for method_id in (
                            by_ss.get(reference.semantic_scholar_id, set())
                            | by_arxiv.get(reference.arxiv_id, set())
                        )
                        if method_id in eligible_method_ids
                        and (paper.id, method_id) not in excluded_pairs
                    }
            if failed:
                lookup_failed = True
                stats.papers_failed += 1
                if not dry_run:
                    for method_id, row in rows.items():
                        if method_id not in eligible_method_ids:
                            continue
                        row.retryable_failures += 1
                        row.last_error = (
                            f"{provider_name} lookup failed for {identifier}"
                        )
                        row.updated_at = datetime.now(UTC)
                    db.commit()
                break
            stats.papers_processed += resolved
            stats.matches += len(matched)
            if not dry_run:
                stats.links_written += upsert_evidence_links(
                    db,
                    (
                        {"paper_id": paper.id, "method_id": method_id}
                        for method_id in matched
                    ),
                    evidence_type="reference",
                    details={
                        "workload_key": (
                            "secondary"
                            if provider_name == "semantic_scholar"
                            else provider_name
                        ),
                        "provider": provider_name,
                    },
                )
                for method_id, row in rows.items():
                    if method_id not in eligible_method_ids:
                        continue
                    if resolved:
                        row.processed_papers += 1
                    else:
                        row.unresolvable_papers += 1
                    if method_id in matched:
                        row.matched_papers += 1
                    row.cursor_published_at = paper.date_published
                    row.cursor_paper_id = paper.id
                    row_cursors[method_id] = (paper.date_published, paper.id)
                    row.updated_at = datetime.now(UTC)
                cursor_date = paper.date_published
                cursor_id = paper.id
                pending_checkpoint += 1
                if pending_checkpoint >= batch_size:
                    db.commit()
                    pending_checkpoint = 0
        if not dry_run and pending_checkpoint:
            db.commit()
        if not dry_run:
            remaining = (
                db.query(func.count(Paper.id))
                .filter(
                    Paper.is_latest_version,
                    Paper.date_published >= month,
                    Paper.date_published < next_month,
                    or_(
                        Paper.date_published > (cursor_date or month),
                        and_(
                            Paper.date_published == (cursor_date or month),
                            Paper.id > cursor_id,
                        ),
                    ),
                )
                .scalar()
                or 0
            )
            eligible_now = (
                db.query(func.count(Paper.id))
                .filter(
                    Paper.is_latest_version,
                    Paper.date_published >= month,
                    Paper.date_published < next_month,
                )
                .scalar()
                or 0
            )
            for row in rows.values():
                row.eligible_papers = eligible_now
                accounted = row.processed_papers + row.unresolvable_papers
                if (
                    remaining == 0
                    and accounted < eligible_now
                    and row.retryable_failures == 0
                ):
                    row.status = "pending"
                    row.processed_papers = 0
                    row.matched_papers = 0
                    row.unresolvable_papers = 0
                    row.cursor_published_at = None
                    row.cursor_paper_id = None
                    row.completed_at = None
                    row.updated_at = datetime.now(UTC)
                    continue
                if (
                    remaining == 0
                    and accounted >= eligible_now
                    and row.retryable_failures == 0
                ):
                    row.status = "complete"
                    row.completed_at = datetime.now(UTC)
                    stats.months_completed += 1
                row.updated_at = datetime.now(UTC)
            db.commit()
        remaining_estimate = (
            remaining if not dry_run else max(0, eligible - len(papers))
        )
        log(
            f"reference backfill month={month} methods={len(active)} "
            f"processed={stats.papers_processed} api_calls={client.api_calls} "
            f"retries={getattr(client, 'retry_attempts', client.rate_limit_hits)} "
            f"matches={stats.matches} "
            f"links={stats.links_written} cursor={cursor_date}/{cursor_id} "
            f"remaining={remaining_estimate} provider={provider_name}"
        )
        if db.bind.dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key}
            )
        if runtime_reached or lookup_failed:
            break
    stats.api_calls = client.api_calls
    return stats
