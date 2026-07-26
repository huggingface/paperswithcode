# Environment consolidation audit — 2026-07-23

Pre-migration read-only capture:

- production FastAPI ran as root from the developer checkout on `:8000`;
- staging FastAPI ran as root from the same checkout on `:8001`;
- public staging used a checkout-backed Vite/HMR server on `:8081`;
- staging ordinary API, docs, health, and thumbnails referenced production
  `:8000`; its admin check alone referenced staging `:8001`;
- production nginx served
  `/root/python_projects/pwc-releases/current/frontend-dist` with an unbounded
  historical asset archive;
- `pwc-app.service` called the process-killing/building
  `start_services.sh` from the checkout;
- the PostgreSQL backup timer ran the checkout backup script as root;
- the curation sidecar on `:8002` also ran from the checkout;
- `/srv/paperswithcode`, `/etc/paperswithcode`, and
  `/var/lib/paperswithcode` did not yet exist;
- 3.5 GiB was free on the 75 GiB filesystem; the existing thumbnail mirror
  occupied 2.6 GiB, local database backups 1.1 GiB, checkout logs 72 MiB, and
  CRON logs 130 MiB.

The audit identified all four prohibited couplings: mutable-checkout runtime,
cross-environment API/auth routing, relative persistent paths, and a backup
whose provenance was the developer checkout.

Use `python deploy/topology_audit.py --json` and `pwc-status` for the final
machine-readable topology.

## Completed migration

The staging-first rehearsal and production migration completed on 2026-07-23.
The final topology audit returned no findings.

- A single shared uv environment lives at `/srv/paperswithcode/.venv`; neither
  deployed service executes from a developer checkout.
- Production and staging run as `pwc-production` and `pwc-staging` from their
  own atomic release pointers on ports 8000 and 8001.
- Production current is `1a7368b338e5-production` at
  `1a7368b338e5b476dfadb68bff4f1084e5672d44`; its previous pointer is the
  preserved `174ff3ead5c1-production` migration release.
- Staging current is `6aa60325a112-staging` at
  `6aa60325a1124cc88361c0b4e17bbb4a2798e5b2`; its previous pointer is
  `12a8ab6bd1a0-staging`.
- Exactly those four current/previous releases remain after confirmed release
  cleanup.
- `pwc-app.service`, the Vite staging server on port 8081, and the curation
  sidecar on port 8002 are disabled or absent. Nginx routes only to the two
  environment backends and immutable frontend trees.
- Environment files are root-owned, group-readable only by their environment
  identity. The CRON credential overlay is readable only by `pwc-cron`.
- Thumbnails are shared at
  `/var/lib/paperswithcode/shared/thumbnails`; environment-owned user and
  workflow state remains separate.

## Staging gates

The immutable staging candidate and live smoke checks passed. A visible staging
feature release was deployed, the complete backend-plus-frontend pointer was
rolled back, and the new release was deployed again. Hash and process-path
checks proved that subsequent developer-checkout changes could not alter the
running staging application.

The database privilege audit proves that staging can read the shared live
catalog but cannot update it. Existing staging chat state was moved without
loss to the staging schema: 24 sessions, 43 messages, 198 transcript entries,
19 summaries. Production's former shared chat tables are empty.

Catalog curation remains deliberately unavailable in staging. The versioned
release manifest and bundled frontend both declare
`codex_add_evals=false` and `codex_enrich_paper=false`; staging runtime jobs
are disabled and no job credentials are installed. Re-enabling these controls
requires an approved production-owned or otherwise safely mediated mutation
path, credentials, and endpoint smoke tests. The staging chat flag remains
true; all three production flags remain false.

## Preservation and operations evidence

After production cutover, candidate and live smoke tests passed. Independent
checks verified the SPA shell and immutable asset MIME/cache headers, papers,
paper search, related-paper embeddings, thumbnail delivery, the admin
dashboard, unauthenticated authentication/CRON boundaries, and production chat
absence. Both backend health endpoints report their exact release IDs.

CRON now runs only through the installed `pwc-cron` launcher as `pwc-cron`,
records the exact production release, and declares a timeout, mutation scope,
idempotency contract, and health job for every registered task. A strict live
embedding-health check passed while the hourly job was running, with zero
missing embeddings.

The authoritative `pwc-postgres-backup.timer` is enabled for 03:15 UTC. A full
live run produced and locally verified
`paperswithcode_hf_20260723_152108.dump` (381 MiB), verified its remote dump
and checksum, retained three local dumps and thirty remote dumps, and exited
successfully. The three redundant checkout-era local backup copies were
removed only after checksum and remote-object verification.

The hourly application-smoke workflow is active. Manual run
`30022738170` passed against the deployed production commit
`1a7368b338e5b476dfadb68bff4f1084e5672d44`.

## Deployment skill evidence

The installed release interfaces are `pwc-deploy`, `pwc-rollback`,
`pwc-status`, `pwc-cleanup`, `pwc-nginx`, and `pwc-cron`. The
`.agents/skills/pwc-deploy` skill was created after those contracts existed,
validated with both skill validators, and evaluated against status-only,
production-deploy, and staging-rollback scenarios.

Iteration 1 scored 91.7% with the skill versus 52.8% without it and exposed an
over-broad precautionary nginx-reload instruction. After tightening that
boundary, the targeted iteration 2 regression scored 100% with the skill
versus 25% without it. Static human-review artifacts, grading records, and
benchmark summaries are checked in beside the skill.
