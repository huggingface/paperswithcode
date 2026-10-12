"""Worker buffers, socket fences, and reserved-endpoint admission."""

import asyncio
from datetime import UTC, datetime, timedelta
import json
import threading
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    MAX_EXTERNAL_TURN_FRAME_BYTES,
    ExternalPiChatTurnRunner,
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
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeSocket,
    FakeWorkerRepository,
    FakeWorkspaceManager,
    SessionContext,
    SocketContext,
    _async_value,
    _collect,
    _tool_runner,
    worker_status,
)


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
