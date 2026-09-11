"""Content-free persistence for deployed chat latency measurements."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatMessageRecord,
    ChatSession,
    ChatTurnJob,
    ChatTurnLatency,
)
from backend.services.chat_sandbox_provider import (
    ATTEMPT_KINDS,
    sanitized_failure_class,
    sanitized_failure_stage,
)
from backend.services.chat_turn_lifecycle import NONTERMINAL_STATES

RETENTION_DAYS = 30
MAX_DURATION_MS = 3_600_000
DEFAULT_CLEANUP_BATCH_SIZE = 500
MAX_CLEANUP_BATCH_SIZE = 5_000
MODAL_CPU_USD_PER_CORE_SECOND = 0.00003942
MODAL_MEMORY_USD_PER_GIB_SECOND = 0.00000672
ACTIVE_SPEND_ALERT_FLOOR_USD = 50.0
ACTIVE_SPEND_LOOKBACK_DAYS = 7
ACTIVE_SPEND_BASELINE_DAYS = 30
ACTIVE_SPEND_ALERT_MULTIPLIER = 2.0
MIN_ACTIVE_SPEND_OBSERVATION_SECONDS = 60.0
STALE_TURN_FINALIZATION_GRACE_SECONDS = 30

PHASE_COLUMNS = {
    "sandbox_acquisition_started": "acquisition_started_ms",
    "sandbox_acquisition_ms": "acquisition_started_ms",
    "pool_lookup_completed": "pool_lookup_completed_ms",
    "modal_sandbox_created": "modal_sandbox_created_ms",
    "modal_create_ms": "modal_sandbox_created_ms",
    "worker_control_ready": "worker_control_ready_ms",
    "worker_ready_ms": "worker_control_ready_ms",
    "session_assignment_completed": "session_assignment_completed_ms",
    "broker_capability_installed": "broker_capability_installed_ms",
    "capability_install_ms": "broker_capability_installed_ms",
    "sdk_query_dispatched": "sdk_query_dispatched_ms",
    "sdk_dispatch_ms": "sdk_query_dispatched_ms",
    "provider_gateway_received": "provider_gateway_received_ms",
    "control_connection": "control_connection_ms",
    "agent_spawn": "agent_spawn_ms",
    "agent_startup_ready": "agent_startup_ready_ms",
    "session_bind_restore": "session_bind_restore_ms",
    "resource_loading": "resource_loading_ms",
    "agent_session_ready": "agent_session_ready_ms",
    "upstream_response_headers": "upstream_response_headers_ms",
    "upstream_first_body_byte": "upstream_first_body_byte_ms",
    "first_worker_delta": "first_worker_delta_ms",
    "first_application_sse_delta": "first_application_sse_delta_ms",
    "first_semantic_event": "first_semantic_event_ms",
    "assignment_fallback": "retry_overhead_ms",
}
ACQUISITION_OUTCOMES = {
    "pending",
    "created",
    "reused_session",
    "pool_hit",
    "pool_miss",
}
TERMINAL_STATUSES = {"complete", "stopped", "error", "interrupted"}
BROWSER_TERMINAL_CLASSIFICATIONS = {
    "complete",
    "stopped",
    "error",
    "network_error",
    "aborted",
}
QUALIFICATION_SCENARIOS = {
    "focused_latency",
    "reliability",
    "clean_cancel",
    "forced_failure",
}
QUALIFICATION_PROFILES = {
    "32-functional-turns",
    "100-immediate-admission",
}
QUALIFICATION_WORKLOADS = {"no_tool", "read", "bash"}


def _bounded_duration(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    if not 0 <= value <= MAX_DURATION_MS:
        raise ValueError(f"{name} is out of range")
    return round(value)


def _payload_value(payload: object, name: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(name)
    return getattr(payload, name, None)


class ChatLatencyService:
    """Write one sanitized latency record per admitted chat turn."""

    def __init__(self, db: Session):
        self.db = db

    def admit(
        self,
        *,
        turn_id: uuid.UUID,
        session_id: uuid.UUID,
        request_id: str,
        settings: Settings,
        model_route: str,
        execution_backend: str,
        is_new_chat: bool,
        agent_harness: str = "claude",
    ) -> ChatTurnLatency:
        if execution_backend not in {"local_mcp", "modal_cli", "external_pi"}:
            raise ValueError("Unsupported chat execution backend")
        if agent_harness not in {"claude", "pi"}:
            raise ValueError("Unsupported chat agent harness")
        try:
            request_uuid = uuid.UUID(request_id)
        except ValueError:
            raise ValueError("request_id must be a UUID") from None
        existing = self.db.execute(
            select(ChatTurnLatency).where(ChatTurnLatency.request_id == request_uuid)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.chat_session_id != session_id or existing.turn_id != turn_id:
                raise ValueError("Request reference is already bound to another turn")
            return existing

        row = ChatTurnLatency(
            turn_id=turn_id,
            request_id=request_uuid,
            chat_session_id=session_id,
            traffic_class="new_chat" if is_new_chat else "followup",
            execution_backend=execution_backend,
            agent_harness=agent_harness,
            pi_version=settings.chat_pi_version if agent_harness == "pi" else None,
            model_route=model_route,
            app_release_id=settings.release_id,
            sandbox_image_version=settings.chat_modal_image_version or None,
            worker_contract_version=settings.chat_worker_contract_version or None,
            pwc_cli_version=settings.chat_pwc_cli_version or None,
            system_prompt_sha256=settings.chat_system_prompt_sha256 or None,
            sandbox_cpu_request=(
                settings.chat_sandbox_cpu if execution_backend == "modal_cli" else None
            ),
            sandbox_memory_request_mib=(
                settings.chat_sandbox_memory_mib
                if execution_backend == "modal_cli"
                else None
            ),
            acquisition_outcome="pending",
            terminal_status="running",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_external_pi(self, request_id: str) -> bool:
        """Record that the turn ran on the external Pi fleet, not a sandbox.

        Admission cannot know this: routing also depends on durable
        qualification evidence resolved later. Until it is corrected the turn
        carries the Modal sandbox shape, so `finalize` bills it for compute
        that never ran and feeds that figure to the Modal spend circuits.
        """
        try:
            request_uuid = uuid.UUID(request_id)
        except ValueError:
            raise ValueError("request_id must be a UUID") from None
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == request_uuid,
                ChatTurnLatency.execution_backend == "modal_cli",
            )
            .values(
                execution_backend="external_pi",
                sandbox_cpu_request=None,
                sandbox_memory_request_mib=None,
                updated_at=datetime.now(UTC),
            )
        )
        return bool(result.rowcount)

    def record_phase(
        self,
        request_id: str,
        phase: str,
        elapsed_ms: int,
        *,
        acquisition_outcome: str | None = None,
        first_semantic_event_class: str | None = None,
        pool_miss_reason: str | None = None,
        session_reuse_cohort: str | None = None,
        failure_stage: str | None = None,
        failure_class: str | None = None,
        attempt_kind: str | None = None,
    ) -> bool:
        column_name = PHASE_COLUMNS.get(phase)
        if column_name is None:
            raise ValueError(f"Unsupported latency phase: {phase}")
        elapsed_ms = _bounded_duration(elapsed_ms, "elapsed_ms")
        values: dict[str, Any] = {
            column_name: elapsed_ms,
            "updated_at": datetime.now(UTC),
        }
        if acquisition_outcome is not None:
            if acquisition_outcome not in ACQUISITION_OUTCOMES - {"pending"}:
                raise ValueError("Unsupported sandbox acquisition outcome")
            values["acquisition_outcome"] = acquisition_outcome
        if first_semantic_event_class is not None:
            if first_semantic_event_class not in {"reasoning", "tool", "answer"}:
                raise ValueError("Unsupported first semantic event class")
            values["first_semantic_event_class"] = first_semantic_event_class
        if pool_miss_reason is not None:
            if pool_miss_reason not in {
                "empty_pool",
                "incompatible_profile",
                "stale_blank",
                "claim_race",
                "unhealthy_blank",
            }:
                raise ValueError("Unsupported pool miss reason")
            values["pool_miss_reason"] = pool_miss_reason
        if session_reuse_cohort is not None:
            if session_reuse_cohort not in {
                "fully_in_memory",
                "control_reconnected",
                "rediscovered",
                "restarted",
            }:
                raise ValueError("Unsupported session reuse cohort")
            values["session_reuse_cohort"] = session_reuse_cohort
        diagnostic_values = (failure_stage, failure_class, attempt_kind)
        if any(value is not None for value in diagnostic_values):
            if phase != "assignment_fallback" or any(
                value is None for value in diagnostic_values
            ):
                raise ValueError("Incomplete warm assignment diagnostics")
            if attempt_kind not in ATTEMPT_KINDS:
                raise ValueError("Unsupported sandbox attempt kind")
            values.update(
                failure_stage=sanitized_failure_stage(failure_stage),
                failure_class=sanitized_failure_class(failure_class),
                attempt_kind=attempt_kind,
            )
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                getattr(ChatTurnLatency, column_name).is_(None),
                ChatTurnLatency.terminal_status == "running",
            )
            .values(**values)
        )
        return bool(result.rowcount)

    def record_phase_for_turn(
        self,
        turn_id: uuid.UUID,
        phase: str,
        elapsed_ms: int,
    ) -> bool:
        column_name = PHASE_COLUMNS.get(phase)
        if column_name is None:
            raise ValueError(f"Unsupported latency phase: {phase}")
        elapsed_ms = _bounded_duration(elapsed_ms, "elapsed_ms")
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.turn_id == turn_id,
                getattr(ChatTurnLatency, column_name).is_(None),
                ChatTurnLatency.terminal_status == "running",
            )
            .values(**{column_name: elapsed_ms, "updated_at": datetime.now(UTC)})
        )
        return bool(result.rowcount)

    def record_pool_assignment_fallback(self, request_id: str) -> bool:
        """Move a failed claimed blank out of the successful pool-hit cohort."""

        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                ChatTurnLatency.acquisition_outcome == "pool_hit",
                ChatTurnLatency.terminal_status == "running",
            )
            .values(
                acquisition_outcome="pool_miss",
                pool_miss_reason="unhealthy_blank",
                updated_at=datetime.now(UTC),
            )
        )
        return bool(result.rowcount)

    def record_gateway_received(
        self,
        turn_id: uuid.UUID,
        received_at: datetime,
    ) -> bool:
        if received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        admitted_at = self.db.execute(
            select(ChatTurnLatency.admitted_at).where(
                ChatTurnLatency.turn_id == turn_id
            )
        ).scalar_one_or_none()
        if admitted_at is None:
            return False
        if admitted_at.tzinfo is None:
            admitted_at = admitted_at.replace(tzinfo=UTC)
        elapsed_ms = round((received_at - admitted_at).total_seconds() * 1000)
        return self.record_phase_for_turn(
            turn_id, "provider_gateway_received", elapsed_ms
        )

    def mark_qualification(
        self,
        request_id: str,
        *,
        run_id: str,
        scope_id: uuid.UUID | None = None,
        profile: str | None = None,
        workload: str | None = None,
        scenario: str,
    ) -> bool:
        if scenario not in QUALIFICATION_SCENARIOS:
            raise ValueError("Unsupported qualification scenario")
        if profile is not None and profile not in QUALIFICATION_PROFILES:
            raise ValueError("Unsupported qualification profile")
        if workload is not None and workload not in QUALIFICATION_WORKLOADS:
            raise ValueError("Unsupported qualification workload")
        normalized_run_id = run_id.strip()
        if not normalized_run_id or len(normalized_run_id) > 64:
            raise ValueError("qualification run_id must be 1-64 characters")
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                ChatTurnLatency.qualification_run_id.is_(None),
                ChatTurnLatency.qualification_scenario.is_(None),
                ChatTurnLatency.qualification_scope_id.is_(None),
            )
            .values(
                qualification_scope_id=scope_id,
                qualification_run_id=normalized_run_id,
                qualification_profile=profile,
                qualification_workload=workload,
                qualification_scenario=scenario,
                updated_at=datetime.now(UTC),
            )
        )
        return bool(result.rowcount)

    @staticmethod
    def _estimated_active_cost(row: ChatTurnLatency, total_ms: int) -> float | None:
        if (
            row.execution_backend != "modal_cli"
            or row.sandbox_cpu_request is None
            or row.sandbox_memory_request_mib is None
        ):
            return None
        seconds = total_ms / 1000
        return seconds * (
            float(row.sandbox_cpu_request) * MODAL_CPU_USD_PER_CORE_SECOND
            + (row.sandbox_memory_request_mib / 1024) * MODAL_MEMORY_USD_PER_GIB_SECOND
        )

    def finalize(self, request_id: str, status: str, total_ms: int) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError("Unsupported terminal latency status")
        total_ms = _bounded_duration(total_ms, "total_ms")
        now = datetime.now(UTC)
        row = self.db.execute(
            select(ChatTurnLatency).where(
                ChatTurnLatency.request_id == uuid.UUID(request_id)
            )
        ).scalar_one_or_none()
        estimated_active_cost_usd = (
            self._estimated_active_cost(row, total_ms) if row is not None else None
        )
        result = self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == uuid.UUID(request_id),
                ChatTurnLatency.terminal_status == "running",
                ChatTurnLatency.total_ms.is_(None),
            )
            .values(
                terminal_status=status,
                total_ms=total_ms,
                estimated_active_cost_usd=estimated_active_cost_usd,
                completed_at=now,
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    def reconcile_stale_turns(
        self,
        *,
        now: datetime | None = None,
        batch_size: int = 100,
    ) -> dict[str, int]:
        """Finalize telemetry and projections left open past their turn lease."""

        if not 1 <= batch_size <= 1_000:
            raise ValueError("stale turn batch_size is out of range")
        current = now or datetime.now(UTC)
        finalization_cutoff = current - timedelta(
            seconds=STALE_TURN_FINALIZATION_GRACE_SECONDS
        )
        rows = list(
            self.db.execute(
                select(ChatTurnLatency, ChatSession, ChatMessageRecord)
                .join(
                    ChatSession,
                    ChatSession.id == ChatTurnLatency.chat_session_id,
                )
                .join(
                    ChatMessageRecord,
                    (ChatMessageRecord.session_id == ChatSession.id)
                    & (ChatMessageRecord.turn_id == ChatTurnLatency.turn_id)
                    & (ChatMessageRecord.role == "user"),
                )
                .where(
                    ChatTurnLatency.terminal_status == "running",
                    # Durable lifecycle owns expiry and must update the job and
                    # conversation atomically using the worker's current lease.
                    # The session lease can expire while that worker is healthy.
                    ~select(ChatTurnJob.turn_id)
                    .where(
                        ChatTurnJob.turn_id == ChatTurnLatency.turn_id,
                        ChatTurnJob.state.in_(NONTERMINAL_STATES),
                    )
                    .exists(),
                    or_(
                        ChatSession.active_turn_expires_at <= current,
                        and_(
                            or_(
                                ChatSession.active_turn_id.is_(None),
                                ChatSession.active_turn_id != ChatTurnLatency.turn_id,
                                ChatSession.active_turn_expires_at.is_(None),
                            ),
                            ChatSession.updated_at <= finalization_cutoff,
                        ),
                    ),
                )
                .order_by(ChatTurnLatency.admitted_at, ChatTurnLatency.turn_id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
        )
        reconciled = {"complete": 0, "error": 0, "interrupted": 0}
        for latency, session, message in rows:
            active_expiry = session.active_turn_expires_at
            message_was_terminal = message.status in {
                "complete",
                "error",
                "interrupted",
            }
            if message.status == "complete":
                status = "complete"
            elif message.status == "error":
                status = "error"
            else:
                status = "interrupted"
                if message.status in {"generating", "preparing"}:
                    message.status = "interrupted"
                    message.error_code = "lease_expired"
            if session.active_turn_id == latency.turn_id:
                session.active_turn_id = None
                session.active_turn_expires_at = None
                session.updated_at = current
            admitted_at = latency.admitted_at
            if admitted_at.tzinfo is None:
                admitted_at = admitted_at.replace(tzinfo=UTC)
            if message_was_terminal:
                ended_at = latency.updated_at
            elif active_expiry is not None:
                ended_at = min(current, active_expiry)
            else:
                ended_at = current
            if ended_at.tzinfo is None:
                ended_at = ended_at.replace(tzinfo=UTC)
            total_ms = min(
                MAX_DURATION_MS,
                max(0, round((ended_at - admitted_at).total_seconds() * 1000)),
            )
            latency.terminal_status = status
            latency.total_ms = total_ms
            latency.estimated_active_cost_usd = self._estimated_active_cost(
                latency, total_ms
            )
            latency.completed_at = ended_at
            latency.updated_at = current
            reconciled[status] += 1
        self.db.flush()
        return reconciled

    def update_browser(
        self,
        owner_id: str,
        request_id: str,
        payload: object,
    ) -> bool:
        try:
            request_uuid = uuid.UUID(request_id)
        except ValueError:
            raise ValueError("request_id must be a UUID") from None
        latency = self.db.execute(
            select(ChatTurnLatency)
            .join(ChatSession, ChatSession.id == ChatTurnLatency.chat_session_id)
            .where(
                ChatTurnLatency.request_id == request_uuid,
                ChatSession.hf_user_id == owner_id,
            )
        ).scalar_one_or_none()
        if latency is None:
            return False

        supplied = {
            "browser_stream_start_ms": _payload_value(
                payload, "submission_to_stream_start_ms"
            ),
            "browser_first_visible_delta_ms": _payload_value(
                payload, "submission_to_first_visible_delta_ms"
            ),
            "browser_first_reasoning_delta_ms": _payload_value(
                payload, "submission_to_first_reasoning_delta_ms"
            ),
            "browser_first_tool_call_ms": _payload_value(
                payload, "submission_to_first_tool_call_ms"
            ),
            "browser_first_answer_delta_ms": _payload_value(
                payload, "submission_to_first_answer_delta_ms"
            ),
            "browser_terminal_classification": _payload_value(
                payload, "terminal_classification"
            ),
        }
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        null_conditions = []
        for column_name, value in supplied.items():
            if value is None:
                continue
            if column_name == "browser_terminal_classification":
                if value not in BROWSER_TERMINAL_CLASSIFICATIONS:
                    raise ValueError("Unsupported browser terminal classification")
            else:
                value = _bounded_duration(value, column_name)
            column = getattr(ChatTurnLatency, column_name)
            values[column_name] = func.coalesce(column, value)
            null_conditions.append(column.is_(None))
        if not null_conditions:
            raise ValueError("Browser timing update is empty")

        self.db.execute(
            update(ChatTurnLatency)
            .where(
                ChatTurnLatency.request_id == request_uuid,
                ChatTurnLatency.chat_session_id == latency.chat_session_id,
                or_(*null_conditions),
            )
            .values(**values)
        )
        # An authenticated duplicate is still a successful idempotent update;
        # COALESCE above preserves the first value for each timing class.
        return True

    def active_spend_status(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return content-free active-compute spend and alert projections."""
        observed_at = now or datetime.now(UTC)
        if observed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        observed_at = observed_at.astimezone(UTC)
        month_start = observed_at.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        next_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        cost = ChatTurnLatency.estimated_active_cost_usd
        cost_recorded = cost.is_not(None)
        in_month = (ChatTurnLatency.completed_at >= month_start) & (
            ChatTurnLatency.completed_at <= observed_at
        )
        trailing_start = observed_at - timedelta(days=ACTIVE_SPEND_LOOKBACK_DAYS)

        month_cost, first_observation = self.db.execute(
            select(
                func.coalesce(func.sum(cost), 0),
                func.min(ChatTurnLatency.completed_at),
            ).where(cost_recorded, in_month)
        ).one()
        completed_turns = int(
            self.db.scalar(
                select(func.count())
                .select_from(ChatTurnLatency)
                .where(
                    cost_recorded,
                    in_month,
                    ChatTurnLatency.terminal_status == "complete",
                )
            )
            or 0
        )
        trailing_cost = float(
            self.db.scalar(
                select(func.coalesce(func.sum(cost), 0)).where(
                    cost_recorded,
                    ChatTurnLatency.completed_at >= trailing_start,
                    ChatTurnLatency.completed_at <= observed_at,
                )
            )
            or 0
        )
        month_cost = float(month_cost or 0)
        cost_per_completed_turn = (
            month_cost / completed_turns if completed_turns else 0.0
        )

        projected_monthly_cost = 0.0
        if first_observation is not None and month_cost:
            if first_observation.tzinfo is None:
                first_observation = first_observation.replace(tzinfo=UTC)
            observation_seconds = max(
                (observed_at - first_observation).total_seconds(),
                MIN_ACTIVE_SPEND_OBSERVATION_SECONDS,
            )
            projected_monthly_cost = (
                month_cost
                / observation_seconds
                * (next_month - month_start).total_seconds()
            )

        trailing_daily_average = trailing_cost / ACTIVE_SPEND_LOOKBACK_DAYS
        trailing_30_day_projection = trailing_daily_average * ACTIVE_SPEND_BASELINE_DAYS
        alert_threshold = max(
            ACTIVE_SPEND_ALERT_FLOOR_USD,
            ACTIVE_SPEND_ALERT_MULTIPLIER * trailing_30_day_projection,
        )
        return {
            "month_to_date_cost_usd": month_cost,
            "completed_turns": completed_turns,
            "cost_per_completed_turn_usd": cost_per_completed_turn,
            "projected_monthly_cost_usd": projected_monthly_cost,
            "trailing_seven_day_cost_usd": trailing_cost,
            "trailing_daily_average_usd": trailing_daily_average,
            "trailing_30_day_projection_usd": trailing_30_day_projection,
            "alert_threshold_usd": alert_threshold,
            "should_alert": projected_monthly_cost > alert_threshold,
        }

    def cleanup(
        self,
        batch_size: int = DEFAULT_CLEANUP_BATCH_SIZE,
        *,
        now: datetime | None = None,
    ) -> int:
        if not 1 <= batch_size <= MAX_CLEANUP_BATCH_SIZE:
            raise ValueError("cleanup batch_size is out of range")
        cutoff = (now or datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)
        ids = list(
            self.db.execute(
                select(ChatTurnLatency.turn_id)
                .where(ChatTurnLatency.admitted_at < cutoff)
                .order_by(ChatTurnLatency.admitted_at, ChatTurnLatency.turn_id)
                .limit(batch_size)
            ).scalars()
        )
        if not ids:
            return 0
        result = self.db.execute(
            delete(ChatTurnLatency).where(ChatTurnLatency.turn_id.in_(ids))
        )
        return max(result.rowcount or 0, 0)
