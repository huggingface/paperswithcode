"""Conservative lifecycle metering and durable Modal-chat circuit breaker."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, aliased

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
)
from backend.services.chat_sandbox_capacity_repository import (
    CAPACITY_LOCK_NAME as CAPACITY_LOCK_NAME,  # noqa: PLC0414
)
from backend.services.chat_sandbox_capacity_repository import (
    LIVE_LEASE_STATES,
    lock_capacity,
)

CPU_MICROUSD_PER_CORE_SECOND = Decimal("39.42")
MEMORY_MICROUSD_PER_GIB_SECOND = Decimal("6.72")
METERING_CLOCK_SKEW_SECONDS = 5


class ChatComputeDisabled(RuntimeError):
    code = "chat_temporarily_disabled"

    def __init__(self, message: str, *, reason: str = "application_cap"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ProviderReconciliationClaim:
    """Exact budget-state generation allowed to finalize one provider report."""

    owner_state_id: uuid.UUID
    billing_cycle: date
    attempted_at: datetime


def billing_cycle(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("billing-cycle timestamps must be timezone aware")
    return now.astimezone(UTC).date().replace(day=1)


def cycle_end(cycle: date) -> datetime:
    return datetime(
        cycle.year + (cycle.month == 12), cycle.month % 12 + 1, 1, tzinfo=UTC
    )


class ChatSandboxSpendService:
    """All money is integer microdollars; the provider floor can only raise spend."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        utcnow: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self.settings = settings
        self.utcnow = utcnow or (lambda: datetime.now(UTC))

    def _lock(self) -> None:
        lock_capacity(self.db)

    def _policy(self) -> tuple[int, int, int, int]:
        return (
            self.settings.chat_sandbox_warning_microusd,
            self.settings.chat_sandbox_application_cap_microusd,
            self.settings.chat_sandbox_environment_cap_microusd,
            self.settings.chat_sandbox_workspace_cap_microusd,
        )

    def _state(
        self,
        now: datetime,
        *,
        lock: bool = True,
        provider_cycle_confirmed: bool = False,
    ) -> ChatSandboxBudgetState:
        cycle = billing_cycle(now)
        query = select(ChatSandboxBudgetState).where(
            ChatSandboxBudgetState.environment == self.settings.environment,
            ChatSandboxBudgetState.billing_cycle == cycle,
        )
        if lock:
            query = query.with_for_update()
        state = self.db.execute(query).scalar_one_or_none()
        if state is None:
            previous = self.db.execute(
                select(ChatSandboxBudgetState)
                .where(ChatSandboxBudgetState.environment == self.settings.environment)
                .order_by(ChatSandboxBudgetState.billing_cycle.desc())
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
            if previous is not None and previous.circuit_state == "tripped":
                unresolved = (
                    self.db.scalar(
                        select(func.count())
                        .select_from(ChatSandboxComputeInterval)
                        .where(
                            ChatSandboxComputeInterval.environment
                            == self.settings.environment,
                            (ChatSandboxComputeInterval.terminal_at.is_(None))
                            | (ChatSandboxComputeInterval.reserved_microusd > 0),
                        )
                    )
                    or 0
                )
                safe_spend_trip = previous.trip_reason in {
                    "application_cap",
                    "safety_reserve",
                    "provider_budget",
                }
                sweep = self.db.execute(
                    select(ChatSandboxCircuitEvent)
                    .where(
                        ChatSandboxCircuitEvent.budget_state_id == previous.id,
                        ChatSandboxCircuitEvent.event_type == "kill_sweep_complete",
                    )
                    .order_by(ChatSandboxCircuitEvent.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                sweep_after_trip = bool(
                    sweep is not None
                    and previous.tripped_at is not None
                    and self._aware(sweep.created_at)
                    >= self._aware(previous.tripped_at)
                )
                policy_matches = (
                    (
                        previous.warning_microusd,
                        previous.application_cap_microusd,
                        previous.environment_cap_microusd,
                        previous.workspace_cap_microusd,
                    )
                    == self._policy()
                    and previous.policy_attestation
                    == self.settings.chat_sandbox_budget_attestation
                )
                if not (
                    safe_spend_trip
                    and provider_cycle_confirmed
                    and unresolved == 0
                    and sweep_after_trip
                    and policy_matches
                ):
                    raise ChatComputeDisabled("Chat is temporarily disabled")
            warning, application, environment, workspace = self._policy()
            state = ChatSandboxBudgetState(
                id=uuid.uuid4(),
                environment=self.settings.environment,
                billing_cycle=cycle,
                cycle_end_at=cycle_end(cycle),
                warning_microusd=warning,
                application_cap_microusd=application,
                environment_cap_microusd=environment,
                workspace_cap_microusd=workspace,
                policy_attestation=self.settings.chat_sandbox_budget_attestation,
            )
            self.db.add(state)
            self.db.flush()
            if previous is not None:
                self._event(state, "cycle_rearmed", "recovery", None, now)
        return state

    def cost_per_second(self) -> int:
        cpu = Decimal(
            str(self.settings.chat_sandbox_cpu_limit or self.settings.chat_sandbox_cpu)
        )
        memory = Decimal(
            self.settings.chat_sandbox_memory_limit_mib
            or self.settings.chat_sandbox_memory_mib
        ) / Decimal(1024)
        return int(
            (
                cpu * CPU_MICROUSD_PER_CORE_SECOND
                + memory * MEMORY_MICROUSD_PER_GIB_SECOND
            ).to_integral_value(rounding=ROUND_CEILING)
        )

    def reservation_amount(self) -> int:
        seconds = (
            self.settings.chat_sandbox_watchdog_seconds
            + self.settings.chat_sandbox_drain_grace_seconds
            + self.settings.chat_sandbox_termination_grace_seconds
        )
        return (
            self.cost_per_second() * seconds
            + self.settings.chat_sandbox_reconciliation_allowance_microusd
        )

    @staticmethod
    def _interval_rate(interval: ChatSandboxComputeInterval) -> int:
        # Modal bills the greater of the resource request and actual usage, not
        # the configured burst limit. Provider reconciliation raises this local
        # request-based estimate when actual usage is higher.
        return int(
            (
                Decimal(interval.cpu_request_millicores)
                / Decimal(1000)
                * CPU_MICROUSD_PER_CORE_SECOND
                + Decimal(interval.memory_request_mib)
                / Decimal(1024)
                * MEMORY_MICROUSD_PER_GIB_SECOND
            ).to_integral_value(rounding=ROUND_CEILING)
        )

    def reconcile_terminal_leases(self, now: datetime) -> int:
        """Settle intervals left open after their durable lease became terminal."""

        successor = aliased(ChatSandboxComputeInterval)
        superseded = dict(
            self.db.execute(
                select(
                    ChatSandboxComputeInterval.id,
                    func.min(successor.reserved_at),
                )
                .join(
                    successor,
                    (successor.environment == ChatSandboxComputeInterval.environment)
                    & (
                        successor.chat_session_id
                        == ChatSandboxComputeInterval.chat_session_id
                    )
                    & (successor.reserved_at > ChatSandboxComputeInterval.reserved_at),
                )
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                    ChatSandboxComputeInterval.claimed_at.is_not(None),
                )
                .group_by(ChatSandboxComputeInterval.id)
            ).all()
        )
        superseded_rows = list(
            self.db.scalars(
                select(ChatSandboxComputeInterval)
                .where(ChatSandboxComputeInterval.id.in_(superseded))
                .with_for_update()
            )
        )
        for interval in superseded_rows:
            self._settle_reconciled_interval(
                interval,
                terminal_at=self._aware(superseded[interval.id]),
                reason="lease_superseded_reconciled",
                now=now,
            )

        rows = list(
            self.db.execute(
                select(ChatSandboxComputeInterval, ChatSandboxLease)
                .join(
                    ChatSandboxLease,
                    ChatSandboxLease.chat_session_id
                    == ChatSandboxComputeInterval.chat_session_id,
                )
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                    ChatSandboxComputeInterval.claimed_at.is_not(None),
                    ChatSandboxLease.state.in_(["terminated", "failed"]),
                    ChatSandboxLease.modal_sandbox_id.is_(None),
                    ChatSandboxLease.worker_generation
                    == ChatSandboxComputeInterval.worker_generation,
                )
                .with_for_update()
            ).all()
        )
        for interval, lease in rows:
            terminal_at = max(
                self._aware(interval.provider_created_at or interval.reserved_at),
                self._aware(lease.updated_at),
            )
            self._settle_reconciled_interval(
                interval,
                terminal_at=terminal_at,
                reason="lease_terminal_reconciled",
                now=now,
            )
        return len(superseded_rows) + len(rows)

    @staticmethod
    def _settle_reconciled_interval(
        interval: ChatSandboxComputeInterval,
        *,
        terminal_at: datetime,
        reason: str,
        now: datetime,
    ) -> None:
        interval.termination_requested_at = (
            interval.termination_requested_at or terminal_at
        )
        interval.terminal_at = terminal_at
        interval.terminal_reason = reason
        interval.reserved_microusd = 0
        interval.reconciliation_state = "confirmed"
        interval.updated_at = now

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def _metered_end(
        self, interval: ChatSandboxComputeInterval, now: datetime
    ) -> datetime:
        start = self._aware(interval.reserved_at)
        if interval.terminal_at is not None:
            return self._aware(interval.terminal_at)
        return min(
            now,
            start
            + timedelta(seconds=self.settings.chat_persistent_sandbox_lifetime_seconds),
        )

    def _overlap_cost(
        self,
        interval: ChatSandboxComputeInterval,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> int:
        overlap_start = max(self._aware(interval.reserved_at), start)
        overlap_end = min(self._metered_end(interval, now), end)
        seconds = max(0, int((overlap_end - overlap_start).total_seconds()))
        return seconds * self._interval_rate(interval)

    def _provider_covered_orphan(
        self,
        interval: ChatSandboxComputeInterval,
        state: ChatSandboxBudgetState,
    ) -> bool:
        """Use the provider floor once a confirmed orphan's hour is closed."""

        if (
            interval.origin != "reconciled_orphan"
            or interval.reconciliation_state != "confirmed"
            or interval.terminal_at is None
            or state.last_reconciled_at is None
        ):
            return False
        reconciled_at = self._aware(state.last_reconciled_at)
        provider_coverage_end = reconciled_at.replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        return self._aware(interval.terminal_at) <= provider_coverage_end

    @staticmethod
    def _is_uncreated_failure(interval: ChatSandboxComputeInterval) -> bool:
        """Return whether Modal never created compute for a closed reservation."""

        return (
            interval.reconciliation_state == "creation_failed"
            and interval.provider_created_at is None
            and interval.modal_sandbox_id is None
        )

    def _terminal_summary(
        self,
        *,
        state: ChatSandboxBudgetState,
        cycle_start: datetime,
        cycle_finish: datetime,
        now: datetime,
    ) -> tuple[int, bool]:
        """Aggregate immutable terminal history without row-locking it on admission."""

        if self.db.get_bind().dialect.name != "postgresql":
            rows = list(
                self.db.execute(
                    select(ChatSandboxComputeInterval).where(
                        ChatSandboxComputeInterval.environment
                        == self.settings.environment,
                        ChatSandboxComputeInterval.terminal_at.is_not(None),
                        ChatSandboxComputeInterval.reserved_at < cycle_finish,
                        ChatSandboxComputeInterval.terminal_at >= cycle_start,
                    )
                ).scalars()
            )
            accrued = 0
            invalid = False
            for interval in rows:
                if self._is_uncreated_failure(interval):
                    continue
                interval_start = self._aware(interval.reserved_at)
                provider_created_at = (
                    None
                    if interval.provider_created_at is None
                    else self._aware(interval.provider_created_at)
                )
                terminal_at = self._aware(interval.terminal_at)
                if (
                    interval.cpu_request_millicores <= 0
                    or interval.memory_request_mib <= 0
                    or interval.cpu_limit_millicores < interval.cpu_request_millicores
                    or interval.memory_limit_mib < interval.memory_request_mib
                    or interval_start
                    > now + timedelta(seconds=METERING_CLOCK_SKEW_SECONDS)
                    or (
                        provider_created_at is not None
                        and provider_created_at < interval_start
                    )
                    or terminal_at < interval_start
                ):
                    invalid = True
                if not self._provider_covered_orphan(interval, state):
                    accrued += self._overlap_cost(
                        interval, cycle_start, cycle_finish, now
                    )
            return accrued, invalid

        coverage_end = None
        if state.last_reconciled_at is not None:
            coverage_end = self._aware(state.last_reconciled_at).replace(
                minute=0,
                second=0,
                microsecond=0,
            )
        summary = (
            self.db.execute(
                text(
                    """
                SELECT
                    COALESCE(
                        SUM(
                            GREATEST(
                                0,
                                FLOOR(
                                    EXTRACT(
                                        EPOCH FROM (
                                            LEAST(terminal_at, :cycle_finish)
                                            - GREATEST(reserved_at, :cycle_start)
                                        )
                                    )
                                )
                            )::bigint
                            * CEIL(
                                cpu_request_millicores / 1000.0 * 39.42
                                + memory_request_mib / 1024.0 * 6.72
                            )::bigint
                        ) FILTER (
                            WHERE NOT (
                                :has_coverage
                                AND origin = 'reconciled_orphan'
                                AND reconciliation_state = 'confirmed'
                                AND terminal_at <= :coverage_end
                            )
                            AND NOT (
                                reconciliation_state = 'creation_failed'
                                AND provider_created_at IS NULL
                                AND modal_sandbox_id IS NULL
                            )
                        ),
                        0
                    )::bigint AS accrued_microusd,
                    COUNT(*) FILTER (
                        WHERE cpu_request_millicores <= 0
                           OR memory_request_mib <= 0
                           OR cpu_limit_millicores < cpu_request_millicores
                           OR memory_limit_mib < memory_request_mib
                           OR reserved_at > :future_limit
                           OR provider_created_at < reserved_at
                           OR terminal_at < reserved_at
                    )::bigint AS invalid_count
                FROM chat_sandbox_compute_intervals
                WHERE environment = :environment
                  AND terminal_at IS NOT NULL
                  AND reserved_at < :cycle_finish
                  AND terminal_at >= :cycle_start
                """
                ),
                {
                    "coverage_end": coverage_end or cycle_start,
                    "cycle_finish": cycle_finish,
                    "cycle_start": cycle_start,
                    "environment": self.settings.environment,
                    "future_limit": now
                    + timedelta(seconds=METERING_CLOCK_SKEW_SECONDS),
                    "has_coverage": coverage_end is not None,
                },
            )
            .mappings()
            .one()
        )
        return int(summary["accrued_microusd"]), bool(summary["invalid_count"])

    def refresh(
        self, now: datetime, *, capacity_locked: bool = False
    ) -> ChatSandboxBudgetState:
        if not capacity_locked:
            self._lock()
        state = self._state(now)
        configured_policy = self._policy()
        stored_policy = (
            state.warning_microusd,
            state.application_cap_microusd,
            state.environment_cap_microusd,
            state.workspace_cap_microusd,
        )
        integrity_reason = None
        if (
            stored_policy != configured_policy
            or state.policy_attestation != self.settings.chat_sandbox_budget_attestation
        ):
            integrity_reason = "accounting_integrity"
        last_metered = state.last_metered_at
        if last_metered is not None and self._aware(last_metered) > now + timedelta(
            seconds=METERING_CLOCK_SKEW_SECONDS
        ):
            observed_now = self.utcnow()
            if self._aware(last_metered) <= observed_now + timedelta(
                seconds=METERING_CLOCK_SKEW_SECONDS
            ):
                now = max(now, observed_now)
                if billing_cycle(now) != state.billing_cycle:
                    state = self._state(now)
            else:
                integrity_reason = "metering_degraded"
        self.reconcile_terminal_leases(now)
        cycle_start = datetime(
            state.billing_cycle.year, state.billing_cycle.month, 1, tzinfo=UTC
        )
        cycle_finish = self._aware(state.cycle_end_at)
        intervals = list(
            self.db.execute(
                select(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.reserved_at < cycle_finish,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                )
                .with_for_update()
            ).scalars()
        )
        accrued, invalid_terminal = self._terminal_summary(
            state=state,
            cycle_start=cycle_start,
            cycle_finish=cycle_finish,
            now=now,
        )
        if invalid_terminal:
            integrity_reason = "metering_degraded"
        reserved = 0
        for interval in intervals:
            interval_start = self._aware(interval.reserved_at)
            provider_created_at = (
                None
                if interval.provider_created_at is None
                else self._aware(interval.provider_created_at)
            )
            terminal_at = (
                None
                if interval.terminal_at is None
                else self._aware(interval.terminal_at)
            )
            if (
                interval.cpu_limit_millicores <= 0
                or interval.memory_limit_mib <= 0
                or interval_start > now + timedelta(seconds=METERING_CLOCK_SKEW_SECONDS)
                or (
                    provider_created_at is not None
                    and provider_created_at < interval_start
                )
                or (terminal_at is not None and terminal_at < interval_start)
            ):
                integrity_reason = "metering_degraded"
            end = self._metered_end(interval, now)
            start = interval_start
            seconds = max(0, int((end - start).total_seconds()))
            # Each interval preserves its resource shape so policy changes
            # cannot rewrite history.
            rate = self._interval_rate(interval)
            interval.accrued_microusd = max(interval.accrued_microusd, seconds * rate)
            interval.updated_at = now
            accrued += self._overlap_cost(
                interval, cycle_start, min(now, cycle_finish), now
            )
            reserved += interval.reserved_microusd
        state.estimated_accrued_microusd = accrued
        state.outstanding_reservation_microusd = reserved
        configured_floor = self.settings.chat_sandbox_provider_floor_microusd
        state.provider_floor_microusd = max(
            state.provider_floor_microusd, configured_floor
        )
        if self.settings.chat_sandbox_provider_reported_at:
            reported_at = datetime.fromisoformat(
                self.settings.chat_sandbox_provider_reported_at
            )
            if reported_at.tzinfo is None:
                raise ValueError("provider report timestamp must be timezone aware")
            if billing_cycle(reported_at) == state.billing_cycle:
                state.last_reconciled_at = reported_at.astimezone(UTC)
                state.reconciliation_state = "fresh"
        state.last_metered_at = now
        state.updated_at = now
        if integrity_reason is not None:
            state.circuit_state = "tripped"
            state.trip_reason = integrity_reason
            state.tripped_at = state.tripped_at or now
            self._event(
                state,
                f"circuit_{integrity_reason}",
                "critical",
                integrity_reason,
                now,
            )
        else:
            self._evaluate(state, now)
        if state.provider_floor_microusd > state.estimated_accrued_microusd:
            self._event(
                state, "provider_above_estimate", "critical", "provider_budget", now
            )
        return state

    def _event(
        self,
        state: ChatSandboxBudgetState,
        event_type: str,
        severity: str,
        reason: str | None,
        now: datetime,
        *,
        deduplicate: bool = True,
    ) -> None:
        duplicate = None
        if deduplicate:
            event_query = select(ChatSandboxCircuitEvent.id).where(
                ChatSandboxCircuitEvent.budget_state_id == state.id,
                ChatSandboxCircuitEvent.event_type == event_type,
            )
            if event_type.startswith("kill_sweep_") and state.tripped_at is not None:
                event_query = event_query.where(
                    ChatSandboxCircuitEvent.created_at >= state.tripped_at
                )
            duplicate = self.db.execute(event_query.limit(1)).scalar_one_or_none()
        if duplicate is None:
            live_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment == state.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                    )
                )
                or 0
            )
            uncertain_count = (
                self.db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxComputeInterval)
                    .where(
                        ChatSandboxComputeInterval.environment == state.environment,
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                        ChatSandboxComputeInterval.reconciliation_state
                        == "termination_uncertain",
                    )
                )
                or 0
            )
            effective = max(
                state.estimated_accrued_microusd, state.provider_floor_microusd
            )
            reconciled_at = state.last_reconciled_at
            if reconciled_at is not None:
                reconciled_at = self._aware(reconciled_at)
            self.db.add(
                ChatSandboxCircuitEvent(
                    id=uuid.uuid4(),
                    budget_state_id=state.id,
                    event_type=event_type,
                    severity=severity,
                    reason=reason,
                    details={
                        "environment": state.environment,
                        "billing_cycle": state.billing_cycle.isoformat(),
                        "release": self.settings.release_id,
                        "effective_microusd": effective,
                        "provider_floor_microusd": state.provider_floor_microusd,
                        "threshold_microusd": state.application_cap_microusd,
                        "remaining_provider_reserve_microusd": max(
                            0,
                            (
                                state.environment_cap_microusd
                                or state.workspace_cap_microusd
                            )
                            - effective,
                        ),
                        "circuit_state": state.circuit_state,
                        "live_count": live_count,
                        "uncertain_count": uncertain_count,
                        "reconciliation_age_seconds": (
                            None
                            if reconciled_at is None
                            else max(0, int((now - reconciled_at).total_seconds()))
                        ),
                    },
                    created_at=now,
                )
            )

    def _evaluate(self, state: ChatSandboxBudgetState, now: datetime) -> None:
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        projected = effective + state.outstanding_reservation_microusd
        if (
            state.circuit_state != "tripped"
            and projected >= state.application_cap_microusd
        ):
            state.circuit_state = "tripped"
            state.trip_reason = "application_cap"
            state.tripped_at = now
            self._event(state, "circuit_tripped", "critical", state.trip_reason, now)
        elif state.circuit_state == "armed" and effective >= state.warning_microusd:
            state.circuit_state = "warning"
            self._event(state, "warning_entered", "warning", None, now)

    def trip(self, reason: str, now: datetime | None = None) -> ChatSandboxBudgetState:
        now = now or datetime.now(UTC)
        self._lock()
        state = self.refresh(now)
        if state.circuit_state != "tripped":
            state.circuit_state = "tripped"
            state.trip_reason = reason
            state.tripped_at = now
            state.updated_at = now
            self._event(state, "circuit_tripped", "critical", reason, now)
        return state

    def assert_available(
        self,
        now: datetime | None = None,
        *,
        capacity_locked: bool = False,
    ) -> ChatSandboxBudgetState:
        state = self.refresh(
            now or datetime.now(UTC),
            capacity_locked=capacity_locked,
        )
        if state.circuit_state == "tripped":
            raise ChatComputeDisabled(
                "Chat is temporarily disabled",
                reason=state.trip_reason or "application_cap",
            )
        return state

    def reserve_interval(
        self,
        *,
        origin: str,
        worker_generation: str,
        chat_session_id: uuid.UUID | None = None,
        now: datetime | None = None,
        capacity_locked: bool = False,
    ) -> uuid.UUID:
        now = now or datetime.now(UTC)
        state = self.assert_available(now, capacity_locked=capacity_locked)
        reservation = self.reservation_amount()
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        if (
            effective + state.outstanding_reservation_microusd + reservation
            >= state.application_cap_microusd
        ):
            state.circuit_state = "tripped"
            state.trip_reason = "safety_reserve"
            state.tripped_at = now
            self._event(state, "circuit_tripped", "critical", state.trip_reason, now)
            raise ChatComputeDisabled(
                "Chat is temporarily disabled", reason=state.trip_reason
            )
        interval_id = uuid.uuid4()
        self.db.add(
            ChatSandboxComputeInterval(
                id=interval_id,
                environment=self.settings.environment,
                modal_app=MODAL_APP_NAME,
                app_release_id=self.settings.release_id,
                image_version=self.settings.chat_modal_image_version,
                worker_generation=worker_generation,
                origin=origin,
                chat_session_id=chat_session_id,
                cpu_request_millicores=round(self.settings.chat_sandbox_cpu * 1000),
                cpu_limit_millicores=round(
                    (
                        self.settings.chat_sandbox_cpu_limit
                        or self.settings.chat_sandbox_cpu
                    )
                    * 1000
                ),
                memory_request_mib=self.settings.chat_sandbox_memory_mib,
                memory_limit_mib=self.settings.chat_sandbox_memory_limit_mib
                or self.settings.chat_sandbox_memory_mib,
                reserved_at=now,
                billing_cycle=state.billing_cycle,
                reserved_microusd=reservation,
                updated_at=now,
            )
        )
        self.db.flush()
        return interval_id

    def provider_created(
        self, interval_id: uuid.UUID, sandbox_id: str, now: datetime | None = None
    ) -> None:
        """Attach a provider and revive an exact creation-failed reservation."""

        now = now or datetime.now(UTC)
        row = self.db.get(ChatSandboxComputeInterval, interval_id)
        if row:
            if row.reconciliation_state == "creation_failed":
                row.terminal_at = None
                row.terminal_reason = None
                row.termination_requested_at = None
                row.reserved_microusd = max(
                    row.reserved_microusd,
                    self.reservation_amount(),
                )
                row.reconciliation_state = "local"
            row.modal_sandbox_id = sandbox_id
            row.provider_created_at = now
            row.updated_at = now

    def abort_reservation(
        self, interval_id: uuid.UUID, reason: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        row = self.db.get(ChatSandboxComputeInterval, interval_id)
        if row and row.terminal_at is None:
            row.terminal_at = now
            row.terminal_reason = reason
            row.reserved_microusd = 0
            row.reconciliation_state = "creation_failed"
            row.updated_at = now

    def abort_abandoned_pool_reservations(
        self, now: datetime | None = None, *, limit: int = 100
    ) -> int:
        """Release pre-provider reservations whose durable pool owner is terminal."""

        now = now or datetime.now(UTC)
        active_pool = (
            select(ChatSandboxPool.id)
            .where(
                ChatSandboxPool.worker_generation
                == ChatSandboxComputeInterval.worker_generation,
                ChatSandboxPool.state.in_(["starting", "blank_ready", "draining"]),
            )
            .exists()
        )
        self._lock()
        rows = list(
            self.db.scalars(
                select(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.origin == "blank_pool",
                    ChatSandboxComputeInterval.modal_sandbox_id.is_(None),
                    ChatSandboxComputeInterval.provider_created_at.is_(None),
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                    ~active_pool,
                )
                .order_by(ChatSandboxComputeInterval.reserved_at)
                .limit(limit)
                .with_for_update()
            )
        )
        for row in rows:
            self.abort_reservation(row.id, "pool_owner_terminated", now)
        return len(rows)

    def abort_abandoned_direct_reservations(
        self, now: datetime | None = None, *, limit: int = 100
    ) -> int:
        """Release pre-provider reservations without a live durable lease owner."""

        now = now or datetime.now(UTC)
        active_lease = (
            select(ChatSandboxLease.chat_session_id)
            .where(
                ChatSandboxLease.chat_session_id
                == ChatSandboxComputeInterval.chat_session_id,
                ChatSandboxLease.state.in_(LIVE_LEASE_STATES),
            )
            .exists()
        )
        self._lock()
        rows = list(
            self.db.scalars(
                select(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == self.settings.environment,
                    ChatSandboxComputeInterval.origin == "direct",
                    ChatSandboxComputeInterval.chat_session_id.is_not(None),
                    ChatSandboxComputeInterval.modal_sandbox_id.is_(None),
                    ChatSandboxComputeInterval.provider_created_at.is_(None),
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                    ~active_lease,
                )
                .order_by(ChatSandboxComputeInterval.reserved_at)
                .limit(limit)
                .with_for_update()
            )
        )
        for row in rows:
            self.abort_reservation(row.id, "lease_owner_terminated", now)
        return len(rows)

    def claim(
        self, sandbox_id: str, chat_session_id: uuid.UUID, now: datetime | None = None
    ) -> None:
        row = self.db.execute(
            select(ChatSandboxComputeInterval)
            .where(ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row:
            row.chat_session_id = chat_session_id
            row.claimed_at = row.claimed_at or now or datetime.now(UTC)
            row.updated_at = now or datetime.now(UTC)

    def terminate(
        self,
        sandbox_id: str,
        reason: str | None,
        *,
        confirmed: bool,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        row = self.db.execute(
            select(ChatSandboxComputeInterval)
            .where(ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            cycle = billing_cycle(now)
            cycle_start = datetime(cycle.year, cycle.month, 1, tzinfo=UTC)
            row = ChatSandboxComputeInterval(
                id=uuid.uuid4(),
                modal_sandbox_id=sandbox_id,
                environment=self.settings.environment,
                modal_app=MODAL_APP_NAME,
                app_release_id=self.settings.release_id,
                image_version=self.settings.chat_modal_image_version,
                worker_generation="reconciled-orphan",
                origin="reconciled_orphan",
                cpu_request_millicores=round(self.settings.chat_sandbox_cpu * 1000),
                cpu_limit_millicores=round(
                    (
                        self.settings.chat_sandbox_cpu_limit
                        or self.settings.chat_sandbox_cpu
                    )
                    * 1000
                ),
                memory_request_mib=self.settings.chat_sandbox_memory_mib,
                memory_limit_mib=self.settings.chat_sandbox_memory_limit_mib
                or self.settings.chat_sandbox_memory_mib,
                reserved_at=max(
                    cycle_start,
                    now
                    - timedelta(
                        seconds=self.settings.chat_persistent_sandbox_lifetime_seconds
                    ),
                ),
                provider_created_at=None,
                billing_cycle=cycle,
                reserved_microusd=0 if confirmed else self.reservation_amount(),
                updated_at=now,
            )
            self.db.add(row)
        row.termination_requested_at = row.termination_requested_at or now
        row.terminal_reason = reason
        if confirmed:
            row.terminal_at = now
            row.reserved_microusd = 0
            row.reconciliation_state = "confirmed"
        else:
            row.reconciliation_state = "termination_uncertain"
        row.updated_at = now

    def reconcile_provider_floor(
        self, floor_microusd: int, reported_at: datetime
    ) -> ChatSandboxBudgetState:
        self._lock()
        return self._reconcile_provider_floor(
            floor_microusd,
            reported_at,
        )

    def _reconcile_provider_floor(
        self,
        floor_microusd: int,
        reported_at: datetime,
    ) -> ChatSandboxBudgetState:
        self._state(reported_at, provider_cycle_confirmed=True)
        state = self.refresh(reported_at, capacity_locked=True)
        was_degraded = state.reconciliation_state != "fresh" and (
            self.db.execute(
                select(ChatSandboxCircuitEvent.id)
                .where(
                    ChatSandboxCircuitEvent.budget_state_id == state.id,
                    ChatSandboxCircuitEvent.event_type.in_(
                        ["reconciliation_stale", "reconciliation_unavailable"]
                    ),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )
        state.provider_floor_microusd = max(
            state.provider_floor_microusd, floor_microusd
        )
        state.last_reconciled_at = reported_at
        state.reconciliation_state = "fresh"
        state.updated_at = reported_at
        # Recompute after persisting the provider coverage boundary so confirmed
        # orphan estimates from closed billing hours cannot double-count the
        # provider-authoritative floor.
        state = self.refresh(reported_at)
        if was_degraded:
            self._event(
                state,
                "reconciliation_recovered",
                "recovery",
                None,
                reported_at,
                deduplicate=False,
            )
        return state

    def claim_provider_reconciliation_exact(
        self,
        now: datetime,
    ) -> ProviderReconciliationClaim | None:
        """Claim an exact hourly provider-report generation.

        A tripped prior cycle owns the claim until a successful provider report
        proves that creating the requested cycle is safe.
        """

        requested_cycle = billing_cycle(now)
        attempted_at = now.astimezone(UTC)
        self._lock()
        current = self.db.execute(
            select(ChatSandboxBudgetState)
            .where(
                ChatSandboxBudgetState.environment == self.settings.environment,
                ChatSandboxBudgetState.billing_cycle == requested_cycle,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if current is None:
            previous = self.db.execute(
                select(ChatSandboxBudgetState)
                .where(
                    ChatSandboxBudgetState.environment == self.settings.environment,
                    ChatSandboxBudgetState.billing_cycle < requested_cycle,
                )
                .order_by(ChatSandboxBudgetState.billing_cycle.desc())
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
            if previous is not None and previous.circuit_state == "tripped":
                state = previous
            else:
                state = self.refresh(attempted_at, capacity_locked=True)
        else:
            state = self.refresh(attempted_at, capacity_locked=True)
        prior_attempt = state.last_reconciliation_attempt_at
        if prior_attempt is not None:
            prior_attempt = self._aware(prior_attempt)
            if (now - prior_attempt).total_seconds() < (
                self.settings.chat_sandbox_reconciliation_interval_seconds
            ):
                return None
        state.last_reconciliation_attempt_at = now.astimezone(UTC)
        state.updated_at = now.astimezone(UTC)
        return ProviderReconciliationClaim(
            owner_state_id=state.id,
            billing_cycle=requested_cycle,
            attempted_at=now.astimezone(UTC),
        )

    def claim_provider_reconciliation(self, now: datetime) -> bool:
        """Compatibility wrapper for the established boolean claim API."""

        return self.claim_provider_reconciliation_exact(now) is not None

    def _provider_reconciliation_owner(
        self,
        claim: ProviderReconciliationClaim,
    ) -> ChatSandboxBudgetState | None:
        """Lock and match the exact unsuperseded claim owner."""

        if billing_cycle(claim.attempted_at) != claim.billing_cycle:
            return None
        owner = self.db.execute(
            select(ChatSandboxBudgetState)
            .where(
                ChatSandboxBudgetState.id == claim.owner_state_id,
                ChatSandboxBudgetState.environment == self.settings.environment,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if (
            owner is None
            or owner.last_reconciliation_attempt_at is None
            or self._aware(owner.last_reconciliation_attempt_at) != claim.attempted_at
        ):
            return None

        latest_state_id = self.db.scalar(
            select(ChatSandboxBudgetState.id)
            .where(ChatSandboxBudgetState.environment == self.settings.environment)
            .order_by(ChatSandboxBudgetState.billing_cycle.desc())
            .limit(1)
        )
        latest_attempt = self.db.scalar(
            select(
                func.max(ChatSandboxBudgetState.last_reconciliation_attempt_at)
            ).where(ChatSandboxBudgetState.environment == self.settings.environment)
        )
        if (
            latest_state_id != owner.id
            or latest_attempt is None
            or self._aware(latest_attempt) != claim.attempted_at
        ):
            return None

        if owner.billing_cycle == claim.billing_cycle:
            return owner
        if (
            owner.billing_cycle < claim.billing_cycle
            and owner.circuit_state == "tripped"
        ):
            return owner
        return None

    def reconcile_provider_floor_for_claim(
        self,
        claim: ProviderReconciliationClaim,
        floor_microusd: int,
    ) -> ChatSandboxBudgetState | None:
        """Apply a provider floor only for the exact newest claim."""

        self._lock()
        if self._provider_reconciliation_owner(claim) is None:
            return None
        state = self._reconcile_provider_floor(
            floor_microusd,
            claim.attempted_at,
        )
        state.last_reconciliation_attempt_at = claim.attempted_at
        state.updated_at = claim.attempted_at
        return state

    def reconciliation_unavailable_for_claim(
        self,
        claim: ProviderReconciliationClaim,
    ) -> ChatSandboxBudgetState | None:
        """Mark only the exact newest claim owner unavailable."""

        self._lock()
        owner = self._provider_reconciliation_owner(claim)
        if owner is None:
            return None
        if owner.billing_cycle == claim.billing_cycle:
            owner = self.refresh(claim.attempted_at, capacity_locked=True)
        return self._mark_reconciliation_unavailable(owner, claim.attempted_at)

    def _mark_reconciliation_unavailable(
        self,
        state: ChatSandboxBudgetState,
        now: datetime,
    ) -> ChatSandboxBudgetState:
        was_unavailable = state.reconciliation_state == "unavailable"
        state.reconciliation_state = "unavailable"
        state.updated_at = now
        if not was_unavailable:
            self._event(
                state,
                "reconciliation_unavailable",
                "warning",
                "provider_budget",
                now,
                deduplicate=False,
            )
        return state

    def reconciliation_unavailable(
        self, now: datetime | None = None
    ) -> ChatSandboxBudgetState:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        return self._mark_reconciliation_unavailable(state, now)

    def record_kill_sweep(
        self, *, complete: bool, now: datetime | None = None
    ) -> ChatSandboxBudgetState:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        self._event(
            state,
            "kill_sweep_complete" if complete else "kill_sweep_incomplete",
            "recovery" if complete else "critical",
            None if complete else "termination_uncertain",
            now,
        )
        return state

    def status(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        state = self.refresh(now)
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        live = (
            self.db.execute(
                select(ChatSandboxComputeInterval).where(
                    ChatSandboxComputeInterval.environment == state.environment,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        leases = self.db.execute(
            select(ChatSandboxLease.state, func.count()).group_by(
                ChatSandboxLease.state
            )
        ).all()
        pools = self.db.execute(
            select(ChatSandboxPool.state, func.count()).group_by(ChatSandboxPool.state)
        ).all()
        live_states = {
            "starting": 0,
            "blank": 0,
            "busy": 0,
            "idle": 0,
            "draining": 0,
            "termination_uncertain": 0,
        }
        for lifecycle_state, count in leases:
            key = "draining" if lifecycle_state == "terminating" else lifecycle_state
            if key in live_states:
                live_states[key] += count
        for lifecycle_state, count in pools:
            key = {"blank_ready": "blank", "draining": "draining"}.get(
                lifecycle_state, lifecycle_state
            )
            if key in live_states:
                live_states[key] += count
        live_states["termination_uncertain"] = sum(
            row.reconciliation_state == "termination_uncertain" for row in live
        )
        cycle_start = datetime(
            state.billing_cycle.year, state.billing_cycle.month, 1, tzinfo=UTC
        )
        cycle_finish = self._aware(state.cycle_end_at)
        cycle_rows = (
            self.db.execute(
                select(ChatSandboxComputeInterval).where(
                    ChatSandboxComputeInterval.environment == state.environment,
                    ChatSandboxComputeInterval.reserved_at < cycle_finish,
                    or_(
                        ChatSandboxComputeInterval.terminal_at.is_(None),
                        ChatSandboxComputeInterval.terminal_at >= cycle_start,
                    ),
                )
            )
            .scalars()
            .all()
        )
        daily: dict[str, dict[str, int]] = {}
        for row in cycle_rows:
            if self._is_uncreated_failure(row):
                continue
            row_start = max(self._aware(row.reserved_at), cycle_start)
            row_end = min(self._metered_end(row, now), now, cycle_finish)
            cursor = row_start
            while cursor < row_end:
                next_day = datetime(
                    cursor.year,
                    cursor.month,
                    cursor.day,
                    tzinfo=UTC,
                ) + timedelta(days=1)
                segment_end = min(row_end, next_day)
                bucket = daily.setdefault(
                    cursor.date().isoformat(),
                    {"blank_pool_microusd": 0, "assigned_microusd": 0},
                )
                claimed_at = (
                    None if row.claimed_at is None else self._aware(row.claimed_at)
                )
                if row.origin == "blank_pool" and (
                    claimed_at is None or cursor < claimed_at
                ):
                    blank_end = min(segment_end, claimed_at or segment_end)
                    bucket["blank_pool_microusd"] += max(
                        0, int((blank_end - cursor).total_seconds())
                    ) * self._interval_rate(row)
                    cursor = blank_end
                    if cursor >= segment_end:
                        continue
                bucket["assigned_microusd"] += max(
                    0, int((segment_end - cursor).total_seconds())
                ) * self._interval_rate(row)
                cursor = segment_end
        events = (
            self.db.execute(
                select(ChatSandboxCircuitEvent)
                .where(ChatSandboxCircuitEvent.budget_state_id == state.id)
                .order_by(ChatSandboxCircuitEvent.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        reconciled_at = state.last_reconciled_at
        if reconciled_at is not None and reconciled_at.tzinfo is None:
            reconciled_at = reconciled_at.replace(tzinfo=UTC)
        age = (
            None
            if reconciled_at is None
            else int((now - reconciled_at).total_seconds())
        )
        reconciliation = (
            "unavailable"
            if age is None or state.reconciliation_state == "unavailable"
            else (
                "stale"
                if age > self.settings.chat_sandbox_reconciliation_stale_seconds
                else "fresh"
            )
        )
        if reconciliation == "stale" and state.reconciliation_state != "stale":
            state.reconciliation_state = "stale"
            self._event(
                state,
                "reconciliation_stale",
                "warning",
                "provider_budget",
                now,
                deduplicate=False,
            )
        recent_start = max(cycle_start, now - timedelta(hours=24))
        recent_rows = [
            row
            for row in cycle_rows
            if not self._is_uncreated_failure(row)
            and self._metered_end(row, now) > recent_start
            and self._aware(row.reserved_at) < now
        ]
        observed_start = min(
            (max(self._aware(row.reserved_at), recent_start) for row in recent_rows),
            default=now,
        )
        observed_hours = max(0.0, (now - observed_start).total_seconds() / 3600)
        burn_rate = None
        projected_cap_hit_at = None
        if len(recent_rows) >= 2 and observed_hours >= 1:
            recent_cost = sum(
                self._overlap_cost(row, recent_start, now, now) for row in recent_rows
            )
            burn_rate = round(recent_cost / observed_hours)
            if burn_rate > 0 and state.circuit_state != "tripped":
                hours_left = (
                    max(0, state.application_cap_microusd - effective) / burn_rate
                )
                projected_cap_hit_at = now + timedelta(hours=hours_left)
        prior_state = self.db.execute(
            select(ChatSandboxBudgetState)
            .where(
                ChatSandboxBudgetState.environment == state.environment,
                ChatSandboxBudgetState.billing_cycle < state.billing_cycle,
            )
            .order_by(ChatSandboxBudgetState.billing_cycle.desc())
            .limit(1)
        ).scalar_one_or_none()
        return {
            "environment": state.environment,
            "provider_mode": self.settings.chat_sandbox_provider_mode,
            "billing_cycle": state.billing_cycle.isoformat(),
            "cycle_end_at": state.cycle_end_at,
            "circuit_state": state.circuit_state,
            "trip_reason": state.trip_reason,
            "tripped_at": state.tripped_at,
            "estimated_microusd": state.estimated_accrued_microusd,
            "provider_floor_microusd": state.provider_floor_microusd,
            "effective_microusd": effective,
            "warning_microusd": state.warning_microusd,
            "application_cap_microusd": state.application_cap_microusd,
            "environment_cap_microusd": state.environment_cap_microusd or None,
            "workspace_cap_microusd": state.workspace_cap_microusd,
            "remaining_microusd": max(
                0,
                state.application_cap_microusd
                - effective
                - state.outstanding_reservation_microusd,
            ),
            "outstanding_reservation_microusd": state.outstanding_reservation_microusd,
            "last_metered_at": state.last_metered_at,
            "last_reconciled_at": state.last_reconciled_at,
            "last_reconciliation_attempt_at": state.last_reconciliation_attempt_at,
            "next_reconciliation_at": (
                self._aware(
                    state.last_reconciliation_attempt_at
                    or state.last_reconciled_at
                    or state.created_at
                )
                + timedelta(
                    seconds=self.settings.chat_sandbox_reconciliation_interval_seconds
                )
            ),
            "reconciliation_state": reconciliation,
            "live_count": len(live),
            "termination_uncertain_count": sum(
                row.reconciliation_state == "termination_uncertain" for row in live
            ),
            "live_states": live_states,
            "oldest_live_at": min((row.reserved_at for row in live), default=None),
            "burn_rate_microusd_per_hour": burn_rate,
            "projected_cap_hit_at": projected_cap_hit_at,
            "prior_cycle": (
                None
                if prior_state is None
                else {
                    "billing_cycle": prior_state.billing_cycle.isoformat(),
                    "estimated_microusd": prior_state.estimated_accrued_microusd,
                    "provider_floor_microusd": prior_state.provider_floor_microusd,
                    "effective_microusd": max(
                        prior_state.estimated_accrued_microusd,
                        prior_state.provider_floor_microusd,
                    ),
                }
            ),
            "daily_spend": [
                {"date": day, **values} for day, values in sorted(daily.items())
            ],
            "events": [
                {
                    "id": str(event.id),
                    "type": event.event_type,
                    "severity": event.severity,
                    "reason": event.reason,
                    "created_at": event.created_at,
                    "details": event.details,
                }
                for event in events
            ],
        }
