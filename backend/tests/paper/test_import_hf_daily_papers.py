import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import aiohttp
import pytest

WORKFLOWS_DIR = Path(__file__).parents[3] / ".github" / "workflows"
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.append(str(WORKFLOWS_DIR))

from scripts.daily import import_hf_daily_papers as importer_module  # noqa: E402
from scripts.daily.import_hf_daily_papers import (  # noqa: E402
    HuggingFaceDailyPapersJob,
)


def _paper(arxiv_id):
    return {"paper": {"id": arxiv_id}}


class _Response:
    def __init__(self, status, payload=None, json_error=None):
        self.status = status
        self.payload = payload
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, *, params, timeout):
        self.requests.append((url, params, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _job_with_responses(monkeypatch, responses):
    job = HuggingFaceDailyPapersJob.__new__(HuggingFaceDailyPapersJob)
    job.logger = MagicMock()
    session = _Session(responses)
    monkeypatch.setattr(importer_module.aiohttp, "ClientSession", lambda: session)
    return job, session


def _fetch(job, date="2026-06-04"):
    return asyncio.run(job.fetch_daily_papers(date))


def test_fetches_more_than_fifty_papers_across_pages(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    second_page = [_paper(f"2606.{index:05d}") for index in range(50, 54)]
    job, session = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, second_page)],
    )

    result = _fetch(job)

    assert result == first_page + second_page
    assert [request[1]["p"] for request in session.requests] == [0, 1]
    assert all(request[1]["limit"] == 50 for request in session.requests)
    assert all(request[1]["sort"] == "publishedAt" for request in session.requests)


def test_exact_page_size_fetches_empty_terminal_page(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, session = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, [])],
    )

    assert _fetch(job) == first_page
    assert [request[1]["p"] for request in session.requests] == [0, 1]


def test_duplicate_ids_across_pages_are_removed_in_first_seen_order(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    duplicate = first_page[-1]
    new_paper = _paper("2606.99999")
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(200, [duplicate, new_paper])],
    )

    result = _fetch(job)

    assert result == first_page + [new_paper]


@pytest.mark.parametrize("response", [_Response(200, []), _Response(400)])
def test_empty_and_http_400_dates_return_empty(monkeypatch, response):
    job, session = _job_with_responses(monkeypatch, [response])

    assert _fetch(job) == []
    assert len(session.requests) == 1


def test_later_page_failure_raises_instead_of_returning_partial_cohort(monkeypatch):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), _Response(503)],
    )

    with pytest.raises(RuntimeError, match="HTTP 503 on page 1"):
        _fetch(job)

    job.logger.error.assert_called_once()


def test_later_page_network_failure_raises_instead_of_returning_partial_cohort(
    monkeypatch,
):
    first_page = [_paper(f"2606.{index:05d}") for index in range(50)]
    job, _ = _job_with_responses(
        monkeypatch,
        [_Response(200, first_page), aiohttp.ClientConnectionError("disconnected")],
    )

    with pytest.raises(RuntimeError, match="page 1: disconnected"):
        _fetch(job)

    job.logger.error.assert_called_once()


def test_existing_paper_retries_external_duplicate_merge(monkeypatch):
    job = HuggingFaceDailyPapersJob.__new__(HuggingFaceDailyPapersJob)
    job.logger = MagicMock()
    job.get_paper_by_arxiv_id = MagicMock(return_value={"id": 109717})
    job._link_organizations = MagicMock()
    session = MagicMock()
    external = SimpleNamespace(id=109693)
    monkeypatch.setattr(
        importer_module, "db_manager", SimpleNamespace(session_local=lambda: session)
    )
    monkeypatch.setattr(
        importer_module,
        "find_external_paper_for_title",
        MagicMock(return_value=external),
    )
    merge = MagicMock(return_value={"hf_artifacts_merged": 3})
    monkeypatch.setattr(importer_module, "merge_external_paper_into_arxiv", merge)

    job.process_paper({"paper": {"id": "2608.24053", "title": "Example"}})

    merge.assert_called_once_with(session, 109693, 109717)
    session.commit.assert_called_once_with()


def test_external_duplicate_merge_failure_rolls_back_and_propagates(monkeypatch):
    job = HuggingFaceDailyPapersJob.__new__(HuggingFaceDailyPapersJob)
    job.logger = MagicMock()
    job.get_paper_by_arxiv_id = MagicMock(return_value={"id": 109717})
    job._link_organizations = MagicMock()
    job.error_count = 0
    session = MagicMock()
    monkeypatch.setattr(
        importer_module, "db_manager", SimpleNamespace(session_local=lambda: session)
    )
    monkeypatch.setattr(
        importer_module,
        "find_external_paper_for_title",
        MagicMock(side_effect=RuntimeError("duplicate")),
    )

    with pytest.raises(RuntimeError, match="duplicate"):
        job.process_paper({"paper": {"id": "2608.24053", "title": "Example"}})

    assert job.error_count == 0
    session.rollback.assert_called_once_with()


def test_run_continues_after_one_failure_emits_summary_then_raises(monkeypatch):
    job = HuggingFaceDailyPapersJob.__new__(HuggingFaceDailyPapersJob)
    job.logger = MagicMock()
    job.target_date = "2026-08-28"
    job.lookback_days = 1
    for name in (
        "processed_count",
        "fetched_count",
        "fetched_dates",
        "error_count",
        "new_papers_count",
        "new_authors_count",
        "new_repos_count",
        "new_pages_count",
        "new_tasks_count",
        "new_methods_count",
        "new_organization_links_count",
        "unknown_organizations_seen",
    ):
        setattr(job, name, 0)
    job.load_task_keywords = MagicMock()
    job.load_method_keywords = MagicMock()
    papers = [_paper("2608.00001"), _paper("2608.00002"), _paper("2608.00003")]

    async def fetch(_date):
        return papers

    job.fetch_daily_papers = fetch
    job.process_paper = MagicMock(
        side_effect=[None, RuntimeError("merge failed"), None]
    )
    job.vacuum_analyze_table = MagicMock()
    job.execute_query = MagicMock()

    with pytest.raises(RuntimeError, match="1 paper import failure"):
        job.run()

    assert job.process_paper.call_count == 3
    assert job.execute_query.call_count == 2
    assert [call.args[1][1] for call in job.execute_query.call_args_list] == [
        "2608.00001",
        "2608.00003",
    ]
    assert job.processed_count == 2
    assert job.error_count == 1
    summary_call = next(
        call
        for call in job.logger.info.call_args_list
        if call.args and call.args[0] == "HF_DAILY_PAPERS_SUMMARY %s"
    )
    assert json.loads(summary_call.args[1]) == {
        "upstream_fetch_succeeded": True,
        "dates_fetched": 1,
        "fetched": 3,
        "inserted": 0,
        "updated": 2,
        "skipped": 0,
        "failed": 1,
    }
    assert job.vacuum_analyze_table.call_count == 6
