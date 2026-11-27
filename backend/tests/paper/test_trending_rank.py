from datetime import date

import pytest

from backend.models.papers import Paper
from backend.services import paper_trending_rank_service as service
from backend.services.paper_service import PaperService


@pytest.fixture
def trending_calls(monkeypatch):
    calls = []

    def fake_trending_paper_ids(
        self, limit, published_after=None, published_before=None
    ):
        calls.append((limit, published_after, published_before))
        return [30, 10, 20]

    monkeypatch.setattr(PaperService, "trending_paper_ids", fake_trending_paper_ids)
    monkeypatch.setattr(service, "_today", lambda: date(2026, 11, 27))
    service.reset_trending_rank_cache()
    yield calls
    service.reset_trending_rank_cache()


def _paper(paper_id: str, latest: bool = True) -> Paper:
    return Paper(id=paper_id, title="T", authors=[], is_latest_version=latest)


def test_rank_matches_default_trending_feed_window(trending_calls):
    assert service.with_trending_rank(None, _paper("10")).trending_rank == 2
    assert service.with_trending_rank(None, _paper("30")).trending_rank == 1
    assert service.with_trending_rank(None, _paper("99")).trending_rank is None
    assert trending_calls == [(25, date(2026, 11, 21), date(2026, 11, 27))]


def test_older_versions_get_no_rank(trending_calls):
    assert (
        service.with_trending_rank(None, _paper("10", latest=False)).trending_rank
        is None
    )
    assert trending_calls == []


def test_cache_refreshes_on_a_new_day(trending_calls, monkeypatch):
    service.with_trending_rank(None, _paper("10"))
    monkeypatch.setattr(service, "_today", lambda: date(2026, 11, 28))
    service.with_trending_rank(None, _paper("10"))
    assert [call[1] for call in trending_calls] == [
        date(2026, 11, 21),
        date(2026, 11, 22),
    ]
