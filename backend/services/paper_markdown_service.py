"""Read paper Markdown stored in a private Hugging Face bucket."""

from __future__ import annotations

import re
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from huggingface_hub import HfFileSystem, download_bucket_files
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError
from PIL import Image

_MODERN_ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")
_EXTERNAL_PAPER_ID = re.compile(r"^[1-9]\d{0,19}$")
PAPER_PDF_MAX_BYTES = 150 * 1024 * 1024
PAPER_PDF_CHUNK_BYTES = 1024 * 1024
PAPER_MARKDOWN_MAX_BYTES = 64 * 1024 * 1024
PAPER_MARKDOWN_MANIFEST_MAX_BYTES = 4096
PAPER_MARKDOWN_CHUNK_CACHE_ENTRIES = 256
PAPER_MARKDOWN_CHUNK_CACHE_BYTES = 16 * 1024 * 1024
PAPER_MARKDOWN_CHUNK_CACHE_SECONDS = 3600
PAPER_MARKDOWN_MANIFEST_CACHE_ENTRIES = 512
PAPER_MARKDOWN_MANIFEST_CACHE_SECONDS = 60
PAPER_MARKDOWN_MANIFEST_STALE_SECONDS = 300
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


_PAPER_ASSET_NAME = re.compile(
    r"^(?P<digest>[0-9a-f]{16,64})\.(?P<extension>png|jpe?g|webp)$"
)
_ASSET_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


class PaperMarkdownNotFoundError(ValueError):
    pass


class PaperMarkdownRangeError(ValueError):
    pass


class PaperMarkdownVersionMismatchError(ValueError):
    pass


class PaperMarkdownStorageError(ValueError):
    pass


@dataclass(frozen=True)
class PaperMarkdownChunk:
    markdown: str
    content_version: str
    next_offset: int | None

    @property
    def truncated(self) -> bool:
        return self.next_offset is not None


@dataclass(frozen=True)
class _PaperMarkdownManifest:
    paper_key: str
    source: str
    content_version: str
    content_key: str
    size_bytes: int


class _ChunkCache:
    def __init__(self, *, maximum_entries: int, maximum_bytes: int) -> None:
        self.maximum_entries = maximum_entries
        self.maximum_bytes = maximum_bytes
        self._values: OrderedDict[object, tuple[float, int, PaperMarkdownChunk]] = (
            OrderedDict()
        )
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, key: object) -> PaperMarkdownChunk | None:
        now = time.monotonic()
        with self._lock:
            cached = self._values.get(key)
            if cached is None:
                return None
            expires_at, size, value = cached
            if expires_at <= now:
                self._bytes -= size
                del self._values[key]
                return None
            self._values.move_to_end(key)
            return value

    def put(self, key: object, value: PaperMarkdownChunk) -> None:
        size = len(value.markdown.encode("utf-8"))
        if size > self.maximum_bytes:
            return
        with self._lock:
            previous = self._values.pop(key, None)
            if previous is not None:
                self._bytes -= previous[1]
            self._values[key] = (
                time.monotonic() + PAPER_MARKDOWN_CHUNK_CACHE_SECONDS,
                size,
                value,
            )
            self._bytes += size
            while (
                len(self._values) > self.maximum_entries
                or self._bytes > self.maximum_bytes
            ):
                _, (_, removed_size, _) = self._values.popitem(last=False)
                self._bytes -= removed_size

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._bytes = 0


class _ManifestKeyCache:
    def __init__(self) -> None:
        self._values: OrderedDict[object, tuple[float, float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: object, *, allow_stale: bool = False) -> str | None:
        now = time.monotonic()
        with self._lock:
            cached = self._values.get(key)
            if cached is None:
                return None
            fresh_until, stale_until, value = cached
            if stale_until <= now:
                del self._values[key]
                return None
            if fresh_until <= now and not allow_stale:
                return None
            self._values.move_to_end(key)
            return value

    def put(self, key: object, value: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._values.pop(key, None)
            self._values[key] = (
                now + PAPER_MARKDOWN_MANIFEST_CACHE_SECONDS,
                now + PAPER_MARKDOWN_MANIFEST_STALE_SECONDS,
                value,
            )
            while len(self._values) > PAPER_MARKDOWN_MANIFEST_CACHE_ENTRIES:
                self._values.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


_paper_markdown_chunk_cache = _ChunkCache(
    maximum_entries=PAPER_MARKDOWN_CHUNK_CACHE_ENTRIES,
    maximum_bytes=PAPER_MARKDOWN_CHUNK_CACHE_BYTES,
)
_paper_markdown_manifest_key_cache = _ManifestKeyCache()


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


def paper_markdown_manifest_key(paper_id: str, *, source: str | None = None) -> str:
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    paper_key = (
        f"external/{normalized}" if resolved_source == "external" else normalized
    )
    return f"_content/manifests/{paper_key}.json"


def paper_markdown_content_key(content_version: str) -> str:
    if _SHA256_HEX.fullmatch(content_version) is None:
        raise PaperMarkdownStorageError("Paper Markdown manifest is invalid")
    return f"_content/sha256/{content_version[:2]}/{content_version}.md"


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
    """Read at most ``max_bytes`` from a paper Markdown revision.

    The extra byte distinguishes an exact-size document from a truncated one
    without downloading the rest of a private bucket object. Once a versioned
    manifest exists, it is authoritative over the mutable compatibility alias.
    """
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if not bucket_id.strip():
        raise ValueError("PWC_PAPER_MARKDOWN_HF_BUCKET_ID is not configured")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    bucket_key = _resolve_bounded_markdown_key(
        paper_id=normalized,
        source=resolved_source,
        bucket_id=bucket_id.strip(),
        token=token,
    )

    raw, truncated = _read_paper_markdown_bytes(
        bucket_key,
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


def _read_markdown_manifest(
    filesystem: HfFileSystem,
    *,
    bucket_id: str,
    paper_id: str,
    source: str,
) -> _PaperMarkdownManifest:
    normalized_source, normalized = normalize_markdown_paper_id(paper_id, source)
    expected_paper_key = (
        f"external/{normalized}" if normalized_source == "external" else normalized
    )
    key = paper_markdown_manifest_key(normalized, source=normalized_source)
    path = f"hf://buckets/{bucket_id}/{key}"
    try:
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(PAPER_MARKDOWN_MANIFEST_MAX_BYTES + 1)
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise PaperMarkdownNotFoundError(
            "Versioned Markdown is not available for this paper"
        ) from error
    except (HfHubHTTPError, OSError) as error:
        raise PaperMarkdownStorageError(
            "Paper Markdown storage is temporarily unavailable"
        ) from error
    if not raw or len(raw) > PAPER_MARKDOWN_MANIFEST_MAX_BYTES:
        raise PaperMarkdownStorageError("Paper Markdown manifest is invalid")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperMarkdownStorageError("Paper Markdown manifest is invalid") from error
    if not isinstance(payload, dict):
        raise PaperMarkdownStorageError("Paper Markdown manifest is invalid")
    content_version = payload.get("content_sha256")
    content_key = payload.get("content_key")
    size_bytes = payload.get("size_bytes")
    if (
        payload.get("schema_version") != 1
        or payload.get("paper_key") != expected_paper_key
        or payload.get("source") != normalized_source
        or not isinstance(content_version, str)
        or not isinstance(content_key, str)
        or content_key != paper_markdown_content_key(content_version)
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 1
        or size_bytes > PAPER_MARKDOWN_MAX_BYTES
    ):
        raise PaperMarkdownStorageError("Paper Markdown manifest is invalid")
    return _PaperMarkdownManifest(
        paper_key=expected_paper_key,
        source=normalized_source,
        content_version=content_version,
        content_key=content_key,
        size_bytes=size_bytes,
    )


def _resolve_bounded_markdown_key(
    *, paper_id: str, source: str, bucket_id: str, token: str | None
) -> str:
    paper_key = f"external/{paper_id}" if source == "external" else paper_id
    cache_key = (bucket_id, paper_key)
    cached = _paper_markdown_manifest_key_cache.get(cache_key)
    if cached is not None:
        return cached

    filesystem = HfFileSystem(token=token)
    try:
        manifest = _read_markdown_manifest(
            filesystem,
            bucket_id=bucket_id,
            paper_id=paper_id,
            source=source,
        )
        bucket_key = manifest.content_key
    except PaperMarkdownNotFoundError:
        bucket_key = paper_markdown_bucket_key(paper_id, source=source)
    except PaperMarkdownStorageError:
        stale = _paper_markdown_manifest_key_cache.get(cache_key, allow_stale=True)
        if stale is None:
            raise
        return stale
    _paper_markdown_manifest_key_cache.put(cache_key, bucket_key)
    return bucket_key


def _complete_utf8_prefix(raw: bytes, limit: int) -> bytes:
    candidate = raw[:limit]
    try:
        candidate.decode("utf-8")
        return candidate
    except UnicodeDecodeError as error:
        if error.reason != "unexpected end of data" or error.end != len(candidate):
            raise PaperMarkdownStorageError(
                "Stored Paper Markdown is not valid UTF-8"
            ) from error
        candidate = candidate[: error.start]
    if not candidate:
        raise PaperMarkdownRangeError(
            "The requested limit cannot fit the next UTF-8 code point"
        )
    try:
        candidate.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PaperMarkdownStorageError(
            "Stored Paper Markdown is not valid UTF-8"
        ) from error
    return candidate


def read_paper_markdown_chunk(
    paper_id: str,
    *,
    source: str | None = None,
    bucket_id: str,
    token: str | None,
    offset: int,
    limit: int,
    content_version: str | None = None,
) -> PaperMarkdownChunk:
    """Read one UTF-8-safe byte range from an immutable Markdown revision."""
    resolved_source, normalized = normalize_markdown_paper_id(paper_id, source)
    if not bucket_id.strip():
        raise PaperMarkdownStorageError("Paper Markdown storage is not configured")
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or offset > 2**63 - 1
    ):
        raise PaperMarkdownRangeError("Paper Markdown offset is invalid")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or limit > 262_144
    ):
        raise PaperMarkdownRangeError("Paper Markdown limit is invalid")

    filesystem = HfFileSystem(token=token)
    manifest = _read_markdown_manifest(
        filesystem,
        bucket_id=bucket_id.strip(),
        paper_id=normalized,
        source=resolved_source,
    )
    if content_version is not None and content_version != manifest.content_version:
        raise PaperMarkdownVersionMismatchError(
            "Paper Markdown changed; restart reading from offset zero"
        )
    if offset > manifest.size_bytes:
        raise PaperMarkdownRangeError("Paper Markdown offset is beyond the document")
    if offset == manifest.size_bytes:
        return PaperMarkdownChunk("", manifest.content_version, None)

    cache_key = (
        bucket_id.strip(),
        manifest.paper_key,
        manifest.content_version,
        offset,
        limit,
    )
    cached = _paper_markdown_chunk_cache.get(cache_key)
    if cached is not None:
        return cached

    path = f"hf://buckets/{bucket_id.strip()}/{manifest.content_key}"
    try:
        with filesystem.open(path, "rb", block_size=0) as handle:
            handle.seek(offset)
            raw = handle.read(min(limit + 4, manifest.size_bytes - offset))
    except (EntryNotFoundError, FileNotFoundError) as error:
        raise PaperMarkdownStorageError(
            "The immutable Paper Markdown revision is unavailable"
        ) from error
    except (HfHubHTTPError, OSError) as error:
        raise PaperMarkdownStorageError(
            "Paper Markdown storage is temporarily unavailable"
        ) from error
    if not raw:
        raise PaperMarkdownStorageError("Paper Markdown manifest size is inconsistent")
    if raw[0] & 0b1100_0000 == 0b1000_0000:
        raise PaperMarkdownRangeError(
            "Paper Markdown offset must be a UTF-8 code-point boundary"
        )
    chunk_bytes = _complete_utf8_prefix(raw, min(limit, len(raw)))
    next_offset = offset + len(chunk_bytes)
    chunk = PaperMarkdownChunk(
        markdown=chunk_bytes.decode("utf-8"),
        content_version=manifest.content_version,
        next_offset=next_offset if next_offset < manifest.size_bytes else None,
    )
    _paper_markdown_chunk_cache.put(cache_key, chunk)
    return chunk


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
        if bucket_key.startswith("_content/sha256/"):
            raise PaperMarkdownStorageError(
                "The immutable Paper Markdown revision is unavailable"
            ) from error
        raise ValueError(
            f"Markdown for paper {bucket_key.removesuffix('.md')} "
            f"was not found in {path}"
        ) from error
    truncated = len(raw) > max_bytes
    return raw[:max_bytes], truncated
