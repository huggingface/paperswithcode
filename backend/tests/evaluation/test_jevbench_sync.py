"""Parsing and sync tests for Benchmark Heaven's JevBench API board."""

import json
from datetime import date
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
from backend.services import jevbench_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.jevbench_sync_service import (
    BOARD,
    JEVBENCH_API_URL,
    METRIC_NAME,
    MODEL_IDENTITIES,
    fetch_jevbench,
    parse_jevbench,
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


# The API-board and reference rows of /api/jevbench/latest on 2026-11-12
# (release v1.8.9, method v1.7), trimmed to the fields the parser reads.
FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "jevbench_latest.json").read_text()
TASK_ID = 1032
DATASET_ID = 3353


def _payload() -> dict:
    return json.loads(FIXTURE_TEXT)


def _system(payload: dict, key: str) -> dict:
    return next(system for system in payload["systems"] if system["key"] == key)


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
    session.add(Task(id=TASK_ID, name="Decision Making", slug="decision-making"))
    session.add(Dataset(id=DATASET_ID, name="JevBench", slug="jevbench"))
    session.add(Metric(id=1667, name=METRIC_NAME, direction="higher_is_better"))
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    session.add(
        TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=1667)
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


def test_parse_keeps_the_ranked_api_board_in_official_order():
    entries = parse_jevbench(FIXTURE_TEXT)
    assert len(entries) == 48
    first = entries[0]
    assert (first.name, first.value, first.lab) == (
        "Super Decider",
        Decimal("78.48"),
        "Singularity Compute",
    )
    assert first.detail == (
        "rank 1 of 48 on the API board of release v1.8.9, Composite Score 78.48 "
        "(Intelligence 78.9, Calibration 90.8, Speed 85.3, Cost 64.3), measured "
        "in v1.7.0"
    )
    assert first.evaluated_on == date(2026, 10, 21)
    by_name = {entry.name: entry for entry in entries}
    # A vendor suffix matching the source host is dropped from the row name.
    assert by_name["Drex Max"].lab == "Nace AI"
    assert by_name["Drex Max"].value == Decimal("75.38")
    assert by_name[
        "Mercury Decide (Inception; System One decisions API, served "
        "free on OpenRouter as inception/mercury-decide:free)"
    ].lab == ("Inception")
    assert by_name["Amos 1 large (Scira)"].lab == "Scira"
    # The Jev reference row sits on the API board at rank 15.
    assert by_name["Jev 1.13.0"].detail.startswith("rank 15 of 48")
    assert entries[-1].name == "Qwen3.8 27B (Chutes TEE)"
    # Preliminary, unranked, wrapper and listed-only rows are skipped.
    assert "classifier.dev (fast tier)" not in by_name
    assert not any(
        name.startswith("Microsoft-Decision-1 (Azure Foundry) —") for name in by_name
    )
    assert set(MODEL_IDENTITIES) <= set(by_name)
    values = [entry.value for entry in entries]
    assert values == sorted(values, reverse=True)


def test_fetch_reads_the_latest_api():
    def handler(request):
        assert str(request.url) == JEVBENCH_API_URL
        return httpx.Response(200, text=FIXTURE_TEXT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_jevbench(client) == parse_jevbench(FIXTURE_TEXT)
    assert BOARD_SYNCS["sync_jevbench"].board is BOARD


def _broken(change) -> str:
    payload = _payload()
    change(payload)
    return json.dumps(payload)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<html>", "not JSON"),
        (_broken(lambda p: p.update(benchmark="Other")), "layout changed"),
        (_broken(lambda p: p.update(schema_version=3)), "schema 3"),
        (_broken(lambda p: p["method"].update(label="v1.8")), "method is 'v1.8'"),
        (
            _broken(lambda p: _system(p, "drex-max").update(api_board_rank=None)),
            "not 1..n",
        ),
        (
            _broken(lambda p: _system(p, "drex-max").update(listing="preliminary")),
            "unranked or stale row: Drex Max",
        ),
        (
            _broken(lambda p: _system(p, "drex-max").update(method="v1.6")),
            "unranked or stale row: Drex Max",
        ),
        (
            _broken(lambda p: _system(p, "drex-max").update(composite_score=99)),
            "out of rank order: Drex Max",
        ),
        (
            _broken(lambda p: _system(p, "drex-max").update(composite_score=None)),
            "malformed: Drex Max",
        ),
        (
            _broken(lambda p: _system(p, "kettei-fat").update(name="Myles-G 12B")),
            "twice",
        ),
    ],
)
def test_parser_fails_loudly_on_layout_changes(text, message):
    with pytest.raises(ValueError, match=message):
        parse_jevbench(text)


def test_vendor_is_stripped_only_as_a_whole_trailing_parenthetical():
    payload = _payload()
    _system(payload, "drex-max")["name"] = "Drex Max (hosted (Nace AI)"
    _system(payload, "kettei-fat")["name"] = "kettei-fat (Sqwish (Sqwish)"
    names = {entry.name for entry in parse_jevbench(json.dumps(payload))}
    assert "Drex Max (hosted (Nace AI)" in names
    assert "kettei-fat (Sqwish (Sqwish)" in names
    assert "Myles-G 12B" in names


def test_parser_enforces_entry_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 49)
    with pytest.raises(ValueError, match="has 48 entries"):
        parse_jevbench(FIXTURE_TEXT)


def test_first_run_publishes_reviewed_rows_and_signals_the_rest():
    session = _session()
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_jevbench(FIXTURE_TEXT)
    )
    assert stats.fetched == 48 and stats.created == 6
    assert stats.missing_papers == [] and stats.missing_upstream == []
    assert len(stats.unreviewed) == 41
    rows = _rows(session)
    ranked = sorted(rows.values(), key=lambda row: row.best_rank)
    assert [(row.model_name, row.metrics[METRIC_NAME]) for row in ranked] == [
        ("Drex Max", 75.38),
        # The better of GPT-6 Luna's two reasoning settings.
        ("GPT-6 Luna", 40.39),
        ("GPT-5.6 Luna", 21.36),
        ("Gemini 3.1 Flash-Lite", 16.93),
        ("DeepSeek V4.1 Flash", 6.9),
        ("Qwen3.8-27B", 0.0),
    ]
    assert [row.best_rank for row in ranked] == [1, 2, 3, 4, 5, 6]
    drex = rows["Drex Max"]
    assert (
        drex.is_open
        and drex.hf_model_url == "https://huggingface.co/nace-ai/drex-max-v1"
    )
    assert drex.external_source_url == "https://benchmarkheaven.com/jev-models/api"
    assert drex.methodology.startswith(
        f'{BOARD.managed_prefix} Official leaderboard entry "Drex Max": rank 7 of '
        "48 on the API board of release v1.8.9"
    )
    assert BOARD.managed_head.match(drex.methodology)
    labs = {
        signal.model_name: signal.lab for signal in session.query(ModelReleaseSignal)
    }
    assert labs["Super Decider"] == "Singularity Compute"
    assert labs["Jev 1.13.0"] == "TypeSafe AI"

    again = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_jevbench(FIXTURE_TEXT)
    )
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)


def test_new_release_revises_scores_in_place():
    session = _session()
    LiveLeaderboardSyncService(session, BOARD).sync(parse_jevbench(FIXTURE_TEXT))
    payload = _payload()
    payload["latest_release"] = "v1.8.10"
    _system(payload, "drex-max")["composite_score"] = 75.0
    stats = LiveLeaderboardSyncService(session, BOARD).sync(
        parse_jevbench(json.dumps(payload))
    )
    assert stats.created == 0 and stats.changed == 6
    drex = _rows(session)["Drex Max"]
    assert drex.metrics == {METRIC_NAME: 75.0}
    assert "release v1.8.10" in drex.methodology
