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
benchmark found across the required sources and checking eligible results against
configured leaderboards and existing rows. Already-satisfied results are omitted.
The helper will report `no_changes` when nothing needs writing; do not describe
that outcome as an applied mutation.

For `hf-trending-cron`, eligibility is restricted to the exact release in
`context.source_candidate.model_release`, including its canonical name and aliases.
An older paper may document the family without reporting results for this release.
Never relabel older or sibling model results as the triggering release, including
after a model-ownership validation error. If the exact release has no eligible
results, submit empty `evaluations` even when the older paper has configured
benchmarks. Apply the same restriction to `benchmark_gaps` and explain older or
sibling results as `not_paper_native` in source coverage.

For every `source_documents` URL in `/tmp/url_candidates.json`, include a separate
`source_coverage` entry with benchmark outcomes. This includes the official GitHub
README even when it contains no eligible scores. Use `status: "unavailable"` and
the actual failure detail for a source you could not inspect; never invent an
inspection. Check completeness before the first apply. `source_coverage` is separate
from `validation_evidence`; empty validation evidence for new inserts or no changes
does not satisfy source coverage. Existing-row edits still require the evidence
specified above.

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
