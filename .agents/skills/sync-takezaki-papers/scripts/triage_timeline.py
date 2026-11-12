"""Triage an X account's recent paper posts into Papers with Code actions.

Reads the newest posts of one account (default @shumpeiMaxwell, Shumpei
Takezaki) with the OAuth2 user token, groups them into the account's own
threads, finds the arXiv papers each thread links to, and checks every paper
against the public Papers with Code API: indexed, enrichment gaps, evaluation
count, and whether the thread is linked. Writes a JSON report plus a
link_threads.py input for the threads not yet linked. It never writes to
Papers with Code.

Usage (from the repository root):
  uv run --env-file backend/keys.env python \
      .agents/skills/sync-takezaki-papers/scripts/triage_timeline.py \
      --max 200 --out <scratchpad>/takezaki.json

The fetched posts are saved to <out>.raw.json before anything else, so a rerun
(for example after indexing) can reuse them with --from-raw instead of paying
for them again.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "process-x-bookmarks" / "scripts")
)

from triage_bookmarks import (  # noqa: E402
    PWC_API,
    TWEET_FIELDS,
    CreditsDepleted,
    get,
    links,
    paper_status,
    x_get,
)

from backend.services.x_thread_discovery_service import (  # noqa: E402
    post_text_and_urls,
)


def fetch_timeline(handle, limit):
    user = x_get(f"/users/by/username/{handle}")["data"]
    posts, token = [], None
    while len(posts) < limit:
        page = f"&pagination_token={token}" if token else ""
        try:
            data = x_get(
                f"/users/{user['id']}/tweets?max_results=100&exclude=retweets"
                f"&{TWEET_FIELDS}{page}"
            )
        except CreditsDepleted:
            if not posts:
                raise
            print(f"X credits depleted: continuing with {len(posts)} posts")
            break
        posts += data.get("data", [])
        token = data.get("meta", {}).get("next_token")
        if not token:
            break
    return user, posts[:limit]


def own_threads(posts):
    """Group posts by conversation, keeping only threads the account started."""
    threads = defaultdict(list)
    for post in posts:
        threads[post.get("conversation_id", post["id"])].append(post)
    return {
        root: sorted(thread, key=lambda p: p["created_at"])
        for root, thread in threads.items()
        if any(p["id"] == root for p in thread)
    }


def evaluation_count(paper_id):
    return get(f"{PWC_API}/evaluations/?paper_id={paper_id}&limit=1", {})["count"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handle", default="shumpeiMaxwell")
    parser.add_argument("--max", type=int, default=200, help="newest N posts")
    parser.add_argument("--out", required=True)
    parser.add_argument("--from-raw", help="reuse posts saved by an earlier run")
    args = parser.parse_args()

    if args.from_raw:
        with open(args.from_raw) as raw:
            user, posts = json.load(raw)
    else:
        try:
            user, posts = fetch_timeline(args.handle, args.max)
        except CreditsDepleted:
            sys.exit(
                "X API credits are depleted: top them up in the X developer console."
            )
        with open(f"{args.out}.raw.json", "w") as raw:
            json.dump([user, posts], raw)

    handle = user["username"]
    thread_users = {handle: user}
    report, unlinked = [], []
    for root, thread in own_threads(posts).items():
        arxiv_ids, other = links(thread)
        url = f"https://x.com/{handle}/status/{root}"
        papers = []
        for arxiv_id in arxiv_ids:
            status = paper_status(arxiv_id, thread_users)
            if status["indexed"]:
                status["evaluations"] = evaluation_count(status["paper_id"])
                status["thread_linked"] = any(
                    t.rstrip("/").split("/")[-1] == root
                    for t in status["linked_threads"]
                )
                if not status["thread_linked"]:
                    unlinked.append({"paper": arxiv_id, "urls": [url]})
            papers.append(status)
        report.append(
            {
                "thread": url,
                "posted_at": thread[0]["created_at"],
                "text": post_text_and_urls(thread[0])[0][:400],
                "arxiv_ids": arxiv_ids,
                "other_urls": other,
                "papers": papers,
            }
        )

    with open(args.out, "w") as out:
        json.dump({"account": handle, "threads": report}, out, indent=2)
    links_path = f"{args.out}.links.json"
    with open(links_path, "w") as out:
        json.dump(unlinked, out, indent=2)

    paper_threads = [r for r in report if r["arxiv_ids"]]
    print(
        f"@{handle}: {len(posts)} posts, {len(report)} own threads, "
        f"{len(paper_threads)} with arXiv links"
    )
    for row in report:
        for paper in row["papers"]:
            if not paper["indexed"]:
                print(f"MISSING  {paper['arxiv_id']:11} {row['thread']}")
                continue
            state = "linked" if paper["thread_linked"] else "UNLINKED"
            gaps = ",".join(paper["gaps"]) or "-"
            print(
                f"{state:8} {paper['arxiv_id']:11} id={paper['paper_id']:<7} "
                f"evals={paper['evaluations']:<3} gaps={gaps:28} {paper['title'][:50]}"
            )
    for row in report:
        if not row["arxiv_ids"] and row["other_urls"]:
            print(
                f"NON-ARXIV {row['thread']} {row['other_urls'][:2]} | {row['text'][:80]!r}"
            )
    print(f"{len(unlinked)} unlinked threads written to {links_path}")


if __name__ == "__main__":
    main()
