"""Tests for the feature-flagged trending ranking mode (rollback switch).

Verify that PWC_TRENDING_RANKING_MODE selects the right SQL: the GitHub-only
ranking (default + rollback path) vs the composite paper score, and that an
unset/invalid value safely falls back to GitHub.
"""

from backend.models.papers import Papers
from backend.services.paper_service import PaperService


class _EmptyResult:
    def fetchall(self):
        return []


class _FakeDatabase:
    def __init__(self):
        self.captured = {}

    def execute(self, statement, params):
        self.captured["sql"] = str(statement)
        self.captured["params"] = params
        return _EmptyResult()


def _service():
    return PaperService(_FakeDatabase())


def test_build_query_github_mode():
    svc = _service()
    sql, params = svc._build_trending_query(
        mode="github",
        search=None,
        published_after=None,
        published_before=None,
        conference=None,
        latest_only=True,
        page=1,
        page_size=30,
    )
    sql_str = str(sql)
    assert "pr.is_official = TRUE" in sql_str
    assert "r.trending_score" in sql_str
    # GitHub path requires a repo when not searching.
    assert "r.id IS NOT NULL" in sql_str
    assert params["limit"] == 30
    assert params["offset"] == 0


def test_build_query_composite_mode():
    svc = _service()
    sql, params = svc._build_trending_query(
        mode="composite",
        search="vision",
        published_after=None,
        published_before=None,
        conference=None,
        latest_only=True,
        page=2,
        page_size=20,
    )
    sql_str = str(sql)
    # Composite ranks by the paper-level score.
    assert "p.trending_score" in sql_str
    # HF-only papers (NULL repo) are kept, not deduped away.
    assert "repository_id IS NULL OR repo_paper_rank = 1" in sql_str
    assert params["search_term"] == "%vision%"
    assert params["limit"] == 20
    assert params["offset"] == 20


def test_unknown_mode_falls_back_to_github():
    svc = _service()
    github_sql, _ = svc._build_trending_query(
        "github", None, None, None, None, True, 1, 10
    )
    for bad in ("", "GITHUB", "hf", "anything-else", None):
        sql, _ = svc._build_trending_query(bad, None, None, None, None, True, 1, 10)
        assert str(sql) == str(github_sql)


def test_get_trending_papers_respects_composite_setting(monkeypatch):
    svc = _service()
    monkeypatch.setattr(svc.settings, "trending_ranking_mode", "composite")
    result = svc._get_trending_papers(page=1, page_size=20)
    assert isinstance(result, Papers)
    assert "p.trending_score" in svc.db.captured["sql"]
    assert "repository_id IS NULL OR repo_paper_rank = 1" in svc.db.captured["sql"]


def test_get_trending_papers_defaults_to_github(monkeypatch):
    svc = _service()
    monkeypatch.setattr(svc.settings, "trending_ranking_mode", "github")
    svc._get_trending_papers(page=1, page_size=20)
    sql = svc.db.captured["sql"]
    assert "pr.is_official = TRUE" in sql
    assert "r.trending_score" in sql
