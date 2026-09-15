"""Typed responses for the public benchmark discovery endpoints."""

from datetime import datetime

from pydantic import BaseModel

from backend.models.tasks import Task


class DatasetTasks(BaseModel):
    count: int
    results: list[Task]


class LeaderboardMetric(BaseModel):
    metric_id: str
    metric_name: str
    metric_direction: str | None
    created_at: datetime | None


class LeaderboardMetrics(BaseModel):
    task_id: str
    dataset_id: str
    task_name: str
    dataset_name: str
    supports_harness: bool
    metrics: list[LeaderboardMetric]
