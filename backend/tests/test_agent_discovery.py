from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import agent_discovery


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(agent_discovery.router)
    return TestClient(app)


def test_api_catalog_is_an_rfc_9727_linkset():
    with _client() as client:
        response = client.get("/.well-known/api-catalog")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"'
    )
    assert response.headers["link"] == (
        '<https://paperswithcode.co/.well-known/api-catalog>; rel="api-catalog"'
    )
    assert response.headers["cache-control"] == (
        "public, max-age=3600, stale-while-revalidate=86400"
    )
    assert response.json() == {
        "linkset": [
            {
                "anchor": "https://paperswithcode.co/api/v1/papers/",
                "service-desc": [
                    {
                        "href": "https://paperswithcode.co/api/v1/openapi.json",
                        "type": "application/json",
                    }
                ],
                "service-doc": [
                    {
                        "href": "https://paperswithcode.co/docs/api",
                        "type": "text/html",
                    }
                ],
                "status": [
                    {
                        "href": "https://paperswithcode.co/health",
                        "type": "application/json",
                    }
                ],
            }
        ]
    }


def test_api_catalog_supports_head_discovery():
    with _client() as client:
        response = client.head("/.well-known/api-catalog")

    assert response.status_code == 200
    assert response.content == b""
    assert 'rel="api-catalog"' in response.headers["link"]


def test_openid_configuration_describes_delegated_hf_oidc():
    with _client() as client:
        response = client.get("/.well-known/openid-configuration")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == (
        "public, max-age=3600, stale-while-revalidate=86400"
    )
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.json() == {
        "issuer": "https://paperswithcode.co",
        "authorization_endpoint": "https://huggingface.co/oauth/authorize",
        "token_endpoint": "https://huggingface.co/oauth/token",
        "userinfo_endpoint": "https://huggingface.co/oauth/userinfo",
        "jwks_uri": "https://huggingface.co/oauth/jwks",
        "scopes_supported": ["openid", "profile", "inference-api"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256"],
        "service_documentation": "https://paperswithcode.co/docs/api",
    }


def test_openid_configuration_supports_head_discovery():
    with _client() as client:
        response = client.head("/.well-known/openid-configuration")

    assert response.status_code == 200
    assert response.content == b""
    assert 'rel="openid-configuration"' in response.headers["link"]


def test_api_documentation_is_readable_without_javascript():
    from backend.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/docs/api")
        markdown = client.get("/docs/api.md")
        negotiated = client.get("/docs/api", headers={"Accept": "text/markdown"})
        root = client.get("/api/", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h2>Traffic limits</h2>" in response.text
    assert "/api/v1/research/papers/{paper_id}/read" in response.text
    assert 'href="https://paperswithcode.co/api/v1/openapi.json"' in response.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert markdown.text.startswith("# Papers with Code API")
    assert "## Endpoints" in markdown.text
    assert "### Get papers with pagination and filtering" in markdown.text
    assert negotiated.text == markdown.text
    assert root.status_code == 308
    assert root.headers["location"] == "/docs/api"
