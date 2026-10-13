from __future__ import annotations

import json
import hmac
import base64
import uuid
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousRun,
    AutonomousSubmissionClaim,
    AutonomousOperatorState,
    PendingPaperEdit,
)
from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.routers import pending_edits
from backend.services.autonomous_operations_repository import ManualModeEnabled
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_capabilities import (
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_codex_runner import (
    AutonomousCodexRunner,
    CodexResult,
    ProposedAction,
    UsageSummary,
)
from backend.services.autonomous_submission_service import (
    AutonomousSubmissionCallbackError,
    AutonomousSubmissionDecision,
    AutonomousSubmissionService,
)
from backend.tests.curation.submission_harness import (
    NOW,
    _run,
    _service,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AutonomousOperatorState,
        AutonomousRun,
        PendingPaperEdit,
        AutonomousSubmissionClaim,
    ):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "JSON"


MIGRATIONS = Path(__file__).parents[2] / "database/migrations"
HUMAN_ONLY = {
    "new_task",
    "new_method",
    "new_benchmark",
    "new_metric",
    "new_conference",
    "new_organization",
}
ALL_TYPES = [
    "tasks",
    "methods",
    "evaluations",
    "repositories",
    "project_pages",
    "source_url",
    "hf_artifacts",
    "organizations",
    *sorted(HUMAN_ONLY),
    "new_external_paper",
]


@pytest.fixture
def postgres_engine():
    database_url = os.getenv("PWC_AUTONOMOUS_SUBMISSION_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PWC_AUTONOMOUS_SUBMISSION_TEST_DATABASE_URL is not configured")
    if not (make_url(database_url).database or "").startswith(
        "autonomous_submission_test_"
    ):
        pytest.fail("Submission concurrency tests require a disposable database")
    engine = create_engine(database_url, pool_size=4)
    pending_sql = """
    CREATE TABLE pending_paper_edits (
      id BIGSERIAL PRIMARY KEY, paper_id BIGINT, hf_username VARCHAR(255) NOT NULL,
      hf_subject VARCHAR(255), source_ip VARCHAR(64), idempotency_key VARCHAR(255),
      payload_hash VARCHAR(64), is_author BOOLEAN NOT NULL DEFAULT false,
      edit_type VARCHAR(32) NOT NULL, proposed_payload JSONB NOT NULL,
      current_payload JSONB, applied_payload JSONB, result_entity_type VARCHAR(64),
      result_entity_id VARCHAR(255), catalog_event_id UUID, conflict_payload JSONB,
      status VARCHAR(16) NOT NULL DEFAULT 'pending', admin_note TEXT,
      user_review_reason TEXT, reviewed_by VARCHAR(255), reviewed_by_kind VARCHAR(16),
      reviewed_by_hf_subject VARCHAR(255), review_run_id UUID, review_model VARCHAR(255),
      review_evidence JSONB, failure_reason TEXT, created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL, reviewed_at TIMESTAMPTZ
    );
    """
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute((MIGRATIONS / "add_autonomous_operations.sql").read_text())
            cursor.execute(pending_sql)
            migration = (
                MIGRATIONS / "add_autonomous_submission_claims.sql"
            ).read_text()
            cursor.execute(migration)
            cursor.execute(migration)
            remote_migration = (
                MIGRATIONS / "add_autonomous_submission_remote_jobs.sql"
            ).read_text()
            cursor.execute(remote_migration)
            cursor.execute(remote_migration)
        connection.commit()
    finally:
        connection.close()
    try:
        yield engine
    finally:
        engine.dispose()


def _edit(db: Session, edit_type: str, age: int, *, payload=None) -> PendingPaperEdit:
    row = PendingPaperEdit(
        hf_username="submitter",
        hf_subject="hf-subject",
        source_ip="203.0.113.1",
        payload_hash=f"{age:064x}",
        edit_type=edit_type,
        proposed_payload=payload or {"value": age},
        current_payload={"before": age},
        status="pending",
        created_at=NOW - timedelta(minutes=age),
        updated_at=NOW - timedelta(minutes=age),
    )
    db.add(row)
    db.flush()
    return row


def _attest(
    db: Session,
    claim_id: str,
    decision: AutonomousSubmissionDecision,
) -> None:
    review_run_id = uuid.uuid4()
    AutonomousOperationsRepository().append_run(
        db,
        context=RunContext(
            review_run_id, Operator.SUBMISSIONS, False, "submission-review-test"
        ),
        status="completed",
        exit_classification="completed",
        now=NOW,
    )
    claim = db.get(AutonomousSubmissionClaim, uuid.UUID(claim_id))
    claim.review_run_id = review_run_id
    claim.attested_decision_digest = sha256(
        json.dumps(
            decision.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    db.commit()


def test_claims_at_most_25_oldest_without_overlap_and_covers_every_type(db):
    first_run, second_run = uuid.uuid4(), uuid.uuid4()
    _run(db, first_run)
    _run(db, second_run)
    rows = [
        _edit(db, edit_type, 100 + index) for index, edit_type in enumerate(ALL_TYPES)
    ]
    rows.extend(_edit(db, "repositories", age) for age in range(1, 20))
    db.commit()

    first = _service(db).claim_submission_batch(first_run, limit=25)
    second = _service(db).claim_submission_batch(second_run, limit=25)

    assert len(first) == 25
    assert {item.pending_edit_id for item in first}.isdisjoint(
        item.pending_edit_id for item in second
    )
    assert [item.pending_edit_id for item in first] == [
        row.id for row in sorted(rows, key=lambda row: (row.created_at, row.id))[:25]
    ]
    assert HUMAN_ONLY <= {item.edit_type for item in first}
    assert all(
        item.required_decision == ("defer" if item.edit_type in HUMAN_ONLY else None)
        for item in first
    )


def test_manifest_is_signed_expiring_immutable_and_omits_private_submitter_data(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    row = _edit(db, "tasks", 1, payload={"task_ids": [7]})
    db.commit()

    service = _service(db)
    manifest = service.build_submission_manifest(
        service.claim_submission_batch(run_id, limit=1)
    )

    assert manifest["run_id"] == str(run_id)
    assert manifest["model_alias"] == "luna-medium"
    assert manifest["expires_at"] == "2026-08-28T13:00:00Z"
    assert manifest["items"][0]["snapshot"] == {
        "id": row.id,
        "paper_id": None,
        "edit_type": "tasks",
        "proposed_payload": {"task_ids": [7]},
        "current_payload": {"before": 1},
        "payload_hash": row.payload_hash,
        "created_at": "2026-08-28T11:59:00Z",
    }
    serialized = str(manifest).lower()
    assert "hf-subject" not in serialized
    assert "submitter" not in serialized
    assert "203.0.113.1" not in serialized
    assert service.verify_manifest(manifest)
    manifest["items"][0]["snapshot"]["proposed_payload"] = {"task_ids": [999]}
    assert not service.verify_manifest(manifest)


def test_review_batch_calls_attested_luna_medium_runner_with_structured_evidence(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    row = _edit(db, "tasks", 1, payload={"task_ids": [7]})
    db.commit()
    service = _service(db)
    batch = service.claim_submission_batch(run_id, limit=1)
    captured = []

    def runner(request, *, db):
        captured.append(request)
        if db.get(AutonomousRun, request.context.run_id) is None:
            AutonomousOperationsRepository().append_run(
                db,
                context=request.context,
                status="completed",
                exit_classification="completed",
                now=NOW,
            )
            db.commit()
        return CodexResult(
            run_id=request.context.run_id,
            status="completed",
            exit_classification="completed",
            proposed_actions=(
                ProposedAction(
                    Capability.REVIEW_SUBMISSION,
                    ResourceRef(ResourceKind.PENDING_EDIT, str(row.id), True),
                    "approve",
                    "The immutable snapshot links an existing task.",
                    (f"submission_snapshot:{batch[0].snapshot_digest}",),
                    0.98,
                    {"task_ids": [7]},
                ),
            ),
            usage=UsageSummary(100, 20, Decimal("0.01")),
            result_digest="a" * 64,
        )

    reviewed = service.review_submission_batch(
        batch, budget_usd=Decimal("1.00"), runner=runner
    )
    reviewed_again = service.review_submission_batch(
        batch, budget_usd=Decimal("1.00"), runner=runner
    )

    assert captured[0].model_alias == "diagnosis"
    assert captured[1].context.run_id == captured[0].context.run_id
    assert captured[0].evidence_payload["submissions"][0]["snapshot"][
        "proposed_payload"
    ] == {"task_ids": [7]}
    action_schema = captured[0].output_schema["properties"]["proposed_actions"]
    assert "rationale" in action_schema["items"]["anyOf"][0]["required"]
    parsed_status, parsed_actions = AutonomousCodexRunner._parse_result(
        captured[0],
        json.dumps(
            {
                "status": "completed",
                "proposed_actions": [
                    {
                        "capability": "review_submission",
                        "resource": {
                            "kind": "pending_edit",
                            "identifier": str(row.id),
                            "exists": True,
                        },
                        "reason_code": "approve",
                        "rationale": "The snapshot links an existing task.",
                        "evidence": ["submission_snapshot"],
                        "confidence": 0.98,
                        "resolved_payload": {"task_ids": [7]},
                    }
                ],
            }
        ),
    )
    assert parsed_status == "completed"
    assert parsed_actions[0].resolved_payload == {"task_ids": [7]}
    assert reviewed[0].decision.decision == "approve"
    assert reviewed_again[0].decision == reviewed[0].decision
    claim = db.get(AutonomousSubmissionClaim, reviewed[0].claim_id)
    assert claim.review_run_id == captured[0].context.run_id
    assert (
        claim.attested_decision_digest
        == sha256(
            json.dumps(
                reviewed[0].decision.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def test_callback_rejects_expired_tampered_replayed_and_scope_expanding_payloads(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    _edit(db, "tasks", 1, payload={"task_ids": [7]})
    db.commit()
    applied = []
    service = _service(
        db, applied=lambda context, decision: applied.append((context, decision))
    )
    item = service.build_submission_manifest(
        service.claim_submission_batch(run_id, limit=1)
    )["items"][0]
    decision = AutonomousSubmissionDecision(
        claim_id=uuid.UUID(item["claim_id"]),
        decision="approve",
        rationale="The existing task ID matches the paper.",
        evidence=["submission_snapshot"],
        confidence=0.98,
        resolved_payload={"task_ids": [7]},
    )
    _attest(db, item["claim_id"], decision)

    with pytest.raises(AutonomousSubmissionCallbackError, match="token"):
        service.apply_submission_decision("tampered", decision)
    with pytest.raises(AutonomousSubmissionCallbackError, match="scope"):
        service.apply_submission_decision(
            item["callback_token"],
            decision.model_copy(update={"claim_id": uuid.uuid4()}),
        )
    with pytest.raises(AutonomousSubmissionCallbackError, match="expand"):
        service.apply_submission_decision(
            item["callback_token"],
            decision.model_copy(update={"resolved_payload": {"task_ids": [8]}}),
        )
    with pytest.raises(AutonomousSubmissionCallbackError, match="attested"):
        service.apply_submission_decision(
            item["callback_token"],
            decision.model_copy(update={"decision": "reject"}),
        )

    service.apply_submission_decision(item["callback_token"], decision)
    service.apply_submission_decision(item["callback_token"], decision)
    assert len(applied) == 1
    with pytest.raises(AutonomousSubmissionCallbackError, match="replay"):
        service.apply_submission_decision(
            item["callback_token"],
            decision.model_copy(update={"decision": "reject"}),
        )

    expired = _service(db)
    expired._clock = lambda: NOW + timedelta(hours=2)
    with pytest.raises(AutonomousSubmissionCallbackError, match="expired"):
        expired.apply_submission_decision(item["callback_token"], decision)


def test_expired_claim_can_be_reclaimed_by_same_run_without_unique_conflict(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    _edit(db, "repositories", 1)
    db.commit()
    first_service = _service(db)
    first = first_service.claim_submission_batch(run_id, limit=1)[0]
    second_service = AutonomousSubmissionService(
        db,
        signing_secret=b"test-signing-secret-with-sufficient-entropy",
        callback_base_url="https://paperswithcode.co/api/v1",
        clock=lambda: NOW + timedelta(hours=2),
    )

    second = second_service.claim_submission_batch(run_id, limit=1)[0]

    assert second.claim_id == first.claim_id
    assert second.callback_token != first.callback_token
    claim = db.get(AutonomousSubmissionClaim, second.claim_id)
    assert claim.review_run_id is None
    assert claim.attested_decision_digest is None
    assert db.query(AutonomousSubmissionClaim).count() == 1


def test_manifest_writer_is_exclusive_private_and_refuses_symlinks(db, tmp_path):
    path = tmp_path / "manifest.json"
    AutonomousSubmissionService.write_manifest(path, {"signed": True})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        AutonomousSubmissionService.write_manifest(path, {"replace": True})

    target = tmp_path / "target"
    target.write_text("untouched")
    link = tmp_path / "manifest-link"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        AutonomousSubmissionService.write_manifest(link, {"replace": True})
    assert target.read_text() == "untouched"


def test_database_free_remote_decision_requires_scoped_completion_signature(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    row = _edit(db, "tasks", 1, payload={"task_ids": [7]})
    db.commit()
    applied = []
    service = _service(
        db, applied=lambda context, decision: applied.append((context, decision))
    )
    batch = service.claim_submission_batch(run_id, limit=1)
    manifest = service.build_submission_manifest(batch)
    service.prepare_remote_review(batch, manifest)
    service.record_remote_job(batch, job_id="remote-job-1")
    decision = AutonomousSubmissionDecision(
        claim_id=batch[0].claim_id,
        decision="approve",
        rationale="The existing task identifier resolves.",
        evidence=["submission_snapshot"],
        confidence=0.99,
        resolved_payload={"task_ids": [7]},
    )
    usage = {"input_tokens": 100, "output_tokens": 20, "cost_usd": "0.01"}
    encoded_usage = base64.urlsafe_b64encode(
        json.dumps(usage, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    canonical = json.dumps(
        {"decision": decision.model_dump(mode="json"), "usage": usage},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    with pytest.raises(AutonomousSubmissionCallbackError, match="attested"):
        service.apply_submission_decision(batch[0].callback_token, decision)
    with pytest.raises(AutonomousSubmissionCallbackError, match="signature"):
        service.apply_submission_decision(
            batch[0].callback_token,
            decision,
            remote_signature="0" * 64,
            remote_usage=encoded_usage,
        )

    signature = hmac.new(
        batch[0].callback_token.encode(), canonical, sha256
    ).hexdigest()
    service.apply_submission_decision(
        batch[0].callback_token,
        decision,
        remote_signature=signature,
        remote_usage=encoded_usage,
    )

    claim = db.get(AutonomousSubmissionClaim, batch[0].claim_id)
    review_run = db.get(AutonomousRun, claim.review_run_id)
    assert claim.remote_job_id == "remote-job-1"
    assert claim.state == "completed"
    assert review_run.status == "completed"
    assert review_run.exit_classification == "completed"
    assert review_run.capability_requests[0]["reason_code"] == "approve"
    assert review_run.input_tokens == 100
    assert review_run.output_tokens == 20
    assert review_run.cost_usd == Decimal("0.01")
    assert applied[0][1] == decision
    assert db.get(PendingPaperEdit, row.id).status == "pending"


def test_human_only_must_defer_and_external_paper_cannot_request_enrichment(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    _edit(db, "new_task", 2)
    _edit(
        db, "new_external_paper", 1, payload={"source_url": "https://example.com/paper"}
    )
    db.commit()
    service = _service(db, applied=lambda _context, _decision: None)
    manifest = service.build_submission_manifest(
        service.claim_submission_batch(run_id, limit=2)
    )
    by_type = {item["snapshot"]["edit_type"]: item for item in manifest["items"]}

    taxonomy = by_type["new_task"]
    taxonomy_decision = AutonomousSubmissionDecision(
        claim_id=uuid.UUID(taxonomy["claim_id"]),
        decision="approve",
        rationale="not allowed",
        evidence=["submission_snapshot"],
        confidence=1,
    )
    with pytest.raises(AutonomousSubmissionCallbackError, match="defer"):
        service.apply_submission_decision(taxonomy["callback_token"], taxonomy_decision)

    external = by_type["new_external_paper"]
    external_decision = AutonomousSubmissionDecision(
        claim_id=uuid.UUID(external["claim_id"]),
        decision="approve",
        rationale="valid external release",
        evidence=["official_release"],
        confidence=0.99,
        resolved_payload={
            "source_url": "https://example.com/paper",
            "title": "Release",
            "date_published": "2026-08-28",
            "enrich": True,
        },
    )
    with pytest.raises(AutonomousSubmissionCallbackError, match="enrichment"):
        service.apply_submission_decision(external["callback_token"], external_decision)


def test_callback_route_is_disabled_by_default_and_requires_bearer_scope(
    db, monkeypatch
):
    claim_id = uuid.uuid4()
    body = {
        "claim_id": str(claim_id),
        "decision": "defer",
        "rationale": "Needs human judgment.",
        "evidence": ["submission_snapshot"],
        "confidence": 0.5,
    }
    app = FastAPI()
    app.include_router(pending_edits.router, prefix="/api/v1")
    app.dependency_overrides[get_database_session] = lambda: db
    app.dependency_overrides[get_settings] = lambda: Settings(
        autonomous_submission_enabled=False
    )
    client = TestClient(app)
    assert (
        client.post(
            f"/api/v1/autonomous-submissions/{claim_id}/decision", json=body
        ).status_code
        == 404
    )

    settings = Settings(
        autonomous_submission_enabled=True,
        autonomous_submission_callback_secret=("s" * 32),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    assert (
        client.post(
            f"/api/v1/autonomous-submissions/{claim_id}/decision", json=body
        ).status_code
        == 401
    )

    called = []
    monkeypatch.setattr(
        pending_edits,
        "apply_submission_callback",
        lambda *_args, **kwargs: called.append(kwargs),
    )
    response = client.post(
        f"/api/v1/autonomous-submissions/{claim_id}/decision",
        json=body,
        headers={"Authorization": "Bearer scoped-token"},
    )
    assert response.status_code == 204
    assert called[0]["claim_id"] == claim_id


def test_manual_mode_blocks_claiming_but_not_queue_visibility(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    row = _edit(db, "repositories", 1)
    db.get(AutonomousOperatorState, "global").manual_mode = True
    db.commit()

    with pytest.raises(ManualModeEnabled):
        _service(db).claim_submission_batch(run_id)

    assert _service(db).preview_submission_queue() == [
        {
            "pending_edit_id": row.id,
            "edit_type": "repositories",
            "required_decision": None,
        }
    ]
    assert db.get(PendingPaperEdit, row.id).status == "pending"
    assert db.query(AutonomousSubmissionClaim).count() == 0


def test_manual_mode_blocks_an_already_reviewed_callback(db):
    run_id = uuid.uuid4()
    _run(db, run_id)
    _edit(db, "repositories", 1)
    db.commit()
    service = _service(db, applied=lambda _context, _decision: None)
    item = service.build_submission_manifest(
        service.claim_submission_batch(run_id, limit=1)
    )["items"][0]
    decision = AutonomousSubmissionDecision(
        claim_id=uuid.UUID(item["claim_id"]),
        decision="defer",
        rationale="Manual mode must stop callback state changes.",
        evidence=["submission_snapshot"],
        confidence=1,
    )
    _attest(db, item["claim_id"], decision)
    db.get(AutonomousOperatorState, "global").manual_mode = True
    db.commit()

    with pytest.raises(ManualModeEnabled):
        service.apply_submission_decision(item["callback_token"], decision)

    claim = db.get(AutonomousSubmissionClaim, decision.claim_id)
    assert claim.state == "claimed"


def test_postgres_claiming_is_concurrent_and_migration_is_private(postgres_engine):
    first_run, second_run = uuid.uuid4(), uuid.uuid4()
    with Session(postgres_engine) as db:
        db.execute(
            text(
                "UPDATE autonomous_operator_state SET manual_mode=false; "
                "UPDATE autonomous_operator_state SET enabled=true "
                "WHERE operator='submissions'"
            )
        )
        _run(db, first_run)
        _run(db, second_run)
        for age in range(30):
            _edit(db, "repositories", age + 1)
        db.commit()

    barrier = Barrier(2)

    def claim(run_id):
        with Session(postgres_engine, expire_on_commit=False) as db:
            service = _service(db)
            barrier.wait()
            return {
                item.pending_edit_id
                for item in service.claim_submission_batch(run_id, limit=20)
            }

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(claim, first_run)
        second_future = executor.submit(claim, second_run)
        first, second = first_future.result(), second_future.result()

    assert first.isdisjoint(second)
    assert len(first | second) == 30
    with postgres_engine.connect() as connection:
        owner, acl = connection.execute(
            text(
                "SELECT relowner::regrole::text, coalesce(array_to_string(relacl, ','),'') "
                "FROM pg_class WHERE relname='autonomous_submission_claim'"
            )
        ).one()
    assert owner == "paperswithcode_user"
    assert not any(entry.startswith("=") for entry in acl.split(","))
