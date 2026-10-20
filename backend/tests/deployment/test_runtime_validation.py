"""Deployed runtime validation of chat, provider, and environment policy."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env
from backend.services import openrouter_budget_service as deploy_openrouter
from backend.services.runtime_validation import (
    validate_chat_capacity_and_spend_policy,
    validate_runtime,
)
from deploy.release import (
    build_manifest,
    profile_features,
    validate_rolling_compatibility,
)
from backend.tests.deployment.harness import (
    configure_hf_scope_and_title,
    deployed_settings,
    make_bundle,
)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployed_runtime_validation(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    assert validate_runtime(settings) == profile_features(environment)


def test_staging_runtime_rejects_unapproved_team_environment_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_environment_cap_microusd = 125_000_000
    settings.chat_sandbox_budget_attestation = "modal-workspace-250-staging-125-v1"

    with pytest.raises(RuntimeError, match="BUDGET_ATTESTATION"):
        validate_runtime(settings)


def test_production_runtime_accepts_reviewed_team_environment_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_max_concurrency = 2
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_environment_cap_microusd = 125_000_000
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_modal_workspace = "paperswithcode"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-paperswithcode-250-production-125-v1"
    )
    settings.chat_sandbox_slack_webhook_url = "https://hooks.slack.test/production"
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    configure_hf_scope_and_title(settings, "production")

    validate_chat_capacity_and_spend_policy(settings)


def test_enabled_chat_rejects_missing_hf_authentication_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.hf_oauth_credential_secret = ""

    with pytest.raises(RuntimeError, match="OAuth authentication path"):
        validate_runtime(settings)


def test_enabled_chat_does_not_require_general_server_hf_token(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.hf_token = ""

    assert validate_runtime(settings) == profile_features("staging")


def test_enabled_chat_requires_hf_glm_title_credential(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_title_hf_token = ""

    with pytest.raises(RuntimeError, match="HF GLM title credential"):
        validate_runtime(settings)


def test_enabled_chat_requires_named_environment_scoped_title_owner(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    for field, value in [
        ("chat_title_credential_owner", " "),
        ("chat_title_credential_environment", "production"),
    ]:
        with pytest.raises(RuntimeError, match="title credential with a named owner"):
            validate_runtime(settings.model_copy(update={field: value}))


def test_title_circuit_accepts_operator_chosen_monthly_cap(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_title_monthly_cap_microusd = 50_000_000

    assert validate_runtime(settings) == profile_features("staging")

    settings.chat_title_warning_microusd = 50_000_000
    with pytest.raises(RuntimeError, match="monthly circuit"):
        validate_runtime(settings)


def test_enforced_runtime_rejects_legacy_openrouter_title_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_title_provider = "openrouter"
    settings.chat_title_model = "deepseek/deepseek-v4-flash-0731"

    with pytest.raises(RuntimeError, match="HF GLM title credential"):
        validate_runtime(settings)


def test_enabled_chat_requires_scope_guardrail(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_scope_guardrail_enabled = False

    with pytest.raises(RuntimeError, match="research-scope guardrail"):
        validate_runtime(settings)


def test_bridge_runtime_rejects_unapproved_hf_title_model(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_title_model = "deepseek-ai/DeepSeek-V4-Flash-0731:fastest"

    with pytest.raises(RuntimeError, match="HF GLM title credential"):
        validate_runtime(settings)


def test_starter_runtime_rejects_unenforced_environment_cap(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_environment_cap_microusd = 125_000_000

    with pytest.raises(RuntimeError, match="no environment cap"):
        validate_runtime(settings)


def test_staging_requires_alerts_even_when_blank_pool_is_disabled(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_sandbox_slack_webhook_url = ""
    settings.chat_sandbox_alert_fallback_webhook_url = ""
    settings.chat_blank_pool_enabled = False
    with pytest.raises(RuntimeError, match="alert destinations are required"):
        validate_runtime(settings)


def test_staging_allows_budgeted_server_funded_openrouter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    monkeypatch.setattr(
        "backend.services.openrouter_budget_service.validate_openrouter_guardrail",
        lambda _settings: None,
    )

    assert validate_runtime(settings) == profile_features("staging")


@pytest.mark.parametrize("budget", [5, 199, 201])
def test_staging_rejects_openrouter_workspace_budget_other_than_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: int
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    settings.chat_openrouter_workspace_monthly_budget_usd = budget
    monkeypatch.setattr(
        "backend.services.openrouter_budget_service.validate_openrouter_guardrail",
        lambda _settings: None,
    )

    with pytest.raises(RuntimeError, match="must equal \\$200"):
        validate_runtime(settings)


def test_staging_rejects_missing_provider_enforced_guardrail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True

    def missing(_settings):
        raise deploy_openrouter.OpenRouterBudgetUnavailable("no hard limit")

    monkeypatch.setattr(deploy_openrouter, "validate_openrouter_guardrail", missing)
    with pytest.raises(RuntimeError, match="provider-enforced guardrail"):
        validate_runtime(settings)


def test_staging_rejects_openrouter_request_bound_above_user_budget(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    settings.chat_openrouter_monthly_user_budget_usd = 5

    with pytest.raises(RuntimeError, match=r"per-user budget must equal \$1"):
        validate_runtime(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chat_openrouter_daily_budget_usd", 11),
        ("chat_openrouter_rate_limit_window_seconds", 300),
        ("chat_openrouter_user_rate_limit_calls", 31),
        ("chat_openrouter_global_rate_limit_calls", 81),
    ],
)
def test_staging_rejects_weakened_openrouter_abuse_circuit(
    tmp_path: Path,
    field: str,
    value: int,
):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_openrouter_server_funded_enabled = True
    setattr(settings, field, value)

    with pytest.raises(RuntimeError, match="abuse circuit policy is invalid"):
        validate_runtime(settings)


def test_staging_openrouter_values_preserve_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    key = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()
    (config_root / "staging.env").write_text(
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING='"
        + json.dumps({"1": key}, separators=(",", ":"))
        + "'\n"
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET=stable-secret\n"
    )
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)

    values = configure_host_env.staging_openrouter_values(
        {"PWC_OPENROUTER_API_KEY": "PWC_OPENROUTER_API_KEY=provider-key"}
    )

    assert json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"]) == {"1": key}
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"] == "stable-secret"
    assert values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] == "1.00"
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "200.00"


def test_staging_openrouter_secret_rotation_preserves_decryption_versions():
    old_key = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()
    current = {
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": (
            "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING='"
            + json.dumps({"1": old_key}, separators=(",", ":"))
            + "'"
        ),
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": (
            "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION=1"
        ),
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": (
            "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET=old-secret"
        ),
    }

    values = configure_host_env.rotate_staging_openrouter_secret_values(current)

    keyring = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])
    assert keyring["1"] == old_key
    assert (
        len(base64.urlsafe_b64decode(keyring["2"] + "=" * (-len(keyring["2"]) % 4)))
        == 32
    )
    assert values["PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION"] == "2"
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"] != "old-secret"


def test_dormant_production_accepts_sealed_openrouter_with_dispatch_disabled(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_openrouter_server_funded_enabled = False

    assert validate_runtime(settings) == profile_features("production")


def test_production_runtime_accepts_reviewed_250_environment_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_max_concurrency = 2
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_environment_cap_microusd = 250_000_000
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_modal_workspace = "paperswithcode"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-paperswithcode-250-production-250-v2"
    )
    settings.chat_sandbox_slack_webhook_url = "https://hooks.slack.test/production"
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    configure_hf_scope_and_title(settings, "production")
    validate_chat_capacity_and_spend_policy(settings)


def test_production_runtime_accepts_reviewed_225_application_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_max_concurrency = 2
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_warning_microusd = 200_000_000
    settings.chat_sandbox_application_cap_microusd = 225_000_000
    settings.chat_sandbox_environment_cap_microusd = 250_000_000
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_modal_workspace = "paperswithcode"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-paperswithcode-250-production-250-warn200-app225-v3"
    )
    settings.chat_sandbox_slack_webhook_url = "https://hooks.slack.test/production"
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    configure_hf_scope_and_title(settings, "production")

    validate_chat_capacity_and_spend_policy(settings)


def test_staging_runtime_rejects_shared_session_signer(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.session_signing_private_key = (
        base64.urlsafe_b64encode(b"\x01" * 32).rstrip(b"=").decode()
    )
    with pytest.raises(RuntimeError, match="staging must not have"):
        validate_runtime(settings)


def test_production_runtime_rejects_mismatched_session_keys(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.session_signing_private_key = (
        base64.urlsafe_b64encode(b"\x03" * 32).rstrip(b"=").decode()
    )
    with pytest.raises(RuntimeError, match="signing and verification keys differ"):
        validate_runtime(settings)


def test_shared_session_key_generation_is_stable():
    private_value, public_value = configure_host_env.shared_session_keys({}, {})
    production = {
        "PWC_SESSION_SIGNING_PRIVATE_KEY": (
            f"PWC_SESSION_SIGNING_PRIVATE_KEY={private_value}"
        ),
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": (
            f"PWC_SESSION_VERIFICATION_PUBLIC_KEY={public_value}"
        ),
    }
    staging = {
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": (
            f"PWC_SESSION_VERIFICATION_PUBLIC_KEY={public_value}"
        )
    }

    assert configure_host_env.shared_session_keys(production, staging) == (
        private_value,
        public_value,
    )


def test_shared_oauth_credential_secret_is_stable_and_conflict_safe():
    production = {
        "PWC_HF_OAUTH_CREDENTIAL_SECRET": (
            "PWC_HF_OAUTH_CREDENTIAL_SECRET=shared-secret"
        )
    }
    staging = dict(production)

    assert (
        configure_host_env.shared_oauth_credential_secret(production, staging)
        == "shared-secret"
    )
    staging["PWC_HF_OAUTH_CREDENTIAL_SECRET"] = (
        "PWC_HF_OAUTH_CREDENTIAL_SECRET=other-secret"
    )
    with pytest.raises(ValueError, match="differs"):
        configure_host_env.shared_oauth_credential_secret(production, staging)


def test_deployed_runtime_rejects_relative_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.runtime_data_dir = "./runtime"
    with pytest.raises(RuntimeError, match="must be absolute"):
        validate_runtime(settings)


def test_staging_runtime_rejects_directory_snapshot_feature(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_workspace_snapshots_enabled = True
    with pytest.raises(RuntimeError, match="snapshots must remain disabled"):
        validate_runtime(settings)


def test_staging_blank_pool_requires_persistent_workers(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_enabled = True
    settings.chat_persistent_worker_enabled = False
    with pytest.raises(RuntimeError, match="blank pool requires persistent workers"):
        validate_runtime(settings)


def test_staging_blank_pool_rejects_inverted_capacity(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_blank_pool_min = 2
    settings.chat_blank_pool_max = 1
    with pytest.raises(RuntimeError, match="capacity must be"):
        validate_runtime(settings)


def test_production_rejects_blank_pool_activation(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_blank_pool_enabled = True
    with pytest.raises(
        RuntimeError, match="active or incomplete chat runtime descriptor"
    ):
        validate_runtime(settings)


def test_disabled_production_accepts_complete_dormant_worker_descriptor(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")

    assert settings.chat_enabled is False
    assert settings.chat_public_admission_enabled is False
    assert settings.chat_sandbox_admission_enabled is False
    assert settings.chat_blank_pool_enabled is False
    assert settings.chat_new_chat_modal_percentage == 0
    assert settings.chat_default_backend == "modal_cli"
    assert validate_runtime(settings) == profile_features("production")


def test_disabled_production_accepts_armed_configuration_for_atomic_rollback(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_max_concurrency = 2
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
    settings.chat_sandbox_cpu_limit = 1
    settings.chat_sandbox_memory_limit_mib = 2048
    settings.chat_sandbox_modal_environment = "pwc-chat-production"
    settings.chat_sandbox_provider_mode = "team_environments"
    settings.chat_sandbox_environment_cap_microusd = 125_000_000
    settings.chat_sandbox_modal_workspace = "paperswithcode"
    settings.chat_sandbox_modal_owner_username = "nielsrogge"
    settings.chat_sandbox_budget_attestation = (
        "modal-workspace-paperswithcode-250-production-125-v1"
    )
    settings.chat_sandbox_slack_webhook_url = (
        "https://hooks.slack.test/services/production"
    )
    settings.chat_sandbox_alert_fallback_webhook_url = (
        "https://alerts.test/production-fallback"
    )
    settings.chat_sandbox_runbook_url = "https://example.test/production-runbook"
    settings.chat_sandbox_operator_usernames = "nielsr"
    settings.chat_operational_alerts_enabled = True
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    configure_hf_scope_and_title(settings, "production")

    assert settings.chat_enabled is False
    assert settings.chat_new_chat_modal_percentage == 0
    assert settings.chat_public_admission_enabled is False
    assert settings.chat_sandbox_admission_enabled is False
    assert settings.chat_blank_pool_enabled is False
    assert validate_runtime(settings) == profile_features("production")


def test_disabled_legacy_production_rejects_armed_configuration(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_default_backend = "local_mcp"
    settings.chat_modal_image_version = ""
    settings.chat_pwc_cli_version = ""
    settings.chat_worker_contract_version = ""
    settings.chat_system_prompt_sha256 = ""
    settings.chat_title_generation_enabled = True

    with pytest.raises(RuntimeError, match="legacy production"):
        validate_runtime(settings)


def test_disabled_bridge_releases_can_replace_legacy_production_safely():
    legacy = {
        "chat_runtime": {
            "enabled": False,
            "gateway_contract_version": 1,
            "gateway_compatible_from": 1,
            "database_contract_version": 1,
        }
    }
    first_bridge = build_manifest("a" * 40, "production")
    second_bridge = build_manifest("b" * 40, "production")

    validate_rolling_compatibility(legacy, first_bridge)
    validate_rolling_compatibility(first_bridge, second_bridge)


def test_hf_catalog_gateway_upgrade_has_one_explicit_fail_closed_rollback():
    active = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 26,
            "gateway_compatible_from": 26,
            "database_contract_version": 1,
        }
    }
    candidate = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 27,
            "gateway_compatible_from": 26,
            "database_contract_version": 1,
        }
    }
    validate_rolling_compatibility(active, candidate)
    candidate["chat_runtime"]["gateway_contract_version"] = 28
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(active, candidate)


def test_pi_upgrade_allows_only_zero_assignment_additive_bridge():
    active = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 27,
            "gateway_compatible_from": 26,
            "database_contract_version": 1,
        }
    }
    candidate = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 28,
            "gateway_compatible_from": 27,
            "database_contract_version": 2,
            "supported_agent_harnesses": ["claude", "pi"],
            "default_agent_harness": "claude",
            "new_session_pi_percentage": 0,
        }
    }
    validate_rolling_compatibility(active, candidate)

    candidate["chat_runtime"]["new_session_pi_percentage"] = 100
    candidate["chat_runtime"]["default_agent_harness"] = "pi"
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(active, candidate)


def test_posterly_gateway_upgrade_requires_zero_assignment_bridge():
    active = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 28,
            "gateway_compatible_from": 27,
            "database_contract_version": 2,
        }
    }
    bridge = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 29,
            "gateway_compatible_from": 28,
            "database_contract_version": 2,
            "posterly_enabled": False,
        }
    }
    validate_rolling_compatibility(active, bridge)

    armed = {"chat_runtime": {**bridge["chat_runtime"], "posterly_enabled": True}}
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(active, armed)
    validate_rolling_compatibility(bridge, armed)


def test_direct_openai_gateway_upgrade_requires_zero_assignment_bridge():
    active = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 29,
            "gateway_compatible_from": 28,
            "database_contract_version": 2,
        }
    }
    bridge = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 30,
            "gateway_compatible_from": 29,
            "database_contract_version": 2,
            "direct_openai_enabled": False,
        }
    }
    validate_rolling_compatibility(active, bridge)

    armed = {"chat_runtime": {**bridge["chat_runtime"], "direct_openai_enabled": True}}
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(active, armed)
    validate_rolling_compatibility(bridge, armed)


def test_disabled_pi_gateway_bridge_can_open_only_with_zero_assignment():
    active = {
        "chat_runtime": {
            "enabled": False,
            "gateway_contract_version": 28,
            "gateway_compatible_from": 27,
            "database_contract_version": 1,
        }
    }
    candidate = {
        "chat_runtime": {
            "enabled": True,
            "gateway_contract_version": 28,
            "gateway_compatible_from": 27,
            "database_contract_version": 2,
            "supported_agent_harnesses": ["claude", "pi"],
            "default_agent_harness": "claude",
            "new_session_pi_percentage": 0,
        }
    }

    validate_rolling_compatibility(active, candidate)
    candidate["chat_runtime"]["new_session_pi_percentage"] = 100
    candidate["chat_runtime"]["default_agent_harness"] = "pi"
    with pytest.raises(ValueError, match="database contracts"):
        validate_rolling_compatibility(active, candidate)


def test_deployed_runtime_rejects_source_shell(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "index.html").write_text(
        '<script type="module" src="/src/main.tsx"></script>'
    )
    with pytest.raises(RuntimeError, match="/src/main.tsx"):
        validate_runtime(deployed_settings(tmp_path, release, "production"))


def test_staging_runtime_rejects_public_gateway_origin(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_gateway_url = (
        "https://staging.paperswithcode.co/api/internal/chat-gateway"
    )
    with pytest.raises(RuntimeError, match="dedicated HTTPS origin"):
        validate_runtime(settings)
