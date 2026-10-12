"""Fake provider, database, and settings for sandbox capacity acquisition tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
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
    ChatTurnLatency,
)
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_sandbox_ready_timeout_seconds": 0.1,
        "chat_persistent_worker_enabled": False,
        "chat_blank_pool_enabled": False,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_workspace_snapshots_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _spend_settings(**overrides) -> Settings:
    values = {
        "chat_sandbox_spend_enforcement_enabled": True,
        "chat_sandbox_budget_attestation": "attested",
        "chat_sandbox_warning_microusd": 75_000_000,
        "chat_sandbox_application_cap_microusd": 100_000_000,
        "chat_sandbox_environment_cap_microusd": 125_000_000,
        "chat_sandbox_workspace_cap_microusd": 250_000_000,
        "chat_sandbox_cpu": 1,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 2048,
        "chat_sandbox_memory_limit_mib": 2048,
    }
    values.update(overrides)
    return _settings(**values)


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChatSession.__table__.create(engine)
    ChatSandboxPool.__table__.create(engine)
    ChatSandboxLease.__table__.create(engine)
    ChatSandboxBudgetState.__table__.create(engine)
    ChatSandboxComputeInterval.__table__.create(engine)
    ChatSandboxCircuitEvent.__table__.create(engine)
    ChatTurnLatency.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _session(session_id: uuid.UUID) -> ChatSession:
    return ChatSession(
        id=session_id,
        hf_user_id=f"owner-{session_id}",
        hf_username=f"owner-{session_id}",
        selected_model="google/gemma-4-31B-it",
        execution_backend="modal_cli",
    )


def _lease(
    settings: Settings,
    session_id: uuid.UUID,
    *,
    state: str,
    sandbox_id: str | None,
    token_hash: str | None = None,
    expires_at: datetime | None = None,
    worker_generation: str | None = "generation-current",
    last_activity_at: datetime | None = None,
    snapshot_id: str | None = None,
) -> ChatSandboxLease:
    now = datetime.now(UTC)
    return ChatSandboxLease(
        chat_session_id=session_id,
        modal_sandbox_id=sandbox_id,
        app_release_id=settings.release_id,
        image_version=settings.chat_modal_image_version,
        worker_contract_version=settings.chat_worker_contract_version,
        worker_generation=worker_generation,
        egress_policy_digest=egress_policy_digest(settings),
        state=state,
        lease_token_hash=token_hash,
        lease_expires_at=expires_at,
        last_activity_at=last_activity_at or now,
        workspace_snapshot_id=snapshot_id,
        snapshot_image_version=(
            settings.chat_modal_image_version if snapshot_id else None
        ),
        snapshot_updated_at=now if snapshot_id else None,
        workspace_dirty=False,
        created_at=now,
        updated_at=now,
    )


class _Provider:
    def __init__(self, *, transactions=None):
        self.transactions = transactions or []
        self.created = SimpleNamespace(object_id="sb-created")
        self.calls: list[tuple[object, ...]] = []

    def _assert_outside_transaction(self) -> None:
        assert not any(db.in_transaction() for db in self.transactions)

    async def create(self, **options):
        self._assert_outside_transaction()
        self.calls.append(("create", options["worker_generation"]))
        return self.created

    async def resolve(self, sandbox_id):
        self._assert_outside_transaction()
        self.calls.append(("resolve", sandbox_id))
        return SimpleNamespace(object_id=sandbox_id)

    async def poll(self, sandbox):
        self._assert_outside_transaction()
        self.calls.append(("poll", sandbox.object_id))
        return None

    async def health(self, sandbox, **options):
        self._assert_outside_transaction()
        self.calls.append(("health", sandbox.object_id, options["worker_generation"]))
        return True

    async def terminate(self, sandbox_id, sandbox=None):
        self._assert_outside_transaction()
        self.calls.append(("terminate", sandbox_id, sandbox))
        return True


def _manager(
    settings: Settings,
    sessions,
    provider,
    *,
    capacity_locker=None,
    start_locker=None,
) -> SandboxSessionManager:
    opened = provider.transactions

    def factory():
        db = sessions()
        opened.append(db)
        return db

    state_repository = ChatSandboxStateRepository(settings)
    capacity_repository = ChatSandboxCapacityRepository(
        settings,
        state_repository,
        capacity_locker=capacity_locker or (lambda _db, *, wait=True: True),
        start_locker=start_locker or (lambda *_args: None),
    )
    return SandboxSessionManager(
        settings,
        session_factory=factory,
        sandbox_provider=provider,
        state_repository=state_repository,
        capacity_repository=capacity_repository,
    )
