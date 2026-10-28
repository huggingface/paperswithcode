from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.routers import discovery_pages
from backend.routers.search_discovery import robots_policy
from backend.services.discovery_html_service import render_discovery_document
from backend.services.public_page_markdown_service import render_discovery_markdown
from backend.services.discovery_page_service import (
    DiscoveryLink,
    DiscoveryPage,
    DiscoveryPageService,
    DiscoveryPaperLink,
    STATIC_INDEX_PAGES,
)


def _page(*, robots: str = "index,follow") -> DiscoveryPage:
    return DiscoveryPage(
        kind="Task",
        canonical_path="/tasks/safe",
        title="Safe task",
        description='A <useful> "description"',
        heading="<Safe & sound>",
        breadcrumbs=(DiscoveryLink("/", "Home"),),
        entity_links=(DiscoveryLink("/benchmark/test", "Test & benchmark"),),
        paper_links=(
            DiscoveryPaperLink(
                "2607.24653",
                '<script>alert("x")</script>',
                date(2026, 7, 27),
                "Tagged <here>",
            ),
        ),
        robots=robots,
    )


@pytest.fixture
def client(monkeypatch):
    app = create_app()

    def database():
        yield object()

    app.dependency_overrides[get_database_session] = database
    monkeypatch.setattr(
        discovery_pages,
        "load_index_html",
        lambda: (
            "<!doctype html><html><head><title>Generic</title>"
            '<meta name="description" content="Generic"></head><body>'
            '<div id="root"></div><script src="/assets/app.js"></script></body></html>'
        ),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_robots_policies_are_environment_aware_and_end_with_newline():
    production, production_headers = robots_policy("production")
    staging, staging_headers = robots_policy("staging")
    assert production.endswith("\n")
    assert production.count("Sitemap: https://paperswithcode.co/sitemap.xml") == 1
    assert "Allow: /" in production
    assert staging == "User-agent: *\nDisallow: /\n"
    assert "Sitemap:" not in staging
    assert staging_headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "X-Robots-Tag" not in production_headers


def _query(*, one=None, rows=()):
    result = MagicMock()
    for method in (
        "filter",
        "join",
        "outerjoin",
        "order_by",
        "group_by",
        "limit",
    ):
        getattr(result, method).return_value = result
    result.one_or_none.return_value = one
    result.all.return_value = rows
    return result


@pytest.mark.parametrize("linked", [True, False])
def test_empty_task_benchmark_requires_association(client, linked):
    """A configured leaderboard can render before its first score is imported."""
    tasks = [(1, "other-task", "Other task")]
    if linked:
        tasks.insert(0, (775, "audio-editing", "Audio editing"))
    db = MagicMock()
    db.query.side_effect = [
        _query(one=SimpleNamespace(id=2590, name="MMAE", description="Audio edits")),
        _query(one=SimpleNamespace(id=775, slug="audio-editing")),
        _query(rows=tasks),
        _query(),  # evaluations
        _query(),  # configured leaderboard metrics
    ]
    client.app.dependency_overrides[get_database_session] = lambda: db

    response = client.get("/benchmark/mmae?task=audio-editing")

    assert response.status_code == (200 if linked else 404)
    if linked:
        assert "MMAE" in response.text
        assert 'id="root"' in response.text
        assert "Page not found" not in response.text


def _evaluation(id, paper_id, model, metrics, best_metric, best_rank, task_id=7):
    return SimpleNamespace(
        id=id,
        paper_id=paper_id,
        task_id=task_id,
        model_name=model,
        harness=None,
        metrics=metrics,
        best_metric=best_metric,
        best_rank=best_rank,
    )


def _paper_row(id, title, eligible=True):
    return SimpleNamespace(
        id=id,
        title=title,
        source="arxiv",
        arxiv_id=f"2601.0000{id}",
        date_published=date(2026, 1, id),
        eligible=eligible,
    )


def test_benchmark_page_ranks_leaderboard_like_the_spa():
    """Stored ranks are stale; the page re-ranks by value like the SPA does."""
    db = MagicMock()
    db.query.side_effect = [
        _query(
            one=SimpleNamespace(
                id=19, name="MMLU", description="**Massive** multitask test."
            )
        ),
        _query(rows=[(7, "multi-task-language-understanding", "Language")]),
        _query(
            rows=[
                _evaluation(1, 1, "Old leader", {"Accuracy": "80.5"}, "Accuracy", 1),
                _evaluation(
                    2, 2, "New leader", {"Accuracy": "91.2 ± 0.1"}, "Accuracy", 2
                ),
                _evaluation(3, 3, "Tied", {"Accuracy": 80.5}, "Accuracy", 3),
                _evaluation(4, 4, "Unscored", {"F1": "70"}, "F1", None),
            ]
        ),
        _query(rows=[(7, "Accuracy"), (7, "F1")]),
        _query(rows=[("Accuracy", "higher_is_better")]),
        _query(
            rows=[
                _paper_row(1, "Old paper"),
                _paper_row(2, "New paper"),
                _paper_row(3, "Tied paper"),
                _paper_row(4, "Hidden paper", eligible=False),
            ]
        ),
    ]

    page = DiscoveryPageService(db).benchmark("mmlu")

    assert page.title == (
        "MMLU Leaderboard: state of the art results | Papers with Code"
    )
    board = page.leaderboard
    assert board.metric == "Accuracy"
    assert [(row.rank, row.model, row.score) for row in board.rows] == [
        (1, "New leader", "91.2 ± 0.1"),
        (2, "Old leader", "80.5"),
        (2, "Tied", "80.5"),
        (None, "Unscored", None),
    ]
    assert board.rows[0].paper_route_identifier == "2601.00002"
    assert board.rows[3].paper_route_identifier is None
    assert page.description.startswith(
        "New leader leads the MMLU leaderboard with Accuracy 91.2 ± 0.1."
    )
    assert len(page.description) <= 155
    assert page.body_markdown == "**Massive** multitask test."
    assert [link.href for link in page.breadcrumbs] == [
        "/",
        "/tasks",
        "/tasks/multi-task-language-understanding",
    ]
    assert page.robots == "index,follow"

    document = render_discovery_document(page)
    assert "<table>" in document
    assert "<strong>Massive</strong>" in document
    assert '<a href="/paper/2601.00002">New paper</a>' in document
    assert "Relevant papers" not in document
    assert 'href="/benchmark"' not in document


def test_task_page_renders_markdown_trends_and_benchmark_links(monkeypatch):
    monkeypatch.setattr(
        "backend.services.dataset_service.DatasetService._best_results_for_datasets",
        lambda *args, **kwargs: {},
    )
    db = MagicMock()
    db.query.side_effect = [
        _query(
            one=SimpleNamespace(
                id=2,
                parent_id=None,
                name="Object Detection",
                description=(
                    "Object detection finds **objects** in [images](/tasks/vision). "
                    + "It is used widely in robotics and driving. " * 6
                ),
                research_trends=["**Trend.** See [DETR](/paper/2005.12872)."],
            )
        ),
        _query(rows=[]),  # related tasks
        _query(rows=[(1, "coco", "COCO", 120), (2, "lvis", "LVIS", 0)]),
        _query(rows=[]),  # tagged papers
    ]

    page = DiscoveryPageService(db).task("object-detection")

    assert len(page.description) <= 155
    assert "**" not in page.description and "](" not in page.description
    assert page.description.startswith("Object detection finds objects in images.")
    assert [link.href for link in page.benchmark_links] == [
        "/benchmark/coco",
        "/benchmark/lvis",
    ]
    assert [link.href for link in page.breadcrumbs] == ["/", "/tasks"]

    document = render_discovery_document(page)
    assert '<a href="/tasks/vision">images</a>' in document
    assert "<strong>objects</strong>" in document
    assert '<a href="/paper/2005.12872">DETR</a>' in document
    assert '<a href="/benchmark/coco">COCO</a>' in document
    assert "**" not in document and "](" not in document


def _top_model_task_db(benchmarks, open_rows=()):
    db = MagicMock()
    db.query.side_effect = [
        _query(
            one=SimpleNamespace(
                id=2,
                parent_id=None,
                name="OCR",
                description="Optical character recognition reads text in images.",
                research_trends=[],
            )
        ),
        _query(rows=[]),  # related tasks
        _query(rows=benchmarks),
        _query(rows=[]),  # tagged papers
        _query(rows=list(open_rows)),  # open evaluations, best rank first
    ]
    return db


def test_task_page_summarizes_best_models(monkeypatch):
    calls = []

    def best_results(self, dataset_ids, task_ids, is_open=None):
        calls.append((dataset_ids, task_ids, is_open))
        return {
            1: {"metric": "Overall", "model_name": "Gemini 3 Pro"},
            3: {"metric": "Edit distance", "model_name": "GPT-6"},
        }

    monkeypatch.setattr(
        "backend.services.dataset_service.DatasetService._best_results_for_datasets",
        best_results,
    )
    db = _top_model_task_db(
        [
            (1, "olmocr-bench", "olmOCR-Bench", 40),
            (3, "omnidocbench", "OmniDocBench", 12),
            (4, "unscored", "Unscored", 0),
        ],
        open_rows=[
            # Leads a different metric leaderboard, so it is not the open leader.
            (1, "Tables", "Table Model"),
            (1, "Overall", "olmOCR <2>"),
            (1, "Overall", "Runner-up"),
        ],
    )

    page = DiscoveryPageService(db).task("ocr", today=date(2026, 10, 13))

    assert calls == [([1, 3], [2], None)]
    assert page.title == (
        "Best OCR Models (October 2026): leaderboards and papers | Papers with Code"
    )
    assert page.description.startswith(
        "Gemini 3 Pro leads olmOCR-Bench for OCR; the best open model there is "
        "olmOCR <2>."
    )
    assert "across 2 benchmarks" in page.description
    assert len(page.description) <= 155
    assert [(top.model, top.open_model) for top in page.top_models] == [
        ("Gemini 3 Pro", "olmOCR <2>"),
        ("GPT-6", None),
    ]

    document = render_discovery_document(page)
    assert '<h2 id="top-models-heading">Best OCR models</h2>' in document
    assert "as of October 2026" in document
    assert '<a href="/benchmark/olmocr-bench">olmOCR-Bench</a>' in document
    assert "olmOCR &lt;2&gt;" in document

    markdown = render_discovery_markdown(page)
    assert "## Best OCR models" in markdown
    assert (
        "| [olmOCR\\-Bench](https://paperswithcode.co/benchmark/olmocr-bench)"
        in markdown
    )


def test_task_page_with_open_leader_on_one_benchmark(monkeypatch):
    monkeypatch.setattr(
        "backend.services.dataset_service.DatasetService._best_results_for_datasets",
        lambda *args, **kwargs: {1: {"metric": "Overall", "model_name": "olmOCR"}},
    )
    db = _top_model_task_db(
        [(1, "olmocr-bench", "olmOCR-Bench", 40)],
        open_rows=[(1, "Overall", "olmOCR")],
    )

    page = DiscoveryPageService(db).task("ocr", today=date(2026, 10, 13))

    assert page.description.startswith(
        "olmOCR leads olmOCR-Bench for OCR. Compare the best OCR models across "
        "1 benchmark with"
    )


def test_task_page_without_evaluations_keeps_generic_title(monkeypatch):
    monkeypatch.setattr(
        "backend.services.dataset_service.DatasetService._best_results_for_datasets",
        lambda *args, **kwargs: pytest.fail("no evaluated benchmarks to summarize"),
    )
    db = _top_model_task_db([(4, "unscored", "Unscored", 0)])

    page = DiscoveryPageService(db).task("ocr")

    assert page.title == "OCR — papers and benchmarks | Papers with Code"
    assert page.top_models == ()
    assert "top-models-heading" not in render_discovery_document(page)


def test_discovery_shell_sets_per_page_social_tags(client, monkeypatch):
    monkeypatch.setattr(
        discovery_pages,
        "load_index_html",
        lambda: (
            "<!doctype html><html><head><title>Generic</title>"
            '<meta property="og:url" content="https://paperswithcode.co/" />'
            '<meta property="og:title" content="Papers with Code" />'
            '<meta name="twitter:description" content="Generic" />'
            '<meta property="og:image" content="https://paperswithcode.co/og.png" />'
            '</head><body><div id="root"></div></body></html>'
        ),
    )
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: _page())
    text = client.get("/tasks/safe").text
    assert text.count('property="og:url"') == 1
    assert (
        '<meta property="og:url" content="https://paperswithcode.co/tasks/safe">'
        in text
    )
    assert '<meta property="og:title" content="Safe task">' in text
    assert text.count('name="twitter:description"') == 1
    assert 'property="og:image"' in text


def test_robots_get_and_head_are_plain_text(client):
    get = client.get("/robots.txt")
    head = client.head("/robots.txt")
    assert get.status_code == head.status_code == 200
    assert get.headers["content-type"].startswith("text/plain")
    assert head.headers["content-type"].startswith("text/plain")
    assert "<html" not in get.text.lower()
    assert head.content == b""


def test_renderer_escapes_every_database_value():
    document = render_discovery_document(_page())
    assert '<main hidden data-pwc-initial-document="discovery">' in document
    assert "<script>" not in document
    assert "&lt;Safe &amp; sound&gt;" in document
    assert "&lt;script&gt;alert(" in document
    assert "Tagged &lt;here&gt;" in document
    assert document.count("<h1>") == 1


def test_entity_route_has_semantic_html_and_query_variant_policy(client, monkeypatch):
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: _page())
    response = client.get("/tasks/safe")
    variant = client.get("/tasks/safe?sort=oldest")
    assert response.status_code == 200
    assert 'data-pwc-initial-document="discovery"' in response.text
    assert (
        '<link rel="canonical" href="https://paperswithcode.co/tasks/safe">'
        in response.text
    )
    assert '<meta name="robots" content="index,follow">' in response.text
    assert response.text.count("<title>") == 1
    assert response.text.count('name="description"') == 1
    assert response.text.count('rel="canonical"') == 1
    assert '<meta name="robots" content="noindex,follow">' in variant.text
    assert response.headers["vary"] == "Accept"


def test_discovery_markdown_is_available_without_frontend_bundle(client, monkeypatch):
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: _page())
    monkeypatch.setattr(discovery_pages, "load_index_html", lambda: None)
    response = client.get("/tasks/safe", headers={"Accept": "text/markdown"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["vary"] == "Accept"
    assert response.headers["link"] == (
        '<https://paperswithcode.co/tasks/safe>; rel="canonical"'
    )
    assert response.headers["cache-control"].startswith("public, max-age=300")
    assert response.text.startswith("---\n")
    assert response.text.count("\n# ") == 1
    assert "\n# <Safe" not in response.text
    assert "<script>" not in response.text


def test_missing_discovery_page_keeps_html_error_for_markdown_accept(
    client, monkeypatch
):
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: None)
    response = client.get("/tasks/missing", headers={"Accept": "text/markdown"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")


def test_missing_entity_and_unknown_top_level_are_real_404s(client, monkeypatch):
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: None)
    monkeypatch.setattr(DiscoveryPageService, "organization", lambda self, slug: None)
    assert client.get("/tasks/missing").status_code == 404
    assert client.get("/definitely-not-an-organization").status_code == 404
    assert client.get("/api/not-a-route").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/papers",
        "/chat/abc",
        "/pdf/2606.23050",
        "/privacy",
        "/rate-limits",
        "/autonomous-operations",
        "/authorize-paper-edit/00000000-0000-0000-0000-000000000001",
    ],
)
def test_known_client_only_routes_keep_the_spa_shell(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


@pytest.mark.parametrize(
    "listing", ["all", "oral", "spotlight", "outstanding", "best-paper-finalists"]
)
def test_conference_listing_paths_render_the_spa_shell(client, monkeypatch, listing):
    calls = []

    def conference_listing(self, slug, name):
        calls.append((slug, name))
        return _page(robots="noindex,follow")

    monkeypatch.setattr(DiscoveryPageService, "conference_listing", conference_listing)
    response = client.get(f"/conferences/icml-2026/{listing}")
    assert response.status_code == 200
    assert '<script src="/assets/app.js"></script>' in response.text
    assert calls == [("icml-2026", listing)]


def test_conference_listing_for_unknown_conference_is_404(client, monkeypatch):
    monkeypatch.setattr(DiscoveryPageService, "conference", lambda self, slug: None)
    assert client.get("/conferences/missing/oral").status_code == 404


def test_legacy_aliases_redirect_permanently(client):
    assert client.get("/task/safe", follow_redirects=False).status_code == 301
    alias = client.get("/organizations/example", follow_redirects=False)
    assert alias.status_code == 301
    assert alias.headers["location"] == "/orgs/example"
    task_alias = client.get(
        "/organizations/example/safe?q=vision", follow_redirects=False
    )
    assert task_alias.status_code == 301
    assert task_alias.headers["location"] == "/orgs/example/safe?q=vision"
    markdown_alias = client.get(
        "/task/safe", headers={"Accept": "text/markdown"}, follow_redirects=False
    )
    assert markdown_alias.status_code == 301


def test_method_moved_to_task_redirects_to_the_task_page(client):
    response = client.get("/methods/continual-learning", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/tasks/continual-learning"


def test_merged_organization_slug_redirects_to_canonical_page(client):
    response = client.get("/orgs/googledeepmind?q=vision", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/orgs/google?q=vision"


def test_author_naming_an_organization_redirects_to_its_page(client, monkeypatch):
    monkeypatch.setattr(
        discovery_pages,
        "organization_slug_for_author",
        lambda db, author_id: "nvidia" if author_id == 92883 else None,
    )
    response = client.get("/authors/92883?has_code=true", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/orgs/nvidia?has_code=true"


@pytest.mark.parametrize(
    ("path", "method_name"),
    [
        ("/", "homepage"),
        ("/tasks/safe", "task"),
        ("/methods/safe", "method"),
        ("/benchmark/safe", "benchmark"),
        ("/conferences/safe", "conference"),
        ("/authors/7", "author"),
        ("/orgs/safe-org", "organization"),
        ("/astra-for-robotics", "astra_for_robotics"),
    ],
)
def test_discovery_page_classes_support_head(client, monkeypatch, path, method_name):
    monkeypatch.setattr(
        DiscoveryPageService, method_name, lambda self, *args, **kwargs: _page()
    )
    monkeypatch.setattr(
        discovery_pages, "organization_slug_for_author", lambda db, author_id: None
    )
    response = client.head(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["link"] == (
        '<https://paperswithcode.co/tasks/safe>; rel="canonical"'
    )
    assert response.content == b""


def test_discovery_markdown_head_matches_get(client, monkeypatch):
    monkeypatch.setattr(DiscoveryPageService, "task", lambda self, slug: _page())
    headers = {"Accept": "text/markdown"}
    get = client.get("/tasks/safe", headers=headers)
    head = client.head("/tasks/safe", headers=headers)
    assert head.status_code == get.status_code == 200
    assert head.headers["content-type"] == get.headers["content-type"]
    assert head.headers["vary"] == get.headers["vary"] == "Accept"
    assert head.headers["link"] == get.headers["link"]
    assert head.content == b""


def _astra_db(
    *, task=SimpleNamespace(id=11), method=SimpleNamespace(id=1041), papers=()
):
    """A MagicMock session whose query order mirrors ``astra_for_robotics``."""

    def query(*, one=None, rows=()):
        result = MagicMock()
        for chain in ("filter", "join", "order_by", "limit"):
            getattr(result, chain).return_value = result
        result.one_or_none.return_value = one
        result.all.return_value = rows
        return result

    db = MagicMock()
    db.query.side_effect = [query(one=task), query(one=method), query(rows=papers)]
    return db


def test_astra_collection_page_lists_papers_tagged_with_task_and_method():
    paper = SimpleNamespace(
        id=122059,
        source="external",
        arxiv_id=None,
        title="GPT-6 Astra on robotic manipulation",
        date_published=date(2026, 9, 4),
    )
    page = DiscoveryPageService(_astra_db(papers=[paper])).astra_for_robotics()

    assert page.kind == "Collection"
    assert page.canonical_path == "/astra-for-robotics"
    assert page.canonical_url == "https://paperswithcode.co/astra-for-robotics"
    assert page.heading == "GPT-6 Astra for Robotics"
    assert page.robots == "index,follow"
    assert [link.href for link in page.entity_links] == [
        "/methods/gpt-6-astra",
        "/tasks/robotics",
    ]
    assert [(p.route_identifier, p.title) for p in page.paper_links] == [
        ("122059", "GPT-6 Astra on robotic manipulation")
    ]


def test_astra_collection_page_without_taxonomy_rows_is_not_indexed():
    page = DiscoveryPageService(_astra_db(method=None)).astra_for_robotics()

    assert page.paper_links == ()
    assert page.robots == "noindex,follow"


def test_astra_collection_route_renders_server_side_document(client, monkeypatch):
    monkeypatch.setattr(
        DiscoveryPageService,
        "astra_for_robotics",
        lambda self: DiscoveryPage(
            kind="Collection",
            canonical_path="/astra-for-robotics",
            title="GPT-6 Astra for Robotics | Papers with Code",
            description="Astra robotics papers",
            heading="GPT-6 Astra for Robotics",
            breadcrumbs=(DiscoveryLink("/", "Home"),),
            entity_links=(DiscoveryLink("/methods/gpt-6-astra", "GPT-6 Astra"),),
            paper_links=(
                DiscoveryPaperLink(
                    "122059",
                    "GPT-6 Astra on robotic manipulation",
                    date(2026, 9, 4),
                    "GPT-6 Astra for robotics",
                ),
            ),
        ),
    )
    response = client.get("/astra-for-robotics")

    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert "<title>GPT-6 Astra for Robotics | Papers with Code</title>" in response.text
    assert (
        '<link rel="canonical" href="https://paperswithcode.co/astra-for-robotics">'
        in response.text
    )
    assert 'href="/paper/122059"' in response.text
    assert "Page not found" not in response.text


@pytest.mark.parametrize("path", sorted(STATIC_INDEX_PAGES))
def test_static_index_pages_have_own_title_description_and_canonical(client, path):
    response = client.get(path)

    assert response.status_code == 200
    body = response.text
    assert "<title>Generic</title>" not in body
    assert f'<link rel="canonical" href="https://paperswithcode.co{path}">' in body
    assert '<meta name="robots" content="index,follow">' in body
    assert STATIC_INDEX_PAGES[path][0] in body.replace("&amp;", "&")
    assert response.headers["link"] == (
        f'<https://paperswithcode.co{path}>; rel="canonical"'
    )


def test_static_index_page_with_query_is_noindex(client):
    response = client.get("/tasks?q=vision")
    assert '<meta name="robots" content="noindex,follow">' in response.text
