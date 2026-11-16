"""Parsing and sync tests for the official RSI-Exam leaderboard."""

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
from backend.services import rsi_exam_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.rsi_exam_sync_service import (
    BOARD,
    METRIC_NAME,
    MODEL_IDENTITIES,
    RSI_EXAM_URL,
    fetch_rsi_exam,
    parse_rsi_exam,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# The leaderboard section of https://rsi-exam.ai/ on 2026-11-16 (all three
# panels; only Full is read).
FIXTURE_TEXT = (
    Path(__file__).parent / "fixtures" / "rsi_exam_leaderboard.html"
).read_text()
TASK_ID = 862
DATASET_ID = 3428


def _paper_keys() -> list[str]:
    return sorted({identity.paper_key for identity in MODEL_IDENTITIES.values()})


def _paper_id(key: str) -> int:
    return 1000 + _paper_keys().index(key)


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
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            ModelReleaseSignal.__table__,
        ],
    )
    session = Session(engine)
    session.add(Task(id=TASK_ID, name="Auto-Research", slug="auto-research"))
    session.add(Dataset(id=DATASET_ID, name="RSI-Exam", slug="rsi-exam"))
    session.add(Metric(id=324, name=METRIC_NAME, direction="higher_is_better"))
    session.add(
        TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID, supports_harness=True)
    )
    session.add(
        TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=324)
    )
    for key in _paper_keys():
        arxiv = not key.startswith("https://")
        session.add(
            Paper(
                id=_paper_id(key),
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


def _rows(session: Session) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
    }


def _replace(old: str, new: str, text: str = FIXTURE_TEXT) -> str:
    assert old in text
    return text.replace(old, new, 1)


def test_parse_reads_the_full_board_in_official_order():
    entries = parse_rsi_exam(FIXTURE_TEXT)
    assert len(entries) == 21
    first = entries[0]
    assert (first.name, first.value, first.harness, first.lab) == (
        "Opus 5.5",
        Decimal("0.5357"),
        "Claude Code",
        "Anthropic",
    )
    assert first.detail == (
        "rank 1 of 21 on the RSI-Exam 0.1 Full board (88 tasks), normalised "
        "score 0.5357, run in claude code · max"
    )
    by_name = {entry.name: entry for entry in entries}
    # Four decimals as published, not the Public or Private panel's values.
    assert by_name["Opus 5"].value == Decimal("0.4640")
    assert by_name["Qwen3.8 Max"].harness == "Qwen Code"
    assert by_name["Muse Spark 1.3"].harness == "Muse Code"
    assert by_name["Seed Evolving-0909"].lab == "ByteDance"
    assert entries[-1].name == "Gemini 3.7 Flash"
    assert set(MODEL_IDENTITIES) <= set(by_name)
    values = [entry.value for entry in entries]
    assert values == sorted(values, reverse=True)


def test_fetch_reads_the_homepage():
    def handler(request):
        assert str(request.url) == RSI_EXAM_URL
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_rsi_exam(client) == parse_rsi_exam(FIXTURE_TEXT)
    assert BOARD_SYNCS["sync_rsi_exam"].board is BOARD


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<html>", "no longer names release"),
        (_replace("RSI-Exam 0.1", "RSI-Exam 0.2"), "no longer names release"),
        (_replace('id="lbpanel-full"', 'id="lbpanel-all"'), "panel not found"),
        (
            _replace("over all 88 active tasks", "over all 92 active tasks"),
            "covers 92 tasks",
        ),
        (
            _replace('<text class="hlbrank" x="5" y="95">2</text>', ""),
            "rank None at row 2",
        ),
        (_replace("claude code · max", "openhands · max"), "not reviewed: Opus 5.5"),
        (_replace("claude code · max", "claude code"), "not reviewed: Opus 5.5"),
        (_replace(">0.5357<", ">n/a<"), "malformed: Opus 5.5"),
        (_replace(">0.5357<", ">1.5357<"), "out of range: Opus 5.5"),
        (_replace(">0.5126<", ">0.6126<"), "out of rank order: GPT-6-astra"),
        (_replace(">Fable 5.1<", ">Opus 5.5<"), "twice"),
    ],
    ids=lambda value: value if len(value) < 40 else "",
)
def test_parser_fails_loudly_on_layout_changes(text, message):
    with pytest.raises(ValueError, match=message):
        parse_rsi_exam(text)


def test_parser_enforces_entry_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 22)
    with pytest.raises(ValueError, match="has 21 entries"):
        parse_rsi_exam(FIXTURE_TEXT)


def test_first_run_publishes_reviewed_rows_and_signals_the_rest():
    session = _session()
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_rsi_exam(FIXTURE_TEXT)
    )
    assert stats.fetched == 21 and stats.created == 20
    assert stats.missing_papers == [] and stats.missing_upstream == []
    assert stats.unreviewed == ["Seed Evolving-0909 (Claude Code)"]
    rows = _rows(session)
    ranked = sorted(rows.values(), key=lambda row: row.best_rank)
    assert [(row.model_name, row.harness) for row in ranked[:3]] == [
        ("Claude Opus 5.5", "Claude Code"),
        ("GPT-6 Astra", "Codex"),
        ("Gemini 4 Argon", "Antigravity"),
    ]
    assert [row.best_rank for row in ranked] == list(range(1, 21))
    # The dated snapshot and the release model share the Qwen3.8-Max paper.
    assert rows["Qwen3.8 Max-0902"].paper_id == rows["Qwen3.8 Max"].paper_id
    assert rows["Kimi K3"].is_open and not rows["Claude Opus 5.5"].is_open
    opus = rows["Claude Opus 5.5"]
    assert opus.metrics == {METRIC_NAME: 0.5357}
    assert opus.external_source_url == RSI_EXAM_URL
    assert opus.methodology.startswith(
        f'{BOARD.managed_prefix} Official leaderboard entry "Opus 5.5 (Claude '
        'Code)": rank 1 of 21 on the RSI-Exam 0.1 Full board'
    )
    assert BOARD.managed_head.match(opus.methodology)
    signals = {
        signal.model_name: signal.lab for signal in session.query(ModelReleaseSignal)
    }
    assert signals == {"Seed Evolving-0909": "ByteDance"}

    again = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_rsi_exam(FIXTURE_TEXT)
    )
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)


def test_hand_imported_rows_are_adopted_and_revised_in_place():
    session = _session()
    paper_id = _paper_id("https://www.anthropic.com/claude-opus-5-5")
    session.add(
        Evaluation(
            paper_id=paper_id,
            task_id=TASK_ID,
            dataset_id=DATASET_ID,
            model_name="Claude Opus 5.5",
            harness="Claude Code",
            metrics={METRIC_NAME: "0.5357"},
            best_metric=METRIC_NAME,
            methodology="",
        )
    )
    session.commit()
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_rsi_exam(FIXTURE_TEXT)
    )
    assert (stats.created, stats.adopted) == (19, 1)
    text = _replace(">0.5357<", ">0.5401<")
    stats = LiveLeaderboardSyncService(session, BOARD).sync(parse_rsi_exam(text))
    assert stats.changed == 1
    opus = _rows(session)["Claude Opus 5.5"]
    assert opus.paper_id == paper_id and opus.metrics == {METRIC_NAME: 0.5401}
    assert "normalised score 0.5401" in opus.methodology
