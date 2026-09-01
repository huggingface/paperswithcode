#!/usr/bin/env python3
"""Release-managed lifecycle for environment-isolated external Pi workers."""

from __future__ import annotations

import grp
import json
import math
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

try:
    from deploy.external_pi_runtime import external_pi_runtime_manifest
    from deploy.external_pi_slot_topology import ExternalPiReplicaSpec, replica_specs
except ModuleNotFoundError:
    from external_pi_runtime import external_pi_runtime_manifest  # type: ignore[no-redef]
    from external_pi_slot_topology import (  # type: ignore[no-redef]
        ExternalPiReplicaSpec,
        replica_specs,
    )

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
STATUS_ROOT = Path(
    os.environ.get("PWC_EXTERNAL_PI_STATUS_ROOT", "/run/paperswithcode/external-pi")
)
PRODUCTION_STATUS_ROOT = Path(
    os.environ.get(
        "PWC_PRODUCTION_EXTERNAL_PI_STATUS_ROOT",
        "/run/paperswithcode/external-pi-status-production",
    )
)
WORKER_USER = "pwc-external-pi"
WORKER_CONFIG = CONFIG_ROOT / "external-pi-worker.env"
ENVIRONMENT_SLOT_PORTS = {
    "staging": {"blue": 8766, "green": 8767},
    "production": {"blue": 8776, "green": 8777},
}
MAXIMUM_SESSIONS = 32
PREVIOUS_REPLICA_COUNT = 8
PREVIOUS_REPLICA_MAXIMUM_SESSIONS = 4
CONTRACT_VERSION = "external-pi-v1"
DRAIN_SECONDS_MINIMUM = 5
DRAIN_SECONDS_MAXIMUM = 300
DRAIN_POLL_SECONDS_MINIMUM = 0.1
DRAIN_POLL_SECONDS_MAXIMUM = 5.0
NODE_TERMINATION_OVERHEAD_SECONDS = 5
SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS = 5
MAXIMUM_DRAIN_STOP_TIMEOUT_SECONDS = (
    DRAIN_SECONDS_MAXIMUM
    + DRAIN_POLL_SECONDS_MAXIMUM
    + NODE_TERMINATION_OVERHEAD_SECONDS
    + SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS
)
MAXIMUM_WORKER_STATUS_BYTES = 64 * 1024
OPERATION_COUNTER_NAMES = (
    "shadow_requests",
    "model_calls",
    "tool_calls",
    "provider_calls",
    "modal_calls",
    "billing_events",
)

_SUPERVISOR_PROTECTED_KEYS = (
    "PWC_DB_HOST",
    "PWC_DB_PORT",
    "PWC_DB_NAME",
    "PWC_DB_USER",
    "PWC_DB_PASSWORD",
    "PWC_DB_SEARCH_PATH",
    "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
    "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS",
)


class ExternalPiSlotError(RuntimeError):
    """One shadow slot failed its bounded lifecycle transition."""


@dataclass(frozen=True, slots=True)
class ExternalPiSlot:
    slot: str
    port: int
    worker_id: str
    release: Path
    release_id: str
    runtime: Path
    node: Path
    entry_point: Path
    prompt: Path
    status_path: Path


def _environment_status_path(environment: str, worker_id: str) -> Path:
    if environment == "staging":
        return STATUS_ROOT / f"{worker_id}.json"
    parts = worker_id.split("-")
    if (
        len(parts) not in {2, 3}
        or parts[0] != "production"
        or parts[1]
        not in {
            "blue",
            "green",
        }
    ):
        raise ValueError("external Pi production worker identity is invalid")
    root = PRODUCTION_STATUS_ROOT.with_name(f"{PRODUCTION_STATUS_ROOT.name}-{parts[1]}")
    return root / (f"{worker_id}.json" if len(parts) == 3 else "status.json")


def resolve_external_pi_slot(environment: str, slot: str) -> ExternalPiSlot:
    ports = ENVIRONMENT_SLOT_PORTS.get(environment)
    if ports is None or slot not in ports:
        raise ValueError("external Pi deployment slot is invalid")
    release_link = APP_ROOT / "environments" / environment / "slots" / slot / "release"
    if not release_link.is_symlink():
        raise ValueError("external Pi slot release pointer is missing")
    release = release_link.resolve(strict=True)
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    descriptor = manifest.get("external_pi_runtime")
    if not isinstance(descriptor, dict):
        raise ValueError("release has no recorded external Pi runtime")
    identifier = descriptor.get("runtime_id")
    contract = descriptor.get("contract")
    if not isinstance(identifier, str) or not isinstance(contract, str):
        raise ValueError("release recorded external Pi runtime is invalid")
    runtime = APP_ROOT / "runtimes/external-pi" / identifier
    runtime_value = external_pi_runtime_manifest(
        runtime,
        expected_id=identifier,
        expected_contract=contract,
    )
    entry_point = runtime / str(runtime_value["entry_point"])
    worker_id = f"{environment}-{slot}"
    return ExternalPiSlot(
        slot=slot,
        port=ports[slot],
        worker_id=worker_id,
        release=release,
        release_id=str(manifest["release_id"]),
        runtime=runtime,
        node=runtime / "node/bin/node",
        entry_point=entry_point,
        prompt=runtime / "assets/pi-system-prompt.txt",
        status_path=_environment_status_path(environment, worker_id),
    )


def resolve_external_pi_replicas(
    environment: str, slot: str, base_token: str
) -> tuple[ExternalPiSlot, ...]:
    resolved = resolve_external_pi_slot(environment, slot)
    return tuple(
        replace(
            resolved,
            port=spec.port,
            worker_id=spec.worker_id,
            status_path=_environment_status_path(environment, spec.worker_id),
        )
        for spec in replica_specs(environment, slot, base_token)
    )


def node_environment(
    resolved: ExternalPiSlot,
    protected: dict[str, str],
    *,
    instance_id: str,
) -> dict[str, str]:
    base_token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(base_token) < 32:
        raise ValueError("external Pi worker token is missing or too short")
    base_state_root = protected.get("PWC_EXTERNAL_PI_STATE_ROOT", "")
    expected_base_state_root = (
        f"/run/paperswithcode/external-pi-{resolved.slot}"
        if resolved.worker_id.startswith("staging-")
        else f"/run/paperswithcode/external-pi-production-{resolved.slot}"
    )
    if base_state_root != expected_base_state_root:
        raise ValueError("external Pi worker state root is invalid")
    specs = replica_specs(
        resolved.worker_id.split("-", 1)[0], resolved.slot, base_token
    )
    spec = next((item for item in specs if item.worker_id == resolved.worker_id), None)
    legacy_worker_id = f"{resolved.worker_id.split('-', 1)[0]}-{resolved.slot}"
    if spec is None and resolved.worker_id != legacy_worker_id:
        raise ValueError("external Pi worker replica is invalid")
    state_root = (
        str(Path(base_state_root) / resolved.worker_id)
        if spec is not None
        else base_state_root
    )
    return {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": str(resolved.port),
        "PWC_EXTERNAL_PI_TOKEN": spec.token if spec is not None else base_token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": str(
            spec.maximum_sessions if spec is not None else MAXIMUM_SESSIONS
        ),
        "PWC_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
        "PWC_EXTERNAL_PI_INSTANCE_ID": instance_id,
        "PWC_EXTERNAL_PI_RELEASE_ID": resolved.release_id,
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
        "PWC_EXTERNAL_PI_STATE_ROOT": state_root,
    }


def supervisor_environment(
    resolved: ExternalPiSlot, protected: dict[str, str]
) -> dict[str, str]:
    environment = resolved.worker_id.split("-", 1)[0]
    base_token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    spec = next(
        (
            item
            for item in replica_specs(environment, resolved.slot, base_token)
            if item.worker_id == resolved.worker_id
        ),
        None,
    )
    legacy_worker_id = f"{environment}-{resolved.slot}"
    if spec is None and resolved.worker_id != legacy_worker_id:
        raise ValueError("external Pi worker replica is invalid")
    values = {
        key: protected[key] for key in _SUPERVISOR_PROTECTED_KEYS if key in protected
    }
    values["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"] = (
        spec.token if spec is not None else base_token
    )
    values.update(
        {
            "PWC_ENVIRONMENT": environment,
            "PWC_RELEASE_ID": resolved.release_id,
            "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
            "PWC_CHAT_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
            "PWC_CHAT_EXTERNAL_PI_WORKER_URL": f"http://127.0.0.1:{resolved.port}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": CONTRACT_VERSION,
            "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(
                spec.maximum_sessions if spec is not None else MAXIMUM_SESSIONS
            ),
            "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS", "10"
            ),
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS", "30"
            ),
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS", "60"
            ),
            "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS", "60"
            ),
            "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS": protected.get(
                "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS", "1"
            ),
            "PWC_EXTERNAL_PI_STATUS_PATH": str(resolved.status_path),
            "PWC_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
        }
    )
    return values


def _supervisor_unit(environment: str, slot: str) -> str:
    if (
        environment not in ENVIRONMENT_SLOT_PORTS
        or slot not in ENVIRONMENT_SLOT_PORTS[environment]
    ):
        raise ValueError("external Pi deployment slot is invalid")
    return f"paperswithcode-{environment}-external-pi@{slot}.service"


def _worker_unit(environment: str, slot: str) -> str:
    if (
        environment not in ENVIRONMENT_SLOT_PORTS
        or slot not in ENVIRONMENT_SLOT_PORTS[environment]
    ):
        raise ValueError("external Pi deployment slot is invalid")
    return f"paperswithcode-{environment}-external-pi-worker@{slot}.service"


def _status_path(environment: str, slot: str) -> Path:
    if (
        environment not in ENVIRONMENT_SLOT_PORTS
        or slot not in ENVIRONMENT_SLOT_PORTS[environment]
    ):
        raise ValueError("external Pi deployment slot is invalid")
    worker_id = f"{environment}-{slot}"
    return _environment_status_path(environment, worker_id)


def _status_paths(environment: str, slot: str) -> tuple[Path, ...]:
    return tuple(
        _environment_status_path(environment, spec.worker_id)
        for spec in replica_specs(environment, slot, "x" * 32)
    )


def _draining_replica_specs(
    environment: str, slot: str, base_token: str, release_id: str
) -> tuple[ExternalPiReplicaSpec, ...]:
    current = replica_specs(environment, slot, base_token)
    paths = tuple(
        _environment_status_path(environment, spec.worker_id) for spec in current
    )
    previous_paths = paths[:PREVIOUS_REPLICA_COUNT]
    added_paths = paths[PREVIOUS_REPLICA_COUNT:]
    previous_statuses = _read_replica_statuses(
        environment, slot, current[:PREVIOUS_REPLICA_COUNT]
    )

    def previous_status_is_proven(status: dict, spec: ExternalPiReplicaSpec) -> bool:
        identity_matches = (
            status.get("release_id") == release_id
            and status.get("worker_id") == spec.worker_id
        )
        current_contract = (
            status.get("protocol") == CONTRACT_VERSION
            and type(status.get("maximum_sessions")) is int
            and status.get("maximum_sessions") == PREVIOUS_REPLICA_MAXIMUM_SESSIONS
        )
        legacy_supervisor_contract = (
            "protocol" not in status
            and "maximum_sessions" not in status
            and status.get("authenticated") is True
            and status.get("registered") is True
            and type(status.get("generation")) is int
            and status["generation"] > 0
            and type(status.get("heartbeats")) is int
            and status["heartbeats"] >= 1
            and (
                (status.get("state") == "ready" and status.get("drained") is False)
                or (status.get("state") == "offline" and status.get("drained") is True)
            )
        )
        return identity_matches and (current_contract or legacy_supervisor_contract)

    previous_topology_is_proven = all(
        previous_status_is_proven(status, spec)
        for status, spec in zip(
            previous_statuses, current[:PREVIOUS_REPLICA_COUNT], strict=True
        )
    )
    if (
        all(path.is_file() for path in previous_paths)
        and not any(path.exists() for path in added_paths)
        and previous_topology_is_proven
    ):
        return tuple(
            replace(spec, maximum_sessions=PREVIOUS_REPLICA_MAXIMUM_SESSIONS)
            for spec in current[:PREVIOUS_REPLICA_COUNT]
        )
    return current


def _read_status(environment: str, slot: str) -> dict:
    path = _status_path(environment, slot)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_replica_statuses(
    environment: str,
    slot: str,
    specs: tuple[ExternalPiReplicaSpec, ...] | None = None,
) -> tuple[dict, ...]:
    values = []
    paths = (
        _status_paths(environment, slot)
        if specs is None
        else tuple(
            _environment_status_path(environment, spec.worker_id) for spec in specs
        )
    )
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            value = {}
        values.append(value if isinstance(value, dict) else {})
    return tuple(values)


def _read_primary_status(environment: str, slot: str) -> dict:
    replicas = _read_replica_statuses(environment, slot)
    return replicas[0] if any(replicas) else _read_status(environment, slot)


def slot_status(environment: str, slot: str) -> dict:
    """Return aggregate release-managed lifecycle evidence for one slot."""
    replicas = _read_replica_statuses(environment, slot)
    if not any(replicas):
        return _read_status(environment, slot)
    return {
        "replicas": list(replicas),
        "ready_replicas": sum(value.get("state") == "ready" for value in replicas),
        "maximum_sessions": sum(
            value.get("maximum_sessions", 0)
            for value in replicas
            if type(value.get("maximum_sessions")) is int
        ),
    }


def _read_protected_values(environment: str) -> dict[str, str]:
    path = CONFIG_ROOT / f"{environment}.env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, raw = line.partition("=")
        if separator:
            values[key] = raw.strip().strip("\"'")
    return values


def _protected_staging_values() -> dict[str, str]:
    """Compatibility seam for the qualified staging lifecycle."""
    return _read_protected_values("staging")


def _protected_environment_values(environment: str) -> dict[str, str]:
    if environment not in ENVIRONMENT_SLOT_PORTS:
        raise ValueError("external Pi deployment environment is invalid")
    if environment == "staging":
        return _protected_staging_values()
    return _read_protected_values(environment)


def drain_stop_timeout_seconds(environment: str) -> float:
    """Bound systemctl by the protected drain contract plus fixed teardown time."""
    values = _protected_environment_values(environment)
    raw_drain = values.get("PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS", "60")
    raw_poll = values.get("PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS", "1")
    try:
        drain_seconds = int(raw_drain)
        poll_seconds = float(raw_poll)
    except ValueError as error:
        raise ValueError("external Pi drain configuration must be numeric") from error
    if not DRAIN_SECONDS_MINIMUM <= drain_seconds <= DRAIN_SECONDS_MAXIMUM:
        raise ValueError("external Pi drain seconds are outside protected bounds")
    if (
        not math.isfinite(poll_seconds)
        or not DRAIN_POLL_SECONDS_MINIMUM <= poll_seconds <= DRAIN_POLL_SECONDS_MAXIMUM
    ):
        raise ValueError("external Pi drain polling is outside protected bounds")
    return (
        drain_seconds
        + poll_seconds
        + NODE_TERMINATION_OVERHEAD_SECONDS
        + SYSTEMCTL_COMPLETION_OVERHEAD_SECONDS
    )


def protected_lease_seconds(environment: str) -> int:
    raw = _protected_environment_values(environment).get(
        "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS", "30"
    )
    try:
        lease_seconds = int(raw)
    except ValueError as error:
        raise ValueError("external Pi lease configuration must be numeric") from error
    if not 5 <= lease_seconds <= 60:
        raise ValueError("external Pi lease seconds are outside protected bounds")
    return lease_seconds


def sync_worker_environment(environment: str) -> None:
    """Publish only the worker token to the dedicated protected environment."""
    token = _protected_environment_values(environment).get(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""
    )
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise ValueError("external Pi worker token is missing or invalid")
    worker_config = (
        WORKER_CONFIG
        if environment == "staging"
        else CONFIG_ROOT / f"external-pi-worker-{environment}.env"
    )
    temporary = worker_config.with_name(f".{worker_config.name}.new-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            handle.write(f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={token}\n")
        os.chown(temporary, 0, grp.getgrnam(WORKER_USER).gr_gid)
        os.replace(temporary, worker_config)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _stop_proven_orphaned_worker_if_active(
    environment: str,
    slot: str,
    *,
    worker_active_proven: bool = False,
    expected_release_id: str | None = None,
    validated_orphan_release_ids: frozenset[str] = frozenset(),
    draining_specs: tuple[ExternalPiReplicaSpec, ...] | None = None,
) -> None:
    if not worker_active_proven and _worker_is_inactive(environment, slot):
        return
    if not _supervisor_is_inactive(environment, slot):
        raise ExternalPiSlotError("external Pi supervisor is still active")
    base_token = _protected_environment_values(environment).get(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""
    )
    if len(base_token) < 32:
        raise ExternalPiSlotError("external Pi worker token is unavailable")
    trusted_release_ids = validated_orphan_release_ids
    if expected_release_id is not None:
        trusted_release_ids = trusted_release_ids | {expected_release_id}

    def safe_status(status: object, worker_id: str, maximum_sessions: int) -> bool:
        counters = (
            status.get("operation_counters") if isinstance(status, dict) else None
        )
        identity_and_capacity_match = (
            isinstance(status, dict)
            and status.get("protocol") == CONTRACT_VERSION
            and status.get("worker_id") == worker_id
            and type(status.get("active_sessions")) is int
            and status.get("active_sessions") == 0
            and type(status.get("maximum_sessions")) is int
            and status.get("maximum_sessions") == maximum_sessions
        )
        request_free_unclaimed = (
            isinstance(status, dict)
            and status.get("release_id") in trusted_release_ids
            and status.get("state") == "ready"
            and "worker_generation" in status
            and status.get("worker_generation") is None
            and isinstance(counters, dict)
            and set(counters) == set(OPERATION_COUNTER_NAMES)
            and all(
                type(counters[name]) is int and counters[name] == 0
                for name in OPERATION_COUNTER_NAMES
            )
        )
        return identity_and_capacity_match and (
            status.get("state") == "draining" or request_free_unclaimed
        )

    legacy_worker_id = f"{environment}-{slot}"
    legacy_request = urllib.request.Request(
        f"http://127.0.0.1:{ENVIRONMENT_SLOT_PORTS[environment][slot]}/v1/status",
        headers={"Authorization": f"Bearer {base_token}"},
        method="GET",
    )
    legacy_status: object = None
    try:
        with urllib.request.urlopen(legacy_request, timeout=5) as response:
            payload = response.read(MAXIMUM_WORKER_STATUS_BYTES + 1)
            if len(payload) <= MAXIMUM_WORKER_STATUS_BYTES:
                legacy_status = json.loads(payload)
    except (OSError, ValueError, urllib.error.URLError):
        pass
    if isinstance(legacy_status, dict):
        if not safe_status(legacy_status, legacy_worker_id, MAXIMUM_SESSIONS):
            raise ExternalPiSlotError(
                "external Pi active worker is not proven safe to restart"
            )
        subprocess.run(
            ["systemctl", "stop", _worker_unit(environment, slot)], check=True
        )
        if not _worker_is_inactive(environment, slot):
            raise ExternalPiSlotError("external Pi active worker did not stop")
        return

    current_specs = replica_specs(environment, slot, base_token)
    specs = (
        current_specs
        if draining_specs is None
        else tuple(
            replace(current, maximum_sessions=selected.maximum_sessions)
            for current, selected in zip(current_specs, draining_specs, strict=False)
        )
    )
    for spec in specs:
        request = urllib.request.Request(
            f"http://127.0.0.1:{spec.port}/v1/status",
            headers={"Authorization": f"Bearer {spec.token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = response.read(MAXIMUM_WORKER_STATUS_BYTES + 1)
                if len(payload) > MAXIMUM_WORKER_STATUS_BYTES:
                    raise ValueError("external Pi worker status is too large")
                status = json.loads(payload)
        except (OSError, ValueError, urllib.error.URLError) as error:
            raise ExternalPiSlotError(
                "external Pi active worker status is unavailable"
            ) from error
        if not safe_status(status, spec.worker_id, spec.maximum_sessions):
            raise ExternalPiSlotError(
                "external Pi active worker is not proven safe to restart"
            )
    subprocess.run(["systemctl", "stop", _worker_unit(environment, slot)], check=True)
    if not _worker_is_inactive(environment, slot):
        raise ExternalPiSlotError("external Pi active worker did not stop")


def start_slot(environment: str, slot: str) -> None:
    _status_path(environment, slot).unlink(missing_ok=True)
    for path in _status_paths(environment, slot):
        path.unlink(missing_ok=True)
    sync_worker_environment(environment)
    _stop_proven_orphaned_worker_if_active(environment, slot)
    subprocess.run(["systemctl", "start", _worker_unit(environment, slot)], check=True)
    try:
        subprocess.run(
            ["systemctl", "start", _supervisor_unit(environment, slot)], check=True
        )
    except (OSError, subprocess.CalledProcessError):
        subprocess.run(
            ["systemctl", "stop", _worker_unit(environment, slot)], check=False
        )
        raise


def qualify_candidate(
    environment: str,
    slot: str,
    release_id: str,
    *,
    timeout_seconds: float = 65,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    last: tuple[dict, ...] = ()
    worker_ids = tuple(
        spec.worker_id for spec in replica_specs(environment, slot, "x" * 32)
    )
    while time.monotonic() < deadline:
        last = _read_replica_statuses(environment, slot)
        if not any(last):
            legacy = _read_status(environment, slot)
            generation = legacy.get("generation")
            if (
                legacy.get("release_id") == release_id
                and legacy.get("worker_id") == f"{environment}-{slot}"
                and legacy.get("state") == "ready"
                and legacy.get("authenticated") is True
                and legacy.get("registered") is True
                and isinstance(generation, int)
                and generation >= 1
                and isinstance(legacy.get("heartbeats"), int)
                and legacy["heartbeats"] >= 1
            ):
                return generation
        generations = tuple(value.get("generation") for value in last)
        if len(last) == len(worker_ids) and all(
            value.get("release_id") == release_id
            and value.get("worker_id") == worker_id
            and value.get("state") == "ready"
            and value.get("authenticated") is True
            and value.get("registered") is True
            and isinstance(generation, int)
            and generation >= 1
            and isinstance(value.get("heartbeats"), int)
            and value["heartbeats"] >= 1
            for value, worker_id, generation in zip(
                last, worker_ids, generations, strict=True
            )
        ):
            return min(generations)
        time.sleep(0.25)
    raise ExternalPiSlotError(f"external Pi candidate qualification failed: {last!r}")


def restart_supervisor_after_lease_expiry(
    environment: str,
    slot: str,
    release_id: str,
    initial_generation: int,
) -> int:
    """Run the crash/takeover transaction without termination-signal gaps."""
    watched = {signal.SIGTERM, signal.SIGINT}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, watched)
    try:
        return _restart_supervisor_after_lease_expiry(
            environment, slot, release_id, initial_generation
        )
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def _restart_supervisor_after_lease_expiry(
    environment: str,
    slot: str,
    release_id: str,
    initial_generation: int,
) -> int:
    """Crash only the supervisor and prove takeover after its durable lease expires.

    This helper is used before qualification sends any shadow requests, so a
    fully expired lease is also sufficient to stop both owned units if the
    supervisor cannot be recovered for the normal graceful drain path.
    """
    lease_seconds = protected_lease_seconds(environment)
    supervisor_unit = _supervisor_unit(environment, slot)
    subprocess.run(
        [
            "systemctl",
            "kill",
            "--kill-whom=main",
            "--signal=KILL",
            supervisor_unit,
        ],
        check=True,
    )
    # Restart=on-failure would otherwise reconnect the same live Node instance
    # immediately and renew its existing claim forever.  Cancel that scheduled
    # restart, leave the Node worker alive, and start a new supervisor only after
    # the last possible heartbeat lease has expired.
    subprocess.run(["systemctl", "stop", supervisor_unit], check=True)
    takeover_at = time.monotonic() + lease_seconds + 1

    def recover_takeover() -> int:
        remaining = takeover_at - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        subprocess.run(["systemctl", "start", supervisor_unit], check=True)
        deadline = time.monotonic() + 70
        last: dict = {}
        while time.monotonic() < deadline:
            last = _read_primary_status(environment, slot)
            generation = last.get("generation")
            expected_worker_ids = {
                f"{environment}-{slot}",
                replica_specs(environment, slot, "x" * 32)[0].worker_id,
            }
            if (
                last.get("release_id") == release_id
                and last.get("worker_id") in expected_worker_ids
                and last.get("state") == "ready"
                and last.get("authenticated") is True
                and last.get("registered") is True
                and type(generation) is int
                and generation > initial_generation
                and type(last.get("heartbeats")) is int
                and last["heartbeats"] >= 1
            ):
                return generation
            time.sleep(0.25)
        raise ExternalPiSlotError(
            f"external Pi lease-expiry restart did not advance generation: {last!r}"
        )

    try:
        return recover_takeover()
    except BaseException:
        try:
            recover_takeover()
        except BaseException as recovery_error:
            # A recovery start can commit a fresh lease before status
            # observation fails. Stop that supervisor first, then wait a
            # complete lease from this stop before directly stopping Node.
            subprocess.run(["systemctl", "stop", supervisor_unit], check=True)
            time.sleep(lease_seconds + 1)
            subprocess.run(
                ["systemctl", "stop", _worker_unit(environment, slot)], check=True
            )
            raise ExternalPiSlotError(
                "external Pi supervisor takeover failed; the expired, "
                "request-free qualification worker was stopped"
            ) from recovery_error
        raise


def _never_registered(
    status: dict,
    *,
    release_id: str,
    worker_id: str,
) -> bool:
    return (
        status.get("release_id") == release_id
        and status.get("worker_id") == worker_id
        and status.get("state") == "starting"
        and status.get("registered") is False
        and "generation" in status
        and status.get("generation") is None
    )


def _worker_stop_is_safe(
    previous: dict,
    current: dict,
    *,
    release_id: str,
    worker_id: str,
) -> bool:
    if (
        current.get("release_id") == release_id
        and current.get("worker_id") == worker_id
        and current.get("state") == "offline"
        and current.get("drained") is True
    ):
        return True
    return _never_registered(
        previous,
        release_id=release_id,
        worker_id=worker_id,
    ) and _never_registered(
        current,
        release_id=release_id,
        worker_id=worker_id,
    )


def _unit_is_inactive(unit: str) -> bool:
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "--property=ActiveState",
                "--value",
                unit,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() in {"inactive", "failed"}


def _worker_is_inactive(environment: str, slot: str) -> bool:
    return _unit_is_inactive(_worker_unit(environment, slot))


def _supervisor_is_inactive(environment: str, slot: str) -> bool:
    return _unit_is_inactive(_supervisor_unit(environment, slot))


def stop_slot(
    environment: str,
    slot: str,
    release_id: str,
    *,
    validated_orphan_release_ids: frozenset[str] = frozenset(),
) -> None:
    timeout_seconds = drain_stop_timeout_seconds(environment)
    draining_specs = _draining_replica_specs(environment, slot, "x" * 32, release_id)
    previous = _read_replica_statuses(environment, slot, draining_specs)
    legacy = not any(previous)
    if legacy:
        previous = (_read_status(environment, slot),)
    try:
        subprocess.run(
            ["systemctl", "stop", _supervisor_unit(environment, slot)],
            check=True,
            timeout=timeout_seconds,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ExternalPiSlotError("external Pi worker drain timed out") from error
    value = _read_replica_statuses(environment, slot, draining_specs)
    if legacy:
        value = (_read_status(environment, slot),)
        worker_ids = (f"{environment}-{slot}",)
    else:
        worker_ids = tuple(spec.worker_id for spec in draining_specs)
    if len(previous) == len(value) == len(worker_ids) and all(
        _worker_stop_is_safe(
            prior,
            current,
            release_id=release_id,
            worker_id=worker_id,
        )
        for prior, current, worker_id in zip(previous, value, worker_ids, strict=True)
    ):
        subprocess.run(
            ["systemctl", "stop", _worker_unit(environment, slot)], check=True
        )
        return
    if _worker_is_inactive(environment, slot):
        return
    try:
        _stop_proven_orphaned_worker_if_active(
            environment,
            slot,
            worker_active_proven=True,
            expected_release_id=release_id,
            validated_orphan_release_ids=validated_orphan_release_ids,
            draining_specs=draining_specs,
        )
    except ExternalPiSlotError as error:
        raise ExternalPiSlotError(
            "external Pi worker did not prove graceful drain"
        ) from error


def prepare_candidate(environment: str, slot: str, release_id: str) -> int:
    try:
        start_slot(environment, slot)
        first_generation = qualify_candidate(environment, slot, release_id)
        stop_slot(environment, slot, release_id)
        start_slot(environment, slot)
        restarted_generation = qualify_candidate(environment, slot, release_id)
        if restarted_generation <= first_generation:
            raise ExternalPiSlotError(
                "external Pi restart did not advance fencing generation"
            )
        return restarted_generation
    except (
        ExternalPiSlotError,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        try:
            stop_slot(environment, slot, release_id)
        except (ExternalPiSlotError, OSError, ValueError) as cleanup_error:
            raise ExternalPiSlotError(
                f"external Pi candidate cleanup failed: {cleanup_error}"
            ) from cleanup_error
        raise


def lifecycle_enabled(environment: str) -> bool:
    if environment not in ENVIRONMENT_SLOT_PORTS:
        return False
    values = _protected_environment_values(environment)
    raw_shadow = values.get("PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED", "false").lower()
    raw_supervisor = values.get(
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED", "false"
    ).lower()
    if raw_shadow not in {"true", "false"} or raw_supervisor not in {
        "true",
        "false",
    }:
        raise ExternalPiSlotError("external Pi lifecycle flags must be boolean")
    if raw_shadow != raw_supervisor:
        raise ExternalPiSlotError("external Pi shadow and supervisor flags disagree")
    return raw_shadow == "true"


def prepare_candidate_if_enabled(environment: str, slot: str, release_id: str) -> bool:
    if not lifecycle_enabled(environment):
        return False
    prepare_candidate(environment, slot, release_id)
    return True


def stop_slot_if_enabled(
    environment: str,
    slot: str,
    release_id: str,
    *,
    validated_orphan_release_ids: frozenset[str] = frozenset(),
) -> bool:
    if not lifecycle_enabled(environment):
        return False
    stop_slot(
        environment,
        slot,
        release_id,
        validated_orphan_release_ids=validated_orphan_release_ids,
    )
    return True
