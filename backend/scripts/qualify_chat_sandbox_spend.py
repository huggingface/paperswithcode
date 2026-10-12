"""Exercise spend thresholds without creating or purchasing provider compute."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatTitleBudgetEvent,
    ChatTitleBudgetState,
)
from backend.scripts.monitor_chat_operational_alerts import deliver_pending, new_event
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
    cycle_end,
)
from backend.services.chat_title_budget_service import (
    ChatTitleBudgetService,
    deliver_title_budget_alerts,
)


async def deliver_all_spend_alerts(settings) -> int:
    """Drain the bounded dispatcher batches produced by one qualification."""

    delivered = 0
    manager = SandboxSessionManager(settings)
    for _ in range(3):
        batch = await manager.deliver_spend_alerts()
        delivered += batch
        if batch == 0:
            break
    return delivered


def confirmation_for(environment: str) -> str:
    return f"QUALIFY_{environment.upper()}_CHAT_SPEND"


def fallback_spend_event_statement(environment: str):
    """Select the warning transition deliberately routed to fallback."""

    return (
        select(ChatSandboxCircuitEvent)
        .join(
            ChatSandboxBudgetState,
            ChatSandboxBudgetState.id == ChatSandboxCircuitEvent.budget_state_id,
        )
        .where(
            ChatSandboxBudgetState.environment == environment,
            ChatSandboxCircuitEvent.event_type == "warning_entered",
        )
    )


def qualify_concurrent_reservations(
    session_local, settings, now: datetime, *, workers: int = 8
) -> list[str]:
    """Prove the synthetic cap admits exactly three reservations, then release them."""

    def reserve(index: int) -> str | None:
        with session_local() as db, db.begin():
            try:
                return str(
                    ChatSandboxSpendService(db, settings).reserve_interval(
                        origin="qualification",
                        worker_generation=f"qualification-{index}",
                        now=now,
                    )
                )
            except ChatComputeDisabled:
                return None

    with ThreadPoolExecutor(max_workers=workers) as executor:
        reservations = list(executor.map(reserve, range(8)))
    accepted_reservations = [value for value in reservations if value is not None]
    if len(accepted_reservations) != 3:
        raise RuntimeError(
            "atomic reservation qualification did not admit exactly three reservations"
        )
    with session_local() as db, db.begin():
        service = ChatSandboxSpendService(db, settings)
        for interval_id in accepted_reservations:
            service.abort_reservation(
                uuid.UUID(interval_id), "qualification_complete", now
            )
        db.flush()
        open_intervals = db.execute(
            select(ChatSandboxComputeInterval.id).where(
                ChatSandboxComputeInterval.environment == settings.environment,
                ChatSandboxComputeInterval.terminal_at.is_(None),
            )
        ).all()
    if open_intervals:
        raise RuntimeError("synthetic qualification reservations were left open")
    return accepted_reservations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment", choices=("staging", "production"), default="staging"
    )
    parser.add_argument("--qualification-id", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    confirmation = confirmation_for(args.environment)
    if args.confirm != confirmation:
        parser.error(f"--confirm must be {confirmation}")
    if not re.fullmatch(r"[a-z0-9]{4,12}", args.qualification_id):
        parser.error("--qualification-id must be 4-12 lowercase letters or digits")
    base = get_settings()
    if (
        base.environment != args.environment
        or not base.chat_sandbox_spend_enforcement_enabled
    ):
        parser.error(f"qualification requires {args.environment} spend enforcement")
    environment = f"{args.environment}-q-{args.qualification_id}"
    settings = base.model_copy(update={"environment": environment})
    now = datetime.now(UTC)
    samples = (
        (74_990_000, "armed"),
        (75_000_000, "warning"),
        (99_990_000, "warning"),
        (100_000_000, "tripped"),
    )
    observed = []
    with db_manager.session_local() as db, db.begin():
        existing = db.execute(
            select(ChatSandboxBudgetState.id).where(
                ChatSandboxBudgetState.environment == environment
            )
        ).first()
        if existing is not None:
            parser.error("qualification ID has already been used; choose a new ID")
        service = ChatSandboxSpendService(db, settings)
        for floor, expected in samples:
            state = service.reconcile_provider_floor(floor, now)
            if state.circuit_state != expected:
                raise RuntimeError(
                    f"threshold {floor} produced {state.circuit_state}, expected {expected}"
                )
            observed.append(
                {"effective_microusd": floor, "circuit_state": state.circuit_state}
            )
        service.record_kill_sweep(complete=True, now=now)
    reservation_environment = f"{environment}-r"
    with db_manager.session_local() as db:
        reservation = ChatSandboxSpendService(db, settings).reservation_amount()
    reservation_settings = settings.model_copy(
        update={
            "environment": reservation_environment,
            "chat_sandbox_warning_microusd": 1,
            "chat_sandbox_application_cap_microusd": reservation * 3 + 1,
            "chat_sandbox_environment_cap_microusd": reservation * 4 + 1,
            "chat_sandbox_workspace_cap_microusd": reservation * 5 + 1,
            "chat_sandbox_budget_attestation": "synthetic-concurrency-v1",
        }
    )

    accepted_reservations = qualify_concurrent_reservations(
        db_manager.session_local, reservation_settings, now
    )
    with db_manager.session_local() as db, db.begin():
        restarted = ChatSandboxSpendService(db, settings).status(now)
        if restarted["circuit_state"] != "tripped":
            raise RuntimeError("trip did not survive a fresh service instance")
        next_cycle = restarted["cycle_end_at"]
        rearmed = ChatSandboxSpendService(db, settings).reconcile_provider_floor(
            0, next_cycle
        )
        if rearmed.circuit_state != "armed":
            raise RuntimeError("synthetic next-cycle re-arm failed")
    delivered = asyncio.run(deliver_all_spend_alerts(settings))
    with db_manager.session_local() as db:
        events = list(
            db.execute(
                select(
                    ChatSandboxCircuitEvent.event_type,
                    ChatSandboxCircuitEvent.delivery_state,
                )
                .join(
                    ChatSandboxBudgetState,
                    ChatSandboxBudgetState.id
                    == ChatSandboxCircuitEvent.budget_state_id,
                )
                .where(ChatSandboxBudgetState.environment == environment)
            ).all()
        )
    required_events = {"warning_entered", "circuit_tripped", "cycle_rearmed"}
    observed_events = {event_type for event_type, _state in events}
    if not required_events <= observed_events:
        raise RuntimeError(
            "required warning, trip, and recovery events were not emitted"
        )
    if any(state != "delivered" for _event_type, state in events):
        raise RuntimeError("one or more synthetic alert transitions were not delivered")
    fallback_environment = f"{environment}-f"
    fallback_settings = settings.model_copy(
        update={"environment": fallback_environment}
    )
    with db_manager.session_local() as db, db.begin():
        service = ChatSandboxSpendService(db, fallback_settings)
        service.reconcile_provider_floor(75_000_000, now)
        # Deployed repository sessions disable autoflush, so make the synthetic
        # transition visible to the verification query in this transaction.
        db.flush()
        fallback_event = db.execute(
            fallback_spend_event_statement(fallback_environment)
        ).scalar_one()
        # Exercise the real fallback destination without sending five deliberate
        # failures to the primary endpoint first.
        fallback_event.delivery_state = "failed"
        fallback_event.delivery_attempts = 5
        fallback_event_id = fallback_event.id
    asyncio.run(SandboxSessionManager(fallback_settings).deliver_spend_alerts())
    with db_manager.session_local() as db:
        fallback_state = db.execute(
            select(ChatSandboxCircuitEvent.fallback_delivery_state).where(
                ChatSandboxCircuitEvent.id == fallback_event_id
            )
        ).scalar_one()
    if fallback_state != "delivered":
        raise RuntimeError("the synthetic fallback alert was not delivered")

    title_environment = f"{environment}-t"
    title_settings = settings.model_copy(
        update={
            "environment": title_environment,
            "chat_title_warning_microusd": 1,
            "chat_title_monthly_cap_microusd": (
                settings.chat_title_max_call_microusd * 2
            ),
        }
    )
    with db_manager.session_local() as db, db.begin():
        service = ChatTitleBudgetService(db, title_settings)
        for _ in range(2):
            call_id = uuid.uuid4()
            service.reserve_call(call_id, now=now)
            service.mark_dispatched(call_id, now=now)
            service.settle_call(
                call_id,
                input_tokens=None,
                output_tokens=None,
                now=now,
            )
    title_delivered = asyncio.run(deliver_title_budget_alerts(title_settings))
    with db_manager.session_local() as db:
        title_events = list(
            db.execute(
                select(
                    ChatTitleBudgetEvent.event_type,
                    ChatTitleBudgetEvent.delivery_state,
                )
                .join(
                    ChatTitleBudgetState,
                    ChatTitleBudgetState.id == ChatTitleBudgetEvent.budget_state_id,
                )
                .where(ChatTitleBudgetState.environment == title_environment)
            ).all()
        )
    if title_delivered != 2 or set(title_events) != {
        ("warning", "delivered"),
        ("exhausted", "delivered"),
    }:
        raise RuntimeError(
            "the synthetic title-budget warning/exhaustion alerts were not delivered"
        )

    title_fallback_environment = f"{environment}-tf"
    title_fallback_settings = title_settings.model_copy(
        update={
            "environment": title_fallback_environment,
            "chat_sandbox_slack_webhook_url": "https://127.0.0.1:1",
        }
    )
    with db_manager.session_local() as db, db.begin():
        ChatTitleBudgetService(db, title_fallback_settings).reserve_call(
            uuid.uuid4(), now=now
        )
    asyncio.run(deliver_title_budget_alerts(title_fallback_settings))
    with db_manager.session_local() as db:
        title_fallback_state = db.execute(
            select(ChatTitleBudgetEvent.fallback_delivery_state)
            .join(
                ChatTitleBudgetState,
                ChatTitleBudgetState.id == ChatTitleBudgetEvent.budget_state_id,
            )
            .where(ChatTitleBudgetState.environment == title_fallback_environment)
        ).scalar_one()
    if title_fallback_state != "delivered":
        raise RuntimeError(
            "the synthetic title-budget fallback alert was not delivered"
        )

    provider_event = new_event(
        "hf_provider_sustained_failure",
        now=now,
        count=5,
        classifications={
            "failed_turns": 5,
            "total_turns": 5,
            "failure_percent": 100,
        },
    )
    provider_alert_state = {"events": [provider_event]}
    if asyncio.run(deliver_pending(provider_alert_state, settings)) != 1 or (
        provider_event["primary_delivery_state"] != "delivered"
    ):
        raise RuntimeError("the synthetic sustained-provider alert was not delivered")

    runtime_event = new_event(
        "chat_runtime_critical",
        now=now,
        classifications={"synthetic_runtime_signal": 1},
    )
    runtime_alert_state = {"events": [runtime_event]}
    operational_fallback_settings = settings.model_copy(
        update={"chat_sandbox_slack_webhook_url": "https://127.0.0.1:1"}
    )
    if (
        asyncio.run(deliver_pending(runtime_alert_state, operational_fallback_settings))
        != 1
        or runtime_event["fallback_delivery_state"] != "delivered"
    ):
        raise RuntimeError("the synthetic critical-runtime fallback was not delivered")
    report = {
        "environment": environment,
        "samples": observed,
        "restart_persisted": True,
        "next_cycle": cycle_end(now.date().replace(day=1)).isoformat(),
        "next_cycle_rearmed": True,
        "alerts_delivered": delivered,
        "fallback_alert_delivered": True,
        "title_primary_alert_delivered": True,
        "title_fallback_alert_delivered": True,
        "provider_operational_alert_delivered": True,
        "runtime_operational_fallback_delivered": True,
        "event_types": sorted(observed_events),
        "concurrent_reservations": {
            "attempted": 8,
            "accepted": len(accepted_reservations),
            "rejected": 8 - len(accepted_reservations),
        },
        "admin_path": f"/api/v1/chat/admin/sandbox-spend?environment={environment}",
        "provider_compute_created": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
