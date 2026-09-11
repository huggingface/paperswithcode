"""Aggregate autonomous daily reporting and cumulative budget enforcement."""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousAction,
    AutonomousExecutionIntent,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
    PendingPaperEdit,
)
from backend.services.autonomous_capabilities import HUMAN_ONLY_EDIT_TYPES
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)


_DIGEST_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MONEY = re.compile(r"^\d+\.\d{9}$")


def _utc_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def render_daily_digest(digest: Mapping[str, object]) -> str:
    """Render only the bounded aggregate schema accepted by mobile delivery."""

    try:
        day_value = str(digest["day"])
        if date.fromisoformat(day_value).isoformat() != day_value:
            raise ValueError
        runs = digest["runs_by_status"]
        actions = digest["actions_by_reason"]
        disabled = digest["disabled_operators"]
        cost = digest["cost_usd"]
        numbers = {
            key: digest[key]
            for key in (
                "repairs",
                "deployments",
                "rollbacks",
                "input_tokens",
                "output_tokens",
                "pending_human_only",
            )
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError("Autonomous digest aggregates are invalid") from None
    if (
        not isinstance(runs, dict)
        or not isinstance(actions, dict)
        or any(
            not isinstance(key, str)
            or _DIGEST_CODE.fullmatch(key) is None
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for values in (runs, actions)
            for key, value in values.items()
        )
        or not isinstance(disabled, list)
        or disabled != sorted(set(disabled))
        or any(
            value not in {operator.value for operator in Operator} for value in disabled
        )
        or not isinstance(cost, str)
        or _MONEY.fullmatch(cost) is None
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in numbers.values()
        )
        or not isinstance(digest.get("manual_mode"), bool)
        or not isinstance(digest.get("lease_active"), bool)
    ):
        raise ValueError("Autonomous digest aggregates are invalid")
    return (
        f"PwC autonomy digest {day_value} UTC — "
        f"runs={sum(runs.values())}, actions={sum(actions.values())}, "
        f"health={','.join(f'{key}:{runs[key]}' for key in sorted(runs)) or 'none'}, "
        f"decisions={','.join(f'{key}:{actions[key]}' for key in sorted(actions)) or 'none'}, "
        f"repairs={numbers['repairs']}, deployments={numbers['deployments']}, "
        f"rollbacks={numbers['rollbacks']}, cost=${cost}, "
        f"tokens={numbers['input_tokens'] + numbers['output_tokens']}, "
        f"human-only pending={numbers['pending_human_only']}, "
        f"manual={'on' if digest['manual_mode'] else 'off'}, "
        f"disabled={','.join(disabled) if disabled else 'none'}, "
        f"lease={'active' if digest['lease_active'] else 'none'}"
    )


class AutonomousDigestService:
    def __init__(
        self,
        *,
        pending_human_counter: Callable[[Session], int] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.pending_human_counter = pending_human_counter or self._pending_human_only
        self.now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _pending_human_only(db: Session) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(PendingPaperEdit)
                .where(
                    PendingPaperEdit.status == "pending",
                    PendingPaperEdit.edit_type.in_(HUMAN_ONLY_EDIT_TYPES),
                )
            )
            or 0
        )

    def build_daily_digest(self, db: Session, day: date) -> dict[str, object]:
        if not isinstance(day, date):
            raise TypeError("Autonomous digest day is invalid")
        start, end = _utc_bounds(day)
        runs = list(
            db.scalars(
                select(AutonomousRun)
                .where(
                    AutonomousRun.created_at >= start,
                    AutonomousRun.created_at < end,
                )
                .order_by(AutonomousRun.created_at, AutonomousRun.id)
            )
        )
        actions = list(
            db.scalars(
                select(AutonomousAction)
                .where(
                    AutonomousAction.created_at >= start,
                    AutonomousAction.created_at < end,
                )
                .order_by(AutonomousAction.created_at, AutonomousAction.id)
            )
        )
        states = list(
            db.scalars(
                select(AutonomousOperatorState).order_by(
                    AutonomousOperatorState.operator
                )
            )
        )
        lease = db.get(AutonomousRepairLease, "source_repair")
        runs_by_status = dict(sorted(Counter(row.status for row in runs).items()))
        actions_by_reason = dict(
            sorted(Counter(row.reason_code for row in actions).items())
        )
        total_cost = sum((Decimal(row.cost_usd) for row in runs), Decimal("0"))
        input_tokens = sum(row.input_tokens for row in runs)
        output_tokens = sum(row.output_tokens for row in runs)
        disabled = sorted(
            row.operator
            for row in states
            if row.operator != "global" and not row.enabled
        )
        manual_mode = next(
            (row.manual_mode for row in states if row.operator == "global"), False
        )
        repairs = sum(
            reason in {"source_repaired", "repair_started", "review_approved"}
            for reason in (row.reason_code for row in actions)
        )
        deployments = sum(
            reason in {"deployed", "source_repaired", "deploy_succeeded"}
            for reason in (row.reason_code for row in actions)
        )
        rollbacks = sum("rollback" in row.reason_code for row in actions)
        pending_human_only = self.pending_human_counter(db)
        observed_at = self.now()
        if observed_at.tzinfo is None:
            raise ValueError("Autonomous digest clock must be timezone-aware")
        lease_active = bool(
            lease is not None
            and (
                lease.expires_at.replace(tzinfo=UTC)
                if lease.expires_at.tzinfo is None
                else lease.expires_at
            )
            > observed_at
        )
        digest: dict[str, object] = {
            "day": day.isoformat(),
            "runs_by_status": runs_by_status,
            "actions_by_reason": actions_by_reason,
            "repairs": repairs,
            "deployments": deployments,
            "rollbacks": rollbacks,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": f"{total_cost.quantize(Decimal('0.000000001')):.9f}",
            "pending_human_only": pending_human_only,
            "manual_mode": manual_mode,
            "disabled_operators": disabled,
            "lease_active": lease_active,
        }
        digest["text"] = render_daily_digest(digest)
        return digest


def build_daily_digest(db: Session, day: date) -> dict[str, object]:
    return AutonomousDigestService().build_daily_digest(db, day)


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    per_run_cost_usd: Decimal
    per_run_tokens: int
    daily_cost_usd: Decimal
    daily_tokens: int
    monthly_cost_usd: Decimal
    monthly_tokens: int

    def __post_init__(self) -> None:
        costs = (
            self.per_run_cost_usd,
            self.daily_cost_usd,
            self.monthly_cost_usd,
        )
        tokens = (self.per_run_tokens, self.daily_tokens, self.monthly_tokens)
        if (
            any(
                not isinstance(value, Decimal) or not value.is_finite() or value <= 0
                for value in costs
            )
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in tokens
            )
            or self.per_run_cost_usd > self.daily_cost_usd
            or self.daily_cost_usd > self.monthly_cost_usd
            or self.per_run_tokens > self.daily_tokens
            or self.daily_tokens > self.monthly_tokens
        ):
            raise ValueError("Autonomous cumulative budget limits are invalid")

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "BudgetLimits":
        values = dict(os.environ if environ is None else environ)
        try:
            return cls(
                Decimal(values.get("PWC_AUTONOMOUS_PER_RUN_COST_USD", "10")),
                int(values.get("PWC_AUTONOMOUS_PER_RUN_TOKENS", "200000")),
                Decimal(values.get("PWC_AUTONOMOUS_DAILY_COST_USD", "25")),
                int(values.get("PWC_AUTONOMOUS_DAILY_TOKENS", "1000000")),
                Decimal(values.get("PWC_AUTONOMOUS_MONTHLY_COST_USD", "250")),
                int(values.get("PWC_AUTONOMOUS_MONTHLY_TOKENS", "10000000")),
            )
        except (InvalidOperation, ValueError):
            raise ValueError(
                "Autonomous cumulative budget environment is invalid"
            ) from None


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    reason_code: str
    transitioned: bool
    daily_cost_usd: Decimal
    monthly_cost_usd: Decimal
    daily_tokens: int
    monthly_tokens: int


class AutonomousBudgetService:
    def __init__(
        self,
        *,
        limits: BudgetLimits | None = None,
        repository: AutonomousOperationsRepository | None = None,
        now: Callable[[], datetime] | None = None,
        on_exhausted: Callable[[Session, Operator, str, datetime], None] | None = None,
    ) -> None:
        self.limits = limits or BudgetLimits.from_environ()
        self.repository = repository or AutonomousOperationsRepository()
        self.now = now or (lambda: datetime.now(UTC))
        self.on_exhausted = on_exhausted

    @staticmethod
    def _usage(
        db: Session,
        start: datetime,
        end: datetime,
        *,
        pending_token_reservation: int,
    ) -> tuple[Decimal, int]:
        cost, input_tokens, output_tokens = db.execute(
            select(
                func.coalesce(func.sum(AutonomousRun.cost_usd), 0),
                func.coalesce(func.sum(AutonomousRun.input_tokens), 0),
                func.coalesce(func.sum(AutonomousRun.output_tokens), 0),
            ).where(
                AutonomousRun.created_at >= start,
                AutonomousRun.created_at < end,
            )
        ).one()
        pending_cost, pending_count = db.execute(
            select(
                func.coalesce(func.sum(AutonomousExecutionIntent.budget_usd), 0),
                func.count(AutonomousExecutionIntent.run_id),
            )
            .outerjoin(
                AutonomousRun,
                AutonomousRun.id == AutonomousExecutionIntent.run_id,
            )
            .where(
                AutonomousRun.id.is_(None),
            )
        ).one()
        return (
            Decimal(str(cost)) + Decimal(str(pending_cost)),
            int(input_tokens)
            + int(output_tokens)
            + int(pending_count) * pending_token_reservation,
        )

    def enforce_before_run(
        self,
        db: Session,
        *,
        operator: Operator,
        requested_cost_usd: Decimal,
        requested_tokens: int,
    ) -> BudgetDecision:
        now = self.now()
        if (
            now.tzinfo is None
            or not isinstance(operator, Operator)
            or not isinstance(requested_cost_usd, Decimal)
            or not requested_cost_usd.is_finite()
            or requested_cost_usd <= 0
            or isinstance(requested_tokens, bool)
            or not isinstance(requested_tokens, int)
            or requested_tokens <= 0
        ):
            raise ValueError("Autonomous budget request is invalid")
        day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        horizon = now + timedelta(microseconds=1)
        self.repository.lock_cumulative_budget(db)
        daily_cost, daily_tokens = self._usage(
            db,
            day_start,
            horizon,
            pending_token_reservation=self.limits.per_run_tokens,
        )
        monthly_cost, monthly_tokens = self._usage(
            db,
            month_start,
            horizon,
            pending_token_reservation=self.limits.per_run_tokens,
        )
        checks = (
            (requested_cost_usd > self.limits.per_run_cost_usd, "per_run_cost_limit"),
            (requested_tokens > self.limits.per_run_tokens, "per_run_token_limit"),
            (
                daily_cost + requested_cost_usd > self.limits.daily_cost_usd,
                "daily_cost_limit",
            ),
            (
                daily_tokens + requested_tokens > self.limits.daily_tokens,
                "daily_token_limit",
            ),
            (
                monthly_cost + requested_cost_usd > self.limits.monthly_cost_usd,
                "monthly_cost_limit",
            ),
            (
                monthly_tokens + requested_tokens > self.limits.monthly_tokens,
                "monthly_token_limit",
            ),
        )
        reason = next((code for exceeded, code in checks if exceeded), "within_budget")
        transitioned = False
        if reason != "within_budget":
            control = self.repository.get_control_state(db)
            if control.enabled[operator]:
                self.repository.set_operator_enabled(
                    db,
                    operator=operator,
                    enabled=False,
                    expected_revision=control.revision,
                    actor="system:budget",
                    now=now,
                )
                db.commit()
                transitioned = True
            if self.on_exhausted is not None:
                self.on_exhausted(db, operator, reason, now)
        return BudgetDecision(
            reason == "within_budget",
            reason,
            transitioned,
            daily_cost,
            monthly_cost,
            daily_tokens,
            monthly_tokens,
        )
