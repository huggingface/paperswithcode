from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
sys.path.insert(0, str(WORKFLOWS))
SCRIPT = WORKFLOWS / "scripts" / "hourly" / "update_citations.py"
SPEC = importlib.util.spec_from_file_location("update_citations_cron", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _job():
    job = object.__new__(MODULE.CitationHourlyUpdateJob)
    job.logger = Mock()
    job.chunk_size = 2
    job.stats = {
        "papers_found": 0,
        "papers_processed": 0,
        "citations_updated": 0,
        "papers_selected": 0,
        "deadline_reached": False,
    }
    job.shutdown_requested = False
    job.deadline_monotonic = None
    job.request_timeout = 10
    job.request_delay = 1.5
    job.flush_reserve_seconds = 30
    job.api_key = None
    return job


def test_streaming_chunks_use_one_stable_selection():
    job = _job()
    papers = [{"id": paper_id} for paper_id in range(5)]
    job.get_papers_chunk = Mock(return_value=papers)
    job.process_papers_with_rate_limiting = AsyncMock(return_value=True)

    asyncio.run(job.process_papers_in_streaming_chunks(5))

    job.get_papers_chunk.assert_called_once_with(0, 5)
    assert job.stats["papers_selected"] == 5
    assert [
        [paper["id"] for paper in call.args[0]]
        for call in job.process_papers_with_rate_limiting.await_args_list
    ] == [[0, 1], [2, 3], [4]]


def test_streaming_chunks_stop_after_partial_chunk():
    job = _job()
    papers = [{"id": paper_id} for paper_id in range(5)]
    job.get_papers_chunk = Mock(return_value=papers)
    job.process_papers_with_rate_limiting = AsyncMock(side_effect=[True, False])

    asyncio.run(job.process_papers_in_streaming_chunks(5))

    assert job.process_papers_with_rate_limiting.await_count == 2
    job.logger.info.assert_any_call(
        "Stopping citation refresh cleanly; remaining selected "
        "papers stay eligible for the next hourly run"
    )


def test_request_admission_reserves_time_to_flush(monkeypatch):
    job = _job()
    job.deadline_monotonic = 100

    monkeypatch.setattr(MODULE.time, "monotonic", lambda: 58)
    assert job._can_start_request() is True
    assert job.stats["deadline_reached"] is False

    monkeypatch.setattr(MODULE.time, "monotonic", lambda: 59)
    assert job._can_start_request() is False
    assert job.stats["deadline_reached"] is True


def test_shutdown_prevents_another_request_without_claiming_deadline():
    job = _job()
    job.shutdown_requested = True

    assert job._can_start_request() is False
    assert job.stats["deadline_reached"] is False


def test_partial_batch_is_flushed_before_deadline_exit(monkeypatch):
    job = _job()
    papers = [
        {"id": 1, "arxiv_id": "2601.00001", "title": "One"},
        {"id": 2, "arxiv_id": "2601.00002", "title": "Two"},
    ]
    result = MODULE.CitationResult(1, "2601.00001", "One", 3, "s2", True)
    job._can_start_request = Mock(side_effect=[True, False])
    job.process_single_paper = AsyncMock(return_value=result)
    job.update_citations_batch = Mock()
    job.batch_size = 100

    class Client:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(MODULE.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(MODULE.asyncio, "sleep", AsyncMock())

    completed = asyncio.run(job.process_papers_with_rate_limiting(papers))

    assert completed is False
    job.update_citations_batch.assert_called_once_with([result])
    job.process_single_paper.assert_awaited_once_with(papers[0])


def _fetch_job(responses):
    job = _job()
    job.base_url = "https://example.com"
    job.client = SimpleNamespace(get=AsyncMock(side_effect=responses))
    job.stats.update(api_calls=0, api_successes=0, api_errors=0, rate_limit_hits=0)
    return job


def test_rate_limit_retries_same_paper_and_honors_retry_after(monkeypatch):
    data = {"title": "One", "citationCount": 12}
    job = _fetch_job(
        [
            SimpleNamespace(status_code=429, headers={"Retry-After": "12"}),
            SimpleNamespace(status_code=200, json=lambda: data),
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(MODULE.asyncio, "sleep", sleep)
    assert asyncio.run(job.fetch_citation_data("2601.00001", "One")) == data
    assert job.stats["api_calls"] == 2
    assert job.stats["api_errors"] == 0
    assert job.stats["rate_limit_hits"] == 1
    sleep.assert_awaited_once_with(12)


def test_rate_limit_does_not_retry_beyond_deadline(monkeypatch):
    import pytest

    job = _fetch_job([SimpleNamespace(status_code=429, headers={"Retry-After": "30"})])
    job.deadline_monotonic = 60
    monkeypatch.setattr(MODULE.time, "monotonic", lambda: 10)
    sleep = AsyncMock()
    monkeypatch.setattr(MODULE.asyncio, "sleep", sleep)
    with pytest.raises(RuntimeError, match="deadline"):
        asyncio.run(job.fetch_citation_data("2601.00001", "One"))
    assert job.stats["deadline_reached"] is True
    sleep.assert_not_awaited()
    assert job.client.get.await_count == 1
