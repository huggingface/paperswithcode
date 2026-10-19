from __future__ import annotations

from datetime import date, datetime, timezone
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import Author, Task
from backend.services.sitemap_service import (
    ArchivePaper,
    SitemapEntity,
    SitemapPaper,
    SitemapService,
    SitemapShard,
)


@pytest.fixture
def client():
    app = create_app()

    def database():
        yield object()

    app.dependency_overrides[get_database_session] = database
    with TestClient(app) as test_client:
        yield test_client


def test_sitemap_index_is_xml_and_apex_hosted(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService,
        "list_shards",
        lambda self: [SitemapShard(2026, 2), SitemapShard(0, 1)],
    )
    monkeypatch.setattr(SitemapService, "list_author_shards", lambda self: [3])
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("loc")]
    assert locations == [
        "https://paperswithcode.co/sitemaps/static.xml",
        "https://paperswithcode.co/sitemaps/tasks.xml",
        "https://paperswithcode.co/sitemaps/methods.xml",
        "https://paperswithcode.co/sitemaps/benchmarks.xml",
        "https://paperswithcode.co/sitemaps/conferences.xml",
        "https://paperswithcode.co/sitemaps/organizations.xml",
        "https://paperswithcode.co/sitemaps/authors-3.xml",
        "https://paperswithcode.co/sitemaps/papers-2026-2.xml",
        "https://paperswithcode.co/sitemaps/papers-0000-1.xml",
    ]


def test_paper_shard_streams_valid_xml_and_lastmod(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService,
        "iter_shard",
        lambda self, shard: iter(
            [
                SitemapPaper(
                    route_identifier="2607.24653",
                    lastmod=datetime(2026, 7, 27, tzinfo=timezone.utc),
                ),
                SitemapPaper(
                    route_identifier="42&x",
                    lastmod=datetime(2026, 7, 28, tzinfo=timezone.utc),
                ),
            ]
        ),
    )
    response = client.get("/sitemaps/papers-2026-2.xml")

    assert response.status_code == 200
    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("loc")]
    assert locations[0] == "https://paperswithcode.co/paper/2607.24653"
    assert locations[1] == "https://paperswithcode.co/paper/42&x"
    assert len([node for node in root.iter() if node.tag.endswith("lastmod")]) == 2


def test_entity_sitemap_contains_only_canonical_apex_urls(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService,
        "iter_entities",
        lambda self, kind: iter(
            [
                SitemapEntity(
                    path="/tasks/image-classification",
                    lastmod=datetime(2026, 7, 28, tzinfo=timezone.utc),
                )
            ]
        ),
    )
    response = client.get("/sitemaps/tasks.xml")
    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("loc")]
    assert response.status_code == 200
    assert locations == ["https://paperswithcode.co/tasks/image-classification"]


def test_sitemap_head_has_no_body(client, monkeypatch):
    monkeypatch.setattr(SitemapService, "list_shards", lambda self: [])
    monkeypatch.setattr(SitemapService, "list_author_shards", lambda self: [])
    response = client.head("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.content == b""


def test_recent_archive_exposes_ordinary_links_and_pagination(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService,
        "archive_page",
        lambda self, **kwargs: (
            [ArchivePaper("2607.24653", "Kimi K3", date(2026, 7, 27))],
            True,
        ),
    )
    response = client.get("/papers/recent")
    assert response.status_code == 200
    assert '<a href="/paper/2607.24653">Kimi K3</a>' in response.text
    assert 'rel="next" href="/papers/recent?page=2"' in response.text
    assert (
        '<link rel="canonical" href="https://paperswithcode.co/papers/recent">'
        in response.text
    )
    assert response.headers["vary"] == "Accept"
    assert response.headers["link"] == (
        '<https://paperswithcode.co/papers/recent>; rel="canonical"'
    )


def test_recent_archive_markdown_and_head_contract(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService,
        "archive_page",
        lambda self, **kwargs: (
            [ArchivePaper("2607.24653", "<h1>Kimi [K3]</h1>", date(2026, 7, 27))],
            True,
        ),
    )
    headers = {"Accept": "text/markdown"}
    response = client.get("/papers/recent", headers=headers)
    head = client.head("/papers/recent", headers=headers)
    assert response.status_code == head.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["vary"] == head.headers["vary"] == "Accept"
    assert response.headers["link"] == (
        '<https://paperswithcode.co/papers/recent>; rel="canonical"'
    )
    assert response.headers["cache-control"].startswith("public, max-age=300")
    assert response.text.startswith("---\n")
    assert "<h1>" not in response.text
    assert "Kimi \\[K3\\]" in response.text
    assert head.content == b""


def test_empty_month_is_real_archive_and_invalid_period_is_404(client, monkeypatch):
    monkeypatch.setattr(
        SitemapService, "archive_page", lambda self, **kwargs: ([], False)
    )
    empty = client.get("/papers/archive/2026/07")
    invalid = client.get("/papers/archive/2026/13")
    assert empty.status_code == 200
    assert "No eligible papers were published in this period." in empty.text
    assert invalid.status_code == 404


def _selected_columns(query_mock):
    return [column.key for column in query_mock.call_args.args]


def test_paper_shard_selects_only_sitemap_columns():
    db = MagicMock()

    assert list(SitemapService(db).iter_shard(SitemapShard(2026, 1))) == []

    assert _selected_columns(db.query) == [
        "id",
        "source",
        "arxiv_id",
        "date_published",
        "created_at",
    ]


def test_entity_and_author_shards_select_only_sitemap_columns():
    db = MagicMock()
    assert list(SitemapService(db).iter_entities("tasks")) == []
    assert [column.key for column in db.query.call_args.args] == ["slug", "updated_at"]
    assert all(column.class_ is Task for column in db.query.call_args.args)

    db = MagicMock()
    assert list(SitemapService(db).iter_author_shard(2)) == []
    assert [column.key for column in db.query.call_args.args] == ["id", "updated_at"]
    assert all(column.class_ is Author for column in db.query.call_args.args)


def test_archive_page_selects_only_archive_columns():
    db = MagicMock()

    assert SitemapService(db).archive_page(page=1, year=2026) == ([], False)

    with_entities_calls = [
        call for call in db.mock_calls if call[0].endswith(".with_entities")
    ]
    assert len(with_entities_calls) == 1
    assert [column.key for column in with_entities_calls[0].args] == [
        "id",
        "source",
        "arxiv_id",
        "title",
        "date_published",
    ]


def test_paper_shard_is_rendered_before_the_response_starts(client, monkeypatch):
    lastmod = datetime(2026, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        SitemapService,
        "iter_shard",
        lambda self, shard: iter(
            [
                SitemapPaper(route_identifier=f"2608.{index:05d}", lastmod=lastmod)
                for index in range(3)
            ]
        ),
    )

    response = client.get("/sitemaps/papers-2026-0.xml")

    assert response.status_code == 200
    # A materialized body carries its length; a streamed one would be chunked
    # and hold the database connection open for the whole download.
    assert response.headers["content-length"] == str(len(response.content))
    assert "transfer-encoding" not in response.headers
    assert response.content.count(b"<url>") == 3


def test_static_sitemap_lists_curated_landing_pages(client):
    response = client.get("/sitemaps/static.xml")

    assert response.status_code == 200
    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("loc")]
    assert "https://paperswithcode.co/astra-for-robotics" in locations


def test_static_sitemap_lists_browse_index_pages(client):
    response = client.get("/sitemaps/static.xml")

    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("loc")]
    for path in ("/ai-deadlines", "/trends", "/tasks", "/methods", "/conferences"):
        assert f"https://paperswithcode.co{path}" in locations
