from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services import runtime_validation
from backend.services import openrouter_budget_service
from backend.tests.deployment.harness import deployed_settings, make_bundle
from deploy.release import profile_features


IMAGE = (
    "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-netns-v1-staging@sha256:"
    + "a" * 64
)


@pytest.fixture(autouse=True)
def _avoid_live_openrouter_guardrail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_budget_service,
        "validate_openrouter_guardrail",
        lambda _settings: None,
    )


def _armed_settings(tmp_path: Path):
    release = make_bundle(tmp_path, chat=True)
    settings = deployed_settings(tmp_path, release, "staging")
    settings.chat_artifacts_enabled = True
    settings.chat_posterly_enabled = False
    settings.chat_latex_paper_enabled = True
    settings.chat_latex_compiler_jobs_enabled = True
    settings.chat_latex_compiler_qualification_mode = False
    settings.chat_artifact_shared_preview_enabled = False
    settings.chat_artifact_storage_backend = "hf_bucket"
    settings.chat_artifact_hf_bucket_id = "nielsr/pwc-chat-artifacts-staging"
    settings.chat_latex_compiler_hf_sandbox_image = IMAGE
    settings.chat_latex_compiler_hf_sandbox_namespace = "nielsr"
    settings.chat_latex_compiler_hf_sandbox_token = "test-only-sandbox-token"
    settings.chat_latex_compiler_hf_sandbox_flavor = "cpu-upgrade"
    settings.chat_latex_compiler_hf_sandbox_idle_timeout_seconds = 180
    settings.chat_latex_compiler_hf_sandbox_egress_policy_attestation = (
        "sandbox-netns-v1"
    )
    settings.chat_latex_compiler_signing_private_key = (
        base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()
    )
    return settings


def _trusted_evidence(
    tmp_path: Path, image: str = IMAGE
) -> tuple[Path, dict[str, object]]:
    evidence = (
        tmp_path
        / "staging-compiler-qualification"
        / "latex-compiler-qualification.json"
    )
    evidence.parent.mkdir()
    payload: dict[str, object] = {
        "schema_version": 1,
        "environment": "staging",
        "compiler_image": image,
        "passed": 7,
        "total": 7,
        "checks": {
            "hostile_input": True,
            "cancellation": True,
            "health": True,
            "metrics": True,
            "image_isolation": True,
            "reconciliation": True,
            "restart": True,
        },
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return evidence, payload


def _trust_evidence_stat(monkeypatch: pytest.MonkeyPatch, evidence: Path) -> None:
    expected_gid = os.getegid()
    monkeypatch.setattr(
        runtime_validation.grp,
        "getgrnam",
        lambda _name: SimpleNamespace(gr_gid=expected_gid),
    )
    original_lstat = type(evidence).lstat

    def trusted_lstat(path: Path):
        observed = original_lstat(path)
        if path == evidence:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o640,
                st_uid=0,
                st_gid=expected_gid,
                st_nlink=1,
                st_size=observed.st_size,
            )
        if path == evidence.parent:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o750,
                st_uid=0,
                st_gid=expected_gid,
                st_nlink=2,
                st_size=observed.st_size,
            )
        return observed

    monkeypatch.setattr(type(evidence), "lstat", trusted_lstat)


def test_deployed_staging_paper_runtime_requires_bound_root_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _armed_settings(tmp_path)
    evidence, _payload = _trusted_evidence(tmp_path)
    _trust_evidence_stat(monkeypatch, evidence)
    monkeypatch.setattr(
        runtime_validation, "STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE", evidence
    )

    assert runtime_validation.validate_runtime(settings) == profile_features("staging")


def test_compiler_qualification_disables_user_facing_artifacts(tmp_path: Path) -> None:
    settings = _armed_settings(tmp_path)
    settings.chat_latex_paper_enabled = False
    settings.chat_latex_compiler_jobs_enabled = False
    settings.chat_latex_compiler_qualification_mode = True
    settings.chat_artifacts_enabled = False
    settings.chat_artifact_shared_preview_enabled = False

    runtime_validation.validate_private_paper_runtime(settings)

    settings.chat_artifacts_enabled = True
    with pytest.raises(RuntimeError, match="user-facing artifacts"):
        runtime_validation.validate_private_paper_runtime(settings)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("chat_latex_paper_enabled", False, "coherent"),
        ("chat_artifact_shared_preview_enabled", True, "shared previews"),
        ("chat_posterly_enabled", True, "Posterly"),
        ("chat_artifact_hf_bucket_id", "other/private-bucket", "private bucket"),
        (
            "chat_latex_compiler_hf_sandbox_egress_policy_attestation",
            "unattested",
            "egress",
        ),
        ("hf_token", "", "staging Hub identity"),
    ],
)
def test_deployed_staging_paper_runtime_rejects_direct_configuration_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    settings = _armed_settings(tmp_path)
    evidence, _payload = _trusted_evidence(tmp_path)
    _trust_evidence_stat(monkeypatch, evidence)
    monkeypatch.setattr(
        runtime_validation, "STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE", evidence
    )
    setattr(settings, field, value)

    with pytest.raises(RuntimeError, match=message):
        runtime_validation.validate_runtime(settings)


def test_private_paper_runtime_rejects_production_and_untrusted_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _armed_settings(tmp_path)
    evidence, _payload = _trusted_evidence(tmp_path)
    _trust_evidence_stat(monkeypatch, evidence)
    monkeypatch.setattr(
        runtime_validation, "STAGING_LATEX_COMPILER_QUALIFICATION_EVIDENCE", evidence
    )

    settings.environment = "production"
    with pytest.raises(RuntimeError, match="staging"):
        runtime_validation.validate_private_paper_runtime(settings)

    settings.environment = "staging"
    evidence.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="qualification evidence"):
        runtime_validation.validate_private_paper_runtime(settings)
