"""Persistent sandbox assignment, health probe, relay, and control contracts."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    MirrorErrorMessage,
)

from backend.chat_sandbox_worker import (
    agent,
    control_daemon,
    supervisor,
)
from backend.chat_sandbox_worker.protocol import (
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter as WorkerSDKAdapter


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
