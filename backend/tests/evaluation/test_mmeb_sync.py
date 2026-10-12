"""Contract tests for the official MMEB-v2/v3 leaderboard sync."""

import json
import sqlite3
from datetime import date

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
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.mmeb_sync_service import (
    MANAGED_METHODOLOGY_PREFIX,
    MMEB_CONFIG_URL,
    MmebEntry,
    MmebSyncService,
    fetch_mmeb_leaderboard,
    parse_mmeb_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _component(component_id: int, headers: list[str], score_column: str) -> dict:
    rows = []
    for index in range(50):
        row = [
            index + 1,
            (
                '<a href="https://huggingface.co/example/model-'
                f'{index}">Model {index}</a>'
            ),
            1.5,
            "26-08-20",
        ]
        row.extend(70.0 + index / 100 for _ in headers[4:])
        rows.append(row)
    assert score_column in headers
    return {
        "id": component_id,
        "type": "dataframe",
        "props": {"value": {"headers": headers, "data": rows}},
    }


def _payload() -> dict:
    return {
        "version": "5.9.1",
        "components": [
            _component(
                20,
                [
                    "Rank",
                    "Models",
                    "Size(B)",
                    "Date",
                    "Overall",
                    "Overall-V3🆕",
                    "Text-Overall",
                    "Audio-Overall",
                    "Agent-Overall",
                    "Image-Overall",
                    "Video-Overall",
                    "Visdoc-Overall",
                ],
                "Overall",
            ),
            _component(
                26,
                [
                    "Rank",
                    "Models",
                    "Size(B)",
                    "Date",
                    "Overall-V2",
                    "Image-Overall(V2)",
                    "Video-Overall",
                    "Visdoc-Overall",
                ],
                "Overall-V2",
            ),
        ],
    }


def test_fetches_both_official_mmeb_overall_tables():
    payload = _payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == MMEB_CONFIG_URL
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_mmeb_leaderboard(version="v2", client=client)

    assert len(entries) == 50
    assert entries[0].model_name == "Model 0"
    assert entries[0].model_url == "https://huggingface.co/example/model-0"
    assert entries[0].hf_model_url == "https://huggingface.co/example/model-0"
    assert entries[0].total_params == 1_500_000_000
    assert entries[0].reported_on.isoformat() == "2026-08-20"
    assert entries[0].scores == {"v2": 70.0}


def test_parser_fails_closed_when_an_official_table_is_truncated():
    payload = _payload()
    payload["components"][1]["props"]["value"]["data"] = payload["components"][1][
        "props"
    ]["value"]["data"][:5]

    with pytest.raises(ValueError, match="expected at least 50"):
        parse_mmeb_leaderboard(payload, version="v2")


def test_each_version_parses_independently():
    payload = _payload()
    payload["components"][0]["props"]["value"]["data"].append(
        payload["components"][0]["props"]["value"]["data"][0].copy()
    )
    payload["components"][0]["props"]["value"]["data"][-1][0] = 51
    payload["components"][0]["props"]["value"]["data"][-1][1] = "V3 only"

    v2 = parse_mmeb_leaderboard(payload, version="v2")
    v3 = parse_mmeb_leaderboard(payload, version="v3")

    assert len(v2) == 50
    assert len(v3) == 51


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
        ],
    )
    session = Session(engine)
    task = Task(id=17, name="Embedding models", slug="embedding-models")
    datasets = [
        Dataset(id=1201, name="MMEB-v2", slug="mmeb-v2"),
        Dataset(id=1202, name="MMEB-v3", slug="mmeb-v3"),
    ]
    metrics = [
        Metric(id=1201, name="MMEB-v2 Score", direction="higher_is_better"),
        Metric(id=1202, name="MMEB-v3 Score", direction="higher_is_better"),
    ]
    session.add_all([task, *datasets, *metrics])
    for dataset, metric in zip(datasets, metrics, strict=True):
        session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
        session.add(
            TaskDatasetMetric(
                task_id=task.id,
                dataset_id=dataset.id,
                metric_id=metric.id,
            )
        )
    session.add(
        Paper(
            id=1,
            title="Model paper",
            arxiv_id="2601.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    return session


def _entry() -> MmebEntry:
    return MmebEntry(
        model_name="Example Model",
        model_url="https://arxiv.org/abs/2601.00001",
        total_params=1_500_000_000,
        reported_on=date(2026, 8, 20),
        scores={"v2": 72.5, "v3": 55.0},
        ranks={"v2": 2, "v3": 1},
        is_open=False,
        hf_model_url=None,
    )


def test_sync_replaces_only_managed_rows_and_is_idempotent():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=17,
                dataset_id=1201,
                model_name="stale",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old snapshot",
                metrics={"MMEB-v2 Score": 10.0},
                best_metric="MMEB-v2 Score",
            ),
            Evaluation(
                paper_id=1,
                task_id=17,
                dataset_id=1201,
                model_name="manual",
                methodology="Human curated",
                metrics={"MMEB-v2 Score": 80.0},
                best_metric="MMEB-v2 Score",
            ),
        ]
    )
    session.commit()

    stats = MmebSyncService(session).sync([_entry()], version="v2")

    assert stats.created == 1
    assert stats.deleted == 1
    assert {row.model_name for row in session.query(Evaluation)} == {
        "Example Model",
        "manual",
    }
    synced = session.query(Evaluation).filter_by(model_name="Example Model").one()
    assert synced.paper_id == 1
    assert synced.metrics == {"MMEB-v2 Score": 72.5}
    assert synced.num_parameters == 1_500_000_000
    assert synced.is_open is False

    second = MmebSyncService(session).sync([_entry()], version="v2")

    assert second.created == 0
    assert second.updated == 1
    assert session.query(Evaluation).count() == 2
