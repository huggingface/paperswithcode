"""Request builders shared by chat endpoint tests."""

from __future__ import annotations

from starlette.requests import Request


def _cookie_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", b"pwc_session=test")],
        }
    )
