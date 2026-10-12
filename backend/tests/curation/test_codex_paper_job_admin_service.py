from __future__ import annotations

import asyncio
import threading
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.config import get_settings
from backend.models.database import Paper, PaperCurationJob
from backend.routers import codex_add_evals, codex_enrich_paper
from backend.services.codex_paper_job_admin_service import (
    CodexPaperJobAdminService,
    CodexPaperJobNotFoundError,
    CodexPaperJobsDisabledError,
    CodexPaperNotFoundError,
)


def _settings(*, enabled: bool = True):
    return get_settings().model_copy(update={"codex_jobs_enabled": enabled})


class _PaperQuery:
    def __init__(self, paper):
        self.paper = paper

    def filter(self, *_criteria):
        return self

    def one_or_none(self):
        return self.paper


class _Database:
    def __init__(self, *, paper=None, job_row=None):
        self.paper = paper
        self.job_row = job_row
        self.queries = []
        self.gets = []

    def query(self, model):
        self.queries.append(model)
        return _PaperQuery(self.paper)

    def get(self, model, key):
        self.gets.append((model, key))
        return self.job_row


class _JobService:
    def __init__(self, *, job=None):
        self.job = job
        self.calls = []

    def enqueue(self, db, **kwargs):
        self.calls.append(("enqueue", db, kwargs))
        return self.job

    def get(self, db, job_id, settings):
        self.calls.append(("get", db, job_id, settings))
        return self.job

    def cancel(self, db, row, settings):
        self.calls.append(("cancel", db, row, settings))
        return self.job


@pytest.mark.parametrize("kind", ["add-evals", "enrich-paper"])
def test_start_job_owns_exact_paper_projection_and_kind(kind):
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2601.00042",
        title="A useful paper",
    )
    db = _Database(paper=paper)
    expected_job = object()
    jobs = _JobService(job=expected_job)

    result = CodexPaperJobAdminService(db, job_service=jobs).start(
        kind=kind,
        paper_id=42,
        requested_by="admin",
        settings=_settings(),
    )

    assert result is expected_job
    assert db.queries == [Paper]
    assert jobs.calls == [
        (
            "enqueue",
            db,
            {
                "kind": kind,
                "paper_id": 42,
                "paper_route": "2601.00042",
                "paper_title": "A useful paper",
                "requested_by": "admin",
                "settings": _settings(),
            },
        )
    ]


def test_disabled_and_missing_paper_fail_before_job_enqueue():
    db = _Database()
    jobs = _JobService()
    service = CodexPaperJobAdminService(db, job_service=jobs)

    with pytest.raises(CodexPaperJobsDisabledError, match="^Not found$"):
        service.start(
            kind="add-evals",
            paper_id=42,
            requested_by="admin",
            settings=_settings(enabled=False),
        )
    assert db.queries == []

    with pytest.raises(CodexPaperNotFoundError, match="^Paper not found$"):
        service.start(
            kind="add-evals",
            paper_id=42,
            requested_by="admin",
            settings=_settings(),
        )
    assert jobs.calls == []


def test_get_and_cancel_preserve_job_service_lifecycle():
    job_id = uuid.uuid4()
    row = object()
    job = object()
    db = _Database(job_row=row)
    jobs = _JobService(job=job)
    service = CodexPaperJobAdminService(db, job_service=jobs)
    settings = _settings()

    assert service.get(job_id, settings) is job
    assert service.cancel(job_id, settings) is job
    assert db.gets == [(PaperCurationJob, job_id)]
    assert jobs.calls == [
        ("get", db, job_id, settings),
        ("cancel", db, row, settings),
    ]


def test_missing_get_and_cancel_keep_exact_job_error():
    job_id = uuid.uuid4()
    settings = _settings()
    with pytest.raises(CodexPaperJobNotFoundError, match="^Job not found$"):
        CodexPaperJobAdminService(_Database(), job_service=_JobService()).get(
            job_id, settings
        )
    with pytest.raises(CodexPaperJobNotFoundError, match="^Job not found$"):
        CodexPaperJobAdminService(_Database(), job_service=_JobService()).cancel(
            job_id, settings
        )


@pytest.mark.parametrize(
    ("router_module", "request_model", "kind"),
    [
        (codex_add_evals, codex_add_evals.StartCodexAddEvalsRequest, "add-evals"),
        (
            codex_enrich_paper,
            codex_enrich_paper.StartCodexEnrichPaperRequest,
            "enrich-paper",
        ),
    ],
)
def test_both_start_routes_remain_thin_kind_specific_adapters(
    monkeypatch, router_module, request_model, kind
):
    calls = []
    expected = object()

    class Service:
        def __init__(self, db, *, job_service):
            calls.append(("init", db, job_service))

        def start(self, **kwargs):
            calls.append(("start", kwargs))
            return expected

    monkeypatch.setattr(router_module, "CodexPaperJobAdminService", Service)
    result = asyncio.run(
        router_module.start_job(
            request_model(paper_id=42),
            {"username": "admin"},
            object(),
            _settings(),
        )
    )

    assert result is expected
    assert calls[1][1]["kind"] == kind
    assert calls[1][1]["paper_id"] == 42
    assert calls[1][1]["requested_by"] == "admin"


@pytest.mark.parametrize(
    ("router_module", "service_error", "detail"),
    [
        (codex_add_evals, CodexPaperJobsDisabledError("Not found"), "Not found"),
        (
            codex_enrich_paper,
            CodexPaperNotFoundError("Paper not found"),
            "Paper not found",
        ),
    ],
)
def test_start_routes_translate_domain_errors_exactly(
    monkeypatch, router_module, service_error, detail
):
    class Service:
        def __init__(self, _db, *, job_service):
            pass

        def start(self, **_kwargs):
            raise service_error

    monkeypatch.setattr(router_module, "CodexPaperJobAdminService", Service)
    request_model = (
        codex_add_evals.StartCodexAddEvalsRequest
        if router_module is codex_add_evals
        else codex_enrich_paper.StartCodexEnrichPaperRequest
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router_module.start_job(
                request_model(paper_id=42),
                {"username": "admin"},
                object(),
                _settings(),
            )
        )

    assert error.value.status_code == 404
    assert error.value.detail == detail


@pytest.mark.parametrize("router_module", [codex_add_evals, codex_enrich_paper])
@pytest.mark.parametrize("operation", ["start", "get", "cancel"])
def test_blocking_job_operations_run_off_the_event_loop(
    monkeypatch, router_module, operation
):
    calls = []

    class Service:
        def __getattr__(self, name):
            def blocking_operation(*args, **kwargs):
                calls.append((name, threading.get_ident()))
                raise (
                    CodexPaperJobNotFoundError("Job not found")
                    if name != "start"
                    else CodexPaperNotFoundError("Paper not found")
                )

            return blocking_operation

    monkeypatch.setattr(router_module, "_service", lambda db: Service())

    async def invoke():
        loop_thread = threading.get_ident()
        with pytest.raises(HTTPException) as error:
            if operation == "start":
                await router_module.start_job(
                    SimpleNamespace(paper_id=42),
                    {"username": "admin"},
                    object(),
                    _settings(),
                )
            else:
                await getattr(router_module, operation + "_job")(
                    uuid.uuid4(), {}, object(), _settings()
                )
        assert error.value.status_code == 404
        assert calls[0][0] == operation
        assert calls[0][1] != loop_thread

    asyncio.run(invoke())
