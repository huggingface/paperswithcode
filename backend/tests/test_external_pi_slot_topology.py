import json

import pytest

from deploy.external_pi_slot_topology import (
    REPLICA_COUNT,
    REPLICA_MAXIMUM_SESSIONS,
    external_pi_endpoints,
    replica_instance,
    replica_specs,
)


def test_four_replica_topology_has_unique_slot_isolated_identity() -> None:
    token = "t" * 48

    staging_blue = replica_specs("staging", "blue", token)
    staging_green = replica_specs("staging", "green", token)
    production_blue = replica_specs("production", "blue", token)
    production_green = replica_specs("production", "green", token)

    assert REPLICA_COUNT == 4
    assert REPLICA_MAXIMUM_SESSIONS == 8
    assert sum(item.maximum_sessions for item in staging_blue) == 32
    assert (
        len({item.port for item in (*staging_blue, *staging_green, *production_blue)})
        == 12
    )
    assert len({item.worker_id for item in (*staging_blue, *staging_green)}) == 8
    assert len({item.token for item in staging_blue}) == 4
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
    assert replica_instance("green", 3) == "green-03"

    with pytest.raises(ValueError, match="replica"):
        replica_instance("green", 4)
    with pytest.raises(ValueError, match="slot"):
        replica_instance("other", 0)


def test_backend_endpoint_json_matches_replica_contract() -> None:
    endpoints = json.loads(external_pi_endpoints("production", "green", "s" * 48))

    assert len(endpoints) == 4
    assert [item["endpoint_id"] for item in endpoints] == [
        "production-green-00",
        "production-green-01",
        "production-green-02",
        "production-green-03",
    ]
    assert all(item["worker_id"] == item["endpoint_id"] for item in endpoints)
    assert all(item["base_url"].startswith("http://127.0.0.1:") for item in endpoints)
    assert len({item["token"] for item in endpoints}) == 4
