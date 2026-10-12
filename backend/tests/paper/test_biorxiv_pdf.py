import asyncio
from datetime import date

from backend.utils import biorxiv as biorxiv_mod
from backend.utils.biorxiv import (
    BioRxivMetadata,
    build_biorxiv_pdf_url,
    fetch_europepmc_pdf_url,
    parse_biorxiv_doi,
)


def test_parse_biorxiv_doi_from_content_url():
    parsed = parse_biorxiv_doi(
        "https://www.biorxiv.org/content/10.1101/2025.05.14.654049v1"
    )
    assert parsed == ("biorxiv", "10.1101/2025.05.14.654049")


def test_parse_biorxiv_doi_supports_64898_prefix():
    parsed = parse_biorxiv_doi(
        "https://www.biorxiv.org/content/10.64898/2026.05.22.727119v1"
    )
    assert parsed == ("biorxiv", "10.64898/2026.05.22.727119")


def test_build_biorxiv_pdf_url_uses_posted_date():
    url = build_biorxiv_pdf_url(
        "biorxiv",
        "10.1101/2025.05.14.654049",
        version="1",
        date_str="2025-05-18",
    )
    assert (
        url
        == "https://www.biorxiv.org/content/early/2025/05/18/2025.05.14.654049v1.full.pdf"
    )


def test_fetch_europepmc_pdf_url_skips_biorxiv_host(monkeypatch):
    payload = {
        "resultList": {
            "result": [
                {
                    "fullTextUrlList": {
                        "fullTextUrl": [
                            {
                                "documentStyle": "pdf",
                                "site": "Unpaywall",
                                "url": "https://www.biorxiv.org/content/biorxiv/early/2025/05/18/2025.05.14.654049.full.pdf",
                            },
                            {
                                "documentStyle": "pdf",
                                "site": "Europe_PMC",
                                "url": "https://europepmc.org/api/fulltextRepo?pprId=PPR1022516",
                            },
                        ]
                    }
                }
            ]
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(biorxiv_mod.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    resolved = asyncio.run(fetch_europepmc_pdf_url("10.1101/2025.05.14.654049"))
    assert resolved == "https://europepmc.org/api/fulltextRepo?pprId=PPR1022516"


def test_download_biorxiv_pdf_bytes_uses_europepmc(monkeypatch):
    metadata = BioRxivMetadata(
        title="Example",
        doi="10.1101/2025.05.14.654049",
        date_published=date(2025, 5, 18),
    )

    async def fake_metadata(url, timeout_seconds=12.0):
        return metadata

    async def fake_epmc(doi, timeout_seconds=20.0):
        return "https://europepmc.org/api/fulltextRepo?pprId=PPR1022516"

    async def fake_download(url, timeout_seconds=60.0):
        return b"%PDF-1.5 test"

    monkeypatch.setattr(biorxiv_mod, "fetch_biorxiv_metadata", fake_metadata)
    monkeypatch.setattr(biorxiv_mod, "fetch_europepmc_pdf_url", fake_epmc)
    monkeypatch.setattr(biorxiv_mod, "_download_pdf_url", fake_download)

    pdf_bytes = asyncio.run(
        biorxiv_mod.download_biorxiv_pdf_bytes(
            "https://www.biorxiv.org/content/10.1101/2025.05.14.654049v1"
        )
    )
    assert pdf_bytes == b"%PDF-1.5 test"
