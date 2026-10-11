"""Accounting ledgers for provider calls.

A ledger records one call's reservation, ambiguous-dispatch boundary, and
settlement in the session the lifecycle hands it. It never opens, commits, or
rolls back a transaction; the lifecycle owns every transaction boundary.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatOpenRouterProviderCall
from backend.services.chat_openai_budget_service import (
    ChatOpenAIBudgetService,
    OpenAIBudgetError,
    OpenAIBudgetExhausted,
    OpenAILimitExceeded,
    OpenAIRequestBounds,
    actual_usage_microusd,
)
from backend.services.chat_openai_usage_extractor import ExtractedOpenAIUsage
from backend.services.chat_provider_gateway.lifecycle import (
    ProviderError,
    ProviderReservationRejected,
    UsageStream,
)
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    require_openrouter_budget,
)
from backend.services.openrouter_byok_service import OpenRouterBYOKService
from backend.services.openrouter_usage_extractor import ExtractedOpenRouterUsage
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterAbuseLimitExceeded,
    OpenRouterMonthlyBudgetExhausted,
    OpenRouterPricingUnavailable,
    OpenRouterUserBudgetService,
    RequestBounds,
)


def _retry_after(retry_at: datetime) -> dict[str, str]:
    seconds = math.ceil((retry_at - datetime.now(UTC)).total_seconds())
    return {"Retry-After": str(max(1, seconds))}


def openai_unavailable() -> dict[str, str]:
    return {"code": "openai_unavailable", "message": "Direct OpenAI is unavailable."}


def openrouter_unavailable() -> dict[str, Any]:
    return {
        "code": "openrouter_unavailable",
        "message": (
            "OpenRouter is currently unavailable. However, you can "
            "still bring your own key in Settings."
        ),
        "byok_settings_available": True,
        "support_url": PUBLIC_SUPPORT_URL,
    }


@dataclass(slots=True)
class OpenAIResponsesLedger:
    """Direct-OpenAI allowance accounting for one Responses call."""

    settings: Settings
    capability_id: uuid.UUID
    owner_id: str
    public_model_id: str
    reasoning_effort: str
    request_bytes: int
    maximum_output_tokens: int
    qualification_scope_id: uuid.UUID | None
    name: str = "openai"
    metered: bool = True
    call_id: uuid.UUID | None = None
    reserved_microusd: int | None = None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        self.call_id = uuid.uuid5(
            self.capability_id, f"openai-provider-call:{call_sequence}"
        )
        try:
            reservation = ChatOpenAIBudgetService(db, self.settings).reserve_call(
                owner_id=self.owner_id,
                turn_id=turn_id,
                call_id=self.call_id,
                call_sequence=call_sequence,
                public_model_id=self.public_model_id,
                provider_model=self.settings.chat_openai_model,
                reasoning_effort=self.reasoning_effort,
                bounds=OpenAIRequestBounds(
                    request_bytes=self.request_bytes,
                    maximum_output_tokens=self.maximum_output_tokens,
                ),
                qualification_scope_id=self.qualification_scope_id,
            )
        except OpenAIBudgetExhausted:
            raise ProviderReservationRejected(
                "openai_budget_exhausted",
                status_code=429,
                detail={
                    "code": "openai_budget_exhausted",
                    "message": (
                        "The Papers With Code direct OpenAI allowance is exhausted."
                    ),
                },
            ) from None
        except OpenAILimitExceeded as error:
            code = f"openai_{error.scope}_limited"
            raise ProviderReservationRejected(
                code,
                status_code=429,
                detail={
                    "code": code,
                    "message": "Direct OpenAI usage is temporarily limited.",
                },
                headers=(
                    None if error.retry_at is None else _retry_after(error.retry_at)
                ),
            ) from None
        except OpenAIBudgetError:
            raise ProviderReservationRejected(
                "openai_unavailable", status_code=503, detail=openai_unavailable()
            ) from None
        self.reserved_microusd = reservation.reserved_microusd

    def mark_dispatched(self, db: Session) -> None:
        ChatOpenAIBudgetService(db, self.settings).mark_dispatched(self.call_id)

    def trace_accounting(self) -> dict[str, Any]:
        return {
            "accounting_call_id": str(self.call_id),
            "reserved_microusd": self.reserved_microusd,
        }

    def mark_unknown(self, db: Session, error_code: str) -> None:
        ChatOpenAIBudgetService(db, self.settings).mark_cost_unknown(
            self.call_id, error_code=error_code
        )

    def settle_rejected(
        self,
        db: Session,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None:
        ChatOpenAIBudgetService(db, self.settings).settle_call(
            self.call_id,
            failure.usage,
            provider_request_id=provider_request_id,
            error_code=failure.code,
            latency_ms=latency_ms,
        )

    def record_ttft(self, db: Session, elapsed_ms: int) -> None:
        # Responses TTFT is settled together with the call.
        del db, elapsed_ms

    def settle(
        self,
        db: Session,
        usage: UsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> ExtractedOpenAIUsage:
        result = usage.result()
        ChatOpenAIBudgetService(db, self.settings).settle_call(
            self.call_id,
            result,
            provider_request_id=provider_request_id,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            error_code=error_code,
        )
        return replace(
            result, cost_microusd=actual_usage_microusd(self.settings, result)
        )


@dataclass(slots=True)
class OpenRouterFundedLedger:
    """Shared Papers With Code OpenRouter allowance for one funded call."""

    settings: Settings
    capability_id: uuid.UUID
    owner_id: str
    model: str
    reasoning_effort: str
    request_bytes: int
    maximum_output_tokens: int
    payload: dict[str, Any]
    name: str = "openrouter"
    metered: bool = True
    call_id: uuid.UUID | None = None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        try:
            await require_openrouter_budget(self.settings)
        except (OpenRouterBudgetExceeded, OpenRouterBudgetUnavailable):
            raise ProviderReservationRejected(
                "openrouter_unavailable",
                status_code=503,
                detail=openrouter_unavailable(),
            ) from None
        self.call_id = uuid.uuid5(self.capability_id, f"provider-call:{call_sequence}")
        try:
            OpenRouterUserBudgetService(db, self.settings).reserve_call(
                self.owner_id,
                turn_id,
                self.call_id,
                call_sequence,
                self.model,
                RequestBounds(
                    request_bytes=self.request_bytes,
                    maximum_output_tokens=self.maximum_output_tokens,
                    payload=self.payload,
                ),
                reasoning_effort=self.reasoning_effort,
            )
        except OpenRouterMonthlyBudgetExhausted as error:
            resets_at = error.resets_at.isoformat().replace("+00:00", "Z")

            def exhausted() -> dict[str, Any]:
                usage = OpenRouterUserBudgetService(
                    db, self.settings
                ).status_percentage(self.owner_id)
                return {
                    "code": "openrouter_monthly_budget_exhausted",
                    "message": (
                        "The remaining shared Papers With Code OpenRouter allowance "
                        "is not enough for another model call."
                    ),
                    "used_percent": usage.used_percent,
                    "remaining_percent": usage.remaining_percent,
                    "resets_at": resets_at,
                }

            raise ProviderReservationRejected(
                "openrouter_monthly_budget_exhausted",
                status_code=429,
                detail=exhausted,
            ) from None
        except OpenRouterAbuseLimitExceeded as error:
            code = f"openrouter_{error.scope}_limited"
            raise ProviderReservationRejected(
                code,
                status_code=429,
                detail={
                    "code": code,
                    "message": (
                        "Shared OpenRouter usage is temporarily limited. "
                        "You can retry later or use your own key in Settings."
                    ),
                    "byok_settings_available": True,
                },
                headers=_retry_after(error.retry_at),
            ) from None
        except OpenRouterPricingUnavailable:
            raise ProviderReservationRejected(
                "openrouter_unavailable",
                status_code=503,
                detail=openrouter_unavailable(),
            ) from None

    def mark_dispatched(self, db: Session) -> None:
        OpenRouterUserBudgetService(db, self.settings).mark_dispatched(self.call_id)

    def trace_accounting(self) -> dict[str, Any]:
        return {}

    def mark_unknown(self, db: Session, error_code: str) -> None:
        del error_code
        OpenRouterUserBudgetService(db, self.settings).mark_cost_unknown(self.call_id)

    def settle_rejected(
        self,
        db: Session,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None:
        # Messages relays provider failures, so settlement reads their usage.
        del db, failure, provider_request_id, latency_ms

    def record_ttft(self, db: Session, elapsed_ms: int) -> None:
        call = db.get(ChatOpenRouterProviderCall, self.call_id)
        if call is not None and call.provider_ttft_ms is None:
            call.provider_ttft_ms = elapsed_ms

    def settle(
        self,
        db: Session,
        usage: UsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> ExtractedOpenRouterUsage:
        del provider_request_id, latency_ms, ttft_ms, error_code
        result = usage.result()
        service = OpenRouterUserBudgetService(db, self.settings)
        if result.cost_microusd is None:
            service.mark_cost_unknown(self.call_id, result.generation_id)
        else:
            service.settle_call(
                self.call_id, result.cost_microusd, result.generation_id
            )
        call = db.get(ChatOpenRouterProviderCall, self.call_id)
        if call is not None:
            call.upstream_provider = result.provider
            call.prompt_tokens = result.prompt_tokens
            call.completion_tokens = result.completion_tokens
            call.cache_read_tokens = result.cache_read_tokens
            call.cache_creation_tokens = result.cache_creation_tokens
        return result


@dataclass(slots=True)
class UserBilledLedger:
    """Hugging Face and BYOK calls bill the user's own provider account.

    Only a BYOK ledger carries ``owner_id``, which lets an authentication
    failure revoke the stored OpenRouter credential.
    """

    settings: Settings
    owner_id: str | None = None
    name: str = "provider"
    metered: bool = False
    call_id: uuid.UUID | None = None

    async def reserve(
        self, db: Session, *, turn_id: uuid.UUID, call_sequence: int
    ) -> None:
        del db, turn_id, call_sequence

    def mark_dispatched(self, db: Session) -> None:
        del db

    def trace_accounting(self) -> dict[str, Any]:
        return {}

    def mark_unknown(self, db: Session, error_code: str) -> None:
        del db, error_code

    def settle_rejected(
        self,
        db: Session,
        failure: ProviderError,
        *,
        provider_request_id: str | None,
        latency_ms: int,
    ) -> None:
        del db, failure, provider_request_id, latency_ms

    def record_ttft(self, db: Session, elapsed_ms: int) -> None:
        del db, elapsed_ms

    def settle(
        self,
        db: Session,
        usage: UsageStream,
        *,
        provider_request_id: str | None,
        latency_ms: int,
        ttft_ms: int | None,
        error_code: str | None,
    ) -> Any:
        del db, provider_request_id, latency_ms, ttft_ms, error_code
        return usage.result()

    def revoke_credential(self, db: Session) -> None:
        if self.owner_id is None:
            raise ValueError("Only BYOK calls hold a revocable credential")
        OpenRouterBYOKService(db, self.settings).invalidate_auth_failure(self.owner_id)
