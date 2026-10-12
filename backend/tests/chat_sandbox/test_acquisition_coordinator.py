from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.services.chat_sandbox_acquisition_coordinator import (
    LeaseReused,
    SandboxCreated,
)
from backend.services.chat_sandbox_provider import (
    ExecutorLaunchBundle,
    SandboxLaunchMode,
)
from backend.tests.chat_sandbox.capacity_harness import (
    _database,
    _lease,
    _Provider,
    _session,
    _settings,
)
from backend.tests.chat_sandbox.acquisition_harness import (
    _coordinator,
)


def test_direct_coordinator_creation_returns_a_typed_outcome_without_db_io_overlap():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = _Provider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)

    outcome = asyncio.run(coordinator.acquire(session_id))

    assert isinstance(outcome, SandboxCreated)
    assert outcome.sandbox is provider.created
    assert outcome.public_label == "created"
    assert outcome.created is True
    assert provider.calls[0][0] == "create"


def test_direct_coordinator_forwards_executor_launch_mode_to_provider():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    class RecordingProvider(_Provider):
        async def create(self, **options):
            self.launch_mode = options["launch_mode"]
            self.executor_launch = options["executor_launch"]
            return await super().create(**options)

    provider = RecordingProvider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)
    bundle = ExecutorLaunchBundle(
        b"signed-launch", shard_generation=9, authorization_keys_json="{}"
    )
    coordinator.executor_launch_factory = lambda _generation: asyncio.sleep(
        0, result=bundle
    )

    asyncio.run(coordinator.acquire(session_id, launch_mode=SandboxLaunchMode.EXECUTOR))

    assert provider.launch_mode is SandboxLaunchMode.EXECUTOR
    assert provider.executor_launch is bundle


@pytest.mark.parametrize(
    ("persistent", "expected_cohort"),
    [(False, "rediscovered"), (True, "control_reconnected")],
)
def test_reused_lease_records_control_reconnection_state(persistent, expected_cohort):
    settings = _settings(chat_persistent_worker_enabled=persistent)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="idle",
                sandbox_id="sb-reused",
                worker_generation="generation-reused",
            )
        )
    provider = _Provider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)

    outcome = asyncio.run(coordinator.acquire(session_id))

    assert isinstance(outcome, LeaseReused)
    assert outcome.reuse_cohort == expected_cohort


@pytest.mark.parametrize(
    "mismatch",
    ["state_settings", "pool_repository_settings"],
)
def test_direct_coordinator_rejects_mismatched_repository_settings(mismatch):
    settings = _settings()
    sessions = _database()
    provider = _Provider(transactions=[])

    with pytest.raises(ValueError, match="settings must be shared"):
        _coordinator(
            settings,
            sessions,
            provider,
            **{mismatch: _settings()},
        )
