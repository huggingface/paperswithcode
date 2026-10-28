"""Chat model-provider accounting, budget, and runtime-state persistence models."""

from datetime import date, datetime
from typing import Optional

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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.models.database.base import Base


class ChatTitleBudgetState(Base):
    """Environment-isolated monthly circuit for server-funded chat titles."""

    __tablename__ = "chat_title_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    application_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_title_budget_cycle"
        ),
        CheckConstraint(
            "spent_microusd >= 0 AND reserved_microusd >= 0 "
            "AND circuit_state IN ('armed','warning','tripped')",
            name="chat_title_budget_state_check",
        ),
    )


class ChatTitleProviderCall(Base):
    """Idempotent reservation and settlement for one title-generation attempt."""

    __tablename__ = "chat_title_provider_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_title_budget_states.id"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger)
    input_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)
    output_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)
    provider_generation_id: Mapped[Optional[str]] = mapped_column(Text)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','settled','released')",
            name="chat_title_provider_calls_state_check",
        ),
        CheckConstraint(
            "reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0) AND "
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="chat_title_provider_calls_nonnegative_check",
        ),
        Index(
            "idx_chat_title_calls_cycle",
            "environment",
            "billing_cycle",
            "state",
        ),
    )


class ChatTitleBudgetEvent(Base):
    """Content-free title-circuit transition and alert-delivery record."""

    __tablename__ = "chat_title_budget_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_title_budget_states.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    fallback_delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "budget_state_id", "event_type", name="uq_chat_title_budget_event"
        ),
        Index("idx_chat_title_budget_events_delivery", "delivery_state", "created_at"),
    )


class ChatWebSearchBudgetState(Base):
    """UTC-month Exa request budget and fail-closed circuit state."""

    __tablename__ = "chat_web_search_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    hard_limit_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    provider_cost_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    last_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_result_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    trip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_provider_error_class: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_web_search_budget_cycle"
        ),
        CheckConstraint(
            "circuit_state IN ('armed','warning','cooldown','tripped')",
            name="chat_web_search_budget_circuit_check",
        ),
        CheckConstraint(
            "call_count >= 0 AND success_count >= 0 AND failure_count >= 0 AND "
            "provider_cost_microusd >= 0 AND warning_calls > 0 AND "
            "hard_limit_calls >= warning_calls",
            name="chat_web_search_budget_counts_check",
        ),
    )


class ChatWebSearchCircuitEvent(Base):
    """Content-free operator event for the web-search circuit."""

    __tablename__ = "chat_web_search_circuit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_web_search_budget_states.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index("idx_chat_web_search_events_recent", "budget_state_id", "created_at"),
    )


class ChatWebSearchOwnerUsage(Base):
    """Opaque concentration telemetry; never a user-visible allowance."""

    __tablename__ = "chat_web_search_owner_usage"

    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    billing_cycle: Mapped[date] = mapped_column(Date, primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatOpenRouterCredential(Base):
    """Write-only, owner-scoped encrypted OpenRouter inference credential."""

    __tablename__ = "chat_openrouter_credentials"

    hf_user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fallback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    credential_revision: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatOpenRouterMonthlyUsage(Base):
    """Authoritative funded OpenRouter usage for one HF subject and UTC month."""

    __tablename__ = "chat_openrouter_monthly_usage"

    hf_user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    limit_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    spent_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    unknown_cost_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "limit_microusd > 0 AND reserved_microusd >= 0 AND "
            "spent_microusd >= 0 AND unknown_cost_calls >= 0",
            name="chat_openrouter_monthly_usage_nonnegative_check",
        ),
    )


class ChatOpenRouterProviderCall(Base):
    """Idempotent funded-provider reservation and trusted settlement ledger."""

    __tablename__ = "chat_openrouter_provider_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    call_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    model_route: Mapped[str] = mapped_column(String(255), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    upstream_provider: Mapped[Optional[str]] = mapped_column(String(128))
    routing_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="throughput"
    )
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cache_read_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cache_creation_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    provider_ttft_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fallback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    request_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    system_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    tool_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    conversation_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    generation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','settled','released','cost_unknown')",
            name="chat_openrouter_provider_calls_state_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','medium','high','max')",
            name="chat_openrouter_provider_calls_reasoning_effort_check",
        ),
        CheckConstraint(
            "reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0)",
            name="chat_openrouter_provider_calls_nonnegative_check",
        ),
        UniqueConstraint(
            "turn_id", "call_sequence", name="uq_chat_openrouter_turn_call"
        ),
        Index(
            "idx_chat_openrouter_calls_owner_month",
            "hf_user_id",
            "month_start",
        ),
        Index("idx_chat_openrouter_calls_state_updated", "state", "updated_at"),
    )


class ChatOpenAIMonthlyUsage(Base):
    """Authoritative server-funded direct-OpenAI usage for one owner/month."""

    __tablename__ = "chat_openai_monthly_usage"

    owner_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    limit_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    spent_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    unknown_cost_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "limit_microusd > 0 AND reserved_microusd >= 0 AND "
            "spent_microusd >= 0 AND unknown_cost_calls >= 0",
            name="chat_openai_monthly_usage_nonnegative_check",
        ),
    )


class ChatOpenAIProviderCall(Base):
    """Idempotent reservation and trusted Responses API settlement ledger."""

    __tablename__ = "chat_openai_provider_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    call_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    public_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(255), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False)
    service_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="default"
    )
    request_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cached_input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cache_write_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    response_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    provider_ttft_ms: Mapped[Optional[int]] = mapped_column(Integer)
    outcome: Mapped[Optional[str]] = mapped_column(String(64))
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    settlement_source: Mapped[Optional[str]] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','settled','released','cost_unknown')",
            name="chat_openai_provider_calls_state_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','medium','high','max')",
            name="chat_openai_provider_calls_reasoning_effort_check",
        ),
        CheckConstraint(
            "settlement_source IS NULL OR settlement_source IN "
            "('provider_usage','recovered_provider_usage','reserved_ceiling')",
            name="chat_openai_provider_calls_settlement_source_check",
        ),
        CheckConstraint(
            "reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0)",
            name="chat_openai_provider_calls_nonnegative_check",
        ),
        UniqueConstraint("turn_id", "call_sequence", name="uq_chat_openai_turn_call"),
        Index("idx_chat_openai_calls_owner_month", "owner_id", "month_start"),
        Index("idx_chat_openai_calls_state_updated", "state", "updated_at"),
        Index("idx_chat_openai_calls_environment_month", "environment", "month_start"),
    )


class ChatOpenRouterCredentialAudit(Base):
    """Bounded non-secret credential lifecycle audit event."""

    __tablename__ = "chat_openrouter_credential_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "action IN ('connected','replaced','fallback_enabled',"
            "'fallback_disabled','disconnected','invalidated','account_deleted')",
            name="chat_openrouter_credential_audit_action_check",
        ),
        Index("idx_chat_openrouter_credential_audit_created", "created_at"),
    )


class ChatProviderRuntimeState(Base):
    """Content-free active provider revision per environment."""

    __tablename__ = "chat_provider_runtime_state"

    environment: Mapped[str] = mapped_column(String(16), primary_key=True)
    manifest_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    state_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    active_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "environment IN ('staging','production')",
            name="chat_provider_runtime_state_environment_check",
        ),
        CheckConstraint(
            "state_revision > 0",
            name="chat_provider_runtime_state_revision_check",
        ),
    )
