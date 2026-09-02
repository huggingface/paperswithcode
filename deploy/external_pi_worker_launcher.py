#!/usr/bin/env python3
"""Run eight immutable external Pi Node workers without backend credentials."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

try:
    from deploy.external_pi_slot_lifecycle import (
        node_environment,
        resolve_external_pi_replicas,
    )
    from deploy.process_fleet import run_process_fleet
except ModuleNotFoundError:
    from external_pi_slot_lifecycle import (  # type: ignore[no-redef]
        node_environment,
        resolve_external_pi_replicas,
    )
    from process_fleet import run_process_fleet  # type: ignore[no-redef]


WORKER_LAUNCH_INTERVAL_SECONDS = 0.5


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: external_pi_worker_launcher.py staging SLOT")
    environment, slot = sys.argv[1:]
    protected = dict(os.environ)
    resolved_fleet = resolve_external_pi_replicas(
        environment,
        slot,
        protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""),
    )
    commands = []
    environments = []
    for resolved in resolved_fleet:
        child_env = node_environment(
            resolved,
            protected,
            instance_id=str(uuid.uuid4()),
        )
        Path(child_env["PWC_EXTERNAL_PI_STATE_ROOT"]).mkdir(mode=0o700, exist_ok=True)
        tsx_loader = resolved.runtime / "app/node_modules/tsx/dist/loader.mjs"
        commands.append(
            [
                str(resolved.node),
                "--import",
                str(tsx_loader),
                str(resolved.entry_point),
            ]
        )
        environments.append(child_env)
    code = run_process_fleet(
        commands,
        environments,
        cwd=resolved_fleet[0].release,
        launch_interval_seconds=WORKER_LAUNCH_INTERVAL_SECONDS,
    )
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
