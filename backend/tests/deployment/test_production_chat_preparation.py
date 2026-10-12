"""Sealed production chat preparation, budgets, and bundle installation."""

from __future__ import annotations

from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env
import deploy.configure_production_chat_application_cap as configure_production_chat_application_cap
import deploy.configure_production_chat_budget as configure_production_chat_budget


def _production_chat_preparation_source() -> dict[str, str]:
    values = {
        "MODAL_TOKEN_ID": "modal-id",
        "MODAL_TOKEN_SECRET": "modal-secret",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": "paperswithcode",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME": "nielsrogge",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES": "root,nielsr",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "modal-workspace-paperswithcode-250-production-250-warn200-app225-v3"
        ),
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
            "https://alerts-primary.test/production"
        ),
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
            "https://alerts-fallback.test/production"
        ),
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_HF_TOKEN": "production-title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "production",
        "PWC_CHAT_OPENROUTER_API_KEY": "production-openrouter-secret",
    }
    return {key: f"{key}={value}" for key, value in values.items()}


def test_production_environment_example_exposes_sealed_preparation_contract():
    source = Path(__file__).resolve().parents[3]
    values = configure_host_env.read_lines(
        source / "deploy" / "env" / "production.env.example"
    )

    assert configure_host_env.decoded_value(values["PWC_CHAT_ENABLED"]) == "false"
    assert (
        configure_host_env.decoded_value(values["PWC_CHAT_PUBLIC_ADMISSION_ENABLED"])
        == "false"
    )
    assert (
        configure_host_env.decoded_value(values["PWC_CHAT_SANDBOX_ADMISSION_ENABLED"])
        == "false"
    )
    assert (
        configure_host_env.decoded_value(values["PWC_CHAT_BLANK_POOL_ENABLED"])
        == "false"
    )
    assert (
        configure_host_env.decoded_value(
            values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"]
        )
        == "false"
    )
    assert {
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_OPENROUTER_API_KEY",
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING",
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
    } <= values.keys()


def test_production_chat_preparation_is_sealed_and_fail_closed():
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )

    assert values["PWC_CHAT_ENABLED"] == "true"
    assert values["PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE"] == "100"
    assert values["PWC_CHAT_PUBLIC_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_SANDBOX_ADMISSION_ENABLED"] == "false"
    assert values["PWC_CHAT_BLANK_POOL_ENABLED"] == "false"
    assert values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"] == "false"
    assert values["PWC_CHAT_OPERATIONAL_ALERTS_ENABLED"] == "true"
    assert values["PWC_CHAT_PROVIDER_ALERT_WINDOW_SECONDS"] == "300"
    assert values["PWC_CHAT_PROVIDER_ALERT_MIN_FAILURES"] == "5"
    assert values["PWC_CHAT_PROVIDER_ALERT_FAILURE_PERCENT"] == "50"
    assert values["PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT"] == "pwc-chat-production"
    assert values["PWC_CHAT_SANDBOX_WARNING_MICROUSD"] == "200000000"
    assert values["PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD"] == "225000000"
    assert values["PWC_CHAT_SANDBOX_PROVIDER_MODE"] == "team_environments"
    assert values["PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD"] == "250000000"
    assert values["PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD"] == "250000000"
    assert values["PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD"] == "25000000"
    assert values["PWC_CHAT_TITLE_HF_TOKEN"] == "production-title-secret"
    assert values["PWC_CHAT_TITLE_MODEL"] == "zai-org/GLM-5.3-Flash:baseten"
    assert values["PWC_CHAT_TITLE_PROVIDER"] == "huggingface"
    assert values["PWC_CHAT_OPENROUTER_API_KEY"] == "production-openrouter-secret"
    assert values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] == "5.00"
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "200.00"
    assert values["PWC_CHAT_MAX_CONCURRENCY"] == "2"
    assert values["PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP"] == "3"


def test_production_chat_budget_alignment_is_narrow():
    current = {
        "PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=true",
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": (
            "PWC_CHAT_SANDBOX_WARNING_MICROUSD=75000000"
        ),
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD=100000000"
        ),
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD=125000000"
        ),
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD=250000000"
        ),
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": (
            "PWC_CHAT_SANDBOX_PROVIDER_MODE=team_environments"
        ),
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION="
            "modal-workspace-paperswithcode-250-production-125-v1"
        ),
        "PWC_UNRELATED": "PWC_UNRELATED=preserved",
    }

    updated = configure_production_chat_budget.aligned_values(current)

    assert (
        configure_host_env.decoded_value(
            updated["PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD"]
        )
        == "250000000"
    )
    assert (
        configure_host_env.decoded_value(updated["PWC_CHAT_SANDBOX_BUDGET_ATTESTATION"])
        == "modal-workspace-paperswithcode-250-production-250-v2"
    )
    assert updated["PWC_UNRELATED"] == current["PWC_UNRELATED"]


def test_production_application_cap_raise_is_narrow():
    current = {
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": (
            "PWC_CHAT_SANDBOX_WARNING_MICROUSD=75000000"
        ),
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD=100000000"
        ),
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD=250000000"
        ),
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": (
            "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD=250000000"
        ),
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": (
            "PWC_CHAT_SANDBOX_PROVIDER_MODE=team_environments"
        ),
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION="
            "modal-workspace-paperswithcode-250-production-250-v2"
        ),
        "PWC_UNRELATED": "PWC_UNRELATED=preserved",
    }

    updated = configure_production_chat_application_cap.raised_values(current)

    assert (
        configure_host_env.decoded_value(updated["PWC_CHAT_SANDBOX_WARNING_MICROUSD"])
        == "200000000"
    )
    assert (
        configure_host_env.decoded_value(
            updated["PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD"]
        )
        == "225000000"
    )
    assert (
        configure_host_env.decoded_value(
            updated["PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD"]
        )
        == "250000000"
    )
    assert (
        configure_host_env.decoded_value(
            updated["PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD"]
        )
        == "250000000"
    )
    assert updated["PWC_UNRELATED"] == current["PWC_UNRELATED"]


def test_production_modal_profile_is_imported_without_persisting_a_copy(
    tmp_path: Path,
):
    config = tmp_path / ".modal.toml"
    config.write_text(
        '[nielsrogge]\ntoken_id = "modal-id"\n'
        'token_secret = "modal-secret"\nactive = true\n'
    )
    config.chmod(0o600)
    source = {"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}

    updated = configure_host_env.production_modal_profile_source(
        source,
        config,
        "nielsrogge",
    )

    assert source == {"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}
    assert updated["MODAL_TOKEN_ID"] == "MODAL_TOKEN_ID=modal-id"
    assert updated["MODAL_TOKEN_SECRET"] == "MODAL_TOKEN_SECRET=modal-secret"


@pytest.mark.parametrize(
    ("mode", "profile", "source", "match"),
    [
        (0o644, "nielsrogge", {}, "group/world readable"),
        (0o600, "missing", {}, "profile is missing"),
        (
            0o600,
            "nielsrogge",
            {"MODAL_TOKEN_ID": "MODAL_TOKEN_ID=other"},
            "conflicts",
        ),
    ],
)
def test_production_modal_profile_rejects_unsafe_import(
    tmp_path: Path,
    mode: int,
    profile: str,
    source: dict[str, str],
    match: str,
):
    config = tmp_path / ".modal.toml"
    config.write_text(
        '[nielsrogge]\ntoken_id = "modal-id"\n'
        'token_secret = "modal-secret"\nactive = true\n'
    )
    config.chmod(mode)

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_modal_profile_source(
            source,
            config,
            profile,
        )


def test_production_chat_install_revalidates_exact_sealed_bundle():
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )
    sealed = {key: f"{key}={value}" for key, value in values.items()}

    assert (
        configure_host_env.production_chat_install_values(
            sealed,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
        )
        == values
    )


def test_production_chat_admission_requires_exact_installed_bundle():
    source = _production_chat_preparation_source()
    values = configure_host_env.production_chat_preparation_values(
        source,
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )
    sealed = {key: f"{key}={value}" for key, value in values.items()}
    current = {
        **{"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        **sealed,
    }

    assert configure_host_env.production_chat_admission_values(
        sealed,
        current,
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    ) == {
        "PWC_CHAT_PUBLIC_ADMISSION_ENABLED": "true",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "true",
    }

    drifted = dict(current)
    drifted["PWC_CHAT_BLANK_POOL_ENABLED"] = "PWC_CHAT_BLANK_POOL_ENABLED=true"
    with pytest.raises(ValueError, match="must change together"):
        configure_host_env.production_chat_admission_values(
            sealed,
            drifted,
            {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
        )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=false"}, "stale"),
        ({"UNREVIEWED_SECRET": "UNREVIEWED_SECRET=value"}, "unexpected"),
    ],
)
def test_production_chat_install_rejects_tampered_bundle(mutation, match):
    values = configure_host_env.production_chat_preparation_values(
        _production_chat_preparation_source(),
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=staging-secret"},
    )
    sealed = {key: f"{key}={value}" for key, value in values.items()}
    sealed.update(mutation)

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_chat_install_values(
            sealed,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {"PWC_CHAT_TITLE_HF_TOKEN": ("PWC_CHAT_TITLE_HF_TOKEN=staging-secret")},
        )


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("PWC_CHAT_OPENROUTER_API_KEY", "staging-secret", "must not reuse"),
        (
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
            "https://alerts-primary.test/production",
            "distinct",
        ),
        (
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
            "unattested",
            "does not match",
        ),
    ],
)
def test_production_chat_preparation_rejects_unsafe_inputs(key, value, match):
    source = _production_chat_preparation_source()
    source[key] = f"{key}={value}"

    with pytest.raises(ValueError, match=match):
        configure_host_env.production_chat_preparation_values(
            source,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {
                "PWC_CHAT_OPENROUTER_API_KEY": "PWC_CHAT_OPENROUTER_API_KEY=staging-secret"
            },
        )
