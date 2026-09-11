"""Private immutable LaTeX-paper versions and their compiler hand-off."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

import httpx
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import (
    LatexPaperArtifactDescriptor,
    LatexPaperDiagnostic,
    LatexPaperDisplayMetadata,
    LatexPaperFile,
    LatexPaperHistoryPage,
    LatexPaperManifest,
    LatexPaperVersionDescriptor,
    LatexPaperVersionProvenance,
)
from backend.models.database import (
    ChatArtifact,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperStorageCleanup,
    ChatLatexPaperVersion,
    ChatSession,
)
from backend.services.chat_artifact_service import (
    ArtifactError,
    ArtifactStorage,
    StoredArtifactFile,
    artifact_storage_from_settings,
    lock_owner_artifact_quota,
    owner_artifact_storage_bytes,
)
from backend.services.latex_compiler_service import (
    LatexCompilerTransport,
    compiler_transport_from_settings,
)
from latex_compiler_contract import CompilerJobState, CompilerResult, EnvelopeError

_PAPER_IDENTIFIER = "latex-paper"
_PREVIEW_PDF = "preview.pdf"
_MAX_REPAIR_ATTEMPTS = 3
_REPAIR_POLL_ATTEMPTS = 20
_REPAIR_POLL_SECONDS = 0.25
_AUDIT_PROVENANCE_KEY = "_audit_provenance"

logger = logging.getLogger(__name__)

_FIGURE_TYPES = {
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".pdf": ("application/pdf", b"%PDF-"),
}
_SAFE_FIGURE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,299}")


@dataclass(frozen=True)
class LatexPaperRepairOutcome:
    descriptor: LatexPaperArtifactDescriptor
    repaired: bool
    exhausted: bool


def _neutral_scaffold(title: str) -> dict[str, bytes]:
    safe_title = " ".join(title.split()) or "Untitled Research Draft"
    return {
        "main.tex": f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{natbib}}
\\title{{{safe_title}}}
\\author{{TODO: Author name}}
\\date{{}}
\\begin{{document}}
\\maketitle
\\begin{{abstract}}
TODO: Summarize the research question, evidence, and conclusions.
\\end{{abstract}}
\\section{{Introduction}}
TODO: State the problem and the evidence needed to support this draft.
\\bibliographystyle{{plainnat}}
\\bibliography{{references}}
\\end{{document}}
""".encode(),
        "references.bib": b"@comment{TODO: Add verified bibliography entries.}\n",
    }


def _media_type(path: str) -> str:
    return {
        ".tex": "text/x-tex",
        ".bib": "application/x-bibtex",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
    }[PurePosixPath(path).suffix.lower()]


def _deterministic_zip(files: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def _safe_export_stem(title: str) -> str:
    """Return a bounded ASCII filename stem without path or header syntax."""
    stem = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return (stem or "paper")[:120].rstrip("-") or "paper"


def _figure_storage_key(settings: Settings, digest: str) -> str:
    """Return a generation-specific key for one content-addressed blob.

    A new generation prevents a post-commit cleanup of an orphaned row from
    removing bytes subsequently reintroduced under the same digest.
    """
    return "/".join(
        [
            settings.chat_artifact_hf_bucket_prefix.strip("/"),
            "blobs",
            digest,
            uuid.uuid4().hex,
            "content",
        ]
    )


def _version_display_metadata(
    version: ChatLatexPaperVersion,
) -> LatexPaperDisplayMetadata:
    metadata = dict(version.display_metadata)
    metadata.pop(_AUDIT_PROVENANCE_KEY, None)
    return LatexPaperDisplayMetadata.model_validate(metadata)


def _version_provenance(version: ChatLatexPaperVersion) -> LatexPaperVersionProvenance:
    stored = (version.display_metadata or {}).get(_AUDIT_PROVENANCE_KEY)
    if stored is not None:
        return LatexPaperVersionProvenance.model_validate(stored)
    generated = version.generation_provenance or {}
    if version.actor_type == "ai":
        model_identity = generated.get("selected_model")
        return LatexPaperVersionProvenance(
            action="ai_repair" if generated.get("repair") else "ai_draft",
            model_identity=(
                model_identity if isinstance(model_identity, str) else "unknown"
            ),
        )
    return LatexPaperVersionProvenance(
        action="restore" if version.actor_type == "restore" else "human_save"
    )


def _audit_metadata(
    metadata: LatexPaperDisplayMetadata, provenance: LatexPaperVersionProvenance
) -> dict:
    result = metadata.model_dump(mode="json")
    result[_AUDIT_PROVENANCE_KEY] = provenance.model_dump(mode="json")
    return result


def _version_descriptor(
    artifact: ChatArtifact, version: ChatLatexPaperVersion
) -> LatexPaperVersionDescriptor:
    diagnostics = version.compile_diagnostics or {}
    raw_diagnostics = diagnostics.get("diagnostics", [])
    if not isinstance(raw_diagnostics, list):
        raw_diagnostics = []
    repair_diagnostics = diagnostics.get("last_repair_diagnostics", [])
    if isinstance(repair_diagnostics, list):
        raw_diagnostics = [*raw_diagnostics, *repair_diagnostics]
    errors = diagnostics.get("errors", [])
    if isinstance(errors, list):
        raw_diagnostics.extend(
            {"severity": "error", **item} for item in errors if isinstance(item, dict)
        )
    normalized_diagnostics = [
        LatexPaperDiagnostic(
            severity=item["severity"],
            phase=diagnostics.get("failure_category"),
            file=item.get("file"),
            line=item.get("line"),
            message=item["message"],
        )
        for item in raw_diagnostics[:20]
        if isinstance(item, dict)
        and item.get("severity") in {"error", "warning"}
        and isinstance(item.get("message"), str)
    ]
    attempts = diagnostics.get("repair_attempts", 0)
    attempts = attempts if isinstance(attempts, int) else 0
    attempts = min(max(attempts, 0), _MAX_REPAIR_ATTEMPTS)
    return LatexPaperVersionDescriptor(
        version_id=version.id,
        version=version.version,
        source_digest=version.source_digest,
        compile_status=version.compile_status,
        created_at=version.created_at,
        actor_type=version.actor_type,
        parent_version_id=version.parent_version_id,
        preview_head_version_id=artifact.preview_head_version_id,
        compile_diagnostics=normalized_diagnostics,
        repair_attempts_remaining=_MAX_REPAIR_ATTEMPTS - attempts,
        repair_exhausted=attempts >= _MAX_REPAIR_ATTEMPTS,
        generation_provenance=version.generation_provenance,
        display_metadata=_version_display_metadata(version),
        provenance=_version_provenance(version),
    )


def _paper_descriptor(artifact: ChatArtifact) -> LatexPaperArtifactDescriptor:
    versions = {item.id: item for item in artifact.paper_versions}

    def descriptor(version_id: uuid.UUID | None) -> LatexPaperVersionDescriptor | None:
        if version_id is None or (version := versions.get(version_id)) is None:
            return None
        return _version_descriptor(artifact, version)

    return LatexPaperArtifactDescriptor(
        artifact_id=artifact.id,
        title=artifact.title,
        source_head=descriptor(artifact.source_head_version_id),
        preview_head=descriptor(artifact.preview_head_version_id),
    )


class LatexPaperService:
    """Owns the first paper slice; Posterly keeps its existing service unchanged."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        storage: ArtifactStorage | None = None,
        compiler: LatexCompilerTransport | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._storage = storage
        self.compiler = compiler

    @property
    def storage(self) -> ArtifactStorage:
        if self._storage is None:
            self._storage = artifact_storage_from_settings(self.settings)
        return self._storage

    def create_neutral_scaffold(
        self,
        *,
        owner_id: str,
        session_id: uuid.UUID,
        title: str = "Untitled Research Draft",
        actor_type: str = "human",
        model_identity: str | None = None,
    ) -> LatexPaperArtifactDescriptor:
        if (
            not self.settings.chat_artifacts_enabled
            or not self.settings.chat_latex_paper_enabled
        ):
            raise ArtifactError("artifacts_disabled", "Paper creation is disabled")
        if not self.settings.chat_latex_compiler_jobs_enabled:
            raise ArtifactError("compiler_disabled", "Paper compilation is disabled")
        session_row = self.db.execute(
            select(ChatSession.id, ChatSession.primary_paper_id).where(
                ChatSession.id == session_id, ChatSession.hf_user_id == owner_id
            )
        ).one_or_none()
        if session_row is None:
            raise ArtifactError("artifact_not_found", "Paper chat not found")
        if session_row.primary_paper_id is not None:
            raise ArtifactError(
                "artifact_invalid", "Papers are available only in general chat"
            )
        if actor_type not in {"ai", "human"}:
            raise ArtifactError("artifact_invalid", "Invalid initial paper actor")
        if actor_type == "ai" and not model_identity:
            raise ArtifactError("artifact_invalid", "AI paper versions require a model")
        if actor_type == "human" and model_identity:
            raise ArtifactError(
                "artifact_invalid", "Human paper versions cannot claim a model"
            )
        files = _neutral_scaffold(title)
        provenance = LatexPaperVersionProvenance(
            action="ai_draft" if actor_type == "ai" else "human_save",
            model_identity=model_identity,
            changed_files=sorted(files),
        )
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:session))"),
                {"session": f"chat-latex-paper:{session_id}"},
            )
        existing = self.db.scalar(
            select(ChatArtifact).where(
                ChatArtifact.session_id == session_row.id,
                ChatArtifact.kind == "latex_paper",
            )
        )
        if existing is not None:
            raise ArtifactError("paper_exists", "This chat already has a paper")

        source_bytes, bundle = self._source_bundle(files)
        lock_owner_artifact_quota(self.db, owner_id)
        self._require_owner_quota(owner_id, additional_text_bytes=source_bytes)
        manifest = LatexPaperManifest(
            title=" ".join(title.split()) or "Untitled Research Draft",
            root_document="main.tex",
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(files.items())
            ],
            display_metadata=LatexPaperDisplayMetadata(unresolved_todo_count=3),
        )
        source_digest = hashlib.sha256(bundle).hexdigest()
        artifact = ChatArtifact(
            id=uuid.uuid4(),
            session_id=session_row.id,
            identifier=_PAPER_IDENTIFIER,
            kind="latex_paper",
            title=manifest.title,
            latest_version=1,
        )
        self.db.add(artifact)
        self.db.flush()
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            version=1,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(session_row.id, artifact.id, version=1),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=_audit_metadata(manifest.display_metadata, provenance),
            actor_type=actor_type,
        )
        artifact.source_head_version_id = version.id
        self.db.add(version)
        self.db.flush()
        try:
            for path, data in files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
        except Exception as error:
            version.storage_state = "failed"
            self.storage.delete_prefix(version.storage_key)
            raise ArtifactError(
                "artifact_storage_failed", "Paper source storage failed"
            ) from error
        version.storage_state = "ready"
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def save_human_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        files: Mapping[str, bytes],
        actor_type: str = "human",
        provenance: LatexPaperVersionProvenance | None = None,
    ) -> LatexPaperArtifactDescriptor:
        """Publish one complete human source snapshot and submit it to compilation.

        Browser drafts are deliberately outside this boundary: a call is the explicit
        Save & Compile action, and it must either publish a whole new immutable
        version or leave the current head untouched.
        """
        if actor_type not in {"ai", "human"}:
            raise ArtifactError("artifact_invalid", "Invalid paper version actor")
        if (
            not self.settings.chat_artifacts_enabled
            or not self.settings.chat_latex_paper_enabled
        ):
            raise ArtifactError("artifacts_disabled", "Paper editing is disabled")
        if not self.settings.chat_latex_compiler_jobs_enabled:
            raise ArtifactError("compiler_disabled", "Paper compilation is disabled")
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        lock_owner_artifact_quota(self.db, owner_id)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload its latest version before saving.",
            )
        parent = self._version(owner_id, artifact_id, expected_parent_version_id)
        parent_manifest = LatexPaperManifest.model_validate(parent.source_manifest)
        normalized_files = self._validate_human_files(
            files, root_document=parent_manifest.root_document
        )
        figures = self._figure_blobs_for_version(parent)
        if len(normalized_files) + len(figures) > self.settings.chat_artifact_max_files:
            raise ArtifactError("artifact_too_large", "Paper has too many files")
        bundle_files = self._bundle_files(normalized_files, figures)
        source_bytes, bundle = self._source_bundle(bundle_files)
        self._require_owner_quota(
            owner_id,
            additional_text_bytes=sum(len(data) for data in normalized_files.values()),
        )
        source_digest = hashlib.sha256(bundle).hexdigest()
        if self.db.scalar(
            select(ChatLatexPaperVersion.id).where(
                ChatLatexPaperVersion.artifact_id == artifact.id,
                ChatLatexPaperVersion.source_digest == source_digest,
            )
        ):
            raise ArtifactError(
                "artifact_invalid", "Paper source has no changes to save"
            )
        version_number = (
            self.db.scalar(
                select(func.max(ChatLatexPaperVersion.version)).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
            or 0
        ) + 1
        manifest = LatexPaperManifest(
            title=artifact.title,
            root_document=parent_manifest.root_document,
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(normalized_files.items())
            ]
            + [
                LatexPaperFile(
                    path=path,
                    sha256=blob.digest,
                    bytes=blob.byte_count,
                    media_type=blob.media_type,
                    blob_digest=blob.digest,
                )
                for path, blob in sorted(figures.items())
            ],
            display_metadata=parent_manifest.display_metadata,
        )
        version_provenance = provenance or LatexPaperVersionProvenance(
            action="human_save",
            changed_files=sorted(normalized_files),
        )
        valid_actions = (
            {"ai_draft", "ai_repair"} if actor_type == "ai" else {"human_save"}
        )
        if version_provenance.action not in valid_actions:
            raise ArtifactError(
                "artifact_invalid", "Paper provenance does not match actor"
            )
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            parent_version_id=parent.id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=_audit_metadata(
                manifest.display_metadata, version_provenance
            ),
            actor_type=actor_type,
        )
        self.db.add(version)
        for path, blob in figures.items():
            self.db.add(
                ChatLatexPaperFigureReference(version=version, path=path, blob=blob)
            )
        artifact.latest_version = version_number
        self.db.flush()
        try:
            for path, data in normalized_files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
        except Exception as error:
            version.storage_state = "failed"
            self.storage.delete_prefix(version.storage_key)
            raise ArtifactError(
                "artifact_storage_failed", "Paper source storage failed"
            ) from error
        version.storage_state = "ready"
        # Advance source before compilation so a failed compile remains a durable,
        # repairable human version while the previous PDF remains the preview head.
        artifact.source_head_version_id = version.id
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def save_ai_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        files: Mapping[str, bytes],
        model_identity: str,
        change_summary: str | None = None,
        changed_files: list[str] | None = None,
        reference_changes: list[str] | None = None,
        is_repair: bool = False,
    ) -> LatexPaperArtifactDescriptor:
        """Publish a bounded AI candidate through the same immutable write seam."""
        return self.save_human_version(
            owner_id=owner_id,
            artifact_id=artifact_id,
            expected_parent_version_id=expected_parent_version_id,
            files=files,
            actor_type="ai",
            provenance=LatexPaperVersionProvenance(
                action="ai_repair" if is_repair else "ai_draft",
                model_identity=model_identity,
                change_summary=change_summary,
                changed_files=changed_files or sorted(files),
                reference_changes=reference_changes or [],
            ),
        )

    def upload_figure(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        path: str,
        data: bytes,
        declared_media_type: str,
    ) -> LatexPaperArtifactDescriptor:
        """Add a verified figure as a new immutable source version.

        Figure bytes are immutable content-addressed blobs. Every version stores
        a reference in its manifest and relational reference table, while only
        its editable text files are materialized below the version prefix.
        """
        if not self._editing_enabled():
            raise ArtifactError("artifacts_disabled", "Paper editing is disabled")
        media_type = self._validate_figure(path, data, declared_media_type)
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        lock_owner_artifact_quota(self.db, owner_id)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload its latest version before uploading.",
            )
        parent = self._version(owner_id, artifact_id, expected_parent_version_id)
        parent_manifest = LatexPaperManifest.model_validate(parent.source_manifest)
        if path in {item.path for item in parent_manifest.files}:
            raise ArtifactError(
                "artifact_invalid", "A paper file already uses that path"
            )
        if len(parent_manifest.files) >= self.settings.chat_artifact_max_files:
            raise ArtifactError("artifact_too_large", "Paper has too many files")

        digest = hashlib.sha256(data).hexdigest()
        self._lock_figure_blob(digest)
        blob = self.db.get(ChatLatexPaperFigureBlob, digest)
        is_new_blob = blob is None
        if blob is None:
            blob = ChatLatexPaperFigureBlob(
                digest=digest,
                byte_count=len(data),
                media_type=media_type,
                storage_key=_figure_storage_key(self.settings, digest),
            )
        elif blob.byte_count != len(data) or blob.media_type != media_type:
            raise ArtifactError(
                "artifact_corrupt", "Figure digest metadata is inconsistent"
            )

        text_files = self._read_text_files(parent)
        parent_figures = self._figure_blobs_for_version(parent)
        figures = {**parent_figures, path: blob}
        if is_new_blob:
            bundle_files = self._bundle_files(text_files, parent_figures)
            bundle_files[path] = data
        else:
            bundle_files = self._bundle_files(text_files, figures)
        source_bytes, bundle = self._source_bundle(bundle_files)
        self._require_owner_quota(
            owner_id,
            additional_text_bytes=sum(len(item) for item in text_files.values()),
            additional_figure_bytes=(
                0 if self._owner_references_figure_blob(owner_id, digest) else len(data)
            ),
        )
        version_number = (artifact.latest_version or 0) + 1
        manifest = LatexPaperManifest(
            title=artifact.title,
            root_document=parent_manifest.root_document,
            files=[
                LatexPaperFile(
                    path=file_path,
                    sha256=hashlib.sha256(file_data).hexdigest(),
                    bytes=len(file_data),
                    media_type=_media_type(file_path),
                )
                for file_path, file_data in sorted(text_files.items())
            ]
            + [
                LatexPaperFile(
                    path=file_path,
                    sha256=figure.digest,
                    bytes=figure.byte_count,
                    media_type=figure.media_type,
                    blob_digest=figure.digest,
                )
                for file_path, figure in sorted(figures.items())
            ],
            display_metadata=parent_manifest.display_metadata,
        )
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            parent_version_id=parent.id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=hashlib.sha256(bundle).hexdigest(),
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=_audit_metadata(
                manifest.display_metadata,
                LatexPaperVersionProvenance(action="human_save", changed_files=[path]),
            ),
            actor_type="human",
        )
        if is_new_blob:
            self.db.add(blob)
        self.db.add(version)
        for file_path, figure in figures.items():
            self.db.add(
                ChatLatexPaperFigureReference(
                    version=version, path=file_path, blob=figure
                )
            )
        artifact.latest_version = version_number
        self.db.flush()
        try:
            if is_new_blob:
                self.storage.write_file(blob.storage_key, BytesIO(data))
            for file_path, file_data in text_files.items():
                self.storage.write_file(
                    f"{version.storage_key}/{file_path}", BytesIO(file_data)
                )
        except Exception as error:
            version.storage_state = "failed"
            self.storage.delete_prefix(version.storage_key)
            if is_new_blob:
                self.storage.delete_prefix("/".join(blob.storage_key.split("/")[:-1]))
            raise ArtifactError(
                "artifact_storage_failed", "Figure storage failed"
            ) from error
        version.storage_state = "ready"
        artifact.source_head_version_id = version.id
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return self._descriptor(artifact)

    def list_history(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> LatexPaperHistoryPage:
        """Return audit metadata only; immutable manifests and files stay on demand."""
        if not 1 <= limit <= 50:
            raise ArtifactError(
                "artifact_invalid", "Paper history page size is invalid"
            )
        before_version: int | None = None
        if cursor is not None:
            try:
                before_version = int(cursor)
            except ValueError as error:
                raise ArtifactError(
                    "artifact_invalid", "Paper history cursor is invalid"
                ) from error
            if before_version < 1:
                raise ArtifactError(
                    "artifact_invalid", "Paper history cursor is invalid"
                )
        artifact = self._artifact(owner_id, artifact_id)
        statement = select(ChatLatexPaperVersion).where(
            ChatLatexPaperVersion.artifact_id == artifact.id,
            ChatLatexPaperVersion.storage_state == "ready",
        )
        if before_version is not None:
            statement = statement.where(ChatLatexPaperVersion.version < before_version)
        rows = list(
            self.db.scalars(
                statement.order_by(ChatLatexPaperVersion.version.desc()).limit(
                    limit + 1
                )
            )
        )
        page_rows, extra = rows[:limit], rows[limit:]
        return LatexPaperHistoryPage(
            items=[_version_descriptor(artifact, row) for row in page_rows],
            next_cursor=str(page_rows[-1].version) if extra else None,
        )

    def restore_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        source_version_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
    ) -> LatexPaperArtifactDescriptor:
        """Copy one historical snapshot into a newly compiled immutable head."""
        if not self._editing_enabled():
            raise ArtifactError("artifacts_disabled", "Paper editing is disabled")
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        lock_owner_artifact_quota(self.db, owner_id)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload its latest version before restoring.",
            )
        if source_version_id == expected_parent_version_id:
            raise ArtifactError(
                "artifact_invalid", "Choose a historical version to restore"
            )
        source = self._version(owner_id, artifact_id, source_version_id)
        manifest = LatexPaperManifest.model_validate(source.source_manifest)
        text_files = self._read_text_files(source)
        figures = self._figure_blobs_for_version(source)
        bundle_files = self._bundle_files(text_files, figures)
        source_bytes, bundle = self._source_bundle(bundle_files)
        if hashlib.sha256(bundle).hexdigest() != source.source_digest:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        if source_bytes != source.source_byte_count:
            raise ArtifactError("artifact_corrupt", "Paper source size is invalid")
        self._require_owner_quota(
            owner_id,
            additional_text_bytes=sum(len(data) for data in text_files.values()),
        )
        version_number = (artifact.latest_version or 0) + 1
        provenance = LatexPaperVersionProvenance(
            action="restore", restored_from_version_id=source.id
        )
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            parent_version_id=expected_parent_version_id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source.source_digest,
            source_byte_count=source.source_byte_count,
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=_audit_metadata(manifest.display_metadata, provenance),
            actor_type="restore",
        )
        self.db.add(version)
        for path, blob in figures.items():
            self.db.add(
                ChatLatexPaperFigureReference(version=version, path=path, blob=blob)
            )
        artifact.latest_version = version_number
        self.db.flush()
        try:
            for path, data in text_files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
        except Exception as error:
            version.storage_state = "failed"
            self.storage.delete_prefix(version.storage_key)
            if isinstance(error, ArtifactError):
                raise
            raise ArtifactError(
                "artifact_storage_failed", "Paper source storage failed"
            ) from error
        version.storage_state = "ready"
        artifact.source_head_version_id = version.id
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def _validate_human_files(
        self, files: Mapping[str, bytes], *, root_document: str
    ) -> dict[str, bytes]:
        if not files:
            raise ArtifactError(
                "artifact_invalid", "Paper must contain a root document"
            )
        if len(files) > self.settings.chat_artifact_max_files:
            raise ArtifactError("artifact_too_large", "Paper has too many files")
        normalized: dict[str, bytes] = {}
        for path, data in files.items():
            raw_parts = path.split("/")
            candidate = PurePosixPath(path)
            if (
                not path
                or len(path) > 300
                or "\0" in path
                or "\\" in path
                or candidate.is_absolute()
                or any(part in {"", ".", ".."} for part in raw_parts)
            ):
                raise ArtifactError(
                    "artifact_invalid", "Paper files need safe relative paths"
                )
            if candidate.suffix.lower() not in {".tex", ".bib"}:
                raise ArtifactError(
                    "artifact_invalid",
                    "Paper files must be supported TeX or BibTeX files",
                )
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ArtifactError(
                    "artifact_invalid", "Paper text must be valid UTF-8"
                ) from error
            normalized[path] = data
        if root_document not in normalized:
            raise ArtifactError(
                "artifact_invalid", "The configured root document cannot be deleted"
            )
        total_text_bytes = sum(len(data) for data in normalized.values())
        if total_text_bytes > self.settings.chat_artifact_max_text_bytes:
            raise ArtifactError(
                "artifact_too_large", "Paper text exceeds the editing limit"
            )
        return normalized

    def repair_failed_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        files: Mapping[str, bytes],
        provenance: dict,
    ) -> LatexPaperRepairOutcome:
        """Compile one AI repair candidate without persisting failed attempts."""
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        lock_owner_artifact_quota(self.db, owner_id)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload before repairing.",
            )
        parent = self._version(owner_id, artifact_id, expected_parent_version_id)
        if parent.compile_status != "failed":
            raise ArtifactError(
                "paper_not_failed", "Only a failed source version can be repaired"
            )
        diagnostics = dict(parent.compile_diagnostics or {})
        attempts = diagnostics.get("repair_attempts", 0)
        attempts = attempts if isinstance(attempts, int) else 0
        if attempts >= _MAX_REPAIR_ATTEMPTS:
            return LatexPaperRepairOutcome(
                self._descriptor(artifact), repaired=False, exhausted=True
            )

        parent_manifest = LatexPaperManifest.model_validate(parent.source_manifest)
        normalized_files = self._validate_human_files(
            files, root_document=parent_manifest.root_document
        )
        figures = self._figure_blobs_for_version(parent)
        if len(normalized_files) + len(figures) > self.settings.chat_artifact_max_files:
            raise ArtifactError("artifact_too_large", "Paper has too many files")
        bundle_files = self._bundle_files(normalized_files, figures)
        source_bytes, bundle = self._source_bundle(bundle_files)
        source_digest = hashlib.sha256(bundle).hexdigest()
        candidate_id = uuid.uuid4()
        compiler = self.compiler or compiler_transport_from_settings(self.settings)
        result: CompilerResult | None = None
        submitted = False
        try:
            status = compiler.submit(
                job_id=str(candidate_id),
                bundle=bundle,
                entrypoint=parent_manifest.root_document,
            )
            submitted = True
            for _ in range(_REPAIR_POLL_ATTEMPTS + 1):
                if status.state in {
                    CompilerJobState.SUCCEEDED,
                    CompilerJobState.FAILED,
                }:
                    result = compiler.result(str(candidate_id))
                    break
                time.sleep(_REPAIR_POLL_SECONDS)
                status = compiler.status(str(candidate_id))
            else:
                # Repairs are intentionally ephemeral until a candidate finishes.
                # A pending per-job Sandbox must be released rather than stranded
                # without a durable version/job record to reconcile later.
                compiler.cancel(str(candidate_id))
        except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
            if submitted:
                try:
                    compiler.cancel(str(candidate_id))
                except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
                    pass
            result = None

        if result is None:
            return LatexPaperRepairOutcome(
                self._descriptor(artifact), repaired=False, exhausted=False
            )
        if (
            result.state != CompilerJobState.SUCCEEDED
            or result.pdf is None
            or result.source_digest != source_digest
        ):
            diagnostics["repair_attempts"] = attempts + 1
            diagnostics["last_repair_diagnostics"] = [
                item.model_dump(mode="json") for item in result.diagnostics[:20]
            ]
            parent.compile_diagnostics = diagnostics
            self.db.flush()
            return LatexPaperRepairOutcome(
                self._descriptor(artifact),
                repaired=False,
                exhausted=attempts + 1 >= _MAX_REPAIR_ATTEMPTS,
            )

        self._require_owner_quota(
            owner_id,
            additional_text_bytes=sum(len(data) for data in normalized_files.values()),
        )
        version_number = (artifact.latest_version or 0) + 1
        manifest = LatexPaperManifest(
            title=artifact.title,
            root_document=parent_manifest.root_document,
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(normalized_files.items())
            ]
            + [
                LatexPaperFile(
                    path=path,
                    sha256=blob.digest,
                    bytes=blob.byte_count,
                    media_type=blob.media_type,
                    blob_digest=blob.digest,
                )
                for path, blob in sorted(figures.items())
            ],
            display_metadata=parent_manifest.display_metadata,
        )
        model_identity = provenance.get("selected_model", provenance.get("model"))
        version = ChatLatexPaperVersion(
            id=candidate_id,
            artifact=artifact,
            parent_version_id=parent.id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=_audit_metadata(
                manifest.display_metadata,
                LatexPaperVersionProvenance(
                    action="ai_repair",
                    model_identity=model_identity
                    if isinstance(model_identity, str)
                    else "unknown",
                    changed_files=sorted(normalized_files),
                ),
            ),
            generation_provenance=provenance,
            actor_type="ai",
        )
        self.db.add(version)
        for path, blob in figures.items():
            self.db.add(
                ChatLatexPaperFigureReference(version=version, path=path, blob=blob)
            )
        self.db.flush()
        try:
            for path, data in normalized_files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
            version.storage_state = "ready"
            self._store_compile_result(version, result)
        except Exception as error:
            self.storage.delete_prefix(version.storage_key)
            self.db.expunge(version)
            raise ArtifactError(
                "artifact_storage_failed", "Paper repair storage failed"
            ) from error
        if version.compile_status != "succeeded":
            # A repair candidate is intentionally never a durable failed source.
            # This includes a successful compiler result whose preview cannot be
            # admitted into the owner's quota.
            candidate_diagnostics = version.compile_diagnostics or {}
            candidate_errors = candidate_diagnostics.get("errors")
            if not isinstance(candidate_errors, list):
                candidate_errors = candidate_diagnostics.get("diagnostics")
            diagnostics["repair_attempts"] = attempts + 1
            diagnostics["last_repair_diagnostics"] = (
                candidate_errors[:20]
                if isinstance(candidate_errors, list)
                else [
                    {
                        "severity": "error",
                        "message": "Paper repair could not be published",
                    }
                ]
            )
            parent.compile_diagnostics = diagnostics
            self._schedule_storage_prefix_cleanup(version.storage_key)
            self.db.execute(
                delete(ChatLatexPaperFigureReference).where(
                    ChatLatexPaperFigureReference.version_id == version.id
                )
            )
            self.db.delete(version)
            self.db.flush()
            return LatexPaperRepairOutcome(
                self._descriptor(artifact),
                repaired=False,
                exhausted=attempts + 1 >= _MAX_REPAIR_ATTEMPTS,
            )
        artifact.latest_version = version_number
        artifact.source_head_version_id = version.id
        self.db.flush()
        return LatexPaperRepairOutcome(
            self._descriptor(artifact), repaired=True, exhausted=False
        )

    def repair_context(
        self, *, owner_id: str, artifact_id: uuid.UUID
    ) -> tuple[LatexPaperArtifactDescriptor, dict[str, bytes]]:
        """Return the current failed source for the authenticated chat turn."""
        artifact = self._artifact(owner_id, artifact_id)
        if artifact.source_head_version_id is None:
            raise ArtifactError("paper_missing", "This chat has no paper source")
        version = self._version(owner_id, artifact_id, artifact.source_head_version_id)
        if version.compile_status != "failed":
            raise ArtifactError(
                "paper_not_failed", "The current paper source has not failed"
            )
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        files = {
            file.path: self.read_source_file(
                owner_id, artifact_id, version.id, file.path
            ).data
            for file in manifest.files
            if file.media_type in {"text/x-tex", "application/x-bibtex"}
        }
        return self._descriptor(artifact), files

    def _descriptor(self, artifact: ChatArtifact) -> LatexPaperArtifactDescriptor:
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def _validate_figure(self, path: str, data: bytes, declared_media_type: str) -> str:
        raw_parts = path.split("/")
        candidate = PurePosixPath(path)
        if (
            not _SAFE_FIGURE_PATH.fullmatch(path)
            or candidate.is_absolute()
            or any(part in {"", ".", ".."} for part in raw_parts)
        ):
            raise ArtifactError(
                "artifact_invalid", "Figure files need safe relative paths"
            )
        expected = _FIGURE_TYPES.get(candidate.suffix.lower())
        if expected is None:
            raise ArtifactError(
                "artifact_invalid", "Figures must be PNG, JPEG, or PDF files"
            )
        media_type, signature = expected
        if declared_media_type.lower().split(";", 1)[0].strip() != media_type:
            raise ArtifactError(
                "artifact_invalid", "Figure MIME type does not match its extension"
            )
        if not data.startswith(signature):
            raise ArtifactError(
                "artifact_invalid", "Figure signature does not match its extension"
            )
        if len(data) > self.settings.chat_artifact_max_image_bytes:
            raise ArtifactError("artifact_too_large", "Figures cannot exceed 8 MiB")
        if not data:
            raise ArtifactError("artifact_invalid", "Figure content is empty")
        return media_type

    def _figure_blobs_for_version(
        self, version: ChatLatexPaperVersion
    ) -> dict[str, ChatLatexPaperFigureBlob]:
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        expected = {
            file.path: file for file in manifest.files if file.blob_digest is not None
        }
        references = self.db.scalars(
            select(ChatLatexPaperFigureReference).where(
                ChatLatexPaperFigureReference.version_id == version.id
            )
        ).all()
        blobs: dict[str, ChatLatexPaperFigureBlob] = {}
        for reference in references:
            file = expected.get(reference.path)
            blob = reference.blob
            if (
                file is None
                or blob is None
                or reference.blob_digest != file.blob_digest
                or blob.digest != file.blob_digest
                or blob.byte_count != file.bytes
                or blob.media_type != file.media_type
            ):
                raise ArtifactError(
                    "artifact_corrupt", "Paper figure metadata is invalid"
                )
            blobs[reference.path] = blob
        if set(blobs) != set(expected):
            raise ArtifactError(
                "artifact_corrupt", "Paper figure references are invalid"
            )
        return blobs

    def _read_text_files(self, version: ChatLatexPaperVersion) -> dict[str, bytes]:
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        files: dict[str, bytes] = {}
        for item in manifest.files:
            if item.blob_digest is not None:
                continue
            data = self.storage.read_file(
                f"{version.storage_key}/{item.path}", max_bytes=item.bytes
            )
            if hashlib.sha256(data).hexdigest() != item.sha256:
                raise ArtifactError(
                    "artifact_corrupt", "Paper source digest verification failed"
                )
            files[item.path] = data
        return files

    def _bundle_files(
        self,
        text_files: Mapping[str, bytes],
        figures: Mapping[str, ChatLatexPaperFigureBlob],
    ) -> dict[str, bytes]:
        files = dict(text_files)
        for path, blob in figures.items():
            data = self.storage.read_file(blob.storage_key, max_bytes=blob.byte_count)
            if hashlib.sha256(data).hexdigest() != blob.digest:
                raise ArtifactError(
                    "artifact_corrupt", "Figure digest verification failed"
                )
            expected = _FIGURE_TYPES.get(PurePosixPath(path).suffix.lower())
            if (
                expected is None
                or expected[0] != blob.media_type
                or not data.startswith(expected[1])
            ):
                raise ArtifactError(
                    "artifact_corrupt", "Paper figure content is invalid"
                )
            files[path] = data
        return files

    def _bundle_for_version(self, version: ChatLatexPaperVersion) -> bytes:
        """Reconstruct a compiler bundle without duplicating figures per version."""
        files = self._bundle_files(
            self._read_text_files(version), self._figure_blobs_for_version(version)
        )
        _, bundle = self._source_bundle(files)
        return bundle

    def _source_bundle(self, files: Mapping[str, bytes]) -> tuple[int, bytes]:
        """Build the exact signed compiler input within the version limit."""
        source_bytes = sum(len(data) for data in files.values())
        if source_bytes > self.settings.chat_artifact_max_version_bytes:
            raise ArtifactError(
                "artifact_too_large", "Paper source exceeds the 32 MiB version limit"
            )
        bundle = _deterministic_zip(files)
        if len(bundle) > self.settings.chat_artifact_max_version_bytes:
            raise ArtifactError(
                "artifact_too_large",
                "Paper source archive exceeds the 32 MiB version limit",
            )
        return source_bytes, bundle

    def _owner_references_figure_blob(self, owner_id: str, digest: str) -> bool:
        """Whether this owner already pays for a content-addressed figure."""
        return (
            self.db.scalar(
                select(ChatLatexPaperFigureReference.version_id)
                .join(
                    ChatLatexPaperVersion,
                    ChatLatexPaperFigureReference.version_id
                    == ChatLatexPaperVersion.id,
                )
                .join(
                    ChatArtifact,
                    ChatLatexPaperVersion.artifact_id == ChatArtifact.id,
                )
                .join(ChatSession, ChatArtifact.session_id == ChatSession.id)
                .where(
                    ChatSession.hf_user_id == owner_id,
                    ChatLatexPaperFigureReference.blob_digest == digest,
                )
                .limit(1)
            )
            is not None
        )

    def _owner_durable_bytes(self, owner_id: str) -> int:
        return owner_artifact_storage_bytes(self.db, owner_id)

    def _require_owner_quota(
        self,
        owner_id: str,
        *,
        additional_text_bytes: int = 0,
        additional_figure_bytes: int = 0,
        additional_pdf_bytes: int = 0,
    ) -> None:
        if (
            self._owner_durable_bytes(owner_id)
            + additional_text_bytes
            + additional_figure_bytes
            + additional_pdf_bytes
            > self.settings.chat_artifact_owner_quota_bytes
        ):
            raise ArtifactError(
                "artifact_quota_exceeded", "Paper storage quota would exceed 250 MiB"
            )

    def refresh_compile(
        self, *, owner_id: str, artifact_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor:
        """Idempotently reconcile a submitted compile job on an owner poll."""
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        if artifact.source_head_version_id is None:
            return _paper_descriptor(artifact).model_copy(
                update={"editing_enabled": self._editing_enabled()}
            )
        version = self._version(owner_id, artifact_id, artifact.source_head_version_id)
        if version.compile_status not in {"queued", "compiling"}:
            return _paper_descriptor(artifact).model_copy(
                update={"editing_enabled": self._editing_enabled()}
            )
        job_id = (version.compile_diagnostics or {}).get("job_id")
        if not isinstance(job_id, str):
            raise ArtifactError("artifact_corrupt", "Paper compile job is invalid")
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        bundle = self._bundle_for_version(version)
        if hashlib.sha256(bundle).hexdigest() != version.source_digest:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        compiler = self.compiler or compiler_transport_from_settings(self.settings)
        try:
            provider_job_id = (version.compile_diagnostics or {}).get("provider_job_id")
            resume = getattr(compiler, "resume", None)
            if isinstance(provider_job_id, str) and callable(resume):
                try:
                    status = resume(
                        job_id=job_id,
                        provider_job_id=provider_job_id,
                        bundle=bundle,
                        entrypoint=manifest.root_document,
                    )
                except RuntimeError:
                    # The dedicated VM ended. A replacement remains safe because
                    # the immutable source-version UUID is the logical key.
                    status = compiler.submit(
                        job_id=job_id, bundle=bundle, entrypoint=manifest.root_document
                    )
            else:
                status = compiler.submit(
                    job_id=job_id, bundle=bundle, entrypoint=manifest.root_document
                )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                version.compile_status = (
                    "compiling"
                    if status.state == CompilerJobState.COMPILING
                    else "queued"
                )
                version.compile_diagnostics = {
                    "job_id": job_id,
                    **(
                        {"provider_job_id": status.provider_job_id}
                        if status.provider_job_id is not None
                        else {}
                    ),
                }
            else:
                self._store_compile_result(version, compiler.result(job_id))
        except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
            # A transient poll failure is not a compile failure. Keep the durable
            # source/job state for the next owner poll or later reconciliation.
            pass
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def _editing_enabled(self) -> bool:
        return (
            self.settings.chat_artifacts_enabled
            and self.settings.chat_latex_paper_enabled
            and self.settings.chat_latex_compiler_jobs_enabled
        )

    def get_descriptor(
        self, owner_id: str, session_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor | None:
        artifact = self.db.scalar(
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.session_id == session_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if artifact is None:
            session_exists = self.db.scalar(
                select(ChatSession.id).where(
                    ChatSession.id == session_id, ChatSession.hf_user_id == owner_id
                )
            )
            if session_exists is None:
                raise ArtifactError("artifact_not_found", "Paper chat not found")
            return None
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def get_artifact_descriptor(
        self, owner_id: str, artifact_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor:
        artifact = self._artifact(owner_id, artifact_id)
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def get_manifest(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> LatexPaperManifest:
        return LatexPaperManifest.model_validate(
            self._version(owner_id, artifact_id, version_id).source_manifest
        )

    def read_source_file(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID, path: str
    ) -> StoredArtifactFile:
        version = self._version(owner_id, artifact_id, version_id)
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        file = next((item for item in manifest.files if item.path == path), None)
        if file is None or file.media_type not in {
            "text/x-tex",
            "application/x-bibtex",
        }:
            raise ArtifactError("artifact_not_found", "Paper source file not found")
        data = self.storage.read_file(
            f"{version.storage_key}/{file.path}", max_bytes=file.bytes
        )
        if hashlib.sha256(data).hexdigest() != file.sha256:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        return StoredArtifactFile(
            data=data,
            media_type="text/plain; charset=utf-8",
            filename=PurePosixPath(path).name,
        )

    def read_figure(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID, path: str
    ) -> StoredArtifactFile:
        version = self._version(owner_id, artifact_id, version_id)
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        file = next((item for item in manifest.files if item.path == path), None)
        if file is None or file.blob_digest is None:
            raise ArtifactError("artifact_not_found", "Paper figure not found")
        blob = self._figure_blobs_for_version(version).get(path)
        if blob is None:
            raise ArtifactError("artifact_corrupt", "Paper figure metadata is invalid")
        data = self.storage.read_file(blob.storage_key, max_bytes=blob.byte_count)
        expected = _FIGURE_TYPES.get(PurePosixPath(path).suffix.lower())
        if (
            expected is None
            or blob.media_type != expected[0]
            or not data.startswith(expected[1])
            or hashlib.sha256(data).hexdigest() != blob.digest
        ):
            raise ArtifactError(
                "artifact_corrupt", "Paper figure digest verification failed"
            )
        return StoredArtifactFile(
            data=data, media_type=blob.media_type, filename=PurePosixPath(path).name
        )

    def read_preview_pdf(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> StoredArtifactFile:
        version = self._version(owner_id, artifact_id, version_id)
        if version.compile_status != "succeeded" or version.compiled_pdf_path is None:
            raise ArtifactError("artifact_not_found", "Paper preview not found")
        data = self.storage.read_file(
            f"{version.storage_key}/{version.compiled_pdf_path}",
            max_bytes=self.settings.chat_artifact_max_pdf_bytes,
        )
        expected_digest = (version.compile_diagnostics or {}).get("pdf_sha256")
        if (
            not data.startswith(b"%PDF-")
            or not isinstance(expected_digest, str)
            or hashlib.sha256(data).hexdigest() != expected_digest
        ):
            raise ArtifactError("artifact_corrupt", "Paper preview is invalid")
        return StoredArtifactFile(
            data=data, media_type="application/pdf", filename="paper.pdf"
        )

    def export_last_successful_pdf(
        self, owner_id: str, artifact_id: uuid.UUID
    ) -> StoredArtifactFile:
        """Export only the owner's durable last-good preview."""
        artifact = self._artifact(owner_id, artifact_id)
        if artifact.preview_head_version_id is None:
            raise ArtifactError("artifact_not_found", "Paper preview not found")
        item = self.read_preview_pdf(
            owner_id, artifact.id, artifact.preview_head_version_id
        )
        return StoredArtifactFile(
            data=item.data,
            media_type=item.media_type,
            filename=f"{_safe_export_stem(artifact.title)}.pdf",
        )

    def export_source_zip(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> StoredArtifactFile:
        """Build a bounded verified ZIP for an explicitly selected source version."""
        artifact = self._artifact(owner_id, artifact_id)
        version = self._version(owner_id, artifact.id, version_id)
        bundle = self._bundle_for_version(version)
        if hashlib.sha256(bundle).hexdigest() != version.source_digest:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        return StoredArtifactFile(
            data=bundle,
            media_type="application/zip",
            filename=(
                f"{_safe_export_stem(artifact.title)}-v{version.version}-source.zip"
            ),
        )

    def _compile(
        self, version: ChatLatexPaperVersion, bundle: bytes, entrypoint: str
    ) -> None:
        compiler = self.compiler or compiler_transport_from_settings(self.settings)
        # The immutable source-version ID is the durable idempotency key. A
        # fresh backend process can submit the same bundle after a Space restart
        # without creating a second logical compile job.
        job_id = str(version.id)
        submitted_provider_job_id: str | None = None
        try:
            previous = version.compile_diagnostics or {}
            provider_job_id = previous.get("provider_job_id")
            if isinstance(provider_job_id, str):
                submitted_provider_job_id = provider_job_id
            resume = getattr(compiler, "resume", None)
            if isinstance(provider_job_id, str) and callable(resume):
                try:
                    status = resume(
                        job_id=job_id,
                        provider_job_id=provider_job_id,
                        bundle=bundle,
                        entrypoint=entrypoint,
                    )
                except RuntimeError:
                    # A completed/lost VM is safe to replace: the immutable
                    # version UUID remains the logical idempotency key.
                    status = compiler.submit(
                        job_id=job_id, bundle=bundle, entrypoint=entrypoint
                    )
            else:
                status = compiler.submit(
                    job_id=job_id, bundle=bundle, entrypoint=entrypoint
                )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                submitted_provider_job_id = status.provider_job_id
                status = compiler.status(job_id)
                if (
                    status.provider_job_id is None
                    and submitted_provider_job_id is not None
                ):
                    status = status.model_copy(
                        update={"provider_job_id": submitted_provider_job_id}
                    )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                version.compile_status = (
                    "compiling"
                    if status.state == CompilerJobState.COMPILING
                    else "queued"
                )
                version.compile_diagnostics = {
                    "job_id": job_id,
                    **(
                        {"provider_job_id": status.provider_job_id}
                        if status.provider_job_id is not None
                        else {}
                    ),
                }
                return
            result = compiler.result(job_id)
        except httpx.HTTPError:
            # The durable version remains eligible for the bounded operator
            # reconciliation instead of being falsely finalized on a network
            # failure or a compiler restart.
            version.compile_status = "queued"
            version.compile_diagnostics = {
                "job_id": job_id,
                "failure_category": "transport_failure",
                **(
                    {"provider_job_id": submitted_provider_job_id}
                    if submitted_provider_job_id is not None
                    else {}
                ),
            }
            return
        except (EnvelopeError, RuntimeError, ValueError):
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "job_id": job_id,
                "failure_category": "service_error",
                "errors": [
                    {"severity": "error", "message": "Compiler submission failed"}
                ],
            }
            return
        self._store_compile_result(version, result)

    def reconcile_pending_compiles(self, *, limit: int = 20) -> int:
        """Resume a bounded set of durable versions after transport/Space loss.

        This intentionally does nothing while the compiler kill switch is off.
        It is called by the operator-only reconciliation command, never from a
        request path, so a Space outage cannot amplify normal chat traffic.
        """
        if limit < 1:
            return 0
        self.reconcile_storage_cleanup(limit=limit)
        if not self.settings.chat_latex_compiler_jobs_enabled:
            return 0
        pending_versions = self.db.execute(
            select(ChatLatexPaperVersion.id, ChatLatexPaperVersion.artifact_id)
            .where(
                ChatLatexPaperVersion.storage_state == "ready",
                ChatLatexPaperVersion.compile_status.in_(("queued", "compiling")),
            )
            .order_by(ChatLatexPaperVersion.created_at)
            .limit(limit)
        ).all()
        reconciled = 0
        for version_id, artifact_id in pending_versions:
            # Acquire the same per-artifact transaction lock used by owner
            # polls and writes before looking at a candidate again. The initial
            # query is deliberately only a bounded work list: another worker
            # may settle, delete, or attach this job before this lock is held.
            if self._lock_reconcile_artifact(artifact_id) is None:
                continue
            version = self.db.scalar(
                select(ChatLatexPaperVersion)
                .where(
                    ChatLatexPaperVersion.id == version_id,
                    ChatLatexPaperVersion.artifact_id == artifact_id,
                    ChatLatexPaperVersion.storage_state == "ready",
                    ChatLatexPaperVersion.compile_status.in_(("queued", "compiling")),
                )
                .with_for_update()
            )
            if version is None:
                continue
            manifest = LatexPaperManifest.model_validate(version.source_manifest)
            try:
                bundle = self._bundle_for_version(version)
            except (ArtifactError, httpx.HTTPError, OSError, ValueError):
                version.compile_status = "failed"
                version.compile_diagnostics = {
                    "job_id": str(version.id),
                    "failure_category": "lost",
                    "errors": [
                        {
                            "severity": "error",
                            "message": "Compiler source recovery failed",
                        }
                    ],
                }
                reconciled += 1
                continue
            if hashlib.sha256(bundle).hexdigest() != version.source_digest:
                version.compile_status = "failed"
                version.compile_diagnostics = {
                    "job_id": str(version.id),
                    "failure_category": "lost",
                    "errors": [
                        {
                            "severity": "error",
                            "message": "Compiler source digest mismatch",
                        }
                    ],
                }
                reconciled += 1
                continue
            self._compile(version, bundle, manifest.root_document)
            reconciled += 1
        self.db.flush()
        return reconciled

    def _lock_reconcile_artifact(self, artifact_id: uuid.UUID) -> ChatArtifact | None:
        """Serialize background recovery with owner polls for one paper."""
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:artifact))"),
                {"artifact": f"chat-latex-paper-write:{artifact_id}"},
            )
        return self.db.scalar(
            select(ChatArtifact)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifact.kind == "latex_paper",
            )
            .with_for_update()
        )

    def reconcile_storage_cleanup(self, *, limit: int = 20) -> int:
        """Retry private-prefix cleanup left over by a storage outage or crash."""
        if limit < 1:
            return 0
        pending = self.db.scalars(
            select(ChatLatexPaperStorageCleanup)
            .order_by(ChatLatexPaperStorageCleanup.created_at)
            .limit(limit)
        ).all()
        reclaimed = 0
        for cleanup in pending:
            try:
                self.storage.delete_prefix(cleanup.storage_prefix)
            except Exception:
                continue
            self.db.delete(cleanup)
            reclaimed += 1
        self.db.flush()
        return reclaimed

    def _store_compile_result(
        self, version: ChatLatexPaperVersion, result: CompilerResult
    ) -> None:
        diagnostics = [item.model_dump(mode="json") for item in result.diagnostics]
        result_diagnostics = {
            "diagnostics": diagnostics,
            "job_id": result.job_id,
            "pdf_sha256": result.pdf_digest,
            "pdf_bytes": len(result.pdf) if result.pdf is not None else 0,
            "failure_category": result.failure_category,
        }
        if result.state != CompilerJobState.SUCCEEDED or result.pdf is None:
            version.compile_diagnostics = result_diagnostics
            version.compile_status = "failed"
            return
        if result.source_digest != version.source_digest:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "errors": [
                    {"severity": "error", "message": "Compiler source digest mismatch"}
                ]
            }
            return
        if len(result.pdf) > self.settings.chat_artifact_max_pdf_bytes:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "job_id": result.job_id,
                "failure_category": "output_too_large",
                "errors": [
                    {"severity": "error", "message": "Paper preview exceeds its bound"}
                ],
            }
            return
        previous_pdf_bytes = 0
        if isinstance(previous := version.compile_diagnostics, dict):
            previous_size = previous.get("pdf_bytes")
            if isinstance(previous_size, int) and previous_size > 0:
                previous_pdf_bytes = previous_size
        owner_id = self.db.scalar(
            select(ChatSession.hf_user_id)
            .join(ChatArtifact)
            .where(ChatArtifact.id == version.artifact_id)
        )
        if owner_id is None:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "job_id": result.job_id,
                "failure_category": "ownership_missing",
                "errors": [
                    {"severity": "error", "message": "Paper owner is unavailable"}
                ],
            }
            return
        lock_owner_artifact_quota(self.db, owner_id)
        try:
            self._require_owner_quota(
                owner_id,
                additional_pdf_bytes=max(0, len(result.pdf) - previous_pdf_bytes),
            )
        except ArtifactError as error:
            if error.code != "artifact_quota_exceeded":
                raise
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "job_id": result.job_id,
                "failure_category": "quota_exceeded",
                "errors": [
                    {
                        "severity": "error",
                        "message": "Paper storage quota would exceed 250 MiB",
                    }
                ],
            }
            return
        try:
            self.storage.write_file(
                f"{version.storage_key}/{_PREVIEW_PDF}", BytesIO(result.pdf)
            )
        except Exception as error:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "errors": [{"severity": "error", "message": "Preview storage failed"}]
            }
            raise ArtifactError(
                "artifact_storage_failed", "Paper preview storage failed"
            ) from error
        version.compile_diagnostics = result_diagnostics
        version.compile_status = "succeeded"
        version.compiled_pdf_path = _PREVIEW_PDF
        version.artifact.preview_head_version_id = version.id

    def delete_version(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        """Remove a non-head immutable version and reclaim only orphaned blobs."""
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        if version_id in {
            artifact.source_head_version_id,
            artifact.preview_head_version_id,
        }:
            raise ArtifactError(
                "artifact_invalid", "Current paper versions cannot be deleted"
            )
        version = self._version(owner_id, artifact_id, version_id)
        blob_digests = [
            blob.digest for blob in self._figure_blobs_for_version(version).values()
        ]
        self._cancel_pending_provider_jobs([version])
        self._schedule_storage_prefix_cleanup(version.storage_key)
        self.db.execute(
            delete(ChatLatexPaperFigureReference).where(
                ChatLatexPaperFigureReference.version_id == version.id
            )
        )
        self.db.execute(
            delete(ChatLatexPaperVersion).where(ChatLatexPaperVersion.id == version.id)
        )
        self.db.flush()
        self._delete_orphaned_blobs(blob_digests)
        artifact.latest_version = (
            self.db.scalar(
                select(func.max(ChatLatexPaperVersion.version)).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
            or 0
        )
        self.db.flush()

    def delete_project(self, owner_id: str, artifact_id: uuid.UUID) -> None:
        """Storage lifecycle hook for the later chat deletion policy."""
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        # The identity map can still retain an already-deleted historical row;
        # query the durable set so cleanup only follows live references.
        versions = list(
            self.db.scalars(
                select(ChatLatexPaperVersion).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
        )
        blob_digests = [
            blob.digest
            for version in versions
            for blob in self._figure_blobs_for_version(version).values()
        ]
        self._cancel_pending_provider_jobs(versions)
        for version in versions:
            self._schedule_storage_prefix_cleanup(version.storage_key)
        artifact.source_head_version_id = None
        artifact.preview_head_version_id = None
        self.db.flush()
        version_ids = [version.id for version in versions]
        if version_ids:
            self.db.execute(
                delete(ChatLatexPaperFigureReference).where(
                    ChatLatexPaperFigureReference.version_id.in_(version_ids)
                )
            )
            self.db.execute(
                delete(ChatLatexPaperVersion).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
        self.db.execute(delete(ChatArtifact).where(ChatArtifact.id == artifact.id))
        self.db.flush()
        self._delete_orphaned_blobs(blob_digests)

    def _cancel_pending_provider_jobs(
        self, versions: list[ChatLatexPaperVersion]
    ) -> None:
        """Best-effort deletion cleanup that never rebuilds source or resubmits."""

        provider_job_ids: list[str] = []
        for version in versions:
            if version.compile_status not in {"queued", "compiling"}:
                continue
            diagnostics = version.compile_diagnostics or {}
            provider_job_id = diagnostics.get("provider_job_id")
            if isinstance(provider_job_id, str) and provider_job_id:
                provider_job_ids.append(provider_job_id)
        if not provider_job_ids:
            return
        try:
            compiler = self.compiler or compiler_transport_from_settings(self.settings)
            cancel_provider_job = getattr(compiler, "cancel_provider_job", None)
            if not callable(cancel_provider_job):
                raise RuntimeError("Sandbox provider cancellation is unavailable")
        except (EnvelopeError, httpx.HTTPError, OSError, RuntimeError, ValueError):
            logger.warning(
                "latex_compiler_event "
                "event=delete_pending_sandbox_cancellation_unavailable"
            )
            return
        for provider_job_id in dict.fromkeys(provider_job_ids):
            try:
                cancel_provider_job(provider_job_id)
            except (EnvelopeError, httpx.HTTPError, OSError, RuntimeError, ValueError):
                # Deleting the durable paper must not strand its chat merely
                # because the already-disposable provider VM cannot be reached.
                logger.warning(
                    "latex_compiler_event "
                    "event=delete_pending_sandbox_cancellation_failed"
                )

    def _delete_orphaned_blobs(self, digests: list[str]) -> None:
        for digest in set(digests):
            self._lock_figure_blob(digest)
            blob = self.db.get(ChatLatexPaperFigureBlob, digest)
            if blob is None:
                continue
            if (
                self.db.scalar(
                    select(ChatLatexPaperFigureReference.version_id)
                    .where(ChatLatexPaperFigureReference.blob_digest == blob.digest)
                    .limit(1)
                )
                is not None
            ):
                continue
            self._schedule_storage_prefix_cleanup(
                "/".join(blob.storage_key.split("/")[:-1])
            )
            self.db.delete(blob)
        self.db.flush()

    def _lock_figure_blob(self, digest: str) -> None:
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:blob))"),
                {"blob": f"chat-latex-paper-figure:{digest}"},
            )

    def _schedule_storage_prefix_cleanup(self, prefix: str) -> None:
        """Delete immutable storage only after its DB ownership change commits."""
        pending = self.db.info.setdefault("latex_paper_cleanup_prefixes", set())
        pending.add(prefix)
        self.db.merge(ChatLatexPaperStorageCleanup(storage_prefix=prefix))
        if self.db.info.get("latex_paper_cleanup_listener"):
            return
        self.db.info["latex_paper_cleanup_listener"] = True

        def cleanup_after_commit(session: Session) -> None:
            prefixes = session.info.pop("latex_paper_cleanup_prefixes", set())
            session.info.pop("latex_paper_cleanup_listener", None)
            for stored_prefix in prefixes:
                try:
                    self.storage.delete_prefix(stored_prefix)
                except Exception:
                    continue
                try:
                    with Session(bind=session.bind) as cleanup_db:
                        cleanup_db.execute(
                            delete(ChatLatexPaperStorageCleanup).where(
                                ChatLatexPaperStorageCleanup.storage_prefix
                                == stored_prefix
                            )
                        )
                        cleanup_db.commit()
                except Exception:
                    # The object is already gone. Keep the durable queue item
                    # so the bounded reconciler can retry the DB acknowledgement.
                    continue

        def discard_after_rollback(session: Session) -> None:
            session.info.pop("latex_paper_cleanup_prefixes", None)
            session.info.pop("latex_paper_cleanup_listener", None)

        event.listen(self.db, "after_commit", cleanup_after_commit, once=True)
        event.listen(self.db, "after_rollback", discard_after_rollback, once=True)

    def _artifact(
        self, owner_id: str, artifact_id: uuid.UUID, *, lock: bool = False
    ) -> ChatArtifact:
        statement = (
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if lock:
            if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
                self.db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:artifact))"),
                    {"artifact": f"chat-latex-paper-write:{artifact_id}"},
                )
            statement = statement.with_for_update()
        artifact = self.db.scalar(statement)
        if artifact is None:
            raise ArtifactError("artifact_not_found", "Paper not found")
        return artifact

    def _version(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> ChatLatexPaperVersion:
        self._artifact(owner_id, artifact_id)
        version = self.db.scalar(
            select(ChatLatexPaperVersion).where(
                ChatLatexPaperVersion.id == version_id,
                ChatLatexPaperVersion.artifact_id == artifact_id,
                ChatLatexPaperVersion.storage_state == "ready",
            )
        )
        if version is None:
            raise ArtifactError("artifact_not_found", "Paper version not found")
        return version

    def _storage_prefix(
        self, session_id: uuid.UUID, artifact_id: uuid.UUID, *, version: int
    ) -> str:
        return "/".join(
            [
                self.settings.chat_artifact_hf_bucket_prefix.strip("/"),
                str(session_id),
                str(artifact_id),
                str(version),
            ]
        )
