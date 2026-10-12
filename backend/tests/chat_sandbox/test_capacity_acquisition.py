from __future__ import annotations

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnLatency,
)
from backend.services.chat_sandbox_acquisition_coordinator import (
    LeaseReused,
    PoolAcquired,
    SandboxCreated,
    legacy_ensure_ready_result,
)
from backend.services.chat_sandbox_capacity_repository import (
    CapacityUnavailable,
    ChatSandboxCapacityRepository,
    EvictionRequired,
    LeaseDecisionChanged,
    RecoveryRequired,
    ReuseLease,
    StartAcquired,
    StartEligible,
    WaitForLease,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.tests.chat_sandbox.capacity_harness import (
    _Provider,
    _database,
    _lease,
    _manager,
    _session,
    _settings,
    _spend_settings,
)


def _file_database(path):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    ChatSession.__table__.create(engine)
    ChatSandboxPool.__table__.create(engine)
    ChatSandboxLease.__table__.create(engine)
    ChatSandboxBudgetState.__table__.create(engine)
    ChatSandboxComputeInterval.__table__.create(engine)
    ChatSandboxCircuitEvent.__table__.create(engine)
    ChatTurnLatency.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _pool(settings: Settings, *, state: str) -> ChatSandboxPool:
    now = datetime.now(UTC)
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=f"sb-pool-{uuid.uuid4()}" if state != "starting" else None,
        state=state,
        image_version=settings.chat_modal_image_version,
        worker_contract_version=settings.chat_worker_contract_version,
        worker_generation=f"generation-{uuid.uuid4()}",
        app_release_id=settings.release_id,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        updated_at=now,
        cpu_request=settings.chat_sandbox_cpu,
        cpu_limit=settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu,
        memory_request_mib=settings.chat_sandbox_memory_mib,
        memory_limit_mib=(
            settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
        ),
        billing_month=now.date().replace(day=1),
    )


def _selection_case(
    case_id, state, has_sandbox, compatible, token_hash, expiry_seconds, outcome
):
    return pytest.param(
        state,
        has_sandbox,
        compatible,
        token_hash,
        expiry_seconds,
        outcome,
        id=case_id,
    )


_SELECTION_CASES = [
    _selection_case("ready-reuse", "ready", True, True, None, None, ReuseLease),
    _selection_case("idle-reuse", "idle", True, True, None, None, ReuseLease),
    _selection_case("busy-reuse", "busy", True, True, None, None, ReuseLease),
    _selection_case("ready-lost", "ready", False, True, None, None, StartEligible),
    _selection_case("idle-lost", "idle", False, True, None, None, StartEligible),
    _selection_case("busy-lost", "busy", False, True, None, None, StartEligible),
    _selection_case(
        "starting-owned", "starting", False, True, "owner", 30, WaitForLease
    ),
    _selection_case(
        "terminating-owned", "terminating", True, True, "owner", 30, WaitForLease
    ),
    _selection_case(
        "starting-owned-with-id", "starting", True, True, "owner", 30, WaitForLease
    ),
    _selection_case(
        "terminating-owned-lost",
        "terminating",
        False,
        True,
        "owner",
        30,
        StartEligible,
    ),
    _selection_case(
        "starting-expired", "starting", False, True, "owner", -1, StartEligible
    ),
    _selection_case(
        "starting-tokenless", "starting", False, True, None, 30, StartEligible
    ),
    _selection_case(
        "starting-no-expiry", "starting", False, True, "owner", None, StartEligible
    ),
    _selection_case(
        "terminating-expired-lost",
        "terminating",
        False,
        True,
        "owner",
        -1,
        StartEligible,
    ),
    _selection_case(
        "terminating-tokenless-lost",
        "terminating",
        False,
        True,
        None,
        30,
        StartEligible,
    ),
    _selection_case(
        "terminating-no-expiry-lost",
        "terminating",
        False,
        True,
        "owner",
        None,
        StartEligible,
    ),
    _selection_case(
        "starting-expired-id",
        "starting",
        True,
        True,
        "owner",
        -1,
        RecoveryRequired,
    ),
    _selection_case(
        "starting-tokenless-id", "starting", True, True, None, 30, RecoveryRequired
    ),
    _selection_case(
        "starting-no-expiry-id",
        "starting",
        True,
        True,
        "owner",
        None,
        RecoveryRequired,
    ),
    _selection_case(
        "terminating-expired-id",
        "terminating",
        True,
        True,
        "owner",
        -1,
        RecoveryRequired,
    ),
    _selection_case(
        "terminating-tokenless-id",
        "terminating",
        True,
        True,
        None,
        30,
        RecoveryRequired,
    ),
    _selection_case(
        "terminating-no-expiry-id",
        "terminating",
        True,
        True,
        "owner",
        None,
        RecoveryRequired,
    ),
    *[
        _selection_case(
            f"{state}-incompatible",
            state,
            True,
            False,
            None,
            None,
            RecoveryRequired,
        )
        for state in ("ready", "idle", "busy")
    ],
    _selection_case(
        "starting-incompatible-id",
        "starting",
        True,
        False,
        "owner",
        30,
        RecoveryRequired,
    ),
    _selection_case(
        "terminating-incompatible-id",
        "terminating",
        True,
        False,
        "owner",
        30,
        RecoveryRequired,
    ),
    _selection_case(
        "starting-incompatible-owned",
        "starting",
        False,
        False,
        "owner",
        30,
        WaitForLease,
    ),
    _selection_case(
        "terminated-start", "terminated", False, True, None, None, StartEligible
    ),
    _selection_case("failed-start", "failed", False, True, None, None, StartEligible),
    _selection_case(
        "terminated-stale", "terminated", True, True, None, None, RecoveryRequired
    ),
    _selection_case("failed-stale", "failed", True, True, None, None, RecoveryRequired),
]


@pytest.mark.parametrize(
    (
        "state",
        "has_sandbox",
        "compatible",
        "token_hash",
        "expiry_seconds",
        "expected_type",
    ),
    _SELECTION_CASES,
)
def test_repository_selection_covers_every_lease_state_without_fallthrough(
    state,
    has_sandbox,
    compatible,
    token_hash,
    expiry_seconds,
    expected_type,
):
    settings = _settings()
    now = datetime.now(UTC)
    lease = _lease(
        settings,
        uuid.uuid4(),
        state=state,
        sandbox_id="sb-existing" if has_sandbox else None,
        token_hash=token_hash,
        expires_at=(
            None if expiry_seconds is None else now + timedelta(seconds=expiry_seconds)
        ),
        worker_generation="generation-existing",
    )
    if not compatible:
        lease.image_version = "im-incompatible"
    before = (
        lease.state,
        lease.modal_sandbox_id,
        lease.lease_token_hash,
        lease.lease_expires_at,
        lease.worker_generation,
    )
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_kwargs: lease,
    )

    decision = repository.select(
        object(),
        lease.chat_session_id,
        now=now,
        ready_timeout_seconds=2,
    )

    assert isinstance(decision, expected_type)
    if isinstance(decision, ReuseLease):
        assert decision.sandbox_id == "sb-existing"
        assert decision.worker_generation == "generation-existing"
    elif isinstance(decision, WaitForLease):
        assert decision.state == state
    elif isinstance(decision, RecoveryRequired):
        assert decision.claim.sandbox_id == "sb-existing"
        assert decision.claim.worker_generation == "generation-existing"
        assert lease.state == "terminating"
        assert lease.lease_token_hash == decision.claim.token_hash
        assert lease.lease_expires_at == now + timedelta(seconds=17)
        return
    assert (
        lease.state,
        lease.modal_sandbox_id,
        lease.lease_token_hash,
        lease.lease_expires_at,
        lease.worker_generation,
    ) == before


def test_repository_missing_lease_is_start_eligible_without_mutation():
    settings = _settings()
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_kwargs: None,
    )

    decision = repository.select(
        object(),
        uuid.uuid4(),
        now=datetime.now(UTC),
        ready_timeout_seconds=2,
    )

    assert decision == StartEligible(expected=None)


@pytest.mark.parametrize(
    "mismatch",
    ["image", "contract", "egress", "generation"],
)
def test_each_compatibility_mismatch_requires_provider_recovery(mismatch):
    settings = _settings()
    lease = _lease(
        settings,
        uuid.uuid4(),
        state="ready",
        sandbox_id="sb-incompatible",
    )
    if mismatch == "image":
        lease.image_version = "im-old"
    elif mismatch == "contract":
        lease.worker_contract_version = "worker-old"
    elif mismatch == "egress":
        lease.egress_policy_digest = "0" * 64
    else:
        lease.worker_generation = None
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_kwargs: lease,
    )

    decision = repository.select(
        object(),
        lease.chat_session_id,
        now=datetime.now(UTC),
        ready_timeout_seconds=2,
    )

    assert isinstance(decision, RecoveryRequired)
    assert decision.claim.sandbox_id == "sb-incompatible"


def test_repository_locks_capacity_then_session_then_lease_for_direct_spend():
    settings = _spend_settings()
    calls: list[object] = []
    session_id = uuid.uuid4()
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        capacity_locker=lambda _db, *, wait: calls.append(("capacity", wait)) or True,
        start_locker=lambda _db, candidate: calls.append(("session", candidate)),
        lease_loader=lambda _db, candidate, *, lock: calls.append(
            ("lease", candidate, lock)
        ),
    )

    assert repository.select(
        object(),
        session_id,
        now=datetime.now(UTC),
        ready_timeout_seconds=2,
    ) == StartEligible(expected=None)
    assert calls == [
        ("capacity", True),
        ("session", session_id),
        ("lease", session_id, True),
    ]


@pytest.mark.parametrize(
    ("state", "expected_type"),
    [
        ("starting", CapacityUnavailable),
        ("ready", CapacityUnavailable),
        ("busy", CapacityUnavailable),
        ("idle", EvictionRequired),
        ("terminating", CapacityUnavailable),
        ("terminated", StartEligible),
        ("failed", StartEligible),
    ],
)
def test_capacity_counts_exact_live_lease_states(state, expected_type):
    settings = _settings(
        chat_blank_pool_enabled=True,
        chat_sandbox_total_live_cap=1,
    )
    sessions = _database()
    target_id, other_id = uuid.uuid4(), uuid.uuid4()
    with sessions() as db, db.begin():
        db.add_all([_session(target_id), _session(other_id)])
        db.add(
            _lease(
                settings,
                other_id,
                state=state,
                sandbox_id="sb-other",
            )
        )
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
    )

    with sessions() as db, db.begin():
        decision = repository.select(
            db,
            target_id,
            now=datetime.now(UTC),
            ready_timeout_seconds=2,
        )

    assert isinstance(decision, expected_type)
    if isinstance(decision, EvictionRequired):
        assert decision.chat_session_id == other_id


@pytest.mark.parametrize(
    ("state", "expected_type"),
    [
        ("starting", CapacityUnavailable),
        ("blank_ready", CapacityUnavailable),
        ("draining", CapacityUnavailable),
        ("claimed", StartEligible),
        ("terminated", StartEligible),
        ("failed", StartEligible),
    ],
)
def test_capacity_counts_exact_live_pool_states(state, expected_type):
    settings = _settings(
        chat_blank_pool_enabled=True,
        chat_sandbox_total_live_cap=1,
    )
    sessions = _database()
    target_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(target_id))
        db.add(_pool(settings, state=state))
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
    )

    with sessions() as db, db.begin():
        decision = repository.select(
            db,
            target_id,
            now=datetime.now(UTC),
            ready_timeout_seconds=2,
        )

    assert isinstance(decision, expected_type)


def test_capacity_selects_oldest_idle_and_never_evicts_target():
    settings = _settings(
        chat_blank_pool_enabled=True,
        chat_sandbox_total_live_cap=2,
    )
    sessions = _database()
    target_id, oldest_id, newest_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    with sessions() as db, db.begin():
        db.add_all([_session(target_id), _session(oldest_id), _session(newest_id)])
        db.add_all(
            [
                _lease(
                    settings,
                    target_id,
                    state="failed",
                    sandbox_id=None,
                    last_activity_at=now - timedelta(hours=1),
                ),
                _lease(
                    settings,
                    oldest_id,
                    state="idle",
                    sandbox_id="sb-oldest",
                    last_activity_at=now - timedelta(minutes=10),
                ),
                _lease(
                    settings,
                    newest_id,
                    state="idle",
                    sandbox_id="sb-newest",
                    last_activity_at=now - timedelta(minutes=1),
                ),
            ]
        )
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
    )

    with sessions() as db, db.begin():
        decision = repository.select(
            db,
            target_id,
            now=now,
            ready_timeout_seconds=2,
        )

    assert decision == EvictionRequired(chat_session_id=oldest_id)


def test_acquire_refuses_reservation_side_effect_that_changes_selected_state():
    settings = _settings()
    lease = _lease(
        settings,
        uuid.uuid4(),
        state="failed",
        sandbox_id=None,
    )
    repository = ChatSandboxCapacityRepository(
        settings,
        ChatSandboxStateRepository(settings),
        start_locker=lambda *_args: None,
        lease_loader=lambda *_args, **_kwargs: lease,
    )
    now = datetime.now(UTC)

    def change_selected_state(_worker_generation: str) -> uuid.UUID:
        lease.worker_generation = "generation-successor"
        return uuid.uuid4()

    with pytest.raises(LeaseDecisionChanged):
        repository.acquire(
            object(),
            lease.chat_session_id,
            creation_token="creation-token",
            worker_generation="generation-new",
            now=now,
            ready_timeout_seconds=2,
            reserve_interval=change_selected_state,
        )
    assert lease.state == "failed"
    assert lease.worker_generation == "generation-successor"


def test_created_acquisition_preserves_public_result_and_keeps_provider_io_outside_db():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    sandbox, elapsed_ms, created, outcome, pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox is provider.created
    assert isinstance(elapsed_ms, int)
    assert created is True
    assert outcome == "created"
    assert pool_lookup_ms is None
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == "create"
    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "ready"
    assert lease.modal_sandbox_id == "sb-created"
    assert lease.worker_generation == provider.calls[0][1]
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None


def test_production_cold_start_does_not_query_staging_qualification_profile():
    settings = _settings(environment="production")
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    qualification_queries: list[str] = []

    def record_qualification_query(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        if "chat_turn_latency" in statement:
            qualification_queries.append(statement)

    event.listen(
        sessions.kw["bind"], "before_cursor_execute", record_qualification_query
    )
    provider = _Provider(transactions=[])

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        _manager(settings, sessions, provider).ensure_ready(session_id)
    )

    assert sandbox is provider.created
    assert created is True
    assert outcome == "created"
    assert qualification_queries == []


def test_staging_qualification_cold_start_tags_latest_running_profile():
    settings = _settings(environment="staging")
    sessions = _database()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    now = datetime.now(UTC)
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        latency_defaults = {
            "chat_session_id": session_id,
            "traffic_class": "new_chat",
            "execution_backend": "modal_cli",
            "agent_harness": "pi",
            "acquisition_outcome": "pending",
            "model_route": "gpt-5.6-luna@openai",
            "app_release_id": settings.release_id,
            "terminal_status": "running",
            "updated_at": now,
        }
        db.add_all(
            [
                ChatTurnLatency(
                    turn_id=uuid.uuid4(),
                    request_id=uuid.uuid4(),
                    qualification_profile="100-immediate-admission",
                    admitted_at=now - timedelta(seconds=1),
                    **latency_defaults,
                ),
                ChatTurnLatency(
                    turn_id=turn_id,
                    request_id=uuid.uuid4(),
                    qualification_profile="32-functional-turns",
                    admitted_at=now,
                    **latency_defaults,
                ),
            ]
        )

    class TagCapturingProvider(_Provider):
        async def create(self, **options):
            self.tags = options["tags"]
            return await super().create(**options)

    provider = TagCapturingProvider(transactions=[])

    asyncio.run(_manager(settings, sessions, provider).ensure_ready(session_id))

    assert provider.tags["qualification_profile"] == "32-functional-turns"


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            PoolAcquired(
                sandbox="pool",
                elapsed_ms=11,
                pool_lookup_ms=3,
            ),
            ("pool", 11, False, "pool_hit", 3),
        ),
        (
            LeaseReused(
                sandbox="reuse",
                elapsed_ms=12,
                pool_lookup_ms=None,
            ),
            ("reuse", 12, False, "reused_session", None),
        ),
        (
            SandboxCreated(
                sandbox="created",
                elapsed_ms=13,
                after_pool_miss=False,
                pool_lookup_ms=None,
            ),
            ("created", 13, True, "created", None),
        ),
        (
            SandboxCreated(
                sandbox="miss",
                elapsed_ms=14,
                after_pool_miss=True,
                pool_lookup_ms=4,
            ),
            ("miss", 14, True, "pool_miss", 4),
        ),
    ],
)
def test_typed_acquisition_outcomes_preserve_exact_legacy_result(outcome, expected):
    assert legacy_ensure_ready_result(outcome) == expected


def test_concurrent_first_start_has_one_claim_reservation_and_provider(tmp_path):
    settings = _spend_settings(chat_sandbox_ready_timeout_seconds=2)
    sessions = _file_database(tmp_path / "capacity.db")
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        ChatSandboxSpendService(db, settings).assert_available()

    capacity_lock = threading.Lock()

    def lock_capacity_for_test(db, *, wait):
        assert wait is True
        capacity_lock.acquire()
        db.info["capacity_lock_held"] = True
        return True

    def release_capacity_lock(db, transaction):
        if transaction.parent is None and db.info.pop("capacity_lock_held", False):
            capacity_lock.release()

    event.listen(sessions.class_, "after_transaction_end", release_capacity_lock)
    state_repository = ChatSandboxStateRepository(settings)

    class CountingRepository(ChatSandboxCapacityRepository):
        def __init__(self):
            super().__init__(
                settings,
                state_repository,
                capacity_locker=lock_capacity_for_test,
                start_locker=lambda *_args: None,
            )
            self.claim_calls = 0
            self.claim_lock = threading.Lock()
            self.claim_observations: list[tuple[bool, str, str | None]] = []

        def acquire(self, *args, **kwargs):
            db = args[0]
            reserve_interval = kwargs["reserve_interval"]

            def observe_reservation(generation):
                interval_id = reserve_interval(generation)
                interval = db.get(ChatSandboxComputeInterval, interval_id)
                self.claim_observations.append(
                    (
                        db.in_transaction(),
                        interval.worker_generation,
                        interval.modal_sandbox_id,
                    )
                )
                return interval_id

            kwargs["reserve_interval"] = observe_reservation
            outcome = super().acquire(*args, **kwargs)
            if not isinstance(outcome, StartAcquired):
                return outcome
            with self.claim_lock:
                self.claim_calls += 1
            return outcome

    repository = CountingRepository()

    class ConcurrentProvider:
        def __init__(self):
            self.create_calls = 0
            self.create_lock = threading.Lock()
            self.creation_started = threading.Event()
            self.allow_creation = threading.Event()
            self.sandbox = SimpleNamespace(object_id="sb-concurrent")

        async def create(self, **options):
            with self.create_lock:
                self.create_calls += 1
            with sessions() as db:
                interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
            assert interval.worker_generation == options["worker_generation"]
            assert interval.provider_created_at is None
            self.creation_started.set()
            while not self.allow_creation.is_set():
                await asyncio.sleep(0.01)
            return self.sandbox

        async def resolve(self, sandbox_id):
            assert sandbox_id == "sb-concurrent"
            return self.sandbox

        async def poll(self, sandbox):
            assert sandbox is self.sandbox
            return None

        async def health(self, sandbox, **_options):
            assert sandbox is self.sandbox
            return True

        async def terminate(self, *_args, **_kwargs):
            raise AssertionError("the single owned provider must not be terminated")

    provider = ConcurrentProvider()
    manager = SandboxSessionManager(
        settings,
        session_factory=sessions,
        sandbox_provider=provider,
        state_repository=state_repository,
        capacity_repository=repository,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        assert provider.creation_started.wait(timeout=2)
        waiter = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        provider.allow_creation.set()
        owner_result = owner.result(timeout=3)
        waiter_result = waiter.result(timeout=3)

    assert repository.claim_calls == 1
    assert len(repository.claim_observations) == 1
    in_transaction, reserved_generation, reserved_sandbox_id = (
        repository.claim_observations[0]
    )
    assert in_transaction is True
    assert reserved_generation
    assert reserved_sandbox_id is None
    assert provider.create_calls == 1
    assert {owner_result[2], waiter_result[2]} == {True, False}
    assert {owner_result[3], waiter_result[3]} == {"created", "reused_session"}
    with sessions() as db:
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        lease = db.get(ChatSandboxLease, session_id)
    assert len(intervals) == 1
    assert intervals[0].worker_generation == reserved_generation
    assert intervals[0].worker_generation == lease.worker_generation
    assert intervals[0].modal_sandbox_id == "sb-concurrent"
    assert lease.state == "ready"
    assert lease.modal_sandbox_id == "sb-concurrent"


def test_reused_acquisition_preserves_public_result_and_uses_exact_generation():
    settings = _settings()
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
    manager = _manager(settings, sessions, provider)

    sandbox, elapsed_ms, created, outcome, pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox.object_id == "sb-reused"
    assert isinstance(elapsed_ms, int)
    assert created is False
    assert outcome == "reused_session"
    assert pool_lookup_ms is None
    assert provider.calls == [
        ("resolve", "sb-reused"),
        ("poll", "sb-reused"),
        ("health", "sb-reused", "generation-reused"),
    ]


@pytest.mark.parametrize(
    ("state", "expected_code", "expected_message"),
    [
        (
            "starting",
            "sandbox_timeout",
            "Secure workspace startup timed out",
        ),
        (
            "terminating",
            "sandbox_capacity",
            "Secure workspace capacity is temporarily full",
        ),
    ],
)
def test_owned_in_flight_acquisition_uses_stable_public_error(
    state, expected_code, expected_message
):
    settings = _settings(chat_sandbox_ready_timeout_seconds=0.05)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state=state,
                sandbox_id=("sb-terminating" if state == "terminating" else None),
                token_hash="owned-token",
                expires_at=datetime.now(UTC) + timedelta(seconds=30),
            )
        )
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == expected_code
    assert str(exc_info.value) == expected_message
    assert exc_info.value.uncertain is False
    assert provider.calls == []


def test_confirmed_expired_termination_recovery_finishes_then_creates():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="terminating",
                sandbox_id="sb-expired",
                token_hash="expired-owner",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
                worker_generation="generation-expired",
            )
        )
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        manager.ensure_ready(session_id)
    )

    assert sandbox is provider.created
    assert created is True
    assert outcome == "created"
    assert [call[0] for call in provider.calls] == ["terminate", "create"]
    assert provider.calls[0][1] == "sb-expired"
    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "ready"
    assert lease.modal_sandbox_id == "sb-created"
    assert lease.worker_generation != "generation-expired"


def test_unconfirmed_recovery_stays_capacity_counted_without_new_reservation():
    settings = _spend_settings(chat_sandbox_ready_timeout_seconds=0.05)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="terminating",
                sandbox_id="sb-uncertain",
                token_hash="expired-owner",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
                worker_generation="generation-uncertain",
            )
        )
        spend = ChatSandboxSpendService(db, settings)
        interval_id = spend.reserve_interval(
            origin="direct",
            worker_generation="generation-uncertain",
            chat_session_id=session_id,
        )
        spend.provider_created(interval_id, "sb-uncertain")

    class UnconfirmedProvider(_Provider):
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
    assert [call[0] for call in provider.calls] == ["terminate"]
    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-uncertain"
    assert lease.worker_generation == "generation-uncertain"
    assert lease.lease_token_hash != "expired-owner"
    assert lease.lease_expires_at is not None
    assert len(intervals) == 1
    assert intervals[0].id == interval_id
    assert intervals[0].modal_sandbox_id == "sb-uncertain"
    assert intervals[0].terminal_at is None
    assert intervals[0].reconciliation_state == "termination_uncertain"


def test_capacity_unavailable_preserves_exact_public_error():
    settings = _settings(
        chat_blank_pool_enabled=True,
        chat_sandbox_total_live_cap=1,
    )
    sessions = _database()
    target_id, busy_id = uuid.uuid4(), uuid.uuid4()
    with sessions() as db, db.begin():
        db.add_all([_session(target_id), _session(busy_id)])
        db.add(
            _lease(
                settings,
                busy_id,
                state="busy",
                sandbox_id="sb-busy",
            )
        )
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(target_id))

    assert exc_info.value.code == "sandbox_capacity"
    assert str(exc_info.value) == "Secure workspace capacity is temporarily full"
    assert exc_info.value.uncertain is False
    assert provider.calls == []


def test_budget_rejection_persists_circuit_trip_without_mutating_existing_lease():
    settings = _spend_settings(
        chat_sandbox_warning_microusd=1,
        chat_sandbox_application_cap_microusd=1,
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
                worker_generation="generation-before-rejection",
                snapshot_id="snapshot-before-rejection",
            )
        )
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "chat_temporarily_disabled"
    assert str(exc_info.value) == "Chat is temporarily disabled"
    assert provider.calls == []
    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        budget = db.execute(select(ChatSandboxBudgetState)).scalar_one()
        intervals = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
    assert lease.state == "terminated"
    assert lease.modal_sandbox_id is None
    assert lease.worker_generation == "generation-before-rejection"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
    assert lease.workspace_snapshot_id == "snapshot-before-rejection"
    assert budget.circuit_state == "tripped"
    assert budget.trip_reason == "safety_reserve"
    assert intervals == []


def test_spend_enforced_direct_start_locks_capacity_before_session():
    settings = _spend_settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = _Provider(transactions=[])
    locks: list[str] = []
    manager = _manager(
        settings,
        sessions,
        provider,
        capacity_locker=lambda *_args, **_kwargs: locks.append("capacity") or True,
        start_locker=lambda *_args: locks.append("session"),
    )

    asyncio.run(manager.ensure_ready(session_id))

    assert locks[:2] == ["capacity", "session"]


def test_full_capacity_evicts_oldest_idle_before_creating():
    settings = _settings(
        chat_blank_pool_enabled=True,
        chat_sandbox_total_live_cap=2,
        chat_sandbox_max_warm=10,
    )
    sessions = _database()
    target_id, oldest_id, newest_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    with sessions() as db, db.begin():
        db.add_all([_session(target_id), _session(oldest_id), _session(newest_id)])
        db.add_all(
            [
                _lease(
                    settings,
                    oldest_id,
                    state="idle",
                    sandbox_id="sb-oldest",
                    worker_generation="generation-oldest",
                    last_activity_at=now - timedelta(minutes=10),
                ),
                _lease(
                    settings,
                    newest_id,
                    state="idle",
                    sandbox_id="sb-newest",
                    worker_generation="generation-newest",
                    last_activity_at=now - timedelta(minutes=1),
                ),
            ]
        )
    provider = _Provider(transactions=[])
    manager = _manager(settings, sessions, provider)

    sandbox, _elapsed_ms, created, outcome, _pool_lookup_ms = asyncio.run(
        manager.ensure_ready(target_id)
    )

    assert sandbox is provider.created
    assert created is True
    assert outcome == "created"
    assert [call[0] for call in provider.calls] == ["terminate", "create"]
    assert provider.calls[0][1] == "sb-oldest"
    with sessions() as db:
        oldest = db.get(ChatSandboxLease, oldest_id)
        newest = db.get(ChatSandboxLease, newest_id)
        target = db.get(ChatSandboxLease, target_id)
    assert oldest.state == "terminated"
    assert oldest.modal_sandbox_id is None
    assert newest.state == "idle"
    assert newest.modal_sandbox_id == "sb-newest"
    assert target.state == "ready"
    assert target.modal_sandbox_id == "sb-created"
