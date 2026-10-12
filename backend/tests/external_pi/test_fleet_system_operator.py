"""System operator revalidation, cleanup postconditions, and resource sampling."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.loadtests.external_pi_fleet_core import (
    FleetRunRefused,
    qualification_unit_names,
    resolve_fleet_shape,
)
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_PORTS,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_UNITS,
)
from backend.tests.external_pi.fleet_harness import (
    _FleetOperator,
    _cleanup,
)


def test_system_operator_revalidates_live_staging_and_exact_listener_state(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    staging.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    blue.joinpath("release").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    status_root = tmp_path / "run/external-pi"
    status_root.mkdir(parents=True)
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners: dict[int, tuple[str, ...]] = {}
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class LiveResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    unit_states = {"supervisor": "active", "worker": "active"}
    qualification_active = False

    def systemctl(command, **_kwargs):
        nonlocal qualification_active
        if "qualification" in command[-1]:
            if qualification_active and command[-1].endswith("@00.service"):
                role = (
                    "worker" if "qualification-worker" in command[-1] else "supervisor"
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "LoadState=loaded\nActiveState=active\n"
                    "Description=Papers With Code staging external Pi qualification "
                    f"{role} 00 owner {operator.owner_id}\n",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                "LoadState=not-found\nActiveState=inactive\nDescription=\n",
            )
        state = (
            unit_states["worker"]
            if "external-pi-worker" in command[-1]
            else unit_states["supervisor"]
        )
        return subprocess.CompletedProcess(command, 0, state + "\n")

    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: LiveResponse(),
        runner=systemctl,
    )
    shape = resolve_fleet_shape("5x32")

    operator.revalidate(shape, ())
    listeners[8780] = ("127.0.0.1",)
    qualification_active = True
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    live_status["operation_counters"]["provider_calls"] = 1
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    live_status["operation_counters"]["provider_calls"] = 0

    unit_states["supervisor"] = "failed"
    with pytest.raises(FleetRunRefused, match="active worker"):
        operator.revalidate(shape, active)
    unit_states["supervisor"] = "active"

    listeners[8780] = ("0.0.0.0",)
    with pytest.raises(FleetRunRefused, match="loopback"):
        operator.revalidate(shape, active)
    listeners[8780] = ("127.0.0.1",)
    environ["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] = "true"
    with pytest.raises(FleetRunRefused, match="disabled"):
        operator.revalidate(shape, active)


def test_system_operator_rejects_stale_and_foreign_exact_qualification_units(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    release.mkdir(parents=True)
    release.joinpath("release.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "external_pi_runtime": {"runtime_id": "runtime-1"},
            }
        ),
        encoding="utf-8",
    )
    staging = app_root / "environments/staging"
    blue = staging / "slots/blue"
    blue.mkdir(parents=True)
    staging.joinpath("current").symlink_to(release)
    staging.joinpath("active").symlink_to(blue)
    blue.joinpath("release").symlink_to(release)
    status_root = tmp_path / "status"
    status_root.mkdir()
    status_root.joinpath("staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": release.name,
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 7,
            }
        ),
        encoding="utf-8",
    )
    live_status = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": release.name,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return live_status

    qualification = {}

    def systemctl(command, **_kwargs):
        unit = command[-1]
        if "qualification" not in unit:
            values = {
                "LoadState": "loaded",
                "ActiveState": "active",
                "Description": "live",
            }
        else:
            values = qualification.get(
                unit,
                {
                    "LoadState": "not-found",
                    "ActiveState": "inactive",
                    "Description": "",
                },
            )
        if "--value" in command:
            return subprocess.CompletedProcess(command, 0, values["ActiveState"] + "\n")
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        )

    environ = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    }
    listeners = {}
    operator = SystemFleetOperator(
        release_id=release.name,
        app_root=app_root,
        status_root=status_root,
        environ=environ,
        listener_hosts=lambda port: listeners.get(port, ()),
        http_get=lambda *_args, **_kwargs: Response(),
        runner=systemctl,
    )
    operator.owner_id = "test-owner"
    shape = resolve_fleet_shape("5x32")
    supervisor = qualification_unit_names(shape)[0]
    worker = qualification_unit_names(shape)[shape.worker_count]

    qualification[QUALIFICATION_SUPERVISOR_UNITS[6]] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": "foreign reserved slot",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())
    del qualification[QUALIFICATION_SUPERVISOR_UNITS[6]]

    listeners[QUALIFICATION_PORTS[6]] = ("127.0.0.1",)
    with pytest.raises(FleetRunRefused, match="inactive qualification ports"):
        operator.revalidate(shape, ())
    listeners.clear()

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "failed",
        "Description": "foreign",
    }
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, ())

    qualification[supervisor] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification supervisor 00 "
            "owner test-owner"
        ),
    }
    qualification[worker] = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "Description": (
            "Papers With Code staging external Pi qualification worker 00 "
            "owner test-owner"
        ),
    }
    active = (SimpleNamespace(worker_id=shape.replicas[0].worker_id, port=8780),)
    operator.revalidate(shape, active)

    qualification[worker]["Description"] = "foreign-owner"
    with pytest.raises(FleetRunRefused, match="qualification unit"):
        operator.revalidate(shape, active)


def test_resource_refused_shape_uses_observed_cleanup_postconditions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class RefusedOperator(_FleetOperator):
        def cleanup_postconditions(self, _shape):
            return _cleanup(units_removed=False, processes_gone=False)

    operator = RefusedOperator(refuse={"16x8"})
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "fleet.json",
        report_root=tmp_path,
        shape_names=("16x8",),
        geteuid=lambda: 0,
    )

    assert report.shapes[0].status == "resource_refused"
    assert report.shapes[0].cleanup.units_removed is False
    assert report.shapes[0].cleanup.processes_gone is False


def test_system_recovery_does_not_report_foreign_exact_unit_as_removed(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.listener_hosts = lambda _port: ()
    resolved = SimpleNamespace(
        supervisor_unit=("paperswithcode-staging-external-pi-qualification@00.service"),
        worker_unit=(
            "paperswithcode-staging-external-pi-qualification-worker@00.service"
        ),
        status_path=tmp_path / "missing.json",
        release_id="0123456789ab-staging",
        worker_id="staging-qualification-00",
        port=8780,
    )
    operator._unit_metadata = lambda unit: (
        ("loaded", "active", "foreign")
        if unit == resolved.supervisor_unit
        else ("not-found", "inactive", "")
    )

    cleanup, unresolved = operator.recovery_postconditions(resolved, ())

    assert unresolved == (resolved.supervisor_unit,)
    assert cleanup.units_removed is False
    assert cleanup.registry_offline is False
    assert cleanup.passed is False


def test_system_refusal_cleanup_postconditions_inspect_all_reserved_slots(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    units = []
    ports = []
    operator = object.__new__(SystemFleetOperator)
    operator.qualification_status_root = tmp_path
    operator._unit_metadata = lambda unit: (
        units.append(unit) or ("not-found", "inactive", "")
    )
    operator.listener_hosts = lambda port: ports.append(port) or ()

    cleanup = operator.cleanup_postconditions(resolve_fleet_shape("5x32"))

    assert cleanup.passed is True
    assert units == list(QUALIFICATION_SUPERVISOR_UNITS + QUALIFICATION_WORKER_UNITS)
    assert ports == list(QUALIFICATION_PORTS)


def test_system_resource_preflight_scales_worker_memory_by_session_limit(monkeypatch):
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator.app_root = Path("/srv/paperswithcode")
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=False: Path(
            "/srv/paperswithcode/environments/staging/slots/blue"
        ),
    )

    def properties(unit, *_names):
        return {"MemoryCurrent": 100 * 1024**2 if "worker" in unit else 50 * 1024**2}

    operator._systemctl_properties = properties
    operator._mem_available_bytes = lambda: 4 * 1024**3
    slept = []
    cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(cpu)
    operator.sleep = lambda seconds: slept.append(seconds)

    preflight = operator.resource_preflight(resolve_fleet_shape("5x32"))

    assert slept == [1.0]
    assert preflight.observed_cpu_percent == 80.0
    assert preflight.status == "resource_refused"
    assert preflight.projected_mem_available_bytes == 4 * 1024**3 - 2250 * 1024**2


def test_system_resource_samples_host_cpu_over_one_second():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)
    operator._unit_cpu_state = {}
    operator._systemctl_properties = lambda _unit, *_names: {
        "MemoryPeak": 1,
        "CPUUsageNSec": 1,
        "TasksCurrent": 1,
    }
    operator._mem_available_bytes = lambda: 2 * 1024**3
    cpu = iter(((100, 80), (200, 100)))
    operator._read_host_cpu = lambda: next(cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)

    evidence = operator.sample_resources(resolve_fleet_shape("2x32"))

    assert slept == [1.0]
    assert evidence.peak_cpu_percent == 80.0


def test_system_resource_sample_below_eighty_percent_remains_safe():
    from backend.scripts.qualify_external_pi_fleet import (
        SystemFleetOperator,
        _resources_safe,
    )

    operator = object.__new__(SystemFleetOperator)
    operator._unit_cpu_state = {}
    operator._systemctl_properties = lambda _unit, *_names: {
        "MemoryPeak": 1,
        "CPUUsageNSec": 1,
        "TasksCurrent": 1,
    }
    operator._mem_available_bytes = lambda: 2 * 1024**3
    cpu = iter(((100, 80), (200, 101)))
    operator._read_host_cpu = lambda: next(cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)

    evidence = operator.sample_resources(resolve_fleet_shape("2x32"))

    assert slept == [1.0]
    assert evidence.peak_cpu_percent == 79.0
    assert _resources_safe(evidence) is True


def test_system_host_cpu_sampler_rejects_sub_one_second_window():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    operator = object.__new__(SystemFleetOperator)

    with pytest.raises(FleetRunRefused, match="sample interval"):
        operator._sample_host_cpu_percent(0.999)


def test_system_resource_adapter_parses_only_requested_numeric_properties():
    from backend.scripts.qualify_external_pi_fleet import SystemFleetOperator

    commands = []

    def systemctl(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "MemoryPeak=1048576\nCPUUsageNSec=invalid\nTasksCurrent=7\nIgnored=9\n",
        )

    operator = object.__new__(SystemFleetOperator)
    operator.runner = systemctl
    values = operator._systemctl_properties(
        "qualification-worker@00.service",
        "MemoryPeak",
        "CPUUsageNSec",
        "TasksCurrent",
    )

    assert values == {
        "MemoryPeak": 1048576,
        "CPUUsageNSec": 0,
        "TasksCurrent": 7,
    }
    assert commands == [
        [
            "systemctl",
            "show",
            "--property=MemoryPeak",
            "--property=CPUUsageNSec",
            "--property=TasksCurrent",
            "qualification-worker@00.service",
        ]
    ]


def test_system_sample_resources_aggregates_injected_exact_unit_and_host_evidence(
    monkeypatch,
):
    import backend.scripts.qualify_external_pi_fleet as controller

    calls = Counter()

    def systemctl(command, **_kwargs):
        unit = command[-1]
        calls[unit] += 1
        worker = "qualification-worker" in unit
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(
                (
                    f"MemoryPeak={(20 if worker else 10) * 1024**2}",
                    f"CPUUsageNSec={calls[unit] * 1_000_000_000}",
                    "TasksCurrent=3",
                )
            )
            + "\n",
        )

    operator = object.__new__(controller.SystemFleetOperator)
    operator.runner = systemctl
    operator._unit_cpu_state = {}
    host_cpu = iter(((100, 80), (200, 100), (200, 100), (300, 120)))
    operator._read_host_cpu = lambda: next(host_cpu)
    slept = []
    operator.sleep = lambda seconds: slept.append(seconds)
    operator._mem_available_bytes = lambda: 2 * 1024**3
    monotonic = iter((10.0, 12.0))
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(monotonic))
    shape = resolve_fleet_shape("5x32")

    first = operator.sample_resources(shape)
    second = operator.sample_resources(shape)

    assert first.peak_cpu_percent == 80.0
    assert second.peak_memory_bytes == 150 * 1024**2
    assert second.peak_cpu_percent == 80.0
    assert second.peak_tasks == 30
    assert second.minimum_host_mem_available_bytes == 2 * 1024**3
    assert len(second.unit_peaks) == 10
    assert {item.peak_cpu_percent for item in second.unit_peaks} == {50.0}
    assert set(calls.values()) == {2}
    assert slept == [1.0, 1.0]


def test_controller_concurrently_aborts_round_when_live_resource_guard_crosses(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class CrossingOperator(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            evidence = super().sample_resources(shape)
            if self.in_round.is_set():
                return evidence.model_copy(
                    update={"minimum_host_mem_available_bytes": 1536 * 1024**2 - 1}
                )
            return evidence

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            if not abort_requested():
                raise RuntimeError("no concurrent resource guard")
            raise FleetRunRefused("resource guard crossed")

    operator = CrossingOperator()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="resource guard crossed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True


def test_controller_aborts_round_when_concurrent_resource_sampler_errors(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SamplingFailure(_FleetOperator):
        in_round = threading.Event()

        def sample_resources(self, shape):
            if self.in_round.is_set():
                raise RuntimeError("resource adapter failed")
            return super().sample_resources(shape)

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.in_round.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not abort_requested():
                time.sleep(0.01)
            raise FleetRunRefused("round stopped")

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="round stopped"):
        run_fleet_controller(
            SamplingFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
