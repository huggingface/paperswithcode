"""Typed durable-turn states, failure codes, and canonical mappings."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Mapping


class TurnState(StrEnum):
    ADMITTED = "admitted"
    LEASED = "leased"
    RUNNING = "running"
    WAITING_MODEL = "waiting_model"
    WAITING_TOOL = "waiting_tool"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class TurnFailureCode(StrEnum):
    CANCELLED = "cancelled"
    CANCEL_CONTROL_MISSING = "cancel_control_missing"
    DISPATCH_FAILED = "dispatch_failed"
    EVENT_JOURNAL_EXHAUSTED = "event_journal_exhausted"
    EXECUTION_LOST = "execution_lost"
    EXTERNAL_WORKER_LOST = "external_worker_lost"
    LEASE_EXPIRED = "lease_expired"
    PROJECTION_MISMATCH = "projection_mismatch"
    TURN_FAILED = "turn_failed"


NONTERMINAL_STATES = frozenset(
    state.value
    for state in (
        TurnState.ADMITTED,
        TurnState.LEASED,
        TurnState.RUNNING,
        TurnState.WAITING_MODEL,
        TurnState.WAITING_TOOL,
        TurnState.CANCELLING,
    )
)
TERMINAL_STATES = frozenset(
    state.value
    for state in (TurnState.COMPLETED, TurnState.FAILED, TurnState.INTERRUPTED)
)
CLAIMED_STATES = NONTERMINAL_STATES - {TurnState.ADMITTED.value}
TRANSITIONS = {
    TurnState.LEASED.value: frozenset(
        {TurnState.RUNNING.value, TurnState.CANCELLING.value}
    ),
    TurnState.RUNNING.value: frozenset(
        {
            TurnState.WAITING_MODEL.value,
            TurnState.WAITING_TOOL.value,
            TurnState.CANCELLING.value,
        }
    ),
    TurnState.WAITING_MODEL.value: frozenset(
        {TurnState.RUNNING.value, TurnState.CANCELLING.value}
    ),
    TurnState.WAITING_TOOL.value: frozenset(
        {TurnState.RUNNING.value, TurnState.CANCELLING.value}
    ),
    TurnState.CANCELLING.value: frozenset(),
}
RECONCILABLE_FAILURE_CODES = frozenset(
    code.value
    for code in (
        TurnFailureCode.DISPATCH_FAILED,
        TurnFailureCode.EXTERNAL_WORKER_LOST,
        TurnFailureCode.EVENT_JOURNAL_EXHAUSTED,
        TurnFailureCode.EXECUTION_LOST,
        TurnFailureCode.CANCELLED,
        TurnFailureCode.CANCEL_CONTROL_MISSING,
    )
)
LIFECYCLE_CODES = frozenset(
    {
        *(state.value for state in TurnState),
        *(code.value for code in TurnFailureCode),
        "created",
        "reused",
        "released",
        "invalidated",
        "accepted",
        "succeeded",
        "stale",
        "expired",
    }
)
FAILURE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")

_EXPIRY_FAILURE_BY_STATE = {
    TurnState.LEASED.value: TurnFailureCode.DISPATCH_FAILED.value,
    TurnState.RUNNING.value: TurnFailureCode.EXTERNAL_WORKER_LOST.value,
    TurnState.WAITING_MODEL.value: TurnFailureCode.EXTERNAL_WORKER_LOST.value,
    TurnState.WAITING_TOOL.value: TurnFailureCode.EXECUTION_LOST.value,
    TurnState.CANCELLING.value: TurnFailureCode.CANCEL_CONTROL_MISSING.value,
}


def classify_expired_state(state: str, failure_code: str | None) -> str:
    if failure_code in RECONCILABLE_FAILURE_CODES:
        return failure_code
    return _EXPIRY_FAILURE_BY_STATE.get(
        state, TurnFailureCode.EXTERNAL_WORKER_LOST.value
    )


def terminal_stream_outcome(
    event: str, payload: Mapping[str, object]
) -> tuple[str, str | None] | None:
    if event == "done":
        if payload.get("finish_reason") == "stopped":
            return TurnState.INTERRUPTED.value, TurnFailureCode.CANCELLED.value
        return TurnState.COMPLETED.value, None
    if event != "error":
        return None
    code = str(payload.get("code") or TurnFailureCode.TURN_FAILED.value)
    if FAILURE_CODE_PATTERN.fullmatch(code) is None:
        code = TurnFailureCode.TURN_FAILED.value
    return TurnState.FAILED.value, code
