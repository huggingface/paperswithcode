"""Transactional scripted database for chat admission bridge tests."""

from __future__ import annotations

from backend.models.database import ChatSession
from backend.tests.chat.admission_harness import (
    _ScriptedDB,
)


class _TransactionalScriptedDB(_ScriptedDB):
    """Small transaction fake that exposes durable state at rollback time."""

    def __init__(self, *, execute_results=(), scalar_results=(), tracked=()):
        super().__init__(
            execute_results=execute_results,
            scalar_results=scalar_results,
        )
        self.rows: list[object] = []
        self._pending: list[object] = []
        self._tracked = [(value, vars(value).copy()) for value in tracked]
        self.rows_at_rollback: list[object] = []
        self.states_at_rollback: list[dict[str, object]] = []
        self.rollback_calls = 0

    def add(self, value):
        super().add(value)
        self._pending.append(value)

    def flush(self):
        super().flush()
        for value in self._pending:
            if isinstance(value, ChatSession):
                # These database defaults are materialized by a real flush.
                value.transcript_status = value.transcript_status or "pending"
                value.transcript_bytes = value.transcript_bytes or 0
                value.projection_bytes = value.projection_bytes or 0
                value.message_count = value.message_count or 0
                value.last_sequence = value.last_sequence or 0
                if value.web_search_enabled is None:
                    value.web_search_enabled = False
            self.rows.append(value)
        self._pending.clear()

    def rollback(self):
        self.rollback_calls += 1
        self.rows_at_rollback = list(self.rows)
        self.states_at_rollback = [vars(value).copy() for value, _ in self._tracked]
        self.rows.clear()
        self._pending.clear()
        for value, snapshot in self._tracked:
            vars(value).clear()
            vars(value).update(snapshot)
