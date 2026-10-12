"""Autonomous Codex job configuration validation."""

from __future__ import annotations

import re

from backend.config import Settings


def validate_codex_jobs_configuration(settings: Settings) -> None:
    """Validate credentials and API ownership for enabled Codex jobs."""

    if settings.codex_jobs_enabled:
        if (
            not settings.codex_jobs_namespace
            or not settings.codex_jobs_token
            or not settings.codex_jobs_openai_api_key
        ):
            raise RuntimeError(
                "Codex jobs require namespace, HF, and OpenAI credentials"
            )
        expected_api_url = {
            "production": "https://paperswithcode.co/api/v1",
            "staging": "https://staging.paperswithcode.co/api/v1",
        }[settings.environment]
        if settings.codex_jobs_api_url.rstrip("/") != expected_api_url:
            raise RuntimeError(
                f"{settings.environment} Codex jobs must target {expected_api_url}"
            )
    if settings.autonomous_submission_enabled:
        expected_callback_url = {
            "production": "https://paperswithcode.co/api/v1",
            "staging": "https://staging.paperswithcode.co/api/v1",
        }[settings.environment]
        if (
            len(settings.autonomous_submission_callback_secret.encode()) < 32
            or settings.autonomous_submission_callback_secret
            == settings.admin_api_token
        ):
            raise RuntimeError(
                "autonomous submission callbacks require a separate strong secret"
            )
        if (
            settings.autonomous_submission_callback_base_url.rstrip("/")
            != expected_callback_url
        ):
            raise RuntimeError(
                f"{settings.environment} autonomous callbacks must target "
                f"{expected_callback_url}"
            )
    if settings.autonomous_submission_jobs_enabled:
        if settings.environment != "production":
            raise RuntimeError("autonomous submission Jobs are production-only")
        if not settings.autonomous_submission_enabled:
            raise RuntimeError(
                "autonomous submission Jobs require submission callbacks"
            )
        if (
            not settings.autonomous_submission_hf_namespace
            or not settings.autonomous_submission_hf_token
            or not settings.autonomous_submission_openai_api_key
            or not settings.autonomous_submission_job_image
            or not settings.autonomous_alert_slack_webhook_url
            or not settings.autonomous_alert_fallback_webhook_url
        ):
            raise RuntimeError(
                "autonomous submission Jobs require separate credentials, image, "
                "and alert routes"
            )
        if settings.autonomous_submission_hf_token in {
            settings.codex_jobs_token,
            settings.hf_token,
        } or settings.autonomous_submission_openai_api_key in {
            settings.codex_jobs_openai_api_key,
            settings.openai_api_key,
        }:
            raise RuntimeError(
                "autonomous submission Jobs require separate credentials"
            )
        if (
            settings.autonomous_submission_input_usd_per_million <= 0
            or settings.autonomous_submission_cached_input_usd_per_million <= 0
            or settings.autonomous_submission_output_usd_per_million <= 0
        ):
            raise RuntimeError(
                "autonomous submission Jobs require positive pinned pricing"
            )
        image_is_digest = re.fullmatch(
            r".+@sha256:[0-9a-f]{64}", settings.autonomous_submission_job_image
        )
        if not image_is_digest:
            raise RuntimeError("autonomous submission Jobs require an immutable image")
        if (
            settings.autonomous_alert_slack_webhook_url
            == settings.autonomous_alert_fallback_webhook_url
        ):
            raise RuntimeError(
                "autonomous submission Jobs require separate alert routes"
            )
    if settings.codex_curation_scheduler_enabled:
        if settings.environment != "production":
            raise RuntimeError("scheduled paper curation is production-only")
        if not settings.codex_jobs_enabled:
            raise RuntimeError("scheduled paper curation requires Codex Jobs")
        if settings.codex_curation_direct_apply_enabled and (
            not settings.codex_curation_trace_upload_enabled
            or not settings.codex_curation_trace_hf_bucket_id
        ):
            raise RuntimeError(
                "direct scheduled curation requires private trace storage"
            )
        if settings.codex_jobs_max_scheduled_active >= settings.codex_jobs_max_active:
            raise RuntimeError("scheduled paper curation must reserve an admin slot")
        image_is_digest = "@sha256:" in settings.codex_jobs_image
        image_is_versioned_space = bool(
            re.fullmatch(
                r"hf\.co/spaces/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+-[0-9a-f]{12}",
                settings.codex_jobs_image,
            )
            and re.fullmatch(r"[0-9a-f]{40}", settings.codex_jobs_image_revision)
        )
        if not image_is_digest and not image_is_versioned_space:
            raise RuntimeError(
                "scheduled paper curation requires an immutable curator image"
            )
