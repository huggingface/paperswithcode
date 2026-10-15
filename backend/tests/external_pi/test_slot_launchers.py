"""Supervisor and worker launchers, flag agreement, and process isolation."""

from __future__ import annotations

import os
import pwd
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import deploy.external_pi_slot_launcher as launcher
import deploy.external_pi_slot_lifecycle as lifecycle
import deploy.external_pi_worker_launcher as worker_launcher


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
        "PWC_API_URL",
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
