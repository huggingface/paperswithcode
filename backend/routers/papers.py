"""
FastAPI router for paper endpoints.

This module provides all paper-related API endpoints that match the
original PapersWithCode API specification.
"""

import logging
from datetime import date
from typing import Optional, List, Literal
from urllib.parse import quote, urlencode

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.routers.paper_date_range import PaperDateRange, get_paper_date_range
from backend.models.papers import (
    Paper,
    Papers,
    PaperSummary,
    PaperSearchResults,
    PaperSearchFeedResults,
    PaperLookupRequest,
    PaperLookupResponse,
    RelatedPaperRecommendation,
    PaperVersions,
    VersionComparison,
    PaperBucketCopyRequest,
    PaperBucketCopyResponse,
    RepositoryTrendingPaper,
    PaperSuggestedQuestionsResponse,
)
from backend.services.paper_suggested_questions_service import (
    get_suggested_questions,
)
from backend.services.paper_service import (
    AmbiguousAuthorError,
    InvalidAuthorFilterError,
    MAX_AUTHOR_FILTERS,
    PaperService,
)
from backend.services.paper_reference_service import PaperReferenceService
from backend.services.x_trending_service import XTrendingService
from backend.models.x_trending import XTrendingDayInput, XTrendingDayResult
from backend.models.public_paper_metadata import PublicPaperMetadata
from backend.services.public_paper_metadata_service import (
    PublicMetadataError,
    PublicPaperMetadataService,
)
from backend.services.badge_service import (
    render_leaderboard_badge,
    resolve_leaderboard_badge_target,
)
from backend.services.paper_ingestion_service import (
    PaperIngestionError,
    PaperIngestionService,
)
from backend.utils.auth import (
    catalog_mutation_context,
    has_session,
    require_admin,
    require_contributor,
    require_user,
)
from backend.services.paper_curation_service import PaperCurationService
from backend.services.paper_submission_service import (
    PaperSubmissionArxivMetadataError,
    PaperSubmissionCommand,
    PaperSubmissionDatabaseError,
    PaperSubmissionForbiddenError,
    PaperSubmissionInternalError,
    PaperSubmissionRateLimitError,
    PaperSubmissionService,
    PaperSubmissionValidationError,
)
from backend.services.hf_inference_billing_service import decrypt_oauth_credential
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    BUCKET_OAUTH_COOKIE_NAME,
    HubArtifact,
    PaperBucketError,
    copy_paper_to_bucket,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.client_ip import get_proxied_client_ip
from backend.utils.public_urls import normalize_public_url
from backend.utils.urls import (
    get_paper_route_identifier,
    validate_arxiv_id,
    validate_version,
)


logger = logging.getLogger(__name__)
router = APIRouter()

BADGE_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Cloudflare-CDN-Cache-Control": "no-store",
}


@router.post(
    "/papers/{paper_id}/copy-to-bucket",
    response_model=PaperBucketCopyResponse,
    summary="Copy a paper PDF and Hub artifacts to the signed-in user's Bucket",
)
def copy_paper_artifacts_to_bucket(
    payload: PaperBucketCopyRequest,
    request: Request,
    paper_id: str = Path(..., description="ArXiv ID or internal database ID"),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    encrypted = (
        request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME)
        if payload.create
        else request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME)
        or request.cookies.get(BUCKET_OAUTH_COOKIE_NAME)
    )
    credential = (
        decrypt_oauth_credential(encrypted, user["hf_user_id"], get_settings())
        if encrypted
        else None
    )
    if credential is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "bucket_authorization_required",
                "message": "Authorize Papers With Code to write to your Hugging Face Buckets.",
            },
        )

    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(paper_id)
        result = copy_paper_to_bucket(
            token=credential.token,
            bucket_id=payload.bucket_id.strip(),
            create=payload.create,
            private=payload.private,
            artifacts=[
                HubArtifact(kind=artifact.kind, repo_id=artifact.repo_id)
                for artifact in payload.artifacts
            ],
            pdf_url=paper.url_pdf if payload.include_pdf else None,
            pdf_name=paper.arxiv_id.replace("/", "-") if paper.arxiv_id else None,
        )
    except PaperNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PaperBucketError as error:
        if error.authorization_required:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "bucket_authorization_required",
                    "message": str(error),
                },
            ) from error
        raise HTTPException(status_code=400, detail=str(error)) from error

    return PaperBucketCopyResponse(
        bucket_id=payload.bucket_id.strip(),
        copied=list(result.copied),
        errors=[
            {"artifact": artifact, "message": message}
            for artifact, message in result.errors
        ],
    )


def _curated_paper_update(
    db: Session,
    mutation: dict,
    paper_id: int,
    section: str,
    payload: dict,
):
    return PaperCurationService(db).update(
        paper_id=paper_id,
        section=section,
        payload=payload,
        **mutation,
    )


@router.get("/papers/{paper_id}/curation-state")
def get_paper_curation_state(
    paper_id: int,
    _actor: dict = Depends(require_contributor),
    db: Session = Depends(get_database_session),
):
    return PaperCurationService(db).state(paper_id)


@router.get(
    "/papers/{paper_id}/suggested-questions",
    response_model=PaperSuggestedQuestionsResponse,
    summary="Get starter questions to ask the assistant about a paper",
)
def get_paper_suggested_questions(
    request: Request,
    paper_id: int = Path(..., description="Internal paper database ID"),
    db: Session = Depends(get_database_session),
):
    """
    Return three short questions about the paper, written by a small LLM from
    its title and abstract. Generated on a signed-in reader's first request and
    stored; returns an empty list when none are stored yet for an anonymous
    reader or they cannot be generated right now.
    """
    return PaperSuggestedQuestionsResponse(
        questions=get_suggested_questions(db, paper_id, generate=has_session(request))
    )


@router.get(
    "/papers/{paper_id}/badge.svg",
    response_class=Response,
    summary="Get a paper's leaderboard ranking badge",
)
@router.get(
    "/papers/{paper_id}/leaderboard-badge.svg",
    response_class=Response,
    include_in_schema=False,
)
def get_paper_leaderboard_badge(
    paper_id: str = Path(..., description="ArXiv ID or internal database ID"),
    evaluation_id: Optional[int] = Query(
        None,
        alias="eval",
        description="Render only the badge for this evaluation row",
    ),
    db: Session = Depends(get_database_session),
):
    """Return an embeddable SVG summarizing this paper's top-three rankings."""
    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(paper_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ranks = paper.leaderboard_ranks or []
    if evaluation_id is not None:
        target = resolve_leaderboard_badge_target(
            db,
            paper_id=int(paper.id),
            evaluation_id=evaluation_id,
        )
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=f"Evaluation {evaluation_id} not found for this paper",
            )
        ranks = [target.placement]

    return Response(
        content=render_leaderboard_badge(ranks),
        media_type="image/svg+xml",
        headers={
            **BADGE_CACHE_HEADERS,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/papers/{paper_id}/leaderboard-badge-link",
    response_class=RedirectResponse,
    include_in_schema=False,
)
def get_paper_leaderboard_badge_link(
    paper_id: str = Path(..., description="ArXiv ID or internal database ID"),
    evaluation_id: int = Query(..., alias="eval"),
    db: Session = Depends(get_database_session),
):
    """Redirect a durable badge link to its live row or paper results."""
    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(paper_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    target = resolve_leaderboard_badge_target(
        db,
        paper_id=int(paper.id),
        evaluation_id=evaluation_id,
    )
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Evaluation {evaluation_id} not found for this paper",
        )

    if target.evaluation_id is not None and target.dataset_slug and target.task_slug:
        query = urlencode({"task": target.task_slug, "eval": str(target.evaluation_id)})
        location = f"/benchmark/{quote(target.dataset_slug, safe='')}?{query}"
    else:
        route_id = get_paper_route_identifier(
            paper.source,
            paper.arxiv_id,
            int(paper.id),
        )
        location = f"/paper/{quote(route_id, safe='')}#results"

    return RedirectResponse(
        url=location,
        status_code=307,
        headers=BADGE_CACHE_HEADERS,
    )


@router.get("/papers", response_model=Papers, include_in_schema=False)
@router.get(
    "/papers/",
    response_model=Papers,
    summary="Get papers with pagination and filtering",
)
def get_papers(
    page: int = Query(1, ge=1, le=100, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of papers per page"
    ),
    search: Optional[str] = Query(None, description="Search term for title/abstract"),
    conference: Optional[str] = Query(None, description="Filter by conference"),
    task: Optional[str] = Query(
        None, description="Filter by an exact task name, slug, or ID"
    ),
    method: Optional[str] = Query(
        None, description="Filter by an exact method name, full name, slug, or ID"
    ),
    organization: Optional[str] = Query(
        None, description="Filter by an exact organization name, slug, or ID"
    ),
    authors: Optional[List[str]] = Query(
        None,
        alias="author",
        description=(
            "Repeatable exact author name, numeric author ID, or @HF username"
        ),
    ),
    latest_only: bool = Query(
        True, description="Whether to only include latest versions of papers"
    ),
    order_by: Literal["trending", "date_published", "citation_count"] = Query(
        "trending", description="Field to order by"
    ),
    order_dir: Literal["asc", "desc"] = Query("desc", description="Order direction"),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    has_code: bool = Query(
        False, description="Only include papers with a linked GitHub repository"
    ),
    has_official_implementation: bool = Query(
        False,
        description=(
            "Only include papers with a catalog-linked official implementation"
        ),
    ),
    has_hf_artifacts: bool = Query(
        False, description="Only include papers with linked Hugging Face artifacts"
    ),
    framework: Optional[str] = Query(
        None, description="Filter by an exact framework name, slug, or ID"
    ),
    repository: Optional[str] = Query(
        None, description="Filter by GitHub owner/name or repository URL"
    ),
    date_range: PaperDateRange = Depends(get_paper_date_range),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of papers with optional filtering and searching.

    This endpoint provides comprehensive paper listing functionality with:
    - Pagination support
    - Full-text search in titles and abstracts
    - Date range filtering
    - Conference filtering
    - Sorting options
    - Latest version filtering
    """
    if framework is not None and repository is not None:
        raise HTTPException(
            status_code=422,
            detail="framework and repository are mutually exclusive",
        )
    if authors is not None and len(authors) > MAX_AUTHOR_FILTERS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_AUTHOR_FILTERS} author filters are allowed",
        )
    try:
        service = PaperService(db)
        return service.get_papers(
            page=page,
            page_size=page_size,
            search=search,
            start_date=date_range.start_date,
            end_date=date_range.end_date,
            conference=conference,
            task=task,
            method=method,
            organization=organization,
            authors=authors,
            latest_only=latest_only,
            order_by=order_by,
            order_dir=order_dir,
            include_resources=include_resources,
            has_code=has_code,
            has_official_implementation=has_official_implementation,
            has_hf_artifacts=has_hf_artifacts,
            framework=framework,
            repository=repository,
        )
    except AmbiguousAuthorError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ambiguous_author",
                "reference": error.reference,
                "candidates": [
                    {
                        "id": str(candidate.id),
                        "name": candidate.name,
                        "hf_username": candidate.hf_username,
                    }
                    for candidate in error.candidates
                ],
            },
        ) from error
    except InvalidAuthorFilterError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/papers/search",
    response_model=PaperSearchResults,
    summary="Search latest papers by title, abstract, or ArXiv ID",
)
def search_papers(
    q: str = Query(..., min_length=1, max_length=300, description="Search query"),
    page: int = Query(1, ge=1, le=100, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Papers per page"),
    mode: Optional[Literal["keyword", "semantic", "hybrid"]] = Query(
        None, description="Override the configured search mode for this request"
    ),
    has_official_implementation: bool = Query(
        False,
        description=(
            "Only include papers with a catalog-linked official implementation"
        ),
    ),
    date_range: PaperDateRange = Depends(get_paper_date_range),
    db: Session = Depends(get_database_session),
):
    """
    Search latest paper versions and return one relevance-ranked page.

    ``PWC_PAPER_SEARCH_MODE`` sets the default to keyword, semantic, or hybrid.
    The optional ``mode`` parameter provides an explicit per-request override.
    Keyword search uses weighted PostgreSQL FTS; semantic search uses pgvector;
    hybrid search fuses both rankings with RRF. Endpoint cold starts, timeouts,
    and malformed vectors fall back immediately to keyword search.
    """
    service = PaperService(db)
    return service.search_papers_page(
        q,
        page,
        page_size,
        mode=mode,
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        has_official_implementation=has_official_implementation,
    )


@router.get(
    "/papers/search/feed",
    response_model=PaperSearchFeedResults,
    summary="Browse a hydrated page from the top paper search results",
)
def search_papers_feed(
    q: str = Query(..., min_length=1, max_length=300, description="Search query"),
    page: int = Query(1, ge=1, le=5, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=20, description="Papers per page"),
    order_by: Literal["relevance", "date_published", "citation_count"] = Query(
        "relevance", description="Ordering within the fixed relevant pool"
    ),
    mode: Literal["keyword", "semantic", "hybrid"] = Query(
        "hybrid", description="Requested retrieval mode"
    ),
    has_code: bool = Query(False, description="Only include papers with code"),
    has_hf_artifacts: bool = Query(
        False, description="Only include papers with Hugging Face artifacts"
    ),
    date_range: PaperDateRange = Depends(get_paper_date_range),
    db: Session = Depends(get_database_session),
):
    """Apply filters before retrieval, then reorder one capped candidate pool."""
    return PaperService(db).search_papers_feed(
        q,
        page=page,
        page_size=page_size,
        order_by=order_by,
        mode=mode,
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        has_code=has_code,
        has_hf_artifacts=has_hf_artifacts,
    )


@router.get(
    "/papers/x-trending",
    response_model=Papers,
    summary="Papers trending on X, ordered by trending score",
)
def get_x_trending_papers(
    page: int = Query(1, ge=1, le=100, description="Page number (1-based)"),
    page_size: int = Query(30, ge=1, le=100, description="Papers per page"),
    start_date: Optional[date] = Query(
        None, description="Inclusive earliest publication date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive latest publication date (YYYY-MM-DD)"
    ),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    has_code: bool = Query(
        False, description="Only include papers with a linked GitHub repository"
    ),
    has_hf_artifacts: bool = Query(
        False, description="Only include papers with linked Hugging Face artifacts"
    ),
    db: Session = Depends(get_database_session),
):
    """List papers from the daily "AI Papers on X" picks.

    Like the homepage trending feed, the date window filters on publication
    date and papers are ordered by the same trending score.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422, detail="start_date must be on or before end_date"
        )
    return XTrendingService(db).feed(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        include_resources=include_resources,
        has_code=has_code,
        has_hf_artifacts=has_hf_artifacts,
    )


@router.put(
    "/papers/x-trending/{shared_on}",
    response_model=XTrendingDayResult,
    summary="Replace one day's papers trending on X",
    dependencies=[Depends(require_admin)],
)
async def put_x_trending_day(
    payload: XTrendingDayInput,
    shared_on: date = Path(..., description="Day the papers were shared (YYYY-MM-DD)"),
    db: Session = Depends(get_database_session),
):
    """Store one sheet tab. Missing arXiv papers are imported first."""
    return await XTrendingService(db).replace_day(shared_on, payload.papers)


@router.post(
    "/papers/lookup",
    response_model=PaperLookupResponse,
    summary="Match bibliography entries to catalog papers",
)
def lookup_papers(
    payload: PaperLookupRequest,
    db: Session = Depends(get_database_session),
):
    """
    Resolve a batch of PDF bibliography entries in one round trip.

    Each entry is matched by its explicit arXiv identifier when it has one,
    otherwise by an exact letters-and-digits fingerprint of one of its
    candidate title strings. Entries without a confident match return
    ``paper: null``; the endpoint never guesses from authors or venues.
    """
    return PaperReferenceService(db).resolve(payload.references)


@router.get(
    "/papers/recent", response_model=List[PaperSummary], summary="Get recent papers"
)
def get_recent_papers(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of papers"),
    db: Session = Depends(get_database_session),
):
    """
    Get recently published papers.

    Returns the most recently published papers (latest versions only)
    ordered by publication date.
    """
    service = PaperService(db)
    return service.get_recent_papers(limit)


@router.get(
    "/papers/{paper_id}/related",
    response_model=List[RelatedPaperRecommendation],
    summary="Get embedding-ranked related papers with a task fallback",
)
def get_related_papers(
    paper_id: str = Path(..., description="ArXiv ID or internal paper ID"),
    limit: int = Query(4, ge=1, le=20),
    db: Session = Depends(get_database_session),
):
    """Return latest-version recommendations without synchronous model inference."""
    try:
        return PaperService(db).get_related_papers(paper_id, limit)
    except PaperNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/papers/stats", summary="Get paper statistics")
def get_paper_stats(db: Session = Depends(get_database_session)):
    """
    Get statistics about the papers in the database.

    Returns information about:
    - Total number of papers
    - Papers by publication year
    - Latest paper date
    - Version distribution
    """
    service = PaperService(db)
    return service.get_paper_stats()


@router.get(
    "/papers/trending",
    response_model=List[RepositoryTrendingPaper],
    summary="Get trending papers based on GitHub star velocity",
)
def get_trending_papers(
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of trending papers"
    ),
    max_age_days: int = Query(
        180, ge=1, le=365, description="Maximum paper age in days"
    ),
    min_velocity: Optional[float] = Query(
        None, ge=0, description="Minimum star velocity (stars/hour)"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get trending papers ranked by EMA-based GitHub repository trending score.

    This endpoint uses the trending_papers_24h view. It returns both:
    - velocity_24h: the current 24-hour star velocity shown in the UI as "stars / hr"
    - trending_score: an EMA-smoothed velocity used for ranking, so short bursts
      retain some influence while newer activity still matters most

    The trending score is calculated hourly by a cron job that:
    - Tracks star count changes over time
    - Calculates velocity (stars gained per hour)
    - Applies EMA smoothing (α=0.75) to weight recent velocity heavily while retaining some smoothing

    Returns papers with:
    - High EMA trending scores
    - Official repository links only
    - Latest versions only
    - Published within the specified age limit (default: 6 months)

    **Note**: The trending feature requires the hourly cron job to run for
    at least 1-2 hours to collect sufficient data for velocity calculations.
    """
    return PaperService(db).get_repository_trending_papers(
        limit=limit,
        max_age_days=max_age_days,
        min_velocity=min_velocity,
    )


def _public_metadata_error_response(error: PublicMetadataError) -> JSONResponse:
    headers = {}
    if error.retry_after:
        headers["Retry-After"] = str(error.retry_after)
    if error.status_code in {400, 404}:
        headers["Cache-Control"] = "public, max-age=3600"
    else:
        headers["Cache-Control"] = "no-store"
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": error.message}},
        headers=headers,
    )


def _public_metadata_cache_control(result: PublicPaperMetadata) -> str:
    return (
        "public, max-age=60, stale-while-revalidate=300"
        if result.in_catalog
        else "public, max-age=3600"
    )


@router.get(
    "/papers/public-metadata/search",
    response_model=PublicPaperMetadata,
    summary="Find public metadata for a paper by its exact title",
    responses={
        400: {"description": "Title too short"},
        404: {"description": "No arXiv or Crossref paper has this exact title"},
        429: {"description": "Too many uncached lookups"},
        503: {"description": "Public metadata sources are unavailable"},
    },
)
def search_public_paper_metadata(
    request: Request,
    response: Response,
    title: str = Query(
        ...,
        min_length=1,
        max_length=300,
        description="The paper's full title; matching ignores case and punctuation.",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Resolve a paper title on arXiv and Crossref, even outside the catalog.

    Only an exact normalized-title match counts, so a near-miss title never
    resolves to a different paper. As a last resort a "Name: subtitle" title
    matches the single arXiv paper with the same name before its colon, and
    the `note` says so. A match already in the catalog returns
    `in_catalog: true`; otherwise the response has the same shape as
    `/papers/{identifier}/public-metadata`.
    """
    try:
        result = PublicPaperMetadataService(db).search_title(
            title, get_proxied_client_ip(request)
        )
    except PublicMetadataError as error:
        return _public_metadata_error_response(error)
    response.headers["Cache-Control"] = _public_metadata_cache_control(result)
    return result


@router.get(
    "/papers/{identifier:path}/public-metadata",
    response_model=PublicPaperMetadata,
    summary="Get public metadata for a paper, even one outside the catalog",
    responses={
        400: {"description": "Unrecognised identifier"},
        404: {"description": "Neither the catalog nor any public source knows it"},
        429: {"description": "Too many uncached lookups"},
        503: {"description": "Public metadata sources are unavailable"},
    },
)
def get_public_paper_metadata(
    request: Request,
    response: Response,
    identifier: str = Path(
        ...,
        description=(
            "arXiv ID (with or without version), arXiv or Hugging Face paper "
            "URL, arXiv DOI, DOI, or Papers With Code paper ID."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Return paper metadata whether or not Papers With Code has indexed it.

    Catalog papers return `in_catalog: true` with their catalog ID and page.
    Other papers are looked up on Hugging Face Papers, arXiv, and Crossref
    and return `in_catalog: false`, the `metadata_source`, and an
    `available_at` list of labelled links where the paper can be read.
    Upstream results (hits and misses) are cached for an hour, and uncached
    lookups are rate-limited per client.
    """
    try:
        result = PublicPaperMetadataService(db).get(
            identifier, get_proxied_client_ip(request)
        )
    except PublicMetadataError as error:
        return _public_metadata_error_response(error)
    response.headers["Cache-Control"] = _public_metadata_cache_control(result)
    return result


@router.get(
    "/papers/{paper_id}",
    response_model=Paper,
    summary="Get paper by ArXiv ID or database ID",
)
def get_paper_by_id(
    paper_id: str = Path(
        ...,
        description=(
            "Identifier: ArXiv ID (e.g. '2504.12516') for ArXiv rows, or "
            "internal database ID (e.g. '12345') for external rows."
        ),
    ),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific paper by ArXiv ID or internal database ID.

    Resolution rules (per the external-resources design):
    - If the identifier looks like an ArXiv ID, return the latest version of
      that ArXiv paper.
    - Otherwise, treat the identifier as an internal database ID. This is the
      canonical addressing scheme for `source='external'` rows that do not
      have an ArXiv identifier.
    """
    try:
        service = PaperService(db)
        return service.get_paper_by_id_or_arxiv(
            paper_id, include_resources=include_resources
        )
    except PaperNotFoundError as e:
        # ``code`` sits beside the unchanged string ``detail`` so existing
        # clients keep working; /public-metadata covers unindexed papers.
        return JSONResponse(
            status_code=404,
            content={"detail": str(e), "code": "paper_not_in_catalog"},
        )


@router.get(
    "/papers/arxiv/{arxiv_id}", response_model=Paper, summary="Get paper by ArXiv ID"
)
def get_paper_by_arxiv_id(
    arxiv_id: str = Path(..., description="ArXiv ID (e.g., '1805.10616')"),
    version: Optional[str] = Query(
        None,
        description="Specific version (e.g., 'v2'). If not provided, returns latest version",
    ),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific paper by its ArXiv ID and optional version.

    If no version is specified, returns the latest version of the paper.
    If a specific version is requested, returns that exact version.

    The ArXiv ID should be in the format:
    - Modern: 1805.10616
    - Legacy: cs.DS/0610046
    """
    # Validate ArXiv ID format
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    # Validate version format if provided
    if version and not validate_version(version):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid version format: {version}. Expected format: v1, v2, etc.",
        )

    try:
        service = PaperService(db)
        return service.get_paper_by_arxiv_id(arxiv_id, version, include_resources)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/papers/arxiv/{arxiv_id}/versions",
    response_model=PaperVersions,
    summary="Get all versions of a paper",
)
def get_paper_versions(
    arxiv_id: str = Path(..., description="ArXiv ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all versions of a paper by ArXiv ID.

    Returns information about all available versions including:
    - Version identifiers
    - Publication dates
    - Title changes across versions
    - Abstract previews
    - Direct links to each version
    """
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    try:
        service = PaperService(db)
        return service.get_paper_versions(arxiv_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/papers/arxiv/{arxiv_id}/versions/{from_version}/compare/{to_version}",
    response_model=VersionComparison,
    summary="Compare two versions of a paper",
)
def compare_paper_versions(
    arxiv_id: str = Path(..., description="ArXiv ID"),
    from_version: str = Path(..., description="Source version (e.g., 'v1')"),
    to_version: str = Path(..., description="Target version (e.g., 'v2')"),
    db: Session = Depends(get_database_session),
):
    """
    Compare two versions of a paper to see what changed.

    Returns comparison information including:
    - Whether the title changed
    - Whether the abstract changed
    - Whether the publication date changed
    - Time elapsed between versions
    """
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    if not validate_version(from_version):
        raise HTTPException(
            status_code=400, detail=f"Invalid source version format: {from_version}"
        )

    if not validate_version(to_version):
        raise HTTPException(
            status_code=400, detail=f"Invalid target version format: {to_version}"
        )

    try:
        service = PaperService(db)
        return service.compare_paper_versions(arxiv_id, from_version, to_version)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _arxiv_metadata_error(arxiv_id: str, error_type: Optional[str]) -> HTTPException:
    if error_type == "rate_limited":
        return HTTPException(
            status_code=429,
            detail="arXiv is rate-limiting indexing right now. Try again in a few minutes.",
        )
    if error_type == "not_found":
        return HTTPException(
            status_code=404,
            detail=f"Paper with ArXiv ID {arxiv_id} was not found on arXiv.",
        )
    if error_type == "temporary_failure":
        return HTTPException(
            status_code=502,
            detail="Could not fetch metadata from arXiv right now. Try again in a few minutes.",
        )
    if error_type == "response_error":
        return HTTPException(
            status_code=502,
            detail="arXiv returned an invalid metadata response. Try again in a few minutes.",
        )
    if error_type == "db_error":
        return HTTPException(
            status_code=500,
            detail="Failed to add paper to database (may already exist)",
        )

    return HTTPException(
        status_code=502,
        detail="Could not fetch metadata from arXiv right now. Try again in a few minutes.",
    )


async def _fetch_and_persist_arxiv_paper(
    arxiv_id: str, db: Session, source_endpoint: str
) -> Paper:
    """Pull metadata from ArXiv and persist a new paper row with authors.

    Caller is responsible for checking that ``arxiv_id`` is valid and that no
    row with that ArXiv ID already exists. Returns the API ``Paper`` model.
    """
    try:
        return await PaperIngestionService(db).get_or_import_api_paper(
            arxiv_id,
            source_endpoint=source_endpoint,
            indexing_logger=logger,
        )
    except PaperIngestionError as exc:
        raise _arxiv_metadata_error(arxiv_id, exc.error_type)


@router.post(
    "/papers/index/{arxiv_id}",
    response_model=Paper,
    summary="Index a paper from ArXiv by ID",
    dependencies=[Depends(require_admin)],
)
async def index_paper_from_arxiv(
    arxiv_id: str = Path(..., description="ArXiv ID (e.g., '2511.08544')"),
    db: Session = Depends(get_database_session),
):
    """
    Fetch paper from ArXiv API and add to database.

    This endpoint:
    - Validates the ArXiv ID format
    - Fetches metadata from ArXiv API
    - Saves paper to database with authors
    - Returns the complete paper object

    Returns:
    - 200: Successfully indexed paper (returns Paper object)
    - 400: Invalid ArXiv ID format
    - 404: Paper not found on ArXiv
    - 409: Paper already exists in database
    - 500: Server error (ArXiv API unavailable, database error, etc.)
    """
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    paper_service = PaperService(db)

    try:
        existing_paper = paper_service.get_paper_by_arxiv_id(arxiv_id, version=None)
        if existing_paper:
            raise HTTPException(
                status_code=409,
                detail=(f"Paper with ArXiv ID {arxiv_id} already exists in database"),
            )
    except PaperNotFoundError:
        pass

    try:
        return await _fetch_and_persist_arxiv_paper(arxiv_id, db, "paper_detail")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected paper indexing failure")
        raise HTTPException(status_code=500, detail="Internal server error") from None


class PaperSubmitRequest(BaseModel):
    """Public paper submission payload.

    Either ``arxiv_id`` or ``source_url`` must be provided. The other fields
    are optional overrides for external (non-ArXiv) submissions; they are
    ignored when the submission resolves to an ArXiv ID.
    """

    arxiv_id: Optional[str] = Field(
        None,
        description=(
            "ArXiv identifier (e.g. '2501.12345' or '2501.12345v2'). May also "
            "be the full ArXiv abs/pdf URL; the server will normalize it."
        ),
    )
    source_url: Optional[str] = Field(
        None,
        description=(
            "Canonical URL for an external paper (blog post, technical "
            "report, model release page). ArXiv URLs are auto-detected and "
            "routed to the ArXiv flow even when supplied here."
        ),
    )
    title: Optional[str] = Field(None, description="Title override for external papers")
    abstract: Optional[str] = Field(
        None, description="Abstract override for external papers"
    )
    authors: Optional[List[str]] = Field(
        None, description="Author list override for external papers"
    )
    date_published: Optional[date] = Field(
        None,
        description=(
            "Publication date override for external papers. When omitted, "
            "the submission date is used if the submission is approved."
        ),
    )


class PaperSubmitResponse(BaseModel):
    """Response for a public paper submission."""

    paper: Optional[Paper] = None
    route_identifier: Optional[str] = Field(
        default=None,
        description=(
            "Identifier the frontend should use to navigate to the new paper "
            "page: ArXiv ID for ArXiv rows, internal numeric ID otherwise."
        ),
    )
    created: bool = Field(
        ...,
        description=(
            "True when the submission resulted in a new paper row, False when "
            "an existing row was returned (idempotent re-submission)."
        ),
    )
    refreshed: bool = Field(
        default=False,
        description="True when an existing ArXiv paper was refreshed from arXiv.",
    )
    previous_version: Optional[str] = Field(
        default=None,
        description="Previously indexed latest ArXiv version, if any.",
    )
    latest_version: Optional[str] = Field(
        default=None,
        description="Current latest ArXiv version after submission.",
    )
    submission_id: Optional[int] = Field(
        default=None,
        description="Pending submission ID for non-ArXiv paper proposals.",
    )
    pending_review: bool = False


@router.post(
    "/papers/submit",
    response_model=PaperSubmitResponse,
    summary="Submit a paper (ArXiv or external) from the public submit form",
)
async def submit_paper(
    http_request: Request,
    response: Response,
    request: PaperSubmitRequest = Body(...),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Unified entry point backing the ``/submit`` page.

    Routing:
      * If ``arxiv_id`` is provided (or ``source_url`` is an ArXiv URL), the
        request is funneled into the existing ArXiv indexing flow. Already
        indexed papers are returned with ``created=False`` instead of 409.
      * Otherwise the request is delegated to
        ``ExternalResourceService.add_from_url`` which performs AI-assisted
        metadata extraction with the supplied overrides.
    """
    try:
        result = await PaperSubmissionService(db, indexing_logger=logger).submit(
            PaperSubmissionCommand(
                arxiv_id=request.arxiv_id,
                source_url=request.source_url,
                title=request.title,
                abstract=request.abstract,
                authors=tuple(request.authors or ()),
                date_published=request.date_published,
                actor_username=user["username"],
                actor_subject=user["hf_subject"],
                actor_role=user["role"],
                source_ip=get_proxied_client_ip(http_request),
                idempotency_key=idempotency_key,
            )
        )
    except PaperSubmissionArxivMetadataError as exc:
        raise _arxiv_metadata_error(exc.arxiv_id, exc.error_type) from exc
    except PaperSubmissionDatabaseError as exc:
        raise DatabaseError(str(exc)) from exc
    except PaperSubmissionInternalError:
        logger.exception("Unexpected paper submission failure")
        raise HTTPException(status_code=500, detail="Internal server error") from None
    except PaperSubmissionRateLimitError as exc:
        response.headers["Retry-After"] = str(exc.retry_after)
        response.headers["RateLimit"] = "0"
        response.headers["RateLimit-Policy"] = "submission;w=3600"
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. See /rate-limits for help.",
            headers=dict(response.headers),
        ) from exc
    except PaperSubmissionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PaperSubmissionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PaperSubmitResponse(
        paper=result.paper,
        route_identifier=result.route_identifier,
        created=result.created,
        refreshed=result.refreshed,
        previous_version=result.previous_version,
        latest_version=result.latest_version,
        submission_id=result.submission_id,
        pending_review=result.pending_review,
    )


@router.post(
    "/papers/update-citations",
    summary="Update citation counts from Semantic Scholar",
    dependencies=[Depends(require_admin)],
)
async def update_citation_counts(
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of papers to update"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Update citation counts for papers using the Semantic Scholar API.

    This endpoint fetches citation counts from Semantic Scholar and updates
    the database. It prioritizes papers that haven't been updated recently
    or don't have citation data yet.

    Returns statistics about the update process.
    """
    service = PaperService(db)
    return await service.update_citation_counts(limit)


@router.get(
    "/papers/{paper_id}/methods/",
    summary="Get methods used in a paper",
)
def get_paper_methods(
    paper_id: str = Path(..., description="Paper ID or ArXiv ID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of methods per page (max 100)"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get all methods used in a specific paper.

    Returns a paginated list of AI/ML methods (techniques, algorithms, approaches)
    that are associated with the specified paper.

    **Examples:**
    - `/api/v1/papers/1234/methods/` - Get methods for paper ID 1234
    - `/api/v1/papers/1706.03762/methods/` - Get methods for ArXiv paper 1706.03762 (Attention is All You Need)
    """
    try:
        # Import here to avoid circular imports
        from backend.services.method_service import MethodService

        paper_service = PaperService(db)

        # Get the paper to verify it exists and get the numeric ID
        paper = paper_service.get_paper_by_id_or_arxiv(paper_id)

        # Get methods for this paper
        method_service = MethodService(db)
        return method_service.get_methods_for_paper(
            paper_id=int(paper.id),
            page=page,
            page_size=page_size,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/papers/{paper_id}/tasks",
    response_model=Paper,
    summary="Update tasks for a paper",
)
def update_paper_tasks(
    paper_id: int = Path(..., description="Database paper ID"),
    task_ids: List[int] = Query(
        default=[],
        description="List of task IDs to associate with the paper. "
        "An empty list clears all task associations.",
    ),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update the tasks associated with a paper.

    This endpoint allows admin users to update which tasks are linked to a paper.
    It replaces all existing task associations with the provided list.

    **Request Parameters:**
    - `paper_id`: Database ID of the paper to update
    - `task_ids`: List of task IDs to associate with this paper

    **Returns:**
    - Updated paper with new task associations

    **Example:**
    ```
    PUT /api/v1/papers/123/tasks?task_ids=1&task_ids=2&task_ids=3
    ```
    """
    try:
        return _curated_paper_update(
            db, mutation, paper_id, "tasks", {"task_ids": task_ids}
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/papers/{paper_id}/methods",
    response_model=Paper,
    summary="Update methods for a paper",
)
def update_paper_methods(
    paper_id: int = Path(..., description="Database paper ID"),
    method_ids: List[int] = Query(
        default=[],
        description="List of method IDs to associate with the paper. "
        "An empty list clears all method associations.",
    ),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update the methods associated with a paper.

    This endpoint allows admin users to update which methods are linked to a paper.
    It replaces all existing method associations with the provided list.

    **Request Parameters:**
    - `paper_id`: Database ID of the paper to update
    - `method_ids`: List of method IDs to associate with this paper

    **Returns:**
    - Updated paper with new method associations

    **Example:**
    ```
    PUT /api/v1/papers/123/methods?method_ids=1&method_ids=2&method_ids=3
    ```
    """
    try:
        return _curated_paper_update(
            db, mutation, paper_id, "methods", {"method_ids": method_ids}
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/papers/{paper_id}/organizations",
    response_model=Paper,
    summary="Update organizations for a paper",
)
def update_paper_organizations(
    paper_id: int = Path(..., description="Database paper ID"),
    organization_ids: List[int] = Query(
        default=[],
        description="List of organization IDs to associate with the paper. "
        "An empty list clears all organization associations.",
    ),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update the organizations associated with a paper.

    Makes the provided list the paper's organization associations. Existing
    links retain whether they came from Hugging Face or manual curation. New
    links are manual and record the authenticated HF user when available.

    **Example:**
    ```
    PUT /api/v1/papers/123/organizations?organization_ids=1&organization_ids=2
    ```
    """
    try:
        return _curated_paper_update(
            db,
            mutation,
            paper_id,
            "organizations",
            {"organization_ids": organization_ids},
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


class RepositoryInput(BaseModel):
    """Input model for repository data."""

    url: str = Field(..., description="Repository URL")
    is_official: bool = Field(
        default=False, description="Whether this is an official repository"
    )

    _normalize_url = field_validator("url", mode="before")(normalize_public_url)


class UpdateRepositoriesRequest(BaseModel):
    """Request model for updating paper repositories."""

    repositories: List[RepositoryInput] = Field(
        ..., description="List of repositories to associate with the paper"
    )


class ProjectPageInput(BaseModel):
    """Input model for project page data."""

    url: str = Field(..., description="Project page URL")
    is_official: bool = Field(
        default=False, description="Whether this is an official project page"
    )

    _normalize_url = field_validator("url", mode="before")(normalize_public_url)


class UpdateProjectPagesRequest(BaseModel):
    """Request model for updating paper project pages."""

    project_pages: List[ProjectPageInput] = Field(
        ..., description="List of project pages to associate with the paper"
    )


@router.put(
    "/papers/{paper_id}/repositories",
    response_model=Paper,
    summary="Update repositories for a paper",
)
def update_paper_repositories(
    paper_id: int = Path(..., description="Database paper ID"),
    request: UpdateRepositoriesRequest = Body(...),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update the repositories associated with a paper.

    This endpoint allows admin users to update which repositories are linked to a paper.
    It replaces all existing repository associations with the provided list.
    If a repository URL doesn't exist in the database, it will be created automatically.

    **Request Parameters:**
    - `paper_id`: Database ID of the paper to update
    - `repositories`: List of repository objects with URL and is_official flag

    **Returns:**
    - Updated paper with new repository associations

    **Example:**
    ```json
    PUT /api/v1/papers/123/repositories
    {
        "repositories": [
            {"url": "https://github.com/owner/repo", "is_official": true},
            {"url": "https://github.com/another/repo", "is_official": false}
        ]
    }
    ```
    """
    try:
        # Convert Pydantic models to dict for service layer
        repositories_data = [
            {"url": repo.url, "is_official": repo.is_official}
            for repo in request.repositories
        ]
        return _curated_paper_update(
            db,
            mutation,
            paper_id,
            "repositories",
            {"repositories": repositories_data},
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/papers/{paper_id}/project-pages",
    response_model=Paper,
    summary="Update project pages for a paper",
)
def update_paper_project_pages(
    paper_id: int = Path(..., description="Database paper ID"),
    request: UpdateProjectPagesRequest = Body(...),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update the project pages associated with a paper.

    This endpoint allows admin users to update which project pages are linked to a paper.
    It replaces all existing project page associations with the provided list.
    If a project page URL doesn't exist in the database, it will be created automatically
    via the updatable `project_pages_api` view.

    **Request Parameters:**
    - `paper_id`: Database ID of the paper to update
    - `project_pages`: List of project page objects with URL and is_official flag

    **Returns:**
    - Updated paper with new project page associations

    **Example:**
    ```json
    PUT /api/v1/papers/123/project-pages
    {
        "project_pages": [
            {"url": "https://example.com/project", "is_official": true},
            {"url": "https://another.com/demo", "is_official": false}
        ]
    }
    ```
    """
    try:
        # Convert Pydantic models to dict for service layer
        project_pages_data = [
            {"url": page.url, "is_official": page.is_official}
            for page in request.project_pages
        ]
        return _curated_paper_update(
            db,
            mutation,
            paper_id,
            "project_pages",
            {"project_pages": project_pages_data},
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


class UpdateHfArtifactsRequest(BaseModel):
    """Request model for updating explicit Hugging Face artifact URLs."""

    hf_models: List[str] = Field(
        default_factory=list,
        description="Full Hugging Face model URLs linked to this paper",
    )
    hf_datasets: List[str] = Field(
        default_factory=list,
        description="Full Hugging Face dataset URLs linked to this paper",
    )
    hf_spaces: List[str] = Field(
        default_factory=list,
        description="Full Hugging Face Space URLs linked to this paper",
    )


class UpdateSourceUrlRequest(BaseModel):
    """Request model for updating an external paper's canonical source URL."""

    source_url: str = Field(
        ...,
        description=(
            "New canonical URL for an external paper. Must start with "
            "http:// or https:// and be at most 2000 characters."
        ),
    )

    _normalize_url = field_validator("source_url", mode="before")(normalize_public_url)


@router.put(
    "/papers/{paper_id}/hf-artifacts",
    response_model=Paper,
    summary="Update Hugging Face artifacts for a paper",
)
def update_paper_hf_artifacts(
    paper_id: int = Path(..., description="Database paper ID"),
    request: UpdateHfArtifactsRequest = Body(...),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Replace explicit Hugging Face model, dataset, and Space URLs linked to a
    paper. URLs are normalized and must match their declared bucket.
    """
    return _curated_paper_update(
        db,
        mutation,
        paper_id,
        "hf_artifacts",
        {
            "hf_models": request.hf_models,
            "hf_datasets": request.hf_datasets,
            "hf_spaces": request.hf_spaces,
        },
    )


class UpdateXThreadsRequest(BaseModel):
    """Request model for updating the X threads introducing a paper."""

    x_threads: List[str] = Field(
        ...,
        max_length=10,
        description="X post URLs (x.com or twitter.com), in display order",
    )


@router.put(
    "/papers/{paper_id}/x-threads",
    response_model=Paper,
    summary="Update X threads for a paper",
)
def update_paper_x_threads(
    paper_id: int = Path(..., description="Database paper ID"),
    request: UpdateXThreadsRequest = Body(...),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Replace the X posts in which authors introduce a paper. A preview of each
    newly linked post is captured from X; unavailable posts are rejected.

    **Example:**
    ```json
    PUT /api/v1/papers/123/x-threads
    {"x_threads": ["https://x.com/artemZholus/status/2108983104178213096"]}
    ```
    """
    return _curated_paper_update(
        db, mutation, paper_id, "x_threads", {"x_threads": request.x_threads}
    )


@router.put(
    "/papers/{paper_id}/source-url",
    response_model=Paper,
    summary="Update the canonical source URL of an external paper",
)
def update_paper_source_url(
    paper_id: int = Path(..., description="Database paper ID"),
    request: UpdateSourceUrlRequest = Body(...),
    mutation: dict = Depends(catalog_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Replace the ``source_url`` of an external paper. ArXiv rows are rejected
    because their abstract URL is derived from ``arxiv_id``.
    """
    return _curated_paper_update(
        db,
        mutation,
        paper_id,
        "source_url",
        {"source_url": request.source_url},
    )
