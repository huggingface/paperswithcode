# Proposed operator response

I can answer this with read-only release inspection. I will not deploy, restart,
roll back, clean releases, reload nginx, or change any pointers.

Because you explicitly asked me not to inspect live state, I have not run the
commands below and cannot truthfully supply the current release identifiers.
The supported read-only sequence is:

```bash
cd /root/python_projects/paperswithcode
pwc-status
uv run --env-file backend/keys.env python deploy/topology_audit.py --json
sudo pwc-cron status
```

Interpret the results as follows:

- `pwc-status` is authoritative for the exact production and staging `current`
  releases and their `previous` releases. Report the full release identity and
  exact 40-character commit SHA for each environment.
- Each environment's immediately recoverable rollback target is its complete
  `previous` release. A rollback must restore that release as a unit; do not mix
  an old frontend with a new backend. Merely inspecting it does not authorize
  `pwc-rollback`.
- `deploy/topology_audit.py --json` supplies corroborating read-only evidence
  about release pointers, environment isolation, process ownership, and
  migration/topology state.
- `sudo pwc-cron status` is the supported way to inspect registered scheduled
  jobs. The installed design resolves `production/current` when a job starts,
  records that immutable release ID, and runs from the resolved release rather
  than the developer checkout. Confirm that the registered live jobs report
  this behavior before concluding that the current installation is
  release-pinned; do not infer pinning from service health alone.

After running those commands, the operator-facing result should use this
shape:

```text
Production
  current:  <release-id> (<40-character SHA>)
  previous: <release-id> (<40-character SHA>)
  rollback: immediately recoverable to the complete previous release

Staging
  current:  <release-id> (<40-character SHA>)
  previous: <release-id> (<40-character SHA>)
  rollback: immediately recoverable to the complete previous release

CRON
  release-pinned: yes/no
  evidence: <registered job target(s) and immutable release identity/path>

No state was changed.
```

No mutating command belongs in this status-only request. In particular, do not
run `pwc-deploy`, `pwc-rollback`, `pwc-cleanup`, `pwc-nginx`, service restarts,
or manual `current`/`previous` pointer changes.
