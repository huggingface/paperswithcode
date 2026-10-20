"""Build immutable external Pi runtimes from one release's locked inputs."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import pickle
import re
import signal
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from backend.chat_sandbox_worker.contract import PI_NODE_SHA256, PI_NODE_VERSION

try:
    from deploy import build_sandbox
    from deploy.release import sha256_file
    from deploy.runtime import make_tree_readonly
except ModuleNotFoundError:
    import build_sandbox  # type: ignore[no-redef]
    from release import sha256_file  # type: ignore[no-redef]
    from runtime import make_tree_readonly  # type: ignore[no-redef]

CONTRACT = "external-pi-v1"
IDENTITY_SCHEMA = 1
RETAIN_ALL_RUNTIMES = "__retain_all_external_pi_runtimes__"
ENTRY_POINT = "app/dist/src/external_http_main.js"
WORKER_ROOT = Path("backend/chat_sandbox_worker/pi_worker")
PYTHON_BINARY = Path(os.environ.get("PWC_DEPLOY_PYTHON", "/usr/bin/python3"))
CURL_BINARY = Path(os.environ.get("PWC_DEPLOY_CURL", "/usr/bin/curl"))
NODE_ARCHIVE_URL = (
    f"https://nodejs.org/dist/v{PI_NODE_VERSION}/"
    f"node-v{PI_NODE_VERSION}-linux-x64.tar.xz"
)
BUILD_TIMEOUT_SECONDS = 300
MAX_RUNTIME_FILES = 100_000
MAX_RUNTIME_BYTES = 2 * 1024**3
MAX_NODE_ARCHIVE_BYTES = 128 * 1024**2
MIN_FREE_BYTES = MAX_RUNTIME_BYTES + MAX_NODE_ARCHIVE_BYTES + 512 * 1024**2

PROMPT_INPUTS = (
    Path("backend/__init__.py"),
    Path("backend/chat_execution_policy.py"),
    Path("backend/chat_sandbox_worker/__init__.py"),
    Path("backend/chat_sandbox_worker/render_pi_prompt_asset.py"),
    Path("backend/chat_sandbox_worker/prompt.py"),
    Path("backend/chat_sandbox_worker/PAPER_AUTHORING_PROMPT.md"),
    Path("backend/chat_sandbox_worker/PAPER_AUTHORING.md"),
    Path("backend/chat_sandbox_worker/PWC_CLI_SKILL.md"),
    Path("backend/chat_sandbox_worker/PWC_MCP_SKILL.md"),
    Path("backend/chat_sandbox_worker/HF_CLI_SKILL.md"),
    Path("backend/chat_sandbox_worker/S2_CLI_SKILL.md"),
    Path("backend/chat_sandbox_worker/TASK_CATALOG.md"),
    Path("backend/chat_sandbox_worker/METHOD_CATALOG.md"),
)


def _identity_inputs(release: Path) -> list[Path]:
    worker = release / WORKER_ROOT
    typescript_inputs = [
        path.relative_to(release)
        for tree in ("src", "test")
        for path in sorted((worker / tree).glob("**/*.ts"))
    ]
    if not typescript_inputs:
        raise ValueError("external Pi TypeScript build inputs are missing")
    paths = [
        WORKER_ROOT / "package.json",
        WORKER_ROOT / "package-lock.json",
        WORKER_ROOT / "tsconfig.json",
        *typescript_inputs,
        *PROMPT_INPUTS,
    ]
    for relative in paths:
        if not (release / relative).is_file():
            raise ValueError(f"external Pi runtime input is missing: {relative}")
    return paths


def _node_contract(release: Path) -> tuple[str, str]:
    value = json.loads((release / "release.json").read_text(encoding="utf-8"))
    runtime = value.get("chat_runtime")
    if not isinstance(runtime, dict):
        raise ValueError("release manifest has no external Pi Node contract")
    version = runtime.get("pi_node_version")
    digest = runtime.get("pi_node_sha256")
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise ValueError("release external Pi Node contract is invalid")
    return version, digest


def external_pi_runtime_id(release: Path) -> str:
    """Return a stable content identity for all external Pi build inputs."""

    node_version, node_sha256 = _node_contract(release)
    digest = hashlib.sha256()
    for label, value in (
        ("contract", CONTRACT),
        ("node_version", node_version),
        ("node_distribution_sha256", node_sha256),
    ):
        digest.update(label.encode() + b"\0" + value.encode() + b"\0")
    for relative in _identity_inputs(release):
        digest.update(relative.as_posix().encode() + b"\0")
        with (release / relative).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def external_pi_runtime_descriptor(release: Path) -> dict[str, object]:
    """Return the durable release descriptor for this identity schema."""

    return {
        "identity_schema": IDENTITY_SCHEMA,
        "runtime_id": external_pi_runtime_id(release),
        "contract": CONTRACT,
    }


def recorded_external_pi_runtime_descriptor(release: Path) -> dict | None:
    """Read an opaque packaged descriptor without today's identity rules."""
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    descriptor = manifest.get("external_pi_runtime")
    if descriptor is None:
        return None
    if (
        not isinstance(descriptor, dict)
        or set(descriptor) != {"identity_schema", "runtime_id", "contract"}
        or not isinstance(descriptor["identity_schema"], int)
        or descriptor["identity_schema"] < 1
        or not isinstance(descriptor["runtime_id"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", descriptor["runtime_id"])
        or not isinstance(descriptor["contract"], str)
        or not descriptor["contract"]
    ):
        raise ValueError("release external Pi runtime descriptor is invalid")
    return descriptor


def recorded_external_pi_runtime_id(release: Path) -> str | None:
    descriptor = recorded_external_pi_runtime_descriptor(release)
    return str(descriptor["runtime_id"]) if descriptor is not None else None


def _source_release(release: Path) -> str:
    value = json.loads((release / "release.json").read_text(encoding="utf-8"))
    source_release = value.get("release_id")
    if not isinstance(source_release, str) or not source_release:
        raise ValueError("release manifest has no release identity")
    return source_release


def _path_digest(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(b"symlink\0" + os.readlink(path).encode()).hexdigest()
    return sha256_file(path)


def _runtime_files(runtime: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    total_bytes = 0
    for path in sorted(runtime.rglob("*")):
        relative = path.relative_to(runtime).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if relative == "runtime.json":
            continue
        if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
            raise ValueError(f"external Pi runtime contains a special file: {relative}")
        if path.is_symlink():
            target = (path.parent / os.readlink(path)).resolve()
            if target != runtime.resolve() and runtime.resolve() not in target.parents:
                raise ValueError(f"external Pi runtime symlink escapes: {relative}")
            total_bytes += len(os.readlink(path).encode())
        else:
            total_bytes += metadata.st_size
        files[relative] = _path_digest(path)
        if len(files) > MAX_RUNTIME_FILES or total_bytes > MAX_RUNTIME_BYTES:
            raise ValueError("external Pi runtime exceeds its construction bounds")
    return files


def _tree_usage(root: Path) -> tuple[int, int]:
    inode_count = 1
    total_bytes = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    inode_count += 1
                    total_bytes += metadata.st_size
                    if stat.S_ISDIR(metadata.st_mode):
                        pending.append(Path(entry.path))
        except FileNotFoundError:
            continue
    return total_bytes, inode_count


def _require_tree_bounds(root: Path) -> None:
    total_bytes, inode_count = _tree_usage(root)
    if inode_count > MAX_RUNTIME_FILES or total_bytes > MAX_RUNTIME_BYTES:
        raise ValueError("external Pi runtime exceeds its construction bounds")


PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37


@dataclass(frozen=True)
class _ProcessIdentity:
    pid: int
    state: str
    parent_pid: int
    group_id: int
    session_id: int
    start_time: int


@dataclass
class _DescendantTracker:
    owner_pid: int
    started_after: int
    baseline_children: dict[int, int]
    identities: dict[int, int]

    def refresh(self) -> dict[int, _ProcessIdentity]:
        snapshot = _process_snapshot()
        self.identities = {
            pid: start_time
            for pid, start_time in self.identities.items()
            if pid in snapshot and snapshot[pid].start_time == start_time
        }
        known = set(self.identities)
        changed = True
        while changed:
            changed = False
            for process in snapshot.values():
                if process.pid in known or process.start_time < self.started_after:
                    continue
                adopted = (
                    process.parent_pid == self.owner_pid
                    and self.baseline_children.get(process.pid) != process.start_time
                )
                if process.parent_pid in known or adopted:
                    self.identities[process.pid] = process.start_time
                    known.add(process.pid)
                    changed = True
        return {pid: snapshot[pid] for pid in known if pid in snapshot}

    def reap(self, leader_pid: int) -> None:
        for process in self.refresh().values():
            if (
                process.pid == leader_pid
                or process.parent_pid != self.owner_pid
                or process.state not in {"Z", "X"}
            ):
                continue
            try:
                os.waitpid(process.pid, os.WNOHANG)
            except (ChildProcessError, ProcessLookupError):
                pass


def _open_pidfd(pid: int) -> int | None:
    native = getattr(os, "pidfd_open", None)
    if native is not None:
        try:
            return native(pid)
        except ProcessLookupError:
            return None
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        pidfd_open = libc.pidfd_open
    except AttributeError:
        return None
    pidfd_open.argtypes = (ctypes.c_int, ctypes.c_uint)
    pidfd_open.restype = ctypes.c_int
    descriptor = pidfd_open(pid, 0)
    if descriptor >= 0:
        return descriptor
    error = ctypes.get_errno()
    if error == 3:
        return None
    raise OSError(error, os.strerror(error))


def _proc_identity(pid: int) -> _ProcessIdentity | None:
    try:
        value = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    fields = value[value.rfind(")") + 2 :].split()
    return _ProcessIdentity(
        pid,
        fields[0],
        int(fields[1]),
        int(fields[2]),
        int(fields[3]),
        int(fields[19]),
    )


def _process_snapshot() -> dict[int, _ProcessIdentity]:
    snapshot: dict[int, _ProcessIdentity] = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        identity = _proc_identity(int(path.name))
        if identity is not None:
            snapshot[identity.pid] = identity
    return snapshot


def _direct_children(parent_pid: int) -> dict[int, int]:
    return {
        process.pid: process.start_time
        for process in _process_snapshot().values()
        if process.parent_pid == parent_pid
    }


def _get_child_subreaper() -> bool:
    value = ctypes.c_int()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(value), 0, 0, 0) < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return bool(value.value)


def _set_child_subreaper(enabled: bool) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, int(enabled), 0, 0, 0) < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


@contextmanager
def _scoped_child_subreaper():
    previous = _get_child_subreaper()
    if not previous:
        _set_child_subreaper(True)
    try:
        yield
    finally:
        if not previous:
            _set_child_subreaper(False)


def _live_processes(
    processes: dict[int, _ProcessIdentity],
) -> list[_ProcessIdentity]:
    return [
        process for process in processes.values() if process.state not in {"Z", "X"}
    ]


def _terminate_descendants(
    process: subprocess.Popen, tracker: _DescendantTracker
) -> None:
    members = _live_processes(tracker.refresh())
    if members:
        _signal_processes(members, signal.SIGTERM)
    deadline = time.monotonic() + 1
    while members and time.monotonic() < deadline:
        process.poll()
        tracker.reap(process.pid)
        time.sleep(0.01)
        members = _live_processes(tracker.refresh())
    if members:
        _signal_processes(members, signal.SIGKILL)
    kill_deadline = time.monotonic() + 1
    while tracker.refresh() and time.monotonic() < kill_deadline:
        process.poll()
        tracker.reap(process.pid)
        time.sleep(0.01)
    tracker.reap(process.pid)
    if tracker.refresh():
        raise RuntimeError("bounded subprocess descendants did not terminate")
    try:
        process.wait(timeout=0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _signal_processes(processes: list[_ProcessIdentity], signal_number: int) -> None:
    for process in processes:
        pidfd = _open_pidfd(process.pid)
        if pidfd is None:
            continue
        current = _proc_identity(process.pid)
        try:
            if current is None or current.start_time != process.start_time:
                continue
            if current.state in {"Z", "X"}:
                continue
            native = getattr(signal, "pidfd_send_signal", None)
            if native is not None:
                try:
                    native(pidfd, signal_number)
                except ProcessLookupError:
                    pass
                continue
            libc = ctypes.CDLL(None, use_errno=True)
            pidfd_send_signal = libc.pidfd_send_signal
            pidfd_send_signal.argtypes = (
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_uint,
            )
            pidfd_send_signal.restype = ctypes.c_int
            if pidfd_send_signal(pidfd, signal_number, None, 0) < 0:
                error = ctypes.get_errno()
                if error != 3:
                    raise OSError(error, os.strerror(error))
        finally:
            try:
                os.close(pidfd)
            except OSError:
                pass


def _run_bounded_command_in_supervisor(
    command: list[str],
    *,
    root: Path,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
    text: bool = False,
    timeout: float = BUILD_TIMEOUT_SECONDS,
    max_bytes: int | None = None,
    max_inodes: int | None = None,
    poll_seconds: float = 0.05,
) -> subprocess.CompletedProcess:
    byte_limit = MAX_RUNTIME_BYTES if max_bytes is None else max_bytes
    inode_limit = MAX_RUNTIME_FILES if max_inodes is None else max_inodes
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    started_after = max(0, int(uptime * clock_ticks) - 1)
    owner_pid = os.getpid()
    with _scoped_child_subreaper():
        baseline_children = _direct_children(owner_pid)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            start_new_session=True,
        )
        leader = _proc_identity(process.pid)
        tracker = _DescendantTracker(
            owner_pid,
            started_after,
            baseline_children,
            {leader.pid: leader.start_time} if leader is not None else {},
        )
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                tracker.reap(process.pid)
                tracker.refresh()
                total_bytes, inode_count = _tree_usage(root)
                if total_bytes > byte_limit or inode_count > inode_limit:
                    _terminate_descendants(process, tracker)
                    raise ValueError("external Pi live construction bound exceeded")
                if time.monotonic() >= deadline:
                    _terminate_descendants(process, tracker)
                    raise subprocess.TimeoutExpired(command, timeout)
                time.sleep(poll_seconds)
            tracker.reap(process.pid)
            if tracker.refresh():
                _terminate_descendants(process, tracker)
            stdout, stderr = process.communicate()
            total_bytes, inode_count = _tree_usage(root)
            if total_bytes > byte_limit or inode_count > inode_limit:
                raise ValueError("external Pi live construction bound exceeded")
        except BaseException:
            _terminate_descendants(process, tracker)
            raise
    completed = subprocess.CompletedProcess(
        command, process.returncode, stdout=stdout, stderr=stderr
    )
    if check and process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode, command, output=stdout, stderr=stderr
        )
    return completed


def _interrupt_command_supervisor(_signal_number, _frame) -> None:
    raise InterruptedError("bounded command supervisor interrupted")


def run_bounded_command(
    command: list[str],
    *,
    root: Path,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
    text: bool = False,
    timeout: float = BUILD_TIMEOUT_SECONDS,
    max_bytes: int | None = None,
    max_inodes: int | None = None,
    poll_seconds: float = 0.05,
) -> subprocess.CompletedProcess:
    """Run one build tree in a dedicated subreaper under live filesystem bounds."""

    read_descriptor, write_descriptor = os.pipe()
    supervisor_pid = os.fork()
    if supervisor_pid == 0:
        os.close(read_descriptor)
        signal.signal(signal.SIGTERM, _interrupt_command_supervisor)
        try:
            try:
                outcome = (
                    "result",
                    _run_bounded_command_in_supervisor(
                        command,
                        root=root,
                        cwd=cwd,
                        env=env,
                        check=check,
                        capture_output=capture_output,
                        text=text,
                        timeout=timeout,
                        max_bytes=max_bytes,
                        max_inodes=max_inodes,
                        poll_seconds=poll_seconds,
                    ),
                )
            except Exception as error:
                outcome = ("error", error)
            try:
                payload = pickle.dumps(outcome)
            except Exception as error:
                payload = pickle.dumps(
                    (
                        "error",
                        RuntimeError(f"bounded command supervisor failed: {error}"),
                    )
                )
            with os.fdopen(write_descriptor, "wb") as pipe:
                pipe.write(payload)
        finally:
            os._exit(0)

    os.close(write_descriptor)
    try:
        with os.fdopen(read_descriptor, "rb") as pipe:
            outcome = pickle.load(pipe)
    except BaseException:
        try:
            os.kill(supervisor_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.waitpid(supervisor_pid, 0)
        raise
    _pid, status = os.waitpid(supervisor_pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status):
        raise RuntimeError("bounded command supervisor exited unexpectedly")
    kind, value = outcome
    if kind == "error":
        raise value
    return value


def _run_build_command(
    runner,
    command: list[str],
    *,
    root: Path,
    **kwargs,
):
    if runner is subprocess.run:
        return run_bounded_command(command, root=root, **kwargs)
    result = runner(command, **kwargs)
    _require_tree_bounds(root)
    return result


def _require_readonly(runtime: Path) -> None:
    for path in (runtime, *runtime.rglob("*")):
        if not path.is_symlink() and path.stat().st_mode & 0o222:
            raise ValueError(
                f"external Pi runtime input is mutable: {path.relative_to(runtime)}"
            )


def external_pi_runtime_manifest(
    runtime: Path,
    *,
    expected_id: str | None = None,
    expected_node: tuple[str, str] | None = None,
    expected_contract: str | None = None,
) -> dict:
    """Strictly validate and return one published external Pi runtime manifest."""

    value = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
    if set(value) != {
        "contract",
        "runtime_id",
        "source_release",
        "entry_point",
        "node",
        "files",
    }:
        raise ValueError("external Pi runtime manifest has an unexpected schema")
    if (
        value["contract"] != (expected_contract or CONTRACT)
        or value["runtime_id"] != (expected_id or runtime.name)
        or value["entry_point"] != ENTRY_POINT
        or not isinstance(value["source_release"], str)
        or not value["source_release"]
    ):
        raise ValueError("external Pi runtime manifest identity is invalid")
    node = value["node"]
    if not isinstance(node, dict) or set(node) != {
        "version",
        "distribution_sha256",
        "executable",
        "executable_sha256",
    }:
        raise ValueError("external Pi Node manifest has an unexpected schema")
    node_identity = (node["version"], node["distribution_sha256"])
    if (
        not isinstance(node_identity[0], str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", node_identity[0])
        or not isinstance(node_identity[1], str)
        or not re.fullmatch(r"[0-9a-f]{64}", node_identity[1])
        or node["executable"] != "node/bin/node"
        or (expected_node is not None and node_identity != expected_node)
    ):
        raise ValueError("external Pi Node identity is invalid")
    declared_files = value["files"]
    if not isinstance(declared_files, dict) or any(
        not isinstance(path, str) or not isinstance(digest, str)
        for path, digest in declared_files.items()
    ):
        raise ValueError("external Pi runtime file inventory is invalid")
    actual_files = _runtime_files(runtime)
    if actual_files != declared_files:
        raise ValueError("external Pi runtime file inventory does not match")
    if node["executable_sha256"] != actual_files.get("node/bin/node"):
        raise ValueError("external Pi Node executable digest does not match")
    if (
        ENTRY_POINT not in actual_files
        or "assets/pi-system-prompt.txt" not in actual_files
    ):
        raise ValueError("external Pi executable inputs are missing")
    _require_readonly(runtime)
    return value


def prepare_external_pi_runtime(
    release: Path,
    runtimes_root: Path,
    *,
    runner=subprocess.run,
    node_archive: Path | None = None,
    python_binary: Path = PYTHON_BINARY,
) -> tuple[Path, bool]:
    """Build in a bounded temporary tree and publish by atomic rename."""

    recorded_descriptor = recorded_external_pi_runtime_descriptor(release)
    node_version, node_sha256 = _node_contract(release)
    if recorded_descriptor is not None:
        identifier = str(recorded_descriptor["runtime_id"])
        target = runtimes_root / identifier
    else:
        identifier = external_pi_runtime_id(release)
        target = runtimes_root / identifier
    if target.exists():
        external_pi_runtime_manifest(
            target,
            expected_id=identifier,
            expected_node=(node_version, node_sha256),
            expected_contract=(
                str(recorded_descriptor["contract"])
                if recorded_descriptor is not None
                else CONTRACT
            ),
        )
        return target, False
    calculated_identifier = external_pi_runtime_id(release)
    if recorded_descriptor is not None and identifier != calculated_identifier:
        raise ValueError(
            "recorded external Pi runtime is missing and cannot be rebuilt"
        )
    if (node_version, node_sha256) != (PI_NODE_VERSION, PI_NODE_SHA256):
        raise ValueError("release Node contract does not match deployment tooling")
    runtimes_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(runtimes_root).free < MIN_FREE_BYTES:
        raise ValueError("external Pi runtime root has insufficient free space")
    temporary = Path(tempfile.mkdtemp(prefix=f".{identifier}.new-", dir=runtimes_root))
    try:
        archive = node_archive or temporary / ".node.tar.xz"
        if node_archive is None:
            runner(
                [
                    str(CURL_BINARY),
                    "-fsSLo",
                    str(archive),
                    "--max-filesize",
                    str(MAX_NODE_ARCHIVE_BYTES),
                    NODE_ARCHIVE_URL,
                ],
                check=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        if archive.stat().st_size > MAX_NODE_ARCHIVE_BYTES:
            raise ValueError("external Pi Node archive exceeds its size bound")
        if sha256_file(archive) != node_sha256:
            raise ValueError("external Pi Node archive digest does not match")
        extracted = temporary / ".node-extract"
        extracted.mkdir()
        expected_node_root = f"node-v{node_version}-linux-x64"
        with tarfile.open(archive, mode="r:xz") as bundle:
            member_count = 0
            extracted_bytes = 0
            for member in bundle:
                member_count += 1
                extracted_bytes += member.size
                if (
                    member_count > MAX_RUNTIME_FILES
                    or extracted_bytes > MAX_RUNTIME_BYTES
                ):
                    raise ValueError(
                        "external Pi Node archive exceeds extraction bounds"
                    )
                if Path(member.name).parts[:1] != (expected_node_root,):
                    raise ValueError("external Pi Node archive layout is invalid")
                bundle.extract(member, extracted, filter="data")
        extracted_root = extracted / expected_node_root
        if (
            not (extracted_root / "bin/node").is_file()
            or not (extracted_root / "lib/node_modules/npm/bin/npm-cli.js").is_file()
        ):
            raise ValueError("external Pi Node archive layout is invalid")
        os.replace(extracted_root, temporary / "node")
        shutil.rmtree(extracted)
        if node_archive is None:
            archive.unlink()

        node_binary = temporary / "node/bin/node"
        version = runner(
            [str(node_binary), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
        ).stdout.strip()
        if version != f"v{node_version}":
            raise ValueError(
                "external Pi Node version does not match the pinned contract"
            )

        app = temporary / "app"
        worker = release / WORKER_ROOT
        app.mkdir()
        for name in ("package.json", "package-lock.json", "tsconfig.json"):
            shutil.copy2(worker / name, app / name)
        shutil.copytree(worker / "src", app / "src")
        shutil.copytree(worker / "test", app / "test")
        (temporary / "assets").mkdir()

        npm_home = temporary / ".npm-home"
        npm_cache = temporary / ".npm-cache"
        npm_home.mkdir()
        npm_cache.mkdir()
        npm_user_config = npm_home / "npmrc"
        npm_global_config = npm_home / "global-npmrc"
        npm_user_config.write_text("", encoding="utf-8")
        npm_global_config.write_text("", encoding="utf-8")
        environment = {
            "PATH": f"{temporary / 'node/bin'}:/usr/bin:/bin",
            "HOME": str(npm_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "npm_config_cache": str(npm_cache),
            "npm_config_userconfig": str(npm_user_config),
            "npm_config_globalconfig": str(npm_global_config),
            "npm_config_update_notifier": "false",
        }
        npm_command = [
            str(node_binary),
            str(temporary / "node/lib/node_modules/npm/bin/npm-cli.js"),
        ]
        common = {
            "cwd": app,
            "env": environment,
            "check": True,
            "timeout": BUILD_TIMEOUT_SECONDS,
        }
        # The npm build script and the prompt renderer are release code, so
        # they run as the unprivileged build user, never as root.
        build_sandbox.lend(temporary)
        try:
            _run_build_command(
                runner,
                build_sandbox.command(
                    [
                        *npm_command,
                        "ci",
                        "--ignore-scripts",
                        "--no-audit",
                        "--no-fund",
                    ]
                ),
                root=temporary,
                **common,
            )
            _run_build_command(
                runner,
                build_sandbox.command([*npm_command, "run", "build"]),
                root=temporary,
                **common,
            )
            _run_build_command(
                runner,
                build_sandbox.command(
                    [*npm_command, "prune", "--omit=dev", "--ignore-scripts"]
                ),
                root=temporary,
                **common,
            )
            prompt_environment = environment.copy()
            prompt_environment["PYTHONPATH"] = str(release)
            prompt_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            _run_build_command(
                runner,
                build_sandbox.command(
                    [
                        str(python_binary),
                        str(
                            release
                            / "backend/chat_sandbox_worker/render_pi_prompt_asset.py"
                        ),
                        str(temporary / "assets/pi-system-prompt.txt"),
                    ]
                ),
                root=temporary,
                cwd=release,
                env=prompt_environment,
                check=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        finally:
            build_sandbox.reclaim(temporary)

        shutil.rmtree(app / "src")
        shutil.rmtree(app / "test")
        shutil.rmtree(app / "dist/test", ignore_errors=True)
        shutil.rmtree(npm_home)
        shutil.rmtree(npm_cache)
        (app / "tsconfig.json").unlink()
        files = _runtime_files(temporary)
        node_digest = files["node/bin/node"]
        (temporary / "runtime.json").write_text(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "runtime_id": identifier,
                    "source_release": _source_release(release),
                    "entry_point": ENTRY_POINT,
                    "node": {
                        "version": node_version,
                        "distribution_sha256": node_sha256,
                        "executable": "node/bin/node",
                        "executable_sha256": node_digest,
                    },
                    "files": files,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        make_tree_readonly(temporary)
        external_pi_runtime_manifest(
            temporary,
            expected_id=identifier,
            expected_node=(node_version, node_sha256),
        )
        try:
            os.replace(temporary, target)
        except FileExistsError:
            external_pi_runtime_manifest(target)
            return target, False
        return target, True
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def cleanup_external_pi_runtimes(
    runtimes_root: Path, protected_ids: set[str]
) -> list[str]:
    """Remove only complete, unreferenced external Pi runtime directories."""

    removed: list[str] = []
    if RETAIN_ALL_RUNTIMES in protected_ids or not runtimes_root.is_dir():
        return removed
    for path in sorted(runtimes_root.iterdir()):
        if (
            path.is_dir()
            and not path.name.startswith(".")
            and path.name not in protected_ids
        ):
            shutil.rmtree(path)
            removed.append(path.name)
    return removed
