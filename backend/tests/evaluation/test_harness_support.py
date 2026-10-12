"""
Regression tests for task-dataset harness support validation.
"""

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Metric as DBMetric,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


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
def harness_fixture(db_session):
    db_session.add(
        DBPaper(id=1, title="Paper", abstract="Abstract", arxiv_id="2026.00001")
    )
    db_session.add(DBTask(id=1, name="Coding Agents", slug="coding-agents", level=0))
    db_session.add_all(
        [
            DBDataset(id=1, name="Terminal Bench 2.0", slug="terminal-bench"),
            DBDataset(id=2, name="SWE-Bench Verified", slug="swe-bench-verified"),
            DBDataset(id=3, name="HLE", slug="hle"),
        ]
    )
    db_session.add(DBMetric(id=1, name="Accuracy", direction="higher_is_better"))
    db_session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1, supports_harness=True),
            TaskDataset(task_id=1, dataset_id=2, supports_harness=True),
            TaskDataset(task_id=1, dataset_id=3, supports_harness=False),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=2, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=3, metric_id=1),
        ]
    )
    db_session.commit()


def test_create_evaluation_with_harness_succeeds_when_supported(
    db_session, harness_fixture
):
    evaluation = EvaluationService(db_session).create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=1,
        model_name="GLM-5.1",
        harness="Terminus-2",
        metrics={"Accuracy": "56.1"},
        best_metric="Accuracy",
    )

    assert evaluation.harness == "Terminus-2"


def test_create_swe_bench_verified_evaluation_with_harness_succeeds(
    db_session, harness_fixture
):
    evaluation = EvaluationService(db_session).create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=2,
        model_name="Agent Model",
        harness="Agent Swarm",
        metrics={"Accuracy": "50.0"},
        best_metric="Accuracy",
    )

    assert evaluation.harness == "Agent Swarm"


def test_create_evaluation_with_harness_fails_when_not_supported(
    db_session, harness_fixture
):
    with pytest.raises(ValueError, match="does not support harness values"):
        EvaluationService(db_session).create_evaluation(
            paper_id=1,
            task_id=1,
            dataset_id=3,
            model_name="Agent",
            harness="Claude Code",
            metrics={"Accuracy": "50.0"},
            best_metric="Accuracy",
        )


def test_create_evaluation_without_harness_succeeds_for_any_leaderboard(
    db_session, harness_fixture
):
    service = EvaluationService(db_session)

    supported = service.create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=1,
        model_name="Model A",
        metrics={"Accuracy": "55.0"},
        best_metric="Accuracy",
    )
    unsupported = service.create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=3,
        model_name="Model B",
        metrics={"Accuracy": "45.0"},
        best_metric="Accuracy",
    )

    assert supported.harness is None
    assert unsupported.harness is None


def test_update_evaluation_to_add_harness_fails_when_not_supported(
    db_session, harness_fixture
):
    service = EvaluationService(db_session)
    evaluation = service.create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=3,
        model_name="Model",
        metrics={"Accuracy": "45.0"},
        best_metric="Accuracy",
    )

    with pytest.raises(ValueError, match="does not support harness values"):
        service.update_evaluation(
            int(evaluation.id),
            harness="Claude Code",
            harness_set=True,
        )


def test_moving_harness_evaluation_to_non_supporting_leaderboard_requires_clearing(
    db_session, harness_fixture
):
    service = EvaluationService(db_session)
    evaluation = service.create_evaluation(
        paper_id=1,
        task_id=1,
        dataset_id=1,
        model_name="GLM-5.1",
        harness="Terminus-2",
        metrics={"Accuracy": "56.1"},
        best_metric="Accuracy",
    )

    with pytest.raises(ValueError, match="does not support harness values"):
        service.update_evaluation(int(evaluation.id), dataset_id=3)

    moved = service.update_evaluation(
        int(evaluation.id),
        dataset_id=3,
        harness=None,
        harness_set=True,
    )

    assert moved.dataset_id == "3"
    assert moved.harness is None
