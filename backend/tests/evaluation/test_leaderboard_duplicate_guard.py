"""One leaderboard entry per model, whichever paper the row is filed on."""

import pytest
from sqlalchemy import BigInteger, CheckConstraint, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset,
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.catalog_errors import CatalogConflictError
from backend.services.evaluation_entry_identity import leaderboard_model_key
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


@pytest.fixture
def service():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # SQLite cannot create tables whose checks call PostgreSQL JSONB functions.
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table
            for table in Base.metadata.sorted_tables
            if not any(
                isinstance(constraint, CheckConstraint)
                and "jsonb" in str(constraint.sqltext)
                for constraint in table.constraints
            )
        ],
    )
    db = sessionmaker(autoflush=False, bind=engine)()
    db.add_all(
        [
            Paper(
                id=1,
                title="Model card",
                source="external",
                source_url="https://huggingface.co/infly/Infinity-Parser2-Pro",
            ),
            Paper(id=2, title="Technical report", arxiv_id="2607.07836"),
            Task(id=1, name="OCR", slug="ocr", level=0),
            Dataset(id=1, name="olmOCR-Bench", slug="olmocr-bench"),
            Metric(id=1, name="Accuracy", direction="higher_is_better"),
            TaskDataset(task_id=1, dataset_id=1, supports_harness=True),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
        ]
    )
    db.commit()
    yield EvaluationService(db)
    db.close()


def _create(service, paper_id, model_name, harness=None, score="87.6"):
    return service.create_evaluation(
        paper_id=paper_id,
        task_id=1,
        dataset_id=1,
        model_name=model_name,
        harness=harness,
        metrics={"Accuracy": score},
        best_metric="Accuracy",
    )


def test_model_key_ignores_case_and_separators_but_not_symbols():
    assert leaderboard_model_key("I-DLM-32B", None) == leaderboard_model_key(
        "I-DLM (32B)", ""
    )
    assert leaderboard_model_key("Kimi K3 Max", None) == leaderboard_model_key(
        "Kimi K3 (max)", None
    )
    assert leaderboard_model_key("DAT", None) != leaderboard_model_key("DAT+", None)
    assert leaderboard_model_key("VGAE", None) != leaderboard_model_key("VGAE*", None)


def test_same_model_from_a_twin_paper_is_rejected(service):
    first = _create(service, 1, "Infinity-Parser2-Pro")

    with pytest.raises(CatalogConflictError, match=f"evaluation {first.id}"):
        _create(service, 2, "infinity parser2 pro")


def test_another_harness_or_model_is_a_separate_entry(service):
    _create(service, 1, "GLM-5.1", harness="Terminus-2")
    _create(service, 1, "GLM-5.1", harness="Claude Code")
    _create(service, 2, "GLM-5.1+")


def test_renaming_onto_another_entry_is_rejected(service):
    _create(service, 1, "Chandra")
    other = _create(service, 2, "Chandra 2", score="85.8")

    with pytest.raises(CatalogConflictError):
        service.update_evaluation(other.id, model_name="chandra")
    # Edits that keep the row's identity stay allowed.
    assert service.update_evaluation(other.id, metrics={"Accuracy": "85.9"})
