"""Fail-closed contracts for persistent executor feasibility experiments.

The models in this module describe an experiment before it is allowed to
provision a sandbox or call a model provider.  They intentionally distinguish
preliminary feasibility evidence from release qualification evidence.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

MANIFEST_SCHEMA_VERSION = "persistent-executor-feasibility-v1"
QUALIFICATION_STATUS = "preliminary_feasibility"
EXPECTED_PROFILE_COUNTS = {
    "cold_first_pwd": 1_000,
    "cold_32_way": 32,
    "warm_ack": 1_000,
    "warm_noop": 1_000,
    "connected_stop_one": 1_000,
    "connected_stop_four": 1_000,
    "disconnected_stop_one": 1_000,
    "disconnected_stop_four": 1_000,
    "deadline_one": 1_000,
    "deadline_four": 1_000,
    "reconnect_protocol_peers": 1_000,
    "reconnect_real_modal": 32,
}

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CommitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
ArtifactId = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceFile(_StrictModel):
    path: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$",
    )
    blob_sha: CommitSha
    disposition: Literal["study", "port", "reimplement"]


class TransportSourcePin(_StrictModel):
    repository: Literal["https://github.com/openai/codex"]
    commit_sha: CommitSha
    license: Literal["Apache-2.0"]
    security_profile: Literal["noise_hybrid_ik_v1"]
    files: tuple[SourceFile, ...] = Field(min_length=1, max_length=64)
    dependency_lock_sha256: Sha256
    interoperability_vectors_sha256: Sha256

    @field_validator("files", mode="before")
    @classmethod
    def freeze_files(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_unique_files(self) -> TransportSourcePin:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("transport source paths must be unique")
        return self


class BaselineSnapshot(_StrictModel):
    artifact_id: ArtifactId
    captured_at: str = Field(
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    cohort: Literal["idle", "loaded"]
    host_cpu_percent: float = Field(ge=0, lt=100)
    mem_available_mib: int = Field(ge=0)
    disk_free_mib: int = Field(ge=0)
    event_loop_lag_p99_ms: float = Field(ge=0)
    host_open_fds: int = Field(ge=0)
    postgres_connections: int = Field(ge=0)


class ResourceLimits(_StrictModel):
    host_cpu_percent_exclusive_max: Literal[80]
    host_mem_available_mib_min: Literal[1536]
    disk_free_mib_min: int = Field(ge=1536)
    rendezvous_rss_mib_max: int = Field(ge=64)
    harness_proxy_rss_mib_max: int = Field(ge=64)
    process_fd_max: int = Field(ge=64)
    postgres_connections_total_max: int = Field(ge=1, le=100)
    postgres_connections_incremental_max: int = Field(ge=0)
    postgres_checkpoint_updates_per_second_max: float = Field(gt=0)
    event_loop_lag_p99_ms_max: float = Field(gt=0)
    operation_unacked_bytes_max: Literal[65536]
    turn_stream_unacked_bytes_max: Literal[262144]
    physical_connection_unacked_bytes_max: Literal[524288]
    reserved_control_bytes_per_connection: int = Field(ge=4096, le=65536)
    sampling_interval_ms: int = Field(ge=10, le=5000)
    breach_action: Literal["abort_retain_reservations_and_report_failure"]

    @model_validator(mode="after")
    def validate_buffer_hierarchy(self) -> ResourceLimits:
        if not (
            self.operation_unacked_bytes_max
            < self.turn_stream_unacked_bytes_max
            < self.physical_connection_unacked_bytes_max
        ):
            raise ValueError("transport buffer limits are inconsistent")
        return self


class SpendLimits(_StrictModel):
    total_experiment_microusd: int = Field(gt=0, le=10_000_000)
    pricing_source_id: ArtifactId
    pricing_attested_at: str = Field(
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    sandbox_rate_microusd_per_second: int = Field(gt=0)
    model_provider: Literal["none"]
    provider_call_max: int = Field(ge=0)
    provider_input_token_max: int = Field(ge=0)
    provider_output_token_max: int = Field(ge=0)
    sandbox_create_max: int = Field(gt=0)
    sandbox_billed_seconds_max: int = Field(gt=0)
    sandbox_lifetime_seconds_max: int = Field(ge=240, le=86400)
    blank_reserve_microusd: int = Field(ge=0)
    retained_reserve_microusd: int = Field(ge=0)
    rotation_reserve_microusd: int = Field(ge=0)
    replacement_reserve_microusd: int = Field(ge=0)
    uncertain_usage_reserve_microusd: int = Field(ge=0)
    unknown_usage_retains_reservation: Literal[True]
    budget_exhaustion_action: Literal["stop_new_work_reconcile_covered_turns"]

    @model_validator(mode="after")
    def validate_reserves(self) -> SpendLimits:
        reserve = sum(
            (
                self.blank_reserve_microusd,
                self.retained_reserve_microusd,
                self.rotation_reserve_microusd,
                self.replacement_reserve_microusd,
                self.uncertain_usage_reserve_microusd,
            )
        )
        if reserve >= self.total_experiment_microusd:
            raise ValueError("operating reserves consume the experiment budget")
        if self.provider_call_max == 0 and (
            self.provider_input_token_max or self.provider_output_token_max
        ):
            raise ValueError("provider token limits require provider calls")
        if (
            self.sandbox_create_max * self.sandbox_lifetime_seconds_max
            > self.sandbox_billed_seconds_max
        ):
            raise ValueError("sandbox runtime is not fully reserved")
        sandbox_reserve = (
            self.sandbox_billed_seconds_max * self.sandbox_rate_microusd_per_second
        )
        if sandbox_reserve + reserve > self.total_experiment_microusd:
            raise ValueError("sandbox and operating reserves exceed the budget")
        return self


ProfileName = Literal[
    "cold_first_pwd",
    "cold_32_way",
    "warm_ack",
    "warm_noop",
    "connected_stop_one",
    "connected_stop_four",
    "disconnected_stop_one",
    "disconnected_stop_four",
    "deadline_one",
    "deadline_four",
    "reconnect_protocol_peers",
    "reconnect_real_modal",
]


class FeasibilityProfile(_StrictModel):
    name: ProfileName
    coverage: Literal["local_process", "protocol_simulator", "real_modal"]
    observations: int = Field(gt=0)
    simultaneous_operations: Literal[1, 4, 32, 1000]
    p95_target_ms: int | None = Field(default=None, gt=0)
    p99_target_ms: int | None = Field(default=None, gt=0)
    containment_p95_target_ms: int | None = Field(default=None, gt=0)
    containment_p99_target_ms: int | None = Field(default=None, gt=0)
    includes_saturated_output: bool
    includes_unresponsive_process: bool
    includes_failed_broker_revocation: bool

    @model_validator(mode="after")
    def validate_cancellation_targets(self) -> FeasibilityProfile:
        cancellation = "stop" in self.name or "deadline" in self.name
        containment = (
            self.containment_p95_target_ms,
            self.containment_p99_target_ms,
        )
        if cancellation and (
            (self.p95_target_ms, self.p99_target_ms) != (250, 500)
            or containment != (1000, 2000)
        ):
            raise ValueError(
                "cancellation profiles require delivery and containment KPIs"
            )
        if not cancellation and any(value is not None for value in containment):
            raise ValueError("non-cancellation profiles cannot declare containment KPI")
        return self


class FaultSchedule(_StrictModel):
    peer_loss: tuple[
        Literal[
            "before_delivery",
            "after_acceptance",
            "during_execution",
            "after_terminal_before_delivery",
        ],
        ...,
    ]
    rendezvous_loss: tuple[str, ...] = Field(min_length=4, max_length=4)
    harness_loss: tuple[str, ...] = Field(min_length=4, max_length=4)
    worker_loss: tuple[str, ...] = Field(min_length=4, max_length=4)
    replay_uncertain_commands: Literal[False]

    @field_validator(
        "peer_loss", "rendezvous_loss", "harness_loss", "worker_loss", mode="before"
    )
    @classmethod
    def freeze_boundaries(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_failure_boundaries(self) -> FaultSchedule:
        expected = {
            "before_delivery",
            "after_acceptance",
            "during_execution",
            "after_terminal_before_delivery",
        }
        for values in (
            self.peer_loss,
            self.rendezvous_loss,
            self.harness_loss,
            self.worker_loss,
        ):
            if set(values) != expected:
                raise ValueError("fault schedule must cover every delivery boundary")
        return self


class PersistentExecutorFeasibilityManifest(_StrictModel):
    schema_version: Literal["persistent-executor-feasibility-v1"]
    status: Literal["preliminary_feasibility"]
    manifest_id: ArtifactId
    frozen_at: str = Field(
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    environment: Literal["pwc-chat-staging"]
    modal_region: str = Field(min_length=2, max_length=64)
    worker_shape: str = Field(min_length=1, max_length=64)
    image_reference: str = Field(min_length=1, max_length=256)
    image_digest: Sha256
    source_commit: CommitSha
    protocol_digest: Sha256
    schema_digest: Sha256
    transport_source: TransportSourcePin
    baseline_reference: ArtifactId
    baselines: tuple[BaselineSnapshot, BaselineSnapshot]
    resource_limits: ResourceLimits
    spend_limits: SpendLimits
    offered_requests_per_second: int = Field(gt=0, le=1000)
    duration_seconds: int = Field(gt=0, le=7200)
    percentile_method: Literal["nearest_rank"]
    profiles: tuple[FeasibilityProfile, ...] = Field(min_length=12, max_length=12)
    faults: FaultSchedule
    stop_on_first_failed_gate: Literal[True]

    @field_validator("baselines", "profiles", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_complete_manifest(self) -> PersistentExecutorFeasibilityManifest:
        if {item.cohort for item in self.baselines} != {"idle", "loaded"}:
            raise ValueError("idle and loaded baselines are required")
        if any(item.artifact_id != self.baseline_reference for item in self.baselines):
            raise ValueError("baseline evidence does not match the frozen reference")
        counts = Counter(item.name for item in self.profiles)
        if set(counts) != set(EXPECTED_PROFILE_COUNTS) or any(
            count != 1 for count in counts.values()
        ):
            raise ValueError("feasibility profile set is incomplete or duplicated")
        for profile in self.profiles:
            if profile.observations != EXPECTED_PROFILE_COUNTS[profile.name]:
                raise ValueError(
                    f"{profile.name} must freeze exactly "
                    f"{EXPECTED_PROFILE_COUNTS[profile.name]} observations"
                )
        coverage = {item.name: item.coverage for item in self.profiles}
        if coverage["cold_first_pwd"] != "real_modal":
            raise ValueError("cold first pwd requires real Modal coverage")
        if coverage["cold_32_way"] != "real_modal":
            raise ValueError("32-way cold acquisition requires real Modal coverage")
        if coverage["reconnect_protocol_peers"] != "protocol_simulator":
            raise ValueError(
                "the 1,000-peer cohort must be protocol-faithful simulation"
            )
        if coverage["reconnect_real_modal"] != "real_modal":
            raise ValueError("reconnect requires a distinct real Modal cohort")
        return self


def validate_manifest(value: object) -> PersistentExecutorFeasibilityManifest:
    """Validate the frozen preflight before any provisioned or billed action."""
    return PersistentExecutorFeasibilityManifest.model_validate(value)


Recommendation = Literal["R1", "R2", "R3", "R4", "R5", "R6"]
EvidenceScenario = Literal[
    "connected_cancel",
    "disconnected_cancel",
    "deadline_watchdog",
    "four_process_overlap",
    "ten_sequential_operations",
    "catalog_call_overlap",
    "bootstrap_vectors",
    "credential_state_machine",
    "recovery_matrix",
    "process_loss_injection",
    "manifest_preflight",
    "budget_exhaustion",
    "cold_first_pwd",
    "cold_32_way",
    "reconnect_protocol_peers",
    "reconnect_real_modal",
]
REQUIRED_RECOMMENDATION_SCENARIOS: dict[Recommendation, frozenset[EvidenceScenario]] = {
    "R1": frozenset({"connected_cancel", "disconnected_cancel", "deadline_watchdog"}),
    "R2": frozenset(
        {"four_process_overlap", "ten_sequential_operations", "catalog_call_overlap"}
    ),
    "R3": frozenset({"bootstrap_vectors", "credential_state_machine"}),
    "R4": frozenset({"recovery_matrix", "process_loss_injection"}),
    "R5": frozenset({"manifest_preflight", "budget_exhaustion"}),
    "R6": frozenset(
        {
            "cold_first_pwd",
            "cold_32_way",
            "reconnect_protocol_peers",
            "reconnect_real_modal",
        }
    ),
}


class FeasibilityEvidence(_StrictModel):
    artifact_id: ArtifactId
    scenario: EvidenceScenario
    source: Literal[
        "deterministic_test",
        "local_process_measurement",
        "protocol_simulator",
        "real_modal_measurement",
    ]
    location: str = Field(min_length=1, max_length=512)
    observations: int = Field(gt=0)
    passed: bool
    unknown_outcomes: int = Field(ge=0)
    retained_reservations: int = Field(ge=0)
    metrics: dict[str, int | float | str | bool] = Field(max_length=64)


class RecommendationResult(_StrictModel):
    recommendation: Recommendation
    status: Literal["passed", "failed", "incomplete"]
    evidence: tuple[FeasibilityEvidence, ...] = Field(max_length=32)
    unresolved_decisions: tuple[str, ...] = Field(max_length=32)

    @field_validator("evidence", "unresolved_decisions", mode="before")
    @classmethod
    def freeze_result_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_status(self) -> RecommendationResult:
        scenarios = {item.scenario for item in self.evidence}
        complete = REQUIRED_RECOMMENDATION_SCENARIOS[self.recommendation] <= scenarios
        all_passed = all(
            item.passed and item.unknown_outcomes == 0 for item in self.evidence
        )
        if self.status == "passed" and (
            not complete or not all_passed or self.unresolved_decisions
        ):
            raise ValueError("recommendation pass lacks complete successful evidence")
        if self.status == "failed" and not any(
            not item.passed for item in self.evidence
        ):
            raise ValueError("failed recommendation lacks failing evidence")
        if (
            self.status == "incomplete"
            and complete
            and all_passed
            and not self.unresolved_decisions
        ):
            raise ValueError("complete successful evidence cannot be marked incomplete")
        return self


class PersistentExecutorFeasibilityReport(_StrictModel):
    schema_version: Literal["persistent-executor-feasibility-report-v1"]
    status: Literal["preliminary_feasibility"]
    manifest_id: ArtifactId
    source_commit: CommitSha
    generated_at: str = Field(
        pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    results: tuple[
        RecommendationResult,
        RecommendationResult,
        RecommendationResult,
        RecommendationResult,
        RecommendationResult,
        RecommendationResult,
    ]

    @field_validator("results", mode="before")
    @classmethod
    def freeze_results(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_recommendations(self) -> PersistentExecutorFeasibilityReport:
        if tuple(result.recommendation for result in self.results) != (
            "R1",
            "R2",
            "R3",
            "R4",
            "R5",
            "R6",
        ):
            raise ValueError("report must contain ordered R1-R6 results")
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return all(result.status == "passed" for result in self.results)


def validate_report(value: object) -> PersistentExecutorFeasibilityReport:
    """Validate a preliminary report without upgrading it to release evidence."""
    return PersistentExecutorFeasibilityReport.model_validate(value)
