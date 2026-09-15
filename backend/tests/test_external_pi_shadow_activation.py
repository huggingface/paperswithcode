from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deploy.external_pi_shadow_activation import (
    INERT_FLAGS,
    QualificationEvidence,
    ShadowActivationError,
    ShadowActivationInterrupted,
    _unit_is_inactive,
    _validate_report,
    activation_signal_context,
    apply_staging_shadow_activation,
    deactivate_external_pi_slots,
    refresh_command,
    run_temporary_shadow_qualification,
    temporary_worker_token_file,
)


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def _env_values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    )


def _send_signal_burst(process: subprocess.Popen, order: tuple[int, int]) -> None:
    for number in order:
        os.kill(process.pid, number)


def _release(root: Path, release_id: str = "release-a") -> Path:
    release = root / "releases" / release_id
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps({"release_id": release_id, "git_sha": "a" * 40})
    )
    environment = root / "environments/staging"
    environment.mkdir(parents=True)
    (environment / "current").symlink_to(release)
    return release


def _evidence() -> QualificationEvidence:
    return QualificationEvidence("staging-blue", 4, 5, 6, True, True, "n" * 32)


def _report(
    path: Path,
    *,
    passed: bool = True,
    release_id: str = "release-a",
    evidence: QualificationEvidence | None = None,
):
    evidence = evidence or _evidence()
    case_names = (
        "linear_history",
        "branching_history",
        "tool_history",
        "eight_isolated_sessions",
        "capacity_no_queue",
        "restart_after_lease_expiry",
        "stale_generation_fencing",
        "drain_recovery",
        "zero_external_work",
    )
    path.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "worker_id": evidence.worker_id,
                "worker_generation": evidence.recovery_generation,
                "qualification_nonce": evidence.nonce,
                "qualified_at_unix_ms": int(time.time() * 1000),
                "passed": passed,
                "case_count": 9,
                "duration_ms": 12,
                "external_work_counts": {
                    "shadow_requests": 20,
                    "model_calls": 0,
                    "tool_calls": 0,
                    "provider_calls": 0,
                    "modal_calls": 0,
                    "billing_events": 0,
                },
                "cases": [
                    {
                        "name": name,
                        "passed": passed,
                        "count": 1,
                        "duration_ms": 1,
                        "failure_code": None if passed else "failed",
                    }
                    for name in case_names
                ],
            }
        )
    )


def test_temporary_replica_token_file_is_private_and_removed(tmp_path: Path):
    token = "derived-token-" + "x" * 32

    with temporary_worker_token_file(token, tmp_path) as path:
        assert path.read_text() == f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={token}\n"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert path.exists() is False


def test_temporary_qualification_uses_explicit_replica_identity(tmp_path: Path):
    observed = []
    generations = iter((4, 6))

    evidence = run_temporary_shadow_qualification(
        environment="staging",
        slot="blue",
        release_id="release-a",
        report_path=tmp_path / "report.json",
        worker_id="staging-blue-00",
        start=lambda *_args: None,
        authenticated=lambda *_args: next(generations),
        expire_and_restart=lambda *_args: 5,
        stale_probe=lambda worker_id, *_args: observed.append(worker_id) or True,
        qualify=lambda value, _path: observed.append(value.worker_id),
        stop=lambda *_args: None,
    )

    assert evidence.worker_id == "staging-blue-00"
    assert observed == ["staging-blue-00", "staging-blue-00"]


@pytest.mark.parametrize("mcp_flag", ["", "PWC_CHAT_PWC_MCP_ENABLED=true\n"])
def test_guard_enables_only_shadow_lifecycle_and_preserves_token(
    tmp_path: Path, mcp_flag: str
):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_DB_NAME=pwc\n"
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true\n"
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED=true\n"
    )
    worker = config / "external-pi-worker.env"
    worker.write_text(f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n" + mcp_flag)
    worker.chmod(0o640)
    report = tmp_path / "report.json"
    refreshed = []
    events = []
    units = {"worker": "inactive", "supervisor": "inactive"}

    def qualify(release_id, _git_sha, report_path, leave_recovery_running):
        values = dict(
            line.split("=", 1)
            for line in staging.read_text().splitlines()
            if "=" in line
        )
        expected = "true" if leave_recovery_running else "false"
        assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == expected
        assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == expected

        def start(*_args):
            assert units == {"worker": "inactive", "supervisor": "inactive"}
            units.update(worker="active", supervisor="active")
            events.append("temporary-start")

        generations = iter((4, 6))

        def authenticated(*_args):
            assert units == {"worker": "active", "supervisor": "active"}
            events.append("authenticated")
            return next(generations)

        def expire(*_args):
            events.append("lease-expiry-restart")
            return 5

        def stale(*_args):
            events.append("stale-fenced")
            return True

        def stop(*_args):
            units.update(worker="inactive", supervisor="inactive")
            events.append("temporary-stop")

        def write_report(evidence, destination):
            events.append("qualified")
            _report(destination, evidence=evidence)

        return run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id=release_id,
            report_path=report_path,
            start=start,
            authenticated=authenticated,
            expire_and_restart=expire,
            stale_probe=stale,
            qualify=write_report,
            stop=stop,
            leave_recovery_running=leave_recovery_running,
        )

    def refresh(sha):
        refreshed.append(sha)
        units.update(worker="active", supervisor="active")
        events.append("deploy-qualified-active")

    result = apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=report,
        enabled=True,
        app_root=tmp_path,
        config_root=config,
        qualify=qualify,
        deactivate=None,
        refresh=refresh,
    )

    values = dict(
        line.split("=", 1) for line in staging.read_text().splitlines() if "=" in line
    )
    assert result == {"release_id": "release-a", "enabled": True}
    assert mcp_flag in worker.read_text()
    assert refreshed == ["a" * 40]
    lifecycle_events = [
        "temporary-stop",
        "temporary-start",
        "authenticated",
        "lease-expiry-restart",
        "stale-fenced",
        "temporary-stop",
        "temporary-start",
        "authenticated",
        "qualified",
        "temporary-stop",
    ]
    assert (
        events == lifecycle_events + ["deploy-qualified-active"] + lifecycle_events[:-1]
    )
    assert units == {"worker": "active", "supervisor": "active"}
    assert values["PWC_DB_NAME"] == "pwc"
    assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == "true"
    assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "true"
    for key in (
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED",
        "PWC_CHAT_REMOTE_BASH_ENABLED",
        "PWC_CHAT_REMOTE_READ_ENABLED",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED",
    ):
        assert values[key] == "false"
    assert worker.read_text() == (
        f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n" + mcp_flag
    )
    assert stat.S_IMODE(worker.stat().st_mode) == 0o640


def test_guard_binds_accepted_report_to_final_active_worker(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    report = tmp_path / "report.json"
    active_slot = "blue"
    qualified = []

    def qualify(release_id, _git_sha, destination, _leave_recovery_running):
        evidence = QualificationEvidence(
            f"staging-{active_slot}", 4, 5, 6, True, True, f"{active_slot}-nonce" * 4
        )
        qualified.append(evidence.worker_id)
        _report(destination, release_id=release_id, evidence=evidence)
        return evidence

    def refresh(_sha):
        nonlocal active_slot
        active_slot = "green"

    apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=report,
        enabled=True,
        app_root=tmp_path,
        config_root=config,
        qualify=qualify,
        deactivate=lambda *_args: None,
        refresh=refresh,
    )

    accepted = json.loads(report.read_text())
    assert qualified == ["staging-blue", "staging-green"]
    assert accepted["worker_id"] == "staging-green"
    assert accepted["qualification_nonce"] == "green-nonce" * 4


def test_final_active_qualification_failure_disables_and_refreshes(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    report = tmp_path / "report.json"
    calls = 0
    events = []

    def qualify(release_id, _git_sha, destination, _leave_recovery_running):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("final qualification failed")
        evidence = _evidence()
        _report(destination, release_id=release_id, evidence=evidence)
        return evidence

    def refresh(_sha):
        events.append("refresh")

    def deactivate(*_args):
        assert "SHADOW_ENABLED=true" in staging.read_text()
        events.append("deactivate")

    with pytest.raises(RuntimeError, match="final qualification failed"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=qualify,
            deactivate=deactivate,
            refresh=refresh,
        )

    assert events == ["refresh", "deactivate", "refresh"]
    assert "SHADOW_ENABLED=false" in staging.read_text()


def test_installed_flat_layout_direct_helper_loads_lifecycle_modules(tmp_path: Path):
    installed = tmp_path / "paperswithcode-deploy"
    shutil.copytree(Path(__file__).parents[2] / "deploy", installed)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed)

    direct = subprocess.run(
        [sys.executable, str(installed / "external_pi_shadow_activation.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import external_pi_shadow_activation as helper; "
            "assert helper._lifecycle_modules()[0].__name__ == "
            "'external_pi_slot_lifecycle'",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert direct.returncode == 0, direct.stderr
    assert "{staging,production}" in direct.stdout
    assert result.returncode == 0, result.stderr


def test_guard_refuses_production_wrong_release_or_failed_qualification(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text("PWC_DB_NAME=pwc\n")
    report = tmp_path / "report.json"
    _report(report, passed=False)

    for environment, release_id, match in (
        ("production", "release-a", "staging-only"),
        ("staging", "release-b", "exact current release"),
        ("staging", "release-a", "successful qualification"),
    ):
        with pytest.raises(ShadowActivationError, match=match):
            apply_staging_shadow_activation(
                environment=environment,
                expected_release_id=release_id,
                report_path=report,
                enabled=True,
                app_root=tmp_path,
                config_root=config,
                qualify=lambda *_args: _evidence(),
                deactivate=None,
                refresh=lambda _sha: None,
            )


def test_failed_refresh_restores_the_complete_prior_environment(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    original = "PWC_DB_NAME=pwc\nPWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
    staging.write_text(original)
    report = tmp_path / "report.json"

    def qualify(_release, _sha, destination, _leave_recovery_running):
        evidence = _evidence()
        _report(destination, evidence=evidence)
        return evidence

    with pytest.raises(RuntimeError, match="refresh failed"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=qualify,
            deactivate=None,
            refresh=lambda _sha: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

    assert staging.read_text() == original


def test_temporary_qualification_always_drains_and_stops_on_failure(tmp_path: Path):
    events = []
    generations = iter((4, 6))

    with pytest.raises(RuntimeError, match="qualification failed"):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: (
                events.append("authenticated") or next(generations)
            ),
            expire_and_restart=lambda *_args: events.append("restart") or 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("qualification failed")
            ),
            stop=lambda *_args: events.append("stop"),
        )

    assert events == [
        "stop",
        "start",
        "authenticated",
        "restart",
        "stop",
        "start",
        "authenticated",
        "stop",
    ]


@pytest.mark.parametrize(
    "failure",
    (RuntimeError("pre-stop failed"), KeyboardInterrupt()),
)
def test_temporary_qualification_pre_stop_failure_still_runs_final_cleanup(
    tmp_path: Path,
    failure: BaseException,
):
    events = []
    stop_calls = 0

    def stop(*_args):
        nonlocal stop_calls
        stop_calls += 1
        events.append("stop")
        if stop_calls == 1:
            raise failure

    with pytest.raises(type(failure)):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: 4,
            expire_and_restart=lambda *_args: 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: None,
            stop=stop,
        )

    assert events == ["stop", "stop"]


@pytest.mark.parametrize("mcp_flag", ["", "PWC_CHAT_PWC_MCP_ENABLED=true\n"])
def test_disable_drains_active_units_before_flags_false_and_refresh(
    tmp_path: Path, mcp_flag: str
):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
        f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n"
    )
    (config / "external-pi-worker.env").write_text(
        f"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN={'t' * 32}\n" + mcp_flag
    )
    units = {"worker": "active", "supervisor": "active"}
    events = []

    def deactivate(release_id, _git_sha):
        assert release_id == "release-a"
        assert "SHADOW_ENABLED=true" in staging.read_text()
        assert units == {"worker": "active", "supervisor": "active"}
        units.update(worker="inactive", supervisor="inactive")
        events.append("proven-stop")

    def refresh(_sha):
        assert "SHADOW_ENABLED=false" in staging.read_text()
        assert units == {"worker": "inactive", "supervisor": "inactive"}
        events.append("refresh")

    result = apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=tmp_path / "unused.json",
        enabled=False,
        app_root=tmp_path,
        config_root=config,
        qualify=None,
        deactivate=deactivate,
        refresh=refresh,
    )

    assert result == {"release_id": "release-a", "enabled": False}
    assert mcp_flag in (config / "external-pi-worker.env").read_text()
    assert events == ["proven-stop", "refresh"]
    assert units == {"worker": "inactive", "supervisor": "inactive"}


def test_disable_refresh_failure_stays_stopped_and_fail_closed(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    staging.write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
    )
    units = {"worker": "active", "supervisor": "active"}

    def deactivate(*_args):
        units.update(worker="inactive", supervisor="inactive")

    with pytest.raises(ShadowActivationError, match="proven stopped.*remain disabled"):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=tmp_path / "unused.json",
            enabled=False,
            app_root=tmp_path,
            config_root=config,
            qualify=None,
            deactivate=deactivate,
            refresh=lambda _sha: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

    assert units == {"worker": "inactive", "supervisor": "inactive"}
    assert "SHADOW_ENABLED=false" in staging.read_text()


def test_refresh_command_uses_positional_git_sha():
    assert refresh_command("staging", "a" * 40) == [
        "pwc-deploy",
        "staging",
        "a" * 40,
        "--refresh-environment",
    ]


@pytest.mark.parametrize("state", ("inactive", "failed"))
def test_unit_inactive_accepts_exact_non_running_states(
    monkeypatch: pytest.MonkeyPatch, state: str
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, f"{state}\n"),
    )

    assert _unit_is_inactive("external-pi.service") is True


@pytest.mark.parametrize("state", ("active", "activating", "deactivating"))
def test_unit_inactive_refuses_running_or_transitional_states(
    monkeypatch: pytest.MonkeyPatch, state: str
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, f"{state}\n"),
    )

    assert _unit_is_inactive("external-pi.service") is False


def test_unit_inactive_fails_closed_on_systemctl_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "failed\n"),
    )

    assert _unit_is_inactive("external-pi.service") is False

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("systemctl missing")),
    )

    assert _unit_is_inactive("external-pi.service") is False


def test_false_false_disable_still_deactivates_orphan_units(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    events = []

    apply_staging_shadow_activation(
        environment="staging",
        expected_release_id="release-a",
        report_path=tmp_path / "unused.json",
        enabled=False,
        app_root=tmp_path,
        config_root=config,
        qualify=None,
        deactivate=lambda *_args: events.append("deactivate"),
        refresh=lambda _sha: events.append("refresh"),
    )

    assert events == ["deactivate", "refresh"]


def test_deactivation_rejects_active_unit_when_slot_resolution_fails():
    def resolve(_environment, _slot):
        raise ValueError("missing release pointer")

    with pytest.raises(ShadowActivationError, match="blue units remain active"):
        deactivate_external_pi_slots(
            "release-a",
            active_slot="blue",
            resolve=resolve,
            stop=lambda *_args: None,
            unit_inactive=lambda unit: "worker@blue" in unit,
        )


def test_temporary_qualification_cleans_up_on_base_exception(tmp_path: Path):
    events = []
    generations = iter((4, 6))

    with pytest.raises(KeyboardInterrupt):
        run_temporary_shadow_qualification(
            environment="staging",
            slot="blue",
            release_id="release-a",
            report_path=tmp_path / "report.json",
            start=lambda *_args: events.append("start"),
            authenticated=lambda *_args: next(generations),
            expire_and_restart=lambda *_args: 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()),
            stop=lambda *_args: events.append("stop"),
        )

    assert events == ["stop", "start", "stop", "start", "stop"]


def test_enable_restores_flags_and_token_on_refresh_base_exception(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    staging = config / "staging.env"
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    staging.write_text(original)
    report = tmp_path / "report.json"

    def qualify(_release, _sha, destination, _leave_recovery_running):
        evidence = _evidence()
        _report(destination, evidence=evidence)
        return evidence

    with pytest.raises(KeyboardInterrupt):
        apply_staging_shadow_activation(
            environment="staging",
            expected_release_id="release-a",
            report_path=report,
            enabled=True,
            app_root=tmp_path,
            config_root=config,
            qualify=qualify,
            deactivate=None,
            refresh=lambda _sha: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

    assert staging.read_text() == original
    assert not (config / "external-pi-worker.env").exists()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda value: value.update(worker_id="wrong"), "not proven"),
        (lambda value: value.update(worker_generation=5), "not proven"),
        (lambda value: value.update(qualification_nonce="x" * 32), "not proven"),
        (lambda value: value.update(qualified_at_unix_ms=1), "not proven"),
        (lambda value: value.update(duration_ms=True), "not proven"),
    ],
)
def test_report_rejects_identity_replay_and_boolean_integers(
    tmp_path: Path, mutation, match: str
):
    path = tmp_path / "report.json"
    _report(path)
    value = json.loads(path.read_text())
    mutation(value)
    path.write_text(json.dumps(value))

    with pytest.raises(ShadowActivationError, match=match):
        _validate_report(
            path,
            "release-a",
            _evidence(),
            now_unix_ms=int(time.time() * 1000),
        )


def test_real_sigterm_runs_temporary_unit_cleanup(tmp_path: Path):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    activation_signal_context, apply_staging_shadow_activation,
    run_temporary_shadow_qualification,
)
root = Path(sys.argv[1])
events = root / "events"
generations = iter((4, 6))
def record(value):
    with events.open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def qualify(release_id, _sha, report_path, _leave_recovery_running):
    return run_temporary_shadow_qualification(
        environment="staging", slot="blue", release_id=release_id,
        report_path=report_path,
        start=lambda *_args: record("start"),
        authenticated=lambda *_args: next(generations),
        expire_and_restart=lambda *_args: 5,
        stale_probe=lambda *_args: True,
        stop=lambda *_args: record("stop"),
        qualify=lambda *_args: (
            (root / "ready").write_text("ready", encoding="utf-8"),
            time.sleep(30),
        ),
    )
with activation_signal_context():
    apply_staging_shadow_activation(
        environment="staging", expected_release_id="release-a",
        report_path=root / "report.json", enabled=True, app_root=root,
        config_root=root / "config", qualify=qualify, deactivate=None,
        refresh=lambda _sha: None,
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 1
    assert "ShadowActivationInterrupted" in stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "stop",
        "start",
        "stop",
        "start",
        "stop",
    ]
    assert (config / "staging.env").read_text() == original
    assert not (config / "external-pi-worker.env").exists()


def test_activation_signal_context_restores_prior_handlers():
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)

    with activation_signal_context():
        assert signal.getsignal(signal.SIGTERM) != previous_term
        assert signal.getsignal(signal.SIGINT) != previous_int

    assert signal.getsignal(signal.SIGTERM) == previous_term
    assert signal.getsignal(signal.SIGINT) == previous_int


def test_activation_signal_latches_are_independent_across_nested_and_serial_contexts():
    previous = {
        number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)
    }

    with activation_signal_context():
        outer = signal.getsignal(signal.SIGTERM)
        with activation_signal_context():
            inner = signal.getsignal(signal.SIGTERM)
            assert inner is not outer
            with pytest.raises(ShadowActivationInterrupted):
                inner(signal.SIGTERM, None)
            assert inner(signal.SIGINT, None) is None
        assert signal.getsignal(signal.SIGTERM) is outer
        with pytest.raises(ShadowActivationInterrupted):
            outer(signal.SIGINT, None)
        assert outer(signal.SIGTERM, None) is None

    for number, handler in previous.items():
        assert signal.getsignal(number) == handler

    with activation_signal_context():
        serial = signal.getsignal(signal.SIGTERM)
        with pytest.raises(ShadowActivationInterrupted):
            serial(signal.SIGTERM, None)
        assert serial(signal.SIGINT, None) is None

    for number, handler in previous.items():
        assert signal.getsignal(number) == handler


def test_real_sigterm_during_start_still_stops_owned_units(tmp_path: Path):
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    activation_signal_context, run_temporary_shadow_qualification,
)
root = Path(sys.argv[1]); events = root / "events"
def record(value):
    with events.open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def start(*_args):
    record("partially-started")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
with activation_signal_context():
    run_temporary_shadow_qualification(
        environment="staging", slot="blue", release_id="release-a",
        report_path=root / "report.json", start=start,
        authenticated=lambda *_args: 4,
        expire_and_restart=lambda *_args: 5,
        stale_probe=lambda *_args: True,
        qualify=lambda *_args: None,
        stop=lambda *_args: record("stop"),
    )
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    process.terminate()
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 1
    assert "ShadowActivationInterrupted" in stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "stop",
        "partially-started",
        "stop",
    ]


@pytest.mark.parametrize(
    "order",
    [(signal.SIGTERM, signal.SIGINT), (signal.SIGINT, signal.SIGTERM)],
)
def test_real_burst_during_start_enters_and_completes_cleanup_once(
    tmp_path: Path, order: tuple[int, int]
):
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    ShadowActivationInterrupted, activation_signal_context,
    run_temporary_shadow_qualification,
)
root = Path(sys.argv[1]); events = root / "events"
def record(value):
    with events.open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def start(*_args):
    record("partially-started")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
def stop(*_args):
    record("cleanup-enter")
    time.sleep(.1)
    record("cleanup-complete")
try:
    with activation_signal_context():
        run_temporary_shadow_qualification(
            environment="staging", slot="blue", release_id="release-a",
            report_path=root / "report.json", start=start,
            authenticated=lambda *_args: 4,
            expire_and_restart=lambda *_args: 5,
            stale_probe=lambda *_args: True,
            qualify=lambda *_args: None,
            stop=stop,
        )
except ShadowActivationInterrupted:
    record("interruption")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    _send_signal_burst(process, order)
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "cleanup-enter",
        "cleanup-complete",
        "partially-started",
        "cleanup-enter",
        "cleanup-complete",
        "interruption",
    ]


@pytest.mark.parametrize(
    "order",
    [(signal.SIGTERM, signal.SIGINT), (signal.SIGINT, signal.SIGTERM)],
)
def test_real_burst_during_refresh_restores_false_flags(
    tmp_path: Path, order: tuple[int, int]
):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import json, sys, time
from pathlib import Path
import deploy.external_pi_shadow_activation as activation
from deploy.external_pi_shadow_activation import (
    QualificationEvidence, ShadowActivationInterrupted, activation_signal_context,
    apply_staging_shadow_activation,
)
root = Path(sys.argv[1]); config = root / "config"
refresh_calls = 0
original_atomic_write = activation._atomic_write
def slow_rollback(path, content, mode):
    if path.name == "staging.env" and (root / "ready").exists() and b"SHADOW_ENABLED=false" in content:
        (root / "rollback").write_text("rollback", encoding="utf-8")
        time.sleep(1)
    return original_atomic_write(path, content, mode)
activation._atomic_write = slow_rollback
evidence = QualificationEvidence("staging-blue", 4, 5, 6, True, True, "n" * 32)
names = (
    "linear_history", "branching_history", "tool_history",
    "eight_isolated_sessions", "capacity_no_queue",
    "restart_after_lease_expiry", "stale_generation_fencing",
    "drain_recovery", "zero_external_work",
)
def qualify(_release, _sha, destination, _leave_recovery_running):
    destination.write_text(json.dumps({
        "release_id": "release-a", "worker_id": evidence.worker_id,
        "worker_generation": evidence.recovery_generation,
        "qualification_nonce": evidence.nonce,
        "qualified_at_unix_ms": int(time.time() * 1000), "passed": True,
        "case_count": 9, "duration_ms": 1,
        "external_work_counts": {"shadow_requests": 20, "model_calls": 0,
            "tool_calls": 0, "provider_calls": 0, "modal_calls": 0,
            "billing_events": 0},
        "cases": [{"name": name, "passed": True, "count": 1,
            "duration_ms": 1, "failure_code": None} for name in names],
    }), encoding="utf-8")
    return evidence
def deactivate(*_args):
    (root / "deactivated").write_text("one", encoding="utf-8")
    (root / "worker-state").write_text("inactive", encoding="utf-8")
def refresh(_sha):
    global refresh_calls
    refresh_calls += 1
    if refresh_calls > 1:
        (root / "disabled-refresh").write_text("one", encoding="utf-8")
        return
    (root / "worker-state").write_text("active", encoding="utf-8")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
try:
    with activation_signal_context():
        apply_staging_shadow_activation(
            environment="staging", expected_release_id="release-a",
            report_path=root / "report.json", enabled=True, app_root=root,
            config_root=config, qualify=qualify, deactivate=deactivate, refresh=refresh,
        )
except ShadowActivationInterrupted:
    (root / "interruption").write_text("one", encoding="utf-8")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    _send_signal_burst(process, order)
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert (tmp_path / "interruption").read_text() == "one"
    assert (tmp_path / "deactivated").read_text() == "one"
    assert (tmp_path / "worker-state").read_text() == "inactive"
    assert (tmp_path / "disabled-refresh").read_text() == "one"
    assert (tmp_path / "rollback").is_file()
    values = _env_values(config / "staging.env")
    assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == "false"
    assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "false"
    assert all(values[key] == "false" for key in INERT_FLAGS)
    assert (config / "external-pi-worker.env").is_file()


def test_sigterm_after_deactivation_publishes_false_flags_before_delivery(
    tmp_path: Path,
):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=false\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n"
    )
    script = r"""
import json, os, signal, sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    QualificationEvidence, ShadowActivationInterrupted, activation_signal_context,
    apply_staging_shadow_activation,
)
root = Path(sys.argv[1]); calls = 0
evidence = QualificationEvidence("staging-blue", 4, 5, 6, True, True, "n" * 32)
names = (
    "linear_history", "branching_history", "tool_history",
    "eight_isolated_sessions", "capacity_no_queue",
    "restart_after_lease_expiry", "stale_generation_fencing",
    "drain_recovery", "zero_external_work",
)
def qualify(_release, _sha, destination, _leave_recovery_running):
    global calls
    calls += 1
    if calls == 2:
        raise RuntimeError("final qualification failed")
    destination.write_text(json.dumps({
        "release_id": "release-a", "worker_id": evidence.worker_id,
        "worker_generation": evidence.recovery_generation,
        "qualification_nonce": evidence.nonce,
        "qualified_at_unix_ms": int(time.time() * 1000), "passed": True,
        "case_count": 9, "duration_ms": 1,
        "external_work_counts": {"shadow_requests": 20, "model_calls": 0,
            "tool_calls": 0, "provider_calls": 0, "modal_calls": 0,
            "billing_events": 0},
        "cases": [{"name": name, "passed": True, "count": 1,
            "duration_ms": 1, "failure_code": None} for name in names],
    }), encoding="utf-8")
    return evidence
def deactivate(*_args):
    (root / "worker-state").write_text("inactive", encoding="utf-8")
    os.kill(os.getpid(), signal.SIGTERM)
def refresh(_sha):
    with (root / "refreshes").open("a", encoding="utf-8") as handle:
        handle.write("refresh\n")
try:
    with activation_signal_context():
        apply_staging_shadow_activation(
            environment="staging", expected_release_id="release-a",
            report_path=root / "report.json", enabled=True, app_root=root,
            config_root=root / "config", qualify=qualify,
            deactivate=deactivate, refresh=refresh,
        )
except ShadowActivationInterrupted:
    (root / "interruption").write_text("one", encoding="utf-8")
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert process.returncode == 0, process.stderr
    assert (tmp_path / "interruption").read_text() == "one"
    assert (tmp_path / "worker-state").read_text() == "inactive"
    assert (tmp_path / "refreshes").read_text().splitlines() == [
        "refresh",
        "refresh",
    ]
    values = _env_values(config / "staging.env")
    assert values["PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED"] == "false"
    assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "false"


@pytest.mark.parametrize(
    "order",
    [(signal.SIGTERM, signal.SIGINT), (signal.SIGINT, signal.SIGTERM)],
)
def test_real_burst_during_disable_preserves_true_recovery_state(
    tmp_path: Path, order: tuple[int, int]
):
    _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    original = (
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true\n"
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true\n"
    )
    (config / "staging.env").write_text(original)
    script = r"""
import sys, time
from pathlib import Path
from deploy.external_pi_shadow_activation import (
    ShadowActivationRecoveryRequired, activation_signal_context,
    apply_staging_shadow_activation,
)
root = Path(sys.argv[1])
def deactivate(*_args):
    (root / "partial-stop").write_text("partial", encoding="utf-8")
    (root / "ready").write_text("ready", encoding="utf-8")
    time.sleep(30)
try:
    with activation_signal_context():
        apply_staging_shadow_activation(
            environment="staging", expected_release_id="release-a",
            report_path=root / "unused.json", enabled=False, app_root=root,
            config_root=root / "config", qualify=None, deactivate=deactivate,
            refresh=lambda _sha: (root / "refreshed").write_text("bad", encoding="utf-8"),
        )
except ShadowActivationRecoveryRequired:
    (root / "recovery-required").write_text("one", encoding="utf-8")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "ready")
    _send_signal_burst(process, order)
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert (tmp_path / "recovery-required").read_text() == "one"
    assert (tmp_path / "partial-stop").is_file()
    assert not (tmp_path / "refreshed").exists()
    assert (config / "staging.env").read_text() == original
    assert not (config / "external-pi-worker.env").exists()


@pytest.mark.parametrize(
    "order",
    [(signal.SIGTERM, signal.SIGINT), (signal.SIGINT, signal.SIGTERM)],
)
def test_real_burst_during_handler_restoration_restores_all_handlers(
    tmp_path: Path, order: tuple[int, int]
):
    script = r"""
import signal, sys, time
from pathlib import Path
import deploy.external_pi_shadow_activation as activation
root = Path(sys.argv[1])
def record(value):
    with (root / "events").open("a", encoding="utf-8") as handle:
        handle.write(value + "\n")
def prior_term(_number, _frame):
    record("term")
def prior_int(_number, _frame):
    record("int")
signal.signal(signal.SIGTERM, prior_term)
signal.signal(signal.SIGINT, prior_int)
real_signal = activation.signal.signal
def slow_restore(number, handler):
    if number == signal.SIGTERM and handler is prior_term:
        (root / "restoring").write_text("restoring", encoding="utf-8")
        time.sleep(1)
    return real_signal(number, handler)
activation.signal.signal = slow_restore
with activation.activation_signal_context():
    pass
assert signal.getsignal(signal.SIGTERM) is prior_term
assert signal.getsignal(signal.SIGINT) is prior_int
(root / "restored").write_text("restored", encoding="utf-8")
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _wait_for(tmp_path / "restoring")
    _send_signal_burst(process, order)
    _, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr
    assert sorted((tmp_path / "events").read_text().splitlines()) == ["int", "term"]
    assert (tmp_path / "restored").is_file()
