from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.models.curation import ApplyMutationRequest
from backend.models.database import Evaluation, Metric, TaskDataset
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)

PAPER_ID = 42
TASK_ID = 7
DATASET_ID = 11


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def all(self):
        return list(self.rows)

    def one_or_none(self):
        return self.rows[0] if self.rows else None


class _Database:
    def __init__(self, *, metric=None, evaluations=(), leaderboard=True):
        self.rows = {
            Metric: [metric] if metric else [],
            Evaluation: list(evaluations),
            TaskDataset: [SimpleNamespace()] if leaderboard else [],
        }

    def query(self, model):
        return _Query(self.rows[model])

    def get(self, model, key):
        return next((row for row in self.rows[model] if row.id == key), None)


def _row():
    return SimpleNamespace(
        kind="add-evals",
        trigger="admin",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=PAPER_ID,
        url_candidates={},
    )


def _service(db) -> CodexCurationCallbackService:
    return CodexCurationCallbackService(
        db, evaluation_service=SimpleNamespace(), association_service=SimpleNamespace()
    )


def _body(outcome: dict, **extra) -> ApplyMutationRequest:
    return ApplyMutationRequest(
        source_coverage=[
            {
                "url": "https://arxiv.org/abs/2111.12993",
                "status": "inspected",
                "benchmark_outcomes": [
                    {"benchmark": "Kinetics-400", "detail": "...", **outcome}
                ],
            }
        ],
        **extra,
    )


def _already_present(value=82.0, **overrides):
    return {
        "disposition": "already_present",
        "task_id": TASK_ID,
        "dataset_id": DATASET_ID,
        "metric": "Top-1 Accuracy",
        "value": value,
        **overrides,
    }


def _evaluation(evaluation_id: int, score, metric="Top-1 Accuracy"):
    return SimpleNamespace(id=evaluation_id, paper_id=PAPER_ID, metrics={metric: score})


HIGHER = SimpleNamespace(name="Top-1 Accuracy", direction="higher_is_better")
LOWER = SimpleNamespace(name="Top-1 Accuracy", direction="lower_is_better")


def test_already_present_rejected_when_only_other_papers_rank_higher():
    # Other papers' rows are never returned: the query is scoped to this paper.
    service = _service(_Database(metric=HIGHER, evaluations=[]))

    with pytest.raises(ValueError, match="is not already_present"):
        service._validate_mutation(
            _row(),
            _body(
                _already_present(
                    detail="Other papers already rank higher on this leaderboard."
                )
            ),
        )


def test_already_present_rejected_when_own_row_is_worse():
    service = _service(_Database(metric=HIGHER, evaluations=[_evaluation(1, 80.1)]))

    with pytest.raises(ValueError, match="equal to or better than 82"):
        service._validate_mutation(_row(), _body(_already_present(82.0)))


@pytest.mark.parametrize("score", [82.0, "82%", 84.5])
def test_already_present_accepted_when_own_row_is_equal_or_better(score):
    service = _service(_Database(metric=HIGHER, evaluations=[_evaluation(1, score)]))

    service._validate_mutation(_row(), _body(_already_present(82.0)))


def test_already_present_respects_lower_is_better_direction():
    service = _service(_Database(metric=LOWER, evaluations=[_evaluation(1, 3.0)]))
    service._validate_mutation(_row(), _body(_already_present(3.5)))

    service = _service(_Database(metric=LOWER, evaluations=[_evaluation(1, 4.0)]))
    with pytest.raises(ValueError, match="is not already_present"):
        service._validate_mutation(_row(), _body(_already_present(3.5)))


def test_already_present_ignores_rows_on_other_metrics():
    service = _service(
        _Database(metric=HIGHER, evaluations=[_evaluation(1, 99.0, metric="Top-5")])
    )

    with pytest.raises(ValueError, match="is not already_present"):
        service._validate_mutation(_row(), _body(_already_present(82.0)))


def test_already_present_ignores_rows_removed_by_the_same_proposal():
    existing = _evaluation(1, 85.0)
    service = _service(_Database(metric=HIGHER, evaluations=[existing]))
    removal = {
        "evaluation_id": 1,
        "reason": "Consolidate onto the better appendix result.",
        "before_state": {"id": 1},
        "evidence": [{"url": "https://arxiv.org/abs/2111.12993"}],
    }

    with pytest.raises(ValueError, match="is not already_present"):
        service._validate_mutation(
            _row(), _body(_already_present(82.0), evaluation_removals=[removal])
        )


@pytest.mark.parametrize("missing", ["task_id", "dataset_id", "metric", "value"])
def test_already_present_requires_the_exact_leaderboard_and_value(missing):
    outcome = _already_present()
    outcome.pop(missing)
    service = _service(_Database(metric=HIGHER, evaluations=[_evaluation(1, 90.0)]))

    with pytest.raises(ValueError, match="must name task_id"):
        service._validate_mutation(_row(), _body(outcome))


def test_already_present_rejects_unconfigured_metric():
    service = _service(_Database(metric=None, evaluations=[_evaluation(1, 90.0)]))

    with pytest.raises(ValueError, match="not configured"):
        service._validate_mutation(_row(), _body(_already_present()))


def test_other_dispositions_do_not_need_leaderboard_ids():
    service = _service(_Database())

    service._validate_mutation(_row(), _body({"disposition": "not_applicable"}))


def test_skips_naming_configured_leaderboards_are_reported():
    body = ApplyMutationRequest(
        source_coverage=[
            {
                "url": "https://arxiv.org/abs/2111.12993",
                "status": "inspected",
                "benchmark_outcomes": [
                    {
                        "benchmark": "Kinetics-400",
                        "disposition": "not_applicable",
                        "detail": "Base model only.",
                        "task_id": TASK_ID,
                        "dataset_id": DATASET_ID,
                        "metric": "Top-1 Accuracy",
                    },
                    {
                        "benchmark": "Unrelated",
                        "disposition": "not_applicable",
                        "detail": "No leaderboard.",
                    },
                    {
                        "benchmark": "ImageNet",
                        "disposition": "evaluation",
                        "detail": "Submitted.",
                        "task_id": 1,
                        "dataset_id": 2,
                    },
                ],
            }
        ]
    )

    skipped = _service(_Database())._skipped_configured_leaderboards(body)

    assert skipped == [
        {
            "source_url": "https://arxiv.org/abs/2111.12993",
            "benchmark": "Kinetics-400",
            "disposition": "not_applicable",
            "task_id": TASK_ID,
            "dataset_id": DATASET_ID,
            "metric": "Top-1 Accuracy",
            "value": None,
            "detail": "Base model only.",
        }
    ]
    assert (
        _service(_Database(leaderboard=False))._skipped_configured_leaderboards(body)
        == []
    )
