from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    CatalogMutationEvent,
    CatalogMutationIdempotency,
    PaperEditAccount,
)
from backend.models.database import Paper as DBPaper
from backend.routers.papers import UpdateDocumentTypeRequest
from backend.services import catalog_mutation_service as catalog_mutation_module
from backend.services.catalog_errors import CatalogConflictError
from backend.services.catalog_mutation_service import canonical_hash
from backend.services.paper_curation_service import PaperCurationService

ADMIN = {"hf_subject": "admin-subject", "username": "admin", "role": "admin"}


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    for model in (
        DBPaper,
        PaperEditAccount,
        CatalogMutationEvent,
        CatalogMutationIdempotency,
    ):
        model.__table__.create(engine)
    monkeypatch.setattr(
        catalog_mutation_module,
        "get_settings",
        lambda: Settings(environment="production", release_id="test-release"),
    )
    with Session(engine) as session:
        session.add(
            DBPaper(
                id=1,
                arxiv_id="2607.24653",
                source="arxiv",
                version="v1",
                is_latest_version=True,
                title="Kimi K3: Open Frontier Intelligence",
                date_published=date(2026, 7, 27),
            )
        )
        session.commit()
        yield session


def _service(db):
    service = PaperCurationService(db)
    service.paper_service.get_paper_by_id = lambda paper_id, **_: paper_id
    return service


def _version(service):
    return canonical_hash(service.snapshot(1, "document_type"))


def _set(service, value, *, version=None, key="set"):
    service.update(
        paper_id=1,
        section="document_type",
        payload={"document_type": value},
        actor=ADMIN,
        idempotency_key=key,
        expected_version=version,
        request_id=key,
    )


def test_admin_sets_document_type_and_rolls_it_back(db):
    service = _service(db)
    version = _version(service)

    _set(service, "Technical Report", version=version)
    assert db.get(DBPaper, 1).document_type == "Technical Report"
    assert _version(service) != version

    event = db.query(CatalogMutationEvent).one()
    assert event.entity_type == "paper_document_type"
    assert event.before_snapshot["value"] is None
    assert event.after_snapshot["value"] == "Technical Report"

    service.rollback(event=event, actor=ADMIN, request_id="undo")
    db.commit()
    assert db.get(DBPaper, 1).document_type is None


def test_stale_version_is_rejected(db):
    service = _service(db)
    stale = _version(service)
    _set(service, "System Card", key="first")
    with pytest.raises(CatalogConflictError):
        _set(service, "Technical Report", version=stale, key="second")
    assert db.get(DBPaper, 1).document_type == "System Card"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Technical   Report ", "Technical Report"),
        ("   ", None),
        (None, None),
    ],
)
def test_request_normalizes_whitespace_and_blank_clears(raw, expected):
    assert UpdateDocumentTypeRequest(document_type=raw).document_type == expected


def test_request_rejects_long_types():
    with pytest.raises(ValidationError):
        UpdateDocumentTypeRequest(document_type="x" * 51)
