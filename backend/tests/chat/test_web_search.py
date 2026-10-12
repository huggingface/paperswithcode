import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.chat_sandbox_worker.prompt import render
from backend.chat_sandbox_worker import agent
from backend.chat_sandbox_worker.tool_policy import ToolBudget, WEB_SEARCH_TOOL
from backend.config import Settings
from backend.models.database import (
    Base,
    ChatWebSearchBudgetState,
    ChatWebSearchCircuitEvent,
    ChatWebSearchOwnerUsage,
)
from backend.services import chat_web_search_service as web
from backend.services.chat_stream_service import ChatTurnProjection


def configured_settings(**overrides) -> Settings:
    return Settings(
        environment="staging",
        chat_web_search_enabled=True,
        chat_web_search_exa_api_key="test-secret",
        **overrides,
    )


def test_normalized_results_are_https_denylisted_and_bounded():
    settings = configured_settings(
        chat_web_search_domain_denylist="blocked.example",
        chat_web_search_max_result_bytes=4_096,
    )
    payload = web.normalize_exa_payload(
        {
            "results": [
                {
                    "title": f" Result {index} ",
                    "url": url,
                    "image": "https://images.example/preview.png",
                    "favicon": "http://insecure.example/favicon.ico",
                    "publishedDate": "2026-08-07T00:00:00.000Z",
                    "highlights": ["x" * 500],
                }
                for index, url in enumerate(
                    [
                        "http://insecure.example/source",
                        "https://blocked.example/source",
                        "https://one.example/source",
                        "https://two.example/source",
                        "https://three.example/source",
                        "https://four.example/source",
                        "https://five.example/source",
                        "https://six.example/source",
                    ]
                )
            ]
        },
        settings,
    )

    assert len(payload["results"]) <= 5
    assert all(result["url"].startswith("https://") for result in payload["results"])
    assert all("blocked.example" not in result["url"] for result in payload["results"])
    assert all(
        result["image_url"] == "https://images.example/preview.png"
        for result in payload["results"]
    )
    assert all(result["favicon_url"] is None for result in payload["results"])
    assert web._serialized_size(payload) <= 4_096


def test_hugging_face_blog_social_image_fills_missing_provider_image(monkeypatch):
    async def fetch(_url, **kwargs):
        assert kwargs["allowed_hosts"] == web._HF_BLOG_HOSTS
        return SimpleNamespace(
            body=(
                b'<html><head><meta property="og:image" '
                b'content="https://huggingface.co/blog/assets/smollm3/image.png">'
            )
        )

    monkeypatch.setattr(web, "fetch_public_resource", fetch)
    payload = {
        "results": [
            {
                "url": "https://huggingface.co/blog/smollm3",
                "image_url": None,
            },
            {
                "url": "https://example.com/post",
                "image_url": None,
            },
        ]
    }

    asyncio.run(web._enrich_hf_blog_images(payload, configured_settings(), 1.0))

    assert payload["results"][0]["image_url"] == (
        "https://huggingface.co/blog/assets/smollm3/image.png"
    )
    assert payload["results"][1]["image_url"] is None


def test_provider_retry_is_one_visible_call_but_two_metered_attempts(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ChatWebSearchBudgetState.__table__,
            ChatWebSearchCircuitEvent.__table__,
            ChatWebSearchOwnerUsage.__table__,
        ],
    )
    factory = sessionmaker(engine)
    monkeypatch.setattr(web, "db_manager", SimpleNamespace(session_local=factory))
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Primary source",
                            "url": "https://example.com/source",
                            "highlights": ["Evidence" * 1_000],
                        }
                    ],
                    "costDollars": {"total": 0.002},
                },
            ),
        ]
    )

    async def dispatch(_query, _settings, _timeout):
        return next(responses)

    monkeypatch.setattr(web, "_dispatch_exa", dispatch)
    settings = configured_settings(chat_web_search_max_result_bytes=4_096)
    result = asyncio.run(
        web.search_web("current AI research", settings, owner_hash="a" * 64)
    )

    assert result["results"][0]["url"] == "https://example.com/source"
    assert web._serialized_size(result) <= settings.chat_web_search_max_result_bytes
    with factory() as db:
        state = db.execute(select(ChatWebSearchBudgetState)).scalar_one()
        owner = db.execute(select(ChatWebSearchOwnerUsage)).scalar_one()
        assert state.call_count == 2
        assert state.success_count == 1
        assert state.failure_count == 0
        assert state.provider_cost_microusd == 2_000
        assert owner.call_count == 2


def test_worker_policy_counts_web_and_overall_budgets_and_latches_failure():
    disabled = ToolBudget(12, 4, 1024, 4096)
    assert not disabled.authorize("w0", WEB_SEARCH_TOOL, {"query": "news"}).allowed

    budget = ToolBudget(
        12,
        4,
        1024,
        4096,
        maximum_web_searches=3,
        web_search_enabled=True,
    )
    assert budget.authorize("w1", WEB_SEARCH_TOOL, {"query": "news"}).allowed
    budget.result("w1", "unavailable", status="error")
    assert budget.calls == 1
    assert budget.web_searches == 1
    assert not budget.authorize("w2", WEB_SEARCH_TOOL, {"query": "again"}).allowed
    assert not budget.authorize(
        "invalid", WEB_SEARCH_TOOL, {"query": "x", "extra": True}
    ).allowed


def test_web_search_results_do_not_authorize_web_fetch():
    budget = ToolBudget(
        12,
        4,
        1024,
        4096,
        maximum_web_searches=3,
        web_search_enabled=True,
    )
    assert budget.authorize("web", WEB_SEARCH_TOOL, {"query": "release"}).allowed
    budget.result(
        "web", '{"results":[{"url":"https://example.com/release"}]}', status="success"
    )

    assert not budget.authorize(
        "fetch", "WebFetch", {"url": "https://example.com/release"}
    ).allowed


def test_worker_prompt_keeps_stable_web_tool_instructions_and_varies_metadata():
    disabled = render(web_search_enabled=False)
    enabled = render(web_search_enabled=True)
    disabled_prefix, disabled_metadata = disabled.rsplit("# Turn metadata", 1)
    enabled_prefix, enabled_metadata = enabled.rsplit("# Turn metadata", 1)

    assert disabled_prefix == enabled_prefix
    assert "search_web" in disabled
    assert "search_web" in enabled
    assert "hard ceiling is 3 searches" in enabled
    assert "untrusted evidence" in enabled
    assert '"web_search_enabled":false' in disabled_metadata
    assert '"web_search_enabled":true' in enabled_metadata


def test_worker_options_keep_the_exact_mcp_tool_schema_stable(monkeypatch):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )
    settings = agent.WorkerSettings()
    hooks = agent.WorkerToolHooks(settings)

    disabled = agent._options(
        settings, hooks, model="model-a", resume=None, web_search_enabled=False
    )
    enabled = agent._options(
        settings, hooks, model="model-a", resume=None, web_search_enabled=True
    )

    assert WEB_SEARCH_TOOL in disabled.allowed_tools
    assert WEB_SEARCH_TOOL not in disabled.disallowed_tools
    assert set(disabled.mcp_servers) == {"web"}
    assert "search_web" in disabled.system_prompt
    assert "model-a" in disabled.system_prompt
    assert WEB_SEARCH_TOOL in enabled.allowed_tools
    assert WEB_SEARCH_TOOL not in enabled.disallowed_tools
    assert set(enabled.mcp_servers) == {"web"}
    assert "search_web" in enabled.system_prompt
    assert disabled.allowed_tools == enabled.allowed_tools
    assert disabled.disallowed_tools == enabled.disallowed_tools
    assert (
        disabled.system_prompt.rsplit("# Turn metadata", 1)[0]
        == (enabled.system_prompt.rsplit("# Turn metadata", 1)[0])
    )


def test_projection_persists_only_exact_authoritative_web_citations(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chat_stream_service.resolve_citation_targets",
        lambda _db, _text: ([], {}),
    )
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call",
        {"id": "web-1", "name": "search_web", "args": {"query": "release"}},
    )
    projection.apply(
        "tool_result",
        {
            "id": "web-1",
            "status": "success",
            "took_ms": 12,
            "content": [
                {
                    "type": "text",
                    "text": '{"results":[{"title":"Official","url":"https://example.com/release","published_date":null,"excerpt":"Evidence","image_url":"https://cdn.example.com/release.png","favicon_url":"https://example.com/favicon.ico"}]}',
                    "truncated": False,
                }
            ],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply(
        "answer_delta",
        {
            "text": "[supported](https://example.com/release) and [invented](https://other.example/item)"
        },
    )

    _answer, citations = projection.finalize(object())

    assert citations == [
        {
            "kind": "external_source",
            "position": 0,
            "route_id": None,
            "url": "https://example.com/release",
            "source_type": "article",
            "provider": "web",
            "title": "Official",
            "excerpt": "Evidence",
            "source_url": None,
            "thumbnail_url": "https://cdn.example.com/release.png",
            "favicon_url": "https://example.com/favicon.ico",
            "arxiv_id": None,
            "semantic_scholar_id": None,
            "authors": [],
            "published": None,
            "conference": None,
            "citation_count": None,
        }
    ]
    assert projection.blocks[-1]["citations"] == citations


def test_query_validation_is_content_free_and_strict():
    with pytest.raises(web.WebSearchValidationError):
        asyncio.run(web.search_web(" ", configured_settings(), owner_hash="a" * 64))
