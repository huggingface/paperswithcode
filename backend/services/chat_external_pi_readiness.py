"""Read-only proof that the configured external Pi endpoint can accept work."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_external_pi_shadow import ExternalPiWorkerControlClient
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
    WorkerLeaseUnavailable,
)
from backend.services.chat_external_worker_capacity import external_worker_endpoints
from backend.services.runtime_validation import (
    validate_external_worker_reservation_schema,
)


async def validate_external_pi_readiness(settings: Settings) -> None:
    endpoints = external_worker_endpoints(settings)
    async with httpx.AsyncClient() as http:
        statuses = []
        for endpoint in endpoints:
            status = await ExternalPiWorkerControlClient(
                base_url=endpoint.base_url,
                token=endpoint.token,
                http=http,
                timeout_seconds=5.0,
            ).status()
            if (
                status.worker_id != endpoint.worker_id
                or status.worker_generation is None
                or status.state != "ready"
                or status.release_id != settings.release_id
                or status.protocol != settings.chat_external_pi_worker_contract_version
                or status.active_sessions >= status.maximum_sessions
            ):
                raise WorkerLeaseUnavailable("External worker is not ready")
            statuses.append(status)
    with db_manager.session_local() as db:
        validate_external_worker_reservation_schema(db)
        repository = ChatExternalWorkerRepository(environment=settings.environment)
        for status in statuses:
            repository.require_endpoint_ready(
                db,
                claim=ExternalWorkerClaim(
                    worker_id=status.worker_id,
                    instance_id=status.instance_id,
                    generation=status.worker_generation,
                    release_id=status.release_id,
                    contract_version=status.protocol,
                ),
                active_sessions=status.active_sessions,
                maximum_sessions=status.maximum_sessions,
                configured_maximum_sessions=settings.chat_external_pi_worker_max_sessions,
                now=datetime.now(UTC),
            )
