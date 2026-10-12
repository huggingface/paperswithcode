"""Runner executor creation, bash routing, loss handling, and stream producers."""

import asyncio
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
)
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionLost,
    SandboxExecutorClient,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.chat_sandbox.executor_client_harness import (
    _Process,
    _Provider,
)
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeSocket,
    FakeWorkerRepository,
    FakeWorkspaceManager,
    LostExecutor,
    SessionContext,
    SocketContext,
    _async_value,
    _collect,
    worker_status,
)


@pytest.mark.parametrize("stop_after_done", [False, True])
def test_external_pi_runner_lazily_creates_executor_for_remote_read(stop_after_done):
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
        events = [first]
        async for event in stream:
            events.append(event)
            if event["type"] == "done":
                # The consumer may close as soon as completion is published.
                assert len(workspace_manager.released) == 1
                if stop_after_done:
                    break
        await stream.aclose()
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
    coordinator._cancel_requested_after_error = lambda: asyncio.sleep(0, result=False)
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
