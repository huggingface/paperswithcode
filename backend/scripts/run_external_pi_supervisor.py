"""Run the lifecycle supervisor for one deployed external Pi worker."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.services.chat_external_pi_shadow import ExternalPiWorkerControlClient
from backend.services.chat_external_pi_supervisor import ChatExternalPiSupervisor
from backend.services.chat_external_pi_supervisor_runtime_service import (
    ChatExternalPiSupervisorRuntime,
    StopWaiter,
)
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
)
from backend.services.runtime_validation import validate_external_pi_migration_policy

logger = logging.getLogger(__name__)


def validate_supervisor_settings(settings: Settings) -> None:
    if not settings.chat_external_pi_supervisor_enabled:
        raise RuntimeError("External Pi supervisor is not enabled")
    if settings.environment not in {"staging", "production"}:
        raise RuntimeError("External Pi supervisor requires a deployed environment")
    validate_external_pi_migration_policy(settings)


def build_runtime(
    settings: Settings,
    *,
    http: httpx.AsyncClient,
    session_factory: Callable[[], AbstractContextManager[Session]],
    wait_for_stop: StopWaiter,
    release_connections: Callable[[], None] | None = None,
) -> ChatExternalPiSupervisorRuntime:
    validate_supervisor_settings(settings)
    supervisor = ChatExternalPiSupervisor(
        client=ExternalPiWorkerControlClient(
            base_url=settings.chat_external_pi_worker_url,
            token=settings.chat_external_pi_worker_token,
            http=http,
        ),
        repository=ChatExternalWorkerRepository(environment=settings.environment),
        expected_release_id=settings.release_id,
        expected_contract_version=settings.chat_external_pi_worker_contract_version,
        expected_maximum_sessions=settings.chat_external_pi_worker_max_sessions,
        lease_seconds=settings.chat_external_pi_lease_seconds,
        drain_seconds=settings.chat_external_pi_drain_seconds,
    )
    return ChatExternalPiSupervisorRuntime(
        supervisor=supervisor,
        session_factory=session_factory,
        now=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        wait_for_stop=wait_for_stop,
        sleep=asyncio.sleep,
        heartbeat_interval_seconds=settings.chat_external_pi_heartbeat_seconds,
        startup_timeout_seconds=settings.chat_external_pi_startup_timeout_seconds,
        drain_poll_seconds=settings.chat_external_pi_drain_poll_seconds,
        release_connections=release_connections,
    )


async def run() -> None:
    settings = get_settings()
    validate_supervisor_settings(settings)
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

    async with httpx.AsyncClient() as http:
        result = await build_runtime(
            settings,
            http=http,
            session_factory=db_manager.session_local,
            wait_for_stop=wait_for_stop,
            release_connections=db_manager.engine.dispose,
        ).run()
    logger.info(
        "External Pi supervisor stopped registrations=%d heartbeats=%d drained=%s",
        result.registrations,
        result.heartbeats,
        result.drained,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
