"""Backend and slot launchers derive features and runtime from the release."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import deploy.run_backend as run_backend
import deploy.slot_launcher as slot_launcher
from backend.services.runtime_validation import (
    validate_chat_provider_policy,
)
from deploy.release import (
    build_manifest,
)
from deploy.run_backend import RELEASE_ROOT, configure_release_environment
from backend.tests.deployment.harness import (
    deployed_settings,
    make_bundle,
)


def test_run_backend_derives_features_from_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))

    manifest = configure_release_environment(release)

    assert manifest["build_profile"] == "production"
    assert os.environ["PWC_CHAT_ENABLED"] == "false"
    assert os.environ["PWC_CHAT_PAPER_MENTIONS_ENABLED"] == "false"
    assert os.environ["PWC_CHAT_HF_CATALOG_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "true"


def test_slot_launcher_enables_chat_catalog_features(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("PWC_CHAT_PAPER_MENTIONS_ENABLED", raising=False)
    monkeypatch.delenv("PWC_CHAT_HF_CATALOG_ENABLED", raising=False)
    manifest = build_manifest(
        "a" * 40,
        "production",
        production_chat_enabled=True,
    )

    slot_launcher.configure_release(manifest, Path("/release"), "production")

    assert os.environ["PWC_CHAT_PAPER_MENTIONS_ENABLED"] == "true"
    assert os.environ["PWC_CHAT_HF_CATALOG_ENABLED"] == "true"


def test_run_backend_staging_disables_posterly_and_shared_artifact_previews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = make_bundle(tmp_path, chat=True)
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))

    configure_release_environment(release)

    assert os.environ["PWC_CHAT_ARTIFACTS_ENABLED"] == "true"
    assert os.environ["PWC_CHAT_POSTERLY_ENABLED"] == "false"
    assert os.environ["PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED"] == "false"


def test_staging_launcher_disables_posterly_and_shared_artifact_previews(
    monkeypatch: pytest.MonkeyPatch,
):
    manifest = build_manifest("a" * 40, "staging")

    with monkeypatch.context() as scoped:
        for key in (
            "PWC_CHAT_ARTIFACTS_ENABLED",
            "PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED",
            "PWC_CHAT_POSTERLY_ENABLED",
            "PWC_CHAT_ARTIFACT_STORAGE_BACKEND",
            "PWC_CHAT_ARTIFACT_HF_BUCKET_ID",
        ):
            scoped.delenv(key, raising=False)
        slot_launcher.configure_release(manifest, Path("/release"), "staging")

        assert os.environ["PWC_CHAT_ARTIFACTS_ENABLED"] == "true"
        assert os.environ["PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED"] == "false"
        assert os.environ["PWC_CHAT_POSTERLY_ENABLED"] == "false"


@pytest.mark.parametrize("slot", ("blue", "green"))
def test_staging_slot_launcher_binds_external_pi_loopback_fleet(
    monkeypatch: pytest.MonkeyPatch, slot: str
):
    for key in (
        "PWC_CHAT_EXTERNAL_PI_WORKER_ID",
        "PWC_CHAT_EXTERNAL_PI_WORKER_URL",
        "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION",
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS",
        "PWC_CHAT_EXTERNAL_PI_WORKER_ENDPOINTS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 48)

    slot_launcher.configure_external_pi_slot("staging", slot)

    endpoints = json.loads(os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_ENDPOINTS"])
    assert len(endpoints) == 8
    assert [item["worker_id"] for item in endpoints] == [
        f"staging-{slot}-{index:02d}" for index in range(8)
    ]
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_ID"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION"] == (
        "external-pi-v1"
    )
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "4"


def test_production_slot_launcher_binds_isolated_external_pi_worker(
    monkeypatch: pytest.MonkeyPatch,
):
    for key in (
        "PWC_CHAT_EXTERNAL_PI_WORKER_ID",
        "PWC_CHAT_EXTERNAL_PI_WORKER_URL",
        "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION",
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS",
        "PWC_CHAT_EXTERNAL_PI_WORKER_ENDPOINTS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 48)
    slot_launcher.configure_external_pi_slot("production", "blue")

    endpoints = json.loads(os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_ENDPOINTS"])
    assert [item["base_url"] for item in endpoints] == [
        "http://127.0.0.1:8830",
        "http://127.0.0.1:8831",
        "http://127.0.0.1:8832",
        "http://127.0.0.1:8833",
        "http://127.0.0.1:8846",
        "http://127.0.0.1:8847",
        "http://127.0.0.1:8848",
        "http://127.0.0.1:8849",
    ]
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_ID"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"] == ""
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION"] == (
        "external-pi-v1"
    )
    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "4"


def test_production_chat_accepts_bounded_hf_catalog_policy(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.environment = "production"
    settings.chat_gateway_url = (
        "https://chat-gateway.paperswithcode.co/api/internal/chat-gateway"
    )
    settings.chat_hf_catalog_enabled = True

    validate_chat_provider_policy(settings, include_openrouter=False)


def test_run_backend_prepends_immutable_release_root():
    assert sys.path[0] == str(RELEASE_ROOT)
    assert RELEASE_ROOT == Path(__file__).resolve().parents[3]


def test_backend_launcher_uses_release_specific_feature_flags(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    runtime_data_dir = tmp_path / "runtime-data"
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(runtime_data_dir))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_XET_CACHE", raising=False)
    run_backend.configure_release_environment(release)
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "true"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "true"
    assert os.environ["HF_HOME"] == str(runtime_data_dir / "hf-app-cache")
    assert os.environ["HF_XET_CACHE"] == str(runtime_data_dir / "hf-app-cache" / "xet")


def test_backend_launcher_preserves_explicit_hugging_face_cache(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))
    monkeypatch.setenv("HF_HOME", "/custom/hf")
    monkeypatch.setenv("HF_XET_CACHE", "/custom/xet")

    run_backend.configure_release_environment(release)

    assert os.environ["HF_HOME"] == "/custom/hf"
    assert os.environ["HF_XET_CACHE"] == "/custom/xet"


def test_backend_launcher_disables_features_for_legacy_rollback(
    tmp_path: Path, monkeypatch
):
    release = make_bundle(tmp_path, chat=False)
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("feature_contract_version")
    manifest.pop("chat_runtime")
    manifest["backend_features"] = {"chat": False}
    manifest["frontend_features"] = {"chat": False}
    manifest_path.write_text(json.dumps(manifest))
    (release / "frontend-dist" / "features.json").write_text(
        json.dumps({"chat": False})
    )
    monkeypatch.setenv("PWC_FRONTEND_DIST_DIR", str(release / "frontend-dist"))
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path / "runtime-data"))
    run_backend.configure_release_environment(release)
    assert os.environ["PWC_CODEX_JOBS_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] == "false"
    assert os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] == "false"


def test_slot_launcher_sizes_replicas_from_the_protected_fleet_tier(
    monkeypatch: pytest.MonkeyPatch,
):
    import json as _json

    from deploy import slot_launcher

    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN", "t" * 48)
    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS", "64")
    slot_launcher.configure_external_pi_slot("production", "blue")

    assert os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "8"
    assert len(_json.loads(os.environ["PWC_CHAT_EXTERNAL_PI_WORKER_ENDPOINTS"])) == 8

    monkeypatch.setenv("PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS", "48")
    with pytest.raises(ValueError, match="reviewed tier"):
        slot_launcher.configure_external_pi_slot("production", "blue")
