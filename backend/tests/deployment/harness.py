"""Release bundles and deployed settings shared by deployment tests."""

from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.config import Settings
from deploy.release import (
    build_manifest,
    profile_features,
)


def make_bundle(root: Path, *, chat: bool) -> Path:
    release = root / ("release-staging" if chat else "release-production")
    dist = release / "frontend-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app-abc123.js").write_text("export {}")
    (assets / "app-abc123.css").write_text("body{}")
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/app-abc123.js"></script>'
        '<link rel="stylesheet" href="/assets/app-abc123.css">'
    )
    (dist / "features.json").write_text(
        json.dumps(profile_features("staging" if chat else "production"))
    )
    (release / "backend").mkdir()
    (release / "backend" / "main.py").write_text("")
    sha = "a" * 40
    environment = "staging" if chat else "production"
    if environment == "staging":
        (assets / "pdf.worker.min-abc123.js").write_text("export {}")
    (dist / "features.json").write_text(json.dumps(profile_features(environment)))
    descriptor = None
    if environment == "staging":
        descriptor = {
            **build_manifest(sha, environment)["chat_runtime"],
            "modal_image_version": "im-test-immutable",
        }
    (release / "release.json").write_text(
        json.dumps(build_manifest(sha, environment, chat_descriptor=descriptor))
    )
    return release


def deployed_settings(tmp_path: Path, release: Path, environment: str) -> Settings:
    state = tmp_path / "state"
    thumbnail = tmp_path / "thumbnails"
    for path in (
        state,
        thumbnail,
        state / "cache",
        state / "logs",
        state / "locks",
        state / "spool",
        state / "agent",
        state / "recovery",
    ):
        path.mkdir(parents=True, exist_ok=True)
    runtime = json.loads((release / "release.json").read_text())["chat_runtime"]
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    private_value = base64.urlsafe_b64encode(b"\x01" * 32).rstrip(b"=").decode()
    public_value = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        .rstrip(b"=")
        .decode()
    )
    return Settings(
        environment=environment,
        release_id=json.loads((release / "release.json").read_text())["release_id"],
        frontend_dist_dir=str(release / "frontend-dist"),
        runtime_data_dir=str(state),
        thumbnail_cache_dir=str(thumbnail),
        thumbnail_temp_cache_dir=str(state / "cache"),
        cron_log_dir=str(state / "logs"),
        cron_lock_dir=str(state / "locks"),
        codex_add_evals_spool_dir=str(state / "spool"),
        chat_agent_cwd=str(state / "agent"),
        chat_recovery_spool_dir=str(state / "recovery"),
        jwt_secret="test-only",
        production_jwt_fingerprint=("0" * 64 if environment == "staging" else ""),
        session_cookie_domain="",
        session_cookie_name=(
            "pwc_staging_session" if environment == "staging" else "pwc_session"
        ),
        shared_session_cookie_name="pwc_shared_session",
        shared_session_cookie_domain=".paperswithcode.co",
        session_signing_private_key=(
            private_value if environment == "production" else ""
        ),
        session_verification_public_key=public_value,
        auth_authority_origin="https://paperswithcode.co",
        auth_return_origins=(
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        hf_oauth_client_id="test-oauth-client",
        hf_oauth_client_secret="test-oauth-secret",
        hf_oauth_credential_secret="test-oauth-credential-secret",
        chat_enabled=environment == "staging",
        native_pdf_reader_enabled=environment == "staging",
        paper_reader_chat_enabled=environment == "staging",
        paper_reader_selection_enabled=environment == "staging",
        chat_public_admission_enabled=environment == "staging",
        chat_sandbox_admission_enabled=environment == "staging",
        chat_default_backend=runtime["default_backend"],
        chat_new_chat_modal_percentage=runtime["new_chat_modal_percentage"],
        chat_modal_image_version=runtime["modal_image_version"],
        chat_pwc_cli_version=runtime["pwc_cli_version"],
        chat_worker_contract_version=runtime["worker_contract_version"],
        chat_system_prompt_sha256=runtime["system_prompt_sha256"],
        chat_max_concurrency=2 if environment == "staging" else 1,
        chat_user_max_concurrency=2,
        chat_sandbox_total_live_cap=3,
        chat_blank_pool_enabled=environment == "staging",
        chat_blank_pool_min=1,
        chat_blank_pool_max=1,
        chat_persistent_worker_enabled=environment == "staging",
        chat_sandbox_spend_enforcement_enabled=environment == "staging",
        chat_sandbox_provider_mode="starter_workspace",
        chat_sandbox_budget_attestation=(
            "modal-workspace-nielsrogge-250-staging-starter-v1"
            if environment == "staging"
            else ""
        ),
        chat_sandbox_modal_environment=(
            "pwc-chat-staging" if environment == "staging" else ""
        ),
        chat_sandbox_modal_workspace=("nielsrogge" if environment == "staging" else ""),
        chat_sandbox_modal_owner_username=(
            "nielsrogge" if environment == "staging" else ""
        ),
        chat_sandbox_slack_webhook_url=(
            "https://hooks.slack.test/services/test" if environment == "staging" else ""
        ),
        chat_sandbox_alert_fallback_webhook_url=(
            "https://alerts.test/fallback" if environment == "staging" else ""
        ),
        chat_sandbox_runbook_url=(
            "https://example.test/runbook" if environment == "staging" else ""
        ),
        chat_sandbox_operator_usernames=("root" if environment == "staging" else ""),
        chat_gateway_url=(
            "https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway"
            if environment == "staging"
            else ""
        ),
        chat_title_generation_enabled=environment == "staging",
        chat_title_hf_token=(
            "test-only-isolated-title-token" if environment == "staging" else ""
        ),
        chat_title_bill_to=("huggingface" if environment == "staging" else ""),
        chat_title_credential_owner=("nielsr" if environment == "staging" else ""),
        chat_title_credential_environment=(
            "staging" if environment == "staging" else ""
        ),
        chat_scope_guardrail_enabled=environment == "staging",
        chat_scope_guardrail_hf_token=(
            "test-only-isolated-title-token" if environment == "staging" else ""
        ),
        chat_scope_guardrail_hf_bill_to=(
            "huggingface" if environment == "staging" else ""
        ),
        chat_scope_guardrail_openai_api_key=(
            "test-only-guardrail-fallback" if environment == "staging" else ""
        ),
        chat_artifacts_enabled=environment == "staging",
        chat_artifact_shared_preview_enabled=environment == "staging",
        chat_artifact_storage_backend=(
            "hf_bucket" if environment == "staging" else "local"
        ),
        chat_artifact_hf_bucket_id=(
            "nielsr/pwc-chat-artifacts-staging" if environment == "staging" else ""
        ),
        codex_jobs_enabled=True,
        codex_add_evals_enabled=True,
        codex_enrich_paper_enabled=True,
        codex_jobs_namespace="test",
        codex_jobs_token="test-only",
        codex_jobs_openai_api_key="test-only",
        codex_jobs_api_url=(
            "https://staging.paperswithcode.co/api/v1"
            if environment == "staging"
            else "https://paperswithcode.co/api/v1"
        ),
        github_token="test-only",
        hf_token="test-only-hf-token" if environment == "staging" else "",
        chat_openrouter_api_key="test-only-openrouter-token",
        chat_openrouter_server_funded_enabled=environment == "staging",
        chat_openrouter_monthly_user_budget_usd=(1 if environment == "staging" else 5),
        chat_openrouter_workspace_monthly_budget_usd=200,
        chat_openrouter_credential_keyring=json.dumps(
            {"1": base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()}
        ),
        chat_openrouter_user_tracking_secret="test-only-tracking-secret",
        # Pricing freshness is wall-clock bound; keep these tests date-independent.
        chat_openrouter_pricing_verified_at=date.today().isoformat(),
        catalog_mutations_enabled=environment == "production",
        thumbnail_mutations_enabled=False,
        cron_enabled=environment == "production",
        db_search_path="staging,public" if environment == "staging" else "public",
    )


def configure_hf_scope_and_title(settings: Settings, environment: str) -> None:
    settings.chat_title_generation_enabled = True
    settings.chat_title_provider = "huggingface"
    settings.chat_title_model = "zai-org/GLM-5.3-Flash:baseten"
    settings.chat_title_hf_token = f"test-only-title-{environment}"
    settings.chat_title_bill_to = "huggingface"
    settings.chat_title_credential_owner = "nielsr"
    settings.chat_title_credential_environment = environment
    settings.chat_scope_guardrail_enabled = True
    settings.chat_scope_guardrail_hf_token = settings.chat_title_hf_token
    settings.chat_scope_guardrail_hf_bill_to = "huggingface"
    settings.chat_scope_guardrail_openai_api_key = (
        f"test-only-guardrail-fallback-{environment}"
    )
