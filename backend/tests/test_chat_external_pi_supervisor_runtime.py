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
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim


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
    )

    result = asyncio.run(runtime.run())

    assert result.registrations == 1
    assert result.heartbeats == 1
    assert result.drained is True
    assert len(sessions) == 4
    assert all(session.commit.call_count == 1 for session in sessions)
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


def test_runtime_fails_closed_when_heartbeat_outage_consumes_the_lease():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15)
    supervisor.register = AsyncMock(return_value=claim)
    supervisor.heartbeat = AsyncMock(side_effect=ExternalPiWorkerUnavailable("offline"))
    supervisor.begin_drain = AsyncMock()

    @contextmanager
    def session_factory():
        yield Mock()

    runtime = ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime(2026, 8, 26, 12, tzinfo=UTC),
        monotonic=Mock(side_effect=(0, 0, 5, 10, 15)),
        wait_for_stop=AsyncMock(return_value=False),
        sleep=AsyncMock(),
        heartbeat_interval_seconds=5,
        startup_timeout_seconds=30,
        drain_poll_seconds=1,
    )

    with pytest.raises(ExternalPiSupervisorLeaseLost):
        asyncio.run(runtime.run())

    supervisor.register.assert_awaited_once()
    supervisor.begin_drain.assert_not_awaited()


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


def test_runtime_counts_slow_successful_heartbeats_against_the_durable_lease():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15)
    supervisor.register = AsyncMock(return_value=claim)
    clock = [0.0]

    async def heartbeat(*_args, **_kwargs):
        if supervisor.heartbeat.await_count == 1:
            clock[0] += 9
            return _status(generation=3)
        clock[0] += 2
        raise ExternalPiWorkerUnavailable("offline")

    supervisor.heartbeat = AsyncMock(side_effect=heartbeat)

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

    assert supervisor.heartbeat.await_count == 2


def test_runtime_does_not_start_a_heartbeat_at_the_lease_deadline():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    supervisor = Mock(lease_seconds=15)
    supervisor.register = AsyncMock(return_value=claim)
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
