"""Sandbox pool coordinator harness shared by warm-pool tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace

from sqlalchemy import create_engine, event
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
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    LeaseEvictionOutcome,
)
from backend.services.chat_sandbox_pool_coordinator import (
    ChatSandboxPoolCoordinator,
)
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
)
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
