#!/usr/bin/env python3
"""Run the frozen 1,000-peer issuer, nonce, scheduler, and Noise cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import psutil
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.loadtests.persistent_executor_feasibility import validate_manifest
from backend.loadtests.persistent_executor_recovery import (
    ReconnectPeer,
    ReconnectScheduler,
)
from backend.services.chat_executor_bootstrap import (
    BootstrapRejected,
    ExecutorBootstrapStateMachine,
    registration_proof_message,
)

OBSERVATIONS = 1000


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


def _authenticate_cohort() -> dict[str, object]:
    machine = ExecutorBootstrapStateMachine(
        issuer_private_key=Ed25519PrivateKey.generate(),
        clock=time.time,
    )
    tokens: dict[str, str] = {}
    peers = []
    for index in range(OBSERVATIONS):
        environment_id = f"protocol-peer-{index:04d}"
        credential = f"launch-{index:04d}-{os.urandom(8).hex()}"
        identity = Ed25519PrivateKey.generate()
        public_key = identity.public_key().public_bytes_raw()
        machine.provision(environment_id, 1, credential)
        machine.redeem_launch(
            environment_id=environment_id,
            generation=1,
            launch_credential=credential,
            identity_public_key=public_key,
            signature=identity.sign(
                registration_proof_message(
                    environment_id,
                    1,
                    credential,
                    public_key,
                )
            ),
        )
        token = machine.issue_reconnect_token(
            environment_id,
            1,
            shard_id="task0",
            shard_generation=1,
            lifecycle_class=(
                "active_claim"
                if index < 100
                else "assigned_idle"
                if index < 400
                else "blank"
            ),
        )
        tokens[environment_id] = token.encoded
        peers.append(
            ReconnectPeer(
                peer_id=environment_id,
                lifecycle_class=(
                    "active_claim"
                    if index < 100
                    else "assigned_idle"
                    if index < 400
                    else "blank"
                ),
            )
        )
    scheduled = ReconnectScheduler().schedule(tuple(peers))
    starts_per_second = Counter(int(item.started_at_seconds) for item in scheduled)
    admission_ms = []
    attempt_ids = set()
    for item in scheduled:
        started = time.monotonic()
        admission = machine.admit_reconnect(
            tokens[item.peer_id],
            expected_shard_id="task0",
            expected_shard_generation=1,
            scheduler_slot_acquired=True,
        )
        admission_ms.append((time.monotonic() - started) * 1000)
        if not admission.admitted or admission.attempt_id is None:
            raise RuntimeError("scheduled reconnect was not admitted")
        attempt_ids.add(admission.attempt_id)
    replay_rejected = False
    try:
        machine.admit_reconnect(
            tokens[scheduled[0].peer_id],
            expected_shard_id="task0",
            expected_shard_generation=1,
            scheduler_slot_acquired=True,
        )
    except BootstrapRejected:
        replay_rejected = True
    return {
        "observations": len(scheduled),
        "unique_attempts": len(attempt_ids),
        "starts_per_second_max": max(starts_per_second.values()),
        "scheduler_ready_p99_ms": scheduled[989].started_at_seconds * 1000,
        "admission_max_ms": max(admission_ms),
        "replay_rejected": replay_rejected,
    }


def _run_noise_cohort(binary: Path) -> tuple[dict[str, object], dict[str, object]]:
    process = subprocess.Popen(
        [str(binary), "--run", "1000", "250"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    monitored = psutil.Process(process.pid)
    host_cpu_max = 0.0
    mem_available_min = psutil.virtual_memory().available
    rss_max = 0
    fd_max = 0
    psutil.cpu_percent(interval=None)
    while process.poll() is None:
        host_cpu_max = max(host_cpu_max, psutil.cpu_percent(interval=0.1))
        mem_available_min = min(mem_available_min, psutil.virtual_memory().available)
        try:
            rss_max = max(rss_max, monitored.memory_info().rss)
            fd_max = max(fd_max, monitored.num_fds())
        except psutil.NoSuchProcess:
            break
    stdout, stderr = process.communicate(timeout=5)
    if process.returncode != 0:
        raise RuntimeError(f"protocol cohort failed: {stderr[-1000:]}")
    return (
        json.loads(stdout),
        {
            "host_cpu_percent_max": host_cpu_max,
            "mem_available_mib_min": mem_available_min // (1024 * 1024),
            "process_rss_mib_max": rss_max / (1024 * 1024),
            "process_fd_max": fd_max,
        },
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if _source_commit(args.worktree) != manifest.source_commit:
        raise ValueError("manifest source commit does not match HEAD")
    if args.output.exists():
        raise ValueError("refusing to overwrite existing qualification evidence")
    authentication = _authenticate_cohort()
    noise, resources = _run_noise_cohort(args.binary)
    profile = next(
        profile
        for profile in manifest.profiles
        if profile.name == "reconnect_protocol_peers"
    )
    passed = (
        authentication["observations"] == OBSERVATIONS
        and authentication["unique_attempts"] == OBSERVATIONS
        and authentication["starts_per_second_max"] <= 250
        and authentication["replay_rejected"] is True
        and noise["observations"] == OBSERVATIONS
        and noise["starts_per_second_max"] <= 250
        and noise["ready_p95_ms"] <= profile.p95_target_ms
        and noise["ready_p99_ms"] <= profile.p99_target_ms
        and resources["host_cpu_percent_max"]
        < manifest.resource_limits.host_cpu_percent_exclusive_max
        and resources["mem_available_mib_min"]
        >= manifest.resource_limits.host_mem_available_mib_min
        and resources["process_rss_mib_max"]
        <= manifest.resource_limits.rendezvous_rss_mib_max
        and resources["process_fd_max"] <= manifest.resource_limits.process_fd_max
    )
    return {
        "schema_version": "persistent-executor-protocol-cohort-v1",
        "manifest_id": manifest.manifest_id,
        "source_commit": manifest.source_commit,
        "generated_at": _utc_now(),
        "binary_sha256": _sha256(args.binary),
        "authentication": authentication,
        "noise": noise,
        "resources": resources,
        "passed": passed,
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
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "noise"}, indent=2
        )
    )
    print(
        json.dumps(
            {
                "noise": {
                    key: value
                    for key, value in report["noise"].items()
                    if key != "ready_ms"
                }
            },
            indent=2,
        )
    )
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
