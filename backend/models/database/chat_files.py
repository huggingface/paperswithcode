"""Files a user attached to a chat session."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.models.database.base import Base


class ChatUploadedFile(Base):
    """One uploaded file: our private copy plus the OpenAI Files copy.

    A row is ``pending`` from before the first byte is stored until both copies
    exist, so a crash leaves a row that cleanup can find and remove.
    """

    __tablename__ = "chat_uploaded_files"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_detail: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    openai_file_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'ready')", name="chat_uploaded_files_state_check"
        ),
        CheckConstraint(
            "pdf_detail IS NULL OR pdf_detail IN ('low', 'high')",
            name="chat_uploaded_files_detail_check",
        ),
        CheckConstraint("size_bytes > 0", name="chat_uploaded_files_size_check"),
        Index("idx_chat_uploaded_files_session", "session_id", "created_at"),
        Index("idx_chat_uploaded_files_owner", "hf_user_id", "state"),
    )
