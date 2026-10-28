"""Private research interests and the durable digest outbox."""

from datetime import datetime
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
)
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
    topic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("research_topics.id")
    )
    topic_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchTopic(Base):
    """Free-text interest shared by every user who wrote the same normalized text."""

    __tablename__ = "research_topics"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    text: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(String(300), unique=True)
    backfill_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    backfill_total: Mapped[int | None] = mapped_column(Integer)
    backfill_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    backfill_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    backfill_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    backfill_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchTopicVerdict(Base):
    """Raw Jev relevance score; the feed applies the threshold when reading."""

    __tablename__ = "research_topic_verdicts"
    topic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("research_topics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float)
    card_sha: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(32))
    judged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
