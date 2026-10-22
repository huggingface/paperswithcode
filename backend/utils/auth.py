"""Authentication helpers for protecting administrative endpoints.

Most admin endpoints accept either an HF OAuth session cookie or the legacy
``X-Admin-Token`` header for CLI/cron workflows. User-facing paper-page edits
on paper metadata use :func:`require_hf_admin` so only allowlisted HF accounts
can mutate them; evaluation CRUD uses :func:`require_admin` so scripts can
import rows with ``X-Admin-Token``.
"""

import hmac
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from backend.config import get_settings

admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)
Role = Literal["admin", "contributor"]


def role_for_hf_subject(
    hf_subject: object, *, username: object = None
) -> Optional[Role]:
    """Resolve current authorization from protected configuration.

    The username fallback is deliberately admin-only and applies only while
    the subject allowlist is empty. Contributor access is never name-based.
    """

    settings = get_settings()
    subject = hf_subject.strip() if isinstance(hf_subject, str) else ""
    if subject and subject in settings.admin_hf_subject_set:
        return "admin"
    if subject and subject in settings.contributor_hf_subject_set:
        return "contributor"
    if not settings.admin_hf_subject_set and isinstance(username, str):
        if username.strip().lower() in settings.admin_hf_username_set:
            return "admin"
    return None


def can_access_staging(hf_subject: object, *, username: object = None) -> bool:
    return role_for_hf_subject(hf_subject, username=username) is not None


def can_directly_edit_catalog(role: Optional[Role]) -> bool:
    settings = get_settings()
    if role == "admin":
        return settings.catalog_mutations_enabled and settings.is_production
    return (
        role == "contributor"
        and settings.is_production
        and settings.catalog_mutations_enabled
        and settings.contributor_direct_edits_enabled
    )


def _session_actor(request: Request) -> Optional[dict]:
    from backend.routers.auth import decode_request_session

    payload = decode_request_session(request)
    if not payload:
        return None
    subject = payload.get("sub")
    username = payload.get("username")
    if not isinstance(subject, str) or not subject.strip() or not username:
        return None
    role = role_for_hf_subject(subject, username=username)
    if role is None:
        return None
    actor = {
        "source": "cookie",
        "hf_subject": subject.strip(),
        "username": username,
        "role": role,
        "session_iat": payload.get("iat"),
    }
    qualification_owner = payload.get("chat_qualification_owner")
    if (
        role == "admin"
        and get_settings().environment == "staging"
        and isinstance(qualification_owner, str)
        and qualification_owner.startswith("operator:pi-qualification:")
        and len(qualification_owner) <= 128
    ):
        actor["chat_qualification_owner"] = qualification_owner
    return actor


def require_admin(
    request: Request,
    admin_token: Optional[str] = Depends(admin_token_header),
) -> dict:
    """Allow the request iff the caller is a configured admin.

    Cookie path is preferred; the ``X-Admin-Token`` header is a fallback for
    scripts and curl-driven workflows.  Returns a small dict describing the
    caller; raises 401 otherwise.
    """

    settings = get_settings()

    # 1) Session cookie set by the HF OAuth callback.

    actor = _session_actor(request)
    if actor and actor["role"] == "admin":
        return actor

    # 2) X-Admin-Token header fallback (CLI / cron tooling).
    if (
        settings.admin_api_token
        and admin_token
        and hmac.compare_digest(admin_token, settings.admin_api_token)
    ):
        return {
            "source": "header",
            "hf_subject": "admin-api-token",
            "username": None,
            "role": "admin",
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


def require_hf_admin(request: Request) -> dict:
    """Allow the request only for an allowlisted Hugging Face session."""

    actor = _session_actor(request)
    if actor and actor["role"] == "admin":
        return actor

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in with an authorized Hugging Face account to edit this paper",
    )


def require_contributor_role(request: Request) -> dict:
    """Allow a currently configured contributor or admin session."""
    actor = _session_actor(request)
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with an authorized Hugging Face account",
        )
    return actor


def require_contributor(request: Request) -> dict:
    """Require the role and the direct-edit capability for contributors."""

    actor = require_contributor_role(request)
    if actor["role"] == "contributor" and not can_directly_edit_catalog("contributor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "direct_catalog_edits_disabled",
                "message": "Direct contributor catalog edits are not enabled here",
            },
        )
    return actor


def require_catalog_mutator(
    request: Request,
    admin_token: Optional[str] = Depends(admin_token_header),
) -> dict:
    """Retain the configured contributor/admin boundary for shared catalog writes."""
    return _require_mutator(request, admin_token, paper_edit=False)


def require_paper_mutator(
    request: Request,
    admin_token: Optional[str] = Depends(admin_token_header),
) -> dict:
    """Authenticate paper editors; the mutation service enforces scope and quotas."""
    return _require_mutator(request, admin_token, paper_edit=True)


def _require_mutator(
    request: Request, admin_token: Optional[str], *, paper_edit: bool
) -> dict:
    authorization = request.headers.get("Authorization", "")
    if authorization:
        if not paper_edit:
            raise HTTPException(
                status_code=403,
                detail="Paper credentials cannot edit shared catalog definitions",
            )
        # Credentials scoped to papers never fall back to a broader cookie or
        # admin identity when invalid.
        from backend.database.connection import get_database_session
        from backend.services.paper_edit_access import PaperEditAccess

        if not authorization.startswith("Bearer ") or not can_directly_edit_catalog(
            "contributor"
        ):
            raise HTTPException(status_code=403, detail="Paper editing is unavailable")
        sessions = get_database_session()
        db = next(sessions)
        try:
            return PaperEditAccess(db).authenticate(authorization[7:])
        finally:
            sessions.close()
    actor = _session_actor(request)
    if paper_edit and actor is None and can_directly_edit_catalog("contributor"):
        from backend.routers.auth import decode_request_session

        payload = decode_request_session(request)
        if payload and payload.get("sub") and payload.get("username"):
            actor = {
                "source": "cookie",
                "hf_subject": payload["sub"],
                "username": payload["username"],
                "role": "contributor",
                "session_iat": payload.get("iat"),
            }
    if actor:
        if actor["role"] == "contributor" and not can_directly_edit_catalog(
            "contributor"
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "direct_catalog_edits_disabled",
                    "message": "Direct contributor catalog edits are not enabled here",
                },
            )
        return actor
    settings = get_settings()
    if (
        settings.admin_api_token
        and admin_token
        and hmac.compare_digest(admin_token, settings.admin_api_token)
    ):
        return {
            "source": "header",
            "hf_subject": "admin-api-token",
            "username": None,
            "role": "admin",
        }
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_fresh_contributor(request: Request) -> dict:
    actor = require_contributor(request)
    ensure_fresh_contributor_actor(actor)
    return actor


def require_fresh_catalog_mutator(
    actor: dict = Depends(require_catalog_mutator),
) -> dict:
    """Require a catalog mutator and step up destructive contributor actions."""

    if actor["role"] == "contributor":
        ensure_fresh_contributor_actor(actor)
    return actor


def ensure_fresh_contributor_actor(actor: dict) -> None:
    if actor["role"] == "admin" or actor.get("source") == "paper_token":
        return
    issued_at = actor.get("session_iat")
    now = datetime.now(timezone.utc).timestamp()
    if not isinstance(issued_at, (int, float)) or now - issued_at > 15 * 60:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "fresh_auth_required",
                "message": "Sign in again before deleting catalog data",
            },
        )


def catalog_mutation_context(
    request: Request,
    actor: dict = Depends(require_paper_mutator),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    expected_version: Optional[str] = Header(default=None, alias="If-Match"),
) -> dict:
    return {
        "actor": actor,
        "idempotency_key": idempotency_key,
        "expected_version": expected_version,
        "request_id": request.headers.get("X-Request-ID") or str(id(request)),
    }


def fresh_catalog_mutation_context(
    request: Request,
    actor: dict = Depends(require_catalog_mutator),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    expected_version: Optional[str] = Header(default=None, alias="If-Match"),
) -> dict:
    if actor["role"] == "contributor":
        ensure_fresh_contributor_actor(actor)
    return {
        "actor": actor,
        "idempotency_key": idempotency_key,
        "expected_version": expected_version,
        "request_id": request.headers.get("X-Request-ID") or str(id(request)),
    }


def evaluation_mutation_context(
    request: Request,
    actor: dict = Depends(require_paper_mutator),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    expected_version: Optional[str] = Header(default=None, alias="If-Match"),
) -> dict:
    if request.method == "DELETE" and actor["role"] == "contributor":
        ensure_fresh_contributor_actor(actor)
    return {
        "actor": actor,
        "idempotency_key": idempotency_key,
        "expected_version": expected_version,
        "request_id": request.headers.get("X-Request-ID") or str(id(request)),
    }


def has_session(request: Request) -> bool:
    """Whether the request carries a valid signed-in Hugging Face session."""

    from backend.routers.auth import decode_request_session

    payload = decode_request_session(request) or {}
    subject = payload.get("sub")
    return (
        bool(payload.get("username"))
        and isinstance(subject, str)
        and bool(subject.strip())
    )


def require_user(request: Request) -> dict:
    """Allow any signed-in HF user.

    Mirrors :func:`require_hf_admin` without the admin-allowlist check; used by
    user-scoped endpoints such as the bookmark API. Returns a small dict with
    the canonical HF ``username`` (lowercased) pulled from the session JWT.
    """

    from backend.routers.auth import decode_request_session

    payload = decode_request_session(request)
    username = (payload or {}).get("username")
    hf_user_id = (payload or {}).get("sub")
    if not username or not isinstance(hf_user_id, str) or not hf_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with Hugging Face to use this feature",
        )
    role = role_for_hf_subject(hf_user_id, username=username)
    actor = {
        "source": "cookie",
        "username": username.lower(),
        "hf_user_id": hf_user_id,
        "hf_subject": hf_user_id,
        "role": role,
        "can_directly_edit_catalog": can_directly_edit_catalog(role),
    }
    qualification_owner = (payload or {}).get("chat_qualification_owner")
    if (
        role == "admin"
        and get_settings().environment == "staging"
        and isinstance(qualification_owner, str)
        and qualification_owner.startswith("operator:pi-qualification:")
        and len(qualification_owner) <= 128
    ):
        actor["hf_user_id"] = qualification_owner
    return actor
