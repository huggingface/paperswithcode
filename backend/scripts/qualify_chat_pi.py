#!/usr/bin/env python3
"""Run the protected, content-sanitized Pi/Claude staging qualification gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import modal
from sqlalchemy import select

from backend.chat_sandbox_worker.comparison_control import sha256 as control_sha256
from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatTurnLatency,
)
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import settings_for_release
from backend.scripts.staging_qualification_http import client as staging_client
from backend.services.chat_latency_service import ChatLatencyService

CONFIRMATION = "QUALIFY_STAGING_PI_ADMIN"
SUITE = Path(__file__).parents[1] / "chat_sandbox_worker" / "quality_suite_v1.json"


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def _cookie(subject: str, username: str, qualification_owner: str) -> str:
    return _encode_legacy_session(
        {
            "sub": subject,
            "username": username,
            "iat": int(time.time()),
            "chat_qualification_owner": qualification_owner,
        }
    )


async def _create(client, harness: str, model: str) -> str:
    response = await client.post(
        "/api/v1/chat/admin/sessions",
        json={
            "agent_harness": harness,
            "selected_model": model,
            "reasoning_effort": "high",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if "agent_harness" in payload:
        raise RuntimeError("public admin response disclosed the harness")
    return str(payload["id"])


async def _turn(
    client,
    session_id: str,
    prompt: str,
    *,
    replace_message_id: str | None = None,
    prior_revision: int | None = None,
) -> dict:
    body = {
        "session_id": session_id,
        "message": prompt,
        "client_message_id": str(uuid.uuid4()),
        "reasoning_effort": "high",
    }
    if replace_message_id is not None:
        body.update(
            replace_message_id=replace_message_id,
            prior_revision=prior_revision,
        )
    answer: list[str] = []
    tools: list[str] = []
    request_id = None
    terminal = "stream_ended"
    finish_reason = None
    error_code = None
    started = time.perf_counter()
    async with client.stream("POST", "/api/v1/chat/stream", json=body) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            kind = event.get("type")
            if kind == "stream_start":
                request_id = str(event["request_id"])
            elif kind == "answer_delta":
                answer.append(str(event.get("text") or ""))
            elif kind == "tool_call":
                tools.append(str(event.get("name") or ""))
            elif kind == "done":
                terminal = "done"
                finish_reason = str(event.get("finish_reason") or "")
            elif kind == "error":
                terminal = "error"
                error_code = str(event.get("code") or "")
    return {
        "request_id": request_id,
        "terminal": terminal,
        "finish_reason": finish_reason,
        "error_code": error_code,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "answer": "".join(answer),
        "tools": tools,
    }


def _task_passed(task: dict, turn: dict) -> bool:
    answer = turn["answer"].casefold()
    tools = {tool.casefold() for tool in turn["tools"]}
    return (
        turn["terminal"] == "done"
        and turn["finish_reason"] in {"success", "tool_limit"}
        and all(str(value).casefold() in answer for value in task.get("required", []))
        and all(
            str(value).casefold() in tools for value in task.get("required_tools", [])
        )
        and not (
            {str(value).casefold() for value in task.get("forbidden_tools", [])} & tools
        )
    )


async def _terminate_session_sandbox(session_id: str) -> bool:
    with db_manager.session_local() as db:
        sandbox_id = db.scalar(
            select(ChatSandboxLease.modal_sandbox_id).where(
                ChatSandboxLease.chat_session_id == uuid.UUID(session_id)
            )
        )
        prior_compute_exists = db.scalar(
            select(ChatSandboxComputeInterval.id)
            .where(ChatSandboxComputeInterval.chat_session_id == uuid.UUID(session_id))
            .limit(1)
        )
    if not sandbox_id:
        return prior_compute_exists is not None
    sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
    await sandbox.terminate.aio(wait=False)
    return True


def _latency_report(session_ids: set[uuid.UUID], started_at: datetime) -> dict:
    with db_manager.session_local() as db:
        rows = list(
            db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.chat_session_id.in_(session_ids),
                    ChatTurnLatency.admitted_at >= started_at,
                )
            ).scalars()
        )
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, "agent_harness", "claude")].append(row)
    result = {}
    for harness, values in grouped.items():
        semantic = [
            row.first_worker_delta_ms
            for row in values
            if row.first_worker_delta_ms is not None
        ]
        visible = [
            row.first_application_sse_delta_ms
            for row in values
            if row.first_application_sse_delta_ms is not None
        ]
        totals = [row.total_ms for row in values if row.total_ms is not None]
        costs = [float(row.estimated_active_cost_usd or 0) for row in values]
        followups = [row for row in values if row.traffic_class == "followup"]
        followup_browser_reasoning = [
            row.browser_first_reasoning_delta_ms
            for row in followups
            if row.browser_first_reasoning_delta_ms is not None
        ]
        result[harness] = {
            "turns": len(values),
            "successful": sum(row.terminal_status == "complete" for row in values),
            "semantic_ttft_p50_ms": round(statistics.median(semantic))
            if semantic
            else None,
            "semantic_ttft_p95_ms": _percentile(semantic, 0.95),
            "visible_ttft_p50_ms": round(statistics.median(visible))
            if visible
            else None,
            "visible_ttft_p95_ms": _percentile(visible, 0.95),
            "total_p50_ms": round(statistics.median(totals)) if totals else None,
            "total_p95_ms": _percentile(totals, 0.95),
            "estimated_active_cost_usd": round(sum(costs), 6),
            "followup_browser_reasoning_count": len(followup_browser_reasoning),
            "followup_browser_reasoning_p50_ms": (
                round(statistics.median(followup_browser_reasoning))
                if followup_browser_reasoning
                else None
            ),
            "followup_browser_reasoning_p90_ms": _percentile(
                followup_browser_reasoning, 0.90
            ),
            "reuse_cohorts": dict(
                Counter(row.session_reuse_cohort or "unclassified" for row in followups)
            ),
            "transcript_failures": sum(
                row.terminal_status == "error"
                and getattr(row, "terminal_error_code", None)
                == "transcript_mirror_failed"
                for row in values
            ),
            "release_ids": sorted({row.app_release_id for row in values}),
            "image_ids": sorted(
                {
                    row.sandbox_image_version
                    for row in values
                    if row.sandbox_image_version
                }
            ),
        }
    return result


async def _run(
    settings,
    *,
    admin_subject: str,
    qualification_owner: str,
    admin_username: str,
    new_turns: int,
    followups: int,
):
    suite = json.loads(SUITE.read_text())
    tasks = suite["tasks"]
    model = settings.chat_model_choices[0]["id"]
    model_route = settings.chat_model_routes[model]
    control_digest = control_sha256(
        model_route=model_route,
        provider=settings.chat_model_providers[model],
        prompt_sha256=settings.chat_system_prompt_sha256,
    )
    started_at = datetime.now(UTC)
    run_id = uuid.uuid4().hex[:12]
    session_ids: set[uuid.UUID] = set()
    requests: dict[str, str] = {}
    quality: list[dict] = []
    new_results: list[dict] = []
    followup_results: list[dict] = []
    replacements = 0
    sandbox_replacements = 0
    cookies = {
        settings.session_cookie_name: _cookie(
            admin_subject, admin_username, qualification_owner
        ),
    }
    async with staging_client(timeout=240, cookies=cookies) as client:
        for task in tasks:
            for harness in ("claude", "pi"):
                session_id = await _create(client, harness, model)
                session_ids.add(uuid.UUID(session_id))
                turn = await _turn(client, session_id, task["prompt"])
                passed = _task_passed(task, turn)
                quality.append(
                    {
                        "task_id": task["id"],
                        "stratum": task["stratum"],
                        "harness": harness,
                        "passed": passed,
                        "terminal": turn["terminal"],
                        "error_code": turn["error_code"],
                        "tool_count": len(turn["tools"]),
                    }
                )
                if turn["request_id"]:
                    requests[turn["request_id"]] = "reliability"

        pi_sessions: list[str] = []
        for index in range(new_turns):
            session_id = await _create(client, "pi", model)
            pi_sessions.append(session_id)
            session_ids.add(uuid.UUID(session_id))
            task = tasks[index % len(tasks)]
            turn = await _turn(client, session_id, task["prompt"])
            new_results.append(turn)
            if turn["request_id"]:
                requests[turn["request_id"]] = "reliability"

        for index in range(followups):
            session_id = pi_sessions[index % len(pi_sessions)]
            if index < min(5, followups) and await _terminate_session_sandbox(
                session_id
            ):
                sandbox_replacements += 1
            turn = await _turn(
                client,
                session_id,
                "Follow up by stating the most important evidence from your prior answer.",
            )
            followup_results.append(turn)
            if turn["request_id"]:
                requests[turn["request_id"]] = (
                    "forced_failure" if index < min(5, followups) else "reliability"
                )

        for session_id in pi_sessions[:3]:
            detail = (await client.get(f"/api/v1/chat/sessions/{session_id}")).json()
            users = [
                message for message in detail["messages"] if message["role"] == "user"
            ]
            if len(users) < 2:
                continue
            target = users[-1]
            turn = await _turn(
                client,
                session_id,
                "Replace that follow-up with a concise evidence check.",
                replace_message_id=target["id"],
                prior_revision=target["revision"],
            )
            if turn["terminal"] == "done":
                replacements += 1
            if turn["request_id"]:
                requests[turn["request_id"]] = "reliability"

        deletion_session = await _create(client, "pi", model)
        deleted = await client.delete(f"/api/v1/chat/sessions/{deletion_session}")
        deletion_passed = (
            deleted.status_code == 204
            and (
                await client.get(f"/api/v1/chat/sessions/{deletion_session}")
            ).status_code
            == 404
        )

    with db_manager.session_local() as db:
        marker = ChatLatencyService(db)
        marked = sum(
            marker.mark_qualification(request_id, run_id=run_id, scenario=scenario)
            for request_id, scenario in requests.items()
        )
        db.commit()
    latency = _latency_report(session_ids, started_at)
    pi_latency = latency.get("pi", {})
    reuse_gate = bool(
        pi_latency.get("followup_browser_reasoning_count", 0) >= 50
        and pi_latency.get("followup_browser_reasoning_p50_ms") is not None
        and pi_latency["followup_browser_reasoning_p50_ms"] <= 3_000
        and pi_latency.get("followup_browser_reasoning_p90_ms") is not None
        and pi_latency["followup_browser_reasoning_p90_ms"] <= 6_000
    )
    new_successes = sum(turn["terminal"] == "done" for turn in new_results)
    followup_successes = sum(turn["terminal"] == "done" for turn in followup_results)
    quality_by_harness = {
        harness: sum(item["passed"] for item in quality if item["harness"] == harness)
        for harness in ("claude", "pi")
    }
    per_stratum = {
        stratum: {
            harness: sum(
                item["passed"]
                for item in quality
                if item["stratum"] == stratum and item["harness"] == harness
            )
            for harness in ("claude", "pi")
        }
        for stratum in sorted({item["stratum"] for item in quality})
    }
    passed = (
        new_successes == new_turns
        and followup_successes == followups
        and replacements == 3
        and sandbox_replacements >= min(3, followups)
        and deletion_passed
        and marked == len(requests)
        and quality_by_harness["pi"] >= quality_by_harness["claude"]
        and all(value["pi"] >= value["claude"] for value in per_stratum.values())
        and latency.get("pi", {}).get("transcript_failures", 1) == 0
    )
    return {
        "status": "passed" if passed else "failed",
        "run_id": run_id,
        "release_id": settings.release_id,
        "suite_version": suite["version"],
        "consent_contract": suite["consent_contract"],
        "comparison_control_sha256": control_digest,
        "requested": {"admin_new_turns": new_turns, "admin_followups": followups},
        "observed": {
            "admin_new_successes": new_successes,
            "admin_followup_successes": followup_successes,
            "sandbox_replacements": sandbox_replacements,
            "edit_retry_successes": replacements,
            "deletion_passed": deletion_passed,
            "qualification_rows_marked": marked,
        },
        "quality": {
            "paired_tasks": len(tasks),
            "passed_by_harness": quality_by_harness,
            "per_stratum": per_stratum,
            "results": quality,
        },
        "latency_cost_reliability": latency,
        "decision_gates": {
            "reused_browser_reasoning": reuse_gate,
            "note": "HTTP qualification does not synthesize browser-render timings.",
        },
    }, passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--admin-subject", required=True)
    parser.add_argument("--qualification-owner", required=True)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--new-turns", type=int, default=50)
    parser.add_argument("--followups", type=int, default=50)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if args.new_turns < 50 or args.followups < 50:
        raise SystemExit(
            "Pi qualification requires at least 50 new turns and follow-ups"
        )
    environment = get_settings()
    settings = settings_for_release(args.release_dir).model_copy(
        update={
            "session_cookie_name": environment.session_cookie_name,
            "jwt_secret": environment.jwt_secret,
            "hf_token": environment.hf_token,
        }
    )
    report, passed = asyncio.run(
        _run(
            settings,
            admin_subject=args.admin_subject,
            qualification_owner=args.qualification_owner,
            admin_username=args.admin_username,
            new_turns=args.new_turns,
            followups=args.followups,
        )
    )
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
