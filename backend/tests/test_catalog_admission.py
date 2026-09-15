import asyncio

import pytest

from backend.services.catalog_admission import (
    CatalogAdmissionMiddleware,
    is_catalog_read,
)


def scope(path="/api/v1/papers/", method="GET"):
    return {"type": "http", "method": method, "path": path}


@pytest.mark.parametrize(
    "path",
    ["/api/v1/papers/", "/api/v1/datasets/1", "/api/v1/areas/6", "/paper/123", "/"],
)
def test_catalog_paths(path):
    assert is_catalog_read(scope(path))


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/chat/stream",
        "/api/v1/chat/sessions",
        "/api/v1/auth/me",
        "/internal/deployment-status",
        "/health",
        "/api/v1/papers-extra",
    ],
)
def test_control_paths_and_writes_bypass(path):
    assert not is_catalog_read(scope(path))
    assert not is_catalog_read(scope("/api/v1/papers/", "POST"))
    assert not is_catalog_read({"type": "websocket"})


@pytest.mark.anyio
async def test_saturation_preserves_chat_and_holds_slot_through_body():
    entered = asyncio.Event()
    finish = asyncio.Event()
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.disconnect"}

    async def app(request, receive, send):
        if request["path"] == "/api/v1/chat/stream":
            await send({"type": "chat-reached"})
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        entered.set()
        await finish.wait()
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = CatalogAdmissionMiddleware(app, limit=1)
    first = asyncio.create_task(middleware(scope(), receive, send))
    await entered.wait()
    await middleware(scope(), receive, send)
    rejected = [m for m in sent if m.get("status") == 503]
    assert len(rejected) == 1
    assert (b"retry-after", b"1") in rejected[0]["headers"]
    assert (b"cache-control", b"no-store") in rejected[0]["headers"]
    await middleware(scope("/api/v1/chat/stream", "POST"), receive, send)
    assert {"type": "chat-reached"} in sent
    assert middleware.active == 1
    finish.set()
    await first
    await middleware(scope(), receive, send)
    assert middleware.active == 0
    assert sum(m.get("status") == 200 for m in sent) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_slot_released_on_exception_or_cancellation(failure):
    async def app(*args):
        raise failure()

    middleware = CatalogAdmissionMiddleware(app, limit=1)
    with pytest.raises(failure):
        await middleware(scope(), None, None)
    assert middleware.active == 0


@pytest.fixture
def anyio_backend():
    return "asyncio"
