"""Durable profile report evidence, atomic publication, and failure reasons."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    aggregate_durable_profile,
    resolve_durable_profile,
    DurableTurnObservation,
    DurableQualificationReport,
    publish_durable_report,
    DurableQualificationEvidence,
)
from backend.tests.external_pi.fleet_harness import (
    _DurableOperator,
    _FUNCTIONAL_MODAL,
    _MODAL_RATE,
    _NO_MODAL,
    _SERVER_LATENCY_P95,
    _live_qualification_evidence,
)


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
