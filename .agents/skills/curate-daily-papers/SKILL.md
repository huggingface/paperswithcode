---
name: curate-daily-papers
description: >-
  Curate Papers With Code papers from a Hugging Face daily-paper import: enrich
  official URLs and existing task/method tags, remove false-positive tags, add
  paper-native evaluation results only for existing benchmark/task/metric
  leaderboards, verify ranks and duplicates, and report every change. Use this
  whenever the user asks to curate yesterday's papers, run daily paper curation,
  enrich a daily import, process a specific Hugging Face paper date, or repeat
  the recent weekly paper-enrichment workflow for a day or date range.
---

# Curate Daily Papers

Curate the exact Hugging Face daily-paper cohort, not all papers whose arXiv
publication date happens to fall on the requested day. This distinction keeps
conference bulk imports and unrelated backfills out of scope.

Run repository commands from the repository root:

```bash
uv run --env-file backend/keys.env ...
```

## Inputs and defaults

- Accept a date, `yesterday`, or a closed date range.
- Interpret dates in UTC. If no date is supplied, use yesterday in UTC.
- A date range means the union of each day's Hugging Face daily list,
  de-duplicated by arXiv ID.
- If the user says `dry run`, perform every read and proposal step but make no
  database writes.

Before acting, read and follow these repository skills:

- `hf-cli` for the canonical daily list and paper Markdown.
- `pwc-cli` for paper inspection and supported paper updates.
- `enrich-paper` for official URLs and conservative taxonomy tagging.
- `add-evals` for evaluation eligibility, normalization, and writes.
- `verify-evals` for the final leaderboard audit.

User instructions override defaults. In particular, preserve these standing
curation constraints unless the user explicitly changes them:

- Prefer no eval over an external/comparator eval.
- Add evals only to benchmark + task + metric triples already configured in the
  database.
- Never create duplicate evals.

## 1. Resolve the exact cohort

For each date, run:

```bash
uv run --env-file backend/keys.env \
  hf papers list --date YYYY-MM-DD --limit 100 --format quiet
```

Use the returned IDs as the sole paper scope. Do not substitute a database
`date_published` filter. De-duplicate IDs while preserving date order and verify
that every ID resolves in the local database. Report missing imports rather than
silently indexing them unless the user also asked for ingestion.

For a quick machine-readable inventory, run:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/curate-daily-papers/scripts/inspect_cohort.py \
  --date YYYY-MM-DD
```

Repeat `--date` for a range. The helper is read-only.

## 2. Triage all papers cheaply

Read every title and abstract. Use them to identify:

- clearly relevant existing task and method tags;
- existing tags that describe cited baselines, model families, or incidental
  domains rather than the paper's contribution;
- papers likely to contain eligible result tables.

Do not read every paper in full. For eval candidates, use `hf papers read ID`
and inspect the evaluation/experiments sections and relevant tables. Escalate to
the PDF only when Markdown loses table structure or essential footnotes.

Keep tags sparse and contribution-focused. A useful default is 1–4 tasks and
1–6 methods, but evidence matters more than quotas. Use only taxonomy rows that
already exist. Generic mentions such as LLM, VLM, transformer, RL, QA, NeRF, or
Gaussian Splatting do not by themselves establish a task or method tag.

Preserve existing links unless they are clear false positives. Replace task and
method lists through `pwc paper update`; merge deliberately so an update does
not accidentally erase a valid manual tag. Record every add and removal.

## 3. Apply the eval eligibility gates

An evaluation is eligible only when all gates pass:

1. The result is for a model introduced by the source paper. Exclude comparator,
   baseline, and cited-model rows even if the paper reproduces them.
2. The benchmark already exists and is already associated with the target task.
3. The exact metric already exists on that benchmark/task leaderboard.
4. No evaluation already exists for the same paper and leaderboard. Treat
   renamed variants or duplicate table rows as duplicates; keep the paper's
   best eligible introduced-model result per leaderboard.
5. The value uses the leaderboard's expected scale and direction. Check percent
   versus fraction scales and benchmark-specific conventions such as OCRBench.
6. The source is the paper itself. For arXiv papers, use exactly
   `https://arxiv.org/abs/<arxiv_id>` and ensure the resulting row is not marked
   external.
7. The evaluated model is finished. Skip results from a model that the source
   marks as still training, under revision, or a preview or interim
   checkpoint, as `add-evals` describes.

Set a Hugging Face model URL only when the exact evaluated model has an official
model repository. Set open/closed status from evidence, not from the presence of
a paper repository.

When a potentially useful result fails a gate, skip it and include the specific
reason in the report. Never create a missing benchmark, task association, or
metric as part of this workflow.

## 4. Preflight and write safely

Before each eval write, query existing evaluations for the paper and the exact
task/dataset/metric triple. Check both model name and leaderboard identity.

Batch proposed tag and eval changes in a reviewable temporary script or explicit
CLI commands. Keep the scope limited to the cohort IDs. Use `apply_patch` for
temporary files and remove them after successful verification.

In dry-run mode, print the exact proposed changes and stop here.

## 5. Verify every write

After writes:

- reread each changed paper;
- verify task/method additions and removals;
- query every new eval ID and confirm:
  - paper ID and model are correct;
  - source URL is the paper's own arXiv URL;
  - `is_external` is false;
  - benchmark/task/metric match the configured leaderboard;
  - rank is non-null;
- query duplicate groups by paper + leaderboard and ensure none were introduced;
- run the repository metric/evaluation validator described by `add-evals`;
- use `verify-evals` for any leaderboard where comparability is uncertain.

If verification finds an error, correct or delete that scoped write before
reporting completion.

## Report

Lead with the outcome and include:

- requested dates and exact cohort size;
- number of papers whose task/method tags changed;
- per-paper tag additions and removals;
- each added eval: paper URL, model, task, benchmark, metric, value, rank;
- skipped eval candidates and concise reasons;
- confirmation that all new evals are paper-native, use existing leaderboards,
  have ranks, and introduce no duplicates;
- validation failures or unresolved uncertainties.

If nothing changed, say so explicitly and still report the cohort size and the
checks performed.
