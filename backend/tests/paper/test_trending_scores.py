"""Focused tests for full-corpus normalization with targeted paper writes."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


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


def test_targeted_compute_only_changes_selected_papers(monkeypatch):
    cron = _load_module()
    population = {
        1: {"github_raw": 10.0, "existing": False, "artifacts": []},
        2: {"github_raw": 2.0, "existing": True, "artifacts": []},
        3: {"github_raw": 0.0, "existing": True, "artifacts": []},
    }
    calls = []

    def fake_compute(github_raw, github_corpus, artifacts, artifact_corpora):
        calls.append((github_raw, list(github_corpus)))
        return github_raw, github_raw, 0.0

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
        1: {"github_raw": 10.0, "existing": False, "artifacts": []},
        2: {"github_raw": 2.0, "existing": False, "artifacts": []},
    }
    github_corpus, hf_corpora = cron.derive_corpora(population)
    full, _ = cron.build_score_changes(population, github_corpus, hf_corpora)
    targeted, _ = cron.build_score_changes(
        population, github_corpus, hf_corpora, paper_ids=[2]
    )

    assert targeted == [next(update for update in full if update["id"] == 2)]


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
