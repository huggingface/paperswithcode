"""
FastAPI router for repository and project page endpoints.

This module provides all repository and project page related API endpoints
that support the enhanced PapersWithCode functionality.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.papers import (
    Repository,
    Repositories,
    ProjectPage,
    ProjectPages,
    PaperProjectPage,
    ProjectPageWithPapers,
    ProjectPageCreateRequest,
    ProjectPageUpdateRequest,
    RepositoryStarHistoryList,
    GithubRepositoryPreview,
)
from backend.config import get_settings
from backend.services.github_preview_service import (
    GithubPreviewError,
    get_github_repository_preview,
)
from backend.services.repository_service import RepositoryService
from backend.services.project_page_service import ProjectPageService
from backend.utils.auth import (
    require_catalog_mutator,
    require_fresh_catalog_mutator,
    require_user,
)

router = APIRouter()


@router.get(
    "/github/repositories/{owner}/{repository}/preview",
    response_model=GithubRepositoryPreview,
    summary="Get cached GitHub repository preview metadata",
)
async def get_github_preview(
    response: Response,
    owner: str = Path(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$"),
    repository: str = Path(pattern=r"^[A-Za-z0-9._-]{1,100}$"),
    _user: dict = Depends(require_user),
):
    try:
        preview = await get_github_repository_preview(owner, repository, get_settings())
    except GithubPreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "private, max-age=1800"
    return preview


@router.get(
    "/repositories/",
    response_model=Repositories,
    summary="Get repositories with pagination and filtering",
)
def get_repositories(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of repositories per page"
    ),
    owner: Optional[str] = Query(None, description="Filter by repository owner"),
    official_only: bool = Query(
        False, description="Only include official repositories by paper authors"
    ),
    min_stars: Optional[int] = Query(
        None, ge=0, description="Minimum number of GitHub stars"
    ),
    source: Optional[str] = Query(
        None,
        description="Filter by data source (pwc_archive, ai_extraction, manual, etc.)",
    ),
    order_by: str = Query("num_stars", description="Field to order by"),
    order_dir: str = Query(
        "desc", pattern="^(asc|desc)$", description="Order direction"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of repositories with optional filtering.

    This endpoint provides comprehensive repository listing functionality with:
    - Pagination support
    - Filtering by owner, official status, and star count
    - Sorting options
    """
    return RepositoryService(db).get_repositories(
        page=page,
        page_size=page_size,
        owner=owner,
        official_only=official_only,
        min_stars=min_stars,
        source=source,
        order_by=order_by,
        order_dir=order_dir,
    )


@router.get(
    "/repositories/{repository_id}",
    response_model=Repository,
    summary="Get repository by ID",
)
def get_repository_by_id(
    repository_id: str = Path(..., description="Repository ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific repository by its database ID.
    """
    return RepositoryService(db).get_repository_by_id(repository_id)


@router.get(
    "/repositories/{owner}",
    response_model=List[Repository],
    summary="Get repositories by owner",
)
def get_repositories_by_owner(
    owner: str = Path(
        ..., description="Repository owner (GitHub username/organization)"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get all repositories by a specific owner.
    """
    return (
        RepositoryService(db)
        .get_repositories(
            page=1,
            page_size=1000,  # Large limit to get all repos by owner
            owner=owner,
        )
        .results
    )


@router.get(
    "/repositories/{owner}/{name}",
    response_model=List[Repository],
    summary="Get repositories by owner and name",
)
def get_repositories_by_owner_and_name(
    owner: str = Path(..., description="Repository owner"),
    name: str = Path(..., description="Repository name"),
    db: Session = Depends(get_database_session),
):
    """
    Get repositories by owner and name.
    """
    return RepositoryService(db).get_repositories_by_owner_and_name(owner, name)


@router.get(
    "/repositories/{repository_id}/stars/history",
    response_model=RepositoryStarHistoryList,
    summary="Get star count history for a repository",
)
def get_repository_star_history(
    repository_id: str = Path(..., description="Repository ID"),
    limit: Optional[int] = Query(
        None, ge=1, le=1000, description="Maximum number of snapshots to return"
    ),
    since: Optional[datetime] = Query(
        None, description="Return snapshots after this datetime (ISO 8601 format)"
    ),
    hours_lookback: Optional[int] = Query(
        None,
        ge=1,
        le=8760,
        description="Number of hours to look back (overrides 'since' if provided)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get historical star count snapshots for a repository.

    This endpoint returns the star count history from the `repository_star_history` table,
    which is populated by the hourly trending calculation CRON job.

    **Query Parameters:**
    - `limit`: Maximum number of snapshots to return (default: all)
    - `since`: Return snapshots after this datetime (ISO 8601 format)
    - `hours_lookback`: Number of hours to look back (e.g., 24 for last day, 168 for last week)

    **Examples:**
    - `/api/v1/repositories/123/stars/history?hours_lookback=24` - Last 24 hours
    - `/api/v1/repositories/123/stars/history?limit=100` - Last 100 snapshots
    - `/api/v1/repositories/123/stars/history?since=2025-11-01T00:00:00Z` - Since Nov 1, 2025

    **Returns:**
    ```json
    {
        "repository_id": "123",
        "count": 48,
        "snapshots": [
            {
                "id": "1",
                "repository_id": "123",
                "num_stars": 1234,
                "snapshot_at": "2025-11-01T12:00:00Z",
                "created_at": "2025-11-01T12:00:05Z"
            },
            ...
        ]
    }
    ```

    **Note:** Snapshots are ordered chronologically (oldest first).
    """
    return RepositoryService(db).get_repository_star_history(
        repository_id=repository_id,
        limit=limit,
        since=since,
        hours_lookback=hours_lookback,
    )


@router.get(
    "/project-pages/",
    response_model=ProjectPages,
    summary="Get project pages with pagination and filtering",
)
def get_project_pages(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of project pages per page"
    ),
    official_only: bool = Query(
        False, description="Only include official project pages by paper authors"
    ),
    source: Optional[str] = Query(
        None,
        description="Filter by data source (pwc_archive, ai_extraction, manual, etc.)",
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order_dir: str = Query(
        "desc", pattern="^(asc|desc)$", description="Order direction"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of project pages with optional filtering.

    This endpoint provides comprehensive project page listing functionality with:
    - Pagination support
    - Filtering by official status
    - Sorting options
    """
    return ProjectPageService(db).get_project_pages(
        page=page,
        page_size=page_size,
        official_only=official_only,
        source=source,
        order_by=order_by,
        order_dir=order_dir,
    )


@router.get(
    "/project-pages/{page_id}",
    response_model=ProjectPage,
    summary="Get project page by ID",
)
def get_project_page_by_id(
    page_id: str = Path(..., description="Project page ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific project page by its database ID.
    """
    return ProjectPageService(db).get_project_page_by_id(page_id)


@router.post(
    "/project-pages/",
    response_model=ProjectPage,
    status_code=201,
    summary="Create a new project page",
    dependencies=[Depends(require_catalog_mutator)],
)
def create_project_page(
    request: ProjectPageCreateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Create a new project page.

    Creates a new project page with the provided URL and metadata. The URL must be unique.

    **Request Body:**
    ```json
    {
        "url": "https://example.com/project",
        "is_official": true,
        "source": "manual"
    }
    ```

    **Returns:**
    - 201: Created project page object with ID
    - 400: Invalid request or URL already exists
    - 500: Internal server error
    """
    return ProjectPageService(db).create_project_page(request)


@router.put(
    "/project-pages/{page_id}",
    response_model=ProjectPage,
    summary="Update a project page",
    dependencies=[Depends(require_catalog_mutator)],
)
def update_project_page(
    page_id: str = Path(..., description="Project page ID"),
    request: ProjectPageUpdateRequest = ...,
    db: Session = Depends(get_database_session),
):
    """
    Update an existing project page.

    Updates the fields of an existing project page. Only provided fields will be updated.

    **Example:**
    ```
    PUT /api/v1/project-pages/123
    {
        "url": "https://new-url.com/project",
        "is_official": true
    }
    ```

    **Returns:**
    - 200: Updated project page object
    - 400: Invalid request or URL conflict
    - 404: Project page not found
    - 500: Internal server error
    """
    return ProjectPageService(db).update_project_page(page_id, request)


@router.delete(
    "/project-pages/{page_id}",
    status_code=204,
    summary="Delete a project page",
    dependencies=[Depends(require_fresh_catalog_mutator)],
)
def delete_project_page(
    page_id: str = Path(..., description="Project page ID"),
    db: Session = Depends(get_database_session),
):
    """
    Delete a project page.

    Permanently deletes a project page and all its associations with papers.

    **Example:**
    - `/api/v1/project-pages/123` - Delete project page with ID 123

    **Returns:**
    - 204 No Content on success
    - 404: Project page not found
    - 500: Internal server error
    """
    ProjectPageService(db).delete_project_page(page_id)
    return None


# Paper-specific endpoints


@router.get(
    "/papers/{paper_id}/repositories",
    response_model=List[Repository],
    summary="Get repositories for a paper",
)
def get_repositories_for_paper(
    paper_id: str = Path(..., description="Paper ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all repositories associated with a specific paper.
    """
    return RepositoryService(db).get_repositories_for_paper(paper_id)


@router.get(
    "/papers/{paper_id}/project-pages",
    response_model=List[ProjectPage],
    summary="Get project pages for a paper",
)
def get_project_pages_for_paper(
    paper_id: str = Path(..., description="Paper ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all project pages associated with a specific paper.
    """
    return ProjectPageService(db).get_project_pages_for_paper(paper_id)


@router.get(
    "/project-pages/{page_id}/papers",
    response_model=ProjectPageWithPapers,
    summary="Get project page with associated papers",
)
def get_project_page_with_papers(
    page_id: str = Path(..., description="Project page ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get a project page with all associated papers and relationship metadata.

    This endpoint provides detailed information about which papers are associated
    with a project page, including relationship metadata like official status.
    """
    return ProjectPageService(db).get_project_page_with_papers(page_id)


@router.get(
    "/paper-project-page-relationships/",
    response_model=List[PaperProjectPage],
    summary="Get paper-project page relationships",
)
def get_paper_project_page_relationships(
    paper_id: Optional[str] = Query(None, description="Filter by paper ID"),
    project_page_id: Optional[str] = Query(
        None, description="Filter by project page ID"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get paper-project page relationships with optional filtering.

    This endpoint provides access to the junction table data, including
    relationship metadata like official status and source information.
    """
    return ProjectPageService(db).get_paper_project_page_relationships(
        paper_id=paper_id, project_page_id=project_page_id
    )
