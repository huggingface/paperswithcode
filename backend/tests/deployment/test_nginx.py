"""nginx template validation and environment isolation."""

from __future__ import annotations

from pathlib import Path


from deploy.nginx_validate import (
    CURATION_CALLBACK_LOCATION,
    SEO_LOCATIONS,
    SHARE_API_LOCATION,
    SHARE_PAGE_LOCATION,
    location_block,
)
from deploy.nginx_validate import (
    validate as validate_nginx,
)


def test_nginx_cross_environment_references_are_rejected():
    failures = validate_nginx(
        "root /srv/paperswithcode/environments/production/current/frontend-dist;"
        " upstream pwc_staging_backend { server 127.0.0.1:8001; } location / { }",
        "root /srv/paperswithcode/environments/staging/current/frontend-dist;"
        " location = /_staging_access_check { internal; "
        "proxy_pass http://pwc_staging_backend/api/v1/auth/staging-check; } "
        "location / { }"
        " server_name chat-gateway-staging.paperswithcode.co;"
        " client_max_body_size 512k;"
        " location = /api/internal/chat-gateway/catalog { }"
        " location = /api/internal/chat-gateway/session-store { }"
        " location = /api/internal/chat-gateway/web-fetch { }"
        " location = /api/internal/chat-gateway/v1/messages { }",
    )
    assert "production references staging backend" in failures


def test_staging_nginx_requires_bearer_authenticated_curation_callback_route():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []

    failures = validate_nginx(
        production,
        staging.replace(CURATION_CALLBACK_LOCATION, "location /missing-callback"),
    )
    assert "staging job-token callback route is missing" in failures


def test_staging_nginx_requires_an_unbuffered_chat_stream_route():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    for directive in (
        "proxy_buffering off;",
        "proxy_cache off;",
        "gzip off;",
        "proxy_read_timeout 190s;",
    ):
        before, stream = staging.split("location = /api/v1/chat/stream", 1)
        failures = validate_nginx(
            production,
            before
            + "location = /api/v1/chat/stream"
            + stream.replace(directive, "", 1),
        )
        assert f"staging chat stream route misses: {directive}" in failures


def test_nginx_requires_isolated_production_and_staging_gateways():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    failures = validate_nginx(
        production.replace(
            "server_name chat-gateway.paperswithcode.co;",
            "server_name missing-production-gateway.paperswithcode.co;",
        ),
        staging,
    )
    assert "production chat gateway hostname is missing" in failures

    failures = validate_nginx(
        production,
        staging.replace(
            "location = /api/internal/chat-gateway/catalog {\n"
            "        limit_except POST { deny all; }\n"
            "        proxy_pass http://pwc_staging_backend;",
            "location = /api/internal/chat-gateway/catalog {\n"
            "        limit_except POST { deny all; }\n"
            "        proxy_pass http://missing_staging_backend;",
        ),
    )
    assert "staging chat gateway catalog misses pwc_staging_backend" in failures


def test_nginx_requires_backend_routes_for_seo_surfaces():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    failures = validate_nginx(
        production.replace(SEO_LOCATIONS[0], "location = /missing-sitemap"),
        staging,
    )
    assert "production SEO route is missing" in " ".join(failures)


def test_nginx_public_page_proxies_preserve_accept_and_origin_headers():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    assert "proxy_set_header Accept" not in production
    assert "proxy_set_header Accept" not in staging
    assert "proxy_hide_header Content-Type" not in production + staging
    assert "proxy_hide_header Vary" not in production + staging
    assert "proxy_hide_header Link" not in production + staging
    assert "proxy_hide_header Cache-Control" not in production + staging


def test_spa_shell_never_reveals_initial_documents():
    repository = Path(__file__).resolve().parents[3]
    shell = (repository / "frontend/index.html").read_text()

    hiding_rule = (
        "html [data-pwc-initial-document], "
        "html .initial-discovery-footer { display: none !important; }"
    )
    assert hiding_rule in shell
    assert shell.index(hiding_rule) < shell.index("<script>")
    assert shell.index(hiding_rule) < shell.index('<link rel="stylesheet"')
    assert "<noscript>" not in shell
    assert '<footer hidden id="initial-discovery-footer"' in shell
    assert 'data-pwc-initial-document="paper"' not in shell
    assert '<div id="root"></div>' in shell


def test_nginx_share_capability_bypasses_only_narrow_public_get_surfaces():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    for config in (production, staging):
        page = location_block(config, SHARE_PAGE_LOCATION)
        api = location_block(config, SHARE_API_LOCATION)
        assert "auth_request" not in page + api
        assert "limit_except GET" in page
        assert "limit_except GET" in api
        assert "/artifacts/" in SHARE_API_LOCATION
        assert "download/(png|pdf)" in SHARE_API_LOCATION
        assert 'X-Robots-Tag "noindex, nofollow" always' in page
        assert 'Cache-Control "no-store"' in page

    assets = staging.split("location ^~ /assets/", 1)[1].split("}", 1)[0]
    auth_me = staging.split("location = /api/v1/auth/me", 1)[1].split("}", 1)[0]
    owner_api = staging.split("location /api/", 1)[1].split("}", 1)[0]
    catch_all = staging.split("location / {", 1)[1].split("}", 1)[0]
    assert "auth_request" not in assets + auth_me
    assert "auth_request /_staging_access_check;" in owner_api
    assert "auth_request /_staging_access_check;" in catch_all


def test_staging_access_request_surface_is_public_and_narrow():
    repository = Path(__file__).resolve().parents[3]
    production = (repository / "deploy/nginx/paperswithcode.co.conf").read_text()
    staging = (repository / "deploy/nginx/staging.paperswithcode.co.conf").read_text()

    assert validate_nginx(production, staging) == []
    page = location_block(staging, "location = /request-access")
    api = location_block(staging, "location = /api/v1/staging-access-request")
    forbidden = location_block(staging, "location @staging_forbidden")

    assert "auth_request" not in page + api
    assert "try_files /index.html =404;" in page
    assert 'X-Robots-Tag "noindex, nofollow" always' in page
    assert "limit_except POST" in api
    assert "proxy_pass http://pwc_staging_backend;" in api
    assert "return 302 /request-access;" in forbidden
