---
name: update-ai-deadlines
description: Update, audit, or fix the AI conference deadlines on paperswithcode.co/ai-deadlines. The database is the source of truth, kept current by off-box Claude research agents (weekly and daily sweeps on Hugging Face Jobs). Use whenever the user asks to update or refresh the deadlines page, check whether deadlines are current or missing, add a newly announced conference edition or call for papers, research specific conferences now, apply a finished sweep early, fix a wrong deadline, or investigate why a conference is missing or stale on /ai-deadlines — even when they mention the old huggingface/ai-deadlines repo. Not for conference pages and accepted-paper imports (use add-conference).
metadata:
  compatibility: Requires the paperswithcode repository, uv, backend/keys.env database access, sudo for pwc-cron, and /etc/paperswithcode/production-cron.env for Hugging Face Job credentials when launching, inspecting, or replaying sweeps.
---

# Update AI conference deadlines

`/ai-deadlines` is generated from the `conferences` and `conference_deadlines`
tables. The upstream huggingface/ai-deadlines YAML repo is not a data source. Don't
edit YAML or open PRs there. Change data only through the paths below. Sweeps
and replays go through the guarded writer: it never deletes, past editions and
past deadlines are immutable, and every edit leaves a catalog audit event with
before/after snapshots. The admin endpoint (step 6) replaces an edition's whole
deadline list and is audited the same way.

## How the pipeline works

| Piece | Where |
|---|---|
| Weekly sweep (Sun ~02:35 UTC): series with nothing upcoming whose next cycle is due within ~8 months, plus series with a deadline within ~120 days | `pwc-cron-sweep-conference-deadlines.timer` |
| Refresh (07:40 / 19:40 UTC): collects finished Jobs, applies them, launches a small **daily** sweep (deadlines within 3 weeks, top-tier cycles due within ~6 weeks) | `pwc-cron-refresh-conference-deadlines.timer` |
| Research | Hugging Face Job in namespace `nielsr`. Per series: 3 retrieval agents (1 for daily) plus an aggregator that checks official pages. Results go to the Job logs as `PWC_DEADLINE_RESULT` lines. |
| Ledger | `conference_deadline_sweeps` (status `running` → `applied` / `failed`; `results` holds each series' reasoning, planned changes and rejections) |
| Operator CLI | `backend/scripts/conference_deadlines.py` (`status`, `plan`, `launch`, `collect`) |
| Rules | `plan_edition_change` in `backend/services/conference_deadline_service.py` |
| API / page | `GET /api/v1/conferences/deadlines` → `frontend/src/views/AiDeadlinesView.tsx` |

A new edition needs a deadline **or** official conference dates (`start_date`).
Editions with dates but no deadlines appear on the page as **TBA** after the
upcoming deadlines, and the sweeps keep researching them until deadlines are
published (PR #909). Run every command from the repo root.

## Workflow

### 1. Check the pipeline before doing research yourself

```bash
uv run --env-file backend/keys.env python -m backend.scripts.conference_deadlines status
systemctl list-timers 'pwc-cron-*deadline*' --all --no-pager
```

- **A sweep is `running`**: it blocks new launches. Check its Job (step 4) and wait for it rather than duplicating its research.
- **No sweep in the last ~8 days, or a run of `failed`**: the pipeline is broken. Fix that first; editing rows by hand only hides it. The usual causes are below.

### 2. Find the real gaps

```bash
uv run --env-file backend/keys.env python .agents/skills/update-ai-deadlines/scripts/coverage.py --gaps --top-tier
```

- **`upcoming`**: fine.
- **`tba`**: dates are announced and deadlines are pending. The sweeps keep checking these.
- **`gap`**: nothing upcoming is listed.

For each `gap` row, read why the agents left it alone before searching yourself:

```bash
PGPASSWORD=$(grep '^PWC_DB_PASSWORD' backend/keys.env | cut -d= -f2-) \
  psql -h localhost -U paperswithcode_user -d paperswithcode_hf -At -c \
  "select s->>'series', s->>'status', left(s->>'reasoning', 400), s->'editions'
     from conference_deadline_sweeps, jsonb_array_elements(results->'series') s
    where id = (select max(id) from conference_deadline_sweeps where status = 'applied' and mode = 'weekly')
      and s->>'series' in ('icml','neurips')"
```

Most summer-deadline venues (ICML, NeurIPS, UAI, COLM, EMNLP, …) have no call
for papers until a few months before. A `gap` with "official page 404 / no
CFP" reasoning is correct, not stale. Biennial series (ICCV, ECCV) expect the
next edition two years on. LREC is biennial too.

### 3. Research specific series now

When the user wants something checked immediately (a CFP just came out, or a
deadline was extended), launch a manual sweep for just those series instead
of editing rows by hand:

```bash
uv run --env-file backend/keys.env --env-file /etc/paperswithcode/production-cron.env \
  python -m backend.scripts.conference_deadlines launch --series icml,neurips
```

It refuses while another sweep is `running`. Series are researched in
parallel. A manual sweep usually finishes in under 30 minutes and costs about
$0.05–0.20 per series (weekly sweep 29 cost $2.84 for 30 series).

### 4. Watch a Job and apply it early

The local `hf` token gets 403 on namespace `nielsr`. Inspect Jobs with the
service's credentials:

```bash
uv run --env-file backend/keys.env --env-file /etc/paperswithcode/production-cron.env python -c "
from backend.config import get_settings
from backend.services.conference_deadline_sweep_service import job_credentials
from huggingface_hub import HfApi
c = job_credentials(get_settings()); api = HfApi(token=c.token)
job = '<hf_job_id>'
print(api.inspect_job(job_id=job, namespace=c.namespace).status)
print('\n'.join(l[:200] for l in list(api.fetch_job_logs(job_id=job, namespace=c.namespace))[-10:]))"
```

Once the stage is `COMPLETED`, apply it now instead of waiting for the next
refresh timer:

```bash
sudo pwc-cron refresh_conference_deadlines
```

Then read the sweep's `changes_applied` and per-series `rejections` in the
ledger. A rejection is a guard decision, not an error. Report the useful ones
to the user, for example "dates announced but past deadlines are immutable".

### 5. Replay proposals after a rule change

If a code change makes earlier rejections acceptable, re-plan that sweep's
logged proposals against today's rows. Do the same if a collection failed but
the Job logs are intact. Always run a dry run first:

```bash
uv run --env-file backend/keys.env --env-file /etc/paperswithcode/production-cron.env \
  python .agents/skills/update-ai-deadlines/scripts/replay_sweep.py <sweep_id> --series icml,iccv
# inspect, then add --apply
```

Replays are idempotent: already-applied changes plan to nothing. Run them from
a worktree at the **deployed** commit, so the rules match production.

### 6. Correct one edition by hand (last resort)

Use this only for a verified official source the agents keep missing, or for
an urgent correction. The admin endpoint replaces the edition's **whole**
deadline list, so send every deadline, not just the changed one. Omitted
deadlines are deleted. Dates are local times in each deadline's timezone
(`AoE`, `UTC`, `UTC-7`, or an IANA name). `short_name` creates a missing
edition.

```bash
curl -sS -X PUT https://paperswithcode.co/api/v1/conferences/<series>-<year>/deadlines \
  -H "X-Admin-Token: $(grep '^PWC_ADMIN_API_TOKEN' backend/keys.env | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{"short_name": "CVPR", "url": "https://cvpr.thecvf.com/Conferences/2027",
       "deadlines": [
         {"type": "abstract", "label": "Abstract Submission", "date": "2026-11-06 23:59:59", "timezone": "AoE"},
         {"type": "paper", "label": "Paper Submission", "date": "2026-11-13 23:59:59", "timezone": "AoE"}
       ]}'
```

Fetch the edition's current list from `GET /api/v1/conferences/deadlines`
first and edit that. Never invent or estimate dates: aggregator sites
(OpenCurious, WikiCFP, and the like) often publish guesses. Only use the
conference's official page.

### 7. Verify live

```bash
curl -s "https://paperswithcode.co/api/v1/conferences/deadlines?v=$RANDOM" | python3 -c "
import sys, json; r = json.load(sys.stdin)
print(r['count'], 'editions,', sum(not c['deadlines'] for c in r['results']), 'TBA')
for c in r['results']:
    if c['slug'] in {'icml-2027', 'cvpr-2027'}: print(c['slug'], c['start_date'], [(d['type'], d['deadline_at']) for d in c['deadlines']])"
```

The page defaults to **Top tier only** (`tier = 'a'`). A new edition inherits
its series' tier and tags. Data changes need no deploy. Code changes to the
rules or the page go through the normal PR → Bugbot → merge → `pwc-deploy` flow.

## Known failure modes

- **Stuck `running` row**: it blocks every launch. `collect` marks it `failed` once the Job is past its timeout plus 1 h. If the Job is truly gone, investigate before editing the ledger.
- **Every aggregation fails with HTTP 400**: the Job's pinned `claude-agent-sdk` bundles a Claude Code CLI that is too old for the aggregation model. Check `_cli_version.py` whenever you bump the model.
- **`SweepConfigurationError: missing … HF_TOKEN`**: you didn't pass `--env-file /etc/paperswithcode/production-cron.env`.
- **Only a couple of changes after a big sweep**: this is usually correct. Read the rejections first. Most are "past deadline is immutable", or a new edition without deadlines or dates.
- **Tests**: `test_missing_credentials_fail_loudly` fails under `--env-file backend/keys.env` because the key is present there. Run `pytest backend/tests/test_conference_deadline_service.py` without the env file.

## Report

Tell the user:
- which sweeps ran and what they cost
- what changed: editions created, deadlines added or moved
- which gaps remain and why ("no official CFP yet" vs. a rejected proposal)
- the live verification
