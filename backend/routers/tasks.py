"""
Tasks API router.

Provides endpoints for accessing AI/ML task data, including hierarchical relationships,
filtering by area, and paper associations.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session
from typing import Optional, List

from backend.models.api import (
    Task,
    Tasks,
    TaskPage,
    Papers,
    KeywordUpdate,
    TaskCreateRequest,
    TrendingBenchmarks,
    TrendingTasks,
)
from backend.models.database import Task as DBTask
from backend.services.benchmark_trend_service import BenchmarkTrendService
from backend.services.task_service import TaskService
from backend.database.connection import get_database_session
from backend.utils.entity_images import (
    IMAGE_CACHE_HEADERS,
    IMAGE_MISSING_HEADERS,
    load_entity_image,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=Tasks)
def list_tasks(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of tasks per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for task name and description"
    ),
    name: Optional[str] = Query(None, description="Filter by partial task name match"),
    area_id: Optional[int] = Query(None, description="Filter by research area ID"),
    parent_id: Optional[int] = Query(None, description="Filter by parent task ID"),
    level: Optional[int] = Query(None, ge=0, description="Filter by hierarchy level"),
    visible_only: bool = Query(
        False,
        description=(
            "If true, restrict results to tasks with `is_visible = true`. "
            "Used by user-facing pickers (paper task-tagging dropdown, "
            "taxonomy index) so hidden tasks like `object-counting` or "
            "`classic-language-modeling` never appear as choices."
        ),
    ),
    ordering: Optional[str] = Query(
        "name",
        description="Order by field: name, created_at, level, paper_count (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of AI/ML tasks.

    Tasks are hierarchical and can be filtered by area, parent task, or hierarchy level.
    Supports full-text search across task names and descriptions.

    **Example queries:**
    - `/api/v1/tasks/` - Get all tasks
    - `/api/v1/tasks/?area_id=1` - Get tasks in Vision area
    - `/api/v1/tasks/?level=0` - Get only top-level tasks
    - `/api/v1/tasks/?parent_id=5` - Get subtasks of task 5
    - `/api/v1/tasks/?q=classification` - Search for tasks containing "classification"
    - `/api/v1/tasks/?visible_only=true` - Hide tasks marked `is_visible = false`
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = ["name", "created_at", "level", "paper_count"]
        if order_by not in valid_fields:
            order_by = "name"

        service = TaskService(db)

        # Use search if q parameter is provided
        if q:
            return service.search_tasks(
                query=q,
                page=page,
                page_size=page_size,
                visible_only=visible_only,
            )

        return service.get_tasks(
            page=page,
            page_size=page_size,
            name=name,
            area_id=area_id,
            parent_id=parent_id,
            level=level,
            visible_only=visible_only,
            order_by=order_by,
            order_dir=order_dir,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trending", response_model=TrendingTasks)
def get_trending_tasks(
    limit: int = Query(
        8, ge=1, le=50, description="Maximum number of trending tasks to return"
    ),
    recent_days: int = Query(
        30, ge=1, le=365, description="Length of the recent window in days"
    ),
    baseline_days: int = Query(
        180,
        ge=1,
        le=730,
        description="Length of the baseline window immediately preceding the recent window",
    ),
    level: Optional[int] = Query(
        None,
        ge=0,
        description="Optional hierarchy level filter (0 = top-level domains only)",
    ),
    min_recent_papers: int = Query(
        5,
        ge=1,
        description="Minimum recent-window paper count required for a task to qualify",
    ),
    min_baseline_papers: int = Query(
        10,
        ge=1,
        description="Minimum baseline-window paper count required for a task to qualify",
    ),
    min_share_lift: float = Query(
        1.0,
        ge=0.0,
        description=(
            "Minimum share lift (recent share divided by baseline share). Default 1.0 "
            "restricts results to domains that are actively growing."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Trending domains for the homepage sidebar.

    Ranks tasks by descending `share_lift`, where `share_lift` compares each
    task's share of recent papers against its share in the preceding baseline
    window. Lift > 1.0 means the task is over-indexed in recent publications
    relative to its history. `trend_score` is still returned (and used as a
    tiebreaker) but no longer drives the primary order.

    **Example queries:**
    - `/api/v1/tasks/trending` - default 30d vs preceding 180d, top 8
    - `/api/v1/tasks/trending?limit=12&level=0` - top-level domains only
    """
    try:
        service = TaskService(db)
        return service.get_trending_tasks(
            limit=limit,
            recent_days=recent_days,
            baseline_days=baseline_days,
            level=level,
            min_recent_papers=min_recent_papers,
            min_baseline_papers=min_baseline_papers,
            min_share_lift=min_share_lift,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top", response_model=List[Task])
def get_top_tasks(
    limit: int = Query(
        8, ge=1, le=50, description="Maximum number of top tasks to return"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Top tasks by paper count for the homepage sidebar.

    This endpoint is intentionally small and cache-friendly. It avoids the
    pagination count work done by the general `/tasks/` listing.
    """
    try:
        service = TaskService(db)
        return service.get_top_tasks(limit=limit)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/trending-benchmarks", response_model=TrendingBenchmarks)
def get_trending_benchmarks(
    task_id: str,
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of benchmarks to return"
    ),
    recent_days: int = Query(
        90, ge=1, le=365, description="Length of the recent reporting window"
    ),
    baseline_days: int = Query(
        180,
        ge=1,
        le=730,
        description="Length of the window immediately preceding the recent one",
    ),
    min_recent_papers: int = Query(
        1, ge=0, description="Minimum distinct recent reporting papers"
    ),
    include_descendants: bool = Query(
        False, description="Roll up benchmark reports from descendant tasks"
    ),
    bucket_days: int = Query(
        30, ge=7, le=90, description="Length of each sparkline bucket"
    ),
    history_buckets: int = Query(
        6, ge=2, le=24, description="Number of sparkline buckets"
    ),
    db: Session = Depends(get_database_session),
):
    """Rank a task's benchmarks by distinct recent evaluation-reporting papers.

    The default 90-day ranking provides enough evidence for sparse task pages
    without falling back to all-time leaderboard popularity. Each paper counts
    once per benchmark even when it contributes multiple model or metric rows.
    """
    try:
        return BenchmarkTrendService(db).get_trending_benchmarks(
            task_id,
            limit=limit,
            recent_days=recent_days,
            baseline_days=baseline_days,
            min_recent_papers=min_recent_papers,
            include_descendants=include_descendants,
            bucket_days=bucket_days,
            history_buckets=history_buckets,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=Task)
def get_task(
    task_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific AI/ML task by ID or slug.

    Returns detailed information about a task including its description,
    hierarchy information (parent/area), and paper count.

    **Examples:**
    - `/api/v1/tasks/1` - Get task with ID 1
    - `/api/v1/tasks/computer-use-agents` - Get task by slug
    """
    try:
        service = TaskService(db)

        # Try as numeric ID first
        if task_id.isdigit():
            return service.get_task_by_id(task_id)

        # Otherwise, treat as slug
        return service.get_task_by_slug(task_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/image")
def get_task_image(
    task_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Serve the DB-backed hero image for a task by ID or slug.

    Returns the raw image bytes stored in `tasks.image_data`. 404s when the
    task does not exist or has no stored image.
    """
    result = load_entity_image(db, DBTask, task_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Image not available",
            headers=IMAGE_MISSING_HEADERS,
        )
    data, mime = result
    return Response(content=data, media_type=mime, headers=IMAGE_CACHE_HEADERS)


@router.get("/{task_id}/page", response_model=TaskPage)
def get_task_page(
    task_id: str,
    is_open: Optional[bool] = Query(
        None,
        description=(
            "When set, choose benchmark `best_model_name` values from only "
            "open-source or only closed-source evaluation rows."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get the bundled task-page payload in a single request.

    Returns the task plus its parents, explicitly configured sister tasks,
    recommended GitHub frameworks (with current star counts), visible
    children, directly-associated benchmarks, and a short benchmark preview
    for each child. This collapses the task-detail page's initial request
    fan-out into one round trip.

    **Examples:**
    - `/api/v1/tasks/language-modeling/page`
    - `/api/v1/tasks/5/page`
    """
    try:
        service = TaskService(db)
        return service.get_task_page(task_id, is_open=is_open)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/children", response_model=Tasks)
def get_task_children(
    task_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of tasks per page (max 100)"
    ),
    visible_only: bool = Query(
        False,
        description="If true, restrict results to subtasks with `is_visible = true`.",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get child tasks (subtasks) of a specific task.

    Returns all tasks that have the specified task as their parent.
    Useful for exploring task hierarchies.

    **Example:**
    - `/api/v1/tasks/5/children` - Get all subtasks of task 5
    """
    try:
        service = TaskService(db)
        return service.get_task_children(
            task_id,
            page=page,
            page_size=page_size,
            visible_only=visible_only,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/parents", response_model=list[Task])
def get_task_parents(
    task_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get all parent tasks of a specific task.

    Returns the entire hierarchy from the immediate parent up to the root task.
    The list is ordered from immediate parent to root.

    **Example:**
    - `/api/v1/tasks/10/parents` - Get parent hierarchy of task 10
    """
    try:
        service = TaskService(db)
        return service.get_task_parents(task_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/papers", response_model=Papers)
def get_task_papers(
    task_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Number of papers per page (max 100)"
    ),
    latest_only: bool = Query(
        True, description="Whether to only include latest versions of papers"
    ),
    order_by: str = Query(
        "date_published",
        description="Field to order by: date_published, title, citation_count, trending",
    ),
    order_dir: str = Query(
        "desc", pattern="^(asc|desc)$", description="Order direction"
    ),
    include_resources: bool = Query(
        False, description="Include repositories and tasks"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get papers associated with a specific task.

    Returns paginated papers that are tagged with the specified task.
    Supports sorting by publication date, title, citation count, or trending score.

    **Examples:**
    - `/api/v1/tasks/2/papers` - Get recent papers for task 2
    - `/api/v1/tasks/object-detection/papers?order_by=citation_count` - Most cited papers
    - `/api/v1/tasks/object-detection/papers?order_by=trending` - Papers ranked by official repo trending score
    - `/api/v1/tasks/object-detection/papers?order_by=title&order_dir=asc` - Papers A-Z
    """
    try:
        service = TaskService(db)
        return service.get_task_papers(
            task_id=task_id,
            page=page,
            page_size=page_size,
            latest_only=latest_only,
            order_by=order_by,
            order_dir=order_dir,
            include_resources=include_resources,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Task, status_code=201)
def create_task(
    request: TaskCreateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Create a new task.

    Creates a new AI/ML task with the provided information. The task slug is
    auto-generated from the name. The task level is automatically calculated
    based on whether it has a parent task.

    **Request Body:**
    ```json
    {
        "name": "Audio Classification",
        "description": "Classification of audio signals into predefined categories",
        "keywords": "audio classification",
        "area_id": 6,
        "parent_id": null,
        "image_url": null,
        "image_credit": null
    }
    ```

    **Returns:**
    - Created task object with auto-generated slug and ID
    - 201 status code on success

    **Errors:**
    - 400: Invalid request data (area_id or parent_id don't exist)
    - 409: Task with the same slug already exists
    - 500: Internal server error
    """
    try:
        service = TaskService(db)
        return service.create_task(request)

    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        elif "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{task_id}/keywords", response_model=Task)
def add_task_keywords(
    task_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Add keywords to a task (appends to existing keywords).

    Adds the specified keywords to the task's keyword list without removing
    existing keywords. Duplicates are automatically prevented.

    **Examples:**
    - `/api/v1/tasks/computer-use-agents/keywords` - Add keywords to task by slug
    - `/api/v1/tasks/1/keywords` - Add keywords by task ID

    **Request body:**
    ```json
    {
        "keywords": ["agent", "computer-use"]
    }
    ```
    """
    try:
        service = TaskService(db)
        return service.add_keywords(task_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}/keywords", response_model=Task)
def remove_task_keywords(
    task_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Remove specific keywords from a task.

    Removes the specified keywords from the task's keyword list.
    Keywords not present in the list are silently ignored.

    **Examples:**
    - `/api/v1/tasks/computer-use-agents/keywords` - Remove keywords from task by slug
    - `/api/v1/tasks/1/keywords` - Remove keywords by task ID

    **Request body:**
    ```json
    {
        "keywords": ["old-keyword"]
    }
    ```
    """
    try:
        service = TaskService(db)
        return service.remove_keywords(task_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}/keywords", response_model=Task)
def replace_task_keywords(
    task_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Replace all keywords for a task.

    Replaces the entire keyword list with the provided keywords.
    All existing keywords are removed and replaced with the new list.

    **Examples:**
    - `/api/v1/tasks/computer-use-agents/keywords` - Replace all keywords for task by slug
    - `/api/v1/tasks/1/keywords` - Replace keywords by task ID

    **Request body:**
    ```json
    {
        "keywords": ["agent", "computer-use", "automation"]
    }
    ```
    """
    try:
        service = TaskService(db)
        return service.replace_keywords(task_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
