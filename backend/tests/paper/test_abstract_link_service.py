from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Framework,
    Method,
    Paper,
    PaperAbstractMention,
    PaperMethodExclusion,
)
from backend.services.abstract_link_service import (
    abstract_sha,
    judge_paper,
    store_paper_mentions,
    stored_abstract_shas,
)
from backend.services.abstract_mention_service import CatalogEntity, build_index
from backend.services.paper_relation_loader import PaperRelationLoader, PaperRelations


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "TEXT"


ABSTRACT = (
    "We train with GRPO on GQA-style attention. Grouped-Query Attention (GQA) "
    "cuts memory, and results on GQA hold. Agents improve."
)


class FakeJudge:
    name = "fake-judge"

    def __init__(self, scores):
        self.scores = scores
        self.requests = []

    def score(self, title, abstract, requests):
        self.requests.extend(requests)
        return {r.key: self.scores.get(r.key, 0.0) for r in requests}


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Method.__table__,
            Dataset.__table__,
            Framework.__table__,
            PaperAbstractMention.__table__,
            PaperMethodExclusion.__table__,
        ],
    )
    db = Session(engine)
    db.add(
        Paper(
            id=1,
            title="GQA paper",
            abstract=ABSTRACT,
            source="external",
            source_url="https://example.com/gqa",
            version="v1",
            is_latest_version=True,
        )
    )
    db.add_all(
        [
            Method(id=10, name="GRPO", slug="grpo", description="RL algorithm"),
            Method(
                id=11,
                name="Grouped-Query Attention",
                slug="grouped-query-attention",
                description="Attention with shared key/value heads",
            ),
            Method(id=12, name="Agent", slug="agent"),
            Dataset(id=20, name="GQA", slug="gqa", description="Visual QA benchmark"),
        ]
    )
    db.commit()
    return db


def _index():
    return build_index(
        [
            CatalogEntity("method", 10, "GRPO", "grpo", mode="always"),
            CatalogEntity(
                "method",
                11,
                "Grouped-Query Attention",
                "grouped-query-attention",
                full_name="Grouped-Query Attention (GQA)",
                mode="always",
            ),
            CatalogEntity("method", 12, "Agent", "agent", mode="never"),
            CatalogEntity("dataset", 20, "GQA", "gqa", mode="always"),
        ]
    )


def test_modes_judge_and_shared_spans_decide_links():
    db = _session()
    judge = FakeJudge({("method", 11): 0.9, ("dataset", 20): 0.1})
    paper = db.get(Paper, 1)

    rows = judge_paper(db, paper, _index(), judge)

    linked = {(r.entity_type, r.entity_id, r.surface) for r in rows if r.linked}
    assert ("method", 10, "GRPO") in linked  # always, clean match: no judge call
    assert ("method", 11, "Grouped-Query Attention (GQA)") in linked
    assert ("method", 11, "GQA") in linked  # shared name won by the method
    assert not any(r.entity_id == 20 and r.linked for r in rows)
    assert not any(r.entity_id == 12 for r in rows if r.linked)  # mode never
    assert {r.key for r in judge.requests} == {("method", 11), ("dataset", 20)}
    assert all(r.abstract_sha == abstract_sha(ABSTRACT) for r in rows)


def test_curator_exclusions_remove_method_links():
    db = _session()
    db.add(PaperMethodExclusion(paper_id=1, method_id=10))
    db.commit()

    rows = judge_paper(db, db.get(Paper, 1), _index(), FakeJudge({}))

    assert not any(r.entity_id == 10 for r in rows)


def test_loader_serves_only_linked_mentions_of_the_current_abstract():
    db = _session()
    paper = db.get(Paper, 1)
    rows = judge_paper(
        db, paper, _index(), FakeJudge({("method", 11): 0.9, ("dataset", 20): 0.1})
    )
    store_paper_mentions(db, 1, rows)
    db.commit()
    assert stored_abstract_shas(db) == {1: abstract_sha(ABSTRACT)}

    mentions = _served(db)[1]
    assert [(m.surface, m.entity_type, m.slug) for m in mentions][:2] == [
        ("GRPO", "method", "grpo"),
        ("GQA", "method", "grouped-query-attention"),
    ]
    assert all(ABSTRACT[m.start : m.end] == m.surface for m in mentions)

    paper.abstract = ABSTRACT + " Revised."
    db.commit()
    assert _served(db) == {}


def _served(db):
    relations = PaperRelations()
    PaperRelationLoader(db)._load_abstract_mentions([1], relations)
    return relations.abstract_mentions
