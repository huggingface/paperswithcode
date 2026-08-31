"""
FastAPI router for conference endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.routers.paper_date_range import PaperDateRange, get_paper_date_range
from backend.models.api import (
    Conference,
    ConferenceAreasWithTasks,
    ConferenceDeadlines,
    Conferences,
)
from backend.models.papers import Papers
from backend.services.conference_service import ConferenceService
from backend.utils.exceptions import PaperNotFoundError
from backend.utils.entity_images import (
    IMAGE_CACHE_HEADERS,
    IMAGE_MISSING_HEADERS,
)

router = APIRouter(prefix="/conferences", tags=["conferences"])


@router.get(
    "/",
    response_model=Conferences,
    summary="List all conferences",
)
def get_conferences(
    db: Session = Depends(get_database_session),
):
    return ConferenceService(db).get_conferences()


@router.get(
    "/deadlines",
    response_model=ConferenceDeadlines,
    summary="List conferences with their submission deadlines",
)
def get_conference_deadlines(
    db: Session = Depends(get_database_session),
):
    return ConferenceService(db).get_conference_deadlines()


@router.get(
    "/{slug}",
    response_model=Conference,
    summary="Get conference details",
)
def get_conference(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    db: Session = Depends(get_database_session),
):
    return ConferenceService(db).lookup_conference(slug)


@router.get(
    "/{slug}/image",
    summary="Serve the DB-backed conference hero image",
)
def get_conference_image(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    db: Session = Depends(get_database_session),
):
    """
    Serve the DB-backed hero image for a conference by slug.

    Returns the raw image bytes stored in `conferences.image_data`. 404s when
    the conference does not exist or has no stored image.
    """
    try:
        data, mime = ConferenceService(db).get_image(slug)
    except PaperNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Image not available",
            headers=IMAGE_MISSING_HEADERS,
        )
    return Response(content=data, media_type=mime, headers=IMAGE_CACHE_HEADERS)


@router.get(
    "/{slug}/areas-with-tasks",
    response_model=ConferenceAreasWithTasks,
    summary="Get conference taxonomy grouped by area and task",
)
def get_conference_areas_with_tasks(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    db: Session = Depends(get_database_session),
):
    return ConferenceService(db).get_conference_areas_with_tasks(slug)


@router.get(
    "/{slug}/papers",
    response_model=Papers,
    summary="List papers for a conference, optionally filtered by task",
)
def get_conference_papers(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    task: Optional[str] = Query(
        None, description="Optional task slug to filter papers"
    ),
    presentation: Optional[str] = Query(
        None,
        description=(
            "Optional presentation tier filter: oral, spotlight, outstanding, "
            "or best_paper_finalist"
        ),
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Papers per page"),
    latest_only: bool = Query(True, description="Only include latest paper versions"),
    order_by: str = Query(
        "date_published",
        description="Sort field: date_published, title, citation_count, trending",
    ),
    order_dir: str = Query("desc", description="Sort direction: asc or desc"),
    include_resources: bool = Query(
        False, description="Include repositories and tasks on each paper"
    ),
    has_code: bool = Query(
        False, description="Only include papers with a linked GitHub repository"
    ),
    has_hf_artifacts: bool = Query(
        False, description="Only include papers with linked Hugging Face artifacts"
    ),
    date_range: PaperDateRange = Depends(get_paper_date_range),
    db: Session = Depends(get_database_session),
):
    return ConferenceService(db).lookup_conference_papers(
        slug=slug,
        task_slug=task,
        presentation=presentation,
        page=page,
        page_size=page_size,
        latest_only=latest_only,
        order_by=order_by,
        order_dir=order_dir,
        include_resources=include_resources,
        has_code=has_code,
        has_hf_artifacts=has_hf_artifacts,
        start_date=date_range.start_date,
        end_date=date_range.end_date,
    )
