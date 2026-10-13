from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_qualification_settings_disable_all_user_facing_artifacts() -> None:
    from backend.config import Settings
    from backend.scripts.qualify_latex_compiler_sandbox import validate_settings

    settings = Settings(
        environment="staging",
        chat_scope_guardrail_enabled=True,
        chat_latex_compiler_qualification_mode=True,
        chat_artifacts_enabled=True,
        chat_artifact_shared_preview_enabled=True,
        chat_posterly_enabled=False,
        chat_artifact_storage_backend="hf_bucket",
        chat_artifact_hf_bucket_id="nielsr/pwc-chat-artifacts-staging",
        chat_latex_compiler_modal_image_id="im-TestLatexCompilerImage0",
        chat_latex_compiler_modal_environment="pwc-latex-staging",
    )

    assert settings.chat_artifacts_enabled is False
    assert settings.chat_artifact_shared_preview_enabled is False
    validate_settings(settings)


def test_qualification_cases_cover_the_required_hostile_boundaries() -> None:
    from backend.services.latex_compiler_qualification_service import (
        qualification_cases,
    )

    names = {case.name for case in qualification_cases()}

    assert {
        "valid-document",
        "shell-escape",
        "host-file-read",
        "network-pipe",
        "recursive-expansion",
        "process-pressure",
        "oversized-output",
        "path-traversal-archive",
        "malformed-archive",
        "hostile-pdf",
    } <= names


def test_qualification_report_is_bounded_and_never_contains_case_source() -> None:
    from backend.services.latex_compiler_qualification_service import (
        QualificationCase,
        report,
    )

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


@pytest.mark.parametrize(
    ("failure_category", "expected"),
    [("compiler_error", "failed"), ("invalid_bundle", "rejected")],
)
def test_sandbox_qualification_uses_the_transport_contract(
    failure_category: str, expected: str
) -> None:
    from backend.scripts.qualify_latex_compiler_sandbox import run_case
    from backend.services.latex_compiler_qualification_service import (
        QualificationCase,
    )
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

        def result(self, job_id: str) -> SimpleNamespace:
            self.results.append(job_id)
            return SimpleNamespace(failure_category=failure_category)

    compiler = Compiler()
    outcome, elapsed = run_case(
        QualificationCase("synthetic", b"private manuscript source", expected),
        compiler,
    )

    assert outcome == expected
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
