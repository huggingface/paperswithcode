"""Own durable supervision for one separately isolated external Pi worker."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.scripts.run_external_pi_supervisor import build_runtime
from backend.services.chat_external_pi_supervisor_runtime_service import (
    ExternalPiSupervisorRunResult,
    LifecycleEvent,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim


def _write_status(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _status_update(
    event: LifecycleEvent, claim: ExternalWorkerClaim, heartbeats: int
) -> dict:
    """Translate a lifecycle event into the durable status file's vocabulary."""
    # A lost lease sends the runtime back through registration, so report the
    # same transitional state as a fresh start until a new claim lands. The
    # lost generation stays on record: the worker endpoint is still bound to it.
    if event == "lease_lost":
        worker_state = "starting"
    elif event == "drained":
        worker_state = "offline"
    else:
        worker_state = "ready"
    return {
        "authenticated": True,
        "registered": event != "lease_lost",
        "generation": claim.generation,
        "heartbeats": heartbeats,
        "state": worker_state,
        "drained": event == "drained",
    }


def _lifecycle_completed(result: ExternalPiSupervisorRunResult) -> bool:
    """Whether the run ended in a shape the deploy lifecycle can prove stopped.

    A drained run is offline. A stop before the first claim never bound the
    worker, so the initial "starting" status stays truthful. A stop that
    interrupts re-registration leaves the worker bound to a lost claim with no
    drain behind it; that must be reported as "failed" so `stop_slot` applies
    its expired-lease proof instead of finding an unprovable status.
    """
    return result.drained or result.registrations == 0


def _initial_status(settings, worker_id: str) -> dict:
    return {
        "protocol": settings.chat_external_pi_worker_contract_version,
        "release_id": settings.release_id,
        "worker_id": worker_id,
        "maximum_sessions": settings.chat_external_pi_worker_max_sessions,
        "state": "starting",
        "authenticated": False,
        "registered": False,
        "generation": None,
        "heartbeats": 0,
        "drained": False,
    }


async def run() -> None:
    settings = get_settings()
    status_path = Path(os.environ["PWC_EXTERNAL_PI_STATUS_PATH"])
    state = _initial_status(settings, os.environ["PWC_EXTERNAL_PI_WORKER_ID"])
    _write_status(status_path, state)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for termination_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(termination_signal, stop.set)

    async def wait_for_stop(seconds: float) -> bool:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True

    def observe(
        event: LifecycleEvent,
        claim: ExternalWorkerClaim,
        heartbeats: int,
    ) -> None:
        state.update(_status_update(event, claim, heartbeats))
        _write_status(status_path, state)

    lifecycle_completed = False
    try:
        async with httpx.AsyncClient() as http:
            runtime = build_runtime(
                settings,
                http=http,
                session_factory=db_manager.session_local,
                wait_for_stop=wait_for_stop,
                release_connections=db_manager.engine.dispose,
            )
            runtime.observe = observe
            lifecycle_completed = _lifecycle_completed(await runtime.run())
    finally:
        if not lifecycle_completed and state["state"] != "offline":
            state["state"] = "failed"
            _write_status(status_path, state)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
