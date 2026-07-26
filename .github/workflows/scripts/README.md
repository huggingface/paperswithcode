# PapersWithCode Cron Jobs

Production cron scheduling is driven by GitHub Actions. The workflows under
`.github/workflows/cron-*.yml` SSH into the VPS and run the entrypoints in this
directory with `uv run --env-file backend/keys.env ...`.

## Active Production Jobs

| Workflow | Schedule (UTC) | VPS entrypoint | Python job |
| --- | --- | --- | --- |
| `cron-update-github-stars.yml` | `0 * * * *` | `.github/workflows/scripts/run_github_stars.sh` | `.github/workflows/scripts/hourly/update_github_stars.py` |
| `cron-calculate-trending-scores.yml` | `15 * * * *` | `.github/workflows/scripts/run_trending_scores.sh` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` |
| `cron-update-citations.yml` | `30 * * * *` | `.github/workflows/scripts/run_citations_hourly.sh` | `.github/workflows/scripts/hourly/update_citations.py` |
| `cron-extract-urls.yml` | `45 * * * *` | `.github/workflows/scripts/run_extract_urls_hourly.sh` | `.github/workflows/scripts/hourly/extract_urls.py` |
| `cron-import-hf-daily-papers.yml` | `0 * * * *` | direct `uv run` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` |
| `cron-refresh-paper-embeddings.yml` | `15 * * * *` | `.github/workflows/scripts/run_refresh_paper_embeddings.sh` | `.github/workflows/scripts/hourly/refresh_paper_embeddings.py` |
| `cron-update-hf-artifacts.yml` | `30 * * * *` | `pwc-cron update_hf_artifacts` | `.github/workflows/scripts/hourly/update_hf_artifacts.py` |
| `cron-link-methods-by-references.yml` | `0 4 * * 0` | `.github/workflows/scripts/run_link_methods_by_references_weekly.sh` | `.github/workflows/scripts/weekly/link_methods_by_references.py` |
| `cron-link-papers-by-task-keywords.yml` | `0 5 * * 0` | `.github/workflows/scripts/run_link_papers_by_task_keywords_weekly.sh` | `.github/workflows/scripts/weekly/link_papers_by_task_keywords.py` |

The `test-database.yml` workflow is unrelated to cron scheduling.

## Directory Layout

```text
.github/workflows/scripts/
├── daily/
│   └── import_hf_daily_papers.py
├── hourly/
│   ├── calculate_trending_scores.py
│   ├── extract_urls.py
│   ├── refresh_paper_embeddings.py
│   ├── update_citations.py
│   └── update_github_stars.py
├── backfill/
│   └── backfill_hf_papers.py
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

`update_github_stars.py` refreshes repository star counts and writes historical
snapshots to `repository_star_history`. Recent papers are refreshed more often
than older papers so trending calculations have enough signal.

`calculate_trending_scores.py` computes EMA-smoothed trending scores from star
history and stores them on repositories for the trending API/view pipeline.

`update_citations.py` pulls citation counts from Semantic Scholar for ArXiv
papers. Runs are bounded so hourly Actions do not pile up under API throttling.

`extract_urls.py` uses Gemini to find official GitHub repositories and project
pages for papers that still have `urls_extracted = false`.

`import_hf_daily_papers.py` runs hourly, imports the current day's Hugging Face
papers that are not yet in the database, and auto-tags tasks/methods using
keyword matching.

`refresh_paper_embeddings.py` runs 15 minutes later and sends only missing or
content-changed latest papers to the protected TEI endpoint. It validates and
upserts normalized vectors into the active generation in bounded batches. The
VPS supplies the endpoint URL and `PWC_HF_TOKEN` from `backend/keys.env`.

## Manual Utilities

The backfill and maintenance scripts are not scheduled by GitHub Actions:

```bash
uv run --env-file backend/keys.env python .github/workflows/scripts/hourly/update_hf_artifacts.py --backfill

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
