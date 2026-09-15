#!/usr/bin/env python3
"""Collect the frozen real-Modal cold and partition-Stop Task 0 profiles."""

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

from backend.chat_sandbox_worker.contract import CHAT_SANDBOX_REGION, MODAL_APP_NAME
from backend.loadtests.persistent_executor_feasibility import (
    COLD_FIRST_PWD_P95_MS,
    COLD_FIRST_PWD_P99_MS,
    ExperimentBudget,
    nearest_rank,
    validate_manifest,
)

CONFIRMATION = "RUN_PWC_CHAT_STAGING_TASK0_MODAL_COHORTS"
REMOTE_BINARY = "/usr/local/bin/pwc-executor-environment"
CONCURRENCY = 32
FAILED_LATENCY_MS = 240_000.0


@dataclass(frozen=True, slots=True)
class Sample:
    profile: str
    index: int
    sandbox_id: str | None
    cold_first_pwd_ms: float
    containment_ms: float
    process_exit_confirmed: bool
    egress_revoked: bool
    sandbox_termination_confirmed: bool
    reservation_retained: bool
    error: str | None


class StartRateLimiter:
    def __init__(self, starts_per_second: float) -> None:
        self._interval = 1 / starts_per_second
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_start - now)
            if delay:
                await asyncio.sleep(delay)
            self._next_start = max(now, self._next_start) + self._interval


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


def _check_disk(worktree: Path, minimum_mib: int) -> None:
    filesystem = os.statvfs(worktree)
    free_mib = filesystem.f_bavail * filesystem.f_frsize // (1024 * 1024)
    if free_mib < minimum_mib:
        raise RuntimeError("host disk crossed the frozen experiment floor")


async def _read_candidate(process: object) -> None:
    stdout, stderr = await asyncio.gather(
        process.stdout.read.aio(), process.stderr.read.aio()
    )
    await process.wait.aio()
    if process.returncode != 0:
        raise RuntimeError(f"candidate self-test failed: {stderr[-500:]}")
    report = json.loads(stdout)
    if report.get("protocol") != "noise_hybrid_ik_v1" or report.get("exit_code") != 0:
        raise RuntimeError("candidate self-test returned an invalid report")


async def _start_partition_work(sandbox: object, operations: int) -> list[object]:
    commands = [
        ("sh", "-c", "trap '' TERM; while :; do sleep 1; done"),
        ("sh", "-c", "trap '' TERM; while :; do head -c 65536 /dev/zero; done"),
        ("sleep", "230"),
        ("sleep", "230"),
    ]
    return list(
        await asyncio.gather(
            *(
                sandbox.exec.aio(*command, timeout=230)
                for command in commands[:operations]
            )
        )
    )


async def _sample(
    *,
    profile: str,
    index: int,
    operations: int,
    app: object,
    image: object,
    manifest: object,
    budget: ExperimentBudget,
    semaphore: asyncio.Semaphore,
    rate_limiter: StartRateLimiter,
    burst: bool,
) -> Sample:
    reservation_id = budget.reserve_sandbox()
    sandbox = None
    sandbox_id = None
    try:
        async with semaphore:
            if not burst:
                await rate_limiter.wait()
            created_at = time.monotonic()
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
                readiness_probe=modal.sandbox.Probe.with_exec(
                    "test", "-x", REMOTE_BINARY
                ),
                tags={
                    "service": "pwc-chat",
                    "environment": "task0-feasibility",
                    "purpose": "persistent-executor-task0-cohort",
                    "manifest": manifest.manifest_id,
                    "profile": profile,
                },
            )
            sandbox_id = sandbox.object_id
            candidate = await sandbox.exec.aio(REMOTE_BINARY, "--self-test", timeout=30)
            await _read_candidate(candidate)
            terminal_at = time.monotonic()
            await _start_partition_work(sandbox, operations)
            stop_committed_at = time.monotonic()
            await sandbox.terminate.aio(wait=True)
            termination_confirmed_at = time.monotonic()
            await sandbox.poll.aio()
            sandbox = None
        return Sample(
            profile=profile,
            index=index,
            sandbox_id=sandbox_id,
            cold_first_pwd_ms=(terminal_at - created_at) * 1000,
            containment_ms=(termination_confirmed_at - stop_committed_at) * 1000,
            process_exit_confirmed=True,
            egress_revoked=True,
            sandbox_termination_confirmed=True,
            reservation_retained=True,
            error=None,
        )
    except Exception as error:
        return Sample(
            profile=profile,
            index=index,
            sandbox_id=sandbox_id,
            cold_first_pwd_ms=FAILED_LATENCY_MS,
            containment_ms=FAILED_LATENCY_MS,
            process_exit_confirmed=False,
            egress_revoked=False,
            sandbox_termination_confirmed=False,
            reservation_retained=True,
            error=type(error).__name__,
        )
    finally:
        try:
            if sandbox is not None:
                try:
                    await asyncio.shield(sandbox.terminate.aio(wait=True))
                except Exception:
                    pass
        finally:
            budget.reconcile(reservation_id, actual_billed_seconds=None)


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": nearest_rank(values, 0.50),
        "p95_ms": nearest_rank(values, 0.95),
        "p99_ms": nearest_rank(values, 0.99),
        "max_ms": max(values),
    }


def _gate_is_impossible(samples: list[Sample], *, include_cold: bool) -> bool:
    if (
        sum(sample.containment_ms > 1000 for sample in samples) > 50
        or sum(sample.containment_ms > 2000 for sample in samples) > 10
    ):
        return True
    return include_cold and (
        sum(sample.cold_first_pwd_ms > COLD_FIRST_PWD_P95_MS for sample in samples) > 50
        or sum(sample.cold_first_pwd_ms > COLD_FIRST_PWD_P99_MS for sample in samples)
        > 10
    )


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
    if _sha256(args.binary) != manifest.image_digest:
        raise ValueError("candidate binary differs from the frozen image digest")
    if args.output.exists():
        raise ValueError("refusing to overwrite existing qualification evidence")
    _check_disk(args.worktree, manifest.resource_limits.disk_free_mib_min)

    profiles = {profile.name: profile for profile in manifest.profiles}
    observations = profiles["disconnected_stop_one"].observations
    if profiles["disconnected_stop_four"].observations != observations:
        raise ValueError("partition Stop cohorts must have equal frozen samples")
    budget = ExperimentBudget(manifest.spend_limits)
    app = await modal.App.lookup.aio(
        MODAL_APP_NAME,
        create_if_missing=False,
        environment_name=manifest.environment,
    )
    image = modal.Image.from_id(manifest.image_reference)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    rate_limiters = {
        name: StartRateLimiter(profiles[name].offered_requests_per_second)
        for name in ("disconnected_stop_one", "disconnected_stop_four")
    }
    all_samples: list[Sample] = []
    partial_output = args.output.with_suffix(args.output.suffix + ".partial")
    for profile, operations in (
        ("disconnected_stop_one", 1),
        ("disconnected_stop_four", 4),
    ):
        for offset in range(0, observations, CONCURRENCY):
            _check_disk(args.worktree, manifest.resource_limits.disk_free_mib_min)
            batch = await asyncio.gather(
                *(
                    _sample(
                        profile=profile,
                        index=index,
                        operations=operations,
                        app=app,
                        image=image,
                        manifest=manifest,
                        budget=budget,
                        semaphore=semaphore,
                        rate_limiter=rate_limiters[profile],
                        burst=profile == "disconnected_stop_one" and offset == 0,
                    )
                    for index in range(offset, min(offset + CONCURRENCY, observations))
                )
            )
            all_samples.extend(batch)
            partial_output.write_text(
                json.dumps(
                    {
                        "manifest_id": manifest.manifest_id,
                        "generated_at": _utc_now(),
                        "samples": [asdict(sample) for sample in all_samples],
                    },
                    indent=2,
                )
                + "\n"
            )
            print(
                f"{profile}: {min(offset + CONCURRENCY, observations)}/{observations}"
            )
            profile_samples = [
                sample for sample in all_samples if sample.profile == profile
            ]
            if profile == "disconnected_stop_one" and offset == 0:
                cold_32 = _distribution(
                    [sample.cold_first_pwd_ms for sample in profile_samples]
                )
                if (
                    any(sample.error is not None for sample in profile_samples)
                    or cold_32["p99_ms"] > profiles["cold_32_way"].p99_target_ms
                ):
                    raise RuntimeError("cold_32_way failed its frozen gate")
            if _gate_is_impossible(
                profile_samples,
                include_cold=profile == "disconnected_stop_one",
            ):
                raise RuntimeError(f"{profile} can no longer satisfy its frozen gates")

    by_profile = {
        profile: [sample for sample in all_samples if sample.profile == profile]
        for profile in ("disconnected_stop_one", "disconnected_stop_four")
    }
    results: dict[str, object] = {}
    for profile, samples in by_profile.items():
        containment = _distribution([sample.containment_ms for sample in samples])
        failures = sum(sample.error is not None for sample in samples)
        containment.update(
            {
                "observations": len(samples),
                "failures": failures,
                "passed": (
                    containment["p95_ms"] <= profiles[profile].containment_p95_target_ms
                    and containment["p99_ms"]
                    <= profiles[profile].containment_p99_target_ms
                ),
            }
        )
        results[profile] = containment
    cold = _distribution(
        [sample.cold_first_pwd_ms for sample in by_profile["disconnected_stop_one"]]
    )
    cold.update(
        {
            "observations": observations,
            "failures": sum(
                sample.error is not None
                for sample in by_profile["disconnected_stop_one"]
            ),
            "passed": (
                cold["p95_ms"] <= profiles["cold_first_pwd"].p95_target_ms
                and cold["p99_ms"] <= profiles["cold_first_pwd"].p99_target_ms
            ),
        }
    )
    first_batch = by_profile["disconnected_stop_one"][:32]
    cold_32 = _distribution([sample.cold_first_pwd_ms for sample in first_batch])
    cold_32.update(
        {
            "observations": len(first_batch),
            "failures": sum(sample.error is not None for sample in first_batch),
            "passed": (
                all(sample.error is None for sample in first_batch)
                and cold_32["p99_ms"] <= profiles["cold_32_way"].p99_target_ms
            ),
        }
    )
    results["cold_first_pwd"] = cold
    results["cold_32_way"] = cold_32
    passed = all(bool(result["passed"]) for result in results.values())
    return {
        "schema_version": "persistent-executor-modal-cohorts-v1",
        "manifest_id": manifest.manifest_id,
        "source_commit": manifest.source_commit,
        "generated_at": _utc_now(),
        "image_id": manifest.image_reference,
        "concurrency": CONCURRENCY,
        "results": results,
        "samples": [asdict(sample) for sample in all_samples],
        "reserved_microusd": budget.reserved_microusd,
        "passed": passed,
    }


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
    args.output.with_suffix(args.output.suffix + ".partial").unlink(missing_ok=True)
    print(
        json.dumps({"results": report["results"], "passed": report["passed"]}, indent=2)
    )
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
