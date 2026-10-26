"""Parsing and sync tests for the FrontierCS 2 leaderboard."""

from datetime import date
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
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import frontiercs_2_sync_service as service
from backend.services.frontiercs_2_sync_service import (
    FCI,
    FRONTIERCS_2_DATA_URL,
    FRONTIERCS_2_URL,
    MANAGED_METHODOLOGY_PREFIX,
    MODEL_IDENTITIES,
    PASS_RATE,
    FrontierCS2SyncService,
    FrontierCSLeaderboard,
    fetch_frontiercs_2,
    parse_frontiercs_2,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# The MODELS/UPDATED/PASS/ECI constants of
# https://frontier-cs.org/assets/js/fcs2-data.js on 2026-10-26.
SOURCE = (Path(__file__).parent / "fixtures" / "frontiercs_2_data.js").read_text()
TASK_ID = 15
DATASET_ID = 3096


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
        ],
    )
    session = Session(engine)
    session.add(Task(id=TASK_ID, name="Coding Agents", slug="coding-agents"))
    session.add(Dataset(id=DATASET_ID, name="FrontierCS 2", slug="frontiercs-2"))
    session.add(Metric(id=250, name=PASS_RATE, direction="higher_is_better"))
    session.add(Metric(id=251, name=FCI, direction="higher_is_better"))
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    for metric_id in (250, 251):
        session.add(
            TaskDatasetMetric(
                task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=metric_id
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


def _rows(session: Session) -> dict[str, Evaluation]:
    return {
        f"{row.model_name} ({row.harness})": row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
    }


def test_parse_and_fetch_the_leaderboard_constants():
    leaderboard = parse_frontiercs_2(SOURCE)
    assert leaderboard.updated == date(2026, 10, 26)
    assert len(leaderboard.entries) == 14
    by_label = {entry.label: entry for entry in leaderboard.entries}
    opus = by_label["Claude Opus 5.5 (Claude Code)"]
    assert (opus.pass_rate, opus.passes, opus.runs) == (58.3, 28, 48)
    assert (opus.fci, opus.fci_low, opus.fci_high) == (53.3, 44.5, 64.3)
    assert by_label["Gemini 4 Argon (Antigravity)"].upstream_id == "gemini-agy"
    assert by_label["Step 5 Preview (Step Code)"].fci_low == -3.9

    def handler(request):
        assert str(request.url) == FRONTIERCS_2_DATA_URL
        return httpx.Response(200, text=SOURCE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_frontiercs_2(client) == leaderboard


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("PASS={", "PASSES={", "0 PASS literals"),
        ('UPDATED="', 'LAST="', "UPDATED date"),
        ("opus:[58.3,28,48]", "opus:[58.3,27,48]", "disagrees for opus"),
        ("opus:[58.3,28,48]", "opus:[58.3,28]", "missing for opus"),
        ("opus:[53.3,44.5,64.3,48]", "opus:[65,44.5,64.3,48]", "interval"),
        ('h:"Claude Code"', 'h:""', "malformed"),
        ("ECI={astra:", "ECI={astra:foo,x:", "not plain data"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    assert old in SOURCE
    with pytest.raises(ValueError, match=message):
        parse_frontiercs_2(SOURCE.replace(old, new, 1))


def test_parser_enforces_entry_bounds_and_uniqueness(monkeypatch):
    duplicated = SOURCE.replace('h:"Antigravity"', 'h:"Pi"', 1)
    with pytest.raises(ValueError, match="twice"):
        parse_frontiercs_2(duplicated)
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 20)
    with pytest.raises(ValueError, match="14 entries"):
        parse_frontiercs_2(SOURCE)


def test_first_run_creates_every_entry_and_second_run_is_a_no_op():
    session = _session()
    leaderboard = parse_frontiercs_2(SOURCE)
    stats = FrontierCS2SyncService(session).sync(leaderboard)

    assert (stats.fetched, stats.matched, stats.created, stats.changed) == (
        14,
        14,
        14,
        0,
    )
    assert stats.unreviewed == stats.missing_papers == stats.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 14
    opus = rows["Claude Opus 5.5 (Claude Code)"]
    assert opus.best_rank == 1 and opus.best_metric == PASS_RATE
    assert opus.metrics == {PASS_RATE: 58.3, FCI: 53.3}
    assert opus.evaluated_on == date(2026, 10, 26)
    assert opus.external and opus.external_source_url == FRONTIERCS_2_URL
    assert opus.methodology.startswith(
        f'{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "Claude Opus 5.5" '
        "(Claude Code): 58.3% pass rate (28/48 runs beat the human reference), "
        "FCI 53.3 (90% interval 44.5 to 64.3)"
    )
    # One model, two harnesses: two rows on the same paper.
    assert rows["Gemini 4 Argon (Antigravity)"].best_rank == 2
    assert rows["Gemini 4 Argon (Pi)"].metrics == {PASS_RATE: 39.6, FCI: 38.7}
    assert rows["DeepSeek-V4.1-Flash-1017 (DeepSeek Harness)"].is_open
    assert {row.paper_id for row in session.query(PaperTask).all()} == {
        _paper_id(key) for key in _paper_keys()
    }

    again = FrontierCS2SyncService(session).sync(parse_frontiercs_2(SOURCE))
    assert (again.matched, again.created, again.changed) == (14, 0, 0)
    assert len(_rows(session)) == 14


def test_score_updates_revise_the_row_and_unknown_models_are_reported():
    session = _session()
    FrontierCS2SyncService(session).sync(parse_frontiercs_2(SOURCE))
    updated = (
        SOURCE.replace("opus:[58.3,28,48]", "opus:[60.4,29,48]", 1)
        .replace("opus:[53.3,44.5,64.3,48]", "opus:[55.1,46,66,48]", 1)
        .replace('name:"Step 5 Preview"', 'name:"Step 6"', 1)
    )
    stats = FrontierCS2SyncService(session).sync(parse_frontiercs_2(updated))
    assert (stats.changed, stats.created) == (1, 0)
    assert stats.unreviewed == ["Step 6 (Step Code)"]
    assert stats.missing_upstream == ["Step-5-Preview (Step Code)"]
    rows = _rows(session)
    assert rows["Claude Opus 5.5 (Claude Code)"].metrics == {
        PASS_RATE: 60.4,
        FCI: 55.1,
    }
    # Dropped rows are reported, never deleted.
    assert "Step-5-Preview (Step Code)" in rows


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    leaderboard = parse_frontiercs_2(SOURCE)
    FrontierCS2SyncService(session).sync(leaderboard, commit=False)
    assert _rows(session) == {}
    with pytest.raises(RuntimeError, match="refusing"):
        FrontierCS2SyncService(session).sync(
            FrontierCSLeaderboard(leaderboard.updated, leaderboard.entries[:5])
        )


def test_unconfigured_leaderboard_is_refused():
    session = _session()
    session.query(TaskDatasetMetric).filter(TaskDatasetMetric.metric_id == 251).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked"):
        FrontierCS2SyncService(session).sync(parse_frontiercs_2(SOURCE))
