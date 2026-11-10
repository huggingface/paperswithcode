"""Public OpenReview submissions and their replies (reviews, decisions, ...)."""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class OpenReviewSubmission(Base):
    """One public OpenReview submission (a forum)."""

    __tablename__ = "openreview_submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    venue_id: Mapped[str] = mapped_column(String(200), nullable=False)
    conference_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("conferences.id", ondelete="SET NULL")
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[List[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    primary_area: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    venue: Mapped[Optional[str]] = mapped_column(Text)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL")
    )
    license: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("venue_id", "number"),
        Index(
            "idx_openreview_submissions_paper_id",
            "paper_id",
            postgresql_where=text("paper_id IS NOT NULL"),
        ),
        Index("idx_openreview_submissions_conference_id", "conference_id"),
    )


class OpenReviewNote(Base):
    """One public reply in a submission's forum: review, decision, comment."""

    __tablename__ = "openreview_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    forum_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("openreview_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    reply_to: Mapped[Optional[str]] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    invitation: Mapped[str] = mapped_column(String(100), nullable=False)
    signature: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger)
    confidence: Mapped[Optional[int]] = mapped_column(SmallInteger)
    license: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_openreview_notes_forum_id", "forum_id"),
        Index(
            "idx_openreview_notes_kind",
            "kind",
            postgresql_where=text("removed_at IS NULL"),
        ),
    )
