from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.chat_gateway_app as gateway
from backend.services.chat_provider_gateway import anthropic_messages
import backend.services.chat_turn_runner as turn_runner
from backend.config import get_settings
from backend.services.chat_capability_service import (
    ChatCapabilityService,
    IssuedCapability,
)
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_turn_job_repository import StaleTurnClaim, TurnLeaseClaim


class FenceDB:
    def __init__(self, *, on_commit=None, on_get=None, on_rollback=None) -> None:
        self.rollbacks = 0
        self.on_commit = on_commit
        self.on_get = on_get
        self.on_rollback = on_rollback

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.on_rollback is not None:
            self.on_rollback()

    def commit(self) -> None:
        if self.on_commit is not None:
            self.on_commit()

    def get(self, *args, **kwargs):
        if self.on_get is not None:
            return self.on_get(*args, **kwargs)
        return None


def _external_capability(turn_id: uuid.UUID):
    return SimpleNamespace(
        turn_id=turn_id,
        scopes=["model", "catalog", "session_store", "external_turn"],
    )


def test_capability_service_accepts_the_external_turn_scope():
    added = []

    class DB:
        def add(self, row):
            added.append(row)

        def flush(self):
            pass

    issued = ChatCapabilityService(DB()).issue(
        chat_session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        owner_id="owner-1",
        model="route",
        scopes={"model", "external_turn"},
        agent_harness="pi",
    )

    assert issued.capability_id == added[0].id
    assert added[0].scopes == ["external_turn", "model"]


def test_external_turn_scope_requires_all_claim_headers(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    with pytest.raises(HTTPException) as error:
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "chat_turn_fence_missing"


def test_external_turn_scope_rejects_a_stale_claim(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    class Jobs:
        def require_live_claim(self, *_args, **_kwargs):
            raise StaleTurnClaim("stale")

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    with pytest.raises(HTTPException) as error:
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
            turn_fence=gateway.ExternalTurnFenceHeaders("api-1", "4", "9"),
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "chat_turn_fence_stale"


def test_external_turn_scope_checks_the_exact_immutable_claim(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    observed: list[TurnLeaseClaim] = []

    class Jobs:
        def require_live_claim(self, _db, *, claim, now):
            assert now.tzinfo is not None
            observed.append(claim)

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    assert (
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
            turn_fence=gateway.ExternalTurnFenceHeaders("api-1", "4", "9"),
        )
        is row
    )
    assert observed == [TurnLeaseClaim(turn_id, "api-1", 4, 9)]


def test_legacy_sandbox_scope_remains_header_free(monkeypatch):
    row = SimpleNamespace(scopes=["model"])
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    class Jobs:
        def require_live_claim(self, *_args, **_kwargs):
            raise AssertionError("legacy capabilities must not consult the turn fence")

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    assert (
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            FenceDB(),
        )
        is row
    )


GATEWAY_CASES = [
    (
        "pwc_mcp",
        "/catalog-mcp",
        {"tool": "search_papers", "arguments": {"query": "x"}},
        {},
    ),
    (
        "paper_catalog",
        "/catalog",
        {"operation": "search", "arguments": {"query": "x"}},
        {},
    ),
    (
        "web_search",
        "/catalog",
        {"operation": "web_search", "arguments": {"query": "x"}},
        {},
    ),
    (
        "hf_catalog",
        "/hf-catalog",
        {"operation": "model_info", "arguments": {"repo_id": "owner/model"}},
        {},
    ),
    (
        "session_store",
        "/session-store",
        {
            "action": "load_session",
            "format": "pi",
            "agent_session_id": "30000000-0000-4000-8000-000000000001",
        },
        {},
    ),
    (
        "artifact_prepare",
        "/artifact-prepare",
        {"paper_route_id": "2401.00001"},
        {},
    ),
    ("paper", "/paper", {"operation": "create", "title": "Draft"}, {}),
    (
        "artifact_publish",
        "/artifact-publish?publication_id=publication-1",
        b"x",
        {"Content-Type": "application/zip"},
    ),
    ("web_fetch", "/web-fetch", {"url": "https://example.com"}, {}),
    (
        "responses",
        "/v1/responses",
        {"model": "gpt-5.6", "input": "x", "max_output_tokens": 1},
        {},
    ),
    (
        "messages",
        "/v1/messages",
        {"model": "route", "messages": [], "max_tokens": 1},
        {},
    ),
]


@pytest.mark.parametrize(
    ("_name", "path", "body", "extra_headers"),
    GATEWAY_CASES,
)
def test_every_gateway_entry_rejects_an_external_capability_before_side_effects(
    monkeypatch, _name, path, body, extra_headers
):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    settings = get_settings().model_copy(deep=True)
    settings.chat_hf_catalog_enabled = True
    settings.chat_pwc_mcp_enabled = True
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-openai-key"
    settings.chat_openai_model = "gpt-5.6"
    db = FenceDB()
    gateway.app.dependency_overrides[gateway.get_database_session] = lambda: db
    gateway.app.dependency_overrides[gateway.get_settings] = lambda: settings
    headers = {
        "Authorization": "Bearer token",
        "X-PWC-Session": str(uuid.uuid4()),
        "X-PWC-Turn": str(turn_id),
        **extra_headers,
    }
    try:
        with TestClient(gateway.app, raise_server_exceptions=False) as client:
            if isinstance(body, bytes):
                response = client.post(path, content=body, headers=headers)
            else:
                response = client.post(path, json=body, headers=headers)
    finally:
        gateway.app.dependency_overrides.clear()

    assert response.status_code == 403, (path, response.text)
    assert response.json()["detail"]["code"] == "chat_turn_fence_missing"


def _install_downstream_sentinel(monkeypatch, name, reached, db):
    def hit(*_args, **_kwargs):
        reached.append(name)
        raise HTTPException(status_code=418, detail="downstream_reached")

    if name in {"paper_catalog", "pwc_mcp"}:
        monkeypatch.setattr(gateway.ChatCapabilityService, "meter_catalog", hit)
    elif name == "web_search":
        monkeypatch.setattr(gateway.ChatCapabilityService, "meter_web_search", hit)
    elif name == "hf_catalog":
        monkeypatch.setattr(gateway.ChatCapabilityService, "meter_hf_catalog", hit)
    elif name == "session_store":
        monkeypatch.setattr(gateway.ChatPiTranscriptService, "load_session", hit)
    elif name == "artifact_prepare":
        monkeypatch.setattr(gateway.ChatPaperContextService, "prepare_one", hit)
    elif name == "paper":
        db.on_get = hit
    elif name == "artifact_publish":
        monkeypatch.setattr(gateway.tempfile, "mkstemp", hit)
    elif name == "web_fetch":
        db.on_commit = hit
    else:
        monkeypatch.setattr(gateway, "_capability_owner", lambda *_args: "owner-1")
        monkeypatch.setattr(
            anthropic_messages,
            "provider_target",
            lambda *_args: ("https://provider.example.test", "token", None),
        )
        monkeypatch.setattr(gateway.ChatCapabilityService, "meter_provider", hit)


@pytest.mark.parametrize(("name", "path", "body", "extra_headers"), GATEWAY_CASES)
@pytest.mark.parametrize("claim_variant", ["exact", "stale_worker", "stale_lease"])
def test_every_gateway_entry_forwards_the_exact_claim_before_downstream_work(
    monkeypatch, name, path, body, extra_headers, claim_variant
):
    turn_id = uuid.uuid4()
    settings = get_settings().model_copy(deep=True)
    settings.chat_hf_catalog_enabled = True
    settings.chat_pwc_mcp_enabled = True
    settings.chat_artifacts_enabled = True
    settings.chat_posterly_enabled = True
    settings.chat_latex_paper_enabled = True
    settings.chat_latex_compiler_jobs_enabled = True
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-openai-key"
    settings.chat_openai_model = "gpt-5.6"
    model = (
        settings.chat_openai_luna_route
        if name == "responses"
        else settings.chat_deepseek_v4_flash_openrouter_route
    )
    if name == "responses":
        body = {**body, "model": settings.chat_openai_model}
    elif name == "messages":
        body = {**body, "model": model}
    row = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        chat_session_id=uuid.uuid4(),
        scopes=[
            "model",
            "catalog",
            "web_search",
            "hf_catalog",
            "session_store",
            "artifact",
            "paper",
            "web_fetch",
            "external_turn",
        ],
        owner_hash="a" * 64,
        agent_harness="pi",
        provider_mode="openai_funded" if name == "responses" else "openrouter_funded",
        model=model,
        reasoning_effort="high",
        provider_requests=0,
        provider_tokens=0,
        artifact_paper_id=uuid.uuid4(),
    )
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    expected = TurnLeaseClaim(turn_id, "api-1", 4, 9)

    class Jobs:
        def require_live_claim(self, _db, *, claim, now):
            assert now.tzinfo is not None
            if claim != expected:
                raise StaleTurnClaim("stale")

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs)
    reached = []
    db = FenceDB()
    _install_downstream_sentinel(monkeypatch, name, reached, db)
    gateway.app.dependency_overrides[gateway.get_database_session] = lambda: db
    gateway.app.dependency_overrides[gateway.get_settings] = lambda: settings
    worker_generation = "5" if claim_variant == "stale_worker" else "4"
    lease_generation = "10" if claim_variant == "stale_lease" else "9"
    headers = {
        "Authorization": "Bearer token",
        "X-PWC-Session": str(row.chat_session_id),
        "X-PWC-Turn": str(turn_id),
        "X-PWC-Turn-Worker-ID": "api-1",
        "X-PWC-Turn-Worker-Generation": worker_generation,
        "X-PWC-Turn-Lease-Generation": lease_generation,
        **extra_headers,
    }
    try:
        with TestClient(gateway.app, raise_server_exceptions=False) as client:
            if isinstance(body, bytes):
                response = client.post(path, content=body, headers=headers)
            else:
                response = client.post(path, json=body, headers=headers)
    finally:
        gateway.app.dependency_overrides.clear()

    if claim_variant == "exact":
        assert response.status_code == 418, (name, response.text)
        assert reached == [name]
    else:
        assert response.status_code == 403, (name, claim_variant, response.text)
        assert response.json()["detail"]["code"] == "chat_turn_fence_stale"
        assert reached == []


def test_rejected_external_fence_rolls_back_capability_accounting(monkeypatch):
    turn_id = uuid.uuid4()
    row = SimpleNamespace(scopes=["model", "external_turn"], gateway_calls=0)

    def validate(*_args, **_kwargs):
        row.gateway_calls += 1
        return row

    monkeypatch.setattr(gateway.ChatCapabilityService, "validate", validate)
    db = FenceDB(on_rollback=lambda: setattr(row, "gateway_calls", 0))

    with pytest.raises(HTTPException) as error:
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            db,
        )

    assert error.value.detail["code"] == "chat_turn_fence_missing"
    assert db.rollbacks == 1
    assert row.gateway_calls == 0


def test_gateway_accepts_complete_external_turn_headers(monkeypatch):
    turn_id = uuid.uuid4()
    row = SimpleNamespace(
        turn_id=turn_id,
        scopes=["catalog", "external_turn"],
        owner_hash="a" * 64,
    )
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "meter_catalog",
        lambda *_args, **_kwargs: None,
    )

    class Jobs:
        def require_live_claim(self, _db, *, claim, now):
            assert claim == TurnLeaseClaim(turn_id, "api-1", 4, 9)
            assert now.tzinfo is not None

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs)
    monkeypatch.setattr(
        gateway.ChatGatewayService,
        "catalog",
        lambda *_args, **_kwargs: {"papers": []},
    )
    db = FenceDB()
    gateway.app.dependency_overrides[gateway.get_database_session] = lambda: db
    try:
        with TestClient(gateway.app) as client:
            response = client.post(
                "/catalog",
                json={"operation": "search", "arguments": {"query": "x"}},
                headers={
                    "Authorization": "Bearer token",
                    "X-PWC-Session": str(uuid.uuid4()),
                    "X-PWC-Turn": str(turn_id),
                    "X-PWC-Turn-Worker-ID": "api-1",
                    "X-PWC-Turn-Worker-Generation": "4",
                    "X-PWC-Turn-Lease-Generation": "9",
                },
            )
    finally:
        gateway.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"result": {"papers": []}}


@pytest.mark.parametrize("external", [False, True])
def test_only_external_pi_runner_capabilities_receive_external_turn_scope(
    monkeypatch, external
):
    settings = get_settings().model_copy(deep=True)
    settings.chat_external_pi_admission_enabled = external
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
    owner = ChatOwner(
        hf_user_id="owner-1",
        hf_username="owner",
        hf_inference_token=None,
        hf_inference_bill_to=None,
        openrouter_token=None,
        openrouter_mode="openrouter_funded",
        openrouter_credential_revision=None,
    )
    observed_scopes: list[set[str]] = []

    class DB:
        def commit(self):
            pass

    @contextmanager
    def session():
        yield DB()

    def issue(_self, **kwargs):
        observed_scopes.append(kwargs["scopes"])
        return IssuedCapability("token", None, datetime.now(UTC) + timedelta(minutes=1))

    marked: list[str] = []

    def mark_external_pi(_self, request_id):
        marked.append(request_id)
        return True

    monkeypatch.setattr(
        turn_runner, "db_manager", SimpleNamespace(session_local=session)
    )
    monkeypatch.setattr(ChatCapabilityService, "issue", issue)
    monkeypatch.setattr(
        turn_runner.ChatLatencyService, "mark_external_pi", mark_external_pi
    )
    monkeypatch.setattr(
        turn_runner,
        "ExternalPiChatTurnRunner",
        lambda **_kwargs: "external-runner",
    )
    monkeypatch.setattr(
        turn_runner,
        "ModalChatTurnRunner",
        lambda **_kwargs: "sandbox-runner",
    )

    created = turn_runner.create_chat_turn_runner(
        settings=settings,
        owner=owner,
        admission=admission,
        prompt="answer",
        request_id=str(uuid.uuid4()),
        resume_id=None,
        store=SimpleNamespace(),
    )

    assert created == ("external-runner" if external else "sandbox-runner")
    assert ("external_turn" in observed_scopes[0]) is external
