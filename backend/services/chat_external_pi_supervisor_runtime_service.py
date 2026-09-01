"""Process lifecycle loop for a single externally hosted Pi worker."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.services.chat_external_pi_shadow import ExternalPiWorkerUnavailable
from backend.services.chat_external_pi_supervisor import (
    ChatExternalPiSupervisor,
    ExternalPiWorkerDrainIncomplete,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim


class StopWaiter(Protocol):
    async def __call__(self, seconds: float) -> bool: ...


class Sleeper(Protocol):
    async def __call__(self, seconds: float) -> None: ...


class LifecycleObserver(Protocol):
    def __call__(
        self,
        event: Literal["registered", "heartbeat", "drained"],
        claim: ExternalWorkerClaim,
        heartbeats: int,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ExternalPiSupervisorRunResult:
    registrations: int
    heartbeats: int
    drained: bool


class ExternalPiSupervisorStartupTimeout(RuntimeError):
    """The worker stayed unavailable for the bounded startup window."""


class ExternalPiSupervisorLeaseLost(RuntimeError):
    """The supervisor could not renew its lease before it expired."""


class ExternalPiSupervisorDrainTimeout(RuntimeError):
    """The worker did not become idle before its drain deadline."""


@dataclass(slots=True)
class ChatExternalPiSupervisorRuntime:
    """Own registration, heartbeats, and graceful drain for one worker."""

    supervisor: ChatExternalPiSupervisor
    session_factory: Callable[[], AbstractContextManager[Session]]
    now: Callable[[], datetime]
    monotonic: Callable[[], float]
    wait_for_stop: StopWaiter
    sleep: Sleeper
    heartbeat_interval_seconds: float
    startup_timeout_seconds: float
    drain_poll_seconds: float
    observe: LifecycleObserver | None = None

    async def _transaction(self, operation):
        with self.session_factory() as db:
            result = await operation(db)
            db.commit()
            return result

    async def _wait_for_drain_retry(
        self, *, deadline: float, error: BaseException
    ) -> None:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise ExternalPiSupervisorDrainTimeout(
                "External Pi worker drain timed out"
            ) from error
        await self.sleep(min(self.drain_poll_seconds, remaining))

    async def run(self) -> ExternalPiSupervisorRunResult:
        started_at = self.monotonic()
        while True:
            registration_now = self.now()
            try:
                claim: ExternalWorkerClaim = await self._transaction(
                    lambda db: self.supervisor.register(db, now=registration_now)
                )
                if self.observe is not None:
                    self.observe("registered", claim, 0)
                break
            except (ExternalPiWorkerUnavailable, OperationalError) as error:
                remaining = self.startup_timeout_seconds - (
                    self.monotonic() - started_at
                )
                if remaining <= 0:
                    raise ExternalPiSupervisorStartupTimeout(
                        "External Pi worker startup timed out"
                    ) from error
                if await self.wait_for_stop(
                    min(self.heartbeat_interval_seconds, remaining)
                ):
                    return ExternalPiSupervisorRunResult(0, 0, False)

        last_heartbeat_at = self.monotonic()
        heartbeats = 0

        while True:
            lease_remaining = self.supervisor.lease_seconds - (
                self.monotonic() - last_heartbeat_at
            )
            if lease_remaining <= 0:
                raise ExternalPiSupervisorLeaseLost("External Pi worker lease expired")
            if await self.wait_for_stop(
                min(self.heartbeat_interval_seconds, lease_remaining)
            ):
                break
            heartbeat_started_at = self.monotonic()
            if (
                heartbeat_started_at - last_heartbeat_at
                >= self.supervisor.lease_seconds
            ):
                raise ExternalPiSupervisorLeaseLost("External Pi worker lease expired")
            heartbeat_now = self.now()
            try:
                await self._transaction(
                    lambda db: self.supervisor.heartbeat(
                        db,
                        claim=claim,
                        now=heartbeat_now,
                    )
                )
                last_heartbeat_at = heartbeat_started_at
                heartbeats += 1
                if self.observe is not None:
                    self.observe("heartbeat", claim, heartbeats)
            except (ExternalPiWorkerUnavailable, OperationalError) as error:
                if (
                    self.monotonic() - last_heartbeat_at
                    >= self.supervisor.lease_seconds
                ):
                    raise ExternalPiSupervisorLeaseLost(
                        "External Pi worker lease could not be renewed"
                    ) from error

        drain_deadline = self.monotonic() + self.supervisor.drain_seconds
        while True:
            try:
                await self._transaction(
                    lambda db: self.supervisor.begin_drain(
                        db,
                        claim=claim,
                        now=self.now(),
                    )
                )
                break
            except (ExternalPiWorkerUnavailable, OperationalError) as error:
                await self._wait_for_drain_retry(deadline=drain_deadline, error=error)
        while True:
            try:
                await self._transaction(
                    lambda db: self.supervisor.finish_drain(
                        db,
                        claim=claim,
                        now=self.now(),
                    )
                )
                break
            except (
                ExternalPiWorkerDrainIncomplete,
                ExternalPiWorkerUnavailable,
                OperationalError,
            ) as error:
                await self._wait_for_drain_retry(deadline=drain_deadline, error=error)
        if self.observe is not None:
            self.observe("drained", claim, heartbeats)
        return ExternalPiSupervisorRunResult(
            registrations=1,
            heartbeats=heartbeats,
            drained=True,
        )
