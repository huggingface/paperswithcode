import asyncio
import json

import httpx
import pytest

from backend.services.chat_pwc_mcp import META, TOOL_NAMES, PwcMcpError, request_mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_stateless_protocol_envelope_and_no_private_credentials():
    def respond(request):
        payload = json.loads(request.content)
        assert request.url == "https://paperswithcode.co/mcp"
        assert "authorization" not in request.headers
        assert "x-pwc-turn" not in request.headers
        assert payload["params"]["_meta"] == META
        assert payload["params"]["name"] == "search_papers"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"structuredContent": {"items": []}},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await request_mcp(
            client,
            "tools/call",
            {"name": "search_papers", "arguments": {"query": "VLA"}},
        )
    assert result == {"structuredContent": {"items": []}}


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["redirect", "error", "bad_id", "large", "invalid"])
async def test_upstream_failures_are_bounded_sanitized_and_never_retried(kind):
    calls = []

    def respond(request):
        calls.append(request)
        payload = json.loads(request.content)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://other.test"})
        if kind == "large":
            return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        if kind == "invalid":
            return httpx.Response(200, content=b"private error content")
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"] if kind == "error" else "other",
                "error": {"message": "secret"},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), follow_redirects=False
    ) as client:
        with pytest.raises(PwcMcpError) as error:
            await request_mcp(client, "tools/call", {})
    assert "secret" not in str(error.value) and "private" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.anyio
async def test_tool_discovery_requires_complete_allowlist_and_ignores_extra_tools():
    def respond(request):
        payload = json.loads(request.content)
        tools = [{"name": name} for name in TOOL_NAMES] + [{"name": "unreviewed_tool"}]
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": tools}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await request_mcp(client, "tools/list", {})
    assert {t["name"] for t in result["tools"]} == TOOL_NAMES


@pytest.mark.anyio
async def test_cancellation_propagates_to_pending_transport():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def respond(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        task = asyncio.create_task(request_mcp(client, "tools/call", {}))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cancelled.is_set()


@pytest.mark.anyio
async def test_gateway_disconnect_cancels_upstream_without_leaving_tasks(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    import backend.chat_gateway_app as gateway

    started, cancelled = asyncio.Event(), asyncio.Event()

    async def call(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def disconnected():
        await started.wait()
        return True

    monkeypatch.setattr(gateway, "request_mcp", call)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pwc_mcp_client=None)),
        is_disconnected=disconnected,
    )
    with pytest.raises(HTTPException) as error:
        await gateway.catalog_mcp(
            gateway.McpCatalogRequest(tool="search_papers"), request
        )
    assert error.value.status_code == 499
    assert cancelled.is_set()


@pytest.mark.parametrize(
    "tool,args,expected",
    [
        ("search_papers", {"query": "VLA"}, "search"),
        ("list_papers", {"search": "VLA"}, "search"),
        ("get_paper_info", {"paper": "1"}, "mcp_catalog"),
        (None, {}, "mcp_catalog"),
    ],
)
def test_gateway_meters_before_dispatch_and_preserves_fence(
    monkeypatch, tool, args, expected
):
    from types import SimpleNamespace
    import backend.chat_gateway_app as gateway

    events = []
    capability = object()
    fence = object()

    def scope(*args, **kwargs):
        assert args[1] == "catalog" and kwargs["turn_fence"] is fence
        events.append("authorized")
        return capability

    class Meter:
        def __init__(self, db):
            pass

        def meter_catalog(self, row, operation, maximum_searches):
            assert row is capability and operation == expected and maximum_searches == 4
            events.append("metered")

    monkeypatch.setattr(gateway, "_scope", scope)
    monkeypatch.setattr(gateway, "ChatCapabilityService", Meter)
    db = SimpleNamespace(commit=lambda: events.append("committed"))
    settings = SimpleNamespace(
        chat_pwc_mcp_enabled=True, chat_max_direct_search_calls=4
    )
    gateway._authorize_pwc_mcp(
        gateway.McpCatalogRequest(tool=tool, arguments=args),
        "Bearer token",
        "session",
        "turn",
        fence,
        db,
        settings,
    )
    assert events == ["authorized", "metered", "committed"]


def test_gateway_denies_disabled_unknown_and_exhausted_calls(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    import backend.chat_gateway_app as gateway

    settings = SimpleNamespace(
        chat_pwc_mcp_enabled=False, chat_max_direct_search_calls=4
    )
    for body, status in [
        (gateway.McpCatalogRequest(), 503),
        (gateway.McpCatalogRequest(tool="unreviewed"), 422),
    ]:
        with pytest.raises(HTTPException) as error:
            gateway._authorize_pwc_mcp(
                body, "Bearer token", "s", "t", None, None, settings
            )
        assert error.value.status_code == status
        settings.chat_pwc_mcp_enabled = True
    monkeypatch.setattr(gateway, "_scope", lambda *args, **kw: object())

    def exhausted(*args, **kwargs):
        raise gateway.CapabilityError("exhausted")

    monkeypatch.setattr(gateway.ChatCapabilityService, "meter_catalog", exhausted)
    events = []
    db = SimpleNamespace(rollback=lambda: events.append("rollback"))
    with pytest.raises(HTTPException) as error:
        gateway._authorize_pwc_mcp(
            gateway.McpCatalogRequest(tool="search_papers"),
            "Bearer token",
            "s",
            "t",
            None,
            db,
            settings,
        )
    assert error.value.status_code == 429 and events == ["rollback"]


def test_protected_flag_transition_preserves_every_other_setting():
    from deploy.configure_chat_pwc_mcp import enabled_values
    from deploy.configure_host_env import decoded_value

    current = {
        "PWC_ENVIRONMENT": "PWC_ENVIRONMENT=staging",
        "UNRELATED": "UNRELATED=preserved",
    }
    result = enabled_values(current, "staging")
    assert all(result[k] == v for k, v in current.items())
    assert decoded_value(result["PWC_CHAT_PWC_MCP_ENABLED"]) == "true"
    with pytest.raises(ValueError):
        enabled_values(current, "production")
    with pytest.raises(ValueError):
        enabled_values(result, "staging")


def test_mcp_nginx_route_is_post_only_and_environment_isolated():
    from pathlib import Path
    from deploy.nginx_validate import validate

    root = Path(__file__).resolve().parents[2] / "deploy/nginx"
    prod = (root / "paperswithcode.co.conf").read_text()
    stage = (root / "staging.paperswithcode.co.conf").read_text()
    assert validate(prod, stage) == []
    before, route = stage.split("location = /api/internal/chat-gateway/catalog-mcp", 1)
    bad = (
        before
        + "location = /api/internal/chat-gateway/catalog-mcp"
        + route.replace("pwc_staging_backend", "pwc_production_backend", 1)
    )
    assert "staging MCP gateway must be POST-only and environment-isolated" in validate(
        prod, bad
    )


@pytest.mark.anyio
async def test_completed_call_does_not_wait_for_disconnect_poll_that_swallows_cancel(
    monkeypatch,
):
    from types import SimpleNamespace
    import backend.chat_gateway_app as gateway

    polling = asyncio.Event()
    cancellations = 0

    async def call(*_args):
        await polling.wait()
        return {"structuredContent": {"title": "Paper"}}

    async def disconnected():
        nonlocal cancellations
        polling.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellations += 1
            if cancellations > 1:
                raise
            # Starlette's disconnect probe uses a local AnyIO cancellation scope.
            return False

    monkeypatch.setattr(gateway, "request_mcp", call)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pwc_mcp_client=None)),
        is_disconnected=disconnected,
    )
    task = asyncio.create_task(
        gateway.catalog_mcp(gateway.McpCatalogRequest(), request)
    )
    done, _ = await asyncio.wait({task}, timeout=0.3)
    if not done:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert done, "Completed MCP response was held until the client disconnected"
    assert task.result() == {"result": {"structuredContent": {"title": "Paper"}}}
