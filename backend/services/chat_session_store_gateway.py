"""Atomic capability-scoped Agent SDK SessionStore operations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk._internal.session_store import project_key_for_directory
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatSession, ChatTurnCapability
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore

EXPECTED_PROJECT_KEY = project_key_for_directory("/workspace")


class SessionStoreGatewayError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SessionStoreCommand:
    action: str
    key: dict[str, Any] | None
    entries: list[dict[str, Any]] | None
    project_key: str | None


class ChatSessionStoreGateway:
    ACTIONS = {
        "append",
        "load",
        "list_sessions",
        "list_session_summaries",
        "list_subkeys",
    }

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def execute(
        self,
        capability: ChatTurnCapability,
        command: SessionStoreCommand,
    ) -> Any:
        self._validate_shape(command)
        chat = self.db.execute(
            select(ChatSession)
            .where(ChatSession.id == capability.chat_session_id)
            .with_for_update()
        ).scalar_one_or_none()
        if chat is None:
            raise SessionStoreGatewayError(403, "Session store scope rejected")

        key = self._bind_key(capability, chat, command.key)
        if command.project_key not in {None, EXPECTED_PROJECT_KEY}:
            raise SessionStoreGatewayError(403, "Session store scope rejected")

        if command.action == "append":
            assert key is not None
            self._lock_owner_quota(chat.hf_user_id)
            PostgresSDKSessionStore.append_in_session(
                self.db, key, command.entries or []
            )
            self.db.flush()
            self._enforce_quota(chat)
            return None
        if command.action == "load":
            assert key is not None
            return PostgresSDKSessionStore.load_in_session(self.db, key)
        if command.action == "list_subkeys":
            assert key is not None
            return PostgresSDKSessionStore.list_subkeys_in_session(self.db, key)

        if capability.sdk_session_id is None:
            return []
        if command.action == "list_sessions":
            rows = PostgresSDKSessionStore.list_sessions_in_session(
                self.db, EXPECTED_PROJECT_KEY
            )
        else:
            rows = PostgresSDKSessionStore.list_session_summaries_in_session(
                self.db, EXPECTED_PROJECT_KEY
            )
        expected_session = str(capability.sdk_session_id)
        return [row for row in rows if row.get("session_id") == expected_session]

    def _validate_shape(self, command: SessionStoreCommand) -> None:
        if command.action not in self.ACTIONS:
            raise SessionStoreGatewayError(422, "Unsupported session store action")
        uses_key = command.action in {"append", "load", "list_subkeys"}
        if uses_key != (command.key is not None):
            raise SessionStoreGatewayError(422, "Invalid session store key")
        uses_project = command.action in {
            "list_sessions",
            "list_session_summaries",
        }
        if uses_project != (command.project_key is not None):
            raise SessionStoreGatewayError(422, "Invalid session store project")
        if command.action == "append":
            entries = command.entries
            if entries is None:
                raise SessionStoreGatewayError(
                    422, "Session append entries are required"
                )
            append_bytes = len(json.dumps(entries, ensure_ascii=False).encode())
            if len(entries) > 128 or append_bytes > 512 * 1024:
                raise SessionStoreGatewayError(413, "Session append is too large")
        elif command.entries is not None:
            raise SessionStoreGatewayError(422, "Entries are only valid for append")

    def _bind_key(
        self,
        capability: ChatTurnCapability,
        chat: ChatSession,
        key: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if key is None:
            return None
        if set(key) - {"project_key", "session_id", "subpath"}:
            raise SessionStoreGatewayError(422, "Invalid session store key")
        if key.get("project_key") != EXPECTED_PROJECT_KEY:
            raise SessionStoreGatewayError(403, "Session store scope rejected")
        subpath = key.get("subpath", "")
        if (
            not isinstance(subpath, str)
            or len(subpath) > 500
            or ".." in subpath.split("/")
        ):
            raise SessionStoreGatewayError(422, "Invalid session subpath")
        try:
            candidate = uuid.UUID(str(key["session_id"]))
        except (KeyError, ValueError):
            raise SessionStoreGatewayError(422, "Invalid SDK session") from None
        if capability.sdk_session_id not in {None, candidate}:
            raise SessionStoreGatewayError(403, "Session store scope rejected")
        if chat.sdk_session_id not in {None, candidate}:
            raise SessionStoreGatewayError(403, "Session store scope rejected")
        capability.sdk_session_id = candidate
        chat.sdk_session_id = candidate
        chat.sdk_project_key = EXPECTED_PROJECT_KEY
        chat.transcript_status = "ready"
        return {
            "project_key": EXPECTED_PROJECT_KEY,
            "session_id": str(candidate),
            "subpath": subpath,
        }

    def _lock_owner_quota(self, owner_id: str) -> None:
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(
                        f"chat-storage:{owner_id}",
                        0,
                    )
                )
            )
        )

    def _enforce_quota(self, chat: ChatSession) -> None:
        self.db.refresh(chat)
        owner_total = (
            self.db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            ChatSession.transcript_bytes + ChatSession.projection_bytes
                        ),
                        0,
                    )
                ).where(ChatSession.hf_user_id == chat.hf_user_id)
            )
            or 0
        )
        if (
            chat.transcript_bytes + chat.projection_bytes
            > self.settings.chat_session_byte_limit
            or owner_total > self.settings.chat_user_byte_limit
        ):
            raise SessionStoreGatewayError(409, "Chat storage quota reached")
