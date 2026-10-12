"""Lease-expiry restart transactions and drain timeouts."""

from __future__ import annotations

import json
import signal
import subprocess
from pathlib import Path

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle


def test_lease_expiry_restart_ignores_stale_status_until_generation_advances(
    monkeypatch: pytest.MonkeyPatch,
):
    statuses = iter(
        (
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 4,
                "heartbeats": 2,
            },
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "authenticated": True,
                "registered": True,
                "generation": 5,
                "heartbeats": 1,
            },
        )
    )
    commands = []
    sleeps = []
    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle, "_read_primary_status", lambda *_args: next(statuses)
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    assert (
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )
        == 5
    )
    assert commands == [
        [
            "systemctl",
            "kill",
            "--kill-whom=main",
            "--signal=KILL",
            "paperswithcode-staging-external-pi@blue.service",
        ],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi@blue.service",
        ],
        [
            "systemctl",
            "start",
            "paperswithcode-staging-external-pi@blue.service",
        ],
    ]
    assert sleeps == [31, 0.25]


def test_lease_expiry_transaction_masks_signals_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
):
    events = []

    def pthread_sigmask(operation, mask):
        events.append((operation, mask))
        return {signal.SIGHUP}

    def transaction(*_args):
        events.append("transaction")
        raise KeyboardInterrupt

    monkeypatch.setattr(lifecycle.signal, "pthread_sigmask", pthread_sigmask)
    monkeypatch.setattr(
        lifecycle, "_restart_supervisor_after_lease_expiry", transaction
    )

    with pytest.raises(KeyboardInterrupt):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert events == [
        (signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT}),
        "transaction",
        (signal.SIG_SETMASK, {signal.SIGHUP}),
    ]


def test_lease_expiry_interruption_recovers_claim_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []
    interrupted = False

    def sleep(seconds):
        nonlocal interrupted
        sleeps.append(seconds)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "ready",
            "authenticated": True,
            "registered": True,
            "generation": 5,
            "heartbeats": 1,
        },
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", sleep)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    with pytest.raises(KeyboardInterrupt):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert sleeps == [31, 31]
    assert commands[-1] == [
        "systemctl",
        "start",
        "paperswithcode-staging-external-pi@blue.service",
    ]


def test_lease_expiry_restart_failure_recovers_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    starts = 0

    def run(command, **_kwargs):
        nonlocal starts
        commands.append(command)
        if command[1] == "start":
            starts += 1
            if starts == 1:
                raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: {
            "release_id": "release-blue",
            "worker_id": "staging-blue",
            "state": "ready",
            "authenticated": True,
            "registered": True,
            "generation": 5,
            "heartbeats": 1,
        },
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == ["kill", "stop", "start", "start"]


def test_lease_expiry_unrecoverable_restart_stops_request_free_worker(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "start":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(
        lifecycle.ExternalPiSlotError,
        match="request-free qualification worker was stopped",
    ):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == [
        "kill",
        "stop",
        "start",
        "start",
        "stop",
        "stop",
    ]
    assert commands[-1][-1] == (
        "paperswithcode-staging-external-pi-worker@blue.service"
    )
    assert sleeps == [31, 31, 31]


def test_lease_expiry_status_failure_expires_fresh_recovery_lease_before_stop(
    monkeypatch: pytest.MonkeyPatch,
):
    commands = []
    sleeps = []
    monkeypatch.setattr(lifecycle, "protected_lease_seconds", lambda _env: 30)
    monkeypatch.setattr(
        lifecycle,
        "_read_primary_status",
        lambda *_args: (_ for _ in ()).throw(OSError("status write missing")),
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    with pytest.raises(
        lifecycle.ExternalPiSlotError,
        match="request-free qualification worker was stopped",
    ):
        lifecycle.restart_supervisor_after_lease_expiry(
            "staging", "blue", "release-blue", 4
        )

    assert [command[1] for command in commands] == [
        "kill",
        "stop",
        "start",
        "start",
        "stop",
        "stop",
    ]
    assert sleeps == [31, 31, 31]


def test_drain_timeout_fails_the_slot_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", config)
    (tmp_path / "staging-blue.json").write_text(
        json.dumps({"release_id": "release-blue", "state": "ready"})
    )
    seen: dict[str, float] = {}

    def timeout(*_args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        raise lifecycle.subprocess.TimeoutExpired("systemctl", kwargs["timeout"])

    monkeypatch.setattr(lifecycle.subprocess, "run", timeout)
    with pytest.raises(lifecycle.ExternalPiSlotError, match="drain timed out"):
        lifecycle.stop_slot("staging", "blue", "release-blue")
    assert seen["timeout"] == 315
