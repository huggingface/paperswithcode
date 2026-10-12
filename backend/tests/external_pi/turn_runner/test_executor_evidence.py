"""Executor start evidence, legacy admission, and lazy turn binding."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_external_pi_tool_executor import (
    ExternalPiToolWorkspaceExecutor,
)
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionResult,
)
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeWorkspaceManager,
    _tool_runner,
)


def test_workspace_ack_is_not_misreported_as_executor_start():
    events = []
    contexts = []

    class Executor:
        async def ensure_workspace(self, context):
            contexts.append(context)
            events.append("workspace_ack")

    turn_id = uuid.uuid4()
    session_id = uuid.uuid4()
    owner = SimpleNamespace(
        admission=SimpleNamespace(
            turn_id=turn_id,
            session_id=session_id,
            durable_claim=TurnLeaseClaim(turn_id, "production-green-00", 4, 9),
        ),
        capability=SimpleNamespace(
            token="capability", expires_at=datetime.now(UTC) + timedelta(minutes=4)
        ),
        executor=Executor(),
        record_evidence=lambda **values: events.append(values) or True,
        active_context=None,
    )
    owner._durable_turn_claim = lambda: owner.admission.durable_claim
    workspace = SimpleNamespace(
        sandbox=object(),
        workspace_generation=1,
        worker_generation="generation-a",
    )

    asyncio.run(
        ExternalPiToolWorkspaceExecutor._ensure_executor(
            owner,
            workspace,
            "call_BRXcbfqP7dwS0QnvatEH7mtL|fc_unsafe-provider-id",
            "operation-a",
        )
    )

    assert events == ["workspace_ack"]
    assert contexts[0].tool_call_id == "operation-a"
    assert contexts[0].turn_worker_id == "production-green-00"
    assert contexts[0].turn_worker_generation == "4"
    assert contexts[0].turn_lease_generation == "9"


def test_executor_start_evidence_follows_successful_executor_operation():
    events = []
    turn_id = uuid.uuid4()
    session_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "worker", 1, 1)
    workspace = SimpleNamespace(
        sandbox=object(),
        workspace_generation=1,
        worker_generation="generation-a",
    )

    class Manager:
        async def acquire(self, **_kwargs):
            return workspace

        async def release(self, _workspace):
            events.append("released")
            return True

        async def invalidate(self, _workspace):
            raise AssertionError("successful operation must not invalidate")

    class Executor:
        async def ensure_workspace(self, _context):
            events.append("workspace_ack")

        async def exec_resumable(self, _context, **_kwargs):
            events.append("executor_completed")
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "completed", "exit_code": 0, "error": None},
                responses=(),
            )

    async def transition(state):
        events.append(f"state:{state}")

    executor = ExternalPiToolWorkspaceExecutor(
        settings=get_settings(),
        admission=SimpleNamespace(
            turn_id=turn_id,
            session_id=session_id,
            durable_claim=claim,
        ),
        capability=SimpleNamespace(
            token="capability", expires_at=datetime.now(UTC) + timedelta(minutes=4)
        ),
        provider=object(),
        executor=Executor(),
        workspace_manager=Manager(),
        transition=transition,
        observe=lambda *_args: None,
        record_evidence=lambda **values: events.append(values) or True,
    )

    result = asyncio.run(
        executor.tool_result(
            {
                "operation_id": "operation-a",
                "tool_call_id": "tool-call",
                "operation": "exec",
                "command": "printf ready",
                "timeout_ms": 1_000,
            }
        )
    )

    assert result["ok"] is True
    assert events.index("executor_completed") < events.index(
        {
            "turn_id": turn_id,
            "chat_session_id": session_id,
            "event_type": "executor_started",
            "operation_id": "operation-a",
            "operation_kind": "bash",
        }
    )
    assert events[-1] == "state:running"


def test_compatibility_tool_helper_supplies_the_stale_boundary():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    recorded = []
    runner.record_evidence = lambda **event: recorded.append(event) or True

    async def execute(request, *, operation_id, operation, stale_boundary):
        assert request["tool_call_id"] == "tool-1"
        assert operation_id == "operation-1"
        assert operation == "read"
        stale_boundary.reject()
        return {"type": "tool_result", "operation_id": operation_id, "ok": True}

    runner.tool_executor._execute = execute
    result = asyncio.run(
        runner._execute_tool_result(
            {"tool_call_id": "tool-1"},
            operation_id="operation-1",
            operation="read",
        )
    )

    assert result == {
        "type": "tool_result",
        "operation_id": "operation-1",
        "ok": True,
    }
    assert recorded == [
        {
            "turn_id": runner.admission.turn_id,
            "chat_session_id": runner.admission.session_id,
            "event_type": "stale_fence",
        }
    ]


@pytest.mark.parametrize("remote_enabled", [False, True])
def test_legacy_admission_uses_legacy_workspace_without_rendezvous(remote_enabled):
    class Manager(FakeWorkspaceManager):
        async def acquire(self, **kwargs):
            raise AssertionError("executor startup requires a rendezvous bundle")

        async def acquire_legacy(self, *, session_id, turn_claim):
            return await super().acquire(session_id=session_id, turn_claim=turn_claim)

    manager = Manager(FakeProvider())
    executor = FakeExecutor()
    runner = _tool_runner(executor, manager)
    runner.tool_executor.settings.chat_executor_remote_transport_enabled = (
        remote_enabled
    )
    assert runner.tool_executor.admission.executor_transport == "legacy"

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "legacy-operation",
                "tool_call_id": "legacy-tool",
                "operation": "exec",
                "command": "printf x >> marker",
                "timeout_ms": 1000,
            }
        )
    )

    assert result["ok"] is True
    assert executor.exec_calls == 1
    assert len(manager.acquired) == 1
    assert len(manager.released) == 1
    assert manager.invalidated == []


def test_turn_binding_is_lazy_ordered_shared_bounded_and_settled_once():
    events: list[str] = []

    class Manager(FakeWorkspaceManager):
        async def acquire_for_binding(self, *, session_id, turn_claim):
            events.extend(("live_turn", "environment_claim"))
            return await self.acquire(session_id=session_id, turn_claim=turn_claim)

    class Channel:
        def __init__(self):
            self.health_calls = 0
            self.workspace_calls = 0
            self.exec_calls = 0
            self.active = 0
            self.maximum_active = 0
            self.four_started = asyncio.Event()
            self.release = asyncio.Event()
            self.closed = 0

        async def health(self):
            self.health_calls += 1
            events.append("health")
            return "ok"

        async def ensure_workspace(self, _context):
            self.workspace_calls += 1
            events.append("workspace_ack")

        async def exec_resumable(self, _context, *, command, timeout_ms):
            assert timeout_ms == 1000
            self.exec_calls += 1
            if command == "parallel":
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
                if self.active == 4:
                    self.four_started.set()
                await self.release.wait()
                self.active -= 1
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "completed", "exit_code": 0, "error": None},
            )

        async def cancel(self, _context):
            return True

        async def aclose(self):
            self.closed += 1

    manager = Manager(FakeProvider())
    channel = Channel()
    runner = _tool_runner(FakeExecutor(), manager)

    async def channel_factory(_workspace, _turn_claim, minimum_remaining_seconds):
        assert minimum_remaining_seconds == 240
        events.extend(("route", "authorization", "noise_attach", "generation"))
        return channel

    runner.tool_executor.channel_factory = channel_factory

    async def tool(index: int, command: str):
        return await runner._tool_result(
            {
                "operation_id": f"operation-{index}",
                "tool_call_id": f"tool-{index}",
                "operation": "exec",
                "command": command,
                "timeout_ms": 1000,
            }
        )

    async def exercise():
        runner.tool_executor.begin_turn()
        for index in range(10):
            assert (await tool(index, "sequential"))["ok"] is True
        tasks = [
            asyncio.create_task(tool(10 + index, "parallel")) for index in range(5)
        ]
        await asyncio.wait_for(channel.four_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert channel.maximum_active == 4
        channel.release.set()
        assert all(result["ok"] for result in await asyncio.gather(*tasks))
        await runner.tool_executor.settle_turn()
        await runner.tool_executor.settle_turn()

    asyncio.run(exercise())

    assert events[:8] == [
        "live_turn",
        "environment_claim",
        "route",
        "authorization",
        "noise_attach",
        "generation",
        "health",
        "workspace_ack",
    ]
    assert len(manager.acquired) == 1
    assert len(manager.released) == 1
    assert manager.invalidated == []
    assert channel.health_calls == 1
    assert channel.workspace_calls == 1
    assert channel.exec_calls == 15
    assert channel.closed == 1


def test_turn_cancellation_reaches_four_siblings_and_blocks_the_fifth_start():
    class BlockingExecutor(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.cancelled: list[str] = []

        async def exec_resumable(self, context, *, command, timeout_ms):
            assert command == "parallel"
            assert timeout_ms == 1000
            self.active += 1
            if self.active == 4:
                self.started.set()
            await self.release.wait()
            self.active -= 1
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "cancelled", "exit_code": None, "error": None},
            )

        async def cancel_execution(self, context):
            self.cancelled.append(context.execution_id)
            if len(self.cancelled) == 4:
                self.release.set()
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "cancelled", "exit_code": None, "error": None},
            )

    executor = BlockingExecutor()
    manager = FakeWorkspaceManager(FakeProvider())
    runner = _tool_runner(executor, manager)

    async def tool(index: int):
        return await runner._tool_result(
            {
                "operation_id": f"operation-{index}",
                "tool_call_id": f"tool-{index}",
                "operation": "exec",
                "command": "parallel",
                "timeout_ms": 1000,
            }
        )

    async def exercise():
        runner.tool_executor.begin_turn()
        tasks = [asyncio.create_task(tool(index)) for index in range(5)]
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        assert await runner.tool_executor.cancel_active() is True
        results = await asyncio.gather(*tasks)
        await runner.tool_executor.settle_turn()
        return results

    results = asyncio.run(exercise())

    assert sorted(executor.cancelled) == [f"operation-{index}" for index in range(4)]
    assert results[4] == {
        "type": "tool_result",
        "operation_id": "operation-4",
        "ok": False,
        "error": "turn_cancelled",
    }
    assert len(manager.released) == 1
    assert manager.invalidated == []
