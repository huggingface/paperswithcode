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

Read the validated `paper_markdown` or `paper_pdf` in the source manifest.
When a source document supplies `local_path`, read that file and verify its
`sha256` before use. Preflight has already downloaded this exact paper text;
its private bucket URL may return 401 after the download credential is removed.
Use the supplied `url` for citations and source coverage, and the local file for
reading. Never request or recover the removed bucket credential. Do not treat a
401 from re-fetching that URL as missing evidence when the verified local copy
is available.
A cached image caption, SVG title, diagram notice, empty wrapper, or successful
HTTP response alone does not count as reading the paper. The PDF preflight
checks only the first two pages for readable content and artifact URLs; read
the relevant body, experiment tables, and captions yourself before curating.
If no substantive source can be read, report the failure rather than marking
the source inspected or URL extraction complete.

For enrichment, search the existing task taxonomy for the actual contribution,
including when the paper starts with no tasks. Accept an official artifact only
when it belongs to this exact paper. Shared navigation links to sibling products,
lab home pages, and website templates are not paper artifacts; a shared vendor
or domain does not establish ownership. Preserve existing manual links and
report questionable existing links separately.

If context includes `retry_feedback`, address its exact rejection before apply.
Re-read current rows and sources; a prior proposal is not evidence.

Choose the workflow from the context's job kind. For `enrich-paper`, submit
only the `enrich` payload; keep `evaluations`, `evaluation_removals`,
`validation_evidence`, and `benchmark_gaps` as empty arrays. Benchmark discovery
and score/gap submission below belong to `add-evals`, even if the enrichment
paper contains evaluation tables. The scheduled workflow runs that stage
separately. Follow the enrichment instructions below for links and taxonomy.

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

Query every benchmark the paper reports under its exact name and common
variants (for example `ImageNet`, `ImageNet-1K`, `ILSVRC-2012`); the first match
may be a different task, such as an inpainting board named `ImageNet`.
Try exact names and common spelling variants, but reject semantically different
datasets or splits even when their names are similar. The `taxonomy` command
searches only task and method names. Never use an empty taxonomy result to
conclude that a benchmark or leaderboard is missing.

Establish the exact benchmark version, split, task/language coverage, aggregation,
tool setting, and metric definition before selecting the best eligible result.
Never substitute a subset for a complete suite, an overall score for a split,
or instruction-level accuracy for prompt-level accuracy because it is higher.
Skip an unverified protocol match and scores known to include invalid trials;
report the source evidence instead. A familiar baseline used as an experimental
probe is not a model introduced by the paper.

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
Never submit `best_rank`: the server derives ranks from the complete leaderboard.
Do not rewrite existing rows just to rephrase methodology or source URLs; omit
already-correct rows. If an actual factual correction is needed, supply the exact
field diff and primary evidence required by the schema.
The helper will report `no_changes` when nothing needs writing; do not describe
that outcome as an applied mutation.

Whenever `context.source_candidate.model_release` is present, eligibility is
restricted to that exact release, including its canonical name and aliases. This
also applies to retries labeled `hf-daily-cron`; the supplied release determines
scope, not the trigger label.
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

For evidence referring to a supplied source document, copy its `kind` verbatim
into `source_kind`: a GitHub README is `github_readme`, and a project page is
`project_page`. Do not label either as `paper_source` merely because it supports
the paper. Keep the source URL and its kind paired as supplied in the manifest.

Scheduled `add-evals` accepts at most one result for each exact
`(task_id, dataset_id, best_metric)` leaderboard. Select the benchmark-wise best
eligible result from a model introduced by the paper, exactly as required by
`add-evals/SKILL.md`; never submit lower-performing size/configuration variants,
gamma sweeps, or other ablation rows. Apply the same best-eligible-only rule to
`blocked_evaluations` inside benchmark gaps.

Compare each proposed score with this paper's own existing row on that
leaderboard (same `paper_id`), including other sizes of the same family. If
that row is equal or better under the configured metric direction and scale,
omit the new variant and report `already_present`. Rows from other papers never
make a result `already_present`: a paper-native result belongs on its
leaderboard whatever its rank, so never skip it because other models score
higher. If the new result is better, provide primary evidence
and the existing row's full before-state in `evaluation_removals` to consolidate
onto the new best result. Explain the best-result replacement; do not call an
accurately reported older score factually wrong. Never insert a second variant
and expect the server to silently remove the first.

For `add-evals`, when a paper-native result is blocked by missing catalog configuration, include
one structured `benchmark_gaps` entry conforming to
`jobs/schemas/curation_proposal.schema.json`. Group all introduced-model results
blocked by the same configuration in one entry, include primary-paper evidence
and the catalog searches performed, and exclude comparator rows. Always submit
`"benchmark_gaps": []` after a completed search when no gap qualifies. These
observations never create tasks, datasets, metrics, or leaderboards.

Within each gap, every `blocked_evaluations.metrics` key and `best_metric` must
exactly match a name in that gap's `protocol.metrics`. Represent ID/OOD or other
evaluation splits in `split`; do not append split suffixes to metric names unless
those exact names are defined by the protocol. Every protocol metric requires a
nonempty `definition` explaining what it measures, grounded in the source. Copy
the manifest source kind into each gap's evidence too. Check these fields before
apply; schema-shaped objects with empty definitions are rejected.

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
