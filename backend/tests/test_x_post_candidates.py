from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services import x_post_candidates as service
from backend.services.x_post_candidates import (
    Board,
    Candidate,
    classify_win,
    league_text,
    open_beats_closed_line,
    open_closed_facts,
    open_release_score,
    open_release_text,
    open_sota_text,
    placement,
    plain_text,
    sota_score,
    subject_paper_id,
)
from backend.services.x_trending_post_service import Row


ALL = set(range(100))


def board(rows, *, open_ids, lower=False):
    rows = [Row(eid, pid, model, value) for eid, pid, model, value in rows]
    rows.sort(key=lambda row: row.value, reverse=not lower)
    return Board(rows, lower, set(open_ids))


def test_classify_win_new_sota_beats_every_other_paper():
    b = board(
        [(1, 10, "Mine", 90.0), (2, 10, "Mine small", 80.0), (3, 20, "Prev", 85.0)],
        open_ids={1, 2, 3},
    )
    kind, mine, beaten = classify_win(b, 10, ALL)
    assert (kind, mine.model, beaten.model) == ("new_sota", "Mine", "Prev")


def test_classify_win_lower_is_better():
    b = board([(1, 10, "Mine", 4.7), (2, 20, "Prev", 5.2)], open_ids={1, 2}, lower=True)
    assert classify_win(b, 10, ALL)[0] == "new_sota"
    assert classify_win(b, 20, ALL) is None


def test_classify_win_open_sota_needs_a_closed_leader():
    b = board(
        [
            (1, 30, "Closed", 95.0),
            (2, 10, "Mine", 90.0),
            (3, 20, "Open prev", 88.0),
            (4, 40, "Closed 2", 89.0),
        ],
        open_ids={2, 3},
    )
    kind, mine, beaten = classify_win(b, 10, ALL)
    assert (kind, mine.model, beaten.model) == ("open_sota", "Mine", "Open prev")

    all_open = board(
        [(1, 30, "Open lead", 95.0), (2, 10, "Mine", 90.0), (3, 20, "Prev", 88.0)],
        open_ids={1, 2, 3},
    )
    assert classify_win(all_open, 10, ALL) is None


def test_classify_win_rejects_closed_or_beaten_entries():
    b = board(
        [(1, 30, "Closed", 95.0), (2, 10, "Mine", 90.0), (3, 20, "Open", 91.0)],
        open_ids={3},
    )
    assert classify_win(b, 10, ALL) is None  # mine is closed
    b.open_ids = {2, 3}
    assert classify_win(b, 10, ALL) is None  # another open model is better
    assert classify_win(board([(1, 10, "Only", 1.0)], open_ids={1}), 10, ALL) is None


def test_open_sota_text_names_both_comparisons():
    text = open_sota_text(
        {
            "model": "Qwen4",
            "benchmark": "GPQA",
            "value": "80",
            "metric": "Accuracy",
            "previous_best_open_model": "DeepSeek V4",
            "previous_best_open_value": "78",
            "overall_leader": "GPT-6",
            "overall_leader_value": "88",
        },
        "@Alibaba_Qwen",
    )
    assert "best open model on GPQA (80 Accuracy)" in text
    assert "DeepSeek V4 at 78" in text
    assert "GPT-6, scores 88" in text
    assert text.endswith("Congrats @Alibaba_Qwen!")


def test_plain_text_strips_markdown_links():
    assert (
        plain_text(" A [VLA model](/methods/vla) with [MoE](/methods/moe). ")
        == "A VLA model with MoE."
    )


def test_league_text_handles_ties():
    assert league_text(["Google"], 28, 1166).startswith(
        "Google holds first place on 28 of 1166"
    )
    assert league_text(["Google", "StepFun"], 28, 1166).startswith(
        "Google and StepFun each hold first place on 28 of 1166"
    )


def test_gather_adds_roundups_only_early_in_the_period(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "leaderboard_wins", lambda db, now: [])
    monkeypatch.setattr(service, "open_releases", lambda db, now: [])
    monkeypatch.setattr(service, "trending_papers", lambda db, now: [])
    monkeypatch.setattr(service, "lab_league", lambda db, now: None)
    monkeypatch.setattr(service, "concepts", lambda db, now: [])
    monkeypatch.setattr(
        service,
        "_roundup",
        lambda db, period, now: calls.append(period)
        or Candidate(f"top_papers_{period}", "k", "d", "l"),
    )
    kinds = [c.kind for c in service.gather(None, now=datetime(2026, 6, 1, tzinfo=UTC))]
    assert kinds == ["top_papers_month", "top_papers_week"]  # Monday the 1st
    calls.clear()
    assert service.gather(None, now=datetime(2026, 6, 11, tzinfo=UTC)) == []  # Thursday
    assert calls == []


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass


def test_record_validates_kind_and_post_id():
    db = FakeDb()
    row = service.record(db, kind="concept", subject_key="mid-training", post_id="123")
    assert (row.kind, row.subject_key, row.post_id) == (
        "concept",
        "mid-training",
        "123",
    )
    with pytest.raises(ValueError):
        service.record(db, kind="trending_task", subject_key="x", post_id="1")
    with pytest.raises(ValueError):
        service.record(db, kind="concept", subject_key="x", post_id="https://x.com/1")
    assert len(db.added) == 1


def test_classify_win_ignores_an_old_lead_when_another_result_is_new():
    b = board(
        [(1, 10, "Old best", 90.0), (2, 10, "New small", 70.0), (3, 20, "Prev", 85.0)],
        open_ids={1, 2, 3},
    )
    assert classify_win(b, 10, {2}) is None
    assert classify_win(b, 10, {1})[0] == "new_sota"


def test_open_closed_facts_names_the_best_of_each():
    b = board(
        [(1, 10, "GPT-6", 90.0), (2, 20, "Qwen4", 88.0), (3, 30, "Llama 5", 80.0)],
        open_ids={2, 3},
    )
    facts = open_closed_facts(b, b.rows[1])
    assert facts == {
        "best_open_model": "Qwen4",
        "best_open_value": "88",
        "best_closed_model": "GPT-6",
        "best_closed_value": "90",
    }
    only_open = board([(2, 20, "Qwen4", 88.0)], open_ids={2})
    assert "best_closed_model" not in open_closed_facts(only_open, only_open.rows[0])


def test_sota_score_ranks_open_weights_stories_first():
    open_win = sota_score("new_sota", 10, model_is_open=True, beats_closed=True)
    open_best = sota_score("open_sota", 10, model_is_open=True, beats_closed=False)
    closed_win = sota_score("new_sota", 10, model_is_open=False, beats_closed=True)
    assert open_win > open_best > closed_win
    assert (
        sota_score("new_sota", 10, model_is_open=True, beats_closed=False) == closed_win
    )


def test_open_beats_closed_line():
    line = open_beats_closed_line(
        {"best_closed_model": "GPT-6", "best_closed_value": "90"}
    )
    assert line == "Open weights, ahead of the best closed model, GPT-6 (90)."


def test_placement_counts_open_papers_ahead_and_the_best_closed():
    b = board(
        [
            (1, 10, "GPT-6", 90.0),
            (2, 20, "Qwen4", 88.0),
            (3, 30, "Mine 72B", 86.0),
            (4, 30, "Mine 7B", 70.0),
            (5, 40, "Llama 5", 80.0),
        ],
        open_ids={2, 3, 4, 5},
    )
    place = placement(b, 30)
    assert place["model"] == "Mine 72B"
    assert place["open_rank"] == 2
    assert place["overall_rank"] == 3
    assert place["best_closed_model"] == "GPT-6"
    assert place["ahead_of_best_closed"] is False
    assert placement(b, 10) is None  # closed entries never place
    assert placement(b, 30, eligible={4})["model"] == "Mine 7B"


def test_placement_open_winner_beats_closed():
    b = board([(1, 10, "GPT-6", 80.0), (2, 20, "Qwen4", 88.0)], open_ids={2})
    place = placement(b, 20)
    assert place["open_rank"] == 1 and place["ahead_of_best_closed"] is True


def test_open_release_score_counts_only_top_three_open_placements():
    assert open_release_score([{"open_rank": 7, "entries": 300}]) == 0.0
    assert open_release_score([{"open_rank": 2, "entries": 50}]) == 15.0
    assert (
        open_release_score(
            [{"open_rank": 1, "entries": 20}, {"open_rank": 3, "entries": 10}]
        )
        == 23.0
    )


def test_open_release_text():
    text = open_release_text(
        {
            "model": "Qwen4-72B",
            "parameters_b": 72.0,
            "placements": [
                {
                    "benchmark": "GPQA",
                    "open_rank": 1,
                    "value": "88",
                    "ahead_of_best_closed": True,
                    "best_closed_model": "GPT-6",
                    "best_closed_value": "87",
                },
                {"benchmark": "GPQA", "open_rank": 1},
                {"benchmark": "MMLU", "open_rank": 2},
            ],
        },
        "@Alibaba_Qwen",
    )
    assert text.startswith("New open-weights model: Qwen4-72B, 72.0B.")
    assert "Best open model on GPQA." in text
    assert "beats every closed model, 88 to GPT-6's 87." in text
    assert text.endswith("Congrats @Alibaba_Qwen!")


def test_subject_paper_id_reads_every_key_shape():
    assert subject_paper_id("131917") == 131917
    assert subject_paper_id("625:Accuracy:131917") == 131917
    assert subject_paper_id("open:625:Accuracy:131917") == 131917
    assert subject_paper_id("task:12:625:Accuracy:131917") == 131917
    assert subject_paper_id("2026-W46") is None
