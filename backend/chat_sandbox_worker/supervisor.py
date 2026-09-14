"""Root supervisor that keeps broker credentials outside the agent process."""

from __future__ import annotations

import json
import os
import secrets
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
from backend.chat_sandbox_worker.process_security import (
    PR_SET_DUMPABLE as PR_SET_DUMPABLE,
    _demote as _demote,
    _not_dumpable as _not_dumpable,
)

SUPERVISOR_PREFIX = b"@@PWC_SUPERVISOR_V1@@"


def _safe_environment(home: str) -> dict[str, str]:
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "/opt/pwc",
        "HOME": home,
        "LANG": "C.UTF-8",
    }
    for key, value in os.environ.items():
        if key.startswith("PWC_CHAT_"):
            environment[key] = value
    return environment


def _agent_environment() -> dict[str, str]:
    environment = _safe_environment("/home/pwc-chat")
    environment["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = environment.get(
        "PWC_CHAT_MAX_OUTPUT_TOKENS", str(PROVIDER_OUTPUT_TOKEN_LIMIT)
    )
    environment["HTTPS_PROXY"] = "http://127.0.0.1:8766"
    environment["NO_PROXY"] = "127.0.0.1,localhost"
    environment["NODE_EXTRA_CA_CERTS"] = "/tmp/pwc-webfetch-ca.pem"
    environment["PWC_API_URL"] = "http://127.0.0.1:8765/api/v1"
    environment["S2_API_KEY"] = "sandbox-gateway"
    environment["S2_API_URL"] = "http://127.0.0.1:8765/semantic-scholar/graph/v1"
    return environment


def _readline_unbuffered(fd: int, maximum_bytes: int) -> bytes:
    """Read exactly one line without prefetching bytes from the next frame."""
    line = bytearray()
    while len(line) < maximum_bytes:
        chunk = os.read(fd, 1)
        if not chunk:
            break
        line.extend(chunk)
        if chunk == b"\n":
            return bytes(line)
    if len(line) >= maximum_bytes:
        raise RuntimeError("Private supervisor launch frame is too large")
    return bytes(line)


def _wait_for_broker(process: subprocess.Popen, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Broker exited before readiness")
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.1):
                pass
            with socket.create_connection(("127.0.0.1", 8766), timeout=0.1):
                pass
            if Path("/tmp/pwc-webfetch-ca.pem").is_file():
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("Broker readiness timed out")


def _harden_proc() -> None:
    mounts = Path("/proc/mounts").read_text(encoding="utf-8")
    proc_line = next(
        (line for line in mounts.splitlines() if line.split()[1:2] == ["/proc"]), ""
    )
    if proc_line:
        options = proc_line.split()[3].split(",")
        if "hidepid=2" in options:
            return
    # Modal sandboxes do not grant mount(2), so hidepid is defense in depth.
    # The broker still runs under a distinct UID, marks itself non-dumpable,
    # receives its capability over an inherited FD, and has no secrets in argv.
    subprocess.run(
        ["mount", "-o", "remount,hidepid=2,nosuid,nodev", "/proc"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    _not_dumpable()
    _harden_proc()
    launch = _readline_unbuffered(sys.stdin.fileno(), 64 * 1024)
    if not launch.startswith(SUPERVISOR_PREFIX):
        raise RuntimeError("Missing private supervisor launch frame")
    config = json.loads(launch[len(SUPERVISOR_PREFIX) :])
    required = {
        "capability",
        "gateway_url",
        "session_id",
        "turn_id",
        "agent_harness",
    }
    if set(config) != required:
        raise RuntimeError("Invalid private supervisor launch frame")
    agent_harness = config.pop("agent_harness")
    if agent_harness not in {"claude", "pi"}:
        raise RuntimeError("Invalid agent harness")
    proxy_token = secrets.token_urlsafe(32)
    config["proxy_token"] = proxy_token

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
        preexec_fn=_demote("pwc-broker"),
    )
    os.close(read_fd)
    os.write(write_fd, json.dumps(config, separators=(",", ":")).encode())
    os.close(write_fd)
    del config
    _wait_for_broker(broker)

    agent_environment = _agent_environment()
    pass_fds: tuple[int, ...] = ()
    agent_read_fd: int | None = None
    agent_write_fd: int | None = None
    if agent_harness == "claude":
        agent_read_fd, agent_write_fd = os.pipe()
        agent_environment["PWC_WEBFETCH_TOKEN_FD"] = str(agent_read_fd)
        pass_fds = (agent_read_fd,)
        command = [sys.executable, "-m", "backend.chat_sandbox_worker.agent"]
    else:
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
        preexec_fn=_demote(
            "pwc-chat",
            pids_max=int(os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", "64")),
        ),
        bufsize=0,
    )
    if agent_read_fd is not None and agent_write_fd is not None:
        os.close(agent_read_fd)
        os.write(agent_write_fd, proxy_token.encode())
        os.close(agent_write_fd)
    del proxy_token
    assert agent.stdin is not None and agent.stdout is not None
    poller = select.poll()
    poller.register(sys.stdin.buffer, select.POLLIN | select.POLLHUP)
    poller.register(agent.stdout, select.POLLIN | select.POLLHUP)
    inputs_open = True
    try:
        while agent.poll() is None:
            for fd, event in poller.poll(250):
                if fd == sys.stdin.buffer.fileno() and event & select.POLLIN:
                    data = os.read(fd, 64 * 1024)
                    if data:
                        agent.stdin.write(data)
                        agent.stdin.flush()
                    else:
                        inputs_open = False
                elif fd == agent.stdout.fileno() and event & select.POLLIN:
                    data = os.read(fd, 64 * 1024)
                    if data:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
            if not inputs_open:
                agent.stdin.close()
        return int(agent.returncode or 0)
    finally:
        if agent.poll() is None:
            agent.terminate()
            try:
                agent.wait(timeout=2)
            except subprocess.TimeoutExpired:
                agent.kill()
        broker.terminate()
        try:
            broker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            broker.kill()


if __name__ == "__main__":
    raise SystemExit(main())
