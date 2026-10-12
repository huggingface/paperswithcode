"""Persistent transport profile manifests, reports, and pass gates."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    PERSISTENT_TRANSPORT_SCENARIOS,
    PERSISTENT_LATENCY_GATES,
    build_persistent_transport_user_specs,
    validate_persistent_transport_manifest,
    validate_persistent_transport_report,
)
from backend.tests.external_pi.fleet_harness import (
    _persistent_transport_manifest,
)


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
            name: {
                "denominator": 1000,
                "accepted": 1000,
                "p50_ms": 100,
                "p95_ms": targets[0],
                "p99_ms": targets[1],
            }
            for name, targets in PERSISTENT_LATENCY_GATES.items()
        },
        "soak": {"turns": 320, "failed": 0, "duration_seconds": 3600},
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


@pytest.mark.parametrize("metric", tuple(PERSISTENT_LATENCY_GATES))
@pytest.mark.parametrize("invalid", ["missing", "too_few", "failed", "p99"])
def test_persistent_pass_requires_every_measured_latency_gate(metric, invalid):
    payload = _persistent_transport_report()
    if invalid == "missing":
        del payload["percentiles"][metric]
    else:
        row = payload["percentiles"][metric]
        if invalid == "too_few":
            row.update(denominator=999, accepted=999)
        elif invalid == "failed":
            row["accepted"] = 999
        else:
            row["p99_ms"] += 1
    with pytest.raises(ValidationError):
        validate_persistent_transport_report(payload)
    payload["status"] = "failed"
    validate_persistent_transport_report(payload)


@pytest.mark.parametrize(
    "field,value", [("turns", 319), ("duration_seconds", 3599), ("failed", 4)]
)
def test_persistent_pass_requires_soak_duration_volume_and_reliability(field, value):
    payload = _persistent_transport_report()
    payload["soak"][field] = value
    with pytest.raises(ValidationError):
        validate_persistent_transport_report(payload)


def test_persistent_cli_never_substitutes_legacy_fleet_workload(monkeypatch, tmp_path):
    import sys
    from backend.scripts import qualify_external_pi_fleet as cli

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_persistent_transport_manifest()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualify",
            "--environment",
            "staging",
            "--release-id",
            "candidate",
            "--confirm",
            cli.CONFIRMATION,
            "--profile",
            "persistent-transport",
            "--persistent-manifest",
            str(manifest),
        ],
    )
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    invoked = []
    monkeypatch.setattr(
        cli, "SystemFleetOperator", lambda **kwargs: invoked.append(kwargs)
    )
    assert cli.main() == 1
    assert invoked == []
