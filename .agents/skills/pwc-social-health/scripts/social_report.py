#!/usr/bin/env python3
"""One JSON report on the Papers with Code social accounts (X @paperswithcodee + the LinkedIn page).

Read-only: it reads the X growth agent's files under /root/x-post-schedule and runs the agent's own
`performance` commands (which only read stats files). It never posts, edits the queue, or calls the
X API. Run as root on the production host:

    python3 .agents/skills/pwc-social-health/scripts/social_report.py [--dir /root/x-post-schedule]
"""

import argparse
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Posting window and cadence of post_x.py (WINDOW_UTC=(8, 2): 08:00 to 02:59 UTC, a post every 2 h).
WINDOW_START, WINDOW_END = 8, 3
MAX_GAP_HOURS = 3
MIRROR_GRACE_MINUTES = 60
STATS_MAX_AGE_HOURS = 2
TOKEN_WARN_DAYS = 14


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def hours_since(at: str, now: datetime) -> float:
    return round((now - datetime.fromisoformat(at)).total_seconds() / 3600, 1)


def in_window(moment: datetime) -> bool:
    return moment.hour >= WINDOW_START or moment.hour < WINDOW_END


def performance(directory: Path, script: str) -> dict:
    result = subprocess.run(
        ["python3", str(directory / script), "performance"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return {"error": (result.stderr or result.stdout).strip()[-500:]}
    return json.loads(result.stdout or "{}")


def last_line(path: Path) -> str:
    lines = (
        path.read_text(errors="replace").strip().splitlines() if path.exists() else []
    )
    return lines[-1] if lines else ""


def timer_active(name: str) -> str:
    return subprocess.run(
        ["systemctl", "is-active", name], capture_output=True, text=True
    ).stdout.strip()


def followers_delta(rows: list[dict], days: int) -> int | None:
    if not rows:
        return None
    latest = rows[-1]
    cutoff = datetime.fromisoformat(latest["at"]) - timedelta(days=days)
    if datetime.fromisoformat(rows[0]["at"]) > cutoff + timedelta(hours=6):
        return None  # history shorter than the window
    then = next((r for r in rows if datetime.fromisoformat(r["at"]) >= cutoff), None)
    if then is None or then["followers"] is None or latest["followers"] is None:
        return None
    return latest["followers"] - then["followers"]


def followers_per_day(rows: list[dict], days: int = 14) -> dict[str, int]:
    """Followers at the last snapshot of each UTC day, for the last `days` days."""
    by_day = {}
    for row in rows:
        by_day[row["at"][:10]] = row["followers"]
    return dict(list(by_day.items())[-days:])


def joined_posts(
    ledger: list[dict],
    x_stats: list[dict],
    li_ledger: list[dict],
    li_stats: list[dict],
    now: datetime,
    days: int = 14,
) -> list[dict]:
    """One row per X post of the last `days` days: X and LinkedIn impressions side by side.

    `mirror_delay_min` is LinkedIn time minus X time; a large delay means the post went out in a
    catch-up burst, whose LinkedIn reach is not comparable to a post mirrored on its own."""
    x_imp = x_stats[-1]["impressions"] if x_stats else {}
    li_posts = li_stats[-1]["posts"] if li_stats else {}
    li_at = {e["post_id"]: e["at"] for e in li_ledger}
    rows = {}
    for e in ledger:  # last row per post_id wins, so a "replaced" post counts once
        if (
            e.get("status") in {"posted", "replaced"}
            and e.get("url")
            and hours_since(e["at"], now) <= days * 24
        ):
            rows[e["post_id"]] = e
    out = []
    for post_id, e in rows.items():
        li = li_posts.get(post_id) or {}
        delay = (
            round(
                (
                    datetime.fromisoformat(li_at[post_id])
                    - datetime.fromisoformat(e["at"])
                ).total_seconds()
                / 60
            )
            if post_id in li_at
            else None
        )
        out.append(
            {
                "post_id": post_id,
                "kind": e.get("kind") or "manual",
                "x_at": e["at"][:16],
                "age_h": hours_since(e["at"], now),
                "x_impressions": x_imp.get(post_id),
                "li_impressions": li.get("impressions"),
                "li_engaged": (
                    li.get("clicks", 0)
                    + li.get("likes", 0)
                    + li.get("comments", 0)
                    + li.get("shares", 0)
                )
                if li
                else None,
                "mirror_delay_min": delay,
                "line1": (e.get("text") or "").split("\n")[0][:100],
            }
        )
    return out


def report(directory: Path) -> dict:
    now = datetime.now(UTC)
    findings = []

    def flag(level: str, area: str, message: str) -> None:
        findings.append({"level": level, "area": area, "message": message})

    # --- X ---
    ledger = jsonl(directory / "ledger.jsonl")
    published = [
        e for e in ledger if e.get("status") in {"posted", "replaced"} and e.get("url")
    ]
    posted_24h = [e for e in published if hours_since(e["at"], now) <= 24]
    last_post = published[-1] if published else None
    gap = hours_since(last_post["at"], now) if last_post else None
    if gap is None:
        flag("broken", "x", "no published post in ledger.jsonl")
    elif gap > MAX_GAP_HOURS and in_window(now):
        flag(
            "warn",
            "x",
            f"last X post {gap} h ago, inside the posting window (cadence is every 2 h)",
        )
    queue = (
        json.loads((directory / "queue.json").read_text() or "[]")
        if (directory / "queue.json").exists()
        else []
    )
    if len(queue) < 2:
        flag(
            "warn",
            "x",
            f"only {len(queue)} drafts queued (the planner tops up to 4): read planner_last_line and "
            "the planner logs for why (mix rules, flopping cap, or no candidate passing checks)",
        )
    x_stats = jsonl(directory / "stats.jsonl")
    if not x_stats or hours_since(x_stats[-1]["at"], now) > STATS_MAX_AGE_HOURS:
        flag(
            "warn",
            "x",
            "stats.jsonl is stale: impressions/followers are not being recorded",
        )
    rejected_24h = [
        e
        for e in ledger
        if str(e.get("status", "")).startswith("rejected")
        and hours_since(e["at"], now) <= 24
    ]
    errors = (
        [
            line
            for line in (directory / "logs" / "posts.log")
            .read_text(errors="replace")
            .splitlines()[-200:]
            if '"error"' in line or "Traceback" in line
        ]
        if (directory / "logs" / "posts.log").exists()
        else []
    )
    if errors:
        flag(
            "warn",
            "x",
            f"{len(errors)} error lines in the last 200 lines of logs/posts.log",
        )
    planner_logs = sorted(
        p for p in (directory / "logs").glob("2*.log") if p.stem[-1] == "Z"
    )
    planner_tail = last_line(planner_logs[-1]) if planner_logs else ""

    # --- LinkedIn ---
    li_ledger = jsonl(directory / "linkedin-ledger.jsonl")
    mirrored = {e["post_id"] for e in li_ledger}
    sync_since = "2026-11-12T20:00"
    unmirrored = [
        e["post_id"]
        for e in ledger
        if e.get("status") == "posted"
        and e["at"] >= sync_since
        and e["post_id"] not in mirrored
        and hours_since(e["at"], now) * 60 > MIRROR_GRACE_MINUTES
    ]
    if unmirrored:
        flag(
            "broken",
            "linkedin",
            f"{len(unmirrored)} X posts older than {MIRROR_GRACE_MINUTES} min are not on LinkedIn",
        )
    li_logs = sorted((directory / "logs").glob("*-linkedin.log"))
    li_last = last_line(li_logs[-1]) if li_logs else ""
    if li_last and "Failed: none" not in li_last:
        flag(
            "warn",
            "linkedin",
            f"latest mirror run did not end cleanly: {li_last[:200]}",
        )
    li_stats = jsonl(directory / "linkedin-stats.jsonl")
    if not li_stats or hours_since(li_stats[-1]["at"], now) > STATS_MAX_AGE_HOURS:
        flag(
            "warn",
            "linkedin",
            "linkedin-stats.jsonl is stale: run.sh records it hourly",
        )
    token = {}
    token_file = directory / "linkedin-token.json"
    if token_file.exists():
        raw = json.loads(
            token_file.read_text()
        )  # only expiry fields leave this function
        token = {
            "access_days_left": round((raw["expires_at"] - now.timestamp()) / 86400, 1),
            "refresh_days_left": round(
                (raw.get("refresh_expires_at", 0) - now.timestamp()) / 86400, 1
            ),
        }
        if token["refresh_days_left"] < TOKEN_WARN_DAYS:
            flag(
                "warn",
                "linkedin",
                "refresh token expires soon: a page admin must redo auth-url/exchange",
            )
        elif token["access_days_left"] < 0:
            flag(
                "broken",
                "linkedin",
                "access token expired and was not refreshed (post_linkedin.py refresh)",
            )
    else:
        flag("broken", "linkedin", "linkedin-token.json is missing")

    timers = {
        name: timer_active(name)
        for name in ("x-post-schedule.timer", "x-post-watch.timer")
    }
    for name, state in timers.items():
        if state != "active":
            flag("broken", "x", f"{name} is {state}")
    sync_tail = last_line(directory / "logs" / "sync.log")
    if "Traceback" in sync_tail or "Error" in sync_tail:
        flag("warn", "dashboard", f"last dashboard sync failed: {sync_tail[:200]}")

    return {
        "at": now.isoformat(timespec="seconds"),
        "findings": findings,
        "x": {
            "followers": x_stats[-1]["followers"] if x_stats else None,
            "followers_delta_7d": followers_delta(x_stats, 7),
            "followers_delta_14d": followers_delta(x_stats, 14),
            "followers_per_day": followers_per_day(x_stats),
            "posts_24h": len(posted_24h),
            "hours_since_last_post": gap,
            "last_post": {k: last_post.get(k) for k in ("at", "post_id", "kind", "url")}
            if last_post
            else None,
            "rejected_24h": len(rejected_24h),
            "queue": [
                {k: q.get(k) for k in ("post_id", "kind")}
                | {"line1": (q.get("text") or "").split("\n")[0][:100]}
                for q in queue
            ],
            "planner_last_line": planner_tail[:300],
            "performance": performance(directory, "post_x.py"),
        },
        "linkedin": {
            "followers": li_stats[-1]["followers"] if li_stats else None,
            "followers_delta_7d": followers_delta(li_stats, 7),
            "followers_per_day": followers_per_day(li_stats),
            "mirrored_posts": len(li_ledger),
            "unmirrored": unmirrored,
            "last_mirror_line": li_last[:300],
            "token": token,
            "performance": performance(directory, "post_linkedin.py"),
        },
        "posts": joined_posts(ledger, x_stats, li_ledger, li_stats, now),
        "timers": timers,
        "dashboard_last_sync": sync_tail[:300],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", default="/root/x-post-schedule", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.dir), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
