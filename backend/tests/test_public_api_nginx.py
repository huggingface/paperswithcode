"""Exercise the checked-in limits using unprivileged, isolated nginx and upstream."""

import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from deploy.nginx_validate import location_block

ROOT = Path(__file__).resolve().parents[2]


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    do_OPTIONS = do_GET
    do_POST = do_GET

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_nginx_catalog_limits_and_docs_routing(environment):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx is needed for the isolated integration test")
    name = (
        "paperswithcode.co.conf"
        if environment == "production"
        else "staging.paperswithcode.co.conf"
    )
    template = (ROOT / "deploy/nginx" / name).read_text()
    maps = template.split("upstream ", 1)[0]
    api = location_block(template, "location /api/")
    limited = location_block(template, "location @public_api_rate_limited")
    docs = location_block(template, "location = /docs/api")
    with ThreadingHTTPServer(("127.0.0.1", 0), Upstream) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory(prefix="pwc-api-nginx-") as directory:
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
            (root / "index.html").write_text("API documentation app")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            api = api.replace(
                f"http://pwc_{environment}_backend",
                f"http://127.0.0.1:{upstream.server_port}",
            ).replace("include proxy_params;", "")
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
{api}
{limited}
{docs}
}}
}}"""
            conf = root / "nginx.conf"
            conf.write_text(config)
            command = [
                nginx,
                "-p",
                f"{root}/",
                "-c",
                str(conf),
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
                            ready = client.get("/docs/api")
                            break
                        except httpx.ConnectError:
                            if process.poll() is not None:
                                pytest.fail((root / "error.log").read_text())
                            time.sleep(0.05)
                    else:
                        pytest.fail("isolated nginx did not start")
                    assert ready.text == "API documentation app"
                    responses = [
                        client.get(
                            "/api/v1/papers/search?q=test&mode=keyword",
                            headers={"X-Forwarded-For": f"192.0.2.{i}"},
                        )
                        for i in range(28)
                    ]
                    assert responses[0].status_code == 200
                    rejected = [r for r in responses if r.status_code == 429]
                    assert rejected, (
                        "search limits must apply despite spoofed forwarding headers"
                    )
                    assert (
                        rejected[0]
                        .json()["detail"]
                        .startswith("API traffic limit exceeded")
                    )
                    assert rejected[0].headers["retry-after"] == "2"
                    assert rejected[0].headers["access-control-allow-origin"] == "*"
                    assert client.get("/api/v1/papers/123").status_code == 200
                    assert client.options("/api/v1/papers/search").status_code == 200
                    assert client.post("/api/v1/papers/search").status_code == 200
                    time.sleep(2.05)
                    assert client.get("/api/v1/papers/search?q=test").status_code == 200
                    details = [client.get("/api/v1/papers/123") for _ in range(90)]
                    assert any(r.status_code == 429 for r in details)
                    assert client.get("/api/v1/auth/me").status_code == 200
            finally:
                process.terminate()
                process.wait(timeout=5)
                upstream.shutdown()
                thread.join(timeout=5)
