#!/usr/bin/env python3
"""Operator-only Modal sandbox qualification; never runs from web startup.

This exercises the immutable image and sandbox envelope without creating chat
rows or issuing a real model capability. Full Agent SDK/HF resume qualification
still runs through an authenticated staging chat after both bridge releases.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import secrets
import statistics
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import modal

from backend.config import Settings
from backend.services.chat_sandbox_service import (
    WorkspaceSnapshotProvider,
    create_isolated_sandbox,
)
from backend.services.chat_runtime_contract import (
    dedicated_gateway_hostname,
    require_immutable_image_id,
)
from deploy.release import validate_manifest

CONFIRMATION = "QUALIFY_STAGING_SANDBOX"
FORBIDDEN_ENVIRONMENT_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "HF_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "PWC_DB_PASSWORD",
    "PWC_HF_TOKEN",
    "PWC_JWT_SECRET",
}
MAX_CAPTURE_BYTES = 64 * 1024


@dataclass(frozen=True)
class Sample:
    cold_start_ms: int
    exec_ms: int
    termination_ms: int
    snapshot_ms: int | None
    restore_ms: int | None


def percentile(values: list[int], quantile: float) -> int:
    if not values:
        raise ValueError("At least one value is required")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize(samples: list[Sample]) -> dict[str, Any]:
    def metric(name: str) -> dict[str, int] | None:
        values = [
            value for sample in samples if (value := getattr(sample, name)) is not None
        ]
        if not values:
            return None
        return {
            "count": len(values),
            "min": min(values),
            "p50": round(statistics.median(values)),
            "p95": percentile(values, 0.95),
            "max": max(values),
        }

    return {
        "samples": len(samples),
        "cold_start_ms": metric("cold_start_ms"),
        "exec_ms": metric("exec_ms"),
        "termination_ms": metric("termination_ms"),
        "snapshot_ms": metric("snapshot_ms"),
        "restore_ms": metric("restore_ms"),
    }


def validate_settings(settings: Settings) -> None:
    if settings.environment != "staging":
        raise ValueError("Qualification requires PWC_ENVIRONMENT=staging")
    if settings.chat_new_chat_modal_percentage != 0:
        raise ValueError("Qualification requires a zero-percent Modal rollout")
    require_immutable_image_id(settings.chat_modal_image_version)
    dedicated_gateway_hostname(settings.chat_gateway_url)


def settings_for_release(release_dir: Path) -> Settings:
    release = release_dir.resolve(strict=True)
    manifest = validate_manifest(release, "staging")
    runtime = manifest["chat_runtime"]
    return Settings(
        environment="staging",
        release_id=manifest["release_id"],
        frontend_dist_dir=str(release / "frontend-dist"),
        chat_enabled=runtime["enabled"],
        chat_default_backend=runtime["default_backend"],
        chat_new_chat_modal_percentage=runtime["new_chat_modal_percentage"],
        chat_modal_image_version=runtime["modal_image_version"],
        chat_pwc_cli_version=runtime["pwc_cli_version"],
        chat_worker_contract_version=runtime["worker_contract_version"],
        chat_system_prompt_sha256=runtime["system_prompt_sha256"],
    )


async def _capture(process) -> tuple[int, str, str]:
    stdout, stderr = await asyncio.gather(
        process.stdout.read.aio(),
        process.stderr.read.aio(),
    )
    await process.wait.aio()
    stdout = str(stdout)[:MAX_CAPTURE_BYTES]
    stderr = str(stderr)[:MAX_CAPTURE_BYTES]
    return int(process.returncode or 0), stdout, stderr


async def _exec(sandbox, *command: str, timeout: int = 30) -> tuple[int, str, str]:
    process = await sandbox.exec.aio(
        *command,
        stdout=modal.StreamType.PIPE,
        stderr=modal.StreamType.PIPE,
        timeout=timeout,
        text=True,
        workdir="/workspace",
    )
    return await _capture(process)


async def _require_success(sandbox, *command: str, timeout: int = 30) -> str:
    returncode, stdout, _stderr = await _exec(sandbox, *command, timeout=timeout)
    if returncode:
        raise RuntimeError(f"Sandbox probe failed with exit code {returncode}")
    return stdout


class QualificationRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        starts: int,
        parallel: int,
        snapshot_samples: int,
    ):
        self.settings = settings
        self.starts = starts
        self.parallel = parallel
        self.snapshot_samples = snapshot_samples
        self.run_id = uuid.uuid4().hex[:12]
        self._semaphore = asyncio.Semaphore(parallel)

    async def _create(self, suffix: str):
        return await create_isolated_sandbox(
            self.settings,
            name=f"qualify-{self.run_id}-{suffix}",
            tags={
                "purpose": "qualification",
                "run": self.run_id,
                "release": self.settings.release_id,
            },
        )

    async def _security_probes(self, sandbox) -> int:
        started = time.perf_counter()
        await _require_success(sandbox, "pwc", "version")
        environment = await _require_success(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "env",
        )
        exposed = {
            line.partition("=")[0] for line in environment.splitlines() if "=" in line
        } & FORBIDDEN_ENVIRONMENT_KEYS
        if exposed:
            raise RuntimeError("Agent environment exposes a forbidden key")

        gateway_probe = """
import json, sys, urllib.error, urllib.request
request = urllib.request.Request(
    sys.argv[1].rstrip("/") + "/catalog",
    data=json.dumps({}).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(request, timeout=10)
except urllib.error.HTTPError as error:
    raise SystemExit(0 if error.code in {401, 403, 422} else 2)
raise SystemExit(3)
"""
        await _require_success(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "python",
            "-c",
            gateway_probe,
            self.settings.chat_gateway_url,
        )

        blocked_egress = """
import urllib.request
urllib.request.urlopen("https://example.com", timeout=5)
"""
        returncode, _stdout, _stderr = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "python",
            "-c",
            blocked_egress,
            timeout=10,
        )
        if returncode == 0:
            raise RuntimeError("Agent reached a non-allowlisted internet host")

        sentinel = secrets.token_hex(32)
        proc_probe = """
set -eu
if ! grep -Eq '^[^ ]+ /proc [^ ]+ [^ ]*hidepid=2' /proc/mounts; then
  mount -o remount,hidepid=2,nosuid,nodev /proc
fi
setpriv --reuid=pwc-broker --regid=pwc-broker --clear-groups \
  env PWC_QUALIFICATION_SENTINEL="$1" sleep 20 &
broker_pid=$!
trap 'kill "$broker_pid" 2>/dev/null || true' EXIT
if setpriv --reuid=pwc-chat --regid=pwc-chat --clear-groups \
  cat "/proc/$broker_pid/environ" >/dev/null 2>&1; then
  exit 20
fi
if setpriv --reuid=pwc-chat --regid=pwc-chat --clear-groups \
  kill -0 "$broker_pid" >/dev/null 2>&1; then
  exit 21
fi
"""
        await _require_success(sandbox, "sh", "-c", proc_probe, "proc-probe", sentinel)
        return round((time.perf_counter() - started) * 1000)

    async def _snapshot_probe(self, sandbox, index: int) -> tuple[int, int]:
        marker = secrets.token_hex(16)
        await _require_success(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "sh",
            "-c",
            'printf "%s" "$1" > /workspace/qualification-marker',
            "write-marker",
            marker,
        )
        snapshots = WorkspaceSnapshotProvider(ttl_days=1)
        started = time.perf_counter()
        snapshot_id = await snapshots.save(sandbox, uuid.uuid4())
        snapshot_ms = round((time.perf_counter() - started) * 1000)

        restored = await self._create(f"restore-{index}")
        try:
            started = time.perf_counter()
            await snapshots.restore(restored, snapshot_id)
            restored_marker = await _require_success(
                restored,
                "setpriv",
                "--reuid=pwc-chat",
                "--regid=pwc-chat",
                "--clear-groups",
                "cat",
                "/workspace/qualification-marker",
            )
            restore_ms = round((time.perf_counter() - started) * 1000)
            if restored_marker != marker:
                raise RuntimeError("Directory snapshot did not preserve workspace data")
            return snapshot_ms, restore_ms
        finally:
            await restored.terminate.aio(wait=False)

    async def _sample(self, index: int) -> Sample:
        async with self._semaphore:
            started = time.perf_counter()
            sandbox = await self._create(str(index))
            cold_start_ms = round((time.perf_counter() - started) * 1000)
            terminated = False
            try:
                exec_ms = await self._security_probes(sandbox)
                snapshot_ms = restore_ms = None
                if index < self.snapshot_samples:
                    snapshot_ms, restore_ms = await self._snapshot_probe(sandbox, index)

                await sandbox.exec.aio("sleep", "120", timeout=180)
                started = time.perf_counter()
                await sandbox.terminate.aio(wait=False)
                terminated = True
                while await sandbox.poll.aio() is None:
                    if time.perf_counter() - started > 10:
                        raise RuntimeError("Sandbox termination exceeded ten seconds")
                    await asyncio.sleep(0.1)
                termination_ms = round((time.perf_counter() - started) * 1000)
                return Sample(
                    cold_start_ms=cold_start_ms,
                    exec_ms=exec_ms,
                    termination_ms=termination_ms,
                    snapshot_ms=snapshot_ms,
                    restore_ms=restore_ms,
                )
            finally:
                if not terminated:
                    await sandbox.terminate.aio(wait=False)

    async def _resource_probe(
        self,
        name: str,
        *command: str,
        expect_success: bool,
        timeout: int,
    ) -> None:
        sandbox = await self._create(f"resource-{name}")
        try:
            returncode, _stdout, _stderr = await _exec(
                sandbox,
                "setpriv",
                "--reuid=pwc-chat",
                "--regid=pwc-chat",
                "--clear-groups",
                *command,
                timeout=timeout,
            )
            succeeded = returncode == 0
            if succeeded != expect_success:
                expectation = "success" if expect_success else "limit failure"
                raise RuntimeError(
                    f"{name} resource probe did not produce expected {expectation}"
                )
        finally:
            await sandbox.terminate.aio(wait=False)

    async def run_resource_probes(self) -> dict[str, str]:
        pid_probe = """
import os, signal, time
children = []
limit_observed = False
try:
    for _ in range(int(os.environ["PWC_CHAT_SANDBOX_PIDS_MAX"]) * 2):
        try:
            pid = os.fork()
        except OSError:
            limit_observed = True
            break
        if pid == 0:
            time.sleep(30)
            os._exit(0)
        children.append(pid)
finally:
    for pid in children:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid in children:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
raise SystemExit(0 if limit_observed else 2)
"""
        await self._resource_probe(
            "pids",
            "python",
            "-c",
            pid_probe,
            expect_success=True,
            timeout=45,
        )
        disk_mib = self.settings.chat_sandbox_writable_bytes // (1024 * 1024) + 64
        await self._resource_probe(
            "disk",
            "dd",
            "if=/dev/zero",
            "of=/workspace/qualification-disk-fill",
            "bs=1M",
            f"count={disk_mib}",
            "status=none",
            expect_success=False,
            timeout=90,
        )
        allocation_mib = self.settings.chat_sandbox_memory_mib + 512
        memory_probe = (
            "import time; "
            f"value = bytearray({allocation_mib} * 1024 * 1024); "
            "time.sleep(2); print(len(value))"
        )
        await self._resource_probe(
            "memory",
            "python",
            "-c",
            memory_probe,
            expect_success=False,
            timeout=30,
        )
        return {"pids": "enforced", "disk": "enforced", "memory": "enforced"}

    async def run(
        self, *, resource_probes: bool
    ) -> tuple[list[Sample], dict[str, str] | None]:
        samples: list[Sample | None] = [None] * self.starts

        async def land(index: int) -> None:
            samples[index] = await self._sample(index)

        async with asyncio.TaskGroup() as group:
            for index in range(self.starts):
                group.create_task(land(index))
        landed = [sample for sample in samples if sample is not None]
        resources = await self.run_resource_probes() if resource_probes else None
        return landed, resources


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify the pinned staging Modal sandbox image"
    )
    result.add_argument("--starts", type=int, default=100)
    result.add_argument("--parallel", type=int, default=4)
    result.add_argument("--snapshot-samples", type=int, default=3)
    result.add_argument("--resource-probes", action="store_true")
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.starts <= 500:
        raise SystemExit("--starts must be 1-500")
    if not 1 <= args.parallel <= 16:
        raise SystemExit("--parallel must be 1-16")
    if not 0 <= args.snapshot_samples <= args.starts:
        raise SystemExit("--snapshot-samples must be between 0 and --starts")
    settings = settings_for_release(args.release_dir)
    validate_settings(settings)
    samples, resource_results = asyncio.run(
        QualificationRunner(
            settings,
            starts=args.starts,
            parallel=args.parallel,
            snapshot_samples=args.snapshot_samples,
        ).run(resource_probes=args.resource_probes)
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "release_id": settings.release_id,
                "image_id": settings.chat_modal_image_version,
                "configuration": {
                    "starts": args.starts,
                    "parallel": args.parallel,
                    "snapshot_samples": args.snapshot_samples,
                },
                "summary": summarize(samples),
                "resource_probes": resource_results,
                "raw_samples": [asdict(sample) for sample in samples],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
