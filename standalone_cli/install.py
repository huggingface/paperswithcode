#!/usr/bin/env python3
"""Install one checksum-verified prebuilt pwc CLI artifact."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import shlex
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_RELEASE_ORIGIN = "https://github.com/huggingface/pwc-cli/releases/download"
DEFAULT_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/huggingface/pwc-cli/releases/latest"
)
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class NetworkError(Exception):
    """A concise installer networking failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        help="install an explicit release version instead of the latest release",
    )
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument(
        "--release-origin",
        default=DEFAULT_RELEASE_ORIGIN,
    )
    parser.add_argument(
        "--latest-release-url",
        default=DEFAULT_LATEST_RELEASE_URL,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _open(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "pwc-cli-installer",
        },
    )
    try:
        return urllib.request.urlopen(request, timeout=30)
    except (urllib.error.URLError, TimeoutError) as error:
        reason = str(getattr(error, "reason", error)).replace("\n", " ")
        raise NetworkError(reason) from error


def _validate_version(version: str) -> str:
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"invalid release version: {version}")
    return version


def _read_response(response, maximum_bytes: int) -> bytes:
    try:
        contents = response.read(maximum_bytes + 1)
    except (OSError, http.client.HTTPException) as error:
        raise NetworkError(str(error)) from error
    if len(contents) > maximum_bytes:
        raise NetworkError("response was unexpectedly large")
    return contents


def resolve_version(explicit_version: str | None, latest_release_url: str) -> str:
    if explicit_version:
        return _validate_version(explicit_version)
    try:
        with _open(latest_release_url) as response:
            payload = json.loads(_read_response(response, 1024 * 1024))
        tag = payload["tag_name"]
    except NetworkError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise NetworkError("latest release response was invalid") from error
    prefix = "pwc-cli-"
    if not isinstance(tag, str) or not tag.startswith(prefix):
        raise NetworkError("latest release tag was invalid")
    try:
        return _validate_version(tag.removeprefix(prefix))
    except SystemExit as error:
        raise NetworkError("latest release tag was invalid") from error


def _download(url: str, destination: Path) -> None:
    with _open(url) as response, destination.open("wb") as output:
        while True:
            try:
                chunk = response.read(1024 * 1024)
            except (OSError, http.client.HTTPException) as error:
                raise NetworkError(str(error)) from error
            if not chunk:
                break
            output.write(chunk)


def _read_checksum(url: str) -> str:
    with _open(url) as response:
        contents = _read_response(response, 4096)
    try:
        checksum = contents.decode("ascii", errors="strict").split()[0]
    except (IndexError, UnicodeDecodeError) as error:
        raise SystemExit("artifact checksum file was invalid") from error
    if len(checksum) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in checksum
    ):
        raise SystemExit("artifact checksum file was invalid")
    return checksum.lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_atomically(artifact: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".pwc-install-", dir=destination.parent
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(artifact, temporary)
        temporary.chmod(
            temporary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def report_path(bin_directory: Path, path_value: str | None = None) -> None:
    path_value = os.environ.get("PATH", "") if path_value is None else path_value
    expanded_bin = bin_directory.expanduser().resolve()
    entries = {
        Path(entry).expanduser().resolve()
        for entry in path_value.split(os.pathsep)
        if entry
    }
    display = (
        "~/.local/bin"
        if expanded_bin == (Path.home() / ".local/bin").resolve()
        else str(bin_directory)
    )
    shell_path = (
        '"$HOME/.local/bin:$PATH"'
        if display == "~/.local/bin"
        else f'{shlex.quote(str(expanded_bin))}:"$PATH"'
    )
    if expanded_bin in entries:
        print(f"{display} is on PATH", flush=True)
        return
    print(f"warning: {display} is not on PATH", file=sys.stderr, flush=True)
    print(
        f"Add this to ~/.profile: export PATH={shell_path}",
        file=sys.stderr,
        flush=True,
    )


def _print_network_error(error: NetworkError) -> None:
    message = str(error).replace("\r", " ").replace("\n", " ")
    print(f"pwc installer: network error: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        version = resolve_version(args.version, args.latest_release_url)
    except NetworkError as error:
        _print_network_error(error)
        return 3

    machine = platform.machine().lower()
    system = platform.system().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    supported = {
        ("linux", "x86_64"),
        ("darwin", "x86_64"),
        ("darwin", "arm64"),
    }
    if (system, machine) not in supported:
        raise SystemExit(f"unsupported platform: {system}-{machine}")
    artifact = f"pwc-{version}-{system}-{machine}"
    base = f"{args.release_origin.rstrip('/')}/pwc-cli-{version}"
    try:
        with tempfile.TemporaryDirectory(prefix="pwc-install-") as directory:
            target = Path(directory) / artifact
            _download(f"{base}/{artifact}", target)
            checksum = _read_checksum(f"{base}/{artifact}.sha256")
            if _sha256(target) != checksum:
                raise SystemExit("artifact checksum verification failed")
            destination = args.prefix / "bin" / "pwc"
            _install_atomically(target, destination)
    except NetworkError as error:
        _print_network_error(error)
        return 3
    report_path(destination.parent)
    os.execv(destination, [str(destination), "version"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
