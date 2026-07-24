from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import deploy.cli as deploy_cli
from deploy.install_deploy_tools import (
    RUNTIME_CONTRACT_PATHS,
    bundle_runtime_contract,
)
from backend.chat_sandbox_worker.contract import MODAL_IMAGE_ID
from backend.config import Settings
from backend.services.runtime_validation import validate_runtime
from deploy.cli import _chat_descriptor_from_source
from deploy.nginx_validate import validate as validate_nginx
from deploy.release import atomic_symlink, build_manifest, validate_manifest
from deploy.smoke_test import validate_local_bundle


def test_deployment_tool_bundle_includes_chat_runtime_contract(tmp_path: Path):
    repository = Path(__file__).resolve().parents[2]
    staging = tmp_path / "staging"
    source = staging / "deploy"
    source.mkdir(parents=True)
    shutil.copy2(repository / "deploy" / "release.py", source / "release.py")
    for relative in RUNTIME_CONTRACT_PATHS:
        origin = repository / relative
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)

    bundle_runtime_contract(staging, source)

    for relative in RUNTIME_CONTRACT_PATHS:
        backend_relative = Path(relative).relative_to("backend")
        assert (source / "backend" / backend_relative).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import release; assert release.chat_runtime('staging')['enabled']",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(source)},
    )
    assert result.returncode == 0, result.stderr


def make_bundle(root: Path, *, chat: bool) -> Path:
    release = root / ("release-staging" if chat else "release-production")
    dist = release / "frontend-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app-abc123.js").write_text("export {}")
    (assets / "app-abc123.css").write_text("body{}")
    (dist / "index.html").write_text(
        '<script type="module" src="/assets/app-abc123.js"></script>'
        '<link rel="stylesheet" href="/assets/app-abc123.css">'
    )
    (dist / "features.json").write_text(json.dumps({"chat": chat}))
    (release / "backend").mkdir()
    (release / "backend" / "main.py").write_text("")
    sha = "a" * 40
    environment = "staging" if chat else "production"
    descriptor = None
    if environment == "staging":
        descriptor = {
            **build_manifest(sha, environment)["chat_runtime"],
            "modal_image_version": "im-test-immutable",
        }
    (release / "release.json").write_text(
        json.dumps(build_manifest(sha, environment, chat_descriptor=descriptor))
    )
    return release


def deployed_settings(tmp_path: Path, release: Path, environment: str) -> Settings:
    state = tmp_path / "state"
    thumbnail = tmp_path / "thumbnails"
    for path in (
        state,
        thumbnail,
        state / "cache",
        state / "logs",
        state / "locks",
        state / "spool",
        state / "agent",
        state / "recovery",
    ):
        path.mkdir(parents=True, exist_ok=True)
    runtime = json.loads((release / "release.json").read_text())["chat_runtime"]
    return Settings(
        environment=environment,
        release_id=json.loads((release / "release.json").read_text())["release_id"],
        frontend_dist_dir=str(release / "frontend-dist"),
        runtime_data_dir=str(state),
        thumbnail_cache_dir=str(thumbnail),
        thumbnail_temp_cache_dir=str(state / "cache"),
        cron_log_dir=str(state / "logs"),
        cron_lock_dir=str(state / "locks"),
        codex_add_evals_spool_dir=str(state / "spool"),
        chat_agent_cwd=str(state / "agent"),
        chat_recovery_spool_dir=str(state / "recovery"),
        jwt_secret="test-only",
        production_jwt_fingerprint=("0" * 64 if environment == "staging" else ""),
        session_cookie_domain="",
        session_cookie_name=(
            "pwc_staging_session" if environment == "staging" else "pwc_session"
        ),
        chat_enabled=environment == "staging",
        chat_default_backend=runtime["default_backend"],
        chat_new_chat_modal_percentage=runtime["new_chat_modal_percentage"],
        chat_modal_image_version=runtime["modal_image_version"],
        chat_pwc_cli_version=runtime["pwc_cli_version"],
        chat_worker_contract_version=runtime["worker_contract_version"],
        chat_system_prompt_sha256=runtime["system_prompt_sha256"],
        chat_gateway_url=(
            "https://chat-gateway.staging.paperswithcode.co/api/internal/chat-gateway"
            if environment == "staging"
            else ""
        ),
        hf_token="test-only-hf-token" if environment == "staging" else "",
        catalog_mutations_enabled=environment == "production",
        thumbnail_mutations_enabled=False,
        cron_enabled=environment == "production",
        db_search_path="staging,public" if environment == "staging" else "public",
    )


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_deployed_runtime_validation(tmp_path: Path, environment: str):
    release = make_bundle(tmp_path, chat=environment == "staging")
    settings = deployed_settings(tmp_path, release, environment)
    assert validate_runtime(settings) == {"chat": environment == "staging"}


def test_deployed_runtime_rejects_relative_path(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    settings = deployed_settings(tmp_path, release, "production")
    settings.runtime_data_dir = "./runtime"
    with pytest.raises(RuntimeError, match="must be absolute"):
        validate_runtime(settings)


def test_staging_runtime_accepts_directory_snapshot_feature(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_workspace_snapshots_enabled = True
    assert validate_runtime(settings) == {"chat": True}


def test_deployed_runtime_rejects_source_shell(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "index.html").write_text(
        '<script type="module" src="/src/main.tsx"></script>'
    )
    with pytest.raises(RuntimeError, match="/src/main.tsx"):
        validate_runtime(deployed_settings(tmp_path, release, "production"))


def test_release_manifest_rejects_feature_mismatch(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "features.json").write_text('{"chat": true}')
    with pytest.raises(ValueError, match="features.json"):
        validate_manifest(release, "production")


@pytest.mark.parametrize(
    ("environment", "version", "features"),
    [
        (
            "staging",
            2,
            {
                "chat": True,
                "codex_add_evals": False,
                "codex_enrich_paper": False,
            },
        ),
        (
            "production",
            3,
            {
                "chat": False,
                "codex_add_evals": True,
                "codex_enrich_paper": True,
            },
        ),
    ],
)
def test_pre_bridge_versioned_manifest_remains_valid(
    tmp_path: Path, environment: str, version: int, features: dict[str, bool]
):
    release = make_bundle(tmp_path, chat=environment == "staging")
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("chat_runtime")
    manifest["feature_contract_version"] = version
    manifest["backend_features"] = features
    manifest["frontend_features"] = features
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(json.dumps(features))

    assert (
        validate_manifest(release, environment)["release_id"] == manifest["release_id"]
    )


def test_staging_manifest_requires_immutable_modal_image(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chat_runtime"]["modal_image_version"] = "pwc-chat-v1"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="immutable Modal image ID"):
        validate_manifest(release, "staging")


def test_chat_descriptor_is_extracted_from_selected_source():
    source = Path(__file__).resolve().parents[2]
    descriptor = _chat_descriptor_from_source(source, "staging")
    assert descriptor["modal_image_version"] == MODAL_IMAGE_ID
    assert descriptor["worker_contract_version"] == "1"
    assert _chat_descriptor_from_source(source, "production") is None


def test_staging_runtime_rejects_public_gateway_origin(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_gateway_url = (
        "https://staging.paperswithcode.co/api/internal/chat-gateway"
    )
    with pytest.raises(RuntimeError, match="dedicated HTTPS origin"):
        validate_runtime(settings)


def test_smoke_bundle_parser_catches_missing_asset(tmp_path: Path):
    release = make_bundle(tmp_path, chat=False)
    (release / "frontend-dist" / "assets" / "app-abc123.js").unlink()
    assert any(
        "missing asset" in item for item in validate_local_bundle(release, False)
    )


def test_nginx_cross_environment_references_are_rejected():
    failures = validate_nginx(
        "root /srv/paperswithcode/environments/production/current/frontend-dist;"
        " upstream pwc_staging_backend { server 127.0.0.1:8001; } location / { }",
        "root /srv/paperswithcode/environments/staging/current/frontend-dist;"
        " location = /_admin_check { internal; } location / { }"
        " server_name chat-gateway.staging.paperswithcode.co;"
        " client_max_body_size 512k;"
        " location = /api/internal/chat-gateway/catalog { }"
        " location = /api/internal/chat-gateway/session-store { }"
        " location = /api/internal/chat-gateway/v1/messages { }",
    )
    assert "production references staging backend" in failures


def test_atomic_symlink_replaces_pointer(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "current"
    atomic_symlink(first, link)
    atomic_symlink(second, link)
    assert link.resolve() == second


def test_activation_rollback_restores_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    failed = tmp_path / "failed"
    previous = tmp_path / "previous"
    failed.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(failed, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "log_event",
        lambda *_args, **_kwargs: events.append("logged"),
    )

    deploy_cli.rollback_after_failed_activation(
        "staging", failed, previous_runtime_lock="old-lock"
    )

    assert (root / "current").resolve() == previous
    assert events[0] == ("restore", "old-lock")
    assert events[1] == [
        "systemctl",
        "restart",
        "paperswithcode-backend@staging.service",
    ]


def test_manual_rollback_syncs_target_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(current, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(deploy_cli, "require_root", lambda: None)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {"release_id": release.name},
    )
    monkeypatch.setattr(
        deploy_cli,
        "sync_runtime",
        lambda release: events.append(("sync", release)) or True,
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "_read_json",
        lambda *_args, **_kwargs: {"release_id": "previous"},
    )
    monkeypatch.setattr(deploy_cli, "log_event", lambda *_args, **_kwargs: None)

    assert deploy_cli.rollback(Namespace(environment="staging", confirm="")) == 0
    assert events[:2] == [
        ("sync", previous),
        [
            "systemctl",
            "restart",
            "paperswithcode-backend@staging.service",
        ],
    ]


def test_runtime_sync_failure_restores_previous_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events: list[object] = []

    def fail_sync(_release):
        events.append("sync")
        raise OSError("partial runtime mutation")

    monkeypatch.setattr(deploy_cli, "sync_runtime", fail_sync)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )

    with pytest.raises(OSError, match="partial runtime"):
        deploy_cli.sync_runtime_with_recovery(tmp_path, "old-lock")

    assert events == ["sync", ("restore", "old-lock")]
