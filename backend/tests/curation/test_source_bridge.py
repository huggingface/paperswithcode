from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

import deploy.autonomous_cron_retry_bridge as retry_bridge
from deploy.autonomous_source_bridge import (
    BridgeError,
    cleanup_candidate,
    inspect_candidate,
    parse_request,
    prepare_candidate,
    publish_candidate,
)
from deploy.install_deploy_tools import (
    autonomous_cron_retry_wrapper,
    autonomous_source_wrapper,
    autonomous_sudoers,
)
from backend.services.autonomous_source_repair import (
    AutonomousSourceRepairService,
    RepairTarget,
)


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repositories(tmp_path):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    mirror = tmp_path / "mirror.git"
    source.mkdir()
    git(source, "init", "--initial-branch=main")
    git(source, "config", "user.name", "Test")
    git(source, "config", "user.email", "test@example.com")
    job = source / ".github" / "workflows" / "scripts" / "hourly" / "job.py"
    job.parent.mkdir(parents=True)
    job.write_text("VALUE = 1\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
    git(source, "remote", "add", "origin", str(remote))
    git(source, "push", "-u", "origin", "main")
    subprocess.run(["git", "clone", "--mirror", str(remote), str(mirror)], check=True)
    return remote, mirror


def test_closed_bridge_prepares_inspects_publishes_and_cleans(repositories, tmp_path):
    remote, mirror = repositories
    candidates = tmp_path / "candidates"
    state = tmp_path / "state"
    candidate_id = uuid.uuid4()
    run_id = uuid.uuid4()
    base = prepare_candidate(
        candidate_id,
        run_id,
        repository=mirror,
        candidates_root=candidates,
        state_root=state,
        owner="",
    )
    worktree = candidates / f"candidate-{candidate_id.hex}"
    target = worktree / ".github/workflows/scripts/hourly/job.py"
    target.write_text("VALUE = 2\n")
    inspected = inspect_candidate(
        candidate_id,
        run_id,
        repository=mirror,
        candidates_root=candidates,
        state_root=state,
    )
    assert inspected["base_sha"] == base
    assert inspected["changed_paths"] == [".github/workflows/scripts/hourly/job.py"]
    published = publish_candidate(
        candidate_id,
        run_id,
        "calculate_trending_scores",
        inspected["patch_digest"],
        repository=mirror,
        candidates_root=candidates,
        state_root=state,
    )
    assert git(remote, "rev-parse", "main") == published
    cleanup_candidate(
        candidate_id,
        run_id,
        repository=mirror,
        candidates_root=candidates,
        state_root=state,
    )
    assert not worktree.exists()
    assert not (state / f"{candidate_id}.json").exists()


def test_bridge_cli_rejects_generic_git_and_unscoped_publication():
    with pytest.raises(BridgeError):
        parse_request(["git", str(uuid.uuid4()), str(uuid.uuid4())])
    with pytest.raises(BridgeError):
        parse_request(
            ["publish", str(uuid.uuid4()), str(uuid.uuid4()), "bad'job", "x" * 64]
        )


def test_installed_wrapper_and_sudoers_keep_root_git_behind_closed_bridge():
    assert "autonomous_source_bridge.py" in autonomous_source_wrapper()
    sudoers = autonomous_sudoers()
    assert "pwc-cron ALL=(root) NOPASSWD" in sudoers
    assert "autonomous_source_bridge.py" in sudoers


def test_retry_bridge_accepts_only_exact_allowlisted_scope():
    run_id = uuid.uuid4()

    assert retry_bridge.parse_request([str(run_id), "calculate_trending_scores"]) == (
        run_id,
        "calculate_trending_scores",
    )
    with pytest.raises(retry_bridge.BridgeError):
        retry_bridge.parse_request([str(run_id), "autonomous_cron_health"])
    with pytest.raises(retry_bridge.BridgeError):
        retry_bridge.parse_request([str(run_id), "calculate_trending_scores", "extra"])


def test_retry_bridge_wrapper_and_sudoers_are_closed():
    wrapper = autonomous_cron_retry_wrapper()
    sudoers = autonomous_sudoers()

    assert "sudo -n" in wrapper
    assert "autonomous_cron_retry_bridge.py" in wrapper
    assert "pwc-cron ALL=(root) NOPASSWD" in sudoers
    assert "autonomous_cron_retry_bridge.py *" in sudoers


def test_production_mirror_automatically_uses_root_source_bridge(tmp_path):
    service = AutonomousSourceRepairService(
        repository=object(),
        source_repository=Path("/srv/paperswithcode/repository.git"),
        candidates_root=tmp_path,
        repair_targets={
            "job": RepairTarget(
                (".github/workflows/scripts/hourly/job.py",),
                ("backend/tests/test_autonomous_cron_operator.py",),
            )
        },
        min_free_bytes=0,
    )
    assert service.git_bridge_executable == "/usr/local/sbin/pwc-autonomous-source"
