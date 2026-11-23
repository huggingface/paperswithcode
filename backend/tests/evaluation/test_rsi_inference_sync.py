"""Parsing and sync tests for the official RSI-Inference Bench leaderboard."""

import json

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
from backend.services import rsi_inference_sync_service as service
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.rsi_inference_sync_service import (
    BOARDS,
    MODEL_IDENTITIES,
    MODEL_SUPPORT_BOARD,
    OPTIMIZATION_BOARD,
    RATING_BOARD,
    RSI_INFERENCE_DATA_URL,
    fetch_rsi_inference_boards,
    parse_rsi_inference,
)


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


FIXTURE_TEXT = (
    Path(__file__).parent / "fixtures" / "rsi_inference_leaderboard.html"
).read_text()
_PREFIX, _, _REST = FIXTURE_TEXT.partition("window.RSI_LEADERBOARD=")
_BLOB, _, _SUFFIX = _REST.partition(";</script>")
FIXTURE_DATA = json.loads(_BLOB)


def _with(mutate) -> str:
    data = json.loads(_BLOB)
    mutate(data)
    return f"{_PREFIX}window.RSI_LEADERBOARD={json.dumps(data)};</script>{_SUFFIX}"


def test_parse_reads_three_boards_in_official_order():
    boards = parse_rsi_inference(FIXTURE_TEXT)
    assert [board for board, _ in boards] == list(BOARDS)
    rating, support, optimization = (entries for _, entries in boards)
    assert len(rating) == len(support) == len(optimization) == 15
    first = rating[0]
    assert (first.name, first.value, first.harness, first.lab) == (
        "Sonnet-5.5",
        Decimal("2043.92"),
        None,
        "Anthropic",
    )
    assert first.detail == "rank 1 of 15 on the joint board, rating 2043.92"
    assert support[0].value == Decimal("26.67")
    assert {e.name: e.value for e in optimization}["GLM-5.3"] == Decimal("1.2189")
    assert {e.name for e in rating} == set(MODEL_IDENTITIES)


def test_fetch_reads_the_raw_repository_page():
    def handler(request):
        assert str(request.url) == RSI_INFERENCE_DATA_URL
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_rsi_inference_boards(client) == parse_rsi_inference(FIXTURE_TEXT)


def test_incomplete_rows_are_skipped():
    text = _with(lambda data: data["joint"][0].update(complete=False))
    rating = parse_rsi_inference(text)[0][1]
    assert "Sonnet-5.5" not in {entry.name for entry in rating}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(schema="rsi-inference-leaderboard/2"), "schema changed"),
        (lambda d: d["rating"].update(method="bt-elo-v3"), "rating method"),
        (lambda d: d["release"].update(tasks=40), "release has 40 tasks"),
        (lambda d: d["tracks"][0].update(tasks_released=12), "tracks changed"),
        (lambda d: d["joint"][1].update(rank=3), "joint rank 3 at row 2"),
        (lambda d: d["joint"][1].update(rating=2100), "out of rank order"),
        (lambda d: d["optimization"][0].update(speedup="fast"), "malformed"),
        (lambda d: d["model_support"][1].update(agent="Sonnet-5.5"), "twice"),
    ],
)
def test_parser_fails_loudly_on_rating_release_or_layout_changes(mutate, message):
    with pytest.raises(ValueError, match=message):
        parse_rsi_inference(_with(mutate))


def test_parser_enforces_entry_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 16)
    with pytest.raises(ValueError, match="has 15 entries"):
        parse_rsi_inference(FIXTURE_TEXT)


def test_first_run_publishes_each_board_on_its_own_benchmark():
    session = _session(BOARDS, MODEL_IDENTITIES)
    for board, entries in parse_rsi_inference(FIXTURE_TEXT):
        stats = LiveLeaderboardSyncService(session, board).sync(entries)
        assert (stats.created, stats.unreviewed) == (15, [])
    rating = _rows(session, RATING_BOARD.dataset_slug)
    assert rating["Claude Sonnet 5.5"].metrics == {"Elo": 2043.92}
    assert rating["Claude Sonnet 5.5"].best_rank == 1
    support = _rows(session, MODEL_SUPPORT_BOARD.dataset_slug)
    assert support["Claude Sonnet 5.5"].metrics == {"Pass@1": 26.67}
    optimization = _rows(session, OPTIMIZATION_BOARD.dataset_slug)
    assert optimization["Claude Opus 4.8"].metrics == {"Speedup": 1.1394}
    assert (
        rating["DeepSeek-V4.1-Flash"].paper_id
        == rating["DeepSeek-V4.1-Flash-1017"].paper_id
    )
    for board, entries in parse_rsi_inference(FIXTURE_TEXT):
        again = LiveLeaderboardSyncService(session, board).sync(entries)
        assert (again.created, again.changed, again.adopted) == (0, 0, 0)
