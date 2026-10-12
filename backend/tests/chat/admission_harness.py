"""Scripted database and session builders for chat turn admission tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace


from backend.services.chat_session_service import (
    ChatSessionService,
)


class _Result:
    def __init__(self, *, one=None, rows=()):
        self._one = one
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _ScriptedDB:
    def __init__(self, *, execute_results=(), scalar_results=()):
        self._execute_results = iter(execute_results)
        self._scalar_results = iter(scalar_results)
        self.events: list[tuple[str, object]] = []
        self.added: list[object] = []
        self.flush_calls = 0

    def execute(self, query):
        self.events.append(("execute", query))
        return next(self._execute_results)

    def scalar(self, query):
        self.events.append(("scalar", query))
        return next(self._scalar_results)

    def add(self, value):
        self.events.append(("add", value))
        self.added.append(value)

    def flush(self):
        self.events.append(("flush", None))
        self.flush_calls += 1


def _session(settings, **overrides):
    values = {
        "id": uuid.uuid4(),
        "hf_user_id": "owner-1",
        "hf_username": "owner",
        "selected_model": settings.chat_model_choices[0]["id"],
        "execution_backend": "local_mcp",
        "transcript_status": "pending",
        "sdk_session_id": None,
        "sdk_project_key": None,
        "active_turn_id": None,
        "active_turn_expires_at": None,
        "transcript_bytes": 0,
        "projection_bytes": 0,
        "message_count": 0,
        "last_sequence": 0,
        "title_source": None,
        "web_search_enabled": False,
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _owned_service(db, settings, session):
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session
    return service
