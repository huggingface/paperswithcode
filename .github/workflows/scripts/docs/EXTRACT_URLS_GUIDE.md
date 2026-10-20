# URL Extraction Cron Guide

The URL extraction workflow finds official GitHub repositories and project
pages with one Claude Agent SDK researcher per paper.

## Production Schedule

Production runs through GitHub Actions:

At `45 * * * *`, `cron-extract-urls.yml` runs three isolated jobs:

1. Select up to 100 candidates from the VPS database over SSH.
2. Dispatch one paper per Modal container, capped at 20 containers.
3. Return structured findings and persist validated URLs over SSH.

## Requirements

- GitHub repository secrets: `VPS_HOST`, `VPS_USER`,
  `VPS_SSH_PRIVATE_KEY`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`,
  `MODAL_TOKEN_ID`, and `MODAL_TOKEN_SECRET`.
- Existing Modal secret `anthropic`, containing the HF Inference Providers
  endpoint/token/model environment used by `paper_parsing_agent_v2`.
- Modal deployment access. The discovery job deploys the current app before
  dispatch; it can also be deployed manually:

```bash
uv run modal deploy url_extraction_agent/modal_app.py
```

## Manual Runs

```bash
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env python -m url_extraction_agent.database select --limit 1 > /tmp/candidates.json
uv run python -m url_extraction_agent.runner --input /tmp/candidates.json --output /tmp/results.json
uv run --env-file backend/keys.env python -m url_extraction_agent.database persist --input /tmp/results.json
```

Logs are written to:

```text
.github/workflows/scripts/logs/extract_urls_hourly_YYYYMMDD.log
```

## Current Runtime Settings

The hourly batch is capped at 100 papers and 20 concurrent Modal containers.
Each container processes exactly one paper. HF/provider 429 and transient
gateway failures receive bounded exponential-backoff retries.

## Processing Rules

Candidates are latest ArXiv papers with abstracts, at least one missing
official URL, and `urls_extracted = false`. New HF imports and page-one papers
from home/task/method/conference feeds rank first; remaining capacity drains
the backlog newest-first.

The model returns only reasoning and URL findings. Trusted orchestration derives
attempt health from SDK status and successful research tool events. URL
validation and database writes happen on the VPS. `urls_extracted` becomes true
only after a conclusive attempt and committed persistence; partial or failed
runs remain retryable.

## Troubleshooting

```bash
uv run --env-file backend/keys.env .github/workflows/scripts/manage_cron.py status extract_urls_hourly
tail -f .github/workflows/scripts/logs/extract_urls_hourly_$(date +%Y%m%d).log
```

Common checks:

- Check the three GitHub Actions jobs to distinguish selection, Modal, and
  persistence failures.
- Confirm the Modal app is deployed and the `anthropic` secret is attached.
- Check HF Inference Providers quota when containers return 429s.
- Confirm the VPS checkout contains the same database CLI as the workflow.
