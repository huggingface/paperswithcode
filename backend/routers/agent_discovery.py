"""Machine-readable discovery metadata for the public API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from backend.services.content_negotiation_service import prefers_markdown
from backend.services.public_api_docs_service import (
    markdown_to_html,
    public_api_markdown,
    public_api_shell,
)
from backend.services.public_api_schema import cached_public_openapi
from backend.services.spa_shell_service import load_index_html

router = APIRouter()

_ORIGIN = "https://paperswithcode.co"
_CATALOG_URL = f"{_ORIGIN}/.well-known/api-catalog"
_OIDC_CONFIGURATION_URL = f"{_ORIGIN}/.well-known/openid-configuration"
_PROFILE = "https://www.rfc-editor.org/info/rfc9727"
_MEDIA_TYPE = f'application/linkset+json; profile="{_PROFILE}"'
_DISCOVERY_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
}
_CATALOG_HEADERS = {
    **_DISCOVERY_CACHE_HEADERS,
    "Link": f'<{_CATALOG_URL}>; rel="api-catalog"',
}


_DOCS_HEADERS = {
    "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
    "Link": (
        f'<{_ORIGIN}/docs/api>; rel="canonical", '
        f'<{_ORIGIN}/docs/api.md>; rel="alternate"; type="text/markdown"'
    ),
    "Vary": "Accept",
}


def _markdown_documentation(request: Request) -> Response:
    return Response(
        public_api_markdown(cached_public_openapi(request.app)),
        media_type="text/markdown; charset=utf-8",
        headers=_DOCS_HEADERS,
    )


@router.api_route("/docs/api", methods=["GET", "HEAD"], include_in_schema=False)
def api_documentation(request: Request) -> Response:
    """Serve the API docs page with its content rendered for non-JS readers."""
    if prefers_markdown(request.headers.get("accept")):
        return _markdown_documentation(request)
    shell = load_index_html()
    schema = cached_public_openapi(request.app)
    if shell is None:
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            "<title>Papers with Code API documentation</title></head><body><main>"
            f"{markdown_to_html(public_api_markdown(schema))}</main></body></html>",
            headers=_DOCS_HEADERS,
        )
    return HTMLResponse(public_api_shell(shell, schema), headers=_DOCS_HEADERS)


@router.api_route("/docs/api.md", methods=["GET", "HEAD"], include_in_schema=False)
def api_documentation_markdown(request: Request) -> Response:
    """Serve the API docs as one Markdown document for agents and scripts."""
    return _markdown_documentation(request)


@router.api_route("/api", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/", methods=["GET", "HEAD"], include_in_schema=False)
def api_root() -> RedirectResponse:
    return RedirectResponse("/docs/api", status_code=308)


@router.api_route(
    "/.well-known/api-catalog",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def api_catalog() -> JSONResponse:
    """Return the RFC 9727 catalog for the public Papers With Code API."""

    return JSONResponse(
        {
            "linkset": [
                {
                    "anchor": f"{_ORIGIN}/api/v1/papers/",
                    "service-desc": [
                        {
                            "href": f"{_ORIGIN}/api/v1/openapi.json",
                            "type": "application/json",
                        }
                    ],
                    "service-doc": [
                        {
                            "href": f"{_ORIGIN}/docs/api",
                            "type": "text/html",
                        }
                    ],
                    "status": [
                        {
                            "href": f"{_ORIGIN}/health",
                            "type": "application/json",
                        }
                    ],
                }
            ]
        },
        media_type=_MEDIA_TYPE,
        headers=_CATALOG_HEADERS,
    )


@router.api_route(
    "/.well-known/openid-configuration",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def openid_configuration() -> JSONResponse:
    """Describe the OIDC provider used by Papers With Code authentication."""

    return JSONResponse(
        {
            "issuer": _ORIGIN,
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
            "service_documentation": f"{_ORIGIN}/docs/api",
        },
        headers={
            **_DISCOVERY_CACHE_HEADERS,
            "Access-Control-Allow-Origin": "*",
            "Link": f'<{_OIDC_CONFIGURATION_URL}>; rel="openid-configuration"',
        },
    )
