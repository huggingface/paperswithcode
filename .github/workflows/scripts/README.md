# PapersWithCode Cron Jobs

Production cron scheduling is driven by host systemd timers generated from
`deploy/cron_schedules.py` into `deploy/systemd/cron/`; each timer invokes the
allowlisted `pwc-cron` launcher through the bounded `pwc-cron-throttled`
wrapper. The workflows under `.github/workflows/cron-*.yml` are
`workflow_dispatch`-only manual-recovery paths that SSH into the VPS and run
the same `pwc-cron` jobs. The schedule columns below describe the timer
cadence, which preserves the former GitHub Actions minute offsets.

## Production Jobs and Pending Activations

| Workflow | Schedule (UTC) | VPS entrypoint | Python job |
| --- | --- | --- | --- |
| local `pwc-curation-thumbnails.timer` | Every minute | `pwc-cron process_curation_thumbnails` | `.github/workflows/scripts/hourly/process_curation_thumbnails.py` |
| `cron-update-hot-github-trending.yml` | Every 15 minutes | `.github/workflows/scripts/run_hot_github_trending.sh` | `.github/workflows/scripts/hourly/update_hot_github_trending.py` |
| `cron-update-github-stars.yml` | `0 * * * *` | `.github/workflows/scripts/run_github_stars.sh` | `.github/workflows/scripts/hourly/update_github_stars.py` |
| `cron-calculate-trending-scores.yml` | `15 * * * *` | `.github/workflows/scripts/run_trending_scores.sh` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` |
| `cron-update-citations.yml` | `30 * * * *` | `.github/workflows/scripts/run_citations_hourly.sh` | `.github/workflows/scripts/hourly/update_citations.py` |
| `cron-extract-urls.yml` | `45 * * * *` | `.github/workflows/scripts/run_extract_urls_hourly.sh` | `.github/workflows/scripts/hourly/extract_urls.py` |
| `cron-import-hf-daily-papers.yml` | `0 * * * *` | `pwc-cron import_hf_daily_papers` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` |
| `cron-enqueue-hf-daily-paper-curation.yml` | `27 * * * *` | `pwc-cron enqueue_hf_daily_paper_curation` | `backend/scripts/enqueue_hf_daily_paper_curation.py` |
| `cron-enqueue-hf-trending-model-curation.yml` | `42 * * * *` | `pwc-cron enqueue_hf_trending_model_curation` | `backend/scripts/enqueue_hf_trending_model_curation.py` |
| local `pwc-cron-enqueue-benchmark-gap-review.timer` | `35 6 * * *` | `pwc-cron enqueue_benchmark_gap_review` | `backend/scripts/enqueue_benchmark_gap_review.py` |
| local `pwc-cron-scan-model-releases.timer` | `48 1/3 * * *` | `pwc-cron scan_model_releases` | `backend/scripts/scan_model_releases.py` |
| local `pwc-cron-discover-x-threads.timer` | `22 8,20 * * *` | `pwc-cron discover_x_threads` | `backend/scripts/discover_x_threads.py` |
| local `pwc-cron-post-trending-paper-to-x.timer` | `13 */4 * * *` | `pwc-cron post_trending_paper_to_x` | `backend/scripts/post_trending_paper_to_x.py` |
| local `pwc-cron-warm-paper-suggested-questions.timer` | `33 * * * *` | `pwc-cron warm_paper_suggested_questions` | `backend/scripts/warm_paper_suggested_questions.py` |
| local `pwc-cron-post-x-insight.timer` | `43 9,17 * * *` | `pwc-cron post_x_insight` | `backend/scripts/post_x_insight.py` |
| `cron-sync-3d-arena.yml` | `5 * * * *` | `pwc-cron sync_3d_arena` | `.github/workflows/scripts/hourly/sync_3d_arena.py` |
| `cron-sync-tabarena.yml` | `55 * * * *` | `pwc-cron sync_tabarena` | `.github/workflows/scripts/hourly/sync_tabarena.py` |
| `cron-sync-open-asr.yml` | `15 * * * *` | `pwc-cron sync_open_asr` | `.github/workflows/scripts/hourly/sync_open_asr.py` |
| `cron-sync-open-tts.yml` | `18 * * * *` | `pwc-cron sync_open_tts` | `.github/workflows/scripts/hourly/sync_open_tts.py` (English and all-language-average views) |
| `cron-sync-mmteb-overall.yml` | `7 * * * *` | `pwc-cron sync_mmteb_overall` | `.github/workflows/scripts/hourly/sync_mmteb.py overall` |
| `cron-sync-mmteb-retrieval.yml` | `22 * * * *` | `pwc-cron sync_mmteb_retrieval` | `.github/workflows/scripts/hourly/sync_mmteb.py retrieval` |
| `cron-sync-mmteb-reranking.yml` | `37 * * * *` | `pwc-cron sync_mmteb_reranking` | `.github/workflows/scripts/hourly/sync_mmteb.py reranking` |
| `cron-sync-mmeb-v2.yml` | `12 * * * *` | `pwc-cron sync_mmeb_v2` | `.github/workflows/scripts/hourly/sync_mmeb.py v2` |
| `cron-sync-mmeb-v3.yml` | `42 * * * *` | `pwc-cron sync_mmeb_v3` | `.github/workflows/scripts/hourly/sync_mmeb.py v3` |
| `cron-sync-deepswe.yml` | `25 * * * *` | `pwc-cron sync_deepswe` | `.github/workflows/scripts/hourly/sync_deepswe.py` |
| `cron-sync-artificial-analysis.yml` | `35 */2 * * *` | `pwc-cron sync_artificial_analysis` | `.github/workflows/scripts/hourly/sync_artificial_analysis.py` |
| `cron-sync-programbench.yml` | `40 * * * *` | `pwc-cron sync_programbench` | `.github/workflows/scripts/hourly/sync_programbench.py` |
| `cron-sync-frontiercode.yml` | `45 * * * *` | `pwc-cron sync_frontiercode` | `.github/workflows/scripts/hourly/sync_frontiercode.py` |
| `cron-sync-parsebench.yml` | `20 * * * *` | `pwc-cron sync_parsebench` | `.github/workflows/scripts/hourly/sync_parsebench.py` |
| `cron-sync-extractbench.yml` | `32 * * * *` | `pwc-cron sync_extractbench` | `.github/workflows/scripts/hourly/sync_extractbench.py` |
| `cron-sync-physics-iq-verified.yml` | `28 * * * *` | `pwc-cron sync_physics_iq_verified` | `.github/workflows/scripts/hourly/sync_physics_iq_verified.py` |
| `cron-sync-vals-finance-agent.yml` | `47 * * * *` | `pwc-cron sync_vals_finance_agent` | `.github/workflows/scripts/hourly/sync_vals_finance_agent.py` |
| `cron-sync-coarena.yml` | `50 * * * *` | `pwc-cron sync_coarena` | `.github/workflows/scripts/hourly/sync_coarena.py` |
| `cron-sync-arc-prize.yml` | `10 * * * *` | `pwc-cron sync_arc_prize` | `.github/workflows/scripts/hourly/sync_arc_prize.py` |
| `cron-sync-hf-organizations.yml` | `20 2 * * *` | `pwc-cron sync_hf_organizations` | `.github/workflows/scripts/daily/sync_hf_organizations.py` |
| `cron-sync-hf-author-profiles.yml` | `50 2 * * *` | `pwc-cron sync_hf_author_profiles` | `.github/workflows/scripts/daily/sync_hf_author_profiles.py` |
| `cron-calculate-organization-trending-scores.yml` | `40 3 * * *` | `pwc-cron calculate_organization_trending_scores` | `.github/workflows/scripts/daily/calculate_organization_trending_scores.py` |
| `cron-refresh-paper-embeddings.yml` | `15 * * * *` | `.github/workflows/scripts/run_refresh_paper_embeddings.sh` | `.github/workflows/scripts/hourly/refresh_paper_embeddings.py` |
| `cron-update-hf-artifacts.yml` | `30 * * * *` | `pwc-cron update_hf_artifacts` | `.github/workflows/scripts/hourly/update_hf_artifacts.py` |
| `cron-backfill-method-keywords.yml` | `10 1 * * *` | `pwc-cron backfill_method_keywords --resume --limit 250000 --max-runtime-seconds 3300` | `.github/workflows/scripts/backfill/backfill_method_keywords.py` |
| `cron-backfill-method-references.yml` | `15 * * * *` | `pwc-cron backfill_method_references --provider openalex --resume --retry-failures --limit 10000 --max-runtime-seconds 19800` | `.github/workflows/scripts/backfill/backfill_method_references.py` |
| `cron-link-methods-by-references.yml` | `0 4 * * 0` | `.github/workflows/scripts/run_link_methods_by_references_weekly.sh` | `.github/workflows/scripts/weekly/link_methods_by_references.py` |
| `cron-link-papers-by-task-keywords.yml` | `0 5 * * 0` | `.github/workflows/scripts/run_link_papers_by_task_keywords_weekly.sh` | `.github/workflows/scripts/weekly/link_papers_by_task_keywords.py` |

The `test-database.yml` workflow is unrelated to cron scheduling.

Historical method work is scheduled in bounded, resumable, release-pinned runs.
The commands below remain available for estimates and targeted maintenance:

```bash
# Non-mutating capacity and match estimates first.
sudo pwc-cron backfill_method_keywords --dry-run --limit 5000
sudo pwc-cron backfill_method_references --method-slug clip \
  --month-from 2021-03-01 --month-to 2021-03-01 \
  --provider openalex --dry-run --limit 1000

# Authorized resumable writes.
sudo pwc-cron backfill_method_keywords --resume --limit 5000
sudo pwc-cron backfill_method_references --method-slug clip \
  --provider openalex --resume --limit 1000
```

The checked-in schedule uses OpenAlex, batching exact arXiv landing-page
lookups and using `PWC_OPENALEX_API_KEY` when configured. The Semantic Scholar
route remains available for manual historical scans, fails closed unless
`PWC_SEMANTIC_SCHOLAR_API_KEY_2` is present and valid, and never falls back to
the primary key used by hourly citation updates and the weekly incremental
linker.
After the first authorized bulk load, run `ANALYZE` only on
`paper_method_evidence`, `paper_method_exclusions`,
`method_reference_backfill_months`, and `method_keyword_backfill_runs`; do not
use `VACUUM FULL`.

## Directory Layout

```text
.github/workflows/scripts/
├── daily/
│   ├── import_hf_daily_papers.py
│   ├── sync_hf_organizations.py
│   └── calculate_organization_trending_scores.py
├── hourly/
│   ├── calculate_trending_scores.py
│   ├── extract_urls.py
│   ├── process_curation_thumbnails.py
│   ├── refresh_paper_embeddings.py
│   ├── update_citations.py
│   ├── update_hot_github_trending.py
│   └── update_github_stars.py
├── backfill/
│   ├── backfill_hf_papers.py
│   ├── backfill_method_keywords.py
│   └── backfill_method_references.py
├── weekly/
│   ├── link_methods_by_references.py
│   └── link_papers_by_task_keywords.py
├── maintenance/
│   ├── cleanup_invalid_repositories.py
│   └── run_cleanup_invalid_repositories.sh
├── utils/
│   ├── cron_helpers.py
│   └── hf_paper_importer.py
├── manage_cron.py
└── run_*.sh
```

Generated logs are written to `.github/workflows/scripts/logs/`. Backfill checkpoint state is runtime
data and is intentionally ignored by git.

## Job Summary

`update_hot_github_trending.py` is designed to own official repositories for
latest papers aged 0–30 days. Once separately activated in production, every
15 minutes it snapshots up to 500 normalized repository groups, calculates
repository EMA only for touched rows, then writes composite scores only for
their linked latest papers using full-corpus normalization.

`update_github_stars.py` owns the non-overlapping hourly fresh (31–180 days,
2,500 calls) and weekly (>180 days, 1,000 calls) queues.
The hot/fresh boundary is a fixed 30 days shared by both adapters and CRON
health; only cadence, caps, delays, and credentials are configurable.

`calculate_trending_scores.py` computes EMA-smoothed trending scores from star
history and stores them on repositories for the trending API/view pipeline.

`update_citations.py` pulls citation counts from Semantic Scholar for ArXiv
papers. Runs are bounded so hourly Actions do not pile up under API throttling.

`discover_x_threads.py` finds X posts in which authors introduce recent
papers and links them to the paper page's "X threads" card. Twice a day it
takes up to 40 arXiv papers from the last 10 days that are trending or featured
on Hugging Face daily papers and have no X threads, and runs one X API v2
recent search per paper over links to the paper (the arXiv ID in any URL,
project page, official repositories), its short method name, and its title.
Only original posts from the paper's own authors (display name, or first and
last name in the handle) or from a business-verified account of one of the
paper's linked organizations are kept; outside accounts never are (at most two
per paper, most liked first). Each paper is searched at most
three times, at least 20 hours apart, tracked in `paper_x_thread_scans`. The
job needs `X_API_BEARER_TOKEN` in `production-cron.env` and exits 0 without
it. It is report-only, storing matches on the scan row, unless
`PWC_X_THREAD_DISCOVERY_APPLY=true`, which links matches through the audited
`x_threads` curation section as actor `x-thread-discovery`. Before linking,
each match is reviewed by gpt-5.6-sol (`PWC_OPENAI_API_KEY`, from
`production.env`): it rejects posts about a sibling project, multi-paper
acceptance lists, and congratulation replies, and the verdict and reason are
stored with the candidate. Without the key the job links nothing. Review stored
matches, or run it by hand, with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.discover_x_threads --show-candidates
uv run --env-file backend/keys.env python -m backend.scripts.discover_x_threads --max-papers 5
```

To backfill older papers, `--backfill-days N` takes trending or HF-featured
arXiv papers from the last N days that have no X threads and no scan row,
newest first, and scans each once with full-archive search (included in X's
pay-per-use plan), limited to one week before to two months after
publication. X allows 300 archive searches per 15 minutes, so run batches of
at most 200 papers at least 15 minutes apart:

```bash
sudo pwc-cron discover_x_threads --backfill-days 180 --max-papers 200
```

`--review-linked-since YYYY-MM-DD` re-reviews threads the job linked since that
date (hand-curated threads are never touched) and, in apply mode, unlinks the
ones the reviewer rejects:

```bash
sudo pwc-cron discover_x_threads --review-linked-since 2026-10-12
```

`enqueue_benchmark_gap_review.py` turns benchmark gaps that scheduled add-evals
agents report into configured leaderboards. Once per UTC day it queues one
`review-benchmark-gaps` overseer job that sees every candidate reported by at
least three distinct papers (high or medium confidence, up to 150 per run) and
approves, merges, rejects, or defers each. Each approved candidate gets one
`add-benchmark` job, at most 20 per UTC day, that finds the introducing paper,
the most specific task, and one to three metrics; the backend validates and
writes the rows, then requeues add-evals for the papers that reported the gap.
Rejected candidates return for review once their paper count doubles; deferred
ones after 14 days. Both kinds share the scheduler pause and run at most two at
a time. Inspect or dry-run it with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.enqueue_benchmark_gap_review --status
```

`warm_paper_suggested_questions.py` pre-generates the three paper-page
suggested questions (gpt-5.6-luna, stored in `paper_suggested_questions`) for
the papers visitors see first: the first three pages of the home feed's
default view (trending, past week) and the first page of every task and method
page (trending, busiest pages first). Papers that already have questions are
skipped and `--limit` (default 1500) bounds generations per run, so the hourly
run only fills newcomers once the backlog is done. Count the work with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.warm_paper_suggested_questions --dry-run
```

`post_trending_paper_to_x.py` posts one trending paper to the Papers with
Code X account (@paperswithcodee) every four hours. It takes the top
`trending_score` arXiv paper from the last 14 days that has a TL;DR and was
never posted, renders the first page of its PDF as an image, and posts the
title, a blank line, and the Luna TL;DR with that image, then replies with the
paper page link. `paper_x_posts` records each posted paper so none is posted
twice. It needs the posting account's OAuth 1.0a keys in `production-cron.env`
(`X_POST_CONSUMER_KEY`, `X_POST_CONSUMER_SECRET`, `X_POST_ACCESS_TOKEN`,
`X_POST_ACCESS_TOKEN_SECRET`; the X app needs Read and Write permission) and
only previews the post without them. Posts are capped at
`PWC_X_POST_MAX_CHARS` (default 280; raise it when the account has X Premium
long posts), dropping trailing TL;DR sentences to fit. Preview the next post
with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.post_trending_paper_to_x --dry-run --save-image /tmp/page.png
```

`post_x_insight.py` posts one insight to the same X account twice a day.
The morning run (09:43 UTC; until 15:00 if throttled) leads with the top
trending papers of the previous month (posted on the 1st, caught up through the
3rd) and week (Monday, caught up through Wednesday), then a new SOTA: a paper published in the last 45
days whose result, added in the last 3 days, took first place on a leaderboard
with at least 5 entries and beats the previous best from another paper (at
most one SOTA post per 20 hours). The 17:43 UTC run posts the fastest-growing
benchmark (site-wide reporting rate, 90 vs. 180 days), method, or task (share
of new papers, 30 vs. 180 days), whichever kind was posted least recently;
the same benchmark, method, or task returns after 30 days at the earliest.
Each post has a chart card and a link reply. Luna (`PWC_OPENAI_API_KEY`)
rewrites the template text, and the rewrite is kept only if it keeps every
number and adds none beyond the facts. `x_insight_posts` records each post.
Preview one kind with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.post_x_insight --dry-run --kind new_sota --save-image /tmp/card.png
```

`scan_model_releases.py` is a read-only radar for model releases that neither
the daily-paper import (arXiv only) nor the trending-model curation (Hub
weights only) can see, such as API-only or blog-first launches. Every three
hours it reads the official news feeds of OpenAI and Google DeepMind (RSS) and
Anthropic, Mistral AI, and DeepSeek (sitemaps plus the newest article pages),
keeps posts whose headline announces a versioned model name, and adds recent
Artificial Analysis leaderboard models that are missing from the reviewed
`MODEL_PAPER_IDENTITIES` map. Each release from the last 14 days is matched
against `papers.source_url`, paper titles, `model_releases`, and
`artificial-analysis` provider aliases. Unindexed releases are logged as a
`model_release_radar_unindexed` warning for an operator to index with the
`add-external-paper` and `add-evals` skills; scheduled jobs never create
external papers. Releases from any other lab (for example Reflection's Beam,
Aleph Alpha's Kolibri, or Meta's Muse Wonder) are found through a web news
search: four Exa news queries over the last three days (`EXA_API_KEY`, about
$0.09 per run) whose deduplicated headlines `gpt-5.6-luna` turns into
(lab, model, date, cited hits) releases (`OPENAI_API_KEY`). A web signal links
the lab's own announcement page when one of the hits is from the lab, and a
news article otherwise. Pass `--skip-web-search` to scan only the feeds and
the leaderboard. Run it by hand with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.scan_model_releases --lookback-days 30
```

`extract_urls.py` uses Gemini to find official GitHub repositories and project
pages for papers that still have `urls_extracted = false`.

`import_hf_daily_papers.py` runs hourly, imports the current day's Hugging Face
papers that are not yet in the database, and auto-tags tasks/methods using
keyword matching. New papers get a feed-style TL;DR from `gpt-5.6-luna`
(`backend/services/paper_tldr_service.py`, needs `PWC_OPENAI_API_KEY`); if that
key is missing or the call fails, the Hugging Face `ai_summary` is stored instead.
Each run also fills a TL;DR for up to 50 latest-version papers that have an
abstract but no TL;DR, which covers papers added through the admin API, the
`paper index` CLI, or external-resource ingestion. It also links curated organization payloads for both new and
already-existing papers.

The three MMTEB v2 jobs consume the official MTEB leaderboard API's precomputed
`meanTask`, Retrieval, and Reranking aggregates. They synchronize only models
whose API citation resolves unambiguously to a latest-version local arXiv paper;
rows without a paper, with a missing local paper, or with unresolved multiple
citations are skipped. Every lane owns only rows carrying its managed
methodology prefix, so manual evaluation rows remain untouched.

The MMEB-v2 and MMEB-v3 jobs consume the official MMEB Space's precomputed
`Overall-V2` and V3 `Overall` tables. They synchronize only rows whose official
model link resolves to exactly one local paper through an arXiv URL, Hugging
Face artifact, GitHub repository, project page, or external source URL. Each
job owns only its managed-prefix rows, leaving manually curated evaluations
untouched.

`sync_parsebench.py` consumes the official `leaderboard.csv` published in the
`run-llama/parsebench` repository (the source of parsebench.ai). It publishes
only rows whose exact upstream provider label is mapped to a reviewed paper or
official release page, stores the overall score plus the five dimension scores,
owns only its managed-prefix rows, and logs unreviewed provider labels as a
warning instead of failing.

`sync_extractbench.py` applies the same reviewed-label contract to the official
`leaderboard.csv` in `run-llama/ExtractBench`. It stores unified value F1 plus
word- and page-level grounding F1 on the Document Understanding task, and omits
the grounding metrics for systems that return no evidence (upstream reports
0.00 for both).

`sync_vals_finance_agent.py` parses the Finance Agent v2 table on
https://www.vals.ai/benchmarks/fabv2 (Rank, Model, Accuracy, …) into the
`finance-agent-v2` benchmark on task `agents` and fails on any layout change
or a row count outside 40–400. Exact Vals model labels map to reviewed
`(paper, model_name)` identities in the service (model names follow the
catalog, e.g. Vals "Wonder Full" is "Muse Wonder Full (max)"); the job never
creates papers, so unreviewed labels and unresolved papers are logged as
warnings. It creates missing mapped rows, revises a row's accuracy when Vals
changes it (values that round to the published precision are unchanged),
adopts matching hand-imported rows, and renames a mislabelled hand-imported
row once (`renamed_from`, only when its score matches). Managed rows that drop
off the leaderboard are reported, never deleted.

`sync_physics_iq_verified.py` parses the Physics-IQ Verified table in the
official `google-deepmind/physics-IQ-benchmark` README (the
physics-iq-verified.anates.ai site has no JSON endpoint) and fails on any
layout change or a row count outside 30–300. It applies an explicit import
policy: best-of-N runs reranked by a third-party reward model (WMReward, MBR
consensus) and Physical Registry rows (anonymous manuscript) are excluded, and
each reviewed model keeps its best single-generation run per track (I2V, V2V).
Exact leaderboard labels map to reviewed `(paper, model_name)` identities; the
job never creates papers, so unreviewed labels and unresolved papers are
logged as warnings. It creates missing mapped rows, revises a row's score and
methodology when the leaderboard changes (a stored value that rounds to the
published precision is unchanged), and adopts matching hand-imported rows by
prefixing their methodology. Managed rows that drop off the leaderboard are
reported, never deleted, and rows outside the managed set are never touched.

`sync_hf_organizations.py` runs daily as an append-only reconciliation backstop
for the strict 21-organization manifest. It validates HF organization pages,
imports missing ArXiv papers, caches validated logos, and never removes an
existing HF attribution.

`sync_hf_author_profiles.py` walks `https://huggingface.co/api/papers` (newest
first, 100 papers per request) back 30 days and applies each paper's HF
authorship claims. Each HF account has its own author row, which lists only
the papers it claimed: a claim moves the paper's link from the author matched
by that name to the account's row (created on first sight), marks the link
`claimed`, and refreshes the avatar, username, and Pro status. It never moves an
account between rows, ignores HF's unconfirmed `extracted_pending` guesses, and
logs claims of an already claimed slot and unmatched names as `conflicts` and
`unmatched`. Pass `--days N` for a one-off historical backfill (`--days 10000`
walks all of HF, about an hour) and `--dry-run` to roll back every batch.

`calculate_organization_trending_scores.py` runs after paper trending and
organization sync. It upserts one raw snapshot per featured organization and UTC
date, calculates the trailing 30-day arithmetic mean, and retains 120 days of
bounded history.

`refresh_paper_embeddings.py` runs 15 minutes later and sends only missing or
content-changed latest papers to the protected TEI endpoint. It validates and
upserts normalized vectors into the active generation in bounded batches. The
VPS supplies the endpoint URL and `PWC_HF_TOKEN` from `backend/keys.env`.

## Manual Utilities

The backfill and maintenance scripts are not scheduled by GitHub Actions:

```bash
uv run --env-file backend/keys.env python .github/workflows/scripts/hourly/update_hf_artifacts.py --backfill
uv run --env-file backend/keys.env python .github/workflows/scripts/hourly/update_hf_artifacts.py --backfill-explicit

PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.backfill.backfill_hf_papers
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.backfill.backfill_hf_papers --max-papers 200

PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.maintenance.cleanup_invalid_repositories --dry-run
./.github/workflows/scripts/maintenance/run_cleanup_invalid_repositories.sh --limit 100
```

The Hugging Face artifact backfill requires `PWC_HF_TOKEN` in
`backend/keys.env`, or `HF_TOKEN` in the process environment. Each invocation
processes at most 4,000 previously unscanned latest-version arXiv papers
published since January 2021 (the start of the public trend series), and commits
after every paper. Re-run it until it reports zero papers needing discovery.
Valid empty Hub responses are checkpointed; rate limits and transient failures
are retried and remain unscanned if all retries fail.

`--backfill-explicit` is the bounded, idempotent repair path for paper rows that
already contain curated HF URLs. It scans all latest-version publication dates,
creates missing normalized artifact/junction rows without arXiv discovery
calls, and refreshes metrics only for artifacts linked to papers in the active
180-day window.

Keep these manual unless a production schedule is intentionally added.

## Management Commands

```bash
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py list
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py status
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py status update_citations_hourly
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py test update_citations
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py summary
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py cleanup
```

Production recovery and dry-run selection use the allowlisted launcher:

```bash
sudo pwc-cron update_hot_github_trending --dry-run
pwc cron health update_hot_github_trending --strict --json
```

The optional `PWC_GITHUB_TOKEN_HOT` belongs only in
`/etc/paperswithcode/production-cron.env`. Without it, the hot queue falls back
to `PWC_GITHUB_TOKEN` and stops at the configured reserve (at least 500 calls).
Requests reuse a session, retain GitHub rate headers, honor `Retry-After`, and
retry transient 5xx responses with bounded jittered backoff. Structured
`api_calls` counts every HTTP attempt, including retry attempts.

The workflow is intentionally `workflow_dispatch`-only for staging review.
Production activation is not implied by merging or staging deployment. First
install the checked-in deploy tooling from the exact authorized production SHA,
then deploy that SHA to production and confirm `sudo pwc-cron status` lists the
new command. Only then add `*/15 * * * *` in a separately reviewed workflow
commit.

The management script discovers `hourly/`, `daily/`, `weekly/`, and `monthly/`
Python jobs. It does not schedule jobs itself.

## Adding A Job

1. Put scheduled jobs under `.github/workflows/scripts/hourly/` or `.github/workflows/scripts/daily/`.
2. Reuse `DatabaseCronJob` from `.github/workflows/scripts/utils/cron_helpers.py` for DB-backed jobs.
3. Add or update a shell wrapper if the GitHub Action needs one.
4. Add a `.github/workflows/cron-*.yml` workflow if the job should run in production.
5. Run with `uv run --env-file backend/keys.env ...` before enabling a schedule.

## References

- GitHub Actions workflow overview: `.github/workflows/README.md`
- Operational overview: `docs/operations.md`
- Trending implementation notes: `.github/workflows/scripts/hourly/README.md` and `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`
