from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid

import pytest

from backend.models.database import ChatSession
from backend.services.chat_external_executor_workspace import (
    ChatExternalExecutorWorkspaceManager,
)
from backend.services.chat_sandbox_provider import SandboxError, SandboxLaunchMode
from backend.services.chat_sandbox_capacity_repository import LeaseDecisionChanged
from backend.services.chat_turn_job_repository import StaleTurnClaim, TurnLeaseClaim
from backend.tests.test_chat_sandbox_acquisition_coordinator import _coordinator
from backend.tests.test_chat_sandbox_capacity_acquisition import (
    _Provider,
    _database,
    _session,
    _settings,
)


class RecordingProvider(_Provider):
    def __init__(self, *, transactions):
        super().__init__(transactions=transactions)
        self.create_options = []

    async def create(self, **options):
        self.create_options.append(options)
        return await super().create(**options)


class ExecutorHealth:
    def __init__(self, *statuses: str):
        self.statuses = list(statuses or ("ok",))
        self.sandboxes = []

    async def health(self, sandbox):
        self.sandboxes.append(sandbox)
        return self.statuses.pop(0) if self.statuses else "ok"


class BlockingHealth(ExecutorHealth):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()

    async def health(self, sandbox):
        self.sandboxes.append(sandbox)
        self.started.set()
        await asyncio.Future()


class LiveTurns:
    def __init__(self):
        self.claims = []

    def require_live_claim(self, _db, *, claim, now):
        self.claims.append((claim, now))


class ExpiringTurn(LiveTurns):
    def require_live_claim(self, _db, *, claim, now):
        super().require_live_claim(_db, claim=claim, now=now)
        if len(self.claims) == 2:
            raise StaleTurnClaim("expired")


class ExpiringTurnAt(LiveTurns):
    def __init__(self, call):
        super().__init__()
        self.call = call

    def require_live_claim(self, _db, *, claim, now):
        super().require_live_claim(_db, claim=claim, now=now)
        if len(self.claims) == self.call:
            raise StaleTurnClaim("expired")


TURN_CLAIM = TurnLeaseClaim(uuid.uuid4(), "worker", 3, 7)


def setup_manager(
    *,
    health: ExecutorHealth | None = None,
    observe=None,
    record=None,
    qualification_capacity=None,
    sandbox_cap=2,
):
    settings = _settings(
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_total_live_cap=sandbox_cap,
    )
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = RecordingProvider(transactions=[])
    acquisition = _coordinator(settings, sessions, provider)
    manager = ChatExternalExecutorWorkspaceManager(
        settings=settings,
        session_factory=acquisition.session_factory,
        state_repository=acquisition.state_repository,
        acquisition=acquisition,
        lifecycle=acquisition.lease_maintenance.lifecycle,
        maintenance=acquisition.lease_maintenance,
        executor=health or ExecutorHealth(),
        turn_repository=LiveTurns(),
        observe=observe,
        record_evidence=record,
        qualification_capacity=(
            qualification_capacity
            if qualification_capacity is not None
            else (lambda *_args, **_kwargs: None)
        ),
    )
    return manager, sessions, session_id, provider


@pytest.mark.parametrize(
    ("qualified_cap", "expected_cap"),
    [(16, 16), (None, 3)],
)
def test_workspace_capacity_uses_only_persisted_turn_authorization(
    qualified_cap, expected_cap
):
    manager, _sessions, session_id, _provider = setup_manager(
        qualification_capacity=lambda *_args, **_kwargs: qualified_cap,
        sandbox_cap=3,
    )
    recorded_caps = []
    acquire = manager.acquisition.capacity_repository.acquire

    def recording_acquire(*args, **kwargs):
        recorded_caps.append(kwargs["total_live_cap"])
        return acquire(*args, **kwargs)

    manager.acquisition.capacity_repository.acquire = recording_acquire

    async def exercise():
        workspace = await manager.acquire(
            session_id=session_id,
            turn_claim=TURN_CLAIM,
        )
        assert await manager.release(workspace)

    asyncio.run(exercise())

    assert recorded_caps == [expected_cap]


def test_workspace_retry_rechecks_scope_and_revokes_elevated_capacity():
    capacities = iter((16, None))
    manager, _sessions, session_id, provider = setup_manager(
        health=ExecutorHealth("draining", "ok"),
        qualification_capacity=lambda *_args, **_kwargs: next(capacities),
        sandbox_cap=3,
    )
    provider.created = SimpleNamespace(object_id="sb-created")
    recorded_caps = []
    acquire = manager.acquisition.capacity_repository.acquire

    def recording_acquire(*args, **kwargs):
        recorded_caps.append(kwargs["total_live_cap"])
        return acquire(*args, **kwargs)

    manager.acquisition.capacity_repository.acquire = recording_acquire

    async def exercise():
        workspace = await manager.acquire(
            session_id=session_id,
            turn_claim=TURN_CLAIM,
        )
        assert await manager.release(workspace)

    asyncio.run(exercise())

    assert recorded_caps == [16, 3]


def test_workspace_lock_retry_rechecks_scope_before_capacity_decision():
    capacities = iter((16, None))
    manager, _sessions, session_id, _provider = setup_manager(
        qualification_capacity=lambda *_args, **_kwargs: next(capacities),
        sandbox_cap=3,
    )
    recorded_caps = []
    acquire = manager.acquisition.capacity_repository.acquire

    def retry_once(*args, **kwargs):
        recorded_caps.append(kwargs["total_live_cap"])
        if len(recorded_caps) == 1:
            raise LeaseDecisionChanged
        return acquire(*args, **kwargs)

    manager.acquisition.capacity_repository.acquire = retry_once

    async def exercise():
        workspace = await manager.acquire(
            session_id=session_id,
            turn_claim=TURN_CLAIM,
        )
        assert await manager.release(workspace)

    asyncio.run(exercise())

    assert recorded_caps == [16, 3]


def test_workspace_lifecycle_records_exact_turn_and_session_evidence():
    evidence = []
    manager, _sessions, session_id, _provider = setup_manager(
        record=lambda **values: evidence.append(values) or True
    )

    async def exercise():
        workspace = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        await manager.invalidate(workspace)

    asyncio.run(exercise())

    assert evidence == [
        {
            "turn_id": TURN_CLAIM.turn_id,
            "chat_session_id": session_id,
            "event_type": "workspace_created",
        },
        {
            "turn_id": TURN_CLAIM.turn_id,
            "chat_session_id": session_id,
            "event_type": "workspace_evicted",
        },
    ]


def test_workspace_programming_failure_is_visible_without_invalidating_busy_claim():
    def fail_record(**_values):
        raise RuntimeError("evidence unavailable")

    manager, sessions, session_id, provider = setup_manager(record=fail_record)

    async def exercise():
        with pytest.raises(RuntimeError, match="evidence unavailable"):
            await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)

    asyncio.run(exercise())

    assert [call[0] for call in provider.calls].count("terminate") == 0
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "busy"


def test_first_bash_creates_executor_and_later_turn_reuses_exact_workspace():
    observations = []
    manager, sessions, session_id, provider = setup_manager(
        observe=lambda event, code, value: observations.append((event, code, value))
    )

    async def exercise():
        first = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(first)
        second_claim = TurnLeaseClaim(uuid.uuid4(), "worker", 3, 8)
        second = await manager.acquire(session_id=session_id, turn_claim=second_claim)
        assert await manager.release(second)
        return first, second

    first, second = asyncio.run(exercise())

    assert first.sandbox_id == second.sandbox_id
    assert first.workspace_generation == second.workspace_generation
    assert first.worker_generation == second.worker_generation
    assert len(provider.create_options) == 1
    assert provider.create_options[0]["launch_mode"] is SandboxLaunchMode.EXECUTOR
    assert observations == [
        ("workspace_state", "created", 1),
        ("workspace_active_ms", None, observations[1][2]),
        ("workspace_state", "released", 1),
        ("workspace_state", "reused", 1),
        ("workspace_active_ms", None, observations[4][2]),
        ("workspace_state", "released", 1),
    ]
    assert observations[1][2] >= 0
    assert observations[4][2] >= 0
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "idle"
        assert lease.modal_sandbox_id == first.sandbox_id
        assert lease.workspace_snapshot_id is None


def test_executor_workspace_reuse_uses_executor_launch_mode_health():
    manager, _sessions, session_id, provider = setup_manager()
    original_health = provider.health

    async def mode_aware_health(sandbox, **options):
        if options.get("launch_mode") is not SandboxLaunchMode.EXECUTOR:
            return False
        return await original_health(sandbox, **options)

    provider.health = mode_aware_health

    async def exercise():
        first = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(first)
        second = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(second)
        return first, second

    first, second = asyncio.run(exercise())

    assert second.sandbox_id == first.sandbox_id
    assert len(provider.create_options) == 1


def test_concurrent_acquisition_waits_for_existing_busy_workspace():
    manager, _sessions, session_id, provider = setup_manager()

    async def exercise():
        first = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        waiting = asyncio.create_task(
            manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        )
        await asyncio.sleep(0.01)
        assert not waiting.done()
        assert await manager.release(first)
        second = await waiting
        assert await manager.release(second)
        return first, second

    first, second = asyncio.run(exercise())

    assert second.sandbox_id == first.sandbox_id
    assert len(provider.create_options) == 1


def test_failed_executor_health_uses_fenced_termination_before_one_replacement():
    health = ExecutorHealth("draining", "ok")
    manager, _sessions, session_id, provider = setup_manager(health=health)
    provider.created = SimpleNamespace(object_id="sb-created")

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(handle)

    asyncio.run(exercise())

    assert len(provider.create_options) == 2
    assert [call[0] for call in provider.calls].count("terminate") == 1
    terminate_index = next(
        index for index, call in enumerate(provider.calls) if call[0] == "terminate"
    )
    create_indices = [
        index for index, call in enumerate(provider.calls) if call[0] == "create"
    ]
    assert create_indices[0] < terminate_index < create_indices[1]


def test_health_cleanup_failure_preserves_typed_failure_and_busy_fence():
    health = ExecutorHealth("draining")
    manager, sessions, session_id, provider = setup_manager(health=health)

    async def fail_invalidation(*_args, **_kwargs):
        raise RuntimeError("cleanup failed")

    manager.invalidate = fail_invalidation

    async def exercise():
        with pytest.raises(SandboxError) as exc_info:
            await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert exc_info.value.code == "sandbox_worker_failed"

    asyncio.run(exercise())

    assert len(provider.create_options) == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "busy"


def test_cancellation_during_unhealthy_health_invalidation_propagates():
    health = ExecutorHealth("draining")
    manager, sessions, session_id, _provider = setup_manager(health=health)

    async def cancel_invalidation(*_args, **_kwargs):
        raise asyncio.CancelledError

    manager.invalidate = cancel_invalidation

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)

    asyncio.run(exercise())

    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "busy"


def test_identity_failure_invalidates_only_the_exact_busy_claim():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        await manager.invalidate(handle)

    asyncio.run(exercise())

    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "failed"
        assert lease.modal_sandbox_id is None


@pytest.mark.parametrize(
    ("cancel_proven", "expected_state"),
    [(True, "idle"), (False, "failed")],
)
def test_executor_cancellation_settlement_is_durable(cancel_proven, expected_state):
    manager, sessions, session_id, _provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        if cancel_proven:
            assert await manager.release(handle)
        else:
            await manager.invalidate(handle)

    asyncio.run(exercise())

    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == expected_state
        assert (lease.modal_sandbox_id is not None) is cancel_proven


def test_maintenance_failure_after_release_leaves_durable_lease_idle():
    manager, sessions, session_id, _provider = setup_manager()

    async def fail_maintenance():
        raise RuntimeError("maintenance failed")

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        manager.maintenance.enforce_warm_cap = fail_maintenance
        with pytest.raises(RuntimeError, match="maintenance failed"):
            await manager.release(handle)

    asyncio.run(exercise())

    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "idle"


def test_turn_fence_expiring_during_acquisition_releases_workspace_to_idle():
    manager, sessions, session_id, provider = setup_manager()
    manager.turn_repository = ExpiringTurn()

    async def exercise():
        await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)

    try:
        asyncio.run(exercise())
    except StaleTurnClaim:
        pass
    else:  # pragma: no cover - the fake always expires on the second fence
        raise AssertionError("turn claim should expire")

    assert [call[0] for call in provider.calls].count("terminate") == 0
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "idle"


@pytest.mark.parametrize("rejection_call", (1, 2))
def test_workspace_acquire_stale_turn_seams_propagate_to_high_level_boundary(
    rejection_call,
):
    evidence = []
    manager, _sessions, session_id, _provider = setup_manager(
        record=lambda **values: evidence.append(values) or True
    )
    manager.turn_repository = ExpiringTurnAt(rejection_call)

    with pytest.raises(StaleTurnClaim):
        asyncio.run(manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM))

    assert evidence == []


def test_idle_executor_workspace_is_reclaimed_by_existing_eviction_lifecycle():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(handle)
        return await manager.lifecycle.idle_eviction.evict_idle(session_id)

    outcome = asyncio.run(exercise())

    assert outcome.acquired is True
    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "terminated"
        assert lease.modal_sandbox_id is None


def test_cancellation_during_health_invalidates_exact_busy_workspace():
    health = BlockingHealth()
    manager, sessions, session_id, provider = setup_manager(health=health)

    async def exercise():
        task = asyncio.create_task(
            manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        )
        await health.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())

    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        lease = manager.state_repository.load_lease(db, session_id, lock=False)
        assert lease is not None
        assert lease.state == "failed"
        assert lease.modal_sandbox_id is None


def test_retained_workspace_uses_existing_deleted_session_cleanup_path():
    manager, sessions, session_id, provider = setup_manager()

    async def exercise():
        handle = await manager.acquire(session_id=session_id, turn_claim=TURN_CLAIM)
        assert await manager.release(handle)
        with sessions() as db, db.begin():
            session = db.get(ChatSession, session_id)
            assert session is not None
            db.delete(session)
        await manager.lifecycle.cleanup_deleted(handle.sandbox_id, None)

    asyncio.run(exercise())

    assert [call[0] for call in provider.calls].count("terminate") == 1
    with sessions() as db:
        assert db.get(ChatSession, session_id) is None
