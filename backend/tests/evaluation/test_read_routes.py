"""Typed HTTP contracts for evaluation reads."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.catalog_error_handlers import register_catalog_error_handlers
from backend.services.catalog_errors import (
    CatalogNotFoundError,
    CatalogPersistenceError,
)
from backend.services.evaluation_service import EvaluationService
from backend.utils.exceptions import DatabaseError


def _app(monkeypatch, service):
    from backend.database.connection import get_database_session
    from backend.routers import evaluations

    app = FastAPI()
    register_catalog_error_handlers(app)
    app.include_router(evaluations.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: None
    monkeypatch.setattr(evaluations, "EvaluationService", lambda _db: service)
    return app


def _rank_recalculation_app(monkeypatch, service):
    from backend.database.connection import get_database_session
    from backend.routers import evaluations
    from backend.utils.auth import require_admin

    app = FastAPI()
    register_catalog_error_handlers(app)
    app.include_router(evaluations.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: None
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    monkeypatch.setattr(evaluations, "EvaluationService", lambda _db: service)
    return app


def test_list_route_forwards_filters_to_typed_service(monkeypatch):
    calls = []

    class Service:
        def list_catalog_evaluations(self, **kwargs):
            calls.append(kwargs)
            return {"count": 0, "next_page": None, "previous_page": None, "results": []}

    with TestClient(_app(monkeypatch, Service())) as client:
        response = client.get("/api/v1/evaluations/?dataset_id=3&ordering=best_rank")

    assert response.status_code == 200
    assert calls == [
        {
            "page": 1,
            "page_size": 50,
            "search": None,
            "paper_id": None,
            "task_id": None,
            "include_descendants": False,
            "dataset_id": 3,
            "best_metric": None,
            "is_open": None,
            "external": None,
            "max_parameters_exclusive": None,
            "ordering": "best_rank",
        }
    ]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (CatalogNotFoundError("Evaluation 1 not found"), 404),
        (CatalogPersistenceError("read failed"), 500),
    ],
)
def test_lookup_route_preserves_typed_error_envelope(monkeypatch, error, status):
    class Service:
        def get_catalog_evaluation(self, _evaluation_id):
            raise error

    with TestClient(_app(monkeypatch, Service())) as client:
        response = client.get("/api/v1/evaluations/1")

    assert response.status_code == status
    assert response.json() == {
        "detail": "Internal server error"
        if isinstance(error, CatalogPersistenceError)
        else error.detail
    }


def test_catalog_lookup_converts_falsey_legacy_result_to_typed_not_found(monkeypatch):
    service = EvaluationService(None)
    monkeypatch.setattr(service, "get_evaluation", lambda _evaluation_id: None)

    with pytest.raises(CatalogNotFoundError, match="^Evaluation 1 not found$"):
        service.get_catalog_evaluation(1)


def test_catalog_list_converts_legacy_database_error_to_typed_persistence(monkeypatch):
    service = EvaluationService(None)
    monkeypatch.setattr(
        service,
        "get_evaluations",
        lambda **_kwargs: (_ for _ in ()).throw(DatabaseError("read failed")),
    )

    with pytest.raises(CatalogPersistenceError, match="^read failed$"):
        service.list_catalog_evaluations(ordering=None)


def test_rank_recalculation_hides_and_logs_unexpected_service_errors(
    monkeypatch, caplog
):
    class Service:
        def recalculate_ranks(self, **_kwargs):
            raise DatabaseError("database password leaked")

    with TestClient(
        _rank_recalculation_app(monkeypatch, Service()),
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/api/v1/evaluations/recalculate-ranks?task_id=1&dataset_id=2"
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "database password leaked" in caplog.text
