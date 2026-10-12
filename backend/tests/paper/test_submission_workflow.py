"""Characterization contracts for the public paper-submission workflow."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from backend.models.papers import Paper
from backend.routers import papers as papers_router
from backend.routers.papers import PaperSubmitRequest, PaperSubmitResponse
from backend.services import paper_ingestion_service as ingestion_module
from backend.services import paper_submission_service as submission_module
from backend.services.paper_ingestion_service import PaperIngestionError
from backend.services.paper_version_refresh_service import ArxivPaperRefreshResult
from backend.services.pending_edit_errors import (
    PendingEditError,
    SubmissionRateLimitError,
    SubmissionSuspendedError,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError

USER = {
    "username": "submitter",
    "hf_subject": "hf-subject",
    "role": "user",
}
DEFAULT_DB = object()


def _paper(
    *, paper_id: str = "17", arxiv_id: str | None = "2605.18736", version="v2"
) -> Paper:
    return Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        title="A Paper",
        authors=["Ada Lovelace"],
        version=version,
    )


def _request(*, headers=(), client=("127.0.0.1", 12345)) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/papers/submit",
            "headers": list(headers),
            "client": client,
        }
    )


def _submit(
    payload: PaperSubmitRequest,
    *,
    user: dict = USER,
    idempotency_key: str | None = None,
    response: Response | None = None,
    request: Request | None = None,
    db=DEFAULT_DB,
) -> PaperSubmitResponse:
    return asyncio.run(
        papers_router.submit_paper(
            http_request=request or _request(),
            response=response or Response(),
            request=payload,
            idempotency_key=idempotency_key,
            user=user,
            db=db,
        )
    )


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def collect(dependant) -> None:
        for child in dependant.dependencies:
            names.add(getattr(child.call, "__name__", type(child.call).__name__))
            collect(child)

    collect(route.dependant)
    return names


def test_submit_route_models_path_and_auth_are_stable():
    route = next(
        route for route in papers_router.router.routes if route.path == "/papers/submit"
    )

    assert route.methods == {"POST"}
    assert route.response_model is PaperSubmitResponse
    assert "require_user" in _dependency_names(route)


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (
            PaperSubmitRequest(arxiv_id="  ", source_url=" "),
            "Provide an ArXiv ID or a paper URL to submit.",
        ),
        (
            PaperSubmitRequest(arxiv_id=" https://arxiv.org/abs/2605.18736 "),
            "Invalid ArXiv ID: https://arxiv.org/abs/2605.18736",
        ),
        (
            PaperSubmitRequest(arxiv_id="not-an-id"),
            "Invalid ArXiv ID: not-an-id",
        ),
    ],
)
def test_transport_validation_errors_are_exact(payload, detail):
    with pytest.raises(HTTPException) as error:
        _submit(payload)

    assert error.value.status_code == 400
    assert error.value.detail == detail


def test_staging_rejects_arxiv_url_before_catalog_access(monkeypatch):
    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="staging"),
    )

    class UnexpectedPaperService:
        def __init__(self, _db):
            pytest.fail("staging ArXiv submission accessed the catalog")

    monkeypatch.setattr(submission_module, "PaperService", UnexpectedPaperService)

    with pytest.raises(HTTPException) as error:
        _submit(
            PaperSubmitRequest(source_url=" https://arxiv.org/pdf/2605.18736v3.pdf ")
        )

    assert error.value.status_code == 403
    assert error.value.detail == (
        "ArXiv submissions mutate the canonical catalog and are disabled on "
        "staging. External paper URLs may still be queued for staging-local review."
    )


def test_existing_arxiv_submission_normalizes_and_refreshes(monkeypatch):
    calls = []
    existing = _paper(version="v1")
    refreshed = _paper(version="v3")

    class PaperService:
        def __init__(self, db):
            calls.append(("service", db))

        def get_paper_by_arxiv_id(self, arxiv_id, version):
            calls.append(("get", arxiv_id, version))
            return existing

        async def refresh_arxiv_paper(self, arxiv_id):
            calls.append(("refresh", arxiv_id))
            return ArxivPaperRefreshResult(
                paper=refreshed,
                created=True,
                refreshed=True,
                previous_version="v1",
                latest_version="v3",
            )

    db = object()
    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)

    result = _submit(
        PaperSubmitRequest(
            arxiv_id=" 2605.18736v7 ",
            source_url="https://example.com/ignored",
            title="Ignored",
        ),
        db=db,
    )

    assert result == PaperSubmitResponse(
        paper=refreshed,
        route_identifier="2605.18736",
        created=True,
        refreshed=True,
        previous_version="v1",
        latest_version="v3",
    )
    assert calls == [
        ("service", db),
        ("get", "2605.18736", None),
        ("refresh", "2605.18736"),
    ]


def test_existing_refresh_uses_internal_route_identifier_fallback(monkeypatch):
    paper = _paper(paper_id="91", arxiv_id=None)

    class PaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_arxiv_id(self, _arxiv_id, version):
            assert version is None
            return paper

        async def refresh_arxiv_paper(self, _arxiv_id):
            return ArxivPaperRefreshResult(
                paper=paper,
                created=False,
                refreshed=False,
                previous_version="v2",
                latest_version="v2",
            )

    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)

    result = _submit(PaperSubmitRequest(arxiv_id="2605.18736"))

    assert result.route_identifier == "91"
    assert result.created is False
    assert result.refreshed is False


def test_lookup_database_error_remains_a_database_error(monkeypatch):
    class PaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_arxiv_id(self, _arxiv_id, version):
            assert version is None
            raise DatabaseError("lookup failed")

    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)

    with pytest.raises(DatabaseError, match="lookup failed"):
        _submit(PaperSubmitRequest(arxiv_id="2605.18736"))


@pytest.mark.parametrize(
    ("error_type", "status_code", "detail"),
    [
        (
            "rate_limited",
            429,
            "arXiv is rate-limiting indexing right now. Try again in a few minutes.",
        ),
        (
            "not_found",
            404,
            "Paper with ArXiv ID 2605.18736 was not found on arXiv.",
        ),
        (
            "temporary_failure",
            502,
            "Could not fetch metadata from arXiv right now. Try again in a few minutes.",
        ),
        (
            "response_error",
            502,
            "arXiv returned an invalid metadata response. Try again in a few minutes.",
        ),
        (
            "db_error",
            500,
            "Failed to add paper to database (may already exist)",
        ),
        (
            "unknown",
            502,
            "Could not fetch metadata from arXiv right now. Try again in a few minutes.",
        ),
    ],
)
def test_arxiv_metadata_error_compatibility_mapping(error_type, status_code, detail):
    error = papers_router._arxiv_metadata_error("2605.18736", error_type)

    assert error.status_code == status_code
    assert error.detail == detail


@pytest.mark.parametrize("message", ["write failed", "arxiv_metadata_error:"])
def test_refresh_database_errors_preserve_existing_http_mapping(monkeypatch, message):
    class PaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_arxiv_id(self, _arxiv_id, version):
            assert version is None
            return _paper()

        async def refresh_arxiv_paper(self, _arxiv_id):
            raise DatabaseError(message)

    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)

    with pytest.raises(HTTPException) as error:
        _submit(PaperSubmitRequest(arxiv_id="2605.18736"))

    if message.startswith("arxiv_metadata_error:"):
        assert error.value.status_code == 502
        assert error.value.detail == (
            "Could not fetch metadata from arXiv right now. Try again in a few minutes."
        )
    else:
        assert error.value.status_code == 500
        assert error.value.detail == "Internal server error"


def test_new_arxiv_submission_ingests_hydrates_and_logs(monkeypatch):
    calls = []
    paper = _paper(version="v4")

    class PaperService:
        def __init__(self, db):
            self.db = db

        def get_paper_by_arxiv_id(self, arxiv_id, version):
            calls.append(("get", arxiv_id, version))
            raise PaperNotFoundError("not indexed")

        def get_paper_by_id(self, paper_id, include_resources):
            calls.append(("hydrate", paper_id, include_resources))
            return paper

    async def ingest(service, arxiv_id):
        calls.append(("ingestion-service", service.db))
        calls.append(("ingest", arxiv_id))
        return SimpleNamespace(id=17), True

    timestamps = iter((10.0, 10.125))
    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)
    monkeypatch.setattr(ingestion_module, "PaperService", PaperService)
    monkeypatch.setattr(
        ingestion_module.PaperIngestionService,
        "get_or_import_arxiv_paper",
        ingest,
    )
    monkeypatch.setattr(
        ingestion_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(timestamps)),
    )
    monkeypatch.setattr(
        papers_router.logger,
        "info",
        lambda *args: calls.append(("log", *args)),
    )
    db = object()

    result = _submit(
        PaperSubmitRequest(
            source_url="https://arxiv.org/html/2605.18736v9",
        ),
        db=db,
    )

    assert result == PaperSubmitResponse(
        paper=paper,
        route_identifier="2605.18736",
        created=True,
        refreshed=False,
        latest_version="v4",
    )
    assert calls == [
        ("get", "2605.18736", None),
        ("ingestion-service", db),
        ("ingest", "2605.18736"),
        ("hydrate", 17, True),
        (
            "log",
            "arxiv_indexing_result arxiv_id=%s source_endpoint=%s result=success elapsed_ms=%d fallback_used=%s",
            "2605.18736",
            "submit",
            125,
            False,
        ),
    ]


def test_arxiv_ingestion_failure_maps_and_logs(monkeypatch):
    calls = []

    class PaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_arxiv_id(self, _arxiv_id, version):
            assert version is None

    async def ingest(_service, arxiv_id):
        raise PaperIngestionError(arxiv_id, "not_found")

    timestamps = iter((20.0, 20.042))
    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)
    monkeypatch.setattr(
        ingestion_module.PaperIngestionService,
        "get_or_import_arxiv_paper",
        ingest,
    )
    monkeypatch.setattr(
        ingestion_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(timestamps)),
    )
    monkeypatch.setattr(
        papers_router.logger,
        "info",
        lambda *args: calls.append(args),
    )

    with pytest.raises(HTTPException) as error:
        _submit(PaperSubmitRequest(arxiv_id="2605.18736"))

    assert error.value.status_code == 404
    assert error.value.detail == (
        "Paper with ArXiv ID 2605.18736 was not found on arXiv."
    )
    assert calls == [
        (
            "arxiv_indexing_result arxiv_id=%s source_endpoint=%s result=%s elapsed_ms=%d fallback_used=%s",
            "2605.18736",
            "submit",
            "not_found",
            42,
            False,
        )
    ]


def test_unexpected_ingestion_failure_preserves_wrapped_500(monkeypatch):
    class PaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_arxiv_id(self, _arxiv_id, version):
            assert version is None
            raise PaperNotFoundError("not indexed")

    async def ingest(_service, _arxiv_id):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(submission_module, "PaperService", PaperService)
    monkeypatch.setattr(
        ingestion_module.PaperIngestionService,
        "get_or_import_arxiv_paper",
        ingest,
    )

    with pytest.raises(HTTPException) as error:
        _submit(PaperSubmitRequest(arxiv_id="2605.18736"))

    assert error.value.status_code == 500
    assert error.value.detail == "Internal server error"


@pytest.mark.parametrize(
    ("role", "exempt"),
    [("user", False), ("contributor", True), ("admin", True)],
)
def test_external_submission_constructs_exact_pending_edit(monkeypatch, role, exempt):
    calls = []
    submitted = SimpleNamespace(id=42)

    class PendingService:
        def __init__(self, db):
            calls.append(("service", db))

        def submit(self, **kwargs):
            calls.append(("submit", kwargs))
            return submitted

    monkeypatch.setattr(submission_module, "PendingEditService", PendingService)
    monkeypatch.setattr(
        submission_module,
        "get_settings",
        lambda: pytest.fail("external submission inspected the environment"),
    )
    user = {**USER, "role": role}
    db = object()

    result = _submit(
        PaperSubmitRequest(
            source_url=" https://example.com/paper ",
            title="Title",
            abstract="Abstract",
            authors=["Ada", "Grace"],
            date_published=date(2026, 8, 10),
        ),
        user=user,
        idempotency_key="same-request",
        request=_request(headers=((b"x-real-ip", b"203.0.113.8"),)),
        db=db,
    )

    assert result == PaperSubmitResponse(
        created=False,
        submission_id=42,
        pending_review=True,
    )
    assert calls == [
        ("service", db),
        (
            "submit",
            {
                "paper_id": None,
                "hf_username": "submitter",
                "hf_subject": "hf-subject",
                "source_ip": "203.0.113.8",
                "idempotency_key": "same-request",
                "exempt_from_limits": exempt,
                "edit_type": "new_external_paper",
                "proposed_payload": {
                    "source_url": "https://example.com/paper",
                    "title": "Title",
                    "abstract": "Abstract",
                    "authors": ["Ada", "Grace"],
                    "date_published": "2026-08-10",
                },
            },
        ),
    ]


def test_external_submission_normalizes_optional_payload_defaults(monkeypatch):
    captured = {}

    class PendingService:
        def __init__(self, _db):
            pass

        def submit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id=7)

    monkeypatch.setattr(submission_module, "PendingEditService", PendingService)

    result = _submit(PaperSubmitRequest(source_url="https://example.com/paper"))

    assert captured["proposed_payload"] == {
        "source_url": "https://example.com/paper",
        "title": None,
        "abstract": None,
        "authors": [],
        "date_published": None,
    }
    assert result.submission_id == 7


def test_external_rate_limit_preserves_detail_and_headers(monkeypatch):
    class PendingService:
        def __init__(self, _db):
            pass

        def submit(self, **_kwargs):
            raise SubmissionRateLimitError(
                "Hourly account submission limit reached", retry_after=73
            )

    monkeypatch.setattr(submission_module, "PendingEditService", PendingService)
    response = Response()

    with pytest.raises(HTTPException) as error:
        _submit(
            PaperSubmitRequest(source_url="https://example.com/paper"),
            response=response,
        )

    expected_headers = {
        "content-length": "0",
        "retry-after": "73",
        "ratelimit": "0",
        "ratelimit-policy": "submission;w=3600",
    }
    assert error.value.status_code == 429
    assert error.value.detail == (
        "Hourly account submission limit reached. See /rate-limits for help."
    )
    assert error.value.headers == expected_headers
    assert dict(response.headers) == expected_headers


@pytest.mark.parametrize(
    ("service_error", "status_code", "detail"),
    [
        (
            SubmissionSuspendedError("This account cannot create new submissions"),
            403,
            "This account cannot create new submissions",
        ),
        (
            PendingEditError("Submission payload is too large"),
            400,
            "Submission payload is too large",
        ),
    ],
)
def test_external_rejections_preserve_status_and_detail(
    monkeypatch, service_error, status_code, detail
):
    class PendingService:
        def __init__(self, _db):
            pass

        def submit(self, **_kwargs):
            raise service_error

    monkeypatch.setattr(submission_module, "PendingEditService", PendingService)

    with pytest.raises(HTTPException) as error:
        _submit(PaperSubmitRequest(source_url="https://example.com/paper"))

    assert error.value.status_code == status_code
    assert error.value.detail == detail


def test_unexpected_pending_edit_error_still_propagates(monkeypatch):
    class PendingService:
        def __init__(self, _db):
            pass

        def submit(self, **_kwargs):
            raise RuntimeError("unexpected persistence failure")

    monkeypatch.setattr(submission_module, "PendingEditService", PendingService)

    with pytest.raises(RuntimeError, match="unexpected persistence failure"):
        _submit(PaperSubmitRequest(source_url="https://example.com/paper"))
