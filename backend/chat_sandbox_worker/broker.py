"""Local broker process: the only sandbox process holding a turn capability."""

from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import socketserver
import ssl
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Full, LifoQueue
from threading import Condition, Lock
from time import monotonic
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_PAPER_INFO = re.compile(r"^/api/v1/papers/([^/]+)$")
_PAPER_RELATED = re.compile(r"^/api/v1/papers/([^/]+)/related$")
_PAPER_READ = re.compile(r"^/api/v1/research/papers/([^/]+)/read$")
_PAPER_LINEAGE = re.compile(r"^/api/v1/research/papers/([^/]+)/lineage$")
_TASK_PAGE = re.compile(r"^/api/v1/tasks/([^/]+)/page$")
_TASK_PAPERS = re.compile(r"^/api/v1/tasks/([^/]+)/papers$")
_TASK_DETAIL = re.compile(r"^/api/v1/tasks/([^/]+)$")
_METHOD_DETAIL = re.compile(r"^/api/v1/methods/([^/]+)$")
_CONFERENCE_DETAIL = re.compile(r"^/api/v1/conferences/([^/]+)$")
_ORGANIZATION_DETAIL = re.compile(r"^/api/v1/organizations/([^/]+)$")
_BENCHMARK_TRENDS = re.compile(r"^/api/v1/tasks/([^/]+)/trending-benchmarks$")
_BENCHMARK_EVALUATIONS = re.compile(r"^/api/v1/datasets/([^/]+)/evaluations/$")
_EVALUATIONS = re.compile(r"^/api/v1/evaluations/$")
CONTROL_SOCKET = Path("/var/empty/pwc-broker/control.sock")
CAPABILITY_DRAIN_QUIET_SECONDS = 0.5
CAPABILITY_DRAIN_TIMEOUT_SECONDS = 20.0
GATEWAY_CONNECTION_POOL_SIZE = 4
GATEWAY_CONNECTION_MAX_IDLE_SECONDS = 30.0
HF_OPERATIONS = frozenset(
    {
        "collection_info",
        "collection_list",
        "dataset_card",
        "dataset_info",
        "dataset_list",
        "model_card",
        "model_info",
        "model_list",
        "space_card",
        "space_info",
        "space_list",
    }
)
HF_MAX_RESPONSE_BYTES = 300 * 1024
ARTIFACT_MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def _load_config() -> dict:
    fd = int(os.environ["PWC_BROKER_CONFIG_FD"])
    with os.fdopen(fd, "rb", closefd=True) as handle:
        config = json.loads(handle.read(16 * 1024))
    required = {"gateway_url", "proxy_token"}
    optional = {"capability", "session_id", "turn_id"}
    if not required.issubset(config) or not set(config).issubset(required | optional):
        raise RuntimeError("Invalid broker configuration")
    if set(config) & optional and not optional.issubset(config):
        raise RuntimeError("Incomplete broker capability")
    return config


CONFIG = _load_config()
UPSTREAM = urlsplit(CONFIG["gateway_url"])
PROXY_CA_PATH = Path("/tmp/pwc-webfetch-ca.pem")
PROXY_GRANTS: dict[str, list[float]] = {}
PROXY_GRANTS_LOCK = Lock()


class BrokerState:
    def __init__(self, initial: dict):
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._active: dict[str, str] | None = None
        self._inflight = 0
        self._last_activity = monotonic()
        if "capability" in initial:
            self._active = {
                key: str(initial[key])
                for key in ("capability", "session_id", "turn_id")
            }

    def install(self, payload: dict) -> None:
        required = {"capability", "session_id", "turn_id"}
        if set(payload) != required or not all(
            isinstance(payload[key], str) and payload[key] for key in required
        ):
            raise RuntimeError("Invalid broker capability")
        with self._lock:
            if self._active is not None:
                raise RuntimeError("Broker capability already installed")
            self._active = dict(payload)
            self._last_activity = monotonic()

    def clear(
        self,
        *,
        session_id: str,
        turn_id: str,
        quiet_seconds: float = CAPABILITY_DRAIN_QUIET_SECONDS,
        timeout_seconds: float = CAPABILITY_DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        deadline = monotonic() + timeout_seconds
        with self._condition:
            if self._active is None:
                raise RuntimeError("Broker capability is not installed")
            if (
                self._active["session_id"] != session_id
                or self._active["turn_id"] != turn_id
            ):
                raise RuntimeError("Broker capability correlation failed")
            while True:
                quiet_remaining = quiet_seconds - (monotonic() - self._last_activity)
                if self._inflight == 0 and quiet_remaining <= 0:
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise RuntimeError("Broker capability drain timed out")
                self._condition.wait(
                    timeout=min(
                        remaining,
                        max(quiet_remaining, 0.01),
                    )
                )
            self._active = None
        with PROXY_GRANTS_LOCK:
            PROXY_GRANTS.clear()

    def begin_request(self) -> dict[str, str]:
        with self._condition:
            if self._active is None:
                raise PermissionError("No turn capability is installed")
            self._inflight += 1
            self._last_activity = monotonic()
            return dict(self._active)

    def finish_request(self) -> None:
        with self._condition:
            if self._inflight <= 0:
                raise RuntimeError("Broker request accounting underflow")
            self._inflight -= 1
            self._last_activity = monotonic()
            self._condition.notify_all()

    def current(self) -> dict[str, str]:
        with self._lock:
            if self._active is None:
                raise PermissionError("No turn capability is installed")
            return dict(self._active)

    def active(self) -> bool:
        with self._lock:
            return self._active is not None


STATE = BrokerState(CONFIG)


def _grant_proxy_url(url: str) -> None:
    with PROXY_GRANTS_LOCK:
        PROXY_GRANTS.setdefault(url, []).append(monotonic() + 10)


def _consume_proxy_url(url: str) -> bool:
    now = monotonic()
    with PROXY_GRANTS_LOCK:
        grants = [expiry for expiry in PROXY_GRANTS.pop(url, []) if expiry > now]
        if not grants:
            return False
        if len(grants) > 1:
            PROXY_GRANTS[url] = grants[1:]
        return True


def _connection():
    connection = (
        http.client.HTTPSConnection
        if UPSTREAM.scheme == "https"
        else http.client.HTTPConnection
    )
    return connection(UPSTREAM.hostname, UPSTREAM.port, timeout=180)


class GatewayConnectionPool:
    """Bounded idle pool for the broker's dedicated gateway connection."""

    def __init__(
        self,
        factory: Callable[[], object],
        *,
        max_size: int,
        max_idle_seconds: float,
    ) -> None:
        self._factory = factory
        self._max_idle_seconds = max_idle_seconds
        self._idle: LifoQueue[tuple[object, float]] = LifoQueue(maxsize=max_size)

    def acquire(self):
        while True:
            try:
                connection, returned_at = self._idle.get_nowait()
            except Empty:
                return self._factory()
            if monotonic() - returned_at <= self._max_idle_seconds:
                return connection
            connection.close()

    def release(self, connection, *, reusable: bool) -> None:
        if not reusable:
            connection.close()
            return
        try:
            self._idle.put_nowait((connection, monotonic()))
        except Full:
            connection.close()

    def close(self) -> None:
        while True:
            try:
                connection, _returned_at = self._idle.get_nowait()
            except Empty:
                return
            connection.close()


GATEWAY_CONNECTIONS = GatewayConnectionPool(
    lambda: _connection(),
    max_size=GATEWAY_CONNECTION_POOL_SIZE,
    max_idle_seconds=GATEWAY_CONNECTION_MAX_IDLE_SECONDS,
)


def _response_reusable(response) -> bool:
    if getattr(response, "will_close", False):
        return False
    isclosed = getattr(response, "isclosed", None)
    return not callable(isclosed) or bool(isclosed())


def _gateway_headers(
    *, active: dict[str, str] | None = None, content_type: str = "application/json"
) -> dict[str, str]:
    active = active or STATE.current()
    return {
        "Authorization": f"Bearer {active['capability']}",
        "X-PWC-Session": active["session_id"],
        "X-PWC-Turn": active["turn_id"],
        "Content-Type": content_type,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "pwc-broker/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _connection(self):
        return GATEWAY_CONNECTIONS.acquire()

    def _forward(
        self,
        path: str,
        body: bytes,
        *,
        content_type: str = "application/json",
        accept: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        active = STATE.begin_request()
        connection = self._connection()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/{path.lstrip('/')}",
                body=body,
                headers={
                    **_gateway_headers(active=active, content_type=content_type),
                    "Accept": accept,
                    **(extra_headers or {}),
                },
            )
            response = connection.getresponse()
            self.send_response(response.status)
            upstream_type = response.getheader("Content-Type")
            if upstream_type:
                self.send_header("Content-Type", upstream_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
            reusable = _response_reusable(response)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()

    def _forward_upload(self, path: str, length: int) -> None:
        active = STATE.begin_request()
        connection = self._connection()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.putrequest("POST", f"{prefix}/{path.lstrip('/')}")
            for name, value in {
                **_gateway_headers(active=active, content_type="application/zip"),
                "Accept": "application/json",
                "Content-Length": str(length),
            }.items():
                connection.putheader(name, value)
            connection.endheaders()
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(64 * 1024, remaining))
                if not chunk:
                    raise ConnectionError("Artifact upload ended early")
                connection.send(chunk)
                remaining -= len(chunk)
            response = connection.getresponse()
            raw = response.read(64 * 1024)
            self.send_response(response.status)
            self.send_header(
                "Content-Type", response.getheader("Content-Type") or "application/json"
            )
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            reusable = _response_reusable(response)
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()

    def _forward_hf(self, body: bytes) -> None:
        active = STATE.begin_request()
        connection = self._connection()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/hf-catalog",
                body=body,
                headers={
                    **_gateway_headers(active=active),
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read(HF_MAX_RESPONSE_BYTES + 1)
            if len(raw) > HF_MAX_RESPONSE_BYTES:
                self.send_error(502)
                return
            content_type = (response.getheader("Content-Type") or "").partition(";")[0]
            if content_type != "application/json":
                self.send_error(502)
                return
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            reusable = _response_reusable(response)
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()

    def _forward_semantic_scholar(self, body: bytes) -> None:
        active = STATE.begin_request()
        connection = self._connection()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/catalog",
                body=json.dumps(
                    {
                        "operation": "semantic_scholar",
                        "arguments": json.loads(body),
                    },
                    separators=(",", ":"),
                ).encode(),
                headers={
                    **_gateway_headers(active=active),
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                self.send_error(502)
                return
            if response.status >= 400:
                self.send_response(response.status)
                self.end_headers()
                self.wfile.write(raw)
                return
            result = json.loads(raw)["result"]
            output = json.dumps(
                result, ensure_ascii=False, separators=(",", ":")
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(output)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(output)
            reusable = _response_reusable(response)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.send_error(502)
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            declared_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if path == "/artifact-publish":
            if not 0 < declared_length <= ARTIFACT_MAX_UPLOAD_BYTES:
                self.send_error(413)
                return
            publication_id = parse_qs(urlsplit(self.path).query).get(
                "publication_id", [""]
            )[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", publication_id):
                self.send_error(422)
                return
            self._forward_upload(
                f"artifact-publish?publication_id={publication_id}", declared_length
            )
            return
        maximum_body = 3 * 1024 * 1024 if path == "/paper" else 512 * 1024
        length = min(declared_length, maximum_body)
        body = self.rfile.read(length)
        if declared_length != length:
            self.send_error(413)
            return
        if path == "/hf/v1/query":
            try:
                payload = json.loads(body)
                operation = payload["operation"]
                arguments = payload["arguments"]
                if (
                    set(payload) != {"operation", "arguments"}
                    or operation not in HF_OPERATIONS
                    or not isinstance(arguments, dict)
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(422)
                return
            envelope = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode()
            self._forward_hf(envelope)
            return
        if path == "/proxy-authorize":
            if not STATE.active():
                self.send_error(403)
                return
            supplied = self.headers.get("X-PWC-Proxy-Token", "")
            if not hmac.compare_digest(supplied, CONFIG["proxy_token"]):
                self.send_error(403)
                return
            try:
                payload = json.loads(body)
                url = payload["url"]
                if not isinstance(url, str) or len(url) > 2000:
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(422)
                return
            _grant_proxy_url(url)
            self.send_response(204)
            self.end_headers()
            return
        if path == "/session-store":
            self._forward("session-store", body)
            return
        if path == "/artifact-prepare":
            self._forward("artifact-prepare", body)
            return
        if path == "/paper":
            self._forward("paper", body)
            return
        if path == "/web-search":
            try:
                payload = json.loads(body)
                query = payload["query"]
                if set(payload) != {"query"} or not isinstance(query, str):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(422)
                return
            envelope = json.dumps(
                {"operation": "web_search", "arguments": {"query": query}},
                separators=(",", ":"),
            ).encode()
            self._forward("catalog", envelope)
            return
        if path in {"/v1/messages", "/v1/responses"}:
            self._forward(
                "v1/messages" if path == "/v1/responses" else path.lstrip("/"),
                body,
                content_type=self.headers.get("Content-Type", "application/json"),
                accept=self.headers.get("Accept", "application/json"),
                extra_headers=(
                    {"X-PWC-Provider-Protocol": "openai-responses"}
                    if path == "/v1/responses"
                    else None
                ),
            )
            return
        self.send_error(404)

    def do_GET(self) -> None:
        if not STATE.active():
            self.send_error(403)
            return
        parsed = urlsplit(self.path)
        query_values = parse_qs(parsed.query)
        query = {key: values[-1] for key, values in query_values.items()}
        semantic_scholar_prefix = "/semantic-scholar/graph/v1/"
        if parsed.path.startswith(semantic_scholar_prefix):
            payload = json.dumps(
                {
                    "path": parsed.path[len(semantic_scholar_prefix) :],
                    "query": query,
                },
                separators=(",", ":"),
            ).encode()
            self._forward_semantic_scholar(payload)
            return
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
                "start_date": query.get("start_date"),
                "end_date": query.get("end_date"),
            }
        elif parsed.path in {"/api/v1/papers", "/api/v1/papers/"}:
            operation = "paper_list"
            arguments = {
                **{key: value for key, value in query.items() if key != "author"},
                "authors": query_values.get("author", []),
                "all_versions": query.get("latest_only") == "false",
                "include_resources": query.get("include_resources") == "true",
            }
        elif parsed.path == "/api/v1/papers/recent":
            operation = "paper_recent"
        elif parsed.path == "/api/v1/papers/trending":
            operation = "paper_trending"
        elif parsed.path in {"/api/v1/areas", "/api/v1/areas/"}:
            operation = "area_list"
        elif parsed.path in {
            "/api/v1/areas/with-tasks",
            "/api/v1/areas/with-tasks/",
        }:
            operation = "area_tasks"
        elif parsed.path in {"/api/v1/tasks", "/api/v1/tasks/"}:
            operation = "task_list"
        elif parsed.path in {"/api/v1/methods", "/api/v1/methods/"}:
            operation = "method_list"
        elif parsed.path in {"/api/v1/conferences", "/api/v1/conferences/"}:
            operation = "conference_list"
        elif parsed.path in {"/api/v1/organizations", "/api/v1/organizations/"}:
            operation = "organization_list"
            arguments = {"featured_only": query.get("featured_only") == "true"}
        elif parsed.path in {"/api/v1/frameworks", "/api/v1/frameworks/"}:
            operation = "framework_list"
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
                "order_dir": (
                    "desc" if (query.get("ordering") or "").startswith("-") else "asc"
                ),
            }
        elif match := _BENCHMARK_TRENDS.match(parsed.path):
            operation = "benchmark_trending"
            arguments = {
                "task": unquote(match.group(1)),
                "limit": query.get("limit", 100),
                "min_recent_papers": query.get("min_recent_papers", 0),
                "include_descendants": query.get("include_descendants") == "true",
                "is_open": query.get("is_open"),
            }
        elif match := _BENCHMARK_EVALUATIONS.match(parsed.path):
            operation = "benchmark_evaluations"
            arguments = {
                "dataset": unquote(match.group(1)),
                "page": query.get("page", 1),
                "page_size": query.get("page_size", 100),
                "is_open": query.get("is_open"),
            }
        elif _EVALUATIONS.match(parsed.path):
            if query.get("dataset_id") is not None:
                operation = "benchmark_evaluations"
                arguments = {
                    "dataset": query["dataset_id"],
                    "page": query.get("page", 1),
                    "page_size": query.get("page_size", 100),
                    "is_open": query.get("is_open"),
                    "max_parameters_exclusive": query.get("max_parameters_exclusive"),
                }
            else:
                operation = "paper_evaluations"
                arguments = {
                    "paper": query.get("paper_id"),
                    "page": query.get("page", 1),
                    "page_size": query.get("page_size", 100),
                    "ordering": query.get("ordering", "-benchmark_popularity"),
                }
        elif match := _TASK_PAGE.match(parsed.path):
            operation = "task_page"
            arguments = {
                "task": unquote(match.group(1)),
                "is_open": query.get("is_open"),
            }
        elif match := _TASK_PAPERS.match(parsed.path):
            operation = "task_papers"
            arguments = {
                "task": unquote(match.group(1)),
                **query,
                "include_resources": query.get("include_resources") == "true",
                "all_versions": query.get("latest_only") == "false",
            }
        elif match := _TASK_DETAIL.match(parsed.path):
            operation = "task_detail"
            arguments = {"task": unquote(match.group(1))}
        elif match := _METHOD_DETAIL.match(parsed.path):
            operation = "method_detail"
            arguments = {"method": unquote(match.group(1))}
        elif match := _CONFERENCE_DETAIL.match(parsed.path):
            operation = "conference_detail"
            arguments = {"conference": unquote(match.group(1))}
        elif match := _ORGANIZATION_DETAIL.match(parsed.path):
            operation = "organization_detail"
            arguments = {"organization": unquote(match.group(1))}
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
        payload = json.dumps(
            {"operation": operation, "arguments": arguments}, separators=(",", ":")
        ).encode()
        active = STATE.begin_request()
        connection = self._connection()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/catalog",
                body=payload,
                headers=_gateway_headers(active=active),
            )
            response = connection.getresponse()
            raw = response.read(2 * 1024 * 1024)
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
            reusable = _response_reusable(response)
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()


class _CertificateAuthority:
    SANDBOX_LIFETIME = timedelta(hours=24)
    VALIDITY_MARGIN = timedelta(hours=1)

    def __init__(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="pwc-webfetch-", dir="/var/empty/pwc-broker"
        )
        self.directory = Path(self.temporary_directory.name)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        self.not_valid_after = now + self.SANDBOX_LIFETIME + self.VALIDITY_MARGIN
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "PwC WebFetch Ephemeral CA")]
        )
        self.certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(self.not_valid_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(self.key, hashes.SHA256())
        )
        PROXY_CA_PATH.write_bytes(
            self.certificate.public_bytes(serialization.Encoding.PEM)
        )
        PROXY_CA_PATH.chmod(0o644)
        self.contexts: dict[str, ssl.SSLContext] = {}

    def context(self, host: str) -> ssl.SSLContext:
        if host in self.contexts:
            return self.contexts[host]
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(self.not_valid_after)
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False
            )
            .sign(self.key, hashes.SHA256())
        )
        stem = str(len(self.contexts))
        cert_path = self.directory / f"{stem}.crt"
        key_path = self.directory / f"{stem}.key"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert_path.chmod(0o600)
        key_path.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        self.contexts[host] = context
        return context


CERTIFICATES: _CertificateAuthority | None = None


class OriginHandler(BaseHTTPRequestHandler):
    server_version = "pwc-webfetch-proxy/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        if not STATE.active():
            self.send_error(403)
            return
        host = str(getattr(self.server, "target_host", ""))
        requested_host = (self.headers.get("Host") or "").partition(":")[0].lower()
        path = urlsplit(self.path).path
        if (
            host != "api.anthropic.com"
            or requested_host != host
            or path != "/v1/messages"
            or self.path.startswith(("http://", "https://"))
        ):
            self.send_error(403)
            return
        length = min(int(self.headers.get("Content-Length", "0")), 512 * 1024)
        body = self.rfile.read(length)
        active = STATE.begin_request()
        connection = GATEWAY_CONNECTIONS.acquire()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/v1/messages",
                body=body,
                headers={
                    **_gateway_headers(
                        active=active,
                        content_type=self.headers.get(
                            "Content-Type", "application/json"
                        ),
                    ),
                    "Accept": self.headers.get("Accept", "application/json"),
                },
            )
            response = connection.getresponse()
            self.send_response(response.status)
            if content_type := response.getheader("Content-Type"):
                self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
            reusable = _response_reusable(response)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()

    def do_GET(self) -> None:
        if not STATE.active():
            self.send_error(403)
            return
        host = str(getattr(self.server, "target_host", ""))
        requested_host = (self.headers.get("Host") or "").partition(":")[0].lower()
        if (
            not host
            or requested_host != host
            or self.path.startswith(("http://", "https://"))
        ):
            self.send_error(403)
            return
        body = json.dumps(
            {"url": f"https://{host}{self.path}"}, separators=(",", ":")
        ).encode()
        url = json.loads(body)["url"]
        if not _consume_proxy_url(url):
            self.send_error(403)
            return
        active = STATE.begin_request()
        connection = GATEWAY_CONNECTIONS.acquire()
        reusable = False
        try:
            prefix = UPSTREAM.path.rstrip("/")
            connection.request(
                "POST",
                f"{prefix}/web-fetch",
                body=body,
                headers=_gateway_headers(active=active),
            )
            response = connection.getresponse()
            self.send_response(response.status)
            for header in ("Content-Type", "Content-Length"):
                if value := response.getheader(header):
                    self.send_header(header, value)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
            reusable = _response_reusable(response)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            GATEWAY_CONNECTIONS.release(connection, reusable=reusable)
            STATE.finish_request()


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "pwc-webfetch-connect/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_CONNECT(self) -> None:
        try:
            parsed = urlsplit(f"//{self.path}")
            host = parsed.hostname
            if (
                not host
                or not host.isascii()
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError
        except ValueError:
            self.send_error(400)
            return
        assert CERTIFICATES is not None
        self.send_response(200, "Connection Established")
        self.end_headers()
        try:
            connection = CERTIFICATES.context(host.lower()).wrap_socket(
                self.connection, server_side=True
            )
            server = type("OriginServer", (), {"target_host": host.lower()})()
            OriginHandler(connection, self.client_address, server)
        except (OSError, ssl.SSLError):
            return


class BrokerControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            payload = json.loads(self.rfile.readline(16 * 1024))
            operation = payload.pop("operation")
            if operation == "install":
                STATE.install(payload)
            elif operation == "clear":
                if set(payload) != {"session_id", "turn_id"}:
                    raise RuntimeError("Invalid broker clear request")
                STATE.clear(
                    session_id=str(payload["session_id"]),
                    turn_id=str(payload["turn_id"]),
                )
            elif operation == "status":
                if payload:
                    raise RuntimeError("Invalid broker status request")
            else:
                raise RuntimeError("Invalid broker operation")
            response = {"ok": True, "active": STATE.active()}
        except Exception:  # noqa: BLE001 - the credential control plane fails closed
            response = {"ok": False, "code": "broker_control_rejected"}
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")


class BrokerControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def main() -> int:
    global CERTIFICATES
    CERTIFICATES = _CertificateAuthority()
    broker = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    proxy = ThreadingHTTPServer(("127.0.0.1", 8766), ProxyHandler)
    CONTROL_SOCKET.unlink(missing_ok=True)
    control = BrokerControlServer(str(CONTROL_SOCKET), BrokerControlHandler)
    CONTROL_SOCKET.chmod(0o600)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    threading.Thread(target=control.serve_forever, daemon=True).start()
    try:
        broker.serve_forever()
    finally:
        GATEWAY_CONNECTIONS.close()
        control.shutdown()
        CONTROL_SOCKET.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
