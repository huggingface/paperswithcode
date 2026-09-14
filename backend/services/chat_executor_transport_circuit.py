"""Database-shared circuit breaker for persistent executor admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatExecutorTransportAlert,
    ChatExecutorTransportCircuit,
)

ROUTE_HEALTH_MAX_SECONDS = 5
FAILURE_WINDOW_SECONDS = 60
FAILURES_TO_OPEN = 3
OPEN_SECONDS = 30
HALF_OPEN_SUCCESSES_TO_CLOSE = 3
CANARY_LEASE_SECONDS = 30


@dataclass(frozen=True, slots=True)
class CircuitDecision:
    transport: str
    state: str
    epoch: int
    canary: bool = False


class ChatTransportUnavailable(RuntimeError):
    code = "chat_unavailable"


class ExecutorTransportCircuit:
    def __init__(self, *, environment: str) -> None:
        if environment not in {"staging", "production"}:
            raise ValueError("Executor circuit environment is invalid")
        self.environment = environment

    def initialize(self, db: Session, *, now: datetime) -> None:
        now = self._database_now(db, test_now=now)
        if db.get(ChatExecutorTransportCircuit, self.environment) is None:
            try:
                with db.begin_nested():
                    db.add(
                        ChatExecutorTransportCircuit(
                            environment=self.environment,
                            state="closed",
                            revision=1,
                            epoch=0,
                            consecutive_failures=0,
                            failure_window_started_at=None,
                            opened_at=None,
                            open_until=None,
                            canary_owner=None,
                            canary_expires_at=None,
                            half_open_successes=0,
                            security_reason=None,
                            updated_at=now,
                        )
                    )
                    db.flush()
            except IntegrityError:
                # Another API worker created the one environment row.
                if db.get(ChatExecutorTransportCircuit, self.environment) is None:
                    raise

    def choose(
        self,
        db: Session,
        *,
        remote_enabled: bool,
        route_health_seconds: float | None,
        canary_owner: str,
        now: datetime,
        legacy_available: bool = True,
    ) -> CircuitDecision:
        now = self._database_now(db, test_now=now)
        if (
            not remote_enabled
            or route_health_seconds is None
            or route_health_seconds > ROUTE_HEALTH_MAX_SECONDS
        ):
            row = self._row(db, lock=True)
            return self._legacy(row, available=legacy_available)
        row = self._row(db, lock=True)
        if row.state == "closed":
            return CircuitDecision("persistent", row.state, row.epoch)
        if row.state == "security_hold":
            return self._legacy(row, available=legacy_available)
        if row.state == "open":
            if row.open_until is None or now < self._aware(row.open_until):
                return self._legacy(row, available=legacy_available)
            row.state = "half_open"
            row.canary_owner = None
            row.canary_expires_at = None
            row.half_open_successes = 0
        if (
            row.canary_owner is None
            or row.canary_expires_at is None
            or self._aware(row.canary_expires_at) <= now
            or row.canary_owner == canary_owner
        ):
            row.canary_owner = canary_owner
            row.canary_expires_at = now + timedelta(seconds=CANARY_LEASE_SECONDS)
            row.updated_at = now
            row.revision += 1
            db.flush()
            return CircuitDecision("persistent", row.state, row.epoch, canary=True)
        return self._legacy(row, available=legacy_available)

    def record_attach_failure(
        self, db: Session, *, now: datetime, canary_owner: str | None = None
    ) -> bool:
        now = self._database_now(db, test_now=now)
        row = self._row(db, lock=True)
        if row.state == "security_hold":
            return False
        if row.state == "half_open":
            if canary_owner != row.canary_owner:
                return False
            self._open(db, row, now)
            row.updated_at = now
            row.revision += 1
            db.flush()
            return True
        if row.state == "open":
            return False
        if row.failure_window_started_at is None or now - self._aware(
            row.failure_window_started_at
        ) > timedelta(seconds=FAILURE_WINDOW_SECONDS):
            row.failure_window_started_at = now
            row.consecutive_failures = 1
        else:
            row.consecutive_failures += 1
        opened = row.consecutive_failures >= FAILURES_TO_OPEN
        if opened:
            self._open(db, row, now)
        row.updated_at = now
        row.revision += 1
        db.flush()
        return opened

    def record_success(
        self, db: Session, *, now: datetime, canary_owner: str | None = None
    ) -> bool:
        now = self._database_now(db, test_now=now)
        row = self._row(db, lock=True)
        if row.state == "closed":
            row.consecutive_failures = 0
            row.failure_window_started_at = None
            row.updated_at = now
            row.revision += 1
            db.flush()
            return False
        if row.state != "half_open" or canary_owner != row.canary_owner:
            return False
        row.half_open_successes += 1
        closed = row.half_open_successes >= HALF_OPEN_SUCCESSES_TO_CLOSE
        if closed:
            row.state = "closed"
            row.consecutive_failures = 0
            row.failure_window_started_at = None
            row.opened_at = None
            row.open_until = None
            row.canary_owner = None
            row.canary_expires_at = None
            row.half_open_successes = 0
            self._enqueue_alert(db, row, transition="recovered", now=now)
        row.updated_at = now
        row.revision += 1
        db.flush()
        return closed

    def security_hold(self, db: Session, *, reason: str, now: datetime) -> int:
        now = self._database_now(db, test_now=now)
        if not reason or len(reason) > 64:
            raise ValueError("Security hold reason is invalid")
        row = self._row(db, lock=True)
        if row.state != "security_hold":
            row.epoch += 1
        row.state = "security_hold"
        row.security_reason = reason
        row.open_until = None
        row.canary_owner = None
        row.canary_expires_at = None
        row.updated_at = now
        row.revision += 1
        self._enqueue_alert(db, row, transition="security_hold", now=now)
        db.flush()
        return row.epoch

    def clear_security_hold(
        self,
        db: Session,
        *,
        replacement_credentials_proven: bool,
        affected_live_generations: int,
        now: datetime,
    ) -> bool:
        now = self._database_now(db, test_now=now)
        row = self._row(db, lock=True)
        if row.state != "security_hold":
            return False
        if not replacement_credentials_proven or affected_live_generations != 0:
            return False
        row.state = "closed"
        row.security_reason = None
        row.consecutive_failures = 0
        row.failure_window_started_at = None
        row.updated_at = now
        row.revision += 1
        self._enqueue_alert(db, row, transition="recovered", now=now)
        db.flush()
        return True

    @classmethod
    def _open(
        cls, db: Session, row: ChatExecutorTransportCircuit, now: datetime
    ) -> None:
        row.state = "open"
        row.epoch += 1
        row.opened_at = now
        row.open_until = now + timedelta(seconds=OPEN_SECONDS)
        row.canary_owner = None
        row.canary_expires_at = None
        row.half_open_successes = 0
        cls._enqueue_alert(db, row, transition="open", now=now)

    @staticmethod
    def _enqueue_alert(
        db: Session,
        row: ChatExecutorTransportCircuit,
        *,
        transition: str,
        now: datetime,
    ) -> None:
        event_id = f"executor-circuit:{row.environment}:{row.epoch}:{transition}"
        if db.get(ChatExecutorTransportAlert, event_id) is not None:
            return
        db.add(
            ChatExecutorTransportAlert(
                event_id=event_id,
                environment=row.environment,
                epoch=row.epoch,
                transition=transition,
                delivery_state="pending",
                claim_owner=None,
                claim_expires_at=None,
                attempts=0,
                next_attempt_at=now,
                acknowledged_at=None,
                created_at=now,
            )
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _legacy(
        row: ChatExecutorTransportCircuit, *, available: bool
    ) -> CircuitDecision:
        if not available:
            raise ChatTransportUnavailable("Chat is temporarily unavailable")
        return CircuitDecision("legacy", row.state, row.epoch)

    @classmethod
    def _database_now(
        cls, db: Session, *, test_now: datetime | None = None
    ) -> datetime:
        """Use PostgreSQL time; deterministic injection is SQLite-test-only."""

        dialect = db.get_bind().dialect.name
        if test_now is not None and dialect == "sqlite":
            return cls._aware(test_now)
        value = db.scalar(select(func.current_timestamp()))
        if value is None:
            raise RuntimeError("Executor transport circuit clock is unavailable")
        return cls._aware(value)

    def _row(self, db: Session, *, lock: bool) -> ChatExecutorTransportCircuit:
        statement = select(ChatExecutorTransportCircuit).where(
            ChatExecutorTransportCircuit.environment == self.environment
        )
        if lock:
            statement = statement.with_for_update()
        row = db.scalar(statement)
        if row is None:
            raise RuntimeError("Executor transport circuit is not initialized")
        return row
