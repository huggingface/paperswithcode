"""Expired-lease and orphaned-worker proofs before stopping a slot."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle


def _install_active_worker_status(
    monkeypatch: pytest.MonkeyPatch, status: dict
) -> list[list[str]]:
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    monkeypatch.setattr(
        lifecycle,
        "_read_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "failed",
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    commands: list[list[str]] = []
    worker_active = True

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(
                command, 0, stdout="active\n" if worker_active else "inactive\n"
            )
        if command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(status).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    def open_status(request, *, timeout):
        assert request.full_url == "http://127.0.0.1:8766/v1/status"
        assert request.get_header("Authorization") == f"Bearer {'t' * 32}"
        assert timeout == 5
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_status)
    return commands


def _unclaimed_worker_status() -> dict:
    return {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 32,
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


def test_stale_failed_supervisor_proves_zero_use_bound_worker_is_expired(tmp_path):
    status_path = tmp_path / "staging-blue-00.json"
    status_path.write_text("{}")
    os.utime(status_path, (0, 0))
    counters = {
        "shadow_requests": 0,
        "model_calls": 0,
        "tool_calls": 0,
        "provider_calls": 0,
        "modal_calls": 0,
        "billing_events": 0,
    }
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 2,
        "worker_generation": 5,
        "operation_counters": counters,
    }
    durable = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "failed",
        "maximum_sessions": 2,
        "generation": 5,
    }

    assert lifecycle._stale_bound_worker_is_proven(
        endpoint,
        durable,
        status_path=status_path,
        trusted_release_ids=frozenset({"release-blue"}),
        lease_seconds=30,
        now=100,
    )
    assert not lifecycle._stale_bound_worker_is_proven(
        endpoint,
        durable,
        status_path=status_path,
        trusted_release_ids=frozenset({"release-blue"}),
        lease_seconds=30,
        now=20,
    )


def test_expired_database_lease_proves_zero_use_bound_worker_is_expired():
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 2,
        "worker_generation": 5,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    database_status = {
        "worker_id": "staging-blue-00",
        "release_id": "release-blue",
        "contract_version": "external-pi-v1",
        "generation": 5,
        "state": "ready",
        "maximum_sessions": 2,
        "active_sessions": 0,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"release-blue"}),
    )
    database_status["lease_expired"] = False
    assert not lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"release-blue"}),
    )


def test_expired_database_lease_proves_used_idle_worker_is_expired():
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "release_id": "old-release",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 4,
        "worker_generation": 5,
        "operation_counters": {
            "shadow_requests": 3,
            "model_calls": 3,
            "tool_calls": 2,
            "provider_calls": 3,
            "modal_calls": 2,
            "billing_events": 3,
        },
    }
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 5,
        "state": "ready",
        "maximum_sessions": 4,
        "active_sessions": 0,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._expired_database_worker_is_proven(
        endpoint,
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize("state", ("draining", "ready"))
def test_expired_database_lease_proves_stable_draining_turns_are_orphaned(state):
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": state,
        "active_sessions": 3,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 381,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 7,
        "state": state,
        "maximum_sessions": 4,
        "active_sessions": 3,
        "lease_expired": True,
        "reservation_free": True,
    }

    assert lifecycle._orphaned_draining_turns_are_proven(
        endpoint,
        endpoint.copy(),
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize(
    ("target", "field", "unsafe_value"),
    (
        ("first", "state", "offline"),
        ("second", "active_sessions", 2),
        ("second", "operation_counters", {"model_calls": 382}),
        ("database", "lease_expired", False),
        ("database", "reservation_free", False),
        ("database", "active_sessions", 2),
        ("database", "instance_id", "00000000-0000-0000-0000-000000000002"),
    ),
)
@pytest.mark.parametrize("state", ("draining", "ready"))
def test_orphaned_draining_turn_proof_rejects_live_or_changing_work(
    target: str,
    field: str,
    unsafe_value: object,
    state: str,
):
    endpoint = {
        "protocol": "external-pi-v1",
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": state,
        "active_sessions": 3,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 0,
            "model_calls": 381,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
    }
    first = endpoint.copy()
    second = endpoint.copy()
    database_status = {
        "worker_id": "production-blue-00",
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "contract_version": "external-pi-v1",
        "generation": 7,
        "state": state,
        "maximum_sessions": 4,
        "active_sessions": 3,
        "lease_expired": True,
        "reservation_free": True,
    }
    selected = {"first": first, "second": second, "database": database_status}
    selected[target][field] = unsafe_value

    assert not lifecycle._orphaned_draining_turns_are_proven(
        first,
        second,
        database_status,
        trusted_release_ids=frozenset({"old-release"}),
    )


@pytest.mark.parametrize("backend_inactive", (True, False))
@pytest.mark.parametrize("state", ("draining", "ready"))
def test_only_an_inactive_backend_allows_orphaned_draining_turns_to_stop(
    monkeypatch: pytest.MonkeyPatch,
    backend_inactive: bool,
    state: str,
):
    worker_active = True

    def worker_is_inactive(*_args):
        return not worker_active

    monkeypatch.setattr(lifecycle, "_worker_is_inactive", worker_is_inactive)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle, "_backend_slot_is_inactive", lambda *_args: backend_inactive
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {
            "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
        },
    )
    specs = lifecycle.replica_specs("production", "blue", "t" * 32)
    statuses = {
        spec.worker_id: {
            "protocol": "external-pi-v1",
            "worker_id": spec.worker_id,
            "instance_id": f"00000000-0000-0000-0000-{index:012d}",
            "release_id": "old-release",
            "state": state,
            "active_sessions": 3 if index == 0 else 0,
            "maximum_sessions": 4,
            "worker_generation": 7,
            "operation_counters": {
                "shadow_requests": 0,
                "model_calls": 381 if index == 0 else 0,
                "tool_calls": 0,
                "provider_calls": 0,
                "modal_calls": 0,
                "billing_events": 0,
            },
        }
        for index, spec in enumerate(specs)
    }
    database_statuses = {
        spec.worker_id: {
            "worker_id": spec.worker_id,
            "instance_id": statuses[spec.worker_id]["instance_id"],
            "release_id": "old-release",
            "contract_version": "external-pi-v1",
            "generation": 7,
            "state": state,
            "maximum_sessions": 4,
            "active_sessions": statuses[spec.worker_id]["active_sessions"],
            "lease_expired": True,
            "reservation_free": True,
        }
        for spec in specs
    }
    commands: list[list[str]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        lifecycle, "_worker_status", lambda spec: statuses[spec.worker_id].copy()
    )
    monkeypatch.setattr(
        lifecycle,
        "_read_database_worker_statuses",
        lambda *_args: database_statuses,
    )
    monkeypatch.setattr(lifecycle.time, "sleep", sleeps.append)

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "stop"]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    def invocation():
        lifecycle._stop_proven_orphaned_worker_if_active(
            "production",
            "blue",
            worker_active_proven=True,
            expected_release_id="old-release",
            draining_specs=specs,
            allow_orphaned_turn_reap=True,
        )

    if backend_inactive:
        invocation()
        assert commands == [
            [
                "systemctl",
                "stop",
                "paperswithcode-production-external-pi-worker@blue.service",
            ]
        ]
    else:
        with pytest.raises(
            lifecycle.ExternalPiSlotError, match="not proven safe to restart"
        ):
            invocation()
        assert commands == []
    assert sleeps == ([5] if backend_inactive else [])


def test_orphaned_draining_turns_are_reap_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "_backend_slot_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {
            "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32,
            "PWC_CHAT_EXTERNAL_PI_LEASE_SECONDS": "30",
        },
    )
    specs = lifecycle.replica_specs("production", "blue", "t" * 32)
    status = {
        "protocol": "external-pi-v1",
        "worker_id": specs[0].worker_id,
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "release_id": "old-release",
        "state": "draining",
        "active_sessions": 1,
        "maximum_sessions": 4,
        "worker_generation": 7,
        "operation_counters": {name: 0 for name in lifecycle.OPERATION_COUNTER_NAMES},
    }
    monkeypatch.setattr(lifecycle, "_worker_status", lambda _spec: status)

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle._stop_proven_orphaned_worker_if_active(
            "production",
            "blue",
            worker_active_proven=True,
            expected_release_id="old-release",
            draining_specs=specs,
        )


def test_stop_slot_cleans_exact_unclaimed_request_free_worker(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = _install_active_worker_status(monkeypatch, _unclaimed_worker_status())

    lifecycle.stop_slot("staging", "blue", "release-blue")

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands


def test_stop_slot_cleans_unclaimed_worker_from_validated_orphan_release(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    status["release_id"] = "validated-previous-release"
    commands = _install_active_worker_status(monkeypatch, status)

    lifecycle.stop_slot(
        "staging",
        "blue",
        "candidate-release",
        validated_orphan_release_ids=frozenset({"validated-previous-release"}),
    )

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("protocol", "external-pi-v2"),
        ("worker_id", "staging-green"),
        ("release_id", "other-release"),
        ("state", "starting"),
        ("worker_generation", 0),
        ("active_sessions", 0.0),
        ("active_sessions", 1),
        ("maximum_sessions", 32.0),
        ("maximum_sessions", 31),
    ),
)
def test_stop_slot_refuses_ambiguous_unclaimed_worker_identity_or_capacity(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    unsafe_value: object,
):
    status = _unclaimed_worker_status()
    status[field] = unsafe_value
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_refuses_unclaimed_worker_without_explicit_null_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    del status["worker_generation"]
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


@pytest.mark.parametrize(
    ("counter", "unsafe_value"),
    (
        ("shadow_requests", True),
        ("model_calls", 0.0),
        ("tool_calls", 1),
        ("provider_calls", 1),
        ("modal_calls", 1),
        ("billing_events", 1),
    ),
)
def test_stop_slot_refuses_unclaimed_worker_with_ambiguous_operation_evidence(
    monkeypatch: pytest.MonkeyPatch,
    counter: str,
    unsafe_value: object,
):
    status = _unclaimed_worker_status()
    status["operation_counters"][counter] = unsafe_value
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_refuses_unclaimed_worker_with_incomplete_operation_evidence(
    monkeypatch: pytest.MonkeyPatch,
):
    status = _unclaimed_worker_status()
    del status["operation_counters"]["billing_events"]
    commands = _install_active_worker_status(monkeypatch, status)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert not any(
        command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]
        for command in commands
    )


def test_stop_slot_cleans_exact_orphan_with_authenticated_zero_session_proof(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    monkeypatch.setattr(
        lifecycle,
        "_read_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "failed",
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    commands: list[list[str]] = []
    worker_active = True

    def run(command, **_kwargs):
        nonlocal worker_active
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(
                command, 0, stdout="active\n" if worker_active else "inactive\n"
            )
        if command[:2] == ["systemctl", "stop"] and "worker@" in command[-1]:
            worker_active = False
        return subprocess.CompletedProcess(command, 0)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": "external-pi-v1",
                    "worker_id": "staging-blue",
                    "state": "draining",
                    "active_sessions": 0,
                    "maximum_sessions": 32,
                }
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    lifecycle.stop_slot("staging", "blue", "release-blue")

    assert [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ] in commands
