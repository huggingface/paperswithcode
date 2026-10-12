import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services.chat_external_pi_shadow import ExternalPiWorkerStatus
from backend.services.chat_external_pi_supervisor import (
    ChatExternalPiSupervisor,
    ExternalPiWorkerDrainIncomplete,
    ExternalPiWorkerMismatch,
)
from backend.services.chat_external_worker_registry import ExternalWorkerClaim
from backend.services.chat_external_worker_registry import StaleWorkerClaim


def _status(**changes):
    values = {
        "protocol": "external-pi-v1",
        "worker_id": "worker-1",
        "instance_id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "release_id": "release-a",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": None,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }
    values.update(changes)
    return ExternalPiWorkerStatus(**values)


def test_supervisor_registers_only_the_expected_worker_contract():
    client = Mock(
        status=AsyncMock(return_value=_status()),
        bind_claim=AsyncMock(return_value=_status(worker_generation=3)),
    )
    repository = Mock()
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    repository.register.return_value = claim
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)

    registered = asyncio.run(supervisor.register(Mock(), now=now))

    assert registered == claim
    client.bind_claim.assert_awaited_once_with(3)
    assert repository.register.call_args.kwargs == {
        "worker_id": "worker-1",
        "instance_id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "release_id": "release-a",
        "contract_version": "external-pi-v1",
        "maximum_sessions": 8,
        "now": now,
        "lease_seconds": 15,
    }


def test_supervisor_rejects_release_or_capacity_mismatch_before_registration():
    client = Mock(status=AsyncMock(return_value=_status(release_id="release-b")))
    repository = Mock()
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    with pytest.raises(ExternalPiWorkerMismatch, match="identity or compatibility"):
        asyncio.run(
            supervisor.register(Mock(), now=datetime(2026, 8, 26, 12, tzinfo=UTC))
        )

    repository.register.assert_not_called()


def test_supervisor_drains_only_its_fenced_worker_and_finishes_at_zero():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    client = Mock(
        begin_drain=AsyncMock(
            return_value=_status(
                state="draining", active_sessions=2, worker_generation=3
            )
        ),
        status=AsyncMock(
            return_value=_status(
                state="draining", active_sessions=0, worker_generation=3
            )
        ),
    )
    repository = Mock()
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )
    db = Mock()
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)

    asyncio.run(supervisor.begin_drain(db, claim=claim, now=now))
    asyncio.run(supervisor.finish_drain(db, claim=claim, now=now))

    client.begin_drain.assert_awaited_once_with(3)
    repository.begin_drain.assert_called_once_with(
        db, claim=claim, now=now, drain_seconds=60
    )
    repository.require_ready_claim.assert_called_once_with(db, claim=claim, now=now)
    repository.heartbeat.assert_called_once_with(
        db, claim=claim, active_sessions=0, now=now, lease_seconds=15
    )
    repository.mark_offline.assert_called_once_with(db, claim=claim, now=now)


def test_stale_supervisor_cannot_mutate_the_remote_worker():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        2,
        "release-a",
        "external-pi-v1",
    )
    client = Mock(begin_drain=AsyncMock())
    repository = Mock()
    repository.require_ready_claim.side_effect = StaleWorkerClaim("fenced")
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    with pytest.raises(StaleWorkerClaim, match="fenced"):
        asyncio.run(
            supervisor.begin_drain(
                Mock(),
                claim=claim,
                now=datetime(2026, 8, 26, 12, tzinfo=UTC),
            )
        )

    client.begin_drain.assert_not_awaited()


def test_supervisor_reports_an_incomplete_drain_without_marking_offline():
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        3,
        "release-a",
        "external-pi-v1",
    )
    client = Mock(
        status=AsyncMock(
            return_value=_status(
                state="draining", active_sessions=1, worker_generation=3
            )
        )
    )
    repository = Mock()
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    with pytest.raises(ExternalPiWorkerDrainIncomplete):
        asyncio.run(
            supervisor.finish_drain(
                Mock(),
                claim=claim,
                now=datetime(2026, 8, 26, 12, tzinfo=UTC),
            )
        )

    repository.mark_offline.assert_not_called()


def test_supervisor_reclaims_an_idle_drained_worker_after_restart():
    # A drained worker never returns to "ready" on its own, so refusing to
    # register one turned a single supervisor restart into a permanent crash
    # loop that systemd could not escape.
    client = Mock(
        status=AsyncMock(return_value=_status(state="draining", worker_generation=3)),
        bind_claim=AsyncMock(return_value=_status(state="ready", worker_generation=4)),
    )
    repository = Mock()
    claim = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        4,
        "release-a",
        "external-pi-v1",
    )
    repository.register.return_value = claim
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    registered = asyncio.run(
        supervisor.register(Mock(), now=datetime(2026, 8, 26, 12, tzinfo=UTC))
    )

    assert registered == claim
    client.bind_claim.assert_awaited_once_with(4)


def test_supervisor_refuses_a_drained_worker_that_still_owns_sessions():
    client = Mock(
        status=AsyncMock(
            return_value=_status(
                state="draining", active_sessions=1, worker_generation=3
            )
        ),
        bind_claim=AsyncMock(),
    )
    repository = Mock()
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    with pytest.raises(ExternalPiWorkerMismatch, match="identity or compatibility"):
        asyncio.run(
            supervisor.register(Mock(), now=datetime(2026, 8, 26, 12, tzinfo=UTC))
        )

    repository.register.assert_not_called()
    client.bind_claim.assert_not_awaited()


def test_supervisor_requires_the_reclaimed_worker_to_report_ready():
    client = Mock(
        status=AsyncMock(return_value=_status(state="draining", worker_generation=3)),
        bind_claim=AsyncMock(
            return_value=_status(state="draining", worker_generation=4)
        ),
    )
    repository = Mock()
    repository.register.return_value = ExternalWorkerClaim(
        "worker-1",
        uuid.UUID("10000000-0000-4000-8000-000000000001"),
        4,
        "release-a",
        "external-pi-v1",
    )
    supervisor = ChatExternalPiSupervisor(
        client=client,
        repository=repository,
        expected_release_id="release-a",
        expected_contract_version="external-pi-v1",
        expected_maximum_sessions=8,
    )

    with pytest.raises(ExternalPiWorkerMismatch, match="identity or compatibility"):
        asyncio.run(
            supervisor.register(Mock(), now=datetime(2026, 8, 26, 12, tzinfo=UTC))
        )
