"""Worker-before-supervisor ordering and active-session replacement guards."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle


def test_lifecycle_starts_worker_before_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    events: list[object] = []
    monkeypatch.setattr(
        lifecycle,
        "sync_worker_environment",
        lambda environment: events.append(("sync", environment)),
    )

    def run(command, **_kwargs):
        events.append(command)
        if command[:2] == ["systemctl", "show"]:
            return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    lifecycle.start_slot("staging", "blue")

    assert events == [
        ("sync", "staging"),
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        [
            "systemctl",
            "start",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        ["systemctl", "start", "paperswithcode-staging-external-pi@blue.service"],
    ]


def test_lifecycle_restarts_exact_zero_session_worker_before_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
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
        if command[:2] == ["systemctl", "stop"]:
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
                    "instance_id": "00000000-0000-0000-0000-000000000001",
                    "release_id": "older-release-staging",
                    "state": "draining",
                    "active_sessions": 0,
                    "maximum_sessions": 32,
                    "worker_generation": 7,
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
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    lifecycle.start_slot("staging", "blue")

    stop = [
        "systemctl",
        "stop",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ]
    start = [
        "systemctl",
        "start",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ]
    assert commands.index(stop) < commands.index(start)


@pytest.mark.parametrize(
    ("worker_state", "active_sessions"),
    (("draining", 0.0), ("ready", 0)),
)
def test_lifecycle_refuses_ambiguous_active_session_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_state: str,
    active_sessions: object,
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            if command[-1] == "paperswithcode-staging-external-pi@blue.service":
                return subprocess.CompletedProcess(command, 0, stdout="inactive\n")
            return subprocess.CompletedProcess(command, 0, stdout="active\n")
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
                    "release_id": "older-release-staging",
                    "state": worker_state,
                    "active_sessions": active_sessions,
                    "maximum_sessions": 32,
                }
            ).encode()

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="not proven safe to restart"
    ):
        lifecycle.start_slot("staging", "blue")

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)


def test_lifecycle_refuses_worker_replacement_while_supervisor_is_active(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    monkeypatch.setattr(lifecycle, "sync_worker_environment", lambda _environment: None)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            return subprocess.CompletedProcess(command, 0, stdout="active\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(
        lifecycle.ExternalPiSlotError, match="supervisor is still active"
    ):
        lifecycle.start_slot("staging", "blue")

    assert not any(command[:2] == ["systemctl", "stop"] for command in commands)


def test_lifecycle_bounds_active_worker_status_body(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle, "_worker_is_inactive", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "_supervisor_is_inactive", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle,
        "_protected_staging_values",
        lambda: {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "t" * 32},
    )
    read_sizes: list[int] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            read_sizes.append(size)
            return b"x" * size

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(lifecycle.ExternalPiSlotError, match="status is unavailable"):
        lifecycle._stop_proven_orphaned_worker_if_active("staging", "blue")

    assert read_sizes == [65_537, 65_537]
