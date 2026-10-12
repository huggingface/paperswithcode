from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.chat_sandbox_worker.protocol import encode_frame
from backend.config import Settings
from backend.services import chat_turn_runner
from backend.services.chat_sandbox_acquisition_coordinator import LeaseReused
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    WorkerClaim,
)
from backend.services.chat_sandbox_turn_coordinator import ChatSandboxTurnRequest
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    RunningWorker,
    WorkerCancelStatus,
)
from backend.tests.chat_sandbox.turn_harness import (
    TurnHarnessSession,
    build_turn_coordinator,
)


async def _unexpected_turn_termination(*_args, **_kwargs):
    raise AssertionError("turn unexpectedly terminated its lease")


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _Probe:
    returncode = 0

    def __init__(self):
        self.wait = _AsyncCall(self._wait)

    async def _wait(self):
        return None


class _Sandbox:
    def __init__(self, object_id: str):
        self.object_id = object_id
        self.poll = _AsyncCall(self._poll)
        self.exec = _AsyncCall(self._exec)
        self.terminate = _AsyncCall(self._terminate)

    async def _poll(self):
        return None

    async def _exec(self, *_args, **_kwargs):
        return _Probe()

    async def _terminate(self, *, wait):
        assert wait is False


def _lease(*, state: str, sandbox_id: str | None):
    return SimpleNamespace(
        modal_sandbox_id=sandbox_id,
        app_release_id="old-release",
        image_version="im-current",
        worker_contract_version="worker-v1",
        worker_generation="generation-a",
        state=state,
        lease_token_hash=None,
        lease_expires_at=None,
        last_activity_at=datetime.now(UTC),
        workspace_snapshot_id=None,
        snapshot_image_version=None,
        snapshot_updated_at=None,
        workspace_dirty=False,
        failure_code=None,
        updated_at=datetime.now(UTC),
    )


def test_persistent_turns_reuse_one_control_attachment():
    class Connection:
        def __init__(self):
            self.chunks: asyncio.Queue[bytes] = asyncio.Queue()
            self.sent: list[bytes] = []
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.chunks.get()

        async def send(self, payload):
            self.sent.append(payload)
            request_id = f"request-{len(self.sent)}"
            await self.chunks.put(
                b"".join(
                    [
                        encode_frame(
                            {
                                "v": 1,
                                "type": "workspace_ready",
                                "request_id": request_id,
                            }
                        ),
                        encode_frame(
                            {
                                "v": 1,
                                "type": "done",
                                "request_id": request_id,
                            }
                        ),
                        encode_frame(
                            {
                                "v": 1,
                                "type": "worker_done",
                                "request_id": request_id,
                                "status": "complete",
                            }
                        ),
                    ]
                )
            )

        async def close(self):
            self.closed = True

    async def run():
        connection = Connection()
        sandbox = SimpleNamespace(object_id="sb-persistent")
        start_calls = 0

        class Provider:
            async def open_persistent_connection(self, candidate, worker_generation):
                nonlocal start_calls
                start_calls += 1
                assert candidate is sandbox
                assert worker_generation == "generation-a"
                return connection

        settings = Settings(
            _env_file=None,
            chat_workspace_snapshots_enabled=False,
            chat_persistent_worker_enabled=True,
            chat_persistent_sandbox_lifetime_seconds=86400,
            chat_agent_timeout_seconds=2,
            chat_gateway_url="https://gateway.example.test",
        )
        transport = ChatSandboxWorkerTransport(Provider())
        session_factory = TurnHarnessSession
        acquisition_calls = 0
        lease = object()
        claims: list[WorkerClaim] = []

        class StateRepository:
            def __init__(self):
                self.settings = settings

            @staticmethod
            def load_lease(_db, loaded_session_id, *, lock):
                assert loaded_session_id == session_id
                assert lock is True
                return lease

            @staticmethod
            def claim_worker(
                loaded_lease,
                *,
                sandbox_id,
                assignment_token,
                now,
            ):
                assert loaded_lease is lease
                assert sandbox_id == "sb-persistent"
                assert assignment_token == "assignment-token"
                assert now.tzinfo is UTC
                claim = WorkerClaim(
                    sandbox_id=sandbox_id,
                    token_hash="claim",
                    assignment_token=assignment_token,
                    worker_generation="generation-a",
                )
                claims.append(claim)
                return claim

            @staticmethod
            def release_worker(loaded_lease, *, claim, now):
                nonlocal released
                assert loaded_lease is lease
                assert claim is claims[-1]
                assert now.tzinfo is UTC
                released += 1
                return True

        async def acquire(loaded_session_id, **kwargs):
            nonlocal acquisition_calls
            assert loaded_session_id == session_id
            assert kwargs == {
                "pool_miss": False,
                "budget_prechecked": True,
                "allow_pool": False,
                "pool_miss_reason": None,
            }
            acquisition_calls += 1
            return LeaseReused(sandbox, elapsed_ms=1, pool_lookup_ms=None)

        released = 0
        warm_cap_calls = 0

        async def unexpected_terminate_worker(*_args, **_kwargs):
            raise AssertionError("completed turn unexpectedly terminated its worker")

        async def enforce_warm_cap():
            nonlocal warm_cap_calls
            warm_cap_calls += 1
            return 0

        session_id = uuid.uuid4()
        repository = StateRepository()
        coordinator = build_turn_coordinator(
            settings,
            session_factory=session_factory,
            state_repository=repository,
            transport=transport,
            acquire=acquire,
            terminate_worker=unexpected_terminate_worker,
            terminate=_unexpected_turn_termination,
            enforce_warm_cap=enforce_warm_cap,
            blank_pool_enabled=False,
        )
        for index in (1, 2):
            if index == 2:
                transport.session_controls[session_id].resume_id = "failed-branch"
            events = []
            turn_id = uuid.uuid4()
            stream = coordinator.run(
                ChatSandboxTurnRequest(
                    chat_session_id=session_id,
                    turn_id=turn_id,
                    request_id=f"request-{index}",
                    prompt="prompt",
                    model="model",
                    resume="durable-branch",
                    capability_token="capability",
                )
            )
            async for event in stream:
                events.append(event)
                if event["type"] == "done":
                    running = transport.running_worker(turn_id)
                    assert running is not None
                    assert running.done is not None and running.done.is_set()
            expected = [
                ("sandbox_start", None),
                ("lifecycle", "preparing_workspace"),
                ("_latency", "sandbox_acquisition_ms"),
                ("sandbox_ready", None),
                ("lifecycle", "starting_agent"),
            ]
            if index == 1:
                expected.append(("_latency", "control_connection"))
            expected.extend(
                [
                    ("_latency", "capability_install_ms"),
                    ("_latency", "sdk_dispatch_ms"),
                    ("lifecycle", "connecting_model"),
                    ("workspace_ready", None),
                    ("done", None),
                ]
            )
            assert [(event["type"], event.get("phase")) for event in events] == expected
            assert released == index
        assert transport.session_controls[session_id].resume_id is None
        transport.drop_session_control(session_id)
        if transport.close_tasks:
            await asyncio.gather(*transport.close_tasks, return_exceptions=True)
        assert start_calls == 1
        assert acquisition_calls == 1
        assert warm_cap_calls == 2
        assert len(connection.sent) == 2
        assert connection.closed is True

    asyncio.run(run())


def test_turn_runners_share_session_manager_for_one_settings_instance(monkeypatch):
    created: list[object] = []

    class Manager:
        def __init__(self, settings, **_kwargs):
            self.settings = settings
            created.append(settings)

    monkeypatch.setattr(chat_turn_runner, "SandboxSessionManager", Manager)
    monkeypatch.setattr(chat_turn_runner, "_manager", None)
    monkeypatch.setattr(chat_turn_runner, "_manager_settings", None)
    first_settings = object()
    second_settings = object()

    first = chat_turn_runner.shared_sandbox_manager(first_settings)
    assert chat_turn_runner.shared_sandbox_manager(first_settings) is first
    second = chat_turn_runner.shared_sandbox_manager(second_settings)

    assert second is not first
    assert created == [first_settings, second_settings]


def test_cancel_control_write_failure_terminates_worker():
    class Input:
        def __init__(self):
            self.drain = _AsyncCall(self._drain)

        def write(self, _payload):
            pass

        async def _drain(self):
            raise RuntimeError("control closed")

    async def run():
        settings = Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
        session_factory = TurnHarnessSession
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        claim = WorkerClaim(sandbox_id="sb-cancel", token_hash="claim")
        terminated: list[str] = []

        class Provider:
            pass

        class StateRepository:
            def __init__(self):
                self.settings = settings

        transport = ChatSandboxWorkerTransport(Provider())
        done = asyncio.Event()
        transport.register_running_worker(
            turn_id,
            RunningWorker(
                process=SimpleNamespace(stdin=Input()),
                request_id="request",
                claim=claim,
                done=done,
            ),
        )

        async def unused_acquire(*_args, **_kwargs):
            raise AssertionError("cancel unexpectedly acquired a sandbox")

        async def terminate_worker(
            loaded_session_id,
            loaded_claim,
            *,
            failure_code,
        ):
            assert loaded_session_id == session_id
            assert loaded_claim is claim
            terminated.append(failure_code)
            return True

        async def unused_warm_cap():
            raise AssertionError("cancel unexpectedly enforced the warm cap")

        coordinator = build_turn_coordinator(
            settings,
            session_factory=session_factory,
            state_repository=StateRepository(),
            transport=transport,
            acquire=unused_acquire,
            terminate_worker=terminate_worker,
            terminate=_unexpected_turn_termination,
            enforce_warm_cap=unused_warm_cap,
            blank_pool_enabled=False,
        )

        assert (
            await coordinator.cancel(session_id, turn_id)
            is WorkerCancelStatus.CONTROL_LOST
        )
        assert terminated == ["cancel_control_lost"]
        assert done.is_set()

    asyncio.run(run())


def test_stale_successful_worker_cannot_release_a_successor_or_termination():
    lease = _lease(state="busy", sandbox_id="sb-old")
    lease.lease_token_hash = "worker-old"
    repository = ChatSandboxStateRepository(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    stale_claim = WorkerClaim("sb-old", "worker-old")

    lease.modal_sandbox_id = "sb-new"
    lease.lease_token_hash = "worker-new"
    assert not repository.release_worker(
        lease,
        claim=stale_claim,
        now=datetime.now(UTC),
    )
    assert lease.state == "busy"
    assert lease.modal_sandbox_id == "sb-new"
    assert lease.lease_token_hash == "worker-new"
    assert not lease.workspace_dirty

    lease.state = "terminating"
    lease.modal_sandbox_id = "sb-old"
    lease.lease_token_hash = "termination-new"
    assert not repository.release_worker(
        lease,
        claim=stale_claim,
        now=datetime.now(UTC),
    )
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-old"
    assert lease.lease_token_hash == "termination-new"
    assert not lease.workspace_dirty
