# Autonomous operations

Autonomous operations are a monitored, reversible production subsystem. The
global manual switch and each operator switch live in the admin control plane;
they are the only supported remote mutation controls. Manual mode blocks
callbacks, retries, source publication, deployments, and data changes while the
15-minute monitors, daily audit, digest, and alerts continue.

## Permanent hard boundaries

- Autonomous code may never create or mutate tasks, methods,
  benchmarks/datasets, metrics, or conferences. Those submissions stay pending
  in their existing human review tabs.
- Database migrations, nginx or host changes, secret rotation, billing renewal,
  destructive repair, and ambiguous lock ownership always stop for a human.
- One global source-repair lease fences every operator.
- Chat source changes additionally require the recorded scalable-chat baseline,
  Luna diagnosis, independent Terra/high approval, staging exact-SHA canary,
  production exact-SHA promotion, verification, and rollback.
- User chat content is never stored in alerts, digests, run/action records,
  commits, patches, tests, health files, or Codex telemetry.

## Remote controls

Use `/admin-dashboard` from an authenticated admin session. The autonomous
operations panel exposes global manual mode, independent submission/CRON/chat
switches, active lease state, qualified chat baseline, provider state, run cost,
and immutable run/action history. Changing a switch requires the displayed
revision; stale writes fail instead of overwriting a newer decision.

Emergency sequence from mobile:

1. Turn global manual mode on.
2. Confirm `monitoring_active` remains true and all mutation attempts report
   `manual_mode`.
3. Disable only the affected operator if the incident is isolated.
4. Review the content-free alert receipt and linked runbook.

Host access is not required for normal control. Use `/connect-hetzner-vps` only
when Tailscale re-authentication or host-level recovery is itself the incident.
Never bypass the installed `pwc-cron`, `pwc-deploy`, `pwc-rollback`, and
`pwc-nginx` interfaces.

## Alerts and digest

Urgent alerts use `PWC_AUTONOMOUS_ALERT_SLACK_WEBHOOK_URL` first. A non-2xx or
transport failure uses the distinct
`PWC_AUTONOMOUS_ALERT_FALLBACK_WEBHOOK_URL`. Delivery receipts persist only the
event class, severity, operator, hashes, route states, status codes, and time.
The resource identifier, webhook URL, response body, and user content are not
stored. Identical event/operator/resource windows are durably deduplicated.

The daily deep CRON audit sends a mobile-sized aggregate digest through the
separate `PWC_AUTONOMOUS_DIGEST_WEBHOOK_URL` and writes the same aggregate to
the CRON health record. The route must be the Codex-mobile notification bridge,
not either urgent-alert webhook. The renderer accepts only bounded counts,
costs, fixed operator names, and control flags. It contains no submission
payload, trace, prompt, callback, username, or resource identifier.

Apply the append-only receipt migration before enabling alert-producing units:

```bash
sudo -u postgres psql --no-psqlrc --set ON_ERROR_STOP=1 \
  --dbname paperswithcode_hf \
  --file backend/database/migrations/add_autonomous_alert_delivery.sql
```

The digest route and both urgent routes are CRON-only secrets. Verify a 2xx
digest receipt from the daily audit before considering the mobile channel
qualified.

## Chat reliability monitoring

The production chat alert monitor runs content-free Langfuse aggregate checks
every 15 minutes. Its Langfuse requests select only `core`, `basic`, `time`, and
`metrics`; they never request trace input, output, or metadata. End-to-end turn
observations supply success, interruption, first-token, and completion timing,
while provider observations supply provider/auth/billing classes. Existing
sanitized operational counters supply persistence and capacity failures.

A dedicated-account synthetic chat runs at most every four hours, plus explicit
post-alert, deploy, rollback, and provider-route checks. It verifies login,
admission, first token, complete stream, persisted/reopenable state, deletion,
and deletion verification. Configure its username and session credential only
in the root-owned CRON overlay:

```text
PWC_CHAT_SYNTHETIC_EXPECTED_USERNAME=replace-dedicated-monitor-username
PWC_CHAT_SYNTHETIC_SESSION_COOKIE=replace-dedicated-monitor-session
```

The synthetic prompt is fixed in source. Its durable state contains only step
states and stable incident signatures, never the session identifier, response,
credential, prompt, or trace identifier. Manual mode does not disable either
monitor.

Incident trace-content access is exceptional. It requires a degraded aggregate
finding, a named operator and run, a trace ID inside a bounded incident window,
an execution environment that explicitly guarantees telemetry retention is
disabled, and a durable redacted audit acknowledgement before access is
authorized. Normal monitoring has no trace-content access path.

## Budget controls

Each Codex request is still capped by its provider-side per-run reservation.
The local cumulative gate serializes launch admission, accounts for completed
runs across every operator, and reserves the full configured cost/token ceiling
for each unfinished execution intent. It checks UTC daily/monthly ceilings
before credentials are issued. Crossing a ceiling records an immutable control
transition, emits a budget-threshold alert, and disables mutation for only the
operator requesting the new run. Deterministic monitoring and alerts remain
scheduled.

Configured defaults can be lowered in the CRON environment:

```text
PWC_AUTONOMOUS_PER_RUN_COST_USD=10
PWC_AUTONOMOUS_PER_RUN_TOKENS=200000
PWC_AUTONOMOUS_DAILY_COST_USD=25
PWC_AUTONOMOUS_DAILY_TOKENS=1000000
PWC_AUTONOMOUS_MONTHLY_COST_USD=250
PWC_AUTONOMOUS_MONTHLY_TOKENS=10000000
```

Autonomous Codex, submission HF Job, and submission OpenAI credentials must be
dedicated and externally budget-capped. The host configurator keeps these and
both alert webhook credentials out of application environments and only in the
root-installed CRON overlay.

## Operator runbooks

### Database or migration required

Turn manual mode on, leave monitoring active, and reject the candidate. Review
and apply a narrow migration through the normal human deployment workflow.
Autonomous source targets exclude `backend/database/migrations/`.

### Nginx or host change required

Turn manual mode on and use the separately reviewed `pwc-nginx` or host-layout
workflow. Autonomous brokers reject nginx, systemd, host-layout, and credential
paths.

### Secret, provider billing, or subscription renewal

Disable the affected operator, rotate or renew through the provider account,
then run a deterministic probe. Never paste a secret into a run, alert, issue,
or chat. Re-enable only after the provider-side cap and credential scope are
verified.

### Ambiguous or stale lock

Do not delete or steal the lock. Compare scheduler state, process ancestry,
owner, age, and durable progress. If ownership remains ambiguous, keep the job
disabled and repair manually. The autonomous CRON operator diagnoses and alerts
but has no lock-deletion capability.

### Destructive data repair

Stop and preserve evidence. Export the exact affected identifiers, review a
bounded repair and rollback procedure, and execute it manually. Autonomous
operators may retry only explicitly idempotent commands and cannot run generic
SQL or shell actions.

### Attempt or budget exhausted

Monitoring continues. Inspect aggregate evidence and prior attempt receipts;
do not reset counters to force another autonomous attempt. Increase a budget
only after confirming provider pricing and the independent credential cap.

### Global manual mode

Expect monitors and alerts to remain healthy while all callbacks, runtime
retries, source publication, deployments, and catalog mutations fail with
`manual_mode`. If anything mutates, keep manual mode on and treat it as a
control-plane incident.

## Rollout and rollback

All operator mutation switches remain off until their Task 15 evidence is in
the immutable admin run history. Submission review requires seven days of
shadow comparisons. CRON requires each deterministic failure/recovery drill.
Chat requires the exact staging-qualified scalable baseline and every provider,
privacy, canary, production rollback, and retry-exhaustion drill.
Until that external scalable-chat baseline is reconciled by exact SHA, the
acceptance API rejects chat evidence and always reports
`scalable_chat_baseline_reconciliation_pending`; the chat operator cannot be
enabled through the control plane.

Apply the additive acceptance-event migration before recording evidence:

```bash
sudo -u postgres psql --no-psqlrc --set ON_ERROR_STOP=1 \
  --dbname paperswithcode_hf \
  --file backend/database/migrations/add_autonomous_acceptance_evidence.sql
```

Record one content-free evidence digest through the admin API. The server uses
its own UTC timestamp, so seven submission shadow days must be seven actual,
distinct days; callers cannot backdate them.

```text
POST /api/v1/admin/autonomous-operations/operators/{operator}/acceptance-evidence
confirmation=RECORD_ACCEPTANCE_EVIDENCE
gate_code=<declared-gate>
evidence_digest=<sha256>
```

Read the current gate state without changing it at
`GET /api/v1/admin/autonomous-operations/operators/{operator}/acceptance-readiness`.

Operator enable requests return `409 acceptance_incomplete` until every
declared gate is present. Disabling remains available at any time. Enabling an
accepted operator does not bypass global manual mode, which remains on through
shadow qualification.

Rollback an application SHA only through `pwc-rollback` with the failed SHA
fence. After rollback, verify `/health`, `/`, one SPA route, one API route, and
the affected operator probe. Monitoring stays active; source repair never
silently retries a third chat attempt or an ambiguous CRON repair.
