# Deployment

Production and staging use the same immutable-release mechanism. Each
environment selects one complete backend-plus-frontend release through an
atomic `active` slot; `current` records that release and `previous` is its only
rollback target.

## Topology

```text
/srv/paperswithcode/
  repository.git
  .venv
  runtime-lock.sha256
  runtimes/<uv-lock-sha256>/
  releases/<sha12>-<environment>/
  environments/{production,staging}/
    current
    previous
    active -> slots/{blue,green}
    slots/{blue,green}/
      release -> ../../../releases/<release-id>
      backend.sock -> /run/paperswithcode/<environment>-<slot>.sock

/etc/paperswithcode/{production,staging}.env
/etc/paperswithcode/production-cron.env
/var/lib/paperswithcode/{shared,production,staging}
```

Nginx resolves backend requests through `active/backend.sock` and static files
through `active/release/frontend-dist`. New connections therefore move
together when `active` is replaced, while established SSE connections remain
attached to the old Unix socket. Each slot runs from the immutable runtime
whose ID is the release's `uv.lock` SHA-256. The legacy shared `.venv` and
fixed-port services remain a migration fallback until both environments have
passed a slot rollback window. Public staging is static and gated to
allowlisted project contributors and admins; it never runs Vite or HMR.

Both environments read the live `public` catalog and shared thumbnail mirror.
Staging connects as `pwc_staging`, can select catalog rows, and can write only
environment-owned user, workflow, and chat rows in the `staging` schema.

## Commands

Read-only status:

```bash
pwc-status
python deploy/topology_audit.py --json
```

Deploy:

```bash
sudo pwc-deploy staging <commit-or-ref>
sudo pwc-deploy production <commit-or-ref> --confirm DEPLOY_PRODUCTION
```

After changing a protected environment file, refresh an already-current release
through the same inactive-slot qualification, atomic cutover, drain, smoke, and
rollback path:

```bash
sudo pwc-deploy staging <exact-current-sha> --refresh-environment
sudo pwc-deploy production <exact-current-main-sha> \
  --refresh-environment --confirm DEPLOY_PRODUCTION
```

The refresh mode accepts only the active release, always starts the inactive
slot with the updated environment, and preserves the existing `previous`
release pointer.

Install production Langfuse credentials from the root-owned protected source
without printing or manually copying them, then refresh the active release:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/production.env --production-langfuse-only
sudo pwc-deploy production <exact-current-main-sha> \
  --refresh-environment --confirm DEPLOY_PRODUCTION
```

The installer requires a mode-`0600` source, rejects staging-key reuse, and
changes only the three Langfuse connection values plus the tracing flag.

Production accepts only commits reachable from `origin/main`. Every slot deploy
builds the selected frontend profile and immutable runtime, starts the inactive
slot, checks its exact release/runtime/slot identity, validates rolling gateway
and database compatibility, and runs direct-socket checks before atomically
switching `previous`, `current`, and `active`. A failed live smoke restores all
three pointers. A successful activation drains the displaced slot without
blocking transcript callbacks; if streams remain at the reporting deadline the
result is `success-with-draining` and `pwc-reap` finishes cleanup later.

Production chat remains disabled when source is merely landed or deployed with
`PWC_CHAT_ENABLED=false`. A separately authorized protected configuration
change to `true` causes the next new exact-SHA production release to build chat
into both backend and frontend manifests with the active immutable runtime
descriptor. The deploy rejects an existing same-SHA release whose activation
mode differs, so operators must use a new exact source SHA rather than mutate an
immutable bundle. Runtime readiness still fails closed until every production
chat prerequisite is configured. A disabled production release may contain the
sealed, production-isolated OpenRouter contract, but funded dispatch, public
admission, sandbox admission, and the blank pool remain false until the guarded
activation step changes all four together.

For the one-time migration from a legacy service, install the committed tools
and slot units. A source-only compatibility landing may use the explicit
staging-only bridge mode before any slot exists, but only when `uv.lock`
matches the installed shared runtime:

```bash
sudo python deploy/install_deploy_tools.py <exact-sha>
sudo python deploy/install_host_layout.py
sudo pwc-deploy staging <exact-sha> --legacy-bridge
sudo pwc-deploy staging <current-sha> --qualify-only
```

Production may use the same bridge only with the explicit production
confirmation when its current legacy release predates the slot operator
endpoints:

```bash
sudo pwc-deploy production <exact-main-sha> \
  --legacy-bridge --confirm DEPLOY_PRODUCTION
sudo pwc-deploy production <exact-main-sha> \
  --qualify-only --confirm DEPLOY_PRODUCTION
```

`--legacy-bridge` is rejected after nginx or an active slot is present and can
never mutate the shared dependency set. Production additionally requires the
candidate to be reachable from `origin/main`. Qualification creates
`active -> slots/blue` but leaves live nginx and the legacy service
unchanged. Applying the checked-in active-slot nginx template is a separately
authorized `pwc-nginx` operation. After that one-time cutover, verify both
staging hosts and run the ordinary exact-SHA slot deployment. After its live
smoke succeeds, that deployment gracefully retires only the legacy staging
service; a failure to stop it is recorded as `legacy-retirement-pending`
without rolling back an otherwise healthy slot activation.
`--defer-public-smoke` is retired.

Rollback:

```bash
sudo pwc-rollback staging
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
sudo pwc-reap staging
```

Nginx has a separate lifecycle:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

It displays the effective diff, runs `nginx -t`, reloads, and smokes the
selected host. Ordinary deploys never edit or reload nginx.

Install deployment tooling only from committed source:

```bash
sudo python deploy/install_deploy_tools.py <commit>
```

## Staging sandbox-chat bridge

The sandbox chat bridge has additional fail-closed prerequisites:

1. Publish the standalone CLI release and verify its checksums and provenance.
2. Build the Modal image from that committed source, then commit the emitted
   immutable `im-...` image ID as `MODAL_IMAGE_ID`. A source revision with an
   empty ID cannot pass release validation.
3. Provision TLS for `chat-gateway-staging.paperswithcode.co`, install the
   committed nginx template with the explicit `pwc-nginx staging` lifecycle,
   and set `PWC_CHAT_GATEWAY_URL` to
   `https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway`.
   The dedicated host exposes only the capability-authenticated gateway
   routes, including the anonymous read-only HF catalog route and the bounded
   artifact preparation/publication routes.
4. Apply `add_chat_sandbox_runtime.sql`, `add_chat_turn_latency.sql`,
   `add_chat_sandbox_pool.sql`, `add_chat_active_cost.sql`,
   `add_chat_user_billing.sql`, `add_chat_qualification_metadata.sql`,
   `add_chat_openrouter_user_budget.sql`, and
   `add_chat_sandbox_spend_cap.sql`, `add_chat_web_search.sql`, and
   `add_chat_hf_catalog.sql`, `add_chat_reasoning_effort.sql`, and
   `add_chat_ttft_profiles.sql`, `add_chat_sandbox_egress_policy.sql`,
   `add_chat_artifacts.sql`, `expand_chat_artifact_foundation.sql`,
   `allow_chat_latex_paper_restore_digests.sql`,
   `add_chat_latex_paper_figure_storage.sql`,
   `add_chat_latex_repair_provenance.sql`, and
   `add_chat_warm_assignment_race.sql` as
   PostgreSQL superuser with
   `search_path=staging,public`. The guarded migrations refuse any other schema,
   assign the new tables to `pwc_staging_owner`, grant `pwc_staging`, and
   revoke the production application role. The pool migration remains required
   even while `PWC_CHAT_BLANK_POOL_ENABLED=false`, because readiness validates
   the rollback-safe audit schema before pool activation.
5. Keep `PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED=false`; snapshot activation is
   outside the latency project and requires a separate approved plan. V1 uses
   Modal's isolated, automatically reclaimed ephemeral disk; PID and memory
   ceilings remain hard qualification probes.

Posterly's additive gateway contract uses one zero-assignment bridge release.
Deploy the first gateway-29 release with `POSTERLY_ENABLED=false`; only after
that release is both current and the rollback target accepts contract 29 may a
second exact-SHA release set `POSTERLY_ENABLED=true`. The bridge contains the
image, schema, storage provenance, and routes, but the launcher keeps artifact
admission and publication disabled.

Staging web search uses a server-owned Exa key and remains fail-closed unless
the feature flag, protected credential, monthly circuit, database tables, and
immutable worker contract are all ready. Install or rotate only the staging
credential from a protected source without printing it:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env --staging-web-search-only
```

The application records content-free attempt, success/failure, latency, result
count, provider-reported cost, and opaque-owner concentration telemetry. The
admin dashboard warns at 1,000 provider attempts and the application circuit
opens at 1,200 per UTC month; configure Exa account-level paid-tier spend alerts
as the outer backstop. For emergency abuse response, set
`PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST` to a comma-separated hostname list and
redeploy the exact staging release. Key rotation is the same narrow operation
followed by `pwc-deploy staging <exact-current-sha> --refresh-environment` when
the active source SHA is unchanged. These staging steps never enable or mutate
the production web-search feature.

After production rollout is explicitly approved, install the same bounded
configuration from production's server-owned Exa key, then deploy or refresh
the intended exact production release:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-web-search-only
```

GitHub repository previews use the server-owned GitHub token rather than
exposing it to browsers. Install or rotate only the staging copy from a
protected source, then deploy or refresh the intended exact staging release:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env --staging-github-only
```

The worker system prompt embeds
`backend/chat_sandbox_worker/PWC_CLI_SKILL.md` plus the bounded area/task
taxonomy in `backend/chat_sandbox_worker/TASK_CATALOG.md` and the bounded,
area-grouped method snapshot in
`backend/chat_sandbox_worker/METHOD_CATALOG.md`. The hourly
`sync-pwc-cli-skill.yml` workflow compares the skill with
`huggingface/pwc-cli:standalone_cli/SKILL.md` and commits validated skill changes
directly to `main`. A concurrent update to `main` is rebased before push; a
conflict fails the run so the next hourly checkout can retry from a clean base.
After a skill sync, publish a new immutable Modal image, commit its
`MODAL_IMAGE_ID`, and deploy that exact commit to staging; an application deploy
cannot alter an already-published worker image.

`sync-chat-task-catalog.yml` refreshes the checked-in fallback
`TASK_CATALOG.md` from the production taxonomy API every 15 minutes and on
manual dispatch. At runtime, both worker harnesses fetch every page of the task
taxonomy through the trusted capability-backed catalog gateway and replace the
baked prompt section before each turn. Persistent sessions are recreated when
that live catalog changes. The fallback therefore stays useful during a
catalog-gateway failure without making prompt freshness depend on a Modal image
publication or application deployment. The prompt also requires task-scoped
SOTA questions to resolve the canonical task and its ranked benchmarks before
using broad paper or model search.

Chat sandboxes are pinned to Modal's `eu-west` compute region so the persistent
worker stays near the dedicated gateway and PostgreSQL host. A region change is
a worker-contract change: publish a new immutable image, deploy it to staging,
and repeat the exact-release latency and reliability qualification.
The qualified staging capacity shape requests 0.5 physical CPU cores and
512 MiB, with hard limits of one core and 2 GiB; the higher CPU request avoids
scheduler tail latency without changing the circuit's worst-case resource rate.
Reapplying the qualified capacity shape preserves an explicit blank-pool toggle;
pool enablement and disablement remain separate operator actions.

Before any non-zero rollout, deploy two distinct zero-percent bridge commits so
both `current` and `previous` understand `modal_cli`. Then run the operator-only
infrastructure qualification from the selected immutable release:

Pi prewarming and blank-pool admission are independent protected staging
controls. Toggle Pi prewarming without changing admission, then refresh the
exact active release through the immutable deployment path:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-chat-pi-prewarm-enable-only
sudo pwc-deploy staging <exact-current-sha> --refresh-environment
```

Use `--staging-chat-pi-prewarm-disable-only` for the independent rollback. The
existing `--staging-chat-pool-enable-only` and
`--staging-chat-pool-disable-only` modes control admission separately.

Production Pi prewarm is a separately authorized chat change. It reuses the
qualified DeepSeek Hugging Face `:baseten` / `low` profile and requires the
already-admitted one-blank production pool. It does not enable Luna, Gemini, or
any other alternative model:

```bash
sudo /srv/paperswithcode/.venv/bin/python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-chat-pi-prewarm-enable-only \
  --confirm ENABLE_PRODUCTION_CHAT_PI_PREWARM
sudo pwc-deploy production <exact-current-main-sha> \
  --refresh-environment --confirm DEPLOY_PRODUCTION
```

Use `--production-chat-pi-prewarm-disable-only` with
`--confirm DISABLE_PRODUCTION_CHAT_PI_PREWARM` for the independent rollback.

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_sandbox \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --starts 100 --parallel 4 --snapshot-samples 0 --resource-probes \
  --confirm QUALIFY_STAGING_SANDBOX
```

The runner creates only tagged disposable qualification sandboxes. It verifies
the pinned CLI, dedicated-gateway reachability without a capability, blocked
general egress, agent/broker UID and `/proc` isolation, and cancellation by
sandbox termination. Directory snapshots remain disabled for this latency
project. It emits timings and no environment values, commands, prompts,
credentials, or tool output. Full model,
SDK compaction, resume, edit/retry, and citation qualification still runs
through authenticated staging chats before increasing the rollout percentage.

### Private LaTeX paper staging gate

After the private artifact and compiler switches have been enabled in staging,
run the paper gate through the active staging Unix socket. It requires Luna to
be both the discovered staging API default and the explicitly selected model;
the runner never falls back to whichever model happens to be first in a local
configuration.

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_latex_paper_staging \
  --admin-subject <allowlisted-staging-admin-subject> \
  --admin-username <operator-name> \
  --qualification-owner operator:pi-qualification:paper-<run-id> \
  --model gpt-5.6-luna@openai \
  --expect enabled \
  --confirm QUALIFY_STAGING_LATEX_PAPER
```

The normal enabled run uses an operator-only disposable chat and deletes every
created session in `finally`. Its report contains only check names, booleans,
and elapsed milliseconds—never prompts, answers, sources, diagnostics,
artifact IDs, share IDs, URLs, credentials, or trace payloads. It exercises the
deterministic `/write-paper` and natural-prompt activation paths, ordinary-turn
non-activation, structural citations, first compile, Preview/Files, editing,
figure upload, optimistic conflicts, failed-source/stale-PDF behavior, history
restore, private exports, public-share omission, actual
`/sessions/archive-oldest` plus owner re-read, responsive Preview/Files UI, and
deletion. The controlled failed source is also repaired through exactly three
Luna repair receipts; it only passes when the failed source and last good
preview remain unchanged and the descriptor reports an exhausted repair budget.

For the telemetry-content gate, add
`--telemetry-canary <opaque-random-marker>` to the normal enabled command (and
to the preserve run when using the two-phase sequence). The runner places that
marker in the private authoring input and an owner-only LaTeX comment, then
checks the current owner source ZIP contains it without echoing the marker or
any source bytes. The report contains only the structural
`telemetry_canary_owner_source_present` result. It does not query Langfuse or
claim the telemetry gate passed: use the same protected marker in the separate
Langfuse scan and retain its content-free absence evidence before accepting the
gate.

The kill-switch evidence is an intentionally separate, two-phase sequence.
First run the normal enabled command above so archive behavior is qualified.
Then use the same dedicated owner value for a second enabled preparation run,
adding `--preserve-for-kill-switch`. That variant never calls
`archive-oldest`: archiving would hide the sole active historical session that
the disabled phase must list. It deletes all secondary sessions and preserves
the one primary Luna paper only if every executed deterministic preparation
check passed; otherwise `finally` deletes everything.

After an operator has independently disabled all three paper/compiler switches
through the documented staging host-configuration procedure, run the disabled
historical phase with that exact same owner:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_latex_paper_staging \
  --admin-subject <allowlisted-staging-admin-subject> \
  --admin-username <operator-name> \
  --qualification-owner operator:pi-qualification:paper-<run-id> \
  --model gpt-5.6-luna@openai \
  --expect disabled \
  --verify-historical \
  --confirm QUALIFY_STAGING_LATEX_PAPER
```

This phase refuses anything other than exactly one active session for that
owner. It reads the private session descriptor and source ZIP, verifies a
disabled `/write-paper` turn creates no artifact, then deletes that session.
Neither phase changes feature flags. The runner intentionally reports (and
exits nonzero for) any unexercised external telemetry-content gate; an enabled
report also keeps rollback unmet until the disabled historical phase succeeds.
Do not turn those false values into a pass by supplying a synthetic report.
Keep the switches off if either phase fails.

The release-scoped reliability gate uses explicit qualification metadata rather
than synthetic usernames. Run the naturally paced SLO cohort and the broader
follow-up/cancellation matrix from the active immutable release, then audit the
same exact release and start time:

```bash
uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.qualify_chat_latency \
  --sessions 25 \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm QUALIFY_STAGING_CHAT_LATENCY

uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.qualify_chat_soak \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm QUALIFY_STAGING_CHAT_SOAK

uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.audit_chat_soak \
  --started-at <candidate-activation-time> \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm AUDIT_STAGING_CHAT_SOAK
```

The auditor reads all legacy and blue/green staging journal units, reports only
content-free error codes and aggregates, scopes health and SLO gates to the
active release, and keeps insufficient pre-soak samples distinct from failures.
Production and staging expose DeepSeek V4 Flash under one stable public model
ID. `PWC_CHAT_DEEPSEEK_V4_FLASH_PROVIDER` selects the user-funded Hugging Face
route `deepseek-ai/DeepSeek-V4-Flash-0731:baseten` by default or the
server-funded OpenRouter route `deepseek/deepseek-v4-flash-0731`. Both routes
remain registered at the private gateway so a rolling switch does not invalidate
already-issued capabilities. Hugging Face turns use each authenticated user's
OAuth inference credential and are billed to that user's selected HF billing
account.

When OpenRouter is selected, its environment-isolated credentials, keyrings,
ledgers, and gateway accounting remain active. The explicit
`provider.sort=throughput` request policy is equivalent to the `:nitro` suffix
while preserving the stable route used by durable accounting. Admission checks
provider-authoritative monthly usage before each funded turn, and the provider
key must prove an exact monthly `$200` environment workspace limit.
Durable PostgreSQL reservations enforce a separate `$1` per-user ceiling on
staging and a `$5` per-user ceiling on production before each funded gateway
dispatch. Allowlisted staging admin subjects retain the `$5` ceiling. The same
reservation transaction enforces
30 funded provider calls per user and 80 globally per rolling 10 minutes, plus a
guarded `$10` UTC-day application circuit. Settled calls count at actual cost;
in-flight and unknown-cost calls count at their conservative reservation. Only
the staging-only `operator:pi-qualification:` identity may bypass these short
window and daily circuits so explicitly authorized load tests do not weaken or
misrepresent the public protections. Monthly per-user and provider workspace
limits still apply. Production exposes the same allowance and BYOK product
behavior only after its production schema and protected secrets pass closed
qualification; it never reuses staging credentials or state.

Automatic title generation uses the server-funded OpenRouter credential and
routes `deepseek/deepseek-v4-flash-0731` through Nitro throughput sorting. It
reserves against a persistent,
environment-isolated `$25/month` title circuit before dispatch. Missing
credentials, ledger uncertainty, provider failure, or exhaustion falls back to
a local prompt-derived title. Production uses its production research key but a
separate production `$25` title ledger and circuit. Neither environment may
read or borrow the other's title or research budget.

Production additionally uses the allowlisted
`monitor_chat_operational_alerts` job once per minute. It advances a protected
journald cursor without persisting raw log lines and emits only signal names,
counts, release identity, timestamps, and runbook metadata. Critical runtime
patterns alert immediately. DeepSeek provider failures alert after at least
five failures and a 50% failure rate in a five-minute window, then send one
recovery event after a fully clean five-minute window. Primary failure routes
the same content-free event to the fallback destination. The timer is safe to
enable while production chat is disabled because the job reports `dormant`
without reading chat state or sending alerts.

The committed timer is installed with the deployment tools but is never enabled
implicitly. Enabling it is a reviewed production preparation mutation:

```bash
sudo systemctl enable --now pwc-chat-alert-monitor.timer
```

An enabled production-chat deployment fails closed unless this timer is
enabled. The timer invokes only the `pwc-cron` allowlist, and only this job's
transient unit receives read access to the system journal.

Seal the reviewed production preparation inputs into a root-owned, non-loaded
overlay. The named mode-`0600` Modal profile is imported in memory, so its token
pair is never printed or copied into the local source input:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/production.env \
  --production-chat-seal-only \
  --modal-profile pwc-production \
  --confirm SEAL_PRODUCTION_CHAT_PREPARATION
```

The helper rejects a missing or group/world-readable Modal profile, incomplete
credentials, conflicts with an explicitly configured pair, unsafe alert URLs,
an invalid budget attestation, a missing/invalid OpenRouter keyring contract,
or reuse of the staging OpenRouter key. It generates or preserves production-
only BYOK encryption and tracking secrets, fixes the `$5`/`$200` policy, and
writes only
`/etc/paperswithcode/production-chat-prepared.env`; no service loads that file
implicitly.

Production uses the Team service user `pwc-production`, which must be
Contributor on only `pwc-chat-production` and retain No Access on `main` and
every other Environment. The provider-side production Environment budget is
$125 per billing period, between the durable $100 application circuit and the
$250 workspace backstop. Rotate the sealed pair only after both `current` and
`previous` production releases accept the Team policy, so direct rollback does
not depend on restoring an older owner credential.

After a disabled production bridge release contains the qualification tooling,
exercise all sandbox, title, provider-health, and runtime-alert transitions
without creating provider compute. The sealed overlay must have been produced
by the protected preparation helper and is loaded only into this transient
process:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-production --gid=pwc-production \
  --working-directory=/srv/paperswithcode/environments/production/current \
  --property=EnvironmentFile=/etc/paperswithcode/production.env \
  --property=EnvironmentFile=/etc/paperswithcode/production-chat-prepared.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_sandbox_spend \
  --environment production --qualification-id <unique-id> \
  --confirm QUALIFY_PRODUCTION_CHAT_SPEND
```

Record human acknowledgement from both independently routed destinations. The
synthetic rows remain environment-qualified and contain no prompt, answer,
credential, capability, or provider compute.

Before sealing an OpenRouter-capable production release, apply
`backend/database/migrations/add_chat_openrouter_user_budget_production.sql` as
PostgreSQL superuser with `search_path=public`. The guarded migration owns the
four production OpenRouter tables and audit sequence with
`paperswithcode_user`, grants only the production application role, and
explicitly revokes `pwc_staging`. Audit table/sequence ownership, columns,
constraints, and both role boundaries before continuing. This migration does
not enable chat or dispatch a provider request.

The common production chat schema must also include the guarded public
counterparts `add_chat_web_search_production.sql`,
`add_chat_hf_catalog_production.sql`, and
`add_chat_reasoning_effort_production.sql`. They keep disabled feature columns
compatible with the shared ORM, complete OpenRouter reasoning accounting, own
new objects with `paperswithcode_user`, and deny staging writes. Apply them in
that order after the base chat/OpenRouter tables exist and before opening
production admission.

Chat session reads also require the common typed-artifact foundation even when
paper authoring is disabled. Apply `add_chat_artifacts.sql` and then
`expand_chat_artifact_foundation.sql` with `search_path=public` before deploying
an ORM release that includes the artifact models.

Enabled immutable chat releases derive inline paper mentions and the bounded
read-only Hugging Face catalog capability from the release manifest in both
environments. Disabled releases force both capabilities off, so an ordinary
release rollback also restores their prior activation state without editing
protected configuration.

Only after the two disabled production bridge releases are active, the sealed
bundle has passed qualification, and the exact activation SHA has separate
production authorization, install the same revalidated bundle into the live
production environment. This changes protected configuration but does not
restart a service, deploy a release, open public or sandbox admission, or enable
the blank pool:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/production.env \
  --production-chat-install-only \
  --confirm INSTALL_PRODUCTION_CHAT_PREPARATION
```

The installer reads only the previously sealed root-owned bundle, rejects
missing, stale, or added keys, and revalidates title metadata, Modal policy,
alert separation, capacity, and the isolated OpenRouter accounting contract
before an atomic write. Funded dispatch and all three admission/capacity gates
remain false, so the same installed configuration remains rollback-compatible
without editing secrets during an incident.

After the enabled release passes production smoke with admission closed, open
funded dispatch, public admission, sandbox admission, and the one-blank pool
together through the guarded configuration path. This revalidates the exact
sealed bundle, rejects drift, and does not restart a service; refresh the exact
active release so the new activation state is loaded:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/production.env \
  --production-chat-admission-enable-only \
  --confirm ENABLE_PRODUCTION_CHAT_ADMISSION
```

Install the staging title policy from a protected local environment file through
the narrow staging-only helper. It validates the exact owner, environment,
model, provider, and `$25` circuit and does not write production. Legacy HF
credential fields remain temporarily required for rollback compatibility but
are not used by the OpenRouter title call:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/staging.env \
  --staging-title-only
```

The separate staging OpenRouter helper configures only its provider key:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-openrouter-only
```

Direct OpenAI uses a separate staging project credential. Put only
`OPENAI_API_KEY` in a root-owned mode-`0600` source file; the installer rejects
the credential if it matches either production OpenAI key. It writes the key
only to the trusted staging gateway environment, enables the direct route, and
sets the single blank profile to direct Luna/low without changing production:

Gateway contract 30 requires one direct-disabled bridge release first. Deploy
that bridge with the historical OpenRouter Luna/low profile, then enable the
protected direct configuration and deploy a second distinct contract-30 release.
This keeps both the forward drain and automatic rollback paths executable.

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /root/protected/staging-openai.env \
  --staging-openai-direct-only
sudo pwc-deploy staging <exact-current-sha> --refresh-environment
```

Configuration-first rollback preserves the ledger and credential while
disabling direct dispatch and restoring the historical OpenRouter Luna/low
profile for the prior staging release:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /root/protected/staging-openai.env \
  --staging-openai-direct-disable-only
sudo pwc-deploy staging <exact-current-sha> --refresh-environment
```

When the provider-enforced workspace limit changes, retain a protected copy of
the prior staging environment until two distinct staging releases accept the
new exact limit. Deploy the first compatible release with the new environment,
then deploy a second compatible release before retiring the protected copy. This
keeps both `current` and `previous` directly restartable through `pwc-rollback`.

The application fails closed if OpenRouter cannot prove the exact provider
guardrail, or if durable per-user accounting is unavailable. Staging runs
bounded reconciliation and retention maintenance daily. An operator can also
run the release-scoped maintenance script explicitly, including an intentional
encryption-key rotation batch:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.maintain_openrouter_accounting \
  --batch-size 100 --rotate-credentials
```

Generate a new active staging AES key and tracking secret without removing old
decryption versions, then deploy the intended release so processes load it:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-openrouter-secrets-rotate-only
```

After the explicit credential-rotation batch has re-encrypted every older row,
retire unused decryption versions in a separately reviewed environment change.

To retire the preview, use the provisioning command with
`--staging-openrouter-disable-only`. This leaves the ledger intact for
reconciliation and keeps Hugging Face-backed chat available.

## Production Excalidraw MCP App

Production bundles the reviewed same-origin MCP App host whenever production
chat is enabled, but the backend route, worker registration, and sandbox egress
remain disabled until both protected Excalidraw switches are enabled. The
official App HTML is accepted in production only when it matches the SHA-256
pinned in `backend/chat_sandbox_worker/mcp_app_providers.json`; staging retains
its compatibility-gated drift policy.

Enable the worker and App host together, then deploy the exact compatible
release so its frontend, backend, and newly compatible blank sandbox pool become
active atomically:

```bash
sudo /srv/paperswithcode/.venv/bin/python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-excalidraw-enable-only \
  --confirm ENABLE_PRODUCTION_EXCALIDRAW
sudo pwc-deploy production <exact-current-main-sha> --confirm DEPLOY_PRODUCTION
```

The independent feature rollback disables both switches before refreshing the
exact active release. This drains the Excalidraw egress profile and causes the
one-blank pool to refill with a compatible gateway-only sandbox:

```bash
sudo /srv/paperswithcode/.venv/bin/python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-excalidraw-disable-only \
  --confirm DISABLE_PRODUCTION_EXCALIDRAW
sudo pwc-deploy production <exact-active-sha> \
  --refresh-environment --confirm DEPLOY_PRODUCTION
```

Run the release-scoped live contract gate as `pwc-production` with the active
production environment. It records only endpoint status, tool names/digests,
latency, egress domains, and sanitized failure classes, and always terminates
its disposable sandbox:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-production --gid=pwc-production \
  --working-directory=/srv/paperswithcode/environments/production/current \
  --property=EnvironmentFile=/etc/paperswithcode/production.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_excalidraw_mcp \
  --release-dir /srv/paperswithcode/environments/production/current \
  --confirm QUALIFY_EXCALIDRAW_MCP
```

## Release cleanup

Remove releases and runtimes not referenced by either environment's
`current`/`previous` pointers or either running/draining slot:

```bash
sudo pwc-cleanup --confirm CLEAN_RELEASES
```

The cleanup command takes the same host mutation lock as deploy, rollback, and
reaping. Never remove a release or runtime directory by hand.

## Invariants

`release.json` stores the full SHA, build profile, build time, frontend
entrypoint, backend/frontend feature manifests, and rolling gateway/database
contracts. `features.json` lives
beside built `index.html`. Startup fails if a deployed shell references
`/src/main.tsx`, assets are missing, paths are relative or inside a release,
or feature manifests disagree.

While chat remains staging-only, production build and runtime configuration
disable it; its backend router is absent and `/chat` redirects home.
Production is the sole OAuth/session authority. It signs
`pwc_shared_session` with an Ed25519 private key and scopes the cookie to
`.paperswithcode.co`; staging receives only the public verification key.
The host-only `pwc_session` and `pwc_staging_session` cookies and their
distinct HS256 secrets remain temporarily readable for rollback compatibility.
Staging login redirects through the production callback, whose return
destinations are restricted to the production and staging HTTPS origins.

Codex add-evals and enrich-paper buttons are enabled only in production and
remain protected by Hugging Face admin authentication in both the frontend and
API. Production owns the writable catalog and receives the remote-job
credentials through its protected environment. Staging keeps both controls
disabled because its catalog role is read-only and it has no job credentials.
Each release launcher derives the non-secret capability flags from that
release's validated manifest, so rolling back also restores the matching
frontend/backend feature state.

Slot processes expose deployment status, drain, and undrain operators only
through their Unix socket. Checked-in nginx templates return 404 for those
paths. `pwc-status` shows each slot's service/socket state, immutable
release/runtime identity, drain counts, and the activation journal. A deploy
never edits or reloads nginx.

## Scheduled work and backup

GitHub Actions calls `sudo /usr/local/sbin/pwc-cron <registered-job>`. The
launcher runs as `pwc-cron`, loads production plus CRON-only configuration,
resolves `production/current`, records its release ID, and uses absolute
lock/log directories.

```bash
sudo pwc-cron status
pwc cron health refresh_paper_embeddings --strict --json
```

`pwc-postgres-backup.timer` remains at 03:15 UTC. It runs the backup script from
`production/current` as `pwc-cron`, dumps both `public` and `staging` with the
read-only `pwc_backup` role, verifies the local checksum and remote object
listing, keeps three local dumps, and keeps thirty remote dumps.

`pwc-curation-thumbnails.timer` invokes the allowlisted
`pwc-cron process_curation_thumbnails` command every minute. Web identities only
enqueue work on `paper_curation_jobs`; the timer's `pwc-cron` transient unit is
the curation path that enables thumbnail mutations and writes the shared
thumbnail mirror. Stale processing claims are recoverable, and an operator can
retry terminal failures once per invocation with
`sudo pwc-cron process_curation_thumbnails --retry-failed`.
Install the committed deploy tools and apply
`backend/database/migrations/add_curation_thumbnail_queue.sql` before enabling
the timer with `sudo systemctl enable --now pwc-curation-thumbnails.timer`.

The hourly GitHub Actions monitor uses the same
`deploy/smoke_test.py --monitor-subset` implementation as releases. It checks
the production SPA and hashed asset MIME types plus the staging health/auth
boundary without creating an authenticated session.

## Development

Use `uv run --env-file backend/keys.env ...` for local backend commands and
`npm run dev` for a localhost frontend. `start_services.sh` and
`stop_services.sh` are non-mutating retirement notices; `check_services.sh`
delegates to `pwc-status`.
