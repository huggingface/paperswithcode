"""
User-scoped bookmark endpoints.

All endpoints below require a valid ``pwc_session`` cookie. Existing database
bookmarks remain readable until the user opts into a private Hugging Face
Bucket. After migration, database rows are retained as a compatibility mirror.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.papers import Paper as ApiPaper
from backend.services.bookmark_service import (
    BookmarkPaperNotFoundError,
    BookmarkService,
)
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    PaperBucketError,
)
from backend.utils.auth import require_user

router = APIRouter(prefix="/me", tags=["bookmarks"])


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class BookmarkIdsResponse(BaseModel):
    paper_ids: list[int] = Field(
        default_factory=list,
        description="IDs of papers bookmarked by the current user",
    )


class SavedTaskGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(None, description="Task ID, NULL for the 'Untagged' bucket")
    slug: str | None = Field(
        None, description="Task slug, NULL for the 'Untagged' bucket"
    )
    name: str = Field(..., description="Task display name")
    papers: list[ApiPaper] = Field(default_factory=list)


class SavedAreaGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(None, description="Area ID, NULL for the 'Other' bucket")
    name: str = Field(..., description="Area display name")
    tasks: list[SavedTaskGroup] = Field(default_factory=list)


class SavedPapersResponse(BaseModel):
    count: int = Field(..., description="Total number of bookmarked papers")
    areas: list[SavedAreaGroup] = Field(default_factory=list)
    bucket_connected: bool = Field(
        False,
        description="Whether the response was read from the user's HF Bucket",
    )
    bucket_migrated: bool = Field(
        False,
        description=(
            "Whether the account's saved papers were already migrated to an HF "
            "Bucket on any device; when true but not connected, this browser "
            "only needs to reconnect"
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _bucket_error(error: PaperBucketError) -> HTTPException:
    if error.authorization_required:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "saved_papers_bucket_authorization_required",
                "message": str(error),
            },
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get(
    "/bookmarks/ids",
    response_model=BookmarkIdsResponse,
    summary="List the current user's bookmarked paper IDs",
)
def get_my_bookmark_ids(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> BookmarkIdsResponse:
    """Return just the IDs (cheap; used to hydrate the Save button state)."""

    listing = BookmarkService(db).list_refs(
        encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
        hf_user_id=user["hf_user_id"],
        username=user["username"],
    )
    return BookmarkIdsResponse(paper_ids=[item.paper_id for item in listing.refs])


@router.get(
    "/bookmarks",
    response_model=SavedPapersResponse,
    summary="List the current user's bookmarked papers grouped by area and task",
)
def get_my_bookmarks(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> SavedPapersResponse:
    """Return all bookmarks for the user, grouped by Area and then Task.

    Each paper is classified using its primary task (the row in ``paper_tasks``
    with the lowest ``task_id``). Papers without any tagged task land in a
    catch-all ``Other / Untagged`` bucket.
    """

    projection = BookmarkService(db).list_grouped(
        encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
        hf_user_id=user["hf_user_id"],
        username=user["username"],
    )
    areas = [
        SavedAreaGroup(
            id=area.id,
            name=area.name,
            tasks=[
                SavedTaskGroup(
                    id=task.id,
                    slug=task.slug,
                    name=task.name,
                    papers=list(task.papers),
                )
                for task in area.tasks
            ],
        )
        for area in projection.areas
    ]
    return SavedPapersResponse(
        count=projection.count,
        areas=areas,
        bucket_connected=projection.bucket_connected,
        bucket_migrated=projection.bucket_migrated,
    )


@router.post(
    "/bookmarks/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add the given paper to the current user's bookmarks",
)
def add_bookmark(
    request: Request,
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    try:
        BookmarkService(db).add_bookmark(
            paper_id=paper_id,
            encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
            hf_user_id=user["hf_user_id"],
            username=user["username"],
        )
    except BookmarkPaperNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found"
        ) from None
    except PaperBucketError as error:
        raise _bucket_error(error) from error


@router.delete(
    "/bookmarks/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the given paper from the current user's bookmarks",
)
def remove_bookmark(
    request: Request,
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    try:
        BookmarkService(db).remove_bookmark(
            paper_id=paper_id,
            encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
            hf_user_id=user["hf_user_id"],
            username=user["username"],
        )
    except PaperBucketError as error:
        raise _bucket_error(error) from error
