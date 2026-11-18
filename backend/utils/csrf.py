"""Central same-origin protection for cookie-authenticated unsafe requests."""

from __future__ import annotations

import hmac

from fastapi import Request

from backend.config import Settings

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Browsers post CSP violation reports without an Origin header, sometimes with
# cookies. The endpoint only appends to a log and never reads the session.
CSRF_EXEMPT_PATHS = frozenset({"/api/v1/csp-reports"})


def request_has_session_cookie(request: Request, settings: Settings) -> bool:
    names = {
        name
        for name in (
            settings.session_cookie_name,
            settings.shared_session_cookie_name,
        )
        if name
    }
    return any(name in request.cookies for name in names)


def has_valid_non_cookie_admin_credential(request: Request, settings: Settings) -> bool:
    supplied = request.headers.get("X-Admin-Token")
    return bool(
        supplied
        and settings.admin_api_token
        and hmac.compare_digest(supplied, settings.admin_api_token)
    )


def csrf_allowed_origins(settings: Settings) -> frozenset[str]:
    if settings.environment == "production":
        return frozenset({"https://paperswithcode.co"})
    if settings.environment == "staging":
        return frozenset({"https://staging.paperswithcode.co"})
    return frozenset(origin.rstrip("/") for origin in settings.allowed_origins)


def cookie_request_passes_csrf(request: Request, settings: Settings) -> bool:
    """Return whether a cookie-authenticated unsafe request is same-origin."""

    if request.method not in UNSAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
        return True
    if not request_has_session_cookie(request, settings):
        return True
    if has_valid_non_cookie_admin_credential(request, settings):
        return True
    origin = request.headers.get("Origin")
    return bool(origin and origin.rstrip("/") in csrf_allowed_origins(settings))
