"""Regression tests for task-dataset membership and benchmark ordering."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    Paper as DBPaper,
    PaperDataset,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.dataset_service import DatasetService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def task_dataset_fixture(db_session):
    task = DBTask(id=1, name="Coding Agents", slug="coding-agents", level=0)
    db_session.add(task)

    datasets = [
        DBDataset(id=1, name="Alpha", slug="alpha"),
        DBDataset(id=2, name="SWE-Bench Verified", slug="swe-bench-verified"),
        DBDataset(id=3, name="LiveCodeBench", slug="livecodebench"),
        DBDataset(id=4, name="Beta", slug="beta"),
    ]
    db_session.add_all(datasets)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2026.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 8)
    ]
    db_session.add_all(papers)

    db_session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
            TaskDataset(task_id=1, dataset_id=3),
            TaskDataset(task_id=1, dataset_id=4),
        ]
    )

    db_session.add_all(
        [
            PaperDataset(paper_id=1, dataset_id=1),
            PaperDataset(paper_id=2, dataset_id=1),
            PaperDataset(paper_id=3, dataset_id=1),
            PaperDataset(paper_id=4, dataset_id=2),
            PaperDataset(paper_id=5, dataset_id=3),
            PaperDataset(paper_id=6, dataset_id=3),
            PaperDataset(paper_id=7, dataset_id=4),
        ]
    )

    metrics = [
        DBMetric(id=1, name="Accuracy", direction="higher_is_better"),
        DBMetric(id=2, name="Pass@1", direction="higher_is_better"),
    ]
    db_session.add_all(metrics)

    # Dataset 3 has two metrics for the same task-dataset pair. The task-filtered
    # dataset query should still return it once.
    db_session.add_all(
        [
            TaskDatasetMetric(task_id=1, dataset_id=2, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=3, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=3, metric_id=2),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=4, metric_id=1),
        ]
    )

    db_session.commit()


def test_task_datasets_use_requested_ordering(db_session):
    task = DBTask(id=1, name="Image Classification", slug="image-classification")
    db_session.add(task)
    db_session.add_all(
        [
            DBDataset(id=1, name="Small", slug="small"),
            DBDataset(id=2, name="Large", slug="large"),
        ]
    )
    db_session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
            PaperDataset(paper_id=1, dataset_id=2),
            PaperDataset(paper_id=2, dataset_id=2),
            PaperDataset(paper_id=3, dataset_id=1),
        ]
    )
    db_session.add_all(
        [
            DBPaper(id=1, title="One", abstract="A", arxiv_id="2026.00001"),
            DBPaper(id=2, title="Two", abstract="B", arxiv_id="2026.00002"),
            DBPaper(id=3, title="Three", abstract="C", arxiv_id="2026.00003"),
        ]
    )
    db_session.commit()

    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert [dataset.slug for dataset in result.results] == ["large", "small"]


def test_task_dataset_ordering_returns_each_dataset_once(
    db_session, task_dataset_fixture
):
    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert [dataset.slug for dataset in result.results] == [
        "alpha",
        "beta",
        "livecodebench",
        "swe-bench-verified",
    ]
    assert (
        len([dataset for dataset in result.results if dataset.slug == "livecodebench"])
        == 1
    )


def test_unfiltered_dataset_queries_use_requested_ordering(
    db_session, task_dataset_fixture
):
    result = DatasetService(db_session).get_datasets(order_by="name", order_dir="asc")

    assert [dataset.name for dataset in result.results] == [
        "Alpha",
        "Beta",
        "LiveCodeBench",
        "SWE-Bench Verified",
    ]


def test_paper_count_merges_per_metric_evaluation_rows(db_session):
    """A single model evaluated on one benchmark across multiple metrics is
    stored as one evaluation row per metric, but the benchmark page merges
    them into a single leaderboard row keyed by
    (paper, task, dataset, model, harness). The task-page `paper_count` must
    report that merged row count, so four per-metric rows count as one entry.
    """
    task = DBTask(id=1, name="Object Counting", slug="object-counting", level=0)
    dataset = DBDataset(id=1, name="Blood Cell Detection", slug="blood-cell-detection")
    db_session.add_all([task, dataset])

    metrics = [
        DBMetric(id=1, name="MAE", direction="lower_is_better"),
        DBMetric(id=2, name="RMSE", direction="lower_is_better"),
        DBMetric(id=3, name="AP", direction="higher_is_better"),
        DBMetric(id=4, name="AP50", direction="higher_is_better"),
    ]
    db_session.add_all(metrics)

    db_session.add(TaskDataset(task_id=1, dataset_id=1))
    db_session.add_all(
        [TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=m.id) for m in metrics]
    )

    db_session.add(
        DBPaper(
            id=1,
            title="Counting Paper",
            abstract="A",
            arxiv_id="2026.00001",
            version="v1",
            is_latest_version=True,
        )
    )

    # Same paper/task/dataset/model, one row per metric — these collapse to a
    # single logical leaderboard row.
    db_session.add_all(
        [
            DBEvaluation(
                id=100 + i,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="CountModel",
                metrics={metric.name: "1.0"},
                best_metric=metric.name,
            )
            for i, metric in enumerate(metrics)
        ]
    )
    db_session.commit()

    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert [dataset.slug for dataset in result.results] == ["blood-cell-detection"]
    assert result.results[0].paper_count == 1


def test_paper_count_distinguishes_models_and_papers(db_session):
    """Distinct models (and distinct papers) on the same benchmark are
    separate leaderboard rows, so the merged `paper_count` reflects each
    unique (paper, model) entry even when they share metrics.
    """
    task = DBTask(id=1, name="Object Counting", slug="object-counting", level=0)
    dataset = DBDataset(id=1, name="Blood Cell Detection", slug="blood-cell-detection")
    db_session.add_all([task, dataset])

    db_session.add(DBMetric(id=1, name="MAE", direction="lower_is_better"))
    db_session.add(DBMetric(id=2, name="RMSE", direction="lower_is_better"))
    db_session.add(TaskDataset(task_id=1, dataset_id=1))
    db_session.add_all(
        [
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=2),
        ]
    )
    db_session.add_all(
        [
            DBPaper(id=1, title="P1", abstract="A", arxiv_id="2026.00001"),
            DBPaper(id=2, title="P2", abstract="B", arxiv_id="2026.00002"),
        ]
    )

    db_session.add_all(
        [
            # Paper 1 / Model A across two metrics -> 1 row.
            DBEvaluation(
                id=101,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="ModelA",
                metrics={"MAE": "1.0"},
                best_metric="MAE",
            ),
            DBEvaluation(
                id=102,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="ModelA",
                metrics={"RMSE": "2.0"},
                best_metric="RMSE",
            ),
            # Paper 1 / Model B -> 1 row.
            DBEvaluation(
                id=103,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="ModelB",
                metrics={"MAE": "1.5"},
                best_metric="MAE",
            ),
            # Paper 2 / Model A -> 1 row (different paper).
            DBEvaluation(
                id=104,
                paper_id=2,
                task_id=1,
                dataset_id=1,
                model_name="ModelA",
                metrics={"MAE": "0.9"},
                best_metric="MAE",
            ),
        ]
    )
    db_session.commit()

    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert result.results[0].paper_count == 3
