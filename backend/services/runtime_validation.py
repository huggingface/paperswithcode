"""Fail-closed validation for deployed environment and release configuration."""

from __future__ import annotations

import base64
import grp
import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import text

from backend.chat_sandbox_worker.contract import (
    PI_NODE_SHA256,
    PI_NODE_VERSION,
    PI_SOURCE_COMMIT,
    PI_VERSION,
    PROVIDER_OUTPUT_TOKEN_LIMIT,
    RESTRICTED_HF_CLI_VERSION,
    SDK_VERSION,
)
from backend.config import Settings
from backend.services.chat_runtime_contract import (
    ExternalAdmissionContract,
    dedicated_gateway_hostname,
    require_external_admission_contract,
    require_immutable_image_id,
)
from backend.services.chat_external_worker_capacity import (
    UnsupportedChatMode,
    external_worker_endpoints,
    require_ordinary_research_mode,
)
from latex_compiler_contract import (
    EnvelopeError,
    validate_staging_sandbox_compiler_identity,
)

_ASSET_RE = re.compile(
    r"""(?:src|href)=["'](?P<path>/assets/[^"'?#]+\.(?:js|css))(?:[?#][^"']*)?["']"""
)
_RELEASE_ROOT = Path("/srv/paperswithcode/releases")
_STAGING_LATEX_COMPILER_ARTIFACT_BUCKET = "nielsr/pwc-chat-artifacts-staging"
_STAGING_LATEX_COMPILER_EGRESS_ATTESTATION = "sandbox-netns-v1"
_STAGING_LATEX_COMPILER_EVIDENCE_GROUP = "pwc-staging"
STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE = Path(
    "/var/lib/paperswithcode/staging-compiler-qualification/"
    "latex-compiler-qualification.json"
)
_STAGING_LATEX_QUALIFICATION_CHECKS = frozenset(
    {
        "hostile_input",
        "cancellation",
        "health",
        "metrics",
        "image_isolation",
        "reconciliation",
        "restart",
    }
)


def _resolved_absolute(name: str, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"PWC_{name} must be absolute in deployed environments")
    resolved = path.resolve(strict=False)
    if resolved == _RELEASE_ROOT or _RELEASE_ROOT in resolved.parents:
        raise RuntimeError(f"PWC_{name} must be outside immutable releases")
    return resolved


def validate_frontend_dist(settings: Settings) -> dict[str, bool]:
    dist = Path(settings.frontend_dist_dir)
    if not dist.is_absolute():
        raise RuntimeError("PWC_FRONTEND_DIST_DIR must be absolute")
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"built frontend shell is missing: {index}")
    html = index.read_text(encoding="utf-8")
    if "/src/main.tsx" in html:
        raise RuntimeError("deployed frontend shell references /src/main.tsx")
    assets = {
        match.group("path").removeprefix("/") for match in _ASSET_RE.finditer(html)
    }
    if not any(asset.endswith(".js") for asset in assets):
        raise RuntimeError("deployed frontend shell has no module JavaScript asset")
    for asset in assets:
        candidate = (dist / asset).resolve()
        if dist.resolve() not in candidate.parents or not candidate.is_file():
            raise RuntimeError(
                f"frontend asset is missing or escapes the bundle: {asset}"
            )

    features_path = dist / "features.json"
    if not features_path.is_file():
        raise RuntimeError("frontend features.json is missing")
    features = json.loads(features_path.read_text(encoding="utf-8"))
    expected_features = {
        "chat": settings.chat_enabled,
        "native_pdf_reader": settings.native_pdf_reader_enabled,
        "paper_reader_chat": settings.paper_reader_chat_enabled,
        "paper_reader_selection": settings.paper_reader_selection_enabled,
        "codex_add_evals": (
            settings.codex_jobs_enabled and settings.codex_add_evals_enabled
        ),
        "codex_enrich_paper": (
            settings.codex_jobs_enabled and settings.codex_enrich_paper_enabled
        ),
    }
    if features != expected_features:
        raise RuntimeError(
            "frontend/backend feature mismatch: "
            f"frontend={features!r} backend={expected_features!r}"
        )
    return features


@dataclass(frozen=True, slots=True)
class SandboxSpendPolicy:
    """Reviewed spend thresholds pinned for deployed chat sandboxes."""

    warning_microusd: int
    application_cap_microusd: int
    environment_cap_microusd: int
    workspace_cap_microusd: int


@dataclass(frozen=True, slots=True)
class SandboxCapacityPolicy:
    """Reviewed active-turn and warm-pool capacity."""

    max_concurrency: int
    user_max_concurrency: int
    total_live_cap: int
    blank_pool_min: int
    blank_pool_max: int


_STARTER_SANDBOX_SPEND_POLICY = SandboxSpendPolicy(
    warning_microusd=75_000_000,
    application_cap_microusd=100_000_000,
    environment_cap_microusd=0,
    workspace_cap_microusd=250_000_000,
)
_STAGING_STARTER_105_SPEND_POLICY = SandboxSpendPolicy(
    warning_microusd=75_000_000,
    application_cap_microusd=105_000_000,
    environment_cap_microusd=0,
    workspace_cap_microusd=250_000_000,
)
_TEAM_SANDBOX_SPEND_POLICIES = {
    "v1": SandboxSpendPolicy(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=125_000_000,
        workspace_cap_microusd=250_000_000,
    ),
    "v2": SandboxSpendPolicy(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=250_000_000,
        workspace_cap_microusd=250_000_000,
    ),
    "v3": SandboxSpendPolicy(
        warning_microusd=200_000_000,
        application_cap_microusd=225_000_000,
        environment_cap_microusd=250_000_000,
        workspace_cap_microusd=250_000_000,
    ),
}
_SANDBOX_CAPACITY_POLICY = SandboxCapacityPolicy(
    max_concurrency=2,
    user_max_concurrency=2,
    total_live_cap=3,
    blank_pool_min=1,
    blank_pool_max=1,
)
# Reviewed external Pi capacity tiers, keyed by admitted concurrent turns. The
# deploy tooling sizes the eight-replica fleet from the same tier value, and
# the OpenAI circuits below must match the tier (see docs/deployment.md).
_EXTERNAL_PI_CAPACITY_POLICIES = {
    tier: SandboxCapacityPolicy(
        max_concurrency=tier,
        user_max_concurrency=1,
        total_live_cap=16,
        blank_pool_min=1,
        blank_pool_max=1,
    )
    for tier in (32, 64)
}
_EXTERNAL_PI_CAPACITY_POLICY = _EXTERNAL_PI_CAPACITY_POLICIES[32]
# OpenAI concurrency equals the tier; the ten-minute call allowance grows faster
# because an MCP research turn spends 10-13 model calls and a full tier of turns
# cycles several times per window.
_EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS = {32: 512, 64: 4096}


def validate_deployment_identity(settings: Settings) -> None:
    """Validate the deployed environment and immutable release identity."""

    if settings.environment not in {"production", "staging"}:
        raise RuntimeError("PWC_ENVIRONMENT must be production or staging")
    if not settings.release_id or settings.release_id == "development":
        raise RuntimeError("PWC_RELEASE_ID is required")


def validate_auth_configuration(settings: Settings) -> bytes:
    """Validate shared-session cookies, signing keys, and verification authority."""

    if not settings.jwt_secret:
        raise RuntimeError("PWC_JWT_SECRET is required")
    if settings.session_cookie_domain:
        raise RuntimeError("deployed session cookies must be host-only")
    expected_cookie = {
        "production": "pwc_session",
        "staging": "pwc_staging_session",
    }[settings.environment]
    if settings.session_cookie_name != expected_cookie:
        raise RuntimeError(
            f"PWC_SESSION_COOKIE_NAME must be {expected_cookie!r} for "
            f"{settings.environment}"
        )
    if settings.shared_session_cookie_name != "pwc_shared_session":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_NAME must be 'pwc_shared_session'"
        )
    if settings.shared_session_cookie_domain != ".paperswithcode.co":
        raise RuntimeError(
            "PWC_SHARED_SESSION_COOKIE_DOMAIN must be '.paperswithcode.co'"
        )
    if not settings.session_verification_public_key:
        raise RuntimeError("PWC_SESSION_VERIFICATION_PUBLIC_KEY is required")
    try:
        public_bytes = base64.urlsafe_b64decode(
            settings.session_verification_public_key
            + "=" * (-len(settings.session_verification_public_key) % 4)
        )
        Ed25519PublicKey.from_public_bytes(public_bytes)
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "PWC_SESSION_VERIFICATION_PUBLIC_KEY must be a base64url Ed25519 key"
        ) from error
    if settings.auth_authority_origin != "https://paperswithcode.co":
        raise RuntimeError(
            "PWC_AUTH_AUTHORITY_ORIGIN must be 'https://paperswithcode.co'"
        )
    required_return_origins = {
        "https://paperswithcode.co",
        "https://staging.paperswithcode.co",
    }
    if settings.auth_return_origin_set != required_return_origins:
        raise RuntimeError(
            "PWC_AUTH_RETURN_ORIGINS must contain production and staging origins"
        )
    if settings.environment == "production":
        if not settings.session_signing_private_key:
            raise RuntimeError("production requires PWC_SESSION_SIGNING_PRIVATE_KEY")
        try:
            private_bytes = base64.urlsafe_b64decode(
                settings.session_signing_private_key
                + "=" * (-len(settings.session_signing_private_key) % 4)
            )
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
            derived_public = private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                "PWC_SESSION_SIGNING_PRIVATE_KEY must be a base64url Ed25519 key"
            ) from error
        if derived_public != public_bytes:
            raise RuntimeError("shared-session signing and verification keys differ")
    elif settings.session_signing_private_key:
        raise RuntimeError("staging must not have the session signing private key")
    return public_bytes


def validate_runtime_storage(settings: Settings) -> None:
    """Validate deployed read/write paths outside immutable releases."""

    if not Path(settings.frontend_dist_dir).is_absolute():
        raise RuntimeError("PWC_FRONTEND_DIST_DIR must be absolute")
    writable = {
        "RUNTIME_DATA_DIR": settings.runtime_data_dir,
        "CODEX_ADD_EVALS_SPOOL_DIR": settings.codex_add_evals_spool_dir,
        "CHAT_AGENT_CWD": settings.chat_agent_cwd,
        "CHAT_RECOVERY_SPOOL_DIR": settings.chat_recovery_spool_dir,
    }
    for name, value in writable.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing writable directory")

    for name, value in {
        "CRON_LOG_DIR": settings.cron_log_dir,
        "CRON_LOCK_DIR": settings.cron_lock_dir,
    }.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing readable directory")

    thumbnail_store = _resolved_absolute(
        "THUMBNAIL_TEMP_CACHE_DIR", settings.thumbnail_temp_cache_dir
    )
    if not thumbnail_store.is_dir() or not os.access(thumbnail_store, os.R_OK):
        raise RuntimeError(
            "PWC_THUMBNAIL_CACHE_DIR must be an existing readable directory"
        )


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


def validate_environment_policy(settings: Settings) -> None:
    """Validate production/staging isolation and mutation ownership."""

    if settings.environment == "production":
        if not settings.catalog_mutations_enabled or not settings.cron_enabled:
            raise RuntimeError(
                "production catalog mutations and CRON must remain enabled"
            )
    else:
        if settings.catalog_mutations_enabled:
            raise RuntimeError("staging catalog mutations must be disabled")
        if settings.cron_enabled:
            raise RuntimeError("staging CRON must be disabled")
        if settings.db_search_path != "staging,public":
            raise RuntimeError("staging database search_path must be staging,public")
        if not settings.production_jwt_fingerprint:
            raise RuntimeError("staging requires PWC_PRODUCTION_JWT_FINGERPRINT")
        fingerprint = hashlib.sha256(settings.jwt_secret.encode()).hexdigest()
        if fingerprint == settings.production_jwt_fingerprint:
            raise RuntimeError("staging must not reuse the production JWT secret")
        if not settings.chat_enabled:
            raise RuntimeError("staging chat feature must be enabled")


def _validate_private_paper_compiler_settings(settings: Settings) -> str:
    """Verify the only supported staging compiler transport without logging secrets."""
    try:
        image = validate_staging_sandbox_compiler_identity(
            settings.chat_latex_compiler_hf_sandbox_image,
            settings.chat_latex_compiler_hf_sandbox_namespace,
        )
    except EnvelopeError as error:
        raise RuntimeError(
            "private paper runtime requires an immutable Sandbox image"
        ) from error
    if not settings.chat_latex_compiler_hf_sandbox_token:
        raise RuntimeError("private paper runtime requires a Sandbox credential")
    if not settings.hf_token:
        raise RuntimeError("private paper runtime requires the staging Hub identity")
    if (
        settings.chat_latex_compiler_hf_sandbox_flavor != "cpu-upgrade"
        or settings.chat_latex_compiler_hf_sandbox_idle_timeout_seconds != 180
    ):
        raise RuntimeError("private paper runtime Sandbox limits are invalid")
    if (
        settings.chat_latex_compiler_hf_sandbox_egress_policy_attestation
        != _STAGING_LATEX_COMPILER_EGRESS_ATTESTATION
    ):
        raise RuntimeError("private paper runtime Sandbox egress is unattested")
    try:
        encoded = settings.chat_latex_compiler_signing_private_key
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as error:
        raise RuntimeError("private paper runtime signing key is invalid") from error
    return image


def _validate_private_paper_qualification_evidence(*, image: str) -> None:
    """Bind paper activation to root-produced, content-free staging evidence."""
    evidence_path = STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE
    try:
        evidence_gid = grp.getgrnam(_STAGING_LATEX_COMPILER_EVIDENCE_GROUP).gr_gid
        directory_stat = evidence_path.parent.lstat()
        evidence_stat = evidence_path.lstat()
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or stat.S_IMODE(directory_stat.st_mode) != 0o750
            or directory_stat.st_uid != 0
            or directory_stat.st_gid != evidence_gid
            or not stat.S_ISREG(evidence_stat.st_mode)
            or stat.S_IMODE(evidence_stat.st_mode) != 0o640
            or evidence_stat.st_uid != 0
            or evidence_stat.st_gid != evidence_gid
            or evidence_stat.st_nlink != 1
            or evidence_stat.st_size > 16_384
        ):
            raise ValueError
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "private paper qualification evidence is unavailable"
        ) from error
    checks = payload.get("checks") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "schema_version",
            "environment",
            "compiler_image",
            "passed",
            "total",
            "checks",
        }
        or not isinstance(checks, dict)
        or set(checks) != _STAGING_LATEX_QUALIFICATION_CHECKS
        or payload.get("schema_version") != 1
        or payload.get("environment") != "staging"
        or payload.get("compiler_image") != image
        or type(payload.get("passed")) is not int
        or type(payload.get("total")) is not int
        or payload["passed"] != payload["total"]
        or payload["total"] < len(_STAGING_LATEX_QUALIFICATION_CHECKS)
        or any(checks[name] is not True for name in _STAGING_LATEX_QUALIFICATION_CHECKS)
    ):
        raise RuntimeError("private paper qualification evidence is incomplete")


def validate_private_paper_runtime(settings: Settings) -> None:
    """Fail closed unless the private per-job paper path has all staging gates."""
    user_paper_flags = (
        settings.chat_latex_paper_enabled,
        settings.chat_latex_compiler_jobs_enabled,
    )
    any_private_paper_flag = any(user_paper_flags) or (
        settings.chat_latex_compiler_qualification_mode
    )
    if not any_private_paper_flag:
        if settings.environment == "staging" and settings.chat_posterly_enabled:
            raise RuntimeError("staging Posterly must remain disabled")
        return
    if settings.environment != "staging":
        raise RuntimeError("private paper runtime is staging-only")
    if settings.chat_posterly_enabled:
        raise RuntimeError("staging Posterly must remain disabled")
    if any(user_paper_flags) and settings.chat_artifact_shared_preview_enabled:
        raise RuntimeError("private paper runtime shared previews must remain disabled")
    if (
        settings.chat_artifact_storage_backend != "hf_bucket"
        or settings.chat_artifact_hf_bucket_id
        != _STAGING_LATEX_COMPILER_ARTIFACT_BUCKET
    ):
        raise RuntimeError("private paper runtime requires the private bucket")
    image = _validate_private_paper_compiler_settings(settings)
    if settings.chat_latex_compiler_qualification_mode:
        if any(user_paper_flags):
            raise RuntimeError(
                "private paper qualification must keep user features disabled"
            )
        return
    if not all(user_paper_flags):
        raise RuntimeError("private paper runtime flags must be coherent")
    _validate_private_paper_qualification_evidence(image=image)


def validate_chat_runtime_descriptor(settings: Settings) -> bool:
    """Validate enabled, dormant, or legacy chat state and return armed status."""

    validate_chat_configuration = settings.chat_enabled
    if not settings.chat_enabled and settings.environment == "production":
        admission_controls = (
            settings.chat_new_chat_modal_percentage != 0
            or settings.chat_blank_pool_enabled
            or settings.chat_public_admission_enabled
            or settings.chat_sandbox_admission_enabled
        )
        legacy_descriptor = (
            settings.chat_default_backend == "local_mcp"
            and not settings.chat_modal_image_version
            and not settings.chat_pwc_cli_version
            and not settings.chat_worker_contract_version
            and not settings.chat_system_prompt_sha256
        )
        dormant_descriptor = (
            settings.chat_default_backend == "modal_cli"
            and bool(settings.chat_modal_image_version)
            and bool(settings.chat_pwc_cli_version)
            and bool(settings.chat_worker_contract_version)
            and bool(settings.chat_system_prompt_sha256)
        )
        if admission_controls or not (legacy_descriptor or dormant_descriptor):
            raise RuntimeError(
                "disabled production contains an active or incomplete chat runtime descriptor"
            )
        if dormant_descriptor:
            try:
                require_immutable_image_id(settings.chat_modal_image_version)
            except ValueError as error:
                raise RuntimeError(
                    f"dormant production chat runtime is invalid: {error}"
                ) from error
            from backend.chat_sandbox_worker.prompt import sha256

            if settings.chat_system_prompt_sha256 != sha256():
                raise RuntimeError(
                    "dormant production prompt and execution limits disagree"
                )
            prepared_controls = (
                settings.chat_persistent_worker_enabled
                or settings.chat_title_generation_enabled
                or settings.chat_sandbox_cpu_limit is not None
                or settings.chat_sandbox_memory_limit_mib is not None
                or settings.chat_operational_alerts_enabled
            )
            validate_chat_configuration = prepared_controls
        elif (
            settings.chat_persistent_worker_enabled
            or settings.chat_title_generation_enabled
            or settings.chat_sandbox_cpu_limit is not None
            or settings.chat_sandbox_memory_limit_mib is not None
            or settings.chat_operational_alerts_enabled
        ):
            raise RuntimeError(
                "legacy production cannot contain armed chat preparation"
            )
    if validate_chat_configuration:
        _validate_chat_runtime_identity(settings)
        _validate_chat_execution_identity(settings)
    return validate_chat_configuration


def validate_chat_scope_guardrail_configuration(settings: Settings) -> None:
    if not settings.chat_scope_guardrail_enabled:
        return
    if settings.chat_scope_guardrail_glm_model != "zai-org/GLM-5.3-Flash:baseten":
        raise RuntimeError("scope guardrail GLM must pin the Baseten provider")
    if settings.chat_scope_guardrail_openai_model != "gpt-5.6-luna":
        raise RuntimeError("scope guardrail fallback must use direct Luna")
    if settings.chat_scope_guardrail_max_context_chars != 8_000:
        raise RuntimeError("scope guardrail context must preserve a full API message")
    if not all(
        (
            settings.chat_scope_guardrail_hf_token,
            settings.chat_scope_guardrail_hf_bill_to,
            settings.chat_scope_guardrail_openai_api_key,
        )
    ):
        raise RuntimeError("scope guardrail requires dedicated server credentials")
    if settings.chat_scope_guardrail_hf_token == settings.hf_token:
        raise RuntimeError("scope guardrail must not reuse the main HF credential")
    private_paper_mode = (
        settings.chat_latex_paper_enabled
        or settings.chat_latex_compiler_jobs_enabled
        or settings.chat_latex_compiler_qualification_mode
    )
    if settings.environment == "staging" and (
        not settings.chat_artifacts_enabled
        or (
            not private_paper_mode and not settings.chat_artifact_shared_preview_enabled
        )
        or settings.chat_artifact_storage_backend != "hf_bucket"
        or not settings.chat_artifact_hf_bucket_id
    ):
        raise RuntimeError("scope guardrail must preserve staging research artifacts")
    if settings.chat_posterly_enabled:
        raise RuntimeError("Posterly must remain disabled with scope enforcement")


def validate_chat_provider_policy(
    settings: Settings,
    *,
    include_openrouter: bool = True,
) -> None:
    """Validate inference credentials, discovery, gateway, search, and OpenRouter."""

    validate_chat_scope_guardrail_configuration(settings)

    if not all(
        (
            settings.hf_oauth_client_id,
            settings.hf_oauth_client_secret,
            settings.hf_oauth_credential_secret,
        )
    ):
        raise RuntimeError(
            "enabled chat requires the Hugging Face OAuth authentication path"
        )
    discovered = settings.chat_model_choices
    expected_huggingface_route = "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"
    expected_openrouter_route = "deepseek/deepseek-v4-flash-0731"
    if settings.chat_deepseek_v4_flash_route != expected_huggingface_route:
        raise RuntimeError("DeepSeek V4 Flash must use the reviewed Hugging Face route")
    if settings.chat_deepseek_v4_flash_openrouter_route != expected_openrouter_route:
        raise RuntimeError("DeepSeek V4 Flash must use the reviewed OpenRouter route")
    expected_provider = settings.chat_deepseek_v4_flash_provider
    if settings.environment == "production":
        expected_glm_route = "zai-org/GLM-5.3-Flash:fastest"
        if settings.chat_glm_5_3_flash_route != expected_glm_route:
            raise RuntimeError("GLM-5.3-Flash must use Hugging Face fastest routing")
        expected_discovery = (
            {
                "id": "zai-org/GLM-5.3-Flash",
                "label": "GLM-5.3-Flash",
                "route": expected_glm_route,
                "provider": "huggingface",
            },
        )
    else:
        expected_discovery = (
            {
                "id": "deepseek-ai/DeepSeek-V4-Flash-0731",
                "label": "DeepSeek V4 Flash",
                "route": (
                    expected_huggingface_route
                    if expected_provider == "huggingface"
                    else expected_openrouter_route
                ),
                "provider": expected_provider,
            },
        )
    if settings.chat_openai_direct_enabled:
        if not settings.openai_api_key:
            raise RuntimeError("direct OpenAI chat requires an OpenAI API key")
        if (
            settings.chat_openai_luna_route != "gpt-5.6-luna@openai"
            or settings.chat_openai_model != "gpt-5.6-luna"
        ):
            raise RuntimeError("direct OpenAI chat must use the reviewed Luna route")
        direct_choice = {
            "id": "gpt-5.6-luna@openai",
            "label": (
                "GPT-5.6 Luna"
                if settings.environment == "production"
                else "GPT-5.6 Luna (Direct)"
            ),
            "route": settings.chat_openai_luna_route,
            "provider": "openai",
        }
        if settings.environment == "production":
            expected_discovery = (direct_choice,) + expected_discovery
    if settings.environment == "staging":
        expected_kimi_route = "moonshotai/Kimi-K3:baseten"
        if settings.chat_kimi_route != expected_kimi_route:
            raise RuntimeError("Kimi K3 must use the reviewed Hugging Face route")
        if settings.chat_luna_route != "openai/gpt-5.6-luna":
            raise RuntimeError("GPT-5.6 Luna must use the reviewed OpenAI route")
        expected_discovery += (
            {
                "id": "moonshotai/Kimi-K3",
                "label": "Kimi K3",
                "route": expected_kimi_route,
                "provider": "huggingface",
            },
            {
                "id": "gpt-5.6-luna@openrouter",
                "label": "GPT-5.6 Luna",
                "route": settings.chat_luna_route,
                "provider": "openrouter",
            },
        )
        if settings.chat_openai_direct_enabled:
            expected_discovery = (direct_choice,) + expected_discovery
    if settings.chat_alternative_model_enabled:
        if settings.environment != "staging":
            raise RuntimeError("alternative chat models are staging-only")
        if (
            settings.chat_alternative_model != "openai/gpt-5.6-luna"
            and settings.chat_alternative_model
            not in {choice["id"] for choice in expected_discovery}
        ):
            candidate_labels = {
                "openai/gpt-5.6-luna": "GPT-5.6 Luna",
                "google/gemini-3.7-flash": "Gemini 3.7 Flash",
            }
            expected_discovery += (
                {
                    "id": settings.chat_alternative_model,
                    "label": candidate_labels[settings.chat_alternative_model],
                    "route": settings.chat_alternative_model,
                    "provider": "openrouter",
                },
            )
    discovery_projection = tuple(
        {
            "id": choice["id"],
            "label": choice["label"],
            "route": choice["route"],
            "provider": choice["provider"],
        }
        for choice in discovered
    )
    if discovery_projection != expected_discovery:
        raise RuntimeError("chat discovery contains an unreviewed model configuration")
    if settings.chat_default_backend != "modal_cli":
        raise RuntimeError("deployed chat must use the isolated Modal backend")
    expected_modal_percentage = 100 if settings.chat_enabled else 0
    if settings.chat_new_chat_modal_percentage != expected_modal_percentage:
        raise RuntimeError("chat must not spill new sessions to local execution")
    if settings.chat_web_search_enabled:
        web_search_url = urlsplit(settings.chat_web_search_exa_url)
        if (
            settings.chat_web_search_provider != "exa"
            or not settings.chat_web_search_exa_api_key
            or web_search_url.scheme != "https"
            or web_search_url.hostname != "api.exa.ai"
            or web_search_url.path.rstrip("/") != "/search"
            or settings.chat_web_search_max_calls != 3
            or settings.chat_web_search_timeout_seconds != 3
            or settings.chat_web_search_result_count != 5
            or settings.chat_web_search_max_result_bytes != 16 * 1024
            or settings.chat_web_search_query_max_chars != 500
            or settings.chat_web_search_monthly_warning_calls != 1_000
            or settings.chat_web_search_monthly_hard_calls != 1_200
        ):
            raise RuntimeError("web-search runtime descriptor is invalid")
    if settings.chat_hf_catalog_enabled:
        if (
            settings.chat_hf_catalog_timeout_seconds != 10
            or settings.chat_hf_catalog_max_calls != 6
            or settings.chat_hf_recursive_list_max_calls != 2
            or settings.chat_hf_discovery_max_limit != 50
            or settings.chat_hf_max_files != 200
            or settings.chat_hf_max_depth != 10
            or settings.chat_hf_card_metadata_max_bytes != 32 * 1024
            or settings.chat_hf_card_text_max_bytes != 192 * 1024
            or settings.chat_hf_card_total_max_bytes != 224 * 1024
            or settings.chat_hf_cache_max_entries != 512
            or settings.chat_hf_cache_max_bytes != 64 * 1024 * 1024
            or settings.chat_hf_response_max_bytes != 256 * 1024
        ):
            raise RuntimeError("HF catalog runtime descriptor is invalid")
    _validate_chat_gateway_policy(settings)
    if include_openrouter:
        _validate_chat_openrouter_policy(settings)


def validate_chat_capacity_and_spend_policy(settings: Settings) -> None:
    """Validate migration controls and the chat capacity policy."""

    validate_external_pi_migration_policy(settings)
    _validate_chat_capacity_and_spend_policy(settings)


def _validate_chat_capacity_policy(settings: Settings) -> None:
    configured = SandboxCapacityPolicy(
        max_concurrency=settings.chat_max_concurrency,
        user_max_concurrency=settings.chat_user_max_concurrency,
        total_live_cap=settings.chat_sandbox_total_live_cap,
        blank_pool_min=settings.chat_blank_pool_min,
        blank_pool_max=settings.chat_blank_pool_max,
    )
    candidates = (
        tuple(_EXTERNAL_PI_CAPACITY_POLICIES.values())
        if settings.chat_external_pi_admission_enabled
        else (_SANDBOX_CAPACITY_POLICY,)
    )
    if configured in candidates:
        return
    if (
        settings.environment == "staging"
        and settings.chat_external_pi_admission_enabled
        and settings.chat_executor_remote_transport_enabled
        and any(
            configured == replace(expected, blank_pool_min=4, blank_pool_max=4)
            for expected in candidates
        )
    ):
        return
    raise RuntimeError("chat capacity must be the reviewed runtime profile")


def _external_pi_capacity_tier(settings: Settings) -> int | None:
    """Return the reviewed tier whose turn and OpenAI budgets the settings match."""

    tier = settings.chat_max_concurrency
    if (
        tier in _EXTERNAL_PI_CAPACITY_POLICIES
        and settings.chat_openai_global_max_concurrency == tier
        and settings.chat_openai_global_rate_limit_calls
        == _EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS[tier]
    ):
        return tier
    return None


def _validate_chat_capacity_and_spend_policy(settings: Settings) -> None:
    """Validate sandbox spend, capacity, alerting, and provider reserve."""

    if not settings.chat_sandbox_spend_enforcement_enabled:
        raise RuntimeError("PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED is required")
    configured_spend = SandboxSpendPolicy(
        warning_microusd=settings.chat_sandbox_warning_microusd,
        application_cap_microusd=settings.chat_sandbox_application_cap_microusd,
        environment_cap_microusd=settings.chat_sandbox_environment_cap_microusd,
        workspace_cap_microusd=settings.chat_sandbox_workspace_cap_microusd,
    )
    if settings.chat_sandbox_provider_mode == "team_environments":
        team_policy_version = next(
            (
                version
                for version, policy in _TEAM_SANDBOX_SPEND_POLICIES.items()
                if configured_spend == policy
            ),
            None,
        )
        expected_spend = _TEAM_SANDBOX_SPEND_POLICIES.get(team_policy_version)
    else:
        team_policy_version = None
        expected_spend = _STARTER_SANDBOX_SPEND_POLICY
        if (
            settings.environment == "staging"
            and settings.chat_sandbox_modal_workspace == "nielsrogge"
            and configured_spend == _STAGING_STARTER_105_SPEND_POLICY
        ):
            expected_spend = _STAGING_STARTER_105_SPEND_POLICY
    if configured_spend != expected_spend:
        if settings.chat_sandbox_provider_mode == "starter_workspace":
            raise RuntimeError(
                "sandbox spend policy must be $75/$100/$250 with no environment cap"
            )
        raise RuntimeError("team sandbox spend policy is not reviewed")
    _validate_chat_capacity_policy(settings)
    expected_modal_environment = f"pwc-chat-{settings.environment}"
    if settings.chat_sandbox_modal_environment != expected_modal_environment:
        raise RuntimeError(
            f"PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT must be {expected_modal_environment}"
        )
    if not settings.chat_sandbox_modal_workspace:
        raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_WORKSPACE is required")
    if not settings.chat_sandbox_modal_owner_username:
        raise RuntimeError("PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME is required")
    if settings.chat_sandbox_provider_mode == "team_environments":
        policy_suffix = {
            "v1": "125-v1",
            "v2": "250-v2",
            "v3": "250-warn200-app225-v3",
        }[team_policy_version]
        expected_attestation = (
            f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-"
            f"{settings.environment}-{policy_suffix}"
        )
    else:
        starter_suffix = (
            "starter-app105-v2"
            if expected_spend == _STAGING_STARTER_105_SPEND_POLICY
            else "starter-v1"
        )
        expected_attestation = (
            f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-"
            f"{settings.environment}-{starter_suffix}"
        )
    if settings.chat_sandbox_budget_attestation != expected_attestation:
        raise RuntimeError(
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION does not match configured policy"
        )
    primary_alert = settings.chat_sandbox_slack_webhook_url
    fallback_alert = settings.chat_sandbox_alert_fallback_webhook_url
    if not primary_alert or not fallback_alert:
        raise RuntimeError("primary and fallback chat alert destinations are required")
    if fallback_alert == primary_alert:
        raise RuntimeError("primary and fallback chat alert destinations must differ")
    if not settings.chat_sandbox_runbook_url:
        raise RuntimeError("PWC_CHAT_SANDBOX_RUNBOOK_URL is required")
    if not settings.chat_sandbox_operator_username_set:
        raise RuntimeError("PWC_CHAT_SANDBOX_OPERATOR_USERNAMES is required")
    if settings.environment == "production" and (
        not settings.chat_operational_alerts_enabled
        or settings.chat_provider_alert_window_seconds != 300
        or settings.chat_provider_alert_min_failures != 5
        or settings.chat_provider_alert_failure_percent != 50
    ):
        raise RuntimeError(
            "production operational alerts require the reviewed 5-minute, "
            "5-failure, 50-percent provider policy"
        )
    rate = (settings.chat_sandbox_cpu_limit or settings.chat_sandbox_cpu) * 40 + (
        settings.chat_sandbox_memory_limit_mib or settings.chat_sandbox_memory_mib
    ) / 1024 * 7
    burst = int(
        rate
        * settings.chat_sandbox_total_live_cap
        * (
            settings.chat_sandbox_watchdog_seconds
            + settings.chat_sandbox_drain_grace_seconds
            + settings.chat_sandbox_termination_grace_seconds
        )
    ) + (
        settings.chat_sandbox_reconciliation_allowance_microusd
        * settings.chat_sandbox_total_live_cap
    )
    if (
        settings.chat_sandbox_workspace_cap_microusd
        - settings.chat_sandbox_application_cap_microusd
        < burst
    ):
        raise RuntimeError(
            "sandbox provider reserve is smaller than the worst-case aggregate burst"
        )
    _validate_chat_title_policy(settings)
    _validate_chat_resource_policy(settings)


def _validate_chat_runtime_identity(settings: Settings) -> None:
    """Validate immutable worker, snapshot, and retention identity."""

    if not all(
        (
            settings.chat_modal_image_version,
            settings.chat_pwc_cli_version,
            settings.chat_worker_contract_version,
            settings.chat_system_prompt_sha256,
        )
    ):
        raise RuntimeError("chat runtime descriptor is incomplete")
    try:
        require_immutable_image_id(settings.chat_modal_image_version)
    except ValueError as error:
        raise RuntimeError(f"chat runtime is invalid: {error}") from error
    if settings.chat_workspace_snapshots_enabled:
        raise RuntimeError("directory snapshots must remain disabled")
    if settings.chat_new_session_pi_percentage not in (0, 100):
        raise RuntimeError("Pi admission must be stopped or fully cut over")
    if (
        settings.chat_new_session_pi_percentage == 100
        and settings.chat_default_agent_harness != "pi"
    ):
        raise RuntimeError("full Pi admission must default to Pi")
    if (
        settings.chat_new_session_pi_percentage == 0
        and settings.chat_default_agent_harness != "claude"
    ):
        raise RuntimeError("stopped Pi admission must default to Claude")
    pi_identity_present = settings.chat_pi_runtime_enabled
    if pi_identity_present:
        expected_pi_identity = (
            settings.chat_claude_sdk_version == SDK_VERSION
            and settings.chat_pi_version == PI_VERSION
            and settings.chat_pi_source_commit == PI_SOURCE_COMMIT
            and settings.chat_pi_node_version == PI_NODE_VERSION
            and settings.chat_pi_node_sha256 == PI_NODE_SHA256
            and settings.chat_restricted_hf_cli_version == RESTRICTED_HF_CLI_VERSION
        )
        if not expected_pi_identity:
            raise RuntimeError(
                "dual-harness runtime identity is incomplete or mismatched"
            )
        if any(
            (
                settings.chat_pi_self_extension_enabled,
                settings.chat_pi_durable_extensions_enabled,
                settings.chat_pi_max_extension_files,
                settings.chat_pi_max_extension_bytes,
                settings.chat_pi_max_reloads_per_turn,
            )
        ):
            raise RuntimeError("Pi extension surfaces must remain disabled")
    if (
        settings.chat_session_limit != 100
        or settings.chat_user_byte_limit != 100 * 1024 * 1024
    ):
        raise RuntimeError(
            "chat retention quotas must remain 100 active chats and 100 MB"
        )


def _validate_chat_gateway_policy(settings: Settings) -> None:
    expected_gateway = {
        "staging": "chat-gateway-staging.paperswithcode.co",
        "production": "chat-gateway.paperswithcode.co",
    }[settings.environment]
    try:
        gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    except ValueError as error:
        raise RuntimeError(f"chat runtime is invalid: {error}") from error
    if gateway_host != expected_gateway:
        raise RuntimeError(f"chat gateway must use {expected_gateway}")


def _validate_chat_title_policy(settings: Settings) -> None:
    """Validate the environment-specific title provider and spend circuit."""

    if not settings.chat_scope_guardrail_enabled:
        raise RuntimeError("enabled chat requires the research-scope guardrail")
    if (
        not settings.chat_title_generation_enabled
        or settings.chat_title_credential_owner != "nielsr"
        or settings.chat_title_credential_environment != settings.environment
    ):
        raise RuntimeError(
            "an environment-scoped title credential owned by nielsr is required"
        )
    hf_glm = (
        settings.chat_title_provider == "huggingface"
        and settings.chat_title_model == "zai-org/GLM-5.3-Flash:baseten"
        and settings.chat_title_hf_token
        and settings.chat_title_bill_to
    )
    if not hf_glm:
        raise RuntimeError("an HF GLM title credential is required")
    if (
        settings.chat_title_max_tokens != 64
        or settings.chat_title_monthly_cap_microusd != 25_000_000
        or not 0
        < settings.chat_title_warning_microusd
        < settings.chat_title_monthly_cap_microusd
        or settings.chat_title_max_call_microusd
        > settings.chat_title_monthly_cap_microusd
        or settings.chat_title_max_call_microusd
        < (
            8_000 * settings.chat_title_input_microusd_per_token
            + settings.chat_title_max_tokens
            * settings.chat_title_output_microusd_per_token
        )
    ):
        raise RuntimeError("the title model and $25 monthly circuit are invalid")


def _validate_chat_openrouter_policy(settings: Settings) -> None:
    """Validate deployed OpenRouter credentials and durable accounting."""

    if (
        settings.chat_openrouter_routing_enabled
        and settings.chat_openrouter_routing_policy == "preferred_provider"
    ):
        providers = [
            value.strip()
            for value in settings.chat_openrouter_preferred_providers.split(",")
            if value.strip()
        ]
        if not providers or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9._/-]{0,127}", value)
            for value in providers
        ):
            raise RuntimeError(
                "preferred-provider routing requires valid provider slugs"
            )

    if (
        settings.environment == "staging"
        and not settings.chat_openrouter_server_funded_enabled
    ):
        raise RuntimeError("staging OpenRouter funded/BYOK paths must remain enabled")
    # Production's OpenAI and HF routes do not use the shared OpenRouter key.
    # Keep durable accounting validation for existing sessions and BYOK below.
    if (
        settings.chat_openrouter_server_funded_enabled
        and not settings.chat_openrouter_api_key
    ):
        raise RuntimeError("server-funded OpenRouter chat requires an OpenRouter key")
    if settings.chat_openrouter_workspace_monthly_budget_usd != 200:
        raise RuntimeError("OpenRouter workspace budget must equal $200")
    expected_user_budget = 1 if settings.environment == "staging" else 5
    if settings.chat_openrouter_monthly_user_budget_usd != expected_user_budget:
        raise RuntimeError(
            f"OpenRouter per-user budget must equal ${expected_user_budget}"
        )
    if (
        settings.chat_openrouter_daily_budget_usd != 10
        or settings.chat_openrouter_rate_limit_window_seconds != 600
        or settings.chat_openrouter_user_rate_limit_calls != 30
        or settings.chat_openrouter_global_rate_limit_calls != 80
    ):
        raise RuntimeError("OpenRouter abuse circuit policy is invalid")
    if not settings.chat_openrouter_user_tracking_secret:
        raise RuntimeError("OpenRouter user tracking HMAC is required")
    from backend.services.openrouter_byok_service import credential_keyring
    from backend.services.openrouter_user_budget_service import (
        RequestBounds,
        safe_maximum_microusd,
    )

    try:
        credential_keyring(settings)
        maximum = max(
            safe_maximum_microusd(
                settings,
                route,
                RequestBounds(
                    request_bytes=1,
                    maximum_output_tokens=PROVIDER_OUTPUT_TOKEN_LIMIT,
                    payload={"messages": [{"role": "user", "content": "x"}]},
                ),
            )
            for route in settings.chat_openrouter_routes
        )
    except (ValueError, RuntimeError) as error:
        raise RuntimeError(
            "OpenRouter durable accounting configuration is invalid"
        ) from error
    if maximum > 1_000_000:
        raise RuntimeError(
            "OpenRouter minimum request bound exceeds the per-user hard budget"
        )
    from backend.services.openrouter_budget_service import (
        OpenRouterBudgetUnavailable,
        validate_openrouter_guardrail,
    )

    try:
        validate_openrouter_guardrail(settings)
    except OpenRouterBudgetUnavailable as error:
        raise RuntimeError(
            "OpenRouter provider-enforced guardrail is invalid"
        ) from error


def _is_staging_durable_external_qualification_profile(settings: Settings) -> bool:
    """Recognize only the exact pool-free staging qualification bridge."""

    return all(
        (
            settings.environment == "staging",
            settings.chat_openai_direct_enabled,
            not settings.chat_external_pi_admission_enabled,
            settings.chat_external_pi_supervisor_enabled,
            settings.chat_external_pi_ready_registry_enabled,
            settings.chat_external_pi_runtime_contract_version
            == "durable-external-pi-v1",
            settings.chat_external_pi_worker_contract_version == "external-pi-v1",
            settings.chat_durable_turn_dispatch_enabled,
            settings.chat_turn_event_journal_schema_enabled,
            settings.chat_sandbox_executor_enabled,
            settings.chat_sandbox_executor_contract_version == "sandbox-executor-v1",
            settings.chat_remote_workspace_tools_enabled,
            settings.chat_remote_bash_enabled,
            settings.chat_remote_read_enabled,
            settings.chat_lazy_workspace_enabled,
            not settings.chat_blank_pool_enabled,
            not settings.chat_pi_prewarm_enabled,
            settings.chat_max_concurrency == 2,
            settings.chat_sandbox_total_live_cap == 3,
        )
    )


def _is_durable_external_admission_profile(settings: Settings) -> bool:
    """Recognize the approved pool-free external-harness serving profile."""

    return all(
        (
            settings.environment in {"staging", "production"},
            settings.chat_external_pi_admission_enabled,
            settings.chat_external_pi_supervisor_enabled,
            settings.chat_external_pi_ready_registry_enabled,
            settings.chat_external_pi_runtime_contract_version
            == "durable-external-pi-v1",
            settings.chat_external_pi_worker_contract_version == "external-pi-v1",
            settings.chat_durable_turn_dispatch_enabled,
            settings.chat_turn_event_journal_schema_enabled,
            settings.chat_sandbox_executor_enabled,
            settings.chat_sandbox_executor_contract_version == "sandbox-executor-v1",
            settings.chat_remote_workspace_tools_enabled,
            settings.chat_remote_bash_enabled,
            settings.chat_remote_read_enabled,
            settings.chat_lazy_workspace_enabled,
            not settings.chat_blank_pool_enabled,
            not settings.chat_pi_prewarm_enabled,
            _external_pi_capacity_tier(settings) is not None,
            settings.chat_user_max_concurrency == 1,
            settings.chat_openai_user_max_concurrency == 1,
            settings.chat_sandbox_total_live_cap == 16,
        )
    )


def _validate_chat_resource_policy(settings: Settings) -> None:
    """Validate sandbox resources and warm-pool lifetime."""

    if settings.chat_excalidraw_enabled != settings.chat_mcp_apps_host_enabled:
        raise RuntimeError("Excalidraw worker and MCP App host switches must match")
    if (
        settings.chat_sandbox_cpu_limit is not None
        and settings.chat_sandbox_cpu_limit < settings.chat_sandbox_cpu
    ):
        raise RuntimeError("chat CPU limit is below its request")
    if (
        settings.chat_sandbox_memory_limit_mib is not None
        and settings.chat_sandbox_memory_limit_mib < settings.chat_sandbox_memory_mib
    ):
        raise RuntimeError("chat memory limit is below its request")
    if settings.chat_blank_pool_enabled:
        if not settings.chat_persistent_worker_enabled:
            raise RuntimeError("blank pool requires persistent workers")
        if (
            settings.chat_blank_pool_min_remaining_seconds
            >= settings.chat_persistent_sandbox_lifetime_seconds
        ):
            raise RuntimeError("blank pool minimum remaining lifetime is invalid")
        if (
            settings.chat_blank_pool_rotate_before_seconds
            >= settings.chat_persistent_sandbox_lifetime_seconds
        ):
            raise RuntimeError("blank pool rotation window is invalid")
    if settings.chat_openai_direct_enabled:
        qualification_profile = _is_staging_durable_external_qualification_profile(
            settings
        )
        external_admission_profile = _is_durable_external_admission_profile(settings)
        if (
            not qualification_profile
            and not external_admission_profile
            and (
                not settings.chat_pi_prewarm_enabled
                or not settings.chat_blank_pool_enabled
                or settings.chat_effective_pi_prewarm_model
                != settings.chat_openai_luna_route
                or settings.chat_pi_prewarm_reasoning_effort != "low"
            )
        ):
            raise RuntimeError(
                "direct OpenAI chat requires the direct-Luna low-reasoning prewarm profile"
            )
    if settings.chat_pi_prewarm_enabled:
        if not settings.chat_blank_pool_enabled:
            raise RuntimeError("Pi prewarm requires the blank pool")
        if not settings.chat_persistent_worker_enabled:
            raise RuntimeError("Pi prewarm requires persistent workers")
        if settings.chat_default_agent_harness != "pi":
            raise RuntimeError("Pi prewarm requires Pi as the default harness")
        prewarm_model = settings.chat_effective_pi_prewarm_model
        if prewarm_model not in settings.chat_route_providers:
            raise RuntimeError("Pi prewarm model is not in the route registry")
        expected_prewarm_model = (
            settings.chat_openai_luna_route
            if settings.chat_openai_direct_enabled
            else (
                settings.chat_alternative_model
                if settings.chat_alternative_model_enabled
                else settings.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash-0731"]
            )
        )
        if prewarm_model != expected_prewarm_model:
            raise RuntimeError("Pi prewarm model does not match the qualified model")
        if not settings.chat_system_prompt_sha256:
            raise RuntimeError("Pi prewarm requires an immutable prompt digest")


def validate_external_pi_migration_policy(settings: Settings) -> None:
    """Keep each external-harness bridge independently reversible."""

    worker_switches = {
        "shadow": settings.chat_external_pi_shadow_enabled,
        "admission": settings.chat_external_pi_admission_enabled,
        "supervisor": settings.chat_external_pi_supervisor_enabled,
    }
    executor_switches = {
        "executor": settings.chat_sandbox_executor_enabled,
        "bash": settings.chat_remote_bash_enabled,
        "read": settings.chat_remote_read_enabled,
    }
    if settings.chat_executor_remote_transport_enabled:
        from backend.chat_sandbox_worker.executor_protocol import (
            MAX_COMMAND_BYTES,
            MAX_PATH_BYTES,
            MAX_REMOTE_READ_BYTES,
            MAX_TIMEOUT_MS,
        )

        if not settings.chat_external_pi_admission_enabled:
            raise RuntimeError(
                "remote executor transport requires external Pi admission"
            )
        if not all(
            (
                settings.chat_executor_cell_id,
                settings.chat_executor_admission_signing_key_id,
                settings.chat_executor_harness_key_id,
                settings.chat_executor_authorization_key_id,
                settings.chat_executor_authorization_keys_json,
            )
        ) or not settings.chat_executor_admission_signing_key_file.startswith(
            "/run/credentials/"
        ):
            raise RuntimeError(
                "remote executor transport requires systemd credential configuration"
            )
        try:
            authorization_keys = json.loads(
                settings.chat_executor_authorization_keys_json
            )
            if set(authorization_keys) - {"current", "previous"}:
                raise ValueError
            current_authorization_key = authorization_keys["current"]
            authorization_window = (
                current_authorization_key["not_after"]
                - current_authorization_key["not_before"]
            )
            now_seconds = int(time.time())
            if (
                set(current_authorization_key)
                != {"key_id", "public_key", "not_before", "not_after"}
                or current_authorization_key["key_id"]
                != settings.chat_executor_authorization_key_id
                or len(
                    base64.b64decode(
                        current_authorization_key["public_key"], validate=True
                    )
                )
                != 32
                or current_authorization_key["not_before"] <= 0
                or current_authorization_key["not_after"]
                <= current_authorization_key["not_before"]
                or authorization_window > 30 * 24 * 60 * 60
                or not current_authorization_key["not_before"]
                <= now_seconds
                <= current_authorization_key["not_after"]
            ):
                raise ValueError
            previous_authorization_key = authorization_keys.get("previous")
            if previous_authorization_key is not None and (
                not isinstance(previous_authorization_key, dict)
                or set(previous_authorization_key)
                != {"key_id", "public_key", "not_before", "not_after"}
                or previous_authorization_key["key_id"]
                == current_authorization_key["key_id"]
                or len(
                    base64.b64decode(
                        previous_authorization_key["public_key"], validate=True
                    )
                )
                != 32
                or previous_authorization_key["not_before"] <= 0
                or previous_authorization_key["not_after"]
                <= previous_authorization_key["not_before"]
                or previous_authorization_key["not_before"]
                >= current_authorization_key["not_before"]
                or previous_authorization_key["not_after"]
                - previous_authorization_key["not_before"]
                > 30 * 24 * 60 * 60
                or previous_authorization_key["not_after"]
                > current_authorization_key["not_before"] + 24 * 60 * 60
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise RuntimeError(
                "remote executor authorization key configuration is invalid"
            ) from None
        now_ms = int(time.time() * 1_000)
        if (
            settings.chat_executor_admission_key_not_before_ms <= 0
            or settings.chat_executor_admission_key_not_after_ms
            <= settings.chat_executor_admission_key_not_before_ms
            or settings.chat_executor_admission_key_not_after_ms
            - settings.chat_executor_admission_key_not_before_ms
            > 30 * 24 * 60 * 60 * 1_000
            or not settings.chat_executor_admission_key_not_before_ms
            <= now_ms
            <= settings.chat_executor_admission_key_not_after_ms
        ):
            raise RuntimeError("remote executor admission key window is invalid")
        if settings.chat_workspace_snapshots_enabled:
            raise RuntimeError("remote executor transport rejects snapshots")
        if (
            settings.chat_executor_max_parallel_operations != 4
            or settings.chat_tool_result_max_bytes != 24 * 1024
            or settings.chat_turn_tool_output_max_bytes != 96 * 1024
            or settings.chat_blank_pool_min_remaining_seconds != 240
            or settings.chat_persistent_sandbox_lifetime_seconds != 86_400
            or settings.chat_blank_pool_rotate_before_seconds != 3_600
            or settings.chat_bash_timeout_seconds != 30
            or MAX_COMMAND_BYTES != 64 * 1024
            or MAX_PATH_BYTES != 4 * 1024
            or MAX_TIMEOUT_MS != 30_000
            or MAX_REMOTE_READ_BYTES != 1024 * 1024
        ):
            raise RuntimeError("remote executor transport limits are inconsistent")
    if any(worker_switches.values()):
        try:
            external_worker_endpoints(settings)
        except ValueError as error:
            message = str(error).lower()
            if "ambiguous" in message:
                raise RuntimeError("external Pi worker topology is ambiguous") from None
            if "incomplete" in message or "not configured" in message:
                raise RuntimeError(
                    "external Pi worker endpoint topology is incomplete"
                ) from None
            raise RuntimeError(
                "external Pi worker endpoint must be an authenticated loopback service"
            ) from None
        if settings.chat_external_pi_worker_contract_version != "external-pi-v1":
            raise RuntimeError("external Pi worker identity is invalid")
    if any(executor_switches.values()):
        if settings.chat_sandbox_executor_contract_version != "sandbox-executor-v1":
            raise RuntimeError("sandbox executor contract is invalid")
        if (
            settings.chat_remote_bash_enabled or settings.chat_remote_read_enabled
        ) and not settings.chat_sandbox_executor_enabled:
            raise RuntimeError("remote Bash and Read require the sandbox executor")
    if (
        settings.chat_external_pi_heartbeat_seconds
        >= settings.chat_external_pi_lease_seconds
    ):
        raise RuntimeError("external Pi heartbeat must be shorter than the lease")
    if settings.chat_safe_cli_fast_path_enabled and not (
        settings.chat_remote_workspace_tools_enabled
    ):
        raise RuntimeError("safe CLI fast path requires remote workspace tools")
    if settings.chat_lazy_workspace_enabled and not (
        settings.chat_remote_workspace_tools_enabled
    ):
        raise RuntimeError("lazy workspaces require remote workspace tools")
    if settings.chat_external_pi_admission_enabled and not all(
        (
            settings.chat_remote_workspace_tools_enabled,
            settings.chat_lazy_workspace_enabled,
            settings.chat_durable_turn_dispatch_enabled,
        )
    ):
        raise RuntimeError(
            "external Pi admission requires remote workspace tools, lazy workspaces, "
            "and durable turn dispatch"
        )
    if settings.chat_external_pi_admission_enabled and not all(
        (
            settings.chat_sandbox_executor_enabled,
            settings.chat_remote_bash_enabled,
            settings.chat_remote_read_enabled,
        )
    ):
        raise RuntimeError(
            "external Pi admission requires the sandbox executor with Bash and Read"
        )
    if settings.chat_external_pi_admission_enabled:
        try:
            require_ordinary_research_mode(
                poster_mode=(
                    settings.chat_artifacts_enabled and settings.chat_posterly_enabled
                ),
                paper_artifacts_enabled=(
                    settings.chat_artifacts_enabled
                    and settings.chat_latex_paper_enabled
                    and settings.chat_latex_compiler_jobs_enabled
                ),
            )
        except UnsupportedChatMode as error:
            raise RuntimeError(
                "external Pi admission supports ordinary research only"
            ) from error
        if settings.chat_agent_timeout_seconds != 180:
            raise RuntimeError(
                "external Pi ordinary research requires a 180-second deadline"
            )
        try:
            require_external_admission_contract(
                ExternalAdmissionContract(
                    durable_dispatch=settings.chat_durable_turn_dispatch_enabled,
                    event_journal_schema=(
                        settings.chat_turn_event_journal_schema_enabled
                    ),
                    external_supervisor=settings.chat_external_pi_supervisor_enabled,
                    ready_worker_registry=(
                        settings.chat_external_pi_ready_registry_enabled
                    ),
                    remote_workspace_tools=(
                        settings.chat_remote_workspace_tools_enabled
                    ),
                    lazy_workspace=settings.chat_lazy_workspace_enabled,
                    sandbox_executor=settings.chat_sandbox_executor_enabled,
                    remote_bash=settings.chat_remote_bash_enabled,
                    remote_read=settings.chat_remote_read_enabled,
                    worker_contract_version=(
                        settings.chat_external_pi_worker_contract_version
                    ),
                    runtime_contract_version=(
                        settings.chat_external_pi_runtime_contract_version
                    ),
                )
            )
        except ValueError as error:
            raise RuntimeError(
                "external Pi admission requires the complete durable runtime contract"
            ) from error


def _validate_chat_execution_identity(settings: Settings) -> None:
    """Validate execution limits against the immutable prompt identity."""

    from backend.chat_execution_policy import validate_execution_limits
    from backend.chat_sandbox_worker.prompt import sha256 as prompt_sha256

    try:
        validate_execution_limits(
            max_turns=settings.chat_max_turns,
            max_tool_calls=settings.chat_max_tool_calls,
            max_direct_searches=settings.chat_max_direct_search_calls,
            max_web_searches=settings.chat_web_search_max_calls,
        )
    except ValueError as error:
        raise RuntimeError(str(error)) from error

    effective_prompt_hash = prompt_sha256(
        max_turns=settings.chat_max_turns,
        max_calls=settings.chat_max_tool_calls,
        max_searches=settings.chat_max_direct_search_calls,
    )
    if settings.chat_system_prompt_sha256 != effective_prompt_hash:
        raise RuntimeError("chat prompt and execution limits disagree")


def validate_release_manifest(settings: Settings) -> None:
    """Validate that the selected release manifest matches runtime settings."""

    manifest_path = Path(settings.frontend_dist_dir).parent / "release.json"
    if not manifest_path.is_file():
        raise RuntimeError("release.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = manifest.get("chat_runtime")
    expected_runtime = {
        "enabled": settings.chat_enabled,
        "new_chat_modal_percentage": settings.chat_new_chat_modal_percentage,
        "default_backend": settings.chat_default_backend,
        "modal_image_version": settings.chat_modal_image_version,
        "pwc_cli_version": settings.chat_pwc_cli_version,
        "worker_contract_version": settings.chat_worker_contract_version,
        "system_prompt_sha256": settings.chat_system_prompt_sha256,
    }
    if isinstance(runtime, dict) and settings.chat_pi_runtime_enabled:
        expected_runtime.update(
            {
                "default_agent_harness": settings.chat_default_agent_harness,
                "new_session_pi_percentage": settings.chat_new_session_pi_percentage,
                "claude_sdk_version": settings.chat_claude_sdk_version,
                "pi_version": settings.chat_pi_version,
                "pi_source_commit": settings.chat_pi_source_commit,
                "pi_node_version": settings.chat_pi_node_version,
                "pi_node_sha256": settings.chat_pi_node_sha256,
                "restricted_hf_cli_version": settings.chat_restricted_hf_cli_version,
            }
        )
    projected_runtime = (
        {key: runtime.get(key) for key in expected_runtime}
        if isinstance(runtime, dict)
        else runtime
    )
    if (
        projected_runtime != expected_runtime
        or manifest.get("release_id") != settings.release_id
    ):
        raise RuntimeError("running chat runtime differs from the release manifest")


def validate_deployed_mutation_policy(settings: Settings) -> None:
    """Keep deployed thumbnail writes outside web-service processes."""

    if settings.thumbnail_mutations_enabled:
        raise RuntimeError("deployed web services must not mutate thumbnails")


def validate_runtime(settings: Settings) -> dict[str, bool]:
    """Orchestrate fail-closed validation for one deployed release."""

    if not settings.is_deployed:
        return {"chat": settings.chat_enabled}

    validate_deployment_identity(settings)
    validate_auth_configuration(settings)
    validate_runtime_storage(settings)
    validate_codex_jobs_configuration(settings)
    validate_environment_policy(settings)
    validate_private_paper_runtime(settings)
    validate_external_pi_migration_policy(settings)
    validate_chat_configuration = validate_chat_runtime_descriptor(settings)
    if validate_chat_configuration:
        validate_chat_provider_policy(settings, include_openrouter=False)
        _validate_chat_capacity_and_spend_policy(settings)
        _validate_chat_openrouter_policy(settings)
    validate_release_manifest(settings)
    validate_deployed_mutation_policy(settings)
    return validate_frontend_dist(settings)


def validate_external_worker_reservation_schema(db) -> None:
    """Require model/migration parity for protected external-worker admission."""
    expected_columns = {
        "request_id": ("character varying", "NO", 200),
        "turn_id": ("uuid", "YES", None),
        "endpoint_id": ("character varying", "NO", 128),
        "worker_id": ("character varying", "NO", 128),
        "instance_id": ("uuid", "NO", None),
        "worker_generation": ("bigint", "NO", None),
        "release_id": ("character varying", "NO", 255),
        "contract_version": ("character varying", "NO", 128),
        "maximum_sessions": ("integer", "NO", None),
        "reserved_at": ("timestamp with time zone", "NO", None),
        "expires_at": ("timestamp with time zone", "NO", None),
    }
    columns = {
        name: (data_type, nullable, maximum_length)
        for name, data_type, nullable, maximum_length in db.execute(
            text("""
                SELECT column_name, data_type, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'chat_external_worker_reservations'
                """)
        ).all()
    }
    if columns != expected_columns:
        raise RuntimeError("required external worker schema is missing")

    index_rows = dict(
        db.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'chat_external_worker_reservations'
                """)
        ).all()
    )
    expected_index_names = {
        "chat_external_worker_reservations_pkey",
        "chat_external_worker_reservations_turn_id_key",
        "idx_chat_external_worker_reservations_capacity",
        "idx_chat_external_worker_reservations_unbound_expiry",
    }
    if set(index_rows) != expected_index_names:
        raise RuntimeError("required external worker schema is missing")
    normalized_indexes = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in index_rows.items()
    }
    index_contracts = {
        "chat_external_worker_reservations_pkey": (
            True,
            "(request_id)",
            None,
        ),
        "chat_external_worker_reservations_turn_id_key": (
            True,
            "(turn_id)",
            None,
        ),
        "idx_chat_external_worker_reservations_capacity": (
            False,
            "(worker_id, instance_id, worker_generation)",
            None,
        ),
        "idx_chat_external_worker_reservations_unbound_expiry": (
            False,
            "(expires_at)",
            "where (turn_id is null)",
        ),
    }
    for name, (unique, columns_text, predicate) in index_contracts.items():
        definition = normalized_indexes[name]
        if (
            (definition.startswith("create unique index ") != unique)
            or f" using btree {columns_text}" not in definition
            or (predicate is None and " where " in definition)
            or (predicate is not None and not definition.endswith(predicate))
        ):
            raise RuntimeError("required external worker schema is missing")

    constraint_rows = dict(
        db.execute(
            text("""
                SELECT constraint_row.conname,
                       pg_get_constraintdef(constraint_row.oid, true)
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = 'chat_external_worker_reservations'
                  AND conname IN (
                      'chat_external_worker_reservations_pkey',
                      'chat_external_worker_reservations_turn_id_key',
                      'chat_external_worker_reservations_worker_generation_check',
                      'chat_external_worker_reservations_maximum_sessions_check'
                  )
                """)
        ).all()
    )
    expected_constraint_names = {
        "chat_external_worker_reservations_pkey",
        "chat_external_worker_reservations_turn_id_key",
        "chat_external_worker_reservations_worker_generation_check",
        "chat_external_worker_reservations_maximum_sessions_check",
    }
    if set(constraint_rows) != expected_constraint_names:
        raise RuntimeError("required external worker schema is missing")
    definitions = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in constraint_rows.items()
    }
    generation_check = definitions[
        "chat_external_worker_reservations_worker_generation_check"
    ]
    maximum_check = definitions[
        "chat_external_worker_reservations_maximum_sessions_check"
    ]
    if (
        definitions["chat_external_worker_reservations_pkey"]
        != "primary key (request_id)"
        or definitions["chat_external_worker_reservations_turn_id_key"]
        != "unique (turn_id)"
        or not re.fullmatch(r"check \(\(*worker_generation > 0\)*\)", generation_check)
        or not (
            re.fullmatch(
                r"check \(\(*maximum_sessions between 1 and 32\)*\)", maximum_check
            )
            or re.fullmatch(
                r"check \(\(*maximum_sessions >= 1\)* and "
                r"\(*maximum_sessions <= 32\)*\)",
                maximum_check,
            )
        )
    ):
        raise RuntimeError("required external worker schema is missing")


def validate_qualification_evidence_schema(db) -> None:
    """Require the exact durable qualification storage contract."""
    columns = {
        (table, column): (data_type, nullable, maximum_length, default)
        for table, column, data_type, nullable, maximum_length, default in db.execute(
            text("""
                /* qualification_evidence_exact_columns */
                SELECT table_name, column_name, data_type, is_nullable,
                       character_maximum_length, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN (
                    'chat_qualification_scopes',
                    'chat_qualification_evidence_events',
                    'chat_turn_latency'
                  )
            """)
        ).all()
    }
    required_columns = {
        ("chat_qualification_scopes", "id"): ("uuid", "NO", None, None),
        ("chat_qualification_scopes", "run_id"): ("character varying", "NO", 64, None),
        ("chat_qualification_scopes", "profile"): ("character varying", "NO", 32, None),
        ("chat_qualification_scopes", "app_release_id"): (
            "character varying",
            "NO",
            255,
            None,
        ),
        ("chat_qualification_scopes", "window_started_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_scopes", "window_ended_at"): (
            "timestamp with time zone",
            "YES",
            None,
            None,
        ),
        ("chat_qualification_scopes", "expires_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_scopes", "created_at"): (
            "timestamp with time zone",
            "NO",
            None,
            "now()",
        ),
        ("chat_qualification_evidence_events", "id"): ("uuid", "NO", None, None),
        ("chat_qualification_evidence_events", "qualification_scope_id"): (
            "uuid",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_evidence_events", "turn_id"): ("uuid", "NO", None, None),
        ("chat_qualification_evidence_events", "chat_session_id"): (
            "uuid",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_evidence_events", "event_type"): (
            "character varying",
            "NO",
            32,
            None,
        ),
        ("chat_qualification_evidence_events", "operation_digest"): (
            "character varying",
            "YES",
            64,
            None,
        ),
        ("chat_qualification_evidence_events", "operation_kind"): (
            "character varying",
            "YES",
            8,
            None,
        ),
        ("chat_qualification_evidence_events", "occurred_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_turn_latency", "qualification_run_id"): (
            "character varying",
            "YES",
            64,
            None,
        ),
        ("chat_turn_latency", "qualification_scope_id"): ("uuid", "YES", None, None),
        ("chat_turn_latency", "qualification_profile"): (
            "character varying",
            "YES",
            32,
            None,
        ),
        ("chat_turn_latency", "qualification_workload"): (
            "character varying",
            "YES",
            16,
            None,
        ),
        ("chat_turn_latency", "qualification_scenario"): (
            "character varying",
            "YES",
            32,
            None,
        ),
    }
    contract_columns = {
        key: value
        for key, value in columns.items()
        if key[0]
        in {
            "chat_qualification_scopes",
            "chat_qualification_evidence_events",
        }
        or key[1].startswith("qualification_")
    }
    if contract_columns != required_columns:
        raise RuntimeError("required qualification evidence schema is missing")

    constraints = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in db.execute(
            text("""
                /* qualification_evidence_exact_constraints */
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE connamespace = current_schema()::regnamespace
                  AND (
                    conrelid = 'chat_qualification_scopes'::regclass
                    OR conrelid = 'chat_qualification_evidence_events'::regclass
                    OR (
                      conrelid = 'chat_turn_latency'::regclass
                      AND conname LIKE 'chat_turn_latency_qualification_%'
                    )
                  )
            """)
        ).all()
    }
    required_constraints = {
        "chat_qualification_scopes_pkey": "primary key (id)",
        "chat_qualification_scopes_run_id_key": "unique (run_id)",
        "chat_qualification_scopes_profile_check": "check (((profile)::text = any ((array['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[])))",
        "chat_qualification_scopes_window_check": "check (((window_ended_at is null) or (window_ended_at >= window_started_at)))",
        "chat_qualification_scopes_expiry_check": "check ((expires_at > window_started_at))",
        "chat_qualification_evidence_events_pkey": "primary key (id)",
        "chat_qualification_evidence_scope_fkey": "foreign key (qualification_scope_id) references chat_qualification_scopes(id) on delete cascade",
        "chat_qualification_evidence_turn_fkey": "foreign key (turn_id) references chat_turn_jobs(turn_id) on delete cascade",
        "chat_qualification_evidence_session_fkey": "foreign key (chat_session_id) references chat_sessions(id) on delete cascade",
        "chat_qualification_evidence_event_type_check": "check (((event_type)::text = any ((array['admitted_no_queue'::character varying, 'executor_started'::character varying, 'stale_fence'::character varying, 'queued'::character varying, 'workspace_created'::character varying, 'workspace_reused'::character varying, 'workspace_evicted'::character varying])::text[])))",
        "chat_qualification_evidence_operation_shape_check": "check ((((event_type)::text = 'executor_started'::text) = ((operation_digest is not null) and (operation_kind is not null) and ((operation_kind)::text = any ((array['read'::character varying, 'bash'::character varying])::text[])))))",
        "chat_turn_latency_qualification_scope_fkey": "foreign key (qualification_scope_id) references chat_qualification_scopes(id) on delete set null",
        "chat_turn_latency_qualification_profile_check": "check (((qualification_profile is null) or ((qualification_profile)::text = any ((array['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[]))))",
        "chat_turn_latency_qualification_workload_check": "check (((qualification_workload is null) or ((qualification_workload)::text = any ((array['no_tool'::character varying, 'read'::character varying, 'bash'::character varying])::text[]))))",
        "chat_turn_latency_qualification_scenario_check": "check (((qualification_scenario is null) or ((qualification_scenario)::text = any ((array['focused_latency'::character varying, 'reliability'::character varying, 'clean_cancel'::character varying, 'forced_failure'::character varying])::text[]))))",
    }
    if constraints != required_constraints:
        raise RuntimeError("required qualification evidence schema is missing")

    indexes = {
        name: (unique, list(index_columns), predicate)
        for name, unique, index_columns, predicate in db.execute(
            text("""
                /* qualification_evidence_exact_indexes */
                SELECT index_class.relname,
                       index_meta.indisunique,
                       ARRAY(
                         SELECT attribute.attname
                         FROM unnest(index_meta.indkey) WITH ORDINALITY AS key(attnum, position)
                         JOIN pg_attribute attribute
                           ON attribute.attrelid = table_class.oid
                          AND attribute.attnum = key.attnum
                         ORDER BY key.position
                       ),
                       pg_get_expr(index_meta.indpred, index_meta.indrelid)
                FROM pg_index index_meta
                JOIN pg_class index_class ON index_class.oid = index_meta.indexrelid
                JOIN pg_class table_class ON table_class.oid = index_meta.indrelid
                JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND index_class.relname IN (
                    'idx_chat_qualification_scopes_expiry',
                    'idx_chat_qualification_scopes_release_profile',
                    'idx_chat_qualification_evidence_scope_event_time',
                    'idx_chat_qualification_evidence_session_time',
                    'idx_chat_qualification_evidence_turn_event',
                    'uq_chat_qualification_evidence_stale_turn',
                    'uq_chat_qualification_evidence_eviction_turn',
                    'idx_chat_turn_latency_qualification_scope'
                  )
            """)
        ).all()
    }
    required_indexes = {
        "idx_chat_qualification_scopes_expiry": (False, ["expires_at"], None),
        "idx_chat_qualification_scopes_release_profile": (
            False,
            ["app_release_id", "profile"],
            None,
        ),
        "idx_chat_qualification_evidence_scope_event_time": (
            False,
            ["qualification_scope_id", "event_type", "occurred_at"],
            None,
        ),
        "idx_chat_qualification_evidence_session_time": (
            False,
            ["chat_session_id", "occurred_at"],
            None,
        ),
        "idx_chat_qualification_evidence_turn_event": (
            False,
            ["turn_id", "event_type"],
            None,
        ),
        "uq_chat_qualification_evidence_stale_turn": (
            True,
            ["qualification_scope_id", "turn_id"],
            "((event_type)::text = 'stale_fence'::text)",
        ),
        "uq_chat_qualification_evidence_eviction_turn": (
            True,
            ["qualification_scope_id", "turn_id"],
            "((event_type)::text = 'workspace_evicted'::text)",
        ),
        "idx_chat_turn_latency_qualification_scope": (
            False,
            ["qualification_scope_id", "admitted_at"],
            None,
        ),
    }
    if indexes != required_indexes:
        raise RuntimeError("required qualification evidence schema is missing")


def validate_chat_schema(db, settings: Settings) -> None:
    """Validate only the tables required by the enabled provider profile."""

    if db.execute(text("SHOW transaction_read_only")).scalar_one() != "off":
        raise RuntimeError("chat database connection is read-only")
    common_tables = {
        "chat_sessions",
        "chat_messages",
        "chat_shares",
        "chat_sandbox_leases",
        "chat_sandbox_pool",
        "chat_sandbox_compute_intervals",
        "chat_sandbox_budget_states",
        "chat_sandbox_circuit_events",
        "chat_title_budget_states",
        "chat_title_provider_calls",
        "chat_title_budget_events",
        "chat_turn_capabilities",
        "chat_turn_latency",
        "chat_artifacts",
        "chat_latex_paper_versions",
    }
    pi_tables = {
        "chat_pi_sessions",
        "chat_pi_transcript_entries",
        "chat_pi_prepared_forks",
        "chat_harness_assignment_audit",
    }
    openrouter_tables = {
        "chat_openrouter_credentials",
        "chat_openrouter_monthly_usage",
        "chat_openrouter_provider_calls",
        "chat_openrouter_credential_audit",
    }
    web_search_tables = {
        "chat_web_search_budget_states",
        "chat_web_search_circuit_events",
        "chat_web_search_owner_usage",
    }
    durable_turn_tables = {"chat_turn_jobs", "chat_turn_event_chunks"}
    external_worker_tables = {
        "chat_external_workers",
        "chat_external_worker_reservations",
        "chat_qualification_scopes",
        "chat_qualification_evidence_events",
    }
    required_tables = (
        common_tables
        | (
            openrouter_tables
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_tables if settings.chat_web_search_enabled else set())
        | (pi_tables if settings.chat_pi_runtime_enabled else set())
        | (
            durable_turn_tables
            if settings.chat_durable_turn_dispatch_enabled
            else set()
        )
        | (
            external_worker_tables
            if settings.chat_external_pi_admission_enabled
            else set()
        )
    )
    rows = dict(
        db.execute(
            text("""
                SELECT name, to_regclass(name)::text
                FROM (VALUES
                    ('chat_sessions'),
                    ('chat_messages'),
                    ('chat_shares'),
                    ('chat_sandbox_leases'),
                    ('chat_sandbox_pool'),
                    ('chat_sandbox_compute_intervals'),
                    ('chat_sandbox_budget_states'),
                    ('chat_sandbox_circuit_events'),
                    ('chat_title_budget_states'),
                    ('chat_title_provider_calls'),
                    ('chat_title_budget_events'),
                    ('chat_turn_capabilities'),
                    ('chat_turn_latency'),
                    ('chat_artifacts'),
                    ('chat_latex_paper_versions'),
                    ('chat_openrouter_credentials'),
                    ('chat_openrouter_monthly_usage'),
                    ('chat_openrouter_provider_calls'),
                    ('chat_openrouter_credential_audit')
                    ,('chat_web_search_budget_states')
                    ,('chat_web_search_circuit_events')
                    ,('chat_web_search_owner_usage')
                    ,('chat_pi_sessions')
                    ,('chat_pi_transcript_entries')
                    ,('chat_pi_prepared_forks')
                    ,('chat_harness_assignment_audit')
                    ,('chat_turn_jobs')
                    ,('chat_turn_event_chunks')
                    ,('chat_external_workers')
                    ,('chat_external_worker_reservations')
                    ,('chat_qualification_scopes')
                    ,('chat_qualification_evidence_events')
                ) AS required(name)
                """)
        ).all()
    )
    missing = [name for name in required_tables if rows.get(name) is None]
    common_columns = {
        ("chat_sessions", "execution_backend"),
        ("chat_sessions", "reasoning_effort"),
        ("chat_sessions", "primary_paper_id"),
        ("chat_messages", "finish_reason"),
        ("chat_messages", "reasoning_effort"),
        ("chat_messages", "primary_paper_context"),
        ("chat_messages", "viewer_context"),
        ("chat_messages", "paper_selection"),
        ("chat_messages", "prepared_fork_sdk_session_id"),
        ("chat_messages", "prepared_fork_sdk_project_key"),
        ("chat_messages", "paper_mentions"),
        ("chat_messages", "effective_prompt"),
        ("chat_messages", "langfuse_trace_id"),
        ("chat_shares", "snapshot_version"),
        ("chat_shares", "messages"),
        ("chat_artifacts", "source_head_version_id"),
        ("chat_artifacts", "preview_head_version_id"),
        ("chat_sandbox_leases", "worker_generation"),
        ("chat_sandbox_leases", "egress_policy_digest"),
        ("chat_sandbox_pool", "modal_sandbox_id"),
        ("chat_sandbox_pool", "worker_generation"),
        ("chat_sandbox_pool", "billing_month"),
        ("chat_sandbox_pool", "estimated_blank_cost_usd"),
        ("chat_sandbox_pool", "agent_harness"),
        ("chat_sandbox_pool", "agent_harness_version"),
        ("chat_sandbox_pool", "model_profile"),
        ("chat_sandbox_pool", "reasoning_profile"),
        ("chat_sandbox_pool", "prompt_digest"),
        ("chat_sandbox_pool", "provider_adapter_contract"),
        ("chat_sandbox_pool", "egress_policy_digest"),
        ("chat_sandbox_pool", "provider_create_ms"),
        ("chat_sandbox_pool", "backend_control_connect_ms"),
        ("chat_sandbox_pool", "broker_ready_ms"),
        ("chat_sandbox_pool", "control_ready_ms"),
        ("chat_sandbox_pool", "agent_spawn_ms"),
        ("chat_sandbox_pool", "agent_startup_ready_ms"),
        ("chat_sandbox_pool", "health_check_token_hash"),
        ("chat_sandbox_pool", "health_check_started_at"),
        ("chat_sandbox_compute_intervals", "accrued_microusd"),
        ("chat_sandbox_budget_states", "circuit_state"),
        ("chat_sandbox_budget_states", "provider_floor_microusd"),
        ("chat_sandbox_budget_states", "last_reconciliation_attempt_at"),
        ("chat_sandbox_circuit_events", "fallback_delivery_state"),
        ("chat_sandbox_circuit_events", "fallback_next_delivery_attempt_at"),
        ("chat_title_budget_states", "reserved_microusd"),
        ("chat_title_budget_states", "spent_microusd"),
        ("chat_title_provider_calls", "actual_microusd"),
        ("chat_title_provider_calls", "provider_generation_id"),
        ("chat_title_budget_events", "fallback_delivery_state"),
        ("chat_turn_latency", "request_id"),
        ("chat_turn_latency", "terminal_status"),
        ("chat_turn_latency", "browser_first_visible_delta_ms"),
        ("chat_turn_latency", "browser_first_reasoning_delta_ms"),
        ("chat_turn_latency", "first_semantic_event_ms"),
        ("chat_turn_latency", "pool_miss_reason"),
        ("chat_turn_latency", "session_reuse_cohort"),
        ("chat_turn_latency", "estimated_active_cost_usd"),
        ("chat_turn_latency", "qualification_run_id"),
        ("chat_turn_latency", "qualification_scope_id"),
        ("chat_turn_latency", "qualification_profile"),
        ("chat_turn_latency", "qualification_workload"),
        ("chat_turn_latency", "qualification_scenario"),
        ("chat_turn_latency", "failure_stage"),
        ("chat_turn_latency", "failure_class"),
        ("chat_turn_latency", "attempt_kind"),
        ("chat_turn_latency", "retry_overhead_ms"),
        ("chat_turn_capabilities", "provider_mode"),
        ("chat_turn_capabilities", "provider_credential_revision"),
        ("chat_turn_capabilities", "provider_error_code"),
        ("chat_turn_capabilities", "reasoning_effort"),
    }
    pi_columns = {
        ("chat_sessions", "agent_harness"),
        ("chat_messages", "agent_harness"),
        ("chat_messages", "agent_resume_boundary_id"),
        ("chat_turn_latency", "agent_harness"),
        ("chat_turn_latency", "pi_version"),
        ("chat_turn_latency", "first_semantic_event_class"),
        ("chat_turn_capabilities", "agent_harness"),
    }
    openrouter_columns = {
        ("chat_openrouter_credentials", "credential_revision"),
        ("chat_openrouter_monthly_usage", "reserved_microusd"),
        ("chat_openrouter_provider_calls", "actual_microusd"),
        ("chat_openrouter_provider_calls", "reasoning_effort"),
        ("chat_openrouter_provider_calls", "routing_policy"),
        ("chat_openrouter_provider_calls", "provider_ttft_ms"),
        ("chat_openrouter_provider_calls", "system_token_bucket"),
    }
    web_search_columns = {
        ("chat_sessions", "web_search_enabled"),
        ("chat_messages", "web_search_enabled"),
        ("chat_turn_capabilities", "web_search_calls"),
        ("chat_turn_capabilities", "web_search_failed"),
    }
    hf_catalog_columns = {
        ("chat_turn_capabilities", "hf_catalog_calls"),
        ("chat_turn_capabilities", "hf_recursive_list_calls"),
    }
    durable_turn_columns = {
        ("chat_turn_jobs", "state"),
        ("chat_turn_jobs", "worker_id"),
        ("chat_turn_jobs", "worker_generation"),
        ("chat_turn_jobs", "lease_generation"),
        ("chat_turn_jobs", "lease_expires_at"),
        ("chat_turn_jobs", "terminal_at"),
        ("chat_turn_jobs", "failure_code"),
        ("chat_turn_jobs", "event_sequence"),
        ("chat_turn_jobs", "event_bytes"),
        ("chat_turn_event_chunks", "turn_id"),
        ("chat_turn_event_chunks", "first_sequence"),
        ("chat_turn_event_chunks", "last_sequence"),
        ("chat_turn_event_chunks", "events"),
        ("chat_turn_event_chunks", "payload_bytes"),
    }
    external_worker_columns = {
        ("chat_external_workers", "worker_id"),
        ("chat_external_workers", "instance_id"),
        ("chat_external_workers", "environment"),
        ("chat_external_workers", "release_id"),
        ("chat_external_workers", "contract_version"),
        ("chat_external_workers", "generation"),
        ("chat_external_workers", "state"),
        ("chat_external_workers", "maximum_sessions"),
        ("chat_external_workers", "active_sessions"),
        ("chat_external_workers", "lease_expires_at"),
        ("chat_external_worker_reservations", "request_id"),
        ("chat_external_worker_reservations", "turn_id"),
        ("chat_external_worker_reservations", "endpoint_id"),
        ("chat_external_worker_reservations", "worker_id"),
        ("chat_external_worker_reservations", "instance_id"),
        ("chat_external_worker_reservations", "worker_generation"),
        ("chat_external_worker_reservations", "release_id"),
        ("chat_external_worker_reservations", "contract_version"),
        ("chat_external_worker_reservations", "maximum_sessions"),
        ("chat_external_worker_reservations", "reserved_at"),
        ("chat_external_worker_reservations", "expires_at"),
        ("chat_qualification_evidence_events", "id"),
        ("chat_qualification_evidence_events", "qualification_scope_id"),
        ("chat_qualification_evidence_events", "turn_id"),
        ("chat_qualification_evidence_events", "chat_session_id"),
        ("chat_qualification_evidence_events", "event_type"),
        ("chat_qualification_evidence_events", "operation_digest"),
        ("chat_qualification_evidence_events", "operation_kind"),
        ("chat_qualification_evidence_events", "occurred_at"),
        ("chat_qualification_scopes", "id"),
        ("chat_qualification_scopes", "run_id"),
        ("chat_qualification_scopes", "profile"),
        ("chat_qualification_scopes", "app_release_id"),
        ("chat_qualification_scopes", "window_started_at"),
        ("chat_qualification_scopes", "window_ended_at"),
        ("chat_qualification_scopes", "expires_at"),
        ("chat_turn_latency", "qualification_scope_id"),
        ("chat_turn_latency", "qualification_profile"),
    }
    expected_columns = (
        common_columns
        | (
            openrouter_columns
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_columns if settings.chat_web_search_enabled else set())
        | (hf_catalog_columns if settings.chat_hf_catalog_enabled else set())
        | (pi_columns if settings.chat_pi_runtime_enabled else set())
        | (
            durable_turn_columns
            if settings.chat_durable_turn_dispatch_enabled
            else set()
        )
        | (
            external_worker_columns
            if settings.chat_external_pi_admission_enabled
            else set()
        )
    )
    present_columns = set(
        db.execute(
            text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name, column_name) IN (
                ('chat_sessions', 'execution_backend'),
                ('chat_sessions', 'reasoning_effort'),
                ('chat_sessions', 'primary_paper_id'),
                ('chat_sessions', 'agent_harness'),
                ('chat_messages', 'finish_reason'),
                ('chat_messages', 'reasoning_effort'),
                ('chat_messages', 'primary_paper_context'),
                ('chat_messages', 'viewer_context'),
                ('chat_messages', 'paper_selection'),
                ('chat_messages', 'prepared_fork_sdk_session_id'),
                ('chat_messages', 'prepared_fork_sdk_project_key'),
                ('chat_messages', 'paper_mentions'),
                ('chat_messages', 'effective_prompt'),
                ('chat_messages', 'langfuse_trace_id'),
                ('chat_messages', 'agent_harness'),
                ('chat_messages', 'agent_resume_boundary_id'),
                ('chat_shares', 'snapshot_version'),
                ('chat_shares', 'messages'),
                ('chat_artifacts', 'source_head_version_id'),
                ('chat_artifacts', 'preview_head_version_id'),
                ('chat_sandbox_leases', 'worker_generation'),
                ('chat_sandbox_leases', 'egress_policy_digest'),
                ('chat_sandbox_pool', 'modal_sandbox_id'),
                ('chat_sandbox_pool', 'worker_generation'),
                ('chat_sandbox_pool', 'billing_month'),
                ('chat_sandbox_pool', 'estimated_blank_cost_usd'),
                ('chat_sandbox_pool', 'agent_harness'),
                ('chat_sandbox_pool', 'agent_harness_version'),
                ('chat_sandbox_pool', 'model_profile'),
                ('chat_sandbox_pool', 'reasoning_profile'),
                ('chat_sandbox_pool', 'prompt_digest'),
                ('chat_sandbox_pool', 'provider_adapter_contract'),
                ('chat_sandbox_pool', 'egress_policy_digest'),
                ('chat_sandbox_pool', 'provider_create_ms'),
                ('chat_sandbox_pool', 'backend_control_connect_ms'),
                ('chat_sandbox_pool', 'broker_ready_ms'),
                ('chat_sandbox_pool', 'control_ready_ms'),
                ('chat_sandbox_pool', 'agent_spawn_ms'),
                ('chat_sandbox_pool', 'agent_startup_ready_ms'),
                ('chat_sandbox_pool', 'health_check_token_hash'),
                ('chat_sandbox_pool', 'health_check_started_at'),
                ('chat_sandbox_compute_intervals', 'accrued_microusd'),
                ('chat_sandbox_budget_states', 'circuit_state'),
                ('chat_sandbox_budget_states', 'provider_floor_microusd'),
                ('chat_sandbox_budget_states', 'last_reconciliation_attempt_at'),
                ('chat_sandbox_circuit_events', 'fallback_delivery_state'),
                ('chat_sandbox_circuit_events', 'fallback_next_delivery_attempt_at'),
                ('chat_title_budget_states', 'reserved_microusd'),
                ('chat_title_budget_states', 'spent_microusd'),
                ('chat_title_provider_calls', 'actual_microusd'),
                ('chat_title_provider_calls', 'provider_generation_id'),
                ('chat_title_budget_events', 'fallback_delivery_state'),
                ('chat_turn_latency', 'request_id'),
                ('chat_turn_latency', 'terminal_status'),
                ('chat_turn_latency', 'browser_first_visible_delta_ms'),
                ('chat_turn_latency', 'browser_first_reasoning_delta_ms'),
                ('chat_turn_latency', 'first_semantic_event_ms'),
                ('chat_turn_latency', 'pool_miss_reason'),
                ('chat_turn_latency', 'session_reuse_cohort'),
                ('chat_turn_latency', 'estimated_active_cost_usd'),
                ('chat_turn_latency', 'qualification_run_id'),
                ('chat_turn_latency', 'qualification_scenario'),
                ('chat_turn_latency', 'failure_stage'),
                ('chat_turn_latency', 'failure_class'),
                ('chat_turn_latency', 'attempt_kind'),
                ('chat_turn_latency', 'retry_overhead_ms'),
                ('chat_turn_latency', 'agent_harness'),
                ('chat_turn_latency', 'pi_version'),
                ('chat_turn_latency', 'first_semantic_event_class'),
                ('chat_turn_capabilities', 'provider_mode'),
                ('chat_turn_capabilities', 'provider_credential_revision'),
                ('chat_turn_capabilities', 'provider_error_code'),
                ('chat_turn_capabilities', 'reasoning_effort'),
                ('chat_turn_capabilities', 'agent_harness'),
                ('chat_openrouter_credentials', 'credential_revision'),
                ('chat_openrouter_monthly_usage', 'reserved_microusd'),
                ('chat_openrouter_provider_calls', 'actual_microusd')
                ,('chat_openrouter_provider_calls', 'reasoning_effort')
                ,('chat_openrouter_provider_calls', 'routing_policy')
                ,('chat_openrouter_provider_calls', 'provider_ttft_ms')
                ,('chat_openrouter_provider_calls', 'system_token_bucket')
                ,('chat_sessions', 'web_search_enabled')
                ,('chat_messages', 'web_search_enabled')
                ,('chat_turn_capabilities', 'web_search_calls')
                ,('chat_turn_capabilities', 'web_search_failed')
                ,('chat_turn_capabilities', 'hf_catalog_calls')
                ,('chat_turn_capabilities', 'hf_recursive_list_calls')
                ,('chat_turn_jobs', 'state')
                ,('chat_turn_jobs', 'worker_id')
                ,('chat_turn_jobs', 'worker_generation')
                ,('chat_turn_jobs', 'lease_generation')
                ,('chat_turn_jobs', 'lease_expires_at')
                ,('chat_turn_jobs', 'terminal_at')
                ,('chat_turn_jobs', 'failure_code')
                ,('chat_turn_jobs', 'event_sequence')
                ,('chat_turn_jobs', 'event_bytes')
                ,('chat_turn_event_chunks', 'turn_id')
                ,('chat_turn_event_chunks', 'first_sequence')
                ,('chat_turn_event_chunks', 'last_sequence')
                ,('chat_turn_event_chunks', 'events')
                ,('chat_turn_event_chunks', 'payload_bytes')
                ,('chat_external_workers', 'worker_id')
                ,('chat_external_workers', 'instance_id')
                ,('chat_external_workers', 'environment')
                ,('chat_external_workers', 'release_id')
                ,('chat_external_workers', 'contract_version')
                ,('chat_external_workers', 'generation')
                ,('chat_external_workers', 'state')
                ,('chat_external_workers', 'maximum_sessions')
                ,('chat_external_workers', 'active_sessions')
                ,('chat_external_workers', 'lease_expires_at')
                ,('chat_external_worker_reservations', 'request_id')
                ,('chat_external_worker_reservations', 'turn_id')
                ,('chat_external_worker_reservations', 'endpoint_id')
                ,('chat_external_worker_reservations', 'worker_id')
                ,('chat_external_worker_reservations', 'instance_id')
                ,('chat_external_worker_reservations', 'worker_generation')
                ,('chat_external_worker_reservations', 'release_id')
                ,('chat_external_worker_reservations', 'contract_version')
                ,('chat_external_worker_reservations', 'maximum_sessions')
                ,('chat_external_worker_reservations', 'reserved_at')
                ,('chat_external_worker_reservations', 'expires_at')
                ,('chat_qualification_evidence_events', 'id')
                ,('chat_qualification_evidence_events', 'qualification_scope_id')
                ,('chat_qualification_evidence_events', 'turn_id')
                ,('chat_qualification_evidence_events', 'chat_session_id')
                ,('chat_qualification_evidence_events', 'event_type')
                ,('chat_qualification_evidence_events', 'operation_digest')
                ,('chat_qualification_evidence_events', 'operation_kind')
                ,('chat_qualification_evidence_events', 'occurred_at')
                ,('chat_qualification_scopes', 'id')
                ,('chat_qualification_scopes', 'run_id')
                ,('chat_qualification_scopes', 'profile')
                ,('chat_qualification_scopes', 'app_release_id')
                ,('chat_qualification_scopes', 'window_started_at')
                ,('chat_qualification_scopes', 'window_ended_at')
                ,('chat_qualification_scopes', 'expires_at')
                ,('chat_turn_latency', 'qualification_scope_id')
                ,('chat_turn_latency', 'qualification_profile')
                ,('chat_turn_latency', 'qualification_workload')
            )
            """)
        ).all()
    )
    missing_columns = expected_columns - present_columns
    if settings.chat_external_pi_admission_enabled and (
        "chat_external_worker_reservations" in missing
        or any(
            table == "chat_external_worker_reservations"
            for table, _column in missing_columns
        )
    ):
        raise RuntimeError("required external worker schema is missing")
    if missing or missing_columns:
        raise RuntimeError("required chat sandbox schema is missing")
    if settings.chat_durable_turn_dispatch_enabled:
        durable_contract = set(
            db.execute(
                text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname IN (
                          'idx_chat_turn_jobs_expiry',
                          'idx_chat_turn_jobs_terminal_cleanup',
                          'idx_chat_turn_event_chunks_after',
                          'uq_chat_turn_event_chunk_start'
                      )
                    """)
            ).scalars()
        )
        if durable_contract != {
            "idx_chat_turn_jobs_expiry",
            "idx_chat_turn_jobs_terminal_cleanup",
            "idx_chat_turn_event_chunks_after",
            "uq_chat_turn_event_chunk_start",
        }:
            raise RuntimeError("required durable chat schema is missing")
        durable_constraints = set(
            db.execute(
                text("""
                    SELECT conname
                    FROM pg_constraint
                    WHERE conname IN (
                        'chat_turn_jobs_state_check',
                        'chat_turn_jobs_lease_fields_check',
                        'chat_turn_jobs_terminal_timestamp_check',
                        'ck_chat_turn_event_chunk_range'
                    )
                    """)
            ).scalars()
        )
        if durable_constraints != {
            "chat_turn_jobs_state_check",
            "chat_turn_jobs_lease_fields_check",
            "chat_turn_jobs_terminal_timestamp_check",
            "ck_chat_turn_event_chunk_range",
        }:
            raise RuntimeError("required durable chat schema is missing")
    if settings.chat_external_pi_admission_enabled:
        worker_indexes = set(
            db.execute(
                text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = 'idx_chat_external_workers_dispatch'
                    """)
            ).scalars()
        )
        if worker_indexes != {"idx_chat_external_workers_dispatch"}:
            raise RuntimeError("required external worker schema is missing")
        validate_external_worker_reservation_schema(db)
        validate_qualification_evidence_schema(db)
    share_snapshot_constraint = db.execute(
        text("""
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'chat_shares'::regclass
              AND conname = 'chat_shares_messages_array_check'
            """)
    ).first()
    if share_snapshot_constraint is None:
        raise RuntimeError("required chat sandbox schema is missing")
    artifact_head_constraints = set(
        db.execute(
            text("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'chat_artifacts'::regclass
                  AND confrelid = 'chat_latex_paper_versions'::regclass
                  AND contype = 'f'
                  AND conname IN (
                      'chat_artifacts_source_head_version_fkey',
                      'chat_artifacts_preview_head_version_fkey'
                  )
                """)
        ).all()
    )
    if artifact_head_constraints != {
        ("chat_artifacts_source_head_version_fkey",),
        ("chat_artifacts_preview_head_version_fkey",),
    }:
        raise RuntimeError("required chat sandbox schema is missing")
