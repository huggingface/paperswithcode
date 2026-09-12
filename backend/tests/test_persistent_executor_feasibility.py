from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from backend.loadtests.persistent_executor_feasibility import (
    BudgetExhausted,
    ExperimentBudget,
    EXPECTED_PROFILE_COUNTS,
    StopMeasurement,
    nearest_rank,
    validate_manifest,
    validate_report,
)
from backend.scripts.qualify_persistent_executor_modal_task0 import (
    Sample,
    _gate_is_impossible,
)


def _manifest() -> dict[str, object]:
    boundary = (
        "before_delivery",
        "after_acceptance",
        "during_execution",
        "after_terminal_before_delivery",
    )
    coverage = {
        "cold_first_pwd": "real_modal",
        "cold_32_way": "real_modal",
        "warm_ack": "local_process",
        "warm_noop": "local_process",
        "connected_stop_one": "local_process",
        "connected_stop_four": "local_process",
        "disconnected_stop_one": "real_modal",
        "disconnected_stop_four": "real_modal",
        "deadline_one": "local_process",
        "deadline_four": "local_process",
        "reconnect_protocol_peers": "protocol_simulator",
        "reconnect_real_modal": "real_modal",
    }
    simultaneous = {
        "cold_32_way": 32,
        "connected_stop_four": 4,
        "disconnected_stop_four": 4,
        "deadline_four": 4,
        "reconnect_protocol_peers": 1000,
        "reconnect_real_modal": 32,
    }
    return {
        "schema_version": "persistent-executor-feasibility-v2",
        "status": "preliminary_feasibility",
        "manifest_id": "persistent-executor-feasibility-20260911-r1",
        "frozen_at": "2026-09-11T12:00:00Z",
        "environment": "pwc-chat-staging",
        "modal_region": "eu-west",
        "worker_shape": "modal-sandbox-1cpu-2048mib",
        "image_reference": "im-1234567890abcdefghijklmnop",
        "image_digest": "1" * 64,
        "source_commit": "67e575c680b853b0a92e0173916916ec5a7404e0",
        "protocol_digest": "2" * 64,
        "schema_digest": "3" * 64,
        "transport_source": {
            "repository": "https://github.com/openai/codex",
            "commit_sha": "c62d191c4c8c0cab7045fca6efc399197334bb6c",
            "license": "Apache-2.0",
            "security_profile": "noise_hybrid_ik_v1",
            "files": [
                {
                    "path": "codex-rs/exec-server/src/remote.rs",
                    "blob_sha": "a" * 40,
                    "disposition": "study",
                }
            ],
            "dependency_lock_sha256": "4" * 64,
            "interoperability_vectors_sha256": "5" * 64,
        },
        "baseline_reference": "pwc-vps-baseline-20260911-r1",
        "baselines": [
            {
                "artifact_id": "pwc-vps-baseline-20260911-r1",
                "captured_at": "2026-09-11T12:00:00Z",
                "cohort": cohort,
                "host_cpu_percent": 6.08 if cohort == "idle" else 42.0,
                "mem_available_mib": 5175 if cohort == "idle" else 3072,
                "disk_free_mib": 2791,
                "event_loop_lag_p99_ms": 0.274 if cohort == "idle" else 12.0,
                "host_open_fds": 9152 if cohort == "idle" else 12000,
                "postgres_connections": 21 if cohort == "idle" else 45,
            }
            for cohort in ("idle", "loaded")
        ],
        "resource_limits": {
            "host_cpu_percent_exclusive_max": 80,
            "host_mem_available_mib_min": 1536,
            "disk_free_mib_min": 2048,
            "rendezvous_rss_mib_max": 512,
            "harness_proxy_rss_mib_max": 512,
            "process_fd_max": 4096,
            "postgres_connections_total_max": 80,
            "postgres_connections_incremental_max": 20,
            "postgres_checkpoint_updates_per_second_max": 33.4,
            "event_loop_lag_p99_ms_max": 50.0,
            "operation_unacked_bytes_max": 65536,
            "turn_stream_unacked_bytes_max": 262144,
            "physical_connection_unacked_bytes_max": 524288,
            "reserved_control_bytes_per_connection": 16384,
            "sampling_interval_ms": 100,
            "breach_action": "abort_retain_reservations_and_report_failure",
        },
        "spend_limits": {
            "total_experiment_microusd": 10_000_000,
            "pricing_source_id": "modal-staging-price-v1",
            "pricing_attested_at": "2026-09-11T12:00:00Z",
            "sandbox_rate_microusd_per_second": 24,
            "model_provider": "none",
            "provider_call_max": 0,
            "provider_input_token_max": 0,
            "provider_output_token_max": 0,
            "sandbox_create_max": 1100,
            "sandbox_billed_seconds_max": 264_000,
            "sandbox_lifetime_seconds_max": 240,
            "blank_reserve_microusd": 250_000,
            "retained_reserve_microusd": 250_000,
            "rotation_reserve_microusd": 250_000,
            "replacement_reserve_microusd": 500_000,
            "uncertain_usage_reserve_microusd": 1_000_000,
            "unknown_usage_retains_reservation": True,
            "budget_exhaustion_action": "stop_new_work_reconcile_covered_turns",
        },
        "offered_requests_per_second": 250,
        "duration_seconds": 3600,
        "percentile_method": "nearest_rank",
        "profiles": [
            {
                "name": name,
                "coverage": coverage[name],
                "observations": observations,
                "simultaneous_operations": simultaneous.get(name, 1),
                "p95_target_ms": (
                    None
                    if name.startswith("disconnected_stop")
                    else 250
                    if "stop" in name or "deadline" in name
                    else 1000
                ),
                "p99_target_ms": (
                    None
                    if name.startswith("disconnected_stop")
                    else 500
                    if "stop" in name or "deadline" in name
                    else 5000
                ),
                "delivery_requirement": (
                    "not_applicable_partition_termination"
                    if name.startswith("disconnected_stop")
                    else "executor_observation"
                    if "stop" in name or "deadline" in name
                    else "profile_latency"
                ),
                "containment_p95_target_ms": (
                    1000 if "stop" in name or "deadline" in name else None
                ),
                "containment_p99_target_ms": (
                    2000 if "stop" in name or "deadline" in name else None
                ),
                "includes_saturated_output": "stop" in name,
                "includes_unresponsive_process": "stop" in name or "deadline" in name,
                "includes_failed_broker_revocation": "stop" in name,
            }
            for name, observations in EXPECTED_PROFILE_COUNTS.items()
        ],
        "faults": {
            "peer_loss": boundary,
            "rendezvous_loss": boundary,
            "harness_loss": boundary,
            "worker_loss": boundary,
            "replay_uncertain_commands": False,
        },
        "stop_on_first_failed_gate": True,
    }


def test_complete_manifest_passes_preflight() -> None:
    manifest = validate_manifest(_manifest())

    assert manifest.status == "preliminary_feasibility"
    assert len(manifest.profiles) == len(EXPECTED_PROFILE_COUNTS)


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ((), "resource_limits"),
        ((), "spend_limits"),
        (("resource_limits",), "event_loop_lag_p99_ms_max"),
        (("resource_limits",), "process_fd_max"),
        (("resource_limits",), "postgres_connections_total_max"),
        (("spend_limits",), "total_experiment_microusd"),
        (("spend_limits",), "provider_call_max"),
        (("spend_limits",), "sandbox_billed_seconds_max"),
    ],
)
def test_missing_numeric_limits_fail_preflight(path: tuple[str, ...], key: str) -> None:
    value = copy.deepcopy(_manifest())
    target = value
    for part in path:
        target = target[part]  # type: ignore[index,assignment]
    del target[key]  # type: ignore[arg-type,index]

    with pytest.raises(ValidationError):
        validate_manifest(value)


def test_missing_profile_fails_preflight() -> None:
    value = _manifest()
    value["profiles"] = value["profiles"][:-1]  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_manifest(value)


def test_revision_79_budget_ceiling_is_fifteen_dollars() -> None:
    value = _manifest()
    value["spend_limits"]["total_experiment_microusd"] = 15_000_000  # type: ignore[index]
    validate_manifest(value)
    value["spend_limits"]["total_experiment_microusd"] = 15_000_001  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_manifest(value)


def test_post_hoc_sample_reduction_fails_preflight() -> None:
    value = _manifest()
    value["profiles"][0]["observations"] = 999  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_manifest(value)


def test_simulated_cold_modal_evidence_fails_preflight() -> None:
    value = _manifest()
    value["profiles"][0]["coverage"] = "protocol_simulator"  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_manifest(value)


def test_release_qualification_status_is_not_accepted() -> None:
    value = _manifest()
    value["status"] = "release_qualification"

    with pytest.raises(ValidationError):
        validate_manifest(value)


def _report() -> dict[str, object]:
    return {
        "schema_version": "persistent-executor-feasibility-report-v2",
        "status": "preliminary_feasibility",
        "manifest_id": "persistent-executor-feasibility-20260911-r1",
        "source_commit": "67e575c680b853b0a92e0173916916ec5a7404e0",
        "generated_at": "2026-09-11T21:15:00Z",
        "results": [
            {
                "recommendation": recommendation,
                "status": "incomplete",
                "evidence": [],
                "unresolved_decisions": ["required evidence has not been collected"],
            }
            for recommendation in ("R1", "R2", "R3", "R4", "R5", "R6")
        ],
    }


def test_incomplete_report_cannot_pass_task_zero() -> None:
    report = validate_report(_report())

    assert not report.passed


def test_recommendation_cannot_pass_with_missing_scenarios() -> None:
    value = _report()
    value["results"][0] = {  # type: ignore[index]
        "recommendation": "R1",
        "status": "passed",
        "evidence": [],
        "unresolved_decisions": [],
    }

    with pytest.raises(ValidationError):
        validate_report(value)


def test_report_rejects_missing_recommendation() -> None:
    value = _report()
    value["results"] = value["results"][:-1]  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_report(value)


def test_budget_exhaustion_stops_unreserved_sandbox_work() -> None:
    manifest = validate_manifest(_manifest())
    budget = ExperimentBudget(manifest.spend_limits)

    reservations = [budget.reserve_sandbox() for _ in range(1100)]
    with pytest.raises(BudgetExhausted):
        budget.reserve_sandbox()

    assert budget.sandbox_creates == 1100
    assert len(set(reservations)) == 1100


def test_unknown_usage_retains_reservation_and_reconciliation_is_exactly_once() -> None:
    manifest = validate_manifest(_manifest())
    budget = ExperimentBudget(manifest.spend_limits)
    reservation = budget.reserve_sandbox()

    budget.reconcile(reservation, actual_billed_seconds=None)
    assert budget.reserved_microusd > 0
    with pytest.raises(ValueError, match="already reconciled"):
        budget.reconcile(reservation, actual_billed_seconds=1)


def test_partition_stop_passes_only_on_independent_containment() -> None:
    measurement = StopMeasurement(
        stop_committed_at=100.0,
        executor_observed_at=None,
        process_exit_confirmed_at=100.8,
        egress_revoked_at=100.8,
        sandbox_termination_confirmed_at=100.8,
        delivery_required=False,
    )

    assert measurement.delivery_ms is None
    assert measurement.containment_ms == pytest.approx(800)
    assert measurement.passed


def test_connected_stop_still_requires_executor_observation() -> None:
    measurement = StopMeasurement(
        stop_committed_at=100.0,
        executor_observed_at=None,
        process_exit_confirmed_at=100.8,
        egress_revoked_at=100.8,
        sandbox_termination_confirmed_at=100.8,
        delivery_required=True,
    )

    assert not measurement.passed


def test_nearest_rank_keeps_tail_failures_in_distribution() -> None:
    values = [float(value) for value in range(1, 1001)]

    assert nearest_rank(values, 0.95) == 950
    assert nearest_rank(values, 0.99) == 990


def test_modal_cohort_stops_when_frozen_tail_gate_is_impossible() -> None:
    healthy = Sample(
        profile="disconnected_stop_one",
        index=0,
        sandbox_id="sb-1",
        cold_first_pwd_ms=1000,
        containment_ms=500,
        process_exit_confirmed=True,
        egress_revoked=True,
        sandbox_termination_confirmed=True,
        reservation_retained=True,
        error=None,
    )
    failed = Sample(
        profile="disconnected_stop_one",
        index=1,
        sandbox_id=None,
        cold_first_pwd_ms=240_000,
        containment_ms=240_000,
        process_exit_confirmed=False,
        egress_revoked=False,
        sandbox_termination_confirmed=False,
        reservation_retained=True,
        error="SandboxError",
    )

    assert not _gate_is_impossible([healthy] * 989 + [failed] * 10, include_cold=True)
    assert _gate_is_impossible([healthy] * 989 + [failed] * 11, include_cold=True)
