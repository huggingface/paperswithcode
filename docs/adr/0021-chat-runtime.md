# ADR 0021: Research chat runtime: sandboxes, executors and external Pi

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## API cache policy: short public caching for catalog GETs, no-store for session and mutable paths

Read-only public catalog GET endpoints (papers, methods, tasks, datasets, areas, organizations, frameworks and similar) return Cache-Control public, max-age=60, stale-while-revalidate=300 so browsers and any shared CDN can serve repeat navigation instantly. Session-dependent prefixes (auth, me, cron, admin, contributions, curation-state) and mutable per-paper detail rows are forced to no-store so signed-in state and admin edits are never served stale. All prefixes end in a slash so prefix matching cannot accidentally capture sibling routes such as /api/v1/papers-archive or /api/v1/methods via /api/v1/me.

Read-only public catalog GET endpoints return short public caching headers, while prefixes whose responses depend on the signed-in session (auth, me, cron, admin, contributions, curation-state) are forced to Cache-Control no-store. Prefixes carry trailing slashes so prefix matching cannot leak across sibling routes.

Per-paper detail endpoints (/api/v1/papers/{id} and /api/v1/papers/arxiv/...) are served with Cache-Control no-store even though other catalog GETs get a short public cache, because admin edits and newly linked repositories must appear immediately on the paper page.

Code: `backend/main.py::_PUBLIC_CACHEABLE_PREFIXES`, `backend/main.py::_PRIVATE_GET_PREFIXES`, `backend/main.py::create_app.add_public_cache_headers`

## Active-turn limits change only after load qualification

chat_max_concurrency is a protected emergency limit; deployed profiles stay at their qualified 1 (global) and 2 (per-user) turn values. Raising them requires a separate load qualification, because capacity beyond the qualified values has not been shown to hold on the 16 GB host and provider gates.

Code: `backend/chat_configuration/settings.py::ChatAdmissionSettings`

## Batch failures propagate only after every sibling cleans up

Cold samples in a batch are gathered with return_exceptions=True so every sibling finishes its sandbox cleanup and journaling before any journal failure is raised as an exception group. Raising on the first error would leave sibling sandboxes and reservations unreconciled.

Code: `backend/loadtests/persistent_executor_cold.py::collect_cold_stage`

## Blank sandboxes are reused by compatibility, not release

A blank pool sandbox records the release that created it for audit only. Whether an unassigned blank can be reused is decided by immutable worker and resource compatibility, so blanks survive releases that do not change the worker contract.

Code: `backend/services/chat_sandbox_pool_acquisition_coordinator.py::ChatSandboxPoolAcquisitionCoordinator.claim_blank`

## Blocking ledger transitions are drained before cancellation cleanup

Database and fsync transitions run in a worker thread via asyncio.to_thread. Cancelling the awaiting coroutine does not stop that thread, so on cancellation the code waits for the thread to finish before re-raising. This prevents provider cleanup from racing a still-committing spend reservation or journal update.

Code: `backend/loadtests/persistent_executor_cold.py::_blocking_transition`

## Bound worker reservations older than a day are orphans

Unbound external-worker reservations expire on their own; bound ones are deleted when a turn is released, but a crashed or lease-lost turn leaves its row behind. Because no turn lasts a day, reservation cleanup deletes bound rows older than 24 hours (BOUND_RESERVATION_RETENTION_SECONDS) so capacity is not lost forever.

Code: `backend/services/chat_external_worker_capacity.py::BOUND_RESERVATION_RETENTION_SECONDS`, `backend/services/chat_external_worker_capacity.py::ChatExternalWorkerCapacityRepository.reserve`

## Cancelled executions re-terminate before publishing status

If cancellation was requested while a command ran, execute calls the terminate path again before publishing a cancelled result. This synchronizes with a concurrent cancel thread so containment evidence never lags the terminal state reported to callers.

Code: `backend/loadtests/persistent_executor_runtime.py::execute`

## Capacity admission precedes session creation

Turn admission validates capacity before creating a new session, so a rejected new-chat request leaves no session or message state behind.

Code: `backend/services/chat_session_service.py::ChatSessionService.begin_turn`

## Chat reconnect streams count as active chat turns during drain

Besides /api/v1/chat/stream, the reconnect endpoint /api/v1/chat/sessions/{id}/stream relays a live chat turn. Both are counted as active chat streams so a draining slot is not stopped while a reconnected client is still receiving a turn.

Code: `backend/services/deployment_lifecycle.py::DeploymentLifecycle.request`

## Cold batch admissions are durable before any sample starts

Each batch of cold samples is admitted to the journal (durably written) before any member starts its latency clock. This keeps the record of simultaneous admission trustworthy and lets an interrupted run reconcile every admitted sample.

Code: `backend/loadtests/persistent_executor_cold.py::collect_cold_stage`

## Cold latency gates count errors as infinite latency

In the 1,000-sample cold_first_pwd cohort, errored samples are scored as infinite latency so they occupy the percentile tail rather than being dropped. The 32-way burst profile additionally requires zero failures, and both profiles require every sandbox to have confirmed cleanup.

Code: `backend/loadtests/persistent_executor_cold.py::cold_stage_result`

## Cold observations persist only exception type names

Sample collection is a measurement boundary that records any failure as an observation instead of retrying. Only the exception class name is persisted in the journal, never its message, because messages may contain authorization material such as capabilities or tokens.

Code: `backend/loadtests/persistent_executor_cold.py::collect_cold_observation`

## Cold qualification budget adds to, never reuses, the prior allocation

The cold-start qualification run was approved on 2026-09-15 with a fixed budget: the entire earlier qualification allocation (16.25 USD) is preserved and a separate 25 USD cold allocation is added on top. The combined ceiling is the sum of both, so cold samples must never draw down the prior allocation.

Code: `backend/loadtests/persistent_executor_cold.py::PRIOR_ALLOCATION_MICROUSD`

## Cold qualification cohort reserves the full four-minute sandbox lifetime

The sandbox provider enforces a four-minute maximum lifetime. The separate cold-start qualification cohort reserves all of it (240 s) rather than the 120 s used by the warm durable cohort, so cold starts are not cut short.

Code: `backend/services/durable_external_qualification_contract.py::COLD_QUALIFICATION_SANDBOX_LIFETIME_SECONDS`

## Compiler qualification must read terminal results to release the VM

The LaTeX compiler transport only releases a disposable sandbox VM after the terminal job result has been read and validated. The qualification script therefore calls compiler.result() on every terminal state but never prints the content, since it may hold untrusted output; skipping the read leaks VMs.

Code: `backend/scripts/qualify_latex_compiler_sandbox.py::run_case`

## Compute intervals keep their own resource shape

Each compute interval stores its CPU and memory request and is priced from that, so later policy changes cannot rewrite historical spend.

Code: `backend/services/chat_sandbox_spend_service.py::ChatSandboxSpendService.refresh`

## Compute-disabled circuit events are committed before raising

assert_available records a durable circuit event when compute is disabled. The coordinator commits before raising SandboxError, because otherwise the session's rollback would discard the event.

Code: `backend/services/chat_sandbox_pool_acquisition_coordinator.py::ChatSandboxPoolAcquisitionCoordinator._claim_candidate`

## Compute-disabled rejection is raised after the transaction commits

When reservation raises ChatComputeDisabled, the coordinator captures it and exits the transaction normally so the durable circuit trip is committed, then raises SandboxError outside. Raising inside the transaction would roll back the trip.

Code: `backend/services/chat_sandbox_acquisition_coordinator.py::ChatSandboxAcquisitionCoordinator`

## Counter publish happens inside the request try block

Request counters are incremented before publishing them to shared state. The publish runs inside the try whose finally decrements them, so a failed write (for example ENOSPC) cannot leak the increment and leave a drained slot reporting busy until it is stopped.

Code: `backend/services/deployment_lifecycle.py::DeploymentLifecycle.request`

## Deployed DB sessions disable autoflush; flush before same-transaction reads

Deployed repository sessions run with autoflush off. Code that mutates a row and then queries for it in the same transaction (spend reconciliation, provider identity on compute intervals, qualification checks) must call db.flush() explicitly, or the later query will not see the change.

Code: `backend/scripts/qualify_chat_sandbox_spend.py::main`, `backend/services/chat_sandbox_spend_service.py::ChatSandboxSpendService.provider_created`

## Discovery pages router is registered last

The discovery_pages router serves the public homepage and entity HTML routes and includes a top-level /{slug} organization fallback. FastAPI matches routes in registration order, so the router must be included after every other router or the fallback would shadow their paths.

Code: `backend/main.py::create_app`

## Durable event ack only for journal-backed streams

worker_ready proves the trusted harness accepted the run but is not forwarded to the browser SSE contract. Durable event acknowledgement is enabled only when the worker supports it and durable turn dispatch is on, because live streams have no event journal and must keep the original terminal acknowledgement behaviour.

Code: `backend/services/chat_external_pi_turn_runner.py::ExternalPiChatTurnRunner._events`

## Durable qualification budgets three provider requests per tool turn

Each qualification tool turn may need one model call that selects Bash, a second that selects Read, and a third that synthesizes the visible answer from both results. The OpenAI request limit for the durable 32-user qualification is therefore sized with three provider requests per tool turn.

Code: `backend/services/durable_external_qualification_contract.py::DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN`

## Durable qualification preflight uses a fixed resource envelope

The 32-turn durable external qualification profile reserves a fixed 2 GiB of projected memory and an 80% CPU guard. The envelope is deliberately explicit and is not scaled up from detected host RAM, so the approved profile behaves the same on any host and cannot over-commit the 16 GB VPS.

Code: `backend/services/durable_external_qualification_system.py::_system_resource_preflight`

## Durable-ack workers release only a consumed prefix

Older external Pi workers keep the original protocol and receive an immediate terminal ack on worker_done. Workers that advertise durable_event_ack may only be released for a durably consumed event prefix; if persistence lags, the runner withholds the ack and the worker's bounded terminal grace owns cleanup.

Code: `backend/services/chat_external_pi_turn_runner.py::ExternalPiChatTurnRunner._events`

## Event receipt failures are tolerated

Event acknowledgements to the external Pi worker are cumulative. A lost receipt only means the worker retains replay frames; a later receipt advances progress and the terminal grace period bounds cleanup if the final ack fails. Transport errors on receipts are therefore ignored instead of failing the turn.

Code: `backend/services/chat_external_pi_turn_runner.py::ExternalPiChatTurnRunner._events.acknowledge_persisted`

## Executor admin requests re-check idempotency after taking the cell lock

Executor key revocation and rollback requests are idempotent by request ID and serialize on a SELECT ... FOR UPDATE of the executor cell. A retry may have waited behind the original request while it committed, so the request-ID audit row is re-read after acquiring the cell lock and before advancing the epoch or rolling back. Checking only before the lock would double-apply the mutation.

Code: `backend/services/chat_executor_registry.py::ChatExecutorRegistry.revoke_key`, `backend/services/chat_executor_registry.py::ChatExecutorRegistry.rollback_manifest`

## Executor data is sent before the open ACK

Open and data frames keep wire order, so the first data frame is sent before awaiting the open acknowledgement to save a round trip. ExecutorClient has already marked payload delivery attempted, so failures recover by execution ID rather than by replaying the payload.

Code: `backend/services/chat_sandbox_executor_channel.py::PersistentSandboxExecutorChannel._send_stream_data`

## Executor key validity windows are enforced at use, not at startup

Startup validation checks only the shape and ordering of the chat executor authorization and admission key windows. Whether the current time falls inside a window is enforced where the key is used (executor_transport admission and sign_admission). Checking it at startup would make an expiring key stop every backend worker at its next restart; expiry is instead surfaced by chat_config_expiry.

Startup validation checks only the shape and ordering of the chat executor admission key window; sign_admission enforces the current time against it. Checking the time at startup would make an expiring key stop every backend worker at its next restart.

Code: `backend/services/runtime_validation.py::validate_runtime_settings`

## Executor tool_call_id uses the harness operation ID

Provider tool-call IDs are untrusted and may contain characters outside the executor protocol grammar. The executor context uses the harness-issued operation ID, already unique, replay-stable and bound to the provider call.

Code: `backend/services/chat_external_pi_tool_executor.py::ExternalPiToolWorkspaceExecutor._context`

## Executor-backed blanks rely on rendezvous readiness

With the executor runtime, blank readiness comes from the rendezvous registration, and resolving the sandbox handle runs no Modal command and opens no legacy control channel. The legacy health-check path is used only for non-executor blanks.

Code: `backend/services/chat_sandbox_pool_maintenance_coordinator.py::ChatSandboxPoolMaintenanceCoordinator.pool_sandbox_health`

## Existing Pi session binding is returned on retry

A failed reusable-sandbox assignment may already have durably created the native Pi session before the coordinator retries the same admitted turn in a replacement sandbox. create_or_bind_session returns the existing binding so the new worker restores that transcript instead of creating a conflicting one.

Code: `backend/services/chat_pi_transcript_service.py::ChatPiTranscriptService.create_or_bind_session`

## External Pi turns clear the Modal sandbox shape from latency rows

Routing to the external Pi fleet is decided after admission, so the latency row starts with the Modal sandbox CPU/memory shape. mark_external_pi must clear it; otherwise finalize bills requested Modal resources for a sandbox never created and inflates the Modal spend circuits.

Code: `backend/tests/chat/test_latency_service.py::test_external_pi_turns_are_not_billed_for_an_unused_sandbox`

## External Pi turns correct their recorded sandbox shape

Admission records a Modal sandbox shape because routing is only resolved when the capability is issued. When the turn routes to the external Pi worker, the latency row is corrected immediately so the turn is not billed for Modal compute it never uses.

Code: `backend/services/chat_turn_runner.py::create_chat_turn_runner`

## Feedback route commits or rolls back itself

The request-scoped DB session only closes at exit and never commits, so the feedback route must commit a stored rating explicitly and roll back when nothing was stored.

Code: `backend/tests/chat/test_session_routes.py::test_feedback_route_commits_the_stored_rating`

## First authenticated heartbeat completes executor registration

A heartbeat can authenticate only after the bound identity accepted the registration response. The first heartbeat therefore marks the registration attempt complete, closing the response-loss recovery window, before reconnect state is created.

Code: `backend/services/chat_executor_bootstrap.py::ExecutorBootstrapStateMachine.issue_reconnect_token`

## LaTeX compiler Sandbox image defaults to blank

A per-job HF Sandbox is the only transport for LaTeX compilation. The image setting defaults to an empty string so staging cannot accidentally create a VM; an explicit reviewed image must be configured before any Sandbox is launched.

Code: `backend/chat_configuration/settings.py::ChatArtifactSettings`

## LaTeX compiler signing key stays in the backend; Sandboxes get only the public key

The private signing key for LaTeX compiler jobs lives only in the PwC backend environment. Each disposable HF Sandbox receives the matching public key solely through its per-job environment, so a compromised Sandbox cannot mint job tokens.

Code: `backend/chat_configuration/settings.py::ChatArtifactSettings`

## LaTeX sandbox preflight proves network isolation before accepting manuscripts

Each compiler sandbox first runs latex_compiler_space.preflight, which starts an unprivileged user and network namespace and refuses to proceed if any default route exists. Only after it passes are manuscript bytes submitted, so untrusted LaTeX can never reach the network.

Code: `backend/services/latex_compiler_service.py::HuggingFaceSandboxLatexCompilerTransport._create_session`

## Landing commit yields once to surface pending cancellation

After the synchronous landing commit, _resolve_landing awaits asyncio.sleep(0) so a cancellation requested during the commit is delivered there and classified as an ambiguous landing, instead of surfacing later in unrelated code.

Code: `backend/services/chat_sandbox_pool_creation_coordinator.py::ChatSandboxPoolCreationCoordinator._resolve_landing`

## Latency results alone never qualify the cold stage

Timing observations cannot attest host resources, simultaneous admission or identity, so cold_stage_result always reports cold_stage_qualified = False even when all latency gates pass. Qualification requires separate evidence beyond this result.

Code: `backend/loadtests/persistent_executor_cold.py::cold_stage_result`

## Legacy executor channel release is a no-op

Legacy relays install and revoke workspace access around each operation, so _LegacyExecutorChannel.release_workspace does nothing. Adding a release there would double-revoke.

Code: `backend/services/chat_external_pi_tool_executor.py::_LegacyExecutorChannel.release_workspace`

## Lending a tree makes release-copied files writable for the build user

The Pi build copies package-lock.json from the immutable release, where files are mode 0444, and npm prune rewrites it. Root could write it regardless of mode, but the unprivileged pwc-build user cannot, so lend must make copied files writable for the build user, not just change ownership.

Code: `backend/tests/deployment/test_build_sandbox.py::test_lend_lets_the_build_user_write_files_copied_from_the_release`

## Local sandbox cost estimates use resource requests

Modal bills the greater of the resource request and actual usage, not the configured burst limit. Local accrual uses the request-based rate, and provider reconciliation raises it when actual usage was higher.

Code: `backend/services/chat_sandbox_spend_service.py::ChatSandboxSpendService._interval_rate`

## Lost lease reports 'starting' and keeps the lost generation

When an external Pi worker loses its lease, the runtime goes back through registration, so the durable status file reports worker_state 'starting' (the same transitional state as a fresh start) until a new claim lands. The lost claim generation is kept on record because the worker endpoint remains bound to it until re-registration replaces it.

Code: `backend/scripts/run_external_pi_slot.py::_status_update`

## Middleware order: CORS outside catalog admission outside handlers

In deployed environments CatalogAdmissionMiddleware is added after the routers and other middleware so it wraps them and rejects excess catalog traffic before database sessions or response buffers are allocated. PublicReadCorsMiddleware is added after it so it is outermost and admission rejections still carry CORS headers that browser clients can read.

PublicReadCorsMiddleware is added after CatalogAdmissionMiddleware so that it is the outermost layer; otherwise admission rejections would lack CORS headers and browser clients could not read them.

Code: `backend/main.py::create_app`

## Modal metadata cache is keyed by PID, loop and client

Resolved Modal app and image metadata is cached per process, event loop, client, environment and image ID. Including the loop and client prevents asyncio locks and credentials from being reused across event-loop or client lifetimes.

Code: `backend/services/chat_modal_metadata.py::_entry`

## Modal region multipliers are explicit; unknown regions fail

Sandbox pricing applies Modal's region multiplier (eu-west 1.75x, from https://modal.com/docs/guide/region-selection, verified 2026-09-14). The lookup is a strict dict index so moving the sandbox to an unlisted region fails at import instead of silently using base pricing.

Code: `backend/services/chat_sandbox_pricing.py::_REGION_MULTIPLIERS`

## Open timeout covers only the acknowledgement

The executor stream opening deadline bounds the open acknowledgement only. Once an on-time ACK arrives the timeout is cleared, so a payload write that is still draining is not cancelled by the opening deadline.

Code: `backend/services/chat_sandbox_executor_channel.py::PersistentSandboxExecutorChannel._dispatch`

## OpenAI call allowance grows faster than the capacity tier

OpenAI concurrency equals the external Pi tier, but the ten-minute call allowance grows faster because an MCP research turn spends 10-13 model calls and a full tier of turns cycles several times per window. The 32-turn tier keeps each environment's established allowance (production 512, staging 300); 64 turns get 4096.

Code: `backend/services/runtime_policies/chat_runtime_profile.py::_EXTERNAL_PI_OPENAI_RATE_LIMIT_CALLS`

## Paper-enabled turns get process headroom for the LaTeX extension

The worker starts under normal turn limits and extends only after an authenticated paper command. The process-level timeout for paper-enabled turns is therefore raised to the LaTeX paper timeout so the worker survives long enough to receive that extension.

Code: `backend/services/chat_sandbox_turn_coordinator.py::ChatSandboxTurnCoordinator._run_once`

## Persistent workspace claims are single-use

A persistent executor claim is consumed by its first attachment attempt, even when attachment fails; the binding is marked failed and the workspace invalidated rather than retried with the same claim.

Code: `backend/services/chat_external_pi_tool_executor.py::ExternalPiToolWorkspaceExecutor._turn_binding`

## Pi harness migration supports only 0% or 100% of new sessions

chat_new_session_pi_percentage accepts 0-100 in the schema, but runtime identity validation rejects anything except 0 (stop) and 100 (full cutover). Partial rollouts are not supported; Pi qualification instead uses an authenticated per-session override.

Code: `backend/chat_configuration/settings.py::ChatAdmissionSettings`

## Pi session header is not a tree entry

In Pi transcripts the session header entry carries Pi's own session ID, not a tree entry ID, so it is stored without entry or parent IDs.

Code: `backend/services/chat_pi_transcript_service.py::_envelope`

## Pinned Modal images are hydrated once

For an existing im- image ID, Image.build only fetches metadata (ImageFromId) and does not rebuild. Hydrating once and caching the image prevents every Sandbox.create from repeating that lookup.

Code: `backend/services/chat_modal_metadata.py::executor_metadata`

## Pool qualification replays a seven-day production arrival profile

The production_7d arrival profile comes from seven days of production telemetry (462 arrivals): 4.6% of gaps were at most 15 s, at most two arrivals in any 15 s window and three in 30 s. Long idle gaps are clipped to 30 s because blank-sandbox startup p90 is below that, and one 10 s/20 s pair reproduces the observed three-arrival burst.

Code: `backend/scripts/qualify_chat_pool.py::arrival_offsets_ms`

## Pool readiness probes do not consume the workspace

The pool readiness check claims liveness with a fresh short-lived nonce that is deliberately not consumed, so only a real turn can claim the workspace with its own liveness assertion. Uncertain transport failures propagate to the pool's skip and retry handling rather than being swallowed.

Code: `backend/services/chat_executor_runtime.py::ChatExecutorRuntime.pool_ready`

## Pre-dispatch retries never reselect the failed control

A retry reaches acquisition only after the existing control failed before SDK dispatch. Acquisition forces a pool miss instead of selecting the same in-memory control, even if lifecycle cleanup has not yet removed it from the transport.

Code: `backend/services/chat_sandbox_turn_coordinator.py::ChatSandboxTurnCoordinator._acquire_for_turn`

## Qualification scope lock comes first

Qualification evidence locks follow a fixed order: scope, then reservation, then capability for reconstructed Pi runners, and scope, then capacity, then sandbox lease for executor acquisition. The caller's transaction holds the scope row lock through its final mutation. Taking these locks in another order risks deadlocks.

Code: `backend/services/chat_durable_qualification_evidence.py::ChatDurableQualificationEvidenceService._active_functional_turn`

## Reclaim refuses symlink chains through build-user-owned pivots

When reclaiming a tree from the unprivileged pwc-build user, deploy/build_sandbox.py refuses launchers whose symlink chain hops through a link outside the tree, even if that link currently resolves to the system interpreter. The build user may own the pivot and retarget it later, so current resolution is not proof of safety.

Code: `backend/tests/deployment/test_build_sandbox.py::test_reclaim_refuses_launchers_that_hop_through_an_outside_pivot`

## Reclaimed health claims defer other drains a cycle

A reclaimed stale health claim is already a complete termination claim and still appears as draining in the same transaction. When any are reclaimed, the termination limit is set to zero for that cycle so planning cannot rotate its token and issue duplicate provider termination calls.

Code: `backend/services/chat_sandbox_pool_maintenance_coordinator.py::ChatSandboxPoolMaintenanceCoordinator._plan_maintenance`

## Relay close marks the opening future's exception observed

A relay can close before its caller awaits the opening future. The channel reads the future's exception immediately so asyncio does not log an unobserved exception, while any existing waiter still receives the same error.

Code: `backend/services/chat_sandbox_executor_channel.py::_VirtualRelay._finish`

## Remote executor readiness comes only from authenticated registration

For remote executors, sandbox creation returns without Modal exec health probes: only authenticated durable registration establishes readiness, because exec probes cannot prove remote identity and are kept off the warm path.

Code: `backend/services/chat_sandbox_provider.py::ModalSandboxProviderAdapter.create`

## Rollback requires an active blue/green slot

The old fixed-port rollback path re-synced the shared runtime as root. Both production and staging now run blue/green slots, so rollback without an active slot is refused rather than falling back to that root re-sync.

Code: `backend/tests/deployment/test_activation_rollback.py::test_rollback_without_an_active_slot_is_retired`

## SSE qualification reads one byte at a time

Qualification measures time to the first semantic SSE event, so the transport iterates with chunk_size=1 instead of waiting for urllib3 to fill a larger read buffer. The cost is acceptable because only the bounded synthetic staging workload uses this path.

Code: `backend/loadtests/durable_chat_transport.py::HttpSSEDurableChatTransport._events`

## Sandbox billing is bounded by Modal's 24-hour timeout

Modal enforces at most a 24-hour timeout on every sandbox, so spend accounting assumes no provider instance bills past creation plus 86,400 seconds.

Code: `backend/services/chat_sandbox_spend_service.py::PROVIDER_MAX_SANDBOX_LIFETIME_SECONDS`

## Sandbox cost per second uses pinned region pricing

Sandbox cost per second is computed as (CPU count x 39.42 + GiB memory x 6.72) x 1.75 for the pinned region multiplier, rounded up to whole micro-USD; one CPU with 2 GiB costs 93 micro-USD per second. Spend reservations are taken at this rate before provider creation.

Code: `backend/tests/chat_sandbox/test_spend_service.py::test_pinned_region_price_is_reserved_before_provider_creation`

## Sandbox creation never passes environment_name

Modal derives the sandbox environment from the App object, so Sandbox.create is called without environment_name; passing it separately can disagree with the app's environment.

Code: `backend/tests/chat_sandbox/test_provider.py::test_fresh_executor_launches_use_metadata_but_create_distinct_sandboxes`

## Snapshot reclaim counts as sandbox replacement

During Pi qualification, a session with no live sandbox ID was snapshotted or reclaimed between turns, so the follow-up must acquire a new provider sandbox. It counts as a replacement when durable compute history proves a prior sandbox existed, rather than forcing a terminate.

Code: `backend/scripts/qualify_chat_pi.py::_terminate_session_sandbox`

## Spend is reserved before the sandbox lease changes

Sandbox start reserves the spend interval before mutating the lease. A rejected reservation may trip the durable spend circuit but leaves the lease exactly as it was, so a budget denial never corrupts lease state.

Code: `backend/services/chat_sandbox_capacity_repository.py::ChatSandboxCapacityRepository.acquire`

## Spend refresh runs after persisting the provider floor

Provider reconciliation persists the provider-authoritative floor and coverage boundary before recomputing state, so orphan estimates from already-closed billing hours are not counted on top of the provider floor.

Code: `backend/services/chat_sandbox_spend_service.py::ChatSandboxSpendService._reconcile_provider_floor`

## Spend-cap termination counts differ by source

SpendCapEnforcementResult.terminated counts lease actions as attempted even when the durable claim is already gone, pool rows only on successful claims, and provider rows only on confirmed, durably accounted terminations.

Code: `backend/tests/chat_sandbox/test_spend_cap_coordinator.py::test_enforcement_preserves_global_state_scope_order_and_action_counts`

## Starting leases without a sandbox ID are waited on

A start owner may be between its database claim and provider sandbox creation. While a starting lease has no provider sandbox ID there is nothing safe to recover, so callers wait for the lease even if the owner's target image has since become incompatible.

Code: `backend/services/chat_sandbox_capacity_repository.py::ChatSandboxCapacityRepository._select_locked`

## Supervisor reclaims idle drained workers after restart

An External Pi worker in the draining state never returns to ready on its own. If the supervisor refused to register a drained worker on startup, a single supervisor restart became a permanent crash loop that systemd could not escape. The supervisor therefore rebinds an idle drained worker under a new worker generation.

Code: `backend/tests/external_pi/test_supervisor.py::test_supervisor_reclaims_an_idle_drained_worker_after_restart`

## Supervisor reclaims idle draining Pi workers

An external Pi worker stays draining for the rest of its process lifetime and only the deploy path recycles it. Refusing to register a draining worker would turn one supervisor restart into a permanent crash loop, so a draining worker with zero active sessions is reclaimed; bind_claim advances the fencing generation and still proves it returned to ready.

Code: `backend/services/chat_external_pi_supervisor.py::ChatExternalPiSupervisor.register`

## Suppress gevent MonkeyPatchWarning when importing the Locust adapter

Pytest imports the dependency-free load-test core, which pulls in ssl and httpx, before import-smoking the Locust adapter, so gevent warns that monkey-patching happened too late. A real Locust process patches before any import, so the warning is only a test artefact; the adapter suppresses MonkeyPatchWarning around the locust import instead of restructuring the test imports.

Code: `backend/loadtests/external_pi_shadow_locustfile.py`

## Terminal ack uses a fenced control channel

The producer can finish before its queued terminal event is durably committed. The runner then releases the worker's retained run over the fenced terminal-control channel with a short timeout, instead of keeping the producer alive during persistence.

Code: `backend/services/chat_external_pi_turn_runner.py::ExternalPiChatTurnRunner._events.acknowledge_persisted`

## Transcript appends require chat and agent session to match

The capability binds the chat, but the agent session ID is supplied by the caller. Appends proceed only when the agent session ID matches the session bound to that chat, so a caller cannot write into another chat's transcript that shares the ID.

Code: `backend/services/chat_pi_transcript_service.py::ChatPiTranscriptService.append_entries`

## Turn authorization deadlines are converted once to monotonic time

A turn's absolute wall-clock deadline is converted once to a monotonic deadline at authorization time. Later wall-clock adjustments therefore cannot extend the authorization, and time spent during conversion is subtracted, which is conservative.

Code: `backend/loadtests/persistent_executor_runtime.py::authorize`

## Turn runners release the workspace before publishing done

A stream consumer may close as soon as the done event is published, so the turn runner must release its workspace before emitting done. Releasing afterwards would leak the workspace whenever the consumer disconnects immediately on completion.

Code: `backend/tests/external_pi/turn_runner/test_runner_execution.py::exercise`

## Turn teardown failures publish fail-closed evidence

Teardown talks to external systems and may fail in arbitrary ways. Any exception marks the outcome unknown and retains the reservation, and containment evidence is always published in finally, so concurrent callers waiting on that evidence never block forever and spend is not released prematurely.

Code: `backend/loadtests/persistent_executor_runtime.py::cancel`

## Unconfirmed sandbox creations retain spend reservations

When sandbox creation or termination cannot be confirmed, the observation is journaled without releasing its spend reservation. Reservations are only released after termination is confirmed, so later reconciliation can account for sandboxes that may still be billing.

Code: `backend/loadtests/persistent_executor_cold.py::collect_cold_observation`

## Worker counter publishes are retried until a write succeeds

Each backend worker publishes its in-flight HTTP, chat and gateway counts to a shared state file used to decide when a drained slot is idle. The publish-pending flag is set before writing and cleared only on success, so a failed write (for example ENOSPC) is retried from status() even if the worker receives no further traffic, preventing a slot from reporting stale busy counts forever.

Code: `backend/services/deployment_lifecycle.py::DeploymentLifecycle._publish_locked`, `backend/services/deployment_lifecycle.py::DeploymentLifecycle._status_locked`

## Worker lease errors are retried at registration but fence heartbeats

During registration, an unreachable worker or database, or a still-live lease from a previous claim (WorkerLeaseUnavailable), is retried within the registration window. During heartbeats, transport errors keep retrying until the local lease window ends, but StaleWorkerClaim or WorkerLeaseUnavailable means a newer generation fenced the claim or the durable lease expired, so that claim must never be heartbeated again. The same exception class is therefore retryable in one phase and terminal in the other.

Code: `backend/services/chat_external_pi_supervisor_runtime_service.py::_REGISTRATION_RETRY_ERRORS`, `backend/services/chat_external_pi_supervisor_runtime_service.py::_HEARTBEAT_TRANSPORT_ERRORS`, `backend/services/chat_external_pi_supervisor_runtime_service.py::_HEARTBEAT_FENCED_ERRORS`

## Worker status checks retry until the Pi worker binds its port

systemd reports a Type=simple worker unit active as soon as it execs, while the Node process is still loading the Pi runtime and has not bound its port. A single status probe in that window gets a refused connection, which previously failed the whole deployment. Worker status checks therefore retry across that startup window instead of treating the first refusal as failure.

Code: `backend/tests/external_pi/test_slot_systemd_and_status.py::test_worker_status_tolerates_the_window_before_the_worker_binds`

## Workspace manager assembles dependencies via local imports

The external executor workspace module imports the SandboxSessionManager compatibility façade only inside its factory. This keeps the façade out of the domain module's import graph, avoiding import cycles, while reusing the façade's single validated dependency assembly.

Code: `backend/services/chat_external_executor_workspace.py::ChatExternalExecutorWorkspaceManager.from_settings`

## Workspace settles before the done event is yielded

Yielding the done event lets the stream consumer cancel the producer. The tool executor therefore settles and releases the retained workspace before yielding done, and again in finally, so cancellation cannot leak a held workspace.

Code: `backend/services/chat_external_pi_turn_runner.py::ExternalPiChatTurnRunner.events`

## Workspace snapshot delete only drops the reference

Modal Images have no early-delete API. Deleting a workspace snapshot drops the durable reference, which revokes application access, and relies on Modal's TTL for actual deletion.

Code: `backend/services/chat_sandbox_service.py::WorkspaceSnapshotProvider.delete`

## requests is imported lazily so Locust patches networking first

The load-test transport imports `requests` inside _requests_session so Locust/gevent can monkey-patch networking before requests loads in live runs. A module-level import breaks cooperative I/O.

Code: `backend/loadtests/durable_chat_transport.py::_requests_session`

## worker_ready events never reach the browser

Persistent Pi controls emit worker_ready for every run so dispatch can prove the harness accepted the correlated request. The transport converts it to an internal milestone; it must never be added to the browser event schema.

Code: `backend/services/chat_sandbox_worker_transport.py::WorkerTurnExecution.events`
