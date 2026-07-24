"""
Configuration management for the FastAPI backend.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Codex curation jobs. Disabled on the main API; isolated staging and
    # production sidecars opt in through their systemd environments.
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
    codex_jobs_image: str = Field(default="node:22-bookworm")
    codex_jobs_api_url: str = Field(default="https://paperswithcode.co/api/v1")
    codex_jobs_timeout_seconds: int = Field(default=5400, ge=300, le=14400)

    # Hugging Face OAuth configuration (for "Sign in with Hugging Face")
    hf_oauth_client_id: str = Field(
        default="",
        description="Client ID of the Hugging Face OAuth application",
    )
    hf_oauth_client_secret: str = Field(
        default="",
        description="Client secret of the Hugging Face OAuth application",
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

    # Hugging Face API configuration
    hf_token: str = Field(
        default="", description="Hugging Face API token for higher rate limits"
    )

    # Research chat (disabled until the isolated live qualification passes).
    chat_enabled: bool = Field(default=False)
    chat_glm_route: str = Field(default="zai-org/GLM-5.2:together")
    chat_deepseek_route: str = Field(default="deepseek-ai/DeepSeek-V4-Flash:fastest")
    chat_title_model: str = Field(default="deepseek-ai/DeepSeek-V4-Flash")
    chat_title_timeout_seconds: float = Field(default=5, gt=0, le=30)
    chat_title_max_tokens: int = Field(default=32, ge=8, le=64)
    chat_session_limit: int = Field(default=100, ge=1, le=1000)
    chat_session_message_limit: int = Field(default=200, ge=2, le=2000)
    chat_session_byte_limit: int = Field(default=25 * 1024 * 1024, ge=1024)
    chat_user_byte_limit: int = Field(default=100 * 1024 * 1024, ge=1024)
    chat_agent_cwd: str = Field(default="/tmp/pwc-chat-agent")
    chat_recovery_spool_dir: str = Field(default="/tmp/pwc-chat-recovery")
    chat_recovery_spool_max_sessions: int = Field(default=20, ge=1, le=100)
    chat_max_turns: int = Field(default=8, ge=1, le=12)
    chat_max_search_calls: int = Field(default=2, ge=1, le=5)
    chat_timeout_seconds: float = Field(default=180, gt=0, le=300)
    chat_max_concurrency: int = Field(default=1, ge=1, le=8)
    chat_default_backend: str = Field(
        default="local_mcp", pattern=r"^(local_mcp|modal_cli)$"
    )
    chat_new_chat_modal_percentage: int = Field(default=0, ge=0, le=100)
    chat_modal_image_version: str = Field(default="", max_length=255)
    chat_pwc_cli_version: str = Field(default="", max_length=64)
    chat_worker_contract_version: str = Field(default="", max_length=64)
    chat_system_prompt_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    chat_max_tool_calls: int = Field(default=12, ge=1, le=24)
    chat_max_direct_search_calls: int = Field(default=4, ge=1, le=8)
    chat_sandbox_ready_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_agent_timeout_seconds: float = Field(default=180, gt=0, le=600)
    chat_bash_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chat_cancel_grace_seconds: float = Field(default=2, ge=0, le=10)
    chat_tool_result_max_bytes: int = Field(default=24 * 1024, ge=1024)
    chat_turn_tool_output_max_bytes: int = Field(default=96 * 1024, ge=4096)
    chat_sandbox_cpu: float = Field(default=1, gt=0, le=8)
    chat_sandbox_memory_mib: int = Field(default=2048, ge=512, le=16384)
    chat_sandbox_writable_bytes: int = Field(
        default=512 * 1024 * 1024, ge=64 * 1024 * 1024
    )
    chat_sandbox_pids_max: int = Field(default=64, ge=16, le=512)
    chat_sandbox_warm_seconds: int = Field(default=300, ge=0, le=3600)
    chat_sandbox_max_warm: int = Field(default=10, ge=0, le=1000)
    chat_workspace_snapshots_enabled: bool = Field(default=False)
    chat_workspace_snapshot_inactivity_days: int = Field(default=30, ge=1, le=90)
    chat_gateway_url: str = Field(default="", max_length=1000)
    chat_require_auth: bool = Field(default=True)
    chat_show_reasoning: bool = Field(default=True)
    chat_hf_bill_to: str = Field(
        default="",
        pattern=r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$",
        description="Optional Hugging Face organization slug billed for chat inference",
    )
    chat_requests_per_minute: int = Field(default=5, ge=1, le=1000)
    chat_requests_per_day: int = Field(default=50, ge=1, le=10000)
    catalog_mutations_enabled: bool = Field(default=True)
    thumbnail_mutations_enabled: bool = Field(default=True)
    cron_enabled: bool = Field(default=True)

    @property
    def chat_model_choices(self) -> tuple[dict[str, str], ...]:
        return (
            {
                "id": "deepseek-ai/DeepSeek-V4-Flash",
                "label": "DeepSeek V4 Flash",
                "route": self.chat_deepseek_route,
            },
            {
                "id": "zai-org/GLM-5.2",
                "label": "GLM 5.2",
                "route": self.chat_glm_route,
            },
        )

    @property
    def chat_model_routes(self) -> dict[str, str]:
        return {choice["id"]: choice["route"] for choice in self.chat_model_choices}

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
