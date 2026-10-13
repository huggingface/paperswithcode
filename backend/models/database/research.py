"""Private research interests and the durable digest outbox."""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, BigInteger, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from backend.models.database.base import Base


class ResearchFollow(Base):
    __tablename__ = "research_follows"
    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchSubscription(Base):
    __tablename__ = "research_subscriptions"
    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True)


class ResearchSuppression(Base):
    __tablename__ = "research_suppressions"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    reason: Mapped[str] = mapped_column(String(32))


class ResearchDigest(Base):
    __tablename__ = "research_digests"
    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payload: Mapped[dict] = mapped_column(JSON)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[str | None] = mapped_column(Text)


class ResearchEvent(Base):
    """Insert-only catalog discovery; corrections do not advance discovery time."""

    __tablename__ = "research_events"
    event_key: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_key: Mapped[str] = mapped_column(Text, index=True)
    paper_id: Mapped[int] = mapped_column(BigInteger)
    evaluation_id: Mapped[int | None] = mapped_column(BigInteger)
    dataset_id: Mapped[int | None] = mapped_column(BigInteger)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
