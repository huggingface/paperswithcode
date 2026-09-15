"""Single-threaded privilege boundary for executor command processes."""

from __future__ import annotations

import os
import sys

from backend.chat_sandbox_worker.process_security import _demote

EXECUTOR_USER = "pwc-chat"
DEFAULT_EXECUTOR_PIDS_MAX = 64


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        return 2
    _demote(
        EXECUTOR_USER,
        pids_max=int(
            os.environ.get("PWC_CHAT_SANDBOX_PIDS_MAX", str(DEFAULT_EXECUTOR_PIDS_MAX))
        ),
    )()
    os.execv("/bin/bash", ["/bin/bash", "-lc", arguments[0]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
