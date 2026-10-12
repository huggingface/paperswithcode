"""Focused contracts for method-link provenance and historical backfills."""

from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method,
    MethodKeywordBackfillRun,
    MethodReferenceBackfillMonth,
    Paper,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
)
from backend.services.method_backfill_service import (
    audit_undated_method_links,
    keyword_catalog_rows,
    run_keyword_backfill,
    run_reference_backfill,
)
from backend.services.openalex_reference_service import OpenAlexWorkBatch
from backend.services.paper_method_link_service import (
    replace_manual_links,
    sync_method_source_evidence,
    upsert_evidence_links,
)
from backend.services.method_trend_service import MethodTrendService


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Method.__table__,
            PaperMethod.__table__,
            PaperMethodEvidence.__table__,
            PaperMethodExclusion.__table__,
            MethodReferenceBackfillMonth.__table__,
            MethodKeywordBackfillRun.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _paper(paper_id: int, title: str, published: date | None = None) -> Paper:
    return Paper(
        id=paper_id,
        source="arxiv",
        arxiv_id=f"2601.{paper_id:05d}",
        version="v1",
        is_latest_version=True,
        title=title,
        abstract="",
        date_published=published,
    )


def test_evidence_is_idempotent_and_manual_removal_is_a_durable_veto():
    db = _session()
    db.add_all([_paper(1, "CLIP"), Method(id=10, name="CLIP", slug="clip")])
    db.commit()

    link = [{"paper_id": 1, "method_id": 10}]
    assert upsert_evidence_links(db, link, evidence_type="keyword") == 1
    assert upsert_evidence_links(db, link, evidence_type="keyword") == 0
    db.commit()
    assert db.query(PaperMethodEvidence).count() == 1

    replace_manual_links(db, paper_id=1, method_ids=[])
    db.commit()
    assert db.query(PaperMethod).count() == 0
    assert db.query(PaperMethodEvidence).count() == 0
    assert db.get(PaperMethodExclusion, (1, 10)) is not None

    upsert_evidence_links(db, link, evidence_type="reference")
    db.commit()
    assert db.query(PaperMethod).count() == 0

    replace_manual_links(db, paper_id=1, method_ids=[10])
    db.commit()
    assert db.get(PaperMethodExclusion, (1, 10)) is None
    assert db.get(PaperMethodEvidence, (1, 10, "manual")) is not None


def test_source_evidence_tracks_only_the_current_canonical_source():
    db = _session()
    db.add_all(
        [
            _paper(1, "Old source"),
            _paper(2, "New source"),
            Method(id=10, name="A", slug="a", source_paper_id=1),
        ]
    )
    db.commit()
    sync_method_source_evidence(db, method_id=10, source_paper_id=1)
    db.commit()

    sync_method_source_evidence(db, method_id=10, source_paper_id=2)
    db.commit()

    assert db.get(PaperMethodEvidence, (1, 10, "source")) is None
    assert db.get(PaperMethod, (1, 10)) is None
    assert db.get(PaperMethodEvidence, (2, 10, "source")) is not None


def test_keyword_backfill_covers_sourced_and_sourceless_methods_and_resumes():
    db = _session()
    db.add_all(
        [
            _paper(1, "CLIP improves vision", date(2021, 3, 1)),
            _paper(2, "A transformer study", None),
            Method(
                id=10,
                name="CLIP",
                slug="clip",
                keywords="CLIP",
                source_paper_id=1,
            ),
            Method(
                id=11,
                name="Transformer",
                slug="transformer",
                keywords="transformer",
            ),
        ]
    )
    db.commit()

    first = run_keyword_backfill(db, limit=1, dry_run=False)
    second = run_keyword_backfill(db, limit=10, dry_run=False, resume=True)
    rerun = run_keyword_backfill(db, limit=10, dry_run=False, resume=True)

    assert first.papers_processed == 1
    assert second.papers_processed == 1
    assert rerun.links_written == 0
    assert db.get(PaperMethodEvidence, (1, 10, "keyword")) is not None
    assert db.get(PaperMethodEvidence, (2, 11, "keyword")) is not None
    run = db.query(MethodKeywordBackfillRun).one()
    assert run.status == "complete"
    assert run.cursor_paper_id == 2
    assert run.eligible_papers == 2
    assert run.processed_papers == 2

    db.add(_paper(3, "A new CLIP paper", date(2026, 1, 1)))
    db.commit()
    appended = run_keyword_backfill(db, limit=10, dry_run=False, resume=True)

    db.refresh(run)
    assert appended.papers_processed == 1
    assert run.status == "complete"
    assert run.cursor_paper_id == 3
    assert run.eligible_papers == 3
    assert run.processed_papers == 3


def test_keyword_catalog_version_tracks_matcher_inputs_not_display_names():
    db = _session()
    method = Method(id=10, name="Display A", slug="a", keywords="Alpha")
    db.add(method)
    db.commit()
    original, _ = keyword_catalog_rows(db)

    method.name = "Display B"
    db.commit()
    renamed, _ = keyword_catalog_rows(db)
    method.keywords = "Beta"
    db.commit()
    changed_keywords, _ = keyword_catalog_rows(db)

    assert renamed == original
    assert changed_keywords != original


def test_changed_keyword_catalog_supersedes_incomplete_run():
    db = _session()
    method = Method(id=10, name="CLIP", slug="clip", keywords="CLIP")
    db.add_all([method, _paper(1, "A CLIP paper", date(2026, 1, 1))])
    db.commit()

    run_keyword_backfill(db, limit=1, dry_run=False)
    previous = db.query(MethodKeywordBackfillRun).one()
    previous.status = "running"
    previous.completed_at = None
    db.commit()

    method.keywords = "contrastive language image pretraining"
    db.commit()
    run_keyword_backfill(db, limit=1, dry_run=False, resume=True)

    db.refresh(previous)
    assert previous.status == "failed"
    assert "superseded" in previous.last_error
    assert db.query(MethodKeywordBackfillRun).count() == 2


class _ReferenceClient:
    def __init__(self):
        self.api_calls = 0
        self.api_errors = 0
        self.rate_limit_hits = 0

    def iter_references(self, identifier):
        self.api_calls += 1
        if identifier == "arXiv:2601.00003":
            return iter(
                [
                    SimpleNamespace(semantic_scholar_id="source-a", arxiv_id=None),
                    SimpleNamespace(semantic_scholar_id="source-b", arxiv_id=None),
                ]
            )
        return iter([])


class _FailingReferenceClient:
    api_calls = 0
    api_errors = 0
    rate_limit_hits = 0

    def iter_references(self, _identifier):
        self.api_calls += 1
        self.api_errors += 1
        return iter([])


class _PartialFailingReferenceClient(_ReferenceClient):
    def iter_references(self, _identifier):
        self.api_calls += 2
        yield SimpleNamespace(semantic_scholar_id="source-a", arxiv_id=None)
        self.api_errors += 1


class _RetriedReferenceClient(_ReferenceClient):
    def __init__(self):
        super().__init__()
        self.failed_requests = 0
        self.retry_attempts = 0

    def iter_references(self, _identifier):
        self.api_calls += 2
        self.rate_limit_hits += 1
        self.retry_attempts += 1
        return iter([SimpleNamespace(semantic_scholar_id="source-a", arxiv_id=None)])


def test_reference_backfill_fetches_each_paper_once_for_multiple_methods():
    db = _session()
    db.add_all(
        [
            _paper(1, "Source A", date(2026, 1, 1)),
            _paper(2, "Source B", date(2026, 1, 2)),
            _paper(3, "Citing paper", date(2026, 1, 3)),
        ]
    )
    db.flush()
    db.get(Paper, 1).semantic_scholar_id = "source-a"
    db.get(Paper, 2).semantic_scholar_id = "source-b"
    db.add_all(
        [
            Method(id=10, name="A", slug="a", source_paper_id=1),
            Method(id=11, name="B", slug="b", source_paper_id=2),
        ]
    )
    db.commit()
    client = _ReferenceClient()

    stats = run_reference_backfill(
        db,
        client,
        method_ids=[10, 11],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    assert client.api_calls == 3
    assert stats.matches == 2
    assert db.get(PaperMethodEvidence, (3, 10, "reference")) is not None
    assert db.get(PaperMethodEvidence, (3, 11, "reference")) is not None
    assert all(
        row.status == "complete" for row in db.query(MethodReferenceBackfillMonth).all()
    )


def test_reference_backfill_links_all_methods_that_share_one_source():
    db = _session()
    source = _paper(1, "Shared source", date(2026, 1, 1))
    source.semantic_scholar_id = "shared-source"
    db.add_all(
        [
            source,
            _paper(2, "Citing paper", date(2026, 1, 2)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
            Method(id=11, name="B", slug="b", source_paper_id=1),
        ]
    )
    db.commit()

    class Client(_ReferenceClient):
        def iter_references(self, identifier):
            self.api_calls += 1
            if identifier == "arXiv:2601.00002":
                return iter(
                    [
                        SimpleNamespace(
                            semantic_scholar_id="shared-source", arxiv_id=None
                        )
                    ]
                )
            return iter([])

    stats = run_reference_backfill(
        db,
        Client(),
        method_ids=[10, 11],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    assert stats.matches == 2
    assert stats.links_written == 2
    assert db.get(PaperMethodEvidence, (2, 10, "reference")) is not None
    assert db.get(PaperMethodEvidence, (2, 11, "reference")) is not None


def test_reference_backfill_uses_batched_openalex_ids_and_records_provider():
    db = _session()
    db.add_all(
        [
            _paper(1, "Source", date(2026, 1, 1)),
            _paper(2, "Citing paper", date(2026, 1, 2)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
        ]
    )
    db.commit()

    class OpenAlexClient:
        provider_name = "openalex"
        api_calls = 0
        api_errors = 0
        rate_limit_hits = 0
        failed_requests = 0
        retry_attempts = 0

        def fetch_works(self, arxiv_ids):
            self.api_calls += 1
            ids = set(arxiv_ids)
            return OpenAlexWorkBatch(
                work_ids_by_arxiv={
                    arxiv_id: {f"https://openalex.org/{arxiv_id}"} for arxiv_id in ids
                },
                references_by_arxiv={"2601.00002": {"https://openalex.org/2601.00001"}},
            )

    stats = run_reference_backfill(
        db,
        OpenAlexClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    evidence = db.get(PaperMethodEvidence, (2, 10, "reference"))
    assert stats.matches == 1
    assert stats.api_calls == 2
    assert evidence is not None
    assert evidence.details == {
        "workload_key": "openalex",
        "provider": "openalex",
    }


def test_openalex_missing_work_is_counted_as_unresolvable_coverage():
    db = _session()
    db.add_all(
        [
            _paper(1, "Source", date(2026, 1, 1)),
            _paper(2, "Missing from OpenAlex", date(2026, 1, 2)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
        ]
    )
    db.commit()

    class OpenAlexClient:
        provider_name = "openalex"
        api_calls = 0
        api_errors = 0
        rate_limit_hits = 0
        failed_requests = 0
        retry_attempts = 0

        def fetch_works(self, arxiv_ids):
            self.api_calls += 1
            ids = set(arxiv_ids)
            if ids == {"2601.00001"}:
                return OpenAlexWorkBatch(
                    work_ids_by_arxiv={"2601.00001": {"https://openalex.org/source"}}
                )
            return OpenAlexWorkBatch(
                work_ids_by_arxiv={"2601.00001": {"https://openalex.org/source"}}
            )

    stats = run_reference_backfill(
        db,
        OpenAlexClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.papers_failed == 0
    assert stats.papers_unresolvable == 1
    assert progress.processed_papers == 1
    assert progress.unresolvable_papers == 1
    assert progress.cursor_paper_id == 2
    assert progress.retryable_failures == 0
    assert progress.status == "complete"


def test_openalex_skips_one_unresolved_method_source_when_others_resolve():
    db = _session()
    db.add_all(
        [
            _paper(1, "Resolved source", date(2026, 1, 1)),
            _paper(2, "Unresolved source", date(2026, 1, 1)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
            Method(id=11, name="B", slug="b", source_paper_id=2),
        ]
    )
    db.commit()

    class OpenAlexClient:
        provider_name = "openalex"
        api_calls = 0
        api_errors = 0
        rate_limit_hits = 0
        failed_requests = 0
        retry_attempts = 0

        def fetch_works(self, arxiv_ids):
            self.api_calls += 1
            ids = set(arxiv_ids)
            return OpenAlexWorkBatch(
                work_ids_by_arxiv=(
                    {"2601.00001": {"https://openalex.org/source"}}
                    if ids == {"2601.00001", "2601.00002"}
                    else {}
                )
            )

    messages = []
    stats = run_reference_backfill(
        db,
        OpenAlexClient(),
        method_ids=[10, 11],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=True,
        log=messages.append,
    )

    assert stats.papers_failed == 0
    assert any("arXiv:2601.00002" in message for message in messages)


def test_reference_backfill_counts_excluded_match_as_processed_not_matched():
    db = _session()
    source = _paper(1, "Source", date(2026, 1, 1))
    source.semantic_scholar_id = "source-a"
    db.add_all(
        [
            source,
            _paper(3, "Excluded citing paper", date(2026, 1, 3)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
            PaperMethodExclusion(paper_id=3, method_id=10),
        ]
    )
    db.commit()

    stats = run_reference_backfill(
        db,
        _ReferenceClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.matches == 0
    assert stats.links_written == 0
    assert progress.processed_papers == 2
    assert progress.matched_papers == 0
    assert progress.status == "complete"
    assert db.get(PaperMethod, (3, 10)) is None


def test_failed_reference_lookup_does_not_advance_the_month_cursor():
    db = _session()
    paper = _paper(1, "Source", date(2026, 1, 1))
    paper.semantic_scholar_id = "source"
    db.add_all([paper, Method(id=10, name="A", slug="a", source_paper_id=1)])
    db.commit()

    stats = run_reference_backfill(
        db,
        _FailingReferenceClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.papers_failed == 1
    assert progress.processed_papers == 0
    assert progress.cursor_published_at is None
    assert progress.cursor_paper_id is None
    assert progress.retryable_failures == 1


def test_partially_fetched_reference_lookup_does_not_advance_or_write():
    db = _session()
    source = _paper(1, "Source", date(2026, 1, 1))
    source.semantic_scholar_id = "source-a"
    db.add_all([source, Method(id=10, name="A", slug="a", source_paper_id=1)])
    db.commit()

    stats = run_reference_backfill(
        db,
        _PartialFailingReferenceClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.papers_failed == 1
    assert stats.matches == 0
    assert progress.processed_papers == 0
    assert progress.cursor_published_at is None
    assert db.get(PaperMethodEvidence, (1, 10, "reference")) is None


def test_successful_retry_is_processed_instead_of_left_behind_cursor():
    db = _session()
    source = _paper(1, "Source", date(2026, 1, 1))
    source.semantic_scholar_id = "source-a"
    db.add_all([source, Method(id=10, name="A", slug="a", source_paper_id=1)])
    db.commit()

    stats = run_reference_backfill(
        db,
        _RetriedReferenceClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert stats.papers_failed == 0
    assert progress.processed_papers == 1
    assert progress.retryable_failures == 0
    assert progress.status == "complete"
    assert db.get(PaperMethodEvidence, (1, 10, "reference")) is not None


def test_reference_resume_starts_strictly_after_stored_tuple_and_latest_only():
    db = _session()
    source = _paper(1, "Source", date(2026, 1, 1))
    source.semantic_scholar_id = "source"
    old_version = _paper(4, "Old version", date(2026, 1, 4))
    old_version.is_latest_version = False
    db.add_all(
        [
            source,
            _paper(2, "Second", date(2026, 1, 2)),
            _paper(3, "Third", date(2026, 1, 3)),
            old_version,
            Method(id=10, name="A", slug="a", source_paper_id=1),
        ]
    )
    db.commit()

    class RecordingClient(_ReferenceClient):
        def __init__(self):
            super().__init__()
            self.identifiers = []

        def iter_references(self, identifier):
            self.api_calls += 1
            self.identifiers.append(identifier)
            return iter([])

    first_client = RecordingClient()
    run_reference_backfill(
        db,
        first_client,
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=2,
        dry_run=False,
    )
    second_client = RecordingClient()
    run_reference_backfill(
        db,
        second_client,
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
        resume=True,
    )

    assert first_client.identifiers == ["source", "arXiv:2601.00002"]
    assert second_client.identifiers == ["arXiv:2601.00003"]
    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert progress.eligible_papers == 3
    assert progress.processed_papers == 3
    assert progress.status == "complete"

    db.add(_paper(5, "Late import behind completed cursor", date(2026, 1, 1)))
    db.commit()
    refresh_client = RecordingClient()
    run_reference_backfill(
        db,
        refresh_client,
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
        resume=True,
    )
    db.refresh(progress)
    assert progress.eligible_papers == 4
    assert progress.processed_papers == 4
    assert progress.status == "complete"
    assert refresh_client.identifiers == [
        "source",
        "arXiv:2601.00005",
        "arXiv:2601.00002",
        "arXiv:2601.00003",
    ]


def test_new_paper_behind_reference_cursor_prevents_premature_completion():
    db = _session()
    source = _paper(1, "Source", date(2026, 1, 2))
    source.semantic_scholar_id = "source"
    db.add_all(
        [
            source,
            _paper(2, "Later paper", date(2026, 1, 3)),
            Method(id=10, name="A", slug="a", source_paper_id=1),
        ]
    )
    db.commit()

    class ImportingClient(_ReferenceClient):
        def iter_references(self, identifier):
            self.api_calls += 1
            if self.api_calls == 2:
                db.add(_paper(3, "Imported behind cursor", date(2026, 1, 1)))
                db.flush()
            return iter([])

    run_reference_backfill(
        db,
        ImportingClient(),
        method_ids=[10],
        month_from=date(2026, 1, 1),
        month_to=date(2026, 1, 1),
        limit=10,
        dry_run=False,
    )

    progress = db.get(MethodReferenceBackfillMonth, (10, date(2026, 1, 1)))
    assert progress.eligible_papers == 3
    assert progress.status == "pending"
    assert progress.processed_papers == 0
    assert progress.cursor_published_at is None


def test_undated_audit_groups_evidence_and_reports_a_sample():
    db = _session()
    db.add_all([_paper(1, "Undated"), Method(id=10, name="A", slug="a")])
    db.commit()
    upsert_evidence_links(
        db, [{"paper_id": 1, "method_id": 10}], evidence_type="keyword"
    )
    db.commit()

    audit = audit_undated_method_links(db, sample_size=1)

    assert audit["total"] == 1
    assert audit["grouped"] == [
        {"source": "arxiv", "has_arxiv_id": True, "paper_count": 1}
    ]
    assert audit["sample"][0]["id"] == 1


def test_method_trend_returns_more_than_ten_years_without_an_override():
    db = _session()
    db.add(Method(id=10, name="Long-lived", slug="long-lived", introduced_year=2000))
    db.commit()

    trend = MethodTrendService(db).get_method_trend(
        "long-lived", today=date(2026, 7, 29)
    )

    assert trend.history_months == 319
    assert trend.history[0].start_date == date(2000, 1, 1)
    assert trend.history[-1].start_date == date(2026, 7, 1)
