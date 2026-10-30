"""
Thumbnail Preload CRON Job

Generates and uploads paper thumbnails to a Hugging Face Storage Bucket so that
they are warm before browsers request them via /api/thumbnails/{filename}.

Priority modes (selected via --priority):
- `visible`: union of every user-visible candidate set — homepage feed
  (top --citation-top by citation count, top --trending-top trending,
  top --newest-top by date_published) plus the top --per-task and
  --per-method papers on every task and method page across all three
  sort tabs (trending, newest, most cited). Yielded homepage-first
  (citation -> trending -> newest -> tasks -> methods), deduplicated by
  paper id, then capped by --limit. Used by the hourly visible preload cron.
- `trending`: candidates ranked by the EMA-smoothed `trending_papers_24h`
  view alone.
- `task-top`: top --per-task papers per task tag across the three sort tabs
  (trending, newest, most cited). Used by the daily task-page preload cron.
- `method-top`: top --per-method papers per method tag across the three sort
  tabs (trending, newest, most cited). Used by the daily method-page preload
  cron.
- `recent`: existing newest-first preload, optionally constrained to
  --recent-days. Used by the daily broad preload cron.
- `missing-all`: oldest-first sweep over every latest-version ArXiv paper
  whose thumbnail is missing locally. Supports `--shard i/n` and `--after-id`
  / `--before-id` for chunked manual backfills.
- `external-missing`: sweep over non-ArXiv external papers missing an explicit
  captured thumbnail. Direct PDF source URLs are rendered from page one; bioRxiv
  and medRxiv papers use the bioRxiv API plus Europe PMC / S3 TDM mirrors;
  other source pages are captured with headless Chrome.

The local cache is the source of truth for "do we have this thumbnail" during
backfills: candidates whose .jpg already exists on disk are skipped without any
HF bucket round-trip. By default the bucket is also probed once per missing
candidate; pass `--trust-local-cache` to skip that probe (cheap, safe when the
mirror cron is healthy) so a large backfill can process candidates as fast as
ArXiv allows.

Schedule: see `.github/workflows/cron-preload-thumbnails.yml` for the different
schedules feeding each priority mode.

Dependencies: PostgreSQL, ArXiv access, Hugging Face bucket configured via
PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket plus PWC_THUMBNAIL_HF_BUCKET_ID and
PWC_HF_TOKEN.
"""

import argparse
import asyncio
import gc
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional, Tuple

from sqlalchemy import and_, or_, text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper as DBPaper
from backend.services.thumbnail_service import (
    EXPECTED_THUMBNAIL_WIDTH,
    ThumbnailService,
    build_custom_thumbnail_url,
    build_external_thumbnail_filename,
    build_thumbnail_filename,
    is_thumbnail_valid,
)
from backend.utils.exceptions import ThumbnailGenerationError, ThumbnailUnavailableError
from scripts.utils.cron_helpers import CronJobBase

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_FAILURES = 50
DEFAULT_REFRESH_REQUEST_DELAY_SECONDS = 6.0
DEFAULT_TRENDING_MAX_AGE_DAYS = 180
DEFAULT_PER_TASK = 50
DEFAULT_PER_METHOD = 50
DEFAULT_CITATION_TOP = 1000
DEFAULT_TRENDING_TOP = 500
DEFAULT_NEWEST_TOP = 300
DEFAULT_VISIBLE_PER_TASK = 20
DEFAULT_VISIBLE_PER_METHOD = 20

# Whitelist of (join_table, group_id_column) pairs used by `_iter_group_top`.
# Restricted to known values because the column / table identifiers are
# interpolated into the SQL string (psycopg cannot parameterise identifiers).
_GROUP_TOP_TABLES = {
    "paper_tasks": "task_id",
    "paper_methods": "method_id",
}

VALID_PRIORITIES = (
    "visible",
    "trending",
    "task-top",
    "method-top",
    "recent",
    "missing-all",
    "external-missing",
)


class Candidate(NamedTuple):
    paper_id: int
    arxiv_id: Optional[str]
    version: str
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    pdf_url: Optional[str] = None


class ThumbnailPreloadJob(CronJobBase):
    """Generate thumbnails for prioritised subsets of ArXiv papers."""

    def __init__(
        self,
        priority: str,
        limit: Optional[int],
        batch_size: int,
        recent_days: Optional[int],
        per_task: int,
        per_method: int,
        trending_max_age_days: int,
        citation_top: int,
        trending_top: int,
        newest_top: int,
        after_id: Optional[int],
        before_id: Optional[int],
        shard: Optional[Tuple[int, int]],
        missing_only: bool,
        trust_local_cache: bool,
        max_failures: Optional[int],
        dry_run: bool,
        refresh_existing: bool,
        request_delay_seconds: Optional[float],
        max_runtime_seconds: Optional[float] = None,
    ):
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Unknown priority '{priority}', expected one of {VALID_PRIORITIES}"
            )

        super().__init__(job_name="preload_thumbnails", log_level="INFO")
        self.settings = get_settings()
        self.priority = priority
        self.limit = limit
        self.batch_size = max(1, batch_size)
        self.recent_days = recent_days
        self.per_task = max(1, per_task)
        self.per_method = max(1, per_method)
        self.trending_max_age_days = max(1, trending_max_age_days)
        self.citation_top = max(0, citation_top)
        self.trending_top = max(0, trending_top)
        self.newest_top = max(0, newest_top)
        self.after_id = after_id
        self.before_id = before_id
        self.shard = shard
        self.missing_only = missing_only
        self.trust_local_cache = trust_local_cache
        self.max_failures = max_failures
        self.dry_run = dry_run
        self.refresh_existing = refresh_existing
        self.max_runtime_seconds = max_runtime_seconds

        # missing-all defaults to trusting the local cache because probing the
        # bucket for tens of thousands of candidates is pure overhead when the
        # mirror cron is healthy.
        if priority == "missing-all" and not refresh_existing:
            self.trust_local_cache = True

        if request_delay_seconds is not None:
            self.request_delay_seconds = max(0.0, request_delay_seconds)
        elif refresh_existing and not dry_run:
            self.request_delay_seconds = DEFAULT_REFRESH_REQUEST_DELAY_SECONDS
        else:
            self.request_delay_seconds = 0.0

        self.candidates_seen = 0
        self.already_cached = 0
        self.generated = 0
        self.would_generate = 0
        self.failures = 0
        self.unavailable = 0
        self.stopped_at_runtime_budget = False

    def _validate_settings(self) -> None:
        backend = (self.settings.thumbnail_storage_backend or "").lower()
        if backend != "hf_bucket":
            raise RuntimeError(
                "PWC_THUMBNAIL_STORAGE_BACKEND must be 'hf_bucket' to preload "
                f"thumbnails (current: {backend or 'unset'})"
            )
        if not (self.settings.thumbnail_hf_bucket_id or "").strip():
            raise RuntimeError(
                "PWC_THUMBNAIL_HF_BUCKET_ID is required to preload thumbnails"
            )
        if not (self.settings.hf_token or "").strip():
            raise RuntimeError(
                "PWC_HF_TOKEN is required to authenticate against the Hugging Face bucket"
            )

    def _local_cache_dir(self) -> Path:
        if self.settings.thumbnail_storage_backend.lower() == "hf_bucket":
            return Path(self.settings.thumbnail_temp_cache_dir)
        return Path(self.settings.thumbnail_cache_dir)

    def _existing_local_filenames(self) -> set:
        cache_dir = self._local_cache_dir()
        if not cache_dir.exists():
            return set()
        return {p.name for p in cache_dir.glob("*.jpg")}

    def _local_thumbnail_is_valid(self, filename: str) -> bool:
        """
        Treat a local cache hit as usable only when the file decodes as a JPEG
        of the expected generated width. Stale / truncated / wrong-size files
        must regenerate so visible papers don't keep a broken thumbnail.
        """
        return is_thumbnail_valid(self._local_cache_dir() / filename)

    def _iter_recent(self, session) -> Iterable[Candidate]:
        filters = [
            DBPaper.is_latest_version,
            DBPaper.arxiv_id.isnot(None),
            DBPaper.arxiv_id != "",
        ]
        if self.recent_days is not None and self.recent_days > 0:
            cutoff = datetime.utcnow().date() - timedelta(days=self.recent_days)
            filters.append(
                or_(
                    DBPaper.date_published.is_(None),
                    DBPaper.date_published >= cutoff,
                )
            )

        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(and_(*filters))
            .order_by(
                # Undated papers must not crowd dated recent papers out of --limit.
                DBPaper.date_published.desc().nullslast(),
                DBPaper.id.desc(),
            )
        )
        if self.limit is not None and self.limit > 0:
            query = query.limit(self.limit)

        for row in query.yield_per(self.batch_size):
            yield Candidate(row.id, row.arxiv_id, row.version or "v1")

    def _iter_trending(
        self, session, limit_override: Optional[int] = None
    ) -> Iterable[Candidate]:
        if limit_override is not None and limit_override > 0:
            effective_limit = limit_override
        elif self.limit and self.limit > 0:
            effective_limit = self.limit
        else:
            effective_limit = 1000

        sql = text("""
            WITH ranked AS (
                SELECT DISTINCT ON (tp.paper_id)
                    tp.paper_id,
                    tp.arxiv_id,
                    p.version,
                    tp.trending_score,
                    tp.current_stars
                FROM trending_papers_24h tp
                JOIN papers p ON p.id = tp.paper_id
                WHERE tp.paper_age_days <= :max_age_days
                  AND tp.arxiv_id IS NOT NULL
                  AND tp.arxiv_id <> ''
                ORDER BY tp.paper_id,
                         tp.trending_score DESC NULLS LAST,
                         tp.current_stars DESC
            )
            SELECT paper_id, arxiv_id, version
            FROM ranked
            ORDER BY trending_score DESC NULLS LAST, current_stars DESC
            LIMIT :limit
            """)
        rows = session.execute(
            sql,
            {
                "max_age_days": self.trending_max_age_days,
                "limit": effective_limit,
            },
        ).fetchall()
        for row in rows:
            yield Candidate(row[0], row[1], row[2] or "v1")

    def _iter_citation_top(
        self, session, limit_override: Optional[int] = None
    ) -> Iterable[Candidate]:
        """
        Top latest-version arXiv papers ordered by Semantic Scholar citation
        count, matching what /?order_by=citation_count exposes on the homepage.
        """
        effective_limit = (
            limit_override if limit_override is not None else self.citation_top
        )
        if effective_limit <= 0:
            return
        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(
                DBPaper.is_latest_version,
                DBPaper.arxiv_id.isnot(None),
                DBPaper.arxiv_id != "",
            )
            .order_by(
                DBPaper.citation_count.desc().nullslast(),
                DBPaper.id.desc(),
            )
            .limit(effective_limit)
        )
        for row in query.yield_per(self.batch_size):
            yield Candidate(row.id, row.arxiv_id, row.version or "v1")

    def _iter_visible(self, session) -> Iterable[Candidate]:
        """
        Union of every candidate set actually visible to users, ordered so the
        homepage feed is preloaded before per-task / per-method tails:

        1. top by citation count            (homepage feed: most cited)
        2. top trending                     (homepage feed: trending)
        3. top by date_published            (homepage feed: newest)
        4. top --per-task papers per task   (task pages, 3 sort tabs each)
        5. top --per-method papers per method (method pages, 3 sort tabs each)

        Deduplicated by paper_id so the same paper isn't generated twice
        within one run; the truncation by --limit happens afterwards in
        `_collect_candidates`, so any cap slices the lowest-visibility tail.
        """
        seen: set = set()
        sources: List[Iterable[Candidate]] = [
            self._iter_citation_top(session),
            self._iter_trending(session, limit_override=self.trending_top),
            self._iter_newest_top(session),
            self._iter_task_top(session),
            self._iter_method_top(session),
        ]
        for source in sources:
            for candidate in source:
                if candidate.paper_id in seen:
                    continue
                seen.add(candidate.paper_id)
                yield candidate

    def _iter_newest_top(
        self, session, limit_override: Optional[int] = None
    ) -> Iterable[Candidate]:
        """
        Top latest-version arXiv papers ordered by `date_published`, matching
        the "newest" sort tab on the homepage feed (and any other list view
        opened with ?order_by=date_published).
        """
        effective_limit = (
            limit_override if limit_override is not None else self.newest_top
        )
        if effective_limit <= 0:
            return
        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(
                DBPaper.is_latest_version,
                DBPaper.arxiv_id.isnot(None),
                DBPaper.arxiv_id != "",
            )
            .order_by(
                DBPaper.date_published.desc().nullslast(),
                DBPaper.id.desc(),
            )
            .limit(effective_limit)
        )
        for row in query.yield_per(self.batch_size):
            yield Candidate(row.id, row.arxiv_id, row.version or "v1")

    def _iter_task_top(self, session) -> Iterable[Candidate]:
        yield from self._iter_group_top(
            session,
            join_table="paper_tasks",
            per_group=self.per_task,
        )

    def _iter_method_top(self, session) -> Iterable[Candidate]:
        yield from self._iter_group_top(
            session,
            join_table="paper_methods",
            per_group=self.per_method,
        )

    def _iter_group_top(
        self,
        session,
        *,
        join_table: str,
        per_group: int,
    ) -> Iterable[Candidate]:
        """
        Top --per-group papers per task / method across the three sort tabs
        present on every list page (trending, newest, most cited). Returns the
        union of all three top-N subsets so the visible head of each tab gets
        warmed regardless of which sort the user lands on.
        """
        if join_table not in _GROUP_TOP_TABLES:
            raise ValueError(f"Unsupported join table {join_table!r}")
        if per_group <= 0:
            return

        group_col = _GROUP_TOP_TABLES[join_table]
        sql = text(f"""
            WITH scored AS (
                SELECT
                    pg.{group_col} AS group_id,
                    p.id           AS paper_id,
                    p.arxiv_id,
                    p.version,
                    p.date_published,
                    p.citation_count,
                    COALESCE(MAX(r.trending_score), 0) AS trending_score,
                    COALESCE(MAX(r.num_stars), 0)      AS stars
                FROM {join_table} pg
                JOIN papers p ON p.id = pg.paper_id
                LEFT JOIN paper_repositories pr
                  ON pr.paper_id = p.id AND pr.is_official = TRUE
                LEFT JOIN repositories r ON r.id = pr.repository_id
                WHERE p.is_latest_version
                  AND p.arxiv_id IS NOT NULL
                  AND p.arxiv_id <> ''
                GROUP BY pg.{group_col}, p.id, p.arxiv_id, p.version,
                         p.date_published, p.citation_count
            ), ranked AS (
                SELECT
                    paper_id, arxiv_id, version,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_id
                        ORDER BY trending_score DESC NULLS LAST,
                                 stars DESC NULLS LAST,
                                 date_published DESC NULLS LAST,
                                 paper_id DESC
                    ) AS rn_trending,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_id
                        ORDER BY date_published DESC NULLS LAST,
                                 paper_id DESC
                    ) AS rn_newest,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_id
                        ORDER BY citation_count DESC NULLS LAST,
                                 paper_id DESC
                    ) AS rn_citations
                FROM scored
            )
            SELECT DISTINCT ON (paper_id) paper_id, arxiv_id, version
            FROM ranked
            WHERE rn_trending  <= :per_group
               OR rn_newest    <= :per_group
               OR rn_citations <= :per_group
            ORDER BY paper_id
            """)
        rows = session.execute(sql, {"per_group": per_group}).fetchall()
        candidates = [Candidate(row[0], row[1], row[2] or "v1") for row in rows]
        if self.limit is not None and self.limit > 0:
            candidates = candidates[: self.limit]
        for candidate in candidates:
            yield candidate

    def _iter_missing_all(self, session) -> Iterable[Candidate]:
        filters = [
            DBPaper.is_latest_version,
            DBPaper.arxiv_id.isnot(None),
            DBPaper.arxiv_id != "",
        ]
        if self.after_id is not None:
            filters.append(DBPaper.id > self.after_id)
        if self.before_id is not None:
            filters.append(DBPaper.id < self.before_id)
        if self.shard is not None:
            shard_index, shard_total = self.shard
            filters.append(DBPaper.id % shard_total == shard_index)

        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(and_(*filters))
            .order_by(DBPaper.id.asc())
        )
        if self.limit is not None and self.limit > 0:
            query = query.limit(self.limit)

        for row in query.yield_per(self.batch_size):
            yield Candidate(row.id, row.arxiv_id, row.version or "v1")

    def _iter_external_missing(self, session) -> Iterable[Candidate]:
        filters = [
            DBPaper.is_latest_version,
            DBPaper.source == "external",
            DBPaper.source_url.isnot(None),
            DBPaper.source_url != "",
            or_(DBPaper.thumbnail_url.is_(None), DBPaper.thumbnail_url == ""),
        ]
        if self.after_id is not None:
            filters.append(DBPaper.id > self.after_id)
        if self.before_id is not None:
            filters.append(DBPaper.id < self.before_id)
        if self.shard is not None:
            shard_index, shard_total = self.shard
            filters.append(DBPaper.id % shard_total == shard_index)

        query = (
            session.query(
                DBPaper.id,
                DBPaper.source_url,
                DBPaper.thumbnail_url,
                DBPaper.title,
                DBPaper.conference_url_pdf,
            )
            .filter(and_(*filters))
            .order_by(DBPaper.date_published.desc().nullslast(), DBPaper.id.desc())
        )
        if self.limit is not None and self.limit > 0:
            query = query.limit(self.limit)

        for row in query.yield_per(self.batch_size):
            yield Candidate(
                paper_id=row.id,
                arxiv_id=None,
                version="external",
                source_url=row.source_url,
                thumbnail_url=row.thumbnail_url,
                title=row.title,
                pdf_url=row.conference_url_pdf,
            )

    def _candidate_thumbnail_filename(self, candidate: Candidate) -> str:
        if candidate.arxiv_id:
            return build_thumbnail_filename(candidate.arxiv_id, candidate.version)
        return build_external_thumbnail_filename(candidate.paper_id)

    def _persist_external_thumbnail_url(self, paper_id: int, filename: str) -> None:
        session = db_manager.session_local()
        try:
            paper = session.get(DBPaper, paper_id)
            if paper is not None:
                paper.thumbnail_url = build_custom_thumbnail_url(filename)
                session.commit()
        finally:
            session.close()

    def _collect_candidates(self, session) -> List[Candidate]:
        if self.priority == "visible":
            iterator = self._iter_visible(session)
        elif self.priority == "trending":
            iterator = self._iter_trending(session)
        elif self.priority == "task-top":
            iterator = self._iter_task_top(session)
        elif self.priority == "method-top":
            iterator = self._iter_method_top(session)
        elif self.priority == "missing-all":
            iterator = self._iter_missing_all(session)
        elif self.priority == "external-missing":
            iterator = self._iter_external_missing(session)
        else:
            iterator = self._iter_recent(session)

        raw = list(iterator)
        if self.priority == "visible" and self.limit and self.limit > 0:
            raw = raw[: self.limit]

        if (self.missing_only and self.priority != "external-missing") or (
            self.priority == "missing-all"
        ):
            filtered = [
                candidate
                for candidate in raw
                if not self._local_thumbnail_is_valid(
                    self._candidate_thumbnail_filename(candidate)
                )
            ]
            self.logger.info(
                "Missing-only filter: %d -> %d candidates "
                "(skipped %d already on disk with valid %dpx JPEG)",
                len(raw),
                len(filtered),
                len(raw) - len(filtered),
                EXPECTED_THUMBNAIL_WIDTH,
            )
            return filtered

        return raw

    async def _process_paper(
        self,
        thumbnail_service: ThumbnailService,
        candidate: Candidate,
    ) -> str:
        """Process one paper, returning a status: cached | generated | dry_run | failed."""
        filename = self._candidate_thumbnail_filename(candidate)
        active_cache_path = thumbnail_service._get_active_cache_path(filename)
        local_exists = active_cache_path.exists()
        local_invalid = local_exists and not is_thumbnail_valid(active_cache_path)

        if not self.refresh_existing and not local_invalid:
            if local_exists:
                if not candidate.arxiv_id:
                    self._persist_external_thumbnail_url(candidate.paper_id, filename)
                return "cached"

            if (
                not self.trust_local_cache
                and thumbnail_service._bucket_thumbnail_exists(filename)
            ):
                if not candidate.arxiv_id:
                    self._persist_external_thumbnail_url(candidate.paper_id, filename)
                return "cached"

        if self.dry_run:
            return "dry_run"

        force = self.refresh_existing or local_invalid
        if candidate.arxiv_id:
            await thumbnail_service.generate_thumbnail(
                candidate.arxiv_id, candidate.version, force=force
            )
        else:
            if not candidate.source_url:
                raise ThumbnailGenerationError("External paper has no source URL")
            await thumbnail_service.generate_external_thumbnail(
                candidate.paper_id,
                candidate.source_url,
                force=force,
                title=candidate.title,
                pdf_url=candidate.pdf_url,
            )
            self._persist_external_thumbnail_url(candidate.paper_id, filename)
        return "generated"

    async def _run_async(self) -> None:
        thumbnail_service = ThumbnailService()

        session = db_manager.session_local()
        try:
            candidates = self._collect_candidates(session)
        finally:
            session.close()

        total = len(candidates)
        self.logger.info(
            "Found %d candidate papers "
            "(priority=%s, limit=%s, recent_days=%s, per_task=%s, per_method=%s, "
            "citation_top=%s, trending_top=%s, newest_top=%s, "
            "after_id=%s, before_id=%s, shard=%s, missing_only=%s, "
            "trust_local_cache=%s, dry_run=%s, refresh_existing=%s, "
            "request_delay_seconds=%.1f)",
            total,
            self.priority,
            self.limit,
            self.recent_days,
            self.per_task if self.priority in ("task-top", "visible") else None,
            self.per_method if self.priority in ("method-top", "visible") else None,
            self.citation_top if self.priority == "visible" else None,
            self.trending_top if self.priority == "visible" else None,
            self.newest_top if self.priority == "visible" else None,
            self.after_id,
            self.before_id,
            f"{self.shard[0]}/{self.shard[1]}" if self.shard else None,
            self.missing_only,
            self.trust_local_cache,
            self.dry_run,
            self.refresh_existing,
            self.request_delay_seconds,
        )
        if total == 0:
            return

        start = time.time()
        for candidate in candidates:
            if (
                self.max_runtime_seconds is not None
                and time.time() - start >= self.max_runtime_seconds
            ):
                # Missing-only runs resume from what is still missing, so the
                # next run picks up the rest instead of the launcher timeout
                # killing this one mid-backlog.
                self.stopped_at_runtime_budget = True
                self.logger.warning(
                    "Stopping at --max-runtime-seconds=%.0f with %d/%d candidates "
                    "left; the next run resumes them",
                    self.max_runtime_seconds,
                    total - self.candidates_seen,
                    total,
                )
                break
            self.candidates_seen += 1

            try:
                status = await self._process_paper(thumbnail_service, candidate)
            except ThumbnailUnavailableError as exc:
                self.unavailable += 1
                self.logger.info(
                    "Thumbnail unavailable for paper %s (%s %s): %s",
                    candidate.paper_id,
                    candidate.arxiv_id or "external",
                    candidate.version,
                    exc,
                )
            except ThumbnailGenerationError as exc:
                self.failures += 1
                self.logger.warning(
                    "Failed to generate thumbnail for paper %s (%s %s): %s",
                    candidate.paper_id,
                    candidate.arxiv_id or "external",
                    candidate.version,
                    exc,
                )
            except Exception as exc:
                self.failures += 1
                self.logger.warning(
                    "Unexpected error for paper %s (%s %s): %s",
                    candidate.paper_id,
                    candidate.arxiv_id or "external",
                    candidate.version,
                    exc,
                )
            else:
                if status == "cached":
                    self.already_cached += 1
                elif status == "generated":
                    self.generated += 1
                    self.logger.info(
                        "Generated thumbnail for %s %s (paper_id=%s)",
                        candidate.arxiv_id or "external",
                        candidate.version,
                        candidate.paper_id,
                    )
                elif status == "dry_run":
                    self.would_generate += 1

            if self.candidates_seen % self.batch_size == 0:
                elapsed = time.time() - start
                self.logger.info(
                    "Progress: %d/%d processed, generated=%d, cached=%d, "
                    "would_generate=%d, failures=%d (%.1fs elapsed)",
                    self.candidates_seen,
                    total,
                    self.generated,
                    self.already_cached,
                    self.would_generate,
                    self.failures,
                    elapsed,
                )
                gc.collect()

            if (
                self.max_failures is not None
                and self.max_failures >= 0
                and self.failures > self.max_failures
            ):
                self.logger.error(
                    "Aborting: failures (%d) exceeded --max-failures=%d",
                    self.failures,
                    self.max_failures,
                )
                break

            if (
                self.request_delay_seconds > 0
                and not self.dry_run
                and self.candidates_seen < total
            ):
                await asyncio.sleep(self.request_delay_seconds)

    def run(self) -> None:
        self._validate_settings()
        self.logger.info(
            "Starting thumbnail preload job "
            "(priority=%s, bucket=%s, prefix=%s, dry_run=%s, "
            "refresh_existing=%s, missing_only=%s, trust_local_cache=%s, "
            "request_delay_seconds=%.1f)",
            self.priority,
            self.settings.thumbnail_hf_bucket_id,
            self.settings.thumbnail_hf_bucket_prefix,
            self.dry_run,
            self.refresh_existing,
            self.missing_only,
            self.trust_local_cache,
            self.request_delay_seconds,
        )

        asyncio.run(self._run_async())

        self.logger.info("Thumbnail preload finished:")
        self.logger.info("  - Candidates seen: %d", self.candidates_seen)
        self.logger.info("  - Already cached:  %d", self.already_cached)
        self.logger.info("  - Generated:       %d", self.generated)
        self.logger.info("  - Would generate:  %d", self.would_generate)
        self.logger.info("  - Unavailable:     %d", self.unavailable)
        self.logger.info("  - Failures:        %d", self.failures)
        self.logger.info(
            "THUMBNAIL_PRELOAD_SUMMARY %s",
            json.dumps(
                {
                    "candidates_seen": self.candidates_seen,
                    "already_cached": self.already_cached,
                    "generated": self.generated,
                    "would_generate": self.would_generate,
                    "unavailable_documents": self.unavailable,
                    "failed_downloads": self.failures,
                    "stopped_at_runtime_budget": self.stopped_at_runtime_budget,
                }
            ),
        )


def _parse_shard(value: str) -> Tuple[int, int]:
    if "/" not in value:
        raise argparse.ArgumentTypeError("expected --shard in the form i/n")
    left, right = value.split("/", 1)
    try:
        shard_index = int(left)
        shard_total = int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))
    if shard_total <= 0:
        raise argparse.ArgumentTypeError("shard total must be > 0")
    if not 0 <= shard_index < shard_total:
        raise argparse.ArgumentTypeError(
            f"shard index must be in [0, {shard_total - 1}]"
        )
    return shard_index, shard_total


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preload paper thumbnails into a Hugging Face bucket so they are "
            "warm before /api/thumbnails/{filename} is requested."
        )
    )
    parser.add_argument(
        "--priority",
        choices=VALID_PRIORITIES,
        default="recent",
        help=(
            "Which candidate set to process. 'visible' unions citation-top, "
            "trending-top, newest-top, per-task, and per-method papers (every "
            "user-visible surface) and deduplicates homepage-first. 'trending' "
            "uses the EMA trending_papers_24h view, 'task-top' takes the top "
            "--per-task papers per task tag across the trending/newest/cited "
            "sort tabs, 'method-top' does the same per method tag, 'recent' is "
            "newest-first (optionally constrained to --recent-days), and "
            "'missing-all' sweeps every latest-version ArXiv paper without a "
            "local thumbnail. 'external-missing' captures missing non-ArXiv "
            "thumbnails."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate papers to consider (default: all).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Logging / yield_per batch size (default: %(default)s).",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=None,
        help=(
            "Only consider papers published within the last N days "
            "(applies to --priority=recent). Papers without date_published "
            "are also included."
        ),
    )
    parser.add_argument(
        "--per-task",
        type=int,
        default=DEFAULT_PER_TASK,
        help=(
            "Top N papers per task to preload for --priority=task-top and "
            "--priority=visible. Each task contributes its top N papers from "
            "each of the three sort tabs (trending, newest, most cited). "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--per-method",
        type=int,
        default=DEFAULT_PER_METHOD,
        help=(
            "Top N papers per method to preload for --priority=method-top and "
            "--priority=visible. Each method contributes its top N papers from "
            "each of the three sort tabs (trending, newest, most cited). "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--trending-max-age-days",
        type=int,
        default=DEFAULT_TRENDING_MAX_AGE_DAYS,
        help=(
            "Maximum paper age (days) for --priority=trending candidates "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--citation-top",
        type=int,
        default=DEFAULT_CITATION_TOP,
        help=(
            "Top N papers by citation_count to include in --priority=visible "
            "(default: %(default)s). Pass 0 to skip the citation contribution."
        ),
    )
    parser.add_argument(
        "--trending-top",
        type=int,
        default=DEFAULT_TRENDING_TOP,
        help=(
            "Top N trending papers to include in --priority=visible "
            "(default: %(default)s). Pass 0 to skip the trending contribution."
        ),
    )
    parser.add_argument(
        "--newest-top",
        type=int,
        default=DEFAULT_NEWEST_TOP,
        help=(
            "Top N newest papers (by date_published) to include in "
            "--priority=visible, matching the homepage 'newest' sort tab "
            "(default: %(default)s). Pass 0 to skip the newest contribution."
        ),
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=None,
        help="Only consider papers with id > AFTER_ID (--priority=missing-all).",
    )
    parser.add_argument(
        "--before-id",
        type=int,
        default=None,
        help="Only consider papers with id < BEFORE_ID (--priority=missing-all).",
    )
    parser.add_argument(
        "--shard",
        type=_parse_shard,
        default=None,
        help=(
            "Process only papers where paper.id %% N == I, expressed as 'I/N' "
            "(--priority=missing-all)."
        ),
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help=(
            "Drop candidates whose thumbnail already exists in the local "
            "cache before processing. Implicit for --priority=missing-all."
        ),
    )
    parser.add_argument(
        "--trust-local-cache",
        action="store_true",
        help=(
            "Skip the per-paper HF bucket exists() probe. Safe when the "
            "mirror_thumbnails_to_disk cron is healthy and the local cache "
            "reflects bucket contents. Implicit for --priority=missing-all."
        ),
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=DEFAULT_MAX_FAILURES,
        help=(
            "Abort after this many failures (default: %(default)s). "
            "Pass a negative value to disable the cap."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be generated without downloading or uploading.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help=(
            "Regenerate and overwrite thumbnails even when a local or bucket "
            "object already exists."
        ),
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=None,
        help=(
            "Minimum delay between paper downloads. Defaults to "
            f"{DEFAULT_REFRESH_REQUEST_DELAY_SECONDS:g}s for --refresh-existing "
            "and 0 otherwise."
        ),
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=None,
        help=(
            "Stop starting new candidates after this many seconds of processing "
            "so a large backlog finishes across several runs within the "
            "launcher timeout. With --missing-only the next run resumes."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    job = ThumbnailPreloadJob(
        priority=args.priority,
        limit=args.limit,
        batch_size=args.batch_size,
        recent_days=args.recent_days,
        per_task=args.per_task,
        per_method=args.per_method,
        trending_max_age_days=args.trending_max_age_days,
        citation_top=args.citation_top,
        trending_top=args.trending_top,
        newest_top=args.newest_top,
        after_id=args.after_id,
        before_id=args.before_id,
        shard=args.shard,
        missing_only=args.missing_only,
        trust_local_cache=args.trust_local_cache,
        max_failures=args.max_failures,
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
        request_delay_seconds=args.request_delay_seconds,
        max_runtime_seconds=args.max_runtime_seconds,
    )
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
