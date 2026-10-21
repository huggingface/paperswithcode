"""Deployment tool bundle, installed wrappers, and release ref resolution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import deploy.cli as deploy_cli
import deploy.configure_host_env as configure_host_env
from deploy.cli import (
    parser_for,
)
from deploy.install_deploy_tools import (
    RUNTIME_CONTRACT_PATHS,
    bundle_runtime_contract,
    deployment_wrapper,
)


def test_deployment_tool_bundle_includes_chat_runtime_contract(tmp_path: Path):
    repository = Path(__file__).resolve().parents[3]
    staging = tmp_path / "staging"
    source = staging / "deploy"
    source.mkdir(parents=True)
    shutil.copy2(repository / "deploy" / "release.py", source / "release.py")
    for relative in RUNTIME_CONTRACT_PATHS:
        origin = repository / relative
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)

    bundle_runtime_contract(staging, source)

    for relative in RUNTIME_CONTRACT_PATHS:
        backend_relative = Path(relative).relative_to("backend")
        assert (source / "backend" / backend_relative).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import release; assert release.chat_runtime('staging')['enabled']",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(source)},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pwc-deploy", "{production,staging} source"),
        ("pwc-rollback", "{production,staging}"),
    ],
)
def test_installed_wrapper_preserves_command_parser(
    command: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    wrapper = deployment_wrapper(command)
    assert f"export PWC_DEPLOY_COMMAND={command}\n" in wrapper
    monkeypatch.setenv("PWC_DEPLOY_COMMAND", command)
    monkeypatch.setattr(sys, "argv", ["cli.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        deploy_cli.main()

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert f"usage: {command}" in output
    assert expected in output


def test_rollback_parser_accepts_failed_sha_fencing():
    sha = "a" * 40

    args = deploy_cli.parser_for("pwc-rollback").parse_args(
        ["staging", "--failed-sha", sha]
    )

    assert args.failed_sha == sha


def test_production_sha_resolves_from_bare_main_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source"
    origin = tmp_path / "origin.git"
    repository = tmp_path / "repository.git"
    source.mkdir()

    def git(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "--initial-branch=main", cwd=source)
    git("config", "user.name", "Deployment Test", cwd=source)
    git("config", "user.email", "deployment-test@example.invalid", cwd=source)
    (source / "README.md").write_text("test\n")
    git("add", "README.md", cwd=source)
    git("commit", "-m", "Initial commit", cwd=source)
    sha = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    git("clone", "--bare", str(source), str(origin))
    git("init", "--bare", str(repository))
    git("--git-dir", str(repository), "remote", "add", "origin", str(origin))
    git(
        "--git-dir",
        str(repository),
        "config",
        "remote.origin.fetch",
        "+refs/heads/*:refs/heads/*",
    )
    monkeypatch.setattr(deploy_cli, "REPOSITORY", repository)

    assert deploy_cli.resolve_sha(sha, "production") == sha
    assert (
        git(
            "--git-dir", str(repository), "rev-parse", "--verify", "refs/heads/main"
        ).stdout.strip()
        == sha
    )
    missing_remote_ref = subprocess.run(
        [
            "git",
            "--git-dir",
            str(repository),
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_remote_ref.returncode != 0


@pytest.mark.parametrize(
    ("program", "arguments", "handler"),
    [
        ("pwc-deploy", ["staging", "abc123"], "deploy"),
        ("pwc-rollback", ["staging"], "rollback"),
        ("pwc-cleanup", ["--confirm", "CLEAN_RELEASES"], "cleanup_command"),
        ("pwc-status", [], "status"),
    ],
)
def test_installed_deployment_command_dispatch(program, arguments, handler):
    args = parser_for(program).parse_args(arguments)
    assert args.handler.__name__ == handler


def test_deploy_parser_accepts_environment_refresh():
    args = parser_for("pwc-deploy").parse_args(
        ["staging", "abc123", "--refresh-environment"]
    )

    assert args.refresh_environment


def test_environment_config_directory_is_search_only(tmp_path: Path, monkeypatch):
    config = tmp_path / "paperswithcode" / "staging.env"
    monkeypatch.setattr(configure_host_env.os, "chown", lambda *_: None)
    monkeypatch.setattr(
        configure_host_env.grp,
        "getgrnam",
        lambda _group: type("Group", (), {"gr_gid": 123})(),
    )

    configure_host_env.write_env(config, {"KEY": "KEY=value"}, "pwc-staging")

    assert config.parent.stat().st_mode & 0o777 == 0o711
    assert config.stat().st_mode & 0o777 == 0o640
