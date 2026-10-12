from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.models.database import ChatSandboxLease
from backend.services.chat_sandbox_provider import SandboxError
from backend.tests.chat_sandbox.capacity_harness import (
    _database,
    _manager,
    _Provider,
    _session,
    _settings,
)


def test_sandbox_provider_startup_timeout_marks_claim_and_uses_stable_error_code():
    settings = _settings(chat_sandbox_ready_timeout_seconds=0.01)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    class NeverFinishes(_Provider):
        async def create(self, **options):
            self._assert_outside_transaction()
            self.calls.append(("create", options["worker_generation"]))
            await asyncio.Future()

    provider = NeverFinishes(transactions=[])
    manager = _manager(settings, sessions, provider)

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(manager.ensure_ready(session_id))

    assert exc_info.value.code == "sandbox_timeout"
    assert str(exc_info.value) == "Secure workspace startup timed out"
    assert exc_info.value.uncertain is False
    assert [call[0] for call in provider.calls] == ["create"]
    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "failed"
    assert lease.failure_code == "sandbox_timeout"
    assert lease.lease_token_hash is None
    assert lease.lease_expires_at is None
