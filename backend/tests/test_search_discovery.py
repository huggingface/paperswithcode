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
from backend.services.discovery_page_service import (
    DiscoveryLink,
    DiscoveryPage,
    DiscoveryPageService,
    DiscoveryPaperLink,
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


@pytest.mark.parametrize("linked", [True, False])
def test_empty_task_benchmark_requires_association(client, linked):
    """A configured leaderboard can render before its first score is imported."""

    def query(*, one=None, rows=()):
        result = MagicMock()
        for method in ("filter", "join", "order_by", "limit"):
            getattr(result, method).return_value = result
        result.one_or_none.return_value = one
        result.all.return_value = rows
        return result

    db = MagicMock()
    db.query.side_effect = [
        query(one=SimpleNamespace(id=2590, name="MMAE", description="Audio edits")),
        # The sidebar's bounded task list need not include the selected task.
        query(rows=[("other-task", "Other task")]),
        query(),
        query(one=SimpleNamespace(id=775)),
        query(one=object() if linked else None),
    ]
    client.app.dependency_overrides[get_database_session] = lambda: db

    response = client.get("/benchmark/mmae?task=audio-editing")

    assert response.status_code == (200 if linked else 404)
    if linked:
        assert "MMAE" in response.text
        assert 'id="root"' in response.text
        assert "Page not found" not in response.text


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
        "/tasks",
        "/methods",
        "/conferences",
        "/organizations",
        "/chat/abc",
        "/pdf/2606.23050",
        "/privacy",
        "/authorize-paper-edit/00000000-0000-0000-0000-000000000001",
    ],
)
def test_known_client_only_routes_keep_the_spa_shell(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


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


def test_merged_organization_slug_redirects_to_canonical_page(client):
    response = client.get("/orgs/googledeepmind?q=vision", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/orgs/google?q=vision"


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
