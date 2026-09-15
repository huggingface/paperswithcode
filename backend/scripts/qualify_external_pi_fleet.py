"""Root-operated staging controller for transient external Pi qualification."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from backend.loadtests.external_pi_fleet_core import (
    MIN_PROJECTED_MEM_AVAILABLE_BYTES,
    CleanupEvidence,
    FleetQualificationReport,
    FleetFailureCode,
    FleetFailureStage,
    FleetRecoveryReport,
    FleetReplica,
    FleetRoundReport,
    FleetRunRefused,
    FleetSafetyConfig,
    FleetShape,
    FleetShapeName,
    ForbiddenActivity,
    HostResourceSnapshot,
    PortState,
    RecoveryReplicaEvidence,
    ResourceEvidence,
    ResourcePreflight,
    UnitResourceEvidence,
    WorkerEvidence,
    aggregate_round,
    build_completed_shape_report,
    build_final_report,
    build_resource_refused_shape_report,
    publish_fleet_report,
    qualification_unit_names,
    resolve_fleet_shape,
    route_ordinal,
    validate_fleet_preflight,
    validate_persistent_transport_manifest,
)
from backend.services.chat_external_pi_shadow import ExternalPiWorkerStatus
from deploy import external_pi_qualification_lifecycle as lifecycle
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_PORTS,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
    QUALIFICATION_WORKER_UNITS,
)

HOST_CPU_AGGREGATE_SECONDS = 1.0


class FleetOperator(Protocol):
    runtime_id: str

    def revalidate(self, shape: FleetShape, active: Sequence[object]) -> None: ...

    def resource_preflight(self, shape: FleetShape) -> ResourcePreflight: ...

    def resolve(self, shape: FleetShape, index: int): ...

    def start(self, resolved) -> None: ...

    def wait_ready(self, resolved) -> int: ...

    def prepare_round(self) -> None: ...

    def run_round(
        self,
        name: str,
        workers: tuple[WorkerEvidence, ...],
        *,
        expected_users: int,
        abort_requested: Callable[[], bool],
    ) -> FleetRoundReport: ...

    def sample_resources(self, shape: FleetShape) -> ResourceEvidence: ...

    def cleanup(self, resolved, generation: int | None): ...

    def cleanup_postconditions(self, shape: FleetShape) -> CleanupEvidence: ...

    def set_owner(self, owner_id: str) -> None: ...

    def owned_units(self, resolved) -> tuple[str, ...]: ...

    def recovery_postconditions(
        self, resolved, owned_units: tuple[str, ...]
    ) -> tuple[CleanupEvidence, tuple[str, ...]]: ...


@dataclass(slots=True)
class AttemptedReplica:
    resolved: object
    generation: int | None = None
    owned_units: tuple[str, ...] = ()


@dataclass(slots=True)
class _FailureDiagnostic:
    stage: FleetFailureStage = "replica_lifecycle"
    code: FleetFailureCode = "replica_lifecycle_failed"
    captured: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def mark(self, stage: FleetFailureStage, code: FleetFailureCode) -> None:
        with self.lock:
            if not self.captured:
                self.stage = stage
                self.code = code

    def capture(
        self,
        stage: FleetFailureStage | None = None,
        code: FleetFailureCode | None = None,
    ) -> None:
        with self.lock:
            if self.captured:
                return
            if stage is not None and code is not None:
                self.stage = stage
                self.code = code
            self.captured = True


class _FleetOperationFailure(Exception):
    def __init__(
        self,
        stage: FleetFailureStage,
        code: FleetFailureCode,
        cause: BaseException,
    ) -> None:
        super().__init__("external Pi fleet operation failed")
        self.stage = stage
        self.code = code
        self.cause = cause


class FleetQualificationInterrupted(FleetRunRefused):
    """A normal operator signal interrupted the qualification transaction."""

    def __init__(self, signal_number: int):
        super().__init__(
            f"external Pi fleet qualification interrupted by signal {signal_number}"
        )
        self.signal_number = signal_number


@contextlib.contextmanager
def qualification_signal_context():
    """Convert normal termination into cleanup-preserving exceptions."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("qualification signal handlers require the main thread")
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {number: signal.getsignal(number) for number in watched}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    interrupted = False

    def interrupt(signal_number, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        raise FleetQualificationInterrupted(signal_number)

    try:
        for number in watched:
            signal.signal(number, interrupt)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        try:
            for number, handler in previous.items():
                signal.signal(number, handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)


def _listener_hosts(port: int) -> tuple[str, ...]:
    hosts: set[str] = set()
    for path, family in (
        (Path("/proc/net/tcp"), socket.AF_INET),
        (Path("/proc/net/tcp6"), socket.AF_INET6),
    ):
        for line in path.read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            address, encoded_port = fields[1].split(":")
            if int(encoded_port, 16) != port:
                continue
            packed = bytes.fromhex(address)
            if family == socket.AF_INET:
                packed = packed[::-1]
            else:
                packed = b"".join(
                    packed[index : index + 4][::-1]
                    for index in range(0, len(packed), 4)
                )
            hosts.add(socket.inet_ntop(family, packed))
    return tuple(sorted(hosts))


class SystemFleetOperator:
    """Fresh host-state adapter for the root qualification controller."""

    _REMOTE_FLAGS = (
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED",
        "PWC_CHAT_REMOTE_BASH_ENABLED",
        "PWC_CHAT_REMOTE_READ_ENABLED",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED",
    )

    def __init__(
        self,
        *,
        release_id: str,
        app_root: Path = Path("/srv/paperswithcode"),
        status_root: Path = Path("/run/paperswithcode/external-pi"),
        qualification_status_root: Path = lifecycle.STATUS_ROOT,
        environ: Mapping[str, str] = os.environ,
        listener_hosts: Callable[[int], tuple[str, ...]] = _listener_hosts,
        runner: Callable = subprocess.run,
        http_get: Callable = httpx.get,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.release_id = release_id
        self.app_root = app_root
        self.status_root = status_root
        self.qualification_status_root = qualification_status_root
        self.environ = environ
        self.listener_hosts = listener_hosts
        self.runner = runner
        self.http_get = http_get
        self.sleep = sleep
        self.owner_id = str(uuid.uuid4())
        self._prompt_path: Path | None = None
        self._round_runner: Callable | None = None
        self._unit_cpu_state: dict[str, tuple[int, float]] = {}
        self.runtime_id = self._manifest()["external_pi_runtime"]["runtime_id"]

    def set_owner(self, owner_id: str) -> None:
        if (
            not owner_id
            or len(owner_id) > 64
            or any(
                not (character.isalnum() or character == "-") for character in owner_id
            )
        ):
            raise FleetRunRefused("external Pi fleet owner marker is invalid")
        self.owner_id = owner_id

    def _unit_metadata(self, unit: str) -> tuple[str, str, str]:
        result = self.runner(
            [
                "systemctl",
                "show",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=Description",
                unit,
            ],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ("unknown", "unknown", "")
        values = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        return (
            values.get("LoadState", "unknown"),
            values.get("ActiveState", "unknown"),
            values.get("Description", ""),
        )

    def _manifest(self) -> dict:
        current = self.app_root / "environments/staging/current"
        if not current.is_symlink():
            raise FleetRunRefused("external Pi fleet active release is unavailable")
        release = current.resolve(strict=True)
        if (
            release.parent != self.app_root / "releases"
            or release.name != self.release_id
        ):
            raise FleetRunRefused(
                "external Pi fleet requires the exact active staging release"
            )
        manifest = json.loads(
            release.joinpath("release.json").read_text(encoding="utf-8")
        )
        descriptor = manifest.get("external_pi_runtime")
        if (
            manifest.get("release_id") != self.release_id
            or not isinstance(descriptor, dict)
            or not isinstance(descriptor.get("runtime_id"), str)
        ):
            raise FleetRunRefused("external Pi fleet release manifest is invalid")
        return manifest

    def _active_worker(self) -> tuple[str, bool]:
        staging = self.app_root / "environments/staging"
        active = staging / "active"
        if not active.is_symlink():
            raise FleetRunRefused("external Pi fleet active worker is unavailable")
        target = active.resolve(strict=True)
        slot = next(
            (
                name
                for name in ("blue", "green")
                if target == (staging / "slots" / name).resolve(strict=True)
            ),
            None,
        )
        if slot is None:
            raise FleetRunRefused("external Pi fleet active worker is invalid")
        slot_release = target.joinpath("release").resolve(strict=True)
        current_release = staging.joinpath("current").resolve(strict=True)
        status = json.loads(
            self.status_root.joinpath(f"staging-{slot}.json").read_text(
                encoding="utf-8"
            )
        )

        def unit_active(unit: str) -> bool:
            result = self.runner(
                [
                    "systemctl",
                    "show",
                    "--property=ActiveState",
                    "--value",
                    unit,
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0 and result.stdout.strip() == "active"

        units_active = all(
            unit_active(unit)
            for unit in (
                f"paperswithcode-staging-external-pi@{slot}.service",
                f"paperswithcode-staging-external-pi-worker@{slot}.service",
            )
        )
        healthy = (
            units_active
            and slot_release == current_release
            and status.get("release_id") == self.release_id
            and status.get("worker_id") == f"staging-{slot}"
            and status.get("state") == "ready"
            and status.get("authenticated") is True
            and status.get("registered") is True
            and type(status.get("generation")) is int
            and status["generation"] >= 1
        )
        try:
            response = self.http_get(
                f"http://127.0.0.1:{8766 if slot == 'blue' else 8767}/v1/status",
                headers={
                    "Authorization": "Bearer "
                    + self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
                },
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
            )
            response.raise_for_status()
            live = ExternalPiWorkerStatus.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise FleetRunRefused(
                "external Pi fleet active worker health is invalid"
            ) from None
        counters = live.operation_counters
        healthy = healthy and (
            live.worker_id == f"staging-{slot}"
            and live.release_id == self.release_id
            and live.state == "ready"
            and live.active_sessions == 0
            and live.maximum_sessions == 8
            and live.worker_generation == status.get("generation")
            and not live.capability_evidence.provider_credentials_present
            and not live.capability_evidence.modal_credentials_present
            and live.capability_evidence.registered_tool_count == 0
            and not any(
                (
                    counters.model_calls,
                    counters.tool_calls,
                    counters.provider_calls,
                    counters.modal_calls,
                    counters.billing_events,
                )
            )
        )
        if not healthy:
            raise FleetRunRefused("external Pi fleet active worker health is invalid")
        return f"staging-{slot}", healthy

    def revalidate(self, shape: FleetShape, active: Sequence[object]) -> None:
        self._manifest()
        active_worker_id, active_worker_healthy = self._active_worker()
        admission = (
            self.environ.get("PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED") != "false"
        )
        executor = self.environ.get("PWC_CHAT_SANDBOX_EXECUTOR_ENABLED") != "false"
        remote = any(self.environ.get(name) != "false" for name in self._REMOTE_FLAGS)
        config = FleetSafetyConfig(
            environment="staging",
            requested_release=self.release_id,
            active_release=self.release_id,
            external_admission_enabled=admission,
            executor_routing_enabled=executor,
            remote_execution_enabled=remote,
            active_worker_id=active_worker_id,
            active_worker_healthy=active_worker_healthy,
            worker_token=self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""),
        )
        validate_fleet_preflight(
            config,
            shape,
            tuple(
                PortState(replica.port, "127.0.0.1", True) for replica in shape.replicas
            ),
        )
        active_replicas = tuple(
            FleetReplica(item.worker_id, item.port) for item in active
        )
        if active_replicas:
            route_ordinal(0, active_replicas)
        active_by_port = {
            item.port: evidence
            for item, evidence in zip(active_replicas, active, strict=True)
        }
        active_ids = {item.worker_id for item in active_replicas}
        if not active_ids <= {replica.worker_id for replica in shape.replicas}:
            raise FleetRunRefused(
                "external Pi fleet active replica is outside the current shape"
            )
        for index, worker_id in enumerate(QUALIFICATION_WORKER_IDS):
            expected = (
                (QUALIFICATION_SUPERVISOR_UNITS[index], "supervisor"),
                (QUALIFICATION_WORKER_UNITS[index], "worker"),
            )
            for unit, role in expected:
                load, state, description = self._unit_metadata(unit)
                if worker_id in active_ids:
                    owner = (
                        "Papers With Code staging external Pi qualification "
                        f"{role} {index:02d} owner {self.owner_id}"
                    )
                    if (load, state, description) != ("loaded", "active", owner):
                        raise FleetRunRefused(
                            "external Pi fleet qualification unit is not exact-owned active"
                        )
                elif (load, state) != ("not-found", "inactive"):
                    raise FleetRunRefused(
                        "external Pi fleet qualification unit is not absent"
                    )
        for port in QUALIFICATION_PORTS:
            hosts = self.listener_hosts(port)
            active_evidence = active_by_port.get(port)
            if active_evidence is not None:
                ready_observed = hasattr(active_evidence, "generation")
                if hosts not in (
                    (("127.0.0.1",),) if ready_observed else ((), ("127.0.0.1",))
                ):
                    raise FleetRunRefused(
                        "external Pi fleet active ports must remain loopback-only"
                    )
            elif hosts:
                raise FleetRunRefused(
                    "external Pi fleet inactive qualification ports must remain free"
                )

    def _systemctl_properties(self, unit: str, *names: str) -> dict[str, int]:
        result = self.runner(
            ["systemctl", "show", *(f"--property={name}" for name in names), unit],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {name: 0 for name in names}
        values: dict[str, int] = {}
        for line in result.stdout.splitlines():
            key, separator, raw = line.partition("=")
            if separator and key in names:
                try:
                    values[key] = int(raw)
                except ValueError:
                    values[key] = 0
        return {name: max(0, values.get(name, 0)) for name in names}

    @staticmethod
    def _mem_available_bytes() -> int:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                value = int(line.split()[1]) * 1024
                return min(value, 2**63 - 1)
        raise FleetRunRefused("external Pi fleet host memory evidence is unavailable")

    @staticmethod
    def _read_host_cpu() -> tuple[int, int]:
        fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        if fields[0] != "cpu" or len(fields) < 6:
            raise FleetRunRefused("external Pi fleet host CPU evidence is unavailable")
        counters = tuple(int(value) for value in fields[1:])
        return sum(counters), counters[3] + counters[4]

    def _sample_host_cpu_percent(
        self, interval_seconds: float = HOST_CPU_AGGREGATE_SECONDS
    ) -> float:
        if interval_seconds != HOST_CPU_AGGREGATE_SECONDS:
            raise FleetRunRefused("external Pi fleet CPU sample interval is invalid")
        before_total, before_idle = self._read_host_cpu()
        self.sleep(interval_seconds)
        after_total, after_idle = self._read_host_cpu()
        if after_total <= before_total:
            raise FleetRunRefused("external Pi fleet CPU sample did not advance")
        busy = (after_total - before_total) - (after_idle - before_idle)
        return max(0.0, min(100.0, busy * 100 / (after_total - before_total)))

    def resource_preflight(self, shape: FleetShape) -> ResourcePreflight:
        staging = self.app_root / "environments/staging"
        active = staging.joinpath("active").resolve(strict=True)
        slot = active.name
        if slot not in {"blue", "green"}:
            raise FleetRunRefused("external Pi fleet active worker is invalid")
        supervisor_memory = self._systemctl_properties(
            f"paperswithcode-staging-external-pi@{slot}.service", "MemoryCurrent"
        )["MemoryCurrent"]
        worker_memory = self._systemctl_properties(
            f"paperswithcode-staging-external-pi-worker@{slot}.service",
            "MemoryCurrent",
        )["MemoryCurrent"]
        cpu_percent = self._sample_host_cpu_percent(HOST_CPU_AGGREGATE_SECONDS)
        if supervisor_memory <= 0 or worker_memory <= 0:
            return ResourcePreflight("resource_refused", 0, cpu_percent, 80.0)
        session_scale = shape.sessions_per_worker / 8
        projected = int(
            shape.worker_count * (supervisor_memory + worker_memory * session_scale)
        )
        snapshot = HostResourceSnapshot(
            mem_available_bytes=self._mem_available_bytes(),
            projected_additional_bytes=min(projected, 2**63 - 1),
            cpu_percent=cpu_percent,
            cpu_guard_percent=80.0,
        )
        from backend.loadtests.external_pi_fleet_core import evaluate_resource_preflight

        return evaluate_resource_preflight(snapshot)

    def resolve(self, shape: FleetShape, index: int):
        resolved = lifecycle.resolve_qualification_replica(
            "staging",
            self.release_id,
            index,
            QUALIFICATION_PORTS[index],
            shape.sessions_per_worker,
        )
        if self._prompt_path is None:
            self._prompt_path = resolved.prompt
        elif self._prompt_path != resolved.prompt:
            raise FleetRunRefused("external Pi fleet runtime prompt changed")
        return resolved

    def start(self, resolved) -> None:
        lifecycle.start_replica(resolved, runner=self.runner, owner_id=self.owner_id)

    def wait_ready(self, resolved) -> int:
        return lifecycle.wait_ready(resolved)

    def _worker_status(self, worker: WorkerEvidence) -> ExternalPiWorkerStatus:
        token = self.environ.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "")
        try:
            response = self.http_get(
                f"http://127.0.0.1:{worker.port}/v1/status",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
                follow_redirects=False,
                trust_env=False,
            )
            response.raise_for_status()
            return ExternalPiWorkerStatus.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise FleetRunRefused(
                "external Pi fleet worker status is invalid"
            ) from None

    def _validate_worker_status(
        self, worker: WorkerEvidence, status: ExternalPiWorkerStatus
    ) -> None:
        counters = status.operation_counters
        if (
            status.worker_id != worker.worker_id
            or status.release_id != self.release_id
            or status.state != "ready"
            or status.active_sessions != 0
            or status.maximum_sessions != worker.maximum_sessions
            or status.worker_generation != worker.generation
            or status.capability_evidence.provider_credentials_present
            or status.capability_evidence.modal_credentials_present
            or status.capability_evidence.registered_tool_count != 0
            or any(
                (
                    counters.model_calls,
                    counters.tool_calls,
                    counters.provider_calls,
                    counters.modal_calls,
                    counters.billing_events,
                )
            )
        ):
            raise FleetRunRefused("external Pi fleet worker evidence is unsafe")

    def prepare_round(self) -> None:
        if self._round_runner is None:
            from backend.loadtests.external_pi_fleet_locustfile import (
                run_local_fleet_round,
            )

            self._round_runner = run_local_fleet_round

    def run_round(
        self,
        name: str,
        workers: tuple[WorkerEvidence, ...],
        *,
        expected_users: int,
        abort_requested: Callable[[], bool],
    ) -> FleetRoundReport:
        if self._prompt_path is None:
            raise FleetRunRefused("external Pi fleet runtime prompt is unavailable")
        if self._round_runner is None:
            raise FleetRunRefused("external Pi fleet round runtime is unavailable")
        try:
            before = tuple(self._worker_status(worker) for worker in workers)
            for worker, status in zip(workers, before, strict=True):
                self._validate_worker_status(worker, status)
        except BaseException as error:  # noqa: BLE001 - retain safe stage only
            raise _FleetOperationFailure(
                "worker_status", "worker_status_failed", error
            ) from error
        try:
            result = self._round_runner(
                replicas=tuple(
                    FleetReplica(worker.worker_id, worker.port) for worker in workers
                ),
                prompt=self._prompt_path.read_text(encoding="utf-8"),
                token=self.environ["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"],
                expected_users=expected_users,
                abort_requested=abort_requested,
            )
        except BaseException as error:  # noqa: BLE001 - retain safe stage only
            raise _FleetOperationFailure(
                "locust_round", "locust_round_failed", error
            ) from error
        try:
            after = tuple(self._worker_status(worker) for worker in workers)
            for worker, status in zip(workers, after, strict=True):
                self._validate_worker_status(worker, status)
        except BaseException as error:  # noqa: BLE001 - retain safe stage only
            raise _FleetOperationFailure(
                "worker_status", "worker_status_failed", error
            ) from error
        shadow_delta = sum(
            final.operation_counters.shadow_requests
            - initial.operation_counters.shadow_requests
            for initial, final in zip(before, after, strict=True)
        )
        if shadow_delta != expected_users:
            error = FleetRunRefused("external Pi fleet shadow counter is inconsistent")
            raise _FleetOperationFailure(
                "counter", "counter_mismatch", error
            ) from error
        return aggregate_round(
            name=name,
            expected_users=expected_users,
            observations=result.observations,
            protocol_errors=result.protocol_errors,
            transport_errors=result.transport_errors,
            forbidden_activity=ForbiddenActivity(),
        )

    def sample_resources(self, shape: FleetShape) -> ResourceEvidence:
        now = time.monotonic()
        unit_peaks = []
        for unit in qualification_unit_names(shape):
            values = self._systemctl_properties(
                unit, "MemoryPeak", "CPUUsageNSec", "TasksCurrent"
            )
            previous = self._unit_cpu_state.get(unit)
            self._unit_cpu_state[unit] = (values["CPUUsageNSec"], now)
            cpu_percent = 0.0
            if previous is not None and now > previous[1]:
                cpu_percent = max(
                    0.0,
                    min(
                        100.0,
                        (values["CPUUsageNSec"] - previous[0])
                        / ((now - previous[1]) * 1_000_000_000)
                        * 100,
                    ),
                )
            unit_peaks.append(
                UnitResourceEvidence(
                    unit_name=unit,
                    peak_memory_bytes=values["MemoryPeak"],
                    peak_cpu_percent=cpu_percent,
                    peak_tasks=values["TasksCurrent"],
                )
            )
        return ResourceEvidence(
            peak_memory_bytes=sum(item.peak_memory_bytes for item in unit_peaks),
            peak_cpu_percent=self._sample_host_cpu_percent(HOST_CPU_AGGREGATE_SECONDS),
            peak_tasks=sum(item.peak_tasks for item in unit_peaks),
            minimum_host_mem_available_bytes=self._mem_available_bytes(),
            unit_peaks=tuple(unit_peaks),
        )

    def cleanup(self, resolved, generation: int | None):
        return lifecycle.cleanup_replica(
            resolved, generation=generation, runner=self.runner
        )

    def cleanup_postconditions(self, shape: FleetShape) -> CleanupEvidence:
        units_removed = all(
            self._unit_metadata(unit)[:2] == ("not-found", "inactive")
            for unit in QUALIFICATION_SUPERVISOR_UNITS + QUALIFICATION_WORKER_UNITS
        )
        status_files_removed = all(
            not self.qualification_status_root.joinpath(f"{worker_id}.json").exists()
            for worker_id in QUALIFICATION_WORKER_IDS
        )
        ports_free = all(not self.listener_hosts(port) for port in QUALIFICATION_PORTS)
        return CleanupEvidence(
            drain_proven=status_files_removed,
            registry_offline=status_files_removed,
            supervisors_stopped_before_workers=units_removed,
            units_removed=units_removed,
            status_files_removed=status_files_removed,
            ports_free=ports_free,
            processes_gone=units_removed and ports_free,
        )

    def owned_units(self, resolved) -> tuple[str, ...]:
        owned = []
        for unit, role in (
            (resolved.supervisor_unit, "supervisor"),
            (resolved.worker_unit, "worker"),
        ):
            description = (
                "Papers With Code staging external Pi qualification "
                f"{role} {resolved.index:02d} owner {self.owner_id}"
            )
            load, state, observed = self._unit_metadata(unit)
            if (load, state) != ("not-found", "inactive") and observed == description:
                owned.append(unit)
        return tuple(owned)

    def recovery_postconditions(
        self, resolved, owned_units: tuple[str, ...]
    ) -> tuple[CleanupEvidence, tuple[str, ...]]:
        unit_states = {
            unit: self._unit_metadata(unit)[:2]
            for unit in (resolved.supervisor_unit, resolved.worker_unit)
        }
        unresolved = tuple(
            unit
            for unit in (resolved.supervisor_unit, resolved.worker_unit)
            if unit_states[unit] != ("not-found", "inactive")
        )
        status_removed = not resolved.status_path.exists()
        supervisor_removed = unit_states[resolved.supervisor_unit] == (
            "not-found",
            "inactive",
        )
        registry_offline = status_removed and supervisor_removed
        if not status_removed:
            try:
                status = json.loads(resolved.status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                status = {}
            registry_offline = (
                status.get("release_id") == resolved.release_id
                and status.get("worker_id") == resolved.worker_id
                and status.get("state") == "offline"
                and status.get("drained") is True
            )
        ports_free = not self.listener_hosts(resolved.port)
        units_removed = all(
            state == ("not-found", "inactive") for state in unit_states.values()
        )
        cleanup = CleanupEvidence(
            drain_proven=registry_offline,
            registry_offline=registry_offline,
            supervisors_stopped_before_workers=supervisor_removed,
            units_removed=units_removed,
            status_files_removed=status_removed,
            ports_free=ports_free,
            processes_gone=units_removed and ports_free,
        )
        return cleanup, unresolved


def _cleanup_evidence(results: Sequence[object]) -> CleanupEvidence:
    return CleanupEvidence(
        drain_proven=all(item.registry_offline for item in results),
        registry_offline=all(item.registry_offline for item in results),
        supervisors_stopped_before_workers=all(
            item.supervisors_stopped_before_workers for item in results
        ),
        units_removed=all(item.units_removed for item in results),
        status_files_removed=all(item.status_files_removed for item in results),
        ports_free=all(item.ports_free for item in results),
        processes_gone=all(item.processes_gone for item in results),
    )


def _unknown_cleanup_evidence() -> CleanupEvidence:
    return CleanupEvidence(
        drain_proven=False,
        registry_offline=False,
        supervisors_stopped_before_workers=False,
        units_removed=False,
        status_files_removed=False,
        ports_free=False,
        processes_gone=False,
    )


def _merge_resources(samples: Sequence[ResourceEvidence]) -> ResourceEvidence:
    if not samples:
        raise FleetRunRefused("external Pi fleet resource evidence is missing")
    unit_names = tuple(item.unit_name for item in samples[0].unit_peaks)
    if any(
        tuple(item.unit_name for item in sample.unit_peaks) != unit_names
        for sample in samples
    ):
        raise FleetRunRefused("external Pi fleet resource evidence is inconsistent")
    unit_peaks = tuple(
        UnitResourceEvidence(
            unit_name=name,
            peak_memory_bytes=max(
                sample.unit_peaks[index].peak_memory_bytes for sample in samples
            ),
            peak_cpu_percent=max(
                sample.unit_peaks[index].peak_cpu_percent for sample in samples
            ),
            peak_tasks=max(sample.unit_peaks[index].peak_tasks for sample in samples),
        )
        for index, name in enumerate(unit_names)
    )
    return ResourceEvidence(
        peak_memory_bytes=max(item.peak_memory_bytes for item in samples),
        peak_cpu_percent=max(item.peak_cpu_percent for item in samples),
        peak_tasks=max(item.peak_tasks for item in samples),
        minimum_host_mem_available_bytes=min(
            item.minimum_host_mem_available_bytes for item in samples
        ),
        unit_peaks=unit_peaks,
    )


def _resources_safe(evidence: ResourceEvidence) -> bool:
    return (
        evidence.minimum_host_mem_available_bytes >= MIN_PROJECTED_MEM_AVAILABLE_BYTES
        and evidence.peak_cpu_percent < 80.0
    )


def _run_guarded_round(
    operator: FleetOperator,
    shape: FleetShape,
    name: str,
    workers: tuple[WorkerEvidence, ...],
    diagnostic: _FailureDiagnostic | None = None,
) -> tuple[FleetRoundReport, tuple[ResourceEvidence, ...]]:
    diagnostic = diagnostic or _FailureDiagnostic()
    diagnostic.mark("locust_round", "locust_round_failed")
    operator.prepare_round()
    stop = threading.Event()
    abort = threading.Event()
    samples: list[ResourceEvidence] = []
    sampling_errors: list[BaseException] = []

    def sample_until_stopped() -> None:
        while not stop.is_set():
            try:
                evidence = operator.sample_resources(shape)
                samples.append(evidence)
                if not _resources_safe(evidence):
                    diagnostic.capture(
                        "resource_threshold", "resource_threshold_crossed"
                    )
                    abort.set()
                    return
            except BaseException as error:  # noqa: BLE001 - fail round closed
                sampling_errors.append(error)
                diagnostic.capture("resource_sampling", "resource_sampling_failed")
                abort.set()
                return
            stop.wait(0.1)

    sampler = threading.Thread(
        target=sample_until_stopped,
        name="external-pi-fleet-resource-guard",
        daemon=True,
    )
    sampler.start()
    try:
        diagnostic.mark("locust_round", "locust_round_failed")
        try:
            report = operator.run_round(
                name,
                workers,
                expected_users=shape.expected_users,
                abort_requested=abort.is_set,
            )
        except _FleetOperationFailure as error:
            diagnostic.capture(error.stage, error.code)
            raise error.cause.with_traceback(error.cause.__traceback__) from error
        except BaseException:  # noqa: BLE001 - capture the first failure immediately
            diagnostic.capture("locust_round", "locust_round_failed")
            raise
    finally:
        stop.set()
        sampler.join(timeout=2.0)
    if sampler.is_alive():
        diagnostic.capture("resource_sampling", "resource_sampler_stalled")
        raise FleetRunRefused("external Pi fleet live resource guard crossed")
    if sampling_errors or abort.is_set():
        raise FleetRunRefused("external Pi fleet live resource guard crossed")
    if not samples:
        raise FleetRunRefused("external Pi fleet live resource evidence is missing")
    return report, tuple(samples)


def _run_shape(
    operator: FleetOperator,
    shape: FleetShape,
    attempted: list[AttemptedReplica],
    diagnostic: _FailureDiagnostic,
):
    active: list[object] = []
    generations: dict[str, int] = {}
    workers: list[WorkerEvidence] = []
    cleanup_results: list[object] = []
    samples: list[ResourceEvidence] = []
    error: BaseException | None = None

    def checkpoint() -> None:
        evidence = tuple(
            WorkerEvidence(
                worker_id=resolved.worker_id,
                port=resolved.port,
                generation=generations[resolved.worker_id],
                maximum_sessions=shape.sessions_per_worker,
            )
            if resolved.worker_id in generations
            else resolved
            for resolved in active
        )
        diagnostic.mark("revalidation", "revalidation_failed")
        operator.revalidate(shape, evidence)
        diagnostic.mark("resource_sampling", "resource_sampling_failed")
        resource_evidence = operator.sample_resources(shape)
        samples.append(resource_evidence)
        if not _resources_safe(resource_evidence):
            diagnostic.capture("resource_threshold", "resource_threshold_crossed")
            raise FleetRunRefused("external Pi fleet live resource guard crossed")

    checkpoint()
    diagnostic.mark("resource_sampling", "resource_sampling_failed")
    preflight = operator.resource_preflight(shape)
    checkpoint()
    if preflight.status == "resource_refused":
        diagnostic.mark("cleanup", "cleanup_failed")
        return build_resource_refused_shape_report(
            shape, preflight, operator.cleanup_postconditions(shape)
        )

    healthy: FleetRoundReport | None = None
    survivor: FleetRoundReport | None = None
    removed_worker_id: str | None = None
    resolved_by_id: dict[str, object] = {}
    try:
        for index, replica in enumerate(shape.replicas):
            checkpoint()
            diagnostic.mark("replica_lifecycle", "replica_lifecycle_failed")
            resolved = operator.resolve(shape, index)
            attempt = AttemptedReplica(resolved=resolved)
            attempted.append(attempt)
            try:
                diagnostic.mark("replica_lifecycle", "replica_lifecycle_failed")
                operator.start(resolved)
            except BaseException:
                attempt.owned_units = operator.owned_units(resolved)
                if attempt.owned_units:
                    active.append(resolved)
                    resolved_by_id[replica.worker_id] = resolved
                raise
            attempt.owned_units = (resolved.supervisor_unit, resolved.worker_unit)
            active.append(resolved)
            resolved_by_id[replica.worker_id] = resolved
            checkpoint()
            diagnostic.mark("replica_lifecycle", "replica_lifecycle_failed")
            generation = operator.wait_ready(resolved)
            generations[replica.worker_id] = generation
            attempt.generation = generation
            workers.append(
                WorkerEvidence(
                    worker_id=replica.worker_id,
                    port=replica.port,
                    generation=generation,
                    maximum_sessions=shape.sessions_per_worker,
                )
            )
            checkpoint()

        checkpoint()
        healthy, round_samples = _run_guarded_round(
            operator, shape, "healthy", tuple(workers), diagnostic
        )
        samples.extend(round_samples)
        checkpoint()

        removed = workers[0]
        removed_worker_id = removed.worker_id
        removed_resolved = resolved_by_id[removed.worker_id]
        checkpoint()
        diagnostic.mark("cleanup", "cleanup_failed")
        cleanup_results.append(operator.cleanup(removed_resolved, removed.generation))
        active.remove(removed_resolved)
        checkpoint()

        survivor_workers = tuple(worker for worker in workers if worker != removed)
        checkpoint()
        survivor, round_samples = _run_guarded_round(
            operator, shape, "survivor", survivor_workers, diagnostic
        )
        samples.extend(round_samples)
        checkpoint()
    except BaseException as exc:  # noqa: BLE001 - signals must enter cleanup
        diagnostic.capture()
        error = exc
    finally:
        for resolved in tuple(active):
            worker_id = resolved.worker_id
            generation = generations.get(worker_id)
            try:
                checkpoint()
            except BaseException as checkpoint_error:  # noqa: BLE001
                if error is None:
                    diagnostic.capture()
                    error = checkpoint_error
            try:
                diagnostic.mark("cleanup", "cleanup_failed")
                cleanup_results.append(operator.cleanup(resolved, generation))
                active.remove(resolved)
            except BaseException as cleanup_error:  # noqa: BLE001 - keep cleaning
                if error is None:
                    diagnostic.capture()
                    error = cleanup_error
                continue
            try:
                checkpoint()
            except BaseException as checkpoint_error:  # noqa: BLE001
                if error is None:
                    diagnostic.capture()
                    error = checkpoint_error

    if error is not None:
        raise error
    if healthy is None or survivor is None or removed_worker_id is None:
        raise FleetRunRefused("external Pi fleet shape evidence is incomplete")
    return build_completed_shape_report(
        shape=shape,
        healthy=healthy,
        survivor=survivor,
        workers=tuple(workers),
        removed_worker_id=removed_worker_id,
        resources=_merge_resources(samples),
        resource_preflight=preflight,
        cleanup=_cleanup_evidence(cleanup_results),
    )


def run_fleet_controller(
    operator: FleetOperator,
    *,
    release_id: str,
    report_path: Path,
    report_root: Path,
    shape_names: tuple[FleetShapeName, ...] = ("5x32", "8x16", "16x8"),
    stop_on_nonpassing_shape: bool = False,
    geteuid: Callable[[], int] = os.geteuid,
) -> FleetQualificationReport:
    """Run allowlisted shapes sequentially and atomically retain final evidence."""
    if geteuid() != 0:
        raise FleetRunRefused("external Pi fleet controller requires a root operator")
    attempt_id = str(uuid.uuid4())
    attempted_at_unix_ms = int(time.time() * 1_000)
    owner_id = str(uuid.uuid4())
    operator.set_owner(owner_id)
    current_shape: FleetShape | None = None
    attempted: list[AttemptedReplica] = []
    diagnostic = _FailureDiagnostic()
    with qualification_signal_context():
        shapes = tuple(resolve_fleet_shape(name) for name in shape_names)
        recovery_descriptors = {
            shape.name: tuple(
                operator.resolve(shape, index)
                for index in range(len(QUALIFICATION_PORTS))
            )
            for shape in shapes
        }
        try:
            reports = []
            for shape in shapes:
                current_shape = shape
                attempted = []
                diagnostic = _FailureDiagnostic()
                shape_report = _run_shape(
                    operator, current_shape, attempted, diagnostic
                )
                reports.append(shape_report)
                if stop_on_nonpassing_shape and not shape_report.overall_passed:
                    break
            final = build_final_report(
                release_id=release_id,
                runtime_id=operator.runtime_id,
                shapes=tuple(reports),
            )
            publish_fleet_report(final, report_path, report_root)
        except BaseException:
            if current_shape is None:
                raise
            diagnostic.capture()
            attempts_by_index = {
                attempt.resolved.index: attempt for attempt in attempted
            }
            replicas = []
            for index in range(len(QUALIFICATION_PORTS)):
                attempt = attempts_by_index.get(index)
                resolved = (
                    attempt.resolved
                    if attempt is not None
                    else recovery_descriptors[current_shape.name][index]
                )
                inspection_failed = False
                if attempt is not None:
                    owned_units = attempt.owned_units
                else:
                    try:
                        owned_units = operator.owned_units(resolved)
                    except FleetQualificationInterrupted:
                        raise
                    except Exception:
                        owned_units = ()
                        inspection_failed = True
                if inspection_failed:
                    cleanup = _unknown_cleanup_evidence()
                    unresolved = (resolved.supervisor_unit, resolved.worker_unit)
                else:
                    try:
                        cleanup, unresolved = operator.recovery_postconditions(
                            resolved, owned_units
                        )
                    except FleetQualificationInterrupted:
                        raise
                    except Exception:
                        cleanup = _unknown_cleanup_evidence()
                        unresolved = (resolved.supervisor_unit, resolved.worker_unit)
                if attempt is None and cleanup.passed and not unresolved:
                    continue
                replicas.append(
                    RecoveryReplicaEvidence(
                        worker_id=resolved.worker_id,
                        port=resolved.port,
                        generation=(
                            attempt.generation if attempt is not None else None
                        ),
                        supervisor_unit=resolved.supervisor_unit,
                        worker_unit=resolved.worker_unit,
                        owned_units=owned_units,
                        cleanup=cleanup,
                        unresolved_units=unresolved,
                    )
                )
            recovery = FleetRecoveryReport(
                attempt_id=attempt_id,
                attempted_at_unix_ms=attempted_at_unix_ms,
                release_id=release_id,
                runtime_id=operator.runtime_id,
                owner_id=owner_id,
                failure_stage=diagnostic.stage,
                failure_code=diagnostic.code,
                replicas=tuple(replicas),
            )
            publish_fleet_report(recovery, report_path, report_root)
            raise
    return final


REPORT_ROOT = Path("/var/lib/paperswithcode/staging")
CONFIRMATION = "RUN_EXTERNAL_PI_FLEET_QUALIFICATION"


def resolve_qualification_profile(
    profile: str,
) -> tuple[tuple[FleetShapeName, ...], str]:
    profiles: dict[str, tuple[tuple[FleetShapeName, ...], str]] = {
        "32-user": (
            ("2x32",),
            "external-pi-32-user-qualification.json",
        ),
        "100-user": (
            ("5x32", "8x16", "16x8"),
            "external-pi-fleet-qualification.json",
        ),
        "capacity": (
            ("2x32", "4x16", "3x32"),
            "external-pi-capacity-qualification.json",
        ),
        "persistent-transport": (
            ("2x32",),
            "external-pi-persistent-transport-fleet.json",
        ),
    }
    try:
        return profiles[profile]
    except KeyError as error:
        raise FleetRunRefused("external Pi qualification profile is invalid") from error


def qualification_exit_code(report: FleetQualificationReport) -> int:
    if any(
        shape.status == "completed" and not shape.overall_passed
        for shape in report.shapes
    ):
        return 1
    return 0 if report.preferred_shape is not None else 1


def load_persistent_transport_manifest(path: Path | None) -> None:
    """Fail closed on missing or unbounded release qualification input."""

    if path is None or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise FleetRunRefused("persistent transport qualification manifest is required")
    try:
        manifest = validate_persistent_transport_manifest(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if manifest.chaos_declared:
            raise ValueError("chaos manifest is not a release qualification")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise FleetRunRefused(
            "persistent transport qualification manifest is invalid"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("staging",), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument(
        "--profile",
        choices=("32-user", "100-user", "capacity", "persistent-transport"),
        default="100-user",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--persistent-manifest", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo as the root operator")
    if args.confirm != CONFIRMATION:
        parser.error("exact fleet qualification confirmation is required")
    try:
        shape_names, report_name = resolve_qualification_profile(args.profile)
        if args.profile == "persistent-transport":
            load_persistent_transport_manifest(args.persistent_manifest)
            raise FleetRunRefused(
                "persistent transport requires its scenario runner; "
                "the legacy fleet workload cannot qualify this transport"
            )
        elif args.persistent_manifest is not None:
            raise FleetRunRefused(
                "persistent manifest is only valid for its distinct profile"
            )
        operator = SystemFleetOperator(release_id=args.release_id)
        report = run_fleet_controller(
            operator,
            release_id=args.release_id,
            report_path=args.report or REPORT_ROOT / report_name,
            report_root=REPORT_ROOT,
            shape_names=shape_names,
            stop_on_nonpassing_shape=args.profile
            in {"capacity", "persistent-transport"},
        )
    except Exception:  # noqa: BLE001 - CLI must never emit protected details
        print("external Pi fleet qualification failed closed", file=os.sys.stderr)
        return 1
    return qualification_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
