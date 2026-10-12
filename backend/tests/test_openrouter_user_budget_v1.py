from __future__ import annotations

import asyncio
import base64
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.config import Settings
from backend.routers import chat as chat_router
from backend.services import chat_admission_billing as chat_billing
from backend.routers.chat import _require_recent_auth
from backend.services.chat_admission_billing import authorize_openrouter
from backend.services.chat_session_service import ChatServiceError
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
)
from backend.services.openrouter_byok_service import (
    OpenRouterCredentialError,
    decrypt_openrouter_key,
    encrypt_openrouter_key,
    verify_openrouter_inference_key,
)
from backend.services.openrouter_user_budget_service import (
    OpenRouterPricingUnavailable,
    OpenRouterUserBudgetService,
    RequestBounds,
    safe_maximum_microusd,
    utc_month,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "chat_enabled": True,
        "chat_openrouter_credential_keyring": '{"1":"%s"}'
        % base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        "chat_openrouter_credential_active_key_version": 1,
        "chat_openrouter_pricing_verified_at": "2026-08-02",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("now", "start", "reset"),
    [
        (
            datetime(2024, 2, 29, 23, 59, tzinfo=UTC),
            "2024-02-01",
            "2024-03-01T00:00:00+00:00",
        ),
        (
            datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
            "2026-12-01",
            "2027-01-01T00:00:00+00:00",
        ),
    ],
)
def test_utc_calendar_month_boundaries(now, start, reset):
    month, resets_at = utc_month(now)
    assert month.isoformat() == start
    assert resets_at.isoformat() == reset


def test_safe_maximum_is_integer_conservative_and_modality_closed():
    settings = _settings()
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    maximum = safe_maximum_microusd(
        settings,
        settings.chat_deepseek_v4_flash_openrouter_route,
        RequestBounds(512 * 1024, 8_000, payload),
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )
    assert maximum == 512 * 1024 * 2 + 8_000 * 9 + 10_000
    assert maximum > 1_000_000

    with pytest.raises(OpenRouterPricingUnavailable):
        safe_maximum_microusd(
            settings,
            settings.chat_deepseek_v4_flash_openrouter_route,
            RequestBounds(
                100,
                8_000,
                {"messages": [{"content": [{"type": "image_url"}]}]},
            ),
            now=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_safe_maximum_accepts_nested_tool_schema_type_property():
    settings = _settings()
    payload = {
        "tools": [
            {
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                    },
                }
            }
        ]
    }

    maximum = safe_maximum_microusd(
        settings,
        settings.chat_deepseek_v4_flash_openrouter_route,
        RequestBounds(100, 8_000, payload),
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert maximum == 100 * 2 + 8_000 * 9 + 10_000


def test_safe_maximum_fails_closed_for_stale_or_unknown_pricing():
    settings = _settings(chat_openrouter_pricing_verified_at="2026-01-01")
    bounds = RequestBounds(100, 8_000, {"messages": []})
    with pytest.raises(OpenRouterPricingUnavailable):
        safe_maximum_microusd(
            settings,
            settings.chat_deepseek_v4_flash_openrouter_route,
            bounds,
            now=datetime(2026, 8, 2, tzinfo=UTC),
        )
    with pytest.raises(OpenRouterPricingUnavailable):
        safe_maximum_microusd(
            _settings(),
            "unpriced/model",
            bounds,
            now=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_aes_256_gcm_is_owner_bound_and_never_contains_plaintext():
    settings = _settings()
    ciphertext, nonce, version = encrypt_openrouter_key(
        "sk-or-v1-private", "hf-user-1", settings
    )
    assert len(nonce) == 12
    assert version == 1
    assert b"sk-or-v1-private" not in ciphertext
    row = SimpleNamespace(
        hf_user_id="hf-user-1",
        ciphertext=ciphertext,
        nonce=nonce,
        encryption_key_version=version,
    )
    assert decrypt_openrouter_key(row, settings) == "sk-or-v1-private"
    row.hf_user_id = "hf-user-2"
    with pytest.raises(Exception):
        decrypt_openrouter_key(row, settings)


@pytest.mark.parametrize("field", ["is_management_key", "is_provisioning_key"])
def test_byok_verification_rejects_non_inference_keys(field):
    async def run():
        def handler(_request: httpx.Request):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "is_management_key": field == "is_management_key",
                        "is_provisioning_key": field == "is_provisioning_key",
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await verify_openrouter_inference_key("sk-or-v1-test", client=client)

    with pytest.raises(OpenRouterCredentialError):
        asyncio.run(run())


def test_byok_verification_reports_a_rejected_key_as_invalid():
    async def run():
        def handler(_request: httpx.Request):
            return httpx.Response(401, json={"error": "invalid key"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await verify_openrouter_inference_key("sk-or-v1-invalid", client=client)

    with pytest.raises(OpenRouterCredentialError, match="rejected"):
        asyncio.run(run())


def test_migration_is_staging_owned_idempotent_and_secret_safe():
    migration = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_openrouter_user_budget.sql"
    ).read_text()
    assert "current_schema() <> 'staging'" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_monthly_usage" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_provider_calls" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_credentials" in migration
    assert (
        "ALTER TABLE chat_openrouter_credentials OWNER TO pwc_staging_owner"
        in migration
    )
    assert "REVOKE ALL ON chat_openrouter_credentials" in migration
    assert "plaintext" not in migration.lower()


def test_byok_remains_available_when_funded_preview_is_disabled(monkeypatch):
    revision = __import__("uuid").uuid4()
    monkeypatch.setattr(
        "backend.services.chat_admission_billing.OpenRouterBYOKService.selected",
        lambda _service, _owner: SimpleNamespace(token="sk-or-user", revision=revision),
    )
    admission = asyncio.run(
        authorize_openrouter(
            _settings(chat_openrouter_server_funded_enabled=False),
            SimpleNamespace(),
            "hf-user",
        )
    )
    assert admission.mode == "openrouter_byok"
    assert admission.token == "sk-or-user"
    assert admission.credential_revision == revision

    monkeypatch.setattr(
        "backend.services.chat_admission_billing.OpenRouterBYOKService.selected",
        lambda _service, _owner: None,
    )
    with pytest.raises(ChatServiceError) as error:
        asyncio.run(
            authorize_openrouter(
                _settings(chat_openrouter_server_funded_enabled=False),
                SimpleNamespace(),
                "hf-user",
            )
        )
    assert error.value.code == "openrouter_unavailable"


def test_non_admin_staging_users_receive_shared_funding(monkeypatch):
    async def allow(_settings):
        return None

    monkeypatch.setattr(chat_billing, "require_openrouter_budget", allow)
    admission = asyncio.run(
        authorize_openrouter(
            _settings(chat_openrouter_server_funded_enabled=True),
        )
    )
    assert admission.mode == "openrouter_funded"


def test_production_funding_is_unchanged_for_non_admins(monkeypatch):
    async def allow(_settings):
        return None

    monkeypatch.setattr(chat_billing, "require_openrouter_budget", allow)
    admission = asyncio.run(
        authorize_openrouter(
            _settings(
                environment="production",
                chat_openrouter_server_funded_enabled=True,
            ),
        )
    )
    assert admission.mode == "openrouter_funded"


def test_staging_admin_retains_five_dollar_monthly_allowance():
    settings = _settings(
        chat_openrouter_monthly_user_budget_usd=1,
        admin_hf_subjects="admin-subject",
    )
    service = OpenRouterUserBudgetService(SimpleNamespace(), settings)

    assert service.limit_microusd_for("regular-subject") == 1_000_000
    assert service.limit_microusd_for("admin-subject") == 5_000_000


def test_recent_auth_and_same_origin_csrf_are_both_required(monkeypatch):
    settings = _settings(
        environment="staging",
        release_id="test-release",
        chat_openrouter_recent_auth_seconds=900,
    )

    def request(origin: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "PUT",
                "path": "/api/v1/chat/openrouter-key",
                "headers": [
                    (b"host", b"staging.paperswithcode.co"),
                    (b"origin", origin.encode()),
                    (b"sec-fetch-site", b"same-origin"),
                ],
            }
        )

    monkeypatch.setattr(
        "backend.routers.auth.decode_request_session",
        lambda _request: {"iat": time.time()},
    )
    _require_recent_auth(request("https://staging.paperswithcode.co"), {}, settings)

    monkeypatch.setattr(
        "backend.routers.auth.decode_request_session",
        lambda _request: {"iat": time.time() - 901},
    )
    with pytest.raises(HTTPException) as stale:
        _require_recent_auth(request("https://staging.paperswithcode.co"), {}, settings)
    assert stale.value.status_code == 401
    assert stale.value.detail["code"] == "fresh_auth_required"

    monkeypatch.setattr(
        "backend.routers.auth.decode_request_session",
        lambda _request: {"iat": time.time()},
    )
    with pytest.raises(HTTPException) as csrf:
        _require_recent_auth(request("https://attacker.example"), {}, settings)
    assert csrf.value.status_code == 403
    assert csrf.value.detail["code"] == "csrf_rejected"


def test_disabling_byok_consent_does_not_require_step_up(monkeypatch):
    csrf_checks = []

    class FakeDB:
        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeService:
        def __init__(self, *_args):
            pass

        def set_fallback_enabled(self, owner: str, enabled: bool):
            assert owner == "hf-user"
            assert enabled is False
            return SimpleNamespace(
                public_dict=lambda: {
                    "connected": True,
                    "verified_at": None,
                    "fallback_enabled": False,
                }
            )

    monkeypatch.setattr(chat_router, "OpenRouterBYOKService", FakeService)
    monkeypatch.setattr(
        chat_router,
        "_require_recent_auth",
        lambda *_args: (_ for _ in ()).throw(AssertionError("step-up called")),
    )
    monkeypatch.setattr(
        chat_router,
        "_require_same_origin_csrf",
        lambda request, settings: csrf_checks.append((request, settings)),
    )
    request = SimpleNamespace()
    settings = _settings()
    result = chat_router.set_openrouter_fallback(
        chat_router.SetOpenRouterFallback(enabled=False),
        request,
        {"hf_user_id": "hf-user"},
        FakeDB(),
        settings,
    )
    assert result == {
        "connected": True,
        "verified_at": None,
        "fallback_enabled": False,
    }
    assert csrf_checks == [(request, settings)]


def test_disabling_byok_consent_still_rejects_cross_origin():
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/v1/chat/openrouter-key",
            "headers": [
                (b"host", b"staging.paperswithcode.co"),
                (b"origin", b"https://attacker.example"),
                (b"sec-fetch-site", b"cross-site"),
            ],
        }
    )
    with pytest.raises(HTTPException) as csrf:
        chat_router.set_openrouter_fallback(
            chat_router.SetOpenRouterFallback(enabled=False),
            request,
            {"hf_user_id": "hf-user"},
            SimpleNamespace(),
            _settings(environment="staging", release_id="test-release"),
        )
    assert csrf.value.status_code == 403
    assert csrf.value.detail["code"] == "csrf_rejected"


def test_allowance_and_workspace_failures_have_distinct_secret_safe_contracts(
    monkeypatch,
):
    reset = datetime(2026, 9, 1, tzinfo=UTC)

    class ExhaustedBudget:
        def __init__(self, *_args):
            pass

        def can_fund_call(self, _owner):
            return False

        def status_percentage(self, _owner):
            return SimpleNamespace(
                used_percent=60,
                remaining_percent=40,
                resets_at=reset,
            )

    monkeypatch.setattr(chat_billing, "OpenRouterUserBudgetService", ExhaustedBudget)
    monkeypatch.setattr(
        "backend.services.chat_admission_billing.OpenRouterBYOKService.selected",
        lambda _service, _owner: None,
    )
    with pytest.raises(ChatServiceError) as exhausted:
        asyncio.run(
            authorize_openrouter(
                _settings(chat_openrouter_server_funded_enabled=True),
                SimpleNamespace(),
                "hf-user",
            )
        )
    assert exhausted.value.status_code == 429
    assert exhausted.value.code == "openrouter_monthly_budget_exhausted"
    assert exhausted.value.details == {
        "used_percent": 60,
        "remaining_percent": 40,
        "resets_at": "2026-09-01T00:00:00Z",
    }
    assert not any("usd" in key or "dollar" in key for key in exhausted.value.details)

    class AvailableBudget(ExhaustedBudget):
        def can_fund_call(self, _owner):
            return True

    async def workspace_exhausted(_settings):
        raise OpenRouterBudgetExceeded("internal workspace reason")

    monkeypatch.setattr(chat_billing, "OpenRouterUserBudgetService", AvailableBudget)
    monkeypatch.setattr(chat_billing, "require_openrouter_budget", workspace_exhausted)
    with pytest.raises(ChatServiceError) as unavailable:
        asyncio.run(
            authorize_openrouter(
                _settings(chat_openrouter_server_funded_enabled=True),
                SimpleNamespace(),
                "hf-user",
            )
        )
    assert unavailable.value.status_code == 503
    assert unavailable.value.code == "openrouter_unavailable"
    assert unavailable.value.details == {
        "byok_settings_available": True,
        "support_url": "https://github.com/huggingface/paperswithcode-feedback",
    }
    assert "workspace" not in str(unavailable.value).lower()


def test_usage_reports_shared_credit_failure_separately_from_user_allowance(
    monkeypatch,
):
    user_status = SimpleNamespace(
        available=True,
        public_dict=lambda: {
            "used_percent": 57,
            "remaining_percent": 43,
            "resets_at": datetime(2026, 9, 1, tzinfo=UTC),
            "available": True,
            "as_of": datetime(2026, 8, 4, tzinfo=UTC),
        },
    )

    class UserBudget:
        def __init__(self, *_args):
            pass

        def status_percentage(self, _owner):
            return user_status

    async def shared_status(_settings):
        return SimpleNamespace(
            within_budget=False,
            unavailable_reason="shared_credits_exhausted",
        )

    monkeypatch.setattr(chat_router, "OpenRouterUserBudgetService", UserBudget)
    monkeypatch.setattr(chat_router, "openrouter_budget_status", shared_status)

    result = asyncio.run(
        chat_router.get_openrouter_usage(
            {"hf_user_id": "hf-user", "role": "admin"},
            SimpleNamespace(),
            _settings(chat_openrouter_server_funded_enabled=True),
        )
    )

    assert result["remaining_percent"] == 43
    assert result["available"] is False
    assert result["unavailable_reason"] == "shared_credits_exhausted"


def test_usage_reports_non_admin_staging_allowance(monkeypatch):
    user_status = SimpleNamespace(
        available=True,
        public_dict=lambda: {
            "used_percent": 12,
            "remaining_percent": 88,
            "resets_at": datetime(2026, 9, 1, tzinfo=UTC),
            "available": True,
            "as_of": datetime(2026, 8, 4, tzinfo=UTC),
        },
    )

    class UserBudget:
        def __init__(self, *_args):
            pass

        def status_percentage(self, _owner):
            return user_status

    async def shared_status(_settings):
        return SimpleNamespace(within_budget=True, unavailable_reason=None)

    monkeypatch.setattr(chat_router, "OpenRouterUserBudgetService", UserBudget)
    monkeypatch.setattr(chat_router, "openrouter_budget_status", shared_status)

    result = asyncio.run(
        chat_router.get_openrouter_usage(
            {"hf_user_id": "hf-user", "role": None},
            SimpleNamespace(),
            _settings(chat_openrouter_server_funded_enabled=True),
        )
    )

    assert result["available"] is True
    assert result["remaining_percent"] == 88
    assert result["unavailable_reason"] is None
