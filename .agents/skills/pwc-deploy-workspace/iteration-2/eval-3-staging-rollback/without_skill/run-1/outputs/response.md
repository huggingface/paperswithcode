# Proposed operator response

I’ll roll back **staging only** using the supported lifecycle command, then validate the recovered release. I will not reload nginx “just to be safe”: a staging application rollback does not itself justify changing or reloading the shared proxy, and an unnecessary reload creates additional production risk. If the post-rollback checks instead point to an nginx configuration or process problem, I’ll stop and request separate authorization for a targeted `pwc-nginx` operation.

No operational commands have been run while preparing this response.

## Proposed command sequence

Run these commands from an operator shell with the release-management tools on `PATH`:

```bash
# Establish the current release and make sure the target is staging.
pwc-status

# Confirm the installed CLI's staging-target syntax before mutation.
pwc-rollback --help

# Roll back staging only. Do not target production.
pwc-rollback staging

# Confirm the resulting release/service state.
pwc-status
```

Then smoke-test the rollback. Set `STAGING_ORIGIN` to the already-established staging URL; do not guess a hostname:

```bash
STAGING_ORIGIN='<confirmed-staging-origin>'

curl --fail --silent --show-error "${STAGING_ORIGIN}/health"
curl --fail --silent --show-error --output /dev/null "${STAGING_ORIGIN}/"
curl --fail --silent --show-error --output /dev/null "${STAGING_ORIGIN}/tasks/"
curl --fail --silent --show-error --output /dev/null "${STAGING_ORIGIN}/api/v1/tasks/"
```

The checks cover health, the frontend root, one SPA route, and one API route. If the installed `pwc-rollback --help` shows a different explicit environment flag, use that documented staging form instead of the illustrative positional form above. If rollback or validation fails, preserve the command output, run `pwc-status` once more, and stop for diagnosis rather than reloading nginx or touching production.
