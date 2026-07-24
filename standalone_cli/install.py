#!/usr/bin/env python3
"""Install one checksum-verified prebuilt pwc CLI artifact."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import stat
import tempfile
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument(
        "--release-origin",
        default="https://github.com/huggingface/pwc-cli/releases/download",
    )
    args = parser.parse_args()
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
    artifact = f"pwc-{args.version}-{system}-{machine}"
    base = f"{args.release_origin.rstrip('/')}/pwc-cli-{args.version}"
    with tempfile.TemporaryDirectory(prefix="pwc-install-") as directory:
        target = Path(directory) / artifact
        urllib.request.urlretrieve(f"{base}/{artifact}", target)
        checksum = (
            urllib.request.urlopen(f"{base}/{artifact}.sha256")
            .read()
            .decode()
            .split()[0]
        )
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise SystemExit("artifact checksum verification failed")
        destination = args.prefix / "bin" / "pwc"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        destination.chmod(
            destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
    os.execv(destination, [str(destination), "version"])


if __name__ == "__main__":
    raise SystemExit(main())
