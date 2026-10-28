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
An external paper's `paper_source` entry may carry the `local_path` of the
page's prepared Markdown copy. First-party release sites often return 403 to
the runner, so read that copy and cite the entry's `url`. Mark the source
covered, not `unavailable`, when the copy was read.
A cached image caption, SVG title, diagram notice, empty wrapper, or successful
HTTP response alone does not count as reading the paper. The PDF preflight
checks only the first two pages for readable content and artifact URLs; read
the relevant body, experiment tables, and captions yourself before curating.
If no substantive source can be read, report the failure rather than marking
the source inspected or URL extraction complete.

An external paper (`paper.source == "external"`) is a release page, model
card, or report with no arXiv text, so its manifest usually has no
`paper_markdown` or `paper_pdf`. Then the `paper_source` document is the paper:
read it in full, together with the `model_card`, `github_readme`, and
`project_page` documents, and curate from them exactly as you would from paper
text. The missing Markdown or PDF is not missing evidence. For `enrich-paper`:

- Tag the tasks and methods the release page states. Examples: a speech-only
  conversation model is speech-to-speech or spoken dialogue, and an action
  model for robots is robotics or robot manipulation. Use only existing
  taxonomy entries and the same high-confidence bar as for paper text.
- Add the official Hugging Face repositories the page links or is itself, to
  `hf_models`, `hf_datasets`, or `hf_spaces`. A `paper.source_url` on
  `huggingface.co/<org>/<repo>` is the release's own model card. Include the
  publisher's official quantized or size variants of this release, never
  community mirrors or fine-tunes.
- Link the publisher as an organization when the page names it.
- Set `urls_extracted=true` after this complete check, including a clean
  no-result.

Report a release page that cannot be read (blocked, empty, or a script shell
with no text) as a source failure; do not tag from the title alone.

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
table, model row, column, and protocol. Put these entries in the proposal's
top-level `score_evidence` array, next to `evaluations`, not inside each
evaluation. Every metric key in every evaluation's `metrics` needs its own
entry, so a row with `MAE` and `Acc-2` needs two. When you drop an evaluation,
drop its entries too. For example:

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

### Benchmark chart images (add-evals only)

Many model cards, READMEs, and release pages publish their scores only as an
embedded benchmark chart. When a source document has no text table or prose
score for a benchmark but embeds a results image (`<img>`, Markdown
`![...](...)`), you may read that image:

1. Resolve the image URL from the source document (absolute, first-party: the
   model repo, the release page's own domain, or its GitHub repo). Download it
   to `/tmp/charts/` with Python (`urllib.request`, browser User-Agent), then
   open the local file with the `view_image` tool.
2. Import only values printed on the chart as numbers (a data label on or
   above the bar, or a value in a chart table). Never estimate a value from bar
   height, axis gridlines, or pixel position; skip unlabeled bars.
3. The bar must unambiguously belong to the introduced model: its label or
   legend entry names the release, and the legend color-to-model mapping is
   clear. Comparator bars stay excluded, as in text tables.
4. Apply every text-table rule: exact benchmark version, split, setting
   (thinking/tools/pass@k), metric definition, and scale. A chart panel title
   such as `SWE-bench Verified` names the benchmark; a footnote may define the
   protocol. If the chart omits protocol details that the leaderboard needs,
   skip and report.
5. Cite the chart. In `score_evidence`, `source_url` is the image URL and
   `table_reference` is `Chart image on <source document URL>: panel
   "<exact panel/benchmark title>", bar "<exact bar label>", printed value
   "<exact text>"`. Use the same citation in any `validation_evidence` entry
   that relies on the chart, and list the source document in `source_coverage`
   with the chart named in the outcome detail.

Prefer a text table whenever both exist; the chart only fills gaps. Report
which values came from charts in the audit.

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

The pinned official model card in `source_candidate.model_card_url` is
first-party evidence for the triggering release. When it reports scores for
that exact release (for example a dated point release such as `…-1017`), those
scores are eligible results for it even when the paper only reports an earlier
release of the family; never mark them `not_paper_native`. Submit them with
the release's canonical name (or a supplied alias) as `model_name`, the pinned
card URL as each `score_evidence.source_url`, and the card table as
`table_reference`. The exact split, version, tool-setting, metric, and scale
rules apply unchanged, and the card's comparator columns stay excluded.

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

Before picking that best result, read every results table, including appendix
and supplementary tables, for larger or better configurations of the introduced
model (for example Large or Huge variants, longer schedules, or higher
resolution) on the same benchmark and protocol. A main-text table that reports
only a Base model is not the paper's best result when an appendix table reports
a better Large model under the same protocol.

Compare each proposed score with this paper's own existing row on that
leaderboard (same `paper_id`), including other sizes of the same family. If
that row is equal or better under the configured metric direction and scale,
omit the new variant and report `already_present` with that leaderboard's
`task_id`, `dataset_id`, `metric`, and the paper's best eligible score as
`value` on the leaderboard scale. Before submitting, check each
`already_present` value against that leaderboard's row in context
`paper.evaluations`. When they differ, reread the source table column and
model row: a mismatch usually means an adjacent column was copied. A rerun on a
paper whose results are all stored is a valid proposal with no evaluations, in
which every benchmark is `already_present`. The server rejects `already_present` unless
this paper already has an equal or better row on that exact leaderboard. Rows
from other papers never make a result `already_present`: a paper-native result
belongs on its leaderboard whatever its rank, so never skip it because other
models score higher. Include `task_id`, `dataset_id`, and `metric` on any other
outcome that names a configured leaderboard, so `not_applicable` skips appear in
the admin report. If the new result is better, provide primary evidence
and the existing row's full before-state in `evaluation_removals` to consolidate
onto the new best result. Explain the best-result replacement; do not call an
accurately reported older score factually wrong. Never insert a second variant
and expect the server to silently remove the first.

Never update or remove an existing row whose `methodology` starts with
`Managed by the Papers with Code <source> live sync.`. A live leaderboard sync
owns it and rewrites it from the official leaderboard every run, and the server
rejects any proposal that changes, consolidates, or removes it. Do not submit a
differently named row for the same model on that leaderboard instead. Drop the
item and report the benchmark as a `not_applicable` outcome with `task_id`,
`dataset_id`, `metric`, and a `detail` saying the row is managed by that live
sync. Other models and other leaderboards follow the normal rules.

Never submit results for an unfinished checkpoint. When the source marks the
evaluated model as still training, under revision, a preview or interim
checkpoint, or an intermediate training step (check page headers and footers,
title notes, and model card status; the Avalon-M1 report stamps every page
"Model still training, under revision"), submit no `evaluations` and no
`benchmark_gaps` for that model. Report each of its benchmarks as
`not_paper_native`, with a `detail` that quotes the source's marking. Results
for a paper's final model stay eligible even if the paper also analyzes
earlier checkpoints.

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

### Organizations

For `enrich-paper`, also tag the organizations behind the paper. Read the
author affiliations, including footnote markers, from the `paper_front_matter`
source document: preflight saves page 1 of the arXiv PDF, with its text and
hyperlinks, at its `local_path` (verify its `sha256`). The Markdown is often an
arXiv HTML copy that starts at the Abstract or keeps only author names, so an
empty Markdown header is not evidence that the paper lists no affiliations. If
the front matter is missing, read the affiliations from the arXiv HTML at
`https://arxiv.org/html/<arxiv_id>` (`ltx_role_affiliation` and `ltx_personname`
elements) or from page 1 of `https://arxiv.org/pdf/<arxiv_id>`. Conclude that
there are no affiliations only after checking one of them. Tag the labs,
companies, and universities that the authors list as their affiliations, at
most 10. Skip departments and sub-groups when the parent organization is what
the catalog lists (for example, FAIR is Meta), funding agencies, compute
sponsors, and organizations named only in acknowledgements.

Also tag the Hugging Face organization that officially hosts this paper's own
release: its weights, Space, dataset, or collection, linked from the paper's
first page (including the front matter's hyperlinks) or from its official
repository README. This covers labs whose affiliation line uses a different name
from their Hub organization; for example, MOSS-Image lists "MOSI Intelligence"
and links `huggingface.co/collections/OpenMOSS-Team/moss-image`, so tag
OpenMOSS (`OpenMOSS-Team`). Do not tag the organization of a model the paper
only uses or compares against, a community re-upload, or a hub link found
anywhere other than the paper and its official repository. The evidence is the
link itself.

The context lists the paper's current `organizations`. Find catalog entries
with the taxonomy search, whose `organizations` results give the ID, name, slug,
and HF handle:

```bash
python jobs/curation_api.py taxonomy "Stanford"
```

Try the short name, the full name, and the HF handle before you decide an
organization is missing. Submit an existing organization by ID. Submit a
missing one by its Hugging Face organization handle, found with
`https://huggingface.co/api/quicksearch?q=<name>&type=org` and confirmed at
`https://huggingface.co/api/organizations/<handle>/overview`. Look-alike
handles are common, so choose the verified one (`isVerified`) or the one with
by far the most followers. Leave out an organization that has no catalog entry
and no Hugging Face organization. Each entry needs `name` as the paper writes it
and `evidence` quoting the affiliation line, or the release link for a hosting
organization. When you submit a hosting organization by `hf_slug`, use its
Hugging Face display name as `name`; the VPS skips a name that does not match
the profile.

```json
"organizations": [
  {"organization_id": 11, "name": "Meta", "evidence": "1 FAIR at Meta"},
  {"hf_slug": "StanfordUniversity", "name": "Stanford University",
   "evidence": "2 Stanford University"},
  {"organization_id": 461, "name": "OpenMOSS",
   "evidence": "Page 1 link https://huggingface.co/collections/OpenMOSS-Team/moss-image"}
]
```

Organization links are only added, never removed, so listing only the new
affiliations is enough. The VPS creates a missing organization from its Hugging
Face profile (name, website, and logo) only when the profile is verified or
established and its name matches. The apply response lists skipped entries
under `organizations.skipped`; mention them in the audit report.

Finish with a concise audit report. The runner reports it to the VPS.

## Benchmark-gap jobs

Kinds `review-benchmark-gaps` and `add-benchmark` have no scoped paper
(`context.paper.id` is null). Ignore the paper-enrichment rules in the runner
prompt and follow only this section. Submit `evaluations`,
`evaluation_removals`, `benchmark_gaps`, and `validation_evidence` as empty
arrays plus exactly one of `review_benchmark_gaps` or `add_benchmark`. Each
apply is one transaction; on a validation error, fix the cited field and apply
once more.

The context can be large. Read `/tmp/context.json` with `python3` or `jq`
instead of printing it whole. Search datasets (configured or not), tasks, and
metrics with:

```bash
python jobs/curation_api.py catalog "ScanObjectNN"
```

### `review-benchmark-gaps`: the daily overseer

`context.review.candidates` lists every eligible gap in today's batch
(reported by at least three distinct papers), strongest evidence first.
Return exactly one decision for every candidate in that list, up to 150; the
server rejects a proposal that leaves any candidate out. Triage from the
summaries in the context; do not research candidates one by one (the
`add-benchmark` job does that).

You are the quality gate, not a rubber stamp: three papers mentioning a name
does not make it a benchmark worth a leaderboard. Every approval queues
catalog writes (at most 40 a day), and a wrong one lands a leaderboard on the
wrong task or metric. Read each candidate's `reported_tasks` and
`reported_metrics` (distinct reporting papers per task and metric),
`reported_splits`, `recommendations`, `evidence_papers`, and catalog matches
before deciding. Decide each one with the whole list in view:

- `merge` duplicates into the candidate to keep, for example `TinyImageNet`
  into `Tiny-ImageNet` (`merge_into_candidate_id`). Never merge distinct
  splits, versions, or subsets.
- `reject` a candidate that is not a reusable public benchmark: a private or
  paper-specific test set, a model or method name, a metric, a training
  corpus, a split or subset label (`Avg. OOD`, `test-dev`, `hard`), a
  benchmark suite the catalog already splits into its members, or a name that
  `catalog_name_matches` already covers completely. Watch for name clashes: a
  match with the same name but a different domain (the graph dataset
  `Chameleon` against a camouflaged-object benchmark `CHAMELEON`) is not
  coverage.
- `defer` when you cannot yet say which benchmark and protocol the papers
  mean: an ambiguous or generic name (`ShapeNet`, `Matterport3D`, and
  `DomainNet` each back several unrelated protocols), papers split between
  unrelated tasks or metrics (ShapeNet reported for reconstruction with
  Chamfer distance by most papers and for generation with FID by one),
  `recommendations` that are mostly not `add_candidate`, or evidence too
  thin or contradictory to decide today.
- `approve` only when you can name the established public benchmark, the task
  most reporting papers evaluate, and the primary metric they share. Each
  approval queues one `add-benchmark` job that does the deep research, so
  approve on reusability, demand, and a consistent protocol, not on source
  details. Approve leaderboard gaps (`task_dataset_association_missing`,
  `metric_configuration_missing`) when the papers report results on that
  exact task and metric.

The reasons are the audit trail, and the server enforces that they are
candidate-specific: it rejects the proposal when two approve, reject, or defer
reasons match after removing each candidate's own names and all digits (a
template such as "`{name}` is a standard benchmark reported by `{n}` papers").
Write each reason from that candidate's evidence: what it measures, the task
and metric its papers share or disagree on, and why that leads to the
decision. Merge reasons may repeat. Decide only candidates from the context.

Do not generate reasons from a fill-in sentence. A script that pastes each
candidate's tasks, metrics, splits, lead paper, or URL into one fixed sentence
is a template, and it fails as soon as two candidates come from the same
papers: sibling datasets reported together (several splits of one gait
benchmark, the multi-label sets of one paper) share every slot except the
name, which the check removes. Write a sibling's reason about what tells it
apart: its domain, size, modality, or protocol, or which sibling it is
evaluated next to and why the two need separate leaderboards. Phrase reasons
differently from one another, as a reviewer would.

Build the proposal with a short Python script that walks `/tmp/context.json`
and holds your hand-written decision and reason for every candidate id, so
none is dropped. `python jobs/curation_api.py apply` runs the server's
template check first and, without using up an apply, lists every group of
candidate ids whose reasons clash; rewrite all of them and apply again.

```json
{
  "evaluations": [], "evaluation_removals": [], "benchmark_gaps": [],
  "validation_evidence": [],
  "review_benchmark_gaps": {
    "summary": "Approved 9, merged 2 aliases, rejected 3 paper-specific sets.",
    "decisions": [
      {"candidate_id": "<uuid>", "decision": "approve",
       "reason": "Public 200-class ImageNet subset; 15 of 16 papers report top-1 Accuracy for image classification."},
      {"candidate_id": "<uuid>", "decision": "defer",
       "reason": "ShapeNet names a shape repository, not one protocol: 6 papers report reconstruction Chamfer distance, 1 generation FID."},
      {"candidate_id": "<uuid>", "decision": "merge",
       "merge_into_candidate_id": "<uuid>",
       "reason": "Same dataset as Tiny-ImageNet under another spelling."}
    ]
  }
}
```

### `add-benchmark`: configure one approved benchmark

`context.benchmark` holds the candidate, the overseer's reason, every
reporting paper's protocol, metrics, sources, catalog near-matches, and
related tasks. `candidate.reported_tasks` and `candidate.reported_metrics`
count distinct reporting papers per proposed task and metric, and
`evidence_consensus` lists the leading ones: the task ids and primary metric
names reported by at least half as many papers as the most common one.
Decide:

- `map_existing` when the dataset already exists (check `catalog` for every
  name and alias first): give `existing_dataset_id` and the task and metrics
  the reporting papers use. Missing task links and metrics are added.
- `create` a new dataset otherwise. `source_paper` must be the paper that
  introduced or formally describes the benchmark, never a later paper that only
  evaluates on it; follow the reporting papers' citations. Prefer
  `existing_paper_id`, then `arxiv_id`, then `external_paper` (a homepage or
  technical report with a credible publication date) for a benchmark with no
  paper. Always put that paper's own canonical URL in `evidence_urls`
  (`https://arxiv.org/abs/<arxiv_id>`, or `external_paper.source_url` exactly);
  the reporting papers' URLs alone do not count, and the server rejects the
  create without it.
- `reject` a candidate that is not a reusable benchmark after all, or `defer`
  when primary sources cannot be read.

Task: start from `evidence_consensus.task_ids` and choose the most specific
existing task, at or below one of them, that matches what the papers measure
(COD10K belongs under camouflaged object detection, not the broad image
segmentation task). When the benchmark measures a distinct setting rather
than the plain task (domain adaptation or generalization for Office-Home,
PACS, or DomainNet; robustness to spurious correlations for Waterbirds),
use or propose that more specific task instead of filling the generic
leaderboard. Propose `new_task` only when no existing task fits; it must name
an existing `parent_task_id` and give a description and comma-separated
keywords. The server rejects a task (or a new task's parent) that is neither a
consensus task nor one of its descendants. When the papers' own proposals are
wrong, for example because the evidence lacks the right task, say why in
`task_choice_reason`; it is recorded with the leaderboard.

Metrics: list one to three, primary first, using what the papers report. The
primary metric must be one of `evidence_consensus.primary_metrics` (matched by
name or full name, ignoring case and punctuation); never substitute a metric
from another protocol (retrieval mAP@200 for a benchmark the papers score by
classification accuracy). The server rejects any other primary metric unless
`metric_choice_reason` explains it, for example that `OA` is the existing
`Overall Accuracy` metric. Reuse an existing metric whenever its definition
matches (search `catalog` first); the server rejects a `new_metric` whose name
matches an existing one. A new metric needs its full name, direction, scale
(`0-100`, `0-1`, or a unit), and a definition.

When the reporting papers split between unrelated protocols and no single
task and metric serve most of them, `defer` with that reason instead of
choosing one.

```json
{
  "evaluations": [], "evaluation_removals": [], "benchmark_gaps": [],
  "validation_evidence": [],
  "add_benchmark": {
    "decision": "create",
    "reason": "ModelNet40 is the standard CAD shape classification benchmark.",
    "evidence_urls": ["https://arxiv.org/abs/1406.5670"],
    "new_dataset": {
      "name": "ModelNet40",
      "full_name": "Princeton ModelNet 40-class subset",
      "description": "12,311 CAD models from 40 categories ...",
      "homepage": "https://modelnet.cs.princeton.edu/"
    },
    "source_paper": {"arxiv_id": "1406.5670"},
    "existing_task_id": "<3D shape classification task id>",
    "metrics": [{"existing_metric_id": "<Overall Accuracy metric id>"}],
    "supports_harness": false
  }
}
```

After a successful create or map, the server requeues add-evals for every
paper that reported the gap; do not add evaluation rows yourself.
