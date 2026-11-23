"""Run one compiler command in a bounded tmpfs workspace.

This module is launched inside a fresh user, mount, PID, and (in staging)
network namespace.  It deliberately copies only bounded compiler outputs back
to the outer process; the writable TeX workspace disappears with the namespace.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath

_CHUNK_BYTES = 64 * 1024


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--max-source-bytes", type=int, required=True)
    parser.add_argument("--max-pdf-bytes", type=int, required=True)
    parser.add_argument("--max-log-bytes", type=int, required=True)
    parser.add_argument("--workspace-limit-bytes", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command or args.command[0] != "--":
        parser.error("a compiler command is required after --")
    args.command = args.command[1:]
    if not args.command:
        parser.error("a compiler command is required after --")
    if (
        min(
            args.max_source_bytes,
            args.max_pdf_bytes,
            args.max_log_bytes,
            args.workspace_limit_bytes,
        )
        < 1
    ):
        parser.error("workspace limits must be positive")
    return args


def _regular_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("Compiler workspace path is invalid")


def _copy_source(source_root: Path, workspace_root: Path, maximum: int) -> None:
    """Copy only regular, bounded files extracted by the trusted parent."""
    _regular_directory(source_root)
    excluded = {workspace_root.name, ".results"}
    copied = 0
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        if relative.parts[0] in excluded:
            continue
        destination = workspace_root / relative
        if source.is_symlink():
            raise RuntimeError("Compiler source changed during workspace setup")
        if source.is_dir():
            destination.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue
        if not source.is_file():
            raise RuntimeError("Compiler source contains a non-regular file")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            while chunk := input_file.read(_CHUNK_BYTES):
                copied += len(chunk)
                if copied > maximum:
                    raise RuntimeError("Compiler source exceeds its bound")
                output_file.write(chunk)


def _copy_tail(source: Path, destination: Path, maximum: int) -> None:
    if not source.is_file() or source.is_symlink():
        return
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with source.open("rb") as input_file, temporary.open("xb") as output_file:
        input_file.seek(0, os.SEEK_END)
        input_file.seek(max(0, input_file.tell() - maximum))
        shutil.copyfileobj(input_file, output_file, length=_CHUNK_BYTES)
    os.replace(temporary, destination)


def _copy_pdf(source: Path, destination: Path, maximum: int) -> None:
    if not source.is_file() or source.is_symlink():
        return
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    remaining = maximum + 1
    with source.open("rb") as input_file, temporary.open("xb") as output_file:
        while remaining:
            chunk = input_file.read(min(_CHUNK_BYTES, remaining))
            if not chunk:
                break
            output_file.write(chunk)
            remaining -= len(chunk)
    os.replace(temporary, destination)


def _compiler_environment(workspace_root: Path) -> dict[str, str]:
    home = workspace_root / ".home"
    home.mkdir(mode=0o700)
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": "/opt/texlive/bin:/usr/local/bin:/usr/bin:/bin",
        "TEXMFOUTPUT": str(workspace_root),
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
    }


def _mount_tmpfs(workspace_root: Path, limit: int) -> None:
    _regular_directory(workspace_root)
    subprocess.run(
        [
            "mount",
            "-t",
            "tmpfs",
            "-o",
            f"size={limit},mode=0700,nosuid,nodev,noexec",
            "tmpfs",
            str(workspace_root),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    args = _parse_args()
    source_root = args.source_root.resolve(strict=True)
    workspace_root = args.workspace_root.resolve(strict=True)
    result_root = args.result_root.resolve(strict=True)
    _regular_directory(result_root)
    _mount_tmpfs(workspace_root, args.workspace_limit_bytes)
    try:
        _copy_source(source_root, workspace_root, args.max_source_bytes)
        log_path = workspace_root / "compiler.log"
        with log_path.open("xb") as log:
            completed = subprocess.run(
                args.command,
                cwd=workspace_root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=_compiler_environment(workspace_root),
                check=False,
            )
        _copy_tail(log_path, result_root / "compiler.log", args.max_log_bytes)
        _copy_pdf(
            workspace_root / PurePosixPath(args.entrypoint).with_suffix(".pdf"),
            result_root / "output.pdf",
            args.max_pdf_bytes,
        )
        return completed.returncode
    finally:
        subprocess.run(
            ["umount", str(workspace_root)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    raise SystemExit(main())
