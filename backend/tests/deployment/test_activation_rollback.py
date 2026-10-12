"""Atomic pointer swaps, activation rollback, and runtime sync."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import deploy.cli as deploy_cli
from deploy.release import (
    atomic_symlink,
)


def test_atomic_symlink_replaces_pointer(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "current"
    atomic_symlink(first, link)
    atomic_symlink(second, link)
    assert link.resolve() == second


def test_activation_rollback_restores_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    failed = tmp_path / "failed"
    previous = tmp_path / "previous"
    failed.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(failed, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "log_event",
        lambda *_args, **_kwargs: events.append("logged"),
    )
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda *_args, **_kwargs: {"release_id": "previous"},
    )
    monkeypatch.setattr(deploy_cli, "wait_for_release", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *_args: None)

    deploy_cli.rollback_after_failed_activation(
        "staging", failed, previous_runtime_lock="old-lock"
    )

    assert (root / "current").resolve() == previous
    assert events[0] == ("restore", "old-lock")
    assert events[1] == [
        "systemctl",
        "restart",
        "paperswithcode-backend@staging.service",
    ]


def test_manual_rollback_syncs_target_runtime_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(current, root / "current")
    atomic_symlink(previous, root / "previous")
    events: list[object] = []

    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(deploy_cli, "require_root", lambda: None)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {"release_id": release.name},
    )
    monkeypatch.setattr(
        deploy_cli,
        "sync_runtime",
        lambda release: events.append(("sync", release)) or True,
    )
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: events.append(command)
    )
    monkeypatch.setattr(
        deploy_cli,
        "_read_json",
        lambda *_args, **_kwargs: {"release_id": "previous"},
    )
    monkeypatch.setattr(deploy_cli, "log_event", lambda *_args, **_kwargs: None)

    assert deploy_cli.rollback(Namespace(environment="staging", confirm="")) == 0
    assert events[:2] == [
        ("sync", previous),
        [
            "systemctl",
            "restart",
            "paperswithcode-backend@staging.service",
        ],
    ]


def test_manual_rollback_failed_sha_fence_rejects_changed_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment_root = tmp_path / "environments"
    root = environment_root / "staging"
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    root.mkdir(parents=True)
    atomic_symlink(current, root / "current")
    atomic_symlink(previous, root / "previous")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environment_root)
    monkeypatch.setattr(deploy_cli, "require_root", lambda: None)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: {
            "release_id": release.name,
            "git_sha": "c" * 40,
        },
    )

    with pytest.raises(deploy_cli.DeployError, match="target changed"):
        deploy_cli.rollback(
            Namespace(environment="staging", confirm="", failed_sha="b" * 40)
        )


def test_runtime_sync_failure_restores_previous_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events: list[object] = []

    def fail_sync(_release):
        events.append("sync")
        raise OSError("partial runtime mutation")

    monkeypatch.setattr(deploy_cli, "sync_runtime", fail_sync)
    monkeypatch.setattr(
        deploy_cli,
        "restore_runtime",
        lambda lock: events.append(("restore", lock)),
    )

    with pytest.raises(OSError, match="partial runtime"):
        deploy_cli.sync_runtime_with_recovery(tmp_path, "old-lock")

    assert events == ["sync", ("restore", "old-lock")]
