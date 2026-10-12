"""Drain topology recovery across replica tiers and release cohorts."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle


def test_maximum_configured_drain_can_finish_and_releases_durable_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    status_root = tmp_path / "status"
    status_root.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", status_root)
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", config)
    status = status_root / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "state": "ready",
                "drained": False,
            }
        )
    )
    seen: dict[str, float] = {}

    commands: list[list[str]] = []

    def stop(command, *, check, timeout=None):
        assert check is True
        commands.append(command)
        if "external-pi@" in command[-1]:
            seen["timeout"] = timeout
            status.write_text(
                json.dumps(
                    {
                        "release_id": "release-green",
                        "worker_id": "staging-green",
                        "state": "offline",
                        "drained": True,
                    }
                )
            )

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    lifecycle.stop_slot("staging", "green", "release-green")

    assert seen["timeout"] == 315
    assert lifecycle.slot_status("staging", "green") == {
        "release_id": "release-green",
        "worker_id": "staging-green",
        "state": "offline",
        "drained": True,
    }
    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


def test_eight_replica_tooling_drains_previous_sixteen_replica_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "drain_stop_timeout_seconds", lambda _env: 10)
    old_specs = lifecycle.replica_specs_for_topology(
        "staging",
        "green",
        "x" * 32,
        replica_count=16,
        maximum_sessions=2,
    )
    for spec in old_specs:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "old-release",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "drained": False,
                    "authenticated": True,
                    "registered": True,
                    "generation": 1,
                    "heartbeats": 1,
                    "maximum_sessions": 2,
                }
            )
        )
    commands: list[list[str]] = []

    def stop(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            state = "inactive" if "external-pi@" in command[-1] else "active"
            return SimpleNamespace(returncode=0, stdout=f"{state}\n")
        if "external-pi@" in command[-1]:
            for spec in old_specs:
                (tmp_path / f"{spec.worker_id}.json").write_text(
                    json.dumps(
                        {
                            "protocol": lifecycle.CONTRACT_VERSION,
                            "release_id": "old-release",
                            "worker_id": spec.worker_id,
                            "state": "offline",
                            "drained": True,
                            "authenticated": True,
                            "registered": True,
                            "generation": 1,
                            "heartbeats": 2,
                            "maximum_sessions": 2,
                        }
                    )
                )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    lifecycle.stop_slot("staging", "green", "old-release")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]
    assert all(
        (tmp_path / f"{spec.worker_id}.json").is_file() for spec in old_specs[:8]
    )
    assert all(
        not (tmp_path / f"{spec.worker_id}.json").exists() for spec in old_specs[8:]
    )


def test_supervisor_status_attests_contract_and_capacity():
    from backend.scripts.run_external_pi_slot import _initial_status

    status = _initial_status(
        SimpleNamespace(
            release_id="release-a",
            chat_external_pi_worker_contract_version="external-pi-v1",
            chat_external_pi_worker_max_sessions=4,
        ),
        "staging-blue-07",
    )

    assert status["protocol"] == "external-pi-v1"
    assert status["maximum_sessions"] == 4


def test_partial_sixteen_replica_status_retains_previous_drain_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for spec in current_specs[:8]:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "current-release",
                    "worker_id": spec.worker_id,
                    "state": "offline",
                    "drained": True,
                    "maximum_sessions": 2,
                }
            )
        )
    selected = lifecycle._draining_replica_specs(
        "staging", "green", "x" * 32, "current-release"
    )

    assert len(selected) == 16
    assert all(spec.maximum_sessions == 2 for spec in selected)


def test_authenticated_endpoints_recover_current_topology_without_status_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    token = "t" * 32
    current_specs = lifecycle.replica_specs("staging", "green", token)
    specs_by_port = {spec.port: spec for spec in current_specs}
    requests: list[urllib.request.Request] = []

    class Response:
        def __init__(self, spec):
            self.spec = spec

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "validated-previous-release",
                    "worker_id": self.spec.worker_id,
                    "state": "ready",
                    "maximum_sessions": self.spec.maximum_sessions,
                }
            ).encode()

    def open_status(request, **_kwargs):
        requests.append(request)
        port = int(urllib.parse.urlparse(request.full_url).port)
        spec = specs_by_port[port]
        assert request.get_header("Authorization") == f"Bearer {spec.token}"
        return Response(spec)

    monkeypatch.setattr(urllib.request, "urlopen", open_status)

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        token,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
        allow_endpoint_recovery=True,
    )

    assert selected == current_specs
    assert len(requests) == len(current_specs)


def test_validated_orphan_release_retains_current_drain_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for spec in current_specs:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "validated-previous-release",
                    "worker_id": spec.worker_id,
                    "state": "draining",
                    "maximum_sessions": spec.maximum_sessions,
                }
            )
        )

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        "x" * 32,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
    )

    assert selected == current_specs


def test_mixed_trusted_release_cohort_falls_back_to_previous_drain_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    current_specs = lifecycle.replica_specs("staging", "green", "x" * 32)
    for index, spec in enumerate(current_specs):
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": (
                        "candidate-release"
                        if index < len(current_specs) // 2
                        else "validated-previous-release"
                    ),
                    "worker_id": spec.worker_id,
                    "state": "draining",
                    "maximum_sessions": spec.maximum_sessions,
                }
            )
        )

    selected = lifecycle._draining_replica_specs(
        "staging",
        "green",
        "x" * 32,
        "candidate-release",
        validated_release_ids=frozenset({"validated-previous-release"}),
    )

    assert len(selected) == lifecycle.PREVIOUS_REPLICA_COUNT
    assert all(
        spec.maximum_sessions == lifecycle.PREVIOUS_REPLICA_MAXIMUM_SESSIONS
        for spec in selected
    )


def test_start_checks_every_selected_previous_replica_before_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    specs = lifecycle.replica_specs_for_topology(
        "staging", "blue", "x" * 32, replica_count=16, maximum_sessions=2
    )
    authenticated_specs = lifecycle.replica_specs_for_topology(
        "staging", "blue", "t" * 32, replica_count=16, maximum_sessions=2
    )
    for spec in specs[:8]:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "old-release",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "maximum_sessions": 2,
                }
            )
        )
    specs_by_port = {spec.port: spec for spec in specs}
    authenticated_specs_by_port = {spec.port: spec for spec in authenticated_specs}
    calls = 0

    class Response:
        def __init__(self, spec):
            self.spec = spec

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "worker_id": self.spec.worker_id,
                    "release_id": "old-release",
                    "state": "ready",
                    "active_sessions": 1 if self.spec == specs[8] else 0,
                    "maximum_sessions": 2,
                    "worker_generation": None,
                    "operation_counters": {
                        name: 0 for name in lifecycle.OPERATION_COUNTER_NAMES
                    },
                }
            ).encode()

    def open_status(request, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.URLError("no legacy worker")
        port = int(urllib.parse.urlparse(request.full_url).port)
        assert request.get_header("Authorization") == (
            f"Bearer {authenticated_specs_by_port[port].token}"
        )
        return Response(specs_by_port[port])

    commands: list[list[str]] = []
    monkeypatch.setattr(urllib.request, "urlopen", open_status)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: (
            commands.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle.start_slot("staging", "blue")

    assert calls == 10
    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)
    assert all((tmp_path / f"{spec.worker_id}.json").is_file() for spec in specs[:8])
