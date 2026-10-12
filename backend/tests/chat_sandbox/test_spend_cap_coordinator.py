from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnCapability,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    LeaseTerminationOutcome,
)
from backend.services.chat_sandbox_spend_cap_coordinator import (
    MAX_SPEND_CAP_TERMINATION_CONCURRENCY,
    ChatSandboxSpendCapCoordinator,
    SpendCapEnforcementResult,
)
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_worker_transport import RunningWorker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": True,
        "chat_sandbox_admission_enabled": True,
        "chat_workspace_snapshots_enabled": False,
        "chat_sandbox_spend_enforcement_enabled": True,
        "chat_sandbox_budget_attestation": "attested",
        "chat_sandbox_warning_microusd": 75_000_000,
        "chat_sandbox_application_cap_microusd": 100_000_000,
        "chat_sandbox_environment_cap_microusd": 125_000_000,
        "chat_sandbox_workspace_cap_microusd": 250_000_000,
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
        "chat_sandbox_drain_grace_seconds": 30,
        "chat_sandbox_watchdog_seconds": 15,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _TrackedSession(Session):
    pass


class _TransactionProbe:
    def __init__(self) -> None:
        self.active = 0
        self.io_calls: list[str] = []

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
        self.io_calls.append(operation)


def _database(probe: _TransactionProbe):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        ChatSession.__table__,
        ChatSandboxLease.__table__,
        ChatSandboxPool.__table__,
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
        ChatTurnCapability.__table__,
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
        self.now = datetime(2026, 8, 10, 12, tzinfo=UTC)

    def utcnow(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _ClockedSpend(ChatSandboxSpendService):
    """Default every spend timestamp to the harness clock, not the wall clock."""

    def __init__(self, db, settings: Settings, clock: _Clock) -> None:
        super().__init__(db, settings, utcnow=clock.utcnow)
        self.clock = clock

    def status(self, now: datetime | None = None) -> dict:
        return super().status(now or self.clock.now)

    def terminate(self, sandbox_id, reason, *, confirmed, now=None) -> None:
        return super().terminate(
            sandbox_id, reason, confirmed=confirmed, now=now or self.clock.now
        )

    def record_kill_sweep(self, *, complete, now=None):
        return super().record_kill_sweep(complete=complete, now=now or self.clock.now)


class _Provider:
    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.listed: list[object] = []
        self.list_tags_calls: list[dict[str, str]] = []
        self.terminate_results: dict[str, bool | BaseException] = {}
        self.termination_calls: list[str] = []
        self.iterator_error: BaseException | None = None
        self.yielded = 0
        self.max_in_flight = 0
        self.in_flight = 0
        self.release_terminations: asyncio.Event | None = None

    async def iter_sandboxes(self, *, tags):
        self.probe.outside_transaction("provider.list")
        self.list_tags_calls.append(tags)
        for sandbox in self.listed:
            self.yielded += 1
            yield sandbox
        if self.iterator_error is not None:
            raise self.iterator_error

    async def terminate(self, sandbox_id: str, _sandbox=None) -> bool:
        self.probe.outside_transaction("provider.terminate")
        self.termination_calls.append(sandbox_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.release_terminations is not None:
                await self.release_terminations.wait()
            result = self.terminate_results.get(sandbox_id, True)
            if isinstance(result, BaseException):
                raise result
            return result
        finally:
            self.in_flight -= 1


class _Transport:
    def __init__(self, provider: _Provider, probe: _TransactionProbe) -> None:
        self.provider = provider
        self.probe = probe
        self.workers: list[RunningWorker] = []
        self.signaled: list[str] = []
        self.signal_errors: set[str] = set()

    def running_workers(self) -> tuple[RunningWorker, ...]:
        self.probe.outside_transaction("transport.running_workers")
        return tuple(self.workers)

    async def signal_cancel(self, running: RunningWorker) -> None:
        self.probe.outside_transaction("transport.signal_cancel")
        self.signaled.append(running.request_id)
        if running.request_id in self.signal_errors:
            raise RuntimeError("control lost")


class _Lifecycle:
    def __init__(
        self, settings, sessions, provider, transport, probe, capacity_locker
    ) -> None:
        self.settings = settings
        self.session_factory = sessions
        self.repository = SimpleNamespace(settings=settings)
        self.provider = provider
        self.transport = transport
        self.capacity_locker = capacity_locker
        self.probe = probe
        self.calls: list[uuid.UUID] = []
        self.outcomes: dict[uuid.UUID, LeaseTerminationOutcome | BaseException] = {}
        self.max_in_flight = 0
        self.in_flight = 0
        self.release_terminations: asyncio.Event | None = None
        self.before_terminate = None

    async def terminate(self, session_id, *, failure_code=None):
        self.probe.outside_transaction("lifecycle.terminate")
        assert failure_code == "chat_disabled_interrupted"
        self.calls.append(session_id)
        if self.before_terminate is not None:
            self.before_terminate(session_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.release_terminations is not None:
                await self.release_terminations.wait()
            outcome = self.outcomes.get(session_id, LeaseTerminationOutcome.FINISHED)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        finally:
            self.in_flight -= 1


class _PoolCoordinator:
    def __init__(
        self, settings, sessions, provider, transport, probe, capacity_locker
    ) -> None:
        self.settings = settings
        self.session_factory = sessions
        self.repository = SimpleNamespace(
            settings=settings,
            capacity_locker=capacity_locker,
        )
        self.provider = provider
        self.transport = transport
        self.probe = probe
        self.calls: list[tuple[uuid.UUID, str | None]] = []
        self.results: dict[uuid.UUID, bool | BaseException] = {}
        self.max_in_flight = 0
        self.in_flight = 0
        self.release_terminations: asyncio.Event | None = None

    async def terminate_pool_row(self, pool_id, sandbox_id, *, failure_code=None):
        self.probe.outside_transaction("pool.terminate")
        assert failure_code == "chat_disabled_interrupted"
        self.calls.append((pool_id, sandbox_id))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.release_terminations is not None:
                await self.release_terminations.wait()
            result = self.results.get(pool_id, True)
            if isinstance(result, BaseException):
                raise result
            return result
        finally:
            self.in_flight -= 1


class _CapacityLocker:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, db, *, wait=True):
        assert wait is True
        self.calls += 1
        db.info["capacity_locked"] = True
        return True


class _Harness:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or _settings()
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        self.clock = _Clock()
        self.provider = _Provider(self.probe)
        self.transport = _Transport(self.provider, self.probe)
        self.capacity_locker = _CapacityLocker()
        self.lifecycle = _Lifecycle(
            self.settings,
            self.sessions,
            self.provider,
            self.transport,
            self.probe,
            self.capacity_locker,
        )
        self.pool = _PoolCoordinator(
            self.settings,
            self.sessions,
            self.provider,
            self.transport,
            self.probe,
            self.capacity_locker,
        )
        self.sleep_calls: list[float] = []

    def spend(self, db) -> _ClockedSpend:
        return _ClockedSpend(db, self.settings, self.clock)

    async def sleep(self, seconds: float) -> None:
        self.probe.outside_transaction("sleep")
        self.sleep_calls.append(seconds)
        self.clock.advance(seconds)

    def trip(self, *, seconds_ago: float = 0) -> None:
        at = self.clock.now - timedelta(seconds=seconds_ago)
        with self.sessions() as db, db.begin():
            self.spend(db).trip("test_trip", at)

    def add_lease(
        self,
        *,
        state: str,
        sandbox_id: str | None = None,
    ) -> uuid.UUID:
        session_id = uuid.uuid4()
        sandbox_id = sandbox_id or f"sb-{session_id}"
        with self.sessions() as db, db.begin():
            db.add_all(
                [
                    ChatSession(
                        id=session_id,
                        hf_user_id=f"owner-{session_id}",
                        hf_username=f"owner-{session_id}",
                        selected_model="google/gemma-4-31B-it",
                        execution_backend="modal_cli",
                    ),
                    ChatSandboxLease(
                        chat_session_id=session_id,
                        modal_sandbox_id=sandbox_id,
                        app_release_id=self.settings.release_id,
                        image_version=self.settings.chat_modal_image_version,
                        worker_contract_version=(
                            self.settings.chat_worker_contract_version
                        ),
                        worker_generation=f"generation-{session_id}",
                        state=state,
                        last_activity_at=self.clock.now,
                        workspace_dirty=False,
                        created_at=self.clock.now,
                        updated_at=self.clock.now,
                    ),
                ]
            )
        return session_id

    def add_pool(self, *, state: str, sandbox_id: str | None = None) -> uuid.UUID:
        pool_id = uuid.uuid4()
        with self.sessions() as db, db.begin():
            db.add(
                ChatSandboxPool(
                    id=pool_id,
                    modal_sandbox_id=sandbox_id or f"sb-pool-{pool_id}",
                    state=state,
                    image_version=self.settings.chat_modal_image_version,
                    worker_contract_version=self.settings.chat_worker_contract_version,
                    worker_generation=f"pool-generation-{pool_id}",
                    app_release_id=self.settings.release_id,
                    claim_generation=0,
                    created_at=self.clock.now,
                    expires_at=self.clock.now + timedelta(hours=1),
                    updated_at=self.clock.now,
                    cpu_request=self.settings.chat_sandbox_cpu,
                    cpu_limit=self.settings.chat_sandbox_cpu_limit,
                    memory_request_mib=self.settings.chat_sandbox_memory_mib,
                    memory_limit_mib=self.settings.chat_sandbox_memory_limit_mib,
                    billing_month=self.clock.now.date().replace(day=1),
                )
            )
        return pool_id

    def add_interval(
        self,
        sandbox_id: str,
        *,
        environment: str | None = None,
        terminal: bool = False,
    ) -> uuid.UUID:
        interval_id = uuid.uuid4()
        with self.sessions() as db, db.begin():
            db.add(
                ChatSandboxComputeInterval(
                    id=interval_id,
                    modal_sandbox_id=sandbox_id,
                    environment=environment or self.settings.environment,
                    modal_app="pwc-chat-sandbox",
                    app_release_id=self.settings.release_id,
                    image_version=self.settings.chat_modal_image_version,
                    worker_generation=f"interval-generation-{interval_id}",
                    origin="direct",
                    cpu_request_millicores=125,
                    cpu_limit_millicores=1000,
                    memory_request_mib=512,
                    memory_limit_mib=2048,
                    reserved_at=self.clock.now,
                    provider_created_at=self.clock.now,
                    terminal_at=self.clock.now if terminal else None,
                    billing_cycle=self.clock.now.date().replace(day=1),
                    accrued_microusd=0,
                    reserved_microusd=0,
                    reconciliation_state="local",
                    updated_at=self.clock.now,
                )
            )
        return interval_id

    def add_capability(
        self, session_id: uuid.UUID, *, revoked: bool = False
    ) -> uuid.UUID:
        capability_id = uuid.uuid4()
        with self.sessions() as db, db.begin():
            db.add(
                ChatTurnCapability(
                    id=capability_id,
                    token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    chat_session_id=session_id,
                    turn_id=uuid.uuid4(),
                    owner_hash="a" * 64,
                    model="model-a",
                    scopes=["provider"],
                    nonce=uuid.uuid4().hex,
                    expires_at=self.clock.now + timedelta(minutes=5),
                    revoked_at=self.clock.now if revoked else None,
                    provider_requests=0,
                    provider_tokens=0,
                    gateway_calls=0,
                    catalog_search_calls=0,
                    web_search_calls=0,
                    web_search_failed=False,
                )
            )
        return capability_id

    def add_running_worker(self, request_id: str) -> None:
        self.transport.workers.append(
            RunningWorker(
                process=object(),
                request_id=request_id,
                claim=SimpleNamespace(),
            )
        )

    def events(self) -> list[str]:
        with self.sessions() as db:
            return list(
                db.execute(
                    select(ChatSandboxCircuitEvent.event_type).order_by(
                        ChatSandboxCircuitEvent.created_at,
                        ChatSandboxCircuitEvent.id,
                    )
                ).scalars()
            )

    def coordinator(self, **overrides) -> ChatSandboxSpendCapCoordinator:
        values = {
            "session_factory": self.sessions,
            "lifecycle": self.lifecycle,
            "pool": self.pool,
            "transport": self.transport,
            "provider": self.provider,
            "spend_factory": self.spend,
            "utcnow": self.clock.utcnow,
            "sleeper": self.sleep,
        }
        values.update(overrides)
        return ChatSandboxSpendCapCoordinator(self.settings, **values)


def _sandbox(sandbox_id: str):
    return SimpleNamespace(object_id=sandbox_id)


def test_armed_status_keeps_enforcement_as_a_typed_noop_with_status_side_effects():
    harness = _Harness()

    result = asyncio.run(harness.coordinator().enforce())

    assert result == SpendCapEnforcementResult(state="armed")
    assert harness.lifecycle.calls == []
    assert harness.pool.calls == []
    assert harness.transport.signaled == []
    assert harness.provider.list_tags_calls == []
    assert harness.sleep_calls == []
    with harness.sessions() as db:
        states = list(db.execute(select(ChatSandboxBudgetState)).scalars())
    assert len(states) == 1
    assert states[0].circuit_state == "armed"


def test_trip_enforcement_releases_abandoned_pre_provider_reservations():
    harness = _Harness()
    session_id = harness.add_lease(state="failed")
    with harness.sessions() as db, db.begin():
        interval_id = ChatSandboxSpendService(db, harness.settings).reserve_interval(
            origin="direct",
            worker_generation="abandoned-generation",
            chat_session_id=session_id,
            now=harness.clock.now,
        )
    harness.trip(seconds_ago=31)

    result = asyncio.run(harness.coordinator().enforce())

    assert result == SpendCapEnforcementResult(state="tripped")
    with harness.sessions() as db:
        interval = db.get(ChatSandboxComputeInterval, interval_id)
        assert interval.terminal_reason == "lease_owner_terminated"
        assert interval.reserved_microusd == 0
    assert harness.events()[-1] == "kill_sweep_complete"


def test_enforcement_preserves_global_state_scope_order_and_action_counts():
    harness = _Harness()
    immediate_ids = {
        state: harness.add_lease(state=state)
        for state in ("starting", "ready", "idle", "terminating")
    }
    busy_id = harness.add_lease(state="busy", sandbox_id="sb-busy")
    terminal_ids = {
        state: harness.add_lease(state=state) for state in ("terminated", "failed")
    }
    pool_ids = {
        state: harness.add_pool(state=state)
        for state in ("starting", "blank_ready", "draining")
    }
    terminal_pool_ids = {
        state: harness.add_pool(state=state)
        for state in ("claimed", "terminated", "failed")
    }
    harness.lifecycle.outcomes[immediate_ids["ready"]] = (
        LeaseTerminationOutcome.NOT_CLAIMED
    )
    harness.pool.results[pool_ids["blank_ready"]] = False
    harness.add_running_worker("running-request")
    harness.transport.signal_errors.add("running-request")
    capability_ids = [
        harness.add_capability(busy_id),
        harness.add_capability(terminal_ids["terminated"]),
    ]
    already_revoked = harness.add_capability(terminal_ids["failed"], revoked=True)
    busy_revocation_observed: list[bool] = []

    def observe_forced_busy_termination(session_id: uuid.UUID) -> None:
        if session_id != busy_id:
            return
        with harness.sessions() as db:
            capability = db.get(ChatTurnCapability, capability_ids[0])
        busy_revocation_observed.append(capability.revoked_at is not None)

    harness.lifecycle.before_terminate = observe_forced_busy_termination
    harness.provider.listed = [_sandbox("sb-provider-orphan")]
    harness.trip(seconds_ago=31)

    result = asyncio.run(harness.coordinator().enforce())

    # Lease actions retain the legacy "attempted" count even if a durable claim
    # is already gone. Pool rows count only successful claims; provider rows count
    # only confirmed and durably-accounted terminations.
    assert result == SpendCapEnforcementResult(
        state="tripped",
        terminated=8,
        uncertain=0,
    )
    assert set(harness.lifecycle.calls[:4]) == set(immediate_ids.values())
    assert harness.lifecycle.calls[4:] == [busy_id]
    assert {pool_id for pool_id, _ in harness.pool.calls} == set(pool_ids.values())
    assert not set(terminal_pool_ids.values()).intersection(
        {pool_id for pool_id, _ in harness.pool.calls}
    )
    assert not set(terminal_ids.values()).intersection(harness.lifecycle.calls)
    assert harness.transport.signaled == ["running-request"]
    assert busy_revocation_observed == [True]
    assert harness.provider.termination_calls == ["sb-provider-orphan"]
    assert harness.probe.io_calls.index("transport.signal_cancel") < (
        len(harness.probe.io_calls)
        - 1
        - harness.probe.io_calls[::-1].index("lifecycle.terminate")
    )
    assert harness.probe.io_calls.index("provider.list") < harness.probe.io_calls.index(
        "provider.terminate"
    )
    with harness.sessions() as db:
        revoked = {
            row.id: row.revoked_at
            for row in db.execute(select(ChatTurnCapability)).scalars()
        }
    assert all(revoked[capability_id] is not None for capability_id in capability_ids)
    assert revoked[already_revoked] == harness.clock.now.replace(tzinfo=None)
    assert harness.events()[-1] == "kill_sweep_incomplete"


def test_grace_sleep_protects_busy_provider_and_uses_exact_environment_tags():
    harness = _Harness()
    busy_id = harness.add_lease(state="busy", sandbox_id="sb-busy")
    capability_id = harness.add_capability(busy_id)
    harness.add_interval("sb-busy")
    harness.provider.listed = [_sandbox("sb-busy"), _sandbox("sb-orphan")]
    harness.trip()

    result = asyncio.run(harness.coordinator().enforce())

    assert harness.sleep_calls == [15]
    assert harness.transport.signaled == []
    assert harness.lifecycle.calls == []
    assert harness.provider.list_tags_calls == [
        {"service": "pwc-chat", "environment": "staging"}
    ]
    assert harness.provider.termination_calls == ["sb-orphan"]
    assert result == SpendCapEnforcementResult(
        state="tripped",
        terminated=1,
        uncertain=0,
    )
    with harness.sessions() as db:
        capability = db.get(ChatTurnCapability, capability_id)
    assert capability.revoked_at is None
    assert harness.events()[-1] == "kill_sweep_incomplete"


def test_one_deadline_decision_keeps_busy_protected_when_forcing_is_skipped():
    harness = _Harness()
    harness.add_lease(state="busy", sandbox_id="sb-boundary-busy")
    harness.provider.listed = [_sandbox("sb-boundary-busy")]
    harness.trip()
    base = harness.clock.now
    moments = iter(
        [
            base + timedelta(seconds=29),
            base + timedelta(seconds=29.5),
            base + timedelta(seconds=29.9),
            base + timedelta(seconds=30.1),
        ]
    )
    last = base + timedelta(seconds=30.1)

    def boundary_clock() -> datetime:
        return next(moments, last)

    slept: list[float] = []

    async def no_advance_sleep(seconds: float) -> None:
        slept.append(seconds)

    result = asyncio.run(
        harness.coordinator(
            utcnow=boundary_clock,
            sleeper=no_advance_sleep,
        ).enforce()
    )

    assert slept == [0.5]
    assert harness.transport.signaled == []
    assert harness.lifecycle.calls == []
    assert harness.provider.termination_calls == []
    assert result == SpendCapEnforcementResult(state="tripped")
    assert next(moments) == base + timedelta(seconds=30.1)


def test_provider_success_false_and_error_have_exact_conservative_accounting():
    harness = _Harness()
    for sandbox_id in ("sb-confirmed", "sb-false", "sb-error"):
        harness.add_interval(sandbox_id)
    harness.provider.listed = [
        _sandbox("sb-confirmed"),
        _sandbox("sb-false"),
        _sandbox("sb-error"),
    ]
    harness.provider.terminate_results = {
        "sb-false": False,
        "sb-error": RuntimeError("provider unavailable"),
    }
    harness.trip(seconds_ago=31)

    result = asyncio.run(harness.coordinator().enforce())

    assert result == SpendCapEnforcementResult(
        state="tripped",
        terminated=1,
        uncertain=2,
    )
    assert harness.provider.termination_calls == [
        "sb-confirmed",
        "sb-false",
        "sb-error",
    ]
    with harness.sessions() as db:
        intervals = {
            row.modal_sandbox_id: row
            for row in db.execute(select(ChatSandboxComputeInterval)).scalars()
        }
    assert intervals["sb-confirmed"].terminal_at is not None
    assert intervals["sb-confirmed"].reconciliation_state == "confirmed"
    for sandbox_id in ("sb-false", "sb-error"):
        assert intervals[sandbox_id].terminal_at is None
        assert intervals[sandbox_id].terminal_reason == "termination_uncertain"
        assert intervals[sandbox_id].reconciliation_state == "termination_uncertain"
    assert harness.events()[-1] == "kill_sweep_incomplete"


def test_confirmed_provider_accounting_failure_falls_back_to_uncertain_once():
    harness = _Harness()
    harness.add_interval("sb-accounting-fallback")
    harness.provider.listed = [_sandbox("sb-accounting-fallback")]
    harness.trip(seconds_ago=31)
    accounting_calls: list[tuple[str, bool]] = []

    class Spend:
        def __init__(self, db) -> None:
            self.delegate = harness.spend(db)

        def status(self):
            return self.delegate.status()

        def terminate(self, sandbox_id, reason, *, confirmed):
            accounting_calls.append((reason, confirmed))
            if confirmed:
                raise RuntimeError("confirmed accounting write failed")
            return self.delegate.terminate(
                sandbox_id,
                reason,
                confirmed=confirmed,
            )

        def record_kill_sweep(self, *, complete):
            return self.delegate.record_kill_sweep(complete=complete)

    result = asyncio.run(
        harness.coordinator(spend_factory=lambda db: Spend(db)).enforce()
    )

    assert result == SpendCapEnforcementResult(
        state="tripped",
        terminated=0,
        uncertain=1,
    )
    assert harness.provider.termination_calls == ["sb-accounting-fallback"]
    assert accounting_calls == [
        ("chat_disabled_interrupted", True),
        ("termination_uncertain", False),
    ]
    with harness.sessions() as db:
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-accounting-fallback"
            )
        ).scalar_one()
    assert interval.terminal_at is None
    assert interval.reconciliation_state == "termination_uncertain"


def test_provider_iterator_error_propagates_after_prior_durable_accounting():
    harness = _Harness()
    harness.add_interval("sb-before-iterator-error")
    harness.provider.listed = [_sandbox("sb-before-iterator-error")]
    harness.provider.iterator_error = RuntimeError("listing interrupted")
    harness.trip(seconds_ago=31)

    with pytest.raises(RuntimeError, match="listing interrupted"):
        asyncio.run(harness.coordinator().enforce())

    assert harness.provider.termination_calls == ["sb-before-iterator-error"]
    with harness.sessions() as db:
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id
                == "sb-before-iterator-error"
            )
        ).scalar_one()
    assert interval.terminal_at is not None
    assert "kill_sweep_complete" not in harness.events()
    assert "kill_sweep_incomplete" not in harness.events()


def test_provider_cancellation_propagates_without_uncertain_fallback():
    harness = _Harness()
    harness.add_interval("sb-cancelled")
    harness.provider.listed = [_sandbox("sb-cancelled")]
    harness.provider.terminate_results["sb-cancelled"] = asyncio.CancelledError()
    harness.trip(seconds_ago=31)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(harness.coordinator().enforce())

    with harness.sessions() as db:
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-cancelled"
            )
        ).scalar_one()
    assert interval.terminal_at is None
    assert interval.reconciliation_state == "local"
    assert "kill_sweep_complete" not in harness.events()
    assert "kill_sweep_incomplete" not in harness.events()


def test_final_completeness_uses_global_owners_and_environment_intervals():
    complete = _Harness()
    complete.trip(seconds_ago=31)
    assert asyncio.run(complete.coordinator().enforce()).state == "tripped"
    assert complete.capacity_locker.calls == 1
    assert complete.events()[-1] == "kill_sweep_complete"

    other_environment_interval = _Harness()
    other_environment_interval.add_interval(
        "sb-production-live",
        environment="production",
    )
    other_environment_interval.trip(seconds_ago=31)
    asyncio.run(other_environment_interval.coordinator().enforce())
    assert other_environment_interval.events()[-1] == "kill_sweep_complete"

    current_environment_interval = _Harness()
    current_environment_interval.add_interval("sb-staging-live")
    current_environment_interval.trip(seconds_ago=31)
    asyncio.run(current_environment_interval.coordinator().enforce())
    assert current_environment_interval.events()[-1] == "kill_sweep_incomplete"

    global_lease = _Harness()
    global_lease.add_lease(state="ready")
    global_lease.trip(seconds_ago=31)
    asyncio.run(global_lease.coordinator().enforce())
    assert global_lease.events()[-1] == "kill_sweep_incomplete"

    global_pool = _Harness()
    global_pool.add_pool(state="blank_ready")
    global_pool.trip(seconds_ago=31)
    asyncio.run(global_pool.coordinator().enforce())
    assert global_pool.events()[-1] == "kill_sweep_incomplete"


def test_every_external_operation_runs_outside_database_transactions():
    harness = _Harness()
    harness.add_lease(state="ready")
    harness.add_pool(state="blank_ready")
    harness.add_running_worker("forced-worker")
    harness.provider.listed = [_sandbox("sb-external")]
    harness.trip(seconds_ago=31)

    asyncio.run(harness.coordinator().enforce())

    assert harness.probe.active == 0
    assert {
        "lifecycle.terminate",
        "pool.terminate",
        "transport.running_workers",
        "transport.signal_cancel",
        "provider.list",
        "provider.terminate",
    }.issubset(harness.probe.io_calls)


def test_constructor_rejects_mismatched_dependency_identity_and_clamps_limit():
    mismatched_settings = _Harness()
    mismatched_settings.lifecycle.settings = _settings()
    with pytest.raises(ValueError, match="settings must be shared"):
        mismatched_settings.coordinator()

    mismatched_repository = _Harness()
    mismatched_repository.pool.repository.settings = _settings()
    with pytest.raises(ValueError, match="repository settings must be shared"):
        mismatched_repository.coordinator()

    mismatched_sessions = _Harness()
    mismatched_sessions.lifecycle.session_factory = lambda: None
    with pytest.raises(ValueError, match="sessions must be shared"):
        mismatched_sessions.coordinator()

    mismatched_provider = _Harness()
    mismatched_provider.pool.provider = object()
    with pytest.raises(ValueError, match="provider must be shared"):
        mismatched_provider.coordinator()

    mismatched_transport = _Harness()
    mismatched_transport.lifecycle.transport = object()
    with pytest.raises(ValueError, match="transport must be shared"):
        mismatched_transport.coordinator()

    mismatched_lock = _Harness()
    mismatched_lock.lifecycle.capacity_locker = _CapacityLocker()
    with pytest.raises(ValueError, match="capacity locker must be shared"):
        mismatched_lock.coordinator()

    harness = _Harness()
    assert (
        harness.coordinator(termination_concurrency=99).termination_concurrency
        == MAX_SPEND_CAP_TERMINATION_CONCURRENCY
    )
    assert harness.coordinator(termination_concurrency=0).termination_concurrency == 1


def test_manager_preserves_exact_public_dict_and_caches_the_coordinator():
    harness = _Harness()
    manager = SandboxSessionManager(
        harness.settings,
        session_factory=harness.sessions,
        sandbox_provider=harness.provider,
    )
    composed = manager._spend_cap_coordinator()
    assert composed.settings is harness.settings
    assert composed.session_factory is harness.sessions
    assert composed.transport is manager._worker_transport()
    assert composed.provider is harness.provider
    assert composed.lifecycle is manager._lease_lifecycle_coordinator()
    assert composed.pool is manager._pool_coordinator()
    assert composed.lifecycle.transport is composed.transport
    assert composed.pool.transport is composed.transport
    assert (
        composed.lifecycle.capacity_locker is composed.pool.repository.capacity_locker
    )
    assert manager._spend_cap_coordinator() is composed
    calls = 0

    class Coordinator:
        async def enforce(self):
            nonlocal calls
            calls += 1
            return SpendCapEnforcementResult(
                state="tripped",
                terminated=7,
                uncertain=2,
            )

    coordinator = Coordinator()
    manager._sandbox_spend_cap = coordinator

    result = asyncio.run(manager.enforce_spend_cap())

    assert result == {"state": "tripped", "terminated": 7, "uncertain": 2}
    assert set(result) == {"state", "terminated", "uncertain"}
    assert manager._spend_cap_coordinator() is coordinator
    assert calls == 1


def test_more_than_two_batches_keep_at_most_eight_actions_in_flight():
    async def exercise_leases() -> _Harness:
        harness = _Harness()
        for _ in range(17):
            harness.add_lease(state="ready")
        harness.lifecycle.release_terminations = asyncio.Event()
        harness.trip(seconds_ago=31)
        task = asyncio.create_task(harness.coordinator().enforce())
        while len(harness.lifecycle.calls) < 8:
            await asyncio.sleep(0)
        assert len(harness.lifecycle.calls) == 8
        assert len(asyncio.all_tasks()) <= 10
        harness.lifecycle.release_terminations.set()
        result = await task
        assert result.terminated == 17
        assert harness.lifecycle.max_in_flight == 8
        return harness

    async def exercise_pools() -> _Harness:
        harness = _Harness()
        for _ in range(17):
            harness.add_pool(state="blank_ready")
        harness.pool.release_terminations = asyncio.Event()
        harness.trip(seconds_ago=31)
        task = asyncio.create_task(harness.coordinator().enforce())
        while not harness.pool.calls:
            await asyncio.sleep(0)
        assert 1 <= len(harness.pool.calls) <= 8
        assert len(asyncio.all_tasks()) <= 10
        harness.pool.release_terminations.set()
        result = await task
        assert result.terminated == 17
        assert harness.pool.max_in_flight <= 8
        return harness

    async def exercise_provider() -> _Harness:
        harness = _Harness()
        harness.provider.listed = [
            _sandbox(f"sb-provider-{index}") for index in range(17)
        ]
        harness.provider.release_terminations = asyncio.Event()
        harness.trip(seconds_ago=31)
        task = asyncio.create_task(harness.coordinator().enforce())
        while not harness.provider.termination_calls:
            await asyncio.sleep(0)
        assert 1 <= harness.provider.yielded <= 8
        assert len(asyncio.all_tasks()) <= 10
        harness.provider.release_terminations.set()
        result = await task
        assert result.terminated == 17
        assert harness.provider.max_in_flight <= 8
        assert harness.provider.yielded == 17
        return harness

    async def exercise_all():
        return (
            await exercise_leases(),
            await exercise_pools(),
            await exercise_provider(),
        )

    lease_harness, pool_harness, provider_harness = asyncio.run(exercise_all())
    assert lease_harness.probe.active == 0
    assert pool_harness.probe.active == 0
    assert provider_harness.probe.active == 0


def test_same_coordinator_serializes_concurrent_enforcement_end_to_end():
    harness = _Harness()
    harness.add_interval("sb-serialized")
    harness.provider.listed = [_sandbox("sb-serialized")]
    harness.provider.release_terminations = asyncio.Event()
    harness.trip(seconds_ago=31)
    spend_events: list[str] = []

    class Spend:
        def __init__(self, db) -> None:
            self.delegate = harness.spend(db)

        def status(self):
            spend_events.append("status")
            return self.delegate.status()

        def terminate(self, sandbox_id, reason, *, confirmed):
            spend_events.append("account")
            return self.delegate.terminate(
                sandbox_id,
                reason,
                confirmed=confirmed,
            )

        def record_kill_sweep(self, *, complete):
            spend_events.append("sweep")
            return self.delegate.record_kill_sweep(complete=complete)

    coordinator = harness.coordinator(spend_factory=lambda db: Spend(db))

    async def exercise():
        first = asyncio.create_task(coordinator.enforce())
        while not harness.provider.termination_calls:
            await asyncio.sleep(0)
        second = asyncio.create_task(coordinator.enforce())
        for _ in range(5):
            await asyncio.sleep(0)
        assert harness.provider.list_tags_calls == [
            {"service": "pwc-chat", "environment": "staging"}
        ]
        assert harness.provider.termination_calls == ["sb-serialized"]
        assert spend_events == ["status"]
        harness.provider.release_terminations.set()
        return await asyncio.gather(first, second)

    first, second = asyncio.run(exercise())

    assert first == SpendCapEnforcementResult(state="tripped", terminated=1)
    assert second == SpendCapEnforcementResult(state="tripped", terminated=1)
    assert harness.provider.max_in_flight == 1
    assert len(harness.provider.list_tags_calls) == 2
    assert harness.provider.termination_calls == [
        "sb-serialized",
        "sb-serialized",
    ]
    assert spend_events == [
        "status",
        "account",
        "sweep",
        "status",
        "account",
        "sweep",
    ]
