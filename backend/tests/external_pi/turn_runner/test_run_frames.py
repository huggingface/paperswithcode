"""Run and new-turn frames carry exact capabilities and fences."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
)
from backend.services.chat_external_worker_capacity import (
    UnsupportedChatMode,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeWorkspaceManager,
    SessionContext,
    _tool_runner,
)


@pytest.mark.parametrize(
    ("poster_mode", "paper_artifacts_enabled"),
    [(True, False), (False, True)],
)
def test_external_runner_rejects_authoring_before_any_work(
    poster_mode, paper_artifacts_enabled
):
    settings = get_settings().model_copy(deep=True)
    provider = FakeProvider()
    executor = FakeExecutor()
    manager = FakeWorkspaceManager(provider)
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
        poster_mode=poster_mode,
        paper_artifacts_enabled=paper_artifacts_enabled,
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )

    with pytest.raises(UnsupportedChatMode) as exc_info:
        ExternalPiChatTurnRunner(
            settings=settings,
            admission=admission,
            prompt="author",
            request_id="unsupported-mode",
            resume_id=None,
            capability=IssuedCapability(
                token="opaque-capability",
                capability_id=None,
                expires_at=datetime.now(UTC) + timedelta(minutes=4),
            ),
            hf_username="qualification",
            provider=provider,
            executor=executor,
            workspace_manager=manager,
            worker_capacity_repository=SimpleNamespace(),
            session_factory=SessionContext,
        )

    assert exc_info.value.code == "unsupported_chat_mode"
    assert provider.created == provider.terminated == []
    assert executor.contexts == []
    assert manager.acquired == manager.released == manager.invalidated == []


def test_external_run_frame_omits_absent_paper_descriptor():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.external_worker_claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )

    assert runner.admission.paper_descriptor is None
    assert "paper_descriptor" not in runner._run_frame()


@pytest.mark.parametrize(
    ("worker_enabled", "host_enabled", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_external_run_frame_carries_excalidraw_capability(
    worker_enabled, host_enabled, expected
):
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.settings.chat_excalidraw_enabled = worker_enabled
    runner.settings.chat_mcp_apps_host_enabled = host_enabled

    assert runner._run_frame()["excalidraw_enabled"] is expected


def test_external_new_turn_frame_carries_prebound_pi_session():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    agent_session_id = uuid.uuid4()
    runner.admission = replace(
        runner.admission,
        sdk_session_id=agent_session_id,
        is_first_turn=True,
    )
    runner.resume_id = agent_session_id

    assert runner._run_frame()["agent_session_id"] == str(agent_session_id)
    assert runner._run_frame()["resume"] is None


def test_external_run_frame_preserves_exact_durable_turn_fence_as_strings():
    runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
    runner.external_worker_claim = ExternalWorkerClaim(
        "staging-green", uuid.uuid4(), 72, "release-a", "external-pi-v1"
    )

    assert runner._turn_claim_frame() == {
        "turnId": str(runner.admission.turn_id),
        "workerId": runner.admission.durable_claim.worker_id,
        "workerGeneration": str(runner.admission.durable_claim.worker_generation),
        "leaseGeneration": str(runner.admission.durable_claim.lease_generation),
    }
