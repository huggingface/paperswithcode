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
import time
from collections.abc import Callable
from pathlib import Path

BUILD_USER = "pwc-build"
SETPRIV = Path("/usr/bin/setpriv")
PKILL = Path("/usr/bin/pkill")


def _identity() -> pwd.struct_passwd:
    try:
        return pwd.getpwnam(BUILD_USER)
    except KeyError as error:
        raise RuntimeError(
            f"build user {BUILD_USER!r} is missing; install deploy tools (deploy/install_deploy_tools.py) to create it"
        ) from error


def enabled() -> bool:
    """Drop privileges only when deploying as root (tests run unprivileged)."""

    return os.geteuid() == 0


def _drop_to(identity: pwd.struct_passwd, argv: list[str]) -> list[str]:
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


def command(argv: list[str]) -> list[str]:
    """Wrap ``argv`` so it runs as the build user without root's authority."""

    if not enabled():
        return list(argv)
    return _drop_to(_identity(), argv)


def command_as(user: str, argv: list[str]) -> list[str]:
    """Wrap ``argv`` to run as an existing service account, e.g. pwc-staging.

    For release code that must reach that account's own resources (its
    backend socket) and that the account already runs anyway.
    """

    if not enabled():
        return list(argv)
    return _drop_to(pwd.getpwnam(user), argv)


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    os.lchown(root, uid, gid)
    for directory, names, files in os.walk(root, followlinks=False):
        for name in (*names, *files):
            os.lchown(os.path.join(directory, name), uid, gid)


def lend(root: Path) -> None:
    """Give the build user ownership of ``root`` for the next build step.

    ``root``'s parent must stay root-owned so the build cannot replace
    ``root`` itself with a symlink.
    """

    if enabled():
        identity = _identity()
        _chown_tree(root, identity.pw_uid, identity.pw_gid)
        _make_owner_writable(root)


def _make_owner_writable(root: Path) -> None:
    # Root ignored permission bits on files it copied from the read-only
    # release (e.g. package-lock.json, which npm prune rewrites); the build
    # user does not, so give the owner the write access root had.
    for path in (root, *root.rglob("*")):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o200)


def _stop_build_processes() -> None:
    # A process forked while pkill scans can survive one pass, so repeat
    # until nothing runs as the build user.
    for _attempt in range(50):
        found = subprocess.run(
            [str(PKILL), "--signal", "KILL", "-u", BUILD_USER], check=False
        )
        if found.returncode == 1:
            return
        time.sleep(0.1)
    raise RuntimeError(f"processes owned by {BUILD_USER!r} keep running")


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _reject_escaping_symlinks(
    root: Path, allow: Callable[[Path, Path, Path], bool]
) -> None:
    """Every link must point inside the tree, both literally and when resolved.

    Checking only the final resolution would accept a link that hops through
    an outside path the build user controls (``bin/python -> /tmp/pivot ->
    /usr/bin/python3``) and could retarget later. Checking each link's own
    target keeps every hop inside the now root-owned tree.
    """

    resolved_root = root.resolve()
    for directory, names, files in os.walk(root, followlinks=False):
        for name in (*names, *files):
            path = Path(directory, name)
            if not path.is_symlink():
                continue
            literal = Path(os.path.normpath(os.path.join(directory, os.readlink(path))))
            resolved = Path(os.path.realpath(path))
            if _inside(literal, root) and _inside(resolved, resolved_root):
                continue
            if _inside(literal, root):
                literal = literal.relative_to(root)
            if allow(path.relative_to(root), literal, resolved):
                continue
            raise RuntimeError(
                f"build left a symlink outside its tree: {path.relative_to(root)}"
            )


def reclaim(
    root: Path,
    *,
    allow: Callable[[Path, Path, Path], bool] = lambda *_link: False,
) -> None:
    """Stop leftover build processes, return ``root`` to root, then vet it.

    Killing first means no build process can change the tree while root walks
    it. ``lchown`` never follows symlinks, and changing the owner clears any
    set-user-ID bits a build step left behind. Later root steps write and
    chmod paths inside the tree, so a symlink the build planted pointing out
    of it (for example ``release.json -> /etc/shadow``) is refused unless
    ``allow`` accepts the link and its literal target (both relative to
    ``root`` when inside it) and its resolved target.
    """

    if enabled():
        _identity()
        _stop_build_processes()
        _chown_tree(root, 0, 0)
    _reject_escaping_symlinks(root, allow)


def is_venv_python_launcher(link: Path, literal: Path, resolved: Path) -> bool:
    """A virtualenv's ``bin/python*`` launchers point at the host interpreter.

    The link must name ``/usr/bin/python3*`` directly (root-owned, so nothing
    can retarget it) or a sibling launcher in the same ``bin/`` directory,
    which is checked on its own. The venv may be nested (``mcp_server/.venv``).
    """

    def system_python(path: Path) -> bool:
        return path.parent == Path("/usr/bin") and path.name.startswith("python3")

    return (
        link.parent.name == "bin"
        and link.name.startswith("python")
        and system_python(resolved)
        and (system_python(literal) or literal.parent == link.parent)
    )
