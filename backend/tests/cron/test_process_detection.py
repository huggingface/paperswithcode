"""Tests for CRON process and kernel-lock detection."""

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from backend.services.cron_health import get_lock_state, is_process_running


def _processes(*lines: str):
    return SimpleNamespace(returncode=0, stdout="\n".join(lines))


def test_process_detection_ignores_health_command_and_its_parent():
    output = _processes(
        "50 1 uv run pwc cron health backfill_method_references",
        "100 50 python -m backend.cli cron health backfill_method_references",
    )

    with (
        patch("backend.services.cron_health.os.getpid", return_value=100),
        patch("backend.services.cron_health.subprocess.run", return_value=output),
    ):
        assert not is_process_running(("backfill_method_references",))


def test_process_detection_finds_an_independent_worker():
    output = _processes(
        "50 1 uv run pwc cron health backfill_method_references",
        "100 50 python -m backend.cli cron health backfill_method_references",
        "200 1 python -m scripts.backfill.backfill_method_references --resume",
    )

    with (
        patch("backend.services.cron_health.os.getpid", return_value=100),
        patch("backend.services.cron_health.subprocess.run", return_value=output),
    ):
        assert is_process_running(("backfill_method_references",))


def test_old_unlocked_persistent_file_is_not_stale(tmp_path):
    lock = tmp_path / "persistent.lock"
    lock.touch()
    old = lock.stat().st_mtime - 7200
    os.utime(lock, (old, old))

    state = get_lock_state(str(lock), expected_runtime_minutes=10)

    assert state["probe_status"] == "unlocked"
    assert state["held"] is False
    assert state["stale"] is False
    assert state["age_minutes"] > 100


def test_actively_held_file_uses_kernel_evidence(tmp_path):
    lock = tmp_path / "active.lock"
    lock.touch()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys,time; f=open(sys.argv[1]); fcntl.flock(f, fcntl.LOCK_EX); print('ready', flush=True); time.sleep(10)",
            str(lock),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"
        state = get_lock_state(str(lock), expected_runtime_minutes=10)
        assert state["probe_status"] == "held"
        assert state["held"] is True
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_permission_denied_lock_probe_is_unknown(tmp_path):
    lock = tmp_path / "unknown.lock"
    lock.touch()
    with patch("backend.services.cron_health.os.open", side_effect=PermissionError):
        state = get_lock_state(str(lock), expected_runtime_minutes=10)
    assert state["probe_status"] == "unknown"
    assert state["held"] is None
    assert state["stale"] is False
