"""Host environment chat capacity, dispatch, and capacity-tier modes."""

from __future__ import annotations

from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env


def test_qualified_staging_capacity_keeps_one_warm_sandbox():
    assert configure_host_env.staging_chat_capacity_values() == {
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }


@pytest.mark.parametrize(
    ("environment", "active_turn_limit", "external_worker_limit"),
    [("staging", "2", "32"), ("production", "1", "8")],
)
def test_environment_examples_keep_durable_dispatch_disabled_and_current_safe(
    environment, active_turn_limit, external_worker_limit
):
    values = {
        key: value
        for line in Path(f"deploy/env/{environment}.env.example")
        .read_text()
        .splitlines()
        if line and not line.startswith("#")
        for key, value in [line.split("=", 1)]
    }

    assert values["PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED"] == "false"
    assert values["PWC_CHAT_MAX_CONCURRENCY"] == active_turn_limit
    assert values["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == external_worker_limit
    assert values["PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS"] == "10"
    assert values["PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS"] == "30"


def test_staging_capacity_configuration_preserves_explicit_pool_toggle():
    enabled = {"PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true"}
    values = configure_host_env.staging_chat_capacity_configuration(enabled)

    assert "PWC_CHAT_BLANK_POOL_ENABLED" not in values
    assert (
        configure_host_env.staging_chat_capacity_configuration({})[
            "PWC_CHAT_BLANK_POOL_ENABLED"
        ]
        == "false"
    )


def test_staging_chat_pool_toggle_is_narrow_and_bounded():
    assert configure_host_env.staging_chat_pool_values(enabled=True) == {
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }
    assert configure_host_env.staging_chat_pool_values(enabled=False) == {
        "PWC_CHAT_BLANK_POOL_ENABLED": "false"
    }


# Production break caught: the durable bridge toggle mutates capacity, worker,
# executor, workspace, or provider controls along with its single feature flag.
@pytest.mark.parametrize("enabled", [True, False])
def test_staging_chat_durable_dispatch_toggle_is_single_key(enabled: bool):
    assert configure_host_env.staging_chat_durable_dispatch_values(enabled=enabled) == {
        "PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED": "true" if enabled else "false"
    }


def test_production_durable_external_values_enable_32_with_isolated_token(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        configure_host_env.secrets, "token_urlsafe", lambda _size: "p" * 64
    )
    values = configure_host_env.production_durable_external_values(
        {
            "PWC_CHAT_PUBLIC_ADMISSION_ENABLED": "PWC_CHAT_PUBLIC_ADMISSION_ENABLED=true",
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true",
        },
        enabled=True,
    )

    assert values["PWC_CHAT_MAX_CONCURRENCY"] == "32"
    assert values["PWC_CHAT_USER_MAX_CONCURRENCY"] == "1"
    assert values["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] == "true"
    assert values["PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED"] == "true"
    assert values["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "32"
    assert values["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"] == "p" * 64
    assert values["PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY"] == "32"
    assert values["PWC_CHAT_OPENAI_USER_MAX_CONCURRENCY"] == "1"
    assert values["PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS"] == "512"
    assert values["PWC_CHAT_REMOTE_BASH_ENABLED"] == "true"
    assert values["PWC_CHAT_REMOTE_READ_ENABLED"] == "true"


def test_production_durable_external_values_preserve_token_on_disable():
    values = configure_host_env.production_durable_external_values(
        {
            "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": (
                "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=" + "k" * 64
            )
        },
        enabled=False,
    )

    assert "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN" not in values
    assert values["PWC_CHAT_MAX_CONCURRENCY"] == "2"
    assert values["PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY"] == "4"
    assert values["PWC_CHAT_OPENAI_USER_MAX_CONCURRENCY"] == "2"
    assert values["PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS"] == "80"
    assert values["PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_BLANK_POOL_ENABLED"] == "true"
    assert values["PWC_CHAT_PI_PREWARM_ENABLED"] == "true"


@pytest.mark.parametrize(
    ("environment", "tier", "rate_calls"),
    [
        ("production", 64, "4096"),
        ("production", 32, "512"),
        ("staging", 64, "4096"),
        ("staging", 32, "300"),
    ],
)
def test_chat_capacity_tier_values_move_all_four_budgets_together(
    environment, tier, rate_calls
):
    values = configure_host_env.chat_capacity_tier_values(
        {
            "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true"
        },
        environment=environment,
        tier=tier,
    )

    assert values == {
        "PWC_CHAT_MAX_CONCURRENCY": str(tier),
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(tier),
        "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": str(tier),
        "PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS": rate_calls,
    }


def test_chat_capacity_tier_values_require_external_admission_and_a_reviewed_tier():
    enabled = {
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true"
    }
    with pytest.raises(ValueError, match="admission must already be enabled"):
        configure_host_env.chat_capacity_tier_values(
            {}, environment="production", tier=64
        )
    with pytest.raises(ValueError, match="admission must already be enabled"):
        configure_host_env.chat_capacity_tier_values(
            {
                "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=false"
            },
            environment="production",
            tier=64,
        )
    with pytest.raises(ValueError, match="32 or 64"):
        configure_host_env.chat_capacity_tier_values(
            enabled, environment="production", tier=48
        )
    with pytest.raises(ValueError, match="staging or production"):
        configure_host_env.chat_capacity_tier_values(
            enabled, environment="development", tier=64
        )
