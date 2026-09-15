from __future__ import annotations

import json
import os
import pwd
import signal
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.cli as deploy_cli
import deploy.external_pi_slot_launcher as launcher
import deploy.external_pi_slot_lifecycle as lifecycle
import deploy.external_pi_worker_launcher as worker_launcher
import deploy.install_host_layout as install_host_layout
from backend.config import Settings
from backend.services.chat_external_worker_capacity import external_worker_endpoints
from backend.services.runtime_validation import validate_external_pi_migration_policy


def _release(
    root: Path,
    slot: str,
    runtime_id: str = "a" * 64,
    *,
    environment: str = "staging",
) -> Path:
    release = root / "releases" / f"release-{slot}"
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "release_id": f"release-{slot}",
                "external_pi_runtime": {
                    "identity_schema": 1,
                    "runtime_id": runtime_id,
                    "contract": "external-pi-v1",
                },
            }
        )
    )
    slot_root = root / "environments" / environment / "slots" / slot
    slot_root.mkdir(parents=True)
    (slot_root / "release").symlink_to(release)
    runtime = root / "runtimes/external-pi" / runtime_id
    (runtime / "node" / "bin").mkdir(parents=True)
    (runtime / "app" / "dist" / "src").mkdir(parents=True)
    (runtime / "assets").mkdir()
    (runtime / "node" / "bin" / "node").write_text("node")
    (runtime / "app" / "dist" / "src" / "external_http_main.js").write_text("main")
    (runtime / "assets" / "pi-system-prompt.txt").write_text("prompt")
    return release


@pytest.mark.parametrize(
    ("environment", "port", "worker_id"),
    (
        ("staging", 8766, "staging-blue"),
        ("production", 8776, "production-blue"),
    ),
)
def test_slot_runtime_is_environment_isolated_and_uses_recorded_immutable_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    port: int,
    worker_id: str,
):
    _release(tmp_path, "blue", environment=environment)
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "external_pi_runtime_manifest",
        lambda runtime, **expected: {
            "entry_point": "app/dist/src/external_http_main.js",
            "expected": expected,
        },
    )

    resolved = lifecycle.resolve_external_pi_slot(environment, "blue")

    assert resolved.port == port
    assert resolved.worker_id == worker_id
    assert resolved.release_id == "release-blue"
    assert resolved.runtime.name == "a" * 64
    assert resolved.node == resolved.runtime / "node/bin/node"
    expected_status = (
        lifecycle.STATUS_ROOT / "staging-blue.json"
        if environment == "staging"
        else lifecycle.PRODUCTION_STATUS_ROOT.with_name(
            f"{lifecycle.PRODUCTION_STATUS_ROOT.name}-blue"
        )
        / "status.json"
    )
    assert resolved.status_path == expected_status


def test_wrong_or_unrecorded_runtime_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = _release(tmp_path, "green")
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    value = json.loads((release / "release.json").read_text())
    del value["external_pi_runtime"]
    (release / "release.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="recorded external Pi runtime"):
        lifecycle.resolve_external_pi_slot("staging", "green")


def test_child_environments_are_strictly_scrubbed(tmp_path: Path):
    resolved = lifecycle.ExternalPiSlot(
        slot="green",
        port=8820,
        worker_id="staging-green-00",
        release=tmp_path / "release",
        release_id="release-green",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    protected = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_DB_HOST": "db",
        "PWC_DB_PORT": "5432",
        "PWC_DB_NAME": "pwc",
        "PWC_DB_USER": "staging",
        "PWC_DB_PASSWORD": "secret",
        "PWC_DB_SEARCH_PATH": "staging",
        "PWC_HF_TOKEN": "must-not-leak",
        "PWC_OPENAI_API_KEY": "must-not-leak",
        "MODAL_TOKEN_ID": "must-not-leak",
        "PWC_CHAT_SANDBOX_EXECUTOR_TOKEN": "must-not-leak",
        "PWC_EXTERNAL_PI_STATE_ROOT": "/run/paperswithcode/external-pi-green",
        "PATH": "/usr/bin",
    }

    node = lifecycle.node_environment(resolved, protected, instance_id="i" * 36)
    supervisor = lifecycle.supervisor_environment(resolved, protected)
    derived_token = lifecycle.replica_specs("staging", "green", "t" * 32)[0].token

    assert node == {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": "8820",
        "PWC_EXTERNAL_PI_TOKEN": derived_token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": "4",
        "PWC_EXTERNAL_PI_WORKER_ID": "staging-green-00",
        "PWC_EXTERNAL_PI_INSTANCE_ID": "i" * 36,
        "PWC_EXTERNAL_PI_RELEASE_ID": "release-green",
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
        "PWC_CHAT_PWC_MCP_ENABLED": "false",
        "PWC_EXTERNAL_PI_STATE_ROOT": (
            "/run/paperswithcode/external-pi-green/staging-green-00"
        ),
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
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == "http://127.0.0.1:8820"
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "4"
    assert "PWC_HF_TOKEN" not in supervisor


@pytest.mark.parametrize(("slot", "port"), (("blue", 8820), ("green", 8824)))
def test_supervisor_child_settings_resolve_complete_slot_worker_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slot: str, port: int
):
    worker_id = f"staging-{slot}-00"
    resolved = lifecycle.ExternalPiSlot(
        slot=slot,
        port=port,
        worker_id=worker_id,
        release=tmp_path / "release",
        release_id=f"release-{slot}",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    child_environment = lifecycle.supervisor_environment(
        resolved,
        {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )

    assert child_environment["PWC_CHAT_EXTERNAL_PI_WORKER_ID"] == worker_id

    with monkeypatch.context() as scoped:
        for key in tuple(os.environ):
            if key.startswith("PWC_CHAT_EXTERNAL_PI_WORKER_"):
                scoped.delenv(key)
        for key, value in child_environment.items():
            scoped.setenv(key, value)
        settings = Settings(_env_file=None)

    validate_external_pi_migration_policy(settings)
    (endpoint,) = external_worker_endpoints(settings)
    assert endpoint.endpoint_id == "legacy"
    assert endpoint.worker_id == worker_id
    assert endpoint.base_url == f"http://127.0.0.1:{port}"
    assert endpoint.token == lifecycle.replica_specs("staging", slot, "t" * 32)[0].token


def test_candidate_requires_authenticated_durable_lifecycle_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    statuses = []
    for spec in lifecycle.replica_specs("staging", "blue", "x" * 32):
        status = tmp_path / f"{spec.worker_id}.json"
        status.write_text(
            json.dumps(
                {
                    "release_id": "release-blue",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "authenticated": True,
                    "registered": True,
                    "generation": 3,
                    "heartbeats": 1,
                }
            )
        )
        statuses.append(status)

    assert lifecycle.qualify_candidate("staging", "blue", "release-blue") == 3
    value = json.loads(statuses[0].read_text())
    value["authenticated"] = False
    statuses[0].write_text(json.dumps(value))
    with pytest.raises(lifecycle.ExternalPiSlotError, match="qualification"):
        lifecycle.qualify_candidate(
            "staging", "blue", "release-blue", timeout_seconds=0.01
        )


def test_qualification_budget_covers_the_supervisor_startup_and_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
):
    # A supervisor may use its whole startup timeout to register and then a
    # further heartbeat interval before the first heartbeat is recorded. The
    # previous fixed 65s ceiling was below that 70s worst case, so a loaded
    # host failed qualification with registered=True and heartbeats=0.
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "60",
            "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": "10",
        },
    )
    budget = lifecycle.protected_qualification_timeout_seconds("staging")

    assert budget > 60 + 10
    assert budget == 60 + 2 * 10 + lifecycle.QUALIFICATION_MARGIN_SECONDS


def test_qualification_budget_rejects_out_of_bounds_configuration(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "not-a-number",
        },
    )
    with pytest.raises(ValueError, match="must be numeric"):
        lifecycle.protected_qualification_timeout_seconds("staging")

    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "900",
        },
    )
    with pytest.raises(ValueError, match="protected bounds"):
        lifecycle.protected_qualification_timeout_seconds("staging")


def test_qualification_proves_drain_and_restart_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple] = []
    generations = iter([4, 5])
    monkeypatch.setattr(
        lifecycle, "start_slot", lambda environment, slot: calls.append(("start", slot))
    )
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda environment, slot, release_id: next(generations),
    )
    monkeypatch.setattr(
        lifecycle,
        "stop_slot",
        lambda environment, slot, release_id, **kwargs: calls.append(("stop", slot)),
    )

    assert lifecycle.prepare_candidate("staging", "green", "release-green") == 5
    assert calls == [("start", "green"), ("stop", "green"), ("start", "green")]


def test_lease_expiry_restart_ignores_stale_status_until_generation_advances(
    monkeypatch: pytest.MonkeyPatch,
):
    statuses = iter(
        (
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 4,
                "heartbeats": 2,
            },
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 5,
                "heartbeats": 1,
            },
        )
    )
    commands = []
    sleeps = []
    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle, "_read_primary_status", lambda *_args: next(statuses)
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    assert (
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )
        == 5
    )
    assert commands == [
        [
            "systemctl",
            "kill",
            "--kill-whom=main",
            "--signal=KILL",
            "paperswithcode-staging-external-pi@blue.service",
        ],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi@blue.service",
        ],
        [
            "systemctl",
            "start",
            "paperswithcode-staging-external-pi@blue.service",
        ],
    ]
    assert sleeps == [31, 0.25]


def test_lease_expiry_transaction_masks_signals_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
):
    events = []

    def pthread_sigmask(operation, mask):
        events.append((operation, mask))
        return {signal.SIGHUP}

    def transaction(*_args):
        events.append("transaction")
        raise KeyboardInterrupt

    monkeypatch.setattr(lifecycle.signal, "pthread_sigmask", pthread_sigmask)
    monkeypatch.setattr(
        lifecycle, "_restart_supervisor_after_lease_expiry", transaction
    )

    with pytest.raises(KeyboardInterrupt):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert events == [
        (signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT}),
        "transaction",
        (signal.SIG_SETMASK, {signal.SIGHUP}),
    ]


def test_lease_expiry_interruption_recovers_claim_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []
    interrupted = False

    def sleep(seconds):
        nonlocal interrupted
        sleeps.append(seconds)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "ready",
            "authenticated": True,
            "registered": True,
            "generation": 5,
            "heartbeats": 1,
        },
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", sleep)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    with pytest.raises(KeyboardInterrupt):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert sleeps == [31, 31]
    assert commands[-1] == [
        "systemctl",
        "start",
        "paperswithcode-staging-external-pi@blue.service",
    ]


def test_lease_expiry_restart_failure_recovers_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    starts = 0

    def run(command, **_kwargs):
        nonlocal starts
        commands.append(command)
        if command[1] == "start":
            starts += 1
            if starts == 1:
                raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "ready",
            "authenticated": True,
            "registered": True,
            "generation": 5,
            "heartbeats": 1,
        },
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == ["kill", "stop", "start", "start"]


def test_lease_expiry_unrecoverable_restart_stops_request_free_worker(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "start":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(
        lifecycle.ExternalPiSlotError,
        match="request-free qualification worker was stopped",
    ):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == [
        "kill",
        "stop",
        "start",
        "start",
        "stop",
        "stop",
    ]
    assert commands[-1][-1] == (
        "paperswithcode-staging-external-pi-worker@blue.service"
    )
    assert sleeps == [31, 31, 31]


def test_lease_expiry_status_failure_expires_fresh_recovery_lease_before_stop(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []
    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: (_ for _ in ()).throw(OSError("status write missing")),
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    with pytest.raises(
        lifecycle.ExternalPiSlotError,
        match="request-free qualification worker was stopped",
    ):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == [
        "kill",
        "stop",
        "start",
        "start",
        "stop",
        "stop",
    ]
    assert sleeps == [31, 31, 31]


def test_drain_timeout_fails_the_slot_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", config)
    (tmp_path / "staging-blue.json").write_text(
        json.dumps({"release_id": "release-blue", "state": "ready"})
    )
    seen: dict[str, float] = {}

    def timeout(*_args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        raise lifecycle.subprocess.TimeoutExpired("systemctl", kwargs["timeout"])

    monkeypatch.setattr(lifecycle.subprocess, "run", timeout)
    with pytest.raises(lifecycle.ExternalPiSlotError, match="drain timed out"):
        lifecycle.stop_slot("staging", "blue", "release-blue")
    assert seen["timeout"] == 315


def test_maximum_configured_drain_can_finish_and_releases_durable_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    status_root = tmp_path / "status"
    status_root.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", status_root)
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", config)
    status = status_root / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "state": "ready",
                "drained": False,
            }
        )
    )
    seen: dict[str, float] = {}

    commands: list[list[str]] = []

    def stop(command, *, check, timeout=None):
        assert check is True
        commands.append(command)
        if "external-pi@" in command[-1]:
            seen["timeout"] = timeout
            status.write_text(
                json.dumps(
                    {
                        "release_id": "release-green",
                        "worker_id": "staging-green",
                        "state": "offline",
                        "drained": True,
                    }
                )
            )

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    lifecycle.stop_slot("staging", "green", "release-green")

    assert seen["timeout"] == 315
    assert lifecycle.slot_status("staging", "green") == {
        "release_id": "release-green",
        "worker_id": "staging-green",
        "state": "offline",
        "drained": True,
    }
    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


def test_eight_replica_tooling_drains_previous_sixteen_replica_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    old_specs = lifecycle.replica_specs_for_topology(
        "staging",
        "green",
        "x" * 32,
        replica_count=16,
        maximum_sessions=2,
    )
    for spec in old_specs:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "old-release",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "drained": False,
                    "authenticated": True,
                    "registered": True,
                    "generation": 1,
                    "heartbeats": 1,
                    "maximum_sessions": 2,
                }
            )
        )
    commands: list[list[str]] = []

    def stop(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            state = "inactive" if "external-pi@" in command[-1] else "active"
            return SimpleNamespace(returncode=0, stdout=f"{state}\n")
        if "external-pi@" in command[-1]:
            for spec in old_specs:
                (tmp_path / f"{spec.worker_id}.json").write_text(
                    json.dumps(
                        {
                            "protocol": lifecycle.CONTRACT_VERSION,
                            "release_id": "old-release",
                            "worker_id": spec.worker_id,
                            "state": "offline",
                            "drained": True,
                            "authenticated": True,
                            "registered": True,
                            "generation": 1,
                            "heartbeats": 2,
                            "maximum_sessions": 2,
                        }
                    )
                )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    lifecycle.stop_slot("staging", "green", "old-release")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]
    assert all(
        (tmp_path / f"{spec.worker_id}.json").is_file() for spec in old_specs[:8]
    )
    assert all(
        not (tmp_path / f"{spec.worker_id}.json").exists() for spec in old_specs[8:]
    )


def test_supervisor_status_attests_contract_and_capacity():
    from backend.scripts.run_external_pi_slot import _initial_status

    status = _initial_status(
        SimpleNamespace(
            release_id="release-a",
            chat_external_pi_worker_contract_version="external-pi-v1",
            chat_external_pi_worker_max_sessions=4,
        ),
        "staging-blue-07",
    )

    assert status["protocol"] == "external-pi-v1"
    assert status["maximum_sessions"] == 4


def test_partial_sixteen_replica_status_retains_previous_drain_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for spec in current_specs[:8]:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "current-release",
                    "worker_id": spec.worker_id,
                    "state": "offline",
                    "drained": True,
                    "maximum_sessions": 2,
                }
            )
        )
    selected = lifecycle._draining_replica_specs(
        "staging", "green", "x" * 32, "current-release"
    )

    assert len(selected) == 16
    assert all(spec.maximum_sessions == 2 for spec in selected)


def test_authenticated_endpoints_recover_current_topology_without_status_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    token = "t" * 32
    current_specs = lifecycle.replica_specs("staging", "green", token)
    specs_by_port = {spec.port: spec for spec in current_specs}
    requests: list[urllib.request.Request] = []

    class Response:
        def __init__(self, spec):
            self.spec = spec

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "validated-previous-release",
                    "worker_id": self.spec.worker_id,
                    "state": "ready",
                    "maximum_sessions": self.spec.maximum_sessions,
                }
            ).encode()

    def open_status(request, **_kwargs):
        requests.append(request)
        port = int(urllib.parse.urlparse(request.full_url).port)
        spec = specs_by_port[port]
        assert request.get_header("Authorization") == f"Bearer {spec.token}"
        return Response(spec)

    monkeypatch.setattr(urllib.request, "urlopen", open_status)

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        token,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
        allow_endpoint_recovery=True,
    )

    assert selected == current_specs
    assert len(requests) == len(current_specs)


def test_validated_orphan_release_retains_current_drain_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for spec in current_specs:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "validated-previous-release",
                    "worker_id": spec.worker_id,
                    "state": "draining",
                    "maximum_sessions": spec.maximum_sessions,
                }
            )
        )

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        "x" * 32,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
    )

    assert selected == current_specs


def test_mixed_trusted_release_cohort_falls_back_to_previous_drain_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for index, spec in enumerate(current_specs):
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": (
                        "candidate-release"
                        if index < len(current_specs) // 2
                        else "validated-previous-release"
                    ),
                    "worker_id": spec.worker_id,
                    "state": "draining",
                    "maximum_sessions": spec.maximum_sessions,
                }
            )
        )

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        "x" * 32,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
    )

    assert len(selected) == lifecycle.PREVIOUS_REPLICA_COUNT
    assert all(
        spec.maximum_sessions == lifecycle.PREVIOUS_REPLICA_MAXIMUM_SESSIONS
        for spec in selected
    )


def test_start_checks_every_selected_previous_replica_before_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    specs = lifecycle.replica_specs_for_topology(
        "staging", "blue", "x" * 32, replica_count=16, maximum_sessions=2
    )
    authenticated_specs = lifecycle.replica_specs_for_topology(
        "staging", "blue", "t" * 32, replica_count=16, maximum_sessions=2
    )
    for spec in specs[:8]:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "old-release",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "maximum_sessions": 2,
                }
            )
        )
    specs_by_port = {spec.port: spec for spec in specs}
    authenticated_specs_by_port = {spec.port: spec for spec in authenticated_specs}
    calls = 0

    class Response:
        def __init__(self, spec):
            self.spec = spec

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "worker_id": self.spec.worker_id,
                    "release_id": "old-release",
                    "state": "ready",
                    "active_sessions": 1 if self.spec == specs[8] else 0,
                    "maximum_sessions": 2,
                    "worker_generation": None,
                    "operation_counters": {
                        name: 0 for name in lifecycle.OPERATION_COUNTER_NAMES
                    },
                }
            ).encode()

    def open_status(request, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.URLError("no legacy worker")
        port = int(urllib.parse.urlparse(request.full_url).port)
        assert request.get_header("Authorization") == (
            f"Bearer {authenticated_specs_by_port[port].token}"
        )
        return Response(specs_by_port[port])

    commands: list[list[str]] = []
    monkeypatch.setattr(urllib.request, "urlopen", open_status)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command)
        or subprocess.CompletedProcess(command, 0),
    )

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle.start_slot("staging", "blue")

    assert calls == 10
    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)
    assert all((tmp_path / f"{spec.worker_id}.json").is_file() for spec in specs[:8])


def test_stop_without_durable_drain_evidence_leaves_worker_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "registered": True,
                "generation": 3,
            }
        )
    )
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@blue.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@blue.service",
        ],
    ]


def test_failed_worker_unit_is_not_treated_as_a_running_orphan(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="failed\n"),
    )

    assert lifecycle._worker_is_inactive("staging", "blue") is True


@pytest.mark.parametrize(
    "contents",
    [
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=4\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=301\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=sixty\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=0\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=6\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=nan\n",
    ],
)
def test_drain_stop_timeout_rejects_invalid_protected_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
):
    (tmp_path / "staging.env").write_text(contents)
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)

    with pytest.raises(ValueError, match="drain"):
        lifecycle.drain_stop_timeout_seconds("staging")


def test_candidate_failure_before_registration_stops_worker_after_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-green.json").write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "starting",
                "registered": False,
                "generation": None,
            }
        )
    )
    commands: list[tuple[list[str], bool, float | None]] = []
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )

    def successful_stop(command, *, check, timeout=None):
        commands.append((command, check, timeout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", successful_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate unavailable"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        (
            ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
            True,
            315,
        ),
        (
            [
                "systemctl",
                "stop",
                "paperswithcode-staging-external-pi-worker@green.service",
            ],
            True,
            None,
        ),
    ]


def test_candidate_failure_stops_registered_worker_after_durable_offline_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text("")
    status = tmp_path / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "ready",
                "registered": True,
                "generation": 4,
            }
        )
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def stop(command, **_kwargs):
        commands.append(command)
        if "external-pi@" in command[-1]:
            status.write_text(
                json.dumps(
                    {
                        "release_id": "release-green",
                        "worker_id": "staging-green",
                        "state": "offline",
                        "registered": False,
                        "generation": 4,
                        "drained": True,
                    }
                )
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate unavailable"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


@pytest.mark.parametrize("post_stop_state", [None, "ready", "failed"])
def test_candidate_failure_without_durable_drain_proof_leaves_worker_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    post_stop_state: str | None,
):
    (tmp_path / "staging.env").write_text("")
    status = tmp_path / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "ready",
                "registered": True,
                "generation": 4,
            }
        )
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def successful_stop(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        if "external-pi@" in command[-1]:
            if post_stop_state is None:
                status.unlink()
            else:
                status.write_text(
                    json.dumps(
                        {
                            "release_id": "release-green",
                            "worker_id": "staging-green",
                            "state": post_stop_state,
                            "registered": True,
                            "generation": 4,
                        }
                    )
                )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", successful_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@green.service",
        ],
    ]


def test_candidate_cleanup_leaves_worker_running_if_supervisor_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text("")
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def failed_stop(command, **_kwargs):
        commands.append(command)
        raise lifecycle.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle.subprocess, "run", failed_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate cleanup failed"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"]
    ]


@pytest.mark.parametrize(
    "status_value",
    [
        None,
        "not-json",
        {
            "release_id": "new-candidate",
            "worker_id": "staging-green",
            "state": "starting",
            "registered": False,
        },
        {
            "release_id": "new-candidate",
            "worker_id": "staging-blue",
            "state": "offline",
            "drained": True,
        },
        {
            "release_id": "previous-release",
            "worker_id": "staging-green",
            "state": "offline",
            "drained": True,
        },
    ],
)
def test_stop_without_exact_status_proof_leaves_active_worker_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_value: dict | str | None,
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    if status_value is not None:
        (tmp_path / "staging-green.json").write_text(
            status_value if isinstance(status_value, str) else json.dumps(status_value)
        )
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "green", "new-candidate")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@green.service",
        ],
    ]


def test_stop_without_status_proof_accepts_exact_inactive_worker_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="inactive\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    lifecycle.stop_slot("staging", "green", "new-candidate")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


def test_missing_orphan_token_preserves_lifecycle_error_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "_protected_environment_values", lambda _env: {})

    def run(command, **_kwargs):
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "green", "new-candidate")


def test_disabled_switch_is_a_complete_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = tmp_path / "staging.env"
    config.write_text("PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n")
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "prepare_candidate",
        lambda *_args: pytest.fail("disabled lifecycle started a service"),
    )

    assert not lifecycle.prepare_candidate_if_enabled("staging", "blue", "release")
    assert not lifecycle.stop_slot_if_enabled("staging", "blue", "release")
    assert not lifecycle.prepare_candidate_if_enabled("production", "blue", "release")


def test_launcher_execs_release_python_with_only_scrubbed_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = tmp_path / "release"
    python_runtime = tmp_path / "python-runtime"
    python = python_runtime / "bin/python"
    resolved = lifecycle.ExternalPiSlot(
        slot="blue",
        port=8766,
        worker_id="staging-blue",
        release=release,
        release_id="release-blue",
        runtime=tmp_path / "external-runtime",
        node=tmp_path / "external-runtime/node/bin/node",
        entry_point=tmp_path / "external-runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "external-runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    monkeypatch.setattr(
        launcher,
        "resolve_slot",
        lambda environment, slot: (
            release,
            python_runtime,
            {"release_id": "release-blue"},
        ),
    )
    fleet = tuple(
        replace(
            resolved,
            port=spec.port,
            worker_id=spec.worker_id,
            status_path=tmp_path / f"{spec.worker_id}.json",
        )
        for spec in lifecycle.replica_specs("staging", "blue", "t" * 32)
    )
    monkeypatch.setattr(launcher, "resolve_external_pi_replicas", lambda *_args: fleet)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    monkeypatch.setenv(
        "PWC_EXTERNAL_PI_STATE_ROOT", "/run/paperswithcode/external-pi-blue"
    )
    monkeypatch.setenv("PWC_HF_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    executed: dict = {}

    def run_fleet(commands, environments, *, cwd):
        executed.update(commands=commands, environments=environments, cwd=cwd)
        raise RuntimeError("exec")

    monkeypatch.setattr(launcher, "run_process_fleet", run_fleet)
    monkeypatch.setattr(launcher.sys, "argv", ["launcher", "staging", "blue"])

    with pytest.raises(RuntimeError, match="exec"):
        launcher.main()

    assert (
        executed["commands"]
        == [
            [
                str(python),
                "-m",
                "backend.scripts.run_external_pi_slot",
            ]
        ]
        * 8
    )
    assert [
        value["PWC_EXTERNAL_PI_WORKER_ID"] for value in executed["environments"]
    ] == [
        spec.worker_id for spec in lifecycle.replica_specs("staging", "blue", "t" * 32)
    ]
    assert all(
        "PWC_EXTERNAL_PI_PORT" not in value for value in executed["environments"]
    )
    assert all("PWC_HF_TOKEN" not in value for value in executed["environments"])
    assert all("OPENAI_API_KEY" not in value for value in executed["environments"])


def test_worker_launcher_execs_node_with_only_dedicated_worker_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = lifecycle.ExternalPiSlot(
        slot="blue",
        port=8766,
        worker_id="staging-blue",
        release=tmp_path / "release",
        release_id="release-blue",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/app/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    fleet = tuple(
        replace(
            resolved,
            port=spec.port,
            worker_id=spec.worker_id,
            status_path=tmp_path / f"{spec.worker_id}.json",
        )
        for spec in lifecycle.replica_specs("staging", "blue", "t" * 32)
    )
    monkeypatch.setattr(
        worker_launcher, "resolve_external_pi_replicas", lambda *_args: fleet
    )
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 32)
    monkeypatch.setenv(
        "PWC_EXTERNAL_PI_STATE_ROOT", "/run/paperswithcode/external-pi-blue"
    )
    monkeypatch.setenv("PWC_DB_PASSWORD", "must-not-leak")
    monkeypatch.setenv("PWC_OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setattr(worker_launcher.Path, "mkdir", lambda *_args, **_kwargs: None)
    executed: dict = {}

    def run_fleet(commands, environments, *, cwd, launch_interval_seconds=0):
        executed.update(
            commands=commands,
            environments=environments,
            cwd=cwd,
            launch_interval_seconds=launch_interval_seconds,
        )
        raise RuntimeError("exec")

    monkeypatch.setattr(worker_launcher, "run_process_fleet", run_fleet)
    monkeypatch.setattr(
        worker_launcher.sys, "argv", ["worker-launcher", "staging", "blue"]
    )

    with pytest.raises(RuntimeError, match="exec"):
        worker_launcher.main()

    assert executed["commands"][0] == [
        str(resolved.node),
        "--import",
        str(resolved.runtime / "app/node_modules/tsx/dist/loader.mjs"),
        str(resolved.entry_point),
    ]
    assert len(executed["commands"]) == 8
    assert executed["launch_interval_seconds"] == 5.0
    assert set(executed["environments"][0]) == {
        "PWC_EXTERNAL_PI_HOST",
        "PWC_EXTERNAL_PI_PORT",
        "PWC_EXTERNAL_PI_TOKEN",
        "PWC_EXTERNAL_PI_MAX_SESSIONS",
        "PWC_EXTERNAL_PI_WORKER_ID",
        "PWC_EXTERNAL_PI_INSTANCE_ID",
        "PWC_EXTERNAL_PI_RELEASE_ID",
        "PWC_EXTERNAL_PI_PROMPT_PATH",
        "PWC_EXTERNAL_PI_TOOL_NAMES",
        "PWC_CHAT_PWC_MCP_ENABLED",
        "PWC_EXTERNAL_PI_STATE_ROOT",
    }
    assert all("PWC_DB_PASSWORD" not in value for value in executed["environments"])


@pytest.mark.parametrize(
    ("shadow", "supervisor", "expected"),
    [("false", "false", False), ("true", "true", True)],
)
def test_shadow_and_supervisor_flags_must_agree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shadow: str,
    supervisor: str,
    expected: bool,
):
    (tmp_path / "staging.env").write_text(
        f"PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED={shadow}\n"
        f"PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED={supervisor}\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    assert lifecycle.lifecycle_enabled("staging") is expected
    assert lifecycle.lifecycle_enabled("production") is False


@pytest.mark.parametrize(
    ("shadow", "supervisor"), [("true", "false"), ("false", "true")]
)
def test_mismatched_shadow_and_supervisor_flags_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shadow: str,
    supervisor: str,
):
    (tmp_path / "staging.env").write_text(
        f"PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED={shadow}\n"
        f"PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED={supervisor}\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    with pytest.raises(lifecycle.ExternalPiSlotError, match="flags disagree"):
        lifecycle.prepare_candidate_if_enabled("staging", "blue", "release")


def test_distinct_worker_uid_cannot_read_supervisor_process_secrets():
    if os.geteuid() != 0:
        pytest.skip("cross-UID process boundary test requires root")
    supervisor_identity = pwd.getpwnam("pwc-staging")
    worker_identity = pwd.getpwnam("nobody")
    system_python = "/usr/bin/python3"

    def become(identity):
        def switch():
            os.setgid(identity.pw_gid)
            os.setuid(identity.pw_uid)

        return switch

    supervisor = subprocess.Popen(
        [system_python, "-c", "import time; time.sleep(30)"],
        env={"PWC_DB_PASSWORD": "supervisor-secret"},
        preexec_fn=become(supervisor_identity),
    )
    try:
        probe = subprocess.run(
            [
                system_python,
                "-c",
                (
                    "import pathlib,sys; p=pathlib.Path('/proc')/sys.argv[1]/'environ'; "
                    "\ntry: print(p.read_bytes().decode())\n"
                    "except PermissionError: print('permission-denied')"
                ),
                str(supervisor.pid),
            ],
            env={"PWC_EXTERNAL_PI_TOKEN": "worker-only"},
            preexec_fn=become(worker_identity),
            text=True,
            capture_output=True,
            check=True,
        )
    finally:
        supervisor.terminate()
        supervisor.wait(timeout=5)

    assert probe.stdout.strip() == "permission-denied"
    assert "supervisor-secret" not in probe.stdout


def test_lifecycle_starts_worker_before_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    events: list[object] = []
    monkeypatch.setattr(
        lifecycle,
        "sync_worker_environment",
        lambda environment: events.append(("sync", environment)),
    )

    def run(command, **_kwargs):
        events.append(command)
        if command[:2] == ["systemctl", "show"]:
            return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    lifecycle.start_slot("staging", "blue")

    assert events == [
        ("sync", "staging"),
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        [
            "systemctl",
            "start",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        ["systemctl", "start", "paperswithcode-staging-external-pi@blue.service"],
    ]


def test_lifecycle_restarts_exact_zero_session_worker_before_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
    commands: list[list[str]] = []
    worker_active = True

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(
                command, 0, stdout="active\n" if worker_active else "inactive\n"
            )
        if command[:2] == ["systemctl", "stop"]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": "external-pi-v1",
                    "worker_id": "staging-blue",
                    "instance_id": "00000000-0000-0000-0000-000000000001",
                    "release_id": "older-release-staging",
                    "state": "draining",
                    "active_sessions": 0,
                    "maximum_sessions": 32,
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
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    lifecycle.start_slot("staging", "blue")

    stop = [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ]
    start = [
        "systemctl",
        "start",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ]
    assert commands.index(stop) < commands.index(start)


@pytest.mark.parametrize(
    ("worker_state", "active_sessions"),
    (("draining", 0.0), ("ready", 0)),
)
def test_lifecycle_refuses_ambiguous_active_session_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_state: str,
    active_sessions: object,
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(command, 0, stdout="active\n")
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": "external-pi-v1",
                    "worker_id": "staging-blue",
                    "release_id": "older-release-staging",
                    "state": worker_state,
                    "active_sessions": active_sessions,
                    "maximum_sessions": 32,
                }
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle.start_slot("staging", "blue")

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)


def test_lifecycle_refuses_worker_replacement_while_supervisor_is_active(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            return subprocess.CompletedProcess(command, 0, stdout="active\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="supervisor is still active"
    ):
        lifecycle.start_slot("staging", "blue")

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)


def test_lifecycle_bounds_active_worker_status_body(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    read_sizes: list[int] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            read_sizes.append(size)
            return b"x" * size

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(lifecycle.ExternalPiSlotError, match="status is unavailable"):
        lifecycle._stop_proven_orphaned_worker_if_active("staging", "blue")

    assert read_sizes == [65_537, 65_537]


def _install_active_worker_status(
    monkeypatch: pytest.MonkeyPatch, status: dict
) -> list[list[str]]:
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    monkeypatch.setattr(
        lifecycle,
        "_read_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "failed",
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    commands: list[list[str]] = []
    worker_active = True

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(
                command, 0, stdout="active\n" if worker_active else "inactive\n"
            )
        if command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(status).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    def open_status(request, *, timeout):
        assert request.full_url == "http://127.0.0.1:8766/v1/status"
        assert request.get_header("Authorization") == f"Bearer {'t' * 32}"
        assert timeout == 5
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_status)
    return commands


def _unclaimed_worker_status() -> dict:
    return {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 32,
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


def test_stale_failed_supervisor_proves_zero_use_bound_worker_is_expired(tmp_path):
    status_path = tmp_path / "staging-blue-00.json"
    status_path.write_text("{}")
    os.utime(status_path, (0, 0))
    counters = {
        "shadow_requests": 0,
        "model_calls": 0,
        "tool_calls": 0,
        "provider_calls": 0,
        "modal_calls": 0,
        "billing_events": 0,
    }
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 2,
        "worker_generation": 5,
        "operation_counters": counters,
    }
    durable = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "failed",
        "maximum_sessions": 2,
        "generation": 5,
    }

    assert lifecycle._stale_bound_worker_is_proven(
        endpoint,
        durable,
        status_path=status_path,
        trusted_release_ids=frozenset({"release-blue"}),
        lease_seconds=30,
        now=100,
    )
    assert not lifecycle._stale_bound_worker_is_proven(
        endpoint,
        durable,
        status_path=status_path,
        trusted_release_ids=frozenset({"release-blue"}),
        lease_seconds=30,
        now=20,
    )


def test_expired_database_lease_proves_zero_use_bound_worker_is_expired():
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 2,
        "worker_generation": 5,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    database_status = {
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "contract_version": "external-pi-v1",
        "generation": 5,
        "state": "ready",
        "maximum_sessions": 2,
        "active_sessions": 0,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"release-blue"}),
    )
    database_status["lease_expired"] = False
    assert not lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"release-blue"}),
    )


def test_expired_database_lease_proves_used_idle_worker_is_expired():
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "release_id": "old-release",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 4,
        "worker_generation": 5,
        "operation_counters": {
            "shadow_requests": 3,
            "model_calls": 3,
            "tool_calls": 2,
            "provider_calls": 3,
            "modal_calls": 2,
            "billing_events": 3,
        },
    }
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 5,
        "state": "ready",
        "maximum_sessions": 4,
        "active_sessions": 0,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize("state", ("draining", "ready"))
def test_expired_database_lease_proves_stable_draining_turns_are_orphaned(state):
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": state,
        "active_sessions": 3,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 381,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 7,
        "state": state,
        "maximum_sessions": 4,
        "active_sessions": 3,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._orphaned_draining_turns_are_proven(
        endpoint,
        endpoint.copy(),
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize(
    ("target", "field", "unsafe_value"),
    (
        ("first", "state", "offline"),
        ("second", "active_sessions", 2),
        ("second", "operation_counters", {"model_calls": 382}),
        ("database", "lease_expired", False),
        ("database", "reservation_free", False),
        ("database", "active_sessions", 2),
        ("database", "instance_id", "00000000-0000-0000-0000-000000000002"),
    ),
)
@pytest.mark.parametrize("state", ("draining", "ready"))
def test_orphaned_draining_turn_proof_rejects_live_or_changing_work(
    target: str,
    field: str,
    unsafe_value: object,
    state: str,
):
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": state,
        "active_sessions": 3,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 381,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    first = endpoint.copy()
    second = endpoint.copy()
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 7,
        "state": state,
        "maximum_sessions": 4,
        "active_sessions": 3,
        "lease_expired": True,
        "reservation_free": True,
    }
    selected = {"first": first, "second": second, "database": database_status}
    selected[target][field] = unsafe_value

    assert not lifecycle._orphaned_draining_turns_are_proven(
        first,
        second,
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize("backend_inactive", (True, False))
@pytest.mark.parametrize("state", ("draining", "ready"))
def test_only_an_inactive_backend_allows_orphaned_draining_turns_to_stop(
    monkeypatch: pytest.MonkeyPatch,
    backend_inactive: bool,
    state: str,
):
    worker_active = True

    def worker_is_inactive(*_args):
        return not worker_active

    monkeypatch.setattr(lifecycle, "_worker_is_inactive", worker_is_inactive)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle, "_backend_slot_is_inactive", lambda *_args: backend_inactive
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {
            "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
        },
    )
    specs = lifecycle.replica_specs("production", "blue", "t" * 32)
    statuses = {
        spec.worker_id: {
            "protocol": "external-pi-v1",
            "worker_id": spec.worker_id,
            "instance_id": f"00000000-0000-0000-0000-{index:012d}",
            "release_id": "old-release",
            "state": state,
            "active_sessions": 3 if index == 0 else 0,
            "maximum_sessions": 4,
            "worker_generation": 7,
            "operation_counters": {
                "shadow_requests": 0,
                "model_calls": 381 if index == 0 else 0,
                "tool_calls": 0,
                "provider_calls": 0,
                "modal_calls": 0,
                "billing_events": 0,
            },
        }
        for index, spec in enumerate(specs)
    }
    database_statuses = {
        spec.worker_id: {
            "worker_id": spec.worker_id,
            "instance_id": statuses[spec.worker_id]["instance_id"],
            "release_id": "old-release",
            "contract_version": "external-pi-v1",
            "generation": 7,
            "state": state,
            "maximum_sessions": 4,
            "active_sessions": statuses[spec.worker_id]["active_sessions"],
            "lease_expired": True,
            "reservation_free": True,
        }
        for spec in specs
    }
    commands: list[list[str]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        lifecycle, "_worker_status", lambda spec: statuses[spec.worker_id].copy()
    )
    monkeypatch.setattr(
        lifecycle,
        "_read_database_worker_statuses",
        lambda *_args: database_statuses,
    )
    monkeypatch.setattr(lifecycle.time, "sleep", sleeps.append)

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "stop"]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    def invocation():
        lifecycle._stop_proven_orphaned_worker_if_active(
            "production",
            "blue",
            worker_active_proven=True,
            expected_release_id="old-release",
            draining_specs=specs,
            allow_orphaned_turn_reap=True,
        )

    if backend_inactive:
        invocation()
        assert commands == [
            [
                "systemctl",
                "stop",
                "paperswithcode-production-external-pi-worker@blue.service",
            ]
        ]
    else:
        with pytest.raises(
            lifecycle.ExternalPiSlotError, match="not proven safe to restart"
        ):
            invocation()
        assert commands == []
    assert sleeps == ([5] if backend_inactive else [])


def test_orphaned_draining_turns_are_reap_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "_backend_slot_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {
            "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
        },
    )
    specs = lifecycle.replica_specs("production", "blue", "t" * 32)
    status = {
        "protocol": "external-pi-v1",
        "worker_id": specs[0].worker_id,
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": "draining",
        "active_sessions": 1,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {name: 0 for name in lifecycle.OPERATION_COUNTER_NAMES},
    }
    monkeypatch.setattr(lifecycle, "_worker_status", lambda _spec: status)

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle._stop_proven_orphaned_worker_if_active(
            "production",
            "blue",
            worker_active_proven=True,
            expected_release_id="old-release",
            draining_specs=specs,
        )


def test_stop_slot_cleans_exact_unclaimed_request_free_worker(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = _install_active_worker_status(monkeypatch, _unclaimed_worker_status())

    lifecycle.stop_slot("staging", "blue", "release-blue")

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands


def test_stop_slot_cleans_unclaimed_worker_from_validated_orphan_release(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    status["release_id"] = "validated-previous-release"
    commands = _install_active_worker_status(monkeypatch, status)

    lifecycle.stop_slot(
        "staging",
        "blue",
        "candidate-release",
        validated_orphan_release_ids=frozenset({"validated-previous-release"}),
    )

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("protocol", "external-pi-v2"),
        ("worker_id", "staging-green"),
        ("release_id", "other-release"),
        ("state", "starting"),
        ("worker_generation", 0),
        ("active_sessions", 0.0),
        ("active_sessions", 1),
        ("maximum_sessions", 32.0),
        ("maximum_sessions", 31),
    ),
)
def test_stop_slot_refuses_ambiguous_unclaimed_worker_identity_or_capacity(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    unsafe_value: object,
):
    status = _unclaimed_worker_status()
    status[field] = unsafe_value
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_refuses_unclaimed_worker_without_explicit_null_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    del status["worker_generation"]
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


@pytest.mark.parametrize(
    ("counter", "unsafe_value"),
    (
        ("shadow_requests", True),
        ("model_calls", 0.0),
        ("tool_calls", 1),
        ("provider_calls", 1),
        ("modal_calls", 1),
        ("billing_events", 1),
    ),
)
def test_stop_slot_refuses_unclaimed_worker_with_ambiguous_operation_evidence(
    monkeypatch: pytest.MonkeyPatch,
    counter: str,
    unsafe_value: object,
):
    status = _unclaimed_worker_status()
    status["operation_counters"][counter] = unsafe_value
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_refuses_unclaimed_worker_with_incomplete_operation_evidence(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    del status["operation_counters"]["billing_events"]
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_cleans_exact_orphan_with_authenticated_zero_session_proof(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    monkeypatch.setattr(
        lifecycle,
        "_read_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "failed",
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    commands: list[list[str]] = []
    worker_active = True

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(
                command, 0, stdout="active\n" if worker_active else "inactive\n"
            )
        if command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": "external-pi-v1",
                    "worker_id": "staging-blue",
                    "state": "draining",
                    "active_sessions": 0,
                    "maximum_sessions": 32,
                }
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    lifecycle.stop_slot("staging", "blue", "release-blue")

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands


def test_dedicated_worker_environment_contains_only_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=" + "t" * 32 + "\n"
        "PWC_DB_PASSWORD=must-not-leak\n"
        "PWC_OPENAI_API_KEY=must-not-leak\n"
    )
    worker_environment = tmp_path / "external-pi-worker.env"
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "WORKER_CONFIG", worker_environment)
    monkeypatch.setattr(
        lifecycle.grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=1234)
    )
    ownership: list[tuple[int, int]] = []
    monkeypatch.setattr(
        lifecycle.os,
        "chown",
        lambda _path, user, group: ownership.append((user, group)),
    )

    lifecycle.sync_worker_environment("staging")

    assert worker_environment.read_text() == (
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=" + "t" * 32 + "\n"
    )
    assert worker_environment.stat().st_mode & 0o777 == 0o640
    assert ownership == [(0, 1234)]


def test_systemd_templates_split_worker_and_supervisor_credentials():
    supervisor = (
        Path(__file__).parents[2]
        / "deploy/systemd/paperswithcode-staging-external-pi@.service"
    ).read_text()
    worker = (
        Path(__file__).parents[2]
        / "deploy/systemd/paperswithcode-staging-external-pi-worker@.service"
    ).read_text()

    assert "User=pwc-staging" in supervisor
    assert "EnvironmentFile=/etc/paperswithcode/staging.env" in supervisor
    assert "external_pi_slot_launcher.py staging %i" in supervisor
    assert "User=pwc-external-pi" in worker
    assert "EnvironmentFile=/etc/paperswithcode/external-pi-worker.env" in worker
    assert (
        "BindReadOnlyPaths=/etc/paperswithcode/external-pi-hosts:/etc/hosts" in worker
    )
    assert "RuntimeDirectory=paperswithcode/external-pi-%i" in worker
    assert "PWC_EXTERNAL_PI_STATE_ROOT=/run/paperswithcode/external-pi-%i" in worker
    assert "external_pi_worker_launcher.py staging %i" in worker
    assert "staging.env" not in worker
    assert "ProtectProc=invisible" in worker
    assert "CPUQuota=400%" in worker
    assert "MemoryMax=6442450944" in worker
    assert "TasksMax=512" in worker
    assert "CPUQuota=200%" in supervisor
    assert "MemoryMax=2147483648" in supervisor
    assert "TasksMax=256" in supervisor
    timeout_line = next(
        line for line in supervisor.splitlines() if line.startswith("TimeoutStopSec=")
    )
    assert (
        int(timeout_line.partition("=")[2])
        > lifecycle.MAXIMUM_DRAIN_STOP_TIMEOUT_SECONDS
    )


def test_external_pi_hosts_bypasses_the_public_cdn_only_for_the_worker(
    tmp_path: Path,
):
    hosts = tmp_path / "external-pi-hosts"

    install_host_layout.install_external_pi_hosts(hosts)

    assert hosts.read_text() == (
        "127.0.0.1 localhost chat-gateway-staging.paperswithcode.co "
        "chat-gateway.paperswithcode.co\n"
        "::1 localhost ip6-localhost ip6-loopback "
        "chat-gateway-staging.paperswithcode.co chat-gateway.paperswithcode.co\n"
    )
    assert hosts.stat().st_mode & 0o777 == 0o644


def test_deployment_status_reports_shadow_unit_and_durable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    environments = tmp_path / "environments"
    (environments / "staging").mkdir(parents=True)
    monkeypatch.setattr(deploy_cli, "APP_ROOT", tmp_path)
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(deploy_cli, "RUNTIME_LOCK", tmp_path / "runtime-lock")
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=None, previous=None),
    )
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: "blue")
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: True
    )
    monkeypatch.setattr(deploy_cli, "_slot_release", lambda *_args: None)
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda unit: "active")
    monkeypatch.setattr(deploy_cli, "_unix_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "external_pi_slot_status",
        lambda _environment, slot: {
            "worker_id": f"staging-{slot}",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    )

    assert deploy_cli.status(Namespace()) == 0

    value = json.loads(capsys.readouterr().out)
    shadow = value["environments"]["staging"]["slots"]["blue"]["external_pi_shadow"]
    assert shadow == {
        "supervisor": "active",
        "worker": "active",
        "lifecycle": {
            "worker_id": "staging-blue",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    }


def test_worker_status_tolerates_the_window_before_the_worker_binds(
    monkeypatch: pytest.MonkeyPatch,
):
    # systemd reports the Type=simple worker unit active as soon as it execs,
    # while the Node process is still loading the Pi runtime and has not bound
    # its port. A single attempt turned that into a refused connection that
    # failed the whole deployment.
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    attempts = {"n": 0}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, _size):
            return json.dumps({"worker_id": spec.worker_id, "state": "ready"}).encode()

    def urlopen(_request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionRefusedError(111, "Connection refused")
        return _Response()

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)

    assert lifecycle._worker_status(spec)["worker_id"] == spec.worker_id
    assert attempts["n"] == 3


def test_worker_status_gives_up_after_the_bind_grace_expires(
    monkeypatch: pytest.MonkeyPatch,
):
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    clock = {"now": 0.0}

    def urlopen(_request, timeout=None):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        lifecycle.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with pytest.raises(ConnectionRefusedError):
        lifecycle._worker_status(spec)


def test_worker_status_never_retries_a_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    attempts = {"n": 0}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, _size):
            return b"x" * (lifecycle.MAXIMUM_WORKER_STATUS_BYTES + 1)

    def urlopen(_request, timeout=None):
        attempts["n"] += 1
        return _Response()

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match="too large"):
        lifecycle._worker_status(spec)
    assert attempts["n"] == 1
