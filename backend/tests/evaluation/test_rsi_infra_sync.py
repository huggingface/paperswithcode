"""Parsing and sync tests for the official RSI-Infra Bench leaderboard."""

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
from backend.services import rsi_infra_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.rsi_infra_sync_service import (
    BOARD,
    METRIC_NAME,
    MODEL_IDENTITIES,
    RSI_INFRA_URL,
    fetch_rsi_infra,
    parse_rsi_infra,
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
    Path(__file__).parent / "fixtures" / "rsi_infra_leaderboard.html"
).read_text()


def test_parse_reads_the_table_in_official_order():
    entries = parse_rsi_infra(FIXTURE_TEXT)
    assert len(entries) == 16
    first = entries[0]
    assert (first.name, first.value, first.harness, first.lab) == (
        "Gemini 4 Neon",
        Decimal("43.22"),
        "Antigravity CLI",
        "Google",
    )
    assert first.detail == (
        "rank 1 of 16, score 43.22, run in Antigravity CLI; per-task speed-ups "
        "LLaVA 3.12x, YOCO 2.30x, NanoChat 1.26x, BAGEL SFT 2.50x, R3 2.19x, "
        "3DGS 4.23x, Slime GRPO 2.88x, Slime OPD 1.95x"
    )
    by_name = {entry.name: entry for entry in entries}
    assert by_name["DeepSeek V4.1 Flash-1017"].harness == "DeepSeek Harness"
    assert by_name["GPT-6 Astra"].detail.endswith(
        "marked 'suspected nerf' on the board"
    )
    assert "released judge" in by_name["Hy4"].detail
    assert "released judge" in by_name["Qwen4-Max"].detail
    assert "released judge" not in by_name["GLM-5.3"].detail
    assert set(by_name) == set(MODEL_IDENTITIES)


def test_fetch_reads_the_leaderboard_page():
    def handler(request):
        assert str(request.url) == RSI_INFRA_URL
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_rsi_infra(client) == parse_rsi_infra(FIXTURE_TEXT)
    assert BOARD_SYNCS["sync_rsi_infra"].board is BOARD


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("RSI-Infra Bench</title>", "Other Bench</title>", "no longer names"),
        ("<table id=board>", "<table id=boards>", "table not found"),
        ("<span class=tl>R3</span>", "<span class=tl>R4</span>", "tasks changed"),
        (">2</a></td>", "></a></td>", "rank '' at row 2"),
        ("<span class=hn>Codex</span>", "<span class=hn>Cursor</span>", "not reviewed"),
        ("<span class=scv>43.22<", "<span class=scv>n/a<", "malformed"),
        ("<span class=scv>36.47<", "<span class=scv>41.47<", "out of rank order"),
        ("<span class=scv>40.00<", "<span class=scv>40.01<", "anchor Claude Opus"),
        (
            "<span class=mfull>Kimi k3.1-pro<",
            "<span class=mfull>Kimi K3.1<",
            "anchors missing",
        ),
        (">3.12<span class=x>", ">-<span class=x>", "7 task speed-ups"),
    ],
)
def test_parser_fails_loudly_on_task_anchor_or_layout_changes(old, new, message):
    with pytest.raises(ValueError, match=message):
        parse_rsi_infra(_replace(old, new, FIXTURE_TEXT))


def test_parser_enforces_entry_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 17)
    with pytest.raises(ValueError, match="has 16 entries"):
        parse_rsi_infra(FIXTURE_TEXT)


def test_first_run_publishes_every_reviewed_row():
    session = _session([BOARD], MODEL_IDENTITIES)
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_rsi_infra(FIXTURE_TEXT)
    )
    assert (stats.fetched, stats.created, stats.unreviewed) == (16, 16, [])
    rows = _rows(session, BOARD.dataset_slug)
    assert rows["Gemini 4 Neon"].best_rank == 1
    assert rows["Claude Opus 5.5"].metrics == {METRIC_NAME: 40.0}
    assert rows["Kimi K3.1 Pro"].is_open and rows["Hy4"].is_open
    assert rows["DeepSeek-V4.1-Flash-1017"].harness == "DeepSeek Harness"
    again = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_rsi_infra(FIXTURE_TEXT)
    )
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)
