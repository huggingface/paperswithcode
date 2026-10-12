from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker.protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_sandbox_acquisition_coordinator import PoolAcquired
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import ChatComputeDisabled
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.services.chat_sandbox_turn_coordinator import (
    ChatSandboxTurnCoordinator,
    ChatSandboxTurnRequest,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    WorkerCancelStatus,
    WorkerTurnDispatchOutcome,
    WorkerTurnMilestone,
)
from backend.tests.chat_sandbox.turn_harness import (
    TurnHarnessSession,
    build_turn_coordinator,
)


def _request() -> ChatSandboxTurnRequest:
    return ChatSandboxTurnRequest(
        chat_session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        request_id="request-test",
        prompt="prompt",
        model="model",
        resume=None,
        capability_token="capability",
    )


def test_manager_turn_facade_builds_typed_request_and_preserves_stream_contract():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class TurnCoordinator:
        request: ChatSandboxTurnRequest | None = None

        async def run(self, request):
            self.request = request
            yield {"type": "sandbox_start", "session_id": str(session_id)}
            yield {"type": "done", "resume": "resume-next"}

    coordinator = TurnCoordinator()
    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    manager._sandbox_turn = coordinator

    async def run():
        return [
            event
            async for event in manager.run_turn(
                chat_session_id=session_id,
                turn_id=turn_id,
                request_id="request-a",
                prompt="private prompt",
                model="model-a",
                resume="resume-a",
                capability=SimpleNamespace(token="private capability"),
                web_search_enabled=True,
                fetchable_urls=["https://example.test/paper"],
                hf_username="test-user",
            )
        ]

    assert asyncio.run(run()) == [
        {"type": "sandbox_start", "session_id": str(session_id)},
        {"type": "done", "resume": "resume-next"},
    ]
    assert coordinator.request == ChatSandboxTurnRequest(
        chat_session_id=session_id,
        turn_id=turn_id,
        request_id="request-a",
        prompt="private prompt",
        model="model-a",
        resume="resume-a",
        capability_token="private capability",
        web_search_enabled=True,
        fetchable_urls=("https://example.test/paper",),
        hf_username="test-user",
    )
    request_repr = repr(coordinator.request)
    assert "private prompt" not in request_repr
    assert "private capability" not in request_repr


def test_manager_cancel_facade_preserves_legacy_boolean_contract():
    statuses = iter(
        [
            WorkerCancelStatus.NOT_FOUND,
            WorkerCancelStatus.PENDING,
            WorkerCancelStatus.COMPLETED,
            WorkerCancelStatus.CONTROL_LOST,
            WorkerCancelStatus.TIMED_OUT,
        ]
    )

    class TurnCoordinator:
        async def cancel(self, _chat_session_id, _turn_id):
            return next(statuses)

    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    manager._sandbox_turn = TurnCoordinator()

    async def run():
        return [await manager.cancel(uuid.uuid4(), uuid.uuid4()) for _index in range(5)]

    assert asyncio.run(run()) == [False, True, True, True, True]


def test_manager_exposes_typed_cancel_status_without_changing_legacy_facade():
    class TurnCoordinator:
        async def cancel(self, _chat_session_id, _turn_id):
            return WorkerCancelStatus.CONTROL_LOST

    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    manager._sandbox_turn = TurnCoordinator()

    status = asyncio.run(manager.cancel_status(uuid.uuid4(), uuid.uuid4()))

    assert status is WorkerCancelStatus.CONTROL_LOST


def test_manager_composes_one_shared_turn_component_graph():
    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )

    coordinator = manager._turn_coordinator()

    assert coordinator is manager._turn_coordinator()
    assert coordinator.state_repository is manager._state_repository()
    assert coordinator.acquisition is manager._acquisition_coordinator()
    assert coordinator.transport is manager._worker_transport()
    assert coordinator.lifecycle is manager._lease_lifecycle_coordinator()
    assert coordinator.maintenance is manager._lease_maintenance_coordinator()


def test_turn_coordinator_rejects_mismatched_state_settings():
    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    coordinator = manager._turn_coordinator()
    mismatched_repository = ChatSandboxStateRepository(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )

    with pytest.raises(ValueError, match="Turn state settings must be shared"):
        ChatSandboxTurnCoordinator(
            manager.settings,
            session_factory=manager.session_factory,
            state_repository=mismatched_repository,
            acquisition=coordinator.acquisition,
            transport=coordinator.transport,
            lifecycle=coordinator.lifecycle,
            maintenance=coordinator.maintenance,
        )


def test_turn_spend_rejection_commits_trip_before_mapping_and_skips_acquisition():
    events: list[str] = []

    class Session(TurnHarnessSession):
        def commit(self):
            events.append("commit")

    class Spend:
        @staticmethod
        def assert_available():
            events.append("trip")
            raise ChatComputeDisabled("Chat is temporarily disabled")

    async def unexpected_acquire(*_args, **_kwargs):
        events.append("acquire")
        raise AssertionError("spend rejection must stop before acquisition")

    settings = Settings(
        _env_file=None,
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_spend_enforcement_enabled=True,
    )
    coordinator = build_turn_coordinator(
        settings,
        ChatSandboxWorkerTransport(SimpleNamespace()),
        acquire=unexpected_acquire,
        session_factory=Session,
        spend_factory=lambda _db: Spend(),
    )

    async def run():
        with pytest.raises(SandboxError) as raised:
            async for _event in coordinator.run(_request()):
                pass
        return raised.value

    error = asyncio.run(run())
    assert error.code == "chat_temporarily_disabled"
    assert str(error) == "Chat is temporarily disabled"
    assert error.uncertain is False
    assert events == ["trip", "commit"]


def test_turn_spend_success_commits_once_before_budget_prechecked_acquisition():
    events: list[object] = []

    class Session(TurnHarnessSession):
        def commit(self):
            events.append("commit")

    class Spend:
        @staticmethod
        def assert_available():
            events.append("available")

    class AcquisitionReached(RuntimeError):
        pass

    async def acquire(session_id, **kwargs):
        events.append(("acquire", session_id, kwargs))
        raise AcquisitionReached

    settings = Settings(
        _env_file=None,
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_spend_enforcement_enabled=True,
        chat_persistent_worker_enabled=False,
    )
    coordinator = build_turn_coordinator(
        settings,
        ChatSandboxWorkerTransport(SimpleNamespace()),
        acquire=acquire,
        session_factory=Session,
        spend_factory=lambda _db: Spend(),
    )
    request = _request()

    async def run():
        with pytest.raises(AcquisitionReached):
            async for _event in coordinator.run(request):
                pass

    asyncio.run(run())
    assert events == [
        "available",
        "commit",
        (
            "acquire",
            request.chat_session_id,
            {
                "pool_miss": False,
                "pool_miss_reason": None,
                "budget_prechecked": True,
                "allow_pool": False,
            },
        ),
    ]


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        (TimeoutError("late timeout"), "sandbox_timeout", "The research run timed out"),
        (
            ProtocolError("late protocol failure"),
            "sandbox_worker_failed",
            "The worker protocol failed",
        ),
    ],
)
def test_post_sdk_failures_map_without_reusing_or_retrying(
    failure,
    expected_code,
    expected_message,
):
    settings = Settings(
        _env_file=None,
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_spend_enforcement_enabled=False,
        chat_persistent_worker_enabled=True,
        chat_agent_timeout_seconds=1,
        chat_gateway_url="https://gateway.example.test",
    )
    sandbox = SimpleNamespace(object_id="sb-pool")
    acquisition_calls = 0

    async def acquire(*_args, **_kwargs):
        nonlocal acquisition_calls
        acquisition_calls += 1
        return PoolAcquired(sandbox, elapsed_ms=4, pool_lookup_ms=2)

    class Execution:
        sdk_dispatched = False
        terminal = False
        cancel_requested = False
        closed = False

        async def dispatch(self):
            return WorkerTurnDispatchOutcome.DISPATCHED

        async def events(self, *, timeout_seconds):
            assert timeout_seconds == 1
            self.sdk_dispatched = True
            yield WorkerTurnMilestone.SDK_DISPATCHED
            raise failure

        async def close(self):
            self.closed = True

    execution = Execution()
    transport = ChatSandboxWorkerTransport(SimpleNamespace())
    transport.create_execution = lambda *_args, **_kwargs: execution
    terminations: list[tuple] = []

    async def terminate_worker(*args, **kwargs):
        terminations.append((args, kwargs))

    coordinator = build_turn_coordinator(
        settings,
        transport,
        acquire=acquire,
        terminate_worker=terminate_worker,
    )
    request = _request()

    async def run():
        with pytest.raises(SandboxError) as raised:
            async for _event in coordinator.run(request):
                pass
        return raised.value

    error = asyncio.run(run())
    assert error.code == expected_code
    assert str(error) == expected_message
    assert error.uncertain is True
    assert acquisition_calls == 1
    assert execution.closed is True
    assert len(terminations) == 1
    assert terminations[0][0][0] == request.chat_session_id
    assert terminations[0][0][1].sandbox_id == sandbox.object_id
    assert terminations[0][1] == {"failure_code": "sandbox_worker_failed"}
