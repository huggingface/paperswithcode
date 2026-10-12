"""Contract and idempotency tests for the official MMTEB v2 API sync."""

import json
import sqlite3
from datetime import UTC, datetime

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
    HfArtifact,
    Metric,
    Paper,
    PaperHfArtifact,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.mmteb_sync_service import (
    BENCHMARK_NAME,
    LANES,
    LEGACY_METHODOLOGY_PREFIX,
    MANAGED_METHODOLOGY_PREFIX,
    MMTEB_API_URL,
    MmtebEntry,
    MmtebSyncService,
    fetch_mmteb_leaderboard,
    parse_mmteb_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _api_row(index: int) -> dict:
    arxiv_id = f"2501.{index:05d}"
    return {
        "rank": index + 1,
        "model": {
            "name": f"example/model-{index}",
            "url": f"https://huggingface.co/example/model-{index}",
            "citation": (
                "@misc{model, eprint={" + arxiv_id + "}, archivePrefix={arXiv}}"
            ),
            "totalParamsB": 1.5,
            "openWeights": True,
        },
        "meanTask": 0.7,
        "scoresByTaskType": {"Retrieval": 0.8, "Reranking": 0.6},
    }


def _payload(row_count: int = 100) -> dict:
    return {
        "benchmarkName": BENCHMARK_NAME,
        "taskTypes": ["Retrieval", "Reranking"],
        "tasks": ["ExampleRetrieval", "ExampleReranking"],
        "tasksMeta": [],
        "rows": [_api_row(index) for index in range(row_count)],
        "aggregations": ["mean_task", "mean_task_type", "task_types"],
        "showZeroShot": True,
    }


def _entry(
    model_name: str,
    arxiv_ids: tuple[str, ...],
    *,
    model_url: str,
) -> MmtebEntry:
    return MmtebEntry(
        model_name=model_name,
        model_url=model_url,
        api_rank=1,
        mean_task=0.72,
        scores_by_task_type={"Retrieval": 0.81, "Reranking": 0.63},
        arxiv_ids=arxiv_ids,
        total_params=1_500_000_000,
        is_open=True,
        hf_model_url=model_url,
    )


def _session() -> Session:
    sqlite3.register_adapter(list, json.dumps)
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
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
        ],
    )
    session = Session(engine)
    tasks = [
        Task(id=17, name="Embedding models", slug="embedding-models"),
        Task(id=23, name="Retrieval", slug="retrieval"),
        Task(id=510, name="Text Reranking", slug="text-reranking"),
    ]
    dataset = Dataset(id=106, name="MMTEB v2", slug="mmteb-v2")
    metrics = [
        Metric(id=165, name="MMTEB Score", direction="higher_is_better"),
        Metric(id=1130, name="Retrieval", direction="higher_is_better"),
        Metric(id=1129, name="Rerank", direction="higher_is_better"),
    ]
    session.add_all([*tasks, dataset, *metrics])
    for task, metric in zip(tasks, metrics, strict=True):
        session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
        session.add(
            TaskDatasetMetric(
                task_id=task.id,
                dataset_id=dataset.id,
                metric_id=metric.id,
            )
        )
    session.add_all(
        [
            Paper(
                id=1,
                title="Alpha",
                arxiv_id="2501.00001",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Beta current",
                arxiv_id="2501.00002",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=3,
                title="Beta previous",
                arxiv_id="2501.00003",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=4,
                title="External model",
                source="external",
                source_url="https://huggingface.co/example/external",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    artifact = HfArtifact(
        id=1,
        kind="model",
        repo_id="example/beta",
        url="https://huggingface.co/example/beta",
    )
    session.add(artifact)
    session.flush()
    session.add(PaperHfArtifact(paper_id=2, hf_artifact_id=artifact.id))
    session.commit()
    return session


def test_parse_and_fetch_official_mmteb_api_contract():
    payload = _payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == MMTEB_API_URL
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_mmteb_leaderboard(client)

    assert len(entries) == 100
    assert entries[0].model_name == "model-0"
    assert entries[0].arxiv_ids == ("2501.00000",)
    assert entries[0].total_params == 1_500_000_000
    assert entries[0].hf_model_url == "https://huggingface.co/example/model-0"
    assert entries[0].scores_by_task_type == {
        "Retrieval": 0.8,
        "Reranking": 0.6,
    }


def test_parser_fails_closed_on_wrong_benchmark_or_truncated_payload():
    payload = _payload()
    payload["benchmarkName"] = "MTEB(English, v2)"
    with pytest.raises(ValueError, match="benchmark name"):
        parse_mmteb_leaderboard(payload)

    with pytest.raises(ValueError, match="expected at least"):
        parse_mmteb_leaderboard(_payload(5))


def test_sync_fails_closed_when_full_payload_loses_lane_scores():
    session = _session()
    entries = [
        _entry(
            f"model-{index}",
            ("2501.00001",),
            model_url=f"https://huggingface.co/example/model-{index}",
        )
        for index in range(100)
    ]
    entries = [
        MmtebEntry(
            **{
                **entry.__dict__,
                "mean_task": None,
            }
        )
        for entry in entries
    ]

    with pytest.raises(RuntimeError, match="only 0 scored rows"):
        MmtebSyncService(session).sync(entries, lane_id="overall")

    assert session.query(Evaluation).count() == 0


def test_sync_fails_closed_when_full_payload_loses_arxiv_citations():
    session = _session()
    entries = [
        _entry(
            f"model-{index}",
            (),
            model_url=f"https://huggingface.co/example/model-{index}",
        )
        for index in range(100)
    ]

    with pytest.raises(RuntimeError, match="resolved only 0 arXiv-backed rows"):
        MmtebSyncService(session).sync(entries, lane_id="overall")

    assert session.query(Evaluation).count() == 0


def test_sync_fails_closed_on_large_regression_from_managed_row_count():
    session = _session()
    overall = LANES["overall"]
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=17,
                dataset_id=106,
                model_name=f"old-{index}",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} prior sync",
                metrics={overall.metric_name: 70.0},
                best_metric=overall.metric_name,
            )
            for index in range(50)
        ]
    )
    session.commit()
    entries = [
        _entry(
            f"model-{index}",
            ("2501.00001",) if index < 20 else (),
            model_url=f"https://huggingface.co/example/model-{index}",
        )
        for index in range(100)
    ]

    with pytest.raises(RuntimeError, match="refusing a drop over 50%"):
        MmtebSyncService(session).sync(entries, lane_id="overall")

    assert session.query(Evaluation).count() == 50


def test_sync_keeps_only_arxiv_resolved_models_and_is_idempotent():
    session = _session()
    overall = LANES["overall"]
    session.add_all(
        [
            Evaluation(
                paper_id=4,
                task_id=17,
                dataset_id=106,
                model_name="external",
                methodology=f"{LEGACY_METHODOLOGY_PREFIX} old snapshot",
                metrics={overall.metric_name: 75.0},
                best_metric=overall.metric_name,
                external_source_url=MMTEB_API_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=17,
                dataset_id=106,
                model_name="manual",
                methodology="Human curated",
                metrics={overall.metric_name: 60.0},
                best_metric=overall.metric_name,
            ),
        ]
    )
    session.commit()
    entries = [
        _entry(
            "alpha",
            ("2501.00001",),
            model_url="https://huggingface.co/example/alpha",
        ),
        _entry(
            "beta",
            ("2501.00002", "2501.00003"),
            model_url="https://huggingface.co/example/beta",
        ),
        _entry(
            "missing-local",
            ("2501.99999",),
            model_url="https://huggingface.co/example/missing-local",
        ),
        _entry(
            "no-paper",
            (),
            model_url="https://huggingface.co/example/no-paper",
        ),
        _entry(
            "manual",
            ("2501.00001",),
            model_url="https://huggingface.co/example/manual",
        ),
    ]
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

    stats = MmtebSyncService(session).sync(entries, lane_id="overall", fetched_at=now)

    assert stats.matched == 2
    assert stats.created == 2
    assert stats.deleted == 1
    assert stats.no_arxiv_models == ["no-paper"]
    assert stats.missing_papers == ["missing-local:2501.99999"]
    assert stats.unmanaged_conflicts == ["manual"]
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"alpha", "beta", "manual"}
    assert rows["alpha"].paper_id == 1
    assert rows["beta"].paper_id == 2
    assert rows["alpha"].metrics == {overall.metric_name: 72.0}
    assert rows["alpha"].num_parameters == 1_500_000_000
    assert rows["alpha"].hf_model_url == "https://huggingface.co/example/alpha"
    assert rows["alpha"].is_open is True
    assert rows["alpha"].methodology.startswith(MANAGED_METHODOLOGY_PREFIX)

    second = MmtebSyncService(session).sync(
        entries,
        lane_id="overall",
        fetched_at=now,
    )
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 3


@pytest.mark.parametrize(
    ("lane_id", "expected"),
    [("retrieval", 81.0), ("reranking", 63.0)],
)
def test_task_type_lanes_use_their_exact_api_score(lane_id: str, expected: float):
    session = _session()
    entry = _entry(
        "alpha",
        ("2501.00001",),
        model_url="https://huggingface.co/example/alpha",
    )

    MmtebSyncService(session).sync([entry], lane_id=lane_id)

    lane = LANES[lane_id]
    task = session.query(Task).filter_by(slug=lane.task_slug).one()
    row = session.query(Evaluation).filter_by(task_id=task.id).one()
    assert row.best_metric == lane.metric_name
    assert row.metrics == {lane.metric_name: expected}


def test_dry_run_rolls_back_all_evaluation_and_paper_changes():
    session = _session()
    entry = _entry(
        "alpha",
        ("2501.00001",),
        model_url="https://huggingface.co/example/alpha",
    )

    stats = MmtebSyncService(session).sync(
        [entry],
        lane_id="overall",
        commit=False,
    )

    assert stats.created == 1
    assert session.query(Evaluation).count() == 0
    assert session.query(Paper).filter_by(id=1).one().hf_models in (None, [])
