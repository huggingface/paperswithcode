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
COMMANDS = ("pwc-deploy", "pwc-rollback", "pwc-status", "pwc-cleanup")
RUNTIME_CONTRACT_PATHS = (
    "backend/__init__.py",
    "backend/chat_sandbox_worker/__init__.py",
    "backend/chat_sandbox_worker/CLI_GUIDE.md",
    "backend/chat_sandbox_worker/contract.py",
    "backend/chat_sandbox_worker/prompt.py",
    "backend/services/__init__.py",
    "backend/services/chat_runtime_contract.py",
)


def bundle_runtime_contract(staging: Path, source: Path) -> None:
    """Vendor the backend modules imported by the installed release tooling."""
    shutil.copytree(staging / "backend", source / "backend")


def main() -> int:
    parser = argparse.ArgumentParser(prog="install-deploy-tools")
    parser.add_argument("source", help="exact commit or ref to install")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
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
            wrapper.write_text(
                "#!/bin/sh\n"
                "export PYTHONPATH=/usr/local/lib/paperswithcode-deploy\n"
                'exec /usr/bin/python3 /usr/local/lib/paperswithcode-deploy/cli.py "$@"\n'
            )
            wrapper.chmod(0o755)
        for command, module in {"pwc-nginx": "nginx_tool.py"}.items():
            wrapper = BIN_ROOT / command
            wrapper.write_text(
                "#!/bin/sh\n"
                f'exec /usr/bin/python3 /usr/local/lib/paperswithcode-deploy/{module} "$@"\n'
            )
            wrapper.chmod(0o755)
        wrapper = BIN_ROOT / "pwc-cron"
        wrapper.write_text(
            "#!/bin/sh\n"
            "exec systemd-run --quiet --wait --pipe --collect "
            "--uid=pwc-cron --gid=pwc-cron "
            "--working-directory=/srv/paperswithcode/environments/production/current "
            "--property=EnvironmentFile=/etc/paperswithcode/production.env "
            "--property=EnvironmentFile=/etc/paperswithcode/production-cron.env "
            "/usr/bin/python3 "
            '/usr/local/lib/paperswithcode-deploy/cron_launcher.py "$@"\n'
        )
        wrapper.chmod(0o755)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"installed {', '.join((*COMMANDS, 'pwc-cron', 'pwc-nginx'))} from {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
