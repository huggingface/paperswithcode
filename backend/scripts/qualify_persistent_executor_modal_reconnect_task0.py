#!/usr/bin/env python3
"""Collect the frozen 32-peer real-Modal shared-stream reconnect cohort."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import modal
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.chat_sandbox_worker.contract import CHAT_SANDBOX_REGION, MODAL_APP_NAME
from backend.loadtests.persistent_executor_feasibility import (
    ExperimentBudget,
    nearest_rank,
    validate_manifest,
)
from backend.services.chat_executor_bootstrap import (
    ExecutorBootstrapStateMachine,
    registration_proof_message,
)

CONFIRMATION = "RUN_PWC_CHAT_STAGING_TASK0_MODAL_RECONNECT"
REMOTE_BINARY = "/usr/local/bin/pwc-executor-reconnect-fixture"
REMOTE_PORT = 8787
OBSERVATIONS = 32


@dataclass(frozen=True, slots=True)
class ReconnectSample:
    index: int
    sandbox_id: str | None
    authentication_ms: float
    network_reconnect_ms: float
    ready_ms: float
    same_noise_transport: bool
    authorization_bound: bool
    reservation_retained: bool
    error: str | None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit(worktree: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _registered_token(index: int) -> tuple[str, ExecutorBootstrapStateMachine]:
    machine = ExecutorBootstrapStateMachine(
        issuer_private_key=Ed25519PrivateKey.generate(),
        clock=time.time,
    )
    environment_id = f"modal-reconnect-{index:02d}"
    launch_credential = f"launch-{index:02d}-{os.urandom(16).hex()}"
    identity = Ed25519PrivateKey.generate()
    public_key = identity.public_key().public_bytes_raw()
    machine.provision(environment_id, 1, launch_credential)
    machine.redeem_launch(
        environment_id=environment_id,
        generation=1,
        launch_credential=launch_credential,
        identity_public_key=public_key,
        signature=identity.sign(
            registration_proof_message(
                environment_id,
                1,
                launch_credential,
                public_key,
            )
        ),
    )
    token = machine.issue_reconnect_token(
        environment_id,
        1,
        shard_id="task0",
        shard_generation=1,
        lifecycle_class="active_claim",
    )
    return token.encoded, machine


async def _sample(
    *,
    index: int,
    app: object,
    image: object,
    manifest: object,
    budget: ExperimentBudget,
    client_binary: Path,
) -> ReconnectSample:
    reservation_id = budget.reserve_sandbox()
    sandbox = None
    sandbox_id = None
    try:
        token, machine = _registered_token(index)
        sandbox = await modal.Sandbox.create.aio(
            REMOTE_BINARY,
            "server",
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
            unencrypted_ports=[REMOTE_PORT],
            include_oidc_identity_token=False,
            readiness_probe=modal.sandbox.Probe.with_tcp(REMOTE_PORT),
            tags={
                "service": "pwc-chat",
                "environment": "task0-feasibility",
                "purpose": "persistent-executor-task0-reconnect",
                "manifest": manifest.manifest_id,
            },
        )
        sandbox_id = sandbox.object_id
        tunnel = (await sandbox.tunnels.aio())[REMOTE_PORT]
        authentication_started = time.monotonic()
        admission = machine.admit_reconnect(
            token,
            expected_shard_id="task0",
            expected_shard_generation=1,
            scheduler_slot_acquired=True,
        )
        authentication_ms = (time.monotonic() - authentication_started) * 1000
        if not admission.admitted:
            raise RuntimeError("reconnect token was not admitted")
        process = await asyncio.create_subprocess_exec(
            str(client_binary),
            "client",
            tunnel.unencrypted_host,
            str(tunnel.unencrypted_port),
            token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        if process.returncode != 0:
            raise RuntimeError(f"reconnect client failed: {stderr[-500:]!r}")
        client = json.loads(stdout)
        network_ms = float(client["reconnect_ms"])
        await sandbox.poll.aio()
        await sandbox.terminate.aio(wait=True)
        sandbox = None
        budget.reconcile(reservation_id, actual_billed_seconds=None)
        return ReconnectSample(
            index=index,
            sandbox_id=sandbox_id,
            authentication_ms=authentication_ms,
            network_reconnect_ms=network_ms,
            ready_ms=authentication_ms + network_ms,
            same_noise_transport=bool(client["same_noise_transport"]),
            authorization_bound=bool(client["authorization_bound"]),
            reservation_retained=True,
            error=None,
        )
    except Exception as error:
        if sandbox is not None:
            try:
                await sandbox.terminate.aio(wait=True)
            except Exception:
                pass
        budget.reconcile(reservation_id, actual_billed_seconds=None)
        return ReconnectSample(
            index=index,
            sandbox_id=sandbox_id,
            authentication_ms=240_000,
            network_reconnect_ms=240_000,
            ready_ms=240_000,
            same_noise_transport=False,
            authorization_bound=False,
            reservation_retained=True,
            error=type(error).__name__,
        )


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": nearest_rank(values, 0.50),
        "p95_ms": nearest_rank(values, 0.95),
        "p99_ms": nearest_rank(values, 0.99),
        "max_ms": max(values),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if args.confirm != CONFIRMATION:
        raise ValueError(f"pass --confirm {CONFIRMATION}")
    if manifest.environment != "pwc-chat-staging":
        raise ValueError("Task 0 Modal qualification is staging-only")
    if manifest.modal_region != CHAT_SANDBOX_REGION:
        raise ValueError("manifest region differs from the application contract")
    if _source_commit(args.worktree) != manifest.source_commit:
        raise ValueError("manifest source commit does not match HEAD")
    if args.output.exists():
        raise ValueError("refusing to overwrite existing qualification evidence")
    profile = next(
        profile
        for profile in manifest.profiles
        if profile.name == "reconnect_real_modal"
    )
    if profile.observations != OBSERVATIONS:
        raise ValueError("real Modal reconnect cohort must contain 32 peers")
    if manifest.spend_limits.sandbox_create_max != OBSERVATIONS:
        raise ValueError("manifest must reserve exactly the remaining reconnect cohort")
    budget = ExperimentBudget(manifest.spend_limits)
    app = await modal.App.lookup.aio(
        MODAL_APP_NAME,
        create_if_missing=False,
        environment_name=manifest.environment,
    )
    image = (
        modal.Image.debian_slim()
        .add_local_file(args.server_binary, REMOTE_BINARY, copy=True)
        .run_commands(f"chmod 0555 {REMOTE_BINARY}")
    )
    await image.build.aio(app)
    samples = list(
        await asyncio.gather(
            *(
                _sample(
                    index=index,
                    app=app,
                    image=image,
                    manifest=manifest,
                    budget=budget,
                    client_binary=args.client_binary,
                )
                for index in range(OBSERVATIONS)
            )
        )
    )
    distribution = _distribution([sample.ready_ms for sample in samples])
    failures = sum(sample.error is not None for sample in samples)
    passed = (
        failures == 0
        and all(sample.same_noise_transport for sample in samples)
        and all(sample.authorization_bound for sample in samples)
        and distribution["p95_ms"] <= profile.p95_target_ms
        and distribution["p99_ms"] <= profile.p99_target_ms
    )
    return {
        "schema_version": "persistent-executor-modal-reconnect-v1",
        "manifest_id": manifest.manifest_id,
        "source_commit": manifest.source_commit,
        "generated_at": _utc_now(),
        "image_id": image.object_id,
        "server_binary_sha256": _sha256(args.server_binary),
        "client_binary_sha256": _sha256(args.client_binary),
        "authentication_starts_per_second_max": OBSERVATIONS,
        "results": {
            **distribution,
            "observations": len(samples),
            "failures": failures,
            "passed": passed,
        },
        "samples": [asdict(sample) for sample in samples],
        "reserved_microusd": budget.reserved_microusd,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--server-binary", type=Path, required=True)
    parser.add_argument("--client-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({"results": report["results"], "passed": report["passed"]}, indent=2)
    )
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
