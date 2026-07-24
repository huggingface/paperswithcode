from __future__ import annotations

import json
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.contract import (
    IMAGE_PUBLISH_NAME,
    MODAL_IMAGE_ID,
)
from backend.chat_sandbox_worker.prompt import render, sha256
from backend.chat_sandbox_worker.protocol import (
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.scripts.qualify_chat_sandbox import Sample, summarize
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, sse_event
from backend.models.database import ChatTurnCapability
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
    _digest,
)
from backend.services.chat_sandbox_service import WorkspaceSnapshotProvider
from backend.services.chat_sandbox_service import RunningWorker, SandboxSessionManager
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)
from backend.chat_sandbox_worker.tool_policy import ToolBudget, bound_tool_output
from deploy.release import build_manifest


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


def test_worker_protocol_rejects_uncorrelated_and_duplicate_results():
    frame = {"v": 1, "type": "run_turn", "request_id": "r"}
    assert decode_frame(encode_frame(frame)) == frame
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "missing"})
    validator.accept({"type": "tool_call", "id": "t"})
    validator.accept({"type": "tool_result", "id": "t"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "tool_result", "id": "t"})
    validator.accept({"type": "done"})
    with pytest.raises(ProtocolError):
        validator.accept({"type": "answer_delta", "text": "late"})


def test_prompt_and_manifest_share_eight_round_contract():
    prompt = render()
    assert "at most 8 tool-use round trips" in prompt
    assert "--json only" in prompt
    manifest = build_manifest("a" * 40, "staging")
    assert manifest["chat_runtime"]["system_prompt_sha256"] == sha256()
    assert manifest["chat_runtime"]["new_chat_modal_percentage"] == 0
    production = build_manifest("b" * 40, "production")
    assert production["chat_runtime"]["enabled"] is False
    assert json.dumps(production["chat_runtime"]).count("pwc-chat") == 0
    assert IMAGE_PUBLISH_NAME == "pwc-chat-v1"
    assert MODAL_IMAGE_ID == ""


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
    manager._processes = {turn_id: RunningWorker(Process(), "original-request")}

    assert asyncio.run(manager.cancel(uuid.uuid4(), turn_id))
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
