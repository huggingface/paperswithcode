"""Root-owned, durable command executor for an isolated chat workspace."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import selectors
import signal
import socket
import stat
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Callable

from backend.chat_sandbox_worker.control_daemon import (
    _broker_control,
    _start_broker,
    _stop,
)
from backend.chat_sandbox_worker.executor_protocol import (
    MAX_EXECUTION_OUTPUT_FRAMES,
    MAX_FRAME_BYTES,
    MAX_OUTPUT_CHUNK_BYTES,
    PROTOCOL,
    ProtocolError,
    decode_request,
    encode_response,
)
from backend.chat_sandbox_worker.supervisor import (
    SUPERVISOR_PREFIX,
    _demote,
    _harden_proc,
    _not_dumpable,
    _safe_environment,
)

EXECUTOR_BOOTSTRAP_PREFIX = SUPERVISOR_PREFIX
EXECUTOR_SOCKET = Path("/run/pwc-chat-executor/executor.sock")
EXECUTOR_STATE = Path("/var/lib/pwc-chat-executor")
WORKSPACE_ROOT = Path("/workspace")
READONLY_PATHS = frozenset(
    {
        Path("/opt/pwc/PWC_CLI_SKILL.md"),
        Path("/opt/pwc/HF_CLI_SKILL.md"),
        Path("/opt/pwc/S2_CLI_SKILL.md"),
        Path("/opt/pwc/POSTERLY_PUBLISH.md"),
        Path("/opt/pwc/PAPER_AUTHORING.md"),
        Path("/opt/posterly/SKILL.md"),
    }
)
MAX_CAPTURE_BYTES = 256 * 1024
TERMINATE_GRACE_SECONDS = 0.25
EXECUTOR_USER = "pwc-chat"
DEFAULT_EXECUTOR_PIDS_MAX = 64
_DEFAULT = object()
_OPERATION_FIELDS = (
    "workspace_id",
    "workspace_generation",
    "session_id",
    "turn_id",
    "execution_id",
    "tool_call_id",
)


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _sanitize(data: bytes, maximum_bytes: int = MAX_OUTPUT_CHUNK_BYTES) -> str:
    text = data.decode("utf-8", errors="replace")
    sanitized = "".join(
        character
        for character in text
        if not (
            (ord(character) < 0x20 and character not in "\t\n")
            or 0x7F <= ord(character) <= 0x9F
        )
    )
    encoded = sanitized.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return sanitized
    return encoded[:maximum_bytes].decode("utf-8", errors="ignore")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _command_environment() -> dict[str, str]:
    environment = _safe_environment("/home/pwc-chat")
    environment.update(
        {
            "HTTPS_PROXY": "http://127.0.0.1:8766",
            "NO_PROXY": "127.0.0.1,localhost",
            "NODE_EXTRA_CA_CERTS": "/tmp/pwc-webfetch-ca.pem",
            "PWC_API_URL": "http://127.0.0.1:8765/api/v1",
        }
    )
    forbidden = (
        "API_KEY",
        "CREDENTIAL",
        "OPENAI",
        "OPENROUTER",
        "ANTHROPIC",
        "PASSWORD",
        "SECRET",
        "TOKEN",
    )
    environment = {
        key: value
        for key, value in environment.items()
        if not any(marker in key.upper() for marker in forbidden)
    }
    environment.update(
        {
            "S2_API_KEY": "sandbox-gateway",
            "S2_API_URL": "http://127.0.0.1:8765/semantic-scholar/graph/v1",
        }
    )
    return environment


def _demote_command() -> None:
    _demote(
        EXECUTOR_USER,
        pids_max=int(
            os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", str(DEFAULT_EXECUTOR_PIDS_MAX))
        ),
    )()


@dataclass
class _Execution:
    identity: dict[str, object]
    fingerprint: str
    directory: Path
    events: list[dict[str, object]] = field(default_factory=list)
    terminal: dict[str, object] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)
    cancel: threading.Event = field(default_factory=threading.Event)
    process: subprocess.Popen[bytes] | None = None
    process_group: int | None = None
    process_group_contained: bool = False
    process_containment_failed: bool = False
    termination_lock: threading.Lock = field(default_factory=threading.Lock)
    captured_bytes: int = 0
    persistence_failed: bool = False


class _ContainmentFailure(RuntimeError):
    """An internal durability failure requires fail-closed admission."""


class ExecutorServer:
    """Serve executor protocol requests over a private Unix socket."""

    def __init__(
        self,
        *,
        socket_path: Path = EXECUTOR_SOCKET,
        state_path: Path = EXECUTOR_STATE,
        workspace_root: Path = WORKSPACE_ROOT,
        readonly_paths: frozenset[Path] = READONLY_PATHS,
        worker_generation: str | None = None,
        broker_control: Callable[
            [dict[str, object]], dict[str, object]
        ] = _broker_control,
        execution_thread_factory: Callable[..., threading.Thread] = threading.Thread,
        command_preexec: Callable[[], None] | None | object = _DEFAULT,
        capture_limit: int = MAX_CAPTURE_BYTES,
        read_chunk_size: int = MAX_OUTPUT_CHUNK_BYTES,
        terminate_grace: float = TERMINATE_GRACE_SECONDS,
        containment_proof_timeout: float = TERMINATE_GRACE_SECONDS,
        process_group_probe: Callable[[int], bool] | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.state_path = state_path
        self.workspace_root = workspace_root
        self.readonly_paths = readonly_paths
        self.worker_generation = worker_generation or os.environ.get(
            "PWC_CHAT_WORKER_GENERATION", ""
        )
        self.broker_control = broker_control
        self.execution_thread_factory = execution_thread_factory
        self.command_preexec = (
            _demote_command if command_preexec is _DEFAULT else command_preexec
        )
        self.capture_limit = capture_limit
        if not 1 <= read_chunk_size <= MAX_OUTPUT_CHUNK_BYTES:
            raise ValueError("Invalid executor read chunk size")
        self.read_chunk_size = read_chunk_size
        self.terminate_grace = terminate_grace
        self.containment_proof_timeout = containment_proof_timeout
        self.process_group_probe = (
            process_group_probe or self._process_group_has_live_member
        )
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._contained = threading.Event()
        self._server: socket.socket | None = None
        self._executions: dict[tuple[str, str], _Execution] = {}
        self._workspace: tuple[str, int] | None = None
        self._lock = threading.Lock()
        self._workspace_lock = threading.Lock()

    def wait_until_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def serve_forever(self) -> None:
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_path.parent.chmod(0o700)
        self.state_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_path.chmod(0o700)
        self._recover()
        self.socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = server
        server.bind(str(self.socket_path))
        self.socket_path.chmod(0o600)
        server.listen(16)
        server.settimeout(0.1)
        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                threading.Thread(
                    target=self._handle_connection,
                    args=(connection,),
                    daemon=True,
                ).start()
        finally:
            server.close()
            self.socket_path.unlink(missing_ok=True)

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            executions = list(self._executions.values())
        for execution in executions:
            if execution.terminal is None:
                execution.cancel.set()

    def _handle_connection(self, connection: socket.socket) -> None:
        with connection:
            try:
                reader = connection.makefile("rb", buffering=0)
            except OSError:
                return
            with reader:
                try:
                    first = reader.readline(MAX_FRAME_BYTES + 1)
                    if first.startswith(EXECUTOR_BOOTSTRAP_PREFIX):
                        bootstrap_line = first
                        request_line = reader.readline(MAX_FRAME_BYTES + 1)
                    else:
                        bootstrap_line = None
                        request_line = first
                except OSError:
                    return
                try:
                    bootstrap = (
                        self._decode_bootstrap(bootstrap_line)
                        if bootstrap_line is not None
                        else None
                    )
                    request = decode_request(request_line)
                    if request["type"] != "health":
                        if bootstrap is None:
                            return
                        self._correlate_bootstrap(bootstrap, request)
                except ProtocolError:
                    return
                try:
                    self._dispatch_request(connection, request, bootstrap)
                except _ContainmentFailure:
                    try:
                        self._ack(connection, request)
                        self._send_terminal(
                            connection,
                            request,
                            {
                                "status": "failed",
                                "exit_code": None,
                                "error": "executor_containment_failure",
                            },
                        )
                    except (
                        BrokenPipeError,
                        ConnectionAbortedError,
                        ConnectionResetError,
                    ):
                        return
                except (
                    BrokenPipeError,
                    ConnectionAbortedError,
                    ConnectionResetError,
                ):
                    return

    def _dispatch_request(
        self,
        connection: socket.socket,
        request: dict[str, object],
        bootstrap: dict[str, object] | None,
    ) -> None:
        if request["type"] == "health":
            self._send_health(connection, request)
            return
        assert bootstrap is not None
        operation = request["type"]
        if self._contained.is_set():
            if self._can_retrieve_contained_execution(request):
                if operation == "exec":
                    self._exec(connection, request, bootstrap)
                else:
                    self._attach(connection, request)
                return
            self._ack(connection, request)
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "executor_containment_failure",
                },
            )
            return
        if operation != "ensure_workspace" and not self._bind_workspace(request):
            self._ack(connection, request)
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "workspace_generation_mismatch",
                },
            )
            return
        if operation == "exec":
            self._exec(connection, request, bootstrap)
        elif operation == "attach_execution":
            self._attach(connection, request)
        elif operation == "cancel_execution":
            self._cancel(connection, request)
        elif operation == "ensure_workspace":
            self._ensure_workspace(connection, request)
        elif operation == "read_file":
            self._read_file(connection, request)

    def _can_retrieve_contained_execution(self, request: dict[str, object]) -> bool:
        operation = request["type"]
        if operation not in {"exec", "attach_execution"}:
            return False
        key = (str(request["turn_id"]), str(request["tool_call_id"]))
        with self._lock:
            execution = self._executions.get(key)
        if (
            execution is None
            or execution.terminal is None
            or any(
                execution.identity[field] != request[field]
                for field in _OPERATION_FIELDS
            )
        ):
            return False
        return operation == "attach_execution" or (
            execution.fingerprint == self._fingerprint(request)
        )

    def _decode_bootstrap(self, line: bytes) -> dict[str, object]:
        if len(line) > 64 * 1024 or not line.endswith(b"\n"):
            raise ProtocolError("Invalid executor bootstrap")

        def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ProtocolError("Invalid executor bootstrap")
                result[key] = value
            return result

        try:
            value = json.loads(
                line[len(EXECUTOR_BOOTSTRAP_PREFIX) :],
                object_pairs_hook=exact_object,
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProtocolError("Invalid executor bootstrap") from error
        required = {
            "operation",
            "capability",
            "workspace_id",
            "workspace_generation",
            "session_id",
            "turn_id",
            "worker_generation",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value["operation"] != "executor_connect"
            or not all(
                isinstance(value[key], str) and value[key]
                for key in required - {"workspace_generation"}
            )
            or isinstance(value["workspace_generation"], bool)
            or not isinstance(value["workspace_generation"], int)
            or value["workspace_generation"] <= 0
        ):
            raise ProtocolError("Invalid executor bootstrap")
        return value

    def _correlate_bootstrap(
        self, bootstrap: dict[str, object], request: dict[str, object]
    ) -> None:
        for identity_field in (
            "workspace_id",
            "workspace_generation",
            "session_id",
            "turn_id",
        ):
            if bootstrap[identity_field] != request[identity_field]:
                raise ProtocolError("Uncorrelated executor bootstrap")
        if bootstrap["worker_generation"] != self.worker_generation:
            raise ProtocolError("Stale executor worker generation")

    def _send_health(
        self, connection: socket.socket, request: dict[str, object]
    ) -> None:
        connection.sendall(
            encode_response(
                {
                    "protocol": PROTOCOL,
                    "type": "health_result",
                    "request_id": request["request_id"],
                    "execution_id": request["execution_id"],
                    "status": "draining" if self._contained.is_set() else "ok",
                }
            )
        )

    def _response_base(self, request: dict[str, object]) -> dict[str, object]:
        return {
            "protocol": PROTOCOL,
            "request_id": request["request_id"],
            **{field: request[field] for field in _OPERATION_FIELDS},
        }

    def _ack(self, connection: socket.socket, request: dict[str, object]) -> None:
        connection.sendall(
            encode_response(
                {
                    **self._response_base(request),
                    "type": "acknowledged",
                    "operation": request["type"],
                }
            )
        )

    def _ensure_workspace(
        self, connection: socket.socket, request: dict[str, object]
    ) -> None:
        if not self._bind_workspace(request):
            self._ack(connection, request)
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "workspace_generation_mismatch",
                },
            )
            return
        self._ack(connection, request)

    def _bind_workspace(self, request: dict[str, object]) -> bool:
        requested = (str(request["workspace_id"]), int(request["workspace_generation"]))
        with self._lock:
            if self._workspace is None:
                try:
                    _atomic_json(
                        self.state_path / "workspace.json",
                        {
                            "workspace_id": requested[0],
                            "workspace_generation": requested[1],
                            "worker_generation": self.worker_generation,
                        },
                    )
                except OSError as error:
                    self._contained.set()
                    raise _ContainmentFailure from error
                self._workspace = requested
            return self._workspace == requested

    def _fingerprint(self, request: dict[str, object]) -> str:
        immutable = {
            key: request[key] for key in (*_OPERATION_FIELDS, "command", "timeout_ms")
        }
        immutable["worker_generation"] = self.worker_generation
        return hashlib.sha256(
            json.dumps(immutable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _exec(
        self,
        connection: socket.socket,
        request: dict[str, object],
        bootstrap: dict[str, object],
    ) -> None:
        key = (str(request["turn_id"]), str(request["tool_call_id"]))
        fingerprint = self._fingerprint(request)
        with self._lock:
            execution = self._executions.get(key)
            if execution is None:
                directory = (
                    self.state_path
                    / hashlib.sha256(f"{key[0]}\0{key[1]}".encode()).hexdigest()
                )
                execution = _Execution(
                    identity={field: request[field] for field in _OPERATION_FIELDS},
                    fingerprint=fingerprint,
                    directory=directory,
                )
                try:
                    directory.mkdir(mode=0o700)
                    _atomic_json(
                        directory / "record.json",
                        {
                            "phase": "accepted",
                            "identity": execution.identity,
                            "fingerprint": fingerprint,
                            "worker_generation": self.worker_generation,
                            "terminal": None,
                        },
                    )
                    _fsync_directory(self.state_path)
                except OSError:
                    self._contained.set()
                    return
                self._executions[key] = execution
                worker = self.execution_thread_factory(
                    target=self._run,
                    args=(
                        execution,
                        str(request["command"]),
                        int(request["timeout_ms"]),
                        bootstrap,
                    ),
                    daemon=True,
                )
                try:
                    worker.start()
                except RuntimeError:
                    self._finish(execution, "failed", None, "execution_lost")
            elif execution.fingerprint != fingerprint:
                self._ack(connection, request)
                self._send_terminal(
                    connection,
                    request,
                    {
                        "status": "failed",
                        "exit_code": None,
                        "error": "execution_identity_mismatch",
                    },
                )
                return
        self._ack(connection, request)
        self._stream(connection, request, execution, 0)

    def _attach(self, connection: socket.socket, request: dict[str, object]) -> None:
        key = (str(request["turn_id"]), str(request["tool_call_id"]))
        with self._lock:
            execution = self._executions.get(key)
        self._ack(connection, request)
        if execution is None or any(
            execution.identity[field] != request[field] for field in _OPERATION_FIELDS
        ):
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "execution_not_found",
                },
            )
            return
        self._stream(connection, request, execution, int(request["offset"]))

    def _cancel(self, connection: socket.socket, request: dict[str, object]) -> None:
        key = (str(request["turn_id"]), str(request["tool_call_id"]))
        with self._lock:
            execution = self._executions.get(key)
        self._ack(connection, request)
        if execution is None or any(
            execution.identity[field] != request[field] for field in _OPERATION_FIELDS
        ):
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "execution_not_found",
                },
            )
            return
        execution.cancel.set()
        process = execution.process
        if process is not None:
            self._terminate(execution)
        self._stream(connection, request, execution, 0)

    def _run(
        self,
        execution: _Execution,
        command: str,
        timeout_ms: int,
        bootstrap: dict[str, object],
    ) -> None:
        with self._workspace_lock:
            if execution.cancel.is_set():
                self._finish(execution, "cancelled", None, None)
                return
            install_attempted = False
            outcome: tuple[str, int | None, str | None] | None = None
            try:
                try:
                    install_attempted = True
                    response = self.broker_control(
                        {
                            "operation": "install",
                            "capability": bootstrap["capability"],
                            "session_id": execution.identity["session_id"],
                            "turn_id": execution.identity["turn_id"],
                        }
                    )
                    if (
                        not isinstance(response, dict)
                        or response.get("ok") is not True
                        or response.get("active") is not True
                    ):
                        raise RuntimeError("Broker did not confirm capability install")
                except (OSError, RuntimeError, ValueError):
                    outcome = ("failed", None, "execution_start_failed")
                else:
                    try:
                        _atomic_json(
                            execution.directory / "record.json",
                            {
                                "phase": "running",
                                "identity": execution.identity,
                                "fingerprint": execution.fingerprint,
                                "worker_generation": self.worker_generation,
                                "terminal": None,
                            },
                        )
                        process = subprocess.Popen(
                            ["/bin/bash", "-lc", command],
                            cwd=self.workspace_root,
                            env=_command_environment(),
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            preexec_fn=self.command_preexec,
                            start_new_session=True,
                            bufsize=0,
                        )
                        execution.process_group = process.pid
                        execution.process = process
                        outcome = self._capture(execution, process, timeout_ms / 1000)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        process = execution.process
                        if process is not None:
                            contained = self._terminate(execution)
                        else:
                            contained = True
                        outcome = (
                            ("failed", None, "execution_start_failed")
                            if contained
                            else ("failed", None, "process_containment_failed")
                        )
            finally:
                try:
                    process = execution.process
                    if outcome is None and process is not None:
                        if not self._terminate(execution):
                            outcome = (
                                "failed",
                                None,
                                "process_containment_failed",
                            )
                finally:
                    cleanup_proven = not install_attempted
                    try:
                        if install_attempted:
                            cleanup_proven = self._clear_or_prove_inactive(execution)
                    finally:
                        if not cleanup_proven:
                            self._contained.set()
                            outcome = (
                                "failed",
                                None,
                                "capability_cleanup_failed",
                            )
                        elif outcome is None:
                            outcome = ("failed", None, "execution_lost")
                        self._finish(execution, *outcome)

    def _clear_or_prove_inactive(self, execution: _Execution) -> bool:
        try:
            response = self.broker_control(
                {
                    "operation": "clear",
                    "session_id": execution.identity["session_id"],
                    "turn_id": execution.identity["turn_id"],
                }
            )
            if (
                isinstance(response, dict)
                and response.get("ok") is True
                and response.get("active") is False
            ):
                return True
        # Broker transport loss may surface after either mutation. Always attempt
        # the independent status proof before deciding whether to drain.
        except (OSError, RuntimeError, ValueError):
            pass
        try:
            response = self.broker_control({"operation": "status"})
        except (OSError, RuntimeError, ValueError):
            return False
        return (
            isinstance(response, dict)
            and response.get("ok") is True
            and response.get("active") is False
        )

    def _prove_recovered_broker_inactive(self, execution: _Execution) -> bool:
        try:
            response = self.broker_control({"operation": "status"})
        except (OSError, RuntimeError, ValueError):
            response = None
        if (
            isinstance(response, dict)
            and response.get("ok") is True
            and response.get("active") is False
        ):
            return True
        return self._clear_or_prove_inactive(execution)

    def _capture(
        self, execution: _Execution, process: subprocess.Popen[bytes], timeout: float
    ) -> tuple[str, int | None, str | None]:
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + timeout
        timed_out = False
        while True:
            if execution.cancel.is_set() or time.monotonic() >= deadline:
                timed_out = not execution.cancel.is_set()
                if not self._terminate(execution):
                    selector.close()
                    process.stdout.close()
                    process.stderr.close()
                    return "failed", None, "process_containment_failed"
            for key, _ in selector.select(0.02 if selector.get_map() else 0):
                stream: BinaryIO = key.fileobj
                data = os.read(stream.fileno(), self.read_chunk_size)
                if not data:
                    selector.unregister(stream)
                    continue
                self._append_output(execution, str(key.data), data)
            if not selector.get_map() and self._reap_exited_inactive_process_group(
                execution
            ):
                break
            if not selector.get_map():
                time.sleep(0.005)
        if execution.cancel.is_set():
            return "cancelled", None, None
        if timed_out:
            return "failed", None, "execution_timeout"
        return "completed", int(process.returncode), None

    @staticmethod
    def _leader_exited(process: subprocess.Popen[bytes]) -> bool:
        return (
            os.waitid(
                os.P_PID,
                process.pid,
                os.WEXITED | os.WNOHANG | os.WNOWAIT,
            )
            is not None
        )

    def _reap_exited_inactive_process_group(self, execution: _Execution) -> bool:
        with execution.termination_lock:
            if execution.process_group_contained:
                return True
            process = execution.process
            process_group = execution.process_group
            if (
                process is None
                or process_group is None
                or not self._leader_exited(process)
                or self.process_group_probe(process_group)
            ):
                return False
            process.wait()
            execution.process_group_contained = True
            return True

    def _terminate(self, execution: _Execution) -> bool:
        with execution.termination_lock:
            if execution.process_group_contained:
                return True
            if execution.process_containment_failed:
                return False
            process = execution.process
            process_group = execution.process_group
            if process is None or process_group is None:
                raise RuntimeError("Execution process group was not captured")
            try:
                os.killpg(process_group, signal.SIGTERM)
            except ProcessLookupError:
                pass
            # The unreaped leader pins the numeric group ID while descendants
            # handle TERM, preventing reuse before the final group-wide signal.
            time.sleep(self.terminate_grace)
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            containment_deadline = time.monotonic() + self.containment_proof_timeout
            while self.process_group_probe(process_group):
                if time.monotonic() >= containment_deadline:
                    self._contained.set()
                    execution.process_containment_failed = True
                    return False
                time.sleep(0.005)
            process.wait()
            execution.process_group_contained = True
            return True

    @staticmethod
    def _process_group_has_live_member(process_group: int) -> bool:
        for process_path in Path("/proc").iterdir():
            if not process_path.name.isdigit():
                continue
            try:
                fields = (process_path / "stat").read_text().rsplit(")", 1)[1].split()
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            if (
                len(fields) >= 3
                and fields[0] != "Z"
                and int(fields[2]) == process_group
            ):
                return True
        return False

    def _append_output(self, execution: _Execution, stream: str, data: bytes) -> None:
        with execution.condition:
            if (
                execution.terminal is not None
                or execution.captured_bytes >= self.capture_limit
                or len(execution.events) >= MAX_EXECUTION_OUTPUT_FRAMES
            ):
                return
            remaining = self.capture_limit - execution.captured_bytes
            data = data[:remaining]
            text = _sanitize(data, min(MAX_OUTPUT_CHUNK_BYTES, remaining))
            if not text:
                return
            event = {
                "sequence": len(execution.events) + 1,
                "stream": stream,
                "data": text,
            }
            with (execution.directory / "output.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                json.dump(event, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(execution.directory)
            execution.captured_bytes += len(text.encode("utf-8"))
            execution.events.append(event)
            execution.condition.notify_all()

    def _finish(
        self,
        execution: _Execution,
        status: str,
        exit_code: int | None,
        error: str | None,
    ) -> None:
        with execution.condition:
            if execution.terminal is not None or execution.persistence_failed:
                return
            terminal = {
                "status": status,
                "exit_code": exit_code,
                "error": error,
            }
            try:
                _atomic_json(
                    execution.directory / "record.json",
                    {
                        "phase": "terminal",
                        "identity": execution.identity,
                        "fingerprint": execution.fingerprint,
                        "worker_generation": self.worker_generation,
                        "terminal": terminal,
                    },
                )
            except OSError:
                execution.persistence_failed = True
                self._contained.set()
                execution.condition.notify_all()
                return
            execution.terminal = terminal
            execution.condition.notify_all()

    def _stream(
        self,
        connection: socket.socket,
        request: dict[str, object],
        execution: _Execution,
        after_sequence: int,
    ) -> None:
        sent = after_sequence
        while True:
            with execution.condition:
                available = [
                    event for event in execution.events if int(event["sequence"]) > sent
                ]
                terminal = execution.terminal
                persistence_failed = execution.persistence_failed
                if not available and terminal is None and not persistence_failed:
                    execution.condition.wait(timeout=0.1)
                    continue
            for event in available:
                connection.sendall(
                    encode_response(
                        {**self._response_base(request), "type": "output", **event}
                    )
                )
                sent = int(event["sequence"])
            if terminal is not None:
                self._send_terminal(connection, request, terminal)
                return
            if persistence_failed:
                return

    def _send_terminal(
        self,
        connection: socket.socket,
        request: dict[str, object],
        terminal: dict[str, object],
    ) -> None:
        connection.sendall(
            encode_response(
                {**self._response_base(request), "type": "terminal", **terminal}
            )
        )

    def _read_file(self, connection: socket.socket, request: dict[str, object]) -> None:
        self._ack(connection, request)
        try:
            data, eof = self._contained_read(
                str(request["path"]),
                int(request["offset"]),
                int(request["max_bytes"]),
            )
            connection.sendall(
                encode_response(
                    {
                        **self._response_base(request),
                        "type": "read_result",
                        "path": request["path"],
                        "offset": request["offset"],
                        "data_base64": base64.b64encode(data).decode("ascii"),
                        "eof": eof,
                    }
                )
            )
        except (OSError, ValueError):
            self._send_terminal(
                connection,
                request,
                {
                    "status": "failed",
                    "exit_code": None,
                    "error": "invalid_workspace_path",
                },
            )

    def _contained_read(
        self, path: str, offset: int, maximum: int
    ) -> tuple[bytes, bool]:
        requested = Path(path)
        if requested.is_absolute():
            if requested not in self.readonly_paths:
                raise ValueError
            root = requested.parent
            parts = (requested.name,)
        else:
            root = self.workspace_root
            parts = requested.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError
            data = os.pread(descriptor, maximum, offset)
            return data, offset + len(data) >= metadata.st_size
        finally:
            os.close(descriptor)

    def _recover(self) -> None:
        workspace_record = self.state_path / "workspace.json"
        if workspace_record.is_file():
            value = json.loads(workspace_record.read_text(encoding="utf-8"))
            if value.get("worker_generation") != self.worker_generation:
                self._contained.set()
            else:
                self._workspace = (
                    str(value["workspace_id"]),
                    int(value["workspace_generation"]),
                )
        for record_path in self.state_path.glob("*/record.json"):
            value = json.loads(record_path.read_text(encoding="utf-8"))
            if value.get("worker_generation") != self.worker_generation:
                self._contained.set()
                continue
            identity = value["identity"]
            execution = _Execution(
                identity=identity,
                fingerprint=str(value["fingerprint"]),
                directory=record_path.parent,
            )
            output_path = record_path.parent / "output.jsonl"
            output_corrupt = False
            if output_path.is_file():
                output_corrupt = self._recover_output(execution, output_path)
            if value["phase"] == "terminal" and not output_corrupt:
                execution.terminal = value["terminal"]
            else:
                uncertain_execution = value["phase"] in {"accepted", "running"}
                terminal = {
                    "status": "failed",
                    "exit_code": None,
                    "error": "execution_lost",
                }
                try:
                    _atomic_json(
                        record_path,
                        {**value, "phase": "terminal", "terminal": terminal},
                    )
                except OSError:
                    self._contained.set()
                    continue
                execution.terminal = terminal
                if uncertain_execution:
                    self._prove_recovered_broker_inactive(execution)
                    # Accepted/running v1 evidence carries no durable PGID, so
                    # prior process-group absence cannot be proven after restart.
                    self._contained.set()
            self._executions[
                (str(identity["turn_id"]), str(identity["tool_call_id"]))
            ] = execution

    def _recover_output(self, execution: _Execution, output_path: Path) -> bool:
        def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    raise ProtocolError("Duplicate executor output fields")
                result[key] = item
            return result

        truncate_at: int | None = None
        try:
            with output_path.open("rb") as handle:
                while True:
                    line_start = handle.tell()
                    line = handle.readline(MAX_FRAME_BYTES + 1)
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        if len(line) > MAX_FRAME_BYTES or handle.read(1):
                            raise ProtocolError(
                                "Executor output journal frame is too large"
                            )
                        truncate_at = line_start
                        break
                    event = json.loads(line, object_pairs_hook=exact_object)
                    if not isinstance(event, dict) or set(event) != {
                        "sequence",
                        "stream",
                        "data",
                    }:
                        raise ProtocolError("Invalid executor output evidence")
                    expected_sequence = len(execution.events) + 1
                    if expected_sequence > MAX_EXECUTION_OUTPUT_FRAMES:
                        raise ProtocolError("Too many executor output frames")
                    if event.get("sequence") != expected_sequence:
                        raise ProtocolError("Misordered executor output evidence")
                    encode_response(
                        {
                            "protocol": PROTOCOL,
                            "type": "output",
                            "request_id": "recovery",
                            **execution.identity,
                            **event,
                        }
                    )
                    execution.events.append(event)
                    execution.captured_bytes += len(str(event["data"]).encode())
                    if execution.captured_bytes > self.capture_limit:
                        raise ProtocolError("Oversized executor output evidence")
            if truncate_at is not None:
                with output_path.open("r+b") as handle:
                    handle.truncate(truncate_at)
                    handle.flush()
                    os.fsync(handle.fileno())
                _fsync_directory(output_path.parent)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
            ProtocolError,
            TypeError,
            ValueError,
        ):
            execution.events.clear()
            execution.captured_bytes = 0
            return True
        return False


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("Sandbox executor daemon must run as root")
    _not_dumpable()
    _harden_proc()
    broker, _proxy_token = _start_broker()
    try:
        ExecutorServer().serve_forever()
    finally:
        _stop(broker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
