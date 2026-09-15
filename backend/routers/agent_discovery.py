"""Machine-readable discovery metadata for the public API."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

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


@router.api_route("/docs/api", methods=["GET", "HEAD"], include_in_schema=False)
def api_documentation() -> HTMLResponse:
    """Return a compact human-readable entry point for the public API."""

    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Papers With Code API</title></head>
<body>
<main>
<h1>Papers With Code API</h1>
<p>The public catalog API is available under <code>/api/v1/</code>.</p>
<ul>
<li><a href="/api/v1/openapi.json">Public beta OpenAPI description</a></li>
<li><a href="/openapi.json">Full application OpenAPI description</a></li>
<li><a href="/.well-known/api-catalog">API catalog</a></li>
<li><a href="/.well-known/openid-configuration">OIDC discovery</a></li>
<li><a href="/health">Service health</a></li>
</ul>
<p>Most catalog read endpoints require no authentication. User-specific and
administrative operations declare their requirements in the OpenAPI description.
Interactive identity is delegated to Hugging Face using OpenID Connect.</p>
</main>
</body>
</html>
""",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
