"""Parsing and adoption tests for the Surge AI Chartography board."""

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
from backend.services import surge_chartography_sync_service as service
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.surge_chartography_sync_service import (
    BOARD,
    METRIC_NAME,
    MODEL_IDENTITIES,
    SURGE_CHARTOGRAPHY_URL,
    fetch_surge_chartography,
    parse_surge_chartography,
)
from backend.tests.evaluation.model_evidence import add_release_evidence


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


HTML = (Path(__file__).parent / "fixtures" / "surge_chartography.html").read_text()
NO_TOOLS_HTML = (
    Path(__file__).parent / "fixtures" / "surge_chartography_no_tools.html"
).read_text()

HAND_IMPORTED_ROWS = {
    "Claude Opus 5.5 (with tools)": 89.0,
    "Claude Fable 5.1 (with tools)": 88.4,
    "Claude Opus 5 (with tools)": 83.4,
    "Claude Fable 5.2 (with tools)": 91.6,
    "Inkling 2 Small (with tools)": 82.1,
}
NO_TOOLS_ROWS = {
    "Claude Opus 5.5 (no tools)": 66.3,
    "Gemini 3.8 Flash (no tools)": 40.9,
}
TASK_ID = 8
DATASET_ID = 2701
WITH_TOOLS_DATASET_ID = 2679


def _paper_keys() -> list[str]:
    return sorted({identity.paper_key for identity in MODEL_IDENTITIES.values()})


def _paper_id(key: str) -> int:
    return 1000 + _paper_keys().index(key)


def _identity(model_name: str):
    return next(
        identity
        for identity in MODEL_IDENTITIES.values()
        if model_name.startswith(f"{identity.model_name} (")
    )


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
        Task(id=TASK_ID, name="Image Understanding", slug="image-understanding")
    )
    session.add(
        Dataset(
            id=DATASET_ID, name="Chartography (no tools)", slug="chartography-no-tools"
        )
    )
    session.add(
        Dataset(id=WITH_TOOLS_DATASET_ID, name="Chartography", slug="chartography")
    )
    session.add(Metric(id=47, name=METRIC_NAME, direction="higher_is_better"))
    for dataset_id in (DATASET_ID, WITH_TOOLS_DATASET_ID):
        session.add(TaskDataset(task_id=TASK_ID, dataset_id=dataset_id))
        session.add(
            TaskDatasetMetric(task_id=TASK_ID, dataset_id=dataset_id, metric_id=47)
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


def _seed_production(session: Session) -> None:
    for dataset_id, rows in (
        (WITH_TOOLS_DATASET_ID, HAND_IMPORTED_ROWS),
        (DATASET_ID, NO_TOOLS_ROWS),
    ):
        for model_name, score in rows.items():
            identity = _identity(model_name)
            session.add(
                Evaluation(
                    paper_id=_paper_id(identity.paper_key),
                    task_id=TASK_ID,
                    dataset_id=dataset_id,
                    model_name=model_name,
                    metrics={METRIC_NAME: score},
                    methodology=f"Hand-reviewed notes for {model_name}.",
                    best_metric=METRIC_NAME,
                    is_open=identity.is_open,
                    num_parameters=123 if model_name.startswith("Inkling") else None,
                    external=True,
                )
            )
    session.commit()


def _sync(session: Session, entries, **kwargs):
    return LiveLeaderboardSyncService(session, BOARD).sync(entries, **kwargs)


def _rows(
    session: Session, dataset_id: int = WITH_TOOLS_DATASET_ID
) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == dataset_id)
        .all()
    }


def test_parse_and_fetch_the_leaderboard_block():
    entries = parse_surge_chartography(HTML)
    assert len(entries) == 42
    first = entries[0]
    assert (first.label, first.value, first.detail) == (
        "GPT 6.2 Astra",
        Decimal("90.7"),
        "90.7% Pass@1 (Max reasoning)",
    )
    by_label = {entry.label: entry for entry in entries}
    assert by_label["Inkling"].detail.endswith("(High reasoning)")
    assert by_label["Inkling 2 Small"].detail.endswith("(xHigh reasoning)")
    assert by_label["Mistral Large 3"].detail.endswith("(default)")
    assert by_label["Claude Opus 5.5"].detail == "89.6% Pass@1 (Adaptive/Max)"
    assert (by_label["GPT 6.2 Astra"].lab, by_label["Inkling"].lab) == ("OpenAI", "")

    def handler(request):
        assert str(request.url) == SURGE_CHARTOGRAPHY_URL
        assert "Mozilla/5.0" in request.headers["user-agent"]
        return httpx.Response(200, text=HTML)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": service.USER_AGENT},
    )
    assert fetch_surge_chartography(client) == entries


def test_page_without_the_harbor_harness_is_refused():
    with pytest.raises(ValueError, match="Harbor harness"):
        parse_surge_chartography(NO_TOOLS_HTML)
    with pytest.raises(ValueError, match="Harbor harness"):
        parse_surge_chartography(HTML.replace(service.HARBOR_DATASET_URL, ""))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("Chartography Leaderboard", "Leaderboard", "0 'Chartography Leaderboard'"),
        ('data-score="90.7"', 'data-score="91"', "not a percentage"),
        ('data-score="90.7"', 'data-score="abc"', "invalid"),
        ("head-rank-table-brand", "brand", "row 1 layout changed"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    with pytest.raises(ValueError, match=message):
        parse_surge_chartography(HTML.replace(old, new, 1))


def test_parser_enforces_row_bounds_range_and_uniqueness(monkeypatch):
    out_of_range = HTML.replace('data-score="90.7"', 'data-score="190.7"', 1).replace(
        ">90.7<", ">190.7<", 1
    )
    with pytest.raises(ValueError, match="outside 0-100"):
        parse_surge_chartography(out_of_range)
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 100)
    with pytest.raises(ValueError, match="42 rows"):
        parse_surge_chartography(HTML)
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 25)
    duplicated = HTML.replace("4 Neon (High reasoning)", "4 Carbon (High reasoning)")
    with pytest.raises(ValueError, match="twice"):
        parse_surge_chartography(duplicated)


def test_first_run_publishes_to_the_with_tools_board_only():
    session = _session()
    _seed_production(session)
    stats = _sync(session, parse_surge_chartography(HTML))

    assert stats.fetched == 42
    assert (stats.matched, stats.adopted, stats.created, stats.changed) == (
        42,
        5,
        37,
        0,
    )
    assert stats.excluded == 0
    assert stats.unreviewed == [] and stats.auto_matched == []
    assert stats.missing_papers == [] and stats.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 42
    astra = rows["GPT-6.2 Astra (with tools)"]
    assert astra.best_rank == 1 and astra.metrics == {METRIC_NAME: 90.7}
    assert astra.methodology == (
        f'{BOARD.managed_prefix} Official leaderboard entry "GPT 6.2 Astra": '
        f"90.7% Pass@1 (Max reasoning), listed at {SURGE_CHARTOGRAPHY_URL}. "
        f"{service.PROTOCOL}"
    )
    opus = rows["Claude Opus 5.5 (with tools)"]
    assert opus.metrics == {METRIC_NAME: 89.6}
    assert opus.methodology.endswith(
        f"{service.PROTOCOL} Hand-reviewed notes for Claude Opus 5.5 (with tools)."
    )
    assert rows["Inkling 2 Small (with tools)"].num_parameters == 123
    assert rows["DeepSeek-V4-Flash (with tools)"].is_open

    assert {
        name: row.metrics[METRIC_NAME]
        for name, row in _rows(session, DATASET_ID).items()
    } == NO_TOOLS_ROWS
    assert all(
        row.methodology.startswith("Hand-reviewed")
        for row in _rows(session, DATASET_ID).values()
    )

    again = _sync(session, parse_surge_chartography(HTML))
    assert (again.adopted, again.created, again.changed) == (0, 0, 0)
    assert _rows(session)["GPT-6.2 Astra (with tools)"].methodology == (
        astra.methodology
    )


def test_score_and_configuration_updates_revise_the_row():
    session = _session()
    _seed_production(session)
    _sync(session, parse_surge_chartography(HTML))
    updated = (
        HTML.replace("6.2 Astra (Max reasoning)", "6.2 Astra (xHigh reasoning)", 1)
        .replace('data-score="90.7"', 'data-score="91.25"', 1)
        .replace(">90.7<", ">91.25<", 1)
    )
    stats = _sync(session, parse_surge_chartography(updated))
    assert (stats.changed, stats.created, stats.adopted) == (1, 0, 0)
    astra = _rows(session)["GPT-6.2 Astra (with tools)"]
    assert astra.metrics == {METRIC_NAME: 91.25}
    assert '"GPT 6.2 Astra": 91.25% Pass@1 (xHigh reasoning)' in astra.methodology


def test_new_labels_are_auto_matched_or_handed_to_the_radar():
    session = _session()
    _seed_production(session)
    session.add(
        Paper(
            id=2001,
            title="Kimi K3.5: Open Agentic Intelligence",
            source="external",
            source_url="https://www.kimi.com/blog/kimi-k3-5",
            version="v1",
            is_latest_version=True,
        )
    )
    add_release_evidence(session, 2001)
    session.commit()
    renamed = HTML.replace(">K3 (Max reasoning)<", ">K3.5 (Max reasoning)<", 1).replace(
        ">Large 3<", ">Large 4<", 1
    )
    stats = _sync(session, parse_surge_chartography(renamed))

    assert (stats.auto_matched, stats.unreviewed) == (
        ["Kimi K3.5"],
        ["Mistral Large 4"],
    )
    kimi = _rows(session)["Kimi K3.5 (with tools)"]
    assert (kimi.paper_id, kimi.metrics) == (2001, {METRIC_NAME: 66.4})
    signal = session.query(ModelReleaseSignal).one()
    assert (signal.lab, signal.model_name) == ("Mistral", "Mistral Large 4")
    assert signal.lead_url == SURGE_CHARTOGRAPHY_URL

    again = _sync(session, parse_surge_chartography(renamed))
    assert (again.created, again.changed) == (0, 0)
    assert session.query(ModelReleaseSignal).one().sightings == 2


def test_managed_rows_dropped_upstream_are_reported_not_deleted():
    session = _session()
    _seed_production(session)
    entries = parse_surge_chartography(HTML)
    _sync(session, entries)
    remaining = [entry for entry in entries if entry.label != "Mistral Large 3"]
    stats = _sync(session, remaining)
    assert stats.missing_upstream == ["Mistral Large 3 (with tools)"]
    assert "Mistral Large 3 (with tools)" in _rows(session)


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    _seed_production(session)
    entries = parse_surge_chartography(HTML)
    _sync(session, entries, commit=False)
    assert _rows(session)["Claude Opus 5 (with tools)"].methodology == (
        "Hand-reviewed notes for Claude Opus 5 (with tools)."
    )
    assert "GPT-6.2 Astra (with tools)" not in _rows(session)
    with pytest.raises(RuntimeError, match="refusing"):
        _sync(session, entries[:10])


def test_unconfigured_leaderboard_is_refused():
    session = _session()
    session.query(TaskDatasetMetric).filter(
        TaskDatasetMetric.dataset_id == WITH_TOOLS_DATASET_ID
    ).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked"):
        _sync(session, parse_surge_chartography(HTML))
