"""Validation and idempotency tests for the living 3D Arena sync."""

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
from backend.services.three_d_arena_sync_service import (
    ARENA_ENDPOINT,
    ARENA_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAME,
    ArenaEntry,
    ThreeDArenaSyncService,
    fetch_arena_leaderboard,
    parse_arena_leaderboard,
)


def _public_payload() -> list[dict]:
    return [
        {
            "name": f"Model-{rank}",
            "rank": str(rank),
            "score": 1500 - rank,
            "votes": rank * 10,
            "open_source": rank % 2 == 0,
        }
        for rank in range(1, 16)
    ]


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
    task = Task(id=13, name="3D generation", slug="3d-generation")
    dataset = Dataset(
        id=1695,
        name="3D Arena (iso3d, living)",
        slug="3d-arena-iso3d-living",
    )
    metric = Metric(
        id=745,
        name=METRIC_NAME,
        direction="higher_is_better",
    )
    session.add_all([task, dataset, metric])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add(
        TaskDatasetMetric(
            task_id=task.id,
            dataset_id=dataset.id,
            metric_id=metric.id,
        )
    )
    papers = [
        Paper(
            id=1,
            title="TRELLIS",
            arxiv_id="2412.01506",
            source="arxiv",
            version="v2",
            is_latest_version=True,
        ),
        Paper(
            id=2,
            title="InstantMesh",
            arxiv_id="2404.07191",
            source="arxiv",
            version="v2",
            is_latest_version=True,
        ),
    ]
    session.add_all(papers)
    session.commit()
    return session


def test_parse_and_fetch_public_leaderboard_contract():
    payload = _public_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ARENA_ENDPOINT
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_arena_leaderboard(client)
    assert entries[0] == ArenaEntry("Model-1", 1, 1499, 10, False)
    assert entries[-1].rank == 15


def test_fetch_retries_429_then_succeeds():
    payload = _public_payload()
    calls = {"n": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_arena_leaderboard(client, sleep=delays.append)

    assert calls["n"] == 2
    assert delays == [1.5]
    assert entries[0].name == "Model-1"


def test_fetch_does_not_retry_client_errors():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_arena_leaderboard(client, sleep=lambda _delay: None)

    assert calls["n"] == 1


def test_fetch_raises_after_retry_budget():
    calls = {"n": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_arena_leaderboard(client, sleep=delays.append)

    assert calls["n"] == 4
    assert delays == [2.0, 4.0, 8.0]


def test_parser_rejects_truncated_or_noncontiguous_data():
    with pytest.raises(ValueError, match="expected 15-100"):
        parse_arena_leaderboard([])
    payload = [
        {
            "name": f"Model-{rank}",
            "rank": rank + (1 if rank == 15 else 0),
            "score": 1500 - rank,
            "votes": rank,
            "open_source": True,
        }
        for rank in range(1, 16)
    ]
    with pytest.raises(ValueError, match="contiguous"):
        parse_arena_leaderboard(payload)


def test_sync_upserts_matched_rows_deletes_only_stale_managed_rows():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=13,
                dataset_id=1695,
                model_name="TRELLIS",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={METRIC_NAME: 1200},
                best_metric=METRIC_NAME,
                external_source_url=ARENA_SOURCE_URL,
                source_url=ARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=13,
                dataset_id=1695,
                model_name="GoneModel",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={METRIC_NAME: 1000},
                best_metric=METRIC_NAME,
                external_source_url=ARENA_SOURCE_URL,
                source_url=ARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=13,
                dataset_id=1695,
                model_name="Manual row",
                methodology="Human curated",
                metrics={METRIC_NAME: 2000},
                best_metric=METRIC_NAME,
                external_source_url=ARENA_SOURCE_URL,
                source_url=ARENA_SOURCE_URL,
                external=True,
            ),
        ]
    )
    session.commit()

    entries = [
        ArenaEntry("TRELLIS", 1, 1400, 5000, True),
        ArenaEntry("InstantMesh", 2, 1300, 9000, True),
        ArenaEntry("Unmatched Product", 3, 1250, 100, False),
    ]
    now = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
    stats = ThreeDArenaSyncService(session).sync(entries, fetched_at=now)

    assert stats.to_dict() == {
        "fetched": 3,
        "matched": 2,
        "created": 1,
        "updated": 1,
        "deleted": 1,
        "unmatched_models": ["Unmatched Product"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"TRELLIS", "InstantMesh", "Manual row"}
    assert rows["TRELLIS"].metrics == {METRIC_NAME: 1400}
    assert rows["TRELLIS"].best_rank == 2
    assert rows["InstantMesh"].best_rank == 3
    assert rows["Manual row"].best_rank == 1
    assert "5000 votes" in rows["TRELLIS"].methodology
    assert rows["InstantMesh"].evaluated_on.isoformat() == "2026-08-04"

    second = ThreeDArenaSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 3


def test_current_model_with_missing_paper_does_not_delete_previous_row():
    session = _session()
    row = Evaluation(
        paper_id=1,
        task_id=13,
        dataset_id=1695,
        model_name="Pixal3D",
        methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
        metrics={METRIC_NAME: 1200},
        best_metric=METRIC_NAME,
        external_source_url=ARENA_SOURCE_URL,
        source_url=ARENA_SOURCE_URL,
        external=True,
    )
    session.add(row)
    session.commit()

    stats = ThreeDArenaSyncService(session).sync(
        [ArenaEntry("Pixal3D", 1, 1300, 20, True)]
    )
    assert stats.missing_papers == ["Pixal3D:2605.10922"]
    assert session.query(Evaluation).filter_by(model_name="Pixal3D").count() == 1


def test_sync_adopts_leftover_row_with_stale_source_url():
    session = _session()
    leftover = Evaluation(
        paper_id=2,
        task_id=13,
        dataset_id=1695,
        model_name="InstantMesh",
        methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
        metrics={METRIC_NAME: 1200},
        best_metric=METRIC_NAME,
        external_source_url="https://arxiv.org/abs/2404.07191",
        source_url="https://arxiv.org/abs/2404.07191",
        external=True,
    )
    session.add(leftover)
    session.commit()

    stats = ThreeDArenaSyncService(session).sync(
        [ArenaEntry("InstantMesh", 1, 1267, 20, True)]
    )
    rows = session.query(Evaluation).all()
    assert stats.created == 0
    assert stats.updated == 1
    assert stats.deleted == 0
    assert len(rows) == 1
    assert rows[0].metrics == {METRIC_NAME: 1267}
    assert rows[0].external_source_url == ARENA_SOURCE_URL
    assert rows[0].source_url == ARENA_SOURCE_URL


def test_sync_deletes_duplicate_leftover_when_canonical_row_exists():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=2,
                task_id=13,
                dataset_id=1695,
                model_name="InstantMesh",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} leftover",
                metrics={METRIC_NAME: 1265},
                best_metric=METRIC_NAME,
                external_source_url="https://arxiv.org/abs/2404.07191",
                source_url="https://arxiv.org/abs/2404.07191",
                external=True,
            ),
            Evaluation(
                paper_id=2,
                task_id=13,
                dataset_id=1695,
                model_name="InstantMesh",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} canonical",
                metrics={METRIC_NAME: 1265},
                best_metric=METRIC_NAME,
                external_source_url=ARENA_SOURCE_URL,
                source_url=ARENA_SOURCE_URL,
                external=True,
            ),
        ]
    )
    session.commit()

    stats = ThreeDArenaSyncService(session).sync(
        [ArenaEntry("InstantMesh", 1, 1267, 20, True)]
    )
    rows = session.query(Evaluation).all()
    assert stats.updated == 1
    assert stats.deleted == 1
    assert stats.created == 0
    assert len(rows) == 1
    assert rows[0].metrics == {METRIC_NAME: 1267}
    assert rows[0].external_source_url == ARENA_SOURCE_URL
    assert rows[0].methodology.startswith(MANAGED_METHODOLOGY_PREFIX)
