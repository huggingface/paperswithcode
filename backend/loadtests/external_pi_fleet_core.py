"""Pure, content-free contracts for staging external Pi fleet qualification."""

from __future__ import annotations

import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
)
from deploy.external_pi_qualification_contract import (
    CAPACITY_QUALIFICATION_SHAPES,
    QUALIFICATION_PORTS,
    QUALIFICATION_SHAPES,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
    QUALIFICATION_WORKER_UNITS,
)

EXPECTED_USERS = 100
MIN_PROJECTED_MEM_AVAILABLE_BYTES = 1536 * 1024**2
MAX_REPORT_COUNTER = 1_000_000
MAX_REPORT_DURATION_MS = 60_000
MAX_DURABLE_DURATION_MS = 600_000
P95_TTFT_TARGET_MS = 2_000
MAX_REPORT_BYTES = 2**63 - 1
FleetShapeName = Literal["2x32", "3x32", "4x16", "5x32", "8x16", "16x8"]
DurableWorkload = Literal["no_tool", "read", "bash", "admission_stream"]
FleetFailureStage = Literal[
    "revalidation",
    "resource_sampling",
    "resource_threshold",
    "worker_status",
    "locust_round",
    "counter",
    "replica_lifecycle",
    "cleanup",
]
FleetFailureCode = Literal[
    "revalidation_failed",
    "resource_sampling_failed",
    "resource_threshold_crossed",
    "resource_sampler_stalled",
    "worker_status_failed",
    "locust_round_failed",
    "counter_mismatch",
    "replica_lifecycle_failed",
    "cleanup_failed",
]

PERSISTENT_TRANSPORT_SCENARIOS = (
    "cold_pwd",
    "ten_warm_commands",
    "four_parallel_catalog_calls",
    "sibling_failure_cancel",
    "disconnect_resume",
    "sse_replay",
    "same_account_contention",
    "spend_exhaustion",
    "zero_pool",
    "route_outage",
    "attach_failure",
    "worker_loss",
    "blue_green",
    "mixed_protocol_cohort",
    "invalid_reconnect_traffic",
)
PersistentTransportWorkload = Literal[
    "cold_pwd", "warm_commands", "parallel_catalog", "disconnect_resume"
]
PERSISTENT_TRANSPORT_WORKLOADS: tuple[PersistentTransportWorkload, ...] = (
    "cold_pwd",
    "warm_commands",
    "parallel_catalog",
    "disconnect_resume",
)


class FleetRunRefused(RuntimeError):
    """The requested fleet qualification violates a fail-closed contract."""


@dataclass(frozen=True, slots=True)
class PersistentTransportUserSpec:
    """One of exactly 32 immediate turns, each reserving four operations."""

    ordinal: int
    workload: PersistentTransportWorkload
    operation_limit: Literal[4] = 4
    application_queue: Literal[False] = False


def build_persistent_transport_user_specs() -> tuple[PersistentTransportUserSpec, ...]:
    return tuple(
        PersistentTransportUserSpec(
            ordinal=ordinal,
            workload=PERSISTENT_TRANSPORT_WORKLOADS[ordinal % 4],
        )
        for ordinal in range(32)
    )


class PersistentTransportQualificationManifest(BaseModel):
    """Frozen release gate layered on, never substituted for, fleet profiles."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["persistent-executor-release-qualification-v1"]
    status: Literal["release_qualification"]
    attempt_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    preliminary_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_component_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    modal_image_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    modal_region: str = Field(min_length=2, max_length=64)
    chaos_declared: Literal[False]
    percentile_method: Literal["nearest_rank"]
    scenarios: tuple[str, ...] = Field(min_length=15, max_length=15)
    concurrent_turns: Literal[32]
    operations_per_turn: Literal[4]
    concurrent_operations: Literal[128]
    offered_turns: Literal[64]
    overload_rejections: Literal[32]
    loaded_clients: Literal[1000]
    minimum_soak_turns: Literal[320]
    minimum_soak_minutes: Literal[60]
    reconnect_ready_p99_ms_max: Literal[5000]
    authentication_starts_per_second_max: Literal[250]
    route_health_ms_max: Literal[5000]
    breaker_open_failures: Literal[3]
    breaker_failure_window_seconds: Literal[60]
    breaker_open_seconds: Literal[30]
    breaker_close_successes: Literal[3]
    drain_seconds_max: Literal[240]
    alert_ack_ms_max: Literal[60000]
    heartbeat_checkpoint_updates_per_second_max: Literal[34]
    public_operation_output_bytes_max: Literal[24576]
    public_turn_output_bytes_max: Literal[98304]
    operation_unacked_bytes_max: Literal[65536]
    stream_unacked_bytes_max: Literal[262144]
    connection_unacked_bytes_max: Literal[524288]
    command_bytes_max: Literal[65536]
    path_bytes_max: Literal[4096]
    bash_timeout_ms_max: Literal[30000]
    remote_read_bytes_max: Literal[1048576]
    preauth_frame_bytes_max: Literal[2048]
    preauth_deadline_ms_max: Literal[2000]
    invalid_per_source_rate: Literal[10]
    invalid_per_source_burst: Literal[20]
    invalid_per_shard_rate: Literal[100]
    invalid_per_shard_burst: Literal[200]
    host_cpu_percent_exclusive_max: Literal[80]
    host_mem_available_mib_min: Literal[1536]
    total_spend_microusd_max: int = Field(gt=0, le=16_250_000)
    provider_call_max: Literal[0]
    retain_unknown_spend_reservation: Literal[True]
    stop_on_first_failed_gate: Literal[True]

    @field_validator("scenarios", mode="before")
    @classmethod
    def freeze_scenarios(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_scenarios(self) -> PersistentTransportQualificationManifest:
        if self.scenarios != PERSISTENT_TRANSPORT_SCENARIOS:
            raise ValueError("persistent transport qualification scenarios changed")
        if (
            self.concurrent_turns * self.operations_per_turn
            != self.concurrent_operations
        ):
            raise ValueError("persistent transport operation capacity is inconsistent")
        if self.offered_turns - self.concurrent_turns != self.overload_rejections:
            raise ValueError(
                "persistent transport overload denominator is inconsistent"
            )
        return self


def validate_persistent_transport_manifest(
    value: object,
) -> PersistentTransportQualificationManifest:
    """Reject incomplete release evidence before any provisioned work."""

    return PersistentTransportQualificationManifest.model_validate(value)


class PersistentTransportPercentiles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    denominator: int = Field(gt=0, le=1_000_000)
    accepted: int = Field(ge=0, le=1_000_000)
    p50_ms: int = Field(ge=0, le=600_000)
    p95_ms: int = Field(ge=0, le=600_000)
    p99_ms: int = Field(ge=0, le=600_000)

    @model_validator(mode="after")
    def validate_order(self) -> PersistentTransportPercentiles:
        if (
            self.accepted > self.denominator
            or not self.p50_ms <= self.p95_ms <= self.p99_ms
        ):
            raise ValueError("persistent transport percentile evidence is inconsistent")
        return self


class PersistentTransportCohortReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    transport: Literal["persistent", "legacy"]
    offered: int = Field(ge=0, le=1_000_000)
    admitted: int = Field(ge=0, le=1_000_000)
    completed: int = Field(ge=0, le=1_000_000)
    rejected_pre_work: int = Field(ge=0, le=1_000_000)
    failed: int = Field(ge=0, le=1_000_000)
    candidate_denominator: int = Field(ge=0, le=1_000_000)
    failure_attribution: dict[str, int] = Field(max_length=64)

    @model_validator(mode="after")
    def validate_counts(self) -> PersistentTransportCohortReport:
        if self.offered != self.admitted + self.rejected_pre_work:
            raise ValueError("persistent transport offered denominator is inconsistent")
        if self.admitted != self.completed + self.failed:
            raise ValueError(
                "persistent transport terminal denominator is inconsistent"
            )
        if self.candidate_denominator > self.admitted:
            raise ValueError(
                "persistent transport candidate denominator is inconsistent"
            )
        if sum(self.failure_attribution.values()) != self.failed:
            raise ValueError("persistent transport failure attribution is inconsistent")
        return self


class PersistentTransportResourceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    peak_cpu_percent: float = Field(ge=0, le=100)
    minimum_host_mem_available_mib: int = Field(ge=0)
    peak_rendezvous_rss_mib: int = Field(ge=0)
    peak_harness_proxy_rss_mib: int = Field(ge=0)
    peak_process_fds: int = Field(ge=0)
    peak_postgres_connections: int = Field(ge=0)
    event_loop_lag_p99_ms: float = Field(ge=0)
    operation_unacked_bytes_peak: int = Field(ge=0)
    stream_unacked_bytes_peak: int = Field(ge=0)
    connection_unacked_bytes_peak: int = Field(ge=0)
    process_unacked_bytes_peak: int = Field(ge=0)
    postgres_checkpoint_updates_per_second: float = Field(ge=0)
    heartbeat_receives_per_second: float = Field(ge=0)


class PersistentTransportPoolCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    active: int = Field(ge=0, le=1_000_000)
    assigned_idle: int = Field(ge=0, le=1_000_000)
    blank: int = Field(ge=0, le=1_000_000)
    draining: int = Field(ge=0, le=1_000_000)
    terminated: int = Field(ge=0, le=1_000_000)


# Frozen end-to-end targets; missing cohorts cannot be treated as passes.
PERSISTENT_LATENCY_GATES = {
    "cold_first_pwd": (2000, 5000),
    "warm_ack": (500, 1000),
    "warm_noop": (1000, 2000),
    "pool_hit_readiness": (1000, 2000),
    "reconnect_ready": (5000, 5000),
    "browser_resume": (2000, 5000),
    "cancellation_delivery": (250, 500),
    "process_containment": (1000, 2000),
}


class PersistentTransportSoakReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    turns: int = Field(ge=0)
    failed: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_failures(self) -> PersistentTransportSoakReport:
        if self.failed > self.turns:
            raise ValueError("soak failure denominator is inconsistent")
        return self


class PersistentTransportQualificationReport(BaseModel):
    """Immutable content-free evidence emitted even when a gate fails."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["persistent-executor-release-report-v1"]
    qualification_kind: Literal["release", "chaos"]
    status: Literal["passed", "failed"]
    attempt_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    modal_region: str = Field(min_length=2, max_length=64)
    pool_counts_by_digest: dict[str, PersistentTransportPoolCounts] = Field(
        max_length=2
    )
    cohorts: tuple[PersistentTransportCohortReport, PersistentTransportCohortReport]
    percentiles: dict[str, PersistentTransportPercentiles] = Field(
        min_length=1, max_length=64
    )
    resources: PersistentTransportResourceReport
    soak: PersistentTransportSoakReport
    scenario_outcomes: dict[str, Literal["passed", "failed"]] = Field(
        min_length=15, max_length=15
    )
    duplicate_executions: int = Field(ge=0)
    leaked_environments: int = Field(ge=0)
    breaker_openings: int = Field(ge=0)
    false_global_circuit_trips: int = Field(ge=0)
    reconnect_token_issued: int = Field(ge=0)
    reconnect_token_refreshed: int = Field(ge=0)
    reconnect_token_consumed: int = Field(ge=0)
    reconnect_token_replayed: int = Field(ge=0)
    reconnect_token_expired: int = Field(ge=0)
    reconnect_token_cleaned: int = Field(ge=0)
    cancellation_delivery_observations: int = Field(ge=0)
    process_containment_observations: int = Field(ge=0)
    settlement_count: int = Field(ge=0)
    truncation_markers_missing: int = Field(ge=0)
    control_frame_starvation_events: int = Field(ge=0)

    @field_validator("cohorts", mode="before")
    @classmethod
    def freeze_cohorts(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_release_result(self) -> PersistentTransportQualificationReport:
        if not self.pool_counts_by_digest or any(
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in self.pool_counts_by_digest
        ):
            raise ValueError("persistent transport pool digest evidence is invalid")
        if tuple(item.transport for item in self.cohorts) != ("persistent", "legacy"):
            raise ValueError("persistent and legacy cohorts must remain separate")
        if set(self.scenario_outcomes) != set(PERSISTENT_TRANSPORT_SCENARIOS):
            raise ValueError("persistent transport scenario evidence is incomplete")
        hard_failures = (
            self.duplicate_executions
            + self.leaked_environments
            + self.false_global_circuit_trips
            + self.truncation_markers_missing
            + self.control_frame_starvation_events
        )
        gates_pass = (
            not hard_failures
            and self.soak.turns >= 320
            and self.soak.duration_seconds >= 3600
            and self.soak.failed * 100 <= self.soak.turns
            and all(
                name in self.percentiles
                and self.percentiles[name].denominator >= 1000
                and self.percentiles[name].accepted
                == self.percentiles[name].denominator
                and self.percentiles[name].p95_ms <= targets[0]
                and self.percentiles[name].p99_ms <= targets[1]
                for name, targets in PERSISTENT_LATENCY_GATES.items()
            )
            and self.resources.peak_cpu_percent < 80
            and self.resources.minimum_host_mem_available_mib >= 1536
            and self.resources.operation_unacked_bytes_peak <= 65_536
            and self.resources.stream_unacked_bytes_peak <= 262_144
            and self.resources.connection_unacked_bytes_peak <= 524_288
            and self.resources.postgres_checkpoint_updates_per_second <= 34
            and not any(value == "failed" for value in self.scenario_outcomes.values())
            and (self.qualification_kind == "chaos" or self.breaker_openings == 0)
        )
        if self.status == "passed" and not gates_pass:
            raise ValueError("persistent transport pass contains a failed gate")
        if self.qualification_kind == "chaos" and self.status == "passed":
            raise ValueError("chaos evidence cannot be labeled release-passing")
        return self


def validate_persistent_transport_report(
    value: object,
) -> PersistentTransportQualificationReport:
    return PersistentTransportQualificationReport.model_validate(value)


@dataclass(frozen=True, slots=True)
class DurableQualificationProfile:
    name: Literal["32-functional-turns", "100-immediate-admission"]
    expected_users: Literal[32, 100]
    spawn_rate: Literal[32, 100]
    workloads: tuple[DurableWorkload, ...]
    minimum_available_bytes: int = MIN_PROJECTED_MEM_AVAILABLE_BYTES
    application_queue: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            len(self.workloads) != self.expected_users
            or self.spawn_rate != self.expected_users
            or self.minimum_available_bytes != MIN_PROJECTED_MEM_AVAILABLE_BYTES
        ):
            raise ValueError("durable qualification profile is inconsistent")


class DurableTurnObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workload: DurableWorkload
    outcome: Literal["completed", "refused", "failed"]
    admission_ms: int | None = Field(default=None, ge=0, le=MAX_DURABLE_DURATION_MS)
    reconnect_ready_ms: int | None = Field(
        default=None, ge=0, le=MAX_DURABLE_DURATION_MS
    )
    ttft_ms: int | None = Field(default=None, ge=0, le=MAX_DURABLE_DURATION_MS)
    completion_ms: int | None = Field(default=None, ge=0, le=MAX_DURABLE_DURATION_MS)
    reconnects: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    reconnect_successes: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    model_starts: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    operation_start_count: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    duplicate_operation_start_count: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    queued_states: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    stale_mutations: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    duplicate_turns: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    terminal_cause: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{0,63}$")
    failure_code: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_]{0,63}$")

    @model_validator(mode="after")
    def validate_reconnects(self) -> DurableTurnObservation:
        if self.reconnect_successes > self.reconnects:
            raise ValueError("durable turn reconnect counts are inconsistent")
        milestones = (self.admission_ms, self.reconnect_ready_ms, self.ttft_ms)
        present = tuple(value for value in milestones if value is not None)
        if present != tuple(sorted(present)):
            raise ValueError("durable turn latency milestones are inconsistent")
        return self


class ModalLifecycleSnapshot(BaseModel):
    """Cumulative content-free application lifecycle evidence at one boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    captured_at_ms: int = Field(ge=0, le=MAX_REPORT_BYTES)
    creates: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    reuses: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    evictions: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    active_duration_ms: int = Field(ge=0, le=MAX_REPORT_BYTES)
    source: Literal["application_modal_lifecycle"]


class ModalLifecycleDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    creates: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    reuses: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    evictions: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    active_duration_ms: int = Field(ge=0, le=MAX_REPORT_BYTES)


class ModalRateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    microusd_per_second: int = Field(ge=1, le=MAX_REPORT_COUNTER)
    source: Literal["protected_runtime"]
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
    release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    attested_at_ms: int = Field(ge=1, le=MAX_REPORT_BYTES)


def load_modal_rate_evidence(
    environment: Mapping[str, str],
    *,
    expected_release: str,
    window_started_at_ms: int,
    window_ended_at_ms: int,
    now_ms: int,
) -> ModalRateEvidence:
    """Load one explicit protected runtime rate; source code has no fallback."""
    raw = environment.get("PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND", "")
    try:
        value = int(raw)
        attested_at_ms = int(
            environment.get("PWC_MODAL_EXECUTOR_RATE_ATTESTED_AT_MS", "")
        )
    except (TypeError, ValueError):
        raise FleetRunRefused(
            "explicit protected Modal rate evidence is required"
        ) from None
    if environment.get("PWC_RELEASE_ID") != expected_release:
        raise FleetRunRefused("protected Modal rate evidence release is inconsistent")
    if environment.get("PWC_MODAL_EXECUTOR_RATE_SOURCE_ID") != "modal-staging-price-v1":
        raise FleetRunRefused("protected Modal rate evidence source is inconsistent")
    if not (window_started_at_ms <= attested_at_ms <= window_ended_at_ms <= now_ms):
        raise FleetRunRefused("protected Modal rate evidence window is inconsistent")
    try:
        return ModalRateEvidence(
            microusd_per_second=value,
            source="protected_runtime",
            source_id=environment.get("PWC_MODAL_EXECUTOR_RATE_SOURCE_ID", ""),
            release_id=environment.get("PWC_RELEASE_ID", ""),
            attested_at_ms=attested_at_ms,
        )
    except ValueError:
        raise FleetRunRefused("protected Modal rate evidence is invalid") from None


class DurableServerLatencyP95(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_gateway_received_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    provider_ttft_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    first_semantic_event_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)


class DurableQualificationEvidence(BaseModel):
    """Exact cross-process records for one protected qualification cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_users: Literal[32, 100]
    admitted_turns: int = Field(ge=0, le=100)
    admission_denominator_events: int = Field(ge=0, le=100)
    terminal_turns: int = Field(ge=0, le=100)
    queued_states: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    stale_fences: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    executor_starts: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    duplicate_executor_starts: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    workspace_creates: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    workspace_reuses: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    workspace_evictions: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    billed_duration_ms: int = Field(ge=0, le=MAX_REPORT_BYTES)
    window_started_at_ms: int = Field(ge=1, le=MAX_REPORT_BYTES)
    window_ended_at_ms: int = Field(ge=1, le=MAX_REPORT_BYTES)
    p95_server_latency_ms_by_workload: dict[
        DurableWorkload, DurableServerLatencyP95
    ] = Field(default_factory=dict, max_length=3)
    source: Literal["durable_qualification_records"]

    @model_validator(mode="after")
    def validate_server_latency(self) -> DurableQualificationEvidence:
        expected = {"no_tool", "read", "bash"} if self.expected_users == 32 else set()
        if set(self.p95_server_latency_ms_by_workload) != expected:
            raise ValueError("durable server latency evidence is incomplete")
        return self


class DurableLatencyAttributionP95(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    client_admission_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    client_reconnect_ready_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    client_post_reconnect_to_ttft_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    server_provider_gateway_received_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    provider_ttft_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    server_first_semantic_event_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    end_to_end_ttft_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)


def modal_lifecycle_delta(
    before: ModalLifecycleSnapshot, after: ModalLifecycleSnapshot
) -> ModalLifecycleDelta:
    if after.captured_at_ms <= before.captured_at_ms or after.source != before.source:
        raise FleetRunRefused("Modal lifecycle window evidence is inconsistent")
    values = {
        "creates": after.creates - before.creates,
        "reuses": after.reuses - before.reuses,
        "evictions": after.evictions - before.evictions,
        "active_duration_ms": (after.active_duration_ms - before.active_duration_ms),
    }
    try:
        return ModalLifecycleDelta.model_validate(values)
    except ValueError:
        raise FleetRunRefused("Modal lifecycle counters are inconsistent") from None


class DurableProfileReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    profile: Literal["32-functional-turns", "100-immediate-admission"]
    qualification_evidence_source: Literal[
        "durable_qualification_records", "isolated_test_harness"
    ]
    expected_users: Literal[32, 100]
    observations: int = Field(ge=0, le=EXPECTED_USERS)
    completed: int = Field(ge=0, le=EXPECTED_USERS)
    refusals: int = Field(ge=0, le=EXPECTED_USERS)
    typed_failures: int = Field(ge=0, le=EXPECTED_USERS)
    queued_states: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    model_starts: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    operation_start_count: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    duplicate_model_starts: int = Field(ge=0, le=EXPECTED_USERS)
    duplicate_operation_start_count: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    duplicate_turns: int = Field(ge=0, le=EXPECTED_USERS)
    stale_mutations: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    terminal_outcomes: int = Field(ge=0, le=EXPECTED_USERS)
    terminal_cause_counts: dict[str, int] = Field(max_length=32)
    typed_failure_counts: dict[str, int] = Field(max_length=32)
    reconnects: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    reconnect_successes: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    ttft_observations: int = Field(ge=0, le=EXPECTED_USERS)
    completion_observations: int = Field(ge=0, le=EXPECTED_USERS)
    p95_ttft_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    p95_ttft_ms_by_workload: dict[DurableWorkload, int] = Field(max_length=4)
    p95_latency_attribution_ms_by_workload: dict[
        DurableWorkload, DurableLatencyAttributionP95
    ] = Field(default_factory=dict, max_length=3)
    p99_completion_ms: int = Field(ge=0, le=MAX_DURABLE_DURATION_MS)
    peak_memory_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    minimum_host_mem_available_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    peak_cpu_percent: float = Field(ge=0, le=100)
    peak_active_backend_turns: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    peak_active_external_workers: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    peak_active_sandboxes: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    modal_creates: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    modal_reuses: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    modal_evictions: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    modal_active_ms: int = Field(ge=0, le=MAX_REPORT_BYTES)
    modal_rate_microusd_per_second: int = Field(ge=1, le=MAX_REPORT_COUNTER)
    modal_rate_source: Literal["protected_runtime"]
    modal_rate_source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
    modal_rate_release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    modal_rate_attested_at_ms: int = Field(ge=1, le=MAX_REPORT_BYTES)
    modal_estimated_cost_microusd: int = Field(ge=0, le=MAX_REPORT_BYTES)

    @model_validator(mode="after")
    def validate_typed_counts(self) -> DurableProfileReport:
        for counts in (self.terminal_cause_counts, self.typed_failure_counts):
            if any(
                not re.fullmatch(r"[a-z0-9][a-z0-9_]{0,63}", code)
                or type(count) is not int
                or count < 1
                or count > MAX_REPORT_COUNTER
                for code, count in counts.items()
            ):
                raise ValueError("durable profile typed counts are invalid")
        expected_cost = math.ceil(
            self.modal_active_ms * self.modal_rate_microusd_per_second / 1000
        )
        if self.modal_estimated_cost_microusd != expected_cost:
            raise ValueError("durable profile Modal cost evidence is inconsistent")
        expected_workloads = set(resolve_durable_profile(self.profile).workloads)
        if set(self.p95_ttft_ms_by_workload) != expected_workloads or any(
            type(value) is not int or value < 0 or value > MAX_DURABLE_DURATION_MS
            for value in self.p95_ttft_ms_by_workload.values()
        ):
            raise ValueError("durable workload TTFT evidence is inconsistent")
        expected_attribution = (
            {"no_tool", "read", "bash"}
            if self.qualification_evidence_source == "durable_qualification_records"
            and self.profile == "32-functional-turns"
            else set()
        )
        if set(self.p95_latency_attribution_ms_by_workload) != expected_attribution:
            raise ValueError("durable latency attribution evidence is inconsistent")
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return (
            self.observations == self.expected_users
            and self.completed == self.expected_users
            and self.refusals == 0
            and self.typed_failures == 0
            and self.queued_states == 0
            and self.model_starts == self.expected_users
            and self.duplicate_model_starts == 0
            and self.duplicate_operation_start_count == 0
            and self.duplicate_turns == 0
            and self.stale_mutations == 0
            and self.terminal_outcomes == self.expected_users
            and self.terminal_cause_counts == {"completed": self.expected_users}
            and not self.typed_failure_counts
            and self.reconnects == self.reconnect_successes
            and self.ttft_observations == self.expected_users
            and self.completion_observations == self.expected_users
            and self.p95_ttft_ms < P95_TTFT_TARGET_MS
            and all(
                value < P95_TTFT_TARGET_MS
                for value in self.p95_ttft_ms_by_workload.values()
            )
            and self.p99_completion_ms <= 60_000
            and self.minimum_host_mem_available_bytes
            >= MIN_PROJECTED_MEM_AVAILABLE_BYTES
            and self.peak_cpu_percent < 80.0
            and self.peak_active_backend_turns == self.expected_users
            and self.peak_active_external_workers > 0
            and (
                (
                    self.profile == "32-functional-turns"
                    and self.modal_creates + self.modal_reuses == 16
                    and (
                        self.qualification_evidence_source == "isolated_test_harness"
                        or self.operation_start_count == 16
                    )
                    and self.modal_evictions
                    == (
                        0
                        if self.qualification_evidence_source == "isolated_test_harness"
                        else 16
                    )
                    and self.modal_active_ms > 0
                    and self.peak_active_sandboxes > 0
                )
                or (
                    self.profile == "100-immediate-admission"
                    and self.modal_creates == 0
                    and self.modal_reuses == 0
                    and self.modal_evictions == 0
                    and self.modal_active_ms == 0
                    and (
                        self.qualification_evidence_source == "isolated_test_harness"
                        or self.operation_start_count == 0
                    )
                    and self.peak_active_sandboxes == 0
                )
            )
        )


class DurableQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    status: Literal["completed", "resource_refused", "failed"]
    reason: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_]{0,63}$")
    profiles: tuple[DurableProfileReport, ...] = Field(max_length=1)
    max_spend_microusd: int = Field(default=0, ge=0, le=10_000_000)
    provider_spend_ceiling_microusd: int = Field(default=0, ge=0, le=10_000_000)
    flags_restored: bool
    exact_workers_drained: bool
    transient_workers_removed: bool
    listeners_gone: bool
    status_files_gone: bool
    processes_gone: bool
    final_active_backend_turns: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    final_active_external_workers: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    final_active_sandboxes: int = Field(ge=0, le=MAX_REPORT_COUNTER)

    @property
    def cleanup_passed(self) -> bool:
        return (
            self.flags_restored
            and self.exact_workers_drained
            and self.transient_workers_removed
            and self.listeners_gone
            and self.status_files_gone
            and self.processes_gone
            and self.final_active_backend_turns == 0
            and self.final_active_external_workers == 0
            and self.final_active_sandboxes == 0
        )

    @model_validator(mode="after")
    def validate_status_evidence(self) -> DurableQualificationReport:
        if self.provider_spend_ceiling_microusd > self.max_spend_microusd:
            raise ValueError("durable report spend evidence is inconsistent")
        names = tuple(item.profile for item in self.profiles)
        expected = ("32-functional-turns",)
        if names != expected[: len(names)] or any(
            item.modal_rate_release_id != self.release_id for item in self.profiles
        ):
            raise ValueError("durable report profiles are invalid")
        failed_profiles = sum(not item.passed for item in self.profiles)
        if self.status == "completed":
            if (
                self.reason is not None
                or names != expected
                or failed_profiles
                or not self.cleanup_passed
            ):
                raise ValueError(
                    "completed durable report requires an approved profile sequence and cleanup"
                )
        elif self.status == "resource_refused":
            if (
                self.reason not in {"memory_headroom", "cpu_headroom"}
                or len(names) > 1
                or not self.cleanup_passed
            ):
                raise ValueError("resource-refused durable report is inconsistent")
        else:
            if self.reason is None:
                raise ValueError("failed durable report requires a typed reason")
            failed_profile_limits = {
                "durable_qualification_failed": 0,
                "durable_profile_failed": 1,
                "cleanup_failed": 1,
                "staging_isolation_required": 0,
                "exact_staging_release_required": 0,
                "approved_16_gib_host_required": 0,
                "public_external_admission_flags_must_be_off": 0,
                "public_external_admission_flags_are_invalid": 0,
                "staging_prerequisite_missing": 0,
                "active_staging_worker_required": 0,
                "binding_profile_order_required": 0,
                "host_cpu_evidence_unavailable": 0,
                "host_memory_evidence_unavailable": 0,
                "process_memory_evidence_unavailable": 0,
                "protected_modal_rate_evidence_invalid": 0,
                "protected_staging_settings_invalid": 0,
                "public_external_admission_flags_drifted": 0,
                "qualification_run_id_invalid": 0,
                "qualification_scope_invalid": 0,
                "resource_preflight_invalid": 0,
                "resource_sampling_failed": 0,
                "resource_sampling_lifecycle_invalid": 0,
                "resource_sampling_stalled": 0,
                "spend_envelope_invalid": 0,
                "spend_envelope_exceeded": 0,
                "staging_database_required": 0,
                "staging_pi_openai_model_required": 0,
            }
            maximum_profiles = failed_profile_limits.get(self.reason or "")
            if maximum_profiles is None or len(names) > maximum_profiles:
                raise ValueError("failed durable report reason or profiles are invalid")
            if (
                self.reason == "durable_profile_failed"
                and names
                and failed_profiles != 1
            ) or (self.reason != "durable_profile_failed" and failed_profiles):
                raise ValueError(
                    "failed durable report profile evidence is inconsistent"
                )
            if (
                self.reason == "public_external_admission_flags_are_invalid"
                and self.flags_restored
            ):
                raise ValueError(
                    "failed durable report flag snapshot evidence is contradictory"
                )
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return (
            self.status == "completed"
            and self.reason is None
            and tuple(item.profile for item in self.profiles)
            == ("32-functional-turns",)
            and all(item.passed for item in self.profiles)
            and self.cleanup_passed
        )


_DURABLE_PROFILES = {
    "32-functional-turns": DurableQualificationProfile(
        name="32-functional-turns",
        expected_users=32,
        spawn_rate=32,
        workloads=("no_tool",) * 16 + ("read",) * 8 + ("bash",) * 8,
    ),
    "100-immediate-admission": DurableQualificationProfile(
        name="100-immediate-admission",
        expected_users=100,
        spawn_rate=100,
        workloads=("admission_stream",) * 100,
    ),
}


def resolve_durable_profile(name: str) -> DurableQualificationProfile:
    try:
        return _DURABLE_PROFILES[name]
    except KeyError:
        raise FleetRunRefused("durable qualification profile is invalid") from None


def aggregate_durable_profile(
    *,
    profile: DurableQualificationProfile,
    observations: tuple[DurableTurnObservation, ...],
    peak_memory_bytes: int,
    minimum_host_mem_available_bytes: int,
    peak_cpu_percent: float,
    peak_active_backend_turns: int,
    peak_active_external_workers: int,
    peak_active_sandboxes: int,
    modal_rate: ModalRateEvidence,
    modal_lifecycle: ModalLifecycleDelta | None = None,
    qualification_evidence: DurableQualificationEvidence | None = None,
) -> DurableProfileReport:
    expected = resolve_durable_profile(profile.name)
    if profile != expected or len(observations) != profile.expected_users:
        raise FleetRunRefused(
            "durable qualification requires exact profile observations"
        )
    ttft = tuple(item.ttft_ms for item in observations if item.ttft_ms is not None)
    expected_workloads = set(profile.workloads)
    if Counter(item.workload for item in observations) != Counter(profile.workloads):
        raise FleetRunRefused("durable qualification workload evidence is inconsistent")
    ttft_by_workload = {
        workload: tuple(
            item.ttft_ms
            for item in observations
            if item.workload == workload and item.ttft_ms is not None
        )
        for workload in expected_workloads
    }
    latency_attribution: dict[DurableWorkload, DurableLatencyAttributionP95] = {}
    if qualification_evidence is not None and profile.name == "32-functional-turns":
        if any(
            item.admission_ms is None
            or item.reconnect_ready_ms is None
            or item.ttft_ms is None
            for item in observations
        ):
            raise FleetRunRefused("durable client latency evidence is incomplete")
        for workload in sorted(expected_workloads):
            workload_rows = tuple(
                item for item in observations if item.workload == workload
            )
            server = qualification_evidence.p95_server_latency_ms_by_workload[workload]
            latency_attribution[workload] = DurableLatencyAttributionP95(
                client_admission_ms=_nearest_rank(
                    tuple(cast(int, item.admission_ms) for item in workload_rows),
                    0.95,
                ),
                client_reconnect_ready_ms=_nearest_rank(
                    tuple(cast(int, item.reconnect_ready_ms) for item in workload_rows),
                    0.95,
                ),
                client_post_reconnect_to_ttft_ms=_nearest_rank(
                    tuple(
                        cast(int, item.ttft_ms) - cast(int, item.reconnect_ready_ms)
                        for item in workload_rows
                    ),
                    0.95,
                ),
                server_provider_gateway_received_ms=(
                    server.provider_gateway_received_ms
                ),
                provider_ttft_ms=server.provider_ttft_ms,
                server_first_semantic_event_ms=server.first_semantic_event_ms,
                end_to_end_ttft_ms=_nearest_rank(
                    tuple(cast(int, item.ttft_ms) for item in workload_rows), 0.95
                ),
            )
    completion = tuple(
        item.completion_ms for item in observations if item.completion_ms is not None
    )
    terminal_cause_counts = Counter(item.terminal_cause for item in observations)
    typed_failure_counts = Counter(
        item.failure_code for item in observations if item.failure_code is not None
    )
    if qualification_evidence is not None:
        if (
            qualification_evidence.expected_users != profile.expected_users
            or qualification_evidence.admitted_turns != profile.expected_users
            or qualification_evidence.admission_denominator_events
            != profile.expected_users
            or qualification_evidence.terminal_turns != profile.expected_users
        ):
            raise FleetRunRefused("durable qualification evidence is incomplete")
        queued_states = qualification_evidence.queued_states
        stale_mutations = qualification_evidence.stale_fences
        operation_start_count = qualification_evidence.executor_starts
        duplicate_operation_start_count = (
            qualification_evidence.duplicate_executor_starts
        )
        modal_creates = qualification_evidence.workspace_creates
        modal_reuses = qualification_evidence.workspace_reuses
        modal_evictions = qualification_evidence.workspace_evictions
        modal_active_ms = qualification_evidence.billed_duration_ms
    elif modal_lifecycle is not None:
        # Retained solely for isolated, non-live unit harnesses.
        queued_states = sum(item.queued_states for item in observations)
        stale_mutations = sum(item.stale_mutations for item in observations)
        operation_start_count = sum(item.operation_start_count for item in observations)
        duplicate_operation_start_count = sum(
            item.duplicate_operation_start_count for item in observations
        )
        modal_creates = modal_lifecycle.creates
        modal_reuses = modal_lifecycle.reuses
        modal_evictions = modal_lifecycle.evictions
        modal_active_ms = modal_lifecycle.active_duration_ms
    else:
        raise FleetRunRefused("durable qualification evidence is required")
    return DurableProfileReport(
        profile=profile.name,
        qualification_evidence_source=(
            "durable_qualification_records"
            if qualification_evidence is not None
            else "isolated_test_harness"
        ),
        expected_users=profile.expected_users,
        observations=len(observations),
        completed=sum(item.outcome == "completed" for item in observations),
        refusals=sum(item.outcome == "refused" for item in observations),
        typed_failures=sum(
            item.outcome == "failed" or item.failure_code is not None
            for item in observations
        ),
        queued_states=queued_states,
        model_starts=sum(item.model_starts for item in observations),
        operation_start_count=operation_start_count,
        duplicate_model_starts=sum(item.model_starts > 1 for item in observations),
        duplicate_operation_start_count=duplicate_operation_start_count,
        duplicate_turns=sum(item.duplicate_turns for item in observations),
        stale_mutations=stale_mutations,
        terminal_outcomes=sum(
            item.terminal_cause == item.outcome for item in observations
        ),
        terminal_cause_counts=dict(sorted(terminal_cause_counts.items())),
        typed_failure_counts=dict(sorted(typed_failure_counts.items())),
        reconnects=sum(item.reconnects for item in observations),
        reconnect_successes=sum(item.reconnect_successes for item in observations),
        ttft_observations=len(ttft),
        completion_observations=len(completion),
        p95_ttft_ms=_nearest_rank(ttft, 0.95),
        p95_ttft_ms_by_workload={
            workload: _nearest_rank(values, 0.95)
            for workload, values in sorted(ttft_by_workload.items())
        },
        p95_latency_attribution_ms_by_workload=latency_attribution,
        p99_completion_ms=_nearest_rank(completion, 0.99),
        peak_memory_bytes=peak_memory_bytes,
        minimum_host_mem_available_bytes=minimum_host_mem_available_bytes,
        peak_cpu_percent=peak_cpu_percent,
        peak_active_backend_turns=peak_active_backend_turns,
        peak_active_external_workers=peak_active_external_workers,
        peak_active_sandboxes=peak_active_sandboxes,
        modal_creates=modal_creates,
        modal_reuses=modal_reuses,
        modal_evictions=modal_evictions,
        modal_active_ms=modal_active_ms,
        modal_rate_microusd_per_second=modal_rate.microusd_per_second,
        modal_rate_source=modal_rate.source,
        modal_rate_source_id=modal_rate.source_id,
        modal_rate_release_id=modal_rate.release_id,
        modal_rate_attested_at_ms=modal_rate.attested_at_ms,
        modal_estimated_cost_microusd=math.ceil(
            modal_active_ms * modal_rate.microusd_per_second / 1000
        ),
    )


_STAGING_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")


@dataclass(frozen=True, slots=True)
class FleetSafetyConfig:
    environment: str
    requested_release: str
    active_release: str
    external_admission_enabled: bool
    executor_routing_enabled: bool
    remote_execution_enabled: bool
    active_worker_id: str
    active_worker_healthy: bool
    worker_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PortState:
    port: int
    bind_host: str
    is_free: bool


@dataclass(frozen=True, slots=True)
class HostResourceSnapshot:
    mem_available_bytes: int
    projected_additional_bytes: int
    cpu_percent: float
    cpu_guard_percent: float

    def __post_init__(self) -> None:
        if (
            type(self.mem_available_bytes) is not int
            or self.mem_available_bytes < 0
            or self.mem_available_bytes > MAX_REPORT_BYTES
            or type(self.projected_additional_bytes) is not int
            or self.projected_additional_bytes < 0
            or self.projected_additional_bytes > MAX_REPORT_BYTES
            or not 0 <= self.cpu_percent <= 100
            or not 0 < self.cpu_guard_percent <= 100
        ):
            raise ValueError("external Pi qualification resource inputs are invalid")


@dataclass(frozen=True, slots=True)
class ResourcePreflight:
    status: Literal["passed", "resource_refused"]
    projected_mem_available_bytes: int
    observed_cpu_percent: float
    cpu_guard_percent: float

    def __post_init__(self) -> None:
        if (
            self.status not in {"passed", "resource_refused"}
            or type(self.projected_mem_available_bytes) is not int
            or self.projected_mem_available_bytes < 0
            or self.projected_mem_available_bytes > MAX_REPORT_BYTES
            or not 0 <= self.observed_cpu_percent <= 100
            or not 0 < self.cpu_guard_percent <= 100
        ):
            raise ValueError(
                "external Pi qualification resource preflight evidence is invalid"
            )


class ForbiddenActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    tool_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    provider_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    modal_calls: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)
    billing_events: int = Field(default=0, ge=0, le=MAX_REPORT_COUNTER)

    @property
    def detected(self) -> bool:
        return any(self.model_dump().values())


class FleetRoundReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: Literal["healthy", "survivor"]
    expected_users: int = Field(ge=1, le=EXPECTED_USERS)
    observations: int = Field(ge=0, le=EXPECTED_USERS)
    compatible: int = Field(ge=0, le=EXPECTED_USERS)
    capacity_rejections: int = Field(ge=0, le=EXPECTED_USERS)
    protocol_errors: int = Field(ge=0, le=EXPECTED_USERS)
    transport_errors: int = Field(ge=0, le=EXPECTED_USERS)
    p95_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    p99_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    forbidden_activity: ForbiddenActivity

    @model_validator(mode="after")
    def validate_counts(self) -> FleetRoundReport:
        outcomes = (
            self.compatible
            + self.capacity_rejections
            + self.protocol_errors
            + self.transport_errors
        )
        if self.observations != outcomes:
            raise ValueError("external Pi fleet round counts are inconsistent")
        if self.p95_ms > self.p99_ms:
            raise ValueError("external Pi fleet round percentiles are inconsistent")
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return (
            self.observations == self.expected_users
            and self.compatible == self.expected_users
            and self.capacity_rejections == 0
            and self.protocol_errors == 0
            and self.transport_errors == 0
            and not self.forbidden_activity.detected
            and self.p95_ms <= 3_000
            and self.p99_ms <= 5_000
        )


class WorkerEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    worker_id: str = Field(pattern=r"^staging-qualification-(0[0-9]|1[0-5])$")
    port: int = Field(ge=8780, le=8795)
    generation: int = Field(ge=1, le=MAX_REPORT_COUNTER)
    maximum_sessions: Literal[8, 16, 32]


class UnitResourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    unit_name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9@_.-]+\.service$",
    )
    peak_memory_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    peak_cpu_percent: float = Field(ge=0, le=100)
    peak_tasks: int = Field(ge=0, le=MAX_REPORT_COUNTER)


class ResourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    peak_memory_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    peak_cpu_percent: float = Field(ge=0, le=100)
    peak_tasks: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    minimum_host_mem_available_bytes: int = Field(ge=0, le=MAX_REPORT_BYTES)
    unit_peaks: tuple[UnitResourceEvidence, ...] = Field(max_length=32)


class CleanupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    drain_proven: bool
    registry_offline: bool
    supervisors_stopped_before_workers: bool
    units_removed: bool
    status_files_removed: bool
    ports_free: bool
    processes_gone: bool

    @property
    def passed(self) -> bool:
        return all(self.model_dump().values())


class FleetShapeReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    shape: FleetShapeName
    status: Literal["completed", "resource_refused"]
    worker_count: int = Field(ge=2, le=16)
    sessions_per_worker: Literal[8, 16, 32]
    expected_users: int = Field(ge=1, le=EXPECTED_USERS)
    aggregate_capacity: int = Field(ge=0, le=160)
    post_loss_capacity: int = Field(ge=0, le=160)
    healthy: FleetRoundReport | None
    survivor: FleetRoundReport | None
    workers: tuple[WorkerEvidence, ...] = Field(max_length=16)
    removed_worker_id: str | None = Field(
        pattern=r"^staging-qualification-(0[0-9]|1[0-5])$"
    )
    resources: ResourceEvidence | None
    resource_preflight: ResourcePreflight | None
    cleanup: CleanupEvidence

    @computed_field
    @property
    def safety_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.healthy is not None
            and self.survivor is not None
            and self.healthy.passed
            and self.survivor.passed
        )

    @computed_field
    @property
    def capacity_passed(self) -> bool:
        return self.aggregate_capacity >= self.expected_users

    @computed_field
    @property
    def failure_resilience_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.survivor is not None
            and self.post_loss_capacity >= self.expected_users
            and self.survivor.passed
        )

    @computed_field
    @property
    def resource_passed(self) -> bool:
        return (
            self.status == "completed"
            and self.resources is not None
            and self.resource_preflight is not None
            and self.resource_preflight.status == "passed"
        )

    @computed_field
    @property
    def cleanup_passed(self) -> bool:
        return self.cleanup.passed

    @computed_field
    @property
    def overall_passed(self) -> bool:
        return (
            self.safety_passed
            and self.capacity_passed
            and self.failure_resilience_passed
            and self.resource_passed
            and self.cleanup_passed
        )


class FleetQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    runtime_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    shapes: tuple[FleetShapeReport, ...] = Field(min_length=1, max_length=3)
    preferred_shape: FleetShapeName | None


class RecoveryReplicaEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    worker_id: str = Field(pattern=r"^staging-qualification-(0[0-9]|1[0-5])$")
    port: int = Field(ge=8780, le=8795)
    generation: int | None = Field(default=None, ge=1, le=MAX_REPORT_COUNTER)
    supervisor_unit: str = Field(min_length=1, max_length=128)
    worker_unit: str = Field(min_length=1, max_length=128)
    owned_units: tuple[str, ...] = Field(max_length=2)
    cleanup: CleanupEvidence
    unresolved_units: tuple[str, ...] = Field(max_length=2)

    @model_validator(mode="after")
    def validate_exact_replica(self) -> RecoveryReplicaEvidence:
        index = QUALIFICATION_WORKER_IDS.index(self.worker_id)
        expected = (
            QUALIFICATION_SUPERVISOR_UNITS[index],
            QUALIFICATION_WORKER_UNITS[index],
        )
        if (
            self.port != QUALIFICATION_PORTS[index]
            or (self.supervisor_unit, self.worker_unit) != expected
            or len(set(self.owned_units)) != len(self.owned_units)
            or any(unit not in expected for unit in self.owned_units)
            or len(set(self.unresolved_units)) != len(self.unresolved_units)
            or any(unit not in expected for unit in self.unresolved_units)
        ):
            raise ValueError("external Pi fleet recovery replica is not exact")
        return self


class FleetRecoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    report_type: Literal["recovery"] = "recovery"
    attempt_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    attempted_at_unix_ms: int = Field(ge=1, le=MAX_REPORT_BYTES)
    release_id: str = Field(pattern=r"^[0-9a-f]{12}-staging$")
    runtime_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    owner_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    failure_stage: FleetFailureStage
    failure_code: FleetFailureCode
    replicas: tuple[RecoveryReplicaEvidence, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def validate_unique_replicas(self) -> FleetRecoveryReport:
        worker_ids = tuple(item.worker_id for item in self.replicas)
        if len(set(worker_ids)) != len(worker_ids):
            raise ValueError("external Pi fleet recovery replicas are duplicated")
        valid_failure_pairs = {
            ("revalidation", "revalidation_failed"),
            ("resource_sampling", "resource_sampling_failed"),
            ("resource_sampling", "resource_sampler_stalled"),
            ("resource_threshold", "resource_threshold_crossed"),
            ("worker_status", "worker_status_failed"),
            ("locust_round", "locust_round_failed"),
            ("counter", "counter_mismatch"),
            ("replica_lifecycle", "replica_lifecycle_failed"),
            ("cleanup", "cleanup_failed"),
        }
        if (self.failure_stage, self.failure_code) not in valid_failure_pairs:
            raise ValueError(
                "external Pi fleet recovery failure reason is inconsistent"
            )
        return self

    @computed_field
    @property
    def cleanup_complete(self) -> bool:
        return all(
            item.cleanup.passed and not item.unresolved_units for item in self.replicas
        )


@dataclass(frozen=True, slots=True)
class FleetReplica:
    worker_id: str
    port: int

    @property
    def worker_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@dataclass(frozen=True, slots=True)
class FleetShape:
    name: FleetShapeName
    worker_count: int
    sessions_per_worker: int
    expected_users: int
    replicas: tuple[FleetReplica, ...]

    @property
    def aggregate_capacity(self) -> int:
        return self.worker_count * self.sessions_per_worker

    @property
    def post_loss_capacity(self) -> int:
        return (self.worker_count - 1) * self.sessions_per_worker


def _shape(
    name: FleetShapeName, worker_count: int, sessions: int, expected_users: int
) -> FleetShape:
    return FleetShape(
        name=name,
        worker_count=worker_count,
        sessions_per_worker=sessions,
        expected_users=expected_users,
        replicas=tuple(
            FleetReplica(QUALIFICATION_WORKER_IDS[index], QUALIFICATION_PORTS[index])
            for index in range(worker_count)
        ),
    )


_FLEET_SHAPES: dict[FleetShapeName, FleetShape] = {
    cast(FleetShapeName, f"{worker_count}x{sessions}"): _shape(
        cast(FleetShapeName, f"{worker_count}x{sessions}"),
        worker_count,
        sessions,
        expected_users,
    )
    for worker_count, sessions, expected_users in (
        tuple(
            (workers, sessions, EXPECTED_USERS)
            for workers, sessions in QUALIFICATION_SHAPES
        )
        + CAPACITY_QUALIFICATION_SHAPES
    )
}


def resolve_fleet_shape(name: str) -> FleetShape:
    try:
        return _FLEET_SHAPES[name]
    except KeyError:
        raise FleetRunRefused(
            "external Pi qualification requires an allowlisted fleet shape"
        ) from None


def route_ordinal(
    ordinal: int,
    replicas: tuple[FleetReplica, ...],
    expected_users: int = EXPECTED_USERS,
) -> FleetReplica:
    if (
        type(expected_users) is not int
        or not 1 <= expected_users <= EXPECTED_USERS
        or type(ordinal) is not int
        or not 0 <= ordinal < expected_users
    ):
        raise ValueError("external Pi qualification ordinal is out of range")
    if not replicas:
        raise FleetRunRefused("external Pi qualification requires at least one replica")
    allowed_pairs = {
        worker_id: QUALIFICATION_PORTS[index]
        for index, worker_id in enumerate(QUALIFICATION_WORKER_IDS)
    }
    indices = [
        QUALIFICATION_WORKER_IDS.index(replica.worker_id)
        for replica in replicas
        if replica.worker_id in allowed_pairs
    ]
    if (
        len(indices) != len(replicas)
        or len(set(indices)) != len(indices)
        or indices != sorted(indices)
        or any(
            allowed_pairs.get(replica.worker_id) != replica.port for replica in replicas
        )
    ):
        raise FleetRunRefused(
            "external Pi qualification routing requires allowlisted replicas"
        )
    return replicas[ordinal % len(replicas)]


def validate_fleet_preflight(
    config: FleetSafetyConfig,
    shape: FleetShape,
    ports: tuple[PortState, ...],
) -> None:
    """Validate pure staging, release, disabled-route, and port safety gates."""

    shape = _require_allowlisted_shape(shape)
    if config.environment != "staging":
        raise FleetRunRefused("external Pi qualification is staging only")
    if (
        config.requested_release != config.active_release
        or not _STAGING_RELEASE.fullmatch(config.active_release)
    ):
        raise FleetRunRefused(
            "external Pi qualification requires the exact active staging release"
        )
    flags = (
        config.external_admission_enabled,
        config.executor_routing_enabled,
        config.remote_execution_enabled,
    )
    if any(type(flag) is not bool or flag for flag in flags):
        raise FleetRunRefused(
            "external Pi qualification routing flags must remain disabled"
        )
    if (
        config.active_worker_id not in {"staging-blue", "staging-green"}
        or type(config.active_worker_healthy) is not bool
        or not config.active_worker_healthy
    ):
        raise FleetRunRefused(
            "external Pi qualification requires the healthy active staging worker"
        )
    if not config.worker_token:
        raise FleetRunRefused(
            "external Pi qualification requires a protected worker token"
        )

    expected_ports = tuple(replica.port for replica in shape.replicas)
    if (
        len(ports) != len(expected_ports)
        or tuple(item.port for item in ports) != expected_ports
        or any(
            item.bind_host != "127.0.0.1"
            or type(item.is_free) is not bool
            or not item.is_free
            for item in ports
        )
    ):
        raise FleetRunRefused(
            "external Pi qualification requires exact free loopback ports"
        )


def evaluate_resource_preflight(snapshot: HostResourceSnapshot) -> ResourcePreflight:
    projected = max(
        0, snapshot.mem_available_bytes - snapshot.projected_additional_bytes
    )
    passed = (
        snapshot.mem_available_bytes >= snapshot.projected_additional_bytes
        and projected >= MIN_PROJECTED_MEM_AVAILABLE_BYTES
        and snapshot.cpu_percent < snapshot.cpu_guard_percent
    )
    return ResourcePreflight(
        status="passed" if passed else "resource_refused",
        projected_mem_available_bytes=projected,
        observed_cpu_percent=snapshot.cpu_percent,
        cpu_guard_percent=snapshot.cpu_guard_percent,
    )


# The fleet deliberately shares the proven content-free payload and classifier.
build_external_pi_fleet_request = build_external_pi_baseline_request
classify_external_pi_fleet_response = classify_external_pi_baseline_response


def _nearest_rank(values: tuple[int, ...], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def aggregate_round(
    *,
    name: Literal["healthy", "survivor"],
    expected_users: int = EXPECTED_USERS,
    observations: tuple[BaselineObservation, ...],
    protocol_errors: int,
    transport_errors: int,
    forbidden_activity: ForbiddenActivity,
) -> FleetRoundReport:
    """Reduce one fixed 100-user round to bounded content-free counters."""

    if (
        type(expected_users) is not int
        or not 1 <= expected_users <= EXPECTED_USERS
        or len(observations) != expected_users
    ):
        raise FleetRunRefused(
            "external Pi fleet round requires its exact expected observations"
        )
    if (
        type(protocol_errors) is not int
        or type(transport_errors) is not int
        or protocol_errors < 0
        or transport_errors < 0
    ):
        raise FleetRunRefused("external Pi fleet round error counters are invalid")
    compatible = sum(item.classification == "compatible" for item in observations)
    capacity = sum(item.classification == "capacity" for item in observations)
    classified_errors = sum(item.classification == "error" for item in observations)
    if protocol_errors + transport_errors != classified_errors:
        raise FleetRunRefused("external Pi fleet round error evidence is inconsistent")
    latencies = tuple(item.latency_ms for item in observations)
    p95 = _nearest_rank(latencies, 0.95)
    p99 = _nearest_rank(latencies, 0.99)
    return FleetRoundReport(
        name=name,
        expected_users=expected_users,
        observations=len(observations),
        compatible=compatible,
        capacity_rejections=capacity,
        protocol_errors=protocol_errors,
        transport_errors=transport_errors,
        p95_ms=p95,
        p99_ms=p99,
        forbidden_activity=forbidden_activity,
    )


def _require_allowlisted_shape(shape: FleetShape) -> FleetShape:
    expected = resolve_fleet_shape(shape.name)
    if shape != expected:
        raise FleetRunRefused(
            "external Pi qualification requires an allowlisted fleet shape"
        )
    return expected


def qualification_unit_names(shape: FleetShape) -> tuple[str, ...]:
    """Return every exact transient supervisor and worker unit for a shape."""

    shape = _require_allowlisted_shape(shape)
    return (
        QUALIFICATION_SUPERVISOR_UNITS[: shape.worker_count]
        + QUALIFICATION_WORKER_UNITS[: shape.worker_count]
    )


def build_completed_shape_report(
    *,
    shape: FleetShape,
    healthy: FleetRoundReport,
    survivor: FleetRoundReport,
    workers: tuple[WorkerEvidence, ...],
    removed_worker_id: str,
    resources: ResourceEvidence,
    resource_preflight: ResourcePreflight,
    cleanup: CleanupEvidence,
) -> FleetShapeReport:
    shape = _require_allowlisted_shape(shape)
    expected_worker_ids = tuple(replica.worker_id for replica in shape.replicas)
    if (
        healthy.name != "healthy"
        or survivor.name != "survivor"
        or healthy.expected_users != shape.expected_users
        or survivor.expected_users != shape.expected_users
        or tuple(worker.worker_id for worker in workers) != expected_worker_ids
        or tuple(worker.port for worker in workers)
        != tuple(replica.port for replica in shape.replicas)
        or any(
            worker.maximum_sessions != shape.sessions_per_worker for worker in workers
        )
        or removed_worker_id not in expected_worker_ids
    ):
        raise FleetRunRefused(
            "external Pi fleet shape evidence does not match its topology"
        )
    if resource_preflight.status != "passed":
        raise FleetRunRefused(
            "external Pi completed shape requires a passed resource preflight"
        )
    if tuple(item.unit_name for item in resources.unit_peaks) != (
        qualification_unit_names(shape)
    ):
        raise FleetRunRefused(
            "external Pi shape requires exact per-unit resource evidence"
        )
    return FleetShapeReport(
        shape=shape.name,
        status="completed",
        worker_count=shape.worker_count,
        sessions_per_worker=shape.sessions_per_worker,
        expected_users=shape.expected_users,
        aggregate_capacity=shape.aggregate_capacity,
        post_loss_capacity=shape.post_loss_capacity,
        healthy=healthy,
        survivor=survivor,
        workers=workers,
        removed_worker_id=removed_worker_id,
        resources=resources,
        resource_preflight=resource_preflight,
        cleanup=cleanup,
    )


def build_resource_refused_shape_report(
    shape: FleetShape,
    preflight: ResourcePreflight,
    cleanup: CleanupEvidence,
) -> FleetShapeReport:
    shape = _require_allowlisted_shape(shape)
    if preflight.status != "resource_refused":
        raise FleetRunRefused(
            "external Pi shape may be refused only by resource preflight"
        )
    return FleetShapeReport(
        shape=shape.name,
        status="resource_refused",
        worker_count=shape.worker_count,
        sessions_per_worker=shape.sessions_per_worker,
        expected_users=shape.expected_users,
        aggregate_capacity=shape.aggregate_capacity,
        post_loss_capacity=shape.post_loss_capacity,
        healthy=None,
        survivor=None,
        workers=(),
        removed_worker_id=None,
        resources=None,
        resource_preflight=preflight,
        cleanup=cleanup,
    )


def _shape_evidence(report: FleetShapeReport) -> dict[str, object]:
    return report.model_dump(exclude_computed_fields=True)


def _revalidate_shape_report(report: FleetShapeReport) -> FleetShapeReport:
    """Rebuild a shape verdict exclusively from its bounded source evidence."""

    try:
        shape = resolve_fleet_shape(report.shape)
        if report.status == "completed":
            if (
                report.healthy is None
                or report.survivor is None
                or report.resources is None
                or report.resource_preflight is None
                or report.removed_worker_id is None
            ):
                raise FleetRunRefused(
                    "external Pi completed shape report evidence is incomplete"
                )
            healthy = FleetRoundReport.model_validate(
                report.healthy.model_dump(exclude_computed_fields=True)
            )
            survivor = FleetRoundReport.model_validate(
                report.survivor.model_dump(exclude_computed_fields=True)
            )
            rebuilt = build_completed_shape_report(
                shape=shape,
                healthy=healthy,
                survivor=survivor,
                workers=report.workers,
                removed_worker_id=report.removed_worker_id,
                resources=report.resources,
                resource_preflight=report.resource_preflight,
                cleanup=report.cleanup,
            )
        else:
            if report.resource_preflight is None:
                raise FleetRunRefused(
                    "external Pi refused shape report evidence is incomplete"
                )
            rebuilt = build_resource_refused_shape_report(
                shape, report.resource_preflight, report.cleanup
            )
    except (AttributeError, TypeError, ValueError) as exc:
        raise FleetRunRefused("external Pi shape report evidence is invalid") from exc
    if _shape_evidence(report) != _shape_evidence(rebuilt):
        raise FleetRunRefused("external Pi shape report evidence is contradictory")
    return rebuilt


def build_final_report(
    *,
    release_id: str,
    runtime_id: str,
    shapes: tuple[FleetShapeReport, ...],
) -> FleetQualificationReport:
    validated_shapes = tuple(_revalidate_shape_report(report) for report in shapes)
    names = tuple(report.shape for report in validated_shapes)
    if len(set(names)) != len(names):
        raise FleetRunRefused("external Pi final report requires unique fleet shapes")
    passing = [report for report in validated_shapes if report.overall_passed]
    passing.sort(
        key=lambda report: (
            report.resources.peak_memory_bytes
            if report.resources
            else MAX_REPORT_BYTES,
            report.resources.peak_cpu_percent if report.resources else 101.0,
            max(report.healthy.p99_ms, report.survivor.p99_ms)
            if report.healthy and report.survivor
            else MAX_REPORT_DURATION_MS + 1,
            report.worker_count,
        )
    )
    return FleetQualificationReport(
        release_id=release_id,
        runtime_id=runtime_id,
        shapes=validated_shapes,
        preferred_shape=passing[0].shape if passing else None,
    )


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def publish_fleet_report(
    report: FleetQualificationReport | FleetRecoveryReport | DurableQualificationReport,
    destination: Path,
    report_root: Path,
) -> None:
    """Atomically publish only the bounded report schema with mode 0600."""

    try:
        root = report_root.resolve(strict=True)
        parent = destination.parent.resolve(strict=True)
    except OSError as exc:
        raise FleetRunRefused(
            "external Pi fleet report directory is unavailable"
        ) from exc
    if not destination.is_absolute() or not _path_within(parent, root):
        raise FleetRunRefused(
            "external Pi fleet report must remain under its report root"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        payload = report.model_dump_json(indent=2).encode("utf-8") + b"\n"
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def publish_durable_report(
    report: DurableQualificationReport, destination: Path, report_root: Path
) -> None:
    """Publish only validated content-free durable qualification evidence."""
    validated = DurableQualificationReport.model_validate(
        report.model_dump(exclude_computed_fields=True)
    )
    publish_fleet_report(validated, destination, report_root)
