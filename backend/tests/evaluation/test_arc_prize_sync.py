"""Validation and ownership tests for the ARC Prize leaderboard sync."""

from datetime import UTC, datetime

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
from backend.services.arc_prize_sync_service import (
    ARC_PRIZE_SOURCE_URL,
    LEGACY_METHODOLOGY_PREFIX,
    MANAGED_METHODOLOGY_PREFIX,
    ArcPrizeEntry,
    ArcPrizeSnapshot,
    ArcPrizeSyncService,
    VersionConfig,
    parse_arc_prize_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


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
        ],
    )
    session = Session(engine)
    task = Task(id=21, name="Reasoning", slug="reasoning")
    accuracy = Metric(id=1, name="Accuracy", direction="higher_is_better")
    rhae = Metric(id=2, name="RHAE", direction="higher_is_better")
    datasets = [
        Dataset(id=67, name="ARC-AGI", slug="arc-agi"),
        Dataset(id=68, name="ARC-AGI-2", slug="arc-agi-2"),
        Dataset(id=1631, name="ARC-AGI-3", slug="arc-agi-3"),
    ]
    session.add_all([task, accuracy, rhae, *datasets])
    for dataset in datasets:
        metric = rhae if dataset.slug == "arc-agi-3" else accuracy
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
                title="Claude Fable 5 and Mythos 5",
                source="external",
                source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Kimi K3",
                arxiv_id="2607.24653",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def _snapshot(version: str, entries: list[ArcPrizeEntry]) -> ArcPrizeSnapshot:
    return ArcPrizeSnapshot(
        version=version,
        generated_at=datetime(2026, 8, 13, 23, 42, tzinfo=UTC),
        entries=tuple(entries),
    )


def _entry(
    version: str,
    model_id: str,
    group: str,
    name: str,
    score: float,
) -> ArcPrizeEntry:
    return ArcPrizeEntry(version, model_id, group, name, score, f"/results/{model_id}")


def test_parser_validates_contract_and_converts_scores_to_percent():
    config = VersionConfig(
        "test",
        "https://example.test/leaderboard.json",
        "test_private",
        "ARC-Test",
        "arc-test",
        "Accuracy",
        2,
        3,
    )
    payload = {
        "version": "test",
        "generatedAt": "2026-08-13T23:42:30.422Z",
        "evaluations": [
            {
                "modelId": f"model-{index}",
                "modelGroup": "example",
                "modelDisplayName": f"Model {index}",
                "datasetId": "test_private",
                "datasetDisplayName": "ARC-Test",
                "score": 0.25 + index / 10,
                "resultsUrl": f"/results/model-{index}",
                "display": True,
            }
            for index in range(2)
        ],
    }

    snapshot = parse_arc_prize_leaderboard(payload, config)

    assert snapshot.version == "test"
    assert snapshot.entries[0].score == 25
    assert snapshot.generated_at.tzinfo == UTC

    payload["evaluations"][1]["modelId"] = "model-0"
    with pytest.raises(ValueError, match="duplicate modelId"):
        parse_arc_prize_leaderboard(payload, config)


def test_parser_rejects_truncation_wrong_dataset_and_invalid_scores():
    config = VersionConfig(
        "test",
        "https://example.test",
        "expected",
        "ARC-Test",
        "arc-test",
        "Accuracy",
        1,
        2,
    )
    with pytest.raises(ValueError, match="expected 1-2"):
        parse_arc_prize_leaderboard(
            {
                "version": "test",
                "generatedAt": "2026-08-13T00:00:00Z",
                "evaluations": [],
            },
            config,
        )
    row = {
        "modelId": "model",
        "modelGroup": "group",
        "modelDisplayName": "Model",
        "datasetId": "wrong",
        "datasetDisplayName": "ARC-Test",
        "score": 0.5,
        "resultsUrl": "",
        "display": True,
    }
    payload = {
        "version": "test",
        "generatedAt": "2026-08-13T00:00:00Z",
        "evaluations": [row],
    }
    with pytest.raises(ValueError, match="datasetId"):
        parse_arc_prize_leaderboard(payload, config)
    row["datasetId"] = "expected"
    row["score"] = 1.1
    with pytest.raises(ValueError, match="outside 0-1"):
        parse_arc_prize_leaderboard(payload, config)


def test_sync_adopts_legacy_preserves_stronger_manual_and_deletes_only_managed():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=21,
                dataset_id=67,
                model_name="Legacy Fable",
                methodology=f"{LEGACY_METHODOLOGY_PREFIX}: old",
                metrics={"Accuracy": 80},
                best_metric="Accuracy",
                external_source_url=ARC_PRIZE_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=2,
                task_id=21,
                dataset_id=68,
                model_name="Verified Kimi",
                methodology="Human curated stronger result",
                metrics={"Accuracy": 55},
                best_metric="Accuracy",
                external_source_url=ARC_PRIZE_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=21,
                dataset_id=68,
                model_name="Stale managed row",
                methodology=(
                    f"{MANAGED_METHODOLOGY_PREFIX} "
                    "identity=source:https://www.anthropic.com/news/claude-fable-5-mythos-5; old"
                ),
                metrics={"Accuracy": 20},
                best_metric="Accuracy",
                external_source_url=ARC_PRIZE_SOURCE_URL,
                external=True,
            ),
        ]
    )
    session.commit()
    snapshots = [
        _snapshot(
            "v1",
            [
                _entry(
                    "v1", "fable-high", "anthropic-claude-fable-5", "Fable High", 90
                ),
                _entry("v1", "fable-low", "anthropic-claude-fable-5", "Fable Low", 70),
            ],
        ),
        _snapshot(
            "v2",
            [_entry("v2", "kimi", "moonshot-kimi-k3", "Kimi K3", 50)],
        ),
        _snapshot(
            "v3",
            [_entry("v3", "fable-v3", "anthropic-claude-fable-5", "Fable V3", 10)],
        ),
    ]

    stats = ArcPrizeSyncService(session).sync(
        snapshots, fetched_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
    )

    assert stats.fetched == 4
    assert stats.selected == 3
    assert stats.adopted == 1
    assert stats.created == 1
    assert stats.suppressed == 1
    assert stats.deleted == 1
    rows = session.query(Evaluation).all()
    assert len(rows) == 3
    fable_v1 = next(row for row in rows if row.dataset_id == 67)
    assert fable_v1.model_name == "Fable High"
    assert fable_v1.metrics == {"Accuracy": 90}
    assert fable_v1.harness is None
    assert fable_v1.methodology.startswith(MANAGED_METHODOLOGY_PREFIX)
    assert (
        next(row for row in rows if row.dataset_id == 68).model_name == "Verified Kimi"
    )

    second = ArcPrizeSyncService(session).sync(snapshots)
    assert second.created == 0
    assert second.updated == 2
    assert second.suppressed == 1
    assert session.query(Evaluation).count() == 3
