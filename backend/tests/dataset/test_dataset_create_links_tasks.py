import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.models.evaluations import DatasetCreateRequest
from backend.services.catalog_errors import CatalogNotFoundError
from backend.services.dataset_service import DatasetService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_json_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                Task,
                Dataset,
                TaskDataset,
                Evaluation,
                Paper,
                Metric,
                TaskDatasetMetric,
            )
        ],
    )
    session = Session(engine)
    session.add_all(
        [
            Task(id=1, name="Coding", slug="coding", level=0),
            Task(id=2, name="Math", slug="math", level=0),
        ]
    )
    session.commit()
    yield session
    session.close()


def _request(task_ids):
    return DatasetCreateRequest(
        name="New Bench", description="A benchmark.", task_ids=task_ids
    )


def test_create_dataset_links_requested_tasks(db):
    created = DatasetService(db).create_dataset(_request([2, 1, 2]))

    links = db.query(TaskDataset.task_id, TaskDataset.dataset_id).all()
    assert sorted(links) == [(1, int(created.id)), (2, int(created.id))]


def test_create_dataset_rejects_unknown_tasks_without_writing(db):
    with pytest.raises(CatalogNotFoundError, match=r"\[3\]"):
        DatasetService(db).create_dataset(_request([1, 3]))

    assert db.query(Dataset).count() == 0
    assert db.query(TaskDataset).count() == 0
