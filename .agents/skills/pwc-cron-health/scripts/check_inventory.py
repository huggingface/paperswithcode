#!/usr/bin/env python3
"""Compare deployed CRON registry, dashboard, launcher, and probe coverage."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dashboard-json", type=Path)
    parser.add_argument("--launcher-json", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def literal_keyword(call: ast.Call, name: str, default: Any = None) -> Any:
    for keyword in call.keywords:
        if keyword.arg == name:
            try:
                return ast.literal_eval(keyword.value)
            except (ValueError, TypeError):
                return default
    return default


def registry_jobs(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "backend/services/cron_registry.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    jobs: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Name) or function.id != "CronJobDefinition":
            continue
        job_id = literal_keyword(node, "id")
        if isinstance(job_id, str):
            category = literal_keyword(node, "category")
            scheduler = literal_keyword(node, "scheduler", "github_actions")
            # The deployed registry currently normalizes the manual category in
            # a final dataclass replacement rather than on the constructor.
            if category == "manual":
                scheduler = "manual"
            jobs.append(
                {
                    "id": job_id,
                    "scheduler": scheduler,
                    "workflow_file": literal_keyword(node, "workflow_file"),
                    "systemd_timer": literal_keyword(node, "systemd_timer"),
                }
            )
    return jobs


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text())


def probe_ids() -> list[str]:
    reference = Path(__file__).resolve().parent.parent / "references/job-probes.md"
    return re.findall(r"^## `([^`]+)`$", reference.read_text(), flags=re.MULTILINE)


def duplicate_values(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def probe_reference_gaps(
    registered_ids: list[str], probes: list[str]
) -> dict[str, list[str]]:
    registered = set(registered_ids)
    referenced = set(probes)
    return {
        "probe_missing": sorted(registered - referenced),
        "probe_extra": sorted(referenced - registered),
        "probe_duplicates": duplicate_values(probes),
    }


def main() -> int:
    args = parse_args()
    registered = registry_jobs(args.repo_root.resolve())
    registered_ids = [job["id"] for job in registered]
    registered_set = set(registered_ids)

    dashboard = load_json(args.dashboard_json)
    dashboard_ids = [str(job["job_name"]) for job in dashboard.get("jobs", [])]

    launcher = load_json(args.launcher_json)
    launcher_jobs = launcher.get("jobs", {})
    launcher_commands = set(launcher_jobs)
    launcher_health_ids = {
        str(details.get("health_job"))
        for details in launcher_jobs.values()
        if details.get("health_job")
    }
    launcher_mapped = registered_set & (launcher_commands | launcher_health_ids)

    probes = probe_ids()
    probe_gaps = probe_reference_gaps(registered_ids, probes)
    result = {
        "repo_root": str(args.repo_root.resolve()),
        "registered_count": len(registered_ids),
        "scheduled_count": sum(job["scheduler"] != "manual" for job in registered),
        "manual_count": sum(job["scheduler"] == "manual" for job in registered),
        "registered_duplicates": duplicate_values(registered_ids),
        "dashboard_missing": sorted(registered_set - set(dashboard_ids))
        if dashboard
        else [],
        "dashboard_extra": sorted(set(dashboard_ids) - registered_set)
        if dashboard
        else [],
        "dashboard_duplicates": duplicate_values(dashboard_ids),
        "launcher_unmapped": sorted(registered_set - launcher_mapped)
        if launcher
        else [],
        "launcher_extra_commands": sorted(launcher_commands - registered_set)
        if launcher
        else [],
        **probe_gaps,
        "registered_jobs": registered,
    }
    gap_keys = (
        "registered_duplicates",
        "dashboard_missing",
        "dashboard_extra",
        "dashboard_duplicates",
        "launcher_unmapped",
        "probe_missing",
        "probe_extra",
        "probe_duplicates",
    )
    healthy = not any(result[key] for key in gap_keys)
    result["inventory_consistent"] = healthy

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"registered={result['registered_count']} "
            f"scheduled={result['scheduled_count']} manual={result['manual_count']}"
        )
        for key in gap_keys:
            print(f"{key}: {result[key] or 'none'}")
        print(f"inventory_consistent: {'yes' if healthy else 'no'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
