"""Release, runtime, host-profile, and role-allowlist permissions."""

from __future__ import annotations

from pathlib import Path

import pytest

import deploy.cli as deploy_cli
import deploy.configure_host_env as configure_host_env
import deploy.configure_role_allowlists as configure_role_allowlists


def test_shared_runtime_is_made_service_readable(tmp_path: Path, monkeypatch):
    runtime = tmp_path / ".venv"
    package = runtime / "lib" / "package.py"
    base = tmp_path / "base-python"
    neutral_base = tmp_path / "python-runtime"
    interpreter = base / "bin" / "python3.12"
    package.parent.mkdir(parents=True)
    (runtime / "bin").mkdir()
    interpreter.parent.mkdir(parents=True)
    package.write_text("value = 1\n")
    interpreter.write_text("python")
    interpreter.chmod(0o755)
    (runtime / "bin" / "python").symlink_to(interpreter)
    (runtime / "pyvenv.cfg").write_text(f"home = {base / 'bin'}\n")
    runtime.chmod(0o700)
    package.parent.chmod(0o700)
    package.chmod(0o600)
    monkeypatch.setattr(deploy_cli, "VENV", runtime)
    monkeypatch.setattr(deploy_cli, "PYTHON_RUNTIME", neutral_base)

    deploy_cli.make_runtime_readable()

    assert runtime.stat().st_mode & 0o055 == 0o055
    assert package.parent.stat().st_mode & 0o055 == 0o055
    assert package.stat().st_mode & 0o044 == 0o044
    assert (runtime / "bin" / "python").resolve() == (
        neutral_base / "bin" / "python3.12"
    )
    assert str(neutral_base) in (runtime / "pyvenv.cfg").read_text()


def test_immutable_release_is_world_readable(tmp_path: Path):
    release = tmp_path / "release"
    package = release / "backend"
    module = package / "main.py"
    script = release / "scripts" / "job.sh"
    package.mkdir(parents=True)
    script.parent.mkdir()
    module.write_text("app = object()\n")
    script.write_text("#!/bin/sh\n")
    package.chmod(0o700)
    module.chmod(0o600)
    script.chmod(0o700)

    deploy_cli.make_release_readable(release)

    assert release.stat().st_mode & 0o555 == 0o555
    assert package.stat().st_mode & 0o555 == 0o555
    assert module.stat().st_mode & 0o444 == 0o444
    assert script.stat().st_mode & 0o555 == 0o555
    assert module.stat().st_mode & 0o222 == 0


def test_host_environment_subject_roles_are_shared_and_conflict_safe():
    production = {
        "PWC_ADMIN_HF_SUBJECTS": "PWC_ADMIN_HF_SUBJECTS=admin-sub",
        "PWC_CONTRIBUTOR_HF_SUBJECTS": ("PWC_CONTRIBUTOR_HF_SUBJECTS=one-sub,two-sub"),
    }
    staging = dict(production)
    assert configure_host_env.shared_role_values(production, staging) == {
        "PWC_ADMIN_HF_SUBJECTS": "admin-sub",
        "PWC_CONTRIBUTOR_HF_SUBJECTS": "one-sub,two-sub",
    }
    staging["PWC_ADMIN_HF_SUBJECTS"] = "PWC_ADMIN_HF_SUBJECTS=other-sub"
    with pytest.raises(ValueError, match="differs"):
        configure_host_env.shared_role_values(production, staging)


def test_host_profiles_keep_contributor_direct_edits_default_off():
    repository = Path(__file__).resolve().parents[3]
    script = (repository / "deploy/configure_host_env.py").read_text()
    assert script.count('"PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false"') == 2


def test_role_allowlist_installer_normalizes_and_rejects_usernames():
    assert (
        configure_role_allowlists.normalized_subjects(
            [" subject-b ", "subject-a", "subject-a"]
        )
        == "subject-a,subject-b"
    )
    with pytest.raises(ValueError, match="Malformed"):
        configure_role_allowlists.normalized_subjects(["not a subject"])
