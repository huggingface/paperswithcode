"""Off-box research agent for AI conference deadlines (runs on Hugging Face Jobs).

Ported from huggingface/ai-deadlines ``agents/`` (agent.py + pipeline_utils.py,
including the Aug 2026 hardening): N retrieval agents research one conference
sequentially, an aggregation agent majority-votes only when some agent proposed
an update, every agent has a per-agent wall-clock cap, a fail-closed tool budget
(PostToolUse "answer now" nudge, PreToolUse deny, no-tools follow-up after
``error_max_turns``), SDK silent-exit retries, precomputed year labels, and a
closed status enum.

What changed from upstream: the input is the series' current database rows
(a JSON manifest built on the VPS) and the output is a structured change set,
not YAML pushed to GitHub. Nothing here touches the database; the VPS validates
each change set and applies it with ``conference_deadline_service``.

This file is shipped verbatim into the Job, so it must only import the standard
library and (lazily) ``claude_agent_sdk``. Each series result is printed as one
``PWC_DEADLINE_RESULT <base64 gzip json>`` log line.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import os
import sys
import time
from typing import Any

RESULT_MARKER = "PWC_DEADLINE_RESULT"
DONE_MARKER = "PWC_DEADLINE_DONE"
STATUSES = ("proposed", "no_changes", "error", "timeout")

DEFAULT_RETRIEVAL_MODEL = "claude-sonnet-5-5"
DEFAULT_AGGREGATION_MODEL = "claude-opus-5-5"

SEARCH_TOOLS = ["WebSearch", "WebFetch"]

BUDGET_EXHAUSTED_MESSAGE = (
    "Your tool-call budget is exhausted. Do not search again. "
    "Return structured output now. If you found no verified upcoming deadlines, "
    "set requires_update: false."
)
BUDGET_EXHAUSTED_FOLLOWUP = (
    "Your tool-call budget is exhausted. Do not search again. "
    "Return structured output now from what you already saw. "
    "If you found no verified upcoming deadlines, set requires_update: false."
)

# (max_turns, max_budget_usd) per stage; override with e.g. RETRIEVAL_MAX_TURNS.
STAGE_LIMIT_DEFAULTS = {"retrieval": (12, 1.50), "aggregation": (8, 1.00)}
MAX_RETRIES = 3
MAX_CONSECUTIVE_AGGREGATION_FAILURES = 2
SILENT_EXIT_THRESHOLD = 2

DEADLINE_TYPES = [
    "abstract",
    "paper",
    "submission",
    "supplementary",
    "registration",
    "commitment",
    "review_release",
    "rebuttal_start",
    "rebuttal_end",
    "rebuttal_and_revision",
    "notification",
    "final_decision",
    "camera_ready",
]

_NULLABLE_STRING = {"type": ["string", "null"]}
_NULLABLE_DATE = {
    "type": ["string", "null"],
    "description": "YYYY-MM-DD",
    "pattern": r"^\d{4}-\d{2}-\d{2}$",
}

CHANGE_SET_SCHEMA = {
    "type": "object",
    "properties": {
        "requires_update": {
            "type": "boolean",
            "description": "Whether an upcoming or next edition needs new or changed data",
        },
        "reasoning": {"type": "string"},
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs used as sources for the information",
        },
        "editions": {
            "type": "array",
            "description": (
                "Only editions with new or changed data. Each lists the COMPLETE "
                "set of deadlines known for that edition."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "url": _NULLABLE_STRING,
                    "start_date": _NULLABLE_DATE,
                    "end_date": _NULLABLE_DATE,
                    "venue": _NULLABLE_STRING,
                    "city": _NULLABLE_STRING,
                    "country": _NULLABLE_STRING,
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Official pages proving this edition's data",
                    },
                    "deadlines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": DEADLINE_TYPES},
                                "label": {"type": "string"},
                                "date": {
                                    "type": "string",
                                    "description": "Local time 'YYYY-MM-DD HH:MM:SS'",
                                },
                                "timezone": {
                                    "type": "string",
                                    "description": "AoE, UTC, UTC-7, or an IANA name",
                                },
                            },
                            "required": ["type", "label", "date", "timezone"],
                        },
                    },
                },
                "required": ["year", "source_urls", "deadlines"],
            },
        },
    },
    "required": ["requires_update", "reasoning", "source_urls", "editions"],
}

RETRIEVAL_SYSTEM_PROMPT = """You are an AI assistant responsible for finding up-to-date information about a given AI conference: dates, location, venue and deadlines.

Papers with Code (https://paperswithcode.co/ai-deadlines) shows researchers every upcoming AI conference deadline, sorted chronologically. Its database stores, per conference edition (one per year): the official URL, start/end dates, venue, city, country, and a list of deadlines. Each deadline has a type, a human-readable label, a local date-time and a timezone.

## Date

Today is {date}.

## Task

Search the web and determine whether the current database rows for this conference need an update, and if so return a structured change set. You do NOT edit anything; you only research and return structured output.

## Turn budget

You have at most **{max_turns} tool-use turns** (each web search or fetch counts as one). This is a hard fail-closed budget, not a target to fill.

- After **2-3 official-page fetches** that yield no deadline content (CSS/JS-only, empty CFP, or "not yet announced"), stop. Return `requires_update: false` with reasoning that the CFP is not published or the page is unreadable. Do not keep searching.
- **Reserve the last turn for structured output.** Do not spend turn {max_turns} on another search or fetch.
- Do **not** burn remaining turns on CAPTCHA pages, cookie walls, or generic search-engine flailing.
- **One** WikiCFP (or similar aggregator) fetch is allowed as a last resort when official pages are unreadable. Do not thrash secondary sources.
- Once you have enough verified information, or once it is clear there is none, return structured output immediately.

## CRITICAL: Only research upcoming conferences

Use the precomputed year labels in the user message; do not re-derive them.

- PAST editions must not be changed. Do not research them and do not include them in `editions`.
- UPCOMING editions may be updated with verified new information (new deadline types, changed or extended deadlines, dates, venue, location).
- MISSING_NEXT_YEAR means no row exists yet for that edition: search for it, and add it only if its official call for papers or official website publishes dates. Do not invent dates if unpublished.
- UNKNOWN editions may be researched as upcoming, but do not invent dates.

## Output rules

- Only report `requires_update: true` if you found new, verified information for an upcoming or missing next edition.
- Only include data which is factual and for which you found evidence on an official page. Every edition you return needs at least one `source_urls` entry pointing at the page that states its data (the official conference website or call for papers).
- Do not copy the deadlines of year N to year N+1. Never guess a deadline from last year's calendar.
- For each edition you return, list the COMPLETE set of deadlines known for it, existing ones included, with the same `type` and `label` for deadlines that already exist so they can be matched. Leaving a deadline out never deletes it.
- Deadline `date` is the local time as published, formatted 'YYYY-MM-DD HH:MM:SS'. When only a day is published, use 23:59:59 of that day.
- When no timezone is given, use Anywhere on Earth. Always write `AoE`; never write `UTC-12` or `UTC+12`.
- Include all dates of the conference (main conference plus workshops/tutorials) in `start_date` / `end_date`.

## Deadline types

Type                   Description
-----------------------------------------------------------
abstract               Abstract submission deadline
paper                  Full paper submission
submission             General submission deadline
supplementary          Supplementary material deadline
registration           Paper registration deadline
commitment             Commitment deadline (ACL Rolling Review venues)
review_release         When reviews are released to authors
rebuttal_start         Start of rebuttal period
rebuttal_end           End of rebuttal period
rebuttal_and_revision  Combined rebuttal/revision period
notification           Author notification date
final_decision         Final decision date
camera_ready           Camera-ready deadline

## Tools

* Use `WebSearch` with short queries like "CVPR 2027", "EMNLP 2027 call for papers".
* Look at the previous edition's URL pattern: if CVPR 2026 is at `cvpr.thecvf.com/Conferences/2026`, try the same pattern for the next year.
* Prefer the official website (domain containing the conference acronym and year) over aggregators.
"""

RETRIEVAL_USER_PROMPT = """Please look at the data for the following conference, search the web for up-to-date information, and return your findings as structured output.

## Conference

Name: {title} (series `{series}`)

## Current database rows (JSON)

{conference_data}

## Today and year labels

{year_labels}

## Turn budget

You have at most **{max_turns} tool-use turns**. After 2-3 official-page fetches with no deadline content, return `requires_update: false` (CFP not published / page unreadable). Reserve the last turn for structured output. Do not thrash CAPTCHA pages or search-engine results. One WikiCFP (or similar) last-resort fetch is allowed.

## Instructions

1. **Use the precomputed year labels above.** PAST editions must not be modified. Only UPCOMING editions and a MISSING_NEXT_YEAR edition are eligible.
2. Search the web for the latest information about the upcoming / next edition(s) (dates, deadlines, location, venue).
3. Compare what you find with the current rows for those editions.
4. Return structured output with:
   - `requires_update`: true only if there is new, verified information for an upcoming or next edition
   - `reasoning`: why an update is or isn't needed; state which editions you considered upcoming vs past
   - `source_urls`: the URLs you used
   - `editions`: only the editions with new or changed data, each with its official `source_urls` and its complete deadline list (empty list if no update)
"""

AGGREGATION_SYSTEM_PROMPT = """You are an AI assistant responsible for synthesizing and verifying the findings of multiple colleague agents who independently researched the same AI conference.

## Date

Today is {date}.

## Task

You have received structured results from multiple retrieval agents, each of whom independently searched the web for up-to-date information about **{title}**. Your job is to:

1. **Compare** the results across all agents, noting where they agree and disagree.
2. **Majority vote** on each field: prefer values that multiple agents agree on.
3. **Verify disputed facts**: when agents disagree on a factual claim (dates, deadlines, venue), use web search to verify the claim against the official conference website before accepting any agent's answer. Do NOT blindly pick the majority if you can verify the truth.
4. **Synthesize** a single, authoritative change set.

## Turn budget

You have at most **{max_turns} tool-use turns**. Use them only to resolve factual disagreements between retrieval agents. Do not perform broad research; that was the retrieval agents' job. Return structured output as soon as consensus is reached.

## CRITICAL: Only accept changes for upcoming conferences

Use the precomputed year labels in the user message. Reject every proposed change to a PAST edition, even if multiple agents agree and even if the information is factually correct. Only UPCOMING editions and a MISSING_NEXT_YEAR edition are eligible.

## Rules

- Do NOT introduce new information beyond what the retrieval agents found, unless you need to resolve a factual disagreement for an upcoming edition.
- Every edition in your output needs at least one official `source_urls` entry supporting it.
- Each edition lists its COMPLETE set of deadlines, keeping existing deadlines' `type` and `label` so they can be matched. Leaving a deadline out never deletes it.
- If no agent proposes a verified change to an upcoming or next edition, report `requires_update: false` with an empty `editions` list.
- If agents disagree on whether an update is needed, update only if a majority agrees AND the proposed values are verified.
- Timezones: write `AoE` for Anywhere on Earth; never `UTC-12` or `UTC+12`.
"""

AGGREGATION_USER_PROMPT = """You are reviewing the findings of {num_agents} colleague agents who each independently researched the same conference and decided whether its data needs updating.

## Conference

Name: {title} (series `{series}`)

## Current database rows (JSON)

{conference_data}

## Today and year labels

{year_labels}

Use these labels. Do not re-classify years yourself.

## Colleague results

{retrieval_results}

## Instructions

1. Discard any proposal that targets a PAST edition.
2. Compare the remaining proposals: whether an update is needed, the concrete values, and their sources.
3. Majority vote, verifying disputed values on official pages.
4. Return structured output with `requires_update`, `reasoning` (how you compared the results, which editions you treated as upcoming vs past, which proposals you rejected and why), the combined `source_urls`, and the synthesized `editions`.
"""


# --- Deterministic helpers (unit-tested; no SDK) ------------------------------


class ToolBudgetState:
    """Count search-tool uses and decide the last-turn nudge / deny."""

    def __init__(self, max_turns: int):
        self.max_turns = max_turns
        self.search_uses = 0
        self.nudge_sent = False

    def on_post_tool_use(self, tool_name: str) -> str | None:
        if not is_search_tool(tool_name):
            return None
        self.search_uses += 1
        if self.search_uses >= max(self.max_turns - 1, 1) and not self.nudge_sent:
            self.nudge_sent = True
            return BUDGET_EXHAUSTED_MESSAGE
        return None

    def should_deny_pre_tool_use(self, tool_name: str) -> bool:
        return self.nudge_sent and is_search_tool(tool_name)


def is_search_tool(tool_name: str) -> bool:
    if not tool_name:
        return False
    return tool_name in {"WebSearch", "WebFetch"} or "exa" in tool_name.lower()


def stage_limits(stage: str, environ: dict | None = None) -> tuple[int, float]:
    environ = os.environ if environ is None else environ
    default_turns, default_budget = STAGE_LIMIT_DEFAULTS[stage]
    turns = environ.get(f"{stage.upper()}_MAX_TURNS") or environ.get("AGENT_MAX_TURNS")
    budget = environ.get(f"{stage.upper()}_MAX_BUDGET_USD") or environ.get(
        "AGENT_MAX_BUDGET_USD"
    )
    return (
        int(turns) if turns else default_turns,
        float(budget) if budget else default_budget,
    )


def agent_wall_clock_seconds(stage: str, environ: dict | None = None) -> float | None:
    """Per-agent wall-clock cap. Default 300s; ``0`` disables the cap."""
    environ = os.environ if environ is None else environ
    raw = environ.get(f"{stage.upper()}_WALL_CLOCK_SECONDS") or environ.get(
        "AGENT_WALL_CLOCK_SECONDS"
    )
    if raw is not None:
        value = float(raw)
        return None if value <= 0 else value
    return 300.0


def format_year_labels(manifest: dict) -> str:
    lines = [
        f"today: {manifest['today']}",
        "",
        "Year classification (precomputed; do not re-derive):",
    ]
    labels = manifest.get("year_labels") or {}
    if not labels:
        lines.append("- (no editions found)")
    for year, label in sorted(labels.items()):
        lines.append(f"- {year}: {label}")
    lines += [
        "",
        "PAST editions must not be changed.",
        "Only UPCOMING editions may be updated.",
        "MISSING_NEXT_YEAR means no row exists yet: search for it; do not invent dates if unpublished.",
        "UNKNOWN means no dates are known: search as upcoming, do not invent dates.",
    ]
    return "\n".join(lines)


def has_structured_output(result: dict) -> bool:
    return result.get("requires_update") is not None


def valid_results(results: list[dict]) -> list[dict]:
    return [r for r in results if has_structured_output(r)]


def any_proposed_update(results: list[dict]) -> bool:
    return any(r.get("requires_update") is True for r in results)


def all_agree_update(results: list[dict]) -> bool:
    valid = valid_results(results)
    return len(valid) >= 2 and all(r.get("requires_update") is True for r in valid)


def pipeline_result(
    *,
    status: str,
    reasoning: str = "",
    total_cost_usd: float = 0.0,
    change_set: dict | None = None,
    skipped_aggregation: bool = False,
    error: str | None = None,
    aggregation_failed: bool = False,
) -> dict:
    if status not in STATUSES:
        raise ValueError(f"invalid conference status: {status!r}")
    return {
        "status": status,
        "reasoning": reasoning,
        "change_set": change_set,
        "total_cost_usd": round(total_cost_usd, 4),
        "skipped_aggregation": skipped_aggregation,
        "aggregation_failed": aggregation_failed,
        "error": error,
    }


def aggregation_succeeded(result: dict) -> bool:
    """A majority vote ran and produced a verified answer."""
    return (
        not result.get("skipped_aggregation")
        and not result.get("aggregation_failed")
        and result.get("status") in ("proposed", "no_changes")
    )


def retrieval_short_circuit(results: list[dict], total_cost: float) -> dict:
    """Result when nobody proposed an update, so the majority vote is skipped."""
    valid = valid_results(results)
    if not valid and any(r.get("status") == "timeout" for r in results):
        return pipeline_result(
            status="timeout",
            reasoning="retrieval timed out before producing structured output",
            total_cost_usd=total_cost,
            skipped_aggregation=True,
            error="retrieval agent wall-clock timeout",
        )
    if not valid:
        # Research never produced an answer (SDK errors or silent exits): this
        # is a failure, not evidence that nothing changed.
        errors = sorted({str(r["error"]) for r in results if r.get("error")})
        return pipeline_result(
            status="error",
            reasoning="retrieval produced no structured output",
            total_cost_usd=total_cost,
            skipped_aggregation=True,
            error="; ".join(errors)[:1000] or "retrieval produced no structured output",
        )
    reasons = [r["reasoning"] for r in valid if r.get("reasoning")]
    reasoning = (
        max(reasons, key=len)
        if reasons
        else "retrieval agents did not propose an update"
    )
    return pipeline_result(
        status="no_changes",
        reasoning=reasoning,
        total_cost_usd=total_cost,
        skipped_aggregation=True,
    )


def encode_result_line(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{RESULT_MARKER} {base64.b64encode(gzip.compress(raw)).decode()}"


def decode_result_lines(lines: list[str]) -> list[dict]:
    results = []
    for line in lines:
        marker_at = line.find(RESULT_MARKER + " ")
        if marker_at < 0:
            continue
        encoded = line[marker_at + len(RESULT_MARKER) + 1 :].strip()
        results.append(json.loads(gzip.decompress(base64.b64decode(encoded))))
    return results


def encode_payload_bytes(raw: bytes) -> str:
    return base64.b64encode(gzip.compress(raw)).decode()


def encode_payload(value: Any) -> str:
    return encode_payload_bytes(json.dumps(value).encode())


def decode_payload_text(value: str) -> str:
    return gzip.decompress(base64.b64decode(value)).decode()


def decode_payload(value: str) -> Any:
    return json.loads(gzip.decompress(base64.b64decode(value)))


def _verbose_date(today: str) -> str:
    from datetime import date

    day = date.fromisoformat(today)
    suffix = (
        "th"
        if 11 <= day.day <= 13
        else {1: "st", 2: "nd", 3: "rd"}.get(day.day % 10, "th")
    )
    return f"{day.strftime('%A')}, the {day.day}{suffix} of {day.strftime('%B')}, {day.year}"


# --- Claude Agent SDK runner ----------------------------------------------------


def _log(label: str, text: str) -> None:
    text = text.replace("\n", " ")
    print(f"[{label}] {text[:400]}", flush=True)


def _fail_closed_hooks(max_turns: int) -> dict:
    from claude_agent_sdk import HookMatcher

    state = ToolBudgetState(max_turns)

    async def post_tool_use(input_data, _tool_use_id, _context):
        extra = state.on_post_tool_use(input_data.get("tool_name", ""))
        if not extra:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": extra,
            }
        }

    async def pre_tool_use(input_data, _tool_use_id, _context):
        if not state.should_deny_pre_tool_use(input_data.get("tool_name", "")):
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": BUDGET_EXHAUSTED_MESSAGE,
            }
        }

    return {
        "PostToolUse": [HookMatcher(hooks=[post_tool_use])],
        "PreToolUse": [HookMatcher(hooks=[pre_tool_use])],
    }


def _exa_mcp_servers() -> dict:
    """Exa MCP is opt-in: the SDK's MCP client was unstable on remote runners."""
    key = os.environ.get("EXA_API_KEY", "")
    if os.environ.get("PWC_DEADLINE_ENABLE_EXA_MCP") != "1" or not key:
        return {}
    from claude_agent_sdk.types import McpHttpServerConfig

    return {
        "exa": McpHttpServerConfig(
            type="http", url=f"https://mcp.exa.ai/mcp?exaApiKey={key}"
        )
    }


async def _consume(label: str, query_iter, state: dict) -> None:
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )

    async for message in query_iter:
        state["messages"] += 1
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    _log(label, f"Claude: {block.text}")
                elif isinstance(block, ToolUseBlock):
                    _log(label, f"Tool: {block.name}({block.input})")
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    flag = " [ERROR]" if block.is_error else ""
                    _log(label, f"result{flag}: {str(block.content)[:200]}")
        elif isinstance(message, ResultMessage):
            state["session_id"] = message.session_id
            if message.subtype in ("error_max_turns", "error_max_budget_usd"):
                _log(label, f"limit reached: {message.subtype}")
            if message.subtype == "error_max_turns":
                state["hit_max_turns"] = True
            if message.total_cost_usd:
                state["cost"] += message.total_cost_usd
            if message.structured_output:
                state["result"] = message.structured_output
            elif message.is_error and not message.subtype.startswith("error_max"):
                # Turn/budget/schema limits keep their own handling (the
                # no-tools follow-up); only API/runtime failures are errors.
                # e.g. "API Error: 400 ... does not support this model".
                detail = message.result or message.subtype or "agent run failed"
                state["result"] = {"status": "error", "error": str(detail)[:500]}


async def _run_agent_once(
    *,
    label: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_turns: int,
    max_budget_usd: float,
    wall_clock_seconds: float | None,
) -> tuple[dict, float, int]:
    from claude_agent_sdk import ClaudeAgentOptions, query

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        tools=list(SEARCH_TOOLS),
        allowed_tools=list(SEARCH_TOOLS),
        permission_mode="bypassPermissions",
        output_format={"type": "json_schema", "schema": CHANGE_SET_SCHEMA},
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers=_exa_mcp_servers(),
        hooks=_fail_closed_hooks(max_turns),
        stderr=lambda data: _log(label, f"stderr: {data.strip()}"),
    )
    state: dict = {
        "messages": 0,
        "result": {},
        "cost": 0.0,
        "session_id": None,
        "hit_max_turns": False,
    }

    async def inner() -> None:
        try:
            await _consume(label, query(prompt=user_prompt, options=options), state)
        except Exception as exc:  # The SDK surfaces CLI failures as exceptions.
            _log(label, f"error: {type(exc).__name__}: {exc}")
            state["result"] = {
                **state["result"],
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        if state["hit_max_turns"] and not has_structured_output(state["result"]):
            # One no-tools follow-up: answer from what was already seen.
            _log(label, "error_max_turns without structured output; no-tools follow-up")
            followup = ClaudeAgentOptions(
                system_prompt=system_prompt,
                model=model,
                tools=[],
                permission_mode="bypassPermissions",
                output_format={"type": "json_schema", "schema": CHANGE_SET_SCHEMA},
                max_turns=1,
                resume=state["session_id"],
            )
            follow_state = {**state, "result": {}, "hit_max_turns": False}
            try:
                await _consume(
                    label,
                    query(prompt=BUDGET_EXHAUSTED_FOLLOWUP, options=followup),
                    follow_state,
                )
            except Exception as exc:
                _log(label, f"follow-up error: {type(exc).__name__}: {exc}")
            state["cost"] = follow_state["cost"]
            state["messages"] = follow_state["messages"]
            if follow_state["result"]:
                state["result"] = follow_state["result"]

    try:
        if wall_clock_seconds:
            await asyncio.wait_for(inner(), timeout=wall_clock_seconds)
        else:
            await inner()
    except asyncio.TimeoutError:
        _log(label, f"wall-clock timeout after {wall_clock_seconds:.0f}s")
        return (
            {
                "status": "timeout",
                "error": f"agent wall-clock timeout after {wall_clock_seconds:.0f}s",
            },
            state["cost"],
            state["messages"],
        )
    return state["result"], state["cost"], state["messages"]


async def run_agent(**kwargs) -> tuple[dict, float]:
    """Retry SDK errors and silent exits (only a SystemMessage); never timeouts."""
    total = 0.0
    result: dict = {}
    for attempt in range(1, MAX_RETRIES + 1):
        result, cost, messages = await _run_agent_once(**kwargs)
        total += cost
        if result.get("status") == "timeout" or has_structured_output(result):
            return result, total
        silent_exit = not result and messages <= SILENT_EXIT_THRESHOLD
        failed = result.get("status") == "error"
        if not (silent_exit or failed) or attempt == MAX_RETRIES:
            return result, total
        _log(
            kwargs["label"],
            f"SDK error or silent exit; retrying ({attempt}/{MAX_RETRIES})",
        )
        await asyncio.sleep(2 * attempt)
    return result, total


async def research_series(manifest: dict, *, num_retrieval_agents: int) -> dict:
    """Retrieval agents -> (optional) aggregation -> change set for one series."""
    environ = os.environ
    conference_data = json.dumps(manifest["editions"], indent=1)
    labels = format_year_labels(manifest)
    date_text = _verbose_date(manifest["today"])
    retrieval_model = environ.get(
        "PWC_DEADLINE_RETRIEVAL_MODEL", DEFAULT_RETRIEVAL_MODEL
    )
    aggregation_model = environ.get(
        "PWC_DEADLINE_AGGREGATION_MODEL", DEFAULT_AGGREGATION_MODEL
    )

    turns, budget = stage_limits("retrieval")
    results: list[dict] = []
    total = 0.0
    for index in range(1, num_retrieval_agents + 1):
        result, cost = await run_agent(
            label=f"{manifest['series']}/retrieval-{index}",
            system_prompt=RETRIEVAL_SYSTEM_PROMPT.format(
                date=date_text, max_turns=turns
            ),
            user_prompt=RETRIEVAL_USER_PROMPT.format(
                title=manifest["title"],
                series=manifest["series"],
                conference_data=conference_data,
                year_labels=labels,
                max_turns=turns,
            ),
            model=retrieval_model,
            max_turns=turns,
            max_budget_usd=budget,
            wall_clock_seconds=agent_wall_clock_seconds("retrieval"),
        )
        results.append(result)
        total += cost

    if not any_proposed_update(results):
        return retrieval_short_circuit(results, total)

    turns, budget = stage_limits("aggregation")
    rendered = "".join(
        f"### Agent {i} result\n\n```json\n{json.dumps(r, indent=1)}\n```\n\n"
        for i, r in enumerate(results, 1)
    )
    aggregated, cost = await run_agent(
        label=f"{manifest['series']}/aggregation",
        system_prompt=AGGREGATION_SYSTEM_PROMPT.format(
            date=date_text, title=manifest["title"], max_turns=turns
        ),
        user_prompt=AGGREGATION_USER_PROMPT.format(
            num_agents=len(results),
            title=manifest["title"],
            series=manifest["series"],
            conference_data=conference_data,
            year_labels=labels,
            retrieval_results=rendered,
        ),
        model=aggregation_model,
        max_turns=turns,
        max_budget_usd=budget,
        wall_clock_seconds=agent_wall_clock_seconds("aggregation"),
    )
    total += cost
    if aggregated.get("status") == "timeout":
        return pipeline_result(
            status="timeout",
            reasoning="aggregation agent wall-clock timeout",
            aggregation_failed=True,
            total_cost_usd=total,
            error=aggregated.get("error", "aggregation timeout"),
        )
    if not has_structured_output(aggregated):
        # No unverified fallback to a retrieval result: a misconfigured
        # aggregation model must fail loudly instead of applying data that no
        # majority vote checked.
        return pipeline_result(
            status="error",
            reasoning="aggregation produced no structured output",
            total_cost_usd=total,
            error=aggregated.get("error", "aggregation produced no structured output"),
            aggregation_failed=True,
        )
    if aggregated.get("requires_update") is not True:
        return pipeline_result(
            status="no_changes",
            reasoning=aggregated.get("reasoning", ""),
            total_cost_usd=total,
        )
    return pipeline_result(
        status="proposed",
        reasoning=aggregated.get("reasoning", ""),
        total_cost_usd=total,
        change_set=aggregated,
    )


async def main_async() -> int:
    payload = decode_payload(os.environ["PWC_DEADLINE_MANIFEST"])
    num_agents = int(payload.get("num_retrieval_agents", 3))
    series_list = payload["series"]
    print(
        f"sweep {payload.get('sweep_id')}: {len(series_list)} conferences, "
        f"{num_agents} retrieval agents each",
        flush=True,
    )
    consecutive_aggregation_failures = 0
    for manifest in series_list:
        started = time.monotonic()
        try:
            result = await research_series(manifest, num_retrieval_agents=num_agents)
        except Exception as exc:  # One broken conference must not end the sweep.
            # Unknown stage: count it against aggregation so it neither
            # resets the failure streak nor makes the sweep look verified.
            result = pipeline_result(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                aggregation_failed=True,
            )
        result["series"] = manifest["series"]
        result["seconds"] = round(time.monotonic() - started)
        print(
            f"{manifest['series']}: {result['status']} "
            f"(${result['total_cost_usd']:.2f}, {result['seconds']}s)",
            flush=True,
        )
        print(encode_result_line(result), flush=True)
        if result.get("aggregation_failed"):
            consecutive_aggregation_failures += 1
        elif aggregation_succeeded(result):
            consecutive_aggregation_failures = 0
        if consecutive_aggregation_failures >= MAX_CONSECUTIVE_AGGREGATION_FAILURES:
            # Systemic (model/CLI/credential) failure: stop paying for retrieval.
            # No DONE marker, so the VPS records the sweep as failed.
            print("aborting sweep: aggregation keeps failing", flush=True)
            return 1
    print(f"{DONE_MARKER} {len(series_list)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
