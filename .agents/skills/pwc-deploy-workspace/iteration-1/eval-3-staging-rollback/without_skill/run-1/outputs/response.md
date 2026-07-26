# Proposed operator response

Understood. I would roll back **staging only** using the supported release lifecycle command, then smoke-test the staging deployment. I would not reload nginx merely “to be safe”: the rollback mechanism should restore the staged release without changing shared routing, while an unnecessary nginx reload adds production-facing blast radius. If post-rollback checks point to nginx, I would inspect the active nginx configuration and request confirmation for that separate intervention.

No commands below have been executed.

## Proposed command sequence

Run each command separately and stop if its result differs from the stated expectation.

```bash
# 1. Confirm the current production/staging release mapping and service health.
pwc-status

# 2. Confirm the installed rollback interface before mutating staging.
pwc-rollback --help

# 3. Roll back staging only, using the exact staging form shown by --help.
# Expected form; do not run if local help specifies a different syntax:
pwc-rollback staging

# 4. Confirm staging now points to the previous immutable release and production is unchanged.
pwc-status

# 5. Smoke-test the staging backend directly.
curl --fail --show-error --silent http://127.0.0.1:8001/health

# 6. Smoke-test the externally routed staging site.
# Replace <staging-host> with the hostname reported by the environment/config.
curl --fail --show-error --silent https://<staging-host>/
curl --fail --show-error --silent https://<staging-host>/<known-spa-route>
curl --fail --show-error --silent https://<staging-host>/api/v1/<known-api-route>
```

Before step 3, record the `pwc-status` output so the release can be identified unambiguously. After step 3, abort and escalate if production’s release mapping changed, staging did not move to the prior release, or any smoke test fails. Do not reload nginx as part of this rollback.

If the backend-direct check succeeds but externally routed staging checks fail, treat that as evidence of a routing problem. At that point, inspect the active nginx configuration and use the supported `pwc-nginx` workflow for a narrowly scoped, separately validated change or reload; do not invoke `nginx -s reload` or `systemctl reload nginx` ad hoc.
