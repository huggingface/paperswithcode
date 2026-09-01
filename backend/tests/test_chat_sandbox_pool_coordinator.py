from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.chat_sandbox_worker.mcp_app_registry import egress_policy_digest
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    LeaseEvictionOutcome,
)
from backend.services.chat_sandbox_pool_coordinator import (
    POOL_MAINTENANCE_BATCH_SIZE,
    ChatSandboxPoolCoordinator,
    PoolMaintenanceResult,
)
from backend.services.chat_sandbox_pool_creation_coordinator import (
    PoolReplenishmentOutcome,
)
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
    PoolHealthCandidate,
    PoolLandingDurability,
    PoolLandingOutcome,
    PoolStartReservation,
    PoolTerminationClaim,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_worker_transport import (
    BlankStartupMetrics,
    ChatSandboxWorkerTransport,
    SessionControl,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": True,
        "chat_blank_pool_min": 1,
        "chat_blank_pool_max": 2,
        "chat_blank_pool_min_remaining_seconds": 240,
        "chat_blank_pool_refill_concurrency": 2,
        "chat_sandbox_total_live_cap": 4,
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_sandbox_budget_attestation": "attested",
        "chat_workspace_snapshots_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _TrackedSession(Session):
    pass


class _TransactionProbe:
    def __init__(self) -> None:
        self.active = 0
        self.provider_calls: list[str] = []

    def attach(self, sessions) -> None:
        def after_begin(db, transaction, _connection):
            if transaction.parent is None and not db.info.get("probe_active"):
                db.info["probe_active"] = True
                self.active += 1

        def after_transaction_end(db, transaction):
            if transaction.parent is None and db.info.pop("probe_active", False):
                self.active -= 1

        event.listen(sessions.class_, "after_begin", after_begin)
        event.listen(sessions.class_, "after_transaction_end", after_transaction_end)

    def outside_transaction(self, operation: str) -> None:
        assert self.active == 0, f"{operation} ran inside a database transaction"
        self.provider_calls.append(operation)


def _database(probe: _TransactionProbe):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        ChatSession.__table__,
        ChatSandboxPool.__table__,
        ChatSandboxLease.__table__,
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
    ):
        table.create(engine)
    sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=_TrackedSession,
    )
    probe.attach(sessions)
    return sessions


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
        self.tick = 100.0

    def utcnow(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.tick

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.tick += seconds


class _Provider:
    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.sandboxes: dict[str, object] = {}
        self.poll_result = None
        self.resolve_error: BaseException | None = None
        self.health_result = True
        self.health_hook = None
        self.termination_confirmed = True
        self.termination_calls: list[str] = []
        self.termination_hook = None
        self.create_calls: list[dict] = []
        self.create_error: BaseException | None = None
        self.create_hook = None
        self.listed_sandboxes: list[object] = []
        self.list_tags_calls: list[dict[str, str]] = []
        self.sandbox_tags: dict[str, object] = {}
        self.tag_errors: dict[str, BaseException] = {}
        self.iter_hook = None
        self._sandbox_ids = count(1)

    async def create(self, **kwargs):
        self.probe.outside_transaction("provider.create")
        self.create_calls.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        sandbox = SimpleNamespace(object_id=f"sb-created-{next(self._sandbox_ids)}")
        self.sandboxes[sandbox.object_id] = sandbox
        if self.create_hook is not None:
            await self.create_hook(sandbox, kwargs)
        return sandbox

    async def resolve(self, sandbox_id: str):
        self.probe.outside_transaction("provider.resolve")
        await asyncio.sleep(0)
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.sandboxes.setdefault(
            sandbox_id,
            SimpleNamespace(object_id=sandbox_id),
        )

    async def poll(self, _sandbox):
        self.probe.outside_transaction("provider.poll")
        await asyncio.sleep(0)
        return self.poll_result

    async def health(self, _sandbox, *, persistent, worker_generation):
        self.probe.outside_transaction("provider.health")
        assert persistent is True
        assert worker_generation
        if self.health_hook is not None:
            await self.health_hook(_sandbox, worker_generation)
        await asyncio.sleep(0)
        return self.health_result

    async def terminate(self, sandbox_id: str, _sandbox=None):
        self.probe.outside_transaction("provider.terminate")
        self.termination_calls.append(sandbox_id)
        call_number = len(self.termination_calls)
        if self.termination_hook is not None:
            await self.termination_hook(call_number, sandbox_id)
        return self.termination_confirmed

    async def open_persistent_connection(self, *_args, **_kwargs):
        raise AssertionError("not used by increment-A coordinator tests")

    async def open_turn_process(self, *_args, **_kwargs):
        raise AssertionError("not used by increment-A coordinator tests")

    async def get_tags(self, sandbox):
        self.probe.outside_transaction("provider.tags")
        sandbox_id = sandbox.object_id
        if sandbox_id in self.tag_errors:
            raise self.tag_errors[sandbox_id]
        return self.sandbox_tags.get(sandbox_id, {})

    async def iter_sandboxes(self, *, tags):
        self.probe.outside_transaction("provider.list")
        self.list_tags_calls.append(tags)
        for index, sandbox in enumerate(self.listed_sandboxes):
            if self.iter_hook is not None:
                await self.iter_hook(index, sandbox)
            yield sandbox


class _Transport(ChatSandboxWorkerTransport):
    def __init__(self, provider: _Provider, probe: _TransactionProbe) -> None:
        super().__init__(provider, clock=lambda: 100.0)
        self.probe = probe
        self.ping_result = True
        self.ping_error: BaseException | None = None
        self.ping_hook = None
        self.ping_calls: list[tuple[str, str]] = []
        self.open_calls: list[tuple[str, str]] = []
        self.open_error: BaseException | None = None
        self.open_hook = None
        self.ping_startup_metrics: BlankStartupMetrics | None = None

    async def open_persistent_control(
        self,
        sandbox,
        worker_generation: str,
    ) -> SessionControl:
        self.probe.outside_transaction("transport.open")
        self.open_calls.append((sandbox.object_id, worker_generation))
        if self.open_hook is not None:
            await self.open_hook(sandbox, worker_generation)
        if self.open_error is not None:
            raise self.open_error
        return _control(sandbox)

    async def ping(self, control: SessionControl, worker_generation: str) -> bool:
        self.probe.outside_transaction("transport.ping")
        self.ping_calls.append((control.sandbox_id, worker_generation))
        if self.ping_hook is not None:
            await self.ping_hook(control, worker_generation)
        if self.ping_error is not None:
            raise self.ping_error
        await asyncio.sleep(0)
        if self.ping_result and self.ping_startup_metrics is not None:
            self.blank_startup[control.sandbox_id] = self.ping_startup_metrics
        return self.ping_result


class _LeaseEviction:
    def __init__(self, evict_idle):
        self._evict_idle = evict_idle

    async def evict_idle(
        self,
        chat_session_id: uuid.UUID,
    ) -> LeaseEvictionOutcome:
        return await self._evict_idle(chat_session_id)


class _Harness:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        capacity_locker=None,
        lease_eviction=None,
        lease_loader=None,
        maintenance_locker=None,
        spend_factory=None,
        owner: bool = False,
    ) -> None:
        self.settings = settings or _settings()
        self.clock = _Clock()
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        token_counter = count(1)
        self.repository = ChatSandboxPoolRepository(
            self.settings,
            capacity_locker=(capacity_locker or (lambda _db, *, wait=True: True)),
            lease_loader=lease_loader,
            token_factory=lambda: f"operation-{next(token_counter)}",
        )
        self.provider = _Provider(self.probe)
        self.transport = _Transport(self.provider, self.probe)
        self.owner = owner
        self.evictions: list[uuid.UUID] = []

        async def default_evict(session_id: uuid.UUID) -> LeaseEvictionOutcome:
            self.probe.outside_transaction("assigned.evict")
            self.evictions.append(session_id)
            return LeaseEvictionOutcome.NOT_IDLE

        self.coordinator = ChatSandboxPoolCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            maintenance_owner=lambda: self.owner,
            lease_eviction=(lease_eviction or _LeaseEviction(default_evict)),
            maintenance_locker=(maintenance_locker or (lambda _db: True)),
            spend_factory=(
                spend_factory or (lambda db: ChatSandboxSpendService(db, self.settings))
            ),
            utcnow=self.clock.utcnow,
            monotonic=self.clock.monotonic,
        )


def _session(session_id: uuid.UUID) -> ChatSession:
    return ChatSession(
        id=session_id,
        hf_user_id=f"owner-{session_id}",
        hf_username=f"owner-{session_id}",
        selected_model="google/gemma-4-31B-it",
        execution_backend="modal_cli",
    )


def _pool(
    harness: _Harness,
    *,
    sandbox_id: str | None = "sb-blank",
    state: str = "blank_ready",
    release_id: str | None = None,
) -> ChatSandboxPool:
    now = harness.clock.utcnow()
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        state=state,
        image_version=harness.settings.chat_modal_image_version,
        worker_contract_version=harness.settings.chat_worker_contract_version,
        worker_generation=f"generation-{uuid.uuid4().hex[:8]}",
        app_release_id=release_id or harness.settings.release_id,
        claim_generation=0,
        created_at=now - timedelta(minutes=2),
        ready_at=now - timedelta(minutes=1) if state != "starting" else None,
        expires_at=now + timedelta(hours=1),
        updated_at=now - timedelta(minutes=1),
        cpu_request=harness.settings.chat_sandbox_cpu,
        cpu_limit=(
            harness.settings.chat_sandbox_cpu_limit or harness.settings.chat_sandbox_cpu
        ),
        memory_request_mib=harness.settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            harness.settings.chat_sandbox_memory_limit_mib
            or harness.settings.chat_sandbox_memory_mib
        ),
        billing_month=now.date().replace(day=1),
    )


def _interval(
    harness: _Harness,
    row: ChatSandboxPool,
    *,
    reserved_microusd: int = 1,
) -> ChatSandboxComputeInterval:
    now = harness.clock.utcnow()
    return ChatSandboxComputeInterval(
        id=uuid.uuid4(),
        modal_sandbox_id=row.modal_sandbox_id,
        environment=harness.settings.environment,
        modal_app="pwc-chat-sandboxes",
        app_release_id=harness.settings.release_id,
        image_version=harness.settings.chat_modal_image_version,
        worker_generation=row.worker_generation,
        origin="blank_pool",
        cpu_request_millicores=round(harness.settings.chat_sandbox_cpu * 1000),
        cpu_limit_millicores=round(
            (
                harness.settings.chat_sandbox_cpu_limit
                or harness.settings.chat_sandbox_cpu
            )
            * 1000
        ),
        memory_request_mib=harness.settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            harness.settings.chat_sandbox_memory_limit_mib
            or harness.settings.chat_sandbox_memory_mib
        ),
        reserved_at=now - timedelta(minutes=2),
        provider_created_at=now - timedelta(minutes=2),
        billing_cycle=now.date().replace(day=1),
        reserved_microusd=reserved_microusd,
        updated_at=now,
    )


def _control(sandbox: object) -> SessionControl:
    return SessionControl(
        process=SimpleNamespace(),
        sandbox=sandbox,
        sandbox_id=sandbox.object_id,
        stderr_task=None,
        reader_task=None,
        queues={},
        resume_id=None,
    )


def _pool_tags(harness: _Harness, row: ChatSandboxPool) -> dict[str, str]:
    return {
        "service": "pwc-chat",
        "environment": harness.settings.environment,
        "pool": "blank",
        "pool_id": str(row.id),
        "release": row.app_release_id,
        "image": row.image_version,
        "contract": row.worker_contract_version,
        "egress": row.egress_policy_digest,
    }


def _orphan_tags(harness: _Harness) -> dict[str, str]:
    return {
        "service": "pwc-chat",
        "environment": harness.settings.environment,
        "pool": "blank",
        "pool_id": str(uuid.uuid4()),
        "release": harness.settings.release_id,
        "image": harness.settings.chat_modal_image_version,
        "contract": harness.settings.chat_worker_contract_version,
        "egress": egress_policy_digest(harness.settings),
    }


def test_coordinator_requires_provider_and_transport_identity():
    harness = _Harness()
    other_provider = _Provider(harness.probe)

    with pytest.raises(ValueError, match="provider and transport must be shared"):
        ChatSandboxPoolCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=other_provider,
            transport=harness.transport,
            maintenance_owner=lambda: True,
            lease_eviction=_LeaseEviction(
                lambda _session_id: asyncio.sleep(
                    0,
                    result=LeaseEvictionOutcome.NOT_IDLE,
                )
            ),
            spend_factory=lambda db: ChatSandboxSpendService(db, harness.settings),
        )


def test_fresh_local_health_claim_promotes_the_exact_control():
    harness = _Harness()
    session_id = uuid.uuid4()
    row = _pool(harness)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    control = _control(sandbox)
    harness.transport.register_blank_control(
        row.modal_sandbox_id,
        control,
        checked_at=harness.clock.monotonic(),
    )
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    result = asyncio.run(harness.coordinator.claim_blank(session_id))

    assert result == (sandbox, 0)
    assert harness.probe.provider_calls == []
    assert harness.transport.blank_control(row.modal_sandbox_id) is None
    assert harness.transport.session_control(session_id) is control


def test_stale_local_control_falls_back_to_provider_health():
    harness = _Harness()
    row = _pool(harness)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    harness.provider.sandboxes[row.modal_sandbox_id] = sandbox
    control = _control(sandbox)
    harness.transport.register_blank_control(
        row.modal_sandbox_id,
        control,
        checked_at=0.0,
    )
    harness.transport.ping_result = False

    result = asyncio.run(
        harness.coordinator.maintenance.pool_sandbox_health(
            row.modal_sandbox_id,
            row.worker_generation,
        )
    )

    assert result is sandbox
    assert harness.transport.blank_control(row.modal_sandbox_id) is None
    assert harness.probe.provider_calls == [
        "transport.ping",
        "provider.resolve",
        "provider.poll",
        "provider.health",
    ]


def test_provider_health_claim_is_release_agnostic_and_outside_transactions():
    harness = _Harness()
    session_id = uuid.uuid4()
    row = _pool(harness, release_id="release-previous")
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    result = asyncio.run(harness.coordinator.claim_blank(session_id))

    assert result is not None
    assert result[0].object_id == row.modal_sandbox_id
    assert harness.probe.provider_calls == [
        "provider.resolve",
        "provider.poll",
        "provider.health",
    ]
    with harness.sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        lease = db.get(ChatSandboxLease, session_id)
    assert claimed.state == "claimed"
    assert claimed.app_release_id == "release-previous"
    assert lease.modal_sandbox_id == row.modal_sandbox_id


def test_stale_maintenance_plan_cannot_probe_a_promoted_control():
    harness = _Harness(owner=True)
    session_id = uuid.uuid4()
    row = _pool(harness)
    row.expires_at = harness.clock.utcnow() + timedelta(hours=2)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    # Simulate a second API process: independent coordinator/repository/provider
    # state, with only the database shared with maintenance.
    claim_provider = _Provider(harness.probe)
    claim_transport = _Transport(claim_provider, harness.probe)
    claim_repository = ChatSandboxPoolRepository(
        harness.settings,
        capacity_locker=lambda _db, *, wait=True: True,
    )
    claim_coordinator = ChatSandboxPoolCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=claim_repository,
        provider=claim_provider,
        transport=claim_transport,
        maintenance_owner=lambda: False,
        lease_eviction=_LeaseEviction(
            lambda _session_id: asyncio.sleep(
                0,
                result=LeaseEvictionOutcome.NOT_IDLE,
            )
        ),
        spend_factory=lambda db: ChatSandboxSpendService(db, harness.settings),
        utcnow=harness.clock.utcnow,
        monotonic=harness.clock.monotonic,
    )
    control = _control(sandbox)
    claim_transport.register_blank_control(
        row.modal_sandbox_id,
        control,
        checked_at=harness.clock.monotonic(),
    )

    planned = harness.coordinator.maintenance._plan_maintenance(harness.clock.utcnow())
    assert planned is not None
    _, plan = planned
    assert len(plan.health_candidates) == 1

    assert asyncio.run(claim_coordinator.claim_blank(session_id)) == (sandbox, 0)
    assert claim_transport.session_control(session_id) is control

    async def replace_promoted_relay(_sandbox, _worker_generation):
        pytest.fail("stale maintenance must not perform provider health I/O")

    harness.provider.health_hook = replace_promoted_relay
    assert (
        asyncio.run(
            harness.coordinator.maintenance._refresh_pool_health(plan.health_candidates)
        )
        == 0
    )

    assert "provider.health" not in harness.probe.provider_calls
    assert claim_transport.session_control(session_id) is control


def test_health_owner_blocks_racing_chat_claim_until_probe_settles():
    harness = _Harness(owner=True)
    session_id = uuid.uuid4()
    row = _pool(harness)
    row.expires_at = harness.clock.utcnow() + timedelta(hours=2)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])
    planned = harness.coordinator.maintenance._plan_maintenance(harness.clock.utcnow())
    assert planned is not None
    _, plan = planned
    health_started = asyncio.Event()
    release_health = asyncio.Event()

    async def pause_health(_sandbox, _worker_generation):
        health_started.set()
        await release_health.wait()

    harness.provider.health_hook = pause_health

    async def run():
        maintenance = asyncio.create_task(
            harness.coordinator.maintenance._refresh_pool_health(plan.health_candidates)
        )
        await health_started.wait()
        with harness.sessions() as db:
            owned = db.get(ChatSandboxPool, row.id)
            assert owned.health_check_token_hash is not None
        assert await harness.coordinator.claim_blank(session_id) is None
        release_health.set()
        return await maintenance

    assert asyncio.run(run()) == 0
    with harness.sessions() as db:
        settled = db.get(ChatSandboxPool, row.id)
    assert settled.state == "blank_ready"
    assert settled.health_check_token_hash is None


def test_unavailable_health_probe_stays_excluded_until_stale_recovery():
    harness = _Harness(owner=True)
    row = _pool(harness)
    row.expires_at = harness.clock.utcnow() + timedelta(hours=2)
    with harness.sessions() as db, db.begin():
        db.add(row)
    planned = harness.coordinator.maintenance._plan_maintenance(harness.clock.utcnow())
    assert planned is not None
    _, plan = planned
    harness.provider.resolve_error = RuntimeError("provider unavailable")

    assert (
        asyncio.run(
            harness.coordinator.maintenance._refresh_pool_health(plan.health_candidates)
        )
        == 0
    )
    with harness.sessions() as db:
        unavailable = db.get(ChatSandboxPool, row.id)
    assert unavailable.state == "blank_ready"
    assert unavailable.health_check_token_hash is not None

    harness.clock.advance(31)
    recovered = harness.coordinator.maintenance._plan_maintenance(
        harness.clock.utcnow()
    )
    assert recovered is not None
    _, recovery_plan = recovered
    assert len(recovery_plan.termination_claims) == 1
    with harness.sessions() as db:
        draining = db.get(ChatSandboxPool, row.id)
    assert draining.state == "draining"
    assert draining.health_check_token_hash is None
    assert draining.failure_code == "health_check_timeout"


def test_concurrent_claims_commit_one_exact_claim_and_spend_assignment():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(first_id), _session(second_id), row, interval])

    async def run():
        return await asyncio.gather(
            harness.coordinator.claim_blank(first_id),
            harness.coordinator.claim_blank(second_id),
        )

    results = asyncio.run(run())

    assert sum(result is not None for result in results) == 1
    with harness.sessions() as db:
        leases = list(db.scalars(select(ChatSandboxLease)))
        assigned_interval = db.get(ChatSandboxComputeInterval, interval.id)
        claimed = db.get(ChatSandboxPool, row.id)
    assert claimed.state == "claimed"
    assert claimed.claim_generation == 1
    assert len(leases) == 1
    assert assigned_interval.chat_session_id == leases[0].chat_session_id
    assert assigned_interval.claimed_at is not None


def test_claim_orders_capacity_availability_lease_pool_and_spend():
    order: list[str] = []

    def lock_capacity(_db, *, wait=True):
        assert wait is True
        order.append("capacity")
        return True

    def load_lease(db, session_id, *, lock):
        assert lock is True
        order.append("lease")
        return db.get(ChatSandboxLease, session_id)

    class Spend:
        def assert_available(self, _now, *, capacity_locked):
            assert capacity_locked is True
            order.append("availability")

        def claim(self, _sandbox_id, _session_id, _now):
            order.append("spend")

    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        capacity_locker=lock_capacity,
        lease_loader=load_lease,
        spend_factory=lambda _db: Spend(),
    )
    session_id = uuid.uuid4()
    row = _pool(harness)
    sandbox = SimpleNamespace(object_id=row.modal_sandbox_id)
    harness.transport.register_blank_control(
        row.modal_sandbox_id,
        _control(sandbox),
        checked_at=harness.clock.monotonic(),
    )
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])
    pool_selects = 0

    def record_pool_select(_connection, _cursor, statement, *_args):
        nonlocal pool_selects
        if statement.lstrip().startswith("SELECT") and "chat_sandbox_pool" in statement:
            pool_selects += 1
            order.append("candidate" if pool_selects == 1 else "pool")

    event.listen(
        harness.sessions.kw["bind"],
        "before_cursor_execute",
        record_pool_select,
    )

    assert asyncio.run(harness.coordinator.claim_blank(session_id)) == (sandbox, 0)
    assert order == [
        "candidate",
        "capacity",
        "availability",
        "lease",
        "pool",
        "spend",
    ]


def test_claim_transaction_rolls_back_when_injected_lease_loader_fails():
    def fail_lease_load(*_args, **_kwargs):
        raise RuntimeError("simulated lease failure")

    harness = _Harness(lease_loader=fail_lease_load)
    session_id = uuid.uuid4()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    with pytest.raises(RuntimeError, match="simulated lease failure"):
        asyncio.run(harness.coordinator.claim_blank(session_id))

    with harness.sessions() as db:
        unchanged = db.get(ChatSandboxPool, row.id)
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert unchanged.state == "blank_ready"
    assert unchanged.claimed_at is None
    assert lease_count == 0


def test_spend_denial_commits_circuit_but_does_not_claim_blank():
    harness = _Harness(
        settings=_settings(
            chat_sandbox_spend_enforcement_enabled=True,
            chat_sandbox_warning_microusd=500_000,
            chat_sandbox_application_cap_microusd=1_000_000,
            chat_sandbox_environment_cap_microusd=2_000_000,
            chat_sandbox_workspace_cap_microusd=3_000_000,
        )
    )
    session_id = uuid.uuid4()
    row = _pool(harness)
    interval = _interval(harness, row, reserved_microusd=1_000_000)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row, interval])

    with pytest.raises(SandboxError) as raised:
        asyncio.run(harness.coordinator.claim_blank(session_id))

    assert raised.value.code == "chat_temporarily_disabled"
    with harness.sessions() as db:
        unchanged = db.get(ChatSandboxPool, row.id)
        state = db.execute(select(ChatSandboxBudgetState)).scalar_one()
        event_row = db.execute(select(ChatSandboxCircuitEvent)).scalar_one()
        lease_count = db.scalar(select(func.count()).select_from(ChatSandboxLease))
    assert unchanged.state == "blank_ready"
    assert state.circuit_state == "tripped"
    assert event_row.event_type == "circuit_tripped"
    assert lease_count == 0


def test_unhealthy_provider_blank_is_disposed_outside_the_claim_transaction():
    harness = _Harness()
    harness.provider.health_result = False
    session_id = uuid.uuid4()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    assert asyncio.run(harness.coordinator.claim_blank(session_id)) is None

    assert harness.probe.provider_calls == [
        "provider.resolve",
        "provider.poll",
        "provider.health",
        "provider.terminate",
    ]
    assert harness.provider.termination_calls == [row.modal_sandbox_id]
    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "sandbox_lost"


def test_transient_provider_health_failure_preserves_blank_for_later_retry():
    harness = _Harness()
    harness.provider.resolve_error = TimeoutError("provider unavailable")
    session_id = uuid.uuid4()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add_all([_session(session_id), row])

    assert asyncio.run(harness.coordinator.claim_blank(session_id)) is None

    assert harness.probe.provider_calls == ["provider.resolve"]
    assert harness.provider.termination_calls == []
    with harness.sessions() as db:
        preserved = db.get(ChatSandboxPool, row.id)
    assert preserved.state == "blank_ready"
    assert preserved.failure_code is None


def test_termination_uses_persisted_sandbox_id_when_hint_is_none():
    harness = _Harness()
    row = _pool(harness, sandbox_id="sb-persisted")
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def assert_preclaim_committed(_call_number, sandbox_id):
        with harness.sessions() as db:
            draining = db.get(ChatSandboxPool, row.id)
        assert sandbox_id == "sb-persisted"
        assert draining.state == "draining"
        assert draining.claim_token_hash is not None

    harness.provider.termination_hook = assert_preclaim_committed

    assert (
        asyncio.run(
            harness.coordinator.terminate_pool_row(
                row.id,
                None,
                failure_code=None,
            )
        )
        is True
    )
    assert harness.provider.termination_calls == ["sb-persisted"]
    with harness.sessions() as db:
        terminated = db.get(ChatSandboxPool, row.id)
    assert terminated.state == "terminated"


def test_fresh_duplicate_termination_cannot_steal_the_provider_claim():
    harness = _Harness()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def block_first(call_number, _sandbox_id):
            if call_number == 1:
                started.set()
                await release.wait()

        harness.provider.termination_hook = block_first
        first = asyncio.create_task(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code=None,
            )
        )
        await started.wait()
        duplicate = await harness.coordinator.terminate_pool_row(
            row.id,
            row.modal_sandbox_id,
            failure_code="duplicate_failure",
        )
        release.set()
        return await first, duplicate

    first, duplicate = asyncio.run(run())

    assert first is True
    assert duplicate is False
    assert harness.provider.termination_calls == [row.modal_sandbox_id]


def test_stale_takeover_changes_token_and_fences_the_first_finisher():
    harness = _Harness()
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add(row)

    async def run():
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def block_first(call_number, _sandbox_id):
            if call_number == 1:
                first_started.set()
                await release_first.wait()

        harness.provider.termination_hook = block_first
        first = asyncio.create_task(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code="first_failure",
            )
        )
        await first_started.wait()
        with harness.sessions() as db:
            first_token = db.get(ChatSandboxPool, row.id).claim_token_hash
        harness.clock.advance(harness.coordinator.termination_claim_timeout_seconds + 1)
        successor = await harness.coordinator.terminate_pool_row(
            row.id,
            row.modal_sandbox_id,
            failure_code="second_failure",
        )
        with harness.sessions() as db:
            successor_token = db.get(ChatSandboxPool, row.id).claim_token_hash
        release_first.set()
        return await first, successor, first_token, successor_token

    first, successor, first_token, successor_token = asyncio.run(run())

    assert first is False
    assert successor is True
    assert successor_token != first_token
    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
    assert failed.state == "failed"
    assert failed.failure_code == "first_failure"


def test_unconfirmed_termination_preserves_spend_reason_and_marks_uncertainty():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    harness.provider.termination_confirmed = False
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])

    assert (
        asyncio.run(
            harness.coordinator.terminate_pool_row(
                row.id,
                row.modal_sandbox_id,
                failure_code="sandbox_lost",
            )
        )
        is True
    )

    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
        spend = db.get(ChatSandboxComputeInterval, interval.id)
    assert failed.state == "failed"
    assert failed.failure_code == "termination_uncertain"
    assert spend.terminal_reason == "sandbox_lost"
    assert spend.reconciliation_state == "termination_uncertain"


def test_exact_finish_ownership_loss_does_not_mutate_successor_or_spend():
    harness = _Harness(settings=_settings(chat_sandbox_spend_enforcement_enabled=True))
    row = _pool(harness)
    interval = _interval(harness, row)
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    with harness.sessions() as db, db.begin():
        claim = harness.repository.claim_termination(
            db,
            row.id,
            row.modal_sandbox_id,
            failure_code=None,
            now=harness.clock.utcnow(),
            stale_draining_before=harness.clock.utcnow() - timedelta(minutes=1),
        )
    assert isinstance(claim, PoolTerminationClaim)
    with harness.sessions() as db, db.begin():
        successor = db.get(ChatSandboxPool, row.id)
        successor.claim_token_hash = "successor-token"

    assert asyncio.run(harness.coordinator.terminate_claimed_pool_row(claim)) is False

    with harness.sessions() as db:
        successor = db.get(ChatSandboxPool, row.id)
        spend = db.get(ChatSandboxComputeInterval, interval.id)
    assert successor.state == "draining"
    assert successor.claim_token_hash == "successor-token"
    assert successor.terminated_at is None
    assert spend.termination_requested_at is None


def test_termination_batch_is_bounded_by_configured_concurrency():
    harness = _Harness(
        settings=_settings(
            chat_blank_pool_max=4,
            chat_blank_pool_refill_concurrency=2,
        )
    )
    rows = [_pool(harness, sandbox_id=f"sb-{index}") for index in range(5)]
    with harness.sessions() as db, db.begin():
        db.add_all(rows)
    claims = []
    with harness.sessions() as db, db.begin():
        for row in rows:
            claim = harness.repository.claim_termination(
                db,
                row.id,
                row.modal_sandbox_id,
                failure_code=None,
                now=harness.clock.utcnow(),
                stale_draining_before=harness.clock.utcnow() - timedelta(minutes=1),
            )
            assert isinstance(claim, PoolTerminationClaim)
            claims.append(claim)

    async def run():
        release = asyncio.Event()
        two_started = asyncio.Event()
        active = 0
        maximum = 0

        async def block(call_number, _sandbox_id):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if call_number == 2:
                two_started.set()
            await release.wait()
            active -= 1

        harness.provider.termination_hook = block
        task = asyncio.create_task(
            harness.coordinator.terminate_claimed_pool_rows(claims)
        )
        await two_started.wait()
        await asyncio.sleep(0)
        assert len(harness.provider.termination_calls) == 2
        release.set()
        return await task, maximum

    terminated, maximum = asyncio.run(run())

    assert harness.coordinator.termination_concurrency == 2
    assert terminated == 5
    assert maximum == 2


def test_replenish_creates_control_pings_and_lands_the_exact_spend_interval():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    harness.transport.ping_startup_metrics = BlankStartupMetrics(
        broker_ready_ms=11,
        control_ready_ms=18,
        agent_spawn_ms=19,
        agent_startup_ready_ms=74,
        agent_prestarted=True,
    )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 1

    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "blank_ready"
    assert pool.modal_sandbox_id == "sb-created-1"
    assert pool.ready_at == harness.clock.utcnow().replace(tzinfo=None)
    assert pool.provider_create_ms == 0
    assert pool.backend_control_connect_ms == 0
    assert pool.broker_ready_ms == 11
    assert pool.control_ready_ms == 18
    assert pool.agent_spawn_ms == 19
    assert pool.agent_startup_ready_ms == 74
    assert interval.worker_generation == pool.worker_generation
    assert interval.modal_sandbox_id == pool.modal_sandbox_id
    assert interval.provider_created_at == harness.clock.utcnow().replace(tzinfo=None)
    assert interval.terminal_at is None
    assert harness.transport.blank_control(pool.modal_sandbox_id) is not None
    assert harness.transport.open_calls == [
        (pool.modal_sandbox_id, pool.worker_generation)
    ]
    assert harness.transport.ping_calls == [
        (pool.modal_sandbox_id, pool.worker_generation)
    ]
    assert harness.probe.provider_calls == [
        "provider.create",
        "transport.open",
        "transport.ping",
    ]
    assert harness.provider.create_calls == [
        {
            "name": f"chat-blank-{pool.id}",
            "tags": {
                "service": "pwc-chat",
                "environment": "staging",
                "pool": "blank",
                "pool_id": str(pool.id),
                "release": harness.settings.release_id,
                "image": harness.settings.chat_modal_image_version,
                "contract": harness.settings.chat_worker_contract_version,
                "egress": egress_policy_digest(harness.settings),
            },
            "worker_generation": pool.worker_generation,
        }
    ]


def test_refill_commits_reservation_and_interval_before_provider_creation():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    observed: dict[str, object] = {}

    async def inspect_committed_reservation(_sandbox, _kwargs):
        with harness.sessions() as db:
            pool = db.execute(select(ChatSandboxPool)).scalar_one()
            interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
        observed.update(
            pool_state=pool.state,
            pool_sandbox_id=pool.modal_sandbox_id,
            pool_token=pool.claim_token_hash,
            interval_generation=interval.worker_generation,
            interval_sandbox_id=interval.modal_sandbox_id,
            pool_generation=pool.worker_generation,
        )

    harness.provider.create_hook = inspect_committed_reservation

    assert asyncio.run(harness.coordinator.replenish_pool()) == 1
    assert observed["pool_state"] == "starting"
    assert observed["pool_sandbox_id"] is None
    assert isinstance(observed["pool_token"], str)
    assert observed["pool_token"]
    assert observed["interval_generation"] == observed["pool_generation"]
    assert observed["interval_sandbox_id"] is None


def test_creation_component_reports_typed_start_failure():
    harness = _Harness(owner=True)
    harness.provider.create_error = RuntimeError("provider create failed")

    outcome = asyncio.run(harness.coordinator.creation.replenish())

    assert outcome is PoolReplenishmentOutcome.START_FAILED
    assert outcome.created_count == 0


def test_prewarm_refill_rejects_legacy_health_without_prestarted_agent_proof():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_pi_prewarm_enabled=True),
    )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 0
    assert harness.provider.termination_calls == ["sb-created-1"]
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
    assert pool.state == "failed"
    assert pool.failure_code == "sandbox_start_failed"


def test_concurrent_replenish_is_bounded_and_stops_at_the_database_target():
    harness = _Harness(
        owner=True,
        settings=_settings(
            chat_blank_pool_min=2,
            chat_blank_pool_max=2,
            chat_blank_pool_refill_concurrency=2,
            chat_sandbox_total_live_cap=4,
        ),
    )

    async def run():
        release = asyncio.Event()
        two_started = asyncio.Event()
        active = 0
        maximum = 0

        async def block_create(_sandbox, _kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                two_started.set()
            await release.wait()
            active -= 1

        harness.provider.create_hook = block_create
        tasks = [
            asyncio.create_task(harness.coordinator.replenish_pool()) for _ in range(6)
        ]
        await two_started.wait()
        await asyncio.sleep(0)
        assert len(harness.provider.create_calls) == 2
        release.set()
        return await asyncio.gather(*tasks), maximum

    results, maximum = asyncio.run(run())

    assert sum(results) == 2
    assert maximum == 2
    assert len(harness.provider.create_calls) == 2
    with harness.sessions() as db:
        pools = list(db.scalars(select(ChatSandboxPool)))
    assert len(pools) == 2
    assert {pool.state for pool in pools} == {"blank_ready"}


@pytest.mark.parametrize(
    "setting_overrides,owner",
    [
        ({"chat_blank_pool_enabled": False}, True),
        ({"chat_persistent_worker_enabled": False}, True),
        ({"chat_blank_pool_min": 0}, True),
        ({}, False),
    ],
)
def test_replenish_respects_feature_and_owner_gates(setting_overrides, owner):
    harness = _Harness(
        owner=owner,
        settings=_settings(**setting_overrides),
    )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 0
    assert harness.provider.create_calls == []
    with harness.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ChatSandboxPool)) == 0


def test_owner_loss_skips_a_queued_refill_but_finishes_a_committed_reservation():
    harness = _Harness(
        owner=True,
        settings=_settings(
            chat_blank_pool_min=2,
            chat_blank_pool_max=2,
            chat_blank_pool_refill_concurrency=1,
        ),
    )

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def block_create(_sandbox, _kwargs):
            started.set()
            await release.wait()

        harness.provider.create_hook = block_create
        committed = asyncio.create_task(harness.coordinator.replenish_pool())
        await started.wait()
        harness.coordinator.spawn_replenishment()
        assert len(harness.coordinator.creation._tasks) == 1
        harness.owner = False
        release.set()
        first = await committed
        await asyncio.gather(*tuple(harness.coordinator.creation._tasks))
        await asyncio.sleep(0)
        return first

    assert asyncio.run(run()) == 1
    assert len(harness.provider.create_calls) == 1
    assert harness.coordinator.creation._tasks == set()
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
    assert pool.state == "blank_ready"


def test_total_cap_evicts_outside_the_transaction_then_retries_once():
    holder: dict[str, _Harness] = {}
    session_id = uuid.uuid4()

    async def evict_idle(
        candidate_session_id: uuid.UUID,
    ) -> LeaseEvictionOutcome:
        harness = holder["harness"]
        harness.probe.outside_transaction("assigned.evict")
        harness.evictions.append(candidate_session_id)
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, candidate_session_id)
            lease.state = "terminated"
            lease.modal_sandbox_id = None
            lease.updated_at = harness.clock.utcnow()
        return LeaseEvictionOutcome.EVICTED

    harness = _Harness(
        owner=True,
        settings=_settings(
            chat_blank_pool_min=1,
            chat_blank_pool_max=1,
            chat_sandbox_total_live_cap=1,
        ),
        lease_eviction=_LeaseEviction(evict_idle),
    )
    holder["harness"] = harness
    with harness.sessions() as db, db.begin():
        db.add_all(
            [
                _session(session_id),
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id="sb-idle",
                    app_release_id=harness.settings.release_id,
                    image_version=harness.settings.chat_modal_image_version,
                    worker_contract_version=(
                        harness.settings.chat_worker_contract_version
                    ),
                    worker_generation="generation-idle",
                    state="idle",
                    last_activity_at=harness.clock.utcnow() - timedelta(hours=1),
                    workspace_dirty=False,
                    created_at=harness.clock.utcnow() - timedelta(hours=1),
                    updated_at=harness.clock.utcnow() - timedelta(hours=1),
                ),
            ]
        )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 1

    assert harness.evictions == [session_id]
    assert harness.probe.provider_calls == [
        "assigned.evict",
        "provider.create",
        "transport.open",
        "transport.ping",
    ]
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
    assert lease.state == "terminated"
    assert pool.state == "blank_ready"


def test_provider_failure_before_an_object_aborts_the_exact_reservation():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    harness.provider.create_error = RuntimeError("provider create failed")

    assert asyncio.run(harness.coordinator.replenish_pool()) == 0

    assert harness.provider.termination_calls == []
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.modal_sandbox_id is None
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.modal_sandbox_id is None
    assert interval.provider_created_at is None
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.reconciliation_state == "creation_failed"


@pytest.mark.parametrize("failure", ["open", "ping_false", "ping_error"])
def test_control_or_ping_failure_terminates_the_created_provider(failure):
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    if failure == "open":
        harness.transport.open_error = RuntimeError("control open failed")
    elif failure == "ping_false":
        harness.transport.ping_result = False
    else:
        harness.transport.ping_error = RuntimeError("ping failed")

    outcome = asyncio.run(harness.coordinator.creation.replenish())

    assert outcome is PoolReplenishmentOutcome.START_FAILED
    assert outcome.created_count == 0
    assert harness.provider.termination_calls == ["sb-created-1"]
    assert harness.transport.blank_control("sb-created-1") is None
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.modal_sandbox_id == "sb-created-1"
    assert interval.provider_created_at is not None
    assert interval.terminal_at is not None
    assert interval.terminal_reason == "sandbox_start_failed"


@pytest.mark.parametrize("termination_failure", ["unconfirmed", "error"])
def test_failed_start_records_uncertain_provider_cleanup(termination_failure):
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    harness.transport.ping_result = False
    if termination_failure == "unconfirmed":
        harness.provider.termination_confirmed = False
    else:

        async def fail_termination(_call_number, _sandbox_id):
            raise RuntimeError("provider termination unavailable")

        harness.provider.termination_hook = fail_termination

    outcome = asyncio.run(harness.coordinator.creation.replenish())

    assert outcome is PoolReplenishmentOutcome.START_FAILED
    assert harness.provider.termination_calls == ["sb-created-1"]
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.modal_sandbox_id == "sb-created-1"
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.terminal_at is None
    assert interval.reconciliation_state == "termination_uncertain"


def test_landing_ownership_change_fences_the_successor_and_settles_the_start():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    successor_token = "successor-token"

    def move_ownership(db, reservation, _sandbox_id, *, now, **_metrics):
        row = db.get(ChatSandboxPool, reservation.pool_id)
        row.claim_token_hash = successor_token
        row.updated_at = now
        return PoolLandingOutcome.OWNERSHIP_CHANGED

    harness.repository.land_provider_creation = move_ownership

    outcome = asyncio.run(harness.coordinator.creation.replenish())

    assert outcome is PoolReplenishmentOutcome.OWNERSHIP_CHANGED
    assert outcome.created_count == 0
    assert harness.provider.termination_calls == ["sb-created-1"]
    assert harness.transport.blank_control("sb-created-1") is None
    with harness.sessions() as db:
        successor = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert successor.state == "starting"
    assert successor.claim_token_hash == successor_token
    assert successor.failure_code is None
    assert interval.modal_sandbox_id == "sb-created-1"
    assert interval.terminal_reason == "ownership_changed"


def test_landing_exception_not_durable_cleans_up_then_propagates():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    original_land = harness.repository.land_provider_creation

    def fail_after_flush(db, reservation, sandbox_id, *, now, **metrics):
        outcome = original_land(db, reservation, sandbox_id, now=now, **metrics)
        db.flush()
        raise RuntimeError(f"landing failed after {outcome}")

    harness.repository.land_provider_creation = fail_after_flush

    with pytest.raises(RuntimeError, match="landing failed after landed"):
        asyncio.run(harness.coordinator.replenish_pool())

    assert harness.provider.termination_calls == ["sb-created-1"]
    assert harness.transport.blank_control("sb-created-1") is None
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.terminal_reason == "sandbox_start_failed"


def test_spend_landing_failure_rolls_back_then_compensates_the_exact_start():
    settings = _settings(chat_sandbox_spend_enforcement_enabled=True)
    provider_created_calls = 0

    class FailFirstProviderLanding(ChatSandboxSpendService):
        def provider_created(self, interval_id, sandbox_id, now=None):
            nonlocal provider_created_calls
            provider_created_calls += 1
            if provider_created_calls == 1:
                raise RuntimeError("spend landing failed")
            return super().provider_created(interval_id, sandbox_id, now)

    harness = _Harness(
        owner=True,
        settings=settings,
        spend_factory=lambda db: FailFirstProviderLanding(db, settings),
    )

    with pytest.raises(RuntimeError, match="spend landing failed"):
        asyncio.run(harness.coordinator.replenish_pool())

    assert provider_created_calls == 2
    assert harness.provider.termination_calls == ["sb-created-1"]
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.modal_sandbox_id is None
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.modal_sandbox_id == "sb-created-1"
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.terminal_at == harness.clock.utcnow().replace(tzinfo=None)


@pytest.mark.parametrize(
    "durability,expected_result,control_retained",
    [
        (PoolLandingDurability.BLANK_READY, 1, True),
        (PoolLandingDurability.OWNERSHIP_MOVED, 0, False),
    ],
)
def test_ambiguous_landing_uses_durable_classification(
    durability,
    expected_result,
    control_retained,
):
    harness = _Harness(owner=True)

    def ambiguous_landing(*_args, **_kwargs):
        raise RuntimeError("ambiguous commit result")

    harness.repository.land_provider_creation = ambiguous_landing
    harness.coordinator.creation._landing_durability = lambda *_args: durability

    assert asyncio.run(harness.coordinator.replenish_pool()) == expected_result

    control = harness.transport.blank_control("sb-created-1")
    assert (control is not None) is control_retained
    assert harness.provider.termination_calls == []


def test_landing_durability_failure_preserves_the_original_error():
    harness = _Harness(owner=True)

    def ambiguous_landing(*_args, **_kwargs):
        raise RuntimeError("original landing error")

    def fail_durability(*_args):
        raise LookupError("durability unavailable")

    harness.repository.land_provider_creation = ambiguous_landing
    harness.coordinator.creation._landing_durability = fail_durability

    with pytest.raises(RuntimeError, match="original landing error"):
        asyncio.run(harness.coordinator.replenish_pool())

    assert harness.transport.blank_control("sb-created-1") is None
    assert harness.provider.termination_calls == []


def test_repository_classifies_exact_landing_durability():
    harness = _Harness(owner=True)
    with harness.sessions() as db, db.begin():
        reservation = harness.repository.reserve_starting_blank(
            db,
            now=harness.clock.utcnow(),
        )
    assert isinstance(reservation, PoolStartReservation)
    with harness.sessions() as db, db.begin():
        assert (
            harness.repository.land_provider_creation(
                db,
                reservation,
                "sb-exact",
                now=harness.clock.utcnow(),
            )
            is PoolLandingOutcome.LANDED
        )
    with harness.sessions() as db:
        assert (
            harness.repository.provider_landing_durability(
                db,
                reservation,
                "sb-exact",
            )
            is PoolLandingDurability.BLANK_READY
        )
    with harness.sessions() as db, db.begin():
        row = db.get(ChatSandboxPool, reservation.pool_id)
        row.state = "claimed"
    with harness.sessions() as db:
        assert (
            harness.repository.provider_landing_durability(
                db,
                reservation,
                "sb-exact",
            )
            is PoolLandingDurability.OWNERSHIP_MOVED
        )
        assert (
            harness.repository.provider_landing_durability(
                db,
                reservation,
                "sb-different",
            )
            is PoolLandingDurability.NOT_DURABLE
        )


@pytest.mark.parametrize("phase", ["create", "open", "ping", "landing"])
def test_start_cancellation_rethrows_the_exact_error_after_compensation(phase):
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    cancellation = asyncio.CancelledError(f"cancel during {phase}")

    async def cancel_create(*_args):
        raise cancellation

    if phase == "create":
        harness.provider.create_hook = cancel_create
    elif phase == "open":
        harness.transport.open_hook = cancel_create
    elif phase == "ping":
        harness.transport.ping_hook = cancel_create
    else:
        harness.repository.land_provider_creation = lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(cancellation)

    async def run():
        try:
            await harness.coordinator.replenish_pool()
        except asyncio.CancelledError as caught:
            return caught
        raise AssertionError("cancellation was swallowed")

    assert asyncio.run(run()) is cancellation

    expected_sandbox_id = None if phase == "create" else "sb-created-1"
    assert harness.provider.termination_calls == (
        [] if phase == "create" else ["sb-created-1"]
    )
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert pool.failure_code == "sandbox_start_failed"
    assert interval.modal_sandbox_id == expected_sandbox_id
    assert interval.terminal_reason == "sandbox_start_failed"
    assert interval.reconciliation_state == (
        "creation_failed" if phase == "create" else "confirmed"
    )


def test_cancelled_ambiguous_landing_fences_successor_owned_provider():
    harness = _Harness(owner=True)
    cancellation = asyncio.CancelledError("ambiguous successor landing")

    def cancel_landing(*_args, **_kwargs):
        raise cancellation

    harness.repository.land_provider_creation = cancel_landing
    harness.coordinator.creation._landing_durability = lambda *_args: (
        PoolLandingDurability.OWNERSHIP_MOVED
    )

    async def run():
        try:
            await harness.coordinator.replenish_pool()
        except asyncio.CancelledError as caught:
            return caught
        raise AssertionError("cancellation was swallowed")

    assert asyncio.run(run()) is cancellation
    assert harness.transport.blank_control("sb-created-1") is None
    assert harness.provider.termination_calls == []


def test_cancelled_landing_durability_failure_preserves_unknown_provider(caplog):
    harness = _Harness(owner=True)
    cancellation = asyncio.CancelledError("ambiguous unknown landing")

    def cancel_landing(*_args, **_kwargs):
        raise cancellation

    def fail_durability(*_args):
        raise LookupError("durability unavailable")

    harness.repository.land_provider_creation = cancel_landing
    harness.coordinator.creation._landing_durability = fail_durability

    async def run():
        try:
            await harness.coordinator.replenish_pool()
        except asyncio.CancelledError as caught:
            return caught
        raise AssertionError("cancellation was swallowed")

    assert asyncio.run(run()) is cancellation
    assert harness.transport.blank_control("sb-created-1") is None
    assert harness.provider.termination_calls == []
    assert (
        "cancelled blank landing durability check failed error=LookupError"
        in caplog.text
    )


def test_external_cancellation_waits_for_shielded_control_cleanup():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )

    async def run():
        ping_started = asyncio.Event()
        termination_started = asyncio.Event()
        release_termination = asyncio.Event()

        async def block_ping(*_args):
            ping_started.set()
            await asyncio.Event().wait()

        async def block_termination(_call_number, _sandbox_id):
            termination_started.set()
            await release_termination.wait()

        harness.transport.ping_hook = block_ping
        harness.provider.termination_hook = block_termination
        task = asyncio.create_task(harness.coordinator.replenish_pool())
        await ping_started.wait()
        task.cancel("stop refill")
        await termination_started.wait()
        assert not task.done()
        release_termination.set()
        with pytest.raises(asyncio.CancelledError, match="stop refill"):
            await task

    asyncio.run(run())

    assert harness.provider.termination_calls == ["sb-created-1"]
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "failed"
    assert interval.terminal_reason == "sandbox_start_failed"


def test_cancellation_after_committed_landing_keeps_the_durable_provider():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    original_land = harness.repository.land_provider_creation

    def land_then_cancel(db, reservation, sandbox_id, *, now, **metrics):
        outcome = original_land(db, reservation, sandbox_id, now=now, **metrics)
        task = asyncio.current_task()
        assert task is not None
        asyncio.get_running_loop().call_soon(task.cancel, "after landing commit")
        return outcome

    harness.repository.land_provider_creation = land_then_cancel

    with pytest.raises(asyncio.CancelledError, match="after landing commit"):
        asyncio.run(harness.coordinator.replenish_pool())

    assert harness.provider.termination_calls == []
    assert harness.transport.blank_control("sb-created-1") is not None
    with harness.sessions() as db:
        pool = db.execute(select(ChatSandboxPool)).scalar_one()
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert pool.state == "blank_ready"
    assert pool.modal_sandbox_id == "sb-created-1"
    assert interval.modal_sandbox_id == "sb-created-1"
    assert interval.provider_created_at is not None
    assert interval.terminal_at is None


def test_cleanup_failure_does_not_mask_the_landing_database_error(caplog):
    harness = _Harness(owner=True)
    landing_error = RuntimeError("landing database failed")

    def fail_landing(*_args, **_kwargs):
        raise landing_error

    async def fail_cleanup(*_args, **_kwargs):
        raise LookupError("cleanup failed")

    harness.repository.land_provider_creation = fail_landing
    harness.coordinator.creation._landing_durability = lambda *_args: (
        PoolLandingDurability.NOT_DURABLE
    )
    harness.coordinator.creation._compensate_start = fail_cleanup

    with pytest.raises(RuntimeError) as raised:
        asyncio.run(harness.coordinator.replenish_pool())

    assert raised.value is landing_error
    assert "blank landing cleanup failed error=LookupError" in caplog.text


def test_start_compensation_claim_is_fenced_from_a_successor():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
    )
    with harness.sessions() as db, db.begin():
        spend = ChatSandboxSpendService(db, harness.settings)
        reservation = harness.repository.reserve_starting_blank(
            db,
            now=harness.clock.utcnow(),
            interval_reserver=lambda generation: spend.reserve_interval(
                origin="blank_pool",
                worker_generation=generation,
                now=harness.clock.utcnow(),
                capacity_locked=True,
            ),
        )
    assert isinstance(reservation, PoolStartReservation)
    with harness.sessions() as db, db.begin():
        successor = db.get(ChatSandboxPool, reservation.pool_id)
        successor.claim_token_hash = "successor-token"

    sandbox = SimpleNamespace(object_id="sb-created-by-reservation")
    asyncio.run(
        harness.coordinator.creation._compensate_start(
            reservation,
            sandbox=sandbox,
            control=None,
            failure_code="sandbox_start_failed",
        )
    )

    assert harness.provider.termination_calls == [sandbox.object_id]
    with harness.sessions() as db:
        successor = db.get(ChatSandboxPool, reservation.pool_id)
        interval = db.get(ChatSandboxComputeInterval, reservation.interval_id)
    assert successor.state == "starting"
    assert successor.claim_token_hash == "successor-token"
    assert successor.failure_code is None
    assert interval.modal_sandbox_id == sandbox.object_id
    assert interval.terminal_reason == "sandbox_start_failed"


def test_refill_lock_order_is_maintenance_then_capacity_then_spend():
    order: list[str] = []

    def maintenance_locker(_db):
        order.append("maintenance")
        return True

    def capacity_locker(_db, *, wait=True):
        order.append(f"capacity:{wait}")
        return True

    class Spend:
        def reserve_interval(self, **_kwargs):
            order.append("spend")
            return None

    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        maintenance_locker=maintenance_locker,
        capacity_locker=capacity_locker,
        spend_factory=lambda _db: Spend(),
    )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 1
    assert order[:3] == ["maintenance", "capacity:False", "spend"]


@pytest.mark.parametrize(
    ("eviction_outcome", "expected_reservation_attempts"),
    [
        (LeaseEvictionOutcome.NOT_IDLE, 1),
        (LeaseEvictionOutcome.EVICTED, 2),
        (LeaseEvictionOutcome.OWNERSHIP_CHANGED, 2),
    ],
)
def test_eviction_outcome_controls_the_single_refill_retry(
    eviction_outcome,
    expected_reservation_attempts,
):
    session_id = uuid.uuid4()
    eviction_calls: list[uuid.UUID] = []

    async def leave_capacity_full(candidate_session_id):
        eviction_calls.append(candidate_session_id)
        return eviction_outcome

    harness = _Harness(
        owner=True,
        settings=_settings(chat_sandbox_total_live_cap=1),
        lease_eviction=_LeaseEviction(leave_capacity_full),
    )
    reserve_attempts = 0
    reserve_starting_blank = harness.repository.reserve_starting_blank

    def counted_reservation(*args, **kwargs):
        nonlocal reserve_attempts
        reserve_attempts += 1
        return reserve_starting_blank(*args, **kwargs)

    harness.repository.reserve_starting_blank = counted_reservation
    with harness.sessions() as db, db.begin():
        db.add_all(
            [
                _session(session_id),
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id="sb-still-idle",
                    app_release_id=harness.settings.release_id,
                    image_version=harness.settings.chat_modal_image_version,
                    worker_contract_version=(
                        harness.settings.chat_worker_contract_version
                    ),
                    worker_generation="generation-still-idle",
                    state="idle",
                    last_activity_at=harness.clock.utcnow() - timedelta(hours=1),
                    workspace_dirty=False,
                    created_at=harness.clock.utcnow() - timedelta(hours=1),
                    updated_at=harness.clock.utcnow() - timedelta(hours=1),
                ),
            ]
        )

    assert asyncio.run(harness.coordinator.replenish_pool()) == 0
    assert eviction_calls == [session_id]
    assert reserve_attempts == expected_reservation_attempts
    assert harness.provider.create_calls == []


def test_spawn_replenishment_keeps_a_bounded_strong_task_set():
    harness = _Harness(
        owner=True,
        settings=_settings(chat_blank_pool_refill_concurrency=2),
    )

    async def run():
        two_started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def block_replenishment():
            nonlocal calls
            calls += 1
            if calls == 2:
                two_started.set()
            await release.wait()
            return PoolReplenishmentOutcome.READY

        harness.coordinator.creation.replenish = block_replenishment
        for _ in range(8):
            harness.coordinator.spawn_replenishment()
        await two_started.wait()
        tasks = tuple(harness.coordinator.creation._tasks)
        assert len(tasks) == 2
        assert all(not task.done() for task in tasks)
        release.set()
        assert await asyncio.gather(*tasks) == [
            PoolReplenishmentOutcome.READY,
            PoolReplenishmentOutcome.READY,
        ]
        await asyncio.sleep(0)
        return calls

    assert asyncio.run(run()) == 2
    assert harness.coordinator.creation._tasks == set()


def test_spawn_replenishment_retrieves_and_logs_background_errors(caplog):
    harness = _Harness(owner=True)

    async def run():
        loop_errors = []
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: loop_errors.append(context)
        )

        async def fail_replenishment():
            raise RuntimeError("background failed")

        harness.coordinator.creation.replenish = fail_replenishment
        harness.coordinator.spawn_replenishment()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return loop_errors

    assert asyncio.run(run()) == []
    assert harness.coordinator.creation._tasks == set()
    assert "chat blank pool replenishment failed error=RuntimeError" in caplog.text


def test_spawn_replenishment_discards_cancelled_tasks_without_warning(caplog):
    harness = _Harness(owner=True)

    async def run():
        started = asyncio.Event()

        async def block_replenishment():
            started.set()
            await asyncio.Event().wait()

        harness.coordinator.creation.replenish = block_replenishment
        harness.coordinator.spawn_replenishment()
        await started.wait()
        task = next(iter(harness.coordinator.creation._tasks))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    asyncio.run(run())

    assert harness.coordinator.creation._tasks == set()
    assert "chat blank pool replenishment failed" not in caplog.text


def test_maintenance_replaces_compatible_blank_from_previous_release():
    harness = _Harness(
        settings=_settings(chat_blank_pool_rotate_before_seconds=60),
        owner=True,
    )
    row = _pool(harness, release_id="release-previous")
    row.expires_at = harness.clock.utcnow() + timedelta(hours=2)
    with harness.sessions() as db, db.begin():
        db.add(row)

    result = asyncio.run(harness.coordinator.maintain_pool())

    assert result == PoolMaintenanceResult(drained=1, replenished=1)
    assert harness.provider.termination_calls == [row.modal_sandbox_id]
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, row.id)
        replacement = db.execute(
            select(ChatSandboxPool).where(ChatSandboxPool.id != row.id)
        ).scalar_one()
    assert persisted.state == "terminated"
    assert persisted.app_release_id == "release-previous"
    assert replacement.state == "blank_ready"
    assert replacement.app_release_id == harness.settings.release_id


def test_disabled_maintenance_drains_pool_without_touching_assigned_lease():
    harness = _Harness(settings=_settings(chat_blank_pool_enabled=False), owner=True)
    row = _pool(harness)
    session_id = uuid.uuid4()
    with harness.sessions() as db, db.begin():
        db.add_all(
            [
                row,
                _session(session_id),
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id="sb-assigned",
                    app_release_id=harness.settings.release_id,
                    image_version=harness.settings.chat_modal_image_version,
                    worker_contract_version=(
                        harness.settings.chat_worker_contract_version
                    ),
                    worker_generation="generation-assigned",
                    state="idle",
                ),
            ]
        )

    result = asyncio.run(harness.coordinator.maintain_pool())

    assert result.drained == 1
    assert harness.provider.termination_calls == [row.modal_sandbox_id]
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, row.id)
        assigned = db.get(ChatSandboxLease, session_id)
    assert persisted.state == "terminated"
    assert assigned.state == "idle"
    assert assigned.modal_sandbox_id == "sb-assigned"


def test_maintenance_terminates_settled_claimed_pool_orphan():
    class Spend:
        def terminate(self, *_args, **_kwargs):
            raise AssertionError("settled spend interval must not be rewritten")

    harness = _Harness(
        settings=_settings(
            chat_blank_pool_enabled=False,
            chat_sandbox_spend_enforcement_enabled=True,
        ),
        owner=True,
        spend_factory=lambda _db: Spend(),
    )
    row = _pool(harness, state="claimed", release_id="release-previous")
    row.blank_billable_seconds = 123
    row.estimated_blank_cost_usd = 1.25
    interval = _interval(harness, row)
    interval.claimed_at = harness.clock.utcnow() - timedelta(minutes=1)
    interval.terminal_at = harness.clock.utcnow() - timedelta(seconds=30)
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])

    result = asyncio.run(harness.coordinator.maintain_pool())

    assert result.drained == 1
    assert harness.provider.termination_calls == [row.modal_sandbox_id]
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, row.id)
    assert persisted.state == "terminated"
    assert persisted.blank_billable_seconds == 123
    assert float(persisted.estimated_blank_cost_usd) == 1.25


def test_maintenance_commits_claim_before_provider_io():
    events: list[str] = []

    def capacity_locker(_db, *, wait=True):
        assert wait is True
        events.append("capacity")
        return True

    def maintenance_locker(_db):
        events.append("maintenance")
        return True

    harness = _Harness(
        settings=_settings(chat_blank_pool_enabled=False),
        capacity_locker=capacity_locker,
        maintenance_locker=maintenance_locker,
        owner=True,
    )
    row = _pool(harness)
    with harness.sessions() as db, db.begin():
        db.add(row)
    original_claim = harness.repository.claim_termination

    def record_claim(*args, **kwargs):
        events.append("claim")
        return original_claim(*args, **kwargs)

    harness.repository.claim_termination = record_claim

    async def terminate(sandbox_id, sandbox=None):
        harness.probe.outside_transaction("provider.terminate")
        events.append("provider")
        with harness.sessions() as db:
            persisted = db.get(ChatSandboxPool, row.id)
        assert persisted.state == "draining"
        assert persisted.modal_sandbox_id == sandbox_id
        assert persisted.claim_token_hash is not None
        return True

    harness.provider.terminate = terminate

    result = asyncio.run(harness.coordinator.maintain_pool())

    assert result.drained == 1
    assert events[:4] == ["maintenance", "capacity", "claim", "provider"]


def test_termination_claim_horizon_covers_provider_completion_window():
    harness = _Harness(
        settings=_settings(
            chat_worker_ready_timeout_seconds=5,
            chat_sandbox_termination_grace_seconds=120,
        )
    )

    assert harness.coordinator.termination_claim_timeout_seconds == 140
    assert harness.coordinator.termination_claim_timeout_seconds > (
        harness.coordinator.ready_timeout_seconds
        + harness.settings.chat_sandbox_termination_grace_seconds
    )


@pytest.mark.parametrize("successor_state", ["draining", "claimed"])
def test_health_result_cannot_mutate_a_successor(successor_state):
    harness = _Harness(owner=True)
    row = _pool(harness)
    checked_at = harness.clock.utcnow() - timedelta(minutes=1)
    row.last_health_checked_at = checked_at
    row.blank_billable_seconds = 123
    row.estimated_blank_cost_usd = 1.25
    candidate = PoolHealthCandidate(
        pool_id=row.id,
        sandbox_id=row.modal_sandbox_id,
        worker_generation=row.worker_generation,
        claim_generation=row.claim_generation,
        token_hash=row.claim_token_hash,
    )
    with harness.sessions() as db, db.begin():
        db.add(row)
    successor_at = harness.clock.utcnow() + timedelta(seconds=10)

    async def race_health(sandbox_id, worker_generation):
        assert (sandbox_id, worker_generation) == (
            row.modal_sandbox_id,
            row.worker_generation,
        )
        with harness.sessions() as db, db.begin():
            successor = db.get(ChatSandboxPool, row.id)
            successor.state = successor_state
            successor.claim_token_hash = "successor-token"
            successor.updated_at = successor_at
        return SimpleNamespace(object_id=sandbox_id)

    harness.coordinator.maintenance.pool_sandbox_health = race_health

    assert (
        asyncio.run(harness.coordinator.maintenance._refresh_pool_health((candidate,)))
        == 0
    )
    with harness.sessions() as db:
        successor = db.get(ChatSandboxPool, row.id)
    assert successor.state == successor_state
    assert successor.claim_token_hash == "successor-token"
    assert successor.last_health_checked_at == checked_at.replace(tzinfo=None)
    assert successor.updated_at == successor_at.replace(tzinfo=None)
    assert successor.blank_billable_seconds == 123
    assert float(successor.estimated_blank_cost_usd) == 1.25


def test_concurrent_maintenance_serializes_and_rechecks_owner():
    harness = _Harness(owner=True)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def controlled_maintenance():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return PoolMaintenanceResult(drained=1)

    harness.coordinator.maintenance._maintain_pool = controlled_maintenance

    async def run():
        first = asyncio.create_task(harness.coordinator.maintain_pool())
        await started.wait()
        second = asyncio.create_task(harness.coordinator.maintain_pool())
        await asyncio.sleep(0)
        harness.owner = False
        release.set()
        return await asyncio.gather(first, second)

    first, second = asyncio.run(run())

    assert first == PoolMaintenanceResult(drained=1)
    assert second == PoolMaintenanceResult()
    assert calls == 1


def test_orphan_scan_is_environment_filtered_outside_transactions_and_capped():
    harness = _Harness(owner=True)
    harness.provider.listed_sandboxes = [
        SimpleNamespace(object_id=f"sb-listed-{index}")
        for index in range(POOL_MAINTENANCE_BATCH_SIZE + 5)
    ]
    for sandbox in harness.provider.listed_sandboxes:
        harness.provider.sandbox_tags[sandbox.object_id] = {
            "environment": "another-environment"
        }

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    assert harness.provider.list_tags_calls == [
        {
            "service": "pwc-chat",
            "environment": harness.settings.environment,
            "pool": "blank",
        }
    ]
    tag_calls = [
        call for call in harness.probe.provider_calls if call == "provider.tags"
    ]
    assert len(tag_calls) == POOL_MAINTENANCE_BATCH_SIZE


def test_unrelated_fresh_start_does_not_globally_shield_an_orphan():
    harness = _Harness(owner=True)
    fresh = _pool(harness, state="starting", sandbox_id=None)
    fresh.updated_at = harness.clock.utcnow()
    with harness.sessions() as db, db.begin():
        db.add(fresh)
    orphan = SimpleNamespace(object_id="sb-unrelated-orphan")
    harness.provider.listed_sandboxes = [orphan]
    harness.provider.sandbox_tags[orphan.object_id] = _orphan_tags(harness)

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    assert harness.provider.termination_calls == [orphan.object_id]
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, fresh.id)
    assert persisted.state == "starting"
    assert persisted.modal_sandbox_id is None


def test_exact_fresh_start_is_protected_but_stale_start_is_reconciled():
    harness = _Harness(owner=True)
    fresh = _pool(harness, state="starting", sandbox_id=None)
    stale = _pool(harness, state="starting", sandbox_id=None)
    fresh.updated_at = harness.clock.utcnow()
    stale.updated_at = harness.clock.utcnow() - timedelta(minutes=2)
    fresh_provider = SimpleNamespace(object_id="sb-fresh-start")
    stale_provider = SimpleNamespace(object_id="sb-stale-start")
    with harness.sessions() as db, db.begin():
        db.add_all([fresh, stale])
    harness.provider.listed_sandboxes = [fresh_provider, stale_provider]
    harness.provider.sandbox_tags[fresh_provider.object_id] = _pool_tags(harness, fresh)
    harness.provider.sandbox_tags[stale_provider.object_id] = _pool_tags(harness, stale)

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    assert harness.provider.termination_calls == [stale_provider.object_id]
    with harness.sessions() as db:
        fresh_row = db.get(ChatSandboxPool, fresh.id)
        stale_row = db.get(ChatSandboxPool, stale.id)
    assert fresh_row.state == "starting"
    assert fresh_row.modal_sandbox_id is None
    assert stale_row.state == "failed"
    assert stale_row.failure_code == "sandbox_start_failed"
    assert stale_row.modal_sandbox_id == stale_provider.object_id


def test_mismatched_fresh_start_tags_do_not_protect_provider():
    harness = _Harness(owner=True)
    fresh = _pool(harness, state="starting", sandbox_id=None)
    fresh.updated_at = harness.clock.utcnow()
    sandbox = SimpleNamespace(object_id="sb-mismatched-start")
    with harness.sessions() as db, db.begin():
        db.add(fresh)
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = {
        **_pool_tags(harness, fresh),
        "release": "wrong-release",
    }

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    assert harness.provider.termination_calls == [sandbox.object_id]
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, fresh.id)
    assert persisted.state == "starting"
    assert persisted.modal_sandbox_id is None


def test_provider_landing_during_scan_is_seen_by_fresh_item_inspection():
    harness = _Harness(owner=True)
    sandbox = SimpleNamespace(object_id="sb-landed-during-scan")
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _orphan_tags(harness)

    async def land_during_scan(index, listed):
        assert index == 0
        row = _pool(harness, sandbox_id=listed.object_id)
        with harness.sessions() as db, db.begin():
            db.add(row)

    harness.provider.iter_hook = land_during_scan

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    assert harness.provider.termination_calls == []


def test_tag_and_database_inspection_failures_are_isolated(monkeypatch):
    harness = _Harness(owner=True)
    tag_failure = SimpleNamespace(object_id="sb-tag-failure")
    db_failure = SimpleNamespace(object_id="sb-db-failure")
    healthy_orphan = SimpleNamespace(object_id="sb-next-orphan")
    harness.provider.listed_sandboxes = [tag_failure, db_failure, healthy_orphan]
    harness.provider.tag_errors[tag_failure.object_id] = RuntimeError("tags")
    harness.provider.sandbox_tags[db_failure.object_id] = _orphan_tags(harness)
    harness.provider.sandbox_tags[healthy_orphan.object_id] = _orphan_tags(harness)
    original_inspect = harness.repository.classify_and_claim_provider_sandbox

    def inspect(db, sandbox_id, *args, **kwargs):
        if sandbox_id == db_failure.object_id:
            raise RuntimeError("database inspection")
        return original_inspect(db, sandbox_id, *args, **kwargs)

    monkeypatch.setattr(
        harness.repository,
        "classify_and_claim_provider_sandbox",
        inspect,
    )

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    assert harness.provider.termination_calls == [healthy_orphan.object_id]


def test_orphan_termination_failures_record_uncertainty_and_continue():
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    false_result = SimpleNamespace(object_id="sb-false")
    raised = SimpleNamespace(object_id="sb-raised")
    confirmed = SimpleNamespace(object_id="sb-confirmed")
    harness.provider.listed_sandboxes = [false_result, raised, confirmed]
    for sandbox in harness.provider.listed_sandboxes:
        harness.provider.sandbox_tags[sandbox.object_id] = _orphan_tags(harness)

    async def terminate(sandbox_id, _sandbox=None):
        harness.probe.outside_transaction("provider.terminate")
        if sandbox_id == raised.object_id:
            raise RuntimeError("provider unavailable")
        return sandbox_id == confirmed.object_id

    harness.provider.terminate = terminate

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    with harness.sessions() as db:
        intervals = {
            row.modal_sandbox_id: row
            for row in db.scalars(select(ChatSandboxComputeInterval))
        }
    assert intervals[false_result.object_id].reconciliation_state == (
        "termination_uncertain"
    )
    assert intervals[false_result.object_id].terminal_at is None
    assert intervals[raised.object_id].reconciliation_state == "termination_uncertain"
    assert intervals[raised.object_id].terminal_at is None
    assert intervals[confirmed.object_id].reconciliation_state == "confirmed"
    assert intervals[confirmed.object_id].terminal_at is not None


def test_aborted_interval_is_reactivated_when_provider_is_discovered_unconfirmed():
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state="terminated", sandbox_id=None)
    interval = _interval(harness, row, reserved_microusd=0)
    interval.provider_created_at = None
    interval.terminal_at = harness.clock.utcnow() - timedelta(minutes=1)
    interval.terminal_reason = "pool_owner_terminated"
    interval.reconciliation_state = "creation_failed"
    sandbox = SimpleNamespace(object_id="sb-recovered-after-abort")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)
    harness.provider.termination_confirmed = False

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    with harness.sessions() as db:
        recovered = db.get(ChatSandboxComputeInterval, interval.id)
    assert recovered.modal_sandbox_id == sandbox.object_id
    assert recovered.provider_created_at is not None
    assert recovered.terminal_at is None
    assert recovered.reserved_microusd > 0
    assert recovered.reconciliation_state == "termination_uncertain"


@pytest.mark.parametrize("confirmed", [True, False])
def test_stale_start_spend_preserves_claim_failure_reason(confirmed):
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state="starting", sandbox_id=None)
    row.updated_at = harness.clock.utcnow() - timedelta(minutes=2)
    interval = _interval(harness, row)
    interval.provider_created_at = None
    sandbox = SimpleNamespace(object_id=f"sb-stale-confirmed-{confirmed}")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)
    harness.provider.termination_confirmed = confirmed

    result = asyncio.run(harness.coordinator.reconcile_pool_orphans())

    assert result == int(confirmed)
    with harness.sessions() as db:
        failed = db.get(ChatSandboxPool, row.id)
        settled = db.get(ChatSandboxComputeInterval, interval.id)
    assert failed.state == "failed"
    assert failed.failure_code == (
        "sandbox_start_failed" if confirmed else "termination_uncertain"
    )
    assert settled.terminal_reason == "sandbox_start_failed"
    if confirmed:
        assert settled.terminal_at is not None
        assert settled.reserved_microusd == 0
        assert settled.reconciliation_state == "confirmed"
    else:
        assert settled.terminal_at is None
        assert settled.reserved_microusd > 0
        assert settled.reconciliation_state == "termination_uncertain"


def test_orphan_cancellation_propagates_after_interval_is_linked():
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state="terminated", sandbox_id=None)
    interval = _interval(harness, row)
    sandbox = SimpleNamespace(object_id="sb-cancelled-orphan")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)
    termination_started = asyncio.Event()

    async def terminate(sandbox_id, _sandbox=None):
        harness.probe.outside_transaction("provider.terminate")
        assert sandbox_id == sandbox.object_id
        termination_started.set()
        await asyncio.Event().wait()

    harness.provider.terminate = terminate

    async def run():
        task = asyncio.create_task(harness.coordinator.reconcile_pool_orphans())
        await termination_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    with harness.sessions() as db:
        persisted = db.get(ChatSandboxComputeInterval, interval.id)
    assert persisted.modal_sandbox_id == sandbox.object_id
    assert persisted.provider_created_at is not None
    assert persisted.terminal_at is None


def test_orphan_provider_work_is_bounded_by_termination_concurrency():
    harness = _Harness(
        settings=_settings(
            chat_blank_pool_max=3,
            chat_blank_pool_refill_concurrency=2,
        ),
        owner=True,
    )
    harness.provider.listed_sandboxes = [
        SimpleNamespace(object_id=f"sb-orphan-{index}") for index in range(5)
    ]
    for sandbox in harness.provider.listed_sandboxes:
        harness.provider.sandbox_tags[sandbox.object_id] = _orphan_tags(harness)
    active = 0
    maximum_active = 0

    async def termination_hook(_call_number, _sandbox_id):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1

    harness.provider.termination_hook = termination_hook

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 5
    assert maximum_active == harness.coordinator.termination_concurrency == 2


def test_owner_loss_after_tag_fetch_skips_inspection_and_termination(monkeypatch):
    harness = _Harness(owner=True)
    sandbox = SimpleNamespace(object_id="sb-owner-lost-tags")
    harness.provider.listed_sandboxes = [sandbox]
    tags_started = asyncio.Event()
    release_tags = asyncio.Event()

    async def delayed_tags(candidate):
        harness.probe.outside_transaction("provider.tags")
        assert candidate is sandbox
        tags_started.set()
        await release_tags.wait()
        return _orphan_tags(harness)

    async def run():
        monkeypatch.setattr(harness.provider, "get_tags", delayed_tags)
        monkeypatch.setattr(
            harness.repository,
            "classify_and_claim_provider_sandbox",
            lambda *_args, **_kwargs: pytest.fail(
                "owner loss must skip database inspection"
            ),
        )
        task = asyncio.create_task(harness.coordinator.reconcile_pool_orphans())
        await tags_started.wait()
        harness.owner = False
        release_tags.set()
        return await task

    assert asyncio.run(run()) == 0
    assert harness.provider.termination_calls == []


def test_owner_loss_after_health_probe_skips_database_mutation():
    harness = _Harness(owner=True)
    row = _pool(harness)
    candidate = PoolHealthCandidate(
        pool_id=row.id,
        sandbox_id=row.modal_sandbox_id,
        worker_generation=row.worker_generation,
        claim_generation=row.claim_generation,
        token_hash=row.claim_token_hash,
    )
    with harness.sessions() as db, db.begin():
        db.add(row)
    health_started = asyncio.Event()
    release_health = asyncio.Event()

    async def delayed_health(_sandbox_id, _worker_generation):
        health_started.set()
        await release_health.wait()
        return None

    async def run():
        harness.coordinator.maintenance.pool_sandbox_health = delayed_health
        task = asyncio.create_task(
            harness.coordinator.maintenance._refresh_pool_health((candidate,))
        )
        await health_started.wait()
        harness.owner = False
        release_health.set()
        return await task

    assert asyncio.run(run()) == 0
    assert harness.provider.termination_calls == []
    with harness.sessions() as db:
        persisted = db.get(ChatSandboxPool, row.id)
    assert persisted.state == "blank_ready"
    assert persisted.claim_token_hash is None
    assert persisted.health_check_token_hash is not None


def test_claimless_orphan_spend_settlement_reacquires_capacity_lock():
    capacity_calls: list[bool] = []

    def capacity_locker(_db, *, wait=True):
        capacity_calls.append(wait)
        return True

    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        capacity_locker=capacity_locker,
        owner=True,
    )
    sandbox = SimpleNamespace(object_id="sb-claimless-orphan")
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _orphan_tags(harness)

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 1
    assert capacity_calls == [True, True]
    with harness.sessions() as db:
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == sandbox.object_id
            )
        ).scalar_one()
    assert interval.reconciliation_state == "confirmed"


@pytest.mark.parametrize("pool_state", ["starting", "draining"])
def test_stale_provider_claim_finish_is_fenced_from_successor(pool_state):
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state=pool_state, sandbox_id=None)
    row.updated_at = harness.clock.utcnow() - timedelta(minutes=2)
    interval = _interval(harness, row)
    sandbox = SimpleNamespace(object_id=f"sb-stale-{pool_state}")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)
    successor_at = harness.clock.utcnow() + timedelta(seconds=1)

    async def replace_owner(_call_number, sandbox_id):
        with harness.sessions() as db, db.begin():
            successor = db.get(ChatSandboxPool, row.id)
            assert successor.state == "draining"
            assert successor.modal_sandbox_id == sandbox_id
            successor.state = "blank_ready"
            successor.claim_token_hash = "successor-token"
            successor.updated_at = successor_at

    harness.provider.termination_hook = replace_owner

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    with harness.sessions() as db:
        successor = db.get(ChatSandboxPool, row.id)
        linked = db.get(ChatSandboxComputeInterval, interval.id)
    assert successor.state == "blank_ready"
    assert successor.claim_token_hash == "successor-token"
    assert successor.updated_at == successor_at.replace(tzinfo=None)
    assert linked.modal_sandbox_id == sandbox.object_id
    assert linked.terminal_at is None


def test_claimed_orphan_finish_failure_leaves_durable_reconciliation(monkeypatch):
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state="starting", sandbox_id=None)
    row.updated_at = harness.clock.utcnow() - timedelta(minutes=2)
    interval = _interval(harness, row)
    sandbox = SimpleNamespace(object_id="sb-finish-failure")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)

    def fail_finish(*_args, **_kwargs):
        raise RuntimeError("finish unavailable")

    monkeypatch.setattr(harness.repository, "finish_termination", fail_finish)

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    assert harness.provider.termination_calls == [sandbox.object_id]
    with harness.sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        linked = db.get(ChatSandboxComputeInterval, interval.id)
    assert claimed.state == "draining"
    assert claimed.claim_token_hash is not None
    assert linked.modal_sandbox_id == sandbox.object_id
    assert linked.terminal_at is None


def test_active_pool_and_assigned_lease_protect_provider_sandboxes():
    harness = _Harness(owner=True)
    pool = _pool(harness, sandbox_id="sb-active-pool")
    session_id = uuid.uuid4()
    with harness.sessions() as db, db.begin():
        db.add_all(
            [
                pool,
                _session(session_id),
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id="sb-active-lease",
                    app_release_id=harness.settings.release_id,
                    image_version=harness.settings.chat_modal_image_version,
                    worker_contract_version=(
                        harness.settings.chat_worker_contract_version
                    ),
                    worker_generation="generation-assigned",
                    state="busy",
                ),
            ]
        )
    pool_provider = SimpleNamespace(object_id="sb-active-pool")
    lease_provider = SimpleNamespace(object_id="sb-active-lease")
    harness.provider.listed_sandboxes = [pool_provider, lease_provider]
    for sandbox in harness.provider.listed_sandboxes:
        harness.provider.sandbox_tags[sandbox.object_id] = {
            "environment": harness.settings.environment,
        }

    assert asyncio.run(harness.coordinator.reconcile_pool_orphans()) == 0
    assert harness.provider.termination_calls == []


def test_claimed_orphan_cancellation_keeps_exact_claim_reconcilable():
    harness = _Harness(
        settings=_settings(chat_sandbox_spend_enforcement_enabled=True),
        owner=True,
    )
    row = _pool(harness, state="starting", sandbox_id=None)
    row.updated_at = harness.clock.utcnow() - timedelta(minutes=2)
    interval = _interval(harness, row)
    sandbox = SimpleNamespace(object_id="sb-cancelled-claimed-orphan")
    with harness.sessions() as db, db.begin():
        db.add_all([row, interval])
    harness.provider.listed_sandboxes = [sandbox]
    harness.provider.sandbox_tags[sandbox.object_id] = _pool_tags(harness, row)
    termination_started = asyncio.Event()

    async def terminate(sandbox_id, _sandbox=None):
        harness.probe.outside_transaction("provider.terminate")
        assert sandbox_id == sandbox.object_id
        termination_started.set()
        await asyncio.Event().wait()

    harness.provider.terminate = terminate

    async def run():
        task = asyncio.create_task(harness.coordinator.reconcile_pool_orphans())
        await termination_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    with harness.sessions() as db:
        claimed = db.get(ChatSandboxPool, row.id)
        linked = db.get(ChatSandboxComputeInterval, interval.id)
    assert claimed.state == "draining"
    assert claimed.modal_sandbox_id == sandbox.object_id
    assert claimed.claim_token_hash is not None
    assert claimed.failure_code == "sandbox_start_failed"
    assert linked.modal_sandbox_id == sandbox.object_id
    assert linked.terminal_at is None
