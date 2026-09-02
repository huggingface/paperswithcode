from __future__ import annotations

import asyncio
import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    MirrorErrorMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi import HTTPException

from backend.chat_execution_policy import (
    FINALIZER_MAX_TURNS,
    MAX_FETCHABLE_URLS,
    MAX_POSTER_PROVIDER_REQUESTS,
    MAX_PROVIDER_REQUESTS,
    bounded_url_seed,
    effective_tool_rounds,
    validate_url_seed,
)
from backend.chat_gateway_app import (
    MAX_POSTER_PROVIDER_TURN_TOKENS,
    MAX_PROVIDER_OUTPUT_TOKENS,
    MAX_PROVIDER_TURN_TOKENS,
    CatalogRequest,
    PaperCommandRequest,
    _output_tokens_allowed,
    _provider_turn_limits,
    catalog,
    paper_command,
)
from backend.chat_sandbox_worker import (
    agent,
    control_daemon,
    control_websocket,
    publish_image,
    supervisor,
)
from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    CHAT_SANDBOX_REGION,
    CONTROL_PORT,
    IMAGE_PUBLISH_NAME,
    MODAL_APP_NAME,
    MODAL_IMAGE_ID,
    PRODUCTION_MODAL_IMAGE_ID,
    PWC_CLI_VERSION,
    WORKER_CONTRACT_VERSION,
)
from backend.chat_sandbox_worker.prompt import render, sha256
from backend.chat_sandbox_worker.protocol import (
    MAX_RUN_PROMPT_BYTES,
    ProtocolError,
    WorkerEventValidator,
    artifact_events_from_output,
    paper_events_from_output,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.render_method_catalog import (
    render as render_method_catalog,
)
from backend.chat_sandbox_worker.render_task_catalog import (
    render as render_task_catalog,
)
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter as WorkerSDKAdapter
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output
from backend.config import Settings
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, sse_event
from backend.models.database import ChatSession, ChatTurnCapability
from backend.scripts import qualify_chat_sandbox, qualify_chat_soak
from backend.scripts.qualify_chat_sandbox import (
    QualificationRunner,
    Sample,
    merge_release_settings,
    summarize,
)
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
    _digest,
)
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.catalog_errors import CatalogNotFoundError
from backend.services.chat_sandbox_service import (
    RunningWorker,
    SandboxSessionManager,
    WorkerClaim,
    WorkspaceSnapshotProvider,
    create_isolated_sandbox,
    resolve_modal_image,
)
from backend.services.chat_sandbox_worker_transport import WorkerTurnExecution
from backend.services.chat_session_service import detect_poster_intent
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.services.chat_web_fetch_service import (
    ChatWebFetchError,
    _arxiv_identifier,
    _public_addresses,
    _validate_body_size,
    _validate_origin_metadata,
    authorize_catalog_url,
    canonical_fetch_url,
)
from backend.utils.exceptions import PaperNotFoundError
from deploy.release import build_manifest


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


def test_persistent_assignment_rejects_generation_token_and_session_mismatch(
    monkeypatch,
):
    monkeypatch.setenv(
        "PWC_CHAT_GATEWAY_URL",
        "https://gateway.example.test/api/internal/chat-gateway",
    )
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    session_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    launch = {
        "capability": "capability",
        "gateway_url": os.environ["PWC_CHAT_GATEWAY_URL"],
        "session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "assignment-a",
        "worker_generation": "generation-a",
        "agent_harness": "claude",
    }
    run = {
        "v": 1,
        "type": "run_turn",
        "request_id": str(uuid.uuid4()),
        "chat_session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "assignment-a",
        "worker_generation": "generation-a",
        "agent_harness": "claude",
    }

    assert control_daemon._validate_assignment(
        launch,
        run,
        assigned_session_id=None,
        assigned_agent_harness=None,
    ) == (session_id, "claude")
    with pytest.raises(RuntimeError, match="generation mismatch"):
        control_daemon._validate_assignment(
            {**launch, "worker_generation": "generation-b"},
            run,
            assigned_session_id=None,
            assigned_agent_harness=None,
        )
    with pytest.raises(RuntimeError, match="Invalid persistent run frame"):
        control_daemon._validate_assignment(
            launch,
            {**run, "assignment_token": "assignment-b"},
            assigned_session_id=None,
            assigned_agent_harness=None,
        )
    with pytest.raises(RuntimeError, match="session ownership mismatch"):
        control_daemon._validate_assignment(
            launch,
            run,
            assigned_session_id=str(uuid.uuid4()),
            assigned_agent_harness=None,
        )


def test_prewarmed_pi_assignment_rejects_harness_model_and_reasoning_mismatch(
    monkeypatch,
):
    monkeypatch.setenv("PWC_CHAT_GATEWAY_URL", "https://gateway.example.test")
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    monkeypatch.setenv("PWC_CHAT_PI_PREWARM_ENABLED", "true")
    monkeypatch.setenv("PWC_CHAT_PI_PREWARM_MODEL", "deepseek/profile")
    monkeypatch.setenv("PWC_CHAT_PI_PREWARM_REASONING_EFFORT", "low")
    session_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    launch = {
        "capability": "capability",
        "gateway_url": os.environ["PWC_CHAT_GATEWAY_URL"],
        "session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "assignment-a",
        "worker_generation": "generation-a",
        "agent_harness": "pi",
    }
    run = {
        "v": 1,
        "type": "run_turn",
        "request_id": str(uuid.uuid4()),
        "chat_session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "assignment-a",
        "worker_generation": "generation-a",
        "agent_harness": "pi",
        "model": "deepseek/profile",
        "reasoning_effort": "low",
    }

    assert control_daemon._validate_assignment(
        launch, run, assigned_session_id=None, assigned_agent_harness=None
    ) == (session_id, "pi")
    with pytest.raises(RuntimeError, match="incompatible harness"):
        control_daemon._validate_assignment(
            {**launch, "agent_harness": "claude"},
            {**run, "agent_harness": "claude"},
            assigned_session_id=None,
            assigned_agent_harness=None,
        )
    with pytest.raises(RuntimeError, match="incompatible model"):
        control_daemon._validate_assignment(
            launch,
            {**run, "model": "other"},
            assigned_session_id=None,
            assigned_agent_harness=None,
        )
    with pytest.raises(RuntimeError, match="incompatible reasoning"):
        control_daemon._validate_assignment(
            launch,
            {**run, "reasoning_effort": "high"},
            assigned_session_id=None,
            assigned_agent_harness=None,
        )


def test_persistent_health_probe_requires_idle_children_and_empty_broker(
    monkeypatch,
):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    monkeypatch.setattr(
        control_daemon,
        "_broker_control",
        lambda payload: (
            {"ok": True, "active": False}
            if payload == {"operation": "status"}
            else None
        ),
    )
    daemon_side, relay_side = socket.socketpair()
    request_id = f"health-{uuid.uuid4()}"
    relay_side.sendall(
        supervisor.SUPERVISOR_PREFIX
        + json.dumps(
            {
                "operation": "ping",
                "worker_generation": "generation-a",
                "request_id": request_id,
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    child = SimpleNamespace(poll=lambda: None)
    startup_metrics = {
        "broker_ready_ms": 10,
        "control_ready_ms": 20,
        "agent_spawn_ms": 21,
        "agent_startup_ready_ms": 30,
    }
    try:
        assert control_daemon._serve_turn(
            daemon_side,
            broker=child,
            agent=child,
            proxy_token="unused",
            assigned_session_id=None,
            assigned_agent_harness=None,
            startup_metrics=startup_metrics,
        ) == ("", "", child)
        assert decode_frame(relay_side.recv(4096)) == {
            "v": 1,
            "type": "worker_health",
            "request_id": request_id,
            "assigned": False,
            "agent_prestarted": True,
            "startup_metrics": startup_metrics,
        }
    finally:
        daemon_side.close()
        relay_side.close()


def test_abandoned_persistent_health_probe_does_not_kill_daemon(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    monkeypatch.setattr(
        control_daemon,
        "_broker_control",
        lambda payload: {"ok": True, "active": False},
    )
    daemon_side, relay_side = socket.socketpair()
    relay_side.sendall(
        supervisor.SUPERVISOR_PREFIX
        + json.dumps(
            {
                "operation": "ping",
                "worker_generation": "generation-a",
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    relay_side.close()
    child = SimpleNamespace(poll=lambda: None)
    try:
        assert control_daemon._serve_turn(
            daemon_side,
            broker=child,
            agent=child,
            proxy_token="unused",
            assigned_session_id=None,
            assigned_agent_harness=None,
            startup_metrics={
                "broker_ready_ms": 10,
                "control_ready_ms": 20,
                "agent_spawn_ms": 21,
                "agent_startup_ready_ms": 30,
            },
        ) == ("", "", child)
    finally:
        daemon_side.close()


def test_idle_persistent_relay_accepts_backend_replacement(monkeypatch, tmp_path):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    monkeypatch.setattr(
        control_daemon,
        "_broker_control",
        lambda payload: (
            {"ok": True, "active": False}
            if payload == {"operation": "status"}
            else None
        ),
    )
    stopped = threading.Event()
    child = SimpleNamespace(poll=lambda: 1 if stopped.is_set() else None)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(tmp_path / "control.sock"))
    server.listen(2)
    errors: list[BaseException] = []
    startup_metrics = {
        "broker_ready_ms": 10,
        "control_ready_ms": 20,
        "agent_spawn_ms": None,
        "agent_startup_ready_ms": None,
    }

    def serve():
        try:
            control_daemon._serve_connections(
                server,
                broker=child,
                proxy_token="unused",
                startup_metrics=startup_metrics,
                daemon_started=control_daemon.time.monotonic(),
            )
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    first = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        first.connect(str(tmp_path / "control.sock"))
        second.connect(str(tmp_path / "control.sock"))
        request_id = f"health-{uuid.uuid4()}"
        second.sendall(
            supervisor.SUPERVISOR_PREFIX
            + json.dumps(
                {
                    "operation": "ping",
                    "worker_generation": "generation-a",
                    "request_id": request_id,
                },
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        second.settimeout(2)
        assert decode_frame(second.recv(4096)) == {
            "v": 1,
            "type": "worker_health",
            "request_id": request_id,
            "assigned": False,
            "agent_prestarted": False,
            "startup_metrics": startup_metrics,
        }
        first.settimeout(2)
        assert first.recv(1) == b""
    finally:
        stopped.set()
        first.close()
        second.close()
        thread.join(timeout=3)
        server.close()
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_persistent_control_reports_content_free_failure_stage(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")
    monkeypatch.setenv("PWC_CHAT_GATEWAY_URL", "https://gateway.invalid")
    request_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    turn_id = str(uuid.uuid4())
    launch = {
        "capability": "opaque-capability",
        "gateway_url": "https://gateway.invalid",
        "session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "opaque-assignment",
        "worker_generation": "generation-a",
        "agent_harness": "claude",
    }
    run = {
        "v": 1,
        "type": "run_turn",
        "request_id": request_id,
        "chat_session_id": session_id,
        "turn_id": turn_id,
        "assignment_token": "opaque-assignment",
        "worker_generation": "generation-a",
        "agent_harness": "claude",
    }
    daemon_side, relay_side = socket.socketpair()
    relay_side.sendall(
        supervisor.SUPERVISOR_PREFIX
        + json.dumps(launch, separators=(",", ":")).encode()
        + b"\n"
        + encode_frame(run)
    )
    read_fd, write_fd = os.pipe()
    agent_stdout = os.fdopen(read_fd, "rb", buffering=0)
    os.write(
        write_fd,
        encode_frame(
            {
                "v": 1,
                "type": "worker_done",
                "request_id": request_id,
                "status": "complete",
            }
        ),
    )
    control_operations: list[str] = []

    def broker_control(payload):
        control_operations.append(payload["operation"])
        if payload["operation"] == "clear":
            raise RuntimeError("sensitive provider detail")
        return {"ok": True}

    monkeypatch.setattr(control_daemon, "_broker_control", broker_control)
    child = SimpleNamespace(
        poll=lambda: None,
        stdin=BytesIO(),
        stdout=agent_stdout,
    )
    try:
        with pytest.raises(RuntimeError, match="sensitive provider detail"):
            control_daemon._serve_turn(
                daemon_side,
                broker=child,
                agent=child,
                proxy_token="unused",
                assigned_session_id=None,
                assigned_agent_harness=None,
                startup_metrics={
                    "broker_ready_ms": 10,
                    "control_ready_ms": 20,
                    "agent_spawn_ms": None,
                    "agent_startup_ready_ms": None,
                },
            )
        failure = decode_frame(relay_side.recv(4096))
        assert failure == {
            "v": 1,
            "type": "_control_failure",
            "request_id": request_id,
            "stage": "broker_clear",
            "error_class": "RuntimeError",
        }
        assert "sensitive" not in json.dumps(failure)
        assert control_operations == ["install", "clear", "clear"]
    finally:
        os.close(write_fd)
        agent_stdout.close()
        daemon_side.close()
        relay_side.close()


def test_worker_mirror_error_preserves_bounded_diagnostic_context():
    key = {
        "project_key": "-workspace",
        "session_id": str(uuid.uuid4()),
    }

    async def messages():
        yield MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            key=key,
            error="diagnostic-" + ("x" * 600),
        )

    async def collect():
        settings = agent.WorkerSettings.from_environment()
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=agent.WorkerToolHooks(settings),
                adapter=WorkerSDKAdapter(show_reasoning=False),
            )
        ]

    assert asyncio.run(collect()) == [
        {
            "v": 1,
            "type": "_mirror_error",
            "request_id": "request-1",
            "key": key,
            "error": ("diagnostic-" + ("x" * 600))[:500],
        }
    ]


def test_persistent_agent_reconnects_client_to_apply_model_metadata(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))
            self._query = SimpleNamespace(
                _transcript_mirror_batcher=SimpleNamespace(
                    _flush_task=SimpleNamespace(wait=self.wait_for_flush),
                    flush=self.flush,
                )
            )

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def query(self, prompt):
            calls.append(("query", prompt))

        async def receive_messages(self):
            yield ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="session-a",
            )

        async def flush(self):
            calls.append(("flush",))

        async def wait_for_flush(self):
            calls.append(("wait_for_flush",))

        async def set_model(self, model):
            calls.append(("model", model))

        async def disconnect(self):
            calls.append(("disconnect",))

        async def interrupt(self):
            calls.append(("interrupt",))

    async def adapted(messages, *, request_id, **_kwargs):
        async for _message in messages:
            pass
        yield {"v": 1, "type": "done", "request_id": request_id}

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    monkeypatch.setattr(agent, "_adapt_messages", adapted)
    settings = agent.WorkerSettings.from_environment()
    worker = agent.PersistentAgent(settings)

    async def run():
        first = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "first",
                    "model": "model-a",
                    "resume": "session-a",
                }
            )
        ]
        second = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-2",
                    "prompt": "second",
                    "model": "model-b",
                    "resume": "session-a",
                }
            )
        ]
        await worker.close()
        return first, second

    first, second = asyncio.run(run())
    assert [event["type"] for event in first] == [
        "workspace_ready",
        "_execution_telemetry",
        "done",
    ]
    assert [event["type"] for event in second] == [
        "workspace_ready",
        "_execution_telemetry",
        "done",
    ]
    assert [call[0] for call in calls].count("init") == 2
    assert ("model", "model-b") not in calls
    assert calls.count(("connect", None)) == 2
    assert calls.count(("wait_for_flush",)) == 2
    assert calls.count(("flush",)) == 2
    assert calls[-1] == ("disconnect",)


def test_persistent_agent_recovers_max_turns_with_tool_free_same_session(monkeypatch):
    created = []
    monkeypatch.setattr(
        agent, "GUIDE", Path(agent.__file__).with_name("PWC_CLI_SKILL.md")
    )

    class Client:
        def __init__(self, options):
            self.options = options
            created.append(self)
            self._query = SimpleNamespace(
                _transcript_mirror_batcher=SimpleNamespace(
                    _flush_task=SimpleNamespace(wait=self.wait), flush=self.flush
                )
            )

        async def connect(self, prompt):
            return None

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_messages(self):
            if len(created) == 1:
                yield ResultMessage(
                    subtype="error_max_turns",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=True,
                    num_turns=9,
                    session_id="session-a",
                )
            else:
                yield AssistantMessage(
                    model="test", content=[TextBlock(text="Recovered answer")]
                )
                yield ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id="session-a",
                )

        async def wait(self):
            return None

        async def flush(self):
            return None

        async def disconnect(self):
            return None

        async def interrupt(self):
            return None

        async def set_model(self, _model):
            return None

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def collect():
        events = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "research",
                    "model": "model-a",
                    "fetchable_urls": [],
                }
            )
        ]
        await worker.close()
        return events

    events = asyncio.run(collect())
    assert len(created) == 2
    assert created[1].options.resume == "session-a"
    assert created[1].options.tools == []
    assert created[1].options.allowed_tools == []
    assert created[1].prompt == agent.FINALIZER_PROMPT
    assert [event["type"] for event in events] == [
        "workspace_ready",
        "_sdk_session",
        "usage",
        "answer_delta",
        "usage",
        "_execution_telemetry",
        "done",
    ]
    assert events[-1]["finish_reason"] == "success"


def test_persistent_agent_preflight_keeps_initialized_client(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.preflight("model-a")
        assert worker.client is not None
        await worker.connect(model="model-a", resume=None)
        await worker.close()

    asyncio.run(run())
    assert [call[0] for call in calls].count("init") == 1
    assert calls.count(("connect", None)) == 1
    assert calls[-1] == ("disconnect",)


def test_persistent_agent_preflight_reconnects_to_resume_session(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.preflight("model-a")
        await worker.connect(model="model-a", resume="session-a")
        await worker.close()

    asyncio.run(run())
    assert calls == [
        ("init", "model-a", None),
        ("connect", None),
        ("disconnect",),
        ("init", "model-a", "session-a"),
        ("connect", None),
        ("disconnect",),
    ]


def test_persistent_agent_reconnects_when_turn_metadata_changes(monkeypatch):
    created = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            self.options = options
            created.append(self)

        async def connect(self, prompt):
            return None

        async def disconnect(self):
            return None

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=False,
            hf_username="user-a",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-a",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 11),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 11),
            task_catalog_text="## Complete live task lookup index\n\n- `new` — New",
        )
        await worker.close()

    asyncio.run(run())

    assert len(created) == 5
    metadata = [
        client.options.system_prompt.rsplit("# Turn metadata", 1)[1]
        for client in created
    ]
    assert '"web_search_enabled":false' in metadata[0]
    assert '"web_search_enabled":true' in metadata[1]
    assert '"hf_username":"user-b"' in metadata[2]
    assert '"current_date_utc":"2026-08-11"' in metadata[3]
    assert "`new` — New" in created[4].options.system_prompt


def test_adapter_waits_for_late_mirror_before_terminal():
    async def messages():
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sdk-session",
            total_cost_usd=0,
            usage=None,
            result="done",
            structured_output=None,
        )
        yield MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            error="late mirror failure",
            key={"session_id": "sdk-session", "project_key": "workspace"},
        )

    async def run():
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=agent.WorkerToolHooks(agent.WorkerSettings.from_environment()),
                adapter=agent.SDKEventAdapter(show_reasoning=False),
            )
        ]

    events = asyncio.run(run())
    assert [event["type"] for event in events] == [
        "_sdk_session",
        "_mirror_error",
    ]
    assert events[-1]["error"] == "late mirror failure"


def test_worker_adapter_surfaces_hugging_face_billing_errors():
    adapter = WorkerSDKAdapter(show_reasoning=False)

    events = adapter.feed(
        AssistantMessage(model="test", content=[], error="billing_error")
    )

    assert events == [
        {
            "type": "error",
            "code": "hf_inference_billing_exhausted",
            "message": (
                "Hugging Face could not bill this request. Your included credits "
                "may be exhausted; enable or review pay-as-you-go billing in Settings."
            ),
        }
    ]


@pytest.mark.parametrize(
    ("provider_error", "code"),
    [
        ("authentication_failed", "hf_inference_credential_expired"),
        ("rate_limit", "provider_rate_limit"),
        ("server_error", "provider_unavailable"),
        ("unknown", "provider_error"),
    ],
)
def test_worker_adapter_keeps_provider_failures_distinct(provider_error, code):
    events = WorkerSDKAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error=provider_error)
    )

    assert events[0]["type"] == "error"
    assert events[0]["code"] == code


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [("error", "provider_error"), ("_mirror_error", "mirror_error")],
)
def test_worker_telemetry_classifies_terminal_failure(event_type, outcome):
    assert agent._failure_outcome({"type": event_type}) == outcome


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [("error", "provider_error"), ("_mirror_error", "mirror_error")],
)
def test_worker_stream_reports_terminal_failure_outcome(
    monkeypatch, event_type, outcome
):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    async def messages():
        if False:
            yield None

    async def adapted(_messages, *, request_id, **_kwargs):
        yield {"v": 1, "type": event_type, "request_id": request_id}

    monkeypatch.setattr(agent, "sdk_query", lambda **_kwargs: messages())
    monkeypatch.setattr(agent, "_adapt_messages", adapted)

    async def collect():
        return [
            event
            async for event in agent.stream_turn(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "Research this",
                    "model": "model-a",
                    "fetchable_urls": [],
                },
                agent.WorkerSettings.from_environment(),
            )
        ]

    events = asyncio.run(collect())
    assert events[-2]["type"] == "_execution_telemetry"
    assert events[-2]["finalizer_outcome"] == outcome
    assert events[-1]["type"] == event_type


def test_worker_adapter_deduplicates_late_completed_thinking_snapshot():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={"type": "message_start", "message": {}},
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Same plan"},
            },
        ),
        AssistantMessage(model="test", content=[]),
        AssistantMessage(
            model="test",
            content=[ThinkingBlock(thinking="Same plan", signature="sig")],
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {"type": "reasoning_start"},
        {"type": "reasoning_delta", "text": "Same plan"},
        {"type": "reasoning_end"},
    ]


def test_worker_adapter_closes_reasoning_before_luna_starts_next_message():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "First"},
            },
        ),
        StreamEvent(
            uuid="4", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="6",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Second"},
            },
        ),
        StreamEvent(
            uuid="7",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
    ]


def test_persistent_agent_accepts_resume_hint_before_sdk_session(monkeypatch):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, _options):
            pass

        async def connect(self, prompt):
            pass

        async def disconnect(self):
            pass

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.connect(model="model-a", resume="session-a")
        await worker.connect(model="model-a", resume="session-b")
        await worker.close()

    asyncio.run(run())


def test_persistent_agent_reconnects_when_durable_resume_moves_back(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())
    worker.client = Client(SimpleNamespace(resume="session-a"))
    worker.model = "model-a"
    worker._record_session_id("session-a")

    asyncio.run(worker.connect(model="model-a", resume="session-b"))

    assert worker.sdk_session_id is None
    assert calls[-3:] == [
        ("disconnect",),
        ("init", "session-b"),
        ("connect", None),
    ]


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


def test_supervisor_launch_read_does_not_consume_worker_frame():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"private-launch\nworker-frame\n")
        assert supervisor._readline_unbuffered(read_fd, 64) == b"private-launch\n"
        assert os.read(read_fd, 64) == b"worker-frame\n"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_gateway_accepts_configured_output_token_limit_and_rejects_larger():
    assert MAX_PROVIDER_OUTPUT_TOKENS == 8_000
    assert MAX_PROVIDER_TURN_TOKENS >= 8 * MAX_PROVIDER_OUTPUT_TOKENS
    assert _output_tokens_allowed(8_000)
    assert not _output_tokens_allowed(8_001)


def test_gateway_expands_model_budget_only_after_artifact_or_paper_grant():
    ordinary = SimpleNamespace(scopes=["model", "catalog"])
    artifact = SimpleNamespace(scopes=["model", "catalog", "artifact"])
    paper_available = SimpleNamespace(scopes=["model", "catalog", "paper"])
    paper_granted = SimpleNamespace(scopes=["model", "catalog", "paper", "paper_grant"])

    assert _provider_turn_limits(ordinary) == (
        MAX_PROVIDER_REQUESTS,
        MAX_PROVIDER_TURN_TOKENS,
    )
    assert _provider_turn_limits(artifact) == (
        MAX_POSTER_PROVIDER_REQUESTS,
        MAX_POSTER_PROVIDER_TURN_TOKENS,
    )
    assert _provider_turn_limits(paper_available) == _provider_turn_limits(ordinary)
    assert _provider_turn_limits(paper_granted) == _provider_turn_limits(artifact)
    assert MAX_POSTER_PROVIDER_REQUESTS >= 20 + 2
    assert MAX_POSTER_PROVIDER_TURN_TOKENS > MAX_PROVIDER_TURN_TOKENS


def test_worker_expands_output_budget_only_for_poster_mode():
    settings = agent.WorkerSettings()

    ordinary = agent.WorkerToolHooks(settings)
    poster = agent.WorkerToolHooks(settings, poster_mode=True)

    assert ordinary.budget.maximum_result_bytes == 24 * 1024
    assert ordinary.budget.maximum_turn_output_bytes == 96 * 1024
    assert poster.budget.maximum_result_bytes == 192 * 1024
    assert poster.budget.maximum_turn_output_bytes == 1024 * 1024


def test_paper_receipt_is_bounded_and_emits_a_typed_event():
    event = paper_events_from_output(
        '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )
    assert event == [
        {
            "type": "paper_artifact",
            "operation": "create",
            "activated": True,
            "paper": {"artifact_id": "paper-1", "title": "Draft"},
            "descriptor": {"artifact_id": "paper-1", "title": "Draft"},
        }
    ]
    validator = WorkerEventValidator()
    validator.accept(event[0])


def test_paper_draft_receipt_is_a_typed_event():
    event = paper_events_from_output(
        '@@PWC_PAPER@@{"operation":"draft","activated":false,"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )

    assert event is not None
    validator = WorkerEventValidator()
    validator.accept(event[0])
    assert event[0]["operation"] == "draft"


def test_worker_keeps_large_tool_evidence_out_of_public_events():
    event = agent._public_tool_result_event(
        {
            "type": "tool_result",
            "id": "large",
            "status": "success",
            "took_ms": 1,
            "content": [{"type": "text", "text": "x" * (64 * 1024)}],
            "metadata": {"output_truncated": False},
        }
    )

    assert len(event["content"][0]["text"].encode()) <= 24 * 1024
    assert event["content"][0]["truncated"] is True
    assert event["metadata"]["output_truncated"] is True


def test_gateway_catalog_returns_not_found_for_unknown_task(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def missing_task(*_args, **_kwargs):
        raise PaperNotFoundError(
            "Task with ID, slug, or name 'speech recognition' not found"
        )

    monkeypatch.setattr(ChatGatewayService, "catalog", missing_task)

    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(
                operation="benchmark_trending",
                arguments={"task": "speech recognition"},
            ),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == (
        "Task with ID, slug, or name 'speech recognition' not found"
    )


def test_gateway_catalog_maps_typed_not_found_errors(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def missing_catalog_entity(*_args, **_kwargs):
        raise CatalogNotFoundError("Method 'missing' not found")

    monkeypatch.setattr(ChatGatewayService, "catalog", missing_catalog_entity)

    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(operation="method_detail", arguments={"method": "missing"}),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            turn_fence=None,
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Method 'missing' not found"


@pytest.mark.parametrize("operation", ["draft", "repair"])
def test_gateway_paper_mutation_rejects_same_owner_artifact_from_another_chat(
    monkeypatch, operation: str
):
    session_id = uuid.uuid4()
    other_artifact_id = uuid.uuid4()
    current_artifact_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    calls: list[dict] = []

    class Descriptor:
        def __init__(self, artifact_id: uuid.UUID):
            self.artifact_id = artifact_id

        def model_dump(self, **_kwargs):
            return {"artifact_id": str(self.artifact_id)}

    class DB:
        def get(self, model, identifier):
            assert model is ChatSession
            assert identifier == session_id
            return SimpleNamespace(
                active_turn_id=turn_id,
                primary_paper_id=None,
                selected_model="gpt-5.6-luna@openai",
            )

        def rollback(self):
            pass

        def commit(self):
            pass

    def unexpected_mutation(**kwargs):
        calls.append(kwargs)
        if operation == "draft":
            return Descriptor(other_artifact_id)
        return SimpleNamespace(
            descriptor=Descriptor(other_artifact_id), repaired=False, exhausted=False
        )

    paper_service = SimpleNamespace(
        get_descriptor=lambda owner_id, requested_session_id: (
            Descriptor(current_artifact_id)
            if owner_id == "same-owner" and requested_session_id == session_id
            else None
        ),
        save_ai_version=unexpected_mutation,
        repair_failed_version=unexpected_mutation,
    )
    capability = SimpleNamespace(
        chat_session_id=session_id,
        turn_id=turn_id,
        scopes=["paper"],
        expires_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: capability
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._capability_owner",
        lambda *_args, **_kwargs: "same-owner",
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app.LatexPaperService", lambda *_args: paper_service
    )

    with pytest.raises(HTTPException) as exc_info:
        paper_command(
            PaperCommandRequest(
                operation=operation,
                artifact_id=other_artifact_id,
                expected_parent_version_id=parent_id,
            ),
            authorization="Bearer capability",
            x_pwc_session=str(session_id),
            x_pwc_turn=str(turn_id),
            db=DB(),
            settings=SimpleNamespace(
                chat_artifacts_enabled=True,
                chat_latex_paper_enabled=True,
                chat_latex_compiler_jobs_enabled=True,
                chat_latex_paper_timeout_seconds=600,
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "paper_missing"
    assert calls == []


def test_gateway_paper_read_uses_bounded_diskless_reader(monkeypatch):
    calls = []

    def read(paper, **options):
        calls.append((paper, options))
        return "# EoMT", True

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.read_paper_markdown_bounded", read
    )
    settings = SimpleNamespace(
        paper_markdown_hf_bucket_id="papers",
        hf_token="token",
    )

    result = ChatGatewayService(object(), settings).catalog(
        "paper_read", {"paper": "2503.19108"}
    )

    assert result == {"markdown": "# EoMT", "truncated": True}
    assert calls == [
        (
            "2503.19108",
            {"bucket_id": "papers", "token": "token", "max_bytes": 256 * 1024},
        )
    ]


def test_gateway_paper_list_forwards_every_advertised_catalog_filter(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_papers(self, **options):
            calls.append(options)
            return {"count": 0, "results": [], "applied_filters": options}

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_list",
        {
            "start_date": "2026-08-01",
            "end_date": "2026-08-21",
            "task": "Vision",
            "method": "Transformer",
            "conference": "CVPR 2026",
            "framework": "PyTorch",
            "organization": "Hugging Face",
            "authors": ["Kaiming He", "@yilundu"],
        },
    )

    assert result["count"] == 0
    assert calls[0]["start_date"].isoformat() == "2026-08-01"
    assert calls[0]["end_date"].isoformat() == "2026-08-21"
    assert {
        name: calls[0][name]
        for name in ("task", "method", "conference", "framework", "organization")
    } == {
        "task": "Vision",
        "method": "Transformer",
        "conference": "CVPR 2026",
        "framework": "PyTorch",
        "organization": "Hugging Face",
    }
    assert calls[0]["authors"] == ["Kaiming He", "@yilundu"]


def test_gateway_search_forwards_the_publication_date_range(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def search_papers_page(self, *args, **options):
            calls.append((args, options))
            return {"results": []}

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    ChatGatewayService("db", SimpleNamespace()).catalog(
        "search",
        {
            "query": "date filtering",
            "start_date": "2026-08-01",
            "end_date": "2026-08-21",
        },
    )

    assert calls[0][0] == ("date filtering", 1, 10)
    assert calls[0][1]["start_date"].isoformat() == "2026-08-01"
    assert calls[0][1]["end_date"].isoformat() == "2026-08-21"


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


def test_gateway_exposes_advertised_taxonomy_detail_operations(monkeypatch):
    class Tasks:
        def __init__(self, db):
            assert db == "db"

        def get_task_by_id(self, task):
            return {"kind": "task", "id": task}

        def get_task_by_slug(self, task):
            return {"kind": "task", "slug": task}

        def get_task_page(self, task, *, is_open):
            return {"kind": "task_page", "task": task, "is_open": is_open}

        def get_task_papers(self, task, **options):
            return {"kind": "task_papers", "task": task, "options": options}

    class Methods:
        def __init__(self, db):
            assert db == "db"

        def get_method_by_id(self, method):
            return {"kind": "method", "id": method}

        def get_method_by_name(self, method):
            return {"kind": "method", "name": method}

    class Conferences:
        def __init__(self, db):
            assert db == "db"

        def get_conference(self, conference):
            return {"kind": "conference", "slug": conference}

    class Organizations:
        def __init__(self, db):
            assert db == "db"

        def get_organizations(self, *, featured_only):
            return {"kind": "organizations", "featured_only": featured_only}

        def get_organization(self, organization):
            return {"kind": "organization", "slug": organization}

    class Frameworks:
        def __init__(self, db):
            assert db == "db"

        def get_catalog(self):
            return {"kind": "frameworks"}

    monkeypatch.setattr("backend.services.chat_gateway_service.TaskService", Tasks)
    monkeypatch.setattr("backend.services.chat_gateway_service.MethodService", Methods)
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.ConferenceService", Conferences
    )
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.OrganizationService", Organizations
    )
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.FrameworkService", Frameworks
    )
    gateway = ChatGatewayService("db", SimpleNamespace())

    assert gateway.catalog("task_detail", {"task": "17"})["id"] == "17"
    assert (
        gateway.catalog("task_page", {"task": "vision", "is_open": "true"})["is_open"]
        is True
    )
    assert gateway.catalog("task_papers", {"task": "vision"})["kind"] == "task_papers"
    assert (
        gateway.catalog("method_detail", {"method": "transformer"})["name"]
        == "transformer"
    )
    assert (
        gateway.catalog("conference_detail", {"conference": "cvpr-2026"})["slug"]
        == "cvpr-2026"
    )
    assert (
        gateway.catalog("organization_list", {"featured_only": True})["featured_only"]
        is True
    )
    assert (
        gateway.catalog("organization_detail", {"organization": "hugging-face"})["slug"]
        == "hugging-face"
    )
    assert gateway.catalog("framework_list", {}) == {"kind": "frameworks"}


def test_gateway_paper_info_includes_normalized_hf_artifacts(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_paper_by_id_or_arxiv(self, paper, include_resources):
            calls.append((paper, include_resources))
            return {
                "id": "7",
                "hf_models": ["https://huggingface.co/org/model-a"],
                "hf_datasets": [],
                "hf_spaces": [],
            }

        def get_linked_hf_artifact_urls(self, paper_id):
            assert paper_id == 7
            return {
                "hf_models": [
                    "https://huggingface.co/org/model-a",
                    "https://huggingface.co/org/model-b",
                ],
                "hf_datasets": ["https://huggingface.co/datasets/org/data"],
                "hf_spaces": [],
            }

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_info", {"paper": "2605.20613", "include_resources": True}
    )

    assert calls == [("2605.20613", True)]
    assert result["hf_models"] == [
        "https://huggingface.co/org/model-a",
        "https://huggingface.co/org/model-b",
    ]
    assert result["hf_datasets"] == ["https://huggingface.co/datasets/org/data"]


def test_gateway_paper_evaluations_uses_bounded_service_arguments(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_evaluations(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.EvaluationService", Service
    )

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_evaluations",
        {
            "paper": "42",
            "page": "2",
            "page_size": "500",
            "ordering": "-benchmark_popularity",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 2,
            "page_size": 100,
            "paper_id": 42,
            "order_by": "benchmark_popularity",
            "order_dir": "desc",
        }
    ]


def test_gateway_benchmark_evaluations_forwards_parameter_bound(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_evaluations(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.EvaluationService", Service
    )

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "benchmark_evaluations",
        {
            "dataset": "124",
            "page": "1",
            "page_size": "100",
            "max_parameters_exclusive": "1000000001",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 1,
            "page_size": 100,
            "dataset_id": 124,
            "is_open": None,
            "max_parameters_exclusive": 1_000_000_001,
            "order_by": "best_rank",
            "order_dir": "asc",
        }
    ]


def test_gateway_method_list_uses_bounded_service_arguments(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_methods(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr("backend.services.chat_gateway_service.MethodService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "method_list",
        {
            "page": "2",
            "page_size": "500",
            "area_id": "3",
            "introduced_year": "2020",
            "ordering": "-paper_count",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 2,
            "page_size": 500,
            "area_id": 3,
            "introduced_year": 2020,
            "order_by": "paper_count",
            "order_dir": "desc",
        }
    ]


def test_gateway_paper_read_returns_controlled_upstream_error(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def failed(*_args, **_kwargs):
        raise OSError("read-only cache failure")

    monkeypatch.setattr(ChatGatewayService, "catalog", failed)
    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(operation="paper_read", arguments={"paper": "2503.19108"}),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Paper Markdown could not be read"


def test_worker_adapter_assembles_streamed_tool_arguments():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Bash",
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"command":"pwc search on-device"}',
                },
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {
            "type": "tool_call",
            "id": "tool-1",
            "name": "Bash",
            "args": {"command": "pwc search on-device"},
        }
    ]


def test_worker_adapter_namespaces_reused_provider_tool_ids():
    hooks = agent.WorkerToolHooks(agent.WorkerSettings.from_environment())

    def tool_result(tool_id, text):
        return {
            "type": "tool_result",
            "id": tool_id,
            "status": "success",
            "took_ms": 1,
            "content": [{"type": "text", "text": text, "truncated": False}],
            "metadata": {"exit_code": 0, "output_truncated": False},
        }

    async def messages():
        yield AssistantMessage(
            model="test",
            content=[ToolUseBlock(id="Bash:0", name="Bash", input={})],
        )
        hooks.results["Bash:0"] = tool_result("Bash:0", "first")
        yield UserMessage(
            content=[ToolResultBlock(tool_use_id="Bash:0", content="first")]
        )
        yield AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="Bash:0", name="Bash", input={}),
                ToolUseBlock(id="Bash:1", name="Bash", input={}),
            ],
        )
        hooks.results["Bash:0"] = tool_result("Bash:0", "second")
        hooks.results["Bash:1"] = tool_result("Bash:1", "third")
        yield UserMessage(
            content=[
                ToolResultBlock(tool_use_id="Bash:0", content="second"),
                ToolResultBlock(tool_use_id="Bash:1", content="third"),
            ]
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="sdk-session",
            total_cost_usd=0,
            usage=None,
            result="done",
            structured_output=None,
        )

    async def run():
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request-1",
                hooks=hooks,
                adapter=agent.SDKEventAdapter(
                    show_reasoning=False, policy=agent._sdk_event_policy(hooks)
                ),
            )
        ]

    events = asyncio.run(run())
    tool_events = [
        event for event in events if event["type"] in {"tool_call", "tool_result"}
    ]
    assert [(event["type"], event["id"]) for event in tool_events] == [
        ("tool_call", "Bash:0"),
        ("tool_result", "Bash:0"),
        ("tool_call", "Bash:0#2"),
        ("tool_call", "Bash:1"),
        ("tool_result", "Bash:0#2"),
        ("tool_result", "Bash:1"),
    ]
    validator = WorkerEventValidator()
    for event in events:
        if event["type"] != "_sdk_session":
            validator.accept(event)
    validator.accept({"type": "worker_done", "status": "complete"})


@pytest.mark.parametrize("name", ["Bash", "Read", "Grep", "WebFetch", "pwc"])
def test_generic_tool_projection_and_event_are_v2_raw_text(name):
    block = DISPLAY_BLOCKS_ADAPTER.validate_python(
        [
            {
                "kind": "tool",
                "schema_version": 2,
                "id": "tool-1",
                "name": name,
                "args": {"command": "pwc search vision"},
                "status": "success",
                "took_ms": 25,
                "content": [
                    {"type": "text", "text": "id\ttitle\n1\tPaper", "truncated": False}
                ],
                "metadata": {"exit_code": 0, "output_truncated": False},
            }
        ]
    )[0]
    assert block.name == name
    assert b'"status":"success"' in sse_event(
        "tool_result",
        id="tool-1",
        status="success",
        took_ms=25,
        content=[{"type": "text", "text": "ok", "truncated": False}],
        metadata={"exit_code": 0, "output_truncated": False},
    )


def test_tool_budget_counts_parallel_calls_and_fifth_search_is_denied():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    for index in range(4):
        assert budget.authorize(
            f"tool-{index}", "Bash", {"command": f"pwc search query-{index}"}
        ).allowed
    denied = budget.authorize("tool-5", "Bash", {"command": "pwc search fifth"})
    assert not denied.allowed
    assert budget.calls == 4


def test_tool_budget_counts_s2_search_against_catalog_search_limit():
    budget = ToolBudget(
        maximum_calls=2,
        maximum_direct_searches=1,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize(
        "tool-1", "Bash", {"command": "s2 search transformers"}
    ).allowed
    assert not budget.authorize(
        "tool-2", "Bash", {"command": "pwc search transformers"}
    ).allowed


def test_worker_bash_hook_enables_fail_fast_pipeline_handling():
    hooks = agent.WorkerToolHooks(agent.WorkerSettings.from_environment())

    result = asyncio.run(
        hooks.pre(
            {"tool_name": "Bash", "tool_input": {"command": "pwc search test"}},
            "tool-1",
            None,
        )
    )

    updated = result["hookSpecificOutput"]["updatedInput"]
    assert updated["command"] == "set -eo pipefail\npwc search test"


def test_successful_shell_result_with_execution_limit_is_reclassified():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize("tool-1", "Bash", {"command": "pwc search test"}).allowed

    result = budget.result(
        "tool-1",
        'pwc: API request failed (429): {"detail":"Tool execution limit reached"}',
        status="success",
        exit_code=0,
    )

    assert result["status"] == "error"
    assert result["metadata"]["exit_code"] == 1
    assert budget.tooling_closed


def test_tool_budget_counts_parallel_batches_and_denies_seventh_round_in_full():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=12,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
        maximum_rounds=effective_tool_rounds(8),
    )
    call_count = 0
    for round_index, batch_size in enumerate((2, 2, 2, 2, 1, 1), start=1):
        ids = [f"r{round_index}-{item}" for item in range(batch_size)]
        budget.register_round(ids)
        for tool_id in ids:
            assert budget.authorize(
                tool_id, "Bash", {"command": "pwc tasks list"}
            ).allowed
            call_count += 1
    assert call_count == 10
    assert budget.tool_rounds_started == 6
    assert budget.tool_rounds_executed == 6

    denied_ids = ["r7-a", "r7-b"]
    budget.register_round(denied_ids)
    assert all(
        not budget.authorize(tool_id, "Bash", {"command": "pwc tasks list"}).allowed
        for tool_id in denied_ids
    )
    assert budget.calls == 10
    assert budget.tool_rounds_denied == 1
    assert budget.tooling_closed


def test_worker_tool_budget_counts_parallel_calls_as_one_round_then_sequential():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=12,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
        maximum_rounds=1,
    )

    for tool_id in ("parallel-a", "parallel-b"):
        budget.register_call(tool_id)
        assert budget.authorize(tool_id, "Bash", {"command": "pwc tasks list"}).allowed

    assert budget.tool_rounds_started == 1
    assert budget.tool_rounds_executed == 1
    for tool_id in ("parallel-a", "parallel-b"):
        budget.result(tool_id, "ok", status="success")

    budget.register_call("parallel-a")
    assert not budget.authorize(
        "parallel-a", "Bash", {"command": "pwc tasks list"}
    ).allowed
    assert budget.tool_rounds_started == 2
    assert budget.tool_rounds_executed == 1
    assert budget.tool_rounds_denied == 1


def test_fetchable_url_seed_is_strict_sorted_and_bounded():
    urls = sorted(f"https://example.com/{index}" for index in range(MAX_FETCHABLE_URLS))
    assert validate_url_seed(urls) == urls
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed([*urls, "https://example.com/overflow"])
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed(["https://127.0.0.1/private"])
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed(["https://example.com/b", "https://example.com/a"])


def test_fetchable_url_seed_stabilizes_punctuation_exposed_by_fragment_removal():
    urls = bounded_url_seed(["https://huggingface.co/moonshotai/Kimi-K3&gt;#"])

    assert urls == ["https://huggingface.co/moonshotai/Kimi-K3&gt"]
    assert validate_url_seed(urls) == urls


def test_worker_adapter_surfaces_recoverable_execution_limit_internally():
    events = WorkerSDKAdapter(show_reasoning=False).feed(
        ResultMessage(
            subtype="error_max_turns",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=9,
            session_id="session-a",
        )
    )
    assert [event["type"] for event in events] == ["usage", "_execution_limit"]


def test_worker_adapter_registers_complete_parallel_batch_before_returning_calls():
    batches = []
    adapter = WorkerSDKAdapter(show_reasoning=False, on_tool_batch=batches.append)
    events = adapter.feed(
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="a", name="Bash", input={"command": "one"}),
                ToolUseBlock(id="b", name="Read", input={"file_path": "/workspace/x"}),
            ],
        )
    )
    assert batches == [["a", "b"]]
    assert [event["id"] for event in events] == ["a", "b"]


def test_worker_finalizer_options_are_tool_free_and_single_turn(monkeypatch):
    monkeypatch.setattr(
        agent, "GUIDE", Path(agent.__file__).with_name("PWC_CLI_SKILL.md")
    )
    settings = agent.WorkerSettings.from_environment()
    hooks = agent.WorkerToolHooks(settings)
    options = agent._options(
        settings,
        hooks,
        model="model-a",
        resume="session-a",
        finalizing=True,
    )
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.mcp_servers == {}
    assert options.max_turns == FINALIZER_MAX_TURNS
    assert {"Bash", "Read", "Grep", "WebFetch", "mcp__web__search_web"} <= set(
        options.disallowed_tools
    )


def test_web_fetch_is_disabled_during_controlled_comparison():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    budget.observe_urls("Read https://example.com/paper and http://127.0.0.1/private")

    assert not budget.authorize(
        "fetch", "WebFetch", {"url": "https://arxiv.org/abs/2607.12345"}
    ).allowed
    assert not budget.authorize(
        "observed", "WebFetch", {"url": "https://example.com/paper"}
    ).allowed
    assert not budget.authorize(
        "unknown", "WebFetch", {"url": "https://example.com/unseen"}
    ).allowed
    assert not budget.authorize(
        "subdomain", "WebFetch", {"url": "https://export.arxiv.org/abs/2607.12345"}
    ).allowed
    assert not budget.authorize(
        "private", "WebFetch", {"url": "http://127.0.0.1/private"}
    ).allowed
    assert not budget.authorize(
        "http", "WebFetch", {"url": "http://arxiv.org/abs/2607.12345"}
    ).allowed


def test_tool_results_make_returned_urls_fetchable():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize("info", "Bash", {"command": "pwc paper info 1"}).allowed
    budget.result(
        "info",
        "Project page: https://example.com/project",
        status="success",
        exit_code=0,
    )

    assert not budget.authorize(
        "fetch", "WebFetch", {"url": "https://example.com/project"}
    ).allowed


def test_web_fetch_results_do_not_authorize_discovered_links():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    source = "https://arxiv.org/abs/2607.12345"
    budget.observe_urls(source)
    assert not budget.authorize("fetch", "WebFetch", {"url": source}).allowed
    budget.result(
        "fetch",
        "Discovered https://example.com/not-catalog-authorized",
        status="success",
    )
    assert not budget.authorize(
        "follow",
        "WebFetch",
        {"url": "https://example.com/not-catalog-authorized"},
    ).allowed


def test_catalog_web_fetch_url_normalization_and_arxiv_matching():
    assert (
        canonical_fetch_url("https://ARXIV.org:443/abs/2503.19108/#section")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert _arxiv_identifier("https://arxiv.org/pdf/2503.19108v2.pdf") == "2503.19108"
    assert _arxiv_identifier("https://arxiv.org/abs/2503.19108?download=1") is None
    for value in (
        "http://arxiv.org/abs/2503.19108",
        "https://user@arxiv.org/abs/2503.19108",
        "https://arxiv.org:444/abs/2503.19108",
    ):
        with pytest.raises(ChatWebFetchError):
            canonical_fetch_url(value)


def test_catalog_web_fetch_requires_existing_arxiv_or_exact_attached_url():
    class Result:
        def __init__(self, found):
            self.found = found

        def scalar_one(self):
            return self.found

    class DB:
        def __init__(self, *results):
            self.results = iter(results)

        def execute(self, _statement):
            return Result(next(self.results))

    assert (
        authorize_catalog_url(DB(True), "https://arxiv.org/abs/2503.19108")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert (
        authorize_catalog_url(DB(True), "https://github.com/org/repo")
        == "https://github.com/org/repo"
    )
    with pytest.raises(ChatWebFetchError, match="not linked"):
        authorize_catalog_url(DB(False), "https://arxiv.org/abs/2503.19108")
    with pytest.raises(ChatWebFetchError, match="not attached"):
        authorize_catalog_url(DB(False, False), "https://github.com/org/repo/issues")


def test_catalog_web_fetch_rejects_private_dns_redirects_and_unsupported_content(
    monkeypatch,
):
    class Loop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: Loop())
    with pytest.raises(ChatWebFetchError, match="private network"):
        asyncio.run(_public_addresses("example.com"))
    with pytest.raises(ChatWebFetchError, match="redirect"):
        _validate_origin_metadata(302, "text/html")
    with pytest.raises(ChatWebFetchError, match="Unsupported"):
        _validate_origin_metadata(200, "application/octet-stream")
    with pytest.raises(ChatWebFetchError, match="too large"):
        _validate_body_size(b"x" * (10 * 1024 * 1024 + 1))
    assert _validate_origin_metadata(200, "text/html; charset=utf-8") == "text/html"


def test_worker_disables_native_web_fetch_and_uses_supported_proxy_settings():
    source = Path(agent.__file__).read_text()
    assert 'else ["Bash", "Read"]' in source
    assert '"skipWebFetchPreflight": True' not in source
    assert '"HTTPS_PROXY": "http://127.0.0.1:8766"' in source
    assert '"NO_PROXY": "127.0.0.1,localhost"' in source
    assert '"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"' in source
    assert '"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"' in source


def test_system_prompt_prevents_unsupported_method_search_flags():
    prompt = render()

    assert "When comparing papers, prefer a Markdown table." in prompt
    assert (
        "Always favor native paper hyperlinks instead of arXiv links, unless the user "
        "explicitly asks for an arXiv link." in prompt
    )
    assert "use `--page-size`, never `--limit`" in prompt
    assert "This subcommand has no `--search` or `--limit` flag" in prompt
    assert "pwc method list --page-size 500 | rg -i -- 'QUERY'" in prompt
    assert "Never pipe `pwc paper info` or `pwc paper lineage list`" in prompt
    assert "Paper lineage follows the abstract" in prompt
    assert "Use complete output, or use `--json`" in prompt
    assert "start with `pwc` whether the family is open or closed" in prompt
    assert "Use `hf` first only when" in prompt
    assert "community-only result from one source is not enough evidence" in prompt
    assert "continue with another applicable catalog" in prompt
    assert "If a colloquial task name does not resolve exactly" in prompt
    assert "pwc task list --page-size 100 --flat" in prompt
    assert "retry with the canonical task slug" in prompt
    assert "names an unversioned model family" in prompt
    assert "official external release pages as\nfirst-class model evidence" in prompt
    assert (
        "pwc paper list --organization NAME --order-by date_published --order-dir\n"
        "desc" in prompt
    )
    assert "latest release versus latest technical report" in prompt
    assert '"reader_mode":false' in prompt


def test_reader_system_prompt_profile_is_selected_by_trusted_metadata():
    prompt = render(reader_mode=True)

    assert "## Paper reader mode (reader-v1)" in prompt
    assert "authoritative primary paper" in prompt
    assert "never present its page number as a verified page citation" in prompt
    assert '"reader_mode":true' in prompt
    assert "[repo_id](https://huggingface.co/datasets/<repo_id>)" in prompt


def test_tool_output_is_utf8_bounded_and_terminal_controls_are_inert():
    text, truncated = bound_tool_output(b"\x1b[31m" + "é".encode() * 100, 64)
    assert truncated
    assert "\x1b" not in text
    assert len(text.encode()) <= 64


def test_tool_policy_rejects_traversal_and_enforces_aggregate_bytes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guide = tmp_path / "PWC_CLI_SKILL.md"
    guide.write_text("guide")
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    denied = budget.authorize(
        "outside",
        "Read",
        {"file_path": str(tmp_path / "secret")},
        workspace=workspace,
        guide=guide,
    )
    assert not denied.allowed
    assert denied.reason == (
        "Read and Grep may only access /workspace or the approved CLI guides. "
        "Rerun the source command with output redirected to /workspace, then try again."
    )
    assert not budget.tooling_closed
    assert budget.authorize(
        "recovery",
        "Bash",
        {"command": "printf data > /workspace/result.txt"},
        workspace=workspace,
        guide=guide,
    ).allowed
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    for index in range(3):
        tool_id = f"tool-{index}"
        assert budget.authorize(
            tool_id,
            "Bash",
            {"command": "printf data"},
            workspace=workspace,
            guide=guide,
        ).allowed
        result = budget.result(tool_id, "x" * 100, status="success")
        assert len(result["content"][0]["text"].encode()) <= 24
    assert budget.output_bytes == 48


def test_worker_protocol_accepts_complete_turn_after_one_terminal():
    frame = {"v": 1, "type": "run_turn", "request_id": "r"}
    assert decode_frame(encode_frame(frame)) == frame
    validator = WorkerEventValidator()
    validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "workspace_ready"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_correlates_parallel_argument_streams_and_final_args():
    validator = WorkerEventValidator()
    validator.accept(
        {"type": "tool_call_start", "id": "a", "name": "Bash", "content_index": 0}
    )
    validator.accept(
        {"type": "tool_call_start", "id": "b", "name": "Read", "content_index": 1}
    )
    validator.accept(
        {
            "type": "tool_call_arguments_delta",
            "id": "b",
            "name": "Read",
            "delta": '{"file_path":"src',
            "partial_args": {"file_path": "src"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_delta",
            "id": "a",
            "name": "Bash",
            "delta": '{"command":"pwc',
            "partial_args": {"command": "pwc"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_done",
            "id": "a",
            "name": "Bash",
            "args": {"command": "pwc version"},
        }
    )
    validator.accept(
        {
            "type": "tool_call_arguments_done",
            "id": "b",
            "name": "Read",
            "args": {"file_path": "src/file.py"},
        }
    )
    validator.accept({"type": "tool_result", "id": "b"})
    validator.accept({"type": "tool_result", "id": "a"})

    with pytest.raises(ProtocolError, match="post-terminal"):
        validator.accept(
            {
                "type": "tool_call_arguments_delta",
                "id": "a",
                "name": "Bash",
                "delta": "duplicate",
                "partial_args": {},
            }
        )


def test_worker_transport_replaces_provider_tool_ids_before_public_projection():
    execution = object.__new__(WorkerTurnExecution)
    execution._public_tool_ids = {}
    execution._next_public_tool_id = 1
    provider_id = "call_" + ("provider-metadata" * 8)

    start = execution._public_event(
        {
            "v": 1,
            "request_id": "request-1",
            "type": "app_start",
            "id": provider_id,
            "instance_id": provider_id,
            "provider": "excalidraw",
            "server": "excalidraw",
            "tool": "create_view",
            "resource_uri": "ui://excalidraw/mcp-app.html",
            "input": {"elements": "[]"},
        }
    )
    result = execution._public_event(
        {"type": "app_result", "id": provider_id, "status": "ready"}
    )

    assert start["id"] == "tool-1"
    assert start["instance_id"] == "tool-1"
    assert result["id"] == "tool-1"
    assert provider_id not in json.dumps(start)
    assert provider_id not in json.dumps(result)
    assert b'"instance_id":"tool-1"' in sse_event(
        start["type"], **{key: value for key, value in start.items() if key != "type"}
    )

    first_provider_id = "call_first-provider-id"
    second_provider_id = "call_second-provider-id"
    streamed = [
        execution._public_event(
            {
                "type": "tool_call_start",
                "id": first_provider_id,
                "name": "Bash",
                "content_index": 0,
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_start",
                "id": second_provider_id,
                "name": "Read",
                "content_index": 1,
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_arguments_delta",
                "id": second_provider_id,
                "name": "Read",
                "delta": '{"file_path":"/work',
                "partial_args": {"file_path": "/work"},
            }
        ),
        execution._public_event(
            {
                "type": "tool_call_arguments_done",
                "id": first_provider_id,
                "name": "Bash",
                "args": {"command": "pwc version"},
            }
        ),
        execution._public_event(
            {"type": "tool_result", "id": second_provider_id, "status": "success"}
        ),
    ]
    assert [event["id"] for event in streamed] == [
        "tool-2",
        "tool-3",
        "tool-3",
        "tool-2",
        "tool-3",
    ]
    assert first_provider_id not in json.dumps(streamed)
    assert second_provider_id not in json.dumps(streamed)


def test_worker_accepts_bounded_inline_paper_prompt_by_utf8_bytes():
    prompt = "é" * (MAX_RUN_PROMPT_BYTES // 2)
    frame = {
        "v": 1,
        "type": "run_turn",
        "request_id": "request-1",
        "prompt": prompt,
        "model": "model-a",
    }

    assert agent._validate_run_frame(frame) == (
        prompt,
        "request-1",
        "model-a",
        False,
        False,
        False,
        "high",
        [],
        "unknown",
    )
    assert decode_frame(encode_frame(frame))["prompt"] == prompt

    frame["prompt"] += "é"
    with pytest.raises(ValueError, match="Invalid prompt"):
        agent._validate_run_frame(frame)


def test_persistent_worker_stdin_accepts_inline_paper_frame():
    frame = encode_frame(
        {
            "v": 1,
            "type": "run_turn",
            "request_id": "request-1",
            "prompt": "x" * (80 * 1024),
            "model": "model-a",
        }
    )

    async def read_frame():
        reader = agent._persistent_stdin_reader()
        reader.feed_data(frame)
        reader.feed_eof()
        return await reader.readline()

    assert asyncio.run(read_frame()) == frame


def test_worker_protocol_rejects_invalid_result_and_terminal_sequences():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="Uncorrelated"):
        validator.accept({"type": "tool_result", "id": "missing"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "answer_delta", "text": "late"})
    with pytest.raises(ProtocolError, match="Duplicate terminal"):
        validator.accept({"type": "error"})


def test_worker_protocol_correlates_one_poster_publication():
    ready = {
        "publication_id": "poster-1",
        "artifact_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
        "identifier": "attention-poster",
        "version": 1,
        "kind": "posterly",
        "title": "Attention Is All You Need",
        "preview_mime": "image/png",
        "source_language": "html",
        "gate_status": "warnings",
        "total_bytes": 1024,
    }
    events = artifact_events_from_output(
        "diagnostic\n@@PWC_ARTIFACT@@" + json.dumps(ready)
    )
    assert [event["type"] for event in events] == [
        "artifact_start",
        "artifact_ready",
    ]

    validator = WorkerEventValidator()
    for event in events:
        validator.accept(event)
    with pytest.raises(ProtocolError, match="duplicate artifact terminal"):
        validator.accept(events[-1])
    validator.accept({"type": "done"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_rejects_unfinished_or_inconsistent_poster():
    validator = WorkerEventValidator()
    validator.accept(
        {
            "type": "artifact_start",
            "publication_id": "poster-1",
            "identifier": "paper-poster",
            "kind": "posterly",
            "title": "Paper poster",
        }
    )
    with pytest.raises(ProtocolError, match="unfinished artifact"):
        validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="Inconsistent artifact terminal"):
        validator.accept(
            {
                "type": "artifact_ready",
                "publication_id": "poster-1",
                "artifact_id": str(uuid.uuid4()),
                "version_id": str(uuid.uuid4()),
                "identifier": "different-poster",
                "version": 1,
                "kind": "posterly",
                "title": "Paper poster",
                "preview_mime": "image/png",
                "source_language": "html",
                "gate_status": "passed",
                "total_bytes": 1024,
            }
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Make a poster for this paper", True),
        ("Use Posterly for @Attention Is All You Need", True),
        ("Summarize the poster section", True),
        ("Summarize this paper", False),
        ("What are the posterior probabilities?", False),
    ],
)
def test_poster_intent_is_explicit_and_word_bounded(text: str, expected: bool):
    assert detect_poster_intent(text) is expected


def test_worker_protocol_requires_terminal_before_successful_completion():
    validator = WorkerEventValidator()

    with pytest.raises(ProtocolError, match="without a semantic terminal"):
        validator.accept({"type": "worker_done", "status": "complete"})
    with pytest.raises(ProtocolError, match="Invalid worker completion status"):
        validator.accept({"type": "worker_done", "status": "unknown"})


def test_worker_protocol_treats_transcript_mirror_failure_as_terminal():
    validator = WorkerEventValidator()
    validator.accept({"type": "_mirror_error"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_accepts_content_free_mcp_readiness():
    validator = WorkerEventValidator()
    validator.accept(
        {
            "type": "_mcp_readiness",
            "ready": False,
            "failure_class": "configured_not_connected",
            "enabled_provider_ids": ["excalidraw"],
            "registered_tool_names": ["bash", "read", "search_web"],
            "registration_latency_ms": 12,
            "egress_policy_digest": "a" * 64,
        }
    )
    validator.accept({"type": "done"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_allows_terminal_less_correlated_cancellation():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="without a correlated cancellation"):
        validator.accept({"type": "worker_done", "status": "stopped"})

    validator.accept(
        {"type": "worker_done", "status": "stopped"},
        allow_terminal_less_stop=True,
    )

    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "worker_done", "status": "stopped"})
    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "done"})


def test_prompt_and_manifest_share_six_round_contract():
    prompt = render(
        current_date=date(2026, 7, 28),
        selected_model="deepseek-ai/DeepSeek-V4-Flash-0731:baseten",
        web_search_enabled=True,
        hf_username="nielsrogge",
    )
    assert '"current_date_utc":"2026-07-28"' in prompt
    assert "at most 6 executed tool-use rounds" in prompt
    assert "hard failure ceilings, not retrieval targets" in prompt
    assert "within 2 rounds and 2 searches" in prompt
    assert "aim to stay within\n400 words" in prompt
    assert "title-based `pwc paper info` lookup can consume a search" in prompt
    assert "If any tool reports a 429" in prompt
    assert "Every Bash command runs with `set -eo pipefail`" in prompt
    assert "global leaderboard as evidence" in prompt
    assert "`rg`'s no-match status" in prompt
    assert "do not place multiple search executions" in prompt
    assert "secure, disposable sandbox" in prompt
    assert "Every Bash command already starts in /workspace" in prompt
    assert "never prefix a command with `cd /workspace`" in prompt
    assert "anonymous, read-only `pwc` CLI" in prompt
    assert "`s2` Semantic Scholar CLI" in prompt
    assert "`s2 citations" in prompt
    assert "use `s2 search` as the broader Semantic Scholar fallback" in prompt
    assert "already installed" in prompt
    assert "deepseek-ai/DeepSeek-V4-Flash-0731:baseten" in prompt
    assert "harness is orchestration, not the model" in prompt
    assert "never identify yourself as Pi or Claude" in prompt
    assert "direct network clients" in prompt
    assert "`command -v <name>` succeeds" in prompt
    visual_instruction = (
        "When `read_me` and `create_view` are available, use them any time the "
        "user asks\nfor a visual explanation or visualization."
    )
    assert visual_instruction in prompt
    assert "Use Read only in `/workspace`" in prompt
    assert "HF access is anonymous-only" in prompt
    assert "fix the JSON and call `create_view` once more" in prompt
    assert prompt.index("## Tool usage") < prompt.index(visual_instruction)
    assert "[owner/repo](https://github.com/owner/repo)" in prompt
    assert "Never output a bare repository slug" in prompt
    assert "## Available research areas and representative tasks" in prompt
    assert "## Representative methods in the catalog" in prompt
    assert "`world-action-models` — World Action Models (WAMs)" in prompt
    assert "`on-policy-distillation` — On-Policy Distillation (OPD)" in prompt
    assert "as an existing PwC method" in prompt
    assert "### Audio" in prompt
    assert "### Vision" in prompt
    assert prompt.index("## Available research areas") < prompt.index(
        "## Representative methods"
    )
    assert prompt.index("## Representative methods") < prompt.index("# pwc CLI skill")
    assert "# pwc CLI skill" in prompt
    assert "name: pwc-cli" in prompt
    assert prompt.index("# pwc CLI skill") < prompt.index("# Turn metadata")
    assert '"harness":"PwC research agent"' in prompt
    assert '"agent_harness":"claude"' in prompt
    assert '"sandbox":"secure disposable sandbox with writable /workspace"' in prompt
    assert '"web_search_enabled":true' in prompt
    assert '"hf_username":"nielsrogge"' in prompt
    assert prompt.rstrip().endswith("</turn_metadata>")
    manifest = build_manifest("a" * 40, "staging")
    assert manifest["chat_runtime"]["system_prompt_sha256"] == sha256()
    assert manifest["chat_runtime"]["new_chat_modal_percentage"] == 100
    production = build_manifest("b" * 40, "production")
    assert production["chat_runtime"]["enabled"] is False
    assert production["chat_runtime"]["new_chat_modal_percentage"] == 0
    assert production["chat_runtime"]["default_backend"] == "modal_cli"
    assert (
        production["chat_runtime"]["worker_contract_version"] == WORKER_CONTRACT_VERSION
    )
    assert IMAGE_PUBLISH_NAME == "pwc-chat-v1"
    assert MODAL_APP_NAME == "pwc-chat-sandbox-v1"
    assert BASE_IMAGE.startswith("python:3.12-slim-bookworm@sha256:")
    assert MODAL_IMAGE_ID.startswith("im-")
    assert PRODUCTION_MODAL_IMAGE_ID == "im-W71zgTGkrRObP9Ix1MajBp"
    assert int(WORKER_CONTRACT_VERSION) >= 97
    assert CHAT_SANDBOX_REGION == "eu-west"
    assert CONTROL_PORT == 8080


def test_pi_prompt_keeps_cli_contract_without_embedding_reference_appendices():
    prompt = render(agent_harness="pi")

    assert len(prompt.encode("utf-8")) < 20_000
    assert "pwc task --name TASK" in prompt
    assert "pwc benchmark list --task TASK" in prompt
    assert "/opt/pwc/PWC_CLI_SKILL.md" in prompt
    assert "/opt/pwc/HF_CLI_SKILL.md" in prompt
    assert "/opt/pwc/S2_CLI_SKILL.md" in prompt
    assert "# pwc CLI skill" not in prompt
    assert "## Complete live task lookup index" not in prompt


@pytest.mark.parametrize(
    ("command", "returncode"),
    [
        ("printf 'unmatched\\n' | { rg -- 'match' || test $? -eq 1; }", 0),
        ("false | { rg -- 'match' || test $? -eq 1; }", 1),
    ],
)
def test_rg_no_match_guard_preserves_upstream_pipefail_errors(command, returncode):
    result = subprocess.run(["bash", "-o", "pipefail", "-c", command], check=False)

    assert result.returncode == returncode


def test_task_catalog_is_bounded_and_ranked():
    payload = {
        "results": [
            {
                "name": "Vision",
                "tasks": [
                    {
                        "name": "Popular",
                        "slug": "popular",
                        "paper_count": 999,
                    },
                    {
                        "name": "Video Understanding",
                        "slug": "video-understanding",
                        "paper_count": 40,
                    },
                    {"name": "Detection", "slug": "detection", "paper_count": 20},
                    {
                        "name": "Classification",
                        "slug": "classification",
                        "paper_count": 30,
                    },
                    {"name": "Segmentation", "slug": "segmentation", "paper_count": 10},
                ],
            },
            {
                "name": "Audio",
                "tasks": [
                    {"name": "Speech", "slug": "speech", "paper_count": 5},
                ],
            },
        ],
        "all_tasks": [
            {
                "name": "Text Reranking",
                "slug": "text-reranking",
                "level": 2,
                "paper_count": 630,
            }
        ],
    }

    catalog = render_task_catalog(payload, maximum_tasks_per_area=3)

    assert catalog.index("### Audio") < catalog.index("### Vision")
    assert catalog.index("`popular`") < catalog.index("`classification`")
    assert (
        "video understanding includes subtasks like video question answering" in catalog
    )
    assert "`detection`" not in catalog
    assert "`segmentation`" not in catalog
    assert "## Complete task lookup index" in catalog
    assert "`text-reranking` — Text Reranking" in catalog


def test_method_catalog_is_bounded_ranked_and_retains_featured_methods():
    payload = {
        "results": [
            {
                "name": "General",
                "methods": [
                    {
                        "name": "Transformer",
                        "full_name": "Transformer",
                        "slug": "transformer",
                        "paper_count": 100,
                    },
                    {
                        "name": "Dropout",
                        "full_name": "Dropout",
                        "slug": "dropout",
                        "paper_count": 90,
                    },
                    {
                        "name": "World Action Models",
                        "full_name": "World Action Models (WAMs)",
                        "slug": "world-action-models",
                        "paper_count": 5,
                    },
                ],
            },
            {
                "name": "Vision",
                "methods": [
                    {
                        "name": "Vision Transformer",
                        "full_name": "Vision Transformer",
                        "slug": "vision-transformer",
                        "paper_count": 50,
                    }
                ],
            },
        ]
    }

    catalog = render_method_catalog(payload, maximum_methods_per_area=2)

    assert catalog.index("### General") < catalog.index("### Vision")
    assert "`transformer`" in catalog
    assert "`world-action-models`" in catalog
    assert "World Action Models (WAMs)" in catalog
    assert "`dropout`" not in catalog


def test_image_makes_copied_worker_readable_and_installs_skill():
    source = (
        Path(__file__).resolve().parents[1] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert 'WORKER / "PWC_CLI_SKILL.md", "/opt/pwc/PWC_CLI_SKILL.md"' in source
    assert 'WORKER / "S2_CLI_SKILL.md", "/opt/pwc/S2_CLI_SKILL.md"' in source
    assert (
        'BACKEND / "chat_execution_policy.py",\n'
        '        "/opt/pwc/backend/chat_execution_policy.py"'
    ) in source
    assert '"chmod -R a+rX /opt/pwc/backend"' in source
    assert '"chmod -R a+rX /opt/pwc/restricted_hf_cli"' in source
    assert '"chmod 0644 /opt/pwc/PWC_CLI_SKILL.md /opt/pwc/install-pwc.py"' in source
    assert "PWC_CLI_SOURCE_COMMIT" in source
    assert "PWC_CLI_INSTALLER_SHA256" in source
    assert "raw.githubusercontent.com/huggingface/pwc-cli/" in source
    assert "sha256sum -c -" in source
    assert source.index('"mkdir -p /opt/pwc"') < source.index(
        "raw.githubusercontent.com/huggingface/pwc-cli/"
    )
    assert '"runuser -u pwc-chat -- hf --help >/dev/null"' in source
    assert '"python -m pip install --no-deps /opt/pwc/s2_cli"' in source
    assert "runuser -u pwc-chat -- hf version" in source
    assert (
        "\"PYTHONPATH=/opt/pwc python -c 'import backend.chat_execution_policy'\""
    ) in source
    assert '"chown pwc-broker:pwc-broker /var/empty/pwc-broker"' in source
    assert '"websockets==16.0"' in source
    assert "import backend.chat_sandbox_worker.executor_daemon" in source
    assert "import backend.chat_sandbox_worker.executor_relay" in source
    assert "EXECUTOR_USER == 'pwc-chat'" in source
    assert "DEFAULT_EXECUTOR_PIDS_MAX == 64" in source


def test_chat_worker_exposes_parameter_filtered_benchmarks():
    skill = Path(agent.__file__).with_name("PWC_CLI_SKILL.md").read_text()
    image_source = (
        Path(__file__).resolve().parents[1] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert PWC_CLI_VERSION == "0.3.0"
    assert "--author AUTHOR" in skill
    assert "--max-parameters SIZE" in skill
    assert "at or below an inclusive parameter" in skill
    assert "resource-constrained device requests" in skill
    assert "pwc benchmark --help | grep -F -- '--max-parameters'" in image_source
    assert "pwc paper list --help" in image_source


def test_control_websocket_requires_verified_worker_generation(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")

    def connection(metadata):
        return SimpleNamespace(
            request=SimpleNamespace(
                headers={
                    control_websocket.VERIFIED_METADATA_HEADER: json.dumps(metadata)
                }
            )
        )

    control_websocket._verify_generation(
        connection({"worker_generation": "generation-a"})
    )
    with pytest.raises(PermissionError, match="generation mismatch"):
        control_websocket._verify_generation(
            connection({"worker_generation": "generation-b"})
        )
    with pytest.raises(PermissionError, match="Missing verified"):
        control_websocket._verify_generation(
            SimpleNamespace(request=SimpleNamespace(headers={}))
        )


def test_persistent_control_uses_authenticated_connect_token(monkeypatch):
    calls: dict = {}

    class Connection:
        def __init__(self):
            self.sent = []
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def send(self, payload):
            self.sent.append(payload)

        async def close(self):
            self.closed = True

    connection = Connection()

    async def create_connect_token(*, user_metadata, port):
        calls["token"] = (user_metadata, port)
        return SimpleNamespace(
            url="https://connect.modal.test/control",
            token="secret-token",
        )

    async def connect(url, **options):
        calls["connect"] = (url, options)
        return connection

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.websocket_connect", connect
    )
    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    sandbox = SimpleNamespace(
        object_id="sb-test",
        create_connect_token=SimpleNamespace(aio=create_connect_token),
    )

    async def exercise():
        control = await manager._worker_transport().open_persistent_control(
            sandbox,
            "generation-a",
        )
        control.process.stdin.write(b"first")
        control.process.stdin.write(b"-second")
        await control.process.stdin.drain.aio()
        await control.process.aclose()
        if control.reader_task is not None:
            await control.reader_task
        return control

    control = asyncio.run(exercise())

    assert calls["token"] == ({"worker_generation": "generation-a"}, 8080)
    url, options = calls["connect"]
    assert url == "wss://connect.modal.test/control"
    assert options["additional_headers"] == {"Authorization": "Bearer secret-token"}
    assert options["compression"] is None
    assert options["proxy"] is None
    assert connection.sent == [b"first-second"]
    assert connection.closed is True
    assert control.stderr_task is None


def test_image_publication_initializes_modal_app(monkeypatch, capsys):
    events: list[str] = []

    class Lookup:
        def __call__(self, name, *, create_if_missing):
            assert name == MODAL_APP_NAME
            assert create_if_missing is True
            events.append("lookup")

    class Run:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *_args):
            events.append("exit")

    class App:
        @staticmethod
        def run():
            return Run()

    class Built:
        object_id = "im-test"

        @staticmethod
        def publish(name):
            assert events == ["lookup", "enter", "build"]
            events.append(f"publish:{name}")

    class Image:
        @staticmethod
        def build(_app):
            assert events == ["lookup", "enter"]
            events.append("build")
            return Built()

    monkeypatch.setattr(publish_image, "app", App())
    monkeypatch.setattr(publish_image, "image", Image())
    monkeypatch.setattr(publish_image.modal.App, "lookup", Lookup())

    assert publish_image.main() == 0
    assert events == [
        "lookup",
        "enter",
        "build",
        f"publish:{IMAGE_PUBLISH_NAME}",
        "exit",
    ]
    assert capsys.readouterr().out == "im-test\n"


def test_immutable_modal_image_uses_supported_constructor(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: sentinel if image_id == "im-test" else None,
    )

    assert asyncio.run(resolve_modal_image("im-test")) is sentinel


def test_persistent_sandbox_uses_daemon_probe_and_request_limit_pairs(monkeypatch):
    captured: dict = {}

    async def lookup(*_args, **_kwargs):
        return object()

    async def image(_reference):
        return object()

    class Created:
        def __init__(self):
            self.exec = SimpleNamespace(aio=self._exec)
            self.poll = SimpleNamespace(aio=self._poll)

        async def _exec(self, *_args, **_kwargs):
            async def wait():
                return None

            return SimpleNamespace(
                returncode=0,
                wait=SimpleNamespace(aio=wait),
            )

        async def _poll(self):
            return None

    async def create(*command, **options):
        captured["command"] = command
        captured["options"] = options
        return Created()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.App.lookup",
        SimpleNamespace(aio=lookup),
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.resolve_modal_image",
        image,
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Sandbox.create",
        SimpleNamespace(aio=create),
    )
    settings = Settings(
        _env_file=None,
        chat_gateway_url="https://gateway.example.test/api/internal/chat-gateway",
        chat_modal_image_version="im-test",
        chat_persistent_worker_enabled=True,
        chat_sandbox_cpu=0.125,
        chat_sandbox_cpu_limit=1,
        chat_sandbox_memory_mib=512,
        chat_sandbox_memory_limit_mib=2048,
    )

    asyncio.run(
        create_isolated_sandbox(settings, name="test", tags={"purpose": "test"})
    )

    assert captured["command"] == (
        "python",
        "-m",
        "backend.chat_sandbox_worker.control_daemon",
    )
    assert captured["options"]["cpu"] == (0.125, 1)
    assert captured["options"]["memory"] == (512, 2048)
    assert captured["options"]["region"] == "eu-west"
    assert captured["options"]["timeout"] == 86400
    assert captured["options"]["idle_timeout"] == 86400
    assert captured["options"]["inbound_cidr_allowlist"] is None
    assert captured["options"]["encrypted_ports"] == []
    assert captured["options"]["unencrypted_ports"] == []
    assert captured["options"]["env"]["PWC_CHAT_MAX_OUTPUT_TOKENS"] == "8000"


def test_supervisor_tolerates_unsupported_proc_remount(monkeypatch):
    monkeypatch.setattr(
        supervisor.Path,
        "read_text",
        lambda *_args, **_kwargs: "none /proc proc rw 0 0\n",
    )

    class Result:
        returncode = 32

    calls: list[list[str]] = []

    def run(command, **options):
        calls.append(command)
        assert options["check"] is False
        return Result()

    monkeypatch.setattr(supervisor.subprocess, "run", run)

    supervisor._harden_proc()
    assert calls == [["mount", "-o", "remount,hidepid=2,nosuid,nodev", "/proc"]]


def test_supervisor_child_environment_preserves_packaged_worker_path(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_MAX_TURNS", "8")
    monkeypatch.setenv("PWC_CHAT_MAX_OUTPUT_TOKENS", "8000")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")

    environment = supervisor._safe_environment("/var/empty/pwc-broker")

    assert environment["PYTHONPATH"] == "/opt/pwc"
    assert environment["PWC_CHAT_MAX_TURNS"] == "8"
    assert "ANTHROPIC_API_KEY" not in environment

    agent_environment = supervisor._agent_environment()
    assert agent_environment["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8000"
    assert agent_environment["HTTPS_PROXY"] == "http://127.0.0.1:8766"
    assert agent_environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert agent_environment["NODE_EXTRA_CA_CERTS"] == "/tmp/pwc-webfetch-ca.pem"
    assert agent_environment["PWC_API_URL"] == "http://127.0.0.1:8765/api/v1"
    assert "PWC_WEBFETCH_TOKEN_FD" not in agent_environment


def test_resource_probe_treats_ephemeral_disk_as_provider_managed(monkeypatch):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    probes: list[str] = []

    async def record(name, *_command, **_options):
        probes.append(name)

    monkeypatch.setattr(runner, "_resource_probe", record)

    assert asyncio.run(runner.run_resource_probes()) == {
        "pids": "enforced",
        "disk": "provider_managed_ephemeral",
        "memory": "enforced",
    }
    assert probes == ["pids", "memory"]


def test_qualification_retains_samples_when_resource_probe_fails(monkeypatch):
    runner = QualificationRunner(
        SimpleNamespace(), starts=1, parallel=1, snapshot_samples=0
    )

    async def sample(_index):
        return Sample(1, 2, 3, None, None)

    async def fail_resources():
        raise RuntimeError("content must not be emitted")

    monkeypatch.setattr(runner, "_sample", sample)
    monkeypatch.setattr(runner, "run_resource_probes", fail_resources)

    samples, resources = asyncio.run(runner.run(resource_probes=True))

    assert samples == [Sample(1, 2, 3, None, None)]
    assert resources == {"status": "failed", "error_code": "RuntimeError"}


def test_qualification_merges_complete_release_runtime_identity():
    environment = Settings(
        _env_file=None,
        release_id="protected-stale",
        chat_modal_image_version="im-stale",
        chat_worker_contract_version="3",
        chat_pi_version="",
        chat_pi_node_version="",
    )
    release = environment.model_copy(
        update={
            "release_id": "exact-release",
            "chat_modal_image_version": "im-exact",
            "chat_worker_contract_version": "80",
            "chat_default_agent_harness": "pi",
            "chat_pi_version": "0.84.1",
            "chat_pi_node_version": "22.19.0",
            "chat_pi_runtime_enabled": True,
        }
    )

    merged = merge_release_settings(environment, release)

    assert merged.release_id == "exact-release"
    assert merged.chat_modal_image_version == "im-exact"
    assert merged.chat_worker_contract_version == "80"
    assert merged.chat_default_agent_harness == "pi"
    assert merged.chat_pi_version == "0.84.1"
    assert merged.chat_pi_node_version == "22.19.0"
    assert merged.chat_pi_runtime_enabled is True


def test_pi_prewarm_qualification_creates_the_actual_blank_profile(monkeypatch):
    settings = SimpleNamespace(release_id="release-a")
    runner = QualificationRunner(
        settings,
        starts=1,
        parallel=1,
        snapshot_samples=0,
        pi_prewarm=True,
    )
    captured = {}

    async def create(configured, **options):
        captured.update(settings=configured, **options)
        return object()

    monkeypatch.setattr(qualify_chat_sandbox, "create_isolated_sandbox", create)

    asyncio.run(runner._create("one"))

    assert captured["settings"] is settings
    assert captured["tags"]["pool"] == "blank"
    assert captured["tags"]["release"] == "release-a"


@pytest.mark.parametrize(
    "provider_error",
    [
        qualify_chat_sandbox.NotFoundError("gone"),
        qualify_chat_sandbox.ConflictError("shutting down"),
    ],
)
def test_resource_probe_accepts_provider_kill_as_expected_limit(
    monkeypatch, provider_error
):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    terminated = False

    class Sandbox:
        class Terminate:
            async def aio(self, **_options):
                nonlocal terminated
                terminated = True
                raise qualify_chat_sandbox.NotFoundError("gone")

        terminate = Terminate()

    async def create(_name):
        return Sandbox()

    async def provider_killed(*_args, **_options):
        raise provider_error

    monkeypatch.setattr(runner, "_create", create)
    monkeypatch.setattr(qualify_chat_sandbox, "_exec", provider_killed)

    asyncio.run(
        runner._resource_probe(
            "memory",
            "python",
            "-c",
            "raise SystemExit(1)",
            expect_success=False,
            timeout=30,
        )
    )
    assert terminated


def test_capability_is_exactly_scoped_and_metered():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    token = "opaque-test-token"
    row = ChatTurnCapability(
        id=uuid.uuid4(),
        token_hash=_digest(token),
        chat_session_id=session_id,
        turn_id=turn_id,
        owner_hash="a" * 64,
        model="model-a",
        scopes=["catalog"],
        nonce="b" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        gateway_calls=0,
        provider_requests=0,
        provider_tokens=0,
        catalog_search_calls=0,
    )

    class Result:
        def scalar_one_or_none(self):
            return row

    class DB:
        def execute(self, _query):
            return Result()

        def flush(self):
            pass

    service = ChatCapabilityService(DB())
    assert (
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
        is row
    )
    assert row.gateway_calls == 1
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="model",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
        )


def test_workspace_snapshot_provider_only_snapshots_workspace():
    calls: list[tuple[str, int, int]] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Image:
        object_id = "im-snapshot"

        def __init__(self):
            self.hydrate = AsyncCall(self._hydrate)

        async def _hydrate(self):
            return self

    async def snapshot(path, *, timeout, ttl):
        calls.append((path, timeout, ttl))
        return Image()

    class Sandbox:
        snapshot_directory = AsyncCall(snapshot)

    provider = WorkspaceSnapshotProvider(ttl_days=30)
    assert asyncio.run(provider.save(Sandbox(), uuid.uuid4())) == "im-snapshot"
    assert calls == [("/workspace", 55, 30 * 24 * 60 * 60)]


def test_workspace_snapshot_restore_uses_supported_image_constructor(monkeypatch):
    image = object()
    mounted: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: image if image_id == "im-snapshot" else None,
    )

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    async def mount(path, mounted_image):
        mounted.append((path, mounted_image))

    class Sandbox:
        mount_image = AsyncCall(mount)

    provider = WorkspaceSnapshotProvider()
    asyncio.run(provider.restore(Sandbox(), "im-snapshot"))
    assert mounted == [("/workspace", image)]


def test_sandbox_cancel_correlates_to_original_run_request():
    writes: list[bytes] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Stdin:
        def __init__(self):
            self.drain = AsyncCall(self._drain)

        def write(self, value):
            writes.append(value)

        async def _drain(self):
            return None

    class Process:
        stdin = Stdin()

        def __init__(self):
            self.wait = AsyncCall(self._wait)

        async def _wait(self):
            return None

    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    turn_id = uuid.uuid4()
    running = RunningWorker(
        Process(),
        "original-request",
        WorkerClaim("sandbox-id", "worker-token"),
    )
    manager._worker_transport().register_running_worker(turn_id, running)

    assert asyncio.run(manager.cancel(uuid.uuid4(), turn_id))
    assert running.cancel_requested
    assert decode_frame(writes[0].rstrip(b"\n"))["request_id"] == ("original-request")


def test_forced_failure_probe_does_not_record_user_cancellation():
    assert qualify_chat_soak._requests_user_cancel("clean")
    assert not qualify_chat_soak._requests_user_cancel("forced")


def test_session_store_rejects_bad_shape_before_touching_database():
    class DB:
        def execute(self, _statement):
            raise AssertionError("database must not be touched")

    gateway = ChatSessionStoreGateway(
        DB(),
        type(
            "Settings",
            (),
            {
                "chat_session_byte_limit": 1024,
                "chat_user_byte_limit": 4096,
            },
        )(),
    )
    with pytest.raises(SessionStoreGatewayError, match="Unsupported"):
        gateway.execute(
            ChatTurnCapability(),
            SessionStoreCommand(
                action="delete",
                key=None,
                entries=None,
                project_key=None,
            ),
        )


def test_qualification_summary_uses_nearest_rank_p95():
    samples = [
        Sample(
            cold_start_ms=value,
            exec_ms=value * 2,
            termination_ms=value * 3,
            snapshot_ms=value if value <= 3 else None,
            restore_ms=value + 1 if value <= 3 else None,
        )
        for value in range(1, 21)
    ]
    result = summarize(samples)
    assert result["cold_start_ms"] == {
        "count": 20,
        "min": 1,
        "p50": 10,
        "p95": 19,
        "max": 20,
    }
    assert result["snapshot_ms"]["count"] == 3


def test_sandbox_migration_is_environment_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_sandbox_runtime.sql"
    ).read_text()
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
