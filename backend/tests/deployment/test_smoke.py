"""Release smoke checks for bundles, SPA, SEO, and chat boundaries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import deploy.smoke_test as smoke_test
from deploy.release import (
    profile_features,
)
from deploy.smoke_test import validate_local_bundle
from backend.tests.deployment.harness import (
    make_bundle,
)


def test_smoke_bundle_parser_catches_missing_asset(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "app-abc123.js").unlink()
    assert any(
        "missing asset" in item
        for item in validate_local_bundle(release, profile_features("production"))
    )


def test_staging_smoke_rejects_pdf_worker_with_unsupported_mjs_mime(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    worker = release / "frontend-dist" / "assets" / "pdf.worker.min-abc123.js"
    worker.rename(worker.with_suffix(".mjs"))
    assert any(
        "PDF worker must use a .js extension" in item
        for item in validate_local_bundle(release, profile_features("staging"))
    )


def test_smoke_script_runs_from_outside_repository(tmp_path: Path):
    script = Path(__file__).parents[3] / "deploy" / "smoke_test.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_staging_smoke_accepts_versioned_feature_manifest(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    assert validate_local_bundle(release, True) == []


def _seo_sitemap_index() -> bytes:
    names = (
        "papers-2026-1.xml",
        "tasks.xml",
        "methods.xml",
        "benchmarks.xml",
        "conferences.xml",
        "organizations.xml",
        "authors-0.xml",
    )
    return (
        "<sitemapindex>"
        + "".join(
            f"<sitemap><loc>https://paperswithcode.co/sitemaps/{name}</loc></sitemap>"
            for name in names
        )
        + "</sitemapindex>"
    ).encode()


def _entity_sitemap_response(url: str):
    paths = {
        "tasks.xml": "/tasks/example",
        "methods.xml": "/methods/example",
        "benchmarks.xml": "/benchmark/example",
        "conferences.xml": "/conferences/example",
        "organizations.xml": "/example-org",
        "authors-0.xml": "/authors/1",
    }
    path = paths.get(url.rsplit("/", 1)[-1])
    if path is None:
        return None
    location = f"https://paperswithcode.co{path}"
    return (
        200,
        {"Content-Type": "application/xml"},
        f"<urlset><url><loc>{location}</loc></url></urlset>".encode(),
    )


def _entity_page_response(url: str):
    paths = (
        "/tasks/example",
        "/methods/example",
        "/benchmark/example",
        "/conferences/example",
        "/example-org",
        "/authors/1",
    )
    path = next((candidate for candidate in paths if url.endswith(candidate)), None)
    if path is None:
        return None
    canonical = f"https://paperswithcode.co{path}"
    return (
        200,
        {},
        (
            f'<link rel="canonical" href="{canonical}">'
            '<main data-pwc-initial-document="discovery"><h1>Entity</h1>'
            '<a href="/paper/1">Paper</a></main>'
        ).encode(),
    )


def _markdown_page_response(url: str, headers: dict[str, str] | None):
    if not headers or headers.get("Accept") != "text/markdown":
        return None
    paths = (
        "/",
        "/paper/2607.24653",
        "/tasks/image-classification",
        "/papers/recent",
    )
    path = next((candidate for candidate in paths if url.endswith(candidate)), None)
    if path is None:
        return None
    canonical = f"https://paperswithcode.co{path}"
    return (
        200,
        {
            "Content-Type": "text/markdown; charset=utf-8",
            "Vary": "Accept",
            "Link": f'<{canonical}>; rel="canonical"',
        },
        (
            "---\n"
            f'title: "Example"\ncanonical: "{canonical}"\n'
            'description: "Example"\ntype: "page"\n---\n\n# Example\n'
        ).encode(),
    )


def test_staging_candidate_smoke_leaves_spa_to_nginx(monkeypatch):
    requested: list[str] = []

    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        requested.append(url)
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return 200, {"Content-Type": "text/plain"}, b"User-agent: *\nDisallow: /\n"
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/health"):
            return 200, {}, b'{"release_id":"release-staging"}'
        if url.endswith("/api/v1/papers/1"):
            return 404, {}, b'{"detail":"Paper not found"}'
        if url.endswith("/api/v1/chat/sessions"):
            return 401, {}, b""
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"Link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"Location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"Content-Type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"Content-Type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(f"unexpected candidate request: {url}")

    monkeypatch.setattr(smoke_test, "request", request)

    assert (
        smoke_test.run_http_smoke(
            "staging",
            "http://127.0.0.1:8100",
            expected_release="release-staging",
            candidate=True,
        )
        == []
    )
    assert all(not url.endswith("/chat") for url in requested)


def test_staging_candidate_smoke_rejects_numeric_paper_server_error(monkeypatch):
    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return 200, {"Content-Type": "text/plain"}, b"User-agent: *\nDisallow: /\n"
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/health"):
            return 200, {}, b'{"release_id":"release-staging"}'
        if url.endswith("/api/v1/papers/1"):
            return 500, {}, b"Internal Server Error"
        if url.endswith("/api/v1/chat/sessions"):
            return 401, {}, b""
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"Link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"Location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"Content-Type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"Content-Type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(f"unexpected candidate request: {url}")

    monkeypatch.setattr(smoke_test, "request", request)

    assert smoke_test.run_http_smoke(
        "staging",
        "http://127.0.0.1:8100",
        expected_release="release-staging",
        candidate=True,
    ) == ["numeric paper API returned 500"]


@pytest.mark.parametrize(
    ("chat_enabled", "status", "expected"),
    [
        (False, 404, []),
        (True, 401, []),
        (False, 401, ["production chat API is not absent: 401"]),
        (True, 404, ["production chat API is not auth-protected: 404"]),
    ],
)
def test_production_smoke_uses_release_chat_boundary(
    monkeypatch, chat_enabled, status, expected
):
    monkeypatch.setattr(smoke_test, "run_seo_http_smoke", lambda *_args: [])

    def request(url, **_kwargs):
        if url.endswith("/health"):
            return 200, {}, b'{"release_id":"release-production"}'
        if "/api/v1/papers/" in url:
            return 200, {}, b"{}"
        if url.endswith("/api/v1/chat/sessions"):
            return status, {}, b""
        raise AssertionError(url)

    monkeypatch.setattr(smoke_test, "request", request)

    assert (
        smoke_test.run_http_smoke(
            "production",
            "http://127.0.0.1:8100",
            expected_release="release-production",
            candidate=True,
            chat_enabled=chat_enabled,
        )
        == expected
    )


def test_seo_smoke_treats_http_headers_case_insensitively(monkeypatch):
    requested: list[str] = []

    def request(
        url: str,
        *,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ):
        requested.append(url)
        if response := _markdown_page_response(url, headers):
            return response
        if response := _entity_sitemap_response(url):
            return response
        if response := _entity_page_response(url):
            return response
        if url.endswith("/robots.txt"):
            return (
                200,
                {"content-type": "text/plain"},
                b"User-agent: *\nAllow: /\nSitemap: https://paperswithcode.co/sitemap.xml\n",
            )
        if url.rstrip("/").endswith(":8100"):
            links = b"".join(
                f'<a href="/paper/{i}">Paper</a>'.encode() for i in range(20)
            ) + b"".join(f'<a href="/tasks/{i}">Task</a>'.encode() for i in range(5))
            return (
                200,
                {},
                b'<main data-pwc-initial-document="discovery">' + links + b"</main>",
            )
        if url.endswith("/paper/2607.24653"):
            return (
                200,
                {"link": "<https://paperswithcode.co/paper/2607.24653>; rel=canonical"},
                b'<main data-pwc-initial-document="paper"><h1>Kimi K3: Open Frontier Intelligence</h1><h2 id="abstract-heading"></h2><meta name="citation_arxiv_id" content="2607.24653"><script type="application/ld+json"></script></main>',
            )
        if url.endswith("/paper/9999.99999"):
            return 404, {}, b""
        if url.endswith("/papers/2607.24653"):
            return 301, {"location": "/paper/2607.24653"}, b""
        if url.endswith("/sitemap.xml"):
            return (
                200,
                {"content-type": "application/xml"},
                _seo_sitemap_index(),
            )
        if url.endswith("/sitemaps/papers-2026-1.xml"):
            return 200, {"content-type": "application/xml"}, b"<urlset/>"
        if url.endswith("/papers/recent"):
            return 200, {}, b'<a href="/paper/2607.24653">Kimi K3</a>'
        raise AssertionError(url)

    monkeypatch.setattr(smoke_test, "request", request)
    assert smoke_test.run_seo_http_smoke("http://127.0.0.1:8100") == []
    assert "http://127.0.0.1:8100/sitemaps/papers-2026-1.xml" in requested
    assert "https://example.test/sitemaps/papers-2026-1.xml" not in requested
