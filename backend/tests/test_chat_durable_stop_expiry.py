from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.routers import chat as chat_router
from backend.services import chat_session_service as chat_session_module
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_worker_transport import WorkerCancelStatus
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
)
from backend.services.chat_turn_cancellation_coordinator import (
    ChatTurnCancellationCoordinator,
)
from backend.services.chat_turn_cancel_control import CancelControlResult
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ExpiryProjectionMismatch,
    StaleTurnClaim,
    TurnLeaseClaim,
)


def _enabled_settings():
    return get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )


def test_session_service_has_no_immediate_terminal_journal_cleanup_bypass():
    assert not hasattr(ChatSessionService, "cleanup_terminal_journal")


async def _cancel_with(db, manager, sessions, session_id):
    coordinator = ChatTurnCancellationCoordinator(db, _enabled_settings(), manager)
    coordinator.sessions = sessions
    await coordinator.cancel(ChatOwner("owner-1", "owner"), session_id)


@pytest.mark.parametrize("subscriber_connected", [True, False])
def test_external_stop_is_independent_of_subscriber_and_waits_for_terminal_proof(
    subscriber_connected,
):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "backend-a", 7, 3)
    ordering: list[str] = []

    class DB:
        def commit(self):
            ordering.append("commit")

    class Service:
        def request_cancel(self, *_args):
            ordering.append("cancelling")
            return SimpleNamespace(session_id=session_id, turn_id=turn_id, claim=claim)

    async def cancel_external(request):
        assert request.claim == claim
        assert subscriber_connected in {True, False}
        ordering.append("external-and-executor-cancel")
        return CancelControlResult.REQUESTED

    class Manager:
        async def cancel_status(self, *_args):
            pytest.fail("external cancellation must not use the legacy sandbox path")

    coordinator = ChatTurnCancellationCoordinator(
        DB(),
        _enabled_settings(),
        Manager(),
        external_cancel=cancel_external,
        observe=lambda event, code, value: ordering.append(
            f"observe:{event}:{code}:{value}"
        ),
    )
    coordinator.sessions = Service()

    asyncio.run(coordinator.cancel(ChatOwner("owner-1", "owner"), session_id))

    assert ordering == [
        "cancelling",
        "commit",
        "observe:turn_state:cancelling:1",
        "external-and-executor-cancel",
    ]


def test_missing_process_local_external_control_interrupts_with_exact_code():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "dead-backend", 9, 5)
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

    class Service:
        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id, claim=claim)

        def interrupt_cancel_without_control(self, _owner, request):
            assert request.claim == claim
            calls.append("cancel-control-missing")

    async def missing(_request):
        calls.append("control-missing")
        return CancelControlResult.MISSING

    class Manager:
        async def cancel_status(self, *_args):
            pytest.fail("must not start or search for replacement model control")

    coordinator = ChatTurnCancellationCoordinator(
        DB(), _enabled_settings(), Manager(), external_cancel=missing
    )
    coordinator.sessions = Service()

    asyncio.run(coordinator.cancel(ChatOwner("owner-1", "owner"), session_id))

    assert calls == [
        "commit",
        "control-missing",
        "cancel-control-missing",
        "commit",
    ]


def test_external_cancel_transport_loss_interrupts_without_claiming_cancelled():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "backend-a", 7, 3)
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

    class Service:
        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id, claim=claim)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("cancel-control-missing")

    async def transport_lost(_request):
        calls.append("external-cancel")
        raise OSError("socket lost")

    coordinator = ChatTurnCancellationCoordinator(
        DB(), _enabled_settings(), object(), external_cancel=transport_lost
    )
    coordinator.sessions = Service()

    asyncio.run(coordinator.cancel(ChatOwner("owner-1", "owner"), session_id))

    assert calls == [
        "commit",
        "external-cancel",
        "cancel-control-missing",
        "commit",
    ]


def test_external_cancel_before_runner_attach_fences_future_model_start():
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "backend-a", 7, 3)
    orchestrator = object.__new__(ChatStreamOrchestrator)
    orchestrator.admission = SimpleNamespace(durable_claim=claim)
    orchestrator.runner = None
    orchestrator._detached_cancel_requested = False

    found = asyncio.run(orchestrator.cancel_detached_turn(claim))

    assert found is CancelControlResult.REQUESTED
    assert orchestrator._detached_cancel_requested is True


@pytest.mark.parametrize(
    "status", [WorkerCancelStatus.COMPLETED, WorkerCancelStatus.PENDING]
)
def test_enabled_stop_accepts_delivered_or_deferred_manager_signal(monkeypatch, status):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    ordering: list[str] = []

    class DB:
        def commit(self):
            ordering.append("commit")

        def rollback(self):
            ordering.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            ordering.append("cancelling")
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

    class Manager:
        async def cancel_status(self, requested_session_id, requested_turn_id):
            assert (requested_session_id, requested_turn_id) == (session_id, turn_id)
            ordering.append("signal")
            return status

    db = DB()
    asyncio.run(_cancel_with(db, Manager(), Service(db, None), session_id))
    assert ordering == ["cancelling", "commit", "signal"]


def test_enabled_missing_cancel_control_terminalizes_projection(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, owner, request):
            assert owner.hf_user_id == "owner-1"
            assert request.turn_id == turn_id
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append("cancel")
            return WorkerCancelStatus.NOT_FOUND

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")

    db = DB()
    asyncio.run(_cancel_with(db, Manager(), Service(db, None), session_id))

    assert calls == [
        "commit",
        "cancel",
        "terminate",
        "interrupted",
        "commit",
    ]


def test_enabled_failed_termination_still_terminalizes_projection(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append("cancel")
            return WorkerCancelStatus.CONTROL_LOST

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")
            raise SandboxError("termination_failed", "termination failed")

    db = DB()
    asyncio.run(_cancel_with(db, Manager(), Service(db, None), session_id))
    assert calls == [
        "commit",
        "cancel",
        "terminate",
        "interrupted",
        "commit",
    ]


@pytest.mark.parametrize(
    "status", [WorkerCancelStatus.CONTROL_LOST, WorkerCancelStatus.TIMED_OUT]
)
def test_enabled_uncertain_cancel_status_terminalizes_once(monkeypatch, status):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append(status.value)
            return status

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")

    db = DB()
    asyncio.run(_cancel_with(db, Manager(), Service(db, None), session_id))
    assert calls == ["commit", status.value, "terminate", "interrupted", "commit"]


def test_enabled_cancel_exception_terminates_and_terminalizes_once(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append("cancel")
            raise SandboxError("cancel_failed", "cancel failed")

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")

    db = DB()
    asyncio.run(_cancel_with(db, Manager(), Service(db, None), session_id))
    assert calls == ["commit", "cancel", "terminate", "interrupted", "commit"]


def test_unexpected_cancel_error_propagates_without_terminal_mislabel():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

    class Service:
        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append("cancel")
            raise RuntimeError("programming error")

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")

    db = DB()
    with pytest.raises(RuntimeError, match="programming error"):
        asyncio.run(_cancel_with(db, Manager(), Service(), session_id))
    assert calls == ["commit", "cancel"]


def test_unexpected_termination_error_propagates_without_terminal_mislabel():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

    class Service:
        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel_status(self, *_args):
            calls.append("cancel")
            return WorkerCancelStatus.NOT_FOUND

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")
            raise RuntimeError("programming error")

    db = DB()
    with pytest.raises(RuntimeError, match="programming error"):
        asyncio.run(_cancel_with(db, Manager(), Service(), session_id))
    assert calls == ["commit", "cancel", "terminate"]


def test_enabled_cancel_route_delegates_to_coordinator_and_preserves_204(monkeypatch):
    session_id = uuid.uuid4()
    calls = []

    class Coordinator:
        def __init__(self, db, settings, manager, **_kwargs):
            calls.append((db, settings, manager))

        async def cancel(self, owner, requested_session_id):
            calls.append((owner.hf_user_id, requested_session_id))

    manager = object()
    db = SimpleNamespace()
    settings = _enabled_settings()
    monkeypatch.setattr(chat_router, "ChatTurnCancellationCoordinator", Coordinator)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: manager)

    response = asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=db,
            settings=settings,
        )
    )

    assert response.status_code == 204
    assert calls == [(db, settings, manager), ("owner-1", session_id)]


def test_admission_reconciles_globally_expired_claim_before_capacity_count():
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="other-owner",
        state="running",
    )
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="other-owner",
        active_turn_id=turn_id,
        active_turn_expires_at=now + timedelta(seconds=180),
    )
    message = SimpleNamespace(status="generating", error_code=None)
    ordering: list[str] = []

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class DB:
        def __init__(self):
            self.results = iter((Result(session), Result(message)))

        def execute(self, _query):
            return next(self.results)

    class Repository:
        def lock_user_admission_authority(self, _db, *, hf_user_id):
            assert hf_user_id == "new-owner"
            ordering.append("locks")

        def load_expired_claims(self, _db, *, now, hf_user_id, limit):
            assert hf_user_id == "new-owner"
            assert limit == _enabled_settings().chat_max_concurrency
            ordering.append("expired")
            return (job,)

        def load_by_turn(self, _db, requested_turn_id, *, lock):
            assert requested_turn_id == job.turn_id
            assert lock is True
            return job

        def is_expired_claim(self, loaded_job, *, now):
            assert loaded_job is job
            return True

        def interrupt_exact_expired(self, _db, *, turn_id, now):
            assert turn_id == job.turn_id
            job.state = "interrupted"
            ordering.append("interrupted")

        def preflight_admission(self, _db, **kwargs):
            assert kwargs["authority_locked"] is True
            assert job.state == "interrupted"
            assert session.active_turn_id is None
            assert message.status == "interrupted"
            ordering.append("count")
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

    coordinator = ChatTurnAdmissionCoordinator(
        DB(), _enabled_settings(), repository=Repository()
    )

    preflight = coordinator.preflight(
        hf_user_id="new-owner",
        request_id="new-request",
        requested_session_id=None,
    )

    assert ordering == ["locks", "expired", "interrupted", "count"]
    assert preflight.reconciled_expired_count == 1
    assert session.active_turn_expires_at is None
    assert message.error_code == "lease_expired"


def test_expired_claim_projection_mismatch_fails_before_mutation():
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="running",
    )
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=uuid.uuid4(),
        active_turn_expires_at=now + timedelta(seconds=180),
    )
    message = SimpleNamespace(status="generating", error_code=None)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class DB:
        def __init__(self):
            self.results = iter((Result(session), Result(message)))

        def execute(self, _query):
            return next(self.results)

    class Repository:
        def load_expired_claims(self, *_args, **_kwargs):
            return (job,)

        def load_by_turn(self, _db, requested_turn_id, *, lock):
            assert requested_turn_id == job.turn_id
            assert lock is True
            return job

        def is_expired_claim(self, loaded_job, *, now):
            assert loaded_job is job
            return True

        def interrupt_exact_expired(self, *_args, **_kwargs):
            pytest.fail("durable terminal mutated before projection validation")

    coordinator = ChatTurnAdmissionCoordinator(
        DB(), _enabled_settings(), repository=Repository()
    )

    with pytest.raises(ExpiryProjectionMismatch):
        coordinator._reconcile_expired_claims(hf_user_id="owner-1", now=now)

    assert job.state == "running"
    assert message.status == "generating"
    assert session.active_turn_id != turn_id


def test_false_mode_cancel_uses_legacy_fence_without_durable_method(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def request_legacy_cancel(self, *_args):
            return turn_id

        def request_cancel(self, *_args):
            pytest.fail("durable Stop queried while switch is false")

    class Manager:
        async def cancel(self, *_args):
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: Manager())

    class DB:
        def commit(self):
            return None

        def rollback(self):
            return None

    asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=get_settings().model_copy(
                update={"chat_durable_turn_dispatch_enabled": False}
            ),
        )
    )


def test_request_cancel_uses_exact_persisted_claim(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "other-process", 19, 4)
    session = SimpleNamespace(id=session_id, active_turn_id=turn_id)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="running",
    )
    seen: list[TurnLeaseClaim] = []

    class Repository:
        def load_by_turn(self, _db, requested_turn_id, *, lock=False):
            assert requested_turn_id == turn_id
            assert lock is True
            return job

        def request_cancelling(self, _db, **kwargs):
            assert kwargs["turn_id"] == turn_id
            assert kwargs["worker_id"].startswith("local-runner:")
            seen.append(claim)
            job.state = "cancelling"
            return claim

    service = ChatSessionService(SimpleNamespace(), settings)
    service._owned = lambda *_args, **kwargs: session
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    request = service.request_cancel(ChatOwner("owner-1", "owner"), session_id)

    assert request.turn_id == turn_id
    assert seen == [claim]


def test_active_expiry_reconciles_durable_before_legacy_projection(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    ordering: list[str] = []
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="admitted",
    )

    class Repository:
        def load_by_turn(self, _db, requested_turn_id, *, lock=False):
            assert requested_turn_id == turn_id
            assert lock
            return job

        def interrupt_exact_expired(self, _db, **kwargs):
            ordering.append("durable")
            assert kwargs["turn_id"] == turn_id
            assert kwargs["admitted_worker_id"].startswith("local-runner:")
            job.state = "interrupted"
            return job

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    assert service._apply_expired_active_turn(session, message) is True

    ordering.append("legacy" if session.active_turn_id is None else "not-cleared")
    assert ordering == ["durable", "legacy"]
    assert message.status == "interrupted"
    assert message.error_code == "lease_expired"


def test_live_durable_claim_fails_closed_before_legacy_expiry(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    expiry = object()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=expiry,
    )
    message = SimpleNamespace(status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="running",
    )

    class Repository:
        def load_by_turn(self, *_args, **_kwargs):
            return job

        def interrupt_exact_expired(self, *_args, **_kwargs):
            raise StaleTurnClaim("still live")

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    with pytest.raises(ChatServiceError) as exc_info:
        service._apply_expired_active_turn(session, message)

    assert exc_info.value.code == "durable_control_conflict"
    assert session.active_turn_id == turn_id
    assert session.active_turn_expires_at is expiry
    assert message.status == "generating"
    assert message.error_code is None


def test_replay_expiry_reconciles_exact_durable_job(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[uuid.UUID] = []
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(turn_id=turn_id, status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="leased",
    )

    class Repository:
        def load_by_turn(self, *_args, **_kwargs):
            return job

        def interrupt_exact_expired(self, _db, **kwargs):
            calls.append(kwargs["turn_id"])
            return job

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    service._apply_expired_replay(session, message)

    assert calls == [turn_id]
    assert session.active_turn_id is None
    assert message.status == "interrupted"


def test_false_mode_expiry_never_constructs_durable_repository(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    turn_id = uuid.uuid4()
    session = SimpleNamespace(
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(status="generating", error_code=None)
    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(
        service,
        "_turn_job_repository",
        lambda: pytest.fail("durable expiry queried while switch is false"),
    )

    assert service._apply_expired_active_turn(session, message) is True
    assert session.active_turn_id is None
    assert message.status == "interrupted"


def test_account_busy_preflight_reconciles_expired_projection_then_retries(
    monkeypatch,
):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        selected_model=next(iter(settings.chat_model_routes)),
        reasoning_effort="low",
        transcript_status="ready",
        primary_paper_id=None,
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    stale = SimpleNamespace(turn_id=turn_id, status="generating", error_code=None)
    calls: list[str] = []

    class Coordinator:
        def __init__(self, *_args):
            self.calls = 0

        def preflight(self, **_kwargs):
            self.calls += 1
            calls.append(f"preflight-{self.calls}")
            if self.calls == 1:
                raise AccountBusy("existing expired turn")
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def authorize_global_capacity(self, preflight, **_kwargs):
            return preflight

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", Coordinator
    )
    service = ChatSessionService(SimpleNamespace(), settings)
    service._owned = lambda *_args, **_kwargs: session

    def load_stale(_session, _now):
        return stale if session.active_turn_id else None

    def apply_expired(_session, _stale):
        if _session.active_turn_id is None:
            return False
        calls.append("reconcile")
        _session.active_turn_id = None
        _session.active_turn_expires_at = None
        return True

    monkeypatch.setattr(service, "_load_expired_active_message", load_stale)
    monkeypatch.setattr(service, "_apply_expired_active_turn", apply_expired)
    monkeypatch.setattr(
        service,
        "_resolve_replay",
        lambda *_args, **_kwargs: SimpleNamespace(kind="continue"),
    )
    monkeypatch.setattr(service, "_has_unresolved_turn", lambda _session: True)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session_id,
            client_message_id="new-request",
            text="retry after expiry",
        )

    assert exc_info.value.code == "turn_requires_retry"
    assert exc_info.value.commit_changes is True
    assert calls == ["preflight-1", "reconcile", "preflight-2"]
