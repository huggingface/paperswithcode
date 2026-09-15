"""Persist one circuit-selected executor transport before turn work starts."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import ROUND_CEILING, Decimal

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.chat_execution_policy import (
    MAX_PROVIDER_REQUESTS,
    MAX_PROVIDER_TURN_TOKENS,
)
from backend.services.chat_openai_budget_service import (
    OpenAIRequestBounds,
    safe_maximum_microusd as safe_openai_maximum_microusd,
)
from backend.services.openrouter_user_budget_service import (
    RequestBounds,
    safe_maximum_microusd as safe_openrouter_maximum_microusd,
)
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


def maximum_provider_turn_microusd(
    settings: Settings, *, model_route: str, now: datetime
) -> int:
    """Price the full server-funded provider envelope before turn admission."""
    funding_mode = settings.chat_route_funding_modes.get(model_route)
    if funding_mode in {None, "hf_user_billed"}:
        return 0
    if funding_mode == "openai_funded":
        safe_openai_maximum_microusd(
            settings,
            OpenAIRequestBounds(request_bytes=1, maximum_output_tokens=1),
            now=now,
        )
        # Gateway metering estimates input as JSON bytes / 4; reserve up to
        # four actual tokens per metered token, including long-context rates.
        rate = max(
            settings.chat_openai_input_microusd_per_million_tokens * 8,
            settings.chat_openai_cache_write_microusd_per_million_tokens * 8,
            settings.chat_openai_output_microusd_per_million_tokens * Decimal("1.5"),
        )
        return int(
            (
                Decimal(MAX_PROVIDER_TURN_TOKENS) * Decimal(rate) / Decimal(1_000_000)
            ).to_integral_value(rounding=ROUND_CEILING)
        )
    if funding_mode == "openrouter_funded":
        safe_openrouter_maximum_microusd(
            settings,
            model_route,
            RequestBounds(request_bytes=1, maximum_output_tokens=1, payload={}),
            now=now,
        )
        token_rate = max(
            settings.chat_openrouter_input_microusd_per_token,
            settings.chat_openrouter_output_microusd_per_token,
        )
        return (
            MAX_PROVIDER_TURN_TOKENS * token_rate
            + MAX_PROVIDER_REQUESTS * settings.chat_openrouter_request_fee_microusd
        )
    raise ValueError("Executor provider funding mode is unsupported")


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
        model_route: str,
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
            reserve_microusd=(
                ChatSandboxSpendService(db, self.settings).reservation_amount()
                + maximum_provider_turn_microusd(
                    self.settings, model_route=model_route, now=now
                )
            ),
            transport=decision.transport,
            now=now,
        )
