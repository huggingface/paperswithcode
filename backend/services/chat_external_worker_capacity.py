"""Atomic protected-capacity selection for configured external Pi endpoints."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from backend.models.database import (
    ChatExternalWorker,
    ChatExternalWorkerReservation,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim
from backend.config import ExternalPiWorkerEndpointConfig, Settings


class ExternalWorkerCapacityUnavailable(RuntimeError):
    """No configured live worker has an unreserved protected slot."""


@dataclass(frozen=True, slots=True)
class ExternalWorkerEndpoint:
    endpoint_id: str
    worker_id: str
    base_url: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            not self.endpoint_id
            or len(self.endpoint_id) > 128
            or not self.worker_id
            or len(self.worker_id) > 128
            or parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or len(self.token) < 32
        ):
            raise ValueError("External worker endpoint is invalid")


def external_worker_endpoints(settings: Settings) -> tuple[ExternalWorkerEndpoint, ...]:
    """Return one validated bounded topology, preserving a safe legacy singleton."""
    legacy_values = (
        settings.chat_external_pi_worker_id,
        settings.chat_external_pi_worker_url,
        settings.chat_external_pi_worker_token,
    )
    if settings.chat_external_pi_worker_endpoints and any(legacy_values):
        raise ValueError("External worker topology is ambiguous")
    try:
        parsed_items = tuple(
            ExternalPiWorkerEndpointConfig.model_validate(item, strict=True)
            for item in settings.chat_external_pi_worker_endpoints
        )
    except ValidationError:
        raise ValueError("External worker endpoint is invalid") from None
    configured = tuple(
        ExternalWorkerEndpoint(
            endpoint_id=item.endpoint_id,
            worker_id=item.worker_id,
            base_url=item.base_url,
            token=item.token,
        )
        for item in parsed_items
    )
    if configured:
        ChatExternalWorkerCapacityRepository._endpoint_map(configured)
        return configured
    if all(legacy_values):
        return (
            ExternalWorkerEndpoint(
                endpoint_id="legacy",
                worker_id=settings.chat_external_pi_worker_id,
                base_url=settings.chat_external_pi_worker_url,
                token=settings.chat_external_pi_worker_token,
            ),
        )
    if any(legacy_values):
        raise ValueError("External worker topology is incomplete")
    raise ValueError("External worker topology is not configured")


@dataclass(frozen=True, slots=True)
class ExternalWorkerReservation:
    request_id: str
    turn_id: uuid.UUID | None
    endpoint: ExternalWorkerEndpoint
    worker_claim: ExternalWorkerClaim
    maximum_sessions: int

    @property
    def endpoint_id(self) -> str:
        return self.endpoint.endpoint_id


class ChatExternalWorkerCapacityRepository:
    """Reserve a fleet slot before chat admission mutates any projection."""

    def __init__(
        self,
        *,
        environment: str,
        unbound_ttl_seconds: int = 60,
        active_ttl_seconds: int = 900,
    ) -> None:
        if environment not in {"staging", "production"}:
            raise ValueError("External worker environment is invalid")
        if not 5 <= unbound_ttl_seconds <= 300:
            raise ValueError("External worker reservation TTL is invalid")
        if not 60 <= active_ttl_seconds <= 3600:
            raise ValueError("External worker active reservation TTL is invalid")
        self.environment = environment
        self.unbound_ttl_seconds = unbound_ttl_seconds
        self.active_ttl_seconds = active_ttl_seconds

    @staticmethod
    def _expired(value: datetime, now: datetime) -> bool:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value <= now

    @staticmethod
    def _endpoint_map(
        endpoints: tuple[ExternalWorkerEndpoint, ...],
    ) -> dict[str, ExternalWorkerEndpoint]:
        if not 1 <= len(endpoints) <= 16:
            raise ValueError("External worker topology is invalid")
        by_worker = {endpoint.worker_id: endpoint for endpoint in endpoints}
        if any(
            len(values) != len(endpoints)
            for values in (
                by_worker,
                {endpoint.endpoint_id for endpoint in endpoints},
                {endpoint.base_url for endpoint in endpoints},
                {endpoint.token for endpoint in endpoints},
            )
        ):
            raise ValueError("External worker topology is ambiguous")
        return by_worker

    @staticmethod
    def _reservation(
        row: ChatExternalWorkerReservation,
        endpoint: ExternalWorkerEndpoint,
    ) -> ExternalWorkerReservation:
        return ExternalWorkerReservation(
            request_id=row.request_id,
            turn_id=row.turn_id,
            endpoint=endpoint,
            worker_claim=ExternalWorkerClaim(
                worker_id=row.worker_id,
                instance_id=row.instance_id,
                generation=row.worker_generation,
                release_id=row.release_id,
                contract_version=row.contract_version,
            ),
            maximum_sessions=row.maximum_sessions,
        )

    def reserve(
        self,
        db: Session,
        *,
        request_id: str,
        endpoints: tuple[ExternalWorkerEndpoint, ...],
        contract_version: str,
        now: datetime,
    ) -> ExternalWorkerReservation:
        if not request_id or now.tzinfo is None or not contract_version:
            raise ValueError("External worker reservation is invalid")
        endpoint_by_worker = self._endpoint_map(endpoints)
        existing = db.get(ChatExternalWorkerReservation, request_id)
        if existing is not None:
            if existing.turn_id is None and self._expired(existing.expires_at, now):
                db.delete(existing)
                db.flush()
                existing = None
        if existing is not None:
            endpoint = endpoint_by_worker.get(existing.worker_id)
            if endpoint is None or endpoint.endpoint_id != existing.endpoint_id:
                raise ExternalWorkerCapacityUnavailable(
                    "Reserved external worker endpoint is no longer configured"
                )
            return self._reservation(existing, endpoint)

        db.execute(
            delete(ChatExternalWorkerReservation).where(
                ChatExternalWorkerReservation.turn_id.is_(None),
                ChatExternalWorkerReservation.expires_at <= now,
            )
        )
        query = (
            select(ChatExternalWorker)
            .where(
                ChatExternalWorker.environment == self.environment,
                ChatExternalWorker.worker_id.in_(endpoint_by_worker),
                ChatExternalWorker.contract_version == contract_version,
                ChatExternalWorker.state == "ready",
                ChatExternalWorker.lease_expires_at > now,
            )
            .order_by(ChatExternalWorker.worker_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        workers = tuple(db.scalars(query))
        for worker in workers:
            reserved = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatExternalWorkerReservation)
                    .where(
                        ChatExternalWorkerReservation.worker_id == worker.worker_id,
                        ChatExternalWorkerReservation.instance_id == worker.instance_id,
                        ChatExternalWorkerReservation.worker_generation
                        == worker.generation,
                        ChatExternalWorkerReservation.expires_at > now,
                    )
                )
                or 0
            )
            if max(reserved, worker.active_sessions) >= worker.maximum_sessions:
                continue
            endpoint = endpoint_by_worker[worker.worker_id]
            row = ChatExternalWorkerReservation(
                request_id=request_id,
                turn_id=None,
                endpoint_id=endpoint.endpoint_id,
                worker_id=worker.worker_id,
                instance_id=worker.instance_id,
                worker_generation=worker.generation,
                release_id=worker.release_id,
                contract_version=worker.contract_version,
                maximum_sessions=worker.maximum_sessions,
                reserved_at=now,
                expires_at=now + timedelta(seconds=self.unbound_ttl_seconds),
            )
            db.add(row)
            db.flush()
            return self._reservation(row, endpoint)
        raise ExternalWorkerCapacityUnavailable("External worker capacity is full")

    def bind_turn(
        self,
        db: Session,
        *,
        reservation: ExternalWorkerReservation,
        turn_id: uuid.UUID,
        now: datetime,
    ) -> None:
        row = db.get(ChatExternalWorkerReservation, reservation.request_id)
        if row is None or (row.turn_id is not None and row.turn_id != turn_id):
            raise ExternalWorkerCapacityUnavailable(
                "External worker reservation was lost"
            )
        row.turn_id = turn_id
        row.expires_at = now + timedelta(seconds=self.active_ttl_seconds)
        db.flush()

    def require_turn(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        endpoints: tuple[ExternalWorkerEndpoint, ...],
        now: datetime,
        lock: bool = False,
    ) -> ExternalWorkerReservation:
        endpoint_by_worker = self._endpoint_map(endpoints)
        statement = select(ChatExternalWorkerReservation).where(
            ChatExternalWorkerReservation.turn_id == turn_id
        )
        if lock:
            statement = statement.with_for_update()
        row = db.scalar(statement)
        if row is None:
            raise ExternalWorkerCapacityUnavailable(
                "External worker reservation is missing"
            )
        endpoint = endpoint_by_worker.get(row.worker_id)
        worker = db.get(ChatExternalWorker, row.worker_id)
        if (
            endpoint is None
            or endpoint.endpoint_id != row.endpoint_id
            or worker is None
            or worker.environment != self.environment
            or worker.instance_id != row.instance_id
            or worker.generation != row.worker_generation
            or worker.release_id != row.release_id
            or worker.contract_version != row.contract_version
            or worker.state not in {"ready", "draining"}
            or self._expired(row.expires_at, now)
            or self._expired(worker.lease_expires_at, now)
        ):
            raise ExternalWorkerCapacityUnavailable(
                "Reserved external worker claim is no longer live"
            )
        return self._reservation(row, endpoint)

    @staticmethod
    def release_turn(db: Session, *, turn_id: uuid.UUID) -> None:
        db.execute(
            delete(ChatExternalWorkerReservation).where(
                ChatExternalWorkerReservation.turn_id == turn_id
            )
        )
