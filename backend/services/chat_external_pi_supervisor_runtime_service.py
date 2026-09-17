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
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)

LifecycleEvent = Literal["registered", "heartbeat", "lease_lost", "drained"]

# Conditions worth retrying inside the registration window: the worker endpoint
# or the database is unreachable, or the durable registry still shows a live
# lease from a previous claim that has yet to run out.
_REGISTRATION_RETRY_ERRORS = (
    ExternalPiWorkerUnavailable,
    WorkerLeaseUnavailable,
    OperationalError,
)
# A heartbeat that never reached the worker or the database. The claim may
# still be good, so keep trying until the local lease window runs out.
_HEARTBEAT_TRANSPORT_ERRORS = (ExternalPiWorkerUnavailable, OperationalError)
# The registry rejected the claim itself: a newer generation fenced it or the
# durable lease already expired. It must never be heartbeated again.
_HEARTBEAT_FENCED_ERRORS = (StaleWorkerClaim, WorkerLeaseUnavailable)


class StopWaiter(Protocol):
    async def __call__(self, seconds: float) -> bool: ...


class Sleeper(Protocol):
    async def __call__(self, seconds: float) -> None: ...


class LifecycleObserver(Protocol):
    def __call__(
        self,
        event: LifecycleEvent,
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
    """The lease expired and a replacement claim could not be established."""


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
    release_connections: Callable[[], None] | None = None

    async def _transaction(self, operation):
        try:
            with self.session_factory() as db:
                result = await operation(db)
                db.commit()
                return result
        finally:
            if self.release_connections is not None:
                self.release_connections()

    async def _wait_for_drain_retry(
        self, *, deadline: float, error: BaseException
    ) -> None:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise ExternalPiSupervisorDrainTimeout(
                "External Pi worker drain timed out"
            ) from error
        await self.sleep(min(self.drain_poll_seconds, remaining))

    async def _register(self) -> ExternalWorkerClaim | None:
        """Claim the worker, retrying transient failures within the startup window.

        Returns ``None`` when a stop was requested before the claim succeeded.
        """
        started_at = self.monotonic()
        while True:
            registration_now = self.now()
            try:
                return await self._transaction(
                    lambda db: self.supervisor.register(db, now=registration_now)
                )
            except _REGISTRATION_RETRY_ERRORS as error:
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
                    return None

    async def _reregister(
        self, lost: ExternalWorkerClaim, heartbeats: int
    ) -> ExternalWorkerClaim | None:
        """Replace a claim whose lease can no longer be proven.

        Whether the local lease window ran out (an event loop stalled by a
        starved host) or the registry fenced the claim, the old claim must
        never be heartbeated again. Exiting the process used to enforce that,
        at the price of a systemd restart, an unroutable worker in between,
        and a crash loop whenever the restart itself failed. Take a fresh claim
        in-process through the same fenced registration a restart would run:
        a lease the registry still considers live is renewed under the same
        generation, an expired one advances the generation and fences the old
        owner.
        """
        if self.observe is not None:
            self.observe("lease_lost", lost, heartbeats)
        try:
            return await self._register()
        except ExternalPiSupervisorStartupTimeout as error:
            raise ExternalPiSupervisorLeaseLost(
                "External Pi worker lease expired and could not be re-established"
            ) from error

    async def _heartbeat_until_stop_or_lease_loss(
        self, claim: ExternalWorkerClaim, heartbeats: int
    ) -> tuple[Literal["stop", "lease_lost"], int]:
        """Renew the claim until a stop is requested or its lease cannot be kept.

        Returns the outcome and the cumulative heartbeat count.
        """
        last_heartbeat_at = self.monotonic()
        while True:
            lease_remaining = self.supervisor.lease_seconds - (
                self.monotonic() - last_heartbeat_at
            )
            if lease_remaining <= 0:
                return "lease_lost", heartbeats
            if await self.wait_for_stop(
                min(self.heartbeat_interval_seconds, lease_remaining)
            ):
                return "stop", heartbeats
            heartbeat_started_at = self.monotonic()
            if (
                heartbeat_started_at - last_heartbeat_at
                >= self.supervisor.lease_seconds
            ):
                return "lease_lost", heartbeats
            heartbeat_now = self.now()
            try:
                await self._transaction(
                    lambda db: self.supervisor.heartbeat(
                        db,
                        claim=claim,
                        now=heartbeat_now,
                    )
                )
            except _HEARTBEAT_FENCED_ERRORS:
                return "lease_lost", heartbeats
            except _HEARTBEAT_TRANSPORT_ERRORS:
                if (
                    self.monotonic() - last_heartbeat_at
                    >= self.supervisor.lease_seconds
                ):
                    return "lease_lost", heartbeats
                continue
            last_heartbeat_at = heartbeat_started_at
            heartbeats += 1
            if self.observe is not None:
                self.observe("heartbeat", claim, heartbeats)

    async def run(self) -> ExternalPiSupervisorRunResult:
        registrations = 0
        heartbeats = 0
        claim = await self._register()
        while claim is not None:
            registrations += 1
            if self.observe is not None:
                self.observe("registered", claim, heartbeats)
            outcome, heartbeats = await self._heartbeat_until_stop_or_lease_loss(
                claim, heartbeats
            )
            if outcome == "stop":
                break
            claim = await self._reregister(claim, heartbeats)
        if claim is None:
            return ExternalPiSupervisorRunResult(registrations, heartbeats, False)

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
            registrations=registrations,
            heartbeats=heartbeats,
            drained=True,
        )
