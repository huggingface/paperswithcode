"""Privilege transitions retain their order and stop on failure."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker import process_security, supervisor


@pytest.mark.parametrize("pids_max", [None, 64])
def test_privilege_transition_order(monkeypatch, pids_max):
    calls = []
    monkeypatch.setattr(
        process_security.pwd,
        "getpwnam",
        lambda user: SimpleNamespace(pw_uid=1234, pw_gid=5678),
    )
    for name in ("setgroups", "setgid", "setuid", "umask"):
        monkeypatch.setattr(
            process_security.os,
            name,
            lambda value, name=name: calls.append((name, value)),
        )
    monkeypatch.setattr(
        process_security.resource,
        "setrlimit",
        lambda kind, value: calls.append(("rlimit", kind, value)),
    )
    monkeypatch.setattr(
        process_security.ctypes,
        "CDLL",
        lambda _: SimpleNamespace(prctl=lambda *args: calls.append(("prctl", *args))),
    )
    transition = process_security._demote("pwc-chat", pids_max=pids_max)
    assert calls == []
    transition()
    expected = [("setgroups", []), ("setgid", 5678), ("setuid", 1234), ("umask", 0o077)]
    if pids_max is not None:
        expected.append(("rlimit", process_security.resource.RLIMIT_NPROC, (64, 64)))
    expected.append(("prctl", 4, 0, 0, 0, 0))
    assert calls == expected


def test_failed_group_transition_stops_before_uid_change(monkeypatch):
    monkeypatch.setattr(
        process_security.pwd,
        "getpwnam",
        lambda user: SimpleNamespace(pw_uid=1234, pw_gid=5678),
    )

    def fail(_groups):
        raise PermissionError("cannot clear groups")

    monkeypatch.setattr(process_security.os, "setgroups", fail)
    monkeypatch.setattr(
        process_security.os, "setgid", lambda _: pytest.fail("continued after failure")
    )
    with pytest.raises(PermissionError, match="cannot clear groups"):
        process_security._demote("pwc-chat")()


def test_supervisor_preserves_existing_helpers():
    assert supervisor._demote is process_security._demote
    assert supervisor._not_dumpable is process_security._not_dumpable
    assert supervisor.PR_SET_DUMPABLE == process_security.PR_SET_DUMPABLE


def test_command_launcher_does_not_load_supervisor_dependencies():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from backend.chat_sandbox_worker import executor_command
assert 'backend.chat_sandbox_worker.supervisor' not in sys.modules
assert 'subprocess' not in sys.modules
assert 'socket' not in sys.modules
""",
        ],
        check=True,
    )
