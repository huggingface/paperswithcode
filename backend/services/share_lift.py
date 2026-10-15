"""
Rank taxonomy entities by how over-indexed they are in recent papers.

Shared by trending tasks and trending methods. For each entity with enough
support, computes::

    recent_share   = entity_recent_papers   / all_recent_papers
    baseline_share = entity_baseline_papers / all_baseline_papers
    share_lift     = recent_share / baseline_share
    trend_score    = share_lift * ln(1 + entity_recent_papers)

The recent window is the last ``recent_days``; the baseline window is the
``baseline_days`` immediately preceding it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import Float, and_, case, cast, desc, func
from sqlalchemy.orm import InstrumentedAttribute, Session

from backend.models.database import Paper as DBPaper


@dataclass(frozen=True)
class ShareLiftRow:
    entity: Any
    recent_paper_count: int
    baseline_paper_count: int
    share_lift: float
    trend_score: float


def rank_by_share_lift(
    db: Session,
    entity: Any,
    link_entity_id: InstrumentedAttribute,
    link_paper_id: InstrumentedAttribute,
    *,
    limit: int,
    recent_days: int,
    baseline_days: int,
    min_recent_papers: int,
    min_baseline_papers: int,
    min_share_lift: float,
    today: date,
    filters: Iterable[Any] = (),
) -> list[ShareLiftRow]:
    """
    Return up to ``limit`` entities sorted by descending share lift.

    ``link_entity_id`` and ``link_paper_id`` are the two columns of the
    paper/entity junction table (for example ``PaperTask.task_id`` and
    ``PaperTask.paper_id``). Entities below the ``min_recent_papers`` /
    ``min_baseline_papers`` / ``min_share_lift`` gates are dropped so noisy
    or shrinking entities never surface; ``trend_score`` breaks ties.
    """
    recent_start = today - timedelta(days=recent_days)
    baseline_start = recent_start - timedelta(days=baseline_days)

    # Combined window predicate: only consider latest-version papers published
    # anywhere between baseline_start and today. Pushing this into the WHERE
    # clause lets Postgres skip the bulk of `papers` and the matching junction
    # rows before aggregation instead of discarding them inside a CASE.
    in_window = and_(
        DBPaper.is_latest_version,
        DBPaper.date_published > baseline_start,
        DBPaper.date_published <= today,
    )
    in_recent = and_(
        DBPaper.date_published > recent_start,
        DBPaper.date_published <= today,
    )
    in_baseline = and_(
        DBPaper.date_published > baseline_start,
        DBPaper.date_published <= recent_start,
    )

    totals_row = (
        db.query(
            func.count(case((in_recent, DBPaper.id))).label("all_recent"),
            func.count(case((in_baseline, DBPaper.id))).label("all_baseline"),
        )
        .filter(in_window)
        .one()
    )
    all_recent = int(totals_row.all_recent or 0)
    all_baseline = int(totals_row.all_baseline or 0)
    if all_recent == 0 or all_baseline == 0:
        return []

    recent_count_expr = func.count(case((in_recent, DBPaper.id)))
    baseline_count_expr = func.count(case((in_baseline, DBPaper.id)))

    # Express the ranking maths in SQL so Postgres can filter, sort and LIMIT
    # server-side. `all_recent`/`all_baseline` are known non-zero scalars, so:
    #   share_lift  = (recent * all_baseline) / (baseline * all_recent)
    # The min_baseline_papers gate (>= 1) guarantees baseline_count > 0. Casts
    # force float (not integer) division.
    share_lift_expr = (cast(recent_count_expr, Float) * float(all_baseline)) / (
        cast(baseline_count_expr, Float) * float(all_recent)
    )
    trend_score_expr = share_lift_expr * func.ln(1.0 + recent_count_expr)

    query = (
        db.query(
            entity,
            recent_count_expr.label("recent_count"),
            baseline_count_expr.label("baseline_count"),
            share_lift_expr.label("share_lift"),
            trend_score_expr.label("trend_score"),
        )
        .join(link_entity_id.class_, link_entity_id == entity.id)
        .join(DBPaper, DBPaper.id == link_paper_id)
        .filter(in_window, *filters)
        .group_by(entity.id)
        .having(recent_count_expr >= min_recent_papers)
        .having(baseline_count_expr >= min_baseline_papers)
        .having(share_lift_expr > min_share_lift)
        .order_by(desc("share_lift"), desc("trend_score"))
        .limit(limit)
    )
    return [
        ShareLiftRow(
            entity=row_entity,
            recent_paper_count=int(recent_count or 0),
            baseline_paper_count=int(baseline_count or 0),
            share_lift=float(share_lift),
            trend_score=float(trend_score),
        )
        for row_entity, recent_count, baseline_count, share_lift, trend_score in query.all()
    ]
