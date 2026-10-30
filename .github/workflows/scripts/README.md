# PapersWithCode Cron Jobs

Production CRON jobs run from host systemd timers. `deploy/cron_schedules.py`
is the schedule's single source of truth: `python deploy/generate_cron_units.py`
renders it into the committed units in `deploy/systemd/cron/`, and each timer
invokes the allowlisted `pwc-cron` launcher (`deploy/cron_launcher.py`) through
the bounded `pwc-cron-throttled` wrapper. The `.github/workflows/cron-*.yml`
workflows are `workflow_dispatch`-only recovery paths that SSH into the VPS and
run the same `pwc-cron` jobs. Schedules keep the minute offsets the old GitHub
Actions triggers used, so load stays staggered.

## Production Timers

Generated from `deploy/cron_schedules.py`; update this table when you change it.

| Timer | OnCalendar (UTC) | `pwc-cron` invocation | Python job |
| --- | --- | --- | --- |
| `pwc-cron-send-research-digests.timer` | `*-*-* *:00:00` | `send_research_digests` | `backend/scripts/send_research_digests.py` |
| `pwc-cron-create-eval-verification-issues.timer` | `*-*-* *:52:00` | `create_eval_verification_issues` | `backend/scripts/create_eval_verification_issues.py` `--execute` |
| `pwc-cron-run-chat-synthetic-probe.timer` | `*-*-* *:*:00` | `run_chat_synthetic_probe` | `backend/scripts/run_chat_synthetic_probe.py` |
| `pwc-cron-update-github-stars.timer` | `*-*-* *:00:00` | `update_github_stars` | `.github/workflows/scripts/hourly/update_github_stars.py` |
| `pwc-cron-update-hot-github-trending.timer` | `*-*-* *:00/15:00` | `update_hot_github_trending` | `.github/workflows/scripts/hourly/update_hot_github_trending.py` |
| `pwc-cron-calculate-trending-scores.timer` | `*-*-* *:15:00` | `calculate_trending_scores` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` |
| `pwc-cron-update-citations.timer` | `*-*-* *:30:00` | `update_citations` | `.github/workflows/scripts/hourly/update_citations.py` |
| `pwc-cron-update-hf-artifacts.timer` | `*-*-* *:30:00` | `update_hf_artifacts` | `.github/workflows/scripts/hourly/update_hf_artifacts.py` |
| `pwc-cron-calculate-paper-trending-scores.timer` | `*-*-* *:45:00` | `calculate_paper_trending_scores` | `.github/workflows/scripts/hourly/calculate_paper_trending_scores.py` |
| `pwc-cron-import-hf-daily-papers.timer` | `*-*-* *:00:00` | `import_hf_daily_papers` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` |
| `pwc-cron-refresh-paper-embeddings.timer` | `*-*-* *:15:00` | `refresh_paper_embeddings` | `.github/workflows/scripts/hourly/refresh_paper_embeddings.py` |
| `pwc-cron-paper-markdown-backfill.timer` | `*-*-* *:17:00` | `paper_markdown_backfill --execute --confirm`<br>`paper_markdown_backfill --full --execute --confirm` | `.github/workflows/scripts/hourly/backfill_paper_markdown.py` |
| `pwc-cron-paper-markdown-fresh.timer` | `*-*-* *:00/5:00` | `paper_markdown_backfill --lane fresh --execute --confirm` | `.github/workflows/scripts/hourly/backfill_paper_markdown.py` (papers indexed in the last 24 h; two 10-paper slots and its own lock; the hourly live lane skips that window) |
| `pwc-cron-enqueue-hf-daily-paper-curation.timer` | `*-*-* *:27:00` | `enqueue_hf_daily_paper_curation` | `backend/scripts/enqueue_hf_daily_paper_curation.py` |
| `pwc-cron-enqueue-hf-trending-model-curation.timer` | `*-*-* *:42:00` | `enqueue_hf_trending_model_curation` | `backend/scripts/enqueue_hf_trending_model_curation.py` |
| `pwc-cron-enqueue-benchmark-gap-review.timer` | `*-*-* 06:35:00` | `enqueue_benchmark_gap_review` | `backend/scripts/enqueue_benchmark_gap_review.py` |
| `pwc-cron-scan-model-releases.timer` | `*-*-* 01/3:48:00` | `scan_model_releases` | `backend/scripts/scan_model_releases.py` |
| `pwc-cron-sweep-conference-deadlines.timer` | `Sun *-*-* 02:35:00` | `sweep_conference_deadlines` | `backend/scripts/sweep_conference_deadlines.py` |
| `pwc-cron-link-google-scholar-profiles.timer` | `Wed *-*-* 05:20:00` | `link_google_scholar_profiles` | `backend/scripts/link_google_scholar_profiles.py` |
| `pwc-cron-refresh-conference-deadlines.timer` | `*-*-* 07:40:00`<br>`*-*-* 19:40:00` | `refresh_conference_deadlines` | `backend/scripts/refresh_conference_deadlines.py` |
| `pwc-cron-discover-x-threads.timer` | `*-*-* 08,20:22:00` | `discover_x_threads` | `backend/scripts/discover_x_threads.py` |
| `pwc-cron-post-trending-paper-to-x.timer` | `*-*-* 00/4:13:00` | `post_trending_paper_to_x` | `backend/scripts/post_trending_paper_to_x.py` |
| `pwc-cron-post-x-insight.timer` | `*-*-* 09,17:43:00` | `post_x_insight` | `backend/scripts/post_x_insight.py` |
| `pwc-cron-warm-paper-suggested-questions.timer` | `*-*-* *:33:00` | `warm_paper_suggested_questions` | `backend/scripts/warm_paper_suggested_questions.py` |
| `pwc-cron-sync-3d-arena.timer` | `*-*-* *:05:00` | `sync_3d_arena` | `.github/workflows/scripts/hourly/sync_3d_arena.py` |
| `pwc-cron-sync-mmteb-overall.timer` | `*-*-* *:07:00` | `sync_mmteb_overall` | `.github/workflows/scripts/hourly/sync_mmteb.py` overall |
| `pwc-cron-sync-arc-prize.timer` | `*-*-* *:10:00` | `sync_arc_prize` | `.github/workflows/scripts/hourly/sync_arc_prize.py` |
| `pwc-cron-sync-mmeb-v2.timer` | `*-*-* *:12:00` | `sync_mmeb_v2` | `.github/workflows/scripts/hourly/sync_mmeb.py` v2 |
| `pwc-cron-sync-open-asr.timer` | `*-*-* *:15:00` | `sync_open_asr` | `.github/workflows/scripts/hourly/sync_open_asr.py` |
| `pwc-cron-sync-open-tts.timer` | `*-*-* *:18:00` | `sync_open_tts` | `.github/workflows/scripts/hourly/sync_open_tts.py` |
| `pwc-cron-sync-parsebench.timer` | `*-*-* *:20:00` | `sync_parsebench` | `.github/workflows/scripts/hourly/sync_parsebench.py` |
| `pwc-cron-sync-mmteb-retrieval.timer` | `*-*-* *:22:00` | `sync_mmteb_retrieval` | `.github/workflows/scripts/hourly/sync_mmteb.py` retrieval |
| `pwc-cron-sync-deepswe.timer` | `*-*-* *:25:00` | `sync_deepswe` | `.github/workflows/scripts/hourly/sync_deepswe.py` |
| `pwc-cron-sync-extractbench.timer` | `*-*-* *:32:00` | `sync_extractbench` | `.github/workflows/scripts/hourly/sync_extractbench.py` |
| `pwc-cron-sync-vals-finance-agent.timer` | `*-*-* *:47:00` | `sync_vals_finance_agent` | `.github/workflows/scripts/hourly/sync_vals_finance_agent.py` |
| `pwc-cron-sync-surge-chartography.timer` | `*-*-* *:38:00` | `sync_surge_chartography` | `.github/workflows/scripts/hourly/sync_surge_chartography.py` |
| `pwc-cron-sync-frontiercs-2.timer` | `*-*-* *:43:00` | `sync_frontiercs_2` | `.github/workflows/scripts/hourly/sync_frontiercs_2.py` |
| `pwc-cron-sync-vals-index.timer` | `*-*-* *:03:00` | `sync_vals_index` | `.github/workflows/scripts/hourly/sync_vals_index.py` |
| `pwc-cron-sync-swe-sweep.timer` | `*-*-* *:08:00` | `sync_swe_sweep` | `.github/workflows/scripts/hourly/sync_swe_sweep.py` |
| `pwc-cron-sync-vending-bench-2.timer` | `*-*-* *:13:00` | `sync_vending_bench_2` | `.github/workflows/scripts/hourly/sync_vending_bench_2.py` |
| `pwc-cron-sync-blueprint-bench-2.timer` | `*-*-* *:16:00` | `sync_blueprint_bench_2` | `.github/workflows/scripts/hourly/sync_blueprint_bench_2.py` |
| `pwc-cron-sync-riemann-bench.timer` | `*-*-* *:23:00` | `sync_riemann_bench` | `.github/workflows/scripts/hourly/sync_riemann_bench.py` |
| `pwc-cron-sync-cwe-bench.timer` | `*-*-* *:34:00` | `sync_cwe_bench` | `.github/workflows/scripts/hourly/sync_cwe_bench.py` |
| `pwc-cron-sync-exploitgym.timer` | `*-*-* *:46:00` | `sync_exploitgym` | `.github/workflows/scripts/hourly/sync_exploitgym.py` |
| `pwc-cron-sync-cybergym.timer` | `*-*-* *:09:00` | `sync_cybergym` | `.github/workflows/scripts/hourly/sync_cybergym.py` |
| `pwc-cron-sync-patcheval-verified.timer` | `*-*-* *:21:00` | `sync_patcheval_verified` | `.github/workflows/scripts/hourly/sync_patcheval_verified.py` |
| `pwc-cron-sync-physics-iq-verified.timer` | `*-*-* *:28:00` | `sync_physics_iq_verified` | `.github/workflows/scripts/hourly/sync_physics_iq_verified.py` |
| `pwc-cron-sync-artificial-analysis.timer` | `*-*-* 00/2:35:00` | `sync_artificial_analysis` | `.github/workflows/scripts/hourly/sync_artificial_analysis.py` |
| `pwc-cron-sync-mmteb-reranking.timer` | `*-*-* *:37:00` | `sync_mmteb_reranking` | `.github/workflows/scripts/hourly/sync_mmteb.py` reranking |
| `pwc-cron-sync-programbench.timer` | `*-*-* *:40:00` | `sync_programbench` | `.github/workflows/scripts/hourly/sync_programbench.py` |
| `pwc-cron-sync-mmeb-v3.timer` | `*-*-* *:42:00` | `sync_mmeb_v3` | `.github/workflows/scripts/hourly/sync_mmeb.py` v3 |
| `pwc-cron-sync-frontiercode.timer` | `*-*-* *:45:00` | `sync_frontiercode` | `.github/workflows/scripts/hourly/sync_frontiercode.py` |
| `pwc-cron-sync-coarena.timer` | `*-*-* *:50:00` | `sync_coarena` | `.github/workflows/scripts/hourly/sync_coarena.py` |
| `pwc-cron-sync-tabarena.timer` | `*-*-* *:55:00` | `sync_tabarena` | `.github/workflows/scripts/hourly/sync_tabarena.py` |
| `pwc-cron-backfill-method-keywords.timer` | `*-*-* 01:10:00` | `backfill_method_keywords --resume --limit 250000 --max-runtime-seconds 3300` | `.github/workflows/scripts/backfill/backfill_method_keywords.py` |
| `pwc-cron-sync-hf-organizations.timer` | `*-*-* 02:20:00` | `sync_hf_organizations` | `.github/workflows/scripts/daily/sync_hf_organizations.py` |
| `pwc-cron-sync-hf-author-profiles.timer` | `*-*-* 02:50:00` | `sync_hf_author_profiles` | `.github/workflows/scripts/daily/sync_hf_author_profiles.py` |
| `pwc-cron-export-enrichment-dashboard.timer` | `*-*-* 03:10:00` | `export_enrichment_dashboard` | `backend/scripts/export_enrichment_dashboard.py` `--upload` |
| `pwc-cron-link-openalex-organizations.timer` | `*-*-* 03:20:00` | `link_openalex_organizations` | `.github/workflows/scripts/daily/link_openalex_organizations.py` |
| `pwc-cron-calculate-organization-trending-scores.timer` | `*-*-* 03:40:00` | `calculate_organization_trending_scores` | `.github/workflows/scripts/daily/calculate_organization_trending_scores.py` |
| `pwc-cron-mirror-thumbnails-to-disk.timer` | `*-*-* 05:00:00` | `mirror_thumbnails_to_disk` | `.github/workflows/scripts/daily/mirror_thumbnails_to_disk.py` |
| `pwc-cron-backfill-method-references.timer` | `*-*-* *:15:00` | `backfill_method_references --provider openalex --resume --retry-failures --limit 10000 --max-runtime-seconds 19800` | `.github/workflows/scripts/backfill/backfill_method_references.py` |
| `pwc-cron-link-methods-by-references.timer` | `Sun *-*-* 04:00:00` | `link_methods_by_references` | `.github/workflows/scripts/weekly/link_methods_by_references.py` |
| `pwc-cron-link-papers-by-task-keywords.timer` | `Sun *-*-* 05:00:00` | `link_papers_by_task_keywords` | `.github/workflows/scripts/weekly/link_papers_by_task_keywords.py` |
| `pwc-cron-preload-thumbnails-visible.timer` | `*-*-* 00/3:00:00` | `preload_thumbnails --priority visible --citation-top 1000 --trending-top 500 --newest-top 300 --per-task 20 --per-method 20 --limit 10000 --missing-only --trust-local-cache --max-runtime-seconds 6000` | `.github/workflows/scripts/daily/preload_thumbnails.py` |
| `pwc-cron-preload-thumbnails-task-top.timer` | `*-*-* 04:00:00` | `preload_thumbnails --priority task-top --per-task 50 --missing-only --trust-local-cache --max-runtime-seconds 6000` | `.github/workflows/scripts/daily/preload_thumbnails.py` |
| `pwc-cron-preload-thumbnails-method-top.timer` | `*-*-* 04:15:00` | `preload_thumbnails --priority method-top --per-method 50 --missing-only --trust-local-cache --max-runtime-seconds 6000` | `.github/workflows/scripts/daily/preload_thumbnails.py` |
| `pwc-cron-preload-thumbnails-recent.timer` | `*-*-* 04:30:00` | `preload_thumbnails --priority recent --recent-days 30 --limit 500 --max-runtime-seconds 6000` | `.github/workflows/scripts/daily/preload_thumbnails.py` |
| `pwc-cron-preload-thumbnails-external.timer` | `*-*-* 04:45:00` | `preload_thumbnails --priority external-missing --limit 2000 --request-delay-seconds 2 --max-failures -1 --max-runtime-seconds 6000` | `.github/workflows/scripts/daily/preload_thumbnails.py` |

Host timers outside that table: `pwc-curation-thumbnails.timer` (every minute,
`process_curation_thumbnails`), `pwc-chat-alert-monitor.timer` (every minute),
and `pwc-postgres-backup.timer` (03:15) under `deploy/systemd/`, plus
`submission-review.timer`, which `deploy/install_deploy_tools.py` writes. `extract_urls` has no timer; its hourly schedule has been
paused since 2026-07-13, so it runs only through `cron-extract-urls.yml`
dispatch.

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
│   ├── link_openalex_organizations.py
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
│   ├── run_cleanup_invalid_repositories.sh
│   └── thumbnail_coverage.py
├── utils/
│   ├── cron_helpers.py
│   └── hf_paper_importer.py
├── manage_cron.py
└── run_*.sh
```

`hourly/` also holds every leaderboard `sync_*.py` job, `update_hf_artifacts.py`,
`calculate_paper_trending_scores.py`, and `backfill_paper_markdown.py`; `daily/`
also holds `sync_hf_author_profiles.py`, `preload_thumbnails.py`, and
`mirror_thumbnails_to_disk.py`. Many scheduled jobs live in `backend/scripts/`
instead; the timer table names each job's module. The top-level `run_*.sh`
wrappers predate `pwc-cron` and nothing invokes them any more.

Generated logs are written to `.github/workflows/scripts/logs/`. Backfill checkpoint state is runtime
data and is intentionally ignored by git.

## Job Summary

`update_hot_github_trending.py` is designed to own official repositories for
latest papers aged 0–30 days. Every 15 minutes it snapshots up to 500 normalized repository groups, calculates
repository EMA only for touched rows, then writes composite scores only for
their linked latest papers using full-corpus normalization.

`update_github_stars.py` owns the non-overlapping hourly fresh (31–180 days,
2,500 calls) and weekly (>180 days, 1,000 calls) queues.
The hot/fresh boundary is a fixed 30 days shared by both adapters and CRON
health; only cadence, caps, delays, and credentials are configurable.

`calculate_trending_scores.py` computes EMA-smoothed trending scores from star
history and stores them on repositories for the trending API/view pipeline.

`update_citations.py` pulls citation counts from Semantic Scholar for ArXiv
papers. Runs are bounded so hourly runs do not pile up under API throttling.

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
`add-benchmark` job, at most 40 per UTC day, that finds the introducing paper,
the most specific task, and one to three metrics; the backend validates and
writes the rows, then requeues add-evals for the papers that reported the gap.
Rejected candidates return for review once their paper count doubles; deferred
ones after 14 days. Both kinds share the scheduler pause and run at most two at
a time. Inspect or dry-run it with:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.enqueue_benchmark_gap_review --status
```

`warm_paper_suggested_questions.py` pre-generates the three paper-page
suggested questions (gpt-6-luna, stored in `paper_suggested_questions`) for
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

`scan_model_releases.py` is a radar for model releases that neither
the daily-paper import (arXiv only) nor the trending-model curation (Hub
weights only) can see, such as API-only or blog-first launches. Every three
hours it reads the official news feeds of OpenAI and Google DeepMind (RSS) and
Anthropic, Mistral AI, and DeepSeek (sitemaps plus the newest article pages),
keeps posts whose headline announces a versioned model name, and adds recent
Artificial Analysis leaderboard models that are missing from the reviewed
`MODEL_PAPER_IDENTITIES` map. Each release from the last 14 days is matched
against `papers.source_url`, paper titles, `model_releases`, and
`artificial-analysis` provider aliases. Unindexed releases are logged as a
`model_release_radar_unindexed` warning. Releases from any other lab (for example Reflection's Beam,
Aleph Alpha's Kolibri, or Meta's Muse Wonder) are found through a web news
search: four Exa news queries over the last three days (`EXA_API_KEY`, about
$0.09 per run) whose deduplicated headlines `gpt-6-luna` turns into
(lab, model, date, cited hits) releases (`OPENAI_API_KEY`). A web signal links
the lab's own announcement page when one of the hits is from the lab, and a
news article otherwise. Pass `--skip-web-search` to scan only the feeds and
the leaderboard.

Each unindexed feed or web release (not Artificial Analysis slugs, which have
no announcement page) is upserted into `model_release_signals`, one row per
normalized lab and model name. A signal qualifies for curation on its first
sighting from a vendor feed, or on its second web-search sighting, because
web extraction varies from run to run. Each qualifying signal gets one
`resolve-model-paper` job (trigger `model-release-radar`, at most 6 per UTC
day, on the scheduled curation pause and capacity). The curator finds the
lab's own announcement and resolves the release to an existing paper (old news
about an indexed release), an arXiv report, or a new external paper. The
backend refuses an external paper whose source is not on the publisher's own
site or Hub/GitHub organization, that reuses the news lead's host, or that
duplicates an indexed paper's source, title, or model release. A new external
paper gets the usual enrich-paper -> add-evals workflow, and the resolution
records a `model_releases` row so later scans see the release as indexed. A
failed resolution retries after two days if the radar still sees the release;
rejected signals stay closed. Hugging Face trending-model resolutions still
cannot create external papers. Run it by hand with (`--report-only` skips the
signal table and queue):

```bash
uv run --env-file backend/keys.env python -m backend.scripts.scan_model_releases --lookback-days 30 --report-only
```

`extract_urls.py` uses Gemini to find official GitHub repositories and project
pages for papers that still have `urls_extracted = false`. It is unscheduled
(see above) and runs only on manual dispatch.

`import_hf_daily_papers.py` runs hourly, imports the current day's Hugging Face
papers that are not yet in the database, and auto-tags tasks/methods using
keyword matching. New papers get a feed-style TL;DR from `gpt-6-luna`
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

`sync_frontiercs_2.py` reads the `MODELS`, `PASS`, `ECI`, and `UPDATED`
constants from https://frontier-cs.org/assets/js/fcs2-data.js (the
https://frontier-cs.org/#leaderboard page renders from them client-side) into
the `frontiercs-2` benchmark on task `coding-agents`: Pass Rate (percent of the
48 tasks whose run beats the human reference, checked against the pass count)
and FCI (FrontierCS Capabilities Index, refitted upstream with Kimi K2.7 at 0).
It fails on any layout change or an entry count outside 8–200. Exact model
names map to reviewed `(paper, model_name)` identities in the service, and each
entry's agent harness is stored in `harness`, so one model may appear once per
harness (Gemini 4 Argon in Pi and Antigravity). The job never creates papers,
so unreviewed names and unresolved papers are logged as warnings. It creates
missing mapped rows and rewrites managed rows' scores and methodology every
run; managed rows that drop off the leaderboard are reported, never deleted.

`sync_vals_index.py`, `sync_swe_sweep.py`, `sync_vending_bench_2.py`,
`sync_blueprint_bench_2.py`, `sync_riemann_bench.py`, `sync_cwe_bench.py`, and
`sync_exploitgym.py` keep the frontier boards added with Gemini 4 Carbon
current; `sync_cybergym.py` (the site's default model-focused Level 1 view) and
`sync_patcheval_verified.py` (the README results table) do the same for two
more Cybersecurity boards. Each parses its official leaderboard in
`backend/services/carbon_board_syncs.py` (failing on any layout change or an
implausible row count) and hands the rows to the shared single-metric engine in
`backend/services/live_leaderboard_sync.py`. Upstream names map to reviewed
identities in `backend/services/carbon_board_identities.py`; other names are
auto-matched or handed to the release radar, and a board's `excluded` names
(partial runs, non-standard setups) are skipped. The engine keeps one row per
catalog model and harness (the best upstream setting), adopts hand-imported
rows for the same model, never creates papers, and reports managed rows that
leave the leaderboard instead of deleting them.

`sync_surge_chartography.py` parses the server-rendered "Chartography
Leaderboard" block on https://surgehq.ai/benchmarks/chartography (provider,
model with its reasoning configuration, Pass@1 percent) into the
`chartography-no-tools` benchmark on task `image-understanding`, normalizing
percentages to 0–1, and fails on any layout change or a row count outside
25–400. Surge shows one best configuration per model; exact provider + model
labels map to reviewed `(paper, model_name)` identities in the service, and
row names carry the catalog's " (no tools)" suffix. The job never creates
papers, so unreviewed labels and unresolved papers are logged as warnings;
`EXCLUDED_LABELS` holds labels deliberately left out (DeepSeek V4 Flash
Vision (experimental)). It creates missing mapped rows, revises a row's score
when Surge changes it (values that round to the published precision are
unchanged), and adopts matching hand-imported rows, keeping their notes,
`is_open`, `hf_model_url`, and `num_parameters`. Managed rows that drop off the
leaderboard are reported, never deleted. The with-tools `chartography`
benchmark is curated by hand and never touched.

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
authorship claims. Each HF account has its own author row: a claim moves the
paper's link from the author matched by that name to the account's row
(created on first sight), marks the link
`claimed`, and refreshes the avatar, username, and Pro status. It never moves an
account between rows, ignores HF's unconfirmed `extracted_pending` guesses, and
logs claims of an already claimed slot and unmatched names as `conflicts` and
`unmatched`. Pass `--days N` for a one-off historical backfill (`--days 10000`
walks all of HF, about an hour) and `--dry-run` to roll back every batch.

`link_openalex_organizations.py` revisits arXiv papers published in the last 60
days (100 per OpenAlex request, `PWC_OPENALEX_API_KEY` when set) and adds
`paper_organizations` rows with `source = 'openalex'` for author institutions in
the reviewed map (`backend/database/organizations_setup/openalex_institutions.py`).
OpenAlex adds affiliations days to weeks after a paper appears, so the window is
wide; existing links are skipped and none are deleted. A refused OpenAlex request
fails the run. Pass `--days N` for a wider window and `--dry-run` to count
without writing; `backfill_openalex_organizations.py` handles historical runs.

`backend/scripts/link_google_scholar_profiles.py` (weekly) links authors to
Google Scholar profiles only when papers prove it. Candidates are Wikidata
people with a Scholar ID whose name fits an author with 3+ papers; each new
author is checked once on Semantic Scholar (up to 600 per run, largest first),
then the SerpAPI searches left this month (`PWC_SERPAPI_API_KEY`, free plan:
250) read the Scholar profiles of S2-matched candidates. A link is stored when
the profile lists at least half of the author's papers (70% for names several
Wikidata researchers share), and no other author claims the profile. Progress
is kept in `author_google_scholar_candidates`; links are never deleted. Pass
`--dry-run` to check Semantic Scholar and report without reading profiles or
writing.

`calculate_organization_trending_scores.py` runs after paper trending and
organization sync. It upserts one raw snapshot per featured organization and UTC
date, calculates the trailing 30-day arithmetic mean, and retains 120 days of
bounded history.

`refresh_paper_embeddings.py` runs at :15, after the HF import, and sends only missing or
content-changed latest papers to the protected TEI endpoint. It validates and
upserts normalized vectors into the active generation in bounded batches. The
production environment supplies the endpoint URL and `PWC_HF_TOKEN`.

## Manual Utilities

These backfill and maintenance scripts have no timer:

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

The management script discovers `hourly/`, `daily/`, `weekly/`, and `monthly/`
Python jobs. It does not schedule jobs itself.

## Adding A Job

1. Put the job under `.github/workflows/scripts/<cadence>/` or `backend/scripts/`;
   reuse `DatabaseCronJob` from `.github/workflows/scripts/utils/cron_helpers.py`
   for DB-backed jobs.
2. Test it against a disposable database with
   `uv run --env-file <disposable env> ...`; never point a test run at production.
3. Register it in `COMMANDS` in `deploy/cron_launcher.py` (timeout, idempotency).
4. Add a `TimerSpec` to `deploy/cron_schedules.py`, run
   `python deploy/generate_cron_units.py`, and commit the generated units.
   Add a row to the timer table above.
5. Optionally add a `workflow_dispatch` `.github/workflows/cron-*.yml` recovery
   workflow.
6. After the merged commit is deployed, install the deploy tooling from that
   commit and run `sudo systemctl enable --now pwc-cron-<job>.timer` once;
   installing units does not enable a new timer
   ([host timer scheduling](../../../docs/operations.md#host-timer-scheduling)).

## References

- GitHub Actions workflow overview: `.github/workflows/README.md`
- Operational overview: `docs/operations.md`
- Trending implementation notes: `.github/workflows/scripts/hourly/README.md` and `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`
