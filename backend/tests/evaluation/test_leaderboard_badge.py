from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import papers
from backend.services.badge_service import (
    LeaderboardBadgePlacement,
    LeaderboardBadgeTarget,
    leaderboard_rank_message,
    render_leaderboard_badge,
    resolve_leaderboard_badge_target,
)
from backend.utils.exceptions import PaperNotFoundError


def _rank(value: int, dataset_name: str = "Benchmark", evaluation_id: str = "1"):
    return SimpleNamespace(
        best_rank=value,
        dataset_name=dataset_name,
        evaluation_id=evaluation_id,
    )


class _QueryResult:
    def __init__(self, result):
        self.result = result

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class _SequencedDatabase:
    def __init__(self, *results):
        self.results = list(results)

    def query(self, *args, **kwargs):
        return _QueryResult(self.results.pop(0))


def test_resolver_returns_existing_live_evaluation():
    db = _SequencedDatabase((7, 1, "Benchmark", "benchmark", "task"))

    target = resolve_leaderboard_badge_target(
        db,
        paper_id=42,
        evaluation_id=7,
    )

    assert target == LeaderboardBadgeTarget(
        placement=LeaderboardBadgePlacement("Benchmark", 1),
        evaluation_id=7,
        task_slug="task",
        dataset_slug="benchmark",
    )


def test_resolver_follows_replacement_on_the_same_leaderboard():
    tombstone = SimpleNamespace(
        task_id=2,
        dataset_id=3,
        task_slug="task",
        dataset_slug="benchmark",
        dataset_name="Benchmark",
    )
    db = _SequencedDatabase(
        None,
        tombstone,
        (8, 2, "Benchmark", "benchmark", "task"),
    )

    target = resolve_leaderboard_badge_target(
        db,
        paper_id=42,
        evaluation_id=7,
    )

    assert target.evaluation_id == 8
    assert target.placement.best_rank == 2
    assert target.retired is False


def test_resolver_returns_retired_target_without_replacement():
    tombstone = SimpleNamespace(
        task_id=None,
        dataset_id=None,
        task_slug="task",
        dataset_slug="retired-benchmark",
        dataset_name="Retired Benchmark",
    )
    db = _SequencedDatabase(None, tombstone, None)

    target = resolve_leaderboard_badge_target(
        db,
        paper_id=42,
        evaluation_id=7,
    )

    assert target.evaluation_id is None
    assert target.retired is True
    assert target.placement.dataset_name == "Retired Benchmark"


def test_rank_message_names_each_top_three_benchmark():
    assert (
        leaderboard_rank_message([_rank(3, "RealSR"), _rank(1, "DIV2K-Val")])
        == "SOTA on DIV2K-Val · #3 on RealSR"
    )
    assert leaderboard_rank_message([]) == "unranked"


def test_rank_message_keeps_showing_a_placement_below_top_three():
    placement = LeaderboardBadgePlacement(dataset_name="RealSR", best_rank=4)

    assert leaderboard_rank_message([placement]) == "#4 on RealSR"


def test_retired_badge_names_the_benchmark_and_uses_neutral_color():
    placement = LeaderboardBadgePlacement(
        dataset_name="VisualMRC",
        best_rank=None,
        retired=True,
    )

    svg = render_leaderboard_badge([placement])

    assert "result retired on VisualMRC" in svg
    assert "#8a8f98" in svg


def test_svg_is_accessible_and_uses_ranked_color():
    svg = render_leaderboard_badge([_rank(1, "DIV2K-Val"), _rank(3, "RealSR")])

    assert (
        "Papers with Code leaderboard ranking: SOTA on DIV2K-Val · #3 on RealSR" in svg
    )
    assert 'role="img"' in svg
    assert "#16837a" in svg


def test_badge_endpoint_returns_live_svg_for_requested_evaluation(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            assert paper_id == "2605.23264"
            return SimpleNamespace(
                id="42",
                source="arxiv",
                arxiv_id="2605.23264",
                leaderboard_ranks=[
                    _rank(1, "DIV2K-Val", "12885"),
                    _rank(3, "RealSR", "12886"),
                ],
            )

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    monkeypatch.setattr(
        papers,
        "resolve_leaderboard_badge_target",
        lambda *args, **kwargs: LeaderboardBadgeTarget(
            placement=LeaderboardBadgePlacement("DIV2K-Val", 1),
            evaluation_id=12885,
            task_slug="super-resolution",
            dataset_slug="div2k-val",
        ),
    )
    response = papers.get_paper_leaderboard_badge(
        "2605.23264", evaluation_id=12885, db=object()
    )

    assert response.media_type == "image/svg+xml"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert b"SOTA" in response.body
    assert b"RealSR" not in response.body


def test_badge_endpoint_preserves_paper_summary_without_evaluation(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            return SimpleNamespace(
                id="42",
                source="arxiv",
                arxiv_id=paper_id,
                leaderboard_ranks=[
                    _rank(1, "DIV2K-Val", "12885"),
                    _rank(3, "RealSR", "12886"),
                ],
            )

    monkeypatch.setattr(papers, "PaperService", FakePaperService)

    response = papers.get_paper_leaderboard_badge(
        "2605.23264", evaluation_id=None, db=object()
    )

    assert b"SOTA on DIV2K-Val" in response.body
    assert b"#3 on RealSR" in response.body


def test_badge_endpoint_returns_retired_svg_for_deleted_evaluation(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            return SimpleNamespace(
                id="42",
                source="arxiv",
                arxiv_id=paper_id,
                leaderboard_ranks=[],
            )

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    monkeypatch.setattr(
        papers,
        "resolve_leaderboard_badge_target",
        lambda *args, **kwargs: LeaderboardBadgeTarget(
            placement=LeaderboardBadgePlacement("VisualMRC", None, retired=True),
            evaluation_id=None,
            task_slug="document-understanding",
            dataset_slug="visualmrc",
        ),
    )

    response = papers.get_paper_leaderboard_badge(
        "2307.02499", evaluation_id=17984, db=object()
    )

    assert response.status_code == 200
    assert b"result retired on VisualMRC" in response.body


def test_badge_link_redirects_to_current_replacement(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            return SimpleNamespace(id="42", source="arxiv", arxiv_id=paper_id)

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    monkeypatch.setattr(
        papers,
        "resolve_leaderboard_badge_target",
        lambda *args, **kwargs: LeaderboardBadgeTarget(
            placement=LeaderboardBadgePlacement("AI2D", 2),
            evaluation_id=19001,
            task_slug="image-understanding",
            dataset_slug="ai2d",
        ),
    )

    response = papers.get_paper_leaderboard_badge_link(
        "2601.10611", evaluation_id=9521, db=object()
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/benchmark/ai2d?task=image-understanding&eval=19001"
    )
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_badge_link_redirects_retired_result_to_paper(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            return SimpleNamespace(id="42", source="arxiv", arxiv_id=paper_id)

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    monkeypatch.setattr(
        papers,
        "resolve_leaderboard_badge_target",
        lambda *args, **kwargs: LeaderboardBadgeTarget(
            placement=LeaderboardBadgePlacement("VisualMRC", None, retired=True),
            evaluation_id=None,
            task_slug="document-understanding",
            dataset_slug="visualmrc",
        ),
    )

    response = papers.get_paper_leaderboard_badge_link(
        "2307.02499", evaluation_id=17984, db=object()
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/paper/2307.02499#results"


def test_badge_link_returns_404_for_unknown_or_wrong_paper_evaluation(monkeypatch):
    class FakePaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            return SimpleNamespace(id="42", source="arxiv", arxiv_id=paper_id)

    monkeypatch.setattr(papers, "PaperService", FakePaperService)
    monkeypatch.setattr(
        papers,
        "resolve_leaderboard_badge_target",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc:
        papers.get_paper_leaderboard_badge_link(
            "2601.10611", evaluation_id=999999, db=object()
        )

    assert exc.value.status_code == 404


def test_badge_endpoint_returns_404_for_unknown_paper(monkeypatch):
    class MissingPaperService:
        def __init__(self, db):
            pass

        def get_paper_by_id_or_arxiv(self, paper_id):
            raise PaperNotFoundError("missing")

    monkeypatch.setattr(papers, "PaperService", MissingPaperService)
    with pytest.raises(HTTPException) as exc:
        papers.get_paper_leaderboard_badge("missing", evaluation_id=None, db=object())

    assert exc.value.status_code == 404
