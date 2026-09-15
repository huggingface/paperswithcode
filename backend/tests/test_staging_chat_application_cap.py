"""The approved application-only raise must remain confined to staging."""

from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.scripts.manage_chat_sandbox_circuit import reviewed_higher_caps_allowed
from backend.services.runtime_validation import validate_chat_capacity_and_spend_policy
from backend.tests.test_deployment_runtime import deployed_settings, make_bundle
from deploy.configure_host_env import decoded_value
from deploy.configure_staging_chat_application_cap import raised_values

OLD = "modal-workspace-nielsrogge-250-staging-starter-v1"
NEW = "modal-workspace-nielsrogge-250-staging-starter-app105-v2"


def policy():
    return Settings(
        _env_file=None,
        environment="staging",
        chat_sandbox_provider_mode="starter_workspace",
        chat_sandbox_modal_workspace="nielsrogge",
        chat_sandbox_warning_microusd=75_000_000,
        chat_sandbox_application_cap_microusd=105_000_000,
        chat_sandbox_environment_cap_microusd=0,
        chat_sandbox_workspace_cap_microusd=250_000_000,
        chat_sandbox_budget_attestation=NEW,
    )


def test_exact_application_only_raise():
    state = SimpleNamespace(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=0,
        workspace_cap_microusd=250_000_000,
        policy_attestation=OLD,
    )
    assert reviewed_higher_caps_allowed(state, policy())
    for field, value in [
        ("environment", "production"),
        ("chat_sandbox_provider_mode", "team_environments"),
        ("chat_sandbox_modal_workspace", "other"),
        ("chat_sandbox_budget_attestation", OLD),
        ("chat_sandbox_application_cap_microusd", 106_000_000),
        ("chat_sandbox_environment_cap_microusd", 250_000_000),
        ("chat_sandbox_workspace_cap_microusd", 300_000_000),
    ]:
        assert not reviewed_higher_caps_allowed(
            state, policy().model_copy(update={field: value})
        )
    state.application_cap_microusd = 99_000_000
    assert not reviewed_higher_caps_allowed(state, policy())


def test_runtime_accepts_105_only_with_exact_staging_attestation(tmp_path):
    settings = deployed_settings(tmp_path, make_bundle(tmp_path, chat=True), "staging")
    settings.chat_sandbox_application_cap_microusd = 105_000_000
    settings.chat_sandbox_budget_attestation = NEW
    validate_chat_capacity_and_spend_policy(settings)
    for field, value in [
        ("environment", "production"),
        ("chat_sandbox_modal_workspace", "other"),
        ("chat_sandbox_budget_attestation", OLD),
        ("chat_sandbox_warning_microusd", 76_000_000),
        ("chat_sandbox_application_cap_microusd", 106_000_000),
    ]:
        with pytest.raises(RuntimeError):
            validate_chat_capacity_and_spend_policy(
                settings.model_copy(update={field: value})
            )


def test_protected_installer_preserves_all_other_values():
    values = {
        "PWC_ENVIRONMENT": "staging",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": "nielsrogge",
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "0",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "starter_workspace",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": OLD,
        "PWC_UNRELATED": "preserved",
    }
    current = {key: f"{key}={value}" for key, value in values.items()}
    result = raised_values(current)
    changed = {key for key in current if current[key] != result[key]}
    assert changed == {
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
    }
    assert (
        decoded_value(result["PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD"])
        == "105000000"
    )
    assert decoded_value(result["PWC_CHAT_SANDBOX_BUDGET_ATTESTATION"]) == NEW
    for key in values:
        if key == "PWC_UNRELATED":
            continue
        with pytest.raises(ValueError):
            raised_values({**current, key: f"{key}=unreviewed"})
