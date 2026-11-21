"""Persistent, environment-isolated spend circuit for cosmetic chat titles."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatTitleBudgetEvent,
    ChatTitleBudgetState,
    ChatTitleProviderCall,
)

logger = logging.getLogger(__name__)
TITLE_BUDGET_LOCK = "chat-title-budget-v1"


class ChatTitleBudgetUnavailable(RuntimeError):
    """The title call must fall back locally without affecting research."""


@dataclass(frozen=True)
class ChatTitleReservation:
    call_id: uuid.UUID
    reserved_microusd: int
    idempotent_replay: bool = False


def billing_cycle(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("title budget timestamps must be timezone aware")
    return now.astimezone(UTC).date().replace(day=1)


def cycle_end(cycle: date) -> datetime:
    return datetime(
        cycle.year + (cycle.month == 12), cycle.month % 12 + 1, 1, tzinfo=UTC
    )


class ChatTitleBudgetService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _lock(self) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.scalar(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(TITLE_BUDGET_LOCK, 0)
                    )
                )
            )

    def _state(self, now: datetime) -> ChatTitleBudgetState:
        self._lock()
        cycle = billing_cycle(now)
        state = self.db.execute(
            select(ChatTitleBudgetState)
            .where(
                ChatTitleBudgetState.environment == self.settings.environment,
                ChatTitleBudgetState.billing_cycle == cycle,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if state is None:
            state = ChatTitleBudgetState(
                id=uuid.uuid4(),
                environment=self.settings.environment,
                billing_cycle=cycle,
                cycle_end_at=cycle_end(cycle),
                warning_microusd=self.settings.chat_title_warning_microusd,
                application_cap_microusd=self.settings.chat_title_monthly_cap_microusd,
                spent_microusd=0,
                reserved_microusd=0,
                circuit_state="armed",
                created_at=now,
                updated_at=now,
            )
            self.db.add(state)
            self.db.flush()
        elif (
            state.warning_microusd != self.settings.chat_title_warning_microusd
            or state.application_cap_microusd
            != self.settings.chat_title_monthly_cap_microusd
        ):
            raise ChatTitleBudgetUnavailable(
                "The active title budget policy differs from its monthly snapshot"
            )
        return state

    def _event(
        self,
        state: ChatTitleBudgetState,
        event_type: str,
        now: datetime,
    ) -> None:
        existing = self.db.execute(
            select(ChatTitleBudgetEvent).where(
                ChatTitleBudgetEvent.budget_state_id == state.id,
                ChatTitleBudgetEvent.event_type == event_type,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        self.db.add(
            ChatTitleBudgetEvent(
                id=uuid.uuid4(),
                budget_state_id=state.id,
                event_type=event_type,
                details={
                    "environment": self.settings.environment,
                    "billing_cycle": state.billing_cycle.isoformat(),
                    "release": self.settings.release_id,
                    "spent_microusd": int(state.spent_microusd),
                    "reserved_microusd": int(state.reserved_microusd),
                    "threshold_microusd": (
                        state.warning_microusd
                        if event_type == "warning"
                        else state.application_cap_microusd
                    ),
                },
                delivery_state="pending",
                fallback_delivery_state="pending",
                created_at=now,
            )
        )

    def reserve_call(
        self,
        call_id: uuid.UUID,
        now: datetime | None = None,
    ) -> ChatTitleReservation:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        state = self._state(current)
        existing = self.db.execute(
            select(ChatTitleProviderCall)
            .where(ChatTitleProviderCall.id == call_id)
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.environment != self.settings.environment
                or existing.model != self.settings.chat_title_model
                or existing.provider != self.settings.chat_title_provider
            ):
                raise ChatTitleBudgetUnavailable(
                    "A title call identifier crossed an environment or provider boundary"
                )
            return ChatTitleReservation(
                call_id=call_id,
                reserved_microusd=existing.reserved_microusd,
                idempotent_replay=True,
            )

        reserved = self.settings.chat_title_max_call_microusd
        projected = state.spent_microusd + state.reserved_microusd + reserved
        if (
            state.circuit_state == "tripped"
            or projected > state.application_cap_microusd
        ):
            if (
                state.circuit_state == "tripped"
                or state.spent_microusd >= state.application_cap_microusd
                or state.reserved_microusd == 0
            ):
                state.circuit_state = "tripped"
                state.updated_at = current
                self._event(state, "exhausted", current)
                self.db.flush()
            raise ChatTitleBudgetUnavailable("The monthly title budget is exhausted")

        call = ChatTitleProviderCall(
            id=call_id,
            budget_state_id=state.id,
            environment=self.settings.environment,
            billing_cycle=state.billing_cycle,
            model=self.settings.chat_title_model,
            provider=self.settings.chat_title_provider,
            state="reserved",
            reserved_microusd=reserved,
            reserved_at=current,
            updated_at=current,
        )
        self.db.add(call)
        state.reserved_microusd += reserved
        if projected >= state.warning_microusd:
            state.circuit_state = "warning"
            self._event(state, "warning", current)
        state.updated_at = current
        self.db.flush()
        return ChatTitleReservation(call_id=call_id, reserved_microusd=reserved)

    def _call(self, call_id: uuid.UUID) -> ChatTitleProviderCall:
        call = self.db.execute(
            select(ChatTitleProviderCall)
            .where(ChatTitleProviderCall.id == call_id)
            .with_for_update()
        ).scalar_one_or_none()
        if call is None or call.environment != self.settings.environment:
            raise ChatTitleBudgetUnavailable("The title reservation is unavailable")
        return call

    def mark_dispatched(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        call = self._call(call_id)
        if call.state in {"dispatched", "settled"}:
            return
        if call.state != "reserved":
            raise ChatTitleBudgetUnavailable("A released title call cannot dispatch")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        call.state = "dispatched"
        call.dispatched_at = current
        call.updated_at = current
        self.db.flush()

    def release_call(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        call = self._call(call_id)
        if call.state == "released":
            return
        if call.state != "reserved":
            raise ChatTitleBudgetUnavailable(
                "Only an undispatched title call can release"
            )
        state = self.db.execute(
            select(ChatTitleBudgetState)
            .where(ChatTitleBudgetState.id == call.budget_state_id)
            .with_for_update()
        ).scalar_one()
        current = (now or datetime.now(UTC)).astimezone(UTC)
        state.reserved_microusd -= call.reserved_microusd
        projected = state.spent_microusd + state.reserved_microusd
        state.circuit_state = (
            "tripped"
            if state.spent_microusd >= state.application_cap_microusd
            else "warning"
            if projected >= state.warning_microusd
            else "armed"
        )
        state.updated_at = current
        call.state = "released"
        call.released_at = current
        call.updated_at = current
        self.db.flush()

    def settle_call(
        self,
        call_id: uuid.UUID,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        provider_generation_id: str | None = None,
        now: datetime | None = None,
    ) -> int:
        call = self._call(call_id)
        if call.state == "settled":
            return int(call.actual_microusd or 0)
        if call.state != "dispatched":
            raise ChatTitleBudgetUnavailable("Only a dispatched title call can settle")
        state = self.db.execute(
            select(ChatTitleBudgetState)
            .where(ChatTitleBudgetState.id == call.budget_state_id)
            .with_for_update()
        ).scalar_one()
        if input_tokens is None or output_tokens is None:
            actual = call.reserved_microusd
        else:
            if input_tokens < 0 or output_tokens < 0:
                raise ChatTitleBudgetUnavailable("Provider title usage is invalid")
            actual = (
                input_tokens * self.settings.chat_title_input_microusd_per_token
                + output_tokens * self.settings.chat_title_output_microusd_per_token
            )
            actual = min(call.reserved_microusd, max(1, actual))
        current = (now or datetime.now(UTC)).astimezone(UTC)
        state.reserved_microusd -= call.reserved_microusd
        state.spent_microusd += actual
        projected = state.spent_microusd + state.reserved_microusd
        if projected >= state.application_cap_microusd:
            state.circuit_state = "tripped"
            self._event(state, "exhausted", current)
        elif projected >= state.warning_microusd:
            state.circuit_state = "warning"
            self._event(state, "warning", current)
        state.updated_at = current
        call.state = "settled"
        call.actual_microusd = actual
        call.input_tokens = input_tokens
        call.output_tokens = output_tokens
        call.provider_generation_id = provider_generation_id
        call.settled_at = current
        call.updated_at = current
        self.db.flush()
        return actual

    def reconcile_stale_calls(
        self,
        *,
        now: datetime | None = None,
        stale_after_seconds: int = 300,
    ) -> dict[str, int]:
        """Close abandoned reservations without allowing unmetered provider spend."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        cutoff = current - timedelta(seconds=stale_after_seconds)
        calls = list(
            self.db.scalars(
                select(ChatTitleProviderCall)
                .where(
                    ChatTitleProviderCall.environment == self.settings.environment,
                    ChatTitleProviderCall.state.in_(("reserved", "dispatched")),
                    ChatTitleProviderCall.updated_at <= cutoff,
                )
                .order_by(ChatTitleProviderCall.updated_at)
                .with_for_update(skip_locked=True)
            )
        )
        released = 0
        conservatively_settled = 0
        for call in calls:
            if call.state == "reserved":
                self.release_call(call.id, now=current)
                released += 1
            else:
                self.settle_call(
                    call.id,
                    input_tokens=None,
                    output_tokens=None,
                    now=current,
                )
                conservatively_settled += 1
        return {
            "released": released,
            "conservatively_settled": conservatively_settled,
        }


def reconcile_stale_title_calls(settings: Settings) -> dict[str, int]:
    from backend.database.connection import db_manager

    with db_manager.session_local() as db:
        result = ChatTitleBudgetService(db, settings).reconcile_stale_calls()
        db.commit()
        return result


async def deliver_title_budget_alerts(settings: Settings) -> int:
    """Attempt each content-free title alert once through primary then fallback."""

    if not settings.chat_sandbox_slack_webhook_url:
        return 0
    from backend.database.connection import db_manager

    with db_manager.session_local() as db:
        event_ids = list(
            db.execute(
                select(ChatTitleBudgetEvent.id)
                .join(
                    ChatTitleBudgetState,
                    ChatTitleBudgetState.id == ChatTitleBudgetEvent.budget_state_id,
                )
                .where(ChatTitleBudgetEvent.delivery_state == "pending")
                .where(ChatTitleBudgetState.environment == settings.environment)
                .order_by(ChatTitleBudgetEvent.created_at)
                .limit(10)
            ).scalars()
        )
    delivered = 0
    for event_id in event_ids:
        with db_manager.session_local() as db:
            event = db.get(ChatTitleBudgetEvent, event_id)
            if event is None or event.delivery_state != "pending":
                continue
            payload = {
                "text": (
                    f"PwC chat title budget {event.event_type}; "
                    f"environment={event.details.get('environment')}; "
                    f"cycle={event.details.get('billing_cycle')}; "
                    f"release={event.details.get('release')}; "
                    f"spent_microusd={event.details.get('spent_microusd')}; "
                    f"reserved_microusd={event.details.get('reserved_microusd')}; "
                    f"threshold_microusd={event.details.get('threshold_microusd')}; "
                    f"event_id={event.id}; runbook={settings.chat_sandbox_runbook_url}"
                )
            }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    settings.chat_sandbox_slack_webhook_url, json=payload
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            logger.critical(
                "chat title budget primary alert failed event_id=%s error=%s",
                event_id,
                type(error).__name__,
            )
            with db_manager.session_local() as db:
                event = db.get(ChatTitleBudgetEvent, event_id)
                if event:
                    event.delivery_state = "failed"
                    db.commit()
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.post(
                        settings.chat_sandbox_alert_fallback_webhook_url,
                        json={
                            "text": (
                                "PwC chat title primary alert delivery failed; "
                                f"environment={settings.environment}; event_id={event_id}; "
                                f"runbook={settings.chat_sandbox_runbook_url}"
                            )
                        },
                    )
                    response.raise_for_status()
            except httpx.HTTPError as fallback_error:
                logger.critical(
                    "chat title budget fallback alert failed event_id=%s error=%s",
                    event_id,
                    type(fallback_error).__name__,
                )
                with db_manager.session_local() as db:
                    event = db.get(ChatTitleBudgetEvent, event_id)
                    if event:
                        event.fallback_delivery_state = "failed"
                        db.commit()
            else:
                with db_manager.session_local() as db:
                    event = db.get(ChatTitleBudgetEvent, event_id)
                    if event:
                        event.fallback_delivery_state = "delivered"
                        db.commit()
            continue
        with db_manager.session_local() as db:
            event = db.get(ChatTitleBudgetEvent, event_id)
            if event:
                event.delivery_state = "delivered"
                db.commit()
                delivered += 1
    return delivered
