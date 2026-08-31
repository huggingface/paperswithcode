#!/usr/bin/env python3
"""Start one backend with identity derived from its immutable manifest."""

from __future__ import annotations

import os
import sys
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE_ROOT))

try:
    from deploy.release import validate_manifest
except ModuleNotFoundError:
    from release import validate_manifest  # type: ignore[no-redef]


def configure_release_environment(release: Path) -> dict:
    manifest = validate_manifest(release)
    features = manifest["backend_features"]
    runtime_data_dir = Path(os.environ["PWC_RUNTIME_DATA_DIR"])
    # Request-path Hub/Xet writes must not share the CRON-owned cache. The host
    # layout provisions this directory for the application service identity.
    hf_cache_dir = runtime_data_dir / "hf-app-cache"
    os.environ.setdefault("HF_HOME", str(hf_cache_dir))
    os.environ.setdefault("HF_XET_CACHE", str(hf_cache_dir / "xet"))
    os.environ["PWC_RELEASE_ID"] = manifest["release_id"]
    os.environ["PWC_GIT_SHA"] = manifest["git_sha"]
    os.environ["PWC_CHAT_ENABLED"] = "true" if features["chat"] else "false"
    os.environ["PWC_NATIVE_PDF_READER_ENABLED"] = (
        "true" if features.get("native_pdf_reader", False) else "false"
    )
    os.environ["PWC_PAPER_READER_CHAT_ENABLED"] = (
        "true" if features.get("paper_reader_chat", False) else "false"
    )
    os.environ["PWC_PAPER_READER_SELECTION_ENABLED"] = (
        "true" if features.get("paper_reader_selection", False) else "false"
    )
    os.environ["PWC_CHAT_PAPER_MENTIONS_ENABLED"] = (
        "true" if features["chat"] else "false"
    )
    os.environ["PWC_CHAT_HF_CATALOG_ENABLED"] = "true" if features["chat"] else "false"
    os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] = (
        "true" if features.get("codex_add_evals", False) else "false"
    )
    os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] = (
        "true" if features.get("codex_enrich_paper", False) else "false"
    )
    os.environ["PWC_CODEX_JOBS_ENABLED"] = (
        "true"
        if features.get("codex_add_evals", False)
        or features.get("codex_enrich_paper", False)
        else "false"
    )
    runtime = manifest.get("chat_runtime")
    if runtime is not None:
        os.environ["PWC_CHAT_DEFAULT_BACKEND"] = runtime["default_backend"]
        os.environ["PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE"] = str(
            runtime["new_chat_modal_percentage"]
        )
        os.environ["PWC_CHAT_MODAL_IMAGE_VERSION"] = runtime["modal_image_version"]
        os.environ["PWC_CHAT_PWC_CLI_VERSION"] = runtime["pwc_cli_version"]
        os.environ["PWC_CHAT_WORKER_CONTRACT_VERSION"] = runtime[
            "worker_contract_version"
        ]
        os.environ["PWC_CHAT_SYSTEM_PROMPT_SHA256"] = runtime["system_prompt_sha256"]
        os.environ["PWC_CHAT_DEFAULT_AGENT_HARNESS"] = runtime.get(
            "default_agent_harness", "claude"
        )
        os.environ["PWC_CHAT_NEW_SESSION_PI_PERCENTAGE"] = str(
            runtime.get("new_session_pi_percentage", 0)
        )
        os.environ["PWC_CHAT_CLAUDE_SDK_VERSION"] = runtime.get(
            "claude_sdk_version", ""
        )
        os.environ["PWC_CHAT_PI_VERSION"] = runtime.get("pi_version", "")
        os.environ["PWC_CHAT_PI_RUNTIME_ENABLED"] = (
            "true" if "pi" in runtime.get("supported_agent_harnesses", []) else "false"
        )
        os.environ["PWC_CHAT_PI_SOURCE_COMMIT"] = runtime.get("pi_source_commit", "")
        os.environ["PWC_CHAT_PI_NODE_VERSION"] = runtime.get("pi_node_version", "")
        os.environ["PWC_CHAT_PI_NODE_SHA256"] = runtime.get("pi_node_sha256", "")
        os.environ["PWC_CHAT_RESTRICTED_HF_CLI_VERSION"] = runtime.get(
            "restricted_hf_cli_version", ""
        )
        posterly_release = runtime.get("posterly_enabled") is True
        artifact_foundation = (
            os.environ.get("PWC_ENVIRONMENT") == "staging"
            and runtime.get("enabled") is True
        )
        os.environ["PWC_CHAT_ARTIFACTS_ENABLED"] = str(artifact_foundation).lower()
        os.environ["PWC_CHAT_POSTERLY_ENABLED"] = str(posterly_release).lower()
        os.environ["PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED"] = str(
            artifact_foundation
        ).lower()
        if artifact_foundation:
            os.environ["PWC_CHAT_ARTIFACT_STORAGE_BACKEND"] = "hf_bucket"
            os.environ["PWC_CHAT_ARTIFACT_HF_BUCKET_ID"] = runtime[
                "posterly_artifact_bucket_id"
            ]
    expected_dist = (release / manifest["frontend_entrypoint"]).parent
    configured_dist = Path(os.environ["PWC_FRONTEND_DIST_DIR"]).resolve()
    if configured_dist != expected_dist.resolve():
        raise SystemExit(
            "configured frontend distribution does not match current release"
        )
    return manifest


def main() -> None:
    configure_release_environment(RELEASE_ROOT)
    arguments = [sys.executable, "-m", "uvicorn", "backend.main:app"]
    if inherited_fd := os.environ.get("UVICORN_FD"):
        arguments.extend(["--fd", inherited_fd])
    os.execv(sys.executable, arguments)


if __name__ == "__main__":
    main()
