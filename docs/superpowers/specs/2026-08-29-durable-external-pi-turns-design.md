# Durable External Pi Turns Design

## Status and scope

This design is the production-gate phase after the authenticated external Pi
turn tracer landed on staging. It keeps the Pi harness outside Modal and keeps
Bash/Read inside a lazily created executor sandbox, while removing the browser
connection as the owner of the turn.

The work is staging-only until every qualification gate in this document
passes. `PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED` remains false during normal
development and deployment. Production must continue using its existing chat
path and configuration.

## Goals

- Admit a chat immediately without a user-visible queue and run it independently
  of the initiating HTTP/SSE connection.
- Fence every external worker, turn owner, gateway request, transcript write,
  and tool operation with durable identities.
- Let a browser reconnect to an active turn without starting another model call
  or duplicating a user message.
- Never repeat a Bash side effect after an ambiguous executor transport failure.
- Create no Modal sandbox for turns that do not use Bash or Read.
- Reuse one executor workspace for successive tool-using turns in the same chat
  session, subject to the existing bounded idle lifecycle.
- Qualify 32 and then 100 concurrent active staging chats with immediate
  admission, bounded resource use, and content-free reports.

## Non-goals

- No Redis, Celery, Cloud Tasks, or other queue service.
- No automatic provider fallback between OpenAI and Hugging Face Inference
  Providers.
- No automatic replay of an ambiguously delivered model request after a backend
  or external-worker crash.
- No multiple simultaneous turns for one account.
- No production activation, production environment change, or nginx change.
- No durable preservation of transient SSE chunks after the canonical assistant
  message has been committed.
- No workspace snapshots in this phase. A live executor sandbox may be reused,
  but `PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED` remains false.

## Safety invariants

1. The PostgreSQL `chat_turn_jobs` row is the sole authority for turn ownership.
2. A turn mutation is valid only for the exact tuple `(turn_id, worker_id,
   worker_generation, lease_generation)` and before `lease_expires_at`.
3. The selected external worker must also match the registry tuple `(worker_id,
   instance_id, generation, release_id, contract_version)`.
4. Losing a browser connection never cancels a turn.
5. Losing a durable turn lease prevents further gateway, transcript, and tool
   mutations by the stale owner.
6. An ambiguous model call is interrupted, not replayed.
7. An ambiguous Bash call is reattached by its existing execution identity,
   never submitted again.
8. A no-tool turn creates zero executor sandboxes.
9. Only one nonterminal turn per account remains enforceable by the existing
   unique database constraint and admission locks.
10. Admission does not wait for worker capacity. Insufficient protected capacity
    fails immediately with the existing unbilled overload response.

## Architecture

### 1. Durable admission and detached coordinator

Admission continues to create the user message, active-turn projection, and
`chat_turn_jobs` row in one transaction. For an external Pi turn, the request
then calls a process-local `ExternalTurnCoordinator.ensure_started(turn_id)`.
The coordinator claims the admitted row through `ChatTurnJobRepository` before
creating any model or sandbox resource. Its owner ID and process generation are
stable for that backend process; the repository-generated lease generation is
the per-claim fence.

The coordinator stores the running asyncio task in a strong process-local
registry and shields it from HTTP request cancellation. The task owns lease
heartbeats, the external-worker WebSocket, tool dispatch, terminal persistence,
and cleanup. The SSE response is only a subscriber. Closing that response
removes a subscriber but does not cancel the coordinator task.

There is no waiting queue. `ensure_started` either proves that this process owns
the turn, proves that another live owner already owns it, or fails immediately.
An expired claim is reconciled to `interrupted/lease_expired`; it is not stolen
and replayed because an already-delivered provider call cannot be disproved.
An admitted row that was never claimed may still be claimed normally during its
bounded dispatch-start window. A sweeper marks an older unclaimed row
`interrupted/dispatch_failed`, so admission rows cannot become an implicit
waiting queue.

### 2. Bounded reconnect journal

Add a staging migration for `chat_turn_event_chunks`. Each row belongs to one
turn and contains a contiguous sequence range plus a bounded JSON array of
already-sanitized public stream frames. The coordinator batches frames by both
time and bytes before appending them transactionally. Per-frame and per-turn
bounds are enforced before persistence.

Every SSE frame receives a monotonically increasing event ID. A repeated POST
with the same request/client-message identity attaches to the existing
nonterminal job and replays frames after the caller's last event ID. It must not
prepare the prompt, create another message, issue another capability, claim the
turn, or start another worker run. The frontend automatically retries the same
request identity after a network failure with its last confirmed event ID in
`Last-Event-ID`. The subscriber tails the database journal; a process-local
condition may reduce latency, but correctness cannot depend on the subscriber
and coordinator living in the same backend process.

The canonical assistant message remains the durable chat history. After terminal
message and job persistence commits, an idempotent follow-up transaction deletes
the transient event chunks. A crash before deletion is harmless. When a terminal
replay has no chunks, the existing persisted assistant-message replay is
authoritative. Exceeding the event-journal byte or sequence bound fails the turn
with `event_journal_exhausted`; it never silently drops reconnect data.

### 3. External-worker generation and turn fences

The existing supervisor already binds a durable worker generation through
`POST /v1/claim`. WebSocket upgrade for `/v1/turn` must require the matching
`X-PWC-Worker-Generation` header, just like drain control. The backend resolves
the exact ready registry claim and supplies that generation. A missing, stale,
draining, or expired worker claim is rejected before a session consumes
capacity.

The run frame adds the exact durable turn-claim tuple. The external worker keeps
that tuple with the in-memory run and rejects a second start or attach that does
not match it. Gateway calls, transcript calls, and MCP search calls carry the
same tuple in headers. The trusted gateway checks it against `chat_turn_jobs`
and rejects stale or expired claims before forwarding or mutating data.

Capabilities remain scoped to one owner/session/turn, but capability possession
alone is no longer sufficient for the external path: the live lease fence is
also mandatory.

### 4. Transport detach and reattach

The external worker owns active Pi runs in a registry keyed by request and turn
identity rather than by WebSocket object. Each run has a bounded in-memory event
buffer and at most one attached backend transport. Closing the transport
detaches it; it does not cancel Pi. The coordinator reconnects with an
`attach_turn` frame containing the exact worker generation, turn fence, and last
worker event cursor. The worker replays subsequent buffered events and resumes
live delivery. If the worker's bounded buffer fills while detached, it
terminates the run with `worker_event_buffer_exhausted` rather than losing replay
data.

Only an explicit authenticated cancel, worker drain deadline, lost/expired turn
fence, terminal completion, or bounded run deadline stops the Pi run. A worker
process crash cannot prove whether the provider accepted its latest request, so
the backend records an interrupted turn and requires a user retry instead of
replaying it on another worker.

Pending tool requests remain part of the run state across transport detach. A
reattached coordinator may provide the correlated result for the same operation
ID. A different operation ID cannot satisfy the pending request.

### 5. Exactly-once Bash recovery

Pi tool-call identity produces a stable executor `execution_id` and
`tool_call_id` for the lifetime of the run. The coordinator's run state records
the operation identity and last output sequence before returning a tool result
to Pi. It submits `exec` at most once. This state is recoverable across transport
reattachment within the owning backend process; a backend-process crash
interrupts the turn and never reconstructs or resubmits the Bash call.

If executor transport fails before a terminal frame is proven, the coordinator
calls `attach_execution` with the same context and last observed sequence. It
may repeat bounded attach attempts, but it must never call `exec` again. The
existing executor daemon's durable operation record and identity checks remain
the authority for whether the execution is active or terminal. If neither a
terminal result nor a safe attach can be proven before the deadline, the tool
and turn fail with `execution_lost`.

Read operations use the same correlation fence. They may be reissued only when
the client proves the original payload was not delivered; otherwise they attach
or fail closed.

### 6. Lazy session workspace retention

Replace the external runner's direct create/terminate calls with a focused
executor-workspace manager built on the existing `ChatSandboxLease` state
repository and Modal provider adapter. On the first Bash or Read request it
claims the session workspace lease, reattaches the recorded live executor
sandbox only when its Modal identity, executor health response, workspace ID,
and workspace generation all match the durable lease. Otherwise it reconciles
the stale lease and creates one `SandboxLaunchMode.EXECUTOR` sandbox, recording
its exact Modal ID and workspace generation.

At turn completion the manager releases the session lease to the existing idle
state instead of terminating the sandbox. A later turn in the same chat claims
the same lease and workspace generation, so files written by Bash remain
available. Existing idle-expiry and spend controls reclaim the sandbox. A
deleted chat still invokes the existing cleanup lifecycle. No-tool turns never
call the workspace manager and therefore allocate nothing.

Workspace ownership and durable turn ownership are separate fences: the former
protects session files and the latter protects one model turn. Both must be live
for a tool operation.

### 7. Cancellation and terminal handling

Cancellation first transitions the durable job to `cancelling` under its exact
claim. The coordinator sends authenticated cancel to the attached external run,
cancels or attaches-and-cancels any active executor operation, persists the
interrupted assistant projection, and writes the terminal job state. A missing
process-local coordinator uses the existing control-missing reconciliation and
does not start a replacement run.

Terminal persistence is idempotent for the exact claim. The coordinator stops
heartbeats only after terminal message/job persistence finishes. Stale owners
cannot overwrite a newer or terminal state. Capability revocation and transient
event-chunk cleanup occur after the canonical terminal state is safe.

### 8. Activation and compatibility

The event-journal migration is additive and must be applied to staging before a
release may advertise detached-turn support. Runtime validation rejects
external admission unless durable turn dispatch, the external supervisor, the
ready worker registry claim, and the event-journal schema are all present. The
existing active tracer remains usable for qualification while public external
admission is false.

The gateway contract version advances additively: the new fence headers are
mandatory only for external detached turns, while the current sandbox path
remains compatible during rollout and rollback. A rollback release may ignore
the additive event table but must not encounter external jobs admitted by a
newer release; deployment therefore drains detached turns before switching to a
release that does not advertise the detached-turn contract.

## Failure semantics

| Failure | Required result |
| --- | --- |
| Browser/SSE disconnect | Turn continues; reconnect replays from event cursor. |
| Backend-to-worker WebSocket loss | Reattach to the same in-memory run and cursor. |
| Backend process crash | Lease expires; turn becomes interrupted; no model replay. |
| External worker process crash | Turn becomes interrupted; no model replay. |
| Stale backend or worker generation | Gateway, transcript, and tool mutations return a typed fence error. |
| Executor relay loss during Bash | Attach to the existing execution ID; never resubmit Bash. |
| Executor sandbox lost | Turn fails `execution_lost`; workspace lease is reconciled. |
| Database heartbeat failure | Stop external mutations; natural lease expiry and reconciliation mark the turn interrupted once PostgreSQL is reachable. |
| Capacity unavailable | Immediate unbilled overload response; no waiting queue. |

## Observability

Langfuse keeps the existing per-turn trace and latency observations. Add
content-free counters and durations for coordinator claims, active detached
turns, subscriber detach/reattach, event replay counts, worker reattachments,
stale-fence rejections, executor attaches, executor-lost outcomes, lazy sandbox
creates, workspace reuse, and terminal causes. Logs contain only opaque IDs,
typed states, generations, counts, and durations—never prompts, model output,
tool commands, file contents, capabilities, or provider credentials.

The admin dashboard should alert on expired turn leases, stale-fence attempts,
reattach failure rate, executor-lost rate, external capacity saturation, event
journal bound violations, sandbox creation/reuse ratios, and TTFT regressions.

## Qualification and release gates

All qualification runs use the exact active immutable staging release and leave
normal external admission disabled unless the guarded test controller enables a
scoped profile.

1. Unit and integration tests prove lease fencing, idempotent admission,
   attach-only replay, journal bounds, and terminal cleanup.
2. A browser-disconnect test drops the subscriber during model streaming and
   proves the same turn completes with one provider execution.
3. A transport test drops the backend-worker WebSocket and proves cursor-based
   reattachment without a second Pi run.
4. A stale-owner test advances both worker and turn generations and proves every
   old gateway/transcript/tool mutation is rejected.
5. A Bash fault-injection test drops the relay after payload delivery and proves
   one filesystem side effect, one execution ID, attach recovery, and one tool
   result.
6. A workspace test writes a file in one turn, releases the workspace, reads it
   in the next turn, and proves the same sandbox/workspace generation was reused.
7. A no-tool test proves zero sandbox creates and zero Modal executor cost.
8. The guarded active-chat load profile runs 32 concurrent users first, then 100,
   with immediate admission, no queued state, no duplicate turns, no stale
   mutations, no lost terminal messages, and complete resource cleanup.
9. Reports include TTFT, total latency, active backend/worker/sandbox counts,
   CPU/RAM, Modal lifecycle/cost estimates, reconnect outcomes, and error classes.
10. Production activation requires an explicit later authorization after the
    100-user report passes and the staging soak shows no unresolved alerts.

## Delivery sequence

1. Land the event journal and detached coordinator behind disabled flags.
2. Add worker/turn fencing and gateway validation.
3. Add worker transport reattachment and exactly-once executor attachment.
4. Integrate the lazy retained executor workspace lifecycle.
5. Add frontend reconnect behavior and end-to-end fault tests.
6. Deploy each independently reviewed commit to staging with admission off.
7. Run 32-user active qualification, fix any gate failures, then run 100 users.
8. Present the report and request separate production activation authorization.
