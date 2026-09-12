#!/usr/bin/env python3
"""Kill actor-labelled OS processes while they hold a real Hybrid IK stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.loadtests.persistent_executor_feasibility import validate_manifest
from backend.loadtests.persistent_executor_recovery import inject_process_loss

ACTORS = ("peer", "rendezvous", "harness", "worker")
BOUNDARIES = (
    "before_delivery",
    "after_acceptance",
    "during_execution",
    "after_terminal_before_delivery",
)
ACTOR_MODEL = {
    "peer": "environment_daemon",
    "rendezvous": "rendezvous",
    "harness": "harness",
    "worker": "pi_worker",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_commit(worktree: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _wait_for_process_exit(pid: int, timeout_seconds: float = 2) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status = Path(f"/proc/{pid}/stat").read_text().split()[2]
        except (FileNotFoundError, ProcessLookupError):
            return True
        if status == "Z":
            return True
        time.sleep(0.01)
    return False


def _case(binary: Path, actor: str, boundary: str) -> dict[str, object]:
    process = subprocess.Popen(
        [str(binary), "--hold", actor, boundary],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    readable, _, _ = select.select([process.stdout], [], [], 5)
    if not readable:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
        raise RuntimeError(f"{actor}/{boundary} did not reach its loss boundary")
    marker = json.loads(process.stdout.readline())
    os.killpg(process.pid, signal.SIGKILL)
    return_code = process.wait(timeout=2)
    child_pid = marker.get("child_pid")
    child_contained = child_pid is None or _wait_for_process_exit(int(child_pid))
    model_actor = ACTOR_MODEL[actor]
    outcome = inject_process_loss(
        model_actor,  # type: ignore[arg-type]
        boundary,  # type: ignore[arg-type]
        both_noise_peers_survive=False,
    )
    expected_starts = (
        1
        if boundary
        in {
            "during_execution",
            "after_terminal_before_delivery",
        }
        else 0
    )
    passed = (
        marker["noise_handshake_complete"]
        and marker["encrypted_stream_active"]
        and marker["command_starts"] == expected_starts
        and return_code == -signal.SIGKILL
        and child_contained
        and outcome.replay_command is False
        and outcome.duplicate_starts == 0
    )
    return {
        "actor": actor,
        "model_actor": model_actor,
        "boundary": boundary,
        "noise_handshake_complete": marker["noise_handshake_complete"],
        "encrypted_stream_active": marker["encrypted_stream_active"],
        "command_starts": marker["command_starts"],
        "terminal_ciphertext_buffered": marker["terminal_ciphertext_buffered"],
        "process_return_code": return_code,
        "child_process_contained": child_contained,
        "outcome": outcome.outcome,
        "resume_same_stream": outcome.resume_same_stream,
        "replay_command": outcome.replay_command,
        "duplicate_starts": outcome.duplicate_starts,
        "invalidate_environment": outcome.invalidate_environment,
        "request_sandbox_termination": outcome.request_sandbox_termination,
        "retain_reservation": outcome.retain_reservation,
        "passed": passed,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if _source_commit(args.worktree) != manifest.source_commit:
        raise ValueError("manifest source commit does not match HEAD")
    if args.output.exists():
        raise ValueError("refusing to overwrite existing qualification evidence")
    cases = [
        _case(args.binary, actor, boundary)
        for actor in ACTORS
        for boundary in BOUNDARIES
    ]
    return {
        "schema_version": "persistent-executor-process-loss-v1",
        "manifest_id": manifest.manifest_id,
        "source_commit": manifest.source_commit,
        "generated_at": _utc_now(),
        "binary_sha256": _sha256(args.binary),
        "cases": cases,
        "observations": len(cases),
        "duplicate_starts": sum(int(case["duplicate_starts"]) for case in cases),
        "passed": all(bool(case["passed"]) for case in cases),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
