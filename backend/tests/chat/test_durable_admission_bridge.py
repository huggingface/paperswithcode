from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from backend.config import get_settings
from backend.models.database import ChatMessageRecord
from backend.services import chat_session_service as chat_session_module
from backend.services.chat_external_worker_capacity import (
    ExternalWorkerEndpoint,
    ExternalWorkerReservation,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    _bound_external_worker_reservation,
)
from backend.services.chat_durable_qualification_evidence import QualificationContext
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
)
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    IdempotencyMismatch,
)
from backend.tests.chat.admission_harness import (
    _Result,
    _ScriptedDB,
    _session,
)
from backend.tests.chat.transactional_admission_harness import (
    _TransactionalScriptedDB,
)


def test_qualification_capacity_is_scoped_to_one_durable_preflight():
    settings = get_settings().model_copy(update={"chat_max_concurrency": 2})
    capacities = []

    class Repository:
        def lock_user_admission_authority(self, *_args, **_kwargs):
            return None

        def load_expired_claims(self, *_args, **_kwargs):
            return []

        def preflight_admission(self, _db, **kwargs):
            capacities.append(kwargs["emergency_capacity"])
            return SimpleNamespace(existing_job=None)

    coordinator = ChatTurnAdmissionCoordinator(
        SimpleNamespace(), settings, repository=Repository()
    )

    coordinator.preflight(
        hf_user_id="qualification-owner",
        request_id="qualified",
        requested_session_id=None,
        qualification=QualificationContext(
            scope_id=uuid.uuid4(),
            run_id="qualified-f32",
            profile="32-functional-turns",
            workload="no_tool",
            app_release_id=settings.release_id,
            window_started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )
    coordinator.preflight(
        hf_user_id="ordinary-owner",
        request_id="ordinary",
        requested_session_id=None,
    )

    assert capacities == [32, 2]


def test_bound_external_reservation_carries_the_admitted_turn():
    endpoint = ExternalWorkerEndpoint(
        endpoint_id="green",
        worker_id="external-pi-green",
        base_url="http://127.0.0.1:18102",
        token="g" * 32,
    )
    reservation = ExternalWorkerReservation(
        request_id="client-message-1",
        turn_id=None,
        endpoint=endpoint,
        worker_claim=ExternalWorkerClaim(
            endpoint.worker_id,
            uuid.uuid4(),
            7,
            "release-a",
            "external-pi-v1",
        ),
        maximum_sessions=2,
    )
    preflight = SimpleNamespace(external_reservation=reservation)
    turn_id = uuid.uuid4()

    bound = _bound_external_worker_reservation(preflight, turn_id)

    assert bound is not None
    assert bound.turn_id == turn_id
    assert bound.request_id == reservation.request_id
    assert bound.endpoint == reservation.endpoint
    assert bound.worker_claim == reservation.worker_claim


def test_enabled_completed_replay_validates_durable_revision_before_return(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)
    turn_id = uuid.uuid4()
    durable_job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session.id,
        hf_user_id="owner-1",
        request_id="stable-request",
        revision=2,
    )

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(
                request_id="stable-request",
                requested_session_id=session.id,
                reconciled_expired_count=0,
                existing_job=durable_job,
            )

        def validate_replay(self, _preflight, **identity):
            if identity["revision"] != durable_job.revision:
                raise IdempotencyMismatch("revision differs")

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    user_message = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        status="complete",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=1,
        web_search_enabled=False,
    )
    db = _ScriptedDB(
        execute_results=(
            _Result(one=user_message),
            _Result(one=SimpleNamespace(content="persisted", followups=[])),
        )
    )
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="stable-request",
            text="retry",
        )

    assert exc_info.value.code == "idempotency_conflict"
    assert db.added == []
    assert db.flush_calls == 0


@pytest.mark.parametrize(
    ("repository_error", "expected_code"),
    [(AccountBusy("busy"), "account_busy"), (ChatOverload("full"), "chat_overload")],
)
def test_enabled_capacity_rejection_precedes_session_and_message_writes(
    monkeypatch, repository_error, expected_code
):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    db = _ScriptedDB()

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            raise repository_error

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: pytest.fail(
        "session loaded before preflight"
    )
    service.create_session = lambda *_args, **_kwargs: pytest.fail(
        "session created before preflight"
    )

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=None,
            client_message_id="rejected-request",
            text="must not persist",
        )

    assert exc_info.value.code == expected_code
    assert db.added == []
    assert db.flush_calls == 0


def test_external_worker_capacity_refusal_precedes_all_chat_projection_writes(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": True,
            "chat_default_agent_harness": "pi",
        }
    )
    db = _ScriptedDB()

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def reserve_external_capacity(self, *_args, **_kwargs):
            raise ChatOverload("external fleet full")

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(db, settings)
    service.create_session = lambda *_args, **_kwargs: pytest.fail(
        "session created before external capacity reservation"
    )
    service._apply_turn_creation = lambda *_args, **_kwargs: pytest.fail(
        "message created before external capacity reservation"
    )

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=None,
            client_message_id="rejected-request",
            text="must not persist",
        )

    assert exc_info.value.code == "chat_overload"
    assert db.added == []
    assert db.flush_calls == 0


def _qualification(settings, *, workload="no_tool"):
    return QualificationContext(
        scope_id=uuid.uuid4(),
        run_id="qualified-f32",
        profile="32-functional-turns",
        workload=workload,
        app_release_id=settings.release_id,
        window_started_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_qualified_new_turn_forces_pi_and_external_reservation_when_global_off(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": False,
            "chat_default_agent_harness": "claude",
        }
    )
    qualification = _qualification(settings)
    calls = []

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **kwargs):
            calls.append(("preflight", kwargs["qualification"]))
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def reserve_external_capacity(self, preflight, **_kwargs):
            calls.append(("reserve", None))
            return preflight

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(_ScriptedDB(), settings)

    def fail_after_creation_contract(*_args, **kwargs):
        calls.append(("create", kwargs.get("agent_harness_override")))
        raise RuntimeError("stop after observing creation contract")

    service.create_session = fail_after_creation_contract

    with pytest.raises(RuntimeError, match="creation contract"):
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=None,
            client_message_id="qualified-request",
            text="qualified",
            qualification=qualification,
        )

    assert calls == [
        ("preflight", qualification),
        ("reserve", None),
        ("create", "pi"),
    ]


def test_ordinary_new_turn_does_not_reserve_external_capacity_when_global_off(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": False,
            "chat_default_agent_harness": "claude",
        }
    )
    calls = []

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **kwargs):
            calls.append(("preflight", kwargs["qualification"]))
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def reserve_external_capacity(self, *_args, **_kwargs):
            pytest.fail("ordinary turn reserved external capacity")

        def authorize_global_capacity(self, preflight, **_kwargs):
            return preflight

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(_ScriptedDB(), settings)

    def fail_after_creation_contract(*_args, **kwargs):
        calls.append(("create", kwargs.get("agent_harness_override")))
        raise RuntimeError("stop after observing creation contract")

    service.create_session = fail_after_creation_contract

    with pytest.raises(RuntimeError, match="creation contract"):
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=None,
            client_message_id="ordinary-request",
            text="ordinary",
        )

    assert calls == [("preflight", None), ("create", None)]


def test_external_authoring_is_rejected_before_reservation_or_session_creation(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": True,
            "chat_default_agent_harness": "pi",
            "chat_artifacts_enabled": True,
            "chat_posterly_enabled": True,
        }
    )
    calls = []

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            calls.append("preflight")
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def reserve_external_capacity(self, *_args, **_kwargs):
            pytest.fail("unsupported mode reserved external capacity")

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(_ScriptedDB(), settings)
    service.create_session = lambda *_args, **_kwargs: pytest.fail(
        "unsupported mode created a session"
    )

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=None,
            client_message_id="poster-request",
            text="make a poster",
        )

    assert exc_info.value.code == "unsupported_chat_mode"
    assert calls == ["preflight"]


def test_qualified_existing_non_pi_session_is_rejected_before_replay(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)
    session.agent_harness = "claude"

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def authorize_global_capacity(self, preflight, **_kwargs):
            return preflight

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    service = ChatSessionService(_ScriptedDB(), settings)
    service._owned = lambda *_args, **_kwargs: session

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="qualified-request",
            text="qualified",
            qualification=_qualification(settings),
        )

    assert exc_info.value.code == "qualification_session_harness_mismatch"


def test_enabled_request_without_session_recovers_exact_completed_replay(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)
    turn_id = uuid.uuid4()
    job = SimpleNamespace(chat_session_id=session.id, event_sequence=12)
    validated = []

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(existing_job=job, reconciled_expired_count=0)

        def validate_replay(self, _preflight, **identity):
            validated.append(identity)

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        status="complete",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=3,
        web_search_enabled=False,
        app_release_id="release-a",
        worker_contract_version="contract-a",
    )
    db = _ScriptedDB(
        execute_results=(
            _Result(one=existing),
            _Result(one=SimpleNamespace(content="persisted", followups=[])),
        )
    )
    service = ChatSessionService(db, settings)
    loaded_session_ids = []

    def _owned(_owner, session_id, **_kwargs):
        loaded_session_ids.append(session_id)
        return session

    service._owned = _owned

    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=None,
        client_message_id="stable-request",
        text="retry",
    )

    assert admission.turn_id == turn_id
    assert admission.replay_assistant is not None
    assert admission.attach_only is True
    assert admission.durable_event_sequence == 12
    assert loaded_session_ids == [session.id]
    assert validated == [
        {
            "turn_id": turn_id,
            "chat_session_id": session.id,
            "hf_user_id": "owner-1",
            "revision": 3,
            "dispatch_route": "legacy-claude",
            "app_release_id": "release-a",
            "worker_contract_version": "contract-a",
            "now": validated[0]["now"],
        }
    ]
    assert db.added == []
    assert db.flush_calls == 0


def test_enabled_in_progress_replay_attaches_without_readmission(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(
                existing_job=SimpleNamespace(chat_session_id=session.id),
                reconciled_expired_count=0,
            )

        def admit(self, *_args, **_kwargs):
            pytest.fail("in-progress replay was readmitted")

        def validate_replay(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        status="generating",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=1,
        web_search_enabled=False,
        reasoning_effort="high",
        app_release_id="release-a",
        worker_contract_version="contract-a",
    )
    session.active_turn_id = existing.turn_id
    session.active_turn_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    db = _ScriptedDB(execute_results=(_Result(one=existing), _Result(one=None)))
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=None,
        client_message_id="running-request",
        text="retry",
    )

    assert admission.turn_id == existing.turn_id
    assert admission.attach_only is True
    assert admission.replay_assistant is None
    assert db.added == []
    assert db.flush_calls == 0


def test_qualified_pi_replay_preserves_identity_without_duplicate_reservation(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": False,
        }
    )
    session = _session(settings)
    session.agent_harness = "pi"

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(
                existing_job=SimpleNamespace(
                    chat_session_id=session.id, event_sequence=4
                ),
                reconciled_expired_count=0,
            )

        def reserve_external_capacity(self, *_args, **_kwargs):
            pytest.fail("qualified replay reserved duplicate external capacity")

        def validate_replay(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        status="generating",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=1,
        web_search_enabled=False,
        reasoning_effort="high",
        app_release_id=settings.release_id,
        worker_contract_version="contract-a",
        agent_harness="pi",
    )
    session.active_turn_id = existing.turn_id
    session.active_turn_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    db = _ScriptedDB(execute_results=(_Result(one=existing), _Result(one=None)))
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=None,
        client_message_id="qualified-replay",
        text="retry",
        qualification=_qualification(settings),
    )

    assert admission.turn_id == existing.turn_id
    assert admission.session_id == session.id
    assert admission.attach_only is True


def test_enabled_different_active_message_remains_rejected(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)
    session.active_turn_id = uuid.uuid4()
    session.active_turn_expires_at = datetime.now(UTC) + timedelta(minutes=1)

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def authorize_global_capacity(self, preflight, **_kwargs):
            return preflight

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    db = _ScriptedDB(execute_results=(_Result(one=None),))
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="different-request",
            text="must remain rejected",
        )

    assert exc_info.value.code == "session_busy"
    assert db.added == []
    assert db.flush_calls == 0


def test_enabled_integrity_failure_rolls_back_session_and_message(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    session = _session(settings)

    class _Coordinator:
        def __init__(self, *_args, **_kwargs):
            pass

        def preflight(self, **_kwargs):
            return SimpleNamespace(existing_job=None, reconciled_expired_count=0)

        def authorize_global_capacity(self, preflight, **_kwargs):
            return preflight

        def admit(self, *_args, **_kwargs):
            raise IntegrityError("insert chat_turn_jobs", {}, RuntimeError("conflict"))

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _Coordinator
    )
    db = _TransactionalScriptedDB(
        execute_results=(_Result(one=None), _Result()),
        scalar_results=(0,),
        tracked=(session,),
    )
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session
    before = vars(session).copy()

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session.id,
            client_message_id="flush-conflict",
            text="must roll back",
        )
    db.rollback()

    assert exc_info.value.code == "durable_admission_failed"
    assert exc_info.value.commit_changes is False
    assert any(isinstance(row, ChatMessageRecord) for row in db.rows_at_rollback)
    assert vars(session) == before
    assert db.rows == []


def test_disabled_mode_never_constructs_durable_coordinator(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    session = _session(settings)

    class _ForbiddenCoordinator:
        def __init__(self, *_args, **_kwargs):
            pytest.fail("disabled durable coordinator was constructed")

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", _ForbiddenCoordinator
    )
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        status="complete",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=1,
        web_search_enabled=False,
    )
    db = _ScriptedDB(
        execute_results=(
            _Result(one=existing),
            _Result(one=SimpleNamespace(content="persisted", followups=[])),
        )
    )
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=session.id,
        client_message_id="legacy-replay",
        text="retry",
    )

    assert admission.turn_id == existing.turn_id
    assert db.added == []
    assert db.flush_calls == 0
