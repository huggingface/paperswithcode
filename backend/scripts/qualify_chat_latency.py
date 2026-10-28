#!/usr/bin/env python3
"""Run a naturally paced, explicitly tagged staging latency cohort."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

from sqlalchemy import func, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxPool, ChatTurnLatency
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import settings_for_release
from backend.scripts.staging_qualification_http import client as staging_client
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.hf_inference_billing_service import COOKIE_NAME, encrypt_token

CONFIRMATION = "QUALIFY_STAGING_CHAT_LATENCY"
PROMPT = "Reply with one concise acknowledgement."


async def _wait_for_blank(release, *, model: str, reasoning_effort: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with db_manager.session_local() as db:
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(
                        ChatSandboxPool.state == "blank_ready",
                        ChatSandboxPool.image_version
                        == release.chat_modal_image_version,
                        ChatSandboxPool.worker_contract_version
                        == release.chat_worker_contract_version,
                        ChatSandboxPool.model_profile == model,
                        ChatSandboxPool.reasoning_profile == reasoning_effort,
                    )
                )
                or 0
            )
        if count:
            return
        await asyncio.sleep(0.25)
    raise RuntimeError("compatible blank worker did not become ready")


async def _turn(
    client: object,
    *,
    session_id: str | None = None,
    model: str,
    reasoning_effort: str,
) -> tuple[str, str]:
    payload = {
        "message": PROMPT,
        "client_message_id": str(uuid.uuid4()),
    }
    if session_id is None:
        payload["initial_model"] = model
        payload["reasoning_effort"] = reasoning_effort
    if session_id is not None:
        payload["session_id"] = session_id
    request_id = None
    landed_session = session_id
    terminal = None
    async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "stream_start":
                request_id = event["request_id"]
                landed_session = event["session_id"]
            if event["type"] in {"done", "error"}:
                terminal = event["type"]
    if request_id is None or landed_session is None or terminal != "done":
        raise RuntimeError("focused latency turn did not complete")
    return request_id, landed_session


async def qualify(
    release_dir: Path, sessions: int, *, model: str, reasoning_effort: str
) -> dict:
    environment = get_settings()
    release = settings_for_release(release_dir)
    if environment.environment != "staging":
        raise RuntimeError("Latency qualification requires staging")
    run_id = uuid.uuid4().hex[:12]
    request_ids: list[str] = []
    for index in range(sessions):
        await _wait_for_blank(release, model=model, reasoning_effort=reasoning_effort)
        subject = f"latency-gate-{run_id}-{index}"
        auth = _encode_legacy_session({"sub": subject, "username": subject})
        billing = encrypt_token(environment.hf_token, subject, environment)
        async with staging_client(
            timeout=240,
            cookies={
                environment.session_cookie_name: auth,
                COOKIE_NAME: billing,
            },
        ) as client:
            first_request, session_id = await _turn(
                client, model=model, reasoning_effort=reasoning_effort
            )
            followup_request, _ = await _turn(
                client,
                session_id=session_id,
                model=model,
                reasoning_effort=reasoning_effort,
            )
            request_ids.extend([first_request, followup_request])

    request_uuids = [uuid.UUID(request_id) for request_id in request_ids]
    with db_manager.session_local() as db:
        service = ChatLatencyService(db)
        marked = sum(
            service.mark_qualification(
                request_id,
                run_id=run_id,
                scenario="focused_latency",
            )
            for request_id in request_ids
        )
        rows = list(
            db.execute(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.request_id.in_(request_uuids)
                )
            ).scalars()
        )
        new_rows = [row for row in rows if row.traffic_class == "new_chat"]
        followup_rows = [row for row in rows if row.traffic_class == "followup"]
        report = {
            "run_id": run_id,
            "sessions": sessions,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "rows": len(rows),
            "marked": marked,
            "new_pool_hits": sum(
                row.acquisition_outcome == "pool_hit" for row in new_rows
            ),
            "followup_reused": sum(
                row.acquisition_outcome == "reused_session" for row in followup_rows
            ),
            "complete": sum(row.terminal_status == "complete" for row in rows),
            "release_ids": sorted({row.app_release_id for row in rows}),
            "contracts": sorted({row.worker_contract_version for row in rows}),
        }
        db.commit()
    if (
        len(rows) != sessions * 2
        or marked != sessions * 2
        or report["new_pool_hits"] != sessions
        or report["followup_reused"] != sessions
        or report["complete"] != sessions * 2
        or report["release_ids"] != [release.release_id]
        or report["contracts"] != [release.chat_worker_contract_version]
    ):
        raise RuntimeError("focused latency cohort failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=25)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--reasoning-effort", choices=("low", "medium", "high", "max"), default="low"
    )
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not 1 <= args.sessions <= 100:
        raise SystemExit("--sessions must be 1-100")
    print(
        json.dumps(
            asyncio.run(
                qualify(
                    args.release_dir,
                    args.sessions,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                )
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
