"""Read paper Markdown stored in a private Hugging Face bucket."""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from huggingface_hub import HfFileSystem, download_bucket_files
from huggingface_hub.errors import EntryNotFoundError
from PIL import Image

_MODERN_ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")
_EXTERNAL_PAPER_ID = re.compile(r"^[1-9]\d{0,19}$")
PAPER_PDF_MAX_BYTES = 150 * 1024 * 1024
PAPER_PDF_CHUNK_BYTES = 1024 * 1024


_PAPER_ASSET_NAME = re.compile(
    r"^(?P<digest>[0-9a-f]{16,64})\.(?P<extension>png|jpe?g|webp)$"
)
_ASSET_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def normalize_markdown_arxiv_id(value: str) -> str:
    """Normalize a modern ArXiv ID, optionally with a version suffix."""
    match = _MODERN_ARXIV_ID.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            "Paper Markdown currently requires a modern ArXiv ID such as 1706.03762"
        )
    return match.group("base")


def normalize_markdown_paper_id(
    value: str, source: str | None = None
) -> tuple[str, str]:
    candidate = value.strip()
    resolved_source = source
    if resolved_source is None:
        resolved_source = (
            "arxiv" if _MODERN_ARXIV_ID.fullmatch(candidate) else "external"
        )
    if resolved_source == "arxiv":
        return "arxiv", normalize_markdown_arxiv_id(candidate)
    if resolved_source == "external" and _EXTERNAL_PAPER_ID.fullmatch(candidate):
        return "external", candidate
    raise ValueError("External paper Markdown requires a numeric catalog paper ID")


def paper_markdown_bucket_key(paper_id: str, *, source: str | None = None) -> str:
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if resolved_source == "external":
        return f"external/{normalized}.md"
    return f"{normalized[:4]}/{normalized}.md"


def paper_asset_bucket_key(
    paper_id: str, filename: str, *, source: str | None = None
) -> str:
    """Return the immutable bucket key for one OCR-extracted paper image."""
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if _PAPER_ASSET_NAME.fullmatch(filename) is None:
        raise ValueError("Invalid paper asset filename")
    if resolved_source == "external":
        return f"external/{normalized}/images/{filename}"
    return f"{normalized[:4]}/{normalized}/images/{filename}"


def stream_external_paper_pdf(
    paper_id: str,
    *,
    bucket_id: str,
    token: str | None,
) -> tuple[Iterator[bytes], int]:
    """Open one validated archived external PDF as bounded chunks."""
    _, normalized = normalize_markdown_paper_id(paper_id, "external")
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")

    key = f"external/{normalized}/paper.pdf"
    path = f"hf://buckets/{bucket_id.strip()}/{key}"
    filesystem = HfFileSystem(token=token)
    try:
        size = int(filesystem.info(path)["size"])
        with filesystem.open(path, "rb", block_size=0) as handle:
            magic = handle.read(5)
    except (EntryNotFoundError, FileNotFoundError, KeyError, TypeError) as error:
        raise ValueError(f"Paper PDF was not found: {key}") from error
    if size < 5 or size > PAPER_PDF_MAX_BYTES or magic != b"%PDF-":
        raise ValueError("Archived paper PDF is invalid")

    def chunks() -> Iterator[bytes]:
        remaining = size
        with filesystem.open(path, "rb", block_size=0) as handle:
            while remaining:
                chunk = handle.read(min(PAPER_PDF_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return chunks(), size


def read_paper_asset(
    paper_id: str,
    filename: str,
    *,
    source: str | None = None,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
    max_pixels: int,
) -> tuple[bytes, str]:
    """Read and validate one immutable OCR image from the paper-content bucket."""
    if max_bytes < 1 or max_pixels < 1:
        raise ValueError("Paper asset limits must be positive")
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")

    key = paper_asset_bucket_key(paper_id, filename, source=source)
    path = f"hf://buckets/{bucket_id.strip()}/{key}"
    try:
        filesystem = HfFileSystem(token=token)
        with filesystem.open(path, "rb", block_size=0) as handle:
            data = handle.read(max_bytes + 1)
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise ValueError(f"Paper asset was not found: {key}") from error
    if len(data) > max_bytes:
        raise ValueError("Paper asset exceeds the maximum size")

    extension = filename.rsplit(".", 1)[1]
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > max_pixels:
                raise ValueError("Paper asset exceeds the maximum pixel count")
            expected_format = (
                "JPEG" if extension in {"jpg", "jpeg"} else extension.upper()
            )
            if image.format != expected_format:
                raise ValueError("Paper asset format does not match its filename")
            image.verify()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Paper asset is not a valid image") from error
    return data, _ASSET_MEDIA_TYPES[extension]


def read_paper_markdown(
    paper_id: str,
    *,
    source: str | None = None,
    bucket_id: str,
    token: str | None,
) -> str:
    """Download and return one paper's Markdown from the configured bucket."""
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")

    bucket_key = paper_markdown_bucket_key(normalized, source=resolved_source)
    try:
        with TemporaryDirectory(prefix="pwc-paper-read-") as directory:
            destination = Path(directory) / f"{normalized}.md"
            download_bucket_files(
                bucket_id.strip(),
                [(bucket_key, destination)],
                raise_on_missing_files=True,
                token=token,
            )
            return destination.read_text(encoding="utf-8")
    except EntryNotFoundError as error:
        raise ValueError(
            f"Markdown for paper {normalized} was not found in "
            f"hf://buckets/{bucket_id.strip()}/{bucket_key}"
        ) from error


def read_paper_markdown_bounded(
    paper_id: str,
    *,
    source: str | None = None,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
) -> tuple[str, bool]:
    """Read at most ``max_bytes`` from a paper Markdown object.

    The extra byte distinguishes an exact-size document from a truncated one
    without downloading the rest of a private bucket object.
    """
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    raw, truncated = _read_paper_markdown_bytes(
        paper_markdown_bucket_key(normalized, source=resolved_source),
        bucket_id.strip(),
        token,
        max_bytes,
    )

    while raw:
        try:
            return raw.decode("utf-8"), truncated
        except UnicodeDecodeError as error:
            raw = raw[: error.start]
    return "", truncated


@lru_cache(maxsize=128)
def _read_paper_markdown_bytes(
    bucket_key: str,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
) -> tuple[bytes, bool]:
    """Fetch one bounded public artifact and retain hot reads in-process."""
    path = f"hf://buckets/{bucket_id}/{bucket_key}"
    try:
        filesystem = HfFileSystem(token=token)
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(max_bytes + 1)
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise ValueError(
            f"Markdown for paper {bucket_key.removesuffix('.md')} "
            f"was not found in {path}"
        ) from error
    truncated = len(raw) > max_bytes
    return raw[:max_bytes], truncated
