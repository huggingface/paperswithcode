#!/usr/bin/env python3
"""Release-managed lifecycle for the staging external Pi shadow worker."""

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
from dataclasses import dataclass
from pathlib import Path

try:
    from deploy.external_pi_runtime import external_pi_runtime_manifest
except ModuleNotFoundError:
    from external_pi_runtime import external_pi_runtime_manifest  # type: ignore[no-redef]

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
STATUS_ROOT = Path(
    os.environ.get("PWC_EXTERNAL_PI_STATUS_ROOT", "/run/paperswithcode/external-pi")
)
WORKER_CONFIG = CONFIG_ROOT / "external-pi-worker.env"
WORKER_USER = "pwc-external-pi"
SLOT_PORTS = {"blue": 8766, "green": 8767}
MAXIMUM_SESSIONS = 32
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


def resolve_external_pi_slot(environment: str, slot: str) -> ExternalPiSlot:
    if environment != "staging":
        raise ValueError("external Pi slot lifecycle is staging-only")
    if slot not in SLOT_PORTS:
        raise ValueError("external Pi deployment slot is invalid")
    release_link = APP_ROOT / "environments/staging/slots" / slot / "release"
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
    return ExternalPiSlot(
        slot=slot,
        port=SLOT_PORTS[slot],
        worker_id=f"staging-{slot}",
        release=release,
        release_id=str(manifest["release_id"]),
        runtime=runtime,
        node=runtime / "node/bin/node",
        entry_point=entry_point,
        prompt=runtime / "assets/pi-system-prompt.txt",
        status_path=STATUS_ROOT / f"staging-{slot}.json",
    )


def node_environment(
    resolved: ExternalPiSlot,
    protected: dict[str, str],
    *,
    instance_id: str,
) -> dict[str, str]:
    token = protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32:
        raise ValueError("external Pi worker token is missing or too short")
    state_root = protected.get("PWC_EXTERNAL_PI_STATE_ROOT", "")
    if state_root != f"/run/paperswithcode/external-pi-{resolved.slot}":
        raise ValueError("external Pi worker state root is invalid")
    return {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": str(resolved.port),
        "PWC_EXTERNAL_PI_TOKEN": token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": str(MAXIMUM_SESSIONS),
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
    values = {
        key: protected[key] for key in _SUPERVISOR_PROTECTED_KEYS if key in protected
    }
    values.update(
        {
            "PWC_ENVIRONMENT": "staging",
            "PWC_RELEASE_ID": resolved.release_id,
            "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
            "PWC_CHAT_EXTERNAL_PI_WORKER_ID": resolved.worker_id,
            "PWC_CHAT_EXTERNAL_PI_WORKER_URL": f"http://127.0.0.1:{resolved.port}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": CONTRACT_VERSION,
            "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(MAXIMUM_SESSIONS),
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
    if environment != "staging" or slot not in SLOT_PORTS:
        raise ValueError("external Pi slot lifecycle is staging-only")
    return f"paperswithcode-staging-external-pi@{slot}.service"


def _worker_unit(environment: str, slot: str) -> str:
    if environment != "staging" or slot not in SLOT_PORTS:
        raise ValueError("external Pi slot lifecycle is staging-only")
    return f"paperswithcode-staging-external-pi-worker@{slot}.service"


def _status_path(environment: str, slot: str) -> Path:
    if environment != "staging" or slot not in SLOT_PORTS:
        raise ValueError("external Pi slot lifecycle is staging-only")
    return STATUS_ROOT / f"staging-{slot}.json"


def _read_status(environment: str, slot: str) -> dict:
    path = _status_path(environment, slot)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def slot_status(environment: str, slot: str) -> dict:
    """Return the release-managed lifecycle evidence for one staging slot."""
    return _read_status(environment, slot)


def _protected_staging_values() -> dict[str, str]:
    path = CONFIG_ROOT / "staging.env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, raw = line.partition("=")
        if separator:
            values[key] = raw.strip().strip("\"'")
    return values


def drain_stop_timeout_seconds(environment: str) -> float:
    """Bound systemctl by the protected drain contract plus fixed teardown time."""
    if environment != "staging":
        raise ValueError("external Pi drain lifecycle is staging-only")
    values = _protected_staging_values()
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
    if environment != "staging":
        raise ValueError("external Pi lease lifecycle is staging-only")
    raw = _protected_staging_values().get("PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS", "30")
    try:
        lease_seconds = int(raw)
    except ValueError as error:
        raise ValueError("external Pi lease configuration must be numeric") from error
    if not 5 <= lease_seconds <= 60:
        raise ValueError("external Pi lease seconds are outside protected bounds")
    return lease_seconds


def sync_worker_environment(environment: str) -> None:
    """Publish only the worker token to the dedicated protected environment."""
    if environment != "staging":
        raise ValueError("external Pi worker environment is staging-only")
    token = _protected_staging_values().get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise ValueError("external Pi worker token is missing or invalid")
    temporary = WORKER_CONFIG.with_name(f".{WORKER_CONFIG.name}.new-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            handle.write(f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={token}\n")
        os.chown(temporary, 0, grp.getgrnam(WORKER_USER).gr_gid)
        os.replace(temporary, WORKER_CONFIG)
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
) -> None:
    if not worker_active_proven and _worker_is_inactive(environment, slot):
        return
    if not _supervisor_is_inactive(environment, slot):
        raise ExternalPiSlotError("external Pi supervisor is still active")
    token = _protected_staging_values().get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
    if len(token) < 32:
        raise ExternalPiSlotError("external Pi worker token is unavailable")
    request = urllib.request.Request(
        f"http://127.0.0.1:{SLOT_PORTS[slot]}/v1/status",
        headers={"Authorization": f"Bearer {token}"},
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
    identity_and_capacity_match = (
        isinstance(status, dict)
        and status.get("protocol") == CONTRACT_VERSION
        and status.get("worker_id") == f"staging-{slot}"
        and type(status.get("active_sessions")) is int
        and status.get("active_sessions") == 0
        and type(status.get("maximum_sessions")) is int
        and status.get("maximum_sessions") == MAXIMUM_SESSIONS
    )
    counters = status.get("operation_counters") if isinstance(status, dict) else None
    trusted_release_ids = validated_orphan_release_ids
    if expected_release_id is not None:
        trusted_release_ids = trusted_release_ids | {expected_release_id}
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
    if not identity_and_capacity_match or not (
        status.get("state") == "draining" or request_free_unclaimed
    ):
        raise ExternalPiSlotError(
            "external Pi active worker is not proven safe to restart"
        )
    subprocess.run(["systemctl", "stop", _worker_unit(environment, slot)], check=True)
    if not _worker_is_inactive(environment, slot):
        raise ExternalPiSlotError("external Pi active worker did not stop")


def start_slot(environment: str, slot: str) -> None:
    _status_path(environment, slot).unlink(missing_ok=True)
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
    last: dict = {}
    while time.monotonic() < deadline:
        last = _read_status(environment, slot)
        generation = last.get("generation")
        if (
            last.get("release_id") == release_id
            and last.get("worker_id") == f"staging-{slot}"
            and last.get("state") == "ready"
            and last.get("authenticated") is True
            and last.get("registered") is True
            and isinstance(generation, int)
            and generation >= 1
            and isinstance(last.get("heartbeats"), int)
            and last["heartbeats"] >= 1
        ):
            return generation
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
            last = _read_status(environment, slot)
            generation = last.get("generation")
            if (
                last.get("release_id") == release_id
                and last.get("worker_id") == f"staging-{slot}"
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
    previous = _read_status(environment, slot)
    try:
        subprocess.run(
            ["systemctl", "stop", _supervisor_unit(environment, slot)],
            check=True,
            timeout=timeout_seconds,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ExternalPiSlotError("external Pi worker drain timed out") from error
    value = _read_status(environment, slot)
    if _worker_stop_is_safe(
        previous,
        value,
        release_id=release_id,
        worker_id=f"staging-{slot}",
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
    if environment != "staging":
        return False
    values = _protected_staging_values()
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
