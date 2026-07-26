---
name: pwc-deploy
description: Safely inspect, deploy, roll back, clean, or change nginx for the Papers With Code production and staging environments through the installed immutable-release interfaces. Use this whenever a request mentions PwC deployment, release status, staging promotion, production cutover, rollback, release cleanup, deployed service lifecycle, nginx changes, or environment migration. Do not use it for ordinary local development, data curation, database migrations, CRON job diagnosis, or paper/task/benchmark operations.
---

# Papers With Code deployment

Operate the two deployed environments through their installed interfaces. The
developer checkout is release source, never a runtime directory.

## Start with read-only evidence

1. Read the repository `AGENTS.md` and `docs/deployment.md`.
2. Run `pwc-status`.
3. Run `python deploy/topology_audit.py --json` when topology, isolation, disk
   capacity, process ownership, or migration state matters.
4. Resolve the requested ref to an exact 40-character commit. Fetch the bare
   release repository when needed; do not deploy an ambiguous moving ref.
5. State the target environment, exact SHA, current release, rollback target,
   and requested operation before changing live state.

Status and audit requests are read-only. Do not turn them into a deploy,
restart, cleanup, rollback, or nginx reload.

## Choose the supported interface

| Intent | Interface |
| --- | --- |
| Inspect releases and services | `pwc-status` |
| Deploy backend plus frontend | `pwc-deploy` |
| Restore the prior complete release | `pwc-rollback` |
| Remove unreferenced releases | `pwc-cleanup` |
| Apply a checked-in nginx template | `pwc-nginx` |
| Inspect registered scheduled jobs | `pwc-cron status` |

Never move `current` or `previous` manually, edit a release directory, run
`start_services.sh` or `stop_services.sh`, serve `frontend/dist`, invoke
`systemctl restart` as a substitute for a deployment, or delete release
directories directly. These bypass candidate qualification, feature-manifest
validation, smoke checks, and atomic rollback.

Route CRON health and job diagnostics to the repository `pwc-cli` skill.
Route database/data migrations and Papers With Code curation to their relevant
skills. A deploy does not authorize either.

## Deploy staging

Staging accepts an exact feature-branch SHA:

```bash
sudo pwc-deploy staging <exact-sha>
```

The command builds the staging frontend profile, validates the complete
backend/frontend release, qualifies a candidate on the reserved candidate
range, atomically updates the pointer, restarts only staging, and runs live
smoke checks. Report the resulting `current` and `previous` releases from
`pwc-status`.

Staging is static, admin-gated, and owns only staging user/workflow state. A
staging deployment must not start Vite, use production port 8000, mutate the
production catalog, or enable production CRON. The release contract keeps
`codex_add_evals` and `codex_enrich_paper` false in staging.

## Deploy production

Production deployment requires an explicit user request for production and an
exact commit reachable from `origin/main`:

```bash
sudo pwc-deploy production <exact-main-sha> --confirm DEPLOY_PRODUCTION
```

Do not infer production authorization from approval to deploy staging, test a
branch, merge code, or prepare a release. Preserve all staging-only feature
boundaries; currently production chat and Sandbox features remain disabled.
Production Codex curation controls are admin-only and require the protected
HF/OpenAI/GitHub job credentials plus the writable production catalog.

After success, use `pwc-status` and the release smoke checks. Verify at least
health/release identity, the SPA shell and hashed asset MIME types, a paper
page, one paper API response, and the production chat-absence boundary. Report
the immediately recoverable `previous` release.

## Roll back

Rollback requires an explicit rollback request. Inspect `previous` first:

```bash
sudo pwc-rollback staging
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
```

The command atomically swaps the complete release pointer, restarts only the
target backend, and smokes the restored release. Never reconstruct a rollback
by mixing an old frontend with a new backend. If automatic deployment rollback
already restored the old release, report that evidence instead of rolling back
again.

## Clean releases

Cleanup is separate from deploy and requires explicit authorization:

```bash
sudo pwc-cleanup --confirm CLEAN_RELEASES
```

It may remove only releases outside the union of production/staging `current`
and `previous`. Inspect status and disk capacity before and after. Do not
remove shared runtime, environment state, thumbnails, or backups.

## Change nginx

An application deploy never edits or reloads nginx. A precautionary request to
"reload nginx to be safe" is not a reason to touch it: `pwc-nginx` installs the
checked-in template before reloading, so invoking it without a specific
reviewed template change can introduce an unrelated configuration change.
Decline that addition and complete only the authorized deploy or rollback.

A specific checked-in nginx change requires an explicit request to apply that
change and the environment-specific command:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

Review the displayed diff. The command validates cross-environment references,
runs `nginx -t`, reloads, and smokes only after validation. Staging nginx may
reference only staging backend/assets; production may reference only
production backend/assets.

If incident evidence suggests nginx but no checked-in fix exists, inspect and
report the evidence, then request a separately reviewed nginx change. Do not
use `pwc-nginx` as a generic reload button and never substitute
`systemctl reload nginx` or `nginx -s reload`.

## One-time legacy migration

Use qualification-only only when an existing legacy owner still occupies the
live production port:

```bash
sudo pwc-deploy production <exact-main-sha> \
  --qualify-only --confirm DEPLOY_PRODUCTION
```

Proceed to the cutover only after candidate qualification passes and the user
has authorized the production migration. Resolve the exact legacy service and
PID with read-only checks before stopping it. `--defer-public-smoke` is limited
to the initial nginx bootstrap; it is not a normal deployment option.

## Handoff

Lead with the outcome. Include:

- target environment and exact SHA;
- resulting `current` and `previous`;
- candidate and live smoke outcome;
- whether automatic rollback ran;
- any remaining authorization boundary or failed gate.

Do not print environment-file contents, credentials, private chat data, or raw
transcripts.
