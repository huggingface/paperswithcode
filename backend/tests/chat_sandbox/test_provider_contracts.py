"""Sandbox capability metering, workspace snapshots, cancellation, session store, and migration."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.protocol import (
    decode_frame,
)
from backend.config import Settings
from backend.models.database import ChatTurnCapability
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
    _digest,
)
from backend.services.chat_sandbox_service import (
    RunningWorker,
    SandboxSessionManager,
    WorkerClaim,
    WorkspaceSnapshotProvider,
)
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)


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


def test_sandbox_migration_is_environment_scoped():
    migration = (
        Path(__file__).parents[2]
        / "database"
        / "migrations"
        / "add_chat_sandbox_runtime.sql"
    ).read_text()
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
