from pathlib import Path

from deploy.nginx_validate import validate

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = (ROOT / "deploy/nginx/paperswithcode.co.conf").read_text()
STAGING = (ROOT / "deploy/nginx/staging.paperswithcode.co.conf").read_text()


def test_checked_in_nginx_has_complete_mcp_dispatch_contract():
    assert validate(PRODUCTION, STAGING) == []


def test_mcp_protocol_signals_precede_html_and_honor_q_zero():
    for config, environment in (
        (PRODUCTION, "production"),
        (STAGING, "staging"),
    ):
        prefix = f"pwc_{environment}_mcp"
        location = config.index("location = /mcp {")
        block = config[location : config.index("\n    }", location)]
        html_check = block.index(f"if (${prefix}_html_signal = 0)")
        for protocol_check in (
            "if ($request_method = POST)",
            "if ($request_method = DELETE)",
            "if ($request_method = OPTIONS)",
            'if ($http_mcp_protocol_version != "")',
            f"if (${prefix}_stream_signal)",
        ):
            assert block.index(protocol_check) < html_check
        assert f"${prefix}_stream_q0" in config
        assert f"${prefix}_html_q0" in config
        assert "text/event-stream" in config
        assert "text/html" in config
        assert "(?:(?!\\bq\\s*=)[^,])*" in config
        assert "~^0:1: 1;" in config


def test_mcp_media_patterns_are_quoted_for_real_nginx_parsing():
    for config in (PRODUCTION, STAGING):
        assert '"~*(?:^|,)\\s*text/event-stream' in config
        assert '"~*(?:^|,)\\s*text/html' in config


def test_mcp_validation_rejects_spa_fallthrough_and_untrusted_forwarding():
    broken_spa = PRODUCTION.replace(
        "try_files /index.html =404;", "try_files $uri /index.html;", 1
    )
    assert any(
        "MCP HTML location misses" in failure
        for failure in validate(broken_spa, STAGING)
    )

    broken_proxy = PRODUCTION.replace(
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        1,
    )
    assert any(
        "X-Forwarded-For" in failure for failure in validate(broken_proxy, STAGING)
    )


def test_staging_protocol_and_health_are_public_but_documentation_remains_gated():
    protocol_start = STAGING.index("location @staging_mcp_protocol")
    protocol_end = STAGING.index("\n    }", protocol_start)
    assert "auth_request" not in STAGING[protocol_start:protocol_end]

    health_start = STAGING.index("location = /mcp/health")
    health_end = STAGING.index("\n    }", health_start)
    assert "auth_request" not in STAGING[health_start:health_end]

    html_start = STAGING.index("location = /mcp {")
    html_end = STAGING.index("\n    }", html_start)
    assert "auth_request /_staging_access_check;" in STAGING[html_start:html_end]


def test_mcp_access_log_excludes_identifiers_and_request_content():
    for config, environment in (
        (PRODUCTION, "production"),
        (STAGING, "staging"),
    ):
        marker = f"log_format pwc_{environment}_mcp "
        line = next(line for line in config.splitlines() if line.startswith(marker))
        for forbidden in ("$remote_addr", "$request_uri", "$request ", "$args"):
            assert forbidden not in line
        for allowed in ("$status", "$body_bytes_sent", "$request_time"):
            assert allowed in line


def test_staging_internal_mcp_api_bridge_is_loopback_only():
    assert "listen 127.0.0.1:8011;" in STAGING
    marker = STAGING.index("server_name pwc-staging-mcp-api;")
    bridge_start = STAGING.rfind("server {", 0, marker)
    bridge_end = STAGING.index("\n}\n\nmap ", bridge_start)
    bridge = STAGING[bridge_start:bridge_end]
    assert "listen 127.0.0.1:8011;" in bridge
    assert 'location ~ "^/api/v1/(papers' in bridge
    assert "limit_except GET HEAD" in bridge
    assert "proxy_pass http://pwc_staging_backend;" in bridge
    assert "auth_request" not in bridge
    assert "location ~ ^/ {" in bridge
    assert "return 404;" in bridge
    assert bridge.index('location ~ "^/api/v1/') < bridge.index("location ~ ^/ {")
