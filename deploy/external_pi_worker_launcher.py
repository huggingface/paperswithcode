#!/usr/bin/env python3
"""Exec one immutable external Pi Node worker without backend credentials."""

from __future__ import annotations

import os
import sys
import uuid

try:
    from deploy.external_pi_slot_lifecycle import (
        node_environment,
        resolve_external_pi_slot,
    )
except ModuleNotFoundError:
    from external_pi_slot_lifecycle import (  # type: ignore[no-redef]
        node_environment,
        resolve_external_pi_slot,
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: external_pi_worker_launcher.py staging SLOT")
    environment, slot = sys.argv[1:]
    resolved = resolve_external_pi_slot(environment, slot)
    child_env = node_environment(
        resolved,
        dict(os.environ),
        instance_id=str(uuid.uuid4()),
    )
    os.chdir(resolved.release)
    tsx_loader = resolved.runtime / "app/node_modules/tsx/dist/loader.mjs"
    os.execve(
        str(resolved.node),
        [
            str(resolved.node),
            "--import",
            str(tsx_loader),
            str(resolved.entry_point),
        ],
        child_env,
    )


if __name__ == "__main__":
    main()
