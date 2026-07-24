"""Local broker process: the only sandbox process holding a turn capability."""

from __future__ import annotations

import http.client
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

_PAPER_INFO = re.compile(r"^/api/v1/papers/([^/]+)$")
_PAPER_RELATED = re.compile(r"^/api/v1/papers/([^/]+)/related$")
_PAPER_READ = re.compile(r"^/api/v1/research/papers/([^/]+)/read$")
_PAPER_LINEAGE = re.compile(r"^/api/v1/research/papers/([^/]+)/lineage$")


def _load_config() -> dict:
    fd = int(os.environ["PWC_BROKER_CONFIG_FD"])
    with os.fdopen(fd, "rb", closefd=True) as handle:
        config = json.loads(handle.read(16 * 1024))
    required = {"capability", "gateway_url", "session_id", "turn_id"}
    if set(config) != required:
        raise RuntimeError("Invalid broker configuration")
    return config


CONFIG = _load_config()
UPSTREAM = urlsplit(CONFIG["gateway_url"])


class Handler(BaseHTTPRequestHandler):
    server_version = "pwc-broker/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _connection(self):
        connection = (
            http.client.HTTPSConnection
            if UPSTREAM.scheme == "https"
            else http.client.HTTPConnection
        )
        return connection(UPSTREAM.hostname, UPSTREAM.port, timeout=180)

    def _forward(
        self,
        path: str,
        body: bytes,
        *,
        content_type: str = "application/json",
        accept: str = "application/json",
    ) -> None:
        connection = self._connection()
        prefix = UPSTREAM.path.rstrip("/")
        connection.request(
            "POST",
            f"{prefix}/{path.lstrip('/')}",
            body=body,
            headers={
                "Authorization": f"Bearer {CONFIG['capability']}",
                "X-PWC-Session": CONFIG["session_id"],
                "X-PWC-Turn": CONFIG["turn_id"],
                "Content-Type": content_type,
                "Accept": accept,
            },
        )
        response = connection.getresponse()
        self.send_response(response.status)
        upstream_type = response.getheader("Content-Type")
        if upstream_type:
            self.send_header("Content-Type", upstream_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            connection.close()

    def do_POST(self) -> None:
        length = min(int(self.headers.get("Content-Length", "0")), 512 * 1024)
        body = self.rfile.read(length)
        if self.path == "/session-store":
            self._forward("session-store", body)
            return
        if self.path == "/v1/messages":
            self._forward(
                "v1/messages",
                body,
                content_type=self.headers.get("Content-Type", "application/json"),
                accept=self.headers.get("Accept", "application/json"),
            )
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        operation: str | None = None
        arguments: dict = query
        match = None
        if parsed.path == "/api/v1/papers/search":
            operation = "search"
            arguments = {
                "query": query.get("q", ""),
                "page": query.get("page", 1),
                "limit": query.get("page_size", 10),
                "mode": query.get("mode"),
            }
        elif parsed.path in {"/api/v1/papers", "/api/v1/papers/"}:
            operation = "paper_list"
            arguments = {
                **query,
                "all_versions": query.get("latest_only") == "false",
                "include_resources": query.get("include_resources") == "true",
            }
        elif parsed.path == "/api/v1/papers/recent":
            operation = "paper_recent"
        elif parsed.path == "/api/v1/papers/trending":
            operation = "paper_trending"
        elif parsed.path in {"/api/v1/datasets", "/api/v1/datasets/"}:
            operation = "benchmark_list"
            arguments = {
                "page": query.get("page", 1),
                "page_size": query.get("page_size", 50),
                "search": query.get("q"),
                "task": query.get("task"),
                "include_descendants": query.get("include_descendants") == "true",
                "min_eval_count": query.get("min_eval_count"),
                "is_open": query.get("is_open"),
                "order_by": (query.get("ordering") or "name").lstrip("-"),
                "order_dir": "desc"
                if (query.get("ordering") or "").startswith("-")
                else "asc",
            }
        elif match := _PAPER_RELATED.match(parsed.path):
            operation = "paper_related"
            arguments = {"paper": match.group(1), "limit": query.get("limit", 4)}
        elif match := _PAPER_READ.match(parsed.path):
            operation = "paper_read"
            arguments = {"paper": match.group(1)}
        elif match := _PAPER_LINEAGE.match(parsed.path):
            operation = "paper_lineage_list"
            arguments = {"paper": match.group(1)}
        elif match := _PAPER_INFO.match(parsed.path):
            operation = "paper_info"
            arguments = {
                "paper": match.group(1),
                "include_resources": query.get("include_resources") == "true",
            }
        if operation is None:
            self.send_error(404)
            return
        connection = self._connection()
        payload = json.dumps(
            {"operation": operation, "arguments": arguments}, separators=(",", ":")
        ).encode()
        prefix = UPSTREAM.path.rstrip("/")
        connection.request(
            "POST",
            f"{prefix}/catalog",
            body=payload,
            headers={
                "Authorization": f"Bearer {CONFIG['capability']}",
                "X-PWC-Session": CONFIG["session_id"],
                "X-PWC-Turn": CONFIG["turn_id"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        raw = response.read(2 * 1024 * 1024)
        connection.close()
        if response.status >= 400:
            self.send_response(response.status)
            self.end_headers()
            self.wfile.write(raw)
            return
        result = json.loads(raw).get("result")
        if operation == "paper_read":
            output = str(result.get("markdown", "")).encode()
            content_type = "text/plain; charset=utf-8"
        else:
            output = json.dumps(
                result, ensure_ascii=False, separators=(",", ":")
            ).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(output)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(output)


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
