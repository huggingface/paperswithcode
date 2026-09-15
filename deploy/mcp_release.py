"""Immutable release lifecycle for the independently hosted MCP component."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

try:
    from deploy.smoke_test import run_mcp_smoke
except ModuleNotFoundError:
    from smoke_test import run_mcp_smoke  # type: ignore[no-redef]

MCP_ROOT = Path(os.environ.get("PWC_MCP_ROOT", "/srv/paperswithcode/mcp"))
MCP_REPOSITORY = Path(os.environ.get("PWC_MCP_REPOSITORY", MCP_ROOT / "repository.git"))
MCP_RELEASES = MCP_ROOT / "releases"
MCP_ENVIRONMENTS = MCP_ROOT / "environments"
MCP_CONFIG_ROOT = Path(os.environ.get("PWC_DEPLOY_CONFIG_ROOT", "/etc/paperswithcode"))
MCP_PORTS = {"production": 8002, "staging": 8003}
MCP_API_URLS = {
    "production": "https://paperswithcode.co/api/v1",
    "staging": "http://127.0.0.1:8011/api/v1",
}
MCP_RETAIN_RELEASES = 3
MCP_MIN_FREE_BYTES = int(os.environ.get("PWC_MCP_MIN_FREE_BYTES", str(512 * 1024**2)))
SHA = re.compile(r"^[0-9a-f]{40}$")
PROTOCOL_ASSIGNMENT = re.compile(r'^PROTOCOL_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


class McpReleaseError(ValueError):
    pass


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, text=True, capture_output=capture)


def _git(*arguments: str, capture: bool = False) -> subprocess.CompletedProcess:
    return _run(["git", "--git-dir", str(MCP_REPOSITORY), *arguments], capture=capture)


def resolve_sha(source: str, environment: str) -> str:
    _git("fetch", "--prune", "origin")
    sha = _git("rev-parse", f"{source}^{{commit}}", capture=True).stdout.strip()
    if SHA.fullmatch(sha) is None:
        raise McpReleaseError("could not resolve an exact MCP commit")
    if environment == "production":
        main_ref = "refs/remotes/origin/main"
        if subprocess.run(
            [
                "git",
                "--git-dir",
                str(MCP_REPOSITORY),
                "rev-parse",
                "--verify",
                main_ref,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode:
            main_ref = "refs/heads/main"
        ancestry = subprocess.run(
            [
                "git",
                "--git-dir",
                str(MCP_REPOSITORY),
                "merge-base",
                "--is-ancestor",
                sha,
                main_ref,
            ],
            check=False,
        )
        if ancestry.returncode:
            raise McpReleaseError("production MCP commit is not on origin/main")
    return sha


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_tree_sha256(release: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    files = sorted(
        path
        for root in (release / "mcp_server", release / "standalone_cli")
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file() and ".venv" not in path.relative_to(release).parts
    )
    for path in files:
        relative = path.relative_to(release).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _extract(sha: str, destination: Path) -> None:
    descriptor, archive_name = tempfile.mkstemp(
        prefix="pwc-mcp-source-", suffix=".tar", dir=destination.parent
    )
    archive = Path(archive_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(MCP_REPOSITORY),
                    "archive",
                    "--format=tar",
                    sha,
                    "mcp_server",
                    "standalone_cli",
                ],
                check=True,
                stdout=output,
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")
    finally:
        archive.unlink(missing_ok=True)


def _descriptor(release: Path, sha: str) -> dict[str, object]:
    project = release / "mcp_server"
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    app_source = (project / "src/pwc_mcp/app.py").read_text()
    protocol = PROTOCOL_ASSIGNMENT.search(app_source)
    if protocol is None:
        raise McpReleaseError("MCP protocol version is not declared")
    lock_source = (project / "uv.lock").read_text()
    sdk = re.search(
        r'\[\[package\]\]\s*name = "mcp"\s*version = "([^"]+)"', lock_source
    )
    if sdk is None:
        raise McpReleaseError("MCP SDK is not locked")
    supported_protocols: list[str] | None = None
    for node in ast.parse(app_source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "KNOWN_PROTOCOLS"
            for target in node.targets
        ):
            values = []
            if isinstance(node.value, ast.Set):
                for item in node.value.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        values.append(item.value)
                    elif isinstance(item, ast.Name) and item.id == "PROTOCOL_VERSION":
                        values.append(protocol.group(1))
            if values:
                supported_protocols = sorted(set(values), reverse=True)
    if not supported_protocols or protocol.group(1) not in supported_protocols:
        raise McpReleaseError("MCP supported protocols are not declared")
    return {
        "schema_version": 1,
        "component": "mcp",
        "git_sha": sha,
        "release_id": sha[:16],
        "created_at": datetime.now(UTC).isoformat(),
        "package_version": metadata["project"]["version"],
        "server_version": metadata["project"]["version"],
        "lock_sha256": _sha256(project / "uv.lock"),
        "mcp_sdk_version": sdk.group(1),
        "protocol_version": protocol.group(1),
        "supported_protocols": supported_protocols,
        "health_schema_version": 1,
        "api_urls": MCP_API_URLS,
        "source_tree_sha256": _source_tree_sha256(release),
        "artifact_sha256": {
            "mcp_server/pyproject.toml": _sha256(project / "pyproject.toml"),
            "mcp_server/uv.lock": _sha256(project / "uv.lock"),
        },
    }


def validate_release(release: Path | None) -> dict[str, object]:
    if release is None or not release.is_dir():
        raise McpReleaseError("MCP release is missing")
    try:
        manifest = json.loads((release / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise McpReleaseError("MCP release manifest is invalid") from error
    artifacts = manifest.get("artifact_sha256") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("component") != "mcp"
        or SHA.fullmatch(str(manifest.get("git_sha") or "")) is None
        or manifest.get("lock_sha256") != _sha256(release / "mcp_server/uv.lock")
        or manifest.get("source_tree_sha256") != _source_tree_sha256(release)
        or not (release / "mcp_server/.venv/bin/pwc-mcp").is_file()
        or not os.access(release / "mcp_server/.venv/bin/pwc-mcp", os.X_OK)
        or not isinstance(artifacts, dict)
        or artifacts.get("mcp_server/pyproject.toml")
        != _sha256(release / "mcp_server/pyproject.toml")
        or artifacts.get("mcp_server/uv.lock")
        != _sha256(release / "mcp_server/uv.lock")
    ):
        raise McpReleaseError("MCP release manifest is invalid")
    return manifest


def prepare_release(sha: str) -> Path:
    MCP_RELEASES.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(MCP_ROOT.parent).free
    if free < MCP_MIN_FREE_BYTES:
        raise McpReleaseError(
            f"only {free // (1024**2)} MiB free; "
            f"{MCP_MIN_FREE_BYTES // (1024**2)} MiB is required"
        )
    release = MCP_RELEASES / sha[:16]
    if release.exists():
        manifest = validate_release(release)
        if manifest["git_sha"] != sha:
            raise McpReleaseError("MCP release ID collides with another commit")
        release.chmod(0o755)
        return release
    temporary = Path(tempfile.mkdtemp(prefix=f".{sha[:16]}-", dir=MCP_RELEASES))
    try:
        _extract(sha, temporary)
        _run(
            [
                "uv",
                "sync",
                "--locked",
                "--no-dev",
                "--no-editable",
                "--python",
                "/usr/bin/python3",
                "--no-managed-python",
                "--project",
                str(temporary / "mcp_server"),
            ]
        )
        manifest = _descriptor(temporary, sha)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        temporary.chmod(0o755)
        os.replace(temporary, release)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    validate_release(release)
    return release


def _pointer(environment: str, name: str) -> Path | None:
    path = MCP_ENVIRONMENTS / environment / name
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        return None


def _atomic_pointer(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.new-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


def _health(port: int, expected_version: str, *, attempts: int = 30) -> None:
    url = f"http://127.0.0.1:{port}/health"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.load(response)
            if (
                isinstance(payload, dict)
                and response.status == 200
                and payload.get("status") == "ok"
                and payload.get("version") == expected_version
            ):
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise McpReleaseError("MCP release failed readiness")


def _ensure_permanent_port_available(environment: str) -> None:
    unit = f"paperswithcode-mcp@{environment}.service"
    active = (
        subprocess.run(
            ["systemctl", "is-active", unit],
            text=True,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    if active:
        current = _pointer(environment, "current")
        manifest = validate_release(current)
        _health(MCP_PORTS[environment], str(manifest["package_version"]), attempts=2)
        return
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", MCP_PORTS[environment])) == 0:
            raise McpReleaseError(
                "the permanent MCP port is allocated by another process"
            )


def _smoke(port: int, manifest: dict[str, object]) -> None:
    failures = run_mcp_smoke(
        f"http://127.0.0.1:{port}",
        expected_version=str(manifest["package_version"]),
        protocol_version=str(manifest["protocol_version"]),
    )
    if failures:
        raise McpReleaseError("; ".join(failures))


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def qualify_release(release: Path, environment: str) -> None:
    manifest = validate_release(release)
    port = _free_port()
    config = MCP_CONFIG_ROOT / f"mcp-{environment}.env"
    if not config.is_file():
        raise McpReleaseError(f"MCP {environment} configuration is missing")
    command = [
        "/usr/sbin/runuser",
        "-u",
        "pwc-mcp",
        "--",
        "/usr/bin/env",
        "HOST=127.0.0.1",
        f"PORT={port}",
        "PWC_MCP_HOST=127.0.0.1",
        f"PWC_MCP_PORT={port}",
        f"PWC_API_URL={MCP_API_URLS[environment]}",
        str(release / "mcp_server/.venv/bin/python"),
        "-m",
        "uvicorn",
        "pwc_mcp.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--proxy-headers",
        "--no-access-log",
    ]
    environment_values = os.environ.copy()
    for raw_line in config.read_text().splitlines():
        if (
            raw_line.strip()
            and not raw_line.lstrip().startswith("#")
            and "=" in raw_line
        ):
            name, _, value = raw_line.partition("=")
            environment_values[name.strip()] = value.strip().strip('"').strip("'")
    process = subprocess.Popen(
        command,
        cwd=release / "mcp_server",
        env=environment_values,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _health(port, str(manifest["package_version"]))
        _smoke(port, manifest)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def activate_release(release: Path, environment: str) -> None:
    manifest = validate_release(release)
    _ensure_permanent_port_available(environment)
    root = MCP_ENVIRONMENTS / environment
    current = _pointer(environment, "current")
    previous = _pointer(environment, "previous")
    _atomic_pointer(release, root / "current")
    if current is not None and current != release:
        _atomic_pointer(current, root / "previous")
    unit = f"paperswithcode-mcp@{environment}.service"
    try:
        _run(["systemctl", "restart", unit])
        _health(MCP_PORTS[environment], str(manifest["package_version"]))
        _smoke(MCP_PORTS[environment], manifest)
    except Exception:
        if current is not None:
            _atomic_pointer(current, root / "current")
            if previous is not None:
                _atomic_pointer(previous, root / "previous")
            else:
                (root / "previous").unlink(missing_ok=True)
            _run(["systemctl", "restart", unit])
            old = validate_release(current)
            _health(MCP_PORTS[environment], str(old["package_version"]))
            _smoke(MCP_PORTS[environment], old)
        else:
            (root / "current").unlink(missing_ok=True)
            if previous is not None:
                _atomic_pointer(previous, root / "previous")
            else:
                (root / "previous").unlink(missing_ok=True)
            subprocess.run(["systemctl", "stop", unit], check=False)
        raise


def deploy(source: str, environment: str, *, qualify_only: bool) -> dict[str, object]:
    sha = resolve_sha(source, environment)
    release = prepare_release(sha)
    qualify_release(release, environment)
    if not qualify_only:
        activate_release(release, environment)
        cleanup_releases()
    return {
        "component": "mcp",
        "environment": environment,
        "git_sha": sha,
        "release": release.name,
        "result": "qualified" if qualify_only else "activated",
    }


def rollback(environment: str) -> dict[str, object]:
    current = _pointer(environment, "current")
    previous = _pointer(environment, "previous")
    if current is None or previous is None:
        raise McpReleaseError("current and previous MCP releases are required")
    validate_release(previous)
    _atomic_pointer(previous, MCP_ENVIRONMENTS / environment / "current")
    _atomic_pointer(current, MCP_ENVIRONMENTS / environment / "previous")
    try:
        _run(["systemctl", "restart", f"paperswithcode-mcp@{environment}.service"])
        manifest = validate_release(previous)
        _health(MCP_PORTS[environment], str(manifest["package_version"]))
        _smoke(MCP_PORTS[environment], manifest)
    except Exception:
        _atomic_pointer(current, MCP_ENVIRONMENTS / environment / "current")
        _atomic_pointer(previous, MCP_ENVIRONMENTS / environment / "previous")
        _run(["systemctl", "restart", f"paperswithcode-mcp@{environment}.service"])
        restored = validate_release(current)
        _health(MCP_PORTS[environment], str(restored["package_version"]))
        _smoke(MCP_PORTS[environment], restored)
        raise
    return {"component": "mcp", "environment": environment, "release": previous.name}


def status() -> dict[str, object]:
    environments = {}
    for environment in MCP_PORTS:
        item: dict[str, object] = {"port": MCP_PORTS[environment]}
        for name in ("current", "previous"):
            release = _pointer(environment, name)
            try:
                item[name] = validate_release(release) if release else None
            except McpReleaseError as error:
                item[name] = {"invalid": str(error)}
        service = subprocess.run(
            ["systemctl", "is-active", f"paperswithcode-mcp@{environment}.service"],
            text=True,
            capture_output=True,
            check=False,
        )
        item["service"] = service.stdout.strip() or "unknown"
        environments[environment] = item
    return {"component": "mcp", "environments": environments}


def cleanup_releases() -> None:
    if not MCP_RELEASES.is_dir():
        return
    protected = {
        release
        for environment in MCP_PORTS
        for name in ("current", "previous")
        if (release := _pointer(environment, name)) is not None
    }
    releases = sorted(
        (path for path in MCP_RELEASES.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for release in releases[MCP_RETAIN_RELEASES:]:
        if release not in protected:
            shutil.rmtree(release)
