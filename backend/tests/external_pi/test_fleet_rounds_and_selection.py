"""Round aggregation, shape reports, final selection, and report publication."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    FleetRoundReport,
    FleetRunRefused,
    ForbiddenActivity,
    HostResourceSnapshot,
    aggregate_round,
    build_completed_shape_report,
    build_final_report,
    build_resource_refused_shape_report,
    evaluate_resource_preflight,
    publish_fleet_report,
    resolve_fleet_shape,
)
from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
)
from backend.tests.external_pi.fleet_harness import (
    _cleanup,
    _passed_resource_preflight,
    _resources,
    _round,
    _unit_resources,
    _workers,
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
