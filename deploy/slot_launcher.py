#!/usr/bin/env python3
"""Neutral host launcher for one immutable environment/slot pair."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from deploy.release import ENVIRONMENTS, validate_manifest
    from deploy.runtime import runtime_id, runtime_manifest
except ModuleNotFoundError:
    from release import ENVIRONMENTS, validate_manifest  # type: ignore[no-redef]
    from runtime import runtime_id, runtime_manifest  # type: ignore[no-redef]

APP_ROOT = Path(os.environ.get("PWC_DEPLOY_APP_ROOT", "/srv/paperswithcode"))
EXTERNAL_PI_SLOT_PORTS = {
    "staging": {"blue": 8766, "green": 8767},
    "production": {"blue": 8776, "green": 8777},
}


def resolve_slot(environment: str, slot: str) -> tuple[Path, Path, dict]:
    if environment not in ENVIRONMENTS or slot not in {"blue", "green"}:
        raise ValueError("invalid deployment environment or slot")
    slot_root = APP_ROOT / "environments" / environment / "slots" / slot
    release_link = slot_root / "release"
    if not release_link.is_symlink():
        raise ValueError("slot release pointer is missing")
    release = release_link.resolve(strict=True)
    manifest = validate_manifest(release, environment)
    runtime = APP_ROOT / "runtimes" / runtime_id(release)
    runtime_manifest(runtime)
    return release, runtime, manifest


def configure_release(manifest: dict, release: Path, environment: str) -> None:
    features = manifest["backend_features"]
    runtime = manifest.get("chat_runtime") or {}
    values = {
        "PWC_FRONTEND_DIST_DIR": str(release / "frontend-dist"),
        "PWC_CHAT_ENABLED": "true" if features.get("chat") else "false",
        "PWC_NATIVE_PDF_READER_ENABLED": (
            "true" if features.get("native_pdf_reader") else "false"
        ),
        "PWC_PAPER_READER_CHAT_ENABLED": (
            "true" if features.get("paper_reader_chat") else "false"
        ),
        "PWC_PAPER_READER_SELECTION_ENABLED": (
            "true" if features.get("paper_reader_selection") else "false"
        ),
        "PWC_CHAT_PAPER_MENTIONS_ENABLED": (
            "true" if features.get("chat") else "false"
        ),
        "PWC_CHAT_HF_CATALOG_ENABLED": ("true" if features.get("chat") else "false"),
        "PWC_CODEX_ADD_EVALS_ENABLED": (
            "true" if features.get("codex_add_evals") else "false"
        ),
        "PWC_CODEX_ENRICH_PAPER_ENABLED": (
            "true" if features.get("codex_enrich_paper") else "false"
        ),
        "PWC_CODEX_JOBS_ENABLED": (
            "true"
            if features.get("codex_add_evals") or features.get("codex_enrich_paper")
            else "false"
        ),
    }
    if runtime:
        values.update(
            {
                "PWC_CHAT_DEFAULT_BACKEND": str(runtime["default_backend"]),
                "PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE": str(
                    runtime["new_chat_modal_percentage"]
                ),
                "PWC_CHAT_MODAL_IMAGE_VERSION": str(runtime["modal_image_version"]),
                "PWC_CHAT_PWC_CLI_VERSION": str(runtime["pwc_cli_version"]),
                "PWC_CHAT_WORKER_CONTRACT_VERSION": str(
                    runtime["worker_contract_version"]
                ),
                "PWC_CHAT_SYSTEM_PROMPT_SHA256": str(runtime["system_prompt_sha256"]),
                "PWC_CHAT_DEFAULT_AGENT_HARNESS": str(
                    runtime.get("default_agent_harness", "claude")
                ),
                "PWC_CHAT_NEW_SESSION_PI_PERCENTAGE": str(
                    runtime.get("new_session_pi_percentage", 0)
                ),
                "PWC_CHAT_CLAUDE_SDK_VERSION": str(
                    runtime.get("claude_sdk_version", "")
                ),
                "PWC_CHAT_PI_VERSION": str(runtime.get("pi_version", "")),
                "PWC_CHAT_PI_RUNTIME_ENABLED": (
                    "true"
                    if "pi" in runtime.get("supported_agent_harnesses", [])
                    else "false"
                ),
                "PWC_CHAT_PI_SOURCE_COMMIT": str(runtime.get("pi_source_commit", "")),
                "PWC_CHAT_PI_NODE_VERSION": str(runtime.get("pi_node_version", "")),
                "PWC_CHAT_PI_NODE_SHA256": str(runtime.get("pi_node_sha256", "")),
                "PWC_CHAT_RESTRICTED_HF_CLI_VERSION": str(
                    runtime.get("restricted_hf_cli_version", "")
                ),
            }
        )
        posterly_release = runtime.get("posterly_enabled") is True
        artifact_foundation = (
            environment == "staging" and runtime.get("enabled") is True
        )
        values.update(
            {
                "PWC_CHAT_ARTIFACTS_ENABLED": str(artifact_foundation).lower(),
                "PWC_CHAT_POSTERLY_ENABLED": str(posterly_release).lower(),
                "PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED": "false",
            }
        )
        if artifact_foundation:
            values["PWC_CHAT_ARTIFACT_STORAGE_BACKEND"] = "hf_bucket"
            values["PWC_CHAT_ARTIFACT_HF_BUCKET_ID"] = str(
                runtime["posterly_artifact_bucket_id"]
            )
    os.environ.update(values)


def configure_external_pi_slot(environment: str, slot: str) -> None:
    """Bind a deployed backend slot to its environment-isolated worker."""
    try:
        port = EXTERNAL_PI_SLOT_PORTS[environment][slot]
    except KeyError as error:
        raise ValueError("invalid deployment environment or slot") from error
    os.environ.update(
        {
            "PWC_CHAT_EXTERNAL_PI_WORKER_ID": f"{environment}-{slot}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_URL": f"http://127.0.0.1:{port}",
            "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION": "external-pi-v1",
            "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "32",
        }
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: slot_launcher.py ENVIRONMENT SLOT")
    environment, slot = sys.argv[1:]
    release, runtime, manifest = resolve_slot(environment, slot)
    socket_path = (
        APP_ROOT / "environments" / environment / "slots" / slot / "backend.sock"
    )
    os.environ.update(
        {
            "PWC_ENVIRONMENT": environment,
            "PWC_DEPLOYMENT_SLOT": slot,
            "PWC_RELEASE_ID": manifest["release_id"],
            "PWC_RUNTIME_ID": runtime.name,
            "PWC_BACKEND_SOCKET": str(socket_path),
            "UVICORN_FD": "3",
        }
    )
    configure_release(manifest, release, environment)
    configure_external_pi_slot(environment, slot)
    python = runtime / "bin" / "python"
    os.chdir(release)
    os.execv(
        str(python),
        [str(python), "-m", "uvicorn", "backend.main:app", "--fd", "3"],
    )


if __name__ == "__main__":
    main()
