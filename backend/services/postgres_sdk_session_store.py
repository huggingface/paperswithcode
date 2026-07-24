"""PostgreSQL-backed opaque transcript store for the Claude Agent SDK."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable

from claude_agent_sdk import fold_session_summary
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
)


def _json_bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


class PostgresSDKSessionStore:
    """Keep SDK entries opaque, ordered, transactional, and retry-safe."""

    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or db_manager.session_local

    async def append(self, key: dict, entries: list[dict]) -> None:
        await asyncio.to_thread(self._append, key, entries)

    def _append(self, key: dict, entries: list[dict]) -> None:
        if not entries:
            return
        with self._session_factory() as db, db.begin():
            self.append_in_session(db, key, entries)

    @staticmethod
    def append_in_session(db: Session, key: dict, entries: list[dict]) -> int:
        """Append and account entries inside the caller's transaction."""

        if not entries:
            return 0
        project_key = key["project_key"]
        sdk_session_id = uuid.UUID(str(key["session_id"]))
        subpath = key.get("subpath", "")
        inserted: list[dict] = []
        inserted_bytes = 0
        now_ms = int(time.time() * 1000)

        for entry in entries:
            byte_size = _json_bytes(entry)
            statement = insert(ChatSDKTranscriptEntry).values(
                project_key=project_key,
                sdk_session_id=sdk_session_id,
                subpath=subpath,
                entry_uuid=entry.get("uuid"),
                entry=entry,
                byte_size=byte_size,
            )
            if entry.get("uuid") is not None:
                statement = statement.on_conflict_do_nothing(
                    index_elements=[
                        "project_key",
                        "sdk_session_id",
                        "subpath",
                        "entry_uuid",
                    ],
                    index_where=ChatSDKTranscriptEntry.entry_uuid.is_not(None),
                )
            landed = db.execute(
                statement.returning(ChatSDKTranscriptEntry.id)
            ).scalar_one_or_none()
            if landed is not None:
                inserted.append(entry)
                inserted_bytes += byte_size

        if not subpath and inserted:
            db.execute(
                insert(ChatSDKSessionSummary)
                .values(
                    project_key=project_key,
                    sdk_session_id=sdk_session_id,
                    mtime=0,
                    data={},
                )
                .on_conflict_do_nothing(
                    index_elements=["project_key", "sdk_session_id"]
                )
            )
            summary = db.execute(
                select(ChatSDKSessionSummary)
                .where(
                    ChatSDKSessionSummary.project_key == project_key,
                    ChatSDKSessionSummary.sdk_session_id == sdk_session_id,
                )
                .with_for_update()
            ).scalar_one()
            previous = None
            if summary.mtime:
                previous = {
                    "session_id": str(summary.sdk_session_id),
                    "mtime": summary.mtime,
                    "data": summary.data,
                }
            folded = fold_session_summary(previous, key, inserted)
            folded["mtime"] = now_ms
            summary.mtime = now_ms
            summary.data = folded["data"]
        if inserted_bytes:
            db.execute(
                update(ChatSession)
                .where(
                    ChatSession.sdk_project_key == project_key,
                    ChatSession.sdk_session_id == sdk_session_id,
                )
                .values(transcript_bytes=ChatSession.transcript_bytes + inserted_bytes)
            )
        return inserted_bytes

    async def load(self, key: dict) -> list[dict] | None:
        return await asyncio.to_thread(self._load, key)

    def _load(self, key: dict) -> list[dict] | None:
        with self._session_factory() as db:
            return self.load_in_session(db, key)

    @staticmethod
    def load_in_session(db: Session, key: dict) -> list[dict] | None:
        rows = (
            db.execute(
                select(ChatSDKTranscriptEntry.entry)
                .where(
                    ChatSDKTranscriptEntry.project_key == key["project_key"],
                    ChatSDKTranscriptEntry.sdk_session_id
                    == uuid.UUID(str(key["session_id"])),
                    ChatSDKTranscriptEntry.subpath == key.get("subpath", ""),
                )
                .order_by(ChatSDKTranscriptEntry.id)
            )
            .scalars()
            .all()
        )
        return list(rows) or None

    async def list_sessions(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(self._list_sessions, project_key)

    def _list_sessions(self, project_key: str) -> list[dict]:
        with self._session_factory() as db:
            return self.list_sessions_in_session(db, project_key)

    @staticmethod
    def list_sessions_in_session(db: Session, project_key: str) -> list[dict]:
        rows = db.execute(
            select(
                ChatSDKSessionSummary.sdk_session_id, ChatSDKSessionSummary.mtime
            ).where(ChatSDKSessionSummary.project_key == project_key)
        ).all()
        return [
            {"session_id": str(row.sdk_session_id), "mtime": row.mtime} for row in rows
        ]

    async def list_session_summaries(self, project_key: str) -> list[dict]:
        return await asyncio.to_thread(self._list_session_summaries, project_key)

    def _list_session_summaries(self, project_key: str) -> list[dict]:
        with self._session_factory() as db:
            return self.list_session_summaries_in_session(db, project_key)

    @staticmethod
    def list_session_summaries_in_session(db: Session, project_key: str) -> list[dict]:
        rows = (
            db.execute(
                select(ChatSDKSessionSummary).where(
                    ChatSDKSessionSummary.project_key == project_key
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "session_id": str(row.sdk_session_id),
                "mtime": row.mtime,
                "data": row.data,
            }
            for row in rows
        ]

    async def list_subkeys(self, key: dict) -> list[str]:
        return await asyncio.to_thread(self._list_subkeys, key)

    def _list_subkeys(self, key: dict) -> list[str]:
        with self._session_factory() as db:
            return self.list_subkeys_in_session(db, key)

    @staticmethod
    def list_subkeys_in_session(db: Session, key: dict) -> list[str]:
        return list(
            db.execute(
                select(ChatSDKTranscriptEntry.subpath)
                .where(
                    ChatSDKTranscriptEntry.project_key == key["project_key"],
                    ChatSDKTranscriptEntry.sdk_session_id
                    == uuid.UUID(str(key["session_id"])),
                    ChatSDKTranscriptEntry.subpath != "",
                )
                .distinct()
            ).scalars()
        )

    async def delete(self, key: dict) -> None:
        await asyncio.to_thread(self._delete, key)

    def _delete(self, key: dict) -> None:
        sdk_session_id = uuid.UUID(str(key["session_id"]))
        subpath = key.get("subpath")
        with self._session_factory() as db, db.begin():
            filters = [
                ChatSDKTranscriptEntry.project_key == key["project_key"],
                ChatSDKTranscriptEntry.sdk_session_id == sdk_session_id,
            ]
            if subpath is not None:
                filters.append(ChatSDKTranscriptEntry.subpath == subpath)
            db.execute(delete(ChatSDKTranscriptEntry).where(*filters))
            if subpath is None:
                db.execute(
                    delete(ChatSDKSessionSummary).where(
                        ChatSDKSessionSummary.project_key == key["project_key"],
                        ChatSDKSessionSummary.sdk_session_id == sdk_session_id,
                    )
                )
