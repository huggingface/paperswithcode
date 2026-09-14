#!/usr/bin/env python3
"""Explicit nginx lifecycle command; ordinary deploys never call this."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_ROOT = Path("/usr/local/lib/paperswithcode-deploy")
SITES = {
    "production": "paperswithcode.co",
    "staging": "staging.paperswithcode.co",
}
CONFIRMATIONS = {
    "production": "APPLY_NGINX_PRODUCTION",
    "staging": "APPLY_NGINX_STAGING",
}


def active_release_id(environment: str) -> str:
    manifest = (
        Path("/srv/paperswithcode/environments")
        / environment
        / "active"
        / "release"
        / "release.json"
    )
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        release_id = value["release_id"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"{environment} active slot has no valid release manifest"
        ) from exc
    if not isinstance(release_id, str) or not release_id:
        raise RuntimeError(f"{environment} active release ID is invalid")
    return release_id


def smoke_command(environment: str, expected_release: str) -> list[str]:
    command = [
        "/usr/bin/python3",
        str(INSTALL_ROOT / "smoke_test.py"),
        "--environment",
        environment,
        "--base-url",
        (
            "https://paperswithcode.co"
            if environment == "production"
            else "https://staging.paperswithcode.co"
        ),
        "--expected-release",
        expected_release,
        "--monitor-subset",
    ]
    if environment == "staging":
        command.extend(
            [
                "--gateway-url",
                "https://chat-gateway-staging.paperswithcode.co"
                "/api/internal/chat-gateway",
            ]
        )
    return command


def reload_renewed_certificate(environment: str) -> None:
    """Load an executor certificate without copying or changing nginx templates."""
    hostname = (
        "chat-executor.paperswithcode.co"
        if environment == "production"
        else "chat-executor-staging.paperswithcode.co"
    )
    expected = Path("/etc/letsencrypt/live") / hostname
    lineage = os.environ.get("RENEWED_LINEAGE")
    if lineage is None or Path(lineage) != expected:
        raise RuntimeError("renewal hook requires the selected executor certificate")
    release = active_release_id(environment)
    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    subprocess.run(smoke_command(environment, release), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-nginx")
    parser.add_argument("environment", choices=SITES)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--reload-renewed-certificate", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    if args.confirm != CONFIRMATIONS[args.environment]:
        parser.error(f"expected --confirm {CONFIRMATIONS[args.environment]}")
    if args.reload_renewed_certificate:
        reload_renewed_certificate(args.environment)
        return 0
    name = SITES[args.environment]
    source = INSTALL_ROOT / "nginx" / f"{name}.conf"
    target = Path("/etc/nginx/sites-available") / name
    subprocess.run(
        [
            "/usr/bin/python3",
            str(INSTALL_ROOT / "nginx_validate.py"),
            "--root",
            str(INSTALL_ROOT / "nginx"),
        ],
        check=True,
    )
    expected_release = active_release_id(args.environment)
    current = target.read_text().splitlines(keepends=True) if target.exists() else []
    candidate = source.read_text().splitlines(keepends=True)
    sys.stdout.writelines(
        difflib.unified_diff(
            current, candidate, fromfile=str(target), tofile=str(source)
        )
    )
    backup = target.with_suffix(target.suffix + ".pre-pwc-nginx")
    target_existed = target.exists()
    if target.exists():
        shutil.copy2(target, backup)
    shutil.copy2(source, target)
    enabled = Path("/etc/nginx/sites-enabled") / name
    enabled_created = False
    if not enabled.exists():
        enabled.symlink_to(target)
        enabled_created = True
    try:
        subprocess.run(["nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        subprocess.run(smoke_command(args.environment, expected_release), check=True)
    except subprocess.CalledProcessError:
        if backup.exists():
            shutil.copy2(backup, target)
        elif not target_existed:
            target.unlink(missing_ok=True)
        if enabled_created:
            enabled.unlink(missing_ok=True)
        if backup.exists() or not target_existed:
            subprocess.run(["nginx", "-t"], check=True)
            subprocess.run(["systemctl", "reload", "nginx"], check=True)
        raise
    backup.unlink(missing_ok=True)
    print(f"applied and validated nginx configuration for {args.environment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
