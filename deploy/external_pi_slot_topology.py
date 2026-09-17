"""Fixed eight-replica topology for release-managed external Pi workers.

Every slot runs eight replicas on fixed loopback ports. The reviewed fleet
capacity (sessions across those eight replicas) is a tier read from the
protected environment key ``PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS``; each
replica serves ``fleet / 8`` sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass

REPLICA_COUNT = 8
# Reviewed fleet capacities and the 32-turn tier's per-replica share, which
# remains the default wherever no protected environment is available.
FLEET_SESSION_TIERS = (32, 64)
DEFAULT_FLEET_SESSIONS = 32
FLEET_SESSIONS_KEY = "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"
REPLICA_MAXIMUM_SESSIONS = DEFAULT_FLEET_SESSIONS // REPLICA_COUNT


def replica_maximum_sessions(fleet_sessions: int) -> int:
    """Sessions one replica serves for a reviewed fleet tier."""
    if (
        type(fleet_sessions) is not int
        or fleet_sessions not in FLEET_SESSION_TIERS
        or fleet_sessions % REPLICA_COUNT
    ):
        raise ValueError("external Pi fleet capacity must be a reviewed tier")
    return fleet_sessions // REPLICA_COUNT


def fleet_sessions_from_values(values: Mapping[str, str]) -> int:
    """Read the fleet tier from protected environment values (default 32)."""
    raw = str(values.get(FLEET_SESSIONS_KEY, DEFAULT_FLEET_SESSIONS)).strip()
    raw = raw.strip('"').strip("'")
    if not raw.isdigit():
        raise ValueError("external Pi fleet capacity must be a reviewed tier")
    fleet_sessions = int(raw)
    replica_maximum_sessions(fleet_sessions)
    return fleet_sessions


_SLOT_PORTS = {
    "staging": {
        "blue": (
            8820,
            8821,
            8822,
            8823,
            8838,
            8839,
            8840,
            8841,
            8854,
            8855,
            8856,
            8857,
            8858,
            8859,
            8860,
            8861,
        ),
        "green": (
            8824,
            8825,
            8826,
            8827,
            8842,
            8843,
            8844,
            8845,
            8862,
            8863,
            8864,
            8865,
            8866,
            8867,
            8868,
            8869,
        ),
    },
    "production": {
        "blue": (
            8830,
            8831,
            8832,
            8833,
            8846,
            8847,
            8848,
            8849,
            8870,
            8871,
            8872,
            8873,
            8874,
            8875,
            8876,
            8877,
        ),
        "green": (
            8834,
            8835,
            8836,
            8837,
            8850,
            8851,
            8852,
            8853,
            8878,
            8879,
            8880,
            8881,
            8882,
            8883,
            8884,
            8885,
        ),
    },
}


@dataclass(frozen=True, slots=True)
class ExternalPiReplicaSpec:
    instance: str
    endpoint_id: str
    worker_id: str
    port: int
    maximum_sessions: int
    token: str


def replica_instance(slot: str, index: int) -> str:
    if slot not in {"blue", "green"}:
        raise ValueError("external Pi deployment slot is invalid")
    if type(index) is not int or not 0 <= index < REPLICA_COUNT:
        raise ValueError("external Pi replica index is invalid")
    return f"{slot}-{index:02d}"


def _replica_token(base_token: str, worker_id: str) -> str:
    if not isinstance(base_token, str) or len(base_token) < 32:
        raise ValueError("external Pi worker token is missing or invalid")
    return hmac.new(
        base_token.encode("utf-8"),
        worker_id.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def replica_specs(
    environment: str,
    slot: str,
    base_token: str,
    *,
    fleet_sessions: int = DEFAULT_FLEET_SESSIONS,
) -> tuple[ExternalPiReplicaSpec, ...]:
    return replica_specs_for_topology(
        environment,
        slot,
        base_token,
        replica_count=REPLICA_COUNT,
        maximum_sessions=replica_maximum_sessions(fleet_sessions),
    )


def replica_specs_for_topology(
    environment: str,
    slot: str,
    base_token: str,
    *,
    replica_count: int,
    maximum_sessions: int,
) -> tuple[ExternalPiReplicaSpec, ...]:
    try:
        ports = _SLOT_PORTS[environment][slot]
    except KeyError as error:
        raise ValueError(
            "external Pi deployment environment or slot is invalid"
        ) from error
    if (
        type(replica_count) is not int
        or type(maximum_sessions) is not int
        or not 1 <= replica_count <= len(ports)
        or replica_count * maximum_sessions not in FLEET_SESSION_TIERS
    ):
        raise ValueError("external Pi deployment topology capacity is invalid")
    return tuple(
        ExternalPiReplicaSpec(
            instance=f"{slot}-{index:02d}",
            endpoint_id=f"{environment}-{slot}-{index:02d}",
            worker_id=f"{environment}-{slot}-{index:02d}",
            port=port,
            maximum_sessions=maximum_sessions,
            token=_replica_token(base_token, f"{environment}-{slot}-{index:02d}"),
        )
        for index, port in enumerate(ports[:replica_count])
    )


def external_pi_endpoints(
    environment: str,
    slot: str,
    base_token: str,
    *,
    fleet_sessions: int = DEFAULT_FLEET_SESSIONS,
) -> str:
    values = [
        {
            "endpoint_id": item.endpoint_id,
            "worker_id": item.worker_id,
            "base_url": f"http://127.0.0.1:{item.port}",
            "token": item.token,
        }
        for item in replica_specs(
            environment, slot, base_token, fleet_sessions=fleet_sessions
        )
    ]
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


__all__ = (
    "DEFAULT_FLEET_SESSIONS",
    "FLEET_SESSIONS_KEY",
    "FLEET_SESSION_TIERS",
    "REPLICA_COUNT",
    "REPLICA_MAXIMUM_SESSIONS",
    "ExternalPiReplicaSpec",
    "external_pi_endpoints",
    "fleet_sessions_from_values",
    "replica_instance",
    "replica_maximum_sessions",
    "replica_specs",
    "replica_specs_for_topology",
)
