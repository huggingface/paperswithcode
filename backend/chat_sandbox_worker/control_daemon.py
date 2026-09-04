"""Root-only persistent sandbox control daemon."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

from backend.chat_sandbox_worker.control_websocket import start_server
from backend.chat_sandbox_worker.protocol import (
    MAX_WIRE_FRAME_BYTES,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.supervisor import (
    SUPERVISOR_PREFIX,
    _agent_environment,
    _demote,
    _harden_proc,
    _not_dumpable,
    _safe_environment,
    _wait_for_broker,
)

CONTROL_SOCKET = Path("/run/pwc-chat/control.sock")
BROKER_CONTROL_SOCKET = Path("/var/empty/pwc-broker/control.sock")
MAX_PRIVATE_FRAME_BYTES = 64 * 1024
BROKER_CONTROL_TIMEOUT_SECONDS = 25


def _readline(connection: socket.socket, maximum: int) -> bytes:
    value = bytearray()
    while len(value) < maximum:
        chunk = connection.recv(1)
        if not chunk:
            break
        value.extend(chunk)
        if chunk == b"\n":
            return bytes(value)
    if len(value) >= maximum:
        raise RuntimeError("Persistent control frame is too large")
    return bytes(value)


def _broker_control(payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(BROKER_CONTROL_TIMEOUT_SECONDS)
        connection.connect(str(BROKER_CONTROL_SOCKET))
        connection.sendall(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        response = json.loads(_readline(connection, 16 * 1024))
    if response.get("ok") is not True:
        raise RuntimeError("Broker control operation failed")
    return response


def _start_broker() -> tuple[subprocess.Popen, str]:
    proxy_token = secrets.token_urlsafe(32)
    read_fd, write_fd = os.pipe()
    broker_environment = _safe_environment("/var/empty/pwc-broker")
    broker_environment["PWC_BROKER_CONFIG_FD"] = str(read_fd)
    broker = subprocess.Popen(
        [sys.executable, "-m", "backend.chat_sandbox_worker.broker"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr,
        env=broker_environment,
        pass_fds=(read_fd,),
        preexec_fn=_demote("pwc-broker"),  # noqa: PLW1509
    )
    os.close(read_fd)
    os.write(
        write_fd,
        json.dumps(
            {
                "gateway_url": os.environ["PWC_CHAT_GATEWAY_URL"],
                "proxy_token": proxy_token,
            },
            separators=(",", ":"),
        ).encode(),
    )
    os.close(write_fd)
    _wait_for_broker(broker)
    return broker, proxy_token


def _start_agent(agent_harness: str, proxy_token: str) -> subprocess.Popen:
    if agent_harness not in {"claude", "pi"}:
        raise RuntimeError("Invalid persistent agent harness")
    agent_read_fd, agent_write_fd = os.pipe()
    agent_environment = _agent_environment()
    agent_environment["PWC_CHAT_PERSISTENT_AGENT"] = "1"
    if agent_harness == "claude":
        agent_environment["PWC_WEBFETCH_TOKEN_FD"] = str(agent_read_fd)
        pass_fds = (agent_read_fd,)
        command = [sys.executable, "-m", "backend.chat_sandbox_worker.agent"]
    else:
        pass_fds = ()
        command = [
            "node",
            "--import",
            "/opt/pwc/backend/chat_sandbox_worker/pi_worker/node_modules/tsx/dist/loader.mjs",
            "/opt/pwc/backend/chat_sandbox_worker/pi_worker/dist/src/main.js",
        ]
    agent = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        env=agent_environment,
        pass_fds=pass_fds,
        preexec_fn=_demote(  # noqa: PLW1509
            "pwc-chat",
            pids_max=int(os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", "64")),
        ),
        bufsize=0,
    )
    os.close(agent_read_fd)
    if agent_harness == "claude":
        os.write(agent_write_fd, proxy_token.encode())
    os.close(agent_write_fd)
    assert agent.stdout is not None
    ready, _, _ = select.select([agent.stdout], [], [], 30)
    if not ready:
        raise RuntimeError("Persistent agent readiness timed out")
    startup = decode_frame(agent.stdout.readline())
    if startup != {
        "v": 1,
        "type": "worker_ready",
        "request_id": "startup",
    }:
        raise RuntimeError("Persistent agent readiness failed")
    return agent


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def _validate_assignment(
    launch: dict,
    run: dict,
    *,
    assigned_session_id: str | None,
    assigned_agent_harness: str | None,
) -> tuple[str, str]:
    required = {
        "capability",
        "gateway_url",
        "session_id",
        "turn_id",
        "assignment_token",
        "worker_generation",
        "agent_harness",
    }
    if set(launch) != required:
        raise RuntimeError("Invalid persistent control launch frame")
    if launch["gateway_url"] != os.environ["PWC_CHAT_GATEWAY_URL"]:
        raise RuntimeError("Gateway changed after sandbox creation")
    if not hmac.compare_digest(
        str(launch["worker_generation"]),
        os.environ["PWC_CHAT_WORKER_GENERATION"],
    ):
        raise RuntimeError("Persistent worker generation mismatch")
    assignment_token = str(launch["assignment_token"])
    if not assignment_token:
        raise RuntimeError("Persistent worker assignment token is missing")
    session_id = str(launch["session_id"])
    agent_harness = str(launch["agent_harness"])
    if agent_harness not in {"claude", "pi"}:
        raise RuntimeError("Persistent worker harness is invalid")
    if os.environ.get("PWC_CHAT_PI_PREWARM_ENABLED") == "true":
        if agent_harness != "pi":
            raise RuntimeError("Prewarmed Pi worker rejected incompatible harness")
        if run.get("model") != os.environ.get("PWC_CHAT_PI_PREWARM_MODEL"):
            raise RuntimeError("Prewarmed Pi worker rejected incompatible model")
        if run.get("reasoning_effort") != os.environ.get(
            "PWC_CHAT_PI_PREWARM_REASONING_EFFORT"
        ):
            raise RuntimeError("Prewarmed Pi worker rejected incompatible reasoning")
    if assigned_session_id and assigned_session_id != session_id:
        raise RuntimeError("Persistent worker session ownership mismatch")
    if assigned_agent_harness and assigned_agent_harness != agent_harness:
        raise RuntimeError("Persistent worker harness ownership mismatch")
    if (
        run.get("type") != "run_turn"
        or run.get("chat_session_id") != session_id
        or run.get("request_id") is None
        or run.get("turn_id") != str(launch["turn_id"])
        or run.get("agent_harness") != agent_harness
        or run.get("worker_generation") != str(launch["worker_generation"])
        or not hmac.compare_digest(
            str(run.get("assignment_token") or ""),
            assignment_token,
        )
    ):
        raise RuntimeError("Invalid persistent run frame")
    return session_id, agent_harness


def _serve_turn(
    connection: socket.socket,
    *,
    broker: subprocess.Popen,
    agent: subprocess.Popen | None,
    proxy_token: str,
    assigned_session_id: str | None,
    assigned_agent_harness: str | None,
    startup_metrics: dict[str, int | None],
) -> tuple[str, str, subprocess.Popen | None]:
    launch_line = _readline(connection, MAX_PRIVATE_FRAME_BYTES)
    if not launch_line.startswith(SUPERVISOR_PREFIX):
        raise RuntimeError("Missing persistent control launch frame")
    launch = json.loads(launch_line[len(SUPERVISOR_PREFIX) :])
    if launch.get("operation") == "ping" and frozenset(launch) in {
        frozenset({"operation", "worker_generation"}),
        frozenset({"operation", "worker_generation", "request_id"}),
    }:
        if not hmac.compare_digest(
            str(launch["worker_generation"]),
            os.environ["PWC_CHAT_WORKER_GENERATION"],
        ):
            raise RuntimeError("Persistent worker generation mismatch")
        if broker.poll() is not None or (
            agent is not None and agent.poll() is not None
        ):
            raise RuntimeError("Persistent worker child exited")
        broker_status = _broker_control({"operation": "status"})
        if broker_status.get("active"):
            raise RuntimeError("Persistent worker capability is still active")
        request_id = launch.get("request_id")
        try:
            if request_id is None:
                connection.sendall(b"ready\n")
            else:
                connection.sendall(
                    encode_frame(
                        {
                            "v": 1,
                            "type": "worker_health",
                            "request_id": str(request_id),
                            "assigned": assigned_session_id is not None,
                            "agent_prestarted": agent is not None,
                            "startup_metrics": startup_metrics,
                        }
                    )
                )
        except (BrokenPipeError, ConnectionResetError):
            # Modal may abandon a readiness probe while the prestarted agent is
            # still initializing. A stale health connection carries no turn or
            # capability and must not terminate the otherwise healthy daemon.
            pass
        return assigned_session_id or "", assigned_agent_harness or "", agent
    run_line = _readline(connection, MAX_WIRE_FRAME_BYTES)
    run = decode_frame(run_line)
    session_id, agent_harness = _validate_assignment(
        launch,
        run,
        assigned_session_id=assigned_session_id,
        assigned_agent_harness=assigned_agent_harness,
    )
    if agent is None:
        agent = _start_agent(agent_harness, proxy_token)
    _broker_control(
        {
            "operation": "install",
            "capability": str(launch["capability"]),
            "session_id": session_id,
            "turn_id": str(launch["turn_id"]),
        }
    )
    assert agent.stdin is not None and agent.stdout is not None
    agent.stdin.write(run_line)
    agent.stdin.flush()
    poller = select.poll()
    poller.register(connection, select.POLLIN | select.POLLHUP | select.POLLERR)
    poller.register(agent.stdout, select.POLLIN | select.POLLHUP | select.POLLERR)
    buffer = b""
    worker_done: bytes | None = None
    stage = "agent_stream"
    try:
        while worker_done is None:
            if agent.poll() is not None:
                raise RuntimeError("Persistent agent exited")
            for fd, event in poller.poll(250):
                if fd == connection.fileno():
                    if event & (select.POLLHUP | select.POLLERR):
                        raise ConnectionError("Backend control connection was lost")
                    data = connection.recv(64 * 1024)
                    if not data:
                        raise ConnectionError("Backend control connection was lost")
                    agent.stdin.write(data)
                    agent.stdin.flush()
                elif fd == agent.stdout.fileno():
                    if event & (select.POLLHUP | select.POLLERR):
                        raise RuntimeError("Persistent agent control was lost")
                    data = os.read(fd, 64 * 1024)
                    if not data:
                        raise RuntimeError("Persistent agent control was lost")
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line += b"\n"
                        event_frame = decode_frame(line)
                        if event_frame.get("request_id") != run["request_id"]:
                            raise RuntimeError("Uncorrelated persistent worker frame")
                        if event_frame.get("type") == "worker_done":
                            worker_done = line
                            break
                        connection.sendall(line)
        stage = "broker_clear"
        _broker_control(
            {
                "operation": "clear",
                "session_id": session_id,
                "turn_id": str(launch["turn_id"]),
            }
        )
        stage = "worker_done_send"
        connection.sendall(worker_done)
        return session_id, agent_harness, agent
    except BaseException as exc:
        try:
            connection.sendall(
                encode_frame(
                    {
                        "v": 1,
                        "type": "_control_failure",
                        "request_id": str(run["request_id"]),
                        "stage": stage,
                        "error_class": type(exc).__name__[:64],
                    }
                )
            )
        except Exception:
            pass
        try:
            _broker_control(
                {
                    "operation": "clear",
                    "session_id": session_id,
                    "turn_id": str(launch["turn_id"]),
                }
            )
        except Exception:
            pass
        raise


def _serve_connections(
    server: socket.socket,
    *,
    broker: subprocess.Popen,
    proxy_token: str,
    startup_metrics: dict[str, int | None],
    daemon_started: float,
) -> None:
    """Serve one active relay and let a new backend replace it only while idle."""

    assigned_session_id: str | None = None
    assigned_agent_harness: str | None = None
    agent: subprocess.Popen | None = None
    if os.environ.get("PWC_CHAT_PI_PREWARM_ENABLED") == "true":
        startup_metrics["agent_spawn_ms"] = round(
            (time.monotonic() - daemon_started) * 1000
        )
        agent = _start_agent("pi", proxy_token)
        startup_metrics["agent_startup_ready_ms"] = round(
            (time.monotonic() - daemon_started) * 1000
        )
    connection: socket.socket | None = None
    try:
        while broker.poll() is None and (agent is None or agent.poll() is None):
            if connection is None:
                connection, _ = server.accept()
            readable, _, _ = select.select([connection, server], [], [], 1)
            if connection in readable:
                if not connection.recv(1, socket.MSG_PEEK):
                    connection.close()
                    connection = None
                    continue
                assigned, harness, agent = _serve_turn(
                    connection,
                    broker=broker,
                    agent=agent,
                    proxy_token=proxy_token,
                    assigned_session_id=assigned_session_id,
                    assigned_agent_harness=assigned_agent_harness,
                    startup_metrics=startup_metrics,
                )
                if assigned:
                    assigned_session_id = assigned
                    assigned_agent_harness = harness
                continue
            if server in readable:
                replacement, _ = server.accept()
                connection.close()
                connection = replacement
        raise RuntimeError("Persistent worker child exited")
    finally:
        if connection is not None:
            connection.close()
        if agent is not None:
            _stop(agent)


def main() -> int:
    daemon_started = time.monotonic()
    _not_dumpable()
    _harden_proc()
    broker, proxy_token = _start_broker()
    startup_metrics: dict[str, int | None] = {
        "broker_ready_ms": round((time.monotonic() - daemon_started) * 1000),
        "control_ready_ms": None,
        "agent_spawn_ms": None,
        "agent_startup_ready_ms": None,
    }
    CONTROL_SOCKET.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONTROL_SOCKET.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL_SOCKET))
    CONTROL_SOCKET.chmod(0o600)
    server.listen(2)
    startup_metrics["control_ready_ms"] = round(
        (time.monotonic() - daemon_started) * 1000
    )
    websocket_server, websocket_thread = start_server()
    try:
        _serve_connections(
            server,
            broker=broker,
            proxy_token=proxy_token,
            startup_metrics=startup_metrics,
            daemon_started=daemon_started,
        )
    finally:
        websocket_server.shutdown()
        websocket_thread.join(timeout=2)
        server.close()
        CONTROL_SOCKET.unlink(missing_ok=True)
        _stop(broker)


if __name__ == "__main__":
    raise SystemExit(main())
