"""Atomic pointer swaps and manual rollback guards."""

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


def test_rollback_without_an_active_slot_is_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # The fixed-port rollback re-synced the shared runtime as root; both
    # environments run blue/green slots, so that path is refused instead.
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
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: None)

    with pytest.raises(deploy_cli.DeployError, match="rollback is retired"):
        deploy_cli.rollback(Namespace(environment="staging", confirm=""))


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
