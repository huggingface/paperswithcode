"""
Tests for the per-paper social meta-tag injection used by `/paper/{id}` and
the legacy `/papers/{id}` route.

These tests focus on:
  - Resolving the social image URL from an existing paper thumbnail.
  - Using Hugging Face's paper preview when an arXiv thumbnail is not on disk.
  - Falling back to the static default image for other papers.
  - Injecting properly escaped meta tags into the SPA shell HTML.
  - The end-to-end response surface of the FastAPI routes, including a
    smoke check that the default OG image endpoint returns a PNG payload.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.papers import Paper
from backend.routers import paper_pages
from backend.services import default_og_image, social_meta_service, spa_shell_service
from backend.services.paper_service import PaperService
from backend.services.social_meta_service import (
    PRODUCTION_ORIGIN,
    build_paper_meta,
    build_request_origin,
    inject_paper_meta,
    resolve_social_image_url,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


class _FakeThumbnailService:
    """ThumbnailService stand-in that materialises real JPEGs on disk.

    Real JPEG bytes are written so ``resolve_social_image_url`` can read back
    actual image dimensions, mirroring the production code path.
    """

    def __init__(
        self,
        present: Optional[set[str]] = None,
        custom: Optional[set[str]] = None,
        width: int = 400,
        height: int = 550,
    ):
        self._dir = Path(tempfile.mkdtemp(prefix="pwc-thumb-test-"))
        self._present = present or set()
        self._custom = custom or set()
        for name in self._present | self._custom:
            PILImage.new("RGB", (width, height), (210, 210, 210)).save(
                self._dir / name, "JPEG"
            )

    def get_local_thumbnail_path(self, filename: str) -> Optional[Path]:
        if filename in self._present:
            return self._dir / filename
        return None

    def get_existing_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        if filename in self._custom:
            return self._dir / filename
        return None

    def get_local_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        return self.get_existing_custom_thumbnail_path(filename)


def _make_paper(**overrides) -> Paper:
    base = dict(
        id="1234",
        arxiv_id="2504.12516",
        source="arxiv",
        url_abs="https://arxiv.org/abs/2504.12516",
        url_pdf="https://arxiv.org/pdf/2504.12516.pdf",
        thumbnail_url="/api/thumbnails/2504_12516_v1.jpg?fit=fit2",
        title="A <Great> Paper & Friends",
        abstract="We propose a clever method.  " * 10,
        authors=["Alice Author", "Bob Builder", "Carla Coder"],
        version="v1",
        is_latest_version=True,
        citation_count=42,
    )
    base.update(overrides)
    return Paper(**base)


@pytest.fixture(autouse=True)
def _reset_default_og_cache():
    default_og_image._cached_png = None
    yield
    default_og_image._cached_png = None


@pytest.fixture(autouse=True)
def _reset_index_cache():
    spa_shell_service.reset_cache()
    yield
    spa_shell_service.reset_cache()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_load_index_html_prefers_active_release(tmp_path, monkeypatch):
    release_index = tmp_path / "release-index.html"
    dist_index = tmp_path / "dist-index.html"
    source_index = tmp_path / "source-index.html"
    release_index.write_text("active release", encoding="utf-8")
    dist_index.write_text("stale checkout build", encoding="utf-8")
    source_index.write_text("vite source", encoding="utf-8")

    monkeypatch.setattr(spa_shell_service, "_RELEASE_INDEX_PATH", release_index)
    monkeypatch.setattr(spa_shell_service, "_DIST_INDEX_PATH", dist_index)
    monkeypatch.setattr(spa_shell_service, "_SRC_INDEX_PATH", source_index)

    assert spa_shell_service.load_index_html() == "active release"


def test_build_request_origin_uses_forwarded_headers():
    assert (
        build_request_origin("https", "paperswithcode.co")
        == "https://paperswithcode.co"
    )


def test_build_request_origin_falls_back_to_production_when_host_missing():
    assert build_request_origin(None, None) == PRODUCTION_ORIGIN


def test_build_request_origin_normalises_scheme():
    assert build_request_origin("javascript", "example.test") == "https://example.test"


def test_resolve_social_image_uses_existing_arxiv_thumbnail():
    paper = _make_paper()
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url == (
        "https://paperswithcode.co/api/thumbnails/2504_12516_v1.jpg?fit=fit2"
    )
    assert result.mime_type == "image/jpeg"
    assert (result.width, result.height) == (400, 550)


@pytest.mark.parametrize(
    "thumbnail_url",
    [
        None,
        "/api/thumbnails/2504_12516_v1.jpg?fit=fit2",
    ],
)
def test_resolve_social_image_uses_hf_preview_when_arxiv_thumbnail_missing(
    thumbnail_url,
):
    paper = _make_paper(thumbnail_url=thumbnail_url)
    fake = _FakeThumbnailService(present=set())

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url == (
        "https://cdn-thumbnails.huggingface.co/social-thumbnails/"
        "papers/2504.12516/gradient.png"
    )
    assert result.mime_type == "image/png"
    assert (result.width, result.height) == (1200, 630)


def test_resolve_social_image_falls_back_for_external_paper_without_thumbnail():
    paper = _make_paper(
        source="external",
        arxiv_id=None,
        thumbnail_url=None,
    )
    fake = _FakeThumbnailService(present=set())

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is True
    assert result.absolute_url == "https://paperswithcode.co/api/og/default.png"
    assert result.mime_type == "image/png"
    assert (result.width, result.height) == (1200, 630)


def test_resolve_social_image_uses_existing_custom_thumbnail():
    paper = _make_paper(
        source="external",
        arxiv_id=None,
        thumbnail_url="/api/thumbnails/custom/external_1234.jpg?fit=fit2",
    )
    fake = _FakeThumbnailService(custom={"external_1234.jpg"})

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url.endswith(
        "/api/thumbnails/custom/external_1234.jpg?fit=fit2"
    )


def test_resolve_social_image_accepts_absolute_url_without_disk_check():
    paper = _make_paper(thumbnail_url="https://example.com/preview.jpg")
    fake = _FakeThumbnailService(present=set())

    result = resolve_social_image_url(
        paper, "https://paperswithcode.co", thumbnail_service=fake
    )

    assert result.is_fallback is False
    assert result.absolute_url == "https://example.com/preview.jpg"


def test_build_paper_meta_decodes_latex_accents_in_title():
    paper = _make_paper(
        title=r"D\'ej\`a View: Looping Transformers for Multi-View 3D Reconstruction"
    )
    fake = _FakeThumbnailService(present=set())

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )

    assert meta.title.startswith("Déjà View:")


def test_inject_paper_meta_escapes_user_supplied_strings():
    paper = _make_paper()
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )
    html = inject_paper_meta(
        "<!doctype html><html><head><title>Papers with Code</title>"
        '<meta name="description" content="default" />'
        '<meta property="og:title" content="default" />'
        '<meta property="og:description" content="default" />'
        '<meta property="og:type" content="website" />'
        '<meta name="twitter:card" content="summary" />'
        "</head><body></body></html>",
        meta,
    )

    # The user-supplied title was `A <Great> Paper & Friends` and must be
    # HTML-escaped in every place we render it.
    assert "A &lt;Great&gt; Paper &amp; Friends | Papers with Code" in html
    # Old, generic tags must be replaced (no duplicate `Papers with Code`
    # title or generic `og:type=website`).
    assert html.count("<title>") == 1
    assert 'og:type" content="website"' not in html
    assert 'og:type" content="article"' in html
    assert 'twitter:card" content="summary"' not in html
    assert 'twitter:card" content="summary_large_image"' in html
    # Canonical URL points at the singular `/paper/{id}` shape.
    assert (
        '<link rel="canonical" href="https://paperswithcode.co/paper/2504.12516" />'
        in html
    )
    # Real thumbnail URL is absolute.
    assert (
        'og:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in html
    assert (
        'twitter:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in html
    # Exactly one image tag of each kind so crawlers never see conflicts.
    assert html.count('property="og:image"') == 1
    assert html.count('name="twitter:image"') == 1
    # Crawler-friendly image metadata for the real JPEG thumbnail.
    assert 'og:image:type" content="image/jpeg"' in html
    assert 'og:image:width" content="400"' in html
    assert 'og:image:height" content="550"' in html
    assert (
        'og:image:secure_url" content="https://paperswithcode.co/api/thumbnails/'
        in html
    )
    assert (
        'og:image:alt" content="First page preview of '
        "A &lt;Great&gt; Paper &amp; Friends" in html
    )
    assert (
        'twitter:image:alt" content="First page preview of '
        "A &lt;Great&gt; Paper &amp; Friends" in html
    )


def test_inject_paper_meta_uses_hf_preview_when_arxiv_thumbnail_disk_misses():
    paper = _make_paper()
    fake = _FakeThumbnailService(present=set())

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )
    html = inject_paper_meta("<html><head></head><body></body></html>", meta)

    assert (
        'og:image" content="https://cdn-thumbnails.huggingface.co/'
        'social-thumbnails/papers/2504.12516/gradient.png"'
    ) in html
    # The upstream image carries explicit dimensions and type so
    # summary_large_image cards render cleanly even before the platform has
    # scraped the asset.
    assert 'og:image:type" content="image/png"' in html
    assert 'og:image:width" content="1200"' in html
    assert 'og:image:height" content="630"' in html
    assert (
        'og:image:alt" content="First page preview of '
        'A &lt;Great&gt; Paper &amp; Friends"' in html
    )
    assert (
        'twitter:image:alt" content="First page preview of '
        'A &lt;Great&gt; Paper &amp; Friends"' in html
    )


_STATIC_INDEX_HEAD = (
    "<!doctype html><html><head>"
    '<meta charset="UTF-8" />'
    "<title>Papers with Code</title>"
    '<meta name="description" content="Trending AI research papers." />'
    '<meta property="og:title" content="Papers with Code" />'
    '<meta property="og:description" content="Trending AI research papers." />'
    '<meta property="og:type" content="website" />'
    '<meta property="og:url" content="https://paperswithcode.co/" />'
    '<meta property="og:site_name" content="Papers with Code" />'
    '<meta property="og:image" content="https://paperswithcode.co/og-image.png?v=2" />'
    '<meta property="og:image:width" content="1200" />'
    '<meta property="og:image:height" content="630" />'
    '<meta property="og:image:alt" content="Papers with Code" />'
    '<meta name="twitter:card" content="summary_large_image" />'
    '<meta name="twitter:title" content="Papers with Code" />'
    '<meta name="twitter:description" content="Trending AI research papers." />'
    '<meta name="twitter:image" content="https://paperswithcode.co/og-image.png?v=2" />'
    "</head><body></body></html>"
)


def test_inject_paper_meta_strips_all_generic_static_tags():
    paper = _make_paper()
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )
    html = inject_paper_meta(_STATIC_INDEX_HEAD, meta)

    # The generic site-wide preview image must be gone entirely so X cannot
    # cache it ahead of the per-paper thumbnail.
    assert "og-image.png" not in html
    # Generic site values must be replaced, not duplicated.
    assert 'og:url" content="https://paperswithcode.co/"' not in html
    assert 'og:type" content="website"' not in html
    # Exactly one of each social tag survives.
    for needle in (
        'property="og:image"',
        'name="twitter:image"',
        'property="og:url"',
        'property="og:title"',
        'name="twitter:title"',
        'property="og:site_name"',
        'name="twitter:card"',
        'property="og:image:width"',
        'property="og:image:height"',
        'property="og:image:alt"',
    ):
        assert html.count(needle) == 1, needle
    # And the single survivor points at the paper thumbnail.
    assert (
        'og:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in html


def test_inject_paper_meta_uses_authors_when_abstract_empty():
    paper = _make_paper(abstract="")
    fake = _FakeThumbnailService(present={"2504_12516_v1.jpg"})

    meta = build_paper_meta(
        paper,
        route_identifier=paper.arxiv_id or paper.id,
        origin="https://paperswithcode.co",
        thumbnail_service=fake,
    )

    assert meta.description.startswith("By Alice Author")


# ---------------------------------------------------------------------------
# Default OG image endpoint
# ---------------------------------------------------------------------------


def test_default_og_image_is_a_png():
    payload = default_og_image.get_default_og_image_bytes()
    # PNG magic header.
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    # Cached on second call.
    assert default_og_image.get_default_og_image_bytes() is payload


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app = create_app()

    def override_get_database_session():
        yield object()

    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _stub_paper_lookup(monkeypatch, paper: Paper):
    def fake(self, identifier, include_resources=False):
        return paper

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", fake)


def _stub_paper_lookup_missing(monkeypatch):
    def fake(self, identifier, include_resources=False):
        raise PaperNotFoundError(identifier)

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", fake)


def _stub_thumbnail_present(monkeypatch, filenames: set[str]):
    fake = _FakeThumbnailService(present=filenames)
    monkeypatch.setattr(
        social_meta_service,
        "ThumbnailService",
        lambda: fake,
    )


def test_paper_route_returns_html_with_paper_specific_meta(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, {"2504_12516_v1.jpg"})

    response = client.get(
        "/paper/2504.12516",
        headers={"X-Forwarded-Proto": "https", "Host": "paperswithcode.co"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "A &lt;Great&gt; Paper &amp; Friends | Papers with Code" in body
    assert 'og:url" content="https://paperswithcode.co/paper/2504.12516"' in body
    assert (
        'twitter:image" content="https://paperswithcode.co/api/thumbnails/'
        '2504_12516_v1.jpg?fit=fit2"'
    ) in body
    assert response.headers["vary"] == "Accept"


def test_new_arxiv_paper_route_uses_hf_preview_before_local_preload(
    client, monkeypatch
):
    paper = _make_paper(thumbnail_url=None)
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, set())

    response = client.get("/paper/2504.12516")

    assert response.status_code == 200
    assert (
        'twitter:image" content="https://cdn-thumbnails.huggingface.co/'
        'social-thumbnails/papers/2504.12516/gradient.png"'
    ) in response.text


def test_paper_markdown_is_available_without_frontend_bundle(client, monkeypatch):
    paper = _make_paper(
        title='A # Paper <script>alert("x")</script>',
        abstract="<h2>Injected heading</h2> Safe [abstract]",
    )
    _stub_paper_lookup(monkeypatch, paper)
    monkeypatch.setattr(paper_pages, "load_index_html", lambda: None)
    response = client.get("/paper/2504.12516", headers={"Accept": "text/markdown"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["vary"] == "Accept"
    assert response.headers["link"] == (
        '<https://paperswithcode.co/paper/2504.12516>; rel="canonical"'
    )
    assert response.text.startswith("---\n")
    assert "<script>" not in response.text
    assert "\n## Injected heading" not in response.text


def test_paper_route_returns_404_when_paper_missing(client, monkeypatch):
    _stub_paper_lookup_missing(monkeypatch)

    response = client.get("/paper/9999.99999")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert 'name="robots" content="noindex"' in response.text
    assert "<title>Paper not indexed yet | Papers with Code</title>" in response.text
    assert '<div id="root"></div>' in response.text
    assert 'type="module"' in response.text
    markdown = client.get("/paper/9999.99999", headers={"Accept": "text/markdown"})
    assert markdown.status_code == 404
    assert markdown.headers["content-type"].startswith("text/html")
    assert '<div id="root"></div>' in markdown.text


def test_paper_route_returns_standalone_404_for_invalid_identifier(client, monkeypatch):
    _stub_paper_lookup_missing(monkeypatch)

    response = client.get("/paper/not-an-arxiv-id")

    assert response.status_code == 404
    assert 'name="robots" content="noindex"' in response.text
    assert "<h1>Paper not found</h1>" in response.text
    assert '<div id="root">' not in response.text


def test_legacy_papers_route_redirects_to_canonical_url(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, set())  # force fallback image

    response = client.get(
        "/papers/2504.12516",
        headers={"X-Forwarded-Proto": "https", "Host": "paperswithcode.co"},
        follow_redirects=False,
    )

    assert response.status_code == 301
    assert response.headers["location"] == "/paper/2504.12516"


def test_versioned_alias_redirects_to_canonical_url(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)

    response = client.get("/paper/2504.12516v2", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/paper/2504.12516"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/abs/2504.12516", "/paper/2504.12516"),
        ("/abs/2504.12516v3", "/paper/2504.12516"),
        ("/pdf/2504.12516.pdf", "/pdf/2504.12516"),
        ("/pdf/2504.12516v2.pdf", "/pdf/2504.12516"),
    ],
)
def test_arxiv_host_swap_redirects_to_paper_and_reader(client, path, location):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == location


def test_database_failure_returns_index_safe_503(client, monkeypatch):
    def fake(self, identifier, include_resources=False):
        raise DatabaseError("database unavailable")

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", fake)
    response = client.get("/paper/2504.12516")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "60"
    assert 'name="robots" content="noindex"' in response.text


def test_head_matches_get_headers_without_body(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    _stub_thumbnail_present(monkeypatch, set())

    get_response = client.get("/paper/2504.12516")
    head_response = client.head("/paper/2504.12516")

    assert head_response.status_code == get_response.status_code == 200
    assert head_response.headers["content-type"] == get_response.headers["content-type"]
    assert (
        head_response.headers["cache-control"] == get_response.headers["cache-control"]
    )
    assert head_response.headers["link"] == get_response.headers["link"]
    assert head_response.content == b""


def test_markdown_head_matches_get_headers_without_body(client, monkeypatch):
    paper = _make_paper()
    _stub_paper_lookup(monkeypatch, paper)
    headers = {"Accept": "text/markdown"}
    get_response = client.get("/paper/2504.12516", headers=headers)
    head_response = client.head("/paper/2504.12516", headers=headers)
    assert head_response.status_code == get_response.status_code == 200
    assert head_response.headers["content-type"] == get_response.headers["content-type"]
    assert head_response.headers["vary"] == get_response.headers["vary"] == "Accept"
    assert head_response.headers["link"] == get_response.headers["link"]
    assert head_response.content == b""


def test_default_og_image_endpoint_returns_png(client):
    response = client.get("/api/og/default.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
