"""Focused tests for the MMEB and directional TextCaps benchmark setup."""

import json
import sqlite3
from datetime import date

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.database.datasets_setup.add_mmeb_textcaps_benchmarks import (
    configure_benchmarks,
)
from backend.models.database import (
    Base,
    Dataset,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _session(*, include_tasks: bool = True, include_papers: bool = True) -> Session:
    sqlite3.register_adapter(list, json.dumps)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            PaperTask.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
        ],
    )
    session = Session(engine)
    if include_tasks:
        session.add_all(
            [
                Task(id=17, name="Embedding models", slug="embedding-models"),
                Task(id=8, name="Image understanding", slug="image-understanding"),
            ]
        )
    if include_papers:
        papers = [
            Paper(
                id=1,
                title="MMEB v2",
                arxiv_id="2507.04590",
                source="arxiv",
                version="v1",
                is_latest_version=True,
                date_published=date(2025, 7, 6),
            ),
            Paper(
                id=2,
                title="MMEB v3",
                arxiv_id="2604.23321",
                source="arxiv",
                version="v1",
                is_latest_version=True,
                date_published=date(2026, 4, 30),
            ),
            Paper(
                id=3,
                title="TextCaps",
                arxiv_id="2003.12462",
                source="arxiv",
                version="v1",
                is_latest_version=True,
                date_published=date(2020, 3, 27),
            ),
        ]
        session.add_all(papers)
        session.flush()
        session.add(
            Dataset(
                id=603,
                name="TextCaps",
                slug="textcaps",
                homepage="https://textvqa.org/textcaps/",
                paper_url="https://paperswithcode.co/paper/2003.12462",
                introducing_paper_id=3,
                introducing_paper_title="TextCaps",
                introduced_date=date(2020, 3, 27),
                introduced_year=2020,
                modalities=["Images", "Text"],
                languages=["English"],
            )
        )
    session.commit()
    return session


def test_configure_benchmarks_is_idempotent_and_links_all_leaderboards():
    session = _session()

    first = configure_benchmarks(session)
    session.commit()
    second = configure_benchmarks(session)
    session.commit()

    assert set(first) == {
        "mmeb-v2",
        "mmeb-v3",
        "textcaps-text-to-image",
        "textcaps-image-to-text",
    }
    assert {slug: dataset.id for slug, dataset in first.items()} == {
        slug: dataset.id for slug, dataset in second.items()
    }
    assert session.query(Dataset).filter(Dataset.slug.in_(first)).count() == 4

    links = session.query(TaskDataset).all()
    assert len(links) == 4
    assert all(link.supports_harness is False for link in links)
    metric_names = {
        metric.name
        for metric in session.query(Metric)
        .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
        .all()
    }
    assert metric_names == {"MMEB-v2 Score", "MMEB-v3 Score", "R@1"}
    assert "Audio" not in second["mmeb-v2"].modalities
    assert "Audio" in second["mmeb-v3"].modalities

    for slug in ("textcaps-text-to-image", "textcaps-image-to-text"):
        dataset = second[slug]
        assert dataset.parent_dataset_id == 603
        assert dataset.variant_type == "variant"
        assert dataset.introducing_paper_id == 3


@pytest.mark.parametrize(
    ("session_kwargs", "message"),
    [
        ({"include_tasks": False}, "Missing task"),
        ({"include_papers": False}, "Missing source paper"),
    ],
)
def test_configure_benchmarks_requires_catalog_dependencies(session_kwargs, message):
    session = _session(**session_kwargs)

    with pytest.raises(RuntimeError, match=message):
        configure_benchmarks(session)
