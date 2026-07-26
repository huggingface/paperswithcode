# Proposed production deployment runbook

## Outcome and scope

Deploy exactly `0123456789abcdef0123456789abcdef01234567` to **production** using the immutable-release interface. Production authorization is explicit.

This runbook does not deploy to or alter staging. It preserves the production feature boundary: **Chat and Sandbox remain disabled in production and staging-only**. It does not authorize database/data migrations, CRON changes, release cleanup, nginx changes or reloads, manual service restarts, or edits to release pointers/directories.

No operational command has been executed while preparing this runbook.

## Gates

All gates are fail-closed. Stop before deployment on any failed or ambiguous check.

1. **Authorization and target gate**
   - Target is `production`.
   - Requested operation is a complete backend-plus-frontend deployment.
   - Exact requested SHA is `0123456789abcdef0123456789abcdef01234567`.
   - The operator has supplied the required explicit production approval.

2. **Commit identity and provenance gate**
   - Refresh the installed bare release repository's `origin/main` reference if needed.
   - Verify the requested object exists as a commit.
   - Verify that exact commit is reachable from `origin/main`.
   - Stop if the object is missing, resolves to another SHA, or is not reachable from `origin/main`; do not substitute a branch, tag, or newer commit.

3. **Topology, isolation, and capacity gate**
   - `pwc-status` must show coherent production and staging `current`/`previous` pointers and expected service ownership.
   - `python deploy/topology_audit.py --json` must pass the relevant topology, cross-environment isolation, process ownership, migration-state, and disk-capacity checks.
   - Stop on an unhealthy service, pointer inconsistency, unexpected port/process owner, unsafe migration state, cross-environment reference, or insufficient build headroom.

4. **Rollback gate**
   - Record the pre-deploy production `current` release and exact full SHA. That complete release is the expected immediately recoverable `previous` release after activation.
   - Record the pre-deploy production `previous` release for audit context.
   - Stop if the current complete release cannot be identified or is not a valid rollback candidate.

5. **Feature-boundary gate**
   - Candidate production build/runtime configuration and backend/frontend feature manifests must agree that Chat and Sandbox are disabled.
   - Production must not expose either feature's backend router/API.
   - `/chat` and `/sandbox` must be absent from the production experience or redirect home according to the checked-in production contract.
   - Stop if either feature is enabled, either manifest disagrees, or any production asset/configuration references staging-only Chat or Sandbox state.

6. **Candidate qualification gate**
   - The supported deploy command must build and validate one complete production release, start it only on the reserved candidate range, and pass candidate health, release-identity, backend/frontend manifest, SPA, asset, paper-page, API, and feature-boundary checks.
   - A candidate failure must leave production `current` untouched.

7. **Atomic activation and live-smoke gate**
   - Activation may move only the production pointer and restart only the production backend.
   - Nginx must not be edited or reloaded.
   - Live checks must pass. If they fail, allow the deploy interface's automatic rollback to restore the old complete release; do not attempt a manual pointer change or mix frontend/backend releases.

8. **Post-deploy evidence gate**
   - Re-run `pwc-status`.
   - Confirm production `current` is the release for the exact requested SHA.
   - Confirm production `previous` is the recorded pre-deploy `current`.
   - Confirm staging `current` and `previous` are unchanged.
   - Confirm health/release identity, the SPA shell, hashed asset MIME types, a paper page, one paper API response, and the production absence boundaries for both Chat and Sandbox.

## Exact operator runbook

Run from the release-source repository checkout; never run the checkout as a service or edit `/srv/paperswithcode/releases` directly.

1. Establish read-only pre-deploy evidence:

   ```bash
   pwc-status
   python deploy/topology_audit.py --json
   ```

   Record:

   - production `current` release and full SHA;
   - production `previous` release and full SHA;
   - staging `current` and `previous`;
   - production/staging service ownership and ports;
   - audit result and available capacity.

2. Refresh and verify the exact commit in the installed bare release repository:

   ```bash
   sudo git --git-dir=/srv/paperswithcode/repository.git fetch origin main
   git --git-dir=/srv/paperswithcode/repository.git rev-parse --verify 0123456789abcdef0123456789abcdef01234567^{commit}
   git --git-dir=/srv/paperswithcode/repository.git merge-base --is-ancestor 0123456789abcdef0123456789abcdef01234567 origin/main
   ```

   The `rev-parse` output must equal `0123456789abcdef0123456789abcdef01234567` exactly, and `merge-base --is-ancestor` must exit zero. Otherwise stop.

3. Before mutation, announce and record this deployment tuple:

   ```text
   operation: deploy complete backend+frontend release
   target: production
   exact SHA: 0123456789abcdef0123456789abcdef01234567
   current: <production-current from pwc-status>
   rollback target after activation: <same pre-deploy production-current>
   staging-only boundaries: Chat disabled in production; Sandbox disabled in production
   ```

4. Execute exactly one supported production deployment command:

   ```bash
   sudo pwc-deploy production 0123456789abcdef0123456789abcdef01234567 --confirm DEPLOY_PRODUCTION
   ```

   Do not use `--qualify-only` unless read-only evidence proves this is the separately authorized one-time legacy migration. Do not use `--defer-public-smoke`. Do not invoke `systemctl`, retired service scripts, `pwc-nginx`, `pwc-cleanup`, or manually change `current`/`previous`.

5. If the command reports candidate qualification failure, stop and report that production was not activated. If it reports a failed live check and automatic rollback, stop, verify the restored state, and do not deploy or roll back again without a new operator decision.

6. Collect post-deploy evidence:

   ```bash
   pwc-status
   python deploy/topology_audit.py --json
   ```

   Use the deploy command's candidate and live smoke report plus the installed release smoke checks to verify:

   - `/health` succeeds and reports the exact release identity;
   - `/` serves the production SPA shell;
   - a hashed JavaScript asset and a hashed CSS asset return successful responses with correct MIME types;
   - a known paper SPA route renders;
   - one known paper API route returns a valid response;
   - `/chat` does not expose Chat and the production Chat API/router is absent;
   - `/sandbox` does not expose Sandbox and the production Sandbox API/router is absent;
   - staging pointers, service, and staging-only feature availability are unchanged.

7. Apply the final decision:

   - **Success:** report the exact production `current`, immediately recoverable `previous`, candidate/live smoke outcomes, unchanged staging state, and confirmed Chat/Sandbox production-absence boundary.
   - **Automatic rollback:** report the restored `current`, resulting `previous`, failing gate, and that automatic rollback ran. Do not issue `pwc-rollback`.
   - **Pre-activation failure:** report the failed gate and evidence that production `current` was unchanged.
   - **Unexpected partial/ambiguous state:** stop. Preserve evidence and escalate; do not manually repair pointers or restart services.

## Handoff template

```text
Outcome: <deployed | not activated | automatically rolled back | escalation required>
Target: production
Requested exact SHA: 0123456789abcdef0123456789abcdef01234567
Resulting current: <release ID and full SHA>
Immediately recoverable previous: <release ID and full SHA>
Pre-deploy current: <release ID and full SHA>
Staging state: <confirmed unchanged current/previous>
Candidate qualification: <pass/fail, concise failing check if any>
Live smoke: <pass/fail/not run>
Post-deploy verification:
  health/release identity: <pass/fail>
  SPA shell: <pass/fail>
  hashed JS/CSS MIME: <pass/fail>
  paper page: <pass/fail>
  paper API: <pass/fail>
  production Chat absence: <pass/fail>
  production Sandbox absence: <pass/fail>
Automatic rollback ran: <yes/no>
Remaining failed gate or authorization boundary: <none, or exact gate>
Notes: No nginx, cleanup, CRON, database/data-migration, staging deployment, or manual lifecycle action was performed.
```
