import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_alert_dispatcher import (
    WEBHOOK_TIMEOUT_SECONDS,
    ChatSandboxSpendAlertDispatcher,
    SpendAlertChannel,
)


def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChatSandboxBudgetState.__table__.create(engine, checkfirst=True)
    ChatSandboxCircuitEvent.__table__.create(engine, checkfirst=True)
    return sessionmaker(engine, expire_on_commit=False)


def settings(environment: str = "staging", **values: Any) -> Settings:
    return Settings(
        **{
            "environment": environment,
            "release_id": "release",
            "chat_sandbox_slack_webhook_url": "https://primary.test/hook",
            "chat_sandbox_alert_fallback_webhook_url": "https://fallback.test/hook",
            "chat_sandbox_runbook_url": "https://runbook.test/chat",
            **values,
        }
    )


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


class RecordingPoster:
    def __init__(self, handler=None):
        self.calls: list[tuple[str, dict[str, str], float]] = []
        self.handler = handler

    async def post_json(self, url, payload, *, timeout_seconds):
        self.calls.append((url, dict(payload), timeout_seconds))
        if self.handler is not None:
            result = self.handler(url, payload)
            if asyncio.iscoroutine(result):
                await result


def add_event(
    sessions,
    *,
    environment: str = "staging",
    created_at: datetime,
    details_environment: str | None = None,
    delivery_state: str = "pending",
    delivery_attempts: int = 0,
    next_delivery_attempt_at: datetime | None = None,
    fallback_delivery_state: str = "pending",
    fallback_delivery_attempts: int = 0,
    fallback_next_delivery_attempt_at: datetime | None = None,
) -> uuid.UUID:
    with sessions() as db, db.begin():
        state = db.execute(
            select(ChatSandboxBudgetState).where(
                ChatSandboxBudgetState.environment == environment
            )
        ).scalar_one_or_none()
        if state is None:
            state = ChatSandboxBudgetState(
                id=uuid.uuid4(),
                environment=environment,
                billing_cycle=date(2026, 8, 1),
                cycle_end_at=datetime(2026, 9, 1, tzinfo=UTC),
                warning_microusd=75_000_000,
                application_cap_microusd=100_000_000,
                environment_cap_microusd=125_000_000,
                workspace_cap_microusd=250_000_000,
                policy_attestation="attested",
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(state)
            db.flush()
        event_id = uuid.uuid4()
        db.add(
            ChatSandboxCircuitEvent(
                id=event_id,
                budget_state_id=state.id,
                event_type="circuit_tripped",
                severity="critical",
                reason="application_cap",
                details={
                    "environment": details_environment or environment,
                    "billing_cycle": "2026-08-01",
                    "release": "release",
                    "effective_microusd": 100_000_000,
                    "provider_floor_microusd": 90_000_000,
                    "threshold_microusd": 100_000_000,
                    "remaining_provider_reserve_microusd": 150_000_000,
                    "circuit_state": "tripped",
                    "live_count": 2,
                    "uncertain_count": 1,
                    "reconciliation_age_seconds": 60,
                },
                delivery_state=delivery_state,
                delivery_attempts=delivery_attempts,
                next_delivery_attempt_at=next_delivery_attempt_at,
                fallback_delivery_state=fallback_delivery_state,
                fallback_delivery_attempts=fallback_delivery_attempts,
                fallback_next_delivery_attempt_at=fallback_next_delivery_attempt_at,
                created_at=created_at,
            )
        )
    return event_id


def get_event(sessions, event_id: uuid.UUID) -> ChatSandboxCircuitEvent:
    with sessions() as db:
        return db.get(ChatSandboxCircuitEvent, event_id)


def event_id_from_payload(payload: dict[str, str]) -> uuid.UUID:
    value = payload["text"].split("event_id=", 1)[1].split(";", 1)[0]
    return uuid.UUID(value)


def test_blank_primary_leaves_primary_and_fallback_attempts_untouched():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    primary_id = add_event(sessions, created_at=now)
    fallback_id = add_event(
        sessions,
        created_at=now + timedelta(seconds=1),
        delivery_state="failed",
    )
    poster = RecordingPoster()
    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(chat_sandbox_slack_webhook_url=""),
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 0
    assert poster.calls == []
    assert get_event(sessions, primary_id).delivery_attempts == 0
    assert get_event(sessions, fallback_id).fallback_delivery_attempts == 0


def test_primary_delivery_is_environment_scoped_and_preserves_payload_contract():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    staging_id = add_event(
        sessions,
        environment="staging",
        details_environment="production",
        created_at=now,
    )
    production_id = add_event(
        sessions,
        environment="production",
        details_environment="staging",
        created_at=now - timedelta(seconds=1),
    )
    poster = RecordingPoster()
    configured = settings()
    dispatcher = ChatSandboxSpendAlertDispatcher(
        configured,
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 1
    assert len(poster.calls) == 1
    url, payload, timeout = poster.calls[0]
    assert url == configured.chat_sandbox_slack_webhook_url
    assert timeout == WEBHOOK_TIMEOUT_SECONDS == 5
    assert payload == {
        "text": (
            "PwC chat compute critical: circuit_tripped; "
            "environment=production; cycle=2026-08-01; release=release; "
            "effective_microusd=100000000; provider_floor_microusd=90000000; "
            "threshold_microusd=100000000; provider_reserve_microusd=150000000; "
            "state=tripped; live=2; uncertain=1; reconciliation_age_seconds=60; "
            f"event_id={staging_id}; dashboard=/cron-dashboard; "
            "runbook=https://runbook.test/chat"
        )
    }
    assert get_event(sessions, staging_id).delivery_state == "delivered"
    assert get_event(sessions, production_id).delivery_state == "pending"


def test_primary_batch_is_oldest_ten():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_ids = [
        add_event(sessions, created_at=now + timedelta(seconds=index))
        for index in range(12)
    ]
    poster = RecordingPoster()
    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now + timedelta(minutes=1)),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 10
    assert [event_id_from_payload(payload) for _, payload, _ in poster.calls] == (
        event_ids[:10]
    )
    assert [get_event(sessions, event_id).delivery_state for event_id in event_ids] == [
        *("delivered" for _ in range(10)),
        "pending",
        "pending",
    ]


def test_due_boundary_reclaims_delivering_but_skips_future_and_attempt_cap():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    due_id = add_event(
        sessions,
        created_at=now,
        delivery_state="retry",
        next_delivery_attempt_at=now,
    )
    reclaim_id = add_event(
        sessions,
        created_at=now + timedelta(seconds=1),
        delivery_state="delivering",
        delivery_attempts=1,
        next_delivery_attempt_at=now,
    )
    future_id = add_event(
        sessions,
        created_at=now + timedelta(seconds=2),
        delivery_state="retry",
        next_delivery_attempt_at=now + timedelta(microseconds=1),
    )
    capped_id = add_event(
        sessions,
        created_at=now + timedelta(seconds=3),
        delivery_attempts=5,
    )
    poster = RecordingPoster()
    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 2
    assert [event_id_from_payload(payload) for _, payload, _ in poster.calls] == [
        due_id,
        reclaim_id,
    ]
    assert get_event(sessions, due_id).delivery_attempts == 1
    assert get_event(sessions, reclaim_id).delivery_attempts == 2
    assert get_event(sessions, future_id).delivery_state == "retry"
    assert get_event(sessions, capped_id).delivery_attempts == 5


def test_primary_failure_uses_exact_backoff():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(sessions, created_at=now)

    def fail(_url, _payload):
        raise RuntimeError("unavailable")

    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=sessions,
        webhook_poster=RecordingPoster(fail),
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 0
    event = get_event(sessions, event_id)
    assert event.delivery_state == "retry"
    assert event.delivery_attempts == 1
    assert event.next_delivery_attempt_at.replace(tzinfo=UTC) == now + timedelta(
        seconds=30
    )
    assert event.fallback_delivery_attempts == 0


def test_fifth_primary_failure_falls_back_in_same_call_without_counting_success():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(sessions, created_at=now, delivery_attempts=4)
    configured = settings()

    def fail_primary(url, _payload):
        if url == configured.chat_sandbox_slack_webhook_url:
            raise RuntimeError("primary unavailable")

    poster = RecordingPoster(fail_primary)
    dispatcher = ChatSandboxSpendAlertDispatcher(
        configured,
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 0
    assert [call[0] for call in poster.calls] == [
        configured.chat_sandbox_slack_webhook_url,
        configured.chat_sandbox_alert_fallback_webhook_url,
    ]
    event = get_event(sessions, event_id)
    assert event.delivery_state == "failed"
    assert event.delivery_attempts == 5
    assert event.next_delivery_attempt_at.replace(tzinfo=UTC) == now + timedelta(
        seconds=300
    )
    assert event.fallback_delivery_state == "delivered"
    assert event.fallback_delivery_attempts == 1
    assert event.fallback_delivered_at is not None


def test_fallback_delivery_is_environment_scoped_and_not_counted():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    staging_id = add_event(
        sessions,
        environment="staging",
        details_environment="production",
        created_at=now,
        delivery_state="failed",
    )
    production_id = add_event(
        sessions,
        environment="production",
        details_environment="staging",
        created_at=now - timedelta(seconds=1),
        delivery_state="failed",
    )
    poster = RecordingPoster()
    configured = settings()
    dispatcher = ChatSandboxSpendAlertDispatcher(
        configured,
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=Clock(now),
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 0
    assert [url for url, _, _ in poster.calls] == [
        configured.chat_sandbox_alert_fallback_webhook_url
    ]
    assert event_id_from_payload(poster.calls[0][1]) == staging_id
    assert get_event(sessions, staging_id).fallback_delivery_state == "delivered"
    assert get_event(sessions, production_id).fallback_delivery_state == "pending"


def test_fifth_fallback_failure_uses_exact_payload_backoff_and_attempt_cap():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(
        sessions,
        created_at=now,
        delivery_state="failed",
        fallback_delivery_attempts=4,
    )
    configured = settings()

    def fail(_url, _payload):
        raise RuntimeError("fallback unavailable")

    poster = RecordingPoster(fail)
    clock = Clock(now)
    dispatcher = ChatSandboxSpendAlertDispatcher(
        configured,
        session_factory=sessions,
        webhook_poster=poster,
        utcnow=clock,
    )

    assert asyncio.run(dispatcher.deliver_pending()) == 0
    assert poster.calls == [
        (
            configured.chat_sandbox_alert_fallback_webhook_url,
            {
                "text": (
                    "PwC chat compute primary alert delivery failed; "
                    f"environment=staging; severity=critical; event_id={event_id}; "
                    "runbook=https://runbook.test/chat"
                )
            },
            WEBHOOK_TIMEOUT_SECONDS,
        )
    ]
    event = get_event(sessions, event_id)
    assert event.fallback_delivery_state == "failed"
    assert event.fallback_delivery_attempts == 5
    assert event.fallback_next_delivery_attempt_at.replace(
        tzinfo=UTC
    ) == now + timedelta(seconds=300)

    clock.now = now + timedelta(seconds=301)
    assert asyncio.run(dispatcher.deliver_pending()) == 0
    assert len(poster.calls) == 1


def test_cancellation_leaves_the_committed_delivery_lease_for_reclaim():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(sessions, created_at=now)

    def cancel(_url, _payload):
        raise asyncio.CancelledError

    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=sessions,
        webhook_poster=RecordingPoster(cancel),
        utcnow=Clock(now),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(dispatcher.deliver_pending())
    event = get_event(sessions, event_id)
    assert event.delivery_state == "delivering"
    assert event.delivery_attempts == 1
    assert event.next_delivery_attempt_at.replace(tzinfo=UTC) == now + timedelta(
        seconds=30
    )


def test_stale_finalizer_cannot_overwrite_a_newer_delivery_claim():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(sessions, created_at=now)
    clock = Clock(now)
    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=sessions,
        webhook_poster=RecordingPoster(),
        utcnow=clock,
    )

    first = dispatcher._claim(event_id, SpendAlertChannel.PRIMARY)
    assert first is not None
    clock.now = now + timedelta(seconds=31)
    second = dispatcher._claim(event_id, SpendAlertChannel.PRIMARY)
    assert second is not None
    assert dispatcher._finalize_success(second)
    assert not dispatcher._finalize_failure(first)

    event = get_event(sessions, event_id)
    assert event.delivery_state == "delivered"
    assert event.delivery_attempts == 2
    assert event.next_delivery_attempt_at is None


def test_claim_is_committed_before_post_and_finalize_db_failure_propagates():
    sessions = session_factory()
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    event_id = add_event(sessions, created_at=now)
    observed: list[str] = []

    def observe_claim(_url, _payload):
        observed.append(get_event(sessions, event_id).delivery_state)

    class FailingFactory:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("finalize database unavailable")
            return sessions()

    dispatcher = ChatSandboxSpendAlertDispatcher(
        settings(),
        session_factory=FailingFactory(),
        webhook_poster=RecordingPoster(observe_claim),
        utcnow=Clock(now),
    )

    with pytest.raises(RuntimeError, match="finalize database unavailable"):
        asyncio.run(dispatcher.deliver_pending())
    assert observed == ["delivering"]
    assert get_event(sessions, event_id).delivery_state == "delivering"


def test_postgres_claim_locks_only_the_event_row():
    sessions = session_factory()
    dispatcher = ChatSandboxSpendAlertDispatcher(settings(), session_factory=sessions)
    statements = []

    class Result:
        @staticmethod
        def scalar_one_or_none():
            return None

    class CaptureSession:
        def execute(self, statement):
            statements.append(statement)
            return Result()

    dispatcher._load_event(CaptureSession(), uuid.uuid4())
    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "JOIN chat_sandbox_budget_states" in sql
    assert "FOR UPDATE OF chat_sandbox_circuit_events" in sql


def test_manager_delegates_and_validates_dispatcher_dependency_identity():
    sessions = session_factory()
    configured = settings()

    class StubDispatcher(ChatSandboxSpendAlertDispatcher):
        async def deliver_pending(self) -> int:
            return 7

    dispatcher = StubDispatcher(configured, session_factory=sessions)
    manager = SandboxSessionManager(
        configured,
        session_factory=sessions,
        spend_alert_dispatcher=dispatcher,
    )
    assert asyncio.run(manager.deliver_spend_alerts()) == 7
    assert manager._spend_alert_dispatcher() is dispatcher

    other_settings = settings()
    with pytest.raises(ValueError, match="settings must be shared"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            spend_alert_dispatcher=StubDispatcher(
                other_settings, session_factory=sessions
            ),
        )
    other_sessions = session_factory()
    with pytest.raises(ValueError, match="sessions must be shared"):
        SandboxSessionManager(
            configured,
            session_factory=sessions,
            spend_alert_dispatcher=StubDispatcher(
                configured, session_factory=other_sessions
            ),
        )

    lazy_manager = SandboxSessionManager(configured, session_factory=sessions)
    lazy = lazy_manager._spend_alert_dispatcher()
    assert lazy.settings is configured
    assert lazy.session_factory is sessions
    assert lazy_manager._spend_alert_dispatcher() is lazy
