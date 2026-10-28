"""Durable per-HF-user accounting for server-funded OpenRouter calls."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any

import httpx
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
from backend.config import Settings
from backend.chat_execution_policy import MAX_PROVIDER_REQUEST_BYTES
from backend.models.database import (
    ChatOpenRouterCredentialAudit,
    ChatOpenRouterMonthlyUsage,
    ChatOpenRouterProviderCall,
)

logger = logging.getLogger(__name__)
MICROUSD_PER_USD = Decimal("1000000")
MAX_REQUEST_BYTES = MAX_PROVIDER_REQUEST_BYTES
MAX_OUTPUT_TOKENS = PROVIDER_OUTPUT_TOKEN_LIMIT
PUBLIC_SUPPORT_URL = "https://github.com/huggingface/paperswithcode-feedback"


class OpenRouterUserBudgetError(RuntimeError):
    """Base class for fail-closed per-user accounting errors."""


class OpenRouterMonthlyBudgetExhausted(OpenRouterUserBudgetError):
    def __init__(self, resets_at: datetime):
        super().__init__(
            "The remaining monthly OpenRouter allowance cannot fund this call"
        )
        self.resets_at = resets_at


class OpenRouterAbuseLimitExceeded(OpenRouterUserBudgetError):
    def __init__(self, scope: str, retry_at: datetime):
        super().__init__("The shared OpenRouter abuse circuit rejected this call")
        self.scope = scope
        self.retry_at = retry_at


class OpenRouterPricingUnavailable(OpenRouterUserBudgetError):
    pass


class OpenRouterAccountingInvariantError(OpenRouterUserBudgetError):
    pass


@dataclass(frozen=True)
class OpenRouterUsageStatus:
    used_percent: int
    remaining_percent: int
    resets_at: datetime
    available: bool
    as_of: datetime

    def public_dict(self) -> dict[str, object]:
        return {
            "used_percent": self.used_percent,
            "remaining_percent": self.remaining_percent,
            "resets_at": self.resets_at,
            "available": self.available,
            "as_of": self.as_of,
        }


@dataclass(frozen=True)
class RequestBounds:
    request_bytes: int
    maximum_output_tokens: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReservedCall:
    call_id: uuid.UUID
    reserved_microusd: int
    month_start: date
    idempotent_replay: bool = False


def utc_month(now: datetime) -> tuple[date, datetime]:
    current = now.astimezone(UTC)
    start = date(current.year, current.month, 1)
    if current.month == 12:
        reset = datetime(current.year + 1, 1, 1, tzinfo=UTC)
    else:
        reset = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    return start, reset


def _months_before(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 - months
    return date(absolute // 12, absolute % 12 + 1, 1)


def usd_to_microusd(value: Decimal | str | int | float) -> int:
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    return int((decimal * MICROUSD_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def _contains_unsupported_modality(value: object) -> bool:
    if isinstance(value, list):
        return any(_contains_unsupported_modality(item) for item in value)
    if not isinstance(value, dict):
        return False
    block_type = value.get("type")
    if isinstance(block_type, str) and block_type in {
        "image",
        "image_url",
        "input_audio",
        "audio",
        "document",
        "file",
    }:
        return True
    return any(_contains_unsupported_modality(item) for item in value.values())


def safe_maximum_microusd(
    settings: Settings,
    model_route: str,
    bounds: RequestBounds,
    *,
    now: datetime | None = None,
) -> int:
    """Return a strict configured price bound or fail closed.

    UTF-8 bytes are a conservative upper bound on input token count. Cached
    input is deliberately charged at the full input rate. Output reasoning is
    inside the provider's bounded ``max_tokens`` value. Non-text modalities
    fail closed because they can carry separate provider fees.
    """

    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        verified = date.fromisoformat(settings.chat_openrouter_pricing_verified_at)
    except ValueError as error:
        raise OpenRouterPricingUnavailable(
            "OpenRouter pricing date is invalid"
        ) from error
    if current.date() - verified > timedelta(
        days=settings.chat_openrouter_pricing_max_age_days
    ):
        raise OpenRouterPricingUnavailable("OpenRouter pricing is stale")
    if model_route not in settings.chat_openrouter_routes:
        raise OpenRouterPricingUnavailable("OpenRouter model pricing is not pinned")
    if not 1 <= bounds.request_bytes <= MAX_REQUEST_BYTES:
        raise OpenRouterPricingUnavailable("OpenRouter request size is unbounded")
    if not 1 <= bounds.maximum_output_tokens <= MAX_OUTPUT_TOKENS:
        raise OpenRouterPricingUnavailable("OpenRouter output is unbounded")
    if _contains_unsupported_modality(bounds.payload):
        raise OpenRouterPricingUnavailable("OpenRouter request modality is unsupported")
    return (
        bounds.request_bytes * settings.chat_openrouter_input_microusd_per_token
        + bounds.maximum_output_tokens
        * settings.chat_openrouter_output_microusd_per_token
        + settings.chat_openrouter_request_fee_microusd
    )


def minimum_fundable_call_microusd(settings: Settings) -> int:
    # The agent requests the normal output ceiling. We do not silently reduce
    # quality settings to fit a small remainder.
    return (
        settings.chat_openrouter_request_fee_microusd
        + MAX_OUTPUT_TOKENS * settings.chat_openrouter_output_microusd_per_token
        + settings.chat_openrouter_input_microusd_per_token
    )


def opaque_owner(owner_id: str, settings: Settings) -> str:
    secret = settings.chat_openrouter_user_tracking_secret.encode()
    if not secret:
        secret = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return hmac.new(secret, owner_id.encode(), hashlib.sha256).hexdigest()


class OpenRouterUserBudgetService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    @property
    def limit_microusd(self) -> int:
        return usd_to_microusd(self.settings.chat_openrouter_monthly_user_budget_usd)

    def limit_microusd_for(self, owner_id: str) -> int:
        if (
            self.settings.environment == "staging"
            and owner_id in self.settings.admin_hf_subject_set
        ):
            return usd_to_microusd(Decimal("5.00"))
        return self.limit_microusd

    def _usage(self, owner_id: str, month_start: date, *, lock: bool = False):
        query = select(ChatOpenRouterMonthlyUsage).where(
            ChatOpenRouterMonthlyUsage.hf_user_id == owner_id,
            ChatOpenRouterMonthlyUsage.month_start == month_start,
        )
        if lock:
            query = query.with_for_update()
        return self.db.execute(query).scalar_one_or_none()

    def _ensure_usage(self, owner_id: str, month_start: date):
        statement = (
            pg_insert(ChatOpenRouterMonthlyUsage)
            .values(
                hf_user_id=owner_id,
                month_start=month_start,
                limit_microusd=self.limit_microusd_for(owner_id),
                reserved_microusd=0,
                spent_microusd=0,
                unknown_cost_calls=0,
            )
            .on_conflict_do_nothing(index_elements=["hf_user_id", "month_start"])
        )
        self.db.execute(statement)
        usage = self._usage(owner_id, month_start, lock=True)
        if usage is None:
            raise OpenRouterAccountingInvariantError(
                "Monthly usage row was not created"
            )
        return usage

    def _qualification_bypasses_abuse_circuit(self, owner_id: str) -> bool:
        return self.settings.environment == "staging" and owner_id.startswith(
            "operator:pi-qualification:"
        )

    def _enforce_abuse_circuit(
        self,
        owner_id: str,
        reserved_microusd: int,
        now: datetime,
    ) -> None:
        if self._qualification_bypasses_abuse_circuit(owner_id):
            return

        # Serialize the global check with insertion across users and workers.
        # The monthly usage row separately serializes each user's reservations.
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended("chat-openrouter-abuse-circuit", 0)
                )
            )
        )
        cutoff = now - timedelta(
            seconds=self.settings.chat_openrouter_rate_limit_window_seconds
        )
        active_call = ChatOpenRouterProviderCall.state != "released"
        external_call = active_call
        if self.settings.environment == "staging":
            external_call = (
                active_call
                & ~ChatOpenRouterProviderCall.hf_user_id.startswith(
                    "operator:pi-qualification:"
                )
            )

        user_calls = int(
            self.db.scalar(
                select(func.count())
                .select_from(ChatOpenRouterProviderCall)
                .where(
                    ChatOpenRouterProviderCall.hf_user_id == owner_id,
                    ChatOpenRouterProviderCall.reserved_at >= cutoff,
                    active_call,
                )
            )
            or 0
        )
        retry_at = now + timedelta(
            seconds=self.settings.chat_openrouter_rate_limit_window_seconds
        )
        if user_calls >= self.settings.chat_openrouter_user_rate_limit_calls:
            raise OpenRouterAbuseLimitExceeded("user_rate", retry_at)

        global_calls = int(
            self.db.scalar(
                select(func.count())
                .select_from(ChatOpenRouterProviderCall)
                .where(
                    ChatOpenRouterProviderCall.reserved_at >= cutoff,
                    external_call,
                )
            )
            or 0
        )
        if global_calls >= self.settings.chat_openrouter_global_rate_limit_calls:
            raise OpenRouterAbuseLimitExceeded("global_rate", retry_at)

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        guarded_cost = case(
            (
                ChatOpenRouterProviderCall.state.in_(
                    {"reserved", "dispatched", "cost_unknown"}
                ),
                ChatOpenRouterProviderCall.reserved_microusd,
            ),
            (
                ChatOpenRouterProviderCall.state == "settled",
                func.coalesce(
                    ChatOpenRouterProviderCall.actual_microusd,
                    ChatOpenRouterProviderCall.reserved_microusd,
                ),
            ),
            else_=0,
        )
        guarded_daily_spend = int(
            self.db.scalar(
                select(func.coalesce(func.sum(guarded_cost), 0)).where(
                    ChatOpenRouterProviderCall.reserved_at >= day_start,
                    external_call,
                )
            )
            or 0
        )
        daily_limit = usd_to_microusd(self.settings.chat_openrouter_daily_budget_usd)
        if guarded_daily_spend + reserved_microusd > daily_limit:
            raise OpenRouterAbuseLimitExceeded(
                "global_daily_budget", day_start + timedelta(days=1)
            )

    def status_percentage(
        self, owner_id: str, now: datetime | None = None
    ) -> OpenRouterUsageStatus:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        month_start, reset = utc_month(current)
        row = self._usage(owner_id, month_start)
        if row is None:
            consumed = 0
            active_reserved = 0
            authoritative_remaining = self.limit_microusd_for(owner_id)
        else:
            unknown_reserved = int(
                self.db.scalar(
                    select(
                        func.coalesce(
                            func.sum(ChatOpenRouterProviderCall.reserved_microusd), 0
                        )
                    ).where(
                        ChatOpenRouterProviderCall.hf_user_id == owner_id,
                        ChatOpenRouterProviderCall.month_start == month_start,
                        ChatOpenRouterProviderCall.state == "cost_unknown",
                    )
                )
                or 0
            )
            consumed = min(row.limit_microusd, row.spent_microusd + unknown_reserved)
            active_reserved = max(0, row.reserved_microusd - unknown_reserved)
            authoritative_remaining = max(
                0, row.limit_microusd - row.spent_microusd - row.reserved_microusd
            )
        limit_value = (
            row.limit_microusd if row is not None else self.limit_microusd_for(owner_id)
        )
        remaining = max(0, limit_value - consumed)
        effectively_depleted = (
            active_reserved == 0
            and authoritative_remaining < minimum_fundable_call_microusd(self.settings)
        )
        remaining_percent = (
            0
            if effectively_depleted
            else max(0, min(100, remaining * 100 // limit_value))
        )
        return OpenRouterUsageStatus(
            used_percent=100 - remaining_percent,
            remaining_percent=remaining_percent,
            resets_at=reset,
            available=(
                self.settings.chat_openrouter_server_funded_enabled
                and remaining_percent > 0
            ),
            as_of=current,
        )

    def can_fund_call(self, owner_id: str, now: datetime | None = None) -> bool:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        month_start, _ = utc_month(current)
        row = self._usage(owner_id, month_start)
        available = (
            self.limit_microusd_for(owner_id)
            if row is None
            else max(0, row.limit_microusd - row.spent_microusd - row.reserved_microusd)
        )
        return available >= minimum_fundable_call_microusd(self.settings)

    def reserve_call(
        self,
        owner_id: str,
        turn_id: uuid.UUID,
        call_id: uuid.UUID,
        call_sequence: int,
        model_route: str,
        request_bounds: RequestBounds,
        now: datetime | None = None,
        *,
        reasoning_effort: str = "high",
    ) -> ReservedCall:
        if reasoning_effort not in {"low", "medium", "high", "max"}:
            raise OpenRouterAccountingInvariantError(
                "Provider-call reasoning effort is invalid"
            )
        current = (now or datetime.now(UTC)).astimezone(UTC)
        month_start, reset = utc_month(current)
        reserved = safe_maximum_microusd(
            self.settings, model_route, request_bounds, now=current
        )
        existing = self.db.get(ChatOpenRouterProviderCall, call_id)
        if existing is not None:
            identity = (
                existing.hf_user_id,
                existing.turn_id,
                existing.call_sequence,
                existing.model_route,
                existing.reasoning_effort,
            )
            expected = (
                owner_id,
                turn_id,
                call_sequence,
                model_route,
                reasoning_effort,
            )
            if identity != expected:
                raise OpenRouterAccountingInvariantError(
                    "Provider-call id was reused with different ownership"
                )
            return ReservedCall(
                call_id=call_id,
                reserved_microusd=existing.reserved_microusd,
                month_start=existing.month_start,
                idempotent_replay=True,
            )
        self._enforce_abuse_circuit(owner_id, reserved, current)
        usage = self._ensure_usage(owner_id, month_start)
        if usage.limit_microusd != self.limit_microusd_for(owner_id):
            # A month's limit is an immutable snapshot. Config changes apply
            # only to newly created buckets.
            logger.info(
                "openrouter budget limit snapshot retained owner=%s month=%s",
                opaque_owner(owner_id, self.settings)[:16],
                month_start,
            )
        if (
            usage.spent_microusd + usage.reserved_microusd + reserved
            > usage.limit_microusd
        ):
            logger.info(
                "openrouter reservation denied owner=%s month=%s reason=user_budget",
                opaque_owner(owner_id, self.settings)[:16],
                month_start,
            )
            raise OpenRouterMonthlyBudgetExhausted(reset)
        row = ChatOpenRouterProviderCall(
            id=call_id,
            turn_id=turn_id,
            call_sequence=call_sequence,
            hf_user_id=owner_id,
            month_start=month_start,
            model_route=model_route,
            reasoning_effort=reasoning_effort,
            routing_policy=(
                self.settings.chat_openrouter_routing_policy
                if self.settings.chat_openrouter_routing_enabled
                else "throughput"
            ),
            request_bytes=request_bounds.request_bytes,
            system_token_bucket=self._payload_token_bucket(
                request_bounds.payload.get("system")
            ),
            tool_token_bucket=self._payload_token_bucket(
                request_bounds.payload.get("tools")
            ),
            conversation_token_bucket=self._payload_token_bucket(
                request_bounds.payload.get("messages")
            ),
            state="reserved",
            reserved_microusd=reserved,
            reserved_at=current,
            updated_at=current,
        )
        self.db.add(row)
        usage.reserved_microusd += reserved
        usage.updated_at = current
        self.db.flush()
        logger.info(
            "openrouter reservation owner=%s month=%s call=%s reserved_microusd=%s",
            opaque_owner(owner_id, self.settings)[:16],
            month_start,
            call_id,
            reserved,
        )
        return ReservedCall(call_id, reserved, month_start)

    @staticmethod
    def _payload_token_bucket(value: object) -> int:
        if value is None:
            return 0
        encoded = json.dumps(value, separators=(",", ":")).encode()
        estimate = max(1, len(encoded) // 4)
        # Coarse buckets avoid pretending byte heuristics are tokenizer-exact.
        return min(512_000, int(math.ceil(estimate / 128) * 128))

    def _locked_call(self, call_id: uuid.UUID):
        row = self.db.execute(
            select(ChatOpenRouterProviderCall)
            .where(ChatOpenRouterProviderCall.id == call_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise OpenRouterAccountingInvariantError("Provider-call row is missing")
        return row

    def mark_dispatched(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        row = self._locked_call(call_id)
        if row.state in {"dispatched", "settled", "cost_unknown"}:
            return
        if row.state != "reserved":
            raise OpenRouterAccountingInvariantError("Released call cannot dispatch")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        row.state = "dispatched"
        row.dispatched_at = current
        row.updated_at = current
        self.db.flush()
        logger.info(
            "openrouter dispatch owner=%s month=%s call=%s",
            opaque_owner(row.hf_user_id, self.settings)[:16],
            row.month_start,
            call_id,
        )

    def settle_call(
        self,
        call_id: uuid.UUID,
        actual_microusd: int,
        generation_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if actual_microusd < 0:
            raise ValueError("Provider cost must be non-negative")
        row = self._locked_call(call_id)
        if row.state == "settled":
            if row.actual_microusd != actual_microusd:
                raise OpenRouterAccountingInvariantError(
                    "Provider call was settled with conflicting cost"
                )
            return
        if row.state not in {"dispatched", "cost_unknown"}:
            raise OpenRouterAccountingInvariantError(
                "Only dispatched calls can be settled"
            )
        usage = self._usage(row.hf_user_id, row.month_start, lock=True)
        if usage is None:
            raise OpenRouterAccountingInvariantError("Monthly usage row is missing")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        usage.reserved_microusd -= row.reserved_microusd
        usage.spent_microusd += actual_microusd
        if row.state == "cost_unknown":
            usage.unknown_cost_calls -= 1
        usage.updated_at = current
        row.state = "settled"
        row.actual_microusd = actual_microusd
        row.generation_id = generation_id or row.generation_id
        row.settled_at = current
        row.updated_at = current
        if (
            actual_microusd > row.reserved_microusd
            or usage.spent_microusd > usage.limit_microusd
        ):
            logger.critical(
                "openrouter impossible accounting state owner=%s call=%s actual=%s reserved=%s",
                opaque_owner(row.hf_user_id, self.settings)[:16],
                call_id,
                actual_microusd,
                row.reserved_microusd,
            )
        self.db.flush()
        logger.info(
            "openrouter settlement owner=%s month=%s call=%s actual_microusd=%s",
            opaque_owner(row.hf_user_id, self.settings)[:16],
            row.month_start,
            call_id,
            actual_microusd,
        )

    def mark_cost_unknown(
        self,
        call_id: uuid.UUID,
        generation_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        row = self._locked_call(call_id)
        if row.state in {"cost_unknown", "settled"}:
            return
        if row.state != "dispatched":
            raise OpenRouterAccountingInvariantError(
                "Only dispatched calls can retain unknown cost"
            )
        usage = self._usage(row.hf_user_id, row.month_start, lock=True)
        if usage is None:
            raise OpenRouterAccountingInvariantError("Monthly usage row is missing")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        row.state = "cost_unknown"
        row.generation_id = generation_id or row.generation_id
        row.updated_at = current
        usage.unknown_cost_calls += 1
        usage.updated_at = current
        self.db.flush()
        logger.warning(
            "openrouter unknown cost owner=%s call=%s generation_present=%s",
            opaque_owner(row.hf_user_id, self.settings)[:16],
            call_id,
            bool(row.generation_id),
        )

    def release_call(self, call_id: uuid.UUID, now: datetime | None = None) -> None:
        row = self._locked_call(call_id)
        if row.state == "released":
            return
        if row.state != "reserved" or row.dispatched_at is not None:
            raise OpenRouterAccountingInvariantError(
                "A dispatched call reservation cannot be released"
            )
        usage = self._usage(row.hf_user_id, row.month_start, lock=True)
        if usage is None:
            raise OpenRouterAccountingInvariantError("Monthly usage row is missing")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        usage.reserved_microusd -= row.reserved_microusd
        usage.updated_at = current
        row.state = "released"
        row.released_at = current
        row.updated_at = current
        self.db.flush()
        logger.info(
            "openrouter release owner=%s month=%s call=%s",
            opaque_owner(row.hf_user_id, self.settings)[:16],
            row.month_start,
            call_id,
        )

    def accounting_health(self, now: datetime | None = None) -> dict[str, int]:
        """Return aggregate, content-free operational health counters."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        month_start, _ = utc_month(current)
        stale_before = current - timedelta(
            minutes=self.settings.chat_openrouter_reconciliation_stale_minutes
        )
        stale_reservations = int(
            self.db.scalar(
                select(func.count(ChatOpenRouterProviderCall.id)).where(
                    ChatOpenRouterProviderCall.state.in_(["reserved", "dispatched"]),
                    ChatOpenRouterProviderCall.updated_at < stale_before,
                )
            )
            or 0
        )
        old_unknown_costs = int(
            self.db.scalar(
                select(func.count(ChatOpenRouterProviderCall.id)).where(
                    ChatOpenRouterProviderCall.state == "cost_unknown",
                    ChatOpenRouterProviderCall.updated_at < stale_before,
                )
            )
            or 0
        )
        ledger_microusd = int(
            self.db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            ChatOpenRouterMonthlyUsage.spent_microusd
                            + ChatOpenRouterMonthlyUsage.reserved_microusd
                        ),
                        0,
                    )
                ).where(ChatOpenRouterMonthlyUsage.month_start == month_start)
            )
            or 0
        )
        calls = int(
            self.db.scalar(
                select(func.count(ChatOpenRouterProviderCall.id)).where(
                    ChatOpenRouterProviderCall.month_start == month_start
                )
            )
            or 0
        )
        return {
            "stale_reservations": stale_reservations,
            "old_unknown_costs": old_unknown_costs,
            "ledger_microusd": ledger_microusd,
            "provider_calls": calls,
        }

    def unknown_calls(self, batch_size: int = 100, cursor: uuid.UUID | None = None):
        query = select(ChatOpenRouterProviderCall).where(
            ChatOpenRouterProviderCall.state == "cost_unknown",
            ChatOpenRouterProviderCall.generation_id.is_not(None),
        )
        if cursor is not None:
            query = query.where(ChatOpenRouterProviderCall.id > cursor)
        return list(
            self.db.execute(
                query.order_by(ChatOpenRouterProviderCall.id).limit(
                    max(1, min(batch_size, 500))
                )
            ).scalars()
        )

    async def reconcile_unknown(
        self,
        batch_size: int = 100,
        cursor: uuid.UUID | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, object]:
        rows = self.unknown_calls(batch_size, cursor)
        owns_client = client is None
        active = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
        reconciled = 0
        try:
            for row in rows:
                response = await active.get(
                    "https://openrouter.ai/api/v1/generation",
                    params={"id": row.generation_id},
                    headers={
                        "Authorization": f"Bearer {self.settings.chat_openrouter_api_key}"
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "openrouter reconciliation deferred call=%s status=%s",
                        row.id,
                        response.status_code,
                    )
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    continue
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict):
                    continue
                cost = parse_provider_cost_microusd(
                    data.get("total_cost", data.get("usage"))
                )
                if cost is None:
                    continue
                self.settle_call(row.id, cost, row.generation_id)
                reconciled += 1
        finally:
            if owns_client:
                await active.aclose()
        from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
        from backend.services.chat_turn_admission import ChatTurnAdmissionService

        turn_reservations_reconciled = 0
        if self.settings.chat_executor_remote_transport_enabled:
            turn_reservations_reconciled = ChatTurnAdmissionService(
                environment=self.settings.environment,
                spend_limit_microusd=(
                    self.settings.chat_sandbox_application_cap_microusd
                ),
            ).reconcile_cost_unknown(
                self.db,
                cost_per_second_microusd=ChatSandboxSpendService(
                    self.db, self.settings
                ).cost_per_second(),
                now=datetime.now(UTC),
                batch_size=batch_size,
            )
        return {
            "reconciled": reconciled,
            "examined": len(rows),
            "cursor": str(rows[-1].id) if rows else None,
            "turn_reservations_reconciled": turn_reservations_reconciled,
        }

    def cleanup_retention(
        self, now: datetime | None = None, batch_size: int = 500
    ) -> dict[str, int]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        bounded = max(1, min(batch_size, 1000))
        call_ids = list(
            self.db.scalars(
                select(ChatOpenRouterProviderCall.id)
                .where(
                    ChatOpenRouterProviderCall.state.in_(["settled", "released"]),
                    ChatOpenRouterProviderCall.updated_at
                    < current
                    - timedelta(
                        days=self.settings.chat_openrouter_provider_call_retention_days
                    ),
                )
                .order_by(ChatOpenRouterProviderCall.updated_at)
                .limit(bounded)
            )
        )
        deleted_calls = 0
        if call_ids:
            deleted_calls = int(
                self.db.execute(
                    delete(ChatOpenRouterProviderCall).where(
                        ChatOpenRouterProviderCall.id.in_(call_ids)
                    )
                ).rowcount
                or 0
            )
        month_cutoff = _months_before(
            current.date().replace(day=1),
            self.settings.chat_openrouter_monthly_usage_retention_months,
        )
        usage_keys = list(
            self.db.execute(
                select(
                    ChatOpenRouterMonthlyUsage.hf_user_id,
                    ChatOpenRouterMonthlyUsage.month_start,
                )
                .where(
                    ChatOpenRouterMonthlyUsage.month_start < month_cutoff,
                    ChatOpenRouterMonthlyUsage.reserved_microusd == 0,
                    ChatOpenRouterMonthlyUsage.unknown_cost_calls == 0,
                    ~select(ChatOpenRouterProviderCall.id)
                    .where(
                        ChatOpenRouterProviderCall.hf_user_id
                        == ChatOpenRouterMonthlyUsage.hf_user_id,
                        ChatOpenRouterProviderCall.month_start
                        == ChatOpenRouterMonthlyUsage.month_start,
                    )
                    .exists(),
                )
                .limit(bounded)
            ).all()
        )
        deleted_usage = 0
        for owner_id, month_start in usage_keys:
            deleted_usage += int(
                self.db.execute(
                    delete(ChatOpenRouterMonthlyUsage).where(
                        ChatOpenRouterMonthlyUsage.hf_user_id == owner_id,
                        ChatOpenRouterMonthlyUsage.month_start == month_start,
                    )
                ).rowcount
                or 0
            )
        deleted_audit = int(
            self.db.execute(
                delete(ChatOpenRouterCredentialAudit).where(
                    ChatOpenRouterCredentialAudit.id.in_(
                        select(ChatOpenRouterCredentialAudit.id)
                        .where(
                            ChatOpenRouterCredentialAudit.created_at
                            < current
                            - timedelta(
                                days=self.settings.chat_openrouter_credential_audit_retention_days
                            )
                        )
                        .limit(bounded)
                    )
                )
            ).rowcount
            or 0
        )
        return {
            "provider_calls": deleted_calls,
            "monthly_usage": deleted_usage,
            "credential_audit": deleted_audit,
        }


def parse_provider_cost_microusd(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        cost = Decimal(str(value))
    except Exception:
        return None
    if not cost.is_finite() or cost < 0:
        return None
    return usd_to_microusd(cost)


def parse_json_payload(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Provider payload must be an object")
    return payload
