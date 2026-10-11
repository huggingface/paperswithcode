"""HTTP translation contracts for catalog domain errors."""

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
from backend.models.organizations import Organizations
from backend.models.papers import ProjectPage, ProjectPages, Repositories
from backend.models.tasks import Task
from backend.models.taxonomy import Method, Methods, Tasks
from backend.utils.auth import require_catalog_mutator, require_fresh_catalog_mutator
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


def _catalog_client(monkeypatch):
    from backend.database.connection import get_database_session
    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    return TestClient(app)


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (CatalogNotFoundError("Paper with ID 1 not found"), 404),
        (CatalogConflictError("A paper with this ID already exists"), 409),
        (CatalogValidationError("arxiv_id is required"), 400),
        (CatalogPersistenceError("Failed to save paper"), 500),
    ],
)
def test_catalog_domain_errors_have_stable_http_translation(error, status_code, caplog):
    app = FastAPI()
    register_catalog_error_handlers(app)

    @app.get("/catalog-error")
    def catalog_error():
        raise error

    with TestClient(app) as client:
        response = client.get("/catalog-error")

    assert response.status_code == status_code
    if isinstance(error, CatalogPersistenceError):
        assert response.json() == {"detail": "Internal server error"}
        assert str(error) in caplog.text
    else:
        assert response.json() == {"detail": error.detail}


def test_catalog_conflict_preserves_structured_detail():
    error = CatalogConflictError(
        {"code": "stale_catalog_version", "current_version": "current"}
    )
    app = FastAPI()
    register_catalog_error_handlers(app)

    @app.get("/catalog-conflict")
    def catalog_conflict():
        raise error

    with TestClient(app) as client:
        response = client.get("/catalog-conflict")

    assert response.status_code == 409
    assert response.json() == {"detail": error.detail}


def test_legacy_catalog_errors_are_typed_catalog_errors():
    assert isinstance(PaperNotFoundError("missing"), CatalogNotFoundError)
    assert isinstance(DatabaseError("unavailable"), CatalogPersistenceError)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            PaperNotFoundError("Paper with ID 1 not found"),
            (404, {"detail": "Paper with ID 1 not found"}),
        ),
        (
            DatabaseError("Failed to save paper"),
            (500, {"detail": "Internal server error"}),
        ),
    ],
)
def test_legacy_catalog_errors_use_the_typed_http_contract(error, expected, caplog):
    app = FastAPI()
    register_catalog_error_handlers(app)

    @app.get("/legacy-error")
    def legacy_error():
        raise error

    with TestClient(app) as client:
        response = client.get("/legacy-error")

    assert (response.status_code, response.json()) == expected
    if isinstance(error, DatabaseError):
        assert str(error) in caplog.text


@pytest.mark.parametrize(
    ("path", "service", "method", "error", "status"),
    [
        (
            "/api/v1/areas/invalid",
            "backend.services.area_service.AreaService",
            "get_area_by_id",
            CatalogValidationError("Invalid area ID format"),
            400,
        ),
        (
            "/api/v1/areas/404",
            "backend.services.area_service.AreaService",
            "get_area_by_id",
            PaperNotFoundError("Area with ID 404 not found"),
            404,
        ),
        (
            "/api/v1/areas/",
            "backend.services.area_service.AreaService",
            "get_areas",
            CatalogPersistenceError("Failed to retrieve areas"),
            500,
        ),
    ],
)
def test_taxonomy_endpoint_errors_keep_detail_only_envelopes(
    monkeypatch, path, service, method, error, status
):
    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name),
        method,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == status
    assert response.json() == {
        "detail": "Internal server error"
        if isinstance(error, CatalogPersistenceError)
        else str(error)
    }


def test_paper_persistence_errors_are_logged_without_exposing_details(
    monkeypatch, caplog
):
    from backend.services.paper_service import PaperService

    monkeypatch.setattr(
        PaperService,
        "get_recent_papers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            DatabaseError("database password leaked")
        ),
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get("/api/v1/papers/recent")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "database password leaked" in caplog.text


def test_paper_indexing_implementation_errors_are_logged_without_exposing_details(
    monkeypatch, caplog
):
    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.routers import papers
    from backend.services.paper_service import PaperService
    from backend.utils.auth import require_admin

    monkeypatch.setattr(
        PaperService,
        "get_paper_by_arxiv_id",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PaperNotFoundError("not indexed")
        ),
    )

    async def fail_indexing(*_args, **_kwargs):
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(papers, "_fetch_and_persist_arxiv_paper", fail_indexing)
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}

    with TestClient(app) as client:
        response = client.post("/api/v1/papers/index/2608.13517")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "database password leaked" in caplog.text


@pytest.mark.parametrize(
    ("path", "service", "method"),
    [
        (
            "/api/v1/tasks/404",
            "backend.services.task_service.TaskService",
            "get_task_by_id",
        ),
        (
            "/api/v1/methods/404",
            "backend.services.method_service.MethodService",
            "get_method_by_id",
        ),
        (
            "/api/v1/organizations/missing",
            "backend.services.organization_service.OrganizationService",
            "get_organization",
        ),
        (
            "/api/v1/repositories/404",
            "backend.services.repository_service.RepositoryService",
            "get_repository_by_id",
        ),
        (
            "/api/v1/project-pages/404",
            "backend.services.project_page_service.ProjectPageService",
            "get_project_page_by_id",
        ),
    ],
)
def test_migrated_taxonomy_lookups_keep_typed_not_found_contracts(
    monkeypatch, path, service, method
):
    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name),
        method,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CatalogNotFoundError("entity not found")
        ),
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "entity not found"}


def test_create_task_requires_catalog_mutator_before_service_is_called(monkeypatch):
    from backend.services.task_service import TaskService

    monkeypatch.setattr(
        TaskService,
        "create_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")),
    )
    with _catalog_client(monkeypatch) as client:
        response = client.post("/api/v1/tasks/", json={"name": "Protected task"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


@pytest.mark.parametrize(
    ("path", "service", "method", "payload"),
    [
        (
            "/api/v1/tasks/",
            "backend.services.task_service.TaskService",
            "get_tasks",
            Tasks(count=0, results=[]),
        ),
        (
            "/api/v1/methods/",
            "backend.services.method_service.MethodService",
            "get_methods",
            Methods(count=0, results=[]),
        ),
        (
            "/api/v1/organizations/",
            "backend.services.organization_service.OrganizationService",
            "get_organizations",
            Organizations(count=0, results=[]),
        ),
        (
            "/api/v1/repositories/",
            "backend.services.repository_service.RepositoryService",
            "get_repositories",
            Repositories(count=0, results=[]),
        ),
        (
            "/api/v1/project-pages/",
            "backend.services.project_page_service.ProjectPageService",
            "get_project_pages",
            ProjectPages(count=0, results=[]),
        ),
    ],
)
def test_migrated_taxonomy_lists_keep_success_payloads(
    monkeypatch, path, service, method, payload
):
    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name), method, lambda *_args, **_kwargs: payload
    )

    with _catalog_client(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.parametrize(
    ("path", "verb", "body"),
    [
        ("/api/v1/tasks/missing/keywords", "post", {"keywords": ["x"]}),
        ("/api/v1/tasks/missing/keywords", "put", {"keywords": ["x"]}),
        ("/api/v1/methods/missing/keywords", "post", {"keywords": ["x"]}),
        ("/api/v1/methods/missing/keywords", "put", {"keywords": ["x"]}),
        ("/api/v1/project-pages/", "post", {"url": "https://example.com"}),
        ("/api/v1/project-pages/1", "put", {"url": "https://example.com"}),
        ("/api/v1/project-pages/1", "delete", None),
    ],
)
def test_migrated_taxonomy_mutations_remain_authorized(monkeypatch, path, verb, body):
    with _catalog_client(monkeypatch) as client:
        response = (
            getattr(client, verb)(path, json=body)
            if body is not None
            else getattr(client, verb)(path)
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("path", "method", "body", "service", "operation", "error", "status"),
    [
        (
            "/api/v1/tasks/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.task_service.TaskService",
            "add_keywords",
            CatalogValidationError("invalid"),
            400,
        ),
        (
            "/api/v1/tasks/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.task_service.TaskService",
            "add_keywords",
            CatalogNotFoundError("missing"),
            404,
        ),
        (
            "/api/v1/tasks/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.task_service.TaskService",
            "add_keywords",
            CatalogConflictError("conflict"),
            409,
        ),
        (
            "/api/v1/methods/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.method_service.MethodService",
            "add_keywords",
            CatalogValidationError("invalid"),
            400,
        ),
        (
            "/api/v1/methods/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.method_service.MethodService",
            "add_keywords",
            CatalogNotFoundError("missing"),
            404,
        ),
        (
            "/api/v1/methods/missing/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.method_service.MethodService",
            "add_keywords",
            CatalogConflictError("conflict"),
            409,
        ),
        (
            "/api/v1/project-pages/",
            "post",
            {"url": "https://example.com"},
            "backend.services.project_page_service.ProjectPageService",
            "create_project_page",
            CatalogValidationError("invalid"),
            400,
        ),
        (
            "/api/v1/project-pages/404",
            "put",
            {"url": "https://example.com"},
            "backend.services.project_page_service.ProjectPageService",
            "update_project_page",
            CatalogNotFoundError("missing"),
            404,
        ),
        (
            "/api/v1/project-pages/",
            "post",
            {"url": "https://example.com"},
            "backend.services.project_page_service.ProjectPageService",
            "create_project_page",
            CatalogConflictError("conflict"),
            409,
        ),
    ],
)
def test_migrated_taxonomy_mutations_keep_typed_error_contracts(
    monkeypatch, path, method, body, service, operation, error, status
):
    from backend.database.connection import get_database_session
    from backend.main import create_app

    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name),
        operation,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    app.dependency_overrides[require_catalog_mutator] = lambda: {"sub": "test"}

    with TestClient(app) as client:
        response = getattr(client, method)(path, json=body)

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize(
    ("path", "verb", "body", "service", "operation", "result", "status"),
    [
        (
            "/api/v1/tasks/task/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.task_service.TaskService",
            "add_keywords",
            Task(id="1", name="Task"),
            200,
        ),
        (
            "/api/v1/tasks/task/keywords",
            "put",
            {"keywords": ["x"]},
            "backend.services.task_service.TaskService",
            "replace_keywords",
            Task(id="1", name="Task"),
            200,
        ),
        (
            "/api/v1/methods/method/keywords",
            "post",
            {"keywords": ["x"]},
            "backend.services.method_service.MethodService",
            "add_keywords",
            Method(id="1", name="Method"),
            200,
        ),
        (
            "/api/v1/methods/method/keywords",
            "put",
            {"keywords": ["x"]},
            "backend.services.method_service.MethodService",
            "replace_keywords",
            Method(id="1", name="Method"),
            200,
        ),
        (
            "/api/v1/project-pages/",
            "post",
            {"url": "https://example.com"},
            "backend.services.project_page_service.ProjectPageService",
            "create_project_page",
            ProjectPage(id="1", url="https://example.com"),
            201,
        ),
        (
            "/api/v1/project-pages/1",
            "put",
            {"url": "https://example.com"},
            "backend.services.project_page_service.ProjectPageService",
            "update_project_page",
            ProjectPage(id="1", url="https://example.com"),
            200,
        ),
        (
            "/api/v1/project-pages/1",
            "delete",
            None,
            "backend.services.project_page_service.ProjectPageService",
            "delete_project_page",
            None,
            204,
        ),
    ],
)
def test_migrated_taxonomy_mutations_keep_authorized_success_contracts(
    monkeypatch, path, verb, body, service, operation, result, status
):
    from backend.database.connection import get_database_session
    from backend.main import create_app

    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    monkeypatch.setattr(
        getattr(module, class_name), operation, lambda *_args, **_kwargs: result
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    app.dependency_overrides[require_catalog_mutator] = lambda: {"sub": "test"}
    app.dependency_overrides[require_fresh_catalog_mutator] = lambda: {"sub": "test"}

    with TestClient(app) as client:
        response = (
            getattr(client, verb)(path, json=body)
            if body is not None
            else getattr(client, verb)(path)
        )

    assert response.status_code == status
    if result is not None:
        assert response.json()["id"] == "1"
