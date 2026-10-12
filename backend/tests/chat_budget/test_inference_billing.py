from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend.config import Settings
from backend.routers import inference_billing as billing_router
from backend.services import hf_inference_billing_service as billing


def _settings() -> Settings:
    return Settings(
        jwt_secret="x" * 32,
        hf_oauth_credential_secret="shared-oauth-secret",
        shared_session_cookie_domain=".paperswithcode.co",
    )


def test_inference_token_round_trip_is_bound_to_hf_subject():
    encrypted = billing.encrypt_token("hf_secret", "hf-user-1", _settings())

    assert billing.decrypt_token(encrypted, "hf-user-1", _settings()) == "hf_secret"
    assert billing.decrypt_token(encrypted, "hf-user-2", _settings()) is None
    assert "hf_secret" not in encrypted


def test_inference_credential_round_trip_preserves_organization_billing():
    encrypted = billing.encrypt_credential(
        billing.HfInferenceCredential("hf_secret", "huggingface"),
        "hf-user-1",
        _settings(),
    )

    assert billing.decrypt_credential(
        encrypted, "hf-user-1", _settings()
    ) == billing.HfInferenceCredential("hf_secret", "huggingface")


def test_oauth_credential_round_trip_uses_shared_secret_across_environments():
    production = Settings(
        jwt_secret="production-secret",
        hf_oauth_credential_secret="shared-oauth-secret",
    )
    staging = Settings(
        jwt_secret="staging-secret",
        hf_oauth_credential_secret="shared-oauth-secret",
    )
    encrypted = billing.encrypt_oauth_credential(
        billing.HfInferenceCredential("oauth_access", "huggingface"),
        "hf-user-1",
        production,
    )

    assert "oauth_access" not in encrypted
    assert billing.decrypt_oauth_credential(
        encrypted, "hf-user-1", staging
    ) == billing.HfInferenceCredential("oauth_access", "huggingface")
    assert billing.decrypt_oauth_credential(encrypted, "hf-user-2", staging) is None


def test_verify_token_detects_pro_account(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            assert url == billing.HF_WHOAMI_URL
            assert headers["Authorization"] == "Bearer hf_test"
            return httpx.Response(
                200,
                json={
                    "id": "hf-user-1",
                    "name": "alice",
                    "isPro": True,
                    "orgs": [
                        {"name": "zeta", "plan": "team"},
                        {
                            "name": "huggingface",
                            "fullname": "Hugging Face",
                            "plan": {"name": "enterprise"},
                        },
                    ],
                },
            )

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    account = asyncio.run(billing.verify_token("hf_test", "hf-user-1"))

    assert account.username == "alice"
    assert account.is_pro is True
    assert account.organizations == (
        billing.HfInferenceOrganization("huggingface", "Hugging Face"),
        billing.HfInferenceOrganization("zeta", "zeta"),
    )
    billing.validate_bill_to(account, "huggingface")

    with pytest.raises(billing.HfInferenceCredentialError):
        billing.validate_bill_to(account, "not-my-org")


def test_verify_token_rejects_a_different_account(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"id": "someone-else", "name": "mallory", "isPro": False},
            )

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(
        billing.HfInferenceCredentialError,
        match="different Hugging Face account",
    ):
        asyncio.run(billing.verify_token("hf_test", "hf-user-1"))


def test_verify_oauth_token_reads_authorized_organizations(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            assert url == billing.HF_USERINFO_URL
            assert headers["Authorization"] == "Bearer oauth_access"
            return httpx.Response(
                200,
                json={
                    "sub": "hf-user-1",
                    "preferred_username": "alice",
                    "isPro": True,
                    "orgs": [
                        {
                            "preferred_username": "huggingface",
                            "name": "Hugging Face",
                            "plan": "enterprise",
                        },
                        {
                            "preferred_username": "community",
                            "name": "Community",
                        },
                    ],
                },
            )

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    account = asyncio.run(billing.verify_oauth_token("oauth_access", "hf-user-1"))

    assert account.is_pro is True
    assert account.organizations == (
        billing.HfInferenceOrganization("huggingface", "Hugging Face"),
    )


def test_select_billing_account_updates_encrypted_cookie(monkeypatch):
    settings = _settings()
    encrypted = billing.encrypt_token("hf_secret", "hf-user-1", settings)
    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{billing.COOKIE_NAME}={encrypted}".encode(),
                )
            ],
        }
    )
    response = Response()
    account = billing.HfInferenceAccount(
        subject="hf-user-1",
        username="alice",
        is_pro=True,
        organizations=(billing.HfInferenceOrganization("huggingface", "Hugging Face"),),
    )

    async def fake_verify_token(token, expected_subject):
        assert token == "hf_secret"
        assert expected_subject == "hf-user-1"
        return account

    monkeypatch.setattr(billing_router, "verify_token", fake_verify_token)
    status = asyncio.run(
        billing_router.select_inference_billing_account(
            billing_router.SelectInferenceBillingAccount(bill_to="huggingface"),
            request,
            response,
            {"hf_user_id": "hf-user-1"},
            settings,
        )
    )

    assert status.bill_to == "huggingface"
    assert status.account_type == "Organization"
    assert status.monthly_credits_usd is None
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    saved = cookie[billing.COOKIE_NAME].value
    assert billing.decrypt_credential(
        saved, "hf-user-1", settings
    ) == billing.HfInferenceCredential("hf_secret", "huggingface")


def test_select_billing_account_updates_shared_oauth_cookie(monkeypatch):
    settings = _settings()
    encrypted = billing.encrypt_oauth_credential(
        billing.HfInferenceCredential("oauth_access"), "hf-user-1", settings
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{billing.OAUTH_COOKIE_NAME}={encrypted}".encode(),
                )
            ],
        }
    )
    response = Response()
    account = billing.HfInferenceAccount(
        subject="hf-user-1",
        username="alice",
        is_pro=True,
        organizations=(billing.HfInferenceOrganization("huggingface", "Hugging Face"),),
    )

    async def fake_verify_token(token, expected_subject):
        assert token == "oauth_access"
        assert expected_subject == "hf-user-1"
        return account

    monkeypatch.setattr(billing_router, "verify_oauth_token", fake_verify_token)
    status = asyncio.run(
        billing_router.select_inference_billing_account(
            billing_router.SelectInferenceBillingAccount(bill_to="huggingface"),
            request,
            response,
            {"hf_user_id": "hf-user-1"},
            settings,
        )
    )

    assert status.bill_to == "huggingface"
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    saved = cookie[billing.OAUTH_COOKIE_NAME]
    assert saved["domain"] == ".paperswithcode.co"
    assert billing.decrypt_oauth_credential(
        saved.value, "hf-user-1", settings
    ) == billing.HfInferenceCredential("oauth_access", "huggingface")
