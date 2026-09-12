"""Explicit CI-only image publication entry point.

This is never imported or called by the web service. The emitted immutable image
ID is copied into a later staging release manifest before allocation is enabled.
"""

import json
import os
import subprocess
from pathlib import Path

import modal

from backend.chat_sandbox_worker.contract import IMAGE_PUBLISH_NAME, MODAL_APP_NAME
from backend.chat_sandbox_worker.executor_release_manifest import (
    signed_release_manifest,
)
from backend.chat_sandbox_worker.image import app, image, with_executor_binary

REPOSITORY = Path(__file__).resolve().parents[2]


def main() -> int:
    signing_key = os.environ.get("PWC_CHAT_EXECUTOR_MANIFEST_SIGNING_KEY_FILE")
    release_id = os.environ.get("PWC_CHAT_EXECUTOR_RELEASE_ID")
    if not signing_key or not release_id:
        raise RuntimeError("Executor manifest signing configuration is unavailable")
    target_dir = Path(
        os.environ.get("PWC_EXECUTOR_CARGO_TARGET_DIR", "/tmp/pwc-executor-target")
    )
    subprocess.run(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--manifest-path",
            str(REPOSITORY / "executor_transport/Cargo.toml"),
            "--bin",
            "environment",
        ],
        cwd=REPOSITORY,
        env={**os.environ, "CARGO_TARGET_DIR": str(target_dir)},
        check=True,
    )
    environment_binary = target_dir / "release/environment"
    release_image = with_executor_binary(image, environment_binary)
    modal.App.lookup(MODAL_APP_NAME, create_if_missing=True)
    with app.run():
        built = release_image.build(app)
        built.publish(IMAGE_PUBLISH_NAME)
    if not built.object_id:
        raise RuntimeError("Modal image publication returned no immutable image ID")
    print(
        json.dumps(
            signed_release_manifest(
                image_id=built.object_id,
                environment_binary=environment_binary,
                signing_key_file=Path(signing_key),
                release_id=release_id,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
