from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.routers.public_api import PublicReadCorsMiddleware
from backend.utils.cors import install_cors

SPACE_REGEX = r"^https://[a-z0-9-]+(\.static)?\.hf\.space$"


def _client(**settings_kwargs) -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    install_cors(app, Settings(environment="production", **settings_kwargs))
    return TestClient(app)


def test_exact_origin_keeps_credentials():
    client = _client(extra_allowed_origin_regex=SPACE_REGEX)
    response = client.get(
        "/api/v1/ping", headers={"Origin": "https://paperswithcode.co"}
    )
    assert (
        response.headers["access-control-allow-origin"] == "https://paperswithcode.co"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


def test_regex_origin_reads_without_credentials():
    client = _client(extra_allowed_origin_regex=SPACE_REGEX)
    origin = "https://anyone-anything.hf.space"
    response = client.get("/api/v1/ping", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers

    preflight = client.options(
        "/api/v1/ping",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in preflight.headers


def test_listed_extra_origin_keeps_credentials():
    origin = "https://nielsr-paperswithcode.hf.space"
    client = _client(
        extra_allowed_origins=origin, extra_allowed_origin_regex=SPACE_REGEX
    )
    response = client.get("/api/v1/ping", headers={"Origin": origin})
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_gets_no_cors():
    client = _client(extra_allowed_origin_regex=SPACE_REGEX)
    response = client.get("/api/v1/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_public_catalog_layer_keeps_regex_origins_anonymous():
    settings = Settings(
        environment="production", extra_allowed_origin_regex=SPACE_REGEX
    )
    app = FastAPI()

    @app.get("/api/v1/papers/{paper_id}")
    def detail(paper_id: str):
        return {"id": paper_id}

    install_cors(app, settings)
    app.add_middleware(
        PublicReadCorsMiddleware, allowed_origins=settings.cors_allowed_origins
    )
    client = TestClient(app)

    space = client.get(
        "/api/v1/papers/1", headers={"Origin": "https://anyone-anything.hf.space"}
    )
    assert space.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in space.headers

    site = client.get(
        "/api/v1/papers/1", headers={"Origin": "https://paperswithcode.co"}
    )
    assert site.headers["access-control-allow-origin"] == "https://paperswithcode.co"
    assert site.headers["access-control-allow-credentials"] == "true"
