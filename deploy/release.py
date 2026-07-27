"""Release manifest and immutable filesystem helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.chat_sandbox_worker.contract import (
    DEFAULT_BACKEND,
    MODAL_IMAGE_ID,
    NEW_CHAT_MODAL_PERCENTAGE,
    PWC_CLI_VERSION,
    WORKER_CONTRACT_VERSION,
)
from backend.services.chat_runtime_contract import require_immutable_image_id

ENVIRONMENTS = ("production", "staging")
FEATURE_CONTRACT_VERSION = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_features(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
        # Staging inherits production capabilities and layers preview features
        # such as chat on top.
        "codex_add_evals": True,
        "codex_enrich_paper": True,
    }


def _profile_features_v2(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
        "codex_add_evals": False,
        "codex_enrich_paper": False,
    }


def _profile_features_v3(environment: str) -> dict[str, bool]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return {
        "chat": environment == "staging",
        "codex_add_evals": environment == "production",
        "codex_enrich_paper": environment == "production",
    }


def _profile_features_for_version(environment: str, version: int) -> dict[str, bool]:
    if version == 2:
        return _profile_features_v2(environment)
    if version == 3:
        return _profile_features_v3(environment)
    if version == FEATURE_CONTRACT_VERSION:
        return profile_features(environment)
    raise ValueError("unsupported release feature contract version")


def chat_runtime(
    environment: str, descriptor: dict[str, object] | None = None
) -> dict[str, object]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    if environment == "production":
        return {
            "enabled": False,
            "new_chat_modal_percentage": 0,
            "default_backend": "local_mcp",
            "modal_image_version": "",
            "pwc_cli_version": "",
            "worker_contract_version": "",
            "system_prompt_sha256": "",
        }
    if descriptor is not None:
        return descriptor
    from backend.chat_sandbox_worker.prompt import sha256

    return {
        "enabled": True,
        "new_chat_modal_percentage": NEW_CHAT_MODAL_PERCENTAGE,
        "default_backend": DEFAULT_BACKEND,
        "modal_image_version": MODAL_IMAGE_ID,
        "pwc_cli_version": PWC_CLI_VERSION,
        "worker_contract_version": WORKER_CONTRACT_VERSION,
        "system_prompt_sha256": sha256(),
    }


def release_id(git_sha: str, environment: str) -> str:
    if len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
        raise ValueError("git_sha must be a full lowercase SHA-1")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported environment: {environment}")
    return f"{git_sha[:12]}-{environment}"


def build_manifest(
    git_sha: str,
    environment: str,
    *,
    chat_descriptor: dict[str, object] | None = None,
) -> dict[str, object]:
    features = profile_features(environment)
    return {
        "release_id": release_id(git_sha, environment),
        "git_sha": git_sha,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_profile": environment,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "backend_features": features,
        "frontend_features": features,
        "chat_runtime": chat_runtime(environment, chat_descriptor),
        "frontend_entrypoint": "frontend-dist/index.html",
    }


def validate_manifest(release_dir: Path, environment: str | None = None) -> dict:
    manifest_path = release_dir / "release.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_required = {
        "release_id",
        "git_sha",
        "built_at",
        "build_profile",
        "backend_features",
        "frontend_features",
        "frontend_entrypoint",
    }
    versioned_required = legacy_required | {"feature_contract_version"}
    bridge_required = versioned_required | {"chat_runtime"}
    profile = manifest.get("build_profile")
    if set(manifest) == legacy_required:
        expected = {"chat": profile == "staging"}
    elif set(manifest) == versioned_required:
        expected = _profile_features_for_version(
            profile, manifest["feature_contract_version"]
        )
    elif set(manifest) == bridge_required:
        expected = _profile_features_for_version(
            profile, manifest["feature_contract_version"]
        )
    else:
        raise ValueError("release.json has an unexpected schema")
    if environment is not None and profile != environment:
        raise ValueError("release profile does not match target environment")
    if (
        manifest["backend_features"] != expected
        or manifest["frontend_features"] != expected
    ):
        raise ValueError("release feature manifests do not match the build profile")
    if manifest["release_id"] != release_id(manifest["git_sha"], profile):
        raise ValueError("release ID does not match SHA and profile")
    if manifest["frontend_entrypoint"] != "frontend-dist/index.html":
        raise ValueError("unsupported frontend entrypoint")
    runtime = manifest.get("chat_runtime")
    if runtime is None:
        return _validate_release_files(release_dir, manifest, expected)
    if not isinstance(runtime, dict) or set(runtime) != {
        "enabled",
        "new_chat_modal_percentage",
        "default_backend",
        "modal_image_version",
        "pwc_cli_version",
        "worker_contract_version",
        "system_prompt_sha256",
    }:
        raise ValueError("release chat_runtime has an unexpected schema")
    if profile == "production":
        if runtime != chat_runtime("production"):
            raise ValueError("production release contains an active chat runtime")
    else:
        percentage = runtime["new_chat_modal_percentage"]
        if not isinstance(percentage, int) or not 0 <= percentage <= 100:
            raise ValueError("chat runtime rollout percentage is invalid")
        if runtime["default_backend"] not in {"local_mcp", "modal_cli"}:
            raise ValueError("chat runtime default backend is invalid")
        if percentage == 0 and runtime["default_backend"] != "local_mcp":
            raise ValueError("zero-percent rollout must default to local_mcp")
        if percentage == 100 and runtime["default_backend"] != "modal_cli":
            raise ValueError("full rollout must default to modal_cli")
        for key in (
            "pwc_cli_version",
            "worker_contract_version",
        ):
            if not isinstance(runtime[key], str) or not runtime[key]:
                raise ValueError(f"chat runtime {key} is required")
        require_immutable_image_id(runtime["modal_image_version"])
        prompt_hash = runtime["system_prompt_sha256"]
        if (
            not isinstance(prompt_hash, str)
            or len(prompt_hash) != 64
            or any(character not in "0123456789abcdef" for character in prompt_hash)
        ):
            raise ValueError("chat runtime system prompt hash is invalid")
        if runtime["enabled"] is not True:
            raise ValueError("staging chat runtime must be enabled")
    return _validate_release_files(release_dir, manifest, expected)


def _validate_release_files(
    release_dir: Path, manifest: dict, expected: dict[str, bool]
) -> dict:
    features = json.loads(
        (release_dir / "frontend-dist" / "features.json").read_text(encoding="utf-8")
    )
    if features != expected:
        raise ValueError("features.json does not match release.json")
    index = release_dir / manifest["frontend_entrypoint"]
    html = index.read_text(encoding="utf-8")
    if "/src/main.tsx" in html or "/assets/" not in html:
        raise ValueError("release frontend shell is not a built asset bundle")
    if not (release_dir / "backend" / "main.py").is_file():
        raise ValueError("release backend is missing")
    return manifest


def atomic_symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.new-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


@dataclass(frozen=True)
class ReleasePointers:
    current: Path | None
    previous: Path | None


def read_pointers(environment_root: Path) -> ReleasePointers:
    def target(name: str) -> Path | None:
        link = environment_root / name
        return link.resolve(strict=False) if link.is_symlink() else None

    return ReleasePointers(current=target("current"), previous=target("previous"))
