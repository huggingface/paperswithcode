# GitHub Actions workflows

Production CRON jobs are scheduled by host systemd timers
(`deploy/cron_schedules.py`; see `scripts/README.md`). The `cron-*.yml`
workflows are `workflow_dispatch`-only recovery paths that use SSH only to
invoke the installed, allowlisted runner:

```text
sudo /usr/local/sbin/pwc-cron <registered-job>
```

They never change directory to a developer checkout, source
`backend/keys.env`, install dependencies, or choose an arbitrary Python module
on the VPS. The runner resolves `production/current`, loads
`production.env` plus the CRON credential overlay, runs as `pwc-cron`, applies
the job's timeout and lock, and records its release ID.

The database backup is intentionally different: the authoritative schedule is
the host's `pwc-postgres-backup.timer` at 03:15 UTC. The
`backup-postgres-to-hf-bucket.yml` workflow is a manual remote trigger for that
same unit, not a second schedule.

`hourly-application-smoke.yml` runs at `:37` and uses
`deploy/smoke_test.py --monitor-subset` to check the production SPA, hashed
JavaScript/CSS MIME types, and the unauthenticated staging boundary. It is
read-only and does not create an admin session.

Other workflows retain their normal CI or Hugging Face Space responsibilities.
The VPS credentials used by manually dispatched workflows are
`VPS_SSH_PRIVATE_KEY`, `VPS_HOST`, and `VPS_USER`. Each SSH job first joins the
tailnet as an ephemeral `tag:ci` node with the `TS_OAUTH_CLIENT_ID` and
`TS_OAUTH_SECRET` OAuth client, so `VPS_HOST` can be the VPS's Tailscale
address and public port 22 can stay closed. Inspect runs in GitHub Actions and inspect host-side
execution with:

```bash
sudo pwc-cron status
pwc cron health
journalctl -u 'pwc-cron-*.service' --since today
```

Compatibility `run_*.sh` files delegate to `pwc-cron`; they are not independent
production launchers.
