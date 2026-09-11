"""
Metric service for handling metric-related business logic.

This service provides methods for retrieving metric definitions and their ranking directions.
"""

from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_

from backend.models.database import Metric as DBMetric
from backend.models.evaluations import (
    Metric,
    Metrics,
)
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)
from backend.utils.exceptions import DatabaseError


class MetricService:
    """Service class for metric-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_metric(self, *, commit: bool = True, **fields) -> DBMetric:
        if self.db.query(DBMetric.id).filter(DBMetric.name == fields["name"]).first():
            raise CatalogConflictError(f"Metric '{fields['name']}' already exists")
        row = DBMetric(**fields)
        self.db.add(row)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(row)
        return row

    def get_metrics(
        self,
        page: int = 1,
        page_size: int = 100,
        search: Optional[str] = None,
        direction: Optional[str] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Metrics:
        """
        Get a paginated list of metric definitions.

        Args:
            page: Page number (1-based)
            page_size: Number of metrics per page
            search: Search term for metric name and description
            direction: Filter by direction ('higher_is_better' or 'lower_is_better')
            order_by: Field to order by (name, direction, created_at)
            order_dir: Order direction (asc, desc)

        Returns:
            Metrics object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBMetric)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search
                query = query.filter(
                    or_(
                        DBMetric.name.ilike(f"%{search}%"),
                        DBMetric.full_name.ilike(f"%{search}%")
                        if DBMetric.full_name
                        else False,
                        DBMetric.description.ilike(f"%{search}%")
                        if DBMetric.description
                        else False,
                    )
                )

            if direction:
                query = query.filter(DBMetric.direction == direction)

            # Apply ordering
            order_column = getattr(DBMetric, order_by, DBMetric.name)
            if order_dir == "desc":
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Calculate pagination info
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            # Convert to Pydantic models
            metric_models = [Metric.model_validate(metric) for metric in results]

            return Metrics(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=metric_models,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve metrics: {str(e)}")

    def get_metric_by_name(self, name: str) -> Optional[Metric]:
        """
        Get a specific metric by name.

        Args:
            name: Metric name (e.g., 'WER', 'AP')

        Returns:
            Metric object if found, None otherwise

        Raises:
            DatabaseError: If database query fails
        """
        try:
            metric = self.db.query(DBMetric).filter(DBMetric.name == name).first()
            if metric:
                return Metric.model_validate(metric)
            return None

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve metric '{name}': {str(e)}")

    def lookup_metric(self, name: str) -> Metric:
        metric = self.get_metric_by_name(name)
        if metric is None:
            raise CatalogNotFoundError(f"Metric '{name}' not found")
        return metric

    def list_metrics(self, **kwargs) -> Metrics:
        try:
            return self.get_metrics(**kwargs)
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def list_metric_directions(self) -> Dict[str, str]:
        try:
            return self.get_metric_directions()
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    @staticmethod
    def validate_direction(direction: Optional[str]) -> None:
        if direction and direction not in {"higher_is_better", "lower_is_better"}:
            raise CatalogValidationError(
                "Invalid direction. Must be 'higher_is_better' or 'lower_is_better'"
            )

    def get_metric_directions(self) -> Dict[str, str]:
        """
        Get a mapping of all metric names to their ranking directions.

        This is an optimized endpoint for the frontend to quickly lookup
        metric directions without fetching full metric details.

        Returns:
            Dictionary mapping metric names to directions
            Example: {'WER': 'lower_is_better', 'AP': 'higher_is_better'}

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query all metrics, selecting only name and direction
            metrics = self.db.query(DBMetric.name, DBMetric.direction).all()

            # Build dictionary
            directions = {metric.name: metric.direction for metric in metrics}

            return directions

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve metric directions: {str(e)}")
