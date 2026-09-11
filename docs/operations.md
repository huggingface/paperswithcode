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

Configuration is fail-closed. Production direct apply requires all of:

- `PWC_CODEX_CURATION_SCHEDULER_ENABLED=true`;
- `PWC_CODEX_CURATION_DIRECT_APPLY_ENABLED=true`;
- `PWC_CODEX_CURATION_TRACE_UPLOAD_ENABLED=true`;
- a private, fully qualified `PWC_CODEX_CURATION_TRACE_HF_BUCKET_ID`;
- an immutable curator image: either a registry digest or a content-versioned
  public Docker Space plus its exact 40-character Hub revision;
- pinned model `gpt-5.6-luna`, medium reasoning, and Codex CLI version.

The production image is the public, content-versioned Docker Space
`hf.co/spaces/nielsr/pwc-codex-curator-c0e97b88ca86`, pinned to Hub revision
`7067f309c98f9ea002b812773c9a256400c740ef`. The dispatcher reads the Space
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
`https://huggingface.co/jobs/nielsr/6a8f184e45686a1580c0af9c`; its command
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
