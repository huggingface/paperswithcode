# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "huggingface_hub>=1.0",
#   "pyyaml>=6.0",
# ]
# ///
"""Port Artificial Analysis scores to Hub model repos as `.eval_results` PRs.

Runs as a scheduled Hugging Face Job. It reads the Artificial Analysis data
API, matches each model strictly to a repo in its creator's official Hub
organization, and proposes `.eval_results/*.yaml` entries for official Hub
benchmarks the repo does not report yet (on `main` or in an open PR).

Dry-run is the default and only prints the plan; `--apply` opens the PRs.
Environment: `ARTIFICIAL_ANALYSIS_API_KEY` and `HF_TOKEN`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

AA_MODELS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
PR_TITLE = "Add Artificial Analysis evaluation results"
EVAL_RESULTS_DIR = ".eval_results/"


@dataclass(frozen=True)
class Benchmark:
    aa_key: str
    dataset_id: str
    task_id: str
    filename: str
    label: str
    source_url: str
    setup: str


BENCHMARKS = [
    Benchmark(
        "gpqa",
        "Idavidrein/gpqa",
        "diamond",
        "gpqa-diamond.yaml",
        "GPQA Diamond",
        "https://artificialanalysis.ai/evaluations/gpqa-diamond",
        "198 GPQA Diamond questions",
    ),
    Benchmark(
        "mmlu_pro",
        "TIGER-Lab/MMLU-Pro",
        "mmlu_pro",
        "mmlu-pro.yaml",
        "MMLU-Pro",
        "https://artificialanalysis.ai/evaluations/mmlu-pro",
        "12k MMLU-Pro questions with ten answer options",
    ),
    Benchmark(
        "terminalbench_v2_1",
        "harborframework/terminal-bench-2.1",
        "terminalbench_2_1",
        "terminal-bench-2.1.yaml",
        "Terminal-Bench 2.1",
        "https://artificialanalysis.ai/evaluations/terminalbench-2-1",
        "Terminus 2 harness in an e2b sandbox, pass@1 averaged over three repeats",
    ),
    Benchmark(
        "terminalbench_v4_0",
        "harborframework/terminal-bench",
        "terminalbench_4",
        "terminal-bench-4.0.yaml",
        "Terminal-Bench 4.0",
        "https://artificialanalysis.ai/evaluations/terminalbench-4-0",
        "mini-swe-agent harness, pass@1 averaged over three repeats",
    ),
]

# Official Hub organizations per Artificial Analysis creator slug. Creators
# without open-weight releases on the Hub are left out on purpose.
CREATOR_ORGS = {
    "ai2": ["allenai"],
    "ai21-labs": ["ai21labs"],
    "alibaba": ["Qwen"],
    "arcee": ["arcee-ai"],
    "azure": ["microsoft"],
    "baidu": ["baidu"],
    "bytedance_seed": ["ByteDance-Seed"],
    "cohere": ["CohereLabs"],
    "databricks": ["databricks"],
    "deepcogito": ["deepcogito"],
    "deepseek": ["deepseek-ai"],
    "google": ["google"],
    "ibm": ["ibm-granite"],
    "ifm": ["IFM", "LLM360"],
    "inclusionai": ["inclusionAI"],
    "kimi": ["moonshotai"],
    "lg": ["LGAI-EXAONE"],
    "liquidai": ["LiquidAI"],
    "longcat": ["meituan-longcat"],
    "meta": ["meta-llama", "meta-models"],
    "minimax": ["MiniMaxAI"],
    "mistral": ["mistralai"],
    "motif-technologies": ["Motif-Technologies"],
    "nanbeige": ["Nanbeige"],
    "nous-research": ["NousResearch"],
    "nvidia": ["nvidia"],
    "openai": ["openai"],
    "openbmb": ["openbmb"],
    "prime-intellect": ["PrimeIntellect"],
    "reflection": ["reflection"],
    "sarvam": ["sarvamai"],
    "servicenow": ["ServiceNow-AI"],
    "stepfun": ["stepfun-ai"],
    "swiss-ai-initiative": ["swiss-ai"],
    "tencent": ["tencent"],
    "thinking-machines": ["thinkingmachines"],
    "tii-uae": ["tiiuae"],
    "upstage": ["upstage"],
    "xiaomi": ["XiaomiMiMo"],
    "zai": ["zai-org"],
}

# Repo-name tail tokens that keep a repo the same checkpoint as the AA model:
# total and active parameter counts, a full-precision dtype, and Instruct.
SEPARATOR = re.compile(r"[-_\s]")
SIZE_TOKEN = re.compile(r"\d+(?:\.\d+)?[bmt]|a\d+(?:\.\d+)?[bm]")
INSTRUCT_TOKENS = {"instruct", "it"}
# AA dates some variants, e.g. "DeepSeek-V2.5 (Dec '24)" is the 1210 checkpoint.
DATED_VARIANT = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", re.I
)


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def base_model_name(aa_name: str) -> str:
    """Drop AA variant annotations such as "(Max)" or "(Reasoning, Based on X)"."""
    return re.sub(r"\s*\([^)]*\)", "", aa_name).strip()


def variant_annotations(aa_name: str) -> str:
    return " ".join(re.findall(r"\(([^)]*)\)", aa_name))


def name_tail(model: str, repo_name: str) -> str | None:
    """Return what follows `model` in `repo_name`, ignoring punctuation and case."""
    consumed = 0
    for index, char in enumerate(repo_name):
        if not char.isalnum():
            continue
        if consumed == len(model) or char.lower() != model[consumed]:
            return None
        consumed += 1
        if consumed == len(model):
            return repo_name[index + 1 :]
    return None


def is_reasoning_variant(aa_name: str) -> bool:
    return (
        re.search(r"(?<!non-)\breasoning\b", variant_annotations(aa_name), re.I)
        is not None
    )


def matched_tail(aa_name: str, repo_id: str, org: str) -> list[str] | None:
    """Return the repo-name tail tokens after the AA model name, or None."""
    if DATED_VARIANT.search(variant_annotations(aa_name)):
        return None
    allowed = {"bf16"} | INSTRUCT_TOKENS
    model = normalize(base_model_name(aa_name))
    repo_name = repo_id.split("/", 1)[1]
    names = [repo_name]
    if repo_name.lower().startswith(org.lower()) and SEPARATOR.match(
        repo_name[len(org) :]
    ):
        names.append(repo_name[len(org) + 1 :])
    for name in names:
        tail = name_tail(model, name) if model else None
        if tail is None or (tail and not SEPARATOR.match(tail)):
            continue
        tokens = [t.lower() for t in SEPARATOR.split(tail) if t]
        if all(SIZE_TOKEN.fullmatch(t) or t in allowed for t in tokens):
            return tokens
    return None


def repo_matches(aa_name: str, repo_id: str, org: str) -> bool:
    return matched_tail(aa_name, repo_id, org) is not None


@dataclass
class Candidate:
    repo_id: str
    scores: dict[str, tuple[float, str]] = field(default_factory=dict)

    def offer(self, benchmark: Benchmark, value: float, variant: str) -> None:
        current = self.scores.get(benchmark.aa_key)
        if current is None or value > current[0]:
            self.scores[benchmark.aa_key] = (value, variant)


def fetch_aa_models(api_key: str) -> list[dict]:
    request = urllib.request.Request(
        AA_MODELS_URL, headers={"x-api-key": api_key, "User-Agent": "curl/8.5.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["data"]


def score_percent(model: dict, benchmark: Benchmark) -> float | None:
    value = (model.get("evaluations") or {}).get(benchmark.aa_key)
    if value is None:
        return None
    percent = round(value * 100, 1)
    return percent if percent > 0 else None


def match_candidates(
    api: HfApi, aa_models: list[dict]
) -> tuple[dict[str, Candidate], list[str]]:
    org_repos: dict[str, list[str]] = {}
    candidates: dict[str, Candidate] = {}
    skipped = []
    for model in aa_models:
        scores = [(b, score_percent(model, b)) for b in BENCHMARKS]
        scores = [(b, v) for b, v in scores if v is not None]
        orgs = CREATOR_ORGS.get(model["model_creator"]["slug"])
        if not scores or not orgs:
            continue
        matches = {}
        for org in orgs:
            if org not in org_repos:
                org_repos[org] = [m.id for m in api.list_models(author=org)]
            for repo_id in org_repos[org]:
                tokens = matched_tail(model["name"], repo_id, org)
                if tokens is not None:
                    matches[repo_id] = tokens
        if len(matches) != 1:
            skipped.append(
                f"{model['name']}: {len(matches)} repo matches {list(matches)[:4]}"
            )
            continue
        ((repo_id, tokens),) = matches.items()
        # Hybrid repos carry reasoning scores, but an Instruct repo is the
        # non-thinking sibling of a separate Thinking release.
        if is_reasoning_variant(model["name"]) and INSTRUCT_TOKENS & set(tokens):
            skipped.append(
                f"{model['name']}: reasoning variant on Instruct repo {repo_id}"
            )
            continue
        candidate = candidates.setdefault(repo_id, Candidate(repo_id))
        for benchmark, value in scores:
            candidate.offer(benchmark, value, model["name"])
    return candidates, skipped


def reported_tasks(api: HfApi, repo_id: str, revision: str | None = None) -> set[tuple]:
    tasks = set()
    files = api.list_repo_files(repo_id, revision=revision)
    for path in files:
        if not (path.startswith(EVAL_RESULTS_DIR) and path.endswith((".yaml", ".yml"))):
            continue
        local = Path(hf_hub_download(repo_id, path, revision=revision))
        entries = yaml.safe_load(local.read_text(encoding="utf-8")) or []
        # Hand-written PR files sometimes hold a single mapping instead of a list.
        for entry in entries if isinstance(entries, list) else [entries]:
            if not isinstance(entry, dict):
                continue
            dataset = entry.get("dataset") or {}
            tasks.add((dataset.get("id"), dataset.get("task_id")))
    return tasks


@dataclass
class PlannedPr:
    repo_id: str
    entries: list[tuple[Benchmark, float, str]]
    taken_paths: set[str]


def plan_repo(api: HfApi, candidate: Candidate, me: str | None) -> PlannedPr | str:
    info = api.model_info(candidate.repo_id)
    if info.gated or info.private:
        return "gated or private"
    reported = reported_tasks(api, candidate.repo_id)
    taken_paths = {
        p
        for p in api.list_repo_files(candidate.repo_id)
        if p.startswith(EVAL_RESULTS_DIR)
    }
    for discussion in api.get_repo_discussions(candidate.repo_id):
        if not discussion.is_pull_request:
            continue
        if (
            discussion.status == "closed"
            and discussion.author == me
            and discussion.title == PR_TITLE
        ):
            return f"our PR #{discussion.num} was closed"
        if discussion.status == "open":
            revision = f"refs/pr/{discussion.num}"
            reported |= reported_tasks(api, candidate.repo_id, revision)
            taken_paths |= {
                p
                for p in api.list_repo_files(candidate.repo_id, revision=revision)
                if p.startswith(EVAL_RESULTS_DIR)
            }
    entries = [
        (b, *candidate.scores[b.aa_key])
        for b in BENCHMARKS
        if b.aa_key in candidate.scores and (b.dataset_id, b.task_id) not in reported
    ]
    return (
        PlannedPr(candidate.repo_id, entries, taken_paths)
        if entries
        else "already reported"
    )


def eval_results_yaml(benchmark: Benchmark, value: float, variant: str) -> str:
    entry = [
        {
            "dataset": {"id": benchmark.dataset_id, "task_id": benchmark.task_id},
            "value": value,
            "source": {
                "url": benchmark.source_url,
                "name": f"Artificial Analysis {benchmark.label} leaderboard",
                "user": "ArtificialAnalysis",
            },
            "notes": f"{variant}; {benchmark.setup}.",
        }
    ]
    return yaml.safe_dump(entry, sort_keys=False, allow_unicode=True)


def pr_description(plan: PlannedPr) -> str:
    lines = [
        f"- **{b.label}** (`{b.dataset_id}`, `{b.task_id}`): {value}, "
        f"from the [Artificial Analysis leaderboard]({b.source_url}) ({variant})."
        for b, value, variant in plan.entries
    ]
    return (
        "This PR adds evaluation results in the [`.eval_results/` format]"
        "(https://huggingface.co/docs/hub/main/en/eval-results#adding-evaluation-results), "
        "so they show up on the official benchmark leaderboards on the Hub.\n\n"
        + "\n".join(lines)
        + "\n\nThe scores come from independent evaluations by "
        "[Artificial Analysis](https://artificialanalysis.ai/). When a model has several "
        "reasoning-effort variants, the best-scoring one is used and named in each entry's notes."
    )


def file_path(benchmark: Benchmark, taken_paths: set[str]) -> str:
    path = EVAL_RESULTS_DIR + benchmark.filename
    if path in taken_paths:
        path = path.replace(".yaml", "-artificial-analysis.yaml")
    return path


def open_pr(api: HfApi, plan: PlannedPr) -> str:
    operations = [
        CommitOperationAdd(
            file_path(b, plan.taken_paths),
            eval_results_yaml(b, value, variant).encode(),
        )
        for b, value, variant in plan.entries
    ]
    commit = api.create_commit(
        repo_id=plan.repo_id,
        operations=operations,
        commit_message=PR_TITLE,
        commit_description=pr_description(plan),
        create_pr=True,
    )
    return commit.pr_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="open PRs instead of printing the plan"
    )
    parser.add_argument("--max-prs", type=int, default=10)
    args = parser.parse_args()

    api = HfApi()
    me = api.whoami()["name"]
    aa_models = fetch_aa_models(os.environ["ARTIFICIAL_ANALYSIS_API_KEY"])
    candidates, skipped = match_candidates(api, aa_models)
    print(
        f"{len(aa_models)} AA models, {len(candidates)} matched repos, {len(skipped)} unmatched"
    )
    for line in skipped:
        print(f"  unmatched: {line}")

    opened = 0
    for candidate in sorted(candidates.values(), key=lambda c: c.repo_id):
        plan = plan_repo(api, candidate, me)
        if isinstance(plan, str):
            print(f"skip {candidate.repo_id}: {plan}")
            continue
        summary = ", ".join(
            f"{b.label}={value} ({variant})" for b, value, variant in plan.entries
        )
        if opened >= args.max_prs:
            print(f"cap reached, deferred {plan.repo_id}: {summary}")
            continue
        if args.apply:
            print(f"opened {open_pr(api, plan)}: {summary}")
        else:
            print(f"would open {plan.repo_id}: {summary}")
        opened += 1
    print(f"{'opened' if args.apply else 'planned'} {opened} PRs")


if __name__ == "__main__":
    main()
