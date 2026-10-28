"""Parsing, adoption, and rename tests for the Vals AI Finance Agent v2 sync."""

from dataclasses import replace
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
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import vals_finance_agent_sync_service as service
from backend.services.vals_finance_agent_sync_service import (
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAME,
    MODEL_IDENTITIES,
    VALS_FINANCE_AGENT_URL,
    ValsFinanceAgentSyncService,
    fetch_vals_finance_agent,
    parse_vals_finance_agent,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# The leaderboard table from https://www.vals.ai/benchmarks/fabv2, 2026-10-16.
HTML = (Path(__file__).parent / "fixtures" / "vals_finance_agent_v2.html").read_text()

# The 69 rows hand-imported on 2026-10-14: model_name -> stored accuracy.
# "Muse Spark 1.3" at 59.96 is Vals' "Muse Spark 1.3 Max" (mislabelled).
PRODUCTION_ROWS = {
    "Gemini 4 Argon": 65.4,
    "Gemini 3.8 Flash": 61.44,
    "Muse Spark 1.2": 60.6,
    "Muse Spark 1.3": 59.96,
    "Muse Wonder Full (max)": 59.1,
    "Gemini 3.7 Flash": 59.04,
    "Claude Fable 5.1": 58.88,
    "Claude Opus 5": 58.63,
    "Claude Opus 5.5": 58.59,
    "Claude Sonnet 5.5": 58.1,
    "Gemini 3.5 Flash": 57.86,
    "GLM-5.3-Flash": 57.85,
    "MiMo-V2.6-Pro": 57.34,
    "Muse Spark 1.1": 57.21,
    "Muse Wonder (max)": 56.6,
    "Claude Fable 5": 56.31,
    "Gemini 3.6 Flash": 56.3,
    "MiMo-V2.6-Flash": 56.28,
    "GLM-5.3": 55.84,
    "Hy4 preview": 55.06,
    "GPT-5.6 Luna": 55.04,
    "Mistral Large 4 Preview": 54.68,
    "GPT-5.6 Terra": 54.44,
    "Claude Haiku 5.5": 54.14,
    "Claude Opus 4.8": 53.92,
    "Claude Sonnet 5": 53.91,
    "GPT-5.6 Sol": 53.76,
    "Grok 4.6": 53.68,
    "GPT-6 Astra": 53.54,
    "DeepSeek-V4.1-Flash": 53.48,
    "Kimi K3": 53.11,
    "Grok 4.7": 52.25,
    "GPT-6.1 Sol": 52.03,
    "GPT-5.5": 51.76,
    "Claude Opus 4.7": 51.51,
    "Claude Sonnet 4.6": 51.03,
    "Qwen3.8-Max": 50.59,
    "DeepSeek-V4-Pro-0813": 50.39,
    "GPT-6 Luna": 49.87,
    "GLM-5.2": 49.7,
    "DeepSeek-V4-Flash-0731": 49.52,
    "GPT-6 Sol": 49.05,
    "Qwen3.8-27B": 48.55,
    "Grok 4.5": 48.35,
    "MiniMax M3": 48.27,
    "Qwen3.7-Max": 47.78,
    "Gemini 3.5 Flash-Lite": 47.44,
    "Inkling": 46.6,
    "GPT-5.4 mini": 45.36,
    "Kimi K2.6": 44.9,
    "GLM-5.1": 44.79,
    "DeepSeek-V4-Pro": 44.08,
    "Gemini 3.1 Pro": 42.98,
    "Gemini 3 Flash": 42.55,
    "MiMo-V2.5-Pro": 41.5,
    "Inkling-Small": 41.26,
    "Qwen3.7-Plus": 38.22,
    "GPT-5.4 nano": 38.22,
    "Grok 4.3": 37.73,
    "Nemotron 3 Ultra": 37.67,
    "Kimi K2.5": 35.79,
    "Mistral Medium 3.5": 32.1,
    "Claude Haiku 4.5": 31.01,
    "Gemini 3.1 Flash-Lite": 29.99,
    "MiniMax-M2.7": 27.89,
    "Laguna M.1": 25.03,
    "NVIDIA Nemotron 3.5 Lightning 30B-A3B": 18.5,
    "Laguna XS.2": 15.6,
    "Command A+": 9.04,
}
TASK_ID = 14
DATASET_ID = 2800


def _paper_keys() -> list[str]:
    return sorted({identity.paper_key for identity in MODEL_IDENTITIES.values()})


def _paper_id(key: str) -> int:
    return 1000 + _paper_keys().index(key)


def _identity(model_name: str):
    return next(
        identity
        for identity in MODEL_IDENTITIES.values()
        if model_name in (identity.model_name, identity.renamed_from)
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
    session.add(Task(id=TASK_ID, name="Agents", slug="agents"))
    session.add(
        Dataset(id=DATASET_ID, name="Finance Agent v2", slug="finance-agent-v2")
    )
    session.add(Metric(id=7, name=METRIC_NAME, direction="higher_is_better"))
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    session.add(TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=7))
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
    for model_name, accuracy in PRODUCTION_ROWS.items():
        identity = _identity(model_name)
        session.add(
            Evaluation(
                paper_id=_paper_id(identity.paper_key),
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=model_name,
                metrics={METRIC_NAME: accuracy},
                methodology=f"Hand-reviewed notes for {model_name}.",
                best_metric=METRIC_NAME,
                is_open=identity.is_open,
                external=True,
            )
        )
    session.commit()


def _rows(session: Session) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
    }


def test_parse_and_fetch_the_leaderboard_table():
    entries = parse_vals_finance_agent(HTML)
    assert len(entries) == 78
    first = entries[0]
    assert (first.position, first.label, str(first.accuracy)) == (
        1,
        "Gemini 4 Argon",
        "65.40",
    )
    assert first.model_url.startswith("https://www.vals.ai/models/")

    def handler(request):
        assert str(request.url) == VALS_FINANCE_AGENT_URL
        return httpx.Response(200, text=HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_vals_finance_agent(client) == entries


def test_parser_ignores_relabelled_trailing_columns():
    relabelled = HTML.replace("Input / Output Cost", "Tokens / Test", 1).replace(
        ">Duration<", ">Duration / Test<", 1
    )
    assert parse_vals_finance_agent(relabelled) == parse_vals_finance_agent(HTML)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("<th", "<td", "header changed"),
        ("65.40%", "65.40", "not a percentage"),
        ("65.40%", "165.40%", "outside 0-100"),
        ("</table>", "</table><table></table>", "2 tables"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    broken = (
        HTML.replace(old, new, 1)
        if old != "<th"
        else HTML.replace(">Accuracy<", ">Score<", 1)
    )
    with pytest.raises(ValueError, match=message):
        parse_vals_finance_agent(broken)


def test_parser_enforces_row_bounds_and_uniqueness(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 100)
    with pytest.raises(ValueError, match="78 rows"):
        parse_vals_finance_agent(HTML)
    monkeypatch.setattr(service, "MIN_EXPECTED_ROWS", 40)
    duplicated = HTML.replace("Gemini 3.8 Flash", "Gemini 4 Argon")
    with pytest.raises(ValueError, match="twice"):
        parse_vals_finance_agent(duplicated)


def test_first_run_adopts_renames_creates_and_reports():
    session = _session()
    _seed_production(session)
    stats = ValsFinanceAgentSyncService(session).sync(parse_vals_finance_agent(HTML))

    assert stats.fetched == 78
    assert stats.matched == 78
    assert stats.adopted == 69
    assert stats.created == 9  # Muse Spark 1.3 and the eight newly indexed models
    assert stats.renamed == ["Muse Spark 1.3 -> Muse Spark 1.3 Max"]
    assert stats.unreviewed == []
    assert stats.missing_papers == [] and stats.missing_upstream == []
    rows = _rows(session)
    assert rows["Muse Spark 1.3 Max"].metrics == {METRIC_NAME: 59.96}
    assert rows["Muse Spark 1.3"].metrics == {METRIC_NAME: 58.9}
    assert rows["Muse Wonder Full (max)"].metrics == {METRIC_NAME: 59.06}
    assert rows["Gemini 4 Argon"].best_rank == 1
    assert rows["MiMo-V2.5"].is_open and rows["MiMo-V2.5"].metrics == {
        METRIC_NAME: 36.73
    }
    adopted = rows["Gemini 4 Argon"].methodology
    assert adopted.startswith(MANAGED_METHODOLOGY_PREFIX)
    assert adopted.endswith("Hand-reviewed notes for Gemini 4 Argon.")

    again = ValsFinanceAgentSyncService(session).sync(parse_vals_finance_agent(HTML))
    assert (again.adopted, again.created, again.changed, again.renamed) == (
        0,
        0,
        0,
        [],
    )


def test_dated_deepseek_checkpoint_attaches_to_its_release_paper():
    session = _session()
    entries = parse_vals_finance_agent(HTML)
    flash = next(entry for entry in entries if entry.label == "DeepSeek V4.1 Flash")
    checkpoint = replace(
        flash,
        position=len(entries) + 1,
        label="DeepSeek V4.1 Flash 1017",
        accuracy=Decimal("54.10"),
    )
    stats = ValsFinanceAgentSyncService(session).sync([*entries, checkpoint])

    assert stats.unreviewed == []
    rows = _rows(session)
    row = rows["DeepSeek-V4.1-Flash-1017"]
    assert row.paper_id == rows["DeepSeek-V4.1-Flash"].paper_id
    assert row.paper_id == _paper_id("2609.19969")
    assert row.is_open
    assert row.metrics == {METRIC_NAME: 54.1}


def test_rename_requires_a_matching_score():
    session = _session()
    _seed_production(session)
    row = _rows(session)["Muse Spark 1.3"]
    row.metrics = {METRIC_NAME: 50.0}
    session.commit()
    stats = ValsFinanceAgentSyncService(session).sync(parse_vals_finance_agent(HTML))
    assert stats.renamed == []
    rows = _rows(session)
    # The unmatched row is adopted as plain "Muse Spark 1.3" and corrected to
    # Vals' 58.90; "Muse Spark 1.3 Max" is created separately.
    assert rows["Muse Spark 1.3"].metrics == {METRIC_NAME: 58.9}
    assert rows["Muse Spark 1.3 Max"].metrics == {METRIC_NAME: 59.96}


def test_managed_rows_dropped_upstream_are_reported_not_deleted():
    session = _session()
    _seed_production(session)
    entries = parse_vals_finance_agent(HTML)
    ValsFinanceAgentSyncService(session).sync(entries)
    remaining = [entry for entry in entries if entry.label != "Command A+"]
    stats = ValsFinanceAgentSyncService(session).sync(remaining)
    assert stats.missing_upstream == ["Command A+"]
    assert "Command A+" in _rows(session)


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    _seed_production(session)
    entries = parse_vals_finance_agent(HTML)
    ValsFinanceAgentSyncService(session).sync(entries, commit=False)
    assert "Muse Spark 1.3 Max" not in _rows(session)
    with pytest.raises(RuntimeError, match="refusing"):
        ValsFinanceAgentSyncService(session).sync(entries[:10])


def test_unconfigured_leaderboard_is_refused():
    session = _session()
    session.query(TaskDatasetMetric).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked"):
        ValsFinanceAgentSyncService(session).sync(parse_vals_finance_agent(HTML))
