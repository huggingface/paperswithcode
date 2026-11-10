"""Voice dictation ticket and metering persistence."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database.base import Base


class DictationSession(Base):
    """One single-use dictation WebSocket ticket and the seconds it was charged."""

    __tablename__ = "dictation_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    hf_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    ticket_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    used_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('voxtral','openai')", name="dictation_sessions_provider_check"
        ),
        CheckConstraint(
            "max_seconds > 0 AND (used_seconds IS NULL OR used_seconds BETWEEN 0 AND max_seconds)",
            name="dictation_sessions_seconds_check",
        ),
        Index("idx_dictation_sessions_subject_issued", "hf_subject", "issued_at"),
        Index("idx_dictation_sessions_provider_connected", "provider", "connected_at"),
    )
