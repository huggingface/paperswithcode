---
name: pwc-cron-health
description: Thoroughly audit the health of every Papers With Code production CRON job shown on the admin dashboard, including scheduler execution, logs, locks, durable data freshness, backlog completeness, semantic correctness, and bounded comparisons with upstream sources. Use this whenever a user asks whether PwC CRONs, scheduled imports, citations, GitHub stars, trending scores, leaderboard syncs, embeddings, thumbnails, daily paper enrichment, taxonomy linkers, or the admin CRON dashboard are healthy—even if they only mention one suspicious stale dataset. Do not use a green dashboard status or fresh timestamp as sufficient proof.
metadata:
  compatibility: Requires the paperswithcode repository, production read access, uv, pwc-status, pwc-cron, PostgreSQL read access, and provider CLIs/tokens only when a bounded upstream comparison needs them.
---

# Papers With Code CRON health audit

Audit the production automation as an independent verifier. The admin dashboard is useful control-plane evidence, but it is not the source of truth: a buggy job can exit successfully, update a timestamp, and still leave incorrect or incomplete data.

## Read before auditing

1. Read the repository `AGENTS.md`.
2. Read `docs/database.md` before any database access.
3. Read the CRON and admin sections of `docs/operations.md`.
4. For a full audit, read all of `references/job-probes.md`. For a focused audit, read the common rules and the requested job sections.

Use the exact active production release as the implementation and schedule contract. The developer checkout may be newer or dirtier.

## Outcome standard

Complete a full audit only after every dashboard entry has all four evidence planes classified:

| Plane | Question |
| --- | --- |
| Registration | Is the job represented consistently in the deployed registry, scheduler, launcher allowlist, and dashboard? |
| Execution | Did the expected scheduled slot run the correct release and terminate cleanly without a stuck process, lock, queue, or provider failure? |
| Durable output | Did the intended database rows, objects, files, or queue states actually reach fresh and complete state? |
| Correctness | Do deterministic recomputation, upstream comparison, invariants, or a public functional smoke test show that the values/content are right? |

Classify each plane as `healthy`, `degraded`, `unhealthy`, `unverified`, or `not_applicable`. A job is fully healthy only when all applicable planes are healthy. Preserve `unverified`; never turn missing evidence into green.

## Safety boundary

This skill is read-only. Inspection does not authorize remediation.

- Run `sudo pwc-cron status`, but never `sudo pwc-cron JOB`. Job invocations—including most dry runs—write launcher records, acquire locks, call providers, and commonly mutate shared data.
- Do not dispatch, rerun, or cancel GitHub workflows; restart services/timers; delete locks; edit configuration; rotate tokens; deploy; upload/sync/delete bucket objects; or write SQL.
- Use bounded `SELECT` queries inside an explicitly read-only transaction. Run repository Python/CLI code with `uv run --env-file backend/keys.env ...`.
- Bound logs, journals, external API comparisons, and object downloads. Redact tokens, database URLs, webhook URLs, private traces, and chat content.
- Prefer metadata and aggregate health for chat monitoring. Do not expose user content.
- If a check would be expensive, rate-limited, paid, or stateful, use a stratified sample and label the remaining scope `unverified`.

## Phase 1: pin the live scope

Capture a UTC audit timestamp and read-only release evidence:

```bash
pwc-status
sudo pwc-cron status
readlink -f /srv/paperswithcode/environments/production/current
```

Record the production release ID and exact 40-character SHA. Confirm launcher provenance points to the same release. If source and live release differ, inspect files under the resolved production release rather than assuming the checkout reflects production.

Build the inventory dynamically from the deployed `backend/services/cron_registry.py`; do not trust a remembered list or README. Record the discovered count; no fixed job count is a permanent contract.

Capture a fresh, uncached baseline from the repository backend CLI. Start in
the developer checkout with its existing environment. Do not run `uv` from an
immutable release: it can create a release-local `.venv` and build artifacts.
`--no-sync` prevents dependency installation; `-B` prevents bytecode writes.
The Python process below selects live source only after `uv` has started:

```bash
PWC_CRON_LOG_DIR=/var/lib/paperswithcode/production/cron-logs \
PWC_THUMBNAIL_CACHE_DIR=/var/lib/paperswithcode/shared/thumbnails \
uv run --no-sync --env-file backend/keys.env python -B - <<'PYTHON' > /tmp/pwc-cron-health.json
import os
import runpy
import sys
from pathlib import Path

release = Path("/srv/paperswithcode/environments/production/current").resolve()
os.chdir(release)
sys.path.insert(0, str(release))
sys.argv = ["backend.cli", "cron", "health", "--strict", "--json"]
runpy.run_module("backend.cli", run_name="__main__")
PYTHON
```

Confirm these log/cache paths against the active environment without printing
credentials. If checkout dependencies cannot load live code, use an isolated
temporary environment; never install into or edit the release. Treat any local
configuration mismatch as missing audit evidence, not a production failure.

The public catalog `pwc` executable may not expose the repository-only `cron` command. When `pwc cron health` and the source parser disagree, use `python -m backend.cli` from code matching the active release and report the mismatch.

Save launcher status separately and run the bundled inventory check:

```bash
sudo pwc-cron status > /tmp/pwc-cron-launcher.json
uv run --env-file backend/keys.env \
  python .agents/skills/pwc-cron-health/scripts/check_inventory.py \
  --repo-root /srv/paperswithcode/environments/production/current \
  --dashboard-json /tmp/pwc-cron-health.json \
  --launcher-json /tmp/pwc-cron-launcher.json
```

Also enumerate all scheduled automation, because dashboard coverage discovery only recognizes `cron-*.yml` workflows and systemd services invoking `pwc-cron`:

```bash
rg -n "schedule:|cron:" /srv/paperswithcode/environments/production/current/.github/workflows/*.yml
systemctl list-timers --all --no-pager | rg -i 'pwc|paperswithcode|autonomous|submission'
```

Report scheduled duties outside the dashboard separately. Do not silently redefine them as dashboard jobs.

## Phase 2: challenge the dashboard baseline

Inspect every job object, not only the summary, `critical_issues`, health score, or `/cron/health` boolean.

- Treat `degraded`, `unknown`, `broken`, and `stuck` as findings even when the score is at least 80% or the endpoint says healthy.
- Separate `execution_health` from `output_health`; either can fail independently.
- Inspect `db_metrics`, `work_metrics`, workflow/systemd evidence, lock state, process state, and diagnostics.
- The admin `/status` response is cached stale-while-revalidate for about a minute. Prefer the fresh CLI build; use `force_refresh=true` only as corroboration.
- Treat the paused/manual URL extraction entry as `not_applicable` for schedule cadence. Audit its last manual run only when one is claimed.
- Validate expected schedule slots against workflow YAML/timers. Inspect several consecutive runs and queue age, not only the newest success—long jobs can accumulate queued scheduled runs.
- A systemd job whose execution reason is `timer enabled after the last scheduled slot; first systemd invocation pending` is reported `healthy` because the timer has never triggered and its last slot predates its `ActiveEnterTimestamp`. Manual `pwc-cron` runs do not count as invocations. Confirm the timer's `NEXT` in `systemctl list-timers` matches the registry schedule, then re-check after that slot.

Useful bounded scheduler evidence:

```bash
gh run list --workflow WORKFLOW.yml --event schedule --limit 10 \
  --json databaseId,status,conclusion,createdAt,updatedAt,event,headBranch,url
gh run view RUN_ID --json status,conclusion,createdAt,updatedAt,event,headBranch,jobs
systemctl show TIMER_OR_SERVICE --property=ActiveState,SubState,Result,ExecMainStatus,LastTriggerUSec,NextElapseUSecRealtime
journalctl -u SERVICE --since '24 hours ago' --no-pager -n 200
```

Use failed logs only when needed, and sanitize before reporting.

## Phase 3: verify the data plane independently

Follow `references/job-probes.md` for every dynamically discovered dashboard ID. The reference gives the durable effect, likely dashboard blind spot, and strongest independent checks.

Apply these rules across all jobs:

1. **Prove cohort completeness.** Reconstruct the eligible population or upstream cohort and anti-join it against the output. `MAX(updated_at)` proves only that one row was touched.
2. **Inspect distributions.** Measure oldest wait, percentiles, missing/stale counts, failures, and consecutive-run deltas. A recent average or maximum can hide a starved partition.
3. **Check semantics.** Recompute deterministic scores/hashes/ranks or compare a bounded stratified sample to GitHub, Semantic Scholar, Hugging Face, or the live leaderboard source.
4. **Check invariants.** Look for duplicates, orphans, non-finite vectors, impossible values, stale owned rows, rank direction errors, and mismatched junction tables.
5. **Exercise a public read path.** When appropriate, verify the production API/page/search/thumbnail endpoint exposes plausible current output—not merely that storage rows exist.
6. **Prove no-work.** A successful no-op is healthy only if an independent eligible-cohort/backlog check shows there was no work. Natural upstream stability is not itself a failure.
7. **Avoid circular proof.** Do not reuse only the registry's `db_freshness_query` or the same summary counter that powered the dashboard. Add a logically independent check.

For database work, keep the transaction read-only and bounded. Prefer a short repository script or SQL file that begins a read-only transaction, emits aggregates/samples, and rolls back. Never paste credentials into commands or reports.

## Phase 4: cross-job invariants

Check producer/consumer chains after individual probes:

- GitHub star snapshots → repository trending → paper trending → organization trending.
- HF daily cohort → paper import → curation workflows/jobs → enrichment/evaluations → curation thumbnails.
- Thumbnail preload bucket → local mirror → public thumbnail endpoint.
- Paper catalog/content hashes → active embedding generation → semantic search.
- Method keyword/reference backfills → paper-method evidence and links.
- Live leaderboard sources → owned evaluations → recomputed ranks → public benchmark API.

A downstream fresh timestamp cannot compensate for stale or incorrect upstream inputs. Report the earliest broken edge and affected consumers.

## Reporting

Lead with the outcome and audit timestamp. Use this structure:

### Executive summary

- Production release ID and SHA
- Dashboard entries audited / registry entries / launcher mappings / gaps
- Fully healthy, degraded, unhealthy, unverified, paused counts
- Earliest broken producer and likely user-visible impact
- Explicit statement that no state was changed

### Every-job matrix

Include one row for every dynamically discovered dashboard entry:

| Job | Registration | Execution | Durable output | Correctness | Key evidence | Finding |
| --- | --- | --- | --- | --- | --- | --- |

Do not collapse healthy jobs into “the rest looked fine.” Exhaustiveness is part of the audit.

### Cross-job findings

Describe broken producer/consumer chains, scheduler drift, launcher/release drift, and dashboard false positives.

### Unverified scope

List checks not completed, why, and the precise read-only evidence still needed.

### Recommended remediation

Propose the smallest corrective or diagnostic action, ordered by impact. Do not perform it without separate authorization.

## Completion gate

Before finishing, confirm:

- every deployed registry entry appears exactly once in the report;
- every dashboard entry maps to the registry or is explained;
- every scheduled registry job maps to scheduler and launcher evidence;
- every job has an independent durable-output or correctness probe, or is explicitly unverified;
- paused/manual work is separated from scheduled health;
- out-of-dashboard scheduled automation is listed;
- no mutating command or external message was sent.
