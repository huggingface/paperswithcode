"""Audited operator disable and exceptional early re-arm for sandbox spend."""

from __future__ import annotations

import argparse
import getpass
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxCircuitEvent, ChatSandboxComputeInterval
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService


def operator_identity(settings: Settings) -> str:
    if os.geteuid() != 0:
        raise SystemExit("circuit control must run as root")
    operator = (os.environ.get("SUDO_USER") or getpass.getuser()).strip().lower()
    if operator not in settings.chat_sandbox_operator_username_set:
        raise SystemExit("operator is not allowlisted")
    return operator


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    actions = root.add_subparsers(dest="action", required=True)
    for name in ("disable", "rearm"):
        action = actions.add_parser(name)
        action.add_argument("--environment", required=True)
        action.add_argument("--cycle", required=True)
        action.add_argument("--reason", required=True)
        action.add_argument("--evidence", required=True)
        action.add_argument("--confirm")
    rearm = actions.choices["rearm"]
    rearm.add_argument(
        "--basis",
        required=True,
        choices=(
            "accounting-correction",
            "reviewed-higher-caps",
            "reviewed-provider-cap",
            "reviewed-policy-transition",
        ),
    )
    rearm.add_argument("--orphan-sweep-event-id", required=True)
    return root


def _event(
    state,
    *,
    event_type: str,
    reason: str,
    operator: str,
    evidence: str,
    now: datetime,
    details: dict | None = None,
) -> ChatSandboxCircuitEvent:
    return ChatSandboxCircuitEvent(
        id=uuid.uuid4(),
        budget_state_id=state.id,
        event_type=event_type,
        severity="critical",
        reason=reason,
        details={
            "environment": state.environment,
            "billing_cycle": state.billing_cycle.isoformat(),
            "operator": operator,
            "evidence": evidence,
            **(details or {}),
        },
        created_at=now,
    )


def reviewed_policy_transition_allowed(state, settings: Settings) -> bool:
    """Accept only the reviewed same-cap starter-to-Environment transition."""

    return bool(
        state.trip_reason == "accounting_integrity"
        and state.warning_microusd == settings.chat_sandbox_warning_microusd
        and state.application_cap_microusd
        == settings.chat_sandbox_application_cap_microusd
        and state.workspace_cap_microusd == settings.chat_sandbox_workspace_cap_microusd
        and state.environment_cap_microusd == 0
        and settings.chat_sandbox_environment_cap_microusd > 0
        and state.policy_attestation.endswith(f"-{settings.environment}-starter-v1")
        and state.policy_attestation != settings.chat_sandbox_budget_attestation
    )


def reviewed_higher_caps_allowed(state, settings: Settings) -> bool:
    """Accept only higher application guardrails below unchanged provider caps."""

    workspace_attestation = (
        f"modal-workspace-{settings.chat_sandbox_modal_workspace}-250-staging"
    )
    if (
        settings.environment == "staging"
        and settings.chat_sandbox_provider_mode == "starter_workspace"
        and settings.chat_sandbox_modal_workspace
        and state.policy_attestation == f"{workspace_attestation}-starter-v1"
        and settings.chat_sandbox_budget_attestation
        == f"{workspace_attestation}-starter-app105-v2"
        and state.warning_microusd
        == settings.chat_sandbox_warning_microusd
        == 75_000_000
        and state.application_cap_microusd == 100_000_000
        and settings.chat_sandbox_application_cap_microusd == 105_000_000
        and state.environment_cap_microusd
        == settings.chat_sandbox_environment_cap_microusd
        == 0
        and state.workspace_cap_microusd
        == settings.chat_sandbox_workspace_cap_microusd
        == 250_000_000
    ):
        return True
    return bool(
        settings.chat_sandbox_budget_attestation != state.policy_attestation
        and settings.chat_sandbox_application_cap_microusd
        > state.application_cap_microusd
        and state.warning_microusd
        < settings.chat_sandbox_warning_microusd
        < settings.chat_sandbox_application_cap_microusd
        and settings.chat_sandbox_environment_cap_microusd
        == state.environment_cap_microusd
        and settings.chat_sandbox_workspace_cap_microusd == state.workspace_cap_microusd
    )


def main() -> None:
    args = parser().parse_args()
    settings = get_settings()
    operator = operator_identity(settings)
    if args.environment != settings.environment:
        raise SystemExit("environment does not match the deployed runtime")
    if not args.reason.strip() or not args.evidence.strip():
        raise SystemExit("reason and reviewed evidence are required")
    expected = f"{args.action.upper()}_{settings.environment.upper()}_{args.cycle}"
    sweep_event_id = None
    if args.action == "rearm":
        try:
            sweep_event_id = uuid.UUID(args.orphan_sweep_event_id)
        except ValueError as error:
            raise SystemExit("orphan sweep event ID must be a UUID") from error
    now = datetime.now(UTC)
    failure: str | None = None
    with db_manager.session_local() as db, db.begin():
        service = ChatSandboxSpendService(db, settings)
        state = service.refresh(now)
        live = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxComputeInterval)
                .where(
                    ChatSandboxComputeInterval.environment == settings.environment,
                    ChatSandboxComputeInterval.terminal_at.is_(None),
                )
            )
            or 0
        )
        effective = max(state.estimated_accrued_microusd, state.provider_floor_microusd)
        preview = {
            "action": args.action,
            "operator": operator,
            "old_state": state.circuit_state,
            "effective_microusd": effective,
            "provider_floor_microusd": state.provider_floor_microusd,
            "remaining_microusd": state.application_cap_microusd - effective,
            "live_sandboxes": live,
            "old_policy_microusd": {
                "warning": state.warning_microusd,
                "application": state.application_cap_microusd,
                "environment": state.environment_cap_microusd,
                "workspace": state.workspace_cap_microusd,
            },
            "configured_policy_microusd": {
                "warning": settings.chat_sandbox_warning_microusd,
                "application": settings.chat_sandbox_application_cap_microusd,
                "environment": settings.chat_sandbox_environment_cap_microusd,
                "workspace": settings.chat_sandbox_workspace_cap_microusd,
            },
            "required_confirmation": expected,
        }
        print(preview)
        if args.confirm != expected:
            raise SystemExit(f"review the preview, then pass --confirm {expected}")

        if state.billing_cycle.isoformat() != args.cycle:
            failure = "billing cycle does not match"
        elif args.action == "disable":
            state.circuit_state = "tripped"
            state.trip_reason = "operator_disabled"
            state.tripped_at = state.tripped_at or now
            state.updated_at = now
            db.add(
                _event(
                    state,
                    event_type="operator_disabled",
                    reason=args.reason,
                    operator=operator,
                    evidence=args.evidence,
                    now=now,
                    details={"release": settings.release_id},
                )
            )
        else:
            reconciled_at = state.last_reconciled_at
            if reconciled_at is not None and reconciled_at.tzinfo is None:
                reconciled_at = reconciled_at.replace(tzinfo=UTC)
            sweep = db.get(ChatSandboxCircuitEvent, sweep_event_id)
            changes_caps = args.basis == "reviewed-higher-caps"
            changes_provider_cap = args.basis == "reviewed-provider-cap"
            changes_policy = args.basis == "reviewed-policy-transition"
            active_cap = (
                settings.chat_sandbox_application_cap_microusd
                if changes_caps
                else state.application_cap_microusd
            )
            if state.circuit_state != "tripped":
                failure = "circuit is not tripped"
            elif live or state.outstanding_reservation_microusd:
                failure = "live sandbox or reservation remains"
            elif (
                reconciled_at is None
                or state.reconciliation_state != "fresh"
                or (now - reconciled_at).total_seconds()
                > settings.chat_sandbox_reconciliation_stale_seconds
            ):
                failure = "provider reconciliation is not fresh"
            elif (
                sweep is None
                or sweep.budget_state_id != state.id
                or sweep.event_type != "kill_sweep_complete"
                or (
                    state.tripped_at is not None
                    and ChatSandboxSpendService._aware(sweep.created_at)
                    < ChatSandboxSpendService._aware(state.tripped_at)
                )
            ):
                failure = "a post-trip completed orphan sweep is required"
            elif effective >= active_cap:
                failure = "effective spend is at or above the active cap"
            elif changes_caps and not reviewed_higher_caps_allowed(state, settings):
                failure = (
                    "higher caps require a reviewed warning/application transition, "
                    "unchanged provider caps, and a new attestation"
                )
            elif changes_provider_cap and (
                settings.chat_sandbox_warning_microusd != state.warning_microusd
                or settings.chat_sandbox_application_cap_microusd
                != state.application_cap_microusd
                or settings.chat_sandbox_workspace_cap_microusd
                != state.workspace_cap_microusd
                or settings.chat_sandbox_environment_cap_microusd
                <= state.environment_cap_microusd
                or settings.chat_sandbox_budget_attestation == state.policy_attestation
            ):
                failure = (
                    "provider-cap review requires only a higher environment cap "
                    "and new attestation"
                )
            elif changes_policy and not reviewed_policy_transition_allowed(
                state, settings
            ):
                failure = (
                    "policy transition requires the exact starter-to-environment "
                    "guardrail change"
                )
            if failure is None:
                if changes_caps:
                    state.warning_microusd = settings.chat_sandbox_warning_microusd
                    state.application_cap_microusd = active_cap
                    state.environment_cap_microusd = (
                        settings.chat_sandbox_environment_cap_microusd
                    )
                    state.workspace_cap_microusd = (
                        settings.chat_sandbox_workspace_cap_microusd
                    )
                    state.policy_attestation = settings.chat_sandbox_budget_attestation
                elif changes_provider_cap:
                    state.environment_cap_microusd = (
                        settings.chat_sandbox_environment_cap_microusd
                    )
                    state.policy_attestation = settings.chat_sandbox_budget_attestation
                elif changes_policy:
                    state.environment_cap_microusd = (
                        settings.chat_sandbox_environment_cap_microusd
                    )
                    state.policy_attestation = settings.chat_sandbox_budget_attestation
                state.circuit_state = "armed"
                state.trip_reason = None
                state.tripped_at = None
                state.updated_at = now
                db.add(
                    _event(
                        state,
                        event_type="operator_rearmed",
                        reason=args.reason,
                        operator=operator,
                        evidence=args.evidence,
                        now=now,
                        details={
                            "release": settings.release_id,
                            "basis": args.basis,
                            "effective_microusd": effective,
                            "provider_floor_microusd": state.provider_floor_microusd,
                        },
                    )
                )
        if failure is not None:
            db.add(
                _event(
                    state,
                    event_type=f"operator_{args.action}_failed",
                    reason=failure,
                    operator=operator,
                    evidence=args.evidence,
                    now=now,
                    details={"requested_reason": args.reason},
                )
            )
    if failure is not None:
        raise SystemExit(failure)


if __name__ == "__main__":
    main()
