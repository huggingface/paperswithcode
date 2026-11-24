import pytest

from backend.models.database import Evaluation


def test_external_source_url_column_is_not_mapped():
    assert "external_source_url" not in Evaluation.__table__.c


def test_external_source_url_is_a_read_only_alias():
    row = Evaluation(source_url="https://example.org/a")

    assert row.external_source_url == "https://example.org/a"
    with pytest.raises(AttributeError):
        row.external_source_url = "https://example.org/b"
    with pytest.raises(AttributeError):
        Evaluation(external_source_url="https://example.org/b")


def test_snapshot_restore_accepts_legacy_external_source_url_key(monkeypatch):
    from unittest.mock import Mock

    from backend.services import evaluation_service

    row = Evaluation(id=7, paper_id=1, task_id=2, dataset_id=3, metrics={})
    snapshot = {
        "id": 7,
        "paper_id": 1,
        "task_id": 2,
        "dataset_id": 3,
        "metrics": {},
        "source_url": None,
        "external_source_url": "https://example.org/legacy",
    }
    db = Mock()
    db.get.return_value = row
    service = evaluation_service.EvaluationService(db)
    monkeypatch.setattr(
        service, "_validate_dataset_task_consistency", lambda *_: (True, None)
    )
    monkeypatch.setattr(
        evaluation_service.LeaderboardMetricService,
        "validate_metrics_for_leaderboard",
        lambda *_: (True, None),
    )

    service.restore_evaluation_snapshot(snapshot)

    assert row.source_url == "https://example.org/legacy"


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
