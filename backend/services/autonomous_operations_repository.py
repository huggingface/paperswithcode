"""Durable, content-free state and fencing for autonomous operators."""

from __future__ import annotations

import json
import re
import uuid
from hashlib import sha256
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousAction,
    AutonomousBudgetReservation,
    AutonomousControlEvent,
    AutonomousExecutionIntent,
    AutonomousIncidentAttempt,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
    ChatProviderRuntimeState,
    ChatReliabilityBaseline,
)

_CONTROL_ROWS = (
    "global",
    "submissions",
    "curation",
    "cron_health",
    "chat_reliability",
)
_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,199}$")
_RESOURCE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_ACTOR = re.compile(r"^(?:admin|system):[A-Za-z0-9][A-Za-z0-9._@-]{0,199}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SECRET_PREFIXES = ("sk-", "hf_", "bearer", "eyj")
_MONITORING_INTERVALS = {
    "submissions": timedelta(hours=1),
    "curation": timedelta(hours=1),
    "cron_health": timedelta(minutes=15),
    "chat_reliability": timedelta(minutes=15),
}


class Operator(StrEnum):
    SUBMISSIONS = "submissions"
    CURATION = "curation"
    CRON_HEALTH = "cron_health"
    CHAT_RELIABILITY = "chat_reliability"


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: uuid.UUID
    operator: Operator
    dry_run: bool
    manifest_revision: str


@dataclass(frozen=True, slots=True)
class ControlState:
    manual_mode: bool
    enabled: dict[Operator, bool]
    revision: int


@dataclass(frozen=True, slots=True)
class RepairLease:
    lease_id: uuid.UUID
    owner_run_id: uuid.UUID
    expires_at: datetime


class AutonomousStateConflict(RuntimeError):
    """The control state changed after the caller read it."""


class ManualModeEnabled(RuntimeError):
    """Global manual mode blocked an autonomous mutation."""


class OperatorDisabled(RuntimeError):
    """The selected operator is not mutation-enabled."""


class DryRunMutation(RuntimeError):
    """A dry-run context attempted a mutating capability."""


class RepairLeaseUnavailable(RuntimeError):
    """Another live run owns the singleton source-repair lease."""


class StaleRepairLease(RuntimeError):
    """A release request did not match the current lease fencing tuple."""


class IncidentAttemptLimit(RuntimeError):
    """The fixed chat source-repair attempt budget is exhausted."""


class BudgetReservationUnavailable(RuntimeError):
    """A live execution already owns the provider-enforced run budget."""


Clock = Callable[[Session], datetime]


class AutonomousOperationsRepository:
    """Persistence boundary for operator controls and append-only audit data."""

    def __init__(self, *, clock: Clock | None = None):
        self._clock = clock or self._database_now

    @staticmethod
    def _database_now(db: Session) -> datetime:
        clock = (
            func.clock_timestamp()
            if db.bind is not None and db.bind.dialect.name == "postgresql"
            else func.current_timestamp()
        )
        value = db.scalar(select(clock))
        if not isinstance(value, datetime):
            raise RuntimeError("Database did not return a timestamp")
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _validate_code(value: str, *, label: str, max_length: int) -> None:
        if (
            len(value) > max_length
            or _CODE.fullmatch(value) is None
            or value.lower().startswith(_SECRET_PREFIXES)
        ):
            raise ValueError(f"{label} is invalid")

    @staticmethod
    def _validate_actor(actor: str) -> None:
        if _ACTOR.fullmatch(actor) is None:
            raise ValueError("Autonomous actor is invalid")

    @staticmethod
    def _state_digest(*parts: object) -> str:
        canonical = "\x1f".join(str(part) for part in parts)
        return sha256(canonical.encode()).hexdigest()

    def _append_control_event(
        self,
        db: Session,
        *,
        actor: str,
        event_kind: str,
        target: str,
        before_digest: str,
        after_digest: str,
        now: datetime,
    ) -> None:
        db.add(
            AutonomousControlEvent(
                id=uuid.uuid4(),
                actor=actor,
                event_kind=event_kind,
                target=target,
                before_digest=before_digest,
                after_digest=after_digest,
                created_at=now,
            )
        )

    def _ensure_control_rows(self, db: Session) -> None:
        for key in _CONTROL_ROWS:
            if db.get(AutonomousOperatorState, key) is None:
                db.add(
                    AutonomousOperatorState(
                        operator=key,
                        enabled=False,
                        manual_mode=key == "global",
                        revision=1,
                        updated_by="system:bootstrap",
                    )
                )
        db.flush()

    def get_control_state(self, db: Session) -> ControlState:
        self._ensure_control_rows(db)
        rows = {
            row.operator: row
            for row in db.scalars(select(AutonomousOperatorState)).all()
        }
        return ControlState(
            manual_mode=rows["global"].manual_mode,
            enabled={operator: rows[operator.value].enabled for operator in Operator},
            revision=rows["global"].revision,
        )

    def get_admin_snapshot(self, db: Session, *, limit: int = 25) -> dict:
        """Return a bounded, content-free read model for human supervision."""
        if not 1 <= limit <= 100:
            raise ValueError("Autonomous snapshot limit is invalid")
        control = self.get_control_state(db)
        now = self._clock(db)
        lease_row = db.scalar(
            select(AutonomousRepairLease).where(
                AutonomousRepairLease.singleton_key == "source_repair",
                AutonomousRepairLease.expires_at > now,
            )
        )
        runs = list(
            db.scalars(
                select(AutonomousRun)
                .order_by(AutonomousRun.created_at.desc(), AutonomousRun.id.desc())
                .limit(limit)
            )
        )
        actions = list(
            db.scalars(
                select(AutonomousAction)
                .order_by(
                    AutonomousAction.created_at.desc(), AutonomousAction.id.desc()
                )
                .limit(limit)
            )
        )
        latest_run = {
            operator.value: db.scalar(
                select(AutonomousRun)
                .where(AutonomousRun.operator == operator.value)
                .order_by(AutonomousRun.created_at.desc(), AutonomousRun.id.desc())
                .limit(1)
            )
            for operator in Operator
        }
        latest_action = {
            operator.value: db.scalar(
                select(AutonomousAction)
                .where(AutonomousAction.operator == operator.value)
                .order_by(
                    AutonomousAction.created_at.desc(), AutonomousAction.id.desc()
                )
                .limit(1)
            )
            for operator in Operator
        }
        next_scheduled = {
            operator.value: (
                self._aware(latest_run[operator.value].created_at)
                + _MONITORING_INTERVALS[operator.value]
                if latest_run[operator.value] is not None
                else None
            )
            for operator in Operator
        }
        monitoring = {
            operator.value: (
                next_scheduled[operator.value] is not None
                and now
                <= next_scheduled[operator.value]
                + _MONITORING_INTERVALS[operator.value]
            )
            for operator in Operator
        }

        def operator_status(operator: Operator) -> str:
            if control.manual_mode:
                return "manual"
            if lease_row is not None and lease_row.owner_operator == operator.value:
                return "repairing"
            action = latest_action.get(operator.value)
            run = latest_run[operator.value]
            if (
                action is not None
                and action.reason_code == "rolled_back"
                and (
                    run is None
                    or self._aware(action.created_at) > self._aware(run.created_at)
                )
            ):
                return "rolled-back"
            if (
                not control.enabled[operator]
                or run is None
                or run.status != "completed"
                or not monitoring[operator.value]
            ):
                return "degraded"
            return "healthy"

        statuses = {operator: operator_status(operator) for operator in Operator}
        if control.manual_mode:
            display_state = "manual"
        elif "repairing" in statuses.values():
            display_state = "repairing"
        elif "rolled-back" in statuses.values():
            display_state = "rolled-back"
        elif "degraded" in statuses.values():
            display_state = "degraded"
        else:
            display_state = "healthy"

        input_tokens, output_tokens, total_usd = db.execute(
            select(
                func.coalesce(func.sum(AutonomousRun.input_tokens), 0),
                func.coalesce(func.sum(AutonomousRun.output_tokens), 0),
                func.coalesce(func.sum(AutonomousRun.cost_usd), 0),
            )
        ).one()
        baseline = db.scalar(
            select(ChatReliabilityBaseline).where(
                ChatReliabilityBaseline.singleton.is_(True)
            )
        )
        providers = list(
            db.scalars(
                select(ChatProviderRuntimeState).order_by(
                    ChatProviderRuntimeState.environment
                )
            )
        )
        money = Decimal("0.000000001")
        return {
            "revision": control.revision,
            "manual_mode": control.manual_mode,
            "monitoring_active": any(monitoring.values()),
            "display_state": display_state,
            "operators": [
                {
                    "operator": operator.value,
                    "enabled": control.enabled[operator],
                    "status": statuses[operator],
                    "monitoring_active": monitoring[operator.value],
                    "next_scheduled_run": next_scheduled[operator.value],
                }
                for operator in Operator
            ],
            "active_lease": (
                {
                    "lease_id": str(lease_row.lease_id),
                    "owner_run_id": str(lease_row.owner_run_id),
                    "owner_operator": lease_row.owner_operator,
                    "expires_at": self._aware(lease_row.expires_at),
                }
                if lease_row is not None
                else None
            ),
            "costs": {
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "total_usd": f"{Decimal(str(total_usd)).quantize(money):.9f}",
            },
            "baseline": (
                {
                    "sha": baseline.sha,
                    "revision": baseline.revision,
                    "qualified_by": baseline.qualified_by,
                    "qualified_at": self._aware(baseline.qualified_at),
                }
                if baseline is not None
                else None
            ),
            "provider_states": [
                {
                    "environment": row.environment,
                    "manifest_revision": row.manifest_revision,
                    "state_revision": row.state_revision,
                    "active_provider": row.active_provider,
                    "reason_code": row.reason_code,
                    "updated_at": self._aware(row.updated_at),
                }
                for row in providers
            ],
            "recent_runs": [
                {
                    "run_id": str(row.id),
                    "operator": row.operator,
                    "dry_run": row.dry_run,
                    "status": row.status,
                    "exit_classification": row.exit_classification,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cost_usd": f"{Decimal(str(row.cost_usd)).quantize(money):.9f}",
                    "created_at": self._aware(row.created_at),
                }
                for row in runs
            ],
            "recent_actions": [
                {
                    "action_id": str(row.id),
                    "run_id": str(row.run_id),
                    "operator": row.operator,
                    "capability": row.capability,
                    "reason_code": row.reason_code,
                    "resource_kind": row.resource_kind,
                    "resource_identifier": row.resource_identifier,
                    "created_at": self._aware(row.created_at),
                }
                for row in actions
            ],
            "exclusions": [
                "task_creation",
                "method_creation",
                "benchmark_dataset_creation",
                "metric_creation",
                "conference_creation",
                "database_migrations",
                "nginx_host_changes",
                "secrets_credentials",
                "destructive_data_repair",
            ],
        }

    def _locked_global_state(self, db: Session) -> AutonomousOperatorState:
        self._ensure_control_rows(db)
        return db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == "global")
            .with_for_update()
        ).scalar_one()

    @staticmethod
    def _require_revision(row: AutonomousOperatorState, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise AutonomousStateConflict("Autonomous control state is stale")

    def set_manual_mode(
        self,
        db: Session,
        *,
        enabled: bool,
        expected_revision: int,
        actor: str,
        now: datetime,
    ) -> ControlState:
        self._validate_actor(actor)
        if now.tzinfo is None:
            raise ValueError("Autonomous control timestamp is invalid")
        global_state = self._locked_global_state(db)
        self._require_revision(global_state, expected_revision)
        before_digest = self._state_digest("manual_mode", global_state.manual_mode)
        global_state.manual_mode = enabled
        global_state.revision += 1
        global_state.updated_by = actor
        global_state.updated_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="manual_mode",
            target="global",
            before_digest=before_digest,
            after_digest=self._state_digest("manual_mode", enabled),
            now=now,
        )
        db.flush()
        return self.get_control_state(db)

    def set_operator_enabled(
        self,
        db: Session,
        *,
        operator: Operator,
        enabled: bool,
        expected_revision: int,
        actor: str,
        now: datetime,
    ) -> ControlState:
        self._validate_actor(actor)
        if now.tzinfo is None:
            raise ValueError("Autonomous control timestamp is invalid")
        global_state = self._locked_global_state(db)
        self._require_revision(global_state, expected_revision)
        operator_state = db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == operator.value)
            .with_for_update()
        ).scalar_one()
        before_digest = self._state_digest(
            "operator_enabled", operator.value, operator_state.enabled
        )
        operator_state.enabled = enabled
        operator_state.updated_by = actor
        operator_state.updated_at = now
        global_state.revision += 1
        global_state.updated_by = actor
        global_state.updated_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="operator_enabled",
            target=operator.value,
            before_digest=before_digest,
            after_digest=self._state_digest(
                "operator_enabled", operator.value, enabled
            ),
            now=now,
        )
        db.flush()
        return self.get_control_state(db)

    def assert_mutation_allowed(self, db: Session, context: RunContext) -> None:
        if context.dry_run:
            raise DryRunMutation("Dry-run contexts cannot mutate")
        global_state = self._locked_global_state(db)
        operator_state = db.execute(
            select(AutonomousOperatorState)
            .where(AutonomousOperatorState.operator == context.operator.value)
            .with_for_update()
        ).scalar_one()
        if global_state.manual_mode:
            raise ManualModeEnabled("Global manual mode blocks autonomous mutations")
        if not operator_state.enabled:
            raise OperatorDisabled(f"{context.operator.value} operator is disabled")

    @staticmethod
    def _require_run_context(db: Session, context: RunContext) -> AutonomousRun:
        run = db.get(AutonomousRun, context.run_id)
        if (
            run is None
            or run.operator != context.operator.value
            or run.dry_run != context.dry_run
            or run.manifest_revision != context.manifest_revision
        ):
            raise ValueError("Autonomous run context mismatches durable identity")
        return run

    def assert_run_context(self, db: Session, context: RunContext) -> None:
        """Verify that a caller's typed identity matches its immutable run."""
        self._require_run_context(db, context)

    def has_published_repair(
        self, db: Session, *, context: RunContext, sha_digest: str
    ) -> bool:
        """Require release promotion to reference this run's audited publication."""
        self._require_run_context(db, context)
        if _DIGEST.fullmatch(sha_digest) is None:
            raise ValueError("Published repair digest is invalid")
        return (
            db.execute(
                select(AutonomousAction.id).where(
                    AutonomousAction.run_id == context.run_id,
                    AutonomousAction.operator == context.operator.value,
                    AutonomousAction.capability == "repair_declared_cron_source",
                    AutonomousAction.reason_code == "published",
                    AutonomousAction.after_digest == sha_digest,
                )
            ).scalar_one_or_none()
            is not None
        )

    def owns_repair_lease(self, db: Session, *, context: RunContext) -> bool:
        """Check the live singleton lease against database time and run identity."""
        self._require_run_context(db, context)
        row = db.execute(
            select(AutonomousRepairLease).where(
                AutonomousRepairLease.singleton_key == "source_repair"
            )
        ).scalar_one_or_none()
        return bool(
            row is not None
            and row.owner_run_id == context.run_id
            and row.owner_operator == context.operator.value
            and self._aware(row.expires_at) > self._clock(db)
        )

    @staticmethod
    def _advisory_lock(db: Session, key: str) -> None:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
            )

    def lock_run(self, db: Session, *, run_id: uuid.UUID) -> None:
        """Serialize one immutable run identity across concurrent workers."""
        if not isinstance(run_id, uuid.UUID):
            raise ValueError("Autonomous run ID is invalid")
        self._advisory_lock(db, f"autonomous:run:{run_id}")

    def get_budget_reservation(
        self, db: Session, *, run_id: uuid.UUID
    ) -> AutonomousBudgetReservation | None:
        if not isinstance(run_id, uuid.UUID):
            raise ValueError("Autonomous run ID is invalid")
        return db.get(AutonomousBudgetReservation, run_id)

    def get_execution_intent(
        self, db: Session, *, run_id: uuid.UUID
    ) -> AutonomousExecutionIntent | None:
        if not isinstance(run_id, uuid.UUID):
            raise ValueError("Autonomous run ID is invalid")
        return db.get(AutonomousExecutionIntent, run_id)

    def record_execution_intent(
        self,
        db: Session,
        *,
        context: RunContext,
        request_digest: str,
        evidence_digests: list[str],
        model_alias: str,
        budget_usd: Decimal,
        pricing_policy_digest: str,
        now: datetime,
    ) -> None:
        if (
            _DIGEST.fullmatch(request_digest) is None
            or evidence_digests != sorted(set(evidence_digests))
            or len(evidence_digests) > 500
            or any(_DIGEST.fullmatch(value) is None for value in evidence_digests)
            or model_alias not in {"diagnosis", "independent_review"}
            or not budget_usd.is_finite()
            or budget_usd <= 0
            or _DIGEST.fullmatch(pricing_policy_digest) is None
            or now.tzinfo is None
        ):
            raise ValueError("Autonomous execution intent is invalid")
        try:
            self._validate_code(
                context.manifest_revision,
                label="Manifest revision",
                max_length=128,
            )
        except ValueError:
            raise ValueError("Autonomous execution intent is invalid") from None
        db.add(
            AutonomousExecutionIntent(
                run_id=context.run_id,
                operator=context.operator.value,
                dry_run=context.dry_run,
                manifest_revision=context.manifest_revision,
                request_digest=request_digest,
                evidence_digests=evidence_digests,
                model_alias=model_alias,
                budget_usd=budget_usd,
                pricing_policy_digest=pricing_policy_digest,
                created_at=now,
            )
        )
        db.flush()

    def claim_budget_reservation(
        self,
        db: Session,
        *,
        context: RunContext,
        reservation_id: str,
        provider: str,
        model_alias: str,
        limit_usd: Decimal,
        attestation_digest: str,
        request_digest: str,
        endpoint_digest: str,
        credential_scope: str,
        expires_at: datetime,
        claim_ttl: timedelta,
    ) -> uuid.UUID:
        """Persist and exclusively claim an idempotent provider reservation."""
        now = self._clock(db)
        if (
            _CODE.fullmatch(reservation_id) is None
            or len(reservation_id) > 128
            or provider != "openai"
            or model_alias not in {"diagnosis", "independent_review"}
            or not isinstance(limit_usd, Decimal)
            or not limit_usd.is_finite()
            or limit_usd <= 0
            or _DIGEST.fullmatch(attestation_digest) is None
            or _DIGEST.fullmatch(request_digest) is None
            or _DIGEST.fullmatch(endpoint_digest) is None
            or credential_scope != "responses"
            or expires_at.tzinfo is None
            or expires_at <= now
            or not timedelta(minutes=1) <= claim_ttl <= timedelta(hours=3)
        ):
            raise ValueError("Autonomous budget reservation is invalid")
        row = db.execute(
            select(AutonomousBudgetReservation)
            .where(AutonomousBudgetReservation.run_id == context.run_id)
            .with_for_update()
        ).scalar_one_or_none()
        claim_id = uuid.uuid4()
        if row is None:
            row = AutonomousBudgetReservation(
                run_id=context.run_id,
                operator=context.operator.value,
                reservation_id=reservation_id,
                provider=provider,
                model_alias=model_alias,
                limit_usd=limit_usd,
                attestation_digest=attestation_digest,
                request_digest=request_digest,
                endpoint_digest=endpoint_digest,
                credential_scope=credential_scope,
                expires_at=expires_at,
                claim_id=claim_id,
                claim_expires_at=now + claim_ttl,
                created_at=now,
            )
            db.add(row)
        else:
            if (
                row.operator != context.operator.value
                or row.reservation_id != reservation_id
                or row.provider != provider
                or row.model_alias != model_alias
                or Decimal(row.limit_usd) != limit_usd
                or row.attestation_digest != attestation_digest
                or row.request_digest != request_digest
                or row.endpoint_digest != endpoint_digest
                or row.credential_scope != credential_scope
                or self._aware(row.expires_at) != expires_at
                or row.state != "claimed"
            ):
                raise ValueError("Autonomous budget reservation mismatch")
            if self._aware(row.claim_expires_at) > now:
                raise BudgetReservationUnavailable(
                    "Autonomous budget reservation is already claimed"
                )
            row.claim_id = claim_id
            row.claim_expires_at = now + claim_ttl
        db.flush()
        return claim_id

    def settle_budget_reservation(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        claim_id: uuid.UUID,
        released: bool,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        cost_upper_bound_usd: Decimal,
        now: datetime,
    ) -> None:
        row = db.execute(
            select(AutonomousBudgetReservation)
            .where(AutonomousBudgetReservation.run_id == run_id)
            .with_for_update()
        ).scalar_one()
        if (
            row.claim_id != claim_id
            or row.state != "claimed"
            or now.tzinfo is None
            or input_tokens < 0
            or output_tokens < 0
            or not cost_usd.is_finite()
            or not cost_upper_bound_usd.is_finite()
            or not Decimal("0")
            <= cost_usd
            <= cost_upper_bound_usd
            <= Decimal(row.limit_usd)
        ):
            raise BudgetReservationUnavailable("Autonomous budget claim is stale")
        row.state = "released" if released else "release_failed"
        row.authoritative_input_tokens = input_tokens
        row.authoritative_output_tokens = output_tokens
        row.authoritative_cost_usd = cost_usd
        row.cost_upper_bound_usd = cost_upper_bound_usd
        row.reconciliation_required = not released
        row.released_at = now if released else None
        db.flush()

    def record_budget_usage(
        self,
        db: Session,
        *,
        run_id: uuid.UUID,
        claim_id: uuid.UUID,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        cost_upper_bound_usd: Decimal,
    ) -> None:
        row = db.execute(
            select(AutonomousBudgetReservation)
            .where(AutonomousBudgetReservation.run_id == run_id)
            .with_for_update()
        ).scalar_one()
        if (
            row.claim_id != claim_id
            or row.state != "claimed"
            or input_tokens < row.authoritative_input_tokens
            or output_tokens < row.authoritative_output_tokens
            or cost_usd < row.authoritative_cost_usd
            or cost_upper_bound_usd < cost_usd
            or cost_upper_bound_usd > row.limit_usd
        ):
            raise BudgetReservationUnavailable("Autonomous budget usage is invalid")
        row.authoritative_input_tokens = input_tokens
        row.authoritative_output_tokens = output_tokens
        row.authoritative_cost_usd = cost_usd
        row.cost_upper_bound_usd = cost_upper_bound_usd
        db.flush()

    def budget_claim_is_active(self, db: Session, *, run_id: uuid.UUID) -> bool:
        row = db.get(AutonomousBudgetReservation, run_id)
        return bool(
            row is not None
            and row.state == "claimed"
            and self._aware(row.claim_expires_at) > self._clock(db)
        )

    def mark_budget_unknown(self, db: Session, *, run_id: uuid.UUID) -> None:
        row = db.execute(
            select(AutonomousBudgetReservation)
            .where(AutonomousBudgetReservation.run_id == run_id)
            .with_for_update()
        ).scalar_one()
        if row.state != "claimed":
            raise BudgetReservationUnavailable("Autonomous budget is already settled")
        row.state = "unknown"
        row.reconciliation_required = True
        db.flush()

    def append_run(
        self,
        db: Session,
        *,
        context: RunContext,
        status: str,
        now: datetime,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        result_digest: str | None = None,
        exit_classification: str = "unknown",
        capability_requests: list[dict[str, object]] | None = None,
        evidence_digests: list[str] | None = None,
        pricing_revision: str = "unknown",
        pricing_policy_digest: str = "0" * 64,
    ) -> uuid.UUID:
        capability_requests = capability_requests or []
        evidence_digests = evidence_digests or []
        try:
            self._validate_code(
                context.manifest_revision,
                label="Manifest revision",
                max_length=128,
            )
        except ValueError:
            raise ValueError("Autonomous run is invalid") from None
        if (
            status
            not in {"completed", "rejected", "failed", "budget_exhausted", "cancelled"}
            or now.tzinfo is None
            or input_tokens < 0
            or output_tokens < 0
            or cost_usd < 0
            or (result_digest is not None and _DIGEST.fullmatch(result_digest) is None)
            or exit_classification
            not in {
                "unknown",
                "completed",
                "rejected",
                "timeout",
                "cancelled",
                "budget_exhausted",
                "malformed_output",
                "process_error",
                "output_limit",
                "credential_missing",
                "configuration_missing",
                "credential_revoke_failed",
                "interrupted",
            }
            or len(capability_requests) > 100
            or len(evidence_digests) > 500
            or evidence_digests != sorted(set(evidence_digests))
            or any(_DIGEST.fullmatch(value) is None for value in evidence_digests)
            or _DIGEST.fullmatch(pricing_policy_digest) is None
        ):
            raise ValueError("Autonomous run is invalid")
        self._validate_code(pricing_revision, label="Pricing revision", max_length=128)
        for item in capability_requests:
            base_keys = {
                "capability",
                "resource_kind",
                "resource_identifier",
                "resource_exists",
                "reason_code",
            }
            structured_keys = base_keys | {
                "rationale",
                "evidence",
                "confidence",
                "resolved_payload",
            }
            item_keys = frozenset(item)
            if item_keys not in {frozenset(base_keys), frozenset(structured_keys)}:
                raise ValueError("Autonomous run is invalid")
            if not isinstance(item["resource_exists"], bool):
                raise ValueError("Autonomous run is invalid")
            for key in ("capability", "resource_kind", "reason_code"):
                self._validate_code(item[key], label=key, max_length=64)
            if _RESOURCE_IDENTIFIER.fullmatch(
                item["resource_identifier"]
            ) is None or item["resource_identifier"].lower().startswith(
                _SECRET_PREFIXES
            ):
                raise ValueError("Autonomous run is invalid")
            if item_keys == structured_keys:
                rationale = item["rationale"]
                evidence = item["evidence"]
                confidence = item["confidence"]
                resolved_payload = item["resolved_payload"]
                if (
                    item["capability"] != "review_submission"
                    or not isinstance(rationale, str)
                    or not 1 <= len(rationale) <= 4000
                    or not isinstance(evidence, list)
                    or not 1 <= len(evidence) <= 50
                    or any(
                        not isinstance(value, str) or not 1 <= len(value) <= 255
                        for value in evidence
                    )
                    or isinstance(confidence, bool)
                    or not isinstance(confidence, (int, float))
                    or not 0 <= confidence <= 1
                    or (
                        resolved_payload is not None
                        and not isinstance(resolved_payload, dict)
                    )
                ):
                    raise ValueError("Autonomous run is invalid")
                try:
                    encoded = json.dumps(
                        resolved_payload, sort_keys=True, separators=(",", ":")
                    ).encode()
                except (TypeError, ValueError):
                    raise ValueError("Autonomous run is invalid") from None
                if len(encoded) > 2_000_000:
                    raise ValueError("Autonomous run is invalid")
        db.add(
            AutonomousRun(
                id=context.run_id,
                operator=context.operator.value,
                dry_run=context.dry_run,
                manifest_revision=context.manifest_revision,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                result_digest=result_digest,
                exit_classification=exit_classification,
                capability_requests=capability_requests,
                evidence_digests=evidence_digests,
                pricing_revision=pricing_revision,
                pricing_policy_digest=pricing_policy_digest,
                created_at=now,
            )
        )
        db.flush()
        return context.run_id

    def append_action(
        self,
        db: Session,
        *,
        context: RunContext,
        capability: str,
        reason_code: str,
        resource_kind: str,
        resource_identifier: str,
        before_digest: str | None,
        after_digest: str | None,
        now: datetime,
    ) -> uuid.UUID:
        self.assert_mutation_allowed(db, context)
        for value, label, max_length in (
            (capability, "Capability", 64),
            (reason_code, "Reason code", 64),
            (resource_kind, "Resource kind", 64),
        ):
            self._validate_code(value, label=label, max_length=max_length)
        if (
            _RESOURCE_IDENTIFIER.fullmatch(resource_identifier) is None
            or resource_identifier.lower().startswith(_SECRET_PREFIXES)
            or now.tzinfo is None
            or (before_digest is not None and _DIGEST.fullmatch(before_digest) is None)
            or (after_digest is not None and _DIGEST.fullmatch(after_digest) is None)
        ):
            raise ValueError("Autonomous action is invalid")
        self._require_run_context(db, context)
        action_id = uuid.uuid4()
        db.add(
            AutonomousAction(
                id=action_id,
                run_id=context.run_id,
                operator=context.operator.value,
                capability=capability,
                reason_code=reason_code,
                resource_kind=resource_kind,
                resource_identifier=resource_identifier,
                before_digest=before_digest,
                after_digest=after_digest,
                created_at=now,
            )
        )
        db.flush()
        return action_id

    def acquire_repair_lease(
        self, db: Session, *, context: RunContext, ttl: timedelta
    ) -> RepairLease:
        if context.operator not in {Operator.CRON_HEALTH, Operator.CHAT_RELIABILITY}:
            raise ValueError("Operator is not eligible for source repair")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        if not timedelta(seconds=30) <= ttl <= timedelta(hours=2):
            raise ValueError("Repair lease TTL is invalid")
        now = self._clock(db)
        self._advisory_lock(db, "autonomous:source-repair")
        row = db.execute(
            select(AutonomousRepairLease)
            .where(AutonomousRepairLease.singleton_key == "source_repair")
            .with_for_update()
        ).scalar_one_or_none()
        if row is not None and self._aware(row.expires_at) > now:
            if row.owner_run_id != context.run_id:
                raise RepairLeaseUnavailable("Source-repair lease is already owned")
            return RepairLease(
                row.lease_id, row.owner_run_id, self._aware(row.expires_at)
            )
        if row is not None:
            db.delete(row)
            db.flush()
        lease_id = uuid.uuid4()
        expires_at = now + ttl
        db.add(
            AutonomousRepairLease(
                singleton_key="source_repair",
                lease_id=lease_id,
                owner_run_id=context.run_id,
                owner_operator=context.operator.value,
                expires_at=expires_at,
                created_at=now,
            )
        )
        db.flush()
        return RepairLease(lease_id, context.run_id, expires_at)

    def release_repair_lease(
        self,
        db: Session,
        *,
        lease_id: uuid.UUID,
        owner_run_id: uuid.UUID,
    ) -> bool:
        row = db.execute(
            select(AutonomousRepairLease)
            .where(AutonomousRepairLease.singleton_key == "source_repair")
            .with_for_update()
        ).scalar_one_or_none()
        if row is None or row.lease_id != lease_id or row.owner_run_id != owner_run_id:
            raise StaleRepairLease("Repair lease fencing tuple is stale")
        db.delete(row)
        db.flush()
        return True

    def reserve_chat_repair_attempt(
        self, db: Session, *, context: RunContext, signature: str
    ) -> uuid.UUID:
        if context.operator != Operator.CHAT_RELIABILITY:
            raise ValueError("Only chat-reliability can reserve chat repair attempts")
        if _DIGEST.fullmatch(signature) is None:
            raise ValueError("Incident signature must be a server-generated digest")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        self._advisory_lock(db, f"autonomous:chat-attempt:{signature}")
        now = self._clock(db)
        if self._count_chat_repair_attempts(db, signature=signature, now=now) >= 2:
            raise IncidentAttemptLimit("Chat repair attempt budget is exhausted")
        attempt_id = uuid.uuid4()
        db.add(
            AutonomousIncidentAttempt(
                id=attempt_id,
                run_id=context.run_id,
                operator=Operator.CHAT_RELIABILITY.value,
                signature=signature,
                attempted_at=now,
            )
        )
        db.flush()
        return attempt_id

    @staticmethod
    def _count_chat_repair_attempts(
        db: Session, *, signature: str, now: datetime
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(AutonomousIncidentAttempt)
                .where(
                    AutonomousIncidentAttempt.operator
                    == Operator.CHAT_RELIABILITY.value,
                    AutonomousIncidentAttempt.signature == signature,
                    AutonomousIncidentAttempt.attempted_at > now - timedelta(hours=6),
                    AutonomousIncidentAttempt.attempted_at <= now,
                )
            )
            or 0
        )

    def count_chat_repair_attempts(self, db: Session, *, signature: str) -> int:
        if _DIGEST.fullmatch(signature) is None:
            raise ValueError("Incident signature must be a server-generated digest")
        return self._count_chat_repair_attempts(
            db, signature=signature, now=self._clock(db)
        )

    def owns_chat_repair_attempt(
        self,
        db: Session,
        *,
        context: RunContext,
        signature: str,
        attempt_id: uuid.UUID,
    ) -> bool:
        """Validate a budget reservation already atomically owned by this run."""
        if context.operator != Operator.CHAT_RELIABILITY:
            return False
        if _DIGEST.fullmatch(signature) is None:
            raise ValueError("Incident signature must be a server-generated digest")
        self._require_run_context(db, context)
        row = db.get(AutonomousIncidentAttempt, attempt_id)
        if row is None:
            return False
        now = self._clock(db)
        return bool(
            row.run_id == context.run_id
            and row.operator == context.operator.value
            and row.signature == signature
            and self._aware(row.attempted_at) > now - timedelta(hours=6)
            and self._aware(row.attempted_at) <= now
        )

    def qualify_chat_baseline(
        self,
        db: Session,
        *,
        sha: str,
        actor: str,
        expected_revision: int,
        now: datetime,
    ) -> ChatReliabilityBaseline:
        if _SHA.fullmatch(sha) is None or now.tzinfo is None:
            raise ValueError("Chat baseline qualification is invalid")
        self._validate_actor(actor)
        self._advisory_lock(db, "autonomous:chat-baseline")
        row = db.execute(
            select(ChatReliabilityBaseline)
            .where(ChatReliabilityBaseline.singleton.is_(True))
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            if expected_revision != 0:
                raise AutonomousStateConflict("Chat baseline state is stale")
            before_digest = self._state_digest("chat_baseline", "absent")
            row = ChatReliabilityBaseline(singleton=True, revision=1)
            db.add(row)
        else:
            if row.revision != expected_revision:
                raise AutonomousStateConflict("Chat baseline state is stale")
            before_digest = self._state_digest("chat_baseline", row.sha, row.revision)
            row.revision += 1
        row.sha = sha
        row.qualified_by = actor
        row.qualified_at = now
        self._append_control_event(
            db,
            actor=actor,
            event_kind="chat_baseline",
            target="scalable-chat",
            before_digest=before_digest,
            after_digest=self._state_digest("chat_baseline", sha, row.revision),
            now=now,
        )
        db.flush()
        return row

    def set_chat_provider_state(
        self,
        db: Session,
        *,
        context: RunContext,
        environment: str,
        manifest_revision: str,
        expected_state_revision: int,
        active_provider: str,
        reason_code: str,
        now: datetime,
    ) -> ChatProviderRuntimeState:
        if context.operator != Operator.CHAT_RELIABILITY:
            raise ValueError("Only chat-reliability can change chat provider state")
        self.assert_mutation_allowed(db, context)
        self._require_run_context(db, context)
        if environment not in {"staging", "production"} or now.tzinfo is None:
            raise ValueError("Chat provider environment is invalid")
        for value, label, max_length in (
            (manifest_revision, "Provider revision", 128),
            (active_provider, "Active provider", 64),
            (reason_code, "Provider reason code", 64),
        ):
            self._validate_code(value, label=label, max_length=max_length)
        row = db.execute(
            select(ChatProviderRuntimeState)
            .where(ChatProviderRuntimeState.environment == environment)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            if expected_state_revision != 0:
                raise AutonomousStateConflict("Chat provider state is stale")
            before_digest = self._state_digest("provider", environment, "absent")
            row = ChatProviderRuntimeState(environment=environment, state_revision=1)
            db.add(row)
        else:
            if row.state_revision != expected_state_revision:
                raise AutonomousStateConflict("Chat provider state is stale")
            before_digest = self._state_digest(
                "provider",
                environment,
                row.manifest_revision,
                row.active_provider,
                row.state_revision,
            )
            row.state_revision += 1
        row.manifest_revision = manifest_revision
        row.active_provider = active_provider
        row.reason_code = reason_code
        row.updated_at = now
        db.flush()
        self.append_action(
            db,
            context=context,
            capability="switch_chat_provider",
            reason_code=reason_code,
            resource_kind="chat_provider",
            resource_identifier=environment,
            before_digest=before_digest,
            after_digest=self._state_digest(
                "provider",
                environment,
                manifest_revision,
                active_provider,
                row.state_revision,
            ),
            now=now,
        )
        return row
