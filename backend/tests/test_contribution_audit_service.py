"""Focused contracts for contribution admin-audit ownership."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from backend.config import Settings
from backend.models.database import (
    PaperEditAccount,
    CatalogAuditReadProgress,
    CatalogMutationEvent,
    CatalogMutationIdempotency,
    Metric,
    TaskDatasetMetric,
)
from backend.routers import contributions
from backend.services import catalog_mutation_service as catalog_mutation_module
from backend.services import contribution_audit_service as audit_module
from backend.services.contribution_audit_service import ContributionAuditService
from backend.services.contribution_audit_service import (
    ContributionAuditEventNotFoundError,
    ContributionAuditRollbackError,
)
from backend.services.pending_edit_snapshots import PendingEditSnapshotService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


ADMIN = {
    "hf_subject": "admin-subject",
    "username": "admin",
    "role": "admin",
}


def _event(**overrides):
    values = {
        "id": uuid.uuid4(),
        "actor_hf_subject": "contributor-subject",
        "paper_id": 7,
        "operation": "update",
        "entity_type": "paper_tasks",
        "entity_id": "7",
        "after_snapshot": {"value": [{"task_id": 3}]},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_admin_audit_page_enriches_events_in_page_order(monkeypatch):
    first = _event()
    second = _event()
    page = {
        "events": [{"id": str(first.id)}, {"id": str(second.id)}],
        "next_cursor": "next-page",
    }
    calls = []

    class Query:
        def filter(self, *_conditions):
            calls.append(("filter",))
            return self

        def all(self):
            calls.append(("all",))
            return (
                []
                if getattr(self, "model", None) is PaperEditAccount
                else [second, first]
            )

    class Database:
        def query(self, model):
            calls.append(("query", model))
            query = Query()
            query.model = model
            return query

    class MutationService:
        def __init__(self, db):
            calls.append(("mutation-service", db))

        def list_events(self, *, actor_subject, cursor, limit):
            calls.append(("list", actor_subject, cursor, limit))
            return page

        def unread_count(self, admin_subject):
            calls.append(("unread", admin_subject))
            return 4

    db = Database()
    monkeypatch.setattr(audit_module, "CatalogMutationService", MutationService)
    service = ContributionAuditService(db)

    def eligible(event):
        calls.append(("eligible", event))
        return event is first

    monkeypatch.setattr(service, "is_rollback_eligible", eligible)

    result = service.list_admin_audit(
        admin_subject="admin-subject", cursor="cursor", limit=12
    )

    assert result is page
    assert result == {
        "events": [
            {
                "id": str(first.id),
                "rollback_eligible": True,
                "actor_hf_subject": "contributor-subject",
                "editing_suspended": False,
                "paper_id": 7,
            },
            {
                "id": str(second.id),
                "rollback_eligible": False,
                "actor_hf_subject": "contributor-subject",
                "editing_suspended": False,
                "paper_id": 7,
            },
        ],
        "next_cursor": "next-page",
        "unread_contributor_count": 4,
    }
    assert calls == [
        ("mutation-service", db),
        ("list", None, "cursor", 12),
        ("query", CatalogMutationEvent),
        ("filter",),
        ("all",),
        ("query", PaperEditAccount),
        ("filter",),
        ("all",),
        ("eligible", first),
        ("eligible", second),
        ("unread", "admin-subject"),
    ]


def test_paper_eligibility_uses_section_snapshot_and_canonical_comparison(monkeypatch):
    calls = []
    current = {
        "value": [{"task_id": 3}],
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    class PaperService:
        def __init__(self, db):
            calls.append(("init", db))

        def snapshot(self, paper_id, section):
            calls.append(("snapshot", paper_id, section))
            return current

    db = object()
    monkeypatch.setattr(audit_module, "PaperCurationService", PaperService)
    service = ContributionAuditService(db)
    event = _event(
        entity_type="paper_tasks",
        entity_id="7",
        after_snapshot={
            "updated_at": "2026-01-01 00:00:00+00:00",
            "value": [{"task_id": 3}],
        },
    )

    assert service.is_rollback_eligible(event) is True
    event.after_snapshot = {"value": []}
    assert service.is_rollback_eligible(event) is False
    assert calls == [
        ("init", db),
        ("snapshot", 7, "tasks"),
        ("init", db),
        ("snapshot", 7, "tasks"),
    ]


@pytest.mark.parametrize(
    ("entity_id", "expected_call"),
    [
        ("9", ("snapshot", 9)),
        ("paper:9", ("paper-evaluations", 9)),
    ],
)
def test_evaluation_eligibility_preserves_row_and_collection_paths(
    monkeypatch, entity_id, expected_call
):
    calls = []
    current = [{"id": 1}] if entity_id.startswith("paper:") else {"id": 9}

    class EvaluationService:
        def __init__(self, db):
            calls.append(("init", db))

        def snapshot(self, evaluation_id):
            calls.append(("snapshot", evaluation_id))
            return current

        def paper_evaluations(self, paper_id):
            calls.append(("paper-evaluations", paper_id))
            return current

    db = object()
    monkeypatch.setattr(audit_module, "EvaluationCurationService", EvaluationService)
    event = _event(
        entity_type="evaluation",
        entity_id=entity_id,
        after_snapshot=current,
    )

    assert ContributionAuditService(db).is_rollback_eligible(event) is True
    assert calls == [("init", db), expected_call]


def test_submission_eligibility_passes_the_original_event(monkeypatch):
    calls = []
    event = _event(
        entity_type="submission_created_metric",
        entity_id="11",
        after_snapshot={"entity": {"id": 11}},
    )

    class SubmissionService:
        def __init__(self, db):
            calls.append(("init", db))

        def snapshot(self, received_event):
            calls.append(("snapshot", received_event))
            return {"entity": {"id": 11}}

    db = object()
    monkeypatch.setattr(audit_module, "SubmissionRollbackService", SubmissionService)

    assert ContributionAuditService(db).is_rollback_eligible(event) is True
    assert calls == [("init", db), ("snapshot", event)]


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid entity id"),
        PaperNotFoundError("missing paper"),
        DatabaseError("missing row"),
    ],
)
def test_eligibility_fails_closed_for_existing_snapshot_errors(monkeypatch, error):
    class PaperService:
        def __init__(self, _db):
            pass

        def snapshot(self, _paper_id, _section):
            raise error

    monkeypatch.setattr(audit_module, "PaperCurationService", PaperService)

    assert ContributionAuditService(object()).is_rollback_eligible(_event()) is False


@pytest.mark.parametrize(
    "event",
    [
        _event(operation="rollback"),
        _event(entity_type="unrelated_entity"),
    ],
)
def test_ineligible_event_kinds_do_not_load_live_snapshots(monkeypatch, event):
    class UnexpectedService:
        def __init__(self, _db):
            pytest.fail("ineligible event loaded a snapshot service")

    monkeypatch.setattr(audit_module, "PaperCurationService", UnexpectedService)
    monkeypatch.setattr(audit_module, "EvaluationCurationService", UnexpectedService)
    monkeypatch.setattr(audit_module, "SubmissionRollbackService", UnexpectedService)

    assert ContributionAuditService(object()).is_rollback_eligible(event) is False


@pytest.mark.parametrize(
    ("stored_event", "error_type", "detail"),
    [
        (None, ContributionAuditEventNotFoundError, "Audit event not found"),
        (
            _event(operation="rollback"),
            ContributionAuditRollbackError,
            "Rollback events cannot be rolled back",
        ),
        (
            _event(entity_type="unsupported"),
            ContributionAuditRollbackError,
            "This event type is not rollback eligible",
        ),
    ],
)
def test_rollback_rejections_preserve_exact_status_and_detail(
    monkeypatch, stored_event, error_type, detail
):
    calls = []
    event_id = stored_event.id if stored_event is not None else uuid.uuid4()

    class Database:
        def get(self, model, key):
            calls.append(("get", model, key))
            return stored_event

        def commit(self):
            pytest.fail("rejected rollback committed")

        def rollback(self):
            pytest.fail("rejected rollback opened a transaction boundary")

    class UnexpectedService:
        def __init__(self, _db):
            pytest.fail("rejected rollback constructed a mutation service")

    monkeypatch.setattr(audit_module, "EvaluationCurationService", UnexpectedService)
    monkeypatch.setattr(audit_module, "PaperCurationService", UnexpectedService)
    monkeypatch.setattr(audit_module, "SubmissionRollbackService", UnexpectedService)

    with pytest.raises(error_type, match=f"^{detail}$"):
        ContributionAuditService(Database()).rollback_event(
            event_id=event_id,
            actor=ADMIN,
            request_id="request-id",
        )

    assert calls == [("get", CatalogMutationEvent, event_id)]


@pytest.mark.parametrize(
    ("entity_type", "target_service"),
    [
        ("evaluation", "EvaluationCurationService"),
        ("paper_tasks", "PaperCurationService"),
        ("submission_created_metric", "SubmissionRollbackService"),
    ],
)
def test_rollback_dispatch_commits_before_serialization_without_extra_boundary(
    monkeypatch, entity_type, target_service
):
    calls = []
    event = _event(entity_type=entity_type)
    rollback = _event(operation="rollback", rollback_of_event_id=event.id)

    class Database:
        def get(self, model, key):
            calls.append(("get", model, key))
            return event

        def commit(self):
            calls.append(("commit",))

        def rollback(self):
            calls.append(("database-rollback",))

    db = Database()

    class UnexpectedService:
        def __init__(self, _db):
            pytest.fail("rollback was dispatched to the wrong service")

    class RollbackService:
        def __init__(self, received_db):
            calls.append(("service", target_service, received_db))
            self.db = received_db

        def rollback(self, *, event, actor, request_id):
            calls.append(("rollback", event, actor, request_id))
            self.db.commit()
            return rollback

    class MutationService:
        @staticmethod
        def serialize_event(received_event):
            calls.append(("serialize", received_event))
            return {"id": str(received_event.id)}

    for service_name in (
        "EvaluationCurationService",
        "PaperCurationService",
        "SubmissionRollbackService",
    ):
        monkeypatch.setattr(audit_module, service_name, UnexpectedService)
    monkeypatch.setattr(audit_module, target_service, RollbackService)
    monkeypatch.setattr(audit_module, "CatalogMutationService", MutationService)

    result = ContributionAuditService(db).rollback_event(
        event_id=event.id,
        actor=ADMIN,
        request_id="request-id",
    )

    assert result == {"id": str(rollback.id)}
    assert calls == [
        ("get", CatalogMutationEvent, event.id),
        ("service", target_service, db),
        ("rollback", event, ADMIN, "request-id"),
        ("commit",),
        ("serialize", rollback),
    ]


def test_rollback_failure_propagates_after_one_delegate_rollback(monkeypatch):
    calls = []
    event = _event(entity_type="paper_tasks")

    class Database:
        def get(self, model, key):
            calls.append(("get", model, key))
            return event

        def rollback(self):
            calls.append(("database-rollback",))

    db = Database()

    class PaperService:
        def __init__(self, received_db):
            calls.append(("service", received_db))
            self.db = received_db

        def rollback(self, *, event, actor, request_id):
            calls.append(("rollback", event, actor, request_id))
            self.db.rollback()
            raise DatabaseError("rollback failed")

    class MutationService:
        @staticmethod
        def serialize_event(_event):
            pytest.fail("failed rollback was serialized")

    monkeypatch.setattr(audit_module, "PaperCurationService", PaperService)
    monkeypatch.setattr(audit_module, "CatalogMutationService", MutationService)

    with pytest.raises(DatabaseError, match="rollback failed"):
        ContributionAuditService(db).rollback_event(
            event_id=event.id,
            actor=ADMIN,
            request_id="request-id",
        )

    assert calls == [
        ("get", CatalogMutationEvent, event.id),
        ("service", db),
        ("rollback", event, ADMIN, "request-id"),
        ("database-rollback",),
    ]


def test_acknowledge_delegates_the_only_commit(monkeypatch):
    calls = []

    class Database:
        def commit(self):
            calls.append(("commit",))

    db = Database()

    class MutationService:
        def __init__(self, received_db):
            calls.append(("service", received_db))
            self.db = received_db

        def acknowledge(self, admin_subject):
            calls.append(("acknowledge", admin_subject))
            self.db.commit()

    monkeypatch.setattr(audit_module, "CatalogMutationService", MutationService)

    ContributionAuditService(db).acknowledge("admin-subject")

    assert calls == [
        ("service", db),
        ("acknowledge", "admin-subject"),
        ("commit",),
    ]


def test_router_delegates_http_inputs_and_request_id(monkeypatch):
    calls = []
    db = object()
    event_id = uuid.uuid4()

    class AuditService:
        def __init__(self, received_db):
            calls.append(("service", received_db))

        def list_admin_audit(self, **kwargs):
            calls.append(("list", kwargs))
            return {"events": []}

        def acknowledge(self, admin_subject):
            calls.append(("acknowledge", admin_subject))

        def rollback_event(self, **kwargs):
            calls.append(("rollback", kwargs))
            return {"operation": "rollback"}

    monkeypatch.setattr(contributions, "ContributionAuditService", AuditService)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/catalog-audit/event/rollback",
            "headers": [(b"x-request-id", b"header-request-id")],
        }
    )

    assert contributions.catalog_audit(
        cursor="cursor", limit=7, actor=ADMIN, db=db
    ) == {"events": []}
    assert contributions.acknowledge_catalog_audit(actor=ADMIN, db=db) is None
    assert contributions.rollback_catalog_event(
        event_id=event_id,
        request=request,
        actor=ADMIN,
        db=db,
    ) == {"operation": "rollback"}
    assert calls == [
        ("service", db),
        (
            "list",
            {
                "admin_subject": "admin-subject",
                "cursor": "cursor",
                "limit": 7,
            },
        ),
        ("service", db),
        ("acknowledge", "admin-subject"),
        ("service", db),
        (
            "rollback",
            {
                "event_id": event_id,
                "actor": ADMIN,
                "request_id": "header-request-id",
            },
        ),
    ]


def test_router_preserves_request_identity_fallback(monkeypatch):
    captured = {}

    class AuditService:
        def __init__(self, _db):
            pass

        def rollback_event(self, **kwargs):
            captured.update(kwargs)
            return {}

    monkeypatch.setattr(contributions, "ContributionAuditService", AuditService)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/catalog-audit/event/rollback",
            "headers": [],
        }
    )

    contributions.rollback_catalog_event(
        event_id=uuid.uuid4(), request=request, actor=ADMIN, db=object()
    )

    assert captured["request_id"] == str(id(request))


@pytest.mark.parametrize(
    ("service_error", "status_code"),
    [
        (ContributionAuditEventNotFoundError("Audit event not found"), 404),
        (
            ContributionAuditRollbackError("This event type is not rollback eligible"),
            409,
        ),
    ],
)
def test_router_translates_audit_domain_errors(monkeypatch, service_error, status_code):
    class AuditService:
        def __init__(self, _db):
            pass

        def rollback_event(self, **_kwargs):
            raise service_error

    monkeypatch.setattr(contributions, "ContributionAuditService", AuditService)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/catalog-audit/event/rollback",
            "headers": [],
        }
    )

    with pytest.raises(HTTPException) as error:
        contributions.rollback_catalog_event(
            event_id=uuid.uuid4(), request=request, actor=ADMIN, db=object()
        )

    assert error.value.status_code == status_code
    assert error.value.detail == str(service_error)


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def collect(dependant) -> None:
        for child in dependant.dependencies:
            names.add(getattr(child.call, "__name__", type(child.call).__name__))
            collect(child)

    collect(route.dependant)
    return names


def test_admin_audit_routes_and_authorization_dependencies_are_unchanged():
    routes = {
        (method, route.path): route
        for route in contributions.router.routes
        for method in route.methods
    }
    expected = {
        ("GET", "/admin/catalog-audit"),
        ("POST", "/admin/catalog-audit/acknowledge"),
        ("POST", "/admin/catalog-audit/{event_id}/rollback"),
    }

    assert expected.issubset(routes)
    for key in expected:
        assert "require_admin" in _dependency_names(routes[key])
    assert routes[("POST", "/admin/catalog-audit/acknowledge")].status_code == 204


@pytest.fixture
def audit_db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    for model in (
        PaperEditAccount,
        Metric,
        TaskDatasetMetric,
        CatalogMutationEvent,
        CatalogMutationIdempotency,
        CatalogAuditReadProgress,
    ):
        model.__table__.create(engine)
    monkeypatch.setattr(
        catalog_mutation_module,
        "get_settings",
        lambda: Settings(environment="production", release_id="test-release"),
    )
    with Session(engine) as session:
        yield session


def _seed_created_metric_event(db: Session) -> CatalogMutationEvent:
    db.add(Metric(id=11, name="Accuracy", direction="higher_is_better"))
    db.commit()
    after = PendingEditSnapshotService(db).created_entity("metric", 11)
    event = CatalogMutationEvent(
        id=uuid.uuid4(),
        actor_hf_subject="contributor-subject",
        actor_username="contributor",
        actor_role="contributor",
        operation="create",
        entity_type="submission_created_metric",
        entity_id="11",
        before_snapshot={},
        after_snapshot=after,
        request_id="create-request",
        source_environment="production",
        release_id="test-release",
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    return event


def test_admin_page_and_acknowledgement_preserve_persisted_read_progress(audit_db):
    event = _seed_created_metric_event(audit_db)
    service = ContributionAuditService(audit_db)

    page = service.list_admin_audit(
        admin_subject="admin-subject", cursor=None, limit=25
    )

    assert page["next_cursor"] is None
    assert page["unread_contributor_count"] == 1
    assert page["events"] == [
        {
            "id": str(event.id),
            "actor_username": "contributor",
            "actor_hf_subject": "contributor-subject",
            "editing_suspended": False,
            "paper_id": None,
            "actor_role": "contributor",
            "operation": "create",
            "entity_type": "submission_created_metric",
            "entity_id": "11",
            "before": {},
            "after": event.after_snapshot,
            "created_at": event.created_at,
            "rollback_of_event_id": None,
            "rollback_eligible": True,
        }
    ]

    service.acknowledge("admin-subject")

    assert audit_db.get(CatalogAuditReadProgress, "admin-subject") is not None
    acknowledged_page = service.list_admin_audit(
        admin_subject="admin-subject", cursor=None, limit=25
    )
    assert acknowledged_page["unread_contributor_count"] == 0


def test_submission_rollback_preserves_append_only_persisted_history(audit_db):
    original = _seed_created_metric_event(audit_db)

    result = ContributionAuditService(audit_db).rollback_event(
        event_id=original.id,
        actor=ADMIN,
        request_id="rollback-request",
    )

    assert audit_db.get(Metric, 11) is None
    events = (
        audit_db.query(CatalogMutationEvent)
        .order_by(CatalogMutationEvent.created_at)
        .all()
    )
    assert len(events) == 2
    rollback = next(event for event in events if event.operation == "rollback")
    assert rollback.rollback_of_event_id == original.id
    assert rollback.before_snapshot == original.after_snapshot
    assert rollback.after_snapshot == {}
    assert rollback.request_id == "rollback-request"
    assert result == {
        "id": str(rollback.id),
        "actor_username": "admin",
        "actor_role": "admin",
        "operation": "rollback",
        "entity_type": "submission_created_metric",
        "entity_id": "11",
        "before": original.after_snapshot,
        "after": {},
        "created_at": rollback.created_at,
        "rollback_of_event_id": str(original.id),
    }
    idempotency = audit_db.get(
        CatalogMutationIdempotency,
        ("admin-subject", f"rollback:{original.id}"),
    )
    assert idempotency is not None
    assert idempotency.event_id == rollback.id


def test_stale_submission_rollback_writes_nothing(audit_db):
    original = _seed_created_metric_event(audit_db)
    metric = audit_db.get(Metric, 11)
    metric.description = "changed after the audited event"
    audit_db.commit()

    from backend.services.catalog_errors import CatalogConflictError

    with pytest.raises(CatalogConflictError) as error:
        ContributionAuditService(audit_db).rollback_event(
            event_id=original.id,
            actor=ADMIN,
            request_id="rollback-request",
        )

    assert set(error.value.detail) == {"code", "current_version"}
    assert error.value.detail["code"] == "stale_catalog_version"
    assert audit_db.get(Metric, 11).description == "changed after the audited event"
    assert audit_db.query(CatalogMutationEvent).count() == 1
    assert audit_db.query(CatalogMutationIdempotency).count() == 0
