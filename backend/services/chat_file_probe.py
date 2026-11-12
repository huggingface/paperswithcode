"""Identify an uploaded chat file and count PDF pages in a bounded child process.

Uploads are hostile input. Byte sniffing runs in the backend; PyMuPDF only runs
in a short-lived child with address-space and CPU limits, so a malformed or
decompression-bomb PDF cannot stall or bloat a backend worker.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROBE_MEMORY_BYTES = 512 * 1024 * 1024
PROBE_CPU_SECONDS = 15
PROBE_TIMEOUT_SECONDS = 20
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

TEXT_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".tex": "text/plain",
    ".bib": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/plain",
    ".json": "application/json",
    ".py": "text/plain",
    ".ipynb": "application/json",
    ".yaml": "text/plain",
    ".yml": "text/plain",
}


class FileProbeError(ValueError):
    """The upload is not an accepted, readable file."""


@dataclass(frozen=True)
class FileKind:
    media_type: str
    page_count: int | None = None


def sniff(filename: str, data: bytes) -> FileKind:
    """Accept PDF, PNG/JPEG/WEBP and UTF-8 text by content, not by claim."""
    if data.startswith(b"%PDF-"):
        return FileKind("application/pdf")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileKind("image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return FileKind("image/jpeg")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return FileKind("image/webp")
    media_type = TEXT_MEDIA_TYPES.get(Path(filename).suffix.lower())
    if media_type is None:
        raise FileProbeError("Unsupported file type")
    if b"\x00" in data:
        raise FileProbeError("Text files must not contain binary data")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FileProbeError("Text files must be UTF-8") from error
    return FileKind(media_type)


def count_pdf_pages(path: Path) -> int:
    """Open the PDF with PyMuPDF in a limited child and return its page count."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "backend.services.chat_file_probe", str(path)],
            cwd=_REPOSITORY_ROOT,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "")},
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise FileProbeError("The PDF took too long to read") from error
    if completed.returncode != 0:
        raise FileProbeError("The PDF could not be read")
    pages = json.loads(completed.stdout)["pages"]
    if not isinstance(pages, int) or pages < 1:
        raise FileProbeError("The PDF has no pages")
    return pages


def _main(path: str) -> None:
    # Limits are set here, in the child, rather than with ``preexec_fn``,
    # which can deadlock when the parent (a FastAPI worker) has threads.
    resource.setrlimit(resource.RLIMIT_AS, (PROBE_MEMORY_BYTES, PROBE_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (PROBE_CPU_SECONDS, PROBE_CPU_SECONDS))
    import fitz

    with fitz.open(path, filetype="pdf") as document:
        if document.needs_pass:
            raise SystemExit(2)
        print(json.dumps({"pages": document.page_count}))


if __name__ == "__main__":
    _main(sys.argv[1])
