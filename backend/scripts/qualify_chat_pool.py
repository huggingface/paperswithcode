#!/usr/bin/env python3
"""Run sanitized, authenticated blank-pool qualification on staging."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnLatency,
)
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import (
    merge_release_settings,
    settings_for_release,
)
from backend.scripts.staging_qualification_http import client as staging_client
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.hf_inference_billing_service import COOKIE_NAME, encrypt_token
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_pool_repository import ChatSandboxPoolRepository

CONFIRMATION = "QUALIFY_STAGING_CHAT_POOL"
PRODUCTION_7D_PROFILE = "production-7d-v1"


@dataclass(frozen=True)
class PoolSample:
    request_id: str | None
    acquisition_outcome: str | None
    pool_lookup_ms: int | None
    sdk_dispatch_ms: int | None
    first_delta_ms: int | None
    total_ms: int | None
    estimated_active_cost_usd: float | None
    continuous_pool_interval: bool
    cleanup_confirmed: bool
    terminal_status: str
    error_code: str | None
    assignment_to_dispatch_ms: int | None = None
    browser_reasoning_ms: int | None = None
    pool_miss_reason: str | None = None


def percentile(values: list[int], quantile: float) -> int:
    if not values:
        raise ValueError("At least one value is required")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def summarize(samples: list[PoolSample]) -> dict[str, Any]:
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
            "p75": percentile(values, 0.75),
            "p90": percentile(values, 0.90),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
            "max": max(values),
        }

    return {
        "samples": len(samples),
        "complete": sum(sample.terminal_status == "complete" for sample in samples),
        "pool_hits": sum(
            sample.acquisition_outcome == "pool_hit" for sample in samples
        ),
        "pool_misses": sum(
            sample.acquisition_outcome == "pool_miss" for sample in samples
        ),
        "hit_rate": round(
            sum(sample.acquisition_outcome == "pool_hit" for sample in samples)
            / max(1, len(samples)),
            4,
        ),
        "miss_reasons": {
            reason: sum(sample.pool_miss_reason == reason for sample in samples)
            for reason in sorted(
                {
                    sample.pool_miss_reason
                    for sample in samples
                    if sample.pool_miss_reason
                }
            )
        },
        "continuous_pool_intervals": sum(
            sample.continuous_pool_interval for sample in samples
        ),
        "cleanup_confirmed": sum(sample.cleanup_confirmed for sample in samples),
        "pool_lookup_ms": metric("pool_lookup_ms"),
        "sdk_dispatch_ms": metric("sdk_dispatch_ms"),
        "first_delta_ms": metric("first_delta_ms"),
        "assignment_to_dispatch_ms": metric("assignment_to_dispatch_ms"),
        "browser_reasoning_ms": metric("browser_reasoning_ms"),
        "total_ms": metric("total_ms"),
        "estimated_active_cost_usd": {
            "total": round(
                sum(sample.estimated_active_cost_usd or 0 for sample in samples),
                8,
            ),
            "per_completed_turn": round(
                sum(sample.estimated_active_cost_usd or 0 for sample in samples)
                / max(
                    1,
                    sum(sample.terminal_status == "complete" for sample in samples),
                ),
                8,
            ),
        },
    }


def qualification_passes(
    *, samples: int, summary: dict[str, Any], blank_starts: int, marked: int
) -> bool:
    component = summary["assignment_to_dispatch_ms"]
    return bool(
        samples >= 200
        and summary["complete"] == samples
        and summary["hit_rate"] >= 0.95
        and component is not None
        and component["count"] >= 50
        and component["p50"] <= 1_500
        and component["p90"] <= 3_000
        and summary["continuous_pool_intervals"] == summary["pool_hits"]
        and summary["cleanup_confirmed"] == samples
        and blank_starts >= summary["pool_hits"]
        and marked == samples
    )


def new_chat_payload(*, selected_model: str, reasoning_effort: str) -> dict[str, str]:
    """Build a real new-chat request; omitting session_id is part of the gate."""

    return {
        "message": "Reply with a concise acknowledgement.",
        "client_message_id": str(uuid.uuid4()),
        "initial_model": selected_model,
        "reasoning_effort": reasoning_effort,
    }


def arrival_offsets_ms(
    *, samples: int, interarrival_ms: int, profile: str
) -> list[int]:
    """Return deterministic offsets for fixed or measured production pacing."""

    if profile == "fixed":
        gaps = [interarrival_ms] * max(0, samples - 1)
    elif profile == PRODUCTION_7D_PROFILE:
        gaps = []
        for index in range(max(0, samples - 1)):
            if index == 43:
                gap = 10_000
            elif index == 44:
                gap = 20_000
            elif index % 22 == 21:
                gap = 10_000
            else:
                gap = 30_000
            gaps.append(gap)
    else:
        raise ValueError(f"Unsupported arrival profile: {profile}")
    offsets = [0]
    for gap in gaps:
        offsets.append(offsets[-1] + gap)
    return offsets


class PoolQualification:
    def __init__(
        self,
        *,
        settings,
        billing_settings,
        samples: int,
        blank_timeout: float,
        arrival_concurrency: int,
        interarrival_ms: int,
        admin_subject: str,
        admin_username: str,
        qualification_owner: str,
        selected_model: str,
        arrival_profile: str,
    ):
        self.settings = settings
        self.billing_settings = billing_settings
        self.samples = samples
        self.blank_timeout = blank_timeout
        self.arrival_concurrency = arrival_concurrency
        self.interarrival_ms = interarrival_ms
        self.admin_subject = admin_subject
        self.admin_username = admin_username
        self.qualification_owner = qualification_owner
        self.selected_model = selected_model
        self.arrival_profile = arrival_profile
        self.started_at = datetime.now(UTC)
        self.run_id = uuid.uuid4().hex[:12]

    def validate(self, *, cpu: float, memory_mib: int) -> None:
        if self.settings.environment != "staging":
            raise ValueError("Pool qualification requires staging")
        if not self.settings.chat_persistent_worker_enabled:
            raise ValueError("Persistent workers must be enabled")
        if not self.settings.chat_blank_pool_enabled:
            raise ValueError("The blank pool must be enabled")
        if (
            self.settings.chat_default_agent_harness != "pi"
            or self.settings.chat_new_session_pi_percentage != 100
        ):
            raise ValueError(
                "Pool qualification requires all new staging sessions to use Pi"
            )
        if self.settings.chat_sandbox_cpu != cpu:
            raise ValueError("Configured CPU request does not match the candidate")
        if self.settings.chat_sandbox_memory_mib != memory_mib:
            raise ValueError("Configured memory request does not match the candidate")
        if (
            self.settings.chat_model_routes.get(self.selected_model)
            != self.settings.chat_effective_pi_prewarm_model
        ):
            raise ValueError("Selected model does not map to the Pi prewarm route")

    def _compatible_blank_count(self) -> int:
        compatibility = ChatSandboxPoolRepository(
            self.settings,
            capacity_locker=lambda *_args, **_kwargs: True,
        ).compatibility()
        with db_manager.session_local() as db:
            return (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.image_version == compatibility.image_version,
                        ChatSandboxPool.worker_contract_version
                        == compatibility.worker_contract_version,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.agent_harness == compatibility.agent_harness,
                        ChatSandboxPool.agent_harness_version
                        == compatibility.agent_harness_version,
                        ChatSandboxPool.model_profile == compatibility.model_profile,
                        ChatSandboxPool.reasoning_profile
                        == compatibility.reasoning_profile,
                        ChatSandboxPool.prompt_digest == compatibility.prompt_digest,
                        ChatSandboxPool.provider_adapter_contract
                        == compatibility.provider_adapter_contract,
                        ChatSandboxPool.cpu_request == compatibility.cpu_request,
                        ChatSandboxPool.cpu_limit == compatibility.cpu_limit,
                        ChatSandboxPool.memory_request_mib
                        == compatibility.memory_request_mib,
                        ChatSandboxPool.memory_limit_mib
                        == compatibility.memory_limit_mib,
                    )
                )
                or 0
            )

    async def _wait_for_blank(self) -> None:
        deadline = time.monotonic() + self.blank_timeout
        while time.monotonic() < deadline:
            if self._compatible_blank_count() > 0:
                return
            await asyncio.sleep(0.25)
        raise TimeoutError("Compatible blank worker was not replenished")

    def _latency(
        self, request_id: str, error_code: str | None
    ) -> tuple[PoolSample, uuid.UUID, tuple[uuid.UUID, ...]]:
        with db_manager.session_local() as db:
            row = db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.request_id == uuid.UUID(request_id)
                )
            ).scalar_one()
            intervals = list(
                db.scalars(
                    select(ChatSandboxComputeInterval).where(
                        ChatSandboxComputeInterval.chat_session_id
                        == row.chat_session_id
                    )
                )
            )
            lease = db.get(ChatSandboxLease, row.chat_session_id)
            interval = intervals[0] if len(intervals) == 1 else None
            continuous = bool(
                interval is not None
                and lease is not None
                and interval.origin == "blank_pool"
                and interval.modal_sandbox_id is not None
                and interval.modal_sandbox_id == lease.modal_sandbox_id
                and interval.provider_created_at is not None
                and interval.claimed_at is not None
                and interval.reserved_at <= interval.provider_created_at
                and interval.provider_created_at <= interval.claimed_at
                and interval.terminal_at is None
            )
            return (
                PoolSample(
                    request_id=request_id,
                    acquisition_outcome=row.acquisition_outcome,
                    pool_lookup_ms=row.pool_lookup_completed_ms,
                    sdk_dispatch_ms=row.sdk_query_dispatched_ms,
                    first_delta_ms=row.first_application_sse_delta_ms,
                    assignment_to_dispatch_ms=(
                        row.sdk_query_dispatched_ms
                        - row.session_assignment_completed_ms
                        if row.sdk_query_dispatched_ms is not None
                        and row.session_assignment_completed_ms is not None
                        else None
                    ),
                    browser_reasoning_ms=row.browser_first_reasoning_delta_ms,
                    pool_miss_reason=row.pool_miss_reason,
                    total_ms=row.total_ms,
                    estimated_active_cost_usd=(
                        float(row.estimated_active_cost_usd)
                        if row.estimated_active_cost_usd is not None
                        else None
                    ),
                    continuous_pool_interval=continuous,
                    cleanup_confirmed=False,
                    terminal_status=row.terminal_status,
                    error_code=error_code,
                ),
                row.chat_session_id,
                tuple(candidate.id for candidate in intervals),
            )

    def _session_id(self, subject: str) -> uuid.UUID | None:
        with db_manager.session_local() as db:
            return db.scalar(
                select(ChatSession.id).where(ChatSession.hf_user_id == subject)
            )

    def _cleanup_confirmed(
        self, session_id: uuid.UUID, interval_ids: tuple[uuid.UUID, ...]
    ) -> bool:
        if not interval_ids:
            return False
        with db_manager.session_local() as db:
            lease = db.get(ChatSandboxLease, session_id)
            intervals = [
                db.get(ChatSandboxComputeInterval, interval_id)
                for interval_id in interval_ids
            ]
            return bool(
                lease is not None
                and lease.state == "terminated"
                and lease.modal_sandbox_id is None
                and all(
                    interval is not None and interval.terminal_at is not None
                    for interval in intervals
                )
            )

    async def _turn(self, index: int) -> PoolSample:
        subject = f"{self.qualification_owner}:{index}"
        token = _encode_legacy_session(
            {
                "sub": self.admin_subject,
                "username": self.admin_username,
                "chat_qualification_owner": subject,
            }
        )
        billing = encrypt_token(
            self.billing_settings.hf_token,
            subject,
            self.billing_settings,
        )
        payload = new_chat_payload(
            selected_model=self.selected_model,
            reasoning_effort=self.settings.chat_pi_prewarm_reasoning_effort,
        )
        request_id: str | None = None
        terminal = "error"
        error_code: str | None = None
        async with staging_client(
            timeout=240,
            cookies={
                self.settings.session_cookie_name: token,
                COOKIE_NAME: billing,
            },
        ) as client:
            async with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json=payload,
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    error_code = f"http_{response.status_code}"
                else:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        if event.get("type") == "stream_start":
                            request_id = str(event["request_id"])
                        if event.get("type") in {"done", "cancelled", "error"}:
                            terminal = str(event["type"])
                            error_code = (
                                str(event.get("code")) if event.get("code") else None
                            )
        sample = PoolSample(
            request_id=request_id,
            acquisition_outcome=None,
            pool_lookup_ms=None,
            sdk_dispatch_ms=None,
            first_delta_ms=None,
            total_ms=None,
            estimated_active_cost_usd=None,
            continuous_pool_interval=False,
            cleanup_confirmed=False,
            terminal_status=terminal,
            error_code=error_code,
        )
        session_id: uuid.UUID | None = None
        interval_ids: tuple[uuid.UUID, ...] = ()
        if request_id is not None:
            for _ in range(40):
                try:
                    sample, session_id, interval_ids = self._latency(
                        request_id, error_code
                    )
                    break
                except NoResultFound:
                    await asyncio.sleep(0.05)
        session_id = session_id or self._session_id(subject)
        if session_id is not None:
            await SandboxSessionManager(self.settings).terminate(session_id)
            sample = replace(
                sample,
                cleanup_confirmed=self._cleanup_confirmed(session_id, interval_ids),
            )
        return sample

    def _blank_starts(self) -> int:
        with db_manager.session_local() as db:
            return (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.created_at >= self.started_at,
                        ChatSandboxPool.app_release_id == self.settings.release_id,
                        ChatSandboxPool.cpu_request == self.settings.chat_sandbox_cpu,
                        ChatSandboxPool.memory_request_mib
                        == self.settings.chat_sandbox_memory_mib,
                    )
                )
                or 0
            )

    async def run(self) -> tuple[list[PoolSample], int]:
        await self._wait_for_blank()
        semaphore = asyncio.Semaphore(self.arrival_concurrency)
        offsets_ms = arrival_offsets_ms(
            samples=self.samples,
            interarrival_ms=self.interarrival_ms,
            profile=self.arrival_profile,
        )

        async def paced_turn(index: int) -> PoolSample:
            await asyncio.sleep(offsets_ms[index] / 1000)
            async with semaphore:
                return await self._turn(index)

        landed = list(
            await asyncio.gather(*(paced_turn(index) for index in range(self.samples)))
        )
        await self._wait_for_blank()
        return landed, self._blank_starts()

    def mark_samples(self, samples: list[PoolSample]) -> int:
        request_ids = [sample.request_id for sample in samples if sample.request_id]
        with db_manager.session_local() as db:
            service = ChatLatencyService(db)
            marked = sum(
                service.mark_qualification(
                    request_id,
                    run_id=self.run_id,
                    scenario="focused_latency",
                )
                for request_id in request_ids
            )
            db.commit()
        return marked


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify authenticated staging blank-pool claims and turns"
    )
    result.add_argument("--samples", type=int, default=200)
    result.add_argument("--arrival-concurrency", type=int, default=4)
    result.add_argument("--interarrival-ms", type=int, default=750)
    result.add_argument(
        "--arrival-profile",
        choices=("fixed", PRODUCTION_7D_PROFILE),
        default="fixed",
    )
    result.add_argument("--candidate-cpu", type=float, required=True)
    result.add_argument("--candidate-memory-mib", type=int, required=True)
    result.add_argument("--blank-timeout", type=float, default=90)
    result.add_argument("--admin-subject", required=True)
    result.add_argument("--admin-username", required=True)
    result.add_argument("--qualification-owner", required=True)
    result.add_argument("--selected-model", required=True)
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.samples <= 200:
        raise SystemExit("--samples must be 1-200")
    if not 1 <= args.arrival_concurrency <= 8:
        raise SystemExit("--arrival-concurrency must be 1-8")
    if not 100 <= args.interarrival_ms <= 10_000:
        raise SystemExit("--interarrival-ms must be 100-10000")
    if not args.qualification_owner.startswith("operator:pi-qualification:"):
        raise SystemExit(
            "--qualification-owner must start with operator:pi-qualification:"
        )
    if len(f"{args.qualification_owner}:{args.samples - 1}") > 128:
        raise SystemExit("Per-sample qualification owner exceeds 128 characters")
    environment_settings = get_settings()
    release = settings_for_release(args.release_dir)
    release_settings = merge_release_settings(environment_settings, release)
    qualification = PoolQualification(
        settings=release_settings,
        billing_settings=environment_settings,
        samples=args.samples,
        blank_timeout=args.blank_timeout,
        arrival_concurrency=args.arrival_concurrency,
        interarrival_ms=args.interarrival_ms,
        admin_subject=args.admin_subject,
        admin_username=args.admin_username,
        qualification_owner=args.qualification_owner,
        selected_model=args.selected_model,
        arrival_profile=args.arrival_profile,
    )
    qualification.validate(cpu=args.candidate_cpu, memory_mib=args.candidate_memory_mib)
    samples, blank_starts = asyncio.run(qualification.run())
    marked = qualification.mark_samples(samples)
    summary = summarize(samples)
    passed = qualification_passes(
        samples=args.samples,
        summary=summary,
        blank_starts=blank_starts,
        marked=marked,
    )
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "release_id": qualification.settings.release_id,
                "image_id": qualification.settings.chat_modal_image_version,
                "worker_contract_version": (
                    qualification.settings.chat_worker_contract_version
                ),
                "configuration": {
                    "samples": args.samples,
                    "arrival_concurrency": args.arrival_concurrency,
                    "interarrival_ms": args.interarrival_ms,
                    "arrival_profile": args.arrival_profile,
                    "sandbox_cpu": args.candidate_cpu,
                    "sandbox_cpu_limit": (
                        qualification.settings.chat_sandbox_cpu_limit
                    ),
                    "sandbox_memory_mib": args.candidate_memory_mib,
                    "sandbox_memory_limit_mib": (
                        qualification.settings.chat_sandbox_memory_limit_mib
                    ),
                },
                "blank_starts": blank_starts,
                "marked": marked,
                "summary": summary,
                "raw_samples": [asdict(sample) for sample in samples],
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
