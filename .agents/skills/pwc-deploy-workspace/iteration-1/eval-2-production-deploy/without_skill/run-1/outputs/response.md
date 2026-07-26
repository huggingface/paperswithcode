# Proposed production deployment runbook

Status: **not executed**. This is an operator handoff only. The request explicitly authorizes a production release of commit `0123456789abcdef0123456789abcdef01234567`; it does not authorize changing staging, nginx, Chat availability, or Sandbox availability.

## Fixed scope

- Target environment: `production`
- Requested commit: `0123456789abcdef0123456789abcdef01234567`
- Supported deploy interface: `pwc-deploy`
- Production confirmation token: `DEPLOY_PRODUCTION`
- Chat: staging-only; it must be disabled and unreachable in production
- Sandbox: staging-only; it must be disabled and unreachable in production
- Staging's `current` and `previous` pointers, service, data, and configuration must not change
- No nginx edit or reload
- No direct edits under `/srv/paperswithcode`; the deploy must create/select an immutable release

The executor must stop at the first failed gate. A warning, ambiguous result, missing feature flag, or inability to prove a condition is a failure, not permission to continue.

## Exact runbook

Run the following on the deployment host in one operator session. Keep the full transcript.

### 1. Establish immutable inputs

```bash
set -euo pipefail
readonly TARGET_ENV=production
readonly TARGET_SHA=0123456789abcdef0123456789abcdef01234567
readonly PROD_URL=https://paperswithcode.co
readonly REPO=/srv/paperswithcode/repository.git
```

Gate 1 — input validity:

```bash
test "$TARGET_ENV" = production
test "${#TARGET_SHA}" -eq 40
printf '%s\n' "$TARGET_SHA" | grep -Eq '^[0-9a-f]{40}$'
```

### 2. Read-only preflight and baseline capture

```bash
pwc-status
python /srv/paperswithcode/environments/production/current/deploy/topology_audit.py --json
git --git-dir="$REPO" cat-file -e "${TARGET_SHA}^{commit}"
git --git-dir="$REPO" merge-base --is-ancestor "$TARGET_SHA" refs/remotes/origin/main
readlink -f /srv/paperswithcode/environments/production/current
readlink -f /srv/paperswithcode/environments/production/previous
readlink -f /srv/paperswithcode/environments/staging/current
readlink -f /srv/paperswithcode/environments/staging/previous
df -h /srv/paperswithcode
```

Record the four pointer values as:

```text
PRE_PRODUCTION_CURRENT=<captured value>
PRE_PRODUCTION_PREVIOUS=<captured value>
PRE_STAGING_CURRENT=<captured value>
PRE_STAGING_PREVIOUS=<captured value>
```

Gate 2 — topology and capacity:

- `pwc-status` and `topology_audit.py` must report a healthy, internally consistent topology.
- Production must resolve to the production environment and staging to the staging environment.
- The exact target must exist as a commit and be reachable from `origin/main`.
- Capacity must satisfy the deploy tool's documented minimum.
- There must be a valid current production release and a usable rollback target.
- Any pre-existing unhealthy state requires a separate incident decision; do not deploy through it.

### 3. Prove the environment feature contract before deployment

Inspect the target commit's committed deployment/profile code from the bare repository, without checking it out over a live release:

```bash
git --git-dir="$REPO" show "${TARGET_SHA}:deploy/release.py"
git --git-dir="$REPO" show "${TARGET_SHA}:deploy/smoke_test.py"
git --git-dir="$REPO" grep -n -i -E 'chat|sandbox' "$TARGET_SHA" -- deploy backend frontend
```

Gate 3 — staging-only features:

- The production build profile must explicitly disable both Chat and Sandbox in frontend and backend/runtime configuration.
- Production feature manifests must represent `chat=false` and `sandbox=false`, or the target's committed schema must provide an equally explicit, fail-closed representation.
- Chat and Sandbox routers/endpoints must be absent or return only the documented disabled response in production.
- `/chat` and every Sandbox UI route must not expose those applications in production.
- Staging must retain both features; this deployment must not build, select, restart, or rewrite staging.
- An absent Sandbox flag is acceptable only if the committed contract proves Sandbox is unconditionally unavailable outside staging. Otherwise stop and hand the commit back for a feature-gating fix.

### 4. Execute the single authorized mutation

Immediately before the mutation, announce the exact target SHA and re-confirm that the captured preflight gates passed. Then run exactly:

```bash
sudo pwc-deploy production 0123456789abcdef0123456789abcdef01234567 --confirm DEPLOY_PRODUCTION
```

Do not run `pwc-nginx`, a staging deploy, service-control commands, direct symlink commands, manual frontend builds, or direct filesystem mutations. `pwc-deploy` must perform its own immutable build, manifest validation, candidate qualification, production pointer move, production-backend restart, live smoke checks, and automatic rollback on failure.

Gate 4 — deploy result:

- The command must exit zero.
- Its reported full Git SHA must equal `0123456789abcdef0123456789abcdef01234567`.
- Its build profile and selected environment must both be `production`.
- Candidate qualification and live checks must pass.
- If the command exits nonzero, treat production as potentially rolled back and proceed directly to the failure verification and handoff below. Do not retry blindly.

### 5. Post-deploy verification

```bash
pwc-status
python /srv/paperswithcode/environments/production/current/deploy/topology_audit.py --json
readlink -f /srv/paperswithcode/environments/production/current
readlink -f /srv/paperswithcode/environments/staging/current
readlink -f /srv/paperswithcode/environments/staging/previous
curl --fail --silent --show-error "$PROD_URL/health"
curl --fail --silent --show-error "$PROD_URL/" >/dev/null
curl --fail --silent --show-error "$PROD_URL/paper/2605.13517" >/dev/null
curl --fail --silent --show-error "$PROD_URL/api/v1/papers/?page=1&page_size=1" >/dev/null
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' "$PROD_URL/api/v1/chat/sessions"
```

Inspect the selected release metadata and feature manifests:

```bash
PROD_CURRENT=$(readlink -f /srv/paperswithcode/environments/production/current)
jq . "$PROD_CURRENT/release.json"
jq . "$PROD_CURRENT/frontend-dist/features.json"
```

Then perform equivalent negative checks for every production Sandbox UI and API route identified in Gate 3. Each must be absent, redirected to a non-Sandbox page, or return the target's documented disabled status; an authenticated or functional Sandbox response is a failure.

Gate 5 — release identity and smoke tests:

- `/health` must return HTTP 200 and identify the new production release/SHA.
- `/`, one SPA route, and one public API route must succeed.
- Production Chat API must return 404 or 405, and `/chat` must not expose Chat.
- All production Sandbox UI/API checks must prove Sandbox unavailable.
- `release.json` must contain the exact target SHA and `build_profile=production`.
- Backend and frontend feature manifests must agree and prove Chat and Sandbox disabled under the Gate 3 contract.
- Production `current` must change to the new immutable production release; production `previous` must preserve the pre-deploy production release.

Gate 6 — staging isolation:

- Staging `current` and `previous` must exactly match `PRE_STAGING_CURRENT` and `PRE_STAGING_PREVIOUS`.
- Staging must remain healthy.
- Chat and Sandbox must remain available only on staging, behind staging's existing access controls.
- No staging service restart, pointer change, release build, or configuration change may appear in the deployment transcript.

### 6. Failure and rollback

Rollback is required if the deploy command leaves production on the target release and any Gate 4–6 check fails, including a release mismatch, broken health/site/API route, enabled Chat, enabled Sandbox, manifest disagreement, or staging mutation.

First preserve the transcript and current status. If `pwc-deploy` reports that its automatic rollback completed, verify it; do not stack a manual rollback on top. If production is still on the failed target, run:

```bash
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
```

Then re-run:

```bash
pwc-status
python /srv/paperswithcode/environments/production/current/deploy/topology_audit.py --json
curl --fail --silent --show-error "$PROD_URL/health"
curl --fail --silent --show-error "$PROD_URL/" >/dev/null
curl --fail --silent --show-error "$PROD_URL/paper/2605.13517" >/dev/null
curl --fail --silent --show-error "$PROD_URL/api/v1/papers/?page=1&page_size=1" >/dev/null
```

Rollback gate:

- Production `current` must equal `PRE_PRODUCTION_CURRENT`.
- Production health, root, SPA, and API smoke tests must pass.
- Staging pointers must still equal their captured values.
- Chat and Sandbox must still be unavailable in production.
- If rollback or verification fails, stop and escalate as a production incident; do not improvise with symlinks, service controls, nginx, or filesystem edits.

## Handoff

The executor must return one of these two complete records.

Successful release:

```text
Outcome: SUCCESS
Requested SHA: 0123456789abcdef0123456789abcdef01234567
Deployed full SHA: <value from release.json and /health>
Production release ID: <value>
Production previous release ID/path: <value>
Deploy started/finished UTC: <values>
Deploy command exit status: 0
Preflight/topology result: PASS
Candidate checks: PASS
Production smoke checks: PASS
Production Chat disabled: PASS, with HTTP evidence
Production Sandbox disabled: PASS, with HTTP evidence
Staging pointers unchanged: PASS, with before/after values
Staging health and Chat/Sandbox availability: PASS
Nginx unchanged: YES
Transcript/artifact location: <value>
Operator: <value>
```

Failed or rolled-back release:

```text
Outcome: FAILED | ROLLED_BACK | INCIDENT
Requested SHA: 0123456789abcdef0123456789abcdef01234567
Failed gate and exact evidence: <value>
Production release observed after failure: <value>
Automatic rollback reported: YES | NO
Manual rollback executed: YES | NO
Final production release ID/path: <value>
Production recovery smoke checks: PASS | FAIL, with evidence
Production Chat disabled: PASS | FAIL
Production Sandbox disabled: PASS | FAIL
Staging pointers unchanged: PASS | FAIL, with before/after values
Nginx unchanged: YES | NO
Transcript/artifact location: <value>
Incident/escalation owner: <value>
Operator: <value>
```

No success may be reported until all six gates pass. A successful production deployment with Chat or Sandbox enabled, or with any staging mutation, is not a partial success; it is a failed release requiring rollback.
