"""
Configuration management for the FastAPI backend.
"""

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.services.paper_markdown_job_profile import (
    PAPER_MARKDOWN_BACKFILL_JOB_PROFILE,
    PAPER_MARKDOWN_LIVE_JOB_PROFILE,
)


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


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=["keys.env"], env_prefix="PWC_")

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Host to bind the server")
    port: int = Field(default=8000, description="Port to bind the server")
    environment: str = Field(
        default="development",
        description="Environment (development, staging, production)",
    )
    log_level: str = Field(default="INFO", description="Log level")
    release_id: str = Field(default="development")
    frontend_dist_dir: str = Field(default="")
    runtime_data_dir: str = Field(default="./runtime")
    cron_log_dir: str = Field(default="./.github/workflows/scripts/logs")
    cron_lock_dir: str = Field(default="./.github/workflows/scripts/locks")

    # Database configuration
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="paperswithcode_hf", description="Database name")
    db_user: str = Field(default="nielsrogge", description="Database user")
    db_password: str = Field(default="", description="Database password")
    db_search_path: str = Field(default="public")

    # CORS configuration
    allowed_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
        ],
        description="Allowed CORS origins for non-production environments",
    )
    extra_allowed_origins: str = Field(
        default="",
        description=(
            "Comma-separated list of additional CORS origins. "
            "Used to allow the Hugging Face Space mirror (e.g. "
            "https://nielsr-paperswithcode.hf.space) to call the production "
            "API."
        ),
    )
    extra_allowed_origin_regex: str = Field(
        default="",
        description=(
            "Optional regex of additional CORS origins. Useful to allow "
            "any Hugging Face Space subdomain via something like "
            r"'^https://[a-z0-9-]+\\.hf\\.space$'."
        ),
    )

    # API configuration
    default_page_size: int = Field(
        default=50, description="Default page size for paginated responses"
    )
    max_page_size: int = Field(
        default=500, description="Maximum page size for paginated responses"
    )

    # Trending ranking mode for the papers feed:
    #   "github"    -> rank by official GitHub repo star velocity (current/default;
    #                  the instant rollback path).
    #   "composite" -> rank by papers.trending_score (GitHub velocity + Hugging Face
    #                  artifact trending), computed by calculate_paper_trending_scores.
    # Set PWC_TRENDING_RANKING_MODE=composite to switch the public feed.
    trending_ranking_mode: str = Field(
        default="github",
        description="Papers trending ranking mode: 'github' or 'composite'",
    )

    paper_search_mode: Literal["keyword", "semantic", "hybrid"] = Field(
        default="keyword",
        description="Default paper search mode: keyword, semantic, or hybrid",
    )
    related_papers_mode: Literal["task", "embedding"] = Field(
        default="task",
        description="Related-paper mode: 'task' or 'embedding'",
    )
    embedding_generation_id: int | None = Field(
        default=None,
        description="Optional ready/active embedding generation override",
    )
    related_papers_min_similarity: float | None = Field(
        default=None,
        description="Judgment-calibrated dense similarity floor; unset means no floor",
    )
    query_embedder: Literal["disabled", "hf_endpoint"] = Field(
        default="disabled",
        description="Query encoder: 'disabled' or 'hf_endpoint'",
    )
    hf_query_embedding_endpoint_url: str = Field(
        default="",
        description="Protected HF Inference Endpoint URL for encode_query",
    )
    query_embedding_timeout_ms: int = Field(default=500, ge=50, le=5000)
    query_embedding_max_concurrency: int = Field(default=4, ge=1, le=32)
    hybrid_rrf_k: int = Field(default=60, ge=1, le=1000)
    hybrid_lexical_weight: float = Field(default=1.0, gt=0)
    hybrid_semantic_weight: float = Field(default=1.0, gt=0)

    # ArXiv configuration
    arxiv_base_url: str = Field(
        default="https://arxiv.org", description="ArXiv base URL"
    )

    # Application URLs
    app_domain: str = Field(
        default="paperswithcode.ai", description="Application domain for URL generation"
    )

    # Semantic Scholar API configuration
    semantic_scholar_api_key: str = Field(
        default="", description="Semantic Scholar API key for citation data"
    )
    semantic_scholar_api_key_2: str = Field(
        default="",
        description="Secondary Semantic Scholar key reserved for historical backfills",
    )
    openalex_api_key: str = Field(
        default="", description="Optional OpenAlex API key for historical backfills"
    )

    # LLM API keys
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")
    datalab_api_key: str = Field(default="", description="Datalab API key")

    # Admin API configuration
    admin_api_token: str = Field(
        default="",
        description="API token required for administrative endpoints",
    )
    autonomous_submission_enabled: bool = Field(default=False)
    autonomous_submission_callback_secret: str = Field(default="")
    autonomous_submission_callback_base_url: str = Field(
        default="https://paperswithcode.co/api/v1"
    )
    autonomous_submission_run_budget_usd: Decimal = Field(
        default=Decimal("5"), gt=0, le=100
    )
    autonomous_submission_jobs_enabled: bool = Field(default=False)
    autonomous_submission_hf_namespace: str = Field(default="")
    autonomous_submission_hf_token: str = Field(default="")
    autonomous_submission_openai_api_key: str = Field(default="")
    autonomous_submission_job_image: str = Field(default="")
    autonomous_alert_slack_webhook_url: str = Field(default="", max_length=2000)
    autonomous_alert_fallback_webhook_url: str = Field(default="", max_length=2000)
    autonomous_digest_webhook_url: str = Field(default="", max_length=2000)
    autonomous_alert_runbook_url: str = Field(default="", max_length=2000)
    autonomous_submission_job_timeout_seconds: int = Field(
        default=1800, ge=300, le=3600
    )
    autonomous_submission_codex_timeout_seconds: int = Field(
        default=1200, ge=60, le=1800
    )
    autonomous_submission_max_active_jobs: int = Field(default=1, ge=1, le=1)
    autonomous_submission_input_usd_per_million: Decimal = Field(
        default=Decimal("0"), ge=0
    )
    autonomous_submission_cached_input_usd_per_million: Decimal = Field(
        default=Decimal("0"), ge=0
    )
    autonomous_submission_output_usd_per_million: Decimal = Field(
        default=Decimal("0"), ge=0
    )

    # Codex curation jobs. Immutable production releases may opt in; staging
    # remains disabled because its catalog role is read-only.
    codex_add_evals_enabled: bool = Field(default=False)
    codex_enrich_paper_enabled: bool = Field(default=False)
    codex_add_evals_timeout_seconds: int = Field(default=3600, ge=60, le=7200)
    codex_add_evals_work_dir: str = Field(
        default="/root/python_projects/paperswithcode"
    )
    codex_add_evals_spool_dir: str = Field(default="/tmp/pwc-codex-add-evals")
    # Remote paper-curation workers run on Hugging Face Jobs. Keep these
    # credentials separate from the general Hub token and database credentials.
    codex_jobs_enabled: bool = Field(default=False)
    # Deliberately has no default: launching into the wrong organization can
    # fail with a generic Hub 403 and leaves no remote Job to inspect.
    codex_jobs_namespace: str = Field(default="")
    codex_jobs_token: str = Field(default="")
    codex_jobs_openai_api_key: str = Field(default="")
    codex_jobs_image: str = Field(
        default="hf.co/spaces/nielsr/pwc-codex-curator-87ebc81c234c"
    )
    codex_jobs_image_revision: str = Field(
        default="556b5d14b762684586030d3018999dae392200c9"
    )
    codex_jobs_api_url: str = Field(default="https://paperswithcode.co/api/v1")
    codex_jobs_timeout_seconds: int = Field(default=5400, ge=300, le=14400)
    codex_jobs_cli_version: str = Field(default="0.75.0")
    codex_jobs_model: str = Field(default="gpt-5.6-luna")
    codex_jobs_reasoning_effort: str = Field(default="medium")
    codex_jobs_max_active: int = Field(default=4, ge=1, le=16)
    codex_jobs_max_scheduled_active: int = Field(default=3, ge=0, le=15)
    codex_curation_scheduler_enabled: bool = Field(default=False)
    codex_curation_direct_apply_enabled: bool = Field(default=False)
    codex_curation_trace_upload_enabled: bool = Field(default=False)
    codex_curation_trace_hf_bucket_id: str = Field(default="")
    codex_curation_policy_version: str = Field(default="hf-daily-v1")
    codex_curation_queue_depth: int = Field(default=200, ge=1, le=2000)
    codex_curation_reconcile_limit: int = Field(default=200, ge=1, le=500)
    codex_curation_canary_limit: int = Field(default=10, ge=1, le=100)

    # Hugging Face OAuth configuration (for "Sign in with Hugging Face")
    hf_oauth_client_id: str = Field(
        default="",
        description="Client ID of the Hugging Face OAuth application",
    )
    hf_oauth_client_secret: str = Field(
        default="",
        description="Client secret of the Hugging Face OAuth application",
    )
    hf_oauth_credential_secret: str = Field(
        default="",
        description=(
            "Shared secret used to encrypt OAuth inference credentials for "
            "production and staging"
        ),
    )
    jwt_secret: str = Field(
        default="",
        description="HS256 secret used to sign the session and OAuth state JWTs",
    )
    production_jwt_fingerprint: str = Field(
        default="",
        description="SHA-256 fingerprint used by staging to reject the production secret",
    )
    admin_hf_usernames: str = Field(
        default="",
        description="Comma-separated list of HF usernames allowed to perform admin actions",
    )
    admin_hf_subjects: str = Field(
        default="",
        description="Comma-separated immutable HF OAuth subjects with admin access",
    )
    contributor_hf_subjects: str = Field(
        default="",
        description="Comma-separated immutable HF OAuth subjects with contributor access",
    )
    contributor_direct_edits_enabled: bool = Field(
        default=False,
        description="Enable audited direct contributor catalog edits in production",
    )
    submission_max_active_pending: int = Field(default=50, ge=1, le=1000)
    submission_hourly_subject_limit: int = Field(default=20, ge=1, le=1000)
    submission_hourly_ip_limit: int = Field(default=100, ge=1, le=10000)
    submission_max_payload_bytes: int = Field(default=262_144, ge=1024, le=2_097_152)
    session_cookie_domain: str = Field(
        default="",
        description=(
            "Optional Domain attribute for the session cookie. Empty keeps the "
            "cookie host-only (current behaviour). Set to '.paperswithcode.co' "
            "so one production sign-in is also valid on subdomains such as "
            "staging.paperswithcode.co (whose OAuth redirect URL is not "
            "registered with the HF app)."
        ),
    )
    session_cookie_name: str = Field(default="pwc_session")
    shared_session_cookie_name: str = Field(default="")
    shared_session_cookie_domain: str = Field(default="")
    session_signing_private_key: str = Field(
        default="",
        description="Base64url Ed25519 private key; configured only on production",
    )
    session_verification_public_key: str = Field(
        default="",
        description="Base64url Ed25519 public key shared with session verifiers",
    )
    auth_authority_origin: str = Field(
        default="",
        description="Canonical origin that owns OAuth login and session issuance",
    )
    auth_return_origins: str = Field(
        default="",
        description="Comma-separated origins accepted as OAuth return destinations",
    )

    # Hugging Face API configuration
    hf_token: str = Field(
        default="", description="Hugging Face API token for higher rate limits"
    )

    # Research chat (disabled until the isolated live qualification passes).
    chat_enabled: bool = Field(default=False)
    native_pdf_reader_enabled: bool = Field(default=False)
    paper_reader_chat_enabled: bool = Field(default=False)
    paper_reader_selection_enabled: bool = Field(default=False)
    chat_paper_mentions_enabled: bool = Field(default=False)
    chat_paper_context_timeout_seconds: float = Field(default=20, gt=0, le=60)
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
    chat_openai_model: str = Field(default="gpt-5.6-luna", pattern=r"^gpt-5\.6-luna$")
    chat_openai_service_tier: Literal["default"] = Field(default="default")
    chat_openai_pricing_verified_at: str = Field(default="2026-08-20")
    chat_openai_pricing_max_age_days: int = Field(default=30, ge=1, le=90)
    chat_openai_input_microusd_per_million_tokens: int = Field(default=200_000, ge=1)
    chat_openai_cached_input_microusd_per_million_tokens: int = Field(
        default=20_000, ge=1
    )
    chat_openai_cache_write_microusd_per_million_tokens: int = Field(
        default=250_000, ge=1
    )
    chat_openai_output_microusd_per_million_tokens: int = Field(default=1_200_000, ge=1)
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
        default="gpt-5.6-luna", pattern=r"^gpt-5\.6-luna$"
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
    # Read-only compatibility input for rolling back releases whose staging
    # registry still exposed the Terra route.
    chat_terra_route: str = Field(default="openai/gpt-5.6-terra")
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
    chat_session_limit: int = Field(default=100, ge=1, le=1000)
    chat_session_message_limit: int = Field(default=200, ge=2, le=2000)
    chat_session_byte_limit: int = Field(default=25 * 1024 * 1024, ge=1024)
    chat_user_byte_limit: int = Field(default=100 * 1024 * 1024, ge=1024)
    chat_agent_cwd: str = Field(default="/tmp/pwc-chat-agent")
    chat_recovery_spool_dir: str = Field(default="/tmp/pwc-chat-recovery")
    chat_recovery_spool_max_sessions: int = Field(default=20, ge=1, le=100)
    chat_max_turns: int = Field(default=8, ge=3, le=12)
    chat_max_search_calls: int = Field(default=2, ge=1, le=5)
    chat_timeout_seconds: float = Field(default=180, gt=0, le=300)
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
    chat_external_pi_worker_max_sessions: int = Field(default=8, ge=1, le=32)
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
    chat_modal_image_version: str = Field(default="", max_length=255)
    chat_pwc_cli_version: str = Field(default="", max_length=64)
    chat_worker_contract_version: str = Field(default="", max_length=64)
    chat_system_prompt_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
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
    chat_web_search_monthly_warning_calls: int = Field(default=1000, ge=1)
    chat_web_search_monthly_hard_calls: int = Field(default=1200, ge=1)
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
    chat_sandbox_ready_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_agent_timeout_seconds: float = Field(default=180, gt=0, le=600)
    chat_bash_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_cancel_grace_seconds: float = Field(default=2, ge=0, le=10)
    chat_tool_result_max_bytes: int = Field(default=24 * 1024, ge=1024)
    chat_turn_tool_output_max_bytes: int = Field(default=96 * 1024, ge=4096)
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
    chat_pi_prewarm_enabled: bool = Field(default=False)
    chat_pi_prewarm_model: str = Field(default="", max_length=255)
    chat_pi_prewarm_reasoning_effort: Literal["low", "high", "max"] = Field(
        default="low"
    )
    chat_pi_provider_adapter_contract: str = Field(default="1", max_length=64)
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
    chat_initial_payload_optimization_enabled: bool = Field(default=False)
    chat_initial_payload_optimization_candidate: Literal[
        "system_duplicates", "tool_duplicates"
    ] = Field(default="system_duplicates")
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
    chat_sandbox_total_live_cap: int = Field(default=2, ge=1, le=16)
    chat_workspace_snapshots_enabled: bool = Field(default=False)
    chat_workspace_snapshot_inactivity_days: int = Field(default=30, ge=1, le=90)
    chat_gateway_url: str = Field(default="", max_length=1000)
    chat_require_auth: bool = Field(default=True)
    chat_show_reasoning: bool = Field(default=True)
    chat_langfuse_enabled: bool = Field(default=False)
    chat_langfuse_trace_content_access_enabled: bool = Field(default=False)
    catalog_mutations_enabled: bool = Field(default=True)
    thumbnail_mutations_enabled: bool = Field(default=True)
    cron_enabled: bool = Field(default=True)

    @model_validator(mode="after")
    def preserve_staging_artifacts_when_scope_guarded(self) -> "Settings":
        """Keep non-Posterly research artifacts across the legacy host launcher."""

        if self.environment == "staging" and self.chat_scope_guardrail_enabled:
            self.chat_artifacts_enabled = True
            self.chat_artifact_shared_preview_enabled = True
        return self

    @property
    def chat_model_registry(self) -> tuple[dict[str, str], ...]:
        deepseek_provider = self.chat_deepseek_v4_flash_provider
        deepseek_route = (
            self.chat_deepseek_v4_flash_route
            if deepseek_provider == "huggingface"
            else self.chat_deepseek_v4_flash_openrouter_route
        )
        deepseek = {
            "id": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "label": "DeepSeek V4 Flash",
            "route": deepseek_route,
            "provider": deepseek_provider,
            "provider_model": deepseek_route,
            "protocol": "anthropic-messages",
            "funding_mode": (
                "hf_user_billed"
                if deepseek_provider == "huggingface"
                else "openrouter_funded"
            ),
        }
        glm = {
            "id": "zai-org/GLM-5.3-Flash",
            "label": "GLM-5.3-Flash",
            "route": self.chat_glm_5_3_flash_route,
            "provider": "huggingface",
            "provider_model": self.chat_glm_5_3_flash_route,
            "protocol": "anthropic-messages",
            "funding_mode": "hf_user_billed",
        }
        choices = (glm,) if self.environment == "production" else (deepseek,)
        if self.environment == "production" and self.chat_openai_direct_enabled:
            choices = (
                {
                    "id": "gpt-5.6-luna@openai",
                    "label": "GPT-5.6 Luna",
                    "route": self.chat_openai_luna_route,
                    "provider": "openai",
                    "provider_model": self.chat_openai_model,
                    "protocol": "openai-responses",
                    "funding_mode": "openai_funded",
                },
                glm,
            )
        if self.environment == "staging":
            staging_choices = (
                {
                    "id": "moonshotai/Kimi-K3",
                    "label": "Kimi K3",
                    "route": self.chat_kimi_route,
                    "provider": "huggingface",
                    "provider_model": self.chat_kimi_route,
                    "protocol": "anthropic-messages",
                    "funding_mode": "hf_user_billed",
                },
                {
                    "id": "gpt-5.6-luna@openrouter",
                    "label": "GPT-5.6 Luna",
                    "route": self.chat_luna_route,
                    "provider": "openrouter",
                    "provider_model": self.chat_luna_route,
                    "protocol": "anthropic-messages",
                    "funding_mode": "openrouter_funded",
                },
            )
            if self.chat_openai_direct_enabled:
                # Staging paper qualification deliberately uses the direct Luna
                # route as the default.  The remaining choices stay available
                # for comparative ordinary-chat testing and existing sessions.
                choices = (
                    {
                        "id": "gpt-5.6-luna@openai",
                        "label": "GPT-5.6 Luna (Direct)",
                        "route": self.chat_openai_luna_route,
                        "provider": "openai",
                        "provider_model": self.chat_openai_model,
                        "protocol": "openai-responses",
                        "funding_mode": "openai_funded",
                    },
                    *choices,
                    *staging_choices,
                )
            else:
                choices = choices + staging_choices
        if self.environment != "staging" or not self.chat_alternative_model_enabled:
            return choices
        # The old comparison flag used the misleading historical Luna ID. Luna
        # now has an explicit OpenRouter choice, while the old ID remains hidden.
        if self.chat_alternative_model == "openai/gpt-5.6-luna":
            return choices
        if any(choice["id"] == self.chat_alternative_model for choice in choices):
            return choices
        labels = {
            "openai/gpt-5.6-luna": "GPT-5.6 Luna",
            "google/gemini-3.7-flash": "Gemini 3.7 Flash",
        }
        return choices + (
            {
                "id": self.chat_alternative_model,
                "label": labels[self.chat_alternative_model],
                "route": self.chat_alternative_model,
                "provider": "openrouter",
                "provider_model": self.chat_alternative_model,
                "protocol": "anthropic-messages",
                "funding_mode": "openrouter_funded",
            },
        )

    @staticmethod
    def chat_transport_provider(provider: str) -> str:
        return provider

    @property
    def chat_openrouter_routes(self) -> tuple[str, ...]:
        routes = [
            choice["route"]
            for choice in self.chat_model_registry
            if self.chat_transport_provider(choice["provider"]) == "openrouter"
        ]
        if self.chat_deepseek_v4_flash_openrouter_route not in routes:
            routes.append(self.chat_deepseek_v4_flash_openrouter_route)
        return tuple(routes)

    @property
    def chat_model_choices(self) -> tuple[dict[str, str], ...]:
        if not self.is_deployed or self.environment in {"production", "staging"}:
            return self.chat_model_registry
        return tuple(
            choice
            for choice in self.chat_model_registry
            if self.chat_transport_provider(choice["provider"]) != "openrouter"
        )

    @property
    def chat_model_routes(self) -> dict[str, str]:
        routes = {choice["id"]: choice["route"] for choice in self.chat_model_choices}
        routes.setdefault(
            "deepseek-ai/DeepSeek-V4-Flash-0731",
            (
                self.chat_deepseek_v4_flash_route
                if self.chat_deepseek_v4_flash_provider == "huggingface"
                else self.chat_deepseek_v4_flash_openrouter_route
            ),
        )
        canonical_route = routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
        # Existing sessions keep their persisted selected-model IDs but move to
        # the sole qualified route. These aliases are intentionally absent from
        # discovery and frontend defaults.
        for legacy_model in (
            "google/gemma-4-31B-it",
            "zai-org/GLM-5.2",
            "moonshotai/Kimi-K3",
            "openai/gpt-oss-120b",
            "deepseek-ai/DeepSeek-V4-Flash",
            "openai/gpt-5.6-luna",
            "openai/gpt-5.6-terra",
        ):
            routes.setdefault(legacy_model, canonical_route)
        if self.environment == "staging":
            routes["openai/gpt-5.6-luna"] = self.chat_luna_route
        return routes

    @property
    def chat_model_providers(self) -> dict[str, str]:
        providers = {
            choice["id"]: choice["provider"] for choice in self.chat_model_registry
        }
        providers.setdefault(
            "deepseek-ai/DeepSeek-V4-Flash-0731",
            self.chat_deepseek_v4_flash_provider,
        )
        canonical_provider = providers["deepseek-ai/DeepSeek-V4-Flash-0731"]
        for legacy_model in (
            "google/gemma-4-31B-it",
            "zai-org/GLM-5.2",
            "moonshotai/Kimi-K3",
            "openai/gpt-oss-120b",
            "deepseek-ai/DeepSeek-V4-Flash",
            "openai/gpt-5.6-luna",
            "openai/gpt-5.6-terra",
        ):
            providers.setdefault(legacy_model, canonical_provider)
        if self.environment == "staging":
            providers["openai/gpt-5.6-luna"] = "openrouter"
        return providers

    @property
    def chat_model_labels(self) -> dict[str, str]:
        labels = {choice["id"]: choice["label"] for choice in self.chat_model_registry}
        labels.setdefault("deepseek-ai/DeepSeek-V4-Flash-0731", "DeepSeek V4 Flash")
        if self.environment == "staging":
            labels["openai/gpt-5.6-luna"] = "GPT-5.6 Luna (Legacy OpenRouter)"
        return labels

    @property
    def chat_route_protocols(self) -> dict[str, str]:
        protocols = {
            choice["route"]: choice["protocol"] for choice in self.chat_model_registry
        }
        protocols.setdefault(self.chat_glm_route, "anthropic-messages")
        protocols.setdefault(self.chat_gemma_route, "anthropic-messages")
        protocols.setdefault(self.chat_deepseek_v4_flash_route, "anthropic-messages")
        protocols.setdefault(
            self.chat_deepseek_v4_flash_openrouter_route, "anthropic-messages"
        )
        return protocols

    @property
    def chat_route_provider_models(self) -> dict[str, str]:
        models = {
            choice["route"]: choice["provider_model"]
            for choice in self.chat_model_registry
        }
        models.setdefault(self.chat_glm_route, self.chat_glm_route)
        models.setdefault(self.chat_gemma_route, self.chat_gemma_route)
        models.setdefault(
            self.chat_deepseek_v4_flash_route, self.chat_deepseek_v4_flash_route
        )
        models.setdefault(
            self.chat_deepseek_v4_flash_openrouter_route,
            self.chat_deepseek_v4_flash_openrouter_route,
        )
        return models

    @property
    def chat_route_funding_modes(self) -> dict[str, str]:
        modes = {
            choice["route"]: choice["funding_mode"]
            for choice in self.chat_model_registry
        }
        modes.setdefault(self.chat_glm_route, "openrouter_funded")
        modes.setdefault(self.chat_gemma_route, "openrouter_funded")
        modes.setdefault(self.chat_deepseek_v4_flash_route, "hf_user_billed")
        modes.setdefault(
            self.chat_deepseek_v4_flash_openrouter_route, "openrouter_funded"
        )
        return modes

    @property
    def chat_route_providers(self) -> dict[str, str]:
        providers = {
            choice["route"]: self.chat_transport_provider(choice["provider"])
            for choice in self.chat_model_registry
        }
        # Both routes remain valid across a rolling provider switch. New turns use
        # chat_deepseek_v4_flash_provider while already-issued capabilities keep
        # their immutable route.
        providers.setdefault(self.chat_deepseek_v4_flash_route, "huggingface")
        providers.setdefault(self.chat_deepseek_v4_flash_openrouter_route, "openrouter")
        # Persisted capabilities from the retired comparison registry may still
        # carry these immutable routes even though they are hidden from discovery.
        providers.setdefault(self.chat_glm_route, "openrouter")
        providers.setdefault(self.chat_gemma_route, "openrouter")
        providers.setdefault(self.chat_kimi_route, "huggingface")
        providers.setdefault(self.chat_luna_route, "openrouter")
        return providers

    @property
    def chat_effective_pi_prewarm_model(self) -> str:
        if self.chat_pi_prewarm_model:
            return self.chat_pi_prewarm_model
        if (
            self.environment in {"production", "staging"}
            and self.chat_openai_direct_enabled
        ):
            return self.chat_openai_luna_route
        if self.chat_alternative_model_enabled:
            return self.chat_alternative_model
        return self.chat_model_choices[0]["route"]

    # GitHub API configuration
    github_token: str = Field(
        default="", description="GitHub API token for higher rate limits"
    )

    # Thumbnail configuration
    thumbnail_cache_dir: str = Field(
        default="./thumbnails", description="Directory to cache PDF thumbnails"
    )
    thumbnail_storage_backend: str = Field(
        default="local",
        description="Thumbnail storage backend: local or hf_bucket",
    )
    thumbnail_hf_bucket_id: str = Field(
        default="",
        description="Private Hugging Face bucket ID for paper thumbnails",
    )
    thumbnail_hf_bucket_prefix: str = Field(
        default="thumbnails",
        description="Path prefix inside the thumbnail Hugging Face bucket",
    )
    thumbnail_temp_cache_dir: str = Field(
        default="./thumbnail_cache",
        description="Small local cache for bucket-backed thumbnail responses",
    )
    paper_markdown_hf_bucket_id: str = Field(
        default="huggingface/pwc-papers-content",
        description="Private Hugging Face bucket containing paper Markdown files",
    )
    paper_markdown_upstream_bucket_id: str = Field(
        default="huggingchat/papers-content",
        description="Read-only Hugging Face bucket used before OCR fallback",
    )
    paper_markdown_hf_namespace: str = Field(default="huggingface")
    paper_markdown_model_id: str = Field(default="datalab-to/chandra-ocr-2")
    paper_markdown_model_revision: str = Field(
        default="af93b47dba1b47b6640c86ccf487ed2260ab9a09"
    )
    paper_markdown_runtime_image: str = Field(default="vllm/vllm-openai:v0.17.0")
    paper_markdown_hardware: Literal["l40sx1"] = Field(default="l40sx1")
    # These legacy settings remain accepted for deployment compatibility. New
    # launches use the shared measured profiles as their authoritative contract.
    paper_markdown_incremental_batch_size: int = Field(
        default=PAPER_MARKDOWN_LIVE_JOB_PROFILE.max_papers, ge=1, le=100
    )
    paper_markdown_backfill_batch_size: int = Field(
        default=PAPER_MARKDOWN_BACKFILL_JOB_PROFILE.max_papers, ge=1, le=500
    )
    paper_markdown_backfill_concurrency: int = Field(
        default=PAPER_MARKDOWN_BACKFILL_JOB_PROFILE.concurrency, ge=1, le=16
    )
    paper_markdown_max_pages: int = Field(default=30, ge=1, le=30)
    paper_markdown_job_timeout: str = Field(
        default=PAPER_MARKDOWN_LIVE_JOB_PROFILE.hard_timeout
    )
    paper_markdown_soft_deadline_seconds: int = Field(
        default=PAPER_MARKDOWN_LIVE_JOB_PROFILE.soft_deadline_seconds,
        ge=0,
        # Accept the prior 11.25-hour environment value during rollout; the
        # shared profile remains authoritative for all new launches.
        le=40_500,
    )
    paper_markdown_incremental_monthly_budget_usd: float = Field(default=100.0, gt=0)
    paper_markdown_backfill_budget_usd: float = Field(default=750.0, gt=0)
    paper_markdown_cost_policy: Literal["metered", "unmetered_hf"] = Field(
        default="unmetered_hf",
        description=(
            "Use unmetered_hf for Hugging Face-owned Jobs that are not billed; "
            "concurrency and timeout limits remain enforced."
        ),
    )
    paper_markdown_paid_dispatch_enabled: bool = Field(
        default=False,
        description=(
            "Permit unattended OCR dispatch with the measured job profile. "
            "Operator capability probes, canaries, and mount recovery remain "
            "separately confirmed commands."
        ),
    )
    paper_markdown_image_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    paper_markdown_image_max_pixels: int = Field(default=80_000_000, ge=1)

    # bioRxiv / medRxiv TDM (requester-pays S3 bucket). Optional: when unset,
    # thumbnails fall back to Europe PMC PDF mirrors where available.
    biorxiv_aws_access_key_id: str = Field(
        default="",
        description="AWS access key for bioRxiv/medRxiv requester-pays S3 PDF downloads",
    )
    biorxiv_aws_secret_access_key: str = Field(
        default="",
        description="AWS secret key for bioRxiv/medRxiv requester-pays S3 PDF downloads",
    )

    @property
    def database_url(self) -> str:
        """Get the database URL."""
        password_part = f":{self.db_password}" if self.db_password else ""
        return f"postgresql://{self.db_user}{password_part}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_log_identifier(self) -> str:
        """Return a sanitized identifier for logging database connections."""

        return f"{self.db_user}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    @property
    def is_deployed(self) -> bool:
        return (
            self.environment.lower() in {"production", "staging"}
            and self.release_id != "development"
        )

    @property
    def frontend_dist_path(self) -> Path:
        if self.frontend_dist_dir:
            return Path(self.frontend_dist_dir)
        return Path(__file__).resolve().parents[1] / "frontend" / "dist"

    @property
    def admin_hf_username_set(self) -> set[str]:
        """Return the set of allowlisted HF usernames, lowercased and trimmed."""

        return {
            name.strip().lower()
            for name in self.admin_hf_usernames.split(",")
            if name.strip()
        }

    @property
    def chat_sandbox_operator_username_set(self) -> set[str]:
        return {
            name.strip().lower()
            for name in self.chat_sandbox_operator_usernames.split(",")
            if name.strip()
        }

    @staticmethod
    def _subject_set(value: str) -> set[str]:
        subjects = {subject.strip() for subject in value.split(",") if subject.strip()}
        invalid = [
            subject
            for subject in subjects
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,254}", subject)
        ]
        if invalid:
            raise ValueError("Malformed immutable Hugging Face subject allowlist")
        return subjects

    @property
    def admin_hf_subject_set(self) -> set[str]:
        return self._subject_set(self.admin_hf_subjects)

    @property
    def contributor_hf_subject_set(self) -> set[str]:
        return self._subject_set(self.contributor_hf_subjects)

    @property
    def auth_return_origin_set(self) -> set[str]:
        return {
            origin.strip().rstrip("/")
            for origin in self.auth_return_origins.split(",")
            if origin.strip()
        }

    @property
    def cors_allowed_origins(self) -> List[str]:
        """Return the appropriate CORS origins for the current environment."""

        if self.is_production:
            base = ["https://paperswithcode.co", "https://www.paperswithcode.co"]
        else:
            base = list(self.allowed_origins)

        # Always merge any extra origins (e.g. the HF Space mirror) so the
        # same setting works in staging/dev while testing the Space.
        for origin in self.extra_allowed_origins.split(","):
            origin = origin.strip()
            if origin and origin not in base:
                base.append(origin)
        return base


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
