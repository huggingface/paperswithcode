import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.curation import ApplyMutationRequest
from backend.models.evaluations import EvaluationScoreEvidence
from backend.services.evaluation_scale_service import (
    validate_board_scale,
    validate_source_score,
)


def evidence(value, scale):
    return EvaluationScoreEvidence(
        task_id=11,
        dataset_id=792,
        metric="Success Rate",
        source_value=value,
        source_scale=scale,
        source_url="https://arxiv.org/html/2609.12641",
        table_reference="Table II, ImageWAM LIT, Overall",
    )


@pytest.mark.parametrize(
    "target,source,units,stored",
    [
        ("percentage", 86.89, "0-100", 86.89),
        (" [0, 1] ", 86.89, "0-100", 0.8689),
        ("percent", 0.8689, "0-1", 86.89),
        ("fraction", 0.8689, "0-1", 0.8689),
        ("0-100", 0.1, "0-100", 0.1),
        ("0-100", 0, "0-100", 0),
        ("0-100", 100, "0-100", 100),
        ("0-1000", 832, "native", 832),
        (None, 0.5, "native", 0.5),
        ("seconds", 42, "native", 42),
    ],
)
def test_source_units_determine_conversion(target, source, units, stored):
    validate_source_score(target, stored, evidence(source, units))


@pytest.mark.parametrize(
    "target,source,units,stored",
    [
        ("0-100", 86.89, "0-100", 0.8689),
        ("0-100", 98.4, "0-100", 0.984),
        ("0-1", 86.89, "0-100", 86.89),
        ("0-1", 0.8689, "0-1", 0.008689),
        ("0-100", 86.89, "0-1", 8689),
        ("0-100", -1, "0-100", -1),
        ("0-100", 101, "0-100", 101),
        ("0-100", 0.8689, "native", 0.8689),
        (None, 86.89, "0-100", 0.8689),
        ("0-1000", 83.2, "0-100", 832),
        ("seconds", 42, "native", 0.42),
    ],
)
def test_rejects_wrong_or_unsupported_conversions(target, source, units, stored):
    with pytest.raises(ValueError):
        validate_source_score(target, stored, evidence(source, units))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_source_value_must_be_finite(value):
    with pytest.raises(ValidationError):
        evidence(value, "0-100")


def test_score_evidence_survives_proposal_serialization_and_matches_job_schema():
    from jsonschema import validate

    body = ApplyMutationRequest(score_evidence=[evidence(86.89, "0-100")])
    payload = body.model_dump(mode="json")
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "jobs/schemas/curation_proposal.schema.json"
        ).read_text()
    )
    validate(payload, schema)
    assert (
        ApplyMutationRequest.model_validate(payload).score_evidence
        == body.score_evidence
    )


PERCENT_BOARD = [92.1, 88.4, 95.0, 71.3]


@pytest.mark.parametrize(
    "target,source,suggested",
    [("0-100", 0.923, "submit 92.3"), ("percentage", 1.0, "submit 100")],
)
def test_board_rejects_fraction_declared_as_percent(target, source, suggested):
    with pytest.raises(ValueError, match=suggested):
        validate_board_scale(target, evidence(source, "0-100"), lambda: PERCENT_BOARD)


def test_one_genuine_sub_one_row_does_not_disable_the_board_check():
    board = [0.44, *range(15, 100)]  # AIME-like: a lone weak model below 1
    with pytest.raises(ValueError, match="at least 18"):
        validate_board_scale("0-100", evidence(0.714, "0-100"), lambda: board)


@pytest.mark.parametrize(
    "target,source,units,board",
    [
        # Converted fractions and ordinary percentages are not ambiguous.
        ("0-100", 0.923, "0-1", PERCENT_BOARD),
        ("0-100", 92.3, "0-100", PERCENT_BOARD),
        ("0-100", 0, "0-100", PERCENT_BOARD),
        # Too few rows, or a board whose low tail genuinely scores near zero.
        ("0-100", 0.9, "0-100", [92.1, 88.4]),
        ("0-100", 0.9, "0-100", [0.5, 1.2, 2.4, 3.1]),
        ("0-100", 0.9, "0-100", [37.1, 95.0, 0.9, 54.4]),
        ("0-100", 0.9, "0-100", [1.06, 2.5, 3.0, *range(20, 67)]),
        # Only 0-100 leaderboards are checked.
        ("0-1", 0.923, "0-100", PERCENT_BOARD),
        ("seconds", 0.9, "native", PERCENT_BOARD),
    ],
)
def test_board_accepts_unambiguous_or_supported_scores(target, source, units, board):
    validate_board_scale(target, evidence(source, units), lambda: board)


def test_board_values_load_only_for_ambiguous_scores():
    def fail():
        raise AssertionError("board values should not be loaded")

    validate_board_scale("0-100", evidence(92.3, "0-100"), fail)
    validate_board_scale("0-1", evidence(0.5, "0-100"), fail)
