"""Curation jobs must not undo curator removals or stray off a promoted board.

Regression: on 2026-11-04 a curator deleted TinyAstral's (paper 131754)
LIBERO-Pro row 46540 after author feedback. The next day a
``benchmark-promotion`` re-check queued for dataset 3280 re-read the paper and
re-created the same score on LIBERO-Pro (dataset 2915) as row 46867.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.models.curation import ApplyMutationRequest
from backend.models.database import Evaluation
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    promoted_dataset_id,
)

PAPER_ID = 131754
TASK_ID = 11
LIBERO_PRO = 2915
PROMOTED = 3280


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def all(self):
        return list(self.rows)


class _OneQuery(_Query):
    def __init__(self, row):
        super().__init__([row])

    def one(self):
        (row,) = self.rows
        return row


class _Database:
    def __init__(self, evaluations=()):
        self.evaluations = {row.id: row for row in evaluations}
        self.deleted = []

    def query(self, model):
        assert model is Evaluation
        return _Query([])

    def get(self, model, evaluation_id):
        assert model is Evaluation
        return self.evaluations.get(evaluation_id)

    def delete(self, row):
        self.deleted.append(row)


class _EvaluationService:
    def __init__(self):
        self.creates = []

    def create_evaluation(self, **values):
        self.creates.append(values)

    def find_leaderboard_duplicate(self, **_identity):
        return None


def _service(evaluations=()):
    return CodexCurationCallbackService(
        _Database(evaluations),
        evaluation_service=_EvaluationService(),
        association_service=SimpleNamespace(),
    )


def _proposal(dataset_id=LIBERO_PRO):
    return {
        "paper_id": PAPER_ID,
        "task_id": TASK_ID,
        "dataset_id": dataset_id,
        "model_name": "TinyAstral-4B",
        "metrics": {"Success Rate": 78.3},
        "best_metric": "Success Rate",
        "is_open": True,
    }


def _stored(evaluation_id, dataset_id):
    return SimpleNamespace(
        id=evaluation_id, paper_id=PAPER_ID, task_id=TASK_ID, dataset_id=dataset_id
    )


def _removal(evaluation_id):
    return {
        "evaluation_id": evaluation_id,
        "reason": "Superseded by the paper's best result.",
        "before_state": {"id": evaluation_id},
        "evidence": [{"url": "https://arxiv.org/abs/2611.00001"}],
    }


def _promotion_job():
    return SimpleNamespace(
        paper_id=PAPER_ID,
        trigger="benchmark-promotion",
        policy_version=f"new-benchmark-{PROMOTED}",
    )


def test_promoted_dataset_comes_from_the_policy_version():
    assert promoted_dataset_id(_promotion_job()) == PROMOTED
    assert promoted_dataset_id(SimpleNamespace(policy_version="v1")) is None
    assert promoted_dataset_id(SimpleNamespace(policy_version=None)) is None


def test_promotion_job_cannot_write_another_benchmark():
    service = _service()
    body = ApplyMutationRequest(evaluations=[_proposal(LIBERO_PRO)])

    with pytest.raises(ValueError, match=r"only benchmark dataset 3280") as exc:
        service._validate_promotion_scope(_promotion_job(), body)
    assert "[2915]" in str(exc.value)


def test_promotion_job_cannot_remove_rows_on_another_benchmark():
    service = _service([_stored(46000, LIBERO_PRO)])
    body = ApplyMutationRequest(
        evaluations=[_proposal(PROMOTED)], evaluation_removals=[_removal(46000)]
    )

    with pytest.raises(ValueError, match=r"\[2915\]"):
        service._validate_promotion_scope(_promotion_job(), body)


def test_promotion_job_may_write_its_own_benchmark():
    service = _service([_stored(46001, PROMOTED)])
    body = ApplyMutationRequest(
        evaluations=[_proposal(PROMOTED)], evaluation_removals=[_removal(46001)]
    )

    service._validate_promotion_scope(_promotion_job(), body)


def test_other_jobs_are_not_scoped_to_one_benchmark():
    service = _service()
    body = ApplyMutationRequest(evaluations=[_proposal(LIBERO_PRO)])
    row = SimpleNamespace(trigger="hf-daily-cron", policy_version="daily-v3")

    service._validate_promotion_scope(row, body)


def test_removed_row_is_not_recreated():
    service = _service()
    body = ApplyMutationRequest(evaluations=[_proposal()])

    created, updated, duplicates, removed = service._apply_evaluations(
        body, removed_leaderboards={(TASK_ID, LIBERO_PRO): 46540}
    )

    assert (created, updated, duplicates) == (0, 0, [])
    assert removed == [
        {
            "task_id": TASK_ID,
            "dataset_id": LIBERO_PRO,
            "model_name": "TinyAstral-4B",
            "harness": None,
            "best_metric": "Success Rate",
            "removed_evaluation_id": 46540,
        }
    ]
    assert service.evaluation_service.creates == []


def test_other_boards_are_still_created():
    service = _service()
    body = ApplyMutationRequest(evaluations=[_proposal(PROMOTED)])

    created, _updated, _duplicates, removed = service._apply_evaluations(
        body, removed_leaderboards={(TASK_ID, LIBERO_PRO): 46540}
    )

    assert created == 1
    assert removed == []


def test_surviving_row_cannot_be_removed_on_a_removed_board():
    # With or without a replacement, a curator already chose the survivor.
    survivor = _stored(46100, LIBERO_PRO)
    survivor.methodology = None
    service = _service([survivor])
    service.db.query = lambda _model: _OneQuery(survivor)
    body = ApplyMutationRequest(evaluation_removals=[_removal(46100)])

    with pytest.raises(ValueError, match="cannot remove evaluation 46100"):
        service._apply_evaluation_removals(
            SimpleNamespace(paper_id=PAPER_ID),
            body,
            removed_leaderboards={(TASK_ID, LIBERO_PRO): 46540},
        )
    assert service.db.deleted == []


def test_rows_on_other_boards_can_still_be_removed():
    row = _stored(46101, PROMOTED)
    row.methodology = None
    service = _service([row])
    service.db.query = lambda _model: _OneQuery(row)
    body = ApplyMutationRequest(evaluation_removals=[_removal(46101)])

    removed = service._apply_evaluation_removals(
        SimpleNamespace(paper_id=PAPER_ID),
        body,
        removed_leaderboards={(TASK_ID, LIBERO_PRO): 46540},
    )

    assert removed == 1
    assert service.db.deleted == [row]
