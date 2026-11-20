"""Parsing and sync tests for the Science's Last Exam leaderboard boards."""

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
from backend.services import sle_sync_service as service
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.sle_sync_service import (
    BOARD_SPECS,
    BOARDS,
    MODEL_IDENTITIES,
    SLE_LEADERBOARD_URL,
    data_bundle_url,
    fetch_sle_boards,
    parse_sle,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "sle_data.js").read_text()
BUNDLE = "assets/data.946b0c6822a31f7c.js"
TASK_ID = 992
DATASET_IDS = {spec[2]: 3429 + index for index, spec in enumerate(BOARD_SPECS)}
METRIC_IDS = {
    "Composite Score": 1667,
    "Inspire Rate": 1679,
    "Mean score": 1358,
    "Pass Rate": 250,
}


def _boards(text: str = FIXTURE_TEXT) -> dict[str, list]:
    return {board.dataset_slug: entries for board, entries in parse_sle(text)}


def _values(entries) -> dict[str, tuple[str, str | None]]:
    return {entry.name: (str(entry.value), entry.harness) for entry in entries}


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
    session.add(
        Task(id=TASK_ID, name="Scientific Reasoning", slug="scientific-reasoning")
    )
    for name, metric_id in METRIC_IDS.items():
        session.add(Metric(id=metric_id, name=name, direction="higher_is_better"))
    for _, label, slug, metric, _, _ in BOARD_SPECS:
        session.add(Dataset(id=DATASET_IDS[slug], name=label, slug=slug))
        session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_IDS[slug]))
        session.add(
            TaskDatasetMetric(
                task_id=TASK_ID,
                dataset_id=DATASET_IDS[slug],
                metric_id=METRIC_IDS[metric],
            )
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


def _rows(session: Session, slug: str) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_IDS[slug])
        .all()
    }


def _sync_all(session: Session, text: str = FIXTURE_TEXT) -> dict:
    return {
        board.dataset_slug: LiveLeaderboardSyncService(session, board).sync(entries)
        for board, entries in parse_sle(text)
    }


def test_parse_splits_every_assessment_into_its_own_board():
    boards = _boards()
    assert list(boards) == [spec[2] for spec in BOARD_SPECS]
    assert _values(boards["sle-protocol-planning"])["Gemini 4 Argon"] == (
        "46.10",
        "Codex",
    )
    assert _values(boards["sle-scientific-computing"])["GPT-6.1 Sol"] == (
        "73.33",
        "Codex",
    )
    assert _values(boards["sle-experiment-observation"])["MiniMax-M3"] == (
        "3.33",
        "Claude Code",
    )
    composite = _values(boards["science-s-last-exam-sle"])
    assert composite["GPT-6.1 Sol"] == ("44.66", "Codex")
    assert composite["Claude Opus 5"] == ("37.50", "Claude Code")
    assert {entry.harness for entry in boards["sle-hypothesis-discovery"]} == {
        "DiscoveryRSI"
    }
    detail = boards["sle-protocol-planning"][0].detail
    assert detail == (
        "Protocol Planning 57.30 with the Codex harness at high reasoning "
        "effort, board updated 2026-11-10"
    )
    assert all(
        entry.name in MODEL_IDENTITIES
        for entries in boards.values()
        for entry in entries
    )


def test_provisional_scores_and_their_composites_are_skipped():
    boards = _boards()
    assert "Gemini 4 Argon" not in _values(boards["sle-hypothesis-discovery"])
    assert "Gemini 4 Argon" not in _values(boards["science-s-last-exam-sle"])
    assert len(boards["sle-scientific-software-operation"]) == 9
    finished = FIXTURE_TEXT.replace('"status": "in progress",', "")
    assert "Gemini 4 Argon" in _values(_boards(finished)["science-s-last-exam-sle"])


def test_data_bundle_url_finds_the_hashed_bundle():
    page = f'<script src="{BUNDLE}"></script><script src="assets/site.1.js">'
    assert data_bundle_url(page) == f"https://sciences-last-exam.org/{BUNDLE}"
    with pytest.raises(ValueError, match="loads 0 data bundles"):
        data_bundle_url("<html></html>")


def test_fetch_reads_the_page_then_its_bundle():
    def handler(request):
        if str(request.url) == SLE_LEADERBOARD_URL:
            return httpx.Response(200, text=f'<script src="{BUNDLE}"></script>')
        assert str(request.url) == f"https://sciences-last-exam.org/{BUNDLE}"
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_sle_boards(client) == parse_sle(FIXTURE_TEXT)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("leaderboard: {", "board: {", "no leaderboard object"),
        (
            '"metric": "Inspire rate"',
            '"metric": "Hit rate"',
            "Hypothesis Discovery metric",
        ),
        (
            '"members": [\n        "pp",',
            '"members": [\n        "wl",\n        "pp",',
            "composite members",
        ),
        ('"name": "MiniMax-M3",', '"name": "MiMo-V2.6-Pro",', "twice"),
        ('"id": "minimax",', '"id": "minimax-m3",', "unlisted model: minimax"),
        ('"score": 57.3,', '"score": 573,', "outside 0-100"),
        ('"score": 57.3,', '"score": "57.3",', "malformed"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    assert old in FIXTURE_TEXT
    with pytest.raises(ValueError, match=message):
        parse_sle(FIXTURE_TEXT.replace(old, new, 1))


def test_parser_enforces_model_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_MODELS", 10)
    with pytest.raises(ValueError, match="has 9 models"):
        parse_sle(FIXTURE_TEXT)


def test_first_run_adopts_hand_imported_rows_and_is_idempotent():
    session = _session()
    session.add(
        Evaluation(
            paper_id=_paper_id(MODEL_IDENTITIES["GPT-6.1 Sol"].paper_key),
            task_id=TASK_ID,
            dataset_id=DATASET_IDS["sle-scientific-computing"],
            model_name="GPT-6.1 Sol",
            harness="Codex",
            metrics={"Pass Rate": "73.33"},
            best_metric="Pass Rate",
            methodology="Science's Last Exam v1 official leaderboard.",
            is_open=False,
        )
    )
    session.commit()
    stats = _sync_all(session)
    computing = stats["sle-scientific-computing"]
    assert (computing.adopted, computing.created) == (1, 8)
    assert all(
        s.unreviewed == [] and s.missing_papers == [] and s.missing_upstream == []
        for s in stats.values()
    )
    assert [stats[spec[2]].matched for spec in BOARD_SPECS] == [8, 8, 9, 9, 9, 9]

    rows = _rows(session, "sle-scientific-computing")
    gpt = rows["GPT-6.1 Sol"]
    board = BOARDS["sc"]
    assert gpt.methodology.startswith(
        f'{board.managed_prefix} Official leaderboard entry "GPT-6.1 Sol (Codex)": '
        "Scientific Computing 73.33"
    )
    assert gpt.methodology.endswith("Science's Last Exam v1 official leaderboard.")
    assert board.managed_head.match(gpt.methodology)
    assert gpt.external_source_url == SLE_LEADERBOARD_URL and gpt.best_rank == 1
    deepseek = rows["DeepSeek-V4.1-Flash"]
    assert deepseek.is_open and deepseek.hf_model_url == (
        "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash"
    )
    assert not rows["Claude Opus 5"].is_open

    again = _sync_all(session)
    assert all((s.created, s.changed, s.adopted) == (0, 0, 0) for s in again.values())


def test_board_update_revises_scores_in_place():
    session = _session()
    _sync_all(session)
    updated = FIXTURE_TEXT.replace('"updated": "2026-11-10"', '"updated": "2026-11-20"')
    updated = updated.replace('"score": 57.3,', '"score": 60.0,', 1)
    stats = _sync_all(session, updated)
    planning = stats["sle-protocol-planning"]
    assert planning.created == 0 and planning.changed == 9
    row = _rows(session, "sle-protocol-planning")["GPT-6.1 Sol"]
    assert row.metrics == {"Mean score": 60.0}
    assert "board updated 2026-11-20" in row.methodology
