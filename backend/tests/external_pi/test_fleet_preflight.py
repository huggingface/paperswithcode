"""Fleet routing and staging, port, and resource preflight."""

from __future__ import annotations

from collections import Counter

import pytest

from backend.loadtests.external_pi_fleet_core import (
    MIN_PROJECTED_MEM_AVAILABLE_BYTES,
    FleetReplica,
    FleetRunRefused,
    FleetSafetyConfig,
    FleetShape,
    HostResourceSnapshot,
    PortState,
    ResourcePreflight,
    build_external_pi_fleet_request,
    classify_external_pi_fleet_response,
    evaluate_resource_preflight,
    resolve_fleet_shape,
    route_ordinal,
    validate_fleet_preflight,
)
from backend.loadtests.external_pi_shadow_core import (
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
)


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
