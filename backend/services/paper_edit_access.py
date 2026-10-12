"""Paper-scoped authorization and account-wide publication limits."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from backend.models.database import (
    CatalogMutationEvent,
    PaperEditAccount,
    PaperEditAuthorization,
)
from backend.services.catalog_errors import (
    CatalogPermissionError,
    CatalogRateLimitError,
)

DAILY_PAPERS = 20
WRITES_PER_MINUTE = 30
EDIT_SECTIONS = frozenset(
    {
        "tasks",
        "methods",
        "organizations",
        "repositories",
        "project_pages",
        "hf_artifacts",
        "source_url",
        "x_threads",
    }
)


def token_hash(secret: str) -> str:
    return sha256(secret.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class PaperEditAccess:
    def __init__(self, db: Session):
        self.db = db

    def lock_account(self, subject: str) -> None:
        # Transaction-scoped and shared across all processes. Always acquire this
        # before a paper lock, including when suspending or approving a grant.
        if self.db.bind.dialect.name == "postgresql":
            key = int.from_bytes(
                sha256(f"paper-edit:{subject}".encode()).digest()[:8],
                "big",
                signed=True,
            )
            self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def check_account(self, subject: str) -> None:
        account = self.db.get(PaperEditAccount, subject, populate_existing=True)
        if account and account.suspended:
            raise CatalogPermissionError(
                {"code": "editing_suspended", "message": "Editing access is suspended"}
            )

    def authenticate(self, secret: str) -> dict:
        grant = self.db.scalar(
            select(PaperEditAuthorization).where(
                PaperEditAuthorization.token_hash == token_hash(secret)
            )
        )
        if (
            not grant
            or grant.revoked_at
            or utc(grant.expires_at) <= datetime.now(UTC)
            or not grant.hf_subject
        ):
            raise CatalogPermissionError(
                {
                    "code": "edit_authorization_expired",
                    "message": "Authorize this paper in your browser again",
                }
            )
        self.check_account(grant.hf_subject)
        from backend.utils.auth import role_for_hf_subject

        return {
            "quota_exempt": role_for_hf_subject(
                grant.hf_subject, username=grant.username
            )
            == "admin",
            "source": "paper_token",
            "role": "contributor",
            "hf_subject": grant.hf_subject,
            "username": grant.username,
            "paper_id": grant.paper_id,
            "authorization_id": str(grant.id),
            "session_iat": utc(grant.approved_at).timestamp()
            if grant.approved_at
            else 0,
        }

    def check_write(
        self,
        actor: dict,
        paper_id: int,
        entity_type: str,
        operation: str,
        payload: dict,
        *,
        now=None,
        limits=True,
    ) -> None:
        if actor["role"] == "admin":
            return
        self.lock_account(actor["hf_subject"])
        now = now or datetime.now(UTC)
        self.check_account(actor["hf_subject"])
        if actor.get("authorization_id"):
            import uuid

            grant = self.db.get(
                PaperEditAuthorization,
                uuid.UUID(actor["authorization_id"]),
                populate_existing=True,
            )
            if not grant or grant.revoked_at or utc(grant.expires_at) <= now:
                raise CatalogPermissionError("Paper authorization expired or revoked")
        if actor.get("paper_id", paper_id) != paper_id:
            raise CatalogPermissionError(
                "Authorization is limited to a different paper"
            )
        allowed = {
            "evaluation",
            "paper_edit_batch",
            *(f"paper_{section}" for section in EDIT_SECTIONS),
        }
        if (
            entity_type not in allowed
            or operation == "delete"
            or any(
                row.get("operation") == "delete"
                for row in payload.get("operations", [])
            )
        ):
            raise CatalogPermissionError(
                "This operation requires a catalog administrator"
            )
        if not limits or actor.get("quota_exempt"):
            return
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        base = select(CatalogMutationEvent).where(
            CatalogMutationEvent.actor_hf_subject == actor["hf_subject"],
            CatalogMutationEvent.paper_id.is_not(None),
        )
        papers = set(
            self.db.scalars(
                base.with_only_columns(CatalogMutationEvent.paper_id)
                .where(CatalogMutationEvent.created_at >= day)
                .distinct()
            )
        )
        if paper_id not in papers and len(papers) >= DAILY_PAPERS:
            raise CatalogRateLimitError(
                {
                    "code": "daily_paper_limit",
                    "message": "You may publish edits to 20 distinct papers per UTC day",
                }
            )
        count = self.db.scalar(
            base.with_only_columns(func.count()).where(
                CatalogMutationEvent.created_at >= now - timedelta(minutes=1)
            )
        )
        if count >= WRITES_PER_MINUTE:
            raise CatalogRateLimitError(
                {
                    "code": "edit_rate_limit",
                    "message": "At most 30 published batches per minute; retry shortly",
                }
            )

    def suspend(self, subject: str, suspended: bool, admin_subject: str) -> dict:
        self.lock_account(subject)
        account = self.db.get(PaperEditAccount, subject)
        if account is None:
            account = PaperEditAccount(hf_subject=subject)
            self.db.add(account)
        account.suspended = suspended
        account.updated_by = admin_subject
        account.updated_at = datetime.now(UTC)
        if suspended:
            self.db.execute(
                update(PaperEditAuthorization)
                .where(PaperEditAuthorization.hf_subject == subject)
                .values(revoked_at=datetime.now(UTC))
            )
        self.db.commit()
        return {"hf_subject": subject, "suspended": suspended}
