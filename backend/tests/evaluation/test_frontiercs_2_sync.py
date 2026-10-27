"""Parsing and sync tests for the FrontierCS 2 leaderboard."""

import re
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
from backend.services import frontiercs_2_sync_service as service
from backend.services import leaderboard_model_matching_service as matching
from backend.services.leaderboard_model_matching_service import (
    title_announces_model,
)
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
# https://frontier-cs.org/assets/js/fcs2-data.js on 2026-10-27.
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
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            ModelReleaseSignal.__table__,
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
    assert leaderboard.updated == date(2026, 10, 27)
    assert len(leaderboard.entries) == 16
    by_label = {entry.label: entry for entry in leaderboard.entries}
    opus = by_label["Claude Opus 5.5 (Claude Code)"]
    assert (opus.pass_rate, opus.passes, opus.runs) == (58.3, 28, 48)
    assert (opus.fci, opus.fci_low, opus.fci_high) == (54, 45.3, 65.2)
    assert by_label["Gemini 4 Argon (Antigravity)"].upstream_id == "gemini-agy"
    assert by_label["Step 5 Preview (Step Code)"].fci_low == -4.3

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
        ("opus:[54,45.3,65.2,48]", "opus:[66,45.3,65.2,48]", "interval"),
        ('h:"Claude Code"', 'h:""', "malformed"),
        ("ECI={astra:", "ECI={astra:foo,x:", "not plain data"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    assert old in SOURCE
    with pytest.raises(ValueError, match=message):
        parse_frontiercs_2(SOURCE.replace(old, new, 1))


@pytest.mark.parametrize("published", ["6.2", "6.3"])
def test_pass_rate_accepts_either_rounding_of_a_half_tenth(published):
    # 1/16 = 6.25%: banker's rounding gives 6.2, half-up gives 6.3.
    source = SOURCE.replace("step:[8.3,4,48]", f"step:[{published},1,16]", 1)
    entries = {e.upstream_id: e for e in parse_frontiercs_2(source).entries}
    assert entries["step"].pass_rate == float(published)


def test_parser_enforces_entry_bounds_and_uniqueness(monkeypatch):
    duplicated = SOURCE.replace('h:"Antigravity"', 'h:"Pi"', 1)
    with pytest.raises(ValueError, match="twice"):
        parse_frontiercs_2(duplicated)
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 20)
    with pytest.raises(ValueError, match="16 entries"):
        parse_frontiercs_2(SOURCE)


def test_first_run_creates_every_entry_and_second_run_is_a_no_op():
    session = _session()
    leaderboard = parse_frontiercs_2(SOURCE)
    stats = FrontierCS2SyncService(session).sync(leaderboard)

    assert (stats.fetched, stats.matched, stats.created, stats.changed) == (
        16,
        16,
        16,
        0,
    )
    assert stats.unreviewed == stats.missing_papers == stats.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 16
    opus = rows["Claude Opus 5.5 (Claude Code)"]
    assert opus.best_rank == 1 and opus.best_metric == PASS_RATE
    assert opus.metrics == {PASS_RATE: 58.3, FCI: 54}
    assert opus.evaluated_on == date(2026, 10, 27)
    assert opus.external and opus.external_source_url == FRONTIERCS_2_URL
    assert opus.methodology.startswith(
        f'{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "Claude Opus 5.5" '
        "(Claude Code): 58.3% pass rate (28/48 runs beat the human reference), "
        "FCI 54.0 (90% interval 45.3 to 65.2)"
    )
    # One model, two harnesses: two rows on the same paper.
    assert rows["Gemini 4 Argon (Antigravity)"].best_rank == 2
    assert rows["Gemini 4 Argon (Pi)"].metrics == {PASS_RATE: 39.6, FCI: 39}
    assert rows["DeepSeek-V4.1-Flash-1017 (DeepSeek Harness)"].is_open
    assert rows["GPT-6.1 Terra (Codex CLI)"].metrics == {PASS_RATE: 39.6, FCI: 44.8}
    kimi = rows["Kimi K3.1 Pro (Kimi Code)"]
    assert kimi.metrics == {PASS_RATE: 25.0, FCI: 35.1} and kimi.is_open
    assert {row.paper_id for row in session.query(PaperTask).all()} == {
        _paper_id(key) for key in _paper_keys()
    }

    again = FrontierCS2SyncService(session).sync(parse_frontiercs_2(SOURCE))
    assert (again.matched, again.created, again.changed) == (16, 0, 0)
    assert len(_rows(session)) == 16


def test_score_updates_revise_the_row_and_unknown_models_are_reported():
    session = _session()
    FrontierCS2SyncService(session).sync(parse_frontiercs_2(SOURCE))
    updated = (
        SOURCE.replace("opus:[58.3,28,48]", "opus:[60.4,29,48]", 1)
        .replace("opus:[54,45.3,65.2,48]", "opus:[55.1,46,66,48]", 1)
        .replace('name:"Step 5 Preview"', 'name:"Step 6"', 1)
    )
    stats = FrontierCS2SyncService(session).sync(parse_frontiercs_2(updated))
    assert (stats.changed, stats.created) == (1, 0)
    assert stats.auto_matched == []
    assert stats.unreviewed == ["Step 6 (Step Code)"]
    assert stats.missing_upstream == ["Step-5-Preview (Step Code)"]
    # The unmatched model is handed to the release radar, once per name.
    signal = session.query(ModelReleaseSignal).one()
    assert (signal.signal_key, signal.lab, signal.model_name) == (
        "stepfun/step6",
        "StepFun",
        "Step 6",
    )
    assert signal.lead_url == signal.source == FRONTIERCS_2_URL
    assert (signal.status, signal.sightings, signal.lead_is_official) == (
        "discovered",
        1,
        False,
    )
    FrontierCS2SyncService(session).sync(parse_frontiercs_2(updated))
    assert session.query(ModelReleaseSignal).one().sightings == 2
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


def _new_model(source: str, upstream_id: str, name: str) -> str:
    """Rename one entry so it falls outside MODEL_IDENTITIES."""
    old = re.search(rf'{{id:"{upstream_id}",name:"[^"]+"', source).group(0)
    return source.replace(old, f'{{id:"{upstream_id}",name:"{name}"', 1)


def test_new_models_match_an_announcing_title_or_a_model_release():
    session = _session()
    session.add_all(
        [
            Paper(
                id=2001,
                title="Kimi K3.2: Open Agentic Intelligence",
                source="external",
                source_url="https://www.kimi.com/blog/kimi-k3-2",
                version="v1",
                is_latest_version=True,
            ),
            # Same family, other version: never a match for "Kimi K3.2".
            Paper(
                id=2002,
                title="Kimi K3.2 Pro: Advancing Open Intelligence",
                source="external",
                source_url="https://www.kimi.com/blog/kimi-k3-2-pro",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2003,
                title="Introducing GPT-6.2",
                source="external",
                source_url="https://openai.com/index/introducing-gpt-6-2",
                version="v1",
                is_latest_version=True,
            ),
            ModelRelease(
                id=1,
                paper_id=2003,
                # A resolution's canonical spelling differs; the leaderboard
                # spelling is an alias.
                canonical_name="gpt-6.2-terra-2026-10",
                publisher="OpenAI",
                aliases=["GPT 6.2 Terra"],
                is_open=False,
            ),
            Paper(
                id=2004,
                title="Muse Spark 2",
                source="external",
                source_url="https://research.meta.ai/blog/muse-spark-2",
                version="v1",
                is_latest_version=True,
            ),
            ModelRelease(
                id=2,
                paper_id=2004,
                canonical_name="Muse Spark 2",
                publisher="Meta",
                aliases=[],
                is_open=True,
            ),
            HfArtifact(
                id=1,
                kind="model",
                repo_id="moonshotai/Kimi-K3.2",
                url="https://huggingface.co/moonshotai/Kimi-K3.2",
            ),
            PaperHfArtifact(paper_id=2001, hf_artifact_id=1),
        ]
    )
    session.commit()
    source = _new_model(SOURCE, "k3", "Kimi K3.2")
    source = _new_model(source, "terra", "GPT-6.2 Terra")
    source = _new_model(source, "muse", "Muse Spark 2")
    stats = FrontierCS2SyncService(session).sync(parse_frontiercs_2(source))

    assert stats.auto_matched == [
        "GPT-6.2 Terra (Codex CLI)",
        "Muse Spark 2 (Muse Code)",
        "Kimi K3.2 (Kimi Code)",
    ]
    assert stats.unreviewed == stats.missing_papers == []
    assert session.query(ModelReleaseSignal).count() == 0
    rows = _rows(session)
    kimi = rows["Kimi K3.2 (Kimi Code)"]
    assert (kimi.paper_id, kimi.is_open) == (2001, True)
    assert kimi.hf_model_url == "https://huggingface.co/moonshotai/Kimi-K3.2"
    terra = rows["GPT-6.2 Terra (Codex CLI)"]
    assert (terra.paper_id, terra.is_open) == (2003, False)
    muse = rows["Muse Spark 2 (Muse Code)"]
    assert (muse.paper_id, muse.is_open) == (2004, True)
    assert muse.metrics == {PASS_RATE: 12.5, FCI: 22}
    assert 2001 in {row.paper_id for row in session.query(PaperTask).all()}
    # The release match is remembered as a provider alias.
    assert {alias.alias for alias in session.query(ModelProviderAlias).all()} == {
        "GPT-6.2 Terra",
        "Muse Spark 2",
    }


def test_ambiguous_titles_are_not_matched(monkeypatch):
    session = _session()
    for paper_id, url in ((2001, "https://a.example/x"), (2002, "https://b.example/x")):
        session.add(
            Paper(
                id=paper_id,
                title="Kimi K3.2: Open Agentic Intelligence",
                source="external",
                source_url=url,
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    stats = FrontierCS2SyncService(session).sync(
        parse_frontiercs_2(_new_model(SOURCE, "k3", "Kimi K3.2"))
    )
    assert stats.auto_matched == []
    assert stats.unreviewed == ["Kimi K3.2 (Kimi Code)"]
    assert session.query(ModelReleaseSignal).one().model_name == "Kimi K3.2"

    # A candidate window that fills up cannot rule out another announcement.
    session.get(Paper, 2002).is_latest_version = False
    session.add(
        Paper(
            id=2000,
            title="Kimi K3.2 Pro Technical Report",
            source="external",
            source_url="https://c.example/x",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    source = parse_frontiercs_2(_new_model(SOURCE, "k3", "Kimi K3.2"))
    assert FrontierCS2SyncService(session).sync(source).auto_matched == [
        "Kimi K3.2 (Kimi Code)"
    ]
    session.query(Evaluation).delete()
    session.commit()
    monkeypatch.setattr(matching, "TITLE_CANDIDATE_LIMIT", 1)
    assert FrontierCS2SyncService(session).sync(source).auto_matched == []


@pytest.mark.parametrize(
    ("title", "name", "announces"),
    [
        ("Kimi K3.1 Pro: Advancing Open Intelligence", "Kimi K3.1 Pro", True),
        ("Introducing GPT-6.1 Terra", "GPT-6.1 Terra", True),
        ("GLM-5.3: From Vibe Coding to Agentic Engineering", "GLM 5.3", True),
        ("Kimi K3.1 Pro: Advancing Open Intelligence", "Kimi K3", False),
        ("Kimi K3.1 Pro: Advancing Open Intelligence", "Kimi K3.1", False),
        ("Evaluating GPT-6.1 Terra on Long Tasks", "GPT-6.1 Terra", False),
        ("GPT-6.1 Terra Is Not Robust", "GPT-6.1 Terra", False),
    ],
)
def test_title_announces_model(title, name, announces):
    assert title_announces_model(title, name) is announces
