#!/usr/bin/env python3
"""Create the neutral host layout without activating either environment."""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
from pathlib import Path

APP_ROOT = Path("/srv/paperswithcode")
STATE_ROOT = Path("/var/lib/paperswithcode")
LOG_ROOT = Path("/var/log/paperswithcode")
CONFIG_ROOT = Path("/etc/paperswithcode")
REPO = Path(__file__).resolve().parents[1]


def ensure_user(name: str) -> None:
    try:
        pwd.getpwnam(name)
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--home",
                "/nonexistent",
                "--shell",
                "/usr/sbin/nologin",
                "--user-group",
                name,
            ],
            check=True,
        )


def ensure_dir(path: Path, user: str, group: str, mode: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, pwd.getpwnam(user).pw_uid, grp.getgrnam(group).gr_gid)
    path.chmod(mode)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("run through sudo")
    for user in ("pwc-production", "pwc-staging", "pwc-cron"):
        ensure_user(user)
    for path in (
        APP_ROOT,
        APP_ROOT / "environments",
        STATE_ROOT,
        LOG_ROOT,
    ):
        ensure_dir(path, "root", "root", 0o755)
    ensure_dir(CONFIG_ROOT, "root", "root", 0o711)
    for path in (
        APP_ROOT / "releases",
        APP_ROOT / "environments" / "production",
        APP_ROOT / "environments" / "staging",
    ):
        ensure_dir(path, "root", "root", 0o755)
    for environment in ("production", "staging"):
        ensure_dir(
            STATE_ROOT / environment,
            f"pwc-{environment}",
            f"pwc-{environment}",
            0o750,
        )
        ensure_dir(
            LOG_ROOT / environment,
            f"pwc-{environment}",
            f"pwc-{environment}",
            0o750,
        )
    ensure_dir(STATE_ROOT / "shared", "root", "root", 0o755)
    ensure_dir(
        STATE_ROOT / "shared" / "thumbnails",
        "pwc-cron",
        "pwc-cron",
        0o755,
    )
    ensure_dir(LOG_ROOT / "deploy", "root", "root", 0o750)
    for path in (
        STATE_ROOT / "production" / "cron-logs",
        STATE_ROOT / "production" / "cron-locks",
    ):
        ensure_dir(path, "pwc-cron", "pwc-production", 0o750)
    ensure_dir(
        STATE_ROOT / "production" / "backups",
        "pwc-cron",
        "pwc-cron",
        0o750,
    )
    ensure_dir(
        STATE_ROOT / "production" / "hf-cache",
        "pwc-cron",
        "pwc-cron",
        0o750,
    )
    for path in (
        STATE_ROOT / "staging" / "chat-agent",
        STATE_ROOT / "staging" / "chat-recovery-spool",
        STATE_ROOT / "staging" / "cron-locks",
        STATE_ROOT / "staging" / "cron-logs",
        STATE_ROOT / "staging" / "recovery-spool",
        STATE_ROOT / "staging" / "codex-work",
    ):
        ensure_dir(path, "pwc-staging", "pwc-staging", 0o700)
    for path in (
        STATE_ROOT / "production" / "recovery-spool",
        STATE_ROOT / "production" / "chat-agent",
        STATE_ROOT / "production" / "chat-recovery-spool",
    ):
        ensure_dir(path, "pwc-production", "pwc-production", 0o700)

    repository = APP_ROOT / "repository.git"
    if not repository.exists():
        subprocess.run(
            ["git", "clone", "--mirror", str(REPO), str(repository)], check=True
        )
        origin = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(repository),
                "remote",
                "set-url",
                "origin",
                origin,
            ],
            check=True,
        )

    systemd = Path(__file__).resolve().parent / "systemd"
    for name in (
        "paperswithcode-backend@.service",
        "pwc-postgres-backup.service",
        "pwc-postgres-backup.timer",
    ):
        shutil.copy2(systemd / name, Path("/etc/systemd/system") / name)
    Path("/etc/systemd/journald.conf.d").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        systemd / "journald-paperswithcode.conf",
        "/etc/systemd/journald.conf.d/paperswithcode.conf",
    )
    shutil.copy2(
        systemd / "paperswithcode-tmpfiles.conf",
        "/etc/tmpfiles.d/paperswithcode.conf",
    )
    subprocess.run(
        ["systemd-tmpfiles", "--create", "/etc/tmpfiles.d/paperswithcode.conf"],
        check=True,
    )
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("host layout installed; no application service was activated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
