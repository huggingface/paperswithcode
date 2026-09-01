"""Durable, server-scoped evidence for protected external-Pi qualification."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Literal

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatQualificationEvidenceEvent,
    ChatQualificationScope,
    ChatSandboxComputeInterval,
    ChatTurnLatency,
)

logger = logging.getLogger(__name__)
QUALIFICATION_PROFILES = {
    "32-functional-turns": 32,
    "100-immediate-admission": 100,
}
FUNCTIONAL_QUALIFICATION_TURN_CAPACITY = 32
FUNCTIONAL_QUALIFICATION_EXECUTOR_LIVE_CAP = 16
QUALIFICATION_EVENT_TYPES = frozenset(
    {
        "admitted_no_queue",
        "executor_started",
        "stale_fence",
        "queued",
        "workspace_created",
        "workspace_reused",
        "workspace_evicted",
    }
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class QualificationEvidenceUnavailable(RuntimeError):
    """The requested exact cohort does not have complete durable evidence."""


@dataclass(frozen=True, slots=True)
class QualificationScope:
    scope_id: uuid.UUID
    run_id: str
    profile: str
    app_release_id: str
    window_started_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class QualificationContext:
    """Server-derived authority for one protected functional turn."""

    scope_id: uuid.UUID
    run_id: str
    profile: Literal["32-functional-turns"]
    workload: Literal["no_tool", "read", "bash"]
    app_release_id: str
    window_started_at: datetime
    expires_at: datetime
    turn_capacity: int = FUNCTIONAL_QUALIFICATION_TURN_CAPACITY
    executor_live_cap: int = FUNCTIONAL_QUALIFICATION_EXECUTOR_LIVE_CAP


@dataclass(frozen=True, slots=True)
class DurableQualificationEvidence:
    expected_users: int
    admitted_turns: int
    admission_denominator_events: int
    terminal_turns: int
    queued_states: int
    stale_fences: int
    executor_starts: int
    duplicate_executor_starts: int
    workspace_creates: int
    workspace_reuses: int
    workspace_evictions: int
    billed_duration_ms: int
    window_started_at_ms: int
    window_ended_at_ms: int
    source: str = "durable_qualification_records"


@dataclass(frozen=True, slots=True)
class QualificationTeardownProof:
    expected_tool_turns: int
    targeted_sessions: int
    closed_intervals: int
    eviction_events: int
    source: str = "exact_scope_canonical_eviction"


class ChatQualificationEvidenceRepository:
    def record(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        event_type: str,
        operation_id: str | None = None,
        operation_kind: str | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        if event_type not in QUALIFICATION_EVENT_TYPES:
            raise ValueError("qualification evidence event is invalid")
        if (
            event_type == "executor_started"
            and (not operation_id or operation_kind not in {"read", "bash"})
        ) or (
            event_type != "executor_started"
            and (operation_id is not None or operation_kind is not None)
        ):
            raise ValueError("qualification executor evidence is invalid")
        scope_id = db.execute(
            select(ChatTurnLatency.qualification_scope_id).where(
                ChatTurnLatency.turn_id == turn_id,
                ChatTurnLatency.chat_session_id == chat_session_id,
                ChatTurnLatency.qualification_scope_id.is_not(None),
                ChatTurnLatency.qualification_scenario == "reliability",
            )
        ).scalar_one_or_none()
        if scope_id is None:
            return False
        db.add(
            ChatQualificationEvidenceEvent(
                id=uuid.uuid4(),
                qualification_scope_id=scope_id,
                turn_id=turn_id,
                chat_session_id=chat_session_id,
                event_type=event_type,
                operation_digest=(
                    hashlib.sha256(operation_id.encode()).hexdigest()
                    if operation_id is not None
                    else None
                ),
                operation_kind=operation_kind,
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )
        return True


def record_qualification_event(**kwargs) -> bool:
    with db_manager.session_local() as db, db.begin():
        return ChatQualificationEvidenceRepository().record(db, **kwargs)


def record_qualification_event_safely(**kwargs) -> bool:
    """Preserve chat semantics for expected evidence-store outages."""
    try:
        return record_qualification_event(**kwargs)
    except (OSError, SQLAlchemyError) as error:
        logger.warning(
            "chat qualification evidence_missing event=%s error=%s",
            kwargs.get("event_type", "unknown"),
            type(error).__name__,
        )
        return False


class ChatDurableQualificationEvidenceService:
    def __init__(
        self,
        db: Session,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.now = now or (lambda: datetime.now(UTC))

    def create_scope(
        self, *, run_id: str, profile: str, settings: Settings
    ) -> QualificationScope:
        normalized = run_id.strip()
        if (
            settings.environment != "staging"
            or profile not in QUALIFICATION_PROFILES
            or not normalized
            or len(normalized) > 64
        ):
            raise QualificationEvidenceUnavailable("qualification scope is invalid")
        self.cleanup_expired(limit=500)
        started = self.now()
        scope = ChatQualificationScope(
            id=uuid.uuid4(),
            run_id=normalized,
            profile=profile,
            app_release_id=settings.release_id,
            window_started_at=started,
            expires_at=started
            + timedelta(hours=settings.chat_qualification_evidence_retention_hours),
        )
        self.db.add(scope)
        try:
            self.db.flush()
        except SQLAlchemyError:
            raise QualificationEvidenceUnavailable(
                "qualification run_id is already used"
            ) from None
        return QualificationScope(
            scope.id,
            scope.run_id,
            scope.profile,
            scope.app_release_id,
            scope.window_started_at,
            scope.expires_at,
        )

    def require_active_scope(
        self,
        scope_id: uuid.UUID,
        *,
        settings: Settings,
        lock: bool | Literal["key_share"] = False,
    ) -> ChatQualificationScope:
        return self._require_scope(
            scope_id,
            settings=settings,
            lock=lock,
            allow_ended=False,
        )

    def require_collectable_scope(
        self, scope_id: uuid.UUID, *, settings: Settings, lock: bool = False
    ) -> ChatQualificationScope:
        """Lock one exact active or teardown-closed scope for bounded evidence."""
        return self._require_scope(
            scope_id,
            settings=settings,
            lock=lock,
            allow_ended=True,
        )

    def _require_scope(
        self,
        scope_id: uuid.UUID,
        *,
        settings: Settings,
        lock: bool | Literal["key_share"],
        allow_ended: bool,
    ) -> ChatQualificationScope:
        statement = select(ChatQualificationScope).where(
            ChatQualificationScope.id == scope_id
        )
        if lock == "key_share":
            statement = statement.with_for_update(read=True, key_share=True)
        elif lock:
            statement = statement.with_for_update()
        scope = self.db.execute(statement).scalar_one_or_none()
        now = self.now()
        if (
            scope is None
            or settings.environment != "staging"
            or scope.app_release_id != settings.release_id
            or scope.profile not in QUALIFICATION_PROFILES
            or (scope.window_ended_at is not None and not allow_ended)
            or _as_utc(scope.expires_at) <= now
        ):
            raise QualificationEvidenceUnavailable("qualification scope is unavailable")
        return scope

    def require_active_context(
        self,
        scope_id: uuid.UUID,
        *,
        workload: str,
        settings: Settings,
    ) -> QualificationContext:
        scope = self.require_active_scope(scope_id, settings=settings, lock="key_share")
        if (
            not settings.chat_durable_turn_dispatch_enabled
            or scope.profile != "32-functional-turns"
            or workload not in {"no_tool", "read", "bash"}
        ):
            raise QualificationEvidenceUnavailable(
                "qualification capacity scope is unavailable"
            )
        return QualificationContext(
            scope_id=scope.id,
            run_id=scope.run_id,
            profile="32-functional-turns",
            workload=workload,
            app_release_id=scope.app_release_id,
            window_started_at=_as_utc(scope.window_started_at),
            expires_at=_as_utc(scope.expires_at),
        )

    def executor_live_cap(
        self,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        settings: Settings,
    ) -> int | None:
        """Authorize elevated executor capacity from exact persisted evidence."""

        if not self._active_functional_turn(
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            settings=settings,
            workloads=("read", "bash"),
        ):
            return None
        return FUNCTIONAL_QUALIFICATION_EXECUTOR_LIVE_CAP

    def external_pi_authorized(
        self,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        settings: Settings,
    ) -> bool:
        """Lock scope then reservation through external capability issuance."""

        if not self._active_functional_turn(
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            settings=settings,
            workloads=("no_tool", "read", "bash"),
            require_pi=True,
        ):
            return False
        from backend.services.chat_external_worker_capacity import (
            ChatExternalWorkerCapacityRepository,
            external_worker_endpoints,
        )

        ChatExternalWorkerCapacityRepository(
            environment=settings.environment
        ).require_turn(
            self.db,
            turn_id=turn_id,
            endpoints=external_worker_endpoints(settings),
            now=self.now(),
            lock=True,
        )
        return True

    def _active_functional_turn(
        self,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        settings: Settings,
        workloads: tuple[str, ...],
        require_pi: bool = False,
    ) -> bool:
        if settings.environment != "staging":
            return False
        latency_filters = [
            ChatTurnLatency.turn_id == turn_id,
            ChatTurnLatency.chat_session_id == chat_session_id,
            ChatTurnLatency.qualification_profile == "32-functional-turns",
            ChatTurnLatency.qualification_workload.in_(workloads),
            ChatTurnLatency.qualification_scenario == "reliability",
            ChatTurnLatency.app_release_id == settings.release_id,
        ]
        if require_pi:
            latency_filters.extend(
                (
                    ChatTurnLatency.agent_harness == "pi",
                    ChatTurnLatency.execution_backend == "modal_cli",
                )
            )
        scope_id = self.db.scalar(
            select(ChatTurnLatency.qualification_scope_id).where(*latency_filters)
        )
        if scope_id is None:
            return False
        # Lock order is scope -> reservation -> capability for reconstructed Pi
        # runners, and scope -> capacity -> sandbox lease for executor acquisition.
        # The caller transaction retains this row lock through the final mutation.
        try:
            scope = self.require_active_scope(scope_id, settings=settings, lock=True)
        except QualificationEvidenceUnavailable:
            return False
        if scope.profile != "32-functional-turns":
            return False
        latency = self.db.scalar(
            select(ChatTurnLatency).where(
                *latency_filters,
                ChatTurnLatency.qualification_scope_id == scope.id,
            )
        )
        if latency is None:
            return False
        now = self.now()
        if (
            latency.qualification_run_id != scope.run_id
            or _as_utc(scope.expires_at) <= now
            or _as_utc(latency.admitted_at) < _as_utc(scope.window_started_at)
        ):
            return False
        return True

    def collect(
        self,
        *,
        scope_id: uuid.UUID,
        settings: Settings,
    ) -> DurableQualificationEvidence:
        scope = self.require_collectable_scope(scope_id, settings=settings, lock=True)
        ended = _as_utc(scope.window_ended_at) if scope.window_ended_at else self.now()
        if scope.window_ended_at is None:
            scope.window_ended_at = ended
            self.db.flush()
        started = _as_utc(scope.window_started_at)
        expected_users = QUALIFICATION_PROFILES[scope.profile]
        latency_rows = self.db.execute(
            select(
                ChatTurnLatency.turn_id,
                ChatTurnLatency.chat_session_id,
                ChatTurnLatency.terminal_status,
                ChatTurnLatency.qualification_workload,
            ).where(
                ChatTurnLatency.qualification_scope_id == scope.id,
                ChatTurnLatency.qualification_run_id == scope.run_id,
                ChatTurnLatency.qualification_profile == scope.profile,
                ChatTurnLatency.qualification_scenario == "reliability",
                ChatTurnLatency.app_release_id == scope.app_release_id,
                ChatTurnLatency.admitted_at >= started,
                ChatTurnLatency.admitted_at <= ended,
            )
        ).all()
        session_ids = {row.chat_session_id for row in latency_rows}
        turn_ids = {row.turn_id for row in latency_rows}
        turn_sessions = {row.turn_id: row.chat_session_id for row in latency_rows}
        if len(latency_rows) != expected_users or len(session_ids) != expected_users:
            raise QualificationEvidenceUnavailable(
                "qualification cohort evidence is incomplete"
            )
        terminal_turns = sum(row.terminal_status == "complete" for row in latency_rows)
        if terminal_turns != expected_users:
            raise QualificationEvidenceUnavailable(
                "qualification terminal evidence is incomplete"
            )
        workload_counts = Counter(row.qualification_workload for row in latency_rows)
        expected_workloads = (
            {"no_tool": 16, "read": 8, "bash": 8}
            if scope.profile == "32-functional-turns"
            else {"no_tool": 100}
        )
        if dict(workload_counts) != expected_workloads:
            raise QualificationEvidenceUnavailable(
                "qualification workload evidence is incomplete"
            )
        events = self.db.execute(
            select(
                ChatQualificationEvidenceEvent.turn_id,
                ChatQualificationEvidenceEvent.chat_session_id,
                ChatQualificationEvidenceEvent.event_type,
                ChatQualificationEvidenceEvent.operation_digest,
                ChatQualificationEvidenceEvent.operation_kind,
            ).where(
                ChatQualificationEvidenceEvent.qualification_scope_id == scope.id,
                ChatQualificationEvidenceEvent.turn_id.in_(turn_ids),
                ChatQualificationEvidenceEvent.occurred_at >= started,
                ChatQualificationEvidenceEvent.occurred_at <= ended,
            )
        ).all()
        if any(turn_sessions.get(row.turn_id) != row.chat_session_id for row in events):
            raise QualificationEvidenceUnavailable(
                "qualification cohort evidence collides"
            )
        event_counts = Counter(row.event_type for row in events)
        per_turn_event_counts = Counter((row.turn_id, row.event_type) for row in events)
        denominator_turns = {
            row.turn_id for row in events if row.event_type == "admitted_no_queue"
        }
        if (
            event_counts["admitted_no_queue"] != expected_users
            or denominator_turns != turn_ids
        ):
            raise QualificationEvidenceUnavailable(
                "qualification admission evidence is incomplete"
            )
        operations = Counter(
            (row.turn_id, row.operation_digest)
            for row in events
            if row.event_type == "executor_started"
        )
        intervals = self.db.execute(
            select(
                ChatSandboxComputeInterval.chat_session_id,
                ChatSandboxComputeInterval.reserved_at,
                ChatSandboxComputeInterval.provider_created_at,
                ChatSandboxComputeInterval.terminal_at,
                ChatSandboxComputeInterval.app_release_id,
            ).where(ChatSandboxComputeInterval.chat_session_id.in_(session_ids))
        ).all()
        if any(interval.terminal_at is None for interval in intervals):
            raise QualificationEvidenceUnavailable(
                "qualification sandbox intervals are still open"
            )
        billed_duration_ms = 0
        interval_counts_by_session: Counter[uuid.UUID] = Counter()
        for interval in intervals:
            interval_started = _as_utc(
                interval.provider_created_at or interval.reserved_at
            )
            interval_ended = _as_utc(interval.terminal_at)
            overlap_start = max(interval_started, started)
            overlap_end = min(interval_ended, ended)
            if overlap_end > overlap_start:
                if interval.app_release_id != scope.app_release_id:
                    raise QualificationEvidenceUnavailable(
                        "qualification sandbox evidence collides"
                    )
                interval_counts_by_session[interval.chat_session_id] += 1
                billed_duration_ms += round(
                    (overlap_end - overlap_start).total_seconds() * 1_000
                )
        for row in latency_rows:
            is_tool_turn = row.qualification_workload in {"read", "bash"}
            executor_starts = per_turn_event_counts[(row.turn_id, "executor_started")]
            acquisitions = sum(
                per_turn_event_counts[(row.turn_id, event_type)]
                for event_type in ("workspace_created", "workspace_reused")
            )
            evictions = per_turn_event_counts[(row.turn_id, "workspace_evicted")]
            interval_count = interval_counts_by_session[row.chat_session_id]
            expected = 1 if is_tool_turn else 0
            operation_kinds = [
                event.operation_kind
                for event in events
                if event.turn_id == row.turn_id
                and event.event_type == "executor_started"
            ]
            if (
                executor_starts != expected
                or acquisitions != expected
                or evictions != expected
                or interval_count != expected
            ):
                raise QualificationEvidenceUnavailable(
                    "qualification per-turn evidence is incomplete"
                )
            if operation_kinds != (
                [row.qualification_workload] if is_tool_turn else []
            ):
                raise QualificationEvidenceUnavailable(
                    "qualification operation kind evidence is incomplete"
                )
        return DurableQualificationEvidence(
            expected_users=expected_users,
            admitted_turns=len(latency_rows),
            admission_denominator_events=event_counts["admitted_no_queue"],
            terminal_turns=terminal_turns,
            queued_states=event_counts["queued"],
            stale_fences=event_counts["stale_fence"],
            executor_starts=event_counts["executor_started"],
            duplicate_executor_starts=sum(count - 1 for count in operations.values()),
            workspace_creates=event_counts["workspace_created"],
            workspace_reuses=event_counts["workspace_reused"],
            workspace_evictions=event_counts["workspace_evicted"],
            billed_duration_ms=billed_duration_ms,
            window_started_at_ms=round(started.timestamp() * 1_000),
            window_ended_at_ms=round(ended.timestamp() * 1_000),
        )

    async def teardown_scope(
        self,
        *,
        scope_id: uuid.UUID,
        settings: Settings,
        sandbox_manager,
    ) -> QualificationTeardownProof:
        scope = self._require_scope(
            scope_id,
            settings=settings,
            lock=True,
            allow_ended=True,
        )
        close_window = scope.window_ended_at is None
        rows = self.db.execute(
            select(
                ChatTurnLatency.turn_id,
                ChatTurnLatency.chat_session_id,
                ChatTurnLatency.qualification_workload,
                ChatTurnLatency.terminal_status,
            ).where(
                ChatTurnLatency.qualification_scope_id == scope.id,
                ChatTurnLatency.qualification_run_id == scope.run_id,
                ChatTurnLatency.qualification_profile == scope.profile,
                ChatTurnLatency.qualification_scenario == "reliability",
                ChatTurnLatency.app_release_id == scope.app_release_id,
            )
        ).all()
        expected_users = QUALIFICATION_PROFILES[scope.profile]
        expected_workloads = (
            {"no_tool": 16, "read": 8, "bash": 8}
            if scope.profile == "32-functional-turns"
            else {"no_tool": 100}
        )
        if (
            len(rows) != expected_users
            or len({row.chat_session_id for row in rows}) != expected_users
            or Counter(row.qualification_workload for row in rows) != expected_workloads
            or any(row.terminal_status != "complete" for row in rows)
        ):
            raise QualificationEvidenceUnavailable(
                "qualification teardown cohort is incomplete"
            )
        tool_rows = tuple(
            row for row in rows if row.qualification_workload in {"read", "bash"}
        )
        for row in tool_rows:
            try:
                await sandbox_manager.snapshot_and_terminate(row.chat_session_id)
            except Exception:
                raise QualificationEvidenceUnavailable(
                    "qualification teardown failed"
                ) from None

        self.db.expire_all()
        interval_rows = self.db.execute(
            select(
                ChatSandboxComputeInterval.chat_session_id,
                ChatSandboxComputeInterval.terminal_at,
                ChatSandboxComputeInterval.app_release_id,
            ).where(
                ChatSandboxComputeInterval.chat_session_id.in_(
                    tuple(row.chat_session_id for row in tool_rows)
                )
            )
        ).all()
        intervals_by_session = Counter(row.chat_session_id for row in interval_rows)
        if (
            len(interval_rows) != len(tool_rows)
            or any(
                row.app_release_id != scope.app_release_id or row.terminal_at is None
                for row in interval_rows
            )
            or any(intervals_by_session[row.chat_session_id] != 1 for row in tool_rows)
        ):
            raise QualificationEvidenceUnavailable(
                "qualification teardown intervals are incomplete"
            )
        eviction_rows = self.db.execute(
            select(
                ChatQualificationEvidenceEvent.turn_id,
                ChatQualificationEvidenceEvent.chat_session_id,
            ).where(
                ChatQualificationEvidenceEvent.qualification_scope_id == scope.id,
                ChatQualificationEvidenceEvent.event_type == "workspace_evicted",
            )
        ).all()
        tool_turn_sessions = {row.turn_id: row.chat_session_id for row in tool_rows}
        if any(
            tool_turn_sessions.get(row.turn_id) != row.chat_session_id
            for row in eviction_rows
        ):
            raise QualificationEvidenceUnavailable(
                "qualification teardown evidence collides"
            )
        eviction_counts = Counter(row.turn_id for row in eviction_rows)
        occurred_at = self.now()
        for row in tool_rows:
            if eviction_counts[row.turn_id] == 0:
                self.db.add(
                    ChatQualificationEvidenceEvent(
                        id=uuid.uuid4(),
                        qualification_scope_id=scope.id,
                        turn_id=row.turn_id,
                        chat_session_id=row.chat_session_id,
                        event_type="workspace_evicted",
                        occurred_at=occurred_at,
                    )
                )
        if close_window:
            scope.window_ended_at = self.now()
        self.db.flush()
        expected_tool_turns = len(tool_rows)
        return QualificationTeardownProof(
            expected_tool_turns=expected_tool_turns,
            targeted_sessions=expected_tool_turns,
            closed_intervals=expected_tool_turns,
            eviction_events=expected_tool_turns,
        )

    def cleanup_scope(self, scope_id: uuid.UUID) -> bool:
        result = self.db.execute(
            delete(ChatQualificationScope).where(ChatQualificationScope.id == scope_id)
        )
        return bool(result.rowcount)

    def cleanup_expired(self, *, limit: int = 500) -> int:
        if type(limit) is not int or not 1 <= limit <= 1_000:
            raise ValueError("qualification cleanup limit is invalid")
        expired_ids = self.db.execute(
            select(ChatQualificationScope.id)
            .where(ChatQualificationScope.expires_at < self.now())
            .order_by(ChatQualificationScope.expires_at)
            .limit(limit)
        ).scalars()
        ids = tuple(expired_ids)
        if not ids:
            return 0
        return int(
            self.db.execute(
                delete(ChatQualificationScope).where(ChatQualificationScope.id.in_(ids))
            ).rowcount
            or 0
        )
