"""Blind judge for Codex/Pi shadow pairs and the per-stage cutover gates."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.models.database import Dataset, Method, Task
from backend.services import curation_pair_judge as judge_module
from backend.services.curation_pair_judge import (
    CandidateVerdict,
    JudgeOutput,
    _ask_judge,
    _stage_report,
    disagreement_candidates,
    judge_pair,
)


class FakeDB:
    def __init__(self, rows: dict) -> None:
        self.rows = rows

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        return iter(self.rows.get(model, []))


def _taxonomy(id_, name, description=""):
    return SimpleNamespace(id=id_, name=name, description=description)


def _job(kind, pair_diff=None, proposal=None, **overrides):
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind=kind,
        proposal=proposal or {},
        pair_diff=pair_diff,
        pair_judgment=None,
        context_snapshot={
            "paper": {"id": 7, "title": "A paper", "arxiv_id": "2611.00001"}
        },
        **overrides,
    )


def _enrich_diff():
    empty = {"both": [], "codex_only": [], "pi_only": []}
    return {
        "kind": "enrich-paper",
        "enrich": {
            "task_ids": {"both": [1], "codex_only": [2], "pi_only": []},
            "method_ids": {"both": [], "codex_only": [], "pi_only": [10]},
            "repositories": {**empty, "pi_only": ["https://github.com/o/r"]},
            "project_pages": empty,
            "hf_models": empty,
            "hf_datasets": empty,
            "hf_spaces": empty,
        },
    }


def _eval_diff():
    return {
        "kind": "add-evals",
        "evaluations": {
            "same": [{"task_id": 1, "dataset_id": 5, "metric": "Acc", "value": 1.0}],
            "different": [
                {
                    "task_id": 1,
                    "dataset_id": 6,
                    "metric": "Acc",
                    "codex": {"model_name": "M-L", "value": 80.1},
                    "pi": {"model_name": "M-S", "value": 77.0},
                }
            ],
            "codex_only": [],
            "pi_only": [
                {
                    "task_id": 1,
                    "dataset_id": 5,
                    "metric": "F1",
                    "pi": {"model_name": "M-L", "value": 3.0},
                }
            ],
        },
    }


def _eval_proposal(rows):
    return {
        "evaluations": [
            {"task_id": t, "dataset_id": d, "metrics": {m: 0}, "methodology": note}
            for t, d, m, note in rows
        ]
    }


def test_enrich_candidates_are_blind_and_resolve_taxonomy_names():
    db = FakeDB(
        {
            Task: [_taxonomy(2, "Image Classification", "Assign labels")],
            Method: [_taxonomy(10, "GRPO", "Group relative policy optimization")],
        }
    )
    pi = _job("enrich-paper", _enrich_diff())
    candidates = disagreement_candidates(db, pi, _job("enrich-paper"))

    assert [c["id"] for c in candidates] == ["c1", "c2", "c3"]
    by_field = {c["field"]: c for c in candidates}
    assert by_field["task_ids"]["origin"] == "codex"
    assert by_field["method_ids"]["origin"] == "pi"
    assert by_field["method_ids"]["prompt"] == (
        "method tag: GRPO: Group relative policy optimization"
    )
    assert by_field["repositories"]["value"] == "https://github.com/o/r"
    for candidate in candidates:
        assert "codex" not in candidate["prompt"].lower()
        assert " pi" not in candidate["prompt"].lower()


def test_eval_conflicts_become_two_candidates_with_each_runners_note():
    db = FakeDB({Dataset: [_taxonomy(6, "ImageNet")], Task: [_taxonomy(1, "Cls")]})
    codex = _job("add-evals", proposal=_eval_proposal([(1, 6, "Acc", "codex note")]))
    pi = _job(
        "add-evals",
        _eval_diff(),
        proposal=_eval_proposal([(1, 6, "Acc", "pi note"), (1, 5, "F1", "f1 note")]),
    )
    candidates = disagreement_candidates(db, pi, codex)

    conflict = [c for c in candidates if c["conflict"]]
    assert {c["origin"] for c in conflict} == {"codex", "pi"}
    assert {c["conflict"] for c in conflict} == {"1|6|Acc"}
    notes = {c["origin"]: c["prompt"] for c in conflict}
    assert "benchmark ImageNet" in notes["codex"]
    assert "codex note" in notes["codex"] and "pi note" in notes["pi"]
    lone = next(c for c in candidates if not c["conflict"])
    assert lone["origin"] == "pi" and lone["value"]["metric"] == "F1"


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _client(*responses):
    messages = FakeMessages(responses)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def _response(stop_reason="end_turn", verdicts=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=["block"],
        parsed_output=None if verdicts is None else JudgeOutput(verdicts=verdicts),
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
    )


def test_ask_judge_continues_after_pause_turn_and_sums_usage():
    verdicts = [CandidateVerdict(candidate_id="c1", verdict="correct", reason="r")]
    client, messages = _client(_response("pause_turn"), _response(verdicts=verdicts))

    output, usage = _ask_judge(client, "claude-opus-5-5", "prompt")

    assert output.verdicts == verdicts
    assert usage == {"input_tokens": 200, "output_tokens": 20}
    assert messages.calls[1]["messages"][-1] == {
        "role": "assistant",
        "content": ["block"],
    }
    assert messages.calls[0]["fallbacks"] == "default"


def test_ask_judge_rejects_a_refusal():
    client, _ = _client(_response("refusal"))
    with pytest.raises(RuntimeError, match="refusal"):
        _ask_judge(client, "claude-opus-5-5", "prompt")


def test_judge_pair_unblinds_verdicts_and_marks_missing_ones_unsure(monkeypatch):
    monkeypatch.setattr(judge_module, "_paper_text", lambda paper, settings: "text")
    db = FakeDB({Task: [_taxonomy(2, "Cls")], Method: [_taxonomy(10, "GRPO")]})
    pi = _job("enrich-paper", _enrich_diff())
    candidates = disagreement_candidates(db, pi, _job("enrich-paper"))
    first = candidates[0]["id"]
    client, messages = _client(
        _response(
            verdicts=[
                CandidateVerdict(candidate_id=first, verdict="incorrect", reason="no")
            ]
        )
    )

    judgment = judge_pair(
        db, pi, _job("enrich-paper"), client=client, settings=get_settings()
    )

    graded = {c["id"]: c for c in judgment["candidates"]}
    assert graded[first]["verdict"] == "incorrect"
    assert {c["verdict"] for c in graded.values() if c["id"] != first} == {"unsure"}
    assert graded[first]["origin"] in {"codex", "pi"}
    assert "Disputed candidates" in messages.calls[0]["messages"][0]["content"]


def test_judge_pair_skips_the_model_without_disagreements():
    diff = _enrich_diff()
    for split in diff["enrich"].values():
        split["codex_only"], split["pi_only"] = [], []
    client, messages = _client()

    judgment = judge_pair(
        FakeDB({}),
        _job("enrich-paper", diff),
        _job("enrich-paper"),
        client=client,
        settings=get_settings(),
    )

    assert judgment["candidates"] == [] and messages.calls == []


def _summary(status, seconds):
    return {"status": status, "duration_ms": seconds * 1000}


def _pair(kind, diff, candidates, codex=("completed", 100), pi=("completed", 120)):
    row = _job(kind, {**diff, "codex": _summary(*codex), "pi": _summary(*pi)})
    row.pair_judgment = None if candidates is None else {"candidates": candidates}
    return row


def _graded(origin, verdict, field="evaluation"):
    return {"origin": origin, "verdict": verdict, "field": field}


def test_eval_gates_count_agreed_rows_as_correct_for_both_runners():
    pairs = [
        _pair(
            "add-evals",
            _eval_diff(),
            [
                _graded("codex", "correct"),
                _graded("pi", "wrong_score"),
                _graded("pi", "correct"),
                _graded("pi", "unsure"),
            ],
        ),
        _pair("add-evals", _eval_diff(), None, pi=("failed", 300)),
    ]
    report = _stage_report(pairs, "add-evals")

    assert report["judged"] == 1 and report["unsure"] == 1
    assert report["eval_precision"] == {"codex": 1.0, "pi": round(2 / 3, 4)}
    assert report["wrong_scores"] == {"codex": 0, "pi": 1}
    assert report["success_rate"] == {"codex": 1.0, "pi": 0.5}
    assert report["duration_ratio"] == 2.1
    assert report["gates"] == {
        "enough_pairs": False,
        "all_judged": False,
        "success": False,
        "median_time": False,
        "eval_precision": False,
        "wrong_scores": False,
    }
    assert report["passes"] is False


def test_enrich_tag_precision_ignores_link_candidates(monkeypatch):
    monkeypatch.setattr(judge_module, "MIN_PAIRS", 1)
    pairs = [
        _pair(
            "enrich-paper",
            _enrich_diff(),
            [
                _graded("codex", "correct", "task_ids"),
                _graded("pi", "correct", "method_ids"),
                _graded("pi", "incorrect", "repositories"),
            ],
        )
    ]
    report = _stage_report(pairs, "enrich-paper")

    assert report["tag_precision"] == {"codex": 1.0, "pi": 1.0}
    assert report["gates"]["tag_precision"] is True
    assert report["passes"] is True
