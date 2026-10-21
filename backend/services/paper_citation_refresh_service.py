"""Citation refresh selection, orchestration, and persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from backend.models.database import Paper as DBPaper
from backend.services.semantic_scholar_service import SemanticScholarService
from backend.utils.exceptions import DatabaseError


class PaperCitationRefreshService:
    """Own Semantic Scholar refresh workflows shared by HTTP and cron callers."""

    def __init__(self, db: Session):
        self.db = db

    async def update_citation_counts(self, limit: int = 100) -> dict[str, Any]:
        """Refresh a bounded batch and return the public endpoint result."""
        try:
            updated_count = await SemanticScholarService(
                self.db
            ).batch_update_citation_counts(limit)
            return {
                "updated_count": updated_count,
                "limit": limit,
                "status": "completed",
            }
        except Exception as error:  # noqa: BLE001 - preserve HTTP error translation
            raise DatabaseError(f"Error updating citation counts: {error}")

    def count_pending(self, threshold_days: int = 7) -> int:
        """Return the number of ArXiv papers whose citations need refreshing."""
        try:
            threshold_date = datetime.now() - timedelta(  # noqa: DTZ005
                days=threshold_days
            )
            return (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .count()
            )
        except Exception as error:  # noqa: BLE001 - normalize database failures
            raise DatabaseError(
                f"Error counting papers needing citation updates: {error}"
            )

    def count_refreshable(self) -> int:
        """Return every ArXiv paper the hourly refresh cycles through."""
        return (
            self.db.query(DBPaper)
            .filter(DBPaper.is_latest_version)
            .filter(DBPaper.arxiv_id.is_not(None))
            .count()
        )

    def refresh_ahead_chunk(
        self, limit: int, threshold_days: int = 7
    ) -> list[dict[str, Any]]:
        """Return not-yet-due papers whose citations were refreshed longest ago.

        Refreshing them early in quiet hours spreads a weekly wave of papers
        refreshed on the same days across the whole cycle.
        """
        threshold_date = datetime.now() - timedelta(  # noqa: DTZ005
            days=threshold_days
        )
        papers = (
            self.db.query(DBPaper)
            .filter(DBPaper.is_latest_version)
            .filter(DBPaper.arxiv_id.is_not(None))
            .filter(DBPaper.citation_updated_at >= threshold_date)
            .order_by(DBPaper.citation_updated_at.asc(), DBPaper.id.asc())
            .limit(limit)
            .all()
        )
        return [self._pending_projection(paper) for paper in papers]

    def pending_chunk(
        self, offset: int, limit: int, threshold_days: int = 7
    ) -> list[dict[str, Any]]:
        """Return one priority-ordered projection for the hourly refresh job."""
        try:
            threshold_date = datetime.now() - timedelta(  # noqa: DTZ005
                days=threshold_days
            )
            priority_order = case(
                (DBPaper.citation_updated_at.is_(None), 0),
                (DBPaper.citation_count == 0, 1),
                else_=2,
            )
            year_priority = case(
                (func.extract("year", DBPaper.date_published).between(2019, 2022), 1),
                (func.extract("year", DBPaper.date_published).between(2017, 2018), 2),
                (func.extract("year", DBPaper.date_published).between(2023, 2024), 3),
                else_=4,
            )
            papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .order_by(
                    priority_order,
                    year_priority,
                    DBPaper.citation_updated_at.asc().nullsfirst(),
                    DBPaper.id.asc(),
                )
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._pending_projection(paper) for paper in papers]
        except Exception as error:  # noqa: BLE001 - normalize database failures
            raise DatabaseError(
                f"Error fetching papers chunk for citation updates: {error}"
            )

    @staticmethod
    def _pending_projection(paper: DBPaper) -> dict[str, Any]:
        return {
            "id": paper.id,
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "citation_count": paper.citation_count or 0,
            "citation_updated_at": paper.citation_updated_at,
            "date_published": paper.date_published,
            "priority_type": (
                "NEVER_UPDATED"
                if paper.citation_updated_at is None
                else ("ZERO_CITATIONS" if paper.citation_count == 0 else "REFRESH")
            ),
        }

    def update_batch(self, citation_updates: list[dict[str, Any]]) -> dict[str, int]:
        """Persist a batch of Semantic Scholar results in one transaction."""
        try:
            stats = {"updated": 0, "failed": 0}
            for update in citation_updates:
                try:
                    paper = (
                        self.db.query(DBPaper)
                        .filter(DBPaper.id == update["paper_id"])
                        .first()
                    )
                    if paper is None:
                        stats["failed"] += 1
                        continue

                    if update.get("success", True) and update.get(
                        "semantic_scholar_id"
                    ):
                        paper.citation_count = update["citation_count"]
                        paper.semantic_scholar_id = update["semantic_scholar_id"]
                        stats["updated"] += 1
                    else:
                        stats["failed"] += 1

                    paper.citation_updated_at = func.now()
                    paper.updated_at = func.now()
                except Exception as error:  # noqa: BLE001 - preserve per-row progress
                    print(
                        f"Error updating paper {update.get('paper_id', 'unknown')}: "
                        f"{error}"
                    )
                    stats["failed"] += 1

            self.db.commit()
            return stats
        except Exception as error:  # noqa: BLE001 - guarantee transaction rollback
            self.db.rollback()
            raise DatabaseError(f"Error updating citation counts batch: {error}")

    def statistics(self) -> dict[str, Any]:
        """Return aggregate citation-refresh coverage statistics."""
        try:
            latest_papers = self.db.query(DBPaper).filter(DBPaper.is_latest_version)
            total_papers = latest_papers.count()
            papers_processed = latest_papers.filter(
                DBPaper.citation_updated_at.is_not(None)
            ).count()
            papers_with_citations = latest_papers.filter(
                DBPaper.citation_count > 0
            ).count()

            return {
                "total_papers": total_papers,
                "papers_processed": papers_processed,
                "papers_with_citations": papers_with_citations,
                "processed_percentage": round(
                    papers_processed / total_papers * 100 if total_papers else 0, 1
                ),
                "citations_percentage": round(
                    papers_with_citations / total_papers * 100 if total_papers else 0,
                    1,
                ),
            }
        except Exception as error:  # noqa: BLE001 - normalize database failures
            raise DatabaseError(f"Error getting citation statistics: {error}")
