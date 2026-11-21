"""
Leaderboard-Metric service for managing relationships between tasks, datasets, and metrics.

This service provides methods for managing which metrics are allowed for each leaderboard
(defined as a triple of task, dataset, metric), and validates evaluation submissions against
these relationships.
"""

from typing import List, Optional, Set, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset as DBDataset,
)
from backend.models.database import (
    Metric as DBMetric,
)
from backend.models.database import (
    Task as DBTask,
)
from backend.models.database import (
    TaskDataset,
)
from backend.models.database import (
    TaskDatasetMetric as DBTaskDatasetMetric,
)
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)


class LeaderboardMetricService:
    """Service class for leaderboard (task-dataset-metric) operations."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_leaderboard_identifiers(
        self, task_identifier: str, dataset_identifier: str
    ) -> tuple[int, int]:
        """Resolve the numeric-only public identifiers for leaderboard routes."""
        try:
            return int(task_identifier), int(dataset_identifier)
        except ValueError as error:
            raise CatalogValidationError(
                "Invalid dataset or task ID. Must be integers."
            ) from error

    def get_allowed_metrics_for_leaderboard(
        self, task_id: int, dataset_id: int
    ) -> Set[str]:
        """
        Get set of allowed metric names for a specific leaderboard (task + dataset).

        Args:
            task_id: Task ID
            dataset_id: Dataset ID

        Returns:
            Set of metric names (e.g., {'AP', 'AP50', 'AP75'})
            Empty set if the leaderboard has no linked metrics

        Raises:
            CatalogPersistenceError: If database query fails
        """
        try:
            metric_names = (
                self.db.query(DBMetric.name)
                .join(DBTaskDatasetMetric, DBMetric.id == DBTaskDatasetMetric.metric_id)
                .filter(
                    DBTaskDatasetMetric.task_id == task_id,
                    DBTaskDatasetMetric.dataset_id == dataset_id,
                )
                .all()
            )

            return {name[0] for name in metric_names}

        except Exception as e:
            raise CatalogPersistenceError(
                f"Failed to retrieve allowed metric names: {e!s}"
            )

    def validate_metrics_for_leaderboard(
        self,
        task_id: int,
        dataset_id: int,
        metric_keys: List[str],
        best_metric: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that all provided metrics are allowed for the leaderboard.

        Args:
            task_id: Task ID
            dataset_id: Dataset ID
            metric_keys: List of metric names from evaluation (keys from metrics dict)
            best_metric: Optional best_metric field to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if all metrics are valid
            - (False, error_message) if validation fails

        Raises:
            CatalogPersistenceError: If database query fails
        """
        try:
            allowed_metrics = self.get_allowed_metrics_for_leaderboard(
                task_id, dataset_id
            )

            if not allowed_metrics:
                return False, (
                    f"No metrics are defined for this leaderboard (task {task_id}, "
                    f"dataset {dataset_id}). Define its metrics before adding or "
                    "editing evaluation metrics."
                )

            invalid_metrics = [m for m in metric_keys if m not in allowed_metrics]

            if invalid_metrics:
                allowed_list = ", ".join(sorted(allowed_metrics))
                invalid_list = ", ".join(invalid_metrics)
                error_msg = (
                    f"Invalid metrics for this leaderboard (task {task_id}, dataset {dataset_id}): {invalid_list}. "
                    f"Allowed metrics: {allowed_list}"
                )
                return False, error_msg

            if best_metric and best_metric not in allowed_metrics:
                allowed_list = ", ".join(sorted(allowed_metrics))
                error_msg = (
                    f"Invalid best_metric '{best_metric}' for this leaderboard. "
                    f"Allowed metrics: {allowed_list}"
                )
                return False, error_msg

            return True, None

        except CatalogPersistenceError:
            raise
        except Exception as e:
            raise CatalogPersistenceError(f"Failed to validate metrics: {e!s}")

    def add_metric_to_leaderboard(
        self, task_id: int, dataset_id: int, metric_name: str
    ) -> dict:
        """
        Add a metric to a leaderboard's allowed metrics list.

        Args:
            task_id: Task ID
            dataset_id: Dataset ID
            metric_name: Metric name (e.g., 'AP', 'WER')

        Returns:
            Dictionary with task_id, dataset_id, metric_id, metric_name

        Raises:
            CatalogNotFoundError: If the task, dataset, or metric does not exist
            CatalogConflictError: If the metric is already linked
            CatalogPersistenceError: If database operation fails
        """
        try:
            task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
            if not task:
                raise CatalogNotFoundError(f"Task with ID {task_id} not found")

            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise CatalogNotFoundError(f"Dataset with ID {dataset_id} not found")

            metric = (
                self.db.query(DBMetric).filter(DBMetric.name == metric_name).first()
            )
            if not metric:
                raise CatalogNotFoundError(f"Metric '{metric_name}' not found")

            existing_link = (
                self.db.query(DBTaskDatasetMetric)
                .filter(
                    and_(
                        DBTaskDatasetMetric.task_id == task_id,
                        DBTaskDatasetMetric.dataset_id == dataset_id,
                        DBTaskDatasetMetric.metric_id == metric.id,
                    )
                )
                .first()
            )

            if existing_link:
                raise CatalogConflictError(
                    f"Metric '{metric_name}' is already linked to leaderboard (task {task_id}, dataset {dataset_id})"
                )

            new_link = DBTaskDatasetMetric(
                task_id=task_id, dataset_id=dataset_id, metric_id=metric.id
            )
            self.db.add(new_link)
            self.db.commit()
            self.db.refresh(new_link)

            return {
                "task_id": str(task_id),
                "dataset_id": str(dataset_id),
                "metric_id": str(metric.id),
                "metric_name": metric.name,
                "metric_direction": metric.direction,
                "created_at": new_link.created_at,
            }

        except CatalogError:
            raise
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(f"Failed to add metric to leaderboard: {e!s}")

    def remove_metric_from_leaderboard(
        self, task_id: int, dataset_id: int, metric_name: str
    ) -> bool:
        """
        Remove a metric from a leaderboard's allowed metrics list.

        Args:
            task_id: Task ID
            dataset_id: Dataset ID
            metric_name: Metric name (e.g., 'AP', 'WER')

        Returns:
            True if removed successfully

        Raises:
            CatalogNotFoundError: If the metric or leaderboard link does not exist
            CatalogPersistenceError: If database operation fails
        """
        try:
            metric = (
                self.db.query(DBMetric).filter(DBMetric.name == metric_name).first()
            )
            if not metric:
                raise CatalogNotFoundError(f"Metric '{metric_name}' not found")

            link = (
                self.db.query(DBTaskDatasetMetric)
                .filter(
                    and_(
                        DBTaskDatasetMetric.task_id == task_id,
                        DBTaskDatasetMetric.dataset_id == dataset_id,
                        DBTaskDatasetMetric.metric_id == metric.id,
                    )
                )
                .first()
            )

            if not link:
                raise CatalogNotFoundError(
                    f"Metric '{metric_name}' is not linked to leaderboard (task {task_id}, dataset {dataset_id})"
                )

            self.db.delete(link)
            self.db.commit()

            return True

        except CatalogError:
            raise
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(
                f"Failed to remove metric from leaderboard: {e!s}"
            )

    def set_leaderboard_metrics(
        self, task_id: int, dataset_id: int, metric_names: List[str]
    ) -> dict:
        """
        Set all allowed metrics for a leaderboard (replaces existing).

        Args:
            task_id: Task ID
            dataset_id: Dataset ID
            metric_names: List of metric names to allow

        Returns:
            Dictionary with task_id, dataset_id, and list of metrics

        Raises:
            CatalogNotFoundError: If the task, dataset, or a metric does not exist
            CatalogPersistenceError: If database operation fails
        """
        try:
            task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
            if not task:
                raise CatalogNotFoundError(f"Task with ID {task_id} not found")

            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise CatalogNotFoundError(f"Dataset with ID {dataset_id} not found")

            metrics = (
                self.db.query(DBMetric).filter(DBMetric.name.in_(metric_names)).all()
            )

            if len(metrics) != len(metric_names):
                found_names = {m.name for m in metrics}
                missing_names = set(metric_names) - found_names
                raise CatalogNotFoundError(
                    f"The following metrics were not found: {', '.join(missing_names)}"
                )

            self.db.query(DBTaskDatasetMetric).filter(
                DBTaskDatasetMetric.task_id == task_id,
                DBTaskDatasetMetric.dataset_id == dataset_id,
            ).delete()

            for metric in metrics:
                new_link = DBTaskDatasetMetric(
                    task_id=task_id, dataset_id=dataset_id, metric_id=metric.id
                )
                self.db.add(new_link)

            self.db.commit()

            return {
                "task_id": str(task_id),
                "dataset_id": str(dataset_id),
                "task_name": task.name,
                "dataset_name": dataset.name,
                "metrics": [
                    {
                        "metric_id": str(m.id),
                        "metric_name": m.name,
                        "metric_direction": m.direction,
                    }
                    for m in metrics
                ],
            }

        except CatalogError:
            raise
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(f"Failed to set leaderboard metrics: {e!s}")

    def get_leaderboard_metrics(self, task_id: int, dataset_id: int) -> dict:
        """
        Get all allowed metrics for a specific leaderboard.

        Args:
            task_id: Task ID
            dataset_id: Dataset ID

        Returns:
            Dictionary with task_id, dataset_id, and list of metrics

        Raises:
            CatalogNotFoundError: If the task or dataset does not exist
            CatalogPersistenceError: If database query fails
        """
        try:
            task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
            if not task:
                raise CatalogNotFoundError(f"Task with ID {task_id} not found")

            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not dataset:
                raise CatalogNotFoundError(f"Dataset with ID {dataset_id} not found")

            task_dataset = (
                self.db.query(TaskDataset)
                .filter(
                    TaskDataset.task_id == task_id,
                    TaskDataset.dataset_id == dataset_id,
                )
                .first()
            )

            links = (
                self.db.query(DBTaskDatasetMetric, DBMetric)
                .join(DBMetric, DBTaskDatasetMetric.metric_id == DBMetric.id)
                .filter(
                    DBTaskDatasetMetric.task_id == task_id,
                    DBTaskDatasetMetric.dataset_id == dataset_id,
                )
                .order_by(
                    DBMetric.name.ilike("%overall%").desc(),
                    DBMetric.name.asc(),
                )
                .all()
            )

            metric_list = []
            for link, metric in links:
                metric_list.append(
                    {
                        "metric_id": str(metric.id),
                        "metric_name": metric.name,
                        "metric_direction": metric.direction,
                        "created_at": link.created_at,
                    }
                )

            return {
                "task_id": str(task_id),
                "dataset_id": str(dataset_id),
                "task_name": task.name,
                "dataset_name": dataset.name,
                "supports_harness": bool(
                    task_dataset and task_dataset.supports_harness
                ),
                "metrics": metric_list,
            }

        except CatalogError:
            raise
        except Exception as e:
            raise CatalogPersistenceError(
                f"Failed to retrieve leaderboard metrics: {e!s}"
            )
