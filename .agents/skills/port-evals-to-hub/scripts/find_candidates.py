"""List PwC evaluations that could be ported to a Hub benchmark leaderboard, newest models first.

Reads evaluations with an `hf_model_url` on the PwC leaderboards mapped in MAPPING (read-only), and
writes a CSV with each row's Hub status: already on the board (merged or open PR), already declared
in `.eval_results`, or a candidate. Every candidate still needs its value, source, protocol, and
checkpoint verified by hand before it goes into an open_eval_prs.py spec.

    uv run --env-file backend/keys.env python .agents/skills/port-evals-to-hub/scripts/find_candidates.py out.csv
"""

import csv
import re
import sys
from pathlib import Path

from sqlalchemy import text

import hub_leaderboard as hub

sys.path.insert(
    0, str(Path(__file__).resolve().parents[4])
)  # repository root, for `backend`
from backend.database.connection import db_manager  # noqa: E402

# (PwC dataset id, PwC metric, Hub benchmark dataset, Hub task_id). Check
# https://huggingface.co/datasets?benchmark=benchmark:official for new official benchmarks and add them here.
MAPPING = [
    (82, "Accuracy", "cais/hle", "hle"),
    (38, "Accuracy", "Idavidrein/gpqa", "diamond"),
    (20, "Accuracy", "TIGER-Lab/MMLU-Pro", "mmlu_pro"),
    (45, "Accuracy", "openai/gsm8k", "gsm8k"),
    (1984, "Pass Rate", "agents-last-exam/agents-last-exam", "ale-cli-pass-rate"),
    (22, "Accuracy", "SWE-bench/SWE-bench_Verified", "swe_bench_%_resolved"),
    (23, "Accuracy", "ScaleAI/SWE-bench_Pro", "SWE_Bench_Pro"),
    (
        427,
        "Accuracy",
        "SWE-bench/SWE-bench_Multilingual",
        "swe_bench_multilingual_%_resolved",
    ),
    (
        813,
        "Pass@1",
        "datacurve/deep-swe",
        "deep_swe",
    ),  # PwC stores fractions; the Hub board uses percent
    (37, "Accuracy", "harborframework/terminal-bench-2.0", "terminalbench_2"),
    (686, "Accuracy", "harborframework/terminal-bench-2.1", "terminalbench_2_1"),
    (1980, "Accuracy", "harborframework/terminal-bench", "terminalbench_3"),
    (2570, "Accuracy", "harborframework/terminal-bench", "terminalbench_4"),
    (847, "Overall (ParseBench)", "llamaindex/ParseBench", "mean"),
    (847, "Tables", "llamaindex/ParseBench", "table"),
    (847, "Charts", "llamaindex/ParseBench", "chart"),
    (847, "Content Faithfulness", "llamaindex/ParseBench", "text_content"),
    (847, "Semantic Formatting", "llamaindex/ParseBench", "text_formatting"),
    (847, "Visual Grounding", "llamaindex/ParseBench", "layout"),
    (141, "Accuracy", "allenai/olmOCR-bench", "overall"),
    (685, "Accuracy", "PaddlePaddle/Real5-OmniDocBench", "overall"),
    (1199, "MDPBench Overall", "Delores-Lin/MDPBench", "overall"),
    (1199, "MDPBench Latin", "Delores-Lin/MDPBench", "latin"),
    (1199, "MDPBench Non-Latin", "Delores-Lin/MDPBench", "non_latin"),
    (1199, "MDPBench Private", "Delores-Lin/MDPBench", "private"),
    (1985, "Pass Rate", "benchflow/skillsbench", "skillsbench_v1_1"),
    (28, "Accuracy", "likaixin/ScreenSpot-Pro", "overall"),
    (444, "Accuracy", "MathArena/aime_2026", "MathArena/aime_2026"),
    (683, "Accuracy", "MathArena/hmmt_feb_2026", "MathArena/hmmt_feb_2026"),
    (1341, "WBench Navigation Average", "meituan-longcat/WBench", "wbench_navi"),
]
# Major labs, listed first in the CSV. Any other Hub organization is fine too; personal accounts are not.
MAJOR = {
    o.lower()
    for o in """microsoft google nvidia Anthropic deepseek-ai meta-llama Qwen black-forest-labs
stabilityai moonshotai facebook zai-org ByteDance ByteDance-Seed mistralai allenai xai-org openai apple tencent
MiniMaxAI poolside PrimeIntellect LiquidAI openbmb ibm-granite stepfun-ai meituan-longcat internlm XiaomiMiMo
inclusionAI thinkingmachines Nanbeige JetBrains amazon arcee-ai HuggingFaceTB""".split()
}


def repo_of(url):
    m = re.match(r"https?://huggingface\.co/([^/?#]+/[^/?#]+)", url or "")
    return m[1] if m else None


def main():
    out = sys.argv[1]
    rows = []
    with db_manager.session_local() as db:
        for dataset_id, metric, hub_ds, task in MAPPING:
            evals = db.execute(
                text("""
                SELECT e.id, e.model_name, e.hf_model_url, e.metrics->>:m AS value,
                       COALESCE(e.external_source_url, e.source_url) AS source, e.created_at
                FROM evaluations e
                WHERE e.dataset_id = :d AND e.hf_model_url IS NOT NULL AND e.metrics ? :m
            """),
                {"d": dataset_id, "m": metric},
            ).all()
            on_board = {
                e["modelId"].lower()
                for e in hub.board(hub_ds, task, {"base_model": "false"})
            }
            for e in evals:
                repo = repo_of(e.hf_model_url)
                if repo:
                    rows.append(
                        dict(
                            eval_id=e.id,
                            model=e.model_name,
                            repo=repo,
                            hub=hub_ds,
                            task=task,
                            metric=metric,
                            value=e.value,
                            source=e.source or "",
                            on_board=repo.lower() in on_board,
                        )
                    )
    kinds, facts, declared = {}, {}, {}
    for r in rows:
        ns = r["repo"].split("/")[0]
        if ns not in kinds:
            kinds[ns] = "major" if ns.lower() in MAJOR else hub.namespace_kind(ns)
        r["org_tier"] = kinds[ns]
        if r["org_tier"] == "user" or r["on_board"]:
            r["status"] = "personal_account" if r["org_tier"] == "user" else "on_board"
            continue
        if r["repo"] not in facts:
            facts[r["repo"]] = hub.fetch(f"{hub.HUB}/api/models/{r['repo']}") or {}
            declared[r["repo"]] = (
                hub.declared_datasets(r["repo"]) if facts[r["repo"]] else set()
            )
        info = facts[r["repo"]]
        r["model_created"] = (info.get("createdAt") or "")[:10]
        r["downloads"] = info.get("downloads", 0)
        if not info:
            r["status"] = "repo_missing"
        elif declared[r["repo"]] is None:
            r["status"] = "discussions_disabled"
        elif r["hub"] in declared[r["repo"]]:
            r["status"] = "already_declared"
        else:
            r["status"] = "candidate"
    rows.sort(key=lambda r: r.get("model_created", ""), reverse=True)
    rows.sort(key=lambda r: (r["status"] != "candidate", r["org_tier"] != "major"))
    fields = [
        "status",
        "org_tier",
        "model_created",
        "downloads",
        "repo",
        "model",
        "hub",
        "task",
        "metric",
        "value",
        "source",
        "eval_id",
        "on_board",
    ]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(
        out,
        {
            s: sum(r["status"] == s for r in rows)
            for s in sorted({r["status"] for r in rows})
        },
    )


if __name__ == "__main__":
    main()
