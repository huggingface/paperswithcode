"""Fetchable URL seed validation and the absent WebFetch tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.chat_execution_policy import (
    MAX_FETCHABLE_URLS,
    bounded_url_seed,
    validate_url_seed,
)
from backend.chat_sandbox_worker import agent
from backend.chat_sandbox_worker.tool_policy import ToolBudget


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


def test_web_fetch_is_not_an_available_tool():
    budget = ToolBudget(
        maximum_calls=12,
        maximum_direct_searches=4,
        maximum_result_bytes=1024,
        maximum_turn_output_bytes=4096,
    )
    budget.register_call("fetch")

    decision = budget.authorize(
        "fetch", "WebFetch", {"url": "https://arxiv.org/abs/2607.12345"}
    )

    assert not decision.allowed
    assert decision.reason == "That tool is not available."


def test_worker_disables_native_web_fetch_and_uses_supported_proxy_settings():
    source = Path(agent.__file__).read_text()
    assert 'else ["Bash", "Read"]' in source
    assert '"WebFetch",' in source
    assert "PWC_WEBFETCH_TOKEN_FD" not in source
    assert '"HTTPS_PROXY": "http://127.0.0.1:8766"' in source
    assert '"NO_PROXY": "127.0.0.1,localhost"' in source
    assert '"NODE_EXTRA_CA_CERTS": "/tmp/pwc-webfetch-ca.pem"' in source
    assert '"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"' in source
    assert '"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"' in source
