"""Issue, validate, meter, and revoke opaque per-turn capabilities."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import ChatTurnCapability


class CapabilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedCapability:
    token: str
    capability_id: uuid.UUID
    expires_at: datetime


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ChatCapabilityService:
    def __init__(self, db: Session):
        self.db = db

    def issue(
        self,
        *,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        owner_id: str,
        model: str,
        scopes: set[str],
        sdk_session_id: uuid.UUID | None = None,
        lifetime_seconds: int = 240,
    ) -> IssuedCapability:
        allowed = {"model", "catalog", "session_store"}
        if not scopes or not scopes <= allowed:
            raise ValueError("Capability scopes are invalid")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=lifetime_seconds)
        row = ChatTurnCapability(
            id=uuid.uuid4(),
            token_hash=_digest(token),
            chat_session_id=chat_session_id,
            turn_id=turn_id,
            sdk_session_id=sdk_session_id,
            owner_hash=_digest(owner_id),
            model=model,
            scopes=sorted(scopes),
            nonce=secrets.token_hex(16),
            expires_at=expires_at,
        )
        self.db.add(row)
        self.db.flush()
        return IssuedCapability(token, row.id, expires_at)

    def validate(
        self,
        token: str,
        *,
        scope: str,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        model: str | None = None,
        gateway_call_limit: int = 64,
    ) -> ChatTurnCapability:
        row = self.db.execute(
            select(ChatTurnCapability)
            .where(ChatTurnCapability.token_hash == _digest(token))
            .with_for_update()
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            row is None
            or row.revoked_at is not None
            or row.expires_at <= now
            or row.chat_session_id != chat_session_id
            or row.turn_id != turn_id
            or scope not in row.scopes
            or (model is not None and row.model != model)
        ):
            raise CapabilityError("Capability is invalid, expired, or out of scope")
        if row.gateway_calls >= gateway_call_limit:
            raise CapabilityError("Gateway call limit reached")
        row.gateway_calls += 1
        self.db.flush()
        return row

    def meter_provider(
        self,
        row: ChatTurnCapability,
        *,
        request_tokens: int,
        maximum_requests: int,
        maximum_tokens: int,
    ) -> None:
        if row.provider_requests >= maximum_requests:
            raise CapabilityError("Provider request limit reached")
        if row.provider_tokens + request_tokens > maximum_tokens:
            raise CapabilityError("Provider token limit reached")
        row.provider_requests += 1
        row.provider_tokens += request_tokens
        self.db.flush()

    def meter_catalog(
        self,
        row: ChatTurnCapability,
        operation: str,
        *,
        maximum_searches: int,
    ) -> None:
        if operation == "search":
            if row.catalog_search_calls >= maximum_searches:
                raise CapabilityError("Catalog search limit reached")
            row.catalog_search_calls += 1
        self.db.flush()

    def revoke(self, capability_id: uuid.UUID) -> bool:
        row = self.db.get(ChatTurnCapability, capability_id)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
        self.db.flush()
        return True
