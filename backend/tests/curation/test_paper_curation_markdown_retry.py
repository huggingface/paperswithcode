"""Markdown-gated reconciliation, deferral, and bounded workflow retry."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.models.database import (
    Paper,
    PaperCurationWorkflow,
)
from backend.services.codex_add_evals_service import (
    EXTERNAL_PAPER_POLICY_VERSION,
    CodexPaperJobService,
    _is_callback_validation_rejection,
)
from backend.services.hf_daily_curation_service import (
    HFDailyCurationService,
    _dispatched_canary_workflows,
    _MAX_AUTOMATIC_RETRIES,
    paper_markdown_available,
)


def test_hourly_reconciliation_requeues_markdown_ready_papers():
    timer = Path(
        "deploy/systemd/cron/pwc-cron-enqueue-hf-daily-paper-curation.timer"
    ).read_text()
    assert "OnCalendar=*-*-* *:27:00" in timer
    assert "Persistent=true" in timer


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
            "Markdown Content:\n\n" + "Ready paper experiments establish the result. "
            "The ready paper analysis includes reproducible ablations.\n" * 25,
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


def test_external_workflow_releases_to_admin_add_evals_after_enrichment():
    workflow = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=131370,
        cohort_date=date(2026, 10, 27),
        policy_version=EXTERNAL_PAPER_POLICY_VERSION,
        status="deferred",
        deferred_reason="awaiting_markdown",
        error=None,
        enrich_satisfied_by_job_id=None,
        evals_satisfied_by_job_id=None,
        cohort_order=0,
        created_at=datetime.now(UTC),
    )
    paper = SimpleNamespace(
        id=131370, source="external", arxiv_id=None, title="Introducing GPT-6.1 Terra"
    )

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def all(self):
            return self.rows

        def first(self):
            return self.rows[0] if self.rows else None

    class Database:
        def query(self, model):
            if model is PaperCurationWorkflow:
                return Query([workflow])
            # The workflow's completed enrich-paper job.
            return Query([SimpleNamespace(id=uuid.uuid4())])

        def get(self, model, key):
            return paper

    enqueued = []
    service = HFDailyCurationService(
        Database(),
        SimpleNamespace(),
        job_service=SimpleNamespace(enqueue=lambda *_a, **kw: enqueued.append(kw)),
        markdown_available=lambda _paper, _settings: True,
    )

    assert service.release_awaiting_markdown(1) == 1
    assert workflow.status == "queued"
    assert (
        enqueued[0]["kind"],
        enqueued[0]["trigger"],
        enqueued[0]["requested_by"],
    ) == ("add-evals", "admin", "external-paper-markdown-ready")


@pytest.mark.parametrize("pending", [True, False])
def test_external_markdown_availability_follows_page_markdown(monkeypatch, pending):
    monkeypatch.setattr(
        "backend.services.hf_daily_curation_service.web_markdown_pending",
        lambda paper, *, bucket_id, token: pending,
    )
    paper = SimpleNamespace(id=131370, source="external", arxiv_id=None, title="X")
    settings = SimpleNamespace(hf_token="t", paper_markdown_hf_bucket_id="b/c")

    assert paper_markdown_available(paper, settings) is not pending
