from __future__ import annotations

import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from textwrap import dedent
from typing import BinaryIO

from backend.chat_sandbox_worker.executor_daemon import (
    EXECUTOR_BOOTSTRAP_PREFIX,
    ExecutorServer,
)
from backend.chat_sandbox_worker.executor_protocol import (
    PROTOCOL,
    decode_response,
    encode_request,
)


def _read_frames(connection: socket.socket) -> list[dict[str, object]]:
    data = b""
    while True:
        chunk = connection.recv(64 * 1024)
        if not chunk:
            break
        data += chunk
    return [decode_response(line + b"\n") for line in data.splitlines()]


IDENTITY = {
    "workspace_id": "workspace-1",
    "workspace_generation": 1,
    "session_id": "session-1",
    "turn_id": "turn-1",
    "execution_id": "execution-1",
    "tool_call_id": "tool-1",
}


class _Broker:
    def __init__(self) -> None:
        self.active = False

    def __call__(self, payload: dict[str, object]) -> dict[str, object]:
        if payload["operation"] == "install":
            assert not self.active
            self.active = True
        elif payload["operation"] == "clear":
            assert self.active
            self.active = False
        return {"ok": True, "active": self.active}


def _operation(
    socket_path: Path,
    request: dict[str, object],
    *,
    capability: str = "synthetic-capability",
    worker_generation: str = "worker-1",
) -> list[dict[str, object]]:
    bootstrap = {
        "operation": "executor_connect",
        "capability": capability,
        "workspace_id": request["workspace_id"],
        "workspace_generation": request["workspace_generation"],
        "session_id": request["session_id"],
        "turn_id": request["turn_id"],
        "worker_generation": worker_generation,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(
            EXECUTOR_BOOTSTRAP_PREFIX
            + json.dumps(bootstrap, separators=(",", ":")).encode()
            + b"\n"
            + encode_request(request)
        )
        connection.shutdown(socket.SHUT_WR)
        return _read_frames(connection)


def _open_operation(
    socket_path: Path, request: dict[str, object]
) -> tuple[socket.socket, BinaryIO]:
    bootstrap = {
        "operation": "executor_connect",
        "capability": "synthetic-capability",
        "workspace_id": request["workspace_id"],
        "workspace_generation": request["workspace_generation"],
        "session_id": request["session_id"],
        "turn_id": request["turn_id"],
        "worker_generation": "worker-1",
    }
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(socket_path))
    connection.sendall(
        EXECUTOR_BOOTSTRAP_PREFIX
        + json.dumps(bootstrap, separators=(",", ":")).encode()
        + b"\n"
        + encode_request(request)
    )
    connection.shutdown(socket.SHUT_WR)
    reader = connection.makefile("rb")
    return connection, reader


def _write_exited_leader_command(workspace: Path) -> str:
    (workspace / "exited-leader.py").write_text(
        dedent("""
import os, signal, time
with open("leader.pid", "w") as handle:
    handle.write(str(os.getpid()))
ready_read, ready_write = os.pipe()
descendant = os.fork()
if descendant:
    os.close(ready_write)
    os.read(ready_read, 1)
    os._exit(0)
os.close(ready_read)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
output = os.open("descendant.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.dup2(output, 1)
os.dup2(output, 2)
os.close(output)
with open("descendant.pid", "w") as handle:
    handle.write(str(os.getpid()))
os.write(ready_write, b"1")
os.close(ready_write)
time.sleep(0.5)
with open("after-exited-leader", "w") as handle:
    handle.write("late")
""")
    )
    return f"exec {sys.executable} exited-leader.py"


def test_health_is_served_over_a_private_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "private" / "executor.sock"
    state_path = tmp_path / "state"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=socket_path,
        state_path=state_path,
        workspace_root=workspace,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-health",
                    "execution_id": "execution-health",
                }
            )
        )
        connection.shutdown(socket.SHUT_WR)
        responses = _read_frames(connection)

    assert responses == [
        {
            "protocol": PROTOCOL,
            "type": "health_result",
            "request_id": "request-health",
            "execution_id": "execution-health",
            "status": "ok",
        }
    ]
    assert socket_path.stat().st_mode & 0o777 == 0o600
    assert socket_path.parent.stat().st_mode & 0o777 == 0o700
    assert state_path.stat().st_mode & 0o777 == 0o700
    server.shutdown()
    thread.join(timeout=2)


def test_duplicate_exec_reattaches_without_repeating_side_effect(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        **IDENTITY,
        "command": "printf x >> side-effect; printf 'one\\ntwo\\n'",
        "timeout_ms": 2_000,
    }

    first = _operation(server.socket_path, request)
    duplicate = _operation(
        server.socket_path,
        {**request, "request_id": "request-2"},
    )

    assert (workspace / "side-effect").read_text() == "x"
    assert first[0]["type"] == "acknowledged"
    assert first[-1]["type"] == "terminal"
    assert (
        "".join(str(frame["data"]) for frame in first if frame["type"] == "output")
        == "one\ntwo\n"
    )
    assert first[-1]["status"] == "completed"
    assert duplicate[0]["request_id"] == "request-2"
    assert (
        "".join(str(frame["data"]) for frame in duplicate if frame["type"] == "output")
        == "one\ntwo\n"
    )
    assert duplicate[-1]["status"] == "completed"
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_read_is_bounded_and_descriptor_contained(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.bin").write_bytes(b"\xff\xc3\xa9\x00Z")
    (workspace / "outside-link").symlink_to(tmp_path / "outside.txt")
    (tmp_path / "outside.txt").write_text("secret")
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    base = {
        "protocol": PROTOCOL,
        "type": "read_file",
        "request_id": "request-read",
        **IDENTITY,
        "offset": 0,
        "max_bytes": 3,
    }

    valid = _operation(server.socket_path, {**base, "path": "note.bin"})
    split_multibyte = _operation(
        server.socket_path,
        {
            **base,
            "request_id": "request-split",
            "path": "note.bin",
            "offset": 1,
            "max_bytes": 1,
        },
    )
    nul = _operation(
        server.socket_path,
        {
            **base,
            "request_id": "request-nul",
            "path": "note.bin",
            "offset": 3,
            "max_bytes": 1,
        },
    )
    traversal = _operation(server.socket_path, {**base, "path": "../outside.txt"})
    symlink = _operation(server.socket_path, {**base, "path": "outside-link"})

    assert valid[1]["type"] == "read_result"
    assert valid[1]["offset"] == 0
    assert valid[1]["data_base64"] == "/8Op"
    assert valid[1]["eof"] is False
    assert split_multibyte[1]["data_base64"] == "ww=="
    assert split_multibyte[1]["eof"] is False
    assert nul[1]["data_base64"] == "AA=="
    assert traversal[-1]["error"] == "invalid_workspace_path"
    assert symlink[-1]["error"] == "invalid_workspace_path"
    server.shutdown()
    thread.join(timeout=2)


def test_read_allows_only_exact_configured_readonly_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guides = tmp_path / "guides"
    guides.mkdir()
    guide = guides / "PWC_CLI_SKILL.md"
    guide.write_text("# PWC CLI\n")
    sibling = guides / "private.txt"
    sibling.write_text("private\n")
    link = guides / "linked.md"
    link.symlink_to(guide)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        readonly_paths=frozenset({guide, link}),
        worker_generation="worker-1",
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    base = {
        "protocol": PROTOCOL,
        "type": "read_file",
        "request_id": "request-guide",
        **IDENTITY,
        "offset": 0,
        "max_bytes": 1024,
    }

    allowed = _operation(server.socket_path, {**base, "path": str(guide)})
    denied = _operation(
        server.socket_path,
        {**base, "request_id": "request-private", "path": str(sibling)},
    )
    symlink = _operation(
        server.socket_path,
        {**base, "request_id": "request-link", "path": str(link)},
    )

    assert allowed[1]["type"] == "read_result"
    assert allowed[1]["data_base64"] == "IyBQV0MgQ0xJCg=="
    assert denied[-1]["error"] == "invalid_workspace_path"
    assert symlink[-1]["error"] == "invalid_workspace_path"
    server.shutdown()
    thread.join(timeout=2)


def test_cancel_terminates_the_process_group_before_side_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.05,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-run",
        **IDENTITY,
        "command": "sleep 5; printf late > after-cancel",
        "timeout_ms": 10_000,
    }
    connection, reader = _open_operation(server.socket_path, request)
    acknowledged = decode_response(reader.readline())
    assert acknowledged["type"] == "acknowledged"

    cancelled = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "cancel_execution",
            "request_id": "request-cancel",
            **IDENTITY,
        },
    )
    terminal = decode_response(reader.readline())
    reader.close()
    connection.close()

    assert cancelled[-1]["status"] == "cancelled"
    assert terminal["status"] == "cancelled"
    assert not (workspace / "after-cancel").exists()
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_timeout_is_terminal_and_does_not_run_later_side_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.05,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-timeout",
            **IDENTITY,
            "command": "sleep 5; printf late > after-timeout",
            "timeout_ms": 50,
        },
    )

    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "execution_timeout"
    assert not (workspace / "after-timeout").exists()
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_timeout_kills_term_ignoring_descendant_after_shell_exits(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.03,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-descendant-timeout",
            **IDENTITY,
            "command": (
                "trap 'exit 0' TERM; "
                "(trap '' TERM; exec </dev/null >descendant.log 2>&1; "
                'printf "$BASHPID" > descendant.pid; '
                "sleep .5; printf late > after-descendant-timeout) & wait"
            ),
            "timeout_ms": 150,
        },
    )

    descendant_pid = int((workspace / "descendant.pid").read_text())
    stat_path = Path(f"/proc/{descendant_pid}/stat")
    if stat_path.exists():
        state = stat_path.read_text().rsplit(")", 1)[1].split()[0]
        assert state == "Z"
    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "execution_timeout"
    time.sleep(0.55)
    assert not (workspace / "after-descendant-timeout").exists()
    assert not broker.active
    server.shutdown()
    thread.join(timeout=2)


def test_timeout_contains_group_after_leader_already_exited(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        terminate_grace=0.03,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-exited-leader",
            **IDENTITY,
            "command": _write_exited_leader_command(workspace),
            "timeout_ms": 150,
        },
    )

    descendant_pid = int((workspace / "descendant.pid").read_text())
    stat_path = Path(f"/proc/{descendant_pid}/stat")
    if stat_path.exists():
        state = stat_path.read_text().rsplit(")", 1)[1].split()[0]
        assert state == "Z"
    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "execution_timeout"
    time.sleep(0.55)
    assert not (workspace / "after-exited-leader").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_fast_command_reaps_leader_without_hanging(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-fast-reap",
            **IDENTITY,
            "command": "printf $$ > fast-leader.pid",
            "timeout_ms": 2_000,
        },
    )

    leader_pid = int((workspace / "fast-leader.pid").read_text())
    assert responses[-1]["status"] == "completed"
    assert not Path(f"/proc/{leader_pid}").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_shutdown_contains_group_after_leader_already_exited(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = _Broker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
        terminate_grace=0.03,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    connection, reader = _open_operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-shutdown-exited-leader",
            **IDENTITY,
            "command": _write_exited_leader_command(workspace),
            "timeout_ms": 2_000,
        },
    )
    assert decode_response(reader.readline())["type"] == "acknowledged"
    deadline = time.monotonic() + 1
    while not (workspace / "descendant.pid").is_file():
        assert time.monotonic() < deadline
        time.sleep(0.005)
    leader_pid = int((workspace / "leader.pid").read_text())
    while True:
        leader_stat = Path(f"/proc/{leader_pid}/stat")
        if (
            leader_stat.exists()
            and leader_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        ):
            break
        assert time.monotonic() < deadline
        time.sleep(0.005)

    server.shutdown()
    terminal = decode_response(reader.readline())
    descendant_pid = int((workspace / "descendant.pid").read_text())
    descendant_stat = Path(f"/proc/{descendant_pid}/stat")
    if descendant_stat.exists():
        assert descendant_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    reader.close()
    connection.close()

    assert terminal["status"] == "cancelled"
    time.sleep(0.55)
    assert not (workspace / "after-exited-leader").exists()
    assert broker.active is False
    thread.join(timeout=2)


def test_concurrent_cancel_cannot_reap_during_leader_exit_observation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    waitid_entered = threading.Event()
    release_waitid = threading.Event()
    thread_exceptions: list[BaseException] = []
    real_waitid = os.waitid

    def controlled_waitid(id_type: int, process_id: int, options: int):
        waitid_entered.set()
        assert release_waitid.wait(2)
        return real_waitid(id_type, process_id, options)

    def capture_thread_exception(args: threading.ExceptHookArgs) -> None:
        thread_exceptions.append(args.exc_value)

    monkeypatch.setattr(os, "waitid", controlled_waitid)
    monkeypatch.setattr(threading, "excepthook", capture_thread_exception)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        terminate_grace=0.01,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    connection, reader = _open_operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-cancel-observation-race",
            **IDENTITY,
            "command": _write_exited_leader_command(workspace),
            "timeout_ms": 2_000,
        },
    )
    assert decode_response(reader.readline())["type"] == "acknowledged"
    assert waitid_entered.wait(1)
    leader_pid = int((workspace / "leader.pid").read_text())
    cancelled: list[dict[str, object]] = []
    cancel_thread = threading.Thread(
        target=lambda: cancelled.extend(
            _operation(
                server.socket_path,
                {
                    "protocol": PROTOCOL,
                    "type": "cancel_execution",
                    "request_id": "request-cancel-observation",
                    **IDENTITY,
                },
            )
        )
    )
    cancel_thread.start()
    reap_deadline = time.monotonic() + 0.3
    while Path(f"/proc/{leader_pid}").exists() and time.monotonic() < reap_deadline:
        time.sleep(0.005)
    release_waitid.set()

    terminal = decode_response(reader.readline())
    cancel_thread.join(timeout=2)
    descendant_pid = int((workspace / "descendant.pid").read_text())
    descendant_stat = Path(f"/proc/{descendant_pid}/stat")
    if descendant_stat.exists():
        assert descendant_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    reader.close()
    connection.close()

    assert not cancel_thread.is_alive()
    assert terminal["status"] == "cancelled"
    assert cancelled[-1]["status"] == "cancelled"
    assert all(frame.get("error") != "execution_lost" for frame in cancelled)
    assert thread_exceptions == []
    time.sleep(0.55)
    assert not (workspace / "after-exited-leader").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_unproven_process_group_returns_bounded_containment_terminal(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        terminate_grace=0.01,
        containment_proof_timeout=0.03,
        process_group_probe=lambda _process_group: True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-unproven-group",
        **IDENTITY,
        "command": "printf $$ > unproven-leader.pid; sleep 5",
        "timeout_ms": 2_000,
    }
    connection, reader = _open_operation(server.socket_path, request)
    assert decode_response(reader.readline())["type"] == "acknowledged"
    deadline = time.monotonic() + 1
    while not (workspace / "unproven-leader.pid").is_file():
        assert time.monotonic() < deadline
        time.sleep(0.005)

    started = time.monotonic()
    cancelled = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "cancel_execution",
            "request_id": "request-unproven-cancel",
            **IDENTITY,
        },
    )
    terminal = decode_response(reader.readline())
    connection.settimeout(0.5)
    assert reader.readline() == b""
    reader.close()
    connection.close()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as health_connection:
        health_connection.connect(str(server.socket_path))
        health_connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-unproven-health",
                    "execution_id": "execution-unproven-health",
                }
            )
        )
        health_connection.shutdown(socket.SHUT_WR)
        health = _read_frames(health_connection)

    assert time.monotonic() - started < 1
    assert terminal["status"] == "failed"
    assert terminal["error"] == "process_containment_failed"
    assert cancelled[-1]["status"] == "failed"
    assert cancelled[-1]["error"] == "process_containment_failed"
    assert health[0]["status"] == "draining"
    record = json.loads(next((tmp_path / "state").glob("*/record.json")).read_text())
    assert record["terminal"]["error"] == "process_containment_failed"
    leader_pid = int((workspace / "unproven-leader.pid").read_text())
    os.waitpid(leader_pid, 0)
    server.shutdown()
    thread.join(timeout=2)


def test_attach_cursor_and_mismatch_fencing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-run",
        **IDENTITY,
        "command": "printf first; sleep .05; printf second >&2",
        "timeout_ms": 2_000,
    }
    original = _operation(server.socket_path, request)
    outputs = [frame for frame in original if frame["type"] == "output"]
    assert len(outputs) == 2

    attached = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-attach",
            **IDENTITY,
            "offset": outputs[0]["sequence"],
        },
    )
    mismatch = _operation(
        server.socket_path,
        {
            **request,
            "request_id": "request-mismatch",
            "execution_id": "execution-other",
            "command": "printf bad > mismatched-side-effect",
        },
    )

    assert [frame["data"] for frame in attached if frame["type"] == "output"] == [
        "second"
    ]
    assert attached[-1]["status"] == "completed"
    assert mismatch[-1]["error"] == "execution_identity_mismatch"
    assert not (workspace / "mismatched-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_output_is_sanitized_ordered_and_bounded(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        capture_limit=8,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-output",
            **IDENTITY,
            "command": "printf '\\033[31mabcdefghijklmnop\\000'",
            "timeout_ms": 2_000,
        },
    )
    outputs = [frame for frame in responses if frame["type"] == "output"]

    assert [frame["sequence"] for frame in outputs] == list(range(1, len(outputs) + 1))
    assert sum(len(str(frame["data"]).encode()) for frame in outputs) <= 8
    assert all(
        "\x1b" not in str(frame["data"]) and "\x00" not in str(frame["data"])
        for frame in outputs
    )
    assert responses[-1]["type"] == "terminal"
    server.shutdown()
    thread.join(timeout=2)


def test_command_environment_strips_provider_credentials_and_uses_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PWC_CHAT_OPENAI_API_KEY", "must-not-enter")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-env",
            **IDENTITY,
            "command": 'printf \'%s|%s\' "$PWD" "${PWC_CHAT_OPENAI_API_KEY-unset}"',
            "timeout_ms": 2_000,
        },
    )

    output = "".join(
        str(frame["data"]) for frame in responses if frame["type"] == "output"
    )
    assert output == f"{workspace}|unset"
    server.shutdown()
    thread.join(timeout=2)


def test_restart_turns_durable_acceptance_into_execution_lost(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker_entered = threading.Event()
    never_release = threading.Event()

    def blocked_broker(payload: dict[str, object]) -> dict[str, object]:
        if payload["operation"] == "install":
            broker_entered.set()
            never_release.wait()
        return {"ok": True, "active": payload["operation"] == "install"}

    state_path = tmp_path / "state"
    first = ExecutorServer(
        socket_path=tmp_path / "first" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=blocked_broker,
        command_preexec=None,
    )
    first_thread = threading.Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    assert first.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-before-crash",
        **IDENTITY,
        "command": "printf x >> must-not-run",
        "timeout_ms": 2_000,
    }
    connection, reader = _open_operation(first.socket_path, request)
    assert decode_response(reader.readline())["type"] == "acknowledged"
    assert broker_entered.wait(2)
    reader.close()
    connection.close()
    record_path = next(state_path.glob("*/record.json"))
    running_record = json.loads(record_path.read_text())
    running_record["phase"] = "running"
    record_path.write_text(json.dumps(running_record))
    prior_process = subprocess.Popen(
        ["/bin/bash", "-lc", "sleep 1; printf old > prior-side-effect"],
        cwd=workspace,
        start_new_session=True,
    )

    class RecoveryBroker(_Broker):
        def __init__(self) -> None:
            super().__init__()
            self.active = True
            self.operations: list[str] = []

        def __call__(self, payload: dict[str, object]) -> dict[str, object]:
            self.operations.append(str(payload["operation"]))
            return super().__call__(payload)

    recovery_broker = RecoveryBroker()
    recovered = ExecutorServer(
        socket_path=tmp_path / "recovered" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=recovery_broker,
        command_preexec=None,
    )
    recovered_thread = threading.Thread(target=recovered.serve_forever, daemon=True)
    recovered_thread.start()
    assert recovered.wait_until_ready(2)
    attached = _operation(
        recovered.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-after-crash",
            **IDENTITY,
            "offset": 0,
        },
    )
    duplicate = _operation(recovered.socket_path, request)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as health_connection:
        health_connection.connect(str(recovered.socket_path))
        health_connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-recovery-health",
                    "execution_id": "execution-recovery-health",
                }
            )
        )
        health_connection.shutdown(socket.SHUT_WR)
        health = _read_frames(health_connection)
    rejected = _operation(
        recovered.socket_path,
        {
            **request,
            "request_id": "request-new-after-recovery",
            "turn_id": "turn-new",
            "execution_id": "execution-new",
            "tool_call_id": "tool-new",
            "command": "printf bad > recovery-overlap",
        },
    )

    assert attached[-1]["status"] == "failed"
    assert attached[-1]["error"] == "execution_lost"
    assert duplicate[-1]["error"] == "execution_lost"
    assert health[0]["status"] == "draining"
    assert rejected[-1]["error"] == "executor_containment_failure"
    assert recovery_broker.operations == ["status", "clear"]
    assert recovery_broker.active is False
    assert prior_process.poll() is None
    assert not (workspace / "recovery-overlap").exists()
    os.killpg(prior_process.pid, signal.SIGKILL)
    prior_process.wait()
    assert not (workspace / "must-not-run").exists()
    recovered.shutdown()
    recovered_thread.join(timeout=2)
    first.shutdown()


def test_restart_rejects_evidence_from_an_old_worker_generation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = tmp_path / "state"
    first = ExecutorServer(
        socket_path=tmp_path / "first" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    first_thread = threading.Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    assert first.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-generation-one",
        **IDENTITY,
        "command": "printf old-generation",
        "timeout_ms": 2_000,
    }
    assert _operation(first.socket_path, request)[-1]["status"] == "completed"
    first.shutdown()
    first_thread.join(timeout=2)

    recovered = ExecutorServer(
        socket_path=tmp_path / "second" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-2",
        broker_control=_Broker(),
        command_preexec=None,
    )
    recovered_thread = threading.Thread(target=recovered.serve_forever, daemon=True)
    recovered_thread.start()
    assert recovered.wait_until_ready(2)
    attached = _operation(
        recovered.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-generation-two",
            **IDENTITY,
            "offset": 0,
        },
        worker_generation="worker-2",
    )

    assert attached[-1]["status"] == "failed"
    assert attached[-1]["error"] == "executor_containment_failure"
    assert all(frame["type"] != "output" for frame in attached)
    recovered.shutdown()
    recovered_thread.join(timeout=2)


def test_relay_copies_bytes_through_a_real_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "relay.sock"
    ready = threading.Event()

    def echo_server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                data = b""
                while chunk := connection.recv(1024):
                    data += chunk
                connection.sendall(b"echo:" + data)

    thread = threading.Thread(target=echo_server, daemon=True)
    thread.start()
    assert ready.wait(2)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; "
                "from backend.chat_sandbox_worker.executor_relay import relay; "
                "raise SystemExit(relay(Path(sys.argv[1])))"
            ),
            str(socket_path),
        ],
        input=b"request-bytes",
        capture_output=True,
        timeout=2,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == b"echo:request-bytes"
    assert completed.stderr == b""


def test_workspace_generation_fences_execution(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    ensured = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "ensure_workspace",
            "request_id": "request-ensure",
            **IDENTITY,
        },
    )
    stale_identity = {**IDENTITY, "workspace_generation": 2}

    stale = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-stale",
            **stale_identity,
            "command": "printf bad > stale-side-effect",
            "timeout_ms": 2_000,
        },
    )

    assert [frame["type"] for frame in ensured] == ["acknowledged"]
    assert stale[-1]["status"] == "failed"
    assert stale[-1]["error"] == "workspace_generation_mismatch"
    assert not (workspace / "stale-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_capability_cleanup_failure_is_a_terminal_containment_failure(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def cleanup_fails(payload: dict[str, object]) -> dict[str, object]:
        return {
            "ok": payload["operation"] == "install",
            "active": True,
        }

    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=cleanup_fails,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-cleanup",
            **IDENTITY,
            "command": "printf ran > command-ran",
            "timeout_ms": 2_000,
        },
    )

    assert (workspace / "command-ran").read_text() == "ran"
    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "capability_cleanup_failed"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-contained-health",
                    "execution_id": "execution-contained-health",
                }
            )
        )
        connection.shutdown(socket.SHUT_WR)
        health = _read_frames(connection)
    assert health[0]["status"] == "draining"
    server.shutdown()
    thread.join(timeout=2)


def test_lost_install_response_still_clears_mutated_broker(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class SyntheticLostInstallResponse(ConnectionError):
        pass

    class LostInstallResponseBroker:
        def __init__(self) -> None:
            self.active = False

        def __call__(self, payload: dict[str, object]) -> dict[str, object]:
            if payload["operation"] == "install":
                self.active = True
                raise SyntheticLostInstallResponse("synthetic lost response")
            if payload["operation"] == "clear":
                self.active = False
                raise SyntheticLostInstallResponse("synthetic lost clear response")
            return {"ok": True, "active": self.active}

    broker = LostInstallResponseBroker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-lost-install",
            **IDENTITY,
            "command": "printf bad > lost-install-side-effect",
            "timeout_ms": 2_000,
        },
    )

    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "execution_start_failed"
    assert broker.active is False
    assert not (workspace / "lost-install-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_unexpected_broker_defect_propagates_after_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    propagated: list[BaseException] = []
    propagated_event = threading.Event()

    class DefectiveBroker:
        def __init__(self) -> None:
            self.active = False

        def __call__(self, payload: dict[str, object]) -> dict[str, object]:
            if payload["operation"] == "install":
                self.active = True
                raise AssertionError("synthetic unexpected broker defect")
            if payload["operation"] == "clear":
                self.active = False
            return {"ok": True, "active": self.active}

    def capture_thread_exception(args: threading.ExceptHookArgs) -> None:
        propagated.append(args.exc_value)
        propagated_event.set()

    monkeypatch.setattr(threading, "excepthook", capture_thread_exception)
    broker = DefectiveBroker()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=broker,
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-unexpected-broker",
            **IDENTITY,
            "command": "true",
            "timeout_ms": 2_000,
        },
    )

    assert propagated_event.wait(1)
    assert isinstance(propagated[0], AssertionError)
    assert broker.active is False
    assert responses[-1]["error"] == "execution_lost"
    server.shutdown()
    thread.join(timeout=2)


def test_malformed_or_uncorrelated_frames_execute_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        connection.sendall(b"not-json\n")
        connection.shutdown(socket.SHUT_WR)
        assert connection.recv(1) == b""
    stale = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-stale-worker",
        **IDENTITY,
        "command": "printf bad > stale-worker-side-effect",
        "timeout_ms": 2_000,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(server.socket_path))
        bootstrap = {
            "operation": "executor_connect",
            "capability": "synthetic-capability",
            "workspace_id": IDENTITY["workspace_id"],
            "workspace_generation": IDENTITY["workspace_generation"],
            "session_id": IDENTITY["session_id"],
            "turn_id": IDENTITY["turn_id"],
            "worker_generation": "worker-stale",
        }
        connection.sendall(
            EXECUTOR_BOOTSTRAP_PREFIX
            + json.dumps(bootstrap, separators=(",", ":")).encode()
            + b"\n"
            + encode_request(stale)
        )
        connection.shutdown(socket.SHUT_WR)
        assert connection.recv(1) == b""

    assert not (workspace / "stale-worker-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_client_disconnect_during_response_is_only_a_transport_loss(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    thread_exceptions: list[BaseException] = []
    monkeypatch.setattr(
        threading,
        "excepthook",
        lambda args: thread_exceptions.append(args.exc_value),
    )
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(server.socket_path))
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    connection.sendall(
        encode_request(
            {
                "protocol": PROTOCOL,
                "type": "health",
                "request_id": "request-reset-health",
                "execution_id": "execution-reset-health",
            }
        )
    )
    connection.close()
    time.sleep(0.05)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as health_connection:
        health_connection.connect(str(server.socket_path))
        health_connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-after-reset",
                    "execution_id": "execution-after-reset",
                }
            )
        )
        health_connection.shutdown(socket.SHUT_WR)
        health = _read_frames(health_connection)

    assert thread_exceptions == []
    assert health[0]["status"] == "ok"
    server.shutdown()
    thread.join(timeout=2)


def test_only_one_command_runs_at_a_time_in_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    first_request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-first",
        **IDENTITY,
        "command": "sleep .1; printf ready > serialized-marker",
        "timeout_ms": 2_000,
    }
    second_identity = {
        **IDENTITY,
        "turn_id": "turn-2",
        "execution_id": "execution-2",
        "tool_call_id": "tool-2",
    }
    second_request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-second",
        **second_identity,
        "command": "test -f serialized-marker",
        "timeout_ms": 2_000,
    }
    results: dict[str, list[dict[str, object]]] = {}
    first_thread = threading.Thread(
        target=lambda: results.setdefault(
            "first", _operation(server.socket_path, first_request)
        )
    )
    second_thread = threading.Thread(
        target=lambda: results.setdefault(
            "second", _operation(server.socket_path, second_request)
        )
    )
    first_thread.start()
    time.sleep(0.02)
    second_thread.start()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert results["first"][-1]["exit_code"] == 0
    assert results["second"][-1]["exit_code"] == 0
    server.shutdown()
    thread.join(timeout=2)


def test_invalid_utf8_at_chunk_limit_still_reaches_terminal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        capture_limit=64 * 1024,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-invalid-utf8",
            **IDENTITY,
            "command": "python -c 'import os; os.write(1, b\"\\xff\" * 65536)'",
            "timeout_ms": 2_000,
        },
    )

    assert responses[-1]["type"] == "terminal"
    assert responses[-1]["status"] == "completed"
    assert all(
        len(str(frame["data"]).encode()) <= 64 * 1024
        for frame in responses
        if frame["type"] == "output"
    )
    server.shutdown()
    thread.join(timeout=2)


def test_terminal_write_failure_exposes_no_success_and_drains(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_replace = os.replace

    def fail_terminal_replace(source: str | bytes, target: str | bytes) -> None:
        value = json.loads(Path(source).read_text(encoding="utf-8"))
        if value.get("phase") == "terminal":
            raise OSError("synthetic terminal persistence failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_terminal_replace)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    connection, reader = _open_operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "exec",
            "request_id": "request-terminal-write",
            **IDENTITY,
            "command": "true",
            "timeout_ms": 2_000,
        },
    )
    connection.settimeout(0.5)

    assert decode_response(reader.readline())["type"] == "acknowledged"
    assert reader.readline() == b""
    reader.close()
    connection.close()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as health_connection:
        health_connection.connect(str(server.socket_path))
        health_connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-terminal-health",
                    "execution_id": "execution-terminal-health",
                }
            )
        )
        health_connection.shutdown(socket.SHUT_WR)
        health = _read_frames(health_connection)
    assert health[0]["status"] == "draining"
    server.shutdown()
    thread.join(timeout=2)


def test_acceptance_write_failure_leaves_no_attachable_hanging_execution(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_replace = os.replace
    failed = False

    def fail_first_acceptance(source: str | bytes, target: str | bytes) -> None:
        nonlocal failed
        value = json.loads(Path(source).read_text(encoding="utf-8"))
        if value.get("phase") == "accepted" and not failed:
            failed = True
            raise OSError("synthetic acceptance persistence failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_first_acceptance)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-acceptance-write",
        **IDENTITY,
        "command": "printf bad > acceptance-side-effect",
        "timeout_ms": 2_000,
    }

    assert _operation(server.socket_path, request) == []
    retry = _operation(
        server.socket_path,
        {**request, "request_id": "request-acceptance-retry"},
    )

    assert retry[-1]["status"] == "failed"
    assert retry[-1]["error"] == "executor_containment_failure"
    assert not (workspace / "acceptance-side-effect").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_workspace_binding_persistence_failure_is_typed_and_drains(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_replace = os.replace

    def fail_workspace_replace(source: str | bytes, target: str | bytes) -> None:
        if Path(target).name == "workspace.json":
            raise OSError("synthetic workspace persistence failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_workspace_replace)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)

    responses = _operation(
        server.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "ensure_workspace",
            "request_id": "request-workspace-persistence",
            **IDENTITY,
        },
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as health_connection:
        health_connection.connect(str(server.socket_path))
        health_connection.sendall(
            encode_request(
                {
                    "protocol": PROTOCOL,
                    "type": "health",
                    "request_id": "request-workspace-persistence-health",
                    "execution_id": "execution-workspace-persistence-health",
                }
            )
        )
        health_connection.shutdown(socket.SHUT_WR)
        health = _read_frames(health_connection)

    assert responses[-1]["status"] == "failed"
    assert responses[-1]["error"] == "executor_containment_failure"
    assert health[0]["status"] == "draining"
    assert not (tmp_path / "state" / "workspace.json").exists()
    server.shutdown()
    thread.join(timeout=2)


def test_thread_start_failure_is_durable_execution_lost_for_duplicates(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class FailedStartThread(threading.Thread):
        def start(self) -> None:
            raise RuntimeError("synthetic thread-start failure")

    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        execution_thread_factory=FailedStartThread,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-thread-start",
        **IDENTITY,
        "command": "printf bad > thread-start-side-effect",
        "timeout_ms": 2_000,
    }

    first = _operation(server.socket_path, request)
    duplicate = _operation(
        server.socket_path,
        {**request, "request_id": "request-thread-start-duplicate"},
    )

    assert first[-1]["error"] == "execution_lost"
    assert duplicate[-1]["error"] == "execution_lost"
    assert not (workspace / "thread-start-side-effect").exists()
    record = json.loads(next((tmp_path / "state").glob("*/record.json")).read_text())
    assert record["phase"] == "terminal"
    assert record["terminal"]["error"] == "execution_lost"
    server.shutdown()
    thread.join(timeout=2)


def test_thread_start_terminal_failure_closes_stream_and_drains(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_replace = os.replace

    class FailedStartThread(threading.Thread):
        def start(self) -> None:
            raise RuntimeError("synthetic thread-start failure")

    def fail_terminal_replace(source: str | bytes, target: str | bytes) -> None:
        value = json.loads(Path(source).read_text(encoding="utf-8"))
        if value.get("phase") == "terminal":
            raise OSError("synthetic execution-lost persistence failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_terminal_replace)
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
        execution_thread_factory=FailedStartThread,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-thread-start-terminal-failure",
        **IDENTITY,
        "command": "true",
        "timeout_ms": 2_000,
    }

    first = _operation(server.socket_path, request)
    duplicate = _operation(
        server.socket_path,
        {**request, "request_id": "request-thread-start-contained"},
    )

    assert [frame["type"] for frame in first] == ["acknowledged"]
    assert duplicate[-1]["error"] == "executor_containment_failure"
    server.shutdown()
    thread.join(timeout=2)


def test_restart_discards_only_an_incomplete_output_journal_tail(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = tmp_path / "state"
    first = ExecutorServer(
        socket_path=tmp_path / "first" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    first_thread = threading.Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    assert first.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-partial-tail",
        **IDENTITY,
        "command": "printf first; sleep .05; printf second >&2",
        "timeout_ms": 2_000,
    }
    original = _operation(first.socket_path, request)
    assert original[-1]["status"] == "completed"
    first.shutdown()
    first_thread.join(timeout=2)
    output_path = next(state_path.glob("*/output.jsonl"))
    with output_path.open("ab") as handle:
        handle.write(b'{"sequence":3')

    recovered = ExecutorServer(
        socket_path=tmp_path / "recovered" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    recovered_thread = threading.Thread(target=recovered.serve_forever, daemon=True)
    recovered_thread.start()
    assert recovered.wait_until_ready(2)
    attached = _operation(
        recovered.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-partial-attach",
            **IDENTITY,
            "offset": 0,
        },
    )

    assert (
        "".join(str(frame["data"]) for frame in attached if frame["type"] == "output")
        == "firstsecond"
    )
    assert attached[-1]["status"] == "completed"
    assert output_path.read_bytes().endswith(b"\n")
    recovered.shutdown()
    recovered_thread.join(timeout=2)


def test_restart_turns_malformed_middle_output_into_execution_lost(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = tmp_path / "state"
    first = ExecutorServer(
        socket_path=tmp_path / "first" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    first_thread = threading.Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    assert first.wait_until_ready(2)
    request = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-malformed-middle",
        **IDENTITY,
        "command": "printf first; sleep .05; printf second >&2",
        "timeout_ms": 2_000,
    }
    original = _operation(first.socket_path, request)
    assert original[-1]["status"] == "completed"
    first.shutdown()
    first_thread.join(timeout=2)
    output_path = next(state_path.glob("*/output.jsonl"))
    lines = output_path.read_bytes().splitlines(keepends=True)
    assert len(lines) == 2
    final_event = json.loads(lines[1])
    final_event["sequence"] = 3
    malformed_middle = {
        "sequence": 2,
        "stream": "stdout",
        "data": "tampered",
        "workspace_id": "workspace-other",
    }
    output_path.write_bytes(
        lines[0]
        + json.dumps(malformed_middle, separators=(",", ":")).encode()
        + b"\n"
        + json.dumps(final_event, separators=(",", ":")).encode()
        + b"\n"
    )

    recovered = ExecutorServer(
        socket_path=tmp_path / "recovered" / "executor.sock",
        state_path=state_path,
        workspace_root=workspace,
        worker_generation="worker-1",
        broker_control=_Broker(),
        command_preexec=None,
    )
    recovered_thread = threading.Thread(target=recovered.serve_forever, daemon=True)
    recovered_thread.start()
    assert recovered.wait_until_ready(2)
    attached = _operation(
        recovered.socket_path,
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-malformed-attach",
            **IDENTITY,
            "offset": 0,
        },
    )

    assert all(frame["type"] != "output" for frame in attached)
    assert attached[-1]["status"] == "failed"
    assert attached[-1]["error"] == "execution_lost"
    recovered.shutdown()
    recovered_thread.join(timeout=2)
