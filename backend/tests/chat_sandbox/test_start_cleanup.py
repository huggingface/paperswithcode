from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select

from backend.models.database import ChatSandboxComputeInterval, ChatSandboxLease
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
    LeaseDecisionChanged,
    ReuseLease,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.tests.chat_sandbox.capacity_harness import (
    _database,
    _lease,
    _manager,
    _Provider,
    _session,
    _settings,
    _spend_settings,
)


@pytest.mark.parametrize("mismatch", ["state", "sandbox", "token", "generation"])
def test_reuse_recovery_claim_rejects_every_exact_candidate_mismatch(mismatch):
    settings = _settings()
    lease = _lease(
        settings,
        uuid.uuid4(),
        state="ready",
        sandbox_id="sb-candidate",
        worker_generation="generation-candidate",
    )
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_kwargs: lease,
    )
    now = datetime.now(UTC)
    candidate = repository.select(
        object(),
        lease.chat_session_id,
        now=now,
        ready_timeout_seconds=2,
    )
    assert isinstance(candidate, ReuseLease)
    if mismatch == "state":
        lease.state = "idle"
    elif mismatch == "sandbox":
        lease.modal_sandbox_id = "sb-successor"
    elif mismatch == "token":
        lease.lease_token_hash = "successor-token"
    else:
        lease.worker_generation = "generation-successor"
    before = (
        lease.state,
        lease.modal_sandbox_id,
        lease.lease_token_hash,
        lease.worker_generation,
        lease.lease_expires_at,
        lease.failure_code,
    )

    with pytest.raises(LeaseDecisionChanged):
        repository.claim_reuse_recovery(
            object(),
            lease.chat_session_id,
            candidate,
            now=now,
            ready_timeout_seconds=2,
        )
    assert (
        lease.state,
        lease.modal_sandbox_id,
        lease.lease_token_hash,
        lease.worker_generation,
        lease.lease_expires_at,
        lease.failure_code,
    ) == before


def test_provider_success_with_landing_ownership_loss_cleans_only_created_sandbox():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    class OwnershipChangingProvider(_Provider):
        async def create(self, **options):
            sandbox = await super().create(**options)
            with sessions() as db, db.begin():
                lease = db.get(ChatSandboxLease, session_id)
                lease.worker_generation = "generation-successor"
                lease.lease_token_hash = ChatSandboxStateRepository.token_hash(
                    "successor-token"
                )
                lease.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
            return sandbox

    provider = OwnershipChangingProvider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "sandbox_start_failed"
    assert str(exc_info.value) == "Secure workspace ownership changed"
    assert provider.calls[0][0] == "create"
    assert provider.calls[1] == ("terminate", "sb-created", provider.created)
    with sessions() as db:
        successor = db.get(ChatSandboxLease, session_id)
    assert successor.state == "starting"
    assert successor.modal_sandbox_id is None
    assert successor.worker_generation == "generation-successor"
    assert successor.lease_token_hash == ChatSandboxStateRepository.token_hash(
        "successor-token"
    )


@pytest.mark.parametrize("termination_confirmed", [False, True])
def test_landing_transaction_failure_cleans_and_accounts_for_created_provider(
    termination_confirmed,
):
    settings = _spend_settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    fail_landing = False

    def fail_next_flush(_db, _flush_context, _instances):
        nonlocal fail_landing
        if fail_landing:
            fail_landing = False
            raise RuntimeError("landing commit failed")

    event.listen(sessions.class_, "before_flush", fail_next_flush)

    class Provider(_Provider):
        async def create(self, **options):
            nonlocal fail_landing
            sandbox = await super().create(**options)
            fail_landing = True
            return sandbox

        async def terminate(self, sandbox_id, sandbox=None):
            await super().terminate(sandbox_id, sandbox)
            return termination_confirmed

    provider = Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(RuntimeError, match="landing commit failed"):
        asyncio.run(manager.ensure_ready(session_id))

    assert provider.calls[0][0] == "create"
    assert provider.calls[1] == ("terminate", "sb-created", provider.created)
    with sessions() as db:
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
        lease = db.get(ChatSandboxLease, session_id)
    assert interval.worker_generation == provider.calls[0][1]
    assert interval.modal_sandbox_id == "sb-created"
    assert interval.provider_created_at is not None
    assert interval.termination_requested_at is not None
    assert (interval.terminal_at is not None) is termination_confirmed
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.reconciliation_state == (
        "confirmed" if termination_confirmed else "termination_uncertain"
    )
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.failure_code == "sandbox_start_failed"


def test_provider_create_failure_aborts_only_pre_provider_reservation():
    settings = _spend_settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    class FailingProvider(_Provider):
        async def create(self, **options):
            self._assert_outside_transaction()
            self.calls.append(("create", options["worker_generation"]))
            raise RuntimeError("provider create failed")

    provider = FailingProvider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "sandbox_start_failed"
    assert str(exc_info.value) == "Secure workspace startup failed"
    assert [call[0] for call in provider.calls] == ["create"]
    with sessions() as db:
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
        lease = db.get(ChatSandboxLease, session_id)
    assert interval.worker_generation == provider.calls[0][1]
    assert interval.modal_sandbox_id is None
    assert interval.provider_created_at is None
    assert interval.termination_requested_at is None
    assert interval.terminal_at is not None
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.reserved_microusd == 0
    assert interval.reconciliation_state == "creation_failed"
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.failure_code == "sandbox_start_failed"


def test_ordinary_snapshot_restore_failure_is_nonfatal_and_clears_exact_snapshot():
    settings = _spend_settings(chat_workspace_snapshots_enabled=True)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="terminated",
                sandbox_id=None,
                snapshot_id="snapshot-current",
            )
        )

    class FailingRestore:
        supported = True

        async def restore(self, sandbox, snapshot_id):
            assert sandbox.object_id == "sb-created"
            assert snapshot_id == "snapshot-current"
            raise RuntimeError("snapshot restore failed")

    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)
    manager.snapshots = FailingRestore()

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox is provider.created
    assert created is True
    assert outcome == "created"
    assert [call[0] for call in provider.calls] == ["create"]
    with sessions() as db:
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
        lease = db.get(ChatSandboxLease, session_id)
    assert interval.modal_sandbox_id == "sb-created"
    assert interval.provider_created_at is not None
    assert interval.terminal_at is None
    assert lease.state == "ready"
    assert lease.modal_sandbox_id == "sb-created"
    assert lease.workspace_snapshot_id is None
    assert lease.snapshot_image_version is None
    assert lease.snapshot_updated_at is None


@pytest.mark.parametrize("spend_enabled", [False, True])
@pytest.mark.parametrize("termination_confirmed", [False, True])
def test_timeout_after_provider_create_accounts_and_terminates_instead_of_aborting(
    spend_enabled, termination_confirmed
):
    settings_factory = _spend_settings if spend_enabled else _settings
    settings = settings_factory(
        chat_sandbox_ready_timeout_seconds=0.05,
        chat_workspace_snapshots_enabled=True,
    )
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="terminated",
                sandbox_id=None,
                snapshot_id="snapshot-current",
            )
        )

    class NeverRestores:
        supported = True

        async def restore(self, _sandbox, _snapshot_id):
            await asyncio.Future()

    class Provider(_Provider):
        async def terminate(self, sandbox_id, sandbox=None):
            await super().terminate(sandbox_id, sandbox)
            return termination_confirmed

    provider = Provider(transactions=[])
    manager = _manager(settings, sessions, provider)
    manager.snapshots = NeverRestores()

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "sandbox_timeout"
    assert str(exc_info.value) == "Secure workspace startup timed out"
    assert provider.calls[0][0] == "create"
    assert provider.calls[1] == ("terminate", "sb-created", provider.created)
    with sessions() as db:
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        lease = db.get(ChatSandboxLease, session_id)
    if spend_enabled:
        assert len(intervals) == 1
        interval = intervals[0]
        assert interval.modal_sandbox_id == "sb-created"
        assert interval.provider_created_at is not None
        assert interval.termination_requested_at is not None
        assert (interval.terminal_at is not None) is termination_confirmed
        assert interval.terminal_reason == "sandbox_timeout"
        assert interval.reconciliation_state == (
            "confirmed" if termination_confirmed else "termination_uncertain"
        )
    else:
        assert intervals == []
    assert lease.state == "failed"
    assert lease.failure_code == "sandbox_timeout"


@pytest.mark.parametrize("spend_enabled", [False, True])
@pytest.mark.parametrize("termination_confirmed", [False, True])
def test_cancellation_after_provider_create_accounts_and_terminates_exact_generation(
    spend_enabled, termination_confirmed
):
    async def scenario():
        settings_factory = _spend_settings if spend_enabled else _settings
        settings = settings_factory(chat_workspace_snapshots_enabled=True)
        sessions = _database()
        session_id = uuid.uuid4()
        with sessions() as db, db.begin():
            db.add(_session(session_id))
            db.add(
                _lease(
                    settings,
                    session_id,
                    state="terminated",
                    sandbox_id=None,
                    snapshot_id="snapshot-current",
                )
            )
        restore_started = asyncio.Event()

        class BlockingRestore:
            supported = True

            async def restore(self, _sandbox, _snapshot_id):
                restore_started.set()
                await asyncio.Future()

        class Provider(_Provider):
            async def terminate(self, sandbox_id, sandbox=None):
                await super().terminate(sandbox_id, sandbox)
                return termination_confirmed

        provider = Provider(transactions=[])
        manager = _manager(settings, sessions, provider)
        manager.snapshots = BlockingRestore()
        start = asyncio.create_task(manager.ensure_ready(session_id))
        await restore_started.wait()
        start.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start

        assert provider.calls[0][0] == "create"
        assert provider.calls[1] == ("terminate", "sb-created", provider.created)
        with sessions() as db:
            intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
            lease = db.get(ChatSandboxLease, session_id)
        if spend_enabled:
            assert len(intervals) == 1
            interval = intervals[0]
            assert interval.worker_generation == provider.calls[0][1]
            assert interval.modal_sandbox_id == "sb-created"
            assert interval.provider_created_at is not None
            assert interval.termination_requested_at is not None
            assert (interval.terminal_at is not None) is termination_confirmed
            assert interval.terminal_reason == "sandbox_start_failed"
            assert interval.reconciliation_state == (
                "confirmed" if termination_confirmed else "termination_uncertain"
            )
        else:
            assert intervals == []
        assert lease.state == "failed"
        assert lease.failure_code == "sandbox_start_failed"

    asyncio.run(scenario())


def test_cancellation_during_warm_cap_aborts_owned_pre_provider_start():
    async def scenario():
        settings = _spend_settings()
        sessions = _database()
        session_id = uuid.uuid4()
        with sessions() as db, db.begin():
            db.add(_session(session_id))
        warm_cap_started = asyncio.Event()

        async def blocking_warm_cap():
            warm_cap_started.set()
            await asyncio.Future()

        provider = _Provider(transactions=[])
        manager = _manager(settings, sessions, provider)
        manager._acquisition_coordinator().lease_maintenance.enforce_warm_cap = (
            blocking_warm_cap
        )
        start = asyncio.create_task(manager.ensure_ready(session_id))
        await warm_cap_started.wait()
        start.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start

        assert provider.calls == []
        with sessions() as db:
            interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
            lease = db.get(ChatSandboxLease, session_id)
        assert interval.worker_generation == lease.worker_generation
        assert interval.modal_sandbox_id is None
        assert interval.provider_created_at is None
        assert interval.terminal_at is not None
        assert interval.terminal_reason == "sandbox_start_failed"
        assert interval.reserved_microusd == 0
        assert interval.reconciliation_state == "creation_failed"
        assert lease.state == "failed"
        assert lease.modal_sandbox_id is None
        assert lease.lease_token_hash is None
        assert lease.lease_expires_at is None
        assert lease.failure_code == "sandbox_start_failed"

    asyncio.run(scenario())


def test_unhealthy_reuse_closes_old_interval_before_reserving_and_creating_new():
    settings = _spend_settings()
    sessions = _database()
    session_id = uuid.uuid4()
    old_generation = "generation-old"
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="ready",
                sandbox_id="sb-old",
                worker_generation=old_generation,
            )
        )
        spend = ChatSandboxSpendService(db, settings)
        old_interval_id = spend.reserve_interval(
            origin="direct",
            worker_generation=old_generation,
            chat_session_id=session_id,
        )
        spend.provider_created(old_interval_id, "sb-old")

    class UnhealthyProvider(_Provider):
        async def health(self, sandbox, **options):
            await super().health(sandbox, **options)
            return False

        async def create(self, **options):
            with sessions() as db:
                intervals = list(
                    db.execute(
                        select(ChatSandboxComputeInterval).order_by(
                            ChatSandboxComputeInterval.reserved_at
                        )
                    ).scalars()
                )
            assert len(intervals) == 2
            old, replacement = intervals
            assert old.id == old_interval_id
            assert old.modal_sandbox_id == "sb-old"
            assert old.termination_requested_at is not None
            assert old.terminal_at is not None
            assert old.terminal_reason == "stale_replaced"
            assert old.reconciliation_state == "confirmed"
            assert replacement.modal_sandbox_id is None
            assert replacement.provider_created_at is None
            assert replacement.terminal_at is None
            assert replacement.worker_generation == options["worker_generation"]
            return await super().create(**options)

    provider = UnhealthyProvider(transactions=[])
    manager = _manager(settings, sessions, provider)

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox is provider.created
    assert created is True
    assert outcome == "created"
    assert [call[0] for call in provider.calls] == [
        "resolve",
        "poll",
        "health",
        "terminate",
        "create",
    ]
    assert provider.calls[3][1] == "sb-old"
    with sessions() as db:
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        lease = db.get(ChatSandboxLease, session_id)
    assert len(intervals) == 2
    assert lease.modal_sandbox_id == "sb-created"
    assert lease.worker_generation != old_generation
    assert lease.worker_generation == provider.calls[4][1]
    replacement = next(row for row in intervals if row.id != old_interval_id)
    assert replacement.worker_generation == lease.worker_generation
    assert replacement.modal_sandbox_id == "sb-created"
    assert replacement.provider_created_at is not None


def test_unconfirmed_unhealthy_reuse_keeps_old_owner_and_never_starts_replacement():
    settings = _spend_settings(chat_sandbox_ready_timeout_seconds=0.05)
    sessions = _database()
    session_id = uuid.uuid4()
    old_generation = "generation-old"
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="ready",
                sandbox_id="sb-old",
                worker_generation=old_generation,
            )
        )
        spend = ChatSandboxSpendService(db, settings)
        old_interval_id = spend.reserve_interval(
            origin="direct",
            worker_generation=old_generation,
            chat_session_id=session_id,
        )
        spend.provider_created(old_interval_id, "sb-old")

    class UnconfirmedProvider(_Provider):
        async def health(self, sandbox, **options):
            await super().health(sandbox, **options)
            return False

        async def terminate(self, sandbox_id, sandbox=None):
            await super().terminate(sandbox_id, sandbox)
            return False

    provider = UnconfirmedProvider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "sandbox_capacity"
    assert str(exc_info.value) == "Secure workspace capacity is temporarily full"
    assert exc_info.value.uncertain is False
    assert [call[0] for call in provider.calls] == [
        "resolve",
        "poll",
        "health",
        "terminate",
    ]
    with sessions() as db:
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        lease = db.get(ChatSandboxLease, session_id)
    assert len(intervals) == 1
    assert intervals[0].id == old_interval_id
    assert intervals[0].modal_sandbox_id == "sb-old"
    assert intervals[0].termination_requested_at is not None
    assert intervals[0].terminal_at is None
    assert intervals[0].terminal_reason == "stale_replaced"
    assert intervals[0].reconciliation_state == "termination_uncertain"
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-old"
    assert lease.worker_generation == old_generation
    assert lease.lease_token_hash is not None
    assert lease.lease_expires_at is not None
    assert lease.failure_code == "stale_replaced"


def test_unhealthy_reuse_successor_mismatch_neither_cleans_nor_reserves():
    settings = _spend_settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="ready",
                sandbox_id="sb-old",
                worker_generation="generation-old",
            )
        )
        spend = ChatSandboxSpendService(db, settings)
        interval_id = spend.reserve_interval(
            origin="direct",
            worker_generation="generation-old",
            chat_session_id=session_id,
        )
        spend.provider_created(interval_id, "sb-old")

    class ReplacedDuringHealth(_Provider):
        async def health(self, sandbox, **options):
            await super().health(sandbox, **options)
            if sandbox.object_id == "sb-old":
                with sessions() as db, db.begin():
                    lease = db.get(ChatSandboxLease, session_id)
                    lease.modal_sandbox_id = "sb-successor"
                    lease.worker_generation = "generation-successor"
                return False
            return True

    provider = ReplacedDuringHealth(transactions=[])
    manager = _manager(settings, sessions, provider)
    ensure_calls = 0
    ensure_ready = manager.ensure_ready

    async def counted_ensure_ready(*args, **kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        return await ensure_ready(*args, **kwargs)

    manager.ensure_ready = counted_ensure_ready

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox.object_id == "sb-successor"
    assert created is False
    assert outcome == "reused_session"
    assert ensure_calls == 1
    assert [call[0] for call in provider.calls] == [
        "resolve",
        "poll",
        "health",
        "resolve",
        "poll",
        "health",
    ]
    with sessions() as db:
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        lease = db.get(ChatSandboxLease, session_id)
    assert len(intervals) == 1
    assert intervals[0].terminal_at is None
    assert lease.modal_sandbox_id == "sb-successor"
    assert lease.worker_generation == "generation-successor"
