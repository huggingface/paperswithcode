from datetime import date, timedelta
from types import SimpleNamespace

from backend.models.papers import Paper, PaperSummary
from backend.services.paper_service import PaperService


class FakeRetrieval:
    applied_mode = "keyword"

    def __init__(self, papers):
        self.papers = papers
        self.calls = []

    def search_db_papers(self, query, limit, **kwargs):
        self.calls.append((query, limit, kwargs))
        return self.papers[:limit]


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_args):
        return FakeQuery(self.rows)


def build_service():
    today = date(2026, 8, 25)
    summaries = [
        PaperSummary(
            id=str(index),
            title=f"Paper {index}",
            arxiv_id=None if index == 100 else f"2608.{index:05d}",
            source="external" if index == 100 else "arxiv",
            source_url="https://example.com/report" if index == 100 else None,
            authors=["Author"],
            published=today - timedelta(days=index % 17),
            citation_count=(index * 13) % 97,
        )
        for index in range(1, 102)
    ]
    rows = [
        SimpleNamespace(
            id=int(summary.id),
            date_published=summary.published,
            citation_count=summary.citation_count,
        )
        for summary in summaries
    ]
    retrieval = FakeRetrieval(rows)
    service = object.__new__(PaperService)
    service.db = FakeDb(rows)
    service._retrieval_service = lambda: retrieval
    service.hydrate_cards = lambda selected, include_resources: [
        Paper(
            id=str(row.id),
            title=f"Paper {row.id}",
            authors=["Author"],
            source="external" if row.id == 100 else "arxiv",
            source_url="https://example.com/report" if row.id == 100 else None,
        )
        for row in selected
    ]
    return service, retrieval


def test_search_feed_uses_one_capped_pool_for_every_sort_and_hydrates_one_page():
    service, retrieval = build_service()
    relevance = service.search_papers_feed("needle", page=1, order_by="relevance")
    newest = service.search_papers_feed("needle", page=1, order_by="date_published")
    cited = service.search_papers_feed("needle", page=1, order_by="citation_count")

    assert relevance.cap == 100
    assert relevance.cap_reached is True
    assert relevance.next_page == 2
    assert len(relevance.results) == 20
    assert len({paper.id for paper in relevance.results}) == 20
    assert {paper.id for paper in newest.results}.issubset(
        {str(i) for i in range(1, 101)}
    )
    assert {paper.id for paper in cited.results}.issubset(
        {str(i) for i in range(1, 101)}
    )
    assert all(call[1] == 101 for call in retrieval.calls)


def test_search_feed_forwards_pre_ranking_filters_and_reports_keyword_fallback():
    service, retrieval = build_service()
    result = service.search_papers_feed(
        "needle",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 25),
        has_code=True,
        has_hf_artifacts=True,
    )

    kwargs = retrieval.calls[0][2]
    assert kwargs["start_date"] == date(2026, 8, 1)
    assert kwargs["end_date"] == date(2026, 8, 25)
    assert kwargs["has_code"] is True
    assert kwargs["has_hf_artifacts"] is True
    assert result.requested_mode == "hybrid"
    assert result.applied_mode == "keyword"
    assert result.applied_filters == {
        "start_date": "2026-08-01",
        "end_date": "2026-08-25",
        "has_code": "true",
        "has_hf_artifacts": "true",
    }
