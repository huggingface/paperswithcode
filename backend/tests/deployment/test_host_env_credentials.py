"""Host environment credential mapping, isolation, and rotation."""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env

CURATOR_IMAGE = (
    "cr.hf.co/nielsr/pwc-codex-curator:runner-f165a0e4c56a"
    "@sha256:3c4c6b16737946f69a0390f3c014ffea5a46be8b7e63633e804c21d3e0046496"
)


def test_staging_chat_alert_values_are_distinct_https_destinations():
    values = configure_host_env.staging_chat_alert_values(
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=https://hooks.slack.test/primary"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL="
                "https://hooks.slack.test/fallback"
            ),
        }
    )

    assert values == {
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": ("https://hooks.slack.test/primary"),
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
            "https://hooks.slack.test/fallback"
        ),
    }


@pytest.mark.parametrize(
    "legacy",
    [
        {},
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=http://alerts.test/primary"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL="
                "https://alerts.test/fallback"
            ),
        },
        {
            "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL=https://alerts.test/same"
            ),
            "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL": (
                "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL=https://alerts.test/same"
            ),
        },
    ],
)
def test_staging_chat_alert_values_reject_unsafe_configuration(legacy):
    with pytest.raises(ValueError):
        configure_host_env.staging_chat_alert_values(legacy)


def test_production_codex_credentials_are_mapped_without_enabling_base_flags():
    values = configure_host_env.production_codex_values(
        {
            "OPENAI_API_KEY": "OPENAI_API_KEY=openai-secret",
            "PWC_HF_TOKEN": "PWC_HF_TOKEN=hf-secret",
        },
        "nielsr",
    )
    assert values == {
        "PWC_CODEX_ADD_EVALS_ENABLED": "false",
        "PWC_CODEX_ENRICH_PAPER_ENABLED": "false",
        "PWC_CODEX_JOBS_ENABLED": "false",
        "PWC_CODEX_JOBS_NAMESPACE": "nielsr",
        "PWC_CODEX_JOBS_OPENAI_API_KEY": "openai-secret",
        "PWC_CODEX_JOBS_TOKEN": "hf-secret",
        "PWC_CODEX_JOBS_IMAGE": CURATOR_IMAGE,
        "PWC_CODEX_JOBS_IMAGE_REVISION": "",
        "PWC_CODEX_JOBS_CLI_VERSION": "0.75.0",
        "PWC_CODEX_JOBS_MODEL": "gpt-6-luna",
        "PWC_CODEX_JOBS_REASONING_EFFORT": "medium",
        "PWC_CODEX_JOBS_MAX_ACTIVE": "4",
        "PWC_CODEX_JOBS_MAX_SCHEDULED_ACTIVE": "3",
        "PWC_CODEX_CURATION_SCHEDULER_ENABLED": "true",
        "PWC_CODEX_CURATION_DIRECT_APPLY_ENABLED": "true",
        "PWC_CODEX_CURATION_TRACE_UPLOAD_ENABLED": "true",
        "PWC_CODEX_CURATION_TRACE_HF_BUCKET_ID": "nielsr/curate-papers-traces",
        "PWC_CODEX_CURATION_POLICY_VERSION": "hf-daily-v1",
    }


def test_production_codex_only_updates_app_and_cron_environments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.env"
    source.write_text(
        "\n".join(
            f"{key}=test-value"
            for key in (
                "PWC_DB_HOST",
                "PWC_DB_NAME",
                "PWC_DB_PASSWORD",
                "PWC_DB_PORT",
                "PWC_DB_USER",
                "PWC_HF_OAUTH_CLIENT_ID",
                "PWC_HF_OAUTH_CLIENT_SECRET",
                "PWC_HF_TOKEN",
                "PWC_JWT_SECRET",
                "PWC_GITHUB_TOKEN",
                "PWC_OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text("APP_ONLY=keep\n", encoding="utf-8")
    (config_root / "production-cron.env").write_text(
        "CRON_ONLY=keep\n", encoding="utf-8"
    )
    writes = []
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_env",
        lambda path, lines, group: writes.append((path, lines, group)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--production-codex-only",
            "--codex-jobs-namespace",
            "nielsr",
        ],
    )

    assert configure_host_env.main() == 0
    assert [(path.name, group) for path, _, group in writes] == [
        ("production.env", "pwc-production"),
        ("production-cron.env", "pwc-cron"),
    ]
    app_lines = writes[0][1]
    cron_lines = writes[1][1]
    assert configure_host_env.decoded_value(app_lines["APP_ONLY"]) == "keep"
    assert configure_host_env.decoded_value(cron_lines["CRON_ONLY"]) == "keep"
    for lines in (app_lines, cron_lines):
        assert (
            configure_host_env.decoded_value(
                lines["PWC_CODEX_CURATION_SCHEDULER_ENABLED"]
            )
            == "true"
        )
        assert (
            configure_host_env.decoded_value(lines["PWC_CODEX_JOBS_IMAGE_REVISION"])
            == ""
        )


def test_production_codex_image_only_updates_no_other_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "incomplete-production.env"
    source.write_text("APP_ONLY=source\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text(
        "APP_ONLY=keep\nPWC_CODEX_JOBS_IMAGE=old-image\n",
        encoding="utf-8",
    )
    (config_root / "production-cron.env").write_text(
        "CRON_ONLY=keep\nPWC_CODEX_JOBS_IMAGE_REVISION=old-revision\n",
        encoding="utf-8",
    )
    writes = []
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_env",
        lambda path, lines, group: writes.append((path, lines, group)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--production-codex-image-only",
            "--confirm",
            "UPDATE_PRODUCTION_CODEX_IMAGE",
        ],
    )

    assert configure_host_env.main() == 0
    assert [(path.name, group) for path, _, group in writes] == [
        ("production.env", "pwc-production"),
        ("production-cron.env", "pwc-cron"),
    ]
    app_lines = writes[0][1]
    cron_lines = writes[1][1]
    assert configure_host_env.decoded_value(app_lines["APP_ONLY"]) == "keep"
    assert configure_host_env.decoded_value(cron_lines["CRON_ONLY"]) == "keep"
    for lines in (app_lines, cron_lines):
        assert configure_host_env.decoded_value(lines["PWC_CODEX_JOBS_IMAGE"]) == (
            CURATOR_IMAGE
        )
        assert (
            configure_host_env.decoded_value(lines["PWC_CODEX_JOBS_IMAGE_REVISION"])
            == ""
        )


def test_historical_semantic_scholar_key_is_cron_only_and_preserved():
    secondary = "PWC_SEMANTIC_SCHOLAR_API_KEY_2"
    legacy = {
        "PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github",
        secondary: f"{secondary}=new-secondary",
    }
    current = {secondary: f"{secondary}=old-secondary"}

    cron = configure_host_env.cron_passthrough_credentials(legacy, current)
    assert cron[secondary] == f"{secondary}=new-secondary"
    assert secondary not in configure_host_env.without_cron_only_credentials(legacy)

    preserved = configure_host_env.cron_passthrough_credentials(
        {"PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github"}, current
    )
    assert preserved[secondary] == f"{secondary}=old-secondary"


def test_autonomous_credentials_are_preserved_only_in_cron_overlay():
    keys = {
        "PWC_AUTONOMOUS_ALERT_FALLBACK_WEBHOOK_URL",
        "PWC_AUTONOMOUS_ALERT_SLACK_WEBHOOK_URL",
        "PWC_AUTONOMOUS_CODEX_API_KEY",
        "PWC_AUTONOMOUS_CODEX_BROKER_TOKEN",
        "PWC_AUTONOMOUS_DIGEST_WEBHOOK_URL",
        "PWC_AUTONOMOUS_CODEX_RESERVATION_VERIFY_KEY",
        "PWC_AUTONOMOUS_SUBMISSION_HF_TOKEN",
        "PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED",
        "PWC_AUTONOMOUS_SUBMISSION_OPENAI_API_KEY",
    }
    current = {key: f"{key}=existing-{index}" for index, key in enumerate(keys)}
    legacy = {"PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github"}

    cron = configure_host_env.cron_passthrough_credentials(legacy, current)
    application = configure_host_env.without_cron_only_credentials(current)

    assert keys <= cron.keys()
    assert keys.isdisjoint(application)


def test_staging_chat_runtime_credentials_are_preserved():
    preserved = configure_host_env.staging_runtime_passthrough(
        {
            "MODAL_TOKEN_ID": "MODAL_TOKEN_ID=id",
            "MODAL_TOKEN_SECRET": "MODAL_TOKEN_SECRET=secret",
            "PWC_CHAT_MODAL_IMAGE_VERSION": "PWC_CHAT_MODAL_IMAGE_VERSION=im-123",
            "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
            "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
            "PWC_CHAT_GATEWAY_URL": "PWC_CHAT_GATEWAY_URL=https://stale.example",
            "PWC_DB_PASSWORD": "PWC_DB_PASSWORD=secret",
        }
    )

    assert preserved == {
        "MODAL_TOKEN_ID": "MODAL_TOKEN_ID=id",
        "MODAL_TOKEN_SECRET": "MODAL_TOKEN_SECRET=secret",
        "PWC_CHAT_MODAL_IMAGE_VERSION": "PWC_CHAT_MODAL_IMAGE_VERSION=im-123",
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
    }


def test_staging_title_values_are_exact_and_isolated():
    source = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": ("PWC_CHAT_TITLE_GENERATION_ENABLED=true"),
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "PWC_CHAT_TITLE_CREDENTIAL_OWNER=nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": (
            "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT=staging"
        ),
    }

    values = configure_host_env.staging_title_values(
        source,
        {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
        {"PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=production-secret"},
    )

    assert values == {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_HF_TOKEN": "title-secret",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "staging",
        "PWC_CHAT_TITLE_MODEL": "zai-org/GLM-5.3-Flash:baseten",
        "PWC_CHAT_TITLE_PROVIDER": "huggingface",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }

    reused = dict(source)
    reused["PWC_CHAT_TITLE_HF_TOKEN"] = "PWC_CHAT_TITLE_HF_TOKEN=general-secret"
    with pytest.raises(ValueError, match="distinct from general and production"):
        configure_host_env.staging_title_values(
            reused,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=general-secret"},
            {},
        )


def test_staging_langfuse_credentials_are_bounded_and_preserved():
    legacy = {
        "LANGFUSE_BASE_URL": "LANGFUSE_BASE_URL=https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "LANGFUSE_PUBLIC_KEY=pk-test",
        "LANGFUSE_SECRET_KEY": "LANGFUSE_SECRET_KEY=sk-test",
    }

    assert configure_host_env.staging_langfuse_values(legacy) == {
        "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "PWC_CHAT_LANGFUSE_ENABLED": "true",
    }
    lines = {
        **legacy,
        "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
    }
    assert configure_host_env.staging_runtime_passthrough(lines) == lines


def test_production_langfuse_credentials_are_isolated_from_staging():
    source = {
        "LANGFUSE_BASE_URL": "LANGFUSE_BASE_URL=https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "LANGFUSE_PUBLIC_KEY=pk-production",
        "LANGFUSE_SECRET_KEY": "LANGFUSE_SECRET_KEY=sk-production",
    }
    staging = {
        "LANGFUSE_PUBLIC_KEY": "LANGFUSE_PUBLIC_KEY=pk-staging",
        "LANGFUSE_SECRET_KEY": "LANGFUSE_SECRET_KEY=sk-staging",
    }

    assert configure_host_env.production_langfuse_values(source, staging) == {
        "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
        "LANGFUSE_PUBLIC_KEY": "pk-production",
        "LANGFUSE_SECRET_KEY": "sk-production",
        "PWC_CHAT_LANGFUSE_ENABLED": "true",
    }

    source["LANGFUSE_SECRET_KEY"] = "LANGFUSE_SECRET_KEY=sk-staging"
    with pytest.raises(ValueError, match="must not reuse"):
        configure_host_env.production_langfuse_values(source, staging)


def test_production_langfuse_mode_preserves_unrelated_live_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.env"
    source.write_text(
        "LANGFUSE_BASE_URL=https://cloud.langfuse.com\n"
        "LANGFUSE_PUBLIC_KEY=pk-production\n"
        "LANGFUSE_SECRET_KEY=sk-production\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text(
        "PWC_CHAT_ENABLED=true\n", encoding="utf-8"
    )
    (config_root / "staging.env").write_text(
        "LANGFUSE_PUBLIC_KEY=pk-staging\nLANGFUSE_SECRET_KEY=sk-staging\n",
        encoding="utf-8",
    )
    written = {}
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_env",
        lambda path, lines, group: written.update(
            {"path": path, "lines": lines, "group": group}
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--production-langfuse-only",
        ],
    )

    assert configure_host_env.main() == 0
    assert written["path"] == config_root / "production.env"
    assert written["group"] == "pwc-production"
    assert (
        configure_host_env.decoded_value(written["lines"]["PWC_CHAT_ENABLED"]) == "true"
    )
    assert (
        configure_host_env.decoded_value(written["lines"]["PWC_CHAT_LANGFUSE_ENABLED"])
        == "true"
    )


def test_staging_openrouter_credential_gets_a_chat_only_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", tmp_path)
    values = configure_host_env.staging_openrouter_values(
        {"PWC_OPENROUTER_API_KEY": "PWC_OPENROUTER_API_KEY=secret"}
    )
    assert values["PWC_CHAT_OPENROUTER_API_KEY"] == "secret"
    assert values["PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED"] == "true"
    assert values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] == "1.00"
    assert values["PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD"] == "200.00"
    encoded_key = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])["1"]
    assert (
        len(base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))) == 32
    )
    assert values["PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET"]

    with pytest.raises(ValueError, match="PWC_OPENROUTER_API_KEY"):
        configure_host_env.staging_openrouter_values({})


def test_staging_openai_direct_configuration_is_isolated_and_exact():
    values = configure_host_env.staging_openai_direct_values(
        {"OPENAI_API_KEY": "OPENAI_API_KEY=staging-secret"},
        {"OPENAI_API_KEY": "OPENAI_API_KEY=production-secret"},
    )

    assert values == {
        "PWC_OPENAI_API_KEY": "staging-secret",
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_MODEL": "gpt-5.6-luna@openai",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
    }
    with pytest.raises(ValueError, match="must not reuse production"):
        configure_host_env.staging_openai_direct_values(
            {"OPENAI_API_KEY": "OPENAI_API_KEY=same-secret"},
            {"PWC_OPENAI_API_KEY": "PWC_OPENAI_API_KEY=same-secret"},
        )
    with pytest.raises(ValueError, match="source is missing"):
        configure_host_env.staging_openai_direct_values({}, {})


def test_staging_openai_direct_rollback_restores_legacy_openrouter_profile():
    assert configure_host_env.staging_openai_direct_disable_values() == {
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "false",
        "PWC_CHAT_PI_PREWARM_MODEL": "openai/gpt-5.6-luna",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
    }


def test_staging_openai_direct_installer_rejects_unprotected_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "openai.env"
    source.write_text("OPENAI_API_KEY=staging-secret\n", encoding="utf-8")
    source.chmod(0o644)
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--staging-openai-direct-only",
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()


def test_staging_web_search_configuration_is_scoped_and_bounded():
    values = configure_host_env.staging_web_search_values(
        {"EXA_API_KEY": "EXA_API_KEY=server-secret"}
    )

    assert values["PWC_CHAT_WEB_SEARCH_EXA_API_KEY"] == "server-secret"
    assert values["PWC_CHAT_WEB_SEARCH_ENABLED"] == "true"
    assert values["PWC_CHAT_WEB_SEARCH_MAX_CALLS"] == "3"
    assert values["PWC_CHAT_WEB_SEARCH_RESULT_COUNT"] == "5"
    assert values["PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES"] == "16384"
    assert values["PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS"] == "5000"
    assert values["PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS"] == "6000"
    assert set(values) <= configure_host_env.STAGING_RUNTIME_PASSTHROUGH_KEYS
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        configure_host_env.staging_web_search_values({})


def test_production_web_search_configuration_uses_the_same_bounded_contract():
    legacy = {"EXA_API_KEY": "EXA_API_KEY=server-secret"}
    assert configure_host_env.production_web_search_values(
        legacy
    ) == configure_host_env.staging_web_search_values(legacy)


def test_staging_github_configuration_is_single_key_and_non_empty():
    assert configure_host_env.staging_github_values(
        {"PWC_GITHUB_TOKEN": "PWC_GITHUB_TOKEN=github-secret"}
    ) == {"PWC_GITHUB_TOKEN": "github-secret"}
    with pytest.raises(ValueError, match="PWC_GITHUB_TOKEN"):
        configure_host_env.staging_github_values({})


def test_production_cron_github_rotation_is_single_key_and_preserves_overlay(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source.env"
    source.write_text("PWC_GITHUB_TOKEN=new-secret\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production-cron.env").write_text(
        "PWC_GITHUB_TOKEN=old-secret\nPWC_HF_TOKEN=keep-me\n",
        encoding="utf-8",
    )
    written = {}
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        configure_host_env,
        "write_env",
        lambda path, lines, group: written.update(
            {"path": path, "lines": lines, "group": group}
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--production-cron-github-only",
            "--confirm",
            "ROTATE_PRODUCTION_CRON_GITHUB",
        ],
    )

    assert configure_host_env.main() == 0
    assert written["path"] == config_root / "production-cron.env"
    assert written["group"] == "pwc-cron"
    assert (
        configure_host_env.decoded_value(written["lines"]["PWC_GITHUB_TOKEN"])
        == "new-secret"
    )
    assert configure_host_env.decoded_value(written["lines"]["PWC_HF_TOKEN"]) == (
        "keep-me"
    )


def test_staging_openrouter_disable_removes_key_and_pins_flag_off():
    assert configure_host_env.without_staging_openrouter(
        {
            "PWC_CHAT_OPENROUTER_API_KEY": "PWC_CHAT_OPENROUTER_API_KEY=secret",
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": (
                "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED=true"
            ),
            "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
        }
    ) == {
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": (
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED=false"
        ),
        "PWC_CHAT_LANGFUSE_ENABLED": "PWC_CHAT_LANGFUSE_ENABLED=true",
    }


def test_staging_chat_latency_rollout_settings_are_preserved():
    rollout_keys = {
        "PWC_CHAT_BLANK_POOL_ENABLED",
        "PWC_CHAT_BLANK_POOL_MAX",
        "PWC_CHAT_BLANK_POOL_MIN",
        "PWC_CHAT_BLANK_POOL_MIN_REMAINING_SECONDS",
        "PWC_CHAT_BLANK_POOL_MONTHLY_BUDGET_USD",
        "PWC_CHAT_BLANK_POOL_REFILL_CONCURRENCY",
        "PWC_CHAT_BLANK_POOL_REPORTED_MONTH_TO_DATE_USD",
        "PWC_CHAT_BLANK_POOL_ROTATE_BEFORE_SECONDS",
        "PWC_CHAT_CANCEL_GRACE_SECONDS",
        "PWC_CHAT_PERSISTENT_SANDBOX_LIFETIME_SECONDS",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED",
        "PWC_CHAT_SANDBOX_CPU",
        "PWC_CHAT_SANDBOX_CPU_LIMIT",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB",
        "PWC_CHAT_SANDBOX_MEMORY_MIB",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP",
        "PWC_CHAT_WORKER_READY_TIMEOUT_SECONDS",
    }
    lines = {key: f"{key}=configured" for key in rollout_keys}

    assert rollout_keys <= configure_host_env.STAGING_RUNTIME_PASSTHROUGH_KEYS
    assert configure_host_env.staging_runtime_passthrough(lines) == lines


def test_environment_files_are_never_readable_while_being_written(
    tmp_path, monkeypatch
):
    import stat

    import deploy.configure_host_env as host_env

    modes = []
    real_replace = host_env.os.replace

    def replace(source, destination):
        modes.append(stat.S_IMODE(os.stat(source).st_mode))
        real_replace(source, destination)

    monkeypatch.setattr(host_env.os, "chown", lambda *_args: None)
    monkeypatch.setattr(
        host_env.grp, "getgrnam", lambda _name: type("G", (), {"gr_gid": 0})()
    )
    monkeypatch.setattr(host_env.os, "replace", replace)
    created = []
    real_mkstemp = host_env.tempfile.mkstemp

    def mkstemp(**kwargs):
        descriptor, path = real_mkstemp(**kwargs)
        created.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
        return descriptor, path

    monkeypatch.setattr(host_env.tempfile, "mkstemp", mkstemp)

    host_env.write_env(tmp_path / "production.env", {"A": "A=secret"}, "pwc-production")

    assert created == [0o600]
    assert modes == [0o640]
    assert (tmp_path / "production.env").read_text() == "A=secret\n"


def test_autonomous_sudo_grants_are_opt_in():
    source = (Path(__file__).parents[3] / "deploy/install_deploy_tools.py").read_text()

    assert (
        "if args.enable_autonomous_brokers:\n            install_autonomous_sudoers()"
        in source
    )


def test_backup_unit_does_not_load_the_application_environment():
    unit = (
        Path(__file__).parents[3] / "deploy/systemd/pwc-postgres-backup.service"
    ).read_text()

    environment_files = [
        line for line in unit.splitlines() if line.startswith("EnvironmentFile=")
    ]
    assert environment_files == [
        "EnvironmentFile=/etc/paperswithcode/production-cron.env"
    ]


def test_chat_executor_units_cannot_read_environment_files():
    root = Path(__file__).parents[3] / "deploy/systemd"
    for name in (
        "pwc-chat-executor-rendezvous@.service",
        "pwc-chat-executor-harness-proxy@.service",
    ):
        unit = (root / name).read_text()
        assert "SupplementaryGroups" not in unit, name
        for line in unit.splitlines():
            if "chgrp" in line:
                assert line.startswith("ExecStartPost=+"), line
