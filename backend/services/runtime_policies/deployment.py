"""Deployment identity, environment, release, and frontend validation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from backend.config import Settings


_ASSET_RE = re.compile(
    r"""(?:src|href)=["'](?P<path>/assets/[^"'?#]+\.(?:js|css))(?:[?#][^"']*)?["']"""
)


_RELEASE_ROOT = Path("/srv/paperswithcode/releases")


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


def validate_deployment_identity(settings: Settings) -> None:
    """Validate the deployed environment and immutable release identity."""

    if settings.environment not in {"production", "staging"}:
        raise RuntimeError("PWC_ENVIRONMENT must be production or staging")
    if not settings.release_id or settings.release_id == "development":
        raise RuntimeError("PWC_RELEASE_ID is required")


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
