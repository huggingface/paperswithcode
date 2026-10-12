from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.models.database import ChatSandboxLease
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseStateClaim,
    LeaseUnavailable,
    SnapshotClaim,
    StartClaim,
    WorkerGenerationUnavailable,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_workspace_snapshots_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _lease(
    *,
    state: str = "ready",
    sandbox_id: str | None = "sb-current",
    worker_generation: str | None = "generation-a",
    token_hash: str | None = None,
    snapshot_id: str | None = None,
    snapshot_image_version: str | None = None,
) -> ChatSandboxLease:
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    return ChatSandboxLease(
        chat_session_id=uuid.uuid4(),
        modal_sandbox_id=sandbox_id,
        app_release_id="release-old",
        image_version="im-current",
        worker_contract_version="worker-v1",
        worker_generation=worker_generation,
        state=state,
        lease_token_hash=token_hash,
        lease_expires_at=None,
        last_activity_at=now,
        workspace_snapshot_id=snapshot_id,
        snapshot_image_version=snapshot_image_version,
        snapshot_updated_at=now if snapshot_id else None,
        workspace_dirty=False,
        failure_code=None,
        created_at=now,
        updated_at=now,
    )


def _state(lease: ChatSandboxLease) -> tuple[object, ...]:
    return (
        lease.modal_sandbox_id,
        lease.app_release_id,
        lease.image_version,
        lease.worker_contract_version,
        lease.worker_generation,
        lease.state,
        lease.lease_token_hash,
        lease.lease_expires_at,
        lease.last_activity_at,
        lease.workspace_snapshot_id,
        lease.snapshot_image_version,
        lease.snapshot_updated_at,
        lease.workspace_dirty,
        lease.failure_code,
        lease.updated_at,
    )


@pytest.mark.parametrize(
    ("snapshots_enabled", "snapshot_image", "expected_snapshot"),
    [
        (True, "im-current", "snapshot-a"),
        (True, "im-old", None),
        (False, "im-current", None),
    ],
)
def test_start_claim_selects_only_compatible_enabled_snapshot(
    snapshots_enabled, snapshot_image, expected_snapshot
):
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(
        _settings(chat_workspace_snapshots_enabled=snapshots_enabled)
    )
    lease = _lease(
        state="terminated",
        sandbox_id="sb-stale",
        snapshot_id="snapshot-a",
        snapshot_image_version=snapshot_image,
    )

    claim = repository.claim_start(
        lease,
        creation_token="creation-token",
        now=now,
        ready_timeout_seconds=20,
        worker_generation="generation-new",
    )

    assert claim.token_hash == repository.token_hash("creation-token")
    assert claim.stale_sandbox_id == "sb-stale"
    assert claim.snapshot_id == expected_snapshot
    assert claim.worker_generation == "generation-new"
    assert lease.state == "starting"
    assert lease.modal_sandbox_id is None
    assert lease.app_release_id == "release-current"
    assert lease.image_version == "im-current"
    assert lease.worker_contract_version == "worker-v1"
    assert lease.worker_generation == "generation-new"
    assert lease.lease_token_hash == claim.token_hash
    assert lease.lease_expires_at == now + timedelta(seconds=35)
    assert lease.failure_code is None
    assert lease.updated_at == now
    if expected_snapshot is None:
        assert lease.workspace_snapshot_id is None
        assert lease.snapshot_image_version is None
        assert lease.snapshot_updated_at is None
    else:
        assert lease.workspace_snapshot_id == "snapshot-a"


def test_fail_start_applies_only_to_the_owned_start_claim():
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    failed_at = now + timedelta(seconds=1)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="terminated", sandbox_id="sb-stale")
    claim = repository.claim_start(
        lease,
        creation_token="creation-token",
        now=now,
        ready_timeout_seconds=20,
        worker_generation="generation-new",
    )

    assert repository.fail_start(
        lease,
        claim=claim,
        code="sandbox_timeout",
        now=failed_at,
    )
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.worker_generation == "generation-new"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.failure_code == "sandbox_timeout"
    assert lease.updated_at == failed_at


def test_start_snapshot_clear_and_land_are_owned_by_the_same_claim():
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    landed_at = now + timedelta(seconds=2)
    repository = ChatSandboxStateRepository(
        _settings(chat_workspace_snapshots_enabled=True)
    )
    lease = _lease(
        state="terminated",
        snapshot_id="snapshot-a",
        snapshot_image_version="im-current",
    )
    claim = repository.claim_start(
        lease,
        creation_token="creation-token",
        now=now,
        ready_timeout_seconds=20,
        worker_generation="generation-new",
    )

    assert repository.clear_start_snapshot(lease, claim=claim)
    assert lease.workspace_snapshot_id is None
    assert lease.snapshot_image_version is None
    assert lease.snapshot_updated_at is None
    assert repository.land_start(
        lease,
        claim=claim,
        sandbox_id="sb-new",
        now=landed_at,
    )
    assert lease.modal_sandbox_id == "sb-new"
    assert lease.state == "ready"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.last_activity_at == landed_at
    assert lease.workspace_dirty is False
    assert lease.updated_at == landed_at


def test_start_snapshot_clear_and_land_reject_replaced_generation():
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(
        _settings(chat_workspace_snapshots_enabled=True)
    )
    lease = _lease(
        state="terminated",
        snapshot_id="snapshot-a",
        snapshot_image_version="im-current",
    )
    claim = repository.claim_start(
        lease,
        creation_token="creation-token",
        now=now,
        ready_timeout_seconds=20,
        worker_generation="generation-new",
    )
    lease.worker_generation = "generation-replacement"
    before = _state(lease)

    assert not repository.clear_start_snapshot(lease, claim=claim)
    assert not repository.land_start(
        lease,
        claim=claim,
        sandbox_id="sb-new",
        now=now + timedelta(seconds=1),
    )
    assert _state(lease) == before


@pytest.mark.parametrize(
    "mismatch",
    ["state", "token", "sandbox", "generation"],
)
def test_fail_start_rejects_stale_or_replaced_claim(mismatch):
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="terminated")
    claim = repository.claim_start(
        lease,
        creation_token="creation-token",
        now=now,
        ready_timeout_seconds=20,
        worker_generation="generation-new",
    )
    if mismatch == "state":
        lease.state = "ready"
    elif mismatch == "token":
        lease.lease_token_hash = "replacement-token"
    elif mismatch == "sandbox":
        lease.modal_sandbox_id = "sb-replacement"
    else:
        lease.worker_generation = "generation-replacement"
    before = _state(lease)

    assert not repository.fail_start(
        lease,
        claim=claim,
        code="sandbox_timeout",
        now=now + timedelta(seconds=1),
    )
    assert _state(lease) == before


@pytest.mark.parametrize(
    ("state", "sandbox_id", "token_hash", "worker_generation", "expected_error"),
    [
        ("busy", "sb-current", None, "generation-a", LeaseUnavailable),
        ("ready", "sb-replacement", None, "generation-a", LeaseUnavailable),
        ("ready", "sb-current", "already-owned", "generation-a", LeaseUnavailable),
        ("ready", "sb-current", None, None, WorkerGenerationUnavailable),
    ],
)
def test_worker_claim_rejects_ineligible_lease(
    state, sandbox_id, token_hash, worker_generation, expected_error
):
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(
        state=state,
        sandbox_id=sandbox_id,
        token_hash=token_hash,
        worker_generation=worker_generation,
    )
    before = _state(lease)

    with pytest.raises(expected_error):
        repository.claim_worker(
            lease,
            sandbox_id="sb-current",
            assignment_token="assignment-token",
            now=datetime(2026, 8, 10, 13, tzinfo=UTC),
        )

    assert _state(lease) == before


def test_worker_claim_and_release_preserve_generation_and_mark_workspace_dirty():
    claimed_at = datetime(2026, 8, 10, 13, tzinfo=UTC)
    released_at = claimed_at + timedelta(seconds=2)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="idle")

    claim = repository.claim_worker(
        lease,
        sandbox_id="sb-current",
        assignment_token="assignment-token",
        now=claimed_at,
    )
    assert claim.sandbox_id == "sb-current"
    assert claim.token_hash == repository.token_hash("assignment-token")
    assert claim.assignment_token == "assignment-token"
    assert claim.worker_generation == "generation-a"
    assert lease.state == "busy"
    assert lease.lease_token_hash == claim.token_hash
    assert lease.last_activity_at == claimed_at

    assert repository.release_worker(lease, claim=claim, now=released_at)
    assert lease.state == "idle"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.last_activity_at == released_at
    assert lease.workspace_dirty is True
    assert lease.updated_at == released_at


@pytest.mark.parametrize(
    "mismatch",
    ["state", "token", "sandbox", "generation"],
)
def test_worker_release_rejects_stale_or_replaced_claim(mismatch):
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="ready")
    claim = repository.claim_worker(
        lease,
        sandbox_id="sb-current",
        assignment_token="assignment-token",
        now=now,
    )
    if mismatch == "state":
        lease.state = "terminating"
    elif mismatch == "token":
        lease.lease_token_hash = "replacement-token"
    elif mismatch == "sandbox":
        lease.modal_sandbox_id = "sb-replacement"
    else:
        lease.worker_generation = "generation-replacement"
    before = _state(lease)

    assert not repository.release_worker(
        lease,
        claim=claim,
        now=now + timedelta(seconds=1),
    )
    assert _state(lease) == before


def test_worker_termination_claim_and_finish_are_owned_compare_and_sets():
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    expires_at = now + timedelta(seconds=35)
    finished_at = now + timedelta(seconds=2)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="ready")
    worker_claim = repository.claim_worker(
        lease,
        sandbox_id="sb-current",
        assignment_token="assignment-token",
        now=now,
    )

    termination_claim = repository.claim_worker_termination(
        lease,
        claim=worker_claim,
        termination_token="termination-token",
        failure_code="sandbox_worker_failed",
        expires_at=expires_at,
        now=now + timedelta(seconds=1),
    )

    assert termination_claim is not None
    assert termination_claim.sandbox_id == "sb-current"
    assert termination_claim.token_hash == repository.token_hash("termination-token")
    assert termination_claim.worker_generation == "generation-a"
    assert lease.state == "terminating"
    assert lease.failure_code == "sandbox_worker_failed"
    assert lease.lease_token_hash == termination_claim.token_hash
    assert lease.lease_expires_at == expires_at

    assert repository.finish_termination(
        lease,
        claim=termination_claim,
        state="failed",
        failure_code="sandbox_worker_failed",
        clear_sandbox=True,
        now=finished_at,
    )
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.worker_generation == "generation-a"
    assert lease.failure_code == "sandbox_worker_failed"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.updated_at == finished_at


@pytest.mark.parametrize(
    "mismatch",
    ["state", "token", "sandbox", "generation"],
)
def test_worker_termination_claim_rejects_stale_or_replaced_worker(mismatch):
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="ready")
    worker_claim = repository.claim_worker(
        lease,
        sandbox_id="sb-current",
        assignment_token="assignment-token",
        now=now,
    )
    if mismatch == "state":
        lease.state = "idle"
    elif mismatch == "token":
        lease.lease_token_hash = "replacement-token"
    elif mismatch == "sandbox":
        lease.modal_sandbox_id = "sb-replacement"
    else:
        lease.worker_generation = "generation-replacement"
    before = _state(lease)

    assert (
        repository.claim_worker_termination(
            lease,
            claim=worker_claim,
            termination_token="termination-token",
            failure_code="sandbox_worker_failed",
            expires_at=now + timedelta(seconds=35),
            now=now + timedelta(seconds=1),
        )
        is None
    )
    assert _state(lease) == before


@pytest.mark.parametrize(
    "mismatch",
    ["state", "token", "sandbox", "generation"],
)
def test_finish_termination_rejects_stale_or_replaced_claim(mismatch):
    now = datetime(2026, 8, 10, 13, tzinfo=UTC)
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(state="ready")
    worker_claim = repository.claim_worker(
        lease,
        sandbox_id="sb-current",
        assignment_token="assignment-token",
        now=now,
    )
    termination_claim = repository.claim_worker_termination(
        lease,
        claim=worker_claim,
        termination_token="termination-token",
        failure_code="sandbox_worker_failed",
        expires_at=now + timedelta(seconds=35),
        now=now + timedelta(seconds=1),
    )
    assert termination_claim is not None
    if mismatch == "state":
        lease.state = "ready"
    elif mismatch == "token":
        lease.lease_token_hash = "replacement-token"
    elif mismatch == "sandbox":
        lease.modal_sandbox_id = "sb-replacement"
    else:
        lease.worker_generation = "generation-replacement"
    before = _state(lease)

    assert not repository.finish_termination(
        lease,
        claim=termination_claim,
        state="failed",
        failure_code="sandbox_worker_failed",
        clear_sandbox=True,
        now=now + timedelta(seconds=2),
    )
    assert _state(lease) == before


def test_start_lock_precedes_row_lock_and_repository_never_commits():
    session_id = uuid.uuid4()
    lease = _lease()
    calls: list[tuple[str, dict[str, object]]] = []

    class Result:
        def scalar_one_or_none(self):
            return lease

    class DB:
        def execute(self, query):
            compiled = query.compile()
            calls.append((str(compiled), compiled.params))
            return Result()

        def commit(self):
            raise AssertionError("repository transitions must not commit")

    db = DB()
    repository = ChatSandboxStateRepository(_settings())

    repository.lock_start_claim(db, session_id)
    assert repository.load_lease(db, session_id, lock=True) is lease

    assert "pg_advisory_xact_lock" in calls[0][0]
    assert f"chat-sandbox:{session_id}" in calls[0][1].values()
    assert "FOR UPDATE" in calls[1][0]
    assert len(calls) == 2


def test_manager_constructor_uses_injected_state_repository():
    settings = _settings()
    repository = ChatSandboxStateRepository(settings)
    manager = SandboxSessionManager(
        settings,
        state_repository=repository,
    )

    capacity = manager._capacity_repository()

    assert manager._state_repository() is repository
    assert capacity.state_repository is repository
    assert manager._capacity_repository() is capacity


class _TransactionContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _TransactionDB(_TransactionContext):
    def begin(self):
        return _TransactionContext()

    def scalar(self, *_args):
        # Staging startup looks up a running turn's qualification profile.
        return None


def _manager_for_start_transition(lease, provider) -> SandboxSessionManager:
    settings = _settings(
        chat_sandbox_ready_timeout_seconds=2,
        chat_persistent_worker_enabled=False,
        chat_blank_pool_enabled=False,
        chat_sandbox_admission_enabled=True,
        chat_sandbox_spend_enforcement_enabled=False,
    )

    class StateRepository(ChatSandboxStateRepository):
        def load_lease(self, *_args, **_options):
            return lease

    state_repository = StateRepository(settings)
    capacity_repository = ChatSandboxCapacityRepository(
        settings,
        state_repository,
        capacity_locker=lambda *_args, **_kwargs: True,
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_options: lease,
    )
    manager = SandboxSessionManager(
        settings,
        session_factory=_TransactionDB,
        sandbox_provider=provider,
        state_repository=state_repository,
        capacity_repository=capacity_repository,
    )

    async def enforce_warm_cap():
        return 0

    manager._acquisition_coordinator().lease_maintenance.enforce_warm_cap = (
        enforce_warm_cap
    )
    return manager


def test_manager_provider_create_failure_fails_the_owned_start_claim():
    lease = _lease(state="terminated", sandbox_id=None)
    observed_start: list[tuple[object, ...]] = []

    class Provider:
        async def create(self, **options):
            observed_start.append(
                (
                    lease.state,
                    lease.lease_token_hash,
                    lease.worker_generation,
                    options["worker_generation"],
                )
            )
            raise RuntimeError("provider create failed")

    manager = _manager_for_start_transition(lease, Provider())

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(lease.chat_session_id))

    assert exc_info.value.code == "sandbox_start_failed"
    assert str(exc_info.value) == "Secure workspace startup failed"
    assert len(observed_start) == 1
    state, token_hash, lease_generation, provider_generation = observed_start[0]
    assert state == "starting"
    assert token_hash
    assert lease_generation == provider_generation
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.failure_code == "sandbox_start_failed"


def test_manager_landing_rejects_new_generation_and_cleans_old_provider():
    lease = _lease(state="terminated", sandbox_id=None)
    repository = ChatSandboxStateRepository(_settings())
    created = SimpleNamespace(object_id="sb-created")
    provider_generation: list[str] = []
    terminations: list[tuple[str, object]] = []
    successor_state: list[tuple[object, ...]] = []

    class Provider:
        async def create(self, **options):
            provider_generation.append(options["worker_generation"])
            lease.state = "starting"
            lease.modal_sandbox_id = None
            lease.worker_generation = "generation-successor"
            lease.lease_token_hash = repository.token_hash("successor-token")
            lease.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
            lease.failure_code = None
            successor_state.append(_state(lease))
            return created

        async def terminate(self, sandbox_id, sandbox=None):
            terminations.append((sandbox_id, sandbox))
            return True

    manager = _manager_for_start_transition(lease, Provider())

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(lease.chat_session_id))

    assert exc_info.value.code == "sandbox_start_failed"
    assert str(exc_info.value) == "Secure workspace ownership changed"
    assert provider_generation and provider_generation[0] != "generation-successor"
    assert terminations == [("sb-created", created)]
    assert _state(lease) == successor_state[0]
    assert lease.state == "starting"
    assert lease.modal_sandbox_id is None
    assert lease.worker_generation == "generation-successor"
    assert lease.lease_token_hash == repository.token_hash("successor-token")


@pytest.mark.parametrize("prior_state", ["starting", "busy", "terminating"])
def test_unconditional_termination_replaces_any_in_flight_owner(prior_state):
    repository = ChatSandboxStateRepository(_settings())
    expires_at = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(
        state=prior_state,
        sandbox_id="sb-current",
        token_hash="prior-owner-token",
        worker_generation="generation-a",
    )

    claim = repository.claim_termination(
        lease,
        termination_token="termination-token",
        failure_code="forced_cleanup",
        expires_at=expires_at,
    )

    assert claim is not None
    assert claim.sandbox_id == "sb-current"
    assert claim.token_hash == repository.token_hash("termination-token")
    assert claim.worker_generation == "generation-a"
    assert claim.failure_code == "forced_cleanup"
    assert claim.should_snapshot is False
    assert lease.state == "terminating"
    assert lease.failure_code == "forced_cleanup"
    assert lease.lease_token_hash == claim.token_hash
    assert lease.lease_expires_at == expires_at


def test_historical_null_generation_can_complete_owned_termination():
    repository = ChatSandboxStateRepository(_settings())
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(
        state="busy",
        sandbox_id="sb-historical",
        token_hash="historical-owner",
        worker_generation=None,
    )
    claim = repository.claim_termination(
        lease,
        termination_token="termination-token",
        failure_code=None,
        expires_at=now + timedelta(seconds=30),
    )

    assert claim is not None
    assert claim.worker_generation is None
    assert repository.finish_termination(
        lease,
        claim=claim,
        state="terminated",
        failure_code=None,
        clear_sandbox=True,
        now=now,
    )
    assert lease.state == "terminated"
    assert lease.modal_sandbox_id is None
    assert lease.worker_generation is None


def test_idle_snapshot_claim_record_and_finish_share_one_generation_bound_owner():
    repository = ChatSandboxStateRepository(
        _settings(chat_workspace_snapshots_enabled=True)
    )
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(state="idle", sandbox_id="sb-current")
    lease.workspace_dirty = True

    claim = repository.claim_snapshot_termination(
        lease,
        termination_token="termination-token",
        expires_at=now + timedelta(seconds=30),
    )

    assert claim is not None
    assert claim.sandbox_id == "sb-current"
    assert claim.worker_generation == "generation-a"
    assert claim.should_snapshot is True
    assert lease.state == "terminating"
    assert repository.record_snapshot(
        lease,
        claim=claim,
        snapshot_id="snapshot-new",
        image_version="im-current",
        now=now + timedelta(seconds=1),
    )
    assert lease.workspace_snapshot_id == "snapshot-new"
    assert lease.snapshot_image_version == "im-current"
    assert lease.workspace_dirty is False
    assert repository.finish_termination(
        lease,
        claim=claim,
        state="terminated",
        failure_code=None,
        clear_sandbox=True,
        now=now + timedelta(seconds=2),
    )
    assert lease.state == "terminated"
    assert lease.modal_sandbox_id is None


def test_snapshot_record_and_finish_refuse_a_successor_generation():
    repository = ChatSandboxStateRepository(
        _settings(chat_workspace_snapshots_enabled=True)
    )
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(state="idle", sandbox_id="sb-current")
    lease.workspace_dirty = True
    claim = repository.claim_snapshot_termination(
        lease,
        termination_token="termination-token",
        expires_at=now + timedelta(seconds=30),
    )
    assert claim is not None
    lease.state = "idle"
    lease.modal_sandbox_id = "sb-successor"
    lease.worker_generation = "generation-successor"
    lease.lease_token_hash = None
    before = _state(lease)

    assert not repository.record_snapshot(
        lease,
        claim=claim,
        snapshot_id="snapshot-old-owner",
        image_version="im-current",
        now=now + timedelta(seconds=1),
    )
    assert not repository.finish_termination(
        lease,
        claim=claim,
        state="terminated",
        failure_code=None,
        clear_sandbox=True,
        now=now + timedelta(seconds=2),
    )
    assert _state(lease) == before


@pytest.mark.parametrize(
    ("state", "active_expiry", "failure_code"),
    [
        ("busy", None, "sandbox_worker_failed"),
        ("terminating", None, "prior_failure"),
    ],
)
def test_stale_busy_and_terminating_claims_are_generation_bound(
    state, active_expiry, failure_code
):
    repository = ChatSandboxStateRepository(_settings())
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(
        state=state,
        sandbox_id="sb-current",
        token_hash="prior-token",
        worker_generation="generation-a",
    )
    lease.failure_code = failure_code if state == "terminating" else None
    lease.lease_expires_at = now - timedelta(seconds=1)
    expected = LeaseStateClaim(
        state=state,
        sandbox_id="sb-current",
        token_hash="prior-token",
        worker_generation="generation-a",
    )

    claim = repository.claim_stale_termination(
        lease,
        expected=expected,
        active_turn_expires_at=active_expiry,
        termination_token="termination-token",
        expires_at=now + timedelta(seconds=30),
        now=now,
    )

    assert claim is not None
    assert claim.failure_code == failure_code
    assert claim.worker_generation == "generation-a"
    assert lease.state == "terminating"
    assert lease.lease_token_hash == claim.token_hash

    successor = _lease(
        state=state,
        sandbox_id="sb-current",
        token_hash="prior-token",
        worker_generation="generation-successor",
    )
    successor.failure_code = lease.failure_code
    successor.lease_expires_at = now - timedelta(seconds=1)
    before = _state(successor)
    assert (
        repository.claim_stale_termination(
            successor,
            expected=expected,
            active_turn_expires_at=active_expiry,
            termination_token="termination-token",
            expires_at=now + timedelta(seconds=30),
            now=now,
        )
        is None
    )
    assert _state(successor) == before


def test_stale_claim_refuses_renewed_busy_turn_or_termination_lease():
    repository = ChatSandboxStateRepository(_settings())
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    for state, active_expiry in (
        ("busy", now + timedelta(seconds=1)),
        ("terminating", None),
    ):
        lease = _lease(
            state=state,
            sandbox_id="sb-current",
            token_hash="owner-token",
        )
        lease.lease_expires_at = now + timedelta(seconds=1)
        expected = LeaseStateClaim(
            state=state,
            sandbox_id="sb-current",
            token_hash="owner-token",
            worker_generation="generation-a",
        )
        before = _state(lease)
        assert (
            repository.claim_stale_termination(
                lease,
                expected=expected,
                active_turn_expires_at=active_expiry,
                termination_token="termination-token",
                expires_at=now + timedelta(seconds=30),
                now=now,
            )
            is None
        )
        assert _state(lease) == before


@pytest.mark.parametrize("renewed", [False, True])
def test_expired_start_failure_checks_expiry_and_generation(renewed):
    repository = ChatSandboxStateRepository(_settings())
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(
        state="starting",
        sandbox_id=None,
        token_hash="start-token",
        worker_generation="generation-a",
    )
    lease.lease_expires_at = now + timedelta(seconds=1 if renewed else -1)
    claim = StartClaim(
        token_hash="start-token",
        stale_sandbox_id=None,
        snapshot_id=None,
        worker_generation="generation-a",
    )
    before = _state(lease)

    result = repository.fail_expired_start(
        lease,
        claim=claim,
        code="sandbox_start_failed",
        now=now,
    )

    assert result is not renewed
    if renewed:
        assert _state(lease) == before
    else:
        assert lease.state == "failed"
        assert lease.failure_code == "sandbox_start_failed"

    replaced = _lease(
        state="starting",
        sandbox_id=None,
        token_hash="start-token",
        worker_generation="generation-successor",
    )
    replaced.lease_expires_at = now - timedelta(seconds=1)
    replaced_before = _state(replaced)
    assert not repository.fail_expired_start(
        replaced,
        claim=claim,
        code="sandbox_start_failed",
        now=now,
    )
    assert _state(replaced) == replaced_before


@pytest.mark.parametrize(
    ("state", "sandbox_id"),
    [("ready", None), ("idle", "sb-lost")],
)
def test_mark_lost_handles_ready_and_idle_claims(state, sandbox_id):
    repository = ChatSandboxStateRepository(_settings())
    now = datetime(2026, 8, 10, 14, tzinfo=UTC)
    lease = _lease(state=state, sandbox_id=sandbox_id)
    claim = LeaseStateClaim(
        state=state,
        sandbox_id=sandbox_id,
        token_hash=None,
        worker_generation="generation-a",
    )

    assert repository.mark_lost(lease, claim=claim, now=now)
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.failure_code == "sandbox_lost"
    assert lease.updated_at == now

    successor = _lease(
        state=state,
        sandbox_id=sandbox_id,
        worker_generation="generation-successor",
    )
    before = _state(successor)
    assert not repository.mark_lost(successor, claim=claim, now=now)
    assert _state(successor) == before


def test_inactive_snapshot_clear_uses_deleted_snapshot_id_not_generation():
    repository = ChatSandboxStateRepository(_settings())
    lease = _lease(
        snapshot_id="snapshot-deleted",
        snapshot_image_version="im-old",
        worker_generation="generation-successor",
    )

    assert repository.clear_inactive_snapshot(
        lease,
        claim=SnapshotClaim(snapshot_id="snapshot-deleted"),
    )
    assert lease.workspace_snapshot_id is None
    assert lease.snapshot_image_version is None
    assert lease.snapshot_updated_at is None
    assert lease.worker_generation == "generation-successor"

    lease.workspace_snapshot_id = "snapshot-current"
    lease.snapshot_image_version = "im-current"
    before = _state(lease)
    assert not repository.clear_inactive_snapshot(
        lease,
        claim=SnapshotClaim(snapshot_id="snapshot-deleted"),
    )
    assert _state(lease) == before
