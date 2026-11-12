"""Focused tests for full-corpus normalization with targeted paper writes."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "scripts"
    / "hourly"
    / "calculate_paper_trending_scores.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "calculate_paper_trending_scores_for_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_population_ignores_hf_aggregator_links():
    cron = _load_module()
    github_rows = [
        SimpleNamespace(
            paper_id=1,
            existing=False,
            stored_score=None,
            stored_g=None,
            stored_h=None,
            github_raw=None,
        ),
        SimpleNamespace(
            paper_id=2,
            existing=True,
            stored_score=100.0,
            stored_g=0.0,
            stored_h=0.0,
            github_raw=None,
        ),
    ]
    hf_rows = [
        SimpleNamespace(
            paper_id=1, kind="model", repo_id="org/m", trending_score=5, linked_papers=1
        ),
        SimpleNamespace(
            paper_id=1,
            kind="space",
            repo_id="tardellirs/paper-pulse",
            trending_score=9,
            linked_papers=1,
        ),
        SimpleNamespace(
            paper_id=2,
            kind="space",
            repo_id="org/feed",
            trending_score=9,
            linked_papers=40,
        ),
    ]
    session = Mock()
    session.execute.side_effect = [
        Mock(fetchall=Mock(return_value=github_rows)),
        Mock(fetchall=Mock(return_value=hf_rows)),
        Mock(fetchall=Mock(return_value=[SimpleNamespace(paper_id=2, x_raw=12.5)])),
    ]

    population = cron.load_population(session, cutoff=None)

    assert population[1]["artifacts"] == [("model", 5.0)]
    assert population[2]["artifacts"] == []
    assert population[1]["x_raw"] == 0.0
    assert population[2]["x_raw"] == 12.5
    assert population[1]["hourly_lift"] == 0.0
    assert population[2]["hourly_lift"] == 100.0
    # Paper 2 only had an aggregator, so its stored score is cleared.
    github_corpus, hf_corpora = cron.derive_corpora(population)
    updates, clears = cron.build_score_changes(population, github_corpus, hf_corpora)
    assert [update["id"] for update in updates] == [1]
    assert clears == [2]


def test_targeted_compute_only_changes_selected_papers(monkeypatch):
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        2: {
            "github_raw": 2.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        3: {
            "github_raw": 0.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
    }
    calls = []

    def fake_compute(github_raw, github_corpus, artifacts, artifact_corpora, **_x):
        calls.append((github_raw, list(github_corpus)))
        return github_raw, github_raw, 0.0, 0.0

    monkeypatch.setattr(cron, "compute_paper_score", fake_compute)
    github_corpus, hf_corpora = cron.derive_corpora(population)
    updates, clears = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2, 3]
    )

    assert [update["id"] for update in updates] == [2]
    assert clears == [3]
    assert len(calls) == 2
    # The selected score is still normalized against paper 1's larger signal.
    assert calls[0][1] == [2.0, 10.0]


def test_full_and_targeted_compute_agree_for_same_paper(monkeypatch):
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        2: {
            "github_raw": 2.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)
    full, _ = cron.build_score_changes(population, github_corpus, hf_corpora)
    targeted, _ = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2]
    )

    assert targeted == [next(update for update in full if update["id"] == 2)]


def test_targeted_rescore_keeps_hourly_x_lift(monkeypatch):
    """The 15-minute job runs without PWC_TRENDING_X_WEIGHT; it must not drop
    the X lift the hourly job wrote (2611.09501 flipped between #1 and #324)."""
    cron = _load_module()
    monkeypatch.delenv("PWC_TRENDING_X_WEIGHT", raising=False)
    lifted = cron.hourly_lift(100.0, 0.9841, 0.0)
    population = {
        1: {
            "github_raw": 10.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        2: {
            "github_raw": 2.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 242.0,
            "hourly_lift": lifted,
        },
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)

    targeted, _ = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2]
    )
    full, _ = cron.build_score_changes(population, github_corpus, hf_corpora)

    assert lifted == 100.0
    assert targeted[0]["score"] == 100.0
    # The hourly run recomputes the lift from its own settings (here: weight 0).
    assert next(u for u in full if u["id"] == 2)["score"] == 25.0


def test_targeted_rescore_keeps_pinned_paper_without_live_signal():
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        2: {
            "github_raw": 0.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 80.0,
        },
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)

    updates, clears = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2]
    )

    assert updates[0]["id"] == 2 and updates[0]["score"] == 80.0
    assert clears == []


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ((None, None, None), 0.0),
        ((50.0, 0.5, 0.5), 0.0),
        ((50.005, 0.5001, 0.4999), 0.0),
        ((100.0, 0.98, 0.0), 100.0),
        ((72.0, 0.4, 0.2), 72.0),
    ],
)
def test_hourly_lift(stored, expected):
    cron = _load_module()
    assert cron.hourly_lift(*stored) == expected


def test_decaying_pins_share_state_for_arxiv_and_internal_paper_ids(
    monkeypatch, tmp_path
):
    cron = _load_module()
    state_path = tmp_path / "trending_pin_state.json"
    monkeypatch.setattr(cron, "PIN_STATE_PATH", state_path)
    monkeypatch.setenv("PWC_TRENDING_PIN_ARXIV_IDS", "2606.16140:48")
    monkeypatch.setenv("PWC_TRENDING_PIN_PAPER_IDS", "104054:96")

    rows = [
        SimpleNamespace(id=1, arxiv_id="2606.16140", trending_score=50.0),
        SimpleNamespace(id=104054, arxiv_id=None, trending_score=50.0),
    ]
    selection = Mock()
    selection.fetchall.return_value = rows
    session = Mock()
    session.execute.side_effect = [selection, Mock(), Mock()]

    assert cron.apply_decaying_trending_pins(session) == 2

    selection_params = session.execute.call_args_list[0].args[1]
    assert selection_params == {
        "arxiv_ids": ["2606.16140"],
        "paper_ids": [104054],
    }
    update_params = [call.args[1] for call in session.execute.call_args_list[1:]]
    assert update_params == [
        {"id": 1, "score": 100.0},
        {"id": 104054, "score": 100.0},
    ]
    session.commit.assert_called_once_with()

    state = json.loads(state_path.read_text())
    assert state["2606.16140"]["decay_hours"] == 48.0
    assert state["paper:104054"]["decay_hours"] == 96.0


def test_full_run_clears_scores_of_papers_that_left_the_window(monkeypatch):
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        }
    }
    monkeypatch.setattr(cron, "load_population", lambda _session, _cutoff: population)
    monkeypatch.setattr(
        cron, "get_aged_out_scored_paper_ids", lambda _session, _cutoff: [7, 8]
    )
    writes = []
    monkeypatch.setattr(
        cron,
        "write_scores",
        lambda _session, updates, clears: writes.append((updates, clears))
        or (len(updates), len(clears)),
    )

    result = cron.calculate_paper_scores(Mock())

    assert writes[0][1] == [7, 8]
    assert result["cleared"] == 2


def test_targeted_run_leaves_aged_out_scores_to_the_full_run(monkeypatch):
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        }
    }
    monkeypatch.setattr(cron, "load_population", lambda _session, _cutoff: population)
    aged_out = Mock(return_value=[7])
    monkeypatch.setattr(cron, "get_aged_out_scored_paper_ids", aged_out)
    monkeypatch.setattr(
        cron,
        "write_scores",
        lambda _session, updates, clears: (len(updates), len(clears)),
    )

    cron.calculate_paper_scores(Mock(), paper_ids=[1])

    aged_out.assert_not_called()


def test_x_only_paper_stays_unscored_while_x_weight_is_zero():
    cron = _load_module()
    population = {
        1: {
            "github_raw": 10.0,
            "existing": False,
            "artifacts": [],
            "x_raw": 0.0,
            "hourly_lift": 0.0,
        },
        2: {
            "github_raw": 0.0,
            "existing": True,
            "artifacts": [],
            "x_raw": 50.0,
            "hourly_lift": 0.0,
        },
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)

    updates, clears = cron.build_score_changes(
        population, github_corpus, hf_corpora, x_sorted=[50.0], x_weight=0.0
    )
    assert [update["id"] for update in updates] == [1]
    assert clears == [2]

    updates, clears = cron.build_score_changes(
        population, github_corpus, hf_corpora, x_sorted=[50.0], x_weight=1.0
    )
    by_id = {update["id"]: update for update in updates}
    assert by_id[2]["x"] == 1.0
    assert by_id[2]["score"] == pytest.approx(100, abs=1e-3)
    # The GitHub-only paper keeps its score: X only lifts.
    assert by_id[1]["score"] == pytest.approx(50, abs=1e-3)
    assert clears == []


def test_x_settings_accept_a_full_lift_and_reject_out_of_range(monkeypatch):
    cron = _load_module()
    monkeypatch.setenv("PWC_TRENDING_X_WEIGHT", "1.5")
    with pytest.raises(ValueError, match="PWC_TRENDING_X_WEIGHT"):
        cron.x_settings()
    monkeypatch.setenv("PWC_TRENDING_X_WEIGHT", "1")
    assert cron.x_settings() == (1.0, 1.0)
    monkeypatch.setenv("PWC_TRENDING_X_WEIGHT", "0.3333")
    monkeypatch.setenv("PWC_TRENDING_X_MIN_LIKES_PER_HOUR", "2")
    assert cron.x_settings() == (0.3333, 2.0)
