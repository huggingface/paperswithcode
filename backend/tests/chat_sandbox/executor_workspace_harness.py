"""Executor workspace manager builder shared by warm-pool tests."""

from __future__ import annotations

import uuid


from backend.services.chat_external_executor_workspace import (
    ChatExternalExecutorWorkspaceManager,
)
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.tests.chat_sandbox.acquisition_harness import _coordinator
from backend.tests.chat_sandbox.capacity_harness import (
    _Provider,
    _database,
    _session,
    _settings,
)


class RecordingProvider(_Provider):
    def __init__(self, *, transactions):
        super().__init__(transactions=transactions)
        self.create_options = []

    async def create(self, **options):
        self.create_options.append(options)
        return await super().create(**options)


class ExecutorHealth:
    def __init__(self, *statuses: str):
        self.statuses = list(statuses or ("ok",))
        self.sandboxes = []

    async def health(self, sandbox):
        self.sandboxes.append(sandbox)
        return self.statuses.pop(0) if self.statuses else "ok"


class LiveTurns:
    def __init__(self):
        self.claims = []

    def require_live_claim(self, _db, *, claim, now):
        self.claims.append((claim, now))


TURN_CLAIM = TurnLeaseClaim(uuid.uuid4(), "worker", 3, 7)


def setup_manager(
    *,
    health: ExecutorHealth | None = None,
    observe=None,
    record=None,
    qualification_capacity=None,
    sandbox_cap=2,
    warm_seconds=300,
    max_warm=10,
):
    settings = _settings(
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_total_live_cap=sandbox_cap,
        chat_sandbox_warm_seconds=warm_seconds,
        chat_sandbox_max_warm=max_warm,
    )
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = RecordingProvider(transactions=[])
    acquisition = _coordinator(settings, sessions, provider)
    manager = ChatExternalExecutorWorkspaceManager(
        settings=settings,
        session_factory=acquisition.session_factory,
        state_repository=acquisition.state_repository,
        acquisition=acquisition,
        lifecycle=acquisition.lease_maintenance.lifecycle,
        maintenance=acquisition.lease_maintenance,
        executor=health or ExecutorHealth(),
        turn_repository=LiveTurns(),
        observe=observe,
        record_evidence=record,
        qualification_capacity=(
            qualification_capacity
            if qualification_capacity is not None
            else (lambda *_args, **_kwargs: None)
        ),
    )
    return manager, sessions, session_id, provider
