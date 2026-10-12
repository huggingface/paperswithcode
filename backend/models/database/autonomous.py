"""Autonomous curation operator, run, budget, and audit persistence models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DDL,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class AutonomousSubmissionClaim(Base):
    """Scoped, expiring ownership and callback receipt for one submission."""

    __tablename__ = "autonomous_submission_claim"

    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pending_edit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pending_paper_edits.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autonomous_run.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autonomous_run.id", ondelete="RESTRICT"),
        nullable=True,
    )
    attested_decision_digest: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    remote_manifest_digest: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    remote_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remote_review_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    callback_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="claimed", server_default="claimed"
    )
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    decision_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('claimed','completed')",
            name="autonomous_submission_claim_state_check",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('approve','reject','defer')",
            name="autonomous_submission_claim_decision_check",
        ),
        CheckConstraint(
            "length(snapshot_digest) = 64 AND length(callback_token_hash) = 64",
            name="autonomous_submission_claim_digest_check",
        ),
        CheckConstraint(
            "decision_digest IS NULL OR length(decision_digest) = 64",
            name="autonomous_submission_claim_decision_digest_check",
        ),
        CheckConstraint(
            "attested_decision_digest IS NULL OR length(attested_decision_digest) = 64",
            name="autonomous_submission_claim_attested_digest_check",
        ),
        CheckConstraint(
            "remote_manifest_digest IS NULL OR length(remote_manifest_digest) = 64",
            name="autonomous_submission_claim_remote_manifest_digest_check",
        ),
        Index(
            "idx_autonomous_submission_claim_pending_state",
            "pending_edit_id",
            "state",
            "expires_at",
        ),
        UniqueConstraint(
            "pending_edit_id",
            "run_id",
            name="uq_autonomous_submission_claim_edit_run",
        ),
    )


class AutonomousOperatorState(Base):
    """Global and per-operator autonomous mutation switches."""

    __tablename__ = "autonomous_operator_state"

    operator: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    manual_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('global','submissions','curation','cron_health','chat_reliability')",
            name="autonomous_operator_state_operator_check",
        ),
        CheckConstraint(
            "operator = 'global' OR NOT manual_mode",
            name="autonomous_operator_state_manual_check",
        ),
        CheckConstraint(
            "operator <> 'global' OR NOT enabled",
            name="autonomous_operator_state_global_check",
        ),
        CheckConstraint(
            "revision > 0", name="autonomous_operator_state_revision_check"
        ),
    )


class AutonomousExecutionIntent(Base):
    """Immutable request identity recorded before any model allocation."""

    __tablename__ = "autonomous_execution_intent"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manifest_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digests: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    model_alias: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    pricing_policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('submissions','curation','cron_health','chat_reliability')",
            name="autonomous_execution_intent_operator_check",
        ),
        CheckConstraint(
            "model_alias IN ('diagnosis','independent_review')",
            name="autonomous_execution_intent_model_alias_check",
        ),
        CheckConstraint(
            "budget_usd > 0 AND length(request_digest) = 64 "
            "AND length(pricing_policy_digest) = 64",
            name="autonomous_execution_intent_integrity_check",
        ),
    )


class AutonomousRun(Base):
    """One immutable, content-free autonomous execution summary."""

    __tablename__ = "autonomous_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manifest_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, server_default="0"
    )
    result_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exit_classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    capability_requests: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    evidence_digests: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    pricing_revision: Mapped[str] = mapped_column(
        String(128), nullable=False, default="unknown", server_default="unknown"
    )
    pricing_policy_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, default="0" * 64, server_default="0" * 64
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('submissions','curation','cron_health','chat_reliability')",
            name="autonomous_run_operator_check",
        ),
        CheckConstraint(
            "status IN ('completed','rejected','failed','budget_exhausted','cancelled')",
            name="autonomous_run_status_check",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0",
            name="autonomous_run_usage_check",
        ),
        CheckConstraint(
            "result_digest IS NULL OR length(result_digest) = 64",
            name="autonomous_run_digest_check",
        ),
        CheckConstraint(
            "exit_classification IN ('unknown','completed','rejected','timeout',"
            "'cancelled','budget_exhausted','malformed_output','process_error',"
            "'output_limit','credential_missing','configuration_missing',"
            "'credential_revoke_failed','interrupted')",
            name="autonomous_run_exit_classification_check",
        ),
        CheckConstraint(
            "length(pricing_policy_digest) = 64",
            name="autonomous_run_pricing_policy_digest_check",
        ),
        UniqueConstraint("id", "operator", name="uq_autonomous_run_id_operator"),
        Index("idx_autonomous_run_operator_created", "operator", "created_at"),
    )


class AutonomousBudgetReservation(Base):
    """Provider-enforced, per-run spend reservation without credential material."""

    __tablename__ = "autonomous_budget_reservation"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    reservation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    attestation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    claim_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="claimed", server_default="claimed"
    )
    authoritative_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    authoritative_output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    authoritative_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, server_default="0"
    )
    cost_upper_bound_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 9), nullable=False, server_default="0"
    )
    reconciliation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('submissions','curation','cron_health','chat_reliability')",
            name="autonomous_budget_reservation_operator_check",
        ),
        CheckConstraint(
            "provider = 'openai'",
            name="autonomous_budget_reservation_provider_check",
        ),
        CheckConstraint(
            "model_alias IN ('diagnosis','independent_review')",
            name="autonomous_budget_reservation_model_alias_check",
        ),
        CheckConstraint(
            "limit_usd > 0 AND length(attestation_digest) = 64",
            name="autonomous_budget_reservation_integrity_check",
        ),
        CheckConstraint(
            "length(request_digest) = 64 AND length(endpoint_digest) = 64 "
            "AND credential_scope = 'responses'",
            name="autonomous_budget_reservation_scope_check",
        ),
        CheckConstraint(
            "state IN ('claimed','released','release_failed','unknown') "
            "AND authoritative_input_tokens >= 0 "
            "AND authoritative_output_tokens >= 0 "
            "AND authoritative_cost_usd >= 0 "
            "AND authoritative_cost_usd <= cost_upper_bound_usd "
            "AND cost_upper_bound_usd <= limit_usd "
            "AND ((state = 'released' AND reconciliation_required = false "
            "AND released_at IS NOT NULL) "
            "OR (state IN ('release_failed','unknown') "
            "AND reconciliation_required = true AND released_at IS NULL) "
            "OR (state = 'claimed' AND reconciliation_required = false "
            "AND released_at IS NULL))",
            name="autonomous_budget_reservation_lifecycle_check",
        ),
    )


class AutonomousAction(Base):
    """One append-only autonomous mutation audit event."""

    __tablename__ = "autonomous_action"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    before_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    after_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('submissions','curation','cron_health','chat_reliability')",
            name="autonomous_action_operator_check",
        ),
        CheckConstraint(
            "before_digest IS NULL OR length(before_digest) = 64",
            name="autonomous_action_before_digest_check",
        ),
        CheckConstraint(
            "after_digest IS NULL OR length(after_digest) = 64",
            name="autonomous_action_after_digest_check",
        ),
        ForeignKeyConstraint(
            ["run_id", "operator"],
            ["autonomous_run.id", "autonomous_run.operator"],
            ondelete="RESTRICT",
            name="fk_autonomous_action_run_operator",
        ),
        Index("idx_autonomous_action_run_created", "run_id", "created_at"),
    )


class AutonomousAlertDelivery(Base):
    """Append-only, content-free autonomous alert delivery receipt."""

    __tablename__ = "autonomous_alert_delivery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resource_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    release_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_state: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fallback_state: Mapped[str] = mapped_column(String(16), nullable=False)
    fallback_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    delivered_route: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('operator_failure','site_impact','lease_timeout',"
            "'repair_started','review_rejected','deploy_succeeded','rollback',"
            "'provider_switch','budget_threshold','both_provider_outage',"
            "'daily_digest')",
            name="autonomous_alert_delivery_event_kind_check",
        ),
        CheckConstraint(
            "severity IN ('info','high','critical')",
            name="autonomous_alert_delivery_severity_check",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN "
            "('submissions','curation','cron_health','chat_reliability')",
            name="autonomous_alert_delivery_operator_check",
        ),
        CheckConstraint(
            "environment IN ('staging','production')",
            name="autonomous_alert_delivery_environment_check",
        ),
        CheckConstraint(
            "primary_state IN ('acknowledged','failed','not_configured','suppressed') "
            "AND fallback_state IN "
            "('acknowledged','failed','not_configured','not_needed','suppressed')",
            name="autonomous_alert_delivery_state_check",
        ),
        CheckConstraint(
            "delivered_route IN ('primary','fallback','none','suppressed')",
            name="autonomous_alert_delivery_route_check",
        ),
        CheckConstraint(
            "length(dedup_key) = 64 AND length(resource_digest) = 64 "
            "AND length(release_digest) = 64",
            name="autonomous_alert_delivery_digest_check",
        ),
        CheckConstraint(
            "(primary_status_code IS NULL OR primary_status_code BETWEEN 100 AND 599) "
            "AND (fallback_status_code IS NULL OR fallback_status_code BETWEEN 100 AND 599)",
            name="autonomous_alert_delivery_status_code_check",
        ),
        Index("idx_autonomous_alert_delivery_created", "created_at"),
    )


class AutonomousReleaseConsumption(Base):
    """Root-owned, single-use authorization consumed at the release boundary."""

    __tablename__ = "autonomous_release_consumption"

    authorization_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autonomous_action.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "action IN ('deploy','rollback')",
            name="autonomous_release_consumption_action_check",
        ),
        CheckConstraint(
            "environment IN ('staging','production')",
            name="autonomous_release_consumption_environment_check",
        ),
        CheckConstraint(
            "length(sha) = 40",
            name="autonomous_release_consumption_sha_check",
        ),
    )


class AutonomousControlEvent(Base):
    """Append-only audit history for human control-plane mutations."""

    __tablename__ = "autonomous_control_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    before_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    after_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('manual_mode','operator_enabled','chat_baseline',"
            "'acceptance_evidence')",
            name="autonomous_control_event_kind_check",
        ),
        CheckConstraint(
            "length(before_digest) = 64 AND length(after_digest) = 64",
            name="autonomous_control_event_digest_check",
        ),
        Index("idx_autonomous_control_event_created", "created_at"),
        Index(
            "uq_autonomous_acceptance_evidence",
            "target",
            "after_digest",
            unique=True,
            postgresql_where=text("event_kind = 'acceptance_evidence'"),
            sqlite_where=text("event_kind = 'acceptance_evidence'"),
        ),
    )


class AutonomousRepairLease(Base):
    """The singleton global source-repair lease."""

    __tablename__ = "autonomous_repair_lease"

    singleton_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    owner_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_operator: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 'source_repair'",
            name="autonomous_repair_lease_singleton_check",
        ),
        ForeignKeyConstraint(
            ["owner_run_id", "owner_operator"],
            ["autonomous_run.id", "autonomous_run.operator"],
            ondelete="RESTRICT",
            name="fk_autonomous_repair_lease_run_operator",
        ),
    )


class AutonomousIncidentAttempt(Base):
    """Content-free source-repair attempt accounting by stable signature."""

    __tablename__ = "autonomous_incident_attempt"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "operator IN ('cron_health','chat_reliability')",
            name="autonomous_incident_attempt_operator_check",
        ),
        CheckConstraint(
            "length(signature) = 64",
            name="autonomous_incident_attempt_signature_check",
        ),
        ForeignKeyConstraint(
            ["run_id", "operator"],
            ["autonomous_run.id", "autonomous_run.operator"],
            ondelete="RESTRICT",
            name="fk_autonomous_incident_attempt_run_operator",
        ),
        Index(
            "idx_autonomous_incident_attempt_window",
            "operator",
            "signature",
            "attempted_at",
        ),
    )


for _table, _operation, _trigger in (
    (
        AutonomousExecutionIntent.__table__,
        "UPDATE",
        "autonomous_execution_intent_no_update",
    ),
    (
        AutonomousExecutionIntent.__table__,
        "DELETE",
        "autonomous_execution_intent_no_delete",
    ),
    (AutonomousRun.__table__, "UPDATE", "autonomous_run_no_update"),
    (AutonomousRun.__table__, "DELETE", "autonomous_run_no_delete"),
    (
        AutonomousBudgetReservation.__table__,
        "DELETE",
        "autonomous_budget_reservation_no_delete",
    ),
    (AutonomousAction.__table__, "UPDATE", "autonomous_action_no_update"),
    (AutonomousAction.__table__, "DELETE", "autonomous_action_no_delete"),
    (
        AutonomousAlertDelivery.__table__,
        "UPDATE",
        "autonomous_alert_delivery_no_update",
    ),
    (
        AutonomousAlertDelivery.__table__,
        "DELETE",
        "autonomous_alert_delivery_no_delete",
    ),
    (AutonomousControlEvent.__table__, "UPDATE", "autonomous_control_no_update"),
    (AutonomousControlEvent.__table__, "DELETE", "autonomous_control_no_delete"),
    (AutonomousIncidentAttempt.__table__, "UPDATE", "autonomous_attempt_no_update"),
    (AutonomousIncidentAttempt.__table__, "DELETE", "autonomous_attempt_no_delete"),
):
    event.listen(
        _table,
        "after_create",
        DDL(
            f"CREATE TRIGGER {_trigger} BEFORE {_operation} ON {_table.name} "
            f"BEGIN SELECT RAISE(ABORT, '{_table.name} is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )
