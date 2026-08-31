#!/usr/bin/env python3
"""Bounded-concurrency wrapper around the immutable pwc-cron launcher.

Timer-driven jobs stagger their minute offsets during normal operation, but a
persistent catch-up storm (host downtime, first enablement) can make every
timer fire at once.  This wrapper admits at most PWC_CRON_THROTTLE_SLOTS jobs
at a time by holding one slot flock for the duration of the launch, so the
8 GB host is never asked to run dozens of jobs concurrently.  Per-job
exclusivity stays with the launcher's own job lock.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

PWC_CRON = "/usr/local/sbin/pwc-cron"


def acquire_slot(slot_dir: Path, slots: int, max_wait_seconds: int):
    """Block until one slot flock is held; return the open handle."""

    slot_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max_wait_seconds
    while True:
        for index in range(slots):
            handle = (slot_dir / f"slot-{index}.lock").open("w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except BlockingIOError:
                handle.close()
        if time.monotonic() >= deadline:
            return None
        time.sleep(20)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pwc-cron-throttled <job> [arguments]", file=sys.stderr)
        return 2
    slot_dir = Path(
        os.environ.get("PWC_CRON_SLOT_DIR", "/run/paperswithcode/cron-slots")
    )
    slots = int(os.environ.get("PWC_CRON_THROTTLE_SLOTS", "3"))
    max_wait = int(os.environ.get("PWC_CRON_THROTTLE_MAX_WAIT_SECONDS", "10800"))
    slot = acquire_slot(slot_dir, slots, max_wait)
    if slot is None:
        print(
            f"no cron concurrency slot became free within {max_wait}s",
            file=sys.stderr,
        )
        return 75
    with slot:
        return subprocess.run([PWC_CRON, *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
