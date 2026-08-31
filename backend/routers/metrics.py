"""
Metrics API router.

Provides endpoints for accessing metric definitions and their ranking directions.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.evaluations import (
    Metric,
    Metrics,
    MetricDirections,
)
from backend.services.metric_service import MetricService
from backend.database.connection import get_database_session

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", response_model=Metrics)
def list_metrics(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        100, ge=1, le=500, description="Number of metrics per page (max 500)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for metric name, full name, and description"
    ),
    direction: Optional[str] = Query(
        None, description="Filter by direction: 'higher_is_better' or 'lower_is_better'"
    ),
    ordering: Optional[str] = Query(
        "name",
        description="Order by field: name, direction, created_at (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of metric definitions.

    Metrics can be filtered by direction or searched across name and description.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/metrics/` - Get all metrics
    - `/api/v1/metrics/?direction=lower_is_better` - Get metrics where lower is better (WER, etc.)
    - `/api/v1/metrics/?q=accuracy` - Search for metrics containing "accuracy"
    - `/api/v1/metrics/?ordering=-name` - Order by name descending
    """
    # Parse ordering
    order_dir = "asc"
    order_by = ordering
    if ordering and ordering.startswith("-"):
        order_dir = "desc"
        order_by = ordering[1:]

    valid_fields = ["name", "direction", "created_at"]
    if order_by not in valid_fields:
        order_by = "name"

    service = MetricService(db)
    service.validate_direction(direction)

    return service.list_metrics(
        page=page,
        page_size=page_size,
        search=q,
        direction=direction,
        order_by=order_by,
        order_dir=order_dir,
    )


@router.get("/directions", response_model=MetricDirections)
def get_metric_directions(
    db: Session = Depends(get_database_session),
):
    """
    Get a mapping of all metric names to their ranking directions.

    This is an optimized endpoint for the frontend to quickly lookup
    metric directions without fetching full metric details.

    **Returns:**
    ```json
    {
        "directions": {
            "WER": "lower_is_better",
            "AP": "higher_is_better",
            "Accuracy": "higher_is_better",
            "Perplexity": "lower_is_better",
            ...
        }
    }
    ```

    **Example:**
    - `/api/v1/metrics/directions` - Get all metric directions
    """
    return MetricDirections(directions=MetricService(db).list_metric_directions())


@router.get("/{metric_name}", response_model=Metric)
def get_metric(
    metric_name: str,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific metric by name.

    **Example:**
    - `/api/v1/metrics/WER` - Get details for Word Error Rate metric
    - `/api/v1/metrics/AP` - Get details for Average Precision metric
    """
    return MetricService(db).lookup_metric(metric_name)
