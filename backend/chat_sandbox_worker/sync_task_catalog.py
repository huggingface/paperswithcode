"""Synchronize the checked-in chat task catalog from the public taxonomy API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.chat_sandbox_worker.render_task_catalog import render

DEFAULT_API_URL = "https://paperswithcode.co/api/v1"
DEFAULT_OUTPUT = Path(__file__).with_name("TASK_CATALOG.md")
MIN_EXPECTED_TASKS = 50
MAX_EXPECTED_TASKS = 1_000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LABEL_LENGTH = 255
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"User-Agent": "paperswithcode-task-catalog-sync/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError(f"taxonomy response is too large: {url}")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise TypeError(f"taxonomy response must be an object: {url}")
    return payload


def _fetch_all_tasks(api_url: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    page = 1
    expected_count: int | None = None
    while True:
        query = urlencode({"page": page, "page_size": 100, "ordering": "name"})
        payload = _fetch_json(f"{api_url.rstrip('/')}/tasks/?{query}")
        results = payload.get("results")
        count = payload.get("count")
        if not isinstance(results, list) or not isinstance(count, int):
            raise TypeError("task taxonomy page is missing count or results")
        if expected_count is None:
            expected_count = count
        elif count != expected_count:
            raise ValueError("task taxonomy count changed during pagination")
        tasks.extend(task for task in results if isinstance(task, dict))
        next_page = payload.get("next_page")
        if next_page is None:
            break
        if not isinstance(next_page, int) or next_page <= page or next_page > 100:
            raise ValueError("task taxonomy returned invalid pagination")
        page = next_page

    if expected_count != len(tasks):
        raise ValueError(
            f"task taxonomy returned {len(tasks)} rows but declared {expected_count}"
        )
    if not MIN_EXPECTED_TASKS <= len(tasks) <= MAX_EXPECTED_TASKS:
        raise ValueError(
            f"task taxonomy returned {len(tasks)} rows; expected "
            f"{MIN_EXPECTED_TASKS}-{MAX_EXPECTED_TASKS}"
        )
    slugs = [str(task.get("slug") or "").strip() for task in tasks]
    names = [str(task.get("name") or "").strip() for task in tasks]
    if any(not slug for slug in slugs) or any(not name for name in names):
        raise ValueError("task taxonomy contains a missing name or slug")
    if any(
        len(slug) > MAX_LABEL_LENGTH or not SLUG_PATTERN.fullmatch(slug)
        for slug in slugs
    ):
        raise ValueError("task taxonomy contains an invalid slug")
    if any(
        len(name) > MAX_LABEL_LENGTH or "\n" in name or "\r" in name for name in names
    ):
        raise ValueError("task taxonomy contains an invalid name")
    if len(slugs) != len(set(slugs)):
        raise ValueError("task taxonomy contains duplicate slugs")
    return tasks


def build_catalog(api_url: str = DEFAULT_API_URL) -> str:
    """Fetch and render one complete, validated task catalog snapshot."""
    base = api_url.rstrip("/")
    areas = _fetch_json(f"{base}/areas/with-tasks/")
    area_results = areas.get("results")
    if not isinstance(area_results, list) or not area_results:
        raise ValueError("area taxonomy response must contain results")
    tasks = _fetch_all_tasks(base)
    canonical_tasks = {
        str(task["slug"]).strip(): str(task["name"]).strip() for task in tasks
    }
    representative_tasks = {
        str(task.get("slug") or "").strip(): str(task.get("name") or "").strip()
        for area in area_results
        if isinstance(area, dict) and isinstance(area.get("tasks"), list)
        for task in area["tasks"]
        if isinstance(task, dict)
    }
    if not representative_tasks or any(
        canonical_tasks.get(slug) != name for slug, name in representative_tasks.items()
    ):
        raise ValueError("area taxonomy and complete task taxonomy do not agree")
    area_names = [
        str(area.get("name") or "").strip()
        for area in area_results
        if isinstance(area, dict)
    ]
    if any(
        not name or len(name) > MAX_LABEL_LENGTH or "\n" in name or "\r" in name
        for name in area_names
    ):
        raise ValueError("area taxonomy contains an invalid name")
    frameworks = _fetch_json(f"{base}/frameworks/")
    return render(
        {
            **areas,
            "all_tasks": tasks,
            "framework_domains": frameworks.get("domains"),
        }
    )


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 instead of writing when the checked-in catalog is stale.",
    )
    args = parser.parse_args()
    try:
        rendered = build_catalog(args.api_url)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"task catalog sync failed: {exc}", file=sys.stderr)
        return 2
    current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
    if current == rendered:
        print(f"task catalog is current: {args.output}")
        return 0
    if args.check:
        print(f"task catalog is stale: {args.output}", file=sys.stderr)
        return 1
    _write_atomic(args.output, rendered)
    print(f"updated task catalog: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
