"""Parsing and adoption tests for the Surge AI Chartography sync."""

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
from backend.services import surge_chartography_sync_service as service
from backend.services.surge_chartography_sync_service import (
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAME,
    MODEL_IDENTITIES,
    SURGE_CHARTOGRAPHY_URL,
    SurgeChartographySyncService,
    fetch_surge_chartography,
    parse_surge_chartography,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# The "Chartography Leaderboard" block of https://surgehq.ai/benchmarks/chartography,
# 2026-10-17 (element ids and image URLs stripped).
HTML = (Path(__file__).parent / "fixtures" / "surge_chartography.html").read_text()

# The 41 rows hand-imported on 2026-10-17: model_name -> stored Pass@1.
PRODUCTION_ROWS = {
    "Gemini 4 Argon (no tools)": 0.716,
    "GPT-6 Astra (no tools)": 0.71,
    "Claude Opus 5.5 (no tools)": 0.663,
    "GPT-6 Sol (no tools)": 0.536,
    "Claude Fable 5.1 (no tools)": 0.462,
    "GPT-5.6 Sol (no tools)": 0.45,
    "Gemini 3.8 Flash (no tools)": 0.409,
    "Gemini 3.7 Flash (no tools)": 0.404,
    "Claude Fable 5 (no tools)": 0.348,
    "GPT-5.6 Terra (no tools)": 0.34,
    "Gemini 3.6 Flash (no tools)": 0.34,
    "Muse Spark 1.2 (no tools)": 0.321,
    "GPT-5.6 Luna (no tools)": 0.314,
    "GPT-5.5 (no tools)": 0.31,
    "GPT-5.4 (no tools)": 0.296,
    "GPT-6 Luna (no tools)": 0.291,
    "Qwen3.8-Max (no tools)": 0.291,
    "Muse Spark 1.3 (no tools)": 0.276,
    "Claude Opus 5 (no tools)": 0.273,
    "Kimi K3 (no tools)": 0.266,
    "Gemini 3.1 Pro (no tools)": 0.261,
    "Muse Spark 1.1 (no tools)": 0.244,
    "Grok 4.6 (no tools)": 0.205,
    "Qwen3.8-Flash (no tools)": 0.174,
    "Muse Glimmer-30B (no tools)": 0.172,
    "Grok 4.5 (no tools)": 0.17,
    "Claude Sonnet 5 (no tools)": 0.166,
    "Claude Opus 4.7 (no tools)": 0.165,
    "GLM-5.3-Flash (no tools)": 0.163,
    "Qwen3.5-Plus (no tools)": 0.159,
    "Claude Opus 4.8 (no tools)": 0.159,
    "Qwen3.7-Plus (no tools)": 0.158,
    "Grok 4.7 (no tools)": 0.147,
    "Grok 4.3 (no tools)": 0.129,
    "Kimi K2.5 (no tools)": 0.126,
    "Kimi K2.6 (no tools)": 0.122,
    "DeepSeek-V4.1-Flash (no tools)": 0.116,
    "Gemini 3.5 Flash-Lite (no tools)": 0.102,
    "Inkling (no tools)": 0.1,
    "Inkling-Small (no tools)": 0.091,
    "Mistral Large 3 (no tools)": 0.09,
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
        if identity.row_model_name == model_name
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
    for model_name, score in PRODUCTION_ROWS.items():
        identity = _identity(model_name)
        session.add(
            Evaluation(
                paper_id=_paper_id(identity.paper_key),
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=model_name,
                metrics={METRIC_NAME: score},
                methodology=f"Hand-reviewed notes for {model_name}.",
                best_metric=METRIC_NAME,
                is_open=identity.is_open,
                num_parameters=123 if model_name.startswith("Kimi K2.6") else None,
                external=True,
            )
        )
    # A with-tools row on the same paper the sync must never touch.
    session.add(
        Evaluation(
            paper_id=_paper_id(MODEL_IDENTITIES["Claude Opus 5.5"].paper_key),
            task_id=TASK_ID,
            dataset_id=WITH_TOOLS_DATASET_ID,
            model_name="Claude Opus 5.5",
            metrics={METRIC_NAME: 0.5},
            methodology="Anthropic system card.",
            external=True,
        )
    )
    session.commit()


def _rows(session: Session, dataset_id: int = DATASET_ID) -> dict[str, Evaluation]:
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
    assert (first.position, first.label, first.configuration, str(first.score)) == (
        1,
        "Gemini 4 Argon",
        "High reasoning",
        "71.6",
    )
    by_label = {entry.label: entry for entry in entries}
    assert by_label["Inkling"].configuration == "High reasoning"
    assert by_label["Inkling Small"].configuration == "xHigh reasoning"
    assert by_label["Mistral Large 3"].configuration == "default"
    assert by_label["DeepSeek V4 Flash Vision (experimental)"].configuration == (
        "Max reasoning"
    )
    assert str(by_label["GPT 6 Astra"].score) == "71"

    def handler(request):
        assert str(request.url) == SURGE_CHARTOGRAPHY_URL
        assert "Mozilla/5.0" in request.headers["user-agent"]
        return httpx.Response(200, text=HTML)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": service.USER_AGENT},
    )
    assert fetch_surge_chartography(client) == entries


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("Chartography Leaderboard", "Leaderboard", "0 'Chartography Leaderboard'"),
        ('data-score="71.6"', 'data-score="72"', "not a percentage"),
        ('data-score="71.6"', 'data-score="abc"', "invalid"),
        ("head-rank-table-brand", "brand", "row 1 layout changed"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    with pytest.raises(ValueError, match=message):
        parse_surge_chartography(HTML.replace(old, new, 1))


def test_parser_enforces_row_bounds_range_and_uniqueness(monkeypatch):
    out_of_range = HTML.replace('data-score="71.6"', 'data-score="171.6"', 1).replace(
        ">71.6<", ">171.6<", 1
    )
    with pytest.raises(ValueError, match="outside 0-100"):
        parse_surge_chartography(out_of_range)
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 100)
    with pytest.raises(ValueError, match="42 rows"):
        parse_surge_chartography(HTML)
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 25)
    duplicated = HTML.replace("3.8 Flash (High reasoning)", "4 Argon (High reasoning)")
    with pytest.raises(ValueError, match="twice"):
        parse_surge_chartography(duplicated)


def test_first_run_adopts_every_hand_imported_row():
    session = _session()
    _seed_production(session)
    stats = SurgeChartographySyncService(session).sync(parse_surge_chartography(HTML))

    assert stats.fetched == 42
    assert (stats.matched, stats.adopted, stats.created, stats.changed) == (
        41,
        41,
        0,
        0,
    )
    assert stats.excluded == ["DeepSeek V4 Flash Vision (experimental)"]
    assert stats.unreviewed == []
    assert stats.missing_papers == [] and stats.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 41
    argon = rows["Gemini 4 Argon (no tools)"]
    assert argon.best_rank == 1 and argon.metrics == {METRIC_NAME: 0.716}
    assert argon.methodology.startswith(
        f'{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "Gemini 4 Argon" '
        "(High reasoning): 71.6% Pass@1"
    )
    assert argon.methodology.endswith(
        "Hand-reviewed notes for Gemini 4 Argon (no tools)."
    )
    assert rows["Kimi K2.6 (no tools)"].num_parameters == 123
    assert rows["Qwen3.8-Max (no tools)"].is_open

    again = SurgeChartographySyncService(session).sync(parse_surge_chartography(HTML))
    assert (again.adopted, again.created, again.changed) == (0, 0, 0)
    assert _rows(session, WITH_TOOLS_DATASET_ID)["Claude Opus 5.5"].metrics == {
        METRIC_NAME: 0.5
    }
    assert _rows(session)["Gemini 4 Argon (no tools)"].methodology == argon.methodology


def test_score_and_configuration_updates_revise_the_row():
    session = _session()
    _seed_production(session)
    SurgeChartographySyncService(session).sync(parse_surge_chartography(HTML))
    updated = (
        HTML.replace("4 Argon (High reasoning)", "4 Argon (Max reasoning)", 1)
        .replace('data-score="71.6"', 'data-score="73.25"', 1)
        .replace(">71.6<", ">73.25<", 1)
    )
    stats = SurgeChartographySyncService(session).sync(
        parse_surge_chartography(updated)
    )
    assert (stats.changed, stats.created, stats.adopted) == (1, 0, 0)
    argon = _rows(session)["Gemini 4 Argon (no tools)"]
    assert argon.metrics == {METRIC_NAME: 0.7325}
    assert '"Gemini 4 Argon" (Max reasoning): 73.25% Pass@1' in argon.methodology
    assert argon.methodology.endswith(
        "Hand-reviewed notes for Gemini 4 Argon (no tools)."
    )


def test_new_mapped_rows_are_created_and_new_labels_reported():
    session = _session()
    _seed_production(session)
    session.query(Evaluation).filter(
        Evaluation.model_name == "Mistral Large 3 (no tools)"
    ).delete()
    session.commit()
    renamed = HTML.replace(">Inkling<", ">Nova<", 1).replace(
        ">Inkling (High reasoning)<", ">Nova 2 (High reasoning)<", 1
    )
    stats = SurgeChartographySyncService(session).sync(
        parse_surge_chartography(renamed)
    )
    assert stats.created == 1
    assert stats.unreviewed == ["Nova 2"]
    assert stats.missing_upstream == []
    created = _rows(session)["Mistral Large 3 (no tools)"]
    assert created.metrics == {METRIC_NAME: 0.09}
    assert created.is_open and created.external_source_url == SURGE_CHARTOGRAPHY_URL


def test_managed_rows_dropped_upstream_are_reported_not_deleted():
    session = _session()
    _seed_production(session)
    entries = parse_surge_chartography(HTML)
    SurgeChartographySyncService(session).sync(entries)
    remaining = [entry for entry in entries if entry.label != "Mistral Large 3"]
    stats = SurgeChartographySyncService(session).sync(remaining)
    assert stats.missing_upstream == ["Mistral Large 3 (no tools)"]
    assert "Mistral Large 3 (no tools)" in _rows(session)


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    _seed_production(session)
    entries = parse_surge_chartography(HTML)
    SurgeChartographySyncService(session).sync(entries, commit=False)
    assert _rows(session)["GPT-5.5 (no tools)"].methodology == (
        "Hand-reviewed notes for GPT-5.5 (no tools)."
    )
    with pytest.raises(RuntimeError, match="refusing"):
        SurgeChartographySyncService(session).sync(entries[:10])


def test_unconfigured_leaderboard_is_refused():
    session = _session()
    session.query(TaskDatasetMetric).filter(
        TaskDatasetMetric.dataset_id == DATASET_ID
    ).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked"):
        SurgeChartographySyncService(session).sync(parse_surge_chartography(HTML))
