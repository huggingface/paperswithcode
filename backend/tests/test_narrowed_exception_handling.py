import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

import aiohttp
import pytest

import backend.database.repos_and_pages_setup.batch_extract as batch_extract
import backend.services.paper_service as paper_service_module
import backend.utils.paper_utils as paper_utils
from backend.services.paper_service import PaperService
from backend.services.semantic_scholar_service import SemanticScholarUnavailableError
from backend.services.thumbnail_service import ThumbnailService
from backend.utils import pdf_utils


def _cleanup_service(cache_dir):
    service = object.__new__(ThumbnailService)
    service.storage_backend = "local"
    service.legacy_cache_dir = cache_dir
    return service


def test_thumbnail_cleanup_deletes_old_files(tmp_path):
    old = tmp_path / "old.jpg"
    new = tmp_path / "new.jpg"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    stale = time.time() - 40 * 24 * 60 * 60
    os.utime(old, (stale, stale))

    assert _cleanup_service(tmp_path).cleanup_old_thumbnails(30) == 1
    assert not old.exists() and new.exists()


def test_thumbnail_cleanup_surfaces_permission_errors(tmp_path, monkeypatch):
    old = tmp_path / "old.jpg"
    old.write_bytes(b"x")
    stale = time.time() - 40 * 24 * 60 * 60
    os.utime(old, (stale, stale))

    def denied(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(type(old), "unlink", denied)

    with pytest.raises(PermissionError):
        _cleanup_service(tmp_path).cleanup_old_thumbnails(30)


def test_unreadable_pdf_has_no_hyperlinks(tmp_path):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")

    assert pdf_utils.extract_hyperlinks_from_pdf(str(pdf)) == []


def test_hyperlink_extraction_bugs_propagate(tmp_path, monkeypatch):
    def broken_open(_path):
        raise AttributeError("bug")

    monkeypatch.setattr(pdf_utils.pdfplumber, "open", broken_open)

    with pytest.raises(AttributeError):
        asyncio.run(pdf_utils.safe_extract_hyperlinks_async(str(tmp_path / "x.pdf")))


def test_retry_requires_at_least_one_attempt():
    async def never_called():
        raise AssertionError("must not run")

    with pytest.raises(ValueError):
        asyncio.run(pdf_utils.async_retry_with_backoff(never_called, max_retries=0))


def test_retry_reraises_last_failure():
    calls = []

    async def flaky():
        calls.append(1)
        raise aiohttp.ClientError("down")

    with pytest.raises(aiohttp.ClientError):
        asyncio.run(
            pdf_utils.async_retry_with_backoff(
                flaky,
                max_retries=2,
                base_delay=0,
                retry_exceptions=(aiohttp.ClientError,),
            )
        )
    assert len(calls) == 2


def test_semantic_scholar_outage_keeps_local_results(monkeypatch):
    service = PaperService(Mock())
    local = [SimpleNamespace(title="Local")]
    monkeypatch.setattr(service, "search_papers", lambda _query, _limit: local)

    class Unavailable:
        def __init__(self, _db):
            pass

        async def get_highly_cited_papers(self, _query, _limit):
            raise SemanticScholarUnavailableError("rate limited")

    monkeypatch.setattr(paper_service_module, "SemanticScholarService", Unavailable)

    assert asyncio.run(service.search_papers_with_semantic_scholar("q", 5)) == local


def test_semantic_scholar_supplement_database_errors_propagate(monkeypatch):
    db = Mock()
    db.query.side_effect = RuntimeError("database down")
    service = PaperService(db)
    monkeypatch.setattr(service, "search_papers", lambda _query, _limit: [])

    class Cited:
        def __init__(self, _db):
            pass

        async def get_highly_cited_papers(self, _query, _limit):
            return [("Attention Is All You Need", 100)]

    monkeypatch.setattr(paper_service_module, "SemanticScholarService", Cited)

    with pytest.raises(RuntimeError):
        asyncio.run(service.search_papers_with_semantic_scholar("q", 5))


def test_failed_url_save_rolls_back_and_propagates(monkeypatch):
    import backend.services.repository_service as repository_service

    class BrokenRepositories:
        def __init__(self, _db):
            pass

        def create_repository_for_paper(self, **_kwargs):
            raise RuntimeError("insert failed")

    monkeypatch.setattr(repository_service, "RepositoryService", BrokenRepositories)
    extractor = object.__new__(batch_extract.BatchURLExtractor)
    extractor.dry_run = False
    db = Mock()

    with pytest.raises(RuntimeError):
        extractor.save_results_to_db(db, 1, "https://github.com/a/b", "")

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_comment_fetch_transport_errors_degrade(monkeypatch):
    class FailingSession:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def get(self, *_args, **_kwargs):
            raise aiohttp.ClientConnectionError("down")

    monkeypatch.setattr(paper_utils.aiohttp, "ClientSession", FailingSession)

    comments = asyncio.run(paper_utils.get_comments("2401.00001"))

    assert comments.endswith("No comments were found (due to error).")
