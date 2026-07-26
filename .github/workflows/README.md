# GitHub Actions workflows

Scheduled production workflows use SSH only to invoke the installed,
allowlisted runner:

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
The VPS credentials used by scheduled workflows are `VPS_SSH_PRIVATE_KEY`,
`VPS_HOST`, and `VPS_USER`. Inspect runs in GitHub Actions and inspect host-side
execution with:

```bash
sudo pwc-cron status
pwc cron health
journalctl -u 'run-u*.service' --since today
```

Compatibility `run_*.sh` files delegate to `pwc-cron`; they are not independent
production launchers.
