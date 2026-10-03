from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    CatalogAuditReadProgress,
    CatalogMutationEvent,
    CatalogMutationIdempotency,
)
from backend.services import catalog_mutation_service as module
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
)
from backend.services.catalog_errors import CatalogConflictError


@compiles(JSONB, "sqlite")
def compile_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


metadata = MetaData()
items = Table(
    "curated_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("value", String),
)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    CatalogMutationEvent.__table__.create(engine)
    CatalogMutationIdempotency.__table__.create(engine)
    CatalogAuditReadProgress.__table__.create(engine)
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: Settings(environment="production", release_id="test-release"),
    )
    with Session(engine) as session:
        yield session


def actor(role="contributor"):
    return {
        "hf_subject": f"{role}-subject",
        "username": role,
        "role": role,
    }


def snapshot(db: Session):
    row = db.execute(select(items.c.id, items.c.value)).first()
    return None if row is None else {"id": row.id, "value": row.value}


def mutate(db: Session, **overrides):
    values = {
        "actor": actor(),
        "operation": "create",
        "entity_type": "test",
        "entity_id": "1",
        "request_payload": {"value": "after"},
        "idempotency_key": "key-1",
        "expected_version": canonical_hash(None),
        "snapshot": lambda: snapshot(db),
        "apply": lambda: db.execute(items.insert().values(id=1, value="after")),
        "request_id": "request-1",
    }
    values.update(overrides)
    return CatalogMutationService(db).mutate(**values)


def test_forward_mutation_and_audit_commit_atomically(db):
    after, event, replayed = mutate(db)
    assert replayed is False
    assert after == {"id": 1, "value": "after"}
    assert event.before_snapshot is None
    assert db.query(CatalogMutationEvent).count() == 1
    assert db.query(CatalogMutationIdempotency).count() == 1


def test_failed_mutation_leaves_no_data_or_audit_event(db):
    def fail():
        db.execute(items.insert().values(id=1, value="partial"))
        raise ValueError("boom")

    with pytest.raises(ValueError):
        mutate(db, apply=fail)
    assert snapshot(db) is None
    assert db.query(CatalogMutationEvent).count() == 0


def test_idempotent_retry_returns_one_event_and_key_mismatch_conflicts(db):
    first_after, first_event, _ = mutate(db)
    second_after, second_event, replayed = mutate(
        db, apply=lambda: pytest.fail("retry applied mutation")
    )
    assert replayed is True
    assert second_after == first_after
    assert second_event.id == first_event.id
    assert db.query(CatalogMutationEvent).count() == 1
    with pytest.raises(CatalogConflictError) as error:
        mutate(db, request_payload={"value": "different"})
    assert str(error.value) == "Idempotency key was already used for another request"


def test_stale_version_conflicts_before_catalog_or_audit_write(db):
    with pytest.raises(CatalogConflictError) as error:
        mutate(db, expected_version="stale")
    assert error.value.detail["code"] == "stale_catalog_version"
    assert snapshot(db) is None
    assert db.query(CatalogMutationEvent).count() == 0


def test_section_version_can_exclude_related_audit_snapshot_state(db):
    def audit_snapshot():
        return {
            "section": snapshot(db),
            "related": {"global_state": "included-in-audit"},
        }

    after, event, _ = mutate(
        db,
        expected_version=canonical_hash(None),
        snapshot=audit_snapshot,
        version_snapshot=lambda: snapshot(db),
    )
    assert after["related"] == {"global_state": "included-in-audit"}
    assert event.before_snapshot["related"] == {"global_state": "included-in-audit"}


def test_admin_can_omit_contributor_headers(db):
    after, _, _ = mutate(
        db,
        actor=actor("admin"),
        idempotency_key=None,
        expected_version=None,
    )
    assert after["value"] == "after"


def test_history_is_actor_scoped_and_read_progress_is_separate(db):
    mutate(db)
    own = CatalogMutationService(db).list_events(
        actor_subject="contributor-subject", cursor=None, limit=10
    )
    other = CatalogMutationService(db).list_events(
        actor_subject="other", cursor=None, limit=10
    )
    assert len(own["events"]) == 1
    assert other["events"] == []
    service = CatalogMutationService(db)
    assert service.unread_count("admin-subject") == 1
    service.acknowledge("admin-subject")
    assert service.unread_count("admin-subject") == 0
    assert db.query(CatalogMutationEvent).count() == 1


def test_rollback_restores_prior_state_and_appends_linked_event(db):
    _, original, _ = mutate(db)
    service = CatalogMutationService(db)
    _, rollback, _ = service.mutate(
        actor=actor("admin"),
        operation="rollback",
        entity_type="test",
        entity_id="1",
        request_payload={"rollback_of": str(original.id)},
        idempotency_key=f"rollback:{original.id}",
        expected_version=canonical_hash(original.after_snapshot),
        snapshot=lambda: snapshot(db),
        apply=lambda: db.execute(items.delete().where(items.c.id == 1)),
        request_id="rollback-request",
        rollback_of_event_id=original.id,
    )
    assert snapshot(db) is None
    assert rollback.rollback_of_event_id == original.id
    assert db.query(CatalogMutationEvent).count() == 2


def test_rollback_refuses_to_overwrite_later_change(db):
    _, original, _ = mutate(db)
    db.execute(items.update().values(value="later"))
    db.commit()
    with pytest.raises(CatalogConflictError) as error:
        CatalogMutationService(db).mutate(
            actor=actor("admin"),
            operation="rollback",
            entity_type="test",
            entity_id="1",
            request_payload={"rollback_of": str(original.id)},
            idempotency_key=f"rollback:{original.id}",
            expected_version=canonical_hash(original.after_snapshot),
            snapshot=lambda: snapshot(db),
            apply=lambda: db.execute(items.delete().where(items.c.id == 1)),
            request_id="rollback-request",
            rollback_of_event_id=original.id,
        )
    assert error.value.detail["code"] == "stale_catalog_version"
    assert snapshot(db)["value"] == "later"
    assert db.query(CatalogMutationEvent).count() == 1


def test_audit_pagination_uses_opaque_cursor(db):
    mutate(db)
    db.execute(items.delete())
    db.commit()
    mutate(
        db,
        idempotency_key="key-2",
        request_payload={"value": "second"},
        request_id="request-2",
    )
    service = CatalogMutationService(db)
    first = service.list_events(actor_subject=None, cursor=None, limit=1)
    assert len(first["events"]) == 1
    assert first["next_cursor"]
    second = service.list_events(
        actor_subject=None, cursor=first["next_cursor"], limit=1
    )
    assert len(second["events"]) == 1
    assert second["events"][0]["id"] != first["events"][0]["id"]


def test_evaluation_route_preserves_concurrency_conflict(monkeypatch):
    from backend.routers import evaluations

    class ConflictingService:
        def __init__(self, _db):
            pass

        def delete(self, **_kwargs):
            raise HTTPException(
                status_code=409,
                detail={"code": "stale_catalog_version"},
            )

    monkeypatch.setattr(evaluations, "EvaluationCurationService", ConflictingService)
    with pytest.raises(HTTPException) as error:
        evaluations.delete_evaluation(1, mutation={}, db=None)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "stale_catalog_version"


def test_evaluation_batch_is_one_ordered_audit_mutation(monkeypatch):
    from backend.services import evaluation_curation_service as evaluation_module

    calls = []
    next_id = iter((101, 102))

    class Mutation:
        def __init__(self, _db):
            pass

        def mutate(self, **kwargs):
            calls.append(kwargs)
            kwargs["apply"]()
            return ([{"id": 101}, {"id": 102}], SimpleNamespace(id=uuid.uuid4()), False)

    service = evaluation_module.EvaluationCurationService(None)
    service.service = SimpleNamespace(
        create_evaluation=lambda **_kwargs: SimpleNamespace(id=next(next_id))
    )
    monkeypatch.setattr(evaluation_module, "CatalogMutationService", Mutation)
    operations = [
        {
            "operation": "create",
            "payload": {
                "paper_id": 7,
                "task_id": 1,
                "dataset_id": 1,
                "metrics": {"Accuracy": 0},
                "model_name": "a",
            },
        },
        {
            "operation": "create",
            "payload": {
                "paper_id": 7,
                "task_id": 1,
                "dataset_id": 1,
                "metrics": {"Accuracy": 1},
                "model_name": "b",
            },
        },
    ]
    result = service.batch(
        paper_id=7,
        operations=operations,
        mutation={
            "actor": actor(),
            "idempotency_key": "batch-key",
            "expected_version": "version",
            "request_id": "request",
        },
    )
    assert len(calls) == 1
    assert calls[0]["operation"] == "batch"
    assert calls[0]["request_payload"]["operations"] == operations
    assert result["result_ids"] == [101, 102]


def test_evaluation_batch_limit_applies_only_to_contributors(monkeypatch):
    from backend.services import evaluation_curation_service as evaluation_module

    calls = []

    class Mutation:
        def __init__(self, _db):
            pass

        def mutate(self, **kwargs):
            calls.append(kwargs)
            return ([], SimpleNamespace(id=uuid.uuid4()), False)

    monkeypatch.setattr(evaluation_module, "CatalogMutationService", Mutation)
    service = evaluation_module.EvaluationCurationService(None)
    operations = [{} for _ in range(51)]
    mutation = {
        "actor": actor(),
        "idempotency_key": "batch-key",
        "expected_version": "version",
        "request_id": "request",
    }
    with pytest.raises(ValueError, match="at most 50"):
        service.batch(paper_id=7, operations=operations, mutation=mutation)
    assert calls == []

    mutation["actor"] = actor("admin")
    service.batch(paper_id=7, operations=operations, mutation=mutation)
    assert len(calls) == 1
