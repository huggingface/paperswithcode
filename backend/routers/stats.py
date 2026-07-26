"""Public aggregate statistics endpoints."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import TrendsResponse
from backend.services.research_trends_service import ResearchTrendsService


router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "/trends",
    response_model=TrendsResponse,
    summary="Get monthly research trends",
)
def get_research_trends(
    response: Response,
    db: Session = Depends(get_database_session),
) -> TrendsResponse:
    """Return official-code and Hugging Face artifact coverage by month."""
    response.headers["Cache-Control"] = (
        "public, max-age=3600, stale-while-revalidate=86400"
    )
    return ResearchTrendsService(db).get_trends()
