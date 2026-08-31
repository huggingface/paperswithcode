"""Deterministic compact renderer for agent consumption."""

from __future__ import annotations

import json


def render(envelope: dict) -> str:
    lines = [
        f"operation: {envelope['operation']}",
        f"cache: {envelope.get('cache', 'miss')}",
    ]
    if envelope.get("cache_age_seconds") is not None:
        lines.append(f"cache_age_seconds: {envelope['cache_age_seconds']}")
    source = envelope.get("source") or {}
    for key in ("repo_type", "repo_id", "resolved_sha", "url", "immutable_card_url"):
        if source.get(key) is not None:
            lines.append(f"source.{key}: {source[key]}")
    result_set = envelope.get("result_set") or {}
    if result_set:
        lines.append(
            (
                "results: returned={returned} limit={limit} "
                "more_available={more_available}"
            ).format(
                returned=result_set.get("returned", 0),
                limit=result_set.get("limit", 0),
                more_available=str(bool(result_set.get("more_available"))).lower(),
            )
        )
    data = envelope.get("data")
    lines.append("data:")
    lines.append(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    truncation = envelope.get("truncation") or {"truncated": False}
    lines.append(
        "truncation: " + json.dumps(truncation, ensure_ascii=False, sort_keys=True)
    )
    return "\n".join(lines) + "\n"
