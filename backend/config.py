"""
Configuration management for the FastAPI backend.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Host to bind the server")
    port: int = Field(default=8000, description="Port to bind the server")
    environment: str = Field(
        default="development",
        description="Environment (development, staging, production)",
    )
    log_level: str = Field(default="INFO", description="Log level")

    # Database configuration
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="paperswithcode_hf", description="Database name")
    db_user: str = Field(default="nielsrogge", description="Database user")
    db_password: str = Field(default="", description="Database password")

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
    admin_hf_usernames: str = Field(
        default="",
        description="Comma-separated list of HF usernames allowed to perform admin actions",
    )

    # Hugging Face API configuration
    hf_token: str = Field(
        default="", description="Hugging Face API token for higher rate limits"
    )

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

    class Config:
        env_file = ["keys.env"]
        env_prefix = "PWC_"

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
