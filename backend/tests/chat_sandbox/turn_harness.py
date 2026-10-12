"""Shared fake dependency graph for direct sandbox turn-coordinator tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace

from backend.config import Settings
from backend.services.chat_sandbox_state_repository import WorkerClaim
from backend.services.chat_sandbox_turn_coordinator import ChatSandboxTurnCoordinator
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport


class TurnHarnessSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def begin(self):
        return self


def _default_claim_worker(
    _lease,
    *,
    sandbox_id: str,
    assignment_token: str,
    **_kwargs,
) -> WorkerClaim:
    return WorkerClaim(
        sandbox_id=sandbox_id,
        token_hash="claim-token",
        assignment_token=assignment_token,
    )


def _default_release_worker(*_args, **_kwargs) -> bool:
    return True


async def _default_terminate(*_args, **_kwargs) -> None:
    return None


async def _default_enforce_warm_cap() -> int:
    return 0


def build_turn_coordinator(
    settings: Settings,
    transport: ChatSandboxWorkerTransport,
    *,
    acquire,
    session_factory: Callable = TurnHarnessSession,
    state_repository=None,
    claim_worker=None,
    release_worker=None,
    terminate_worker=None,
    terminate=None,
    enforce_warm_cap=None,
    blank_pool_enabled: bool = True,
    assignment_token_factory: Callable[[], str] = lambda: "assignment-token",
    spend_factory=None,
    utcnow=None,
    perf_counter: Callable[[], float] = time.perf_counter,
) -> ChatSandboxTurnCoordinator:
    """Build one identity-consistent fake graph with optional behavior hooks."""

    if state_repository is None:
        state_repository = SimpleNamespace(
            settings=settings,
            load_lease=lambda *_args, **_kwargs: object(),
            claim_worker=claim_worker or _default_claim_worker,
            release_worker=release_worker or _default_release_worker,
        )

    def capacity_locker(_db, *_args, **_kwargs):
        return True

    idle_eviction = object()
    lifecycle = SimpleNamespace(
        settings=settings,
        session_factory=session_factory,
        repository=state_repository,
        transport=transport,
        provider=transport.provider,
        idle_eviction=idle_eviction,
        capacity_locker=capacity_locker,
        terminate_worker=terminate_worker or _default_terminate,
        terminate=terminate or _default_terminate,
    )
    maintenance = SimpleNamespace(
        settings=settings,
        session_factory=session_factory,
        repository=state_repository,
        provider=transport.provider,
        lifecycle=lifecycle,
        capacity_locker=capacity_locker,
        enforce_warm_cap=enforce_warm_cap or _default_enforce_warm_cap,
    )
    acquisition = SimpleNamespace(
        settings=settings,
        session_factory=session_factory,
        state_repository=state_repository,
        transport=transport,
        provider=transport.provider,
        lease_maintenance=maintenance,
        pool=SimpleNamespace(lease_eviction=idle_eviction),
        capacity_repository=SimpleNamespace(capacity_locker=capacity_locker),
        blank_pool_enabled=blank_pool_enabled,
        acquire=acquire,
    )
    return ChatSandboxTurnCoordinator(
        settings,
        session_factory=session_factory,
        state_repository=state_repository,
        acquisition=acquisition,
        transport=transport,
        lifecycle=lifecycle,
        maintenance=maintenance,
        spend_factory=spend_factory,
        utcnow=utcnow,
        perf_counter=perf_counter,
        assignment_token_factory=assignment_token_factory,
    )
