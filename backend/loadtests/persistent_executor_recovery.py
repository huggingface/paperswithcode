"""Deterministic Task 0 recovery matrix and reconnect scheduler."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

DeliveryBoundary = Literal[
    "before_delivery",
    "after_acceptance",
    "during_execution",
    "after_terminal_before_delivery",
]
FailureActor = Literal[
    "browser",
    "environment_socket",
    "rendezvous",
    "pi_worker",
    "harness",
    "environment_daemon",
]
LifecycleClass = Literal["active_claim", "assigned_idle", "blank"]


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    actor: FailureActor
    boundary: DeliveryBoundary
    outcome: str
    resume_same_stream: bool
    replay_command: Literal[False]
    duplicate_starts: Literal[0]
    invalidate_environment: bool
    request_sandbox_termination: bool
    retain_reservation: bool
    surviving_admission_slots: int


def inject_process_loss(
    actor: FailureActor,
    boundary: DeliveryBoundary,
    *,
    both_noise_peers_survive: bool = True,
    provider_recovery_is_replay_safe: bool = False,
) -> RecoveryOutcome:
    """Return the conservative v1 result for one declared failure boundary."""
    if actor == "browser":
        return RecoveryOutcome(
            actor=actor,
            boundary=boundary,
            outcome="continue_and_replay_journal",
            resume_same_stream=True,
            replay_command=False,
            duplicate_starts=0,
            invalidate_environment=False,
            request_sandbox_termination=False,
            retain_reservation=False,
            surviving_admission_slots=32,
        )
    if actor in {"environment_socket", "rendezvous"} and both_noise_peers_survive:
        return RecoveryOutcome(
            actor=actor,
            boundary=boundary,
            outcome="resume_same_stream_by_operation_identity",
            resume_same_stream=True,
            replay_command=False,
            duplicate_starts=0,
            invalidate_environment=False,
            request_sandbox_termination=False,
            retain_reservation=boundary in {"after_acceptance", "during_execution"},
            surviving_admission_slots=32,
        )
    if actor == "pi_worker" and provider_recovery_is_replay_safe:
        return RecoveryOutcome(
            actor=actor,
            boundary=boundary,
            outcome="attach_replacement_worker",
            resume_same_stream=True,
            replay_command=False,
            duplicate_starts=0,
            invalidate_environment=False,
            request_sandbox_termination=False,
            retain_reservation=boundary in {"after_acceptance", "during_execution"},
            surviving_admission_slots=32,
        )
    if actor == "harness":
        return RecoveryOutcome(
            actor=actor,
            boundary=boundary,
            outcome="typed_transport_loss_and_contain",
            resume_same_stream=False,
            replay_command=False,
            duplicate_starts=0,
            invalidate_environment=True,
            request_sandbox_termination=True,
            retain_reservation=boundary != "before_delivery",
            surviving_admission_slots=32,
        )
    if actor == "environment_daemon":
        return RecoveryOutcome(
            actor=actor,
            boundary=boundary,
            outcome="typed_executor_loss_and_terminate",
            resume_same_stream=False,
            replay_command=False,
            duplicate_starts=0,
            invalidate_environment=True,
            request_sandbox_termination=True,
            retain_reservation=boundary != "before_delivery",
            surviving_admission_slots=31,
        )
    return RecoveryOutcome(
        actor=actor,
        boundary=boundary,
        outcome="typed_interrupted_turn",
        resume_same_stream=False,
        replay_command=False,
        duplicate_starts=0,
        invalidate_environment=actor == "environment_socket",
        request_sandbox_termination=actor == "environment_socket",
        retain_reservation=boundary != "before_delivery",
        surviving_admission_slots=32,
    )


@dataclass(frozen=True, slots=True)
class ReconnectPeer:
    peer_id: str
    lifecycle_class: LifecycleClass
    arrived_at_seconds: float = 0


@dataclass(frozen=True, slots=True)
class ScheduledReconnect:
    peer_id: str
    lifecycle_class: LifecycleClass
    started_at_seconds: float


class ReconnectScheduler:
    """Virtual-time 250/s scheduler with a 25% active-claim reservation."""

    def __init__(
        self,
        *,
        starts_per_second: int = 250,
        active_reservation_fraction: float = 0.25,
        shared_aging_seconds: float = 2.0,
    ) -> None:
        if starts_per_second != 250:
            raise ValueError("v1 requires exactly 250 authentication starts/second")
        if active_reservation_fraction < 0.25:
            raise ValueError("active reconnect reservation must be at least 25%")
        if not 0 < shared_aging_seconds <= 5:
            raise ValueError("shared aging bound is invalid")
        self.starts_per_second = starts_per_second
        self.active_reserved_per_second = math.ceil(
            starts_per_second * active_reservation_fraction
        )
        self.shared_aging_seconds = shared_aging_seconds

    def schedule(
        self, peers: tuple[ReconnectPeer, ...]
    ) -> tuple[ScheduledReconnect, ...]:
        if len({peer.peer_id for peer in peers}) != len(peers):
            raise ValueError("reconnect peer identities must be unique")
        queues = {
            lifecycle: deque(
                sorted(
                    (peer for peer in peers if peer.lifecycle_class == lifecycle),
                    key=lambda peer: (peer.arrived_at_seconds, peer.peer_id),
                )
            )
            for lifecycle in ("active_claim", "assigned_idle", "blank")
        }
        output: list[ScheduledReconnect] = []
        index = 0
        while any(queues.values()):
            second = index // self.starts_per_second
            slot_in_second = index % self.starts_per_second
            current = second + (slot_in_second + 1) / self.starts_per_second
            active_reserved = slot_in_second < self.active_reserved_per_second
            peer = self._next_peer(queues, current, active_reserved)
            if peer is None:
                # No contender has arrived yet. Advance one virtual slot without
                # creating an authentication start.
                index += 1
                continue
            output.append(
                ScheduledReconnect(
                    peer_id=peer.peer_id,
                    lifecycle_class=peer.lifecycle_class,
                    started_at_seconds=current,
                )
            )
            index += 1
        return tuple(output)

    def _next_peer(
        self,
        queues: dict[str, deque[ReconnectPeer]],
        now: float,
        active_reserved: bool,
    ) -> ReconnectPeer | None:
        eligible = {
            name: queue
            for name, queue in queues.items()
            if queue and queue[0].arrived_at_seconds <= now
        }
        if not eligible:
            return None
        if active_reserved and "active_claim" in eligible:
            return eligible["active_claim"].popleft()
        aged = [
            queue[0]
            for name, queue in eligible.items()
            if name != "active_claim"
            and now - queue[0].arrived_at_seconds >= self.shared_aging_seconds
        ]
        if aged:
            selected = min(
                aged, key=lambda peer: (peer.arrived_at_seconds, peer.peer_id)
            )
            return eligible[selected.lifecycle_class].popleft()
        for name in ("active_claim", "assigned_idle", "blank"):
            if name in eligible:
                return eligible[name].popleft()
        return None


def nearest_rank(values: tuple[float, ...], percentile: float) -> float:
    if not values or not 0 < percentile <= 1:
        raise ValueError("percentile input is invalid")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percentile) - 1]
