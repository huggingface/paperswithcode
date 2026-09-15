"""Permission/limit boundaries shared by browser and CLI writes."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    CatalogMutationEvent,
    PaperEditAccount,
    PaperEditAuthorization,
)
from backend.services.catalog_errors import (
    CatalogPermissionError,
    CatalogRateLimitError,
)
from backend.services.paper_edit_access import PaperEditAccess, token_hash


@compiles(JSONB, "sqlite")
def jsonb_sqlite(*args, **kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for model in (CatalogMutationEvent, PaperEditAccount, PaperEditAuthorization):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session


def actor(**kw):
    return dict(hf_subject="alice", username="alice", role="contributor", **kw)


def event(paper_id, when):
    return CatalogMutationEvent(
        actor_hf_subject="alice",
        actor_username="alice",
        actor_role="contributor",
        paper_id=paper_id,
        operation="update",
        entity_type="paper_tasks",
        entity_id=str(paper_id),
        request_id="test",
        source_environment="production",
        release_id="test",
        created_at=when,
    )


def test_twenty_distinct_papers_shared_across_sessions(db):
    now = datetime.now(UTC)
    db.add_all(event(i, now) for i in range(1, 21))
    db.commit()
    access = PaperEditAccess(db)
    access.check_write(actor(), 20, "paper_tasks", "update", {}, now=now)
    with pytest.raises(CatalogRateLimitError):
        access.check_write(actor(), 21, "paper_tasks", "update", {}, now=now)
    access.check_write(
        dict(actor(), role="admin"), 21, "paper_tasks", "update", {}, now=now
    )


def test_quota_resets_at_utc_midnight(db):
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    db.add_all(event(i, now - timedelta(seconds=1)) for i in range(1, 21))
    db.commit()
    PaperEditAccess(db).check_write(actor(), 21, "paper_tasks", "update", {}, now=now)


def test_scope_and_deletion_cannot_be_bypassed(db):
    access = PaperEditAccess(db)
    with pytest.raises(CatalogPermissionError):
        access.check_write(actor(paper_id=1), 2, "evaluation", "update", {})
    for operation, payload in [
        ("delete", {}),
        ("batch", {"operations": [{"operation": "delete"}]}),
    ]:
        with pytest.raises(CatalogPermissionError):
            access.check_write(actor(), 1, "evaluation", operation, payload)
    with pytest.raises(CatalogPermissionError):
        access.check_write(actor(), 1, "organization", "update", {})


def test_suspension_denies_cookie_and_active_token_and_does_not_revive(db):
    now = datetime.now(UTC)
    grant = PaperEditAuthorization(
        paper_id=1,
        device_hash=token_hash("device"),
        token_hash=token_hash("token"),
        expires_at=now + timedelta(hours=1),
        hf_subject="alice",
        username="alice",
        approved_at=now,
        created_at=now,
    )
    db.add(grant)
    db.commit()
    access = PaperEditAccess(db)
    assert access.authenticate("token")["paper_id"] == 1
    access.suspend("alice", True, "admin")
    with pytest.raises(CatalogPermissionError):
        access.authenticate("token")
    with pytest.raises(CatalogPermissionError):
        access.check_write(actor(), 1, "paper_tasks", "update", {})
    access.suspend("alice", False, "admin")
    with pytest.raises(CatalogPermissionError):
        access.authenticate("token")


def test_expired_authorization_denied(db):
    db.add(
        PaperEditAuthorization(
            paper_id=1,
            device_hash=token_hash("d"),
            token_hash=token_hash("t"),
            hf_subject="alice",
            username="alice",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    db.commit()
    with pytest.raises(CatalogPermissionError):
        PaperEditAccess(db).authenticate("t")


def test_write_rate_limit_and_admin_exemption(db):
    now = datetime.now(UTC)
    db.add_all(event(1, now) for _ in range(30))
    db.commit()
    with pytest.raises(CatalogRateLimitError):
        PaperEditAccess(db).check_write(
            actor(), 1, "paper_tasks", "update", {}, now=now
        )
    PaperEditAccess(db).check_write(
        dict(actor(), role="admin"), 1, "paper_tasks", "update", {}, now=now
    )
