from __future__ import annotations

import json
import os
from argparse import Namespace

import pytest


def test_qualification_cases_cover_the_required_hostile_boundaries() -> None:
    from backend.scripts.qualify_latex_compiler_space import qualification_cases

    names = {case.name for case in qualification_cases()}

    assert {
        "valid-document",
        "shell-escape",
        "host-file-read",
        "network-pipe",
        "recursive-expansion",
        "process-pressure",
        "cpu-limit",
        "memory-limit",
        "disk-limit",
        "oversized-output",
        "path-traversal-archive",
        "malformed-archive",
        "hostile-pdf",
    } <= names


def test_qualification_report_is_bounded_and_never_contains_case_source() -> None:
    from backend.scripts.qualify_latex_compiler_space import QualificationCase, report

    case = QualificationCase(
        name="secret-case", bundle=b"private manuscript source", expected="failed"
    )

    payload = report([(case, "failed", 12)])

    assert payload == {
        "cases": [{"name": "secret-case", "outcome": "failed", "elapsed_ms": 12}],
        "passed": 1,
        "total": 1,
    }
    assert "private manuscript source" not in str(payload)


def test_sandbox_qualification_uses_the_transport_contract() -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import run_case
    from backend.scripts.qualify_latex_compiler_space import QualificationCase
    from latex_compiler_contract import CompilerJobState, CompilerStatus

    class Compiler:
        def __init__(self) -> None:
            self.submitted: list[tuple[str, bytes, str]] = []
            self.results: list[str] = []

        def submit(
            self, *, job_id: str, bundle: bytes, entrypoint: str
        ) -> CompilerStatus:
            self.submitted.append((job_id, bundle, entrypoint))
            return CompilerStatus(job_id=job_id, state=CompilerJobState.COMPILING)

        def status(self, job_id: str) -> CompilerStatus:
            return CompilerStatus(job_id=job_id, state=CompilerJobState.FAILED)

        def result(self, job_id: str) -> None:
            self.results.append(job_id)

    compiler = Compiler()
    outcome, elapsed = run_case(
        QualificationCase("synthetic", b"private manuscript source", "failed"), compiler
    )

    assert outcome == "failed"
    assert elapsed >= 0
    assert compiler.submitted[0][1] == b"private manuscript source"
    assert compiler.results


def test_sandbox_qualification_cancels_a_fresh_synthetic_job() -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import run_cancellation_case
    from latex_compiler_contract import CompilerJobState, CompilerStatus

    class Compiler:
        def __init__(self) -> None:
            self.cancelled: list[str] = []

        def submit(
            self, *, job_id: str, bundle: bytes, entrypoint: str
        ) -> CompilerStatus:
            return CompilerStatus(job_id=job_id, state=CompilerJobState.QUEUED)

        def cancel(self, job_id: str) -> CompilerStatus:
            self.cancelled.append(job_id)
            return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)

    compiler = Compiler()
    outcome, elapsed = run_cancellation_case(compiler)

    assert outcome == "canceled"
    assert elapsed >= 0
    assert len(compiler.cancelled) == 1


def test_sandbox_qualification_requires_explicit_mode_and_private_artifact_store() -> (
    None
):
    from backend.config import Settings
    from backend.scripts.qualify_latex_compiler_sandbox import validate_settings

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )
    with pytest.raises(RuntimeError, match="qualification mode"):
        validate_settings(
            Settings(
                environment="staging",
                chat_artifact_storage_backend="hf_bucket",
                chat_artifact_hf_bucket_id="nielsr/pwc-chat-artifacts-staging",
                chat_latex_compiler_hf_sandbox_image=image,
            )
        )

    validate_settings(
        Settings(
            environment="staging",
            chat_artifact_storage_backend="hf_bucket",
            chat_artifact_hf_bucket_id="nielsr/pwc-chat-artifacts-staging",
            chat_latex_compiler_qualification_mode=True,
            chat_latex_compiler_hf_sandbox_image=image,
            chat_latex_compiler_hf_sandbox_namespace="nielsr",
        )
    )


@pytest.mark.parametrize(
    "enabled_setting",
    [
        "chat_artifacts_enabled",
        "chat_artifact_shared_preview_enabled",
        "chat_posterly_enabled",
    ],
)
def test_sandbox_qualification_refuses_all_user_facing_artifact_surfaces(
    enabled_setting: str,
) -> None:
    """The synthetic compiler check cannot expose any user artifact feature."""

    from backend.config import Settings
    from backend.scripts.qualify_latex_compiler_sandbox import validate_settings

    with pytest.raises(RuntimeError, match="user-facing artifact features"):
        validate_settings(
            Settings(
                environment="staging",
                chat_artifact_storage_backend="hf_bucket",
                chat_artifact_hf_bucket_id="nielsr/pwc-chat-artifacts-staging",
                chat_latex_compiler_qualification_mode=True,
                chat_latex_compiler_hf_sandbox_image=(
                    "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
                    + "a" * 64
                ),
                chat_latex_compiler_hf_sandbox_namespace="nielsr",
                **{enabled_setting: True},
            )
        )


def test_sandbox_qualification_collects_content_free_operational_checks() -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import run_operational_checks
    from latex_compiler_contract import CompilerJobState, CompilerStatus

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )

    class Compiler:
        def __init__(self) -> None:
            self.image = image

        def submit(
            self, *, job_id: str, bundle: bytes, entrypoint: str
        ) -> CompilerStatus:
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id="opaque-provider-handle",
            )

        def health(self, job_id: str) -> dict[str, object]:
            return {
                "status": "ready",
                "qualified_image": image,
                "network_isolation": "sandbox-netns-v1",
            }

        def metrics(self, job_id: str) -> dict[str, object]:
            return {
                "capacity": 1,
                "queue_depth": 1,
                "active": 0,
                "retained_jobs": 1,
                "outcomes": {},
                "failure_categories": {},
                "latency_ms": {"count": 0, "max": 0, "p50": 0},
            }

        def isolation(self, job_id: str) -> dict[str, object]:
            return {
                "image": image,
                "forward_hf_token": False,
                "secrets": False,
                "volumes": False,
                "network_isolation": "sandbox-netns-v1",
            }

        def cancel(self, job_id: str) -> CompilerStatus:
            return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)

    rows = run_operational_checks(Compiler())

    assert {case.name for case, _, _ in rows} == {
        "health",
        "metrics",
        "image-isolation",
    }
    assert all(outcome == "passed" for _, outcome, _ in rows)
    assert "opaque-provider-handle" not in str(rows)


def test_sandbox_qualification_exercises_transport_restart_and_reconciliation() -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import (
        run_restart_reconciliation_checks,
    )
    from latex_compiler_contract import CompilerJobState, CompilerStatus

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )

    class Compiler:
        def __init__(self) -> None:
            self.image = image

        def submit(
            self, *, job_id: str, bundle: bytes, entrypoint: str
        ) -> CompilerStatus:
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id="opaque-provider-handle",
            )

        def reconnect_after_restart(
            self,
            *,
            job_id: str,
            provider_job_id: str,
            bundle: bytes,
            entrypoint: str,
        ) -> CompilerStatus:
            assert provider_job_id == "opaque-provider-handle"
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=provider_job_id,
            )

        def status(self, job_id: str) -> CompilerStatus:
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id="opaque-provider-handle",
            )

        def cancel(self, job_id: str) -> CompilerStatus:
            return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)

    rows = run_restart_reconciliation_checks(Compiler())

    assert {case.name for case, _, _ in rows} == {"restart", "reconciliation"}
    assert all(outcome == "passed" for _, outcome, _ in rows)


def test_sandbox_qualification_evidence_is_private_and_mode_0600(tmp_path) -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import (
        qualification_evidence,
        write_qualification_evidence,
    )
    from backend.scripts.qualify_latex_compiler_space import (
        QualificationCase,
        qualification_cases,
        report,
    )

    image = "registry.hf.space/pwc-test-latex-compiler-staging@sha256:" + "a" * 64
    rows = [(case, case.expected, 1) for case in qualification_cases()]
    rows.extend(
        (
            (
                QualificationCase(
                    name,
                    b"private source",
                    "canceled" if name == "cancellation" else "passed",
                ),
                "canceled" if name == "cancellation" else "passed",
                1,
            )
            for name in (
                "cancellation",
                "health",
                "metrics",
                "image-isolation",
                "restart",
                "reconciliation",
            )
        )
    )
    payload = qualification_evidence(rows, image=image)
    evidence = tmp_path / "qualification.json"

    write_qualification_evidence(payload, evidence)

    assert report(rows)["passed"] == report(rows)["total"]
    assert json.loads(evidence.read_text()) == payload
    assert os.stat(evidence).st_mode & 0o777 == 0o600
    assert os.stat(evidence).st_uid == 0
    assert os.stat(evidence).st_nlink == 1
    assert payload["checks"] == {
        "hostile_input": True,
        "cancellation": True,
        "health": True,
        "metrics": True,
        "image_isolation": True,
        "restart": True,
        "reconciliation": True,
    }
    assert "private source" not in evidence.read_text()


def test_sandbox_qualification_evidence_refuses_a_nonroot_writer(
    monkeypatch, tmp_path
) -> None:
    """A user process cannot create an approval file consumed by activation."""

    from backend.scripts import qualify_latex_compiler_sandbox as qualification

    monkeypatch.setattr(qualification.os, "geteuid", lambda: 1000)

    with pytest.raises(PermissionError, match="root"):
        qualification.write_qualification_evidence(
            {"schema_version": 1}, tmp_path / "qualification.json"
        )


def test_sandbox_qualification_evidence_refuses_a_linked_parent_directory(
    tmp_path,
) -> None:
    """Root approval cannot be redirected through a caller-controlled path link."""

    from backend.scripts import qualify_latex_compiler_sandbox as qualification

    target = tmp_path / "target"
    target.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(target, target_is_directory=True)

    with pytest.raises(PermissionError, match="directory"):
        qualification.write_qualification_evidence(
            {"schema_version": 1}, linked_parent / "qualification.json"
        )

    assert not (target / "qualification.json").exists()


def test_full_qualification_invalidates_stale_evidence_before_running(tmp_path) -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import (
        invalidate_qualification_evidence,
    )

    evidence = tmp_path / "qualification.json"
    evidence.write_text('{"checks":{"hostile_input":true}}')

    invalidate_qualification_evidence(evidence)

    assert not evidence.exists()


def test_sandbox_qualification_redacts_transport_failures(
    monkeypatch, tmp_path
) -> None:
    import httpx

    from backend.config import Settings
    from backend.scripts import qualify_latex_compiler_sandbox as qualification

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )

    class Compiler:
        def __init__(self) -> None:
            self.image = image

        def submit(self, **kwargs: object) -> None:
            raise httpx.ConnectError("https://private-sandbox.example.invalid")

    monkeypatch.setattr(
        qualification,
        "_parse_args",
        lambda: Namespace(
            confirm=qualification.CONFIRMATION,
            case=["valid-document"],
            evidence_path=tmp_path / "qualification.json",
            no_write_evidence=True,
        ),
    )
    monkeypatch.setattr(
        qualification,
        "get_settings",
        lambda: Settings(
            environment="staging",
            chat_artifact_storage_backend="hf_bucket",
            chat_artifact_hf_bucket_id="nielsr/pwc-chat-artifacts-staging",
            chat_latex_compiler_qualification_mode=True,
            chat_latex_compiler_hf_sandbox_image=image,
            chat_latex_compiler_hf_sandbox_namespace="nielsr",
        ),
    )
    monkeypatch.setattr(
        qualification, "compiler_transport_from_settings", lambda _: Compiler()
    )

    with pytest.raises(SystemExit, match="Sandbox qualification failed") as error:
        qualification.main()

    assert "private-sandbox.example.invalid" not in str(error.value)
