"""Method mention trends derived from the union of paper-method evidence."""

import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session

from backend.models.taxonomy import MethodTrend, MethodTrendPoint
from backend.models.database import Method as DBMethod
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperMethod
from backend.services.method_backfill_service import keyword_catalog_rows
from backend.services.paper_method_link_service import (
    method_history_start,
    month_start,
    shift_month,
)
from backend.services.catalog_errors import CatalogNotFoundError


# Catalog-wide monthly paper counts are identical for every method trend and
# cost a full scan of `papers`, so share them briefly across requests.
CATALOG_MONTH_COUNTS_TTL_SECONDS = 300
_catalog_month_counts: dict[tuple[str, date], tuple[float, dict[date, int]]] = {}


def postgres_catalog_month_counts(db: Session, generated_on: date) -> dict[date, int]:
    """Latest-version papers per publication month up to `generated_on`."""
    key = (str(db.get_bind().url), generated_on)
    cached = _catalog_month_counts.get(key)
    if cached and time.monotonic() - cached[0] < CATALOG_MONTH_COUNTS_TTL_SECONDS:
        return cached[1]
    counts = dict(
        db.execute(
            text("""
                SELECT date_trunc('month', date_published)::date AS month_start,
                       count(*) AS paper_count
                FROM papers
                WHERE is_latest_version
                  AND date_published <= :generated_on
                GROUP BY 1
                """),
            {"generated_on": generated_on},
        ).all()
    )
    _catalog_month_counts.clear()
    _catalog_month_counts[key] = (time.monotonic(), counts)
    return counts


class MethodTrendService:
    """Calculate complete, coverage-aware monthly method mention histories."""

    def __init__(self, db: Session):
        self.db = db

    def get_method_trend(
        self,
        method_id: str,
        *,
        recent_days: int = 90,
        baseline_days: int = 180,
        history_months: int | None = None,
        today: date | None = None,
    ) -> MethodTrend:
        method = self._resolve_method(method_id)
        generated_on = today or datetime.now(UTC).date()
        current_month = month_start(generated_on)
        history_start = method_history_start(self.db, method) or current_month
        if history_months is not None:
            history_start = shift_month(current_month, 1 - history_months)
        actual_history_months = (
            (current_month.year - history_start.year) * 12
            + current_month.month
            - history_start.month
            + 1
        )
        recent_start = generated_on - timedelta(days=recent_days)
        baseline_start = recent_start - timedelta(days=baseline_days)
        query_start = min(history_start, baseline_start)

        # paper_methods is unique per (paper, method), so the join yields each
        # paper once; no DISTINCT needed.
        rows = (
            self.db.query(DBPaper.date_published)
            .join(PaperMethod, PaperMethod.paper_id == DBPaper.id)
            .filter(
                PaperMethod.method_id == method.id,
                DBPaper.is_latest_version,
                DBPaper.date_published >= query_start,
                DBPaper.date_published <= generated_on,
            )
            .all()
        )
        undated_count = (
            self.db.query(func.count())
            .select_from(DBPaper)
            .join(PaperMethod, PaperMethod.paper_id == DBPaper.id)
            .filter(
                PaperMethod.method_id == method.id,
                DBPaper.is_latest_version,
                DBPaper.date_published.is_(None),
            )
            .scalar()
            or 0
        )
        counts: dict[date, int] = {}
        recent_count = baseline_count = 0
        for (published_on,) in rows:
            bucket = month_start(published_on)
            counts[bucket] = counts.get(bucket, 0) + 1
            if published_on > recent_start:
                recent_count += 1
            elif published_on > baseline_start:
                baseline_count += 1

        if self.db.bind.dialect.name == "sqlite":
            catalog = {}
            catalog_rows = (
                self.db.query(DBPaper.id, DBPaper.date_published)
                .filter(
                    DBPaper.is_latest_version,
                    DBPaper.date_published >= history_start,
                    DBPaper.date_published <= generated_on,
                )
                .all()
            )
            for _paper_id, published_on in catalog_rows:
                bucket = month_start(published_on)
                catalog[bucket] = catalog.get(bucket, 0) + 1
        else:
            catalog = {
                month: count
                for month, count in postgres_catalog_month_counts(
                    self.db, generated_on
                ).items()
                if month >= history_start
            }
        coverage_available = self.db.bind.dialect.name == "postgresql" and inspect(
            self.db.bind
        ).has_table("method_reference_backfill_months")
        coverage: dict[date, tuple] = {}
        keyword_complete = False
        if coverage_available:
            coverage = {
                row.month_start: row
                for row in self.db.execute(
                    text("""
                        SELECT month_start, status, eligible_papers, processed_papers,
                               unresolvable_papers, retryable_failures
                        FROM method_reference_backfill_months
                        WHERE method_id = :method_id
                          AND month_start BETWEEN :history_start AND :current_month
                        """),
                    {
                        "method_id": method.id,
                        "history_start": history_start,
                        "current_month": current_month,
                    },
                ).all()
            }
            keyword_digest, _methods = keyword_catalog_rows(self.db)
            keyword_complete = bool(
                self.db.execute(
                    text(
                        "SELECT 1 FROM method_keyword_backfill_runs "
                        "WHERE keyword_catalog_sha256 = :digest "
                        "AND status = 'complete' LIMIT 1"
                    ),
                    {"digest": keyword_digest},
                ).first()
            )

        history: list[MethodTrendPoint] = []
        reference_complete = True
        comparison_reference_complete = True
        comparison_start = max(history_start, month_start(baseline_start))
        for index in range(actual_history_months):
            start = shift_month(history_start, index)
            catalog_count = int(catalog.get(start, 0))
            paper_count = counts.get(start, 0)
            row = coverage.get(start)
            if method.source_paper_id and coverage_available:
                eligible = catalog_count
                processed = (
                    int(row.processed_papers + row.unresolvable_papers) if row else 0
                )
                complete = bool(
                    row
                    and row.status == "complete"
                    and row.retryable_failures == 0
                    and row.eligible_papers == eligible
                    and processed >= eligible
                )
                status = (
                    "complete"
                    if complete
                    else (
                        str(row.status)
                        if row and row.status != "complete"
                        else "pending"
                    )
                )
                reference_complete = reference_complete and complete
                if start >= comparison_start:
                    comparison_reference_complete = (
                        comparison_reference_complete and complete
                    )
                ratio = (
                    min(1.0, processed / eligible)
                    if eligible
                    else (1.0 if complete else 0.0)
                )
            else:
                eligible = processed = 0
                status = "not_applicable"
                ratio = None
            history.append(
                MethodTrendPoint(
                    start_date=start,
                    end_date=min(
                        generated_on, shift_month(start, 1) - timedelta(days=1)
                    ),
                    paper_count=paper_count,
                    eligible_paper_count=eligible,
                    processed_paper_count=processed,
                    coverage_ratio=round(ratio, 4) if ratio is not None else None,
                    coverage_status=status,
                    catalog_paper_count=catalog_count,
                    catalog_share=(
                        round(100.0 * paper_count / catalog_count, 4)
                        if catalog_count
                        else 0.0
                    ),
                )
            )

        history_complete = (
            keyword_complete
            and (reference_complete if method.source_paper_id else True)
            if coverage_available
            else True
        )
        comparison_complete = (
            keyword_complete
            and (comparison_reference_complete if method.source_paper_id else True)
            if coverage_available
            else True
        )
        recent_velocity = recent_count * 30.0 / recent_days
        baseline_velocity = baseline_count * 30.0 / baseline_days
        return MethodTrend(
            method_id=method.id,
            method_slug=method.slug,
            recent_days=recent_days,
            baseline_days=baseline_days,
            history_months=actual_history_months,
            generated_on=generated_on,
            recent_paper_count=recent_count,
            baseline_paper_count=baseline_count,
            trend_score=round(recent_velocity, 4) if comparison_complete else 0.0,
            rate_change=(
                round(recent_velocity / baseline_velocity, 4)
                if comparison_complete and baseline_velocity
                else None
            ),
            history=history,
            undated_paper_count=undated_count,
            history_complete=history_complete,
            comparison_complete=comparison_complete,
            current_month_is_partial=True,
        )

    def _resolve_method(self, method_id: str) -> DBMethod:
        if str(method_id).isdigit():
            method = (
                self.db.query(DBMethod).filter(DBMethod.id == int(method_id)).first()
            )
        else:
            method = (
                self.db.query(DBMethod)
                .filter(
                    or_(
                        func.lower(DBMethod.slug) == str(method_id).lower(),
                        func.lower(DBMethod.name) == str(method_id).lower(),
                    )
                )
                .order_by(DBMethod.id)
                .first()
            )
        if method is None:
            raise CatalogNotFoundError(
                f"Method with ID, slug, or name '{method_id}' not found"
            )
        return method
