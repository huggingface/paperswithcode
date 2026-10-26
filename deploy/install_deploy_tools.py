#!/usr/bin/env python3
"""Install the deployment CLI from one committed source revision."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

INSTALL_ROOT = Path("/usr/local/lib/paperswithcode-deploy")
BIN_ROOT = Path("/usr/local/sbin")
SYSTEMD_ROOT = Path("/etc/systemd/system")
SUDOERS_PATH = Path("/etc/sudoers.d/paperswithcode-autonomous-operations")
PRODUCTION_ENV_PATH = Path("/etc/paperswithcode/production.env")
PRODUCTION_CRON_ENV_PATH = Path("/etc/paperswithcode/production-cron.env")
SUBMISSION_REVIEW_SCHEDULE_STATE_PATH = Path(
    "/var/lib/paperswithcode/production/cron-logs/submission-review-schedule.json"
)
# pwc-deploy runs release build steps as this account (deploy/build_sandbox.py).
BUILD_USER = "pwc-build"
COMMANDS = (
    "pwc-deploy",
    "pwc-rollback",
    "pwc-status",
    "pwc-cleanup",
    "pwc-reap",
)
RUNTIME_CONTRACT_PATHS = (
    "backend/__init__.py",
    "backend/chat_execution_policy.py",
    "backend/chat_sandbox_worker/__init__.py",
    "backend/chat_sandbox_worker/PWC_CLI_SKILL.md",
    "backend/chat_sandbox_worker/HF_CLI_SKILL.md",
    "backend/chat_sandbox_worker/S2_CLI_SKILL.md",
    "backend/chat_sandbox_worker/METHOD_CATALOG.md",
    "backend/chat_sandbox_worker/PAPER_AUTHORING_PROMPT.md",
    "backend/chat_sandbox_worker/TASK_CATALOG.md",
    "backend/chat_sandbox_worker/PAPER_AUTHORING_PROMPT.md",
    "backend/chat_sandbox_worker/contract.py",
    "backend/operator_profile.py",
    "config/operator.toml",
    "backend/chat_sandbox_worker/prompt.py",
    "backend/services/__init__.py",
    "backend/services/chat_runtime_contract.py",
)


def bundle_runtime_contract(staging: Path, source: Path) -> None:
    """Vendor the backend modules imported by the installed release tooling."""
    shutil.copytree(staging / "backend", source / "backend")
    # backend/operator_profile.py reads ../config/operator.toml.
    shutil.copytree(staging / "config", source / "config")


def deployment_wrapper(command: str) -> str:
    return (
        "#!/bin/sh\n"
        "export PYTHONPATH=/usr/local/lib/paperswithcode-deploy\n"
        f"export PWC_DEPLOY_COMMAND={command}\n"
        'exec /usr/bin/python3 /usr/local/lib/paperswithcode-deploy/cli.py "$@"\n'
    )


def cron_throttle_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "exec /usr/bin/python3 "
        '/usr/local/lib/paperswithcode-deploy/cron_throttle.py "$@"\n'
    )


def cron_wrapper() -> str:
    common = (
        "systemd-run --quiet --wait --pipe --collect "
        "--working-directory=/srv/paperswithcode/environments/production/current "
    )
    production_environment = (
        "--property=EnvironmentFile=/etc/paperswithcode/production.env "
        "--property=EnvironmentFile=/etc/paperswithcode/production-cron.env "
    )
    trending_environment = (
        "--property=EnvironmentFile=/etc/paperswithcode/trending-cron.env "
    )
    launcher = (
        '/usr/bin/python3 /usr/local/lib/paperswithcode-deploy/cron_launcher.py "$@"\n'
    )
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "monitor_chat_operational_alerts" ]; then\n'
        f"  exec {common}--uid=pwc-cron --gid=pwc-cron "
        f"{production_environment}"
        f"--property=SupplementaryGroups=systemd-journal {launcher}"
        "fi\n"
        'case "$1" in\n'
        "  calculate_trending_scores|calculate_paper_trending_scores)\n"
        f"    exec {common}--uid=pwc-cron-trending --gid=pwc-cron-trending "
        f"{trending_environment}"
        f"{launcher}"
        "    ;;\n"
        "esac\n"
        f"exec {common}--uid=pwc-cron --gid=pwc-cron "
        f"{production_environment}{launcher}"
    )


def submission_review_timer_action(
    *,
    review_enabled: bool,
    jobs_enabled: bool,
    primary_alert_url: str,
    fallback_alert_url: str,
) -> list[str]:
    alert_configured = bool(
        primary_alert_url
        and fallback_alert_url
        and primary_alert_url != fallback_alert_url
    )
    action = (
        "enable" if review_enabled and jobs_enabled and alert_configured else "disable"
    )
    return ["systemctl", action, "--now", "submission-review.timer"]


def _environment_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return values
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def reconcile_submission_review_timer(
    environment_path: Path = PRODUCTION_ENV_PATH,
    cron_environment_path: Path = PRODUCTION_CRON_ENV_PATH,
    state_path: Path = SUBMISSION_REVIEW_SCHEDULE_STATE_PATH,
) -> None:
    values = _environment_values(environment_path)
    values.update(_environment_values(cron_environment_path))

    def enabled(name: str) -> bool:
        return values.get(name, "").casefold() in {"1", "true", "yes", "on"}

    action = submission_review_timer_action(
        review_enabled=enabled("PWC_AUTONOMOUS_SUBMISSION_ENABLED"),
        jobs_enabled=enabled("PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED"),
        primary_alert_url=values.get("PWC_AUTONOMOUS_ALERT_SLACK_WEBHOOK_URL", ""),
        fallback_alert_url=values.get("PWC_AUTONOMOUS_ALERT_FALLBACK_WEBHOOK_URL", ""),
    )
    subprocess.run(action, check=True)
    schedule_enabled = action[1] == "enable"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{state_path.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {
                "enabled": schedule_enabled,
                "reason": (
                    "complete configuration"
                    if schedule_enabled
                    else "incomplete or unsafe configuration"
                ),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o644)
    os.replace(temporary, state_path)


def autonomous_check_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "exec /usr/bin/sudo -n /usr/bin/python3 "
        '/usr/local/lib/paperswithcode-deploy/autonomous_check_runner.py "$@"\n'
    )


def autonomous_release_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "exec /usr/bin/sudo -n /usr/bin/python3 "
        '/usr/local/lib/paperswithcode-deploy/autonomous_release_bridge.py "$@"\n'
    )


def autonomous_source_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "exec /usr/bin/sudo -n /usr/bin/python3 "
        '/usr/local/lib/paperswithcode-deploy/autonomous_source_bridge.py "$@"\n'
    )


def autonomous_cron_retry_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "exec /usr/bin/sudo -n /usr/bin/python3 "
        "/usr/local/lib/paperswithcode-deploy/autonomous_cron_retry_bridge.py "
        '"$@"\n'
    )


def autonomous_sudoers() -> str:
    root = "/usr/local/lib/paperswithcode-deploy"
    return (
        "pwc-cron ALL=(root) NOPASSWD: "
        f"/usr/bin/python3 {root}/autonomous_check_runner.py *\n"
        "pwc-cron ALL=(root) NOPASSWD: "
        f"/usr/bin/python3 {root}/autonomous_release_bridge.py *\n"
        "pwc-cron ALL=(root) NOPASSWD: "
        f"/usr/bin/python3 {root}/autonomous_source_bridge.py *\n"
        "pwc-cron ALL=(root) NOPASSWD: "
        f"/usr/bin/python3 {root}/autonomous_cron_retry_bridge.py *\n"
    )


def autonomous_release_broker_check() -> str:
    return """
DO $$
BEGIN
    IF to_regclass('public.autonomous_release_consumption') IS NULL THEN
        RAISE EXCEPTION 'autonomous release broker migration is not applied';
    END IF;
    IF (
        SELECT tableowner <> 'postgres'
          FROM pg_tables
         WHERE schemaname = 'public'
           AND tablename = 'autonomous_release_consumption'
    ) THEN
        RAISE EXCEPTION 'autonomous release broker table is not root-owned';
    END IF;
    IF has_table_privilege(
        'paperswithcode_user',
        'public.autonomous_release_consumption',
        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
    ) OR has_table_privilege(
        'pwc_staging',
        'public.autonomous_release_consumption',
        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
    ) THEN
        RAISE EXCEPTION 'application roles can access release broker state';
    END IF;
END $$;
""".strip()


def verify_autonomous_release_broker_schema() -> None:
    subprocess.run(
        [
            "/usr/sbin/runuser",
            "-u",
            "postgres",
            "--",
            "/usr/bin/psql",
            "--dbname",
            "paperswithcode_hf",
            "--no-psqlrc",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            autonomous_release_broker_check(),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )


def install_autonomous_sudoers() -> None:
    temporary = SUDOERS_PATH.with_name(f".{SUDOERS_PATH.name}.new-{os.getpid()}")
    temporary.write_text(autonomous_sudoers())
    temporary.chmod(0o440)
    try:
        subprocess.run(["/usr/sbin/visudo", "-cf", str(temporary)], check=True)
        os.replace(temporary, SUDOERS_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_build_user() -> None:
    """Create the unprivileged account that builds releases for pwc-deploy."""

    if subprocess.run(["id", "-u", BUILD_USER], capture_output=True).returncode:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--home",
                "/nonexistent",
                "--shell",
                "/usr/sbin/nologin",
                "--user-group",
                BUILD_USER,
            ],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(prog="install-deploy-tools")
    parser.add_argument("source", help="exact commit or ref to install")
    parser.add_argument(
        "--enable-autonomous-brokers",
        action="store_true",
        help=(
            "let pwc-cron sudo the autonomous root brokers; off by default "
            "because the source broker trusts pwc-cron-writable Git metadata"
        ),
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    SUDOERS_PATH.unlink(missing_ok=True)
    ensure_build_user()
    repo = Path(__file__).resolve().parents[1]
    sha = subprocess.run(
        ["git", "rev-parse", f"{args.source}^{{commit}}"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    print(f"installing deployment tooling from {sha}")
    staging = Path(tempfile.mkdtemp(prefix="pwc-deploy-tools-", dir="/usr/local/lib"))
    try:
        archive = staging / "deploy.tar"
        with archive.open("wb") as handle:
            subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=tar",
                    sha,
                    "deploy",
                    *RUNTIME_CONTRACT_PATHS,
                ],
                cwd=repo,
                stdout=handle,
                check=True,
            )
        subprocess.run(["tar", "-xf", str(archive), "-C", str(staging)], check=True)
        source = staging / "deploy"
        bundle_runtime_contract(staging, source)
        (source / "installed.json").write_text(
            json.dumps(
                {
                    "source_sha": sha,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
        backup = INSTALL_ROOT.with_name(INSTALL_ROOT.name + ".old")
        if backup.exists():
            shutil.rmtree(backup)
        if INSTALL_ROOT.exists():
            os.replace(INSTALL_ROOT, backup)
        os.replace(source, INSTALL_ROOT)
        for command in COMMANDS:
            wrapper = BIN_ROOT / command
            wrapper.write_text(deployment_wrapper(command))
            wrapper.chmod(0o755)
        for command, module in {"pwc-nginx": "nginx_tool.py"}.items():
            wrapper = BIN_ROOT / command
            wrapper.write_text(
                "#!/bin/sh\n"
                f'exec /usr/bin/python3 /usr/local/lib/paperswithcode-deploy/{module} "$@"\n'
            )
            wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-autonomous-check"
        wrapper.write_text(autonomous_check_wrapper())
        wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-autonomous-release"
        wrapper.write_text(autonomous_release_wrapper())
        wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-autonomous-source"
        wrapper.write_text(autonomous_source_wrapper())
        wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-autonomous-cron-retry"
        wrapper.write_text(autonomous_cron_retry_wrapper())
        wrapper.chmod(0o755)
        verify_autonomous_release_broker_schema()
        if args.enable_autonomous_brokers:
            install_autonomous_sudoers()
        wrapper = BIN_ROOT / "pwc-cron"
        wrapper.write_text(cron_wrapper())
        wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-cron-throttled"
        wrapper.write_text(cron_throttle_wrapper())
        wrapper.chmod(0o755)
        for unit in (
            "paperswithcode-staging-backend@.service",
            "paperswithcode-staging-backend@.socket",
            "paperswithcode-staging-external-pi@.service",
            "paperswithcode-staging-external-pi-worker@.service",
            "paperswithcode-production-external-pi@.service",
            "paperswithcode-production-external-pi-worker@.service",
            "paperswithcode-production-backend@.service",
            "paperswithcode-production-backend@.socket",
            "paperswithcode-mcp@.service",
            "pwc-curation-thumbnails.service",
            "pwc-curation-thumbnails.timer",
            "pwc-chat-alert-monitor.service",
            "pwc-chat-alert-monitor.timer",
            "pwc-chat-executor-rendezvous.service",
            "pwc-chat-executor-rendezvous@.service",
            "pwc-chat-executor-harness-proxy.service",
            "pwc-chat-executor-harness-proxy@.service",
            "autonomous/submission-review.service",
            "autonomous/submission-review.timer",
            "autonomous/submission-review-alert.service",
            "autonomous/autonomous-cron-health.service",
            "autonomous/autonomous-cron-health.timer",
            "autonomous/autonomous-cron-audit.service",
            "autonomous/autonomous-cron-audit.timer",
        ):
            source = (
                INSTALL_ROOT / unit
                if unit.startswith("autonomous/")
                else INSTALL_ROOT / "systemd" / unit
            )
            shutil.copy2(
                source,
                SYSTEMD_ROOT / Path(unit).name,
            )
        for unit_file in sorted((INSTALL_ROOT / "systemd" / "cron").glob("pwc-cron-*")):
            shutil.copy2(unit_file, SYSTEMD_ROOT / unit_file.name)
        shutil.copy2(
            INSTALL_ROOT / "systemd" / "paperswithcode-tmpfiles.conf",
            "/etc/tmpfiles.d/paperswithcode.conf",
        )
        subprocess.run(
            ["systemd-tmpfiles", "--create", "/etc/tmpfiles.d/paperswithcode.conf"],
            check=True,
        )
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        reconcile_submission_review_timer()
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"installed {', '.join((*COMMANDS, 'pwc-cron', 'pwc-nginx'))} from {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
