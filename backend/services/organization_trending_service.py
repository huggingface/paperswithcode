"""Daily raw snapshots and rolling 30-day organization momentum."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Organization,
    OrganizationTrendingHistory,
    Paper,
    PaperOrganization,
)
from backend.services.sitemap_service import eligible_paper_filter
from backend.services.trending_ranking_service import active_paper_score_components

ROLLING_DAYS = 30
RETENTION_DAYS = 120
# Organizations with at least this many public papers are featured automatically.
AUTO_FEATURE_MIN_PAPERS = 25


class OrganizationTrendingService:
    def __init__(self, db: Session):
        self.db = db

    def calculate(self, snapshot_date: date | None = None) -> dict[str, int]:
        snapshot_date = snapshot_date or datetime.now(timezone.utc).date()
        newly_featured = self._feature_established_organizations()
        repo_stats, active_score = active_paper_score_components(
            self.db, get_settings().trending_ranking_mode
        )
        score_rows = (
            self.db.query(
                Organization.id,
                func.coalesce(func.sum(active_score), 0.0).label("raw_score"),
            )
            .outerjoin(
                PaperOrganization,
                PaperOrganization.organization_id == Organization.id,
            )
            .outerjoin(
                Paper,
                (Paper.id == PaperOrganization.paper_id) & Paper.is_latest_version,
            )
            .outerjoin(repo_stats, repo_stats.c.paper_id == Paper.id)
            .filter(Organization.is_featured.is_(True))
            .group_by(Organization.id)
            .all()
        )
        now = datetime.now(timezone.utc)
        for organization_id, raw_score in score_rows:
            snapshot = (
                self.db.query(OrganizationTrendingHistory)
                .filter(
                    OrganizationTrendingHistory.organization_id == organization_id,
                    OrganizationTrendingHistory.snapshot_date == snapshot_date,
                )
                .first()
            )
            if snapshot is None:
                snapshot = OrganizationTrendingHistory(
                    organization_id=organization_id,
                    snapshot_date=snapshot_date,
                    raw_score=float(raw_score or 0),
                )
                self.db.add(snapshot)
            else:
                snapshot.raw_score = float(raw_score or 0)

        # Repository sessions disable autoflush, so make today's upserts visible
        # to the rolling query in this same transaction.
        self.db.flush()
        rolling_start = snapshot_date - timedelta(days=ROLLING_DAYS - 1)
        rolling_rows = (
            self.db.query(
                OrganizationTrendingHistory.organization_id,
                func.avg(OrganizationTrendingHistory.raw_score),
            )
            .filter(
                OrganizationTrendingHistory.snapshot_date >= rolling_start,
                OrganizationTrendingHistory.snapshot_date <= snapshot_date,
            )
            .group_by(OrganizationTrendingHistory.organization_id)
            .all()
        )
        for organization_id, rolling_score in rolling_rows:
            self.db.query(Organization).filter(
                Organization.id == organization_id
            ).update(
                {
                    Organization.trending_score: float(rolling_score or 0),
                    Organization.trending_score_updated_at: now,
                },
                synchronize_session=False,
            )
        deleted = (
            self.db.query(OrganizationTrendingHistory)
            .filter(
                OrganizationTrendingHistory.snapshot_date
                < snapshot_date - timedelta(days=RETENTION_DAYS)
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {
            "snapshots": len(score_rows),
            "history_pruned": deleted,
            "newly_featured": newly_featured,
        }

    def _feature_established_organizations(self) -> int:
        """Feature every organization with enough public papers; never unfeature."""
        established = (
            self.db.query(PaperOrganization.organization_id)
            .join(Paper, Paper.id == PaperOrganization.paper_id)
            .filter(eligible_paper_filter())
            .group_by(PaperOrganization.organization_id)
            .having(func.count(func.distinct(Paper.id)) >= AUTO_FEATURE_MIN_PAPERS)
        )
        return (
            self.db.query(Organization)
            .filter(
                Organization.is_featured.is_(False),
                Organization.id.in_(established),
            )
            .update({Organization.is_featured: True}, synchronize_session=False)
        )
