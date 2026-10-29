from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Method,
    PaperMethod,
    PaperTask,
    Task,
)
from backend.services import chat_autocomplete_service
from backend.services.chat_autocomplete_service import get_autocomplete_vocabulary


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Task.__table__,
            Method.__table__,
            Dataset.__table__,
            PaperTask.__table__,
            PaperMethod.__table__,
            Evaluation.__table__,
        ],
    )
    return Session(engine)


def test_vocabulary_ranks_used_names_and_skips_unused_and_duplicates(monkeypatch):
    monkeypatch.setattr(chat_autocomplete_service, "_cached", None)
    db = _session()
    db.add_all(
        [
            Task(id=1, name="Object Detection"),
            Task(id=3, name="Unused Task"),
            Method(
                id=1, name="PPO", full_name="Proximal Policy Optimization", slug="ppo"
            ),
            Method(id=2, name="object detection", slug="object-detection"),
            Dataset(id=1, name="COCO", slug="coco"),
        ]
    )
    db.add_all([PaperTask(paper_id=paper, task_id=1) for paper in (1, 2)])
    db.add_all([PaperMethod(paper_id=paper, method_id=1) for paper in (1, 2, 3)])
    db.add(PaperMethod(paper_id=1, method_id=2))
    db.add(Evaluation(id=1, paper_id=1, task_id=1, dataset_id=1, metrics={}))
    db.flush()

    assert get_autocomplete_vocabulary(db) == [
        "PPO",
        "Proximal Policy Optimization",
        "Object Detection",
        "COCO",
    ]
