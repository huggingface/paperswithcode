"""Parsing and sync tests for the frontier boards added with Gemini 4 Carbon."""

import json
from datetime import UTC, datetime
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
from backend.services import carbon_board_syncs as boards
from backend.services.carbon_board_identities import IDENTITIES
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    LiveLeaderboardSyncService,
    ModelIdentity,
    js_literal,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# Trimmed snapshots of each official leaderboard taken on 2026-10-29.
FIXTURES = Path(__file__).parent / "fixtures" / "carbon_boards"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _by_name(entries: list[LeaderboardEntry]) -> dict[str, LeaderboardEntry]:
    return {entry.name: entry for entry in entries}


def test_js_literal_decodes_minified_and_hand_written_data():
    source = "x=1,m={vb2:{'A b':{v:.5,w:-.25,list:[1,2,],}}, /* note */ n:'it\\'s'};"
    assert js_literal(source, source.index("{"), "m") == {
        "vb2": {"A b": {"v": 0.5, "w": -0.25, "list": [1, 2]}},
        "n": "it's",
    }
    with pytest.raises(ValueError, match="not plain data"):
        js_literal("m={a:f(1)}", 2, "m")
    with pytest.raises(ValueError, match="unterminated"):
        js_literal("m={a:[1}", 2, "m")


def test_parse_vals_index_picks_the_ranked_table():
    entries = boards.parse_vals_index(_fixture("vals_index.html"))
    assert len(entries) == 29
    carbon = _by_name(entries)["Gemini 4 Carbon"]
    assert (carbon.value, carbon.harness) == (70.36, None)
    assert carbon.detail == "70.36% Accuracy"


def test_parse_swe_sweep_converts_fractions_to_percent():
    entries = _by_name(boards.parse_swe_sweep(_fixture("swe_sweep.html")))
    assert len(entries) == 13
    assert entries["Opus 5.5 (xhigh)"].value == 3.61
    assert entries["Opus 5.5 (xhigh)"].harness == "mini-SWE-agent"
    assert entries["Opus 5.5 (xhigh)"].lab == "Anthropic"


def test_parse_vending_bench_2_reads_every_model_from_the_chunk():
    entries = _by_name(
        boards.parse_vending_bench_2(_fixture("vending_bench_2_chunk.js"))
    )
    assert len(entries) == 73
    carbon = entries["Gemini 4 Carbon"]
    assert carbon.value == 16484.21
    assert carbon.detail.startswith("$16,484.21 mean final balance over ")


def test_fetch_vending_bench_2_follows_imports_to_the_data_chunk():
    chunk = _fixture("vending_bench_2_chunk.js")
    pages = {
        boards.VENDING_BENCH_2_URL: '<link href="../_app/immutable/nodes/27.abc.js">'
        '<link href="../_app/immutable/chunks/unrelated.js">',
        "https://andonlabs.com/_app/immutable/nodes/27.abc.js": 'import{a}from"../chunks/data.js";',
        "https://andonlabs.com/_app/immutable/chunks/data.js": chunk,
    }

    def handler(request):
        return httpx.Response(200, text=pages[str(request.url)])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert len(boards.fetch_vending_bench_2(client)) == 73


def test_parse_blueprint_bench_2_skips_human_and_floor_rows():
    entries = _by_name(
        boards.parse_blueprint_bench_2(_fixture("blueprint_bench_2.html"))
    )
    assert entries["Gemini 4 Carbon"].value == 0.586
    assert not any(name.endswith("*") for name in entries)
    assert all(entry.value > 0 for entry in entries.values())


def test_parse_riemann_bench_reads_visible_percentages():
    entries = _by_name(boards.parse_riemann_bench(_fixture("riemann_bench.html")))
    assert len(entries) == 44
    assert entries["GPT 5.6 Sol"].value == pytest.approx(0.744)
    # "Hy" + "Hy4 Preview" names the model once.
    assert "Hy4 Preview" in entries


def test_parse_cwe_bench_reads_the_json_ld_item_list():
    entries = _by_name(boards.parse_cwe_bench(_fixture("cwe_bench.html")))
    assert len(entries) == 12
    assert (entries["Gemini 4 Carbon"].value, entries["Gemini 4 Carbon"].harness) == (
        0.71,
        "Antigravity",
    )
    assert "pass@4 not reported" in entries["Inkling"].detail


def test_parse_exploitgym_keeps_only_six_hour_full_set_runs():
    entries = _by_name(boards.parse_exploitgym(_fixture("exploitgym.json")))
    assert entries["GPT-5.6 Sol"].value == 33.7
    assert entries["GPT-5.6 Sol"].harness == "Codex CLI"
    assert entries["Claude Opus 5.5"].harness == "Not reported"
    # 2h runs, token-budgeted runs, and selected subsets are other protocols.
    assert "GPT-5.4" not in entries
    assert "GPT-6 Astra" not in entries
    assert all("subset" not in entry.detail for entry in entries.values())


def test_parse_cybergym_keeps_the_default_model_focused_level_1_view():
    entries = boards.parse_cybergym(
        _fixture("cybergym.json"), now=datetime(2026, 10, 29, tzinfo=UTC)
    )
    by_label = {entry.label: entry for entry in entries}
    assert by_label["DeepSeek-V4-Pro (DeepSeek Agent)"].value == 83.3
    # One model can appear under several agents; each is its own row.
    assert by_label["GPT-5.4 (OpenAI Agent)"].value == 79.0
    assert by_label["GPT-5.4 (Codex CLI)"].value == 66.3
    names = {entry.name for entry in entries}
    # Agent-focused systems, 30-trial runs, and dynamic / test-time-memory
    # runs are other views of the board.
    assert "Multi-model (DeepSeek-V4.1-Flash, Abliterated GLM-5.2)" not in names
    assert all("dynamic" not in entry.detail for entry in entries)
    assert len(entries) == 44


def test_parse_cybergym_waits_for_held_back_rows():
    data = json.loads(_fixture("cybergym.json"))
    row = next(r for r in data["level1"] if r["model"] == "GLM-5.1")
    row["visible_after"] = "2026-11-01T00:00:00-07:00"
    entries = boards.parse_cybergym(
        json.dumps(data), now=datetime(2026, 10, 29, tzinfo=UTC)
    )
    assert "GLM-5.1" not in {entry.name for entry in entries}


def test_parse_patcheval_verified_reads_the_readme_results_table():
    entries = _by_name(
        boards.parse_patcheval_verified(_fixture("patcheval_verified.md"))
    )
    assert entries["gpt-5.6-sol"].value == 83.91
    assert entries["gpt-5.6-sol"].harness == "Codex"
    assert entries["seed-2.1-turbo"].harness == "Trae CLI"
    assert entries["GLM 5.2"].harness == "OpenCode"
    assert "193/230 CVEs repaired" in entries["gpt-5.6-sol"].detail
    assert set(entries) == set(IDENTITIES["patcheval-verified"])


@pytest.mark.parametrize(
    ("parse", "fixture", "old", "new", "message"),
    [
        (
            boards.parse_vals_index,
            "vals_index.html",
            "Accuracy",
            "Score",
            "0 ranked tables",
        ),
        (
            boards.parse_blueprint_bench_2,
            "blueprint_bench_2.html",
            ">Score<",
            ">Points<",
            "header changed",
        ),
        (
            boards.parse_cwe_bench,
            "cwe_bench.html",
            "Programmatic pass@1 71%",
            "pass@1 71%",
            "description changed",
        ),
        (
            boards.parse_riemann_bench,
            "riemann_bench.html",
            "Riemann-bench Leaderboard",
            "Leaderboard",
            "0 leaderboard blocks",
        ),
        (
            boards.parse_exploitgym,
            "exploitgym.json",
            '"total": 869',
            '"total": 9',
            "instance total changed",
        ),
        (
            boards.parse_cybergym,
            "cybergym.json",
            '"level1"',
            '"levelOne"',
            "no level1 list",
        ),
        (
            boards.parse_patcheval_verified,
            "patcheval_verified.md",
            "| Agent | Model | Pass@1 |",
            "| Agent | Model | Resolved |",
            "header changed",
        ),
        (
            boards.parse_patcheval_verified,
            "patcheval_verified.md",
            "193/230",
            "193/300",
            "case count changed",
        ),
    ],
)
def test_parsers_fail_on_layout_changes(parse, fixture, old, new, message):
    source = _fixture(fixture)
    assert old in source
    with pytest.raises(ValueError, match=message):
        parse(source.replace(old, new, 1))


def test_every_board_has_identities_and_a_configured_fetcher():
    assert set(boards.BOARD_SYNCS) == {
        "sync_vals_index",
        "sync_swe_sweep",
        "sync_vending_bench_2",
        "sync_blueprint_bench_2",
        "sync_riemann_bench",
        "sync_cwe_bench",
        "sync_exploitgym",
        "sync_cybergym",
        "sync_patcheval_verified",
    }
    for sync in boards.BOARD_SYNCS.values():
        assert len(sync.board.identities) >= sync.board.min_selected
        assert sync.board.identities is IDENTITIES[sync.board.dataset_slug]


# --- Engine -------------------------------------------------------------------

TASK_ID = 15
DATASET_ID = 9000
METRIC = "Resolved"
OPUS = "https://www.anthropic.com/claude-opus-5-5"
SOL = "https://openai.com/index/gpt-5-6"


def _board(**overrides) -> LiveLeaderboard:
    fields = dict(
        source="Test Board",
        provider="test-board",
        url="https://example.com/board",
        task_slug="coding-agents",
        dataset_slug="test-board",
        metric=METRIC,
        identities={
            "Opus 5.5 (xhigh)": ModelIdentity("Claude Opus 5.5", source_url=OPUS),
            "Sol 5.6 (high)": ModelIdentity("GPT-5.6 Sol", source_url=SOL),
            "Sol 5.6 (xhigh)": ModelIdentity("GPT-5.6 Sol", source_url=SOL),
        },
        min_selected=2,
        protocol="Test protocol.",
    )
    return LiveLeaderboard(**{**fields, **overrides})


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
    session.add(Dataset(id=DATASET_ID, name="Test Board", slug="test-board"))
    session.add(Metric(id=1, name=METRIC, direction="higher_is_better"))
    session.add(
        TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID, supports_harness=True)
    )
    session.add(TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=1))
    for paper_id, url in ((1, OPUS), (2, SOL)):
        session.add(
            Paper(
                id=paper_id,
                title=url,
                source="external",
                source_url=url,
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    return session


def _entry(name: str, value: float, harness: str | None = "mini-SWE-agent"):
    return LeaderboardEntry(name, value, f"{value}% resolved", harness=harness)


def _rows(session: Session) -> dict[str, Evaluation]:
    return {
        f"{row.model_name} ({row.harness})": row
        for row in session.query(Evaluation).filter(Evaluation.dataset_id == DATASET_ID)
    }


def test_sync_creates_rows_keeping_each_models_best_setting():
    session = _session()
    stats = LiveLeaderboardSyncService(session, _board()).sync(
        [
            _entry("Opus 5.5 (xhigh)", 3.61),
            _entry("Sol 5.6 (high)", 3.1),
            _entry("Sol 5.6 (xhigh)", 4.7),
        ]
    )
    rows = _rows(session)
    assert set(rows) == {
        "Claude Opus 5.5 (mini-SWE-agent)",
        "GPT-5.6 Sol (mini-SWE-agent)",
    }
    sol = rows["GPT-5.6 Sol (mini-SWE-agent)"]
    assert sol.metrics == {METRIC: 4.7}
    assert sol.methodology.startswith(
        "Managed by the Papers with Code Test Board live sync. "
        'Official leaderboard entry "Sol 5.6 (xhigh) (mini-SWE-agent)"'
    )
    assert sol.best_rank == 1 and sol.external is True
    assert (stats.created, stats.matched) == (2, 2)


def test_sync_adopts_a_hand_imported_row_and_its_unreported_harness():
    session = _session()
    hand = Evaluation(
        paper_id=1,
        task_id=TASK_ID,
        dataset_id=DATASET_ID,
        model_name="Claude Opus 5.5",
        harness="Not reported",
        metrics={METRIC: 3.6},
        best_metric=METRIC,
        methodology="Hand import from the system card.",
        is_open=False,
    )
    session.add(hand)
    session.commit()
    stats = LiveLeaderboardSyncService(session, _board()).sync(
        [_entry("Opus 5.5 (xhigh)", 3.61), _entry("Sol 5.6 (xhigh)", 4.7)]
    )
    assert stats.adopted == 1 and stats.created == 1
    assert (
        session.query(Evaluation).filter_by(model_name="Claude Opus 5.5").count() == 1
    )
    assert (hand.harness, hand.metrics) == ("mini-SWE-agent", {METRIC: 3.61})
    assert hand.source_url == "https://example.com/board"

    # A second run only reports unchanged managed rows.
    again = LiveLeaderboardSyncService(session, _board()).sync(
        [_entry("Opus 5.5 (xhigh)", 3.61), _entry("Sol 5.6 (xhigh)", 4.7)]
    )
    assert (again.created, again.changed, again.adopted) == (0, 0, 0)


def test_sync_skips_excluded_names_and_reports_rows_that_leave_upstream():
    session = _session()
    service = LiveLeaderboardSyncService(session, _board())
    service.sync([_entry("Opus 5.5 (xhigh)", 3.61), _entry("Sol 5.6 (xhigh)", 4.7)])

    board = _board(excluded={"Sol 5.6 (xhigh)": "partial run"})
    stats = LiveLeaderboardSyncService(session, board).sync(
        [
            _entry("Opus 5.5 (xhigh)", 3.7),
            _entry("Sol 5.6 (high)", 3.1),
            _entry("Sol 5.6 (xhigh)", 9.9),
        ]
    )
    assert stats.excluded == 1
    assert _rows(session)["GPT-5.6 Sol (mini-SWE-agent)"].metrics == {METRIC: 3.1}
    assert stats.missing_upstream == []

    gone = LiveLeaderboardSyncService(session, _board()).sync(
        [_entry("Opus 5.5 (xhigh)", 3.7), _entry("Sol 5.6 (high)", 3.1)]
    )
    assert gone.missing_upstream == []
    rows = _rows(session)
    assert len(rows) == 2  # never deleted


def test_sync_reports_unknown_models_to_the_release_radar():
    session = _session()
    stats = LiveLeaderboardSyncService(session, _board()).sync(
        [
            _entry("Opus 5.5 (xhigh)", 3.61),
            _entry("Sol 5.6 (xhigh)", 4.7),
            LeaderboardEntry(
                "Mystery 9", 1.0, "1.0% resolved", "mini-SWE-agent", "Lab X"
            ),
        ]
    )
    assert stats.unreviewed == ["Mystery 9 (mini-SWE-agent)"]
    assert session.query(ModelReleaseSignal).count() == 1


def test_sync_refuses_a_collapsed_board_without_writing():
    session = _session()
    with pytest.raises(RuntimeError, match="only 1 reviewed entries"):
        LiveLeaderboardSyncService(session, _board()).sync(
            [_entry("Opus 5.5 (xhigh)", 3.61)]
        )
    assert session.query(Evaluation).count() == 0


def test_sync_dry_run_rolls_back():
    session = _session()
    LiveLeaderboardSyncService(session, _board()).sync(
        [_entry("Opus 5.5 (xhigh)", 3.61), _entry("Sol 5.6 (xhigh)", 4.7)], commit=False
    )
    assert session.query(Evaluation).count() == 0


def test_parse_vals_index_ignores_empty_tables():
    html = _fixture("vals_index.html").replace("<body>", "<body><table></table>", 1)
    assert len(boards.parse_vals_index(html)) == 29


def test_riemann_fetch_sends_the_surge_browser_user_agent():
    seen = {}

    def handler(request):
        seen["agent"] = request.headers["User-Agent"]
        return httpx.Response(200, text=_fixture("riemann_bench.html"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert len(boards.BOARD_SYNCS["sync_riemann_bench"].fetch(client)) == 44
    assert seen["agent"].startswith("Mozilla/5.0 (X11; Linux x86_64)")
