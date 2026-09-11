"""Bounded opaque persistence for native Pi JSONL sessions."""

from __future__ import annotations

import json
import uuid
from base64 import b64decode, b64encode
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatPiPreparedFork,
    ChatPiSession,
    ChatPiTranscriptEntry,
    ChatSession,
)

MAX_APPEND_ENTRIES = 128
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRY_TYPE_CHARS = 64
FORMAT_VERSION = 1
_PATH_METADATA_TYPES = {"session", "model_change", "thinking_level_change"}
_OPAQUE_ENTRY_KEY = "__pwc_pi_native_json_b64_v1"


class PiTranscriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class PiSessionSnapshot:
    agent_session_id: uuid.UUID
    chat_session_id: uuid.UUID
    current_leaf_id: str | None
    entry_count: int
    byte_size: int
    format_version: int
    entries: tuple[dict[str, Any], ...]


def _serialized(entry: object) -> tuple[dict[str, Any], int]:
    if not isinstance(entry, dict):
        raise PiTranscriptError("Pi transcript entry must be an object")
    raw = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode()
    if not 2 <= len(raw) <= MAX_ENTRY_BYTES:
        raise PiTranscriptError("Pi transcript entry is outside the byte limit")
    return entry, len(raw)


def _database_entry(entry: dict[str, Any]) -> dict[str, str]:
    """Encode native JSON losslessly for PostgreSQL JSONB, which rejects NUL."""

    raw = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode()
    return {_OPAQUE_ENTRY_KEY: b64encode(raw).decode("ascii")}


def _native_entry(entry: dict[str, Any]) -> dict[str, Any]:
    encoded = entry.get(_OPAQUE_ENTRY_KEY)
    if encoded is None:
        return entry
    if set(entry) != {_OPAQUE_ENTRY_KEY} or not isinstance(encoded, str):
        raise PiTranscriptError("Pi transcript storage envelope is invalid")
    try:
        decoded = json.loads(b64decode(encoded, validate=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise PiTranscriptError("Pi transcript storage envelope is invalid") from error
    if not isinstance(decoded, dict):
        raise PiTranscriptError("Pi transcript storage envelope is invalid")
    return decoded


def _envelope(entry: dict[str, Any]) -> tuple[str | None, str | None, str]:
    entry_id = entry.get("id")
    parent_id = entry.get("parentId")
    entry_type = entry.get("type")
    if entry_id is not None and (not isinstance(entry_id, str) or not entry_id):
        raise PiTranscriptError("Pi transcript entry id is invalid")
    if parent_id is not None and (not isinstance(parent_id, str) or not parent_id):
        raise PiTranscriptError("Pi transcript parent id is invalid")
    if (
        not isinstance(entry_type, str)
        or not entry_type
        or len(entry_type) > MAX_ENTRY_TYPE_CHARS
    ):
        raise PiTranscriptError("Pi transcript entry type is invalid")
    if entry_type == "session":
        # Pi's session header has its own session id, not a tree entry id.
        return None, None, entry_type
    return entry_id, parent_id, entry_type


class ChatPiTranscriptService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _pi_chat(
        self, chat_session_id: uuid.UUID, *, lock: bool = False
    ) -> ChatSession:
        query = select(ChatSession).where(ChatSession.id == chat_session_id)
        if lock:
            query = query.with_for_update()
        chat = self.db.execute(query).scalar_one_or_none()
        if chat is None or getattr(chat, "agent_harness", "claude") != "pi":
            raise PiTranscriptError("Pi transcript ownership mismatch")
        return chat

    def create_or_bind_session(
        self, chat_session_id: uuid.UUID, agent_session_id: uuid.UUID
    ) -> ChatPiSession:
        chat = self._pi_chat(chat_session_id, lock=True)
        row = self.db.execute(
            select(ChatPiSession)
            .where(ChatPiSession.chat_session_id == chat_session_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is not None:
            # A failed reusable-sandbox assignment may have durably created the
            # native session before the coordinator retries the same admitted
            # turn in a replacement sandbox. Return that binding so the new
            # worker restores it instead of inventing a conflicting transcript.
            return row
        if chat.sdk_session_id not in {None, agent_session_id}:
            raise PiTranscriptError("Chat already has a different agent session")
        row = ChatPiSession(
            agent_session_id=agent_session_id,
            chat_session_id=chat_session_id,
            current_leaf_id=None,
            entry_count=0,
            byte_size=0,
            format_version=FORMAT_VERSION,
        )
        chat.sdk_session_id = agent_session_id
        chat.sdk_project_key = None
        chat.transcript_status = "pending"
        self.db.add(row)
        self.db.flush()
        return row

    def prebind_new_session(
        self, chat: ChatSession, agent_session_id: uuid.UUID | None = None
    ) -> ChatPiSession:
        """Bind a freshly-created external Pi chat inside its admission transaction."""
        if (
            getattr(chat, "agent_harness", "claude") != "pi"
            or chat.sdk_session_id is not None
        ):
            raise PiTranscriptError("Pi session cannot be prebound")
        bound_id = agent_session_id or uuid.uuid4()
        row = ChatPiSession(
            agent_session_id=bound_id,
            chat_session_id=chat.id,
            current_leaf_id=None,
            entry_count=0,
            byte_size=0,
            format_version=FORMAT_VERSION,
        )
        chat.sdk_session_id = bound_id
        chat.sdk_project_key = None
        chat.transcript_status = "pending"
        self.db.add(row)
        return row

    def append_entries(
        self,
        chat_session_id: uuid.UUID,
        agent_session_id: uuid.UUID,
        entries: list[dict[str, Any]],
        *,
        current_leaf_id: str | None,
    ) -> ChatPiSession:
        if not 1 <= len(entries) <= MAX_APPEND_ENTRIES:
            raise PiTranscriptError("Pi transcript append batch is outside the limit")
        chat = self._pi_chat(chat_session_id, lock=True)
        row = self.create_or_bind_session(chat_session_id, agent_session_id)
        row = self.db.execute(
            select(ChatPiSession)
            .where(ChatPiSession.agent_session_id == agent_session_id)
            .with_for_update()
        ).scalar_one()
        parsed: list[tuple[int, dict[str, Any], int, str | None, str | None, str]] = []
        for item in entries:
            if not isinstance(item, dict) or set(item) != {"ordinal", "entry"}:
                raise PiTranscriptError("Pi transcript append envelope is invalid")
            ordinal = item["ordinal"]
            if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
                raise PiTranscriptError("Pi transcript ordinal is invalid")
            entry, byte_size = _serialized(item["entry"])
            entry_id, parent_id, entry_type = _envelope(entry)
            parsed.append((ordinal, entry, byte_size, entry_id, parent_id, entry_type))
        parsed.sort(key=lambda value: value[0])
        if len({value[0] for value in parsed}) != len(parsed):
            raise PiTranscriptError("Pi transcript append has duplicate ordinals")

        added_bytes = 0
        added_count = 0
        expected_ordinal = row.entry_count
        for ordinal, entry, byte_size, entry_id, parent_id, entry_type in parsed:
            existing = self.db.execute(
                select(ChatPiTranscriptEntry).where(
                    ChatPiTranscriptEntry.agent_session_id == agent_session_id,
                    ChatPiTranscriptEntry.ordinal == ordinal,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if _native_entry(existing.entry) != entry:
                    raise PiTranscriptError("Pi transcript ordinal conflicts")
                continue
            if ordinal != expected_ordinal:
                raise PiTranscriptError("Pi transcript ordinal is not contiguous")
            if ordinal == 0 and entry_type != "session":
                raise PiTranscriptError("Pi transcript header is missing")
            if ordinal == 0 and str(entry.get("id") or "") != str(agent_session_id):
                raise PiTranscriptError("Pi transcript header identity mismatches")
            expected_ordinal += 1
            if entry_id is not None:
                duplicate = self.db.execute(
                    select(ChatPiTranscriptEntry.id).where(
                        ChatPiTranscriptEntry.agent_session_id == agent_session_id,
                        ChatPiTranscriptEntry.entry_id == entry_id,
                    )
                ).scalar_one_or_none()
                if duplicate is not None:
                    raise PiTranscriptError("Pi transcript entry id conflicts")
            self.db.add(
                ChatPiTranscriptEntry(
                    agent_session_id=agent_session_id,
                    ordinal=ordinal,
                    entry_id=entry_id,
                    parent_entry_id=parent_id,
                    entry_type=entry_type,
                    entry=_database_entry(entry),
                    byte_size=byte_size,
                )
            )
            added_bytes += byte_size
            added_count += 1

        owner_bytes = (
            self.db.scalar(
                select(func.coalesce(func.sum(ChatPiSession.byte_size), 0))
                .join(ChatSession, ChatSession.id == ChatPiSession.chat_session_id)
                .where(ChatSession.hf_user_id == chat.hf_user_id)
            )
            or 0
        )
        if row.byte_size + added_bytes > self.settings.chat_session_byte_limit:
            raise PiTranscriptError("Pi transcript session quota exceeded")
        if owner_bytes + added_bytes > self.settings.chat_user_byte_limit:
            raise PiTranscriptError("Pi transcript owner quota exceeded")
        if current_leaf_id is not None:
            known = (
                current_leaf_id
                in {value[3] for value in parsed if value[3] is not None}
                or self.db.execute(
                    select(ChatPiTranscriptEntry.id).where(
                        ChatPiTranscriptEntry.agent_session_id == agent_session_id,
                        ChatPiTranscriptEntry.entry_id == current_leaf_id,
                    )
                ).scalar_one_or_none()
                is not None
            )
            if not known:
                raise PiTranscriptError("Pi current leaf is not durable")
        row.entry_count += added_count
        row.byte_size += added_bytes
        row.current_leaf_id = current_leaf_id
        chat.transcript_bytes = row.byte_size
        chat.transcript_status = "ready"
        self.db.flush()
        return row

    def load_session(
        self, chat_session_id: uuid.UUID, agent_session_id: uuid.UUID
    ) -> PiSessionSnapshot:
        self._pi_chat(chat_session_id)
        row = self.db.execute(
            select(ChatPiSession).where(
                ChatPiSession.agent_session_id == agent_session_id,
                ChatPiSession.chat_session_id == chat_session_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise PiTranscriptError("Pi session was not found")
        entries = tuple(
            _native_entry(item.entry)
            for item in self.db.execute(
                select(ChatPiTranscriptEntry)
                .where(ChatPiTranscriptEntry.agent_session_id == agent_session_id)
                .order_by(ChatPiTranscriptEntry.ordinal)
            ).scalars()
        )
        if len(entries) != row.entry_count:
            raise PiTranscriptError("Pi transcript summary is inconsistent")
        if entries and (
            entries[0].get("type") != "session"
            or str(entries[0].get("id") or "") != str(agent_session_id)
        ):
            raise PiTranscriptError("Pi transcript header identity mismatches")
        return PiSessionSnapshot(
            agent_session_id=agent_session_id,
            chat_session_id=chat_session_id,
            current_leaf_id=row.current_leaf_id,
            entry_count=row.entry_count,
            byte_size=row.byte_size,
            format_version=row.format_version,
            entries=entries,
        )

    def prepare_fork(
        self,
        chat_session_id: uuid.UUID,
        source_session_id: uuid.UUID,
        boundary_entry_id: str,
        fork_session_id: uuid.UUID,
    ) -> PiSessionSnapshot:
        snapshot = self.load_session(chat_session_id, source_session_id)
        records = list(
            self.db.execute(
                select(ChatPiTranscriptEntry)
                .where(ChatPiTranscriptEntry.agent_session_id == source_session_id)
                .order_by(ChatPiTranscriptEntry.ordinal)
            ).scalars()
        )
        by_id = {record.entry_id: record for record in records if record.entry_id}
        if boundary_entry_id not in by_id:
            raise PiTranscriptError("Pi fork boundary was not found")
        path_ids: set[str] = set()
        cursor: str | None = boundary_entry_id
        while cursor is not None:
            if cursor in path_ids or cursor not in by_id:
                raise PiTranscriptError("Pi transcript parent path is invalid")
            path_ids.add(cursor)
            cursor = by_id[cursor].parent_entry_id
        selected = [
            record
            for record in records
            if record.entry_id in path_ids
            or (
                record.entry_id is None
                and record.entry_type in _PATH_METADATA_TYPES
                and record.ordinal <= by_id[boundary_entry_id].ordinal
            )
        ]
        copied_entries: list[dict[str, Any]] = []
        copied_bytes = 0
        for record in selected:
            entry = dict(_native_entry(record.entry))
            if record.entry_type == "session":
                entry["id"] = str(fork_session_id)
                entry["parentSession"] = str(source_session_id)
            entry, byte_size = _serialized(entry)
            copied_entries.append(entry)
            copied_bytes += byte_size
        fork = ChatPiSession(
            agent_session_id=fork_session_id,
            chat_session_id=chat_session_id,
            current_leaf_id=boundary_entry_id,
            entry_count=len(selected),
            byte_size=copied_bytes,
            format_version=snapshot.format_version,
        )
        self.db.add(
            ChatPiPreparedFork(
                fork_session_id=fork_session_id,
                chat_session_id=chat_session_id,
                source_session_id=source_session_id,
                boundary_entry_id=boundary_entry_id,
                entries=copied_entries,
                entry_count=fork.entry_count,
                byte_size=fork.byte_size,
                format_version=fork.format_version,
            )
        )
        self.db.flush()
        return PiSessionSnapshot(
            agent_session_id=fork.agent_session_id,
            chat_session_id=chat_session_id,
            current_leaf_id=boundary_entry_id,
            entry_count=fork.entry_count,
            byte_size=fork.byte_size,
            format_version=fork.format_version,
            entries=tuple(copied_entries),
        )

    def delete_prepared_fork(
        self, chat_session_id: uuid.UUID, fork_session_id: uuid.UUID
    ) -> bool:
        self._pi_chat(chat_session_id)
        result = self.db.execute(
            delete(ChatPiPreparedFork).where(
                ChatPiPreparedFork.chat_session_id == chat_session_id,
                ChatPiPreparedFork.fork_session_id == fork_session_id,
            )
        )
        return bool(result.rowcount)

    def delete_session(
        self, chat_session_id: uuid.UUID, agent_session_id: uuid.UUID
    ) -> bool:
        self._pi_chat(chat_session_id)
        result = self.db.execute(
            delete(ChatPiSession).where(
                ChatPiSession.chat_session_id == chat_session_id,
                ChatPiSession.agent_session_id == agent_session_id,
            )
        )
        return bool(result.rowcount)
