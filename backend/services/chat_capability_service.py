"""Issue, validate, meter, and revoke opaque per-turn capabilities."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatTurnCapability
from backend.services.hf_inference_billing_service import (
    HfInferenceCredential,
    decrypt_credential,
    encrypt_credential,
)


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
        provider_token: str | None = None,
        provider_bill_to: str | None = None,
        provider_mode: str | None = None,
        provider_credential_revision: uuid.UUID | None = None,
        reasoning_effort: str = "high",
        settings: Settings | None = None,
        model: str,
        scopes: set[str],
        sdk_session_id: uuid.UUID | None = None,
        agent_harness: str = "claude",
        lifetime_seconds: int = 240,
    ) -> IssuedCapability:
        allowed = {
            "model",
            "catalog",
            "session_store",
            "web_fetch",
            "web_search",
            "hf_catalog",
            "artifact",
            "paper",
            "external_turn",
        }
        if not scopes or not scopes <= allowed:
            raise ValueError("Capability scopes are invalid")
        if reasoning_effort not in {"low", "medium", "high", "max"}:
            raise ValueError("Capability reasoning effort is invalid")
        if agent_harness not in {"claude", "pi"}:
            raise ValueError("Capability agent harness is invalid")
        if provider_mode not in {
            None,
            "huggingface",
            "openrouter_funded",
            "openrouter_byok",
            "openai_funded",
        }:
            raise ValueError("Capability provider mode is invalid")
        if provider_mode == "openai_funded" and any(
            value is not None
            for value in (
                provider_token,
                provider_bill_to,
                provider_credential_revision,
            )
        ):
            raise ValueError("Direct OpenAI capabilities cannot contain credentials")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=lifetime_seconds)
        row = ChatTurnCapability(
            id=uuid.uuid4(),
            token_hash=_digest(token),
            chat_session_id=chat_session_id,
            turn_id=turn_id,
            agent_harness=agent_harness,
            sdk_session_id=sdk_session_id,
            owner_hash=_digest(owner_id),
            provider_token_encrypted=(
                encrypt_credential(
                    HfInferenceCredential(provider_token, provider_bill_to),
                    _digest(owner_id),
                    settings,
                )
                if provider_token and settings
                else None
            ),
            provider_mode=provider_mode,
            reasoning_effort=reasoning_effort,
            provider_credential_revision=provider_credential_revision,
            model=model,
            scopes=sorted(scopes),
            nonce=secrets.token_hex(16),
            expires_at=expires_at,
        )
        self.db.add(row)
        self.db.flush()
        return IssuedCapability(token, row.id, expires_at)

    @staticmethod
    def provider_token(
        row: ChatTurnCapability, owner_id: str, settings: Settings
    ) -> str | None:
        if not row.provider_token_encrypted:
            return None
        credential = ChatCapabilityService.provider_credential(row, owner_id, settings)
        return credential.token if credential else None

    @staticmethod
    def provider_credential(
        row: ChatTurnCapability, owner_id: str, settings: Settings
    ) -> HfInferenceCredential | None:
        if not row.provider_token_encrypted:
            return None
        return decrypt_credential(row.provider_token_encrypted, owner_id, settings)

    def validate(
        self,
        token: str,
        *,
        scope: str,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        model: str | None = None,
        agent_harness: str | None = None,
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
            or (agent_harness is not None and row.agent_harness != agent_harness)
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

    def meter_web_search(
        self, row: ChatTurnCapability, *, maximum_searches: int
    ) -> None:
        if row.web_search_failed or row.web_search_calls >= maximum_searches:
            raise CapabilityError("Web search limit reached")
        row.web_search_calls += 1
        self.db.flush()

    def fail_web_search(self, row: ChatTurnCapability) -> None:
        row.web_search_failed = True
        self.db.flush()

    def meter_hf_catalog(
        self,
        row: ChatTurnCapability,
        *,
        recursive: bool,
        maximum_calls: int,
        maximum_recursive_calls: int,
    ) -> None:
        if row.hf_catalog_calls >= maximum_calls:
            raise CapabilityError("HF catalog limit reached")
        if recursive and row.hf_recursive_list_calls >= maximum_recursive_calls:
            raise CapabilityError("HF recursive list limit reached")
        row.hf_catalog_calls += 1
        if recursive:
            row.hf_recursive_list_calls += 1
        self.db.flush()

    def revoke(self, capability_id: uuid.UUID) -> bool:
        row = self.db.get(ChatTurnCapability, capability_id)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
        self.db.flush()
        return True

    def record_provider_error(self, row: ChatTurnCapability, code: str) -> None:
        row.provider_error_code = code
        self.db.flush()

    def provider_error_for_turn(
        self, chat_session_id: uuid.UUID, turn_id: uuid.UUID
    ) -> str | None:
        return self.db.scalar(
            select(ChatTurnCapability.provider_error_code)
            .where(
                ChatTurnCapability.chat_session_id == chat_session_id,
                ChatTurnCapability.turn_id == turn_id,
                ChatTurnCapability.provider_error_code.is_not(None),
            )
            .order_by(ChatTurnCapability.created_at.desc())
            .limit(1)
        )
