"""Shared SQL expressions for the active, freshness-bounded paper score."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperRepository, Repository


def active_paper_score_components(
    db: Session,
    ranking_mode: str,
    *,
    cutoff: datetime | None = None,
    missing_score: float = 0.0,
):
    cutoff = cutoff or datetime.now(timezone.utc) - timedelta(hours=24)
    repo_stats = (
        db.query(
            PaperRepository.paper_id.label("paper_id"),
            func.max(Repository.num_stars).label("max_stars"),
            func.max(
                case(
                    (
                        Repository.trending_score_updated_at >= cutoff,
                        Repository.trending_score,
                    )
                )
            ).label("repo_trending_score"),
        )
        .join(Repository, PaperRepository.repository_id == Repository.id)
        .filter(PaperRepository.is_official.is_(True))
        .group_by(PaperRepository.paper_id)
        .subquery()
    )
    if ranking_mode == "composite":
        score = case(
            (
                Paper.trending_score_updated_at >= cutoff,
                func.coalesce(Paper.trending_score, missing_score),
            ),
            else_=missing_score,
        )
    else:
        score = func.coalesce(repo_stats.c.repo_trending_score, missing_score)
    return repo_stats, score


def correlated_paper_score_expressions(
    ranking_mode: str,
    *,
    cutoff: datetime | None = None,
    missing_score: float = 0.0,
):
    """Active score and best official star count as per-paper expressions.

    Equivalent to ``active_paper_score_components`` for ordering a scoped
    paper query, but each value is a scalar subquery correlated to
    ``Paper.id``. That uses the ``paper_repositories.paper_id`` index for only
    the papers in scope instead of aggregating every official repository, and
    counting the query (``order_by(None)``) skips the expressions entirely.
    """
    cutoff = cutoff or datetime.now(timezone.utc) - timedelta(hours=24)

    def official_repositories(column):
        return (
            select(column)
            .select_from(PaperRepository)
            .join(Repository, PaperRepository.repository_id == Repository.id)
            .where(
                PaperRepository.paper_id == Paper.id,
                PaperRepository.is_official.is_(True),
            )
            .correlate(Paper)
            .scalar_subquery()
        )

    max_stars = official_repositories(func.max(Repository.num_stars))
    if ranking_mode == "composite":
        score = case(
            (
                Paper.trending_score_updated_at >= cutoff,
                func.coalesce(Paper.trending_score, missing_score),
            ),
            else_=missing_score,
        )
    else:
        repo_score = official_repositories(
            func.max(
                case(
                    (
                        Repository.trending_score_updated_at >= cutoff,
                        Repository.trending_score,
                    )
                )
            )
        )
        score = func.coalesce(repo_score, missing_score)
    return score, max_stars
