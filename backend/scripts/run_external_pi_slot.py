"""Own durable supervision for one separately isolated external Pi worker."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Literal

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.scripts.run_external_pi_supervisor import build_runtime
from backend.services.chat_external_worker_registry import ExternalWorkerClaim


def _write_status(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


async def run() -> None:
    settings = get_settings()
    status_path = Path(os.environ["PWC_EXTERNAL_PI_STATUS_PATH"])
    state = {
        "release_id": settings.release_id,
        "worker_id": os.environ["PWC_EXTERNAL_PI_WORKER_ID"],
        "state": "starting",
        "authenticated": False,
        "registered": False,
        "generation": None,
        "heartbeats": 0,
        "drained": False,
    }
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
        event: Literal["registered", "heartbeat", "drained"],
        claim: ExternalWorkerClaim,
        heartbeats: int,
    ) -> None:
        state.update(
            {
                "authenticated": True,
                "registered": True,
                "generation": claim.generation,
                "heartbeats": heartbeats,
                "state": "offline" if event == "drained" else "ready",
                "drained": event == "drained",
            }
        )
        _write_status(status_path, state)

    lifecycle_completed = False
    try:
        async with httpx.AsyncClient() as http:
            runtime = build_runtime(
                settings,
                http=http,
                session_factory=db_manager.session_local,
                wait_for_stop=wait_for_stop,
            )
            runtime.observe = observe
            await runtime.run()
            lifecycle_completed = True
    finally:
        if not lifecycle_completed and state["state"] != "offline":
            state["state"] = "failed"
            _write_status(status_path, state)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
