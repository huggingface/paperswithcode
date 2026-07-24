#!/usr/bin/env python3
"""Start one backend with identity derived from its immutable manifest."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from deploy.release import validate_manifest
except ModuleNotFoundError:
    from release import validate_manifest  # type: ignore[no-redef]

release = Path.cwd()
manifest = validate_manifest(release)
os.environ["PWC_RELEASE_ID"] = manifest["release_id"]
runtime = manifest["chat_runtime"]
os.environ["PWC_CHAT_ENABLED"] = "true" if runtime["enabled"] else "false"
os.environ["PWC_CHAT_DEFAULT_BACKEND"] = runtime["default_backend"]
os.environ["PWC_CHAT_NEW_CHAT_MODAL_PERCENTAGE"] = str(
    runtime["new_chat_modal_percentage"]
)
os.environ["PWC_CHAT_MODAL_IMAGE_VERSION"] = runtime["modal_image_version"]
os.environ["PWC_CHAT_PWC_CLI_VERSION"] = runtime["pwc_cli_version"]
os.environ["PWC_CHAT_WORKER_CONTRACT_VERSION"] = runtime["worker_contract_version"]
os.environ["PWC_CHAT_SYSTEM_PROMPT_SHA256"] = runtime["system_prompt_sha256"]
expected_dist = (release / manifest["frontend_entrypoint"]).parent
configured_dist = Path(os.environ["PWC_FRONTEND_DIST_DIR"]).resolve()
if configured_dist != expected_dist.resolve():
    raise SystemExit("configured frontend distribution does not match current release")
python = Path("/srv/paperswithcode/.venv/bin/python")
os.execv(python, [str(python), "-m", "uvicorn", "backend.main:app"])
