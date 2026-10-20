"""Run release-controlled build code as an unprivileged user, never as root.

``pwc-deploy`` runs as root, but building a release executes code chosen by
the selected revision: npm lifecycle scripts, the Vite config, release Python
modules, and sdist builds picked by ``uv.lock``. Those steps run as the
dedicated ``pwc-build`` account with a cleared environment, no supplementary
groups, no capabilities, and ``no_new_privs``. The account owns only the build
tree while a step runs; root takes the tree back before inspecting or
publishing it.
"""

from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

BUILD_USER = "pwc-build"
SETPRIV = Path("/usr/bin/setpriv")
PKILL = Path("/usr/bin/pkill")


def _identity() -> pwd.struct_passwd:
    try:
        return pwd.getpwnam(BUILD_USER)
    except KeyError as error:
        raise RuntimeError(
            f"build user {BUILD_USER!r} is missing; run deploy/install_host_layout.py"
        ) from error


def enabled() -> bool:
    """Drop privileges only when deploying as root (tests run unprivileged)."""

    return os.geteuid() == 0


def command(argv: list[str]) -> list[str]:
    """Wrap ``argv`` so it runs as the build user without root's authority."""

    if not enabled():
        return list(argv)
    identity = _identity()
    return [
        str(SETPRIV),
        f"--reuid={identity.pw_uid}",
        f"--regid={identity.pw_gid}",
        "--clear-groups",
        "--no-new-privs",
        "--inh-caps=-all",
        "--bounding-set=-all",
        "--",
        *argv,
    ]


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    os.lchown(root, uid, gid)
    for directory, names, files in os.walk(root, followlinks=False):
        for name in (*names, *files):
            os.lchown(os.path.join(directory, name), uid, gid)


def lend(root: Path) -> None:
    """Give the build user ownership of ``root`` for the next build step."""

    if enabled():
        identity = _identity()
        _chown_tree(root, identity.pw_uid, identity.pw_gid)


def reclaim(root: Path) -> None:
    """Stop leftover build processes, then return ``root`` to root ownership.

    Killing first means no build process can swap files while root walks the
    tree. ``lchown`` never follows symlinks, and changing the owner clears any
    set-user-ID bits a build step left behind.
    """

    if not enabled():
        return
    _identity()
    subprocess.run([str(PKILL), "--signal", "KILL", "-u", BUILD_USER], check=False)
    _chown_tree(root, 0, 0)
