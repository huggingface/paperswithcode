"""Fake sockets, workers, providers, and executors for external Pi turn-runner tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid


from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
    StaleWorkerClaim,
)
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionLost,
    ExecutorExecutionResult,
    ExecutorReadResult,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim


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
