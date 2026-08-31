from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker.protocol import (
    MAX_WIRE_FRAME_BYTES,
    ProtocolError,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.config import Settings
from backend.services.chat_sandbox_acquisition_coordinator import SandboxCreated
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_state_repository import WorkerClaim
from backend.services.chat_sandbox_turn_coordinator import ChatSandboxTurnRequest
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    RunningWorker,
    SessionControl,
    WorkerCancelStatus,
    WorkerTurnDispatchOutcome,
    WorkerTurnMilestone,
    WorkerTurnMode,
    WorkerTurnRequest,
)
from backend.tests.chat_sandbox_turn_harness import build_turn_coordinator


class _AsyncConnection:
    def __init__(self):
        self.incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.sent: list[bytes] = []
        self.close_calls = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.incoming.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.close_calls += 1
        await self.incoming.put(None)


class _CloseProcess:
    def __init__(self, *, wait_to_close: bool = False):
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.allow_close = asyncio.Event()
        if not wait_to_close:
            self.allow_close.set()

    async def aclose(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        await self.allow_close.wait()


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _ChunkStream:
    def __init__(self, chunks=()):
        self.items: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()
        for chunk in chunks:
            self.items.put_nowait(chunk)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.items.get()
        if item is None:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item

    async def feed(self, *chunks: bytes) -> None:
        for chunk in chunks:
            await self.items.put(chunk)

    async def finish(self) -> None:
        await self.items.put(None)


class _RecordingStdin:
    def __init__(self, drain_action=None):
        self.writes: list[bytes] = []
        self.drain_calls = 0
        self.drain_started = asyncio.Event()
        self._drain_action = drain_action
        self.drain = _AsyncCall(self._drain)

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    async def _drain(self) -> None:
        self.drain_calls += 1
        self.drain_started.set()
        if self._drain_action is not None:
            await self._drain_action()


class _OneShotProcess:
    def __init__(self, *, chunks=(), drain_action=None, wait_action=None):
        self.stdin = _RecordingStdin(drain_action)
        self.stdout = _ChunkStream(chunks)
        self.stderr = _ChunkStream([None])
        self.wait_calls = 0
        self.wait_started = asyncio.Event()
        self._wait_action = wait_action
        self.wait = _AsyncCall(self._wait)

    async def _wait(self) -> None:
        self.wait_calls += 1
        self.wait_started.set()
        if self._wait_action is not None:
            await self._wait_action()


class _TurnProvider:
    def __init__(self, *, connection=None, process=None):
        self.connection = connection
        self.process = process
        self.persistent_calls: list[tuple[object, str]] = []
        self.process_calls: list[tuple[object, int]] = []

    async def open_persistent_connection(self, sandbox, worker_generation):
        self.persistent_calls.append((sandbox, worker_generation))
        return self.connection

    async def open_turn_process(self, sandbox, *, timeout_seconds):
        self.process_calls.append((sandbox, timeout_seconds))
        return self.process


def _transport(*, clock=None):
    async def unexpected_open(_sandbox, _worker_generation):
        raise AssertionError("this test must not open a provider connection")

    provider = SimpleNamespace(
        open_persistent_connection=unexpected_open,
        open_turn_process=None,
    )
    options = {}
    if clock is not None:
        options["clock"] = clock
    return ChatSandboxWorkerTransport(provider, **options)


def _control(sandbox_id: str, process=None) -> SessionControl:
    return SessionControl(
        process=process or _CloseProcess(),
        sandbox=SimpleNamespace(object_id=sandbox_id),
        sandbox_id=sandbox_id,
        stderr_task=None,
        reader_task=None,
        queues={},
        resume_id=None,
    )


def _running(request_id: str) -> RunningWorker:
    return RunningWorker(
        process=object(),
        request_id=request_id,
        claim=WorkerClaim("sb-worker", "claim-token"),
        done=asyncio.Event(),
    )


def _turn_request(**overrides) -> WorkerTurnRequest:
    values = {
        "chat_session_id": uuid.uuid4(),
        "turn_id": uuid.uuid4(),
        "request_id": "request-turn",
        "prompt": "research prompt",
        "model": "openai/gpt-test",
        "resume": "resume-id",
        "capability_token": "capability-token",
        "gateway_url": "https://gateway.example.test",
        "web_search_enabled": True,
        "reader_mode": False,
        "fetchable_urls": ("https://papers.example/one",),
        "hf_username": "test-user",
    }
    values.update(overrides)
    return WorkerTurnRequest(**values)


def _turn_claim() -> WorkerClaim:
    return WorkerClaim(
        sandbox_id="sb-turn",
        token_hash="claim-token",
        assignment_token="assignment-token",
        worker_generation="generation-a",
    )


def _decode_dispatch(payload: bytes) -> tuple[dict, dict]:
    launch_wire, run_wire = payload.split(b"\n", 1)
    assert launch_wire.startswith(SUPERVISOR_PREFIX)
    launch = json.loads(launch_wire[len(SUPERVISOR_PREFIX) :])
    return launch, decode_frame(run_wire)


def test_reader_mode_frame_field_is_sent_only_when_enabled():
    transport = _transport()
    claim = _turn_claim()
    sandbox = SimpleNamespace(object_id=claim.sandbox_id)

    disabled = transport.create_execution(
        sandbox=sandbox,
        claim=claim,
        request=_turn_request(reader_mode=False),
        mode=WorkerTurnMode.PERSISTENT,
        process_timeout_seconds=47,
    )
    enabled = transport.create_execution(
        sandbox=sandbox,
        claim=claim,
        request=_turn_request(reader_mode=True),
        mode=WorkerTurnMode.PERSISTENT,
        process_timeout_seconds=47,
    )

    assert "reader_mode" not in _decode_dispatch(disabled._request_frame())[1]
    assert _decode_dispatch(enabled._request_frame())[1]["reader_mode"] is True


def test_provider_protocol_frame_field_preserves_contract_90_compatibility():
    transport = _transport()
    claim = _turn_claim()
    sandbox = SimpleNamespace(object_id=claim.sandbox_id)

    default_protocol = transport.create_execution(
        sandbox=sandbox,
        claim=claim,
        request=_turn_request(
            agent_harness="pi",
            provider_protocol="anthropic-messages",
        ),
        mode=WorkerTurnMode.PERSISTENT,
        process_timeout_seconds=47,
    )
    direct_openai = transport.create_execution(
        sandbox=sandbox,
        claim=claim,
        request=_turn_request(
            agent_harness="pi",
            provider_protocol="openai-responses",
        ),
        mode=WorkerTurnMode.PERSISTENT,
        process_timeout_seconds=47,
    )

    assert (
        "provider_protocol"
        not in _decode_dispatch(default_protocol._request_frame())[1]
    )
    assert (
        _decode_dispatch(direct_openai._request_frame())[1]["provider_protocol"]
        == "openai-responses"
    )


async def _wait_until(predicate) -> None:
    for _ in range(20):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


def test_session_control_cleanup_is_identity_safe_and_session_scoped():
    async def exercise():
        transport = _transport()
        first_session = uuid.uuid4()
        second_session = uuid.uuid4()
        stale = _control("sb-first")
        replacement = _control("sb-first")
        other = _control("sb-other")

        transport.register_session_control(first_session, stale)
        transport.register_session_control(first_session, replacement)
        transport.register_session_control(second_session, other)

        transport.drop_session_control(first_session, expected=stale)
        await asyncio.sleep(0)
        assert transport.session_control(first_session) is replacement
        assert transport.session_control(second_session) is other
        assert stale.process.close_calls == 0
        assert replacement.process.close_calls == 0

        transport.drop_session_control(first_session, expected=replacement)
        await replacement.process.close_started.wait()
        assert transport.session_control(first_session) is None
        assert transport.session_control(second_session) is other
        assert replacement.process.close_calls == 1

        transport.drop_session_control(second_session, expected=other)
        await other.process.close_started.wait()

    asyncio.run(exercise())


def test_drop_by_sandbox_never_closes_an_unrelated_session_control():
    async def exercise():
        transport = _transport()
        matching_session = uuid.uuid4()
        unrelated_session = uuid.uuid4()
        matching = _control("sb-target")
        unrelated = _control("sb-other")
        transport.register_session_control(matching_session, matching)
        transport.register_session_control(unrelated_session, unrelated)

        transport.drop_session_controls_by_sandbox("sb-target")
        await matching.process.close_started.wait()

        assert transport.session_control(matching_session) is None
        assert transport.session_control(unrelated_session) is unrelated
        assert matching.process.close_calls == 1
        assert unrelated.process.close_calls == 0

        transport.drop_session_control(unrelated_session, expected=unrelated)
        await unrelated.process.close_started.wait()

    asyncio.run(exercise())


def test_blank_control_health_and_promotion_have_one_owner():
    clock_values = iter([10.0, 30.0])

    async def exercise():
        transport = _transport(clock=lambda: next(clock_values))
        session_id = uuid.uuid4()
        control = _control("sb-blank")
        other = _control("sb-other")

        transport.register_blank_control("sb-blank", control)
        transport.register_blank_control("sb-other", other, checked_at=20.0)
        assert transport.blank_health_checked_at("sb-blank") == 10.0
        assert transport.blank_health_checked_at("sb-other") == 20.0

        assert transport.mark_blank_healthy("sb-blank", expected=control)
        assert transport.blank_health_checked_at("sb-blank") == 30.0

        assert (
            transport.promote_blank_control("sb-blank", session_id, expected=control)
            is control
        )
        assert transport.blank_control("sb-blank") is None
        assert transport.blank_health_checked_at("sb-blank") is None
        assert transport.session_control(session_id) is control
        assert transport.blank_control("sb-other") is other
        assert control.process.close_calls == 0

        transport.drop_session_control(session_id, expected=control)
        transport.drop_blank_control("sb-other", expected=other)
        await asyncio.gather(
            control.process.close_started.wait(),
            other.process.close_started.wait(),
        )

    asyncio.run(exercise())


def test_missing_blank_control_cannot_be_promoted_into_a_session():
    transport = _transport()
    session_id = uuid.uuid4()
    expected = _control("sb-missing")

    assert (
        transport.promote_blank_control("sb-missing", session_id, expected=expected)
        is None
    )
    assert transport.blank_control("sb-missing") is None
    assert transport.blank_health_checked_at("sb-missing") is None
    assert transport.session_control(session_id) is None
    assert expected.process.close_calls == 0


def test_stale_blank_cleanup_preserves_replacement_and_health_timestamp():
    async def exercise():
        transport = _transport()
        stale = _control("sb-blank")
        replacement = _control("sb-blank")
        transport.register_blank_control("sb-blank", stale, checked_at=10.0)
        transport.register_blank_control("sb-blank", replacement, checked_at=20.0)

        assert not transport.mark_blank_healthy(
            "sb-blank", expected=stale, checked_at=30.0
        )
        assert (
            transport.promote_blank_control("sb-blank", uuid.uuid4(), expected=stale)
            is None
        )
        transport.drop_blank_control("sb-blank", expected=stale)
        await asyncio.sleep(0)

        assert transport.blank_control("sb-blank") is replacement
        assert transport.blank_health_checked_at("sb-blank") == 20.0
        assert stale.process.close_calls == 0
        assert replacement.process.close_calls == 0

        transport.drop_blank_control("sb-blank", expected=replacement)
        await replacement.process.close_started.wait()

    asyncio.run(exercise())


def test_running_worker_cleanup_is_identity_safe_and_turn_scoped():
    transport = _transport()
    first_turn = uuid.uuid4()
    second_turn = uuid.uuid4()
    stale = _running("stale-request")
    replacement = _running("replacement-request")
    other = _running("other-request")

    transport.register_running_worker(first_turn, stale)
    transport.register_running_worker(first_turn, replacement)
    transport.register_running_worker(second_turn, other)

    transport.remove_running_worker(first_turn, expected=stale)
    assert transport.running_worker(first_turn) is replacement
    assert transport.running_worker(second_turn) is other

    transport.remove_running_worker(first_turn, expected=replacement)
    assert transport.running_worker(first_turn) is None
    assert transport.running_worker(second_turn) is other


def test_control_close_is_deduplicated_while_background_close_is_running():
    async def exercise():
        transport = _transport()
        session_id = uuid.uuid4()
        process = _CloseProcess(wait_to_close=True)
        control = _control("sb-shared", process)
        transport.register_session_control(session_id, control)
        transport.register_blank_control("sb-shared", control, checked_at=10.0)

        transport.drop_session_control(session_id, expected=control)
        transport.drop_blank_control("sb-shared", expected=control)
        await process.close_started.wait()
        assert process.close_calls == 1

        process.allow_close.set()
        await _wait_until(lambda: not transport.close_tasks)
        assert process.close_calls == 1

    asyncio.run(exercise())


def test_one_shot_process_open_forwards_exact_timeout_and_provider_result():
    async def exercise():
        sandbox = object()
        process = object()
        calls: list[tuple[object, int]] = []

        async def open_process(candidate, *, timeout_seconds):
            calls.append((candidate, timeout_seconds))
            return process

        provider = SimpleNamespace(
            open_persistent_connection=None,
            open_turn_process=open_process,
        )
        transport = ChatSandboxWorkerTransport(provider)

        assert await transport.open_turn_process(sandbox, timeout_seconds=47) is process
        assert calls == [(sandbox, 47)]

    asyncio.run(exercise())


def test_one_shot_process_open_preserves_provider_failure():
    async def exercise():
        failure = RuntimeError("provider process unavailable")

        async def open_process(_sandbox, *, timeout_seconds):
            assert timeout_seconds == 47
            raise failure

        provider = SimpleNamespace(
            open_persistent_connection=None,
            open_turn_process=open_process,
        )
        transport = ChatSandboxWorkerTransport(provider)

        with pytest.raises(RuntimeError) as raised:
            await transport.open_turn_process(object(), timeout_seconds=47)
        assert raised.value is failure

    asyncio.run(exercise())


def test_persistent_control_ping_preserves_framing_and_correlation():
    async def exercise():
        connection = _AsyncConnection()
        calls: list[tuple[object, str]] = []

        async def open_connection(sandbox, worker_generation):
            calls.append((sandbox, worker_generation))
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        sandbox = SimpleNamespace(object_id="sb-open")
        control = await transport.open_persistent_control(sandbox, "generation-a")

        ping = asyncio.create_task(transport.ping(control, "generation-a"))
        await _wait_until(lambda: bool(connection.sent))
        wire = connection.sent[0]
        assert wire.startswith(SUPERVISOR_PREFIX)
        request = json.loads(wire[len(SUPERVISOR_PREFIX) :].rstrip(b"\n"))
        await connection.incoming.put(
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_health",
                    "request_id": request["request_id"],
                    "assigned": False,
                }
            )
        )

        assert await ping is True
        assert calls == [(sandbox, "generation-a")]
        assert request == {
            "operation": "ping",
            "worker_generation": "generation-a",
            "request_id": request["request_id"],
        }
        assert control.queues == {}

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_persistent_control_ping_records_bounded_content_free_startup_metrics():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        sandbox = SimpleNamespace(object_id="sb-prewarmed")
        control = await transport.open_persistent_control(sandbox, "generation-a")
        ping = asyncio.create_task(transport.ping(control, "generation-a"))
        await _wait_until(lambda: bool(connection.sent))
        request = json.loads(connection.sent[0][len(SUPERVISOR_PREFIX) :].rstrip(b"\n"))
        await connection.incoming.put(
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_health",
                    "request_id": request["request_id"],
                    "assigned": False,
                    "agent_prestarted": True,
                    "startup_metrics": {
                        "broker_ready_ms": 12,
                        "control_ready_ms": 19,
                        "agent_spawn_ms": 20,
                        "agent_startup_ready_ms": 87,
                    },
                }
            )
        )

        assert await ping is True
        metrics = transport.blank_startup_metrics("sb-prewarmed")
        assert metrics is not None
        assert metrics.agent_prestarted is True
        assert metrics.agent_startup_ready_ms == 87

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_persistent_control_ping_rejects_malformed_startup_metrics():
    assert (
        ChatSandboxWorkerTransport._startup_metrics(
            {
                "broker_ready_ms": 20,
                "control_ready_ms": 10,
                "agent_spawn_ms": None,
                "agent_startup_ready_ms": None,
            },
            agent_prestarted=False,
        )
        is None
    )


def test_cancelled_ping_removes_its_request_queue():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        ping = asyncio.create_task(transport.ping(control, "generation-a"))
        await _wait_until(lambda: bool(control.queues))

        ping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ping
        assert control.queues == {}

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_reader_cancellation_wakes_all_correlated_requests_and_propagates():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        first: asyncio.Queue = asyncio.Queue()
        second: asyncio.Queue = asyncio.Queue()
        control.queues.update({"request-a": first, "request-b": second})

        assert control.reader_task is not None
        await asyncio.sleep(0)
        control.reader_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await control.reader_task

        failures = [await first.get(), await second.get()]
        assert all(isinstance(error, SandboxError) for error in failures)
        assert all(error.code == "sandbox_worker_failed" for error in failures)
        assert all(error.uncertain for error in failures)

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_uncorrelated_frame_fails_every_live_request_without_cross_routing():
    async def exercise():
        connection = _AsyncConnection()

        async def open_connection(_sandbox, _worker_generation):
            return connection

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=open_connection,
                open_turn_process=None,
            )
        )
        control = await transport.open_persistent_control(
            SimpleNamespace(object_id="sb-open"), "generation-a"
        )
        first: asyncio.Queue = asyncio.Queue()
        second: asyncio.Queue = asyncio.Queue()
        control.queues.update({"request-a": first, "request-b": second})

        await connection.incoming.put(
            encode_frame(
                {
                    "v": 1,
                    "type": "worker_ready",
                    "request_id": "unknown-request",
                }
            )
        )
        assert control.reader_task is not None
        await control.reader_task

        failures = [await first.get(), await second.get()]
        assert all(isinstance(error, ProtocolError) for error in failures)
        assert all("Uncorrelated" in str(error) for error in failures)
        assert first.empty()
        assert second.empty()

        transport.schedule_close(control)
        await _wait_until(lambda: connection.close_calls == 1)

    asyncio.run(exercise())


def test_transport_drop_control_keeps_existing_lifecycle_contract():
    async def exercise():
        transport = _transport()
        session_id = uuid.uuid4()
        control = _control("sb-manager")
        transport.register_session_control(session_id, control)

        transport.drop_session_control(session_id)
        await control.process.close_started.wait()

        assert session_id not in transport.session_controls
        assert control.process.close_calls == 1

    asyncio.run(exercise())


def test_persistent_turn_execution_preserves_frames_milestones_and_terminal_order():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        sandbox = SimpleNamespace(object_id=claim.sandbox_id)
        process = _OneShotProcess()
        control = _control(claim.sandbox_id, process)
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )

        await execution.dispatch()
        assert process.stdin.drain_calls == 1
        assert len(process.stdin.writes) == 1
        launch, run = _decode_dispatch(process.stdin.writes[0])
        assert launch == {
            "capability": request.capability_token,
            "gateway_url": request.gateway_url,
            "session_id": str(request.chat_session_id),
            "turn_id": str(request.turn_id),
            "assignment_token": claim.assignment_token,
            "worker_generation": claim.worker_generation,
            "agent_harness": "claude",
        }
        assert run == {
            "v": 1,
            "type": "run_turn",
            "request_id": request.request_id,
            "chat_session_id": str(request.chat_session_id),
            "prompt": request.prompt,
            "model": request.model,
            "resume": request.resume,
            "web_search_enabled": True,
            "reasoning_effort": "high",
            "fetchable_urls": list(request.fetchable_urls),
            "hf_username": "test-user",
            "turn_id": str(request.turn_id),
            "assignment_token": claim.assignment_token,
            "worker_generation": claim.worker_generation,
            "agent_harness": "claude",
        }
        running = transport.running_worker(request.turn_id)
        assert running is not None
        assert running.process is process
        assert running.request_id == request.request_id
        assert control.queues.keys() == {request.request_id}

        queue = control.queues[request.request_id]
        for event in (
            {"v": 1, "type": "worker_ready", "request_id": request.request_id},
            {
                "v": 1,
                "type": "_sdk_session",
                "request_id": request.request_id,
                "session_id": "sdk-session-a",
            },
            {"v": 1, "type": "workspace_ready", "request_id": request.request_id},
            {
                "v": 1,
                "type": "reasoning_delta",
                "request_id": request.request_id,
                "delta": "thinking",
            },
            {
                "v": 1,
                "type": "done",
                "request_id": request.request_id,
                "answer": "complete",
            },
            {
                "v": 1,
                "type": "worker_done",
                "request_id": request.request_id,
                "status": "complete",
            },
        ):
            await queue.put(event)

        events = execution.events(timeout_seconds=1)
        observed = []
        async for event in events:
            observed.append(event)
            if event == {"type": "done", "answer": "complete"}:
                assert running.done is not None and running.done.is_set()

        assert observed == [
            WorkerTurnMilestone.AGENT_READY,
            {"type": "_sdk_session", "session_id": "sdk-session-a"},
            WorkerTurnMilestone.SDK_DISPATCHED,
            {"type": "workspace_ready"},
            WorkerTurnMilestone.FIRST_DELTA,
            {"type": "reasoning_delta", "delta": "thinking"},
            {"type": "done", "answer": "complete"},
        ]
        assert control.resume_id == "sdk-session-a"
        assert execution.terminal is True
        assert execution.sdk_dispatched is True
        assert execution.cancel_requested is False

        await execution.close()
        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None
        assert transport.session_control(request.chat_session_id) is control

    asyncio.run(exercise())


def test_one_shot_turn_execution_preserves_frames_wait_and_exact_cleanup():
    async def exercise():
        request = _turn_request(resume=None, web_search_enabled=False)
        claim = _turn_claim()
        sandbox = SimpleNamespace(object_id=claim.sandbox_id)
        frames = b"ignored output\n" + b"".join(
            (
                encode_frame(
                    {
                        "v": 1,
                        "type": "worker_ready",
                        "request_id": request.request_id,
                    }
                ),
                encode_frame(
                    {
                        "v": 1,
                        "type": "done",
                        "request_id": request.request_id,
                    }
                ),
                encode_frame(
                    {
                        "v": 1,
                        "type": "worker_done",
                        "request_id": request.request_id,
                        "status": "complete",
                    }
                ),
            )
        )
        process = _OneShotProcess(chunks=[frames])
        provider = _TurnProvider(process=process)
        transport = ChatSandboxWorkerTransport(provider)
        execution = transport.create_execution(
            sandbox=sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.ONE_SHOT,
            process_timeout_seconds=47,
        )

        await execution.dispatch()
        assert provider.process_calls == [(sandbox, 47)]
        assert process.stdin.drain_calls == 1
        launch, run = _decode_dispatch(process.stdin.writes[0])
        assert launch == {
            "capability": request.capability_token,
            "gateway_url": request.gateway_url,
            "session_id": str(request.chat_session_id),
            "turn_id": str(request.turn_id),
            "agent_harness": "claude",
        }
        assert run == {
            "v": 1,
            "type": "run_turn",
            "request_id": request.request_id,
            "chat_session_id": str(request.chat_session_id),
            "prompt": request.prompt,
            "model": request.model,
            "resume": None,
            "web_search_enabled": False,
            "reasoning_effort": "high",
            "fetchable_urls": list(request.fetchable_urls),
            "hf_username": "test-user",
            "agent_harness": "claude",
        }

        assert [event async for event in execution.events(timeout_seconds=1)] == [
            WorkerTurnMilestone.AGENT_READY,
            {"type": "done"},
        ]
        assert process.wait_calls == 1
        assert execution.terminal is True
        assert transport.session_control(request.chat_session_id) is None

        running = transport.running_worker(request.turn_id)
        assert running is not None
        await execution.close()
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_duplicate_persistent_request_is_rejected_prewrite_without_queue_theft():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        process = _OneShotProcess()
        control = _control(claim.sandbox_id, process)
        existing_queue: asyncio.Queue = asyncio.Queue()
        control.queues[request.request_id] = existing_queue
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=SimpleNamespace(object_id=claim.sandbox_id),
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )

        with pytest.raises(ProtocolError, match="Duplicate persistent request"):
            await execution.dispatch()
        assert process.stdin.writes == []

        await execution.close()
        assert control.queues[request.request_id] is existing_queue
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_execution_close_cannot_remove_successor_queue_or_running_worker():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        successor_queue: asyncio.Queue = asyncio.Queue()
        successor = _running("successor-request")
        control.queues[request.request_id] = successor_queue
        transport.register_running_worker(request.turn_id, successor)

        await execution.close()

        assert control.queues[request.request_id] is successor_queue
        assert transport.running_worker(request.turn_id) is successor
        control.queues.pop(request.request_id)
        transport.remove_running_worker(request.turn_id, expected=successor)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (
            {"v": 1, "type": "worker_ready", "request_id": "wrong-request"},
            "Uncorrelated worker frame",
        ),
        (
            {
                "v": 1,
                "type": "worker_done",
                "request_id": "request-turn",
                "status": "complete",
            },
            "without a semantic terminal event",
        ),
    ],
)
def test_turn_execution_rejects_uncorrelated_or_invalid_event_order(event, message):
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=SimpleNamespace(object_id=claim.sandbox_id),
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        await control.queues[request.request_id].put(event)

        with pytest.raises(ProtocolError, match=message):
            _ = [item async for item in execution.events(timeout_seconds=1)]

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_sdk_resume_identity_is_checked_before_cancelled_event_filtering():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        control.resume_id = "old-sdk-session"
        transport.register_session_control(request.chat_session_id, control)

        assert (
            transport.reusable_sandbox(request.chat_session_id, request.resume)
            is control.sandbox
        )
        assert control.resume_id is None

        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        running = transport.running_worker(request.turn_id)
        assert running is not None
        running.cancel_requested = True
        queue = control.queues[request.request_id]
        await queue.put(
            {
                "v": 1,
                "type": "_sdk_session",
                "request_id": request.request_id,
                "session_id": "new-sdk-session",
            }
        )
        await queue.put(
            {
                "v": 1,
                "type": "done",
                "request_id": request.request_id,
                "answer": "must-not-leak",
            }
        )
        await queue.put(
            {
                "v": 1,
                "type": "worker_done",
                "request_id": request.request_id,
                "status": "stopped",
            }
        )

        assert [item async for item in execution.events(timeout_seconds=1)] == [
            WorkerTurnMilestone.CANCELLED
        ]
        assert control.resume_id == "new-sdk-session"
        assert execution.terminal is True
        assert execution.cancel_requested is True

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_cancel_requested_during_dispatch_wins_drain_failure_and_cleans_state():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()

        async def fail_after_cancel():
            running = transport.running_worker(request.turn_id)
            assert running is not None
            running.cancel_requested = True
            raise RuntimeError("control lost after cancellation")

        control = _control(
            claim.sandbox_id,
            _OneShotProcess(drain_action=fail_after_cancel),
        )
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )

        assert await execution.dispatch() is WorkerTurnDispatchOutcome.CANCELLED
        running = transport.running_worker(request.turn_id)
        assert running is not None
        assert running.cancel_requested is True
        assert running.done is not None and running.done.is_set()

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_persistent_dispatch_distinguishes_control_open_and_write_failures():
    async def open_failure():
        async def fail_open(_sandbox, _worker_generation):
            raise ConnectionError("private provider detail")

        transport = ChatSandboxWorkerTransport(
            SimpleNamespace(
                open_persistent_connection=fail_open,
                open_turn_process=None,
            )
        )
        request = _turn_request()
        claim = _turn_claim()
        execution = transport.create_execution(
            sandbox=SimpleNamespace(object_id=claim.sandbox_id),
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        with pytest.raises(SandboxError) as raised:
            await execution.dispatch()
        assert raised.value.failure_stage == "control_open"
        assert raised.value.failure_class == "ConnectionError"
        assert "private provider detail" not in str(raised.value)
        await execution.close()

    async def write_failure():
        async def fail_write():
            raise BrokenPipeError("private frame detail")

        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(
            claim.sandbox_id,
            _OneShotProcess(drain_action=fail_write),
        )
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        with pytest.raises(SandboxError) as raised:
            await execution.dispatch()
        assert raised.value.failure_stage == "dispatch_write"
        assert raised.value.failure_class == "BrokenPipeError"
        assert "private frame detail" not in str(raised.value)
        await execution.close()

    asyncio.run(open_failure())
    asyncio.run(write_failure())


def test_cancel_deferred_before_worker_registration_returns_cancelled_without_write():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        process = _OneShotProcess()
        control = _control(claim.sandbox_id, process)
        transport.register_session_control(request.chat_session_id, control)
        transport.defer_cancel(request.turn_id)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )

        assert await execution.dispatch() is WorkerTurnDispatchOutcome.CANCELLED
        running = transport.running_worker(request.turn_id)
        assert running is not None
        assert running.cancel_requested is True
        assert running.done is not None and running.done.is_set()
        assert process.stdin.writes == []

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_conflicting_sdk_resume_fails_and_cleans_exact_execution_state():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        control.resume_id = "sdk-session-a"
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        await control.queues[request.request_id].put(
            {
                "v": 1,
                "type": "_sdk_session",
                "request_id": request.request_id,
                "session_id": "sdk-session-b",
            }
        )

        with pytest.raises(ProtocolError, match="SDK session changed"):
            _ = [item async for item in execution.events(timeout_seconds=1)]
        assert control.resume_id == "sdk-session-a"

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_persistent_control_failure_maps_to_uncertain_sandbox_error_and_cleans():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        await control.queues[request.request_id].put(
            {
                "v": 1,
                "type": "_control_failure",
                "request_id": request.request_id,
                "stage": "broker_clear",
                "error_class": "ConnectionResetError",
            }
        )

        with pytest.raises(SandboxError) as raised:
            _ = [item async for item in execution.events(timeout_seconds=1)]
        assert raised.value.code == "sandbox_worker_failed"
        assert raised.value.uncertain is True
        assert raised.value.failure_stage == "broker_clear"
        assert raised.value.failure_class == "ConnectionResetError"

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_persistent_timeout_cleans_correlated_queue_and_worker_registration():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()

        with pytest.raises(TimeoutError):
            _ = [item async for item in execution.events(timeout_seconds=0.01)]

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_persistent_oversized_unterminated_stream_fails_and_cleans_execution():
    async def exercise():
        connection = _AsyncConnection()
        provider = _TurnProvider(connection=connection)
        transport = ChatSandboxWorkerTransport(provider)
        request = _turn_request()
        claim = _turn_claim()
        sandbox = SimpleNamespace(object_id=claim.sandbox_id)
        control = await transport.open_persistent_control(
            sandbox, claim.worker_generation
        )
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()

        await connection.incoming.put(b"x" * (MAX_WIRE_FRAME_BYTES + 1))
        with pytest.raises(ProtocolError, match="too large"):
            _ = [item async for item in execution.events(timeout_seconds=1)]

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None
        transport.drop_session_control(request.chat_session_id, expected=control)
        if control.reader_task is not None:
            await asyncio.gather(control.reader_task, return_exceptions=True)
        if transport.close_tasks:
            await asyncio.gather(*transport.close_tasks, return_exceptions=True)

    asyncio.run(exercise())


def test_one_shot_oversized_unterminated_stream_fails_and_cleans_execution():
    async def exercise():
        request = _turn_request()
        claim = _turn_claim()
        process = _OneShotProcess(chunks=[b"x" * (MAX_WIRE_FRAME_BYTES + 1)])
        transport = ChatSandboxWorkerTransport(_TurnProvider(process=process))
        execution = transport.create_execution(
            sandbox=SimpleNamespace(object_id=claim.sandbox_id),
            claim=claim,
            request=request,
            mode=WorkerTurnMode.ONE_SHOT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()

        with pytest.raises(ProtocolError, match="too large"):
            _ = [item async for item in execution.events(timeout_seconds=1)]

        await execution.close()
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_one_shot_wait_is_timed_and_terminal_state_survives_timeout():
    async def exercise():
        request = _turn_request()
        claim = _turn_claim()
        wait_forever = asyncio.Event()

        async def wait_action():
            await wait_forever.wait()

        process = _OneShotProcess(
            chunks=[
                encode_frame(
                    {
                        "v": 1,
                        "type": "done",
                        "request_id": request.request_id,
                    }
                )
                + encode_frame(
                    {
                        "v": 1,
                        "type": "worker_done",
                        "request_id": request.request_id,
                        "status": "complete",
                    }
                )
            ],
            wait_action=wait_action,
        )
        transport = ChatSandboxWorkerTransport(_TurnProvider(process=process))
        execution = transport.create_execution(
            sandbox=SimpleNamespace(object_id=claim.sandbox_id),
            claim=claim,
            request=request,
            mode=WorkerTurnMode.ONE_SHOT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        observed = []

        with pytest.raises(TimeoutError):
            async for item in execution.events(timeout_seconds=0.01):
                observed.append(item)

        assert observed == [{"type": "done"}]
        assert process.wait_calls == 1
        assert execution.terminal is True
        await execution.close()
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


def test_cancel_not_found_has_no_transport_side_effects():
    async def exercise():
        transport = _transport()
        turn_id = uuid.uuid4()

        outcome = await transport.cancel(turn_id, grace_seconds=0.01)

        assert outcome.status is WorkerCancelStatus.NOT_FOUND
        assert outcome.turn_id == turn_id
        assert outcome.request_id is None
        assert outcome.claim is None
        assert transport.running_worker(turn_id) is None

    asyncio.run(exercise())


def test_cancel_completed_uses_original_request_and_preserves_claim_identity():
    async def exercise():
        transport = _transport()
        turn_id = uuid.uuid4()
        claim = _turn_claim()
        process = _OneShotProcess()
        done = asyncio.Event()
        done.set()
        running = RunningWorker(
            process=process,
            request_id="original-request",
            claim=claim,
            done=done,
        )
        transport.register_running_worker(turn_id, running)

        outcome = await transport.cancel(turn_id, grace_seconds=1)

        assert outcome.status is WorkerCancelStatus.COMPLETED
        assert outcome.turn_id == turn_id
        assert outcome.request_id == "original-request"
        assert outcome.claim is claim
        assert running.cancel_requested is True
        assert decode_frame(process.stdin.writes[0]) == {
            "v": 1,
            "type": "cancel",
            "request_id": "original-request",
        }
        transport.remove_running_worker(turn_id, expected=running)

    asyncio.run(exercise())


def test_cancel_control_loss_requires_explicit_completion_signal():
    async def exercise():
        async def lose_control():
            raise RuntimeError("control closed")

        transport = _transport()
        turn_id = uuid.uuid4()
        claim = _turn_claim()
        process = _OneShotProcess(drain_action=lose_control)
        running = RunningWorker(
            process=process,
            request_id="request-control-lost",
            claim=claim,
            done=asyncio.Event(),
        )
        transport.register_running_worker(turn_id, running)

        outcome = await transport.cancel(turn_id, grace_seconds=1)

        assert outcome.status is WorkerCancelStatus.CONTROL_LOST
        assert outcome.claim is claim
        assert running.cancel_requested is True
        assert running.done is not None and not running.done.is_set()
        transport.complete_control_loss(outcome)
        assert running.done.is_set()
        transport.remove_running_worker(turn_id, expected=running)

    asyncio.run(exercise())


def test_cancel_timeout_is_distinct_from_control_loss():
    async def exercise():
        transport = _transport()
        turn_id = uuid.uuid4()
        claim = _turn_claim()
        running = RunningWorker(
            process=_OneShotProcess(),
            request_id="request-timeout",
            claim=claim,
            done=asyncio.Event(),
        )
        transport.register_running_worker(turn_id, running)

        outcome = await transport.cancel(turn_id, grace_seconds=0.01)

        assert outcome.status is WorkerCancelStatus.TIMED_OUT
        assert outcome.claim is claim
        assert running.cancel_requested is True
        assert running.done is not None and not running.done.is_set()
        transport.remove_running_worker(turn_id, expected=running)

    asyncio.run(exercise())


def test_accepted_cancel_wins_concurrent_stream_failure_and_cleans_execution():
    async def exercise():
        transport = _transport()
        request = _turn_request()
        claim = _turn_claim()
        control = _control(claim.sandbox_id, _OneShotProcess())
        transport.register_session_control(request.chat_session_id, control)
        execution = transport.create_execution(
            sandbox=control.sandbox,
            claim=claim,
            request=request,
            mode=WorkerTurnMode.PERSISTENT,
            process_timeout_seconds=47,
        )
        await execution.dispatch()
        cancel = asyncio.create_task(transport.cancel(request.turn_id, grace_seconds=1))
        await _wait_until(lambda: execution.cancel_requested)
        await control.queues[request.request_id].put(
            RuntimeError("worker exited during cancellation")
        )

        assert [item async for item in execution.events(timeout_seconds=1)] == [
            WorkerTurnMilestone.CANCELLED
        ]
        outcome = await cancel
        assert outcome.status is WorkerCancelStatus.COMPLETED

        await execution.close()
        assert request.request_id not in control.queues
        assert transport.running_worker(request.turn_id) is None

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("terminal", "expected_releases", "expected_termination"),
    [
        (True, 1, []),
        (False, 0, ["cancelled"]),
    ],
)
def test_turn_coordinator_cancelled_milestone_preserves_release_vs_terminate_contract(
    terminal,
    expected_releases,
    expected_termination,
):
    async def exercise():
        settings = Settings(
            _env_file=None,
            chat_workspace_snapshots_enabled=False,
            chat_persistent_worker_enabled=False,
            chat_sandbox_spend_enforcement_enabled=False,
            chat_agent_timeout_seconds=1,
            chat_gateway_url="https://gateway.example.test",
        )
        provider = _TurnProvider(process=_OneShotProcess())
        transport = ChatSandboxWorkerTransport(provider)
        sandbox = SimpleNamespace(object_id="sb-manager-cancel")

        async def acquire(*_args, **_kwargs):
            return SandboxCreated(
                sandbox=sandbox,
                elapsed_ms=0,
                after_pool_miss=False,
                pool_lookup_ms=None,
            )

        claim = WorkerClaim(sandbox.object_id, "claim-token")
        releases = 0
        terminations: list[str] = []

        def release_worker(*_args, **_kwargs):
            nonlocal releases
            releases += 1
            return True

        async def terminate_worker(_session_id, _claim, *, failure_code):
            terminations.append(failure_code)
            return True

        class Execution:
            sdk_dispatched = False
            cancel_requested = True

            def __init__(self):
                self.terminal = False
                self.closed = False

            async def dispatch(self):
                return WorkerTurnDispatchOutcome.DISPATCHED

            async def events(self, *, timeout_seconds):
                assert timeout_seconds == 1
                self.terminal = terminal
                yield WorkerTurnMilestone.CANCELLED

            async def close(self):
                self.closed = True

        execution = Execution()
        transport.create_execution = lambda *_args, **_kwargs: execution
        coordinator = build_turn_coordinator(
            settings,
            transport,
            acquire=acquire,
            claim_worker=lambda *_args, **_kwargs: claim,
            release_worker=release_worker,
            terminate_worker=terminate_worker,
        )

        events = [
            event
            async for event in coordinator.run(
                ChatSandboxTurnRequest(
                    chat_session_id=uuid.uuid4(),
                    turn_id=uuid.uuid4(),
                    request_id="manager-cancel",
                    prompt="prompt",
                    model="model",
                    resume=None,
                    capability_token="capability",
                )
            )
        ]

        assert events[-1] == {"type": "_cancelled"}
        assert execution.closed is True
        assert releases == expected_releases
        assert terminations == expected_termination

    asyncio.run(exercise())


def test_turn_coordinator_cancel_maps_timeout_and_not_found_to_typed_status():
    async def exercise():
        settings = Settings(
            _env_file=None,
            chat_workspace_snapshots_enabled=False,
            chat_cancel_grace_seconds=0.01,
        )
        transport = _transport()
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        claim = _turn_claim()
        running = RunningWorker(
            process=_OneShotProcess(),
            request_id="manager-timeout",
            claim=claim,
            done=asyncio.Event(),
        )
        transport.register_running_worker(turn_id, running)
        terminations: list[tuple[uuid.UUID, WorkerClaim, str]] = []

        async def terminate_worker(candidate_session, candidate_claim, *, failure_code):
            terminations.append((candidate_session, candidate_claim, failure_code))
            return True

        async def unexpected_acquire(*_args, **_kwargs):
            raise AssertionError("cancellation must not acquire a sandbox")

        coordinator = build_turn_coordinator(
            settings,
            transport,
            acquire=unexpected_acquire,
            terminate_worker=terminate_worker,
        )

        assert (
            await coordinator.cancel(session_id, turn_id)
            is WorkerCancelStatus.TIMED_OUT
        )
        assert terminations == [(session_id, claim, "cancel_timeout")]
        deferred_turn_id = uuid.uuid4()
        assert (
            await coordinator.cancel(session_id, deferred_turn_id)
            is WorkerCancelStatus.PENDING
        )
        deferred = RunningWorker(
            process=_OneShotProcess(),
            request_id="manager-deferred",
            claim=claim,
            done=asyncio.Event(),
        )
        transport.register_running_worker(deferred_turn_id, deferred)
        assert deferred.cancel_requested is True
        transport.remove_running_worker(deferred_turn_id, expected=deferred)

        transport.remove_running_worker(turn_id, expected=running)

    asyncio.run(exercise())


def test_turn_coordinator_defers_cancel_across_inflight_sandbox_acquisition():
    async def exercise():
        settings = Settings(
            _env_file=None,
            chat_workspace_snapshots_enabled=False,
            chat_persistent_worker_enabled=True,
            chat_sandbox_spend_enforcement_enabled=False,
            chat_agent_timeout_seconds=1,
            chat_gateway_url="https://gateway.example.test",
        )
        transport = _transport()
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        request = ChatSandboxTurnRequest(
            chat_session_id=session_id,
            turn_id=turn_id,
            request_id="acquisition-race",
            prompt="prompt",
            model="model",
            resume=None,
            capability_token="capability",
        )
        sandbox = SimpleNamespace(object_id="sb-acquisition-race")
        process = _OneShotProcess()
        registrations = []
        register_running_worker = transport.register_running_worker

        def register(turn, running):
            registrations.append((turn, turn in transport.deferred_cancellations))
            register_running_worker(turn, running)

        transport.register_running_worker = register
        acquisition_started = asyncio.Event()
        allow_acquisition = asyncio.Event()

        async def acquire(*_args, **_kwargs):
            acquisition_started.set()
            await allow_acquisition.wait()
            transport.register_session_control(
                session_id, _control(sandbox.object_id, process)
            )
            return SandboxCreated(
                sandbox=sandbox,
                elapsed_ms=1,
                after_pool_miss=False,
                pool_lookup_ms=None,
            )

        terminations = []

        async def terminate_worker(_session_id, _claim, *, failure_code):
            terminations.append(failure_code)
            return True

        coordinator = build_turn_coordinator(
            settings,
            transport,
            acquire=acquire,
            claim_worker=lambda *_args, **_kwargs: WorkerClaim(
                sandbox.object_id,
                "claim-token",
                assignment_token="assignment-token",
                worker_generation="generation-a",
            ),
            terminate_worker=terminate_worker,
        )
        events = []

        async def consume():
            async for event in coordinator.run(request):
                events.append(event)

        turn = asyncio.create_task(consume())
        await acquisition_started.wait()
        assert (
            await coordinator.cancel(session_id, turn_id) is WorkerCancelStatus.PENDING
        )
        assert turn_id in transport.deferred_cancellations
        allow_acquisition.set()
        await turn

        assert events[-1] == {"type": "_cancelled"}
        assert registrations == [(turn_id, True)]
        assert process.stdin.writes == []
        assert terminations == ["cancelled"]
        assert transport.running_worker(turn_id) is None

    asyncio.run(exercise())
