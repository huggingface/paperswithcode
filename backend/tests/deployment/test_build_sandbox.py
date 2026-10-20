"""Release build code runs as pwc-build, never as root."""

from __future__ import annotations

import os
import pwd
from pathlib import Path

from types import SimpleNamespace

import pytest

from deploy import build_sandbox

BUILD = pwd.struct_passwd(
    ("pwc-build", "x", 990, 980, "", "/nonexistent", "/usr/sbin/nologin")
)


@pytest.fixture
def as_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(build_sandbox, "enabled", lambda: True)
    monkeypatch.setattr(build_sandbox.pwd, "getpwnam", lambda name: BUILD)
    killed: list[list[str]] = []

    def pkill(command, check):
        killed.append(command)
        # pkill exits 1 once no process matched.
        return SimpleNamespace(returncode=0 if len(killed) == 1 else 1)

    monkeypatch.setattr(build_sandbox.subprocess, "run", pkill)
    owners: dict[str, tuple[int, int]] = {}
    monkeypatch.setattr(
        build_sandbox.os,
        "lchown",
        lambda path, uid, gid: owners.__setitem__(str(path), (uid, gid)),
    )
    return killed, owners


def test_command_drops_every_root_privilege(as_root):
    wrapped = build_sandbox.command(["npm", "ci"])

    assert wrapped == [
        "/usr/bin/setpriv",
        "--reuid=990",
        "--regid=980",
        "--clear-groups",
        "--no-new-privs",
        "--inh-caps=-all",
        "--bounding-set=-all",
        "--",
        "npm",
        "ci",
    ]


def test_lend_and_reclaim_never_follow_symlinks(tmp_path: Path, as_root):
    killed, owners = as_root
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}")
    (tmp_path / "frontend" / "inside").symlink_to("package.json")

    build_sandbox.lend(tmp_path)
    assert set(owners.values()) == {(990, 980)}
    assert str(tmp_path / "frontend" / "inside") in owners

    build_sandbox.reclaim(tmp_path)
    # pkill repeats until no build process is left.
    assert killed == [["/usr/bin/pkill", "--signal", "KILL", "-u", "pwc-build"]] * 2
    assert set(owners.values()) == {(0, 0)}


@pytest.mark.parametrize(
    "link, target",
    [
        ("release.json", "/etc/shadow"),
        ("frontend/dist", "/etc"),
        ("bin/python", "/etc/passwd"),
        ("runtime.json", "/usr/bin/python3"),
    ],
)
def test_reclaim_refuses_symlinks_planted_outside_the_tree(
    tmp_path: Path, as_root, link: str, target: str
):
    planted = tmp_path / link
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.symlink_to(target)

    with pytest.raises(RuntimeError, match="symlink outside its tree"):
        build_sandbox.reclaim(tmp_path, allow=build_sandbox.is_venv_python_launcher)


def test_reclaim_allows_venv_launchers_to_reach_the_system_python(tmp_path: Path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").symlink_to("/usr/bin/python3")
    (tmp_path / "lib64").symlink_to("lib")

    build_sandbox.reclaim(tmp_path, allow=build_sandbox.is_venv_python_launcher)
    with pytest.raises(RuntimeError, match="bin/python"):
        build_sandbox.reclaim(tmp_path)


def test_missing_build_user_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(build_sandbox, "enabled", lambda: True)

    def missing(name):
        raise KeyError(name)

    monkeypatch.setattr(build_sandbox.pwd, "getpwnam", missing)
    with pytest.raises(RuntimeError, match="build user 'pwc-build' is missing"):
        build_sandbox.command(["npm", "ci"])


def test_disabled_sandbox_runs_commands_unchanged(tmp_path: Path):
    # backend/tests/conftest.py disables the drop, as for unprivileged callers.
    assert build_sandbox.command(["npm", "ci"]) == ["npm", "ci"]
    build_sandbox.lend(tmp_path)
    build_sandbox.reclaim(tmp_path)
    assert tmp_path.stat().st_uid == os.geteuid()


def test_runtime_build_runs_uv_and_python_as_build_user(
    tmp_path: Path, as_root, monkeypatch: pytest.MonkeyPatch
):
    from deploy import runtime as runtime_module

    release = tmp_path / "release"
    release.mkdir()
    (release / "uv.lock").write_text("lock")
    seen: list[tuple[list[str], dict]] = []

    def build(command, *, cwd, env, check):
        seen.append((command, env))
        target = Path(env["UV_PROJECT_ENVIRONMENT"])
        (target / "bin").mkdir()
        (target / "bin" / "python").symlink_to("/usr/bin/python3")

    def version(command, **kwargs):
        seen.append((command, {}))

        class Result:
            stdout = "Python 3.12.11\n"

        return Result()

    runtime_module.prepare_runtime(
        release, tmp_path / "runtimes", runner=build, version_runner=version
    )
    (uv_command, uv_env), (python_command, _) = seen
    assert uv_command[0] == "/usr/bin/setpriv"
    assert uv_command[uv_command.index("--") + 1] == str(runtime_module.UV_BINARY)
    assert python_command[0] == "/usr/bin/setpriv"
    assert uv_env["UV_CACHE_DIR"] == uv_env["HOME"]
    assert not uv_env["HOME"].startswith("/root")
    assert not any(
        path.name.startswith(".") for path in (tmp_path / "runtimes").iterdir()
    )
