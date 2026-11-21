"""Strict Posterly bundle validation, immutable storage, and owner access."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import stat
import uuid
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import BinaryIO, Literal
from urllib.parse import urlsplit, urlunsplit

from huggingface_hub import HfFileSystem
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from PyPDF2 import PdfReader
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatArtifact,
    ChatArtifactVersion,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperVersion,
    ChatSession,
)

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}v\d+$")
_SAFE_TEXT_EXTENSIONS = {".html", ".css", ".json", ".md", ".txt"}
_SAFE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_SAFE_EXTENSIONS = _SAFE_TEXT_EXTENSIONS | _SAFE_IMAGE_EXTENSIONS | {".pdf"}
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PDF_MAGIC = b"%PDF-"
_PAGE_SIZE = re.compile(
    r"@page\s*\{[^}]*\bsize\s*:\s*"
    r"(?P<width>\d+(?:\.\d+)?)\s*(?P<wunit>in|cm|mm|pt)\s+"
    r"(?P<height>\d+(?:\.\d+)?)\s*(?P<hunit>in|cm|mm|pt)",
    re.IGNORECASE | re.DOTALL,
)
_REMOTE_SUBRESOURCE = re.compile(
    r"(?:\bsrc(?:set)?\s*=\s*['\"]\s*(?:https?:)?//|"
    r"<link\b[^>]*\bhref\s*=\s*['\"]\s*(?:https?:)?//|"
    r"url\(\s*['\"]?\s*(?:https?:)?//|"
    r"@import\s+(?:url\()?\s*['\"]?\s*(?:https?:)?//)",
    re.IGNORECASE,
)


class ArtifactError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def lock_owner_artifact_quota(db: Session, owner_id: str) -> None:
    """Serialize durable artifact quota admission for one owner.

    Posterly and LaTeX paper versions use separate tables, so their normal
    artifact locks cannot make an owner-wide limit atomic.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:owner))"),
            {"owner": f"chat-artifact-storage:{owner_id}"},
        )


def owner_artifact_storage_bytes(db: Session, owner_id: str) -> int:
    """Return one owner's durable bytes across all chat artifact types."""
    poster_bytes = db.scalar(
        select(func.coalesce(func.sum(ChatArtifactVersion.byte_count), 0))
        .join(ChatArtifact)
        .join(ChatSession)
        .where(
            ChatSession.hf_user_id == owner_id,
            ChatArtifactVersion.state.in_(["uploading", "ready"]),
        )
    )
    paper_versions = db.scalars(
        select(ChatLatexPaperVersion)
        .join(ChatArtifact)
        .join(ChatSession)
        .where(
            ChatSession.hf_user_id == owner_id,
            ChatLatexPaperVersion.storage_state == "ready",
        )
    ).all()
    paper_text_bytes = sum(
        int(file.get("bytes", 0))
        for version in paper_versions
        for file in (version.source_manifest or {}).get("files", [])
        if file.get("blob_digest") is None
    )
    figure_digests = db.scalars(
        select(ChatLatexPaperFigureReference.blob_digest)
        .join(ChatLatexPaperVersion)
        .join(ChatArtifact)
        .join(ChatSession)
        .where(ChatSession.hf_user_id == owner_id)
        .distinct()
    ).all()
    figure_bytes = sum(
        blob.byte_count
        for digest in figure_digests
        if (blob := db.get(ChatLatexPaperFigureBlob, digest)) is not None
    )
    paper_pdf_bytes = sum(
        diagnostics.get("pdf_bytes", 0)
        for version in paper_versions
        if isinstance(diagnostics := version.compile_diagnostics, dict)
        and isinstance(diagnostics.get("pdf_bytes"), int)
    )
    return int(poster_bytes or 0) + paper_text_bytes + figure_bytes + paper_pdf_bytes


class PosterCanvas(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    width: float = Field(gt=0, le=200)
    height: float = Field(gt=0, le=200)
    unit: Literal["in"] = "in"
    orientation: Literal["landscape", "portrait"]

    @model_validator(mode="after")
    def validate_orientation(self) -> "PosterCanvas":
        expected = "landscape" if self.width > self.height else "portrait"
        if self.width == self.height or self.orientation != expected:
            raise ValueError("Canvas dimensions and orientation disagree")
        return self


class PosterPaperProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=64)
    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}v\d+$", max_length=50)
    paper_version: str = Field(pattern=r"^v\d+$", max_length=16)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_available: bool


class PosterDownload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    label: Literal["Print PDF"]


class PosterManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    identifier: str = Field(min_length=1, max_length=80)
    kind: Literal["posterly"] = "posterly"
    title: str = Field(min_length=1, max_length=300)
    canvas: PosterCanvas
    qr_destination: str | None = Field(default=None, max_length=2000)
    entrypoint: str = Field(min_length=1, max_length=300)
    preview: str = Field(min_length=1, max_length=300)
    downloads: list[PosterDownload] = Field(default_factory=list, max_length=1)
    source_files: list[str] = Field(min_length=2, max_length=96)
    gate_report: str = Field(min_length=1, max_length=300)
    gate_status: Literal["passed", "warnings", "failed"]
    gate_summary: list[str] = Field(default_factory=list, max_length=20)
    paper: PosterPaperProvenance
    direction: str = Field(min_length=1, max_length=120)
    canvas_defaulted: bool
    omitted_branding: list[Literal["logo", "qr"]] = Field(
        default_factory=list, max_length=2
    )

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if _IDENTIFIER.fullmatch(value) is None:
            raise ValueError("Artifact identifier must be a lowercase slug")
        return value

    @field_validator("qr_destination")
    @classmethod
    def validate_qr_destination(cls, value: str | None) -> str | None:
        return normalize_public_https_url(value) if value else None

    @model_validator(mode="after")
    def validate_files_and_gate(self) -> "PosterManifest":
        paths = [self.entrypoint, self.preview, self.gate_report, *self.source_files]
        paths.extend(item.path for item in self.downloads)
        normalized = [_normalize_relative_path(path) for path in paths]
        if len(set(normalized)) != len(normalized):
            allowed = {self.entrypoint, self.gate_report}
            duplicates = {path for path in normalized if normalized.count(path) > 1}
            if duplicates - allowed:
                raise ValueError("Manifest contains duplicate file declarations")
        if self.entrypoint not in self.source_files:
            raise ValueError("Poster HTML entrypoint must be a source file")
        if self.gate_report not in self.source_files:
            raise ValueError("Gate report must be a source file")
        if PurePosixPath(self.entrypoint).suffix.lower() != ".html":
            raise ValueError("Poster entrypoint must be HTML")
        if PurePosixPath(self.preview).suffix.lower() != ".png":
            raise ValueError("Poster preview must be PNG")
        if self.gate_status == "failed" and self.downloads:
            raise ValueError("Failed-gate drafts cannot declare a print PDF")
        if self.gate_status != "failed" and len(self.downloads) != 1:
            raise ValueError("Passed posters require one print PDF")
        if self.qr_destination is None and "qr" not in self.omitted_branding:
            raise ValueError("A missing QR destination must be recorded as omitted")
        return self


@dataclass(frozen=True)
class ValidatedPosterBundle:
    manifest: PosterManifest
    directory: Path
    files: dict[str, Path]
    file_digests: dict[str, str]
    file_sizes: dict[str, int]
    bundle_digest: str
    total_bytes: int


@dataclass(frozen=True)
class StoredArtifactFile:
    data: bytes
    media_type: str
    filename: str


class ArtifactStorage(ABC):
    @abstractmethod
    def write_file(self, key: str, source: BinaryIO) -> None: ...

    @abstractmethod
    def read_file(self, key: str, *, max_bytes: int) -> bytes: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        normalized = _normalize_relative_path(key)
        path = (self.root / normalized).resolve()
        if not path.is_relative_to(self.root):
            raise ArtifactError("artifact_invalid", "Invalid storage key")
        return path

    def write_file(self, key: str, source: BinaryIO) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("xb") as output:
            shutil.copyfileobj(source, output, length=64 * 1024)
        os.replace(temporary, path)

    def read_file(self, key: str, *, max_bytes: int) -> bytes:
        with self._path(key).open("rb") as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ArtifactError(
                "artifact_too_large", "Stored artifact exceeds its bound"
            )
        return data

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.exists():
            shutil.rmtree(path)


class HfBucketArtifactStorage(ArtifactStorage):
    def __init__(self, bucket_id: str, token: str | None):
        if not bucket_id:
            raise ValueError("Artifact Hugging Face bucket is not configured")
        self.bucket_id = bucket_id
        self.filesystem = HfFileSystem(token=token)

    def _path(self, key: str) -> str:
        return f"hf://buckets/{self.bucket_id}/{_normalize_relative_path(key)}"

    def write_file(self, key: str, source: BinaryIO) -> None:
        with self.filesystem.open(self._path(key), "wb") as output:
            shutil.copyfileobj(source, output, length=64 * 1024)

    def read_file(self, key: str, *, max_bytes: int) -> bytes:
        with self.filesystem.open(self._path(key), "rb", block_size=0) as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ArtifactError(
                "artifact_too_large", "Stored artifact exceeds its bound"
            )
        return data

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if self.filesystem.exists(path):
            self.filesystem.rm(path, recursive=True)


def artifact_storage_from_settings(settings: Settings) -> ArtifactStorage:
    """Build the shared private artifact store without exposing its credentials."""
    if settings.chat_artifact_storage_backend == "hf_bucket":
        return HfBucketArtifactStorage(
            settings.chat_artifact_hf_bucket_id,
            settings.hf_token or None,
        )
    return LocalArtifactStorage(Path(settings.chat_artifact_local_dir))


def normalize_public_https_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise ValueError("QR destination must be a public HTTPS URL")
    hostname = parsed.hostname.rstrip(".").lower()
    if (
        "." not in hostname
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("QR destination must use a public host")
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("QR destination must use a public host")
    netloc = hostname if parsed.port is None else f"{hostname}:443"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def _normalize_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("Artifact paths must be normalized relative paths")
    if _SAFE_PATH.fullmatch(value) is None:
        raise ValueError("Artifact paths must use conservative ASCII names")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Artifact paths must stay below the manifest directory")
    normalized = path.as_posix()
    if normalized != value or len(normalized) > 300:
        raise ValueError("Artifact path is not normalized")
    return normalized


def _unit_to_inches(value: float, unit: str) -> float:
    return value * {"in": 1, "cm": 1 / 2.54, "mm": 1 / 25.4, "pt": 1 / 72}[unit]


def _validate_html_canvas(path: Path, canvas: PosterCanvas) -> None:
    try:
        html = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactError("artifact_invalid", "Poster HTML must be UTF-8") from error
    match = _PAGE_SIZE.search(html)
    if match is None:
        raise ArtifactError(
            "artifact_invalid", "Poster HTML has no explicit @page size"
        )
    width = _unit_to_inches(float(match["width"]), match["wunit"].lower())
    height = _unit_to_inches(float(match["height"]), match["hunit"].lower())
    if abs(width - canvas.width) > 0.02 or abs(height - canvas.height) > 0.02:
        raise ArtifactError(
            "artifact_invalid", "Poster HTML and manifest canvas disagree"
        )
    if _REMOTE_SUBRESOURCE.search(html):
        raise ArtifactError(
            "artifact_invalid", "Poster source contains a remote subresource"
        )


def _validate_text_assets(files: dict[str, Path]) -> None:
    for relative, path in files.items():
        if path.suffix.lower() not in _SAFE_TEXT_EXTENSIONS:
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactError(
                "artifact_invalid", f"Artifact text must be UTF-8: {relative}"
            ) from error
        if _REMOTE_SUBRESOURCE.search(value):
            raise ArtifactError(
                "artifact_invalid", "Poster source contains a remote subresource"
            )


def _validate_png(path: Path, canvas: PosterCanvas, max_pixels: int) -> None:
    with path.open("rb") as handle:
        if handle.read(8) != _PNG_MAGIC:
            raise ArtifactError("artifact_invalid", "Preview is not a PNG")
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.width * image.height > max_pixels:
                raise ArtifactError(
                    "artifact_invalid", "Preview PNG exceeds image limits"
                )
            if (
                abs((image.width / image.height) - (canvas.width / canvas.height))
                > 0.01
            ):
                raise ArtifactError(
                    "artifact_invalid", "Preview aspect ratio is incorrect"
                )
            image.verify()
    except ArtifactError:
        raise
    except Exception as error:
        raise ArtifactError("artifact_invalid", "Preview PNG is invalid") from error


def _validate_pdf(path: Path, canvas: PosterCanvas) -> None:
    with path.open("rb") as handle:
        if handle.read(5) != _PDF_MAGIC:
            raise ArtifactError("artifact_invalid", "Download is not a PDF")
    try:
        reader = PdfReader(str(path), strict=True)
        if len(reader.pages) != 1:
            raise ArtifactError("artifact_invalid", "Poster PDF must have one page")
        box = reader.pages[0].mediabox
        width = float(box.width) / 72
        height = float(box.height) / 72
    except ArtifactError:
        raise
    except Exception as error:
        raise ArtifactError("artifact_invalid", "Poster PDF is invalid") from error
    if abs(width - canvas.width) > 0.02 or abs(height - canvas.height) > 0.02:
        raise ArtifactError(
            "artifact_invalid", "Poster PDF and manifest canvas disagree"
        )


def _safe_extract_zip(archive: Path, destination: Path, settings: Settings) -> None:
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as error:
        raise ArtifactError(
            "artifact_invalid", "Publication is not a valid ZIP"
        ) from error
    with bundle:
        infos = bundle.infolist()
        if len(infos) > settings.chat_artifact_max_files + 1:
            raise ArtifactError(
                "artifact_too_large", "Artifact contains too many files"
            )
        expanded = 0
        seen: set[str] = set()
        for info in infos:
            name = _normalize_relative_path(info.filename)
            if info.is_dir() or name in seen:
                raise ArtifactError(
                    "artifact_invalid", "Artifact has invalid ZIP entries"
                )
            seen.add(name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
                raise ArtifactError(
                    "artifact_invalid", "Artifact contains a special file"
                )
            expanded += info.file_size
            if expanded > settings.chat_artifact_max_version_bytes:
                raise ArtifactError(
                    "artifact_too_large", "Artifact exceeds the version limit"
                )
            if info.compress_size and info.file_size / info.compress_size > 100:
                raise ArtifactError(
                    "artifact_invalid", "Artifact compression ratio is unsafe"
                )
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=64 * 1024)


def validate_poster_bundle(
    directory: Path, settings: Settings
) -> ValidatedPosterBundle:
    manifest_path = directory / "manifest.json"
    try:
        raw_manifest = manifest_path.read_bytes()
        if len(raw_manifest) > settings.chat_artifact_max_text_bytes:
            raise ArtifactError("artifact_too_large", "Artifact manifest is too large")
        manifest = PosterManifest.model_validate_json(raw_manifest)
    except ArtifactError:
        raise
    except Exception as error:
        raise ArtifactError(
            "artifact_invalid", "Artifact manifest is invalid"
        ) from error

    declared = {
        manifest.entrypoint,
        manifest.preview,
        manifest.gate_report,
        *manifest.source_files,
        *(download.path for download in manifest.downloads),
    }
    present = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if declared != present:
        raise ArtifactError(
            "artifact_invalid", "Artifact has undeclared or missing files"
        )
    if len(present) > settings.chat_artifact_max_files:
        raise ArtifactError("artifact_too_large", "Artifact contains too many files")

    files: dict[str, Path] = {}
    digests: dict[str, str] = {}
    sizes: dict[str, int] = {}
    total_bytes = len(raw_manifest)
    for relative in sorted(present):
        path = directory / relative
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.is_symlink():
            raise ArtifactError("artifact_invalid", "Artifact contains an unsafe file")
        extension = path.suffix.lower()
        if extension not in _SAFE_EXTENSIONS:
            raise ArtifactError("artifact_invalid", "Artifact file type is not allowed")
        limit = (
            settings.chat_artifact_max_pdf_bytes
            if extension == ".pdf"
            else (
                settings.chat_artifact_max_image_bytes
                if extension in _SAFE_IMAGE_EXTENSIONS
                else settings.chat_artifact_max_text_bytes
            )
        )
        if info.st_size > limit:
            raise ArtifactError(
                "artifact_too_large", f"Artifact file is too large: {relative}"
            )
        total_bytes += info.st_size
        if total_bytes > settings.chat_artifact_max_version_bytes:
            raise ArtifactError(
                "artifact_too_large", "Artifact exceeds the version limit"
            )
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
        files[relative] = path
        digests[relative] = digest.hexdigest()
        sizes[relative] = info.st_size

    _validate_html_canvas(files[manifest.entrypoint], manifest.canvas)
    _validate_text_assets(files)
    _validate_png(
        files[manifest.preview],
        manifest.canvas,
        settings.chat_artifact_preview_max_pixels,
    )
    for download in manifest.downloads:
        _validate_pdf(files[download.path], manifest.canvas)
    try:
        report = json.loads(files[manifest.gate_report].read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError(
            "artifact_invalid", "Gate report must be valid JSON"
        ) from error
    report_status = report.get("gate_status", report.get("overall"))
    normalized_status = (
        True if manifest.gate_status in {"passed", "warnings"} else False
    )
    if report_status not in {manifest.gate_status, normalized_status}:
        raise ArtifactError("artifact_invalid", "Manifest and gate report disagree")

    canonical = manifest.model_dump(mode="json")
    canonical["files"] = [
        {"path": path, "sha256": digests[path], "bytes": sizes[path]}
        for path in sorted(files)
    ]
    canonical_bytes = json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    bundle_digest = hashlib.sha256(canonical_bytes).hexdigest()
    return ValidatedPosterBundle(
        manifest=manifest,
        directory=directory,
        files=files,
        file_digests=digests,
        file_sizes=sizes,
        bundle_digest=bundle_digest,
        total_bytes=total_bytes,
    )


class ChatArtifactService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        storage: ArtifactStorage | None = None,
    ):
        self.db = db
        self.settings = settings
        self.storage = storage or self._storage_from_settings()

    def _storage_from_settings(self) -> ArtifactStorage:
        return artifact_storage_from_settings(self.settings)

    def storage_status(self, owner_id: str) -> dict[str, int]:
        used_bytes = owner_artifact_storage_bytes(self.db, owner_id)
        return {
            "used_bytes": used_bytes,
            "quota_bytes": self.settings.chat_artifact_owner_quota_bytes,
            "available_bytes": max(
                0, self.settings.chat_artifact_owner_quota_bytes - used_bytes
            ),
        }

    def publish_zip(
        self,
        *,
        owner_id: str,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        publication_id: str,
        archive: Path,
        expected_paper: PosterPaperProvenance,
        message_id: uuid.UUID | None = None,
    ) -> ChatArtifactVersion:
        if (
            not self.settings.chat_artifacts_enabled
            or not self.settings.chat_posterly_enabled
        ):
            raise ArtifactError("artifacts_disabled", "Poster generation is disabled")
        if not publication_id or len(publication_id) > 64:
            raise ArtifactError("artifact_invalid", "Publication ID is invalid")
        session = self.db.scalar(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.hf_user_id == owner_id,
            )
        )
        if session is None or session.active_turn_id != turn_id:
            raise ArtifactError("artifact_unauthorized", "Artifact turn is not active")
        with TemporaryDirectory(prefix="pwc-artifact-ingest-") as temporary:
            directory = Path(temporary)
            _safe_extract_zip(archive, directory, self.settings)
            bundle = validate_poster_bundle(directory, self.settings)
            if bundle.manifest.paper != expected_paper:
                raise ArtifactError(
                    "artifact_invalid",
                    "Poster paper provenance does not match the prepared input",
                )
            return self._publish_validated(
                owner_id=owner_id,
                session=session,
                turn_id=turn_id,
                message_id=message_id,
                bundle=bundle,
            )

    def _publish_validated(
        self,
        *,
        owner_id: str,
        session: ChatSession,
        turn_id: uuid.UUID,
        message_id: uuid.UUID | None,
        bundle: ValidatedPosterBundle,
    ) -> ChatArtifactVersion:
        lock_owner_artifact_quota(self.db, owner_id)
        used = owner_artifact_storage_bytes(self.db, owner_id)
        if used + bundle.total_bytes > self.settings.chat_artifact_owner_quota_bytes:
            raise ArtifactError(
                "poster_storage_quota_exceeded",
                "Poster storage quota exceeded; delete a poster or chat and try again",
            )
        artifact = self.db.scalar(
            select(ChatArtifact)
            .where(
                ChatArtifact.session_id == session.id,
                ChatArtifact.identifier == bundle.manifest.identifier,
            )
            .with_for_update()
        )
        if artifact is None:
            artifact_count = self.db.scalar(
                select(func.count(ChatArtifact.id)).where(
                    ChatArtifact.session_id == session.id
                )
            )
            if (
                int(artifact_count or 0)
                >= self.settings.chat_artifact_max_session_artifacts
            ):
                raise ArtifactError(
                    "artifact_limit_reached", "Chat artifact limit reached"
                )
            artifact = ChatArtifact(
                id=uuid.uuid4(),
                session_id=session.id,
                identifier=bundle.manifest.identifier,
                kind="posterly",
                title=bundle.manifest.title,
                latest_version=0,
            )
            self.db.add(artifact)
            self.db.flush()
        existing = self.db.scalar(
            select(ChatArtifactVersion).where(
                ChatArtifactVersion.artifact_id == artifact.id,
                ChatArtifactVersion.bundle_digest == bundle.bundle_digest,
                ChatArtifactVersion.state == "ready",
            )
        )
        if existing is not None:
            return existing
        per_turn = self.db.scalar(
            select(func.count(ChatArtifactVersion.id)).where(
                ChatArtifactVersion.turn_id == turn_id,
                ChatArtifactVersion.state.in_(["uploading", "ready"]),
            )
        )
        if int(per_turn or 0) >= self.settings.chat_artifact_max_versions_per_turn:
            raise ArtifactError("artifact_limit_reached", "Turn artifact limit reached")

        version_number = artifact.latest_version + 1
        version_id = uuid.uuid4()
        prefix = "/".join(
            [
                self.settings.chat_artifact_hf_bucket_prefix.strip("/"),
                str(session.id),
                str(artifact.id),
                str(version_id),
            ]
        )
        canonical = bundle.manifest.model_dump(mode="json")
        canonical["files"] = [
            {
                "path": path,
                "sha256": bundle.file_digests[path],
                "bytes": bundle.file_sizes[path],
                "media_type": _media_type(path),
            }
            for path in sorted(bundle.files)
        ]
        version = ChatArtifactVersion(
            id=version_id,
            artifact_id=artifact.id,
            turn_id=turn_id,
            message_id=message_id,
            version=version_number,
            manifest=canonical,
            bundle_digest=bundle.bundle_digest,
            byte_count=bundle.total_bytes,
            storage_key=prefix,
            preview_path=bundle.manifest.preview,
            preview_mime="image/png",
            gate_status=bundle.manifest.gate_status,
            state="uploading",
        )
        self.db.add(version)
        self.db.flush()
        try:
            for relative, path in bundle.files.items():
                with path.open("rb") as source:
                    self.storage.write_file(f"{prefix}/{relative}", source)
            manifest_bytes = json.dumps(
                canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            self.storage.write_file(f"{prefix}/manifest.json", BytesIO(manifest_bytes))
        except Exception as error:
            version.state = "failed"
            version.failure_code = "artifact_storage_failed"
            self.storage.delete_prefix(prefix)
            raise ArtifactError(
                "artifact_storage_failed", "Poster storage failed"
            ) from error
        artifact.latest_version = version_number
        artifact.title = bundle.manifest.title
        artifact.updated_at = func.now()
        version.state = "ready"
        self.db.flush()
        return version

    def get_artifact(self, owner_id: str, artifact_id: uuid.UUID) -> ChatArtifact:
        artifact = self.db.scalar(
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatSession.hf_user_id == owner_id,
            )
        )
        if artifact is None:
            raise ArtifactError("artifact_not_found", "Artifact not found")
        return artifact

    def delete_version(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        version = self.get_version(owner_id, artifact_id, version_id)
        version.state = "deleting"
        self.db.flush()
        try:
            self.storage.delete_prefix(version.storage_key)
        except Exception as error:
            version.state = "ready"
            raise ArtifactError(
                "artifact_deletion_failed", "Poster deletion could not be verified"
            ) from error
        artifact = version.artifact
        self.db.delete(version)
        self.db.flush()
        latest = self.db.scalar(
            select(func.max(ChatArtifactVersion.version)).where(
                ChatArtifactVersion.artifact_id == artifact.id,
                ChatArtifactVersion.state == "ready",
            )
        )
        if latest is None:
            self.db.delete(artifact)
        else:
            artifact.latest_version = int(latest)
        self.db.flush()

    def get_version(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> ChatArtifactVersion:
        version = self.db.scalar(
            select(ChatArtifactVersion)
            .join(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifactVersion.id == version_id,
                ChatArtifactVersion.state == "ready",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if version is None:
            raise ArtifactError("artifact_not_found", "Artifact version not found")
        return version

    def read_version_file(
        self,
        owner_id: str,
        artifact_id: uuid.UUID,
        version_id: uuid.UUID,
        relative_path: str,
        *,
        role: Literal["preview", "source", "download"],
    ) -> StoredArtifactFile:
        version = self.get_version(owner_id, artifact_id, version_id)
        path = _normalize_relative_path(relative_path)
        manifest = version.manifest
        if role == "preview" and path != version.preview_path:
            raise ArtifactError("artifact_not_found", "Artifact preview not found")
        if role == "source" and path not in manifest["source_files"]:
            raise ArtifactError("artifact_not_found", "Artifact source not found")
        downloads = {item["path"] for item in manifest["downloads"]}
        if role == "download" and path not in downloads:
            raise ArtifactError("artifact_not_found", "Artifact download not found")
        declared = {item["path"]: item for item in manifest["files"]}
        if path not in declared:
            raise ArtifactError("artifact_not_found", "Artifact file not found")
        expected = declared[path]
        data = self.storage.read_file(
            f"{version.storage_key}/{path}", max_bytes=int(expected["bytes"])
        )
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ArtifactError(
                "artifact_corrupt", "Artifact digest verification failed"
            )
        media_type = (
            "text/plain; charset=utf-8" if role == "source" else _media_type(path)
        )
        return StoredArtifactFile(
            data=data,
            media_type=media_type,
            filename=PurePosixPath(path).name,
        )


def _media_type(path: str) -> str:
    extension = PurePosixPath(path).suffix.lower()
    if extension == ".html":
        return "text/plain; charset=utf-8"
    return mimetypes.types_map.get(extension, "application/octet-stream")
