import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset,
    Metric,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.leaderboard_metric_service import LeaderboardMetricService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_json_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@pytest.fixture
def service():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (Task, Dataset, Metric, TaskDataset, TaskDatasetMetric)
        ],
    )
    session = Session(engine)
    session.add(Task(id=1, name="Coding", slug="coding", level=0))
    session.add_all(
        [
            Dataset(id=1, name="Linked", slug="linked"),
            Dataset(id=2, name="Unlinked", slug="unlinked"),
        ]
    )
    session.add(Metric(id=1, name="Accuracy", direction="higher_is_better"))
    session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
        ]
    )
    session.commit()
    yield LeaderboardMetricService(session)
    session.close()


def test_linked_metrics_are_accepted(service):
    assert service.validate_metrics_for_leaderboard(1, 1, ["Accuracy"], "Accuracy") == (
        True,
        None,
    )


def test_unlinked_metric_is_rejected(service):
    valid, error = service.validate_metrics_for_leaderboard(1, 1, ["F1"])

    assert not valid
    assert "F1" in error


def test_leaderboard_without_metric_links_rejects_any_metric(service):
    valid, error = service.validate_metrics_for_leaderboard(
        1, 2, ["Accuracy"], "Accuracy"
    )

    assert not valid
    assert "No metrics are defined" in error
