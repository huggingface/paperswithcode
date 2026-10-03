"""Public contracts for evaluation mutation routes."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.catalog_error_handlers import register_catalog_error_handlers
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


def _evaluation_app(monkeypatch, service):
    from backend.database.connection import get_database_session
    from backend.routers import evaluations
    from backend.utils.auth import evaluation_mutation_context

    app = FastAPI()
    register_catalog_error_handlers(app)
    app.include_router(evaluations.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: None
    app.dependency_overrides[evaluation_mutation_context] = lambda: {"actor": {}}
    monkeypatch.setattr(evaluations, "EvaluationCurationService", lambda _db: service)
    return app


def _evaluation_curation_app(monkeypatch, evaluation_service):
    """Exercise real curation translation while isolating persistence."""
    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.services import evaluation_curation_service
    from backend.utils.auth import evaluation_mutation_context

    class MutationService:
        def __init__(self, _db):
            pass

        def mutate(self, *, apply, **_kwargs):
            apply()
            return [], SimpleNamespace(before_snapshot=[]), False

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: None
    app.dependency_overrides[evaluation_mutation_context] = lambda: {
        "actor": {"role": "admin", "hf_subject": "route-test"},
        "idempotency_key": None,
        "expected_version": None,
        "request_id": "route-test",
    }
    monkeypatch.setattr(
        evaluation_curation_service, "EvaluationService", lambda _db: evaluation_service
    )
    monkeypatch.setattr(
        evaluation_curation_service, "CatalogMutationService", MutationService
    )
    return app


def _evaluation_payload():
    now = datetime.now(UTC)
    return {
        "id": "1",
        "paper_id": "1",
        "task_id": "1",
        "dataset_id": "1",
        "metrics": {"mAP": "1"},
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (CatalogNotFoundError("Evaluation 1 not found"), 404, "Evaluation 1 not found"),
        (
            CatalogPersistenceError("database unavailable"),
            500,
            "Internal server error",
        ),
        (
            CatalogConflictError({"code": "stale_catalog_version"}),
            409,
            {"code": "stale_catalog_version"},
        ),
    ],
)
def test_delete_uses_catalog_error_contract(monkeypatch, error, status, detail):
    class Service:
        def delete(self, **_kwargs):
            raise error

    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = client.delete("/api/v1/evaluations/1")

    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_delete_success(monkeypatch):
    class Service:
        def delete(self, **_kwargs):
            return None

    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = client.delete("/api/v1/evaluations/1")

    assert response.status_code == 204


@pytest.mark.parametrize(
    "method,path", [("post", "/api/v1/evaluations/"), ("put", "/api/v1/evaluations/1")]
)
@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (CatalogValidationError("invalid metric"), 400, "invalid metric"),
        (CatalogNotFoundError("Evaluation 1 not found"), 404, "Evaluation 1 not found"),
        (
            CatalogConflictError({"code": "stale_catalog_version"}),
            409,
            {"code": "stale_catalog_version"},
        ),
        (CatalogPersistenceError("write failed"), 500, "Internal server error"),
    ],
)
def test_post_put_preserve_typed_error_envelopes(
    monkeypatch, method, path, error, status, detail
):
    class Service:
        def create(self, **_kwargs):
            raise error

        def update(self, **_kwargs):
            raise error

    payload = {"paper_id": 1, "task_id": 1, "dataset_id": 1, "metrics": {"mAP": "1"}}
    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = getattr(client, method)(path, json=payload)
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_post_forwards_payload_and_returns_success(monkeypatch):
    calls = []

    class Service:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _evaluation_payload()

    payload = {"paper_id": 1, "task_id": 2, "dataset_id": 3, "metrics": {"mAP": "1"}}
    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        response = client.post("/api/v1/evaluations/", json=payload)
    assert response.status_code == 201
    assert response.json()["id"] == "1"
    assert {key: calls[0]["payload"][key] for key in payload} == payload


@pytest.mark.parametrize(
    ("method", "path", "legacy_error", "status"),
    [
        (
            "post",
            "/api/v1/evaluations/",
            PaperNotFoundError("Paper with ID 1 not found"),
            404,
        ),
        ("post", "/api/v1/evaluations/", DatabaseError("evaluation write failed"), 500),
        (
            "put",
            "/api/v1/evaluations/1",
            PaperNotFoundError("Paper with ID 1 not found"),
            404,
        ),
        ("put", "/api/v1/evaluations/1", DatabaseError("evaluation write failed"), 500),
    ],
)
def test_post_put_translate_legacy_service_errors_at_boundary(
    monkeypatch, method, path, legacy_error, status
):
    class LegacyEvaluationService:
        def create_evaluation(self, **_kwargs):
            raise legacy_error

        def update_evaluation(self, *_args, **_kwargs):
            raise legacy_error

    payload = {"paper_id": 1, "task_id": 2, "dataset_id": 3, "metrics": {"mAP": "1"}}
    with TestClient(
        _evaluation_curation_app(monkeypatch, LegacyEvaluationService())
    ) as client:
        response = getattr(client, method)(path, json=payload)

    assert response.status_code == status
    assert response.json() == {
        "detail": "Internal server error"
        if isinstance(legacy_error, DatabaseError)
        else str(legacy_error)
    }


def test_put_forwards_payload_and_returns_success(monkeypatch):
    calls = []

    class EvaluationService:
        def update_evaluation(self, evaluation_id, **kwargs):
            calls.append((evaluation_id, kwargs))

        def get_evaluation(self, evaluation_id):
            assert evaluation_id == 1
            return _evaluation_payload()

    payload = {"model_name": "Updated model", "metrics": {"mAP": "2"}}
    with TestClient(
        _evaluation_curation_app(monkeypatch, EvaluationService())
    ) as client:
        response = client.put("/api/v1/evaluations/1", json=payload)

    assert response.status_code == 200
    assert response.json()["id"] == "1"
    evaluation_id, forwarded = calls[0]
    assert evaluation_id == 1
    assert forwarded["commit"] is False
    assert forwarded["model_name"] == "Updated model"
    assert forwarded["metrics"] == {"mAP": "2"}
    assert forwarded["harness_set"] is False


@pytest.mark.parametrize(
    "method,path", [("post", "/api/v1/evaluations/"), ("put", "/api/v1/evaluations/1")]
)
@pytest.mark.parametrize(
    "legacy_error",
    [
        PaperNotFoundError("Evaluation 1 not found"),
        DatabaseError("evaluation hydration failed"),
    ],
)
def test_post_put_translate_legacy_hydration_errors_at_boundary(
    monkeypatch, method, path, legacy_error
):
    class LegacyHydrationService:
        def create_evaluation(self, **_kwargs):
            return SimpleNamespace(id=1)

        def update_evaluation(self, *_args, **_kwargs):
            return None

        def get_evaluation(self, _evaluation_id):
            raise legacy_error

    payload = {"paper_id": 1, "task_id": 2, "dataset_id": 3, "metrics": {"mAP": "1"}}
    with TestClient(
        _evaluation_curation_app(monkeypatch, LegacyHydrationService())
    ) as client:
        response = getattr(client, method)(path, json=payload)

    expected_status = 404 if isinstance(legacy_error, PaperNotFoundError) else 500
    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Internal server error"
        if isinstance(legacy_error, DatabaseError)
        else str(legacy_error)
    }


@pytest.mark.parametrize("batch", [False, True])
def test_public_update_cannot_override_patch_presence_with_internal_flags(
    monkeypatch, batch
):
    calls = []

    class Service:
        def update(self, **kwargs):
            calls.append(kwargs["payload"])
            return _evaluation_payload()

        def batch(self, **kwargs):
            calls.append(kwargs["operations"][0]["payload"])
            return {"evaluations": []}

    payload = {"source_url": None, "source_url_set": False, "num_parameters_set": True}
    with TestClient(_evaluation_app(monkeypatch, Service())) as client:
        if batch:
            # The batch route checks the actor's role before adapting operations.
            from backend.utils.auth import evaluation_mutation_context

            client.app.dependency_overrides[evaluation_mutation_context] = lambda: {
                "actor": {"role": "admin"}
            }
            response = client.post(
                "/api/v1/evaluations/batch",
                json={
                    "paper_id": 1,
                    "operations": [
                        {"operation": "update", "evaluation_id": 1, "payload": payload}
                    ],
                },
            )
        else:
            response = client.put("/api/v1/evaluations/1", json=payload)
    assert response.status_code == 200
    assert calls[0]["source_url_set"] is True
    assert calls[0]["num_parameters_set"] is False
