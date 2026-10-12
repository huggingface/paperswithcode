import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from deploy.nginx_validate import validate
from deploy.nginx_validate import location_block

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION = (ROOT / "deploy/nginx/paperswithcode.co.conf").read_text()
STAGING = (ROOT / "deploy/nginx/staging.paperswithcode.co.conf").read_text()


class MCPUpstream(BaseHTTPRequestHandler):
    def _respond(self):
        size = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(size) if size else b""
        payload = json.dumps(
            {"path": self.path, "method": self.command, "body_bytes": len(body)}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = _respond
    do_HEAD = _respond
    do_POST = _respond

    def log_message(self, *_args):
        pass


def _without_access_log(block: str) -> str:
    return re.sub(r"^\s*access_log [^;]+;\s*$", "", block, flags=re.MULTILINE)


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
        for protocol_check in (
            "if ($request_method = POST)",
            "if ($request_method = DELETE)",
            "if ($request_method = OPTIONS)",
            'if ($http_mcp_protocol_version != "")',
            f"if (${prefix}_stream_signal)",
        ):
            assert protocol_check in block
        assert f"if (${prefix}_html_signal = 0)" not in block
        assert "return 406" not in block
        assert "limit_except" not in block
        assert f"${prefix}_stream_q0" in config
        assert f"${prefix}_html_q0" in config
        assert "text/event-stream" in config
        assert "text/html" in config
        assert "(?:(?!\\bq\\s*=)[^,])*" in config
        assert "~^0:1: 1;" in config


def test_mcp_discovery_and_schema_routes_proxy_to_the_mcp_service():
    for config, port in ((PRODUCTION, 8002), (STAGING, 8003)):
        well_known = config[config.index("location = /.well-known/mcp") :]
        well_known = well_known[: well_known.index("\n    }")]
        assert f"proxy_pass http://127.0.0.1:{port}/.well-known/mcp;" in well_known
        assert "auth_request" not in well_known

        schema = config[config.index("location = /mcp/schema") :]
        schema = schema[: schema.index("\n    }")]
        assert f"proxy_pass http://127.0.0.1:{port}/docs;" in schema
        assert 'add_header Cache-Control "no-store" always;' in schema


@pytest.mark.parametrize(
    ("environment", "template", "mcp_port"),
    (("production", PRODUCTION, 8002), ("staging", STAGING, 8003)),
)
def test_mcp_routes_in_isolated_unprivileged_nginx(
    environment: str, template: str, mcp_port: int
):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx is needed for the isolated integration test")
    prefix = f"pwc_{environment}_mcp"
    maps_start = template.index(f"map $request_method ${prefix}_method_allowed")
    maps_end = template.index(f"log_format {prefix}", maps_start)
    maps_end = template.index("\n", maps_end)
    maps = template[maps_start:maps_end]
    locations = "\n".join(
        _without_access_log(location_block(template, marker))
        for marker in (
            f"location @{environment}_mcp_protocol",
            "location = /mcp/health",
            "location = /.well-known/mcp",
            "location = /mcp/schema",
            "location = /mcp {",
            "location = /mcp/ {",
            "location ^~ /mcp/",
        )
    )
    with ThreadingHTTPServer(("127.0.0.1", 0), MCPUpstream) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        locations = locations.replace(
            f"http://127.0.0.1:{mcp_port}",
            f"http://127.0.0.1:{upstream.server_port}",
        )
        with tempfile.TemporaryDirectory(prefix="pwc-mcp-nginx-") as directory:
            root = Path(directory)
            identity = {}
            if os.geteuid() == 0:
                nobody = pwd.getpwnam("nobody")
                os.chown(root, nobody.pw_uid, nobody.pw_gid)
                identity = {
                    "user": nobody.pw_uid,
                    "group": nobody.pw_gid,
                    "extra_groups": [],
                }
            root.chmod(0o755)
            for name in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
                path = root / name
                path.mkdir()
                if identity:
                    os.chown(path, identity["user"], identity["group"])
            (root / "index.html").write_text("Papers With Code MCP setup")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            config = f"""worker_processes 1;
pid {root}/nginx.pid;
lock_file {root}/nginx.lock;
error_log {root}/error.log;
events {{ worker_connections 128; }}
http {{
access_log off;
client_body_temp_path {root}/body;
proxy_temp_path {root}/proxy;
fastcgi_temp_path {root}/fastcgi;
uwsgi_temp_path {root}/uwsgi;
scgi_temp_path {root}/scgi;
{maps}
server {{
listen 127.0.0.1:{port};
root {root};
location = /_staging_access_check {{ return 204; }}
{locations}
}}
}}"""
            config_path = root / "nginx.conf"
            config_path.write_text(config)
            command = [
                nginx,
                "-p",
                f"{root}/",
                "-c",
                str(config_path),
                "-e",
                str(root / "error.log"),
            ]
            checked = subprocess.run([*command, "-t"], capture_output=True, **identity)
            assert checked.returncode == 0, checked.stderr.decode()
            process = subprocess.Popen(
                [*command, "-g", "daemon off; master_process off;"], **identity
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=3
                ) as client:
                    for _ in range(50):
                        try:
                            guide = client.get("/mcp")
                            break
                        except httpx.ConnectError:
                            if process.poll() is not None:
                                pytest.fail((root / "error.log").read_text())
                            time.sleep(0.05)
                    else:
                        pytest.fail("isolated nginx did not start")
                    assert guide.text == "Papers With Code MCP setup"
                    assert client.get("/mcp/").status_code == 200
                    protocol = client.post(
                        "/mcp",
                        content=b"x" * (128 * 1024),
                        headers={"Accept": "application/json, text/event-stream"},
                    )
                    assert protocol.json() == {
                        "path": "/mcp",
                        "method": "POST",
                        "body_bytes": 128 * 1024,
                    }
                    assert client.get("/.well-known/mcp").json()["path"] == (
                        "/.well-known/mcp"
                    )
                    assert client.get("/mcp/schema").json()["path"] == "/docs"
                    assert client.get("/mcp/unknown").status_code == 404
            finally:
                process.terminate()
                process.wait(timeout=5)
                upstream.shutdown()
                thread.join(timeout=5)


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


@pytest.mark.parametrize(
    ("config", "environment", "port", "backend", "host"),
    [
        (STAGING, "staging", 8011, "pwc_staging_backend", "staging.paperswithcode.co"),
        (PRODUCTION, "production", 8010, "pwc_production_backend", "paperswithcode.co"),
    ],
)
def test_internal_mcp_api_bridge_is_loopback_only(
    config, environment, port, backend, host
):
    # The MCP service reads the catalog through this bridge in both
    # environments, so its traffic never leaves the host or shares the public
    # per-IP rate limits.
    assert f"listen 127.0.0.1:{port};" in config
    marker = config.index(f"server_name pwc-{environment}-mcp-api;")
    bridge_start = config.rfind("server {", 0, marker)
    bridge_end = config.index("\n}\n\nmap ", bridge_start)
    bridge = config[bridge_start:bridge_end]
    assert f"listen 127.0.0.1:{port};" in bridge
    assert 'location ~ "^/api/v1/(papers' in bridge
    assert "limit_except GET HEAD" in bridge
    assert f"proxy_pass http://{backend};" in bridge
    assert f"proxy_set_header Host {host};" in bridge
    assert "auth_request" not in bridge
    assert "limit_req" not in bridge
    assert "location ~ ^/ {" in bridge
    assert "return 404;" in bridge
    assert bridge.index('location ~ "^/api/v1/') < bridge.index("location ~ ^/ {")
