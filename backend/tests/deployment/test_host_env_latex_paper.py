"""Guarded staging transitions for the private LaTeX paper runtime."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import deploy.configure_host_env as configure_host_env


def test_staging_private_paper_runtime_configuration_is_preserved():
    keys = {
        "PWC_CHAT_ARTIFACTS_ENABLED",
        "PWC_CHAT_POSTERLY_ENABLED",
        "PWC_CHAT_LATEX_PAPER_ENABLED",
        "PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED",
        "PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE",
        "PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID",
        "PWC_CHAT_LATEX_COMPILER_MODAL_ENVIRONMENT",
        "PWC_CHAT_LATEX_COMPILER_SIGNING_PRIVATE_KEY",
        "PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED",
        "PWC_CHAT_ARTIFACT_STORAGE_BACKEND",
        "PWC_CHAT_ARTIFACT_HF_BUCKET_ID",
    }
    lines = {key: f"{key}=value" for key in keys}

    assert keys <= configure_host_env.STAGING_RUNTIME_PASSTHROUGH_KEYS
    assert configure_host_env.staging_runtime_passthrough(lines) == lines


def _staging_latex_paper_source() -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    signing_key = base64.urlsafe_b64encode(private_key).rstrip(b"=").decode()
    values = {
        "PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID": "im-StagingLatexCompiler01",
        "PWC_CHAT_LATEX_COMPILER_MODAL_ENVIRONMENT": "pwc-latex-staging",
        "PWC_CHAT_LATEX_COMPILER_SIGNING_PRIVATE_KEY": signing_key,
    }
    return {key: f"{key}={value}" for key, value in values.items()}


_STAGING_IDENTITY = {
    "PWC_HF_TOKEN": "hf_staging_identity",
    "MODAL_TOKEN_ID": "ak-staging",
    "MODAL_TOKEN_SECRET": "as-staging",
}


def _installed_lines(**extra: str) -> dict[str, str]:
    values = configure_host_env.staging_latex_paper_install_values(
        _staging_latex_paper_source()
    )
    values.update(_STAGING_IDENTITY)
    values.update(extra)
    return {key: f"{key}={value}" for key, value in values.items()}


def test_staging_latex_paper_install_values_are_validated_and_disabled():
    values = configure_host_env.staging_latex_paper_install_values(
        _staging_latex_paper_source()
    )

    assert values["PWC_CHAT_ARTIFACTS_ENABLED"] == "true"
    assert values["PWC_CHAT_POSTERLY_ENABLED"] == "false"
    assert values["PWC_CHAT_LATEX_PAPER_ENABLED"] == "false"
    assert values["PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED"] == "false"
    assert values["PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE"] == "false"
    assert values["PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED"] == "false"
    assert values["PWC_CHAT_ARTIFACT_STORAGE_BACKEND"] == "hf_bucket"
    assert values["PWC_CHAT_ARTIFACT_HF_BUCKET_ID"] == (
        "nielsr/pwc-chat-artifacts-staging"
    )

    invalid = _staging_latex_paper_source()
    invalid["PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID"] = (
        "PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID=latest"
    )
    with pytest.raises(ValueError, match="immutable Modal image ID"):
        configure_host_env.staging_latex_paper_install_values(invalid)
    chat_environment = _staging_latex_paper_source()
    chat_environment["PWC_CHAT_LATEX_COMPILER_MODAL_ENVIRONMENT"] = (
        "PWC_CHAT_LATEX_COMPILER_MODAL_ENVIRONMENT=pwc-chat-staging"
    )
    with pytest.raises(ValueError, match="must be pwc-latex-staging"):
        configure_host_env.staging_latex_paper_install_values(chat_environment)


def test_staging_latex_paper_modes_are_coherent_and_fail_closed():
    current = _installed_lines()

    assert configure_host_env.staging_latex_paper_mode_values(
        current, mode="qualification"
    ) == {
        "PWC_CHAT_ARTIFACTS_ENABLED": "false",
        "PWC_CHAT_POSTERLY_ENABLED": "false",
        "PWC_CHAT_LATEX_PAPER_ENABLED": "false",
        "PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED": "false",
        "PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE": "true",
        "PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED": "false",
        "PWC_CHAT_ARTIFACT_STORAGE_BACKEND": "hf_bucket",
        "PWC_CHAT_ARTIFACT_HF_BUCKET_ID": "nielsr/pwc-chat-artifacts-staging",
    }
    activation = configure_host_env.staging_latex_paper_mode_values(
        current, mode="activation"
    )
    assert activation["PWC_CHAT_LATEX_PAPER_ENABLED"] == "true"
    assert activation["PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED"] == "true"
    assert activation["PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED"] == "false"
    assert (
        configure_host_env.staging_latex_paper_mode_values({}, mode="disable")[
            "PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED"
        ]
        == "false"
    )
    with pytest.raises(ValueError, match="compiler configuration"):
        configure_host_env.staging_latex_paper_mode_values({}, mode="qualification")

    for key in ("PWC_HF_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"):
        missing = _installed_lines(**{key: ""})
        with pytest.raises(ValueError, match=f"requires {key}"):
            configure_host_env.staging_latex_paper_mode_values(
                missing, mode="activation"
            )


def test_staging_latex_paper_activation_requires_external_pi_admission_off():
    current = _installed_lines(PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED="true")

    with pytest.raises(ValueError, match="external Pi admission to be off"):
        configure_host_env.staging_latex_paper_mode_values(current, mode="activation")
    # Compiler qualification and the kill switch never route chat turns.
    assert configure_host_env.staging_latex_paper_mode_values(
        current, mode="qualification"
    )["PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE"] == ("true")
    assert configure_host_env.staging_latex_paper_mode_values(current, mode="disable")[
        "PWC_CHAT_LATEX_PAPER_ENABLED"
    ] == ("false")


@pytest.mark.parametrize(
    ("argument", "confirmation", "expected_mode"),
    [
        (
            "--staging-latex-paper-qualification-enable-only",
            "ENABLE_STAGING_LATEX_PAPER_QUALIFICATION",
            "qualification",
        ),
        (
            "--staging-latex-paper-activation-enable-only",
            "ENABLE_STAGING_LATEX_PAPER",
            "activation",
        ),
        (
            "--staging-latex-paper-disable-only",
            "DISABLE_STAGING_LATEX_PAPER",
            "disable",
        ),
    ],
)
def test_staging_latex_paper_modes_only_update_protected_staging_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argument: str,
    confirmation: str,
    expected_mode: str,
):
    source = tmp_path / "source.env"
    source.write_text("IGNORED=true\n", encoding="utf-8")
    source.chmod(0o600)
    config_root = tmp_path / "config"
    config_root.mkdir()
    installed = _installed_lines()
    (config_root / "staging.env").write_text(
        "\n".join(installed.values()) + "\n", encoding="utf-8"
    )
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            argument,
            "--confirm",
            confirmation,
        ],
    )

    assert configure_host_env.main() == 0
    expected = configure_host_env.staging_latex_paper_mode_values(
        installed, mode=expected_mode
    )
    assert written["path"] == config_root / "staging.env"
    assert written["group"] == "pwc-staging"
    assert {
        key: configure_host_env.decoded_value(written["lines"][key]) for key in expected
    } == expected


def test_staging_latex_paper_install_requires_protected_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.env"
    source.write_text(
        "\n".join(_staging_latex_paper_source().values()) + "\n",
        encoding="utf-8",
    )
    source.chmod(0o644)
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
            "--staging-latex-paper-install-only",
            "--confirm",
            "INSTALL_STAGING_LATEX_PAPER",
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()
