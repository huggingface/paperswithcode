"""Build and retain immutable Python runtimes keyed by ``uv.lock``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from deploy import build_sandbox
    from deploy.release import sha256_file
except ModuleNotFoundError:
    import build_sandbox  # type: ignore[no-redef]
    from release import sha256_file  # type: ignore[no-redef]

UV_BINARY = Path(os.environ.get("PWC_DEPLOY_UV", "/usr/local/bin/uv"))


def runtime_id(release: Path) -> str:
    return sha256_file(release / "uv.lock")


def runtime_manifest(runtime: Path) -> dict:
    value = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
    if set(value) != {"lock_sha256", "python_version", "python_base"}:
        raise ValueError("runtime manifest has an unexpected schema")
    if value["lock_sha256"] != runtime.name:
        raise ValueError("runtime manifest lock hash does not match its path")
    launcher = runtime / "bin" / "python"
    if not launcher.is_file():
        raise ValueError("runtime Python launcher is missing")
    resolved = launcher.resolve()
    if str(resolved) != value["python_base"]:
        raise ValueError("runtime Python base does not match its manifest")
    if resolved == Path("/root") or Path("/root") in resolved.parents:
        raise ValueError("runtime Python base is inside root's private home")
    return value


def make_tree_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        readable_mode = 0o555 if path.is_dir() else 0o444
        path.chmod((mode & ~0o222) | readable_mode)
    root.chmod((root.stat().st_mode & ~0o222) | 0o555)


def prepare_runtime(
    release: Path,
    runtimes_root: Path,
    *,
    runner=subprocess.run,
    version_runner=subprocess.run,
) -> tuple[Path, bool]:
    """Build once in a temporary directory and publish by atomic rename."""

    identifier = runtime_id(release)
    target = runtimes_root / identifier
    if target.exists():
        runtime_manifest(target)
        return target, False
    runtimes_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{identifier}.new-", dir=runtimes_root))
    # uv.lock picks the packages and may build sdists, so the build user runs
    # uv with a throwaway cache rather than root's environment and cache.
    cache = Path(tempfile.mkdtemp(prefix=f".{identifier}.cache-", dir=runtimes_root))
    try:
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(cache),
            "LANG": "C.UTF-8",
            "UV_CACHE_DIR": str(cache),
        }
        environment["UV_PROJECT_ENVIRONMENT"] = str(temporary)
        environment["UV_PYTHON"] = "/usr/bin/python3"
        environment["UV_PYTHON_PREFERENCE"] = "only-system"
        # uv may otherwise hard-link files from its shared cache. Chmodding a
        # hard-linked runtime read-only would also mutate the cache inode and
        # any other environment linked to it.
        environment["UV_LINK_MODE"] = "copy"
        build_sandbox.lend(temporary)
        build_sandbox.lend(cache)
        try:
            runner(
                build_sandbox.command(
                    [
                        str(UV_BINARY),
                        "sync",
                        "--frozen",
                        "--no-install-project",
                        "--project",
                        str(release),
                    ]
                ),
                env=environment,
                check=True,
            )
            version = version_runner(
                build_sandbox.command([str(temporary / "bin" / "python"), "--version"]),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        finally:
            build_sandbox.reclaim(temporary)
            build_sandbox.reclaim(cache)
        (temporary / "runtime.json").write_text(
            json.dumps(
                {
                    "lock_sha256": identifier,
                    "python_version": version,
                    "python_base": str((temporary / "bin" / "python").resolve()),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # Console scripts embed the build venv path (including shell wrappers
        # for long shebangs). Point them at the final path before publishing.
        for script in (temporary / "bin").iterdir():
            if script.is_symlink() or not script.is_file():
                continue
            with script.open("rb") as handle:
                is_script = handle.read(2) == b"#!"
            if is_script:
                script.write_bytes(
                    script.read_bytes().replace(
                        os.fsencode(temporary), os.fsencode(target)
                    )
                )
        make_tree_readonly(temporary)
        try:
            os.replace(temporary, target)
        except FileExistsError:
            runtime_manifest(target)
        return target, True
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)


def cleanup_runtimes(runtimes_root: Path, protected_ids: set[str]) -> list[str]:
    removed: list[str] = []
    if not runtimes_root.is_dir():
        return removed
    for path in runtimes_root.iterdir():
        if (
            path.is_dir()
            and not path.name.startswith(".")
            and path.name not in protected_ids
        ):
            shutil.rmtree(path)
            removed.append(path.name)
    return removed
