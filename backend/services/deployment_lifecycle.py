"""Process-local request and stream accounting for zero-downtime deployments."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar


DEPLOYED_ENVIRONMENTS_ROOT = Path("/srv/paperswithcode/environments")


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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accepting_chat_turns = True
        self._active_http_requests = 0
        self._active_chat_streams = 0
        self._active_gateway_streams = 0
        self._drain_started_at: str | None = None

    @contextmanager
    def request(self, path: str) -> Iterator[None]:
        chat = path == "/api/v1/chat/stream"
        gateway = path.endswith("/api/internal/chat-gateway/v1/messages")
        with self._lock:
            self._active_http_requests += 1
            if chat:
                self._active_chat_streams += 1
            if gateway:
                self._active_gateway_streams += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_http_requests -= 1
                if chat:
                    self._active_chat_streams -= 1
                if gateway:
                    self._active_gateway_streams -= 1

    def drain(self) -> DeploymentStatus:
        with self._lock:
            if self._accepting_chat_turns:
                self._accepting_chat_turns = False
                self._drain_started_at = datetime.now(UTC).isoformat()
            return self._status_locked()

    def undrain(self) -> DeploymentStatus:
        with self._lock:
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
        return DeploymentStatus(
            accepting_chat_turns=self._accepting_chat_turns,
            active_http_requests=self._active_http_requests,
            active_chat_streams=self._active_chat_streams,
            active_gateway_streams=self._active_gateway_streams,
            drain_started_at=self._drain_started_at,
            environment=os.environ.get("PWC_ENVIRONMENT", ""),
            git_sha=os.environ.get("PWC_GIT_SHA", ""),
            slot=os.environ.get("PWC_DEPLOYMENT_SLOT", "legacy"),
            release_id=os.environ.get("PWC_RELEASE_ID", ""),
            runtime_id=os.environ.get("PWC_RUNTIME_ID", "legacy"),
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
