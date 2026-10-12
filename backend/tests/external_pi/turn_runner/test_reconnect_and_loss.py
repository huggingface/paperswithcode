"""Reattach, replay, reconnect, and worker-loss classification."""

import asyncio
from datetime import UTC, datetime, timedelta
import json
import threading
import uuid

import pytest

from backend.config import get_settings
from backend.chat_sandbox_worker.executor_daemon import ExecutorServer
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerControlRejected,
    ExternalPiWorkerUnavailable,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
)
from backend.services.chat_sandbox_executor import (
    SandboxExecutorClient,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.chat_sandbox.executor_client_harness import (
    _Broker,
    _DropFirstResponseSocketProvider,
)
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeSocket,
    FakeWorkerRepository,
    FakeWorkspaceManager,
    SequencedConnector,
    SessionContext,
    _async_value,
    _collect,
    _tool_runner,
    worker_status,
)


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


@pytest.mark.parametrize("concurrent", [False, True])
def test_failed_persistent_attachment_does_not_allocate_again(concurrent):
    from backend.services.chat_sandbox_provider import SandboxError

    manager = FakeWorkspaceManager(FakeProvider())
    runner = _tool_runner(FakeExecutor(), manager)
    attachments = []

    async def failed_attachment(workspace, _claim, _minimum):
        attachments.append(workspace)
        raise SandboxError("sandbox_executor_attachment_failed", "Attachment failed")

    runner.tool_executor.channel_factory = failed_attachment

    async def call(index):
        return await runner._tool_result(
            {
                "operation_id": f"operation-{index}",
                "tool_call_id": f"tool-{index}",
                "operation": "exec",
                "command": "pwd",
                "timeout_ms": 1000,
            }
        )

    async def run():
        if concurrent:
            return await asyncio.gather(call(1), call(2))
        return [await call(1), await call(2)]

    results = asyncio.run(run())
    assert [result["error"] for result in results] == [
        "sandbox_executor_attachment_failed",
        "executor_transport_unavailable",
    ]
    assert all(result["ok"] is False for result in results)
    assert len(manager.acquired) == len(attachments) == len(manager.invalidated) == 1
