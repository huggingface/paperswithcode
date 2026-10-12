"""Conference, deadline, and paper-conference persistence models."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.papers import Paper


class Conference(Base):
    """Normalized conference metadata (CVPR, ICCV, NeurIPS, etc.)."""

    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DB-backed hero image (see Task.image_data for the deferred/flag rationale).
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_conferences", back_populates="conferences"
    )
    deadlines: Mapped[List["ConferenceDeadline"]] = relationship(
        "ConferenceDeadline",
        back_populates="conference",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_conferences_slug", "slug"),
        Index("idx_conferences_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<Conference(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class ConferenceDeadline(Base):
    """A submission/abstract/rebuttal deadline for a conference instance."""

    __tablename__ = "conference_deadlines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conferences.id", ondelete="CASCADE"),
        nullable=False,
    )
    deadline_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conference: Mapped["Conference"] = relationship(
        "Conference", back_populates="deadlines"
    )

    __table_args__ = (
        Index("idx_conference_deadlines_conference_id", "conference_id"),
        Index("idx_conference_deadlines_deadline_at", "deadline_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConferenceDeadline(id={self.id}, "
            f"conference_id={self.conference_id}, type='{self.deadline_type}')>"
        )


class PaperConference(Base):
    """Junction table linking papers to conferences."""

    __tablename__ = "paper_conferences"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    conference_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conferences.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    award: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_paper_conferences_conference_id", "conference_id"),
        Index("idx_paper_conferences_paper_id", "paper_id"),
        Index(
            "idx_paper_conferences_award",
            "conference_id",
            "award",
            postgresql_where=text("award IS NOT NULL"),
        ),
    )
