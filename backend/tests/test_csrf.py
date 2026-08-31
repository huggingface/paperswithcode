import asyncio
import uuid

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.config import Settings
from backend.utils.csrf import cookie_request_passes_csrf


def _request(
    *,
    method: str = "POST",
    origin: str | None = None,
    cookie: str | None = "session-value",
    admin_token: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    if cookie is not None:
        headers.append((b"cookie", f"pwc_session={cookie}".encode()))
    if admin_token is not None:
        headers.append((b"x-admin-token", admin_token.encode()))
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/me/paper-edits",
            "headers": headers,
        }
    )


def test_production_cookie_mutation_requires_exact_origin():
    settings = Settings(
        environment="production",
        session_cookie_name="pwc_session",
    )
    assert cookie_request_passes_csrf(
        _request(origin="https://paperswithcode.co"), settings
    )
    assert not cookie_request_passes_csrf(_request(origin=None), settings)
    assert not cookie_request_passes_csrf(
        _request(origin="https://staging.paperswithcode.co"), settings
    )
    assert not cookie_request_passes_csrf(
        _request(origin="https://paperswithcode.co.attacker.example"), settings
    )
    assert not cookie_request_passes_csrf(
        _request(origin="https://www.paperswithcode.co"), settings
    )
    assert not cookie_request_passes_csrf(
        _request(origin="https://chat.paperswithcode.co"), settings
    )


def test_staging_accepts_only_staging_origin():
    settings = Settings(
        environment="staging",
        session_cookie_name="pwc_session",
    )
    assert cookie_request_passes_csrf(
        _request(origin="https://staging.paperswithcode.co"), settings
    )
    assert not cookie_request_passes_csrf(
        _request(origin="https://paperswithcode.co"), settings
    )


def test_non_cookie_and_valid_admin_header_paths_do_not_require_origin():
    settings = Settings(
        environment="production",
        session_cookie_name="pwc_session",
        admin_api_token="secret-token",
    )
    assert cookie_request_passes_csrf(_request(cookie=None, origin=None), settings)
    assert cookie_request_passes_csrf(
        _request(origin=None, admin_token="secret-token"), settings
    )
    assert not cookie_request_passes_csrf(
        _request(origin=None, admin_token="wrong-token"), settings
    )


def test_safe_methods_are_unaffected():
    settings = Settings(environment="production", session_cookie_name="pwc_session")
    assert cookie_request_passes_csrf(_request(method="GET", origin=None), settings)


def test_central_middleware_rejects_before_route_auth(monkeypatch):
    settings = Settings(environment="production", session_cookie_name="pwc_session")
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    from backend.main import create_app

    async def exercise():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport, base_url="https://paperswithcode.co"
        ) as client:
            response = await client.post(
                "/api/v1/me/paper-edits",
                cookies={"pwc_session": "invalid-session"},
                headers={"Origin": "https://staging.paperswithcode.co"},
                json={
                    "paper_id": 1,
                    "edit_type": "tasks",
                    "proposed_payload": {"task_ids": []},
                },
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "csrf_rejected"

    asyncio.run(exercise())


def test_staging_chat_initial_and_reconnect_origin_pass_central_csrf(monkeypatch):
    settings = Settings(
        environment="staging",
        session_cookie_name="pwc_session",
        chat_enabled=True,
    )
    monkeypatch.setattr("backend.main.get_settings", lambda: settings)
    from backend.main import create_app

    async def exercise():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport, base_url="https://staging.paperswithcode.co"
        ) as client:
            client.cookies.set("pwc_session", "invalid-session")
            for headers in (
                {"Origin": "https://staging.paperswithcode.co"},
                {
                    "Origin": "https://staging.paperswithcode.co",
                    "Last-Event-ID": "1",
                },
            ):
                response = await client.post(
                    "/api/v1/chat/stream",
                    headers=headers,
                    json={"message": "hello", "client_message_id": "scope-test"},
                )
                assert response.status_code == 401
                assert response.json() != {
                    "detail": {
                        "code": "csrf_rejected",
                        "message": (
                            "Unsafe cookie-authenticated requests must be same-origin"
                        ),
                    }
                }

    asyncio.run(exercise())


def test_qualification_scope_requires_staging_and_protected_admin_credential():
    from backend.routers.chat import _durable_qualification_scope

    scope_id = uuid.uuid4()

    headers = [
        (b"x-pwc-qualification-scope-id", str(scope_id).encode()),
        (b"x-pwc-qualification-workload", b"read"),
        (b"x-admin-token", b"a" * 32),
    ]
    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": headers}
    )
    staging = Settings(environment="staging", admin_api_token="a" * 32)
    assert _durable_qualification_scope(request, staging) == (scope_id, "read")
    with pytest.raises(HTTPException) as error:
        _durable_qualification_scope(
            request,
            staging.model_copy(update={"environment": "production"}),
        )
    assert error.value.status_code == 403
