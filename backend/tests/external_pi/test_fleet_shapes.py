"""Fleet shapes, capacity profiles, and durable profile binding."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import FrozenInstanceError

import pytest

from backend.loadtests.external_pi_fleet_core import (
    MIN_PROJECTED_MEM_AVAILABLE_BYTES,
    FleetRunRefused,
    ForbiddenActivity,
    aggregate_round,
    resolve_fleet_shape,
    resolve_durable_profile,
)
from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
)
from backend.tests.external_pi.fleet_harness import (
    _persistent_transport_manifest,
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
