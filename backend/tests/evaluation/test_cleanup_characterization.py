"""Characterization and invariant tests for evaluation cleanup."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from backend.services import (
    dataset_service,
    evaluation_service,
    github_issue_body_service,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.metric_value_service import parse_metric_value
from backend.utils.exceptions import DatabaseError


def _database_unavailable() -> OperationalError:
    return OperationalError(
        "SELECT leaderboard metrics",
        {},
        RuntimeError("database unavailable"),
    )


def test_dataset_task_validation_propagates_operational_error():
    db = Mock()
    db.query.side_effect = _database_unavailable()

    with pytest.raises(OperationalError, match="database unavailable"):
        EvaluationService(db)._validate_dataset_task_consistency(1, 2)


def test_create_evaluation_rolls_back_when_validation_operational_error_propagates():
    db = Mock()
    db.query.side_effect = _database_unavailable()
    service = EvaluationService(db)

    with pytest.raises(DatabaseError, match="Failed to create evaluation"):
        service.create_evaluation(
            paper_id=1,
            task_id=2,
            dataset_id=3,
            metrics={"Accuracy": "50.0"},
            best_metric="Accuracy",
        )

    db.rollback.assert_called_once_with()
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_update_evaluation_rolls_back_without_mutation_when_validation_error_propagates():
    evaluation = SimpleNamespace(
        task_id=2,
        dataset_id=3,
        model_name="Before",
        metrics={"Accuracy": "50.0"},
        best_metric="Accuracy",
        harness=None,
    )
    db = Mock()
    evaluation_query = Mock()
    evaluation_query.filter.return_value.first.return_value = evaluation
    db.query.side_effect = [evaluation_query, _database_unavailable()]
    service = EvaluationService(db)

    with pytest.raises(DatabaseError, match="Failed to update evaluation"):
        service.update_evaluation(
            evaluation_id=10,
            dataset_id=4,
            model_name="After",
        )

    assert evaluation.dataset_id == 3
    assert evaluation.model_name == "Before"
    assert evaluation.metrics == {"Accuracy": "50.0"}
    db.rollback.assert_called_once_with()
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        pytest.param(50, 50.0, id="integer"),
        pytest.param(50.25, 50.25, id="float"),
        pytest.param("50.25", 50.25, id="numeric-string"),
        pytest.param("50.0±0.2", 50.0, id="unicode-uncertainty"),
        pytest.param("50.0 +/- 0.2", 50.0, id="ascii-plus-minus-uncertainty"),
        pytest.param("50,0", 50.0, id="decimal-comma"),
        pytest.param(None, None, id="none"),
        pytest.param("not-a-number", None, id="invalid-text"),
    ],
)
def test_metric_parsing_is_identical_for_every_consumer(raw_value, expected):
    actual = {
        "ranking": evaluation_service.parse_metric_value(raw_value),
        "dataset_summary": dataset_service.parse_metric_value(raw_value),
        "github_issue": github_issue_body_service.parse_metric_value(raw_value),
    }

    assert actual == {consumer: expected for consumer in actual}


def test_metric_consumers_reference_the_canonical_parser():
    assert evaluation_service.parse_metric_value is parse_metric_value
    assert dataset_service.parse_metric_value is parse_metric_value
    assert github_issue_body_service.parse_metric_value is parse_metric_value
