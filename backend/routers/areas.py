"""
FastAPI router for area endpoints.

This module provides all area-related API endpoints that match the
original PapersWithCode API specification.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.taxonomy import (
    Area,
    Areas,
    AreasWithTaskBenchmarks,
    AreasWithTasks,
    Tasks,
)
from backend.services.area_service import AreaService
from backend.services.task_service import TaskService

router = APIRouter()


@router.get(
    "/areas/",
    response_model=Areas,
    summary="List research areas with pagination and filtering",
)
def get_areas(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        50, ge=1, le=500, description="Number of areas per page"
    ),
    q: Optional[str] = Query(
        None, description="Filter areas by querying the area name"
    ),
    name: Optional[str] = Query(None, description="Filter areas by part of the name"),
    ordering: Optional[str] = Query(
        None,
        pattern="^-?(name|created_at)$",
        description="Which field to use when ordering the results (prefix with - for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of research areas with optional filtering and searching.

    This endpoint provides comprehensive area listing functionality with:
    - Pagination support
    - Name search and filtering
    - Flexible sorting options

    **Filtering Options:**
    - `q`: Full-text search in area names
    - `name`: Filter by partial area name match

    **Sorting Options:**
    - `name`: Sort alphabetically by area name (default)
    - `created_at`: Sort by when area was added to database
    - Prefix with `-` for descending order (e.g., `-name`)

    **Response Format:**
    Returns a paginated response with area objects containing:
    - Area ID and name
    - Description (if available)
    - Timestamps
    - Pagination metadata (next/previous page numbers)

    **Example:**
    ```
    GET /api/v1/areas/?q=vision&page=1&page_size=10
    ```
    """
    area_service = AreaService(db)

    # Parse ordering
    order_by = "name"
    order_dir = "asc"
    if ordering:
        if ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]
        else:
            order_by = ordering

    # Use search if q is provided, otherwise use filtering
    if q:
        return area_service.search_areas(query=q, page=page, page_size=page_size)
    return area_service.list_areas(
        page=page,
        page_size=page_size,
        name=name,
        order_by=order_by,
        order_dir=order_dir,
    )


@router.get(
    "/areas/with-tasks/",
    response_model=AreasWithTasks,
    summary="Get all research areas with their tasks (taxonomy index)",
)
def get_areas_with_tasks(
    db: Session = Depends(get_database_session),
):
    """
    Return every research area together with its tasks and per-task paper
    counts in a single response.

    Powers the `/tasks` taxonomy index in the frontend without the previous
    fan-out (`/areas/` plus one `/areas/{id}/tasks` per area). All paper counts
    are aggregated in a single GROUP BY query rather than one count per task.
    """
    return AreaService(db).list_areas_with_tasks()


@router.get(
    "/areas/with-task-benchmarks/",
    response_model=AreasWithTaskBenchmarks,
    summary="Get research areas, tasks, and top benchmark previews",
)
def get_areas_with_task_benchmarks(
    benchmarks_per_task: int = Query(
        3, ge=1, le=10, description="Maximum benchmarks returned per task"
    ),
    min_eval_count: int = Query(
        2, ge=0, description="Minimum logical leaderboard rows per benchmark"
    ),
    db: Session = Depends(get_database_session),
):
    """Return a bounded areas → tasks → top benchmarks taxonomy for CLI use."""
    return AreaService(db).list_areas_with_task_benchmarks(
        benchmarks_per_task=benchmarks_per_task, min_eval_count=min_eval_count
    )


@router.get(
    "/areas/{area_id}",
    response_model=Area,
    summary="Get specific research area details",
)
def get_area(
    area_id: str = Path(..., description="Area ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get detailed information about a specific research area.

    This endpoint returns comprehensive area information including:
    - Area ID and name
    - Description (if available)
    - Timestamps

    **Path Parameters:**
    - `area_id`: The unique identifier for the research area

    **Response Format:**
    Returns a single area object with all available information.

    **Error Responses:**
    - `404 Not Found`: Area with the specified ID does not exist
    - `400 Bad Request`: Invalid area ID format
    - `500 Internal Server Error`: Database or server error

    **Example:**
    ```
    GET /api/v1/areas/1
    ```

    Returns information about the research area with ID 1 (e.g., "Vision").
    """
    return AreaService(db).lookup_area(area_id)


@router.get(
    "/areas/{area_id}/tasks",
    response_model=Tasks,
    summary="Get tasks for a specific research area",
)
def get_area_tasks(
    area_id: str = Path(..., description="Area ID"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        50, ge=1, le=100, description="Number of tasks per page"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of tasks associated with a specific research area.

    This endpoint returns all AI/ML tasks that belong to the specified research area,
    allowing you to explore the task taxonomy within each area.

    **Path Parameters:**
    - `area_id`: The unique identifier for the research area

    **Query Parameters:**
    - `page`: Page number for pagination (default: 1)
    - `page_size`: Number of tasks per page (max: 100, default: 50)

    **Response Format:**
    Returns a paginated response with task objects containing:
    - Task ID, name, and description
    - Hierarchy information (parent_id, level)
    - Paper count for each task
    - Pagination metadata

    **Example:**
    ```
    GET /api/v1/areas/1/tasks?page=1&page_size=20
    ```

    Returns all tasks in the area with ID 1 (e.g., Vision tasks like
    Image Classification, Object Detection, etc.)

    **Error Responses:**
    - `404 Not Found`: Area with the specified ID does not exist
    - `400 Bad Request`: Invalid area ID format
    - `500 Internal Server Error`: Database or server error
    """
    return TaskService(db).get_tasks_by_area(area_id, page=page, page_size=page_size)
