"""Guarded staging external Pi admission transitions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env
from backend.services.runtime_validation import validate_runtime
from backend.tests.deployment.harness import deployed_settings, make_bundle
from deploy.release import profile_features

_EXTERNAL_PROFILE = {
    "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "true",
    "PWC_CHAT_EXECUTOR_REMOTE_TRANSPORT_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "durable-external-pi-v1",
    "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "true",
    "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "true",
    "PWC_CHAT_REMOTE_BASH_ENABLED": "true",
    "PWC_CHAT_REMOTE_READ_ENABLED": "true",
    "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "true",
    "PWC_CHAT_BLANK_POOL_ENABLED": "false",
    "PWC_CHAT_PI_PREWARM_ENABLED": "false",
    "PWC_CHAT_MAX_CONCURRENCY": "32",
    "PWC_CHAT_USER_MAX_CONCURRENCY": "1",
    "PWC_CHAT_BLANK_POOL_MIN": "4",
    "PWC_CHAT_BLANK_POOL_MAX": "4",
    "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "32",
    "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "16",
    "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "32",
    "UNRELATED_SETTING": "keep",
}


def _lines(values: dict[str, str]) -> dict[str, str]:
    return {key: f"{key}={value}" for key, value in values.items()}


def test_disable_saves_every_changed_key_and_enable_restores_it_exactly():
    current = _lines(_EXTERNAL_PROFILE)

    values, backup = configure_host_env.staging_external_pi_disable_values(current)
    disabled = configure_host_env.assign(current, values)
    restored = configure_host_env.staging_external_pi_enable_lines(disabled, backup)

    assert values["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_EXECUTOR_REMOTE_TRANSPORT_ENABLED"] == "false"
    assert values["PWC_CHAT_SAFE_CLI_FAST_PATH_ENABLED"] == "false"
    assert values["PWC_CHAT_BLANK_POOL_ENABLED"] == "true"
    # Keys the external profile never set are removed again, not left behind.
    assert "PWC_CHAT_SAFE_CLI_FAST_PATH_ENABLED" in disabled
    assert restored == current
    # Settings outside the transition are never touched.
    assert disabled["UNRELATED_SETTING"] == "UNRELATED_SETTING=keep"
    assert "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS" not in values


def test_transitions_fail_closed():
    current = _lines(_EXTERNAL_PROFILE)
    values, backup = configure_host_env.staging_external_pi_disable_values(current)
    disabled = configure_host_env.assign(current, values)

    with pytest.raises(ValueError, match="already off"):
        configure_host_env.staging_external_pi_disable_values(disabled)
    with pytest.raises(ValueError, match="no saved staging external Pi profile"):
        configure_host_env.staging_external_pi_enable_lines(disabled, {})
    papers_on = configure_host_env.assign(
        disabled, {"PWC_CHAT_LATEX_PAPER_ENABLED": "true"}
    )
    with pytest.raises(ValueError, match="disable the staging LaTeX paper feature"):
        configure_host_env.staging_external_pi_enable_lines(papers_on, backup)
    partial = dict(backup)
    partial.pop("PWC_CHAT_REMOTE_BASH_ENABLED")
    with pytest.raises(ValueError, match="incomplete"):
        configure_host_env.staging_external_pi_enable_lines(disabled, partial)


def test_external_pi_off_profile_passes_staging_runtime_validation(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    # Staging runs every new session on Pi by default, which prewarm requires.
    settings.chat_default_agent_harness = "pi"
    settings.chat_new_session_pi_percentage = 100
    external = dict(_EXTERNAL_PROFILE)
    external.pop("UNRELATED_SETTING")
    values, _ = configure_host_env.staging_external_pi_disable_values(_lines(external))
    # Start from staging's external profile, then apply the off transition.
    for key, value in {**external, **values}.items():
        field = key.removeprefix("PWC_").lower()
        current = getattr(settings, field)
        if isinstance(current, bool):
            setattr(settings, field, value == "true")
        elif isinstance(current, int):
            setattr(settings, field, int(value))
        else:
            setattr(settings, field, value)

    assert validate_runtime(settings) == profile_features("staging")


@pytest.mark.parametrize(
    ("argument", "confirmation"),
    [
        ("--staging-external-pi-disable-only", "DISABLE_STAGING_EXTERNAL_PI"),
        ("--staging-external-pi-enable-only", "ENABLE_STAGING_EXTERNAL_PI"),
    ],
)
def test_cli_round_trip_only_touches_protected_staging_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argument: str,
    confirmation: str,
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    backup_path = config_root / "staging-external-pi-profile.env"
    current = _lines(_EXTERNAL_PROFILE)
    if argument.endswith("enable-only"):
        values, backup = configure_host_env.staging_external_pi_disable_values(current)
        backup_path.write_text("\n".join(backup.values()) + "\n", encoding="utf-8")
        current = configure_host_env.assign(current, values)
    (config_root / "staging.env").write_text(
        "\n".join(current.values()) + "\n", encoding="utf-8"
    )
    written: dict[Path, tuple[dict[str, str], str]] = {}

    def write_env(path: Path, lines: dict[str, str], group: str) -> None:
        written[path] = (lines, group)
        path.write_text("\n".join(lines.values()) + "\n", encoding="utf-8")

    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(
        configure_host_env, "STAGING_EXTERNAL_PI_PROFILE_BACKUP", backup_path
    )
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(configure_host_env, "write_env", write_env)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(config_root / "staging.env"),
            argument,
            "--confirm",
            confirmation,
        ],
    )

    assert configure_host_env.main() == 0
    staging_lines, group = written[config_root / "staging.env"]
    assert group == "pwc-staging"
    if argument.endswith("disable-only"):
        assert written[backup_path][1] == "root"
        assert configure_host_env.decoded_value(
            staging_lines["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"]
        ) == ("false")
    else:
        assert staging_lines == _lines(_EXTERNAL_PROFILE)
        assert not backup_path.exists()


def test_full_staging_rebuild_keeps_the_installed_external_pi_state():
    for profile in (
        _lines(_EXTERNAL_PROFILE),
        configure_host_env.assign(
            _lines(_EXTERNAL_PROFILE),
            configure_host_env.staging_external_pi_disable_values(
                _lines(_EXTERNAL_PROFILE)
            )[0],
        ),
    ):
        kept = configure_host_env.staging_runtime_passthrough(profile)
        for key in configure_host_env._STAGING_EXTERNAL_PI_OFF:
            if key in profile:
                assert kept[key] == profile[key], key
