"""Stable Hugging Face profiles, aliases, contribution history, and moderation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from backend.models.database import (
    CatalogMutationEvent,
    PendingPaperEdit,
    UserProfile,
    UserProfileAlias,
)

RESERVED_PROFILE_SLUGS = frozenset(
    {
        "admin-dashboard",
        "ai-deadlines",
        "api",
        "authors",
        "benchmark",
        "chat",
        "conferences",
        "cron-dashboard",
        "docs",
        "frameworks",
        "health",
        "methods",
        "organizations",
        "orgs",
        "paper",
        "papers",
        "privacy",
        "rate-limits",
        "saved",
        "settings",
        "share",
        "submit",
        "submissions",
        "task",
        "tasks",
        "topics",
        "trends",
    }
)


class UserProfileError(ValueError):
    pass


@dataclass(frozen=True)
class PrivateSubmissionProjection:
    id: int
    edit_type: str
    status: str
    proposed_payload: dict
    applied_payload: dict | None
    result_entity_type: str | None
    result_entity_id: str | None
    review_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None


@dataclass(frozen=True)
class ProfilePrivateView:
    is_owner: bool
    submissions: tuple[PrivateSubmissionProjection, ...]


def normalize_profile_username(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 255 or "/" in normalized:
        raise UserProfileError("Invalid Hugging Face username")
    return normalized


class UserProfileService:
    def __init__(self, db: Session):
        self.db = db

    def upsert_verified_identity(self, hf_subject: str, username: str) -> UserProfile:
        username = normalize_profile_username(username)
        profile = self.db.get(UserProfile, hf_subject)
        alias = self.db.get(UserProfileAlias, username)
        if alias is not None and alias.hf_subject != hf_subject:
            raise UserProfileError("Hugging Face username alias collision")
        if profile is None:
            profile = UserProfile(hf_subject=hf_subject, current_username=username)
            self.db.add(profile)
            self.db.flush()
        else:
            profile.current_username = username
        if alias is None:
            self.db.add(UserProfileAlias(alias=username, hf_subject=hf_subject))
        self.db.flush()
        return profile

    def resolve(self, username: str) -> tuple[UserProfile, bool]:
        username = normalize_profile_username(username)
        if username in RESERVED_PROFILE_SLUGS:
            raise UserProfileError("Reserved profile route")
        alias = self.db.get(UserProfileAlias, username)
        if alias is None:
            raise UserProfileError("Profile not found")
        profile = self.db.get(UserProfile, alias.hf_subject)
        if profile is None:
            raise UserProfileError("Profile not found")
        return profile, username != profile.current_username

    def private_view(
        self,
        *,
        profile_hf_subject: str,
        viewer_hf_subject: str | None,
    ) -> ProfilePrivateView:
        if viewer_hf_subject != profile_hf_subject:
            return ProfilePrivateView(is_owner=False, submissions=())

        rows = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.hf_subject == profile_hf_subject)
            .order_by(PendingPaperEdit.created_at.desc())
            .limit(200)
            .all()
        )
        return ProfilePrivateView(
            is_owner=True,
            submissions=tuple(
                PrivateSubmissionProjection(
                    id=row.id,
                    edit_type=row.edit_type,
                    status=row.status,
                    proposed_payload=row.proposed_payload,
                    applied_payload=row.applied_payload,
                    result_entity_type=row.result_entity_type,
                    result_entity_id=row.result_entity_id,
                    review_reason=row.user_review_reason,
                    created_at=row.created_at,
                    reviewed_at=row.reviewed_at,
                )
                for row in rows
            ),
        )

    def contribution_calendar(self, hf_subject: str) -> dict:
        end_date = date.today()
        start_date = end_date - timedelta(days=364)
        rollback = aliased(CatalogMutationEvent)
        rolled_back_event_ids = self.db.query(rollback.rollback_of_event_id).filter(
            rollback.rollback_of_event_id.isnot(None)
        )
        submission_rows = (
            self.db.query(
                func.date(PendingPaperEdit.reviewed_at), func.count(PendingPaperEdit.id)
            )
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.status == "approved",
                PendingPaperEdit.reviewed_at.isnot(None),
                PendingPaperEdit.reviewed_at
                >= datetime.combine(
                    start_date, datetime.min.time(), tzinfo=timezone.utc
                ),
                or_(
                    PendingPaperEdit.catalog_event_id.is_(None),
                    ~PendingPaperEdit.catalog_event_id.in_(rolled_back_event_ids),
                ),
            )
            .group_by(func.date(PendingPaperEdit.reviewed_at))
            .all()
        )
        direct_rows = (
            self.db.query(
                func.date(CatalogMutationEvent.created_at),
                func.count(CatalogMutationEvent.id),
            )
            .filter(
                CatalogMutationEvent.actor_hf_subject == hf_subject,
                CatalogMutationEvent.operation != "rollback",
                CatalogMutationEvent.created_at
                >= datetime.combine(
                    start_date, datetime.min.time(), tzinfo=timezone.utc
                ),
                ~CatalogMutationEvent.id.in_(rolled_back_event_ids),
            )
            .group_by(func.date(CatalogMutationEvent.created_at))
            .all()
        )
        counts: dict[str, int] = {}
        for day, count in [*submission_rows, *direct_rows]:
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            counts[key] = counts.get(key, 0) + count
        results = [{"date": day, "paper_count": counts[day]} for day in sorted(counts)]
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_count": sum(counts.values()),
            "results": results,
        }

    def moderation_snapshot(self, hf_subject: str, *, lock: bool = False) -> dict:
        query = self.db.query(UserProfile).filter(UserProfile.hf_subject == hf_subject)
        profile = query.with_for_update().first() if lock else query.first()
        if profile is None:
            raise UserProfileError("Profile not found")
        pending = (
            self.db.query(PendingPaperEdit.id, PendingPaperEdit.status)
            .filter(PendingPaperEdit.hf_subject == hf_subject)
            .order_by(PendingPaperEdit.id)
            .all()
        )
        return {
            "hf_subject": hf_subject,
            "is_submission_suspended": profile.is_submission_suspended,
            "suspension_reason": profile.suspension_reason,
            "suspended_at": profile.suspended_at,
            "suspended_by_hf_subject": profile.suspended_by_hf_subject,
            "submissions": [{"id": row.id, "status": row.status} for row in pending],
        }

    def suspend(
        self, *, hf_subject: str, suspended: bool, reason: str, actor: dict
    ) -> UserProfile:
        profile = self.db.get(UserProfile, hf_subject)
        if profile is None:
            raise UserProfileError("Profile not found")
        profile.is_submission_suspended = suspended
        profile.suspension_reason = reason.strip() or None
        profile.suspended_at = datetime.now(timezone.utc) if suspended else None
        profile.suspended_by_hf_subject = actor["hf_subject"] if suspended else None
        return profile

    def reject_active_as_spam(self, *, hf_subject: str, actor: dict) -> int:
        rows = (
            self.db.query(PendingPaperEdit)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.status == "pending",
            )
            .with_for_update()
            .all()
        )
        now = datetime.now(timezone.utc)
        for row in rows:
            row.status = "rejected"
            row.admin_note = (
                "Rejected as spam by a separately confirmed moderation action"
            )
            row.user_review_reason = "Rejected under the submission abuse policy."
            row.reviewed_by = actor.get("username")
            row.reviewed_by_kind = "human"
            row.reviewed_by_hf_subject = actor.get("hf_subject")
            row.reviewed_at = now
        return len(rows)
