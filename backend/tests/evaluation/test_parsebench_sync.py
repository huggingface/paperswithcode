"""Validation and idempotency tests for the ParseBench live sync."""

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
from backend.services import parsebench_sync_service as pb
from backend.services.parsebench_sync_service import (
    EXCLUDED_PROVIDERS,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAMES,
    MODEL_PAPER_IDENTITIES,
    PARSEBENCH_CSV_URL,
    PARSEBENCH_SOURCE_URL,
    PRIMARY_METRIC_NAME,
    ParseBenchDiscovery,
    ParseBenchPaperDiscoveryService,
    ParseBenchSyncService,
    fetch_parsebench_leaderboard,
    parse_parsebench_leaderboard,
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
    "Provider,Category,Overall,Tables,Charts,Content_Faithfulness,"
    "Semantic_Formatting,Visual_Grounding,Cost_Per_Page,Cost_Charts,"
    "Cost_Tables,Cost_Text,Cost_Layout,HF_Model_ID\n"
)


def _row(provider: str, overall: float, *, hf: str = "", cost: str = "") -> str:
    return (
        f"{provider},VLM - Open Weight,{overall},{overall + 1},{overall - 1},"
        f"{overall},{overall},{overall},{cost},,,,,{hf}\n"
    )


def _csv(count: int = 40) -> str:
    return HEADER + "".join(
        _row(f"model-{index}", 50 + index / 10, hf=f"org/model-{index}")
        for index in range(count)
    )


def _identities(count: int = 40) -> dict[str, pb.PaperIdentity]:
    return {
        f"model-{index}": pb.external(
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
    task = Task(id=4, name="OCR", slug="ocr")
    dataset = Dataset(id=847, name="ParseBench", slug="parsebench")
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
        for index in range(40)
    )
    session.commit()
    return session


def _discovery(count: int = 40) -> ParseBenchDiscovery:
    return ParseBenchDiscovery(
        papers={
            f"https://example.com/model-{index}": 1000 + index for index in range(count)
        }
    )


def test_reviewed_identities_are_well_formed():
    assert not set(MODEL_PAPER_IDENTITIES) & EXCLUDED_PROVIDERS
    for identity in MODEL_PAPER_IDENTITIES.values():
        assert identity.key
    with pytest.raises(ValueError, match="exactly one stable identity"):
        pb.PaperIdentity()
    with pytest.raises(ValueError, match="title and publication date"):
        pb.PaperIdentity(source_url="https://example.com")


def test_parse_and_fetch_leaderboard_csv():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == PARSEBENCH_CSV_URL
        return httpx.Response(200, text=_csv())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_parsebench_leaderboard(client)

    assert len(entries) == 40
    assert entries[0].provider == "model-0"
    assert entries[0].overall == 50
    assert entries[0].dimensions["Tables"] == 51
    assert entries[0].hf_model_id == "org/model-0"
    assert entries[0].cost_per_page_cents is None
    assert set(entries[0].metrics) == set(METRIC_NAMES)


def test_parser_rejects_malformed_upstream_data():
    with pytest.raises(ValueError, match="expected 40-400"):
        parse_parsebench_leaderboard(_csv(39))
    with pytest.raises(ValueError, match="missing columns"):
        parse_parsebench_leaderboard("Provider,Overall\nA,1\n")
    with pytest.raises(ValueError, match="repeats provider"):
        parse_parsebench_leaderboard(_csv() + _row("model-0", 10))
    with pytest.raises(ValueError, match="outside 0-100"):
        parse_parsebench_leaderboard(_csv() + _row("too-high", 101))
    with pytest.raises(ValueError, match="Tables is invalid"):
        parse_parsebench_leaderboard(
            _csv() + "blank,VLM - Open Weight,50,,50,50,50,50,,,,,,\n"
        )
    with pytest.raises(ValueError, match="HF model id is invalid"):
        parse_parsebench_leaderboard(_csv() + _row("bad-hf", 10, hf="no-slash"))


def test_sync_upserts_managed_rows_and_preserves_manual_rows(monkeypatch):
    session = _session()
    identities = _identities()
    identities.pop("model-39")
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", identities)
    monkeypatch.setattr(pb, "EXCLUDED_PROVIDERS", frozenset({"model-39"}))
    session.add_all(
        [
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="Old label",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=model-0; old",
                metrics={"Accuracy": 10},
                best_metric="Accuracy",
            ),
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="Gone model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=gone; old",
                metrics={"Accuracy": 5},
                best_metric="Accuracy",
            ),
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
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
        + "".join(
            _row(f"model-{index}", 50 + index / 10, hf=f"org/model-{index}")
            for index in range(1, 40)
        )
        + _row("Brand New Product", 95)
        + _row("model-0", 70, cost="5.625")
    )
    entries = parse_parsebench_leaderboard(csv_text)

    first = ParseBenchSyncService(session).sync(entries, discovery=_discovery())
    assert first.to_dict() == {
        "fetched": 41,
        "matched": 39,
        "created": 38,
        "updated": 1,
        "deleted": 1,
        "excluded": 1,
        "unreviewed": ["Brand New Product"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert "Gone model" not in rows and "Old label" not in rows
    assert "model-39" not in rows and "Brand New Product" not in rows
    assert rows["Manual model"].metrics == {PRIMARY_METRIC_NAME: 99}
    updated = rows["model-0"]
    assert updated.metrics[PRIMARY_METRIC_NAME] == 70
    assert updated.metrics["Tables"] == 71
    assert updated.best_metric == PRIMARY_METRIC_NAME
    assert updated.is_open is True
    assert updated.external is True
    assert updated.source_url == PARSEBENCH_SOURCE_URL
    assert updated.hf_model_url is None
    assert "5.625 cents/page" in updated.methodology
    assert rows["model-1"].hf_model_url == "https://huggingface.co/org/model-1"
    assert rows["Manual model"].best_rank == 1
    assert updated.best_rank == 2
    assert session.query(PaperTask).count() == 39

    second = ParseBenchSyncService(session).sync(entries, discovery=_discovery())
    assert second.created == 0
    assert second.updated == 39
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 40


def test_sync_refuses_when_reviewed_coverage_collapses(monkeypatch):
    session = _session()
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", _identities(10))
    with pytest.raises(RuntimeError, match="only 10 reviewed rows"):
        ParseBenchSyncService(session).sync(
            parse_parsebench_leaderboard(_csv()), discovery=_discovery()
        )
    assert session.query(Evaluation).count() == 0


def test_sync_requires_resolved_papers_unless_dry_run(monkeypatch):
    session = _session()
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", _identities())
    entries = parse_parsebench_leaderboard(_csv())
    partial = _discovery(39)

    with pytest.raises(RuntimeError, match="No reviewed paper resolved for 'model-39'"):
        ParseBenchSyncService(session).sync(entries, discovery=partial)
    assert session.query(Evaluation).count() == 0

    stats = ParseBenchSyncService(session).sync(
        entries, discovery=partial, commit=False
    )
    assert stats.missing_papers == ["model-39"]
    assert stats.matched == 39
    assert session.query(Evaluation).count() == 0


def test_discovery_reuses_existing_and_indexes_missing_external_papers(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        pb,
        "MODEL_PAPER_IDENTITIES",
        {
            "Existing A": pb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "Existing A (Thinking)": pb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "New Model": pb.external(
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

    dry = asyncio.run(
        ParseBenchPaperDiscoveryService(session, external_service=External()).discover(
            persist=False
        )
    )
    assert dry.papers == {"https://example.com/model-0": 1000}
    assert dry.would_index == ["https://example.com/new"]

    result = asyncio.run(
        ParseBenchPaperDiscoveryService(session, external_service=External()).discover()
    )
    assert result.papers["https://example.com/model-0"] == 1000
    assert result.papers["https://example.com/new"]
    assert result.indexed_papers == ["https://example.com/new"]
