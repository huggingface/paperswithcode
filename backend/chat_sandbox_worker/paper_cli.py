#!/usr/bin/env python3
"""Authenticated, current-turn-only client for private paper operations."""

from __future__ import annotations

import argparse
import errno
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

BROKER = "http://127.0.0.1:8765"
WORKSPACE = Path("/workspace")
EVENT_PREFIX = "@@PWC_PAPER@@"
MAX_RESPONSE = 3 * 1024 * 1024
_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)


def _command(operation: str, **values: object) -> dict:
    payload = {"operation": operation, **values}
    request = urllib.request.Request(
        f"{BROKER}/paper",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            data = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(8 * 1024).decode(errors="replace")
        raise RuntimeError(detail or f"Paper request failed ({error.code})") from None
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("Paper response exceeded its bound")
    result = json.loads(data)
    if not isinstance(result, dict) or not isinstance(result.get("paper"), dict):
        raise RuntimeError("Invalid paper response")
    return result


def _require_real_directory(path: Path, label: str) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"{label} must not be a symlink")
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"{label} must be a directory")


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"{label} must not contain symlinks")


def _workspace_root() -> Path:
    _require_real_directory(WORKSPACE, "Paper workspace")
    return WORKSPACE.resolve(strict=True)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_directory(path: Path, label: str) -> int:
    try:
        descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RuntimeError(f"{label} must not be a symlink") from None
        raise
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise RuntimeError(f"{label} must be a directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _lstat_at(directory_fd: int, name: str) -> os.stat_result:
    return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)


def _open_child_directory(
    directory_fd: int, name: str, label: str, *, create: bool
) -> int:
    try:
        expected = _lstat_at(directory_fd, name)
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(name, mode=0o700, dir_fd=directory_fd)
        expected = _lstat_at(directory_fd, name)
    if stat.S_ISLNK(expected.st_mode):
        raise RuntimeError(f"{label} must not contain symlinks")
    if not stat.S_ISDIR(expected.st_mode):
        raise RuntimeError(f"{label} must be a directory")
    try:
        descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RuntimeError(f"{label} must not contain symlinks") from None
        raise
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or not _same_file(expected, opened):
            raise RuntimeError(f"{label} changed while opening")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_workspace_directory(workspace: Path, directory: Path, *, create: bool) -> int:
    if not directory.is_relative_to(workspace):
        raise RuntimeError("Paper directory must be below /workspace")
    descriptor = _open_directory(workspace, "Paper workspace")
    try:
        for part in directory.relative_to(workspace).parts:
            child = _open_child_directory(
                descriptor, part, "Paper directory", create=create
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _paper_directory(directory: Path, *, create: bool) -> tuple[Path, Path]:
    workspace = _workspace_root()
    requested = directory if directory.is_absolute() else Path.cwd() / directory
    resolved = requested.resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise RuntimeError("Paper directory must be below /workspace")
    _reject_symlink_components(requested, "Paper directory")
    descriptor = _open_workspace_directory(workspace, resolved, create=create)
    os.close(descriptor)
    if resolved.resolve(strict=True) != resolved:
        raise RuntimeError("Paper directory must not contain symlinks")
    return workspace, resolved


def _open_source_file(directory_fd: int, name: str, expected: os.stat_result) -> int:
    if stat.S_ISLNK(expected.st_mode):
        raise RuntimeError("Paper source contains a symlink")
    if not stat.S_ISREG(expected.st_mode):
        raise RuntimeError("Paper source contains a non-regular entry")
    if expected.st_nlink != 1:
        raise RuntimeError("Paper source contains a hard link")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RuntimeError("Paper source contains a symlink") from None
        raise RuntimeError("Paper source changed during publication") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not _same_file(opened, expected)
        ):
            raise RuntimeError("Paper source changed during publication")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_source(descriptor: int) -> str:
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


def _open_source_directory(
    directory_fd: int, name: str, expected: os.stat_result
) -> int:
    if stat.S_ISLNK(expected.st_mode):
        raise RuntimeError("Paper source contains a symlink")
    if not stat.S_ISDIR(expected.st_mode):
        raise RuntimeError("Paper source changed during publication")
    try:
        descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RuntimeError("Paper source contains a symlink") from None
        raise RuntimeError("Paper source changed during publication") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or not _same_file(expected, opened):
            raise RuntimeError("Paper source changed during publication")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _source_entries(directory_fd: int) -> list[tuple[str, os.stat_result]]:
    with os.scandir(directory_fd) as entries:
        return sorted(
            ((entry.name, entry.stat(follow_symlinks=False)) for entry in entries),
            key=lambda entry: entry[0],
        )


def _paper_directory_still_matches(
    workspace: Path, directory: Path, expected: os.stat_result
) -> None:
    try:
        descriptor = _open_workspace_directory(workspace, directory, create=False)
    except (OSError, RuntimeError) as error:
        raise RuntimeError("Paper directory changed during publication") from error
    try:
        if not _same_file(expected, os.fstat(descriptor)):
            raise RuntimeError("Paper directory changed during publication")
    finally:
        os.close(descriptor)


def _paper_source_files(directory: Path, workspace: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []

    def collect(current_fd: int, relative: tuple[str, ...]) -> None:
        for name, info in _source_entries(current_fd):
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError("Paper source contains a symlink")
            if stat.S_ISDIR(info.st_mode):
                child_fd = _open_source_directory(current_fd, name, info)
                try:
                    collect(child_fd, (*relative, name))
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    raise RuntimeError("Paper source contains a hard link")
                if PurePosixPath(name).suffix.lower() in {".tex", ".bib"}:
                    source_fd = _open_source_file(current_fd, name, info)
                    try:
                        content = _read_source(source_fd)
                    finally:
                        os.close(source_fd)
                    files.append(
                        {
                            "path": PurePosixPath(*relative, name).as_posix(),
                            "content": content,
                        }
                    )
            else:
                raise RuntimeError("Paper source contains a non-regular entry")

    directory_fd = _open_workspace_directory(workspace, directory, create=False)
    try:
        expected_directory = os.fstat(directory_fd)
        collect(directory_fd, ())
        _paper_directory_still_matches(workspace, directory, expected_directory)
        return files
    finally:
        os.close(directory_fd)


def _repair_path(directory: Path, workspace: Path, source_path: str) -> Path:
    relative = PurePosixPath(source_path)
    if (
        not source_path
        or relative.is_absolute()
        or "\\" in source_path
        or any(part in {"", ".", ".."} for part in source_path.split("/"))
    ):
        raise RuntimeError("Invalid paper repair path")
    requested = directory.joinpath(*relative.parts)
    resolved = requested.resolve(strict=False)
    if not (resolved.is_relative_to(directory) and resolved.is_relative_to(workspace)):
        raise RuntimeError("Invalid paper repair path")
    _reject_symlink_components(requested, "Paper repair path")
    return resolved


def _validate_repair_destination(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        info = _lstat_at(directory_fd, name)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError("Paper repair path must not be a symlink")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RuntimeError("Paper repair path must be a regular file")
    return info


def _open_repair_destination(
    directory_fd: int, name: str
) -> tuple[int, os.stat_result]:
    expected = _validate_repair_destination(directory_fd, name)
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    if expected is None:
        flags |= os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(
            name,
            flags,
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise RuntimeError("Paper repair path must not be a symlink") from None
        raise RuntimeError("Paper repair path changed while opening") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (expected is not None and not _same_file(expected, opened))
        ):
            raise RuntimeError("Paper repair path changed while opening")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def _repair_destination_still_matches(
    directory_fd: int, name: str, expected: os.stat_result
) -> None:
    try:
        current = _lstat_at(directory_fd, name)
    except FileNotFoundError:
        raise RuntimeError("Paper repair path changed while writing") from None
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or not _same_file(expected, current)
    ):
        raise RuntimeError("Paper repair path changed while writing")


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise RuntimeError("Paper repair source could not be written")
        remaining = remaining[written:]


def _write_repair_source(
    workspace: Path, directory: Path, path: Path, content: str
) -> None:
    relative = path.relative_to(directory)
    if not relative.parts:
        raise RuntimeError("Invalid paper repair path")
    directory_fd = _open_workspace_directory(workspace, directory, create=True)
    descriptors = [directory_fd]
    source_fd = -1
    try:
        parent_fd = directory_fd
        for part in relative.parts[:-1]:
            parent_fd = _open_child_directory(
                parent_fd, part, "Paper repair path", create=True
            )
            descriptors.append(parent_fd)
        name = relative.parts[-1]
        data = content.encode("utf-8")
        source_fd, expected = _open_repair_destination(parent_fd, name)
        os.ftruncate(source_fd, 0)
        _write_all(source_fd, data)
        os.fsync(source_fd)
        _repair_destination_still_matches(parent_fd, name, expected)
    finally:
        if source_fd != -1:
            os.close(source_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _write_context(directory: Path, operation: str) -> int:
    workspace, directory = _paper_directory(directory, create=True)
    result = _command(operation)
    files = result.get("files")
    if not isinstance(files, list):
        raise RuntimeError("Invalid paper repair context")
    for file in files:
        if (
            not isinstance(file, dict)
            or not isinstance(file.get("path"), str)
            or not isinstance(file.get("content"), str)
        ):
            raise RuntimeError("Invalid paper repair source")
        path = _repair_path(directory, workspace, file["path"])
        _write_repair_source(workspace, directory, path, file["content"])
    print(
        "Checked out the failed paper source for repair."
        if operation == "repair-context"
        else "Checked out the current paper source for editing."
    )
    return 0


def _repair(directory: Path, parent_version_id: str, artifact_id: str) -> int:
    return _publish("repair", directory, parent_version_id, artifact_id)


def _draft(directory: Path, parent_version_id: str, artifact_id: str) -> int:
    """Publish the worker-authored first complete draft for this turn only."""
    return _publish("draft", directory, parent_version_id, artifact_id)


def _publish(
    operation: str, directory: Path, parent_version_id: str, artifact_id: str
) -> int:
    workspace, directory = _paper_directory(directory, create=False)
    files = _paper_source_files(directory, workspace)
    result = _command(
        operation,
        artifact_id=artifact_id,
        expected_parent_version_id=parent_version_id,
        files=files,
    )
    activated = result.get("activated")
    if not isinstance(activated, bool):
        raise RuntimeError("Invalid paper publication response")
    receipt = {**result, "operation": operation, "activated": activated}
    print(EVENT_PREFIX + json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-paper")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--title", required=True)
    commands.add_parser("begin-edit")
    for name in ("edit-context", "repair-context"):
        checkout = commands.add_parser(name)
        checkout.add_argument("--directory", required=True)
    repair = commands.add_parser("repair")
    repair.add_argument("--directory", required=True)
    repair.add_argument("--artifact-id", required=True)
    repair.add_argument("--expected-parent-version-id", required=True)
    draft = commands.add_parser("draft")
    draft.add_argument("--directory", required=True)
    draft.add_argument("--artifact-id", required=True)
    draft.add_argument("--expected-parent-version-id", required=True)
    args = parser.parse_args()
    try:
        if args.command in {"edit-context", "repair-context"}:
            return _write_context(Path(args.directory), args.command)
        if args.command == "repair":
            return _repair(
                Path(args.directory), args.expected_parent_version_id, args.artifact_id
            )
        if args.command == "draft":
            return _draft(
                Path(args.directory), args.expected_parent_version_id, args.artifact_id
            )
        result = _command(args.command, title=getattr(args, "title", None))
        print(
            EVENT_PREFIX + json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        )
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
