#!/usr/bin/env python3
"""Run the decisive staging-only Task 0 disconnected-Stop probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import modal

from backend.chat_sandbox_worker.contract import CHAT_SANDBOX_REGION, MODAL_APP_NAME
from backend.loadtests.persistent_executor_feasibility import (
    ExperimentBudget,
    StopMeasurement,
    validate_manifest,
)

CONFIRMATION = "RUN_PWC_CHAT_STAGING_TASK0_STOP_PROBE"
REMOTE_BINARY = "/usr/local/bin/pwc-executor-environment"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_commit(worktree: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


async def run(args: argparse.Namespace) -> dict[str, object]:
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if args.confirm != CONFIRMATION:
        raise ValueError(f"pass --confirm {CONFIRMATION}")
    if manifest.environment != "pwc-chat-staging":
        raise ValueError("Task 0 Modal probes are staging-only")
    if manifest.modal_region != CHAT_SANDBOX_REGION:
        raise ValueError("manifest region differs from the application contract")
    if _source_commit(args.worktree) != manifest.source_commit:
        raise ValueError("manifest source commit does not match HEAD")
    binary_digest = _sha256(args.binary)
    if binary_digest != manifest.image_digest:
        raise ValueError("candidate binary differs from the frozen image digest")
    filesystem = os.statvfs(args.worktree)
    free_mib = filesystem.f_bavail * filesystem.f_frsize // (1024 * 1024)
    if free_mib < manifest.resource_limits.disk_free_mib_min:
        raise ValueError("host disk is below the frozen experiment floor")

    budget = ExperimentBudget(manifest.spend_limits)
    reservation_id = budget.reserve_sandbox()
    app = await modal.App.lookup.aio(
        MODAL_APP_NAME,
        create_if_missing=False,
        environment_name=manifest.environment,
    )
    image = (
        modal.Image.debian_slim()
        .add_local_file(args.binary, REMOTE_BINARY, copy=True)
        .run_commands(f"chmod 0555 {REMOTE_BINARY}")
    )
    image_build_started = time.monotonic()
    await image.build.aio(app)
    image_build_ms = (time.monotonic() - image_build_started) * 1000

    sandbox = None
    created_at = time.monotonic()
    try:
        sandbox = await modal.Sandbox.create.aio(
            "sleep",
            "infinity",
            app=app,
            image=image,
            region=manifest.modal_region,
            timeout=manifest.spend_limits.sandbox_lifetime_seconds_max,
            idle_timeout=manifest.spend_limits.sandbox_lifetime_seconds_max,
            cpu=0.5,
            memory=512,
            block_network=False,
            inbound_cidr_allowlist=[],
            encrypted_ports=[],
            unencrypted_ports=[],
            include_oidc_identity_token=False,
            readiness_probe=modal.sandbox.Probe.with_exec("test", "-x", REMOTE_BINARY),
            tags={
                "service": "pwc-chat",
                "environment": "task0-feasibility",
                "purpose": "persistent-executor-disconnected-stop",
                "manifest": manifest.manifest_id,
            },
        )
        process = await sandbox.exec.aio(REMOTE_BINARY, "--self-test", timeout=30)
        stdout, stderr = await asyncio.gather(
            process.stdout.read.aio(), process.stderr.read.aio()
        )
        await process.wait.aio()
        terminal_at = time.monotonic()
        if process.returncode != 0:
            raise RuntimeError(f"candidate self-test failed: {stderr[-1000:]}")
        candidate_report = json.loads(stdout)

        # This process represents work that cannot receive the explicit Stop
        # after its transport is partitioned. Modal termination is independent
        # containment, not executor observation of the Stop frame.
        await sandbox.exec.aio(
            "sh", "-c", "trap '' TERM; while :; do sleep 1; done", timeout=230
        )
        stop_committed_at = time.monotonic()
        await sandbox.terminate.aio(wait=True)
        termination_confirmed_at = time.monotonic()
        await sandbox.poll.aio()
        measurement = StopMeasurement(
            stop_committed_at=stop_committed_at,
            executor_observed_at=None,
            process_exit_confirmed_at=termination_confirmed_at,
            egress_revoked_at=termination_confirmed_at,
            sandbox_termination_confirmed_at=termination_confirmed_at,
        )
        sandbox = None
        budget.reconcile(reservation_id, actual_billed_seconds=None)
        return {
            "schema_version": "persistent-executor-modal-stop-probe-v1",
            "manifest_id": manifest.manifest_id,
            "source_commit": manifest.source_commit,
            "generated_at": _utc_now(),
            "environment": manifest.environment,
            "region": manifest.modal_region,
            "image_id": image.object_id,
            "binary_sha256": binary_digest,
            "image_build_ms": image_build_ms,
            "cold_first_pwd_ms": (terminal_at - created_at) * 1000,
            "candidate": candidate_report,
            "disconnected_stop": {
                "executor_observed": False,
                "delivery_ms": measurement.delivery_ms,
                "containment_ms": measurement.containment_ms,
                "sandbox_termination_confirmed": True,
                "reservation_retained": True,
                "passed": measurement.passed,
            },
            "stop_on_first_failed_gate": manifest.stop_on_first_failed_gate,
            "task0_may_proceed": measurement.passed,
            "reserved_microusd": budget.reserved_microusd,
        }
    finally:
        if sandbox is not None:
            await sandbox.terminate.aio(wait=True)
            budget.reconcile(reservation_id, actual_billed_seconds=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["task0_may_proceed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
