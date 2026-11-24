import pytest

from backend.models.database import Evaluation


def test_constructor_mirrors_source_url_into_legacy_column():
    row = Evaluation(source_url="https://example.org/leaderboard")

    assert row.legacy_external_source_url == "https://example.org/leaderboard"
    assert row.external_source_url == "https://example.org/leaderboard"


def test_assignment_keeps_legacy_column_identical():
    row = Evaluation(source_url="https://example.org/old")

    row.source_url = "https://example.org/new"
    assert row.legacy_external_source_url == "https://example.org/new"

    row.source_url = None
    assert row.legacy_external_source_url is None


def test_external_source_url_is_a_read_only_alias():
    row = Evaluation(source_url="https://example.org/a")

    with pytest.raises(AttributeError):
        row.external_source_url = "https://example.org/b"
    with pytest.raises(AttributeError):
        Evaluation(external_source_url="https://example.org/b")


def test_legacy_column_maps_to_the_persisted_column_name():
    column = Evaluation.__table__.c["external_source_url"]

    assert Evaluation.legacy_external_source_url.property.columns[0] is column


def _api_model(row):
    from datetime import datetime, timezone
    from unittest.mock import Mock

    from backend.services.evaluation_service import EvaluationService

    row.id = 1
    row.paper_id = 2
    row.task_id = 3
    row.dataset_id = 4
    row.metrics = {"Accuracy": 1.0}
    row.external = True
    row.uses_additional_data = False
    row.is_open = True
    row.created_at = row.updated_at = datetime.now(timezone.utc)
    return EvaluationService(Mock())._evaluation_model(
        row, None, None, None, None, set()
    )


def test_api_returns_external_source_url_as_alias_of_source_url():
    model = _api_model(Evaluation(source_url="https://example.org/board"))

    assert model.source_url == "https://example.org/board"
    assert model.external_source_url == model.source_url


def test_api_falls_back_to_unmirrored_legacy_column():
    row = Evaluation()
    row.legacy_external_source_url = "https://example.org/legacy"

    model = _api_model(row)

    assert model.source_url == "https://example.org/legacy"
    assert model.external_source_url == model.source_url
