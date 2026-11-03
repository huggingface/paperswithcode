"""Entrypoint for a remote, shadow-only Papers With Code Pi curation Job.

Runs the same bootstrap, preflight, prompt, and callbacks as the Codex runner,
whose module ships beside this file in the Pi image, but drives the Pi harness
on an open model through Hugging Face Inference Providers. The server stores a
Pi proposal for comparison and never applies it.
"""

from __future__ import annotations

import base64
import gzip
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import run_paper_curation as base

PROVIDER = os.environ.get("PWC_CURATION_PI_PROVIDER", "")
BILL_TO = os.environ.get("PWC_CURATION_PI_BILL_TO", "huggingface")
AGENT_DIR = Path("/tmp/pi-agent")
PROVIDER_NAME = "pwc-hf"
TOOLS = "read,bash,edit,write,grep,find,ls"


def _model_entry(model_id: str) -> dict:
    return {
        "id": model_id,
        "name": model_id,
        "reasoning": True,
        "input": ["text"],
        # Pi compacts against the declared window; the model's 1M tail is
        # slower and costlier than one paper plus its context needs.
        "contextWindow": 262_144,
        "maxTokens": 32_768,
        "cost": {"input": 0.3, "output": 1.2, "cacheRead": 0, "cacheWrite": 0},
        "samplingParams": {"temperature": 1.0, "top_p": 1.0},
        # Probed 2026-11-02: the router accepts thinking={"type":"enabled"},
        # streams reasoning_content, returns OpenAI tool_calls, and accepts
        # replayed reasoning_content across tool turns.
        "compat": {"thinkingFormat": "deepseek", "supportsDeveloperRole": False},
    }


def write_models_config() -> list[str]:
    """Write Pi's provider config; return the model ids to try, in order."""
    model_ids = [f"{base.MODEL}:{PROVIDER}"] if PROVIDER else []
    model_ids.append(base.MODEL)
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    (AGENT_DIR / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    PROVIDER_NAME: {
                        "baseUrl": "https://router.huggingface.co/v1",
                        "api": "openai-completions",
                        "apiKey": "$HF_TOKEN",
                        "headers": {"X-HF-Bill-To": BILL_TO},
                        "models": [_model_entry(model_id) for model_id in model_ids],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return model_ids


def _events() -> list[dict]:
    events = []
    raw = base.EVENTS.read_bytes() if base.EVENTS.exists() else b""
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _assistant_messages(events: list[dict]) -> list[dict]:
    return [
        event["message"]
        for event in events
        if event.get("type") == "message_end"
        and isinstance(event.get("message"), dict)
        and event["message"].get("role") == "assistant"
    ]


def final_report(events: list[dict]) -> str:
    messages = _assistant_messages(events)
    if not messages:
        return ""
    return "\n".join(
        block.get("text", "")
        for block in messages[-1].get("content") or []
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def usage_totals(events: list[dict]) -> dict[str, int]:
    """Sum per-response usage; Pi reports each response, not a running total."""
    totals = {"input_tokens": 0, "output_tokens": 0}
    for message in _assistant_messages(events):
        usage = message.get("usage") or {}
        totals["input_tokens"] += sum(
            int(usage.get(key) or 0) for key in ("input", "cacheRead", "cacheWrite")
        )
        totals["output_tokens"] += int(usage.get("output") or 0)
    return totals


def ended_with_provider_error(events: list[dict]) -> bool:
    messages = _assistant_messages(events)
    return bool(messages) and messages[-1].get("stopReason") == "error"


def run_pi(model_id: str, prompt: str, env: dict, timeout: float) -> int:
    command = [
        "pi",
        "--mode",
        "json",
        "--print",
        "--no-session",
        "--no-context-files",
        "--no-skills",
        "--no-extensions",
        "--no-prompt-templates",
        "--no-mcp",
        "--offline",
        "--provider",
        PROVIDER_NAME,
        "--model",
        model_id,
        "--thinking",
        base.REASONING_EFFORT,
        "--tools",
        TOOLS,
        prompt,
    ]
    with base.EVENTS.open("ab") as event_file:
        return subprocess.run(
            command,
            stdout=event_file,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=base.WORKTREE,
            timeout=timeout,
            check=False,
        ).returncode


def _submitted() -> bool:
    return isinstance(base.api_request("context").get("job", {}).get("proposal"), dict)


def main() -> int:
    try:
        base.bootstrap_worktree()
        context = base.api_request("context")
        preflight = base.run_url_preflight(context)
        base.URL_CANDIDATES.write_text(json.dumps(preflight), encoding="utf-8")
        if preflight.get("awaiting_markdown"):
            sys.path.insert(0, str(base.WORKTREE))
            from jobs.curation_failure_codes import (  # noqa: PLC0415
                AWAITING_MARKDOWN,
                format_failure,
            )

            raise base.SourceEvidenceIncomplete(
                format_failure(
                    AWAITING_MARKDOWN,
                    "Awaiting paper Markdown extraction: "
                    + str(context["paper"].get("arxiv_id") or "unknown"),
                )
            )
        if base.KIND == "enrich-paper" and not preflight.get("complete"):
            failed_sources = sorted(
                {
                    str(item.get("source") or "unknown")
                    for item in preflight.get("errors") or []
                }
            )
            empty_events = base64.b64encode(gzip.compress(b"")).decode()
            base.trace_callback(
                "trace/preapply",
                {
                    "proposal": {},
                    "events_gzip_b64": empty_events,
                    "prompt": "Deterministic URL preflight failed before Pi execution.",
                    "url_candidates": preflight,
                },
            )
            base.trace_callback(
                "trace/finalize",
                {
                    "events_gzip_b64": empty_events,
                    "result": {
                        "status": "source_evidence_incomplete",
                        "failed_sources": failed_sources,
                    },
                    "benchmark_gaps": [],
                    "report": "URL source evidence preflight was incomplete.",
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                    "duration_ms": 0,
                },
            )
            raise base.SourceEvidenceIncomplete(
                "URL source evidence preflight incomplete: " + ", ".join(failed_sources)
            )

        prompt = base._prompt(context)
        model_ids = write_models_config()
        run_env = {
            **os.environ,
            "PI_CODING_AGENT_DIR": str(AGENT_DIR),
            "PI_TELEMETRY": "0",
            "PWC_CURATION_EVENTS_PATH": str(base.EVENTS),
            "PWC_CURATION_PROMPT": prompt,
        }
        # Source fetching is complete; the agent keeps only its callback token
        # and the inference-only HF token Pi needs for every model request.
        run_env.pop("PWC_PAPER_MARKDOWN_HF_TOKEN", None)
        limit = 1800 if base.KIND == "add-evals" else 1200
        started = time.monotonic()
        returncode = run_pi(model_ids[0], prompt, run_env, limit)
        remaining = limit - (time.monotonic() - started)
        # The pinned provider can fail outright; retry once on automatic routing.
        if (
            len(model_ids) > 1
            and remaining > 300
            and ended_with_provider_error(_events())
            and not _submitted()
        ):
            returncode = run_pi(model_ids[1], prompt, run_env, remaining)
        duration_ms = int((time.monotonic() - started) * 1000)
        events = _events()
        report = final_report(events)
        trace_error = None
        try:
            payload = base._trace_payload(report, duration_ms)
            payload["usage"] = usage_totals(events)
            base.trace_callback("trace/finalize", payload)
        except Exception as exc:
            trace_error = f"Trace finalization failed ({type(exc).__name__})."
        error = f"Pi exited with status {returncode}." if returncode else trace_error
        completion = base.complete({"report": report, "error": error})
        return 1 if completion.get("status") == "failed" else 0
    except subprocess.TimeoutExpired:
        try:
            base.complete(
                {"report": "", "error": f"{base.KIND} timed out at its stage limit."}
            )
        except (OSError, http.client.HTTPException):
            pass
        return 1
    except Exception as exc:
        try:
            error = (
                str(exc)
                if isinstance(exc, base.SourceEvidenceIncomplete)
                else f"Remote runner failed ({type(exc).__name__})."
            )
            base.complete({"report": "", "error": error})
        except (OSError, http.client.HTTPException):
            pass
        return 1
    finally:
        shutil.rmtree(base.WORKTREE, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
