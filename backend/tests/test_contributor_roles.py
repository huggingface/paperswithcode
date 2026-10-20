from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.config import Settings
from backend.routers import auth
from backend.utils import auth as auth_utils


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": "https",
            "headers": [],
        }
    )


def request_with_headers(*headers: tuple[bytes, bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "scheme": "https",
            "headers": list(headers),
        }
    )


def settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "catalog_mutations_enabled": True,
        "contributor_direct_edits_enabled": True,
        "admin_hf_subjects": " admin-sub , shared ",
        "contributor_hf_subjects": " contributor-sub, shared ",
        "admin_hf_usernames": "legacy-admin",
    }
    values.update(overrides)
    return Settings(**values)


def configure(monkeypatch, current: Settings, payload: dict | None) -> None:
    monkeypatch.setattr(auth_utils, "get_settings", lambda: current)
    monkeypatch.setattr(auth, "get_settings", lambda: current)
    monkeypatch.setattr(auth, "decode_request_session", lambda _request: payload)


def test_subject_lists_are_normalized_and_admin_precedes_contributor(monkeypatch):
    current = settings()
    monkeypatch.setattr(auth_utils, "get_settings", lambda: current)
    assert current.admin_hf_subject_set == {"admin-sub", "shared"}
    assert current.contributor_hf_subject_set == {"contributor-sub", "shared"}
    assert auth_utils.role_for_hf_subject("shared") == "admin"


def test_malformed_subject_configuration_fails_closed():
    current = settings(admin_hf_subjects="valid-sub,not allowed")
    with pytest.raises(ValueError, match="Malformed"):
        _ = current.admin_hf_subject_set


@pytest.mark.parametrize(
    ("subject", "username", "expected"),
    [
        ("admin-sub", "renamed", "admin"),
        ("contributor-sub", "renamed", "contributor"),
        ("unlisted", "legacy-admin", None),
    ],
)
def test_role_uses_immutable_subject_when_subject_configured(
    monkeypatch, subject, username, expected
):
    current = settings()
    monkeypatch.setattr(auth_utils, "get_settings", lambda: current)
    assert auth_utils.role_for_hf_subject(subject, username=username) == expected


def test_legacy_username_fallback_is_admin_only(monkeypatch):
    current = settings(admin_hf_subjects="", contributor_hf_subjects="")
    monkeypatch.setattr(auth_utils, "get_settings", lambda: current)
    assert (
        auth_utils.role_for_hf_subject("anything", username="Legacy-Admin") == "admin"
    )
    assert auth_utils.role_for_hf_subject("anything", username="abidlabs") is None


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        (None, 401),
        ({"sub": "unlisted", "username": "person"}, 403),
        (
            {
                "sub": "operator:pi-qualification:test-run:0",
                "username": "operator:pi-qualification:test-run:0",
                "chat_qualification_owner": "operator:pi-qualification:test-run:0",
            },
            204,
        ),
        ({"sub": "contributor-sub", "username": "person"}, 204),
        ({"sub": "admin-sub", "username": "person"}, 204),
    ],
)
def test_staging_check_statuses(monkeypatch, payload, status_code):
    configure(monkeypatch, settings(environment="staging"), payload)
    if status_code == 204:
        assert auth.staging_check(request()).status_code == 204
    else:
        with pytest.raises(HTTPException) as error:
            auth.staging_check(request())
        assert error.value.status_code == status_code


def test_admin_check_still_rejects_contributor(monkeypatch):
    configure(
        monkeypatch,
        settings(),
        {"sub": "contributor-sub", "username": "person"},
    )
    with pytest.raises(HTTPException) as error:
        auth.admin_check(request())
    assert error.value.status_code == 403


def test_me_reports_contributor_capabilities(monkeypatch):
    configure(
        monkeypatch,
        settings(),
        {"sub": "contributor-sub", "username": "renamed"},
    )
    response = auth.me(request())
    assert response.hf_subject == "contributor-sub"
    assert response.role == "contributor"
    assert response.is_admin is False
    assert response.can_contribute is True
    assert response.can_directly_edit_catalog is True


def test_me_reports_subject_for_unlisted_authenticated_user(monkeypatch):
    configure(
        monkeypatch,
        settings(environment="staging"),
        {"sub": "unlisted-subject", "username": "person"},
    )
    response = auth.me(request())
    assert response.hf_subject == "unlisted-subject"
    assert response.role is None
    assert response.can_contribute is False


def test_staging_me_never_advertises_direct_edits(monkeypatch):
    configure(
        monkeypatch,
        settings(environment="staging"),
        {"sub": "contributor-sub", "username": "person"},
    )
    assert auth.me(request()).can_directly_edit_catalog is False


def test_allowlist_revocation_applies_to_existing_cookie(monkeypatch):
    payload = {"sub": "contributor-sub", "username": "person"}
    current = settings()
    configure(monkeypatch, current, payload)
    assert auth.staging_check(request()).status_code == 204
    current.contributor_hf_subjects = ""
    with pytest.raises(HTTPException) as error:
        auth.staging_check(request())
    assert error.value.status_code == 403


def test_stale_session_blocks_contributor_delete_only(monkeypatch):
    old_iat = datetime.now(timezone.utc).timestamp() - 901
    configure(
        monkeypatch,
        settings(),
        {
            "sub": "contributor-sub",
            "username": "person",
            "iat": old_iat,
        },
    )
    assert auth_utils.require_contributor(request())["role"] == "contributor"
    with pytest.raises(HTTPException) as error:
        auth_utils.require_fresh_contributor(request())
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "fresh_auth_required"


def test_direct_edits_fail_closed_when_flag_disabled(monkeypatch):
    configure(
        monkeypatch,
        settings(contributor_direct_edits_enabled=False),
        {"sub": "contributor-sub", "username": "person"},
    )
    with pytest.raises(HTTPException) as error:
        auth_utils.require_contributor(request())
    assert error.value.status_code == 403


def test_existing_admin_api_token_evaluation_workflow_is_preserved(monkeypatch):
    current = settings(admin_api_token="secret-token")
    configure(monkeypatch, current, None)
    result = auth_utils.require_catalog_mutator(
        request_with_headers(), admin_token="secret-token"
    )
    assert result == {
        "source": "header",
        "hf_subject": "admin-api-token",
        "username": None,
        "role": "admin",
    }


@pytest.mark.parametrize(
    "dependency",
    [
        auth_utils.require_admin,
        auth_utils.require_hf_admin,
    ],
)
def test_contributor_is_rejected_by_admin_only_dependencies(monkeypatch, dependency):
    configure(
        monkeypatch,
        settings(),
        {"sub": "contributor-sub", "username": "person"},
    )
    with pytest.raises(HTTPException):
        if dependency is auth_utils.require_admin:
            dependency(request(), admin_token=None)
        else:
            dependency(request())


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def collect(dependant) -> None:
        for child in dependant.dependencies:
            names.add(getattr(child.call, "__name__", type(child.call).__name__))
            collect(child)

    collect(route.dependant)
    return names


def test_all_catalog_write_routes_receive_catalog_mutator_dependency():
    from backend.main import app

    routes = {
        (method, route.path): _dependency_names(route)
        for route in app.routes
        if hasattr(route, "methods") and hasattr(route, "dependant")
        for method in route.methods
    }
    approved_paper_paths = {
        "/api/v1/papers/{paper_id}/tasks",
        "/api/v1/papers/{paper_id}/methods",
        "/api/v1/papers/{paper_id}/organizations",
        "/api/v1/papers/{paper_id}/repositories",
        "/api/v1/papers/{paper_id}/project-pages",
        "/api/v1/papers/{paper_id}/hf-artifacts",
        "/api/v1/papers/{paper_id}/source-url",
    }
    for path in approved_paper_paths:
        assert "catalog_mutation_context" in routes[("PUT", path)]
        assert "require_paper_mutator" in routes[("PUT", path)]

    catalog_routes = {
        ("POST", "/api/v1/project-pages/"): "require_catalog_mutator",
        ("PUT", "/api/v1/project-pages/{page_id}"): "require_catalog_mutator",
        ("DELETE", "/api/v1/project-pages/{page_id}"): "require_fresh_catalog_mutator",
        ("POST", "/api/v1/datasets/"): "require_catalog_mutator",
        ("PUT", "/api/v1/datasets/{dataset_id}"): "require_catalog_mutator",
        (
            "POST",
            "/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics",
        ): "require_catalog_mutator",
        (
            "PUT",
            "/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics",
        ): "require_fresh_catalog_mutator",
        (
            "DELETE",
            "/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics/{metric_name}",
        ): "require_fresh_catalog_mutator",
        ("POST", "/api/v1/tasks/"): "require_catalog_mutator",
        ("POST", "/api/v1/tasks/{task_id}/keywords"): "require_catalog_mutator",
        ("PUT", "/api/v1/tasks/{task_id}/keywords"): "require_fresh_catalog_mutator",
        ("DELETE", "/api/v1/tasks/{task_id}/keywords"): "require_fresh_catalog_mutator",
        ("POST", "/api/v1/methods/{method_id}/keywords"): "require_catalog_mutator",
        (
            "PUT",
            "/api/v1/methods/{method_id}/keywords",
        ): "require_fresh_catalog_mutator",
        (
            "DELETE",
            "/api/v1/methods/{method_id}/keywords",
        ): "require_fresh_catalog_mutator",
    }
    for key, dependency in catalog_routes.items():
        assert dependency in routes[key]

    for method, path in {
        ("POST", "/api/v1/evaluations/batch"),
        ("POST", "/api/v1/evaluations/"),
        ("PUT", "/api/v1/evaluations/{evaluation_id}"),
        ("DELETE", "/api/v1/evaluations/{evaluation_id}"),
    }:
        assert "evaluation_mutation_context" in routes[(method, path)]
        assert "require_paper_mutator" in routes[(method, path)]


def test_representative_excluded_boundaries_remain_admin_only():
    from backend.main import app

    routes = {
        (method, route.path): _dependency_names(route)
        for route in app.routes
        if hasattr(route, "methods") and hasattr(route, "dependant")
        for method in route.methods
    }
    expected = {
        ("POST", "/api/v1/admin/paper-edits/{edit_id}/approve"): "require_hf_admin",
        ("POST", "/api/v1/evaluations/recalculate-ranks"): "require_admin",
        ("POST", "/api/v1/admin/codex-add-evals/jobs"): "require_hf_admin",
        ("POST", "/api/v1/admin/codex-enrich-paper/jobs"): "require_hf_admin",
        ("POST", "/api/v1/papers/index/{arxiv_id}"): "require_admin",
        ("POST", "/api/v1/papers/update-citations"): "require_admin",
        ("POST", "/api/v1/papers/external"): "require_admin",
        ("POST", "/api/v1/papers/external/from-url"): "require_admin",
    }
    for key, dependency in expected.items():
        assert dependency in routes[key]

    for path in (
        "/api/thumbnails/generate/{paper_id}",
        "/api/thumbnails/cache/cleanup",
    ):
        assert "require_admin" in routes[("POST", path)]
    assert "require_admin" in routes[("GET", "/api/thumbnails/cache/stats")]


def test_chat_spend_dashboard_route_is_admin_only():
    from backend.routers.chat import router

    route = next(
        route for route in router.routes if route.path == "/chat/admin/sandbox-spend"
    )
    assert "require_admin" in _dependency_names(route)


def test_public_paper_editor_cannot_mutate_shared_catalog(monkeypatch):
    configure(monkeypatch, settings(), {"sub": "public-user", "username": "alice"})
    assert auth_utils.require_paper_mutator(request(), None)["role"] == "contributor"
    with pytest.raises(HTTPException) as error:
        auth_utils.require_catalog_mutator(request(), None)
    assert error.value.status_code == 401


@pytest.mark.parametrize("subject", ["contributor-sub", "admin-sub"])
def test_configured_catalog_roles_still_work(monkeypatch, subject):
    configure(monkeypatch, settings(), {"sub": subject, "username": "alice"})
    assert auth_utils.require_catalog_mutator(request(), None)["hf_subject"] == subject


def test_paper_bearer_never_falls_back_to_catalog_admin(monkeypatch):
    configure(
        monkeypatch,
        settings(admin_api_token="admin-secret"),
        {"sub": "admin-sub", "username": "admin"},
    )
    with pytest.raises(HTTPException) as error:
        auth_utils.require_catalog_mutator(
            request_with_headers((b"authorization", b"Bearer paper-token")),
            "admin-secret",
        )
    assert error.value.status_code == 403
