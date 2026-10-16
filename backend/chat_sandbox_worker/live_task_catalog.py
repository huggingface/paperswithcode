"""Load the current task taxonomy through the sandbox's trusted catalog gateway."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.chat_sandbox_worker.render_task_catalog import render_framework_index

MAXIMUM_PAGES = 10
MAXIMUM_RESPONSE_BYTES = 1_000_000


def _get(url: str, *, timeout: float) -> Any:
    with urlopen(url, timeout=timeout) as response:
        body = response.read(MAXIMUM_RESPONSE_BYTES + 1)
    if len(body) > MAXIMUM_RESPONSE_BYTES:
        raise ValueError("task catalog response is too large")
    return json.loads(body)


def _page(api_url: str, page: int, *, timeout: float) -> dict[str, Any]:
    query = urlencode({"page": page, "page_size": 100, "ordering": "name"})
    payload = _get(f"{api_url.rstrip('/')}/tasks/?{query}", timeout=timeout)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise TypeError("task catalog response is invalid")
    return payload


def render_live_task_catalog(
    tasks: list[dict[str, Any]],
    framework_domains: list[dict[str, Any]] | None = None,
) -> str:
    """Render a compact, complete lookup index from validated public task rows."""
    rows: set[tuple[str, str]] = set()
    for task in tasks:
        name = str(task.get("name") or "").strip()
        slug = str(task.get("slug") or "").strip()
        if name and slug and len(name) <= 200 and len(slug) <= 200:
            rows.add((name, slug))
    ordered = sorted(rows, key=lambda row: (row[0].casefold(), row[1].casefold()))
    if not ordered:
        raise ValueError("live task catalog is empty")
    lines = [
        "## Complete live task lookup index",
        "",
        (
            "This index was refreshed from the trusted PwC catalog for the current "
            "turn and supersedes the baked fallback snapshot. Treat names and slugs "
            "as taxonomy clues, then use `pwc task --name TASK` and "
            "`pwc benchmark list --task TASK` to verify task and leaderboard details."
        ),
        "",
    ]
    lines.extend(f"- `{slug}` — {name}" for name, slug in ordered)
    if framework_domains is not None:
        lines.extend(("", *render_framework_index(framework_domains)))
    return "\n".join(lines) + "\n"


def fetch_live_task_catalog(
    api_url: str | None = None,
    *,
    timeout: float = 3.0,
) -> str:
    """Fetch every task page and return prompt-ready Markdown."""
    base_url = api_url or os.environ.get("PWC_API_URL", "http://127.0.0.1:8765/api/v1")
    deadline = time.monotonic() + timeout
    tasks: list[dict[str, Any]] = []
    page = 1
    while page <= MAXIMUM_PAGES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("task catalog refresh timed out")
        payload = _page(base_url, page, timeout=remaining)
        tasks.extend(task for task in payload["results"] if isinstance(task, dict))
        next_page = payload.get("next_page")
        if next_page is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("task catalog refresh timed out")
            frameworks = _get(f"{base_url.rstrip('/')}/frameworks/", timeout=remaining)
            if not isinstance(frameworks, dict) or not isinstance(
                frameworks.get("domains"), list
            ):
                raise TypeError("framework catalog response is invalid")
            return render_live_task_catalog(tasks, frameworks["domains"])
        if not isinstance(next_page, int) or next_page != page + 1:
            raise ValueError("task catalog pagination is invalid")
        page = next_page
    raise ValueError("task catalog exceeded the page limit")
