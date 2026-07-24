# Deployment

Production and staging use the same immutable-release mechanism. Each
environment selects one complete backend-plus-frontend release through
`current`; `previous` is its only rollback target.

## Topology

```text
/srv/paperswithcode/
  repository.git
  .venv
  runtime-lock.sha256
  releases/<sha12>-<environment>/
  environments/{production,staging}/{current,previous}

/etc/paperswithcode/{production,staging}.env
/etc/paperswithcode/production-cron.env
/var/lib/paperswithcode/{shared,production,staging}
```

`paperswithcode-backend@production` runs as `pwc-production` on `127.0.0.1:8000`.
`paperswithcode-backend@staging` runs as `pwc-staging` on `127.0.0.1:8001`.
Nginx serves each environment's `current/frontend-dist` and may fall back only
to its `previous` hashed assets. Public staging is static and admin-gated; it
never runs Vite or HMR.

Both environments read the live `public` catalog and shared thumbnail mirror.
Staging connects as `pwc_staging`, can select catalog rows, and can write only
environment-owned user, workflow, and chat rows in the `staging` schema.

## Commands

Read-only status:

```bash
pwc-status
python deploy/topology_audit.py --json
```

Deploy:

```bash
sudo pwc-deploy staging <commit-or-ref>
sudo pwc-deploy production <commit-or-ref> --confirm DEPLOY_PRODUCTION
```

Production accepts only commits reachable from `origin/main`. Every deploy
builds the selected frontend profile, validates manifests and paths, starts a
candidate on `8100-8199`, runs smoke checks, moves only the selected pointer,
restarts only that backend, and rolls back automatically on a failed live
check.

Rollback:

```bash
sudo pwc-rollback staging
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
```

Nginx has a separate lifecycle:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

It displays the effective diff, runs `nginx -t`, reloads, and smokes the
selected host. Ordinary deploys never edit or reload nginx.

Install deployment tooling only from committed source:

```bash
sudo python deploy/install_deploy_tools.py <commit>
```

## Staging sandbox-chat bridge

The sandbox chat bridge has additional fail-closed prerequisites:

1. Publish the standalone CLI release and verify its checksums and provenance.
2. Build the Modal image from that committed source, then commit the emitted
   immutable `im-...` image ID as `MODAL_IMAGE_ID`. A source revision with an
   empty ID cannot pass release validation.
3. Provision TLS for `chat-gateway.staging.paperswithcode.co`, install the
   committed nginx template with the explicit `pwc-nginx staging` lifecycle,
   and set `PWC_CHAT_GATEWAY_URL` to
   `https://chat-gateway.staging.paperswithcode.co/api/internal/chat-gateway`.
   The dedicated host exposes only the three capability-authenticated gateway
   routes.
4. Apply `add_chat_sandbox_runtime.sql` as PostgreSQL superuser with
   `search_path=staging,public`. The migration refuses any other schema, assigns
   the new tables to `pwc_staging_owner`, grants `pwc_staging`, and revokes the
   production application role.
5. Keep `PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED=false` until directory snapshot
   qualification passes.

Before any non-zero rollout, deploy two distinct zero-percent bridge commits so
both `current` and `previous` understand `modal_cli`. Then run the operator-only
infrastructure qualification from the selected immutable release:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  backend/scripts/qualify_chat_sandbox.py \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --starts 100 --parallel 4 --snapshot-samples 3 --resource-probes \
  --confirm QUALIFY_STAGING_SANDBOX
```

The runner creates only tagged disposable qualification sandboxes. It verifies
the pinned CLI, dedicated-gateway reachability without a capability, blocked
general egress, agent/broker UID and `/proc` isolation, cancellation by sandbox
termination, and directory snapshot restoration. It emits timings and no
environment values, commands, prompts, credentials, or tool output. Full model,
SDK compaction, resume, edit/retry, and citation qualification still runs
through authenticated staging chats before increasing the rollout percentage.

## Invariants

`release.json` stores the full SHA, build profile, build time, frontend
entrypoint, and backend/frontend feature manifests. `features.json` lives
beside built `index.html`. Startup fails if a deployed shell references
`/src/main.tsx`, assets are missing, paths are relative or inside a release,
or feature manifests disagree.

While chat remains staging-only, production build and runtime configuration
disable it; its backend router is absent and `/chat` redirects home.
Production and staging use host-only `pwc_session` and
`pwc_staging_session` cookies, distinct JWT secrets, and the shared OAuth
client with host-validated callback state.

## Scheduled work and backup

GitHub Actions calls `sudo /usr/local/sbin/pwc-cron <registered-job>`. The
launcher runs as `pwc-cron`, loads production plus CRON-only configuration,
resolves `production/current`, records its release ID, and uses absolute
lock/log directories.

`pwc-postgres-backup.timer` remains at 03:15 UTC. It runs the backup script from
`production/current` as `pwc-cron` and includes both `public` and `staging`.

## Development

Use `uv run --env-file backend/keys.env ...` for local backend commands and
`npm run dev` for a localhost frontend. `start_services.sh` and
`stop_services.sh` are non-mutating retirement notices; `check_services.sh`
delegates to `pwc-status`.
