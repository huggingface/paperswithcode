"""Chat artifact and LaTeX paper persistence models."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.chat import ChatMessageRecord, ChatSession


class ChatArtifact(Base):
    """Stable identity for one private, typed chat artifact."""

    __tablename__ = "chat_artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    identifier: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    latest_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # LaTeX-paper heads are independent: a failed source can retain a prior
    # successful preview without ever associating that PDF with new source.
    # They stay NULL for all legacy and current Posterly rows.
    source_head_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    preview_head_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSession"] = relationship(back_populates="artifacts")
    versions: Mapped[list["ChatArtifactVersion"]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ChatArtifactVersion.artifact_id",
    )
    paper_versions: Mapped[list["ChatLatexPaperVersion"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan", passive_deletes=True
    )
    __table_args__ = (
        CheckConstraint(
            "kind IN ('posterly', 'latex_paper')", name="chat_artifacts_kind_check"
        ),
        CheckConstraint("latest_version >= 0", name="chat_artifacts_version_check"),
        UniqueConstraint(
            "session_id", "identifier", name="uq_chat_artifacts_session_identifier"
        ),
        Index("idx_chat_artifacts_session", "session_id", "created_at"),
        Index(
            "uq_chat_artifacts_session_latex_paper",
            "session_id",
            unique=True,
            postgresql_where=text("kind = 'latex_paper'"),
            sqlite_where=text("kind = 'latex_paper'"),
        ),
    )


class ChatArtifactVersion(Base):
    """One immutable, content-addressed Posterly publication."""

    __tablename__ = "chat_artifact_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bundle_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    preview_path: Mapped[str] = mapped_column(String(300), nullable=False)
    preview_mime: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_status: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    artifact: Mapped[ChatArtifact] = relationship(
        back_populates="versions", foreign_keys=[artifact_id]
    )
    message: Mapped[Optional["ChatMessageRecord"]] = relationship(
        back_populates="artifact_versions"
    )
    __table_args__ = (
        CheckConstraint("version >= 1", name="chat_artifact_versions_number_check"),
        CheckConstraint("byte_count >= 0", name="chat_artifact_versions_bytes_check"),
        CheckConstraint(
            "gate_status IN ('passed','warnings','failed')",
            name="chat_artifact_versions_gate_check",
        ),
        CheckConstraint(
            "state IN ('uploading','ready','failed','deleting')",
            name="chat_artifact_versions_state_check",
        ),
        UniqueConstraint(
            "artifact_id", "version", name="uq_chat_artifact_versions_number"
        ),
        UniqueConstraint(
            "artifact_id", "bundle_digest", name="uq_chat_artifact_versions_digest"
        ),
        Index("idx_chat_artifact_versions_turn", "turn_id"),
        Index("idx_chat_artifact_versions_message", "message_id"),
    )


class ChatLatexPaperVersion(Base):
    """Immutable LaTeX source version with a separately tracked compile result."""

    __tablename__ = "chat_latex_paper_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_latex_paper_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    turn_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_pdf_path: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    storage_state: Mapped[str] = mapped_column(String(16), nullable=False)
    compile_status: Mapped[str] = mapped_column(String(16), nullable=False)
    compile_diagnostics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    display_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generation_provenance: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    artifact: Mapped[ChatArtifact] = relationship(back_populates="paper_versions")
    parent_version: Mapped[Optional["ChatLatexPaperVersion"]] = relationship(
        remote_side=[id], foreign_keys=[parent_version_id]
    )
    figure_references: Mapped[list["ChatLatexPaperFigureReference"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", passive_deletes=True
    )
    message: Mapped[Optional["ChatMessageRecord"]] = relationship()
    __table_args__ = (
        CheckConstraint("version >= 1", name="chat_latex_paper_versions_number_check"),
        CheckConstraint(
            "source_byte_count >= 0", name="chat_latex_paper_versions_bytes_check"
        ),
        CheckConstraint(
            "length(source_digest) = 64",
            name="chat_latex_paper_versions_source_digest_check",
        ),
        CheckConstraint(
            "storage_state IN ('uploading','ready','failed','deleting')",
            name="chat_latex_paper_versions_storage_state_check",
        ),
        CheckConstraint(
            "compile_status IN ('queued','compiling','succeeded','failed')",
            name="chat_latex_paper_versions_compile_status_check",
        ),
        CheckConstraint(
            "(compile_status = 'succeeded' AND compiled_pdf_path IS NOT NULL) "
            "OR (compile_status <> 'succeeded' AND compiled_pdf_path IS NULL)",
            name="chat_latex_paper_versions_preview_check",
        ),
        CheckConstraint(
            "actor_type IN ('ai','human','restore')",
            name="chat_latex_paper_versions_actor_type_check",
        ),
        UniqueConstraint(
            "artifact_id", "version", name="uq_chat_latex_paper_versions_number"
        ),
        Index("idx_chat_latex_paper_versions_turn", "turn_id"),
        Index("idx_chat_latex_paper_versions_message", "message_id"),
    )


class ChatLatexPaperFigureBlob(Base):
    """One private content-addressed figure, shared by immutable paper versions."""

    __tablename__ = "chat_latex_paper_figure_blobs"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    references: Mapped[list["ChatLatexPaperFigureReference"]] = relationship(
        back_populates="blob", passive_deletes=True
    )
    __table_args__ = (
        CheckConstraint(
            "length(digest) = 64", name="chat_latex_paper_figure_blobs_digest_check"
        ),
        CheckConstraint(
            "byte_count > 0", name="chat_latex_paper_figure_blobs_bytes_check"
        ),
        CheckConstraint(
            "media_type IN ('image/png','image/jpeg','application/pdf')",
            name="chat_latex_paper_figure_blobs_type_check",
        ),
    )


class ChatLatexPaperFigureReference(Base):
    """A safe source-tree path from one immutable version to a figure blob."""

    __tablename__ = "chat_latex_paper_figure_references"

    version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_latex_paper_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    path: Mapped[str] = mapped_column(String(300), primary_key=True)
    blob_digest: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chat_latex_paper_figure_blobs.digest", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped["ChatLatexPaperVersion"] = relationship(
        back_populates="figure_references"
    )
    blob: Mapped["ChatLatexPaperFigureBlob"] = relationship(back_populates="references")
    __table_args__ = (
        CheckConstraint(
            "length(blob_digest) = 64", name="chat_latex_paper_figure_refs_digest_check"
        ),
        Index("idx_chat_latex_paper_figure_refs_digest", "blob_digest"),
    )


class ChatLatexPaperStorageCleanup(Base):
    """A retriable private-prefix deletion scheduled after a paper DB commit."""

    __tablename__ = "chat_latex_paper_storage_cleanup"

    storage_prefix: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
