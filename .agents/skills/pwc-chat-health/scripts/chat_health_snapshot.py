#!/usr/bin/env python3
"""Emit a read-only, content-free aggregate snapshot of production chat health."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

NOT_FOUND = re.compile(
    r"not_found: (Method|Task|Benchmark|Framework|Conference|Dataset|Paper title|Paper URL)"
    r" not (?:found|supported): (.+?)(?:;|\. Correct|$)"
)

# User-stop codes are not failures; superseded rows were retried by the user.
USER_STOP_CODES = ("cancelled", "cancel_control_missing")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--top", type=int, default=40)
    return parser.parse_args()


def classify_tool_error(message: str) -> tuple[str, str | None]:
    """Return (error class, catalog entity name) for one tool error text."""
    if message.startswith("Execution limit reached"):
        return "execution_limit", None
    match = NOT_FOUND.search(message)
    if match:
        kind = match.group(1).lower().replace(" ", "_")
        return f"not_found:{kind}", match.group(2).strip()
    # Author names are people; count them without recording the name.
    if re.search(r"Author '.+' not found", message):
        return "not_found:author", None
    if "not_found" in message:
        return "not_found:other", None
    if "no_markdown" in message or "No saved page" in message:
        return "no_markdown", None
    if "no next page" in message:
        return "cursor_misuse", None
    if re.search(r"\b(5\d\d)\b|upstream_error|unavailable", message):
        return "upstream", None
    return "other", None


def rows(connection, sql: str, since: datetime) -> list[dict[str, Any]]:
    return [
        dict(row._mapping) for row in connection.execute(text(sql), {"since": since})
    ]


def percentile_sql(column: str, alias: str) -> str:
    return (
        f"round(percentile_cont(0.5) within group (order by {column})) as {alias}_p50, "
        f"round(percentile_cont(0.9) within group (order by {column})) as {alias}_p90"
    )


def snapshot(connection, since: datetime, top: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["user_turns"] = rows(
        connection,
        """
        select status, error_code, count(*) as turns
        from chat_messages
        where role = 'user' and created_at >= :since
        group by 1, 2 order by 3 desc
        """,
        since,
    )
    result["volume"] = rows(
        connection,
        """
        select count(*) as user_turns,
               count(distinct m.session_id) as sessions,
               count(distinct s.hf_user_id) as users
        from chat_messages m join chat_sessions s on s.id = m.session_id
        where m.role = 'user' and m.created_at >= :since
        """,
        since,
    )[0]
    stops = ", ".join(f"'{code}'" for code in USER_STOP_CODES)
    result["failures_by_release"] = rows(
        connection,
        f"""
        select coalesce(app_release_id, '?') as app_release_id, error_code,
               count(*) as turns, min(created_at) as first_at, max(created_at) as last_at
        from chat_messages
        where role = 'user' and created_at >= :since
          and error_code is not null and error_code not in ({stops})
        group by 1, 2 order by 3 desc
        """,
        since,
    )
    result["latency"] = rows(
        connection,
        f"""
        select l.traffic_class, coalesce(u.reasoning_effort, '?') as effort,
               l.terminal_status, count(*) as turns,
               {percentile_sql("l.first_semantic_event_ms", "ttfe")},
               {percentile_sql("l.total_ms", "total")}
        from chat_turn_latency l
        left join chat_messages u on u.turn_id = l.turn_id and u.role = 'user'
        where l.admitted_at >= :since
        group by 1, 2, 3 order by 4 desc
        """,
        since,
    )
    result["provider_calls"] = rows(
        connection,
        f"""
        select provider_model, reasoning_effort, coalesce(outcome, state) as outcome,
               count(*) as calls,
               count(*) filter (where reasoning_tokens >= 8000) as reasoning_capped,
               {percentile_sql("provider_ttft_ms", "ttft")},
               {percentile_sql("provider_latency_ms", "latency")}
        from chat_openai_provider_calls
        where reserved_at >= :since and environment = 'production'
        group by 1, 2, 3 order by 4 desc
        """,
        since,
    )
    result["tool_calls"] = rows(
        connection,
        """
        select b->>'name' as tool, b->>'status' as status, count(*) as calls
        from chat_messages m, jsonb_array_elements(m.display_blocks) b
        where m.role = 'assistant' and m.created_at >= :since and b->>'kind' = 'tool'
        group by 1, 2 order by 3 desc
        """,
        since,
    )
    errors = rows(
        connection,
        """
        select b->>'name' as tool, coalesce(b->'content'->0->>'text', '') as message
        from chat_messages m, jsonb_array_elements(m.display_blocks) b
        where m.role = 'assistant' and m.created_at >= :since
          and b->>'kind' = 'tool' and b->>'status' = 'error'
        """,
        since,
    )
    classes: Counter[tuple[str, str]] = Counter()
    misses: Counter[tuple[str, str]] = Counter()
    for error in errors:
        error_class, entity = classify_tool_error(error["message"])
        classes[(error["tool"], error_class)] += 1
        if entity:
            misses[(error_class.removeprefix("not_found:"), entity.lower())] += 1
    result["tool_error_classes"] = [
        {"tool": tool, "class": error_class, "calls": count}
        for (tool, error_class), count in classes.most_common()
    ]
    result["catalog_misses"] = [
        {"kind": kind, "name": name, "calls": count}
        for (kind, name), count in misses.most_common(top)
    ]
    result["execution_limit_turns"] = rows(
        connection,
        """
        select count(distinct m.turn_id) as turns
        from chat_messages m, jsonb_array_elements(m.display_blocks) b
        where m.role = 'assistant' and m.created_at >= :since and b->>'kind' = 'tool'
          and b->'content'->0->>'text' like 'Execution limit reached%'
        """,
        since,
    )[0]["turns"]
    result["no_tool_answers"] = rows(
        connection,
        """
        select jsonb_typeof(u.primary_paper_context) = 'object' as paper_context,
               count(*) as answers,
               count(*) filter (where not exists (
                   select 1 from jsonb_array_elements(a.display_blocks) b
                   where b->>'kind' = 'tool')) as without_tools
        from chat_messages a
        join chat_messages u on u.turn_id = a.turn_id and u.role = 'user'
        where a.role = 'assistant' and a.status = 'complete' and a.created_at >= :since
        group by 1
        """,
        since,
    )
    result["scope_refusals"] = rows(
        connection,
        """
        select coalesce(finish_reason, '?') as finish_reason, count(*) as answers
        from chat_messages
        where role = 'assistant' and created_at >= :since
          and (finish_reason = 'scope_blocked' or content like 'I can only help with AI%')
        group by 1
        """,
        since,
    )
    result["largest_failed_sessions"] = rows(
        connection,
        """
        select s.id::text as session_id, s.message_count, s.transcript_bytes,
               count(*) as failed_turns, array_agg(distinct m.error_code) as error_codes
        from chat_messages m join chat_sessions s on s.id = m.session_id
        where m.role = 'user' and m.created_at >= :since
          and m.error_code in ('context_too_large', 'transcript_mirror_error',
                               'openai_user_concurrency_limited')
        group by 1, 2, 3 order by 4 desc, 3 desc limit 10
        """,
        since,
    )
    result["feedback"] = rows(
        connection,
        """
        select value as thumbs_up, count(*) as votes,
               count(comment) as with_comment, count(exported_at) as exported
        from chat_feedback where created_at >= :since group by 1
        """,
        since,
    )
    result["web_search_budget"] = rows(
        connection,
        """
        select billing_cycle, call_count, success_count, failure_count,
               warning_calls, hard_limit_calls, circuit_state, trip_reason,
               cooldown_until, last_provider_error_class, updated_at
        from chat_web_search_budget_states
        where environment = 'production'
        order by billing_cycle desc limit 1
        """,
        since,
    )
    return result


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.repo_root.resolve()))
    from backend.database.connection import get_engine

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    with get_engine().connect() as connection:
        connection.execute(text("set transaction read only"))
        result = snapshot(connection, since, args.top)
        connection.rollback()
    payload = {"generated_at": now, "since": since, "hours": args.hours, **result}
    print(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    main()
