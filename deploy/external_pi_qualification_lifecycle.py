#!/usr/bin/env python3
"""Transient, staging-only lifecycle for external Pi qualification replicas."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from deploy.external_pi_qualification_contract import (
        QUALIFICATION_SUPERVISOR_UNITS,
        QUALIFICATION_WORKER_IDS,
        QUALIFICATION_WORKER_UNITS,
        qualification_index,
    )
    from deploy.external_pi_runtime import external_pi_runtime_manifest
    from deploy.runtime import runtime_id, runtime_manifest
except ModuleNotFoundError:
    from external_pi_qualification_contract import (  # type: ignore[no-redef]
        QUALIFICATION_SUPERVISOR_UNITS,
        QUALIFICATION_WORKER_IDS,
        QUALIFICATION_WORKER_UNITS,
        qualification_index,
    )
    from external_pi_runtime import external_pi_runtime_manifest  # type: ignore[no-redef]
    from runtime import runtime_id, runtime_manifest  # type: ignore[no-redef]

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
STATUS_ROOT = Path(
    os.environ.get(
        "PWC_EXTERNAL_PI_QUALIFICATION_STATUS_ROOT",
        "/run/paperswithcode/external-pi-qualification",
    )
)
CONTRACT_VERSION = "external-pi-v1"
MAXIMUM_WORKER_STATUS_BYTES = 64 * 1024
OPERATION_COUNTER_NAMES = (
    "shadow_requests",
    "model_calls",
    "tool_calls",
    "provider_calls",
    "modal_calls",
    "billing_events",
)
_IMMUTABLE_STAGING_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")
_SUPERVISOR_PROTECTED_KEYS = (
    "PWC_DB_HOST",
    "PWC_DB_PORT",
    "PWC_DB_NAME",
    "PWC_DB_USER",
    "PWC_DB_PASSWORD",
    "PWC_DB_SEARCH_PATH",
    "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
)
_LIFECYCLE_DEFAULTS = {
    "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": "10",
    "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
    "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "60",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS": "60",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS": "1",
}


@dataclass(frozen=True, slots=True)
class QualificationReplica:
    index: int
    port: int
    maximum_sessions: int
    worker_id: str
    supervisor_unit: str
    worker_unit: str
    release: Path
    release_id: str
    runtime: Path
    node: Path
    entry_point: Path
    prompt: Path
    python: Path
    status_path: Path


class QualificationLifecycleError(RuntimeError):
    """A bounded qualification replica transition failed closed."""


@dataclass(frozen=True, slots=True)
class QualificationCleanupEvidence:
    registry_offline: bool
    supervisors_stopped_before_workers: bool
    units_removed: bool
    status_files_removed: bool
    ports_free: bool
    processes_gone: bool


def resolve_qualification_replica(
    environment: str,
    requested_release: str,
    index: int,
    port: int,
    maximum_sessions: int,
) -> QualificationReplica:
    if environment != "staging":
        raise ValueError("external Pi qualification lifecycle is staging-only")
    index = qualification_index(index, port, maximum_sessions)
    current = APP_ROOT / "environments/staging/current"
    if not current.is_symlink():
        raise ValueError("active staging release pointer is missing")
    release = current.resolve(strict=True)
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    release_id = manifest.get("release_id")
    if (
        release.parent != APP_ROOT / "releases"
        or _IMMUTABLE_STAGING_RELEASE.fullmatch(release.name) is None
        or release_id != release.name
        or release_id != requested_release
    ):
        raise ValueError("external Pi qualification requires the exact active release")
    descriptor = manifest.get("external_pi_runtime")
    if not isinstance(descriptor, dict):
        raise ValueError("release has no recorded external Pi runtime")
    identifier = descriptor.get("runtime_id")
    contract = descriptor.get("contract")
    if not isinstance(identifier, str) or not isinstance(contract, str):
        raise ValueError("release recorded external Pi runtime is invalid")
    external_runtime = APP_ROOT / "runtimes/external-pi" / identifier
    runtime_value = external_pi_runtime_manifest(
        external_runtime, expected_id=identifier, expected_contract=contract
    )
    python_runtime = APP_ROOT / "runtimes" / runtime_id(release)
    runtime_manifest(python_runtime)
    return QualificationReplica(
        index=index,
        port=port,
        maximum_sessions=maximum_sessions,
        worker_id=QUALIFICATION_WORKER_IDS[index],
        supervisor_unit=QUALIFICATION_SUPERVISOR_UNITS[index],
        worker_unit=QUALIFICATION_WORKER_UNITS[index],
        release=release,
        release_id=str(release_id),
        runtime=external_runtime,
        node=external_runtime / "node/bin/node",
        entry_point=external_runtime / str(runtime_value["entry_point"]),
        prompt=external_runtime / "assets/pi-system-prompt.txt",
        python=python_runtime / "bin/python",
        status_path=STATUS_ROOT / f"{QUALIFICATION_WORKER_IDS[index]}.json",
    )


def worker_environment(
    resolved: QualificationReplica,
    protected: dict[str, str],
    *,
    instance_id: str,
) -> dict[str, str]:
    token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise ValueError("external Pi worker token is missing or invalid")
    return {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": str(resolved.port),
        "PWC_EXTERNAL_PI_TOKEN": token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": str(resolved.maximum_sessions),
        "PWC_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
        "PWC_EXTERNAL_PI_INSTANCE_ID": instance_id,
        "PWC_EXTERNAL_PI_RELEASE_ID": resolved.release_id,
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
    }


def _bounded_lifecycle_values(protected: dict[str, str]) -> dict[str, str]:
    values = {
        key: protected.get(key, default) for key, default in _LIFECYCLE_DEFAULTS.items()
    }
    try:
        heartbeat = int(values["PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS"])
        lease = int(values["PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS"])
        startup = int(values["PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS"])
        drain = int(values["PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS"])
        poll = float(values["PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS"])
    except ValueError as error:
        raise ValueError("external Pi lifecycle settings must be numeric") from error
    if not (
        1 <= heartbeat <= 30
        and 5 <= lease <= 60
        and heartbeat < lease
        and 5 <= startup <= 120
        and 5 <= drain <= 300
        and 0.1 <= poll <= 5
    ):
        raise ValueError("external Pi lifecycle settings are outside protected bounds")
    return values


def supervisor_environment(
    resolved: QualificationReplica, protected: dict[str, str]
) -> dict[str, str]:
    token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise ValueError("external Pi worker token is missing or invalid")
    values = {
        key: protected[key] for key in _SUPERVISOR_PROTECTED_KEYS if key in protected
    }
    values.update(_bounded_lifecycle_values(protected))
    values.update(
        {
            "PWC_ENVIRONMENT": "staging",
            "PWC_RELEASE_ID": resolved.release_id,
            "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
            "PWC_CHAT_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
            "PWC_CHAT_EXTERNAL_PI_WORKER_URL": f"http://127.0.0.1:{resolved.port}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": CONTRACT_VERSION,
            "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(resolved.maximum_sessions),
            "PWC_EXTERNAL_PI_STATUS_PATH": str(resolved.status_path),
            "PWC_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
        }
    )
    return values


def _launcher_arguments(resolved: QualificationReplica) -> list[str]:
    return [
        "staging",
        resolved.release_id,
        str(resolved.index),
        str(resolved.port),
        str(resolved.maximum_sessions),
    ]


def _unit_description(resolved: QualificationReplica, role: str, owner_id: str) -> str:
    return (
        "Papers With Code staging external Pi qualification "
        f"{role} {resolved.index:02d} owner {owner_id}"
    )


def _worker_start_command(
    resolved: QualificationReplica, *, owner_id: str
) -> list[str]:
    return [
        "systemd-run",
        "--quiet",
        "--service-type=exec",
        f"--description={_unit_description(resolved, 'worker', owner_id)}",
        f"--unit={resolved.worker_unit}",
        "--collect",
        "--uid=pwc-external-pi-staging",
        "--gid=pwc-external-pi-staging",
        f"--working-directory={resolved.release}",
        "--property=EnvironmentFile=/etc/paperswithcode/external-pi-worker.env",
        "--property=NoNewPrivileges=true",
        "--property=PrivateTmp=true",
        "--property=ProtectHome=true",
        "--property=ProtectSystem=strict",
        "--property=ProtectProc=invisible",
        "--property=ProcSubset=pid",
        "--property=ReadOnlyPaths=/srv/paperswithcode",
        "--property=CPUQuota=400%",
        "--property=MemoryMax=4294967296",
        "--property=TasksMax=512",
        "--property=Restart=on-failure",
        "--property=RestartSec=3",
        "--property=TimeoutStartSec=75",
        "--property=TimeoutStopSec=15",
        "/usr/bin/python3",
        str(resolved.release / "deploy/external_pi_qualification_worker_launcher.py"),
        *_launcher_arguments(resolved),
    ]


def _supervisor_start_command(
    resolved: QualificationReplica, *, owner_id: str
) -> list[str]:
    return [
        "systemd-run",
        "--quiet",
        "--service-type=exec",
        f"--description={_unit_description(resolved, 'supervisor', owner_id)}",
        f"--unit={resolved.supervisor_unit}",
        "--collect",
        "--uid=pwc-staging",
        "--gid=pwc-staging",
        f"--working-directory={resolved.release}",
        "--property=EnvironmentFile=/etc/paperswithcode/staging.env",
        "--property=NoNewPrivileges=true",
        "--property=PrivateTmp=true",
        "--property=ProtectHome=true",
        "--property=ProtectSystem=strict",
        "--property=ReadOnlyPaths=/srv/paperswithcode",
        "--property=RuntimeDirectory=paperswithcode/external-pi-qualification",
        "--property=RuntimeDirectoryMode=0750",
        "--property=RuntimeDirectoryPreserve=yes",
        "--property=ReadWritePaths=/var/lib/paperswithcode/staging /run/paperswithcode/external-pi-qualification",
        "--property=CPUQuota=50%",
        "--property=MemoryMax=536870912",
        "--property=TasksMax=64",
        "--property=Restart=on-failure",
        "--property=RestartSec=3",
        "--property=TimeoutStartSec=75",
        "--property=TimeoutStopSec=330",
        "--property=KillSignal=SIGTERM",
        "/usr/bin/python3",
        str(
            resolved.release / "deploy/external_pi_qualification_supervisor_launcher.py"
        ),
        *_launcher_arguments(resolved),
    ]


def _read_status(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _unit_state(unit: str, *, runner: Callable) -> tuple[str, str]:
    result = runner(
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            unit,
        ],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )
    lines = result.stdout.splitlines() if result.returncode == 0 else []
    if len(lines) != 2:
        raise QualificationLifecycleError(
            f"external Pi qualification unit state is unavailable: {unit}"
        )
    return lines[0], lines[1]


def _unit_owner(unit: str, *, runner: Callable) -> str | None:
    result = runner(
        ["systemctl", "show", "--property=Description", "--value", unit],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )
    value = result.stdout.strip() if result.returncode == 0 else ""
    return value or None


def start_replica(
    resolved: QualificationReplica,
    *,
    runner: Callable = subprocess.run,
    owner_id: str | None = None,
) -> None:
    """Start one exact transient pair and clean partial startup on every failure."""
    qualification_index(resolved.index, resolved.port, resolved.maximum_sessions)
    owner_id = str(uuid.uuid4()) if owner_id is None else owner_id
    if re.fullmatch(r"[A-Za-z0-9-]{1,64}", owner_id) is None:
        raise ValueError("external Pi qualification lifecycle owner is invalid")
    states = {
        unit: _unit_state(unit, runner=runner)
        for unit in (resolved.supervisor_unit, resolved.worker_unit)
    }
    if any(state != ("not-found", "inactive") for state in states.values()):
        raise QualificationLifecycleError(
            f"external Pi qualification exact unit already exists: {states!r}"
        )
    if not _port_is_free("127.0.0.1", resolved.port):
        raise QualificationLifecycleError(
            "external Pi qualification port is occupied before startup"
        )
    owned_units: set[str] = set()
    try:
        runner(
            _worker_start_command(resolved, owner_id=owner_id),
            check=True,
            timeout=75,
        )
        owned_units.add(resolved.worker_unit)
        resolved.status_path.unlink(missing_ok=True)
        runner(
            _supervisor_start_command(resolved, owner_id=owner_id),
            check=True,
            timeout=75,
        )
        owned_units.add(resolved.supervisor_unit)
    except BaseException:
        attempted_unit = (
            resolved.worker_unit if not owned_units else resolved.supervisor_unit
        )
        role = "worker" if attempted_unit == resolved.worker_unit else "supervisor"
        expected_owner = _unit_description(resolved, role, owner_id)
        if (
            _unit_state(attempted_unit, runner=runner) != ("not-found", "inactive")
            and _unit_owner(attempted_unit, runner=runner) == expected_owner
        ):
            owned_units.add(attempted_unit)
        if owned_units:
            try:
                cleanup_replica(
                    resolved,
                    generation=None,
                    owned_units=owned_units,
                    runner=runner,
                )
            except BaseException as cleanup_error:
                raise QualificationLifecycleError(
                    "external Pi qualification retained bounded recovery evidence; "
                    "an owned worker remains running"
                ) from cleanup_error
        raise


def wait_ready(
    resolved: QualificationReplica,
    *,
    minimum_generation: int = 0,
    timeout_seconds: float = 65,
    read_status: Callable[[Path], dict] = _read_status,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    if not 0 < timeout_seconds <= 120:
        raise ValueError("external Pi qualification readiness timeout is not bounded")
    deadline = monotonic() + timeout_seconds
    last: dict = {}
    while monotonic() < deadline:
        last = read_status(resolved.status_path)
        generation = last.get("generation")
        if (
            last.get("release_id") == resolved.release_id
            and last.get("worker_id") == resolved.worker_id
            and last.get("state") == "ready"
            and last.get("authenticated") is True
            and last.get("registered") is True
            and type(generation) is int
            and generation > minimum_generation
            and type(last.get("heartbeats")) is int
            and last["heartbeats"] >= 1
        ):
            return generation
        sleep(0.25)
    raise QualificationLifecycleError(
        f"external Pi qualification replica readiness timed out: {last!r}"
    )


def replica_status(
    resolved: QualificationReplica, *, runner: Callable = subprocess.run
) -> dict:
    """Return exact transient unit and bounded durable status evidence."""
    units = {}
    for name in (resolved.supervisor_unit, resolved.worker_unit):
        result = runner(
            ["systemctl", "show", "--property=ActiveState", "--value", name],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        units[name] = result.stdout.strip() if result.returncode == 0 else "unknown"
    return {"units": units, "status": _read_status(resolved.status_path)}


def _authenticated_unclaimed_worker_is_safe(
    resolved: QualificationReplica,
) -> bool:
    token = os.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        return False
    request = urllib.request.Request(
        f"http://127.0.0.1:{resolved.port}/v1/status",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read(MAXIMUM_WORKER_STATUS_BYTES + 1)
            if len(payload) > MAXIMUM_WORKER_STATUS_BYTES:
                return False
            status = json.loads(payload)
    except (OSError, ValueError, urllib.error.URLError):
        return False
    counters = status.get("operation_counters") if isinstance(status, dict) else None
    return (
        isinstance(status, dict)
        and status.get("protocol") == CONTRACT_VERSION
        and status.get("worker_id") == resolved.worker_id
        and status.get("release_id") == resolved.release_id
        and status.get("state") == "ready"
        and "worker_generation" in status
        and status.get("worker_generation") is None
        and type(status.get("active_sessions")) is int
        and status.get("active_sessions") == 0
        and type(status.get("maximum_sessions")) is int
        and status.get("maximum_sessions") == resolved.maximum_sessions
        and isinstance(counters, dict)
        and set(counters) == set(OPERATION_COUNTER_NAMES)
        and all(
            type(counters[name]) is int and counters[name] == 0
            for name in OPERATION_COUNTER_NAMES
        )
    )


def cleanup_replica(
    resolved: QualificationReplica,
    *,
    generation: int | None,
    owned_units: set[str] | frozenset[str] | None = None,
    runner: Callable = subprocess.run,
    read_status: Callable[[Path], dict] = _read_status,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    port_is_free: Callable[[str, int], bool] = _port_is_free,
    timeout_seconds: float = 305,
) -> QualificationCleanupEvidence:
    """Idempotently drain and remove one exact pair, then prove postconditions."""
    if not 0 < timeout_seconds <= 330:
        raise ValueError("external Pi qualification cleanup timeout is not bounded")
    qualification_index(resolved.index, resolved.port, resolved.maximum_sessions)
    owned = (
        {resolved.supervisor_unit, resolved.worker_unit}
        if owned_units is None
        else set(owned_units)
    )
    allowed = {resolved.supervisor_unit, resolved.worker_unit}
    if not owned <= allowed:
        raise ValueError("external Pi qualification cleanup ownership is invalid")
    supervisor_owned = resolved.supervisor_unit in owned
    worker_owned = resolved.worker_unit in owned
    if supervisor_owned:
        runner(
            ["systemctl", "stop", resolved.supervisor_unit],
            check=False,
            timeout=timeout_seconds,
        )
        if _unit_state(resolved.supervisor_unit, runner=runner)[1] not in {
            "inactive",
            "failed",
        }:
            raise QualificationLifecycleError(
                "external Pi qualification supervisor did not stop"
            )
    registry_offline = False
    if not supervisor_owned:
        registry_offline = _unit_state(resolved.supervisor_unit, runner=runner) == (
            "not-found",
            "inactive",
        )
        if not registry_offline:
            raise QualificationLifecycleError(
                "external Pi qualification has ambiguous bounded recovery evidence: "
                "an unowned supervisor exists"
            )
    if (
        generation is None
        and not registry_offline
        and (supervisor_owned or worker_owned)
    ):
        last = read_status(resolved.status_path)
        observed_generation = last.get("generation")
        durable_registry_offline = supervisor_owned and (
            last.get("release_id") == resolved.release_id
            and last.get("worker_id") == resolved.worker_id
            and (
                (
                    type(observed_generation) is int
                    and observed_generation >= 1
                    and last.get("state") == "offline"
                    and last.get("drained") is True
                )
                or (
                    observed_generation is None
                    and last.get("state") == "starting"
                    and last.get("registered") is False
                )
            )
        )
        registry_offline = durable_registry_offline or (
            worker_owned and _authenticated_unclaimed_worker_is_safe(resolved)
        )
        if not registry_offline:
            raise QualificationLifecycleError(
                f"external Pi qualification has ambiguous bounded recovery evidence: {last!r}"
            )
    elif supervisor_owned and generation is not None:
        deadline = monotonic() + timeout_seconds
        last: dict = {}
        while monotonic() < deadline:
            last = read_status(resolved.status_path)
            if (
                last.get("release_id") == resolved.release_id
                and last.get("worker_id") == resolved.worker_id
                and last.get("generation") == generation
                and last.get("state") == "offline"
                and last.get("drained") is True
            ):
                registry_offline = True
                break
            sleep(0.25)
        if not registry_offline:
            raise QualificationLifecycleError(
                f"external Pi qualification drain proof timed out: {last!r}"
            )
    if worker_owned:
        runner(
            ["systemctl", "stop", resolved.worker_unit],
            check=False,
            timeout=15,
        )
    for unit in (resolved.supervisor_unit, resolved.worker_unit):
        if unit in owned:
            runner(
                ["systemctl", "reset-failed", unit],
                check=False,
                timeout=10,
            )
    resolved.status_path.unlink(missing_ok=True)
    units_removed = True
    for unit in (resolved.supervisor_unit, resolved.worker_unit):
        if unit in owned and _unit_state(unit, runner=runner) != (
            "not-found",
            "inactive",
        ):
            units_removed = False
    ports_free = port_is_free("127.0.0.1", resolved.port)
    if not ports_free or not units_removed:
        raise QualificationLifecycleError(
            "external Pi qualification postconditions failed after cleanup"
        )
    return QualificationCleanupEvidence(
        registry_offline=registry_offline,
        supervisors_stopped_before_workers=True,
        units_removed=units_removed,
        status_files_removed=not resolved.status_path.exists(),
        ports_free=ports_free,
        processes_gone=units_removed and ports_free,
    )
