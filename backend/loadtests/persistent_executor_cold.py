"""Cold-stage collection primitives; never confer full release qualification.

The caller must preflight the isolated cell, host capacity, exact release and
SDK, and supply the ordinary durable spend ledger. This module does not start
services, change capacity, select images, or bypass application spend caps.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, Protocol, TypeVar

from backend.loadtests.persistent_executor_feasibility import (
    COLD_FIRST_PWD_P95_MS,
    COLD_FIRST_PWD_P99_MS,
    nearest_rank,
)
from backend.services.durable_external_qualification_contract import (
    COLD_QUALIFICATION_SANDBOX_LIFETIME_SECONDS,
)
from backend.services.chat_sandbox_executor import ExecutorContext
from backend.services.chat_sandbox_provider import SandboxLaunchMode

# Approved 2026-09-15: preserve the entire earlier allocation, add cold only.
PRIOR_ALLOCATION_MICROUSD = 16_250_000
COLD_ALLOCATION_MICROUSD = 25_000_000
COMBINED_CEILING_MICROUSD = PRIOR_ALLOCATION_MICROUSD + COLD_ALLOCATION_MICROUSD
COLD_SAMPLE_COUNTS = {"cold_first_pwd": 1000, "cold_32_way": 32}
SANDBOX_LIFETIME_SECONDS = COLD_QUALIFICATION_SANDBOX_LIFETIME_SECONDS
SANDBOX_RATE_MICROUSD = 93
OPERATING_RESERVE_MICROUSD = 1_250_000
CLEANUP_TIMEOUT_SECONDS = 30
COLD_RESERVATION_MICROUSD = (
    sum(COLD_SAMPLE_COUNTS.values()) * SANDBOX_LIFETIME_SECONDS * SANDBOX_RATE_MICROUSD
    + OPERATING_RESERVE_MICROUSD
)
Profile = Literal["cold_first_pwd", "cold_32_way"]
T = TypeVar("T")


async def _blocking_transition(function: Callable[..., T], *args: object) -> T:
    """Keep database/fsync work off the loop; drain it before cancellation cleanup."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling an await does not stop its thread. Do not race provider
        # cleanup against a still-committing reservation or journal update.
        await asyncio.gather(task, return_exceptions=True)
        raise


class SpendLedger(Protocol):
    """Use durable application reservations in addition to the cold allocation."""

    def reserve(self, worker_generation: str) -> str: ...
    def created(self, reservation_id: str, sandbox_id: str) -> None: ...
    def terminated(self, sandbox_id: str) -> None: ...


@dataclass(frozen=True)
class ColdObservation:
    profile: Profile
    index: int
    worker_generation: str
    reservation_id: str | None = None
    sandbox_id: str | None = None
    elapsed_ms: float | None = None
    error: str | None = None
    cleanup_error: str | None = None
    terminal_confirmed: bool = False
    completed: bool = False

    def __post_init__(self) -> None:
        if self.elapsed_ms is not None and (
            not math.isfinite(self.elapsed_ms) or self.elapsed_ms < 0
        ):
            raise ValueError("elapsed time must be finite and nonnegative")


class ColdJournal:
    """Exclusive run directory, atomic durable observations, no resume or retry.

    A crash leaves an incomplete observation with its generation and any known
    provider identity. It is failed evidence and requires separate provider
    reconciliation; opening the run again never launches replacement samples.
    """

    def __init__(self, directory: Path, *, source_sha: str, image_id: str):
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not image_id.startswith(
            "im-"
        ):
            raise ValueError("source commit and image identity are required")
        directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.directory = directory
        self.image_id = image_id
        self._admitted: set[tuple[str, int]] = set()
        self._started: set[tuple[str, int]] = set()
        self._start_lock = threading.Lock()
        self._write(
            "manifest.json",
            {
                "kind": "cold-stage-only-not-release-qualification",
                "source_sha": source_sha,
                "image_id": image_id,
                "sample_counts": COLD_SAMPLE_COUNTS,
                "prior_allocation_retained_microusd": PRIOR_ALLOCATION_MICROUSD,
                "cold_allocation_microusd": COLD_ALLOCATION_MICROUSD,
                "combined_ceiling_microusd": COMBINED_CEILING_MICROUSD,
                "cold_reservation_microusd": COLD_RESERVATION_MICROUSD,
                "sandbox_lifetime_seconds": SANDBOX_LIFETIME_SECONDS,
                "sandbox_rate_microusd": SANDBOX_RATE_MICROUSD,
            },
        )

    def _write(self, name: str, value: dict) -> None:
        temporary = self.directory / (name + ".tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.directory / name)
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def admit(self, profile: Profile, index: int) -> ColdObservation:
        if (
            profile not in COLD_SAMPLE_COUNTS
            or not 0 <= index < COLD_SAMPLE_COUNTS[profile]
        ):
            raise ValueError("sample is outside the approved cold allocation")
        identity = (profile, index)
        if identity in self._admitted:
            raise ValueError("cold observations cannot be retried")
        self._admitted.add(identity)
        observation = ColdObservation(profile, index, "cold-" + uuid.uuid4().hex)
        self.save(observation)
        return observation

    def begin(self, observation: ColdObservation) -> None:
        with self._start_lock:
            identity = (observation.profile, observation.index)
            if identity not in self._admitted or identity in self._started:
                raise ValueError("observation must be admitted exactly once")
            path = (
                self.directory / f"{observation.profile}-{observation.index:04d}.json"
            )
            if json.loads(path.read_text()) != asdict(observation):
                raise ValueError("observation differs from durable admission")
            self._started.add(identity)

    def save_result(self, result: dict) -> None:
        self._write("result.json", result)

    def save(self, observation: ColdObservation) -> None:
        self._write(
            f"{observation.profile}-{observation.index:04d}.json", asdict(observation)
        )


def read_observations(directory: Path) -> list[ColdObservation]:
    """Read interrupted runs without provisioning or releasing reservations."""
    return [
        ColdObservation(**json.loads(path.read_text()))
        for profile in COLD_SAMPLE_COUNTS
        for path in sorted(directory.glob(f"{profile}-[0-9][0-9][0-9][0-9].json"))
    ]


def cold_stage_result(observations: list[ColdObservation]) -> dict:
    """Missing/failed measurements occupy the tail; incomplete cohorts fail."""
    unique = len({row.worker_generation for row in observations}) == len(
        observations
    ) and len({row.sandbox_id for row in observations if row.sandbox_id}) == sum(
        row.sandbox_id is not None for row in observations
    )
    result = {"full_release_qualified": False, "profiles": {}}
    for profile, count in COLD_SAMPLE_COUNTS.items():
        rows = [row for row in observations if row.profile == profile]
        complete = (
            unique
            and len(rows) == count
            and {row.index for row in rows} == set(range(count))
            and len({row.worker_generation for row in rows}) == count
            and all(row.sandbox_id for row in rows)
            and len({row.sandbox_id for row in rows}) == count
        )
        failures = sum(
            not row.completed
            or row.error is not None
            or row.cleanup_error is not None
            or not row.terminal_confirmed
            or row.elapsed_ms is None
            for row in rows
        )
        values = [
            row.elapsed_ms
            if row.completed and row.error is None and row.elapsed_ms is not None
            else float("inf")
            for row in rows
        ]
        # Errors occupy the percentile tail in the 1,000-sample cohort. The
        # separate burst requires zero errors; both require complete cleanup.
        passed = complete and all(
            row.completed and row.cleanup_error is None and row.terminal_confirmed
            for row in rows
        )
        if profile == "cold_32_way":
            passed = passed and failures == 0
        if passed:
            passed = (
                max(values) <= COLD_FIRST_PWD_P99_MS
                if profile == "cold_32_way"
                else (
                    nearest_rank(values, 0.95) <= COLD_FIRST_PWD_P95_MS
                    and nearest_rank(values, 0.99) <= COLD_FIRST_PWD_P99_MS
                )
            )
        result["profiles"][profile] = {
            "observed": len(rows),
            "expected": count,
            "failures": failures,
            "passed": passed,
        }
    result["latency_gates_passed"] = all(
        p["passed"] for p in result["profiles"].values()
    )
    # Timing rows cannot attest host resources, simultaneous admission or identity.
    result["cold_stage_qualified"] = False
    return result


def cold_gate_impossible(observations: list[ColdObservation]) -> bool:
    rows = [row for row in observations if row.profile == "cold_first_pwd"]
    values = [
        row.elapsed_ms
        if row.error is None and row.elapsed_ms is not None
        else float("inf")
        for row in rows
    ]
    return (
        sum(value > COLD_FIRST_PWD_P95_MS for value in values) > 50
        or sum(value > COLD_FIRST_PWD_P99_MS for value in values) > 10
    )


async def collect_cold_observation(
    *,
    observation: ColdObservation,
    journal: ColdJournal,
    runtime,
    provider,
    spend: SpendLedger,
    verify_sandbox: Callable[[str], None],
    clock: Callable[[], float] = time.monotonic,
) -> ColdObservation:
    """Measure actual launch-to-pwd, preserving failures and unknown usage.

    Admit all 32 burst observations durably before scheduling this coroutine
    concurrently. No semaphore or retries are hidden inside the measurement.
    Caller cancellation propagates after bounded cleanup, leaving durable
    incomplete/failed evidence. The provider must enforce the 240s lifetime.
    """
    expected = {
        "environment": "staging",
        "chat_sandbox_modal_environment": "pwc-chat-staging",
        "chat_modal_image_version": journal.image_id,
        "chat_sandbox_cpu": 0.5,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
    }
    for settings in (runtime.settings, provider.settings):
        if any(getattr(settings, key) != value for key, value in expected.items()):
            raise ValueError("runtime/provider differs from frozen cold shape or image")
    await _blocking_transition(journal.begin, observation)
    box = channel = None
    row = observation
    try:
        reservation_id = await _blocking_transition(
            spend.reserve, row.worker_generation
        )
        row = replace(row, reservation_id=reservation_id)
        await _blocking_transition(journal.save, row)
        started = clock()
        async with asyncio.timeout(SANDBOX_LIFETIME_SECONDS):
            launch = await runtime.prepare_launch(row.worker_generation)
            box = await provider.create(
                name=row.worker_generation,
                tags={
                    "environment": "staging",
                    "purpose": "cold-qualification",
                    "qualification_profile": "persistent-cold",
                    "profile": row.profile,
                },
                worker_generation=row.worker_generation,
                launch_mode=SandboxLaunchMode.EXECUTOR,
                executor_launch=launch,
            )
            row = replace(row, sandbox_id=box.object_id)
            await _blocking_transition(journal.save, row)
            await _blocking_transition(spend.created, reservation_id, box.object_id)
            verify_sandbox(box.object_id)
            turn_id, workspace_id = uuid.uuid4(), uuid.uuid4()
            channel = await runtime.attach_channel(
                SimpleNamespace(worker_generation=row.worker_generation),
                SimpleNamespace(turn_id=turn_id, lease_generation=1),
                SANDBOX_LIFETIME_SECONDS,
            )
            context = ExecutorContext(
                sandbox=box,
                workspace_id=str(workspace_id),
                workspace_generation=1,
                session_id=str(workspace_id),
                turn_id=str(turn_id),
                execution_id="first-pwd",
                tool_call_id="first-pwd",
                worker_generation=row.worker_generation,
                capability="cold-qualification-no-gateway-access",
                turn_worker_id="cold-qualification",
                turn_worker_generation="1",
                turn_lease_generation="1",
                turn_deadline_unix_ms=int(time.time() * 1000) + 120_000,
            )
            await channel.ensure_workspace(context)
            response = await channel.exec_resumable(
                context, command="pwd", timeout_ms=1000
            )
            elapsed = (clock() - started) * 1000
            if response.terminal.get("exit_code") != 0:
                raise RuntimeError("cold command did not exit successfully")
            row = replace(row, elapsed_ms=elapsed)
    except Exception as error:
        # This is a measurement boundary, not an operational fallback. Do not
        # persist exception messages that might contain authorization material.
        row = replace(row, error=type(error).__name__)
    finally:
        if channel is not None:
            try:
                async with asyncio.timeout(5):
                    await channel.aclose()
            except Exception as error:
                row = replace(row, cleanup_error="channel:" + type(error).__name__)
        if box is not None:
            try:
                async with asyncio.timeout(CLEANUP_TIMEOUT_SECONDS):
                    if not await provider.terminate(box.object_id, box):
                        raise RuntimeError("provider termination is unconfirmed")
                    while await provider.poll(box) is None:
                        await asyncio.sleep(0.1)
                await _blocking_transition(spend.terminated, box.object_id)
                row = replace(row, terminal_confirmed=True)
            except Exception as error:
                row = replace(row, cleanup_error="sandbox:" + type(error).__name__)
        # Unknown creation results retain their reservation for reconciliation.
        await _blocking_transition(journal.save, row)
    row = replace(row, completed=True)
    await _blocking_transition(journal.save, row)
    return row


async def collect_cold_stage(
    *,
    journal: ColdJournal,
    runtime,
    provider,
    spend: SpendLedger,
    verify_sandbox: Callable[[str], None],
    preflight: Callable[[int], Awaitable[None]],
) -> dict:
    """Collect 1,000 fresh observations in batches of four, then a 32-way burst.

    Preflight must reject before admission unless the isolated cell and host can
    accept the entire batch. The 32-way burst is never queued through a smaller
    ordinary capacity limit. Early-stop is failure, never a smaller passing run.
    The caller still needs independent resource/security/identity evidence.
    """
    for profile, count in COLD_SAMPLE_COUNTS.items():
        width = 32 if profile == "cold_32_way" else 4
        for offset in range(0, count, width):
            await preflight(width)
            admitted = await _blocking_transition(
                lambda: [
                    journal.admit(profile, i) for i in range(offset, offset + width)
                ]
            )
            # Admission files are durable before any member starts its clock.
            results = await asyncio.gather(
                *(
                    collect_cold_observation(
                        observation=row,
                        journal=journal,
                        runtime=runtime,
                        provider=provider,
                        spend=spend,
                        verify_sandbox=verify_sandbox,
                    )
                    for row in admitted
                ),
                return_exceptions=True,
            )
            # Finish cleanup of every sibling before propagating journal failures.
            errors = [result for result in results if isinstance(result, BaseException)]
            if errors:
                raise BaseExceptionGroup("cold collection interrupted", errors)
            rows = await _blocking_transition(read_observations, journal.directory)
            if cold_gate_impossible(rows) or any(
                row.cleanup_error or not row.terminal_confirmed for row in rows
            ):
                result = cold_stage_result(rows)
                await _blocking_transition(journal.save_result, result)
                return result
    result = cold_stage_result(
        await _blocking_transition(read_observations, journal.directory)
    )
    await _blocking_transition(journal.save_result, result)
    return result
