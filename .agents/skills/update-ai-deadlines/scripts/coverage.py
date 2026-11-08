"""Read-only /ai-deadlines coverage: what each tracked series shows today.

Prints one row per series that has ever had a deadline: its latest edition,
its next upcoming deadline, and a state:

    upcoming  an upcoming deadline is listed
    tba       an announced edition (official dates) waits for its deadlines
    gap       nothing upcoming is listed; the next call may be out

Run from the repo root:

    uv run --env-file backend/keys.env python .agents/skills/update-ai-deadlines/scripts/coverage.py [--gaps] [--top-tier]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from backend.database.connection import db_manager
from backend.services.conference_deadline_service import load_deadline_series

TIER_A = "a"


def rows(today: date, now: datetime) -> list[dict]:
    with db_manager.session_local() as db:
        series = load_deadline_series(db)
    out = []
    for item in series:
        latest = max(item.editions, key=lambda e: e.year)
        next_deadline = item.next_deadline(now)
        tba = [
            e
            for e in item.editions
            if not e.deadlines and e.start_date and not e.is_past(today)
        ]
        state = "upcoming" if next_deadline else "tba" if tba else "gap"
        out.append(
            {
                "series": item.series,
                "tier": item.tier or "-",
                "latest": latest.slug,
                "next_deadline": next_deadline.date().isoformat()
                if next_deadline
                else "-",
                "tba": ",".join(e.slug for e in tba) or "-",
                "state": state,
            }
        )
    order = {"gap": 0, "tba": 1, "upcoming": 2}
    return sorted(out, key=lambda r: (order[r["state"]], r["tier"], r["series"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gaps", action="store_true", help="only gap/tba series")
    parser.add_argument("--top-tier", action="store_true", help="only tier 'a'")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    table = rows(now.date(), now)
    if args.gaps:
        table = [r for r in table if r["state"] != "upcoming"]
    if args.top_tier:
        table = [r for r in table if r["tier"] == TIER_A]
    cols = ("state", "tier", "series", "latest", "next_deadline", "tba")
    widths = {
        c: max(len(c), *(len(r[c]) for r in table)) if table else len(c) for c in cols
    }
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in table:
        print("  ".join(r[c].ljust(widths[c]) for c in cols))
    counts = {
        s: sum(r["state"] == s for r in table) for s in ("upcoming", "tba", "gap")
    }
    print(f"\n{len(table)} series: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
