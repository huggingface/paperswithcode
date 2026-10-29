"""User profile, preference, bookmark, and staging-access persistence models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class UserBookmark(Base):
    """Per-HF-user paper bookmarks.

    Keyed on the HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Rows are removed via ``ON DELETE CASCADE`` when
    the underlying paper is deleted.
    """

    __tablename__ = "user_bookmarks"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_bookmarks_user", "hf_username"),
        Index("idx_user_bookmarks_paper", "paper_id"),
    )

    def __repr__(self) -> str:
        return f"<UserBookmark(hf_username='{self.hf_username}', paper_id={self.paper_id})>"


class UserPreference(Base):
    """Per-HF-user account preferences.

    Keyed on the lowercased HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Written exclusively through the
    ``/api/v1/me/preferences`` endpoints which require the session cookie.
    """

    __tablename__ = "user_preferences"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    # When True, the user hides closed-source model rows (Evaluation.is_open is
    # False) on benchmark leaderboards and paper evaluation tables.
    hide_closed_source_evals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # First time the user's saved papers were read from their HF Bucket. The
    # Bucket token lives in a per-browser cookie, so this tells other devices
    # to offer a reconnect instead of a fresh migration.
    saved_papers_bucket_migrated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserPreference(hf_username='{self.hf_username}', "
            f"hide_closed_source_evals={self.hide_closed_source_evals})>"
        )


class StagingAccessRequest(Base):
    """Verified Hugging Face accounts requesting contributor access."""

    __tablename__ = "staging_access_requests"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="staging_access_requests_status_check",
        ),
        CheckConstraint(
            "email IS NULL OR email_verified",
            name="staging_access_requests_verified_email_check",
        ),
        Index("idx_staging_access_requests_status_created", "status", "created_at"),
    )


class UserProfile(Base):
    """Stable Hugging Face identity and its current public username."""

    __tablename__ = "user_profiles"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    current_username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    is_submission_suspended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserProfileAlias(Base):
    __tablename__ = "user_profile_aliases"

    alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_subject: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("user_profiles.hf_subject", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_user_profile_aliases_subject", "hf_subject"),)


class AuthSession(Base):
    """Server-side handle of a browser session, so logout revokes copies.

    Production issues and revokes rows; staging only reads them to verify the
    shared production session it receives.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hf_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_auth_sessions_subject", "hf_subject"),
        Index("idx_auth_sessions_expires_at", "expires_at"),
    )
