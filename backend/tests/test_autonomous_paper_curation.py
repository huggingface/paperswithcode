from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import sys
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.scripts import enqueue_hf_daily_paper_curation as curation_cli
from backend.models.database import (
    AutonomousOperatorState,
    AutonomousRun,
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Metric,
    Paper,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
    Task,
    TaskDataset,
)
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)
from backend.services.codex_add_evals_service import (
    CanaryDispatchFailed,
    CodexPaperJobService,
    curation_dispatch_lock,
    _is_callback_validation_rejection,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.curation_trace_service import (
    CurationTraceService,
    redact_trace,
    trace_json,
)
from backend.services.hf_daily_curation_service import (
    HFDailyCurationService,
    _dispatched_canary_workflows,
    _MAX_AUTOMATIC_RETRIES,
    paper_markdown_available,
)
from jobs import url_preflight


class _HeadResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _context(*, project_page: bool = True) -> dict:
    return {
        "paper": {
            "id": 42,
            "arxiv_id": "2608.00042",
            "abstract": "A paper without inline links.",
            "repositories": [
                {
                    "url": "https://github.com/example/project",
                    "is_official": True,
                    "source": "hf_api",
                }
            ],
            "project_pages": (
                [
                    {
                        "url": "https://example.github.io/project",
                        "is_official": True,
                        "source": "hf_api",
                    }
                ]
                if project_page
                else []
            ),
        }
    }


def test_url_patterns_are_the_authoritative_design_patterns():
    assert url_preflight.GITHUB_URL_PATTERN == r"\bhttps?:\/\/github\.com[^\s]*\b"
    assert (
        url_preflight.PROJECT_PAGE_URL_PATTERN
        == r"\bhttps?:\/\/[^\s\/]+\.github\.io[^\s]*\b"
    )


def test_normalize_candidate_ignores_malformed_markdown_link_url():
    assert (
        url_preflight.normalize_candidate(
            "https://odensenlp.github.io](https://odensenlp.github.io"
        )
        is None
    )


def test_preflight_reuses_complete_importer_links_but_verifies_markdown(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    fetched = []

    def fetch(url, _limit):
        fetched.append(url)
        assert url.endswith(".md")
        return b"# Paper\n", url

    result = url_preflight.extract_candidates(_context(), fetch=fetch)

    assert result["complete"] is True
    assert result["markdown_available"] is True
    assert fetched == ["https://huggingface.co/papers/2608.00042.md"]
    assert {item["kind"] for item in result["candidates"]} == {"github", "project_page"}
    assert all("hf_api" in item["source_layers"][0] for item in result["candidates"])


def test_eval_preflight_manifests_model_card_blog_project_and_readme(monkeypatch):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context()
    context["paper"]["source_url"] = "https://example.com/official-blog"
    context["source_candidate"] = {
        "repo_id": "org/model",
        "model_card_url": "https://huggingface.co/org/model/raw/revision/README.md",
    }

    result = url_preflight.extract_candidates(
        context,
        fetch=lambda url, _limit: (b"# Paper\n", url),
    )

    assert {(item["kind"], item["url"]) for item in result["source_documents"]} == {
        ("paper_source", "https://example.com/official-blog"),
        (
            "model_card",
            "https://huggingface.co/org/model/raw/revision/README.md",
        ),
        ("github_readme", "https://github.com/example/project"),
        ("project_page", "https://example.github.io/project"),
        ("paper_markdown", "https://huggingface.co/papers/2608.00042.md"),
    }


def test_preflight_accepts_official_links_when_markdown_is_not_ready(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return json.dumps(
                {
                    "githubRepo": "https://github.com/example/project",
                    "projectPage": "https://example.github.io/project",
                }
            ).encode(), url
        assert url.endswith(".md")
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["awaiting_markdown"] is False
    assert result["complete"] is True
    assert fetched == [
        "https://huggingface.co/api/papers/2608.00042",
        "https://huggingface.co/papers/2608.00042.md",
    ]
    assert result["sources"][0]["sha256"]


def test_preflight_uses_discovered_project_candidate_for_conditional_html(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    context["paper"]["abstract"] = "Project: https://demo.github.io/paper"
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return b"", url
        if "/pdf/" in url:
            raise ValueError("fixture has no PDF")
        assert url == "https://demo.github.io/paper"
        return b'<a href="https://github.com/example/discovered">code</a>', url

    result = url_preflight.extract_candidates(context, fetch=fetch)

    assert "https://demo.github.io/paper" in fetched
    assert any(
        item["normalized_url"] == "https://github.com/example/discovered"
        and "project_page_html" in item["source_layers"]
        for item in result["candidates"]
    )


def test_preflight_uses_ocr_markdown_when_public_markdown_is_unavailable(
    monkeypatch,
):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        raise AssertionError("OCR Markdown must avoid the PDF fallback")

    def fetch_ocr_markdown(arxiv_id: str, _limit: int, *, token: str):
        assert arxiv_id == "2608.00042"
        assert token == "hf-test"
        return (
            b"Code: https://github.com/example/project\n"
            b"Project: https://example.github.io/project\n",
            "https://signed.example/markdown",
        )

    result = url_preflight.extract_candidates(
        _context(project_page=False),
        fetch=fetch,
        fetch_ocr_markdown=fetch_ocr_markdown,
    )

    assert result["complete"] is True
    assert {source["source"] for source in result["sources"]} == {
        "hf_api",
        "ocr_markdown",
    }
    assert not result["errors"]
    assert not any("/pdf/" in url for url in fetched)


def test_preflight_does_not_fetch_pdf_when_hf_markdown_is_available(monkeypatch):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return b"# Complete paper\n", url
        raise AssertionError("PDF is a last-resort source")

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["complete"] is True
    assert not any("/pdf/" in url for url in fetched)


def test_preflight_skips_pdf_when_official_repository_is_available(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["complete"] is True
    assert result["awaiting_markdown"] is False
    assert {error["source"] for error in result["errors"]} == {"hf_markdown"}
    assert not any("/pdf/" in url for url in fetched)


def test_preflight_marks_missing_public_and_ocr_markdown_as_awaiting(monkeypatch):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def unavailable(url: str, _limit: int):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def unavailable_ocr(*_args, **_kwargs):
        raise urllib.error.HTTPError("bucket", 404, "not found", {}, None)

    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    result = url_preflight.extract_candidates(
        context, fetch=unavailable, fetch_ocr_markdown=unavailable_ocr
    )

    assert result["awaiting_markdown"] is True
    assert result["markdown_available"] is False


def test_fetch_ocr_markdown_uses_authenticated_bucket_download(monkeypatch):
    captured = {}

    class Response:
        headers = {"Content-Length": "2"}

        def geturl(self):
            return "https://signed.example/markdown"

        def read(self, _size):
            return b"#\n"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        url_preflight.urllib.request,
        "build_opener",
        lambda *_handlers: type("Opener", (), {"open": staticmethod(open)})(),
    )

    body, final_url = url_preflight._fetch_ocr_markdown(
        "2608.00042v3", 10, token="hf-test"
    )

    assert body == b"#\n"
    assert final_url == (
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/"
        "2608%2F2608.00042.md"
    )
    assert captured == {
        "url": "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/2608%2F2608.00042.md",
        "authorization": "Bearer hf-test",
        "timeout": url_preflight.TIMEOUT_SECONDS,
    }


def test_ocr_bucket_redirect_strips_authorization_for_cdn_request():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://cdn.example/signed-file",
    )

    assert redirected is not None
    assert redirected.full_url == "https://cdn.example/signed-file"
    assert redirected.get_header("Authorization") is None


def test_ocr_bucket_redirect_strips_authorization_for_scheme_downgrade():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "http://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None


def test_trace_redaction_removes_planted_credentials():
    redacted = redact_trace(
        b"Authorization: Bearer-secret\nOPENAI_API_KEY=sk-exampleexampleexample\nhf-exampleexampleexample"
    ).decode()

    assert "Bearer-secret" not in redacted
    assert "sk-example" not in redacted
    assert "hf-example" not in redacted
    assert redacted.count("<redacted>") >= 3


def test_checked_in_proposal_schema_requires_benchmark_gaps():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert "benchmark_gaps" in schema["required"]
    assert "evaluation_removals" in schema["required"]
    assert "validation_evidence" in schema["required"]
    assert (
        schema["properties"]["benchmark_gaps"]["items"]["properties"]["reasoning"][
            "maxLength"
        ]
        == 2000
    )


def test_trace_json_keeps_gap_reasoning_first_with_deterministic_nested_keys():
    encoded = trace_json(
        {
            "benchmark_gaps": [
                {
                    "gap_type": "dataset_missing",
                    "reasoning": "Evidence-based summary.",
                    "assessment": {"why": "reusable", "confidence": "high"},
                }
            ]
        }
    ).decode()

    gap = encoded[encoded.index("[{") + 2 : encoded.index("}]")]
    assert gap.startswith('"reasoning":"Evidence-based summary."')
    assert '"assessment":{"confidence":"high","why":"reusable"}' in encoded


def test_hourly_reconciliation_requeues_markdown_ready_papers():
    workflow = Path(
        ".github/workflows/cron-enqueue-hf-daily-paper-curation.yml"
    ).read_text()
    assert 'cron: "27 * * * *"' in workflow
    assert 'cron: "20 2 * * *"' not in workflow


def test_canary_gate_excludes_durable_deferred_overflow():
    completed = SimpleNamespace(status="completed", deferred_reason=None)
    deferred = SimpleNamespace(status="deferred", deferred_reason="canary_cap")
    awaiting = SimpleNamespace(status="deferred", deferred_reason="awaiting_markdown")

    assert _dispatched_canary_workflows([completed, deferred, awaiting]) == [
        completed,
        awaiting,
    ]


@pytest.mark.parametrize("trigger", ["hf-daily-cron", "hf-trending-cron"])
def test_scheduled_job_retry_uses_the_shared_durable_queue(trigger):
    job_id = uuid.uuid4()
    row = SimpleNamespace(id=job_id, trigger=trigger, status="failed")
    serialized = {
        "id": str(uuid.uuid4()),
        "retry_of_id": str(job_id),
        "status": "queued",
    }

    class Database:
        def get(self, _model, key):
            return row if key == job_id else None

        def query(self, *_args):
            return SimpleNamespace(
                filter=lambda *_args: SimpleNamespace(
                    order_by=lambda *_args: SimpleNamespace(first=lambda: None)
                )
            )

    class JobService:
        def retry(self, db, selected, settings, *, priority):
            assert isinstance(db, Database)
            assert selected is row
            assert settings is configuration
            assert priority == 50
            return SimpleNamespace(model_dump=lambda **_kwargs: serialized)

    configuration = SimpleNamespace()
    result = HFDailyCurationService(
        Database(),
        configuration,
        job_service=JobService(),
    ).retry_scheduled_job(job_id)

    assert result == serialized


def test_terminal_workflow_retry_is_bounded_and_reuses_the_latest_attempt():
    workflow_id = uuid.uuid4()
    first = SimpleNamespace(
        id=uuid.uuid4(),
        parent_workflow_id=workflow_id,
        trigger="hf-daily-cron",
        status="failed",
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )
    latest = SimpleNamespace(
        id=uuid.uuid4(),
        parent_workflow_id=workflow_id,
        trigger="hf-daily-cron",
        status="failed",
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    workflow = SimpleNamespace(id=workflow_id, status="partial")

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def all(self):
            return [latest, first]

    class Database:
        def query(self, _model):
            return Query()

    class Jobs:
        def __init__(self):
            self.retried = []

        def retry(self, db, row, settings, *, priority):
            self.retried.append((db, row, settings, priority))
            return SimpleNamespace()

    jobs = Jobs()
    service = HFDailyCurationService(
        Database(),
        SimpleNamespace(),
        job_service=jobs,
    )

    assert service.retry_terminal_workflow(workflow) is True
    assert jobs.retried == [(service.db, latest, service.settings, 50)]
    assert _MAX_AUTOMATIC_RETRIES == 3


def test_missing_markdown_defers_workflow_without_immediate_retry():
    workflow_id = uuid.uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        status="running",
        deferred_reason=None,
        error="old",
        finished_at=datetime.now(UTC),
    )
    row = SimpleNamespace(
        parent_workflow_id=workflow_id,
        status="failed",
        error="[awaiting_markdown] Awaiting paper Markdown extraction: 2608.00042",
        kind="enrich-paper",
    )

    class Database:
        def get(self, model, key):
            assert model is PaperCurationWorkflow
            return workflow if key == workflow_id else None

        def commit(self):
            return None

    service = CodexPaperJobService()
    service.enqueue = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("awaiting Markdown must not retry immediately")
    )

    service._advance_workflow(Database(), row, SimpleNamespace())

    assert workflow.status == "deferred"
    assert workflow.deferred_reason == "awaiting_markdown"
    assert workflow.error is None
    assert workflow.finished_at is None


def test_markdown_reconciliation_requeues_only_ready_deferred_workflow():
    ready = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=42,
        cohort_date=date(2026, 8, 24),
        policy_version="daily-v1",
        status="deferred",
        deferred_reason="awaiting_markdown",
        error="old",
        enrich_satisfied_by_job_id=None,
        evals_satisfied_by_job_id=None,
        cohort_order=0,
        created_at=datetime.now(UTC),
    )
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2608.00042",
        title="Ready paper",
    )

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def all(self):
            return [ready]

    class Database:
        def query(self, model):
            assert model is PaperCurationWorkflow
            return Query()

        def get(self, model, key):
            assert model is Paper
            return paper if key == 42 else None

    class Jobs:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, *_args, **kwargs):
            self.enqueued.append(kwargs)

    jobs = Jobs()
    service = HFDailyCurationService(
        Database(),
        SimpleNamespace(),
        job_service=jobs,
        markdown_available=lambda _paper, _settings: True,
    )

    released = service.release_awaiting_markdown(1)

    assert released == 1
    assert ready.status == "queued"
    assert ready.deferred_reason is None
    assert ready.error is None
    assert jobs.enqueued[0]["kind"] == "enrich-paper"


def test_markdown_reconciliation_rotates_unavailable_workflows():
    unavailable = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=41,
        cohort_date=date(2026, 8, 23),
        policy_version="daily-v1",
        status="deferred",
        deferred_reason="awaiting_markdown",
        error=None,
        enrich_satisfied_by_job_id=None,
        cohort_order=0,
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
        updated_at=datetime(2026, 8, 23, tzinfo=UTC),
    )
    ready = SimpleNamespace(
        **{
            **vars(unavailable),
            "id": uuid.uuid4(),
            "paper_id": 42,
            "cohort_order": 1,
        }
    )
    papers = {
        41: SimpleNamespace(id=41, source="arxiv", arxiv_id="2608.00041"),
        42: SimpleNamespace(
            id=42, source="arxiv", arxiv_id="2608.00042", title="Ready paper"
        ),
    }

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def all(self):
            return [unavailable, ready]

    class Database:
        def query(self, _model):
            return Query()

        def get(self, _model, key):
            return papers[key]

    jobs = SimpleNamespace(enqueue=lambda *_args, **_kwargs: None)
    service = HFDailyCurationService(
        Database(),
        SimpleNamespace(),
        job_service=jobs,
        markdown_available=lambda paper, _settings: paper.id == 42,
    )

    checked_at = datetime.now(UTC)
    assert service.release_awaiting_markdown(1) == 1
    assert unavailable.updated_at >= checked_at


@pytest.mark.parametrize(
    ("canonical", "expected"),
    [
        (
            "Title: Ready Paper\n\nURL Source: https://example.com\n\n"
            "Markdown Content:\n\nReady paper experiments establish the result. "
            "The ready paper analysis includes reproducible ablations.\n",
            True,
        ),
        (
            "Title: Ready Paper\n\nURL Source: https://example.com\n\n"
            "Markdown Content:\n\npage_001_image_01.png\n",
            False,
        ),
    ],
)
def test_curation_markdown_availability_requires_semantic_body(
    monkeypatch, canonical, expected
):
    observed = {}

    class Handle(BytesIO):
        def read(self, size=-1):
            observed["read_size"] = size
            return super().read(size)

    class Filesystem:
        def __init__(self, *, token):
            assert token == "token"

        def open(self, path, mode, *, block_size):
            observed.update(path=path, mode=mode, block_size=block_size)
            return Handle(canonical.encode())

    monkeypatch.setattr(
        "backend.services.hf_daily_curation_service.HfFileSystem", Filesystem
    )
    paper = SimpleNamespace(arxiv_id="2608.00042v2", title="Ready Paper")
    settings = SimpleNamespace(
        hf_token="token", paper_markdown_hf_bucket_id="test/paper-markdown"
    )

    assert paper_markdown_available(paper, settings) is expected
    assert observed == {
        "path": "hf://buckets/test/paper-markdown/2608/2608.00042.md",
        "mode": "rb",
        "block_size": 0,
        "read_size": 64 * 1024 * 1024 + 1,
    }


def test_callback_validation_rejection_is_not_classified_as_transient():
    rejected = SimpleNamespace(
        error="Remote job completed without an accepted apply.",
        validation_summary={"status": "rejected", "error": "bad payload"},
    )
    transient = SimpleNamespace(
        error="Codex process timed out",
        validation_summary=None,
    )

    assert _is_callback_validation_rejection(rejected) is True
    assert _is_callback_validation_rejection(transient) is False


def test_validator_replay_uses_saved_proposal_without_writes(monkeypatch):
    from backend.services import hf_daily_curation_service

    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        url_candidates=None,
        proposal={
            "evaluations": [],
            "evaluation_removals": [],
            "benchmark_gaps": [],
            "validation_evidence": [],
        },
    )
    paper = SimpleNamespace(id=42)

    class Database:
        def get(self, model, key):
            if model is hf_daily_curation_service.PaperCurationJob and key == job_id:
                return row
            if model is hf_daily_curation_service.Paper and key == 42:
                return paper
            return None

    class Gaps:
        def __init__(self, db):
            assert isinstance(db, Database)

        def validate(self, gaps, *, paper):
            assert gaps == []
            assert paper is None
            return [], []

    class Callback:
        def __init__(self, db):
            assert isinstance(db, Database)

        def _validate_mutation(self, replay_row, body):
            assert replay_row.status == "running"
            assert replay_row.trace_status == "disabled"
            assert body.evaluations == []

        def _validate_scheduled_policy(self, _replay_row, _body):
            return {"policy": "scheduled-add-evals-v1", "evaluations": 0}

    monkeypatch.setattr(hf_daily_curation_service, "BenchmarkGapService", Gaps)
    monkeypatch.setattr(
        hf_daily_curation_service, "CodexCurationCallbackService", Callback
    )

    result = HFDailyCurationService(
        Database(), SimpleNamespace(), job_service=SimpleNamespace()
    ).validator_replay(job_id)

    assert result == {
        "job_id": str(job_id),
        "valid": True,
        "validation": {"policy": "scheduled-add-evals-v1", "evaluations": 0},
        "benchmark_gaps_accepted": 0,
        "benchmark_gaps_rejected": [],
    }


@pytest.mark.parametrize("trigger", ["hf-daily-cron", "hf-trending-cron"])
def test_queued_operator_retry_is_prioritized_without_duplication(trigger):
    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        trigger=trigger,
        status="queued",
        priority=100,
    )

    class Database:
        committed = False

        def get(self, _model, _key):
            return row

        def query(self, *_args):
            return SimpleNamespace(
                filter=lambda *_args: SimpleNamespace(
                    order_by=lambda *_args: SimpleNamespace(first=lambda: None)
                )
            )

        def commit(self):
            self.committed = True

    class JobService:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, selected, _settings):
            assert selected is row
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(job_id),
                    "priority": row.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("queued jobs must not be duplicated")

    database = Database()
    jobs = JobService()
    result = HFDailyCurationService(
        database,
        SimpleNamespace(),
        job_service=jobs,
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(job_id), "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


def test_canary_dispatch_launches_only_selected_job_while_normal_dispatch_is_paused():
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    other = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-trending-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Database:
        def get(self, model, key):
            if model is PaperCurationSchedulerState:
                return scheduler
            if key == selected.id:
                return selected
            return None

    class Jobs:
        launched = []

        def dispatch_canary(self, _db, _settings, row):
            self.launched.append(row)
            row.status = "running"
            return row

        def serialize(self, row, _settings):
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(row.id),
                    "status": row.status,
                }
            )

    jobs = Jobs()
    result = HFDailyCurationService(
        Database(), SimpleNamespace(), job_service=jobs
    ).dispatch_canary_job(selected.id)

    assert result == {"id": str(selected.id), "status": "running"}
    assert jobs.launched == [selected]
    assert other.status == "queued"
    assert scheduler.dispatch_enabled is False
    assert scheduler.paused_at is not None


def test_daily_curation_cli_dispatches_one_explicit_canary_job(monkeypatch, capsys):
    job_id = uuid.uuid4()
    calls = []

    def session():
        yield object()

    class Service:
        def __init__(self, db, settings):
            calls.append((db, settings))

        def dispatch_canary_job(self, selected_job_id):
            calls.append(selected_job_id)
            return {"id": str(selected_job_id), "status": "running"}

    settings = object()
    monkeypatch.setattr(curation_cli, "get_database_session", session)
    monkeypatch.setattr(curation_cli, "get_settings", lambda: settings)
    monkeypatch.setattr(curation_cli, "HFDailyCurationService", Service)
    monkeypatch.setattr(
        sys,
        "argv",
        ["enqueue_hf_daily_paper_curation", "--canary-job", str(job_id)],
    )

    assert curation_cli.main() == 0
    assert calls[1] == job_id
    assert json.loads(capsys.readouterr().out) == {
        "id": str(job_id),
        "status": "running",
    }


def test_daily_curation_cli_exits_nonzero_when_canary_does_not_launch(
    monkeypatch, capsys
):
    job_id = uuid.uuid4()

    def session():
        yield object()

    class Service:
        def __init__(self, _db, _settings):
            pass

        def dispatch_canary_job(self, _selected_job_id):
            raise CanaryDispatchFailed("Canary job did not launch")

    monkeypatch.setattr(curation_cli, "get_database_session", session)
    monkeypatch.setattr(curation_cli, "get_settings", object)
    monkeypatch.setattr(curation_cli, "HFDailyCurationService", Service)
    monkeypatch.setattr(
        sys,
        "argv",
        ["enqueue_hf_daily_paper_curation", "--canary-job", str(job_id)],
    )

    assert curation_cli.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "Canary job did not launch",
        "job_id": str(job_id),
        "launched": False,
    }


@pytest.mark.parametrize(
    ("trigger", "status", "dispatch_enabled", "paused_at", "message"),
    (
        ("admin", "queued", False, datetime.now(UTC), "Only scheduled"),
        (
            "hf-daily-cron",
            "running",
            False,
            datetime.now(UTC),
            "requires a queued",
        ),
        (
            "hf-trending-cron",
            "queued",
            True,
            None,
            "normal dispatch to be paused",
        ),
    ),
)
def test_canary_dispatch_rejects_unsafe_selection_or_scheduler_state(
    trigger, status, dispatch_enabled, paused_at, message
):
    row = SimpleNamespace(id=uuid.uuid4(), trigger=trigger, status=status)
    scheduler = SimpleNamespace(
        dispatch_enabled=dispatch_enabled,
        paused_at=paused_at,
    )

    class Database:
        def get(self, model, _key):
            return scheduler if model is PaperCurationSchedulerState else row

    class Jobs:
        def dispatch_canary(self, *_args):
            raise AssertionError("unsafe canary must not reach the dispatcher")

    with pytest.raises(ValueError, match=message):
        HFDailyCurationService(
            Database(), SimpleNamespace(), job_service=Jobs()
        ).dispatch_canary_job(row.id)


@pytest.mark.parametrize("trigger", ["hf-daily-cron", "hf-trending-cron"])
def test_repeating_operator_retry_returns_active_child_attempt(trigger):
    job_id = uuid.uuid4()
    failed = SimpleNamespace(id=job_id, trigger=trigger, status="failed")
    active = SimpleNamespace(id=uuid.uuid4(), status="running", priority=100)

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return active

    class Database:
        committed = False

        def get(self, *_args):
            return failed

        def query(self, *_args):
            return Query()

        def commit(self):
            self.committed = True

    class Jobs:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, row, _settings):
            assert row is active
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(active.id),
                    "status": active.status,
                    "priority": active.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("an active child retry must be reused")

    database = Database()
    jobs = Jobs()
    result = HFDailyCurationService(
        database, SimpleNamespace(), job_service=jobs
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(active.id), "status": "running", "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


def test_operator_retry_rejects_admin_jobs():
    job_id = uuid.uuid4()

    class Database:
        def get(self, _model, _key):
            return SimpleNamespace(trigger="admin")

    with pytest.raises(ValueError, match="Only scheduled HF daily"):
        HFDailyCurationService(
            Database(),
            SimpleNamespace(),
            job_service=SimpleNamespace(),
        ).retry_scheduled_job(job_id)


def test_dispatch_acknowledgement_starts_a_fresh_failure_window():
    state = SimpleNamespace(
        dispatch_enabled=True,
        paused_at=datetime.now(UTC),
        pause_reason="Historical failures",
        pause_condition="terminal_failure_rate",
        acknowledged_at=None,
        first_enabled_at=datetime.now(UTC),
        consecutive_trace_failures=3,
        consecutive_apply_failures=3,
        canary_released=True,
    )

    class Query:
        def filter(self, *_args):
            return self

        def scalar(self):
            return None

    class Database:
        def get(self, *_args):
            return state

        def query(self, *_args):
            return Query()

        def commit(self):
            pass

    jobs = SimpleNamespace(dispatch_next=lambda *_args: None)
    result = HFDailyCurationService(
        Database(),
        get_settings(),
        job_service=jobs,
    ).set_dispatch(True)

    assert result["paused_at"] is None
    assert state.acknowledged_at is not None
    assert state.consecutive_trace_failures == 0
    assert state.consecutive_apply_failures == 0


def test_scheduled_usage_snapshot_exposes_enforced_threshold(monkeypatch):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    rows = [
        SimpleNamespace(
            finished_at=now,
            input_tokens=400,
            output_tokens=200,
        )
    ] + [
        SimpleNamespace(
            finished_at=now - codex_add_evals_service.timedelta(days=offset),
            input_tokens=80,
            output_tokens=20,
        )
        for offset in range(1, 8)
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return rows

    class Database:
        def query(self, *_args):
            return Query()

    snapshot = CodexPaperJobService._scheduled_usage_snapshot(
        Database(),
        SimpleNamespace(
            first_enabled_at=now - codex_add_evals_service.timedelta(days=8)
        ),
    )

    assert snapshot == {
        "mode": "enforced",
        "current_day_tokens": 600,
        "trailing_seven_day_median_tokens": 100,
        "positive_baseline_days": 7,
        "pause_threshold_tokens": 200,
    }


def test_scheduled_usage_filters_for_completed_jobs(monkeypatch):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    filters = []

    class Query:
        def filter(self, *predicates):
            filters.extend(str(predicate) for predicate in predicates)
            return self

        def all(self):
            return []

    class Database:
        def query(self, *_args):
            return Query()

    CodexPaperJobService._scheduled_usage_snapshot(Database(), None)

    assert any("paper_curation_jobs.status" in predicate for predicate in filters)


@pytest.mark.parametrize(
    ("daily_tokens", "mode", "median_tokens", "threshold"),
    [
        ([100, 300], "baseline_alert_only", 200, None),
        ([100, 300, 500], "enforced", 300, 600),
    ],
)
def test_scheduled_usage_excludes_zero_days_and_requires_three_positive_days(
    monkeypatch, daily_tokens, mode, median_tokens, threshold
):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    rows = [
        SimpleNamespace(
            finished_at=now - codex_add_evals_service.timedelta(days=offset),
            input_tokens=tokens,
            output_tokens=0,
        )
        for offset, tokens in enumerate(daily_tokens, start=1)
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return rows

    class Database:
        def query(self, *_args):
            return Query()

    snapshot = CodexPaperJobService._scheduled_usage_snapshot(
        Database(),
        SimpleNamespace(
            first_enabled_at=now - codex_add_evals_service.timedelta(days=30)
        ),
    )

    assert snapshot == {
        "mode": mode,
        "current_day_tokens": 0,
        "trailing_seven_day_median_tokens": median_tokens,
        "positive_baseline_days": len(daily_tokens),
        "pause_threshold_tokens": threshold,
    }


def test_cross_job_callback_token_pauses_scheduled_dispatch(monkeypatch):
    from backend.routers import codex_curation_callbacks

    added = []

    class Database:
        def get(self, *_args):
            return None

        def add(self, value):
            added.append(value)

        def commit(self):
            pass

    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "authenticate",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "token_owner_for_other_job",
        lambda *_args: object(),
    )

    with pytest.raises(HTTPException) as error:
        codex_curation_callbacks._callback_job(
            uuid.uuid4(), "Bearer valid-for-another-job", Database()
        )

    assert error.value.status_code == 401
    assert added[0].pause_condition == "cross_paper_authorization"
    assert added[0].paused_at is not None


@pytest.mark.parametrize(
    ("scale", "value"),
    [("0-1", 1.01), ("0-100", 100.01), ("0-1000", 1000.01)],
)
def test_metric_scale_guard_rejects_out_of_range_values(scale, value):
    with pytest.raises(ValueError, match="outside configured scale"):
        CodexCurationCallbackService._validate_metric_scale(scale, value)


class _DispatchQuery:
    def __init__(self, database):
        self.database = database

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *args):
        self.database.orderings.append([str(value) for value in args])
        return self

    def first(self):
        return self.database.first_results.pop(0)


class _DispatchDatabase:
    def __init__(self, *first_results):
        self.first_results = list(first_results)
        self.orderings = []

    def query(self, *_args):
        return _DispatchQuery(self)


def test_overdue_dispatch_reserves_only_one_slot_before_newest_first():
    oldest_overdue = object()
    newest = object()
    first_slot = _DispatchDatabase(None, oldest_overdue)
    remaining_slot = _DispatchDatabase(object(), None, newest)

    assert CodexPaperJobService._next_scheduled_row(first_slot) is oldest_overdue
    assert CodexPaperJobService._next_scheduled_row(remaining_slot) is newest
    assert any(
        "cohort_order" in value
        for ordering in remaining_slot.orderings
        for value in ordering
    )


def test_trending_resolution_precedes_non_overdue_daily_work():
    trending = object()
    database = _DispatchDatabase(object(), trending)

    assert CodexPaperJobService._next_scheduled_row(database) is trending


def test_newest_first_fallback_when_no_overdue_workflow_exists():
    newest = object()
    database = _DispatchDatabase(None, None, newest)

    assert CodexPaperJobService._next_scheduled_row(database) is newest


def test_hf_dispatch_retries_with_bounded_exponential_backoff(monkeypatch):
    calls = []
    sleeps = []

    class Hub:
        def run_job(self, **values):
            calls.append(values)
            if len(calls) < 3:
                raise OSError("transient dispatch failure")
            return SimpleNamespace(id="hf-job")

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_api", lambda _settings: Hub())
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service.time.sleep", sleeps.append
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        retry_of_id=None,
        repository_sha="a" * 40,
        trigger="hf-daily-cron",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_openai_api_key": "test-openai",
            "github_token": "test-github",
            "hf_token": "test-hf",
        }
    )

    remote = service._run_job_with_retry(
        settings=settings,
        row=row,
        callback_token="callback",
        image="example/image:sha",
    )

    assert remote.id == "hf-job"
    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert all("GITHUB_TOKEN" not in call["secrets"] for call in calls)
    assert all(
        call["secrets"]["PWC_PAPER_MARKDOWN_HF_TOKEN"] == "test-hf" for call in calls
    )
    assert all(call["image"] == "example/image:sha" for call in calls)


def test_space_image_revision_is_verified_and_mismatch_pauses_daily_dispatch(
    monkeypatch,
):
    expected = "a" * 40
    state = SimpleNamespace(
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )

    class Hub:
        observed = expected

        def space_info(self, *, repo_id):
            assert repo_id == "example/curator-0123456789ab"
            return SimpleNamespace(sha=self.observed)

    class Database:
        commits = 0

        def get(self, *_args):
            return state

        def commit(self):
            self.commits += 1

    service = CodexPaperJobService()
    hub = Hub()
    monkeypatch.setattr(service, "_api", lambda _settings: hub)
    settings = get_settings().model_copy(
        update={
            "codex_jobs_image": "hf.co/spaces/example/curator-0123456789ab",
            "codex_jobs_image_revision": expected,
        }
    )
    row = SimpleNamespace(trigger="hf-daily-cron", repository_sha="b" * 40)
    database = Database()

    assert service._verified_job_image(database, settings, row) == (
        "hf.co/spaces/example/curator-0123456789ab"
    )

    hub.observed = "c" * 40
    with pytest.raises(RuntimeError, match="Curator Space revision mismatch"):
        service._verified_job_image(database, settings, row)
    assert state.pause_condition == "curator_image_revision_mismatch"
    assert state.paused_at is not None


def test_dispatch_does_not_append_registry_tag_to_verified_space(monkeypatch):
    launched = {}

    class Database:
        def commit(self):
            pass

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_verified_job_image",
        lambda _db, _settings, _row: "hf.co/spaces/example/curator-0123456789ab",
    )
    monkeypatch.setattr(
        service,
        "_run_job_with_retry",
        lambda **values: launched.update(values) or SimpleNamespace(id="hf-job"),
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=42,
        trigger="admin",
        retry_of_id=None,
        repository_sha="b" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        status="queued",
        callback_token_hash=None,
        attempt_count=0,
        hf_job_id=None,
        started_at=None,
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_token": "hf-token",
            "codex_jobs_openai_api_key": "openai-token",
        }
    )

    service._dispatch_row(Database(), settings, row)

    assert launched["image"] == "hf.co/spaces/example/curator-0123456789ab"
    assert row.status == "running"
    assert row.hf_job_id == "hf-job"


def test_one_shot_dispatch_calls_only_the_selected_scheduled_row(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    other = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-trending-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return []

    class Database:
        def query(self, model):
            assert model is PaperCurationJob
            return Query()

        def get(self, model, key):
            assert (model, key) == (PaperCurationSchedulerState, 1)
            return scheduler

    launched = []
    service = CodexPaperJobService()

    def launch(_db, _settings, row):
        launched.append(row)
        row.status = "running"
        row.hf_job_id = "hf-canary-job"

    monkeypatch.setattr(
        service,
        "_dispatch_row",
        launch,
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    service.dispatch_canary(Database(), settings, selected)

    assert launched == [selected]
    assert other.status == "queued"
    assert scheduler.dispatch_enabled is False
    assert scheduler.paused_at is not None


def test_one_shot_dispatch_refuses_to_exceed_scheduled_capacity(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    active = SimpleNamespace(trigger="hf-trending-cron", status="running")
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [active]

    class Database:
        def query(self, _model):
            return Query()

        def get(self, _model, _key):
            return scheduler

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_dispatch_row",
        lambda *_args: pytest.fail("capacity denial must not launch a job"),
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=1,
    )

    with pytest.raises(RuntimeError, match="scheduled curation capacity"):
        service.dispatch_canary(Database(), settings, selected)


def test_one_shot_dispatch_reports_a_non_launched_row_as_failure(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
        hf_job_id=None,
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return []

    class Database:
        def query(self, _model):
            return Query()

        def get(self, model, _key):
            return scheduler if model is PaperCurationSchedulerState else selected

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_dispatch_row", lambda *_args: None)
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    with pytest.raises(RuntimeError, match="did not launch"):
        service.dispatch_canary(Database(), settings, selected)


def test_one_shot_dispatch_cannot_bypass_an_automatic_safety_pause(monkeypatch):
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="daily_token_guardrail",
        first_enabled_at=datetime.now(UTC),
    )

    class Database:
        def get(self, _model, _key):
            return scheduler

    service = CodexPaperJobService()
    monkeypatch.setattr(
        service,
        "_dispatch_row",
        lambda *_args: pytest.fail("automatic safety pauses must not be bypassed"),
    )
    settings = SimpleNamespace(
        codex_jobs_enabled=True,
        codex_curation_scheduler_enabled=True,
        codex_jobs_max_active=4,
        codex_jobs_max_scheduled_active=3,
    )

    with pytest.raises(RuntimeError, match="operator pause"):
        service.dispatch_canary(Database(), settings, selected)


def test_postgres_curation_dispatch_lock_serializes_concurrent_sessions():
    database_url = os.getenv("PWC_AUTONOMOUS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PWC_AUTONOMOUS_TEST_DATABASE_URL is not configured")
    if not (make_url(database_url).database or "").startswith("autonomous_ops_test_"):
        pytest.fail("Curation concurrency test requires a disposable database")
    engine = create_engine(database_url, pool_size=2)
    first_acquired = Event()
    release_first = Event()
    second_acquired = Event()

    def hold_first_lock():
        with Session(engine) as db:
            with curation_dispatch_lock(db):
                first_acquired.set()
                assert release_first.wait(timeout=5)

    def acquire_second_lock():
        assert first_acquired.wait(timeout=5)
        with Session(engine) as db:
            with curation_dispatch_lock(db):
                second_acquired.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(hold_first_lock)
            second = pool.submit(acquire_second_lock)
            assert first_acquired.wait(timeout=5)
            assert second_acquired.wait(timeout=0.2) is False
            release_first.set()
            first.result(timeout=5)
            second.result(timeout=5)
        assert second_acquired.is_set()
    finally:
        engine.dispose()


def test_scheduled_dispatch_fails_closed_before_remote_launch_when_curation_is_disabled(
    monkeypatch,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AutonomousOperatorState,
        AutonomousRun,
        PaperCurationSchedulerState,
    ):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:

        class Database:
            def get(self, model, key):
                if model is Paper:
                    return SimpleNamespace(id=key)
                return session.get(model, key)

            def __getattr__(self, name):
                return getattr(session, name)

        db = Database()
        operations = AutonomousOperationsRepository()
        control = operations.get_control_state(db)
        assert control.manual_mode is True
        session.get(AutonomousOperatorState, "global").manual_mode = False
        state = PaperCurationSchedulerState(
            id=1,
            dispatch_enabled=True,
            first_enabled_at=datetime.now(UTC),
        )
        db.add(state)
        db.commit()
        row = SimpleNamespace(
            id=uuid.uuid4(),
            kind="enrich-paper",
            paper_id=42,
            candidate_id=None,
            trigger="hf-daily-cron",
            policy_version="scheduled-v1",
            status="queued",
        )
        service = CodexPaperJobService()
        launched = False

        def launch(**_values):
            nonlocal launched
            launched = True
            return SimpleNamespace(id="hf-job")

        monkeypatch.setattr(service, "_run_job_with_retry", launch)
        settings = get_settings().model_copy(
            update={
                "codex_jobs_namespace": "example",
                "codex_jobs_token": "hf-token",
                "codex_jobs_openai_api_key": "openai-token",
            }
        )

        service._dispatch_row(db, settings, row)

        assert launched is False
        assert row.status == "queued"
        assert state.pause_condition == "autonomous_policy_denied"
        assert "curation operator is disabled" in state.pause_reason
        control = operations.get_control_state(db)
        assert control.enabled[Operator.CURATION] is False
    engine.dispose()


def test_bootstrap_bundle_is_allowlisted_hashed_and_release_bound(monkeypatch):
    from backend.services import codex_add_evals_service as service_module

    revision = "d" * 40
    monkeypatch.setattr(service_module, "_git_revision", lambda: revision)
    service = CodexPaperJobService()

    bundle = service.bootstrap_bundle(SimpleNamespace(repository_sha=revision))

    assert bundle["revision"] == revision
    assert {item["path"] for item in bundle["files"]} == set(
        service_module.CURATOR_BOOTSTRAP_PATHS
    )
    for item in bundle["files"]:
        content = base64.b64decode(item["content_b64"], validate=True)
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
    with pytest.raises(ValueError, match="active immutable release"):
        service.bootstrap_bundle(SimpleNamespace(repository_sha="e" * 40))

    persisted = service_module._curator_bootstrap_bundle(revision)
    monkeypatch.setattr(service_module, "_git_revision", lambda: "f" * 40)
    assert (
        service.bootstrap_bundle(
            SimpleNamespace(repository_sha=revision, bootstrap_bundle=persisted)
        )
        == persisted
    )

    persisted["files"][0]["content_b64"] = base64.b64encode(b"tampered").decode()
    with pytest.raises(ValueError, match="hash mismatch"):
        service.bootstrap_bundle(
            SimpleNamespace(repository_sha=revision, bootstrap_bundle=persisted)
        )


def test_benchmark_gap_validation_isolates_malformed_entries():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    valid = {
        "reasoning": "A reusable public benchmark blocks a paper-native result.",
        "local_ref": "gap-1",
        "gap_type": "dataset_missing",
        "proposed_benchmark": {
            "name": "ExampleBench",
            "aliases": ["Example Bench"],
            "description": "A reusable public benchmark.",
            "task_candidates": [
                {
                    "task_id": 19,
                    "task_name": "Example Task",
                    "confidence": "high",
                    "reason": "The paper evaluates this task.",
                }
            ],
            "canonical_sources": [
                {
                    "kind": "homepage",
                    "url": "https://example.org/benchmark",
                    "title": "ExampleBench",
                }
            ],
        },
        "protocol": {
            "dataset_version": "v1",
            "splits": ["test"],
            "evaluation_protocol": "Evaluate on the public test split.",
            "metrics": [
                {
                    "name": "Accuracy",
                    "direction": "higher_is_better",
                    "unit": "percent",
                    "native_scale": "0-100",
                    "definition": "Exact-match accuracy.",
                }
            ],
            "supports_harness": False,
        },
        "blocked_evaluations": [
            {
                "local_ref": "blocked-1",
                "model_name": "Introduced Model",
                "harness": None,
                "split": "test",
                "metrics": {"Accuracy": 87.4},
                "best_metric": "Accuracy",
                "methodology": "Official test split.",
                "uses_additional_data": False,
                "is_open": True,
                "num_parameters": 7_000_000_000,
                "hf_model_url": "https://huggingface.co/example/model",
                "evidence_ids": ["e1"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "e1",
                "source_kind": "paper_pdf",
                "source_url": "https://arxiv.org/pdf/2608.00042",
                "page": 7,
                "section": "4.2",
                "table": "Table 3",
                "snippet": "ExampleBench test results.",
                "supports": ["blocked-1"],
            }
        ],
        "catalog_search": {
            "queries": ["ExampleBench"],
            "near_matches": [],
            "conclusion": "No configured benchmark matches.",
        },
        "assessment": {
            "recommendation": "add_candidate",
            "confidence": "high",
            "why_worth_adding": "The protocol is public and reusable.",
            "ambiguities": [],
        },
    }

    accepted, rejected = BenchmarkGapService(Database()).validate(
        [valid, {"gap_type": "dataset_missing"}]
    )

    assert len(accepted) == 1
    assert accepted[0]["_normalized"]["task_ids"] == [19]
    assert rejected == [{"index": 1, "error": "reasoning is required"}]

    html_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_markdown",
                "source_url": "https://arxiv.org/html/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [html_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert len(accepted) == 1
    assert rejected == []

    queried_source = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_source",
                "source_url": "https://example.com/report?id=1",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [queried_source],
        paper=SimpleNamespace(
            source_url="https://example.com/report?id=1",
            arxiv_id=None,
        ),
    )

    assert len(accepted) == 1
    assert rejected == []

    eprint_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_source",
                "source_url": "https://export.arxiv.org/e-print/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [eprint_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert rejected == []
    assert accepted[0]["evidence"][0]["source_url"] == (
        "https://arxiv.org/html/2608.00042"
    )

    repository_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "github_readme",
                "source_url": (
                    "https://raw.githubusercontent.com/example/model/main/README.md"
                ),
                "supports": ["ExampleBench results in Table 3"],
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [repository_evidence],
        paper=SimpleNamespace(
            source_url="https://example.com/release",
            arxiv_id=None,
        ),
        source_documents=[
            {"kind": "github_readme", "url": "https://github.com/example/model"}
        ],
    )

    assert len(accepted) == 1
    assert rejected == []

    mismatched_kind = {
        **repository_evidence,
        "evidence": [
            {**repository_evidence["evidence"][0], "source_kind": "paper_pdf"}
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [mismatched_kind],
        paper=SimpleNamespace(
            source_url="https://example.com/release",
            arxiv_id=None,
        ),
        source_documents=[
            {"kind": "github_readme", "url": "https://github.com/example/model"}
        ],
    )

    assert accepted == []
    assert rejected == [
        {"index": 0, "error": "evidence source kind does not match scoped source"}
    ]


def test_benchmark_gap_rejects_server_owned_fields():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    invalid = {
        "reasoning": "A gap.",
        "candidate_id": "agent-invented",
        "gap_type": "dataset_missing",
    }

    accepted, rejected = BenchmarkGapService(Database()).validate([invalid])

    assert accepted == []
    assert rejected == [
        {"index": 0, "error": "agent proposal contains server-owned fields"}
    ]


def test_reviewed_benchmark_promotion_requeues_only_evidence_papers():
    candidate_id = uuid.uuid4()
    candidate = SimpleNamespace(
        id=candidate_id,
        task_ids=[19],
        status="candidate",
        promoted_at=None,
    )
    evidence = SimpleNamespace(
        candidate_id=candidate_id,
        paper_id=42,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload={"protocol": {"metrics": [{"name": "Accuracy"}]}},
    )
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2608.00042",
        title="Evidence paper",
    )

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def one_or_none(self):
            if self.model is Metric:
                return SimpleNamespace(id=7, name="Accuracy")
            return None

        def all(self):
            return [evidence] if self.model is BenchmarkCurationEvidence else []

        def first(self):
            return None

    class Database:
        def __init__(self):
            self.commits = 0

        def get(self, model, key):
            values = {
                (BenchmarkCurationCandidate, candidate_id): candidate,
                (Dataset, 8): SimpleNamespace(id=8),
                (Task, 19): SimpleNamespace(id=19),
                (TaskDataset, (19, 8)): SimpleNamespace(task_id=19, dataset_id=8),
                (Paper, 42): paper,
            }
            return values.get((model, key))

        def query(self, model):
            return Query(model)

        def commit(self):
            self.commits += 1

    class Jobs:
        def __init__(self):
            self.enqueued = []
            self.dispatched = False

        def enqueue(self, db, **values):
            self.enqueued.append((db, values))
            return SimpleNamespace(id=uuid.uuid4())

        def dispatch_next(self, *_args):
            self.dispatched = True

    database = Database()
    jobs = Jobs()
    result = BenchmarkGapService(database).promote_and_enqueue(
        candidate_id=candidate_id,
        dataset_id=8,
        task_id=19,
        best_metric="Accuracy",
        settings=get_settings(),
        job_service=jobs,
    )

    assert result["skipped_active_paper_ids"] == []
    assert len(result["enqueued_job_ids"]) == 1
    assert jobs.enqueued[0][1] | {"settings": None} == {
        "kind": "add-evals",
        "paper_id": 42,
        "paper_route": "2608.00042",
        "paper_title": "Evidence paper",
        "requested_by": f"benchmark-promotion:{candidate_id}",
        "trigger": "benchmark-promotion",
        "policy_version": f"benchmark-promotion-{str(candidate_id)[:12]}",
        "priority": 50,
        "dispatch": False,
        "commit": False,
        "settings": None,
    }
    assert candidate.status == "promoted"
    assert candidate.promoted_at is not None
    assert jobs.dispatched is True


def test_trace_bundle_manifest_hashes_every_uploaded_object(tmp_path):
    scheduler = SimpleNamespace(consecutive_trace_failures=2)

    class Database:
        def commit(self):
            pass

        def get(self, model, *_args):
            from backend.models.database import PaperCurationSchedulerState

            return scheduler if model is PaperCurationSchedulerState else None

    class Hub:
        def __init__(self):
            self.objects = {}

        def create_bucket(self, *_args, **_kwargs):
            pass

        def batch_bucket_files(self, _bucket, *, add):
            self.objects.update({path: data for data, path in add})

    settings = get_settings().model_copy(
        update={
            "codex_curation_trace_upload_enabled": True,
            "codex_curation_trace_hf_bucket_id": "example/curate-papers-traces",
            "codex_add_evals_spool_dir": str(tmp_path),
        }
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=42,
        cohort_date=date(2026, 8, 18),
        policy_version="hf-daily-v1",
        parent_workflow_id=uuid.uuid4(),
        repository_sha="a" * 40,
        skill_sha256="b" * 64,
        prompt_sha256=None,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        proposal=None,
        url_candidates=None,
        trace_attempt_count=0,
        trace_uri=None,
    )
    hub = Hub()
    service = CurationTraceService(Database(), settings, hf_api=hub)
    events = base64.b64encode(gzip.compress(b'{"type":"done"}\n')).decode()
    service.preapply(
        row,
        proposal={"evaluations": [], "benchmark_gaps": []},
        events_gzip_b64=events,
        prompt="curate paper 42",
        url_candidates={"complete": True, "candidates": [], "sources": []},
    )
    service.finalize(
        row,
        {
            "events_gzip_b64": events,
            "result": {"status": "no_changes"},
            "benchmark_gaps": [],
            "report": "No eligible changes.",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "duration_ms": 50,
        },
    )

    manifest_path = next(path for path in hub.objects if path.endswith("manifest.json"))
    manifest = json.loads(hub.objects[manifest_path])
    assert row.trace_status == "complete"
    assert scheduler.consecutive_trace_failures == 0
    assert {"events.jsonl.gz", "prompt.txt", "proposal.json", "result.json"} <= set(
        manifest["objects"]
    )
    assert not (tmp_path / "curation-traces" / f"{row.id}.json").exists()
