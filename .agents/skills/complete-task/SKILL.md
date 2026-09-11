---
name: complete-task
description: >-
  Complete the benchmark, paper, and evaluation data for a single Papers With Code task page end-to-end,
  using the legacy PwC dump as the source of truth for what the major benchmarks and papers are. Use this
  whenever the user wants to "complete", "fill out", "build out", "populate", "flesh out", "round out", or
  "finish" a task page; audit a task for missing benchmarks/evals; or says things like "make the
  motion-generation task complete", "add the top benchmarks and papers for object tracking", "populate
  evals for this task", or "bring the <task> leaderboards up to date". It mines the legacy
  evaluation-tables.json for the top benchmarks (by leaderboard entries) and their top papers, then
  orchestrates the add-benchmark, enrich-paper, add-evals, and verify-evals skills (one focused subagent
  each, always on Composer 2.5) to index papers, create missing benchmarks, import evaluations, and verify
  every leaderboard is apples-to-apples. Prefer this orchestration skill over running those skills ad hoc
  when the goal is whole-task completion rather than a single benchmark/paper/eval. When data already
  exists, it degrades gracefully into verifying what is there. Be memory-aware: the legacy dump is ~250 MB
  and this runs on a small VPS, so always stream it with the bundled miner rather than loading it.
---

# Complete a Task

This skill brings a single task page (e.g. `/tasks/motion-generation`) up to a "complete" state:
the major benchmarks exist and are linked to the task, their source papers are indexed and enriched,
the top papers have evaluation rows, and every leaderboard has been verified apples-to-apples.

It is an **orchestrator**. The real work is done by four existing skills, each run in its own subagent
so the context stays small and the work parallelizes:

| Sub-skill | Role here |
|-----------|-----------|
| `enrich-paper` | Add code links + task/method tags to each top paper (one subagent per paper). |
| `add-benchmark` | Create + task-link each major benchmark that isn't in the DB yet (one subagent per benchmark). |
| `add-evals` | Import the leaderboard rows for each top paper (one subagent per paper). |
| `verify-evals` | Audit each benchmark leaderboard for apples-to-apples comparability (one subagent per benchmark). |

The legacy Papers With Code dump (`data/legacy_pwc_data/evaluation-tables.json`) is the source of truth
for *which* benchmarks and papers matter — it already encodes years of community curation about what the
real leaderboards are. We mine it for the top benchmarks and their top papers, then re-create that data
properly in the live database via the sub-skills.

## Why delegate to subagents (and always on Composer 2.5)

Each sub-skill is long and reads a lot of source material (papers, model cards, READMEs, legacy tables).
Running them inline would blow up your context and make the orchestration unmanageable. Spawning one
subagent per unit of work (per paper, per benchmark) keeps each agent focused on a small, well-scoped job
and lets independent work run in parallel.

**Always pass `model: "composer-2.5-fast"` when launching these subagents.** Composer 2.5 is cheap and
plenty capable for these mechanical, well-specified sub-tasks, and the user has asked that all delegated
work in this pipeline use it. The orchestration (this skill) stays on whatever model the user is driving.

When launching a subagent, give it everything it needs to run autonomously: the exact sub-skill path to
read first, the task slug, the specific paper/benchmark it owns, the relevant legacy rows, and what to
report back. Subagents don't see this conversation, so be explicit.

## Pre-flight

Run everything from the repo root with the project environment:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the backend is up (start it without asking if not, per AGENTS.md):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/papers/recent?limit=1
```

Resolve the task row from the slug or name the user gave:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine
slug = "motion-generation"
with get_engine().connect() as conn:
    row = conn.execute(text(
        "SELECT id, name, slug FROM tasks WHERE slug = :s OR name ILIKE :n"
    ), {"s": slug, "n": f"%{slug.replace('-', ' ')}%"}).mappings().first()
    print(dict(row) if row else "TASK NOT FOUND")
PY
```

If the task itself doesn't exist, this is the wrong skill — use `add-task` first, then come back.

Use a TodoList to track the phases below; this is a long pipeline and it's easy to lose a benchmark or
paper partway through.

## Phase 1 — Mine the legacy dump for benchmarks + papers

The legacy file is ~250 MB. **Never load it whole** on this VPS. Use the bundled streaming miner.

Site task slugs rarely match legacy task names (the site's `motion-generation` lives under the legacy
task `Motion Synthesis`), so discover the legacy name first:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/complete-task/scripts/mine_legacy_task.py \
  --list-tasks "motion|dance|gesture"
```

Pick the legacy task name(s) that genuinely correspond to the site task — sometimes more than one legacy
task maps to one site task (e.g. `Motion Synthesis` + `Motion Captioning`). Then aggregate:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/complete-task/scripts/mine_legacy_task.py \
  --task "Motion Synthesis" --max-benchmarks 5 --max-papers 10 \
  --out /tmp/complete-<slug>.json
```

This returns, per benchmark (ranked by number of leaderboard rows, capped at the top 5):

- `benchmark`, `row_count`, `unique_papers`, the legacy `metrics` columns, and
- `top_papers`: up to 10 deduped papers with `model_name`, `metrics`, `paper_url`, `paper_title`, `paper_date`.

Keep the caps the user asked for — **at most 5 benchmarks, at most 10 papers per benchmark** — so the
pipeline stays bounded. The union of all `paper_url`s across benchmarks is your paper worklist; the set of
`benchmark` names is your benchmark worklist.

Sanity-check the picks against the live task page before committing to them — the legacy metric columns
tell you what leaderboard metrics the benchmark needs, and a benchmark with very few rows or an obviously
off-topic name (legacy regex matches are loose) should be dropped.

## Phase 2 — Take stock of what already exists

The user explicitly wants graceful degradation: benchmarks may already exist with many evals, and top
papers may already be indexed and enriched. **Do not redo finished work — verify it instead.** Check the
current state before launching any write subagents:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

task_id = <task_id>
benchmark_names = ["HumanML3D", "KIT Motion-Language", "AIST++", ...]
arxiv_ids = ["2312.00063", ...]  # parsed from legacy paper_url where possible

with get_engine().connect() as conn:
    print("== datasets / task link / metrics / eval count ==")
    for name in benchmark_names:
        rows = conn.execute(text("""
            SELECT d.id, d.name, d.slug,
                   bool_or(td.task_id = :tid) AS linked_to_task,
                   count(DISTINCT tdm.metric_id) FILTER (WHERE tdm.task_id = :tid) AS metrics_on_task,
                   count(DISTINCT e.id) FILTER (WHERE e.task_id = :tid) AS evals_on_task
            FROM datasets d
            LEFT JOIN task_datasets td ON td.dataset_id = d.id
            LEFT JOIN task_dataset_metrics tdm ON tdm.dataset_id = d.id
            LEFT JOIN evaluations e ON e.dataset_id = d.id
            WHERE d.name ILIKE :n OR d.slug ILIKE :s
            GROUP BY d.id, d.name, d.slug
        """), {"tid": task_id, "n": name, "s": name.lower().replace(" ", "-")}).mappings().all()
        print(name, "=>", [dict(r) for r in rows] or "MISSING")

    print("== papers indexed? ==")
    for aid in arxiv_ids:
        r = conn.execute(text(
            "SELECT id, arxiv_id, urls_extracted FROM papers WHERE arxiv_id = :a "
            "ORDER BY is_latest_version DESC NULLS LAST LIMIT 1"
        ), {"a": aid}).mappings().first()
        print(aid, "=>", dict(r) if r else "NOT INDEXED")
PY
```

From this, bucket each item:

- **Benchmark**: missing → Phase 3 (`add-benchmark`); exists but not linked to this task or missing the
  needed metric → Phase 3 (`add-benchmark` handles linking + metrics); fully wired with evals → skip to
  Phase 6 (`verify-evals`).
- **Paper**: not indexed → Phase 4 index step; indexed but sparse (no repo/tags) → Phase 4 `enrich-paper`;
  already enriched with evals on these benchmarks → leave it, just verify in Phase 6.

Phases 3 and 4 are independent and can run concurrently. Phase 5 (`add-evals`) needs the benchmarks from
Phase 3 to exist first (so the leaderboard + metric are configured), and Phase 6 (`verify-evals`) runs
last, once rows are in place.

## Phase 3 — Create missing benchmarks (one subagent per benchmark)

For each benchmark that is missing, unlinked, or missing its leaderboard metric, launch a subagent that
reads and follows `add-benchmark`. Divide the work one benchmark per subagent so they run in parallel.

Subagent prompt template (launch with `model: "composer-2.5-fast"`, `run_in_background: true`):

```
Read and follow the skill at .agents/skills/add-benchmark/SKILL.md.

Add/repair the benchmark "<benchmark name>" and link it to task "<task-slug>" (task_id <id>).
Source metrics seen in legacy PwC for this benchmark: <metrics list from the miner>.
Candidate source paper (introduced the benchmark): <paper_title> <paper_url>.

Goals: ensure a datasets row exists; resolve and attach the benchmark's *introducing* source paper
(native paperswithcode.co paper URL, indexing/creating it if needed per the skill); ensure the
(task_id, dataset_id) link exists; ensure the leaderboard metric(s) the legacy table uses are linked.
Report the dataset id, slug, source paper URL, and metrics linked.
```

Be careful (the skill stresses this): the benchmark's source paper is the paper that *introduced* the
dataset, not a model paper that merely scores on it. Pass the miner's `paper_title`/`paper_url` only as a
*candidate*; let the subagent verify provenance.

## Phase 4 — Index + enrich the top papers (one subagent per paper)

Papers from the legacy dump may not be in the live DB yet. For each paper on the worklist:

1. **Index it if missing.** For an arXiv paper, the admin endpoint is the simplest path:

   ```bash
   source backend/keys.env
   curl -s -X POST "http://localhost:8000/api/v1/papers/index/$ARXIV_ID" \
     -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" -o /dev/null -w "%{http_code}\n"
   # 200 = indexed, 409 = already present (both fine), 404 = not on arXiv
   ```

   Parse the arXiv id from the legacy `paper_url` (e.g. `https://arxiv.org/abs/2312.00063v1` → `2312.00063`).
   If a top paper has no arXiv id (CVPR/proceedings/blog), it must be created via `add-external-paper`;
   fold that into the subagent prompt so the worker creates the external row before enriching.

2. **Enrich it** with a subagent that reads and follows `enrich-paper`. Launch with
   `model: "composer-2.5-fast"`, `run_in_background: true`:

   ```
   Read and follow the skill at .agents/skills/enrich-paper/SKILL.md.

   Enrich the paper "<paper_title>" (arxiv <arxiv_id> / paperswithcode.co/paper/<id>).
   It is a top paper on the "<task-slug>" task's benchmark "<benchmark>".
   Find its own official GitHub repo + project page (authenticity over recall) and add high-confidence
   task/method tags from the existing taxonomy, MERGING with — never clobbering — existing tags.
   If the paper row does not exist and it has no arXiv id, first create it via add-external-paper.
   Report the paper URL, links saved, and tags added/removed.
   ```

Papers that are already indexed and enriched (from Phase 2) don't need a subagent here — skip them.

## Phase 5 — Import evaluations (one subagent per paper)

Once the benchmarks exist (Phase 3 complete) and papers are indexed (Phase 4), import the leaderboard
rows. One subagent per paper, reading and following `add-evals`. Launch with `model: "composer-2.5-fast"`,
`run_in_background: true`:

```
Read and follow the skill at .agents/skills/add-evals/SKILL.md.

Add evaluation rows for the paper "<paper_title>" (arxiv <arxiv_id> / paperswithcode.co/paper/<id>),
which is a top paper for the "<task-slug>" task. Target benchmarks for this paper (from legacy PwC):
<benchmark names + the metric columns + the model_name(s) and scores the miner found for this paper>.

Follow the skill's rules exactly: only import rows on benchmarks already wired up with the configured
leaderboard metric; attach rows to THIS paper's id (no external/comparator evals); set is_open,
num_parameters, harness per the skill. Use the legacy numbers as a hint of which table to find in the
source, but re-source each score from the paper/README/model card — do not trust legacy values blindly.
Report rows added, benchmarks skipped + why, and the paper URL.
```

`add-evals` is conservative by design: it skips benchmarks that aren't fully configured. That's why Phase
3 runs first. If a subagent reports it skipped a benchmark because the metric wasn't configured, that's a
signal Phase 3 missed something — fix the benchmark, then re-run that paper's eval subagent.

The legacy `metrics` columns are a strong hint, but the leaderboard contract is whatever metric is
actually configured on the live `(task_id, dataset_id)`. Let `add-evals` pick the best eligible row per
benchmark; don't force every legacy column.

## Phase 6 — Verify each benchmark leaderboard (one subagent per benchmark)

After evals are in, audit each benchmark for apples-to-apples comparability. One subagent per benchmark,
reading and following `verify-evals`. Launch with `model: "composer-2.5-fast"`, `run_in_background: true`:

```
Read and follow the skill at .agents/skills/verify-evals/SKILL.md.

Audit the benchmark "<benchmark>" (dataset slug <slug>) on task "<task-slug>" (task_id <id>).
Confirm every evaluation row is apples-to-apples: same metric, same dataset split, same evaluation setup,
and a score faithful to its source paper. Establish the leaderboard contract first (split/metric/setup),
then classify each row (PASS / WRONG_SPLIT / WRONG_SETUP / WRONG_METRIC / WRONG_PAPER / DUPLICATE /
UNVERIFIABLE). Fix or delete per the skill's remediation rules. Report the contract, a row-by-row verdict
table, and the benchmark URL.
```

This is also the path for the "already complete" case: if Phase 2 showed a benchmark already has many
evals, you can skip straight here and just verify what exists rather than re-importing.

## Orchestration tips

- **Batch independent subagents in one turn.** Within a phase, launch all the per-paper or per-benchmark
  subagents together so they run concurrently. Across phases, respect the ordering (benchmarks → evals →
  verify); enrichment (Phase 4) overlaps freely with benchmark creation (Phase 3).
- **Reconcile in the parent.** As background subagents report back, keep your TodoList current and watch
  for cross-cutting issues (a benchmark a subagent couldn't source, a metric mismatch surfaced by
  add-evals, a paper with no arXiv id). Resolve those at the orchestrator level so workers don't duplicate
  writes.
- **Idempotency.** Every sub-skill is written to be safe to re-run. If a subagent fails midway, re-launch
  it for the same unit rather than trying to hand-patch the DB.
- **Stay memory-aware throughout.** Beyond the miner, never bulk-load `papers-with-abstracts.json` or the
  full eval tables. Targeted SQL, the miner, `gh api .../readme`, and per-paper PDFs in `/tmp` are enough.

## Reporting back

End with a concise completion report for the task:

- The task page URL: `https://paperswithcode.co/tasks/<slug>`.
- **Benchmarks**: for each of the (≤5) benchmarks — created / already-existed / repaired, dataset slug,
  source paper URL, metrics linked, and the benchmark URL `https://paperswithcode.co/benchmark/<slug>`.
- **Papers**: which top papers were indexed, which were enriched (repos/tags added), and which were
  already complete.
- **Evaluations**: rows added per paper/benchmark, and benchmarks skipped by `add-evals` with the reason.
- **Verification**: per-benchmark verdict summary (PASS counts and any rows fixed/deleted), and any
  leaderboard left with an open question for the user.
- Anything that needs a human decision (ambiguous benchmark source paper, a legacy benchmark with no clear
  live equivalent, a paper with no resolvable source).

## When NOT to use this skill

- The user wants to add **one** benchmark → `add-benchmark`. One paper's evals → `add-evals`. Enrich one
  paper → `enrich-paper`. Verify one leaderboard → `verify-evals`. This skill is for whole-task buildout.
- The task page itself doesn't exist yet → `add-task` first.
- The user wants evaluation rows from a specific paper or source rather than whole-task buildout →
  `add-evals`.
