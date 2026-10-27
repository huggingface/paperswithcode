#!/usr/bin/env python3
"""Render a bounded method taxonomy snapshot as prompt-ready Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import Any

FEATURED_METHOD_SLUGS = frozenset(
    {
        "decision-model",
        "on-policy-distillation",
        "world-action-models",
    }
)


def _display_name(method: dict[str, Any]) -> str:
    name = str(method.get("name") or "").strip()
    full_name = str(method.get("full_name") or "").strip()
    if full_name and full_name.casefold() != name.casefold():
        if full_name.casefold().startswith(name.casefold()):
            return full_name
        return f"{name} — {full_name}"
    return name


def _rank(method: dict[str, Any]) -> tuple[int, str]:
    return (
        -int(method.get("paper_count") or 0),
        str(method.get("name") or "").casefold(),
    )


def _select_methods(
    methods: list[dict[str, Any]],
    *,
    maximum: int,
    featured_slugs: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    ranked = sorted(methods, key=_rank)
    selected = ranked[:maximum]
    selected_slugs = {str(method.get("slug") or "").strip() for method in selected}
    featured = [
        method
        for method in ranked
        if str(method.get("slug") or "").strip() in featured_slugs
        and str(method.get("slug") or "").strip() not in selected_slugs
    ]
    for method in featured:
        replace_at = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if str(selected[index].get("slug") or "").strip() not in featured_slugs
            ),
            None,
        )
        if replace_at is not None:
            selected[replace_at] = method
    return sorted(selected, key=_rank)


def render(
    payload: dict[str, Any],
    *,
    maximum_methods_per_area: int = 12,
    featured_slugs: Iterable[str] = FEATURED_METHOD_SLUGS,
) -> str:
    areas = payload.get("results")
    if not isinstance(areas, list):
        raise TypeError("method taxonomy response must contain a results list")

    featured = {str(slug).strip() for slug in featured_slugs if str(slug).strip()}
    lines = [
        "## Representative methods in the catalog",
        "",
        (
            "Methods are general techniques, architectures, and training "
            "procedures reused across many papers and tracked by Papers With "
            "Code; a specific model or system is a paper, not a method. The "
            "list below is a "
            "bounded snapshot, grouped by research area and primarily ordered by "
            "paper coverage; a small number of featured newer methods are retained "
            "for discoverability. It is not exhaustive. Treat names, full names, "
            "acronyms, and slugs as taxonomy clues, and use `pwc method` to verify "
            "the current catalog before saying that a named method is absent."
        ),
    ]
    for area in sorted(areas, key=lambda item: str(item.get("name") or "").casefold()):
        name = str(area.get("name") or "").strip()
        methods = area.get("methods")
        if not name or not isinstance(methods, list):
            continue
        catalog_methods = [
            method
            for method in methods
            if isinstance(method, dict)
            and str(method.get("name") or "").strip()
            and str(method.get("slug") or "").strip()
        ]
        if not catalog_methods:
            continue
        selected = _select_methods(
            catalog_methods,
            maximum=maximum_methods_per_area,
            featured_slugs=featured,
        )
        lines.extend(("", f"### {name}", ""))
        for method in selected:
            lines.append(f"- `{str(method['slug']).strip()}` — {_display_name(method)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maximum-methods-per-area", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.maximum_methods_per_area <= 25:
        parser.error("--maximum-methods-per-area must be 1-25")
    payload = json.load(sys.stdin)
    sys.stdout.write(
        render(payload, maximum_methods_per_area=args.maximum_methods_per_area)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
