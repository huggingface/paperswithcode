"""Open one `.eval_results` PR per Hub model repo from a JSON spec. Dry run unless --apply.

Spec: a JSON list of
  {"repo": "org/model", "source_url": "...", "source_name": "Model Card",
   "origin": "the model card (\"On Terminal-Bench 2.0 it scores 9.36%\")",
   "results": [{"dataset": "harborframework/terminal-bench-2.0", "task_id": "terminalbench_2",
                "value": 9.36, "notes": "optional protocol note"}]}

`origin` completes the sentence "These results were extracted from ..." and must tell the reviewer
where to find each number. Every result is checked before anything is written: the task id exists
in the benchmark's eval.yaml, the repo is not a personal account, the benchmark is not already
declared on main or in an open PR, and the result would rank in the visible top 50 of some view.
"""

import argparse
import html
import json
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

import hub_leaderboard as hub


def render(repo, origin, results, views):
    """PR title and description, formatted like meta-models/Muse-Glimmer-30B#8.

    `views` maps (dataset, task_id) to the leaderboard view each link opens. A benchmark reported
    for several tasks (ParseBench sub-scores) gets one link per task, labelled with the task id.
    """
    counts = Counter(r["dataset"] for r in results)
    bullets = []
    for r in results:
        label = hub.bench_name(r["dataset"]) + (
            f" ({r['task_id']})" if counts[r["dataset"]] > 1 else ""
        )
        url = hub.link(
            repo, r["dataset"], r["task_id"], views[r["dataset"], r["task_id"]]
        )
        bullets.append(f"- **[{label}]({url})**")
    title = "Add community evaluation results for " + ", ".join(
        hub.bench_name(ds) for ds in counts
    )
    body = (
        "This PR adds community-provided evaluation results for the following benchmarks:\n\n"
        + "\n".join(bullets)
        + f"\n\nThese results were extracted from {origin}. This is based on the new "
        "[evaluation results feature](https://huggingface.co/docs/hub/eval-results).\n\n"
        "*Note: This is an automated PR. Please review the evaluation results before merging.*"
    )
    return title, body


def result_yaml(r, source_url, source_name):
    notes = f"  notes: {json.dumps(r['notes'])}\n" if r.get("notes") else ""
    return (
        f"- dataset:\n    id: {r['dataset']}\n    task_id: {r['task_id']}\n  value: {r['value']}\n"
        f"{notes}  source:\n    url: {source_url}\n    name: {source_name}\n"
    )


def model_card(url):
    """(repo id, revision) when `url` points at a model card (any revision, README, anchor), else None."""
    m = re.fullmatch(
        r"https://huggingface\.co/(?!datasets/|spaces/|papers/)([^/]+/[^/?#]+)"
        r"(?:/tree/([^/?#]+)|/blob/([^/?#]+)/README\.md)?/?(?:[?#].*)?",
        url,
    )
    return (m[1], m[2] or m[3] or "main") if m else None


def source_text(url):
    """Plain text of the cited source, for the findability check (model cards via raw README)."""
    card = model_card(url)
    if card:
        repo, revision = card
        return hub.fetch(f"{hub.HUB}/{repo}/raw/{revision}/README.md", raw=True) or ""
    url = url.replace("arxiv.org/abs/", "arxiv.org/html/")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            page = f.read().decode("utf8", "replace")
    except urllib.error.URLError as e:
        print(f"  could not fetch {url} ({e}); check findability by hand")
        return ""
    return html.unescape(re.sub(r"<[^>]+>", " ", page))


def check(spec):
    """Keep the results that pass every gate; return (repo spec, {dataset: view}) or None."""
    repo = spec["repo"]
    if hub.namespace_kind(repo.split("/")[0]) == "user":
        print(
            f"  {repo}: personal account, skipped (its results never appear on leaderboards)"
        )
        return None
    declared = hub.declared_datasets(repo)
    if declared is None:
        print(f"  {repo}: discussions are disabled, so no PR can be opened; skipped")
        return None
    text = source_text(spec["source_url"])
    keep, views = [], {}
    for r in spec["results"]:
        label = f"{repo} {r['dataset']} {r['value']}"
        if r["task_id"] not in hub.task_ids(hub.eval_yaml(r["dataset"])):
            print(f"  {label}: task_id {r['task_id']!r} not in eval.yaml, skipped")
            continue
        if r["dataset"] in declared:
            print(f"  {label}: already declared on main or in an open PR, skipped")
            continue
        found = hub.predicted_view(repo, r["dataset"], r["task_id"], float(r["value"]))
        if not found:
            print(f"  {label}: outside the top 50 in every view, skipped")
            continue
        if str(r["value"]) not in text:
            print(
                f"  {label}: WARNING value not in the source text; say where it is (image, hidden view) in origin"
            )
        print(f"  {label}: rank {found[1]} ({hub.describe(found[0])})")
        keep.append(r)
        views[r["dataset"], r["task_id"]] = found[0]
    return ({**spec, "results": keep}, views) if keep else None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("reports/hf-eval-results-prs.json"),
        help="JSON list of [repo, pr number] that sweep_eval_prs.py re-checks",
    )
    parser.add_argument(
        "--apply", action="store_true", help="open the PRs (default: dry run)"
    )
    args = parser.parse_args()
    api = HfApi()
    registry = json.loads(args.registry.read_text()) if args.registry.exists() else []
    for spec in json.loads(args.spec.read_text()):
        checked = check(spec)
        if not checked:
            continue
        spec, views = checked
        title, body = render(spec["repo"], spec["origin"], spec["results"], views)
        files = defaultdict(
            str
        )  # one file per benchmark dataset, one list entry per task
        for r in spec["results"]:
            files[f".eval_results/{r['dataset'].split('/')[1].lower()}.yaml"] += (
                result_yaml(r, spec["source_url"], spec["source_name"])
            )
        ops = [
            CommitOperationAdd(path, content.encode())
            for path, content in files.items()
        ]
        if not args.apply:
            print(f"## {spec['repo']}\n{title}\n\n{body}\n")
            for op in ops:
                print(f"--- {op.path_in_repo}\n{op.path_or_fileobj.decode()}")
            continue
        info = api.create_commit(
            spec["repo"],
            operations=ops,
            commit_message=title,
            commit_description=body,
            create_pr=True,
        )
        print(spec["repo"], info.pr_url)
        registry.append([spec["repo"], info.pr_num])
        args.registry.parent.mkdir(parents=True, exist_ok=True)
        args.registry.write_text(json.dumps(registry, indent=0) + "\n")


if __name__ == "__main__":
    main()
