"""Process-local request and stream accounting for zero-downtime deployments."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, ClassVar


DEPLOYED_ENVIRONMENTS_ROOT = Path("/srv/paperswithcode/environments")
DEPLOYMENT_STATE_ROOT = Path("/var/lib/paperswithcode")


def _process_start_token(process_id: int) -> str:
    fields = (
        Path(f"/proc/{process_id}/stat")
        .read_text(encoding="utf-8")
        .rsplit(") ", 1)[1]
        .split()
    )
    return fields[19]


def _process_is_alive(process_id: int, start_token: str) -> bool:
    try:
        return _process_start_token(process_id) == start_token
    except (OSError, IndexError):
        return False


@dataclass(frozen=True)
class _LifecycleIdentity:
    environment: str
    slot: str
    release_id: str
    runtime_id: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    def state_key(self) -> str:
        encoded = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class DeploymentStatus:
    accepting_chat_turns: bool
    active_http_requests: int
    active_chat_streams: int
    active_gateway_streams: int
    drain_started_at: str | None
    environment: str
    git_sha: str
    slot: str
    release_id: str
    runtime_id: str


class DeploymentLifecycle:
    """Track complete ASGI body lifetimes and gate new chat admissions."""

    def __init__(
        self,
        *,
        state_root: Path | None = None,
        process_id: int | None = None,
        process_start_token: str | None = None,
        process_is_alive: Callable[[int, str], bool] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._accepting_chat_turns = True
        self._active_http_requests = 0
        self._active_chat_streams = 0
        self._active_gateway_streams = 0
        self._publish_pending = False
        self._drain_started_at: str | None = None
        self._identity = _LifecycleIdentity(
            environment=os.environ.get("PWC_ENVIRONMENT", ""),
            slot=os.environ.get("PWC_DEPLOYMENT_SLOT", "legacy"),
            release_id=os.environ.get("PWC_RELEASE_ID", ""),
            runtime_id=os.environ.get("PWC_RUNTIME_ID", "legacy"),
        )
        self._process_id = os.getpid() if process_id is None else process_id
        self._process_start_token = process_start_token or _process_start_token(
            self._process_id
        )
        self._process_is_alive = process_is_alive or _process_is_alive
        if state_root is None and self._shared_state_is_deployed():
            state_root = DEPLOYMENT_STATE_ROOT / self._identity.environment
        self._state_directory = (
            state_root
            / "deployment-lifecycle"
            / self._identity.slot
            / self._identity.state_key()
            if state_root is not None
            else None
        )
        if self._state_directory is not None:
            self._state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        token_digest = hashlib.sha256(self._process_start_token.encode()).hexdigest()
        self._worker_path = (
            self._state_directory
            / f"worker-{self._process_id}-{token_digest[:16]}.json"
            if self._state_directory is not None
            else None
        )
        self._drain_path = (
            self._state_directory / "drain.json"
            if self._state_directory is not None
            else None
        )

    def _shared_state_is_deployed(self) -> bool:
        return (
            self._identity.environment in {"production", "staging"}
            and self._identity.slot in {"blue", "green"}
            and bool(self._identity.release_id)
            and self._identity.runtime_id not in {"", "legacy"}
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("deployment lifecycle state is invalid")
        return value

    def _read_json_if_exists(self, path: Path) -> dict[str, object] | None:
        try:
            return self._read_json(path)
        except FileNotFoundError:
            return None

    @staticmethod
    def _write_json(path: Path, value: dict[str, object]) -> None:
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}-{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _identity_matches(self, value: dict[str, object]) -> bool:
        return all(
            value.get(key) == expected
            for key, expected in self._identity.as_dict().items()
        )

    def _publish_locked(self) -> None:
        if self._worker_path is None:
            return
        # Stays set if the write below fails, so status() retries it.
        self._publish_pending = True
        if not (
            self._active_http_requests
            or self._active_chat_streams
            or self._active_gateway_streams
        ):
            self._worker_path.unlink(missing_ok=True)
            self._publish_pending = False
            return
        self._write_json(
            self._worker_path,
            {
                "schema": 1,
                **self._identity.as_dict(),
                "process_id": self._process_id,
                "process_start_token": self._process_start_token,
                "active_http_requests": self._active_http_requests,
                "active_chat_streams": self._active_chat_streams,
                "active_gateway_streams": self._active_gateway_streams,
            },
        )
        self._publish_pending = False

    def _shared_counters_locked(self) -> tuple[int, int, int]:
        assert self._state_directory is not None
        totals = [0, 0, 0]
        counter_names = (
            "active_http_requests",
            "active_chat_streams",
            "active_gateway_streams",
        )
        for path in self._state_directory.glob("worker-*.json"):
            value = self._read_json_if_exists(path)
            if value is None:
                continue
            process_id = value.get("process_id")
            start_token = value.get("process_start_token")
            counters = tuple(value.get(name) for name in counter_names)
            if (
                value.get("schema") != 1
                or not self._identity_matches(value)
                or isinstance(process_id, bool)
                or not isinstance(process_id, int)
                or not isinstance(start_token, str)
                or any(
                    isinstance(counter, bool)
                    or not isinstance(counter, int)
                    or counter < 0
                    for counter in counters
                )
            ):
                raise RuntimeError("deployment lifecycle worker state is invalid")
            if not self._process_is_alive(process_id, start_token):
                path.unlink(missing_ok=True)
                continue
            for index, counter in enumerate(counters):
                totals[index] += counter
        return totals[0], totals[1], totals[2]

    def _shared_drain_started_at_locked(self) -> str | None:
        if self._drain_path is None:
            return None
        value = self._read_json_if_exists(self._drain_path)
        if value is None:
            return None
        started_at = value.get("drain_started_at")
        if (
            value.get("schema") != 1
            or not self._identity_matches(value)
            or not isinstance(started_at, str)
            or not started_at
        ):
            raise RuntimeError("deployment lifecycle drain state is invalid")
        return started_at

    @contextmanager
    def request(self, path: str) -> Iterator[None]:
        chat = path == "/api/v1/chat/stream"
        gateway = path.endswith(
            (
                "/api/internal/chat-gateway/v1/messages",
                "/api/internal/chat-gateway/v1/responses",
            )
        )
        with self._lock:
            self._active_http_requests += 1
            if chat:
                self._active_chat_streams += 1
            if gateway:
                self._active_gateway_streams += 1
        # Publish inside the try: a failed write (for example ENOSPC) must not
        # leak the increment, or a drained slot reports busy until it stops.
        try:
            with self._lock:
                self._publish_locked()
            yield
        finally:
            with self._lock:
                self._active_http_requests -= 1
                if chat:
                    self._active_chat_streams -= 1
                if gateway:
                    self._active_gateway_streams -= 1
                self._publish_locked()

    def drain(self) -> DeploymentStatus:
        with self._lock:
            if self._drain_path is not None:
                started_at = self._shared_drain_started_at_locked()
                if started_at is None:
                    started_at = datetime.now(UTC).isoformat()
                    self._write_json(
                        self._drain_path,
                        {
                            "schema": 1,
                            **self._identity.as_dict(),
                            "drain_started_at": started_at,
                        },
                    )
                return self._status_locked()
            if self._accepting_chat_turns:
                self._accepting_chat_turns = False
                self._drain_started_at = datetime.now(UTC).isoformat()
            return self._status_locked()

    def undrain(self) -> DeploymentStatus:
        with self._lock:
            if self._drain_path is not None:
                self._drain_path.unlink(missing_ok=True)
                return self._status_locked()
            self._accepting_chat_turns = True
            self._drain_started_at = None
            return self._status_locked()

    def status(self) -> DeploymentStatus:
        with self._lock:
            return self._status_locked()

    def owns_active_slot(
        self, environments_root: Path = DEPLOYED_ENVIRONMENTS_ROOT
    ) -> bool:
        """Return whether this process owns environment-wide background work."""

        status = self.status()
        if status.slot == "legacy":
            return True
        if status.slot not in {"blue", "green"} or not status.environment:
            return False
        active = environments_root / status.environment / "active"
        expected = environments_root / status.environment / "slots" / status.slot
        try:
            return active.resolve(strict=True) == expected.resolve(strict=True)
        except OSError:
            return False

    def _status_locked(self) -> DeploymentStatus:
        if self._state_directory is not None:
            if self._publish_pending:
                # Repair this worker's record after a failed write, so a slot
                # that receives no more traffic still reports its real counts.
                with contextlib.suppress(OSError):
                    self._publish_locked()
            http, chat, gateway = self._shared_counters_locked()
            drain_started_at = self._shared_drain_started_at_locked()
            accepting_chat_turns = drain_started_at is None
        else:
            http = self._active_http_requests
            chat = self._active_chat_streams
            gateway = self._active_gateway_streams
            drain_started_at = self._drain_started_at
            accepting_chat_turns = self._accepting_chat_turns
        return DeploymentStatus(
            accepting_chat_turns=accepting_chat_turns,
            active_http_requests=http,
            active_chat_streams=chat,
            active_gateway_streams=gateway,
            drain_started_at=drain_started_at,
            environment=self._identity.environment,
            git_sha=os.environ.get("PWC_GIT_SHA", ""),
            slot=self._identity.slot,
            release_id=self._identity.release_id,
            runtime_id=self._identity.runtime_id,
        )

    def as_dict(self) -> dict[str, object]:
        return asdict(self.status())


deployment_lifecycle = DeploymentLifecycle()


class DeploymentAccountingMiddleware:
    """ASGI middleware that decrements only after the final response body."""

    _operator_paths: ClassVar[set[str]] = {
        "/internal/ready",
        "/internal/deployment-status",
        "/internal/drain",
        "/internal/undrain",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") in self._operator_paths:
            await self.app(scope, receive, send)
            return
        with deployment_lifecycle.request(scope.get("path", "")):
            await self.app(scope, receive, send)


def operator_socket_allowed(scope: dict) -> bool:
    """Mutation endpoints exist only in a slot process reached through its UDS."""

    if os.environ.get("PWC_DEPLOY_TESTING") == "1":
        return True
    socket_path = os.environ.get("PWC_BACKEND_SOCKET")
    if not socket_path:
        return False
    server = scope.get("server")
    if isinstance(server, str):
        server_path = server
    elif (
        isinstance(server, (list, tuple))
        and len(server) == 2
        and isinstance(server[0], str)
        and server[1] is None
    ):
        server_path = server[0]
    else:
        return False
    return os.path.realpath(server_path) == os.path.realpath(socket_path)
