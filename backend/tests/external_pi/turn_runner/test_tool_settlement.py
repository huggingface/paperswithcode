"""Tool execution settlement, cancellation, and workspace invalidation."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionLost,
    ExecutorExecutionResult,
)
from backend.services.chat_turn_cancel_control import CancelControlResult
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeWorkspaceManager,
    LostExecutor,
    _tool_runner,
)


def test_tool_execution_persists_waiting_tool_until_safe_settlement():
    states: list[str] = []
    observations: list[tuple[str, str | None, int]] = []
    manager = FakeWorkspaceManager(FakeProvider())
    runner = _tool_runner(FakeExecutor(), manager)

    async def record(state):
        states.append(state)
        if state == "running":
            assert len(manager.released) == 1

    runner.turn_state_transition = record
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "operation-1",
                "tool_call_id": "tool-1",
                "operation": "exec",
                "command": "printf x >> marker",
                "timeout_ms": 1000,
            }
        )
    )

    assert result["ok"] is True
    assert states == ["waiting_tool", "running"]
    assert observations == [
        ("turn_state", "waiting_tool", 1),
        ("turn_state", "running", 1),
    ]


def test_tool_execution_reports_executor_recovery_only_with_recovery_evidence():
    class RecoveredExecutor(FakeExecutor):
        async def exec_resumable(self, context, *, command, timeout_ms):
            result = await super().exec_resumable(
                context, command=command, timeout_ms=timeout_ms
            )
            return ExecutorExecutionResult(
                outputs=result.outputs,
                terminal=result.terminal,
                responses=result.responses,
                recovered=True,
            )

    observations: list[tuple[str, str | None, int]] = []
    runner = _tool_runner(RecoveredExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "operation-1",
                "tool_call_id": "tool-1",
                "operation": "exec",
                "command": "printf x >> marker",
                "timeout_ms": 1000,
            }
        )
    )

    assert result["ok"] is True
    assert ("executor_recovery", "succeeded", 1) in observations


def test_execution_lost_cancel_failure_invalidates_without_releasing():
    class CancelFailure(LostExecutor):
        async def cancel_execution(self, context):
            self.cancelled_contexts.append(context)
            raise OSError("cancel uncertain")

    executor = CancelFailure()
    manager = FakeWorkspaceManager(FakeProvider())
    manager.invalidate_error = RuntimeError("invalidation failed")
    runner = _tool_runner(executor, manager)
    request = {
        "operation_id": "operation-1",
        "tool_call_id": "tool-1",
        "operation": "exec",
        "command": "printf x >> marker",
        "timeout_ms": 1000,
    }

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(runner._tool_result(request))

    assert exc_info.value.code == "execution_lost"
    assert manager.released == []
    assert len(manager.invalidated) == 1


@pytest.mark.parametrize("operation", ["exec", "read"])
@pytest.mark.parametrize("cancel_succeeds", [True, False])
def test_external_task_cancellation_settles_exact_active_workspace(
    cancel_succeeds, operation
):
    class BlockingExecutor(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled_contexts = []

        async def exec_resumable(self, context, *, command, timeout_ms):
            self.started.set()
            await asyncio.Future()

        async def read_file(self, context, *, path, offset, max_bytes):
            self.started.set()
            await asyncio.Future()

        async def cancel_execution(self, context):
            self.cancelled_contexts.append(context)
            if not cancel_succeeds:
                raise OSError("cancel uncertain")
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "cancelled", "exit_code": None, "error": None},
            )

    async def exercise():
        executor = BlockingExecutor()
        manager = FakeWorkspaceManager(FakeProvider())
        if not cancel_succeeds:
            manager.invalidate_error = RuntimeError("secondary cleanup failed")
        runner = _tool_runner(executor, manager)
        request = {
            "operation_id": "operation-1",
            "tool_call_id": "tool-1",
            "operation": operation,
        }
        if operation == "exec":
            request.update(command="printf x >> marker", timeout_ms=1000)
        else:
            request.update(path="/opt/pwc/PWC_CLI_SKILL.md", offset=0, max_bytes=1024)
        task = asyncio.create_task(runner._tool_result(request))
        await executor.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return executor, manager

    executor, manager = asyncio.run(exercise())
    assert len(executor.cancelled_contexts) == 1
    if cancel_succeeds:
        assert len(manager.released) == 1
        assert manager.invalidated == []
    else:
        assert manager.released == []
        assert len(manager.invalidated) == 1


def test_cleanup_failures_do_not_override_successful_tool_result():
    manager = FakeWorkspaceManager(FakeProvider())
    manager.release_error = RuntimeError("release failed")
    manager.invalidate_error = RuntimeError("invalidate failed")
    runner = _tool_runner(FakeExecutor(), manager)

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "operation-1",
                "tool_call_id": "tool-1",
                "operation": "exec",
                "command": "printf x >> marker",
                "timeout_ms": 1000,
            }
        )
    )

    assert result["ok"] is True
    assert len(manager.released) == 1
    assert len(manager.invalidated) == 1


def test_false_workspace_release_records_stale_fence_without_changing_tool_result():
    manager = FakeWorkspaceManager(FakeProvider())
    manager.release_result = False
    runner = _tool_runner(FakeExecutor(), manager)
    events = []
    runner.tool_executor.record_evidence = (
        lambda **values: events.append(values) or True
    )

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "operation-1",
                "tool_call_id": "tool-1",
                "operation": "exec",
                "command": "printf x >> marker",
                "timeout_ms": 1000,
            }
        )
    )

    assert result["ok"] is True
    assert [event["event_type"] for event in events] == [
        "executor_started",
        "stale_fence",
    ]
    assert manager.invalidated == []


def test_new_cancellation_during_successful_release_propagates_after_invalidation():
    manager = FakeWorkspaceManager(FakeProvider())
    manager.release_error = asyncio.CancelledError()
    runner = _tool_runner(FakeExecutor(), manager)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            runner._tool_result(
                {
                    "operation_id": "operation-1",
                    "tool_call_id": "tool-1",
                    "operation": "exec",
                    "command": "printf x >> marker",
                    "timeout_ms": 1000,
                }
            )
        )

    assert len(manager.released) == 1
    assert len(manager.invalidated) == 1


@pytest.mark.parametrize(
    ("terminal", "safe"),
    [
        ({"status": "cancelled", "exit_code": None, "error": None}, True),
        ({"status": "completed", "exit_code": 0, "error": None}, True),
        ({"status": "completed", "exit_code": -(2**31), "error": None}, True),
        ({"status": "completed", "exit_code": 2**31 - 1, "error": None}, True),
        ({"status": "cancelled", "exit_code": -(2**31), "error": None}, True),
        ({"status": "cancelled", "exit_code": 2**31 - 1, "error": None}, True),
        (
            {
                "status": "failed",
                "exit_code": None,
                "error": "execution_not_found",
            },
            False,
        ),
        ({"status": "failed", "exit_code": 1, "error": "failed"}, False),
        ({"status": "unknown", "exit_code": None, "error": None}, False),
        ({"status": "cancelled", "error": None}, False),
        ({"status": "completed", "exit_code": None, "error": None}, False),
        ({"status": "completed", "exit_code": True, "error": None}, False),
        ({"status": "completed", "exit_code": "0", "error": None}, False),
        ({"status": "completed", "exit_code": 0.0, "error": None}, False),
        ({"status": "completed", "exit_code": 2**31, "error": None}, False),
        ({"status": "completed", "exit_code": -(2**31) - 1, "error": None}, False),
        ({"status": "cancelled", "exit_code": False, "error": None}, False),
        ({"status": "cancelled", "exit_code": "0", "error": None}, False),
        ({"status": "cancelled", "exit_code": 2**31, "error": None}, False),
        ({"status": "cancelled", "exit_code": -(2**31) - 1, "error": None}, False),
        (None, False),
    ],
)
def test_cancel_executor_requires_positive_terminal_proof(terminal, safe):
    class CancelResult(FakeExecutor):
        async def cancel_execution(self, context):
            return ExecutorExecutionResult(outputs=(), terminal=terminal)

    runner = _tool_runner(CancelResult(), FakeWorkspaceManager(FakeProvider()))
    context = SimpleNamespace()

    assert asyncio.run(runner._cancel_executor(context)) is safe


def test_cancel_attempts_executor_when_worker_socket_fails_and_defers_revocation():
    calls: list[str] = []

    class BrokenSocket:
        async def send(self, _frame):
            calls.append("worker")
            raise OSError("socket lost")

    class CancelExecutor(FakeExecutor):
        async def cancel_execution(self, _context):
            calls.append("executor")
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "cancelled", "exit_code": None, "error": None},
            )

    runner = _tool_runner(CancelExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.socket = BrokenSocket()
    runner.active_context = SimpleNamespace()
    runner._revoke = lambda: calls.append("revoke")

    result = asyncio.run(runner.cancel())

    assert result is CancelControlResult.MISSING
    assert calls == ["worker", "executor"]


def test_cancel_times_out_never_returning_worker_send_but_cancels_executor():
    worker_started = asyncio.Event()
    executor_cancelled = asyncio.Event()

    class WedgedSocket:
        async def send(self, _frame):
            worker_started.set()
            await asyncio.Future()

    class CancelExecutor(FakeExecutor):
        async def cancel_execution(self, _context):
            executor_cancelled.set()
            return ExecutorExecutionResult(
                outputs=(),
                terminal={"status": "cancelled", "exit_code": None, "error": None},
            )

    runner = _tool_runner(CancelExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.socket = WedgedSocket()
    runner.active_context = SimpleNamespace()
    runner.cancel_timeout_seconds = 0.01

    result = asyncio.run(asyncio.wait_for(runner.cancel(), timeout=0.2))

    assert worker_started.is_set()
    assert executor_cancelled.is_set()
    assert result is CancelControlResult.MISSING


def test_execution_not_found_cancel_result_invalidates_ambiguous_workspace():
    class MissingExecution(LostExecutor):
        async def cancel_execution(self, context):
            self.cancelled_contexts.append(context)
            return ExecutorExecutionResult(
                outputs=(),
                terminal={
                    "status": "failed",
                    "exit_code": None,
                    "error": "execution_not_found",
                },
            )

    manager = FakeWorkspaceManager(FakeProvider())
    runner = _tool_runner(MissingExecution(), manager)

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            runner._tool_result(
                {
                    "operation_id": "operation-1",
                    "tool_call_id": "tool-1",
                    "operation": "exec",
                    "command": "printf x >> marker",
                    "timeout_ms": 1000,
                }
            )
        )

    assert exc_info.value.code == "execution_lost"
    assert manager.released == []
    assert len(manager.invalidated) == 1


def test_invalidation_failure_never_releases_identity_mismatch():
    class IdentityFailure(FakeExecutor):
        async def ensure_workspace(self, context):
            raise ProtocolError("workspace mismatch")

    manager = FakeWorkspaceManager(FakeProvider())
    manager.invalidate_error = RuntimeError("invalidate failed")
    runner = _tool_runner(IdentityFailure(), manager)

    result = asyncio.run(
        runner._tool_result(
            {
                "operation_id": "operation-1",
                "tool_call_id": "tool-1",
                "operation": "read",
                "path": "/opt/pwc/PWC_CLI_SKILL.md",
                "offset": 0,
                "max_bytes": 1024,
            }
        )
    )

    assert result == {
        "type": "tool_result",
        "operation_id": "operation-1",
        "ok": False,
        "error": "tool_failed",
    }
    assert manager.released == []
    assert len(manager.invalidated) == 1
