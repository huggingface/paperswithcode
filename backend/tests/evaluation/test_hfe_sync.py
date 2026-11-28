"""Parsing and sync tests for the official HFE leaderboard on Kaggle."""

import copy
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
from backend.services import hfe_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.hfe_sync_service import (
    BOARD,
    HFE_URL,
    KAGGLE_API_URL,
    METRIC_NAME,
    MODEL_IDENTITIES,
    fetch_hfe,
    parse_hfe,
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


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "hfe_kaggle_leaderboard.json").read_text()
)
TASK_ID = 21
DATASET_ID = 3585
PASS_AT_1 = "Pass@1"


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
    session.add(Task(id=TASK_ID, name="Reasoning", slug="reasoning"))
    session.add(
        Dataset(
            id=DATASET_ID,
            name="Humanity's First Exam (HFE)",
            slug="humanitys-first-exam-hfe",
        )
    )
    session.add(Metric(id=1400, name=METRIC_NAME, direction="higher_is_better"))
    session.add(Metric(id=47, name=PASS_AT_1, direction="higher_is_better"))
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    for metric_id in (1400, 47):
        session.add(
            TaskDatasetMetric(
                task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=metric_id
            )
        )
    for key in _paper_keys():
        session.add(
            Paper(
                id=_paper_id(key),
                title=key,
                source="external",
                source_url=key,
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    return session


def _rows(session: Session, metric: str = METRIC_NAME) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
        if metric in (row.metrics or {})
    }


def _payload(**changes) -> dict:
    payload = copy.deepcopy(FIXTURE)
    first = payload["rows"][0]
    tasks = {task["benchmarkTaskName"]: task for task in first["taskResults"]}
    for key, value in changes.items():
        if key == "value":
            for task in tasks.values():
                task["result"]["numericResult"]["value"] = value
        elif key == "version":
            tasks["Family pass^4"]["taskVersion"] = value
        elif key == "display":
            tasks["Family pass^4"]["displayType"] = value
        elif key == "drop_task":
            first["taskResults"] = [tasks["(Overall)"]]
        elif key == "overall":
            tasks["(Overall)"]["result"]["numericResult"]["value"] = value
        else:
            first[key] = value
    return payload


def test_parse_reads_every_configuration_as_a_percentage():
    entries = parse_hfe(FIXTURE)
    assert len(entries) == 16
    first = entries[0]
    assert (first.name, first.value, first.lab, first.evaluated_on) == (
        "GPT-6.2 Astra",
        Decimal("90.7"),
        "OpenAI",
        date(2026, 11, 24),
    )
    assert first.detail == (
        "configuration GPT-6.2 Astra Xhigh Reasoning, family pass^4 90.7% (95% CI ±4.7)"
    )
    by_name = {entry.name: entry for entry in entries}
    assert by_name["Claude Opus 5.5"].value == Decimal("70.0")
    assert by_name["Gemini 3.1 Flash-Lite Preview"].value == Decimal("18.5")
    assert set(by_name) == set(MODEL_IDENTITIES)


def test_fetch_posts_the_documented_request_with_the_token(monkeypatch):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_test")

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == KAGGLE_API_URL
        assert request.headers["Authorization"] == "Bearer KGAT_test"
        assert json.loads(request.content) == {
            "ownerSlug": "deepmind",
            "benchmarkSlug": "hfe",
        }
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_hfe(client) == parse_hfe(FIXTURE)
    assert BOARD_SYNCS["sync_hfe"].board is BOARD


def test_fetch_requires_a_token(monkeypatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="KAGGLE_API_TOKEN"):
        fetch_hfe(httpx.Client(transport=httpx.MockTransport(lambda r: None)))


def test_fetch_raises_on_an_http_error(monkeypatch):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_test")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401))
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_hfe(client)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "has no rows"),
        (_payload(version=2), "task version 2"),
        (_payload(display="COUNTS"), "not a percentage"),
        (_payload(drop_task=True), "reports tasks"),
        (_payload(value="n/a"), "malformed"),
        (_payload(value=1.5), "out of range"),
        (_payload(overall=0.5), "overall score differs"),
        (_payload(modelVersionName=""), "no model or configuration name"),
        (
            _payload(candidateClass="BENCHMARK_CANDIDATE_CLASS_AGENT"),
            "not a model configuration",
        ),
        (_payload(modelVersionName="GPT-6.2 Sol"), "more than once"),
    ],
)
def test_parser_fails_loudly_on_shape_changes(payload, message):
    with pytest.raises(ValueError, match=message):
        parse_hfe(payload)


def test_parser_enforces_entry_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 17)
    with pytest.raises(ValueError, match="has 16 entries"):
        parse_hfe(FIXTURE)


def test_first_run_publishes_every_reviewed_row():
    session = _session()
    stats = LiveLeaderboardSyncService(session, BOARD).sync(parse_hfe(FIXTURE))
    assert stats.fetched == 16 and stats.created == 16
    assert stats.unreviewed == [] and stats.missing_papers == []
    rows = _rows(session)
    ranked = sorted(rows.values(), key=lambda row: row.best_rank)
    assert [row.model_name for row in ranked[:3]] == [
        "GPT-6.2 Astra",
        "GPT-6.2 Sol",
        "Gemini 4 Neon",
    ]
    assert [row.best_rank for row in ranked] == list(range(1, 17))
    assert rows["GPT-6.2 Astra"].paper_id == rows["GPT-6.2 Sol"].paper_id
    flash = rows["Gemini 3 Flash"]
    assert flash.metrics == {METRIC_NAME: 33.4} and not flash.is_open
    assert flash.external_source_url == HFE_URL
    assert flash.evaluated_on == date(2026, 11, 16)
    assert flash.methodology.startswith(
        f'{BOARD.managed_prefix} Official leaderboard entry "Gemini 3 Flash '
        'Preview": configuration Gemini 3 Flash High Reasoning'
    )
    assert BOARD.managed_head.match(flash.methodology)

    again = LiveLeaderboardSyncService(session, BOARD).sync(parse_hfe(FIXTURE))
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)


def test_revisions_and_departures_follow_kaggle():
    session = _session()
    LiveLeaderboardSyncService(session, BOARD).sync(parse_hfe(FIXTURE))
    payload = _payload(value=0.9123)
    payload["rows"] = [
        row
        for row in payload["rows"]
        if row["modelVersionName"] != "Gemini 3.1 Flash-Lite Preview"
    ]
    stats = LiveLeaderboardSyncService(session, BOARD).sync(parse_hfe(payload))
    assert stats.changed == 1
    assert stats.deleted == ["Gemini 3.1 Flash-Lite"]
    rows = _rows(session)
    assert rows["GPT-6.2 Astra"].metrics == {METRIC_NAME: 91.2}
    assert "Gemini 3.1 Flash-Lite" not in rows


def test_paper_rows_on_the_pass_at_1_board_are_left_alone():
    session = _session()
    paper_id = _paper_id("https://www.anthropic.com/claude-opus-5-5")
    session.add(
        Evaluation(
            paper_id=paper_id,
            task_id=TASK_ID,
            dataset_id=DATASET_ID,
            model_name="Claude Opus 5.5",
            metrics={PASS_AT_1: 91.2},
            best_metric=PASS_AT_1,
            methodology="HFE paper, Table 4.",
        )
    )
    session.commit()
    stats = LiveLeaderboardSyncService(session, BOARD).sync(parse_hfe(FIXTURE))
    assert (stats.created, stats.adopted) == (16, 0)
    paper_row = _rows(session, PASS_AT_1)["Claude Opus 5.5"]
    assert paper_row.metrics == {PASS_AT_1: 91.2}
    assert paper_row.methodology == "HFE paper, Table 4."
