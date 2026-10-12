"""Staging durable-external qualification and Modal rate evidence modes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env


def _staging_durable_external_qualification_baseline() -> dict[str, str]:
    return {
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": (
            "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=false"
        ),
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED": (
            "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED=true"
        ),
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": (
            "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=true"
        ),
        "PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED": (
            "PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED=true"
        ),
        "PWC_CHAT_MAX_CONCURRENCY": "PWC_CHAT_MAX_CONCURRENCY=2",
        "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": (
            "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY=4"
        ),
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": ("PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP=3"),
        "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true",
        "PWC_CHAT_PI_PREWARM_ENABLED": "PWC_CHAT_PI_PREWARM_ENABLED=true",
    }


def test_staging_durable_external_qualification_profile_is_exact_and_reversible():
    baseline = _staging_durable_external_qualification_baseline()

    enabled = configure_host_env.staging_durable_external_qualification_values(
        baseline, enabled=True
    )
    qualification_admin_token = enabled.pop("PWC_ADMIN_API_TOKEN")
    assert len(qualification_admin_token) >= 32
    assert enabled == {
        "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "true",
        "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "durable-external-pi-v1",
        "PWC_CHAT_TURN_EVENT_JOURNAL_SCHEMA_ENABLED": "true",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "true",
        "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "sandbox-executor-v1",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "true",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "true",
        "PWC_CHAT_REMOTE_READ_ENABLED": "true",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "false",
        "PWC_CHAT_PI_PREWARM_ENABLED": "false",
        "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "32",
    }

    active = configure_host_env.assign(baseline, enabled)
    disabled = configure_host_env.staging_durable_external_qualification_values(
        active, enabled=False
    )
    assert disabled == {
        "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "false",
        "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "",
        "PWC_CHAT_TURN_EVENT_JOURNAL_SCHEMA_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
        "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "",
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
        "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
        "PWC_CHAT_REMOTE_READ_ENABLED": "false",
        "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_ENABLED": "true",
        "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "4",
        "PWC_ADMIN_API_TOKEN": "",
    }


def test_staging_durable_external_qualification_accepts_implicit_openai_default():
    baseline = _staging_durable_external_qualification_baseline()
    baseline.pop("PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY")

    enabled = configure_host_env.staging_durable_external_qualification_values(
        baseline, enabled=True
    )

    assert enabled["PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY"] == "32"


def test_staging_durable_external_qualification_installs_scoped_admin_token(
    monkeypatch: pytest.MonkeyPatch,
):
    baseline = _staging_durable_external_qualification_baseline()
    monkeypatch.setattr(
        configure_host_env.secrets, "token_urlsafe", lambda _size: "q" * 64
    )

    enabled = configure_host_env.staging_durable_external_qualification_values(
        baseline, enabled=True
    )

    assert enabled["PWC_ADMIN_API_TOKEN"] == "q" * 64
    active = configure_host_env.assign(baseline, enabled)
    disabled = configure_host_env.staging_durable_external_qualification_values(
        active, enabled=False
    )
    assert disabled["PWC_ADMIN_API_TOKEN"] == ""


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED", "true"),
        ("PWC_CHAT_MAX_CONCURRENCY", "32"),
        ("PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY", "8"),
        ("PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP", "16"),
        ("PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED", "false"),
        ("PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED", "false"),
        ("PWC_CHAT_REMOTE_BASH_ENABLED", "true"),
    ),
)
def test_staging_durable_external_qualification_refuses_baseline_drift(key, value):
    baseline = _staging_durable_external_qualification_baseline()
    baseline[key] = f"{key}={value}"

    with pytest.raises(ValueError, match="qualification baseline"):
        configure_host_env.staging_durable_external_qualification_values(
            baseline, enabled=True
        )


@pytest.mark.parametrize("enabled", [True, False])
def test_staging_durable_external_qualification_mode_is_atomic_and_staging_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    enabled: bool,
):
    monkeypatch.setattr(
        configure_host_env.secrets, "token_urlsafe", lambda _size: "q" * 64
    )
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    baseline = _staging_durable_external_qualification_baseline()
    current = (
        baseline
        if enabled
        else configure_host_env.assign(
            baseline,
            configure_host_env.staging_durable_external_qualification_values(
                baseline, enabled=True
            ),
        )
    )
    staging_path = config_root / "staging.env"
    staging_path.write_text(
        "".join(f"{current[key]}\n" for key in sorted(current)), encoding="utf-8"
    )
    production_path = config_root / "production.env"
    production_bytes = b"PRODUCTION=untouched\n"
    production_path.write_bytes(production_bytes)
    written = {}
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_env",
        lambda path, lines, group: written.update(
            {"path": path, "lines": lines, "group": group}
        ),
    )
    action = "enable" if enabled else "disable"
    confirmation = (
        "ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION"
        if enabled
        else "DISABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            f"--staging-durable-external-qualification-{action}-only",
            "--confirm",
            confirmation,
        ],
    )

    assert configure_host_env.main() == 0
    assert written["path"] == staging_path
    assert written["group"] == "pwc-staging"
    assert production_path.read_bytes() == production_bytes
    expected = configure_host_env.staging_durable_external_qualification_values(
        current, enabled=enabled
    )
    assert {
        key: configure_host_env.decoded_value(written["lines"][key]) for key in expected
    } == expected
    assert capsys.readouterr().out == (
        f"{'enabled' if enabled else 'disabled'} staging durable external "
        "qualification profile; no service was restarted\n"
    )


@pytest.mark.parametrize(
    "extra_args",
    (
        (),
        ("--confirm", "DEPLOY_PRODUCTION"),
        (
            "--staging-chat-capacity-only",
            "--confirm",
            "ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION",
        ),
        (
            "--staging-durable-external-qualification-disable-only",
            "--confirm",
            "ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION",
        ),
    ),
)
def test_staging_durable_external_qualification_requires_exact_confirmation_and_runs_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_args: tuple[str, ...],
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    staging_path = config_root / "staging.env"
    staging_path.write_text("KEEP=value\n", encoding="utf-8")
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--staging-durable-external-qualification-enable-only",
            *extra_args,
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()
    assert staging_path.read_text(encoding="utf-8") == "KEEP=value\n"
    assert "staging durable external qualification" in capsys.readouterr().err


def _active_staging_release(tmp_path: Path, release_id: str) -> Path:
    app_root = tmp_path / "app"
    release = app_root / "releases" / release_id
    release.mkdir(parents=True)
    sha = release_id.removesuffix("-staging") + "a" * 28
    (release / "release.json").write_text(
        json.dumps({"git_sha": sha, "release_id": release_id}), encoding="utf-8"
    )
    environment = app_root / "environments" / "staging"
    environment.mkdir(parents=True)
    (environment / "current").symlink_to(release)
    return app_root


def test_staging_modal_rate_evidence_is_exact_release_bound_and_has_no_default(
    tmp_path: Path,
):
    release_id = "a" * 12 + "-staging"
    app_root = _active_staging_release(tmp_path, release_id)

    assert configure_host_env.staging_modal_rate_evidence(
        app_root=app_root,
        release_id=release_id,
        microusd_per_second=53,
    ) == {
        "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "53",
        "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
        "PWC_RELEASE_ID": release_id,
    }
    with pytest.raises(TypeError):
        configure_host_env.staging_modal_rate_evidence(
            app_root=app_root,
            release_id=release_id,
        )
    with pytest.raises(ValueError, match="active immutable staging release"):
        configure_host_env.staging_modal_rate_evidence(
            app_root=app_root,
            release_id="b" * 12 + "-staging",
            microusd_per_second=53,
        )


def test_write_staging_modal_rate_evidence_is_atomic_root_only_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "staging-modal-rate-evidence.json"
    ownership = []
    monkeypatch.setattr(
        configure_host_env.os,
        "chown",
        lambda path, uid, gid: ownership.append((path, uid, gid)),
    )
    values = {
        "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "53",
        "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
        "PWC_RELEASE_ID": "a" * 12 + "-staging",
    }

    configure_host_env.write_staging_modal_rate_evidence(target, values)

    assert json.loads(target.read_text(encoding="utf-8")) == values
    assert target.stat().st_mode & 0o777 == 0o600
    temporary = target.with_name(f".{target.name}.new-{os.getpid()}")
    assert ownership == [(temporary, 0, 0)]
    assert not temporary.exists()
    assert target.stat().st_size <= 4096


@pytest.mark.parametrize("remove", [False, True])
def test_staging_modal_rate_mode_is_confirmed_staging_only_and_content_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    remove: bool,
):
    release_id = "a" * 12 + "-staging"
    app_root = _active_staging_release(tmp_path, release_id)
    config_root = tmp_path / "config"
    config_root.mkdir()
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    production = config_root / "production.env"
    production.write_bytes(b"PRODUCTION=untouched\n")
    target = config_root / "staging-modal-rate-evidence.json"
    if remove:
        target.write_text(
            json.dumps(
                configure_host_env.staging_modal_rate_evidence(
                    app_root=app_root,
                    release_id=release_id,
                    microusd_per_second=53,
                )
            ),
            encoding="utf-8",
        )
        target.chmod(0o600)
    written = {}
    monkeypatch.setattr(configure_host_env, "APP_ROOT", app_root)
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_staging_modal_rate_evidence",
        lambda path, values: written.update({"path": path, "values": values}),
    )
    monkeypatch.setattr(
        configure_host_env,
        "remove_staging_modal_rate_evidence",
        lambda path, expected_release_id: written.update(
            {"removed": path, "release_id": expected_release_id}
        ),
    )
    mode = "remove" if remove else "install"
    confirmation = (
        "REMOVE_STAGING_MODAL_RATE_EVIDENCE"
        if remove
        else "INSTALL_STAGING_MODAL_RATE_EVIDENCE"
    )
    arguments = [
        "configure_host_env.py",
        "--legacy-env",
        str(source),
        f"--staging-modal-rate-evidence-{mode}-only",
        "--staging-modal-rate-release-id",
        release_id,
        "--confirm",
        confirmation,
    ]
    if not remove:
        arguments.extend(["--staging-modal-rate-microusd-per-second", "53"])
    monkeypatch.setattr(sys, "argv", arguments)

    assert configure_host_env.main() == 0
    output = capsys.readouterr().out
    assert "53" not in output
    assert release_id not in output
    assert production.read_bytes() == b"PRODUCTION=untouched\n"
    if remove:
        assert written == {"removed": target, "release_id": release_id}
    else:
        assert written["path"] == target
        assert written["values"]["PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND"] == "53"


def test_staging_modal_rate_mode_rejects_missing_confirmation_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--staging-modal-rate-evidence-install-only",
            "--staging-modal-rate-release-id",
            "a" * 12 + "-staging",
            "--staging-modal-rate-microusd-per-second",
            "53",
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()
    assert not (config_root / "staging-modal-rate-evidence.json").exists()


def test_deployment_runbook_has_reversible_staging_external_qualification_gate():
    runbook = Path("docs/deployment.md").read_text(encoding="utf-8")

    assert "--staging-durable-external-qualification-enable-only" in runbook
    assert "--confirm ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION" in runbook
    assert "--staging-durable-external-qualification-disable-only" in runbook
    assert "--confirm DISABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION" in runbook
    assert 'pwc-deploy staging "$qualification_sha" --refresh-environment' in runbook
    assert "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=false" in runbook
    assert "PWC_CHAT_MAX_CONCURRENCY=2" in runbook
    assert "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP=3" in runbook
    assert "maximum_sessions=32" in runbook
    assert "chat_sandbox_pool" in runbook
    assert "must return `0`" in runbook
    assert "`pwc-rollback staging` does not restore" in runbook
    assert "Production remains unchanged" in runbook
    assert "--staging-modal-rate-evidence-install-only" in runbook
    assert "--staging-modal-rate-microusd-per-second 53" in runbook
    assert "--confirm INSTALL_STAGING_MODAL_RATE_EVIDENCE" in runbook
    assert "--staging-modal-rate-evidence-remove-only" in runbook
    assert "--confirm REMOVE_STAGING_MODAL_RATE_EVIDENCE" in runbook
