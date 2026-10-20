from __future__ import annotations

import subprocess

import asyncio
import socket
import urllib.error
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.services.deployment_lifecycle as lifecycle_module
import backend.services.postgres_sdk_session_store as postgres_store_module
import deploy.cli as deploy_cli
import deploy.nginx_tool as nginx_tool_module
import deploy.runtime as runtime_module
import deploy.topology_audit as topology_audit_module
from backend.chat_sandbox_worker import agent
from backend.chat_sandbox_worker.remote_store import RemoteSessionStore, RetryPolicy
from backend.config import get_settings
from backend.main import create_app
from backend.services.deployment_lifecycle import (
    DeploymentAccountingMiddleware,
    DeploymentLifecycle,
)
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore
from backend.utils.auth import require_user
from deploy.nginx_validate import validate as validate_nginx
from deploy.release import atomic_symlink, validate_rolling_compatibility
from deploy.runtime import prepare_runtime, runtime_id, runtime_manifest


START_RECOVERY_SLOT = deploy_cli._start_recovery_slot


def test_accounting_covers_complete_streaming_body(
    monkeypatch: pytest.MonkeyPatch,
):
    lifecycle = DeploymentLifecycle()
    monkeypatch.setattr(lifecycle_module, "deployment_lifecycle", lifecycle)

    async def exercise() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()

        async def streaming_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            started.set()
            await finish.wait()
            await send({"type": "http.response.body", "body": b"done"})

        middleware = DeploymentAccountingMiddleware(streaming_app)
        task = asyncio.create_task(
            middleware(
                {"type": "http", "path": "/api/v1/chat/stream"},
                lambda: None,
                lambda _message: asyncio.sleep(0),
            )
        )
        await started.wait()
        status = lifecycle.status()
        assert status.active_http_requests == 1
        assert status.active_chat_streams == 1
        finish.set()
        await task
        assert lifecycle.status().active_http_requests == 0
        assert lifecycle.status().active_chat_streams == 0

    asyncio.run(exercise())


def test_drain_is_idempotent_and_blocks_only_new_admission():
    lifecycle = DeploymentLifecycle()
    with lifecycle.request("/api/v1/chat/stream"):
        drained = lifecycle.drain()
        assert not drained.accepting_chat_turns
        assert drained.active_chat_streams == 1
        assert lifecycle.drain().drain_started_at == drained.drain_started_at
    assert lifecycle.status().active_chat_streams == 0
    assert lifecycle.undrain().accepting_chat_turns


def test_multiworker_lifecycle_shares_drain_and_aggregates_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "green")
    monkeypatch.setenv("PWC_RELEASE_ID", "release-1")
    monkeypatch.setenv("PWC_RUNTIME_ID", "runtime-1")
    live = {(1001, "start-1"), (1002, "start-2")}

    def is_alive(pid: int, started: str) -> bool:
        return (pid, started) in live

    first = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1001,
        process_start_token="start-1",
        process_is_alive=is_alive,
    )
    second = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1002,
        process_start_token="start-2",
        process_is_alive=is_alive,
    )

    with first.request("/api/v1/chat/stream"):
        with second.request("/api/internal/chat-gateway/v1/responses"):
            status = first.status()
            assert status.active_http_requests == 2
            assert status.active_chat_streams == 1
            assert status.active_gateway_streams == 1

            drained = first.drain()
            assert not drained.accepting_chat_turns
            assert second.status().drain_started_at == drained.drain_started_at
            assert not second.status().accepting_chat_turns

            assert second.undrain().accepting_chat_turns
            assert first.status().accepting_chat_turns

    assert first.status().active_http_requests == 0
    assert first.status().active_chat_streams == 0
    assert first.status().active_gateway_streams == 0


def test_multiworker_lifecycle_excludes_stale_and_other_release_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PWC_ENVIRONMENT", "production")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "blue")
    monkeypatch.setenv("PWC_RELEASE_ID", "release-1")
    monkeypatch.setenv("PWC_RUNTIME_ID", "runtime-1")
    live = {(1001, "start-1"), (1002, "start-2"), (1003, "start-3")}

    def is_alive(pid: int, started: str) -> bool:
        return (pid, started) in live

    current = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1001,
        process_start_token="start-1",
        process_is_alive=is_alive,
    )
    stale = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1002,
        process_start_token="start-2",
        process_is_alive=is_alive,
    )
    with stale.request("/api/v1/chat/stream"):
        live.remove((1002, "start-2"))
        assert current.status().active_chat_streams == 0

    monkeypatch.setenv("PWC_RELEASE_ID", "release-2")
    other_release = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1003,
        process_start_token="start-3",
        process_is_alive=is_alive,
    )
    with other_release.request("/api/v1/chat/stream"):
        assert current.status().active_chat_streams == 0


def test_multiworker_lifecycle_preserves_drain_after_all_workers_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PWC_ENVIRONMENT", "production")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "blue")
    monkeypatch.setenv("PWC_RELEASE_ID", "release-1")
    monkeypatch.setenv("PWC_RUNTIME_ID", "runtime-1")
    live = {(1001, "start-1")}

    def is_alive(pid: int, started: str) -> bool:
        return (pid, started) in live

    original = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1001,
        process_start_token="start-1",
        process_is_alive=is_alive,
    )
    assert not original.drain().accepting_chat_turns

    live.remove((1001, "start-1"))
    live.add((1002, "start-2"))
    restarted = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1002,
        process_start_token="start-2",
        process_is_alive=is_alive,
    )

    assert not restarted.status().accepting_chat_turns
    assert restarted.status().drain_started_at is not None


def test_multiworker_lifecycle_tolerates_concurrent_state_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "green")
    monkeypatch.setenv("PWC_RELEASE_ID", "release-1")
    monkeypatch.setenv("PWC_RUNTIME_ID", "runtime-1")
    lifecycle = DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1001,
        process_start_token="start-1",
        process_is_alive=lambda _pid, _started: True,
    )
    lifecycle.drain()
    worker_path = lifecycle._worker_path
    drain_path = lifecycle._drain_path
    assert worker_path is not None
    assert drain_path is not None
    original_read = lifecycle._read_json

    def unlink_before_read(path: Path):
        path.unlink(missing_ok=True)
        return original_read(path)

    monkeypatch.setattr(lifecycle, "_read_json", unlink_before_read)

    status = lifecycle.status()
    assert status.active_http_requests == 0
    assert status.accepting_chat_turns


def test_prepare_slot_explicitly_undrains_only_after_exact_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    release = tmp_path / "release"
    release.mkdir()
    runtime = tmp_path / "runtime-1"
    runtime.mkdir()
    manifest = {"release_id": "release-1"}
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda _environment, _slot, path, **kwargs: events.append(
            (path, kwargs.get("method", "GET"))
        )
        or None,
    )
    monkeypatch.setattr(
        deploy_cli.subprocess,
        "run",
        lambda command, **_kwargs: events.append(("subprocess", tuple(command))),
    )
    monkeypatch.setattr(
        deploy_cli,
        "run",
        lambda command, **_kwargs: events.append(("run", tuple(command))),
    )
    monkeypatch.setattr(
        deploy_cli, "validate_manifest", lambda *_args, **_kwargs: manifest
    )

    def wait_slot(_environment, _slot, _manifest, _runtime, *, accepting=True):
        events.append(("wait", accepting))
        return {
            "release_id": "release-1",
            "runtime_id": "runtime-1",
            "slot": "green",
            "accepting_chat_turns": accepting is not False,
        }

    monkeypatch.setattr(deploy_cli, "_wait_slot", wait_slot)
    monkeypatch.setattr(
        deploy_cli,
        "_smoke_slot_candidate",
        lambda *_args: events.append(("smoke", "candidate")),
    )

    result = deploy_cli._prepare_slot("staging", "green", release, runtime)

    assert result["accepting_chat_turns"] is True
    assert [
        (name, value)
        for name, value in events
        if name in {"wait", "/internal/undrain", "smoke"}
    ] == [
        ("wait", None),
        ("/internal/undrain", "POST"),
        ("wait", True),
        ("smoke", "candidate"),
    ]


def test_only_active_slot_owns_environment_background_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    slots = environment_root / "staging" / "slots"
    (slots / "blue").mkdir(parents=True)
    (slots / "green").mkdir()
    (environment_root / "staging" / "active").symlink_to(slots / "blue")
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "blue")

    assert DeploymentLifecycle().owns_active_slot(environment_root)

    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "green")
    assert not DeploymentLifecycle().owns_active_slot(environment_root)


def test_slot_without_active_pointer_does_not_own_background_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "blue")

    assert not DeploymentLifecycle().owns_active_slot(tmp_path / "environments")


def test_draining_chat_endpoint_returns_retry_after(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "hf_user_id": "user-1",
        "username": "user",
    }
    lifecycle_module.deployment_lifecycle.drain()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/stream",
                json={"message": "hello", "client_message_id": "message-1"},
            )
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "3"
    finally:
        lifecycle_module.deployment_lifecycle.undrain()


def test_unix_operator_endpoints_have_request_injected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PWC_DEPLOY_TESTING", "1")
    app = create_app()
    with TestClient(app) as client:
        status = client.get("/internal/deployment-status")
        drained = client.post("/internal/drain")
        not_ready = client.get("/internal/ready")
        undrained = client.post("/internal/undrain")
    assert status.status_code == 200
    assert drained.status_code == 200
    assert not_ready.status_code == 503
    assert undrained.status_code == 200


def test_operator_endpoints_require_exact_unix_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("PWC_DEPLOY_TESTING", raising=False)
    socket_path = tmp_path / "staging-blue.sock"
    socket_alias = tmp_path / "slot" / "backend.sock"
    socket_alias.parent.mkdir()
    socket_alias.symlink_to(socket_path)
    monkeypatch.setenv("PWC_BACKEND_SOCKET", str(socket_alias))

    assert lifecycle_module.operator_socket_allowed(
        {"server": (str(socket_path), None)}
    )
    assert lifecycle_module.operator_socket_allowed({"server": str(socket_alias)})
    assert not lifecycle_module.operator_socket_allowed({"server": ("127.0.0.1", 8001)})
    assert not lifecycle_module.operator_socket_allowed(
        {"server": (str(tmp_path / "staging-green.sock"), None)}
    )
    assert not lifecycle_module.operator_socket_allowed({"server": None})


def test_topology_audit_ignores_its_own_checkout_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_output(command: list[str]) -> str:
        if command[:3] == ["ps", "-eo", "user,pid,args"]:
            return (
                "root 123 /root/python_projects/paperswithcode/.venv/bin/python "
                "deploy/topology_audit.py --json\n"
            )
        return ""

    monkeypatch.setattr(topology_audit_module, "output", fake_output)

    result = topology_audit_module.audit(tmp_path)

    assert "running process references developer checkout" not in result["findings"]


def test_immutable_runtime_build_reuse_and_failed_cleanup(tmp_path: Path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "uv.lock").write_text("lock")
    runtimes = tmp_path / "runtimes"
    builds = 0

    def build(command, *, cwd, env, check):
        nonlocal builds
        builds += 1
        target = Path(env["UV_PROJECT_ENVIRONMENT"])
        (target / "bin").mkdir()
        (target / "bin" / "python").symlink_to("/usr/bin/python3")
        (target / "bin" / "hf").write_text(f"#!{target}/bin/python\nprint(42)\n")
        (target / "bin" / "hf").chmod(0o755)
        (target / "lib").mkdir()
        (target / "lib" / "module.py").write_text("value = 1\n")

    def version(*args, **kwargs):
        return SimpleNamespace(stdout="Python 3.12.11\n")

    first, created = prepare_runtime(
        release, runtimes, runner=build, version_runner=version
    )
    assert created
    result = subprocess.run(
        [str(first / "bin" / "hf")], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "42"
    assert runtime_manifest(first)["lock_sha256"] == first.name
    assert first.stat().st_mode & 0o222 == 0
    assert (first / "runtime.json").stat().st_mode & 0o222 == 0
    assert (first / "lib" / "module.py").stat().st_mode & 0o222 == 0
    second, created = prepare_runtime(
        release, runtimes, runner=build, version_runner=version
    )
    assert second == first
    assert not created
    assert builds == 1

    other = tmp_path / "other"
    other.mkdir()
    (other / "uv.lock").write_text("different")

    def fail(*args, **kwargs):
        raise OSError("build failed")

    with pytest.raises(OSError, match="build failed"):
        prepare_runtime(other, runtimes, runner=fail, version_runner=version)
    assert not any(path.name.startswith(".") for path in runtimes.iterdir())


def test_runtime_builder_uses_stable_absolute_uv_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = tmp_path / "release"
    release.mkdir()
    (release / "uv.lock").write_text("lock")
    uv = tmp_path / "uv"
    uv.write_text("binary")
    monkeypatch.setattr(runtime_module, "UV_BINARY", uv)
    command_seen: list[str] = []

    def build(command, *, cwd, env, check):
        command_seen.extend(command)
        assert env["UV_PYTHON"] == "/usr/bin/python3"
        assert env["UV_PYTHON_PREFERENCE"] == "only-system"
        assert env["UV_LINK_MODE"] == "copy"
        target = Path(env["UV_PROJECT_ENVIRONMENT"])
        (target / "bin").mkdir()
        (target / "bin" / "python").symlink_to("/usr/bin/python3")

    def version(*args, **kwargs):
        return SimpleNamespace(stdout="Python 3.12.11\n")

    prepare_runtime(
        release,
        tmp_path / "runtimes",
        runner=build,
        version_runner=version,
    )
    assert command_seen[0] == str(uv)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_legacy_bridge_flag_is_explicit_on_deploy_parser(environment: str):
    parser = deploy_cli.parser_for("pwc-deploy")
    args = parser.parse_args([environment, "a" * 40, "--legacy-bridge"])
    assert args.legacy_bridge is True
    assert args.qualify_only is False


@pytest.fixture(autouse=True)
def _keep_tests_off_live_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep unstubbed slot control and unit changes away from the live host."""
    real_run = subprocess.run

    def refuse_host_mutation(command, *args, **kwargs):
        if (
            isinstance(command, (list, tuple))
            and len(command) > 1
            and command[0] == "systemctl"
            and command[1] not in {"show", "is-active", "is-enabled"}
        ):
            raise AssertionError(f"test reached host systemd: {command}")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", refuse_host_mutation)
    monkeypatch.setattr(
        deploy_cli,
        "_slot_socket",
        lambda environment, slot: tmp_path / f"{environment}-{slot}.sock",
    )


def _contract(emits: int, accepts: int, database: int = 1) -> dict:
    return {
        "chat_runtime": {
            "gateway_contract_version": emits,
            "gateway_compatible_from": accepts,
            "database_contract_version": database,
        }
    }


def test_rolling_contract_requires_forward_and_rollback_compatibility():
    validate_rolling_compatibility(_contract(26, 25), _contract(26, 26))
    validate_rolling_compatibility(_contract(26, 26), _contract(27, 26))
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(_contract(26, 26), _contract(28, 26))
    with pytest.raises(ValueError, match="database"):
        validate_rolling_compatibility(_contract(26, 26), _contract(26, 26, 2))


def test_active_symlink_switch_keeps_existing_unix_connection(tmp_path: Path):
    slot_a = tmp_path / "blue"
    slot_b = tmp_path / "green"
    slot_a.mkdir()
    slot_b.mkdir()
    socket_a_path = tmp_path / "a.sock"
    socket_b_path = tmp_path / "b.sock"
    (slot_a / "backend.sock").symlink_to(socket_a_path)
    (slot_b / "backend.sock").symlink_to(socket_b_path)
    listener_a = socket.socket(socket.AF_UNIX)
    listener_b = socket.socket(socket.AF_UNIX)
    listener_a.bind(str(socket_a_path))
    listener_b.bind(str(socket_b_path))
    listener_a.listen()
    listener_b.listen()
    try:
        active = tmp_path / "active"
        atomic_symlink(slot_a, active)
        client_a = socket.socket(socket.AF_UNIX)
        client_a.connect(str(active / "backend.sock"))
        server_a, _ = listener_a.accept()
        atomic_symlink(slot_b, active)
        client_b = socket.socket(socket.AF_UNIX)
        client_b.connect(str(active / "backend.sock"))
        server_b, _ = listener_b.accept()
        try:
            server_a.sendall(b"old")
            server_b.sendall(b"new")
            assert client_a.recv(3) == b"old"
            assert client_b.recv(3) == b"new"
        finally:
            client_a.close()
            client_b.close()
            server_a.close()
            server_b.close()
    finally:
        listener_a.close()
        listener_b.close()


def test_remote_store_retries_transient_but_not_permanent_errors():
    store = RemoteSessionStore(
        retry_policy=RetryPolicy(
            total_deadline_seconds=1,
            initial_delay_seconds=0,
            maximum_delay_seconds=0,
        )
    )
    calls = 0

    def ambiguous(_payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError("http://store", 503, "unavailable", {}, None)
        return {"ok": True}

    store._request_once = ambiguous
    assert store._request({"action": "append"}) == {"ok": True}
    assert calls == 2

    calls = 0

    def permanent(_payload):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError("http://store", 403, "forbidden", {}, None)

    store._request_once = permanent
    with pytest.raises(urllib.error.HTTPError):
        store._request({"action": "append"})
    assert calls == 1


def test_ambiguous_append_retry_does_not_refold_or_recount(
    monkeypatch: pytest.MonkeyPatch,
):
    class Result:
        def __init__(self, value=None):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalar_one(self):
            return self.value

    class Database:
        def __init__(self):
            self.entries: set[str] = set()
            self.summary = SimpleNamespace(
                sdk_session_id=uuid.uuid4(),
                mtime=0,
                data={},
            )

        def execute(self, statement):
            table = getattr(statement, "table", None)
            name = getattr(table, "name", "")
            if name == "chat_sdk_transcript_entries":
                entry_uuid = statement.compile().params["entry_uuid"]
                if entry_uuid in self.entries:
                    return Result(None)
                self.entries.add(entry_uuid)
                return Result(1)
            if name in {"chat_sdk_session_summaries", "chat_sessions"}:
                return Result(None)
            return Result(self.summary)

    database = Database()
    key = {
        "project_key": "project",
        "session_id": str(database.summary.sdk_session_id),
    }
    entry = {"uuid": "entry-1", "type": "assistant", "message": "answer"}
    folds = 0

    def fold(previous, folded_key, inserted):
        nonlocal folds
        folds += 1
        assert previous is None
        assert folded_key == key
        assert inserted == [entry]
        return {"mtime": 0, "data": {"count": 1}}

    monkeypatch.setattr(postgres_store_module, "fold_session_summary", fold)
    first = PostgresSDKSessionStore.append_in_session(database, key, [entry])
    summary_after_first = dict(database.summary.data)
    second = PostgresSDKSessionStore.append_in_session(database, key, [entry])

    assert first > 0
    assert second == 0
    assert folds == 1
    assert database.summary.data == summary_after_first == {"count": 1}


def test_post_result_mirror_failure_carries_bounded_terminal_payload():
    class TerminalAdapter:
        terminal = False

        def feed(self, _message):
            self.terminal = True
            return [
                {
                    "type": "done",
                    "finish_reason": "success",
                    "followups": ["next"],
                }
            ]

    key = {"project_key": "project", "session_id": "session"}

    async def messages():
        yield object()
        yield agent.MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            key=key,
            error="lost",
        )

    async def collect():
        settings = agent.WorkerSettings.from_environment()
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request",
                hooks=agent.WorkerToolHooks(settings),
                adapter=TerminalAdapter(),
            )
        ]

    assert asyncio.run(collect()) == [
        {
            "v": 1,
            "type": "_mirror_error",
            "request_id": "request",
            "key": key,
            "error": "lost",
            "result_available": True,
            "terminal": {
                "v": 1,
                "request_id": "request",
                "type": "done",
                "finish_reason": "success",
                "followups": ["next"],
            },
        }
    ]


def test_checked_in_nginx_uses_matching_active_roots_and_denies_operators():
    root = Path(__file__).resolve().parents[2] / "deploy" / "nginx"
    assert (
        validate_nginx(
            (root / "paperswithcode.co.conf").read_text(),
            (root / "staging.paperswithcode.co.conf").read_text(),
        )
        == []
    )


def test_nginx_transition_smoke_pins_release_and_dedicated_gateway():
    command = nginx_tool_module.smoke_command("staging", "release-staging")

    assert command[0] == "/usr/bin/python3"
    assert command[command.index("--expected-release") + 1] == "release-staging"
    assert command[command.index("--gateway-url") + 1] == (
        "https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway"
    )
    production = nginx_tool_module.smoke_command("production", "release-production")
    assert "--gateway-url" not in production


def _activation_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    environments = tmp_path / "environments"
    root = environments / "staging"
    blue = root / "slots" / "blue"
    green = root / "slots" / "green"
    blue.mkdir(parents=True)
    green.mkdir(parents=True)
    old = tmp_path / "old"
    candidate = tmp_path / "candidate"
    older = tmp_path / "older"
    for release in (old, candidate, older):
        release.mkdir()
    atomic_symlink(old, root / "current")
    atomic_symlink(older, root / "previous")
    atomic_symlink(old, blue / "release")
    atomic_symlink(blue, root / "active")
    manifests = {
        release: {
            "release_id": release.name,
            "chat_runtime": {
                "gateway_contract_version": 26,
                "gateway_compatible_from": 26,
                "database_contract_version": 1,
            },
        }
        for release in (old, candidate, older)
    }
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: manifests[release],
    )
    monkeypatch.setattr(deploy_cli, "_write_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(deploy_cli, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        deploy_cli, "_persist_active_slot_socket", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        deploy_cli, "prepare_candidate_if_enabled", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        deploy_cli, "external_pi_lifecycle_enabled", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(
        deploy_cli, "stop_slot_if_enabled", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        deploy_cli, "_start_recovery_slot", lambda *_args, **_kwargs: None
    )

    def prepare(_environment, slot, release, _runtime):
        atomic_symlink(release, root / "slots" / slot / "release")
        return {}

    monkeypatch.setattr(deploy_cli, "_prepare_slot", prepare)
    return root, old, candidate, older


def test_live_smoke_failure_restores_complete_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    smokes: list[Path] = []

    def smoke(release, *_args):
        smokes.append(release)
        if release == candidate:
            raise OSError("candidate smoke failed")

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )
    with pytest.raises(deploy_cli.DeployError, match="restored"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older
    assert smokes == [candidate, old]


def test_automatic_rollback_proves_old_slot_ready_before_repointing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    readiness: list[tuple[str, str]] = []
    monkeypatch.setattr(
        deploy_cli,
        "_start_recovery_slot",
        lambda _environment, slot, release: readiness.append((slot, release.name))
        or (
            (root / "active").resolve() == (root / "slots" / "green").resolve()
            and (root / "current").resolve() == candidate
        )
        or pytest.fail("rollback pointers moved before old-slot readiness"),
    )
    smokes = iter((OSError("candidate smoke failed"), None))

    def smoke(*_args):
        result = next(smokes)
        if result:
            raise result

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="prior activation was restored"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert readiness == [("blue", "old")]


def test_candidate_failure_leaves_live_activation_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("candidate failed")),
    )

    with pytest.raises(OSError, match="candidate failed"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_shadow_cleanup_failure_is_reported_before_candidate_prepared_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    phases: list[str] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **_values: phases.append(phase),
    )
    monkeypatch.setattr(
        deploy_cli,
        "prepare_candidate_if_enabled",
        lambda *_args: (_ for _ in ()).throw(
            deploy_cli.ExternalPiSlotError("candidate cleanup failed")
        ),
    )

    with pytest.raises(
        deploy_cli.ExternalPiSlotError, match="candidate cleanup failed"
    ):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert phases == ["candidate-preparing"]
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_slot_rollback_qualifies_previous_as_one_complete_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)

    result = deploy_cli.activate_slot(older, "staging", tmp_path / "runtime")

    assert result == "success"
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == older
    assert (root / "previous").resolve() == old


def test_old_external_worker_cleanup_is_deferred_until_after_backend_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    events: list[tuple[str, str, str]] = []
    journals: list[tuple[str, dict]] = []

    def prepare(environment, slot, release_id):
        assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
        assert (root / "current").resolve() == old
        events.append(("prepare", slot, release_id))
        return True

    monkeypatch.setattr(deploy_cli, "prepare_candidate_if_enabled", prepare)
    monkeypatch.setattr(deploy_cli, "external_pi_lifecycle_enabled", lambda *_: True)
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda *_args, **_kwargs: pytest.fail(
            "activation must not wait for external worker cleanup"
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args: None)

    def unix(_environment, slot, path, *, method="GET", **_kwargs):
        if path == "/internal/drain":
            events.append(("drain", slot, old.name))
        return {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        }

    monkeypatch.setattr(deploy_cli, "_unix_json", unix)
    monkeypatch.setattr(
        deploy_cli,
        "_stop_drained_slot",
        lambda _environment, slot: events.append(("backend-stopped", slot, old.name))
        or True,
    )
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)

    assert (
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")
        == "success-with-draining"
    )
    assert events == [
        ("prepare", "green", "candidate"),
        ("drain", "blue", "old"),
        ("backend-stopped", "blue", "old"),
    ]
    assert journals[-1][0] == "live-with-old-external-pi-draining"


def test_old_external_worker_cleanup_is_not_run_inside_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *_args: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *_args, **_kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)
    monkeypatch.setattr(deploy_cli, "external_pi_lifecycle_enabled", lambda *_: True)
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("slow or invalid external cleanup must be deferred")
        ),
    )

    result = deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert result == "success-with-draining"
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == candidate
    assert journals[-1][0] == "live-with-old-external-pi-draining"
    assert journals[-1][1]["draining_slot"] == "blue"
    assert journals[-1][1]["draining_release"] == old.name


def _reap_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend_running: bool,
) -> list[tuple[str, str, str]]:
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    events: list[tuple[str, str, str]] = []
    monkeypatch.setattr(deploy_cli, "require_root", lambda: None)
    monkeypatch.setattr(deploy_cli, "deployment_lock", nullcontext)
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: "blue")
    status = (
        {
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        }
        if backend_running
        else None
    )
    monkeypatch.setattr(deploy_cli, "_unix_json", lambda *_args, **_kwargs: status)

    def stop_backend(environment: str, slot: str) -> bool:
        if not backend_running:
            pytest.fail("already-stopped backend was stopped again")
        events.append(("backend", environment, slot))
        return True

    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", stop_backend)
    monkeypatch.setattr(
        deploy_cli,
        "_slot_release",
        lambda _environment, slot: previous if slot == "green" else current,
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {"release_id": release.name},
    )
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda environment, slot, release_id, **kwargs: events.append(
            (
                "external",
                environment,
                f"{slot}:{release_id}",
                kwargs.get("allow_orphaned_turn_reap"),
            )
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=current, previous=previous),
    )
    monkeypatch.setattr(deploy_cli, "_write_journal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(deploy_cli, "cleanup_releases", lambda: None)
    monkeypatch.setattr(deploy_cli, "cleanup_runtimes", lambda *_args: None)
    monkeypatch.setattr(deploy_cli, "cleanup_external_pi_runtimes", lambda *_args: None)
    monkeypatch.setattr(deploy_cli, "protected_external_pi_runtime_ids", lambda: set())
    return events


def test_reap_stops_drained_backend_before_its_external_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events = _reap_fixture(tmp_path, monkeypatch, backend_running=True)

    assert deploy_cli.reap(SimpleNamespace(environment="staging")) == 0
    assert events == [
        ("backend", "staging", "green"),
        ("external", "staging", "green:previous", True),
    ]


def test_reap_finishes_external_cleanup_when_backend_is_already_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events = _reap_fixture(tmp_path, monkeypatch, backend_running=False)

    assert deploy_cli.reap(SimpleNamespace(environment="staging")) == 0
    assert events == [("external", "staging", "green:previous", True)]


def _deferred_drain_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    phase: str = "live-with-old-external-pi-draining",
    lifecycle_enabled: bool = True,
    backend_status: dict | None = None,
) -> tuple[list[tuple], list[tuple[str, dict]]]:
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    events: list[tuple] = []
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": phase,
            "active_slot": "green",
            "draining_slot": "blue",
            "active_release": current.name,
            "draining_release": previous.name,
        },
    )
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: "green")
    monkeypatch.setattr(
        deploy_cli,
        "external_pi_lifecycle_enabled",
        lambda _environment: lifecycle_enabled,
    )
    monkeypatch.setattr(
        deploy_cli, "_unix_json", lambda *_args, **_kwargs: backend_status
    )

    def stop_backend(environment: str, slot: str) -> bool:
        busy = backend_status and backend_status.get("active_chat_streams")
        if not busy:
            events.append(("backend", environment, slot))
        return not busy

    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", stop_backend)
    monkeypatch.setattr(
        deploy_cli,
        "_slot_release",
        lambda _environment, slot: previous if slot == "blue" else current,
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {"release_id": release.name},
    )
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda environment, slot, release_id, **kwargs: events.append(
            ("external", environment, slot, release_id, kwargs)
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=current, previous=previous),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_start_recovery_slot",
        lambda *_args: pytest.fail("a settled cutover is not rolled back"),
    )
    return events, journals


@pytest.mark.parametrize(
    "phase", ["live-with-old-external-pi-draining", "live-with-old-slot-draining"]
)
@pytest.mark.parametrize("backend_running", [True, False])
def test_next_deploy_reaps_the_displaced_slot_before_reusing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    backend_running: bool,
):
    """After cutover the displaced slot keeps its external Pi supervisor and
    worker until pwc-reap. The next deploy must stop both with that slot's own
    release before start_slot or candidate cleanup touches the slot."""
    idle = {
        "accepting_chat_turns": False,
        "active_http_requests": 0,
        "active_chat_streams": 0,
        "active_gateway_streams": 0,
    }
    events, journals = _deferred_drain_fixture(
        tmp_path,
        monkeypatch,
        phase=phase,
        backend_status=idle if backend_running else None,
    )

    deploy_cli._recover_interrupted_activation("staging")

    expected_external = (
        "external",
        "staging",
        "blue",
        "previous",
        {"allow_orphaned_turn_reap": True},
    )
    assert events == (
        [("backend", "staging", "blue"), expected_external]
        if backend_running
        else [expected_external]
    )
    assert journals == [
        (
            "settled",
            {
                "active_slot": "green",
                "active_release": "current",
                "previous_release": "previous",
            },
        )
    ]


def test_next_deploy_refuses_while_the_displaced_slot_still_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events, journals = _deferred_drain_fixture(
        tmp_path,
        monkeypatch,
        backend_status={
            "accepting_chat_turns": False,
            "active_http_requests": 0,
            "active_chat_streams": 1,
            "active_gateway_streams": 0,
        },
    )

    with pytest.raises(deploy_cli.DeployError, match="still draining"):
        deploy_cli._recover_interrupted_activation("staging")

    assert events == []
    assert journals == []


def test_deferred_drain_without_external_pi_keeps_the_rollback_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events, journals = _deferred_drain_fixture(
        tmp_path,
        monkeypatch,
        phase="live-with-old-slot-draining",
        lifecycle_enabled=False,
    )

    deploy_cli._recover_interrupted_activation("staging")

    assert events == []
    assert journals == []


def test_deferred_drain_journal_must_name_the_displaced_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _deferred_drain_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": "live-with-old-external-pi-draining",
            "draining_slot": "green",
        },
    )

    with pytest.raises(deploy_cli.DeployError, match="draining slot"):
        deploy_cli._recover_interrupted_activation("staging")


def test_initial_slot_bridge_qualifies_shadow_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    root = environments / "staging"
    release = tmp_path / "release"
    release.mkdir()
    (root / "slots/blue").mkdir(parents=True)
    atomic_symlink(release, root / "current")
    events: list[tuple] = []
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=release, previous=None),
    )
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: None)
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda environment, slot, candidate, runtime: events.append(
            ("backend", environment, slot, candidate, runtime)
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "prepare_candidate_if_enabled",
        lambda environment, slot, release_id: events.append(
            ("shadow", environment, slot, release_id)
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda candidate, environment: {"release_id": "release-staging"},
    )
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda environment, phase, **values: events.append(
            ("journal", environment, phase)
        ),
    )

    runtime = tmp_path / "runtime"
    deploy_cli._bridge_qualify_current(release, "staging", runtime)

    assert events[:4] == [
        ("journal", "staging", "candidate-preparing"),
        ("backend", "staging", "blue", release, runtime),
        ("shadow", "staging", "blue", "release-staging"),
        ("journal", "staging", "candidate-prepared"),
    ]


def test_active_slot_qualify_only_prepares_external_pi_before_reporting_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = tmp_path / "candidate"
    release.mkdir()
    runtime = tmp_path / "runtime"
    events: list[tuple] = []
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda environment, slot, candidate, python_runtime: events.append(
            ("backend", environment, slot, candidate, python_runtime)
        )
        or {"ready": True},
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda candidate, environment: {"release_id": "candidate-staging"},
    )
    monkeypatch.setattr(
        deploy_cli,
        "prepare_candidate_if_enabled",
        lambda environment, slot, release_id: events.append(
            ("shadow", environment, slot, release_id)
        ),
    )

    result = deploy_cli._prepare_qualified_slot("staging", "green", release, runtime)

    assert result == {"ready": True}
    assert events == [
        ("backend", "staging", "green", release, runtime),
        ("shadow", "staging", "green", "candidate-staging"),
    ]


def test_active_slot_qualify_only_rejects_flag_mismatch_before_backend_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        deploy_cli,
        "external_pi_lifecycle_enabled",
        lambda _environment: (_ for _ in ()).throw(
            deploy_cli.ExternalPiSlotError("flags disagree")
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda *_args: pytest.fail("backend candidate mutated before flag validation"),
    )

    with pytest.raises(deploy_cli.ExternalPiSlotError, match="flags disagree"):
        deploy_cli._prepare_qualified_slot(
            "staging", "green", tmp_path / "release", tmp_path / "runtime"
        )


def test_shadow_candidate_is_drained_on_automatic_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    stopped: list[tuple[str, str]] = []
    monkeypatch.setattr(deploy_cli, "prepare_candidate_if_enabled", lambda *_args: True)
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda _environment, slot, release_id: stopped.append((slot, release_id)),
    )
    smokes = iter((OSError("candidate failed"), None))

    def smoke(*_args):
        result = next(smokes)
        if result:
            raise result

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="prior activation was restored"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert stopped == [("green", "candidate")]
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old


def test_automatic_rollback_reports_unproven_candidate_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    phases: list[str] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **_values: phases.append(phase),
    )
    monkeypatch.setattr(deploy_cli, "prepare_candidate_if_enabled", lambda *_args: True)

    def unproven_cleanup(_environment, slot, release_id):
        assert (slot, release_id) == ("green", "candidate")
        raise deploy_cli.ExternalPiSlotError("worker did not prove graceful drain")

    monkeypatch.setattr(deploy_cli, "stop_slot_if_enabled", unproven_cleanup)
    smokes = iter((OSError("candidate failed"), None))

    def smoke(*_args):
        result = next(smokes)
        if result:
            raise result

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="candidate drain failed"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert phases[-1] == "automatic-rollback-candidate-drain-failed"
    assert "automatic-rollback-complete" not in phases


def test_draining_previous_slot_is_undrained_and_reused_for_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    atomic_symlink(candidate, root / "slots" / "green" / "release")
    runtime = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []
    existing = {
        "release_id": "candidate",
        "runtime_id": "runtime",
        "slot": "green",
        "accepting_chat_turns": False,
        "active_http_requests": 1,
    }

    def unix(_environment, _slot, path, *, method="GET", **_kwargs):
        calls.append((method, path))
        return existing

    monkeypatch.setattr(deploy_cli, "_unix_json", unix)
    monkeypatch.setattr(
        deploy_cli,
        "_wait_slot",
        lambda *_args, **_kwargs: {**existing, "accepting_chat_turns": True},
    )
    monkeypatch.setattr(
        deploy_cli,
        "_smoke_slot_candidate",
        lambda *_args, **_kwargs: calls.append(("SMOKE", "candidate")),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda *_args, **_kwargs: pytest.fail("exact rollback slot was restarted"),
    )

    status = deploy_cli._prepare_or_reuse_slot("staging", "green", candidate, runtime)

    assert status["accepting_chat_turns"] is True
    assert calls == [
        ("GET", "/internal/deployment-status"),
        ("POST", "/internal/undrain"),
        ("SMOKE", "candidate"),
    ]


def test_cleanup_retains_every_pointer_and_slot_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    releases = tmp_path / "releases"
    runtimes = tmp_path / "runtimes"
    environments = tmp_path / "environments"
    releases.mkdir()
    runtimes.mkdir()
    protected = {}
    for name in ("current", "previous", "candidate"):
        release = releases / name
        release.mkdir()
        (release / "uv.lock").write_text(f"{name}-lock")
        protected[name] = release
        (runtimes / runtime_id(release)).mkdir()
    stale = releases / "stale"
    stale.mkdir()
    (stale / "uv.lock").write_text("stale-lock")
    stale_runtime = runtimes / runtime_id(stale)
    stale_runtime.mkdir()

    for environment in ("production", "staging"):
        root = environments / environment
        (root / "slots" / "blue").mkdir(parents=True)
        (root / "slots" / "green").mkdir()
        atomic_symlink(protected["current"], root / "current")
        atomic_symlink(protected["previous"], root / "previous")
    atomic_symlink(
        protected["candidate"],
        environments / "staging" / "slots" / "green" / "release",
    )
    monkeypatch.setattr(deploy_cli, "RELEASES", releases)
    monkeypatch.setattr(deploy_cli, "RUNTIMES", runtimes)
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)

    deploy_cli.cleanup_releases()
    runtime_module.cleanup_runtimes(runtimes, deploy_cli.protected_runtime_ids())

    assert {path.name for path in releases.iterdir()} == set(protected)
    assert {path.name for path in runtimes.iterdir()} == {
        runtime_id(release) for release in protected.values()
    }
    assert not stale_runtime.exists()


def test_busy_old_slot_is_retained_after_successful_cutover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 1,
            "active_chat_streams": 1,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 0)

    result = deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert result == "success-with-draining"
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == candidate
    assert (root / "previous").resolve() == old
    phase, values = journals[-1]
    assert phase == "live-with-old-slot-draining"
    assert values["streams_surviving_cutover"] == {
        "active_http_requests": 1,
        "active_chat_streams": 1,
        "active_gateway_streams": 0,
    }
    assert values["forced_termination_count"] == 0


def test_same_release_finalizes_bridge_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(deploy_cli, "_wait_slot", lambda *args, **kwargs: {})
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )

    result = deploy_cli.activate_slot(old, "staging", tmp_path / "runtime")

    assert result == "success"
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert journals[-1] == (
        "settled",
        {
            "active_slot": "blue",
            "active_release": "old",
            "previous_release": "older",
            "forced_termination_count": 0,
        },
    )


def test_same_release_environment_refresh_restarts_inactive_slot_and_preserves_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    prepared: list[tuple[str, Path]] = []

    def prepare(_environment, slot, release, _runtime):
        prepared.append((slot, release))
        atomic_symlink(release, root / "slots" / slot / "release")
        return {}

    monkeypatch.setattr(deploy_cli, "_prepare_slot", prepare)
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_or_reuse_slot",
        lambda *_args, **_kwargs: pytest.fail("refresh reused a running slot"),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)

    result = deploy_cli.activate_slot(
        old,
        "staging",
        tmp_path / "runtime",
        refresh_environment=True,
    )

    assert result == "success"
    assert prepared == [("green", old)]
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_environment_refresh_rejects_a_different_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root, _old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)

    with pytest.raises(
        deploy_cli.DeployError,
        match="--refresh-environment requires the active release",
    ):
        deploy_cli.activate_slot(
            candidate,
            "staging",
            tmp_path / "runtime",
            refresh_environment=True,
        )


def test_environment_refresh_smoke_failure_restores_active_slot_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    smokes = 0

    def smoke(*_args, **_kwargs):
        nonlocal smokes
        smokes += 1
        if smokes == 1:
            raise OSError("refreshed environment failed smoke")

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="prior activation was restored"):
        deploy_cli.activate_slot(
            old,
            "staging",
            tmp_path / "runtime",
            refresh_environment=True,
        )

    assert smokes == 2
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_legacy_service_retires_only_after_nginx_slot_migration(
    monkeypatch: pytest.MonkeyPatch,
):
    commands: list[list[str]] = []
    events: list[tuple] = []
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: commands.append(command)
    )
    monkeypatch.setattr(
        deploy_cli, "log_event", lambda *args, **kwargs: events.append((args, kwargs))
    )
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: False
    )

    assert not deploy_cli._retire_legacy_service("staging")
    assert commands == []

    states = iter(["active", "inactive"])
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: True
    )
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda _unit: next(states))
    monkeypatch.setattr(
        deploy_cli,
        "_systemctl_enabled_state",
        lambda _unit: "enabled" if not commands else "disabled",
    )

    assert deploy_cli._retire_legacy_service("staging")
    assert commands == [
        [
            "systemctl",
            "disable",
            "--now",
            "paperswithcode-backend@staging.service",
        ]
    ]
    assert events == [
        (
            ("legacy-retire", "staging", "success"),
            {"unit": "paperswithcode-backend@staging.service"},
        )
    ]


def test_legacy_service_is_disabled_even_when_already_inactive(
    monkeypatch: pytest.MonkeyPatch,
):
    commands: list[list[str]] = []
    monkeypatch.setattr(deploy_cli, "_nginx_uses_active_slot", lambda _env: True)
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda _unit: "inactive")
    enabled_states = iter(["enabled", "disabled"])
    monkeypatch.setattr(
        deploy_cli, "_systemctl_enabled_state", lambda _unit: next(enabled_states)
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: commands.append(command)
    )
    monkeypatch.setattr(deploy_cli, "log_event", lambda *_args, **_kwargs: None)

    assert deploy_cli._retire_legacy_service("production")
    assert commands == [
        [
            "systemctl",
            "disable",
            "--now",
            "paperswithcode-backend@production.service",
        ]
    ]


def test_persist_active_slot_enables_only_its_socket(
    monkeypatch: pytest.MonkeyPatch,
):
    commands: list[list[str]] = []
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: commands.append(command)
    )

    deploy_cli._persist_active_slot_socket("production", "green")

    assert commands == [
        ["systemctl", "enable", "paperswithcode-production-backend@green.socket"],
        ["systemctl", "disable", "paperswithcode-production-backend@blue.socket"],
    ]


@pytest.mark.parametrize(
    ("phase", "current_switched", "active_switched"),
    [
        ("previous-update-pending", False, False),
        ("current-update-pending", False, False),
        ("active-switch-pending", True, False),
        ("active-switched-smoke-pending", True, True),
        ("automatic-rollback-in-progress", True, True),
    ],
)
def test_interrupted_cutover_recovers_from_every_mutation_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    current_switched: bool,
    active_switched: bool,
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    atomic_symlink(candidate, root / "slots" / "green" / "release")
    if current_switched:
        atomic_symlink(candidate, root / "current")
        atomic_symlink(old, root / "previous")
    if active_switched:
        atomic_symlink(root / "slots" / "green", root / "active")
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": phase,
            "old_slot": "blue",
            "old_release": old.name,
            "original_previous": older.name,
        },
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: commands.append(command)
    )
    monkeypatch.setattr(deploy_cli, "_start_recovery_slot", START_RECOVERY_SLOT)
    monkeypatch.setattr(
        deploy_cli,
        "_persist_active_slot_socket",
        lambda environment, slot: commands.extend(
            [
                [
                    "systemctl",
                    "enable",
                    deploy_cli._slot_unit(environment, slot, "socket"),
                ],
                [
                    "systemctl",
                    "disable",
                    deploy_cli._slot_unit(
                        environment,
                        "green" if slot == "blue" else "blue",
                        "socket",
                    ),
                ],
            ]
        ),
    )
    initial_current = (root / "current").resolve()
    initial_active = (root / "active").resolve()
    requests: list[tuple[str, str]] = []

    def unix(_environment, slot, path, *, method="GET", **_kwargs):
        requests.append((method, path))
        if path in {"/internal/deployment-status", "/health"}:
            assert (root / "current").resolve() == initial_current
            assert (root / "active").resolve() == initial_active
        if path == "/internal/deployment-status":
            return {"release_id": "old", "slot": slot}
        if path == "/health":
            return {"release_id": "old"}
        assert path == "/internal/undrain"
        assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
        assert (root / "current").resolve() == old
        return {"accepting_chat_turns": True}

    monkeypatch.setattr(deploy_cli, "_unix_json", unix)
    smokes: list[Path] = []
    lifecycle_events: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda environment, slot, release_id: lifecycle_events.append(
            ("stop", slot, release_id)
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "prepare_candidate_if_enabled",
        lambda environment, slot, release_id: lifecycle_events.append(
            ("prepare", slot, release_id)
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "smoke_public",
        lambda release, *_args: smokes.append(release),
    )

    deploy_cli._recover_interrupted_activation("staging")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older
    assert smokes == [old]
    assert lifecycle_events == [
        ("stop", "green", "candidate"),
        ("prepare", "blue", "old"),
    ]
    assert requests[:3] == [
        ("GET", "/internal/deployment-status"),
        ("GET", "/health"),
        ("POST", "/internal/undrain"),
    ]
    assert commands == [
        ["systemctl", "start", "paperswithcode-staging-backend@blue.socket"],
        ["systemctl", "start", "paperswithcode-staging-backend@blue.service"],
        ["systemctl", "enable", "paperswithcode-staging-backend@blue.socket"],
        ["systemctl", "disable", "paperswithcode-staging-backend@green.socket"],
    ]


@pytest.mark.parametrize("backend_stopped", (True, False))
def test_interrupted_candidate_recovery_stops_backend_before_orphan_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend_stopped: bool
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _: {
            "phase": "candidate-preparing",
            "candidate_slot": "green",
            "candidate_release": candidate.name,
        },
    )
    events = []
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda environment, slot, path, **kw: events.append(
            (slot, path, kw.get("method"))
        ),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_stop_drained_slot",
        lambda environment, slot: events.append((slot, "backend-stop"))
        or backend_stopped,
    )

    def stop(environment, slot, release_id, **kwargs):
        assert kwargs["allow_orphaned_turn_reap"] is True
        assert kwargs["validated_orphan_release_ids"] == frozenset(
            {old.name, older.name}
        )
        events.append((slot, "worker-stop"))

    monkeypatch.setattr(deploy_cli, "stop_slot_if_enabled", stop)

    if backend_stopped:
        deploy_cli._recover_interrupted_activation("staging")
    else:
        with pytest.raises(deploy_cli.DeployError, match="candidate backend.*drain"):
            deploy_cli._recover_interrupted_activation("staging")
    assert events == [
        ("green", "/internal/drain", "POST"),
        ("green", "backend-stop"),
    ] + ([("green", "worker-stop")] if backend_stopped else [])
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old


def test_interrupted_candidate_recovery_does_not_abandon_unproven_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": "candidate-preparing",
            "candidate_slot": "green",
            "candidate_release": candidate.name,
        },
    )
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            deploy_cli.ExternalPiSlotError("worker did not prove graceful drain")
        ),
    )
    phases: list[str] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **_values: phases.append(phase),
    )

    with pytest.raises(deploy_cli.ExternalPiSlotError, match="prove graceful drain"):
        deploy_cli._recover_interrupted_activation("staging")

    assert phases == []
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_interrupted_candidate_recovery_never_stops_the_active_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    (root / "active").unlink()
    (root / "active").symlink_to(root / "slots" / "green")
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": "candidate-prepared",
            "candidate_slot": "green",
            "candidate_release": candidate.name,
        },
    )
    monkeypatch.setattr(
        deploy_cli,
        "stop_slot_if_enabled",
        lambda *_args, **_kwargs: pytest.fail("active slot must not be stopped"),
    )

    with pytest.raises(
        deploy_cli.DeployError, match="candidate slot is already active"
    ):
        deploy_cli._recover_interrupted_activation("staging")


def test_interrupted_candidate_recovery_trusts_only_validated_release_pointers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": "candidate-preparing",
            "candidate_slot": "green",
            "candidate_release": candidate.name,
        },
    )
    calls: list[tuple[str, str, str, frozenset[str]]] = []

    def stop(
        environment: str,
        slot: str,
        release_id: str,
        *,
        validated_orphan_release_ids: frozenset[str],
        allow_orphaned_turn_reap: bool,
    ) -> None:
        assert allow_orphaned_turn_reap
        calls.append((environment, slot, release_id, validated_orphan_release_ids))

    monkeypatch.setattr(deploy_cli, "stop_slot_if_enabled", stop)
    phases: list[str] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **_values: phases.append(phase),
    )

    deploy_cli._recover_interrupted_activation("staging")

    assert calls == [
        ("staging", "green", "candidate", frozenset({old.name, older.name}))
    ]
    assert phases == ["candidate-abandoned"]


def test_interrupted_candidate_recovery_trusts_validated_pointers_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    staging_root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    production_root = staging_root.parent / "production"
    staging_root.rename(production_root)
    (production_root / "active").unlink()
    (production_root / "active").symlink_to(production_root / "slots" / "blue")
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": "candidate-preparing",
            "candidate_slot": "green",
            "candidate_release": candidate.name,
        },
    )
    calls: list[tuple[str, str, str, frozenset[str]]] = []

    def stop(
        environment: str,
        slot: str,
        release_id: str,
        *,
        validated_orphan_release_ids: frozenset[str],
        allow_orphaned_turn_reap: bool,
    ) -> None:
        assert allow_orphaned_turn_reap
        calls.append((environment, slot, release_id, validated_orphan_release_ids))

    monkeypatch.setattr(deploy_cli, "stop_slot_if_enabled", stop)

    deploy_cli._recover_interrupted_activation("production")

    assert calls == [
        ("production", "green", "candidate", frozenset({old.name, older.name}))
    ]


def test_certificate_reload_rejects_another_lineage(monkeypatch):
    monkeypatch.setenv("RENEWED_LINEAGE", "/etc/letsencrypt/live/paperswithcode.co")
    with pytest.raises(RuntimeError, match="selected executor certificate"):
        nginx_tool_module.reload_renewed_certificate("production")


def test_certificate_reload_validates_before_reload_and_smokes(monkeypatch):
    monkeypatch.setenv(
        "RENEWED_LINEAGE", "/etc/letsencrypt/live/chat-executor.paperswithcode.co"
    )
    monkeypatch.setattr(nginx_tool_module, "active_release_id", lambda _: "release")
    calls = []
    monkeypatch.setattr(
        nginx_tool_module.subprocess, "run", lambda args, **kwargs: calls.append(args)
    )
    nginx_tool_module.reload_renewed_certificate("production")
    assert calls == [
        ["nginx", "-t"],
        ["systemctl", "reload", "nginx"],
        nginx_tool_module.smoke_command("production", "release"),
    ]


def test_invalid_nginx_configuration_prevents_certificate_reload(monkeypatch):
    monkeypatch.setenv(
        "RENEWED_LINEAGE", "/etc/letsencrypt/live/chat-executor.paperswithcode.co"
    )
    monkeypatch.setattr(nginx_tool_module, "active_release_id", lambda _: "release")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(nginx_tool_module.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        nginx_tool_module.reload_renewed_certificate("production")
    assert calls == [["nginx", "-t"]]
