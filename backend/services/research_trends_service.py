"""Database aggregation for the public research trends page."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.api import TrendPoint, TrendsResponse
from backend.utils.exceptions import DatabaseError


CODE_SERIES_START = date(2019, 1, 1)
HF_SERIES_START = date(2021, 1, 1)

_MONTHLY_TRENDS_QUERY = text(
    """
    SELECT
        date_trunc('month', p.date_published)::date AS month,
        COUNT(*) AS paper_count,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM paper_repositories pr
                WHERE pr.paper_id = p.id
                  AND pr.is_official = TRUE
            )
        ) AS official_code_count,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM paper_hf_artifacts pha
                WHERE pha.paper_id = p.id
            )
            OR COALESCE(cardinality(p.hf_models), 0) > 0
            OR COALESCE(cardinality(p.hf_datasets), 0) > 0
            OR COALESCE(cardinality(p.hf_spaces), 0) > 0
        ) AS hf_artifact_count
    FROM papers p
    WHERE p.is_latest_version
      AND p.source = 'arxiv'
      AND p.date_published >= :start_date
      AND p.date_published < :end_date
    GROUP BY 1
    ORDER BY 1
    """
)


class ResearchTrendsService:
    """Calculate monthly research trends from the current catalog."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _current_month(today: date) -> date:
        return today.replace(day=1)

    @staticmethod
    def _point(month: date, numerator: int, denominator: int) -> TrendPoint:
        return TrendPoint(
            month=month.strftime("%Y-%m"),
            percent=round((numerator * 100.0) / denominator, 1),
        )

    def get_trends(self, *, today: date | None = None) -> TrendsResponse:
        """Return complete-month trend series using publication month."""
        today = today or date.today()
        end_date = self._current_month(today)

        try:
            rows = (
                self.db.execute(
                    _MONTHLY_TRENDS_QUERY,
                    {"start_date": CODE_SERIES_START, "end_date": end_date},
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as error:
            raise DatabaseError(
                f"Failed to calculate research trends: {error}"
            ) from error

        code_availability = []
        hf_artifacts = []
        for row in rows:
            month = row["month"]
            paper_count = int(row["paper_count"])
            if paper_count <= 0:
                continue

            code_availability.append(
                self._point(
                    month,
                    int(row["official_code_count"]),
                    paper_count,
                )
            )
            if month >= HF_SERIES_START:
                hf_artifacts.append(
                    self._point(
                        month,
                        int(row["hf_artifact_count"]),
                        paper_count,
                    )
                )

        return TrendsResponse(
            code_availability=code_availability,
            hf_artifacts=hf_artifacts,
        )
