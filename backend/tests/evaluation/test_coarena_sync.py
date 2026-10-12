"""Validation and idempotency tests for the living CoArena sync."""

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
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.coarena_sync_service import (
    COARENA_ENDPOINT,
    COARENA_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAME,
    CoArenaEntry,
    CoArenaSyncService,
    fetch_coarena_leaderboard,
    parse_coarena_leaderboard,
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
    task = Task(id=7, name="Computer Use Agents", slug="computer-use-agents")
    dataset = Dataset(id=2000, name="CoArena", slug="coarena")
    metric = Metric(id=745, name=METRIC_NAME, direction="higher_is_better")
    session.add_all([task, dataset, metric])
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
                title="Claude Fable 5",
                source="external",
                source_url=("https://www.anthropic.com/news/claude-fable-5-mythos-5"),
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


def _payload_row(index: int) -> dict:
    return {
        "id": f"model-{index}",
        "name": f"Model {index}",
        "model": f"provider-model-{index}",
        "effort": "medium",
        "onlineElo": 1000 + index,
        "elo": 1005 + index,
        "ratingBasis": "bradley_terry",
        "rated": True,
        "hasRuns": True,
        "ratingStatus": "ranked",
        "winRate": 0.4,
        "ci": 30,
        "company": "Example",
    }


def _entry(model_id: str, name: str, elo: float) -> CoArenaEntry:
    return CoArenaEntry(
        id=model_id,
        name=name,
        model=model_id,
        effort="medium",
        elo=elo,
        online_elo=elo + 1,
        rating_basis="bradley_terry",
        rating_status="ranked",
        win_rate=0.5,
        ci=25,
        company="Example",
    )


def test_parse_and_fetch_public_leaderboard_contract():
    payload = {"entries": [_payload_row(index) for index in range(5)]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == COARENA_ENDPOINT
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_coarena_leaderboard(client)

    assert entries[0].id == "model-0"
    assert entries[0].elo == 1005
    assert entries[-1].company == "Example"


def test_parser_accepts_stable_rating_status():
    rows = [_payload_row(index) for index in range(5)]
    rows[0]["ratingStatus"] = "stable"

    entries = parse_coarena_leaderboard({"entries": rows})

    assert entries[0].rating_status == "stable"
    assert entries[1].rating_status == "ranked"


def test_parser_rejects_truncated_duplicate_or_unrated_data():
    with pytest.raises(ValueError, match="expected 5-100"):
        parse_coarena_leaderboard({"entries": []})

    rows = [_payload_row(index) for index in range(5)]
    rows[-1]["id"] = rows[0]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_coarena_leaderboard({"entries": rows})

    rows = [_payload_row(index) for index in range(5)]
    rows[-1]["rated"] = False
    with pytest.raises(ValueError, match="unrated"):
        parse_coarena_leaderboard({"entries": rows})

    rows = [_payload_row(index) for index in range(5)]
    rows[-1]["ratingStatus"] = "pending"
    with pytest.raises(ValueError, match="rating status is invalid"):
        parse_coarena_leaderboard({"entries": rows})


def test_sync_upserts_matched_rows_and_deletes_only_stale_managed_rows():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=7,
                dataset_id=2000,
                model_name="Old Fable label",
                methodology=(f"{MANAGED_METHODOLOGY_PREFIX} upstream_id=fable-5; old"),
                metrics={METRIC_NAME: 900},
                best_metric=METRIC_NAME,
                external_source_url=COARENA_SOURCE_URL,
                source_url=COARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=7,
                dataset_id=2000,
                model_name="Gone model",
                methodology=(f"{MANAGED_METHODOLOGY_PREFIX} upstream_id=gone; old"),
                metrics={METRIC_NAME: 800},
                best_metric=METRIC_NAME,
                external_source_url=COARENA_SOURCE_URL,
                source_url=COARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=7,
                dataset_id=2000,
                model_name="Manual row",
                methodology="Human curated",
                metrics={METRIC_NAME: 1200},
                best_metric=METRIC_NAME,
                external_source_url=COARENA_SOURCE_URL,
                source_url=COARENA_SOURCE_URL,
                external=True,
            ),
        ]
    )
    session.commit()

    entries = [
        _entry("fable-5", "Claude Fable 5", 1080.5),
        _entry("kimi-k3", "Kimi K3", 950.25),
        _entry("unreviewed", "Unreviewed", 900),
    ]
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    stats = CoArenaSyncService(session).sync(entries, fetched_at=now)

    assert stats.to_dict() == {
        "fetched": 3,
        "matched": 2,
        "created": 1,
        "updated": 1,
        "deleted": 1,
        "unmatched_models": ["unreviewed"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"Claude Fable 5", "Kimi K3", "Manual row"}
    assert rows["Claude Fable 5"].metrics == {METRIC_NAME: 1080.5}
    assert rows["Kimi K3"].is_open is True
    assert rows["Manual row"].best_rank == 1
    assert rows["Claude Fable 5"].best_rank == 2
    assert "95% CI ±25" in rows["Claude Fable 5"].methodology

    second = CoArenaSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 3


def test_current_model_with_missing_paper_keeps_previous_row():
    session = _session()
    row = Evaluation(
        paper_id=1,
        task_id=7,
        dataset_id=2000,
        model_name="Gemini 3.6 Flash",
        methodology=(f"{MANAGED_METHODOLOGY_PREFIX} upstream_id=gemini-3-flash; old"),
        metrics={METRIC_NAME: 1000},
        best_metric=METRIC_NAME,
        external_source_url=COARENA_SOURCE_URL,
        source_url=COARENA_SOURCE_URL,
        external=True,
    )
    session.add(row)
    session.commit()

    stats = CoArenaSyncService(session).sync(
        [_entry("gemini-3-flash", "Gemini 3.6 Flash", 1050)]
    )
    assert len(stats.missing_papers) == 1
    assert (
        session.query(Evaluation).filter_by(model_name="Gemini 3.6 Flash").count() == 1
    )


def test_null_company_does_not_block_other_rated_models():
    rows = [_payload_row(index) for index in range(5)]
    rows[0]["company"] = None
    entries = parse_coarena_leaderboard({"entries": rows})
    assert len(entries) == 5
    assert entries[0].company is None
    assert entries[0].id == "model-0"


@pytest.mark.parametrize("company", ["", " ", 42, {}, "x" * 256])
def test_company_still_rejects_malformed_non_null_values(company):
    rows = [_payload_row(index) for index in range(5)]
    rows[0]["company"] = company
    with pytest.raises(ValueError, match="invalid company"):
        parse_coarena_leaderboard({"entries": rows})
