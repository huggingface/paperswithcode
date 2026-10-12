"""Chat configuration composition and the typed model registry."""

from __future__ import annotations

import pytest

from backend.chat_configuration import settings as chat_settings
from backend.chat_configuration.registry import ChatModelRecord
from backend.config import Settings
from backend.services import runtime_validation

GROUPS = [
    chat_settings.ChatSessionSettings,
    chat_settings.ChatModelSettings,
    chat_settings.ChatOpenAIBudgetSettings,
    chat_settings.ChatOpenRouterSettings,
    chat_settings.ChatScopeGuardrailSettings,
    chat_settings.ChatTitleSettings,
    chat_settings.ChatAdmissionSettings,
    chat_settings.ChatRuntimeSettings,
    chat_settings.ChatExternalPiSettings,
    chat_settings.ChatArtifactSettings,
    chat_settings.ChatToolSettings,
    chat_settings.ChatSandboxSettings,
    chat_settings.ChatSandboxSpendSettings,
    chat_settings.ChatOperationalAlertSettings,
    chat_settings.ChatGatewaySettings,
    chat_settings.ChatObservabilitySettings,
]


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_every_chat_field_has_exactly_one_focused_owner():
    owners: dict[str, list[str]] = {}
    for group in GROUPS:
        for name in group.__annotations__:
            owners.setdefault(name, []).append(group.__name__)

    chat_fields = {name for name in Settings.model_fields if name.startswith("chat_")}
    assert chat_fields == set(owners)
    assert all(len(groups) == 1 for groups in owners.values())
    # The root model declares only application-wide settings.
    assert not any(name.startswith("chat_") for name in Settings.__annotations__)


@pytest.mark.parametrize(
    ("variable", "field", "raw", "expected"),
    [
        ("PWC_CHAT_MAX_CONCURRENCY", "chat_max_concurrency", "7", 7),
        ("PWC_CHAT_TITLE_MAX_TOKENS", "chat_title_max_tokens", "33", 33),
        (
            "PWC_CHAT_OPENROUTER_ROUTING_POLICY",
            "chat_openrouter_routing_policy",
            "latency",
            "latency",
        ),
        (
            "PWC_CHAT_GATEWAY_URL",
            "chat_gateway_url",
            "http://gw.test",
            "http://gw.test",
        ),
    ],
)
def test_flat_environment_variables_still_configure_grouped_fields(
    monkeypatch, variable, field, raw, expected
):
    monkeypatch.setenv(variable, raw)

    assert getattr(_settings(), field) == expected


def test_grouped_chat_validator_still_runs_on_the_root_settings():
    settings = _settings(environment="staging", chat_scope_guardrail_enabled=True)

    assert settings.chat_artifacts_enabled is True
    assert settings.chat_artifact_shared_preview_enabled is True


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("direct", [False, True])
def test_model_choices_are_typed_records_with_the_public_shape(environment, direct):
    settings = _settings(environment=environment, chat_openai_direct_enabled=direct)

    records = settings.chat_model_records
    assert records
    assert all(isinstance(record, ChatModelRecord) for record in records)
    assert settings.chat_model_registry == tuple(r.as_choice() for r in records)
    for record in records:
        assert settings.chat_route_providers[record.route] == record.provider
        assert settings.chat_route_protocols[record.route] == record.protocol
        assert settings.chat_route_funding_modes[record.route] == record.funding_mode
    if direct and environment != "development":
        assert records[0].protocol == "openai-responses"
        assert records[0].provider == "openai"


def test_retired_routes_stay_resolvable_but_hidden_from_discovery():
    settings = _settings(environment="production")
    discovered = {choice["route"] for choice in settings.chat_model_choices}

    for route in (settings.chat_glm_route, settings.chat_gemma_route):
        assert route not in discovered
        assert settings.chat_route_providers[route] == "openrouter"
        assert settings.chat_route_protocols[route] == "anthropic-messages"
    assert (
        settings.chat_model_routes["openai/gpt-5.6-terra"]
        == settings.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
    )


def test_runtime_validation_composes_focused_policies_in_a_fixed_order(monkeypatch):
    calls: list[str] = []
    profile = runtime_validation.ChatRuntimeProfile(
        runtime_validation.ChatRuntimeKind.LOCAL
    )

    def step(name, result=None):
        def record(*_args, **_kwargs):
            calls.append(name)
            return result

        monkeypatch.setattr(runtime_validation, name, record)

    for name in (
        "validate_deployment_identity",
        "validate_auth_configuration",
        "validate_runtime_storage",
        "validate_codex_jobs_configuration",
        "validate_environment_policy",
        "validate_private_paper_runtime",
        "validate_chat_provider_policy",
        "_validate_chat_capacity_and_spend_policy",
        "_validate_chat_openrouter_policy",
        "validate_release_manifest",
        "validate_deployed_mutation_policy",
    ):
        step(name)
    step("validate_external_pi_migration_policy", profile)
    step("validate_chat_runtime_descriptor", True)
    step("validate_frontend_dist", {"chat": True})
    settings = _settings(environment="production", release_id="release-1")

    assert runtime_validation.validate_runtime(settings) == {"chat": True}
    assert calls == [
        "validate_deployment_identity",
        "validate_auth_configuration",
        "validate_runtime_storage",
        "validate_codex_jobs_configuration",
        "validate_environment_policy",
        "validate_private_paper_runtime",
        "validate_external_pi_migration_policy",
        "validate_chat_runtime_descriptor",
        "validate_chat_provider_policy",
        "_validate_chat_capacity_and_spend_policy",
        "_validate_chat_openrouter_policy",
        "validate_release_manifest",
        "validate_deployed_mutation_policy",
        "validate_frontend_dist",
    ]


def test_each_runtime_policy_area_has_its_own_module():
    from backend.services.runtime_policies import (
        auth,
        chat_budget,
        chat_capacity,
        chat_gateway,
        chat_provider,
        chat_title,
        deployment,
        schema,
        storage,
    )

    owners = {
        runtime_validation.validate_auth_configuration: auth,
        runtime_validation.validate_runtime_storage: storage,
        runtime_validation.validate_deployment_identity: deployment,
        runtime_validation.validate_chat_provider_policy: chat_provider,
        runtime_validation._validate_chat_capacity_policy: chat_capacity,
        runtime_validation._validate_chat_capacity_and_spend_policy: chat_budget,
        runtime_validation.validate_chat_schema: schema,
    }
    for function, module in owners.items():
        assert function.__module__ == module.__name__
    assert (
        chat_gateway._validate_chat_gateway_policy.__module__ == chat_gateway.__name__
    )
    assert chat_title._validate_chat_title_policy.__module__ == chat_title.__name__
