"""
Thumbnail API router.

Provides endpoints for:
- Generating thumbnails for papers
- Serving cached thumbnails
- Managing thumbnail cache
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database.connection import db_manager, get_database_session
from backend.models.database import Paper as DBPaper
from backend.services.paper_service import PaperService
from backend.services.thumbnail_service import (
    ThumbnailService,
    build_custom_thumbnail_url,
)
from backend.utils.auth import require_admin
from backend.utils.exceptions import PaperNotFoundError

router = APIRouter(prefix="/thumbnails", tags=["thumbnails"])

MISSING_THUMBNAIL_HEADERS = {"Cache-Control": "no-store"}
THUMBNAIL_HEADERS = {
    "Cache-Control": "public, s-maxage=604800, max-age=604800",
}


def _thumbnail_response(path: Path) -> Response:
    """Return a concrete body so HTTP middleware cannot drop file-send frames."""
    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        headers=THUMBNAIL_HEADERS,
    )


def get_thumbnail_service() -> ThumbnailService:
    """Dependency to get thumbnail service instance."""
    return ThumbnailService()


@router.get("/custom/{filename}")
def serve_custom_thumbnail(
    filename: str, thumbnail_service: ThumbnailService = Depends(get_thumbnail_service)
):
    """
    Serve a manually captured thumbnail for non-ArXiv external resources.
    """
    try:
        thumbnail_path = thumbnail_service.get_existing_custom_thumbnail_path(filename)
        if thumbnail_path is None:
            raise HTTPException(
                status_code=404,
                detail="Thumbnail not available",
                headers=MISSING_THUMBNAIL_HEADERS,
            )
        return _thumbnail_response(thumbnail_path)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Thumbnail not available",
            headers=MISSING_THUMBNAIL_HEADERS,
        )


@router.get("/{filename}")
def serve_thumbnail(
    filename: str, thumbnail_service: ThumbnailService = Depends(get_thumbnail_service)
):
    """
    Serve a pre-loaded thumbnail file from the local cache.

    The request path is strictly on-disk: the local cache is kept in sync
    with the HF bucket by `mirror_thumbnails_to_disk`, and brand-new
    thumbnails are generated exclusively by the `preload_thumbnails` cron.
    User-facing requests never trigger PDF rasterisation or HF round-trips.
    """
    try:
        thumbnail_path = thumbnail_service.get_local_thumbnail_path(filename)
    except Exception:
        thumbnail_path = None

    if thumbnail_path is None:
        raise HTTPException(
            status_code=404,
            detail="Thumbnail not available",
            headers=MISSING_THUMBNAIL_HEADERS,
        )

    return _thumbnail_response(thumbnail_path)


@router.post("/generate/{paper_id}", dependencies=[Depends(require_admin)])
async def generate_thumbnail(
    paper_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database_session),
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Generate a thumbnail for a paper.

    Args:
        paper_id: ID of the paper to generate thumbnail for
        background_tasks: FastAPI background tasks
        db: Database session
        thumbnail_service: Thumbnail service instance

    Returns:
        Dictionary with thumbnail URL or generation status

    Raises:
        HTTPException: If paper not found or generation fails
    """
    try:
        # Get paper details
        paper_service = PaperService(db)
        paper = paper_service.get_paper_by_id(paper_id)

        if paper.source == "external":
            if not paper.source_url:
                raise HTTPException(
                    status_code=400,
                    detail="External paper does not have a source URL",
                )

            existing_url = (
                paper.thumbnail_url
                or thumbnail_service.get_external_thumbnail_url(paper.id)
            )
            if existing_url:
                # Hydration fills `paper.thumbnail_url` from disk, so check the
                # stored column on the ORM row rather than the API model.
                db_paper = db.get(DBPaper, int(paper.id))
                if db_paper is not None and not db_paper.thumbnail_url:
                    db_paper.thumbnail_url = existing_url
                    db.commit()
                return {
                    "thumbnail_url": existing_url,
                    "status": "cached",
                    "message": "Thumbnail already exists",
                }

            async def generate_external_in_background():
                try:
                    await thumbnail_service.generate_external_thumbnail(
                        paper.id,
                        paper.source_url,
                        title=paper.title,
                        pdf_url=paper.conference_url_pdf,
                    )
                    filename = thumbnail_service.get_external_filename(paper.id)
                    thumbnail_url = build_custom_thumbnail_url(filename)

                    session = db_manager.session_local()
                    try:
                        db_paper = session.get(DBPaper, paper.id)
                        if db_paper is not None:
                            db_paper.thumbnail_url = thumbnail_url
                            session.commit()
                    finally:
                        session.close()
                except Exception as e:
                    print(
                        f"Background external thumbnail generation failed for "
                        f"paper {paper.id}: {e}"
                    )

            background_tasks.add_task(generate_external_in_background)

            return {
                "thumbnail_url": None,
                "status": "generating",
                "message": "External thumbnail generation started in background",
            }

        if not paper.arxiv_id:
            raise HTTPException(
                status_code=400,
                detail="Paper does not have an ArXiv ID, cannot generate thumbnail",
            )

        # Check if thumbnail already exists
        existing_url = thumbnail_service.get_thumbnail_url(
            paper.arxiv_id, paper.version
        )
        if existing_url:
            return {
                "thumbnail_url": existing_url,
                "status": "cached",
                "message": "Thumbnail already exists",
            }

        # Generate thumbnail in background
        async def generate_in_background():
            try:
                await thumbnail_service.generate_thumbnail(
                    paper.arxiv_id, paper.version
                )
            except Exception as e:
                # Log error but don't fail the request
                print(
                    f"Background thumbnail generation failed for {paper.arxiv_id}: {e}"
                )

        background_tasks.add_task(generate_in_background)

        return {
            "thumbnail_url": None,
            "status": "generating",
            "message": "Thumbnail generation started in background",
        }

    except PaperNotFoundError:
        raise HTTPException(status_code=404, detail="Paper not found")


@router.get("/status/{paper_id}")
def get_thumbnail_status(
    paper_id: str,
    db: Session = Depends(get_database_session),
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Check if a thumbnail exists for a paper.

    Args:
        paper_id: ID of the paper to check
        db: Database session
        thumbnail_service: Thumbnail service instance

    Returns:
        Dictionary with thumbnail status and URL if available

    Raises:
        HTTPException: If paper not found
    """
    try:
        # Get paper details
        paper_service = PaperService(db)
        paper = paper_service.get_paper_by_id(paper_id)

        if paper.source == "external":
            thumbnail_url = (
                paper.thumbnail_url
                or thumbnail_service.get_external_thumbnail_url(paper.id)
            )
            return {
                "has_thumbnail": thumbnail_url is not None,
                "thumbnail_url": thumbnail_url,
                "source": paper.source,
                "source_url": paper.source_url,
            }

        if not paper.arxiv_id:
            return {
                "has_thumbnail": False,
                "thumbnail_url": None,
                "reason": "No ArXiv ID",
            }

        # Check if thumbnail exists
        thumbnail_url = thumbnail_service.get_thumbnail_url(
            paper.arxiv_id, paper.version
        )

        return {
            "has_thumbnail": thumbnail_url is not None,
            "thumbnail_url": thumbnail_url,
            "arxiv_id": paper.arxiv_id,
            "version": paper.version,
        }

    except PaperNotFoundError:
        raise HTTPException(status_code=404, detail="Paper not found")


@router.get("/cache/stats", dependencies=[Depends(require_admin)])
def get_cache_stats(
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Get thumbnail cache statistics (admin only).

    Returns:
        Dictionary with file count, size, and storage backend
    """
    return thumbnail_service.get_cache_stats()


@router.post("/cache/cleanup", dependencies=[Depends(require_admin)])
def cleanup_cache(
    max_age_days: int = Query(default=30, ge=1, le=3650),
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Clean up old cached thumbnails.

    Args:
        max_age_days: Maximum age in days for cached thumbnails

    Returns:
        Dictionary with cleanup results
    """
    try:
        deleted_count = thumbnail_service.cleanup_old_thumbnails(max_age_days)
        return {
            "deleted_count": deleted_count,
            "max_age_days": max_age_days,
            "message": f"Deleted {deleted_count} old thumbnails",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup cache: {str(e)}"
        )
