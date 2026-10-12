"""Sandbox broker capability, gateway forwarding, and catalog routing contracts."""

from __future__ import annotations

import importlib
import json
import os
import sys
import uuid
from datetime import timedelta
from io import BytesIO

import pytest


def _import_broker(monkeypatch):
    read_fd, write_fd = os.pipe()
    try:
        os.write(
            write_fd,
            json.dumps(
                {
                    "capability": "test-capability",
                    "gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
                    "session_id": str(uuid.uuid4()),
                    "turn_id": str(uuid.uuid4()),
                    "proxy_token": "test-proxy-token",
                }
            ).encode(),
        )
    finally:
        os.close(write_fd)
    monkeypatch.setenv("PWC_BROKER_CONFIG_FD", str(read_fd))
    sys.modules.pop("backend.chat_sandbox_worker.broker", None)
    return importlib.import_module("backend.chat_sandbox_worker.broker")


def test_broker_accepts_claude_messages_beta_query(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Request:
        path = "/v1/messages?beta=true"
        headers = {"Content-Length": "2", "Content-Type": "application/json"}
        rfile = BytesIO(b"{}")
        forwarded: list[tuple[str, bytes]] = []
        error: int | None = None

        def _forward(self, path, body, **_kwargs):
            self.forwarded.append((path, body))

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.Handler.do_POST(request)

    assert request.forwarded == [("v1/messages", b"{}")]
    assert request.error is None


def test_broker_allows_only_native_responses_path_for_direct_openai(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Request:
        path = "/v1/responses"
        headers = {"Content-Length": "2", "Content-Type": "application/json"}
        rfile = BytesIO(b"{}")
        forwarded: list[tuple[str, bytes, dict]] = []
        error: int | None = None

        def _forward(self, path, body, **kwargs):
            self.forwarded.append((path, body, kwargs))

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.Handler.do_POST(request)
    assert request.forwarded == [
        (
            "v1/messages",
            b"{}",
            {
                "content_type": "application/json",
                "accept": "application/json",
                "extra_headers": {"X-PWC-Provider-Protocol": "openai-responses"},
            },
        )
    ]
    assert request.error is None

    request.path = "/v1/chat/completions"
    broker.Handler.do_POST(request)
    assert request.error == 404


@pytest.mark.parametrize("path", ["/v1/messages", "/v1/responses"])
def test_broker_forwards_large_model_requests_and_rejects_over_limit(monkeypatch, path):
    broker = _import_broker(monkeypatch)
    body = b'{"input":"' + b"evidence " * 100_000 + b'"}'

    class Request:
        forwarded = None
        error = None

        def _forward(self, path, body, **kwargs):
            self.forwarded = body

        def send_error(self, status):
            self.error = status

    request = Request()
    request.path = path
    request.headers = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
    }
    request.rfile = BytesIO(body)
    broker.Handler.do_POST(request)
    assert request.forwarded == body
    assert request.error is None
    request.forwarded = None
    request.headers["Content-Length"] = str(broker.MODEL_REQUEST_MAX_BYTES + 1)
    request.rfile = BytesIO(b"")
    broker.Handler.do_POST(request)
    assert request.forwarded is None
    assert request.error == 413


def test_broker_certificates_outlive_the_persistent_sandbox(monkeypatch, tmp_path):
    broker = _import_broker(monkeypatch)
    ca_path = tmp_path / "pwc-webfetch-ca.pem"
    monkeypatch.setattr(broker, "PROXY_CA_PATH", ca_path)

    authority = broker._CertificateAuthority()
    authority.context("research.meta.ai")

    ca = broker.x509.load_pem_x509_certificate(ca_path.read_bytes())
    leaf = broker.x509.load_pem_x509_certificate(
        (authority.directory / "0.crt").read_bytes()
    )
    sandbox_expires_at = ca.not_valid_before_utc + timedelta(hours=24, minutes=1)

    assert ca.not_valid_after_utc > sandbox_expires_at
    assert leaf.not_valid_after_utc == ca.not_valid_after_utc


def test_broker_reuses_recent_gateway_connection_and_discards_old_one(monkeypatch):
    broker = _import_broker(monkeypatch)
    created = []

    class Connection:
        def __init__(self):
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    now = 100.0
    monkeypatch.setattr(broker, "monotonic", lambda: now)
    pool = broker.GatewayConnectionPool(
        Connection,
        max_size=1,
        max_idle_seconds=30,
    )

    first = pool.acquire()
    pool.release(first, reusable=True)
    assert pool.acquire() is first

    pool.release(first, reusable=True)
    now = 131.0
    second = pool.acquire()
    assert first.closed is True
    assert second is not first
    assert len(created) == 2


def test_broker_discards_incomplete_gateway_connection(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Connection:
        closed = False

        def close(self):
            self.closed = True

    pool = broker.GatewayConnectionPool(
        Connection,
        max_size=1,
        max_idle_seconds=30,
    )
    connection = pool.acquire()
    pool.release(connection, reusable=False)

    assert connection.closed is True
    assert pool.acquire() is not connection


def test_broker_capability_rotation_rejects_stale_and_cross_turn_clear(monkeypatch):
    broker = _import_broker(monkeypatch)
    state = broker.BrokerState(
        {"capability": "old", "session_id": "session", "turn_id": "turn-1"}
    )

    assert state.current()["capability"] == "old"
    with pytest.raises(RuntimeError, match="already installed"):
        state.install(
            {"capability": "new", "session_id": "session", "turn_id": "turn-2"}
        )
    with pytest.raises(RuntimeError, match="correlation"):
        state.clear(
            session_id="session",
            turn_id="turn-2",
            quiet_seconds=0,
        )

    state.clear(session_id="session", turn_id="turn-1", quiet_seconds=0)
    with pytest.raises(PermissionError):
        state.current()
    state.install({"capability": "new", "session_id": "session", "turn_id": "turn-2"})
    assert state.current()["capability"] == "new"


def test_broker_gateway_headers_include_external_turn_fence(monkeypatch):
    broker = _import_broker(monkeypatch)
    state = broker.BrokerState({})
    state.install(
        {
            "capability": "capability",
            "session_id": "session",
            "turn_id": "turn",
            "turn_worker_id": "production-green-00",
            "turn_worker_generation": "4",
            "turn_lease_generation": "9",
        }
    )

    assert broker._gateway_headers(active=state.current()) == {
        "Authorization": "Bearer capability",
        "X-PWC-Session": "session",
        "X-PWC-Turn": "turn",
        "X-PWC-Turn-Worker-ID": "production-green-00",
        "X-PWC-Turn-Worker-Generation": "4",
        "X-PWC-Turn-Lease-Generation": "9",
        "Content-Type": "application/json",
    }


def test_broker_clear_waits_for_capability_requests(monkeypatch):
    broker = _import_broker(monkeypatch)
    state = broker.BrokerState(
        {"capability": "token", "session_id": "session", "turn_id": "turn"}
    )

    assert state.begin_request()["capability"] == "token"
    with pytest.raises(RuntimeError, match="drain timed out"):
        state.clear(
            session_id="session",
            turn_id="turn",
            quiet_seconds=0,
            timeout_seconds=0.01,
        )
    assert state.active()

    state.finish_request()
    state.clear(session_id="session", turn_id="turn", quiet_seconds=0)
    assert not state.active()


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/api/v1/areas/?page_size=500", "area_list"),
        ("/api/v1/areas/with-tasks/", "area_tasks"),
        ("/api/v1/tasks/?page_size=10", "task_list"),
        ("/api/v1/methods/?page_size=10", "method_list"),
        ("/api/v1/conferences/", "conference_list"),
        ("/api/v1/organizations/?featured_only=true", "organization_list"),
        ("/api/v1/frameworks/", "framework_list"),
        ("/api/v1/tasks/17", "task_detail"),
        ("/api/v1/tasks/17/page", "task_page"),
        ("/api/v1/tasks/17/papers?page_size=10", "task_papers"),
        ("/api/v1/methods/vision-transformer", "method_detail"),
        ("/api/v1/conferences/cvpr-2026", "conference_detail"),
        ("/api/v1/organizations/hugging-face", "organization_detail"),
    ],
)
def test_broker_routes_taxonomy_cli_reads_to_catalog(monkeypatch, path, operation):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def read(self, _size):
            return b'{"result":{"count":0,"results":[]}}'

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, request_path, body, headers):
            del headers
            self.requests.append((method, request_path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    monkeypatch.setattr(broker, "_connection", Connection)

    class Request:
        wfile = BytesIO()
        status = None

        def __init__(self):
            self.path = path

        def _connection(self):
            return Connection()

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.status = status

    request = Request()
    broker.Handler.do_GET(request)

    assert request.status == 200
    payload = json.loads(Connection.requests[-1][2])
    assert payload["operation"] == operation


def test_broker_routes_paper_evaluations_to_catalog(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def read(self, _size):
            return b'{"result":{"count":0,"results":[]}}'

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, request_path, body, headers):
            del headers
            self.requests.append((method, request_path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    class Request:
        path = (
            "/api/v1/evaluations/?page=2&page_size=100&paper_id=42"
            "&ordering=-benchmark_popularity"
        )
        wfile = BytesIO()
        status = None

        def _connection(self):
            return Connection()

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.status = status

    request = Request()
    broker.Handler.do_GET(request)

    assert request.status == 200
    payload = json.loads(Connection.requests[-1][2])
    assert payload == {
        "operation": "paper_evaluations",
        "arguments": {
            "paper": "42",
            "page": "2",
            "page_size": "100",
            "ordering": "-benchmark_popularity",
        },
    }


def test_broker_routes_parameter_filtered_benchmark_evaluations_to_catalog(
    monkeypatch,
):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def read(self, _size):
            return b'{"result":{"count":0,"results":[]}}'

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, request_path, body, headers):
            del headers
            self.requests.append((method, request_path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    class Request:
        path = (
            "/api/v1/evaluations/?page=1&page_size=100&dataset_id=124"
            "&ordering=best_rank&max_parameters_exclusive=1000000001"
        )
        wfile = BytesIO()
        status = None

        def _connection(self):
            return Connection()

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.status = status

    request = Request()
    broker.Handler.do_GET(request)

    assert request.status == 200
    payload = json.loads(Connection.requests[-1][2])
    assert payload == {
        "operation": "benchmark_evaluations",
        "arguments": {
            "dataset": "124",
            "page": "1",
            "page_size": "100",
            "is_open": None,
            "max_parameters_exclusive": "1000000001",
        },
    }


def test_proxy_routes_only_claude_model_posts_to_gateway(monkeypatch):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def getheader(self, name):
            return "application/json" if name == "Content-Type" else None

        def read(self, _size):
            return b""

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, path, body, headers):
            del headers
            self.requests.append((method, path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    monkeypatch.setattr(broker, "_connection", Connection)

    class Request:
        path = "/v1/messages?beta=true"
        headers = {
            "Host": "api.anthropic.com",
            "Content-Length": "2",
            "Content-Type": "application/json",
        }
        rfile = BytesIO(b"{}")
        wfile = BytesIO()
        server = type("Server", (), {"target_host": "api.anthropic.com"})()
        error: int | None = None

        def send_response(self, status):
            assert status == 200

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.OriginHandler.do_POST(request)

    assert Connection.requests == [
        (
            "POST",
            "/api/internal/chat-gateway/v1/messages",
            b"{}",
        )
    ]
    assert request.error is None

    request.path = "/v1/complete"
    broker.OriginHandler.do_POST(request)
    assert request.error == 403


@pytest.mark.parametrize(
    ("path", "expected_operation"),
    [
        (
            "/api/v1/papers/search?q=date+filtering&page=2&page_size=15&start_date=2026-08-01&end_date=2026-08-21",
            "search",
        ),
        (
            "/api/v1/papers/?start_date=2026-08-01&end_date=2026-08-21"
            "&author=Kaiming+He&author=%40yilundu",
            "paper_list",
        ),
    ],
)
def test_broker_forwards_paper_date_ranges_to_the_catalog(
    monkeypatch, path, expected_operation
):
    broker = _import_broker(monkeypatch)

    class Response:
        status = 200

        def read(self, _size):
            return b'{"result":{"count":0,"results":[]}}'

    class Connection:
        requests: list[tuple[str, str, bytes]] = []

        def request(self, method, request_path, body, headers):
            del headers
            self.requests.append((method, request_path, body))

        def getresponse(self):
            return Response()

        def close(self):
            return

    monkeypatch.setattr(broker, "_connection", Connection)

    class Request:
        wfile = BytesIO()
        status = None

        def __init__(self):
            self.path = path

        def _connection(self):
            return Connection()

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return

        def end_headers(self):
            return

        def send_error(self, status):
            self.status = status

    request = Request()
    broker.Handler.do_GET(request)

    payload = json.loads(Connection.requests[-1][2])
    assert request.status == 200
    assert payload["operation"] == expected_operation
    assert payload["arguments"]["start_date"] == "2026-08-01"
    assert payload["arguments"]["end_date"] == "2026-08-21"
    if expected_operation == "paper_list":
        assert payload["arguments"]["authors"] == ["Kaiming He", "@yilundu"]
