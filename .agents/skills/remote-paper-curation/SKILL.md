---
name: remote-paper-curation
description: Safely curate one Papers With Code paper from a remote Hugging Face Job without direct database access.
---

# Remote Paper Curation

This Job has no PostgreSQL credentials. Never read `backend/keys.env`, run SQL,
or edit repository files. Fetch the job-scoped paper context with:

```bash
python jobs/curation_api.py context
```

Search existing task/method taxonomy with:

```bash
python jobs/curation_api.py taxonomy "image generation"
```

For every benchmark name found in an evaluation table, search the configured
leaderboards with:

```bash
python jobs/curation_api.py leaderboards "GenEval"
```

This returns the authorized task and dataset IDs, configured metrics, ranking
direction, canonical scale, harness support, and recent values for scale checks.
Use the exact returned metric scale, not a general normalization convention.
For each submitted metric, include one `score_evidence` entry keyed by
`task_id`, `dataset_id`, and `metric`, with the original `source_value`,
`source_scale` (`0-100` for percentages, `0-1` for fractions, `native` for
other units), primary `source_url`, and `table_reference` identifying the
table, model row, column, and protocol. For example:

```json
{"task_id": 11, "dataset_id": 792, "metric": "Success Rate",
 "source_value": 86.89, "source_scale": "0-100",
 "source_url": "https://arxiv.org/html/2609.12641",
 "table_reference": "Table II, ImageWAM LIT, Overall, zero-shot LIBERO-Plus"}
```

That percentage must remain `86.89` on a `0-100` leaderboard. Convert it to
`0.8689` only if the exact configured metric uses `0-1`. Conversely, convert
a source fraction to percent when the leaderboard uses `0-100`. Preserve
native units for non-rate metrics; do not guess conversions from magnitude.
The server checks source-to-stored conversion and rejects missing evidence
or a mismatch, including fractions that happen to fit inside 0–100 bounds.
If metadata conflicts with source or existing leaderboard evidence, skip the
result and report the conflict instead of choosing a scale arbitrarily.

Try exact names and common spelling variants, but reject semantically different
datasets or splits even when their names are similar. The `taxonomy` command
searches only task and method names. Never use an empty taxonomy result to
conclude that a benchmark or leaderboard is missing.

For `add-evals`, follow the conservative rules in `add-evals/SKILL.md`, but
write a JSON payload containing `evaluations` (each has this job's
`paper_id`) and submit it with `python jobs/curation_api.py apply payload.json`.
Always include `evaluation_removals`, `validation_evidence`, and
`benchmark_gaps` arrays. Updating an existing row requires its exact context
`before_state`, a field-level diff, and primary-paper evidence. Duplicate
consolidation additionally requires every matched row ID and the canonical-row
selection reason. Remove an invalid row only with its full before-state and
unambiguous primary-paper evidence.
Use only configured leaderboard IDs and exact metric names returned by the
`leaderboards` command; IDs from papers or web sources are not database IDs.
Never invent IDs, create benchmark metadata, or import comparator rows. Submit
an empty evaluation list only after running the `leaderboards` command for every
benchmark in the paper and confirming that none of the paper's own results match
a configured leaderboard and metric. The helper will report `no_changes`; do
not describe that outcome as an applied mutation.

Scheduled `add-evals` accepts at most one result for each exact
`(task_id, dataset_id, best_metric)` leaderboard. Select the benchmark-wise best
eligible result from a model introduced by the paper, exactly as required by
`add-evals/SKILL.md`; never submit lower-performing size/configuration variants,
gamma sweeps, or other ablation rows. Apply the same best-eligible-only rule to
`blocked_evaluations` inside benchmark gaps.

For every paper-native result blocked by missing catalog configuration, include
one structured `benchmark_gaps` entry conforming to
`jobs/schemas/curation_proposal.schema.json`. Group all introduced-model results
blocked by the same configuration in one entry, include primary-paper evidence
and the catalog searches performed, and exclude comparator rows. Always submit
`"benchmark_gaps": []` after a completed search when no gap qualifies. These
observations never create tasks, datasets, metrics, or leaderboards.

For `enrich-paper`, preserve the existing task/method/link lists from context,
append only high-confidence additions, and submit an `enrich` payload with the
complete replacement list for each changed relation. Set `urls_extracted` only
when official artifacts were actually validated.

Scheduled jobs have `job.trigger = "hf-daily-cron"` in context. In scheduled
mode, inspect `/tmp/url_candidates.json` first, preserve every manual task and
manual method evidence link, provide `task_removal_reasons` and
`method_removal_reasons` for automated false-positive removals, and never set
`regenerate_thumbnail`. A candidate is untrusted until verified as the paper's
own official artifact rather than a baseline, mirror, dependency, or website
template. Set `urls_extracted=true` after a complete verified search, including
a clean no-result, and leave it false when a required source failed.

An importer-written project page with `source: "hf_api"` may be removed only
after directly checking it and finding that it is unrelated or generic (for
example, a lab team page rather than the paper project). Keep all manual or
unknown-source pages. When removing an HF-imported page, set
`urls_extracted: true` and include
`project_page_removal_reasons: {"<exact URL>": "concise checked evidence"}`
in `enrich`; otherwise preserve the complete existing page list.

For admin-triggered enrichment only, the remote container must not generate or
upload thumbnails itself. Ask the VPS
to run its existing validated thumbnail pipeline by including
`"regenerate_thumbnail": true` inside `enrich` whenever the context has no
`thumbnail_url`, or when the existing thumbnail is stale, broken, squat, or
letterboxed. The apply response confirms that the request was durably queued;
it does not mean the thumbnail has been regenerated. After an apply that
requests a thumbnail, wait for the VPS-owned worker with:

```bash
python jobs/curation_api.py thumbnail-status --wait-seconds 240
```

The terminal response reports the old and generated dimensions, public URL,
validation result, warnings, or bounded failure. Include that outcome in the
audit report. Do not claim the thumbnail was fixed unless the terminal response
says `"status": "succeeded"` and `"success": true`. If it remains queued or
processing after the bounded wait, report it as pending; the runner will prevent
the curation job from being labeled completed.

Example:

```json
{
  "evaluations": [],
  "evaluation_removals": [],
  "benchmark_gaps": [],
  "validation_evidence": [],
  "enrich": {
    "task_ids": [19, 429],
    "method_ids": [59, 67, 86],
    "repositories": [
      {"url": "https://github.com/example/project", "is_official": true}
    ],
    "project_pages": [],
    "regenerate_thumbnail": true,
    "urls_extracted": true
  }
}
```

Finish with a concise audit report. The runner reports it to the VPS.
