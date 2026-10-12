"""Fetchable URL seeding and catalog web-fetch policy."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.chat_execution_policy import (
    MAX_FETCHABLE_URLS,
    bounded_url_seed,
    validate_url_seed,
)
from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.tool_policy import ToolBudget
from backend.services.chat_web_fetch_service import (
    ChatWebFetchError,
    _arxiv_identifier,
    _public_addresses,
    _validate_body_size,
    _validate_origin_metadata,
    authorize_catalog_url,
    canonical_fetch_url,
)


def test_fetchable_url_seed_is_strict_sorted_and_bounded():
    urls = sorted(f"https://example.com/{index}" for index in range(MAX_FETCHABLE_URLS))
    assert validate_url_seed(urls) == urls
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed([*urls, "https://example.com/overflow"])
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed(["https://127.0.0.1/private"])
    with pytest.raises(ValueError, match="Invalid fetchable URL seed"):
        validate_url_seed(["https://example.com/b", "https://example.com/a"])


def test_fetchable_url_seed_stabilizes_punctuation_exposed_by_fragment_removal():
    urls = bounded_url_seed(["https://huggingface.co/moonshotai/Kimi-K3&gt;#"])

    assert urls == ["https://huggingface.co/moonshotai/Kimi-K3&gt"]
    assert validate_url_seed(urls) == urls


def test_web_fetch_is_disabled_during_controlled_comparison():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    budget.observe_urls("Read https://example.com/paper and http://127.0.0.1/private")

    assert not budget.authorize(
        "fetch", "WebFetch", {"url": "https://arxiv.org/abs/2607.12345"}
    ).allowed
    assert not budget.authorize(
        "observed", "WebFetch", {"url": "https://example.com/paper"}
    ).allowed
    assert not budget.authorize(
        "unknown", "WebFetch", {"url": "https://example.com/unseen"}
    ).allowed
    assert not budget.authorize(
        "subdomain", "WebFetch", {"url": "https://export.arxiv.org/abs/2607.12345"}
    ).allowed
    assert not budget.authorize(
        "private", "WebFetch", {"url": "http://127.0.0.1/private"}
    ).allowed
    assert not budget.authorize(
        "http", "WebFetch", {"url": "http://arxiv.org/abs/2607.12345"}
    ).allowed


def test_tool_results_make_returned_urls_fetchable():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    assert budget.authorize("info", "Bash", {"command": "pwc paper info 1"}).allowed
    budget.result(
        "info",
        "Project page: https://example.com/project",
        status="success",
        exit_code=0,
    )

    assert not budget.authorize(
        "fetch", "WebFetch", {"url": "https://example.com/project"}
    ).allowed


def test_web_fetch_results_do_not_authorize_discovered_links():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    source = "https://arxiv.org/abs/2607.12345"
    budget.observe_urls(source)
    assert not budget.authorize("fetch", "WebFetch", {"url": source}).allowed
    budget.result(
        "fetch",
        "Discovered https://example.com/not-catalog-authorized",
        status="success",
    )
    assert not budget.authorize(
        "follow",
        "WebFetch",
        {"url": "https://example.com/not-catalog-authorized"},
    ).allowed


def test_catalog_web_fetch_url_normalization_and_arxiv_matching():
    assert (
        canonical_fetch_url("https://ARXIV.org:443/abs/2503.19108/#section")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert _arxiv_identifier("https://arxiv.org/pdf/2503.19108v2.pdf") == "2503.19108"
    assert _arxiv_identifier("https://arxiv.org/abs/2503.19108?download=1") is None
    for value in (
        "http://arxiv.org/abs/2503.19108",
        "https://user@arxiv.org/abs/2503.19108",
        "https://arxiv.org:444/abs/2503.19108",
    ):
        with pytest.raises(ChatWebFetchError):
            canonical_fetch_url(value)


def test_catalog_web_fetch_requires_existing_arxiv_or_exact_attached_url():
    class Result:
        def __init__(self, found):
            self.found = found

        def scalar_one(self):
            return self.found

    class DB:
        def __init__(self, *results):
            self.results = iter(results)

        def execute(self, _statement):
            return Result(next(self.results))

    assert (
        authorize_catalog_url(DB(True), "https://arxiv.org/abs/2503.19108")
        == "https://arxiv.org/abs/2503.19108"
    )
    assert (
        authorize_catalog_url(DB(True), "https://github.com/org/repo")
        == "https://github.com/org/repo"
    )
    with pytest.raises(ChatWebFetchError, match="not linked"):
        authorize_catalog_url(DB(False), "https://arxiv.org/abs/2503.19108")
    with pytest.raises(ChatWebFetchError, match="not attached"):
        authorize_catalog_url(DB(False, False), "https://github.com/org/repo/issues")


def test_catalog_web_fetch_rejects_private_dns_redirects_and_unsupported_content(
    monkeypatch,
):
    class Loop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: Loop())
    with pytest.raises(ChatWebFetchError, match="private network"):
        asyncio.run(_public_addresses("example.com"))
    with pytest.raises(ChatWebFetchError, match="redirect"):
        _validate_origin_metadata(302, "text/html")
    with pytest.raises(ChatWebFetchError, match="Unsupported"):
        _validate_origin_metadata(200, "application/octet-stream")
    with pytest.raises(ChatWebFetchError, match="too large"):
        _validate_body_size(b"x" * (10 * 1024 * 1024 + 1))
    assert _validate_origin_metadata(200, "text/html; charset=utf-8") == "text/html"


def test_worker_disables_native_web_fetch_and_uses_supported_proxy_settings():
    source = Path(agent.__file__).read_text()
    assert 'else ["Bash", "Read"]' in source
    assert '"skipWebFetchPreflight": True' not in source
    assert '"HTTPS_PROXY": "http://127.0.0.1:8766"' in source
    assert '"NO_PROXY": "127.0.0.1,localhost"' in source
    assert '"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"' in source
    assert '"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"' in source
