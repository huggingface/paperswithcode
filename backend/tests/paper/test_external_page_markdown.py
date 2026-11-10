from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.routers import paper_reader
from backend.services import external_page_markdown_service as service
from backend.services.external_page_markdown_service import (
    ExternalPageMarkdownError,
    ScrapedPage,
)

TITLE = "LFM2.5-24B-A2B: Built for Fast On-Device Agents"
URL = "https://www.liquid.ai/blog/lfm2-5-24b-a2b"
ARTICLE = (
    "# LFM2.5-24B-A2B: Built for Fast On-Device Agents\n\n"
    + "Today we release a sparse reasoning model for agents on device. " * 60
)


@pytest.mark.parametrize(
    ("source_url", "conference_pdf", "expected"),
    [
        (URL, None, URL),
        ("https://github.com/acme/model", None, "https://github.com/acme/model"),
        ("https://example.com/report.pdf", None, None),
        (URL, "https://example.com/paper.pdf", None),
        ("https://ras.papercept.net/program.html#thi1i_171", None, None),
        ("https://doi.org/10.1145/3763359", None, None),
        ("https://aclanthology.org/2020.lrec-1.297/", None, None),
        ("https://www.sciencedirect.com/science/article/pii/1", None, None),
        ("http://127.0.0.1/blog", None, None),
        ("ftp://example.com/blog", None, None),
    ],
)
def test_external_page_url_admits_only_article_pages(
    source_url, conference_pdf, expected
):
    assert (
        service.external_page_url(
            source="external", source_url=source_url, conference_url_pdf=conference_pdf
        )
        == expected
    )


def test_external_page_url_ignores_arxiv_papers():
    assert (
        service.external_page_url(
            source="arxiv", source_url=URL, conference_url_pdf=None
        )
        is None
    )


def test_page_markdown_uses_the_canonical_paper_format():
    markdown = service.page_paper_markdown(TITLE, URL, ScrapedPage(TITLE, ARTICLE))

    assert markdown.startswith(
        f"Title: {TITLE}\n\nURL Source: {URL}\n\nMarkdown Content:\n\n# LFM"
    )


@pytest.mark.parametrize(
    ("page", "code"),
    [
        (ScrapedPage(TITLE, "# LFM2.5-24B-A2B\n\nShort abstract."), "page_too_short"),
        (
            ScrapedPage(
                "ICRA 2026 Program",
                "Session listing. " * 400 + f"\n{TITLE}\n",
            ),
            "page_title_mismatch",
        ),
    ],
)
def test_page_markdown_rejects_pages_that_are_not_the_paper(page, code):
    with pytest.raises(ExternalPageMarkdownError) as error:
        service.page_paper_markdown(TITLE, URL, page)

    assert error.value.code == code


def _firecrawl(monkeypatch, status_code: int, payload: dict):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status_code, json=payload)

    monkeypatch.setattr(service.httpx, "post", post)
    return calls


def test_scrape_page_requests_main_content_markdown(monkeypatch):
    calls = _firecrawl(
        monkeypatch,
        200,
        {
            "success": True,
            "data": {
                "markdown": ARTICLE,
                "metadata": {"title": TITLE, "statusCode": 200},
            },
        },
    )

    page = service.scrape_page(URL, api_key="fc-test", timeout_seconds=30)

    assert page == ScrapedPage(TITLE, ARTICLE)
    url, kwargs = calls[0]
    assert url == service.FIRECRAWL_SCRAPE_URL
    assert kwargs["headers"] == {"Authorization": "Bearer fc-test"}
    assert kwargs["json"]["formats"] == ["markdown"]
    assert kwargs["json"]["onlyMainContent"] is True


@pytest.mark.parametrize(
    ("status_code", "payload", "code", "retryable"),
    [
        (429, {"success": False}, "firecrawl_unavailable", True),
        (402, {"success": False}, "firecrawl_rejected", True),
        (
            200,
            {
                "success": True,
                "data": {"markdown": "", "metadata": {"statusCode": 404}},
            },
            "page_unavailable",
            False,
        ),
    ],
)
def test_scrape_page_classifies_failures(
    monkeypatch, status_code, payload, code, retryable
):
    _firecrawl(monkeypatch, status_code, payload)

    with pytest.raises(ExternalPageMarkdownError) as error:
        service.scrape_page(URL, api_key="fc-test", timeout_seconds=30)

    assert (error.value.code, error.value.retryable) == (code, retryable)


def test_scrape_page_requires_a_key():
    with pytest.raises(ExternalPageMarkdownError) as error:
        service.scrape_page(URL, api_key="", timeout_seconds=30)

    assert error.value.code == "firecrawl_not_configured"


class FakeBucket:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.batches: list[list[str]] = []

    def install(self, monkeypatch):
        bucket = self

        class Api:
            def __init__(self, token=None):
                pass

            def batch_bucket_files(self, bucket_id, *, add, token=None):
                bucket.batches.append([key for _, key in add])
                for data, key in add:
                    bucket.files[key] = data

        class Handle:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                return self.data

        class FileSystem:
            def __init__(self, token=None):
                pass

            def _key(self, path):
                return path.split("/", 5)[5]

            def open(self, path, mode="rb", block_size=0):
                key = self._key(path)
                if key not in bucket.files:
                    raise FileNotFoundError(path)
                return Handle(bucket.files[key])

            def exists(self, path):
                return self._key(path) in bucket.files

            def invalidate_cache(self, path=None):
                pass

        monkeypatch.setattr(service, "HfApi", Api)
        monkeypatch.setattr(service, "BucketFileSystem", FileSystem)
        return self


def _prepare(**overrides):
    arguments = {
        "paper_id": "123294",
        "title": TITLE,
        "page_url": URL,
        "api_key": "fc-test",
        "bucket_id": "huggingface/pwc-papers-content",
        "token": None,
        "timeout_seconds": 30,
    }
    return service.prepare_external_page_markdown(**(arguments | overrides))


def test_prepare_publishes_revision_alias_and_manifest(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    monkeypatch.setattr(
        service, "scrape_page", lambda *args, **kwargs: ScrapedPage(TITLE, ARTICLE)
    )

    version = _prepare()

    content_key = f"_content/sha256/{version[:2]}/{version}.md"
    assert bucket.batches[0] == [
        content_key,
        "external/123294.md",
        "_content/manifests/external/123294.json",
    ]
    manifest = json.loads(bucket.files["_content/manifests/external/123294.json"])
    assert manifest["paper_key"] == "external/123294"
    assert manifest["content_key"] == content_key
    assert bucket.files["external/123294.md"] == bucket.files[content_key]
    status = json.loads(bucket.files[service.status_key("123294")])
    assert status["status"] == "succeeded"
    assert status["markdown_sha256"] == version


def test_prepare_does_not_publish_during_a_markdown_migration(monkeypatch):
    bucket = FakeBucket({"_content/migration.lock": b"locked"}).install(monkeypatch)
    monkeypatch.setattr(service, "scrape_page", pytest.fail)

    with pytest.raises(ExternalPageMarkdownError) as error:
        _prepare()

    assert (error.value.code, error.value.retryable) == (
        "markdown_migration_locked",
        True,
    )
    assert bucket.batches == []


def test_prepare_records_failures_and_does_not_rescrape_permanent_ones(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    scrapes = []

    def scrape(*args, **kwargs):
        scrapes.append(args)
        return ScrapedPage(TITLE, "too short")

    monkeypatch.setattr(service, "scrape_page", scrape)

    for _ in range(2):
        with pytest.raises(ExternalPageMarkdownError) as error:
            _prepare()
        assert error.value.code == "page_too_short"

    assert len(scrapes) == 1
    status = json.loads(bucket.files[service.status_key("123294")])
    assert (status["status"], status["retryable"]) == ("failed", False)


def test_prepare_reports_a_page_in_backoff_as_retryable(monkeypatch):
    FakeBucket().install(monkeypatch)
    scrapes = []

    def scrape(*args, **kwargs):
        scrapes.append(args)
        raise ExternalPageMarkdownError("firecrawl_unavailable", retryable=True)

    monkeypatch.setattr(service, "scrape_page", scrape)

    for _ in range(2):
        with pytest.raises(ExternalPageMarkdownError) as error:
            _prepare()
        assert (error.value.code, error.value.retryable) == (
            "firecrawl_unavailable",
            True,
        )

    assert len(scrapes) == 1


def test_prepare_backs_off_after_a_storage_failure(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    scrapes = []

    def scrape(*args, **kwargs):
        scrapes.append(args)
        return ScrapedPage(TITLE, ARTICLE)

    def publish(*args, **kwargs):
        raise service.HfHubHTTPError(
            "bucket unavailable",
            response=httpx.Response(
                503, request=httpx.Request("POST", "https://hf.co")
            ),
        )

    monkeypatch.setattr(service, "scrape_page", scrape)
    monkeypatch.setattr(service, "publish_paper_markdown", publish)

    for _ in range(2):
        with pytest.raises(ExternalPageMarkdownError) as error:
            _prepare()
        assert (error.value.code, error.value.retryable) == (
            "storage_unavailable",
            True,
        )

    assert len(scrapes) == 1
    status = json.loads(bucket.files[service.status_key("123294")])
    assert (status["error_class"], status["retryable"]) == ("storage_unavailable", True)


def _failing_publish(*args, **kwargs):
    raise service.HfHubHTTPError(
        "bucket unavailable",
        response=httpx.Response(503, request=httpx.Request("POST", "https://hf.co")),
    )


def test_storage_outages_never_exhaust_a_page(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    monkeypatch.setattr(
        service, "scrape_page", lambda *args, **kwargs: ScrapedPage(TITLE, ARTICLE)
    )
    monkeypatch.setattr(service, "publish_paper_markdown", _failing_publish)
    monkeypatch.setattr(service, "retry_due", lambda status: True)

    for _ in range(service.MAX_ATTEMPTS + 2):
        with pytest.raises(ExternalPageMarkdownError):
            _prepare()

    status = json.loads(bucket.files[service.status_key("123294")])
    assert (status["attempt_count"], status["retryable"]) == (0, True)


def test_scrape_failures_stop_after_the_attempt_limit(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)

    def scrape(*args, **kwargs):
        raise ExternalPageMarkdownError("firecrawl_unavailable", retryable=True)

    monkeypatch.setattr(service, "scrape_page", scrape)
    monkeypatch.setattr(service, "retry_due", lambda status: True)

    for _ in range(service.MAX_ATTEMPTS):
        with pytest.raises(ExternalPageMarkdownError):
            _prepare()

    status = json.loads(bucket.files[service.status_key("123294")])
    assert (status["attempt_count"], status["retryable"]) == (3, False)


@pytest.mark.parametrize("failing", ["open", "exists", "batch"])
def test_bucket_errors_surface_as_retryable_storage_unavailable(monkeypatch, failing):
    FakeBucket().install(monkeypatch)
    monkeypatch.setattr(
        service, "scrape_page", lambda *args, **kwargs: ScrapedPage(TITLE, ARTICLE)
    )
    if failing == "batch":
        monkeypatch.setattr(service.HfApi, "batch_bucket_files", _failing_publish)
    else:

        def fail(*args, **kwargs):
            raise OSError("bucket unreachable")

        monkeypatch.setattr(service.BucketFileSystem, failing, fail)

    with pytest.raises(ExternalPageMarkdownError) as error:
        _prepare()

    assert (error.value.code, error.value.retryable) == ("storage_unavailable", True)


def test_prepare_does_not_record_a_missing_key(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)

    with pytest.raises(ExternalPageMarkdownError):
        _prepare(api_key="")

    assert bucket.files == {}


def test_retry_due_honours_backoff_and_the_retryable_flag():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    later = (now + timedelta(hours=1)).isoformat()
    earlier = (now - timedelta(hours=1)).isoformat()

    assert service.retry_due({}, now=now)
    assert service.retry_due(
        {
            "status": "failed",
            "retryable": True,
            "attempt_count": 1,
            "next_retry_at": earlier,
        },
        now=now,
    )
    assert not service.retry_due(
        {
            "status": "failed",
            "retryable": True,
            "attempt_count": 1,
            "next_retry_at": later,
        },
        now=now,
    )
    assert not service.retry_due(
        {"status": "failed", "retryable": False, "attempt_count": 1}, now=now
    )


class FakeSession:
    def __init__(self, paper):
        self.paper = paper

    def get(self, model, paper_id):
        return self.paper if self.paper and self.paper.id == paper_id else None


@pytest.fixture
def reader_client():
    app = create_app()
    state = {
        "paper": SimpleNamespace(
            id=123294,
            title=TITLE,
            source="external",
            source_url=URL,
            conference_url_pdf=None,
        )
    }
    app.dependency_overrides[get_database_session] = lambda: FakeSession(state["paper"])
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
        hf_token="",
        firecrawl_api_key="fc-test",
    )
    yield TestClient(app), state
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """Scraping on a miss is for signed-in readers; tests opt out explicitly."""

    monkeypatch.setattr(paper_reader, "has_session", lambda _request: True)


def test_web_markdown_returns_stored_markdown_without_scraping(
    monkeypatch, reader_client
):
    client, _ = reader_client
    monkeypatch.setattr(
        paper_reader,
        "read_paper_markdown_bounded",
        lambda *args, **kwargs: ("stored", False),
    )
    monkeypatch.setattr(paper_reader, "prepare_external_page_markdown", pytest.fail)

    response = client.get("/api/v1/papers/123294/web-markdown")

    assert response.status_code == 200
    assert response.text == "stored"


def test_web_markdown_prepares_missing_markdown_once(monkeypatch, reader_client):
    client, _ = reader_client
    store: dict[str, str] = {}

    def read(*args, **kwargs):
        if "markdown" not in store:
            raise ValueError("Markdown for paper external/123294 was not found")
        return store["markdown"], False

    def prepare(**kwargs):
        assert kwargs["page_url"] == URL
        store["markdown"] = "prepared"
        return "digest"

    monkeypatch.setattr(paper_reader, "read_paper_markdown_bounded", read)
    monkeypatch.setattr(paper_reader, "prepare_external_page_markdown", prepare)

    response = client.get("/api/v1/papers/123294/web-markdown")

    assert response.status_code == 200
    assert response.text == "prepared"


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ExternalPageMarkdownError("page_title_mismatch"), 422),
        (ExternalPageMarkdownError("firecrawl_unavailable", retryable=True), 503),
        (ExternalPageMarkdownError("firecrawl_not_configured"), 503),
    ],
)
def test_web_markdown_reports_unreadable_pages(
    monkeypatch, reader_client, error, status_code
):
    client, _ = reader_client

    def read(*args, **kwargs):
        raise ValueError("Markdown for paper external/123294 was not found")

    def prepare(**kwargs):
        raise error

    monkeypatch.setattr(paper_reader, "read_paper_markdown_bounded", read)
    monkeypatch.setattr(paper_reader, "prepare_external_page_markdown", prepare)

    response = client.get("/api/v1/papers/123294/web-markdown")

    assert response.status_code == status_code
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "paper",
    [
        None,
        SimpleNamespace(
            id=123294,
            title=TITLE,
            source="external",
            source_url="https://example.com/a.pdf",
            conference_url_pdf=None,
        ),
    ],
)
def test_web_markdown_is_not_found_without_a_web_page(reader_client, paper):
    client, state = reader_client
    state["paper"] = paper

    response = client.get("/api/v1/papers/123294/web-markdown")

    assert response.status_code == 404


def test_hourly_backfill_prepares_a_bounded_batch_of_due_pages(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import Mock

    from backend.tests.paper.markdown_harness import MODULE

    rows = [
        SimpleNamespace(
            id=paper_id,
            title=TITLE,
            source="external",
            source_url=url,
            conference_url_pdf=None,
        )
        for paper_id, url in [
            (1, "https://example.com/stored"),
            (2, "https://example.com/failed"),
            (3, "https://example.com/new"),
            (4, "https://doi.org/10.1/landing"),
        ]
    ]

    @contextmanager
    def session_local():
        yield SimpleNamespace(execute=lambda query: rows)

    monkeypatch.setattr(
        MODULE, "db_manager", SimpleNamespace(session_local=session_local)
    )
    prepared = []
    monkeypatch.setattr(
        MODULE,
        "prepare_external_page_markdown",
        lambda **kwargs: prepared.append(kwargs["paper_id"]) or "digest",
    )
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job.full = True
    job.should_execute = True
    job.logger = Mock()
    job.settings = SimpleNamespace(
        paper_markdown_hf_bucket_id="bucket", hf_token="", firecrawl_api_key="fc-test"
    )
    job._existing_paths = lambda bucket, paths: {"external/1.md": object()}
    job._status_records = lambda paths: {
        service.status_key("2"): {
            "status": "failed",
            "retryable": False,
            "attempt_count": 1,
        }
    }

    framed = []
    monkeypatch.setattr(
        MODULE,
        "record_page_framing",
        lambda paper_id, page_url, **kwargs: framed.append(paper_id) or True,
    )

    counts = job._prepare_external_pages()

    assert prepared == ["3"]
    assert framed == ["1", "2", "3"]
    assert counts == {
        "external_pages_eligible": 3,
        "external_pages_missing": 2,
        "external_pages_due": 1,
        "external_pages_published": 1,
        "external_pages_failed": 0,
        "external_pages_framing_due": 3,
        "external_pages_framing_checked": 3,
        "external_pages_frameable": 3,
    }


def test_anonymous_miss_does_not_spend_firecrawl_credits(monkeypatch, reader_client):
    client, _ = reader_client
    monkeypatch.setattr(paper_reader, "has_session", lambda _request: False)

    def missing(*args, **kwargs):
        raise ValueError("Markdown for paper external/123294 was not found")

    monkeypatch.setattr(paper_reader, "read_paper_markdown_bounded", missing)
    monkeypatch.setattr(paper_reader, "prepare_external_page_markdown", pytest.fail)

    response = client.get("/api/v1/papers/123294/web-markdown")

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("source_url", "exists", "status", "pending"),
    [
        ("https://openai.com/index/introducing-gpt-6-1-terra", False, {}, True),
        ("https://openai.com/index/introducing-gpt-6-1-terra", True, {}, False),
        (
            "https://openai.com/index/introducing-gpt-6-1-terra",
            False,
            {"status": "failed", "retryable": True},
            True,
        ),
        (
            "https://openai.com/index/introducing-gpt-6-1-terra",
            False,
            {"status": "failed", "retryable": False},
            False,
        ),
        ("https://openai.com/index/introducing-gpt-6-1-terra#models", False, {}, False),
    ],
)
def test_web_markdown_pending_never_waits_on_unreadable_pages(
    monkeypatch, source_url, exists, status, pending
):
    checked = []

    class Filesystem:
        def __init__(self, *, token):
            assert token == "token"

        def exists(self, path):
            checked.append(path)
            return exists

    monkeypatch.setattr(service, "BucketFileSystem", Filesystem)
    monkeypatch.setattr(service, "read_status", lambda *_a, **_kw: status)
    paper = SimpleNamespace(
        id=131370, source="external", source_url=source_url, conference_url_pdf=None
    )

    assert (
        service.web_markdown_pending(paper, bucket_id="b/c", token="token") is pending
    )
    if "#" not in source_url:
        assert checked == ["hf://buckets/b/c/external/131370.md"]


@pytest.mark.parametrize(
    ("headers", "blocker"),
    [
        ({}, None),
        ({"X-Frame-Options": "SAMEORIGIN"}, "x_frame_options"),
        ({"Content-Security-Policy": "frame-ancestors 'self'"}, "frame_ancestors"),
        ({"Content-Security-Policy": "default-src 'self'; frame-ancestors *"}, None),
        (
            {
                "Content-Security-Policy": "frame-ancestors https://paperswithcode.co/",
                "X-Frame-Options": "DENY",
            },
            None,
        ),
        ({"Content-Security-Policy": "default-src 'self'"}, None),
    ],
)
def test_frame_blocker_follows_browser_precedence(headers, blocker):
    assert service._frame_blocker(httpx.Headers(headers)) == blocker


def _framing_client(monkeypatch, handler, *, public=True):
    real_client = httpx.Client
    monkeypatch.setattr(
        service.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(service, "_public_host", lambda host: public)


HTML = {"content-type": "text/html; charset=utf-8"}


@pytest.mark.parametrize(
    ("responses", "public", "expected"),
    [
        ({URL: httpx.Response(200, headers=HTML)}, True, (True, "allowed")),
        (
            {URL: httpx.Response(200, headers=HTML | {"X-Frame-Options": "DENY"})},
            True,
            (False, "x_frame_options"),
        ),
        (
            {URL: httpx.Response(301, headers={"location": "http://example.com/a"})},
            True,
            (False, "insecure"),
        ),
        ({URL: httpx.Response(200, headers=HTML)}, False, (False, "private_address")),
        ({URL: httpx.Response(404, headers=HTML)}, True, (False, "http_status")),
        ({URL: httpx.Response(302, headers=HTML)}, True, (False, "http_status")),
        ({URL: httpx.Response(200, headers=HTML)}, None, (False, "unreachable")),
        (
            {URL: httpx.Response(200, headers={"content-type": "application/pdf"})},
            True,
            (False, "not_html"),
        ),
        (
            {
                URL: httpx.Response(302, headers={"location": "/blog/moved"}),
                "https://www.liquid.ai/blog/moved": httpx.Response(200, headers=HTML),
            },
            True,
            (True, "allowed"),
        ),
    ],
)
def test_check_page_framing(monkeypatch, responses, public, expected):
    _framing_client(
        monkeypatch, lambda request: responses[str(request.url)], public=public
    )

    assert service.check_page_framing(URL) == expected


def test_check_page_framing_stops_at_a_redirect_loop(monkeypatch):
    _framing_client(
        monkeypatch, lambda request: httpx.Response(302, headers={"location": URL})
    )

    assert service.check_page_framing(URL) == (False, "too_many_redirects")


def test_public_host_rejects_any_private_address(monkeypatch):
    addresses = {
        "public.example": ["93.184.215.14"],
        "mixed.example": ["93.184.215.14", "10.0.0.5"],
        "local.example": ["fe80::1%eth0"],
    }

    def getaddrinfo(host, *args, **kwargs):
        if host not in addresses:
            raise service.socket.gaierror("Name or service not known")
        return [(None, None, None, "", (address, 443)) for address in addresses[host]]

    monkeypatch.setattr(service.socket, "getaddrinfo", getaddrinfo)

    assert service._public_host("public.example")
    assert not service._public_host("mixed.example")
    assert service._public_host("local.example") is False
    assert service._public_host("missing.example") is None


def test_framing_due_rechecks_stale_moved_and_unreachable_pages():
    now = datetime(2026, 11, 3, tzinfo=UTC)

    def status(reason="allowed", age=timedelta(hours=1), page_url=URL):
        return {
            "framing": {
                "page_url": page_url,
                "frameable": reason == "allowed",
                "reason": reason,
                "checked_at": (now - age).isoformat(),
            }
        }

    assert service.framing_due({}, URL, now=now)
    assert not service.framing_due(status(), URL, now=now)
    assert service.framing_due(status(age=timedelta(days=8)), URL, now=now)
    assert service.framing_due(status(page_url="https://example.com/old"), URL, now=now)
    assert not service.framing_due(
        status("x_frame_options", timedelta(days=2)), URL, now=now
    )
    assert service.framing_due(status("unreachable", timedelta(days=2)), URL, now=now)


def test_framing_record_keeps_scrape_status_and_survives_a_scrape(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    monkeypatch.setattr(service, "check_page_framing", lambda url: (True, "allowed"))

    assert service.record_page_framing(
        "123294", URL, bucket_id="huggingface/pwc-papers-content", token=None
    )
    status = json.loads(bucket.files[service.status_key("123294")])
    assert service.page_frameable(status, URL)
    assert not service.page_frameable(status, "https://example.com/other")
    # A framing-only record is not a scrape attempt.
    assert service.retry_due(status)

    monkeypatch.setattr(
        service, "scrape_page", lambda *args, **kwargs: ScrapedPage(TITLE, ARTICLE)
    )
    _prepare()

    status = json.loads(bucket.files[service.status_key("123294")])
    assert status["status"] == "succeeded"
    assert service.page_frameable(status, URL)


@pytest.mark.parametrize(
    ("status", "frameable"),
    [
        ({}, False),
        ({"framing": {"page_url": URL, "frameable": True}}, True),
        ({"framing": {"page_url": URL, "frameable": False}}, False),
    ],
)
def test_web_page_reports_whether_the_reader_may_frame_it(
    monkeypatch, reader_client, status, frameable
):
    client, _ = reader_client
    monkeypatch.setattr(paper_reader, "read_status", lambda *args, **kwargs: status)

    response = client.get("/api/v1/papers/123294/web-page")

    assert response.status_code == 200
    assert response.json() == {"url": URL, "frameable": frameable}


def test_web_page_is_not_found_without_a_web_page(reader_client):
    client, state = reader_client
    state["paper"] = None

    assert client.get("/api/v1/papers/123294/web-page").status_code == 404
