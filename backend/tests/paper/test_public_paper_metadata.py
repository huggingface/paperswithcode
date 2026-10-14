"""GET /papers/{identifier}/public-metadata answers for papers outside the catalog."""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.services import public_paper_metadata_service as service
from backend.services.paper_service import PaperService
from backend.utils.client_ip import get_proxied_client_ip
from backend.utils.exceptions import PaperNotFoundError

ABS_PAGE = b"""<html><head>
<meta name="citation_title" content="Fresh &amp; Unindexed Paper" />
<meta name="citation_author" content="Doe, Jane" />
<meta name="citation_author" content="Roe, Rick, Jr" />
<meta name="citation_date" content="2026/10/13" />
<meta name="citation_abstract" content="We release code at https://github.com/acme/fresh." />
</head></html>"""

HF_PAPER = {
    "id": "2610.00001",
    "title": "Hugging  Face Paper",
    "authors": [{"name": "Ada Lovelace"}, {"user": "x"}],
    "summary": "An abstract.",
    "publishedAt": "2026-10-01T00:00:00.000Z",
    "githubRepo": "https://github.com/acme/hf",
    "projectPage": "https://acme.dev/hf",
}

CROSSREF_WORK = {
    "message": {
        "title": ["A Journal Paper"],
        "author": [{"given": "Grace", "family": "Hopper"}],
        "issued": {"date-parts": [[2024, 5]]},
        "abstract": "<jats:p>Abstract Some text.</jats:p>",
        "URL": "https://doi.org/10.1000/xyz123",
    }
}


class Upstream:
    """Mock upstream responses keyed by URL prefix; records each request."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        for prefix, response in self.routes.items():
            if url.startswith(prefix):
                return response(request) if callable(response) else response
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def _reset_state():
    service.reset_public_metadata_state()
    yield
    service.reset_public_metadata_state()


@pytest.fixture
def catalog(monkeypatch):
    papers = {}

    def lookup(_self, identifier, include_resources=False):
        if identifier in papers:
            return papers[identifier]
        raise PaperNotFoundError(f"No paper found for identifier '{identifier}'")

    monkeypatch.setattr(PaperService, "get_paper_by_id_or_arxiv", lookup)
    return papers


def _client(monkeypatch, upstream):
    monkeypatch.setattr(
        service,
        "_new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(upstream.handler)),
    )
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    return TestClient(app)


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("2610.18869", ("arxiv", "2610.18869")),
        ("2610.18869v2", ("arxiv", "2610.18869")),
        ("arXiv:2610.18869v1", ("arxiv", "2610.18869")),
        ("https://arxiv.org/abs/2610.18869v3", ("arxiv", "2610.18869")),
        ("https:/arxiv.org/pdf/2610.18869.pdf", ("arxiv", "2610.18869")),
        ("https://huggingface.co/papers/2610.18869", ("arxiv", "2610.18869")),
        ("10.48550/arXiv.2610.18869", ("arxiv", "2610.18869")),
        ("https://doi.org/10.48550/arXiv.2610.18869", ("arxiv", "2610.18869")),
        ("cs/0610046", ("arxiv", "cs/0610046")),
        ("https://huggingface.co/papers/cs/0610046", ("arxiv", "cs/0610046")),
        ("10.1000/xyz123", ("doi", "10.1000/xyz123")),
        ("doi:10.1000/xyz123", ("doi", "10.1000/xyz123")),
        ("12345", ("catalog_id", "12345")),
        ("attention is all you need", None),
        ("https://example.com/paper", None),
    ],
)
def test_parse_reference(identifier, expected):
    reference = service.parse_reference(identifier)
    assert (reference and (reference.kind, reference.value)) == expected


def test_unindexed_arxiv_paper_falls_back_to_arxiv(monkeypatch, catalog):
    upstream = Upstream(
        {"https://arxiv.org/abs/": httpx.Response(200, content=ABS_PAGE)}
    )
    client = _client(monkeypatch, upstream)

    response = client.get("/api/v1/papers/2610.18869v2/public-metadata")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    body = response.json()
    assert body["in_catalog"] is False
    assert body["catalog_id"] is None
    assert body["metadata_source"] == "arxiv"
    assert body["id"] == body["arxiv_id"] == "2610.18869"
    assert body["title"] == "Fresh & Unindexed Paper"
    assert body["authors"] == ["Jane Doe", "Rick Roe Jr"]
    assert body["published"] == "2026-10-13"
    assert body["repositories"] == ["https://github.com/acme/fresh"]
    assert body["hf_url"] is None
    assert [(link["kind"], link["url"]) for link in body["available_at"]] == [
        ("abstract", "https://arxiv.org/abs/2610.18869"),
        ("pdf", "https://arxiv.org/pdf/2610.18869"),
        ("code", "https://github.com/acme/fresh"),
    ]
    assert "Not indexed by Papers With Code" in body["note"]
    assert upstream.calls == [
        "https://huggingface.co/api/papers/2610.18869",
        "https://arxiv.org/abs/2610.18869",
    ]


def test_hugging_face_metadata_wins_and_hits_are_cached(monkeypatch, catalog):
    upstream = Upstream(
        {"https://huggingface.co/api/papers/": httpx.Response(200, json=HF_PAPER)}
    )
    client = _client(monkeypatch, upstream)

    first = client.get(
        "/api/v1/papers/https://huggingface.co/papers/2610.00001/public-metadata"
    )
    second = client.get("/api/v1/papers/2610.00001/public-metadata")

    assert first.json() == second.json()
    body = first.json()
    assert body["metadata_source"] == "huggingface"
    assert body["title"] == "Hugging Face Paper"
    assert body["authors"] == ["Ada Lovelace"]
    assert body["hf_url"] == "https://huggingface.co/papers/2610.00001"
    assert [link["kind"] for link in body["available_at"]] == [
        "abstract",
        "pdf",
        "huggingface",
        "code",
        "project_page",
    ]
    assert len(upstream.calls) == 1


def test_doi_uses_crossref(monkeypatch, catalog):
    upstream = Upstream(
        {"https://api.crossref.org/works/": httpx.Response(200, json=CROSSREF_WORK)}
    )
    client = _client(monkeypatch, upstream)

    body = client.get("/api/v1/papers/10.1000/xyz123/public-metadata").json()

    assert body["metadata_source"] == "crossref"
    assert body["doi"] == "10.1000/xyz123"
    assert body["arxiv_id"] is None
    assert body["published"] == "2024-05"
    assert body["abstract"] == "Some text."
    assert body["authors"] == ["Grace Hopper"]
    assert [(link["label"], link["url"]) for link in body["available_at"]] == [
        ("Publisher page", "https://doi.org/10.1000/xyz123"),
    ]


def test_catalog_paper_reports_in_catalog_without_outbound_calls(monkeypatch, catalog):
    catalog["2504.12516"] = SimpleNamespace(
        id="777",
        arxiv_id="2504.12516",
        source="arxiv",
        title="Catalog Paper",
        authors=["A. Author"],
        abstract="Indexed.",
        published=date(2025, 4, 16),
        url_abs="https://arxiv.org/abs/2504.12516",
        url_pdf="https://arxiv.org/pdf/2504.12516",
    )
    upstream = Upstream({})
    client = _client(monkeypatch, upstream)

    body = client.get(
        "/api/v1/papers/https://arxiv.org/abs/2504.12516v1/public-metadata"
    ).json()

    assert body["in_catalog"] is True
    assert body["catalog_id"] == "777"
    assert body["catalog_url"] == "https://paperswithcode.co/paper/2504.12516"
    assert body["metadata_source"] == "paperswithcode"
    assert body["available_at"][0]["kind"] == "catalog"
    assert upstream.calls == []


def test_unknown_everywhere_is_a_cached_404(monkeypatch, catalog):
    upstream = Upstream({})
    client = _client(monkeypatch, upstream)

    first = client.get("/api/v1/papers/2610.99999/public-metadata")
    second = client.get("/api/v1/papers/2610.99999/public-metadata")

    assert first.status_code == second.status_code == 404
    assert first.json()["detail"]["code"] == "paper_not_found"
    assert first.headers["cache-control"] == "public, max-age=3600"
    assert len(upstream.calls) == 2  # HF + arXiv once; the miss is cached


def test_upstream_outage_is_503_not_404(monkeypatch, catalog):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    upstream = Upstream(
        {
            "https://huggingface.co/": timeout,
            "https://arxiv.org/abs/": httpx.Response(503),
            "https://export.arxiv.org/": timeout,
        }
    )
    client = _client(monkeypatch, upstream)

    response = client.get("/api/v1/papers/2610.18869/public-metadata")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "public_metadata_unavailable"
    assert response.headers["retry-after"] == "60"


def test_arxiv_api_answers_when_abstract_page_fails(monkeypatch, catalog):
    feed = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>http://arxiv.org/abs/2610.18869v1</id><title>From the API</title>
    <summary>Text.</summary><published>2026-10-13T00:00:00Z</published>
    <author><name>Jane Doe</name></author></entry></feed>"""
    upstream = Upstream(
        {
            "https://arxiv.org/abs/": httpx.Response(500),
            "https://export.arxiv.org/api/query": httpx.Response(200, content=feed),
        }
    )
    client = _client(monkeypatch, upstream)

    body = client.get("/api/v1/papers/2610.18869/public-metadata").json()

    assert body["title"] == "From the API"
    assert body["metadata_source"] == "arxiv"


def test_oversized_responses_are_capped(monkeypatch, catalog):
    page = ABS_PAGE + b" " * (2 * service.MAX_RESPONSE_BYTES)
    upstream = Upstream({"https://arxiv.org/abs/": httpx.Response(200, content=page)})
    with httpx.Client(transport=httpx.MockTransport(upstream.handler)) as client:
        sources = service.PublicPaperSources(client)
        body = sources._get("https://arxiv.org/abs/2610.18869")
    assert len(body) == service.MAX_RESPONSE_BYTES


def test_uncached_lookups_are_rate_limited_per_client(monkeypatch, catalog):
    monkeypatch.setattr(service, "CLIENT_LOOKUPS_PER_WINDOW", 2)
    upstream = Upstream({})
    client = _client(monkeypatch, upstream)

    statuses = [
        client.get(f"/api/v1/papers/2610.0000{n}/public-metadata").status_code
        for n in range(3)
    ]
    cached = client.get("/api/v1/papers/2610.00000/public-metadata")

    assert statuses == [404, 404, 429]
    assert cached.status_code == 404  # cache hits never count against the budget


def test_invalid_identifier_is_400(monkeypatch, catalog):
    client = _client(monkeypatch, Upstream({}))
    response = client.get("/api/v1/papers/not%20a%20paper/public-metadata")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_paper_identifier"


def test_paper_endpoint_404_keeps_string_detail_and_adds_code(monkeypatch, catalog):
    upstream = Upstream({})
    client = _client(monkeypatch, upstream)

    response = client.get("/api/v1/papers/2610.18869")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "No paper found for identifier '2610.18869'",
        "code": "paper_not_in_catalog",
    }
    assert upstream.calls == []


def _request(client, real_ip):
    headers = [(b"x-real-ip", real_ip.encode())] if real_ip else []
    return Request({"type": "http", "client": client, "headers": headers})


@pytest.mark.parametrize(
    ("client", "real_ip", "expected"),
    [
        (None, "203.0.113.7", "203.0.113.7"),  # nginx over the unix socket
        (None, "not-an-ip", None),
        (None, None, None),
        (("198.51.100.2", 1234), "203.0.113.7", "198.51.100.2"),  # untrusted peer
        (("127.0.0.1", 1234), "203.0.113.7", "203.0.113.7"),
    ],
)
def test_proxied_client_ip(client, real_ip, expected):
    assert get_proxied_client_ip(_request(client, real_ip)) == expected
