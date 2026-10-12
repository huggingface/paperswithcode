"""Slot stop and candidate cleanup require durable drain proof."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.external_pi_slot_lifecycle as lifecycle


def test_stop_without_durable_drain_evidence_leaves_worker_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-blue.json").write_text(
        json.dumps(
            {
                "release_id": "release-blue",
                "worker_id": "staging-blue",
                "state": "ready",
                "registered": True,
                "generation": 3,
            }
        )
    )
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "blue", "release-blue")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@blue.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@blue.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@blue.service",
        ],
    ]


def test_failed_worker_unit_is_not_treated_as_a_running_orphan(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="failed\n"),
    )

    assert lifecycle._worker_is_inactive("staging", "blue") is True


@pytest.mark.parametrize(
    "contents",
    [
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=4\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=301\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=sixty\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=0\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=6\n",
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=nan\n",
    ],
)
def test_drain_stop_timeout_rejects_invalid_protected_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
):
    (tmp_path / "staging.env").write_text(contents)
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)

    with pytest.raises(ValueError, match="drain"):
        lifecycle.drain_stop_timeout_seconds("staging")


def test_candidate_failure_before_registration_stops_worker_after_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_DRAIN_SECONDS=300\n"
        "PWC_CHAT_EXTERNAL_PI_DRAIN_POLL_SECONDS=5\n"
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    (tmp_path / "staging-green.json").write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "starting",
                "registered": False,
                "generation": None,
            }
        )
    )
    commands: list[tuple[list[str], bool, float | None]] = []
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )

    def successful_stop(command, *, check, timeout=None):
        commands.append((command, check, timeout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", successful_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate unavailable"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        (
            ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
            True,
            315,
        ),
        (
            [
                "systemctl",
                "stop",
                "paperswithcode-staging-external-pi-worker@green.service",
            ],
            True,
            None,
        ),
    ]


def test_candidate_failure_stops_registered_worker_after_durable_offline_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text("")
    status = tmp_path / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "ready",
                "registered": True,
                "generation": 4,
            }
        )
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def stop(command, **_kwargs):
        commands.append(command)
        if "external-pi@" in command[-1]:
            status.write_text(
                json.dumps(
                    {
                        "release_id": "release-green",
                        "worker_id": "staging-green",
                        "state": "offline",
                        "registered": False,
                        "generation": 4,
                        "drained": True,
                    }
                )
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate unavailable"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "stop",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


@pytest.mark.parametrize("post_stop_state", [None, "ready", "failed"])
def test_candidate_failure_without_durable_drain_proof_leaves_worker_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    post_stop_state: str | None,
):
    (tmp_path / "staging.env").write_text("")
    status = tmp_path / "staging-green.json"
    status.write_text(
        json.dumps(
            {
                "release_id": "release-green",
                "worker_id": "staging-green",
                "state": "ready",
                "registered": True,
                "generation": 4,
            }
        )
    )
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def successful_stop(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        if "external-pi@" in command[-1]:
            if post_stop_state is None:
                status.unlink()
            else:
                status.write_text(
                    json.dumps(
                        {
                            "release_id": "release-green",
                            "worker_id": "staging-green",
                            "state": post_stop_state,
                            "registered": True,
                            "generation": 4,
                        }
                    )
                )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", successful_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@green.service",
        ],
    ]


def test_candidate_cleanup_leaves_worker_running_if_supervisor_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "staging.env").write_text("")
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "start_slot", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "qualify_candidate",
        lambda *_args: (_ for _ in ()).throw(
            lifecycle.ExternalPiSlotError("candidate unavailable")
        ),
    )
    commands: list[list[str]] = []

    def failed_stop(command, **_kwargs):
        commands.append(command)
        raise lifecycle.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(lifecycle.subprocess, "run", failed_stop)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="candidate cleanup failed"):
        lifecycle.prepare_candidate("staging", "green", "release-green")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"]
    ]


@pytest.mark.parametrize(
    "status_value",
    [
        None,
        "not-json",
        {
            "release_id": "new-candidate",
            "worker_id": "staging-green",
            "state": "starting",
            "registered": False,
        },
        {
            "release_id": "new-candidate",
            "worker_id": "staging-blue",
            "state": "offline",
            "drained": True,
        },
        {
            "release_id": "previous-release",
            "worker_id": "staging-green",
            "state": "offline",
            "drained": True,
        },
    ],
)
def test_stop_without_exact_status_proof_leaves_active_worker_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_value: dict | str | None,
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    if status_value is not None:
        (tmp_path / "staging-green.json").write_text(
            status_value if isinstance(status_value, str) else json.dumps(status_value)
        )
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "green", "new-candidate")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi@green.service",
        ],
    ]


def test_stop_without_status_proof_accepts_exact_inactive_worker_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="inactive\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    lifecycle.stop_slot("staging", "green", "new-candidate")

    assert commands == [
        ["systemctl", "stop", "paperswithcode-staging-external-pi@green.service"],
        [
            "systemctl",
            "show",
            "--property=ActiveState",
            "--value",
            "paperswithcode-staging-external-pi-worker@green.service",
        ],
    ]


def test_missing_orphan_token_preserves_lifecycle_error_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "_protected_environment_values", lambda _env: {})

    def run(command, **_kwargs):
        if command[1] == "show":
            return SimpleNamespace(returncode=0, stdout="active\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle.subprocess, "run", run)

    with pytest.raises(lifecycle.ExternalPiSlotError, match="prove graceful drain"):
        lifecycle.stop_slot("staging", "green", "new-candidate")


def test_disabled_switch_is_a_complete_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = tmp_path / "staging.env"
    config.write_text("PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED=false\n")
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "prepare_candidate",
        lambda *_args: pytest.fail("disabled lifecycle started a service"),
    )

    assert not lifecycle.prepare_candidate_if_enabled("staging", "blue", "release")
    assert not lifecycle.stop_slot_if_enabled("staging", "blue", "release")
    assert not lifecycle.prepare_candidate_if_enabled("production", "blue", "release")
