import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from sqlalchemy import select

from backend.models.database import (
    ChatSandboxPool,
    ChatSandboxLease,
    ChatSandboxComputeInterval,
)
from backend.services.chat_executor_runtime import ChatExecutorRuntime
from backend.services.chat_sandbox_provider import SandboxError, SandboxLaunchMode
from backend.tests.chat_sandbox.pool_harness import (
    _Harness,
    _settings,
    _session,
)


def harness():
    h = _Harness(
        owner=True,
        settings=_settings(
            chat_executor_remote_transport_enabled=True,
            chat_sandbox_spend_enforcement_enabled=True,
        ),
    )
    h.coordinator.creation.executor_runtime = SimpleNamespace(
        prepare_launch=AsyncMock(return_value="signed-blank-admission"),
        wait_for_pool_ready=AsyncMock(),
        pool_ready=AsyncMock(return_value=True),
    )
    return h


def test_executor_pool_starts_without_legacy_control_and_claims_once():
    h = harness()

    async def run():
        assert await h.coordinator.replenish_pool() == 1
        h.owner = False
        ids = [uuid.uuid4(), uuid.uuid4()]
        with h.sessions() as db, db.begin():
            db.add_all([_session(sid) for sid in ids])
        claims = await asyncio.gather(*(h.coordinator.claim_blank(sid) for sid in ids))
        assert sum(c is not None for c in claims) == 1
        with h.sessions() as db:
            pool = db.scalar(select(ChatSandboxPool))
            lease = db.scalar(select(ChatSandboxLease))
            interval = db.scalar(select(ChatSandboxComputeInterval))
            assert pool.state == "claimed"
            assert lease.modal_sandbox_id == pool.modal_sandbox_id
            assert interval.modal_sandbox_id == pool.modal_sandbox_id
            assert interval.chat_session_id == lease.chat_session_id
            h.coordinator.creation.executor_runtime.prepare_launch.assert_awaited_once_with(
                pool.worker_generation, blank_pool=True
            )
        assert not h.transport.open_calls and not h.transport.ping_calls
        assert "provider.health" not in h.probe.provider_calls
        assert "provider.poll" not in h.probe.provider_calls
        assert h.provider.create_calls[0]["launch_mode"] is SandboxLaunchMode.EXECUTOR
        assert h.provider.create_calls[0]["executor_launch"] == "signed-blank-admission"

    asyncio.run(run())


@pytest.mark.parametrize("cancelled", [False, True])
def test_unregistered_executor_is_never_ready_and_creation_is_compensated(cancelled):
    h = harness()
    h.coordinator.creation.executor_runtime.wait_for_pool_ready.side_effect = (
        asyncio.CancelledError()
        if cancelled
        else SandboxError("registration_timeout", "timeout")
    )
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(h.coordinator.replenish_pool())
    else:
        assert asyncio.run(h.coordinator.replenish_pool()) == 0
    assert h.provider.termination_calls == ["sb-created-1"]
    with h.sessions() as db:
        assert db.scalar(select(ChatSandboxPool)).state != "blank_ready"
        assert db.scalar(select(ChatSandboxComputeInterval)).terminal_at is not None


def test_pool_compatibility_separates_legacy_and_executor_cells():
    h = harness()
    executor = h.repository.compatibility()
    assert executor.agent_harness == "generic"
    assert executor != _Harness().repository.compatibility()
    h.settings.chat_executor_cell_id = "x" * 64
    assert h.repository.compatibility() != executor
    assert len(h.repository.compatibility().provider_adapter_contract) == 64
    h.settings.chat_pi_prewarm_enabled = True
    assert h.repository.compatibility().agent_harness == "generic"


@pytest.mark.parametrize(
    "invalid", ["none", "cell", "image", "expiry", "connection", None]
)
def test_pool_readiness_requires_exact_live_registration(monkeypatch, invalid):
    settings = _settings(chat_executor_remote_transport_enabled=True)
    runtime = ChatExecutorRuntime(settings, session_factory=lambda: None)
    registration = SimpleNamespace(
        cell_id=settings.chat_executor_cell_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    manifest = SimpleNamespace(
        image_digest=hashlib.sha256(
            settings.chat_modal_image_version.encode()
        ).hexdigest()
    )
    if invalid == "cell":
        registration.cell_id = "old-cell"
    if invalid == "image":
        manifest.image_digest = "00" * 32
    if invalid == "expiry":
        registration.expires_at = datetime.now(UTC) + timedelta(seconds=239)
    monkeypatch.setattr(
        runtime,
        "_registration",
        lambda *args: None if invalid == "none" else (registration, manifest),
    )
    liveness = AsyncMock(
        side_effect=asyncio.IncompleteReadError(b"", 4)
        if invalid == "connection"
        else None
    )
    monkeypatch.setattr(runtime, "_claim_liveness", liveness)
    if invalid == "connection":
        with pytest.raises(asyncio.IncompleteReadError):
            asyncio.run(runtime.pool_ready("generation"))
    else:
        assert asyncio.run(runtime.pool_ready("generation")) is (invalid is None)
    assert liveness.await_count == (1 if invalid in [None, "connection"] else 0)


@pytest.mark.parametrize(
    "remote,legacy,expected",
    [(True, False, True), (True, True, False), (False, False, False)],
)
def test_workspace_requests_pool_only_for_persistent_transport(
    monkeypatch, remote, legacy, expected
):
    from backend.tests.test_chat_external_executor_workspace import (
        setup_manager,
        TURN_CLAIM,
    )

    manager, _, session_id, _ = setup_manager()
    manager.settings.chat_executor_remote_transport_enabled = remote
    acquire = AsyncMock(side_effect=RuntimeError("stop at acquisition"))
    monkeypatch.setattr(manager.acquisition, "acquire", acquire)
    action = manager.acquire_legacy if legacy else manager.acquire_for_binding
    with pytest.raises(RuntimeError, match="stop at acquisition"):
        asyncio.run(action(session_id=session_id, turn_claim=TURN_CLAIM))
    assert acquire.await_args.kwargs["allow_pool"] is expected


def test_uncertain_executor_health_skips_blank_without_terminating():
    h = harness()

    async def run():
        assert await h.coordinator.replenish_pool() == 1
        h.owner = False
        sid = uuid.uuid4()
        with h.sessions() as db, db.begin():
            db.add(_session(sid))
        h.coordinator.creation.executor_runtime.pool_ready.side_effect = OSError(
            "temporary disconnect"
        )
        assert await h.coordinator.claim_blank(sid) is None
        with h.sessions() as db:
            assert db.scalar(select(ChatSandboxPool)).state == "blank_ready"
            assert db.scalar(select(ChatSandboxComputeInterval)).terminal_at is None
        assert not h.provider.termination_calls

    asyncio.run(run())


def test_executor_startup_retries_uncertain_probe(monkeypatch):
    runtime = ChatExecutorRuntime(_settings(), session_factory=lambda: None)
    probe = AsyncMock(side_effect=[OSError("temporary disconnect"), True])
    monkeypatch.setattr(runtime, "pool_ready", probe)
    asyncio.run(runtime.wait_for_pool_ready("generation"))
    assert probe.await_count == 2
