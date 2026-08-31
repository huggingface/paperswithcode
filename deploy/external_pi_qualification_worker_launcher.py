#!/usr/bin/env python3
"""Exec one qualification Node worker with a fresh process identity."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))

try:
    from deploy.external_pi_qualification_lifecycle import (
        resolve_qualification_replica,
        worker_environment,
    )
except ModuleNotFoundError:
    from external_pi_qualification_lifecycle import (  # type: ignore[no-redef]
        resolve_qualification_replica,
        worker_environment,
    )


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: external_pi_qualification_worker_launcher.py "
            "staging RELEASE INDEX PORT MAXIMUM_SESSIONS"
        )
    environment, release_id, raw_index, raw_port, raw_sessions = sys.argv[1:]
    resolved = resolve_qualification_replica(
        environment, release_id, int(raw_index), int(raw_port), int(raw_sessions)
    )
    child_env = worker_environment(
        resolved, dict(os.environ), instance_id=str(uuid.uuid4())
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
