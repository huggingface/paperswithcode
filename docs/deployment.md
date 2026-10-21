# Deployment

Production and staging use the same immutable-release mechanism. Each
environment selects one complete backend-plus-frontend release through an
atomic `active` slot; `current` records that release and `previous` is its only
rollback target.

## Topology

```text
/srv/paperswithcode/
  repository.git
  deployment.lock
  python-runtime/                # base interpreter for the shared .venv
  .venv
  runtime-lock.sha256
  runtimes/<uv-lock-sha256>/
  runtimes/external-pi/<content-id>/
  releases/<sha12>-<environment>/
  environments/{production,staging}/
    current
    previous
    activation-journal.json
    active -> slots/{blue,green}
    slots/{blue,green}/
      release -> /srv/paperswithcode/releases/<release-id>
      backend.sock -> /run/paperswithcode/<environment>-<slot>.sock

/etc/paperswithcode/{production,staging}.env
/etc/paperswithcode/{production-cron,trending-cron}.env
/var/lib/paperswithcode/{shared,production,staging}

/srv/paperswithcode/mcp/
  repository.git                 # huggingface/pwc-cli mirror
  releases/<sha16>/
  environments/{production,staging}/{current,previous}

/etc/paperswithcode/mcp-{production,staging}.env
```

Nginx resolves backend requests through `active/backend.sock` and static files
through `active/release/frontend-dist`. New connections therefore move
together when `active` is replaced, while established SSE connections remain
attached to the old Unix socket. Each slot runs from the immutable runtime
whose ID is the release's `uv.lock` SHA-256. Both environments have migrated to
slots: the legacy fixed-port `paperswithcode-backend@<environment>` unit is
disabled (`pwc-status` reports `legacy_service: inactive`), and the shared
`.venv` remains only as a fallback interpreter for operator helpers. Public
staging is static and gated to allowlisted project contributors and admins; it
never runs Vite or HMR.

The external Pi worker is packaged independently under `runtimes/external-pi`
and runs beside each slot as `paperswithcode-<environment>-external-pi@<slot>`
(durable supervisor) and `paperswithcode-<environment>-external-pi-worker@<slot>`
(Node worker fleet). External admission serves browser chat in both
environments. Production enters or leaves the reviewed durable 32-turn profile
only through `configure_host_env.py --production-durable-external-enable-only`
(or `--production-durable-external-disable-only`) with the matching
`--confirm ENABLE_PRODUCTION_DURABLE_EXTERNAL` /
`DISABLE_PRODUCTION_DURABLE_EXTERNAL`, followed by an exact-SHA
`--refresh-environment`. The runtime identity covers the package manifest,
lockfile, TypeScript build inputs, canonical prompt inputs, and pinned Node
22.19.0 distribution contract. Packaging does not activate worker traffic. A
build uses a temporary directory, exact locked dependencies, a production
TypeScript build, production-dependency pruning, and an atomic rename.
`runtime.json` records contract `external-pi-v1`, source release, entry point,
Node identity, and a strict file-digest inventory. Reuse rejects mutable,
missing, extra, or digest-mismatched files. Each staging and production
`release.json` records the selected runtime ID, contract, and identity-schema
version (`external_pi_runtime`) so cleanup and rollback never recalculate a
historical identity with newer packaging rules. Protected releases of both
environments participate in external Pi retention. While
any protected pre-descriptor staging release remains, cleanup conservatively
retains the full external Pi namespace rather than guessing its identity;
descriptor-less production releases do not disable staging cleanup.
Dependency installation, build, pruning, and prompt rendering run under a live
aggregate byte and inode monitor. A dedicated supervisor child becomes a Linux
child subreaper and tracks only the launched build lineage by PID and process
start time, so containment survives process-group changes, new sessions, double
forks, and an early direct-parent exit without adopting unrelated deploy-process
children. Direct-parent completion, a bound breach, or timeout stops revalidated
descendants through PID handles and reaps them before the runner returns. The
one-shot supervisor then exits, and failed builds discard the temporary runtime.

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
With the external Pi lifecycle enabled, the next deploy or rollback runs that
reap itself before it touches the displaced slot again.

Production chat is enabled by the protected `PWC_CHAT_ENABLED=true`. Each new
exact-SHA production release builds chat into both backend and frontend
manifests only when that protected value is set, and the deploy fails closed
unless `pwc-chat-alert-monitor.timer` and
`pwc-cron-run-chat-synthetic-probe.timer` are enabled. The deploy rejects an
existing same-SHA release whose chat activation mode differs, so a change of
mode needs a new exact source SHA rather than a mutated immutable bundle.
Runtime readiness still fails closed until every production chat prerequisite
is configured.

`--qualify-only` prepares the candidate in the inactive slot (result
`candidate-prepared`) after the rolling-compatibility check, without switching
`active`. `--legacy-bridge` (the one-time migration from the fixed-port
services) and the matching fixed-port rollback are retired and refused, as is
`--defer-public-smoke`.

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

`pwc-deploy` runs as root, but never runs release-controlled code as root.
The frontend `npm ci`/`npm run build`, the release chat descriptor import, the
runtime `uv sync`, the external Pi worker build, and the MCP component's
`uv sync` run as the unprivileged `pwc-build` account
(`deploy/build_sandbox.py`). Deploy smoke tests, which run the release's
runtime interpreter, run as that environment's own `pwc-<environment>` account. Each step uses a
cleared environment, a throwaway HOME and package cache, no supplementary
groups or capabilities, and `no_new_privs`. Root takes the build tree back
(killing leftover `pwc-build` processes first) before inspecting or publishing
it. `install_deploy_tools.py` creates the account; a deploy fails closed if it
is missing.

## First-party MCP component

The remote MCP server is an independent immutable component even though its
lifecycle code lives in this monorepo. Its source comes from an exact commit in
the separate `huggingface/pwc-cli` mirror. A release archives only
`mcp_server/` and `standalone_cli/`, installs the committed `mcp_server/uv.lock`,
and records the source SHA, lock and artifact hashes, package and SDK versions,
protocol matrix, health schema, and fixed catalog URLs in `manifest.json`.
Production accepts only commits reachable from the MCP mirror's `origin/main`.

Use the existing commands with an explicit component selector:

```bash
pwc-status --component mcp
sudo pwc-deploy staging <exact-pwc-cli-sha> --component mcp
sudo pwc-deploy staging <exact-pwc-cli-sha> --component mcp --qualify-only
sudo pwc-deploy production <exact-main-pwc-cli-sha> --component mcp \
  --confirm DEPLOY_PRODUCTION
sudo pwc-rollback staging --component mcp
sudo pwc-rollback production --component mcp --confirm ROLLBACK_PRODUCTION
sudo pwc-cleanup --component mcp --confirm CLEAN_RELEASES
```

Site and MCP mutations share the site deployment lock. Candidate qualification
runs as `pwc-mcp` on a temporary loopback port and must pass health, initialize,
tool discovery, and a one-result read-only catalog call before activation.
Activation and rollback enable `paperswithcode-mcp@<environment>.service` before
restarting it, so the active release starts again after a host reboot. The
permanent service is one process on loopback (`8002` production, `8003` staging),
with `MemoryMax=768M`, `CPUQuota=75%`, `TasksMax=64`, protected system paths,
and no database or bucket credentials. The installer requires at least 512 MiB
of free release capacity.

The root-owned mode-`0640` files `mcp-production.env` and `mcp-staging.env` have
different API URLs, Host allowlists, ports, and cursor secrets. They must contain
`PWC_MCP_CURSOR_KEY_CURRENT`; during rotation, move the old value to
`PWC_MCP_CURSOR_KEY_PREVIOUS`, install a fresh current value without printing
either secret, deploy, wait longer than the one-hour cursor lifetime, then clear
the previous value. Never load `backend/keys.env` into this service. Both
environments read the catalog through nginx's loopback-only blue/green bridge
(`http://127.0.0.1:8010/api/v1` for production, `http://127.0.0.1:8011/api/v1`
for staging), so MCP traffic never leaves the host or shares the public per-IP
catalog rate limits. Changing a bridge needs `pwc-nginx` for the listener,
`install_host_layout.py` to reconcile `PWC_API_URL` in the MCP env file, and an
MCP redeploy to restart the service on the new URL. A failure restores the
previous pointer and re-smokes it. If no prior release exists, the failed unit
is stopped.

The public route is activated separately with `pwc-nginx`; an application or
MCP deploy never reloads nginx. The checked-in nginx template maps browser
`Accept: text/html` requests for `/mcp` to the documentation page, protocol
requests to the loopback service, and `/mcp/health` to health. It strips client
cookies and authorization and uses a content-free MCP access log. Existing
catalog/API infrastructure has its own request logging and retention policy, so
this is not an end-to-end no-logging claim.

Qualification fails closed unless health's protocol value equals the protocol
actually negotiated by initialize. After an MCP deploy, smoke browser `/mcp`,
`/mcp/health`, and the MCP protocol (initialize, discovery, a read-only call).
Roll back nginx immediately for routing/content-negotiation failures; roll back
the MCP component for readiness, protocol, error-rate, latency, saturation, or
memory regressions. The Hugging Face Space is a non-canonical fallback, never
the URL clients should save.

## Chat runtime

Chat runs in both environments with fail-closed prerequisites:

1. Sandbox executor changes need a new Modal image built from committed source;
   commit the emitted immutable `im-...` ID as `MODAL_IMAGE_ID` (staging) or
   `PRODUCTION_MODAL_IMAGE_ID` in `backend/chat_sandbox_worker/contract.py`. A
   source revision with an empty ID cannot pass release validation.
2. Each environment has a dedicated gateway host
   (`chat-gateway[-staging].paperswithcode.co`) and executor host
   (`chat-executor[-staging].paperswithcode.co`) in the checked-in nginx
   templates, applied only through `pwc-nginx`. The gateway host exposes only
   the capability-authenticated gateway routes. Executor hostnames must be
   **proxied** Cloudflare records at one subdomain level (the host firewall
   admits web traffic only from Cloudflare, and Universal SSL covers only one
   level).
3. Chat schema migrations live in `backend/database/migrations/` and are never
   applied by an application deploy. Staging migrations run as PostgreSQL
   superuser with `search_path=staging,public`; the guarded migrations refuse
   any other schema, assign new tables to `pwc_staging_owner`, grant
   `pwc_staging`, and revoke the production application role. Their
   `*_production.sql` counterparts run with `search_path=public`, own objects
   with `paperswithcode_user`, and revoke `pwc_staging`.
4. Keep `PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED=false`; snapshot activation
   requires a separate approved plan. Sandboxes use Modal's isolated,
   automatically reclaimed ephemeral disk.

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
admin dashboard warns at 5,000 provider attempts and the application circuit
opens at 6,000 per UTC month (runtime validation caps it at 6,000); configure
Exa account-level paid-tier spend alerts
as the outer backstop. For emergency abuse response, set
`PWC_CHAT_WEB_SEARCH_DOMAIN_DENYLIST` to a comma-separated hostname list and
redeploy the exact staging release. Key rotation is the same narrow operation
followed by `pwc-deploy staging <exact-current-sha> --refresh-environment` when
the active source SHA is unchanged. These staging steps never enable or mutate
the production web-search feature.

Production web search is enabled with the same bounded configuration from
production's own server-owned Exa key. Install or rotate it, then deploy or
refresh the intended exact production release:

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

The worker system prompt is rendered from the files listed in
`PROMPT_INPUTS` in `deploy/external_pi_runtime.py`, including
`backend/chat_sandbox_worker/PWC_MCP_SKILL.md`, `PWC_CLI_SKILL.md`, the bounded
area/task taxonomy in `TASK_CATALOG.md`, and the area-grouped method snapshot in
`METHOD_CATALOG.md`. They are part of the external Pi runtime identity, so a
prompt or skill change reaches chat with the next exact-SHA `pwc-deploy`; a new
Modal image is needed only for sandbox executor changes. The hourly
`sync-pwc-cli-skill.yml` workflow compares the CLI skill with
`huggingface/pwc-cli:standalone_cli/SKILL.md`. Because that text is appended
verbatim to the system prompt, a validated change is never pushed to `main`.
The workflow pushes it to an `automation/sync-pwc-cli-skill-<upstream-sha>`
branch and opens a pull request for review, one per upstream commit.

`sync-chat-task-catalog.yml` refreshes the checked-in fallback
`TASK_CATALOG.md` from the production taxonomy API every 15 minutes and on
manual dispatch. At runtime, both worker harnesses fetch every page of the task
taxonomy and the complete framework list through the trusted capability-backed
catalog gateway and replace the baked prompt section before each turn. Persistent sessions are recreated when
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

Durable turn dispatch (`PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED=true`) is on in
both environments and is part of the durable external Pi profile. The staging
gates remain available for requalification from the active immutable release:
`backend.scripts.qualify_chat_durable_dispatch` with `--audit-disabled-only`
(refuses an enabled bridge) or `--qualify-enabled-only` (refuses a disabled
bridge) and `--confirm QUALIFY_STAGING_DURABLE_DISPATCH`; it runs the catalog
inspection in a database-enforced read-only transaction and never calls a
model, provider, sandbox, or user-visible chat route. Run gates as
`pwc-staging` with `/etc/paperswithcode/staging.env` and the release's
`runtimes/<uv-lock-sha256>/bin/python`, with `PWC_RELEASE_ID` and
`PWC_CHAT_WORKER_CONTRACT_VERSION` taken from the release's `release.json`.
`configure_host_env.py --staging-chat-durable-dispatch-{enable,disable}-only`
toggles only that flag; follow it with an exact-SHA `--refresh-environment`.

### Chat capacity tiers

The durable external Pi profile serves one of two reviewed capacity tiers per
environment. A tier fixes four values together: admitted concurrent turns
(`PWC_CHAT_MAX_CONCURRENCY`), the eight-replica fleet's total sessions
(`PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS`, so each replica serves
`tier / 8`), OpenAI global concurrency, and the OpenAI ten-minute call
allowance. Runtime validation accepts only these shapes once external Pi
admission is on; deploy tooling sizes replicas from the protected value and
recognises the other tier's workers while a slot drains.

| Tier | Turns | Replicas × sessions | OpenAI concurrency | OpenAI calls / 10 min |
| --- | ---: | --- | ---: | ---: |
| 32 | 32 | 8 × 4 | 32 | 512 (production), 300 (staging) |
| 64 | 64 | 8 × 8 | 64 | 4096 |

Moving between tiers is a configuration change followed by an environment
refresh of the exact active release:

```bash
sudo python3 deploy/configure_host_env.py --legacy-env /dev/null \
  --production-chat-capacity-tier 64 --confirm SET_PRODUCTION_CHAT_CAPACITY_TIER_64
sudo pwc-deploy production <exact-active-main-sha> --refresh-environment \
  --confirm DEPLOY_PRODUCTION
```

Use `--staging-chat-capacity-tier` with `SET_STAGING_CHAT_CAPACITY_TIER_<n>` for
staging. The 64 tier keeps the replica count, so host memory stays within the
current blue/green envelope; the per-replica Node process holds eight agent
sessions instead of four. MCP catalog research turns use no sandbox, so the
sandbox live cap (16) is unchanged by the tier. Per-chat-session MCP rate
limits are unaffected; only the MCP server's global ceiling matters at the
higher tier.

### Staging durable external Pi qualification profile

The staging-only 32-turn qualification helpers
(`--staging-durable-external-qualification-{enable,disable}-only`,
`--staging-modal-rate-evidence-{install,remove}-only`, and
`backend.scripts.qualify_durable_external_turns`) require the former ordinary
staging baseline (external admission off, `PWC_CHAT_MAX_CONCURRENCY=2`,
`PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP=3`) and refuse a drifted baseline. Staging now
runs the 32 tier with external admission on, so they no longer apply to it as
configured. `pwc-rollback` never restores protected `/etc` configuration.

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

Both environments currently run the pool-free external Pi profile
(`PWC_CHAT_BLANK_POOL_ENABLED=false`, `PWC_CHAT_PI_PREWARM_ENABLED=false`).
Production Pi prewarm is a separately authorized chat change; its helper
refuses unless production chat, the blank pool, the persistent worker, and
sandbox admission are already enabled, and it rejects an alternative model:

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

The operator-only sandbox infrastructure qualification runs from the active
staging release:

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
sandbox termination. It emits timings and no environment values, commands,
prompts, credentials, or tool output. Full model, SDK compaction, resume,
edit/retry, and citation qualification runs through authenticated staging
chats.

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

Model discovery is defined in `backend/chat_configuration/registry.py`.
Production exposes GPT-6 Luna through the direct OpenAI route plus the
HF-org-funded DeepSeek V4.1 Flash when `PWC_CHAT_SPONSORED_DEEPSEEK_ENABLED` is
set; GLM-5.3-Flash is hidden and its sessions continue on Luna. Staging
defaults to direct GPT-6 Luna when the direct route is enabled and also exposes
DeepSeek V4 Flash under one stable public model ID plus comparison models.
`PWC_CHAT_DEEPSEEK_V4_FLASH_PROVIDER` selects the user-funded Hugging Face
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
limits still apply. Production keeps server-funded OpenRouter dispatch disabled
(`PWC_CHAT_OPENROUTER_SERVER_FUNDED_ENABLED=false`) and never reuses staging
credentials or state.

Automatic title generation uses `PWC_CHAT_TITLE_PROVIDER` (`huggingface` in
both environments, with the pinned `zai-org/GLM-5.3-Flash:baseten` model;
`openrouter` remains supported in `backend/services/chat_title_service.py`). It
reserves against a persistent, environment-isolated `$25/month` title circuit
before dispatch. Missing credentials, ledger uncertainty, provider failure, or
exhaustion falls back to a local prompt-derived title. Neither environment may
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
without reading chat state or sending alerts. Paid synthetic turns run in the
separate allowlisted `run_chat_synthetic_probe` job with a six-minute launcher
timeout. Its minute timer enforces the four-hour due gate and reacts to new
releases, provider routes, and critical alert timestamps without blocking the
journal poll.

Both timers are installed with the deployment tools but never enabled
implicitly; they are enabled on the production host. Re-enabling them is a
reviewed production mutation:

```bash
sudo python deploy/install_deploy_tools.py <exact-main-sha>
sudo systemctl enable --now pwc-chat-alert-monitor.timer
sudo systemctl enable --now pwc-cron-run-chat-synthetic-probe.timer
```

An enabled production-chat deployment fails closed unless both timers are
enabled. Both timers invoke only the `pwc-cron` allowlist, and only the
operational monitor's transient unit receives read access to the system journal.

Production chat was activated through the guarded sealed-bundle helpers in
`deploy/configure_host_env.py`:

- `--production-chat-seal-only --modal-profile pwc-production --confirm
  SEAL_PRODUCTION_CHAT_PREPARATION` imports the named mode-`0600` Modal profile
  in memory and writes only the non-loaded root-owned
  `/etc/paperswithcode/production-chat-prepared.env`. It rejects unsafe alert
  URLs, an invalid budget attestation, an invalid OpenRouter keyring contract,
  or reuse of the staging OpenRouter key.
- `--production-chat-install-only --confirm INSTALL_PRODUCTION_CHAT_PREPARATION`
  revalidates that sealed bundle, rejects missing, stale, or added keys, and
  installs it atomically into `production.env` with admission still closed.
- `--production-chat-admission-enable-only --confirm
  ENABLE_PRODUCTION_CHAT_ADMISSION` opens funded dispatch, public admission,
  sandbox admission, and the pool together; refresh the exact active release
  afterwards.

None of these restarts a service. `backend.scripts.qualify_chat_sandbox_spend
--environment production --qualification-id <unique-id> --confirm
QUALIFY_PRODUCTION_CHAT_SPEND`, run as `pwc-production` with both environment
files, exercises sandbox, title, provider-health, and runtime-alert transitions
without creating provider compute.

Sandbox reservations, local accrued-cost estimates, pool projections, and active-turn
estimates include Modal’s 1.75× multiplier for the pinned `eu-west` region.
Provider-reported spend already includes billing adjustments and must not be
multiplied again. Historical local estimates are conservative until provider
reconciliation covers them; this change does not rewrite provider reports.

Production uses the Team service user `pwc-production`, which must be
Contributor on only `pwc-chat-production` and retain No Access on `main` and
every other Environment. The durable application circuit
(`PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD`, currently $225) sits below the
$250 environment and workspace backstops
(`PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD`,
`PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD`); keep the provider-side Environment
budget consistent with them. Rotate the sealed pair only after both `current` and
`previous` production releases accept the Team policy, so direct rollback does
not depend on restoring an older owner credential.

Enabled immutable chat releases derive inline paper mentions and the bounded
read-only Hugging Face catalog capability from the release manifest in both
environments. Disabled releases force both capabilities off, so an ordinary
release rollback also restores their prior activation state without editing
protected configuration.

Install the staging title credential from a protected local environment file
through the narrow staging-only helper. It requires title generation enabled,
`PWC_CHAT_TITLE_BILL_TO=huggingface`, the expected credential owner, and the
`staging` credential environment, rejects reuse of the general HF token or the
production title token, and does not write production:

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

Chat titles and the research-scope guardrail use the same environment-isolated
HF Inference Providers credential with the pinned
`zai-org/GLM-5.3-Flash:baseten` route. Install the staging policy from its
root-owned title source without restarting services:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/staging.env \
  --staging-scope-title-hf-only
```

Production uses a distinct title token and an explicit confirmation:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env deploy/env/production.env \
  --production-scope-title-hf-only \
  --confirm ENABLE_PRODUCTION_HF_SCOPE_AND_TITLES
```

Both installers reject the general HF credential and the other environment's
title token. They reuse only the target environment's dedicated direct-OpenAI
fallback for guardrail provider failure, keep Posterly disabled, and require an
ordinary exact-SHA deploy or environment refresh before processes read the new
values.

To retire the preview, use the provisioning command with
`--staging-openrouter-disable-only`. This leaves the ledger intact for
reconciliation and keeps Hugging Face-backed chat available.

## Production Excalidraw MCP App

Production bundles the reviewed same-origin MCP App host whenever production
chat is enabled, but the backend route, worker registration, and sandbox egress
stay disabled unless both protected switches (`PWC_CHAT_EXCALIDRAW_ENABLED`,
`PWC_CHAT_MCP_APPS_HOST_ENABLED`) are enabled; both are on in production. The
official App HTML is accepted in production only when it matches the SHA-256
pinned in `backend/chat_sandbox_worker/mcp_app_providers.json`; staging retains
its compatibility-gated drift policy.

Enable the worker and App host together, then deploy the exact compatible
release so its frontend and backend become active atomically:

```bash
sudo /srv/paperswithcode/.venv/bin/python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/production.env \
  --production-excalidraw-enable-only \
  --confirm ENABLE_PRODUCTION_EXCALIDRAW
sudo pwc-deploy production <exact-current-main-sha> --confirm DEPLOY_PRODUCTION
```

The independent feature rollback disables both switches before refreshing the
exact active release. This drains the Excalidraw egress profile; an enabled
blank pool refills with a compatible gateway-only sandbox:

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
reaping. External Pi cleanup is limited to its own namespace and protects
content identities derived from active (`current`), rollback (`previous`), and
prepared slot releases. Never remove a release or runtime directory by hand.

## Invariants

`release.json` stores the full SHA, release ID, build profile, build time,
frontend entrypoint, backend/frontend feature manifests and their contract
version, the chat runtime descriptor (including rolling gateway/database
contracts), and the external Pi runtime descriptor. `features.json` lives
beside built `index.html`. Startup fails if a deployed shell references
`/src/main.tsx`, assets are missing, paths are relative or inside a release,
or feature manifests disagree.

A release built with chat disabled has no chat backend router and `/chat`
redirects home; production releases enable chat only from the protected
`PWC_CHAT_ENABLED=true` (see [Commands](#commands)). Production is the sole OAuth/session authority. It signs
`pwc_shared_session` with an Ed25519 private key and scopes the cookie to
`.paperswithcode.co`; staging receives only the public verification key.
The host-only `pwc_session` and `pwc_staging_session` cookies and their
distinct HS256 secrets remain temporarily readable for rollback compatibility.
Staging login redirects through the production callback, whose return
destinations are restricted to the production and staging HTTPS origins.

Codex add-evals and enrich-paper buttons are enabled in both environments'
release manifests (`profile_features` in `deploy/release.py`; staging inherits
production capabilities) and remain protected by Hugging Face admin
authentication in both the frontend and API. Remote-job credentials come from
each environment's protected configuration. Each release launcher derives the non-secret capability flags from that
release's validated manifest, so rolling back also restores the matching
frontend/backend feature state.

Slot processes expose deployment status, drain, and undrain operators only
through their Unix socket. Checked-in nginx templates return 404 for those
paths. `pwc-status` shows each slot's service/socket state, immutable
release/runtime identity, drain counts, and the activation journal. A deploy
never edits or reloads nginx.

## Scheduled work and backup

Host systemd timers generated from `deploy/cron_schedules.py` (units in
`deploy/systemd/cron/`) run `/usr/local/sbin/pwc-cron-throttled <job>`, which
invokes `/usr/local/sbin/pwc-cron <registered-job>`; the matching
`.github/workflows/cron-*.yml` workflows are manual-dispatch only. See
[operations](operations.md#host-timer-scheduling). The launcher runs as
`pwc-cron` (trending jobs as `pwc-cron-trending` with `trending-cron.env`),
loads production plus CRON-only configuration, resolves `production/current`,
records its release ID, and uses absolute lock/log directories.

General jobs never receive the app-only secrets in `production.env`, such as
the session and OAuth signing keys, the admin API token, and chat provider and
sandbox credentials (`APP_ONLY_SECRET_KEYS` in `deploy/cron_launcher.py`).
`pwc-cron` is not a member of `pwc-production`, so it cannot read
`production.env` directly. systemd loads the environment files as root, and a
`user:pwc-cron:--x` ACL lets jobs traverse `/var/lib/paperswithcode/production`
to their own directories (`install_host_layout.restrict_cron_access`).

```bash
sudo pwc-cron status
pwc cron health refresh_paper_embeddings --strict --json
```

The backup script requires an affirmative boolean `private: true` from authenticated
`hf buckets info` before dumping, immediately before uploading, and before pruning.
An unavailable or malformed response fails the job. Newly created local dumps and
checksums use owner-only permissions. These checks detect visibility changes at
those boundaries; bucket access controls must also prevent unauthorized visibility
changes between checks and after upload. A public-backup incident remains open for
historical exposure assessment even after the bucket becomes private.

`pwc-postgres-backup.timer` runs at 03:15 UTC. It runs the backup script from
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
The timer is enabled; its queue table comes from
`backend/database/migrations/add_curation_thumbnail_queue.sql`.

The hourly `hourly-application-smoke.yml` GitHub Actions monitor uses the same
`deploy/smoke_test.py --monitor-subset` implementation as releases. It checks
the production SPA and hashed asset MIME types plus the staging health/auth
boundary without creating an authenticated session.

## Development

Use `uv run --env-file backend/keys.env ...` for local backend commands and
`npm run dev` for a localhost frontend. `check_services.sh` delegates to
`pwc-status`.

## Production executor certificate renewal

The executor hostname serves only ACME challenge files from
`/var/lib/letsencrypt/pwc-executor-production/.well-known/acme-challenge/`
plus its generation-bound WebSocket route. Other HTTPS paths return 404.
The HTTP challenge location is served directly; other HTTP paths redirect to HTTPS.

The `chat-executor.paperswithcode.co` certificate renews through `certbot.timer`
with the `webroot` authenticator at `/var/lib/letsencrypt/pwc-executor-production`
and the renewal hook
`pwc-nginx production --confirm APPLY_NGINX_PRODUCTION --reload-renewed-certificate`
(see `/etc/letsencrypt/renewal/chat-executor.paperswithcode.co.conf`). The hook
requires Certbot's exact `RENEWED_LINEAGE` for the executor host, validates the
live nginx configuration before reloading, then smoke-tests the active
application release. It does not install a template or change release pointers.
