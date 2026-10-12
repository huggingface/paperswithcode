import uuid

import pytest

from backend.scripts.run_external_pi_slot import (
    _lifecycle_completed,
    _status_update,
)
from backend.services.chat_external_pi_supervisor_runtime_service import (
    ExternalPiSupervisorRunResult,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim

CLAIM = ExternalWorkerClaim(
    "worker-1",
    uuid.UUID("10000000-0000-4000-8000-000000000001"),
    3,
    "release-a",
    "external-pi-v1",
)


def test_status_update_reports_a_lost_lease_as_a_fresh_start_bound_to_the_old_generation():
    assert _status_update("lease_lost", CLAIM, 4) == {
        "authenticated": True,
        "registered": False,
        "generation": 3,
        "heartbeats": 4,
        "state": "starting",
        "drained": False,
    }


@pytest.mark.parametrize(
    ("event", "state", "drained"),
    [
        ("registered", "ready", False),
        ("heartbeat", "ready", False),
        ("drained", "offline", True),
    ],
)
def test_status_update_keeps_the_registered_vocabulary(event, state, drained):
    update = _status_update(event, CLAIM, 1)
    assert update["registered"] is True
    assert update["state"] == state
    assert update["drained"] is drained
    assert update["generation"] == 3


def test_lifecycle_is_complete_after_a_drain_or_before_any_claim():
    assert _lifecycle_completed(ExternalPiSupervisorRunResult(2, 7, True)) is True
    assert _lifecycle_completed(ExternalPiSupervisorRunResult(0, 0, False)) is True


def test_a_stop_during_reregistration_is_reported_as_failed():
    # The worker is still bound to the lost claim and nothing drained it, so
    # the status file must not look like a never-registered fresh start.
    assert _lifecycle_completed(ExternalPiSupervisorRunResult(1, 7, False)) is False
