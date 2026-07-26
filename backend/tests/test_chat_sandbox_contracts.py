from __future__ import annotations

import json
import asyncio
import importlib
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from claude_agent_sdk import StreamEvent

from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    IMAGE_PUBLISH_NAME,
    MODAL_APP_NAME,
    MODAL_IMAGE_ID,
)
from backend.chat_sandbox_worker import supervisor
from backend.chat_sandbox_worker.sdk_adapter import SDKEventAdapter as WorkerSDKAdapter
from backend.chat_sandbox_worker.prompt import render, sha256
from backend.chat_sandbox_worker import publish_image
from backend.chat_sandbox_worker.protocol import (
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.scripts.qualify_chat_sandbox import QualificationRunner, Sample, summarize
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, sse_event
from backend.models.database import ChatTurnCapability
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
    _digest,
)
from backend.services.chat_sandbox_service import WorkspaceSnapshotProvider
from backend.services.chat_sandbox_service import resolve_modal_image
from backend.services.chat_sandbox_service import RunningWorker, SandboxSessionManager
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output
from backend.chat_gateway_app import (
    MAX_PROVIDER_OUTPUT_TOKENS,
    MAX_PROVIDER_TURN_TOKENS,
    _output_tokens_allowed,
)
from deploy.release import build_manifest


def test_broker_accepts_claude_messages_beta_query(monkeypatch):
    read_fd, write_fd = os.pipe()
    try:
        os.write(
            write_fd,
            json.dumps(
                {
                    "capability": "test-capability",
                    "gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
                    "session_id": str(uuid.uuid4()),
                    "turn_id": str(uuid.uuid4()),
                }
            ).encode(),
        )
    finally:
        os.close(write_fd)
    monkeypatch.setenv("PWC_BROKER_CONFIG_FD", str(read_fd))
    sys.modules.pop("backend.chat_sandbox_worker.broker", None)
    broker = importlib.import_module("backend.chat_sandbox_worker.broker")

    class Request:
        path = "/v1/messages?beta=true"
        headers = {"Content-Length": "2", "Content-Type": "application/json"}
        rfile = BytesIO(b"{}")
        forwarded: list[tuple[str, bytes]] = []
        error: int | None = None

        def _forward(self, path, body, **_kwargs):
            self.forwarded.append((path, body))

        def send_error(self, status):
            self.error = status

    request = Request()
    broker.Handler.do_POST(request)

    assert request.forwarded == [("v1/messages", b"{}")]
    assert request.error is None


def test_supervisor_launch_read_does_not_consume_worker_frame():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"private-launch\nworker-frame\n")
        assert supervisor._readline_unbuffered(read_fd, 64) == b"private-launch\n"
        assert os.read(read_fd, 64) == b"worker-frame\n"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_gateway_accepts_claude_output_token_limit_and_rejects_larger():
    assert MAX_PROVIDER_OUTPUT_TOKENS == 32_000
    assert MAX_PROVIDER_TURN_TOKENS >= 8 * MAX_PROVIDER_OUTPUT_TOKENS
    assert _output_tokens_allowed(32_000)
    assert not _output_tokens_allowed(32_001)


def test_worker_adapter_assembles_streamed_tool_arguments():
    adapter = WorkerSDKAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="session",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Bash",
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="session",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"command":"pwc search on-device"}',
                },
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="session",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {
            "type": "tool_call",
            "id": "tool-1",
            "name": "Bash",
            "args": {"command": "pwc search on-device"},
        }
    ]


def test_generic_tool_projection_and_event_are_v2_raw_text():
    block = DISPLAY_BLOCKS_ADAPTER.validate_python(
        [
            {
                "kind": "tool",
                "schema_version": 2,
                "id": "tool-1",
                "name": "Bash",
                "args": {"command": "pwc search vision"},
                "status": "success",
                "took_ms": 25,
                "content": [
                    {"type": "text", "text": "id\ttitle\n1\tPaper", "truncated": False}
                ],
                "metadata": {"exit_code": 0, "output_truncated": False},
            }
        ]
    )[0]
    assert block.name == "Bash"
    assert b'"status":"success"' in sse_event(
        "tool_result",
        id="tool-1",
        status="success",
        took_ms=25,
        content=[{"type": "text", "text": "ok", "truncated": False}],
        metadata={"exit_code": 0, "output_truncated": False},
    )


def test_tool_budget_counts_parallel_calls_and_fifth_search_is_denied():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    for index in range(4):
        assert budget.authorize(
            f"tool-{index}", "Bash", {"command": f"pwc search query-{index}"}
        ).allowed
    denied = budget.authorize("tool-5", "Bash", {"command": "pwc search fifth"})
    assert not denied.allowed
    assert budget.calls == 4


def test_tool_output_is_utf8_bounded_and_terminal_controls_are_inert():
    text, truncated = bound_tool_output(b"\x1b[31m" + "é".encode() * 100, 64)
    assert truncated
    assert "\x1b" not in text
    assert len(text.encode()) <= 64


def test_tool_policy_rejects_traversal_and_enforces_aggregate_bytes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guide = tmp_path / "CLI_GUIDE.md"
    guide.write_text("guide")
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=24,
        maximum_turn_output_bytes=48,
    )
    denied = budget.authorize(
        "outside",
        "Read",
        {"file_path": str(tmp_path / "secret")},
        workspace=workspace,
        guide=guide,
    )
    assert not denied.allowed
    for index in range(3):
        tool_id = f"tool-{index}"
        assert budget.authorize(
            tool_id,
            "Bash",
            {"command": "printf data"},
            workspace=workspace,
            guide=guide,
        ).allowed
        result = budget.result(tool_id, "x" * 100, status="success")
        assert len(result["content"][0]["text"].encode()) <= 24
    assert budget.output_bytes == 48


def test_worker_protocol_accepts_complete_turn_after_one_terminal():
    frame = {"v": 1, "type": "run_turn", "request_id": "r"}
    assert decode_frame(encode_frame(frame)) == frame
    validator = WorkerEventValidator()
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    validator.accept({"type": "worker_done", "status": "complete"})


def test_worker_protocol_rejects_invalid_result_and_terminal_sequences():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="Uncorrelated"):
        validator.accept({"type": "tool_result", "id": "missing"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "answer_delta", "text": "late"})
    with pytest.raises(ProtocolError, match="Duplicate terminal"):
        validator.accept({"type": "error"})


def test_worker_protocol_requires_terminal_before_successful_completion():
    validator = WorkerEventValidator()

    with pytest.raises(ProtocolError, match="without a semantic terminal"):
        validator.accept({"type": "worker_done", "status": "complete"})
    with pytest.raises(ProtocolError, match="Invalid worker completion status"):
        validator.accept({"type": "worker_done", "status": "unknown"})


def test_worker_protocol_allows_terminal_less_correlated_cancellation():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="without a correlated cancellation"):
        validator.accept({"type": "worker_done", "status": "stopped"})

    validator.accept(
        {"type": "worker_done", "status": "stopped"},
        allow_terminal_less_stop=True,
    )

    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "worker_done", "status": "stopped"})
    with pytest.raises(ProtocolError, match="followed worker completion"):
        validator.accept({"type": "done"})


def test_prompt_and_manifest_share_eight_round_contract():
    prompt = render()
    assert "at most 8 tool-use round trips" in prompt
    assert "--json only" in prompt
    manifest = build_manifest("a" * 40, "staging")
    assert manifest["chat_runtime"]["system_prompt_sha256"] == sha256()
    assert manifest["chat_runtime"]["new_chat_modal_percentage"] == 100
    production = build_manifest("b" * 40, "production")
    assert production["chat_runtime"]["enabled"] is False
    assert json.dumps(production["chat_runtime"]).count("pwc-chat") == 0
    assert IMAGE_PUBLISH_NAME == "pwc-chat-v1"
    assert MODAL_APP_NAME == "pwc-chat-sandbox-v1"
    assert BASE_IMAGE.startswith("python:3.12-slim-bookworm@sha256:")
    assert MODAL_IMAGE_ID == "im-QkSSQJcTzpe8ub4Yi7zJRj"


def test_image_makes_copied_worker_readable_and_installs_guide():
    source = (
        Path(__file__).resolve().parents[1] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert 'WORKER / "CLI_GUIDE.md", "/opt/pwc/CLI_GUIDE.md"' in source
    assert '"chmod -R a+rX /opt/pwc/backend"' in source
    assert '"chmod 0644 /opt/pwc/CLI_GUIDE.md /opt/pwc/install-pwc.py"' in source
    assert '"chown pwc-broker:pwc-broker /var/empty/pwc-broker"' in source


def test_image_publication_initializes_modal_app(monkeypatch, capsys):
    events: list[str] = []

    class Lookup:
        async def aio(self, name, *, create_if_missing):
            assert name == MODAL_APP_NAME
            assert create_if_missing is True
            events.append("lookup")

    class Run:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *_args):
            events.append("exit")

    class App:
        def run(self):
            return Run()

    class Built:
        object_id = "im-test"

        def publish(self, name):
            assert events == ["lookup", "enter", "build"]
            events.append(f"publish:{name}")

    class Image:
        def build(self, _app):
            assert events == ["lookup", "enter"]
            events.append("build")
            return Built()

    monkeypatch.setattr(publish_image, "app", App())
    monkeypatch.setattr(publish_image, "image", Image())
    monkeypatch.setattr(publish_image.modal.App, "lookup", Lookup())

    assert publish_image.main() == 0
    assert events == [
        "lookup",
        "enter",
        "build",
        f"publish:{IMAGE_PUBLISH_NAME}",
        "exit",
    ]
    assert capsys.readouterr().out == "im-test\n"


def test_immutable_modal_image_uses_supported_constructor(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: sentinel if image_id == "im-test" else None,
    )

    assert asyncio.run(resolve_modal_image("im-test")) is sentinel


def test_supervisor_tolerates_unsupported_proc_remount(monkeypatch):
    monkeypatch.setattr(
        supervisor.Path,
        "read_text",
        lambda *_args, **_kwargs: "none /proc proc rw 0 0\n",
    )

    class Result:
        returncode = 32

    calls: list[list[str]] = []

    def run(command, **options):
        calls.append(command)
        assert options["check"] is False
        return Result()

    monkeypatch.setattr(supervisor.subprocess, "run", run)

    supervisor._harden_proc()
    assert calls == [["mount", "-o", "remount,hidepid=2,nosuid,nodev", "/proc"]]


def test_supervisor_child_environment_preserves_packaged_worker_path(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_MAX_TURNS", "8")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")

    environment = supervisor._safe_environment("/var/empty/pwc-broker")

    assert environment["PYTHONPATH"] == "/opt/pwc"
    assert environment["PWC_CHAT_MAX_TURNS"] == "8"
    assert "ANTHROPIC_API_KEY" not in environment


def test_resource_probe_treats_ephemeral_disk_as_provider_managed(monkeypatch):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    probes: list[str] = []

    async def record(name, *_command, **_options):
        probes.append(name)

    monkeypatch.setattr(runner, "_resource_probe", record)

    assert asyncio.run(runner.run_resource_probes()) == {
        "pids": "enforced",
        "disk": "provider_managed_ephemeral",
        "memory": "enforced",
    }
    assert probes == ["pids", "memory"]


def test_capability_is_exactly_scoped_and_metered():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    token = "opaque-test-token"
    row = ChatTurnCapability(
        id=uuid.uuid4(),
        token_hash=_digest(token),
        chat_session_id=session_id,
        turn_id=turn_id,
        owner_hash="a" * 64,
        model="model-a",
        scopes=["catalog"],
        nonce="b" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        gateway_calls=0,
        provider_requests=0,
        provider_tokens=0,
        catalog_search_calls=0,
    )

    class Result:
        def scalar_one_or_none(self):
            return row

    class DB:
        def execute(self, _query):
            return Result()

        def flush(self):
            pass

    service = ChatCapabilityService(DB())
    assert (
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
        is row
    )
    assert row.gateway_calls == 1
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="model",
            chat_session_id=session_id,
            turn_id=turn_id,
        )
    with pytest.raises(CapabilityError):
        service.validate(
            token,
            scope="catalog",
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
        )


def test_workspace_snapshot_provider_only_snapshots_workspace():
    calls: list[tuple[str, int, int]] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Image:
        object_id = "im-snapshot"

        def __init__(self):
            self.hydrate = AsyncCall(self._hydrate)

        async def _hydrate(self):
            return self

    async def snapshot(path, *, timeout, ttl):
        calls.append((path, timeout, ttl))
        return Image()

    class Sandbox:
        snapshot_directory = AsyncCall(snapshot)

    provider = WorkspaceSnapshotProvider(ttl_days=30)
    assert asyncio.run(provider.save(Sandbox(), uuid.uuid4())) == "im-snapshot"
    assert calls == [("/workspace", 55, 30 * 24 * 60 * 60)]


def test_workspace_snapshot_restore_uses_supported_image_constructor(monkeypatch):
    image = object()
    mounted: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: image if image_id == "im-snapshot" else None,
    )

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    async def mount(path, mounted_image):
        mounted.append((path, mounted_image))

    class Sandbox:
        mount_image = AsyncCall(mount)

    provider = WorkspaceSnapshotProvider()
    asyncio.run(provider.restore(Sandbox(), "im-snapshot"))
    assert mounted == [("/workspace", image)]


def test_sandbox_cancel_correlates_to_original_run_request():
    writes: list[bytes] = []

    class AsyncCall:
        def __init__(self, function):
            self.aio = function

    class Stdin:
        def __init__(self):
            self.drain = AsyncCall(self._drain)

        def write(self, value):
            writes.append(value)

        async def _drain(self):
            return None

    class Process:
        stdin = Stdin()

        def __init__(self):
            self.wait = AsyncCall(self._wait)

        async def _wait(self):
            return None

    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = type("Settings", (), {"chat_cancel_grace_seconds": 1})()
    turn_id = uuid.uuid4()
    running = RunningWorker(Process(), "original-request")
    manager._processes = {turn_id: running}

    assert asyncio.run(manager.cancel(uuid.uuid4(), turn_id))
    assert running.cancel_requested
    assert decode_frame(writes[0].rstrip(b"\n"))["request_id"] == ("original-request")


def test_session_store_rejects_bad_shape_before_touching_database():
    class DB:
        def execute(self, _statement):
            raise AssertionError("database must not be touched")

    gateway = ChatSessionStoreGateway(
        DB(),
        type(
            "Settings",
            (),
            {
                "chat_session_byte_limit": 1024,
                "chat_user_byte_limit": 4096,
            },
        )(),
    )
    with pytest.raises(SessionStoreGatewayError, match="Unsupported"):
        gateway.execute(
            ChatTurnCapability(),
            SessionStoreCommand(
                action="delete",
                key=None,
                entries=None,
                project_key=None,
            ),
        )


def test_qualification_summary_uses_nearest_rank_p95():
    samples = [
        Sample(
            cold_start_ms=value,
            exec_ms=value * 2,
            termination_ms=value * 3,
            snapshot_ms=value if value <= 3 else None,
            restore_ms=value + 1 if value <= 3 else None,
        )
        for value in range(1, 21)
    ]
    result = summarize(samples)
    assert result["cold_start_ms"] == {
        "count": 20,
        "min": 1,
        "p50": 10,
        "p95": 19,
        "max": 20,
    }
    assert result["snapshot_ms"]["count"] == 3


def test_sandbox_migration_is_staging_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_sandbox_runtime.sql"
    ).read_text()
    assert "current_schema() <> 'staging'" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
