"""Read paper Markdown stored in a private Hugging Face bucket."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from huggingface_hub import HfFileSystem, download_bucket_files
from huggingface_hub.errors import EntryNotFoundError


_MODERN_ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")


def normalize_markdown_arxiv_id(value: str) -> str:
    """Normalize a modern ArXiv ID, optionally with a version suffix."""
    match = _MODERN_ARXIV_ID.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            "Paper Markdown currently requires a modern ArXiv ID such as 1706.03762"
        )
    return match.group("base")


def paper_markdown_bucket_key(arxiv_id: str) -> str:
    normalized = normalize_markdown_arxiv_id(arxiv_id)
    return f"{normalized[:4]}/{normalized}.md"


def read_paper_markdown(
    arxiv_id: str,
    *,
    bucket_id: str,
    token: str | None,
) -> str:
    """Download and return one paper's Markdown from the configured bucket."""
    normalized = normalize_markdown_arxiv_id(arxiv_id)
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")

    bucket_key = paper_markdown_bucket_key(normalized)
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
    arxiv_id: str,
    *,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
) -> tuple[str, bool]:
    """Read at most ``max_bytes`` from a paper Markdown object.

    The extra byte distinguishes an exact-size document from a truncated one
    without downloading the rest of a private bucket object.
    """
    normalized = normalize_markdown_arxiv_id(arxiv_id)
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    raw, truncated = _read_paper_markdown_bytes(
        normalized,
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
    normalized_arxiv_id: str,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
) -> tuple[bytes, bool]:
    """Fetch one bounded public artifact and retain hot reads in-process."""
    bucket_key = paper_markdown_bucket_key(normalized_arxiv_id)
    path = f"hf://buckets/{bucket_id}/{bucket_key}"
    try:
        filesystem = HfFileSystem(token=token)
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(max_bytes + 1)
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise ValueError(
            f"Markdown for paper {normalized_arxiv_id} was not found in {path}"
        ) from error

    truncated = len(raw) > max_bytes
    return raw[:max_bytes], truncated
