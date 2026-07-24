#!/usr/bin/env python3
"""Installed CLI for immutable Papers With Code releases."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from deploy.release import (
        ENVIRONMENTS,
        atomic_symlink,
        build_manifest,
        profile_features,
        read_pointers,
        release_id,
        sha256_file,
        validate_manifest,
    )
except ModuleNotFoundError:
    from release import (  # type: ignore[no-redef]
        ENVIRONMENTS,
        atomic_symlink,
        build_manifest,
        profile_features,
        read_pointers,
        release_id,
        sha256_file,
        validate_manifest,
    )

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
REPOSITORY = Path(os.environ.get("PWC_DEPLOY_REPOSITORY", APP_ROOT / "repository.git"))
RELEASES = APP_ROOT / "releases"
ENVIRONMENTS_ROOT = APP_ROOT / "environments"
VENV = APP_ROOT / ".venv"
RUNTIME_LOCK = APP_ROOT / "runtime-lock.sha256"
CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
LOG_ROOT = Path(os.environ.get("PWC_DEPLOY_LOG_ROOT", "/var/log/paperswithcode/deploy"))
MIN_FREE_BYTES = int(os.environ.get("PWC_DEPLOY_MIN_FREE_BYTES", str(1536**3)))
PORTS = {"production": 8000, "staging": 8001}
PUBLIC_URLS = {
    "production": "https://paperswithcode.co",
    "staging": "https://staging.paperswithcode.co",
}


class DeployError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=True,
    )


def log_event(action: str, environment: str, result: str, **details: object) -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "environment": environment,
        "result": result,
        **details,
    }
    with (LOG_ROOT / "history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def require_root() -> None:
    if os.geteuid() != 0 and not os.environ.get("PWC_DEPLOY_TESTING"):
        raise DeployError("run this command through sudo")


def resolve_sha(source: str, environment: str) -> str:
    run(["git", "--git-dir", str(REPOSITORY), "fetch", "--prune", "origin"])
    result = run(
        ["git", "--git-dir", str(REPOSITORY), "rev-parse", f"{source}^{{commit}}"],
        capture=True,
    )
    sha = result.stdout.strip()
    if len(sha) != 40:
        raise DeployError(f"could not resolve an exact commit from {source!r}")
    if environment == "production":
        ancestry = subprocess.run(
            [
                "git",
                "--git-dir",
                str(REPOSITORY),
                "merge-base",
                "--is-ancestor",
                sha,
                "refs/remotes/origin/main",
            ],
            check=False,
        )
        if ancestry.returncode:
            raise DeployError("production commit is not reachable from origin/main")
    return sha


def check_capacity() -> None:
    free = shutil.disk_usage(APP_ROOT.parent).free
    if free < MIN_FREE_BYTES:
        raise DeployError(
            f"only {free // (1024**2)} MiB free; "
            f"{MIN_FREE_BYTES // (1024**2)} MiB is required"
        )


def _extract_commit(sha: str, destination: Path) -> None:
    archive = destination.parent / "source.tar"
    with archive.open("wb") as handle:
        subprocess.run(
            ["git", "--git-dir", str(REPOSITORY), "archive", "--format=tar", sha],
            stdout=handle,
            check=True,
        )
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")


def _chat_descriptor_from_source(source: Path, environment: str) -> dict | None:
    if environment != "staging":
        return None
    script = """
import json
from backend.chat_sandbox_worker.contract import (
    DEFAULT_BACKEND, MODAL_IMAGE_ID, NEW_CHAT_MODAL_PERCENTAGE,
    PWC_CLI_VERSION, WORKER_CONTRACT_VERSION,
)
from backend.chat_sandbox_worker.prompt import sha256
print(json.dumps({
    "enabled": True,
    "new_chat_modal_percentage": NEW_CHAT_MODAL_PERCENTAGE,
    "default_backend": DEFAULT_BACKEND,
    "modal_image_version": MODAL_IMAGE_ID,
    "pwc_cli_version": PWC_CLI_VERSION,
    "worker_contract_version": WORKER_CONTRACT_VERSION,
    "system_prompt_sha256": sha256(),
}, sort_keys=True))
"""
    environment_values = {
        "PATH": os.defpath,
        "PYTHONPATH": str(source),
        "PYTHONNOUSERSITE": "1",
    }
    output = subprocess.check_output(
        [sys.executable, "-c", script],
        cwd=source,
        env=environment_values,
        text=True,
    )
    descriptor = json.loads(output)
    if not isinstance(descriptor, dict):
        raise DeployError("source chat runtime descriptor is invalid")
    return descriptor


def prepare_release(sha: str, environment: str) -> Path:
    target = RELEASES / release_id(sha, environment)
    if target.exists():
        validate_manifest(target, environment)
        return target
    check_capacity()
    RELEASES.mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(prefix="pwc-build-", dir=APP_ROOT))
    source = build_root / "source"
    source.mkdir()
    try:
        _extract_commit(sha, source)
        frontend = source / "frontend"
        build_env = os.environ.copy()
        build_env.update(
            {
                "VITE_CHAT_ENABLED": "1" if environment == "staging" else "0",
                "VITE_CHAT_LIVE": "1" if environment == "staging" else "0",
                "VITE_CODEX_ADD_EVALS_ENABLED": (
                    "1" if environment == "staging" else "0"
                ),
                "VITE_CODEX_ENRICH_PAPER_ENABLED": (
                    "1" if environment == "staging" else "0"
                ),
            }
        )
        run(["npm", "ci"], cwd=frontend, env=build_env)
        run(
            ["npm", "run", "build", "--", "--mode", environment],
            cwd=frontend,
            env=build_env,
        )
        features = profile_features(environment)
        (frontend / "dist" / "features.json").write_text(
            json.dumps(features, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.move(str(frontend / "dist"), str(source / "frontend-dist"))
        shutil.rmtree(frontend / "node_modules")
        for env_file in source.rglob(".env*"):
            if env_file.is_file():
                env_file.unlink()
        forbidden = [
            path
            for path in source.rglob("*")
            if path.is_file()
            and (
                path.name in {"keys.env", ".env"}
                or path.suffix in {".dump", ".sql.gz"}
                or "__pycache__" in path.parts
            )
        ]
        if forbidden:
            raise DeployError(
                "release contains forbidden artifacts: "
                + ", ".join(str(path.relative_to(source)) for path in forbidden[:10])
            )
        descriptor = _chat_descriptor_from_source(source, environment)
        (source / "release.json").write_text(
            json.dumps(
                build_manifest(sha, environment, chat_descriptor=descriptor),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        validate_manifest(source, environment)
        os.replace(source, target)
        for path in sorted(target.rglob("*"), reverse=True):
            path.chmod(path.stat().st_mode & ~0o222)
        target.chmod(0o555)
        return target
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def sync_runtime(release: Path) -> bool:
    wanted = sha256_file(release / "uv.lock")
    current = RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else ""
    if current == wanted and (VENV / "bin" / "python").is_file():
        return False
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(VENV)
    run(["uv", "sync", "--frozen", "--project", str(release)], env=env)
    RUNTIME_LOCK.write_text(wanted + "\n", encoding="utf-8")
    return True


def sync_runtime_with_recovery(release: Path, previous_lock_hash: str) -> bool:
    try:
        return sync_runtime(release)
    except (subprocess.CalledProcessError, OSError):
        if previous_lock_hash:
            restore_runtime(previous_lock_hash)
        raise


def restore_runtime(lock_hash: str) -> None:
    for environment in ENVIRONMENTS:
        pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
        for release in (pointers.current, pointers.previous):
            if release and sha256_file(release / "uv.lock") == lock_hash:
                env = os.environ.copy()
                env["UV_PROJECT_ENVIRONMENT"] = str(VENV)
                run(
                    ["uv", "sync", "--frozen", "--project", str(release)],
                    env=env,
                )
                RUNTIME_LOCK.write_text(lock_hash + "\n", encoding="utf-8")
                return
    raise DeployError("cannot find a retained release for the previous runtime lock")


def free_candidate_port() -> int:
    for port in range(8100, 8200):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise DeployError("no free candidate qualification port")


def _read_json(url: str, timeout: int = 2) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def qualify(release: Path, environment: str) -> None:
    manifest = validate_manifest(release, environment)
    port = free_candidate_port()
    unit = f"pwc-candidate-{environment}-{os.getpid()}"
    user = f"pwc-{environment}"
    command = [
        "systemd-run",
        "--unit",
        unit,
        "--uid",
        user,
        "--gid",
        user,
        "--working-directory",
        str(release),
        "--property",
        f"EnvironmentFile={CONFIG_ROOT / (environment + '.env')}",
        "--setenv",
        f"PWC_PORT={port}",
        "--setenv",
        f"PWC_RELEASE_ID={manifest['release_id']}",
        "--setenv",
        f"PWC_FRONTEND_DIST_DIR={release / 'frontend-dist'}",
        str(VENV / "bin" / "python"),
        str(release / "deploy" / "run_backend.py"),
    ]
    run(command)
    try:
        deadline = time.monotonic() + 45
        ready = None
        while time.monotonic() < deadline:
            ready = _read_json(f"http://127.0.0.1:{port}/internal/ready")
            if ready and ready.get("status") == "ready":
                break
            time.sleep(0.5)
        else:
            raise DeployError(f"candidate failed readiness: {ready!r}")
        if ready["environment"] != environment:
            raise DeployError("candidate answered with the wrong environment")
        if ready["release_id"] != manifest["release_id"]:
            raise DeployError("candidate answered with the wrong release ID")
        run(
            [
                str(VENV / "bin" / "python"),
                str(release / "deploy" / "smoke_test.py"),
                "--environment",
                environment,
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--expected-release",
                manifest["release_id"],
                "--release-dir",
                str(release),
                "--candidate",
            ]
        )
    finally:
        subprocess.run(["systemctl", "stop", f"{unit}.service"], check=False)
        subprocess.run(["systemctl", "reset-failed", f"{unit}.service"], check=False)


def _unit(environment: str) -> str:
    return f"paperswithcode-backend@{environment}.service"


def activate(
    release: Path,
    environment: str,
    *,
    previous_runtime_lock: str = "",
) -> None:
    root = ENVIRONMENTS_ROOT / environment
    pointers = read_pointers(root)
    if pointers.current == release:
        return
    if pointers.current:
        atomic_symlink(pointers.current, root / "previous")
    atomic_symlink(release, root / "current")
    try:
        run(["systemctl", "restart", _unit(environment)])
        manifest = validate_manifest(release, environment)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = _read_json(f"http://127.0.0.1:{PORTS[environment]}/internal/ready")
            if ready and ready.get("release_id") == manifest["release_id"]:
                break
            time.sleep(0.5)
        else:
            raise DeployError("live readiness failed")
        run(
            [
                str(VENV / "bin" / "python"),
                str(release / "deploy" / "smoke_test.py"),
                "--environment",
                environment,
                "--base-url",
                PUBLIC_URLS[environment],
                "--expected-release",
                manifest["release_id"],
                "--release-dir",
                str(release),
            ]
        )
    except (DeployError, subprocess.CalledProcessError, OSError) as exc:
        rollback_after_failed_activation(
            environment,
            release,
            previous_runtime_lock=previous_runtime_lock,
        )
        raise DeployError("activation failed; automatic rollback completed") from exc


def rollback_after_failed_activation(
    environment: str,
    failed: Path,
    *,
    previous_runtime_lock: str = "",
) -> None:
    root = ENVIRONMENTS_ROOT / environment
    pointers = read_pointers(root)
    if not pointers.previous:
        raise DeployError("activation failed and no previous release exists")
    atomic_symlink(pointers.previous, root / "current")
    if previous_runtime_lock:
        restore_runtime(previous_runtime_lock)
    run(["systemctl", "restart", _unit(environment)])
    log_event(
        "automatic-rollback",
        environment,
        "success",
        failed_release=failed.name,
        restored_release=pointers.previous.name,
    )


def protected_release_paths() -> set[Path]:
    protected = set()
    for environment in ENVIRONMENTS:
        pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
        protected.update(path for path in (pointers.current, pointers.previous) if path)
    return protected


def cleanup_releases() -> None:
    protected = protected_release_paths()
    for release in RELEASES.iterdir():
        if release.is_dir() and release.resolve() not in protected:
            shutil.rmtree(release)


def cleanup_command(args: argparse.Namespace) -> int:
    require_root()
    if args.confirm != "CLEAN_RELEASES":
        raise DeployError("cleanup requires --confirm CLEAN_RELEASES")
    protected = protected_release_paths()
    targets = [
        path
        for path in RELEASES.iterdir()
        if path.is_dir() and path.resolve() not in protected
    ]
    print(json.dumps({"remove": [path.name for path in targets]}, indent=2))
    for path in targets:
        shutil.rmtree(path)
    return 0


def deploy(args: argparse.Namespace) -> int:
    require_root()
    if args.environment == "production" and args.confirm != "DEPLOY_PRODUCTION":
        raise DeployError("production requires --confirm DEPLOY_PRODUCTION")
    sha = resolve_sha(args.source, args.environment)
    release = prepare_release(sha, args.environment)
    old_runtime_lock = (
        RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else ""
    )
    dependency_change = sync_runtime_with_recovery(release, old_runtime_lock)
    current = read_pointers(ENVIRONMENTS_ROOT / args.environment).current
    print(
        json.dumps(
            {
                "environment": args.environment,
                "source": args.source,
                "current_sha": (
                    validate_manifest(current)["git_sha"] if current else None
                ),
                "candidate_sha": sha,
                "features": profile_features(args.environment),
                "dependencies_changed": dependency_change,
            },
            indent=2,
        )
    )
    try:
        qualify(release, args.environment)
        if dependency_change:
            for other in ENVIRONMENTS:
                if other == args.environment:
                    continue
                other_current = read_pointers(ENVIRONMENTS_ROOT / other).current
                if other_current:
                    qualify(other_current, other)
    except (DeployError, subprocess.CalledProcessError, OSError, ValueError):
        if dependency_change and old_runtime_lock:
            restore_runtime(old_runtime_lock)
        raise
    activate(
        release,
        args.environment,
        previous_runtime_lock=old_runtime_lock if dependency_change else "",
    )
    cleanup_releases()
    log_event("deploy", args.environment, "success", git_sha=sha, source=args.source)
    print(f"deployed {args.source} ({sha}) to {args.environment}")
    return 0


def rollback(args: argparse.Namespace) -> int:
    require_root()
    if args.environment == "production" and args.confirm != "ROLLBACK_PRODUCTION":
        raise DeployError("production requires --confirm ROLLBACK_PRODUCTION")
    root = ENVIRONMENTS_ROOT / args.environment
    pointers = read_pointers(root)
    if not pointers.previous or not pointers.current:
        raise DeployError("current and previous releases are required for rollback")
    validate_manifest(pointers.previous, args.environment)
    old_current = pointers.current
    old_runtime_lock = (
        RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else ""
    )
    dependency_change = sync_runtime_with_recovery(pointers.previous, old_runtime_lock)
    atomic_symlink(pointers.previous, root / "current")
    atomic_symlink(old_current, root / "previous")
    try:
        run(["systemctl", "restart", _unit(args.environment)])
        expected = validate_manifest(pointers.previous)["release_id"]
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = _read_json(
                f"http://127.0.0.1:{PORTS[args.environment]}/internal/ready"
            )
            if ready and ready.get("release_id") == expected:
                break
            time.sleep(0.5)
        else:
            raise DeployError("rollback target failed readiness")
    except (DeployError, subprocess.CalledProcessError, OSError) as exc:
        atomic_symlink(old_current, root / "current")
        atomic_symlink(pointers.previous, root / "previous")
        if dependency_change and old_runtime_lock:
            restore_runtime(old_runtime_lock)
        run(["systemctl", "restart", _unit(args.environment)])
        raise DeployError("rollback target failed; restored original release") from exc
    log_event(
        "rollback",
        args.environment,
        "success",
        restored_release=pointers.previous.name,
    )
    print(f"rolled {args.environment} back to {pointers.previous.name}")
    return 0


def _systemctl_state(unit: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", unit], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or "unknown"


def status(_: argparse.Namespace) -> int:
    result: dict[str, object] = {
        "runtime_lock_sha256": (
            RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else None
        ),
        "disk": {},
        "environments": {},
        "logs": {},
    }
    usage = shutil.disk_usage(APP_ROOT.parent)
    result["disk"] = {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }
    for environment in ENVIRONMENTS:
        pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
        item = {
            "port": PORTS[environment],
            "service": _systemctl_state(_unit(environment)),
        }
        for name, path in (
            ("current", pointers.current),
            ("previous", pointers.previous),
        ):
            try:
                item[name] = validate_manifest(path, environment) if path else None
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                item[name] = {"invalid": str(exc), "path": str(path)}
        result["environments"][environment] = item
    for name, path in {
        "journal": Path("/var/log/journal"),
        "nginx": Path("/var/log/nginx"),
        "cron": Path("/var/lib/paperswithcode/production/cron-logs"),
        "deploy": LOG_ROOT,
    }.items():
        size = 0
        if path.exists():
            size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        result["logs"][name] = size
    history = LOG_ROOT / "history.jsonl"
    result["last_action"] = (
        json.loads(history.read_text().splitlines()[-1])
        if history.is_file() and history.stat().st_size
        else None
    )
    print(json.dumps(result, indent=2))
    return 0


def parser_for(program: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=program)
    if program.endswith("pwc-deploy"):
        parser.add_argument("environment", choices=ENVIRONMENTS)
        parser.add_argument("source")
        parser.add_argument("--confirm")
        parser.set_defaults(handler=deploy)
    elif program.endswith("pwc-rollback"):
        parser.add_argument("environment", choices=ENVIRONMENTS)
        parser.add_argument("--confirm")
        parser.set_defaults(handler=rollback)
    elif program.endswith("pwc-cleanup"):
        parser.add_argument("--confirm")
        parser.set_defaults(handler=cleanup_command)
    else:
        parser.set_defaults(handler=status)
    return parser


def main() -> int:
    program = os.environ.get("PWC_DEPLOY_PROGRAM", Path(sys.argv[0]).name)
    parser = parser_for(program)
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (DeployError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"{program}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
