"""Framework catalog and task-framework persistence models."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.models.database.base import Base


class FrameworkDomain(Base):
    """Top-level grouping on the framework catalogue."""

    __tablename__ = "framework_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FrameworkCategory(Base):
    """Ordered framework category within a domain."""

    __tablename__ = "framework_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_domains.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    guide_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    guide_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "domain_id", "slug", name="framework_categories_domain_slug_key"
        ),
        Index("idx_framework_categories_domain_id", "domain_id"),
    )


class Framework(Base):
    """First-class software framework with canonical paper and repository."""

    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    introducing_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_frameworks_category_id", "category_id"),
        Index("idx_frameworks_repository_id", "repository_id"),
        Index("idx_frameworks_introducing_paper_id", "introducing_paper_id"),
    )


class FrameworkPlatform(Base):
    """Hardware platform supported by a framework."""

    __tablename__ = "framework_platforms"

    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(20), primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "platform IN ('gpu', 'cpu', 'apple')",
            name="framework_platforms_platform_check",
        ),
    )


class TaskFramework(Base):
    """Ordered first-class framework recommendations for a task."""

    __tablename__ = "task_frameworks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_task_frameworks_task_id", "task_id"),
        Index("idx_task_frameworks_framework_id", "framework_id"),
    )
