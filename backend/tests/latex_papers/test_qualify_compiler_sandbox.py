from __future__ import annotations


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


def test_sandbox_qualification_uses_the_transport_contract() -> None:
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
