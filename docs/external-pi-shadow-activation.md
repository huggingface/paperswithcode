# External Pi shadow activation

This checkpoint activates only the staging shadow worker and its durable
supervisor. It does not admit turns, execute tools, call a model or provider,
start Modal work, or create billing activity. Production is explicitly outside
the checkpoint.

## Qualification

Publish Task 3 as a second immutable staging release only after both `current`
and `previous` contain the inert external Pi runtime. Keep every external Pi
flag false while publishing, and confirm both external Pi units are inactive.
Do not start either unit manually. The guarded enable command below temporarily
starts the exact active-slot candidate, waits for authenticated registration and
a heartbeat, crashes only the supervisor, waits for its durable lease to expire,
and proves a higher replacement generation. A staging-role database probe then
submits the old generation to the real repository and requires it to be fenced.
The guard performs a real drain/offline stop, starts one final recovery
generation, runs the qualification command with the exact release runtime, and
always drains/stops the temporary units before it changes either flag.
Each temporary qualification claims cleanup ownership and exact-stops its slot
before the first start, so a deploy-qualified worker is drained rather than
started over and an interruption during that pre-stop still triggers final
cleanup. The final successful recovery remains live only when explicitly owned
by the completed qualification.

The integrated command is equivalent to:

```bash
cd /srv/paperswithcode/environments/staging/current
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_external_pi_shadow \
  --environment staging \
  --app-root /srv/paperswithcode \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --worker-url http://127.0.0.1:8820 \
  --worker-id staging-blue-00 \
  --expected-generation <recovery-generation> \
  --initial-generation <initial-generation> \
  --restarted-generation <lease-expiry-generation> \
  --stale-fenced --drain-recovered \
  --qualification-nonce <single-use-activation-nonce> \
  --token-file <guard-created-root-only-derived-replica-token-file> \
  --prompt-file <immutable-runtime>/assets/pi-system-prompt.txt \
  --report /var/lib/paperswithcode/staging/external-pi-shadow-qualification.json
```

The guard supplies replica zero's actual worker ID, port, derived credential,
and immutable prompt path. The temporary credential file is mode `0600` and is
removed immediately after the subprocess exits. The command refuses production
and a release other than the exact staging
`current`. It submits linear, branching, tool-history, and eight concurrent
isolated native JSONL trees. It compares current leaf, entry count, canonical
transcript digest, system-prompt digest, and registered-tool-name digest. It
also proves immediate capacity rejection without a queue, lease-expiry restart
with a higher generation, stale-generation fencing, drain, and clean recovery.

The JSON report is deliberately content-free: exact release/worker/recovery
generation, a single-use nonce, a bounded freshness timestamp, case names,
booleans, bounded integer counts/durations, typed failure codes, and six
external-work counters only. The observed shadow-request counter must be
positive. Model, tool, provider, Modal, and billing counters must be exactly
zero, and the live worker must report no provider/Modal credentials and zero
registered tools. Do not retain request bodies or temporary native sessions.

## Guarded enable and disable

Activate and qualify the exact current release atomically:

```bash
sudo /usr/bin/python3 \
  /usr/local/lib/paperswithcode-deploy/external_pi_shadow_activation.py \
  staging enable \
  --release-id <exact-release-id> \
  --report /var/lib/paperswithcode/staging/external-pi-shadow-qualification.json
```

The guard first bootstraps the content-free qualification while both flags stay
false. It proves drain and stops those temporary units, then checks every
required successful case and creates or preserves the mode-0640 token-only
worker environment. It sets shadow and supervisor together and refreshes that
exact git SHA. Because the refresh switches to the other deployment slot, the
guard then repeats the complete lifecycle and content-free qualification
against the resulting final active worker. The accepted report is replaced and
bound to that final worker's exact identity, recovery generation, single-use
nonce, and freshness timestamp; its final recovery worker remains live only
after report validation succeeds. External admission, the sandbox executor,
remote workspace tools, remote Bash, remote Read, and lazy workspace are forced
false throughout. Production invocation fails. A failed initial refresh
restores the prior protected environment; a failed final-active qualification
exact-evidence drains both slots, writes both lifecycle flags false, and
refreshes fail closed. If exact drain cannot be proven, the helper preserves
the enabled lifecycle configuration and requires guarded disable rather than
abandoning a worker.

Starting a slot also handles a previously active worker whose supervisor is no
longer usable. Before systemd starts the pair, the lifecycle reads that exact
worker's authenticated loopback status and stops it only when the supervisor is
inactive, the worker is already `draining`, its identity and contract match,
and `active_sessions` is the integer zero. Missing, ambiguous, ready, or
non-zero session evidence fails closed; it never replaces an in-use worker.

Stopping a slot preserves that draining proof and adds one narrowly bounded
pre-registration recovery proof. An exact `ready` worker may be stopped only
when its authenticated loopback status matches the slot worker ID and expected
release, `worker_generation` is explicitly null, `active_sessions` is the exact
integer zero, `maximum_sessions` is the exact integer eight, and all six
operation counters are present as exact integer zeros. Any missing, differently
typed, non-zero, or mismatched evidence fails closed.

The CLI converts normal `SIGTERM` and `SIGINT` delivery on its main thread into
a transaction interruption. This runs the same temporary-unit `finally` stop
and protected-environment rollback used for other failures, then restores the
process's prior signal handlers. Cleanup ownership is recorded before either
side-effecting unit start. The first watched signal blocks both watched signals
until rollback/unit cleanup completes and both prior handlers are restored. A
per-transaction latch also ignores a second callback that CPython queued before
the first handler could apply that mask, so a termination burst cannot
interrupt the safe-state transition.

An interruption during disable preserves the prior lifecycle configuration and
raises an explicit recovery-required error because only some units may have
stopped; rerun guarded disable to complete and prove both slots inactive. It
never proceeds to refresh from partial stop evidence. `SIGKILL`, host power
loss, and kernel failure
cannot run in-process cleanup. After one of those events, run the guarded
`disable` command before retrying enable; disable checks both supervisor and
worker units in both slots even when the flags already read false/false, and
leaves the configuration fail closed until all units prove inactive.

Disable is qualification-independent but still exact-release guarded, including
when the protected flags already read false/false so orphan units cannot be
skipped. The guard
keeps true/true in the protected environment while it exact-evidence drains and
stops the current and any old-slot external units. If a slot release cannot be
resolved, both its supervisor and worker systemd units must still prove
inactive. Only after proven stop does
it write false/false and refresh the exact release:

```bash
sudo /usr/bin/python3 \
  /usr/local/lib/paperswithcode-deploy/external_pi_shadow_activation.py \
  staging disable --release-id <exact-current-release-id>
```

If the refresh fails after proven stop, the helper deliberately leaves the
units stopped and both flags false and returns an explicit recovery error. It
does not restore true configuration over stopped services. If drain proof
fails, it makes no configuration change and leaves the lifecycle enabled for
authenticated operator recovery; never kill or abandon an unproven worker.

## Observation and alerts

The dashboard must group by exact release and worker identity and show:

- supervisor registration, heartbeat age, lease expiry, generation, state,
  active sessions, maximum sessions, and drain result;
- shadow case pass rate and duration, capacity rejections, projection mismatch
  codes, restart generation advances, stale-generation rejection, and recovery;
- the positive shadow-request counter and all five forbidden external-work
  counters, each forbidden counter with an alert threshold above zero;
- worker availability, authentication failures, unexpected generation changes,
  missed heartbeat/expired lease, non-zero active sessions during drain, and
  repeated qualification failures.

Page immediately for any external-work count above zero, admission/executor/
remote/lazy flag becoming true, a stale claim being accepted, transcript or
prompt digest mismatch, or failure to reach durable offline state within the
configured drain bound. Alert after two heartbeat intervals for heartbeat age
and before lease expiry leaves less than one heartbeat interval.

## Rollback

Run the guarded disable command first. Confirm `pwc-status staging` shows the
exact worker durably `offline` with `drained=true`, or use the existing exact
inactive-unit proof when it never registered. Do not kill an unproven worker.
If the release itself must roll back, use `pwc-rollback staging` only after the
shadow lifecycle is disabled; both current and previous understand the runtime.
Re-run the normal health, root, SPA, and API smoke checks.

## Gate for later real admission

This checkpoint does not authorize real admission. A later, separately
reviewed phase requires all of the following:

- a sustained staging observation window with no projection mismatch, lease
  loss, stale-generation acceptance, drain failure, or recovery failure;
- eight-session isolation and no-queue capacity behavior remaining green under
  repeated qualification;
- zero model/tool/provider/Modal/billing work throughout shadow observation;
- approved executor and remote-tool capability, credential, cost, audit, and
  rollback contracts, each independently qualified;
- explicit production authorization and a new production qualification plan.

Until then, `PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED`, executor, remote tool,
remote Bash/Read, and lazy workspace controls remain false in every environment.

## Transient fleet qualification

The fleet qualifier is a separate staging-only operator checkpoint after the
active shadow worker is healthy. It does not replace, reconfigure, or target the
active blue/green worker. It starts fixed transient replica pairs only on
`127.0.0.1:8780-8795`, keeps public nginx and all admission/executor/remote flags
out of the path, and removes one exact observed generation between the healthy
and survivor rounds. The full preflight and invocation are in
`backend/loadtests/README.md`; the retained report is
`/var/lib/paperswithcode/staging/external-pi-fleet-qualification.json`. The
separate incremental VPS profile runs 32, 48, then 64 arrivals and retains
`/var/lib/paperswithcode/staging/external-pi-capacity-qualification.json`.

Do not run it while `pwc-status staging` shows the active external Pi worker
failed, draining, unauthenticated, unregistered, stale, or on a release other
than exact staging `current`. Source implementation and test execution do not
authorize repairing or mutating that degraded runtime; restore health through
the staging deployment/activation workflow first.

Every admitted shape must produce 100 compatible healthy observations and 100
compatible survivor observations with zero capacity, protocol, or transport
errors and zero external work. The reported latency is worst-case synthetic
transcript restore/compatibility latency. It is not model TTFT because no prompt
is sent for generation and no provider is called. A `resource_refused` result is
valid safety evidence and must not be forced. On interruption or failure, use
only the controller's exact generation-aware lifecycle cleanup described in the
load-test runbook; never broad-kill a worker or free a port without durable
offline/drained proof.

For the incremental profile, the same contract applies at the shape-specific
arrival count: 2x32 qualifies 32, 4x16 qualifies 48, and 3x32 qualifies 64.
Each target is exactly the capacity remaining after one worker is removed. Run
them in ascending order and stop at the first refusal or failure.

## Durable external-turn staging gate

The durable qualification is distinct from the synthetic shadow and
transient compatibility fleet checks above. Task 11 provides only deterministic
fault/load contracts. The root CLI runs only after explicit authorization with
the exact confirmation `QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS`, the exact active
immutable staging release, and a positive spend envelope no greater than $10.
Production must remain a different immutable release and all ordinary external
admission flags must remain off. The executable Locust barrier, exact 16/8/8
assignment, stream
evidence normalization, identity-aware executor counts, fixed 80% CPU guard,
and strict retained report/cleanup schema are Task 11 code. Task 12 supplies
only protected credentials, exact release/host control, and bounded runtime
evidence. Source constructs the reviewed real chat transport; it must not route
these users to `/v1/shadow` or accept no-op cleanup proof.

The guarded constructor accepts only the exact staging origin and dedicated,
distinct signed synthetic cookies. Before each profile it creates an exact
server-timed cohort with the staging-admin-only
`POST /api/v1/chat/admin/qualification-scopes` endpoint. Streaming requests
carry only the returned `X-PWC-Qualification-Scope-ID`, the closed
`X-PWC-Qualification-Workload` value (`no_tool`, `read`, or `bash`), and the
non-cookie admin credential; client-authored profile, release, and time-window headers are
not evidence. It posts the real `/api/v1/chat/stream` route, resumes the admitted
turn with `Last-Event-ID`, closes every HTTP session, tears down the exact scope
through `POST /api/v1/chat/admin/qualification-scopes/{scope_id}/teardown`,
requires its bounded aggregate proof, and only then closes and reads the scope through
`POST /api/v1/chat/admin/qualification-evidence`. The scope is deleted with the
staging-admin `DELETE /api/v1/chat/admin/qualification-scopes/{scope_id}` path
after collection or any abort.

Apply `add_chat_qualification_evidence_events.sql` and then
`add_chat_qualification_metadata.sql`, followed by
`repair_chat_qualification_evidence_contract.sql`, to the environment-owned schema before
running the gate. Startup readiness validates the exact scope/event columns,
defaults, primary/foreign/unique keys, checks, and index uniqueness/order/predicate.
The normal sandbox maintenance reconcile independently runs bounded expired-scope
retention even when no later scope is issued; cascade deletion removes event rows. The
protected staging runtime must explicitly provide all four rate attestations:
`PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND`,
`PWC_MODAL_EXECUTOR_RATE_SOURCE_ID=modal-staging-price-v1`,
`PWC_MODAL_EXECUTOR_RATE_ATTESTED_AT_MS`, and the exact `PWC_RELEASE_ID`.
Attestation time must fall inside the server-issued cohort window; old, future,
wrong-source, or wrong-release evidence refuses the report.

The current mandatory gate is exactly 32 simultaneous full functional turns
(16 no-tool, eight read-only CLI, eight Bash). The future ordered 32-then-100
controller API remains inert unless separately authorized; standalone 100 is
refused. The cohort is released at once and application-level queueing is
forbidden. The controller rechecks the approved 15–17 GiB window around the
16 GiB VPS class and the existing 1.5 GiB projected `MemAvailable`/80% CPU guard.
A resource refusal is retained safety evidence and ends the operation; it never
authorizes overcommit.

The functional cohort must persist exactly 16/8/8 workload rows. Every tool turn
must own exactly one executor start, one create-or-reuse event, one closed
exact-release compute interval, and one teardown eviction; every no-tool turn
must own zero of all four. The admission cohort must contain exactly 100 no-tool
rows and 100 admission-denominator events.

Qualification includes deterministic browser disconnect, API subscriber
process loss, external worker WebSocket loss, one-worker drain, executor
response loss, and cancellation schedules. Browser/API reconnect resumes by
event cursor, worker reconnect uses the exact retained worker/turn claim, and
executor recovery attaches to the same operation identity. Every schedule
proves exactly one model start and no more than one executor start for an
operation identity. Fault actions cannot precede that model start; cancellation
settles every active executor through its exact operation identity before the
cancelled terminal, and terminal-log loss requires a prior canonical terminal
commit. Verdicts use canonical terminal rows and direct operation counts, not
assumed exactly-once logging.

The exact preflight, thresholds, cleanup proof, report path and permission rules
are in `backend/loadtests/README.md`. Production activation remains forbidden
until the approved 32-turn durable report passes, the staging soak has no
unresolved alerts, and the user gives separate explicit production
authorization.

## Retired singleton overload baseline

The old single-worker 100-user overload baseline is not a scale-out acceptance
gate and must not be used with the four-replica fleet. Use the protected
32-functional-turn procedure in `docs/deployment.md`; it exercises all four
workers through the real admission and generation path and retains the TTFT,
completion, resource, cost, and cleanup verdicts required for activation.
