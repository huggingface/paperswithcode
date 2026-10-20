"""Release manifests, chat descriptors, feature profiles, and rollback targets."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.cli as deploy_cli
from backend.chat_sandbox_worker.contract import (
    MODAL_IMAGE_ID,
    PRODUCTION_MODAL_IMAGE_ID,
    WORKER_CONTRACT_VERSION,
)
from backend.services.runtime_validation import (
    validate_runtime,
)
from deploy.cli import (
    _chat_descriptor_from_source,
    _configured_chat_enabled,
    require_production_chat_monitor,
)
from deploy.release import (
    build_manifest,
    profile_features,
    validate_manifest,
)
from deploy.smoke_test import validate_local_bundle
from backend.tests.deployment.harness import (
    configure_hf_scope_and_title,
    deployed_settings,
    make_bundle,
)


def test_release_manifest_rejects_feature_mismatch(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    features = profile_features("production")
    features["codex_add_evals"] = False
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))
    with pytest.raises(ValueError, match="features.json"):
        validate_manifest(release, "production")


@pytest.mark.parametrize(
    ("environment", "version", "features"),
    [
        (
            "staging",
            2,
            {
                "chat": True,
                "codex_add_evals": False,
                "codex_enrich_paper": False,
            },
        ),
        (
            "production",
            3,
            {
                "chat": False,
                "codex_add_evals": True,
                "codex_enrich_paper": True,
            },
        ),
    ],
)
def test_pre_bridge_versioned_manifest_remains_valid(
    tmp_path: Path, environment: str, version: int, features: dict[str, bool]
):
    release = make_bundle(tmp_path, chat=environment == "staging")
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("chat_runtime")
    manifest["feature_contract_version"] = version
    manifest["backend_features"] = features
    manifest["frontend_features"] = features
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))

    assert (
        validate_manifest(release, environment)["release_id"] == manifest["release_id"]
    )


def test_staging_manifest_requires_immutable_modal_image(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"]["modal_image_version"] = "pwc-chat-v1"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="immutable Modal image ID"):
        validate_manifest(release, "staging")


def test_chat_descriptor_is_extracted_from_selected_source():
    source = Path(__file__).resolve().parents[3]
    descriptor = _chat_descriptor_from_source(source, "staging")
    assert descriptor["modal_image_version"] == MODAL_IMAGE_ID
    assert descriptor["worker_contract_version"] == WORKER_CONTRACT_VERSION
    assert descriptor["direct_openai_enabled"] is True
    assert descriptor["production_excalidraw_enabled"] is False
    dormant = _chat_descriptor_from_source(source, "production")
    assert dormant is not None
    assert dormant["enabled"] is False
    assert dormant["new_chat_modal_percentage"] == 0
    assert dormant["direct_openai_enabled"] is False
    assert dormant["production_excalidraw_enabled"] is False
    assert dormant["database_contract_version"] == 1
    assert dormant["system_prompt_sha256"] == descriptor["system_prompt_sha256"]
    production = _chat_descriptor_from_source(source, "production", chat_enabled=True)
    assert production["modal_image_version"] == PRODUCTION_MODAL_IMAGE_ID
    assert production["worker_contract_version"] == "104"
    assert production["enabled"] is True
    assert production["database_contract_version"] == 2
    assert production["default_agent_harness"] == "pi"
    assert production["new_session_pi_percentage"] == 100
    assert production["direct_openai_enabled"] is True
    assert production["production_excalidraw_enabled"] is True
    assert (
        production["new_chat_modal_percentage"]
        == descriptor["new_chat_modal_percentage"]
    )
    assert production["system_prompt_sha256"] == descriptor["system_prompt_sha256"]


def test_disabled_production_manifest_uses_selected_source_descriptor():
    source = Path(__file__).resolve().parents[3]
    descriptor = _chat_descriptor_from_source(source, "production", chat_enabled=False)
    assert descriptor is not None

    manifest = build_manifest("a" * 40, "production", chat_descriptor=descriptor)

    assert manifest["chat_runtime"] == descriptor
    assert manifest["backend_features"]["chat"] is False


def test_disabled_production_descriptor_supports_pre_pi_source(tmp_path: Path):
    source = tmp_path / "source"
    package = source / "backend" / "chat_sandbox_worker"
    package.mkdir(parents=True)
    (source / "backend" / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "contract.py").write_text(
        "\n".join(
            [
                "DATABASE_CONTRACT_VERSION = 1",
                'DEFAULT_BACKEND = "modal_cli"',
                "GATEWAY_COMPATIBLE_FROM = 26",
                "GATEWAY_CONTRACT_VERSION = 27",
                'MODAL_IMAGE_ID = "im-staging"',
                "NEW_CHAT_MODAL_PERCENTAGE = 100",
                'PRODUCTION_MODAL_IMAGE_ID = "im-production"',
                'PWC_CLI_VERSION = "0.1.12"',
                'WORKER_CONTRACT_VERSION = "59"',
            ]
        )
    )
    (package / "prompt.py").write_text('def sha256():\n    return "a" * 64\n')

    descriptor = _chat_descriptor_from_source(source, "production", chat_enabled=False)

    assert set(descriptor) == {
        "enabled",
        "new_chat_modal_percentage",
        "default_backend",
        "modal_image_version",
        "pwc_cli_version",
        "worker_contract_version",
        "gateway_contract_version",
        "gateway_compatible_from",
        "database_contract_version",
        "system_prompt_sha256",
    }
    assert descriptor["enabled"] is False
    assert descriptor["database_contract_version"] == 1


def test_production_chat_activation_builds_one_consistent_manifest(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "pdf.worker.min-abc123.js").write_text(
        "export {}"
    )
    sha = "a" * 40
    descriptor = _chat_descriptor_from_source(
        Path(__file__).resolve().parents[3],
        "production",
        chat_enabled=True,
    )
    assert descriptor is not None
    descriptor["modal_image_version"] = "im-test-immutable"
    features = profile_features("production", production_chat_enabled=True)
    manifest = build_manifest(
        sha,
        "production",
        chat_descriptor=descriptor,
        production_chat_enabled=True,
    )
    (release / "release.json").write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))

    validated = validate_manifest(release, "production")

    assert validated["backend_features"] == features
    assert validated["frontend_features"] == features
    assert validated["chat_runtime"]["enabled"] is True
    assert validate_local_bundle(release, validated["frontend_features"]) == []


def test_v6_production_chat_release_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    descriptor = _chat_descriptor_from_source(
        Path(__file__).resolve().parents[3],
        "production",
        chat_enabled=True,
    )
    assert descriptor is not None
    descriptor["modal_image_version"] = "im-test-immutable"
    manifest = build_manifest(
        "a" * 40,
        "production",
        chat_descriptor=descriptor,
        production_chat_enabled=True,
    )
    previous_features = {
        "chat": True,
        "native_pdf_reader": False,
        "paper_reader_chat": False,
        "paper_reader_selection": False,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }
    manifest["feature_contract_version"] = 6
    manifest["backend_features"] = previous_features
    manifest["frontend_features"] = previous_features
    (release / "release.json").write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps(previous_features)
    )

    assert validate_manifest(release, "production")["feature_contract_version"] == 6


def test_fully_configured_production_chat_runtime_can_start(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "pdf.worker.min-abc123.js").write_text(
        "export {}"
    )
    sha = "a" * 40
    descriptor = _chat_descriptor_from_source(
        Path(__file__).resolve().parents[3],
        "production",
        chat_enabled=True,
    )
    assert descriptor is not None
    descriptor["modal_image_version"] = "im-test-immutable"
    features = profile_features("production", production_chat_enabled=True)
    (release / "release.json").write_text(
        json.dumps(
            build_manifest(
                sha,
                "production",
                chat_descriptor=descriptor,
                production_chat_enabled=True,
            )
        )
    )
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))
    settings = deployed_settings(tmp_path, release, "production")
    settings.chat_enabled = True
    settings.native_pdf_reader_enabled = True
    settings.paper_reader_chat_enabled = True
    settings.paper_reader_selection_enabled = True
    settings.chat_public_admission_enabled = True
    settings.chat_sandbox_admission_enabled = True
    settings.chat_max_concurrency = 2
    settings.chat_blank_pool_enabled = True
    settings.chat_persistent_worker_enabled = True
    settings.chat_sandbox_spend_enforcement_enabled = True
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
    settings.chat_openrouter_server_funded_enabled = True

    assert validate_runtime(settings) == features
    settings.chat_operational_alerts_enabled = False
    with pytest.raises(RuntimeError, match="operational alerts"):
        validate_runtime(settings)


def test_production_chat_activation_requires_enabled_operational_monitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", tmp_path)
    (tmp_path / "production.env").write_text("PWC_CHAT_ENABLED=true\n")
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(deploy_cli.subprocess, "run", fake_run)
    with pytest.raises(deploy_cli.DeployError, match="operational alert"):
        require_production_chat_monitor("production")
    assert observed == [
        ["systemctl", "is-enabled", "--quiet", "pwc-chat-alert-monitor.timer"]
    ]

    observed.clear()
    (tmp_path / "production.env").write_text("PWC_CHAT_ENABLED=false\n")
    require_production_chat_monitor("production")
    assert observed == []


def test_production_chat_activation_requires_enabled_synthetic_probe_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", tmp_path)
    (tmp_path / "production.env").write_text("PWC_CHAT_ENABLED=true\n")
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(returncode=0 if len(observed) == 1 else 1)

    monkeypatch.setattr(deploy_cli.subprocess, "run", fake_run)

    with pytest.raises(deploy_cli.DeployError, match="synthetic chat probe"):
        require_production_chat_monitor("production")

    assert observed == [
        ["systemctl", "is-enabled", "--quiet", "pwc-chat-alert-monitor.timer"],
        [
            "systemctl",
            "is-enabled",
            "--quiet",
            "pwc-cron-run-chat-synthetic-probe.timer",
        ],
    ]


def test_production_chat_activation_requires_protected_environment_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", config_root)

    assert _configured_chat_enabled("production") is False
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED=false\n")
    assert _configured_chat_enabled("production") is False
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED='true'\n")
    assert _configured_chat_enabled("production") is True


def test_production_chat_activation_rejects_invalid_protected_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text("PWC_CHAT_ENABLED=maybe\n")
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", config_root)

    with pytest.raises(deploy_cli.DeployError, match="true or false"):
        _configured_chat_enabled("production")


def test_legacy_release_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("feature_contract_version")
    manifest.pop("chat_runtime")
    manifest["backend_features"] = {"chat": False}
    manifest["frontend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps({"chat": False})
    )

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_v2_release_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["feature_contract_version"] = 2
    manifest.pop("chat_runtime")
    manifest["backend_features"] = {
        "chat": False,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }
    manifest["frontend_features"] = manifest["backend_features"]
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps(manifest["backend_features"])
    )

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_modal_bridge_manifest_remains_a_valid_rollback_target(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"] = {
        "enabled": False,
        "new_chat_modal_percentage": 0,
        "default_backend": "local_mcp",
        "modal_image_version": "",
        "pwc_cli_version": "",
        "worker_contract_version": "",
        "system_prompt_sha256": "",
    }
    manifest_path.write_text(json.dumps(manifest))

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


def test_disabled_production_runtime_remains_valid_after_worker_upgrade(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"].update(
        {
            "modal_image_version": "im-previous-production-image",
            "worker_contract_version": "54",
            "system_prompt_sha256": "0" * 64,
        }
    )
    manifest_path.write_text(json.dumps(manifest))

    assert validate_manifest(release, "production")["git_sha"] == "a" * 40


@pytest.mark.parametrize(
    ("field", "value"),
    [("enabled", True), ("new_chat_modal_percentage", 1)],
)
def test_disabled_production_runtime_rejects_active_chat(
    tmp_path: Path, field: str, value: object
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"][field] = value
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="active chat runtime"):
        validate_manifest(release, "production")


def test_staging_profile_inherits_admin_catalog_actions():
    assert profile_features("staging") == {
        "chat": True,
        "native_pdf_reader": True,
        "paper_reader_chat": True,
        "paper_reader_selection": True,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


def test_version_three_staging_release_remains_valid_after_profile_expansion(
    tmp_path: Path,
):
    release = make_bundle(tmp_path, chat=True)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    previous_features = {
        "chat": True,
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }
    manifest["feature_contract_version"] = 3
    manifest["backend_features"] = previous_features
    manifest["frontend_features"] = previous_features
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps(previous_features)
    )

    assert validate_manifest(release, "staging")["feature_contract_version"] == 3


def test_production_profile_enables_admin_catalog_actions():
    assert profile_features("production") == {
        "chat": False,
        "native_pdf_reader": False,
        "paper_reader_chat": False,
        "paper_reader_selection": False,
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (
            "production",
            {
                "VITE_AUTH_URL": "",
                "VITE_CHAT_ENABLED": "0",
                "VITE_CHAT_LIVE": "0",
                "VITE_CHAT_MCP_APPS_HOST_ENABLED": "0",
                "VITE_NATIVE_PDF_READER_ENABLED": "0",
                "VITE_PAPER_READER_CHAT_ENABLED": "0",
                "VITE_PAPER_READER_SELECTION_ENABLED": "0",
                "VITE_CODEX_ADD_EVALS_ENABLED": "1",
                "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
            },
        ),
        (
            "staging",
            {
                "VITE_AUTH_URL": "https://paperswithcode.co",
                "VITE_CHAT_ENABLED": "1",
                "VITE_CHAT_LIVE": "1",
                "VITE_CHAT_MCP_APPS_HOST_ENABLED": "1",
                "VITE_NATIVE_PDF_READER_ENABLED": "1",
                "VITE_PAPER_READER_CHAT_ENABLED": "1",
                "VITE_PAPER_READER_SELECTION_ENABLED": "1",
                "VITE_CODEX_ADD_EVALS_ENABLED": "1",
                "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
            },
        ),
    ],
)
def test_frontend_build_flags_follow_release_profile(environment: str, expected: dict):
    assert deploy_cli.frontend_feature_environment(environment) == expected


def test_production_activation_frontend_flags_are_enabled_together():
    assert deploy_cli.frontend_feature_environment(
        "production", production_chat_enabled=True
    ) == {
        "VITE_AUTH_URL": "",
        "VITE_CHAT_ENABLED": "1",
        "VITE_CHAT_LIVE": "1",
        "VITE_CHAT_MCP_APPS_HOST_ENABLED": "1",
        "VITE_NATIVE_PDF_READER_ENABLED": "1",
        "VITE_PAPER_READER_CHAT_ENABLED": "1",
        "VITE_PAPER_READER_SELECTION_ENABLED": "1",
        "VITE_CODEX_ADD_EVALS_ENABLED": "1",
        "VITE_CODEX_ENRICH_PAPER_ENABLED": "1",
    }


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_codex_jobs_require_all_credentials(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    settings.codex_jobs_token = ""
    with pytest.raises(RuntimeError, match="Codex jobs require"):
        validate_runtime(settings)


def test_frontend_host_environment_reads_only_host_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(deploy_cli, "CONFIG_ROOT", tmp_path)
    assert deploy_cli.frontend_host_environment("production") == {}

    (tmp_path / "production.env").write_text(
        "PWC_DB_PASSWORD=secret\n"
        "# VITE_INTERNAL_HOST_ALIASES=ignored\n"
        "VITE_INTERNAL_HOST_ALIASES='203.0.113.10'\n"
        "VITE_POSTHOG_PROJECT_TOKEN=phc_test\n"
    )
    assert deploy_cli.frontend_host_environment("production") == {
        "VITE_INTERNAL_HOST_ALIASES": "203.0.113.10"
    }
    assert deploy_cli.frontend_analytics_environment("production") == {
        "VITE_POSTHOG_PROJECT_TOKEN": "phc_test",
        "VITE_POSTHOG_HOST": "https://eu.i.posthog.com",
    }
