"""Render bounded public task taxonomy JSON as prompt-ready Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def render(payload: dict[str, Any], *, maximum_tasks_per_area: int = 12) -> str:
    areas = payload.get("results")
    if not isinstance(areas, list):
        raise TypeError("taxonomy response must contain a results list")

    lines = [
        "## Available research areas and representative tasks",
        "",
        (
            "The public catalog currently uses the areas below. Up to "
            f"{maximum_tasks_per_area} top-level tasks are shown per area, "
            "ordered by paper coverage. Task slugs are included for precise CLI "
            "queries; use `pwc --help` to inspect the live command surface."
        ),
        "",
        "Note that currently, the tasks are quite broadly defined. To give some examples:",
        "-  video understanding includes subtasks like video question answering, video summarization and video captioning",
        "- image segmentation includes subtasks like semantic segmentation, instance segmentation and panoptic segmentation",
        "- depth estimation includes subtasks like metric depth estimation and relative depth estimation",
        "- etc.",
        "",
        "The goal is to split up those tasks in the future.",
    ]
    for area in sorted(areas, key=lambda item: str(item.get("name") or "").casefold()):
        name = str(area.get("name") or "").strip()
        tasks = area.get("tasks")
        if not name or not isinstance(tasks, list):
            continue
        catalog_tasks = [
            task
            for task in tasks
            if isinstance(task, dict)
            and str(task.get("name") or "").strip()
            and str(task.get("slug") or "").strip()
        ]
        catalog_tasks.sort(
            key=lambda task: (
                -int(task.get("paper_count") or 0),
                str(task.get("name") or "").casefold(),
            )
        )
        lines.extend(("", f"### {name}", ""))
        for task in catalog_tasks[:maximum_tasks_per_area]:
            slug = str(task["slug"]).strip()
            task_name = str(task["name"]).strip()
            lines.append(f"- `{slug}` — {task_name}")

    all_tasks = payload.get("all_tasks")
    if all_tasks is not None:
        if not isinstance(all_tasks, list):
            raise TypeError("complete task taxonomy must be a list")
        lookup_tasks = [
            task
            for task in all_tasks
            if isinstance(task, dict)
            and str(task.get("name") or "").strip()
            and str(task.get("slug") or "").strip()
        ]
        lookup_tasks.sort(
            key=lambda task: (
                str(task.get("name") or "").casefold(),
                str(task.get("slug") or "").casefold(),
            )
        )
        lines.extend(
            (
                "",
                "## Complete task lookup index",
                "",
                (
                    "This compact index contains every current task and subtask. "
                    "Treat names and slugs as taxonomy clues, then use `pwc task` "
                    "and `pwc benchmark list --task TASK` to verify the live catalog."
                ),
                "",
            )
        )
        for task in lookup_tasks:
            lines.append(
                f"- `{str(task['slug']).strip()}` — {str(task['name']).strip()}"
            )
    if "framework_domains" in payload:
        lines.extend(("", *render_framework_index(payload["framework_domains"])))
    return "\n".join(lines) + "\n"


def render_framework_index(domains: list[dict[str, Any]]) -> list[str]:
    """Render every catalog framework as one compact line per category."""
    if not isinstance(domains, list):
        raise TypeError("framework catalog must contain a domains list")
    entries = []
    for domain in domains:
        for category in domain.get("categories") or []:
            frameworks = [
                f"`{str(framework['slug']).strip()}` {str(framework['name']).strip()}"
                for framework in category.get("frameworks") or []
                if str(framework.get("slug") or "").strip()
                and str(framework.get("name") or "").strip()
            ]
            if frameworks:
                entries.append(
                    f"- {str(domain.get('name') or '').strip()} / "
                    f"{str(category.get('name') or '').strip()}: {', '.join(frameworks)}"
                )
    if not entries:
        raise ValueError("framework catalog is empty")
    return [
        "## Complete framework lookup index",
        "",
        (
            "Frameworks are software libraries, inference engines, serving systems, "
            "and toolkits; this index lists every catalog framework by domain and "
            "category. Use the slug with `pwc framework --name FRAMEWORK`."
        ),
        "",
        *entries,
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maximum-tasks-per-area", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.maximum_tasks_per_area <= 25:
        parser.error("--maximum-tasks-per-area must be 1-25")
    payload = json.load(sys.stdin)
    sys.stdout.write(
        render(payload, maximum_tasks_per_area=args.maximum_tasks_per_area)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
