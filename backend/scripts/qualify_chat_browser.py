#!/usr/bin/env python3
"""Qualify browser-rendered reasoning TTFT through the staging React chat UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import subprocess
import tempfile
import time
import uuid
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from websockets.sync.client import connect

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatTurnLatency
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_sandbox import (
    merge_release_settings,
    settings_for_release,
)
from backend.scripts.report_chat_ttft import report
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.hf_inference_billing_service import COOKIE_NAME, encrypt_token
from backend.services.chat_sandbox_service import SandboxSessionManager

CONFIRMATION = "QUALIFY_STAGING_CHAT_BROWSER"
ORIGIN = "https://staging.paperswithcode.co"
CHAT_MODEL_STORAGE_KEY = "pwc:chat-oauth-model"
CHAT_REASONING_EFFORT_STORAGE_KEY = "pwc:chat-reasoning-effort"


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _connect_devtools(url: str):
    """Keep the local CDP channel alive while model turns are in flight."""

    return connect(url, open_timeout=5, ping_interval=None)


class ChromePage(AbstractContextManager):
    """Small synchronous Chrome DevTools client with no browser test dependency."""

    def __init__(self, *, cookies: dict[str, str], timeout: float = 240) -> None:
        self.cookies = cookies
        self.timeout = timeout
        self._profile = tempfile.TemporaryDirectory(
            prefix="pwc-chat-browser-", ignore_cleanup_errors=True
        )
        self._process: subprocess.Popen[str] | None = None
        self._socket = None
        self._next_id = 0

    def __enter__(self):
        port = _free_port()
        self._process = subprocess.Popen(
            [
                "/usr/bin/google-chrome",
                "--headless=new",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={self._profile.name}",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env={
                "HOME": self._profile.name,
                "XDG_CACHE_HOME": self._profile.name,
                "XDG_CONFIG_HOME": self._profile.name,
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
            },
        )
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        while True:
            if self._process.poll() is not None:
                raise RuntimeError("Headless Chrome exited before DevTools was ready")
            try:
                target = httpx.put(
                    f"{base}/json/new?{quote('about:blank')}", timeout=1
                ).json()
                break
            except (httpx.HTTPError, ValueError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Chrome DevTools did not become ready")
                time.sleep(0.1)
        self._socket = _connect_devtools(target["webSocketDebuggerUrl"])
        self.command("Network.enable")
        self.command("Page.enable")
        self.command("Runtime.enable")
        for name, value in self.cookies.items():
            result = self.command(
                "Network.setCookie",
                {
                    "name": name,
                    "value": value,
                    "url": ORIGIN,
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                },
            )
            if not result.get("success"):
                raise RuntimeError(f"Chrome rejected protected cookie {name}")
        self.navigate("/chat")
        return self

    def __exit__(self, *_args):
        if self._socket is not None:
            self._socket.close()
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._profile.cleanup()
        return False

    def command(self, method: str, params: dict[str, Any] | None = None) -> dict:
        if self._socket is None:
            raise RuntimeError("Chrome page is not open")
        self._next_id += 1
        command_id = self._next_id
        self._socket.send(
            json.dumps({"id": command_id, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(self._socket.recv(timeout=self.timeout))
            if message.get("id") != command_id:
                continue
            if "error" in message:
                raise RuntimeError(f"Chrome DevTools error: {message['error']}")
            return message.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )["result"]
        if result.get("subtype") == "error":
            raise RuntimeError(result.get("description") or "Browser evaluation failed")
        return result.get("value")

    def wait_for(self, expression: str, *, timeout: float | None = None) -> Any:
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            value = self.evaluate(expression)
            if value:
                return value
            time.sleep(0.05)
        raise TimeoutError(f"Browser condition timed out: {expression[:120]}")

    def navigate(self, path: str) -> None:
        self.command("Page.navigate", {"url": f"{ORIGIN}{path}"})
        encoded_path = json.dumps(path.partition("?")[0])
        self.wait_for(
            f"location.pathname === {encoded_path} && "
            "document.readyState === 'complete' && "
            "Boolean(document.querySelector('textarea[role=combobox]'))",
            timeout=30,
        )

    def select_model(self, model: str, *, only_available: bool = False) -> None:
        encoded = json.dumps(model)
        storage_key = json.dumps(CHAT_MODEL_STORAGE_KEY)
        if only_available:
            self.wait_for(
                "Boolean(document.querySelector('[aria-label=\"Research model\"]'))"
            )
            self.evaluate(f"sessionStorage.setItem({storage_key},{encoded})")
            return
        self.wait_for(
            "(() => {"
            "const select=document.querySelector('select[aria-label=\"Research model\"]');"
            f"return Boolean(select && [...select.options].some(option=>option.value==={encoded}));"
            "})()"
        )
        selected = self.evaluate(
            "(() => {"
            "const select=document.querySelector('select[aria-label=\"Research model\"]');"
            f"if(!select || ![...select.options].some(option=>option.value==={encoded})) "
            "return false;"
            f"select.value={encoded};"
            "select.dispatchEvent(new Event('change',{bubbles:true}));"
            f"sessionStorage.setItem({storage_key},{encoded});"
            "return true;})()"
        )
        if not selected:
            raise RuntimeError(f"Research model is unavailable: {model}")
        self.wait_for(
            f"document.querySelector('select[aria-label=\"Research model\"]').value==={encoded}"
        )
        self.wait_for(f"sessionStorage.getItem({storage_key})==={encoded}")

    def select_reasoning_effort(self, effort: str) -> None:
        labels = {"low": "Low", "high": "High", "max": "Max"}
        label = labels[effort]
        encoded_label = json.dumps(label)
        storage_key = json.dumps(CHAT_REASONING_EFFORT_STORAGE_KEY)
        encoded_effort = json.dumps(effort)
        self.wait_for(
            "Boolean(document.querySelector('button[aria-label^=\"Reasoning effort:\"]'))"
        )
        opened = self.evaluate(
            "(() => {"
            "const trigger=document.querySelector('button[aria-label^=\"Reasoning effort:\"]');"
            "if(!trigger) return false;"
            "trigger.click();"
            "return true;})()"
        )
        if not opened:
            raise RuntimeError("Reasoning effort picker is unavailable")
        self.wait_for("Boolean(document.querySelector('[role=\"listbox\"]'))")
        selected = self.evaluate(
            "(() => {"
            "const options=[...document.querySelectorAll('[role=\"option\"]')];"
            f"const option=options.find(node=>node.querySelector('strong')?.textContent==={encoded_label});"
            "if(!option) return false;"
            "option.click();"
            f"sessionStorage.setItem({storage_key},{encoded_effort});"
            "return true;})()"
        )
        if not selected:
            raise RuntimeError(f"Reasoning effort is unavailable: {effort}")
        encoded_aria_label = json.dumps(f"Reasoning effort: {label}")
        self.wait_for(
            "document.querySelector('button[aria-label^=\"Reasoning effort:\"]')"
            f"?.getAttribute('aria-label')==={encoded_aria_label}"
        )
        self.wait_for(f"sessionStorage.getItem({storage_key})==={encoded_effort}")

    def assert_release(self, expected: str) -> None:
        actual = self.evaluate(
            "fetch('/health',{cache:'no-store'})"
            ".then(response=>response.ok ? response.json() : null)"
            ".then(payload=>payload?.release_id ?? null)"
        )
        if actual != expected:
            raise RuntimeError(
                f"Staging release changed during qualification: {actual or 'unknown'}"
            )

    def send_turn(self, prompt: str) -> dict[str, Any]:
        before = int(
            self.evaluate("document.querySelectorAll('.chat-msg-assistant').length")
        )
        encoded = json.dumps(prompt)
        submitted = self.evaluate(
            "(() => {"
            "const input=document.querySelector('textarea[role=combobox]');"
            "const send=document.querySelector('button[aria-label=\"Send message\"]');"
            "if(!input || !send) return false;"
            "const setter=Object.getOwnPropertyDescriptor("
            "HTMLTextAreaElement.prototype,'value').set;"
            f"setter.call(input,{encoded});"
            "input.dispatchEvent(new Event('input',{bubbles:true}));"
            "input.dispatchEvent(new Event('change',{bubbles:true}));"
            "return true;})()"
        )
        if not submitted:
            raise RuntimeError("The chat composer was not ready")
        self.wait_for(
            "Boolean(document.querySelector('button[aria-label=\"Send message\"]')"
            " && !document.querySelector('button[aria-label=\"Send message\"]').disabled)"
        )
        self.evaluate(
            "document.querySelector('button[aria-label=\"Send message\"]').click()"
        )
        self.wait_for(
            f"location.origin !== {json.dumps(ORIGIN)} || "
            f"document.querySelectorAll('.chat-msg-assistant').length > {before}"
        )
        current_origin = str(self.evaluate("location.origin"))
        if current_origin != ORIGIN:
            raise RuntimeError(
                f"Browser left the protected staging origin: {current_origin}"
            )
        reasoning = False
        tool = False
        answer = False
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            state = self.evaluate(
                "(() => {"
                "const last=[...document.querySelectorAll('.chat-msg-assistant')].at(-1);"
                "if(!last) return null;"
                "const text=(selector)=>[...last.querySelectorAll(selector)]"
                ".some(node=>Boolean(node.textContent.trim()));"
                "return {"
                "reasoning:text('.chat-reason-live-body,.chat-reason-done-body'),"
                "tool:Boolean(last.querySelector('.chat-tool')) ,"
                "answer:text('.chat-answer:not(.chat-reason-markdown)'),"
                "busy:Boolean(document.querySelector('button[aria-label=\"Stop generating\"]')) ,"
                "error:Boolean(last.querySelector('.chat-error')) ,"
                "path:location.pathname};})()"
            )
            if state:
                reasoning = reasoning or bool(state["reasoning"])
                tool = tool or bool(state["tool"])
                answer = answer or bool(state["answer"])
                if state["error"]:
                    raise RuntimeError("The browser rendered a chat error")
                if not state["busy"] and (reasoning or tool or answer):
                    return {
                        "reasoning": reasoning,
                        "tool": tool,
                        "answer": answer,
                        "path": str(state["path"]),
                    }
            time.sleep(0.05)
        raise TimeoutError("The browser turn did not reach a terminal render")


def _mark_and_report(
    *, settings, session_ids: set[uuid.UUID], started_at: datetime, run_id: str
) -> tuple[int, dict[str, Any]]:
    with db_manager.session_local() as db:
        rows = list(
            db.scalars(
                select(ChatTurnLatency).where(
                    ChatTurnLatency.chat_session_id.in_(session_ids),
                    ChatTurnLatency.admitted_at >= started_at,
                )
            )
        )
        latency = ChatLatencyService(db)
        marked = sum(
            latency.mark_qualification(
                str(row.request_id), run_id=run_id, scenario="focused_latency"
            )
            for row in rows
        )
        db.commit()
    result = report(
        argparse.Namespace(
            release_id=settings.release_id,
            image_id=settings.chat_modal_image_version,
            model=settings.chat_effective_pi_prewarm_model,
            after=started_at,
            run_id=run_id,
            pool_target=settings.chat_blank_pool_min,
            cpu=settings.chat_sandbox_cpu,
            memory_mib=settings.chat_sandbox_memory_mib,
            minimum_reliability=0.99,
        )
    )
    return marked, result


def _new_chat_acquisition_outcome(
    *, session_id: uuid.UUID, started_at: datetime
) -> str:
    """Return the persisted acquisition outcome for one completed browser pair."""

    with db_manager.session_local() as db:
        outcome = db.scalar(
            select(ChatTurnLatency.acquisition_outcome)
            .where(
                ChatTurnLatency.chat_session_id == session_id,
                ChatTurnLatency.traffic_class == "new_chat",
                ChatTurnLatency.admitted_at >= started_at,
            )
            .order_by(ChatTurnLatency.admitted_at.desc())
            .limit(1)
        )
    if outcome not in {"pool_hit", "pool_miss"}:
        raise RuntimeError(
            f"Missing new-chat acquisition outcome for session {session_id}"
        )
    return outcome


def reasoning_minimum_reached(
    *, rendered: dict[str, int], minimum_reasoning: int
) -> bool:
    return bool(
        rendered["new_pool_hit_semantic"] >= minimum_reasoning
        and rendered["followup_semantic"] >= minimum_reasoning
    )


def qualification_passes(
    *,
    rendered: dict[str, int],
    minimum_reasoning: int,
    gates: dict[str, bool],
    marked: int,
    session_count: int,
) -> bool:
    return bool(
        reasoning_minimum_reached(
            rendered=rendered, minimum_reasoning=minimum_reasoning
        )
        and all(
            gates[name]
            for name in (
                "component",
                "model_to_application",
                "pool_browser",
                "reused_browser",
                "reliability",
                "accounting",
                "isolation",
            )
        )
        and marked == session_count * 2
    )


def pilot_passes(
    *, rendered: dict[str, int], pairs: int, marked: int, session_count: int
) -> bool:
    """Accept a bounded visible-semantic smoke without claiming qualification."""

    return bool(
        session_count == pairs
        and marked == pairs * 2
        and rendered["new_semantic"] == pairs
        and rendered["followup_semantic"] == pairs
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--admin-subject", required=True)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--qualification-owner", required=True)
    parser.add_argument("--minimum-reasoning", type=int, default=50)
    parser.add_argument("--maximum-pairs", type=int, default=150)
    parser.add_argument("--pilot-pairs", type=int, default=0)
    parser.add_argument("--new-chat-spacing-seconds", type=float, default=30)
    parser.add_argument("--model")
    parser.add_argument(
        "--reasoning-effort", choices=("low", "medium", "high", "max"), default="low"
    )
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    if not args.qualification_owner.startswith("operator:pi-qualification:"):
        raise SystemExit("--qualification-owner must be a protected Pi operator run")
    if args.pilot_pairs and not 1 <= args.pilot_pairs <= 10:
        raise SystemExit("--pilot-pairs must be 1-10")
    if not args.pilot_pairs and not (
        50 <= args.minimum_reasoning <= args.maximum_pairs <= 150
    ):
        raise SystemExit("require 50 <= minimum reasoning <= maximum pairs <= 150")
    if not 15 <= args.new_chat_spacing_seconds <= 300:
        raise SystemExit("new-chat spacing must be 15-300 seconds")

    environment = get_settings()
    settings = merge_release_settings(
        environment, settings_for_release(args.release_dir)
    )
    if (
        settings.environment != "staging"
        or settings.chat_default_agent_harness != "pi"
        or settings.chat_new_session_pi_percentage != 100
        or not settings.chat_pi_prewarm_enabled
    ):
        raise SystemExit("browser qualification requires the sealed staging Pi runtime")
    selected_model = args.model or settings.chat_model_choices[0]["id"]
    available_models = {choice["id"]: choice for choice in settings.chat_model_choices}
    if selected_model not in available_models:
        raise SystemExit("--model must be present in staging model discovery")
    if (
        available_models[selected_model]["route"]
        != settings.chat_effective_pi_prewarm_model
    ):
        raise SystemExit("selected model must match the staging Pi prewarm profile")
    if args.reasoning_effort != settings.chat_pi_prewarm_reasoning_effort:
        raise SystemExit(
            "selected reasoning effort must match the staging Pi prewarm profile"
        )
    token = _encode_legacy_session(
        {
            "sub": args.admin_subject,
            "username": args.admin_username,
            "chat_qualification_owner": args.qualification_owner,
        }
    )
    billing = encrypt_token(environment.hf_token, args.qualification_owner, environment)
    started_at = datetime.now(UTC)
    run_id = uuid.uuid4().hex[:12]
    session_ids: set[uuid.UUID] = set()
    rendered = {
        "new_reasoning": 0,
        "new_pool_hit_reasoning": 0,
        "new_tool": 0,
        "new_answer": 0,
        "new_semantic": 0,
        "new_pool_hit_semantic": 0,
        "followup_reasoning": 0,
        "followup_tool": 0,
        "followup_answer": 0,
        "followup_semantic": 0,
    }
    last_new_started = 0.0
    manager = SandboxSessionManager(settings)

    async def cleanup() -> None:
        for session_id in session_ids:
            await manager.terminate(session_id)

    try:
        with ChromePage(
            cookies={settings.session_cookie_name: token, COOKIE_NAME: billing}
        ) as page:
            target_pairs = args.pilot_pairs or args.maximum_pairs
            for _index in range(target_pairs):
                remaining = args.new_chat_spacing_seconds - (
                    time.monotonic() - last_new_started
                )
                if remaining > 0:
                    time.sleep(remaining)
                page.navigate(f"/chat?model={quote(selected_model)}")
                page.assert_release(settings.release_id)
                page.select_model(
                    selected_model, only_available=len(available_models) == 1
                )
                page.select_reasoning_effort(args.reasoning_effort)
                last_new_started = time.monotonic()
                new = page.send_turn(
                    "Reason briefly, then state one concise reason benchmarks matter."
                )
                session_id = uuid.UUID(new["path"].removeprefix("/chat/").split("/")[0])
                session_ids.add(session_id)
                rendered["new_reasoning"] += int(new["reasoning"])
                acquisition_outcome = _new_chat_acquisition_outcome(
                    session_id=session_id, started_at=started_at
                )
                rendered["new_pool_hit_reasoning"] += int(
                    new["reasoning"] and acquisition_outcome == "pool_hit"
                )
                rendered["new_tool"] += int(new["tool"])
                rendered["new_answer"] += int(new["answer"])
                rendered["new_semantic"] += int(
                    new["reasoning"] or new["tool"] or new["answer"]
                )
                rendered["new_pool_hit_semantic"] += int(
                    acquisition_outcome == "pool_hit"
                    and (new["reasoning"] or new["tool"] or new["answer"])
                )
                page.assert_release(settings.release_id)
                followup = page.send_turn(
                    "Reason briefly, then restate that evidence in different words."
                )
                rendered["followup_reasoning"] += int(followup["reasoning"])
                rendered["followup_tool"] += int(followup["tool"])
                rendered["followup_answer"] += int(followup["answer"])
                rendered["followup_semantic"] += int(
                    followup["reasoning"] or followup["tool"] or followup["answer"]
                )
                if (
                    reasoning_minimum_reached(
                        rendered=rendered, minimum_reasoning=args.minimum_reasoning
                    )
                    and len(session_ids) >= 50
                ):
                    break
    finally:
        asyncio.run(cleanup())

    marked, gate_report = _mark_and_report(
        settings=settings,
        session_ids=session_ids,
        started_at=started_at,
        run_id=run_id,
    )
    gates = gate_report["gates"]
    if args.pilot_pairs:
        passed = pilot_passes(
            rendered=rendered,
            pairs=args.pilot_pairs,
            marked=marked,
            session_count=len(session_ids),
        )
    else:
        passed = qualification_passes(
            rendered=rendered,
            minimum_reasoning=args.minimum_reasoning,
            gates=gates,
            marked=marked,
            session_count=len(session_ids),
        )
    status = (
        ("pilot_passed" if passed else "pilot_failed")
        if args.pilot_pairs
        else ("passed" if passed else "failed")
    )
    print(
        json.dumps(
            {
                "status": status,
                "mode": "pilot" if args.pilot_pairs else "qualification",
                "run_id": run_id,
                "model": selected_model,
                "rendered": rendered,
                "session_count": len(session_ids),
                "qualification_rows_marked": marked,
                "report": gate_report,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
