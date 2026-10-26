from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
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
    job.api_keys = []
    job._key_index = 0
    job.db_session = Mock()
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


def test_short_due_selection_is_topped_up_with_early_refreshes():
    job = _job()
    job.get_papers_chunk = Mock(return_value=[{"id": 1}])
    job.get_early_refresh_chunk = Mock(return_value=[{"id": 7}, {"id": 8}])
    job.process_papers_with_rate_limiting = AsyncMock(return_value=True)

    asyncio.run(job.process_papers_in_streaming_chunks(3))

    job.get_early_refresh_chunk.assert_called_once_with(2)
    # The selection transaction ends before any Semantic Scholar call.
    job.db_session.close.assert_called_once_with()
    assert job.stats["papers_selected"] == 3
    assert job.stats["papers_refreshed_early"] == 2
    assert [
        [paper["id"] for paper in call.args[0]]
        for call in job.process_papers_with_rate_limiting.await_args_list
    ] == [[1, 7], [8]]


def test_steady_share_covers_the_cycle_with_headroom():
    job = _job()
    job.update_threshold_days = 7
    job.steady_rate_headroom = 1.2
    job.paper_service = Mock()
    job.paper_service.get_citation_refreshable_count.return_value = 115_283

    # 115,283 * 1.2 / 168 hours, rounded up.
    assert job.steady_papers_per_run() == 824


def test_run_refreshes_the_steady_share_when_nothing_is_due():
    job = _job()
    job.max_papers_per_run = 1500
    job.soft_runtime_seconds = 60
    job.max_runtime_seconds = 120
    job.stats.update(
        papers_deferred=0,
        credential_failures=0,
        api_calls=0,
        api_successes=0,
        api_errors=0,
        rate_limit_hits=0,
    )
    job.get_papers_count = Mock(return_value=0)
    job.steady_papers_per_run = Mock(return_value=824)
    job.process_papers_in_streaming_chunks = AsyncMock()
    job.log_summary = Mock()
    job.vacuum_analyze_table = Mock()

    job.run()

    job.process_papers_in_streaming_chunks.assert_awaited_once_with(824)


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


def test_requests_rotate_across_distinct_keys_including_429_retries(monkeypatch):
    data = {"title": "One", "citationCount": 12}
    job = _fetch_job(
        [
            SimpleNamespace(status_code=429, headers={}),
            SimpleNamespace(status_code=200, json=lambda: data),
            SimpleNamespace(status_code=200, json=lambda: data),
        ]
    )
    job.api_keys = ["primary", "secondary"]
    monkeypatch.setattr(MODULE.asyncio, "sleep", AsyncMock())

    asyncio.run(job.fetch_citation_data("2601.00001", "One"))
    asyncio.run(job.fetch_citation_data("2601.00001", "One"))

    keys = [call.kwargs["headers"] for call in job.client.get.await_args_list]
    assert keys == [
        {"x-api-key": "primary"},
        {"x-api-key": "secondary"},
        {"x-api-key": "primary"},
    ]


def test_keys_are_deduplicated_and_spacing_scales_per_key(monkeypatch):
    def job_with(primary, secondary):
        settings = SimpleNamespace(
            semantic_scholar_api_key=primary, semantic_scholar_api_key_2=secondary
        )
        monkeypatch.setattr(MODULE, "get_settings", lambda: settings)
        monkeypatch.setattr(MODULE, "get_database_session", lambda: iter([Mock()]))
        monkeypatch.setattr(MODULE.signal, "signal", Mock())
        monkeypatch.setattr(MODULE.DatabaseCronJob, "__init__", lambda *a, **k: None)
        return MODULE.CitationHourlyUpdateJob()

    two = job_with("a", "b")
    assert (two.api_keys, two.request_delay) == (["a", "b"], 0.75)
    same = job_with("a", "a")
    assert (same.api_keys, same.request_delay) == (["a"], 1.5)
    none = job_with("", "")
    assert (none.api_keys, none.request_delay, none._next_key_headers()) == (
        [],
        1.5,
        {},
    )


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


def test_batch_write_retries_once_after_dropped_connection():
    job = _job()
    job.paper_service = Mock()
    job.paper_service.update_citation_counts_batch.side_effect = [
        MODULE.DatabaseError("SSL connection has been closed unexpectedly"),
        {"updated": 1, "failed": 0},
    ]
    result = MODULE.CitationResult(1, "2601.00001", "One", 3, "s2", True)

    job.update_citations_batch([result])

    assert job.paper_service.update_citation_counts_batch.call_count == 2
    assert job.stats["citations_updated"] == 1


def test_batch_write_raises_when_retry_also_fails():
    job = _job()
    job.paper_service = Mock()
    job.paper_service.update_citation_counts_batch.side_effect = MODULE.DatabaseError(
        "down"
    )
    result = MODULE.CitationResult(1, "2601.00001", "One", 3, "s2", True)

    try:
        job.update_citations_batch([result])
    except MODULE.DatabaseError:
        pass
    else:
        raise AssertionError("second failure must propagate")
    assert job.paper_service.update_citation_counts_batch.call_count == 2
