from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from backend.loadtests import external_pi_fleet_core as fleet_core
from backend.config import Settings
from backend.services.chat_external_worker_capacity import external_worker_endpoints
from backend.services.runtime_validation import validate_external_pi_migration_policy
from deploy import external_pi_qualification_contract as contract
from deploy import external_pi_qualification_lifecycle as lifecycle
from deploy import external_pi_qualification_supervisor_launcher as supervisor_launcher
from deploy import external_pi_qualification_worker_launcher as worker_launcher


def _active_release(root: Path, runtime_id: str = "a" * 64) -> Path:
    release = root / "releases" / "0123456789ab-staging"
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "release_id": "0123456789ab-staging",
                "runtime_id": "python-runtime",
                "external_pi_runtime": {
                    "identity_schema": 1,
                    "runtime_id": runtime_id,
                    "contract": "external-pi-v1",
                },
            }
        )
    )
    current = root / "environments" / "staging" / "current"
    current.parent.mkdir(parents=True)
    current.symlink_to(release)
    runtime = root / "runtimes" / "external-pi" / runtime_id
    (runtime / "node/bin").mkdir(parents=True)
    (runtime / "app/dist/src").mkdir(parents=True)
    (runtime / "assets").mkdir()
    (runtime / "node/bin/node").write_text("node")
    (runtime / "app/dist/src/external_http_main.js").write_text("main")
    (runtime / "assets/pi-system-prompt.txt").write_text("prompt")
    (root / "runtimes/python-runtime/bin").mkdir(parents=True)
    (root / "runtimes/python-runtime/bin/python").write_text("python")
    return release


def test_stdlib_contract_is_the_single_source_for_both_consumers():
    assert fleet_core.QUALIFICATION_PORTS is contract.QUALIFICATION_PORTS
    assert fleet_core.QUALIFICATION_WORKER_IDS is contract.QUALIFICATION_WORKER_IDS
    assert (
        fleet_core.QUALIFICATION_SUPERVISOR_UNITS
        is contract.QUALIFICATION_SUPERVISOR_UNITS
    )
    assert fleet_core.QUALIFICATION_WORKER_UNITS is contract.QUALIFICATION_WORKER_UNITS
    assert contract.QUALIFICATION_PORTS == tuple(range(8780, 8796))
    assert (
        tuple(
            (
                fleet_core.resolve_fleet_shape(name).worker_count,
                fleet_core.resolve_fleet_shape(name).sessions_per_worker,
            )
            for name in ("5x32", "8x16", "16x8")
        )
        == contract.QUALIFICATION_SHAPES
    )


def test_resolution_requires_exact_active_staging_release_and_allowlisted_replica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = _active_release(tmp_path)
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "external_pi_runtime_manifest",
        lambda runtime, **expected: {
            "entry_point": "app/dist/src/external_http_main.js",
            "expected": expected,
        },
    )
    monkeypatch.setattr(lifecycle, "runtime_id", lambda _release: "python-runtime")
    monkeypatch.setattr(lifecycle, "runtime_manifest", lambda _runtime: {})

    resolved = lifecycle.resolve_qualification_replica(
        "staging", "0123456789ab-staging", 15, 8795, 32
    )

    assert resolved.release == release.resolve()
    assert resolved.worker_id == "staging-qualification-15"
    assert resolved.port == 8795
    assert resolved.maximum_sessions == 32
    assert resolved.node == resolved.runtime / "node/bin/node"
    assert resolved.python == tmp_path / "runtimes/python-runtime/bin/python"
    for args in (
        ("production", "0123456789ab-staging", 15, 8795, 32),
        ("staging", "ffffffffffff-staging", 15, 8795, 32),
        ("staging", "0123456789ab-staging", 16, 8795, 32),
        ("staging", "0123456789ab-staging", 15, 8780, 32),
        ("staging", "0123456789ab-staging", 15, 8795, 7),
    ):
        with pytest.raises(ValueError):
            lifecycle.resolve_qualification_replica(*args)
    for overlapping_port in (8766, 8767, 8100, 8199):
        with pytest.raises(ValueError):
            contract.qualification_index(0, overlapping_port, 8)


def _resolved(tmp_path: Path) -> lifecycle.QualificationReplica:
    return lifecycle.QualificationReplica(
        index=3,
        port=8783,
        maximum_sessions=16,
        worker_id="staging-qualification-03",
        supervisor_unit=contract.QUALIFICATION_SUPERVISOR_UNITS[3],
        worker_unit=contract.QUALIFICATION_WORKER_UNITS[3],
        release=tmp_path / "release",
        release_id="0123456789ab-staging",
        runtime=tmp_path / "external-runtime",
        node=tmp_path / "external-runtime/node/bin/node",
        entry_point=tmp_path / "external-runtime/app/main.js",
        prompt=tmp_path / "external-runtime/assets/pi-system-prompt.txt",
        python=tmp_path / "python-runtime/bin/python",
        status_path=tmp_path / "status/staging-qualification-03.json",
    )


def test_worker_and_supervisor_environments_scrub_unrelated_credentials(tmp_path: Path):
    resolved = _resolved(tmp_path)
    protected = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_DB_HOST": "db",
        "PWC_DB_PORT": "5432",
        "PWC_DB_NAME": "pwc",
        "PWC_DB_USER": "staging",
        "PWC_DB_PASSWORD": "secret",
        "PWC_DB_SEARCH_PATH": "staging",
        "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": "10",
        "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
        "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "60",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS": "60",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS": "1",
        "OPENAI_API_KEY": "must-not-leak",
        "HF_TOKEN": "must-not-leak",
        "MODAL_TOKEN_SECRET": "must-not-leak",
        "PATH": "/usr/bin",
    }

    worker = lifecycle.worker_environment(resolved, protected, instance_id="fresh-id")
    supervisor = lifecycle.supervisor_environment(resolved, protected)

    assert worker == {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": "8783",
        "PWC_EXTERNAL_PI_TOKEN": "t" * 32,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": "16",
        "PWC_EXTERNAL_PI_WORKER_ID": "staging-qualification-03",
        "PWC_EXTERNAL_PI_INSTANCE_ID": "fresh-id",
        "PWC_EXTERNAL_PI_RELEASE_ID": "0123456789ab-staging",
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
    }
    assert set(supervisor) == {
        "PWC_ENVIRONMENT",
        "PWC_RELEASE_ID",
        "PWC_DB_HOST",
        "PWC_DB_PORT",
        "PWC_DB_NAME",
        "PWC_DB_USER",
        "PWC_DB_PASSWORD",
        "PWC_DB_SEARCH_PATH",
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED",
        "PWC_CHAT_EXTERNAL_PI_WORKER_ID",
        "PWC_CHAT_EXTERNAL_PI_WORKER_URL",
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
        "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION",
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS",
        "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS",
        "PWC_EXTERNAL_PI_STATUS_PATH",
        "PWC_EXTERNAL_PI_WORKER_ID",
    }
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == "http://127.0.0.1:8783"


def test_qualification_supervisor_settings_resolve_dynamic_worker_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = _resolved(tmp_path)
    child = lifecycle.supervisor_environment(
        resolved, {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32}
    )

    assert child["PWC_CHAT_EXTERNAL_PI_WORKER_ID"] == resolved.worker_id

    with monkeypatch.context() as scoped:
        for key in tuple(os.environ):
            if key.startswith("PWC_CHAT_EXTERNAL_PI_WORKER_"):
                scoped.delenv(key)
        for key, value in child.items():
            scoped.setenv(key, value)
        settings = Settings(_env_file=None)

    validate_external_pi_migration_policy(settings)
    (endpoint,) = external_worker_endpoints(settings)
    assert endpoint.worker_id == resolved.worker_id
    assert endpoint.base_url == "http://127.0.0.1:8783"
    assert endpoint.token == "t" * 32
    assert settings.chat_external_pi_worker_max_sessions == 16


def test_exec_launchers_use_recorded_runtimes_and_keep_token_off_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = _resolved(tmp_path)
    argv = ["launcher", "staging", resolved.release_id, "3", "8783", "16"]
    calls = []
    monkeypatch.setattr(worker_launcher.sys, "argv", argv)
    monkeypatch.setattr(
        worker_launcher, "resolve_qualification_replica", lambda *_: resolved
    )
    monkeypatch.setattr(worker_launcher.uuid, "uuid4", lambda: "fresh-worker-uuid")
    monkeypatch.setattr(
        worker_launcher,
        "worker_environment",
        lambda *_args, **kwargs: {"TOKEN": "secret", "INSTANCE": kwargs["instance_id"]},
    )
    monkeypatch.setattr(
        worker_launcher.os, "chdir", lambda path: calls.append(("chdir", path))
    )
    monkeypatch.setattr(
        worker_launcher.os, "execve", lambda *args: calls.append(("execve", *args))
    )
    worker_launcher.main()
    assert calls[-1] == (
        "execve",
        str(resolved.node),
        [
            str(resolved.node),
            "--import",
            str(resolved.runtime / "app/node_modules/tsx/dist/loader.mjs"),
            str(resolved.entry_point),
        ],
        {"TOKEN": "secret", "INSTANCE": "fresh-worker-uuid"},
    )
    assert "secret" not in calls[-1][2]

    calls.clear()
    monkeypatch.setattr(supervisor_launcher.sys, "argv", argv)
    monkeypatch.setattr(
        supervisor_launcher, "resolve_qualification_replica", lambda *_: resolved
    )
    monkeypatch.setattr(
        supervisor_launcher, "supervisor_environment", lambda *_: {"DB": "secret"}
    )
    monkeypatch.setattr(
        supervisor_launcher.os, "chdir", lambda path: calls.append(("chdir", path))
    )
    monkeypatch.setattr(
        supervisor_launcher.os, "execve", lambda *args: calls.append(("execve", *args))
    )
    supervisor_launcher.main()
    assert calls[-1] == (
        "execve",
        str(resolved.python),
        [str(resolved.python), "-m", "backend.scripts.run_external_pi_slot"],
        {"DB": "secret"},
    )


def test_transient_start_uses_exact_units_users_and_filesystem_restrictions(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        output = "not-found\ninactive\n" if command[:2] == ["systemctl", "show"] else ""
        return subprocess.CompletedProcess(command, 0, output)

    lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    assert [command for command, _ in commands[:2]] == [
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            resolved.supervisor_unit,
        ],
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            resolved.worker_unit,
        ],
    ]
    worker, supervisor = commands[2:]
    assert worker[0] == [
        "systemd-run",
        "--quiet",
        "--service-type=exec",
        "--description=Papers With Code staging external Pi qualification worker 03 owner test-owner",
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
        "staging",
        resolved.release_id,
        "3",
        "8783",
        "16",
    ]
    assert supervisor[0] == [
        "systemd-run",
        "--quiet",
        "--service-type=exec",
        "--description=Papers With Code staging external Pi qualification supervisor 03 owner test-owner",
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
        "staging",
        resolved.release_id,
        "3",
        "8783",
        "16",
    ]
    assert all(kwargs == {"check": True, "timeout": 75} for _, kwargs in commands[2:])
    assert not any(
        argument.startswith("/usr/local/lib/paperswithcode-deploy")
        for command, _ in commands[2:]
        for argument in command
    )


def test_system_python_imports_launchers_from_release_shaped_fixture(tmp_path: Path):
    source_root = Path(__file__).resolve().parents[3]
    release = tmp_path / "0123456789ab-staging"
    release.symlink_to(source_root, target_is_directory=True)
    for launcher in (
        "external_pi_qualification_worker_launcher.py",
        "external_pi_qualification_supervisor_launcher.py",
    ):
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(release / "deploy" / launcher)],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )

        assert result.returncode != 0
        assert "usage: external_pi_qualification_" in result.stderr
        assert "ModuleNotFoundError" not in result.stderr


@pytest.mark.parametrize("occupied", ["worker", "supervisor"])
def test_start_refuses_existing_exact_unit_even_when_port_is_free(
    tmp_path: Path, occupied: str
):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    resolved.status_path.write_text("pre-existing evidence")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        occupied_unit = (
            resolved.worker_unit if occupied == "worker" else resolved.supervisor_unit
        )
        output = (
            "loaded\nactive\n"
            if command[-1] == occupied_unit
            else "not-found\ninactive\n"
        )
        return subprocess.CompletedProcess(command, 0, output)

    with pytest.raises(lifecycle.QualificationLifecycleError, match="already exists"):
        lifecycle.start_replica(resolved, runner=run)

    assert len(commands) == 2
    assert resolved.status_path.read_text() == "pre-existing evidence"


def test_first_start_unit_exists_failure_does_not_clean_unowned_units(tmp_path: Path):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    resolved.status_path.write_text("pre-existing evidence")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "systemd-run":
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, "not-found\ninactive\n")

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.start_replica(resolved, runner=run)

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)
    assert resolved.status_path.read_text() == "pre-existing evidence"


def test_worker_timeout_adopts_matching_owner_and_cleans_only_that_unit(tmp_path: Path):
    resolved = _resolved(tmp_path)
    commands = []
    timed_out = False
    worker_stopped = False

    def run(command, **kwargs):
        nonlocal timed_out, worker_stopped
        commands.append(command)
        if command[0] == "systemd-run":
            timed_out = True
            raise subprocess.TimeoutExpired(command, 75)
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification worker 03 owner test-owner\n",
                )
            if timed_out and not worker_stopped and command[-1] == resolved.worker_unit:
                return subprocess.CompletedProcess(command, 0, "loaded\nactivating\n")
            return subprocess.CompletedProcess(command, 0, "not-found\ninactive\n")
        if command == ["systemctl", "stop", resolved.worker_unit]:
            worker_stopped = True
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(subprocess.TimeoutExpired):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    assert ["systemctl", "stop", resolved.worker_unit] in commands
    assert ["systemctl", "stop", resolved.supervisor_unit] not in commands


def test_supervisor_exec_failure_adopts_matching_owner_and_requires_claim_safety(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    commands = []
    supervisor_failed = False
    supervisor_stopped = False

    def run(command, **kwargs):
        nonlocal supervisor_failed, supervisor_stopped
        commands.append(command)
        if (
            command[0] == "systemd-run"
            and f"--unit={resolved.supervisor_unit}" in command
        ):
            supervisor_failed = True
            resolved.status_path.write_text(
                json.dumps(
                    {
                        "release_id": resolved.release_id,
                        "worker_id": resolved.worker_id,
                        "state": "starting",
                        "registered": False,
                        "generation": None,
                    }
                )
            )
            raise subprocess.CalledProcessError(1, command)
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification supervisor 03 owner test-owner\n",
                )
            if (
                supervisor_failed
                and not supervisor_stopped
                and command[-1] == resolved.supervisor_unit
            ):
                return subprocess.CompletedProcess(command, 0, "loaded\nfailed\n")
            return subprocess.CompletedProcess(command, 0, "not-found\ninactive\n")
        if command == ["systemctl", "stop", resolved.supervisor_unit]:
            supervisor_stopped = True
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    supervisor_stop = commands.index(["systemctl", "stop", resolved.supervisor_unit])
    worker_stop = commands.index(["systemctl", "stop", resolved.worker_unit])
    assert supervisor_stop < worker_stop


def test_non_signal_failure_never_adopts_foreign_worker_marker(tmp_path: Path):
    resolved = _resolved(tmp_path)
    commands = []
    failed = False

    def run(command, **kwargs):
        nonlocal failed
        commands.append(command)
        if command[0] == "systemd-run":
            failed = True
            raise subprocess.CalledProcessError(1, command)
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification worker 03 owner foreign-owner\n",
                )
            output = (
                "loaded\nactivating\n"
                if failed and command[-1] == resolved.worker_unit
                else "not-found\ninactive\n"
            )
            return subprocess.CompletedProcess(command, 0, output)
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)


def test_supervisor_unit_race_leaves_owned_worker_running_without_claim_proof(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    commands = []
    start_count = 0

    def run(command, **kwargs):
        nonlocal start_count
        commands.append(command)
        if command[0] == "systemd-run":
            start_count += 1
            if start_count == 2:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "")
        if command[:2] == ["systemctl", "show"]:
            output = (
                "loaded\nactive\n"
                if start_count == 2 and command[-1] == resolved.supervisor_unit
                else "not-found\ninactive\n"
            )
            return subprocess.CompletedProcess(command, 0, output)
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(
        lifecycle.QualificationLifecycleError, match="recovery evidence"
    ):
        lifecycle.start_replica(resolved, runner=run)

    assert ["systemctl", "stop", resolved.worker_unit] not in commands
    assert ["systemctl", "stop", resolved.supervisor_unit] not in commands


def test_interrupted_supervisor_start_drains_observed_claim_before_owned_worker(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    commands = []
    interrupted = False
    supervisor_stopped = False

    def write_status(state: str, *, drained: bool) -> None:
        resolved.status_path.write_text(
            json.dumps(
                {
                    "release_id": resolved.release_id,
                    "worker_id": resolved.worker_id,
                    "generation": 9,
                    "registered": True,
                    "state": state,
                    "drained": drained,
                }
            )
        )

    def run(command, **kwargs):
        nonlocal interrupted, supervisor_stopped
        commands.append(command)
        if (
            command[0] == "systemd-run"
            and f"--unit={resolved.supervisor_unit}" in command
        ):
            interrupted = True
            write_status("ready", drained=False)
            raise KeyboardInterrupt
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification supervisor 03 owner test-owner\n",
                )
            if (
                interrupted
                and not supervisor_stopped
                and command[-1] == resolved.supervisor_unit
            ):
                return subprocess.CompletedProcess(command, 0, "loaded\nactive\n")
            return subprocess.CompletedProcess(command, 0, "not-found\ninactive\n")
        if command == ["systemctl", "stop", resolved.supervisor_unit]:
            supervisor_stopped = True
            write_status("offline", drained=True)
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(KeyboardInterrupt):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    supervisor_stop = commands.index(["systemctl", "stop", resolved.supervisor_unit])
    worker_stop = commands.index(["systemctl", "stop", resolved.worker_unit])
    assert supervisor_stop < worker_stop


def test_interrupted_supervisor_with_ambiguous_status_leaves_owned_node_running(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    commands = []
    interrupted = False

    def run(command, **kwargs):
        nonlocal interrupted
        commands.append(command)
        if (
            command[0] == "systemd-run"
            and f"--unit={resolved.supervisor_unit}" in command
        ):
            interrupted = True
            raise KeyboardInterrupt
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification supervisor 03 owner test-owner\n",
                )
            output = (
                "loaded\nactive\n"
                if interrupted and command[-1] == resolved.supervisor_unit
                else "not-found\ninactive\n"
            )
            return subprocess.CompletedProcess(command, 0, output)
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(
        lifecycle.QualificationLifecycleError, match="recovery evidence"
    ):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    assert ["systemctl", "stop", resolved.supervisor_unit] in commands
    assert ["systemctl", "stop", resolved.worker_unit] not in commands


def test_interrupted_start_never_adopts_a_concurrent_supervisor_owner(tmp_path: Path):
    resolved = _resolved(tmp_path)
    commands = []
    interrupted = False

    def run(command, **kwargs):
        nonlocal interrupted
        commands.append(command)
        if (
            command[0] == "systemd-run"
            and f"--unit={resolved.supervisor_unit}" in command
        ):
            interrupted = True
            raise KeyboardInterrupt
        if command[:2] == ["systemctl", "show"]:
            if "--property=Description" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "Papers With Code staging external Pi qualification supervisor 03 owner concurrent-owner\n",
                )
            output = (
                "loaded\nactive\n"
                if interrupted and command[-1] == resolved.supervisor_unit
                else "not-found\ninactive\n"
            )
            return subprocess.CompletedProcess(command, 0, output)
        return subprocess.CompletedProcess(command, 0, "")

    with pytest.raises(
        lifecycle.QualificationLifecycleError, match="recovery evidence"
    ):
        lifecycle.start_replica(resolved, runner=run, owner_id="test-owner")

    assert ["systemctl", "stop", resolved.supervisor_unit] not in commands
    assert ["systemctl", "stop", resolved.worker_unit] not in commands


def test_ready_wait_rejects_stale_generation_and_times_out(tmp_path: Path):
    resolved = _resolved(tmp_path)
    status = {
        "release_id": resolved.release_id,
        "worker_id": resolved.worker_id,
        "state": "ready",
        "authenticated": True,
        "registered": True,
        "generation": 4,
        "heartbeats": 1,
    }
    times = iter((0.0, 0.0, 0.5, 1.0, 1.5))
    with pytest.raises(lifecycle.QualificationLifecycleError, match="timed out"):
        lifecycle.wait_ready(
            resolved,
            minimum_generation=4,
            timeout_seconds=1,
            read_status=lambda _path: status,
            monotonic=lambda: next(times),
            sleep=lambda _seconds: None,
        )
    with pytest.raises(ValueError, match="bounded"):
        lifecycle.wait_ready(resolved, timeout_seconds=121)


def test_cleanup_orders_drain_before_worker_and_proves_postconditions(tmp_path: Path):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    resolved.status_path.write_text("status")
    commands = []
    statuses = iter(
        (
            {"generation": 7, "state": "ready"},
            {
                "release_id": resolved.release_id,
                "worker_id": resolved.worker_id,
                "generation": 7,
                "state": "offline",
                "drained": True,
                "registered": True,
            },
        )
    )

    evidence = lifecycle.cleanup_replica(
        resolved,
        generation=7,
        runner=lambda command, **_kwargs: commands.append(command)
        or subprocess.CompletedProcess(command, 0, "not-found\ninactive\n"),
        read_status=lambda _path: next(statuses),
        monotonic=iter((0.0, 0.0, 0.1)).__next__,
        sleep=lambda _seconds: None,
        port_is_free=lambda host, port: host == "127.0.0.1" and port == 8783,
    )

    assert evidence.registry_offline is True
    assert evidence.ports_free is True
    assert evidence.units_removed is True
    assert commands[:5] == [
        ["systemctl", "stop", resolved.supervisor_unit],
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            resolved.supervisor_unit,
        ],
        ["systemctl", "stop", resolved.worker_unit],
        ["systemctl", "reset-failed", resolved.supervisor_unit],
        ["systemctl", "reset-failed", resolved.worker_unit],
    ]
    assert commands[5:] == [
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            resolved.supervisor_unit,
        ],
        [
            "systemctl",
            "show",
            "--property=LoadState",
            "--property=ActiveState",
            "--value",
            resolved.worker_unit,
        ],
    ]
    assert not resolved.status_path.exists()
    with pytest.raises(ValueError, match="bounded"):
        lifecycle.cleanup_replica(
            resolved,
            generation=None,
            timeout_seconds=331,
            runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, "not-found\ninactive\n"
            ),
        )


def test_owned_supervisor_without_claim_requires_matching_pre_registration_evidence(
    tmp_path: Path,
):
    resolved = _resolved(tmp_path)
    status = {
        "release_id": resolved.release_id,
        "worker_id": resolved.worker_id,
        "state": "starting",
        "registered": False,
        "generation": None,
    }
    commands = []

    evidence = lifecycle.cleanup_replica(
        resolved,
        generation=None,
        owned_units={resolved.supervisor_unit, resolved.worker_unit},
        runner=lambda command, **_kwargs: commands.append(command)
        or subprocess.CompletedProcess(command, 0, "not-found\ninactive\n"),
        read_status=lambda _path: status,
        monotonic=iter((0.0, 0.0, 0.1)).__next__,
        sleep=lambda _seconds: None,
        port_is_free=lambda _host, _port: True,
    )

    assert evidence.registry_offline is True
    assert ["systemctl", "stop", resolved.worker_unit] in commands


def _unclaimed_live_worker_status(resolved: lifecycle.QualificationReplica) -> dict:
    return {
        "protocol": "external-pi-v1",
        "worker_id": resolved.worker_id,
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": resolved.release_id,
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": resolved.maximum_sessions,
        "worker_generation": None,
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


_DELETE = object()


def test_generation_none_cleanup_accepts_exact_authenticated_unclaimed_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = _resolved(tmp_path)
    resolved.status_path.parent.mkdir(parents=True)
    resolved.status_path.write_text("failed")
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    events: list[object] = []

    def run(command, **_kwargs):
        events.append(command)
        output = "not-found\ninactive\n" if command[:2] == ["systemctl", "show"] else ""
        return subprocess.CompletedProcess(command, 0, output)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            assert size == 65_537
            return json.dumps(_unclaimed_live_worker_status(resolved)).encode()

    def open_status(request, *, timeout):
        events.append("authenticated-status")
        assert request.full_url == "http://127.0.0.1:8783/v1/status"
        assert request.get_header("Authorization") == f"Bearer {'t' * 32}"
        assert timeout == 5
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_status)

    evidence = lifecycle.cleanup_replica(
        resolved,
        generation=None,
        owned_units={resolved.supervisor_unit, resolved.worker_unit},
        runner=run,
        read_status=lambda _path: {
            "release_id": resolved.release_id,
            "worker_id": resolved.worker_id,
            "state": "failed",
            "authenticated": False,
            "registered": False,
            "generation": None,
        },
        port_is_free=lambda _host, _port: True,
    )

    assert evidence.registry_offline is True
    supervisor_stop = ["systemctl", "stop", resolved.supervisor_unit]
    worker_stop = ["systemctl", "stop", resolved.worker_unit]
    assert events.index(supervisor_stop) < events.index("authenticated-status")
    assert events.index("authenticated-status") < events.index(worker_stop)


@pytest.mark.parametrize(
    ("path", "unsafe_value"),
    (
        (("protocol",), "external-pi-v2"),
        (("worker_id",), "staging-qualification-04"),
        (("release_id",), "ffffffffffff-staging"),
        (("state",), "draining"),
        (("worker_generation",), _DELETE),
        (("worker_generation",), 0),
        (("active_sessions",), 0.0),
        (("active_sessions",), 1),
        (("maximum_sessions",), 16.0),
        (("maximum_sessions",), 32),
        (("operation_counters", "shadow_requests"), True),
        (("operation_counters", "model_calls"), 0.0),
        (("operation_counters", "tool_calls"), 1),
        (("operation_counters", "provider_calls"), 1),
        (("operation_counters", "modal_calls"), 1),
        (("operation_counters", "billing_events"), 1),
        (("operation_counters", "billing_events"), _DELETE),
        (("operation_counters", "unexpected"), 0),
    ),
)
def test_generation_none_cleanup_refuses_ambiguous_live_worker_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    unsafe_value: object,
):
    resolved = _resolved(tmp_path)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    status = _unclaimed_live_worker_status(resolved)
    target = status
    for key in path[:-1]:
        target = target[key]
    if unsafe_value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = unsafe_value
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        output = "not-found\ninactive\n" if command[:2] == ["systemctl", "show"] else ""
        return subprocess.CompletedProcess(command, 0, output)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return json.dumps(status).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(lifecycle.QualificationLifecycleError, match="ambiguous"):
        lifecycle.cleanup_replica(
            resolved,
            generation=None,
            owned_units={resolved.supervisor_unit, resolved.worker_unit},
            runner=run,
            read_status=lambda _path: {
                "release_id": resolved.release_id,
                "worker_id": resolved.worker_id,
                "state": "failed",
                "generation": None,
            },
            port_is_free=lambda _host, _port: True,
        )

    assert ["systemctl", "stop", resolved.worker_unit] not in commands


@pytest.mark.parametrize("failure", ("missing_token", "transport", "oversized"))
def test_generation_none_cleanup_fails_closed_without_bounded_authenticated_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
):
    resolved = _resolved(tmp_path)
    monkeypatch.setenv(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
        "short" if failure == "missing_token" else "t" * 32,
    )
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        output = "not-found\ninactive\n" if command[:2] == ["systemctl", "show"] else ""
        return subprocess.CompletedProcess(command, 0, output)

    class OversizedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            return b"x" * size

    def open_status(*_args, **_kwargs):
        if failure == "transport":
            raise urllib.error.URLError("unavailable")
        return OversizedResponse()

    monkeypatch.setattr(urllib.request, "urlopen", open_status)

    with pytest.raises(lifecycle.QualificationLifecycleError, match="ambiguous"):
        lifecycle.cleanup_replica(
            resolved,
            generation=None,
            owned_units={resolved.supervisor_unit, resolved.worker_unit},
            runner=run,
            read_status=lambda _path: {
                "release_id": resolved.release_id,
                "worker_id": resolved.worker_id,
                "state": "failed",
                "generation": None,
            },
            port_is_free=lambda _host, _port: True,
        )

    assert ["systemctl", "stop", resolved.worker_unit] not in commands


def test_generation_none_cleanup_refuses_worker_stop_until_supervisor_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = _resolved(tmp_path)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        output = "loaded\nactive\n" if command[:2] == ["systemctl", "show"] else ""
        return subprocess.CompletedProcess(command, 0, output)

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("worker status must not be read before supervisor stop")
        ),
    )

    with pytest.raises(lifecycle.QualificationLifecycleError, match="did not stop"):
        lifecycle.cleanup_replica(
            resolved,
            generation=None,
            owned_units={resolved.supervisor_unit, resolved.worker_unit},
            runner=run,
            read_status=lambda _path: {},
            port_is_free=lambda _host, _port: True,
        )

    assert ["systemctl", "stop", resolved.worker_unit] not in commands
