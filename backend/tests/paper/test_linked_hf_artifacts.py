"""Stored Hugging Face links returned with paper detail resources."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import Base, HfArtifact, PaperHfArtifact
from backend.services import paper_relation_loader
from backend.services.paper_relation_loader import PaperRelationLoader, PaperRelations


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[HfArtifact.__table__, PaperHfArtifact.__table__]
    )
    with Session(engine) as session:
        for ident, kind, repo_id, downloads in [
            (1, "model", "org/small", 10),
            (2, "model", "org/popular", 900),
            (3, "model", "org/medium", 50),
            (4, "space", "org/demo", 5),
            (5, "dataset", "org/other-paper-data", 1),
        ]:
            prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}[kind]
            session.add(
                HfArtifact(
                    id=ident,
                    kind=kind,
                    repo_id=repo_id,
                    url=f"https://huggingface.co/{prefix}{repo_id}",
                    downloads=downloads,
                )
            )
        session.add_all(
            [PaperHfArtifact(paper_id=1, hf_artifact_id=i) for i in (1, 2, 3, 4)]
            + [PaperHfArtifact(paper_id=2, hf_artifact_id=5)]
        )
        session.commit()
        yield session
    engine.dispose()


def test_linked_hf_artifacts_are_popular_first_and_capped_per_kind(db, monkeypatch):
    monkeypatch.setattr(paper_relation_loader, "LINKED_HF_ARTIFACT_LIMIT", 2)
    relations = PaperRelationLoader(db).load_linked_hf_artifacts(
        [1, 2], PaperRelations()
    )

    first = relations.linked_hf_artifacts[1]
    assert first.models == [
        "https://huggingface.co/org/popular",
        "https://huggingface.co/org/medium",
    ]
    assert first.datasets == []
    assert first.spaces == ["https://huggingface.co/spaces/org/demo"]
    assert relations.linked_hf_artifacts[2].datasets == [
        "https://huggingface.co/datasets/org/other-paper-data"
    ]
