---
name: complete-task-based-on-hf
description: Complete or audit a Papers With Code task using Hugging Face model popularity as the discovery signal. Use this whenever a user asks to scan the most downloaded or trending Hugging Face models for a pipeline/task, resolve their canonical technical reports, and add missing paper-native evaluations to existing Papers With Code benchmarks. Trigger for requests like "complete this task from HF", "check popular Hub models for missing evals", or a Hugging Face models URL with `pipeline_tag` and `sort`; use `add-evals` instead for one already-known model or paper, and `complete-task-v2` for a holistic field survey beyond Hugging Face.
compatibility: Requires the `hf` CLI, repository database access, and the `add-evals` skill. Run repository commands with `uv run --env-file backend/keys.env`.
---

# Complete Task Based on Hugging Face

Use Hugging Face popularity to find important model releases whose paper-native results are missing from existing Papers With Code leaderboards. This is a bounded task-completion workflow, not permission to create every benchmark mentioned by a popular model.

## Core contract

- Query both `trending_score` and `downloads` for the requested Hugging Face `pipeline_tag`; popularity changes, so always fetch live results.
- Default to the top 30 results from each sort unless the user specifies another limit.
- Deduplicate mirrors, quantizations, adapters, checkpoints, and sibling sizes into release families before researching papers.
- Prefer the original official repository and represent the exact popular
  checkpoint discovered on the Hub. Existing rows for a larger or smaller
  sibling do not make that checkpoint `already-covered`.
- Require a canonical release paper or technical report for automatic evaluation import. A model card, blog, or README without a report belongs in a clearly labeled card-only follow-up unless the user explicitly broadens the source policy.
- Import only results for models introduced by the source. Comparison-table baselines are discovery leads, not evaluations to attach to other papers.
- Add results only to datasets, task associations, and exact metric labels already configured in the database. Never create benchmarks or metrics as a side effect.
- Treat the benchmark protocol—not a similar dataset name—as the comparability boundary. Splits, subsets, judge models, ASR normalizers, shot counts, modes, and aggregation must match.
- Keep a decision for every official release family inspected: `imported`, `already-covered`, `defer-no-report`, `defer-wrong-paper`, `defer-missing-benchmark`, `defer-missing-metric`, `defer-not-comparable`, or `defer-no-paper-native-result`.
- If the user asks only to audit or recommend, stop before writes. If they ask to complete, add, import, or populate, continue through verified database writes.

## Required skills

1. Read and follow `hf-cli` for all Hub model and paper discovery.
2. Read and follow `add-evals` before evaluating DB eligibility or writing rows.
3. Use `add-external-paper` only when the user explicitly allows non-paper sources and the qualifying release has no arXiv row.
4. Use `verify-evals` after a broad import when a leaderboard has mixed protocols or suspicious duplicates.

The orchestration here never relaxes a downstream skill's safety or provenance rules.

## Phase 1: Resolve scope

Parse a Hugging Face models URL or user text into:

- `pipeline_tag`, such as `image-text-to-text`;
- optional Papers With Code task name/slug;
- ranking limit, default 30 per sort;
- mode: read-only audit or import.

If the URL contains multiple `?` characters, parse the first query normally and ignore a trailing punctuation-only `?`. Always run both popularity sorts even when the supplied URL shows only one.

Resolve the closest existing PwC task or tasks from the local database. A Hub pipeline can span several PwC tasks, so do not force every result onto one broad task. Leaderboard eligibility is decided from each matched dataset's configured task associations.

## Phase 2: Fetch and deduplicate popular models

Prefer the bundled helper:

```bash
uv run --env-file backend/keys.env python .agents/skills/complete-task-based-on-hf/scripts/discover_hf_models.py \
  --pipeline-tag <pipeline-tag> --limit 30
```

The helper invokes these live CLI queries and returns their union with rank and paper-tag metadata:

```bash
uv run --env-file backend/keys.env hf models list --pipeline-tag <pipeline-tag> --sort trending_score --limit 30 \
  --expand author,downloads,downloadsAllTime,likes,trendingScore,createdAt,lastModified,tags,baseModels,pipeline_tag --format json
uv run --env-file backend/keys.env hf models list --pipeline-tag <pipeline-tag> --sort downloads --limit 30 \
  --expand author,downloads,downloadsAllTime,likes,trendingScore,createdAt,lastModified,tags,baseModels,pipeline_tag --format json
```

Build a family ledger. Preserve both ranks, downloads, likes, official repo id, variant, `arxiv:` tags, base-model relationships, and a decision. Apply these filters carefully:

- Collapse third-party GGUF/ONNX/AWQ/GPTQ/FP8/INT4 mirrors into the original family.
- Do not mistake a popular finetune's base-model paper for the finetune's own report.
- Keep official sibling variants together, but retain the exact evaluated size/mode when scores differ.
- Treat an `arxiv:` tag as a lead, not proof. Cards frequently tag base architectures, tokenizers, benchmark papers, or unrelated dependencies.

Prioritize families appearing in both rankings, then high trending-only releases, then high download-only releases. Inspect at least the top 15 distinct official families unless fewer survive deduplication.

## Phase 3: Prove report ownership

For each prioritized official model:

```bash
uv run --env-file backend/keys.env hf models info <repo_id> --format json
uv run --env-file backend/keys.env hf models card <repo_id> --text
```

Model-card paper metadata is not exhaustive. Even when the card has no usable
`arxiv:` tag—or only tags older architecture papers—search Hugging Face Papers
for the release family before concluding that no report exists:

```bash
uv run --env-file backend/keys.env hf papers search "<release family> technical report" --limit 10
uv run --env-file backend/keys.env hf papers search "<release family>" --limit 10
```

Run this search for every high-priority official family whose exact release is
not already proven by a card link. Search the family name without a size suffix
as well as the exact release name. Do not classify a family as `defer-no-report`
from model-card metadata alone.

For each plausible report:

```bash
uv run --env-file backend/keys.env hf papers info <arxiv_id> --format json
uv run --env-file backend/keys.env hf papers read <arxiv_id>
```

Accept the report only when the paper introduces the evaluated release or explicitly covers that exact family/variant. Check title, authors/organization, paper abstract, linked official models, card wording, and the evaluation table. Reject these common false links:

- a finetune tagged only with its base model's paper;
- a model tagged with a tokenizer, architecture, or benchmark paper;
- a v2/v3 card pointing to a report that only documents v1;
- community artifacts that merely cite the paper;
- a report evaluating a differently sized or differently trained sibling without an exact mapping.

Resolve the report to the local latest paper row by `arxiv_id`. Record papers missing locally as blockers rather than creating an external duplicate.

## Phase 4: Extract only target-model results

Read the report's main model tables and official appendices. Capture:

- exact benchmark and split;
- exact metric label and direction;
- model variant, mode, size, and evaluation setup;
- raw score and any reported aggregation;
- source table/section;
- official HF repo and raw parameter total when certain.

Exclude comparator columns by default. When the report gives per-language, per-category, or per-split components but the existing leaderboard expects an aggregate, compute one only when the source or established leaderboard convention defines that aggregation. Document the formula and unrounded value.

## Phase 5: Match existing leaderboards

Before any write, inventory candidate datasets and every configured `(task_id, dataset_id, metric)` pair. Follow `add-evals` exactly.

For each source result:

1. Match the exact benchmark and split.
2. Confirm a task association exists.
3. Confirm the source metric is configured for that exact leaderboard.
4. Compare protocol details with existing rows and benchmark metadata.
5. Check whether the source paper/model already has an equivalent row.

Skip lookalikes. Examples include FLEURS-61 versus FLEURS-Multilingual-102, generic DocVQA versus a named test split, or a Chinese result labeled WER when the leaderboard requires CER without a source-supported equivalence.

## Phase 6: Import safely

If writes are authorized, process one source paper at a time through `add-evals`.
This workflow narrows that skill's normal family-wide selection rule to the
exact official checkpoints found in the popularity slice: choose the
benchmark-wise best eligible mode/configuration for each discovered checkpoint
size. Do not add every sibling size merely because the report contains it.

Then:

- use the introducing paper's `paper_id`;
- use the benchmark-wise best eligible mode for each exact popular checkpoint;
- attach every comparable metric configured on that leaderboard;
- set `best_metric` to the ranking metric;
- set `is_open`, `hf_model_url`, parameter count, source URL, and traceable methodology;
- mirror the result across each genuinely configured PwC task association only when the same evaluation belongs on each task view;
- append the exact official model URL to the paper's HF artifacts;
- add model-family lineage with `pwc paper lineage add` when clearly warranted.

Keep the write idempotent by checking the complete uniqueness key before inserting.

## Phase 7: Verify

After imports:

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

Also run targeted checks that:

- every new metric key is configured for its exact leaderboard;
- no duplicate uniqueness keys exist;
- source URLs resolve to the owning paper and are not marked external incorrectly;
- HF links point to official non-quantized repositories;
- ranks were recalculated;
- deferred ambiguous rows were not accidentally imported.

Global validator failures from unrelated legacy rows do not invalidate a clean targeted check, but report them separately.

## Report format

Lead with the result and include:

- pipeline tag, timestamp, and top-N used for both sorts;
- number of exact repos and deduplicated official families reviewed;
- imported papers/models and row counts;
- benchmarks, tasks, metrics, values, and source tables;
- already-covered families;
- deferred families with concrete reasons;
- parameter-count and open-weight evidence;
- validation outcome and any unrelated pre-existing issues;
- Papers With Code links for every source paper.

Do not claim the whole research field or PwC task is complete. State that it is complete for the bounded Hugging Face popularity slice inspected.
