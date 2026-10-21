from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import cli, install_host_layout, mcp_launcher, mcp_release, smoke_test


SHA = "a" * 40


def _release(root: Path, name: str = "aaaaaaaaaaaaaaaa") -> Path:
    release = root / "releases" / name
    project = release / "mcp_server"
    executable = project / ".venv/bin/pwc-mcp"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    interpreter = project / ".venv/bin/python"
    interpreter.write_text("#!/bin/sh\n")
    (project / "uv.lock").write_text("locked\n")
    manifest = {
        "schema_version": 1,
        "component": "mcp",
        "git_sha": SHA,
        "release_id": name,
        "package_version": "0.1.0",
        "protocol_version": "2026-07-28",
        "lock_sha256": mcp_release._sha256(project / "uv.lock"),
        "artifact_sha256": {
            "mcp_server/pyproject.toml": "",
            "mcp_server/uv.lock": mcp_release._sha256(project / "uv.lock"),
        },
    }
    (project / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    manifest["artifact_sha256"]["mcp_server/pyproject.toml"] = mcp_release._sha256(
        project / "pyproject.toml"
    )
    executable.chmod(0o755)
    interpreter.chmod(0o755)
    manifest["source_tree_sha256"] = mcp_release._source_tree_sha256(release)
    (release / "manifest.json").write_text(json.dumps(manifest))
    return release


def test_mcp_paths_are_separate_from_site_releases():
    assert mcp_release.MCP_REPOSITORY == mcp_release.MCP_ROOT / "repository.git"
    assert mcp_release.MCP_RELEASES == mcp_release.MCP_ROOT / "releases"
    assert mcp_release.MCP_PORTS == {"production": 8002, "staging": 8003}
    assert mcp_release.MCP_API_URLS["staging"].startswith("http://127.0.0.1:8011/")
    # Production also reads the catalog over nginx's loopback bridge, never the
    # public edge, so MCP calls do not consume the per-IP catalog rate limits.
    assert mcp_release.MCP_API_URLS["production"] == "http://127.0.0.1:8010/api/v1"
    assert not any(
        url.startswith("https://") for url in mcp_release.MCP_API_URLS.values()
    )


def test_resolve_sha_fetches_and_enforces_production_ancestry(monkeypatch):
    calls = []

    def git(*arguments, capture=False):
        calls.append(arguments)
        return SimpleNamespace(stdout=f"{SHA}\n")

    monkeypatch.setattr(mcp_release, "_git", git)
    monkeypatch.setattr(
        mcp_release.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    assert mcp_release.resolve_sha("origin/main", "production") == SHA
    assert calls[:2] == [
        ("fetch", "--prune", "origin"),
        ("rev-parse", "origin/main^{commit}"),
    ]


def test_descriptor_records_locked_contract_and_artifacts(tmp_path):
    release = tmp_path / "release"
    project = release / "mcp_server"
    source = project / "src/pwc_mcp"
    source.mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    (project / "uv.lock").write_text('[[package]]\nname = "mcp"\nversion = "1.20.0"\n')
    (source / "app.py").write_text(
        'PROTOCOL_VERSION = "2026-07-28"\n'
        'KNOWN_PROTOCOLS = {PROTOCOL_VERSION, "2025-11-25"}\n'
    )
    descriptor = mcp_release._descriptor(release, SHA)
    assert descriptor["git_sha"] == SHA
    assert descriptor["server_version"] == "0.2.0"
    assert descriptor["mcp_sdk_version"] == "1.20.0"
    assert descriptor["supported_protocols"] == ["2026-07-28", "2025-11-25"]
    assert descriptor["api_urls"] == mcp_release.MCP_API_URLS
    assert descriptor["source_tree_sha256"]
    assert descriptor["artifact_sha256"]["mcp_server/uv.lock"]


def test_prepare_release_repairs_existing_release_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ROOT", tmp_path)
    monkeypatch.setattr(mcp_release, "MCP_RELEASES", tmp_path / "releases")
    release = _release(tmp_path)
    release.chmod(0o700)

    assert mcp_release.prepare_release(SHA) == release
    assert release.stat().st_mode & 0o777 == 0o755


def test_validate_release_rejects_nonportable_runtime_interpreter(tmp_path):
    release = _release(tmp_path)
    interpreter = release / "mcp_server/.venv/bin/python"
    managed = tmp_path / "managed-python"
    managed.write_text("#!/bin/sh\n")
    managed.chmod(0o755)
    interpreter.unlink()
    interpreter.symlink_to(managed)

    with pytest.raises(mcp_release.McpReleaseError, match="manifest is invalid"):
        mcp_release.validate_release(release)


def test_prepare_release_makes_new_release_traversable(tmp_path, monkeypatch):
    releases = tmp_path / "releases"
    monkeypatch.setattr(mcp_release, "MCP_ROOT", tmp_path)
    monkeypatch.setattr(mcp_release, "MCP_RELEASES", releases)
    monkeypatch.setattr(mcp_release, "_extract", lambda *args: None)
    commands = []
    environments = []

    def run(command, **kwargs):
        commands.append(command)
        environments.append(kwargs["env"])

    monkeypatch.setattr(mcp_release.subprocess, "run", run)
    monkeypatch.setattr(
        mcp_release,
        "_descriptor",
        lambda *args: {"git_sha": SHA},
    )
    monkeypatch.setattr(
        mcp_release,
        "validate_release",
        lambda release: json.loads((release / "manifest.json").read_text()),
    )

    release = mcp_release.prepare_release(SHA)

    assert release.stat().st_mode & 0o777 == 0o755
    assert "--no-editable" in commands[0]
    # uv runs with a throwaway cache, not root's, and the cache is removed.
    cache = environments[0]["UV_CACHE_DIR"]
    assert environments[0]["HOME"] == cache
    assert not cache.startswith("/root")
    assert [path.name for path in releases.iterdir()] == [release.name]
    assert commands[0][commands[0].index("--python") + 1] == "/usr/bin/python3"
    assert "--no-managed-python" in commands[0]


def test_environment_pointers_are_independent_and_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    production = _release(tmp_path, "a" * 16)
    staging = _release(tmp_path, "b" * 16)
    mcp_release._atomic_pointer(
        production, mcp_release.MCP_ENVIRONMENTS / "production/current"
    )
    mcp_release._atomic_pointer(
        staging, mcp_release.MCP_ENVIRONMENTS / "staging/current"
    )
    assert mcp_release._pointer("production", "current") == production
    assert mcp_release._pointer("staging", "current") == staging


def test_qualify_uses_unprivileged_user_distinct_config_and_temporary_port(
    tmp_path, monkeypatch
):
    release = _release(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "mcp-staging.env").write_text("TOKEN=private\n")
    monkeypatch.setattr(mcp_release, "MCP_CONFIG_ROOT", config)
    monkeypatch.setattr(mcp_release, "_free_port", lambda: 18123)
    observed = {}

    class Process:
        def terminate(self):
            observed["terminated"] = True

        def wait(self, timeout):
            return 0

    def popen(command, **kwargs):
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(mcp_release.subprocess, "Popen", popen)
    monkeypatch.setattr(mcp_release, "_health", lambda *args: None)
    monkeypatch.setattr(mcp_release, "_smoke", lambda *args: None)
    mcp_release.qualify_release(release, "staging")
    command = observed["command"]
    assert command[:4] == ["/usr/sbin/runuser", "-u", "pwc-mcp", "--"]
    assert "PORT=18123" in command
    assert "PWC_API_URL=http://127.0.0.1:8011/api/v1" in command
    assert command[-11:] == [
        str(release / "mcp_server/.venv/bin/python"),
        "-m",
        "uvicorn",
        "pwc_mcp.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "18123",
        "--no-proxy-headers",
        "--no-access-log",
    ]
    assert observed["environment"]["TOKEN"] == "private"
    assert observed["terminated"] is True


def test_launcher_runs_installed_module_with_virtualenv_python(tmp_path, monkeypatch):
    release = _release(tmp_path)
    interpreter = release / "mcp_server/.venv/bin/python"
    interpreter.write_text("#!/bin/sh\n")
    interpreter.chmod(0o755)
    root = tmp_path / "environments/staging"
    mcp_release._atomic_pointer(release, root / "current")
    monkeypatch.setattr(mcp_launcher, "MCP_ENVIRONMENTS", tmp_path / "environments")
    monkeypatch.setattr(mcp_launcher, "validate_release", lambda release: None)
    observed = {}
    monkeypatch.setattr(
        mcp_launcher.os,
        "chdir",
        lambda directory: observed.update(cwd=directory),
    )

    def execve(executable, arguments, environment):
        observed.update(
            executable=executable,
            arguments=arguments,
            environment=environment,
        )
        raise RuntimeError("execve called")

    monkeypatch.setattr(mcp_launcher.os, "execve", execve)
    monkeypatch.setattr(mcp_launcher.sys, "argv", ["mcp_launcher.py", "staging"])

    with pytest.raises(RuntimeError, match="execve called"):
        mcp_launcher.main()

    assert observed["executable"] == interpreter
    assert observed["cwd"] == release / "mcp_server"
    assert observed["arguments"] == [
        str(interpreter),
        "-m",
        "uvicorn",
        "pwc_mcp.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8003",
        "--no-proxy-headers",
        "--no-access-log",
    ]


def test_failed_activation_restores_previous_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    previous = _release(tmp_path, "0" * 16)
    old = _release(tmp_path, "a" * 16)
    new = _release(tmp_path, "b" * 16)
    root = mcp_release.MCP_ENVIRONMENTS / "staging"
    mcp_release._atomic_pointer(old, root / "current")
    mcp_release._atomic_pointer(previous, root / "previous")
    monkeypatch.setattr(mcp_release, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp_release, "_ensure_permanent_port_available", lambda *args: None
    )
    monkeypatch.setattr(mcp_release, "_health", lambda *args, **kwargs: None)
    calls = 0

    def smoke(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise mcp_release.McpReleaseError("candidate failed")

    monkeypatch.setattr(mcp_release, "_smoke", smoke)
    with pytest.raises(mcp_release.McpReleaseError, match="candidate failed"):
        mcp_release.activate_release(new, "staging")
    assert mcp_release._pointer("staging", "current") == old
    assert mcp_release._pointer("staging", "previous") == previous


def test_activation_enables_unit_so_it_survives_reboot(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    release = _release(tmp_path)
    commands = []
    monkeypatch.setattr(
        mcp_release, "_run", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(
        mcp_release, "_ensure_permanent_port_available", lambda *args: None
    )
    monkeypatch.setattr(mcp_release, "_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_release, "_smoke", lambda *args, **kwargs: None)

    mcp_release.activate_release(release, "production")

    assert commands == [
        ["systemctl", "enable", "paperswithcode-mcp@production.service"],
        ["systemctl", "restart", "paperswithcode-mcp@production.service"],
    ]


def test_failed_initial_activation_disables_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    release = _release(tmp_path)
    monkeypatch.setattr(mcp_release, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp_release, "_ensure_permanent_port_available", lambda *args: None
    )
    monkeypatch.setattr(mcp_release, "_health", lambda *args, **kwargs: None)

    def smoke(*args):
        raise mcp_release.McpReleaseError("candidate failed")

    monkeypatch.setattr(mcp_release, "_smoke", smoke)
    stopped = []
    monkeypatch.setattr(
        mcp_release.subprocess,
        "run",
        lambda command, **kwargs: stopped.append(command),
    )

    with pytest.raises(mcp_release.McpReleaseError, match="candidate failed"):
        mcp_release.activate_release(release, "staging")

    assert mcp_release._pointer("staging", "current") is None
    assert stopped == [
        ["systemctl", "disable", "--now", "paperswithcode-mcp@staging.service"]
    ]


def test_rollback_enables_unit_before_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    monkeypatch.setattr(mcp_release, "MCP_PORTS", {"staging": 8003})
    root = mcp_release.MCP_ENVIRONMENTS / "staging"
    mcp_release._atomic_pointer(_release(tmp_path, "b" * 16), root / "current")
    mcp_release._atomic_pointer(_release(tmp_path, "a" * 16), root / "previous")
    commands = []
    monkeypatch.setattr(
        mcp_release, "_run", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(mcp_release, "_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_release, "_smoke", lambda *args, **kwargs: None)

    mcp_release.rollback("staging")

    assert commands == [
        ["systemctl", "enable", "paperswithcode-mcp@staging.service"],
        ["systemctl", "restart", "paperswithcode-mcp@staging.service"],
    ]


def test_rollback_swaps_current_and_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    monkeypatch.setattr(mcp_release, "MCP_PORTS", {"staging": 8003})
    old = _release(tmp_path, "a" * 16)
    current = _release(tmp_path, "b" * 16)
    root = mcp_release.MCP_ENVIRONMENTS / "staging"
    mcp_release._atomic_pointer(current, root / "current")
    mcp_release._atomic_pointer(old, root / "previous")
    monkeypatch.setattr(mcp_release, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_release, "_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_release, "_smoke", lambda *args, **kwargs: None)
    mcp_release.rollback("staging")
    assert mcp_release._pointer("staging", "current") == old
    assert mcp_release._pointer("staging", "previous") == current


def test_failed_rollback_requalifies_restored_release(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    monkeypatch.setattr(mcp_release, "MCP_PORTS", {"staging": 8003})
    previous = _release(tmp_path, "a" * 16)
    current = _release(tmp_path, "b" * 16)
    root = mcp_release.MCP_ENVIRONMENTS / "staging"
    mcp_release._atomic_pointer(current, root / "current")
    mcp_release._atomic_pointer(previous, root / "previous")
    monkeypatch.setattr(mcp_release, "_run", lambda *args, **kwargs: None)
    health_versions = []
    smoke_releases = []
    monkeypatch.setattr(
        mcp_release,
        "_health",
        lambda _port, version: health_versions.append(version),
    )

    def smoke(_port, manifest):
        smoke_releases.append(manifest["release_id"])
        if len(smoke_releases) == 1:
            raise mcp_release.McpReleaseError("rollback failed")

    monkeypatch.setattr(mcp_release, "_smoke", smoke)
    with pytest.raises(mcp_release.McpReleaseError, match="rollback failed"):
        mcp_release.rollback("staging")

    assert mcp_release._pointer("staging", "current") == current
    assert mcp_release._pointer("staging", "previous") == previous
    assert health_versions == ["0.1.0", "0.1.0"]
    assert smoke_releases == [previous.name, current.name]


def test_cleanup_retains_recent_and_pointed_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_release, "MCP_ROOT", tmp_path)
    monkeypatch.setattr(mcp_release, "MCP_RELEASES", tmp_path / "releases")
    monkeypatch.setattr(mcp_release, "MCP_ENVIRONMENTS", tmp_path / "environments")
    monkeypatch.setattr(mcp_release, "MCP_PORTS", {"staging": 8003})
    monkeypatch.setattr(mcp_release, "MCP_RETAIN_RELEASES", 1)
    pointed = _release(tmp_path, "a" * 16)
    newest = _release(tmp_path, "b" * 16)
    pointed.touch()
    newest.touch()
    mcp_release._atomic_pointer(pointed, tmp_path / "environments/staging/current")
    mcp_release.cleanup_releases()
    assert pointed.exists()
    assert newest.exists()


def test_cli_mcp_deploy_uses_shared_deployment_lock(monkeypatch, capsys):
    events = []

    class Lock:
        def __enter__(self):
            events.append("locked")

        def __exit__(self, *args):
            events.append("unlocked")

    monkeypatch.setattr(cli, "require_root", lambda: None)
    monkeypatch.setattr(cli, "deployment_lock", Lock)
    monkeypatch.setattr(
        cli.mcp_release,
        "deploy",
        lambda *args, **kwargs: events.append("deployed") or {"result": "activated"},
    )
    args = SimpleNamespace(
        component="mcp",
        environment="staging",
        source=SHA,
        confirm=None,
        qualify_only=False,
    )
    assert cli.deploy(args) == 0
    assert events == ["locked", "deployed", "unlocked"]
    assert '"activated"' in capsys.readouterr().out


def test_cli_component_defaults_to_site_and_accepts_mcp():
    parser = cli.parser_for("pwc-deploy")
    assert parser.parse_args(["staging", SHA]).component == "site"
    assert parser.parse_args(["staging", SHA, "--component", "mcp"]).component == "mcp"
    assert (
        cli.parser_for("pwc-status").parse_args(["--component", "mcp"]).component
        == "mcp"
    )


def test_mcp_smoke_checks_health_discovery_and_read_only_tool(monkeypatch):
    responses = iter(
        [
            (
                200,
                {},
                json.dumps(
                    {"status": "ok", "version": "0.1", "protocol": "2026-07-28"}
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"supportedVersions": ["2026-07-28"]},
                    }
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "tools": [
                                {"name": "get_paper_info"},
                                {"name": "read_paper"},
                                {"name": "list_papers"},
                            ]
                        },
                    }
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {"jsonrpc": "2.0", "id": 3, "result": {"content": []}}
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "result": {"protocolVersion": "2025-11-25"},
                    }
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "result": {
                            "tools": [
                                {"name": "get_paper_info"},
                                {"name": "read_paper"},
                                {"name": "list_papers"},
                            ]
                        },
                    }
                ).encode(),
            ),
            (
                200,
                {},
                json.dumps(
                    {"jsonrpc": "2.0", "id": 6, "result": {"content": []}}
                ).encode(),
            ),
        ]
    )
    monkeypatch.setattr(smoke_test, "request", lambda *args, **kwargs: next(responses))
    assert (
        smoke_test.run_mcp_smoke("http://127.0.0.1:9999", expected_version="0.1") == []
    )


def test_mcp_exchange_accepts_sse_jsonrpc(monkeypatch):
    monkeypatch.setattr(
        smoke_test,
        "request",
        lambda *args, **kwargs: (
            200,
            {"Content-Type": "text/event-stream; charset=utf-8"},
            b': keepalive\n\nevent: message\ndata: {"jsonrpc":"2.0","id":7,'
            b'"result":{"tools":[]}}\n\n',
        ),
    )

    assert smoke_test._mcp_exchange("http://127.0.0.1:9999", 7, "tools/list", {}) == {
        "tools": []
    }


def test_systemd_unit_is_hardened_and_single_process():
    unit = (Path("deploy/systemd") / "paperswithcode-mcp@.service").read_text()
    for expected in (
        "User=pwc-mcp",
        "EnvironmentFile=/etc/paperswithcode/mcp-%i.env",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "MemoryMax=768M",
        "CPUQuota=75%",
        "TasksMax=64",
    ):
        assert expected in unit
    assert "backend/keys.env" not in unit
    assert "--workers" not in unit


def test_installer_includes_mcp_unit_and_separate_repository():
    host_layout = Path("deploy/install_host_layout.py").read_text()
    tools = Path("deploy/install_deploy_tools.py").read_text()
    assert '"paperswithcode-mcp@.service"' in host_layout
    assert '"paperswithcode-mcp@.service"' in tools
    assert "https://github.com/huggingface/pwc-cli.git" in host_layout
    assert '"pwc-mcp"' in host_layout


def test_mcp_config_reconciles_staging_api_without_rotating_cursor_key(tmp_path):
    config = tmp_path / "mcp-staging.env"
    config.write_text(
        "PORT=8003\n"
        "PWC_MCP_PORT=8003\n"
        "PWC_API_URL=http://127.0.0.1:8001/api/v1\n"
        "PWC_MCP_CURSOR_KEY_CURRENT=keep-this-secret\n"
        "PWC_MCP_CURSOR_KEY_PREVIOUS=\n"
    )

    install_host_layout.ensure_mcp_config(
        config,
        port=8003,
        api_url="http://127.0.0.1:8011/api/v1",
        allowed_hosts="staging.paperswithcode.co,localhost:*,127.0.0.1:*",
    )

    values = dict(line.split("=", 1) for line in config.read_text().splitlines())
    assert values["PWC_API_URL"] == "http://127.0.0.1:8011/api/v1"
    assert values["PWC_MCP_CURSOR_KEY_CURRENT"] == "keep-this-secret"
    assert config.stat().st_mode & 0o777 == 0o600
