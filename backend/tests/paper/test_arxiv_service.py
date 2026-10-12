import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx

from backend.services.arxiv_service import ArxivPdfUnavailableError, ArxivService
from backend.routers.papers import _arxiv_metadata_error


def test_build_direct_pdf_url_uses_known_version_without_metadata_lookup():
    service = ArxivService.__new__(ArxivService)

    assert (
        service._build_direct_pdf_url("arXiv:1806.00187", "v3")
        == "https://arxiv.org/pdf/1806.00187v3"
    )


def test_build_direct_pdf_url_replaces_existing_version_suffix():
    service = ArxivService.__new__(ArxivService)

    assert (
        service._build_direct_pdf_url("2605.06535v1", "v2")
        == "https://arxiv.org/pdf/2605.06535v2"
    )


def test_429_retry_delay_uses_retry_after_seconds():
    service = ArxivService.__new__(ArxivService)
    response = httpx.Response(429, headers={"retry-after": "42"})

    assert service._get_429_retry_delay(response, attempt=0) == 42


def test_429_retry_delay_uses_http_date_retry_after():
    service = ArxivService.__new__(ArxivService)
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=120)
    response = httpx.Response(
        429,
        headers={"retry-after": format_datetime(retry_at, usegmt=True)},
    )

    assert 0 < service._get_429_retry_delay(response, attempt=0) <= 120


def test_429_retry_delay_falls_back_to_exponential_cooldown():
    service = ArxivService.__new__(ArxivService)
    response = httpx.Response(429)

    assert service._get_429_retry_delay(response, attempt=1) == 120


def test_empty_arxiv_feed_is_not_found():
    service = ArxivService.__new__(ArxivService)

    metadata = service._parse_arxiv_response(
        """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"></feed>
        """,
        "2605.18736",
    )

    assert metadata.success is False
    assert metadata.error_type == "not_found"


def test_arxiv_metadata_rate_limit_sets_shared_cooldown(monkeypatch):
    class RateLimitedClient:
        export_request_count = 0

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params=None, headers=None):
            if "export.arxiv.org" in str(url):
                self.__class__.export_request_count += 1
                return httpx.Response(
                    429,
                    headers={"retry-after": "120"},
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                503,
                request=httpx.Request("GET", url),
            )

    async def run_test():
        ArxivService._reset_export_backoff_for_tests()
        monkeypatch.setattr(httpx, "AsyncClient", RateLimitedClient)

        service = ArxivService()
        first = await service.get_paper_metadata("2605.18736")
        second = await service.get_paper_metadata("2605.18736")

        assert first.success is False
        assert first.error_type == "rate_limited"
        assert second.success is False
        assert second.error_type == "rate_limited"
        assert RateLimitedClient.export_request_count == 1

    try:
        asyncio.run(run_test())
    finally:
        ArxivService._reset_export_backoff_for_tests()


def test_abs_page_fallback_extracts_required_metadata():
    service = ArxivService.__new__(ArxivService)

    metadata = service._extract_abs_page_metadata(
        """
        <html>
          <head>
            <meta name="citation_title" content="A Useful Paper">
            <meta name="citation_author" content="Lovelace, Ada">
            <meta name="citation_author" content="Hopper, Grace Brewster Murray">
            <meta name="citation_author" content="King, Martin Luther, Jr.">
            <meta name="citation_author" content="Kimi Team">
            <meta name="citation_date" content="2026/05/20">
            <meta name="citation_online_date" content="2026/05/21">
            <meta name="citation_pdf_url" content="https://arxiv.org/pdf/2605.18736">
            <meta name="citation_arxiv_id" content="2605.18736">
            <meta name="citation_abstract" content="A concise abstract.">
          </head>
          <body>
            <div class="dateline">[Submitted on 20 May 2026 ( v1 ), last revised 21 May 2026 (this version, v2)]</div>
            <table><tr><td class="tablecell subjects">Machine Learning (cs.LG); Computation and Language (cs.CL)</td></tr></table>
          </body>
        </html>
        """,
        "2605.18736",
    )

    assert metadata is not None
    assert metadata.success is True
    assert metadata.fallback_used is True
    assert metadata.version == "v2"
    assert metadata.authors == [
        "Ada Lovelace",
        "Grace Brewster Murray Hopper",
        "Martin Luther King Jr.",
        "Kimi Team",
    ]
    assert metadata.categories == ["cs.LG", "cs.CL"]


def test_router_maps_arxiv_rate_limit_to_429():
    exc = _arxiv_metadata_error("2605.18736", "rate_limited")

    assert exc.status_code == 429
    assert "rate-limiting" in exc.detail


def test_download_pdf_raises_confirmed_unavailable_on_404(monkeypatch):
    class MissingPdfClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(404, request=httpx.Request("GET", url))

    async def run_test():
        monkeypatch.setattr(httpx, "AsyncClient", MissingPdfClient)
        service = ArxivService()
        service._rate_limit = lambda: asyncio.sleep(0)

        try:
            await service.download_pdf("2402.17012", "v4")
        except ArxivPdfUnavailableError:
            return
        raise AssertionError("expected ArxivPdfUnavailableError")

    asyncio.run(run_test())
