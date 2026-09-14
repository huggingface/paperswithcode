"""Atomic capacity and spend reservations for persistent executor turns."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatOpenAIProviderCall,
    ChatOpenRouterProviderCall,
    ChatTurnAdmissionBudget,
    ChatTurnReservation,
)

TURN_LIMIT = 32
ENVIRONMENT_LIMIT = 32
OPERATIONS_PER_TURN = 4
OPERATION_LIMIT = TURN_LIMIT * OPERATIONS_PER_TURN
ACTIVE_STATES = frozenset({"reserved", "dispatched"})
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class TurnReservationError(RuntimeError):
    code = "turn_reservation_failed"


class AccountBusy(TurnReservationError):
    code = "account_busy"


class CapacityOverloaded(TurnReservationError):
    code = "capacity_overloaded"


class SpendUnavailable(TurnReservationError):
    code = "spend_unavailable"


@dataclass(frozen=True, slots=True)
class TurnReservation:
    turn_id: uuid.UUID
    request_id: str
    owner_id: str
    transport: str
    revision: int
    state: str
    reserved_microusd: int


class ChatTurnAdmissionService:
    """Reserve fixed executor capacity and bounded incremental spend."""

    def __init__(self, *, environment: str, spend_limit_microusd: int) -> None:
        if environment not in {"staging", "production"}:
            raise ValueError("Turn reservation environment is invalid")
        if spend_limit_microusd <= 0:
            raise ValueError("Turn reservation spend limit is invalid")
        self.environment = environment
        self.spend_limit_microusd = spend_limit_microusd

    def initialize(self, db: Session, *, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("Turn reservation timestamp is invalid")
        row = db.get(ChatTurnAdmissionBudget, self.environment)
        if row is None:
            db.add(
                ChatTurnAdmissionBudget(
                    environment=self.environment,
                    turn_limit=TURN_LIMIT,
                    environment_limit=ENVIRONMENT_LIMIT,
                    operation_limit=OPERATION_LIMIT,
                    spend_limit_microusd=self.spend_limit_microusd,
                    active_turns=0,
                    reserved_environments=0,
                    reserved_operations=0,
                    reserved_microusd=0,
                    spent_microusd=0,
                    updated_at=now,
                )
            )
            db.flush()
        elif row.spend_limit_microusd != self.spend_limit_microusd:
            raise ValueError("Turn reservation spend limit changed")

    def reserve(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        request_id: str,
        owner_id: str,
        reserve_microusd: int,
        now: datetime,
        transport: str = "legacy",
    ) -> TurnReservation:
        self._validate_request(
            turn_id, request_id, owner_id, reserve_microusd, now, transport
        )
        existing = db.scalar(
            select(ChatTurnReservation).where(
                ChatTurnReservation.request_id == request_id
            )
        )
        if existing is not None:
            if (
                existing.turn_id != turn_id
                or existing.owner_id != owner_id
                or existing.environment != self.environment
                or existing.transport != transport
            ):
                raise ValueError("Turn reservation identity was reused")
            return self._result(existing)
        if (
            db.scalar(
                select(ChatTurnReservation.turn_id).where(
                    ChatTurnReservation.environment == self.environment,
                    ChatTurnReservation.owner_id == owner_id,
                    ChatTurnReservation.state.in_(ACTIVE_STATES),
                )
            )
            is not None
        ):
            raise AccountBusy("Account already has an active turn")

        row = ChatTurnReservation(
            turn_id=turn_id,
            request_id=request_id,
            owner_id=owner_id,
            environment=self.environment,
            transport=transport,
            state="reserved",
            revision=1,
            reserved_turns=1,
            reserved_environments=1,
            reserved_operations=OPERATIONS_PER_TURN,
            reserved_microusd=reserve_microusd,
            actual_microusd=None,
            terminal_outcome=None,
            resource_started_at=None,
            resource_ended_at=None,
            reserved_at=now,
            dispatched_at=None,
            settled_at=None,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as error:
            raise AccountBusy("Account already has an active turn") from error

        changed = db.execute(
            update(ChatTurnAdmissionBudget)
            .where(
                ChatTurnAdmissionBudget.environment == self.environment,
                ChatTurnAdmissionBudget.active_turns < TURN_LIMIT,
                ChatTurnAdmissionBudget.reserved_environments < ENVIRONMENT_LIMIT,
                ChatTurnAdmissionBudget.reserved_operations
                <= OPERATION_LIMIT - OPERATIONS_PER_TURN,
                ChatTurnAdmissionBudget.reserved_microusd
                + ChatTurnAdmissionBudget.spent_microusd
                <= ChatTurnAdmissionBudget.spend_limit_microusd - reserve_microusd,
            )
            .values(
                active_turns=ChatTurnAdmissionBudget.active_turns + 1,
                reserved_environments=ChatTurnAdmissionBudget.reserved_environments + 1,
                reserved_operations=ChatTurnAdmissionBudget.reserved_operations
                + OPERATIONS_PER_TURN,
                reserved_microusd=ChatTurnAdmissionBudget.reserved_microusd
                + reserve_microusd,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            db.delete(row)
            db.flush()
            budget = self._budget(db)
            if budget.active_turns >= TURN_LIMIT:
                raise CapacityOverloaded("Turn capacity is full")
            raise SpendUnavailable("Turn spend capacity is full")
        return self._result(row)

    def mark_resource_started(
        self, db: Session, *, turn_id: uuid.UUID, now: datetime
    ) -> None:
        if now.tzinfo is None:
            raise ValueError("Turn resource timestamp is invalid")
        row = self._reservation(db, turn_id)
        if row.state not in ACTIVE_STATES:
            raise ValueError("Turn resource start is stale")
        row.resource_started_at = row.resource_started_at or now
        db.flush()

    def mark_resource_ended_and_reconcile(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        cost_per_second_microusd: int,
        now: datetime,
    ) -> bool:
        if cost_per_second_microusd <= 0 or now.tzinfo is None:
            raise ValueError("Turn resource settlement is invalid")
        row = self._reservation(db, turn_id)
        if row.resource_started_at is None:
            raise ValueError("Turn resource was not started")
        row.resource_ended_at = row.resource_ended_at or now
        if self._aware(row.resource_ended_at) < self._aware(row.resource_started_at):
            raise ValueError("Turn resource settlement is invalid")
        db.flush()
        if row.terminal_outcome is None:
            return False
        return self.settle(
            db,
            turn_id=turn_id,
            revision=row.revision,
            outcome=row.terminal_outcome,
            actual_microusd=self._actual_cost(db, row, cost_per_second_microusd),
            now=now,
        )

    def settle_terminal(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        revision: int,
        outcome: str,
        cost_per_second_microusd: int,
        now: datetime,
    ) -> bool:
        if outcome not in TERMINAL_STATES or cost_per_second_microusd <= 0:
            raise ValueError("Turn terminal settlement is invalid")
        row = self._reservation(db, turn_id)
        if row.revision != revision:
            return False
        if row.terminal_outcome is not None and row.terminal_outcome != outcome:
            raise ValueError("Turn terminal outcome changed")
        row.terminal_outcome = outcome
        actual = self._actual_cost(db, row, cost_per_second_microusd)
        return self.settle(
            db,
            turn_id=turn_id,
            revision=revision,
            outcome=outcome,
            actual_microusd=actual,
            now=now,
        )

    def reconcile_cost_unknown(
        self,
        db: Session,
        *,
        cost_per_second_microusd: int,
        now: datetime,
        batch_size: int = 100,
    ) -> int:
        if cost_per_second_microusd <= 0 or not 1 <= batch_size <= 500:
            raise ValueError("Turn reconciliation bounds are invalid")
        turn_ids = db.scalars(
            select(ChatTurnReservation.turn_id)
            .where(
                ChatTurnReservation.environment == self.environment,
                ChatTurnReservation.state == "cost_unknown",
                ChatTurnReservation.terminal_outcome.is_not(None),
            )
            .order_by(ChatTurnReservation.settled_at)
            .limit(batch_size)
        ).all()
        reconciled = 0
        for turn_id in turn_ids:
            row = self._reservation(db, turn_id)
            actual = self._actual_cost(db, row, cost_per_second_microusd)
            if actual is not None and self.settle(
                db,
                turn_id=turn_id,
                revision=row.revision,
                outcome=row.terminal_outcome,
                actual_microusd=actual,
                now=now,
            ):
                reconciled += 1
        return reconciled

    def mark_dispatched(
        self, db: Session, *, turn_id: uuid.UUID, revision: int, now: datetime
    ) -> TurnReservation:
        row = self._reservation(db, turn_id)
        if row.revision == revision and row.state == "dispatched":
            return self._result(row)
        if row.revision != revision or row.state != "reserved":
            raise ValueError("Turn reservation dispatch is stale")
        row.state = "dispatched"
        row.dispatched_at = now
        row.revision += 1
        db.flush()
        return self._result(row)

    def reserve_increment(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        revision: int,
        amount_microusd: int,
        now: datetime,
    ) -> TurnReservation:
        if amount_microusd <= 0:
            raise ValueError("Incremental spend reservation is invalid")
        row = self._reservation(db, turn_id)
        if row.revision != revision or row.state not in ACTIVE_STATES:
            raise ValueError("Incremental spend reservation is stale")
        changed = db.execute(
            update(ChatTurnAdmissionBudget)
            .where(
                ChatTurnAdmissionBudget.environment == self.environment,
                ChatTurnAdmissionBudget.reserved_microusd
                + ChatTurnAdmissionBudget.spent_microusd
                <= ChatTurnAdmissionBudget.spend_limit_microusd - amount_microusd,
            )
            .values(
                reserved_microusd=ChatTurnAdmissionBudget.reserved_microusd
                + amount_microusd,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise SpendUnavailable("Incremental spend capacity is full")
        row.reserved_microusd += amount_microusd
        row.revision += 1
        db.flush()
        return self._result(row)

    def settle(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        revision: int,
        outcome: str,
        actual_microusd: int | None,
        now: datetime,
    ) -> bool:
        if outcome not in TERMINAL_STATES or (
            actual_microusd is not None and actual_microusd < 0
        ):
            raise ValueError("Turn reservation settlement is invalid")
        row = self._reservation(db, turn_id)
        if row.revision != revision:
            return False
        if row.state in TERMINAL_STATES:
            return False
        if actual_microusd is not None and actual_microusd > row.reserved_microusd:
            raise SpendUnavailable("Actual spend exceeded its reservation")
        budget = self._budget(db, lock=True)
        if row.state in ACTIVE_STATES:
            budget.active_turns -= 1
            budget.reserved_environments -= 1
            budget.reserved_operations -= OPERATIONS_PER_TURN
        if actual_microusd is None:
            if row.state == "cost_unknown":
                return False
            row.state = "cost_unknown"
        else:
            budget.reserved_microusd -= row.reserved_microusd
            budget.spent_microusd += actual_microusd
            row.state = outcome
            row.actual_microusd = actual_microusd
        row.settled_at = now
        row.revision += 1
        budget.updated_at = now
        db.flush()
        return True

    def _budget(self, db: Session, *, lock: bool = False) -> ChatTurnAdmissionBudget:
        statement = select(ChatTurnAdmissionBudget).where(
            ChatTurnAdmissionBudget.environment == self.environment
        )
        if lock:
            statement = statement.with_for_update()
        row = db.scalar(statement)
        if row is None:
            raise RuntimeError("Turn admission budget is not initialized")
        return row

    def _reservation(self, db: Session, turn_id: uuid.UUID) -> ChatTurnReservation:
        row = db.scalar(
            select(ChatTurnReservation)
            .where(ChatTurnReservation.turn_id == turn_id)
            .with_for_update()
        )
        if row is None or row.environment != self.environment:
            raise ValueError("Turn reservation is missing")
        return row

    @staticmethod
    def _resource_cost(row: ChatTurnReservation, cost_per_second_microusd: int) -> int:
        if row.resource_started_at is None or row.resource_ended_at is None:
            raise ValueError("Turn resource cost is not ready")
        seconds = max(
            0,
            math.ceil(
                (
                    ChatTurnAdmissionService._aware(row.resource_ended_at)
                    - ChatTurnAdmissionService._aware(row.resource_started_at)
                ).total_seconds()
            ),
        )
        return seconds * cost_per_second_microusd

    @staticmethod
    def _provider_cost(db: Session, turn_id: uuid.UUID) -> int | None:
        actual = 0
        for model in (ChatOpenRouterProviderCall, ChatOpenAIProviderCall):
            rows = db.scalars(select(model).where(model.turn_id == turn_id)).all()
            for row in rows:
                if row.state in {"dispatched", "cost_unknown"}:
                    return None
                if row.state == "settled":
                    if row.actual_microusd is None:
                        return None
                    actual += row.actual_microusd
        return actual

    @classmethod
    def _actual_cost(
        cls,
        db: Session,
        row: ChatTurnReservation,
        cost_per_second_microusd: int,
    ) -> int | None:
        provider_cost = cls._provider_cost(db, row.turn_id)
        if provider_cost is None:
            return None
        if row.resource_started_at is None:
            return provider_cost
        if row.resource_ended_at is None:
            return None
        return provider_cost + cls._resource_cost(row, cost_per_second_microusd)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _validate_request(
        turn_id: uuid.UUID,
        request_id: str,
        owner_id: str,
        reserve_microusd: int,
        now: datetime,
        transport: str,
    ) -> None:
        if (
            not isinstance(turn_id, uuid.UUID)
            or not request_id
            or len(request_id) > 200
            or not owner_id
            or len(owner_id) > 255
            or reserve_microusd < 0
            or now.tzinfo is None
            or transport not in {"legacy", "persistent"}
        ):
            raise ValueError("Turn reservation request is invalid")

    @staticmethod
    def _result(row: ChatTurnReservation) -> TurnReservation:
        return TurnReservation(
            turn_id=row.turn_id,
            request_id=row.request_id,
            owner_id=row.owner_id,
            transport=row.transport,
            revision=row.revision,
            state=row.state,
            reserved_microusd=row.reserved_microusd,
        )
