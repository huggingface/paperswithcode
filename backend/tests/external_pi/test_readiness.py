import asyncio
from datetime import UTC
from types import SimpleNamespace
import uuid

import pytest

from backend.config import Settings
from backend.services import chat_external_pi_readiness as readiness
from backend.services.chat_external_worker_registry import WorkerLeaseUnavailable


class SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return None


def _settings():
    return Settings(
        environment="staging",
        release_id="release-a",
        chat_external_pi_worker_id="worker-1",
        chat_external_pi_worker_url="http://127.0.0.1:8766",
        chat_external_pi_worker_token="s" * 32,
        chat_external_pi_worker_contract_version="external-pi-v1",
        chat_external_pi_worker_max_sessions=8,
    )


def _status(**changes):
    values = {
        "worker_id": "worker-1",
        "instance_id": uuid.uuid4(),
        "worker_generation": 3,
        "release_id": "release-a",
        "protocol": "external-pi-v1",
        "state": "ready",
        "active_sessions": 1,
        "maximum_sessions": 8,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_readiness_authenticates_endpoint_then_matches_exact_registry(monkeypatch):
    observed = []
    schema_checks = []
    status = _status()

    async def resolve(_client):
        return status

    def require(_repository, _db, **kwargs):
        observed.append(kwargs)

    monkeypatch.setattr(readiness.ExternalPiWorkerControlClient, "status", resolve)
    monkeypatch.setattr(
        readiness, "db_manager", SimpleNamespace(session_local=SessionContext)
    )
    monkeypatch.setattr(
        readiness.ChatExternalWorkerRepository, "require_endpoint_ready", require
    )
    monkeypatch.setattr(
        readiness,
        "validate_external_worker_reservation_schema",
        lambda db: schema_checks.append(db),
    )

    asyncio.run(readiness.validate_external_pi_readiness(_settings()))

    assert len(observed) == 1
    assert observed[0]["claim"].generation == 3
    assert observed[0]["active_sessions"] == 1
    assert observed[0]["configured_maximum_sessions"] == 8
    assert observed[0]["now"].tzinfo is UTC
    assert len(schema_checks) == 1


@pytest.mark.parametrize(
    "status",
    [
        _status(worker_generation=None),
        _status(release_id="wrong-release"),
        _status(protocol="wrong-contract"),
        _status(state="draining"),
        _status(active_sessions=8),
    ],
)
def test_readiness_rejects_endpoint_before_registry_match(monkeypatch, status):
    async def resolve(_client):
        return status

    monkeypatch.setattr(readiness.ExternalPiWorkerControlClient, "status", resolve)

    with pytest.raises(WorkerLeaseUnavailable, match="not ready"):
        asyncio.run(readiness.validate_external_pi_readiness(_settings()))
