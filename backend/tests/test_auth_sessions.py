from __future__ import annotations

import asyncio
import base64
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request

from backend.config import Settings
from backend.routers import auth
from backend.services import hf_inference_billing_service as billing
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    BUCKET_OAUTH_COOKIE_NAME,
)
from backend.services.user_profile_service import UserProfileService

_REAL_UPSERT_VERIFIED_IDENTITY = UserProfileService.upsert_verified_identity


@pytest.fixture(autouse=True)
def _no_profile_database(monkeypatch):
    """Callbacks upsert the HF identity; keep these tests off PostgreSQL."""

    from backend.database.connection import db_manager
    from backend.services.user_profile_service import UserProfileService

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(db_manager, "_session_local", FakeSession)
    monkeypatch.setattr(
        UserProfileService, "upsert_verified_identity", lambda *_args: None
    )


def _key_values() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    private_value = base64.urlsafe_b64encode(b"\x02" * 32).rstrip(b"=").decode()
    public_value = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        .rstrip(b"=")
        .decode()
    )
    return private_value, public_value


def _settings(*, production: bool) -> Settings:
    private_value, public_value = _key_values()
    return Settings(
        environment="production" if production else "staging",
        jwt_secret="production-legacy" if production else "staging-legacy",
        session_cookie_name="pwc_session" if production else "pwc_staging_session",
        shared_session_cookie_name="pwc_shared_session",
        shared_session_cookie_domain=".paperswithcode.co",
        session_signing_private_key=private_value if production else "",
        session_verification_public_key=public_value,
        auth_authority_origin="https://paperswithcode.co",
        auth_return_origins=(
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        admin_hf_usernames="alice",
        hf_oauth_client_id="client",
        hf_oauth_client_secret="client-secret",
        hf_oauth_credential_secret="shared-oauth-secret",
    )


def _request(host: str, cookie: str = "") -> Request:
    headers = [(b"host", host.encode()), (b"x-forwarded-proto", b"https")]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": "http",
            "headers": headers,
        }
    )


def test_production_session_is_verified_on_staging(monkeypatch, auth_sessions):
    current = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: current)
    token = auth._encode_session(
        {"sub": "hf-123", "username": "Alice", "name": "Alice"},
        auth_sessions.issue("hf-123"),
    )

    current = _settings(production=False)
    payload = auth.decode_request_session(
        _request("staging.paperswithcode.co", f"pwc_shared_session={token}")
    )

    assert payload is not None
    assert payload["sub"] == "hf-123"
    assert payload["username"] == "Alice"


def test_verified_email_survives_shared_session_round_trip(monkeypatch, auth_sessions):
    current = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: current)
    token = auth._encode_session(
        {
            "sub": "hf-123",
            "username": "Alice",
            "email": "alice@example.com",
            "email_verified": True,
        },
        auth_sessions.issue("hf-123"),
    )

    current = _settings(production=False)
    payload = auth.decode_request_session(
        _request("staging.paperswithcode.co", f"pwc_shared_session={token}")
    )

    assert payload is not None
    assert payload["email"] == "alice@example.com"
    assert payload["email_verified"] is True


def test_staging_legacy_token_cannot_impersonate_shared_session(monkeypatch):
    settings = _settings(production=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    token = jwt.encode(
        {"sub": "forged", "username": "Alice"},
        settings.jwt_secret,
        algorithm="HS256",
    )

    assert (
        auth.decode_request_session(
            _request("staging.paperswithcode.co", f"pwc_shared_session={token}")
        )
        is None
    )


def test_staging_login_redirects_to_production_authority(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))

    response = auth.hf_login(
        _request("staging.paperswithcode.co"),
        return_to="/chat?paper=123",
        authorize_inference=True,
    )

    location = response.headers["location"]
    parsed = urlparse(location)
    assert f"{parsed.scheme}://{parsed.netloc}" == "https://paperswithcode.co"
    assert parsed.path == "/api/v1/auth/hf/login"
    assert parse_qs(parsed.query)["return_to"] == [
        "https://staging.paperswithcode.co/chat?paper=123"
    ]
    assert parse_qs(parsed.query)["authorize_inference"] == ["True"]


def test_production_login_requests_only_profile_scope_by_default(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(_request("paperswithcode.co"), return_to="/settings")

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["openid profile"]


def test_access_request_login_explicitly_requests_email_scope(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(
        _request("paperswithcode.co"),
        return_to="https://staging.paperswithcode.co/request-access",
        collect_email=True,
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["openid profile email"]
    state = auth._decode_state(query["state"][0])
    assert state["collect_email"] is True


def test_staging_email_request_is_forwarded_to_auth_authority(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))

    response = auth.hf_login(
        _request("staging.paperswithcode.co"),
        return_to="/request-access",
        collect_email=True,
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["collect_email"] == ["True"]


def test_production_inference_authorization_requests_inference_scope(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(
        _request("paperswithcode.co"),
        return_to="/chat",
        authorize_inference=True,
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["openid profile inference-api"]


def test_production_bucket_authorization_requests_write_scope(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(
        _request("paperswithcode.co"),
        return_to="/paper/2601.00001",
        authorize_bucket=True,
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["openid profile write-repos"]


def test_production_new_bucket_authorization_requests_manage_scope(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(
        _request("paperswithcode.co"),
        return_to="/paper/2601.00001",
        authorize_bucket=True,
        bucket_create=True,
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == ["openid profile manage-repos"]


def test_oauth_callback_keeps_new_profile_uncommitted_when_session_fails(
    monkeypatch,
):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.database.connection import db_manager
    from backend.models.database import UserProfile, UserProfileAlias

    engine = create_engine("sqlite://")
    UserProfile.__table__.create(engine)
    UserProfileAlias.__table__.create(engine)
    session_local = sessionmaker(bind=engine)
    monkeypatch.setattr(db_manager, "_session_local", session_local)
    monkeypatch.setattr(
        UserProfileService, "upsert_verified_identity", _REAL_UPSERT_VERIFIED_IDENTITY
    )

    def fail_create_session(*_args, **_kwargs):
        raise RuntimeError("session insert failed")

    monkeypatch.setattr(
        auth.auth_session_service, "create_session", fail_create_session
    )
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return httpx.Response(200, json={"access_token": "access"})

        async def get(self, _url, **_kwargs):
            return httpx.Response(
                200, json={"sub": "hf-new", "preferred_username": "newcomer"}
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    state = auth._encode_state("/", "paperswithcode.co", nonce="browser-nonce")

    with pytest.raises(RuntimeError, match="session insert failed"):
        asyncio.run(
            auth.hf_callback(
                _request("paperswithcode.co", "pwc_oauth_state=browser-nonce"),
                code="authorization-code",
                state=state,
                error=None,
            )
        )

    with session_local() as db:
        assert db.get(UserProfile, "hf-new") is None


def test_oauth_callback_sets_encrypted_bucket_cookie(monkeypatch):
    settings = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **_kwargs):
            assert url == auth.HF_TOKEN_URL
            return httpx.Response(
                200,
                json={"access_token": "bucket-oauth-access", "expires_in": 3600},
            )

        async def get(self, url, **_kwargs):
            assert url == auth.HF_USERINFO_URL
            return httpx.Response(
                200,
                json={"sub": "hf-123", "preferred_username": "alice"},
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    state = auth._encode_state(
        "/paper/2601.00001",
        "paperswithcode.co",
        nonce="browser-nonce",
        authorize_bucket=True,
    )

    response = asyncio.run(
        auth.hf_callback(
            _request("paperswithcode.co", "pwc_oauth_state=browser-nonce"),
            code="authorization-code",
            state=state,
            error=None,
        )
    )

    cookie_headers = [
        header
        for header in response.headers.getlist("set-cookie")
        if header.startswith(f"{BUCKET_OAUTH_COOKIE_NAME}=")
    ]
    assert len(cookie_headers) == 1
    cookies = SimpleCookie()
    cookies.load(cookie_headers[0])
    assert billing.decrypt_oauth_credential(
        cookies[BUCKET_OAUTH_COOKIE_NAME].value, "hf-123", settings
    ) == billing.HfInferenceCredential("bucket-oauth-access")


def test_new_bucket_authorization_sets_manage_cookie(monkeypatch):
    settings = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return httpx.Response(200, json={"access_token": "manage-access"})

        async def get(self, _url, **_kwargs):
            return httpx.Response(
                200, json={"sub": "hf-123", "preferred_username": "alice"}
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    state = auth._encode_state(
        "/paper/2601.00001",
        "paperswithcode.co",
        nonce="browser-nonce",
        authorize_bucket=True,
        bucket_create=True,
    )

    response = asyncio.run(
        auth.hf_callback(
            _request("paperswithcode.co", "pwc_oauth_state=browser-nonce"),
            code="authorization-code",
            state=state,
            error=None,
        )
    )

    assert any(
        header.startswith(f"{BUCKET_MANAGE_OAUTH_COOKIE_NAME}=")
        for header in response.headers.getlist("set-cookie")
    )


@pytest.mark.parametrize("authorize_inference", [False, True])
def test_oauth_callback_sets_inference_cookie_only_for_inference_authorization(
    monkeypatch,
    authorize_inference,
):
    settings = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **_kwargs):
            assert url == auth.HF_TOKEN_URL
            return httpx.Response(
                200,
                json={"access_token": "oauth-access", "expires_in": 3600},
            )

        async def get(self, url, **_kwargs):
            assert url == auth.HF_USERINFO_URL
            return httpx.Response(
                200,
                json={
                    "sub": "hf-123",
                    "preferred_username": "alice",
                    "name": "Alice",
                },
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    state = auth._encode_state(
        "/settings",
        "paperswithcode.co",
        nonce="browser-nonce",
        authorize_inference=authorize_inference,
    )

    response = asyncio.run(
        auth.hf_callback(
            _request("paperswithcode.co", "pwc_oauth_state=browser-nonce"),
            code="authorization-code",
            state=state,
            error=None,
        )
    )

    oauth_headers = [
        header
        for header in response.headers.getlist("set-cookie")
        if header.startswith(f"{billing.OAUTH_COOKIE_NAME}=")
    ]
    if not authorize_inference:
        assert oauth_headers == []
        return

    oauth_cookie_header = oauth_headers[0]
    cookies = SimpleCookie()
    cookies.load(oauth_cookie_header)
    oauth_cookie = cookies[billing.OAUTH_COOKIE_NAME]
    assert oauth_cookie["domain"] == ".paperswithcode.co"
    assert oauth_cookie["httponly"] is True
    assert oauth_cookie["max-age"] == "3600"
    assert billing.decrypt_oauth_credential(
        oauth_cookie.value, "hf-123", settings
    ) == billing.HfInferenceCredential("oauth-access")


def test_absolute_return_destinations_are_allowlisted(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    assert (
        auth._safe_return_to("https://staging.paperswithcode.co/chat")
        == "https://staging.paperswithcode.co/chat"
    )
    assert auth._safe_return_to("https://evil.example/chat") == "/"


def test_local_return_destinations_reject_other_origins():
    for value in (
        "//evil.example",
        "///evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "/\n/evil.example",
    ):
        assert auth._safe_return_to(value) == "/", value
    assert auth._safe_return_to("/paper/2601.00001?tab=code") == (
        "/paper/2601.00001?tab=code"
    )


class _LoginClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, **_kwargs):
        assert url == auth.HF_TOKEN_URL
        return httpx.Response(200, json={"access_token": "login-access"})

    async def get(self, url, **_kwargs):
        assert url == auth.HF_USERINFO_URL
        return httpx.Response(
            200, json={"sub": "hf-123", "preferred_username": "alice"}
        )


class _ExchangeForbidden:
    def __init__(self, **_kwargs):
        raise AssertionError("code must not be exchanged without a bound browser")


def _state_cookie(response) -> SimpleCookie:
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        if header.startswith(f"{auth.OAUTH_STATE_COOKIE_NAME}="):
            cookies.load(header)
    return cookies


def test_login_binds_state_nonce_to_a_callback_scoped_cookie(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))

    response = auth.hf_login(_request("paperswithcode.co"), return_to="/settings")

    query = parse_qs(urlparse(response.headers["location"]).query)
    state = auth._decode_state(query["state"][0])
    cookie = _state_cookie(response)[auth.OAUTH_STATE_COOKIE_NAME]
    assert cookie.value == state["nonce"]
    assert cookie["path"] == "/api/v1/auth/hf/callback"
    assert cookie["max-age"] == str(auth.STATE_TTL_SECONDS)
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"] == "lax"
    assert cookie["domain"] == ""


def test_staging_login_sets_state_cookie_only_on_auth_authority(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))
    staging = auth.hf_login(_request("staging.paperswithcode.co"), return_to="/")
    assert not _state_cookie(staging)

    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))
    authority = auth.hf_login(
        _request("paperswithcode.co"),
        return_to=parse_qs(urlparse(staging.headers["location"]).query)["return_to"][0],
    )
    assert auth.OAUTH_STATE_COOKIE_NAME in _state_cookie(authority)


@pytest.mark.parametrize("cookie", ["", "pwc_oauth_state=attacker-nonce"])
def test_callback_rejects_state_not_bound_to_this_browser(monkeypatch, cookie):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))
    monkeypatch.setattr(auth.httpx, "AsyncClient", _ExchangeForbidden)
    state = auth._encode_state("/", "paperswithcode.co", nonce="victim-nonce")

    with pytest.raises(auth.HTTPException) as exc_info:
        asyncio.run(
            auth.hf_callback(
                _request("paperswithcode.co", cookie),
                code="attacker-code",
                state=state,
                error=None,
            )
        )

    assert exc_info.value.status_code == 400
    cleared = SimpleCookie()
    cleared.load(exc_info.value.headers["set-cookie"])
    assert cleared[auth.OAUTH_STATE_COOKIE_NAME]["max-age"] == "0"
    assert cleared[auth.OAUTH_STATE_COOKIE_NAME]["path"] == "/api/v1/auth/hf/callback"


def test_callback_accepts_matching_browser_and_preserves_return_to(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=True))
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: _LoginClient())
    login = auth.hf_login(
        _request("paperswithcode.co"),
        return_to="https://staging.paperswithcode.co/chat?paper=123",
    )
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    nonce = _state_cookie(login)[auth.OAUTH_STATE_COOKIE_NAME].value

    response = asyncio.run(
        auth.hf_callback(
            _request("paperswithcode.co", f"pwc_oauth_state={nonce}"),
            code="authorization-code",
            state=state,
            error=None,
        )
    )

    assert response.headers["location"] == (
        "https://staging.paperswithcode.co/chat?paper=123"
    )
    assert any(
        header.startswith("pwc_shared_session=")
        for header in response.headers.getlist("set-cookie")
    )
    assert _state_cookie(response)[auth.OAUTH_STATE_COOKIE_NAME]["max-age"] == "0"


def _sign_in(monkeypatch, settings: Settings) -> dict[str, str]:
    """Complete a production OAuth callback and return the cookies it set."""

    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return httpx.Response(200, json={"access_token": "access"})

        async def get(self, _url, **_kwargs):
            return httpx.Response(
                200, json={"sub": "hf-123", "preferred_username": "alice"}
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    state = auth._encode_state("/", "paperswithcode.co", nonce="browser-nonce")
    response = asyncio.run(
        auth.hf_callback(
            _request("paperswithcode.co", "pwc_oauth_state=browser-nonce"),
            code="authorization-code",
            state=state,
            error=None,
        )
    )
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        cookies.load(header)
    return {name: morsel.value for name, morsel in cookies.items()}


def _cookie_header(cookies: dict[str, str], *names: str) -> str:
    return "; ".join(f"{name}={cookies[name]}" for name in names)


def test_sign_in_binds_shared_and_legacy_cookies_to_one_live_session(
    monkeypatch, auth_sessions
):
    cookies = _sign_in(monkeypatch, _settings(production=True))

    shared = jwt.decode(
        cookies["pwc_shared_session"], options={"verify_signature": False}
    )
    legacy = jwt.decode(cookies["pwc_session"], options={"verify_signature": False})
    assert shared["sid"] == legacy["sid"]
    assert auth_sessions.subjects == {shared["sid"]: "hf-123"}


def test_copied_cookies_are_rejected_after_logout(monkeypatch, auth_sessions):
    cookies = _sign_in(monkeypatch, _settings(production=True))
    copied = _cookie_header(cookies, "pwc_shared_session", "pwc_session")
    assert auth.decode_request_session(_request("paperswithcode.co", copied))

    auth.logout(_request("paperswithcode.co", copied), return_to=None, everywhere=False)

    assert auth.decode_request_session(_request("paperswithcode.co", copied)) is None
    # The host-only production legacy cookie a staging logout cannot delete is
    # revoked with the shared one.
    residual = _cookie_header(cookies, "pwc_session")
    assert auth.decode_request_session(_request("paperswithcode.co", residual)) is None


def test_revoked_production_session_is_rejected_on_staging(monkeypatch, auth_sessions):
    production = _settings(production=True)
    cookies = _sign_in(monkeypatch, production)
    shared = _cookie_header(cookies, "pwc_shared_session")
    auth.logout(_request("paperswithcode.co", shared), return_to=None, everywhere=False)

    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))

    assert (
        auth.decode_request_session(_request("staging.paperswithcode.co", shared))
        is None
    )


def test_logout_everywhere_revokes_every_session_of_the_user(
    monkeypatch, auth_sessions
):
    settings = _settings(production=True)
    laptop = _sign_in(monkeypatch, settings)
    phone = _sign_in(monkeypatch, settings)

    auth.logout(
        _request("paperswithcode.co", _cookie_header(laptop, "pwc_shared_session")),
        return_to=None,
        everywhere=True,
    )

    assert (
        auth.decode_request_session(
            _request("paperswithcode.co", _cookie_header(phone, "pwc_shared_session"))
        )
        is None
    )


def test_logout_revokes_only_its_own_session(monkeypatch, auth_sessions):
    settings = _settings(production=True)
    laptop = _sign_in(monkeypatch, settings)
    phone = _sign_in(monkeypatch, settings)

    auth.logout(
        _request("paperswithcode.co", _cookie_header(laptop, "pwc_shared_session")),
        return_to=None,
        everywhere=False,
    )

    assert auth.decode_request_session(
        _request("paperswithcode.co", _cookie_header(phone, "pwc_shared_session"))
    )


@pytest.mark.parametrize("production", [True, False])
def test_session_without_a_server_side_id_is_rejected(monkeypatch, production):
    """Tokens minted before revocation existed cannot be revoked, so they no
    longer authenticate; their holders sign in again."""

    issuing = _settings(production=True)
    monkeypatch.setattr(auth, "get_settings", lambda: issuing)
    private_value, _public = _key_values()
    shared = jwt.encode(
        {
            "sub": "hf-123",
            "username": "alice",
            "iss": "https://paperswithcode.co",
            "aud": "paperswithcode",
            "exp": 4_000_000_000,
        },
        auth._private_key(private_value),
        algorithm="EdDSA",
    )
    legacy = jwt.encode(
        {"sub": "hf-123", "username": "alice", "exp": 4_000_000_000},
        issuing.jwt_secret,
        algorithm="HS256",
    )
    current = _settings(production=production)
    monkeypatch.setattr(auth, "get_settings", lambda: current)

    assert (
        auth.decode_request_session(
            _request("paperswithcode.co", f"pwc_shared_session={shared}")
        )
        is None
    )
    if production:
        assert (
            auth.decode_request_session(
                _request("paperswithcode.co", f"pwc_session={legacy}")
            )
            is None
        )


def test_staging_qualification_cookie_needs_no_server_side_session(monkeypatch):
    settings = _settings(production=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    token = auth.encode_qualification_session(
        {"sub": "operator:pi-qualification:1", "username": "operator"}, settings
    )

    payload = auth.decode_request_session(
        _request("staging.paperswithcode.co", f"pwc_staging_session={token}")
    )

    assert payload is not None
    assert payload["sub"] == "operator:pi-qualification:1"


def test_staging_logout_never_writes_production_sessions(monkeypatch, auth_sessions):
    cookies = _sign_in(monkeypatch, _settings(production=True))
    shared = _cookie_header(cookies, "pwc_shared_session")
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(production=False))

    auth.logout(
        _request("staging.paperswithcode.co", shared),
        return_to=None,
        everywhere=False,
    )

    assert auth_sessions.revoked == set()
