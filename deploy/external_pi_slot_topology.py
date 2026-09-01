"""Fixed sixteen-replica topology for release-managed external Pi workers."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

REPLICA_COUNT = 16
REPLICA_MAXIMUM_SESSIONS = 2

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
    environment: str, slot: str, base_token: str
) -> tuple[ExternalPiReplicaSpec, ...]:
    try:
        ports = _SLOT_PORTS[environment][slot]
    except KeyError as error:
        raise ValueError(
            "external Pi deployment environment or slot is invalid"
        ) from error
    return tuple(
        ExternalPiReplicaSpec(
            instance=replica_instance(slot, index),
            endpoint_id=f"{environment}-{slot}-{index:02d}",
            worker_id=f"{environment}-{slot}-{index:02d}",
            port=port,
            maximum_sessions=REPLICA_MAXIMUM_SESSIONS,
            token=_replica_token(base_token, f"{environment}-{slot}-{index:02d}"),
        )
        for index, port in enumerate(ports)
    )


def external_pi_endpoints(environment: str, slot: str, base_token: str) -> str:
    values = [
        {
            "endpoint_id": item.endpoint_id,
            "worker_id": item.worker_id,
            "base_url": f"http://127.0.0.1:{item.port}",
            "token": item.token,
        }
        for item in replica_specs(environment, slot, base_token)
    ]
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


__all__ = (
    "ExternalPiReplicaSpec",
    "REPLICA_COUNT",
    "REPLICA_MAXIMUM_SESSIONS",
    "external_pi_endpoints",
    "replica_instance",
    "replica_specs",
)
