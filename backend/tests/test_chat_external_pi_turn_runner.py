import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import threading
from types import SimpleNamespace
import uuid

import pytest

from backend.config import get_settings
from backend.chat_sandbox_worker.executor_daemon import ExecutorServer
from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    MAX_EXTERNAL_TURN_FRAME_BYTES,
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_pi_tool_executor import (
    ExternalPiToolWorkspaceExecutor,
)
from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerControlRejected,
    ExternalPiWorkerUnavailable,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)
from backend.services.chat_external_worker_capacity import (
    ExternalWorkerEndpoint,
    ExternalWorkerReservation,
)
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionLost,
    ExecutorExecutionResult,
    ExecutorReadResult,
    SandboxExecutorClient,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.services.chat_turn_cancel_control import CancelControlResult
from backend.tests.test_chat_sandbox_executor_client import (
    _Broker,
    _DropFirstResponseSocketProvider,
    _Process,
    _Provider,
)


class FakeSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def send(self, value):
        self.sent.append(value)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            value = next(self.messages)
        except StopIteration:
            raise StopAsyncIteration from None
        if isinstance(value, BaseException):
            raise value
        return value


@pytest.fixture(autouse=True)
def _isolate_durable_turn_state(monkeypatch):
    async def ignore(_runner, _state):
        return None

    monkeypatch.setattr(ExternalPiChatTurnRunner, "_persist_turn_state", ignore)


class SocketContext:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, *_args):
        return None


class SequencedConnector:
    def __init__(self, *sockets):
        self.sockets = iter(sockets)
        self.calls = []

    def __call__(self, url, **kwargs):
        socket = next(self.sockets)
        self.calls.append((url, kwargs, socket))
        return SocketContext(socket)


class SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return None


class FakeWorkerRepository:
    def __init__(self, claim):
        self.claim = claim
        self.calls = []

    def select_ready_claim(self, db, *, claim, now):
        self.calls.append(("select", db, claim, now))
        if claim != self.claim:
            raise StaleWorkerClaim("External worker claim was fenced")
        return self.claim

    def require_ready_claim(self, db, *, claim, now):
        self.calls.append(("require", db, claim, now))

    def require_live_claim(self, db, *, claim, now):
        self.calls.append(("require_live", db, claim, now))
        if claim != self.claim:
            raise StaleWorkerClaim("External worker claim was fenced")


class FakeProvider:
    def __init__(self):
        self.created = []
        self.terminated = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return type("Sandbox", (), {"object_id": "sb-test"})()

    async def terminate(self, sandbox_id, sandbox=None):
        self.terminated.append((sandbox_id, sandbox))
        return True


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
        admission=SimpleNamespace(turn_id=turn_id, session_id=session_id),
        capability=SimpleNamespace(token="capability"),
        executor=Executor(),
        record_evidence=lambda **values: events.append(values) or True,
        active_context=None,
    )
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
        capability=SimpleNamespace(token="capability"),
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


class FakeWorkspaceManager:
    def __init__(self, provider):
        self.provider = provider
        self.acquired = []
        self.released = []
        self.invalidated = []
        self.sandbox = type("Sandbox", (), {"object_id": "sb-retained"})()
        self.worker_generation = "durable-workspace-generation"
        self.release_error = None
        self.release_result = True
        self.invalidate_error = None

    async def acquire(self, *, session_id, turn_claim):
        self.acquired.append((session_id, turn_claim))
        return SimpleNamespace(
            session_id=session_id,
            sandbox=self.sandbox,
            sandbox_id=self.sandbox.object_id,
            worker_generation=self.worker_generation,
            workspace_generation=37,
        )

    async def release(self, workspace):
        self.released.append(workspace)
        if self.release_error is not None:
            raise self.release_error
        return self.release_result

    async def invalidate(self, workspace, *, failure_code="sandbox_worker_failed"):
        self.invalidated.append((workspace, failure_code))
        if self.invalidate_error is not None:
            raise self.invalidate_error


class FakeExecutor:
    def __init__(self):
        self.contexts = []
        self.reads = 0
        self.exec_calls = 0

    async def ensure_workspace(self, context):
        self.contexts.append(context)

    async def read_file(self, context, *, path, offset, max_bytes):
        self.contexts.append(context)
        self.reads += 1
        assert path == "/opt/pwc/PWC_CLI_SKILL.md"
        return ExecutorReadResult(path=path, offset=offset, data=b"guide", eof=True)

    async def exec_resumable(self, context, *, command, timeout_ms):
        self.contexts.append(context)
        self.exec_calls += 1
        assert command == "printf x >> marker"
        assert timeout_ms == 1000
        return ExecutorExecutionResult(
            outputs=({"sequence": 1, "stream": "stdout", "data": "x"},),
            terminal={"status": "completed", "exit_code": 0, "error": None},
        )


class LostExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.cancelled_contexts = []

    async def exec_resumable(self, context, *, command, timeout_ms):
        self.exec_calls += 1
        raise ExecutorExecutionLost(
            execution_id=context.execution_id,
            last_sequence=0,
            responses=(),
        )

    async def cancel_execution(self, context):
        self.cancelled_contexts.append(context)
        return ExecutorExecutionResult(
            outputs=(),
            terminal={"status": "cancelled", "exit_code": None, "error": None},
        )


def worker_status(claim):
    return SimpleNamespace(
        worker_id=claim.worker_id,
        instance_id=claim.instance_id,
        worker_generation=claim.generation,
        release_id=claim.release_id,
        protocol=claim.contract_version,
        state="ready",
        active_sessions=0,
        maximum_sessions=8,
    )


def test_external_pi_runner_lazily_creates_executor_for_remote_read():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    workspace_manager = FakeWorkspaceManager(provider)
    executor = FakeExecutor()
    observed = []

    def observe(event, code, value):
        if event == "worker_ready":
            raise ValueError("transport-only readiness is not a lifecycle metric")
        observed.append((event, code, value))

    socket = FakeSocket(
        [
            '{"type":"worker_ready","worker_sequence":1}',
            '{"type":"tool_call_start","id":"tool-1","name":"Read",'
            '"content_index":0,"worker_sequence":2}',
            '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
            '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,"max_bytes":1024,"worker_sequence":3}',
            '{"type":"workspace_ready","worker_sequence":4}',
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":5}',
            '{"type":"worker_done","status":"complete","worker_sequence":6}',
        ]
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=workspace_manager,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=(
            repository := FakeWorkerRepository(
                ExternalWorkerClaim(
                    "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
                )
            )
        ),
        worker_status_resolver=lambda: _async_value(worker_status(repository.claim)),
        session_factory=SessionContext,
        observe=observe,
    )

    async def exercise():
        stream = runner.events()
        first = await anext(stream)
        acquired_before_first_event = list(workspace_manager.acquired)
        events = [first, *[event async for event in stream]]
        await runner.close()
        return events, acquired_before_first_event

    events, acquired_before_first_event = asyncio.run(exercise())

    assert [event["type"] for event in events] == [
        "tool_call_start",
        "workspace_ready",
        "done",
    ]
    assert acquired_before_first_event == []
    assert provider.created == []
    assert provider.terminated == []
    assert workspace_manager.acquired == [
        (admission.session_id, admission.durable_claim)
    ]
    assert workspace_manager.released[0].sandbox_id == "sb-retained"
    assert executor.contexts[0].session_id == str(admission.session_id)
    assert executor.contexts[0].workspace_generation == 37
    assert executor.contexts[0].worker_generation == "durable-workspace-generation"
    assert '"type":"tool_result"' in socket.sent[1]
    assert all(event != "worker_ready" for event, _code, _value in observed)


def test_external_pi_runner_routes_bash_through_resumable_execution():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    workspace_manager = FakeWorkspaceManager(provider)
    executor = FakeExecutor()
    socket = FakeSocket(
        [
            '{"type":"tool_request","operation_id":"operation-1",'
            '"tool_call_id":"tool-1","operation":"exec",'
            '"command":"printf x >> marker","timeout_ms":1000,"worker_sequence":1}',
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=workspace_manager,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == ["done"]
    assert executor.exec_calls == 1
    tool_result = json.loads(socket.sent[1])
    assert tool_result["operation_id"] == "operation-1"
    assert tool_result["ok"] is True


def test_external_pi_runner_cancels_and_aborts_turn_on_execution_lost():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    executor = LostExecutor()
    cancellation_order = []
    socket = FakeSocket(
        [
            '{"type":"tool_request","operation_id":"operation-1",'
            '"tool_call_id":"tool-1","operation":"exec",'
            '"command":"printf x >> marker","timeout_ms":1000,"worker_sequence":1}',
            '{"type":"answer_delta","text":"must not be processed","worker_sequence":2}',
        ]
    )
    original_cancel_execution = executor.cancel_execution
    original_socket_send = socket.send

    async def record_executor_cancel(context):
        cancellation_order.append("executor")
        return await original_cancel_execution(context)

    async def record_socket_send(value):
        if json.loads(value)["type"] == "cancel_turn":
            cancellation_order.append("pi")
        await original_socket_send(value)

    executor.cancel_execution = record_executor_cancel
    socket.send = record_socket_send
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    workspace_manager = FakeWorkspaceManager(FakeProvider())
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=FakeProvider(),
        executor=executor,
        workspace_manager=workspace_manager,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(_collect(runner))

    assert exc_info.value.code == "execution_lost"
    assert executor.exec_calls == 1
    assert len(executor.cancelled_contexts) == 1
    assert executor.cancelled_contexts[0].execution_id == "operation-1"
    assert executor.cancelled_contexts[0].tool_call_id == "operation-1"
    assert cancellation_order == ["executor", "pi"]
    assert len(workspace_manager.released) == 1
    assert workspace_manager.invalidated == []
    assert [json.loads(frame)["type"] for frame in socket.sent] == [
        "run_turn",
        "cancel_turn",
    ]
    assert next(socket.messages) == (
        '{"type":"answer_delta","text":"must not be processed","worker_sequence":2}'
    )


def test_chat_stream_producer_preserves_execution_lost_terminal_code():
    class LostRunner:
        def __init__(self):
            self.cancelled = False

        async def events(self):
            raise ExecutorExecutionLost(
                execution_id="execution-a",
                last_sequence=0,
                responses=(),
            )
            yield

        async def cancel(self):
            self.cancelled = True

    runner = LostRunner()
    coordinator = ChatStreamOrchestrator.__new__(ChatStreamOrchestrator)
    coordinator.runner = runner
    coordinator.admission = SimpleNamespace(session_id=uuid.uuid4())
    queue = asyncio.Queue()

    asyncio.run(coordinator._produce_research(queue))

    assert runner.cancelled is True
    assert queue.get_nowait() == {
        "type": "error",
        "message": "The sandbox execution could not be recovered.",
        "code": "execution_lost",
    }
    assert queue.get_nowait() == {"type": "_research_finished"}


def test_chat_stream_producer_cancels_worker_after_unexpected_failure():
    class FailedRunner:
        def __init__(self):
            self.cancelled = False

        async def events(self):
            raise TypeError("provider detail must not escape")
            yield

        async def cancel(self):
            self.cancelled = True

    runner = FailedRunner()
    coordinator = ChatStreamOrchestrator.__new__(ChatStreamOrchestrator)
    coordinator.runner = runner
    coordinator.admission = SimpleNamespace(session_id=uuid.uuid4())
    queue = asyncio.Queue()

    asyncio.run(coordinator._produce_research(queue))

    assert runner.cancelled is True
    assert queue.get_nowait() == {
        "type": "error",
        "message": "The model provider is unavailable.",
        "code": "provider_error",
    }
    assert queue.get_nowait() == {"type": "_research_finished"}


@pytest.mark.parametrize("failure", ["cursor_gap", "aggregate_limit"])
def test_external_pi_runner_aborts_on_recovery_validation_failure(monkeypatch, failure):
    if failure == "aggregate_limit":
        monkeypatch.setattr(
            "backend.services.chat_sandbox_executor.MAX_EXECUTOR_RESPONSE_FRAMES", 3
        )

    class RecoveryFailureExecutor(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.cancelled_contexts = []

        async def exec_resumable(self, context, *, command, timeout_ms):
            request_ids = iter(["exec-request", "attach-request"])

            def frame(request_id, kind, **fields):
                return {
                    "protocol": "sandbox-executor-v1",
                    "type": kind,
                    "request_id": request_id,
                    **context.operation_identity,
                    **fields,
                }

            attach_sequence = 3 if failure == "cursor_gap" else 2
            client = SandboxExecutorClient(
                _Provider(
                    [
                        _Process(
                            [
                                frame(
                                    "exec-request",
                                    "acknowledged",
                                    operation="exec",
                                ),
                                frame(
                                    "exec-request",
                                    "output",
                                    sequence=1,
                                    stream="stdout",
                                    data="safe",
                                ),
                            ],
                            error=ConnectionResetError("ambiguous exec"),
                        ),
                        _Process(
                            [
                                frame(
                                    "attach-request",
                                    "acknowledged",
                                    operation="attach_execution",
                                ),
                                frame(
                                    "attach-request",
                                    "output",
                                    sequence=attach_sequence,
                                    stream="stdout",
                                    data="unsafe",
                                ),
                            ]
                        ),
                    ]
                ),
                request_id_factory=lambda: next(request_ids),
            )
            return await client.exec_resumable(
                context,
                command=command,
                timeout_ms=timeout_ms,
                max_attach_attempts=1,
            )

        async def cancel_execution(self, context):
            self.cancelled_contexts.append(context)

    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    executor = RecoveryFailureExecutor()
    later_event = '{"type":"answer_delta","text":"must not run","worker_sequence":2}'
    socket = FakeSocket(
        [
            '{"type":"tool_request","operation_id":"operation-1",'
            '"tool_call_id":"tool-1","operation":"exec",'
            '"command":"true","timeout_ms":1000,"worker_sequence":1}',
            later_event,
        ]
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=FakeProvider(),
        executor=executor,
        workspace_manager=FakeWorkspaceManager(FakeProvider()),
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(_collect(runner))

    assert len(executor.cancelled_contexts) == 1
    assert executor.cancelled_contexts[0].execution_id == "operation-1"
    assert [json.loads(frame)["type"] for frame in socket.sent] == [
        "run_turn",
        "cancel_turn",
    ]
    assert next(socket.messages) == later_event


def test_external_pi_runner_uses_no_sandbox_without_tools():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    workspace_manager = FakeWorkspaceManager(provider)
    socket = FakeSocket(
        [
            '{"type":"workspace_ready","worker_sequence":1}',
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        workspace_manager=workspace_manager,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=(
            repository := FakeWorkerRepository(
                ExternalWorkerClaim(
                    "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
                )
            )
        ),
        worker_status_resolver=lambda: _async_value(worker_status(repository.claim)),
        session_factory=SessionContext,
    )

    async def exercise():
        events = [event["type"] async for event in runner.events()]
        await runner.close()
        return events

    assert asyncio.run(exercise()) == ["workspace_ready", "done"]
    assert provider.created == []
    assert workspace_manager.acquired == []
    assert workspace_manager.released == []


def test_external_pi_runner_delivers_contiguous_worker_buffer_exhaustion():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    socket = FakeSocket(
        [
            '{"type":"workspace_ready","worker_sequence":1}',
            '{"type":"error","code":"worker_event_buffer_exhausted",'
            '"message":"The research run failed.","worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )
    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "worker_event_buffer_exhausted",
            "message": "The research run failed.",
        },
    ]


def test_external_pi_runner_fences_socket_and_run_with_distinct_claims():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.UUID("20000000-0000-4000-8000-000000000001")
    admission = TurnAdmission(
        session_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    worker_claim = ExternalWorkerClaim(
        "external-pi-1",
        uuid.UUID("30000000-0000-4000-8000-000000000001"),
        7,
        "release-a",
        "external-pi-v1",
    )
    repository = FakeWorkerRepository(worker_claim)
    socket = FakeSocket(
        ['{"type":"worker_done","status":"complete","worker_sequence":1}']
    )
    connection = {}

    def connect(url, **kwargs):
        connection.update(
            url=url, kwargs=kwargs, repository_calls=list(repository.calls)
        )
        return SocketContext(socket)

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_repository=repository,
        worker_status_resolver=lambda: _async_value(worker_status(worker_claim)),
        session_factory=SessionContext,
        now=lambda: datetime(2026, 8, 29, 12, tzinfo=UTC),
    )

    assert asyncio.run(_collect(runner)) == []
    assert [call[0] for call in connection["repository_calls"]] == [
        "select",
        "require",
    ]
    assert connection["kwargs"]["additional_headers"] == {
        "Authorization": f"Bearer {settings.chat_external_pi_worker_token}",
        "X-PWC-Worker-Generation": "7",
    }
    assert connection["kwargs"]["max_size"] == MAX_EXTERNAL_TURN_FRAME_BYTES
    assert connection["kwargs"]["open_timeout"] == (
        settings.chat_external_pi_startup_timeout_seconds
    )
    assert connection["kwargs"]["ping_interval"] == 20
    assert connection["kwargs"]["ping_timeout"] == 20
    assert json.loads(socket.sent[0])["turnClaim"] == {
        "turnId": str(turn_id),
        "workerId": "api-1",
        "workerGeneration": "4",
        "leaseGeneration": "9",
    }


def test_external_pi_runner_rejects_endpoint_status_mismatch_before_connect():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    selected = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    endpoint = ExternalWorkerClaim(
        "external-pi-2", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    connected = False

    def connect(*_args, **_kwargs):
        nonlocal connected
        connected = True
        raise AssertionError("stale endpoint must not connect")

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_repository=FakeWorkerRepository(selected),
        worker_status_resolver=lambda: _async_value(worker_status(endpoint)),
        session_factory=SessionContext,
    )
    stale_events = []
    runner.record_evidence = lambda **values: stale_events.append(values) or True

    with pytest.raises(StaleWorkerClaim):
        asyncio.run(_collect(runner))
    assert connected is False
    assert [event["event_type"] for event in stale_events] == ["stale_fence"]


def test_external_pi_runner_uses_the_exact_durable_reserved_endpoint():
    settings = get_settings().model_copy(
        deep=True,
        update={
            "environment": "staging",
            "chat_external_pi_worker_endpoints": [
                {
                    "endpoint_id": "blue",
                    "worker_id": "external-pi-blue",
                    "base_url": "http://127.0.0.1:18101",
                    "token": "b" * 32,
                },
                {
                    "endpoint_id": "green",
                    "worker_id": "external-pi-green",
                    "base_url": "http://127.0.0.1:18102",
                    "token": "g" * 32,
                },
            ],
        },
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    endpoint = ExternalWorkerEndpoint(
        endpoint_id="green",
        worker_id="external-pi-green",
        base_url="http://127.0.0.1:18102",
        token="g" * 32,
    )
    claim = ExternalWorkerClaim(
        endpoint.worker_id, uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )

    class Capacity:
        def require_turn(self, _db, *, turn_id, endpoints, now):
            assert turn_id == admission.turn_id
            assert endpoint in endpoints
            return ExternalWorkerReservation(
                "request-1", admission.turn_id, endpoint, claim, 8
            )

    connection = {}
    socket = FakeSocket(
        ['{"type":"worker_done","status":"complete","worker_sequence":1}']
    )

    def connect(url, **kwargs):
        connection.update(url=url, kwargs=kwargs)
        return SocketContext(socket)

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_repository=FakeWorkerRepository(claim),
        worker_capacity_repository=Capacity(),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )
    stale_events = []
    runner.record_evidence = lambda **values: stale_events.append(values) or True

    assert asyncio.run(_collect(runner)) == []
    assert connection["url"] == "ws://127.0.0.1:18102/v1/turn"
    assert connection["kwargs"]["additional_headers"] == {
        "Authorization": f"Bearer {'g' * 32}",
        "X-PWC-Worker-Generation": "7",
    }

    mismatched = worker_status(claim)
    mismatched.maximum_sessions = 7
    runner.worker_status_resolver = lambda: _async_value(mismatched)
    with pytest.raises(StaleWorkerClaim, match="identity mismatches"):
        asyncio.run(_collect(runner))
    assert [event["event_type"] for event in stale_events] == ["stale_fence"]


def test_external_pi_runner_keeps_reserved_endpoint_database_checks_off_event_loop():
    settings = get_settings().model_copy(
        deep=True,
        update={
            "environment": "staging",
            "chat_external_pi_worker_endpoints": [
                {
                    "endpoint_id": "green",
                    "worker_id": "external-pi-green",
                    "base_url": "http://127.0.0.1:18102",
                    "token": "g" * 32,
                }
            ],
        },
    )
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    endpoint = ExternalWorkerEndpoint(
        endpoint_id="green",
        worker_id="external-pi-green",
        base_url="http://127.0.0.1:18102",
        token="g" * 32,
    )
    claim = ExternalWorkerClaim(
        endpoint.worker_id, uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    database_threads = []

    class Capacity:
        def require_turn(self, _db, *, turn_id, endpoints, now):
            database_threads.append(threading.get_ident())
            return ExternalWorkerReservation("request-1", turn_id, endpoint, claim, 8)

    class Repository(FakeWorkerRepository):
        def require_live_claim(self, db, *, claim, now):
            database_threads.append(threading.get_ident())
            super().require_live_claim(db, claim=claim, now=now)

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        worker_repository=Repository(claim),
        worker_capacity_repository=Capacity(),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    async def select():
        event_loop_thread = threading.get_ident()
        selected = await runner._select_worker_claim()
        return event_loop_thread, selected

    event_loop_thread, selected = asyncio.run(select())

    assert selected == claim
    assert len(database_threads) == 2
    assert all(thread != event_loop_thread for thread in database_threads)


def test_external_pi_runner_uses_admission_reservation_without_requerying():
    settings = get_settings().model_copy(
        deep=True,
        update={
            "environment": "staging",
            "chat_external_pi_worker_endpoints": [
                {
                    "endpoint_id": "green",
                    "worker_id": "external-pi-green",
                    "base_url": "http://127.0.0.1:18102",
                    "token": "g" * 32,
                }
            ],
        },
    )
    turn_id = uuid.uuid4()
    endpoint = ExternalWorkerEndpoint(
        endpoint_id="green",
        worker_id="external-pi-green",
        base_url="http://127.0.0.1:18102",
        token="g" * 32,
    )
    claim = ExternalWorkerClaim(
        endpoint.worker_id, uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    reservation = ExternalWorkerReservation(
        "client-message-1", turn_id, endpoint, claim, 2
    )
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
        external_worker_reservation=reservation,
    )
    socket = FakeSocket(
        ['{"type":"worker_done","status":"complete","worker_sequence":1}']
    )
    connection = {}

    def connect(url, **kwargs):
        connection.update(url=url, kwargs=kwargs)
        return SocketContext(socket)

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_status_resolver=lambda: pytest.fail("status was reloaded"),
        session_factory=lambda: pytest.fail("reservation was reloaded"),
    )

    assert asyncio.run(_collect(runner)) == []
    assert connection["url"] == "ws://127.0.0.1:18102/v1/turn"
    assert connection["kwargs"]["additional_headers"] == {
        "Authorization": f"Bearer {'g' * 32}",
        "X-PWC-Worker-Generation": "7",
    }


def test_external_pi_runner_rejects_worker_becoming_full_before_connect():
    class FullWorkerRepository(FakeWorkerRepository):
        def require_ready_claim(self, db, *, claim, now):
            super().require_ready_claim(db, claim=claim, now=now)
            raise WorkerLeaseUnavailable("External worker is not ready")

    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=lambda *_args, **_kwargs: pytest.fail("connected"),
        worker_repository=FullWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        asyncio.run(_collect(runner))


def test_external_pi_runner_observes_endpoint_capacity_saturation():
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    status = worker_status(claim)
    status.active_sessions = status.maximum_sessions
    observations: list[tuple[str, str | None, int]] = []
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.worker_status_resolver = lambda: _async_value(status)
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )
    stale_events = []
    runner.record_evidence = lambda **values: stale_events.append(values) or True

    with pytest.raises(WorkerLeaseUnavailable):
        asyncio.run(runner._select_worker_claim())

    assert observations == [("capacity_saturation", None, 1)]


async def _collect(runner):
    return [event async for event in runner.events()]


async def _async_value(value):
    return value


async def _ignore_turn_state(_state):
    return None


def _tool_runner(executor, workspace_manager):
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=FakeProvider(),
        executor=executor,
        workspace_manager=workspace_manager,
        session_factory=SessionContext,
        turn_state_transition=_ignore_turn_state,
    )
    runner.external_worker_claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    return runner


def test_external_run_frame_omits_absent_paper_descriptor():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.external_worker_claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )

    assert runner.admission.paper_descriptor is None
    assert "paper_descriptor" not in runner._run_frame()


@pytest.mark.parametrize(
    ("worker_enabled", "host_enabled", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_external_run_frame_carries_excalidraw_capability(
    worker_enabled, host_enabled, expected
):
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.settings.chat_excalidraw_enabled = worker_enabled
    runner.settings.chat_mcp_apps_host_enabled = host_enabled

    assert runner._run_frame()["excalidraw_enabled"] is expected


def test_external_new_turn_frame_carries_prebound_pi_session():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    agent_session_id = uuid.uuid4()
    runner.admission = replace(
        runner.admission,
        sdk_session_id=agent_session_id,
        is_first_turn=True,
    )
    runner.resume_id = agent_session_id

    assert runner._run_frame()["agent_session_id"] == str(agent_session_id)
    assert runner._run_frame()["resume"] is None


def test_external_run_frame_preserves_exact_durable_turn_fence_as_strings():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.external_worker_claim = ExternalWorkerClaim(
        "staging-green", uuid.uuid4(), 72, "release-a", "external-pi-v1"
    )

    assert runner._turn_claim_frame() == {
        "turnId": str(runner.admission.turn_id),
        "workerId": runner.admission.durable_claim.worker_id,
        "workerGeneration": str(runner.admission.durable_claim.worker_generation),
        "leaseGeneration": str(runner.admission.durable_claim.lease_generation),
    }


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


def test_external_pi_runner_reattaches_same_run_from_last_acknowledged_sequence():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.UUID("20000000-0000-4000-8000-000000000001")
    admission = TurnAdmission(
        session_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    worker_claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    first = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("link lost")]
    )
    second = FakeSocket(
        [
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    connector = SequencedConnector(first, second)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=(repository := FakeWorkerRepository(worker_claim)),
        worker_status_resolver=lambda: _async_value(worker_status(worker_claim)),
        session_factory=SessionContext,
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "done",
            "finish_reason": "success",
            "followups": [],
        },
    ]
    assert json.loads(first.sent[0])["type"] == "run_turn"
    assert json.loads(second.sent[0]) == {
        "v": 1,
        "type": "attach_turn",
        "request_id": "request-1",
        "turnClaim": {
            "turnId": str(turn_id),
            "workerId": "api-1",
            "workerGeneration": "4",
            "leaseGeneration": "9",
        },
        "afterSequence": 1,
    }
    assert json.loads(second.sent[1]) == {
        "v": 1,
        "type": "ack_terminal",
        "request_id": "request-1",
        "turnClaim": {
            "turnId": str(turn_id),
            "workerId": "api-1",
            "workerGeneration": "4",
            "leaseGeneration": "9",
        },
        "sequence": 3,
    }
    assert [call[0] for call in repository.calls] == [
        "select",
        "require",
        "require_live",
    ]


def test_external_pi_runner_never_reexecutes_replayed_tool_request():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    tool = (
        '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
        '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,'
        '"max_bytes":1024,"worker_sequence":1}'
    )
    first = FakeSocket([tool, OSError("result acknowledgement lost")])
    second = FakeSocket(
        [
            tool,
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    connector = SequencedConnector(first, second)
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=FakeWorkspaceManager(provider),
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == ["done"]
    assert executor.reads == 1
    assert json.loads(second.sent[0])["afterSequence"] == 0
    assert json.loads(first.sent[1]) == json.loads(second.sent[1])
    assert [json.loads(frame)["type"] for frame in second.sent] == [
        "attach_turn",
        "tool_result",
        "ack_terminal",
    ]


def test_external_pi_runner_never_reexecutes_bash_after_websocket_reconnect():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    tool = (
        '{"type":"tool_request","operation_id":"operation-1",'
        '"tool_call_id":"tool-1","operation":"exec",'
        '"command":"printf x >> marker","timeout_ms":1000,"worker_sequence":1}'
    )
    first = FakeSocket([tool, OSError("tool result acknowledgement lost")])

    class FailedAttachSocket(FakeSocket):
        async def send(self, _value):
            raise OSError("attach request was not delivered")

    failed_attach = FailedAttachSocket([])
    reattached = FakeSocket(
        [
            tool,
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    connector = SequencedConnector(first, failed_attach, reattached)
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=FakeWorkspaceManager(provider),
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )
    observations: list[tuple[str, str | None, int]] = []
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == ["done"]
    assert executor.exec_calls == 1
    assert json.loads(first.sent[1]) == json.loads(reattached.sent[1])
    assert ("turn_state", "reconnecting", 1) in observations
    assert ("worker_reconnect", None, 1) in observations
    assert observations.index(("turn_state", "reconnecting", 1)) < observations.index(
        ("worker_reconnect", None, 1)
    )
    assert ("turn_state", "running", 1) in observations
    assert observations.count(("worker_reconnect", None, 1)) == 1
    assert observations.count(("turn_state", "running", 1)) == 2


def test_external_pi_reconnect_reuses_real_recovered_bash_result(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="runner-worker",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    relay = _DropFirstResponseSocketProvider(
        server.socket_path, drop_after_frames=1, drop_on_call=2
    )

    class ExecutorProvider(FakeProvider):
        async def open_executor_relay(self, sandbox, *, timeout_seconds):
            return await relay.open_executor_relay(
                sandbox, timeout_seconds=timeout_seconds
            )

    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = ExecutorProvider()
    request_number = iter(range(10))
    executor = SandboxExecutorClient(
        provider, request_id_factory=lambda: f"executor-{next(request_number)}"
    )
    workspace_manager = FakeWorkspaceManager(provider)
    workspace_manager.worker_generation = "runner-worker"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    tool = (
        '{"type":"tool_request","operation_id":"operation-1",'
        '"tool_call_id":"tool-1","operation":"exec",'
        '"command":"printf x >> marker","timeout_ms":1000,"worker_sequence":1}'
    )
    first = FakeSocket([tool, OSError("Pi link lost after tool result")])
    second = FakeSocket(
        [
            tool,
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=workspace_manager,
        websocket_connector=SequencedConnector(first, second),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )
    try:
        assert [event["type"] for event in asyncio.run(_collect(runner))] == ["done"]
        request_types = [
            json.loads(process.stdin.writes[0].splitlines()[1].decode("utf-8"))["type"]
            for process in relay.processes
        ]
        assert json.loads(first.sent[1])["ok"] is True, (
            request_types,
            json.loads(first.sent[1]),
        )
        assert (workspace / "marker").read_text() == "x"
        assert request_types == ["ensure_workspace", "exec", "attach_execution"]
        assert request_types.count("exec") == 1
        assert json.loads(first.sent[1]) == json.loads(second.sent[1])
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_external_pi_runner_does_not_resend_resolved_tool_result_after_later_loss():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    tool = (
        '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
        '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,'
        '"max_bytes":1024,"worker_sequence":1}'
    )
    first = FakeSocket(
        [
            tool,
            '{"type":"workspace_ready","worker_sequence":2}',
            OSError("later link loss"),
        ]
    )
    second = FakeSocket(
        [
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":3}',
            '{"type":"worker_done","status":"complete","worker_sequence":4}',
        ]
    )
    connector = SequencedConnector(first, second)
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        workspace_manager=FakeWorkspaceManager(provider),
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == [
        "workspace_ready",
        "done",
    ]
    assert executor.reads == 1
    assert [json.loads(frame)["type"] for frame in second.sent] == [
        "attach_turn",
        "ack_terminal",
    ]
    assert json.loads(second.sent[0])["afterSequence"] == 2


def test_external_pi_runner_classifies_exact_worker_loss_without_new_model_run():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    replacement = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 8, "release-b", "external-pi-v1"
    )
    statuses = iter([worker_status(claim), worker_status(replacement)])
    socket = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("worker lost")]
    )
    connector = SequencedConnector(socket)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(next(statuses)),
        session_factory=SessionContext,
    )
    observations: list[tuple[str, str | None, int]] = []
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )
    stale_events = []
    runner.record_evidence = lambda **event: stale_events.append(event) or True

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "external_worker_lost",
            "message": "The research run was interrupted.",
        },
    ]
    assert len(connector.calls) == 1
    assert ("typed_failure", "external_worker_lost", 1) in observations
    assert ("worker_reconnect", None, 1) not in observations
    assert [event["event_type"] for event in stale_events] == ["stale_fence"]


@pytest.mark.parametrize(
    "status_error",
    [
        ExternalPiWorkerUnavailable("worker unavailable"),
        ExternalPiWorkerControlRejected("malformed worker status"),
    ],
    ids=["unavailable", "malformed-or-rejected"],
)
def test_external_pi_runner_classifies_status_control_failure_as_worker_loss(
    status_error,
):
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    statuses = iter([worker_status(claim), status_error])

    async def resolve_status():
        status = next(statuses)
        if isinstance(status, BaseException):
            raise status
        return status

    socket = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("link lost")]
    )
    connector = SequencedConnector(socket)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=resolve_status,
        session_factory=SessionContext,
    )
    observations: list[tuple[str, str | None, int]] = []
    runner.observe = lambda event, code, value: observations.append(
        (event, code, value)
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "external_worker_lost",
            "message": "The research run was interrupted.",
        },
    ]
    assert len(connector.calls) == 1
    assert ("typed_failure", "external_worker_lost", 1) in observations
    assert ("worker_reconnect", None, 1) not in observations


@pytest.mark.parametrize(
    "status_error",
    [
        ExternalPiWorkerUnavailable("worker unavailable"),
        ExternalPiWorkerControlRejected("malformed worker status"),
    ],
)
def test_external_pi_detached_cancel_tolerates_status_control_failure(status_error):
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )

    async def rejected_status():
        raise status_error

    connector = SequencedConnector()
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=rejected_status,
        session_factory=SessionContext,
    )
    runner.external_worker_claim = claim

    asyncio.run(runner.cancel())
    assert connector.calls == []
