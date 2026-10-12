import asyncio
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerStatus,
    ExternalPiWorkerUnavailable,
)
from backend.services.chat_external_pi_supervisor import ChatExternalPiSupervisor
from backend.services.chat_external_pi_supervisor import ExternalPiWorkerDrainIncomplete
from backend.services.chat_external_pi_supervisor_runtime_service import (
    ChatExternalPiSupervisorRuntime,
    ExternalPiSupervisorLeaseLost,
    ExternalPiSupervisorRunResult,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)


def _claim(generation=3):
    return ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        generation,
        "release-a",
        "external-pi-v1",
    )


def _status(*, state="ready", active=0, generation=None):
    return ExternalPiWorkerStatus(
        protocol="external-pi-v1",
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        state=state,
        active_sessions=active,
        maximum_sessions=8,
        worker_generation=generation,
        operation_counters={
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        capability_evidence={
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    )


def test_runtime_registers_heartbeats_and_gracefully_drains():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    client = Mock(
        status=AsyncMock(
            side_effect=[
                _status(),
                _status(active=1, generation=3),
                _status(state="draining", generation=3),
            ]
        ),
        bind_claim=AsyncMock(return_value=_status(generation=3)),
        begin_drain=AsyncMock(
            return_value=_status(state="draining", active=1, generation=3)
        ),
    )
    repository = Mock()
    repository.register.return_value = claim
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )
    sessions = []

    @contextmanager
    def session_factory():
        session = Mock()
        sessions.append(session)
        yield session

    waits = iter((False, True))

    async def wait_for_stop(_seconds):
        return next(waits)

    async def sleep(_seconds):
        return None

    times = iter(
        datetime(2026, 8, 26, 12, tzinfo=UTC) + timedelta(seconds=value)
        for value in range(10)
    )
    observe = Mock()
    release_connections = Mock()
    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: next(times),
        monotonic=Mock(side_effect=range(10)),
        wait_for_stop=wait_for_stop,
        sleep=sleep,
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
        observe=observe,
        release_connections=release_connections,
    )

    result = asyncio.run(runtime.run())

    assert result.registrations == 1
    assert result.heartbeats == 1
    assert result.drained is True
    assert len(sessions) == 4
    assert all(session.commit.call_count == 1 for session in sessions)
    assert release_connections.call_count == 4
    assert observe.call_args_list == [
        (("registered", claim, 0),),
        (("heartbeat", claim, 1),),
        (("drained", claim, 1),),
    ]


def test_runtime_recovers_from_a_transient_startup_failure():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(
        side_effect=[ExternalPiWorkerUnavailable("offline"), claim]
    )
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining"))
    supervisor.finish_drain = AsyncMock(return_value=None)
    sessions = []

    @contextmanager
    def session_factory():
        session = Mock()
        sessions.append(session)
        yield session

    waits = iter((False, True))

    async def wait_for_stop(_seconds):
        return next(waits)

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=Mock(side_effect=range(10)),
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    result = asyncio.run(runtime.run())

    assert result.registrations == 1
    assert supervisor.register.await_count == 2
    assert sessions[0].commit.call_count == 0


def test_successful_slow_registration_starts_a_fresh_lease_window():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    clock = [0.0]

    async def register(*_args, **_kwargs):
        clock[0] += 25
        return claim

    supervisor.register = AsyncMock(side_effect=register)
    supervisor.heartbeat = AsyncMock(return_value=_status(generation=3))
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining"))
    supervisor.finish_drain = AsyncMock(return_value=None)

    @contextmanager
    def session_factory():
        yield Mock()

    waits = iter((False, True))

    async def wait_for_stop(seconds):
        clock[0] += seconds
        return next(waits)

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    result = asyncio.run(runtime.run())

    assert result.heartbeats == 1
    supervisor.heartbeat.assert_awaited_once()


def test_runtime_reregisters_when_a_heartbeat_outage_consumes_the_lease():
    claim = _claim(3)
    renewed = _claim(4)
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(side_effect=[claim, renewed])
    supervisor.heartbeat = AsyncMock(side_effect=ExternalPiWorkerUnavailable("offline"))
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining"))
    supervisor.finish_drain = AsyncMock(return_value=None)
    clock = [0.0]

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        clock[0] += seconds
        return supervisor.register.await_count == 2

    observe = Mock()
    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
        observe=observe,
    )

    result = asyncio.run(runtime.run())

    assert result == ExternalPiSupervisorRunResult(
        registrations=2, heartbeats=0, drained=True
    )
    # Two failed heartbeats consumed the 15 s lease and the third would have
    # started at the deadline, so the loop gave up on the first claim and took
    # a new one instead of exiting.
    assert supervisor.heartbeat.await_count == 2
    assert observe.call_args_list == [
        (("registered", claim, 0),),
        (("lease_lost", claim, 0),),
        (("registered", renewed, 0),),
        (("drained", renewed, 0),),
    ]
    assert supervisor.begin_drain.await_args.kwargs["claim"] is renewed


def test_runtime_polls_an_incomplete_drain_until_the_worker_is_idle():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(return_value=claim)
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining", active=1))
    supervisor.finish_drain = AsyncMock(
        side_effect=[ExternalPiWorkerDrainIncomplete("busy"), None]
    )

    @contextmanager
    def session_factory():
        yield Mock()

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=Mock(side_effect=range(10)),
        wait_for_stop=AsyncMock(return_value=True),
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    result = asyncio.run(runtime.run())

    assert result.drained is True
    assert supervisor.finish_drain.await_count == 2
    runtime.sleep.assert_awaited_once_with(1)


def test_runtime_retries_an_idempotent_drain_request_after_transport_failure():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(return_value=claim)
    supervisor.begin_drain = AsyncMock(
        side_effect=[
            ExternalPiWorkerUnavailable("response lost"),
            _status(state="draining"),
        ]
    )
    supervisor.finish_drain = AsyncMock(return_value=None)

    @contextmanager
    def session_factory():
        yield Mock()

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=Mock(side_effect=range(10)),
        wait_for_stop=AsyncMock(return_value=True),
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    result = asyncio.run(runtime.run())

    assert result.drained is True
    assert supervisor.begin_drain.await_count == 2
    runtime.sleep.assert_awaited_once_with(1)


def test_runtime_fails_closed_when_reregistration_outlives_the_startup_window():
    claim = _claim(3)
    supervisor = Mock(lease_seconds=15)
    clock = [0.0]

    async def register(*_args, **_kwargs):
        if supervisor.register.await_count == 1:
            return claim
        raise ExternalPiWorkerUnavailable("offline")

    async def heartbeat(*_args, **_kwargs):
        if supervisor.heartbeat.await_count == 1:
            clock[0] += 9
            return _status(generation=3)
        clock[0] += 2
        raise ExternalPiWorkerUnavailable("offline")

    supervisor.register = AsyncMock(side_effect=register)
    supervisor.heartbeat = AsyncMock(side_effect=heartbeat)
    supervisor.begin_drain = AsyncMock()

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        clock[0] += seconds
        return False

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    with pytest.raises(ExternalPiSupervisorLeaseLost):
        asyncio.run(runtime.run())

    # A slow successful heartbeat still counts against the durable lease: the
    # second one finished 16 s after the first started, so the claim was lost.
    assert supervisor.heartbeat.await_count == 2
    # Re-registration then retried for the whole startup window before the
    # runtime failed closed.
    assert supervisor.register.await_count > 2
    assert clock[0] >= 21 + 30
    supervisor.begin_drain.assert_not_awaited()


def test_runtime_does_not_start_a_heartbeat_at_the_lease_deadline():
    claim = _claim(3)
    supervisor = Mock(lease_seconds=15)

    async def register(*_args, **_kwargs):
        if supervisor.register.await_count == 1:
            return claim
        raise ExternalPiWorkerUnavailable("offline")

    supervisor.register = AsyncMock(side_effect=register)
    supervisor.heartbeat = AsyncMock()
    clock = [0.0]

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        clock[0] += seconds
        return False

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=20,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    with pytest.raises(ExternalPiSupervisorLeaseLost):
        asyncio.run(runtime.run())

    supervisor.heartbeat.assert_not_awaited()


def test_runtime_reregisters_in_process_after_a_stall_outlives_the_lease():
    claim = _claim(3)
    renewed = _claim(4)
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(side_effect=[claim, renewed])
    supervisor.heartbeat = AsyncMock()
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining"))
    supervisor.finish_drain = AsyncMock(return_value=None)
    clock = [0.0]
    waits = [0]

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        waits[0] += 1
        if waits[0] == 1:
            # A starved host parks the event loop for far longer than the lease.
            clock[0] += 40
            return False
        clock[0] += seconds
        return True

    observe = Mock()
    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
        observe=observe,
    )

    result = asyncio.run(runtime.run())

    assert result == ExternalPiSupervisorRunResult(
        registrations=2, heartbeats=0, drained=True
    )
    # The expired claim is never heartbeated; the runtime goes straight back
    # through fenced registration and drains under the new claim.
    supervisor.heartbeat.assert_not_awaited()
    assert observe.call_args_list == [
        (("registered", claim, 0),),
        (("lease_lost", claim, 0),),
        (("registered", renewed, 0),),
        (("drained", renewed, 0),),
    ]
    assert supervisor.begin_drain.await_args.kwargs["claim"] is renewed
    assert supervisor.finish_drain.await_args.kwargs["claim"] is renewed


def test_runtime_reregisters_immediately_when_the_registry_fences_its_claim():
    claim = _claim(3)
    renewed = _claim(4)
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(
        side_effect=[
            claim,
            WorkerLeaseUnavailable("External worker lease is still active"),
            renewed,
        ]
    )
    supervisor.heartbeat = AsyncMock(
        side_effect=StaleWorkerClaim("External worker claim was fenced")
    )
    supervisor.begin_drain = AsyncMock(return_value=_status(state="draining"))
    supervisor.finish_drain = AsyncMock(return_value=None)
    clock = [0.0]

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        clock[0] += seconds
        return supervisor.register.await_count == 3

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    result = asyncio.run(runtime.run())

    assert result.registrations == 2
    assert result.drained is True
    # One fenced heartbeat is enough; the runtime does not wait out the lease.
    assert supervisor.heartbeat.await_count == 1
    # A registry that still shows the previous lease as live is retried inside
    # the startup window rather than treated as fatal.
    assert supervisor.register.await_count == 3
    assert clock[0] == 5 + 5 + 5


def test_runtime_reports_an_undrained_stop_that_interrupts_reregistration():
    claim = _claim(3)
    supervisor = Mock(lease_seconds=15, drain_seconds=60)
    supervisor.register = AsyncMock(
        side_effect=[claim, ExternalPiWorkerUnavailable("offline")]
    )
    supervisor.heartbeat = AsyncMock(side_effect=StaleWorkerClaim("fenced"))
    supervisor.begin_drain = AsyncMock()
    clock = [0.0]

    @contextmanager
    def session_factory():
        yield Mock()

    async def wait_for_stop(seconds):
        clock[0] += seconds
        # The stop lands while the replacement claim is still being retried.
        return supervisor.register.await_count == 2

    observe = Mock()
    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=lambda: clock[0],
        wait_for_stop=wait_for_stop,
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
        observe=observe,
    )

    result = asyncio.run(runtime.run())

    # The caller can tell this apart from a stop before any claim existed:
    # a claim was taken, nothing drained it, and the last event was the loss.
    assert result == ExternalPiSupervisorRunResult(
        registrations=1, heartbeats=0, drained=False
    )
    assert observe.call_args_list[-1] == (("lease_lost", claim, 0),)
    supervisor.begin_drain.assert_not_awaited()
