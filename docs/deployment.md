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
  runtimes/external-pi/<content-id>/
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

The external Pi worker is packaged independently under `runtimes/external-pi`.
It exposes the content-free shadow comparison and an authenticated active-turn
tracer. Packaging and shadow activation do not route browser chat traffic to
the tracer: external admission remains a separate staging-only switch, and
runtime validation rejects every external migration switch in production until
the durable dispatch, fencing, recovery, workspace-retention, and qualification
gates have been approved. The runtime identity covers the package manifest,
lockfile, TypeScript build inputs, canonical prompt inputs, and pinned Node
22.19.0 distribution contract. Packaging does not activate worker traffic. A
build uses a temporary directory, exact locked dependencies, a production
TypeScript build, production-dependency pruning, and an atomic rename.
`runtime.json` records contract `external-pi-v1`, source release, entry point,
Node identity, and a strict file-digest inventory. Reuse rejects mutable,
missing, extra, or digest-mismatched files. The staging `release.json` records
the selected runtime ID, contract, and identity-schema version so cleanup and
rollback never recalculate a historical identity with newer packaging rules.
Only protected staging releases participate in external Pi retention. While
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
   `add_chat_turn_jobs.sql`,
   `add_chat_sandbox_pool.sql`, `add_chat_active_cost.sql`,
   `add_chat_user_billing.sql`, `add_chat_qualification_metadata.sql`,
   `add_chat_openrouter_user_budget.sql`, and
   `add_chat_sandbox_spend_cap.sql`, `add_chat_web_search.sql`, and
   `add_chat_hf_catalog.sql`, `add_chat_reasoning_effort.sql`, and
   `add_chat_ttft_profiles.sql`, `add_chat_sandbox_egress_policy.sql`,
   `add_chat_artifacts.sql`, `expand_chat_artifact_foundation.sql`, and
   `add_chat_warm_assignment_race.sql` as
   PostgreSQL superuser with
   `search_path=staging,public`. The guarded migrations refuse any other schema,
   assign the new tables to `pwc_staging_owner`, grant `pwc_staging`, and
   revoke the production application role. The pool migration remains required
   even while `PWC_CHAT_BLANK_POOL_ENABLED=false`, because readiness validates
   the rollback-safe audit schema before pool activation.
   Keep `PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED=false` until this migration is
   verified in the staging schema and the exact release passes turn-ownership
   qualification; an application deployment does not apply the migration.
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

The durable-turn compatibility bridge is a separate, reversible staging-only
checkpoint. The guarded `add_chat_turn_jobs.sql` migration must already be
applied with `search_path=staging,public`, and its schema, ownership, grants,
production-role revocation, and indexes must be audited before enabling the
bridge. Keep staging capacity at exactly two
(`PWC_CHAT_MAX_CONCURRENCY=2`) throughout enablement, qualification, and
rollback; this toggle must not change capacity, external-worker, executor,
workspace, or provider switches.

Resolve and validate the active immutable staging release before any protected
configuration write. Audit the schema while the bridge is still disabled, then
enable only through that exact release's helper, refresh its exact SHA, and
verify that `current` still resolves to the audited release before normal
qualification:

```bash
release_root=/srv/paperswithcode/releases
staging_release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
case "$staging_release" in
  "$release_root"/????????????-staging) ;;
  *) echo "active staging release is not immutable" >&2; exit 1 ;;
esac
cd -- "$staging_release" || exit 1
readarray -t staging_identity < <(/srv/paperswithcode/.venv/bin/python -c '
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
sha = manifest.get("git_sha")
assert isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
assert manifest.get("release_id") == f"{sha[:12]}-staging"
runtime = manifest.get("chat_runtime")
assert isinstance(runtime, dict)
worker = runtime.get("worker_contract_version")
assert isinstance(worker, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", worker)
print(sha)
print(manifest["release_id"])
print(worker)
' "$staging_release/release.json") || exit 1
test "${#staging_identity[@]}" -eq 3 || exit 1
staging_sha="${staging_identity[0]}"
staging_release_id="${staging_identity[1]}"
staging_worker_contract="${staging_identity[2]}"
test "$(basename -- "$staging_release")" = "$staging_release_id" || exit 1
runtime_id="$(sha256sum "$staging_release/uv.lock" | awk '{print $1}')" || exit 1
case "$runtime_id" in
  *[!0-9a-f]*|'') echo "staging runtime ID is invalid" >&2; exit 1 ;;
esac
test "${#runtime_id}" -eq 64 || {
  echo "staging runtime ID is invalid" >&2
  exit 1
}
runtime_python="/srv/paperswithcode/runtimes/$runtime_id/bin/python"
test -x "$runtime_python" || {
  echo "installed staging runtime Python is missing" >&2
  exit 1
}

run_staging_chat_gate() {
  case "${1-}" in
    audit-disabled)
      test "$#" -eq 1 || return 1
      gate_module=backend.scripts.qualify_chat_durable_dispatch
      gate_args=(
        --release-dir "$staging_release"
        --confirm QUALIFY_STAGING_DURABLE_DISPATCH
        --audit-disabled-only
      )
      ;;
    qualify-enabled)
      test "$#" -eq 1 || return 1
      gate_module=backend.scripts.qualify_chat_durable_dispatch
      gate_args=(
        --release-dir "$staging_release"
        --confirm QUALIFY_STAGING_DURABLE_DISPATCH
        --qualify-enabled-only
      )
      ;;
    soak)
      test "$#" -eq 1 || return 1
      gate_module=backend.scripts.qualify_chat_soak
      gate_args=(
        --release-dir "$staging_release"
        --confirm QUALIFY_STAGING_CHAT_SOAK
      )
      ;;
    soak-audit)
      test "$#" -eq 2 || return 1
      gate_module=backend.scripts.audit_chat_soak
      gate_args=(
        --started-at "$2"
        --release-dir "$staging_release"
        --confirm AUDIT_STAGING_CHAT_SOAK
      )
      ;;
    *) echo "invalid staging chat gate" >&2; return 1 ;;
  esac
  sudo systemd-run --quiet --wait --pipe --collect \
    --uid=pwc-staging --gid=pwc-staging \
    --working-directory="$staging_release" \
    --property=EnvironmentFile=/etc/paperswithcode/staging.env \
    -- /usr/bin/env \
    PWC_RELEASE_ID="$staging_release_id" \
    PWC_CHAT_WORKER_CONTRACT_VERSION="$staging_worker_contract" \
    "$runtime_python" -m "$gate_module" "${gate_args[@]}"
}

run_staging_chat_gate audit-disabled || exit 1

sudo /srv/paperswithcode/.venv/bin/python \
  "$staging_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-chat-durable-dispatch-enable-only || exit 1
sudo pwc-deploy staging "$staging_sha" --refresh-environment || exit 1

refreshed_release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
test "$refreshed_release" = "$staging_release" || exit 1
refreshed_sha="$(/srv/paperswithcode/.venv/bin/python -c '
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["git_sha"])
' "$refreshed_release/release.json")" || exit 1
test "$refreshed_sha" = "$staging_sha" || exit 1
cd -- "$refreshed_release" || exit 1
run_staging_chat_gate qualify-enabled || exit 1
run_staging_chat_gate soak || exit 1
run_staging_chat_gate soak-audit '<durable-bridge-activation-time>' || exit 1
```

The disabled-state audit must emit `mode=disabled_schema_audit`,
`status.passed=true`, and all six schema audit booleans as true before the
enable helper is run. It performs no inserts, updates, deletes, model/provider
calls, tool calls, or sandbox work. `--audit-disabled-only` refuses an enabled
bridge; `--qualify-enabled-only` refuses a disabled bridge. Both modes require
the exact staging confirmation, live immutable release and worker contract,
staging search path, and complete PostgreSQL schema/role/owner/grant/index/
constraint contract. The catalog inspection runs in a database-enforced
read-only transaction.

Complete the authenticated staging turn-ownership matrix for new turns,
follow-ups, cancellation, edit/retry, and resume before treating the bridge as
qualified. The durable-dispatch command must report all seven scenarios passed,
all six schema audit booleans true, and `cleanup.clean=true`; it never calls a
model, provider, sandbox, or user-visible chat route. Any non-zero exit, failed
scenario, false audit boolean, or incomplete cleanup is a rollback gate. On any
failed gate, resolve and verify the still-active audited release, invoke its
exact disable helper, and refresh the same exact SHA through the immutable
deployment path:

```bash
rollback_root=/srv/paperswithcode/releases
rollback_release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
case "$rollback_release" in
  "$rollback_root"/????????????-staging) ;;
  *) echo "rollback release is not immutable staging" >&2; exit 1 ;;
esac
readarray -t rollback_identity < <(/srv/paperswithcode/.venv/bin/python -c '
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
sha = manifest.get("git_sha")
assert isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
assert manifest.get("release_id") == f"{sha[:12]}-staging"
runtime = manifest.get("chat_runtime")
assert isinstance(runtime, dict)
worker = runtime.get("worker_contract_version")
assert isinstance(worker, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", worker)
print(sha)
print(manifest["release_id"])
print(worker)
' "$rollback_release/release.json") || exit 1
test "${#rollback_identity[@]}" -eq 3 || exit 1
rollback_sha="${rollback_identity[0]}"
rollback_release_id="${rollback_identity[1]}"
rollback_worker_contract="${rollback_identity[2]}"
test "$(basename -- "$rollback_release")" = "$rollback_release_id" || exit 1
test -n "$rollback_worker_contract" || exit 1
sudo /srv/paperswithcode/.venv/bin/python \
  "$rollback_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-chat-durable-dispatch-disable-only || exit 1
sudo pwc-deploy staging "$rollback_sha" --refresh-environment || exit 1
rollback_refreshed="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
test "$rollback_refreshed" = "$rollback_release" || exit 1
rollback_refreshed_sha="$(/srv/paperswithcode/.venv/bin/python -c '
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["git_sha"])
' "$rollback_refreshed/release.json")" || exit 1
test "$rollback_refreshed_sha" = "$rollback_sha" || exit 1
```

### Staging durable external Pi qualification profile

The 32-turn durable external Pi qualification is a staging-only, explicitly
confirmed configuration profile. It does not enable ordinary external
admission: public staging remains at two ordinary concurrent turns with the
three-sandbox safety cap. Resolve the exact active immutable release, enable
the profile with that release's helper, and refresh that same SHA:

```bash
qualification_release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
case "$qualification_release" in
  /srv/paperswithcode/releases/????????????-staging) ;;
  *) echo "qualification release is not immutable staging" >&2; exit 1 ;;
esac
qualification_sha="$(/srv/paperswithcode/.venv/bin/python -c '
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
sha = manifest.get("git_sha")
assert isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
assert manifest.get("release_id") == f"{sha[:12]}-staging"
print(sha)
' "$qualification_release/release.json")" || exit 1
test "$(basename -- "$qualification_release")" = "${qualification_sha:0:12}-staging" || exit 1

sudo /srv/paperswithcode/.venv/bin/python \
  "$qualification_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-modal-rate-evidence-install-only \
  --staging-modal-rate-release-id "$(basename -- "$qualification_release")" \
  --staging-modal-rate-microusd-per-second 53 \
  --confirm INSTALL_STAGING_MODAL_RATE_EVIDENCE || exit 1
sudo /srv/paperswithcode/.venv/bin/python \
  "$qualification_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-durable-external-qualification-enable-only \
  --confirm ENABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION || exit 1
sudo pwc-deploy staging "$qualification_sha" --refresh-environment || exit 1
test "$(readlink -e /srv/paperswithcode/environments/staging/current)" = \
  "$qualification_release" || exit 1
```

`53` is the explicitly reviewed current Modal executor rate in microusd per
second. The helper has no rate default or fallback: re-review and supply the
rate explicitly for each candidate. It binds the three-key evidence file to
the exact active staging release and atomically installs it as root-owned mode
`0600`. It does not invent an attestation timestamp or print the rate, release,
credentials, or file contents.

Before starting an explicitly authorized qualifier, run `pwc-status` and verify
the active external worker without exposing its bearer token:

```bash
pwc-status || exit 1
sudo grep -E '^(PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED|PWC_CHAT_MAX_CONCURRENCY|PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY|PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP|PWC_CHAT_BLANK_POOL_ENABLED|PWC_CHAT_PI_PREWARM_ENABLED)=' \
  /etc/paperswithcode/staging.env
sudo /srv/paperswithcode/.venv/bin/python - <<'PY'
import json
from pathlib import Path

slot = Path("/srv/paperswithcode/environments/staging/active").resolve().name
statuses = [
    json.loads(
        Path(
            f"/run/paperswithcode/external-pi/staging-{slot}-{index:02d}.json"
        ).read_text()
    )
    for index in range(8)
]
assert all(status["state"] == "ready" for status in statuses)
assert all(status["authenticated"] is True for status in statuses)
assert all(status["registered"] is True for status in statuses)
assert all(status["maximum_sessions"] == 4 for status in statuses)
assert sum(status["maximum_sessions"] for status in statuses) == 32
print("eight external workers ready; aggregate maximum_sessions=32")
PY
sudo -u postgres psql -d paperswithcode_hf -Atc \
  "SELECT count(*) FROM staging.chat_sandbox_pool WHERE state IN ('starting','blank_ready','claimed','draining');"
```

The selected environment values must include
`PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=false`,
`PWC_CHAT_MAX_CONCURRENCY=2`, `PWC_CHAT_SANDBOX_TOTAL_LIVE_CAP=3`, and both
pool/prewarm flags set to `false`. The qualification profile must also set
`PWC_CHAT_OPENAI_GLOBAL_MAX_CONCURRENCY=32`; otherwise the ordinary four-call
gateway limit serializes the 32-user cohort and invalidates its TTFT result.
The pool query must return `0`; any other
value is a stop gate, not authorization to delete rows. The qualifier itself is
a separate, explicitly authorized operation.

Run the qualifier with Locust in a transient environment outside the immutable
release. The deployed application runtime intentionally does not contain load-
testing dependencies:

```bash
uv_bin="$(command -v uv)" || exit 1
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=root --gid=root \
  --working-directory="$qualification_release" \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  --property=PrivateTmp=yes \
  -- /usr/bin/env \
  PWC_RELEASE_ID="$(basename -- "$qualification_release")" \
  UV_PROJECT_ENVIRONMENT=/tmp/pwc-staging-qualifier-project \
  "$uv_bin" run --frozen --with locust python \
  -m backend.scripts.qualify_durable_external_turns \
  --environment staging \
  --release-id "$(basename -- "$qualification_release")" \
  --profile 32-functional-turns \
  --max-spend-usd 10 \
  --confirm QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS
```

Restore the paired baseline with the same still-active release and refresh the
same SHA whether qualification passes or fails:

```bash
qualification_release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
qualification_sha="$(/srv/paperswithcode/.venv/bin/python -c '
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["git_sha"])
' "$qualification_release/release.json")" || exit 1
sudo /srv/paperswithcode/.venv/bin/python \
  "$qualification_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-durable-external-qualification-disable-only \
  --confirm DISABLE_STAGING_DURABLE_EXTERNAL_QUALIFICATION || exit 1
sudo pwc-deploy staging "$qualification_sha" --refresh-environment || exit 1
sudo /srv/paperswithcode/.venv/bin/python \
  "$qualification_release/deploy/configure_host_env.py" \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-modal-rate-evidence-remove-only \
  --staging-modal-rate-release-id "$(basename -- "$qualification_release")" \
  --confirm REMOVE_STAGING_MODAL_RATE_EVIDENCE || exit 1
```

Verify ordinary admission is still false, concurrency/cap remain `2`/`3`, and
pool/prewarm are restored to `true`. `pwc-rollback staging` does not restore
protected `/etc` configuration, so release rollback alone is not this profile's
rollback. Run the separately confirmed exact-release removal even when the
qualifier fails; it refuses a missing, symlinked, misowned, mispermissioned,
wrong-source, or wrong-release evidence file. Production remains unchanged and
has no corresponding activation mode.

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
without reading chat state or sending alerts. Paid synthetic turns run in the
separate allowlisted `run_chat_synthetic_probe` job with a six-minute launcher
timeout. Its minute timer enforces the four-hour due gate and reacts to new
releases, provider routes, and critical alert timestamps without blocking the
journal poll.

The committed timer is installed with the deployment tools but is never enabled
implicitly. Enabling it is a reviewed production preparation mutation:

```bash
sudo python deploy/install_deploy_tools.py <exact-main-sha>
sudo systemctl enable --now pwc-chat-alert-monitor.timer
sudo systemctl enable --now pwc-cron-run-chat-synthetic-probe.timer
```

An enabled production-chat deployment fails closed unless both timers are
enabled. Both timers invoke only the `pwc-cron` allowlist, and only the
operational monitor's transient unit receives read access to the system journal.

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
reaping. External Pi cleanup is limited to its own namespace and protects
content identities derived from active (`current`), rollback (`previous`), and
prepared slot releases. Never remove a release or runtime directory by hand.

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
