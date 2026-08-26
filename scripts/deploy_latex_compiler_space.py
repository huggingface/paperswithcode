"""Build a private staging compiler image, pin its registry digest, then pause it.

The Docker Space is an image builder only. PwC never sends compiler requests to
the Space endpoint; each request starts a fresh Hugging Face Sandbox from the
returned immutable registry image instead.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from huggingface_hub import HfApi, get_token
from latex_compiler_contract import STAGING_SANDBOX_COMPILER_NAMESPACE

ROOT = Path(__file__).resolve().parents[1]
SPACE_SOURCE = ROOT / "latex_compiler_space"
CONTRACT_SOURCE = ROOT / "latex_compiler_contract"
CONFIRMATION = "DEPLOY_PRIVATE_LATEX_COMPILER_SPACE"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SPACE_NAME = re.compile(r"^pwc-latex-compiler-[a-z0-9-]+-staging$")


@dataclass(frozen=True)
class CompilerImageIdentity:
    space_id: str
    source_revision: str
    image: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space", required=True, help="Private staging builder Space ID"
    )
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def _validate_space_id(space_id: str) -> str:
    parts = space_id.split("/")
    if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Space ID must be namespace/name")
    namespace, name = parts
    if namespace != STAGING_SANDBOX_COMPILER_NAMESPACE:
        raise ValueError(
            "This staging-only image builder requires the approved staging namespace"
        )
    if "production" in space_id.lower():
        raise ValueError("This staging-only image builder refuses production Space IDs")
    if not _SPACE_NAME.fullmatch(name):
        raise ValueError(
            "This staging-only image builder requires a pwc-latex-compiler-*-staging ID"
        )
    return space_id


def compiler_image_reference(space_id: str, digest: str) -> str:
    """Turn an authenticated OCI manifest digest into the Sandbox image ref."""
    space_id = _validate_space_id(space_id)
    if not _DIGEST.fullmatch(digest):
        raise ValueError("Compiler image must use an immutable sha256 digest")
    return f"registry.hf.space/{space_id.replace('/', '-')}@{digest}"


def _assemble(destination: Path) -> None:
    for name in ("Dockerfile", "README.md", "requirements.txt"):
        shutil.copy2(SPACE_SOURCE / name, destination / name)
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(SPACE_SOURCE, destination / "latex_compiler_space", ignore=ignored)
    shutil.copytree(
        CONTRACT_SOURCE, destination / "latex_compiler_contract", ignore=ignored
    )


def _wait_for_running_builder(
    api: HfApi,
    space_id: str,
    *,
    timeout_seconds: int = 900,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        stage = str(api.get_space_runtime(space_id).stage).upper()
        if stage == "RUNNING":
            return
        if stage in {"BUILD_ERROR", "RUNTIME_ERROR", "ERROR"}:
            raise RuntimeError("Private compiler image builder failed")
        sleep(5)
    raise RuntimeError("Private compiler image builder did not become ready")


def _resolve_registry_digest(space_id: str) -> str:
    """Read only the authenticated OCI manifest header; never emit auth state."""
    token = get_token()
    if not token:
        raise RuntimeError("An authenticated Hugging Face identity is required")
    repository = space_id.replace("/", "-")
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.head(
            f"https://registry.hf.space/v2/{repository}/manifests/latest",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": (
                    "application/vnd.oci.image.index.v1+json,"
                    "application/vnd.docker.distribution.manifest.v2+json"
                ),
            },
        )
        response.raise_for_status()
    digest = response.headers.get("docker-content-digest", "")
    if not _DIGEST.fullmatch(digest):
        raise RuntimeError(
            "Private compiler registry did not return an immutable digest"
        )
    return digest


def provision_compiler_image(
    space_id: str,
    *,
    api: HfApi,
    wait_for_runtime: Callable[[HfApi, str], None] = _wait_for_running_builder,
    resolve_registry_digest: Callable[[str], str] = _resolve_registry_digest,
) -> CompilerImageIdentity:
    """Build exactly once, derive an OCI digest, and leave the builder paused."""
    space_id = _validate_space_id(space_id)
    api.create_repo(
        repo_id=space_id,
        repo_type="space",
        space_sdk="docker",
        private=True,
        exist_ok=True,
    )
    try:
        api.update_repo_settings(repo_id=space_id, repo_type="space", private=True)
        if not bool(getattr(api.space_info(repo_id=space_id), "private", False)):
            raise RuntimeError(
                "Private compiler image builder visibility could not be verified"
            )
        with tempfile.TemporaryDirectory(
            prefix="pwc-latex-image-builder-"
        ) as temporary:
            assembled = Path(temporary)
            _assemble(assembled)
            commit = api.upload_folder(
                repo_id=space_id,
                repo_type="space",
                folder_path=assembled,
                commit_message="Build private PwC LaTeX compiler image",
            )
        source_revision = str(getattr(commit, "oid", ""))
        if not source_revision:
            source_revision = str(getattr(api.space_info(repo_id=space_id), "sha", ""))
        if not source_revision:
            raise RuntimeError("Private compiler image source revision is unavailable")
        wait_for_runtime(api, space_id)
        image = compiler_image_reference(space_id, resolve_registry_digest(space_id))
    finally:
        # A paused private builder cannot receive an endpoint request or retain
        # an always-on process. Sandboxes can still pull its pinned OCI image.
        api.pause_space(repo_id=space_id)
    return CompilerImageIdentity(
        space_id=space_id,
        source_revision=source_revision,
        image=image,
    )


def main() -> None:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION} to build the private image")
    identity = provision_compiler_image(args.space, api=HfApi())
    print(
        json.dumps(
            {
                "image": identity.image,
                "source_revision": identity.source_revision,
                "space": identity.space_id,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
