"""Re-check every registered `.eval_results` PR against the live leaderboards. Dry run unless --apply.

Ranks drift as other results land. For each open PR, point each benchmark link at the broadest view
where its result is still in the top 50, remove results that are visible nowhere, and close a PR only
when it had previewable results and all of them were removed. A PR whose results are not tagged with
its number (it edits an existing file, so the Hub previews main until merge) is reported, never closed.
"""

import argparse
import json
import re
import urllib.parse
from pathlib import Path

from huggingface_hub import CommitOperationDelete, HfApi

import hub_leaderboard as hub

BULLET = re.compile(
    r"^- \*\*\[([^\]]+)\]\((https://huggingface\.co/datasets/([^/?]+/[^/?]+)\?[^)]*)\)\*\*$",
    re.M,
)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--registry", type=Path, default=Path("reports/hf-eval-results-prs.json")
    )
    parser.add_argument(
        "--author", default="nielsr", help="only touch PRs opened by this Hub user"
    )
    parser.add_argument(
        "--apply", action="store_true", help="edit and close PRs (default: dry run)"
    )
    args = parser.parse_args()
    api = HfApi()
    for repo, num in json.loads(args.registry.read_text()):
        d = api.get_discussion_details(repo, num)
        if not d.is_pull_request or d.author != args.author:
            print(f"{repo}#{num}: not a PR by {args.author}, skipped")
            continue
        if d.status != "open":
            print(f"{repo}#{num}: {d.status}")
            continue
        info = (
            hub.fetch(
                f"{hub.HUB}/api/models/{repo}/revision/refs%2Fpr%2F{num}?expand[]=evalResults"
            )
            or {}
        )
        ours = [r for r in info.get("evalResults") or [] if r.get("pullRequest") == num]
        if not ours:
            print(
                f"{repo}#{num}: no previewable results (edits an existing file?), left as is"
            )
            continue
        keep, drop = {}, []
        for r in ours:
            ds, task, value = (
                r["data"]["dataset"]["id"],
                r["data"]["dataset"]["task_id"],
                r["data"]["value"],
            )
            found = hub.visible_view(repo, ds, task, value)
            if found:
                keep[ds, task] = (hub.link(repo, ds, task, found[0]), found)
            else:
                drop.append((r["filename"], ds, value))
        summary = ", ".join(
            f"{hub.bench_name(ds)} {task} rank {rank} ({hub.describe(view)})"
            for (ds, task), (_, (view, rank)) in keep.items()
        )
        print(f"{repo}#{num}: keep [{summary}] drop {[(ds, v) for _, ds, v in drop]}")

        first = next(e for e in d.events if e.type == "comment")
        body = first.content
        for label, url, ds in BULLET.findall(first.content):
            task = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(
                "leaderboard_task_id", [""]
            )[0]
            if (ds, task) in keep:
                body = body.replace(f"({url})", f"({keep[ds, task][0]})")
            else:
                body = re.sub(
                    rf"^- \*\*\[{re.escape(label)}\]\({re.escape(url)}\)\*\*\n",
                    "",
                    body,
                    flags=re.M,
                )
        if not args.apply:
            continue
        if not keep:
            api.comment_discussion(
                repo,
                num,
                "Closing: none of these results would currently be visible in the "
                "top 50 of their leaderboards, under any parameter-size filter.",
            )
            api.change_discussion_status(repo, num, "closed")
            print("  closed")
            continue
        if drop:
            # A file may still hold a kept task of the same benchmark; then leave the file for a manual edit.
            kept_files = {
                r["filename"]
                for r in ours
                if (r["data"]["dataset"]["id"], r["data"]["dataset"]["task_id"]) in keep
            }
            drop = [d for d in drop if d[0] not in kept_files]
        if drop:
            api.create_commit(
                repo,
                operations=[CommitOperationDelete(f) for f, _, _ in drop],
                revision=f"refs/pr/{num}",
                commit_message="Remove results outside the visible leaderboard top 50",
            )
            if d.title.startswith("Add community evaluation results for "):
                api.rename_discussion(
                    repo,
                    num,
                    "Add community evaluation results for "
                    + ", ".join(dict.fromkeys(hub.bench_name(ds) for ds, _ in keep)),
                )
        if body != first.content:
            api.edit_discussion_comment(repo, num, first.id, body)
            print("  updated")


if __name__ == "__main__":
    main()
