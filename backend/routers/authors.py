"""
FastAPI router for author endpoints.

This module provides all author-related API endpoints that match the
original PapersWithCode API specification with enhancements.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.papers import (
    Author,
    Authors,
    Papers,
)
from backend.services.author_service import AuthorService
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

router = APIRouter()


@router.get(
    "/authors/",
    response_model=Authors,
    summary="List authors with pagination and filtering",
)
def get_authors(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        50, ge=1, le=500, description="Number of authors per page"
    ),
    search: Optional[str] = Query(
        None, description="Search term for author name or Hugging Face username"
    ),
    hf_users_only: bool = Query(
        False, description="Filter to only authors with Hugging Face accounts"
    ),
    order_by: str = Query(
        "paper_count",
        pattern="^(name|paper_count|created_at)$",
        description="Field to order by",
    ),
    order_dir: str = Query(
        "desc", pattern="^(asc|desc)$", description="Order direction"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of authors with optional filtering and searching.

    This endpoint provides comprehensive author listing functionality with:
    - Pagination support
    - Name and username search
    - Hugging Face integration filtering
    - Flexible sorting options
    - Paper count statistics

    **Filtering Options:**
    - `search`: Search by author name or Hugging Face username
    - `hf_users_only`: Show only authors with Hugging Face accounts

    **Sorting Options:**
    - `name`: Sort alphabetically by author name
    - `paper_count`: Sort by number of papers (default)
    - `created_at`: Sort by when author was added to database

    **Response Format:**
    Returns a paginated response with author objects containing:
    - Basic author information (ID, name)
    - Hugging Face integration data (username, avatar, etc.)
    - Paper count statistics
    - Pagination metadata (next/previous page numbers)
    """
    try:
        author_service = AuthorService(db)

        if search:
            # Use search functionality for better results
            return author_service.search_authors(
                query=search,
                page=page,
                page_size=page_size,
                hf_users_only=hf_users_only,
            )
        else:
            # Regular listing with filters
            return author_service.get_authors(
                page=page,
                page_size=page_size,
                hf_users_only=hf_users_only,
                order_by=order_by,
                order_dir=order_dir,
            )

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/authors/{author_id}",
    response_model=Author,
    summary="Get specific author details",
)
def get_author(
    author_id: str = Path(..., description="Author ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get detailed information about a specific author.

    This endpoint returns comprehensive author information including:
    - Basic author details (ID, name)
    - Hugging Face integration data (if available)
    - Paper count statistics
    - Account status and metadata

    **Path Parameters:**
    - `author_id`: The unique identifier for the author

    **Response Format:**
    Returns a single author object with all available information.

    **Error Responses:**
    - `404 Not Found`: Author with the specified ID does not exist
    - `400 Bad Request`: Invalid author ID format
    - `500 Internal Server Error`: Database or server error
    """
    try:
        author_service = AuthorService(db)
        return author_service.get_author_by_id(author_id)

    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/authors/{author_id}/papers",
    response_model=Papers,
    summary="Get papers by specific author",
)
def get_author_papers(
    author_id: str = Path(..., description="Author ID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        50, ge=1, le=500, description="Number of papers per page"
    ),
    latest_only: bool = Query(
        True, description="Whether to only include latest versions of papers"
    ),
    order_by: str = Query(
        "date_published",
        pattern="^(date_published|title|citation_count)$",
        description="Field to order by",
    ),
    order_dir: str = Query(
        "desc", pattern="^(asc|desc)$", description="Order direction"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get all papers authored or co-authored by a specific author.

    This endpoint returns a paginated list of papers associated with the author,
    with options for filtering and sorting.

    **Path Parameters:**
    - `author_id`: The unique identifier for the author

    **Query Parameters:**
    - `latest_only`: If true, only returns the latest version of each paper
    - `order_by`: Sort papers by publication date, title, or citation count
    - `order_dir`: Sort in ascending or descending order

    **Response Format:**
    Returns a paginated response with paper objects containing:
    - Full paper metadata (title, abstract, ArXiv ID, etc.)
    - Author information
    - Publication details
    - Citation metrics
    - Pagination metadata

    **Use Cases:**
    - Author profile pages showing their research output
    - Academic collaboration analysis
    - Research timeline visualization
    - Citation impact assessment

    **Error Responses:**
    - `404 Not Found`: Author with the specified ID does not exist
    - `400 Bad Request`: Invalid author ID or query parameters
    - `500 Internal Server Error`: Database or server error
    """
    try:
        author_service = AuthorService(db)
        return author_service.get_author_papers(
            author_id=author_id,
            page=page,
            page_size=page_size,
            latest_only=latest_only,
            order_by=order_by,
            order_dir=order_dir,
        )

    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
