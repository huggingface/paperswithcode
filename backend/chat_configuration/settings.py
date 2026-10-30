"""Chat configuration, composed into the root application settings.

Each focused group owns one area of chat configuration. Fields keep their flat
``chat_*`` names, so ``PWC_CHAT_*`` environment variables, persisted release
environments, and ``settings.chat_*`` call sites are unchanged.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.chat_configuration import registry
from backend.chat_configuration.registry import ChatModelRecord


class ExternalPiWorkerEndpointConfig(BaseModel):
    """Closed configuration shape for one authenticated loopback worker."""

    model_config = ConfigDict(extra="forbid", strict=True)

    endpoint_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    worker_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    base_url: str = Field(min_length=1, max_length=1000)
    token: str = Field(min_length=32, max_length=8192, repr=False)


class ChatSessionSettings(BaseModel):
    """Chat sessions, turns, and request limits."""

    # Research chat (disabled until the isolated live qualification passes).
    chat_enabled: bool = Field(default=False)
    chat_paper_mentions_enabled: bool = Field(default=False)
    chat_paper_context_timeout_seconds: float = Field(default=20, gt=0, le=60)
    chat_session_limit: int = Field(default=500, ge=1, le=1000)
    chat_session_message_limit: int = Field(default=200, ge=2, le=2000)
    chat_session_byte_limit: int = Field(default=25 * 1024 * 1024, ge=1024)
    chat_user_byte_limit: int = Field(default=100 * 1024 * 1024, ge=1024)
    chat_agent_cwd: str = Field(default="/tmp/pwc-chat-agent")
    chat_recovery_spool_dir: str = Field(default="/tmp/pwc-chat-recovery")
    chat_recovery_spool_max_sessions: int = Field(default=20, ge=1, le=100)
    chat_max_turns: int = Field(default=8, ge=3, le=12)
    chat_timeout_seconds: float = Field(default=180, gt=0, le=300)
    chat_require_auth: bool = Field(default=True)
    chat_show_reasoning: bool = Field(default=True)


class ChatModelSettings(BaseModel):
    """Model routes and the provider choices behind them."""

    # Read-only compatibility inputs for sessions created before the DeepSeek-only
    # registry. They are never exposed in current model discovery.
    chat_glm_route: str = Field(default="zai-org/GLM-5.2:together")
    chat_gemma_route: str = Field(default="google/gemma-4-31B-it:cerebras")
    chat_glm_5_3_flash_route: str = Field(default="zai-org/GLM-5.3-Flash:fastest")
    # Staging-only Hugging Face Inference Providers route. Pin a live provider;
    # `:fastest` hops across backends.
    chat_kimi_route: str = Field(default="moonshotai/Kimi-K3:baseten")
    # Pin a live provider. `:fastest` hops across backends and previously
    # included Hugging Face providers whose mapping was in error.
    chat_deepseek_v4_flash_route: str = Field(
        default="deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    )
    chat_deepseek_v4_flash_openrouter_route: str = Field(
        default="deepseek/deepseek-v4-flash-0731"
    )
    chat_deepseek_v4_flash_provider: Literal["huggingface", "openrouter"] = Field(
        default="huggingface",
        description=(
            "Provider selected for the stable DeepSeek V4 Flash model ID; both "
            "routes remain registered for rolling switches"
        ),
    )
    # Free DeepSeek V4.1 Flash for every signed-in user, billed to the Hugging
    # Face organization behind the title credential. The organization's
    # Inference Providers spending limit is the only budget. Only Novita serves
    # this snapshot; pin it like the other reviewed routes.
    chat_sponsored_deepseek_enabled: bool = Field(default=False)
    chat_sponsored_deepseek_route: str = Field(
        default="deepseek-ai/DeepSeek-V4.1-Flash-1017:novita"
    )
    # A default-off server-funded route enabled only by reviewed environment config.
    # Production discovery and the default model remain unchanged.
    chat_alternative_model_enabled: bool = Field(default=False)
    chat_alternative_model: Literal[
        "openai/gpt-5.6-luna", "google/gemini-3.7-flash"
    ] = Field(default="openai/gpt-5.6-luna")
    # The historical Luna route is OpenRouter-backed. Keep it immutable so
    # existing sessions carrying the old public ID never change providers.
    chat_luna_route: str = Field(default="openai/gpt-5.6-luna")
    chat_openai_direct_enabled: bool = Field(default=False)
    chat_openai_luna_route: str = Field(default="gpt-5.6-luna@openai")
    # The route ID is persisted by sessions and capabilities; only the model
    # it serves changes.
    chat_openai_model: str = Field(default="gpt-6-luna", pattern=r"^gpt-6-luna$")
    chat_openai_service_tier: Literal["default"] = Field(default="default")
    # Read-only compatibility input for rolling back releases whose staging
    # registry still exposed the Terra route.
    chat_terra_route: str = Field(default="openai/gpt-5.6-terra")


class ChatOpenAIBudgetSettings(BaseModel):
    """Direct-OpenAI pricing, allowances, and rate limits."""

    chat_openai_pricing_verified_at: str = Field(default="2026-10-19")
    chat_openai_pricing_max_age_days: int = Field(default=30, ge=1, le=90)
    chat_openai_input_microusd_per_million_tokens: int = Field(default=100_000, ge=1)
    chat_openai_cached_input_microusd_per_million_tokens: int = Field(
        default=10_000, ge=1
    )
    chat_openai_cache_write_microusd_per_million_tokens: int = Field(
        default=125_000, ge=1
    )
    chat_openai_output_microusd_per_million_tokens: int = Field(default=500_000, ge=1)
    chat_openai_monthly_user_budget_usd: Decimal = Field(
        default=Decimal("1.00"), gt=0, le=1000
    )
    chat_openai_workspace_monthly_budget_usd: Decimal = Field(
        default=Decimal("200.00"), gt=0, le=10000
    )
    chat_openai_daily_budget_usd: Decimal = Field(
        default=Decimal("10.00"), gt=0, le=1000
    )
    chat_openai_rate_limit_window_seconds: int = Field(
        default=10 * 60, ge=60, le=24 * 60 * 60
    )
    chat_openai_user_rate_limit_calls: int = Field(default=30, ge=1, le=1000)
    chat_openai_global_rate_limit_calls: int = Field(default=80, ge=1, le=10000)
    chat_openai_user_max_concurrency: int = Field(default=2, ge=1, le=16)
    chat_openai_global_max_concurrency: int = Field(default=4, ge=1, le=64)
    chat_openai_reconciliation_stale_minutes: int = Field(default=15, ge=1, le=24 * 60)


class ChatOpenRouterSettings(BaseModel):
    """OpenRouter credentials, allowances, pricing, and routing."""

    chat_openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for server-funded research chat and titles",
    )
    chat_openrouter_server_funded_enabled: bool = Field(default=False)
    chat_openrouter_monthly_user_budget_usd: Decimal = Field(
        default=Decimal("5.00"), gt=0, le=1000
    )
    chat_openrouter_workspace_monthly_budget_usd: Decimal = Field(
        default=Decimal("200.00"), gt=0, le=10000
    )
    chat_openrouter_daily_budget_usd: Decimal = Field(
        default=Decimal("10.00"), gt=0, le=1000
    )
    chat_openrouter_rate_limit_window_seconds: int = Field(
        default=10 * 60, ge=60, le=24 * 60 * 60
    )
    chat_openrouter_user_rate_limit_calls: int = Field(default=30, ge=1, le=1000)
    chat_openrouter_global_rate_limit_calls: int = Field(default=80, ge=1, le=10000)
    # Kept as read-only aliases during the staging rollback window. New code
    # enforces the per-user and workspace values above.
    chat_openrouter_monthly_budget_usd: Decimal = Field(
        default=Decimal("200.00"), gt=0, le=10000
    )
    chat_openrouter_budget_reserve_usd: Decimal = Field(
        default=Decimal("0.50"), ge=0, le=100
    )
    chat_openrouter_monthly_usage_retention_months: int = Field(
        default=13, ge=13, le=60
    )
    chat_openrouter_provider_call_retention_days: int = Field(default=90, ge=90, le=365)
    chat_openrouter_credential_audit_retention_days: int = Field(
        default=90, ge=1, le=90
    )
    chat_openrouter_recent_auth_seconds: int = Field(default=15 * 60, ge=60, le=60 * 60)
    chat_openrouter_credential_keyring: str = Field(
        default="",
        description="JSON map of encryption-key versions to base64url AES-256 keys",
    )
    chat_openrouter_credential_active_key_version: int = Field(default=1, ge=1)
    chat_openrouter_user_tracking_secret: str = Field(
        default="", description="HMAC secret for opaque OpenRouter user tracking"
    )
    chat_openrouter_pricing_verified_at: str = Field(default="2026-09-04")
    chat_openrouter_pricing_max_age_days: int = Field(default=30, ge=1, le=90)
    chat_openrouter_reconciliation_stale_minutes: int = Field(
        default=15, ge=1, le=24 * 60
    )
    chat_openrouter_drift_alert_microusd: int = Field(
        default=50_000, ge=1, le=10_000_000
    )
    chat_openrouter_input_microusd_per_token: int = Field(default=2, ge=1)
    chat_openrouter_output_microusd_per_token: int = Field(default=9, ge=1)
    chat_openrouter_request_fee_microusd: int = Field(default=10_000, ge=0)
    chat_openrouter_routing_enabled: bool = Field(default=False)
    chat_openrouter_routing_policy: Literal[
        "throughput", "latency", "preferred_provider", "price_performance"
    ] = Field(default="throughput")
    chat_openrouter_preferred_providers: str = Field(default="", max_length=512)
    chat_openrouter_max_prompt_price_per_million_usd: float = Field(
        default=0.28, gt=0, le=100
    )
    chat_openrouter_max_completion_price_per_million_usd: float = Field(
        default=0.56, gt=0, le=100
    )
    chat_openrouter_preferred_max_latency_p90_seconds: float = Field(
        default=3, gt=0, le=60
    )
    chat_openrouter_preferred_min_throughput_p90: float = Field(
        default=50, gt=0, le=10_000
    )


class ChatScopeGuardrailSettings(BaseModel):
    """The server-owned research-scope guardrail."""

    # Server-owned research-scope guardrail. These credentials, limits, and
    # counters are deliberately separate from user inference credentials and
    # the main direct-OpenAI chat allowance.
    chat_scope_guardrail_enabled: bool = Field(default=False)
    chat_scope_guardrail_hf_token: str = Field(default="")
    chat_scope_guardrail_hf_bill_to: str = Field(default="", max_length=200)
    chat_scope_guardrail_glm_model: str = Field(
        default="zai-org/GLM-5.3-Flash:baseten",
        pattern=r"^zai-org/GLM-5\.3-Flash:baseten$",
    )
    chat_scope_guardrail_openai_api_key: str = Field(default="")
    chat_scope_guardrail_openai_model: str = Field(
        default="gpt-6-luna", pattern=r"^gpt-6-luna$"
    )
    chat_scope_guardrail_attempt_timeout_seconds: float = Field(
        default=1.5, ge=0.1, le=1.5
    )
    chat_scope_guardrail_max_prior_messages: int = Field(default=6, ge=0, le=6)
    chat_scope_guardrail_max_context_chars: int = Field(
        default=8_000, ge=8_000, le=8_000
    )
    chat_scope_guardrail_buffer_max_events: int = Field(default=256, ge=8, le=4096)
    chat_scope_guardrail_buffer_max_bytes: int = Field(
        default=2 * 1024 * 1024, ge=64 * 1024, le=16 * 1024 * 1024
    )
    chat_scope_guardrail_max_concurrency: int = Field(default=16, ge=1, le=128)
    chat_scope_guardrail_rate_limit_calls: int = Field(default=600, ge=1, le=100_000)
    chat_scope_guardrail_rate_limit_window_seconds: int = Field(
        default=10 * 60, ge=60, le=24 * 60 * 60
    )
    chat_scope_guardrail_daily_budget_usd: Decimal = Field(
        default=Decimal("5.00"), gt=0, le=1000
    )


class ChatTitleSettings(BaseModel):
    """Chat title generation and its spend limits."""

    chat_title_model: str = Field(default="zai-org/GLM-5.3-Flash:baseten")
    chat_title_provider: str = Field(default="huggingface")
    chat_title_timeout_seconds: float = Field(default=5, gt=0, le=30)
    chat_title_max_tokens: int = Field(default=64, ge=8, le=64)
    chat_title_generation_enabled: bool = Field(default=False)
    chat_title_hf_token: str = Field(
        default="",
        description="Dedicated Hugging Face credential used for production titles",
    )
    chat_title_bill_to: str = Field(
        default="",
        max_length=128,
        description="Hugging Face billing target for production titles",
    )
    chat_title_credential_owner: str = Field(default="", max_length=128)
    chat_title_credential_environment: str = Field(default="", max_length=32)
    chat_title_monthly_cap_microusd: int = Field(default=25_000_000, ge=1)
    chat_title_warning_microusd: int = Field(default=20_000_000, ge=1)
    chat_title_max_call_microusd: int = Field(default=10_000, ge=1)
    chat_title_input_microusd_per_token: int = Field(default=1, ge=1)
    chat_title_output_microusd_per_token: int = Field(default=2, ge=1)


class ChatAdmissionSettings(BaseModel):
    """Admission, rollout percentages, and active-turn capacity."""

    # Protected emergency active-turn limit. Deployed profiles stay at their
    # qualified 1/2-turn values until a separate load qualification raises it.
    chat_max_concurrency: int = Field(default=1, ge=1, le=100)
    chat_user_max_concurrency: int = Field(default=2, ge=1, le=8)
    chat_public_admission_enabled: bool = Field(default=True)
    chat_sandbox_admission_enabled: bool = Field(default=True)
    chat_default_backend: str = Field(
        default="local_mcp", pattern=r"^(local_mcp|modal_cli)$"
    )
    chat_new_chat_modal_percentage: int = Field(default=0, ge=0, le=100)
    chat_default_agent_harness: Literal["claude", "pi"] = Field(default="claude")
    # The migration deliberately supports only the protected stop/full-cutover
    # states. Pi qualification uses an authenticated per-session override.
    chat_new_session_pi_percentage: int = Field(default=0, ge=0, le=100)
    chat_sandbox_total_live_cap: int = Field(default=2, ge=1, le=16)


class ChatRuntimeSettings(BaseModel):
    """The pinned agent runtime and Pi harness identity."""

    chat_pi_version: str = Field(default="", max_length=64)
    chat_pi_runtime_enabled: bool = Field(default=False)
    chat_pi_source_commit: str = Field(default="", pattern=r"^(?:[0-9a-f]{40})?$")
    chat_claude_sdk_version: str = Field(default="", max_length=64)
    chat_pi_node_version: str = Field(default="", max_length=64)
    chat_pi_node_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    chat_restricted_hf_cli_version: str = Field(default="", max_length=64)
    chat_pi_self_extension_enabled: Literal[False] = Field(default=False)
    chat_pi_durable_extensions_enabled: Literal[False] = Field(default=False)
    chat_pi_max_extension_files: Literal[0] = Field(default=0)
    chat_pi_max_extension_bytes: Literal[0] = Field(default=0)
    chat_pi_max_reloads_per_turn: Literal[0] = Field(default=0)
    chat_modal_image_version: str = Field(default="", max_length=255)
    chat_pwc_cli_version: str = Field(default="", max_length=64)
    chat_worker_contract_version: str = Field(default="", max_length=64)
    chat_system_prompt_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    chat_pi_prewarm_enabled: bool = Field(default=False)
    chat_pi_prewarm_model: str = Field(default="", max_length=255)
    chat_pi_prewarm_reasoning_effort: Literal["low", "medium", "high", "max"] = Field(
        default="medium"
    )
    chat_pi_provider_adapter_contract: str = Field(default="1", max_length=64)


class ChatExternalPiSettings(BaseModel):
    """External Pi workers, durable dispatch, and the executor bridge."""

    # External-harness migration controls remain independently fail-closed.
    # Chat work is staging-only until a separate production authorization.
    chat_external_pi_shadow_enabled: bool = Field(default=False)
    chat_external_pi_admission_enabled: bool = Field(default=False)
    chat_external_pi_supervisor_enabled: bool = Field(default=False)
    chat_external_pi_ready_registry_enabled: bool = Field(default=False)
    chat_external_pi_runtime_contract_version: str = Field(default="", max_length=64)
    chat_external_pi_worker_id: str = Field(default="", max_length=128)
    chat_external_pi_worker_url: str = Field(default="", max_length=1000)
    chat_external_pi_worker_token: str = Field(default="", repr=False)
    chat_external_pi_worker_endpoints: list[ExternalPiWorkerEndpointConfig] = Field(
        default_factory=list, max_length=16, repr=False
    )
    chat_external_pi_worker_contract_version: str = Field(default="", max_length=64)
    chat_qualification_evidence_retention_hours: int = Field(default=24, ge=1, le=168)
    chat_external_pi_worker_max_sessions: int = Field(default=8, ge=1, le=64)
    chat_external_pi_heartbeat_seconds: float = Field(default=10, ge=1, le=30)
    chat_external_pi_lease_seconds: int = Field(default=30, ge=5, le=60)
    chat_external_pi_startup_timeout_seconds: int = Field(default=60, ge=5, le=300)
    chat_external_pi_drain_seconds: int = Field(default=60, ge=5, le=300)
    chat_external_pi_drain_poll_seconds: float = Field(default=1, ge=0.1, le=5)
    chat_remote_workspace_tools_enabled: bool = Field(default=False)
    # Inert Phase-2 executor bridge. These controls may be qualified on staging
    # without admitting any external Pi traffic.
    chat_sandbox_executor_enabled: bool = Field(default=False)
    chat_sandbox_executor_contract_version: str = Field(default="", max_length=64)
    chat_remote_bash_enabled: bool = Field(default=False)
    chat_remote_read_enabled: bool = Field(default=False)
    chat_safe_cli_fast_path_enabled: bool = Field(default=False)
    chat_lazy_workspace_enabled: bool = Field(default=False)
    chat_durable_turn_dispatch_enabled: bool = Field(default=False)
    chat_turn_event_journal_schema_enabled: bool = Field(default=False)
    chat_turn_event_replay_grace_seconds: int = Field(default=300, ge=30, le=3600)
    chat_turn_event_cleanup_batch_size: int = Field(default=100, ge=1, le=100)
    chat_executor_remote_transport_enabled: bool = Field(default=False)
    chat_executor_max_parallel_operations: Literal[4] = Field(default=4)
    chat_executor_cell_id: str = Field(default="", max_length=64)
    chat_executor_admission_signing_key_file: str = Field(default="", max_length=1000)
    chat_executor_admission_signing_key_id: str = Field(default="", max_length=64)
    chat_executor_admission_key_not_before_ms: int = Field(default=0, ge=0)
    chat_executor_admission_key_not_after_ms: int = Field(default=0, ge=0)
    chat_executor_harness_key_id: str = Field(default="", max_length=128)
    chat_executor_authorization_key_id: str = Field(default="", max_length=128)
    chat_executor_authorization_keys_json: str = Field(default="", max_length=4096)


class ChatArtifactSettings(BaseModel):
    """Artifacts, Posterly, LaTeX papers, and MCP Apps."""

    # Protected remote MCP App controls. Both must be enabled before tools
    # are registered; either is an immediate fail-closed kill switch.
    chat_excalidraw_enabled: bool = Field(default=False)
    chat_mcp_apps_host_enabled: bool = Field(default=False)
    # Staging-only Posterly artifact controls. Historical safe PNG cards remain
    # readable when generation flags are disabled.
    chat_artifacts_enabled: bool = Field(default=False)
    chat_posterly_enabled: bool = Field(default=False)
    # Paper creation is independently disabled until the private storage and
    # compiler path have completed staging qualification.
    chat_latex_paper_enabled: bool = Field(default=False)
    chat_latex_paper_timeout_seconds: float = Field(default=600, ge=60, le=600)
    chat_latex_paper_max_tool_rounds: int = Field(default=12, ge=3, le=20)
    chat_latex_paper_max_tool_calls: int = Field(default=30, ge=12, le=40)
    chat_latex_paper_max_direct_search_calls: int = Field(default=8, ge=1, le=8)
    # Private staging-only compiler boundary. The signing private key belongs
    # only in the PwC backend environment; each disposable Sandbox receives
    # its matching public key only through its per-job environment.
    chat_latex_compiler_jobs_enabled: bool = Field(default=False)
    # Qualification may exercise a sealed Sandbox while paper/compiler job
    # admission remains off. This staging-only flag never enables user work.
    chat_latex_compiler_qualification_mode: bool = Field(default=False)
    # A per-job HF Sandbox is the only application transport. The image is
    # deliberately blank by default so staging cannot accidentally create a VM.
    chat_latex_compiler_hf_sandbox_image: str = Field(default="", max_length=1000)
    chat_latex_compiler_hf_sandbox_namespace: str = Field(default="", max_length=128)
    chat_latex_compiler_hf_sandbox_token: str = Field(default="")
    chat_latex_compiler_hf_sandbox_flavor: Literal["cpu-basic", "cpu-upgrade"] = Field(
        default="cpu-upgrade"
    )
    chat_latex_compiler_hf_sandbox_idle_timeout_seconds: int = Field(
        default=180, ge=60, le=600
    )
    chat_latex_compiler_hf_sandbox_egress_policy_attestation: str = Field(
        default="", max_length=128
    )
    chat_latex_compiler_signing_private_key: str = Field(default="")
    chat_artifact_shared_preview_enabled: bool = Field(default=False)
    chat_artifact_storage_backend: Literal["local", "hf_bucket"] = Field(
        default="local"
    )
    chat_artifact_hf_bucket_id: str = Field(default="", max_length=255)
    chat_artifact_hf_bucket_prefix: str = Field(
        default="chat-artifacts", min_length=1, max_length=200
    )
    chat_artifact_local_dir: str = Field(
        default="/var/lib/paperswithcode/chat-artifacts"
    )
    chat_artifact_max_files: int = Field(default=100, ge=4, le=100)
    chat_artifact_max_text_bytes: int = Field(
        default=2 * 1024 * 1024, ge=1024, le=2 * 1024 * 1024
    )
    chat_artifact_max_image_bytes: int = Field(
        default=8 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024
    )
    chat_artifact_max_pdf_bytes: int = Field(
        default=20 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024
    )
    chat_artifact_max_version_bytes: int = Field(
        default=32 * 1024 * 1024, ge=4096, le=32 * 1024 * 1024
    )
    chat_artifact_owner_quota_bytes: int = Field(
        default=250 * 1024 * 1024, ge=4096, le=250 * 1024 * 1024
    )
    chat_artifact_max_versions_per_turn: int = Field(default=4, ge=1, le=4)
    chat_artifact_max_session_artifacts: int = Field(default=10, ge=1, le=10)
    chat_artifact_preview_max_pixels: int = Field(
        default=20_000_000, ge=1_000_000, le=20_000_000
    )
    chat_posterly_timeout_seconds: float = Field(default=600, ge=60, le=600)
    chat_posterly_max_tool_rounds: int = Field(default=20, ge=8, le=20)
    chat_posterly_max_tool_calls: int = Field(default=40, ge=12, le=40)
    chat_posterly_tool_result_max_bytes: int = Field(
        default=192 * 1024, ge=24 * 1024, le=192 * 1024
    )
    chat_posterly_turn_tool_output_max_bytes: int = Field(
        default=1024 * 1024, ge=96 * 1024, le=1024 * 1024
    )
    chat_posterly_source_commit: str = Field(
        default="b9f42e5578a49a27525a68f85376bb3bb25af86f",
        pattern=r"^[0-9a-f]{40}$",
    )
    chat_posterly_playwright_version: str = Field(default="1.62.0", max_length=32)
    chat_posterly_chromium_revision: str = Field(default="1234", max_length=16)


class ChatToolSettings(BaseModel):
    """Agent tools: catalog, web search, and Hugging Face Hub access."""

    chat_max_search_calls: int = Field(default=2, ge=1, le=5)
    chat_pwc_mcp_enabled: bool = Field(default=False)
    chat_max_tool_calls: int = Field(default=12, ge=1, le=24)
    chat_max_direct_search_calls: int = Field(default=4, ge=1, le=8)
    chat_web_search_enabled: bool = Field(default=False)
    chat_web_search_provider: str = Field(default="exa", pattern=r"^exa$")
    chat_web_search_exa_api_key: str = Field(
        default="", description="Server-only Exa credential for research chat"
    )
    chat_web_search_exa_url: str = Field(default="https://api.exa.ai/search")
    chat_web_search_max_calls: int = Field(default=3, ge=1, le=3)
    chat_web_search_timeout_seconds: float = Field(default=3, gt=0, le=3)
    chat_web_search_result_count: int = Field(default=5, ge=1, le=5)
    chat_web_search_max_result_bytes: int = Field(
        default=16 * 1024, ge=4 * 1024, le=16 * 1024
    )
    chat_web_search_query_max_chars: int = Field(default=500, ge=1, le=500)
    chat_web_search_monthly_warning_calls: int = Field(default=5000, ge=1)
    chat_web_search_monthly_hard_calls: int = Field(default=6000, ge=1)
    chat_web_search_transient_cooldown_seconds: int = Field(default=60, ge=5, le=3600)
    chat_web_search_domain_denylist: str = Field(default="")
    chat_hf_catalog_enabled: bool = Field(default=False)
    chat_hf_catalog_timeout_seconds: float = Field(default=10, gt=0, le=10)
    chat_hf_catalog_max_calls: int = Field(default=6, ge=1, le=6)
    chat_hf_recursive_list_max_calls: int = Field(default=2, ge=1, le=2)
    chat_hf_discovery_max_limit: int = Field(default=50, ge=1, le=50)
    chat_hf_max_files: int = Field(default=200, ge=1, le=200)
    chat_hf_max_depth: int = Field(default=10, ge=1, le=10)
    chat_hf_card_metadata_max_bytes: int = Field(
        default=32 * 1024, ge=1024, le=32 * 1024
    )
    chat_hf_card_text_max_bytes: int = Field(default=192 * 1024, ge=4096, le=192 * 1024)
    chat_hf_card_total_max_bytes: int = Field(
        default=224 * 1024, ge=4096, le=224 * 1024
    )
    chat_hf_cache_max_entries: int = Field(default=512, ge=1, le=512)
    chat_hf_cache_max_bytes: int = Field(
        default=64 * 1024 * 1024, ge=4096, le=64 * 1024 * 1024
    )
    chat_hf_response_max_bytes: int = Field(default=256 * 1024, ge=4096, le=256 * 1024)
    chat_bash_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_tool_result_max_bytes: int = Field(default=24 * 1024, ge=1024)
    chat_turn_tool_output_max_bytes: int = Field(default=96 * 1024, ge=4096)


class ChatSandboxSettings(BaseModel):
    """Sandbox resources, timeouts, and warm pools."""

    chat_sandbox_ready_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_agent_timeout_seconds: float = Field(default=180, gt=0, le=600)
    chat_cancel_grace_seconds: float = Field(default=2, ge=0, le=10)
    chat_sandbox_cpu: float = Field(default=1, gt=0, le=8)
    chat_sandbox_memory_mib: int = Field(default=2048, ge=512, le=16384)
    chat_sandbox_cpu_limit: float | None = Field(default=None, gt=0, le=8)
    chat_sandbox_memory_limit_mib: int | None = Field(default=None, ge=512, le=16384)
    chat_sandbox_pids_max: int = Field(default=64, ge=16, le=512)
    chat_sandbox_warm_seconds: int = Field(default=300, ge=0, le=3600)
    chat_sandbox_max_warm: int = Field(default=10, ge=0, le=1000)
    chat_persistent_worker_enabled: bool = Field(default=False)
    chat_worker_ready_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_persistent_sandbox_lifetime_seconds: int = Field(
        default=86400, ge=300, le=86400
    )
    chat_blank_pool_enabled: bool = Field(default=False)
    chat_blank_pool_min: int = Field(default=1, ge=0, le=8)
    chat_blank_pool_max: int = Field(default=1, ge=0, le=8)
    chat_blank_pool_min_remaining_seconds: int = Field(default=240, ge=60, le=3600)
    chat_blank_pool_rotate_before_seconds: int = Field(default=3600, ge=60, le=43200)
    chat_blank_pool_refill_concurrency: int = Field(default=1, ge=1, le=4)
    chat_workspace_snapshots_enabled: bool = Field(default=False)
    chat_workspace_snapshot_inactivity_days: int = Field(default=30, ge=1, le=90)


class ChatSandboxSpendSettings(BaseModel):
    """Sandbox spend caps, reconciliation, and alert routing."""

    # Read-only compatibility for old environment files during rolling deploys.
    # Enforcement intentionally ignores these blank-only floating-point values.
    chat_blank_pool_monthly_budget_usd: float = Field(default=35, gt=0, le=1000)
    chat_blank_pool_reported_month_to_date_usd: float = Field(default=0, ge=0, le=10000)
    chat_sandbox_warning_microusd: int = Field(default=75_000_000, ge=1)
    chat_sandbox_spend_enforcement_enabled: bool = Field(default=False)
    chat_sandbox_application_cap_microusd: int = Field(default=100_000_000, ge=1)
    chat_sandbox_environment_cap_microusd: int = Field(default=0, ge=0)
    chat_sandbox_workspace_cap_microusd: int = Field(default=250_000_000, ge=1)
    chat_sandbox_provider_mode: Literal["starter_workspace", "team_environments"] = (
        "starter_workspace"
    )
    chat_sandbox_budget_attestation: str = Field(default="", max_length=128)
    chat_sandbox_modal_environment: str = Field(default="", max_length=128)
    chat_sandbox_modal_workspace: str = Field(default="", max_length=128)
    chat_sandbox_modal_owner_username: str = Field(default="", max_length=128)
    chat_sandbox_watchdog_seconds: int = Field(default=15, ge=5, le=60)
    chat_sandbox_drain_grace_seconds: int = Field(default=30, ge=0, le=30)
    chat_sandbox_termination_grace_seconds: int = Field(default=30, ge=5, le=120)
    chat_sandbox_reconciliation_allowance_microusd: int = Field(default=1_000_000, ge=0)
    chat_sandbox_reconciliation_interval_seconds: int = Field(
        default=3600, ge=3600, le=3600
    )
    chat_sandbox_reconciliation_stale_seconds: int = Field(
        default=7200, ge=3600, le=86400
    )
    chat_sandbox_provider_floor_microusd: int = Field(default=0, ge=0)
    chat_sandbox_provider_reported_at: str = Field(default="", max_length=64)
    chat_sandbox_slack_webhook_url: str = Field(default="", max_length=2000)
    chat_sandbox_alert_fallback_webhook_url: str = Field(default="", max_length=2000)
    chat_sandbox_runbook_url: str = Field(default="", max_length=2000)
    chat_sandbox_operator_usernames: str = Field(default="", max_length=500)


class ChatOperationalAlertSettings(BaseModel):
    """Provider and lifecycle operational alerts."""

    chat_operational_alerts_enabled: bool = Field(default=False)
    chat_provider_alert_window_seconds: int = Field(default=300, ge=60, le=900)
    chat_provider_alert_min_failures: int = Field(default=5, ge=2, le=100)
    chat_provider_alert_failure_percent: int = Field(default=50, ge=1, le=100)
    chat_lifecycle_alert_window_seconds: int = Field(default=300, ge=60, le=900)
    chat_lifecycle_alert_min_samples: int = Field(default=5, ge=2, le=100)
    chat_lifecycle_alert_failure_percent: int = Field(default=50, ge=1, le=100)
    chat_lifecycle_capacity_saturation_count: int = Field(default=5, ge=1, le=100)
    chat_lifecycle_workspace_create_percent: int = Field(default=75, ge=1, le=100)
    chat_lifecycle_ttft_threshold_ms: int = Field(default=10_000, ge=100, le=120_000)
    chat_lifecycle_ttft_regression_percent: int = Field(default=50, ge=1, le=100)


class ChatGatewaySettings(BaseModel):
    """The private model gateway and its payload policy."""

    chat_initial_payload_optimization_enabled: bool = Field(default=False)
    chat_initial_payload_optimization_candidate: Literal[
        "system_duplicates", "tool_duplicates"
    ] = Field(default="system_duplicates")
    chat_gateway_url: str = Field(default="", max_length=1000)


class ChatObservabilitySettings(BaseModel):
    """Trace export to Trackio and Langfuse."""

    chat_trackio_enabled: bool = Field(default=False)
    chat_trackio_url: str = Field(
        default="",
        pattern=r"^(https://[a-z0-9][a-z0-9-]*\.hf\.space/?)?$",
    )
    chat_trackio_hf_token: str = Field(default="", repr=False)
    chat_trackio_project: str = Field(default="pwc-chat", min_length=1, max_length=100)
    chat_langfuse_enabled: bool = Field(default=False)
    chat_langfuse_trace_content_access_enabled: bool = Field(default=False)


class ChatSettings(
    ChatSessionSettings,
    ChatModelSettings,
    ChatOpenAIBudgetSettings,
    ChatOpenRouterSettings,
    ChatScopeGuardrailSettings,
    ChatTitleSettings,
    ChatAdmissionSettings,
    ChatRuntimeSettings,
    ChatExternalPiSettings,
    ChatArtifactSettings,
    ChatToolSettings,
    ChatSandboxSettings,
    ChatSandboxSpendSettings,
    ChatOperationalAlertSettings,
    ChatGatewaySettings,
    ChatObservabilitySettings,
):
    """Every chat setting group plus the derived model registry views."""

    @model_validator(mode="after")
    def preserve_staging_artifacts_when_scope_guarded(self) -> "ChatSettings":
        """Keep non-Posterly research artifacts across the legacy host launcher."""

        if self.environment == "staging" and self.chat_scope_guardrail_enabled:
            self.chat_artifacts_enabled = True
            self.chat_artifact_shared_preview_enabled = True
        return self

    @property
    def chat_model_records(self) -> tuple[ChatModelRecord, ...]:
        return registry.chat_model_records(self)

    @property
    def chat_model_registry(self) -> tuple[dict[str, str], ...]:
        return tuple(record.as_choice() for record in self.chat_model_records)

    @staticmethod
    def chat_transport_provider(provider: str) -> str:
        return provider

    @property
    def chat_openrouter_routes(self) -> tuple[str, ...]:
        return registry.openrouter_routes(self)

    @property
    def chat_model_choices(self) -> tuple[dict[str, str], ...]:
        return tuple(
            record.as_choice() for record in registry.discoverable_records(self)
        )

    @property
    def chat_model_routes(self) -> dict[str, str]:
        return registry.model_routes(self)

    @property
    def chat_model_providers(self) -> dict[str, str]:
        return registry.model_providers(self)

    @property
    def chat_model_labels(self) -> dict[str, str]:
        return registry.model_labels(self)

    @property
    def chat_route_protocols(self) -> dict[str, str]:
        return registry.route_protocols(self)

    @property
    def chat_route_provider_models(self) -> dict[str, str]:
        return registry.route_provider_models(self)

    @property
    def chat_route_funding_modes(self) -> dict[str, str]:
        return registry.route_funding_modes(self)

    @property
    def chat_route_providers(self) -> dict[str, str]:
        return registry.route_providers(self)

    @property
    def chat_effective_pi_prewarm_model(self) -> str:
        return registry.effective_pi_prewarm_model(self)

    @property
    def chat_sandbox_operator_username_set(self) -> set[str]:
        return {
            name.strip().lower()
            for name in self.chat_sandbox_operator_usernames.split(",")
            if name.strip()
        }
