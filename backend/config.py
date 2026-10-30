"""
Configuration management for the FastAPI backend.
"""

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.chat_configuration.settings import (
    ChatSettings,
    ExternalPiWorkerEndpointConfig,
)
from backend.services.paper_markdown_job_profile import (
    PAPER_MARKDOWN_BACKFILL_JOB_PROFILE,
    PAPER_MARKDOWN_LIVE_JOB_PROFILE,
)

__all__ = ["ExternalPiWorkerEndpointConfig", "Settings", "get_settings"]


class Settings(BaseSettings, ChatSettings):
    """Application settings; chat groups are composed from ``ChatSettings``."""

    model_config = SettingsConfigDict(env_file=["keys.env"], env_prefix="PWC_")

    research_email_enabled: bool = False
    resend_api_key: str = ""
    resend_from: str = ""
    resend_domain_verified: bool = False
    resend_webhook_secret: str = ""
    resend_webhooks_ready: bool = False

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
    db_user: str = Field(default="postgres", description="Database user")
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
            "https://<namespace>-paperswithcode.hf.space) to call the production "
            "API."
        ),
    )
    local_host_aliases: str = Field(
        default="",
        description=(
            "Comma-separated extra hostnames (for example the origin server IP) "
            "that stored links may use to point at this site's own pages."
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
    serpapi_api_key: str = Field(
        default="",
        description=(
            "SerpAPI key for reading Google Scholar author profiles "
            "(link_google_scholar_profiles)"
        ),
    )
    semantic_scholar_api_key_2: str = Field(
        default="",
        description=(
            "Secondary Semantic Scholar key for historical backfills; the "
            "hourly citation refresh also rotates through it"
        ),
    )
    openalex_api_key: str = Field(
        default="", description="Optional OpenAlex API key for historical backfills"
    )

    # LLM API keys
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")

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
    codex_add_evals_work_dir: str = Field(default="./runtime/codex-work")
    codex_add_evals_spool_dir: str = Field(default="/tmp/pwc-codex-add-evals")
    # Remote paper-curation workers run on Hugging Face Jobs. Keep these
    # credentials separate from the general Hub token and database credentials.
    codex_jobs_enabled: bool = Field(default=False)
    # Deliberately has no default: launching into the wrong organization can
    # fail with a generic Hub 403 and leaves no remote Job to inspect.
    codex_jobs_namespace: str = Field(default="")
    codex_jobs_token: str = Field(default="")
    codex_jobs_openai_api_key: str = Field(default="")
    # Digest-pinned image built by .github/workflows/build-codex-curator-image.yml.
    # Deliberately has no default; each deployment pins its own curator image.
    codex_jobs_image: str = Field(default="")
    # Hub revision of a legacy Docker Space image; unused for registry digests.
    codex_jobs_image_revision: str = Field(default="")
    codex_jobs_api_url: str = Field(default="https://paperswithcode.co/api/v1")
    codex_jobs_timeout_seconds: int = Field(default=5400, ge=300, le=14400)
    codex_jobs_cli_version: str = Field(default="0.75.0")
    codex_jobs_model: str = Field(default="gpt-6-luna")
    codex_jobs_reasoning_effort: str = Field(default="medium")
    # AI conference deadline research runs off-box on Hugging Face Jobs (Claude
    # Agent SDK); only the validated, bounded DB writes happen on the VPS.
    # The HF namespace/token fall back to the curation Jobs credentials.
    conference_deadlines_anthropic_api_key: str = Field(default="")
    conference_deadlines_hf_namespace: str = Field(default="")
    conference_deadlines_hf_token: str = Field(default="")
    conference_deadlines_job_image: str = Field(default="python:3.12-slim")
    conference_deadlines_job_flavor: str = Field(default="cpu-basic")
    # 0.2.165 bundles Claude Code 2.1.294; claude-opus-5-5 needs >= 2.1.280.
    conference_deadlines_sdk_version: str = Field(default="0.2.165")
    conference_deadlines_retrieval_model: str = Field(default="claude-sonnet-5-5")
    conference_deadlines_aggregation_model: str = Field(default="claude-opus-5-5")
    conference_deadlines_weekly_limit: int = Field(default=30, ge=1, le=80)
    conference_deadlines_daily_limit: int = Field(default=8, ge=1, le=30)
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
    paper_edit_auto_approve_enabled: bool = Field(
        default=True,
        description="Apply signed-in users' paper-page edits immediately; "
        "false queues every edit for admin review",
    )
    paper_edit_auto_approve_daily_papers: int = Field(default=100, ge=1, le=10000)
    paper_edit_auto_approve_removal_papers: int = Field(default=10, ge=1, le=1000)
    paper_edit_auto_approve_extra_domains: str = Field(
        default="",
        description="Comma-separated hosts whose links auto-apply without review",
    )
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

    firecrawl_api_key: str = Field(
        default="",
        description="Firecrawl API key that turns external paper web pages into Markdown",
    )

    native_pdf_reader_enabled: bool = Field(default=False)
    paper_reader_chat_enabled: bool = Field(default=False)
    paper_reader_selection_enabled: bool = Field(default=False)
    # Reader chat cites PDF layout blocks when the paper has page-aware layout.
    paper_reader_citations_enabled: bool = Field(default=False)
    paper_layout_hf_bucket_id: str = Field(
        default="huggingface/pwc-papers-pages",
        description="Private bucket with page-aware Chandra Markdown and block sidecars",
    )

    catalog_mutations_enabled: bool = Field(default=True)
    thumbnail_mutations_enabled: bool = Field(default=True)
    cron_enabled: bool = Field(default=True)

    # GitHub API configuration
    github_token: str = Field(
        default="", description="GitHub API token for higher rate limits"
    )
    # Evaluation outreach identity. An open issue by this GitHub login marks a
    # repository as already contacted, and the outreach token must belong to it.
    github_outreach_login: str = Field(default="")
    # First name used to introduce and sign evaluation outreach issues.
    github_outreach_signer: str = Field(default="")

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
    def local_host_alias_set(self) -> set[str]:
        """Return configured local host aliases, lowercased and trimmed."""

        return {
            host.strip().lower()
            for host in self.local_host_aliases.split(",")
            if host.strip()
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
