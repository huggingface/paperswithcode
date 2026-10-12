"""Organization, paper-organization, and organization trending persistence models."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.papers import Paper


class Organization(Base):
    """Normalized organization metadata (NVIDIA, Google, Meta, etc.).

    Organizations are sourced primarily from Hugging Face org profiles
    (``hf_url``) and used to tag papers by the lab/company behind them.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    hf_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    logo_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    logo_mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    logo_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    display_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_hf_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hf_paper_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_organizations", back_populates="organizations"
    )

    trending_history: Mapped[List["OrganizationTrendingHistory"]] = relationship(
        "OrganizationTrendingHistory",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index(
            "uq_organizations_hf_slug",
            "hf_slug",
            unique=True,
            postgresql_where=text("hf_slug IS NOT NULL"),
        ),
        Index(
            "idx_organizations_featured_trending",
            "is_featured",
            text("trending_score DESC"),
        ),
        Index("idx_organizations_featured_order", "is_featured", "display_order"),
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class PaperOrganization(Base):
    """Junction table linking papers to organizations."""

    __tablename__ = "paper_organizations"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    added_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    added_by_hf_username: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (
        Index("idx_paper_organizations_organization_id", "organization_id"),
        Index("idx_paper_organizations_paper_id", "paper_id"),
    )


class OrganizationTrendingHistory(Base):
    """One raw daily organization-momentum snapshot."""

    __tablename__ = "organization_trending_history"

    organization_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    raw_score: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="trending_history"
    )
