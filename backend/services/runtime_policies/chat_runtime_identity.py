"""Chat runtime descriptor and immutable execution identity validation."""

from __future__ import annotations

from backend.chat_sandbox_worker.contract import (
    PI_NODE_SHA256,
    PI_NODE_VERSION,
    PI_SOURCE_COMMIT,
    PI_VERSION,
    RESTRICTED_HF_CLI_VERSION,
    SDK_VERSION,
)
from backend.config import Settings
from backend.services.chat_runtime_contract import (
    require_immutable_image_id,
)


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
        settings.chat_session_limit != 500
        or settings.chat_user_byte_limit != 100 * 1024 * 1024
    ):
        raise RuntimeError(
            "chat retention quotas must remain 500 active chats and 100 MB"
        )


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
