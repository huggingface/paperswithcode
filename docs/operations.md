# Operations & Automation

The global autonomy kill switch, operator controls, alert delivery, budgets,
acceptance gates, and incident procedures are documented in
[autonomous operations](autonomous-operations.md).

## Cron Job Overview

Job implementations live in `.github/workflows/scripts/`, but production never
executes them from a checkout. GitHub Actions invokes the installed
`pwc-cron` launcher, which pins execution to `production/current`, runs as
`pwc-cron`, enforces an allowlist and timeout, and records release provenance.

| Schedule | Script | Purpose |
| --- | --- | --- |
| Every minute (local systemd timer) | `.github/workflows/scripts/hourly/process_curation_thumbnails.py` | Claim remote-curation thumbnail requests and record terminal results as `pwc-cron`. |
| Hourly with randomized delay (packaged, disabled until acceptance) | `.github/workflows/scripts/review_submissions.py` | Launch one pinned, database-free HF Job for at most 25 oldest eligible submissions. |
| Manual dispatch only | `.github/workflows/scripts/hourly/update_hot_github_trending.py` | Staging-ready hot pipeline; production schedule remains intentionally disabled. |
| `0 * * * *` | `.github/workflows/scripts/hourly/update_github_stars.py` | Refresh fresh and weekly official repositories concurrently using separate GitHub accounts. |
| `15 * * * *` | `.github/workflows/scripts/hourly/calculate_trending_scores.py` | Compute EMA-based trending scores using repository star history. |
| `30 * * * *` | `.github/workflows/scripts/hourly/update_citations.py` | Pull citation counts from Semantic Scholar for ArXiv papers. |
| `45 * * * *` | `.github/workflows/scripts/hourly/extract_urls.py` | AI-assisted GitHub/project URL extraction for papers lacking resources. |
| `0 * * * *` | `.github/workflows/scripts/daily/import_hf_daily_papers.py` | Import the current day's Hugging Face submissions not yet in the DB (hourly). |
| `5 * * * *` | `.github/workflows/scripts/hourly/sync_3d_arena.py` | Refresh paper-linked Elo results from the living 3D Arena leaderboard. |
| `55 * * * *` | `.github/workflows/scripts/hourly/sync_tabarena.py` | Refresh paper-linked Elo results from the living TabArena model leaderboard. |
| `15 * * * *` | `.github/workflows/scripts/hourly/sync_open_asr.py` | Discover unambiguous arXiv-backed models and refresh paper-linked WER and RTFx results from the living Open ASR Leaderboard. |
| `18 * * * *` | `.github/workflows/scripts/hourly/sync_open_tts.py` | Atomically refresh paper-linked English and all-language-average WER and RTFx results across Seed-TTS and CV3-Eval from the living Open TTS Leaderboard. |
| `12 * * * *` | `.github/workflows/scripts/hourly/sync_mmeb.py v2` | Refresh paper-linked MMEB-v2 overall scores from the official MMEB Space. |
| `42 * * * *` | `.github/workflows/scripts/hourly/sync_mmeb.py v3` | Refresh paper-linked MMEB-v3 overall scores from the official MMEB Space. |
| `35 * * * *` | `.github/workflows/scripts/hourly/sync_artificial_analysis.py` | Index missing reviewed model releases and refresh paper-linked Artificial Analysis Intelligence, Agentic, and text-to-speech Quality Elo scores. |
| `20 2 * * *` | `.github/workflows/scripts/daily/sync_hf_organizations.py` | Reconcile the strict featured HF organization manifest and append new paper links. |
| `40 3 * * *` | `.github/workflows/scripts/daily/calculate_organization_trending_scores.py` | Snapshot organization momentum and refresh rolling 30-day ranks. |
| `30 4 * * *` | `.github/workflows/scripts/daily/preload_thumbnails.py` | Generate and upload missing paper thumbnails to the HF bucket. |
| `0 5 * * *` | `.github/workflows/scripts/daily/mirror_thumbnails_to_disk.py` | Mirror the entire thumbnail bucket prefix down to the VPS local cache so `/api/thumbnails/{filename}` always serves from local disk. |

Useful production commands:

```bash
sudo pwc-cron status
pwc cron health
pwc cron health refresh_paper_embeddings --strict --json
journalctl -u 'run-u*.service' --since today
```

Remote paper-curation thumbnail requests run through the local
`pwc-curation-thumbnails.timer` and the allowlisted
`process_curation_thumbnails` command. Inspect the timer with
`systemctl status pwc-curation-thumbnails.timer`; retry existing terminal
failures once with:

```bash
sudo pwc-cron process_curation_thumbnails --retry-failed
```

## Autonomous submission reviewer

The packaged `submission-review.timer` invokes the immutable-release
`pwc-cron review_submissions` allowlist once per hour with a randomized delay.
The launcher claims at most 25 oldest pending edits, writes a private signed
manifest under `/var/lib/paperswithcode/autonomous-submissions`, and submits
that manifest as an encrypted secret to one pinned CPU Hugging Face Job. The
remote worker receives no database URL or HF launch credential. It receives
only its dedicated budget-capped OpenAI key and per-claim callback tokens.
The configured Job image must be a Docker reference ending in an exact
`@sha256:` digest; tags and mutable Space URLs are rejected.

Keep both `PWC_AUTONOMOUS_SUBMISSION_ENABLED` and
`PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED` false until Task 15 shadow comparison
and acceptance drills are recorded. The dedicated HF token must only launch
Jobs in the configured namespace; the OpenAI credential must have an external
operator-specific spending limit no higher than the configured run budget.
Neither credential may be shared with paper curation or interactive Codex.
Configure distinct primary and fallback autonomous alert webhooks. A failed
launcher pass, remote startup or timeout, missing callback, or remote cost
limit failure makes the service fail and triggers the content-free
`submission-review-alert.service`; alert payloads contain only environment,
release, severity, and the runbook URL.

Read-only queue preview does not claim or decide anything and remains useful in
manual mode:

```bash
sudo pwc-cron review_submissions --dry-run
```

After acceptance, enable the timer without running the script from a checkout:

```bash
sudo systemctl enable --now submission-review.timer
systemctl status submission-review.timer
sudo pwc-cron status
```

Disable remotely through the admin autonomy control first; for host recovery,
disable the timer and its configuration flag:

```bash
sudo systemctl disable --now submission-review.timer
```

Only one matching remote Job may be active. Each callback is HMAC-bound to its
claim token, immutable snapshot, and exact decision. Exact repeats are safe;
changed, expired, unsigned, or scope-expanding callbacks fail closed. On the
next timer pass, a terminal Job with missing signed callbacks expires only its
claims, exits nonzero for alerting, and can be replayed by running the same
allowlisted command again. Verify deferred taxonomy submissions remain pending
in their existing admin tabs. Launcher, startup, callback, timeout, image-pin,
and capacity failures are systemd failures delivered by autonomous alerting;
the remote provider project enforces the independent cost ceiling.

## Admin Dashboard

- Route: `/admin-dashboard` on the frontend (linked from the admin user menu). The old `/cron-dashboard` URL redirects here.
- Backend endpoints: `/api/v1/cron/status`, `/api/v1/cron/job/{name}`, `/api/v1/cron/health`.
- Codex add-evals/enrich controls and their remote-job queue are intentionally
  disabled during the environment migration. Staging cannot mutate the shared
  catalog and production does not expose the retired write-capable sidecar.
- Auto-refreshes CRON health every 30 seconds (toggleable).
- Pulls production CRON health from
  `/var/lib/paperswithcode/production/cron-logs`.

Use the dashboard to ensure health score stays ≥80%. For command-line
visibility, use `pwc cron health` and `pwc-cron status`.

When building the health report from a developer checkout, point it at the
production log directory; otherwise log-plane evidence (per-job logs and the
content-free chat monitor records) reads as `unknown` and the score drops by
about 15 points for no operational reason:

```bash
PWC_CRON_LOG_DIR=/var/lib/paperswithcode/production/cron-logs \
  uv run --env-file backend/keys.env python -m backend.cli cron health --strict --json
```

Deployed scheduled jobs run through `sudo /usr/local/sbin/pwc-cron <job>` from
the immutable `production/current` release. Use `pwc cron health`, `pwc-status`,
and journald for diagnostics; do not execute scheduled scripts from the
developer checkout. CRON logs live in
`/var/lib/paperswithcode/production/cron-logs` and are retained for 30 days.

### Host timer scheduling

Catalog CRON jobs are scheduled by host systemd timers, not GitHub Actions.
The timer/service pairs are generated from `deploy/cron_schedules.py` into
`deploy/systemd/cron/` (regenerate with `python deploy/generate_cron_units.py`)
and installed by `install_deploy_tools.py`/`install_host_layout.py`. Every
timer sets `Persistent=true`, so missed slots (downtime, reboots) are caught up
on the next activation. Services invoke `pwc-cron-throttled`, which admits at
most `PWC_CRON_THROTTLE_SLOTS` (default 3) concurrent launches through slot
locks in `/run/paperswithcode/cron-slots` before delegating to the immutable
`pwc-cron` launcher; producer chains additionally declare `After=` orderings
for catch-up storms. The former GitHub `schedule:` triggers were removed; the
workflows stay `workflow_dispatch`-only for manual recovery. Enable or inspect
a job's schedule with `systemctl status pwc-cron-<job>.timer`; list all with
`systemctl list-timers 'pwc-cron-*'`.

Environment deployment, rollback, nginx, backup, and release layout are
documented in [deployment.md](deployment.md).

### Paper Markdown continuation and MCP health

`GET /api/v1/research/papers/{paper_id}/read` without query parameters retains
the legacy bounded response and may append its truncation notice. Supplying
`offset`, `limit`, or `content_version` selects byte-chunk mode. Offsets and
limits count stored UTF-8 bytes, not characters; `limit` is at most 262,144.
The first request defaults to offset zero. Continue a nonterminal response with
both `X-PwC-Next-Offset` and the opaque `X-PwC-Content-Version` returned by the
server. A nonzero offset without that version is rejected.

Chunk responses are `200 text/plain` with `X-PwC-Truncated`, the content version,
and a next offset only when more bytes exist. An offset exactly at EOF is an
empty terminal success. Invalid syntax is `422`, a stale version is `409`, an
invalid byte boundary/range is `416`, missing Markdown is `404`, and storage
failure is `503`; error responses are `no-store`. Unversioned first chunks must
revalidate, while version-bound immutable chunks may be cached for one hour.
Modern arXiv identifiers (version suffixes normalize to the stored base paper)
and numeric external-paper IDs are supported. Do not promise historical arXiv
versions or stored reads for legacy papers that have not been migrated.

The backing objects are immutable SHA-256-addressed Markdown selected by a small
per-paper manifest. Writers publish content before the manifest and honor the
migration lock. Run the migration in bounded dry-run batches first; never delete
old content objects while a one-hour continuation cursor could still reference
them. The request path performs bounded reads and strict UTF-8 validation rather
than downloading a whole paper.

For MCP operations, start with `pwc-status --component mcp` and inspect
`journalctl -u paperswithcode-mcp@staging.service` (or `production`). Operational
MCP telemetry is limited to tool name, status, latency, response bytes, protocol
label, and server version. It must not contain query text, paper IDs, cursors,
resource URIs, raw IPs, authorization, or bodies. The upstream catalog remains a
separate service with its own logs. Deployment, key rotation, nginx cutover,
qualification, and rollback instructions are in [deployment.md](deployment.md).

Blue/green deployments record every pointer mutation in
`environments/<environment>/activation-journal.json`. If `pwc-status` reports
`live-with-old-slot-draining`, do not restart or kill the old service; run
`sudo pwc-reap <environment>` later. It stops a slot only after both chat and
gateway stream counts are zero and then removes only unreferenced releases and
runtimes. A journal phase ending in `smoke-pending` or
`automatic-rollback-in-progress` is an incident requiring pointer and public
smoke inspection before another deployment.

## Trending Pipeline

Once production activation is separately authorized, queue ownership is
exclusive: the 15-minute hot job owns latest papers aged
0–30 days (500 calls/run), the hourly fresh queue owns days 31–180 (2,500
calls/run), and the weekly queue owns older repositories (1,000 calls/run).
The 30-day ownership boundary is intentionally fixed across selection and
health checks; it is not an environment override.
`PWC_GITHUB_TOKEN_HOT` is optional in
`/etc/paperswithcode/production-cron.env`; when absent, hot requests use
`PWC_GITHUB_TOKEN` and preserve a 500-call reserve.

Rotate only the production CRON copy from the already-protected application
environment, then let the next invocation load it without exposing the value:

```bash
sudo python /srv/paperswithcode/environments/production/current/deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-cron-github-only \
  --confirm ROTATE_PRODUCTION_CRON_GITHUB
```

The updater emits queue-specific credential and fetch counters. A selected
fresh or weekly queue with zero successful GitHub responses fails the workflow;
the admin dashboard reports the affected credential name and queue while never
returning the token value.

1. `update_hot_github_trending.py` is the targeted path that snapshots hot repositories, calculates their
   EMA scores, and updates only their linked latest papers in the same run.
2. `update_github_stars.py` snapshots the fresh and weekly queues into
   `repository_star_history`.
3. The hourly `calculate_trending_scores.py` and
   `calculate_paper_trending_scores.py` jobs reconcile the full populations.
   Targeted paper writes still normalize against the full live GitHub/HF corpus.
4. Database views and `/api/v1/papers/trending` expose the resulting scores.

```bash
curl "http://localhost:8000/api/v1/papers/trending?limit=10&max_age_days=180"
```

Response snippet:

```json
{
  "paper_id": "51998",
  "arxiv_id": "2507.15061",
  "title": "WebShaper: Agentically Data Synthesizing…",
  "date_published": "2025-07-20",
  "repository": {
    "url": "https://github.com/Alibaba-NLP/WebWalker",
    "owner": "Alibaba-NLP",
    "name": "WebWalker",
    "num_stars": 15549
  },
  "trending": {
    "velocity_24h": 2.143,
    "trending_score": 0.326,
    "stars_gained_24h": 66
  }
}
```

Frontend integration (`frontend/src/pages/Papers.tsx`) uses the dedicated endpoint when users select the 🔥 Trending tab without a search query, and gracefully falls back to `/papers` plus sort options for mixed queries.

The checked-in workflow is `workflow_dispatch`-only. A merge to `main` or a
staging deployment does not activate production, and the installed
`/usr/local/sbin/pwc-cron` will not recognize this command until deploy tooling
from the authorized production SHA is installed.

Production activation requires a separately authorized and reviewed sequence:

1. Install the checked-in deploy tooling from the exact authorized production SHA.
2. Deploy that same SHA to production so the immutable release contains the job.
3. Verify `sudo pwc-cron status` lists `update_hot_github_trending`.
4. In a separate reviewed commit, add the `*/15 * * * *` schedule to
   `cron-update-hot-github-trending.yml`.

After those steps, recovery and selection-only checks are:

```bash
pwc cron health update_hot_github_trending --strict --json
sudo pwc-cron update_hot_github_trending --dry-run
```

The dry run prints the bounded selected population and projected shared-token
calls without GitHub requests or database writes. Disable the schedule to roll
back; snapshots are retained. If it stays disabled, restore hot papers to the
hourly fresh ownership before releasing that rollback.

The hourly paper reconciliation also supports temporary, linearly decaying
emergency floors. Configure comma-separated `identifier:decay_hours` entries in
the production CRON overlay (hours default to 72):

```dotenv
PWC_TRENDING_PIN_ARXIV_IDS=2606.16140:72
PWC_TRENDING_PIN_PAPER_IDS=104054:72
```

The paper-ID form supports external papers without an arXiv ID. Both forms
share the persisted pin state and decay behavior. The CRON worker stores that
state in its writable lock directory so immutable releases remain read-only.
Use pins only as a bridge while the underlying ranking signal is corrected.

## PDF Validation for URL Extraction

- Helper: `_is_valid_pdf` in `backend/utils/pdf_utils.py`
- Ensures downloaded files start with `%PDF-`, contain `%%EOF`, exceed 1 KB, and are not HTML/reCAPTCHA placeholders.
- Critical errors (rate limiting, CAPTCHA) are surfaced so papers are retried later instead of being marked as processed.
- Unit tests: `tests/test_pdf_validation.py`, integration tests: `tests/test_pdf_download_integration.py`.

## Thumbnail Storage

The browser always loads paper previews through `/api/thumbnails/{filename}`.
Production can store generated JPEGs in a private Hugging Face Storage Bucket by
setting:

```bash
PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket
PWC_THUMBNAIL_HF_BUCKET_ID=huggingface/pwc-thumbnail
PWC_THUMBNAIL_HF_BUCKET_PREFIX=thumbnails
PWC_HF_TOKEN=<token with bucket access>
```

Use a dry run before uploading the current VPS cache:

```bash
uv run --env-file backend/keys.env scripts/sync_thumbnails_to_hf_bucket.py --create-bucket
uv run --env-file backend/keys.env scripts/sync_thumbnails_to_hf_bucket.py --create-bucket --apply
```

After spot-checking `/api/thumbnails/...`, the old `thumbnails/` directory can be
removed from the VPS because the bucket is the durable copy. The backend keeps a
small `PWC_THUMBNAIL_TEMP_CACHE_DIR` for recently served bucket objects.

### Local disk mirror

The thumbnail bucket is **private**, so the browser cannot fetch images directly
from `huggingface.co/buckets/...`; every `<img src="/api/thumbnails/...">`
request has to go through FastAPI. To keep that fast, the daily
`mirror_thumbnails_to_disk` cron runs `huggingface_hub.sync_bucket` to
incrementally pull the entire bucket prefix into `PWC_THUMBNAIL_TEMP_CACHE_DIR`
on the VPS. Once the mirror finishes, `ThumbnailService` finds every requested
file on local disk and never has to do a per-request HF download. To run it
manually (e.g. for first-time bootstrap):

```bash
sudo pwc-cron mirror_thumbnails_to_disk
```

## Troubleshooting Checklist

| Issue | Resolution |
| --- | --- |
| Trending endpoint empty | Verify GitHub stars job is running and trending scores have at least two snapshots; check `repositories.trending_score_updated_at`. |
| Cron dashboard shows “Unknown” | Run `pwc-cron status`, inspect `/var/lib/paperswithcode/production/cron-logs`, and check the matching GitHub Actions run. |
| AI URL extraction stalls | Inspect production CRON health and the matching immutable-release job logs; do not rerun it from the checkout. |
| Pending edits not landing in DB | Confirm the submitter is signed in (HF session cookie); the `POST /api/v1/me/paper-edits` endpoint requires `require_user`. Then run `SELECT * FROM pending_paper_edits WHERE status='pending' ORDER BY created_at DESC LIMIT 10;` to inspect recent submissions. |

## Pending Paper Edits Review

Non-admin Hugging Face users submit edits to the paper-page surfaces (tasks,
methods, evaluations, GitHub repositories, project pages) through
`POST /api/v1/me/paper-edits`. The submission lands in the
`pending_paper_edits` table with `status = 'pending'`; live data does not
change until an admin approves it. Admin direct edits via the existing
`/papers/{id}/...` and `/evaluations/...` admin endpoints still bypass this
queue. The frontend admin queue UI is intentionally deferred — review and
approval happens through SQL plus the admin API.

### List pending submissions

Run this against the production DB to surface the current review queue:

```sql
SELECT id,
       paper_id,
       hf_username,
       is_author,
       edit_type,
       created_at,
       jsonb_pretty(proposed_payload) AS proposed_payload,
       jsonb_pretty(current_payload)  AS current_payload
FROM pending_paper_edits
WHERE status = 'pending'
ORDER BY created_at DESC;
```

For a quick triage view:

```sql
SELECT id, paper_id, hf_username, is_author, edit_type, created_at
FROM pending_paper_edits
WHERE status = 'pending'
ORDER BY created_at DESC;
```

You can also ask the agent to surface pending edits — it will run the same
query and summarize the diff between `current_payload` and `proposed_payload`
for you.

### Approve or reject via the admin API

Both endpoints require the HF admin cookie (sign in via the site) or the
`X-Admin-Token` header. Approval re-uses the same backend mutation services
that admin direct edits call, so a future "auto-approve author edits" hook can
reuse the exact same code path. Reject simply records the row as rejected with
an optional note; it does not touch live data.

```bash
# Approve
curl -X POST \
    -H "X-Admin-Token: $PWC_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"admin_note": "looks correct"}' \
    https://paperswithcode.co/api/v1/admin/paper-edits/{edit_id}/approve

# Reject
curl -X POST \
    -H "X-Admin-Token: $PWC_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"admin_note": "task tag was incorrect"}' \
    https://paperswithcode.co/api/v1/admin/paper-edits/{edit_id}/reject
```

`GET /api/v1/admin/paper-edits` lists rows server-side (status / paper_id /
edit_type filters supported) and `GET /api/v1/admin/paper-edits/{id}` returns
a single row including both payloads.

Approved/rejected rows stay in the table for auditing; the same SQL query
with `status = 'approved'` or `status = 'rejected'` shows historical
decisions along with `reviewed_by` and `reviewed_at`.

### Apply an evidence-backed Codex review

The repository CLI can apply a Codex approval or rejection through the same
locked, validated mutation service as the admin API. It requires an explicit
environment, confirmation token, UUID review-run identifier, and a review
artifact of at most 128 KiB. Terminal decisions additionally require at least
one source, numeric confidence of at least `0.9`, no unresolved questions, and
`reviewed_revision` equal to `sha256:<pending_paper_edits.payload_hash>`.

```bash
PWC_ENVIRONMENT=production uv run --env-file backend/keys.env \
  pwc submissions decide {edit_id} \
  --environment production \
  --decision approve \
  --resolved-payload-file /path/to/resolved-payload.json \
  --review-file /path/to/review.json \
  --review-run-id {uuid} \
  --confirm APPLY_SUBMISSION_REVIEW \
  --json
```

The resulting row records `reviewed_by_kind = 'codex'`, the model, run ID,
full evidence artifact, and resolved payload. Approvals also append the normal
catalog mutation event. Repeating the exact run is idempotent; a stale revision,
different terminal decision, or already-reviewed row fails closed.

### Payload shapes

Each `proposed_payload` matches the underlying admin mutation endpoint:

- `tasks` &rarr; `{"task_ids": [int, ...]}`
- `methods` &rarr; `{"method_ids": [int, ...]}`
- `repositories` &rarr; `{"repositories": [{"url": str, "is_official": bool}, ...]}`
- `project_pages` &rarr; `{"project_pages": [{"url": str, "is_official": bool}, ...]}`
- `evaluations` &rarr; `{"operations": [{"op": "create" | "update" | "delete", ...}, ...]}`
  - `create` &rarr; `{ "op": "create", "data": { task_id, dataset_id, metrics, best_metric, ... } }`
  - `update` &rarr; `{ "op": "update", "evaluation_id": int, "data": { ... } }`
  - `delete` &rarr; `{ "op": "delete", "evaluation_id": int }`
| Cron logs filling disk | Verify `systemd-tmpfiles` policy; production CRON logs are bounded to 30 days. Use `pwc-status` to include disk usage in the audit. |

_Last updated: 7 November 2025_
## One-time evaluation Hugging Face metadata backfill

Existing evaluation metadata can be reviewed with the bounded, fill-only command
below. It defaults to dry-run, never derives counts from model names, and only
uses a matched repository's `safetensors.total` value. Review the JSON report
(including conflicts and unavailable repositories), then rerun with its exact
`proposal_hash` to apply. This command is not scheduled: the daily paper-
curation workflow remains responsible for metadata on newly imported
evaluations.

```bash
uv run --env-file backend/keys.env python \
  backend/database/evaluations_setup/backfill_hf_evaluation_metadata.py

uv run --env-file backend/keys.env python \
  backend/database/evaluations_setup/backfill_hf_evaluation_metadata.py \
  --apply --proposal-hash <reviewed-proposal-hash>
```

## Autonomous HF daily-paper curation

### Enrichment dashboard export

The private Hugging Face Space at
`https://huggingface.co/spaces/nielsr/pwc-enrichment-dashboard` reads its
latest snapshot from the private dataset
`nielsr/pwc-enrichment-dashboard-data`. The daily
`export_enrichment_dashboard` job rebuilds the complete historical snapshot
from production curation jobs, evaluations, and benchmark-gap evidence, then
uploads it to the dataset. A manual backfill or verification can be run with:

```bash
sudo pwc-cron export_enrichment_dashboard
```

The Space never connects directly to PostgreSQL. Keep
`PWC_ENRICHMENT_DASHBOARD_REPO_ID` and the write-capable `PWC_HF_TOKEN` only in
the production CRON environment; the Space uses its own read-only download
secret.

The reconciler runs hourly at minute `27` through the installed immutable-release
launcher. Besides discovering new daily-paper cohorts, each pass requeues papers
whose canonical Markdown has appeared since an earlier curation attempt:

```bash
sudo pwc-cron enqueue_hf_daily_paper_curation --dry-run
sudo pwc-cron enqueue_hf_daily_paper_curation
sudo pwc-cron enqueue_hf_daily_paper_curation --status
```

Trending-model discovery is a separate hourly lane. It reads the global Hub
top 50 through the installed `hf` CLI, deterministically skips obvious model
conversions, and queues at most ten new or changed substantive releases per
cycle. Each accepted release runs the normal enrich-paper then add-evals
workflow; benchmark matching remains restricted to the existing catalog.

```bash
sudo pwc-cron enqueue_hf_trending_model_curation --dry-run --max-queued 10
sudo pwc-cron enqueue_hf_trending_model_curation --max-queued 10
sudo pwc-cron enqueue_hf_trending_model_curation --status
```

The first command is the release canary discovery pass and makes no database
changes. The scheduled command runs at minute 42, shares the daily curation
health/token guardrails, and prioritizes trending work behind only overdue
daily workflows. Model-card revisions are pinned; a changed README is curated
again, while rejected repackaging stays durable until the card changes.

It scans the exact rolling seven-day Hugging Face daily cohorts, records missing
imports, creates one durable parent workflow per paper, and uses the shared
admin/scheduled queue. Each workflow runs `enrich-paper` before `add-evals`.
Scheduled work may use three of four global slots; one remains reserved for
admin work. The first production run is capped at ten workflows until every
canary reaches a successful terminal state. The nonterminal scheduled backlog
is capped at 200, with overflow recorded as durable deferred workflows.
The importer durably records HF daily membership in
`papers.hf_daily_featured_on`; reconciliation also records membership from the
live feed and retains unfinished daily papers after they leave the seven-day
window. Daily work must finish both enrichment and evaluation curation before
conference backfill can be admitted or dispatched. Failed, deferred,
awaiting-Markdown, and imported-but-not-yet-queued daily papers all block
backfill. A completed no-evaluations audit counts as completed curation.

Queued backfill workflows are parked to free admission capacity while preserving
their existing job rows. Running work is allowed to finish, but subsequent
background stages wait. Daily jobs use priority 10; backfill uses priority 100.
The old overdue-work allowance applies only once no daily papers remain
unfinished. Operators must resolve failed daily work rather than bypassing this
gate by increasing worker count.

Apply `backend/database/migrations/add_hf_daily_featured_on.sql` before deploying
this scheduler or importer. The additive nullable column is compatible with the
previous release. Bootstrap existing daily membership from official HF daily
cohorts covering the curation history; never infer membership from conference
absence or the shared legacy `hf-daily-cron` trigger.

Configuration is fail-closed. Production direct apply requires all of:

- `PWC_CODEX_CURATION_SCHEDULER_ENABLED=true`;
- `PWC_CODEX_CURATION_DIRECT_APPLY_ENABLED=true`;
- `PWC_CODEX_CURATION_TRACE_UPLOAD_ENABLED=true`;
- a private, fully qualified `PWC_CODEX_CURATION_TRACE_HF_BUCKET_ID`
  (each trace bundle uploads from a short-lived subprocess, because the
  `hf_xet` runtime never returns its memory to a long-lived API worker);
- an immutable curator image: either a registry digest or a content-versioned
  public Docker Space plus its exact 40-character Hub revision;
- pinned model `gpt-5.6-luna`, medium reasoning, and Codex CLI version.

The production image is the public, content-versioned Docker Space
`hf.co/spaces/nielsr/pwc-codex-curator-87ebc81c234c`, pinned to Hub revision
`556b5d14b762684586030d3018999dae392200c9`. The dispatcher reads the Space
revision before every launch and pauses daily dispatch if it differs. Never
update a versioned curator Space in place: publish a new Space whose suffix is
the first 12 characters of the runner SHA-256, record its exact Hub revision,
run a standalone Jobs capability probe, then update both
`PWC_CODEX_JOBS_IMAGE` and `PWC_CODEX_JOBS_IMAGE_REVISION`. A mutable registry
tag such as `latest` is never valid for scheduled production dispatch.

After publishing and probing the replacement Space, install only its image pin
without rewriting the protected Codex credentials:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-codex-image-only \
  --confirm UPDATE_PRODUCTION_CODEX_IMAGE

sudo pwc-deploy production <exact-main-sha> --confirm DEPLOY_PRODUCTION
```

Use the exact new source SHA that records the image pin. If that SHA is already
the active release, apply the protected environment through the same qualified
path with `--refresh-environment` instead.

The current image probe is recorded at
`https://huggingface.co/jobs/nielsr/6aa7ca705527934177edd5e7`; its command
checks the Codex version, PyPDF2 version, full runner SHA-256, exact model, and
scoped callback-token inheritance. The public Space avoids Docker Hub and does
not require personal GitHub Packages access.

The private application repository credential is never sent to a remote job.
After authenticating with its paper-scoped callback token, the runner downloads
only the three curation skills, scoped API helper, proposal schema, and URL
preflight module from the active immutable release. Every file is SHA-256
verified and the bundle revision must equal the dispatched repository SHA.

Pause and recovery are scoped to scheduled dispatch; admin jobs remain
available:

```bash
sudo pwc-cron enqueue_hf_daily_paper_curation --disable-dispatch \
  --reason "operator investigation"
sudo pwc-cron enqueue_hf_daily_paper_curation --enable-dispatch
```

Scheduled curation has a separate `curation` autonomous operator. Enabling or
disabling the submission reviewer does not grant or revoke curation writes.
Before enabling scheduled dispatch, the curation operator must be enabled from
the admin autonomous-operations control plane after recording acceptance
evidence for `dispatcher_preflight`, `capability_isolation`,
`callback_idempotency`, and `paused_callback_apply`; the dispatcher performs the
same policy check before allocating a remote job and pauses with
`autonomous_policy_denied` if it would be rejected. Pausing scheduled dispatch
does not disable the curation operator, so callbacks from jobs already in flight
can finish. Use the global manual-mode control or disable the curation operator
only when already-running callbacks must also fail closed.

Existing installations must apply
`backend/database/migrations/add_curation_autonomous_operator.sql` before
deploying source that uses this operator. The migration adds the disabled
control row and expands only the autonomous operator constraints; it does not
enable curation or release scheduled dispatch.

Retry a terminal scheduled stage by its durable job UUID through the same
allowlisted queue. Operator retries use priority 50 (ahead of ordinary daily
work but behind priority-0 admin jobs), and repeating the command for an already
queued retry promotes that row without duplicating it. This command refuses
admin-triggered jobs:

```bash
sudo pwc-cron enqueue_hf_daily_paper_curation --retry-job <job-uuid>
```

To launch one explicit queued daily or trending canary while normal dispatch
remains paused by an explicit operator action, use its durable job UUID. This
command rechecks the token guardrail and shared capacity, dispatches only the
selected row, and never resumes the scheduler:

```bash
sudo pwc-cron enqueue_hf_daily_paper_curation --canary-job <job-uuid>
```

For a terminal daily job, first use `--retry-job` and then pass the returned
queued retry UUID to `--canary-job`. Admin jobs and non-queued rows are rejected.
The command exits nonzero if the remote job does not reach the running state.

Replay a saved proposal through the currently deployed callback validators
without applying writes. The command reports current policy validity and
isolated benchmark-gap rejections and exits nonzero when the mutation proposal
is invalid:

```bash
sudo pwc-cron enqueue_hf_daily_paper_curation --validate-job <job-uuid>
```

Queued stages that have not started are rebound at dispatch to the exact active
immutable release, including its repository SHA, skill hash, model, CLI,
validator metadata, and hash-validated allowlisted bootstrap bundle. The bundle
is stored on the durable job before launch, so a later deployment cannot break
the remote bootstrap handshake. Running and terminal attempts are never
rebound.

The admin dashboard groups stages under the parent paper workflow and exposes
retry, cancel, pause/resume, URL-candidate provenance, proposals, validator
findings, usage, reports, and private trace URIs. It warns at a three-hour queue
age and becomes critical at five hours. Scheduled dispatch automatically pauses
after a server invariant breach, three consecutive trace/apply/verification
failures, a greater-than-20% non-source failure rate in the latest 25 stages, or
the post-baseline daily token guardrail. Resuming is an explicit acknowledgement
that resets the consecutive counters and starts a fresh 25-stage failure-rate
window; a recurring invariant breach still pauses immediately.

Trace finalization retries storage without rerunning Codex or rolling back an
accepted catalog mutation. To replay a cohort without writes, set direct apply
false and run the reconciler with an explicit date/limit. Validator replay uses
the persisted `proposal` and current callback validators. Revert a bad scoped
mutation through the existing paper/evaluation admin surfaces using the stored
before-state/diff; there is intentionally no broad automatic restore button.

Benchmark gaps remain review-only until an administrator configures the exact
existing task, dataset, and leaderboard metric. The dashboard promotion action
then marks the candidate promoted and idempotently requeues only its evidence
papers as `add-evals`; it never creates taxonomy, datasets, metrics, or
leaderboards. Thumbnail generation and citation/reference tagging remain
separate workflows.

Scheduled enrichment preserves every repository and every manual or
unknown-source project page. It may remove an importer-written `hf_api` project
page only after a complete URL search and a URL-specific recorded reason that
the checked page is generic or unrelated to the paper. A rejected removal pauses
only that stage for review; it does not halt the daily queue. Unexpected
callback/runtime faults still pause scheduled dispatch, while the trace report
preserves the rejected proposal and reason for operator review.

Apply `backend/database/migrations/add_autonomous_paper_curation.sql` before the
first release that enables the scheduler. Thumbnail generation and the
citation/reference method linker remain separate jobs and are not dependencies
of this workflow.

## Durable chat sessions (staging)

Chat content is private user data. PostgreSQL is the live source of truth;
opaque Agent SDK transcripts are stored separately from the sanitized UI
projection. Never print message content or transcript JSON in operational
checks. User-confirmed deletion removes live rows immediately; verified
disaster-recovery backups expire under the normal 30-day remote rotation and
are not a product undo mechanism.

Before enabling durable chat, confirm the backup target reports `"private":
true` and is organization-owned. The daily backup service receives its
organization-authorized bucket credential only through
`production-cron.env`; neither application identity can read that overlay. The
target is selected with `PWC_POSTGRES_BACKUP_BUCKET`.

Content-free storage checks:

```bash
df -h /
sudo -u postgres psql -d paperswithcode_hf -c "
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname LIKE 'chat_%'
ORDER BY pg_total_relation_size(relid) DESC;"
sudo -u postgres psql -d paperswithcode_hf -c "
SELECT count(*) AS sessions,
       sum(message_count) AS messages,
       pg_size_pretty(avg(transcript_bytes + projection_bytes)::bigint)
         AS average_logical_bytes
FROM chat_sessions;"
```

Treat filesystem use at or above 85%, any `transcript_status='degraded'`, or a
recovery-spool entry as an alert. The recovery spool is private, bounded by
`PWC_CHAT_RECOVERY_SPOOL_MAX_SESSIONS`, and exists only to reconcile SDK mirror
failures; it is not a second session store.

### Chat execution-limit recovery

The default eight-model-turn contract permits at most six executed research
tool-use rounds and twelve individual tool calls. Parallel calls in one
assistant response consume one round and multiple call slots. A policy denial,
hard tool/search limit, 429, explicit execution limit, or open web-search
failure circuit closes tooling for that research phase. If the SDK nevertheless
ends at `max_turns`, the worker may make one same-session, tool-free finalizer
request (`max_turns=1`) only when at least ten seconds remain on the original
turn deadline. Successful recovery remains an ordinary `finish_reason=success`;
failed bounded recovery retains `tool_limit` or an existing actionable provider
error.

Operational logs and chat traces record only counts, outcomes, request/token
usage, and latency. Search for `chat execution recovery` and aggregate
`execution_limit_reached`, `finalizer_outcome`, and the round/call fields. Never
log prompts, URLs, tool inputs/results, answers, credentials, or transcript
bodies. Useful staging aggregates are raw limit rate, recovered-limit rate,
visible `tool_limit` rate, finalizer latency/request/token overhead, and denied
attempts after closure. The initial implementation intentionally adds no
database migration; introduce durable latency columns only after a separate
review demonstrates that structured logs and traces are insufficient.

## Persistent chat executor transport

The persistent executor transport is default-off in both environments. A
feature PR stops after local verification. Only the designated publishing task
may install these units, use `pwc-nginx`, or publish to staging after the PR is
merged and Cursor Bugbot and required checks are clear. Production needs
separate explicit authorization and must reuse the exact staging-qualified
commit and artifact digests; never rebuild between environments.

Before starting a staging candidate, apply the executor migrations in this
order with PostgreSQL `search_path=staging,public`:
`add_chat_executor_registrations.sql`, `add_chat_turn_reservations.sql`, then
`add_chat_executor_transport_circuit.sql`. Each script is transactional,
refuses schemas other than `staging` or `public`, assigns environment-specific
ownership and grants, and revokes the opposite application role. Verify all
twelve tables are owned by `pwc_staging_owner`, that `pwc_staging` has the
declared access (the rollback audit remains insert/select only), and that
`paperswithcode_user` has none. An application deployment never applies these
migrations.

Each service generation is addressed as `<environment>/<positive-generation>`.
Escape that path with `systemd-escape --path` and start matching rendezvous and
harness instances. Their only listeners are
`/run/paperswithcode/<environment>/<generation>/chat-executor-rendezvous.sock`
and `chat-executor-harness.sock`. Nginx exposes only
`/v1/generations/<generation>/environment` on the environment's dedicated TLS
1.3 hostname and rewrites it to the rendezvous daemon's internal
`/v1/environment` route. No executor TCP listener is permitted. The sandbox
outbound policy contains exactly the applicable hostname; the pinned Modal SDK
and Rust client validate normal public WSS certificates and that exact host,
port, and generation route.

Provision root-owned configuration beneath
`/etc/paperswithcode/chat-executor/<environment>/<generation>/` with mode 0750
on directories and 0600 on credential sources. Install database, admission
signing, harness Noise, and authorization signing keys as distinct systemd
credentials. Never place key bytes in an environment file, command line,
diagnostic, journal query, or ticket. The service units bound file descriptors,
memory, tasks, restart rate, startup, and the 240-second stop drain; their
`--self-test` and Unix-socket probes are the local liveness and readiness gates.
The non-secret `service.env` contains exactly
`PWC_CHAT_EXECUTOR_BACKEND_GROUP=pwc-production` or `pwc-staging`; the harness
configuration independently pins the matching backend UID.

Before starting a generation, render the two bounded JSON files from the
qualified release manifest. `rendezvous.json` has exactly
`shard_database_id`, `allowed_backend_uid`, `allowed_harness_uid`,
`current_protocol_version`, `current_key`, and optional `previous_key` fields;
each key object has `key_id`, URL-safe-base64 `public_key`,
`not_before_ms`, and `not_after_ms`. `harness.json` has exactly
`allowed_backend_uid`, `expected_rendezvous_uid`, `protocol_version`,
hex `schema_digest`, `authorization_key_id`, `authorization_not_before`, and
`authorization_not_after` (authorization times are Unix seconds). Resolve the
three service-account UIDs from the host immediately before rendering; do not
reuse the backend UID for the harness UID. The environment receives the
matching authorization public-key document with exactly `current` and optional
`previous` objects (`key_id`, standard-base64 `public_key`, `not_before`, and
`not_after`, also in Unix seconds).

When staging activation is authorized, install a backend systemd drop-in that
loads the distinct admission-signing credential and sets
`PWC_CHAT_EXECUTOR_ADMISSION_SIGNING_KEY_FILE` to its `%d/…` path. Keep that
drop-in absent while the feature is disabled so a missing candidate credential
cannot prevent the existing backend from starting. Validate the drop-in and
credential path in staging before enabling the flag.

The harness and environment retain the inner stream's Noise identities,
ordered-frame receiver state, and bounded replay buffers across a rendezvous
socket replacement. Resume rekeys the physical path, exchanges exact
acknowledgement positions, and replays only unacknowledged frames; the fixed
30-second recovery attempt never reissues an executor command. A lost initial
registration response may recover at most three times with the same launch or
reconnect nonce and the already-proven environment identity. Harness or
environment process loss cannot use this path and must fence and reconcile the
turn with a typed transport failure.

Turn admission prices and atomically reserves the selected server-funded
provider's full request/token envelope together with the sandbox lifetime
envelope. It records the resource window independently of terminal chat state.
Model-only turns return their unused sandbox reserve after adding settled
provider usage. A turn whose workspace end or provider usage is not yet proven
becomes `cost_unknown`, releases only concurrency, and retains spend until the
provider ledger and release or termination evidence settle the combined cost
exactly once.

Rendezvous loss marks claimed registrations suspect without destroying their
durable claim. The same environment identity may restore `claimed` state only
inside 30 seconds; a one-second bounded reconciler fences expired suspect
registrations and invalidates their active claims with
`transport_recovery_expired`.

For an ordinary blue/green service release:

1. Build the exact merged source once and record the commit, Rust/Python/image
   digests, protocol version, schema digest, and signing-key IDs. Start the new
   fenced generation without changing the active database route.
2. Require registry connectivity, fresh authenticated ready capacity, local
   self-tests, both socket probes, and a canary Noise exchange. If any check
   fails, stop the candidate; the old shard remains wholly active.
3. Atomically activate the replacement shard in PostgreSQL. New launch tokens
   now contain its positive generation and URL. Existing connections and
   claims remain pinned to the old, now-draining shard.
4. Drain for exactly 240 seconds. At cutoff, commit
   `fence_drained_shard` first: it marks the shard fenced, removes readiness,
   and settles every residual active claim as `service_restarted`. Only after
   that transaction commits may the old processes receive SIGTERM. They unlink
   listeners, allow existing connection tasks the bounded drain, then exit.
   Never replay an uncertain operation.
5. Reconcile registrations, claims, operation settlements, capacity, and alert
   outbox records. Retain content-free generation/digest/timing evidence.

`pwc-nginx` remains the only supported nginx application interface. It runs the
static validator and `nginx -t` before reload, restores the prior file on smoke
failure, and verifies the active application release. A certificate renewal or
nginx reload must be rehearsed with established WebSockets: accepted evidence
is either uninterrupted streams or bounded reconnect to the same generation,
never a mixed-generation resume. Do not edit `/etc/nginx` directly.

Rotate every executor private key within 30 days. Publish and verify the new
public identity first, record activation time and key ID, and permit only the
immediately previous public key for at most 24 hours. Replace environments
still using the old key, then fence their generations before removing the old
verification key. A failed rotation keeps the old generation active only while
it remains inside that overlap; restore the last qualified configuration and
repeat with a fresh key rather than extending the window.

Routine protocol releases accept only `N` and `N-1`. Record activation
timestamps and exact schema digests; `N-1` expires no later than 24 hours after
activation and its remaining environments are fenced and replaced. Log only
bounded version/digest/reason diagnostics for downgrade rejection. An
incompatible or security release permits no `N-1` attach, resume, or drain
overlap and fences immediately.

For suspected key compromise, identify the exact displayed key ID and invoke
the root-only revocation command with its exact-ID confirmation. Revocation
opens the security hold, fences bound generations, emits the incident alert,
terminates affected environments, and audits uncertain operations without
replay. Install clean credentials, rotate every related key, and clear the hold
only after revocation persistence, alert delivery, reconciliation, clean
generation readiness, and a canary succeed. Preserve bounded audit evidence;
never record key material or chat content.

The operational monitor classifies breaker open, reopen, recovery, and security
hold as distinct content-free events. Primary and fallback webhooks must both
be configured and different; immediate delivery uses primary, while the minute
monitor retries and falls back. If durable admission storage is healthy, new
ordinary turns use the separately persisted legacy transport while the remote
breaker is unavailable. If storage itself is unavailable, both paths return
the retryable dual-path `chat_unavailable` response before work.

Rollback starts by setting
`PWC_CHAT_EXECUTOR_REMOTE_TRANSPORT_ENABLED=false` for new turns. Existing
turns retain their recorded transport until settled or reconciled. If legacy
behavior is not restored, roll back the exact application release with
`pwc-rollback`. This single VPS remains an availability boundary: loss of the
host can interrupt both local executor services even though Modal environments
remain isolated.

### Evaluation verification issues

The hourly `create_eval_verification_issues` job (minute 52 UTC) requests author
verification after native evals settle. It runs independently of daily enrichment,
groups papers by official repository, preserves outreach exclusions, and records
idempotent publication state outside release directories. See the
[issue workflow](agents/issue-tracker.md#scheduled-evaluation-outreach) for limits,
preview/status commands, retry behavior, and rollout requirements.
