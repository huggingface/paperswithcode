"""Exercise the same-origin arXiv PDF proxy with an isolated, unprivileged nginx."""

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

from deploy.nginx_validate import ARXIV_PDF_LOCATION, location_block

ROOT = Path(__file__).resolve().parents[3]
PDF = bytes(range(256)) * 4096


class ArxivUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[tuple[str, dict[str, str]]] = []

    def do_GET(self):
        ArxivUpstream.requests.append((self.path, dict(self.headers)))
        if self.path.startswith("/pdf/2610.99999"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start, end, status = 0, len(PDF) - 1, 200
        if self.headers.get("Range"):
            first, last = self.headers["Range"].removeprefix("bytes=").split("-")
            start, end, status = int(first), int(last), 206
        self.send_response(status)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Set-Cookie", "browser=arxiv")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(PDF)}")
        self.end_headers()
        self.wfile.write(PDF[start : end + 1])

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_arxiv_pdf_proxy_passes_ranges_for_valid_ids_only(environment):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("nginx is needed for the isolated integration test")
    name = (
        "paperswithcode.co.conf"
        if environment == "production"
        else "staging.paperswithcode.co.conf"
    )
    template = (ROOT / "deploy/nginx" / name).read_text()
    zone = next(
        line
        for line in template.splitlines()
        if f"zone=pwc_{environment}_arxiv_pdf:" in line
    )
    ArxivUpstream.requests = []
    with ThreadingHTTPServer(("127.0.0.1", 0), ArxivUpstream) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        location = location_block(template, ARXIV_PDF_LOCATION).replace(
            "https://arxiv.org/pdf/", f"http://127.0.0.1:{upstream.server_port}/pdf/"
        )
        with tempfile.TemporaryDirectory(prefix="pwc-arxiv-pdf-nginx-") as directory:
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
{zone}
server {{
listen 127.0.0.1:{port};
location = /_staging_access_check {{ return 204; }}
location @staging_signin {{ return 401; }}
location @staging_forbidden {{ return 403; }}
location / {{ return 418; }}
{location}
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
                            client.get("/")
                            break
                        except httpx.ConnectError:
                            if process.poll() is not None:
                                pytest.fail((root / "error.log").read_text())
                            time.sleep(0.05)
                    else:
                        pytest.fail("isolated nginx did not start")

                    ranged = client.get(
                        "/paper-assets/arxiv-pdf/2610.03391",
                        headers={
                            "Range": "bytes=100-199",
                            "Cookie": "pwc_session=secret",
                            "Authorization": "Bearer secret",
                        },
                    )
                    assert ranged.status_code == 206
                    assert ranged.content == PDF[100:200]
                    assert (
                        ranged.headers["content-range"] == f"bytes 100-199/{len(PDF)}"
                    )
                    assert ranged.headers["accept-ranges"] == "bytes"
                    assert "set-cookie" not in ranged.headers
                    assert (
                        "Accept-Ranges"
                        in ranged.headers["access-control-expose-headers"]
                    )
                    path, headers = ArxivUpstream.requests[-1]
                    assert path == "/pdf/2610.03391"
                    assert headers["Range"] == "bytes=100-199"
                    assert headers["Host"] == "arxiv.org"
                    assert "Cookie" not in headers
                    assert "Authorization" not in headers

                    full = client.get("/paper-assets/arxiv-pdf/hep-th/9901001v2")
                    assert full.status_code == 200
                    assert full.content == PDF
                    assert ArxivUpstream.requests[-1][0] == "/pdf/hep-th/9901001v2"
                    assert (
                        client.get(
                            "/paper-assets/arxiv-pdf/math.GT/0309136"
                        ).status_code
                        == 200
                    )
                    assert (
                        client.get("/paper-assets/arxiv-pdf/2610.99999").status_code
                        == 404
                    )

                    seen = len(ArxivUpstream.requests)
                    for path in (
                        "/paper-assets/arxiv-pdf/2610.03391.pdf",
                        "/paper-assets/arxiv-pdf/2610.03391/../../abs/2610.03391",
                        "/paper-assets/arxiv-pdf/2610.03391%3Fx=1",
                        "/paper-assets/arxiv-pdf/https://evil.example/x",
                        "/paper-assets/arxiv-pdf/2610.03391v1/extra",
                        "/paper-assets/arxiv-pdf/",
                    ):
                        assert client.get(path).status_code == 418, path
                    assert (
                        client.post("/paper-assets/arxiv-pdf/2610.03391").status_code
                        == 403
                    )
                    assert len(ArxivUpstream.requests) == seen
            finally:
                process.terminate()
                process.wait(timeout=5)
                upstream.shutdown()
                thread.join(timeout=5)
