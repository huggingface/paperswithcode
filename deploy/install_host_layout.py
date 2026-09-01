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
UV_DESTINATION = Path("/usr/local/bin/uv")
SYSTEMD_UNITS = (
    "paperswithcode-backend@.service",
    "paperswithcode-staging-backend@.service",
    "paperswithcode-staging-backend@.socket",
    "paperswithcode-staging-external-pi@.service",
    "paperswithcode-staging-external-pi-worker@.service",
    "paperswithcode-production-external-pi@.service",
    "paperswithcode-production-external-pi-worker@.service",
    "paperswithcode-production-backend@.service",
    "paperswithcode-production-backend@.socket",
    "pwc-postgres-backup.service",
    "pwc-postgres-backup.timer",
    "pwc-curation-thumbnails.service",
    "pwc-curation-thumbnails.timer",
    "pwc-chat-alert-monitor.service",
    "pwc-chat-alert-monitor.timer",
    "autonomous/submission-review.service",
    "autonomous/submission-review.timer",
    "autonomous/submission-review-alert.service",
    "autonomous/cron-health.service",
    "autonomous/cron-health.timer",
    "autonomous/cron-audit.service",
    "autonomous/cron-audit.timer",
)
EXTERNAL_PI_HOSTS = (
    "127.0.0.1 localhost chat-gateway-staging.paperswithcode.co "
    "chat-gateway.paperswithcode.co\n"
    "::1 localhost ip6-localhost ip6-loopback "
    "chat-gateway-staging.paperswithcode.co chat-gateway.paperswithcode.co\n"
)


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


def install_uv() -> None:
    """Provision the existing uv binary on root's stable deployment PATH."""

    if UV_DESTINATION.is_file() and os.access(UV_DESTINATION, os.X_OK):
        return
    candidates = [
        Path(found) if (found := shutil.which("uv")) else None,
        Path("/root/.local/bin/uv"),
        Path("/root/.cargo/bin/uv"),
        Path("/usr/bin/uv"),
    ]
    source = next(
        (
            candidate
            for candidate in candidates
            if candidate is not None
            and candidate.is_file()
            and os.access(candidate, os.X_OK)
        ),
        None,
    )
    if source is None:
        raise RuntimeError("uv is required to build immutable runtimes")
    temporary = UV_DESTINATION.with_name(f".uv.new-{os.getpid()}")
    shutil.copy2(source, temporary)
    temporary.chmod(0o755)
    os.replace(temporary, UV_DESTINATION)


def install_external_pi_hosts(path: Path) -> None:
    """Keep trusted-host gateway calls local without changing host DNS."""

    path.write_text(EXTERNAL_PI_HOSTS, encoding="utf-8")
    os.chown(path, 0, 0)
    path.chmod(0o644)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("run through sudo")
    install_uv()
    for user in (
        "pwc-production",
        "pwc-staging",
        "pwc-cron",
        "pwc-cron-trending",
        "pwc-external-pi",
    ):
        ensure_user(user)
    subprocess.run(
        ["usermod", "--groups", "", "pwc-cron-trending"],
        check=True,
    )
    if any(
        "pwc-cron-trending" in group.gr_mem
        for group in grp.getgrall()
        if group.gr_name != "pwc-cron-trending"
    ):
        raise RuntimeError("pwc-cron-trending retains a supplementary group")
    for path in (
        APP_ROOT,
        APP_ROOT / "environments",
        STATE_ROOT,
        LOG_ROOT,
    ):
        ensure_dir(path, "root", "root", 0o755)
    ensure_dir(CONFIG_ROOT, "root", "root", 0o711)
    for worker_environment in (
        CONFIG_ROOT / "external-pi-worker.env",
        CONFIG_ROOT / "external-pi-worker-production.env",
    ):
        if not worker_environment.exists():
            worker_environment.write_text("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=\n")
        os.chown(worker_environment, 0, grp.getgrnam("pwc-external-pi").gr_gid)
        worker_environment.chmod(0o640)
    install_external_pi_hosts(CONFIG_ROOT / "external-pi-hosts")
    for path in (
        APP_ROOT / "releases",
        APP_ROOT / "runtimes",
        APP_ROOT / "environments" / "production",
        APP_ROOT / "environments" / "staging",
    ):
        ensure_dir(path, "root", "root", 0o755)
    for environment in ("production", "staging"):
        slots = APP_ROOT / "environments" / environment / "slots"
        ensure_dir(slots, "root", "root", 0o755)
        for slot in ("blue", "green"):
            slot_root = slots / slot
            ensure_dir(slot_root, "root", "root", 0o755)
            socket_link = slot_root / "backend.sock"
            expected_socket = Path(f"/run/paperswithcode/{environment}-{slot}.sock")
            if socket_link.is_symlink():
                if socket_link.resolve(strict=False) != expected_socket:
                    raise RuntimeError(f"{socket_link} points to the wrong socket")
            elif socket_link.exists():
                raise RuntimeError(f"{socket_link} must be a symlink")
            else:
                socket_link.symlink_to(expected_socket)
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
    # Root publishes only content-free compiler qualification evidence here.
    # The staging service can read it but cannot replace its directory or file.
    ensure_dir(
        STATE_ROOT / "staging-compiler-qualification",
        "root",
        "pwc-staging",
        0o750,
    )
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
    for path in (
        STATE_ROOT / "production" / "trending-cron-logs",
        STATE_ROOT / "production" / "trending-cron-locks",
    ):
        ensure_dir(path, "pwc-cron-trending", "pwc-cron", 0o2770)
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
    ensure_dir(
        STATE_ROOT / "autonomous-candidates",
        "pwc-cron",
        "pwc-cron",
        0o700,
    )
    ensure_dir(
        STATE_ROOT / "autonomous-source-broker",
        "root",
        "root",
        0o700,
    )
    ensure_dir(
        STATE_ROOT / "autonomous-retry-broker",
        "root",
        "root",
        0o700,
    )
    ensure_dir(
        STATE_ROOT / "autonomous-submissions",
        "pwc-cron",
        "pwc-cron",
        0o700,
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
    for name in SYSTEMD_UNITS:
        destination = Path("/etc/systemd/system") / Path(name).name
        source = (
            systemd.parent / name if name.startswith("autonomous/") else systemd / name
        )
        shutil.copy2(source, destination)
    for unit_file in sorted((systemd / "cron").glob("pwc-cron-*")):
        shutil.copy2(unit_file, Path("/etc/systemd/system") / unit_file.name)
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
