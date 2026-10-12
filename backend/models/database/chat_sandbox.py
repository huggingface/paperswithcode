"""Chat sandbox, external worker, executor, and qualification persistence models."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.chat import ChatSession


class ChatExecutorTransportCircuit(Base):
    """Shared rollout circuit state for one deployed environment."""

    __tablename__ = "chat_executor_transport_circuits"

    environment: Mapped[str] = mapped_column(String(16), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="closed")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    failure_window_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    open_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    canary_owner: Mapped[Optional[str]] = mapped_column(String(128))
    canary_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    half_open_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    security_reason: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "environment IN ('staging','production')",
            name="chat_executor_transport_circuit_environment_check",
        ),
        CheckConstraint(
            "state IN ('closed','open','half_open','security_hold')",
            name="chat_executor_transport_circuit_state_check",
        ),
        CheckConstraint(
            "revision > 0 AND epoch >= 0 AND consecutive_failures >= 0 "
            "AND half_open_successes >= 0",
            name="chat_executor_transport_circuit_nonnegative_check",
        ),
    )


class ChatExecutorTransportAlert(Base):
    """Content-free durable outbox row for one circuit transition epoch."""

    __tablename__ = "chat_executor_transport_alerts"

    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    environment: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("chat_executor_transport_circuits.environment", ondelete="CASCADE"),
        nullable=False,
    )
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    transition: Mapped[str] = mapped_column(String(24), nullable=False)
    delivery_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    claim_owner: Mapped[Optional[str]] = mapped_column(String(128))
    claim_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "epoch",
            "transition",
            name="uq_chat_executor_transport_alert_epoch",
        ),
        CheckConstraint(
            "environment IN ('staging','production') AND epoch > 0 AND attempts >= 0",
            name="chat_executor_transport_alert_scope_check",
        ),
        CheckConstraint(
            "transition IN ('open','security_hold','recovered') "
            "AND delivery_state IN ('pending','claimed','acknowledged')",
            name="chat_executor_transport_alert_state_check",
        ),
        CheckConstraint(
            "(delivery_state = 'claimed') = "
            "(claim_owner IS NOT NULL AND claim_expires_at IS NOT NULL)",
            name="chat_executor_transport_alert_claim_check",
        ),
    )


class ChatSandboxLease(Base):
    """Durable ownership and recoverable state for one per-chat sandbox."""

    __tablename__ = "chat_sandbox_leases"

    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    egress_policy_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        default="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    )
    worker_generation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="starting"
    )
    lease_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    workspace_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    workspace_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    session: Mapped["ChatSession"] = relationship(back_populates="sandbox_lease")
    __table_args__ = (
        CheckConstraint(
            "state IN ('starting','ready','busy','idle','terminating','terminated','failed')",
            name="chat_sandbox_leases_state_check",
        ),
        Index("idx_chat_sandbox_leases_state_activity", "state", "last_activity_at"),
    )


class ChatExternalWorker(Base):
    """Durable identity, capacity, and fencing for an external Pi worker."""

    __tablename__ = "chat_external_workers"

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    maximum_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    active_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "environment IN ('staging','production')",
            name="chat_external_workers_environment_check",
        ),
        CheckConstraint(
            "state IN ('ready','draining','offline')",
            name="chat_external_workers_state_check",
        ),
        CheckConstraint(
            "generation > 0",
            name="chat_external_workers_generation_check",
        ),
        CheckConstraint(
            "maximum_sessions BETWEEN 1 AND 32",
            name="chat_external_workers_maximum_sessions_check",
        ),
        CheckConstraint(
            "active_sessions BETWEEN 0 AND maximum_sessions",
            name="chat_external_workers_active_sessions_check",
        ),
        Index(
            "idx_chat_external_workers_dispatch",
            "environment",
            "state",
            "contract_version",
            "lease_expires_at",
        ),
    )


class ChatExternalWorkerReservation(Base):
    """Protected per-turn capacity on one exact external worker endpoint."""

    __tablename__ = "chat_external_worker_reservations"

    request_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    turn_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )
    endpoint_id: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instance_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    worker_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    maximum_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "worker_generation > 0",
            name="chat_external_worker_reservations_worker_generation_check",
        ),
        CheckConstraint(
            "maximum_sessions BETWEEN 1 AND 32",
            name="chat_external_worker_reservations_maximum_sessions_check",
        ),
        Index(
            "idx_chat_external_worker_reservations_capacity",
            "worker_id",
            "instance_id",
            "worker_generation",
        ),
        Index(
            "idx_chat_external_worker_reservations_unbound_expiry",
            "expires_at",
            postgresql_where=text("turn_id IS NULL"),
        ),
    )


class ChatExecutorManifest(Base):
    """Immutable component lineage and mutable qualification/capacity state."""

    __tablename__ = "chat_executor_manifests"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_digest: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("chat_executor_manifests.digest"), nullable=True
    )
    image_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_binary_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    daemon_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    release_id: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default="legacy"
    )
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    compatibility_state: Mapped[str] = mapped_column(String(16), nullable=False)
    qualification_evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    ready_capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    compatibility_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "protocol_version > 0 AND ready_capacity >= 0",
            name="chat_executor_manifests_numeric_check",
        ),
        CheckConstraint(
            "qualification_status IN ('pending','qualified','failed')",
            name="chat_executor_manifests_qualification_check",
        ),
        CheckConstraint(
            "compatibility_state IN ('current','compatible','incompatible')",
            name="chat_executor_manifests_compatibility_check",
        ),
        CheckConstraint(
            "length(digest)=64 AND length(image_digest)=64 "
            "AND length(environment_binary_digest)=64 AND length(daemon_digest)=64 "
            "AND length(source_commit)=64 AND length(schema_digest)=64",
            name="chat_executor_manifests_digest_check",
        ),
        CheckConstraint(
            "length(release_id) BETWEEN 1 AND 128",
            name="chat_executor_manifests_release_check",
        ),
    )


class ChatExecutorCell(Base):
    """One durable route, key epoch, and rollout circuit per logical cell."""

    __tablename__ = "chat_executor_cells"

    cell_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    active_shard_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_executor_shards.id",
            name="fk_chat_executor_cells_active_shard",
            use_alter=True,
        ),
        nullable=True,
    )
    selected_manifest_digest: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("chat_executor_manifests.digest"), nullable=True
    )
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="closed"
    )
    circuit_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_window_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    consecutive_attach_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    canary_lease_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    canary_lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    canary_successes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    key_epoch: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    rollback_epoch: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "circuit_state IN ('closed','open','half_open','security_hold')",
            name="chat_executor_cells_circuit_check",
        ),
        CheckConstraint(
            "circuit_revision > 0 AND key_epoch > 0 AND rollback_epoch >= 0 "
            "AND consecutive_attach_failures >= 0 AND canary_successes BETWEEN 0 AND 3",
            name="chat_executor_cells_numeric_check",
        ),
        CheckConstraint(
            "(canary_lease_id IS NULL) = (canary_lease_expires_at IS NULL)",
            name="chat_executor_cells_canary_pair_check",
        ),
    )


class ChatExecutorShard(Base):
    """A generation-addressable rendezvous route within a logical cell."""

    __tablename__ = "chat_executor_shards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cell_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_executor_cells.cell_id"), nullable=False
    )
    shard_id: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    ready_capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    drain_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    drain_deadline_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "cell_id",
            "shard_id",
            "generation",
            name="uq_chat_executor_shard_generation",
        ),
        CheckConstraint(
            "generation > 0 AND ready_capacity >= 0",
            name="chat_executor_shards_numeric_check",
        ),
        CheckConstraint(
            "state IN ('preparing','ready','draining','fenced')",
            name="chat_executor_shards_state_check",
        ),
        CheckConstraint(
            "(drain_started_at IS NULL AND drain_deadline_at IS NULL) OR "
            "(drain_started_at IS NOT NULL AND drain_deadline_at >= drain_started_at)",
            name="chat_executor_shards_drain_check",
        ),
        Index("idx_chat_executor_shards_route", "cell_id", "state", "generation"),
    )


class ChatExecutorRegistration(Base):
    """Public environment identity and fenced lifecycle metadata."""

    __tablename__ = "chat_executor_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cell_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_executor_cells.cell_id"), nullable=False
    )
    shard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_executor_shards.id"), nullable=False
    )
    shard_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    public_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    public_noise_key: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    authorization_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest_digest: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_executor_manifests.digest"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    recovery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    assigned_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "environment_id",
            "environment_generation",
            name="uq_chat_executor_environment_generation",
        ),
        CheckConstraint(
            "environment_generation > 0 AND shard_generation > 0 AND key_epoch > 0 "
            "AND recovery_attempts BETWEEN 0 AND 3",
            name="chat_executor_registrations_generation_check",
        ),
        CheckConstraint(
            "state IN ('pending','ready','assigned_idle','claimed','suspect',"
            "'draining','fenced','terminated')",
            name="chat_executor_registrations_state_check",
        ),
        CheckConstraint(
            "length(public_key_id)=64 AND length(manifest_digest)=64",
            name="chat_executor_registrations_digest_check",
        ),
        CheckConstraint(
            "length(CAST(public_noise_key AS TEXT)) <= 4096",
            name="chat_executor_registrations_public_key_size_check",
        ),
        Index(
            "idx_chat_executor_registrations_ready",
            "cell_id",
            "shard_id",
            "state",
            "expires_at",
        ),
    )


class ChatExecutorNonce(Base):
    """Digest-only, generation-bound single-use authorization evidence."""

    __tablename__ = "chat_executor_nonces"

    nonce_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shard_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('launch','reconnect','liveness','recovery')",
            name="chat_executor_nonces_purpose_check",
        ),
        CheckConstraint(
            "environment_generation > 0 AND shard_generation > 0 AND key_epoch > 0",
            name="chat_executor_nonces_generation_check",
        ),
        CheckConstraint(
            "length(nonce_digest)=64 AND retention_expires_at >= expires_at",
            name="chat_executor_nonces_retention_check",
        ),
        Index("idx_chat_executor_nonces_cleanup", "retention_expires_at"),
    )


class ChatExecutorClaim(Base):
    """Exclusive turn-scoped workspace ownership with copied fence values."""

    __tablename__ = "chat_executor_claims"

    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_executor_registrations.id"), nullable=False
    )
    claim_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cell_id: Mapped[str] = mapped_column(String(64), nullable=False)
    shard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shard_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    environment_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settlement_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    terminal_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "claim_generation > 0 AND shard_generation > 0 AND environment_generation > 0",
            name="chat_executor_claims_generation_check",
        ),
        CheckConstraint(
            "state IN ('active','settled','invalidated')",
            name="chat_executor_claims_state_check",
        ),
        CheckConstraint(
            "(state='active' AND settled_at IS NULL AND settlement_request_id IS NULL) OR "
            "(state<>'active' AND settled_at IS NOT NULL)",
            name="chat_executor_claims_settlement_check",
        ),
        Index(
            "uq_chat_executor_claims_active_registration",
            "registration_id",
            unique=True,
            postgresql_where=text("state='active'"),
            sqlite_where=text("state='active'"),
        ),
        Index("idx_chat_executor_claims_expiry", "state", "expires_at"),
    )


class ChatExecutorKeyRevocation(Base):
    """Idempotent audit of an exact authorization key epoch revocation."""

    __tablename__ = "chat_executor_key_revocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    cell_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    new_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_class: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "cell_id", "new_epoch", name="uq_chat_executor_key_revocation_epoch"
        ),
        CheckConstraint(
            "previous_epoch > 0 AND new_epoch = previous_epoch + 1",
            name="chat_executor_key_revocations_epoch_check",
        ),
    )


class ChatExecutorRollbackAudit(Base):
    """Append-only evidence for one transactional manifest-pointer change."""

    __tablename__ = "chat_executor_rollback_audits"

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cell_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_class: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    target_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    qualification_evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("cell_id", "epoch", name="uq_chat_executor_rollback_epoch"),
        CheckConstraint("epoch > 0", name="chat_executor_rollback_epoch_check"),
        CheckConstraint(
            "outcome IN ('applied')", name="chat_executor_rollback_outcome_check"
        ),
        CheckConstraint(
            "source_digest <> target_digest AND length(source_digest)=64 "
            "AND length(target_digest)=64",
            name="chat_executor_rollback_digest_check",
        ),
    )


class ChatQualificationScope(Base):
    """Server-issued staging qualification cohort and retention boundary."""

    __tablename__ = "chat_qualification_scopes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    profile: Mapped[str] = mapped_column(String(32), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "profile IN ('32-functional-turns','100-immediate-admission')",
            name="chat_qualification_scopes_profile_check",
        ),
        CheckConstraint(
            "window_ended_at IS NULL OR window_ended_at >= window_started_at",
            name="chat_qualification_scopes_window_check",
        ),
        CheckConstraint(
            "expires_at > window_started_at",
            name="chat_qualification_scopes_expiry_check",
        ),
        Index("idx_chat_qualification_scopes_expiry", "expires_at"),
        Index(
            "idx_chat_qualification_scopes_release_profile",
            "app_release_id",
            "profile",
        ),
    )


class ChatQualificationEvidenceEvent(Base):
    """Content-free durable evidence emitted only for protected qualification turns."""

    __tablename__ = "chat_qualification_evidence_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    qualification_scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_qualification_scopes.id",
            ondelete="CASCADE",
            name="chat_qualification_evidence_scope_fkey",
        ),
        nullable=False,
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_turn_jobs.turn_id",
            ondelete="CASCADE",
            name="chat_qualification_evidence_turn_fkey",
        ),
        nullable=False,
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_sessions.id",
            ondelete="CASCADE",
            name="chat_qualification_evidence_session_fkey",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation_digest: Mapped[Optional[str]] = mapped_column(String(64))
    operation_kind: Mapped[Optional[str]] = mapped_column(String(8))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('admitted_no_queue','executor_started','stale_fence','queued',"
            "'workspace_created','workspace_reused','workspace_evicted')",
            name="chat_qualification_evidence_event_type_check",
        ),
        CheckConstraint(
            "(event_type = 'executor_started') = "
            "(operation_digest IS NOT NULL AND operation_kind IS NOT NULL "
            "AND operation_kind IN ('read','bash'))",
            name="chat_qualification_evidence_operation_shape_check",
        ),
        Index(
            "idx_chat_qualification_evidence_scope_event_time",
            "qualification_scope_id",
            "event_type",
            "occurred_at",
        ),
        Index(
            "idx_chat_qualification_evidence_session_time",
            "chat_session_id",
            "occurred_at",
        ),
        Index(
            "idx_chat_qualification_evidence_turn_event",
            "turn_id",
            "event_type",
        ),
        Index(
            "uq_chat_qualification_evidence_stale_turn",
            "qualification_scope_id",
            "turn_id",
            unique=True,
            postgresql_where=text("event_type = 'stale_fence'"),
            sqlite_where=text("event_type = 'stale_fence'"),
        ),
        Index(
            "uq_chat_qualification_evidence_eviction_turn",
            "qualification_scope_id",
            "turn_id",
            unique=True,
            postgresql_where=text("event_type = 'workspace_evicted'"),
            sqlite_where=text("event_type = 'workspace_evicted'"),
        ),
    )


class ChatSandboxPool(Base):
    """Auditable lifecycle for one unassigned blank chat sandbox."""

    __tablename__ = "chat_sandbox_pool"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="starting"
    )
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="generic"
    )
    agent_harness_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    model_profile: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="generic"
    )
    reasoning_profile: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="generic"
    )
    prompt_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    provider_adapter_contract: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    egress_policy_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        default="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    )
    worker_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    claim_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    health_check_token_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    health_check_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cpu_request: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    cpu_limit: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    memory_request_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    blank_billable_seconds: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    estimated_blank_cost_usd: Mapped[float] = mapped_column(
        Numeric(14, 6), nullable=False, server_default="0"
    )
    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_health_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_create_ms: Mapped[Optional[int]] = mapped_column(Integer)
    backend_control_connect_ms: Mapped[Optional[int]] = mapped_column(Integer)
    broker_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    control_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_spawn_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_startup_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "state IN "
            "('starting','blank_ready','claimed','draining','terminated','failed')",
            name="chat_sandbox_pool_state_check",
        ),
        CheckConstraint(
            "cpu_request > 0 AND cpu_limit >= cpu_request",
            name="chat_sandbox_pool_cpu_check",
        ),
        CheckConstraint(
            "memory_request_mib > 0 AND memory_limit_mib >= memory_request_mib",
            name="chat_sandbox_pool_memory_check",
        ),
        CheckConstraint(
            "(health_check_token_hash IS NULL) = (health_check_started_at IS NULL)",
            name="chat_sandbox_pool_health_check_pair_check",
        ),
        Index(
            "idx_chat_sandbox_pool_claim",
            "state",
            "image_version",
            "worker_contract_version",
            "app_release_id",
            "expires_at",
            "ready_at",
        ),
        Index(
            "idx_chat_sandbox_pool_available_health",
            "state",
            "health_check_token_hash",
            "expires_at",
            "ready_at",
        ),
        Index("idx_chat_sandbox_pool_billing", "billing_month", "state"),
    )


class ChatSandboxComputeInterval(Base):
    """Append-only billing lifecycle for one provider sandbox instance."""

    __tablename__ = "chat_sandbox_compute_intervals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    modal_app: Mapped[str] = mapped_column(String(255), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    chat_session_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=True))
    cpu_request_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    cpu_limit_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_request_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    provider_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    termination_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    terminal_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    accrued_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    terminal_reason: Mapped[Optional[str]] = mapped_column(String(64))
    reconciliation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="local"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "origin IN ('blank_pool','direct','qualification','reconciled_orphan')",
            name="chat_sandbox_compute_origin_check",
        ),
        CheckConstraint(
            "accrued_microusd >= 0 AND reserved_microusd >= 0",
            name="chat_sandbox_compute_cost_check",
        ),
        Index(
            "idx_chat_sandbox_compute_cycle_live",
            "environment",
            "billing_cycle",
            "terminal_at",
        ),
    )


class ChatSandboxBudgetState(Base):
    """One durable, worker-shared sandbox spend circuit per billing cycle."""

    __tablename__ = "chat_sandbox_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    application_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    environment_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workspace_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estimated_accrued_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    provider_floor_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    outstanding_reservation_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    trip_reason: Mapped[Optional[str]] = mapped_column(String(64))
    tripped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_metered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reconciled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_reconciliation_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    reconciliation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="unavailable"
    )
    policy_attestation: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_sandbox_budget_cycle"
        ),
        CheckConstraint(
            "circuit_state IN ('armed','warning','tripped')",
            name="chat_sandbox_budget_state_check",
        ),
    )


class ChatSandboxCircuitEvent(Base):
    """Content-free immutable circuit transition and alert-delivery record."""

    __tablename__ = "chat_sandbox_circuit_events"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sandbox_budget_states.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_delivery_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fallback_delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    fallback_delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    fallback_next_delivery_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    fallback_delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index(
            "idx_chat_sandbox_circuit_events_recent", "budget_state_id", "created_at"
        ),
    )


class ChatReliabilityBaseline(Base):
    """Explicitly qualified scalable-chat baseline, without trace content."""

    __tablename__ = "chat_reliability_baseline"

    singleton: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    qualified_by: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint("singleton", name="chat_reliability_baseline_singleton_check"),
        CheckConstraint("length(sha) = 40", name="chat_reliability_baseline_sha_check"),
        CheckConstraint(
            "revision > 0", name="chat_reliability_baseline_revision_check"
        ),
    )
