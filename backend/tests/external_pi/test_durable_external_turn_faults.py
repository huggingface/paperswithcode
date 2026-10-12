from __future__ import annotations

from collections import Counter

import pytest

from backend.loadtests.durable_external_turn_faults import (
    FaultSchedule,
    OperationIdentity,
    RetainedRunIdentity,
    SubscriberCursorIdentity,
    WorkerTurnClaimIdentity,
    built_in_fault_schedules,
    simulate_fault_schedule,
)


@pytest.mark.parametrize(
    ("name", "terminal_cause", "executor_starts"),
    (
        ("browser_disconnect", "completed", 0),
        ("api_subscriber_process_loss", "completed", 0),
        ("external_websocket_loss", "completed", 0),
        ("worker_drain", "completed", 0),
        ("executor_response_loss", "completed", 1),
        ("cancellation", "cancelled", 1),
    ),
)
def test_fault_schedule_preserves_single_model_and_executor_operation(
    name: str, terminal_cause: str, executor_starts: int
) -> None:
    """Catches reconnect paths that replay model or executor work."""
    result = simulate_fault_schedule(built_in_fault_schedules()[name])

    assert result.model_starts == 1
    assert result.executor_starts == executor_starts
    assert result.terminal_cause == terminal_cause
    assert result.durable_terminal_commits == 1
    assert result.queued_states == 0
    assert all(count <= 1 for count in result.executor_starts_by_operation.values())


def test_all_six_fault_schedules_are_content_free_and_have_stable_identity() -> None:
    """Catches a schedule accidentally retaining prompts, commands, or tokens."""
    schedules = built_in_fault_schedules()

    assert tuple(schedules) == (
        "browser_disconnect",
        "api_subscriber_process_loss",
        "external_websocket_loss",
        "worker_drain",
        "executor_response_loss",
        "cancellation",
    )
    assert all(schedule.content_free for schedule in schedules.values())
    operation_ids = [
        operation
        for schedule in schedules.values()
        for operation in schedule.operation_identities
    ]
    assert operation_ids == [
        OperationIdentity("turn-0005", "tool-0001", 0),
        OperationIdentity("turn-0006", "tool-0001", 0),
    ]


def test_duplicate_start_steps_cannot_forge_exactly_once_evidence() -> None:
    """Catches a simulator/report path that hides duplicate provider execution."""
    schedule = FaultSchedule(
        name="duplicate_model_start",
        steps=("model_start", "model_start", "terminal_completed"),
    )

    with pytest.raises(ValueError, match="model start"):
        simulate_fault_schedule(schedule)


def test_unknown_fault_action_cannot_forge_recovery_evidence() -> None:
    schedule = FaultSchedule(
        name="forged_recovery",
        steps=("model_start", "unverified_reattach", "terminal_completed"),
    )

    with pytest.raises(ValueError, match="unknown action"):
        simulate_fault_schedule(schedule)


def test_executor_identity_is_counted_directly_not_inferred_from_logs() -> None:
    """Catches Task 10's parked log undercount being mistaken for durable truth."""
    identity = OperationIdentity("turn-0001", "tool-0001", 0)
    result = simulate_fault_schedule(
        FaultSchedule(
            name="terminal_log_loss",
            steps=(
                "model_start",
                ("executor_start", identity),
                ("executor_response_lost", identity),
                ("executor_attach", identity),
                "terminal_completed",
                "terminal_log_lost",
            ),
        )
    )

    assert result.executor_starts_by_operation == Counter({identity: 1})
    assert result.durable_terminal_commits == 1
    assert result.terminal_log_records == 0
    assert result.terminal_cause == "completed"


@pytest.mark.parametrize(
    "steps",
    (
        ("model_start", "subscriber_cursor_reattach", "terminal_completed"),
        ("model_start", "subscriber_detach", "terminal_completed"),
        ("model_start", "worker_exact_claim_reattach", "terminal_completed"),
        ("model_start", "worker_socket_lost", "terminal_completed"),
        ("model_start", "executor_response_lost", "terminal_completed"),
        ("model_start", "cancel_requested", "terminal_completed"),
        ("model_start", "terminal_cancelled"),
        ("model_start", "worker_drain", "terminal_completed"),
        (
            "model_start",
            "terminal_completed",
            "subscriber_detach",
        ),
        (
            "model_start",
            ("executor_start", OperationIdentity("turn-0001", "tool-0001", 0)),
            "terminal_completed",
        ),
    ),
)
def test_fault_schedule_rejects_missing_reordered_or_uncorrelated_recovery(
    steps,
) -> None:
    with pytest.raises(ValueError, match="fault schedule"):
        simulate_fault_schedule(FaultSchedule(name="invalid_recovery", steps=steps))


def test_executor_response_loss_attach_requires_same_operation_identity() -> None:
    first = OperationIdentity("turn-0001", "tool-0001", 0)
    second = OperationIdentity("turn-0001", "tool-0002", 0)
    schedule = FaultSchedule(
        name="mismatched_executor_attach",
        steps=(
            "model_start",
            ("executor_start", first),
            ("executor_response_lost", first),
            ("executor_start", second),
            ("executor_attach", second),
            "terminal_completed",
        ),
    )

    with pytest.raises(ValueError, match="same executor operation"):
        simulate_fault_schedule(schedule)


@pytest.mark.parametrize(
    "steps",
    (
        (
            "model_start",
            ("subscriber_detach", SubscriberCursorIdentity("turn-0001", 10)),
            ("subscriber_cursor_reattach", SubscriberCursorIdentity("turn-0001", 9)),
            "terminal_completed",
        ),
        (
            "model_start",
            (
                "worker_socket_lost",
                WorkerTurnClaimIdentity("turn-0001", 1, "worker-0001", 1),
            ),
            (
                "worker_exact_claim_reattach",
                WorkerTurnClaimIdentity("turn-0001", 1, "worker-0001", 2),
            ),
            "terminal_completed",
        ),
        (
            "model_start",
            ("worker_drain", RetainedRunIdentity("turn-0001", "run-0001")),
            (
                "worker_drain_retained_run",
                RetainedRunIdentity("turn-0001", "run-0002"),
            ),
            "terminal_completed",
        ),
    ),
)
def test_fault_recovery_requires_same_cursor_claim_and_retained_run(steps) -> None:
    with pytest.raises(ValueError, match="same .*identity"):
        simulate_fault_schedule(FaultSchedule(name="mismatched_identity", steps=steps))


def test_subscriber_loss_before_model_start_is_not_repaired_by_later_reattach() -> None:
    cursor = SubscriberCursorIdentity("turn-0001", 10)
    schedule = FaultSchedule(
        name="subscriber_loss_before_start",
        steps=(
            ("subscriber_detach", cursor),
            "model_start",
            ("subscriber_cursor_reattach", cursor),
            "terminal_completed",
        ),
    )

    with pytest.raises(ValueError, match="model start must precede"):
        simulate_fault_schedule(schedule)


def test_cancelled_executor_requires_exact_cancel_attach_before_terminal() -> None:
    identity = OperationIdentity("turn-0001", "tool-0001", 0)
    schedule = FaultSchedule(
        name="cancel_without_executor_settlement",
        steps=(
            "model_start",
            ("executor_start", identity),
            "cancel_requested",
            "terminal_cancelled",
        ),
    )

    with pytest.raises(ValueError, match="executor cancellation settlement"):
        simulate_fault_schedule(schedule)


@pytest.mark.parametrize(
    "steps",
    (
        (
            "model_start",
            ("executor_start", OperationIdentity("turn-0001", "tool-0001", 0)),
            (
                "executor_attach_cancel",
                OperationIdentity("turn-0001", "tool-0001", 0),
            ),
            "cancel_requested",
            "terminal_cancelled",
        ),
        (
            "model_start",
            ("executor_start", OperationIdentity("turn-0001", "tool-0001", 0)),
            (
                "executor_start",
                OperationIdentity("turn-0001", "tool-0002", 0),
            ),
            "cancel_requested",
            (
                "executor_attach_cancel",
                OperationIdentity("turn-0001", "tool-0002", 0),
            ),
            "terminal_cancelled",
        ),
        (
            "model_start",
            "cancel_requested",
            ("executor_start", OperationIdentity("turn-0001", "tool-0001", 0)),
            "terminal_cancelled",
        ),
    ),
)
def test_cancel_settlement_requires_request_order_and_every_active_operation(
    steps,
) -> None:
    with pytest.raises(ValueError, match="fault schedule"):
        simulate_fault_schedule(
            FaultSchedule(name="invalid_cancel_settlement", steps=steps)
        )


def test_terminal_log_loss_requires_canonical_terminal_log_opportunity() -> None:
    schedule = FaultSchedule(
        name="log_loss_before_terminal",
        steps=("model_start", "terminal_log_lost", "terminal_completed"),
    )

    with pytest.raises(ValueError, match="terminal log loss precedes"):
        simulate_fault_schedule(schedule)
