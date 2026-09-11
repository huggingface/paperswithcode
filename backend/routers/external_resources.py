"""
HTTP endpoints for ingesting external (non-ArXiv) resources.

External resources are vendor blog posts, technical reports, model release
pages, and similar content that should appear alongside ArXiv papers but
do not have an ArXiv identifier. They are stored in the same `papers` table
with `source='external'` and a populated `source_url`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.papers import Paper
from backend.services.external_resource_service import (
    ExternalResourceError,
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.utils.exceptions import DatabaseError
from backend.utils.auth import require_admin


logger = logging.getLogger(__name__)
router = APIRouter()


class ExternalResourceCreateRequest(BaseModel):
    """Manual ingestion payload (no AI extraction)."""

    source_url: str = Field(..., description="Canonical URL for the external page")
    title: str = Field(..., description="Display title")
    abstract: Optional[str] = Field(None, description="Optional summary/abstract text")
    authors: List[str] = Field(
        default_factory=list,
        description=(
            "Human author names. May be empty for organization-authored posts."
        ),
    )
    date_published: date = Field(
        ...,
        description=(
            "Publication date (YYYY-MM-DD). Required: external rows are not "
            "indexed without a credible date because feeds and trending rely "
            "on it."
        ),
    )
    thumbnail_url: Optional[str] = Field(
        None,
        description=(
            "Optional thumbnail image URL. Manually captured external-resource "
            "thumbnails can use /api/thumbnails/custom/<file>.jpg."
        ),
    )
    github_repository_urls: List[str] = Field(
        default_factory=list,
        description=(
            "GitHub repos linked directly from the page. Stored as official "
            "for the resulting paper."
        ),
    )
    hf_artifact_urls: List[str] = Field(
        default_factory=list,
        description=(
            "Hugging Face model/dataset/space URLs linked from the page. "
            "Categorized and stored on `papers.hf_models`, `papers.hf_datasets`, "
            "and `papers.hf_spaces` respectively."
        ),
    )


class ExternalResourceFromUrlRequest(BaseModel):
    """AI-assisted ingestion payload."""

    source_url: str = Field(..., description="Canonical URL for the external page")
    date_published: Optional[date] = Field(
        None,
        description=(
            "Optional manual override. If extraction cannot determine a date "
            "and this field is also missing, ingestion is rejected."
        ),
    )
    title_override: Optional[str] = Field(None, description="Manual title override")
    abstract_override: Optional[str] = Field(
        None, description="Manual abstract override"
    )
    authors_override: Optional[List[str]] = Field(
        None,
        description="Manual author list (replaces extracted authors when provided)",
    )
    thumbnail_url: Optional[str] = Field(
        None,
        description=(
            "Optional thumbnail image URL. Manually captured external-resource "
            "thumbnails can use /api/thumbnails/custom/<file>.jpg."
        ),
    )


class ExternalResourceIngestionResponse(BaseModel):
    """Result of an ingestion operation."""

    paper: Paper
    repositories_added: int
    repositories_existing: int
    hf_models_added: int
    hf_datasets_added: int
    hf_spaces_added: int
    hf_artifacts_existing: int
    authors_added: int
    authors_existing: int


@router.post(
    "/papers/external",
    response_model=ExternalResourceIngestionResponse,
    summary="Create or update an external (non-ArXiv) paper row",
    dependencies=[Depends(require_admin)],
)
def create_external_resource(
    request: ExternalResourceCreateRequest = Body(...),
    db: Session = Depends(get_database_session),
):
    """Create an external-resource row from explicit caller-supplied fields."""
    try:
        service = ExternalResourceService(db)
        payload = ExternalResourceInput(
            source_url=request.source_url,
            title=request.title,
            abstract=request.abstract,
            authors=list(request.authors or []),
            date_published=request.date_published,
            thumbnail_url=request.thumbnail_url,
            github_repository_urls=list(request.github_repository_urls or []),
            hf_artifact_urls=list(request.hf_artifact_urls or []),
        )
        result = service.add_external_resource(payload)
    except ExternalResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ExternalResourceIngestionResponse(
        paper=result.paper,
        repositories_added=result.repositories_added,
        repositories_existing=result.repositories_existing,
        hf_models_added=result.hf_models_added,
        hf_datasets_added=result.hf_datasets_added,
        hf_spaces_added=result.hf_spaces_added,
        hf_artifacts_existing=result.hf_artifacts_existing,
        authors_added=result.authors_added,
        authors_existing=result.authors_existing,
    )


@router.post(
    "/papers/external/from-url",
    response_model=ExternalResourceIngestionResponse,
    summary="Fetch and ingest an external page using AI metadata extraction",
    dependencies=[Depends(require_admin)],
)
async def create_external_resource_from_url(
    request: ExternalResourceFromUrlRequest = Body(...),
    db: Session = Depends(get_database_session),
):
    """
    Fetch the supplied URL, extract title/abstract/authors/date and linked
    GitHub/HF artifacts via the LLM, and ingest the resulting external row.

    Ingestion is rejected when no credible publication date can be determined
    (per the plan: external rows must have a date populated).
    """
    try:
        service = ExternalResourceService(db)
        result = await service.add_from_url(
            source_url=request.source_url,
            date_published=request.date_published,
            title_override=request.title_override,
            abstract_override=request.abstract_override,
            authors_override=request.authors_override,
            thumbnail_url=request.thumbnail_url,
        )
    except ExternalResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ExternalResourceIngestionResponse(
        paper=result.paper,
        repositories_added=result.repositories_added,
        repositories_existing=result.repositories_existing,
        hf_models_added=result.hf_models_added,
        hf_datasets_added=result.hf_datasets_added,
        hf_spaces_added=result.hf_spaces_added,
        hf_artifacts_existing=result.hf_artifacts_existing,
        authors_added=result.authors_added,
        authors_existing=result.authors_existing,
    )
