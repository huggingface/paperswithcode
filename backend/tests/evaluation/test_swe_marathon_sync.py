"""Parsing and sync tests for the Abundant AI SWE-Marathon board."""

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
from backend.services import swe_marathon_sync_service as service
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from backend.services.swe_marathon_sync_service import (
    BOARD,
    METRIC_NAME,
    MODEL_IDENTITIES,
    SWE_MARATHON_URL,
    bundle_url,
    fetch_swe_marathon,
    parse_swe_marathon_bundle,
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


# Per-task pass and trial counts of every v1.1 config in the site bundle on
# 2026-11-10; ``_bundle`` renders them back into the bundle's layout.
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "swe_marathon_v1_1.json").read_text()
)
BUNDLE_PATH = "/assets/index-IcpvZb3e.js"
HOME = (
    '<!doctype html><html><head><script type="module" crossorigin '
    f'src="{BUNDLE_PATH}"></script></head><body><div id="root"></div></body></html>'
)

# The board's Abundant AI rows as imported by hand on 2026-10-14 and 2026-11-10,
# renamed to catalog model names: model_name -> (harness, stored value).
PRODUCTION_ROWS = {
    "Gemini 4 Carbon": ("Antigravity CLI", 53.75),
    "Muse Wonder Full": ("Muse Code", 53.12),
    "Muse Wonder": ("Muse Code", 52.5),
    "Claude Sonnet 5.5": ("Claude Code", 51.25),
    "Claude Opus 5": ("Claude Code", 50.0),
    "Claude Haiku 5.5": ("Claude Code", 50.0),
    "Claude Opus 4.8": ("Claude Code", 48.75),
    "Kimi K3": ("Claude Code", 48.13),
    "Claude Opus 5.5": ("Claude Code", 46.25),
    "Claude Fable 5.1": ("Claude Code", 45.62),
    "Grok 4.7": ("Grok Build", 45.62),
    "Gemini 4 Argon": ("Gemini CLI", 43.75),
    "GPT-6 Sol": ("Codex", 43.12),
    "GLM-5.3": ("Claude Code", 42.5),
    "GPT-6 Astra": ("Codex", 42.5),
    "GPT-6.1 Sol": ("Codex", 42.5),
    "GPT-5.6 Sol": ("Codex", 42.5),
    "GLM-5.3-Flash": ("Claude Code", 38.75),
    "GPT-5.6 Terra": ("Codex", 32.5),
    "Grok 4.6": ("Grok Build", 31.88),
    # Stale: Abundant AI's data now has a complete max run at 46.25.
    "Muse Spark 1.3": ("Muse Code", 30.62),
    "Claude Sonnet 5": ("Claude Code", 30.0),
    "Grok 4.5": ("Grok Build", 29.38),
    "GPT-6 Luna": ("Codex", 28.12),
    "GPT-5.6 Luna": ("Codex", 24.38),
    "Gemini 3.7 Flash": ("OpenCode", 22.5),
    "GLM-5.2": ("Claude Code", 19.38),
    "DeepSeek V4 Pro": ("Mini-SWE-Agent", 10.63),
}
TASK_ID = 895
DATASET_ID = 2797
KIMI_K3_1_PRO = 5000


def _bundle(fixture: dict | None = None, version: str = "v1.1") -> str:
    fixture = fixture or FIXTURE
    tasks = {}
    for index, name in enumerate(fixture["tasks"]):
        configs = []
        for config in fixture["configs"]:
            passes, trials = config["passes"][index], config["trials"][index]
            if trials is None:
                continue
            rendered = {
                key: config[key]
                for key in ("agent", "model", "reasoningEffort", "canonicalModel")
                if key in config
            }
            rendered.update(
                n=trials,
                binary=f"{passes} / {trials}",
                trials=[
                    {
                        "id": f"{name}-{trial}",
                        "reward": 1.0 if trial < passes else 0.0,
                        "startedAt": config["startedAt"],
                    }
                    for trial in range(trials)
                ],
            )
            configs.append(rendered)
        tasks[name] = {
            "task": name,
            "note": 'Tasks are "binary" `reward`; partial ${scores} are shown.',
            "configs": configs,
        }
    literal = json.dumps(tasks).replace("\\", "\\\\").replace("`", "\\`")
    literal = literal.replace("${", "\\${")
    return (
        "const Ve=[{id:`zstd-decoder`,title:`Zstandard Decoder`}],"
        f"Qe={{version:`{version}`,tasks:JSON.parse(`{literal}`)}},"
        "$e=e=>e.reasoningEffort?e.reasoningEffort:`max`;"
    )


BUNDLE = _bundle()


def _with_config(**config) -> dict:
    fixture = copy.deepcopy(FIXTURE)
    fixture["configs"].append(config)
    return fixture


def _paper_keys() -> list[str]:
    return sorted({identity.paper_key for identity in MODEL_IDENTITIES.values()})


def _paper_id(key: str) -> int:
    return 1000 + _paper_keys().index(key)


def _identity(model_name: str):
    return next(
        identity
        for identity in MODEL_IDENTITIES.values()
        if identity.model_name == model_name
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
        Task(id=TASK_ID, name="Long-Horizon Agents", slug="long-horizon-agents")
    )
    session.add(Dataset(id=DATASET_ID, name="SWE-Marathon", slug="swe-marathon"))
    session.add(Metric(id=713, name=METRIC_NAME, direction="higher_is_better"))
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    session.add(
        TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=713)
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
    session.add(
        Paper(
            id=KIMI_K3_1_PRO,
            title="Kimi K3.1 Pro: Advancing Open Intelligence",
            source="external",
            source_url="https://www.kimi.com/blog/kimi-k3-1-pro",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    return session


def _seed_production(session: Session) -> None:
    for model_name, (harness, score) in PRODUCTION_ROWS.items():
        identity = _identity(model_name)
        session.add(
            Evaluation(
                paper_id=_paper_id(identity.paper_key),
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=model_name,
                harness=harness,
                metrics={METRIC_NAME: score},
                methodology=f"Hand-reviewed notes for {model_name}.",
                best_metric=METRIC_NAME,
                is_open=identity.is_open,
                external_source_url=SWE_MARATHON_URL,
                external=True,
            )
        )
    # Kimi's own launch figure, run with Claude Code; never Abundant AI's row.
    session.add(
        Evaluation(
            paper_id=KIMI_K3_1_PRO,
            task_id=TASK_ID,
            dataset_id=DATASET_ID,
            model_name="Kimi K3.1 Pro (max)",
            harness="Claude Code",
            metrics={METRIC_NAME: 51.7},
            methodology="Kimi K3.1 Pro launch blog.",
            best_metric=METRIC_NAME,
            is_open=True,
            external=False,
        )
    )
    session.commit()


def _sync(session: Session, entries, **kwargs):
    return LiveLeaderboardSyncService(session, BOARD).sync(entries, **kwargs)


def _rows(session: Session) -> dict[str, Evaluation]:
    return {
        row.model_name: row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
    }


def test_parse_complete_runs_at_each_models_best_effort():
    entries = parse_swe_marathon_bundle(BUNDLE)
    by_label = {entry.label: entry for entry in entries}
    assert len(entries) == 29
    first = entries[0]
    assert (first.label, first.value, first.detail, first.lab) == (
        "Gemini 4 Carbon (Antigravity CLI)",
        Decimal("53.75"),
        "53.75% pass@1 (86/160 trials over 20 tasks) at high reasoning effort",
        "Google DeepMind",
    )
    assert first.evaluated_on == date(2026, 11, 7)
    # A config without a reasoning effort is the site's default, max.
    assert by_label["Claude Opus 5 (Claude Code)"].detail.endswith(
        "at max reasoning effort"
    )
    assert by_label["Claude Opus 5 (Claude Code)"].value == Decimal("50.00")
    # Max (74/160) beats the xhigh run (73/160) of the same model and agent.
    assert by_label["Claude Opus 5.5 (Claude Code)"].value == Decimal("46.25")
    assert by_label["Muse Spark 1.3 (Muse Code)"].value == Decimal("46.25")
    assert by_label["Muse Wonder Full (Muse Code)"].lab == "Meta"
    # Half-hundredths round up, as the site's one-decimal display does.
    assert by_label["Kimi K3 (Claude Code)"].value == Decimal("48.13")
    # GPT-6 Astra's medium run (66/153, 43.14%) misses trials; max stands.
    assert by_label["GPT-6 Astra (Codex)"].value == Decimal("42.50")
    assert "DeepSeek V4 Pro (Mini-SWE-Agent)" in by_label
    assert {entry.name for entry in entries} <= set(MODEL_IDENTITIES)


def test_fetch_reads_the_bundle_the_home_page_loads():
    def handler(request):
        if str(request.url) == SWE_MARATHON_URL:
            return httpx.Response(200, text=HOME)
        assert str(request.url) == f"https://www.swe-marathon.org{BUNDLE_PATH}"
        return httpx.Response(200, text=BUNDLE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_swe_marathon(client) == parse_swe_marathon_bundle(BUNDLE)
    assert BOARD_SYNCS["sync_swe_marathon"].board is BOARD


def test_home_page_must_load_exactly_one_bundle():
    with pytest.raises(ValueError, match="0 index bundles"):
        bundle_url("<html></html>")
    with pytest.raises(ValueError, match="2 index bundles"):
        bundle_url(HOME + HOME.replace("IcpvZb3e", "Other123"))


@pytest.mark.parametrize(
    ("bundle", "message"),
    [
        (BUNDLE.replace("version:`v1.1`", "version:`v1.2`"), "versions \\['v1.2'\\]"),
        (BUNDLE + _bundle(version="v1.2"), "versions \\['v1.1', 'v1.2'\\]"),
        (BUNDLE.replace("tasks:JSON.parse", "tasks:JSON.load"), "versions \\[\\]"),
        (BUNDLE.replace('"reward": 1.0', '"reward": 0.5', 1), "not binary"),
        (BUNDLE.replace('"binary": "8 / 8"', '"binary": "7 / 8"', 1), "disagrees"),
        (BUNDLE.replace("\\${scores}", "${scores}", 1), "not plain data"),
        (BUNDLE.split("`)},$e=")[0], "unterminated"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(bundle, message):
    with pytest.raises(ValueError, match=message):
        parse_swe_marathon_bundle(bundle)


def test_parser_enforces_run_bounds(monkeypatch):
    monkeypatch.setattr(service, "MIN_EXPECTED_ENTRIES", 30)
    with pytest.raises(ValueError, match="29 complete runs"):
        parse_swe_marathon_bundle(BUNDLE)


def test_first_run_adopts_hand_imported_rows_and_leaves_vendor_rows():
    session = _session()
    _seed_production(session)
    stats = _sync(session, parse_swe_marathon_bundle(BUNDLE))

    assert stats.fetched == 29
    # Claude Fable 5 had no row; every other Abundant AI row is adopted.
    assert (stats.matched, stats.adopted, stats.created) == (29, 28, 1)
    assert stats.unreviewed == [] and stats.auto_matched == []
    assert stats.missing_papers == [] and stats.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 30
    carbon = rows["Gemini 4 Carbon"]
    assert carbon.best_rank == 1 and carbon.metrics == {METRIC_NAME: 53.75}
    assert carbon.methodology.startswith(
        f'{BOARD.managed_prefix} Official leaderboard entry "Gemini 4 Carbon '
        '(Antigravity CLI)": 53.75% pass@1 (86/160 trials over 20 tasks) at high '
        "reasoning effort, listed at https://www.swe-marathon.org/."
    )
    assert carbon.methodology.endswith("Hand-reviewed notes for Gemini 4 Carbon.")
    assert rows["Muse Spark 1.3"].metrics == {METRIC_NAME: 46.25}
    assert rows["Muse Wonder Full"].metrics == {METRIC_NAME: 53.13}
    assert rows["Claude Fable 5"].metrics == {METRIC_NAME: 45.0}
    assert rows["Claude Fable 5"].evaluated_on == date(2026, 8, 3)
    kimi = rows["Kimi K3.1 Pro (max)"]
    assert kimi.methodology == "Kimi K3.1 Pro launch blog."
    assert kimi.metrics == {METRIC_NAME: 51.7} and kimi.best_rank == 4

    again = _sync(session, parse_swe_marathon_bundle(BUNDLE))
    assert (again.adopted, again.created, again.changed) == (0, 0, 0)


def test_better_effort_revises_the_row_in_place():
    session = _session()
    _seed_production(session)
    _sync(session, parse_swe_marathon_bundle(BUNDLE))
    fixture = _with_config(
        agent="Antigravity CLI",
        model="Gemini 4 Carbon",
        reasoningEffort="max",
        canonicalModel="gemini/gemini-4-carbon",
        passes=[8] * 10 + [1] * 10,
        trials=[8] * 20,
        startedAt="2026-11-09 10:00 UTC",
    )
    stats = _sync(session, parse_swe_marathon_bundle(_bundle(fixture)))
    assert (stats.changed, stats.created) == (1, 0)
    carbon = _rows(session)["Gemini 4 Carbon"]
    assert carbon.metrics == {METRIC_NAME: 56.25}
    assert "(90/160 trials over 20 tasks) at max reasoning effort" in carbon.methodology
    assert carbon.evaluated_on == date(2026, 11, 9)


def test_incomplete_runs_are_skipped():
    fixture = _with_config(
        agent="Codex",
        model="GPT-7",
        reasoningEffort="max",
        canonicalModel="openai/gpt-7",
        passes=[8] * 19 + [None],
        trials=[8] * 19 + [None],
        startedAt="2026-11-09 10:00 UTC",
    )
    labels = {entry.label for entry in parse_swe_marathon_bundle(_bundle(fixture))}
    assert "GPT-7 (Codex)" not in labels


def test_new_models_are_auto_matched_or_handed_to_the_radar():
    session = _session()
    _seed_production(session)
    session.add(
        Paper(
            id=2001,
            title="Introducing Claude Opus 6",
            source="external",
            source_url="https://www.anthropic.com/news/claude-opus-6",
            version="v1",
            is_latest_version=True,
        )
    )
    add_release_evidence(session, 2001)
    session.commit()
    fixture = _with_config(
        agent="Claude Code",
        model="Claude Opus 6",
        reasoningEffort="max",
        canonicalModel="anthropic/claude-opus-6",
        passes=[5] * 20,
        trials=[8] * 20,
        startedAt="2026-11-09 10:00 UTC",
    )
    fixture["configs"].append(
        {
            **fixture["configs"][-1],
            "model": "Muse Nova",
            "agent": "Muse Code",
            "canonicalModel": "meta/muse-nova",
        }
    )
    stats = _sync(session, parse_swe_marathon_bundle(_bundle(fixture)))

    assert stats.auto_matched == ["Claude Opus 6 (Claude Code)"]
    assert stats.unreviewed == ["Muse Nova (Muse Code)"]
    opus = _rows(session)["Claude Opus 6"]
    assert (opus.paper_id, opus.metrics) == (2001, {METRIC_NAME: 62.5})
    signal = session.query(ModelReleaseSignal).one()
    assert (signal.lab, signal.model_name) == ("Meta", "Muse Nova")
    assert signal.lead_url == SWE_MARATHON_URL


def test_managed_rows_dropped_upstream_are_reported_not_deleted():
    session = _session()
    _seed_production(session)
    entries = parse_swe_marathon_bundle(BUNDLE)
    _sync(session, entries)
    stats = _sync(session, [e for e in entries if e.name != "GLM 5.2"])
    assert stats.missing_upstream == ["GLM-5.2 (Claude Code)"]
    assert "GLM-5.2" in _rows(session)


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    _seed_production(session)
    entries = parse_swe_marathon_bundle(BUNDLE)
    _sync(session, entries, commit=False)
    assert _rows(session)["Muse Spark 1.3"].metrics == {METRIC_NAME: 30.62}
    with pytest.raises(RuntimeError, match="refusing"):
        _sync(session, entries[:10])
