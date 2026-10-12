import asyncio
from unittest.mock import Mock

import httpx
import pytest

from backend.config import Settings
from backend.scripts.run_external_pi_supervisor import (
    build_runtime,
    validate_supervisor_settings,
)


def _settings(**changes):
    values = {
        "environment": "staging",
        "release_id": "release-a",
        "chat_external_pi_supervisor_enabled": True,
        "chat_external_pi_worker_id": "external-pi-1",
        "chat_external_pi_worker_url": "http://127.0.0.1:8766",
        "chat_external_pi_worker_token": "s" * 32,
        "chat_external_pi_worker_contract_version": "external-pi-v1",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_supervisor_process_is_explicitly_enabled_for_deployed_environments():
    with pytest.raises(RuntimeError, match="not enabled"):
        validate_supervisor_settings(
            _settings(chat_external_pi_supervisor_enabled=False)
        )
    validate_supervisor_settings(_settings(environment="production"))
    with pytest.raises(RuntimeError, match="deployed environment"):
        validate_supervisor_settings(_settings(environment="development"))


def test_build_runtime_pins_the_release_contract_and_lifecycle_limits():
    settings = _settings()
    http = httpx.AsyncClient()
    wait_for_stop = Mock()
    try:
        runtime = build_runtime(
            settings,
            http=http,
            session_factory=Mock(),
            wait_for_stop=wait_for_stop,
        )
    finally:
        asyncio.run(http.aclose())

    assert runtime.supervisor.expected_release_id == "release-a"
    assert runtime.supervisor.expected_contract_version == "external-pi-v1"
    assert runtime.supervisor.expected_maximum_sessions == 8
    assert runtime.supervisor.lease_seconds == 30
    assert runtime.supervisor.drain_seconds == 60
    assert runtime.heartbeat_interval_seconds == 10
    assert runtime.startup_timeout_seconds == 60
    assert runtime.drain_poll_seconds == 1
    assert runtime.wait_for_stop is wait_for_stop
