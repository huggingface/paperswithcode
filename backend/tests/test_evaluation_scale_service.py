import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.api import ApplyMutationRequest
from backend.models.evaluations import EvaluationScoreEvidence
from backend.services.evaluation_scale_service import validate_source_score


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
            Path(__file__).resolve().parents[2]
            / "jobs/schemas/curation_proposal.schema.json"
        ).read_text()
    )
    validate(payload, schema)
    assert (
        ApplyMutationRequest.model_validate(payload).score_evidence
        == body.score_evidence
    )
