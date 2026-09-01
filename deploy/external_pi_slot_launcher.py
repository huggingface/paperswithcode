#!/usr/bin/env python3
"""Run one slot's four external Pi registrars from recorded runtimes only."""

from __future__ import annotations

import os
import sys

try:
    from deploy.external_pi_slot_lifecycle import (
        resolve_external_pi_replicas,
        supervisor_environment,
    )
    from deploy.process_fleet import run_process_fleet
    from deploy.slot_launcher import resolve_slot
except ModuleNotFoundError:
    from external_pi_slot_lifecycle import (  # type: ignore[no-redef]
        resolve_external_pi_replicas,
        supervisor_environment,
    )
    from process_fleet import run_process_fleet  # type: ignore[no-redef]
    from slot_launcher import resolve_slot  # type: ignore[no-redef]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: external_pi_slot_launcher.py staging SLOT")
    environment, slot = sys.argv[1:]
    release, python_runtime, manifest = resolve_slot(environment, slot)
    protected = dict(os.environ)
    resolved_fleet = resolve_external_pi_replicas(
        environment,
        slot,
        protected.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", ""),
    )
    if any(
        resolved.release != release or resolved.release_id != manifest["release_id"]
        for resolved in resolved_fleet
    ):
        raise ValueError("external Pi and backend slot releases disagree")
    python = python_runtime / "bin/python"
    code = run_process_fleet(
        [
            [str(python), "-m", "backend.scripts.run_external_pi_slot"]
            for _resolved in resolved_fleet
        ],
        [supervisor_environment(resolved, protected) for resolved in resolved_fleet],
        cwd=release,
    )
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
