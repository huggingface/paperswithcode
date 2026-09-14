import json
import time
from itertools import count
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.services import openrouter_budget_service
from backend.services import runtime_validation
from backend.tests.test_deployment_runtime import deployed_settings, make_bundle
from deploy.release import profile_features


_REAL_OPENROUTER_GUARDRAIL = openrouter_budget_service.validate_openrouter_guardrail


@pytest.fixture(autouse=True)
def _avoid_live_openrouter_guardrail(monkeypatch):
    monkeypatch.setattr(
        openrouter_budget_service,
        "validate_openrouter_guardrail",
        lambda _settings: None,
    )


@pytest.fixture
def settings_factory(tmp_path):
    sequence = count()

    def build(environment):
        root = tmp_path / f"{environment}-{next(sequence)}"
        release = make_bundle(root, chat=environment == "staging")
        settings = deployed_settings(root, release, environment)
        return settings, release

    return build


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployment_identity_isolated_from_auth(settings_factory, environment):
    settings, _release = settings_factory(environment)
    settings.jwt_secret = ""

    runtime_validation.validate_deployment_identity(settings)

    settings.environment = "preview"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_deployment_identity(settings)
    assert str(exc_info.value) == "PWC_ENVIRONMENT must be production or staging"


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_auth_configuration_isolated_from_storage(settings_factory, environment):
    settings, _release = settings_factory(environment)
    settings.runtime_data_dir = "./invalid-runtime"

    runtime_validation.validate_auth_configuration(settings)

    settings.jwt_secret = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_auth_configuration(settings)
    assert str(exc_info.value) == "PWC_JWT_SECRET is required"


def test_runtime_storage_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("production")
    settings.jwt_secret = ""

    runtime_validation.validate_runtime_storage(settings)

    settings.runtime_data_dir = "./invalid-runtime"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_runtime_storage(settings)
    assert str(exc_info.value) == (
        "PWC_RUNTIME_DATA_DIR must be absolute in deployed environments"
    )


def test_codex_jobs_configuration_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("staging")
    settings.jwt_secret = ""

    runtime_validation.validate_codex_jobs_configuration(settings)

    settings.codex_jobs_api_url = "https://paperswithcode.co/api/v1"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_codex_jobs_configuration(settings)
    assert str(exc_info.value) == (
        "staging Codex jobs must target https://staging.paperswithcode.co/api/v1"
    )


def test_scheduled_curation_requires_digest_pinned_worker_image(settings_factory):
    settings, _release = settings_factory("production")
    settings.codex_curation_scheduler_enabled = True
    settings.codex_curation_direct_apply_enabled = True
    settings.codex_curation_trace_upload_enabled = True
    settings.codex_curation_trace_hf_bucket_id = "example/private-traces"
    settings.codex_jobs_image = "ghcr.io/example/curator:latest"

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_codex_jobs_configuration(settings)

    assert str(exc_info.value) == (
        "scheduled paper curation requires an immutable curator image"
    )


def test_scheduled_curation_accepts_versioned_space_with_pinned_revision(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.codex_curation_scheduler_enabled = True
    settings.codex_curation_direct_apply_enabled = True
    settings.codex_curation_trace_upload_enabled = True
    settings.codex_curation_trace_hf_bucket_id = "example/private-traces"
    settings.codex_jobs_image = "hf.co/spaces/example/curator-0123456789ab"
    settings.codex_jobs_image_revision = "a" * 40

    runtime_validation.validate_codex_jobs_configuration(settings)


def test_autonomous_submission_callbacks_require_isolated_scoped_secret(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.autonomous_submission_enabled = True
    settings.autonomous_submission_callback_secret = "short"

    with pytest.raises(RuntimeError, match="separate strong secret"):
        runtime_validation.validate_codex_jobs_configuration(settings)

    settings.autonomous_submission_callback_secret = "s" * 32
    settings.autonomous_submission_callback_base_url = (
        "https://staging.paperswithcode.co/api/v1"
    )
    with pytest.raises(RuntimeError, match="production autonomous callbacks"):
        runtime_validation.validate_codex_jobs_configuration(settings)

    settings.autonomous_submission_callback_base_url = (
        "https://paperswithcode.co/api/v1"
    )
    runtime_validation.validate_codex_jobs_configuration(settings)


def test_chat_runtime_descriptor_classifies_enabled_dormant_and_legacy(
    settings_factory,
):
    enabled, _release = settings_factory("staging")
    assert runtime_validation.validate_chat_runtime_descriptor(enabled) is True

    dormant, _release = settings_factory("production")
    assert dormant.chat_default_backend == "modal_cli"
    assert runtime_validation.validate_chat_runtime_descriptor(dormant) is False

    prepared, _release = settings_factory("production")
    prepared.chat_persistent_worker_enabled = True
    assert runtime_validation.validate_chat_runtime_descriptor(prepared) is True

    legacy, _release = settings_factory("production")
    legacy.chat_default_backend = "local_mcp"
    legacy.chat_modal_image_version = ""
    legacy.chat_pwc_cli_version = ""
    legacy.chat_worker_contract_version = ""
    legacy.chat_system_prompt_sha256 = ""
    assert runtime_validation.validate_chat_runtime_descriptor(legacy) is False


def test_chat_runtime_descriptor_rejects_partial_and_armed_legacy_states(
    settings_factory,
):
    partial, _release = settings_factory("production")
    partial.chat_pwc_cli_version = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(partial)
    assert str(exc_info.value) == (
        "disabled production contains an active or incomplete chat runtime descriptor"
    )

    legacy, _release = settings_factory("production")
    legacy.chat_default_backend = "local_mcp"
    legacy.chat_modal_image_version = ""
    legacy.chat_pwc_cli_version = ""
    legacy.chat_worker_contract_version = ""
    legacy.chat_system_prompt_sha256 = ""
    legacy.chat_title_generation_enabled = True
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(legacy)
    assert str(exc_info.value) == (
        "legacy production cannot contain armed chat preparation"
    )


def test_chat_provider_policy_isolated_from_capacity(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_max_concurrency = 999

    runtime_validation.validate_chat_provider_policy(settings)

    settings.hf_oauth_credential_secret = ""
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_provider_policy(settings)
    assert str(exc_info.value) == (
        "enabled chat requires the Hugging Face OAuth authentication path"
    )


def test_external_pi_migration_switches_are_independent_and_fail_closed(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    assert settings.chat_external_pi_shadow_enabled is False
    assert settings.chat_external_pi_admission_enabled is False
    assert settings.chat_remote_workspace_tools_enabled is False
    assert settings.chat_sandbox_executor_enabled is False
    assert settings.chat_sandbox_executor_contract_version == ""
    assert settings.chat_remote_bash_enabled is False
    assert settings.chat_remote_read_enabled is False
    assert settings.chat_safe_cli_fast_path_enabled is False
    assert settings.chat_lazy_workspace_enabled is False
    assert settings.chat_durable_turn_dispatch_enabled is False
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"

    settings.chat_external_pi_admission_enabled = True
    with pytest.raises(RuntimeError, match="external Pi admission requires"):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_external_pi_admission_enabled = False
    settings.chat_safe_cli_fast_path_enabled = True
    with pytest.raises(
        RuntimeError, match="safe CLI fast path requires remote workspace tools"
    ):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)


def test_external_pi_shadow_worker_starts_at_eight_but_remains_configurable():
    defaults = Settings(_env_file=None)
    assert defaults.chat_external_pi_worker_max_sessions == 8
    assert defaults.chat_external_pi_supervisor_enabled is False
    assert defaults.chat_external_pi_heartbeat_seconds == 10
    assert defaults.chat_external_pi_lease_seconds == 30
    assert defaults.chat_external_pi_startup_timeout_seconds == 60
    assert defaults.chat_external_pi_drain_seconds == 60
    assert defaults.chat_external_pi_drain_poll_seconds == 1
    assert (
        Settings(
            _env_file=None, chat_external_pi_worker_max_sessions=32
        ).chat_external_pi_worker_max_sessions
        == 32
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_external_pi_worker_max_sessions=33)


def test_durable_turn_controls_keep_current_capacity_and_allow_100_qualification():
    defaults = Settings(_env_file=None)

    assert defaults.chat_durable_turn_dispatch_enabled is False
    assert defaults.chat_max_concurrency == 1
    assert defaults.chat_timeout_seconds == 180
    assert (
        Settings(_env_file=None, chat_max_concurrency=100).chat_max_concurrency == 100
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_max_concurrency=101)


def test_external_pi_shadow_can_be_armed_without_changing_chat_admission(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_shadow_enabled = True

    with pytest.raises(RuntimeError, match="external Pi worker endpoint"):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    assert settings.chat_external_pi_admission_enabled is False


def test_external_pi_endpoint_list_is_a_complete_runtime_configuration(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_worker_id = ""
    settings.chat_external_pi_worker_url = ""
    settings.chat_external_pi_worker_token = ""
    settings.chat_external_pi_worker_endpoints = [
        {
            "endpoint_id": "blue",
            "worker_id": "worker-blue",
            "base_url": "http://127.0.0.1:8780",
            "token": "b" * 32,
        },
        {
            "endpoint_id": "green",
            "worker_id": "worker-green",
            "base_url": "http://[::1]:8781",
            "token": "g" * 32,
        },
    ]

    runtime_validation.validate_external_pi_migration_policy(settings)


def test_external_pi_endpoint_list_rejects_unknown_configuration_keys(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_worker_endpoints = [
        {
            "endpoint_id": "blue",
            "worker_id": "worker-blue",
            "base_url": "http://127.0.0.1:8780",
            "token": "b" * 32,
            "unexpected": "must-fail",
        }
    ]

    with pytest.raises(RuntimeError, match="external Pi worker"):
        runtime_validation.validate_external_pi_migration_policy(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("base_url", "https://127.0.0.1:8780"),
        ("base_url", "http://worker.internal:8780"),
        ("base_url", "http://127.0.0.1:8780/path"),
        ("token", "short"),
    ),
)
def test_external_pi_runtime_validates_every_list_endpoint(
    settings_factory, field, value
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    endpoint = {
        "endpoint_id": "blue",
        "worker_id": "worker-blue",
        "base_url": "http://127.0.0.1:8780",
        "token": "b" * 32,
    }
    endpoint[field] = value
    settings.chat_external_pi_worker_endpoints = [endpoint]

    with pytest.raises(RuntimeError, match="external Pi worker"):
        runtime_validation.validate_external_pi_migration_policy(settings)


@pytest.mark.parametrize(
    "duplicate_field", ("endpoint_id", "worker_id", "base_url", "token")
)
def test_external_pi_runtime_rejects_ambiguous_endpoint_list(
    settings_factory, duplicate_field
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_shadow_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    first = {
        "endpoint_id": "blue",
        "worker_id": "worker-blue",
        "base_url": "http://127.0.0.1:8780",
        "token": "b" * 32,
    }
    second = {
        "endpoint_id": "green",
        "worker_id": "worker-green",
        "base_url": "http://127.0.0.1:8781",
        "token": "g" * 32,
    }
    second[duplicate_field] = first[duplicate_field]
    settings.chat_external_pi_worker_endpoints = [first, second]

    with pytest.raises(RuntimeError, match="topology is ambiguous"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_external_pi_runtime_rejects_mixed_list_and_legacy_configuration(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_shadow_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_worker_endpoints = [
        {
            "endpoint_id": "blue",
            "worker_id": "worker-blue",
            "base_url": "http://127.0.0.1:8780",
            "token": "b" * 32,
        }
    ]
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"

    with pytest.raises(RuntimeError, match="topology is ambiguous"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_external_pi_runtime_keeps_complete_legacy_singleton_compatible_and_rejects_partial(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_shadow_enabled = True
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_token = "l" * 32

    runtime_validation.validate_external_pi_migration_policy(settings)

    settings.chat_external_pi_worker_token = ""
    with pytest.raises(RuntimeError, match="topology is incomplete"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_production_external_pi_requires_complete_authenticated_topology(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.chat_external_pi_shadow_enabled = True

    with pytest.raises(RuntimeError, match="topology is incomplete"):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)


def _configure_durable_external_admission_resource_profile(settings):
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8776"
    settings.chat_external_pi_worker_id = "production-blue"
    settings.chat_external_pi_worker_token = "p" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_shadow_enabled = True
    settings.chat_external_pi_admission_enabled = True
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_durable_turn_dispatch_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True
    settings.chat_max_concurrency = 32
    settings.chat_user_max_concurrency = 1
    settings.chat_sandbox_total_live_cap = 16
    settings.chat_openai_global_max_concurrency = 32
    settings.chat_openai_user_max_concurrency = 1
    settings.chat_openai_global_rate_limit_calls = 512
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-only"
    settings.chat_blank_pool_enabled = False
    settings.chat_pi_prewarm_enabled = False


def test_production_accepts_complete_durable_external_contract(settings_factory):
    settings, _release = settings_factory("production")
    _configure_durable_external_admission_resource_profile(settings)

    runtime_validation.validate_external_pi_migration_policy(settings)
    runtime_validation._validate_chat_capacity_policy(settings)
    runtime_validation._validate_chat_resource_policy(settings)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("chat_openai_global_max_concurrency", 4),
        ("chat_openai_user_max_concurrency", 2),
        ("chat_openai_global_rate_limit_calls", 80),
    ),
)
def test_production_rejects_durable_external_provider_capacity_drift(
    settings_factory, field, invalid
):
    settings, _release = settings_factory("production")
    _configure_durable_external_admission_resource_profile(settings)
    setattr(settings, field, invalid)

    with pytest.raises(RuntimeError, match="one direct-Luna low-reasoning warm blank"):
        runtime_validation._validate_chat_resource_policy(settings)


def test_staging_can_qualify_durable_bridge_without_external_admission(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_durable_turn_dispatch_enabled = True

    runtime_validation.validate_external_pi_migration_policy(settings)

    assert settings.chat_external_pi_admission_enabled is False


def test_deployed_runtime_allows_disabled_executor_bridge_and_staging_qualification(
    settings_factory,
):
    production, _release = settings_factory("production")
    runtime_validation.validate_runtime(production)

    staging, _release = settings_factory("staging")
    staging.chat_sandbox_executor_enabled = True
    staging.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    staging.chat_remote_bash_enabled = True
    staging.chat_remote_read_enabled = True

    runtime_validation.validate_runtime(staging)

    assert staging.chat_external_pi_admission_enabled is False


def test_executor_bridge_contract_does_not_admit_external_pi(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True

    runtime_validation.validate_external_pi_migration_policy(settings)

    assert settings.chat_external_pi_admission_enabled is False


def test_external_pi_admission_requires_the_executor_bridge(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_admission_enabled = True
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_durable_turn_dispatch_enabled = True

    with pytest.raises(RuntimeError, match="sandbox executor with Bash and Read"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_external_pi_admission_requires_durable_bridge_and_exact_contracts(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_admission_enabled = True
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True

    with pytest.raises(RuntimeError, match="durable turn dispatch"):
        runtime_validation.validate_external_pi_migration_policy(settings)

    settings.chat_durable_turn_dispatch_enabled = True
    with pytest.raises(RuntimeError, match="complete durable runtime contract"):
        runtime_validation.validate_external_pi_migration_policy(settings)

    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    runtime_validation.validate_external_pi_migration_policy(settings)

    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v2"
    with pytest.raises(RuntimeError, match="sandbox executor contract"):
        runtime_validation.validate_external_pi_migration_policy(settings)


@pytest.mark.parametrize("authoring_mode", ["poster", "paper"])
def test_external_pi_startup_rejects_authoring_modes(settings_factory, authoring_mode):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_admission_enabled = True
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True
    settings.chat_durable_turn_dispatch_enabled = True
    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    settings.chat_artifacts_enabled = True
    if authoring_mode == "poster":
        settings.chat_posterly_enabled = True
    else:
        settings.chat_latex_paper_enabled = True
        settings.chat_latex_compiler_jobs_enabled = True

    with pytest.raises(RuntimeError, match="ordinary research only"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_external_pi_startup_keeps_exact_ordinary_research_deadline(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_admission_enabled = True
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True
    settings.chat_durable_turn_dispatch_enabled = True
    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    settings.chat_agent_timeout_seconds = 181

    with pytest.raises(RuntimeError, match="180-second deadline"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def _arm_persistent_executor_transport(settings):
    now_seconds = int(time.time())
    now_ms = now_seconds * 1_000
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_admission_enabled = True
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True
    settings.chat_durable_turn_dispatch_enabled = True
    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    settings.chat_executor_remote_transport_enabled = True
    settings.chat_executor_cell_id = "cell-v1"
    settings.chat_executor_admission_signing_key_file = (
        "/run/credentials/test/executor-admission-key"
    )
    settings.chat_executor_admission_signing_key_id = "admission-v1"
    settings.chat_executor_admission_key_not_before_ms = now_ms - 1_000
    settings.chat_executor_admission_key_not_after_ms = now_ms + 60_000
    settings.chat_executor_harness_key_id = "harness-v1"
    settings.chat_executor_authorization_key_id = "authorization-v1"
    settings.chat_executor_authorization_keys_json = (
        '{"current":{"key_id":"authorization-v1","public_key":"'
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",'
        f'"not_before":{now_seconds - 1},"not_after":{now_seconds + 60}'
        "}}"
    )


def test_persistent_executor_transport_is_default_off_and_parallelism_is_exact():
    settings = Settings(_env_file=None)
    assert settings.chat_executor_remote_transport_enabled is False
    assert settings.chat_executor_max_parallel_operations == 4

    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_executor_max_parallel_operations=5)


def test_persistent_executor_transport_requires_external_admission(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_executor_remote_transport_enabled = True

    with pytest.raises(RuntimeError, match="requires external Pi admission"):
        runtime_validation.validate_external_pi_migration_policy(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chat_workspace_snapshots_enabled", True),
        ("chat_tool_result_max_bytes", 24 * 1024 + 1),
        ("chat_turn_tool_output_max_bytes", 96 * 1024 + 1),
        ("chat_blank_pool_min_remaining_seconds", 239),
        ("chat_persistent_sandbox_lifetime_seconds", 86_399),
        ("chat_blank_pool_rotate_before_seconds", 3_599),
        ("chat_bash_timeout_seconds", 29),
    ],
)
def test_persistent_executor_transport_rejects_release_limit_drift(
    settings_factory, field, value
):
    settings, _release = settings_factory("staging")
    _arm_persistent_executor_transport(settings)
    setattr(settings, field, value)

    with pytest.raises(RuntimeError, match="limits are inconsistent|rejects snapshots"):
        runtime_validation.validate_external_pi_migration_policy(settings)


def test_persistent_executor_transport_accepts_only_fully_armed_ordinary_mode(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    _arm_persistent_executor_transport(settings)

    runtime_validation.validate_external_pi_migration_policy(settings)


def test_persistent_executor_transport_requires_runtime_credentials(settings_factory):
    settings, _release = settings_factory("staging")
    _arm_persistent_executor_transport(settings)
    settings.chat_executor_admission_signing_key_file = ""

    with pytest.raises(RuntimeError, match="systemd credential configuration"):
        runtime_validation.validate_external_pi_migration_policy(settings)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_executor_bridge_environment_examples_remain_disabled(environment):
    source = Path(f"deploy/env/{environment}.env.example").read_text()

    assert "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED=false\n" in source
    assert "PWC_CHAT_EXECUTOR_REMOTE_TRANSPORT_ENABLED=false\n" in source
    assert "PWC_CHAT_EXECUTOR_MAX_PARALLEL_OPERATIONS=4\n" in source
    assert "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION=\n" in source
    assert "PWC_CHAT_REMOTE_BASH_ENABLED=false\n" in source
    assert "PWC_CHAT_REMOTE_READ_ENABLED=false\n" in source


def test_external_pi_supervisor_requires_a_safe_heartbeat_lease_ratio(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    settings.chat_external_pi_worker_id = "worker-legacy"
    settings.chat_external_pi_worker_token = "s" * 32
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_external_pi_heartbeat_seconds = 30
    settings.chat_external_pi_lease_seconds = 30

    with pytest.raises(RuntimeError, match="heartbeat must be shorter than the lease"):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_external_pi_heartbeat_seconds = 29
    runtime_validation.validate_chat_capacity_and_spend_policy(settings)


def test_environment_policy_isolated_from_storage(settings_factory):
    settings, _release = settings_factory("production")
    settings.runtime_data_dir = "./invalid-runtime"

    runtime_validation.validate_environment_policy(settings)

    settings.catalog_mutations_enabled = False
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_environment_policy(settings)
    assert str(exc_info.value) == (
        "production catalog mutations and CRON must remain enabled"
    )


def test_chat_provider_policy_accepts_isolated_production_openrouter(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )

    runtime_validation.validate_chat_provider_policy(settings)


def test_chat_provider_policy_accepts_one_reviewed_staging_candidate(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_alternative_model_enabled = True
    settings.chat_alternative_model = "openai/gpt-5.6-luna"
    settings.chat_pi_prewarm_model = "openai/gpt-5.6-luna"

    runtime_validation.validate_chat_provider_policy(settings)
    runtime_validation.validate_chat_capacity_and_spend_policy(settings)


def test_direct_openai_requires_gateway_key_and_accepts_production(settings_factory):
    staging, _release = settings_factory("staging")
    staging.chat_openai_direct_enabled = True
    staging.openai_api_key = ""
    with pytest.raises(RuntimeError, match="requires an OpenAI API key"):
        runtime_validation.validate_chat_provider_policy(staging)

    production, _release = settings_factory("production")
    production.chat_openai_direct_enabled = True
    production.openai_api_key = "test-only"
    production.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    production.chat_pi_prewarm_enabled = True
    production.chat_pi_prewarm_model = production.chat_openai_luna_route

    runtime_validation.validate_chat_provider_policy(production)


def test_direct_openai_requires_exact_low_reasoning_warm_profile(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-only"
    settings.chat_pi_prewarm_enabled = True
    settings.chat_default_agent_harness = "pi"
    settings.chat_pi_prewarm_model = settings.chat_openai_luna_route
    settings.chat_pi_prewarm_reasoning_effort = "low"

    runtime_validation.validate_chat_provider_policy(settings)
    runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_pi_prewarm_reasoning_effort = "high"
    with pytest.raises(RuntimeError, match="one direct-Luna low-reasoning warm blank"):
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)


def _durable_external_qualification_resource_profile(settings):
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-only"
    settings.chat_blank_pool_enabled = False
    settings.chat_pi_prewarm_enabled = False
    settings.chat_external_pi_admission_enabled = False
    settings.chat_external_pi_supervisor_enabled = True
    settings.chat_external_pi_ready_registry_enabled = True
    settings.chat_external_pi_runtime_contract_version = "durable-external-pi-v1"
    settings.chat_external_pi_worker_contract_version = "external-pi-v1"
    settings.chat_durable_turn_dispatch_enabled = True
    settings.chat_turn_event_journal_schema_enabled = True
    settings.chat_sandbox_executor_enabled = True
    settings.chat_sandbox_executor_contract_version = "sandbox-executor-v1"
    settings.chat_remote_workspace_tools_enabled = True
    settings.chat_remote_bash_enabled = True
    settings.chat_remote_read_enabled = True
    settings.chat_lazy_workspace_enabled = True
    settings.chat_max_concurrency = 2
    settings.chat_sandbox_total_live_cap = 3
    return settings


def test_direct_openai_accepts_only_complete_staging_durable_qualification_profile(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    _durable_external_qualification_resource_profile(settings)

    runtime_validation._validate_chat_resource_policy(settings)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("environment", "production"),
        ("chat_external_pi_admission_enabled", True),
        ("chat_external_pi_supervisor_enabled", False),
        ("chat_external_pi_ready_registry_enabled", False),
        ("chat_external_pi_runtime_contract_version", ""),
        ("chat_external_pi_worker_contract_version", ""),
        ("chat_durable_turn_dispatch_enabled", False),
        ("chat_turn_event_journal_schema_enabled", False),
        ("chat_sandbox_executor_enabled", False),
        ("chat_sandbox_executor_contract_version", ""),
        ("chat_remote_workspace_tools_enabled", False),
        ("chat_remote_bash_enabled", False),
        ("chat_remote_read_enabled", False),
        ("chat_lazy_workspace_enabled", False),
        ("chat_max_concurrency", 3),
        ("chat_sandbox_total_live_cap", 4),
    ),
)
def test_direct_openai_rejects_partial_or_nonstaging_durable_qualification_profile(
    settings_factory, field, invalid
):
    settings, _release = settings_factory("staging")
    _durable_external_qualification_resource_profile(settings)
    setattr(settings, field, invalid)

    with pytest.raises(RuntimeError, match="one direct-Luna low-reasoning warm blank"):
        runtime_validation._validate_chat_resource_policy(settings)


def test_chat_provider_policy_rejects_unreviewed_kimi_route(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_kimi_route = "moonshotai/Kimi-K3:fastest"

    with pytest.raises(RuntimeError, match="reviewed Hugging Face route"):
        runtime_validation.validate_chat_provider_policy(settings)


def test_chat_provider_policy_rejects_unreviewed_luna_route(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_luna_route = "openai/gpt-5.6-terra"

    with pytest.raises(RuntimeError, match="reviewed OpenAI route"):
        runtime_validation.validate_chat_provider_policy(settings)


def test_chat_provider_policy_rejects_alternative_model_in_production(
    settings_factory,
):
    settings, _release = settings_factory("production")
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    settings.chat_alternative_model_enabled = True

    with pytest.raises(RuntimeError, match="staging-only"):
        runtime_validation.validate_chat_provider_policy(settings)


def test_chat_provider_policy_rejects_empty_preferred_provider_order(
    settings_factory,
):
    settings, _release = settings_factory("staging")
    settings.chat_openrouter_routing_enabled = True
    settings.chat_openrouter_routing_policy = "preferred_provider"
    settings.chat_openrouter_preferred_providers = ""

    with pytest.raises(RuntimeError, match="requires valid provider slugs"):
        runtime_validation.validate_chat_provider_policy(settings)


def test_chat_capacity_and_spend_policy_isolated_from_provider(settings_factory):
    settings, _release = settings_factory("staging")
    settings.hf_oauth_credential_secret = ""

    runtime_validation.validate_chat_capacity_and_spend_policy(settings)

    settings.chat_sandbox_warning_microusd = 1
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)
    assert str(exc_info.value) == (
        "sandbox spend policy must be $75/$100/$250 with no environment cap"
    )


def test_chat_descriptor_owns_immutable_runtime_identity(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_workspace_snapshots_enabled = True

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_runtime_descriptor(settings)
    assert str(exc_info.value) == "directory snapshots must remain disabled"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "chat_gateway_url",
            "https://paperswithcode.co/api/internal/chat-gateway",
            "chat gateway must use chat-gateway-staging.paperswithcode.co",
        ),
        (
            "chat_openrouter_api_key",
            "",
            "server-funded OpenRouter chat requires an OpenRouter key",
        ),
    ],
)
def test_chat_provider_policy_owns_gateway_and_openrouter(
    settings_factory, field, value, message
):
    settings, _release = settings_factory("staging")
    setattr(settings, field, value)

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_provider_policy(settings)
    assert str(exc_info.value) == message


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "chat_title_hf_token",
            "",
            "an HF GLM title credential is required",
        ),
        (
            "chat_sandbox_cpu_limit",
            0.5,
            "chat CPU limit is below its request",
        ),
        (
            "chat_persistent_worker_enabled",
            False,
            "blank pool requires persistent workers",
        ),
    ],
)
def test_chat_capacity_policy_owns_title_resources_and_pool(
    settings_factory, field, value, message
):
    settings, _release = settings_factory("staging")
    setattr(settings, field, value)

    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_chat_capacity_and_spend_policy(settings)
    assert str(exc_info.value) == message


def test_runtime_finishes_local_chat_policy_before_openrouter_guardrail(
    settings_factory, monkeypatch
):
    settings, _release = settings_factory("staging")
    calls = []

    def provider(_settings, *, include_openrouter):
        assert include_openrouter is False
        calls.append("provider")

    monkeypatch.setattr(runtime_validation, "validate_chat_provider_policy", provider)

    def capacity(_settings):
        calls.append("capacity")

    monkeypatch.setattr(
        runtime_validation, "_validate_chat_capacity_and_spend_policy", capacity
    )
    monkeypatch.setattr(
        runtime_validation,
        "_validate_chat_openrouter_policy",
        lambda _settings: calls.append("openrouter"),
    )

    runtime_validation.validate_runtime(settings)

    assert calls == ["provider", "capacity", "openrouter"]


@pytest.mark.parametrize("key", ["", "revoked-production-key"])
def test_production_direct_routes_allow_admission_without_openrouter(
    settings_factory, monkeypatch, key
):
    settings, _release = settings_factory("production")
    settings.chat_openai_direct_enabled = True
    settings.chat_public_admission_enabled = True
    settings.chat_sandbox_admission_enabled = True
    settings.chat_openrouter_server_funded_enabled = False
    settings.chat_openrouter_api_key = key
    monkeypatch.setattr(
        openrouter_budget_service,
        "validate_openrouter_guardrail",
        _REAL_OPENROUTER_GUARDRAIL,
    )

    def unexpected_provider_call(*args, **kwargs):
        pytest.fail("Direct OpenAI/HF startup must not contact OpenRouter")

    monkeypatch.setattr(
        openrouter_budget_service.httpx, "Client", unexpected_provider_call
    )

    assert [choice["funding_mode"] for choice in settings.chat_model_registry] == [
        "openai_funded",
        "hf_user_billed",
    ]
    runtime_validation._validate_chat_openrouter_policy(settings)


def test_production_funded_openrouter_still_requires_provider_guardrail(
    settings_factory, monkeypatch
):
    settings, _release = settings_factory("production")
    settings.chat_public_admission_enabled = True
    settings.chat_openrouter_server_funded_enabled = True

    def rejected_key(_settings):
        raise openrouter_budget_service.OpenRouterBudgetUnavailable("rejected key")

    monkeypatch.setattr(
        openrouter_budget_service, "validate_openrouter_guardrail", rejected_key
    )
    with pytest.raises(RuntimeError, match="provider-enforced guardrail is invalid"):
        runtime_validation._validate_chat_openrouter_policy(settings)


def test_runtime_validates_external_migration_policy_exactly_once(
    settings_factory, monkeypatch
):
    settings, _release = settings_factory("staging")
    original = runtime_validation.validate_external_pi_migration_policy
    calls = 0

    def migration_policy(current_settings):
        nonlocal calls
        calls += 1
        original(current_settings)

    monkeypatch.setattr(
        runtime_validation,
        "validate_external_pi_migration_policy",
        migration_policy,
    )

    runtime_validation.validate_runtime(settings)

    assert calls == 1


def test_release_manifest_isolated_from_storage_and_tolerates_extra_keys(
    settings_factory,
):
    settings, release = settings_factory("production")
    settings.runtime_data_dir = "./invalid-runtime"
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["future_release_metadata"] = {"safe": True}
    manifest["chat_runtime"]["future_descriptor_field"] = "ignored"
    manifest_path.write_text(json.dumps(manifest))

    runtime_validation.validate_release_manifest(settings)

    settings.release_id = "different-release"
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_release_manifest(settings)
    assert str(exc_info.value) == (
        "running chat runtime differs from the release manifest"
    )


def test_frontend_dist_isolated_from_identity_and_preserves_exact_error(
    settings_factory,
):
    settings, release = settings_factory("production")
    settings.release_id = ""

    assert runtime_validation.validate_frontend_dist(settings) == profile_features(
        "production"
    )

    (release / "frontend-dist" / "index.html").write_text(
        '<script type="module" src="/src/main.tsx"></script>'
    )
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_frontend_dist(settings)
    assert str(exc_info.value) == ("deployed frontend shell references /src/main.tsx")


def test_deployed_mutation_policy_isolated_from_auth(settings_factory):
    settings, _release = settings_factory("production")
    settings.jwt_secret = ""

    runtime_validation.validate_deployed_mutation_policy(settings)

    settings.thumbnail_mutations_enabled = True
    with pytest.raises(RuntimeError) as exc_info:
        runtime_validation.validate_deployed_mutation_policy(settings)
    assert str(exc_info.value) == ("deployed web services must not mutate thumbnails")


def test_excalidraw_worker_and_host_kill_switches_must_match(settings_factory):
    settings, _release = settings_factory("staging")
    settings.chat_excalidraw_enabled = True
    settings.chat_mcp_apps_host_enabled = False

    with pytest.raises(RuntimeError, match="switches must match"):
        runtime_validation._validate_chat_resource_policy(settings)


@pytest.mark.parametrize(
    "environment,remote,pool_min,pool_max,live_cap,accepted",
    [
        ("staging", True, 1, 1, 16, True),
        ("staging", True, 4, 4, 16, True),
        ("staging", False, 4, 4, 16, False),
        ("production", True, 4, 4, 16, False),
        ("staging", True, 3, 3, 16, False),
        ("staging", True, 8, 8, 16, False),
        ("staging", True, 4, 1, 16, False),
        ("staging", True, 4, 4, 32, False),
    ],
)
def test_four_spare_profile_is_staging_persistent_only(
    environment, remote, pool_min, pool_max, live_cap, accepted
):
    settings = Settings(
        environment=environment,
        chat_external_pi_admission_enabled=True,
        chat_executor_remote_transport_enabled=remote,
        chat_max_concurrency=32,
        chat_user_max_concurrency=1,
        chat_sandbox_total_live_cap=live_cap,
        chat_blank_pool_min=pool_min,
        chat_blank_pool_max=pool_max,
    )
    if accepted:
        runtime_validation._validate_chat_capacity_policy(settings)
    else:
        with pytest.raises(RuntimeError, match="reviewed runtime profile"):
            runtime_validation._validate_chat_capacity_policy(settings)
