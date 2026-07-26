# Proposed operator response

I’ll roll back **staging only** using the supported immutable-release
interface. I’ll first record staging’s exact current and previous release SHAs.
If `previous` is absent, or if the failed deployment already rolled back
automatically, I’ll stop and report the evidence rather than swap the pointers
again.

I will not reload nginx “just to be safe.” An application rollback neither
edits nor requires reloading nginx, and `pwc-nginx` installs the checked-in
template before reloading. Without a specific reviewed nginx change, that
would introduce an unrelated configuration risk. If evidence later identifies
an nginx fault, it should be handled as a separate reviewed change.

## Proposed command sequence

```bash
# 1. Record staging's current and previous complete releases.
pwc-status

# 2. Confirm environment isolation and topology before the rollback.
python deploy/topology_audit.py --json
```

Decision gate: identify the exact 40-character SHAs for staging `current` and
`previous`, confirm that `previous` is the intended known-good release, and
check whether automatic rollback already restored it. Do not continue if the
rollback target is missing or ambiguous.

```bash
# 3. Atomically restore the previous complete backend-plus-frontend release.
# This restarts only staging and runs the rollback's live smoke checks.
sudo pwc-rollback staging

# 4. Verify and record the resulting release pointers and service state.
pwc-status
```

If the rollback or its smoke checks fail, stop and report the failure; do not
manually move pointers, mix frontend and backend releases, restart services
directly, or reload nginx.

The completion report should include the staging target, the exact resulting
`current` and `previous` SHAs, the live-smoke result, whether automatic rollback
had already run, and the fact that nginx was deliberately left unchanged.

No operational command or live-state inspection was performed while preparing
this proposal.
