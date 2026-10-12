"""Fail-closed validation for deployed environment and release configuration."""

from __future__ import annotations

import base64
import grp
import json
import stat
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from backend.config import Settings
from backend.chat_sandbox_worker.executor_protocol import PROTOCOL as EXECUTOR_CONTRACT
from backend.services.chat_runtime_contract import (
    EXTERNAL_PI_WORKER_CONTRACT,
    require_external_admission_contract,
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
from backend.services.runtime_policies.deployment import (
    validate_deployed_mutation_policy,
    validate_deployment_identity,
    validate_environment_policy,
    validate_frontend_dist,
    validate_release_manifest,
)
from backend.services.runtime_policies.auth import (
    validate_auth_configuration,
)
from backend.services.runtime_policies.storage import (
    validate_runtime_storage,
)
from backend.services.runtime_policies.codex_jobs import (
    validate_codex_jobs_configuration,
)
from backend.services.runtime_policies.chat_runtime_identity import (
    validate_chat_runtime_descriptor,
)
from backend.services.runtime_policies.chat_provider import (
    _validate_chat_openrouter_policy,
    validate_chat_provider_policy,
    validate_chat_scope_guardrail_configuration,
)
from backend.services.runtime_policies.chat_runtime_profile import (
    _resolve_chat_runtime_profile as resolve_chat_runtime_profile,
)
from backend.services.runtime_policies.chat_runtime_profile import (
    ChatRuntimeKind,
    ChatRuntimeProfile,
    _EXTERNAL_PI_CAPACITY_POLICIES,
    _EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS,
    _external_pi_capacity_tier,
)
from backend.services.runtime_policies.chat_capacity import (
    _validate_chat_capacity_policy,
    _validate_chat_resource_policy,
)
from backend.services.runtime_policies.chat_budget import (
    _validate_chat_capacity_and_spend_policy,
)
from backend.services.runtime_policies.schema import (
    validate_chat_schema,
    validate_external_worker_reservation_schema,
    validate_qualification_evidence_schema,
)


__all__ = [
    "ChatRuntimeKind",
    "ChatRuntimeProfile",
    "STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE",
    "_EXTERNAL_PI_CAPACITY_POLICIES",
    "_EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS",
    "_external_pi_capacity_tier",
    "_resolve_chat_runtime_profile",
    "_validate_chat_capacity_and_spend_policy",
    "_validate_chat_capacity_policy",
    "_validate_chat_openrouter_policy",
    "_validate_chat_resource_policy",
    "require_external_admission_contract",
    "validate_auth_configuration",
    "validate_chat_capacity_and_spend_policy",
    "validate_chat_provider_policy",
    "validate_chat_runtime_descriptor",
    "validate_chat_schema",
    "validate_chat_scope_guardrail_configuration",
    "validate_codex_jobs_configuration",
    "validate_deployed_mutation_policy",
    "validate_deployment_identity",
    "validate_environment_policy",
    "validate_external_pi_migration_policy",
    "validate_external_worker_reservation_schema",
    "validate_frontend_dist",
    "validate_private_paper_runtime",
    "validate_qualification_evidence_schema",
    "validate_release_manifest",
    "validate_runtime",
    "validate_runtime_storage",
]

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
        if (
            settings.chat_artifacts_enabled
            or settings.chat_artifact_shared_preview_enabled
        ):
            raise RuntimeError(
                "private paper qualification must disable user-facing artifacts"
            )
        return
    if not all(user_paper_flags):
        raise RuntimeError("private paper runtime flags must be coherent")
    _validate_private_paper_qualification_evidence(image=image)


def validate_chat_capacity_and_spend_policy(settings: Settings) -> None:
    """Validate migration controls and the chat capacity policy."""

    profile = validate_external_pi_migration_policy(settings)
    _validate_chat_capacity_and_spend_policy(settings, profile)


def _resolve_chat_runtime_profile(settings: Settings) -> ChatRuntimeProfile:
    """Resolve the runtime profile with this module's admission-contract check."""

    return resolve_chat_runtime_profile(
        settings, require_contract=require_external_admission_contract
    )


def validate_external_pi_migration_policy(settings: Settings) -> ChatRuntimeProfile:
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
        if (
            settings.chat_external_pi_worker_contract_version
            != EXTERNAL_PI_WORKER_CONTRACT
        ):
            raise RuntimeError("external Pi worker identity is invalid")
    if any(executor_switches.values()):
        if settings.chat_sandbox_executor_contract_version != EXECUTOR_CONTRACT:
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
    return _resolve_chat_runtime_profile(settings)


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
    profile = validate_external_pi_migration_policy(settings)
    validate_chat_configuration = validate_chat_runtime_descriptor(settings)
    if validate_chat_configuration:
        validate_chat_provider_policy(settings, include_openrouter=False)
        _validate_chat_capacity_and_spend_policy(settings, profile)
        _validate_chat_openrouter_policy(settings)
    validate_release_manifest(settings)
    validate_deployed_mutation_policy(settings)
    return validate_frontend_dist(settings)
