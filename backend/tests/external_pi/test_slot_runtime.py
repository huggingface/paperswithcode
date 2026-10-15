"""Slot runtime isolation, child environments, candidate evidence, and qualification budget."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle
from backend.config import Settings
from backend.services.chat_external_worker_capacity import external_worker_endpoints
from backend.services.runtime_validation import validate_external_pi_migration_policy
from backend.tests.external_pi.slot_harness import (
    _release,
)


@pytest.mark.parametrize(
    ("environment", "port", "worker_id"),
    (
        ("staging", 8766, "staging-blue"),
        ("production", 8776, "production-blue"),
    ),
)
def test_slot_runtime_is_environment_isolated_and_uses_recorded_immutable_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    port: int,
    worker_id: str,
):
    _release(tmp_path, "blue", environment=environment)
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "external_pi_runtime_manifest",
        lambda runtime, **expected: {
            "entry_point": "app/dist/src/external_http_main.js",
            "expected": expected,
        },
    )

    resolved = lifecycle.resolve_external_pi_slot(environment, "blue")

    assert resolved.port == port
    assert resolved.worker_id == worker_id
    assert resolved.release_id == "release-blue"
    assert resolved.runtime.name == "a" * 64
    assert resolved.node == resolved.runtime / "node/bin/node"
    expected_status = (
        lifecycle.STATUS_ROOT / "staging-blue.json"
        if environment == "staging"
        else lifecycle.PRODUCTION_STATUS_ROOT.with_name(
            f"{lifecycle.PRODUCTION_STATUS_ROOT.name}-blue"
        )
        / "status.json"
    )
    assert resolved.status_path == expected_status


def test_wrong_or_unrecorded_runtime_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = _release(tmp_path, "green")
    monkeypatch.setattr(lifecycle, "APP_ROOT", tmp_path)
    value = json.loads((release / "release.json").read_text())
    del value["external_pi_runtime"]
    (release / "release.json").write_text(json.dumps(value))

    with pytest.raises(ValueError, match="recorded external Pi runtime"):
        lifecycle.resolve_external_pi_slot("staging", "green")


def test_child_environments_are_strictly_scrubbed(tmp_path: Path):
    resolved = lifecycle.ExternalPiSlot(
        slot="green",
        port=8820,
        worker_id="staging-green-00",
        release=tmp_path / "release",
        release_id="release-green",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    protected = {
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
        "PWC_DB_HOST": "db",
        "PWC_DB_PORT": "5432",
        "PWC_DB_NAME": "pwc",
        "PWC_DB_USER": "staging",
        "PWC_DB_PASSWORD": "secret",
        "PWC_DB_SEARCH_PATH": "staging",
        "PWC_HF_TOKEN": "must-not-leak",
        "PWC_OPENAI_API_KEY": "must-not-leak",
        "MODAL_TOKEN_ID": "must-not-leak",
        "PWC_CHAT_SANDBOX_EXECUTOR_TOKEN": "must-not-leak",
        "PWC_EXTERNAL_PI_STATE_ROOT": "/run/paperswithcode/external-pi-green",
        "PATH": "/usr/bin",
    }

    node = lifecycle.node_environment(resolved, protected, instance_id="i" * 36)
    supervisor = lifecycle.supervisor_environment(resolved, protected)
    derived_token = lifecycle.replica_specs("staging", "green", "t" * 32)[0].token

    assert node == {
        "PWC_EXTERNAL_PI_HOST": "127.0.0.1",
        "PWC_EXTERNAL_PI_PORT": "8820",
        "PWC_EXTERNAL_PI_TOKEN": derived_token,
        "PWC_EXTERNAL_PI_MAX_SESSIONS": "4",
        "PWC_EXTERNAL_PI_WORKER_ID": "staging-green-00",
        "PWC_EXTERNAL_PI_INSTANCE_ID": "i" * 36,
        "PWC_EXTERNAL_PI_RELEASE_ID": "release-green",
        "PWC_EXTERNAL_PI_PROMPT_PATH": str(resolved.prompt),
        "PWC_EXTERNAL_PI_TOOL_NAMES": "[]",
        "PWC_CHAT_PWC_MCP_ENABLED": "false",
        "PWC_API_URL": "http://127.0.0.1:8011/api/v1",
        "PWC_EXTERNAL_PI_STATE_ROOT": (
            "/run/paperswithcode/external-pi-green/staging-green-00"
        ),
    }
    assert set(supervisor) == {
        "PWC_ENVIRONMENT",
        "PWC_RELEASE_ID",
        "PWC_DB_HOST",
        "PWC_DB_PORT",
        "PWC_DB_NAME",
        "PWC_DB_USER",
        "PWC_DB_PASSWORD",
        "PWC_DB_SEARCH_PATH",
        "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED",
        "PWC_CHAT_EXTERNAL_PI_WORKER_ID",
        "PWC_CHAT_EXTERNAL_PI_WORKER_URL",
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
        "PWC_CHAT_EXTERNAL_PI_WORKER_CONTRACT_VERSION",
        "PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS",
        "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS",
        "PWC_EXTERNAL_PI_STATUS_PATH",
        "PWC_EXTERNAL_PI_WORKER_ID",
    }
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_URL"] == "http://127.0.0.1:8820"
    assert supervisor["PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS"] == "4"
    assert "PWC_HF_TOKEN" not in supervisor


@pytest.mark.parametrize(("slot", "port"), (("blue", 8820), ("green", 8824)))
def test_supervisor_child_settings_resolve_complete_slot_worker_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slot: str, port: int
):
    worker_id = f"staging-{slot}-00"
    resolved = lifecycle.ExternalPiSlot(
        slot=slot,
        port=port,
        worker_id=worker_id,
        release=tmp_path / "release",
        release_id=f"release-{slot}",
        runtime=tmp_path / "runtime",
        node=tmp_path / "runtime/node/bin/node",
        entry_point=tmp_path / "runtime/dist/src/external_http_main.js",
        prompt=tmp_path / "runtime/assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    child_environment = lifecycle.supervisor_environment(
        resolved,
        {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )

    assert child_environment["PWC_CHAT_EXTERNAL_PI_WORKER_ID"] == worker_id

    with monkeypatch.context() as scoped:
        for key in tuple(os.environ):
            if key.startswith("PWC_CHAT_EXTERNAL_PI_WORKER_"):
                scoped.delenv(key)
        for key, value in child_environment.items():
            scoped.setenv(key, value)
        settings = Settings(_env_file=None)

    validate_external_pi_migration_policy(settings)
    (endpoint,) = external_worker_endpoints(settings)
    assert endpoint.endpoint_id == "legacy"
    assert endpoint.worker_id == worker_id
    assert endpoint.base_url == f"http://127.0.0.1:{port}"
    assert endpoint.token == lifecycle.replica_specs("staging", slot, "t" * 32)[0].token


def test_candidate_requires_authenticated_durable_lifecycle_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    statuses = []
    for spec in lifecycle.replica_specs("staging", "blue", "x" * 32):
        status = tmp_path / f"{spec.worker_id}.json"
        status.write_text(
            json.dumps(
                {
                    "release_id": "release-blue",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "authenticated": True,
                    "registered": True,
                    "generation": 3,
                    "heartbeats": 1,
                }
            )
        )
        statuses.append(status)

    assert lifecycle.qualify_candidate("staging", "blue", "release-blue") == 3
    value = json.loads(statuses[0].read_text())
    value["authenticated"] = False
    statuses[0].write_text(json.dumps(value))
    with pytest.raises(lifecycle.ExternalPiSlotError, match="qualification"):
        lifecycle.qualify_candidate(
            "staging", "blue", "release-blue", timeout_seconds=0.01
        )


def test_qualification_budget_covers_the_supervisor_startup_and_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
):
    # A supervisor may use its whole startup timeout to register and then a
    # further heartbeat interval before the first heartbeat is recorded. The
    # previous fixed 65s ceiling was below that 70s worst case, so a loaded
    # host failed qualification with registered=True and heartbeats=0.
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "60",
            "PWC_CHAT_EXTERNAL_PI_HEARTBEAT_SECONDS": "10",
        },
    )
    budget = lifecycle.protected_qualification_timeout_seconds("staging")

    assert budget > 60 + 10
    assert budget == 60 + 2 * 10 + lifecycle.QUALIFICATION_MARGIN_SECONDS


def test_qualification_budget_rejects_out_of_bounds_configuration(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "not-a-number",
        },
    )
    with pytest.raises(ValueError, match="must be numeric"):
        lifecycle.protected_qualification_timeout_seconds("staging")

    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda environment: {
            "PWC_CHAT_EXTERNAL_PI_STARTUP_TIMEOUT_SECONDS": "900",
        },
    )
    with pytest.raises(ValueError, match="protected bounds"):
        lifecycle.protected_qualification_timeout_seconds("staging")


def test_qualification_proves_drain_and_restart_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple] = []
    generations = iter([4, 5])
    monkeypatch.setattr(
        lifecycle, "start_slot", lambda environment, slot: calls.append(("start", slot))
    )
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda environment, slot, release_id: next(generations),
    )
    monkeypatch.setattr(
        lifecycle,
        "stop_slot",
        lambda environment, slot, release_id, **kwargs: calls.append(("stop", slot)),
    )

    assert lifecycle.prepare_candidate("staging", "green", "release-green") == 5
    assert calls == [("start", "green"), ("stop", "green"), ("start", "green")]
