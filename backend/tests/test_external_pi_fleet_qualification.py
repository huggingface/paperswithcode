from __future__ import annotations

import importlib
import importlib.util
import json
import math
import signal
import subprocess
import threading
import time
import uuid
from collections import Counter
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    MIN_PROJECTED_MEM_AVAILABLE_BYTES,
    CleanupEvidence,
    FleetReplica,
    FleetRoundReport,
    FleetRunRefused,
    FleetSafetyConfig,
    FleetShape,
    ForbiddenActivity,
    HostResourceSnapshot,
    PortState,
    ResourceEvidence,
    ResourcePreflight,
    UnitResourceEvidence,
    WorkerEvidence,
    aggregate_round,
    build_completed_shape_report,
    build_external_pi_fleet_request,
    build_final_report,
    build_resource_refused_shape_report,
    classify_external_pi_fleet_response,
    evaluate_resource_preflight,
    publish_fleet_report,
    qualification_unit_names,
    resolve_fleet_shape,
    route_ordinal,
    validate_fleet_preflight,
    aggregate_durable_profile,
    resolve_durable_profile,
    DurableTurnObservation,
    DurableQualificationReport,
    publish_durable_report,
    ModalLifecycleDelta,
    ModalLifecycleSnapshot,
    ModalRateEvidence,
    DurableQualificationEvidence,
    PERSISTENT_TRANSPORT_SCENARIOS,
    build_persistent_transport_user_specs,
    validate_persistent_transport_manifest,
    validate_persistent_transport_report,
)
from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
)
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_PORTS,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
    QUALIFICATION_WORKER_UNITS,
)

_NO_MODAL = ModalLifecycleDelta(creates=0, reuses=0, evictions=0, active_duration_ms=0)
_FUNCTIONAL_MODAL = ModalLifecycleDelta(
    creates=1, reuses=15, evictions=0, active_duration_ms=16_000
)
_MODAL_RATE = ModalRateEvidence(
    microusd_per_second=25,
    source="protected_runtime",
    source_id="modal-staging-price-v1",
    release_id="0123456789ab-staging",
    attested_at_ms=1,
)
_SERVER_LATENCY_P95 = {
    "no_tool": {
        "provider_gateway_received_ms": 300,
        "provider_ttft_ms": 400,
        "first_semantic_event_ms": 500,
    },
    "read": {
        "provider_gateway_received_ms": 310,
        "provider_ttft_ms": 410,
        "first_semantic_event_ms": 510,
    },
    "bash": {
        "provider_gateway_received_ms": 320,
        "provider_ttft_ms": 420,
        "first_semantic_event_ms": 520,
    },
}


def _persistent_transport_manifest() -> dict[str, object]:
    return {
        "schema_version": "persistent-executor-release-qualification-v1",
        "status": "release_qualification",
        "attempt_id": "a" * 64,
        "source_commit": "b" * 40,
        "preliminary_report_sha256": "c" * 64,
        "signed_component_manifest_sha256": "d" * 64,
        "modal_image_digest": "e" * 64,
        "modal_region": "eu-west",
        "chaos_declared": False,
        "percentile_method": "nearest_rank",
        "scenarios": list(PERSISTENT_TRANSPORT_SCENARIOS),
        "concurrent_turns": 32,
        "operations_per_turn": 4,
        "concurrent_operations": 128,
        "offered_turns": 64,
        "overload_rejections": 32,
        "loaded_clients": 1000,
        "minimum_soak_turns": 320,
        "minimum_soak_minutes": 60,
        "reconnect_ready_p99_ms_max": 5000,
        "authentication_starts_per_second_max": 250,
        "route_health_ms_max": 5000,
        "breaker_open_failures": 3,
        "breaker_failure_window_seconds": 60,
        "breaker_open_seconds": 30,
        "breaker_close_successes": 3,
        "drain_seconds_max": 240,
        "alert_ack_ms_max": 60000,
        "heartbeat_checkpoint_updates_per_second_max": 34,
        "public_operation_output_bytes_max": 24576,
        "public_turn_output_bytes_max": 98304,
        "operation_unacked_bytes_max": 65536,
        "stream_unacked_bytes_max": 262144,
        "connection_unacked_bytes_max": 524288,
        "command_bytes_max": 65536,
        "path_bytes_max": 4096,
        "bash_timeout_ms_max": 30000,
        "remote_read_bytes_max": 1048576,
        "preauth_frame_bytes_max": 2048,
        "preauth_deadline_ms_max": 2000,
        "invalid_per_source_rate": 10,
        "invalid_per_source_burst": 20,
        "invalid_per_shard_rate": 100,
        "invalid_per_shard_burst": 200,
        "host_cpu_percent_exclusive_max": 80,
        "host_mem_available_mib_min": 1536,
        "total_spend_microusd_max": 16250000,
        "provider_call_max": 0,
        "retain_unknown_spend_reservation": True,
        "stop_on_first_failed_gate": True,
    }


def test_persistent_transport_profile_freezes_all_release_gates():
    manifest = validate_persistent_transport_manifest(_persistent_transport_manifest())
    specs = build_persistent_transport_user_specs()

    assert manifest.status == "release_qualification"
    assert len(specs) == 32
    assert sum(spec.operation_limit for spec in specs) == 128
    assert {spec.workload for spec in specs} == {
        "cold_pwd",
        "warm_commands",
        "parallel_catalog",
        "disconnect_resume",
    }


@pytest.mark.parametrize(
    "missing",
    [
        "preliminary_report_sha256",
        "modal_region",
        "minimum_soak_turns",
        "total_spend_microusd_max",
        "operation_unacked_bytes_max",
    ],
)
def test_persistent_transport_profile_rejects_missing_evidence(missing):
    payload = _persistent_transport_manifest()
    payload.pop(missing)

    with pytest.raises(ValidationError):
        validate_persistent_transport_manifest(payload)


def test_persistent_transport_profile_cannot_weaken_a_frozen_kpi():
    payload = _persistent_transport_manifest()
    payload["concurrent_turns"] = 31

    with pytest.raises(ValidationError):
        validate_persistent_transport_manifest(payload)


def _persistent_transport_report() -> dict[str, object]:
    cohort = {
        "offered": 32,
        "admitted": 32,
        "completed": 32,
        "rejected_pre_work": 0,
        "failed": 0,
        "candidate_denominator": 32,
        "failure_attribution": {},
    }
    return {
        "schema_version": "persistent-executor-release-report-v1",
        "qualification_kind": "release",
        "status": "passed",
        "attempt_id": "a" * 64,
        "manifest_sha256": "b" * 64,
        "modal_region": "eu-west",
        "pool_counts_by_digest": {
            "c" * 64: {
                "active": 32,
                "assigned_idle": 0,
                "blank": 0,
                "draining": 0,
                "terminated": 0,
            }
        },
        "cohorts": [
            {"transport": "persistent", **cohort},
            {"transport": "legacy", **cohort},
        ],
        "percentiles": {
            "reconnect_ready": {
                "denominator": 1000,
                "accepted": 1000,
                "p50_ms": 100,
                "p95_ms": 500,
                "p99_ms": 1000,
            }
        },
        "resources": {
            "peak_cpu_percent": 79.9,
            "minimum_host_mem_available_mib": 1536,
            "peak_rendezvous_rss_mib": 64,
            "peak_harness_proxy_rss_mib": 64,
            "peak_process_fds": 100,
            "peak_postgres_connections": 20,
            "event_loop_lag_p99_ms": 5,
            "operation_unacked_bytes_peak": 65536,
            "stream_unacked_bytes_peak": 262144,
            "connection_unacked_bytes_peak": 524288,
            "process_unacked_bytes_peak": 524288,
            "postgres_checkpoint_updates_per_second": 34,
            "heartbeat_receives_per_second": 200,
        },
        "scenario_outcomes": {
            scenario: "passed" for scenario in PERSISTENT_TRANSPORT_SCENARIOS
        },
        "duplicate_executions": 0,
        "leaked_environments": 0,
        "breaker_openings": 0,
        "false_global_circuit_trips": 0,
        "reconnect_token_issued": 1000,
        "reconnect_token_refreshed": 1000,
        "reconnect_token_consumed": 1000,
        "reconnect_token_replayed": 0,
        "reconnect_token_expired": 0,
        "reconnect_token_cleaned": 1000,
        "cancellation_delivery_observations": 1000,
        "process_containment_observations": 1000,
        "settlement_count": 32,
        "truncation_markers_missing": 0,
        "control_frame_starvation_events": 0,
    }


def test_persistent_transport_report_records_required_content_free_evidence():
    report = validate_persistent_transport_report(_persistent_transport_report())

    assert report.status == "passed"
    assert [cohort.transport for cohort in report.cohorts] == [
        "persistent",
        "legacy",
    ]
    assert report.resources.postgres_checkpoint_updates_per_second == 34


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("resources", "peak_cpu_percent"), 80),
        (("resources", "minimum_host_mem_available_mib"), 1535),
        (("resources", "operation_unacked_bytes_peak"), 65537),
        (("breaker_openings",), 1),
    ],
)
def test_persistent_transport_passing_report_rejects_any_gate_miss(path, value):
    payload = _persistent_transport_report()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        validate_persistent_transport_report(payload)


def test_chaos_report_cannot_be_mislabeled_as_release_qualification():
    payload = _persistent_transport_report()
    payload["qualification_kind"] = "chaos"
    payload["breaker_openings"] = 1

    with pytest.raises(ValidationError):
        validate_persistent_transport_report(payload)


def _live_qualification_evidence():
    return DurableQualificationEvidence(
        expected_users=32,
        admitted_turns=32,
        admission_denominator_events=32,
        terminal_turns=32,
        queued_states=0,
        stale_fences=0,
        executor_starts=16,
        duplicate_executor_starts=0,
        workspace_creates=1,
        workspace_reuses=15,
        workspace_evictions=16,
        billed_duration_ms=16_000,
        window_started_at_ms=1,
        window_ended_at_ms=2,
        p95_server_latency_ms_by_workload=_SERVER_LATENCY_P95,
        source="durable_qualification_records",
    )


class _LifecycleSource:
    def __init__(self, delta: ModalLifecycleDelta = _NO_MODAL):
        self.delta = delta
        self.calls = 0

    def snapshot(self, _profile_name):
        self.calls += 1
        before = self.calls % 2 == 1
        return ModalLifecycleSnapshot(
            captured_at_ms=self.calls,
            creates=0 if before else self.delta.creates,
            reuses=0 if before else self.delta.reuses,
            evictions=0 if before else self.delta.evictions,
            active_duration_ms=0 if before else self.delta.active_duration_ms,
            source="application_modal_lifecycle",
        )


def test_fleet_shapes_have_exact_allowlisted_topology_and_capacity():
    expected = {
        "5x32": (5, 32, 160, 128),
        "8x16": (8, 16, 128, 112),
        "16x8": (16, 8, 128, 120),
    }

    for name, capacities in expected.items():
        shape = resolve_fleet_shape(name)
        workers, sessions, aggregate, survivor = capacities
        assert shape.worker_count == workers
        assert shape.sessions_per_worker == sessions
        assert shape.aggregate_capacity == aggregate
        assert shape.post_loss_capacity == survivor
        assert [replica.worker_id for replica in shape.replicas] == [
            f"staging-qualification-{index:02d}" for index in range(workers)
        ]
        assert [replica.port for replica in shape.replicas] == list(
            range(8780, 8780 + workers)
        )

    with pytest.raises(FleetRunRefused, match="allowlisted fleet shape"):
        resolve_fleet_shape("10x10")

    with pytest.raises(FrozenInstanceError):
        resolve_fleet_shape("5x32").worker_count = 6


def test_capacity_profiles_bind_exact_arrivals_to_post_loss_capacity():
    expected = {
        "2x32": (2, 32, 32, 64, 32),
        "4x16": (4, 16, 48, 64, 48),
        "3x32": (3, 32, 64, 96, 64),
    }

    for name, values in expected.items():
        shape = resolve_fleet_shape(name)
        workers, sessions, users, aggregate, survivor = values
        assert shape.worker_count == workers
        assert shape.sessions_per_worker == sessions
        assert shape.expected_users == users
        assert shape.aggregate_capacity == aggregate
        assert shape.post_loss_capacity == survivor

        report = aggregate_round(
            name="survivor",
            expected_users=users,
            observations=tuple(
                BaselineObservation("compatible", 10) for _ in range(users)
            ),
            protocol_errors=0,
            transport_errors=0,
            forbidden_activity=ForbiddenActivity(),
        )
        assert report.expected_users == users
        assert report.passed is True


def test_capacity_qualification_profile_is_separate_and_ascending():
    from backend.scripts.qualify_external_pi_fleet import resolve_qualification_profile

    single_shape_names, single_report_name = resolve_qualification_profile("32-user")
    shape_names, report_name = resolve_qualification_profile("capacity")
    persistent_shapes, persistent_report = resolve_qualification_profile(
        "persistent-transport"
    )

    assert single_shape_names == ("2x32",)
    assert single_report_name == "external-pi-32-user-qualification.json"
    assert shape_names == ("2x32", "4x16", "3x32")
    assert report_name == "external-pi-capacity-qualification.json"
    assert persistent_shapes == ("2x32",)
    assert persistent_report == "external-pi-persistent-transport-fleet.json"
    with pytest.raises(FleetRunRefused, match="qualification profile"):
        resolve_qualification_profile("unknown")


def test_persistent_profile_manifest_preflight_runs_before_live_operator(tmp_path):
    from backend.scripts.qualify_external_pi_fleet import (
        load_persistent_transport_manifest,
    )

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_persistent_transport_manifest()))
    load_persistent_transport_manifest(path)

    payload = _persistent_transport_manifest()
    payload["chaos_declared"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(FleetRunRefused, match="manifest is invalid"):
        load_persistent_transport_manifest(path)


def test_durable_profiles_bind_32_mixed_turns_then_100_immediate_admissions():
    functional = resolve_durable_profile("32-functional-turns")
    admission = resolve_durable_profile("100-immediate-admission")

    assert functional.expected_users == functional.spawn_rate == 32
    assert Counter(functional.workloads) == Counter(
        {"no_tool": 16, "read": 8, "bash": 8}
    )
    assert admission.expected_users == admission.spawn_rate == 100
    assert admission.workloads == ("admission_stream",) * 100
    assert functional.application_queue is False
    assert admission.application_queue is False
    assert functional.minimum_available_bytes == MIN_PROJECTED_MEM_AVAILABLE_BYTES
    assert admission.minimum_available_bytes == MIN_PROJECTED_MEM_AVAILABLE_BYTES


def test_durable_profile_report_records_required_content_free_measurements():
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            workload=workload,
            outcome="completed",
            admission_ms=20 + index,
            reconnect_ready_ms=40 + index,
            ttft_ms=100 + index,
            completion_ms=1_000 + index,
            reconnects=1 if index == 0 else 0,
            reconnect_successes=1 if index == 0 else 0,
            model_starts=1,
            operation_start_count=0 if workload == "no_tool" else 1,
            duplicate_operation_start_count=0,
            terminal_cause="completed",
        )
        for index, workload in enumerate(profile.workloads)
    )

    report = aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=2 * 1024**3,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=50.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=8,
        qualification_evidence=_live_qualification_evidence(),
        modal_rate=_MODAL_RATE,
    )

    assert report.passed is True
    assert report.refusals == report.queued_states == report.typed_failures == 0
    assert report.p95_ttft_ms == 130
    assert report.p95_ttft_ms_by_workload == {
        "bash": 131,
        "no_tool": 115,
        "read": 123,
    }
    assert report.model_dump()["p95_latency_attribution_ms_by_workload"] == {
        "bash": {
            "client_admission_ms": 51,
            "client_reconnect_ready_ms": 71,
            "client_post_reconnect_to_ttft_ms": 60,
            "server_provider_gateway_received_ms": 320,
            "provider_ttft_ms": 420,
            "server_first_semantic_event_ms": 520,
            "end_to_end_ttft_ms": 131,
        },
        "no_tool": {
            "client_admission_ms": 35,
            "client_reconnect_ready_ms": 55,
            "client_post_reconnect_to_ttft_ms": 60,
            "server_provider_gateway_received_ms": 300,
            "provider_ttft_ms": 400,
            "server_first_semantic_event_ms": 500,
            "end_to_end_ttft_ms": 115,
        },
        "read": {
            "client_admission_ms": 43,
            "client_reconnect_ready_ms": 63,
            "client_post_reconnect_to_ttft_ms": 60,
            "server_provider_gateway_received_ms": 310,
            "provider_ttft_ms": 410,
            "server_first_semantic_event_ms": 510,
            "end_to_end_ttft_ms": 123,
        },
    }
    assert report.p99_completion_ms == 1_031
    assert report.ttft_observations == report.completion_observations == 32
    assert report.reconnects == report.reconnect_successes == 1
    assert report.modal_creates == 1
    assert report.modal_reuses == 15
    assert report.modal_evictions == 16
    assert report.modal_active_ms > 0
    assert report.modal_rate_microusd_per_second > 0
    assert report.modal_estimated_cost_microusd == math.ceil(
        report.modal_active_ms * report.modal_rate_microusd_per_second / 1000
    )


def test_live_report_requires_durable_executor_start_and_duplicate_evidence():
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            workload=workload,
            outcome="completed",
            admission_ms=20,
            reconnect_ready_ms=40,
            ttft_ms=100,
            completion_ms=1_000,
            model_starts=1,
            terminal_cause="completed",
        )
        for workload in profile.workloads
    )
    base = {
        "expected_users": 32,
        "admitted_turns": 32,
        "admission_denominator_events": 32,
        "terminal_turns": 32,
        "queued_states": 0,
        "stale_fences": 0,
        "executor_starts": 16,
        "duplicate_executor_starts": 0,
        "workspace_creates": 1,
        "workspace_reuses": 15,
        "workspace_evictions": 16,
        "billed_duration_ms": 16_000,
        "window_started_at_ms": 1,
        "window_ended_at_ms": 2,
        "p95_server_latency_ms_by_workload": _SERVER_LATENCY_P95,
        "source": "durable_qualification_records",
    }

    def aggregate(evidence):
        return aggregate_durable_profile(
            profile=profile,
            observations=observations,
            peak_memory_bytes=2 * 1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=32,
            peak_active_external_workers=4,
            peak_active_sandboxes=16,
            qualification_evidence=DurableQualificationEvidence(**evidence),
            modal_rate=_MODAL_RATE,
        )

    assert aggregate(base).passed is True
    assert aggregate({**base, "executor_starts": 0}).passed is False
    assert aggregate({**base, "duplicate_executor_starts": 1}).passed is False


def test_durable_profile_requires_sub_two_second_p95_for_every_workload():
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            workload=workload,
            outcome="completed",
            ttft_ms=2_000 if index == 31 else 100,
            completion_ms=1_000,
            model_starts=1,
            terminal_cause="completed",
        )
        for index, workload in enumerate(profile.workloads)
    )

    report = aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=1024**3,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=20.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=1,
        modal_lifecycle=_FUNCTIONAL_MODAL,
        modal_rate=_MODAL_RATE,
    )

    assert report.p95_ttft_ms_by_workload["bash"] == 2_000
    assert report.passed is False


def test_durable_profile_report_fails_refusal_queue_duplicate_or_lost_terminal():
    profile = resolve_durable_profile("100-immediate-admission")
    base = DurableTurnObservation(
        workload="admission_stream",
        outcome="completed",
        ttft_ms=100,
        completion_ms=1_000,
        model_starts=1,
        terminal_cause="completed",
    )
    mutations = (
        base.model_copy(update={"outcome": "refused", "terminal_cause": "refused"}),
        base.model_copy(update={"queued_states": 1}),
        base.model_copy(update={"model_starts": 2}),
        base.model_copy(update={"duplicate_operation_start_count": 1}),
        base.model_copy(update={"terminal_cause": "terminal_lost"}),
        base.model_copy(update={"stale_mutations": 1}),
        base.model_copy(update={"duplicate_turns": 1}),
        base.model_copy(update={"ttft_ms": None}),
    )

    for mutation in mutations:
        report = aggregate_durable_profile(
            profile=profile,
            observations=(mutation,) + (base,) * 99,
            peak_memory_bytes=1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=100,
            peak_active_external_workers=8,
            peak_active_sandboxes=0,
            modal_lifecycle=_NO_MODAL,
            modal_rate=_MODAL_RATE,
        )
        assert report.passed is False


def test_durable_profile_retains_slow_completion_as_failing_evidence():
    profile = resolve_durable_profile("32-functional-turns")
    slow = DurableTurnObservation(
        workload="no_tool",
        outcome="completed",
        ttft_ms=100,
        completion_ms=60_001,
        model_starts=1,
        terminal_cause="completed",
    )
    normal = slow.model_copy(update={"completion_ms": 1_000})

    report = aggregate_durable_profile(
        profile=profile,
        observations=(slow,)
        + tuple(
            normal.model_copy(update={"workload": workload})
            for workload in profile.workloads[1:]
        ),
        peak_memory_bytes=1024**3,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=20.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=1,
        modal_lifecycle=_FUNCTIONAL_MODAL,
        modal_rate=_MODAL_RATE,
    )

    assert report.p99_completion_ms == 60_001
    assert report.passed is False


def test_durable_report_is_atomic_mode_0600_and_contains_no_payloads(tmp_path: Path):
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            workload=workload,
            outcome="completed",
            ttft_ms=100,
            completion_ms=1_000,
            model_starts=1,
            terminal_cause="completed",
        )
        for workload in profile.workloads
    )
    profile_report = aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=1024**3,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=20.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=1,
        modal_lifecycle=_FUNCTIONAL_MODAL,
        modal_rate=_MODAL_RATE,
    )
    cleanup = {
        "flags_restored": True,
        "exact_workers_drained": True,
        "transient_workers_removed": True,
        "listeners_gone": True,
        "status_files_gone": True,
        "processes_gone": True,
        "final_active_backend_turns": 0,
        "final_active_external_workers": 0,
        "final_active_sandboxes": 0,
    }
    completed = DurableQualificationReport(
        release_id="0123456789ab-staging",
        status="completed",
        reason=None,
        profiles=(profile_report,),
        **cleanup,
    )
    assert completed.passed is True
    report = DurableQualificationReport(
        release_id="0123456789ab-staging",
        status="failed",
        reason="durable_profile_failed",
        profiles=(),
        **cleanup,
    )
    destination = tmp_path / "durable.json"

    publish_durable_report(report, destination, tmp_path)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert destination.stat().st_mode & 0o777 == 0o600
    assert payload["release_id"] == "0123456789ab-staging"
    assert payload["flags_restored"] is True
    assert payload["final_active_backend_turns"] == 0
    assert payload["final_active_external_workers"] == 0
    assert payload["final_active_sandboxes"] == 0
    assert "prompt" not in destination.read_text(encoding="utf-8")
    assert "token" not in destination.read_text(encoding="utf-8")

    forged = report.model_copy(
        update={"status": "completed", "reason": None, "profiles": ()}
    )
    with pytest.raises(ValidationError, match="completed.*profile sequence"):
        publish_durable_report(forged, tmp_path / "forged.json", tmp_path)


class _DurableOperator:
    def __init__(
        self,
        *,
        environment=None,
        refuse_profile=None,
        failure_stage=None,
        prior_flags=None,
        cpu_percent=20.0,
        cpu_guard_percent=80.0,
        mutate_snapshot=False,
        no_op_proof=False,
    ):
        from backend.scripts.qualify_durable_external_turns import (
            QualificationEnvironment,
        )

        self.current_environment = environment or QualificationEnvironment(
            name="staging",
            target_release="0123456789ab-staging",
            staging_release="0123456789ab-staging",
            production_release="fedcba987654-production",
            host_mem_total_bytes=16 * 1024**3,
            public_external_admission_flags=(False, False, False),
        )
        self.refuse_profile = refuse_profile
        self.failure_stage = failure_stage
        self.prior_flags = (
            prior_flags
            if prior_flags is not None
            else {"external": False, "executor": False, "remote": False}
        )
        self.cpu_percent = cpu_percent
        self.cpu_guard_percent = cpu_guard_percent
        self.mutate_snapshot = mutate_snapshot
        self.no_op_proof = no_op_proof
        self.events = []

    def _fail(self, stage):
        if self.failure_stage == stage:
            raise RuntimeError(f"TOP_SECRET_{stage}")
        if self.failure_stage == f"interrupt:{stage}":
            raise KeyboardInterrupt(f"TOP_SECRET_{stage}")

    def environment(self):
        self.events.append(("environment",))
        self._fail("environment")
        return self.current_environment

    def snapshot_flags(self):
        self.events.append(("snapshot_flags",))
        self._fail("snapshot_flags")
        return self.prior_flags

    def resource_snapshot(self, profile):
        self.events.append(("resource", profile.name))
        self._fail("resource")
        available = 1024**3 if profile.name == self.refuse_profile else 3 * 1024**3
        return HostResourceSnapshot(
            available,
            0,
            self.cpu_percent,
            self.cpu_guard_percent,
        )

    def setup_profile(self, profile):
        self.events.append(("setup", profile.name))
        if self.mutate_snapshot:
            self.prior_flags["external"] = True
        self._fail("setup")

    def run_profile(self, profile):
        self.events.append(("run", profile.name))
        self._fail("run")
        observations = tuple(
            DurableTurnObservation(
                workload=workload,
                outcome="completed",
                ttft_ms=100,
                completion_ms=1_000,
                model_starts=1,
                operation_start_count=0,
                duplicate_operation_start_count=0,
                terminal_cause="completed",
            )
            for workload in profile.workloads
        )
        return aggregate_durable_profile(
            profile=profile,
            observations=observations,
            peak_memory_bytes=1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=profile.expected_users,
            peak_active_external_workers=4,
            peak_active_sandboxes=(1 if profile.name == "32-functional-turns" else 0),
            modal_lifecycle=(
                _FUNCTIONAL_MODAL
                if profile.name == "32-functional-turns"
                else _NO_MODAL
            ),
            modal_rate=_MODAL_RATE,
        )

    def teardown_profile(self, profile, scope_id=None):
        self.events.append(("teardown", profile.name))
        if self.failure_stage == f"teardown:{profile.name}":
            raise RuntimeError("TOP_SECRET_teardown")
        self._fail("teardown")

    def restore_flags(self, flags):
        restored = dict(flags)
        self.events.append(("restore_flags", restored))
        self._fail("restore_flags")
        return None if self.no_op_proof else restored

    def cleanup_transient_workers(self):
        self.events.append(("cleanup_transient_workers",))
        self._fail("cleanup_transient_workers")
        if self.no_op_proof:
            return None
        from backend.scripts.qualify_durable_external_turns import CleanupProof

        return CleanupProof(
            exact_workers_drained=True,
            transient_workers_removed=True,
            listeners_gone=True,
            status_files_gone=True,
            processes_gone=True,
            final_active_backend_turns=0,
            final_active_external_workers=0,
            final_active_sandboxes=0,
        )


def test_durable_controller_runs_only_32_and_restores_everything():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator()
    result = run_durable_qualification(operator)

    assert result.status == "completed"
    assert result.passed is True


def test_durable_controller_finalizes_billed_evidence_after_profile_teardown():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    class TwoPhaseOperator(_DurableOperator):
        def finalize_profile(self, profile, measurement):
            self.events.append(("finalize", profile.name))
            return measurement

    operator = TwoPhaseOperator()
    result = run_durable_qualification(operator)

    assert result.passed is True
    for name in ("32-functional-turns",):
        assert operator.events.index(("teardown", name)) < operator.events.index(
            ("finalize", name)
        )
    assert [report.profile for report in result.profiles] == ["32-functional-turns"]
    assert [event for event in operator.events if event[0] == "run"] == [
        ("run", "32-functional-turns"),
    ]
    assert [event[1] for event in operator.events if event[0] == "resource"] == [
        "32-functional-turns",
    ]
    assert result.flags_restored is True
    assert result.exact_workers_drained is True
    assert operator.events[-2][0] == "restore_flags"
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_treats_resource_refusal_as_evidence_and_stops():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator(refuse_profile="32-functional-turns")
    result = run_durable_qualification(operator)

    assert result.status == "resource_refused"
    assert result.reason == "memory_headroom"
    assert result.profiles == ()
    assert ("setup", "32-functional-turns") not in operator.events
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_uses_fixed_cpu_guard_and_typed_refusal():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(cpu_percent=90.0, cpu_guard_percent=100.0)
    result = run_durable_qualification(operator)

    assert result.status == "resource_refused"
    assert result.reason == "cpu_headroom"
    assert not any(event[0] == "setup" for event in operator.events)
    assert [event[0] for event in operator.events].count("resource") == 1
    assert operator.events[-1] == ("cleanup_transient_workers",)


@pytest.mark.parametrize(
    "updates",
    (
        {"name": "production"},
        {"target_release": "fedcba987654-staging"},
        {"production_release": "0123456789ab-staging"},
        {"production_release": "0123456789ab-production"},
        {"host_mem_total_bytes": 4 * 1024**3},
        {"public_external_admission_flags": (False, True, False)},
    ),
)
def test_durable_controller_refuses_unsafe_environment_but_still_restores(updates):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationEnvironment,
        QualificationRefused,
        run_durable_qualification,
    )

    values = {
        "name": "staging",
        "target_release": "0123456789ab-staging",
        "staging_release": "0123456789ab-staging",
        "production_release": "fedcba987654-production",
        "host_mem_total_bytes": 16 * 1024**3,
        "public_external_admission_flags": (False, False, False),
    }
    values.update(updates)
    operator = _DurableOperator(environment=QualificationEnvironment(**values))

    with pytest.raises(QualificationRefused):
        run_durable_qualification(operator)

    assert not any(event[0] == "setup" for event in operator.events)
    assert not any(event[0] == "restore_flags" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_restores_after_setup_failure():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(failure_stage="setup")
    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason == "durable_qualification_failed"
    assert "TOP_SECRET" not in result.model_dump_json()
    assert ("teardown", "32-functional-turns") in operator.events
    assert operator.events[-2][0] == "restore_flags"
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_post_validation_typed_prerequisite_failure_returns_bounded_report():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    class RefusingOperator(_DurableOperator):
        def setup_profile(self, profile):
            self.events.append(("setup", profile.name))
            raise QualificationRefused("staging_prerequisite_missing")

    report = run_durable_qualification(RefusingOperator())

    assert report.status == "failed"
    assert report.reason == "staging_prerequisite_missing"
    assert "traceback" not in report.model_dump_json().lower()


def test_durable_controller_teardown_failure_retains_no_profile():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator(failure_stage="teardown:32-functional-turns")

    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason == "cleanup_failed"
    assert result.profiles == ()
    assert result.cleanup_passed is True


def test_durable_controller_cannot_skip_or_reverse_the_binding_profile_order():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator()
    for forbidden in (
        ("100-immediate-admission", "32-functional-turns"),
        ("32-functional-turns", "100-immediate-admission"),
    ):
        with pytest.raises(QualificationRefused, match="profile_order"):
            run_durable_qualification(operator, profiles=forbidden)
    assert not any(event[0] == "setup" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_accepts_standalone_functional_profile_only():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator()
    report = run_durable_qualification(
        operator,
        profiles=("32-functional-turns",),
    )

    assert report.status == "completed"
    assert [profile.profile for profile in report.profiles] == ["32-functional-turns"]
    assert [event for event in operator.events if event[0] == "run"] == [
        ("run", "32-functional-turns")
    ]

    for forbidden in ((), ("100-immediate-admission",)):
        with pytest.raises(QualificationRefused, match="profile_order"):
            run_durable_qualification(_DurableOperator(), profiles=forbidden)


def test_durable_controller_requires_snapshot_flags_off_before_setup():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(
        prior_flags={"external": True, "executor": False, "remote": False}
    )
    result = run_durable_qualification(operator)
    assert result.status == "failed"
    assert result.reason == "public_external_admission_flags_must_be_off"
    assert not any(event[0] == "setup" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


@pytest.mark.parametrize(
    "stage",
    (
        "snapshot_flags",
        "resource",
        "setup",
        "run",
        "teardown",
        "restore_flags",
        "cleanup_transient_workers",
        "interrupt:snapshot_flags",
        "interrupt:run",
    ),
)
def test_durable_controller_attempts_cleanup_at_every_failure_boundary(stage):
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(failure_stage=stage)
    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason in {"durable_qualification_failed", "cleanup_failed"}
    assert operator.events[-1] == ("cleanup_transient_workers",)
    if stage in {"snapshot_flags", "interrupt:snapshot_flags"}:
        assert not any(event[0] == "restore_flags" for event in operator.events)


@pytest.mark.parametrize(
    ("stage", "expected_reason"),
    (
        ("setup", "durable_qualification_failed"),
        ("run", "durable_qualification_failed"),
        ("interrupt:run", "durable_qualification_failed"),
        ("teardown", "cleanup_failed"),
        ("finalize", "durable_qualification_failed"),
        ("cleanup_evidence", "cleanup_failed"),
    ),
)
def test_durable_controller_retains_scope_when_teardown_fails_for_cleanup_retry(
    stage, expected_reason
):
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    class ScopedOperator(_DurableOperator):
        def setup_profile(self, profile):
            self.events.append(("scope_created", profile.name))
            super().setup_profile(profile)

        def qualification_scope_id(self, profile):
            self.events.append(("scope_id", profile.name))
            return uuid.UUID("d0000000-0000-4000-8000-000000000001")

        def finalize_profile(self, profile, result):
            self.events.append(("finalize", profile.name))
            self._fail("finalize")
            return result

        def cleanup_profile_evidence(self, profile):
            self.events.append(("cleanup_evidence", profile.name))
            self._fail("cleanup_evidence")

    operator = ScopedOperator(failure_stage=stage)
    report = run_durable_qualification(operator)

    assert report.status == "failed"
    assert report.reason == expected_reason
    assert ("teardown", "32-functional-turns") in operator.events
    if stage in {"teardown", "cleanup_transient_workers"}:
        assert ("cleanup_evidence", "32-functional-turns") not in operator.events
    else:
        assert ("cleanup_evidence", "32-functional-turns") in operator.events
    assert operator.events.index(("cleanup_transient_workers",)) < (
        operator.events.index(("cleanup_evidence", "32-functional-turns"))
        if ("cleanup_evidence", "32-functional-turns") in operator.events
        else len(operator.events)
    )


def test_durable_controller_does_not_delete_scope_when_final_probe_finds_leak():
    from backend.scripts.qualify_durable_external_turns import (
        CleanupProof,
        run_durable_qualification,
    )

    class LeakingOperator(_DurableOperator):
        def cleanup_profile_evidence(self, profile):
            self.events.append(("cleanup_evidence", profile.name))

        def cleanup_transient_workers(self):
            self.events.append(("cleanup_transient_workers",))
            return CleanupProof(True, True, True, True, True, 0, 1, 0)

    operator = LeakingOperator()
    report = run_durable_qualification(operator)

    assert report.reason == "cleanup_failed"
    assert not any(event[0] == "cleanup_evidence" for event in operator.events)


def test_primary_profile_failure_plus_worker_cleanup_failure_is_typed_cleanup_failed():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    class CombinedFailureOperator(_DurableOperator):
        def cleanup_transient_workers(self):
            self.events.append(("cleanup_transient_workers",))
            return None

    report = run_durable_qualification(CombinedFailureOperator(failure_stage="run"))

    assert report.status == "failed"
    assert report.reason == "cleanup_failed"
    assert report.cleanup_passed is False


def test_durable_controller_cleans_after_environment_probe_failure():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator(failure_stage="environment")
    with pytest.raises(QualificationRefused) as exc:
        run_durable_qualification(operator)

    assert "TOP_SECRET" not in str(exc.value)
    assert operator.events[-1] == ("cleanup_transient_workers",)
    assert not any(event[0] == "restore_flags" for event in operator.events)


def test_durable_controller_copies_mutable_flag_snapshot_before_setup():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    flags = {"external": False, "executor": False, "remote": False}
    operator = _DurableOperator(prior_flags=flags, mutate_snapshot=True)
    result = run_durable_qualification(operator)

    assert result.status == "completed"
    assert flags["external"] is True
    restore = next(event for event in operator.events if event[0] == "restore_flags")
    assert restore[1] == {"external": False, "executor": False, "remote": False}


def test_durable_controller_no_op_cleanup_adapter_cannot_complete():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    result = run_durable_qualification(_DurableOperator(no_op_proof=True))

    assert result.status == "failed"
    assert result.reason == "cleanup_failed"
    assert result.passed is False


def test_durable_report_rejects_status_reason_profile_and_cleanup_mismatches():
    profile = resolve_durable_profile("32-functional-turns")
    observations = tuple(
        DurableTurnObservation(
            workload=workload,
            outcome="completed",
            ttft_ms=100,
            completion_ms=1_000,
            model_starts=1,
            terminal_cause="completed",
        )
        for workload in profile.workloads
    )
    profile_report = aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=1024**3,
        minimum_host_mem_available_bytes=2 * 1024**3,
        peak_cpu_percent=20.0,
        peak_active_backend_turns=32,
        peak_active_external_workers=4,
        peak_active_sandboxes=1,
        modal_lifecycle=_FUNCTIONAL_MODAL,
        modal_rate=_MODAL_RATE,
    )
    cleanup = {
        "flags_restored": True,
        "exact_workers_drained": True,
        "transient_workers_removed": True,
        "listeners_gone": True,
        "status_files_gone": True,
        "processes_gone": True,
        "final_active_backend_turns": 0,
        "final_active_external_workers": 0,
        "final_active_sandboxes": 0,
    }

    with pytest.raises(ValidationError, match="resource-refused"):
        DurableQualificationReport(
            release_id="0123456789ab-staging",
            status="resource_refused",
            reason="memory_headroom",
            profiles=(profile_report,),
            **{**cleanup, "listeners_gone": False},
        )
    with pytest.raises(ValidationError, match="typed reason"):
        DurableQualificationReport(
            release_id="0123456789ab-staging",
            status="failed",
            reason=None,
            profiles=(profile_report,),
            **cleanup,
        )
    with pytest.raises(ValidationError, match="at most 1"):
        DurableQualificationReport(
            release_id="0123456789ab-staging",
            status="failed",
            reason="test_failure",
            profiles=(profile_report, profile_report),
            **cleanup,
        )


@pytest.mark.parametrize("reason", ("test_failure", "durable_qualification_failed"))
def test_completed_report_cannot_be_forged_as_contradictory_failure(
    reason: str, tmp_path: Path
) -> None:
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    completed = run_durable_qualification(_DurableOperator())
    forged = completed.model_copy(update={"status": "failed", "reason": reason})
    payload = forged.model_dump(exclude_computed_fields=True)

    with pytest.raises(ValidationError, match="failed durable report"):
        DurableQualificationReport.model_validate(payload)
    with pytest.raises(ValidationError, match="failed durable report"):
        publish_durable_report(forged, tmp_path / f"{reason}.json", tmp_path)


@pytest.mark.parametrize(
    ("reason", "profile_count"),
    (
        ("arbitrary_failure", 0),
        ("durable_profile_failed", 2),
        ("public_external_admission_flags_must_be_off", 2),
    ),
)
def test_failed_report_reasons_and_profile_prefixes_are_closed(
    reason: str, profile_count: int
) -> None:
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    completed = run_durable_qualification(_DurableOperator())
    payload = completed.model_dump(exclude_computed_fields=True)
    payload.update(
        status="failed",
        reason=reason,
        profiles=payload["profiles"][:profile_count],
    )

    with pytest.raises(ValidationError, match="failed durable report"):
        DurableQualificationReport.model_validate(payload)


def test_controller_generated_cleanup_failure_is_a_valid_failed_report() -> None:
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    report = run_durable_qualification(_DurableOperator(no_op_proof=True))

    assert report.status == "failed"
    assert report.reason == "cleanup_failed"
    assert report.cleanup_passed is False
    assert (
        DurableQualificationReport.model_validate(
            report.model_dump(exclude_computed_fields=True)
        )
        == report
    )


@pytest.mark.parametrize(
    ("reason", "profile_count", "flags_restored"),
    (
        ("durable_qualification_failed", 0, True),
        ("durable_profile_failed", 0, True),
        ("staging_isolation_required", 0, True),
        ("exact_staging_release_required", 0, True),
        ("approved_16_gib_host_required", 0, True),
        ("public_external_admission_flags_must_be_off", 0, True),
        ("public_external_admission_flags_are_invalid", 0, False),
    ),
)
def test_failed_report_accepts_only_controller_producible_reason_prefixes(
    reason: str, profile_count: int, flags_restored: bool
) -> None:
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    completed = run_durable_qualification(_DurableOperator())
    payload = completed.model_dump(exclude_computed_fields=True)
    payload.update(
        status="failed",
        reason=reason,
        profiles=payload["profiles"][:profile_count],
        flags_restored=flags_restored,
    )

    report = DurableQualificationReport.model_validate(payload)

    assert report.status == "failed"
    assert report.reason == reason


def test_failed_report_retains_one_nonpassing_profile_for_diagnostics() -> None:
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    completed = run_durable_qualification(_DurableOperator())
    failed_profile = completed.profiles[0].model_copy(
        update={"typed_failures": 1, "typed_failure_counts": {"test": 1}}
    )
    payload = completed.model_dump(exclude_computed_fields=True)
    payload.update(
        status="failed",
        reason="durable_profile_failed",
        profiles=(failed_profile,),
    )

    report = DurableQualificationReport.model_validate(payload)

    assert report.status == "failed"
    assert report.reason == "durable_profile_failed"
    assert report.profiles == (failed_profile,)
    assert report.passed is False


def test_ordinal_routing_is_deterministic_and_balanced_after_loss():
    healthy = resolve_fleet_shape("8x16").replicas
    survivor = healthy[1:]

    assert route_ordinal(0, healthy) == healthy[0]
    assert route_ordinal(8, healthy) == healthy[0]
    assert route_ordinal(99, healthy) == healthy[3]
    assert route_ordinal(0, survivor) == survivor[0]

    counts = Counter(route_ordinal(ordinal, survivor) for ordinal in range(100))
    assert max(counts.values()) - min(counts.values()) == 1

    with pytest.raises(ValueError, match="ordinal"):
        route_ordinal(100, healthy)
    with pytest.raises(FleetRunRefused, match="allowlisted replicas"):
        route_ordinal(0, (FleetReplica(healthy[0].worker_id, healthy[1].port),))
    with pytest.raises(FleetRunRefused, match="allowlisted replicas"):
        route_ordinal(0, (healthy[0], healthy[0]))


def _safety_config(**updates) -> FleetSafetyConfig:
    values = {
        "environment": "staging",
        "requested_release": "0123456789ab-staging",
        "active_release": "0123456789ab-staging",
        "external_admission_enabled": False,
        "executor_routing_enabled": False,
        "remote_execution_enabled": False,
        "active_worker_id": "staging-blue",
        "active_worker_healthy": True,
        "worker_token": "protected-worker-token",
    }
    values.update(updates)
    return FleetSafetyConfig(**values)


def test_preflight_requires_exact_staging_release_and_disabled_flags():
    shape = resolve_fleet_shape("5x32")
    ports = tuple(
        PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas
    )

    validate_fleet_preflight(_safety_config(), shape, ports)
    assert "protected-worker-token" not in repr(_safety_config())

    unsafe = (
        {"environment": "production"},
        {"requested_release": "fedcba987654-staging"},
        {"external_admission_enabled": True},
        {"executor_routing_enabled": True},
        {"remote_execution_enabled": True},
        {"active_worker_id": "staging-qualification-00"},
        {"active_worker_healthy": False},
    )
    for updates in unsafe:
        with pytest.raises(FleetRunRefused, match="staging|release|disabled"):
            validate_fleet_preflight(_safety_config(**updates), shape, ports)


def test_preflight_requires_every_allowlisted_port_free_on_loopback():
    shape = resolve_fleet_shape("5x32")
    ports = [PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas]

    ports[2] = PortState(ports[2].port, "0.0.0.0", True)
    with pytest.raises(FleetRunRefused, match="free loopback ports"):
        validate_fleet_preflight(_safety_config(), shape, tuple(ports))

    ports[2] = PortState(ports[2].port, "127.0.0.1", False)
    with pytest.raises(FleetRunRefused, match="free loopback ports"):
        validate_fleet_preflight(_safety_config(), shape, tuple(ports))


def test_preflight_rejects_forged_topology_even_with_free_loopback_ports():
    forged = FleetShape(
        name="10x10",
        worker_count=1,
        sessions_per_worker=100,
        expected_users=100,
        replicas=(FleetReplica("staging-qualification-00", 8780),),
    )
    ports = (PortState(8780, "127.0.0.1", True),)

    with pytest.raises(FleetRunRefused, match="allowlisted fleet shape"):
        validate_fleet_preflight(_safety_config(), forged, ports)


def test_resource_preflight_preserves_1_5_gib_and_guards_cpu():
    one_gib = 1024**3
    accepted = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * one_gib,
            projected_additional_bytes=MIN_PROJECTED_MEM_AVAILABLE_BYTES,
            cpu_percent=79.9,
            cpu_guard_percent=80.0,
        )
    )
    assert accepted.status == "passed"
    assert accepted.projected_mem_available_bytes == MIN_PROJECTED_MEM_AVAILABLE_BYTES

    low_memory = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * one_gib - 1,
            projected_additional_bytes=MIN_PROJECTED_MEM_AVAILABLE_BYTES,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )
    saturated = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=4 * one_gib,
            projected_additional_bytes=one_gib,
            cpu_percent=80.0,
            cpu_guard_percent=80.0,
        )
    )
    assert low_memory.status == "resource_refused"
    assert saturated.status == "resource_refused"

    with pytest.raises(ValueError, match="resource preflight evidence"):
        ResourcePreflight("passed", -1, 20.0, 80.0)

    with pytest.raises(ValueError, match="resource inputs"):
        HostResourceSnapshot(2**63, 0, 20.0, 80.0)
    with pytest.raises(ValueError, match="resource inputs"):
        HostResourceSnapshot(2**63 - 1, 2**63, 20.0, 80.0)
    with pytest.raises(ValueError, match="resource preflight evidence"):
        ResourcePreflight("passed", 2**63, 20.0, 80.0)


def test_fleet_workload_reuses_shadow_payload_and_classifier_contracts():
    assert build_external_pi_fleet_request is build_external_pi_baseline_request
    assert classify_external_pi_fleet_response is classify_external_pi_baseline_response

    request = build_external_pi_fleet_request(0, "canonical-runtime-prompt")
    assert len(request.transcript_entries) == 2_000
    assert request.tool_names == ()


def _round(
    name: str, *, expected_users: int = 100, latency_ms: int = 100, activity=None
):
    return aggregate_round(
        name=name,
        expected_users=expected_users,
        observations=tuple(
            BaselineObservation("compatible", latency_ms) for _ in range(expected_users)
        ),
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=activity or ForbiddenActivity(),
    )


def _cleanup(**updates) -> CleanupEvidence:
    values = {
        "drain_proven": True,
        "registry_offline": True,
        "supervisors_stopped_before_workers": True,
        "units_removed": True,
        "status_files_removed": True,
        "ports_free": True,
        "processes_gone": True,
    }
    values.update(updates)
    return CleanupEvidence(**values)


def _unit_resources(shape_name: str) -> tuple[UnitResourceEvidence, ...]:
    return tuple(
        UnitResourceEvidence(
            unit_name=unit_name,
            peak_memory_bytes=100_000_000,
            peak_cpu_percent=10.0,
            peak_tasks=4,
        )
        for unit_name in qualification_unit_names(resolve_fleet_shape(shape_name))
    )


def _resources(shape_name: str = "5x32", **updates) -> ResourceEvidence:
    values = {
        "peak_memory_bytes": 300_000_000,
        "peak_cpu_percent": 40.0,
        "peak_tasks": 20,
        "minimum_host_mem_available_bytes": 2 * 1024**3,
        "unit_peaks": _unit_resources(shape_name),
    }
    values.update(updates)
    return ResourceEvidence(**values)


def _passed_resource_preflight():
    return evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * 1024**3,
            projected_additional_bytes=1024**3,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )


def _workers(shape_name: str) -> tuple[WorkerEvidence, ...]:
    shape = resolve_fleet_shape(shape_name)
    return tuple(
        WorkerEvidence(
            worker_id=replica.worker_id,
            port=replica.port,
            generation=index + 1,
            maximum_sessions=shape.sessions_per_worker,
        )
        for index, replica in enumerate(shape.replicas)
    )


def test_round_aggregation_requires_100_compatible_fast_content_free_observations():
    passing = _round("healthy", latency_ms=3_000)
    assert passing.observations == passing.compatible == 100
    assert passing.p95_ms == passing.p99_ms == 3_000
    assert passing.passed is True

    capacity = aggregate_round(
        name="survivor",
        observations=(BaselineObservation("compatible", 50),) * 99
        + (BaselineObservation("capacity", 50),),
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    slow_p95 = aggregate_round(
        name="healthy",
        observations=(BaselineObservation("compatible", 10),) * 94
        + (BaselineObservation("compatible", 3_001),) * 6,
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    slow_p99 = aggregate_round(
        name="healthy",
        observations=(BaselineObservation("compatible", 10),) * 98
        + (BaselineObservation("compatible", 5_001),) * 2,
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=ForbiddenActivity(),
    )
    forbidden = _round("healthy", activity=ForbiddenActivity(model_calls=1))
    assert capacity.passed is False
    assert slow_p95.passed is False
    assert slow_p99.p95_ms == 10 and slow_p99.p99_ms == 5_001
    assert slow_p99.passed is False
    assert forbidden.passed is False


def test_round_aggregation_accounts_for_protocol_and_transport_errors():
    observations = (BaselineObservation("compatible", 10),) * 98 + (
        BaselineObservation("error", 10),
        BaselineObservation("error", 10),
    )
    report = aggregate_round(
        name="healthy",
        observations=observations,
        protocol_errors=1,
        transport_errors=1,
        forbidden_activity=ForbiddenActivity(),
    )
    assert report.protocol_errors == 1
    assert report.transport_errors == 1
    assert report.passed is False


def test_round_report_rejects_forged_pass_with_contradictory_counts():
    with pytest.raises(ValidationError, match="round counts are inconsistent"):
        FleetRoundReport(
            name="healthy",
            expected_users=100,
            observations=1,
            compatible=100,
            capacity_rejections=0,
            protocol_errors=0,
            transport_errors=0,
            p95_ms=10,
            p99_ms=10,
            forbidden_activity=ForbiddenActivity(),
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FleetRoundReport(
            name="healthy",
            observations=100,
            compatible=100,
            capacity_rejections=0,
            protocol_errors=0,
            transport_errors=0,
            p95_ms=10,
            p99_ms=10,
            forbidden_activity=ForbiddenActivity(),
            passed=True,
        )


def test_shape_reports_require_both_rounds_survivor_capacity_and_cleanup():
    shape = resolve_fleet_shape("5x32")
    report = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )
    assert report.aggregate_capacity == 160
    assert report.post_loss_capacity == 128
    assert [worker.port for worker in report.workers] == list(range(8780, 8785))
    assert report.overall_passed is True

    failed_cleanup = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(ports_free=False),
    )
    assert failed_cleanup.cleanup_passed is False
    assert failed_cleanup.overall_passed is False

    forged_summary = failed_cleanup.model_copy(
        update={"cleanup_passed": True, "overall_passed": True}
    )
    forged_final = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(forged_summary,),
    )
    assert forged_final.preferred_shape is None

    contradictory_evidence = report.model_copy(update={"worker_count": 16})
    with pytest.raises(FleetRunRefused, match="shape report evidence"):
        build_final_report(
            release_id="0123456789ab-staging",
            runtime_id="external-pi-runtime-1",
            shapes=(contradictory_evidence,),
        )

    with pytest.raises(FleetRunRefused, match="resource preflight"):
        build_completed_shape_report(
            shape=shape,
            healthy=_round("healthy"),
            survivor=_round("survivor"),
            workers=_workers(shape.name),
            removed_worker_id=shape.replicas[0].worker_id,
            resources=_resources(),
            resource_preflight=evaluate_resource_preflight(
                HostResourceSnapshot(
                    mem_available_bytes=2 * 1024**3,
                    projected_additional_bytes=1024**3,
                    cpu_percent=20.0,
                    cpu_guard_percent=80.0,
                )
            ),
            cleanup=_cleanup(),
        )

    with pytest.raises(FleetRunRefused, match="per-unit resource evidence"):
        build_completed_shape_report(
            shape=shape,
            healthy=_round("healthy"),
            survivor=_round("survivor"),
            workers=_workers(shape.name),
            removed_worker_id=shape.replicas[0].worker_id,
            resources=_resources(unit_peaks=_unit_resources(shape.name)[:-1]),
            resource_preflight=_passed_resource_preflight(),
            cleanup=_cleanup(),
        )


def test_capacity_shape_rejects_rounds_for_a_different_arrival_count():
    shape = resolve_fleet_shape("2x32")

    with pytest.raises(FleetRunRefused, match="topology"):
        build_completed_shape_report(
            shape=shape,
            healthy=_round("healthy"),
            survivor=_round("survivor"),
            workers=_workers(shape.name),
            removed_worker_id=shape.replicas[0].worker_id,
            resources=_resources(shape.name),
            resource_preflight=_passed_resource_preflight(),
            cleanup=_cleanup(),
        )


def test_resource_refusal_is_bounded_evidence_and_never_a_pass():
    shape = resolve_fleet_shape("16x8")
    refusal = evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=2 * 1024**3,
            projected_additional_bytes=1024**3,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )
    report = build_resource_refused_shape_report(shape, refusal, _cleanup())
    assert report.status == "resource_refused"
    assert report.healthy is None and report.survivor is None
    assert report.overall_passed is False


def _completed_shape(name: str, *, memory: int, cpu: float, latency: int):
    shape = resolve_fleet_shape(name)
    return build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy", latency_ms=latency),
        survivor=_round("survivor", latency_ms=latency),
        workers=_workers(name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(
            name,
            peak_memory_bytes=memory,
            peak_cpu_percent=cpu,
        ),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )


def _preferred(*reports) -> str | None:
    return build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=reports,
    ).preferred_shape


def test_final_selection_prefers_lower_measured_memory_first():
    assert (
        _preferred(
            _completed_shape("5x32", memory=200, cpu=10.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=90.0, latency=1_000),
        )
        == "8x16"
    )


def test_final_selection_uses_cpu_when_memory_ties():
    assert (
        _preferred(
            _completed_shape("5x32", memory=100, cpu=20.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=1_000),
        )
        == "8x16"
    )


def test_final_selection_uses_latency_when_memory_and_cpu_tie():
    assert (
        _preferred(
            _completed_shape("5x32", memory=100, cpu=10.0, latency=20),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=10),
        )
        == "8x16"
    )


def test_final_selection_uses_worker_count_as_last_tiebreaker():
    assert (
        _preferred(
            _completed_shape("16x8", memory=100, cpu=10.0, latency=10),
            _completed_shape("5x32", memory=100, cpu=10.0, latency=10),
            _completed_shape("8x16", memory=100, cpu=10.0, latency=10),
        )
        == "5x32"
    )


def test_final_report_is_content_free_atomic_and_mode_0600(tmp_path: Path, monkeypatch):
    shape = resolve_fleet_shape("5x32")
    shape_report = build_completed_shape_report(
        shape=shape,
        healthy=_round("healthy"),
        survivor=_round("survivor"),
        workers=_workers(shape.name),
        removed_worker_id=shape.replicas[0].worker_id,
        resources=_resources(),
        resource_preflight=_passed_resource_preflight(),
        cleanup=_cleanup(),
    )
    final = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(shape_report,),
    )
    destination = tmp_path / "fleet.json"
    destination.write_text('{"previous":true}\n', encoding="utf-8")
    publish_fleet_report(final, destination, tmp_path)

    payload = destination.read_text(encoding="utf-8")
    assert json.loads(payload)["preferred_shape"] == "5x32"
    assert destination.stat().st_mode & 0o777 == 0o600
    for protected in (
        "protected-worker-token",
        "canonical-runtime-prompt",
        "request-body",
        "response-body",
        "exception-text",
    ):
        assert protected not in payload


def test_atomic_publication_failure_preserves_previous_report(
    tmp_path: Path, monkeypatch
):
    shape = resolve_fleet_shape("5x32")
    report = build_final_report(
        release_id="0123456789ab-staging",
        runtime_id="external-pi-runtime-1",
        shapes=(
            build_completed_shape_report(
                shape=shape,
                healthy=_round("healthy"),
                survivor=_round("survivor"),
                workers=_workers(shape.name),
                removed_worker_id=shape.replicas[0].worker_id,
                resources=_resources(),
                resource_preflight=_passed_resource_preflight(),
                cleanup=_cleanup(),
            ),
        ),
    )
    destination = tmp_path / "fleet.json"
    previous = '{"previous":true}\n'
    destination.write_text(previous, encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "backend.loadtests.external_pi_fleet_core.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="replace failed"):
        publish_fleet_report(report, destination, tmp_path)
    assert destination.read_text(encoding="utf-8") == previous


def test_fleet_locust_adapter_import_is_quiet(capsys, recwarn):
    if importlib.util.find_spec("locust") is None:
        return

    importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert not recwarn, [str(warning.message) for warning in recwarn]


def test_durable_locust_specs_start_every_user_immediately_without_queue():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    functional = adapter.build_durable_user_specs("32-functional-turns")
    admission = adapter.build_durable_user_specs("100-immediate-admission")

    assert [item.ordinal for item in functional] == list(range(32))
    assert Counter(item.workload for item in functional) == Counter(
        {"no_tool": 16, "read": 8, "bash": 8}
    )
    assert [item.ordinal for item in admission] == list(range(100))
    assert {item.workload for item in admission} == {"admission_stream"}
    assert all(item.arrival_delay_ms == 0 for item in functional + admission)
    assert all(item.application_queue is False for item in functional + admission)


def test_durable_locust_measurement_requires_content_free_typed_outcomes():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="bash",
        outcome="completed",
        ttft_ms=125,
        completion_ms=2_500,
        reconnects=1,
        reconnect_successes=1,
        model_starts=1,
        operation_start_ids=("op-0001", "op-0002"),
        queued_states=0,
        stale_mutations=0,
        duplicate_turns=0,
        terminal_cause="completed",
        failure_code=None,
    )

    assert observation.ttft_ms == 125
    assert observation.terminal_cause == "completed"
    assert observation.operation_start_count == 2
    assert observation.duplicate_operation_start_count == 0
    secret = "TOP_SECRET_PROMPT"
    with pytest.raises(FleetRunRefused) as exc:
        adapter.build_durable_observation(
            workload="bash",
            outcome="completed",
            ttft_ms=125,
            completion_ms=2_500,
            reconnects=0,
            reconnect_successes=0,
            model_starts=1,
            operation_start_ids=(),
            queued_states=0,
            stale_mutations=0,
            duplicate_turns=0,
            terminal_cause="completed",
            failure_code=None,
            prompt=secret,
        )
    assert secret not in str(exc.value)
    invalid = {
        "workload": "bash",
        "outcome": "completed",
        "ttft_ms": 125,
        "completion_ms": 2_500,
        "reconnects": 0,
        "reconnect_successes": 0,
        "model_starts": 1,
        "operation_start_ids": (),
        "queued_states": 0,
        "stale_mutations": 0,
        "duplicate_turns": 0,
        "terminal_cause": "completed",
        "failure_code": secret,
    }
    with pytest.raises(FleetRunRefused) as exc:
        adapter.build_durable_observation(**invalid)
    assert secret not in str(exc.value)


def test_durable_locust_measurement_accepts_typed_refusal_without_milestones():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="admission_stream",
        outcome="refused",
        ttft_ms=125,
        completion_ms=125,
        reconnects=0,
        reconnect_successes=0,
        model_starts=0,
        duplicate_turns=0,
        terminal_cause="refused",
        failure_code="chat_overload",
    )

    assert observation.outcome == "refused"
    assert observation.admission_ms is None
    assert observation.reconnect_ready_ms is None


def test_durable_locust_observation_counts_duplicate_operation_identity():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="bash",
        outcome="completed",
        ttft_ms=100,
        completion_ms=1_000,
        reconnects=0,
        reconnect_successes=0,
        model_starts=1,
        operation_start_ids=("op-0001", "op-0002", "op-0001"),
        queued_states=0,
        stale_mutations=0,
        duplicate_turns=0,
        terminal_cause="completed",
        failure_code=None,
    )

    assert observation.operation_start_count == 2
    assert observation.duplicate_operation_start_count == 1


@pytest.mark.parametrize(
    ("profile_name", "expected_users", "expected_mix", "sandboxes"),
    (
        (
            "32-functional-turns",
            32,
            Counter({"no_tool": 16, "read": 8, "bash": 8}),
            16,
        ),
        (
            "100-immediate-admission",
            100,
            Counter({"admission_stream": 100}),
            0,
        ),
    ),
)
def test_executable_durable_locust_runner_releases_exact_simultaneous_profile(
    profile_name, expected_users, expected_mix, sandboxes
):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    calls = []

    class Transport:
        def open_durable_stream(self, spec):
            calls.append(
                (
                    spec.ordinal,
                    spec.workload,
                    adapter._durable_barrier_arrivals,
                    spec.arrival_delay_ms,
                    spec.application_queue,
                )
            )
            operation_ids = (
                (f"op-{spec.ordinal:04d}-1", f"op-{spec.ordinal:04d}-2")
                if spec.workload == "bash"
                else ((f"op-{spec.ordinal:04d}-1",) if spec.workload == "read" else ())
            )
            return {
                "workload": spec.workload,
                "outcome": "completed",
                "ttft_ms": 100,
                "completion_ms": 1_000,
                "reconnects": 0,
                "reconnect_successes": 0,
                "model_starts": 1,
                "operation_start_ids": operation_ids,
                "queued_states": 0,
                "stale_mutations": 0,
                "duplicate_turns": 0,
                "terminal_cause": "completed",
                "failure_code": None,
            }

    report = adapter.run_local_durable_profile(
        profile_name=profile_name,
        transport=Transport(),
        resources=adapter.DurableRunResources(
            peak_memory_bytes=1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=expected_users,
            peak_active_external_workers=4,
            peak_active_sandboxes=sandboxes,
        ),
        lifecycle_source=_LifecycleSource(
            _FUNCTIONAL_MODAL if profile_name == "32-functional-turns" else _NO_MODAL
        ),
        modal_rate=_MODAL_RATE,
        timeout_seconds=10.0,
    )

    assert report.passed is True
    assert len(calls) == expected_users
    assert Counter(workload for _, workload, *_ in calls) == expected_mix
    assert {arrivals for _, _, arrivals, _, _ in calls} == {expected_users}
    assert all(delay == 0 and queued is False for *_, delay, queued in calls)
    assert report.operation_start_count == (24 if expected_users == 32 else 0)
    assert report.duplicate_operation_start_count == 0


def test_live_durable_runner_constructs_real_transport_and_accepts_no_fake(monkeypatch):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    captured = {}

    def run_observations(**kwargs):
        captured.update(kwargs)
        return ()

    monkeypatch.setattr(adapter, "_run_durable_observations", run_observations)
    config = DurableChatTransportConfig(
        base_url="https://staging.paperswithcode.co",
        synthetic_cookies=("signed-cookie",),
        initial_model="gpt-5.6-luna@openai",
        qualification_run_id="run",
        admin_token="a" * 32,
    )

    scope_id = uuid.uuid4()
    result = adapter.run_live_durable_profile(
        profile_name="32-functional-turns",
        transport_config=config,
        resources=adapter.DurableRunResources(1, 2 * 1024**3, 1.0, 32, 4, 0),
        qualification_scope_id=scope_id,
    )

    assert result.profile_name == "32-functional-turns"
    assert type(captured["transport"]) is HttpSSEDurableChatTransport
    assert "/v1/shadow" not in repr(captured)


def test_guarded_live_operator_delegates_run_only_to_live_runner(monkeypatch):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
    )

    profile = resolve_durable_profile("32-functional-turns")
    resources = adapter.DurableRunResources(1, 2 * 1024**3, 1.0, 32, 4, 0)
    control = SimpleNamespace(
        run_resources=lambda selected: resources,
        environment=lambda: SimpleNamespace(target_release="0123456789ab-staging"),
    )
    captured = {}

    def run_live(**kwargs):
        captured.update(kwargs)
        return "profile-report"

    monkeypatch.setattr(adapter, "run_live_durable_profile", run_live)
    operator = GuardedLiveDurableOperator(
        control_plane=control,
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    scope_id = uuid.uuid4()
    operator.evidence_source = SimpleNamespace(
        begin_scope=lambda _profile: {
            "scope_id": scope_id,
            "app_release_id": "0123456789ab-staging",
        }
    )

    assert operator.run_profile(profile) == "profile-report"
    assert captured["profile_name"] == profile.name
    assert captured["resources"] is resources
    assert captured["qualification_scope_id"] == scope_id


def test_guarded_live_teardown_requires_and_evicts_only_the_exact_scope():
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
        QualificationRefused,
    )

    profile = resolve_durable_profile("32-functional-turns")
    operator = GuardedLiveDurableOperator(
        control_plane=SimpleNamespace(),
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    exact_scope = uuid.uuid4()
    calls = []
    operator._scopes[profile.name] = exact_scope
    operator.evidence_source = SimpleNamespace(
        teardown=lambda scope_id: calls.append(scope_id)
    )

    with pytest.raises(QualificationRefused, match="qualification_scope_invalid"):
        operator.teardown_profile(profile, uuid.uuid4())
    operator.teardown_profile(profile, exact_scope)
    assert calls == [exact_scope]


def test_guarded_live_finalization_attests_static_rate_inside_closed_scope_window(
    monkeypatch,
):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
    )

    scope_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(
        adapter,
        "finalize_live_durable_profile",
        lambda measurement, **kwargs: captured.update(kwargs)
        or SimpleNamespace(modal_estimated_cost_microusd=1),
    )
    operator = GuardedLiveDurableOperator(
        control_plane=SimpleNamespace(
            environment=lambda: SimpleNamespace(target_release="0123456789ab-staging"),
            protected_runtime_evidence=lambda _profile: {
                "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "25",
                "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
                "PWC_RELEASE_ID": "0123456789ab-staging",
            },
        ),
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    operator.evidence_source = SimpleNamespace(
        collect=lambda _scope_id: SimpleNamespace(
            window_started_at_ms=10,
            window_ended_at_ms=20,
        )
    )

    result = operator.finalize_profile(
        resolve_durable_profile("32-functional-turns"),
        SimpleNamespace(qualification_scope_id=scope_id),
    )

    assert result.modal_estimated_cost_microusd == 1
    assert captured["modal_rate"].attested_at_ms == 20


def test_fleet_locust_requires_one_local_exact_configured_user_runner(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")
    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )
    environment = SimpleNamespace(
        runner=object(),
        parsed_options=SimpleNamespace(num_users=100, spawn_rate=100.0),
        host=None,
    )
    with pytest.raises(FleetRunRefused, match="one local Locust runner"):
        adapter._start(environment)

    environment.runner = object.__new__(adapter.LocalRunner)
    environment.runner.greenlet = None
    for users, spawn_rate, host in (
        (99, 100.0, None),
        (100, 99.0, None),
        (100, 100.0, "https://staging.paperswithcode.co"),
    ):
        environment.parsed_options = SimpleNamespace(
            num_users=users, spawn_rate=spawn_rate
        )
        environment.host = host
        with pytest.raises(FleetRunRefused, match="exact configured|must not accept"):
            adapter._start(environment)


def test_fleet_locust_routes_each_one_shot_user_directly_without_proxy_or_redirect(
    monkeypatch,
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")

    class Response:
        status_code = 503

        def __init__(self):
            self.request_meta = {"name": "external_pi.error"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def json(self):
            return {"code": "shadow_capacity"}

        def success(self):
            return None

        def failure(self, _message):
            return None

    class Client:
        def __init__(self):
            self.trust_env = True
            self.proxies = {"http": "http://proxy.invalid"}
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return Response()

    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )
    adapter._barrier_arrivals = 98
    adapter._arrival_gate.set()
    monkeypatch.setattr(adapter, "_ordinals", iter((0, 5)))
    client = Client()
    for _ in range(2):
        user = object.__new__(adapter.ExternalPiFleetUser)
        user.client = client
        user.on_start()
        with pytest.raises(adapter.StopUser):
            user.run_once()

    assert client.trust_env is False
    assert client.proxies == {}
    assert [call["url"] for call in client.calls] == [
        "http://127.0.0.1:8780/v1/shadow",
        "http://127.0.0.1:8780/v1/shadow",
    ]
    assert all(call["allow_redirects"] is False for call in client.calls)
    assert all("response" not in call and "body" not in call for call in client.calls)
    assert len(adapter.fleet_round_result().observations) == 2


@pytest.mark.parametrize(
    ("shape_name", "expected_users", "expected_per_worker"),
    (("5x32", 100, 20), ("2x32", 32, 16)),
)
def test_fleet_local_runner_completes_exact_balanced_profile_over_loopback(
    shape_name: str, expected_users: int, expected_per_worker: int
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    counts = Counter()
    state = {"in_flight": 0, "peak": 0}
    arrivals_at_request = []
    aggregate_gate = threading.Event()
    aggregate_lock = threading.Lock()
    servers = []
    threads = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            with aggregate_lock:
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
                arrivals_at_request.append(adapter._barrier_arrivals)
                if state["in_flight"] == expected_users:
                    aggregate_gate.set()
            try:
                if not aggregate_gate.wait(timeout=10):
                    self.send_error(503)
                    return
                length = int(self.headers["Content-Length"])
                request = json.loads(self.rfile.read(length))
                with aggregate_lock:
                    counts[self.server.server_port] += 1
                response = {
                    "type": "shadow_projection",
                    "protocol_version": 1,
                    "request_id": request["request_id"],
                    "chat_session_id": request["chat_session_id"],
                    "agent_session_id": request["agent_session_id"],
                    "current_leaf_id": request["current_leaf_id"],
                    "entry_count": len(request["transcript_entries"]),
                    "transcript_sha256": request["expected_transcript_sha256"],
                    "prompt_sha256": request["expected_prompt_sha256"],
                    "tool_names_sha256": request["expected_tool_names_sha256"],
                }
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                with aggregate_lock:
                    state["in_flight"] -= 1

        def log_message(self, *_args):
            return None

    class HighBacklogServer(ThreadingHTTPServer):
        request_queue_size = 128

    try:
        shape = resolve_fleet_shape(shape_name)
        for replica in shape.replicas:
            port = replica.port
            server = HighBacklogServer(("127.0.0.1", port), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append(server)
            threads.append(thread)
        result = adapter.run_local_fleet_round(
            replicas=shape.replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            expected_users=expected_users,
            timeout_seconds=20,
        )
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)

    assert len(result.observations) == expected_users
    assert all(item.classification == "compatible" for item in result.observations)
    assert result.protocol_errors == result.transport_errors == 0
    assert state["peak"] == expected_users
    assert set(arrivals_at_request) == {expected_users}
    assert counts == Counter(
        {replica.port: expected_per_worker for replica in shape.replicas}
    )


def test_fleet_local_runner_validates_before_start(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    started = False

    def reject(_environment):
        raise FleetRunRefused("runner invariant")

    def start(*_args, **_kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(adapter, "_validate_runner", reject)
    monkeypatch.setattr(adapter.LocalRunner, "start", start)
    with pytest.raises(FleetRunRefused, match="runner invariant"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
        )
    assert started is False


def test_fleet_local_runner_timeout_refuses_incomplete_real_round():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    timestamps = iter((0.0, 31.0))

    with pytest.raises(FleetRunRefused, match="round timed out"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=30,
            monotonic=lambda: next(timestamps),
        )


def test_fleet_local_runner_barrier_timeout_releases_without_requests():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    with pytest.raises(FleetRunRefused, match="barrier.*timed out"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=5,
            barrier_timeout_seconds=0.001,
        )

    assert adapter._arrival_gate.is_set()
    assert adapter.fleet_round_result().observations == ()


def test_fleet_local_runner_abort_releases_barrier_and_cannot_pass():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    with pytest.raises(FleetRunRefused, match="aborted"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=5,
            abort_requested=lambda: True,
        )

    assert adapter._arrival_gate.is_set()
    assert len(adapter.fleet_round_result().observations) < 100


class _FleetOperator:
    runtime_id = "external-pi-runtime-1"
    owner_id = "test-owner"

    def __init__(self, *, refuse=()):
        self.refuse = set(refuse)
        self.events = []

    def revalidate(self, shape, active):
        self.events.append(
            ("revalidate", shape.name, tuple(item.worker_id for item in active))
        )

    def resource_preflight(self, shape):
        self.events.append(("resource_preflight", shape.name))
        if shape.name in self.refuse:
            return ResourcePreflight("resource_refused", 1024**3, 20.0, 80.0)
        return _passed_resource_preflight()

    def resolve(self, shape, index):
        replica = FleetReplica(
            QUALIFICATION_WORKER_IDS[index], QUALIFICATION_PORTS[index]
        )
        return SimpleNamespace(
            index=index,
            worker_id=replica.worker_id,
            port=replica.port,
            maximum_sessions=shape.sessions_per_worker,
            supervisor_unit=QUALIFICATION_SUPERVISOR_UNITS[index],
            worker_unit=QUALIFICATION_WORKER_UNITS[index],
            status_path=Path(f"/tmp/{replica.worker_id}.json"),
        )

    def start(self, resolved):
        self.events.append(("start", resolved.worker_id))

    def wait_ready(self, resolved):
        generation = resolved.index + 10
        self.events.append(("ready", resolved.worker_id, generation))
        return generation

    def prepare_round(self):
        self.events.append(("prepare_round", None))

    def run_round(
        self,
        name,
        workers,
        *,
        expected_users=100,
        abort_requested=lambda: False,
    ):
        self.events.append(
            (
                "round",
                name,
                tuple(worker.worker_id for worker in workers),
                expected_users,
            )
        )
        return _round(name, expected_users=expected_users)

    def sample_resources(self, shape):
        self.events.append(("resources", shape.name))
        return _resources(shape.name)

    def cleanup(self, resolved, generation):
        self.events.append(("cleanup", resolved.worker_id, generation))
        return SimpleNamespace(
            registry_offline=True,
            supervisors_stopped_before_workers=True,
            units_removed=True,
            status_files_removed=True,
            ports_free=True,
            processes_gone=True,
        )

    def cleanup_postconditions(self, _shape):
        return _cleanup()

    def set_owner(self, owner_id):
        self.owner_id = owner_id

    def owned_units(self, _resolved):
        return ()

    def recovery_postconditions(self, resolved, owned_units):
        cleaned = any(
            event[0] == "cleanup" and event[1] == resolved.worker_id
            for event in self.events
        )
        cleanup = (
            _cleanup()
            if cleaned or not owned_units
            else _cleanup(units_removed=False, processes_gone=False)
        )
        return cleanup, (() if cleanup.passed else owned_units)


def test_guarded_round_prepares_runtime_before_starting_resource_sampler():
    from backend.scripts.qualify_external_pi_fleet import _run_guarded_round

    class OrderedOperator(_FleetOperator):
        def prepare_round(self):
            assert threading.current_thread() is threading.main_thread()
            super().prepare_round()

        def sample_resources(self, shape):
            assert ("prepare_round", None) in self.events
            return super().sample_resources(shape)

    operator = OrderedOperator()
    shape = resolve_fleet_shape("2x32")
    workers = tuple(
        WorkerEvidence(
            worker_id=replica.worker_id,
            port=replica.port,
            generation=1,
            maximum_sessions=shape.sessions_per_worker,
        )
        for replica in shape.replicas
    )

    report, samples = _run_guarded_round(operator, shape, "healthy", workers)

    assert report.passed is True
    assert samples
    assert operator.events.index(("prepare_round", None)) < next(
        index for index, event in enumerate(operator.events) if event[0] == "resources"
    )


def test_controller_runs_shapes_sequentially_healthy_then_exact_generation_loss(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator(refuse={"16x8"})
    report_path = tmp_path / "fleet.json"
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=report_path,
        report_root=tmp_path,
        geteuid=lambda: 0,
    )

    assert [shape.status for shape in report.shapes] == [
        "completed",
        "completed",
        "resource_refused",
    ]
    assert [shape.removed_worker_id for shape in report.shapes[:2]] == [
        "staging-qualification-00",
        "staging-qualification-00",
    ]
    assert [event[:2] for event in operator.events if event[0] == "round"] == [
        ("round", "healthy"),
        ("round", "survivor"),
        ("round", "healthy"),
        ("round", "survivor"),
    ]
    assert ("cleanup", "staging-qualification-00", 10) in operator.events
    second_shape_preflight = operator.events.index(("resource_preflight", "8x16"))
    first_shape_last_cleanup = max(
        index
        for index, event in enumerate(operator.events)
        if index < second_shape_preflight and event[0] == "cleanup"
    )
    assert first_shape_last_cleanup < second_shape_preflight
    assert any(event[0] == "resources" for event in operator.events)
    transition_indices = [
        index
        for index, event in enumerate(operator.events)
        if event[0] in {"start", "ready", "round", "cleanup"}
    ]
    revalidation_indices = [
        index for index, event in enumerate(operator.events) if event[0] == "revalidate"
    ]
    for index in transition_indices:
        assert any(candidate < index for candidate in revalidation_indices)
        assert any(candidate > index for candidate in revalidation_indices)
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_binds_capacity_profile_rounds_to_exact_expected_users(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator()
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32",),
        geteuid=lambda: 0,
    )

    assert report.shapes[0].expected_users == 32
    assert [event[3] for event in operator.events if event[0] == "round"] == [
        32,
        32,
    ]


def test_capacity_controller_stops_at_first_resource_refusal(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator(refuse={"4x16"})
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32", "4x16", "3x32"),
        stop_on_nonpassing_shape=True,
        geteuid=lambda: 0,
    )

    assert [shape.shape for shape in report.shapes] == ["2x32", "4x16"]
    assert not any(event[1] == "3x32" for event in operator.events)


def test_capacity_controller_stops_at_first_failed_shape(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import (
        qualification_exit_code,
        run_fleet_controller,
    )

    class FailedVerdictOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            report = super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )
            if len(workers) in {3, 4} and expected_users == 48:
                return report.model_copy(
                    update={"forbidden_activity": ForbiddenActivity(model_calls=1)}
                )
            return report

    operator = FailedVerdictOperator()
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32", "4x16", "3x32"),
        stop_on_nonpassing_shape=True,
        geteuid=lambda: 0,
    )

    assert [shape.shape for shape in report.shapes] == ["2x32", "4x16"]
    assert report.shapes[-1].overall_passed is False
    assert qualification_exit_code(report) == 1
    assert not any(event[1] == "3x32" for event in operator.events)


def test_controller_always_cleans_every_observed_generation_on_round_failure(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class FailingOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )
            raise RuntimeError("protected response body")

    operator = FailingOperator()
    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="protected response body"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["release_id"] == "0123456789ab-staging"
    assert len(retained["replicas"]) == 5
    assert [item["generation"] for item in retained["replicas"]] == [10, 11, 12, 13, 14]
    assert all(item["unresolved_units"] == [] for item in retained["replicas"])
    assert retained["cleanup_complete"] is True
    assert "protected response body" not in report_path.read_text(encoding="utf-8")
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_recovery_reports_allowlisted_content_free_failure_reason(
    tmp_path: Path,
):
    from backend.loadtests.external_pi_fleet_core import FleetRecoveryReport
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    secret = "protected_response_body_token"

    class FailingOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            raise RuntimeError(secret)

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match=secret):
        run_fleet_controller(
            FailingOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"
    assert secret not in retained_text

    validation_payload = {
        key: value for key, value in retained.items() if key != "cleanup_complete"
    }
    for field in ("failure_stage", "failure_code"):
        invalid = dict(validation_payload)
        invalid[field] = "protected_response_body_token"
        with pytest.raises(ValidationError):
            FleetRecoveryReport.model_validate_json(json.dumps(invalid))

    mismatched = dict(validation_payload)
    mismatched["failure_code"] = "cleanup_failed"
    with pytest.raises(ValidationError):
        FleetRecoveryReport.model_validate_json(json.dumps(mismatched))


def test_controller_preserves_round_failure_when_sampler_fails_later(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class OrderedFailureOperator(_FleetOperator):
        guard_started = threading.Event()
        round_failed = threading.Event()

        def prepare_round(self):
            self.guard_started.set()
            return super().prepare_round()

        def sample_resources(self, shape):
            if (
                self.guard_started.is_set()
                and threading.current_thread() is not threading.main_thread()
            ):
                assert self.round_failed.wait(timeout=1)
                raise RuntimeError("later sampler detail")
            return super().sample_resources(shape)

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.round_failed.set()
            raise RuntimeError("first round detail")

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="first round detail"):
        run_fleet_controller(
            OrderedFailureOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"


def test_controller_publishes_conservative_recovery_when_inspection_fails(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class InspectionFailureOperator(_FleetOperator):
        def run_round(self, name, workers, *, expected_users, abort_requested):
            raise RuntimeError("first round detail")

        def recovery_postconditions(self, resolved, owned_units):
            raise RuntimeError("later cleanup inspection detail")

    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="first round detail"):
        run_fleet_controller(
            InspectionFailureOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["report_type"] == "recovery"
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"
    assert retained["cleanup_complete"] is False
    assert len(retained["replicas"]) == 16
    assert all(not item["cleanup"]["units_removed"] for item in retained["replicas"])
    assert all(len(item["unresolved_units"]) == 2 for item in retained["replicas"])
    assert all(
        item["unresolved_units"] == item["owned_units"]
        for item in retained["replicas"][:2]
    )
    assert all(not item["owned_units"] for item in retained["replicas"][2:])
    assert "first round detail" not in retained_text
    assert "later cleanup inspection detail" not in retained_text


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    (
        ("revalidation", "revalidation", "revalidation_failed"),
        ("resource_sampling", "resource_sampling", "resource_sampling_failed"),
        ("resource_threshold", "resource_threshold", "resource_threshold_crossed"),
        ("replica_lifecycle", "replica_lifecycle", "replica_lifecycle_failed"),
        ("cleanup", "cleanup", "cleanup_failed"),
    ),
)
def test_controller_recovery_distinguishes_failure_stage_without_error_text(
    tmp_path: Path,
    failure: str,
    expected_stage: str,
    expected_code: str,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    secret = "protected_failure_detail"

    class FailingOperator(_FleetOperator):
        def revalidate(self, shape, active):
            if failure == "revalidation":
                raise RuntimeError(secret)
            return super().revalidate(shape, active)

        def sample_resources(self, shape):
            if failure == "resource_sampling":
                raise RuntimeError(secret)
            evidence = super().sample_resources(shape)
            if failure == "resource_threshold":
                return evidence.model_copy(update={"peak_cpu_percent": 80.0})
            return evidence

        def start(self, resolved):
            if failure == "replica_lifecycle":
                raise RuntimeError(secret)
            return super().start(resolved)

        def cleanup(self, resolved, generation):
            if failure == "cleanup":
                raise RuntimeError(secret)
            return super().cleanup(resolved, generation)

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError):
        run_fleet_controller(
            FailingOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["failure_stage"] == expected_stage
    assert retained["failure_code"] == expected_code
    assert secret not in retained_text


def test_initial_eighty_percent_cpu_checkpoint_retains_clean_threshold_recovery(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ThresholdOperator(_FleetOperator):
        def sample_resources(self, shape):
            return (
                super()
                .sample_resources(shape)
                .model_copy(update={"peak_cpu_percent": 80.0})
            )

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="resource guard crossed"):
        run_fleet_controller(
            ThresholdOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["failure_stage"] == "resource_threshold"
    assert retained["failure_code"] == "resource_threshold_crossed"
    assert retained["replicas"] == []
    assert retained["cleanup_complete"] is True


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    (
        ("worker_status", "worker_status", "worker_status_failed"),
        ("locust_round", "locust_round", "locust_round_failed"),
        ("counter", "counter", "counter_mismatch"),
    ),
)
def test_system_round_classifies_only_allowlisted_failure_reason(
    tmp_path: Path,
    failure: str,
    expected_stage: str,
    expected_code: str,
):
    from backend.scripts.qualify_external_pi_fleet import (
        SystemFleetOperator,
        _FleetOperationFailure,
    )

    prompt = tmp_path / "prompt.txt"
    prompt.write_text("synthetic", encoding="utf-8")
    operator = object.__new__(SystemFleetOperator)
    operator._prompt_path = prompt
    operator.environ = {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "protected"}
    status = SimpleNamespace(operation_counters=SimpleNamespace(shadow_requests=0))
    if failure == "worker_status":
        operator._worker_status = lambda _worker: (_ for _ in ()).throw(
            RuntimeError("protected worker detail")
        )
    else:
        operator._worker_status = lambda _worker: status
    operator._validate_worker_status = lambda _worker, _status: None
    if failure == "locust_round":
        operator._round_runner = lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("protected Locust detail")
        )
    else:
        operator._round_runner = lambda **_kwargs: SimpleNamespace(
            observations=(), protocol_errors=0, transport_errors=0
        )
    worker = WorkerEvidence(
        worker_id="staging-qualification-00",
        port=8780,
        generation=1,
        maximum_sessions=32,
    )

    with pytest.raises(_FleetOperationFailure) as raised:
        operator.run_round(
            "healthy",
            (worker,),
            expected_users=1,
            abort_requested=lambda: False,
        )

    assert raised.value.stage == expected_stage
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("shape_names", "failure_round", "expected_workers"),
    (
        (("5x32", "8x16"), 2, 8),
        (("5x32", "8x16", "16x8"), 3, 16),
    ),
)
def test_later_shape_failure_publishes_only_unique_current_shape_recovery(
    tmp_path: Path,
    shape_names,
    failure_round,
    expected_workers,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SecondShapeFailure(_FleetOperator):
        healthy_rounds = 0

        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            if name == "healthy":
                self.healthy_rounds += 1
                if self.healthy_rounds == failure_round:
                    raise RuntimeError("later shape failed")
            return super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="later shape failed"):
        run_fleet_controller(
            SecondShapeFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=shape_names,
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert [item["worker_id"] for item in retained["replicas"]] == list(
        QUALIFICATION_WORKER_IDS[:expected_workers]
    )
    assert len({item["worker_id"] for item in retained["replicas"]}) == expected_workers


def test_first_checkpoint_foreign_unit_and_port_are_retained_as_recovery(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ForeignPreflight(_FleetOperator):
        def revalidate(self, _shape, _active):
            raise FleetRunRefused("foreign reserved slot")

        def recovery_postconditions(self, resolved, _owned_units):
            if resolved.index == 6:
                return _cleanup(units_removed=False, processes_gone=False), (
                    resolved.supervisor_unit,
                )
            if resolved.index == 7:
                return _cleanup(ports_free=False, processes_gone=False), ()
            return _cleanup(), ()

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="foreign reserved slot"):
        run_fleet_controller(
            ForeignPreflight(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert [item["worker_id"] for item in retained["replicas"]] == [
        "staging-qualification-06",
        "staging-qualification-07",
    ]
    assert retained["replicas"][0]["unresolved_units"] == [
        QUALIFICATION_SUPERVISOR_UNITS[6]
    ]
    assert retained["replicas"][1]["cleanup"]["ports_free"] is False


@pytest.mark.parametrize("pointer_failure", ("current missing", "current changed"))
def test_partial_attempt_recovery_uses_cached_descriptors_after_pointer_drift(
    tmp_path: Path,
    pointer_failure: str,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PointerDrift(_FleetOperator):
        pointer_valid = True

        def resolve(self, shape, index):
            if not self.pointer_valid:
                raise FleetRunRefused(pointer_failure)
            return super().resolve(shape, index)

        def start(self, resolved):
            self.pointer_valid = False
            raise RuntimeError("protected partial-start detail")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="protected partial-start detail"):
        run_fleet_controller(
            PointerDrift(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
    assert len(retained["replicas"]) == 1
    assert retained["replicas"][0]["worker_id"] == "staging-qualification-00"
    assert retained["replicas"][0]["port"] == 8780
    assert retained["replicas"][0]["supervisor_unit"] == (
        "paperswithcode-staging-external-pi-qualification@00.service"
    )
    assert retained["replicas"][0]["worker_unit"] == (
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    )
    assert pointer_failure not in retained_text
    assert "protected partial-start detail" not in retained_text
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_retains_exact_unresolved_worker_only_partial_start(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PartialStartFailure(_FleetOperator):
        def start(self, resolved):
            raise RuntimeError("partial start")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

        def cleanup(self, _resolved, _generation):
            raise RuntimeError("cleanup unavailable")

    operator = PartialStartFailure()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="partial start"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert len(retained["replicas"]) == 1
    replica = retained["replicas"][0]
    assert replica["generation"] is None
    assert replica["owned_units"] == [
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    ]
    assert replica["unresolved_units"] == replica["owned_units"]


def test_controller_cleans_started_replica_when_readiness_has_no_generation(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ReadinessFailure(_FleetOperator):
        def wait_ready(self, resolved):
            if resolved.index == 1:
                raise RuntimeError("readiness failed")
            return super().wait_ready(resolved)

    operator = ReadinessFailure()
    with pytest.raises(RuntimeError, match="readiness failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", None),
    ]


def test_controller_cleanup_continues_when_pre_cleanup_revalidation_fails(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SafetyFailure(_FleetOperator):
        unsafe = False

        def revalidate(self, shape, active):
            if self.unsafe:
                raise FleetRunRefused("safety changed")
            super().revalidate(shape, active)

        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            self.unsafe = True
            raise RuntimeError("round failed")

    operator = SafetyFailure()
    with pytest.raises(RuntimeError, match="round failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]


def test_controller_refuses_non_root_before_operator_actions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator()
    with pytest.raises(FleetRunRefused, match="root operator"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            geteuid=lambda: 1000,
        )
    assert operator.events == []


def test_controller_signal_context_converts_interrupt_and_restores_handlers():
    from backend.scripts.qualify_external_pi_fleet import (
        FleetQualificationInterrupted,
        qualification_signal_context,
    )

    previous = {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    }
    with pytest.raises(FleetQualificationInterrupted), qualification_signal_context():
        signal.raise_signal(signal.SIGTERM)
    assert {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    } == previous


def test_system_operator_revalidates_live_staging_and_exact_listener_state(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    staging.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    blue.joinpath("release").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    status_root = tmp_path / "run/external-pi"
    status_root.mkdir(parents=True)
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners: dict[int, tuple[str, ...]] = {}
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class LiveResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    unit_states = {"supervisor": "active", "worker": "active"}
    qualification_active = False

    def systemctl(command, **_kwargs):
        nonlocal qualification_active
        if "qualification" in command[-1]:
            if qualification_active and command[-1].endswith("@00.service"):
                role = (
                    "worker" if "qualification-worker" in command[-1] else "supervisor"
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "LoadState=loaded\nActiveState=active\n"
                    "Description=Papers With Code staging external Pi qualification "
                    f"{role} 00 owner {operator.owner_id}\n",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                "LoadState=not-found\nActiveState=inactive\nDescription=\n",
            )
        state = (
            unit_states["worker"]
            if "external-pi-worker" in command[-1]
            else unit_states["supervisor"]
        )
        return subprocess.CompletedProcess(command, 0, state + "\n")

    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: LiveResponse(),
        runner=systemctl,
    )
    shape = resolve_fleet_shape("5x32")

    operator.revalidate(shape, ())
    listeners[8780] = ("127.0.0.1",)
    qualification_active = True
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    live_status["operation_counters"]["provider_calls"] = 1
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    live_status["operation_counters"]["provider_calls"] = 0

    unit_states["supervisor"] = "failed"
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    unit_states["supervisor"] = "active"

    listeners[8780] = ("0.0.0.0",)
    with pytest.raises(FleetRunRefused, match="loopback"):
        operator.revalidate(shape, active)
    listeners[8780] = ("127.0.0.1",)
    environ["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] = "true"
    with pytest.raises(FleetRunRefused, match="disabled"):
        operator.revalidate(shape, active)


def test_system_operator_rejects_stale_and_foreign_exact_qualification_units(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    blue.joinpath("release").symlink_to(release)
    status_root = tmp_path / "status"
    status_root.mkdir()
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    qualification = {}

    def systemctl(command, **_kwargs):
        unit = command[-1]
        if "qualification" not in unit:
            values = {
                "LoadState": "loaded",
                "ActiveState": "active",
                "Description": "live",
            }
        else:
            values = qualification.get(
                unit,
                {
                    "LoadState": "not-found",
                    "ActiveState": "inactive",
                    "Description": "",
                },
            )
        if "--value" in command:
            return subprocess.CompletedProcess(command, 0, values["ActiveState"] + "\n")
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        )

    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: Response(),
        runner=systemctl,
    )
    operator.owner_id = "test-owner"
    shape = resolve_fleet_shape("5x32")
    supervisor = qualification_unit_names(shape)[0]
    worker = qualification_unit_names(shape)[shape.worker_count]

    qualification[QUALIFICATION_SUPERVISOR_UNITS[6]] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": "foreign reserved slot",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())
    del qualification[QUALIFICATION_SUPERVISOR_UNITS[6]]

    listeners[QUALIFICATION_PORTS[6]] = ("127.0.0.1",)
    with pytest.raises(FleetRunRefused, match="inactive qualification ports"):
        operator.revalidate(shape, ())
    listeners.clear()

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "failed",
        "Description": "foreign",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification supervisor 00 "
            "owner test-owner"
        ),
    }
    qualification[worker] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification worker 00 "
            "owner test-owner"
        ),
    }
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    qualification[worker]["Description"] = "foreign-owner"
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, active)


def test_resource_refused_shape_uses_observed_cleanup_postconditions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class RefusedOperator(_FleetOperator):
        def cleanup_postconditions(self, _shape):
            return _cleanup(units_removed=False, processes_gone=False)

    operator = RefusedOperator(refuse={"16x8"})
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "fleet.json",
        report_root=tmp_path,
        shape_names=("16x8",),
        geteuid=lambda: 0,
    )

    assert report.shapes[0].status == "resource_refused"
    assert report.shapes[0].cleanup.units_removed is False
    assert report.shapes[0].cleanup.processes_gone is False


def test_system_recovery_does_not_report_foreign_exact_unit_as_removed(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.listener_hosts = lambda _port: ()
    resolved = SimpleNamespace(
        supervisor_unit=("paperswithcode-staging-external-pi-qualification@00.service"),
        worker_unit=(
            "paperswithcode-staging-external-pi-qualification-worker@00.service"
        ),
        status_path=tmp_path / "missing.json",
        release_id="0123456789ab-staging",
        worker_id="staging-qualification-00",
        port=8780,
    )
    operator._unit_metadata = lambda unit: (
        ("loaded", "active", "foreign")
        if unit == resolved.supervisor_unit
        else ("not-found", "inactive", "")
    )

    cleanup, unresolved = operator.recovery_postconditions(resolved, ())

    assert unresolved == (resolved.supervisor_unit,)
    assert cleanup.units_removed is False
    assert cleanup.registry_offline is False
    assert cleanup.passed is False


def test_system_refusal_cleanup_postconditions_inspect_all_reserved_slots(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    units = []
    ports = []
    operator = object.__new__(SystemFleetOperator)
    operator.qualification_status_root = tmp_path
    operator._unit_metadata = lambda unit: (
        units.append(unit) or ("not-found", "inactive", "")
    )
    operator.listener_hosts = lambda port: ports.append(port) or ()

    cleanup = operator.cleanup_postconditions(resolve_fleet_shape("5x32"))

    assert cleanup.passed is True
    assert units == list(QUALIFICATION_SUPERVISOR_UNITS + QUALIFICATION_WORKER_UNITS)
    assert ports == list(QUALIFICATION_PORTS)


def test_system_resource_preflight_scales_worker_memory_by_session_limit(monkeypatch):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.app_root = Path("/srv/paperswithcode")
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=False: Path(
            "/srv/paperswithcode/environments/staging/slots/blue"
        ),
    )

    def properties(unit, *_names):
        return {"MemoryCurrent": 100 * 1024**2 if "worker" in unit else 50 * 1024**2}

    operator._systemctl_properties = properties
    operator._mem_available_bytes = lambda: 4 * 1024**3
    slept = []
    cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(cpu)
    operator.sleep = lambda seconds: slept.append(seconds)

    preflight = operator.resource_preflight(resolve_fleet_shape("5x32"))

    assert slept == [1.0]
    assert preflight.observed_cpu_percent == 80.0
    assert preflight.status == "resource_refused"
    assert preflight.projected_mem_available_bytes == 4 * 1024**3 - 2250 * 1024**2


def test_system_resource_samples_host_cpu_over_one_second():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator._unit_cpu_state = {}
    operator._systemctl_properties = lambda _unit, *_names: {
        "MemoryPeak": 1,
        "CPUUsageNSec": 1,
        "TasksCurrent": 1,
    }
    operator._mem_available_bytes = lambda: 2 * 1024**3
    cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)

    evidence = operator.sample_resources(resolve_fleet_shape("2x32"))

    assert slept == [1.0]
    assert evidence.peak_cpu_percent == 80.0


def test_system_resource_sample_below_eighty_percent_remains_safe():
    from backend.scripts.qualify_external_pi_fleet import (
        SystemFleetOperator,
        _resources_safe,
    )

    operator = object.__new__(SystemFleetOperator)
    operator._unit_cpu_state = {}
    operator._systemctl_properties = lambda _unit, *_names: {
        "MemoryPeak": 1,
        "CPUUsageNSec": 1,
        "TasksCurrent": 1,
    }
    operator._mem_available_bytes = lambda: 2 * 1024**3
    cpu = iter(((100, 80), (200, 101)))
    operator._read_host_cpu = lambda: next(cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)

    evidence = operator.sample_resources(resolve_fleet_shape("2x32"))

    assert slept == [1.0]
    assert evidence.peak_cpu_percent == 79.0
    assert _resources_safe(evidence) is True


def test_system_host_cpu_sampler_rejects_sub_one_second_window():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)

    with pytest.raises(FleetRunRefused, match="sample interval"):
        operator._sample_host_cpu_percent(0.999)


def test_system_resource_adapter_parses_only_requested_numeric_properties():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    commands = []

    def systemctl(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "MemoryPeak=1048576\nCPUUsageNSec=invalid\nTasksCurrent=7\nIgnored=9\n",
        )

    operator = object.__new__(SystemFleetOperator)
    operator.runner = systemctl
    values = operator._systemctl_properties(
        "qualification-worker@00.service",
        "MemoryPeak",
        "CPUUsageNSec",
        "TasksCurrent",
    )

    assert values == {
        "MemoryPeak": 1048576,
        "CPUUsageNSec": 0,
        "TasksCurrent": 7,
    }
    assert commands == [
        [
            "systemctl",
            "show",
            "--property=MemoryPeak",
            "--property=CPUUsageNSec",
            "--property=TasksCurrent",
            "qualification-worker@00.service",
        ]
    ]


def test_system_sample_resources_aggregates_injected_exact_unit_and_host_evidence(
    monkeypatch,
):
    import backend.scripts.qualify_external_pi_fleet as controller

    calls = Counter()

    def systemctl(command, **_kwargs):
        unit = command[-1]
        calls[unit] += 1
        worker = "qualification-worker" in unit
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(
                (
                    f"MemoryPeak={(20 if worker else 10) * 1024**2}",
                    f"CPUUsageNSec={calls[unit] * 1_000_000_000}",
                    "TasksCurrent=3",
                )
            )
            + "\n",
        )

    operator = object.__new__(controller.SystemFleetOperator)
    operator.runner = systemctl
    operator._unit_cpu_state = {}
    host_cpu = iter(((100, 80), (200, 100), (200, 100), (300, 120)))
    operator._read_host_cpu = lambda: next(host_cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)
    operator._mem_available_bytes = lambda: 2 * 1024**3
    monotonic = iter((10.0, 12.0))
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(monotonic))
    shape = resolve_fleet_shape("5x32")

    first = operator.sample_resources(shape)
    second = operator.sample_resources(shape)

    assert first.peak_cpu_percent == 80.0
    assert second.peak_memory_bytes == 150 * 1024**2
    assert second.peak_cpu_percent == 80.0
    assert second.peak_tasks == 30
    assert second.minimum_host_mem_available_bytes == 2 * 1024**3
    assert len(second.unit_peaks) == 10
    assert {item.peak_cpu_percent for item in second.unit_peaks} == {50.0}
    assert set(calls.values()) == {2}
    assert slept == [1.0, 1.0]


def test_controller_concurrently_aborts_round_when_live_resource_guard_crosses(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class CrossingOperator(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            evidence = super().sample_resources(shape)
            if self.in_round.is_set():
                return evidence.model_copy(
                    update={"minimum_host_mem_available_bytes": 1536 * 1024**2 - 1}
                )
            return evidence

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            if not abort_requested():
                raise RuntimeError("no concurrent resource guard")
            raise FleetRunRefused("resource guard crossed")

    operator = CrossingOperator()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="resource guard crossed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True


def test_controller_aborts_round_when_concurrent_resource_sampler_errors(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SamplingFailure(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            if self.in_round.is_set():
                raise RuntimeError("resource adapter failed")
            return super().sample_resources(shape)

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            raise FleetRunRefused("round stopped")

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="round stopped"):
        run_fleet_controller(
            SamplingFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
