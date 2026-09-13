"""Persist one circuit-selected executor transport before turn work starts."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_executor_runtime import ChatExecutorRuntime
from backend.services.chat_executor_transport_circuit import (
    ROUTE_HEALTH_MAX_SECONDS,
    ExecutorTransportCircuit,
)
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_turn_admission import (
    ChatTurnAdmissionService,
    TurnReservation,
)

RuntimeFactory = Callable[[Settings, Callable[[], Session]], ChatExecutorRuntime]


class ChatExecutorTurnAdmission:
    """Compose live route health, the shared circuit, and capacity reservation."""

    def __init__(
        self,
        settings: Settings,
        *,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self.settings = settings
        self.runtime_factory = runtime_factory or (
            lambda settings, sessions: ChatExecutorRuntime(
                settings, session_factory=sessions
            )
        )

    def reserve(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        request_id: str,
        owner_id: str,
        now: datetime,
    ) -> TurnReservation:
        circuit = ExecutorTransportCircuit(environment=self.settings.environment)
        reservations = ChatTurnAdmissionService(
            environment=self.settings.environment,
            spend_limit_microusd=self.settings.chat_sandbox_application_cap_microusd,
        )
        circuit.initialize(db, now=now)
        reservations.initialize(db, now=now)
        try:
            route_health = self.runtime_factory(
                self.settings, lambda: db
            ).route_health_seconds(db)
        except (ConnectionError, OSError, ValueError):
            route_health = None
        if route_health is None or route_health > ROUTE_HEALTH_MAX_SECONDS:
            circuit.record_attach_failure(db, now=now)
        decision = circuit.choose(
            db,
            remote_enabled=self.settings.chat_executor_remote_transport_enabled,
            route_health_seconds=route_health,
            canary_owner=str(turn_id),
            now=now,
        )
        return reservations.reserve(
            db,
            turn_id=turn_id,
            request_id=request_id,
            owner_id=owner_id,
            reserve_microusd=ChatSandboxSpendService(
                db, self.settings
            ).reservation_amount(),
            transport=decision.transport,
            now=now,
        )
