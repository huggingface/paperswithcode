"""Read Hub benchmark leaderboards and find the views in which a model's result is visible.

The leaderboard UI shows ranks 1-50 of the selected view only. A view is a combination of the
"Parameters Size" filter (`max_params`) and the "Base only" toggle (`base_model`), which is on by
default and hides every model whose card declares a `base_model`.
"""

import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

HUB = "https://huggingface.co"
TIERS = [
    "500B",
    "128B",
    "32B",
    "12B",
    "6B",
    "3B",
    "1B",
]  # the UI's "Parameters Size" buttons
VIEWS = (
    [{}, {"base_model": "false"}]
    + [{"max_params": t} for t in TIERS]
    + [{"max_params": t, "base_model": "false"} for t in TIERS]
)
VISIBLE_RANKS = 50

# Benchmark names as their authors write them. Other benchmarks fall back to the `name` in eval.yaml.
NAMES = {
    "allenai/olmOCR-bench": "olmOCR-Bench",
    "harborframework/terminal-bench-2.0": "Terminal-Bench 2.0",
    "harborframework/terminal-bench-2.1": "Terminal-Bench 2.1",
    "SWE-bench/SWE-bench_Verified": "SWE-bench Verified",
    "SWE-bench/SWE-bench_Multilingual": "SWE-bench Multilingual",
    "ScaleAI/SWE-bench_Pro": "SWE-Bench Pro",
    "likaixin/ScreenSpot-Pro": "ScreenSpot-Pro",
    "cais/hle": "Humanity's Last Exam",
    "Idavidrein/gpqa": "GPQA Diamond",
    "TIGER-Lab/MMLU-Pro": "MMLU-Pro",
    "MathArena/aime_2026": "AIME 2026",
    "MathArena/hmmt_feb_2026": "HMMT February 2026",
    "openai/gsm8k": "GSM8K",
    "meituan-longcat/WBench": "WBench",
    "datacurve/deep-swe": "DeepSWE",
}

_token = None
_cache = {}


def token():
    global _token
    if _token is None:
        out = subprocess.run(
            ["hf", "auth", "token"], capture_output=True, text=True
        ).stdout
        _token = out.strip().splitlines()[-1]
    return _token


def fetch(url, raw=False, missing_ok=True):
    """GET a Hub URL with the user's token, retrying rate limits.

    Returns None for a missing, gated, or private resource (401/403/404) when `missing_ok`; callers whose
    decisions depend on the answer (leaderboards) pass False so an error never reads as "no entries".
    """
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token()}"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as f:
                body = f.read().decode("utf8", "replace")
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if missing_ok and e.code in (401, 403, 404):
                return None
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(20 * (attempt + 1))


def board(ds, task, view):
    """Every leaderboard entry in a view, including results from open PRs (tagged `pullRequest`)."""
    key = (ds, task, tuple(sorted(view.items())))
    if key not in _cache:
        query = urllib.parse.urlencode({"task_id": task, **view})
        _cache[key] = fetch(
            f"{HUB}/api/datasets/{ds}/leaderboard?{query}", missing_ok=False
        )
    return _cache[key]


def eval_yaml(ds):
    key = ("eval.yaml", ds)
    if key not in _cache:
        _cache[key] = fetch(f"{HUB}/datasets/{ds}/raw/main/eval.yaml", raw=True) or ""
    return _cache[key]


def task_ids(yaml_text):
    """Task ids declared in an eval.yaml."""
    return re.findall(r"^\s*-\s*id:\s*['\"]?([^'\"\s]+)", yaml_text, re.M)


def bench_name(ds):
    if ds not in NAMES:
        NAMES[ds] = re.search(r"^name:\s*['\"]?(.+?)['\"]?\s*$", eval_yaml(ds), re.M)[1]
    return NAMES[ds]


def link(repo, ds, task, view):
    """Leaderboard URL that opens `view` with this repo's result highlighted."""
    params = {
        "eval_result": repo,
        "leaderboard_task_id": task,
        **{f"leaderboard_{k}": v for k, v in view.items()},
    }
    return f"{HUB}/datasets/{ds}?" + urllib.parse.urlencode(params, safe="/")


def model_facts(repo):
    """(safetensors parameter count or None, whether the card declares a base_model)."""
    d = fetch(f"{HUB}/api/models/{repo}?expand[]=safetensors&expand[]=cardData") or {}
    return (d.get("safetensors") or {}).get("total"), bool(
        (d.get("cardData") or {}).get("base_model")
    )


def namespace_kind(namespace):
    """'org' for a Hub organization, 'user' for a personal account. Results on user repos never show."""
    return "org" if fetch(f"{HUB}/api/organizations/{namespace}/overview") else "user"


def declared_datasets(repo):
    """Benchmark dataset ids already declared in .eval_results on main or in any open PR.

    Returns None when the repo has discussions disabled: no PR can be opened there.
    """
    found = set()
    try:  # get_repo_discussions paginates through every open PR
        open_prs = list(
            HfApi(token=token()).get_repo_discussions(
                repo, discussion_type="pull_request", discussion_status="open"
            )
        )
    except HfHubHTTPError as e:
        if e.response.status_code == 403 and "disabled" in str(e):
            return None
        raise
    revisions = ["main"] + [f"refs/pr/{d.num}" for d in open_prs]
    for rev in revisions:
        info = (
            fetch(
                f"{HUB}/api/models/{repo}/revision/{urllib.parse.quote(rev, safe='')}"
            )
            or {}
        )
        for sibling in info.get("siblings", []):
            if sibling["rfilename"].startswith(".eval_results/"):
                text = fetch(
                    f"{HUB}/{repo}/raw/{urllib.parse.quote(rev, safe='')}/{sibling['rfilename']}",
                    raw=True,
                )
                found.update(
                    re.findall(
                        r"^\s*id:\s*['\"]?([^'\"\s]+/[^'\"\s]+)", text or "", re.M
                    )
                )
    return found


def predicted_rank(entries, repo, value):
    """Rank a not-yet-declared result would get among `entries` (ties rank alongside)."""
    others = [e for e in entries if e["modelId"].lower() != repo.lower()]
    lower = bool(others and others[0].get("lower_is_better"))
    return 1 + sum(
        1
        for e in others
        if (float(e["value"]) < value if lower else float(e["value"]) > value)
    )


def predicted_view(repo, ds, task, value):
    """Broadest (view, rank) where a new result would sit in the visible top 50, or None."""
    params, finetune = model_facts(repo)
    for view in VIEWS:
        if "max_params" in view and (
            params is None or params > float(view["max_params"][:-1]) * 1e9
        ):
            continue
        if "base_model" not in view and finetune:
            continue
        rank = predicted_rank(board(ds, task, view), repo, value)
        if rank <= VISIBLE_RANKS:
            return view, rank
    return None


def visible_view(repo, ds, task, value):
    """Broadest (view, rank) where this repo's declared result is in the top 50, or None."""
    for view in VIEWS:
        for e in board(ds, task, view):
            if (
                e["modelId"].lower() == repo.lower()
                and abs(float(e["value"]) - float(value)) < 1e-6
            ):
                if e["rank"] <= VISIBLE_RANKS:
                    return view, e["rank"]
                break
    return None


def describe(view):
    parts = [
        f"<={view['max_params']}" if "max_params" in view else "all sizes",
        "base-only off" if view.get("base_model") == "false" else "base-only on",
    ]
    return ", ".join(parts)
