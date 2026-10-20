# Chat sandbox spend circuit

This runbook covers the application circuit for Modal chat sandboxes. Research turns are MCP-only and create no sandbox; sandboxes serve poster and paper authoring turns. Policy values live in `/etc/paperswithcode/<environment>.env` (`PWC_CHAT_SANDBOX_*`). Modal budget changes must be made by the sole Workspace operator and recorded in the private operations audit trail. Never place a provider budget-write credential in the web application.

## Required provider policy

- Workspace: `$250` enforced monthly budget and native account-email notifications.
- Staging (`PWC_CHAT_SANDBOX_PROVIDER_MODE=starter_workspace`): the `pwc-chat-staging` Environment in the `nielsrogge` Starter Workspace, using the sole owner's personal token, no Environment cap or credential isolation, and the reviewed `$75` warning / `$105` application trip (attestation `...-starter-app105-v2`).
- Production (`team_environments`): the `pwc-chat-production` Environment in the `paperswithcode` Workspace, with a `$200` warning and `$225` application trip inside the provider's `$250` Environment and Workspace budgets, preserving `$25` of provider headroom for reporting delay and termination. The local ledger prices resource requests; hourly provider reconciliation raises the effective value when actual burst usage is higher.
- In Team mode, Environment-scoped service credentials must not list or terminate the other chat Environment's sandboxes.

## Incident response

1. Confirm the read-only Chat Compute dashboard state and event ID.
2. Verify the `$250` Modal Workspace budget and native notification recipients. In Team mode, also verify the active Environment budget.
3. Enumerate provider sandboxes tagged `service=pwc-chat`; compare them with live compute intervals.
4. Run the watchdog from the affected environment's active immutable release or wait for its next 15-second pass. It terminates tracked workers and tagged orphans.
5. Confirm zero provider sandboxes and zero unresolved reservations/termination states. Keep the circuit tripped on uncertainty.
6. Compare the conservative ledger with Modal's month-to-date report. Provider spend is a floor and may only raise effective spend.
7. Investigate non-chat Workspace spend before changing any cap.

The watchdog also settles any open compute interval whose durable lease is
already `terminated` or `failed`. This repair is idempotent and uses the lease
terminal timestamp; it prevents a missed termination callback from accruing a
full sandbox lifetime indefinitely.

## Staging qualification

`PWC_CHAT_BLANK_POOL_ENABLED` is `false` in both environments. Requalify staging
before re-enabling a blank pool. Primary and fallback alert webhooks are already
installed (`deploy/configure_host_env.py --staging-chat-alerts-only` reinstalls
them). First exercise the synthetic warning/trip states, alert transitions,
restart persistence, public rejection and interruption UX, and the audited re-arm
path without creating real compute:

```bash
sudo uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_chat_sandbox_spend \
  --qualification-id <unique-lowercase-id> \
  --confirm QUALIFY_STAGING_CHAT_SPEND
```

The command prints an isolated admin-dashboard environment record and creates no provider compute. Then create one bounded sandbox, verify both natural and forced 30-second drain outcomes and zero tagged orphans, and only then enable one blank sandbox to prove its interval remains continuous when claimed. A deployment resets the seven-day soak evidence; rerun the release-scoped soak audit before treating staging as qualified.

Run the graceful/forced drain qualification from the active immutable release
with an explicit total reservation ceiling. It creates two sequential tagged
sandboxes, keeps the blank pool disabled, and prints only sanitized lifecycle
evidence:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_sandbox_trip \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --max-total-microusd 2100000 \
  --confirm QUALIFY_STAGING_CHAT_TRIP
```

After that qualification succeeds with zero tagged provider sandboxes, enable
exactly one staging blank sandbox. This mode changes only the staging pool flag
and its already-qualified one-blank capacity; it never changes production:

```bash
sudo /usr/bin/python3 deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-chat-pool-enable-only
```

Deploy the exact pushed release to staging so the web process reads the flag,
wait for one `blank_ready` row, then prove that a real claim keeps one continuous
`blank_pool` compute interval from provider creation through claim. The runner
terminates its synthetic claimed session, confirms interval settlement, waits
for the one replacement blank, and emits content-free evidence:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_pool \
  --samples 1 \
  --candidate-cpu 0.125 \
  --candidate-memory-mib 512 \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm QUALIFY_STAGING_CHAT_POOL
```

If any qualification or post-run guardrail fails, disable replenishment and
redeploy the same staging release before investigating:

```bash
sudo /usr/bin/python3 deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-chat-pool-disable-only
```

## Recovery

Normal recovery occurs only at a confirmed provider billing-cycle boundary with fresh reconciliation, matching policy attestation, zero live/orphan sandboxes, and no unresolved intervals or reservations. Operator-disable and accounting-integrity trips never auto-rearm. The root-only `backend.scripts.manage_chat_sandbox_circuit disable` command records an allowlisted operator, reviewed evidence, reason, and typed environment/cycle confirmation. Exceptional early rearm uses its `rearm` subcommand with the same controls, an explicit `accounting-correction`, `reviewed-higher-caps`, `reviewed-provider-cap`, or `reviewed-policy-transition` basis, and the post-trip `kill_sweep_complete` event ID (`--orphan-sweep-event-id`); it is never available from the dashboard. `reviewed-higher-caps` requires strictly higher warning and application caps below unchanged provider caps, except for the exact reviewed nielsrogge staging Starter transition from `$75`/`$100` to `$75`/`$105`, `reviewed-provider-cap` changes only the provider Environment cap and its attestation, and `reviewed-policy-transition` is limited to the same-cap starter-to-environment guardrail migration. Run either command without `--confirm` first to review the old/new policy, spend, provider floor, headroom, and live count, then rerun with the exact confirmation string it prints.

After any provider policy change, record the Workspace setting, optional Team Environment settings, native notification recipients, operator identity, timestamp, and matching deployment attestation in the private operations audit trail. The sole owner must maintain MFA, verified recovery and billing email, and the current Modal support recovery path outside source control.

## Changing an application cap

Both current caps are already applied by one-shot transition scripts that accept
only the previous policy: `deploy/configure_staging_chat_application_cap.py`
(`starter-v1` to `starter-app105-v2`) and
`deploy/configure_production_chat_application_cap.py` (`250-v2` to
`250-warn200-app225-v3`). A further change needs a new reviewed transition. After
applying a cap change to the protected configuration, refresh the exact active release with
`pwc-deploy <environment> <sha> --refresh-environment`. The policy mismatch trips the existing spend circuit;
wait for the watchdog's completed post-trip orphan sweep, zero live intervals
and reservations, and fresh provider reconciliation. Review and execute the
root-only `manage_chat_sandbox_circuit rearm --basis reviewed-higher-caps`
workflow above with the completed sweep ID. Do not edit the ledger directly or
relax the re-arm prerequisites. Reverting the protected file alone is not a ledger
rollback; leave admissions fail-closed until policy and ledger agree.
