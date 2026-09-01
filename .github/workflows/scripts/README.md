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
| `cron-sync-3d-arena.yml` | `5 * * * *` | `pwc-cron sync_3d_arena` | `.github/workflows/scripts/hourly/sync_3d_arena.py` |
| `cron-sync-tabarena.yml` | `55 * * * *` | `pwc-cron sync_tabarena` | `.github/workflows/scripts/hourly/sync_tabarena.py` |
| `cron-sync-open-asr.yml` | `15 * * * *` | `pwc-cron sync_open_asr` | `.github/workflows/scripts/hourly/sync_open_asr.py` |
| `cron-sync-mmteb-overall.yml` | `7 * * * *` | `pwc-cron sync_mmteb_overall` | `.github/workflows/scripts/hourly/sync_mmteb.py overall` |
| `cron-sync-mmteb-retrieval.yml` | `22 * * * *` | `pwc-cron sync_mmteb_retrieval` | `.github/workflows/scripts/hourly/sync_mmteb.py retrieval` |
| `cron-sync-mmteb-reranking.yml` | `37 * * * *` | `pwc-cron sync_mmteb_reranking` | `.github/workflows/scripts/hourly/sync_mmteb.py reranking` |
| `cron-sync-mmeb-v2.yml` | `12 * * * *` | `pwc-cron sync_mmeb_v2` | `.github/workflows/scripts/hourly/sync_mmeb.py v2` |
| `cron-sync-mmeb-v3.yml` | `42 * * * *` | `pwc-cron sync_mmeb_v3` | `.github/workflows/scripts/hourly/sync_mmeb.py v3` |
| `cron-sync-deepswe.yml` | `25 * * * *` | `pwc-cron sync_deepswe` | `.github/workflows/scripts/hourly/sync_deepswe.py` |
| `cron-sync-artificial-analysis.yml` | `35 * * * *` | `pwc-cron sync_artificial_analysis` | `.github/workflows/scripts/hourly/sync_artificial_analysis.py` |
| `cron-sync-programbench.yml` | `40 * * * *` | `pwc-cron sync_programbench` | `.github/workflows/scripts/hourly/sync_programbench.py` |
| `cron-sync-frontiercode.yml` | `45 * * * *` | `pwc-cron sync_frontiercode` | `.github/workflows/scripts/hourly/sync_frontiercode.py` |
| `cron-sync-coarena.yml` | `50 * * * *` | `pwc-cron sync_coarena` | `.github/workflows/scripts/hourly/sync_coarena.py` |
| `cron-sync-arc-prize.yml` | `10 * * * *` | `pwc-cron sync_arc_prize` | `.github/workflows/scripts/hourly/sync_arc_prize.py` |
| `cron-sync-hf-organizations.yml` | `20 2 * * *` | `pwc-cron sync_hf_organizations` | `.github/workflows/scripts/daily/sync_hf_organizations.py` |
| `cron-calculate-organization-trending-scores.yml` | `40 3 * * *` | `pwc-cron calculate_organization_trending_scores` | `.github/workflows/scripts/daily/calculate_organization_trending_scores.py` |
| `cron-refresh-paper-embeddings.yml` | `15 * * * *` | `.github/workflows/scripts/run_refresh_paper_embeddings.sh` | `.github/workflows/scripts/hourly/refresh_paper_embeddings.py` |
| `cron-update-hf-artifacts.yml` | `30 * * * *` | `pwc-cron update_hf_artifacts` | `.github/workflows/scripts/hourly/update_hf_artifacts.py` |
| `cron-backfill-method-keywords.yml` | `10 1 * * *` | `pwc-cron backfill_method_keywords --resume --limit 250000 --max-runtime-seconds 3300` | `.github/workflows/scripts/backfill/backfill_method_keywords.py` |
| `cron-backfill-method-references.yml` | `15 */6 * * *` | `pwc-cron backfill_method_references --provider semantic-scholar --resume --retry-failures --limit 10000 --max-runtime-seconds 19800` | `.github/workflows/scripts/backfill/backfill_method_references.py` |
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

The Semantic Scholar reference backfill fails closed unless
`PWC_SEMANTIC_SCHOLAR_API_KEY_2` is present and valid. That secondary key is
reserved for historical scans; hourly citation updates and the weekly
incremental linker continue to own `PWC_SEMANTIC_SCHOLAR_API_KEY`.
The checked-in schedule uses the secondary Semantic Scholar key reserved for
historical scans. Alternatively, `--provider openalex` batches exact arXiv
landing-page lookups and uses `PWC_OPENALEX_API_KEY` when configured, while
retaining OpenAlex's smaller keyless allowance for manual bounded runs.
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

`extract_urls.py` uses Gemini to find official GitHub repositories and project
pages for papers that still have `urls_extracted = false`.

`import_hf_daily_papers.py` runs hourly, imports the current day's Hugging Face
papers that are not yet in the database, and auto-tags tasks/methods using
keyword matching. It also links curated organization payloads for both new and
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

`sync_hf_organizations.py` runs daily as an append-only reconciliation backstop
for the strict 21-organization manifest. It validates HF organization pages,
imports missing ArXiv papers, caches validated logos, and never removes an
existing HF attribution.

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
