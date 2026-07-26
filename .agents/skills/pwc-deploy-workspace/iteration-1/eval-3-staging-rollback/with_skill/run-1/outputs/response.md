# Proposed operator response

I’ll target **staging only**. Before changing anything, I’ll identify staging’s
current and previous complete releases. If the failed deployment already
automatically restored the prior release, I’ll stop and report that state
instead of rolling back a second time.

The supported rollback swaps the complete backend-plus-frontend release,
restarts only the staging backend, and smoke-tests the restored release. It
does not require an nginx reload. Because an nginx reload was explicitly
requested, I’ll treat it as a separate staging operation and use `pwc-nginx`,
which reviews the checked-in effective diff, validates cross-environment
references, runs `nginx -t`, reloads, and smokes staging. I will not use a raw
`systemctl reload` or touch production.

## Proposed command sequence

```bash
# 1. Read-only evidence: record staging current and previous release SHAs.
pwc-status

# 2. Read-only isolation/topology check because nginx is also in scope.
python deploy/topology_audit.py --json
```

Decision gate: verify that `staging/previous` exists and is the intended
rollback target. Record its exact 40-character SHA. If status shows that
automatic rollback already restored it, do not run the rollback command.

```bash
# 3. Restore the previous complete staging release.
sudo pwc-rollback staging

# 4. Confirm resulting current/previous pointers and rollback smoke outcome.
pwc-status

# 5. Separately apply/validate/reload the checked-in staging nginx config.
# Review the displayed diff and abort if it contains unexpected changes or
# production references.
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING

# 6. Capture final release/service state.
pwc-status
```

Afterward, report the exact resulting staging `current` and `previous` SHAs,
the rollback live-smoke result, whether automatic rollback had already run,
and the nginx validation/reload/staging-smoke result. Any failed gate stops the
sequence; do not improvise with manual pointer changes, mixed frontend/backend
releases, service restarts, or a raw nginx reload.

No operational command or live-state inspection was performed while preparing
this proposal.
