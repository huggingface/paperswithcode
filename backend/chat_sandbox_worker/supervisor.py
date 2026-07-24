"""Root supervisor that keeps broker credentials outside the agent process."""

from __future__ import annotations

import ctypes
import json
import os
import pwd
import resource
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

SUPERVISOR_PREFIX = b"@@PWC_SUPERVISOR_V1@@"
PR_SET_DUMPABLE = 4


def _not_dumpable() -> None:
    ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)


def _demote(user: str, *, pids_max: int | None = None):
    account = pwd.getpwnam(user)

    def apply() -> None:
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        os.umask(0o077)
        if pids_max is not None:
            resource.setrlimit(resource.RLIMIT_NPROC, (pids_max, pids_max))
        _not_dumpable()

    return apply


def _safe_environment(home: str) -> dict[str, str]:
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": home,
        "LANG": "C.UTF-8",
    }
    for key, value in os.environ.items():
        if key.startswith("PWC_CHAT_"):
            environment[key] = value
    return environment


def _wait_for_broker(process: subprocess.Popen, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Broker exited before readiness")
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.1):
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
    launch = sys.stdin.buffer.readline(64 * 1024)
    if not launch.startswith(SUPERVISOR_PREFIX):
        raise RuntimeError("Missing private supervisor launch frame")
    config = json.loads(launch[len(SUPERVISOR_PREFIX) :])
    required = {"capability", "gateway_url", "session_id", "turn_id"}
    if set(config) != required:
        raise RuntimeError("Invalid private supervisor launch frame")

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

    agent = subprocess.Popen(
        [sys.executable, "-m", "backend.chat_sandbox_worker.agent"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        env=_safe_environment("/home/pwc-chat"),
        preexec_fn=_demote(
            "pwc-chat",
            pids_max=int(os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", "64")),
        ),
        bufsize=0,
    )
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
