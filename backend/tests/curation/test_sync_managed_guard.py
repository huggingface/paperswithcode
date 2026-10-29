from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.models.curation import ApplyMutationRequest
from backend.models.database import Evaluation
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.leaderboard_sync_ownership import (
    is_sync_managed,
    managed_methodology_prefix,
)

PAPER_ID = 123608
TASK_ID = 3
DATASET_ID = 2800
VALS_HEAD = (
    "Managed by the Papers with Code Vals AI Finance Agent v2 live sync. "
    'Official leaderboard entry "Ling 3.0 Flash Fin": 54.93% Accuracy, listed at '
    "https://www.vals.ai/benchmarks/fabv2."
)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def all(self):
        return list(self.rows)

    def one(self):
        (row,) = self.rows
        return row


class _Database:
    def __init__(self, evaluations):
        self.evaluations = list(evaluations)
        self.deleted = []

    def query(self, model):
        assert model is Evaluation
        return _Query(self.evaluations)

    def delete(self, row):
        self.deleted.append(row)


class _EvaluationService:
    def __init__(self, duplicate=None):
        self.updates = []
        self.creates = []
        self.duplicate = duplicate

    def update_evaluation(self, evaluation_id, **values):
        self.updates.append((evaluation_id, values))

    def create_evaluation(self, **values):
        self.creates.append(values)

    def find_leaderboard_duplicate(self, **_identity):
        return self.duplicate


def _existing(methodology: str | None, *, score=54.93, evaluation_id=40025):
    return SimpleNamespace(
        id=evaluation_id,
        paper_id=PAPER_ID,
        task_id=TASK_ID,
        dataset_id=DATASET_ID,
        model_name="Ling-3.0-flash-Fin",
        harness=None,
        methodology=methodology,
        metrics={"Accuracy": score},
        uses_additional_data=False,
        is_open=True,
        best_metric="Accuracy",
        source_url="https://www.vals.ai/benchmarks/fabv2",
        external_source_url="https://www.vals.ai/benchmarks/fabv2",
        best_rank=12,
        evaluated_on=None,
        num_parameters=None,
        hf_model_url=None,
    )


def _proposal(score=59.81, methodology=None):
    return {
        "paper_id": PAPER_ID,
        "task_id": TASK_ID,
        "dataset_id": DATASET_ID,
        "model_name": "Ling-3.0-flash-Fin",
        "metrics": {"Accuracy": score},
        "best_metric": "Accuracy",
        "methodology": methodology,
        "is_open": True,
    }


def _service(existing):
    return CodexCurationCallbackService(
        _Database([existing]),
        evaluation_service=_EvaluationService(),
        association_service=SimpleNamespace(),
    )


def test_curator_cannot_update_a_sync_managed_row():
    # Job 3339830c moved Vals row 40025 from 54.93 to the model card's 59.81.
    service = _service(_existing(VALS_HEAD))
    body = ApplyMutationRequest(
        evaluations=[_proposal(methodology="Official model-card chart.")]
    )

    with pytest.raises(ValueError, match="cannot be updated by curation") as exc:
        service._apply_evaluations(body)
    assert "not_applicable" in str(exc.value)
    assert service.evaluation_service.updates == []


def test_curator_cannot_consolidate_away_a_sync_managed_duplicate():
    service = _service(_existing("Model-card chart."))
    service.db.evaluations.append(_existing(VALS_HEAD, evaluation_id=40026))

    with pytest.raises(ValueError, match="Evaluation 40026"):
        service._apply_evaluations(ApplyMutationRequest(evaluations=[_proposal()]))
    assert service.db.deleted == []


def test_curator_cannot_remove_a_sync_managed_row():
    existing = _existing(VALS_HEAD)
    service = _service(existing)
    removal = {
        "evaluation_id": existing.id,
        "reason": "Superseded by the model card.",
        "before_state": {"id": existing.id},
        "evidence": [{"url": "https://huggingface.co/inclusionAI/Ling-3.0-flash"}],
    }
    body = ApplyMutationRequest(evaluation_removals=[removal])

    with pytest.raises(ValueError, match="cannot be removed by curation"):
        service._apply_evaluation_removals(SimpleNamespace(paper_id=PAPER_ID), body)
    assert service.db.deleted == []


def test_unchanged_resubmission_of_a_sync_managed_row_is_a_no_op():
    service = _service(_existing(VALS_HEAD))
    body = ApplyMutationRequest(evaluations=[_proposal(score=54.93)])

    assert service._apply_evaluations(body) == (0, 0, [])


def test_curator_skips_a_model_already_on_the_leaderboard_from_a_twin_paper():
    twin = SimpleNamespace(id=4945, paper_id=83158)
    service = CodexCurationCallbackService(
        _Database([]),
        evaluation_service=_EvaluationService(duplicate=twin),
        association_service=SimpleNamespace(),
    )
    body = ApplyMutationRequest(evaluations=[_proposal()])

    created, updated, skipped = service._apply_evaluations(body)

    assert (created, updated) == (0, 0)
    assert service.evaluation_service.creates == []
    assert skipped == [
        {
            "task_id": TASK_ID,
            "dataset_id": DATASET_ID,
            "model_name": "Ling-3.0-flash-Fin",
            "harness": None,
            "best_metric": "Accuracy",
            "duplicate_evaluation_id": 4945,
            "duplicate_paper_id": 83158,
        }
    ]


def test_curator_may_still_update_unmanaged_rows():
    service = _service(_existing("Model-card chart, strict-process score."))
    body = ApplyMutationRequest(
        evaluations=[_proposal(methodology="Corrected from the appendix table.")]
    )

    assert service._apply_evaluations(body) == (0, 1, [])


@pytest.mark.parametrize(
    ("methodology", "managed"),
    [
        (VALS_HEAD, True),
        ("  " + managed_methodology_prefix("ARC Prize") + " Notes.", True),
        (managed_methodology_prefix("MMTEB v2"), True),
        ("Managed by the Papers with Code team.", False),
        ("Reported in the Managed by the Papers with Code ARC Prize live sync.", False),
        (None, False),
        ("", False),
    ],
)
def test_is_sync_managed(methodology, managed):
    assert is_sync_managed(methodology) is managed


def test_every_live_sync_marks_its_rows_with_the_shared_prefix():
    services = sorted(
        Path(__file__).parents[2].joinpath("services").glob("*_sync_service.py")
    )
    prefixes = {
        path.stem: getattr(
            importlib.import_module(f"backend.services.{path.stem}"),
            "MANAGED_METHODOLOGY_PREFIX",
            None,
        )
        for path in services
    }
    managed = {name: value for name, value in prefixes.items() if value}

    assert len(managed) >= 18
    for name, prefix in managed.items():
        assert is_sync_managed(f"{prefix} Official leaderboard entry."), name
