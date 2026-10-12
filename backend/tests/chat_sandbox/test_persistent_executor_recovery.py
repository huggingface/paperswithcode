from __future__ import annotations

from collections import Counter

import pytest

from backend.loadtests.persistent_executor_recovery import (
    ReconnectPeer,
    ReconnectScheduler,
    inject_process_loss,
    nearest_rank,
)

BOUNDARIES = (
    "before_delivery",
    "after_acceptance",
    "during_execution",
    "after_terminal_before_delivery",
)
ACTORS = (
    "browser",
    "environment_socket",
    "rendezvous",
    "pi_worker",
    "harness",
    "environment_daemon",
)


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_process_loss_matrix_never_replays_uncertain_commands(
    actor: str, boundary: str
) -> None:
    outcome = inject_process_loss(actor, boundary)  # type: ignore[arg-type]

    assert outcome.replay_command is False
    assert outcome.duplicate_starts == 0
    if actor in {"harness", "environment_daemon"}:
        assert outcome.invalidate_environment
        assert outcome.request_sandbox_termination
        assert not outcome.resume_same_stream


@pytest.mark.parametrize("actor", ["environment_socket", "rendezvous"])
def test_socket_resume_requires_both_noise_peers(actor: str) -> None:
    resumable = inject_process_loss(
        actor,
        "during_execution",
        both_noise_peers_survive=True,  # type: ignore[arg-type]
    )
    lost_peer = inject_process_loss(
        actor,
        "during_execution",
        both_noise_peers_survive=False,  # type: ignore[arg-type]
    )

    assert resumable.resume_same_stream
    assert not lost_peer.resume_same_stream
    assert lost_peer.retain_reservation


def test_worker_loss_reports_capacity_separately_from_turn_outcome() -> None:
    recoverable = inject_process_loss(
        "pi_worker",
        "during_execution",
        provider_recovery_is_replay_safe=True,
    )
    unrecoverable = inject_process_loss("pi_worker", "during_execution")

    assert recoverable.outcome == "attach_replacement_worker"
    assert unrecoverable.outcome == "typed_interrupted_turn"
    assert recoverable.surviving_admission_slots == 32
    assert unrecoverable.surviving_admission_slots == 32


def test_environment_daemon_loss_reduces_environment_capacity() -> None:
    outcome = inject_process_loss("environment_daemon", "during_execution")

    assert outcome.surviving_admission_slots == 31
    assert outcome.retain_reservation


def test_one_thousand_peers_recover_within_rate_and_latency_gates() -> None:
    peers = tuple(
        ReconnectPeer(
            peer_id=f"peer-{index:04d}",
            lifecycle_class=(
                "active_claim"
                if index < 100
                else "assigned_idle"
                if index < 400
                else "blank"
            ),
        )
        for index in range(1000)
    )

    scheduled = ReconnectScheduler().schedule(peers)
    starts_per_second = Counter(int(item.started_at_seconds) for item in scheduled)

    assert len(scheduled) == 1000
    assert max(starts_per_second.values()) <= 250
    assert nearest_rank(tuple(item.started_at_seconds for item in scheduled), 0.99) <= 5
    assert max(item.started_at_seconds for item in scheduled) <= 5


def test_active_claims_receive_reserved_capacity_and_shared_lane_borrows() -> None:
    scheduler = ReconnectScheduler()
    active = tuple(
        ReconnectPeer(peer_id=f"active-{index:03d}", lifecycle_class="active_claim")
        for index in range(100)
    )
    assigned = tuple(
        ReconnectPeer(peer_id=f"assigned-{index:03d}", lifecycle_class="assigned_idle")
        for index in range(150)
    )

    first_second = scheduler.schedule(active + assigned)[:250]

    assert sum(item.lifecycle_class == "active_claim" for item in first_second) == 100
    assert sum(item.lifecycle_class == "assigned_idle" for item in first_second) == 150


def test_bounded_aging_prevents_blank_starvation() -> None:
    peers = tuple(
        [ReconnectPeer(peer_id="blank", lifecycle_class="blank")]
        + [
            ReconnectPeer(
                peer_id=f"active-{index:04d}",
                lifecycle_class="active_claim",
                arrived_at_seconds=index / 250,
            )
            for index in range(1000)
        ]
    )

    scheduled = ReconnectScheduler(shared_aging_seconds=2).schedule(peers)
    blank = next(item for item in scheduled if item.peer_id == "blank")

    assert blank.started_at_seconds <= 2.01
