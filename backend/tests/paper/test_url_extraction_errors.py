import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError

import backend.database.repos_and_pages_setup.batch_extract as batch_extract
import backend.genai_steps.extract_github_and_project_page_url as extraction
import backend.utils.hf_utils as hf_utils
import backend.utils.paper_utils as paper_utils
from backend.utils.pdf_utils import PDFDownloadError, PDFNotFoundError


def _hub_404() -> HfHubHTTPError:
    request = httpx.Request("GET", "https://huggingface.co/api/x")
    return HfHubHTTPError("missing", response=httpx.Response(404, request=request))


def _patch_simple_methods(monkeypatch, github_url="", project_page_url=""):
    async def daily_papers(arxiv_id):
        return github_url, project_page_url

    async def find_github(arxiv_id, abstract=None):
        return github_url

    async def no_wait():
        return None

    monkeypatch.setattr(
        extraction, "get_github_and_project_page_urls_from_daily_papers", daily_papers
    )
    monkeypatch.setattr(extraction, "find_github_url", find_github)
    monkeypatch.setattr(extraction, "_rate_limit_arxiv", no_wait)


def _patch_pdf_download(monkeypatch, error):
    @asynccontextmanager
    async def failing_download(arxiv_id):
        raise error
        yield

    monkeypatch.setattr(extraction, "temp_pdf_download", failing_download)


def test_missing_pdf_returns_urls_found_so_far(monkeypatch):
    _patch_simple_methods(monkeypatch, github_url="https://github.com/a/b")
    _patch_pdf_download(monkeypatch, PDFNotFoundError("404"))

    reasoning, response = asyncio.run(
        extraction.get_project_github_urls("2401.00001", abstract="x")
    )

    assert response == {"github_url": "https://github.com/a/b", "project_page_url": ""}


def test_transient_pdf_failure_propagates(monkeypatch):
    _patch_simple_methods(monkeypatch)
    _patch_pdf_download(monkeypatch, PDFDownloadError("captcha page"))

    with pytest.raises(PDFDownloadError):
        asyncio.run(extraction.get_project_github_urls("2401.00001", abstract="x"))


def test_llm_failure_inside_pdf_context_propagates(monkeypatch):
    _patch_simple_methods(monkeypatch)

    @asynccontextmanager
    async def download(arxiv_id):
        yield "/tmp/paper.pdf"

    async def first_pages(path):
        return path

    async def no_project_page(pdf_path):
        return ""

    async def broken_llm(*args, **kwargs):
        raise RuntimeError("provider 503")

    monkeypatch.setattr(extraction, "temp_pdf_download", download)
    monkeypatch.setattr(extraction, "extract_first_two_pages_pymupdf", first_pages)
    monkeypatch.setattr(extraction, "find_project_page_url", no_project_page)
    monkeypatch.setattr(extraction, "_extract_urls_with_llm", broken_llm)

    with pytest.raises(RuntimeError, match="provider 503"):
        asyncio.run(extraction.get_project_github_urls("2401.00001", abstract="x"))


def _extractor():
    extractor = batch_extract.BatchURLExtractor.__new__(batch_extract.BatchURLExtractor)
    extractor.generator = None
    extractor.stats = {
        "papers_processed": 0,
        "papers_with_both": 0,
        "papers_with_neither": 0,
        "api_errors": 0,
        "papers_skipped_critical_errors": 0,
    }
    extractor.saved = []
    extractor.save_results_to_db = lambda db, paper_id, *rest: extractor.saved.append(
        paper_id
    )
    return extractor


PAPER = {"id": 7, "arxiv_id": "2401.00001", "title": "T", "abstract": "A"}


def test_batch_does_not_mark_failed_paper_processed(monkeypatch):
    async def failing(**kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(batch_extract, "get_project_github_urls", failing)
    extractor = _extractor()

    results = asyncio.run(extractor.process_batch([PAPER], db=None))

    assert results == []
    assert extractor.saved == []
    assert extractor.stats["papers_skipped_critical_errors"] == 1


def test_batch_marks_successful_paper_processed(monkeypatch):
    async def found(**kwargs):
        return "", {"github_url": "https://github.com/a/b", "project_page_url": ""}

    monkeypatch.setattr(batch_extract, "get_project_github_urls", found)
    extractor = _extractor()

    results = asyncio.run(extractor.process_batch([PAPER], db=None))

    assert results[0]["success"] is True
    assert extractor.saved == [7]


def test_get_abstract_falls_back_to_arxiv_when_hub_has_no_paper(monkeypatch):
    def missing(id):
        raise _hub_404()

    async def arxiv_abstract(arxiv_id):
        return "from arxiv"

    monkeypatch.setattr(paper_utils, "paper_info", missing)
    monkeypatch.setattr(paper_utils, "get_abstract_arxiv", arxiv_abstract)

    assert asyncio.run(paper_utils.get_abstract("2401.00001")) == "from arxiv"


def test_get_title_returns_none_instead_of_sentinel(monkeypatch):
    def missing(id):
        raise _hub_404()

    async def no_arxiv_title(arxiv_id):
        return None

    monkeypatch.setattr(paper_utils, "paper_info", missing)
    monkeypatch.setattr(paper_utils, "get_title_arxiv", no_arxiv_title)

    assert asyncio.run(paper_utils.get_title("2401.00001")) is None


def test_hub_lookup_propagates_cancellation(monkeypatch):
    async def cancelled(func, *args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(paper_utils.asyncio, "to_thread", cancelled)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(paper_utils.get_title_hf_hub("2401.00001"))


def test_find_github_url_handles_missing_abstract(monkeypatch):
    async def no_abstract(arxiv_id):
        return None

    monkeypatch.setattr(paper_utils, "get_abstract", no_abstract)

    assert asyncio.run(paper_utils.find_github_url("2401.00001")) == ""


class _FakeHfApi:
    def __init__(self, result):
        self.result = result

    def get_user_overview(self, username, token=None):
        assert token is False
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_get_user_organizations_reads_hub_memberships(monkeypatch):
    user = SimpleNamespace(
        orgs=[SimpleNamespace(name="CraftJarvis"), SimpleNamespace(name="hf")]
    )
    monkeypatch.setattr(hf_utils, "HfApi", lambda: _FakeHfApi(user))

    assert asyncio.run(hf_utils.get_user_organizations("someone")) == [
        "CraftJarvis",
        "hf",
    ]


def test_get_user_organizations_returns_empty_for_unknown_user(monkeypatch):
    monkeypatch.setattr(hf_utils, "HfApi", lambda: _FakeHfApi(_hub_404()))

    assert asyncio.run(hf_utils.get_user_organizations("nobody")) == []


def _download_with(monkeypatch, outcome):
    import backend.utils.pdf_utils as pdf_utils

    async def fake_retry(func, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(pdf_utils, "async_retry_with_backoff", fake_retry)

    async def run():
        async with pdf_utils.temp_pdf_download("cs/0001001") as path:
            with open(path, "rb") as f:
                return f.read()

    return asyncio.run(run())


def test_temp_pdf_download_yields_path(monkeypatch):
    assert _download_with(monkeypatch, b"%PDF-1.7 body").startswith(b"%PDF-")


def test_temp_pdf_download_raises_on_html(monkeypatch):
    with pytest.raises(PDFDownloadError):
        _download_with(monkeypatch, b"%PDF- <html>recaptcha")


def test_temp_pdf_download_wraps_network_errors(monkeypatch):
    import aiohttp

    with pytest.raises(PDFDownloadError) as excinfo:
        _download_with(monkeypatch, aiohttp.ClientConnectionError("reset"))
    assert not isinstance(excinfo.value, PDFNotFoundError)


def test_temp_pdf_download_does_not_swallow_body_errors(monkeypatch):
    import backend.utils.pdf_utils as pdf_utils

    async def fake_retry(func, **kwargs):
        return b"%PDF-1.7 body"

    monkeypatch.setattr(pdf_utils, "async_retry_with_backoff", fake_retry)

    async def run():
        async with pdf_utils.temp_pdf_download("2401.00001"):
            raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(run())


@pytest.mark.parametrize(
    "github_url",
    ["https://github.com", "https://github.com/someuser", "https://gitlab.com/a/b"],
)
def test_save_skips_non_repository_github_url_and_marks_paper(monkeypatch, github_url):
    from backend.services.project_page_service import ProjectPageService
    from backend.services.repository_service import RepositoryService

    created = []
    monkeypatch.setattr(
        RepositoryService,
        "create_repository_for_paper",
        lambda self, **kwargs: created.append(kwargs),
    )
    monkeypatch.setattr(
        ProjectPageService,
        "create_project_page_for_paper",
        lambda self, **kwargs: object(),
    )

    class FakeDB:
        executed = []
        committed = False

        def execute(self, statement, params):
            self.executed.append(params)

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("save must not roll back")

    extractor = batch_extract.BatchURLExtractor.__new__(batch_extract.BatchURLExtractor)
    extractor.dry_run = False
    extractor.stats = {"papers_with_project_page": 0}
    db = FakeDB()

    extractor.save_results_to_db(db, 7, github_url, "https://example.org/project")

    assert created == []
    assert db.executed == [{"paper_id": 7}]
    assert db.committed
    assert extractor.stats["papers_with_project_page"] == 1
