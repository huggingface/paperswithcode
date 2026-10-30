"""
Hugging Face OAuth authentication for the PapersWithCode API.

Implements the "Sign in with Hugging Face" flow described at
https://huggingface.co/docs/hub/oauth :

  * `GET  /auth/hf/login`     — redirects the browser to HF authorize URL.
  * `GET  /auth/hf/callback`  — exchanges the auth code for an access token,
                                fetches the userinfo, sets a signed session
                                cookie and redirects back to `return_to`.
  * `POST /auth/logout`       — revokes the session and clears its cookies.
  * `GET  /auth/me`           — returns the signed-in user (or 401).
  * `GET  /auth/admin-check`  — 204/401/403 gate for nginx `auth_request`
                                (used to admin-lock staging.paperswithcode.co).

Production signs the shared session cookie with Ed25519. Staging has only the
public verification key, so it can consume production sessions without being
able to forge them. Environment-specific HS256 cookies remain readable during
the rollback window.

Every session production issues carries a server-side ``sid`` (see
``auth_session_service``); a token is accepted only while that session is live,
so logout also invalidates copies of the cookie taken earlier.
"""

from __future__ import annotations

import base64
import hmac
import secrets
import time
from typing import Literal, Optional
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.services import auth_session_service
from backend.services.hf_inference_billing_service import (
    OAUTH_COOKIE_NAME,
    HfInferenceCredential,
    encrypt_oauth_credential,
)
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    BUCKET_OAUTH_COOKIE_NAME,
)

router = APIRouter()


HF_AUTHORIZE_URL = "https://huggingface.co/oauth/authorize"
HF_TOKEN_URL = "https://huggingface.co/oauth/token"
HF_USERINFO_URL = "https://huggingface.co/oauth/userinfo"
HF_LOGIN_SCOPES = "openid profile"
HF_INFERENCE_SCOPES = f"{HF_LOGIN_SCOPES} inference-api"
HF_BUCKET_WRITE_SCOPES = f"{HF_LOGIN_SCOPES} write-repos"
HF_BUCKET_MANAGE_SCOPES = f"{HF_LOGIN_SCOPES} manage-repos"


def session_cookie_name() -> str:
    settings = get_settings()
    return settings.shared_session_cookie_name or settings.session_cookie_name


SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
STATE_TTL_SECONDS = 5 * 60  # 5 minutes
# Binds the OAuth state to the browser that started the login (login CSRF).
OAUTH_STATE_COOKIE_NAME = "pwc_oauth_state"
OAUTH_CALLBACK_PATH = "/api/v1/auth/hf/callback"
POSTHOG_SIGNUP_COOKIE_NAME = "pwc_posthog_signup"
POSTHOG_SIGNUP_COOKIE_MAX_AGE_SECONDS = 5 * 60


class AuthMe(BaseModel):
    hf_subject: str
    username: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool
    role: Optional[Literal["admin", "contributor"]] = None
    can_contribute: bool
    can_directly_edit_catalog: bool


def _origin_from_request(request: Request) -> str:
    """Best-effort origin (scheme + host) for the incoming request.

    Honours `X-Forwarded-Proto`/`Host` because we sit behind nginx in prod.
    """

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        host = request.url.netloc
    return f"{proto}://{host}"


def _redirect_uri(request: Request) -> str:
    """Compute the absolute redirect URI registered with the HF OAuth app."""

    return f"{_origin_from_request(request)}{OAUTH_CALLBACK_PATH}"


def _safe_return_to(value: Optional[str]) -> str:
    """Restrict ``return_to`` to local paths or explicitly trusted origins."""

    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if (
            parsed.scheme == "https"
            and origin in get_settings().auth_return_origin_set
            and parsed.path.startswith("/")
            and not parsed.username
            and not parsed.password
        ):
            return value
        return "/"
    # Browsers read "//host", "/\\host" and paths with stripped control
    # characters (e.g. "/\t/host") as another origin, so only plain
    # single-slash paths count as local.
    if (
        not value.startswith("/")
        or value[1:2] in ("/", "\\")
        or any(ord(char) < 0x20 or char == "\x7f" for char in value)
    ):
        return "/"
    return value


def _role(payload: dict) -> Optional[Literal["admin", "contributor"]]:
    from backend.utils.auth import role_for_hf_subject

    return role_for_hf_subject(payload.get("sub"), username=payload.get("username"))


def _is_admin(user: dict | str) -> bool:
    if isinstance(user, dict):
        return _role(user) == "admin"
    # Session encoding has a subject; retain this compatibility helper only for
    # legacy tests/callers that pass a username.
    settings = get_settings()
    return (
        not settings.admin_hf_subject_set
        and user.lower() in settings.admin_hf_username_set
    )


def _encode_state(
    return_to: str,
    host: str,
    *,
    nonce: str,
    authorize_inference: bool = False,
    authorize_bucket: bool = False,
    bucket_create: bool = False,
    collect_email: bool = False,
) -> str:
    settings = get_settings()
    payload = {
        "nonce": nonce,
        "host": host,
        "return_to": return_to,
        "authorize_inference": authorize_inference,
        "authorize_bucket": authorize_bucket,
        "bucket_create": bucket_create,
        "collect_email": collect_email,
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_state(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def _encode_session(user: dict, session_id: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sid": session_id,
        "sub": user["sub"],
        "username": user["username"],
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "email": user.get("email"),
        "email_verified": user.get("email_verified") is True,
        "is_admin": _is_admin(user),
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
    }
    if settings.session_signing_private_key:
        payload["iss"] = settings.auth_authority_origin.rstrip("/")
        payload["aud"] = "paperswithcode"
        return jwt.encode(
            payload,
            _private_key(settings.session_signing_private_key),
            algorithm="EdDSA",
        )
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _encode_legacy_session(user: dict, session_id: Optional[str] = None) -> str:
    settings = get_settings()
    return encode_qualification_session(
        user, settings, is_admin=_is_admin(user), session_id=session_id
    )


def encode_qualification_session(
    user: dict,
    settings: Settings,
    *,
    is_admin: bool = False,
    session_id: Optional[str] = None,
) -> str:
    """Encode the staging qualification cookie with explicitly supplied keys.

    Without ``session_id`` the cookie is accepted only by staging, as its own
    operator qualification identity.
    """
    payload = {
        "sub": user["sub"],
        "username": user["username"],
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "is_admin": is_admin,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    if session_id is not None:
        payload["sid"] = session_id
    qualification_owner = user.get("chat_qualification_owner")
    if (
        settings.environment == "staging"
        and isinstance(qualification_owner, str)
        and qualification_owner.startswith("operator:pi-qualification:")
        and len(qualification_owner) <= 128
    ):
        payload["chat_qualification_owner"] = qualification_owner
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_key(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _private_key(value: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_decode_key(value))


def _public_key(value: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_decode_key(value))


def _decode_shared_session(token: str) -> Optional[dict]:
    settings = get_settings()
    if not token or not settings.session_verification_public_key:
        return None
    try:
        return jwt.decode(
            token,
            _public_key(settings.session_verification_public_key),
            algorithms=["EdDSA"],
            audience="paperswithcode",
            issuer=settings.auth_authority_origin.rstrip("/"),
        )
    except (jwt.PyJWTError, ValueError):
        return None


def decode_session_cookie(token: str) -> Optional[dict]:
    """Decode a legacy environment-specific HS256 session JWT."""

    settings = get_settings()
    if not settings.jwt_secret:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _decode_presented_sessions(request: Request) -> list[tuple[dict, bool]]:
    """Signature-valid session payloads, shared first, with whether each is
    staging's own legacy cookie (the only kind allowed to lack a ``sid``)."""

    settings = get_settings()
    payloads: list[tuple[dict, bool]] = []
    if settings.shared_session_cookie_name:
        shared = request.cookies.get(settings.shared_session_cookie_name)
        payload = _decode_shared_session(shared) if shared else None
        if payload:
            payloads.append((payload, False))
    legacy = request.cookies.get(settings.session_cookie_name)
    payload = decode_session_cookie(legacy) if legacy else None
    if payload:
        payloads.append((payload, settings.environment == "staging"))
    return payloads


def _session_is_live(payload: dict, staging_local: bool) -> bool:
    session_id = payload.get("sid")
    if session_id is None:
        return staging_local
    if not isinstance(session_id, str):
        return False
    from backend.database.connection import db_manager

    with db_manager.session_local() as db:
        return auth_session_service.session_is_active(
            db, session_id, payload.get("sub")
        )


def decode_request_session(request: Request) -> Optional[dict]:
    """Prefer the shared session, then accept the local legacy cookie.

    Only a session whose server-side ``sid`` is still live counts. The result is
    memoised on the request, which several dependencies decode.
    """

    if not hasattr(request.state, "pwc_session"):
        request.state.pwc_session = next(
            (
                payload
                for payload, staging_local in _decode_presented_sessions(request)
                if _session_is_live(payload, staging_local)
            ),
            None,
        )
    return request.state.pwc_session


def _cookie_domain() -> Optional[str]:
    """Domain attribute for the session cookie (None = host-only).

    `PWC_SESSION_COOKIE_DOMAIN=.paperswithcode.co` widens the session to
    subdomains so an ordinary production sign-in also authenticates
    staging.paperswithcode.co — needed because only the production callback
    URL is registered with the HF OAuth app.
    """

    return get_settings().session_cookie_domain.strip() or None


def _shared_cookie_domain() -> Optional[str]:
    return get_settings().shared_session_cookie_domain.strip() or None


def _set_session_cookie(response: Response, token: str, secure: bool) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.shared_session_cookie_name or settings.session_cookie_name,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=(
            _shared_cookie_domain()
            if settings.shared_session_cookie_name
            else _cookie_domain()
        ),
    )


def _clear_session_cookie(response: Response, secure: bool) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    domain = _cookie_domain()
    if domain:
        response.delete_cookie(
            session_cookie_name(),
            path="/",
            httponly=True,
            secure=secure,
            samesite="lax",
            domain=domain,
        )
    if settings.shared_session_cookie_name:
        response.delete_cookie(
            settings.shared_session_cookie_name,
            path="/",
            httponly=True,
            secure=secure,
            samesite="lax",
            domain=_shared_cookie_domain(),
        )
    response.delete_cookie(
        OAUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=_shared_cookie_domain(),
    )


def _is_secure_origin(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def _set_oauth_state_cookie(response: Response, nonce: str, secure: bool) -> None:
    # Host-only: the login handler and the callback share the redirect URI's
    # origin (staging forwards logins to the auth authority first).
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        nonce,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=OAUTH_CALLBACK_PATH,
    )


def _clear_oauth_state_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        OAUTH_STATE_COOKIE_NAME,
        path=OAUTH_CALLBACK_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def _oauth_cookie_max_age(token_payload: dict) -> int:
    expires_in = token_payload.get("expires_in")
    if isinstance(expires_in, bool):
        return SESSION_TTL_SECONDS
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        return SESSION_TTL_SECONDS
    return min(seconds, SESSION_TTL_SECONDS) if seconds > 0 else SESSION_TTL_SECONDS


@router.get("/auth/hf/login")
def hf_login(
    request: Request,
    return_to: Optional[str] = Query(default=None),
    authorize_inference: bool = False,
    authorize_bucket: bool = False,
    bucket_create: bool = False,
    collect_email: bool = False,
):
    """Kick off the HF OAuth authorization-code flow."""

    settings = get_settings()
    safe_return = _safe_return_to(return_to)
    authority = settings.auth_authority_origin.rstrip("/")
    request_origin = _origin_from_request(request).rstrip("/")
    if authority and request_origin != authority:
        if safe_return.startswith("/"):
            authority_return = f"{request_origin}{safe_return}"
        elif safe_return.startswith(f"{request_origin}/"):
            authority_return = safe_return
        else:
            authority_return = f"{request_origin}/"
        authority_query = urlencode(
            {
                "return_to": authority_return,
                "authorize_inference": authorize_inference,
                "authorize_bucket": authorize_bucket,
                "bucket_create": bucket_create,
                "collect_email": collect_email,
            }
        )
        return RedirectResponse(
            url=f"{authority}/api/v1/auth/hf/login?{authority_query}",
            status_code=status.HTTP_302_FOUND,
        )
    if not settings.hf_oauth_client_id or not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hugging Face OAuth is not configured on this server",
        )

    nonce = secrets.token_urlsafe(16)
    state = _encode_state(
        safe_return,
        request.headers.get("host", ""),
        nonce=nonce,
        authorize_inference=authorize_inference,
        authorize_bucket=authorize_bucket,
        bucket_create=bucket_create,
        collect_email=collect_email,
    )
    scope = (
        HF_INFERENCE_SCOPES
        if authorize_inference
        else HF_BUCKET_MANAGE_SCOPES
        if authorize_bucket and bucket_create
        else HF_BUCKET_WRITE_SCOPES
        if authorize_bucket
        else HF_LOGIN_SCOPES
    )
    if collect_email:
        scope = f"{scope} email"
    params = {
        "client_id": settings.hf_oauth_client_id,
        "redirect_uri": _redirect_uri(request),
        "scope": scope,
        "response_type": "code",
        "state": state,
    }
    response = RedirectResponse(
        url=f"{HF_AUTHORIZE_URL}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )
    _set_oauth_state_cookie(response, nonce, secure=_is_secure_origin(request))
    return response


@router.get("/auth/hf/callback")
async def hf_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Complete the OAuth flow: trade the code for a token, set cookie.

    The single-use state cookie is cleared whether the callback succeeds or not.
    """

    secure = _is_secure_origin(request)
    try:
        response = await _complete_hf_callback(request, code, state, error)
    except HTTPException as exc:
        cleared = Response()
        _clear_oauth_state_cookie(cleared, secure)
        exc.headers = {
            **(exc.headers or {}),
            "set-cookie": cleared.headers["set-cookie"],
        }
        raise
    _clear_oauth_state_cookie(response, secure)
    return response


async def _complete_hf_callback(
    request: Request,
    code: Optional[str],
    state: Optional[str],
    error: Optional[str],
) -> Response:
    settings = get_settings()
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hugging Face returned an error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state",
        )
    if not settings.hf_oauth_client_id or not settings.hf_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hugging Face OAuth is not configured on this server",
        )

    try:
        state_payload = _decode_state(state)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        ) from exc

    expected_host = state_payload.get("host")
    actual_host = request.headers.get("host", "")
    if expected_host and expected_host != actual_host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state host mismatch",
        )
    browser_nonce = request.cookies.get(OAUTH_STATE_COOKIE_NAME, "")
    state_nonce = state_payload.get("nonce")
    if (
        not browser_nonce
        or not isinstance(state_nonce, str)
        or not hmac.compare_digest(browser_nonce.encode(), state_nonce.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state does not belong to this browser; sign in again",
        )

    return_to = _safe_return_to(state_payload.get("return_to"))

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            HF_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
            },
            auth=(settings.hf_oauth_client_id, settings.hf_oauth_client_secret),
            headers={"Accept": "application/json"},
        )
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {token_response.text}",
            )
        token_payload = token_response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hugging Face did not return an access token",
            )

        userinfo_response = await client.get(
            HF_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch HF userinfo: {userinfo_response.text}",
            )
        userinfo = userinfo_response.json()

    username = userinfo.get("preferred_username") or userinfo.get("name")
    hf_user_id = userinfo.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HF userinfo did not include a username",
        )
    if not isinstance(hf_user_id, str) or not hf_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HF userinfo did not include an immutable account subject",
        )

    email = userinfo.get("email")
    email_verified = userinfo.get("email_verified") is True
    if state_payload.get("collect_email") and (
        not isinstance(email, str)
        or not email.strip()
        or len(email.strip()) > 320
        or not email_verified
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hugging Face did not provide a verified email address",
        )

    user = {
        "sub": hf_user_id,
        "username": username,
        "name": userinfo.get("name"),
        "avatar_url": userinfo.get("picture"),
        "email": email.strip() if state_payload.get("collect_email") else None,
        "email_verified": email_verified and state_payload.get("collect_email") is True,
    }
    from backend.database.connection import db_manager
    from backend.models.database import UserProfile
    from backend.services.user_profile_service import UserProfileService

    with db_manager.session_local() as profile_db:
        is_new_profile = profile_db.get(UserProfile, hf_user_id) is None
        UserProfileService(profile_db).upsert_verified_identity(hf_user_id, username)
        session_id = auth_session_service.create_session(
            profile_db, hf_user_id, ttl_seconds=SESSION_TTL_SECONDS
        )
    session_token = _encode_session(user, session_id)

    response = RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, session_token, secure=_is_secure_origin(request))
    if is_new_profile:
        response.set_cookie(
            POSTHOG_SIGNUP_COOKIE_NAME,
            "1",
            max_age=POSTHOG_SIGNUP_COOKIE_MAX_AGE_SECONDS,
            httponly=False,
            secure=_is_secure_origin(request),
            samesite="lax",
            path="/",
            domain=_shared_cookie_domain(),
        )
    if state_payload.get("authorize_inference") and settings.hf_oauth_credential_secret:
        response.set_cookie(
            OAUTH_COOKIE_NAME,
            encrypt_oauth_credential(
                HfInferenceCredential(access_token), hf_user_id, settings
            ),
            max_age=_oauth_cookie_max_age(token_payload),
            httponly=True,
            secure=_is_secure_origin(request),
            samesite="lax",
            path="/",
            domain=_shared_cookie_domain(),
        )
    if state_payload.get("authorize_bucket") and settings.hf_oauth_credential_secret:
        response.set_cookie(
            (
                BUCKET_MANAGE_OAUTH_COOKIE_NAME
                if state_payload.get("bucket_create")
                else BUCKET_OAUTH_COOKIE_NAME
            ),
            encrypt_oauth_credential(
                HfInferenceCredential(access_token), hf_user_id, settings
            ),
            max_age=_oauth_cookie_max_age(token_payload),
            httponly=True,
            secure=_is_secure_origin(request),
            samesite="lax",
            path="/",
            domain=_shared_cookie_domain(),
        )
    if settings.session_signing_private_key:
        response.set_cookie(
            settings.session_cookie_name,
            _encode_legacy_session(user, session_id),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=_is_secure_origin(request),
            samesite="lax",
            path="/",
            domain=_cookie_domain(),
        )
    return response


def _revoke_presented_sessions(request: Request, everywhere: bool) -> None:
    """Revoke every session the request's cookies name.

    Staging can only read production's sessions; its logout goes through the
    production authority (``VITE_AUTH_URL``), which revokes them.
    """

    if get_settings().environment == "staging":
        return
    from backend.database.connection import db_manager

    live = decode_request_session(request)
    session_ids = {
        payload["sid"]
        for payload, _staging_local in _decode_presented_sessions(request)
        if isinstance(payload.get("sid"), str)
    }
    with db_manager.session_local() as db:
        if everywhere and live and isinstance(live.get("sub"), str):
            auth_session_service.revoke_all_sessions(db, live["sub"])
        else:
            auth_session_service.revoke_sessions(db, session_ids)


@router.post("/auth/logout")
def logout(
    request: Request,
    return_to: Optional[str] = Query(default=None),
    everywhere: bool = Query(default=False),
):
    """Revoke this session (or, with ``everywhere``, all of the user's
    sessions) and clear the cookies this origin can delete."""

    _revoke_presented_sessions(request, everywhere)
    safe_return = _safe_return_to(return_to)
    response: Response
    if return_to and safe_return != "/":
        response = RedirectResponse(
            url=safe_return,
            status_code=status.HTTP_303_SEE_OTHER,
        )
    else:
        response = JSONResponse({"ok": True})
    _clear_session_cookie(response, secure=_is_secure_origin(request))
    return response


@router.get("/auth/admin-check", status_code=status.HTTP_204_NO_CONTENT)
def admin_check(request: Request) -> Response:
    """Cheap server-side gate for nginx ``auth_request`` (staging admin lock).

    Returns 204 for an allowlisted HF admin session, 401 when there is no
    valid session, and 403 for a signed-in non-admin. nginx maps 401 to the
    HF sign-in redirect and 403 to a plain refusal page — distinguishing the
    two prevents a redirect loop for signed-in non-admins.
    """

    payload = decode_request_session(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if not _is_admin(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/staging-check", status_code=status.HTTP_204_NO_CONTENT)
def staging_check(request: Request) -> Response:
    """Admission check for staging; endpoint authorization remains separate."""

    from backend.utils.auth import can_access_staging

    payload = decode_request_session(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    qualification_owner = payload.get("chat_qualification_owner")
    qualification_identity = (
        isinstance(qualification_owner, str)
        and qualification_owner.startswith("operator:pi-qualification:")
        and len(qualification_owner) <= 128
        and payload.get("sub") == qualification_owner
        and payload.get("username") == qualification_owner
    )
    if not qualification_identity and not can_access_staging(
        payload.get("sub"), username=payload.get("username")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staging access required",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=AuthMe)
def me(request: Request):
    payload = decode_request_session(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    from backend.utils.auth import can_directly_edit_catalog

    role = _role(payload)
    return AuthMe(
        hf_subject=payload["sub"],
        username=payload["username"],
        name=payload.get("name"),
        avatar_url=payload.get("avatar_url"),
        is_admin=role == "admin",
        role=role,
        can_contribute=role in {"admin", "contributor"},
        can_directly_edit_catalog=can_directly_edit_catalog(role or "contributor"),
    )
