"""Run the real native entry point in a disposable root, without host accounts."""

from __future__ import annotations

import os
import re
import signal
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def native_root(tmp_path_factory):
    binary = os.environ.get("PWC_NATIVE_LAUNCHER_TEST_BINARY")
    if not binary or os.geteuid() != 0:
        pytest.skip(
            "requires an explicitly built native binary and disposable chroot access"
        )
    root = tmp_path_factory.mktemp("native-command")
    root.chmod(0o755)
    for directory in ("bin", "etc", "tmp"):
        (root / directory).mkdir()
    (root / "tmp").chmod(0o1777)
    (root / "etc/passwd").write_text("pwc-chat:x:65534:65534::/tmp:/bin/bash\n")
    for source, destination in (
        (binary, "/bin/environment"),
        ("/bin/bash", "/bin/bash"),
    ):
        shutil.copy2(source, root / destination.lstrip("/"))
        dependencies = subprocess.check_output(["ldd", source], text=True)
        for library in re.findall(r"(/[\w/+.\-]+)", dependencies):
            target = root / library.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(library, target)
    return root


def run_command(root, *args, limit="64"):
    return subprocess.run(
        ["/usr/sbin/chroot", str(root), "/bin/environment", *args],
        env={"PATH": "/bin", "HOME": "/tmp", "PWC_CHAT_SANDBOX_PIDS_MAX": limit},
        capture_output=True,
        text=True,
        timeout=5,
        start_new_session=True,
    )


def test_native_bash_identity_limits_and_literal_command(native_root):
    result = run_command(
        native_root,
        "--exec-command",
        'printf \'%s:%s:\' "$UID" "$EUID"; umask; ulimit -u; '
        "printf '%s' 'literal $HOME'; printf private > /tmp/created; exit 7",
        limit="32",
    )
    assert result.returncode == 7, result.stderr
    assert result.stdout == "65534:65534:0077\n32\nliteral $HOME"
    created = native_root / "tmp/created"
    assert created.read_text() == "private"
    assert created.stat().st_uid == created.stat().st_gid == 65534
    assert created.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("limit", ["0", "15", "513", "-1", "bad", b"\xff"])
def test_native_invalid_limit_never_executes(native_root, limit):
    result = run_command(native_root, "--exec-command", "printf forbidden", limit=limit)
    assert result.returncode == 126
    assert not result.stdout
    assert "invalid executor process limit" in result.stderr


@pytest.mark.parametrize(
    "account",
    [
        "",
        "pwc-chat:x:0:65534::/tmp:/bin/bash\n",
        "pwc-chat:x:65534:0::/tmp:/bin/bash\n",
    ],
)
def test_native_missing_or_privileged_account_never_executes(native_root, account):
    passwd = native_root / "etc/passwd"
    original = passwd.read_text()
    try:
        passwd.write_text(account)
        result = run_command(native_root, "--exec-command", "printf forbidden")
        assert result.returncode == 126 and not result.stdout
        assert "executor account" in result.stderr
    finally:
        passwd.write_text(original)


def test_native_argument_contract(native_root):
    for args in [("--exec-command",), ("--exec-command", "true", "extra")]:
        assert run_command(native_root, *args).returncode == 2
    result = run_command(native_root, "--command-launcher-version")
    assert result.returncode == 0 and result.stdout == "1\n"


def test_native_preserves_session_and_process_group_cancellation(native_root):
    process = subprocess.Popen(
        [
            "/usr/sbin/chroot",
            str(native_root),
            "/bin/environment",
            "--exec-command",
            "printf ready; read -r value",
        ],
        env={"PATH": "/bin", "HOME": "/tmp"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        import select

        assert select.select([process.stdout], [], [], 5)[0]
        assert process.stdout.read(5) == b"ready"
        assert os.getsid(process.pid) == os.getpgid(process.pid) == process.pid
        os.killpg(process.pid, signal.SIGTERM)
        assert process.wait(timeout=5) == -signal.SIGTERM
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
