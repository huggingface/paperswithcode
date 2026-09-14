import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
)
from backend.services import chat_sandbox_spend_reconciler as reconciler_module
from backend.services import chat_sandbox_spend_service as spend_service_module
from backend.services.chat_sandbox_pool_repository import (
    MODAL_CPU_USD_PER_CORE_SECOND,
    MODAL_MEMORY_USD_PER_GIB_SECOND,
    ChatSandboxPoolRepository,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_reconciler import (
    ChatSandboxSpendReconciler,
    ProviderReconciliationOutcome,
)
from backend.services.chat_sandbox_spend_reporter import (
    ModalProviderSpendReporter,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)


def session_factory():
    engine = create_engine(
        "sqlite://",
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
    ):
        table.create(engine, checkfirst=True)
    return sessionmaker(engine, expire_on_commit=False)


def settings(**values) -> Settings:
    return Settings(
        **{
            "environment": "staging",
            "release_id": "release",
            "chat_modal_image_version": "im-test",
            "chat_sandbox_modal_environment": "pwc-chat-staging",
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
            **values,
        }
    )


class Reporter:
    def __init__(self, configured: Settings, result: int = 0, handler=None):
        self.settings = configured
        self.result = result
        self.handler = handler
        self.calls: list[tuple[datetime, datetime]] = []

    async def month_to_date_microusd(self, *, start, end) -> int:
        self.calls.append((start, end))
        if self.handler is not None:
            value = self.handler()
            if asyncio.iscoroutine(value):
                await value
        return self.result


class FailingSessionFactory:
    def __init__(self, sessions, fail_at: int):
        self.sessions = sessions
        self.fail_at = fail_at
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("database unavailable")
        return self.sessions()


def pool_row(
    configured: Settings,
    now: datetime,
    *,
    state: str,
    billing_month=None,
    cpu_request: float = 1,
    memory_request_mib: int = 1024,
    cost: float = 0,
) -> ChatSandboxPool:
    return ChatSandboxPool(
        id=uuid.uuid4(),
        modal_sandbox_id=f"sb-{uuid.uuid4()}",
        state=state,
        image_version=configured.chat_modal_image_version,
        worker_contract_version=configured.chat_worker_contract_version,
        worker_generation=uuid.uuid4().hex,
        app_release_id=configured.release_id,
        created_at=now - timedelta(seconds=10),
        ready_at=now - timedelta(seconds=5),
        expires_at=now + timedelta(hours=1),
        updated_at=now,
        cpu_request=cpu_request,
        cpu_limit=max(cpu_request, configured.chat_sandbox_cpu_limit),
        memory_request_mib=memory_request_mib,
        memory_limit_mib=max(
            memory_request_mib,
            configured.chat_sandbox_memory_limit_mib,
        ),
        estimated_blank_cost_usd=cost,
        billing_month=billing_month or now.date().replace(day=1),
    )


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def budget_states(sessions) -> list[ChatSandboxBudgetState]:
    with sessions() as db:
        return list(
            db.execute(
                select(ChatSandboxBudgetState).order_by(
                    ChatSandboxBudgetState.billing_cycle
                )
            ).scalars()
        )


def test_disabled_pool_budget_status_preserves_legacy_projection_and_cost_updates():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    configured = settings(
        chat_sandbox_spend_enforcement_enabled=False,
        chat_blank_pool_min=2,
        chat_blank_pool_monthly_budget_usd=1_000,
        chat_blank_pool_reported_month_to_date_usd=0,
        chat_sandbox_cpu=4,
        chat_sandbox_memory_mib=4096,
    )
    live = pool_row(
        configured,
        now,
        state="starting",
        cpu_request=2,
        memory_request_mib=1024,
        cost=99,
    )
    terminal = pool_row(configured, now, state="claimed", cost=3.25)
    terminal.blank_billable_seconds = 77
    prior_month = pool_row(
        configured,
        now,
        state="blank_ready",
        billing_month=datetime(2026, 7, 1, tzinfo=UTC).date(),
        cost=8.5,
    )
    with sessions() as db, db.begin():
        db.add_all([live, terminal, prior_month])

    transaction_starts = []

    def record_transaction(_db, transaction, _connection):
        if transaction.parent is None:
            transaction_starts.append(transaction)

    event.listen(sessions.class_, "after_begin", record_transaction)
    clock_calls = []

    def clock():
        clock_calls.append(now)
        return now

    capacity_calls = []
    pool_repository = ChatSandboxPoolRepository(
        configured,
        capacity_locker=lambda *_args, **_kwargs: capacity_calls.append(True),
    )
    reporter = Reporter(configured, handler=lambda: pytest.fail("reporter called"))
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        pool_repository=pool_repository,
        utcnow=clock,
    )

    status = reconciler.pool_budget_status()

    live_cost = 10 * (
        2 * MODAL_CPU_USD_PER_CORE_SECOND + MODAL_MEMORY_USD_PER_GIB_SECOND
    )
    accrued = live_cost + 3.25
    remaining_seconds = (datetime(2026, 9, 1, tzinfo=UTC) - now).total_seconds()
    projected = (
        accrued
        + remaining_seconds
        * (4 * MODAL_CPU_USD_PER_CORE_SECOND + 4 * MODAL_MEMORY_USD_PER_GIB_SECOND)
        * 2
    )
    assert status == {
        "billing_month": "2026-08-01",
        "accrued_usd": pytest.approx(accrued),
        "reported_usd": 0.0,
        "effective_accrued_usd": pytest.approx(accrued),
        "projected_usd": pytest.approx(projected),
        "budget_usd": 1_000.0,
        "within_budget": False,
    }
    assert list(status) == [
        "billing_month",
        "accrued_usd",
        "reported_usd",
        "effective_accrued_usd",
        "projected_usd",
        "budget_usd",
        "within_budget",
    ]
    assert clock_calls == [now]
    assert len(transaction_starts) == 1
    assert capacity_calls == []
    assert reporter.calls == []
    with sessions() as db:
        persisted_live = db.get(ChatSandboxPool, live.id)
        persisted_terminal = db.get(ChatSandboxPool, terminal.id)
        persisted_prior = db.get(ChatSandboxPool, prior_month.id)
        assert persisted_live.blank_billable_seconds == 10
        assert float(persisted_live.estimated_blank_cost_usd) == pytest.approx(
            live_cost,
            abs=1e-6,
        )
        assert persisted_terminal.blank_billable_seconds == 77
        assert float(persisted_terminal.estimated_blank_cost_usd) == 3.25
        assert float(persisted_prior.estimated_blank_cost_usd) == 8.5


def test_disabled_pool_budget_status_preserves_empty_sum_and_inclusive_floor():
    sessions = session_factory()
    now = datetime(2026, 12, 31, 23, tzinfo=UTC)
    configured = settings(
        chat_sandbox_spend_enforcement_enabled=False,
        chat_blank_pool_min=0,
        chat_blank_pool_reported_month_to_date_usd=5,
        chat_blank_pool_monthly_budget_usd=5,
    )
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured),
        utcnow=lambda: now,
    )

    status = reconciler.pool_budget_status()

    assert status == {
        "billing_month": "2026-12-01",
        "accrued_usd": 0,
        "reported_usd": 5.0,
        "effective_accrued_usd": 5.0,
        "projected_usd": 5.0,
        "budget_usd": 5.0,
        "within_budget": True,
    }
    assert type(status["accrued_usd"]) is int


def test_enforced_pool_budget_status_maps_spend_status_in_one_transaction(
    monkeypatch,
):
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    configured = settings()
    reporter = Reporter(configured, handler=lambda: pytest.fail("reporter called"))
    pool_repository = ChatSandboxPoolRepository(
        configured,
        capacity_locker=lambda *_args, **_kwargs: pytest.fail("pool lock called"),
    )
    clock_calls = []
    factory_calls = []
    status_calls = []

    def tracked_factory():
        factory_calls.append(True)
        return sessions()

    class StubSpendService:
        def __init__(self, db, service_settings):
            assert db.in_transaction()
            assert service_settings is configured

        def status(self, sampled_at):
            status_calls.append(sampled_at)
            return {
                "billing_cycle": "2026-08",
                "estimated_microusd": 1_250_000,
                "provider_floor_microusd": 2_500_000,
                "effective_microusd": 3_750_000,
                "outstanding_reservation_microusd": 4_250_000,
                "application_cap_microusd": 9_000_000,
                "circuit_state": "tripped",
            }

    monkeypatch.setattr(
        reconciler_module,
        "ChatSandboxSpendService",
        StubSpendService,
    )
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=tracked_factory,
        reporter=reporter,
        pool_repository=pool_repository,
        utcnow=lambda: clock_calls.append(now) or now,
    )

    status = reconciler.pool_budget_status()

    assert status == {
        "billing_month": "2026-08",
        "accrued_usd": 1.25,
        "reported_usd": 2.5,
        "effective_accrued_usd": 3.75,
        "projected_usd": 8.0,
        "budget_usd": 9.0,
        "within_budget": False,
    }
    assert factory_calls == [True]
    assert status_calls == [now]
    assert clock_calls == [now]
    assert reporter.calls == []


def test_enforced_pool_budget_status_commits_spend_status_and_propagates_db_errors():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    configured = settings()
    reporter = Reporter(configured)
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: now,
    )

    status = reconciler.pool_budget_status()

    assert status["billing_month"] == "2026-08-01"
    assert status["within_budget"] is True
    assert len(budget_states(sessions)) == 1
    failing = ChatSandboxSpendReconciler(
        configured,
        session_factory=FailingSessionFactory(sessions, fail_at=1),
        reporter=reporter,
        utcnow=lambda: now,
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        failing.pool_budget_status()
    assert reporter.calls == []


def test_modal_reporter_owns_exact_query_filter_and_rounding(monkeypatch):
    configured = settings()
    captured = []

    class Report:
        async def aio(self, **kwargs):
            captured.append(kwargs)
            return [
                SimpleNamespace(
                    description=MODAL_APP_NAME,
                    environment_name="main",
                    cost=Decimal("1.0000004"),
                ),
                SimpleNamespace(
                    description=MODAL_APP_NAME,
                    environment_name="pwc-chat-staging",
                    cost=Decimal("2.0000004"),
                ),
                SimpleNamespace(
                    description=MODAL_APP_NAME,
                    environment_name="another-environment",
                    cost=Decimal("4"),
                ),
                SimpleNamespace(
                    description="another-app",
                    environment_name="pwc-chat-staging",
                    cost=Decimal("8"),
                ),
            ]

    workspace = SimpleNamespace(billing=SimpleNamespace(report=Report()))
    monkeypatch.setattr(
        "backend.services.chat_sandbox_spend_reporter.modal.Workspace.from_context",
        lambda: workspace,
    )
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 10, 12, tzinfo=UTC)

    result = asyncio.run(
        ModalProviderSpendReporter(configured).month_to_date_microusd(
            start=start,
            end=end,
        )
    )

    assert result == 3_000_001
    assert captured == [{"start": start, "end": end, "resolution": "d"}]


def test_modal_reporter_uses_environment_billing_for_team_identity(monkeypatch):
    configured = settings(chat_sandbox_provider_mode="team_environments")
    captured = []

    class Report:
        async def aio(self, **kwargs):
            captured.append(kwargs)
            return [
                SimpleNamespace(
                    description=MODAL_APP_NAME,
                    cost=Decimal("1.2500004"),
                ),
                SimpleNamespace(description="another-app", cost=Decimal("8")),
            ]

    environment = SimpleNamespace(billing=SimpleNamespace(report=Report()))

    def from_name(name):
        assert name == configured.chat_sandbox_modal_environment
        return environment

    monkeypatch.setattr(
        "backend.services.chat_sandbox_spend_reporter.modal.Environment.from_name",
        from_name,
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_spend_reporter.modal.Workspace.from_context",
        lambda: pytest.fail("team reconciliation must not request workspace billing"),
    )
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 10, 12, tzinfo=UTC)

    result = asyncio.run(
        ModalProviderSpendReporter(configured).month_to_date_microusd(
            start=start,
            end=end,
        )
    )

    assert result == 1_250_000
    assert captured == [{"start": start, "end": end, "resolution": "d"}]


def test_reconciler_skips_inside_hour_without_calling_provider():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    with sessions() as db, db.begin():
        assert (
            ChatSandboxSpendService(db, configured).claim_provider_reconciliation_exact(
                now
            )
            is not None
        )
    reporter = Reporter(configured)
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: now + timedelta(minutes=59),
    )

    assert (
        asyncio.run(reconciler.reconcile_provider())
        is ProviderReconciliationOutcome.SKIPPED
    )
    assert reporter.calls == []


def test_success_observes_committed_claim_and_persists_provider_floor():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    observed_attempts = []

    def observe_claim():
        with sessions() as db:
            state = db.execute(select(ChatSandboxBudgetState)).scalar_one()
            observed_attempts.append(aware(state.last_reconciliation_attempt_at))

    reporter = Reporter(configured, result=12_345_678, handler=observe_claim)
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: now,
    )

    assert (
        asyncio.run(reconciler.reconcile_provider())
        is ProviderReconciliationOutcome.RECONCILED
    )
    assert reporter.calls == [(datetime(2026, 8, 1, tzinfo=UTC), now)]
    assert observed_attempts == [now]
    state = budget_states(sessions)[0]
    assert state.provider_floor_microusd == 12_345_678
    assert aware(state.last_reconciled_at) == now
    assert aware(state.last_reconciliation_attempt_at) == now
    assert state.reconciliation_state == "fresh"


def test_provider_error_marks_exact_claim_unavailable():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).reconcile_provider_floor(
            0, now - timedelta(hours=1)
        )

    def fail():
        raise RuntimeError("provider unavailable")

    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured, handler=fail),
        utcnow=lambda: now,
    )

    assert (
        asyncio.run(reconciler.reconcile_provider())
        is ProviderReconciliationOutcome.UNAVAILABLE
    )
    state = budget_states(sessions)[0]
    assert state.reconciliation_state == "unavailable"
    with sessions() as db:
        events = list(
            db.execute(
                select(ChatSandboxCircuitEvent).where(
                    ChatSandboxCircuitEvent.event_type == "reconciliation_unavailable"
                )
            ).scalars()
        )
    assert len(events) == 1


def test_cancellation_propagates_without_marking_unavailable():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).reconcile_provider_floor(
            0, now - timedelta(hours=1)
        )

    def cancel():
        raise asyncio.CancelledError

    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured, handler=cancel),
        utcnow=lambda: now,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reconciler.reconcile_provider())
    state = budget_states(sessions)[0]
    assert state.reconciliation_state == "fresh"
    assert aware(state.last_reconciliation_attempt_at) == now
    with sessions() as db:
        unavailable = db.scalar(
            select(ChatSandboxCircuitEvent.id).where(
                ChatSandboxCircuitEvent.event_type == "reconciliation_unavailable"
            )
        )
    assert unavailable is None


@pytest.mark.parametrize("provider_fails", [False, True])
def test_superseded_cross_cycle_completion_is_skipped_without_regression(
    provider_fails,
):
    sessions = session_factory()
    configured = settings()
    old_attempt = datetime(2026, 8, 31, 23, tzinfo=UTC)
    newer_attempt = datetime(2026, 9, 1, 0, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).reconcile_provider_floor(
            10, old_attempt - timedelta(hours=1)
        )

    def supersede():
        with sessions() as db, db.begin():
            claim = ChatSandboxSpendService(
                db, configured
            ).claim_provider_reconciliation_exact(newer_attempt)
            assert claim is not None
        with sessions() as db, db.begin():
            applied = ChatSandboxSpendService(
                db, configured
            ).reconcile_provider_floor_for_claim(claim, 20)
            assert applied is not None
        if provider_fails:
            raise RuntimeError("old provider attempt failed")

    reporter = Reporter(configured, result=999_999_999, handler=supersede)
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: old_attempt,
    )

    assert (
        asyncio.run(reconciler.reconcile_provider())
        is ProviderReconciliationOutcome.SKIPPED
    )
    august, september = budget_states(sessions)
    assert august.provider_floor_microusd == 10
    assert august.reconciliation_state == "fresh"
    assert september.provider_floor_microusd == 20
    assert september.reconciliation_state == "fresh"
    assert aware(september.last_reconciled_at) == newer_attempt


@pytest.mark.parametrize("provider_fails", [False, True])
def test_superseded_same_cycle_completion_is_skipped_without_regression(
    provider_fails,
):
    sessions = session_factory()
    configured = settings()
    old_attempt = datetime(2026, 8, 10, 12, tzinfo=UTC)
    newer_attempt = old_attempt + timedelta(hours=1)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).reconcile_provider_floor(
            10, old_attempt - timedelta(hours=1)
        )

    def supersede():
        with sessions() as db, db.begin():
            claim = ChatSandboxSpendService(
                db, configured
            ).claim_provider_reconciliation_exact(newer_attempt)
            assert claim is not None
        with sessions() as db, db.begin():
            applied = ChatSandboxSpendService(
                db, configured
            ).reconcile_provider_floor_for_claim(claim, 20)
            assert applied is not None
        if provider_fails:
            raise RuntimeError("old provider attempt failed")

    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured, result=999_999_999, handler=supersede),
        utcnow=lambda: old_attempt,
    )

    assert (
        asyncio.run(reconciler.reconcile_provider())
        is ProviderReconciliationOutcome.SKIPPED
    )
    state = budget_states(sessions)[0]
    assert state.provider_floor_microusd == 20
    assert state.reconciliation_state == "fresh"
    assert aware(state.last_reconciled_at) == newer_attempt
    assert aware(state.last_reconciliation_attempt_at) == newer_attempt


def test_newer_cycle_without_an_attempt_still_supersedes_old_claim():
    sessions = session_factory()
    configured = settings()
    august = datetime(2026, 8, 31, 23, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        service.reconcile_provider_floor(10, august - timedelta(hours=1))
        old_claim = service.claim_provider_reconciliation_exact(august)
        assert old_claim is not None
    with sessions() as db, db.begin():
        newer = ChatSandboxSpendService(db, configured).refresh(september)
        assert newer.last_reconciliation_attempt_at is None

    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        assert service.reconcile_provider_floor_for_claim(old_claim, 999) is None
        assert service.reconciliation_unavailable_for_claim(old_claim) is None

    august_state, september_state = budget_states(sessions)
    assert august_state.provider_floor_microusd == 10
    assert august_state.reconciliation_state == "fresh"
    assert september_state.last_reconciliation_attempt_at is None


def test_exact_hourly_claim_is_durable_across_sessions():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    with sessions() as db, db.begin():
        first = ChatSandboxSpendService(
            db, configured
        ).claim_provider_reconciliation_exact(now)
        assert first is not None
    with sessions() as db, db.begin():
        assert (
            ChatSandboxSpendService(db, configured).claim_provider_reconciliation_exact(
                now + timedelta(minutes=59)
            )
            is None
        )
    with sessions() as db, db.begin():
        second = ChatSandboxSpendService(
            db, configured
        ).claim_provider_reconciliation_exact(now + timedelta(hours=1))
        assert second is not None
    assert second.owner_state_id == first.owner_state_id
    assert second.attempted_at == now + timedelta(hours=1)


def test_prior_trip_failure_keeps_new_cycle_absent_then_success_rearms():
    sessions = session_factory()
    configured = settings()
    august = datetime(2026, 8, 31, 22, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        state = service.reconcile_provider_floor(100_000_000, august)
        assert state.circuit_state == "tripped"
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).record_kill_sweep(
            complete=True,
            now=august + timedelta(minutes=1),
        )

    def fail():
        raise RuntimeError("provider unavailable")

    reporter = Reporter(configured, handler=fail)
    unavailable = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: september,
    )
    assert (
        asyncio.run(unavailable.reconcile_provider())
        is ProviderReconciliationOutcome.UNAVAILABLE
    )
    assert [state.billing_cycle.isoformat() for state in budget_states(sessions)] == [
        "2026-08-01"
    ]
    assert budget_states(sessions)[0].circuit_state == "tripped"

    reporter.handler = None
    reporter.result = 0
    reconciled = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        utcnow=lambda: september + timedelta(hours=1),
    )
    assert (
        asyncio.run(reconciled.reconcile_provider())
        is ProviderReconciliationOutcome.RECONCILED
    )
    august_state, september_state = budget_states(sessions)
    assert august_state.circuit_state == "tripped"
    assert september_state.billing_cycle.isoformat() == "2026-09-01"
    assert september_state.circuit_state == "armed"
    assert aware(september_state.last_reconciliation_attempt_at) == (
        september + timedelta(hours=1)
    )
    with sessions() as db:
        rearmed = list(
            db.execute(
                select(ChatSandboxCircuitEvent).where(
                    ChatSandboxCircuitEvent.budget_state_id == september_state.id,
                    ChatSandboxCircuitEvent.event_type == "cycle_rearmed",
                )
            ).scalars()
        )
    assert len(rearmed) == 1


def test_unsafe_prior_trip_still_blocks_confirmed_new_cycle():
    sessions = session_factory()
    configured = settings()
    august = datetime(2026, 8, 31, 22, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).trip("accounting_integrity", august)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).record_kill_sweep(
            complete=True,
            now=august + timedelta(minutes=1),
        )
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured),
        utcnow=lambda: september,
    )

    with pytest.raises(ChatComputeDisabled):
        asyncio.run(reconciler.reconcile_provider())
    states = budget_states(sessions)
    assert len(states) == 1
    assert states[0].billing_cycle.isoformat() == "2026-08-01"
    assert states[0].circuit_state == "tripped"
    assert aware(states[0].last_reconciliation_attempt_at) == september


@pytest.mark.parametrize("blocker", ["missing_sweep", "unresolved", "policy"])
def test_confirmed_new_cycle_preserves_every_existing_rearm_gate(blocker):
    sessions = session_factory()
    original = settings()
    august = datetime(2026, 8, 31, 22, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, original).reconcile_provider_floor(
            100_000_000, august
        )
    if blocker != "missing_sweep":
        with sessions() as db, db.begin():
            ChatSandboxSpendService(db, original).record_kill_sweep(
                complete=True,
                now=august + timedelta(minutes=1),
            )
    if blocker == "unresolved":
        with sessions() as db, db.begin():
            db.add(
                ChatSandboxComputeInterval(
                    id=uuid.uuid4(),
                    modal_sandbox_id="sb-unresolved",
                    environment=original.environment,
                    modal_app="pwc-chat-sandbox-v1",
                    app_release_id=original.release_id,
                    image_version=original.chat_modal_image_version,
                    worker_generation="generation",
                    origin="direct",
                    cpu_request_millicores=1000,
                    cpu_limit_millicores=1000,
                    memory_request_mib=2048,
                    memory_limit_mib=2048,
                    reserved_at=august,
                    billing_cycle=august.date().replace(day=1),
                    reserved_microusd=0,
                    updated_at=august,
                )
            )
    configured = (
        settings(chat_sandbox_budget_attestation="changed")
        if blocker == "policy"
        else original
    )
    reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=Reporter(configured),
        utcnow=lambda: september,
    )

    with pytest.raises(ChatComputeDisabled):
        asyncio.run(reconciler.reconcile_provider())
    states = budget_states(sessions)
    assert len(states) == 1
    assert states[0].billing_cycle.isoformat() == "2026-08-01"
    assert states[0].circuit_state == "tripped"


def test_prior_claim_finalization_locks_capacity_then_only_exact_owner(monkeypatch):
    sessions = session_factory()
    configured = settings()
    august = datetime(2026, 8, 31, 22, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, configured).trip("application_cap", august)
    with sessions() as db, db.begin():
        claim = ChatSandboxSpendService(
            db, configured
        ).claim_provider_reconciliation_exact(september)
        assert claim is not None

    order = []
    locked_statements = []

    def record_capacity(_db, *, wait=True):
        assert wait
        order.append("capacity")
        return True

    def record_statement(_conn, clause, *_args, **_kwargs):
        if getattr(clause, "_for_update_arg", None) is not None:
            assert order == ["capacity"]
            order.append("owner")
            locked_statements.append(clause)

    monkeypatch.setattr(spend_service_module, "lock_capacity", record_capacity)
    engine = sessions.kw["bind"]
    event.listen(engine, "before_execute", record_statement)
    try:
        with sessions() as db, db.begin():
            finalized = ChatSandboxSpendService(
                db, configured
            ).reconciliation_unavailable_for_claim(claim)
            assert finalized is not None
    finally:
        event.remove(engine, "before_execute", record_statement)

    assert order == ["capacity", "owner"]
    assert len(locked_statements) == 1
    sql = str(locked_statements[0].compile(dialect=postgresql.dialect()))
    assert "chat_sandbox_budget_states.id =" in sql
    assert "chat_sandbox_budget_states.environment =" in sql
    assert sql.endswith("FOR UPDATE")


def test_database_failures_propagate_without_provider_misclassification():
    sessions = session_factory()
    configured = settings()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)

    reporter = Reporter(configured)
    claim_failure = ChatSandboxSpendReconciler(
        configured,
        session_factory=FailingSessionFactory(sessions, fail_at=1),
        reporter=reporter,
        utcnow=lambda: now,
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(claim_failure.reconcile_provider())
    assert reporter.calls == []

    success_reporter = Reporter(configured)
    success_failure = ChatSandboxSpendReconciler(
        configured,
        session_factory=FailingSessionFactory(sessions, fail_at=2),
        reporter=success_reporter,
        utcnow=lambda: now,
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(success_failure.reconcile_provider())
    assert len(success_reporter.calls) == 1

    later = now + timedelta(hours=1)

    def provider_error():
        raise RuntimeError("provider unavailable")

    unavailable_failure = ChatSandboxSpendReconciler(
        configured,
        session_factory=FailingSessionFactory(sessions, fail_at=2),
        reporter=Reporter(configured, handler=provider_error),
        utcnow=lambda: later,
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(unavailable_failure.reconcile_provider())


def test_manager_maps_only_reconciled_to_true_and_validates_dependencies():
    sessions = session_factory()
    configured = settings()
    reporter = Reporter(configured)

    class SequencedReconciler(ChatSandboxSpendReconciler):
        def __init__(self, outcomes, **kwargs):
            super().__init__(**kwargs)
            self.outcomes = iter(outcomes)

        async def reconcile_provider(self):
            return next(self.outcomes)

    reconciler = SequencedReconciler(
        [
            ProviderReconciliationOutcome.SKIPPED,
            ProviderReconciliationOutcome.RECONCILED,
            ProviderReconciliationOutcome.UNAVAILABLE,
        ],
        settings=configured,
        session_factory=sessions,
        reporter=reporter,
    )
    manager = SandboxSessionManager(
        configured,
        session_factory=sessions,
        spend_reporter=reporter,
        spend_reconciler=reconciler,
    )
    assert [
        asyncio.run(manager.reconcile_spend_provider()),
        asyncio.run(manager.reconcile_spend_provider()),
        asyncio.run(manager.reconcile_spend_provider()),
    ] == [False, True, False]
    assert manager._spend_reconciler() is reconciler

    other_settings = settings()
    with pytest.raises(ValueError, match="reporter settings must be shared"):
        ChatSandboxSpendReconciler(
            configured,
            session_factory=sessions,
            reporter=Reporter(other_settings),
        )
    with pytest.raises(ValueError, match="reconciler settings must be shared"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            spend_reconciler=ChatSandboxSpendReconciler(
                other_settings,
                session_factory=sessions,
                reporter=Reporter(other_settings),
            ),
        )
    other_sessions = session_factory()
    with pytest.raises(ValueError, match="reconciler sessions must be shared"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            spend_reconciler=ChatSandboxSpendReconciler(
                configured,
                session_factory=other_sessions,
                reporter=Reporter(configured),
            ),
        )
    with pytest.raises(ValueError, match="reconciler reporter must be shared"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            spend_reporter=Reporter(configured),
            spend_reconciler=ChatSandboxSpendReconciler(
                configured,
                session_factory=sessions,
                reporter=Reporter(configured),
            ),
        )

    lazy = SandboxSessionManager(configured, session_factory=sessions)
    component = lazy._spend_reconciler()
    assert component.settings is configured
    assert component.session_factory is sessions
    assert component.reporter is lazy._spend_reporter()
    assert component.pool_repository is lazy._pool_repository()

    shared_pool = ChatSandboxPoolRepository(
        configured,
        capacity_locker=lambda *_args, **_kwargs: True,
    )
    shared_reconciler = ChatSandboxSpendReconciler(
        configured,
        session_factory=sessions,
        reporter=reporter,
        pool_repository=shared_pool,
    )
    composed = SandboxSessionManager(
        configured,
        session_factory=sessions,
        spend_reconciler=shared_reconciler,
    )
    assert composed._pool_repository() is shared_pool
    assert composed._spend_reporter() is reporter
    delegated_status = {
        "billing_month": "delegated",
        "accrued_usd": 0.0,
        "reported_usd": 0.0,
        "effective_accrued_usd": 0.0,
        "projected_usd": 0.0,
        "budget_usd": 0.0,
        "within_budget": True,
    }
    shared_reconciler.pool_budget_status = lambda: delegated_status
    assert composed.pool_budget_status() is delegated_status

    different_pool = ChatSandboxPoolRepository(
        configured,
        capacity_locker=lambda *_args, **_kwargs: True,
    )
    with pytest.raises(ValueError, match="reconciler pool repository"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            pool_repository=different_pool,
            spend_reconciler=shared_reconciler,
        )
    wrong_settings_pool = ChatSandboxPoolRepository(
        other_settings,
        capacity_locker=lambda *_args, **_kwargs: True,
    )
    with pytest.raises(ValueError, match="Pool repository settings"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            pool_repository=wrong_settings_pool,
        )
    with pytest.raises(ValueError, match="Spend pool repository settings"):
        ChatSandboxSpendReconciler(
            configured,
            session_factory=sessions,
            reporter=reporter,
            pool_repository=wrong_settings_pool,
        )
