#!/usr/bin/env python3
"""Collect frozen local-process Task 0 latency and overlap evidence."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.loadtests.persistent_executor_feasibility import (
    nearest_rank,
    validate_manifest,
)
from backend.loadtests.persistent_executor_runtime import (
    OperationResult,
    TurnExecutionRuntime,
)

MAX_PARALLEL_TURNS = 16
CANCEL_COMMANDS = (
    "trap '' TERM; while :; do head -c 65536 /dev/zero; done",
    "trap '' TERM; sleep 30",
    "trap '' TERM; sleep 30",
    "trap '' TERM; sleep 30",
)
DEADLINE_COMMANDS = ("trap '' TERM; sleep 30",) * 4
CATALOG_COMMANDS = (
    "/root/.local/bin/pwc search 'vision transformer' --limit 5",
    "/root/.local/bin/pwc search 'large language model' --limit 5",
    "/root/.local/bin/pwc search 'object detection' --limit 5",
    "/root/.local/bin/pwc search 'semantic segmentation' --limit 5",
)


@dataclass(frozen=True, slots=True)
class CancellationSample:
    profile: str
    index: int
    operations: int
    delivery_ms: float
    containment_ms: float
    unknown_outcome: bool
    reservation_retained: bool
    all_processes_cancelled: bool
    capability_revoked: bool


class Broker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = False
        self.installs = 0
        self.clears = 0

    def __call__(self, operation: str, capability: str) -> bool:
        if not capability:
            return False
        with self._lock:
            if operation == "install":
                if self.active:
                    return False
                self.active = True
                self.installs += 1
                return True
            if operation == "clear" and self.active:
                self.active = False
                self.clears += 1
                return True
            return False


class StartRateLimiter:
    def __init__(self, starts_per_second: float) -> None:
        self._interval = 1 / starts_per_second
        self._next_start = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_start - now)
            if delay:
                time.sleep(delay)
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


def _runtime(broker: Broker, *, deadline_seconds: float = 30) -> TurnExecutionRuntime:
    runtime = TurnExecutionRuntime(
        broker=broker,
        sandbox_terminator=lambda: True,
        terminate_grace_seconds=0.005,
    )
    runtime.authorize(
        "task0-local-capability",
        absolute_deadline_unix=time.time() + deadline_seconds,
    )
    return runtime


def _execute_operations(
    runtime: TurnExecutionRuntime, commands: tuple[str, ...], index: int
) -> tuple[list[OperationResult], list[threading.Thread]]:
    results: list[OperationResult] = []
    threads = [
        threading.Thread(
            target=lambda operation=operation, command=command: results.append(
                runtime.execute(
                    f"operation-{index}-{operation}", command, timeout_seconds=30
                )
            )
        )
        for operation, command in enumerate(commands)
    ]
    for thread in threads:
        thread.start()
    return results, threads


def _cancellation_sample(
    profile: str,
    index: int,
    operations: int,
    *,
    deadline: bool,
    rate_limiter: StartRateLimiter,
) -> CancellationSample:
    rate_limiter.wait()
    broker = Broker()
    runtime = _runtime(broker, deadline_seconds=0.5 if deadline else 30)
    commands = (DEADLINE_COMMANDS if deadline else CANCEL_COMMANDS)[:operations]
    results, threads = _execute_operations(runtime, commands, index)
    if not runtime.wait_until_running(operations, timeout_seconds=2):
        runtime.cancel(transport_connected=True, remote_acknowledged=True)
        raise RuntimeError(f"{profile} failed to start every operation")
    if deadline:
        for thread in threads:
            thread.join(timeout=2)
        evidence = runtime.close()
    else:
        evidence = runtime.cancel(
            transport_connected=True,
            remote_acknowledged=True,
        )
        for thread in threads:
            thread.join(timeout=2)
    if any(thread.is_alive() for thread in threads) or len(results) != operations:
        raise RuntimeError(f"{profile} did not contain every operation")
    observed = [result.cancellation_observed_at for result in results]
    contained = [result.process_contained_at for result in results]
    if any(value is None for value in observed + contained):
        raise RuntimeError(f"{profile} lacks cancellation proof")
    return CancellationSample(
        profile=profile,
        index=index,
        operations=operations,
        delivery_ms=(max(observed) - evidence.cancellation_requested_at) * 1000,
        containment_ms=(max(contained) - evidence.cancellation_requested_at) * 1000,
        unknown_outcome=evidence.unknown_outcome,
        reservation_retained=evidence.reservation_retained,
        all_processes_cancelled=all(result.status == "cancelled" for result in results),
        capability_revoked=evidence.capability_revoked_at is not None,
    )


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": nearest_rank(values, 0.50),
        "p95_ms": nearest_rank(values, 0.95),
        "p99_ms": nearest_rank(values, 0.99),
        "max_ms": max(values),
    }


def _run_cancellation_profile(
    profile: object,
) -> tuple[dict[str, object], list[CancellationSample]]:
    deadline = str(profile.name).startswith("deadline")
    rate_limiter = StartRateLimiter(profile.offered_requests_per_second)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_TURNS) as pool:
        samples = list(
            pool.map(
                lambda index: _cancellation_sample(
                    profile.name,
                    index,
                    profile.simultaneous_operations,
                    deadline=deadline,
                    rate_limiter=rate_limiter,
                ),
                range(profile.observations),
            )
        )
    delivery = _distribution([sample.delivery_ms for sample in samples])
    containment = _distribution([sample.containment_ms for sample in samples])
    failures = sum(
        sample.unknown_outcome
        or not sample.all_processes_cancelled
        or not sample.capability_revoked
        for sample in samples
    )
    return (
        {
            "observations": len(samples),
            "operations_per_turn": profile.simultaneous_operations,
            "delivery": delivery,
            "containment": containment,
            "failures": failures,
            "passed": (
                failures == 0
                and delivery["p95_ms"] <= profile.p95_target_ms
                and delivery["p99_ms"] <= profile.p99_target_ms
                and containment["p95_ms"] <= profile.containment_p95_target_ms
                and containment["p99_ms"] <= profile.containment_p99_target_ms
            ),
        },
        samples,
    )


def _run_warm_profiles(profiles: dict[str, object]) -> dict[str, object]:
    broker = Broker()
    runtime = _runtime(broker)
    ack_values = []
    terminal_values = []
    rate_limiter = StartRateLimiter(
        min(
            profiles["warm_ack"].offered_requests_per_second,
            profiles["warm_noop"].offered_requests_per_second,
        )
    )
    for index in range(profiles["warm_noop"].observations):
        rate_limiter.wait()
        invoked_at = time.monotonic()
        result = runtime.execute(f"warm-{index}", "true")
        if result.started_at is None or result.status != "completed":
            raise RuntimeError("warm no-op did not complete")
        ack_values.append((result.started_at - invoked_at) * 1000)
        terminal_values.append((result.terminal_at - invoked_at) * 1000)
    runtime.close()
    ack = _distribution(ack_values)
    terminal = _distribution(terminal_values)
    return {
        "warm_ack": {
            **ack,
            "observations": len(ack_values),
            "passed": ack["p95_ms"] <= profiles["warm_ack"].p95_target_ms
            and ack["p99_ms"] <= profiles["warm_ack"].p99_target_ms,
        },
        "warm_noop": {
            **terminal,
            "observations": len(terminal_values),
            "passed": terminal["p95_ms"] <= profiles["warm_noop"].p95_target_ms
            and terminal["p99_ms"] <= profiles["warm_noop"].p99_target_ms,
        },
        "capability_installs": broker.installs,
        "capability_clears": broker.clears,
    }


def _run_catalog_overlap() -> dict[str, object]:
    broker = Broker()
    runtime = _runtime(broker)
    results, threads = _execute_operations(runtime, CATALOG_COMMANDS, 0)
    if not runtime.wait_until_running(4, timeout_seconds=2):
        runtime.cancel(transport_connected=True, remote_acknowledged=True)
        raise RuntimeError("catalog calls did not start")
    for thread in threads:
        thread.join(timeout=15)
    runtime.close()
    if any(thread.is_alive() for thread in threads) or len(results) != 4:
        raise RuntimeError("catalog calls did not finish")
    starts = [result.started_at for result in results]
    if any(value is None for value in starts):
        raise RuntimeError("catalog calls lack start timestamps")
    overlap_ms = (min(result.terminal_at for result in results) - max(starts)) * 1000
    passed = (
        overlap_ms > 0
        and all(result.status == "completed" for result in results)
        and all(result.output.startswith(b"id\ttitle\tyear") for result in results)
        and broker.installs == 1
        and broker.clears == 1
    )
    return {
        "observations": 4,
        "overlap_ms": overlap_ms,
        "statuses": [result.status for result in results],
        "capability_installs": broker.installs,
        "capability_clears": broker.clears,
        "passed": passed,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if _source_commit(args.worktree) != manifest.source_commit:
        raise ValueError("manifest source commit does not match HEAD")
    if _sha256(args.schema) != manifest.schema_digest:
        raise ValueError("manifest schema digest does not match source")
    if args.output.exists():
        raise ValueError("refusing to overwrite existing qualification evidence")
    free_mib = os.statvfs(args.worktree).f_bavail * os.statvfs(args.worktree).f_frsize
    if free_mib // (1024 * 1024) < manifest.resource_limits.disk_free_mib_min:
        raise RuntimeError("host disk crossed the frozen experiment floor")
    profiles = {profile.name: profile for profile in manifest.profiles}
    results = _run_warm_profiles(profiles)
    samples: list[CancellationSample] = []
    for name in (
        "connected_stop_one",
        "connected_stop_four",
        "deadline_one",
        "deadline_four",
    ):
        result, profile_samples = _run_cancellation_profile(profiles[name])
        results[name] = result
        samples.extend(profile_samples)
    results["catalog_call_overlap"] = _run_catalog_overlap()
    return {
        "schema_version": "persistent-executor-local-cohorts-v1",
        "manifest_id": manifest.manifest_id,
        "source_commit": manifest.source_commit,
        "generated_at": _utc_now(),
        "results": results,
        "cancellation_samples": [asdict(sample) for sample in samples],
        "passed": all(
            bool(result["passed"])
            for result in results.values()
            if isinstance(result, dict) and "passed" in result
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({"results": report["results"], "passed": report["passed"]}, indent=2)
    )
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
