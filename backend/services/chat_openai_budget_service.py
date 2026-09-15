"""Durable fail-closed accounting for server-funded direct OpenAI calls."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.chat_execution_policy import MAX_PROVIDER_REQUEST_BYTES
from backend.models.database import (
    ChatOpenAIMonthlyUsage,
    ChatOpenAIProviderCall,
    ChatQualificationScope,
    ChatTurnLatency,
    ChatTurnJob,
)
from backend.services.durable_external_qualification_contract import (
    DURABLE_QUALIFICATION_OPENAI_GLOBAL_CONCURRENCY,
    DURABLE_QUALIFICATION_OPENAI_REQUEST_LIMIT,
)
from backend.services.chat_openai_usage_extractor import ExtractedOpenAIUsage
from backend.services.openrouter_user_budget_service import usd_to_microusd, utc_month

# GPT-5.6 Luna: https://developers.openai.com/api/docs/models/gpt-5.6-luna
MAX_REQUEST_BYTES = MAX_PROVIDER_REQUEST_BYTES
MAX_BILLABLE_INPUT_TOKENS = 1_050_000
LONG_CONTEXT_INPUT_THRESHOLD = 272_000


def long_context_rates(input_tokens: int) -> tuple[Decimal, Decimal]:
    if input_tokens > LONG_CONTEXT_INPUT_THRESHOLD:
        return Decimal(2), Decimal("1.5")
    return Decimal(1), Decimal(1)


class OpenAIBudgetError(RuntimeError):
    pass


class OpenAIBudgetExhausted(OpenAIBudgetError):
    pass


class OpenAILimitExceeded(OpenAIBudgetError):
    def __init__(self, scope: str, retry_at: datetime | None = None):
        super().__init__(f"Direct OpenAI {scope} limit reached")
        self.scope = scope
        self.retry_at = retry_at


class OpenAIPricingUnavailable(OpenAIBudgetError):
    pass


class OpenAIAccountingInvariantError(OpenAIBudgetError):
    pass


@dataclass(frozen=True)
class OpenAIRequestBounds:
    request_bytes: int
    maximum_output_tokens: int


def _rate(settings: Settings, name: str) -> int:
    value = getattr(settings, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OpenAIPricingUnavailable(f"Missing direct OpenAI price: {name}")
    return value


def _priced_microusd(tokens: int, rate_per_million: int | Decimal) -> int:
    return int(
        (
            Decimal(tokens) * Decimal(rate_per_million) / Decimal(1_000_000)
        ).to_integral_value(rounding=ROUND_CEILING)
    )


def safe_maximum_microusd(
    settings: Settings, bounds: OpenAIRequestBounds, *, now: datetime | None = None
) -> int:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        verified = date.fromisoformat(settings.chat_openai_pricing_verified_at)
    except (AttributeError, ValueError) as error:
        raise OpenAIPricingUnavailable(
            "Direct OpenAI pricing date is invalid"
        ) from error
    if current.date() - verified > timedelta(
        days=settings.chat_openai_pricing_max_age_days
    ):
        raise OpenAIPricingUnavailable("Direct OpenAI pricing is stale")
    if not 1 <= bounds.request_bytes <= MAX_REQUEST_BYTES:
        raise OpenAIPricingUnavailable("Direct OpenAI request size is unbounded")
    if not 1 <= bounds.maximum_output_tokens <= 128_000:
        raise OpenAIPricingUnavailable("Direct OpenAI output is unbounded")
    input_rate = max(
        _rate(settings, "chat_openai_input_microusd_per_million_tokens"),
        _rate(settings, "chat_openai_cache_write_microusd_per_million_tokens"),
    )
    maximum_input_tokens = min(bounds.request_bytes, MAX_BILLABLE_INPUT_TOKENS)
    input_multiplier, output_multiplier = long_context_rates(maximum_input_tokens)
    return _priced_microusd(
        maximum_input_tokens, input_rate * input_multiplier
    ) + _priced_microusd(
        bounds.maximum_output_tokens,
        _rate(settings, "chat_openai_output_microusd_per_million_tokens")
        * output_multiplier,
    )


def actual_usage_microusd(
    settings: Settings, usage: ExtractedOpenAIUsage
) -> int | None:
    required = (usage.input_tokens, usage.output_tokens)
    if any(value is None for value in required):
        return None
    cached = usage.cached_input_tokens or 0
    cache_write = usage.cache_write_tokens or 0
    if cached + cache_write > usage.input_tokens:
        raise OpenAIAccountingInvariantError("OpenAI input usage details exceed total")
    ordinary = usage.input_tokens - cached - cache_write
    input_multiplier, output_multiplier = long_context_rates(usage.input_tokens)
    return sum(
        (
            _priced_microusd(
                ordinary,
                _rate(settings, "chat_openai_input_microusd_per_million_tokens")
                * input_multiplier,
            ),
            _priced_microusd(
                cached,
                _rate(settings, "chat_openai_cached_input_microusd_per_million_tokens")
                * input_multiplier,
            ),
            _priced_microusd(
                cache_write,
                _rate(settings, "chat_openai_cache_write_microusd_per_million_tokens")
                * input_multiplier,
            ),
            _priced_microusd(
                usage.output_tokens,
                _rate(settings, "chat_openai_output_microusd_per_million_tokens")
                * output_multiplier,
            ),
        )
    )


class ChatOpenAIBudgetService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _usage(self, owner_id: str, month: date, *, lock: bool = False):
        query = select(ChatOpenAIMonthlyUsage).where(
            ChatOpenAIMonthlyUsage.owner_id == owner_id,
            ChatOpenAIMonthlyUsage.month_start == month,
        )
        return self.db.execute(
            query.with_for_update() if lock else query
        ).scalar_one_or_none()

    def _ensure_usage(self, owner_id: str, month: date):
        limit = usd_to_microusd(self.settings.chat_openai_monthly_user_budget_usd)
        self.db.execute(
            pg_insert(ChatOpenAIMonthlyUsage)
            .values(owner_id=owner_id, month_start=month, limit_microusd=limit)
            .on_conflict_do_nothing(index_elements=["owner_id", "month_start"])
        )
        row = self._usage(owner_id, month, lock=True)
        if row is None:
            raise OpenAIAccountingInvariantError("OpenAI monthly usage row is missing")
        return row

    def _enforce_concurrency(
        self,
        owner_id: str,
        turn_id: uuid.UUID,
        qualification_scope_id: uuid.UUID | None,
        now: datetime,
    ) -> None:
        active = ChatOpenAIProviderCall.state == "dispatched"
        user_active = int(
            self.db.scalar(
                select(func.count())
                .select_from(ChatOpenAIProviderCall)
                .where(ChatOpenAIProviderCall.owner_id == owner_id, active)
            )
            or 0
        )
        if user_active >= self.settings.chat_openai_user_max_concurrency:
            raise OpenAILimitExceeded("user_concurrency")
        if qualification_scope_id is not None:
            persisted_scope = self.db.scalar(
                select(ChatQualificationScope.id)
                .join(
                    ChatTurnLatency,
                    ChatTurnLatency.qualification_scope_id == ChatQualificationScope.id,
                )
                .where(
                    ChatTurnLatency.turn_id == turn_id,
                    ChatTurnLatency.qualification_profile == "32-functional-turns",
                    ChatQualificationScope.id == qualification_scope_id,
                    ChatQualificationScope.profile == "32-functional-turns",
                    ChatQualificationScope.window_ended_at.is_(None),
                    ChatQualificationScope.expires_at > now,
                )
            )
            if persisted_scope != qualification_scope_id:
                raise OpenAIAccountingInvariantError(
                    "OpenAI qualification scope claim is invalid"
                )
            global_query = (
                select(func.count())
                .select_from(ChatOpenAIProviderCall)
                .join(
                    ChatTurnLatency,
                    ChatTurnLatency.turn_id == ChatOpenAIProviderCall.turn_id,
                )
                .where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    active,
                    ChatTurnLatency.qualification_scope_id == qualification_scope_id,
                )
            )
            limit = DURABLE_QUALIFICATION_OPENAI_GLOBAL_CONCURRENCY
        else:
            qualification_turn = (
                select(ChatTurnLatency.turn_id)
                .where(
                    ChatTurnLatency.turn_id == ChatOpenAIProviderCall.turn_id,
                    ChatTurnLatency.qualification_scope_id.is_not(None),
                )
                .exists()
            )
            global_query = (
                select(func.count())
                .select_from(ChatOpenAIProviderCall)
                .where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    active,
                    ~qualification_turn,
                )
            )
            limit = self.settings.chat_openai_global_max_concurrency
        global_active = int(self.db.scalar(global_query) or 0)
        if global_active >= limit:
            raise OpenAILimitExceeded("global_concurrency")

    def _enforce_rate_limits(
        self,
        owner_id: str,
        qualification_scope_id: uuid.UUID | None,
        now: datetime,
    ) -> None:
        cutoff = now - timedelta(
            seconds=self.settings.chat_openai_rate_limit_window_seconds
        )
        retry_at = now + timedelta(
            seconds=self.settings.chat_openai_rate_limit_window_seconds
        )
        if qualification_scope_id is not None:
            rate_query = (
                select(func.count())
                .select_from(ChatOpenAIProviderCall)
                .join(
                    ChatTurnLatency,
                    ChatTurnLatency.turn_id == ChatOpenAIProviderCall.turn_id,
                )
                .where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    ChatOpenAIProviderCall.reserved_at >= cutoff,
                    ChatOpenAIProviderCall.state != "released",
                    ChatTurnLatency.qualification_scope_id == qualification_scope_id,
                )
            )
            user_limit = global_limit = DURABLE_QUALIFICATION_OPENAI_REQUEST_LIMIT
        else:
            rate_query = (
                select(func.count())
                .select_from(ChatOpenAIProviderCall)
                .where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    ChatOpenAIProviderCall.reserved_at >= cutoff,
                    ChatOpenAIProviderCall.state != "released",
                )
            )
            user_limit = self.settings.chat_openai_user_rate_limit_calls
            global_limit = self.settings.chat_openai_global_rate_limit_calls
        user_rate = int(
            self.db.scalar(
                rate_query.where(ChatOpenAIProviderCall.owner_id == owner_id)
            )
            or 0
        )
        global_rate = int(self.db.scalar(rate_query) or 0)
        if user_rate >= user_limit:
            raise OpenAILimitExceeded("user_rate", retry_at)
        if global_rate >= global_limit:
            raise OpenAILimitExceeded("global_rate", retry_at)

    def _enforce_limits(
        self,
        owner_id: str,
        turn_id: uuid.UUID,
        qualification_scope_id: uuid.UUID | None,
        reserved: int,
        now: datetime,
    ) -> None:
        # One environment-wide transaction lock serializes concurrency, rate,
        # daily, and monthly admission across gateway processes.
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(
                        f"chat-openai-admission:{self.settings.environment}", 0
                    )
                )
            )
        )
        self._enforce_concurrency(owner_id, turn_id, qualification_scope_id, now)
        self._enforce_rate_limits(owner_id, qualification_scope_id, now)
        guarded = case(
            (
                ChatOpenAIProviderCall.state.in_(
                    {"reserved", "dispatched", "cost_unknown"}
                ),
                ChatOpenAIProviderCall.reserved_microusd,
            ),
            (
                ChatOpenAIProviderCall.state == "settled",
                func.coalesce(
                    ChatOpenAIProviderCall.actual_microusd,
                    ChatOpenAIProviderCall.reserved_microusd,
                ),
            ),
            else_=0,
        )
        month, _ = utc_month(now)
        workspace_month = int(
            self.db.scalar(
                select(func.coalesce(func.sum(guarded), 0)).where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    ChatOpenAIProviderCall.month_start == month,
                )
            )
            or 0
        )
        if workspace_month + reserved > usd_to_microusd(
            self.settings.chat_openai_workspace_monthly_budget_usd
        ):
            raise OpenAIBudgetExhausted(
                "Direct OpenAI workspace monthly budget exhausted"
            )
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily = int(
            self.db.scalar(
                select(func.coalesce(func.sum(guarded), 0)).where(
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    ChatOpenAIProviderCall.reserved_at >= day_start,
                )
            )
            or 0
        )
        if daily + reserved > usd_to_microusd(
            self.settings.chat_openai_daily_budget_usd
        ):
            raise OpenAIBudgetExhausted("Direct OpenAI daily budget exhausted")

    def reserve_call(
        self,
        *,
        owner_id: str,
        turn_id: uuid.UUID,
        call_id: uuid.UUID,
        call_sequence: int,
        public_model_id: str,
        provider_model: str,
        reasoning_effort: str,
        bounds: OpenAIRequestBounds,
        qualification_scope_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ):
        current = (now or datetime.now(UTC)).astimezone(UTC)
        existing = self.db.get(ChatOpenAIProviderCall, call_id)
        if existing is not None:
            if (
                existing.owner_id,
                existing.turn_id,
                existing.call_sequence,
                existing.public_model_id,
                existing.provider_model,
            ) != (owner_id, turn_id, call_sequence, public_model_id, provider_model):
                raise OpenAIAccountingInvariantError(
                    "OpenAI call id reused with different identity"
                )
            return existing
        reserved = safe_maximum_microusd(self.settings, bounds, now=current)
        self._enforce_limits(
            owner_id,
            turn_id,
            qualification_scope_id,
            reserved,
            current,
        )
        month, _ = utc_month(current)
        usage = self._ensure_usage(owner_id, month)
        if (
            usage.spent_microusd + usage.reserved_microusd + reserved
            > usage.limit_microusd
        ):
            raise OpenAIBudgetExhausted("Direct OpenAI user monthly budget exhausted")
        row = ChatOpenAIProviderCall(
            id=call_id,
            turn_id=turn_id,
            call_sequence=call_sequence,
            owner_id=owner_id,
            environment=self.settings.environment,
            month_start=month,
            public_model_id=public_model_id,
            provider_model=provider_model,
            reasoning_effort=reasoning_effort,
            service_tier="default",
            request_bytes=bounds.request_bytes,
            state="reserved",
            reserved_microusd=reserved,
            reserved_at=current,
            updated_at=current,
        )
        self.db.add(row)
        usage.reserved_microusd += reserved
        usage.updated_at = current
        self.db.flush()
        return row

    def _locked_call(self, call_id: uuid.UUID):
        row = self.db.execute(
            select(ChatOpenAIProviderCall)
            .where(ChatOpenAIProviderCall.id == call_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise OpenAIAccountingInvariantError("OpenAI call row is missing")
        return row

    def mark_dispatched(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        row = self._locked_call(call_id)
        if row.state in {"dispatched", "settled", "cost_unknown"}:
            return
        if row.state != "reserved":
            raise OpenAIAccountingInvariantError("Released OpenAI call cannot dispatch")
        row.state = "dispatched"
        row.dispatched_at = (now or datetime.now(UTC)).astimezone(UTC)
        row.updated_at = row.dispatched_at
        self.db.flush()

    def settle_call(
        self,
        call_id: uuid.UUID,
        usage_result: ExtractedOpenAIUsage,
        *,
        provider_request_id: str | None = None,
        latency_ms: int | None = None,
        ttft_ms: int | None = None,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> None:
        actual = actual_usage_microusd(self.settings, usage_result)
        if actual is None:
            self.mark_cost_unknown(
                call_id,
                response_id=usage_result.response_id,
                provider_request_id=provider_request_id,
                error_code=error_code,
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                now=now,
            )
            return
        row = self._locked_call(call_id)
        if row.state == "settled":
            if row.actual_microusd != actual:
                raise OpenAIAccountingInvariantError(
                    "OpenAI call settled with conflicting cost"
                )
            return
        if row.state not in {"dispatched", "cost_unknown"}:
            raise OpenAIAccountingInvariantError("Only dispatched OpenAI calls settle")
        aggregate = self._usage(row.owner_id, row.month_start, lock=True)
        if aggregate is None:
            raise OpenAIAccountingInvariantError("OpenAI monthly usage row is missing")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        aggregate.reserved_microusd -= row.reserved_microusd
        aggregate.spent_microusd += actual
        if row.state == "cost_unknown":
            aggregate.unknown_cost_calls -= 1
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "response_id",
            "service_tier",
            "outcome",
        ):
            setattr(row, key, getattr(usage_result, key))
        row.provider_request_id = provider_request_id
        row.provider_latency_ms = latency_ms
        row.provider_ttft_ms = ttft_ms
        row.error_code = error_code
        row.settlement_source = (
            "recovered_provider_usage"
            if row.state == "cost_unknown"
            else "provider_usage"
        )
        row.actual_microusd = actual
        row.state = "settled"
        row.settled_at = current
        row.updated_at = current
        aggregate.updated_at = current
        self.db.flush()

    def mark_cost_unknown(
        self,
        call_id: uuid.UUID,
        *,
        response_id: str | None = None,
        provider_request_id: str | None = None,
        error_code: str | None = None,
        latency_ms: int | None = None,
        ttft_ms: int | None = None,
        now: datetime | None = None,
    ) -> None:
        row = self._locked_call(call_id)
        if row.state == "settled":
            return
        aggregate = self._usage(row.owner_id, row.month_start, lock=True)
        if aggregate is None:
            raise OpenAIAccountingInvariantError("OpenAI monthly usage row is missing")
        if row.state == "dispatched":
            aggregate.unknown_cost_calls += 1
        elif row.state != "cost_unknown":
            raise OpenAIAccountingInvariantError(
                "Only dispatched OpenAI calls become unknown"
            )
        row.state = "cost_unknown"
        row.response_id = response_id or row.response_id
        row.provider_request_id = provider_request_id or row.provider_request_id
        row.error_code = error_code
        row.provider_latency_ms = latency_ms
        row.provider_ttft_ms = ttft_ms
        row.updated_at = (now or datetime.now(UTC)).astimezone(UTC)
        aggregate.updated_at = row.updated_at
        self.db.flush()

    def release_call(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        row = self._locked_call(call_id)
        if row.state == "released":
            return
        if row.state != "reserved":
            raise OpenAIAccountingInvariantError(
                "Dispatched OpenAI reservation cannot release"
            )
        aggregate = self._usage(row.owner_id, row.month_start, lock=True)
        aggregate.reserved_microusd -= row.reserved_microusd
        row.state = "released"
        row.released_at = (now or datetime.now(UTC)).astimezone(UTC)
        row.updated_at = row.released_at
        aggregate.updated_at = row.released_at
        self.db.flush()

    def unknown_calls(self, *, batch_size: int = 100):
        return list(
            self.db.scalars(
                select(ChatOpenAIProviderCall)
                .where(ChatOpenAIProviderCall.state == "cost_unknown")
                .order_by(ChatOpenAIProviderCall.updated_at)
                .limit(batch_size)
            )
        )

    def mark_stale_dispatched_unknown(
        self, *, now: datetime | None = None, batch_size: int = 100
    ) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        stale_before = current - timedelta(
            minutes=self.settings.chat_openai_reconciliation_stale_minutes
        )
        terminal_turn = (
            select(ChatTurnJob.turn_id)
            .where(
                ChatTurnJob.turn_id == ChatOpenAIProviderCall.turn_id,
                ChatTurnJob.state.in_(("completed", "failed", "interrupted")),
                # Allow in-flight provider settlement to finish before recovery.
                ChatTurnJob.terminal_at < current - timedelta(minutes=1),
            )
            .exists()
        )
        rows = list(
            self.db.scalars(
                select(ChatOpenAIProviderCall)
                .where(
                    ChatOpenAIProviderCall.state == "dispatched",
                    ChatOpenAIProviderCall.environment == self.settings.environment,
                    or_(
                        ChatOpenAIProviderCall.updated_at < stale_before, terminal_turn
                    ),
                )
                .order_by(ChatOpenAIProviderCall.updated_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            aggregate = self._usage(row.owner_id, row.month_start, lock=True)
            if aggregate is None:
                raise OpenAIAccountingInvariantError(
                    "OpenAI monthly usage row is missing"
                )
            row.state = "cost_unknown"
            row.outcome = row.outcome or "interrupted"
            row.error_code = row.error_code or "openai_unavailable"
            row.updated_at = current
            aggregate.unknown_cost_calls += 1
            aggregate.updated_at = current
        self.db.flush()
        return len(rows)

    def settle_stale_unknown_at_reserved_ceiling(
        self, *, now: datetime | None = None, batch_size: int = 100
    ) -> int:
        """Close irrecoverable store:false calls without pretending exact usage."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        stale_before = current - timedelta(
            minutes=self.settings.chat_openai_reconciliation_stale_minutes
        )
        rows = list(
            self.db.scalars(
                select(ChatOpenAIProviderCall)
                .where(
                    ChatOpenAIProviderCall.state == "cost_unknown",
                    ChatOpenAIProviderCall.updated_at < stale_before,
                )
                .order_by(ChatOpenAIProviderCall.updated_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            aggregate = self._usage(row.owner_id, row.month_start, lock=True)
            if aggregate is None:
                raise OpenAIAccountingInvariantError(
                    "OpenAI monthly usage row is missing"
                )
            aggregate.reserved_microusd -= row.reserved_microusd
            aggregate.spent_microusd += row.reserved_microusd
            aggregate.unknown_cost_calls -= 1
            aggregate.updated_at = current
            row.actual_microusd = row.reserved_microusd
            row.state = "settled"
            row.settlement_source = "reserved_ceiling"
            row.outcome = "reconciled_reserved_ceiling"
            row.settled_at = current
            row.updated_at = current
        self.db.flush()
        return len(rows)

    def reconcile_call(
        self,
        call_id: uuid.UUID,
        usage: ExtractedOpenAIUsage,
        *,
        provider_request_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Apply asynchronously recovered trusted usage to an unknown call."""

        row = self._locked_call(call_id)
        if row.state == "settled":
            self.settle_call(call_id, usage, now=now)
            return
        if row.state != "cost_unknown":
            raise OpenAIAccountingInvariantError(
                "Only unknown OpenAI calls can be reconciled"
            )
        if (
            row.response_id
            and usage.response_id
            and row.response_id != usage.response_id
        ):
            raise OpenAIAccountingInvariantError(
                "Recovered OpenAI usage has a conflicting response id"
            )
        self.settle_call(
            call_id,
            usage,
            provider_request_id=provider_request_id or row.provider_request_id,
            now=now,
        )
