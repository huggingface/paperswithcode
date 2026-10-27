"""
FastAPI router for organization endpoints.
"""

import hashlib
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.routers.paper_date_range import PaperDateRange, get_paper_date_range
from backend.models.organizations import (
    Organization,
    OrganizationAreasWithTasks,
    OrganizationContributions,
    OrganizationSyncRequest,
    OrganizationSyncResult,
    Organizations,
)
from backend.models.papers import Papers
from backend.services.organization_service import OrganizationService
from backend.services.catalog_errors import CatalogNotFoundError
from backend.services.organization_sync_service import OrganizationSyncService
from backend.services.hf_organization_service import HFOrganizationError
from backend.utils.auth import require_catalog_mutator
from backend.utils.organization_logos import organization_logo_extension

router = APIRouter(prefix="/organizations", tags=["organizations"])

VERSIONED_LOGO_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "CDN-Cache-Control": "public, max-age=31536000, immutable",
}
COMPAT_LOGO_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=0, must-revalidate",
    "CDN-Cache-Control": "public, max-age=0, must-revalidate",
}


@router.get(
    "/",
    response_model=Organizations,
    summary="List all organizations",
)
def get_organizations(
    featured_only: bool = Query(
        False, description="Return only the curated featured organizations"
    ),
    db: Session = Depends(get_database_session),
):
    return OrganizationService(db).get_organizations(featured_only=featured_only)


@router.get(
    "/index/cards",
    response_model=Organizations,
    summary="List curated organization cards for the public directory",
)
def get_organization_index(db: Session = Depends(get_database_session)):
    return OrganizationService(db).get_organization_index()


@router.post(
    "/sync",
    response_model=OrganizationSyncResult,
    dependencies=[Depends(require_catalog_mutator)],
    summary="Synchronize an organization and its papers from Hugging Face",
)
async def sync_organization(
    payload: OrganizationSyncRequest,
    db: Session = Depends(get_database_session),
):
    service = OrganizationSyncService(db)
    try:
        stats = await service.sync_hf_slug(
            payload.hf_slug,
            slug=payload.slug,
            skip_missing_papers=payload.skip_missing_papers,
        )
        return stats.to_dict()
    except (HFOrganizationError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        service.close()


@router.get(
    "/{slug}",
    response_model=Organization,
    summary="Get organization details",
)
def get_organization(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    return OrganizationService(db).get_organization(slug)


@router.get(
    "/{slug}/contributions",
    response_model=OrganizationContributions,
    summary="Get daily paper contributions for an organization",
)
def get_organization_contributions(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    return OrganizationService(db).get_organization_contributions(slug)


def _organization_logo_response(
    request: Request,
    slug: str,
    db: Session,
    extension: str | None = None,
    digest: str | None = None,
):
    try:
        logo_data, logo_mime_type = OrganizationService(db).get_logo(slug)
    except CatalogNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Logo not available",
            headers={"Cache-Control": "no-store"},
        )
    expected_extension = organization_logo_extension(logo_mime_type)
    if extension is not None and extension != expected_extension:
        raise HTTPException(status_code=404, detail="Logo format not available")

    actual_digest = hashlib.sha256(logo_data).hexdigest()
    if digest is not None and digest != actual_digest:
        raise HTTPException(status_code=404, detail="Logo version not available")

    etag = f'"{actual_digest}"'
    cache_headers = (
        VERSIONED_LOGO_CACHE_HEADERS if digest else COMPAT_LOGO_CACHE_HEADERS
    )
    headers = {**cache_headers, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=logo_data,
        media_type=logo_mime_type,
        headers=headers,
    )


@router.get("/{slug}/logo", summary="Serve the cached organization logo")
def get_organization_logo(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    """Compatibility route for logo URLs emitted before extension caching."""
    return _organization_logo_response(request, slug, db)


@router.get(
    "/{slug}/logo/{digest}.{extension}",
    summary="Serve an immutable version of the cached organization logo",
)
def get_versioned_organization_logo(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    digest: str = Path(..., min_length=64, max_length=64),
    extension: str = Path(..., description="Cached logo file extension"),
    db: Session = Depends(get_database_session),
):
    return _organization_logo_response(
        request,
        slug,
        db,
        extension.lower(),
        digest.lower(),
    )


@router.get(
    "/{slug}/logo.{extension}",
    summary="Serve a compatibility organization logo URL",
)
def get_organization_logo_with_extension(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    extension: str = Path(..., description="Cached logo file extension"),
    db: Session = Depends(get_database_session),
):
    return _organization_logo_response(request, slug, db, extension.lower())


@router.get(
    "/{slug}/areas-with-tasks",
    response_model=OrganizationAreasWithTasks,
    summary="Get organization taxonomy grouped by area and task",
)
def get_organization_areas_with_tasks(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    return OrganizationService(db).get_organization_areas_with_tasks(slug)


@router.get(
    "/{slug}/papers",
    response_model=Papers,
    summary="List papers for an organization, optionally filtered by task",
)
def get_organization_papers(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    task: Optional[str] = Query(
        None, description="Optional task slug to filter papers"
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
    return OrganizationService(db).get_organization_papers(
        slug=slug,
        task_slug=task,
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
