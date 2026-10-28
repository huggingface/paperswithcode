"""Host environment chat feature toggles and provider routing modes."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.configure_host_env as configure_host_env


def test_staging_chat_pi_prewarm_toggle_is_narrow_and_profiled():
    assert configure_host_env.staging_chat_pi_prewarm_values(enabled=True) == {
        "PWC_CHAT_PI_PREWARM_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_MODEL": "deepseek-ai/DeepSeek-V4-Flash-0731:baseten",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
    }
    assert configure_host_env.staging_chat_pi_prewarm_values(enabled=False) == {
        "PWC_CHAT_PI_PREWARM_ENABLED": "false"
    }


def test_production_chat_pi_prewarm_reuses_deepseek_profile_on_admitted_pool():
    current = {
        "PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": (
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED=true"
        ),
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": (
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true"
        ),
    }
    assert configure_host_env.production_chat_pi_prewarm_values(
        current, enabled=True
    ) == configure_host_env.staging_chat_pi_prewarm_values(enabled=True)
    assert configure_host_env.production_chat_pi_prewarm_values(
        current, enabled=False
    ) == configure_host_env.staging_chat_pi_prewarm_values(enabled=False)


def test_production_chat_pi_prewarm_rejects_unadmitted_or_alternative_pool():
    admitted = {
        "PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": (
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED=true"
        ),
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": (
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true"
        ),
    }
    closed_pool = {
        **admitted,
        "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=false",
    }
    with pytest.raises(ValueError, match="already-admitted chat pool"):
        configure_host_env.production_chat_pi_prewarm_values(
            closed_pool,
            enabled=True,
        )
    with pytest.raises(ValueError, match="alternative model"):
        configure_host_env.production_chat_pi_prewarm_values(
            {
                **admitted,
                "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED": (
                    "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED=true"
                ),
            },
            enabled=True,
        )


def test_staging_scope_guardrail_uses_server_credentials_and_disables_posterly():
    current = {
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=hf-guardrail",
        "PWC_CHAT_HF_BILL_TO": "PWC_CHAT_HF_BILL_TO=pwc-org",
        "PWC_CODEX_JOBS_OPENAI_API_KEY": ("PWC_CODEX_JOBS_OPENAI_API_KEY=sk-guardrail"),
        "PWC_HF_TOKEN": "PWC_HF_TOKEN=hf-main",
        "PWC_OPENAI_API_KEY": "PWC_OPENAI_API_KEY=sk-main",
    }
    assert configure_host_env.staging_scope_guardrail_values(current) == {
        "PWC_CHAT_SCOPE_GUARDRAIL_ENABLED": "true",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN": "hf-guardrail",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_BILL_TO": "pwc-org",
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY": "sk-guardrail",
        "PWC_CHAT_ARTIFACT_STORAGE_BACKEND": "hf_bucket",
        "PWC_CHAT_ARTIFACT_HF_BUCKET_ID": "nielsr/pwc-chat-artifacts-staging",
        "PWC_CHAT_POSTERLY_ENABLED": "false",
    }
    with pytest.raises(ValueError, match="source is missing"):
        configure_host_env.staging_scope_guardrail_values(
            {
                key: value
                for key, value in current.items()
                if key != "PWC_CHAT_TITLE_HF_TOKEN"
            }
        )
    with pytest.raises(ValueError, match="must not reuse PWC_HF_TOKEN"):
        configure_host_env.staging_scope_guardrail_values(
            {
                **current,
                "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=hf-main",
            }
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_scope_title_hf_values_are_exact_and_environment_isolated(environment):
    other = "production" if environment == "staging" else "staging"
    source = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": ("PWC_CHAT_TITLE_GENERATION_ENABLED=true"),
        "PWC_CHAT_TITLE_HF_TOKEN": (f"PWC_CHAT_TITLE_HF_TOKEN=hf-title-{environment}"),
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": ("PWC_CHAT_TITLE_CREDENTIAL_OWNER=nielsr"),
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": (
            f"PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT={environment}"
        ),
    }
    current = {
        "PWC_HF_TOKEN": f"PWC_HF_TOKEN=hf-general-{environment}",
        "PWC_OPENAI_API_KEY": f"PWC_OPENAI_API_KEY=sk-main-{environment}",
        "PWC_CODEX_JOBS_OPENAI_API_KEY": (
            f"PWC_CODEX_JOBS_OPENAI_API_KEY=sk-guardrail-{environment}"
        ),
    }
    other_current = {
        "PWC_CHAT_TITLE_HF_TOKEN": f"PWC_CHAT_TITLE_HF_TOKEN=hf-title-{other}"
    }

    values = configure_host_env.scope_title_hf_values(
        source,
        current,
        other_current,
        environment=environment,
    )

    assert values == {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_HF_TOKEN": f"hf-title-{environment}",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": "nielsr",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": environment,
        "PWC_CHAT_TITLE_MODEL": "zai-org/GLM-5.3-Flash:baseten",
        "PWC_CHAT_TITLE_PROVIDER": "huggingface",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
        "PWC_CHAT_SCOPE_GUARDRAIL_ENABLED": "true",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN": f"hf-title-{environment}",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_BILL_TO": "huggingface",
        "PWC_CHAT_SCOPE_GUARDRAIL_GLM_MODEL": ("zai-org/GLM-5.3-Flash:baseten"),
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY": (f"sk-guardrail-{environment}"),
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_MODEL": "gpt-5.6-luna",
        "PWC_CHAT_POSTERLY_ENABLED": "false",
        **(
            {
                "PWC_CHAT_ARTIFACT_STORAGE_BACKEND": "hf_bucket",
                "PWC_CHAT_ARTIFACT_HF_BUCKET_ID": ("nielsr/pwc-chat-artifacts-staging"),
            }
            if environment == "staging"
            else {}
        ),
    }

    for reused in (
        f"hf-general-{environment}",
        f"hf-title-{other}",
    ):
        with pytest.raises(ValueError, match="distinct"):
            configure_host_env.scope_title_hf_values(
                {
                    **source,
                    "PWC_CHAT_TITLE_HF_TOKEN": (f"PWC_CHAT_TITLE_HF_TOKEN={reused}"),
                },
                current,
                other_current,
                environment=environment,
            )


def test_scope_title_hf_values_require_luna_fallback():
    source = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": ("PWC_CHAT_TITLE_GENERATION_ENABLED=true"),
        "PWC_CHAT_TITLE_HF_TOKEN": "PWC_CHAT_TITLE_HF_TOKEN=hf-title",
        "PWC_CHAT_TITLE_BILL_TO": "PWC_CHAT_TITLE_BILL_TO=huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": ("PWC_CHAT_TITLE_CREDENTIAL_OWNER=nielsr"),
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": (
            "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT=production"
        ),
    }

    with pytest.raises(ValueError, match="PWC_CODEX_JOBS_OPENAI_API_KEY"):
        configure_host_env.scope_title_hf_values(
            source,
            {"PWC_HF_TOKEN": "PWC_HF_TOKEN=hf-general"},
            {},
            environment="production",
        )
    values = configure_host_env.scope_title_hf_values(
        source,
        {
            "PWC_HF_TOKEN": "PWC_HF_TOKEN=hf-general",
            "PWC_OPENAI_API_KEY": "PWC_OPENAI_API_KEY=shared-fallback",
            "PWC_CODEX_JOBS_OPENAI_API_KEY": (
                "PWC_CODEX_JOBS_OPENAI_API_KEY=shared-fallback"
            ),
        },
        {
            "PWC_CODEX_JOBS_OPENAI_API_KEY": (
                "PWC_CODEX_JOBS_OPENAI_API_KEY=shared-fallback"
            )
        },
        environment="production",
    )
    assert values["PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY"] == "shared-fallback"


def test_production_scope_title_hf_mode_updates_only_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "production-title.env"
    source.write_text(
        "\n".join(
            (
                "PWC_CHAT_TITLE_GENERATION_ENABLED=true",
                "PWC_CHAT_TITLE_HF_TOKEN=hf-title-production",
                "PWC_CHAT_TITLE_BILL_TO=huggingface",
                "PWC_CHAT_TITLE_CREDENTIAL_OWNER=nielsr",
                "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT=production",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text(
        "\n".join(
            (
                "KEEP=production",
                "PWC_HF_TOKEN=hf-general-production",
                "PWC_OPENAI_API_KEY=sk-main-production",
                "PWC_CODEX_JOBS_OPENAI_API_KEY=sk-guardrail-production",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (config_root / "staging.env").write_text(
        "PWC_CHAT_TITLE_HF_TOKEN=hf-title-staging\n",
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
            "--production-scope-title-hf-only",
            "--confirm",
            "ENABLE_PRODUCTION_HF_SCOPE_AND_TITLES",
        ],
    )

    assert configure_host_env.main() == 0
    assert [(path.name, group) for path, _, group in writes] == [
        ("production.env", "pwc-production")
    ]
    written = writes[0][1]
    assert configure_host_env.decoded_value(written["KEEP"]) == "production"
    assert (
        configure_host_env.decoded_value(written["PWC_CHAT_TITLE_PROVIDER"])
        == "huggingface"
    )
    assert (
        configure_host_env.decoded_value(written["PWC_CHAT_SCOPE_GUARDRAIL_ENABLED"])
        == "true"
    )


def test_production_openai_direct_configuration_reuses_protected_key_exactly():
    admitted = {
        "PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=true",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": (
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED=true"
        ),
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": (
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true"
        ),
        "OPENAI_API_KEY": "OPENAI_API_KEY=test-production-secret",
    }

    assert configure_host_env.production_openai_direct_values(admitted) == {
        "PWC_OPENAI_API_KEY": "test-production-secret",
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_MODEL": "gpt-5.6-luna@openai",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
    }
    with pytest.raises(ValueError, match="credential is missing"):
        configure_host_env.production_openai_direct_values(
            {key: value for key, value in admitted.items() if key != "OPENAI_API_KEY"}
        )
    with pytest.raises(ValueError, match="admitted chat infrastructure"):
        configure_host_env.production_openai_direct_values(
            {
                **admitted,
                "PWC_CHAT_BLANK_POOL_ENABLED": "PWC_CHAT_BLANK_POOL_ENABLED=false",
            }
        )


def test_production_excalidraw_toggle_is_narrow_and_requires_admitted_chat():
    admitted = {
        "PWC_CHAT_ENABLED": "PWC_CHAT_ENABLED=true",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": (
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED=true"
        ),
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": (
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true"
        ),
    }
    assert configure_host_env.production_excalidraw_values(admitted, enabled=True) == {
        "PWC_CHAT_EXCALIDRAW_ENABLED": "true",
        "PWC_CHAT_MCP_APPS_HOST_ENABLED": "true",
    }
    assert configure_host_env.production_excalidraw_values({}, enabled=False) == {
        "PWC_CHAT_EXCALIDRAW_ENABLED": "false",
        "PWC_CHAT_MCP_APPS_HOST_ENABLED": "false",
    }
    with pytest.raises(ValueError, match="admitted chat infrastructure"):
        configure_host_env.production_excalidraw_values(
            {
                **admitted,
                "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": (
                    "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=false"
                ),
            },
            enabled=True,
        )


def test_staging_chat_routing_toggle_is_independent_and_latency_profiled():
    assert configure_host_env.staging_chat_routing_values(enabled=True) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_ROUTING_POLICY": "latency",
    }
    assert configure_host_env.staging_chat_routing_values(enabled=False) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "false"
    }


def test_staging_chat_routing_toggle_selects_preferred_provider_profile():
    assert configure_host_env.staging_chat_routing_values(
        enabled=True, policy="preferred_provider"
    ) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_ROUTING_POLICY": "preferred_provider",
        "PWC_CHAT_OPENROUTER_PREFERRED_PROVIDERS": "fireworks",
        "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": "0.28",
        "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": "0.56",
    }


def test_staging_chat_routing_toggle_accepts_an_explicit_preferred_provider():
    assert configure_host_env.staging_chat_routing_values(
        enabled=True,
        policy="preferred_provider",
        preferred_providers=" baseten/fp8 ",
    ) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_ROUTING_POLICY": "preferred_provider",
        "PWC_CHAT_OPENROUTER_PREFERRED_PROVIDERS": "baseten/fp8",
        "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": "0.28",
        "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": "0.56",
    }


def test_staging_chat_routing_toggle_accepts_bounded_price_ceilings():
    assert configure_host_env.staging_chat_routing_values(
        enabled=True,
        policy="preferred_provider",
        preferred_providers="deepseek",
        max_prompt_price_per_million_usd=0.22,
        max_completion_price_per_million_usd=0.66,
    ) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_ROUTING_POLICY": "preferred_provider",
        "PWC_CHAT_OPENROUTER_PREFERRED_PROVIDERS": "deepseek",
        "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": "0.22",
        "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": "0.66",
    }


def test_staging_chat_routing_toggle_rejects_empty_preferred_providers():
    with pytest.raises(
        ValueError, match="preferred-provider routing requires provider slugs"
    ):
        configure_host_env.staging_chat_routing_values(
            enabled=True,
            policy="preferred_provider",
            preferred_providers=" , ",
        )


def test_staging_chat_routing_toggle_selects_price_performance_profile():
    assert configure_host_env.staging_chat_routing_values(
        enabled=True, policy="price_performance"
    ) == {
        "PWC_CHAT_OPENROUTER_ROUTING_ENABLED": "true",
        "PWC_CHAT_OPENROUTER_ROUTING_POLICY": "price_performance",
        "PWC_CHAT_OPENROUTER_PREFERRED_MAX_LATENCY_P90_SECONDS": "3",
        "PWC_CHAT_OPENROUTER_PREFERRED_MIN_THROUGHPUT_P90": "50",
        "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": "0.28",
        "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": "0.56",
    }


def test_staging_chat_payload_toggle_selects_one_exact_candidate():
    assert configure_host_env.staging_chat_payload_values(
        enabled=True, candidate="system_duplicates"
    ) == {
        "PWC_CHAT_INITIAL_PAYLOAD_OPTIMIZATION_ENABLED": "true",
        "PWC_CHAT_INITIAL_PAYLOAD_OPTIMIZATION_CANDIDATE": "system_duplicates",
    }
    assert configure_host_env.staging_chat_payload_values(
        enabled=False, candidate="tool_duplicates"
    ) == {"PWC_CHAT_INITIAL_PAYLOAD_OPTIMIZATION_ENABLED": "false"}


def test_staging_chat_alternative_model_toggle_is_reviewed_and_reversible():
    assert configure_host_env.staging_chat_alternative_model_values(
        enabled=True, candidate="openai/gpt-5.6-luna"
    ) == {
        "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED": "true",
        "PWC_CHAT_ALTERNATIVE_MODEL": "openai/gpt-5.6-luna",
        "PWC_CHAT_PI_PREWARM_MODEL": "openai/gpt-5.6-luna",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
    }
    assert configure_host_env.staging_chat_alternative_model_values(
        enabled=False, candidate="openai/gpt-5.6-luna"
    ) == {
        "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED": "false",
        "PWC_CHAT_PI_PREWARM_MODEL": "deepseek-ai/DeepSeek-V4-Flash-0731:baseten",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
    }
    assert (
        configure_host_env.staging_chat_alternative_model_values(
            enabled=True,
            candidate="openai/gpt-5.6-luna",
            reasoning_effort="high",
        )["PWC_CHAT_PI_PREWARM_REASONING_EFFORT"]
        == "high"
    )
    with pytest.raises(ValueError, match="not reviewed"):
        configure_host_env.staging_chat_alternative_model_values(
            enabled=True, candidate="unreviewed/model"
        )
    with pytest.raises(ValueError, match="reasoning effort"):
        configure_host_env.staging_chat_alternative_model_values(
            enabled=True,
            candidate="openai/gpt-5.6-luna",
            reasoning_effort="xhigh",
        )


@pytest.mark.parametrize("enabled", [True, False])
def test_staging_chat_pi_prewarm_mode_preserves_other_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "staging.env").write_text("UNRELATED=preserved\n", encoding="utf-8")
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
    mode = (
        "--staging-chat-pi-prewarm-enable-only"
        if enabled
        else "--staging-chat-pi-prewarm-disable-only"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_host_env.py", "--legacy-env", str(source), mode],
    )

    assert configure_host_env.main() == 0
    assert written["path"] == config_root / "staging.env"
    assert written["group"] == "pwc-staging"
    assert configure_host_env.decoded_value(written["lines"]["UNRELATED"]) == (
        "preserved"
    )
    assert configure_host_env.decoded_value(
        written["lines"]["PWC_CHAT_PI_PREWARM_ENABLED"]
    ) == ("true" if enabled else "false")


# Production break caught: a staging durable toggle targets production, changes
# unrelated feature/capacity lines, uses the wrong ownership, or prints a broad claim.
@pytest.mark.parametrize("enabled", [True, False])
def test_staging_chat_durable_dispatch_mode_is_narrow_and_staging_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    enabled: bool,
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    staging_lines = (
        "UNRELATED=preserved\n"
        "PWC_CHAT_MAX_CONCURRENCY=2\n"
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true\n"
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED=true\n"
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED=false\n"
        "PWC_CHAT_DEEPSEEK_V4_FLASH_PROVIDER=huggingface\n"
    )
    staging_path = config_root / "staging.env"
    staging_path.write_text(staging_lines, encoding="utf-8")
    staging_path.chmod(0o600)
    production_path = config_root / "production.env"
    production_bytes = b"# production bytes must remain exact\nPRODUCTION=untouched\n"
    production_path.write_bytes(production_bytes)
    real_chown = os.chown
    chown_requests = []
    group_requests = []

    def apply_test_identity(path: Path, uid: int, gid: int) -> None:
        chown_requests.append((path, uid, gid))
        real_chown(path, os.getuid(), os.getgid())

    def test_group(group: str) -> SimpleNamespace:
        group_requests.append(group)
        return SimpleNamespace(gr_name=group, gr_gid=os.getgid())

    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(configure_host_env.grp, "getgrnam", test_group)
    monkeypatch.setattr(configure_host_env.os, "chown", apply_test_identity)
    mode = (
        "--staging-chat-durable-dispatch-enable-only"
        if enabled
        else "--staging-chat-durable-dispatch-disable-only"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_host_env.py", "--legacy-env", str(source), mode],
    )

    assert configure_host_env.main() == 0
    assert capsys.readouterr().out == (
        f"{'enabled' if enabled else 'disabled'} staging chat durable dispatch; "
        "no service was restarted\n"
    )
    assert staging_path.read_text(encoding="utf-8") == (
        "PWC_CHAT_DEEPSEEK_V4_FLASH_PROVIDER=huggingface\n"
        f"PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED={'true' if enabled else 'false'}\n"
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true\n"
        "PWC_CHAT_MAX_CONCURRENCY=2\n"
        "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED=false\n"
        "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED=true\n"
        "UNRELATED=preserved\n"
    )
    # The private temporary file (mkstemp) is handed to root:pwc-staging.
    [(temporary, uid, gid)] = chown_requests
    assert Path(temporary).parent == staging_path.parent
    assert Path(temporary).name.startswith(".staging.env.")
    assert (uid, gid) == (0, os.getgid())
    assert group_requests == ["pwc-staging"]
    assert staging_path.stat().st_uid == os.getuid()
    assert staging_path.stat().st_gid == os.getgid()
    assert staging_path.stat().st_mode & 0o777 == 0o640
    assert config_root.stat().st_mode & 0o777 == 0o711
    assert production_path.read_bytes() == production_bytes


# Production break caught: the protected bridge can be mixed with another mode
# or can accept a production confirmation, widening its staging-only authority.
@pytest.mark.parametrize(
    "extra_args",
    [
        ["--staging-chat-capacity-only"],
        ["--staging-chat-durable-dispatch-disable-only"],
        ["--confirm", "DEPLOY_PRODUCTION"],
    ],
)
def test_staging_chat_durable_dispatch_mode_must_run_alone_without_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "staging.env").write_text("KEEP=value\n", encoding="utf-8")
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--staging-chat-durable-dispatch-enable-only",
            *extra_args,
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()
    assert (config_root / "staging.env").read_text(encoding="utf-8") == "KEEP=value\n"
    assert "staging durable dispatch enable/disable must run alone" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_production_chat_pi_prewarm_mode_preserves_other_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text(
        "UNRELATED=preserved\n"
        "PWC_CHAT_ENABLED=true\n"
        "PWC_CHAT_BLANK_POOL_ENABLED=true\n"
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED=true\n"
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED=true\n",
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
    mode = (
        "--production-chat-pi-prewarm-enable-only"
        if enabled
        else "--production-chat-pi-prewarm-disable-only"
    )
    confirm = (
        "ENABLE_PRODUCTION_CHAT_PI_PREWARM"
        if enabled
        else "DISABLE_PRODUCTION_CHAT_PI_PREWARM"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            mode,
            "--confirm",
            confirm,
        ],
    )

    assert configure_host_env.main() == 0
    assert written["path"] == config_root / "production.env"
    assert written["group"] == "pwc-production"
    assert configure_host_env.decoded_value(written["lines"]["UNRELATED"]) == (
        "preserved"
    )
    assert configure_host_env.decoded_value(
        written["lines"]["PWC_CHAT_PI_PREWARM_ENABLED"]
    ) == ("true" if enabled else "false")
    if enabled:
        assert (
            configure_host_env.decoded_value(
                written["lines"]["PWC_CHAT_PI_PREWARM_MODEL"]
            )
            == "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
        )
        assert (
            configure_host_env.decoded_value(
                written["lines"]["PWC_CHAT_PI_PREWARM_REASONING_EFFORT"]
            )
            == "medium"
        )


def test_production_chat_pi_prewarm_mode_requires_exact_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.env"
    source.write_text("SOURCE=unused\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "production.env").write_text(
        "PWC_CHAT_ENABLED=true\n", encoding="utf-8"
    )
    monkeypatch.setattr(configure_host_env, "CONFIG_ROOT", config_root)
    monkeypatch.setattr(configure_host_env.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_host_env.py",
            "--legacy-env",
            str(source),
            "--production-chat-pi-prewarm-enable-only",
        ],
    )

    with pytest.raises(SystemExit):
        configure_host_env.main()
