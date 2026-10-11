"""Validation and idempotency tests for the ExtractBench live sync."""

import asyncio
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import extractbench_sync_service as eb
from backend.services.extractbench_sync_service import (
    EXCLUDED_PROVIDERS,
    EXTRACTBENCH_CSV_URL,
    EXTRACTBENCH_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAMES,
    MODEL_PAPER_IDENTITIES,
    PRIMARY_METRIC_NAME,
    ExtractBenchDiscovery,
    ExtractBenchPaperDiscoveryService,
    ExtractBenchSyncService,
    fetch_extractbench_leaderboard,
    parse_extractbench_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


HEADER = (
    "Provider,Category,Overall,Short,Medium,Long,Cost_Per_Page,"
    "Word_Grounding,Page_Grounding\n"
)


def _row(
    provider: str,
    overall: float,
    *,
    word: float | None = None,
    page: float | None = None,
    cost: str = "",
) -> str:
    word = overall - 10 if word is None else word
    page = overall - 5 if page is None else page
    return (
        f"{provider},OSS,{overall},{overall},{overall},{overall},{cost},{word},{page}\n"
    )


def _csv(count: int = 30) -> str:
    return HEADER + "".join(
        _row(f"model-{index}", 50 + index / 10) for index in range(count)
    )


def _identities(count: int = 30) -> dict[str, eb.PaperIdentity]:
    return {
        f"model-{index}": eb.external(
            f"https://example.com/model-{index}",
            f"Model {index}",
            "2026-08-01",
            is_open=True,
        )
        for index in range(count)
    }


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
            PaperTask.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=14, name="Agents", slug="agents")
    dataset = Dataset(id=900, name="ExtractBench", slug="extractbench")
    metrics = [
        Metric(id=100 + index, name=name, direction="higher_is_better")
        for index, name in enumerate(METRIC_NAMES)
    ]
    session.add_all([task, dataset, *metrics])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
        for metric in metrics
    )
    session.add_all(
        Paper(
            id=1000 + index,
            title=f"Model {index}",
            source="external",
            source_url=f"https://example.com/model-{index}",
            version="v1",
            is_latest_version=True,
        )
        for index in range(30)
    )
    session.commit()
    return session


def _discovery(count: int = 30) -> ExtractBenchDiscovery:
    return ExtractBenchDiscovery(
        papers={
            f"https://example.com/model-{index}": 1000 + index for index in range(count)
        }
    )


def test_reviewed_identities_are_well_formed():
    assert not set(MODEL_PAPER_IDENTITIES) & EXCLUDED_PROVIDERS
    for identity in MODEL_PAPER_IDENTITIES.values():
        assert identity.key
    with pytest.raises(ValueError, match="exactly one stable identity"):
        eb.PaperIdentity()
    with pytest.raises(ValueError, match="title and publication date"):
        eb.PaperIdentity(source_url="https://example.com")


def test_parse_and_fetch_leaderboard_csv():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == EXTRACTBENCH_CSV_URL
        return httpx.Response(200, text=_csv())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_extractbench_leaderboard(client)

    assert len(entries) == 30
    assert entries[0].provider == "model-0"
    assert entries[0].value_f1 == 50
    assert entries[0].grounding == {"Word Grounding F1": 40, "Page Grounding F1": 45}
    assert entries[0].cost_per_page_usd is None
    assert set(entries[0].metrics) == set(METRIC_NAMES)


def test_parser_omits_grounding_only_for_systems_without_evidence():
    entries = parse_extractbench_leaderboard(
        _csv(29) + _row("no-evidence", 80, word=0, page=0)
    )
    assert entries[-1].metrics == {PRIMARY_METRIC_NAME: 80}

    entries = parse_extractbench_leaderboard(
        _csv(29) + _row("page-only", 80, word=0, page=60)
    )
    assert entries[-1].grounding == {"Word Grounding F1": 0, "Page Grounding F1": 60}


def test_parser_rejects_malformed_upstream_data():
    with pytest.raises(ValueError, match="expected 30-400"):
        parse_extractbench_leaderboard(_csv(29))
    with pytest.raises(ValueError, match="missing columns"):
        parse_extractbench_leaderboard("Provider,Overall\nA,1\n")
    with pytest.raises(ValueError, match="repeats provider"):
        parse_extractbench_leaderboard(_csv() + _row("model-0", 10))
    with pytest.raises(ValueError, match="outside 0-100"):
        parse_extractbench_leaderboard(_csv() + _row("too-high", 101))
    with pytest.raises(ValueError, match="Word Grounding F1 is invalid"):
        parse_extractbench_leaderboard(_csv() + "blank,OSS,50,50,50,50,,,50\n")
    with pytest.raises(ValueError, match="cost is negative"):
        parse_extractbench_leaderboard(_csv() + _row("bad-cost", 10, cost="-1"))


def test_sync_upserts_managed_rows_and_preserves_manual_rows(monkeypatch):
    session = _session()
    identities = _identities()
    identities.pop("model-29")
    monkeypatch.setattr(eb, "MODEL_PAPER_IDENTITIES", identities)
    monkeypatch.setattr(eb, "EXCLUDED_PROVIDERS", frozenset({"model-29"}))
    session.add_all(
        [
            Evaluation(
                paper_id=1000,
                task_id=14,
                dataset_id=900,
                model_name="Old label",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=model-0; old",
                metrics={PRIMARY_METRIC_NAME: 10},
                best_metric=PRIMARY_METRIC_NAME,
            ),
            Evaluation(
                paper_id=1000,
                task_id=14,
                dataset_id=900,
                model_name="Gone model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=gone; old",
                metrics={PRIMARY_METRIC_NAME: 5},
                best_metric=PRIMARY_METRIC_NAME,
            ),
            Evaluation(
                paper_id=1000,
                task_id=14,
                dataset_id=900,
                model_name="Manual model",
                methodology="Human curated",
                metrics={PRIMARY_METRIC_NAME: 99},
                best_metric=PRIMARY_METRIC_NAME,
            ),
        ]
    )
    session.commit()
    csv_text = (
        HEADER
        + "".join(_row(f"model-{index}", 50 + index / 10) for index in range(1, 30))
        + _row("Brand New Product", 95)
        + _row("model-0", 70, word=0, page=0, cost="0.075")
    )
    entries = parse_extractbench_leaderboard(csv_text)

    first = ExtractBenchSyncService(session).sync(entries, discovery=_discovery())
    assert first.to_dict() == {
        "fetched": 31,
        "matched": 29,
        "created": 28,
        "updated": 1,
        "deleted": 1,
        "excluded": 1,
        "unreviewed": ["Brand New Product"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert "Gone model" not in rows and "Old label" not in rows
    assert "model-29" not in rows and "Brand New Product" not in rows
    assert rows["Manual model"].metrics == {PRIMARY_METRIC_NAME: 99}
    updated = rows["model-0"]
    assert updated.metrics == {PRIMARY_METRIC_NAME: 70}
    assert updated.best_metric == PRIMARY_METRIC_NAME
    assert updated.is_open is True
    assert updated.external is True
    assert updated.source_url == EXTRACTBENCH_SOURCE_URL
    assert "$0.075/page" in updated.methodology
    assert "no grounding evidence returned" in updated.methodology
    assert rows["model-1"].metrics["Word Grounding F1"] == pytest.approx(40.1)
    assert rows["Manual model"].best_rank == 1
    assert updated.best_rank == 2
    assert session.query(PaperTask).count() == 29

    second = ExtractBenchSyncService(session).sync(entries, discovery=_discovery())
    assert second.created == 0
    assert second.updated == 29
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 30


def test_sync_refuses_when_reviewed_coverage_collapses(monkeypatch):
    session = _session()
    monkeypatch.setattr(eb, "MODEL_PAPER_IDENTITIES", _identities(10))
    with pytest.raises(RuntimeError, match="only 10 reviewed rows"):
        ExtractBenchSyncService(session).sync(
            parse_extractbench_leaderboard(_csv()), discovery=_discovery()
        )
    assert session.query(Evaluation).count() == 0


def test_sync_refuses_until_metrics_are_linked():
    session = _session()
    session.query(TaskDatasetMetric).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked to the task"):
        ExtractBenchSyncService(session).sync(
            parse_extractbench_leaderboard(_csv()), discovery=_discovery()
        )


def test_sync_requires_resolved_papers_unless_dry_run(monkeypatch):
    session = _session()
    monkeypatch.setattr(eb, "MODEL_PAPER_IDENTITIES", _identities())
    entries = parse_extractbench_leaderboard(_csv())
    partial = _discovery(29)

    with pytest.raises(RuntimeError, match="No reviewed paper resolved for 'model-29'"):
        ExtractBenchSyncService(session).sync(entries, discovery=partial)
    assert session.query(Evaluation).count() == 0

    stats = ExtractBenchSyncService(session).sync(
        entries, discovery=partial, commit=False
    )
    assert stats.missing_papers == ["model-29"]
    assert stats.matched == 29
    assert session.query(Evaluation).count() == 0


def test_discovery_reuses_existing_and_indexes_missing_external_papers(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        eb,
        "MODEL_PAPER_IDENTITIES",
        {
            "Existing A": eb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "Existing A (Evidence)": eb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "New Model": eb.external(
                "https://example.com/new", "New Model", "2026-08-01"
            ),
        },
    )

    class External:
        def add_external_resource(self, payload):
            assert payload.date_published == date(2026, 8, 1)
            paper = Paper(
                title=payload.title,
                source="external",
                source_url=payload.source_url,
                date_published=payload.date_published,
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return SimpleNamespace(paper=SimpleNamespace(id=paper.id))

    service = ExtractBenchPaperDiscoveryService(session, external_service=External())
    dry = asyncio.run(service.discover(persist=False))
    assert dry.papers == {"https://example.com/model-0": 1000}
    assert dry.would_index == ["https://example.com/new"]

    result = asyncio.run(service.discover())
    assert result.papers["https://example.com/model-0"] == 1000
    assert result.papers["https://example.com/new"]
    assert result.indexed_papers == ["https://example.com/new"]
