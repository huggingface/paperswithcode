"""Administrative staging-access and autonomous-operations API contracts."""

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class StagingAccessRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hf_username: str
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime


AutonomousDisplayState = Literal[
    "healthy", "degraded", "repairing", "rolled-back", "manual"
]
AutonomousOperatorName = Literal[
    "submissions", "curation", "cron_health", "chat_reliability"
]


class AutonomousOperatorStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: AutonomousOperatorName
    enabled: bool
    status: AutonomousDisplayState
    monitoring_active: bool
    next_scheduled_run: datetime | None = None


class AutonomousLeaseStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str
    owner_run_id: str
    owner_operator: Literal["cron_health", "chat_reliability"]
    expires_at: datetime


class AutonomousCostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_usd: str = Field(pattern=r"^\d+\.\d{9}$")


class AutonomousBaselineStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    revision: int = Field(ge=1)
    qualified_by: str
    qualified_at: datetime


class AutonomousProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["staging", "production"]
    manifest_revision: str
    state_revision: int = Field(ge=1)
    active_provider: str
    reason_code: str
    updated_at: datetime


class AutonomousRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    operator: AutonomousOperatorName
    dry_run: bool
    status: str
    exit_classification: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: str = Field(pattern=r"^\d+\.\d{9}$")
    created_at: datetime


class AutonomousActionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    run_id: str
    operator: AutonomousOperatorName
    capability: str
    reason_code: str
    resource_kind: str
    resource_identifier: str
    created_at: datetime


class AutonomousOperationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    manual_mode: bool
    monitoring_active: bool
    display_state: AutonomousDisplayState
    operators: List[AutonomousOperatorStatus]
    active_lease: AutonomousLeaseStatus | None
    costs: AutonomousCostSummary
    baseline: AutonomousBaselineStatus | None
    provider_states: List[AutonomousProviderStatus]
    recent_runs: List[AutonomousRunSummary]
    recent_actions: List[AutonomousActionSummary]
    exclusions: List[str]


class AutonomousManualModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_revision: int = Field(ge=1)
    confirmation: Literal["SET_MANUAL_MODE"]


class AutonomousOperatorStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_revision: int = Field(ge=1)
    confirmation: Literal["SET_OPERATOR_STATE"]


class AutonomousBaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_revision: int = Field(ge=0)
    confirmation: Literal["QUALIFY_CHAT_BASELINE"]


class AutonomousAcceptanceEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: Literal["RECORD_ACCEPTANCE_EVIDENCE"]


class AutonomousAcceptanceReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: AutonomousOperatorName
    ready: bool
    passed_gates: List[str]
    missing_gates: List[str]
    shadow_days: int = Field(ge=0)
    required_shadow_days: int = Field(ge=0)


class AutonomousAcceptanceEvidenceResponse(AutonomousAcceptanceReadinessResponse):
    evidence_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


__all__ = [
    "StagingAccessRequestResponse",
    "AutonomousOperatorStatus",
    "AutonomousLeaseStatus",
    "AutonomousCostSummary",
    "AutonomousBaselineStatus",
    "AutonomousProviderStatus",
    "AutonomousRunSummary",
    "AutonomousActionSummary",
    "AutonomousOperationsResponse",
    "AutonomousManualModeRequest",
    "AutonomousOperatorStateRequest",
    "AutonomousBaselineRequest",
    "AutonomousAcceptanceEvidenceRequest",
    "AutonomousAcceptanceReadinessResponse",
    "AutonomousAcceptanceEvidenceResponse",
    "AutonomousDisplayState",
    "AutonomousOperatorName",
]
