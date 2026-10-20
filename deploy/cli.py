#!/usr/bin/env python3
"""Installed CLI for immutable Papers With Code releases."""

from __future__ import annotations

import argparse
import fcntl
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
from contextlib import contextmanager
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
        validate_rolling_compatibility,
    )
    from deploy.runtime import (
        cleanup_runtimes,
        prepare_runtime,
        runtime_id,
    )
    from deploy.external_pi_runtime import (
        RETAIN_ALL_RUNTIMES,
        cleanup_external_pi_runtimes,
        external_pi_runtime_descriptor,
        external_pi_runtime_id,
        prepare_external_pi_runtime,
        recorded_external_pi_runtime_id,
    )
    from deploy.external_pi_slot_lifecycle import (
        ExternalPiSlotError,
        lifecycle_enabled as external_pi_lifecycle_enabled,
        prepare_candidate_if_enabled,
        slot_status as external_pi_slot_status,
        stop_slot_if_enabled,
    )
    from deploy import build_sandbox, mcp_release
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
        validate_rolling_compatibility,
    )
    from runtime import (  # type: ignore[no-redef]
        cleanup_runtimes,
        prepare_runtime,
        runtime_id,
    )
    from external_pi_runtime import (  # type: ignore[no-redef]
        RETAIN_ALL_RUNTIMES,
        cleanup_external_pi_runtimes,
        external_pi_runtime_descriptor,
        external_pi_runtime_id,
        prepare_external_pi_runtime,
        recorded_external_pi_runtime_id,
    )
    from external_pi_slot_lifecycle import (  # type: ignore[no-redef]
        ExternalPiSlotError,
        lifecycle_enabled as external_pi_lifecycle_enabled,
        prepare_candidate_if_enabled,
        slot_status as external_pi_slot_status,
        stop_slot_if_enabled,
    )
    import build_sandbox  # type: ignore[no-redef]
    import mcp_release  # type: ignore[no-redef]

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
REPOSITORY = Path(os.environ.get("PWC_DEPLOY_REPOSITORY", APP_ROOT / "repository.git"))
RELEASES = APP_ROOT / "releases"
RUNTIMES = APP_ROOT / "runtimes"
EXTERNAL_PI_RUNTIMES = RUNTIMES / "external-pi"
ENVIRONMENTS_ROOT = APP_ROOT / "environments"
VENV = APP_ROOT / ".venv"
PYTHON_RUNTIME = APP_ROOT / "python-runtime"
RUNTIME_LOCK = APP_ROOT / "runtime-lock.sha256"
CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
LOG_ROOT = Path(os.environ.get("PWC_DEPLOY_LOG_ROOT", "/var/log/paperswithcode/deploy"))
MIN_FREE_BYTES = int(os.environ.get("PWC_DEPLOY_MIN_FREE_BYTES", str(1536 * 1024**2)))
DEPLOY_LOCK = APP_ROOT / "deployment.lock"
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
        main_ref = "refs/remotes/origin/main"
        if (
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(REPOSITORY),
                    "rev-parse",
                    "--verify",
                    main_ref,
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            != 0
        ):
            main_ref = "refs/heads/main"
        ancestry = subprocess.run(
            [
                "git",
                "--git-dir",
                str(REPOSITORY),
                "merge-base",
                "--is-ancestor",
                sha,
                main_ref,
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


def _chat_descriptor_from_source(
    source: Path, environment: str, *, chat_enabled: bool | None = None
) -> dict | None:
    enabled = environment == "staging" if chat_enabled is None else chat_enabled
    if not enabled and environment != "production":
        return None
    script = """
import json
import os
from backend.chat_sandbox_worker import contract
from backend.chat_sandbox_worker.prompt import sha256
try:
    from deploy import production_chat_contract as production_contract
except ImportError:
    production_contract = None
enabled = os.environ["PWC_RELEASE_CHAT_ENABLED"] == "true"
production = os.environ["PWC_RELEASE_ENVIRONMENT"] == "production"
descriptor = {
    "enabled": enabled,
    "new_chat_modal_percentage": contract.NEW_CHAT_MODAL_PERCENTAGE if enabled else 0,
    "default_backend": contract.DEFAULT_BACKEND,
    "modal_image_version": (
        contract.PRODUCTION_MODAL_IMAGE_ID
        if os.environ["PWC_RELEASE_ENVIRONMENT"] == "production"
        else contract.MODAL_IMAGE_ID
    ),
    "pwc_cli_version": contract.PWC_CLI_VERSION,
    "worker_contract_version": (
        getattr(production_contract, "WORKER_CONTRACT_VERSION", contract.WORKER_CONTRACT_VERSION)
        if production
        else contract.WORKER_CONTRACT_VERSION
    ),
    "gateway_contract_version": contract.GATEWAY_CONTRACT_VERSION,
    "gateway_compatible_from": contract.GATEWAY_COMPATIBLE_FROM,
    "database_contract_version": (
        getattr(production_contract, "DISABLED_DATABASE_CONTRACT_VERSION", 1)
        if production and not enabled
        else contract.DATABASE_CONTRACT_VERSION
    ),
    "system_prompt_sha256": sha256(),
}
pi_fields = (
    "DEFAULT_AGENT_HARNESS", "NEW_SESSION_PI_PERCENTAGE", "PI_NODE_SHA256",
    "PI_NODE_VERSION", "PI_SOURCE_COMMIT", "PI_VERSION",
    "SUPPORTED_AGENT_HARNESSES",
)
present_pi_fields = [field for field in pi_fields if hasattr(contract, field)]
if present_pi_fields and len(present_pi_fields) != len(pi_fields):
    raise RuntimeError("source chat contract has an incomplete Pi descriptor")
if present_pi_fields:
    descriptor.update({
        "supported_agent_harnesses": (
            list(contract.SUPPORTED_AGENT_HARNESSES) if enabled else ["claude"]
        ),
        "default_agent_harness": (
            getattr(production_contract, "DEFAULT_AGENT_HARNESS", "claude")
            if production and enabled
            else contract.DEFAULT_AGENT_HARNESS if enabled else "claude"
        ),
        "new_session_pi_percentage": (
            getattr(production_contract, "NEW_SESSION_PI_PERCENTAGE", 0)
            if production and enabled
            else contract.NEW_SESSION_PI_PERCENTAGE if enabled else 0
        ),
        "claude_sdk_version": contract.SDK_VERSION if enabled else "",
        "pi_version": contract.PI_VERSION if enabled else "",
        "pi_source_commit": contract.PI_SOURCE_COMMIT if enabled else "",
        "pi_node_version": contract.PI_NODE_VERSION if enabled else "",
        "pi_node_sha256": contract.PI_NODE_SHA256 if enabled else "",
        "restricted_hf_cli_version": contract.RESTRICTED_HF_CLI_VERSION if enabled else "",
        "direct_openai_enabled": (
            enabled
            and (
                getattr(production_contract, "DIRECT_OPENAI_ENABLED", False)
                if production
                else contract.DIRECT_OPENAI_ENABLED
            )
        ),
        "production_excalidraw_enabled": (
            enabled
            and production
            and getattr(production_contract, "EXCALIDRAW_ENABLED", False)
        ),
        "posterly_enabled": enabled and not production and contract.POSTERLY_ENABLED,
        "posterly_source_commit": contract.POSTERLY_SOURCE_COMMIT,
        "posterly_source_url": contract.POSTERLY_SOURCE_URL,
        "posterly_license": contract.POSTERLY_LICENSE,
        "posterly_playwright_version": contract.POSTERLY_PLAYWRIGHT_VERSION,
        "posterly_chromium_revision": contract.POSTERLY_CHROMIUM_REVISION,
        "posterly_artifact_bucket_id": contract.POSTERLY_ARTIFACT_BUCKET_ID,
    })
print(json.dumps(descriptor, sort_keys=True))
"""
    environment_values = {
        "PATH": os.defpath,
        "PYTHONPATH": str(source),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PWC_RELEASE_ENVIRONMENT": environment,
        "PWC_RELEASE_CHAT_ENABLED": "true" if enabled else "false",
    }
    # Importing release modules runs release code, so never do it as root.
    output = subprocess.check_output(
        build_sandbox.command([sys.executable, "-c", script]),
        cwd=source,
        env=environment_values,
        text=True,
        # A process the import leaves behind can hold stdout open; never wait
        # for it forever.
        timeout=300,
    )
    descriptor = json.loads(output)
    if not isinstance(descriptor, dict):
        raise DeployError("source chat runtime descriptor is invalid")
    return descriptor


def _configured_chat_enabled(environment: str) -> bool:
    if environment == "staging":
        return True
    config_path = CONFIG_ROOT / f"{environment}.env"
    if not config_path.is_file():
        return False
    configured: str | None = None
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "PWC_CHAT_ENABLED":
            configured = value.strip().strip('"').strip("'").lower()
    if configured is None:
        return False
    if configured not in {"true", "false"}:
        raise DeployError(f"{config_path} must set PWC_CHAT_ENABLED to true or false")
    return configured == "true"


def require_production_chat_monitor(environment: str) -> None:
    """Fail closed before building an enabled production chat release."""

    if environment != "production" or not _configured_chat_enabled(environment):
        return
    required_timers = (
        (
            "pwc-chat-alert-monitor.timer",
            "enabled production chat requires the operational alert monitor timer",
        ),
        (
            "pwc-cron-run-chat-synthetic-probe.timer",
            "enabled production chat requires the synthetic chat probe timer",
        ),
    )
    for timer, error in required_timers:
        enabled = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", timer],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if enabled.returncode:
            raise DeployError(error)


def frontend_feature_environment(
    environment: str, *, production_chat_enabled: bool = False
) -> dict[str, str]:
    features = profile_features(
        environment, production_chat_enabled=production_chat_enabled
    )
    return {
        "VITE_AUTH_URL": (
            "https://paperswithcode.co" if environment == "staging" else ""
        ),
        "VITE_CHAT_ENABLED": "1" if features["chat"] else "0",
        "VITE_CHAT_LIVE": "1" if features["chat"] else "0",
        # Bundle the reviewed host in enabled chat releases. Backend and worker
        # registration retain independent protected-environment kill switches.
        "VITE_CHAT_MCP_APPS_HOST_ENABLED": "1" if features["chat"] else "0",
        "VITE_NATIVE_PDF_READER_ENABLED": (
            "1" if features["native_pdf_reader"] else "0"
        ),
        "VITE_PAPER_READER_CHAT_ENABLED": (
            "1" if features["paper_reader_chat"] else "0"
        ),
        "VITE_PAPER_READER_SELECTION_ENABLED": (
            "1" if features["paper_reader_selection"] else "0"
        ),
        "VITE_CODEX_ADD_EVALS_ENABLED": ("1" if features["codex_add_evals"] else "0"),
        "VITE_CODEX_ENRICH_PAPER_ENABLED": (
            "1" if features["codex_enrich_paper"] else "0"
        ),
    }


def _protected_frontend_values(environment: str, allowed: set[str]) -> dict[str, str]:
    """Read the allowed non-empty keys from the protected environment file."""

    config_path = CONFIG_ROOT / f"{environment}.env"
    if not config_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in allowed and value.strip():
            values[key] = value.strip().strip('"').strip("'")
    return values


def frontend_host_environment(environment: str) -> dict[str, str]:
    """Return host-only frontend build settings, such as origin host aliases.

    Hostnames that would reveal the origin server stay in the protected
    environment file instead of the repository.
    """

    return _protected_frontend_values(environment, {"VITE_INTERNAL_HOST_ALIASES"})


def frontend_analytics_environment(environment: str) -> dict[str, str]:
    """Return optional browser-analytics settings for a frontend build.

    The project token is intentionally kept in the protected environment file
    rather than the repository. Vite still embeds it in the browser bundle,
    as required by PostHog's client-side SDK.
    """

    values = _protected_frontend_values(
        environment, {"VITE_POSTHOG_PROJECT_TOKEN", "VITE_POSTHOG_HOST"}
    )
    if "VITE_POSTHOG_PROJECT_TOKEN" not in values:
        return {}
    values.setdefault("VITE_POSTHOG_HOST", "https://eu.i.posthog.com")
    if not values["VITE_POSTHOG_HOST"].startswith("https://"):
        raise DeployError("VITE_POSTHOG_HOST must use HTTPS")
    return values


def prepare_release(sha: str, environment: str) -> Path:
    production_chat_enabled = (
        _configured_chat_enabled(environment) if environment == "production" else False
    )
    expected_features = profile_features(
        environment, production_chat_enabled=production_chat_enabled
    )
    target = RELEASES / release_id(sha, environment)
    if target.exists():
        make_release_readable(target)
        manifest = validate_manifest(target, environment)
        if manifest["backend_features"] != expected_features:
            raise DeployError(
                "existing immutable release does not match protected chat activation "
                "configuration; use a new exact source SHA"
            )
        return target
    check_capacity()
    RELEASES.mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(prefix="pwc-build-", dir=APP_ROOT))
    source = build_root / "source"
    source.mkdir()
    try:
        _extract_commit(sha, source)
        frontend = source / "frontend"
        build_home = build_root / "home"
        build_home.mkdir()
        # npm lifecycle scripts and the Vite config are release code: build as
        # the unprivileged build user with a private HOME and npm cache instead
        # of root's environment.
        build_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(build_home),
            "LANG": "C.UTF-8",
            "npm_config_cache": str(build_root / "npm-cache"),
            "npm_config_update_notifier": "false",
        }
        build_env.update(
            frontend_feature_environment(
                environment,
                production_chat_enabled=production_chat_enabled,
            )
        )
        build_env.update(frontend_analytics_environment(environment))
        build_env.update(frontend_host_environment(environment))
        build_sandbox.lend(build_root)
        try:
            run(build_sandbox.command(["npm", "ci"]), cwd=frontend, env=build_env)
            run(
                build_sandbox.command(
                    ["npm", "run", "build", "--", "--mode", environment]
                ),
                cwd=frontend,
                env=build_env,
            )
            descriptor = _chat_descriptor_from_source(
                source, environment, chat_enabled=expected_features["chat"]
            )
        finally:
            build_sandbox.reclaim(build_root)
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
        manifest = build_manifest(
            sha,
            environment,
            chat_descriptor=descriptor,
            production_chat_enabled=production_chat_enabled,
        )
        manifest_path = source / "release.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        if environment in {"staging", "production"}:
            manifest["external_pi_runtime"] = external_pi_runtime_descriptor(source)
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        validate_manifest(source, environment)
        os.replace(source, target)
        make_release_readable(target)
        return target
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def make_release_readable(release: Path) -> None:
    for path in sorted(release.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o555)
            continue
        executable = bool(path.stat().st_mode & 0o111)
        path.chmod(0o555 if executable else 0o444)
    release.chmod(0o555)


def sync_runtime(release: Path) -> bool:
    wanted = sha256_file(release / "uv.lock")
    current = RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else ""
    if current == wanted and (VENV / "bin" / "python").is_file():
        make_runtime_readable()
        return False
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(VENV)
    previous_umask = os.umask(0o022)
    try:
        run(["uv", "sync", "--frozen", "--project", str(release)], env=env)
    finally:
        os.umask(previous_umask)
    make_runtime_readable()
    RUNTIME_LOCK.write_text(wanted + "\n", encoding="utf-8")
    return True


def sync_runtime_with_recovery(release: Path, previous_lock_hash: str) -> bool:
    try:
        return sync_runtime(release)
    except (subprocess.CalledProcessError, OSError):
        if previous_lock_hash:
            restore_runtime(previous_lock_hash)
        raise


def make_runtime_readable() -> None:
    config = VENV / "pyvenv.cfg"
    lines = config.read_text(encoding="utf-8").splitlines()
    home_line = next(line for line in lines if line.startswith("home = "))
    source_root = Path(home_line.split("=", 1)[1].strip()).parent
    if source_root != PYTHON_RUNTIME:
        if not PYTHON_RUNTIME.exists():
            temporary = PYTHON_RUNTIME.with_name(
                f".{PYTHON_RUNTIME.name}.new-{os.getpid()}"
            )
            shutil.copytree(source_root, temporary, symlinks=True)
            os.replace(temporary, PYTHON_RUNTIME)
        updated = [
            line.replace(str(source_root), str(PYTHON_RUNTIME)) for line in lines
        ]
        config.write_text("\n".join(updated) + "\n", encoding="utf-8")
    versioned = f"python{sys.version_info.major}.{sys.version_info.minor}"
    base_launcher = PYTHON_RUNTIME / "bin" / versioned
    for name in ("python", "python3", versioned):
        launcher = VENV / "bin" / name
        launcher.unlink(missing_ok=True)
        launcher.symlink_to(base_launcher)
    for path in VENV.rglob("*"):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode | (0o555 if path.is_dir() else 0o444))
    VENV.chmod(VENV.stat().st_mode | 0o555)


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
                make_runtime_readable()
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


def candidate_start_command(
    release: Path,
    environment: str,
    manifest: dict,
    port: int,
    unit: str,
) -> list[str]:
    user = f"pwc-{environment}"
    return [
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
        "/usr/bin/env",
        f"UVICORN_PORT={port}",
        f"PWC_PORT={port}",
        f"PWC_RELEASE_ID={manifest['release_id']}",
        f"PWC_FRONTEND_DIST_DIR={release / 'frontend-dist'}",
        f"PWC_CHAT_ENABLED={'true' if manifest['backend_features']['chat'] else 'false'}",
        (
            "PWC_CODEX_ADD_EVALS_ENABLED="
            f"{'true' if manifest['backend_features'].get('codex_add_evals', False) else 'false'}"
        ),
        (
            "PWC_CODEX_ENRICH_PAPER_ENABLED="
            f"{'true' if manifest['backend_features'].get('codex_enrich_paper', False) else 'false'}"
        ),
        (
            "PWC_CODEX_JOBS_ENABLED="
            f"{'true' if manifest['backend_features'].get('codex_add_evals', False) or manifest['backend_features'].get('codex_enrich_paper', False) else 'false'}"
        ),
        str(VENV / "bin" / "python"),
        str(release / "deploy" / "run_backend.py"),
    ]


def qualify(release: Path, environment: str) -> None:
    manifest = validate_manifest(release, environment)
    port = free_candidate_port()
    unit = f"pwc-candidate-{environment}-{os.getpid()}"
    command = candidate_start_command(release, environment, manifest, port, unit)
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


def wait_for_release(environment: str, expected_release: str) -> bool:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        ready = _read_json(f"http://127.0.0.1:{PORTS[environment]}/internal/ready")
        if ready and ready.get("release_id") == expected_release:
            return True
        time.sleep(0.5)
    return False


def smoke_public(release: Path, environment: str, expected_release: str) -> None:
    immutable_python = (
        RUNTIMES / runtime_id(release) / "bin" / "python"
        if (release / "uv.lock").is_file()
        else Path()
    )
    python = immutable_python if immutable_python.is_file() else VENV / "bin" / "python"
    run(
        [
            str(python),
            str(Path(__file__).resolve().parent / "smoke_test.py"),
            "--environment",
            environment,
            "--base-url",
            PUBLIC_URLS[environment],
            "--expected-release",
            expected_release,
            "--release-dir",
            str(release),
            *(
                [
                    "--gateway-url",
                    "https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway",
                ]
                if environment == "staging"
                else []
            ),
        ]
    )


@contextmanager
def deployment_lock():
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    with DEPLOY_LOCK.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _slots_root(environment: str) -> Path:
    return ENVIRONMENTS_ROOT / environment / "slots"


def _slot_root(environment: str, slot: str) -> Path:
    return _slots_root(environment) / slot


def _slot_socket(environment: str, slot: str) -> Path:
    return Path(f"/run/paperswithcode/{environment}-{slot}.sock")


def _slot_unit(environment: str, slot: str, kind: str = "service") -> str:
    return f"paperswithcode-{environment}-backend@{slot}.{kind}"


def _active_slot(environment: str) -> str | None:
    link = ENVIRONMENTS_ROOT / environment / "active"
    if not link.is_symlink():
        return None
    target = link.resolve(strict=False)
    for slot in ("blue", "green"):
        if target == _slot_root(environment, slot).resolve(strict=False):
            return slot
    raise DeployError(f"{environment} active pointer has an invalid target")


def _nginx_uses_active_slot(environment: str) -> bool:
    result = subprocess.run(
        ["nginx", "-T"],
        text=True,
        capture_output=True,
        check=False,
    )
    expected = (
        "server unix:/srv/paperswithcode/environments/"
        f"{environment}/active/backend.sock;"
    )
    return result.returncode == 0 and expected in result.stdout


def _slot_release(environment: str, slot: str) -> Path | None:
    link = _slot_root(environment, slot) / "release"
    return link.resolve(strict=False) if link.is_symlink() else None


def _unix_json(
    environment: str,
    slot: str,
    path: str,
    *,
    method: str = "GET",
    timeout: int = 5,
    check: bool = True,
) -> dict | None:
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout),
        "--unix-socket",
        str(_slot_socket(environment, slot)),
        "--request",
        method,
        "http://localhost" + path,
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        if check:
            raise DeployError(
                f"{environment}/{slot} socket request failed: {result.stderr.strip()}"
            )
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        if check:
            raise DeployError(f"{environment}/{slot} returned invalid JSON") from exc
        return None
    return value if isinstance(value, dict) else None


def _wait_slot(
    environment: str,
    slot: str,
    manifest: dict,
    runtime: Path,
    *,
    accepting: bool | None = True,
) -> dict:
    deadline = time.monotonic() + 60
    last = None
    while time.monotonic() < deadline:
        last = _unix_json(
            environment,
            slot,
            "/internal/deployment-status",
            check=False,
        )
        if (
            last
            and last.get("release_id") == manifest["release_id"]
            and last.get("runtime_id") == runtime.name
            and last.get("slot") == slot
            and (
                accepting is None or bool(last.get("accepting_chat_turns")) is accepting
            )
        ):
            health = _unix_json(environment, slot, "/health", check=False)
            if health and health.get("release_id") == manifest["release_id"]:
                return last
        time.sleep(0.25)
    raise DeployError(
        f"{environment}/{slot} failed exact release/runtime/slot readiness: {last!r}"
    )


def _smoke_slot_candidate(
    environment: str,
    slot: str,
    release: Path,
    runtime: Path,
    manifest: dict,
) -> None:
    run(
        [
            str(runtime / "bin" / "python"),
            str(Path(__file__).resolve().parent / "smoke_test.py"),
            "--environment",
            environment,
            "--base-url",
            "http://localhost",
            "--expected-release",
            manifest["release_id"],
            "--release-dir",
            str(release),
            "--candidate",
            "--unix-socket",
            str(_slot_socket(environment, slot)),
        ]
    )


def _write_journal(environment: str, phase: str, **values: object) -> None:
    root = ENVIRONMENTS_ROOT / environment
    root.mkdir(parents=True, exist_ok=True)
    target = root / "activation-journal.json"
    temporary = target.with_name(f".{target.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "environment": environment,
                "phase": phase,
                **values,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _journal(environment: str) -> dict | None:
    path = ENVIRONMENTS_ROOT / environment / "activation-journal.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _start_recovery_slot(environment: str, slot: str, release: Path) -> None:
    """Start a rollback target and wait until its control endpoint is ready."""

    run(["systemctl", "start", _slot_unit(environment, slot, "socket")])
    run(["systemctl", "start", _slot_unit(environment, slot)])
    expected_release = validate_manifest(release, environment)["release_id"]
    deadline = time.monotonic() + 60
    last = None
    while time.monotonic() < deadline:
        last = _unix_json(
            environment,
            slot,
            "/internal/deployment-status",
            check=False,
        )
        if (
            last
            and last.get("release_id") == expected_release
            and last.get("slot") == slot
        ):
            health = _unix_json(environment, slot, "/health", check=False)
            if health and health.get("release_id") == expected_release:
                return
        time.sleep(0.25)
    raise DeployError(
        f"{environment}/{slot} rollback target failed readiness: {last!r}"
    )


def _recover_interrupted_activation(environment: str) -> None:
    """Conservatively restore the old slot if cutover smoke was interrupted."""

    journal = _journal(environment)
    if not journal:
        return
    if journal.get("phase") in {
        "live-with-old-slot-draining",
        "live-with-old-external-pi-draining",
    } and external_pi_lifecycle_enabled(environment):
        # The displaced slot's external Pi keeps running until pwc-reap. Finish
        # that reap now, with the slot's own release, so the next activation
        # never starts or cleans up this slot while its old supervisor runs.
        active_slot = _active_slot(environment)
        draining_slot = journal.get("draining_slot")
        if draining_slot not in {"blue", "green"} or draining_slot == active_slot:
            raise DeployError("activation journal cannot identify its draining slot")
        if _reap_draining_slot(environment, draining_slot) is not None:
            raise DeployError(
                f"{environment}/{draining_slot} is still draining from the previous "
                "activation; run pwc-reap once its streams finish"
            )
        _write_settled_journal(environment, active_slot)
        return
    if journal.get("phase") in {"candidate-preparing", "candidate-prepared"}:
        candidate_slot = journal.get("candidate_slot")
        candidate_release_name = journal.get("candidate_release")
        if candidate_slot not in {"blue", "green"} or not isinstance(
            candidate_release_name, str
        ):
            raise DeployError("activation journal cannot identify its candidate")
        if _active_slot(environment) == candidate_slot:
            raise DeployError(
                "activation journal candidate slot is already active; "
                "refusing abandoned-candidate cleanup"
            )
        candidate_release = RELEASES / candidate_release_name
        candidate_manifest = validate_manifest(candidate_release, environment)
        pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
        validated_orphan_release_ids = frozenset(
            validate_manifest(release, environment)["release_id"]
            for release in (pointers.current, pointers.previous)
            if release is not None
        )
        _unix_json(
            environment, candidate_slot, "/internal/drain", method="POST", check=False
        )
        if not _stop_drained_slot(environment, candidate_slot):
            raise DeployError("abandoned candidate backend has not finished draining")
        stop_slot_if_enabled(
            environment,
            candidate_slot,
            candidate_manifest["release_id"],
            validated_orphan_release_ids=validated_orphan_release_ids,
            allow_orphaned_turn_reap=True,
        )
        _write_journal(
            environment,
            "candidate-abandoned",
            candidate_slot=candidate_slot,
            candidate_release=candidate_release_name,
        )
        return
    if journal.get("phase") not in {
        "previous-update-pending",
        "current-update-pending",
        "active-switch-pending",
        "active-switched-smoke-pending",
        "automatic-rollback-in-progress",
    }:
        return
    root = ENVIRONMENTS_ROOT / environment
    old_slot = journal.get("old_slot")
    old_release_name = journal.get("old_release")
    if old_slot not in {"blue", "green"} or not isinstance(old_release_name, str):
        raise DeployError("activation journal cannot identify its rollback target")
    old_release = RELEASES / old_release_name
    validate_manifest(old_release, environment)
    original_previous_name = journal.get("original_previous")
    original_previous = (
        RELEASES / original_previous_name
        if isinstance(original_previous_name, str)
        else None
    )
    _write_journal(
        environment,
        "automatic-rollback-in-progress",
        old_slot=old_slot,
        old_release=old_release.name,
        original_previous=(
            original_previous.name if original_previous is not None else None
        ),
        interrupted_phase=journal["phase"],
    )
    _start_recovery_slot(environment, old_slot, old_release)
    atomic_symlink(_slot_root(environment, old_slot), root / "active")
    atomic_symlink(old_release, root / "current")
    if original_previous:
        atomic_symlink(original_previous, root / "previous")
    else:
        (root / "previous").unlink(missing_ok=True)
    _unix_json(environment, old_slot, "/internal/undrain", method="POST")
    candidate_slot = "green" if old_slot == "blue" else "blue"
    candidate_release = _slot_release(environment, candidate_slot)
    if candidate_release is not None:
        candidate_manifest = validate_manifest(candidate_release, environment)
        stop_slot_if_enabled(
            environment, candidate_slot, candidate_manifest["release_id"]
        )
    prepare_candidate_if_enabled(
        environment,
        old_slot,
        validate_manifest(old_release, environment)["release_id"],
    )
    smoke_public(
        old_release,
        environment,
        validate_manifest(old_release, environment)["release_id"],
    )
    _persist_active_slot_socket(environment, old_slot)
    _write_journal(
        environment,
        "automatic-rollback-complete",
        active_slot=old_slot,
        restored_release=old_release.name,
        interrupted_phase=journal["phase"],
    )


def _prepare_slot(environment: str, slot: str, release: Path, runtime: Path) -> dict:
    existing = _unix_json(environment, slot, "/internal/deployment-status", check=False)
    if existing:
        busy = (
            int(existing.get("active_http_requests", 0))
            + int(existing.get("active_chat_streams", 0))
            + int(existing.get("active_gateway_streams", 0))
        )
        if busy:
            raise DeployError(
                f"inactive slot {slot} is still draining with {busy} streams"
            )
    subprocess.run(["systemctl", "stop", _slot_unit(environment, slot)], check=False)
    subprocess.run(
        ["systemctl", "stop", _slot_unit(environment, slot, "socket")], check=False
    )
    subprocess.run(
        ["systemctl", "reset-failed", _slot_unit(environment, slot)], check=False
    )
    subprocess.run(
        ["systemctl", "reset-failed", _slot_unit(environment, slot, "socket")],
        check=False,
    )
    slot_root = _slot_root(environment, slot)
    slot_root.mkdir(parents=True, exist_ok=True)
    socket_link = slot_root / "backend.sock"
    if not socket_link.is_symlink():
        socket_link.unlink(missing_ok=True)
        socket_link.symlink_to(_slot_socket(environment, slot))
    atomic_symlink(release, slot_root / "release")
    try:
        run(["systemctl", "start", _slot_unit(environment, slot, "socket")])
        run(["systemctl", "start", _slot_unit(environment, slot)])
        manifest = validate_manifest(release, environment)
        _wait_slot(environment, slot, manifest, runtime, accepting=None)
        _unix_json(environment, slot, "/internal/undrain", method="POST")
        status_value = _wait_slot(environment, slot, manifest, runtime)
        _smoke_slot_candidate(environment, slot, release, runtime, manifest)
        return status_value
    except (DeployError, subprocess.CalledProcessError, OSError):
        subprocess.run(
            ["systemctl", "stop", _slot_unit(environment, slot)], check=False
        )
        subprocess.run(
            ["systemctl", "stop", _slot_unit(environment, slot, "socket")],
            check=False,
        )
        subprocess.run(
            ["systemctl", "reset-failed", _slot_unit(environment, slot)],
            check=False,
        )
        subprocess.run(
            ["systemctl", "reset-failed", _slot_unit(environment, slot, "socket")],
            check=False,
        )
        raise


def _prepare_or_reuse_slot(
    environment: str,
    slot: str,
    release: Path,
    runtime: Path,
) -> dict:
    """Reuse an exact draining rollback target; rebuild any stale idle slot."""

    manifest = validate_manifest(release, environment)
    existing = _unix_json(
        environment,
        slot,
        "/internal/deployment-status",
        check=False,
    )
    exact = bool(
        existing
        and _slot_release(environment, slot) == release
        and existing.get("release_id") == manifest["release_id"]
        and existing.get("runtime_id") == runtime.name
        and existing.get("slot") == slot
    )
    if not exact:
        return _prepare_slot(environment, slot, release, runtime)
    if not existing.get("accepting_chat_turns"):
        _unix_json(environment, slot, "/internal/undrain", method="POST")
    status_value = _wait_slot(environment, slot, manifest, runtime)
    _smoke_slot_candidate(environment, slot, release, runtime, manifest)
    return status_value


def _prepare_qualified_slot(
    environment: str,
    slot: str,
    release: Path,
    runtime: Path,
) -> dict:
    """Prepare both backend and guarded external Pi candidate lifecycles."""
    external_pi_lifecycle_enabled(environment)
    status_value = _prepare_slot(environment, slot, release, runtime)
    prepare_candidate_if_enabled(
        environment,
        slot,
        validate_manifest(release, environment)["release_id"],
    )
    return status_value


def _bridge_qualify_current(release: Path, environment: str, runtime: Path) -> None:
    pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
    if pointers.current != release:
        raise DeployError(
            "the one-time slot bridge must qualify the unchanged current release"
        )
    if _active_slot(environment) is not None:
        raise DeployError("the slot bridge is already prepared")
    slot = "blue"
    external_pi_lifecycle_enabled(environment)
    _write_journal(
        environment,
        "candidate-preparing",
        candidate_slot=slot,
        candidate_release=release.name,
        legacy_current=release.name,
    )
    _prepare_slot(environment, slot, release, runtime)
    prepare_candidate_if_enabled(
        environment,
        slot,
        validate_manifest(release, environment)["release_id"],
    )
    _write_journal(
        environment,
        "candidate-prepared",
        candidate_slot=slot,
        candidate_release=release.name,
        rollback_topology="legacy fixed-port service and current/previous pointers",
    )
    atomic_symlink(
        _slot_root(environment, slot), ENVIRONMENTS_ROOT / environment / "active"
    )
    _write_journal(
        environment,
        "bridge-awaiting-nginx",
        active_slot=slot,
        candidate_release=release.name,
        rollback_topology="nginx still routes to the unchanged legacy fixed port",
    )


def _drain_report_seconds(environment: str) -> float:
    configured = os.environ.get("PWC_DEPLOY_DRAIN_REPORT_SECONDS", "15")
    return max(0.0, min(float(configured), 60.0))


def _drain_deadline_seconds(environment: str) -> float:
    values = {
        "PWC_CHAT_TIMEOUT_SECONDS": 180.0,
        "PWC_CHAT_AGENT_TIMEOUT_SECONDS": 180.0,
    }
    config = CONFIG_ROOT / f"{environment}.env"
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            key, separator, raw = line.partition("=")
            if separator and key in values:
                try:
                    values[key] = float(raw.strip().strip("\"'"))
                except ValueError:
                    raise DeployError(f"{key} must be numeric for drain calculation")
    return max(values.values()) + 60


def _stop_drained_slot(environment: str, slot: str) -> bool:
    status = _unix_json(environment, slot, "/internal/deployment-status", check=False)
    if not status:
        return True
    if status.get("accepting_chat_turns"):
        return False
    if (
        int(status.get("active_http_requests", 0))
        or int(status.get("active_chat_streams", 0))
        or int(status.get("active_gateway_streams", 0))
    ):
        return False
    run(["systemctl", "stop", _slot_unit(environment, slot)])
    run(["systemctl", "stop", _slot_unit(environment, slot, "socket")])
    return True


def _retire_legacy_service(environment: str) -> bool:
    """Disable the fixed-port owner only after nginx selects the active slot."""

    if not _nginx_uses_active_slot(environment):
        return False
    unit = _unit(environment)
    state = _systemctl_state(unit)
    enabled_state = _systemctl_enabled_state(unit)
    if state == "inactive" and enabled_state == "disabled":
        return False
    run(["systemctl", "disable", "--now", unit])
    state = _systemctl_state(unit)
    if state != "inactive":
        raise DeployError(f"legacy service {unit} did not stop cleanly: {state}")
    enabled_state = _systemctl_enabled_state(unit)
    if enabled_state != "disabled":
        raise DeployError(
            f"legacy service {unit} remains enabled after retirement: {enabled_state}"
        )
    log_event("legacy-retire", environment, "success", unit=unit)
    return True


def _persist_active_slot_socket(environment: str, slot: str) -> None:
    """Make the selected socket, and only that socket, survive a host reboot."""

    inactive = "green" if slot == "blue" else "blue"
    run(["systemctl", "enable", _slot_unit(environment, slot, "socket")])
    run(["systemctl", "disable", _slot_unit(environment, inactive, "socket")])


def activate_slot(
    release: Path,
    environment: str,
    runtime: Path,
    *,
    refresh_environment: bool = False,
) -> str:
    root = ENVIRONMENTS_ROOT / environment
    active = _active_slot(environment)
    if active is None:
        raise DeployError(
            "slot topology is not active; qualify the current bridge release and "
            "apply the separately authorized nginx migration first"
        )
    old_release = _slot_release(environment, active)
    pointers = read_pointers(root)
    if not old_release or pointers.current != old_release:
        raise DeployError("active slot and current release pointer disagree")
    if refresh_environment and old_release != release:
        raise DeployError("--refresh-environment requires the active release")
    if old_release == release and not refresh_environment:
        _wait_slot(
            environment,
            active,
            validate_manifest(release, environment),
            runtime,
        )
        smoke_public(release, environment, validate_manifest(release)["release_id"])
        _persist_active_slot_socket(environment, active)
        _write_journal(
            environment,
            "settled",
            active_slot=active,
            active_release=release.name,
            previous_release=(
                pointers.previous.name if pointers.previous is not None else None
            ),
            forced_termination_count=0,
        )
        return "success"
    inactive = "green" if active == "blue" else "blue"
    original_previous = pointers.previous
    preserved_previous = original_previous if refresh_environment else old_release
    candidate_manifest = validate_manifest(release, environment)
    active_manifest = validate_manifest(old_release, environment)
    external_pi_enabled = external_pi_lifecycle_enabled(environment)
    validate_rolling_compatibility(active_manifest, candidate_manifest)
    _write_journal(
        environment,
        "candidate-preparing",
        active_slot=active,
        candidate_slot=inactive,
        active_release=old_release.name,
        candidate_release=release.name,
    )
    if refresh_environment:
        _prepare_slot(environment, inactive, release, runtime)
    else:
        _prepare_or_reuse_slot(environment, inactive, release, runtime)
    prepare_candidate_if_enabled(
        environment, inactive, candidate_manifest["release_id"]
    )
    _write_journal(
        environment,
        "candidate-prepared",
        active_slot=active,
        candidate_slot=inactive,
        active_release=old_release.name,
        candidate_release=release.name,
    )
    _write_journal(
        environment,
        "previous-update-pending",
        active_slot=active,
        candidate_slot=inactive,
        previous_release=(
            preserved_previous.name if preserved_previous is not None else None
        ),
        old_slot=active,
        old_release=old_release.name,
        original_previous=(
            original_previous.name if original_previous is not None else None
        ),
    )
    if not refresh_environment:
        atomic_symlink(old_release, root / "previous")
    _write_journal(
        environment,
        "current-update-pending",
        active_slot=active,
        candidate_slot=inactive,
        current_release=release.name,
        old_slot=active,
        old_release=old_release.name,
        original_previous=(
            original_previous.name if original_previous is not None else None
        ),
    )
    atomic_symlink(release, root / "current")
    _write_journal(
        environment,
        "active-switch-pending",
        active_slot=active,
        candidate_slot=inactive,
        old_slot=active,
        old_release=old_release.name,
        original_previous=(
            original_previous.name if original_previous is not None else None
        ),
    )
    old_status = (
        _unix_json(
            environment,
            active,
            "/internal/deployment-status",
            check=False,
        )
        or {}
    )
    streams_surviving_cutover = {
        "active_http_requests": int(old_status.get("active_http_requests", 0)),
        "active_chat_streams": int(old_status.get("active_chat_streams", 0)),
        "active_gateway_streams": int(old_status.get("active_gateway_streams", 0)),
    }
    atomic_symlink(_slot_root(environment, inactive), root / "active")
    _write_journal(
        environment,
        "active-switched-smoke-pending",
        active_slot=inactive,
        draining_slot=active,
        active_release=release.name,
        previous_release=(
            preserved_previous.name if preserved_previous is not None else None
        ),
        old_slot=active,
        old_release=old_release.name,
        original_previous=(
            original_previous.name if original_previous is not None else None
        ),
        streams_surviving_cutover=streams_surviving_cutover,
        forced_termination_count=0,
    )
    try:
        smoke_public(release, environment, candidate_manifest["release_id"])
        _persist_active_slot_socket(environment, inactive)
    except (
        DeployError,
        ExternalPiSlotError,
        subprocess.CalledProcessError,
        OSError,
    ) as exc:
        _write_journal(
            environment,
            "automatic-rollback-in-progress",
            old_slot=active,
            old_release=old_release.name,
            original_previous=(
                original_previous.name if original_previous is not None else None
            ),
        )
        _start_recovery_slot(environment, active, old_release)
        atomic_symlink(_slot_root(environment, active), root / "active")
        atomic_symlink(old_release, root / "current")
        if original_previous:
            atomic_symlink(original_previous, root / "previous")
        else:
            (root / "previous").unlink(missing_ok=True)
        _unix_json(environment, active, "/internal/undrain", method="POST")
        candidate_drain_error = None
        try:
            stop_slot_if_enabled(
                environment, inactive, candidate_manifest["release_id"]
            )
        except ExternalPiSlotError as error:
            candidate_drain_error = error
        prepare_candidate_if_enabled(environment, active, active_manifest["release_id"])
        smoke_public(old_release, environment, active_manifest["release_id"])
        _persist_active_slot_socket(environment, active)
        if candidate_drain_error is not None:
            _write_journal(
                environment,
                "automatic-rollback-candidate-drain-failed",
                active_slot=active,
                restored_release=old_release.name,
                failed_release=release.name,
            )
            raise DeployError(
                "prior activation was restored but candidate drain failed"
            ) from candidate_drain_error
        _write_journal(
            environment,
            "automatic-rollback-complete",
            active_slot=active,
            restored_release=old_release.name,
            failed_release=release.name,
        )
        raise DeployError("live smoke failed; prior activation was restored") from exc
    drain_started = time.monotonic()
    drained = _unix_json(environment, active, "/internal/drain", method="POST")
    drain_deadline = _drain_deadline_seconds(environment)
    _write_journal(
        environment,
        "live-with-old-slot-draining",
        active_slot=inactive,
        draining_slot=active,
        active_release=release.name,
        draining_release=old_release.name,
        drain_deadline_seconds=drain_deadline,
        drain_started_at=drained.get("drain_started_at") if drained else None,
        streams_surviving_cutover=streams_surviving_cutover,
        forced_termination_count=0,
    )
    reporting_deadline = time.monotonic() + _drain_report_seconds(environment)
    while time.monotonic() < reporting_deadline:
        if _stop_drained_slot(environment, active):
            if external_pi_enabled:
                _write_journal(
                    environment,
                    "live-with-old-external-pi-draining",
                    active_slot=inactive,
                    draining_slot=active,
                    active_release=release.name,
                    draining_release=old_release.name,
                    streams_surviving_cutover=streams_surviving_cutover,
                    forced_termination_count=0,
                )
                return "success-with-draining"
            _write_journal(
                environment,
                "settled",
                active_slot=inactive,
                active_release=release.name,
                previous_release=(
                    preserved_previous.name if preserved_previous is not None else None
                ),
                drain_duration_seconds=round(time.monotonic() - drain_started, 3),
                streams_surviving_cutover=streams_surviving_cutover,
                forced_termination_count=0,
            )
            return "success"
        time.sleep(0.5)
    return "success-with-draining"


def activate(
    release: Path,
    environment: str,
    *,
    previous_runtime_lock: str = "",
    defer_public_smoke: bool = False,
) -> None:
    root = ENVIRONMENTS_ROOT / environment
    pointers = read_pointers(root)
    if pointers.current == release:
        manifest = validate_manifest(release, environment)
        if not wait_for_release(environment, manifest["release_id"]):
            raise DeployError("active release failed readiness")
        if not defer_public_smoke:
            smoke_public(release, environment, manifest["release_id"])
        return
    if pointers.current:
        atomic_symlink(pointers.current, root / "previous")
    atomic_symlink(release, root / "current")
    try:
        run(["systemctl", "restart", _unit(environment)])
        manifest = validate_manifest(release, environment)
        if not wait_for_release(environment, manifest["release_id"]):
            raise DeployError("live readiness failed")
        if not defer_public_smoke:
            smoke_public(release, environment, manifest["release_id"])
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
        (root / "current").unlink(missing_ok=True)
        subprocess.run(["systemctl", "stop", _unit(environment)], check=False)
        log_event(
            "automatic-rollback",
            environment,
            "initial-activation-removed",
            failed_release=failed.name,
        )
        return
    atomic_symlink(pointers.previous, root / "current")
    if previous_runtime_lock:
        restore_runtime(previous_runtime_lock)
    run(["systemctl", "restart", _unit(environment)])
    restored = validate_manifest(pointers.previous, environment)
    if not wait_for_release(environment, restored["release_id"]):
        raise DeployError("automatic rollback target failed readiness")
    smoke_public(pointers.previous, environment, restored["release_id"])
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
        protected.update(protected_environment_release_paths(environment))
    return protected


def protected_environment_release_paths(environment: str) -> set[Path]:
    protected = set()
    pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
    protected.update(path for path in (pointers.current, pointers.previous) if path)
    for slot in ("blue", "green"):
        release = _slot_release(environment, slot)
        if release:
            protected.add(release)
    return protected


def protected_runtime_ids() -> set[str]:
    protected: set[str] = set()
    for release in protected_release_paths():
        lock = release / "uv.lock"
        if lock.is_file():
            protected.add(sha256_file(lock))
    return protected


def protected_external_pi_runtime_ids() -> set[str]:
    protected: set[str] = set()
    has_legacy_release = False
    for environment in ("staging", "production"):
        for release in protected_environment_release_paths(environment):
            recorded = recorded_external_pi_runtime_id(release)
            if recorded is not None:
                protected.add(recorded)
                continue
            if environment != "staging":
                continue
            has_legacy_release = True
            try:
                protected.add(external_pi_runtime_id(release))
            except ValueError:
                # Older protected releases predate the external Pi package inputs.
                continue
    if has_legacy_release:
        protected.add(RETAIN_ALL_RUNTIMES)
    return protected


def _protected_python_runtime_ids() -> set[str]:
    return protected_runtime_ids() | {EXTERNAL_PI_RUNTIMES.name}


def cleanup_releases() -> None:
    protected = protected_release_paths()
    for release in RELEASES.iterdir():
        if release.is_dir() and release.resolve() not in protected:
            shutil.rmtree(release)


def cleanup_command(args: argparse.Namespace) -> int:
    require_root()
    if args.confirm != "CLEAN_RELEASES":
        raise DeployError("cleanup requires --confirm CLEAN_RELEASES")
    with deployment_lock():
        if getattr(args, "component", "site") == "mcp":
            mcp_release.cleanup_releases()
            print(json.dumps(mcp_release.status(), indent=2))
            return 0
        protected = protected_release_paths()
        targets = [
            path
            for path in RELEASES.iterdir()
            if path.is_dir() and path.resolve() not in protected
        ]
        runtime_targets = (
            [
                path.name
                for path in RUNTIMES.iterdir()
                if path.is_dir()
                and not path.name.startswith(".")
                and path.name not in _protected_python_runtime_ids()
            ]
            if RUNTIMES.is_dir()
            else []
        )
        protected_external_runtimes = protected_external_pi_runtime_ids()
        print(
            json.dumps(
                {
                    "remove_releases": [path.name for path in targets],
                    "remove_runtimes": runtime_targets,
                    "remove_external_pi_runtimes": [
                        path.name
                        for path in EXTERNAL_PI_RUNTIMES.iterdir()
                        if path.is_dir()
                        and not path.name.startswith(".")
                        and RETAIN_ALL_RUNTIMES not in protected_external_runtimes
                        and path.name not in protected_external_runtimes
                    ]
                    if EXTERNAL_PI_RUNTIMES.is_dir()
                    else [],
                },
                indent=2,
            )
        )
        for path in targets:
            shutil.rmtree(path)
        cleanup_runtimes(RUNTIMES, _protected_python_runtime_ids())
        cleanup_external_pi_runtimes(
            EXTERNAL_PI_RUNTIMES, protected_external_pi_runtime_ids()
        )
    return 0


def deploy(args: argparse.Namespace) -> int:
    require_root()
    if args.environment == "production" and args.confirm != "DEPLOY_PRODUCTION":
        raise DeployError("production requires --confirm DEPLOY_PRODUCTION")
    if getattr(args, "component", "site") == "mcp":
        with deployment_lock():
            result = mcp_release.deploy(
                args.source,
                args.environment,
                qualify_only=args.qualify_only,
            )
        print(json.dumps(result, indent=2))
        return 0
    if args.defer_public_smoke:
        raise DeployError(
            "--defer-public-smoke is retired; slot activation has no listener gap"
        )
    if args.refresh_environment and (args.qualify_only or args.legacy_bridge):
        raise DeployError(
            "--refresh-environment cannot be combined with --qualify-only or "
            "--legacy-bridge"
        )
    with deployment_lock():
        _recover_interrupted_activation(args.environment)
        require_production_chat_monitor(args.environment)
        sha = resolve_sha(args.source, args.environment)
        release = prepare_release(sha, args.environment)
        if args.legacy_bridge:
            if args.qualify_only:
                raise DeployError(
                    "--legacy-bridge and --qualify-only are mutually exclusive"
                )
            if _active_slot(args.environment) is not None or _nginx_uses_active_slot(
                args.environment
            ):
                raise DeployError(
                    "--legacy-bridge is forbidden after active-slot migration"
                )
            installed_lock = (
                RUNTIME_LOCK.read_text().strip() if RUNTIME_LOCK.is_file() else ""
            )
            candidate_lock = sha256_file(release / "uv.lock")
            if (
                not installed_lock
                or installed_lock != candidate_lock
                or not (VENV / "bin" / "python").is_file()
            ):
                raise DeployError(
                    "--legacy-bridge cannot change the shared Python runtime"
                )
            qualify(release, args.environment)
            activate(release, args.environment)
            cleanup_releases()
            log_event(
                "deploy-legacy-bridge",
                args.environment,
                "success",
                git_sha=sha,
                source=args.source,
                runtime_id=f"legacy-shared:{installed_lock}",
            )
            print(
                f"deployed {args.source} ({sha}) to {args.environment}: legacy-bridge"
            )
            return 0
        runtime, runtime_built = prepare_runtime(release, RUNTIMES)
        external_pi_runtime = None
        external_pi_runtime_built = False
        if external_pi_lifecycle_enabled(args.environment):
            external_pi_runtime, external_pi_runtime_built = (
                prepare_external_pi_runtime(release, EXTERNAL_PI_RUNTIMES)
            )
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
                    "candidate_runtime": runtime.name,
                    "runtime_built": runtime_built,
                    "external_pi_runtime": (
                        external_pi_runtime.name if external_pi_runtime else None
                    ),
                    "external_pi_runtime_built": external_pi_runtime_built,
                    "features": validate_manifest(release, args.environment)[
                        "backend_features"
                    ],
                    "active_slot": _active_slot(args.environment),
                },
                indent=2,
            )
        )
        if args.qualify_only:
            if _active_slot(args.environment) is None:
                _bridge_qualify_current(release, args.environment, runtime)
                result = "bridge-awaiting-nginx"
            else:
                active = _active_slot(args.environment)
                assert active is not None
                inactive = "green" if active == "blue" else "blue"
                active_release = _slot_release(args.environment, active)
                if not active_release:
                    raise DeployError("active slot has no release")
                validate_rolling_compatibility(
                    validate_manifest(active_release, args.environment),
                    validate_manifest(release, args.environment),
                )
                _prepare_qualified_slot(args.environment, inactive, release, runtime)
                _write_journal(
                    args.environment,
                    "candidate-prepared",
                    active_slot=active,
                    candidate_slot=inactive,
                    active_release=active_release.name,
                    candidate_release=release.name,
                )
                result = "candidate-prepared"
            log_event(
                "qualify",
                args.environment,
                result,
                git_sha=sha,
                source=args.source,
                runtime_id=runtime.name,
            )
            print(f"qualified {args.source} ({sha}) for {args.environment}: {result}")
            return 0
        if not _nginx_uses_active_slot(args.environment):
            raise DeployError(
                f"{args.environment} nginx has not crossed the explicit active-slot "
                "migration boundary"
            )
        result = activate_slot(
            release,
            args.environment,
            runtime,
            refresh_environment=args.refresh_environment,
        )
        try:
            _retire_legacy_service(args.environment)
        except (DeployError, subprocess.CalledProcessError, OSError):
            active = _active_slot(args.environment)
            _write_journal(
                args.environment,
                "legacy-retirement-pending",
                active_slot=active,
                active_release=(
                    _slot_release(args.environment, active).name
                    if active and _slot_release(args.environment, active)
                    else None
                ),
                prior_activation=_journal(args.environment),
            )
            raise
        if result == "success":
            cleanup_releases()
            cleanup_runtimes(RUNTIMES, _protected_python_runtime_ids())
            cleanup_external_pi_runtimes(
                EXTERNAL_PI_RUNTIMES, protected_external_pi_runtime_ids()
            )
        log_event(
            "deploy",
            args.environment,
            result,
            git_sha=sha,
            source=args.source,
            runtime_id=runtime.name,
        )
    print(f"deployed {args.source} ({sha}) to {args.environment}: {result}")
    return 0


def rollback(args: argparse.Namespace) -> int:
    require_root()
    if args.environment == "production" and args.confirm != "ROLLBACK_PRODUCTION":
        raise DeployError("production requires --confirm ROLLBACK_PRODUCTION")
    if getattr(args, "component", "site") == "mcp":
        with deployment_lock():
            result = mcp_release.rollback(args.environment)
        print(json.dumps(result, indent=2))
        return 0
    with deployment_lock():
        _recover_interrupted_activation(args.environment)
        root = ENVIRONMENTS_ROOT / args.environment
        pointers = read_pointers(root)
        if not pointers.previous or not pointers.current:
            raise DeployError("current and previous releases are required for rollback")
        failed_sha = getattr(args, "failed_sha", None)
        if failed_sha:
            if len(failed_sha) != 40 or any(
                character not in "0123456789abcdef" for character in failed_sha
            ):
                raise DeployError("--failed-sha requires an exact lowercase commit SHA")
            current_sha = validate_manifest(pointers.current, args.environment)[
                "git_sha"
            ]
            if current_sha != failed_sha:
                raise DeployError(
                    "rollback target changed since the failure was observed"
                )
        if _active_slot(args.environment) is None:
            target = pointers.previous
            old_current = pointers.current
            sync_runtime(target)
            atomic_symlink(target, root / "current")
            atomic_symlink(old_current, root / "previous")
            run(["systemctl", "restart", _unit(args.environment)])
            expected = validate_manifest(target, args.environment)["release_id"]
            if not wait_for_release(args.environment, expected):
                raise DeployError("legacy rollback target failed readiness")
            smoke_public(target, args.environment, expected)
            log_event(
                "rollback",
                args.environment,
                "legacy-success",
                restored_release=target.name,
            )
            print(f"rolled {args.environment} back to {target.name}: legacy-success")
            return 0
        validate_manifest(pointers.previous, args.environment)
        target = pointers.previous
        runtime, _ = prepare_runtime(target, RUNTIMES)
        if external_pi_lifecycle_enabled(args.environment):
            prepare_external_pi_runtime(target, EXTERNAL_PI_RUNTIMES)
        result = activate_slot(target, args.environment, runtime)
        log_event(
            "rollback",
            args.environment,
            result,
            restored_release=target.name,
            runtime_id=runtime.name,
        )
    print(f"rolled {args.environment} back to {target.name}: {result}")
    return 0


def _reap_draining_slot(environment: str, draining: str) -> dict | None:
    """Stop a displaced slot's drained backend, then its external Pi.

    Returns the backend status while streams remain, otherwise None.
    """

    status_value = _unix_json(
        environment,
        draining,
        "/internal/deployment-status",
        check=False,
    )
    if status_value is not None and not _stop_drained_slot(environment, draining):
        return status_value
    draining_release = _slot_release(environment, draining)
    if draining_release is None:
        raise DeployError("draining slot has no release")
    stop_slot_if_enabled(
        environment,
        draining,
        validate_manifest(draining_release, environment)["release_id"],
        allow_orphaned_turn_reap=True,
    )
    return None


def _write_settled_journal(environment: str, active: str) -> None:
    pointers = read_pointers(ENVIRONMENTS_ROOT / environment)
    _write_journal(
        environment,
        "settled",
        active_slot=active,
        active_release=pointers.current.name if pointers.current else None,
        previous_release=pointers.previous.name if pointers.previous else None,
    )


def reap(args: argparse.Namespace) -> int:
    require_root()
    with deployment_lock():
        active = _active_slot(args.environment)
        if active is None:
            raise DeployError("slot topology is not active")
        draining = "green" if active == "blue" else "blue"
        status_value = _reap_draining_slot(args.environment, draining)
        if status_value is not None:
            print(
                json.dumps(
                    {
                        "result": "still-draining",
                        "environment": args.environment,
                        "slot": draining,
                        "active_chat_streams": status_value.get(
                            "active_chat_streams", 0
                        ),
                        "active_gateway_streams": status_value.get(
                            "active_gateway_streams", 0
                        ),
                    },
                    indent=2,
                )
            )
            return 0
        _write_settled_journal(args.environment, active)
        cleanup_releases()
        cleanup_runtimes(RUNTIMES, _protected_python_runtime_ids())
        cleanup_external_pi_runtimes(
            EXTERNAL_PI_RUNTIMES, protected_external_pi_runtime_ids()
        )
    print(f"reaped drained {args.environment}/{draining} slot")
    return 0


def _systemctl_state(unit: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-active", unit], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _systemctl_enabled_state(unit: str) -> str:
    result = subprocess.run(
        ["systemctl", "is-enabled", unit], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or "unknown"


def status(args: argparse.Namespace) -> int:
    if getattr(args, "component", "site") == "mcp":
        print(json.dumps(mcp_release.status(), indent=2))
        return 0
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
            "legacy_service": _systemctl_state(_unit(environment)),
            "active_slot": _active_slot(environment),
            "nginx_active_slot": _nginx_uses_active_slot(environment),
            "slots": {},
        }
        if environment == "production":
            monitor_unit = "pwc-chat-alert-monitor.timer"
            item["chat_alert_monitor"] = {
                "enabled": _systemctl_enabled_state(monitor_unit),
                "active": _systemctl_state(monitor_unit),
            }
        for name, path in (
            ("current", pointers.current),
            ("previous", pointers.previous),
        ):
            try:
                item[name] = validate_manifest(path, environment) if path else None
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                item[name] = {"invalid": str(exc), "path": str(path)}
        for slot in ("blue", "green"):
            release = _slot_release(environment, slot)
            slot_item: dict[str, object] = {
                "release": release.name if release else None,
                "runtime_id": (
                    runtime_id(release)
                    if release and (release / "uv.lock").is_file()
                    else None
                ),
                "service": _systemctl_state(_slot_unit(environment, slot)),
                "socket": _systemctl_state(_slot_unit(environment, slot, "socket")),
            }
            live = _unix_json(
                environment,
                slot,
                "/internal/deployment-status",
                check=False,
            )
            if live:
                slot_item["deployment"] = live
            if environment in {"staging", "production"}:
                slot_item["external_pi_shadow"] = {
                    "supervisor": _systemctl_state(
                        f"paperswithcode-{environment}-external-pi@{slot}.service"
                    ),
                    "worker": _systemctl_state(
                        f"paperswithcode-{environment}-external-pi-worker@{slot}.service"
                    ),
                    "lifecycle": external_pi_slot_status(environment, slot) or None,
                }
            item["slots"][slot] = slot_item
        journal = ENVIRONMENTS_ROOT / environment / "activation-journal.json"
        item["activation_journal"] = (
            json.loads(journal.read_text(encoding="utf-8"))
            if journal.is_file()
            else None
        )
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
        parser.add_argument("--defer-public-smoke", action="store_true")
        parser.add_argument("--qualify-only", action="store_true")
        parser.add_argument("--legacy-bridge", action="store_true")
        parser.add_argument("--refresh-environment", action="store_true")
        parser.add_argument("--component", choices=("site", "mcp"), default="site")
        parser.set_defaults(handler=deploy)
    elif program.endswith("pwc-rollback"):
        parser.add_argument("environment", choices=ENVIRONMENTS)
        parser.add_argument("--failed-sha")
        parser.add_argument("--confirm")
        parser.add_argument("--component", choices=("site", "mcp"), default="site")
        parser.set_defaults(handler=rollback)
    elif program.endswith("pwc-cleanup"):
        parser.add_argument("--confirm")
        parser.add_argument("--component", choices=("site", "mcp"), default="site")
        parser.set_defaults(handler=cleanup_command)
    elif program.endswith("pwc-reap"):
        parser.add_argument("environment", choices=ENVIRONMENTS)
        parser.set_defaults(handler=reap)
    else:
        parser.add_argument("--component", choices=("site", "mcp"), default="site")
        parser.set_defaults(handler=status)
    return parser


def main() -> int:
    program = os.environ.get("PWC_DEPLOY_COMMAND", Path(sys.argv[0]).name)
    parser = parser_for(program)
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (DeployError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"{program}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
