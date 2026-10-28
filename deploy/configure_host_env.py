#!/usr/bin/env python3
"""Create the two deployed app environments and the CRON credential overlay."""

from __future__ import annotations

import argparse
import ast
import base64
import grp
import hashlib
import json
import os
import re
import secrets
import tempfile
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

try:
    from backend.operator_profile import OPERATOR
except ModuleNotFoundError:
    # Run from a checkout as `python deploy/configure_host_env.py`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.operator_profile import OPERATOR
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CONFIG_ROOT = Path("/etc/paperswithcode")
APP_ROOT = Path("/srv/paperswithcode")
PRODUCTION_CHAT_SEALED_CONFIG = CONFIG_ROOT / "production-chat-prepared.env"
# Operator profile for paperswithcode.co. The backend only requires these to be
# set; a self-hosted deployment changes them here, not in validation code.
STAGING_CHAT_ARTIFACT_BUCKET_ID = OPERATOR.chat_artifact_bucket
CHAT_TITLE_CREDENTIAL_OWNER = OPERATOR.chat_title_credential_owner
STAGING_CHAT_MODAL_WORKSPACE = OPERATOR.modal_staging_workspace
STAGING_CHAT_MODAL_OWNER_USERNAME = OPERATOR.modal_staging_owner_username

STAGING_EXCLUDED_PREFIXES = (
    "PWC_POSTGRES_BACKUP_",
    "PWC_GITHUB_",
    "GITHUB_",
)
STAGING_EXCLUDED_KEYS = {
    "ARTIFICIAL_ANALYSIS_API_KEY",
    "EXA_API_KEY",
    "OPENAI_API_KEY",
    "PWC_ADMIN_API_TOKEN",
    "PWC_DATALAB_API_KEY",
    "PWC_GEMINI_API_KEY",
    "PWC_OPENAI_API_KEY",
    "PWC_OPENROUTER_API_KEY",
}
CRON_ONLY_KEYS = {
    "PWC_AUTONOMOUS_ALERT_FALLBACK_WEBHOOK_URL",
    "PWC_AUTONOMOUS_ALERT_SLACK_WEBHOOK_URL",
    "PWC_AUTONOMOUS_CODEX_API_KEY",
    "PWC_AUTONOMOUS_CODEX_BROKER_TOKEN",
    "PWC_AUTONOMOUS_DIGEST_WEBHOOK_URL",
    "PWC_AUTONOMOUS_CODEX_RESERVATION_VERIFY_KEY",
    "PWC_AUTONOMOUS_SUBMISSION_HF_TOKEN",
    "PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED",
    "PWC_AUTONOMOUS_SUBMISSION_OPENAI_API_KEY",
    "PWC_CHAT_SYNTHETIC_EXPECTED_USERNAME",
    "PWC_CHAT_SYNTHETIC_SESSION_COOKIE",
    "PWC_CHAT_LANGFUSE_TRACE_CONTENT_ACCESS_ENABLED",
    "PWC_CONFERENCE_DEADLINES_ANTHROPIC_API_KEY",
    "PWC_CONFERENCE_DEADLINES_HF_TOKEN",
    "PWC_GITHUB_TOKEN_HOT",
    "PWC_SEMANTIC_SCHOLAR_API_KEY_2",
    "PWC_X_THREAD_DISCOVERY_APPLY",
    "X_API_BEARER_TOKEN",
    "PWC_X_POST_MAX_CHARS",
    "X_POST_ACCESS_TOKEN",
    "X_POST_ACCESS_TOKEN_SECRET",
    "X_POST_CONSUMER_KEY",
    "X_POST_CONSUMER_SECRET",
}
STAGING_RUNTIME_PASSTHROUGH_KEYS = {
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "MODAL_ENVIRONMENT",
    "PWC_CHAT_DEFAULT_BACKEND",
    "PWC_CHAT_LANGFUSE_ENABLED",
    "PWC_CHAT_TRACKIO_ENABLED",
    "PWC_CHAT_TRACKIO_URL",
    "PWC_CHAT_TRACKIO_PROJECT",
    "PWC_CHAT_TRACKIO_HF_TOKEN",
    "PWC_CHAT_MAX_CONCURRENCY",
    "PWC_CHAT_ALTERNATIVE_MODEL",
    "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED",
    "PWC_CHAT_BLANK_POOL_ENABLED",
    "PWC_CHAT_BLANK_POOL_MAX",
    "PWC_CHAT_BLANK_POOL_MIN",
    "PWC_CHAT_BLANK_POOL_MIN_REMAINING_SECONDS",
    "PWC_CHAT_BLANK_POOL_MONTHLY_BUDGET_USD",
    "PWC_CHAT_BLANK_POOL_REFILL_CONCURRENCY",
    "PWC_CHAT_BLANK_POOL_REPORTED_MONTH_TO_DATE_USD",
    "PWC_CHAT_BLANK_POOL_ROTATE_BEFORE_SECONDS",
    "PWC_CHAT_CANCEL_GRACE_SECONDS",
    "PWC_CHAT_MODAL_IMAGE_VERSION",
    "PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE",
    "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION",
    "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING",
    "PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD",
    "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED",
    "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET",
    "PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD",
    "PWC_CHAT_OPENAI_DIRECT_ENABLED",
    "PWC_OPENAI_API_KEY",
    "PWC_CHAT_PERSISTENT_SANDBOX_LIFETIME_SECONDS",
    "PWC_CHAT_PERSISTENT_WORKER_ENABLED",
    "PWC_CHAT_PI_PREWARM_ENABLED",
    "PWC_CHAT_PI_PREWARM_MODEL",
    "PWC_CHAT_PI_PREWARM_REASONING_EFFORT",
    "PWC_CHAT_PWC_CLI_VERSION",
    "PWC_CHAT_SANDBOX_CPU",
    "PWC_CHAT_SANDBOX_CPU_LIMIT",
    "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB",
    "PWC_CHAT_SANDBOX_MEMORY_MIB",
    "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP",
    "PWC_CHAT_SANDBOX_WARNING_MICROUSD",
    "PWC_CHAT_SCOPE_GUARDRAIL_ENABLED",
    "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN",
    "PWC_CHAT_SCOPE_GUARDRAIL_HF_BILL_TO",
    "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY",
    "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED",
    "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD",
    "PWC_CHAT_SANDBOX_PROVIDER_MODE",
    "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
    "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT",
    "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
    "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
    "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS",
    "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS",
    "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS",
    "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD",
    "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS",
    "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS",
    "PWC_CHAT_SANDBOX_PROVIDER_FLOOR_MICROUSD",
    "PWC_CHAT_SANDBOX_PROVIDER_REPORTED_AT",
    "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
    "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
    "PWC_CHAT_SANDBOX_RUNBOOK_URL",
    "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
    "PWC_CHAT_SYSTEM_PROMPT_SHA256",
    "PWC_CHAT_TITLE_BILL_TO",
    "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
    "PWC_CHAT_TITLE_GENERATION_ENABLED",
    "PWC_CHAT_TITLE_HF_TOKEN",
    "PWC_CHAT_TITLE_MAX_CALL_MICROUSD",
    "PWC_CHAT_TITLE_MAX_TOKENS",
    "PWC_CHAT_TITLE_MODEL",
    "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD",
    "PWC_CHAT_TITLE_PROVIDER",
    "PWC_CHAT_TITLE_WARNING_MICROUSD",
    "PWC_CHAT_WORKER_CONTRACT_VERSION",
    "PWC_CHAT_WORKER_READY_TIMEOUT_SECONDS",
    "PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED",
    "PWC_CHAT_WEB_SEARCH_ENABLED",
    "PWC_CHAT_WEB_SEARCH_PROVIDER",
    "PWC_CHAT_WEB_SEARCH_EXA_API_KEY",
    "PWC_CHAT_WEB_SEARCH_EXA_URL",
    "PWC_CHAT_WEB_SEARCH_MAX_CALLS",
    "PWC_CHAT_WEB_SEARCH_TIMEOUT_SECONDS",
    "PWC_CHAT_WEB_SEARCH_RESULT_COUNT",
    "PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES",
    "PWC_CHAT_WEB_SEARCH_QUERY_MAX_CHARS",
    "PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS",
    "PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS",
    "PWC_CHAT_WEB_SEARCH_TRANSIENT_COOLDOWN_SECONDS",
    "PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST",
}

STAGING_LANGFUSE_KEYS = {
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}
PRODUCTION_LANGFUSE_KEYS = STAGING_LANGFUSE_KEYS


def read_lines(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0]
        if key.replace("_", "").isalnum() and not key[0].isdigit():
            result[key] = line
    return result


def decoded_value(line: str) -> str:
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return str(ast.literal_eval(value))
    return value


def existing_or_random(lines: dict[str, str], key: str) -> str:
    line = lines.get(key)
    return decoded_value(line) if line else secrets.token_urlsafe(48)


def trending_cron_values(
    legacy: dict[str, str],
    current: dict[str, str],
    *,
    password: str,
) -> dict[str, str]:
    """Build the persistent minimal environment for isolated scoring jobs."""
    return {
        "PWC_DB_HOST": decoded_value(legacy["PWC_DB_HOST"]),
        "PWC_DB_NAME": decoded_value(legacy["PWC_DB_NAME"]),
        "PWC_DB_PORT": decoded_value(legacy["PWC_DB_PORT"]),
        "PWC_TRENDING_DB_PASSWORD": password,
        **{
            key: decoded_value(line)
            for key, line in current.items()
            if key.startswith("PWC_TRENDING_PIN_")
        },
    }


def shared_role_values(*sources: dict[str, str]) -> dict[str, str]:
    """Preserve one identical subject allowlist across both environments."""

    result: dict[str, str] = {}
    for key in ("PWC_ADMIN_HF_SUBJECTS", "PWC_CONTRIBUTOR_HF_SUBJECTS"):
        configured = {decoded_value(source[key]) for source in sources if key in source}
        if len(configured) > 1:
            raise ValueError(f"{key} differs between protected environments")
        result[key] = next(iter(configured), "")
    return result


def shared_session_keys(
    production: dict[str, str], staging: dict[str, str]
) -> tuple[str, str]:
    private_line = production.get("PWC_SESSION_SIGNING_PRIVATE_KEY")
    public_line = production.get("PWC_SESSION_VERIFICATION_PUBLIC_KEY")
    staging_public_line = staging.get("PWC_SESSION_VERIFICATION_PUBLIC_KEY")
    if private_line:
        private_value = decoded_value(private_line)
        private_bytes = base64.urlsafe_b64decode(
            private_value + "=" * (-len(private_value) % 4)
        )
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    else:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        private_value = base64.urlsafe_b64encode(private_bytes).rstrip(b"=").decode()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_value = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    for line in (public_line, staging_public_line):
        if line and decoded_value(line) != public_value:
            raise ValueError("configured shared-session public key does not match")
    return private_value, public_value


def shared_oauth_credential_secret(
    production: dict[str, str], staging: dict[str, str]
) -> str:
    """Preserve one credential-encryption secret across both environments."""

    key = "PWC_HF_OAUTH_CREDENTIAL_SECRET"
    configured = {
        decoded_value(source[key]) for source in (production, staging) if key in source
    }
    if len(configured) > 1:
        raise ValueError(f"{key} differs between protected environments")
    return next(iter(configured), secrets.token_urlsafe(48))


def assign(lines: dict[str, str], values: dict[str, str]) -> dict[str, str]:
    updated = dict(lines)
    updated.update({key: f"{key}={value}" for key, value in values.items()})
    return updated


def without_cron_only_credentials(lines: dict[str, str]) -> dict[str, str]:
    """Keep workload-owned credentials out of application environments."""
    return {key: line for key, line in lines.items() if key not in CRON_ONLY_KEYS}


def staging_runtime_passthrough(lines: dict[str, str]) -> dict[str, str]:
    """Preserve provisioned staging chat credentials and immutable pins."""
    return {
        key: line
        for key, line in lines.items()
        if key in STAGING_RUNTIME_PASSTHROUGH_KEYS
    }


def staging_langfuse_values(legacy: dict[str, str]) -> dict[str, str]:
    missing = sorted(STAGING_LANGFUSE_KEYS - legacy.keys())
    if missing:
        raise ValueError("legacy environment is missing: " + ", ".join(missing))
    return {
        **{key: decoded_value(legacy[key]) for key in STAGING_LANGFUSE_KEYS},
        "PWC_CHAT_LANGFUSE_ENABLED": "true",
    }


def production_langfuse_values(
    source: dict[str, str], current_staging: dict[str, str]
) -> dict[str, str]:
    """Install one non-staging project key into production tracing only."""

    missing = sorted(PRODUCTION_LANGFUSE_KEYS - source.keys())
    if missing:
        raise ValueError("production environment is missing: " + ", ".join(missing))
    values = {
        key: decoded_value(source[key]).strip() for key in PRODUCTION_LANGFUSE_KEYS
    }
    empty = sorted(key for key, value in values.items() if not value)
    if empty:
        raise ValueError("production environment is empty: " + ", ".join(empty))
    parsed = urlsplit(values["LANGFUSE_BASE_URL"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("LANGFUSE_BASE_URL must be an HTTPS URL")
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        staging_line = current_staging.get(key)
        if staging_line and decoded_value(staging_line) == values[key]:
            raise ValueError(f"production {key} must not reuse the staging key")
    return {**values, "PWC_CHAT_LANGFUSE_ENABLED": "true"}


def staging_openrouter_accounting_values(current: dict[str, str]) -> dict[str, str]:
    """Preserve or generate the durable, non-provider staging secrets."""

    keyring_line = current.get("PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING")
    if keyring_line and decoded_value(keyring_line).strip():
        keyring = decoded_value(keyring_line)
    else:
        encryption_key = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        )
        keyring = json.dumps({"1": encryption_key}, separators=(",", ":"))
    tracking_line = current.get("PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET")
    tracking_secret = (
        decoded_value(tracking_line).strip() if tracking_line else ""
    ) or secrets.token_urlsafe(48)
    active_line = current.get("PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION")
    active_version = (decoded_value(active_line).strip() if active_line else "") or "1"
    return {
        "PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD": "1.00",
        "PWC_CHAT_OPENROUTER_WORKSPACE_MONTHLY_BUDGET_USD": "200.00",
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": keyring,
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": active_version,
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": tracking_secret,
    }


def rotate_staging_openrouter_secret_values(
    current: dict[str, str],
) -> dict[str, str]:
    """Add a new active AES key while retaining versions needed for decrypt."""

    line = current.get("PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING")
    if not line:
        raise ValueError("staging OpenRouter credential keyring is not configured")
    try:
        parsed = json.loads(decoded_value(line))
        keyring = {str(int(version)): str(value) for version, value in parsed.items()}
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("staging OpenRouter credential keyring is invalid") from error
    if not keyring:
        raise ValueError("staging OpenRouter credential keyring is empty")
    next_version = max(int(version) for version in keyring) + 1
    keyring[str(next_version)] = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    )
    return {
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING": json.dumps(
            keyring, separators=(",", ":")
        ),
        "PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION": str(next_version),
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET": secrets.token_urlsafe(48),
    }


def staging_openrouter_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "PWC_OPENROUTER_API_KEY"
    if key not in legacy:
        raise ValueError(f"legacy environment is missing: {key}")
    current = read_lines(CONFIG_ROOT / "staging.env")
    return {
        **staging_openrouter_accounting_values(current),
        "PWC_CHAT_OPENROUTER_API_KEY": decoded_value(legacy[key]),
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "true",
    }


def staging_openai_direct_values(
    source: dict[str, str], production: dict[str, str]
) -> dict[str, str]:
    """Install one isolated staging Responses credential and rollout profile."""

    key = "OPENAI_API_KEY"
    if key not in source or not decoded_value(source[key]).strip():
        raise ValueError(f"staging OpenAI source is missing: {key}")
    credential = decoded_value(source[key]).strip()
    production_lines = (
        production.get("PWC_OPENAI_API_KEY"),
        production.get("OPENAI_API_KEY"),
    )
    if any(
        line and decoded_value(line).strip() == credential for line in production_lines
    ):
        raise ValueError("staging OpenAI credential must not reuse production")
    return {
        "PWC_OPENAI_API_KEY": credential,
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_MODEL": "gpt-5.6-luna@openai",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
    }


def staging_openai_direct_disable_values() -> dict[str, str]:
    """Restore the historical staging OpenRouter Luna prewarm on rollback."""

    return {
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "false",
        "PWC_CHAT_PI_PREWARM_MODEL": "openai/gpt-5.6-luna",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
    }


def staging_scope_guardrail_values(current: dict[str, str]) -> dict[str, str]:
    """Install server-owned scope credentials without exposing user tokens."""

    required = (
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_HF_BILL_TO",
        "PWC_CODEX_JOBS_OPENAI_API_KEY",
    )
    values = {
        key: decoded_value(current[key]).strip()
        for key in required
        if key in current and decoded_value(current[key]).strip()
    }
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(
            "staging scope guardrail source is missing: " + ", ".join(missing)
        )
    for dedicated, general in (
        ("PWC_CHAT_TITLE_HF_TOKEN", "PWC_HF_TOKEN"),
        ("PWC_CODEX_JOBS_OPENAI_API_KEY", "PWC_OPENAI_API_KEY"),
    ):
        if (
            general in current
            and decoded_value(current[general]).strip() == values[dedicated]
        ):
            raise ValueError(
                f"staging scope guardrail credential must not reuse {general}"
            )
    return {
        "PWC_CHAT_SCOPE_GUARDRAIL_ENABLED": "true",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN": values["PWC_CHAT_TITLE_HF_TOKEN"],
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_BILL_TO": values["PWC_CHAT_HF_BILL_TO"],
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY": values[
            "PWC_CODEX_JOBS_OPENAI_API_KEY"
        ],
        "PWC_CHAT_ARTIFACT_STORAGE_BACKEND": "hf_bucket",
        "PWC_CHAT_ARTIFACT_HF_BUCKET_ID": STAGING_CHAT_ARTIFACT_BUCKET_ID,
        "PWC_CHAT_POSTERLY_ENABLED": "false",
    }


def scope_title_hf_values(
    source: dict[str, str],
    current: dict[str, str],
    other_environment: dict[str, str],
    *,
    environment: str,
) -> dict[str, str]:
    """Build one environment-isolated HF title and scope policy."""

    if environment not in {"staging", "production"}:
        raise ValueError("scope/title environment must be staging or production")
    required_source = (
        "PWC_CHAT_TITLE_GENERATION_ENABLED",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TITLE_BILL_TO",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    )
    source_values = {
        key: decoded_value(source[key]).strip()
        for key in required_source
        if key in source and decoded_value(source[key]).strip()
    }
    missing = [key for key in required_source if key not in source_values]
    if missing:
        raise ValueError("scope/title source is missing: " + ", ".join(missing))
    expected = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": CHAT_TITLE_CREDENTIAL_OWNER,
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": environment,
    }
    for key, value in expected.items():
        if source_values[key] != value:
            raise ValueError(f"{key} must be {value}")

    token = source_values["PWC_CHAT_TITLE_HF_TOKEN"]
    forbidden_hf_tokens = {
        decoded_value(lines[key]).strip()
        for lines, key in (
            (source, "PWC_HF_TOKEN"),
            (current, "PWC_HF_TOKEN"),
            (other_environment, "PWC_HF_TOKEN"),
            (other_environment, "PWC_CHAT_TITLE_HF_TOKEN"),
            (other_environment, "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN"),
        )
        if key in lines and decoded_value(lines[key]).strip()
    }
    if token in forbidden_hf_tokens:
        raise ValueError(
            "the title token must remain distinct from general and other-environment tokens"
        )

    fallback_line = current.get("PWC_CODEX_JOBS_OPENAI_API_KEY")
    fallback = decoded_value(fallback_line).strip() if fallback_line else ""
    if not fallback:
        raise ValueError("PWC_CODEX_JOBS_OPENAI_API_KEY must be configured")
    bill_to = source_values["PWC_CHAT_TITLE_BILL_TO"]
    values = {
        **source_values,
        "PWC_CHAT_TITLE_MODEL": "zai-org/GLM-5.3-Flash:baseten",
        "PWC_CHAT_TITLE_PROVIDER": "huggingface",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
        "PWC_CHAT_SCOPE_GUARDRAIL_ENABLED": "true",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN": token,
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_BILL_TO": bill_to,
        "PWC_CHAT_SCOPE_GUARDRAIL_GLM_MODEL": ("zai-org/GLM-5.3-Flash:baseten"),
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY": fallback,
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_MODEL": "gpt-5.6-luna",
        "PWC_CHAT_POSTERLY_ENABLED": "false",
    }
    if environment == "staging":
        values.update(
            {
                "PWC_CHAT_ARTIFACT_STORAGE_BACKEND": "hf_bucket",
                "PWC_CHAT_ARTIFACT_HF_BUCKET_ID": STAGING_CHAT_ARTIFACT_BUCKET_ID,
            }
        )
    return values


def production_openai_direct_values(current: dict[str, str]) -> dict[str, str]:
    """Promote the existing protected production key and Luna warm profile."""

    required = {
        "PWC_CHAT_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": "true",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "true",
    }
    missing = [
        key
        for key, expected in required.items()
        if _decoded_flag(current, key) != expected
    ]
    if missing:
        raise ValueError(
            "production direct OpenAI requires admitted chat infrastructure: "
            + ", ".join(missing)
        )
    credential_line = current.get("PWC_OPENAI_API_KEY") or current.get("OPENAI_API_KEY")
    if not credential_line or not decoded_value(credential_line).strip():
        raise ValueError("production OpenAI credential is missing")
    return {
        "PWC_OPENAI_API_KEY": decoded_value(credential_line).strip(),
        "PWC_CHAT_OPENAI_DIRECT_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_ENABLED": "true",
        "PWC_CHAT_PI_PREWARM_MODEL": "gpt-5.6-luna@openai",
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
        "PWC_CHAT_BLANK_POOL_ENABLED": "true",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
    }


def production_excalidraw_values(
    current: dict[str, str], *, enabled: bool
) -> dict[str, str]:
    """Toggle only the reviewed production Excalidraw worker and App host."""

    if enabled:
        required = {
            "PWC_CHAT_ENABLED": "true",
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED": "true",
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "true",
        }
        missing = [
            key
            for key, expected in required.items()
            if _decoded_flag(current, key) != expected
        ]
        if missing:
            raise ValueError(
                "production Excalidraw requires admitted chat infrastructure: "
                + ", ".join(missing)
            )
    value = "true" if enabled else "false"
    return {
        "PWC_CHAT_EXCALIDRAW_ENABLED": value,
        "PWC_CHAT_MCP_APPS_HOST_ENABLED": value,
    }


def staging_web_search_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "EXA_API_KEY"
    if key not in legacy or not decoded_value(legacy[key]).strip():
        raise ValueError(f"legacy environment is missing: {key}")
    return {
        "PWC_CHAT_WEB_SEARCH_ENABLED": "true",
        "PWC_CHAT_WEB_SEARCH_PROVIDER": "exa",
        "PWC_CHAT_WEB_SEARCH_EXA_API_KEY": decoded_value(legacy[key]).strip(),
        "PWC_CHAT_WEB_SEARCH_EXA_URL": "https://api.exa.ai/search",
        "PWC_CHAT_WEB_SEARCH_MAX_CALLS": "3",
        "PWC_CHAT_WEB_SEARCH_TIMEOUT_SECONDS": "3",
        "PWC_CHAT_WEB_SEARCH_RESULT_COUNT": "5",
        "PWC_CHAT_WEB_SEARCH_MAX_RESULT_BYTES": "16384",
        "PWC_CHAT_WEB_SEARCH_QUERY_MAX_CHARS": "500",
        "PWC_CHAT_WEB_SEARCH_MONTHLY_WARNING_CALLS": "5000",
        "PWC_CHAT_WEB_SEARCH_MONTHLY_HARD_CALLS": "6000",
        "PWC_CHAT_WEB_SEARCH_TRANSIENT_COOLDOWN_SECONDS": "60",
        "PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST": "",
    }


def production_web_search_values(legacy: dict[str, str]) -> dict[str, str]:
    """Build production chat web-search settings from its server-owned key."""

    return staging_web_search_values(legacy)


def staging_github_values(legacy: dict[str, str]) -> dict[str, str]:
    key = "PWC_GITHUB_TOKEN"
    if key not in legacy or not decoded_value(legacy[key]).strip():
        raise ValueError(f"legacy environment is missing: {key}")
    return {key: decoded_value(legacy[key]).strip()}


def production_cron_github_values(source: dict[str, str]) -> dict[str, str]:
    """Return the single validated credential allowed by the narrow rotation."""
    return staging_github_values(source)


def staging_title_values(
    source: dict[str, str],
    current_staging: dict[str, str],
    current_production: dict[str, str],
) -> dict[str, str]:
    """Validate and isolate the staging-only server-funded title credential."""

    required = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TITLE_BILL_TO",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError("title environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in required}
    expected = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": CHAT_TITLE_CREDENTIAL_OWNER,
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "staging",
    }
    for key, value in expected.items():
        if values[key] != value:
            raise ValueError(f"{key} must be {value}")
    token = values["PWC_CHAT_TITLE_HF_TOKEN"]
    if not token:
        raise ValueError("PWC_CHAT_TITLE_HF_TOKEN must be non-empty")
    forbidden_tokens = {
        decoded_value(lines[key])
        for lines, key in (
            (source, "PWC_HF_TOKEN"),
            (current_staging, "PWC_HF_TOKEN"),
            (current_production, "PWC_CHAT_TITLE_HF_TOKEN"),
        )
        if key in lines and decoded_value(lines[key])
    }
    if token in forbidden_tokens:
        raise ValueError(
            "the staging title token must be distinct from general and production tokens"
        )
    return {
        **values,
        "PWC_CHAT_TITLE_MODEL": "zai-org/GLM-5.3-Flash:baseten",
        "PWC_CHAT_TITLE_PROVIDER": "huggingface",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }


def production_title_values(
    source: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Validate the isolated production HF title policy."""

    required = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TITLE_BILL_TO",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER",
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError("title environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in required}
    expected = {
        "PWC_CHAT_TITLE_GENERATION_ENABLED": "true",
        "PWC_CHAT_TITLE_BILL_TO": "huggingface",
        "PWC_CHAT_TITLE_CREDENTIAL_OWNER": CHAT_TITLE_CREDENTIAL_OWNER,
        "PWC_CHAT_TITLE_CREDENTIAL_ENVIRONMENT": "production",
    }
    for key, value in expected.items():
        if values[key] != value:
            raise ValueError(f"{key} must be {value}")
    token = values["PWC_CHAT_TITLE_HF_TOKEN"]
    forbidden_tokens = {
        decoded_value(lines[key]).strip()
        for lines, key in (
            (source, "PWC_HF_TOKEN"),
            (current_production, "PWC_HF_TOKEN"),
            (current_staging, "PWC_HF_TOKEN"),
            (current_staging, "PWC_CHAT_TITLE_HF_TOKEN"),
            (current_staging, "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN"),
        )
        if key in lines and decoded_value(lines[key]).strip()
    }
    if token in forbidden_tokens:
        raise ValueError(
            "the production title token must be distinct from general and staging tokens"
        )
    return {
        **values,
        "PWC_CHAT_TITLE_MODEL": "zai-org/GLM-5.3-Flash:baseten",
        "PWC_CHAT_TITLE_PROVIDER": "huggingface",
        "PWC_CHAT_TITLE_MAX_TOKENS": "64",
        "PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD": "25000000",
        "PWC_CHAT_TITLE_WARNING_MICROUSD": "20000000",
        "PWC_CHAT_TITLE_MAX_CALL_MICROUSD": "10000",
    }


def production_openrouter_values(
    source: dict[str, str], current_staging: dict[str, str]
) -> dict[str, str]:
    """Build an isolated production OpenRouter preparation contract."""

    key_name = "PWC_CHAT_OPENROUTER_API_KEY"
    provider_line = source.get(key_name)
    provider_key = decoded_value(provider_line).strip() if provider_line else ""
    if not provider_key:
        raise ValueError(f"{key_name} must be non-empty")
    staging_line = current_staging.get(key_name)
    staging_key = decoded_value(staging_line).strip() if staging_line else ""
    if staging_key and provider_key == staging_key:
        raise ValueError("production must not reuse the staging OpenRouter key")
    values = staging_openrouter_accounting_values(source)
    values["PWC_CHAT_OPENROUTER_MONTHLY_USER_BUDGET_USD"] = "5.00"
    try:
        keyring = json.loads(values["PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING"])
        active_version = str(
            int(values["PWC_CHAT_OPENROUTER_CREDENTIAL_ACTIVE_KEY_VERSION"])
        )
        encoded_key = keyring[active_version]
        decoded_key = base64.urlsafe_b64decode(
            encoded_key + "=" * (-len(encoded_key) % 4)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(
            "production OpenRouter credential keyring is invalid"
        ) from error
    if len(decoded_key) != 32:
        raise ValueError("production OpenRouter credential key must be 32 bytes")
    return {
        **values,
        key_name: provider_key,
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "false",
    }


def without_staging_openrouter(lines: dict[str, str]) -> dict[str, str]:
    """Remove shared-provider credentials and explicitly keep the preview off."""
    updated = dict(lines)
    updated.pop("PWC_CHAT_OPENROUTER_API_KEY", None)
    return assign(
        updated,
        {"PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "false"},
    )


def cron_passthrough_credentials(
    legacy: dict[str, str], current_cron: dict[str, str]
) -> dict[str, str]:
    """Build the preserved credential subset for the production CRON overlay."""
    result = {
        key: line
        for key, line in legacy.items()
        if key.startswith(("PWC_POSTGRES_BACKUP_", "PWC_GITHUB_HOT_", "GITHUB_"))
        or key == "PWC_GITHUB_RATE_LIMIT_RESERVE"
        or key
        in {
            "PWC_GITHUB_TOKEN",
            "PWC_GITHUB_TOKEN_HOT",
            "PWC_SEMANTIC_SCHOLAR_API_KEY_2",
        }
    }
    for key in CRON_ONLY_KEYS:
        if key in legacy:
            result[key] = legacy[key]
        elif key in current_cron:
            result[key] = current_cron[key]
    secondary_key = "PWC_SEMANTIC_SCHOLAR_API_KEY_2"
    if secondary_key not in result and secondary_key in current_cron:
        result[secondary_key] = current_cron[secondary_key]
    return result


def write_env(path: Path, lines: dict[str, str], group: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Identities need search permission to reach their own group-readable file,
    # but must not be able to list the other environment filenames.
    path.parent.chmod(0o711)
    # mkstemp creates the file 0600, so the secrets are never readable by other
    # local identities while they are being written.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines[key] for key in sorted(lines)) + "\n")
        os.chown(temporary, 0, grp.getgrnam(group).gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_active_staging_release(app_root: Path, release_id: str) -> None:
    """Require one exact active immutable staging release and manifest identity."""

    if re.fullmatch(r"[0-9a-f]{12}-staging", release_id) is None:
        raise ValueError("active immutable staging release is invalid")
    current = app_root / "environments" / "staging" / "current"
    if not current.is_symlink():
        raise ValueError("active immutable staging release is required")
    try:
        release = current.resolve(strict=True)
        manifest_path = release / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("active immutable staging release is required") from None
    sha = manifest.get("git_sha") if isinstance(manifest, dict) else None
    if (
        release.parent != app_root / "releases"
        or release.name != release_id
        or not isinstance(manifest, dict)
        or manifest.get("release_id") != release_id
        or not isinstance(sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or release_id != f"{sha[:12]}-staging"
    ):
        raise ValueError("active immutable staging release is required")


def staging_modal_rate_evidence(
    *, app_root: Path, release_id: str, microusd_per_second: int
) -> dict[str, str]:
    """Build explicit release-bound Modal rate evidence with no fallback."""

    validate_active_staging_release(app_root, release_id)
    if (
        type(microusd_per_second) is not int
        or not 1 <= microusd_per_second <= 1_000_000
    ):
        raise ValueError("staging Modal rate must be an explicit bounded integer")
    return {
        "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": str(microusd_per_second),
        "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
        "PWC_RELEASE_ID": release_id,
    }


def write_staging_modal_rate_evidence(path: Path, values: dict[str, str]) -> None:
    """Atomically install the fixed root-only Modal rate evidence contract."""

    expected_keys = {
        "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND",
        "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID",
        "PWC_RELEASE_ID",
    }
    if set(values) != expected_keys:
        raise ValueError("staging Modal rate evidence keys are invalid")
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")) + "\n"
    if len(payload.encode("utf-8")) > 4_096:
        raise ValueError("staging Modal rate evidence is too large")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o711)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    descriptor = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temporary, 0, 0)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def remove_staging_modal_rate_evidence(path: Path, expected_release_id: str) -> None:
    """Remove only the exact protected evidence for the active staging release."""

    try:
        metadata = path.lstat()
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError(
            "protected staging Modal rate evidence is unavailable"
        ) from None
    try:
        rate = int(values.get("PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND", ""))
    except (AttributeError, TypeError, ValueError):
        rate = 0
    if (
        not path.is_file()
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_mode & 0o777 != 0o600
        or metadata.st_size > 4_096
        or not isinstance(values, dict)
        or set(values)
        != {
            "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND",
            "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID",
            "PWC_RELEASE_ID",
        }
        or values.get("PWC_RELEASE_ID") != expected_release_id
        or values.get("PWC_MODAL_EXECUTOR_RATE_SOURCE_ID") != "modal-staging-price-v1"
        or not 1 <= rate <= 1_000_000
        or values.get("PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND") != str(rate)
    ):
        raise ValueError("protected staging Modal rate evidence does not match")
    path.unlink()


def staging_chat_capacity_values() -> dict[str, str]:
    """Qualified staging shape: two turns plus one warm blank sandbox."""

    return {
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        "PWC_CHAT_BLANK_POOL_MIN": "1",
        "PWC_CHAT_BLANK_POOL_MAX": "1",
        "PWC_CHAT_SANDBOX_CPU": "0.5",
        "PWC_CHAT_SANDBOX_CPU_LIMIT": "1",
        "PWC_CHAT_SANDBOX_MEMORY_MIB": "512",
        "PWC_CHAT_SANDBOX_MEMORY_LIMIT_MIB": "2048",
    }


def staging_chat_capacity_configuration(existing: dict[str, str]) -> dict[str, str]:
    """Apply the qualified shape without changing an explicit pool toggle."""

    values = {**staging_chat_capacity_values(), **staging_chat_spend_values()}
    if "PWC_CHAT_BLANK_POOL_ENABLED" in existing:
        values.pop("PWC_CHAT_BLANK_POOL_ENABLED")
    return values


def staging_chat_pool_values(*, enabled: bool) -> dict[str, str]:
    """Toggle only the qualified one-blank staging pool shape."""

    values = {"PWC_CHAT_BLANK_POOL_ENABLED": "true" if enabled else "false"}
    if enabled:
        values.update(staging_chat_capacity_values())
    return values


def staging_chat_durable_dispatch_values(*, enabled: bool) -> dict[str, str]:
    """Toggle only the staging durable-turn compatibility bridge."""

    return {"PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED": "true" if enabled else "false"}


_STAGING_DURABLE_EXTERNAL_QUALIFICATION_ENABLED = {
    "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "durable-external-pi-v1",
    "PWC_CHAT_TURN_EVENT_JOURNAL_SCHEMA_ENABLED": "true",
    "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "true",
    "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "sandbox-executor-v1",
    "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "true",
    "PWC_CHAT_REMOTE_BASH_ENABLED": "true",
    "PWC_CHAT_REMOTE_READ_ENABLED": "true",
    "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "true",
    "PWC_CHAT_BLANK_POOL_ENABLED": "false",
    "PWC_CHAT_PI_PREWARM_ENABLED": "false",
    "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "32",
}
_STAGING_DURABLE_EXTERNAL_QUALIFICATION_DISABLED = {
    "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "false",
    "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "",
    "PWC_CHAT_TURN_EVENT_JOURNAL_SCHEMA_ENABLED": "false",
    "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "false",
    "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "",
    "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "false",
    "PWC_CHAT_REMOTE_BASH_ENABLED": "false",
    "PWC_CHAT_REMOTE_READ_ENABLED": "false",
    "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "false",
    "PWC_CHAT_BLANK_POOL_ENABLED": "true",
    "PWC_CHAT_PI_PREWARM_ENABLED": "true",
    "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "4",
}


def staging_durable_external_qualification_values(
    current: dict[str, str], *, enabled: bool
) -> dict[str, str]:
    """Enter or leave the exact staging-only 32-turn qualification profile."""

    required = {
        "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "false",
        "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED": "true",
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
        "PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED": "true",
        "PWC_CHAT_MAX_CONCURRENCY": "2",
        "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
        **(
            _STAGING_DURABLE_EXTERNAL_QUALIFICATION_DISABLED
            if enabled
            else _STAGING_DURABLE_EXTERNAL_QUALIFICATION_ENABLED
        ),
    }

    def observed_value(key: str, expected: str) -> str:
        if expected in {"true", "false"}:
            return _decoded_flag(current, key)
        if key in current:
            return decoded_value(current[key]).strip()
        if key == "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY" and expected == "4":
            return "4"
        return ""

    drifted = sorted(
        key
        for key, expected in required.items()
        if observed_value(key, expected) != expected
    )
    if drifted:
        raise ValueError(
            "staging durable external qualification baseline has drifted: "
            + ", ".join(drifted)
        )
    values = dict(
        _STAGING_DURABLE_EXTERNAL_QUALIFICATION_ENABLED
        if enabled
        else _STAGING_DURABLE_EXTERNAL_QUALIFICATION_DISABLED
    )
    if not enabled:
        values["PWC_ADMIN_API_TOKEN"] = ""
        return values
    existing_line = current.get("PWC_ADMIN_API_TOKEN")
    existing = decoded_value(existing_line).strip() if existing_line else ""
    values["PWC_ADMIN_API_TOKEN"] = (
        existing if 32 <= len(existing) <= 8192 else secrets.token_urlsafe(48)
    )
    return values


_PRODUCTION_DURABLE_EXTERNAL_ENABLED = {
    "PWC_CHAT_EXTERNAL_PI_READY_REGISTRY_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "durable-external-pi-v1",
    "PWC_CHAT_TURN_EVENT_JOURNAL_SCHEMA_ENABLED": "true",
    "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED": "true",
    "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "sandbox-executor-v1",
    "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED": "true",
    "PWC_CHAT_REMOTE_BASH_ENABLED": "true",
    "PWC_CHAT_REMOTE_READ_ENABLED": "true",
    "PWC_CHAT_LAZY_WORKSPACE_ENABLED": "true",
    "PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED": "true",
    "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": "external-pi-v1",
    "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "32",
    "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": "10",
    "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
    "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "60",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS": "60",
    "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS": "1",
    "PWC_CHAT_MAX_CONCURRENCY": "32",
    "PWC_CHAT_USER_MAX_CONCURRENCY": "1",
    "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "32",
    "PWC_CHAT_OPENAI_USER_MAX_CONCURRENCY": "1",
    # One worst-case 16-request turn for every admitted chat per 10-minute window.
    "PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS": "512",
    "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "16",
    "PWC_CHAT_BLANK_POOL_ENABLED": "false",
    "PWC_CHAT_PI_PREWARM_ENABLED": "false",
}


# Reviewed chat capacity tiers for the durable external profile. OpenAI
# concurrency equals admitted turns; the ten-minute call allowance grows faster
# because an MCP research turn spends 10-13 model calls and a full tier of turns
# cycles several times per window. The 32-turn allowance keeps each
# environment's established value.
CHAT_CAPACITY_TIERS = (32, 64)
_CHAT_CAPACITY_TIER_RATE_LIMIT_CALLS = {
    "production": {32: "512", 64: "4096"},
    "staging": {32: "300", 64: "4096"},
}


def chat_capacity_tier_values(
    current: dict[str, str], *, environment: str, tier: int
) -> dict[str, str]:
    """Move one environment between reviewed chat capacity tiers atomically."""

    if environment not in _CHAT_CAPACITY_TIER_RATE_LIMIT_CALLS:
        raise ValueError("chat capacity tiers apply to staging or production")
    if tier not in CHAT_CAPACITY_TIERS:
        raise ValueError("chat capacity tier must be 32 or 64")
    if _decoded_flag(current, "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED") != "true":
        raise ValueError("external Pi admission must already be enabled")
    return {
        "PWC_CHAT_MAX_CONCURRENCY": str(tier),
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": str(tier),
        "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": str(tier),
        "PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS": (
            _CHAT_CAPACITY_TIER_RATE_LIMIT_CALLS[environment][tier]
        ),
    }


def production_durable_external_values(
    current: dict[str, str], *, enabled: bool
) -> dict[str, str]:
    """Atomically enter or leave the approved production 32-turn profile."""

    if not enabled:
        disabled = {
            key: "false"
            for key, value in _PRODUCTION_DURABLE_EXTERNAL_ENABLED.items()
            if value == "true"
        }
        disabled.update(
            {
                "PWC_CHAT_EXTERNAL_PI_RUNTIME_CONTRACT_VERSION": "",
                "PWC_CHAT_SANDBOX_EXECUTOR_CONTRACT_VERSION": "",
                "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": "",
                "PWC_CHAT_MAX_CONCURRENCY": "2",
                "PWC_CHAT_USER_MAX_CONCURRENCY": "2",
                "PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY": "4",
                "PWC_CHAT_OPENAI_USER_MAX_CONCURRENCY": "2",
                "PWC_CHAT_OPENAI_GLOBAL_RATE_LIMIT_CALLS": "80",
                "PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP": "3",
                "PWC_CHAT_BLANK_POOL_ENABLED": "true",
                "PWC_CHAT_PI_PREWARM_ENABLED": "true",
            }
        )
        return disabled
    for key in (
        "PWC_CHAT_PUBLIC_ADMISSION_ENABLED",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED",
    ):
        if not _decoded_flag(current, key):
            raise ValueError("production chat admission must already be enabled")
    values = dict(_PRODUCTION_DURABLE_EXTERNAL_ENABLED)
    existing_line = current.get("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN")
    existing = decoded_value(existing_line).strip() if existing_line else ""
    if existing and not 32 <= len(existing) <= 8192:
        raise ValueError("production external Pi worker token is invalid")
    values["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"] = existing or secrets.token_urlsafe(48)
    return values


# Must match Settings.chat_deepseek_v4_flash_route when Hugging Face is selected.
STAGING_DEEPSEEK_PREWARM_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731:baseten"


def staging_chat_pi_prewarm_values(*, enabled: bool) -> dict[str, str]:
    """Toggle only the qualified staging Pi prewarm profile."""

    values = {"PWC_CHAT_PI_PREWARM_ENABLED": "true" if enabled else "false"}
    if enabled:
        values.update(
            {
                "PWC_CHAT_PI_PREWARM_MODEL": STAGING_DEEPSEEK_PREWARM_MODEL,
                "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": "medium",
            }
        )
    return values


def _decoded_flag(current: dict[str, str], key: str) -> str:
    line = current.get(key)
    if not line:
        return "false"
    return decoded_value(line).strip().lower()


def production_chat_pi_prewarm_values(
    current_production: dict[str, str], *, enabled: bool
) -> dict[str, str]:
    """Toggle production Pi prewarm only on an already-admitted DeepSeek pool."""

    if enabled:
        required = {
            "PWC_CHAT_ENABLED": "true",
            "PWC_CHAT_BLANK_POOL_ENABLED": "true",
            "PWC_CHAT_PERSISTENT_WORKER_ENABLED": "true",
            "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "true",
        }
        missing = [
            key
            for key, expected in required.items()
            if _decoded_flag(current_production, key) != expected
        ]
        if missing:
            raise ValueError(
                "production Pi prewarm requires an already-admitted chat pool: "
                + ", ".join(missing)
            )
        if _decoded_flag(current_production, "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED") == (
            "true"
        ):
            raise ValueError("production Pi prewarm cannot use an alternative model")
    return staging_chat_pi_prewarm_values(enabled=enabled)


def staging_chat_routing_values(
    *,
    enabled: bool,
    policy: str = "latency",
    preferred_providers: str = "fireworks",
    max_prompt_price_per_million_usd: float = 0.28,
    max_completion_price_per_million_usd: float = 0.56,
) -> dict[str, str]:
    """Toggle only the independently reversible staging routing experiment."""

    values = {"PWC_CHAT_OPENROUTER_ROUTING_ENABLED": str(enabled).lower()}
    if enabled:
        values["PWC_CHAT_OPENROUTER_ROUTING_POLICY"] = policy
        if policy == "preferred_provider":
            providers = ",".join(
                provider.strip()
                for provider in preferred_providers.split(",")
                if provider.strip()
            )
            if not providers:
                raise ValueError("preferred-provider routing requires provider slugs")
            if len(providers) > 512:
                raise ValueError("preferred-provider routing exceeds 512 characters")
            prices = (
                max_prompt_price_per_million_usd,
                max_completion_price_per_million_usd,
            )
            if any(price <= 0 or price > 100 for price in prices):
                raise ValueError("preferred-provider price ceilings must be 0-100")
            values.update(
                {
                    "PWC_CHAT_OPENROUTER_PREFERRED_PROVIDERS": providers,
                    "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": (
                        f"{max_prompt_price_per_million_usd:g}"
                    ),
                    "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": (
                        f"{max_completion_price_per_million_usd:g}"
                    ),
                }
            )
        elif policy == "price_performance":
            values.update(
                {
                    "PWC_CHAT_OPENROUTER_PREFERRED_MAX_LATENCY_P90_SECONDS": "3",
                    "PWC_CHAT_OPENROUTER_PREFERRED_MIN_THROUGHPUT_P90": "50",
                    "PWC_CHAT_OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION_USD": "0.28",
                    "PWC_CHAT_OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION_USD": "0.56",
                }
            )
    return values


def staging_chat_payload_values(*, enabled: bool, candidate: str) -> dict[str, str]:
    """Toggle one exact duplicate-removal candidate on staging."""

    values = {"PWC_CHAT_INITIAL_PAYLOAD_OPTIMIZATION_ENABLED": str(enabled).lower()}
    if enabled:
        values["PWC_CHAT_INITIAL_PAYLOAD_OPTIMIZATION_CANDIDATE"] = candidate
    return values


def staging_chat_alternative_model_values(
    *, enabled: bool, candidate: str, reasoning_effort: str = "medium"
) -> dict[str, str]:
    """Toggle one reviewed staging model and its compatible prewarm profile."""

    reviewed = {
        "openai/gpt-5.6-luna",
        "google/gemini-3.7-flash",
    }
    if candidate not in reviewed:
        raise ValueError("alternative model candidate is not reviewed")
    if reasoning_effort not in {"low", "medium", "high", "max"}:
        raise ValueError("alternative model reasoning effort is not reviewed")
    values = {
        "PWC_CHAT_ALTERNATIVE_MODEL_ENABLED": str(enabled).lower(),
        "PWC_CHAT_PI_PREWARM_MODEL": (
            candidate if enabled else STAGING_DEEPSEEK_PREWARM_MODEL
        ),
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": (
            reasoning_effort if enabled else "medium"
        ),
    }
    if enabled:
        values["PWC_CHAT_ALTERNATIVE_MODEL"] = candidate
    return values


def staging_chat_spend_values() -> dict[str, str]:
    return {
        "PWC_CHAT_BLANK_POOL_ENABLED": "false",
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED": "true",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "starter_workspace",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            f"modal-workspace-{STAGING_CHAT_MODAL_WORKSPACE}-250-staging-starter-v1"
        ),
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "0",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT": "pwc-chat-staging",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": STAGING_CHAT_MODAL_WORKSPACE,
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME": STAGING_CHAT_MODAL_OWNER_USERNAME,
        "MODAL_ENVIRONMENT": "pwc-chat-staging",
        "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS": "15",
        "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD": "1000000",
        "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS": "3600",
        "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS": "7200",
        "PWC_CHAT_SANDBOX_RUNBOOK_URL": "https://github.com/huggingface/paperswithcode/blob/main/docs/chat-sandbox-spend-runbook.md",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES": "root",
    }


def staging_chat_alert_values(legacy: dict[str, str]) -> dict[str, str]:
    return chat_alert_values(legacy, environment="staging")


def chat_alert_values(source: dict[str, str], *, environment: str) -> dict[str, str]:
    keys = (
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL",
        "PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL",
    )
    missing = [key for key in keys if key not in source]
    if missing:
        raise ValueError("chat alert environment is missing: " + ", ".join(missing))
    values = {key: decoded_value(source[key]).strip() for key in keys}
    for key, value in values.items():
        parsed = urlsplit(value)
        if (
            not value
            or len(value) > 2000
            or parsed.scheme != "https"
            or not parsed.hostname
        ):
            raise ValueError(f"{key} must be a non-empty HTTPS webhook URL")
    if values[keys[0]] == values[keys[1]]:
        raise ValueError(f"{environment} chat alert webhooks must be distinct")
    return values


def production_chat_preparation_values(
    source: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Build a validated, non-loaded production chat preparation bundle."""

    required = {
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE",
        "PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME",
        "PWC_CHAT_SANDBOX_OPERATOR_USERNAMES",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError(
            "production chat environment is missing: " + ", ".join(missing)
        )
    protected = {key: decoded_value(source[key]).strip() for key in required}
    empty = sorted(key for key, value in protected.items() if not value)
    if empty:
        raise ValueError("production chat environment is empty: " + ", ".join(empty))
    workspace = protected["PWC_CHAT_SANDBOX_MODAL_WORKSPACE"]
    expected_attestation = (
        f"modal-workspace-{workspace}-250-production-250-warn200-app225-v3"
    )
    if protected["PWC_CHAT_SANDBOX_BUDGET_ATTESTATION"] != expected_attestation:
        raise ValueError(
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION does not match the production policy"
        )
    return {
        **protected,
        **production_title_values(source, current_production, current_staging),
        **production_openrouter_values(source, current_staging),
        **chat_alert_values(source, environment="production"),
        **staging_chat_capacity_values(),
        "PWC_CHAT_ENABLED": "true",
        "PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE": "100",
        "PWC_CHAT_PUBLIC_ADMISSION_ENABLED": "false",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED": "false",
        "PWC_CHAT_BLANK_POOL_ENABLED": "false",
        "PWC_CHAT_PERSISTENT_WORKER_ENABLED": "true",
        "PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED": "false",
        "PWC_CHAT_GATEWAY_URL": (
            "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
        ),
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "200000000",
        "PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED": "true",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "team_environments",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": expected_attestation,
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "225000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT": "pwc-chat-production",
        "MODAL_ENVIRONMENT": "pwc-chat-production",
        "PWC_CHAT_SANDBOX_WATCHDOG_SECONDS": "15",
        "PWC_CHAT_SANDBOX_DRAIN_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_TERMINATION_GRACE_SECONDS": "30",
        "PWC_CHAT_SANDBOX_RECONCILIATION_ALLOWANCE_MICROUSD": "1000000",
        "PWC_CHAT_SANDBOX_RECONCILIATION_INTERVAL_SECONDS": "3600",
        "PWC_CHAT_SANDBOX_RECONCILIATION_STALE_SECONDS": "7200",
        "PWC_CHAT_OPERATIONAL_ALERTS_ENABLED": "true",
        "PWC_CHAT_PROVIDER_ALERT_WINDOW_SECONDS": "300",
        "PWC_CHAT_PROVIDER_ALERT_MIN_FAILURES": "5",
        "PWC_CHAT_PROVIDER_ALERT_FAILURE_PERCENT": "50",
        "PWC_CHAT_SANDBOX_RUNBOOK_URL": (
            "https://github.com/huggingface/paperswithcode/blob/main/"
            "docs/chat-sandbox-spend-runbook.md"
        ),
    }


def production_modal_profile_source(
    source: dict[str, str],
    config_path: Path,
    profile: str,
) -> dict[str, str]:
    """Import one protected Modal profile without exposing or duplicating it."""

    if not config_path.is_file():
        raise ValueError("Modal profile configuration is missing")
    if config_path.stat().st_mode & 0o077:
        raise ValueError("Modal profile configuration must not be group/world readable")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError("Modal profile configuration is invalid") from error
    selected = config.get(profile)
    if not isinstance(selected, dict):
        raise ValueError("requested Modal profile is missing")
    values = {
        "MODAL_TOKEN_ID": selected.get("token_id"),
        "MODAL_TOKEN_SECRET": selected.get("token_secret"),
    }
    if any(
        not isinstance(value, str) or not value.strip() for value in values.values()
    ):
        raise ValueError("requested Modal profile has incomplete credentials")
    normalized = {key: value.strip() for key, value in values.items()}
    for key, value in normalized.items():
        existing = decoded_value(source[key]).strip() if key in source else ""
        if existing and existing != value:
            raise ValueError(f"{key} conflicts with the requested Modal profile")
    return assign(source, normalized)


def production_chat_install_values(
    sealed: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Revalidate the sealed bundle before a separately authorized install."""

    if not sealed:
        raise ValueError("sealed production chat preparation is missing")
    values = production_chat_preparation_values(
        sealed,
        current_production,
        current_staging,
    )
    normalized = {key: decoded_value(line).strip() for key, line in sealed.items()}
    unexpected = sorted(set(normalized) - set(values))
    if unexpected:
        raise ValueError(
            "sealed production chat preparation contains unexpected keys: "
            + ", ".join(unexpected)
        )
    mismatched = sorted(
        key for key, value in values.items() if normalized.get(key) != value
    )
    if mismatched:
        raise ValueError(
            "sealed production chat preparation is incomplete or stale: "
            + ", ".join(mismatched)
        )
    return values


def production_chat_admission_values(
    sealed: dict[str, str],
    current_production: dict[str, str],
    current_staging: dict[str, str],
) -> dict[str, str]:
    """Open production admission only from the exact installed sealed bundle."""

    values = production_chat_install_values(
        sealed,
        current_production,
        current_staging,
    )
    activation_keys = {
        "PWC_CHAT_PUBLIC_ADMISSION_ENABLED",
        "PWC_CHAT_SANDBOX_ADMISSION_ENABLED",
        "PWC_CHAT_BLANK_POOL_ENABLED",
        "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED",
    }
    mismatched = sorted(
        key
        for key, value in values.items()
        if key not in activation_keys
        and decoded_value(current_production.get(key, "")).strip() != value
    )
    if mismatched:
        raise ValueError(
            "installed production chat preparation has drifted: "
            + ", ".join(mismatched)
        )
    activation = {
        key: decoded_value(current_production.get(key, "false")).strip().lower()
        for key in activation_keys
    }
    if set(activation.values()) - {"true", "false"}:
        raise ValueError("production chat activation controls are invalid")
    if len(set(activation.values())) != 1:
        raise ValueError("production chat activation controls must change together")
    return {key: "true" for key in activation_keys}


def production_codex_values(
    legacy: dict[str, str], namespace: str, *, scheduled: bool = True
) -> dict[str, str]:
    return {
        # The immutable release launcher overrides these non-secret capability
        # flags from release.json, preserving rollback compatibility.
        "PWC_CODEX_ADD_EVALS_ENABLED": "false",
        "PWC_CODEX_ENRICH_PAPER_ENABLED": "false",
        "PWC_CODEX_JOBS_ENABLED": "false",
        "PWC_CODEX_JOBS_NAMESPACE": namespace,
        "PWC_CODEX_JOBS_OPENAI_API_KEY": decoded_value(legacy["OPENAI_API_KEY"]),
        "PWC_CODEX_JOBS_TOKEN": decoded_value(legacy["PWC_HF_TOKEN"]),
        **production_codex_image_values(),
        "PWC_CODEX_JOBS_CLI_VERSION": "0.75.0",
        "PWC_CODEX_JOBS_MODEL": "gpt-5.6-luna",
        "PWC_CODEX_JOBS_REASONING_EFFORT": "medium",
        "PWC_CODEX_JOBS_MAX_ACTIVE": "4",
        "PWC_CODEX_JOBS_MAX_SCHEDULED_ACTIVE": "3",
        "PWC_CODEX_CURATION_SCHEDULER_ENABLED": "true" if scheduled else "false",
        "PWC_CODEX_CURATION_DIRECT_APPLY_ENABLED": "true" if scheduled else "false",
        "PWC_CODEX_CURATION_TRACE_UPLOAD_ENABLED": "true" if scheduled else "false",
        "PWC_CODEX_CURATION_TRACE_HF_BUCKET_ID": (
            f"{namespace}/curate-papers-traces" if scheduled else ""
        ),
        "PWC_CODEX_CURATION_POLICY_VERSION": "hf-daily-v1",
    }


def production_codex_image_values() -> dict[str, str]:
    return {
        "PWC_CODEX_JOBS_IMAGE": (
            f"{OPERATOR.curator_image_repository}:runner-f165a0e4c56a"
            "@sha256:3c4c6b16737946f69a0390f3c014ffea5a46be8b7e63633e804c21d3e0046496"
        ),
        "PWC_CODEX_JOBS_IMAGE_REVISION": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-env", type=Path, required=True)
    parser.add_argument("--codex-jobs-namespace")
    parser.add_argument("--production-codex-only", action="store_true")
    parser.add_argument("--production-codex-image-only", action="store_true")
    parser.add_argument("--staging-codex-too", action="store_true")
    parser.add_argument("--staging-langfuse-only", action="store_true")
    parser.add_argument("--production-langfuse-only", action="store_true")
    parser.add_argument("--staging-title-only", action="store_true")
    parser.add_argument("--staging-openrouter-only", action="store_true")
    parser.add_argument("--staging-openai-direct-only", action="store_true")
    parser.add_argument("--staging-openai-direct-disable-only", action="store_true")
    parser.add_argument("--staging-scope-guardrail-only", action="store_true")
    parser.add_argument("--staging-scope-title-hf-only", action="store_true")
    parser.add_argument("--production-scope-title-hf-only", action="store_true")
    parser.add_argument("--staging-openrouter-disable-only", action="store_true")
    parser.add_argument("--staging-openrouter-secrets-rotate-only", action="store_true")
    parser.add_argument("--staging-chat-capacity-only", action="store_true")
    parser.add_argument("--staging-chat-alerts-only", action="store_true")
    parser.add_argument("--staging-chat-pool-enable-only", action="store_true")
    parser.add_argument("--staging-chat-pool-disable-only", action="store_true")
    parser.add_argument(
        "--staging-chat-durable-dispatch-enable-only", action="store_true"
    )
    parser.add_argument(
        "--staging-chat-durable-dispatch-disable-only", action="store_true"
    )
    parser.add_argument(
        "--staging-durable-external-qualification-enable-only", action="store_true"
    )
    parser.add_argument(
        "--staging-durable-external-qualification-disable-only", action="store_true"
    )
    parser.add_argument(
        "--staging-modal-rate-evidence-install-only", action="store_true"
    )
    parser.add_argument(
        "--staging-modal-rate-evidence-remove-only", action="store_true"
    )
    parser.add_argument("--staging-modal-rate-release-id")
    parser.add_argument("--staging-modal-rate-microusd-per-second", type=int)
    parser.add_argument("--staging-chat-pi-prewarm-enable-only", action="store_true")
    parser.add_argument("--staging-chat-pi-prewarm-disable-only", action="store_true")
    parser.add_argument("--staging-chat-routing-enable-only", action="store_true")
    parser.add_argument("--staging-chat-routing-disable-only", action="store_true")
    parser.add_argument(
        "--staging-chat-routing-policy",
        choices=("latency", "preferred_provider", "price_performance"),
        default="latency",
    )
    parser.add_argument(
        "--staging-chat-preferred-providers",
        default="fireworks",
        help="comma-separated OpenRouter provider tags for the preferred-provider pilot",
    )
    parser.add_argument(
        "--staging-chat-routing-max-prompt-price",
        type=float,
        default=0.28,
        help="preferred-provider prompt price ceiling in USD per million tokens",
    )
    parser.add_argument(
        "--staging-chat-routing-max-completion-price",
        type=float,
        default=0.56,
        help="preferred-provider completion price ceiling in USD per million tokens",
    )
    parser.add_argument("--staging-chat-payload-enable-only", action="store_true")
    parser.add_argument("--staging-chat-payload-disable-only", action="store_true")
    parser.add_argument(
        "--staging-chat-payload-candidate",
        choices=("system_duplicates", "tool_duplicates"),
        default="system_duplicates",
    )
    parser.add_argument("--staging-chat-alternative-enable-only", action="store_true")
    parser.add_argument("--staging-chat-alternative-disable-only", action="store_true")
    parser.add_argument(
        "--staging-chat-alternative-model",
        choices=("openai/gpt-5.6-luna", "google/gemini-3.7-flash"),
        default="openai/gpt-5.6-luna",
    )
    parser.add_argument(
        "--staging-chat-alternative-reasoning-effort",
        choices=("low", "medium", "high", "max"),
        default="medium",
    )
    parser.add_argument("--staging-web-search-only", action="store_true")
    parser.add_argument("--production-web-search-only", action="store_true")
    parser.add_argument("--staging-github-only", action="store_true")
    parser.add_argument("--production-cron-github-only", action="store_true")
    parser.add_argument("--production-chat-seal-only", action="store_true")
    parser.add_argument("--production-chat-install-only", action="store_true")
    parser.add_argument("--production-chat-admission-enable-only", action="store_true")
    parser.add_argument(
        "--production-durable-external-enable-only", action="store_true"
    )
    parser.add_argument(
        "--production-durable-external-disable-only", action="store_true"
    )
    parser.add_argument("--production-chat-pi-prewarm-enable-only", action="store_true")
    parser.add_argument(
        "--production-chat-pi-prewarm-disable-only", action="store_true"
    )
    parser.add_argument("--production-openai-direct-only", action="store_true")
    parser.add_argument("--production-excalidraw-enable-only", action="store_true")
    parser.add_argument("--production-excalidraw-disable-only", action="store_true")
    parser.add_argument("--modal-profile")
    parser.add_argument(
        "--modal-profile-config",
        type=Path,
        default=Path("/root/.modal.toml"),
    )
    parser.add_argument(
        "--production-chat-capacity-tier", type=int, choices=CHAT_CAPACITY_TIERS
    )
    parser.add_argument(
        "--staging-chat-capacity-tier", type=int, choices=CHAT_CAPACITY_TIERS
    )
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    tier_modes = [
        (environment, tier)
        for environment, tier in (
            ("production", args.production_chat_capacity_tier),
            ("staging", args.staging_chat_capacity_tier),
        )
        if tier is not None
    ]
    if tier_modes:
        other_modes = [
            value for value in vars(args).values() if isinstance(value, bool) and value
        ]
        if (
            len(tier_modes) != 1
            or other_modes
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error("chat capacity tier mode must run alone")
        environment, tier = tier_modes[0]
        confirmation = f"SET_{environment.upper()}_CHAT_CAPACITY_TIER_{tier}"
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        current = read_lines(CONFIG_ROOT / f"{environment}.env")
        try:
            values = chat_capacity_tier_values(
                current, environment=environment, tier=tier
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / f"{environment}.env",
            assign(current, values),
            f"pwc-{environment}",
        )
        print(f"set {environment} chat capacity tier {tier}; deploy/refresh to apply")
        return 0
    legacy = read_lines(args.legacy_env)
    modal_rate_modes = (
        args.staging_modal_rate_evidence_install_only,
        args.staging_modal_rate_evidence_remove_only,
    )
    if any(modal_rate_modes):
        other_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "staging_modal_rate_evidence_install_only",
                "staging_modal_rate_evidence_remove_only",
            }
            and isinstance(value, bool)
            and value
        ]
        if (
            sum(modal_rate_modes) != 1
            or other_modes
            or args.codex_jobs_namespace
            or args.modal_profile
            or not args.staging_modal_rate_release_id
        ):
            parser.error("staging Modal rate evidence mode must run alone")
        install = args.staging_modal_rate_evidence_install_only
        confirmation = (
            "INSTALL_STAGING_MODAL_RATE_EVIDENCE"
            if install
            else "REMOVE_STAGING_MODAL_RATE_EVIDENCE"
        )
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        if install != (args.staging_modal_rate_microusd_per_second is not None):
            parser.error("install requires one explicit staging Modal rate")
        try:
            validate_active_staging_release(
                APP_ROOT, args.staging_modal_rate_release_id
            )
            path = CONFIG_ROOT / "staging-modal-rate-evidence.json"
            if install:
                values = staging_modal_rate_evidence(
                    app_root=APP_ROOT,
                    release_id=args.staging_modal_rate_release_id,
                    microusd_per_second=args.staging_modal_rate_microusd_per_second,
                )
                write_staging_modal_rate_evidence(path, values)
            else:
                remove_staging_modal_rate_evidence(
                    path, args.staging_modal_rate_release_id
                )
        except ValueError as error:
            parser.error(str(error))
        print(
            f"{'installed' if install else 'removed'} protected staging Modal rate "
            "evidence; no service was restarted"
        )
        return 0
    scope_title_modes = (
        args.staging_scope_title_hf_only,
        args.production_scope_title_hf_only,
    )
    if any(scope_title_modes):
        other_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "staging_scope_title_hf_only",
                "production_scope_title_hf_only",
            }
            and isinstance(value, bool)
            and value
        ]
        if (
            sum(scope_title_modes) != 1
            or other_modes
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error("HF scope/title mode must run alone")
        environment = "staging" if args.staging_scope_title_hf_only else "production"
        expected_confirmation = (
            None
            if environment == "staging"
            else "ENABLE_PRODUCTION_HF_SCOPE_AND_TITLES"
        )
        if args.confirm != expected_confirmation:
            if expected_confirmation is None:
                parser.error("staging HF scope/title mode does not accept --confirm")
            parser.error(f"--confirm must be {expected_confirmation}")
        if (
            not args.legacy_env.is_file()
            or args.legacy_env.stat().st_uid != 0
            or args.legacy_env.stat().st_mode & 0o077
        ):
            parser.error("HF scope/title source must be a protected root-only file")
        target = CONFIG_ROOT / f"{environment}.env"
        other = CONFIG_ROOT / (
            "production.env" if environment == "staging" else "staging.env"
        )
        current = read_lines(target)
        try:
            values = scope_title_hf_values(
                legacy,
                current,
                read_lines(other),
                environment=environment,
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            target,
            assign(current, values),
            f"pwc-{environment}",
        )
        print(
            f"enabled {environment} HF GLM titles and research-scope guardrail; "
            "no service was restarted"
        )
        return 0
    if args.staging_scope_guardrail_only:
        other_modes = [
            value
            for key, value in vars(args).items()
            if key != "staging_scope_guardrail_only"
            and isinstance(value, bool)
            and value
        ]
        if (
            other_modes
            or args.confirm is not None
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error("staging scope guardrail mode must run alone")
        current = read_lines(CONFIG_ROOT / "staging.env")
        try:
            values = staging_scope_guardrail_values(current)
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "staging.env",
            assign(current, values),
            "pwc-staging",
        )
        print("enabled staging research-scope guardrail; no service was restarted")
        return 0
    production_external_modes = (
        args.production_durable_external_enable_only,
        args.production_durable_external_disable_only,
    )
    if any(production_external_modes):
        other_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "production_durable_external_enable_only",
                "production_durable_external_disable_only",
            }
            and isinstance(value, bool)
            and value
        ]
        if (
            sum(production_external_modes) != 1
            or other_modes
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error("production durable external mode must run alone")
        enabled = args.production_durable_external_enable_only
        confirmation = (
            "ENABLE_PRODUCTION_DURABLE_EXTERNAL"
            if enabled
            else "DISABLE_PRODUCTION_DURABLE_EXTERNAL"
        )
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        current = read_lines(CONFIG_ROOT / "production.env")
        try:
            values = production_durable_external_values(current, enabled=enabled)
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "production.env",
            assign(current, values),
            "pwc-production",
        )
        print(
            f"{'enabled' if enabled else 'disabled'} production durable external "
            "32-turn profile; no service was restarted"
        )
        return 0
    qualification_modes = (
        args.staging_durable_external_qualification_enable_only,
        args.staging_durable_external_qualification_disable_only,
    )
    if any(qualification_modes):
        other_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "staging_durable_external_qualification_enable_only",
                "staging_durable_external_qualification_disable_only",
            }
            and isinstance(value, bool)
            and value
        ]
        if (
            sum(qualification_modes) != 1
            or other_modes
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error(
                "staging durable external qualification enable/disable must run alone"
            )
        enabled = args.staging_durable_external_qualification_enable_only
        confirmation = (
            "ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION"
            if enabled
            else "DISABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION"
        )
        if args.confirm != confirmation:
            parser.error(
                "staging durable external qualification --confirm must be "
                f"{confirmation}"
            )
        current = read_lines(CONFIG_ROOT / "staging.env")
        try:
            values = staging_durable_external_qualification_values(
                current, enabled=enabled
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "staging.env",
            assign(current, values),
            "pwc-staging",
        )
        print(
            f"{'enabled' if enabled else 'disabled'} staging durable external "
            "qualification profile; no service was restarted"
        )
        return 0
    durable_dispatch_modes = (
        args.staging_chat_durable_dispatch_enable_only,
        args.staging_chat_durable_dispatch_disable_only,
    )
    if any(durable_dispatch_modes):
        other_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "staging_chat_durable_dispatch_enable_only",
                "staging_chat_durable_dispatch_disable_only",
            }
            and isinstance(value, bool)
            and value
        ]
        if (
            sum(durable_dispatch_modes) != 1
            or other_modes
            or args.confirm is not None
            or args.codex_jobs_namespace
            or args.modal_profile
        ):
            parser.error(
                "staging durable dispatch enable/disable must run alone "
                "without --confirm"
            )
        enabled = args.staging_chat_durable_dispatch_enable_only
        staging = assign(
            read_lines(CONFIG_ROOT / "staging.env"),
            staging_chat_durable_dispatch_values(enabled=enabled),
        )
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(
            f"{'enabled' if enabled else 'disabled'} staging chat durable dispatch; "
            "no service was restarted"
        )
        return 0
    if args.production_codex_image_only:
        selected_modes = [
            value
            for key, value in vars(args).items()
            if key != "production_codex_image_only"
            and isinstance(value, bool)
            and value
        ]
        if selected_modes or args.codex_jobs_namespace or args.modal_profile:
            parser.error("production Codex image mode must run alone")
        if args.confirm != "UPDATE_PRODUCTION_CODEX_IMAGE":
            parser.error("--confirm must be UPDATE_PRODUCTION_CODEX_IMAGE")
        values = production_codex_image_values()
        targets = (
            (CONFIG_ROOT / "production.env", "pwc-production"),
            (CONFIG_ROOT / "production-cron.env", "pwc-cron"),
        )
        missing = [str(path) for path, _group in targets if not path.is_file()]
        if missing:
            parser.error(
                "production Codex image targets are missing: " + ", ".join(missing)
            )
        updates = [
            (path, assign(read_lines(path), values), group) for path, group in targets
        ]
        for path, lines, group in updates:
            write_env(path, lines, group)
        print("updated production and CRON Codex image pin")
        return 0
    if args.modal_profile and not args.production_chat_seal_only:
        parser.error("--modal-profile requires --production-chat-seal-only")
    if (
        args.production_excalidraw_enable_only
        or args.production_excalidraw_disable_only
    ):
        if (
            args.production_excalidraw_enable_only
            and args.production_excalidraw_disable_only
        ):
            parser.error("production Excalidraw modes are mutually exclusive")
        selected_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "legacy_env",
                "confirm",
                "production_excalidraw_enable_only",
                "production_excalidraw_disable_only",
                "staging_chat_routing_policy",
                "staging_chat_preferred_providers",
                "staging_chat_routing_max_prompt_price",
                "staging_chat_routing_max_completion_price",
                "staging_chat_payload_candidate",
                "staging_chat_alternative_model",
                "staging_chat_alternative_reasoning_effort",
                "modal_profile_config",
            }
            and isinstance(value, bool)
            and value
        ]
        if selected_modes or args.codex_jobs_namespace or args.modal_profile:
            parser.error("production Excalidraw mode must run alone")
        enabled = args.production_excalidraw_enable_only
        confirmation = (
            "ENABLE_PRODUCTION_EXCALIDRAW"
            if enabled
            else "DISABLE_PRODUCTION_EXCALIDRAW"
        )
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        current = read_lines(CONFIG_ROOT / "production.env")
        try:
            values = production_excalidraw_values(current, enabled=enabled)
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "production.env",
            assign(current, values),
            "pwc-production",
        )
        print(f"{'enabled' if enabled else 'disabled'} production Excalidraw")
        return 0
    if args.production_openai_direct_only:
        selected_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "legacy_env",
                "confirm",
                "production_openai_direct_only",
                "staging_chat_routing_policy",
                "staging_chat_preferred_providers",
                "staging_chat_routing_max_prompt_price",
                "staging_chat_routing_max_completion_price",
                "staging_chat_payload_candidate",
                "staging_chat_alternative_model",
                "staging_chat_alternative_reasoning_effort",
                "modal_profile_config",
            }
            and isinstance(value, bool)
            and value
        ]
        if selected_modes or args.codex_jobs_namespace or args.modal_profile:
            parser.error("production direct OpenAI mode must run alone")
        if args.confirm != "ENABLE_PRODUCTION_OPENAI_DIRECT":
            parser.error("--confirm must be ENABLE_PRODUCTION_OPENAI_DIRECT")
        current = read_lines(CONFIG_ROOT / "production.env")
        try:
            values = production_openai_direct_values(current)
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "production.env",
            assign(current, values),
            "pwc-production",
        )
        print("enabled production OpenAI Luna default and one-blank warm profile")
        return 0
    if args.staging_openai_direct_only or args.staging_openai_direct_disable_only:
        if args.staging_openai_direct_only and args.staging_openai_direct_disable_only:
            parser.error("staging direct OpenAI modes are mutually exclusive")
        selected_modes = [
            value
            for key, value in vars(args).items()
            if key
            not in {
                "legacy_env",
                "confirm",
                "staging_openai_direct_only",
                "staging_openai_direct_disable_only",
                "staging_chat_routing_policy",
                "staging_chat_preferred_providers",
                "staging_chat_routing_max_prompt_price",
                "staging_chat_routing_max_completion_price",
                "staging_chat_payload_candidate",
                "staging_chat_alternative_model",
                "staging_chat_alternative_reasoning_effort",
                "modal_profile_config",
            }
            and isinstance(value, bool)
            and value
        ]
        if selected_modes or args.codex_jobs_namespace or args.modal_profile:
            parser.error("staging direct OpenAI mode must run alone")
        if args.staging_openai_direct_only:
            if (
                not args.legacy_env.is_file()
                or args.legacy_env.stat().st_uid != 0
                or args.legacy_env.stat().st_mode & 0o077
            ):
                parser.error("staging OpenAI source must be a protected root-only file")
            try:
                values = staging_openai_direct_values(
                    legacy, read_lines(CONFIG_ROOT / "production.env")
                )
            except ValueError as error:
                parser.error(str(error))
            label = "installed isolated staging direct OpenAI credential and profile"
        else:
            values = staging_openai_direct_disable_values()
            label = "disabled staging direct OpenAI profile"
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(label)
        return 0
    experiment_modes = (
        args.staging_chat_routing_enable_only,
        args.staging_chat_routing_disable_only,
        args.staging_chat_payload_enable_only,
        args.staging_chat_payload_disable_only,
        args.staging_chat_alternative_enable_only,
        args.staging_chat_alternative_disable_only,
    )
    if any(experiment_modes):
        all_other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.production_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_chat_pi_prewarm_enable_only,
            args.staging_chat_pi_prewarm_disable_only,
            args.staging_web_search_only,
            args.production_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_admission_enable_only,
            args.production_chat_pi_prewarm_enable_only,
            args.production_chat_pi_prewarm_disable_only,
        )
        if sum(experiment_modes) != 1 or any(all_other_modes):
            parser.error("staging chat experiment toggles must run alone")
        if (
            args.staging_chat_routing_enable_only
            or args.staging_chat_routing_disable_only
        ):
            values = staging_chat_routing_values(
                enabled=args.staging_chat_routing_enable_only,
                policy=args.staging_chat_routing_policy,
                preferred_providers=args.staging_chat_preferred_providers,
                max_prompt_price_per_million_usd=(
                    args.staging_chat_routing_max_prompt_price
                ),
                max_completion_price_per_million_usd=(
                    args.staging_chat_routing_max_completion_price
                ),
            )
            label = "routing"
        elif (
            args.staging_chat_payload_enable_only
            or args.staging_chat_payload_disable_only
        ):
            values = staging_chat_payload_values(
                enabled=args.staging_chat_payload_enable_only,
                candidate=args.staging_chat_payload_candidate,
            )
            label = "payload optimization"
        else:
            values = staging_chat_alternative_model_values(
                enabled=args.staging_chat_alternative_enable_only,
                candidate=args.staging_chat_alternative_model,
                reasoning_effort=args.staging_chat_alternative_reasoning_effort,
            )
            label = "alternative model"
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(f"configured staging chat {label} experiment")
        return 0
    if (
        args.staging_chat_pi_prewarm_enable_only
        or args.staging_chat_pi_prewarm_disable_only
    ):
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.production_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.production_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_admission_enable_only,
            args.production_chat_pi_prewarm_enable_only,
            args.production_chat_pi_prewarm_disable_only,
        )
        if (
            args.staging_chat_pi_prewarm_enable_only
            and args.staging_chat_pi_prewarm_disable_only
        ) or any(other_modes):
            parser.error(
                "staging Pi prewarm enable/disable cannot be combined with other modes"
            )
        enabled = args.staging_chat_pi_prewarm_enable_only
        staging = assign(
            read_lines(CONFIG_ROOT / "staging.env"),
            staging_chat_pi_prewarm_values(enabled=enabled),
        )
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(f"{'enabled' if enabled else 'disabled'} staging Pi prewarm")
        return 0
    if args.production_langfuse_only:
        conflicting_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.production_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_admission_enable_only,
            args.production_chat_pi_prewarm_enable_only,
            args.production_chat_pi_prewarm_disable_only,
        )
        if any(conflicting_modes) or args.codex_jobs_namespace or args.modal_profile:
            parser.error(
                "--production-langfuse-only cannot be combined with other modes"
            )
        if args.legacy_env.stat().st_mode & 0o077:
            parser.error("production Langfuse source must not be group/world readable")
        try:
            values = production_langfuse_values(
                legacy, read_lines(CONFIG_ROOT / "staging.env")
            )
        except ValueError as error:
            parser.error(str(error))
        production = assign(read_lines(CONFIG_ROOT / "production.env"), values)
        write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
        print("installed isolated production Langfuse credentials")
        return 0
    if args.production_chat_admission_enable_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_pi_prewarm_enable_only,
            args.production_chat_pi_prewarm_disable_only,
        )
        if any(other_modes):
            parser.error(
                "--production-chat-admission-enable-only cannot be combined "
                "with other modes"
            )
        confirmation = "ENABLE_PRODUCTION_CHAT_ADMISSION"
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        current_production = read_lines(CONFIG_ROOT / "production.env")
        current_staging = read_lines(CONFIG_ROOT / "staging.env")
        try:
            values = production_chat_admission_values(
                read_lines(PRODUCTION_CHAT_SEALED_CONFIG),
                current_production,
                current_staging,
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "production.env",
            assign(current_production, values),
            "pwc-production",
        )
        print(
            "enabled production funded dispatch, public and sandbox admission, "
            "and the one-blank pool; no service was restarted"
        )
        return 0
    if (
        args.production_chat_pi_prewarm_enable_only
        or args.production_chat_pi_prewarm_disable_only
    ):
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.production_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_chat_pi_prewarm_enable_only,
            args.staging_chat_pi_prewarm_disable_only,
            args.staging_web_search_only,
            args.production_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_admission_enable_only,
        )
        if (
            args.production_chat_pi_prewarm_enable_only
            and args.production_chat_pi_prewarm_disable_only
        ) or any(other_modes):
            parser.error(
                "production Pi prewarm enable/disable cannot be combined with other modes"
            )
        enabled = args.production_chat_pi_prewarm_enable_only
        confirmation = (
            "ENABLE_PRODUCTION_CHAT_PI_PREWARM"
            if enabled
            else "DISABLE_PRODUCTION_CHAT_PI_PREWARM"
        )
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        current_production = read_lines(CONFIG_ROOT / "production.env")
        try:
            values = production_chat_pi_prewarm_values(
                current_production, enabled=enabled
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            CONFIG_ROOT / "production.env",
            assign(current_production, values),
            "pwc-production",
        )
        print(
            f"{'enabled' if enabled else 'disabled'} production Pi prewarm; "
            "no service was restarted"
        )
        return 0
    if args.production_cron_github_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.staging_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
        )
        if any(other_modes):
            parser.error(
                "--production-cron-github-only cannot be combined with other modes"
            )
        confirmation = "ROTATE_PRODUCTION_CRON_GITHUB"
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        try:
            values = production_cron_github_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        cron = assign(read_lines(CONFIG_ROOT / "production-cron.env"), values)
        write_env(CONFIG_ROOT / "production-cron.env", cron, "pwc-cron")
        print("rotated production CRON GitHub credential")
        return 0
    if args.production_chat_seal_only or args.production_chat_install_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.staging_github_only,
        )
        if any(other_modes) or (
            args.production_chat_seal_only and args.production_chat_install_only
        ):
            parser.error(
                "production chat preparation modes cannot be combined with other modes"
            )
        if args.production_chat_install_only:
            confirmation = "INSTALL_PRODUCTION_CHAT_PREPARATION"
            if args.confirm != confirmation:
                parser.error(f"--confirm must be {confirmation}")
            current_production = read_lines(CONFIG_ROOT / "production.env")
            current_staging = read_lines(CONFIG_ROOT / "staging.env")
            try:
                values = production_chat_install_values(
                    read_lines(PRODUCTION_CHAT_SEALED_CONFIG),
                    current_production,
                    current_staging,
                )
            except ValueError as error:
                parser.error(str(error))
            write_env(
                CONFIG_ROOT / "production.env",
                assign(current_production, values),
                "pwc-production",
            )
            print(
                "installed sealed production chat preparation; "
                "no service was restarted and admission remains disabled"
            )
            return 0
        confirmation = "SEAL_PRODUCTION_CHAT_PREPARATION"
        if args.confirm != confirmation:
            parser.error(f"--confirm must be {confirmation}")
        if args.modal_profile:
            try:
                legacy = production_modal_profile_source(
                    legacy,
                    args.modal_profile_config,
                    args.modal_profile,
                )
            except ValueError as error:
                parser.error(str(error))
        try:
            values = production_chat_preparation_values(
                legacy,
                read_lines(CONFIG_ROOT / "production.env"),
                read_lines(CONFIG_ROOT / "staging.env"),
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(
            PRODUCTION_CHAT_SEALED_CONFIG,
            assign({}, values),
            "pwc-production",
        )
        print(
            "sealed non-loaded production chat preparation; "
            "the active production environment was not changed"
        )
        return 0
    if args.staging_github_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
        )
        if any(other_modes):
            parser.error("--staging-github-only cannot be combined with other modes")
        try:
            values = staging_github_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging GitHub credential")
        return 0
    if args.production_web_search_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.staging_web_search_only,
            args.staging_github_only,
            args.production_cron_github_only,
            args.production_chat_seal_only,
            args.production_chat_install_only,
            args.production_chat_admission_enable_only,
            args.production_chat_pi_prewarm_enable_only,
            args.production_chat_pi_prewarm_disable_only,
        )
        if any(other_modes):
            parser.error(
                "--production-web-search-only cannot be combined with other modes"
            )
        try:
            values = production_web_search_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        production = assign(read_lines(CONFIG_ROOT / "production.env"), values)
        write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
        print("installed production web-search configuration")
        return 0
    if args.staging_web_search_only:
        other_modes = (
            args.production_codex_only,
            args.staging_codex_too,
            args.staging_langfuse_only,
            args.staging_title_only,
            args.staging_openrouter_only,
            args.staging_openrouter_disable_only,
            args.staging_openrouter_secrets_rotate_only,
            args.staging_chat_capacity_only,
            args.staging_chat_alerts_only,
            args.staging_chat_pool_enable_only,
            args.staging_chat_pool_disable_only,
            args.production_chat_seal_only,
        )
        if any(other_modes):
            parser.error(
                "--staging-web-search-only cannot be combined with other modes"
            )
        try:
            values = staging_web_search_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging web-search configuration")
        return 0
    if args.staging_title_only:
        if any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_openrouter_secrets_rotate_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
                args.staging_chat_pool_enable_only,
                args.staging_chat_pool_disable_only,
            )
        ):
            parser.error("--staging-title-only cannot be combined with other modes")
        try:
            values = staging_title_values(
                legacy,
                read_lines(CONFIG_ROOT / "staging.env"),
                read_lines(CONFIG_ROOT / "production.env"),
            )
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed isolated staging title credential")
        return 0
    if args.staging_chat_pool_enable_only or args.staging_chat_pool_disable_only:
        if (
            args.staging_chat_pool_enable_only and args.staging_chat_pool_disable_only
        ) or any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_openrouter_secrets_rotate_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
            )
        ):
            parser.error(
                "staging chat pool enable/disable cannot be combined with other modes"
            )
        enabled = args.staging_chat_pool_enable_only
        staging = assign(
            read_lines(CONFIG_ROOT / "staging.env"),
            staging_chat_pool_values(enabled=enabled),
        )
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print(f"{'enabled' if enabled else 'disabled'} staging chat blank pool")
        return 0
    if args.staging_openrouter_secrets_rotate_only:
        if any(
            (
                args.production_codex_only,
                args.staging_codex_too,
                args.staging_langfuse_only,
                args.staging_openrouter_only,
                args.staging_openrouter_disable_only,
                args.staging_chat_capacity_only,
                args.staging_chat_alerts_only,
            )
        ):
            parser.error(
                "--staging-openrouter-secrets-rotate-only cannot be combined "
                "with other modes"
            )
        try:
            staging = assign(
                read_lines(CONFIG_ROOT / "staging.env"),
                rotate_staging_openrouter_secret_values(
                    read_lines(CONFIG_ROOT / "staging.env")
                ),
            )
        except ValueError as error:
            parser.error(str(error))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("rotated staging OpenRouter encryption and tracking secrets")
        return 0
    if args.staging_chat_capacity_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_openrouter_disable_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-chat-capacity-only cannot be combined with other modes"
            )
        existing = read_lines(CONFIG_ROOT / "staging.env")
        staging = assign(existing, staging_chat_capacity_configuration(existing))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("configured qualified staging chat capacity")
        return 0
    if args.staging_chat_alerts_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_openrouter_disable_only
        ):
            parser.error(
                "--staging-chat-alerts-only cannot be combined with other modes"
            )
        try:
            values = staging_chat_alert_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging chat alert destinations")
        return 0
    if args.staging_openrouter_disable_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_openrouter_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-openrouter-disable-only cannot be combined with other modes"
            )
        staging = without_staging_openrouter(read_lines(CONFIG_ROOT / "staging.env"))
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("disabled server-funded staging OpenRouter chat")
        return 0
    if args.staging_openrouter_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_langfuse_only
            or args.staging_chat_alerts_only
        ):
            parser.error(
                "--staging-openrouter-only cannot be combined with Codex modes"
            )
        try:
            values = staging_openrouter_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging OpenRouter chat credential")
        return 0
    if args.staging_langfuse_only:
        if (
            args.production_codex_only
            or args.staging_codex_too
            or args.staging_openrouter_only
            or args.staging_chat_alerts_only
        ):
            parser.error("--staging-langfuse-only cannot be combined with Codex modes")
        try:
            values = staging_langfuse_values(legacy)
        except ValueError as error:
            parser.error(str(error))
        staging = assign(read_lines(CONFIG_ROOT / "staging.env"), values)
        write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
        print("installed staging Langfuse credentials")
        return 0
    if not args.codex_jobs_namespace:
        parser.error("--codex-jobs-namespace is required")
    required = {
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
    }
    missing = sorted(required - legacy.keys())
    if missing:
        parser.error("legacy environment is missing: " + ", ".join(missing))

    if args.production_codex_only:
        codex_values = production_codex_values(legacy, args.codex_jobs_namespace)
        production = assign(
            read_lines(CONFIG_ROOT / "production.env"),
            codex_values,
        )
        write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
        production_cron = assign(
            read_lines(CONFIG_ROOT / "production-cron.env"),
            codex_values,
        )
        write_env(CONFIG_ROOT / "production-cron.env", production_cron, "pwc-cron")
        if args.staging_codex_too:
            staging = assign(
                read_lines(CONFIG_ROOT / "staging.env"),
                {
                    **production_codex_values(
                        legacy, args.codex_jobs_namespace, scheduled=False
                    ),
                    "PWC_CODEX_JOBS_API_URL": (
                        "https://staging.paperswithcode.co/api/v1"
                    ),
                    "PWC_GITHUB_TOKEN": decoded_value(legacy["PWC_GITHUB_TOKEN"]),
                },
            )
            write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
            print("installed production, CRON, and staging Codex credentials")
        else:
            print("installed production and CRON Codex credentials")
        return 0
    if args.staging_codex_too:
        parser.error("--staging-codex-too requires --production-codex-only")

    current_production = read_lines(CONFIG_ROOT / "production.env")
    current_staging = read_lines(CONFIG_ROOT / "staging.env")
    current_cron = read_lines(CONFIG_ROOT / "production-cron.env")
    current_trending_cron = read_lines(CONFIG_ROOT / "trending-cron.env")
    staging_db_password = existing_or_random(current_staging, "PWC_DB_PASSWORD")
    staging_jwt = existing_or_random(current_staging, "PWC_JWT_SECRET")
    backup_db_password = existing_or_random(
        current_cron, "PWC_POSTGRES_BACKUP_DB_PASSWORD"
    )
    trending_db_password = existing_or_random(
        current_trending_cron, "PWC_TRENDING_DB_PASSWORD"
    )
    production_jwt = decoded_value(legacy["PWC_JWT_SECRET"])
    session_private_key, session_public_key = shared_session_keys(
        current_production, current_staging
    )
    oauth_credential_secret = shared_oauth_credential_secret(
        current_production, current_staging
    )
    shared_auth = {
        "PWC_AUTH_AUTHORITY_ORIGIN": "https://paperswithcode.co",
        "PWC_AUTH_RETURN_ORIGINS": (
            "https://paperswithcode.co,https://staging.paperswithcode.co"
        ),
        "PWC_SHARED_SESSION_COOKIE_DOMAIN": ".paperswithcode.co",
        "PWC_SHARED_SESSION_COOKIE_NAME": "pwc_shared_session",
        "PWC_SESSION_VERIFICATION_PUBLIC_KEY": session_public_key,
        "PWC_HF_OAUTH_CREDENTIAL_SECRET": oauth_credential_secret,
    }
    shared_roles = shared_role_values(current_production, current_staging, legacy)

    production = assign(
        legacy,
        {
            **shared_auth,
            **shared_roles,
            "PWC_CATALOG_MUTATIONS_ENABLED": "true",
            "PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false",
            "PWC_CHAT_ENABLED": "false",
            "PWC_CHAT_AGENT_CWD": ("/var/lib/paperswithcode/production/chat-agent"),
            "PWC_CHAT_RECOVERY_SPOOL_DIR": (
                "/var/lib/paperswithcode/production/chat-recovery-spool"
            ),
            "PWC_CHAT_REQUIRE_AUTH": "true",
            "PWC_CODEX_ADD_EVALS_SPOOL_DIR": (
                "/var/lib/paperswithcode/production/recovery-spool"
            ),
            **production_codex_values(
                legacy, args.codex_jobs_namespace, scheduled=True
            ),
            "PWC_CRON_ENABLED": "true",
            "PWC_CRON_LOCK_DIR": "/var/lib/paperswithcode/production/cron-locks",
            "PWC_CRON_LOG_DIR": "/var/lib/paperswithcode/production/cron-logs",
            "PWC_DB_SEARCH_PATH": "public",
            "PWC_ENVIRONMENT": "production",
            "PWC_FRONTEND_DIST_DIR": (
                "/srv/paperswithcode/environments/production/current/frontend-dist"
            ),
            "PWC_RUNTIME_DATA_DIR": "/var/lib/paperswithcode/production",
            "PWC_SESSION_COOKIE_DOMAIN": "",
            "PWC_SESSION_COOKIE_NAME": "pwc_session",
            "PWC_SESSION_SIGNING_PRIVATE_KEY": session_private_key,
            "PWC_THUMBNAIL_CACHE_DIR": ("/var/lib/paperswithcode/shared/thumbnails"),
            "PWC_THUMBNAIL_MUTATIONS_ENABLED": "false",
            "PWC_THUMBNAIL_TEMP_CACHE_DIR": (
                "/var/lib/paperswithcode/shared/thumbnails"
            ),
            "UVICORN_HOST": "127.0.0.1",
            "UVICORN_PORT": "8000",
            "WEB_CONCURRENCY": "2",
        },
    )
    # The optional hot-queue credential is automation-only. Keep it out of the
    # application environment and install it only in the CRON overlay below.
    production = without_cron_only_credentials(production)

    staging = {
        key: line
        for key, line in legacy.items()
        if key not in STAGING_EXCLUDED_KEYS
        and not key.startswith(STAGING_EXCLUDED_PREFIXES)
    }
    staging.update(staging_runtime_passthrough(current_staging))
    staging = assign(
        staging,
        {
            **shared_auth,
            **shared_roles,
            **production_codex_values(
                legacy, args.codex_jobs_namespace, scheduled=False
            ),
            "PWC_CATALOG_MUTATIONS_ENABLED": "false",
            "PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false",
            "PWC_CHAT_AGENT_CWD": "/var/lib/paperswithcode/staging/chat-agent",
            "PWC_CHAT_ENABLED": "true",
            "PWC_CHAT_GATEWAY_URL": (
                "https://chat-gateway-staging.paperswithcode.co/"
                "api/internal/chat-gateway"
            ),
            "PWC_CHAT_HF_BILL_TO": "huggingface",
            "PWC_CHAT_OPENROUTER_API_KEY": decoded_value(
                legacy["PWC_OPENROUTER_API_KEY"]
            ),
            **staging_openrouter_accounting_values(current_staging),
            "PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED": "true",
            "PWC_CHAT_RECOVERY_SPOOL_DIR": (
                "/var/lib/paperswithcode/staging/chat-recovery-spool"
            ),
            "PWC_CHAT_REQUIRE_AUTH": "true",
            "PWC_CODEX_ADD_EVALS_ENABLED": "false",
            "PWC_CODEX_ADD_EVALS_SPOOL_DIR": (
                "/var/lib/paperswithcode/staging/recovery-spool"
            ),
            "PWC_CODEX_ADD_EVALS_WORK_DIR": (
                "/var/lib/paperswithcode/staging/codex-work"
            ),
            "PWC_CODEX_JOBS_API_URL": ("https://staging.paperswithcode.co/api/v1"),
            "PWC_CRON_ENABLED": "false",
            "PWC_CRON_LOCK_DIR": "/var/lib/paperswithcode/staging/cron-locks",
            "PWC_CRON_LOG_DIR": "/var/lib/paperswithcode/staging/cron-logs",
            "PWC_DB_PASSWORD": staging_db_password,
            "PWC_DB_SEARCH_PATH": "staging,public",
            "PWC_DB_USER": "pwc_staging",
            "PWC_ENVIRONMENT": "staging",
            "PWC_FRONTEND_DIST_DIR": (
                "/srv/paperswithcode/environments/staging/current/frontend-dist"
            ),
            "PWC_GITHUB_TOKEN": decoded_value(legacy["PWC_GITHUB_TOKEN"]),
            "PWC_JWT_SECRET": staging_jwt,
            "PWC_PRODUCTION_JWT_FINGERPRINT": hashlib.sha256(
                production_jwt.encode()
            ).hexdigest(),
            "PWC_RUNTIME_DATA_DIR": "/var/lib/paperswithcode/staging",
            "PWC_SESSION_COOKIE_DOMAIN": "",
            "PWC_SESSION_COOKIE_NAME": "pwc_staging_session",
            "PWC_THUMBNAIL_CACHE_DIR": ("/var/lib/paperswithcode/shared/thumbnails"),
            "PWC_THUMBNAIL_MUTATIONS_ENABLED": "false",
            "PWC_THUMBNAIL_TEMP_CACHE_DIR": (
                "/var/lib/paperswithcode/shared/thumbnails"
            ),
            "UVICORN_HOST": "127.0.0.1",
            "UVICORN_PORT": "8001",
            "WEB_CONCURRENCY": "5",
        },
    )
    staging = without_cron_only_credentials(staging)

    cron = cron_passthrough_credentials(legacy, current_cron)
    cron.update(
        {
            key: line
            for key, line in current_cron.items()
            if key.startswith("PWC_TRENDING_PIN_")
        }
    )
    cron = assign(
        cron,
        {
            "HF_HOME": "/var/lib/paperswithcode/production/hf-cache",
            # Bucket uploads use Xet for database-sized objects. The
            # organization-authorized Hub token is required for that path.
            "PWC_POSTGRES_BACKUP_HF_TOKEN": decoded_value(legacy["PWC_HF_TOKEN"]),
            "PWC_POSTGRES_BACKUP_DB_PASSWORD": backup_db_password,
            "PWC_POSTGRES_BACKUP_DB_USER": "pwc_backup",
            "PWC_POSTGRES_BACKUP_LOCAL_KEEP_COUNT": "3",
            "PWC_POSTGRES_BACKUP_REMOTE_KEEP_COUNT": "30",
        },
    )

    trending_cron = trending_cron_values(
        legacy,
        {
            **{
                key: line
                for key, line in current_cron.items()
                if key.startswith("PWC_TRENDING_PIN_")
            },
            **current_trending_cron,
        },
        password=trending_db_password,
    )

    write_env(CONFIG_ROOT / "production.env", production, "pwc-production")
    write_env(CONFIG_ROOT / "staging.env", staging, "pwc-staging")
    write_env(CONFIG_ROOT / "production-cron.env", cron, "pwc-cron")
    write_env(
        CONFIG_ROOT / "trending-cron.env",
        trending_cron,
        "pwc-cron-trending",
    )
    # pwc-cron is deliberately not in the pwc-production group: that group can
    # read production.env. install_host_layout.restrict_cron_access() grants the
    # directory traversal CRON needs instead.
    print("installed production, staging, and CRON environment files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
