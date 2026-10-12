import json

import pytest

from deploy.external_pi_slot_topology import (
    REPLICA_COUNT,
    REPLICA_MAXIMUM_SESSIONS,
    external_pi_endpoints,
    replica_instance,
    replica_specs,
    replica_specs_for_topology,
)


def test_eight_replica_topology_has_unique_slot_isolated_identity() -> None:
    token = "t" * 48

    staging_blue = replica_specs("staging", "blue", token)
    staging_green = replica_specs("staging", "green", token)
    production_blue = replica_specs("production", "blue", token)
    production_green = replica_specs("production", "green", token)

    assert REPLICA_COUNT == 8
    assert REPLICA_MAXIMUM_SESSIONS == 4
    assert sum(item.maximum_sessions for item in staging_blue) == 32
    assert (
        len({item.port for item in (*staging_blue, *staging_green, *production_blue)})
        == 24
    )
    assert len({item.worker_id for item in (*staging_blue, *staging_green)}) == 16
    assert len({item.token for item in staging_blue}) == 8
    assert all(item.token != token for item in staging_blue)
    all_ports = {
        item.port
        for item in (
            *staging_blue,
            *staging_green,
            *production_blue,
            *production_green,
        )
    }
    assert all_ports.isdisjoint({8766, 8767, 8776, 8777})
    assert all_ports.isdisjoint(range(8780, 8796))


def test_replica_instance_round_trips_and_rejects_ambiguous_values() -> None:
    assert replica_instance("green", 7) == "green-07"

    with pytest.raises(ValueError, match="replica"):
        replica_instance("green", 8)
    with pytest.raises(ValueError, match="slot"):
        replica_instance("other", 0)


def test_backend_endpoint_json_matches_replica_contract() -> None:
    endpoints = json.loads(external_pi_endpoints("production", "green", "s" * 48))

    assert len(endpoints) == 8
    assert [item["endpoint_id"] for item in endpoints] == [
        "production-green-00",
        "production-green-01",
        "production-green-02",
        "production-green-03",
        "production-green-04",
        "production-green-05",
        "production-green-06",
        "production-green-07",
    ]
    assert all(item["worker_id"] == item["endpoint_id"] for item in endpoints)
    assert all(item["base_url"].startswith("http://127.0.0.1:") for item in endpoints)
    assert len({item["token"] for item in endpoints}) == 8


def test_transition_topology_can_describe_sixteen_two_session_workers() -> None:
    replicas = replica_specs_for_topology(
        "staging",
        "blue",
        "t" * 48,
        replica_count=16,
        maximum_sessions=2,
    )

    assert len(replicas) == 16
    assert sum(item.maximum_sessions for item in replicas) == 32
    assert replicas[-1].worker_id == "staging-blue-15"


def test_sixty_four_tier_keeps_eight_replicas_with_eight_sessions_each() -> None:
    from deploy.external_pi_slot_topology import (
        DEFAULT_FLEET_SESSIONS,
        FLEET_SESSION_TIERS,
        fleet_sessions_from_values,
        replica_maximum_sessions,
    )

    token = "t" * 48
    small = replica_specs("production", "green", token)
    large = replica_specs("production", "green", token, fleet_sessions=64)

    assert FLEET_SESSION_TIERS == (32, 64) and DEFAULT_FLEET_SESSIONS == 32
    assert replica_maximum_sessions(32) == 4 and replica_maximum_sessions(64) == 8
    assert len(large) == 8 and sum(item.maximum_sessions for item in large) == 64
    # Same identities, ports, and tokens; only the per-replica share changes.
    assert [item.worker_id for item in large] == [item.worker_id for item in small]
    assert [item.port for item in large] == [item.port for item in small]
    assert [item.token for item in large] == [item.token for item in small]
    assert (
        len(
            json.loads(
                external_pi_endpoints("staging", "blue", token, fleet_sessions=64)
            )
        )
        == 8
    )

    assert fleet_sessions_from_values({}) == 32
    assert (
        fleet_sessions_from_values({"PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "64"})
        == 64
    )
    assert (
        fleet_sessions_from_values({"PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": '"32"'})
        == 32
    )
    for invalid in ("48", "8", "abc", ""):
        with pytest.raises(ValueError, match="reviewed tier"):
            fleet_sessions_from_values(
                {"PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": invalid}
            )
    with pytest.raises(ValueError, match="reviewed tier"):
        replica_specs("staging", "blue", token, fleet_sessions=48)
    with pytest.raises(ValueError, match="capacity is invalid"):
        replica_specs_for_topology(
            "staging", "blue", token, replica_count=8, maximum_sessions=6
        )
