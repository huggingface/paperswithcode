from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.models.database import (
    AutonomousAction,
    AutonomousControlEvent,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
    ChatProviderRuntimeState,
    ChatReliabilityBaseline,
)
from backend.routers import autonomous_operations
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)
from backend.utils.auth import require_admin


NOW = datetime.now(UTC).replace(microsecond=0)
RUN_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000501")


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (
        AutonomousOperatorState,
        AutonomousRun,
        AutonomousAction,
        AutonomousControlEvent,
        AutonomousRepairLease,
        ChatReliabilityBaseline,
        ChatProviderRuntimeState,
    ):
        model.__table__.create(engine)
    db = Session(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(autonomous_operations.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: db
    app.dependency_overrides[require_admin] = lambda: {
        "hf_subject": "admin-subject",
        "username": "owner",
        "role": "admin",
    }
    try:
        yield TestClient(app), db
    finally:
        db.close()
        engine.dispose()


def _seed_snapshot(db: Session) -> None:
    db.add_all(
        [
            AutonomousOperatorState(
                operator="global",
                enabled=False,
                manual_mode=True,
                revision=7,
                updated_by="admin:owner",
                updated_at=NOW,
            ),
            *(
                AutonomousOperatorState(
                    operator=operator,
                    enabled=operator != "chat_reliability",
                    manual_mode=False,
                    revision=1,
                    updated_by="admin:owner",
                    updated_at=NOW,
                )
                for operator in (
                    "submissions",
                    "curation",
                    "cron_health",
                    "chat_reliability",
                )
            ),
            AutonomousRun(
                id=RUN_ID,
                operator="cron_health",
                dry_run=False,
                manifest_revision="manifest-v1",
                status="completed",
                input_tokens=100,
                output_tokens=20,
                cost_usd=Decimal("0.125"),
                result_digest="a" * 64,
                exit_classification="completed",
                capability_requests=[],
                evidence_digests=["d" * 64],
                pricing_revision="pricing-v1",
                pricing_policy_digest="e" * 64,
                created_at=NOW,
            ),
            AutonomousAction(
                id=uuid.uuid4(),
                run_id=RUN_ID,
                operator="cron_health",
                capability="retry_declared_cron",
                reason_code="recovered",
                resource_kind="declared_cron",
                resource_identifier="refresh_papers",
                before_digest="b" * 64,
                after_digest="c" * 64,
                created_at=NOW,
            ),
            AutonomousRepairLease(
                singleton_key="source_repair",
                lease_id=uuid.uuid4(),
                owner_run_id=RUN_ID,
                owner_operator="cron_health",
                expires_at=NOW + timedelta(hours=1),
                created_at=NOW,
            ),
            ChatReliabilityBaseline(
                singleton=True,
                sha="f" * 40,
                revision=3,
                qualified_by="admin:owner",
                qualified_at=NOW,
            ),
            ChatProviderRuntimeState(
                environment="production",
                manifest_revision="provider-v1",
                state_revision=2,
                active_provider="primary",
                reason_code="healthy",
                updated_at=NOW,
            ),
        ]
    )
    db.commit()


def test_admin_read_model_is_content_free_and_keeps_monitoring_visible(
    api, monkeypatch
):
    client, db = api
    monkeypatch.setattr(
        AutonomousOperationsRepository,
        "_database_now",
        staticmethod(lambda _db: NOW),
    )
    _seed_snapshot(db)

    response = client.get("/api/v1/admin/autonomous-operations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"] == 7
    assert payload["manual_mode"] is True
    assert payload["monitoring_active"] is True
    assert payload["display_state"] == "manual"
    assert payload["monitoring_active"] is True
    assert next(
        row for row in payload["operators"] if row["operator"] == "cron_health"
    )["next_scheduled_run"] == (NOW + timedelta(minutes=15)).isoformat().replace(
        "+00:00", "Z"
    )
    assert payload["active_lease"]["owner_operator"] == "cron_health"
    assert payload["costs"] == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_usd": "0.125000000",
    }
    assert payload["baseline"]["sha"] == "f" * 40
    assert payload["provider_states"][0]["active_provider"] == "primary"
    assert "task_creation" in payload["exclusions"]
    serialized = response.text.lower()
    assert "evidence_digests" not in serialized
    assert "result_digest" not in serialized
    assert "prompt" not in serialized
    assert "user_chat" not in serialized


def test_admin_mutations_require_typed_confirmation_and_audit_actor(api):
    client, db = api

    rejected = client.patch(
        "/api/v1/admin/autonomous-operations/manual-mode",
        json={
            "enabled": False,
            "expected_revision": 1,
            "confirmation": "wrong",
        },
    )
    assert rejected.status_code == 422

    accepted = client.patch(
        "/api/v1/admin/autonomous-operations/manual-mode",
        json={
            "enabled": False,
            "expected_revision": 1,
            "confirmation": "SET_MANUAL_MODE",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["manual_mode"] is False
    assert accepted.json()["revision"] == 2
    event = db.query(AutonomousControlEvent).one()
    assert event.actor == "admin:admin-subject"
    assert event.event_kind == "manual_mode"


def test_acceptance_evidence_endpoint_is_idempotent_and_gates_enablement(api):
    client, db = api
    blocked = client.patch(
        "/api/v1/admin/autonomous-operations/operators/cron_health",
        json={
            "enabled": True,
            "expected_revision": 1,
            "confirmation": "SET_OPERATOR_STATE",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "acceptance_incomplete"

    gates = (
        "shadow_diagnosis",
        "missed_schedule",
        "stale_log",
        "stale_durable_data",
        "safe_retry",
        "rejected_schema_change",
        "source_repair",
        "failed_production_verification",
        "rollback",
    )
    first_id = None
    for index, gate in enumerate(gates, start=1):
        response = client.post(
            "/api/v1/admin/autonomous-operations/operators/cron_health/acceptance-evidence",
            json={
                "gate_code": gate,
                "evidence_digest": f"{index:064x}",
                "confirmation": "RECORD_ACCEPTANCE_EVIDENCE",
            },
        )
        assert response.status_code == 200
        if first_id is None:
            first_id = response.json()["evidence_id"]

    duplicate = client.post(
        "/api/v1/admin/autonomous-operations/operators/cron_health/acceptance-evidence",
        json={
            "gate_code": gates[0],
            "evidence_digest": f"{1:064x}",
            "confirmation": "RECORD_ACCEPTANCE_EVIDENCE",
        },
    )
    assert duplicate.json()["evidence_id"] == first_id
    assert db.query(AutonomousControlEvent).count() == len(gates)

    enabled = client.patch(
        "/api/v1/admin/autonomous-operations/operators/cron_health",
        json={
            "enabled": True,
            "expected_revision": 1,
            "confirmation": "SET_OPERATOR_STATE",
        },
    )
    assert enabled.status_code == 200
    cron = next(
        row for row in enabled.json()["operators"] if row["operator"] == "cron_health"
    )
    assert cron["enabled"] is True


def test_acceptance_evidence_endpoint_rejects_unknown_gate(api):
    client, _db = api

    response = client.post(
        "/api/v1/admin/autonomous-operations/operators/cron_health/acceptance-evidence",
        json={
            "gate_code": "invented_gate",
            "evidence_digest": "a" * 64,
            "confirmation": "RECORD_ACCEPTANCE_EVIDENCE",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_acceptance_gate"


def test_acceptance_readiness_is_available_without_recording_new_evidence(api):
    client, _db = api

    response = client.get(
        "/api/v1/admin/autonomous-operations/operators/submissions/acceptance-readiness"
    )

    assert response.status_code == 200
    assert response.json() == {
        "operator": "submissions",
        "ready": False,
        "passed_gates": [],
        "missing_gates": [
            "callback_idempotency",
            "external_no_enrichment",
            "human_only_deferral",
            "max_batch",
            "oldest_first",
        ],
        "shadow_days": 0,
        "required_shadow_days": 7,
    }


def test_curation_acceptance_readiness_uses_public_operator_contract(api):
    client, _db = api

    response = client.get(
        "/api/v1/admin/autonomous-operations/operators/curation/acceptance-readiness"
    )

    assert response.status_code == 200
    assert response.json() == {
        "operator": "curation",
        "ready": False,
        "passed_gates": [],
        "missing_gates": [
            "callback_idempotency",
            "capability_isolation",
            "dispatcher_preflight",
            "paused_callback_apply",
        ],
        "shadow_days": 0,
        "required_shadow_days": 0,
    }


def test_stale_operator_mutation_returns_conflict_without_overwrite(api):
    client, db = api
    _seed_snapshot(db)

    response = client.patch(
        "/api/v1/admin/autonomous-operations/operators/submissions",
        json={
            "enabled": True,
            "expected_revision": 99,
            "confirmation": "SET_OPERATOR_STATE",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_revision"
    state = db.get(AutonomousOperatorState, "submissions")
    assert state is not None and state.enabled is True


def test_chat_baseline_qualification_requires_exact_sha_and_revision(api):
    client, db = api

    invalid = client.post(
        "/api/v1/admin/autonomous-operations/chat-baseline",
        json={
            "sha": "main",
            "expected_revision": 0,
            "confirmation": "QUALIFY_CHAT_BASELINE",
        },
    )
    assert invalid.status_code == 422

    response = client.post(
        "/api/v1/admin/autonomous-operations/chat-baseline",
        json={
            "sha": "a" * 40,
            "expected_revision": 0,
            "confirmation": "QUALIFY_CHAT_BASELINE",
        },
    )
    assert response.status_code == 200
    baseline = response.json()["baseline"]
    assert baseline["sha"] == "a" * 40
    assert baseline["revision"] == 1
    assert baseline["qualified_by"] == "admin:admin-subject"
    assert datetime.fromisoformat(baseline["qualified_at"]).tzinfo is not None
    assert db.query(ChatReliabilityBaseline).one().sha == "a" * 40


def test_route_requires_admin_authentication():
    app = FastAPI()
    app.include_router(autonomous_operations.router, prefix="/api/v1")

    response = TestClient(app).get("/api/v1/admin/autonomous-operations")

    assert response.status_code == 401


def test_authenticated_non_admin_cannot_access_route(monkeypatch):
    from backend.utils import auth

    monkeypatch.setattr(
        auth,
        "_session_actor",
        lambda _request: {"hf_subject": "contributor", "role": "contributor"},
    )
    app = FastAPI()
    app.include_router(autonomous_operations.router, prefix="/api/v1")

    response = TestClient(app).get("/api/v1/admin/autonomous-operations")

    assert response.status_code == 401


def test_snapshot_uses_each_operator_history_and_newer_success_clears_rollback(api):
    _client, db = api
    repository = AutonomousOperationsRepository(clock=lambda _db: NOW)
    state = repository.get_control_state(db)
    state = repository.set_manual_mode(
        db,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )
    for operator in Operator:
        state = repository.set_operator_enabled(
            db,
            operator=operator,
            enabled=True,
            expected_revision=state.revision,
            actor="admin:owner",
            now=NOW,
        )
    submission_run = uuid.uuid4()
    db.add_all(
        [
            AutonomousRun(
                id=submission_run,
                operator="submissions",
                dry_run=False,
                manifest_revision="manifest-v1",
                status="completed",
                exit_classification="completed",
                capability_requests=[],
                evidence_digests=[],
                created_at=NOW - timedelta(minutes=1),
            ),
            AutonomousAction(
                id=uuid.uuid4(),
                run_id=submission_run,
                operator="submissions",
                capability="apply_submission_decision",
                reason_code="rolled_back",
                resource_kind="pending_edit",
                resource_identifier="submission_1",
                before_digest="a" * 64,
                after_digest="b" * 64,
                created_at=NOW - timedelta(minutes=2),
            ),
            AutonomousRun(
                id=uuid.uuid4(),
                operator="chat_reliability",
                dry_run=True,
                manifest_revision="manifest-v1",
                status="completed",
                exit_classification="completed",
                capability_requests=[],
                evidence_digests=[],
                created_at=NOW - timedelta(minutes=2),
            ),
            AutonomousRun(
                id=uuid.uuid4(),
                operator="curation",
                dry_run=False,
                manifest_revision="curation-v1",
                status="completed",
                exit_classification="completed",
                capability_requests=[],
                evidence_digests=[],
                created_at=NOW - timedelta(minutes=2),
            ),
            *[
                AutonomousRun(
                    id=uuid.uuid4(),
                    operator="cron_health",
                    dry_run=True,
                    manifest_revision="manifest-v1",
                    status="completed",
                    exit_classification="completed",
                    capability_requests=[],
                    evidence_digests=[],
                    created_at=NOW - timedelta(seconds=index),
                )
                for index in range(30)
            ],
        ]
    )
    db.commit()

    snapshot = repository.get_admin_snapshot(db, limit=25)

    assert len(snapshot["recent_runs"]) == 25
    assert snapshot["display_state"] == "healthy"
    assert {row["operator"]: row["status"] for row in snapshot["operators"]} == {
        "submissions": "healthy",
        "curation": "healthy",
        "cron_health": "healthy",
        "chat_reliability": "healthy",
    }


def test_production_application_registers_admin_control_plane(monkeypatch):
    from backend.config import get_settings
    from backend.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("PWC_CHAT_ENABLED", "false")
    monkeypatch.setenv("PWC_CRON_ENABLED", "false")
    app = create_app()

    assert "/api/v1/admin/autonomous-operations" in {route.path for route in app.routes}
