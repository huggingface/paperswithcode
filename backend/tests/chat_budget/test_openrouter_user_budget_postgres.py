"""Real PostgreSQL locking, restart, idempotency, and retention coverage."""

from __future__ import annotations

import asyncio
import base64
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.config import Settings, get_settings
from backend.models.database import (
    ChatOpenRouterCredential,
    ChatOpenRouterCredentialAudit,
    ChatOpenRouterMonthlyUsage,
    ChatOpenRouterProviderCall,
    ChatSession,
    ChatTurnCapability,
)
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.openrouter_byok_service import (
    OpenRouterBYOKService,
    OpenRouterCredentialUnavailable,
)
from backend.services.openrouter_user_budget_service import (
    OpenRouterAbuseLimitExceeded,
    OpenRouterMonthlyBudgetExhausted,
    OpenRouterUserBudgetService,
    RequestBounds,
)

NOW = datetime(2026, 8, 2, 12, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="staging",
        chat_openrouter_server_funded_enabled=True,
        chat_openrouter_monthly_user_budget_usd="0.40",
        chat_openrouter_pricing_verified_at="2026-08-02",
        chat_openrouter_user_tracking_secret="postgres-test-secret",
        chat_openrouter_credential_keyring='{"1":"%s"}'
        % base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        chat_openrouter_provider_call_retention_days=90,
        chat_openrouter_monthly_usage_retention_months=13,
        chat_openrouter_credential_audit_retention_days=30,
        jwt_secret="j" * 32,
    )


@pytest.fixture(scope="module")
def accounting_database_url():
    settings = get_settings()
    database_name = f"pwc_openrouter_accounting_{uuid.uuid4().hex[:12]}"
    subprocess.run(
        [
            "runuser",
            "-u",
            "postgres",
            "--",
            "createdb",
            "--owner",
            settings.db_user,
            database_name,
        ],
        check=True,
    )
    url = make_url(settings.database_url).set(database=database_name)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        subprocess.run(
            ["runuser", "-u", "postgres", "--", "dropdb", "--force", database_name],
            check=True,
        )


@pytest.fixture(scope="module")
def session_factory(accounting_database_url):
    engine = create_engine(accounting_database_url)
    ChatSession.__table__.create(engine)
    ChatTurnCapability.__table__.create(engine)
    ChatOpenRouterMonthlyUsage.__table__.create(engine)
    ChatOpenRouterProviderCall.__table__.create(engine)
    ChatOpenRouterCredential.__table__.create(engine)
    ChatOpenRouterCredentialAudit.__table__.create(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_final_budget_race_restart_idempotency_and_unknown_cost(session_factory):
    owner = "postgres-race-user"
    month = date(2026, 8, 1)
    with session_factory.begin() as db:
        db.add(
            ChatOpenRouterMonthlyUsage(
                hf_user_id=owner,
                month_start=month,
                limit_microusd=300_000,
                reserved_microusd=0,
                spent_microusd=200_000,
                unknown_cost_calls=0,
            )
        )

    identities = [(uuid.uuid4(), uuid.uuid4()), (uuid.uuid4(), uuid.uuid4())]
    bounds = RequestBounds(
        request_bytes=100,
        maximum_output_tokens=8_000,
        payload={"messages": [{"role": "user", "content": "race"}]},
    )

    def reserve(identity):
        turn_id, call_id = identity
        try:
            with session_factory.begin() as db:
                service = OpenRouterUserBudgetService(db, _settings())
                service.reserve_call(
                    owner,
                    turn_id,
                    call_id,
                    1,
                    service.settings.chat_deepseek_v4_flash_openrouter_route,
                    bounds,
                    NOW,
                )
            return call_id
        except OpenRouterMonthlyBudgetExhausted:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, identities))
    accepted = [call_id for call_id in results if call_id is not None]
    assert len(accepted) == 1

    # A new session/worker observes the persisted reservation, and a replay of
    # the same provider-call identity cannot reserve twice.
    with session_factory.begin() as db:
        service = OpenRouterUserBudgetService(db, _settings())
        usage = db.get(ChatOpenRouterMonthlyUsage, (owner, month))
        assert usage.reserved_microusd == 82_200
        assert service.can_fund_call(owner, NOW) is False
        winning_identity = next(item for item in identities if item[1] == accepted[0])
        replay = service.reserve_call(
            owner,
            winning_identity[0],
            winning_identity[1],
            1,
            service.settings.chat_deepseek_v4_flash_openrouter_route,
            bounds,
            NOW,
        )
        assert replay.idempotent_replay is True
        assert usage.reserved_microusd == 82_200
        service.mark_dispatched(accepted[0], NOW)
        service.mark_cost_unknown(accepted[0], "generation-1", NOW)

    with session_factory.begin() as db:
        service = OpenRouterUserBudgetService(db, _settings())
        status = service.status_percentage(owner, NOW)
        # The unknown call consumes its conservative reservation, and the
        # leftover cannot fund a normal call, so the public status is 0%.
        assert status.remaining_percent == 0
        assert len(service.unknown_calls()) == 1
        service.settle_call(accepted[0], 20_000, "generation-1", NOW)
        service.settle_call(accepted[0], 20_000, "generation-1", NOW)

    with session_factory() as db:
        usage = db.get(ChatOpenRouterMonthlyUsage, (owner, month))
        assert usage.reserved_microusd == 0
        assert usage.spent_microusd == 220_000
        assert usage.unknown_cost_calls == 0


def test_funded_call_abuse_circuits_and_qualification_bypass(session_factory):
    bounds = RequestBounds(
        request_bytes=100,
        maximum_output_tokens=100,
        payload={"messages": [{"role": "user", "content": "bounded"}]},
    )

    def reserve(db, settings, owner: str, now: datetime) -> None:
        OpenRouterUserBudgetService(db, settings).reserve_call(
            owner,
            uuid.uuid4(),
            uuid.uuid4(),
            1,
            settings.chat_deepseek_v4_flash_openrouter_route,
            bounds,
            now,
        )

    user_settings = _settings().model_copy(
        update={
            "chat_openrouter_user_rate_limit_calls": 2,
            "chat_openrouter_global_rate_limit_calls": 100,
            "chat_openrouter_daily_budget_usd": 100,
        }
    )
    user_now = NOW + timedelta(days=1)
    with session_factory.begin() as db:
        reserve(db, user_settings, "rate-user", user_now)
        reserve(db, user_settings, "rate-user", user_now)
        with pytest.raises(OpenRouterAbuseLimitExceeded) as limited:
            reserve(db, user_settings, "rate-user", user_now)
        assert limited.value.scope == "user_rate"

    global_settings = _settings().model_copy(
        update={
            "chat_openrouter_user_rate_limit_calls": 100,
            "chat_openrouter_global_rate_limit_calls": 2,
            "chat_openrouter_daily_budget_usd": 100,
        }
    )
    global_now = NOW + timedelta(days=2)
    with session_factory.begin() as db:
        reserve(db, global_settings, "global-user-1", global_now)
        reserve(db, global_settings, "global-user-2", global_now)
        with pytest.raises(OpenRouterAbuseLimitExceeded) as limited:
            reserve(db, global_settings, "global-user-3", global_now)
        assert limited.value.scope == "global_rate"

    daily_settings = _settings().model_copy(
        update={
            "chat_openrouter_user_rate_limit_calls": 100,
            "chat_openrouter_global_rate_limit_calls": 100,
            "chat_openrouter_daily_budget_usd": "0.02",
        }
    )
    daily_now = NOW + timedelta(days=3)
    with session_factory.begin() as db:
        reserve(db, daily_settings, "daily-user-1", daily_now)
        with pytest.raises(OpenRouterAbuseLimitExceeded) as limited:
            reserve(db, daily_settings, "daily-user-2", daily_now)
        assert limited.value.scope == "global_daily_budget"

    bypass_settings = _settings().model_copy(
        update={
            "chat_openrouter_user_rate_limit_calls": 1,
            "chat_openrouter_global_rate_limit_calls": 1,
            "chat_openrouter_daily_budget_usd": "0.001",
        }
    )
    bypass_now = NOW + timedelta(days=4)
    with session_factory.begin() as db:
        reserve(
            db,
            bypass_settings,
            "operator:pi-qualification:safeguard:0",
            bypass_now,
        )
        reserve(
            db,
            bypass_settings,
            "operator:pi-qualification:safeguard:0",
            bypass_now,
        )

    race_settings = _settings().model_copy(
        update={
            "chat_openrouter_user_rate_limit_calls": 100,
            "chat_openrouter_global_rate_limit_calls": 1,
            "chat_openrouter_daily_budget_usd": 100,
        }
    )
    race_now = NOW + timedelta(days=5)

    def race(owner: str) -> str | None:
        try:
            with session_factory.begin() as db:
                reserve(db, race_settings, owner, race_now)
            return owner
        except OpenRouterAbuseLimitExceeded:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(pool.map(race, ["global-race-1", "global-race-2"]))
    assert sum(owner is not None for owner in accepted) == 1


def test_retention_deletes_resolved_rows_but_keeps_unknown_cost(session_factory):
    old_month = date(2025, 1, 1)
    old = NOW - timedelta(days=400)
    settled_id = uuid.uuid4()
    unknown_id = uuid.uuid4()
    with session_factory.begin() as db:
        db.add_all(
            [
                ChatOpenRouterMonthlyUsage(
                    hf_user_id="resolved-owner",
                    month_start=old_month,
                    limit_microusd=400_000,
                    reserved_microusd=0,
                    spent_microusd=10_000,
                    unknown_cost_calls=0,
                    updated_at=old,
                ),
                ChatOpenRouterMonthlyUsage(
                    hf_user_id="unknown-owner",
                    month_start=old_month,
                    limit_microusd=400_000,
                    reserved_microusd=170_100,
                    spent_microusd=0,
                    unknown_cost_calls=1,
                    updated_at=old,
                ),
                ChatOpenRouterCredentialAudit(
                    owner_hash="a" * 64, action="connected", created_at=old
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                ChatOpenRouterProviderCall(
                    id=settled_id,
                    turn_id=uuid.uuid4(),
                    call_sequence=1,
                    hf_user_id="resolved-owner",
                    month_start=old_month,
                    model_route="test/model",
                    state="settled",
                    reserved_microusd=170_100,
                    actual_microusd=10_000,
                    reserved_at=old,
                    settled_at=old,
                    updated_at=old,
                ),
                ChatOpenRouterProviderCall(
                    id=unknown_id,
                    turn_id=uuid.uuid4(),
                    call_sequence=1,
                    hf_user_id="unknown-owner",
                    month_start=old_month,
                    model_route="test/model",
                    state="cost_unknown",
                    reserved_microusd=170_100,
                    generation_id="generation-unknown",
                    reserved_at=old,
                    dispatched_at=old,
                    updated_at=old,
                ),
            ]
        )

    with session_factory.begin() as db:
        result = OpenRouterUserBudgetService(db, _settings()).cleanup_retention(
            NOW, batch_size=100
        )
        assert result == {
            "provider_calls": 1,
            "monthly_usage": 1,
            "credential_audit": 1,
        }

    with session_factory() as db:
        assert db.get(ChatOpenRouterProviderCall, settled_id) is None
        assert db.get(ChatOpenRouterMonthlyUsage, ("resolved-owner", old_month)) is None
        assert db.get(ChatOpenRouterProviderCall, unknown_id) is not None
        assert (
            db.get(ChatOpenRouterMonthlyUsage, ("unknown-owner", old_month)) is not None
        )
        assert db.scalar(select(ChatOpenRouterCredentialAudit.id)) is None


def test_byok_is_cross_session_encrypted_consent_gated_and_revision_revoked(
    session_factory, monkeypatch: pytest.MonkeyPatch
):
    async def verified(_token: str, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "backend.services.openrouter_byok_service.verify_openrouter_inference_key",
        verified,
    )
    owner = "cross-device-user"
    token = "test-openrouter-cross-device-secret"
    with session_factory.begin() as db:
        status = asyncio.run(
            OpenRouterBYOKService(db, _settings()).connect(owner, token)
        )
        assert status.connected is True
        assert status.fallback_enabled is False
        assert set(status.public_dict()) == {
            "connected",
            "verified_at",
            "fallback_enabled",
        }

    with session_factory.begin() as db:
        service = OpenRouterBYOKService(db, _settings())
        assert service.selected(owner) is None
        row = db.get(ChatOpenRouterCredential, owner)
        assert token.encode() not in row.ciphertext
        status = service.set_fallback_enabled(owner, True)
        assert status.fallback_enabled is True
        selected = service.selected(owner)
        assert selected is not None and selected.token == token
        old_revision = selected.revision
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id=owner,
                hf_username=owner,
                selected_model="test/model",
                execution_backend="modal_cli",
            )
        )
        db.flush()
        issued = ChatCapabilityService(db).issue(
            chat_session_id=session_id,
            turn_id=turn_id,
            owner_id=owner,
            provider_token=token,
            provider_mode="openrouter_byok",
            provider_credential_revision=old_revision,
            settings=_settings(),
            model="test/model",
            scopes={"model"},
        )

    with session_factory.begin() as db:
        service = OpenRouterBYOKService(db, _settings())
        assert service.validate_dispatch(owner, old_revision).token == token
        service.invalidate_auth_failure(owner)

    with session_factory() as db:
        capability = db.get(ChatTurnCapability, issued.capability_id)
        assert capability.revoked_at is not None
        assert capability.provider_token_encrypted is None
        status = OpenRouterBYOKService(db, _settings()).status(owner)
        assert status.connected is True
        assert status.fallback_enabled is False
        with pytest.raises(OpenRouterCredentialUnavailable):
            OpenRouterBYOKService(db, _settings()).validate_dispatch(
                owner, old_revision
            )

    with session_factory.begin() as db:
        service = OpenRouterBYOKService(db, _settings())
        service.set_fallback_enabled(owner, True)
        selected = service.selected(owner)
        assert selected is not None
        disabled_capability = ChatCapabilityService(db).issue(
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
            owner_id=owner,
            provider_token=selected.token,
            provider_mode="openrouter_byok",
            provider_credential_revision=selected.revision,
            settings=_settings(),
            model="test/model",
            scopes={"model"},
        )
        service.set_fallback_enabled(owner, False)

    with session_factory() as db:
        capability = db.get(ChatTurnCapability, disabled_capability.capability_id)
        assert capability.revoked_at is not None
        assert capability.provider_token_encrypted is None

    with session_factory.begin() as db:
        service = OpenRouterBYOKService(db, _settings())
        service.set_fallback_enabled(owner, True)
        selected = service.selected(owner)
        assert selected is not None
        replacement_capability = ChatCapabilityService(db).issue(
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
            owner_id=owner,
            provider_token=selected.token,
            provider_mode="openrouter_byok",
            provider_credential_revision=selected.revision,
            settings=_settings(),
            model="test/model",
            scopes={"model"},
        )
        asyncio.run(service.connect(owner, "test-openrouter-replacement-secret"))

    with session_factory.begin() as db:
        capability = db.get(ChatTurnCapability, replacement_capability.capability_id)
        assert capability.revoked_at is not None
        assert capability.provider_token_encrypted is None
        service = OpenRouterBYOKService(db, _settings())
        service.set_fallback_enabled(owner, True)
        selected = service.selected(owner)
        assert selected is not None
        disconnect_capability = ChatCapabilityService(db).issue(
            chat_session_id=session_id,
            turn_id=uuid.uuid4(),
            owner_id=owner,
            provider_token=selected.token,
            provider_mode="openrouter_byok",
            provider_credential_revision=selected.revision,
            settings=_settings(),
            model="test/model",
            scopes={"model"},
        )
        service.disconnect(owner)
    with session_factory() as db:
        capability = db.get(ChatTurnCapability, disconnect_capability.capability_id)
        assert capability.revoked_at is not None
        assert capability.provider_token_encrypted is None
        assert OpenRouterBYOKService(db, _settings()).status(owner).connected is False
