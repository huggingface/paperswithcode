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
        monkeypatch.setattr(service, "HfFileSystem", FileSystem)
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
    monkeypatch.setattr(
        service, "scrape_page", lambda *args, **kwargs: ScrapedPage(TITLE, ARTICLE)
    )

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


def test_prepare_does_not_record_a_missing_key(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)

    with pytest.raises(ExternalPageMarkdownError):
        _prepare(api_key="")

    assert bucket.files == {}


def test_retry_due_honours_backoff_and_attempt_limit():
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
        {"status": "failed", "retryable": True, "attempt_count": 3}, now=now
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

    counts = job._prepare_external_pages()

    assert prepared == ["3"]
    assert counts == {
        "external_pages_eligible": 3,
        "external_pages_missing": 2,
        "external_pages_due": 1,
        "external_pages_published": 1,
        "external_pages_failed": 0,
    }
