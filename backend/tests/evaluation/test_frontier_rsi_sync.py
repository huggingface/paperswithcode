"""Parsing and sync tests for the official FrontierRSI leaderboard."""

from decimal import Decimal
from pathlib import Path

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
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    ModelReleaseSignal,
    Paper,
    PaperHfArtifact,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import frontier_rsi_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.frontier_rsi_sync_service import (
    BOARD,
    FRONTIER_RSI_DATA_URL,
    METRIC_NAME,
    MODEL_IDENTITIES,
    fetch_frontier_rsi,
    parse_frontier_rsi,
)
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


TASK_ID = 862
TABLES = [
    Paper.__table__,
    Task.__table__,
    Dataset.__table__,
    Metric.__table__,
    TaskDataset.__table__,
    TaskDatasetMetric.__table__,
    Evaluation.__table__,
    PaperTask.__table__,
    HfArtifact.__table__,
    PaperHfArtifact.__table__,
    ModelRelease.__table__,
    ModelReleaseArtifact.__table__,
    ModelProviderAlias.__table__,
    ModelReleaseSignal.__table__,
]


def _session(boards, identities) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=TABLES)
    session = Session(engine)
    session.add(Task(id=TASK_ID, name="Auto-Research", slug="auto-research"))
    metrics: dict[str, int] = {}
    for offset, board in enumerate(boards):
        dataset_id = 9100 + offset
        session.add(Dataset(id=dataset_id, name=board.source, slug=board.dataset_slug))
        if board.metric not in metrics:
            metrics[board.metric] = 500 + len(metrics)
            session.add(
                Metric(
                    id=metrics[board.metric],
                    name=board.metric,
                    direction="higher_is_better",
                )
            )
        session.add(
            TaskDataset(task_id=TASK_ID, dataset_id=dataset_id, supports_harness=True)
        )
        session.add(
            TaskDatasetMetric(
                task_id=TASK_ID, dataset_id=dataset_id, metric_id=metrics[board.metric]
            )
        )
    for index, key in enumerate(sorted({i.paper_key for i in identities.values()})):
        arxiv = not key.startswith("https://")
        session.add(
            Paper(
                id=1000 + index,
                title=key,
                arxiv_id=key if arxiv else None,
                source="arxiv" if arxiv else "external",
                source_url=None if arxiv else key,
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    return session


def _rows(session: Session, slug: str) -> dict[str, Evaluation]:
    dataset = session.query(Dataset).filter(Dataset.slug == slug).one()
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == dataset.id)
        .all()
    }


def _replace(old: str, new: str, text: str) -> str:
    assert old in text
    return text.replace(old, new, 1)


FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "frontier_rsi_data.js").read_text()


def test_parse_ranks_models_like_the_site():
    entries = parse_frontier_rsi(FIXTURE_TEXT)
    assert len(entries) == 13
    first = entries[0]
    assert (first.name, first.value, first.harness, first.lab) == (
        "Gemini 4 Neon",
        Decimal("35.22"),
        "Antigravity CLI",
        "Google",
    )
    assert first.detail == (
        "rank 1 of 13, score 35.22% (avg@4 over 27 tasks), run in Antigravity "
        "CLI at xhigh effort"
    )
    by_name = {entry.name: entry for entry in entries}
    assert by_name["Claude Opus 5.5"].value == Decimal("32.63")
    assert by_name["Inkling 2 Small"].harness == "mini-SWE-agent"
    assert set(by_name) == set(MODEL_IDENTITIES)
    values = [entry.value for entry in entries]
    assert values == sorted(values, reverse=True)


def test_fetch_reads_data_js():
    def handler(request):
        assert str(request.url) == FRONTIER_RSI_DATA_URL
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_frontier_rsi(client) == parse_frontier_rsi(FIXTURE_TEXT)
    assert BOARD_SYNCS["sync_frontier_rsi"].board is BOARD


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<html>", "no longer defines"),
        (_replace('"id": "kernels"', '"id": "agents"', FIXTURE_TEXT), "categories"),
        (
            _replace('"category": "pretrain"', '"category": "agents"', FIXTURE_TEXT),
            "no category",
        ),
        (
            _replace('"harness": "Codex"', '"harness": "OpenHands"', FIXTURE_TEXT),
            "not reviewed",
        ),
        (_replace('"effort": "max"', '"effort": "high"', FIXTURE_TEXT), "two setups"),
        (_replace('"avg": 0.75', '"avg": 1.75', FIXTURE_TEXT), "out of range"),
        (
            _replace(
                '"model": "Gemini 4 Neon"', '"model": "GPT-6.2 Sol"', FIXTURE_TEXT
            ),
            "twice",
        ),
    ],
    ids=lambda value: value if len(value) < 40 else "",
)
def test_parser_fails_loudly_on_task_set_or_layout_changes(text, message):
    with pytest.raises(ValueError, match=message):
        parse_frontier_rsi(text)


def test_parser_pins_the_task_count(monkeypatch):
    monkeypatch.setattr(service, "TASK_COUNT", 28)
    with pytest.raises(ValueError, match="lists 27 tasks"):
        parse_frontier_rsi(FIXTURE_TEXT)


def test_first_run_publishes_every_reviewed_row():
    session = _session([BOARD], MODEL_IDENTITIES)
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_frontier_rsi(FIXTURE_TEXT)
    )
    assert (stats.fetched, stats.created, stats.unreviewed) == (13, 13, [])
    rows = _rows(session, BOARD.dataset_slug)
    assert rows["Gemini 4 Neon"].best_rank == 1
    assert rows["Gemini 4 Neon"].metrics == {METRIC_NAME: 35.22}
    assert rows["Inkling-2-Small"].is_open
    assert rows["GPT-6.2 Sol"].paper_id == rows["GPT-6.2 Astra"].paper_id
    assert BOARD.managed_head.match(rows["Claude Opus 5.5"].methodology)
    again = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_frontier_rsi(FIXTURE_TEXT)
    )
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)
