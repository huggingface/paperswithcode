"""Deterministic, content-free fault schedules for durable external turns."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeAlias

_OPAQUE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FAULT_ACTIONS = frozenset(
    {
        "model_start",
        "subscriber_detach",
        "subscriber_process_lost",
        "subscriber_cursor_reattach",
        "worker_socket_lost",
        "worker_exact_claim_reattach",
        "worker_drain",
        "worker_drain_retained_run",
        "executor_start",
        "executor_response_lost",
        "executor_attach",
        "cancel_requested",
        "executor_attach_cancel",
        "queued",
        "terminal_completed",
        "terminal_cancelled",
        "terminal_log_lost",
    }
)


@dataclass(frozen=True, slots=True)
class OperationIdentity:
    turn_id: str
    tool_call_id: str
    attempt: int

    def __post_init__(self) -> None:
        if (
            not _OPAQUE_ID.fullmatch(self.turn_id)
            or not _OPAQUE_ID.fullmatch(self.tool_call_id)
            or type(self.attempt) is not int
            or self.attempt < 0
        ):
            raise ValueError("fault schedule operation identity is invalid")


@dataclass(frozen=True, slots=True)
class SubscriberCursorIdentity:
    turn_id: str
    event_cursor: int

    def __post_init__(self) -> None:
        if (
            not _OPAQUE_ID.fullmatch(self.turn_id)
            or type(self.event_cursor) is not int
            or self.event_cursor < 0
        ):
            raise ValueError("fault schedule subscriber cursor identity is invalid")


@dataclass(frozen=True, slots=True)
class WorkerTurnClaimIdentity:
    turn_id: str
    turn_generation: int
    worker_id: str
    worker_generation: int

    def __post_init__(self) -> None:
        if (
            not _OPAQUE_ID.fullmatch(self.turn_id)
            or type(self.turn_generation) is not int
            or self.turn_generation < 1
            or not _OPAQUE_ID.fullmatch(self.worker_id)
            or type(self.worker_generation) is not int
            or self.worker_generation < 1
        ):
            raise ValueError("fault schedule worker claim identity is invalid")


@dataclass(frozen=True, slots=True)
class RetainedRunIdentity:
    turn_id: str
    run_id: str

    def __post_init__(self) -> None:
        if not _OPAQUE_ID.fullmatch(self.turn_id) or not _OPAQUE_ID.fullmatch(
            self.run_id
        ):
            raise ValueError("fault schedule retained run identity is invalid")


FaultIdentity: TypeAlias = (
    OperationIdentity
    | SubscriberCursorIdentity
    | WorkerTurnClaimIdentity
    | RetainedRunIdentity
)
FaultAction: TypeAlias = str | tuple[str, FaultIdentity]


def _content_free_step(step: FaultAction) -> bool:
    if isinstance(step, str):
        return bool(_OPAQUE_ID.fullmatch(step.replace("_", "-")))
    return (
        len(step) == 2
        and isinstance(step[0], str)
        and isinstance(
            step[1],
            (
                OperationIdentity,
                SubscriberCursorIdentity,
                WorkerTurnClaimIdentity,
                RetainedRunIdentity,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class FaultSchedule:
    name: str
    steps: tuple[FaultAction, ...]

    @property
    def operation_identities(self) -> tuple[OperationIdentity, ...]:
        return tuple(
            dict.fromkeys(
                step[1]
                for step in self.steps
                if isinstance(step, tuple) and isinstance(step[1], OperationIdentity)
            )
        )

    @property
    def content_free(self) -> bool:
        return bool(_OPAQUE_ID.fullmatch(self.name.replace("_", "-"))) and all(
            _content_free_step(step) for step in self.steps
        )


@dataclass(frozen=True, slots=True)
class FaultResult:
    model_starts: int
    executor_starts_by_operation: Counter[OperationIdentity]
    terminal_cause: Literal["completed", "cancelled"]
    durable_terminal_commits: int
    terminal_log_records: int
    queued_states: int

    @property
    def executor_starts(self) -> int:
        return sum(self.executor_starts_by_operation.values())


def built_in_fault_schedules():
    browser_cursor = SubscriberCursorIdentity("turn-0001", 10)
    process_cursor = SubscriberCursorIdentity("turn-0002", 20)
    worker_claim = WorkerTurnClaimIdentity("turn-0003", 1, "worker-0001", 1)
    retained_run = RetainedRunIdentity("turn-0004", "run-0001")
    executor_loss = OperationIdentity("turn-0005", "tool-0001", 0)
    cancellation = OperationIdentity("turn-0006", "tool-0001", 0)
    schedules = {
        "browser_disconnect": FaultSchedule(
            "browser_disconnect",
            (
                "model_start",
                ("subscriber_detach", browser_cursor),
                ("subscriber_cursor_reattach", browser_cursor),
                "terminal_completed",
            ),
        ),
        "api_subscriber_process_loss": FaultSchedule(
            "api_subscriber_process_loss",
            (
                "model_start",
                ("subscriber_process_lost", process_cursor),
                ("subscriber_cursor_reattach", process_cursor),
                "terminal_completed",
            ),
        ),
        "external_websocket_loss": FaultSchedule(
            "external_websocket_loss",
            (
                "model_start",
                ("worker_socket_lost", worker_claim),
                ("worker_exact_claim_reattach", worker_claim),
                "terminal_completed",
            ),
        ),
        "worker_drain": FaultSchedule(
            "worker_drain",
            (
                "model_start",
                ("worker_drain", retained_run),
                ("worker_drain_retained_run", retained_run),
                "terminal_completed",
            ),
        ),
        "executor_response_loss": FaultSchedule(
            "executor_response_loss",
            (
                "model_start",
                ("executor_start", executor_loss),
                ("executor_response_lost", executor_loss),
                ("executor_attach", executor_loss),
                "terminal_completed",
            ),
        ),
        "cancellation": FaultSchedule(
            "cancellation",
            (
                "model_start",
                ("executor_start", cancellation),
                "cancel_requested",
                ("executor_attach_cancel", cancellation),
                "terminal_cancelled",
            ),
        ),
    }
    return MappingProxyType(schedules)


def simulate_fault_schedule(schedule: FaultSchedule) -> FaultResult:
    """Reduce a schedule from durable actions, never from best-effort logs."""
    if not schedule.content_free:
        raise ValueError("fault schedule must be content free")
    model_starts = 0
    executor_starts: Counter[OperationIdentity] = Counter()
    terminal_cause: Literal["completed", "cancelled"] | None = None
    durable_terminal_commits = 0
    terminal_log_records = 0
    queued_states = 0
    started_operations: set[OperationIdentity] = set()
    active_executor_operations: set[OperationIdentity] = set()
    subscriber_fault_pending: SubscriberCursorIdentity | None = None
    worker_socket_loss_pending: WorkerTurnClaimIdentity | None = None
    worker_drain_pending: RetainedRunIdentity | None = None
    lost_executor_operation: OperationIdentity | None = None
    cancel_requested = False
    cancel_pending_operations: set[OperationIdentity] = set()

    for step in schedule.steps:
        action = step[0] if isinstance(step, tuple) else step
        identity = step[1] if isinstance(step, tuple) else None
        if action not in _FAULT_ACTIONS:
            raise ValueError("fault schedule contains an unknown action")
        if terminal_cause is not None and action != "terminal_log_lost":
            raise ValueError("fault schedule continues after terminal outcome")
        if action != "model_start" and model_starts != 1:
            raise ValueError("fault schedule model start must precede every action")
        if action == "model_start":
            model_starts += 1
            if model_starts > 1:
                raise ValueError("fault schedule repeated the model start")
        elif action == "executor_start":
            if not isinstance(identity, OperationIdentity):
                raise ValueError("fault schedule executor identity is invalid")
            if cancel_requested:
                raise ValueError("fault schedule starts an executor after cancellation")
            executor_starts[identity] += 1
            started_operations.add(identity)
            active_executor_operations.add(identity)
            if executor_starts[identity] > 1:
                raise ValueError("fault schedule repeated an executor operation")
        elif action == "subscriber_detach" or action == "subscriber_process_lost":
            if not isinstance(identity, SubscriberCursorIdentity):
                raise ValueError("fault schedule subscriber identity is invalid")
            if subscriber_fault_pending is not None:
                raise ValueError("fault schedule repeats subscriber loss")
            subscriber_fault_pending = identity
        elif action == "subscriber_cursor_reattach":
            if subscriber_fault_pending is None:
                raise ValueError("fault schedule reattaches a live subscriber")
            if identity != subscriber_fault_pending:
                raise ValueError(
                    "fault schedule must use the same subscriber cursor identity"
                )
            subscriber_fault_pending = None
        elif action == "worker_socket_lost":
            if not isinstance(identity, WorkerTurnClaimIdentity):
                raise ValueError("fault schedule worker claim identity is invalid")
            if worker_socket_loss_pending is not None:
                raise ValueError("fault schedule repeats worker socket loss")
            worker_socket_loss_pending = identity
        elif action == "worker_exact_claim_reattach":
            if worker_socket_loss_pending is None:
                raise ValueError("fault schedule reattaches a live worker")
            if identity != worker_socket_loss_pending:
                raise ValueError(
                    "fault schedule must use the same worker claim identity"
                )
            worker_socket_loss_pending = None
        elif action == "worker_drain":
            if not isinstance(identity, RetainedRunIdentity):
                raise ValueError("fault schedule retained run identity is invalid")
            if worker_drain_pending is not None:
                raise ValueError("fault schedule repeats worker drain")
            worker_drain_pending = identity
        elif action == "worker_drain_retained_run":
            if worker_drain_pending is None:
                raise ValueError("fault schedule lacks a worker drain")
            if identity != worker_drain_pending:
                raise ValueError(
                    "fault schedule must use the same retained run identity"
                )
            worker_drain_pending = None
        elif action == "executor_response_lost":
            if (
                not isinstance(identity, OperationIdentity)
                or identity not in started_operations
            ):
                raise ValueError("fault schedule loses an unknown executor operation")
            if lost_executor_operation is not None:
                raise ValueError("fault schedule repeats executor response loss")
            lost_executor_operation = identity
        elif action == "executor_attach":
            if (
                not isinstance(identity, OperationIdentity)
                or identity not in started_operations
            ):
                raise ValueError(
                    "fault schedule attached an unknown executor operation"
                )
            if identity != lost_executor_operation:
                raise ValueError(
                    "fault schedule must attach the same executor operation"
                )
            lost_executor_operation = None
            active_executor_operations.remove(identity)
        elif action == "cancel_requested":
            if cancel_requested:
                raise ValueError("fault schedule repeats cancellation")
            cancel_requested = True
            cancel_pending_operations = set(active_executor_operations)
        elif action == "executor_attach_cancel":
            if (
                not cancel_requested
                or not isinstance(identity, OperationIdentity)
                or identity not in cancel_pending_operations
            ):
                raise ValueError("fault schedule cancellation attach is invalid")
            cancel_pending_operations.remove(identity)
            active_executor_operations.remove(identity)
        elif action == "queued":
            queued_states += 1
        elif action in {"terminal_completed", "terminal_cancelled"}:
            if any(
                (
                    subscriber_fault_pending is not None,
                    worker_socket_loss_pending is not None,
                    worker_drain_pending is not None,
                    lost_executor_operation is not None,
                    action == "terminal_completed" and bool(active_executor_operations),
                )
            ):
                raise ValueError("fault schedule terminal precedes recovery")
            if action == "terminal_cancelled" and not cancel_requested:
                raise ValueError("fault schedule cancellation was not requested")
            if action == "terminal_cancelled" and cancel_pending_operations:
                raise ValueError(
                    "fault schedule lacks executor cancellation settlement"
                )
            if action == "terminal_completed" and cancel_requested:
                raise ValueError("fault schedule completed after cancellation")
            durable_terminal_commits += 1
            terminal_log_records += 1
            if durable_terminal_commits > 1:
                raise ValueError("fault schedule repeated the terminal commit")
            terminal_cause = (
                "completed" if action == "terminal_completed" else "cancelled"
            )
        elif action == "terminal_log_lost":
            if terminal_cause is None or terminal_log_records != 1:
                raise ValueError("fault schedule terminal log loss precedes commit")
            terminal_log_records = 0

    if model_starts != 1 or durable_terminal_commits != 1 or terminal_cause is None:
        raise ValueError("fault schedule lacks one model start and terminal outcome")
    return FaultResult(
        model_starts=model_starts,
        executor_starts_by_operation=executor_starts,
        terminal_cause=terminal_cause,
        durable_terminal_commits=durable_terminal_commits,
        terminal_log_records=terminal_log_records,
        queued_states=queued_states,
    )
