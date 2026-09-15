"""Browser approval for a CLI device, yielding a one-hour paper credential."""

from datetime import UTC, datetime, timedelta
import secrets
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperEditAuthorization
from backend.services.catalog_errors import (
    CatalogNotFoundError,
    CatalogPermissionError,
    CatalogRateLimitError,
)
from backend.services.paper_edit_access import PaperEditAccess, token_hash, utc


class PaperEditAuthorizationService:
    def __init__(self, db: Session):
        self.db = db
        self.access = PaperEditAccess(db)

    def start(self, paper_id: int, client_key: str = "local") -> dict:
        if self.db.get(Paper, paper_id) is None:
            raise CatalogNotFoundError("Paper not found")
        now = datetime.now(UTC)
        # Bound anonymous storage even when a caller never opens the browser.
        self.access.lock_account("device-authorization-admission")
        self.db.execute(
            delete(PaperEditAuthorization).where(
                PaperEditAuthorization.expires_at < now - timedelta(days=1)
            )
        )
        pending = self.db.scalar(
            select(func.count())
            .select_from(PaperEditAuthorization)
            .where(
                PaperEditAuthorization.approved_at.is_(None),
                PaperEditAuthorization.expires_at > now,
            )
        )
        if pending >= 1000:
            raise CatalogRateLimitError(
                "Too many pending authorizations; try again shortly"
            )
        recent = self.db.scalar(
            select(func.count())
            .select_from(PaperEditAuthorization)
            .where(
                PaperEditAuthorization.client_key == client_key,
                PaperEditAuthorization.created_at >= now - timedelta(minutes=1),
            )
        )
        if recent >= 10:
            raise CatalogRateLimitError("At most 10 authorization requests per minute")
        device = secrets.token_urlsafe(32)
        row = PaperEditAuthorization(
            paper_id=paper_id,
            client_key=client_key,
            device_hash=token_hash(device),
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        self.db.add(row)
        self.db.commit()
        return {
            "device_code": device,
            "authorization_id": str(row.id),
            "user_code": row.id.hex[:8].upper(),
            "verification_path": f"/authorize-paper-edit/{row.id}",
            "expires_in": 600,
            "interval": 5,
        }

    def details(self, authorization_id: uuid.UUID) -> dict:
        row = self.db.get(PaperEditAuthorization, authorization_id)
        if row is None or row.revoked_at or utc(row.expires_at) <= datetime.now(UTC):
            raise CatalogNotFoundError(
                "Authorization expired or revoked; start again in the CLI"
            )
        paper = self.db.get(Paper, row.paper_id)
        return {
            "paper_id": row.paper_id,
            "title": paper.title if paper else str(row.paper_id),
            "user_code": row.id.hex[:8].upper(),
            "approved": row.approved_at is not None,
            "expires_at": row.expires_at,
        }

    def approve(self, authorization_id: uuid.UUID, actor: dict) -> dict:
        if actor.get("source") != "cookie":
            raise CatalogPermissionError("Approve access in your signed-in browser")
        self.access.lock_account(actor["hf_subject"])
        self.access.check_account(actor["hf_subject"])
        row = self.db.scalar(
            select(PaperEditAuthorization)
            .where(PaperEditAuthorization.id == authorization_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            row is None
            or row.revoked_at
            or row.approved_at
            or utc(row.expires_at) <= now
        ):
            raise CatalogPermissionError("Authorization already used or expired")
        row.hf_subject, row.username = actor["hf_subject"], actor["username"]
        row.approved_at, row.expires_at = now, now + timedelta(hours=1)
        self.db.commit()
        return {"status": "approved", "expires_at": row.expires_at}

    def exchange(self, device_code: str) -> dict:
        row = self.db.scalar(
            select(PaperEditAuthorization).where(
                PaperEditAuthorization.device_hash == token_hash(device_code)
            )
        )
        now = datetime.now(UTC)
        if row is None or row.revoked_at or utc(row.expires_at) <= now:
            raise CatalogPermissionError("Authorization expired or revoked")
        if not row.hf_subject:
            return {"status": "authorization_pending"}
        self.access.lock_account(row.hf_subject)
        self.access.check_account(row.hf_subject)
        row = self.db.scalar(
            select(PaperEditAuthorization)
            .where(PaperEditAuthorization.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row.revoked_at or row.token_hash or utc(row.expires_at) <= datetime.now(UTC):
            raise CatalogPermissionError(
                "Authorization already exchanged, revoked, or expired"
            )
        secret = secrets.token_urlsafe(32)
        row.token_hash = token_hash(secret)
        self.db.commit()
        return {
            "status": "authorized",
            "access_token": secret,
            "paper_id": row.paper_id,
            "expires_at": row.expires_at,
            "username": row.username,
        }

    def revoke(self, actor: dict) -> None:
        self.access.lock_account(actor["hf_subject"])
        row = self.db.get(PaperEditAuthorization, uuid.UUID(actor["authorization_id"]))
        row.revoked_at = datetime.now(UTC)
        self.db.commit()
