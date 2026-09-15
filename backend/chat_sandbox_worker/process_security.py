"""Privilege setup shared by the supervisor and single-threaded command launcher."""

from __future__ import annotations

import ctypes
import os
import pwd
import resource

PR_SET_DUMPABLE = 4


def _not_dumpable() -> None:
    ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)


def _demote(user: str, *, pids_max: int | None = None):
    account = pwd.getpwnam(user)

    def apply() -> None:
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        os.umask(0o077)
        if pids_max is not None:
            resource.setrlimit(resource.RLIMIT_NPROC, (pids_max, pids_max))
        _not_dumpable()

    return apply
