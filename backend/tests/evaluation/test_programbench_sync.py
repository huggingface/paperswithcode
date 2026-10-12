"""Validation and idempotency tests for the ProgramBench live sync."""

import json
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
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import programbench_sync_service as pb
from backend.services.programbench_sync_service import (
    ALMOST_RESOLVED_METRIC_NAME,
    AVERAGE_PASS_RATE_METRIC_NAME,
    HARNESS_NAME,
    MANAGED_METHODOLOGY_PREFIX,
    PRIMARY_METRIC_NAME,
    PROGRAMBENCH_URL,
    ProgramBenchEntry,
    ProgramBenchSyncService,
    fetch_programbench_leaderboard,
    parse_programbench_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _html(count: int = 15) -> tuple[str, dict[str, pb.PaperIdentity]]:
    identities = {
        f"model-{index}": pb.PaperIdentity(f"https://example.com/model-{index}")
        for index in range(count)
    }
    results = [
        {
            "model": f"Model {index}",
            "provider": "Example AI",
            "slug": f"model-{index}",
            "score": 0.5 + index / 100,
            "date": 1785628800000,
        }
        for index in range(count)
    ]
    rows = "".join(
        f"""
        <tr data-href="/run/model-{index}/" data-provider="Example AI">
          <td><span class="model-name">Model {index}</span></td>
          <td class="col-agent">{HARNESS_NAME}</td>
          <td class="col-num resolved-highlight">{index / 10}%</td>
          <td class="col-num col-almost">{index}%</td>
        </tr>
        """
        for index in range(count)
    )
    return (
        f"""
        <html><body>
          <table class="lb-table"><tbody>{rows}</tbody></table>
          <script>var results = {json.dumps(results)};</script>
        </body></html>
        """,
        identities,
    )


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
    task = Task(id=15, name="Coding Agents", slug="coding-agents")
    dataset = Dataset(id=743, name="ProgramBench", slug="programbench")
    metrics = [
        Metric(id=18 + index, name=name, direction="higher_is_better")
        for index, name in enumerate(
            (
                PRIMARY_METRIC_NAME,
                ALMOST_RESOLVED_METRIC_NAME,
                AVERAGE_PASS_RATE_METRIC_NAME,
            )
        )
    ]
    session.add_all([task, dataset, *metrics])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        [
            TaskDatasetMetric(
                task_id=task.id, dataset_id=dataset.id, metric_id=metric.id
            )
            for metric in metrics
        ]
    )
    session.add_all(
        [
            Paper(
                id=1,
                title="Model A",
                source="external",
                source_url="https://example.com/a",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Model B",
                source="external",
                source_url="https://example.com/b",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def _entry(
    upstream_id: str, model: str, average_test_pass_rate: float
) -> ProgramBenchEntry:
    return ProgramBenchEntry(
        upstream_id=upstream_id,
        model=model,
        provider="Example AI",
        harness=HARNESS_NAME,
        average_test_pass_rate=average_test_pass_rate,
        resolved=1,
        almost_resolved=10,
        evaluated_on=date(2026, 8, 2),
        source_url=f"{PROGRAMBENCH_URL}run/{upstream_id}/",
    )


def test_parse_and_fetch_server_rendered_leaderboard(monkeypatch):
    html, identities = _html()
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", identities)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == PROGRAMBENCH_URL
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_programbench_leaderboard(client)

    assert len(entries) == 15
    assert entries[0].average_test_pass_rate == 50
    assert entries[-1].resolved == 1.4
    assert entries[0].evaluated_on == date(2026, 8, 2)


def test_parser_rejects_truncated_or_unreviewed_run_sets(monkeypatch):
    html, identities = _html(14)
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", identities)
    with pytest.raises(ValueError, match="expected 15-60"):
        parse_programbench_leaderboard(html)

    html, identities = _html()
    identities.pop("model-14")
    monkeypatch.setattr(pb, "MODEL_PAPER_IDENTITIES", identities)
    with pytest.raises(ValueError, match="unreviewed=.*model-14"):
        parse_programbench_leaderboard(html)


def test_sync_upserts_managed_rows_and_preserves_manual_rows(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        pb,
        "MODEL_PAPER_IDENTITIES",
        {
            "model-a": pb.PaperIdentity("https://example.com/a"),
            "model-b": pb.PaperIdentity("https://example.com/b", is_open=True),
        },
    )
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=15,
                dataset_id=743,
                model_name="Old label",
                methodology=(f"{MANAGED_METHODOLOGY_PREFIX} upstream_id=model-a; old"),
                metrics={"Accuracy": 10},
                best_metric="Accuracy",
                external_source_url=f"{PROGRAMBENCH_URL}run/model-a/",
            ),
            Evaluation(
                paper_id=1,
                task_id=15,
                dataset_id=743,
                model_name="Gone model",
                methodology=(f"{MANAGED_METHODOLOGY_PREFIX} upstream_id=gone; old"),
                metrics={"Accuracy": 5},
                best_metric="Accuracy",
                external_source_url=f"{PROGRAMBENCH_URL}run/gone/",
            ),
            Evaluation(
                paper_id=1,
                task_id=15,
                dataset_id=743,
                model_name="Manual model",
                methodology="Human curated",
                metrics={AVERAGE_PASS_RATE_METRIC_NAME: 90},
                best_metric=AVERAGE_PASS_RATE_METRIC_NAME,
            ),
        ]
    )
    session.commit()
    entries = [_entry("model-a", "Model A", 70), _entry("model-b", "Model B", 60)]

    first = ProgramBenchSyncService(session).sync(entries)
    assert first.to_dict() == {
        "fetched": 2,
        "matched": 2,
        "created": 1,
        "updated": 1,
        "deleted": 1,
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"Model A", "Model B", "Manual model"}
    assert rows["Model A"].metrics == {
        PRIMARY_METRIC_NAME: 1,
        ALMOST_RESOLVED_METRIC_NAME: 10,
        AVERAGE_PASS_RATE_METRIC_NAME: 70,
    }
    assert rows["Model A"].best_metric == PRIMARY_METRIC_NAME
    assert rows["Model B"].is_open is True
    assert rows["Model A"].best_rank == 1
    assert rows["Model B"].best_rank == 1
    assert session.query(PaperTask).count() == 2

    second = ProgramBenchSyncService(session).sync(entries)
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 3


def test_dry_run_rolls_back_changes(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        pb,
        "MODEL_PAPER_IDENTITIES",
        {"model-a": pb.PaperIdentity("https://example.com/a")},
    )

    stats = ProgramBenchSyncService(session).sync(
        [_entry("model-a", "Model A", 70)], commit=False
    )

    assert stats.created == 1
    assert session.query(Evaluation).count() == 0
