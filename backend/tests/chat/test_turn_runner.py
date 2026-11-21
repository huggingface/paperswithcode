from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import uuid

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services import chat_turn_runner as runner_module
from backend.services.chat_turn_runner import (
    ModalChatTurnRunner,
    _uses_external_pi,
    _provider_mode_for_route,
    create_chat_turn_runner,
)


def test_direct_openai_route_uses_server_funded_provider_mode():
    settings = get_settings().model_copy(
        update={
            "environment": "staging",
            "chat_openai_direct_enabled": True,
        }
    )
    owner = type("Owner", (), {"openrouter_mode": "openrouter_byok"})()

    assert (
        _provider_mode_for_route(settings, owner, "gpt-5.6-luna@openai")
        == "openai_funded"
    )


def test_modal_runner_preserves_admitted_reasoning_effort():
    captured = {}
    sentinel = object()
    settings = get_settings()
    model_route = settings.chat_deepseek_v4_flash_route

    class Manager:
        def __init__(self, manager_settings):
            self.settings = manager_settings

        def run_turn(self, **kwargs):
            captured.update(kwargs)
            return sentinel

    runner = ModalChatTurnRunner(
        settings=settings,
        admission=TurnAdmission(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            selected_model="deepseek-ai/DeepSeek-V4-Flash-0731",
            model_route=model_route,
            sdk_session_id=None,
            sdk_project_key=None,
            agent_harness="pi",
            execution_backend="modal_cli",
            reasoning_effort="low",
        ),
        prompt="content-free test prompt",
        request_id=str(uuid.uuid4()),
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        manager=Manager(settings),
    )

    assert runner.events() is sentinel
    assert captured["agent_harness"] == "pi"
    assert captured["model"] == model_route
    assert captured["reasoning_effort"] == "low"


def test_external_pi_admission_selects_only_pi_modal_turns():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_admission_enabled = True
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
    )
    assert _uses_external_pi(settings, admission) is True
    assert (
        _uses_external_pi(
            settings,
            admission.__class__(**{**admission.__dict__, "agent_harness": "claude"}),
        )
        is False
    )


def test_persisted_qualified_pi_turn_selects_external_when_global_admission_is_off():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_admission_enabled = False
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
    )

    assert _uses_external_pi(settings, admission, qualification_authorized=True) is True


def test_reconstructed_admission_uses_persisted_qualification_and_reservation(
    monkeypatch,
):
    settings = get_settings().model_copy(
        update={
            "environment": "staging",
            "chat_external_pi_admission_enabled": False,
        }
    )
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
    )
    issued_scopes = []

    class DB:
        def commit(self):
            return None

    @contextmanager
    def session_local():
        yield DB()

    class Evidence:
        def __init__(self, _db):
            pass

        def external_pi_authorized(self, **identity):
            assert identity["turn_id"] == admission.turn_id
            assert identity["chat_session_id"] == admission.session_id
            return True

    class Capabilities:
        def __init__(self, _db):
            pass

        def issue(self, **kwargs):
            issued_scopes.append(kwargs["scopes"])
            return IssuedCapability(
                token="opaque-capability",
                capability_id=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )

    class ReconstructedExternalRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    marked: list[str] = []

    class Latency:
        def __init__(self, _db):
            pass

        def mark_external_pi(self, request_id):
            marked.append(request_id)
            return True

    monkeypatch.setattr(runner_module.db_manager, "_session_local", session_local)
    monkeypatch.setattr(runner_module, "ChatLatencyService", Latency)
    monkeypatch.setattr(
        runner_module, "ChatDurableQualificationEvidenceService", Evidence
    )
    monkeypatch.setattr(runner_module, "ChatCapabilityService", Capabilities)
    monkeypatch.setattr(
        runner_module, "ExternalPiChatTurnRunner", ReconstructedExternalRunner
    )

    runner = create_chat_turn_runner(
        settings=settings,
        owner=ChatOwner("owner", "owner"),
        admission=admission,
        prompt="content-free",
        request_id=str(uuid.uuid4()),
        resume_id=None,
        store=object(),
    )

    assert isinstance(runner, ReconstructedExternalRunner)
    assert issued_scopes == [{"model", "catalog", "session_store", "external_turn"}]
    # The turn must be recorded against the external fleet so it is not billed
    # for a Modal sandbox it never allocates.
    assert marked == [runner.kwargs["request_id"]]


def _failover_factory(monkeypatch, *, session_has_files: bool, enabled: bool = True):
    settings = get_settings().model_copy(
        update={
            "environment": "production",
            "chat_external_pi_admission_enabled": True,
            "chat_openai_direct_enabled": True,
            "chat_provider_failover_enabled": enabled,
        }
    )
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model=settings.chat_openai_luna_route,
        model_route=settings.chat_openai_luna_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="medium",
    )
    issued: list[dict] = []

    class DB:
        def commit(self):
            return None

        def scalar(self, _statement):
            return session_has_files

    @contextmanager
    def session_local():
        yield DB()

    class Capabilities:
        def __init__(self, _db):
            pass

        def issue(self, **kwargs):
            issued.append(kwargs)
            return IssuedCapability(
                token=f"capability-{len(issued)}",
                capability_id=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )

    class ExternalRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Latency:
        def __init__(self, _db):
            pass

        def mark_external_pi(self, _request_id):
            return True

    monkeypatch.setattr(runner_module.db_manager, "_session_local", session_local)
    monkeypatch.setattr(runner_module, "ChatLatencyService", Latency)
    monkeypatch.setattr(runner_module, "ChatCapabilityService", Capabilities)
    monkeypatch.setattr(runner_module, "ExternalPiChatTurnRunner", ExternalRunner)
    runner = create_chat_turn_runner(
        settings=settings,
        owner=ChatOwner("owner", "owner"),
        admission=admission,
        prompt="content-free",
        request_id=str(uuid.uuid4()),
        resume_id=None,
        store=object(),
    )
    return settings, issued, runner


def test_luna_turn_offers_a_credential_free_sponsored_fallback(monkeypatch):
    settings, issued, runner = _failover_factory(monkeypatch, session_has_files=False)

    route = settings.chat_sponsored_deepseek_route
    assert [kwargs["model"] for kwargs in issued] == [
        settings.chat_openai_luna_route,
        route,
    ]
    fallback_issue = issued[1]
    assert fallback_issue["scopes"] == {"model", "external_turn"}
    assert fallback_issue["provider_mode"] == "huggingface"
    assert "provider_token" not in fallback_issue
    assert fallback_issue["turn_id"] == issued[0]["turn_id"]
    fallback = runner.kwargs["provider_fallback"]
    assert fallback.route == route
    assert fallback.model == route
    assert fallback.protocol == "anthropic-messages"
    assert fallback.capability.token == "capability-2"


def test_sessions_with_uploaded_files_get_no_fallback(monkeypatch):
    _settings, issued, runner = _failover_factory(monkeypatch, session_has_files=True)

    assert len(issued) == 1
    assert runner.kwargs["provider_fallback"] is None


def test_disabled_failover_issues_only_the_primary_capability(monkeypatch):
    _settings, issued, runner = _failover_factory(
        monkeypatch, session_has_files=False, enabled=False
    )

    assert len(issued) == 1
    assert runner.kwargs["provider_fallback"] is None
