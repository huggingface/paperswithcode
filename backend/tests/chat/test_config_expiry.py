"""Expiring chat configuration must degrade chat, never stop the backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.config import Settings
from backend.scripts import monitor_chat_operational_alerts as monitor
from backend.services.chat_config_expiry import (
    chat_config_expiries,
    expiring_chat_config,
)
from backend.services.openrouter_user_budget_service import (
    OpenRouterPricingUnavailable,
    RequestBounds,
    safe_maximum_microusd,
)
from deploy import config_expiry_preflight

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "chat_enabled": True,
        "chat_openrouter_pricing_verified_at": "2026-10-05",
        "chat_openrouter_pricing_max_age_days": 30,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _openrouter_bound(settings: Settings, now: datetime, **kwargs) -> int:
    return safe_maximum_microusd(
        settings,
        settings.chat_deepseek_v4_flash_openrouter_route,
        RequestBounds(1, 8_000, {"messages": [{"role": "user", "content": "x"}]}),
        now=now,
        **kwargs,
    )


def test_openrouter_expiry_matches_the_request_time_staleness_boundary():
    settings = _settings()
    [expiry] = chat_config_expiries(settings)

    assert expiry.name == "openrouter_pricing"
    assert expiry.expires_at == datetime(2026, 11, 5, tzinfo=UTC)
    _openrouter_bound(settings, expiry.expires_at - timedelta(seconds=1))
    with pytest.raises(OpenRouterPricingUnavailable, match="stale"):
        _openrouter_bound(settings, expiry.expires_at)


def test_startup_bound_ignores_staleness_but_requests_still_fail_closed():
    settings = _settings(chat_openrouter_pricing_verified_at="2000-01-01")
    now = datetime(2026, 11, 5, tzinfo=UTC)

    assert _openrouter_bound(settings, now, enforce_freshness=False) > 0
    with pytest.raises(OpenRouterPricingUnavailable, match="stale"):
        _openrouter_bound(settings, now)
    with pytest.raises(OpenRouterPricingUnavailable, match="date is invalid"):
        _openrouter_bound(
            _settings(chat_openrouter_pricing_verified_at="soon"),
            now,
            enforce_freshness=False,
        )


def test_only_enabled_features_report_expiries():
    assert chat_config_expiries(_settings(chat_enabled=False)) == []
    names = {
        expiry.name
        for expiry in chat_config_expiries(
            _settings(
                chat_openai_direct_enabled=True,
                chat_executor_remote_transport_enabled=True,
                chat_executor_admission_key_not_after_ms=1_793_546_530_000,
                chat_executor_authorization_keys_json=json.dumps(
                    {"current": {"not_after": 1_793_546_530}}
                ),
            )
        )
    }
    assert names == {
        "openrouter_pricing",
        "openai_pricing",
        "executor_admission_key",
        "executor_authorization_key",
    }


def test_expiring_window_includes_expired_and_soon_but_not_later_values():
    settings = _settings()
    expires_at = datetime(2026, 11, 5, tzinfo=UTC)

    assert expiring_chat_config(settings, expires_at - timedelta(days=8)) == []
    assert [
        e.name for e in expiring_chat_config(settings, expires_at - timedelta(days=7))
    ] == ["openrouter_pricing"]
    assert [
        e.name for e in expiring_chat_config(settings, expires_at + timedelta(days=30))
    ] == ["openrouter_pricing"]


def test_monitor_alerts_once_per_level_and_on_renewal():
    state = monitor.empty_state()
    expires_at = datetime(2026, 11, 5, tzinfo=UTC)
    settings = _settings()

    assert (
        monitor.collect_config_expiry_events(
            state, settings, expires_at - timedelta(days=30)
        )
        == []
    )

    [warning] = monitor.collect_config_expiry_events(
        state, settings, expires_at - timedelta(days=6)
    )
    assert warning["signal"] == "chat_config_expiring"
    assert warning["severity"] == "warning"
    assert warning["classifications"] == {"openrouter_pricing@2026-11-05": 1}
    assert (
        monitor.collect_config_expiry_events(
            state, settings, expires_at - timedelta(days=5)
        )
        == []
    )

    [critical] = monitor.collect_config_expiry_events(state, settings, expires_at)
    assert critical["signal"] == "chat_config_expired"
    assert critical["severity"] == "critical"
    assert state["config_expiry_active"] == {"openrouter_pricing": "expired"}

    [recovered] = monitor.collect_config_expiry_events(
        state, _settings(chat_openrouter_pricing_verified_at="2026-11-05"), expires_at
    )
    assert recovered["signal"] == "chat_config_expiry_recovered"
    assert recovered["severity"] == "recovery"
    assert state["config_expiry_active"] == {}


def test_monitor_state_round_trips_expiry_levels(tmp_path):
    path = tmp_path / "state.json"
    state = monitor.empty_state()
    state["config_expiry_active"] = {"openrouter_pricing": "expiring"}
    path.write_text(json.dumps(state))
    assert (
        monitor.load_state(path)["config_expiry_active"]
        == state["config_expiry_active"]
    )

    state["config_expiry_active"] = {"openrouter_pricing": "soonish"}
    path.write_text(json.dumps(state))
    with pytest.raises(TypeError, match="expiry state"):
        monitor.load_state(path)


def test_deploy_preflight_reads_the_release_defaults_without_importing_them():
    defaults = config_expiry_preflight.release_defaults(REPOSITORY_ROOT)
    settings = Settings(_env_file=None)

    assert set(defaults) == set(config_expiry_preflight.FIELDS)
    for name in config_expiry_preflight.FIELDS:
        assert defaults[name] == getattr(settings, name)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"chat_openrouter_pricing_verified_at": "2026-11-01"},
        {"chat_openai_direct_enabled": "true"},
        {
            "chat_executor_remote_transport_enabled": "true",
            "chat_executor_admission_key_not_after_ms": "1793546530000",
            "chat_executor_authorization_keys_json": json.dumps(
                {"current": {"not_after": 1_793_546_530}}
            ),
        },
    ],
)
def test_deploy_preflight_matches_backend_expiries(overrides):
    defaults = config_expiry_preflight.release_defaults(REPOSITORY_ROOT)
    settings = Settings(_env_file=None, chat_enabled=True, **overrides)

    assert config_expiry_preflight.config_expiries(defaults, overrides) == {
        expiry.name: expiry.expires_at for expiry in chat_config_expiries(settings)
    }


def test_deploy_preflight_reads_env_file_overrides(tmp_path):
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "# comment\n"
        "PWC_CHAT_OPENROUTER_PRICING_VERIFIED_AT='2026-10-05'\n"
        "PWC_UNRELATED=1\n"
    )
    now = datetime(2026, 11, 1, tzinfo=UTC)

    assert config_expiry_preflight.expiring(REPOSITORY_ROOT, env_file, now) == {
        "openrouter_pricing": datetime(2026, 11, 5, tzinfo=UTC)
    }
    env_file.write_text("PWC_CHAT_OPENROUTER_PRICING_VERIFIED_AT=2026-10-30\n")
    assert config_expiry_preflight.expiring(REPOSITORY_ROOT, env_file, now) == {}


@pytest.mark.parametrize("not_after", [10**20, -(10**20)])
def test_out_of_range_key_timestamps_never_raise(not_after):
    """Milliseconds in the seconds field must not crash the startup warning."""

    keys_json = json.dumps({"current": {"not_after": not_after}})
    settings = _settings(
        chat_openrouter_pricing_verified_at="2026-11-05",
        chat_executor_remote_transport_enabled=True,
        chat_executor_admission_key_not_after_ms=10**20,
        chat_executor_authorization_keys_json=keys_json,
    )

    assert [expiry.name for expiry in chat_config_expiries(settings)] == [
        "openrouter_pricing"
    ]
    assert config_expiry_preflight.config_expiries(
        config_expiry_preflight.release_defaults(REPOSITORY_ROOT),
        {
            "chat_openrouter_pricing_verified_at": "2026-11-05",
            "chat_executor_remote_transport_enabled": "true",
            "chat_executor_admission_key_not_after_ms": str(10**20),
            "chat_executor_authorization_keys_json": keys_json,
        },
    ).keys() == {"openrouter_pricing"}
