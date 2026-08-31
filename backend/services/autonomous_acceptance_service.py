"""Append-only Task 15 evidence and the only supported operator enable gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import AutonomousControlEvent, ChatReliabilityBaseline
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    AutonomousStateConflict,
    ControlState,
    Operator,
)


_REQUIREMENTS: dict[Operator, frozenset[str]] = {
    Operator.SUBMISSIONS: frozenset(
        {
            "oldest_first",
            "max_batch",
            "human_only_deferral",
            "external_no_enrichment",
            "callback_idempotency",
        }
    ),
    Operator.CURATION: frozenset(
        {
            "dispatcher_preflight",
            "capability_isolation",
            "callback_idempotency",
            "paused_callback_apply",
        }
    ),
    Operator.CRON_HEALTH: frozenset(
        {
            "shadow_diagnosis",
            "missed_schedule",
            "stale_log",
            "stale_durable_data",
            "safe_retry",
            "rejected_schema_change",
            "source_repair",
            "failed_production_verification",
            "rollback",
        }
    ),
    Operator.CHAT_RELIABILITY: frozenset(
        {
            "qualified_baseline",
            "qualified_fallback",
            "atomic_provider_manifest",
            "billing_auth_failover",
            "threshold_failover",
            "fallback_restoration",
            "broken_stream",
            "persistence_reopen",
            "independent_review_rejection",
            "staging_canary_failure",
            "production_rollback",
            "privacy_redaction",
            "retry_exhaustion",
            "daily_review_cycle",
            "synthetic_cycle",
        }
    ),
}
_SHADOW_GATE = "shadow_comparison"
_CHAT_BASELINE_PENDING = "scalable_chat_baseline_reconciliation_pending"


class AcceptanceNotReady(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptanceReadiness:
    operator: Operator
    ready: bool
    passed_gates: tuple[str, ...]
    missing_gates: tuple[str, ...]
    shadow_days: int
    required_shadow_days: int


class AutonomousAcceptanceService:
    def __init__(
        self, repository: AutonomousOperationsRepository | None = None
    ) -> None:
        self.repository = repository or AutonomousOperationsRepository()

    @staticmethod
    def _target(operator: Operator, gate_code: str) -> str:
        if (gate_code == _SHADOW_GATE and operator is not Operator.SUBMISSIONS) or (
            gate_code != _SHADOW_GATE and gate_code not in _REQUIREMENTS[operator]
        ):
            raise ValueError("Unknown autonomous acceptance gate")
        return f"{operator.value}:{gate_code}"

    def record_evidence(
        self,
        db: Session,
        *,
        operator: Operator,
        gate_code: str,
        evidence_digest: str,
        actor: str,
        occurred_at: datetime,
    ) -> uuid.UUID:
        if (
            operator is Operator.CHAT_RELIABILITY
            and db.scalar(
                select(ChatReliabilityBaseline).where(
                    ChatReliabilityBaseline.singleton.is_(True)
                )
            )
            is None
        ):
            raise ValueError(
                "Chat acceptance is locked pending the qualified scalable-chat baseline"
            )
        target = self._target(operator, gate_code)
        return self.repository.append_acceptance_evidence(
            db,
            target=target,
            evidence_digest=evidence_digest,
            actor=actor,
            occurred_at=occurred_at,
        )

    def readiness(self, db: Session, operator: Operator) -> AcceptanceReadiness:
        if (
            operator is Operator.CHAT_RELIABILITY
            and db.scalar(
                select(ChatReliabilityBaseline).where(
                    ChatReliabilityBaseline.singleton.is_(True)
                )
            )
            is None
        ):
            return AcceptanceReadiness(
                operator,
                False,
                (),
                tuple(sorted((*_REQUIREMENTS[operator], _CHAT_BASELINE_PENDING))),
                0,
                0,
            )
        prefix = f"{operator.value}:"
        rows = list(
            db.scalars(
                select(AutonomousControlEvent).where(
                    AutonomousControlEvent.event_kind == "acceptance_evidence",
                    AutonomousControlEvent.target.like(f"{prefix}%"),
                )
            )
        )
        gates = {row.target.removeprefix(prefix) for row in rows}
        shadow_days = len(
            {
                row.created_at.date()
                for row in rows
                if row.target == f"{prefix}{_SHADOW_GATE}"
            }
        )
        required_shadow_days = 7 if operator is Operator.SUBMISSIONS else 0
        missing = tuple(sorted(_REQUIREMENTS[operator] - gates))
        ready = not missing and shadow_days >= required_shadow_days
        return AcceptanceReadiness(
            operator,
            ready,
            tuple(sorted(gates)),
            missing,
            shadow_days,
            required_shadow_days,
        )

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
        control = self.repository.get_control_state(db)
        if control.revision != expected_revision:
            raise AutonomousStateConflict("Autonomous control state is stale")
        if enabled:
            readiness = self.readiness(db, operator)
            if not readiness.ready:
                raise AcceptanceNotReady(
                    "Autonomous operator acceptance evidence is incomplete"
                )
        return self.repository.set_operator_enabled(
            db,
            operator=operator,
            enabled=enabled,
            expected_revision=expected_revision,
            actor=actor,
            now=now,
        )
