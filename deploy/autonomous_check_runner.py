#!/usr/bin/env python3
"""Run closed autonomous repair checks without host secrets or networking."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import selectors
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath


DEFAULT_ROOT = Path("/var/lib/paperswithcode/autonomous-candidates")
RUNTIMES = Path("/srv/paperswithcode/runtimes")
PYTHON_RUNTIME = Path("/srv/paperswithcode/python-runtime")
BWRAP = Path("/usr/bin/bwrap")
MAX_OUTPUT_BYTES = 60_000
MAX_RUNTIME_SECONDS = 1800


class CheckRunnerError(RuntimeError):
    pass


def _relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
    )


def _sandbox_command(
    worktree: Path,
    executable: Path,
    args: list[str],
    *,
    runtime: Path,
) -> list[str]:
    user = pwd.getpwnam("pwc-cron")
    group = grp.getgrnam("pwc-cron")
    return [
        str(BWRAP),
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--uid",
        str(user.pw_uid),
        "--gid",
        str(group.gr_gid),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--dir",
        "/srv",
        "--dir",
        "/srv/paperswithcode",
        "--ro-bind",
        str(runtime),
        str(runtime),
        "--ro-bind",
        str(PYTHON_RUNTIME),
        str(PYTHON_RUNTIME),
        "--bind",
        "/tmp",
        "/tmp",
        "--ro-bind",
        str(worktree),
        "/workspace",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        f"{runtime}/bin:/usr/bin:/bin",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "DATABASE_URL",
        "sqlite+pysqlite:///:memory:",
        "--chdir",
        "/workspace",
        "--",
        str(executable),
        *args,
    ]


def _resource_limited_command(command: list[str], unit: str) -> list[str]:
    return [
        "/usr/bin/systemd-run",
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        "--service-type=exec",
        f"--unit={unit}",
        "--property=NoNewPrivileges=yes",
        "--property=TasksMax=64",
        "--property=MemoryMax=1073741824",
        "--property=MemorySwapMax=0",
        "--property=CPUQuota=200%",
        "--property=RuntimeMaxSec=1800",
        "--property=LimitFSIZE=67108864",
        "--property=TemporaryFileSystem=/tmp:size=64M",
        "--",
        *command,
    ]


def _stop_unit(unit: str | None) -> None:
    if unit is not None:
        subprocess.run(
            [
                "/usr/bin/systemctl",
                "kill",
                "--signal=SIGKILL",
                "--kill-whom=all",
                f"{unit}.service",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        )


def _run_bounded(command: list[str], *, unit: str | None) -> None:
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS + 60
    output = bytearray()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, MAX_RUNTIME_SECONDS)
            events = selector.select(timeout=min(remaining, 1.0))
            if events:
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    raise CheckRunnerError(
                        "autonomous check output exceeded its hard limit"
                    )
            elif process.poll() is not None:
                break
        returncode = process.wait(timeout=5)
    finally:
        selector.close()
        _stop_unit(unit)
        if process.poll() is None:
            process.kill()
            process.wait()
    print(output.decode("utf-8", errors="replace"), end="")
    if returncode:
        raise subprocess.CalledProcessError(returncode, command)


def _immutable_runtime(worktree: Path) -> Path:
    lockfile = worktree / "uv.lock"
    if not lockfile.is_file() or lockfile.is_symlink():
        raise CheckRunnerError("candidate lockfile is missing")
    identifier = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    runtime = RUNTIMES / identifier
    try:
        manifest = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = None
    if (
        not runtime.is_dir()
        or runtime.is_symlink()
        or not isinstance(manifest, dict)
        or manifest.get("lock_sha256") != identifier
        or not (runtime / "bin/python").is_file()
        or not (runtime / "bin/pytest").is_file()
        or not (runtime / "bin/ruff").is_file()
    ):
        raise CheckRunnerError(
            "candidate immutable runtime is unavailable or incomplete"
        )
    return runtime


def run_check(
    worktree: Path,
    check: str,
    paths: list[str],
    *,
    root: Path = DEFAULT_ROOT,
    testing: bool = False,
    runtime: Path | None = None,
) -> None:
    root = root.resolve()
    resolved = worktree.resolve(strict=True)
    if (
        resolved.parent != root
        or not resolved.name.startswith("candidate-")
        or check not in {"lint", "pytest"}
        or not paths
        or any(not _relative(path) for path in paths)
        or any(
            (resolved / path).is_symlink()
            or resolved not in (resolved / path).resolve().parents
            or not (resolved / path).is_file()
            for path in paths
        )
    ):
        raise CheckRunnerError("autonomous check request is outside its closed scope")
    if testing and runtime is None:
        raise CheckRunnerError("test sandbox runtime must be explicit")
    runtime = runtime or _immutable_runtime(resolved)
    if not BWRAP.is_file() or not runtime.is_dir() or not PYTHON_RUNTIME.is_dir():
        raise CheckRunnerError("autonomous check sandbox is not installed")
    if check == "lint":
        python_paths = [path for path in paths if path.endswith(".py")]
        shell_paths = [path for path in paths if path.endswith(".sh")]
        if len(python_paths) + len(shell_paths) != len(paths):
            raise CheckRunnerError(
                "autonomous lint accepts only Python or shell source"
            )
        commands = []
        if python_paths:
            if testing:
                commands.append(
                    _sandbox_command(
                        resolved,
                        runtime / "bin/python",
                        [
                            "-c",
                            "import ast,pathlib,sys; "
                            "[ast.parse(pathlib.Path(p).read_text(), filename=p) "
                            "for p in sys.argv[1:]]",
                            *python_paths,
                        ],
                        runtime=runtime,
                    )
                )
            else:
                commands.extend(
                    (
                        _sandbox_command(
                            resolved,
                            runtime / "bin/ruff",
                            ["check", "--no-fix", *python_paths],
                            runtime=runtime,
                        ),
                        _sandbox_command(
                            resolved,
                            runtime / "bin/ruff",
                            ["format", "--check", *python_paths],
                            runtime=runtime,
                        ),
                    )
                )
        if shell_paths:
            commands.append(
                _sandbox_command(
                    resolved,
                    Path("/usr/bin/bash"),
                    ["-n", *shell_paths],
                    runtime=runtime,
                )
            )
    else:
        commands = [
            _sandbox_command(
                resolved,
                runtime / "bin/pytest",
                ["-q", *paths],
                runtime=runtime,
            )
        ]
    for command in commands:
        if testing:
            _run_bounded(command, unit=None)
            continue
        if os.geteuid() != 0:
            raise CheckRunnerError("autonomous check resource broker requires root")
        unit = f"pwc-autonomous-check-{uuid.uuid4().hex}"
        _run_bounded(_resource_limited_command(command, unit), unit=unit)


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-autonomous-check")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if len(arguments) < 2:
        parser.error("a closed check name and at least one path are required")
    try:
        run_check(args.worktree, arguments[0], arguments[1:])
    except (CheckRunnerError, OSError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
