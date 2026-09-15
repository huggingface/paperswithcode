"""Real transaction tests. Opt in with PWC_EDIT_TEST_DATABASE=pwc_agent_edits_test.

The dedicated database must already contain Base.metadata; this fixture refuses
any database outside the explicitly named test prefix. Never uses the live DB.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Base,
    PaperEditAuthorization,
    CatalogMutationEvent,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperProjectPage,
    PaperTask,
    ProjectPage,
    Task,
    TaskDatasetMetric,
)
from backend.models.paper_edits import PaperEditDocument
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogPermissionError,
    CatalogRateLimitError,
    CatalogValidationError,
)
from backend.services.paper_edit_access import PaperEditAccess
from backend.services.paper_edit_authorization import PaperEditAuthorizationService
from backend.services.paper_edit_service import PaperEditService

ACTOR = {
    "hf_subject": "edit-test",
    "username": "alice",
    "role": "contributor",
    "source": "cookie",
}
ADMIN = {"hf_subject": "admin", "username": "admin", "role": "admin"}


@pytest.fixture
def engine():
    name = os.environ.get("PWC_EDIT_TEST_DATABASE")
    if not name:
        pytest.skip(
            "Set PWC_EDIT_TEST_DATABASE to a dedicated PostgreSQL test database"
        )
    assert name.startswith("pwc_agent_edits_test"), "Refusing non-test database"
    engine = create_engine(make_url(get_settings().database_url).set(database=name))
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                + ", ".join(
                    engine.dialect.identifier_preparer.quote(table.name)
                    for table in Base.metadata.tables.values()
                )
                + " RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as db:
        db.add_all(
            [
                Paper(id=i, title=f"Paper {i}", arxiv_id=f"2609.{i:05}")
                for i in range(1, 24)
            ]
        )
        db.add(Task(id=1, name="Test task", slug="test-task"))
        db.add(Dataset(id=1, name="Test data", slug="test-data"))
        db.add(Metric(id=1, name="Accuracy", direction="higher_is_better"))
        db.flush()
        db.add(TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1))
        db.commit()
        yield db


def document(db, paper_id=1, operations=None):
    data = PaperEditService(db).export(paper_id)
    data["operations"] = operations or [
        {"section": "tasks", "payload": {"task_ids": [1]}}
    ]
    return PaperEditDocument.model_validate(data)


def test_preview_publish_retry_and_stale_edit(db):
    service = PaperEditService(db)
    doc = document(db)
    preview = service.submit(doc, ACTOR, "preview", preview=True)
    assert preview["before"] != preview["after"]
    assert db.query(PaperTask).count() == db.query(CatalogMutationEvent).count() == 0
    result = service.submit(doc, ACTOR, "submit")
    assert result["status"] == "published"
    assert db.query(PaperTask).count() == db.query(CatalogMutationEvent).count() == 1
    assert service.submit(doc, ACTOR, "retry")["replayed"]
    doc.idempotency_key = uuid.uuid4()
    with pytest.raises(CatalogConflictError):
        service.submit(doc, ACTOR, "stale")
    db.rollback()
    assert db.query(CatalogMutationEvent).count() == 1


def test_invalid_later_operation_rolls_back_everything(db):
    doc = document(
        db,
        operations=[
            {"section": "tasks", "payload": {"task_ids": [1]}},
            {"section": "methods", "payload": {"method_ids": [999999]}},
        ],
    )
    with pytest.raises(CatalogValidationError) as error:
        PaperEditService(db).submit(doc, ACTOR, "invalid")
    assert error.value.detail["errors"][0]["index"] == 1
    assert db.query(PaperTask).count() == db.query(CatalogMutationEvent).count() == 0


def test_authorization_one_use_scope_expiry_and_suspension(db):
    service = PaperEditAuthorizationService(db)
    start = service.start(1)
    assert service.exchange(start["device_code"])["status"] == "authorization_pending"
    service.approve(uuid.UUID(start["authorization_id"]), ACTOR)
    result = service.exchange(start["device_code"])
    actor = PaperEditAccess(db).authenticate(result["access_token"])
    with pytest.raises(CatalogPermissionError):
        service.exchange(start["device_code"])
    db.rollback()
    with pytest.raises(CatalogPermissionError):
        PaperEditService(db).submit(document(db, 2), actor, "wrong-paper")
    db.rollback()
    PaperEditAccess(db).suspend(ACTOR["hf_subject"], True, "admin")
    with pytest.raises(CatalogPermissionError):
        PaperEditService(db).submit(document(db), actor, "suspended")


def test_evaluation_batch_uses_existing_metrics_and_paper_scope(db):
    ops = [
        {
            "section": "evaluations",
            "payload": {
                "task_id": 1,
                "dataset_id": 1,
                "model_name": "Test",
                "metrics": {"Accuracy": 90},
            },
        }
    ]
    result = PaperEditService(db).submit(document(db, operations=ops), ACTOR, "eval")
    evaluation_id = result["after"]["evaluations"][0]["id"]
    assert db.query(Evaluation).count() == 1
    wrong = [
        {
            "section": "evaluations",
            "evaluation_id": evaluation_id,
            "payload": {"metrics": {"Accuracy": 95}},
        }
    ]
    with pytest.raises(CatalogValidationError):
        PaperEditService(db).submit(document(db, 2, wrong), ACTOR, "wrong-eval")
    db.rollback()
    assert db.get(Evaluation, evaluation_id).metrics == {"Accuracy": 90}
    ops[0]["payload"]["metrics"] = {"Unconfigured": 1}
    with pytest.raises(CatalogValidationError):
        PaperEditService(db).submit(document(db, operations=ops), ACTOR, "wrong-metric")
    assert db.query(Evaluation).count() == 1


def test_batch_rollback_and_subsequent_edit_conflict(db):
    service = PaperEditService(db)
    result = service.submit(document(db), ACTOR, "first")
    event = db.get(CatalogMutationEvent, uuid.UUID(result["event_id"]))
    service.rollback(event=event, actor=ADMIN, request_id="revert")
    assert db.query(PaperTask).count() == 0
    assert db.query(CatalogMutationEvent).count() == 2
    result = service.submit(document(db), ACTOR, "second")
    event = db.get(CatalogMutationEvent, uuid.UUID(result["event_id"]))
    service.submit(
        document(db, operations=[{"section": "tasks", "payload": {"task_ids": []}}]),
        ACTOR,
        "third",
    )
    with pytest.raises(CatalogConflictError):
        service.rollback(event=event, actor=ADMIN, request_id="conflict")


def test_shared_project_page_cannot_be_changed_on_another_paper(db):
    page = ProjectPage(url="https://example.org/project", is_official=False)
    db.add(page)
    db.flush()
    db.add(PaperProjectPage(paper_id=2, project_page_id=page.id))
    db.commit()
    ops = [
        {
            "section": "project_pages",
            "payload": {"project_pages": [{"url": page.url, "is_official": True}]},
        }
    ]
    with pytest.raises(CatalogValidationError):
        PaperEditService(db).submit(document(db, operations=ops), ACTOR, "shared")
    assert not db.get(ProjectPage, page.id).is_official


def test_concurrent_last_daily_slot_is_serialized(db, engine):
    now = datetime.now(UTC) - timedelta(minutes=2)
    db.add_all(
        CatalogMutationEvent(
            actor_hf_subject=ACTOR["hf_subject"],
            actor_username="alice",
            actor_role="contributor",
            operation="update",
            entity_type="paper_tasks",
            entity_id=str(i),
            paper_id=i,
            request_id="seed",
            source_environment="production",
            release_id="test",
            created_at=now,
        )
        for i in range(1, 20)
    )
    db.commit()
    barrier = Barrier(2)

    def publish(target):
        with Session(engine) as session:
            doc = document(session, target)
            barrier.wait(timeout=10)
            try:
                PaperEditService(session).submit(doc, ACTOR, "concurrent")
                return "published"
            except CatalogRateLimitError:
                return "limited"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, [20, 21]))
    assert sorted(results) == ["limited", "published"]
    assert db.query(CatalogMutationEvent).count() == 20


def test_website_mutations_share_quota_and_suspension(db):
    from backend.services.paper_curation_service import PaperCurationService

    service = PaperCurationService(db)
    version = service.state(1)["sections"]["tasks"]
    service.update(
        paper_id=1,
        section="tasks",
        payload={"task_ids": [1]},
        actor=ACTOR,
        idempotency_key="website",
        expected_version=version,
        request_id="website",
    )
    assert db.query(CatalogMutationEvent).one().paper_id == 1
    PaperEditAccess(db).suspend(ACTOR["hf_subject"], True, "admin")
    with pytest.raises(CatalogPermissionError):
        service.update(
            paper_id=2,
            section="tasks",
            payload={"task_ids": [1]},
            actor=ACTOR,
            idempotency_key="blocked",
            expected_version=service.state(2)["sections"]["tasks"],
            request_id="blocked",
        )


def test_public_history_scrubs_internal_snapshot_metadata_and_digest(db):
    from backend.services.paper_edit_history import PaperEditHistory

    PaperEditService(db).submit(document(db), ACTOR, "edit")
    history = PaperEditHistory(db).paper(1, None, 20)
    assert history["events"][0]["actor_username"] == "alice"
    assert "actor_hf_subject" not in history["events"][0]
    assert "related_project_pages" not in str(history)
    assert "evidence" not in str(history)
    digest = PaperEditHistory(db).digest(datetime.now(UTC).date(), 1)
    assert (digest["papers"], digest["contributors"], digest["edits"]) == (1, 1, 1)


def test_scoped_token_cannot_approve_another_authorization(db):
    service = PaperEditAuthorizationService(db)
    start = service.start(1)
    with pytest.raises(CatalogPermissionError):
        service.approve(
            uuid.UUID(start["authorization_id"]), dict(ACTOR, source="paper_token")
        )
    assert not db.get(
        PaperEditAuthorization, uuid.UUID(start["authorization_id"])
    ).approved_at


def test_http_browser_consent_and_scoped_bearer_flow(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from backend.config import Settings
    from backend.database import connection
    from backend.routers import (
        auth,
        paper_edits,
        datasets,
        tasks,
        methods,
        organizations,
        repositories,
    )
    from backend.routers.catalog_error_handlers import register_catalog_error_handlers
    from backend.utils import auth as auth_utils
    from backend.utils.csrf import cookie_request_passes_csrf

    settings = Settings(
        environment="production",
        jwt_secret="test-secret-32-characters-long-enough",
        contributor_direct_edits_enabled=True,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_utils, "get_settings", lambda: settings)

    def session():
        yield db

    app = FastAPI()
    app.include_router(paper_edits.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    for module in (datasets, tasks, methods, organizations, repositories):
        app.include_router(module.router, prefix="/api/v1")
    shared_writes = [
        ("POST", "/api/v1/datasets/"),
        ("PUT", "/api/v1/datasets/1"),
        ("POST", "/api/v1/tasks/"),
        ("POST", "/api/v1/methods/1/keywords"),
        ("POST", "/api/v1/organizations/sync"),
        ("POST", "/api/v1/project-pages/"),
        ("DELETE", "/api/v1/project-pages/1"),
    ]
    register_catalog_error_handlers(app)
    app.dependency_overrides[connection.get_database_session] = session
    monkeypatch.setattr(connection, "get_database_session", session)

    @app.middleware("http")
    async def csrf(request, call_next):
        if not cookie_request_passes_csrf(request, settings):
            return JSONResponse({"detail": "csrf"}, status_code=403)
        return await call_next(request)

    with TestClient(app, base_url="https://paperswithcode.co") as browser:
        start = browser.post("/api/v1/paper-edit-authorizations", json={"paper_id": 1})
        assert start.status_code == 200
        assert start.headers["cache-control"] == "no-store"
        data = start.json()
        path = f"/api/v1/paper-edit-authorizations/{data['authorization_id']}/approve"
        assert browser.post(path).status_code == 401
        cookie = auth._encode_session(
            {"sub": ACTOR["hf_subject"], "username": ACTOR["username"]}
        )
        browser.cookies.set(auth.session_cookie_name(), cookie)
        assert browser.get("/api/v1/auth/me").json()["can_directly_edit_catalog"]
        for method, shared_path in shared_writes:
            assert (
                browser.request(
                    method,
                    shared_path,
                    json={},
                    headers={
                        "Origin": "https://paperswithcode.co",
                    },
                ).status_code
                == 401
            )
        assert browser.post(path).status_code == 403  # no same-origin header
        assert (
            browser.post(
                path, headers={"Origin": "https://paperswithcode.co"}
            ).status_code
            == 200
        )
        browser.cookies.clear()
        token = browser.post(
            "/api/v1/paper-edit-authorizations/token",
            json={"device_code": data["device_code"]},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for method, shared_path in shared_writes:
            assert (
                browser.request(
                    method, shared_path, json={}, headers=headers
                ).status_code
                == 403
            )
        exported = browser.get("/api/v1/papers/1/edit-document", headers=headers)
        assert exported.status_code == 200
        doc = exported.json()
        doc["operations"] = [{"section": "tasks", "payload": {"task_ids": [1]}}]
        assert (
            browser.post(
                "/api/v1/papers/1/edits/preview", headers=headers, json=doc
            ).status_code
            == 200
        )
        assert (
            browser.post("/api/v1/papers/1/edits", headers=headers, json=doc).json()[
                "status"
            ]
            == "published"
        )
        assert (
            browser.get("/api/v1/papers/2/edit-document", headers=headers).status_code
            == 403
        )
        assert (
            browser.post("/api/v1/paper-edit-logout", headers=headers).status_code
            == 204
        )
        assert (
            browser.get("/api/v1/papers/1/edit-document", headers=headers).status_code
            == 403
        )


def test_rollback_restores_nonempty_metadata_and_evaluations(db):
    service = PaperEditService(db)
    initial = [
        {"section": "tasks", "payload": {"task_ids": [1]}},
        {
            "section": "evaluations",
            "payload": {
                "task_id": 1,
                "dataset_id": 1,
                "model_name": "Initial",
                "metrics": {"Accuracy": 90},
            },
        },
    ]
    original = service.submit(document(db, operations=initial), ACTOR, "seed")
    evaluation_id = original["after"]["evaluations"][0]["id"]
    changed = service.submit(
        document(
            db,
            operations=[
                {"section": "tasks", "payload": {"task_ids": []}},
                {
                    "section": "evaluations",
                    "evaluation_id": evaluation_id,
                    "payload": {"metrics": {"Accuracy": 95}},
                },
            ],
        ),
        ACTOR,
        "change",
    )
    event = db.get(CatalogMutationEvent, uuid.UUID(changed["event_id"]))
    service.rollback(event=event, actor=ADMIN, request_id="restore")
    assert db.query(PaperTask).one().task_id == 1
    assert db.get(Evaluation, evaluation_id).metrics == {"Accuracy": 90}


def test_expiry_during_application_rolls_back_before_publication(db, monkeypatch):
    from datetime import timedelta

    auth = PaperEditAuthorizationService(db)
    start = auth.start(1)
    grant_id = uuid.UUID(start["authorization_id"])
    auth.approve(grant_id, ACTOR)
    credentials = auth.exchange(start["device_code"])
    actor = PaperEditAccess(db).authenticate(credentials["access_token"])
    service = PaperEditService(db)
    original_apply = service.apply

    def expire_during_apply(*args):
        original_apply(*args)
        db.get(PaperEditAuthorization, grant_id).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
        db.flush()

    monkeypatch.setattr(service, "apply", expire_during_apply)
    with pytest.raises(CatalogPermissionError):
        service.submit(document(db), actor, "expired-before-commit")
    assert db.query(PaperTask).count() == 0
    assert db.query(CatalogMutationEvent).count() == 0


def test_other_paper_rank_changes_do_not_invalidate_edits_or_rollback(db):
    from backend.services.contribution_audit_service import ContributionAuditService

    service = PaperEditService(db)

    def evaluation(score):
        return [
            {
                "section": "evaluations",
                "payload": {
                    "task_id": 1,
                    "dataset_id": 1,
                    "model_name": "Test",
                    "metrics": {"Accuracy": score},
                    "best_metric": "Accuracy",
                },
            }
        ]

    service.submit(document(db, operations=evaluation(90)), ACTOR, "original")
    doc = document(db)
    service.submit(document(db, 2, evaluation(95)), ACTOR, "other-paper")
    row = db.query(Evaluation).filter(Evaluation.paper_id == 1).one()
    assert row.best_rank == 2
    row.updated_at = datetime.now(UTC) + timedelta(seconds=1)
    db.commit()
    assert service.export(1)["version"] == doc.version
    assert service.submit(doc, ACTOR, "preview", preview=True)["status"] == "preview"
    published = service.submit(doc, ACTOR, "publish")
    event = db.get(CatalogMutationEvent, uuid.UUID(published["event_id"]))
    service.submit(document(db, 3, evaluation(99)), ACTOR, "another-paper")
    assert ContributionAuditService(db).is_rollback_eligible(event)
    service.rollback(event=event, actor=ADMIN, request_id="rollback")
    assert db.query(PaperTask).filter(PaperTask.paper_id == 1).count() == 0
    assert db.query(Evaluation).filter(Evaluation.paper_id == 1).one().best_rank == 3


def test_actual_evaluation_changes_still_invalidate_edit_document(db):
    service = PaperEditService(db)
    db.add(
        Evaluation(
            paper_id=1,
            task_id=1,
            dataset_id=1,
            model_name="Old",
            metrics={"Accuracy": 90},
        )
    )
    db.commit()
    doc = document(db)
    row = db.query(Evaluation).one()
    row.metrics = {"Accuracy": 95}
    db.commit()
    with pytest.raises(CatalogConflictError):
        service.submit(doc, ACTOR, "stale")
