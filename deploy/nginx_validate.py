#!/usr/bin/env python3
"""Static cross-environment safety checks for checked-in nginx templates."""

from __future__ import annotations

import argparse
from pathlib import Path

CURATION_CALLBACK_LOCATION = (
    'location ~ "^/api/v1/admin/codex-curation/jobs/'
    "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    '(context|taxonomy|leaderboards|apply|complete)$"'
)
SEO_LOCATIONS = (
    "location = /robots.txt",
    "location = /sitemap.xml",
    "location ^~ /sitemaps/",
    "location = /papers/recent",
    "location = /papers/archive",
    r'location ~ "^/papers/archive/[0-9]{4}(/[0-9]{2})?$"',
    "location = / {",
    r'location ~ "^/(tasks|task|methods|benchmark|conferences|authors|organizations)/[^/]+(/[^/]+)?$"',
)
SHARE_PAGE_LOCATION = (
    r'location ~ "^/share/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{12}$"'
)
SHARE_API_LOCATION = (
    r'location ~ "^/api/v1/chat/shares/[0-9a-f]{8}-[0-9a-f]{4}-'
    r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(/artifacts/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r'[0-9a-f]{12}/(preview|download/(png|pdf)))?$"'
)
CHAT_STREAM_LOCATION = "location = /api/v1/chat/stream"


def _validate_seo_routes(config: str, backend: str, environment: str) -> list[str]:
    failures: list[str] = []
    catch_all = config.find("location / {")
    for location in SEO_LOCATIONS:
        index = config.find(location)
        if index < 0:
            failures.append(f"{environment} SEO route is missing: {location}")
            continue
        if catch_all >= 0 and index > catch_all:
            failures.append(
                f"{environment} SEO route follows the SPA catch-all: {location}"
            )
        line_end = config.find("\n", index)
        block_end = config.find("}", line_end)
        block = config[index : block_end + 1]
        if f"proxy_pass http://{backend};" not in block:
            failures.append(f"{environment} SEO route misses {backend}: {location}")
        if "try_files" in block or "index.html" in block:
            failures.append(
                f"{environment} SEO route falls through to SPA HTML: {location}"
            )
    return failures


def location_block(config: str, location: str) -> str:
    """Return a complete nginx location block, including nested limit blocks."""

    start = config.find(location)
    if start < 0:
        return ""
    opening = config.find("{", start + len(location))
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(config)):
        if config[index] == "{":
            depth += 1
        elif config[index] == "}":
            depth -= 1
            if depth == 0:
                return config[start : index + 1]
    return ""


def validate(production: str, staging: str) -> list[str]:
    failures: list[str] = []
    if (
        "pwc_staging_backend" in production
        or "/environments/staging/active" in production
    ):
        failures.append("production references staging backend")
    if (
        "pwc_production_backend" in staging
        or "/environments/production/active" in staging
    ):
        failures.append("staging references production backend")
    for config, environment in (
        (production, "production"),
        (staging, "staging"),
    ):
        active = f"/environments/{environment}/active"
        if f"{active}/release/frontend-dist" not in config:
            failures.append(f"{environment} root is not its active slot release")
        if f"server unix:/srv/paperswithcode{active}/backend.sock;" not in config:
            failures.append(f"{environment} backend is not its active slot socket")
        if "keepalive " in config.split("server {", 1)[0]:
            failures.append(
                f"{environment} upstream keepalive can reuse the displaced slot"
            )
        if "127.0.0.1:8000" in config or "127.0.0.1:8001" in config:
            failures.append(f"{environment} retains a fixed application upstream")
        operator_block = location_block(
            config, 'location ~ "^/internal/(deployment-status|drain|undrain)$"'
        )
        if not operator_block or "return 404;" not in operator_block:
            failures.append(f"{environment} does not deny public deployment operators")
    if "8081" in staging:
        failures.append("staging exposes Vite/HMR")
    access_block = location_block(staging, "location = /_staging_access_check")
    if (
        not access_block
        or "internal;" not in access_block
        or "/api/v1/auth/staging-check" not in access_block
    ):
        failures.append("staging access-check contract is invalid")
    if "_staging_access_check" in production:
        failures.append("production acquires staging-wide admission gate")
    if CURATION_CALLBACK_LOCATION not in staging:
        failures.append("staging job-token callback route is missing")
    else:
        callback_block = staging.split(CURATION_CALLBACK_LOCATION, 1)[1].split("}", 1)[
            0
        ]
        if "auth_request" in callback_block:
            failures.append("staging job-token callback route uses browser auth")
        if "proxy_pass http://pwc_staging_backend;" not in callback_block:
            failures.append("staging job-token callback route misses staging backend")
    stream_block = location_block(staging, CHAT_STREAM_LOCATION)
    stream_requirements = (
        "limit_except POST",
        "auth_request /_staging_access_check;",
        "proxy_pass http://pwc_staging_backend;",
        "proxy_http_version 1.1;",
        'proxy_set_header Connection "";',
        "proxy_buffering off;",
        "proxy_cache off;",
        "gzip off;",
        "proxy_read_timeout 190s;",
    )
    if not stream_block:
        failures.append("staging chat stream route is missing")
    else:
        for requirement in stream_requirements:
            if requirement not in stream_block:
                failures.append(f"staging chat stream route misses: {requirement}")
    for config, environment, hostname, backend in (
        (
            production,
            "production",
            "chat-gateway.paperswithcode.co",
            "pwc_production_backend",
        ),
        (
            staging,
            "staging",
            "chat-gateway-staging.paperswithcode.co",
            "pwc_staging_backend",
        ),
    ):
        if f"server_name {hostname};" not in config:
            failures.append(f"{environment} chat gateway hostname is missing")
        if f"/etc/letsencrypt/live/{hostname}/fullchain.pem" not in config:
            failures.append(f"{environment} chat gateway TLS certificate is missing")
        for endpoint in (
            "catalog",
            "hf-catalog",
            "session-store",
            "web-fetch",
            "v1/messages",
            "v1/responses",
            *(
                ("artifact-prepare", "artifact-publish")
                if environment == "staging"
                else ()
            ),
        ):
            location = f"location = /api/internal/chat-gateway/{endpoint}"
            block = location_block(config, location)
            if not block:
                failures.append(
                    f"{environment} chat gateway {endpoint} route is missing"
                )
            elif f"proxy_pass http://{backend};" not in block:
                failures.append(
                    f"{environment} chat gateway {endpoint} misses {backend}"
                )
        if "client_max_body_size 512k;" not in config:
            failures.append(f"{environment} chat gateway body limit is missing")
    for config, environment, hostname in (
        (production, "production", "chat-executor.paperswithcode.co"),
        (staging, "staging", "chat-executor.staging.paperswithcode.co"),
    ):
        if f"server_name {hostname};" not in config:
            failures.append(f"{environment} executor hostname is missing")
        if f"/etc/letsencrypt/live/{hostname}/fullchain.pem" not in config:
            failures.append(f"{environment} executor TLS certificate is missing")
        executor_server = config.split(f"server_name {hostname};", 1)[-1].split(
            "\nserver {", 1
        )[0]
        if "ssl_protocols TLSv1.3;" not in executor_server:
            failures.append(f"{environment} executor must require TLS 1.3")
        block = location_block(config, "location = /v1/environment")
        for requirement in (
            "proxy_pass http://unix:/run/pwc-chat-executor/chat-executor-rendezvous.sock:;",
            "proxy_http_version 1.1;",
            "proxy_set_header Upgrade $http_upgrade;",
            'proxy_set_header Connection "upgrade";',
            "proxy_set_header X-PWC-Network-Source $remote_addr;",
            "proxy_read_timeout 20s;",
            "proxy_send_timeout 20s;",
            "proxy_buffering off;",
        ):
            if requirement not in block:
                failures.append(
                    f"{environment} executor rendezvous misses: {requirement}"
                )
        if config.count("proxy_set_header Upgrade") != 1:
            failures.append(
                f"{environment} exposes an unexpected WebSocket upgrade route"
            )
    if staging.count("location / {") != 1 or production.count("location / {") != 1:
        failures.append("ambiguous catch-all location")
    failures.extend(
        _validate_seo_routes(production, "pwc_production_backend", "production")
    )
    failures.extend(_validate_seo_routes(staging, "pwc_staging_backend", "staging"))
    staging_robots = staging.split("location = /robots.txt", 1)
    if len(staging_robots) == 2:
        robots_block = staging_robots[1].split("}", 1)[0]
        if "auth_request" in robots_block:
            failures.append("staging robots route is browser-authenticated")
    if "try_files $uri @public_pages;" not in production:
        failures.append("production public-page fallback is missing")
    if "try_files $uri @staging_public_pages;" not in staging:
        failures.append("staging public-page fallback is missing")
    for config, backend, environment in (
        (production, "pwc_production_backend", "production"),
        (staging, "pwc_staging_backend", "staging"),
    ):
        if SHARE_PAGE_LOCATION not in config:
            failures.append(f"{environment} public share page route is missing")
        else:
            block = location_block(config, SHARE_PAGE_LOCATION)
            if "auth_request" in block:
                failures.append(f"{environment} public share page uses browser auth")
            if 'X-Robots-Tag "noindex, nofollow" always' not in block:
                failures.append(f"{environment} public share page permits indexing")
            if 'Cache-Control "no-store"' not in block:
                failures.append(f"{environment} public share page may be cached")
        if SHARE_API_LOCATION not in config:
            failures.append(f"{environment} public share API route is missing")
        else:
            block = location_block(config, SHARE_API_LOCATION)
            if "auth_request" in block:
                failures.append(f"{environment} public share API uses browser auth")
            if f"proxy_pass http://{backend};" not in block:
                failures.append(f"{environment} public share API misses {backend}")
            if "limit_except GET" not in block:
                failures.append(f"{environment} public share API accepts writes")
    assets = staging.split("location ^~ /assets/", 1)
    if len(assets) != 2 or "auth_request" in assets[1].split("}", 1)[0]:
        failures.append("staging hashed assets are browser-authenticated")
    auth_me = staging.split("location = /api/v1/auth/me", 1)
    if len(auth_me) != 2 or "auth_request" in auth_me[1].split("}", 1)[0]:
        failures.append("staging auth status route is browser-authenticated")
    access_page = location_block(staging, "location = /request-access")
    if (
        not access_page
        or "auth_request" in access_page
        or "try_files /index.html =404;" not in access_page
        or 'X-Robots-Tag "noindex, nofollow" always' not in access_page
    ):
        failures.append("staging access request page is not a public noindex SPA route")
    access_api = location_block(staging, "location = /api/v1/staging-access-request")
    if (
        not access_api
        or "auth_request" in access_api
        or "limit_except POST" not in access_api
        or "proxy_pass http://pwc_staging_backend;" not in access_api
    ):
        failures.append("staging access request API contract is invalid")
    forbidden = location_block(staging, "location @staging_forbidden")
    if "return 302 /request-access;" not in forbidden:
        failures.append("staging forbidden users are not sent to request access")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent / "nginx"
    )
    args = parser.parse_args()
    failures = validate(
        (args.root / "paperswithcode.co.conf").read_text(),
        (args.root / "staging.paperswithcode.co.conf").read_text(),
    )
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
