"""Public projection and browser access must never widen private operations."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from backend.main import create_app
from backend.routers.public_api import PublicReadCorsMiddleware
from backend.services.public_api_schema import PUBLIC_ENDPOINTS, public_openapi


def test_public_schema_contains_only_selected_gets_and_resolves_all_references():
    app = create_app()
    full = app.openapi()
    public = public_openapi(app)
    assert set(public["paths"]) == set(PUBLIC_ENDPOINTS)
    assert all(set(item) == {"get"} for item in public["paths"].values())
    assert "Admin" not in str(public["components"])
    assert app.openapi() == full

    def check(value):
        if isinstance(value, dict):
            if "$ref" in value:
                target = public
                for part in value["$ref"].removeprefix("#/").split("/"):
                    target = target[part]
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(public)
    for path, item in public["paths"].items():
        operation = item["get"]
        assert not full["paths"][path]["get"].get("security")
        assert operation["security"] == []
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]
        params = {p["name"] for p in operation.get("parameters", [])}
        assert set(operation["x-example-parameters"]) <= params
        assert "429" in operation["responses"]
    search = public["paths"]["/api/v1/papers/search"]["get"]
    mode = next(p for p in search["parameters"] if p["name"] == "mode")
    assert mode["schema"] == {"type": "string", "enum": ["keyword"]}
    assert mode["required"]
    full_mode = next(
        p
        for p in full["paths"]["/api/v1/papers/search"]["get"]["parameters"]
        if p["name"] == "mode"
    )
    assert full_mode != mode


def cors_client():
    app = FastAPI()

    @app.get("/api/v1/papers/stats")
    def internal():
        return {"internal": True}

    @app.get("/api/v1/papers/{paper_id}")
    def detail(paper_id: str):
        if paper_id == "missing":
            raise HTTPException(404, "Paper not found")
        return {"id": paper_id}

    @app.post("/api/v1/papers/{paper_id}")
    def write(paper_id: str):
        raise HTTPException(401)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://paperswithcode.co"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_middleware(
        PublicReadCorsMiddleware, allowed_origins=["https://paperswithcode.co"]
    )
    return TestClient(app)


def test_public_gets_and_errors_allow_anonymous_browser_access():
    client = cors_client()
    for id_, code in [("123", 200), ("missing", 404)]:
        response = client.get(
            f"/api/v1/papers/{id_}", headers={"Origin": "https://research.example"}
        )
        assert response.status_code == code
        assert response.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" not in response.headers


def test_route_matching_keeps_reserved_routes_and_writes_private():
    client = cors_client()
    headers = {"Origin": "https://research.example"}
    for response in [
        client.get("/api/v1/papers/stats", headers=headers),
        client.post("/api/v1/papers/123", headers=headers),
    ]:
        assert "access-control-allow-origin" not in response.headers
    for method, extra in [("POST", "content-type"), ("GET", "authorization")]:
        response = client.options(
            "/api/v1/papers/123",
            headers={
                **headers,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": extra,
            },
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


def test_public_preflight_allows_get_but_not_credentials():
    response = cors_client().options(
        "/api/v1/papers/123",
        headers={
            "Origin": "https://research.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-methods"] == "GET"
    assert "access-control-allow-credentials" not in response.headers


def test_schema_endpoint_is_public_and_cacheable():
    response = TestClient(create_app()).get(
        "/api/v1/openapi.json", headers={"Origin": "https://research.example"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "max-age=300" in response.headers["cache-control"]
    assert set(response.json()["paths"]) == set(PUBLIC_ENDPOINTS)


def test_existing_credentialed_origins_keep_their_get_and_preflight_contract():
    client = cors_client()
    headers = {"Origin": "https://paperswithcode.co"}
    for response in [
        client.get("/api/v1/papers/123", headers=headers),
        client.options(
            "/api/v1/papers/123",
            headers={
                **headers,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        ),
    ]:
        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"]
            == "https://paperswithcode.co"
        )
        assert response.headers["access-control-allow-credentials"] == "true"


def test_slashless_lists_have_public_cors_on_aliases_redirects_and_preflights():
    app = FastAPI()

    @app.get("/api/v1/papers")
    @app.get("/api/v1/papers/")
    @app.get("/api/v1/tasks/")
    @app.get("/api/v1/datasets/")
    @app.get("/api/v1/evaluations/")
    def listing():
        return {"results": []}

    app.add_middleware(PublicReadCorsMiddleware)
    client = TestClient(app)
    for kind in ("papers", "tasks", "datasets", "evaluations"):
        path = f"/api/v1/{kind}"
        headers = {"Origin": "https://research.example"}
        response = client.get(path, headers=headers, follow_redirects=False)
        assert response.status_code == (200 if kind == "papers" else 307)
        assert response.headers["access-control-allow-origin"] == "*"
        assert client.get(path, headers=headers).status_code == 200
        preflight = client.options(
            path, headers={**headers, "Access-Control-Request-Method": "GET"}
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "*"


def test_private_method_match_prevents_public_slash_redirect():
    app = FastAPI()

    @app.post("/api/v1/tasks")
    def private_write():
        return {}

    @app.get("/api/v1/tasks/")
    def public_list():
        return {}

    app.add_middleware(PublicReadCorsMiddleware)
    response = TestClient(app).get(
        "/api/v1/tasks", headers={"Origin": "https://research.example"}
    )
    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


def test_distinct_private_get_is_not_treated_as_a_public_alias():
    app = FastAPI()

    @app.get("/api/v1/tasks")
    def private_list():
        return {"private": True}

    @app.get("/api/v1/tasks/")
    def public_list():
        return {"results": []}

    app.add_middleware(PublicReadCorsMiddleware)
    response = TestClient(app).get(
        "/api/v1/tasks", headers={"Origin": "https://research.example"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_deployed_admission_rejections_are_readable_by_browser_clients(monkeypatch):
    from backend import main
    from backend.config import Settings
    from backend.services.catalog_admission import CatalogAdmissionMiddleware

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(environment="production", release_id="test-production"),
    )
    app = main.create_app()
    for middleware in app.user_middleware:
        if middleware.cls is CatalogAdmissionMiddleware:
            middleware.kwargs["limit"] = 0
    client = TestClient(app)
    for origin in ("https://research.example", "https://paperswithcode.co"):
        response = client.get("/api/v1/papers/", headers={"Origin": origin})
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.headers["access-control-expose-headers"] == "Retry-After"
        if origin == "https://paperswithcode.co":
            assert response.headers["access-control-allow-origin"] == origin
            assert response.headers["access-control-allow-credentials"] == "true"
        else:
            assert response.headers["access-control-allow-origin"] == "*"


def test_cached_public_responses_vary_for_all_origin_variants():
    client = cors_client()
    for origin in (None, "https://research.example", "https://paperswithcode.co"):
        headers = {"Origin": origin} if origin else {}
        response = client.get("/api/v1/papers/123", headers=headers)
        assert "origin" in {
            part.strip().lower() for part in response.headers["vary"].split(",")
        }
